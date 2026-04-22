from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ur_arms_manager.config import LIBRARY_PROGRAMS_DIR, ROOT_DIR
from ur_arms_manager.library.storage import (
    AmbiguousPayloadError,
    LibraryStorage,
    MissingPayloadError,
)
from ur_arms_manager.library.urp_parser import (
    list_editable_urp_params,
    parse_urp_metadata,
    update_urp_param,
)


class LibraryError(Exception):
    pass


class LibraryManager:
    def __init__(self, programs_root: Path | None = None, root_dir: Path | None = None):
        self.storage = LibraryStorage(programs_root or LIBRARY_PROGRAMS_DIR)
        self.root_dir = root_dir or ROOT_DIR
        self.storage.ensure()

    def list_items(self) -> list[dict[str, Any]]:
        return [self.inspect_item(path_ref) for path_ref in self.storage.list_program_ids()]

    def list_directory(self, relative_dir: str = "") -> list[dict[str, Any]]:
        try:
            entries = self.storage.list_entries(relative_dir)
        except FileNotFoundError as exc:
            raise LibraryError(str(exc)) from exc

        return [self._serialize_entry(path) for path in entries]

    def add_item(
        self, local_file_path: str, extra_metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        source = Path(local_file_path).expanduser()
        if not source.is_absolute():
            source = (self.root_dir / source).resolve()

        if not source.exists() or not source.is_file():
            raise LibraryError(f"Local source file not found: {source}")

        target_dir = "uploaded"
        preferred_name = source.name
        if extra_metadata and extra_metadata.get("origin") == "robot_remote":
            source_robot = str(extra_metadata.get("source_robot") or "").strip()
            if source_robot:
                target_dir = source_robot
                preferred_name = f"{source_robot}_{source.name}"

        try:
            stored_file = self.storage.copy_program_file(
                source,
                target_dir=target_dir,
                preferred_name=preferred_name,
            )
            return self.inspect_item(self.storage.relative_path(stored_file))
        except Exception as exc:
            raise LibraryError(f"Failed to add file to library from '{source}': {exc}") from exc

    def create_folder(self, relative_dir: str) -> dict[str, Any]:
        try:
            path = self.storage.create_folder(relative_dir)
            return self._serialize_entry(path)
        except FileExistsError as exc:
            raise LibraryError(f"Library folder already exists: {relative_dir}") from exc
        except Exception as exc:
            raise LibraryError(f"Failed to create library folder '{relative_dir}': {exc}") from exc

    def move_item(self, source_rel: str, destination_rel: str) -> dict[str, Any]:
        try:
            destination = self.storage.move_path(source_rel, destination_rel)
            return self._serialize_entry(destination)
        except Exception as exc:
            raise LibraryError(f"Failed to move library path '{source_rel}': {exc}") from exc

    def copy_item(self, source_rel: str, destination_rel: str) -> dict[str, Any]:
        try:
            destination = self.storage.copy_path(source_rel, destination_rel)
            return self._serialize_entry(destination)
        except Exception as exc:
            raise LibraryError(f"Failed to copy library path '{source_rel}': {exc}") from exc

    def inspect_item(self, path_ref: str) -> dict[str, Any]:
        path = self.storage.resolve_path(path_ref)
        if not path.exists():
            raise LibraryError(f"Library path not found: {path_ref}")
        if path.is_dir() and self._looks_like_legacy_item_dir(path):
            try:
                payload = self.storage.resolve_payload_file(path_ref)
                return self._serialize_entry(payload, reference=path_ref)
            except (MissingPayloadError, AmbiguousPayloadError) as exc:
                raise LibraryError(str(exc)) from exc
        return self._serialize_entry(path)

    def inspect_item_enriched(self, path_ref: str) -> dict[str, Any]:
        item = self.inspect_item(path_ref)
        if item["item_kind"] != "file" or str(item.get("extension", "")).lower() != "urp":
            return item

        try:
            path = self.get_stored_file(path_ref)
        except LibraryError as exc:
            item["urp_analysis"] = {
                "parse_success": False,
                "parse_error": str(exc),
            }
            return item

        item["urp_analysis"] = parse_urp_metadata(path)
        return item

    def get_stored_file(self, path_ref: str) -> Path:
        try:
            return self.storage.resolve_payload_file(path_ref)
        except MissingPayloadError as exc:
            raise LibraryError(f"Stored library payload not found for '{path_ref}': {exc}") from exc
        except AmbiguousPayloadError as exc:
            raise LibraryError(f"Stored library payload is ambiguous for '{path_ref}': {exc}") from exc
        except ValueError as exc:
            raise LibraryError(str(exc)) from exc

    def ensure_script_item(self, path_ref: str) -> dict[str, Any]:
        item = self._inspect_payload_item(path_ref)
        if str(item.get("extension", "")).lower() != "script":
            raise LibraryError(f"Library item is not a .script program: {path_ref}")
        return item

    def ensure_urp_item(self, path_ref: str) -> dict[str, Any]:
        item = self._inspect_payload_item(path_ref)
        if str(item.get("extension", "")).lower() != "urp":
            raise LibraryError(f"Library item is not a .urp program: {path_ref}")
        return item

    def get_script_file(self, path_ref: str) -> Path:
        self.ensure_script_item(path_ref)
        return self.get_stored_file(path_ref)

    def list_urp_editable_params(self, path_ref: str) -> dict[str, str]:
        self.ensure_urp_item(path_ref)
        path = self.get_stored_file(path_ref)
        try:
            return list_editable_urp_params(path)
        except Exception as exc:
            raise LibraryError(f"Failed to list editable URP params for '{path_ref}': {exc}") from exc

    def set_urp_param(self, path_ref: str, param_name: str, value: str) -> dict[str, str]:
        self.ensure_urp_item(path_ref)
        path = self.get_stored_file(path_ref)
        try:
            return update_urp_param(path, param_name, value)
        except Exception as exc:
            raise LibraryError(
                f"Failed to update URP param '{param_name}' for '{path_ref}': {exc}"
            ) from exc

    def get_stored_filename(self, path_ref: str) -> str:
        return self.get_stored_file(path_ref).name

    def remove_item(self, path_ref: str) -> dict[str, Any]:
        item = self.inspect_item(path_ref)
        try:
            self.storage.remove_path(path_ref)
            return item
        except FileNotFoundError as exc:
            raise LibraryError(str(exc)) from exc

    def _inspect_payload_item(self, path_ref: str) -> dict[str, Any]:
        item = self.inspect_item(path_ref)
        if item["item_kind"] == "file":
            return item
        path = self.storage.resolve_path(path_ref)
        if path.is_dir():
            try:
                payload = self.storage.resolve_payload_file(path_ref)
            except (MissingPayloadError, AmbiguousPayloadError) as exc:
                raise LibraryError(str(exc)) from exc
            return self._serialize_entry(payload, reference=path_ref)
        return item

    def _looks_like_legacy_item_dir(self, path: Path) -> bool:
        if (path / "manifest.yaml").exists():
            return True
        payload_candidates = [
            child for child in path.iterdir() if child.is_file() and child.name != "manifest.yaml"
        ]
        return len(payload_candidates) == 1

    def _serialize_entry(self, path: Path, reference: str | None = None) -> dict[str, Any]:
        rel_path = self.storage.relative_path(path)
        program_id = reference or rel_path
        stat = path.stat()
        extension = path.suffix.lower().lstrip(".") if path.is_file() else ""
        top_level = Path(rel_path).parts[0] if rel_path else ""
        origin = "robot_remote" if top_level.startswith("robot") else "local"
        source_robot = top_level if origin == "robot_remote" else None
        item_kind = "directory" if path.is_dir() else "file"
        payload_status = "ok" if path.is_file() else ""

        return {
            "program_id": program_id,
            "relative_path": rel_path,
            "name": path.name,
            "original_filename": path.name,
            "stored_filename": path.name if path.is_file() else None,
            "stored_path": str(path),
            "extension": extension,
            "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "size_bytes": stat.st_size if path.is_file() else None,
            "origin": origin,
            "source_robot": source_robot,
            "source_remote_path": None,
            "item_kind": item_kind,
            "is_dir": path.is_dir(),
            "payload_status": payload_status,
            "payload_error": None,
        }
