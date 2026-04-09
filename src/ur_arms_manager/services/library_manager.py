from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ur_arms_manager.config import LIBRARY_PROGRAMS_DIR, ROOT_DIR
from ur_arms_manager.library.manifest import read_manifest, write_manifest
from ur_arms_manager.library.storage import LibraryStorage
from ur_arms_manager.library.urp_parser import list_editable_urp_params, parse_urp_metadata, update_urp_param


class LibraryError(Exception):
    pass


class LibraryManager:
    def __init__(self, programs_root: Path | None = None, root_dir: Path | None = None):
        self.storage = LibraryStorage(programs_root or LIBRARY_PROGRAMS_DIR)
        self.root_dir = root_dir or ROOT_DIR
        self.storage.ensure()

    def list_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for program_id in self.storage.list_program_ids():
            items.append(self.inspect_item(program_id))
        return items

    def add_item(
        self, local_file_path: str, extra_metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        source = Path(local_file_path).expanduser()
        if not source.is_absolute():
            source = (self.root_dir / source).resolve()

        if not source.exists() or not source.is_file():
            raise LibraryError(f"Local source file not found: {source}")

        program_id = self._generate_program_id(source)
        program_id = self._ensure_unique_program_id(program_id)
        try:
            stored_file = self.storage.copy_program_file(program_id, source)
            extension = source.suffix.lower().lstrip(".")
            created_at = datetime.now(timezone.utc).isoformat()

            manifest = {
                "program_id": program_id,
                "original_filename": source.name,
                "stored_filename": stored_file.name,
                "stored_path": str(stored_file),
                "extension": extension,
                "created_at": created_at,
                "source_path": str(source),
                "size_bytes": source.stat().st_size,
            }
            if extra_metadata:
                manifest.update(extra_metadata)
            write_manifest(self.storage.manifest_path(program_id), manifest)
            return manifest
        except Exception as exc:
            # Best effort cleanup to avoid half-written library item directories.
            program_dir = self.storage.program_dir(program_id)
            if program_dir.exists():
                self.storage.remove_program(program_id)
            raise LibraryError(f"Failed to add library item from '{source}': {exc}") from exc

    def inspect_item(self, program_id: str) -> dict[str, Any]:
        manifest_path = self.storage.manifest_path(program_id)
        if not manifest_path.exists():
            raise LibraryError(f"Library item not found: {program_id}")
        return read_manifest(manifest_path)

    def inspect_item_enriched(self, program_id: str) -> dict[str, Any]:
        item = self.inspect_item(program_id)
        if str(item.get("extension", "")).lower() != "urp":
            return item

        stored_path = item.get("stored_path")
        if not stored_path:
            item["urp_analysis"] = {
                "parse_success": False,
                "parse_error": "Missing stored_path for URP item",
            }
            return item

        path = Path(str(stored_path))
        if not path.exists() or not path.is_file():
            item["urp_analysis"] = {
                "parse_success": False,
                "parse_error": f"Stored URP file not found: {path}",
            }
            return item

        item["urp_analysis"] = parse_urp_metadata(path)
        return item

    def get_stored_file(self, program_id: str) -> Path:
        item = self.inspect_item(program_id)
        stored_path = item.get("stored_path")
        if not stored_path:
            raise LibraryError(f"Library item has no stored_path: {program_id}")

        path = Path(str(stored_path))
        if not path.exists() or not path.is_file():
            raise LibraryError(f"Stored library file not found: {path}")
        return path

    def ensure_script_item(self, program_id: str) -> dict[str, Any]:
        item = self.inspect_item(program_id)
        extension = str(item.get("extension", "")).lower()
        if extension != "script":
            raise LibraryError(f"Library item is not a .script program: {program_id}")
        return item

    def ensure_urp_item(self, program_id: str) -> dict[str, Any]:
        item = self.inspect_item(program_id)
        extension = str(item.get("extension", "")).lower()
        if extension != "urp":
            raise LibraryError(f"Library item is not a .urp program: {program_id}")
        return item

    def get_script_file(self, program_id: str) -> Path:
        self.ensure_script_item(program_id)
        return self.get_stored_file(program_id)

    def list_urp_editable_params(self, program_id: str) -> dict[str, str]:
        self.ensure_urp_item(program_id)
        path = self.get_stored_file(program_id)
        try:
            return list_editable_urp_params(path)
        except Exception as exc:
            raise LibraryError(f"Failed to list editable URP params for '{program_id}': {exc}") from exc

    def set_urp_param(self, program_id: str, param_name: str, value: str) -> dict[str, str]:
        self.ensure_urp_item(program_id)
        path = self.get_stored_file(program_id)
        try:
            return update_urp_param(path, param_name, value)
        except Exception as exc:
            raise LibraryError(f"Failed to update URP param '{param_name}' for '{program_id}': {exc}") from exc

    def get_stored_filename(self, program_id: str) -> str:
        item = self.inspect_item(program_id)
        stored_filename = str(item.get("stored_filename") or "").strip()
        if stored_filename:
            return stored_filename

        stored_path = item.get("stored_path")
        if stored_path:
            return Path(str(stored_path)).name
        raise LibraryError(f"Library item has no stored filename: {program_id}")

    def remove_item(self, program_id: str) -> dict[str, Any]:
        item = self.inspect_item(program_id)
        self.storage.remove_program(program_id)
        return item

    @staticmethod
    def _generate_program_id(source: Path) -> str:
        stem = source.stem.lower().replace(" ", "-")
        stem = "".join(ch for ch in stem if ch.isalnum() or ch in {"-", "_"})
        if not stem:
            stem = "program"

        file_hash = hashlib.sha1(source.read_bytes()).hexdigest()[:8]  # noqa: S324
        return f"{stem}-{file_hash}"

    def _ensure_unique_program_id(self, base_id: str) -> str:
        candidate = base_id
        index = 2
        while self.storage.program_dir(candidate).exists():
            candidate = f"{base_id}-{index}"
            index += 1
        return candidate
