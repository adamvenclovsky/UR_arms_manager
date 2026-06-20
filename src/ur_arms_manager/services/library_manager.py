from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ur_arms_manager.config import LIBRARY_PROGRAMS_DIR, ROOT_DIR
from ur_arms_manager.library.storage import (
    LibraryStorage,
    MissingPayloadError,
)
from ur_arms_manager.library.urp_parser import (
    list_editable_urp_params,
    parse_urp_metadata,
    update_urp_param,
)
from ur_arms_manager.services.runtime_validation import (
    normalize_runtime_safe_filename,
    runtime_name_safety_warning,
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
        except (FileNotFoundError, ValueError) as exc:
            raise LibraryError(str(exc)) from exc

        return [self._serialize_entry(path) for path in entries]

    def add_item(
        self,
        local_file_path: str,
        extra_metadata: dict[str, Any] | None = None,
        target_dir: str | None = None,
    ) -> dict[str, Any]:
        source = Path(local_file_path).expanduser()
        if not source.is_absolute():
            source = (self.root_dir / source).resolve()

        if not source.exists() or not source.is_file():
            raise LibraryError(f"Local source file not found: {source}")

        destination_dir = "" if target_dir is None else str(target_dir).strip("/")
        preferred_name = source.name
        if extra_metadata and extra_metadata.get("origin") == "robot_remote":
            source_robot = str(extra_metadata.get("source_robot") or "").strip()
            if source_robot:
                preferred_name = f"{source_robot}_{source.name}"

        try:
            stored_file = self.storage.copy_program_file(
                source,
                target_dir=destination_dir,
                preferred_name=preferred_name,
            )
            return self.inspect_item(self.storage.relative_path(stored_file))
        except Exception as exc:
            raise LibraryError(f"Failed to add file to library from '{source}': {exc}") from exc

    def add_bundle(
        self,
        local_file_paths: list[str],
        target_dir: str | None = None,
        bundle_name: str | None = None,
    ) -> dict[str, Any]:
        sources: list[Path] = []
        for local_file_path in local_file_paths:
            source = Path(local_file_path).expanduser()
            if not source.is_absolute():
                source = (self.root_dir / source).resolve()
            if not source.exists() or not source.is_file():
                raise LibraryError(f"Local source file not found: {source}")
            sources.append(source)

        if not sources:
            raise LibraryError("No local files were provided for bundle import.")

        target_root = "" if target_dir is None else str(target_dir).strip("/")
        source_names = [source.name for source in sources]
        urp_plan = self._build_primary_urp_plan(source_names)
        bundle_dir = self._create_unique_bundle_dir(
            target_root,
            self._sanitize_bundle_name(bundle_name or self._derive_bundle_name(sources)),
        )
        bundle_rel = self.storage.relative_path(bundle_dir)

        try:
            for source in sources:
                preferred_name = source.name
                if (
                    urp_plan["normalization_needed"]
                    and source.name == urp_plan["original_filename"]
                ):
                    preferred_name = urp_plan["runtime_safe_filename"]
                self.storage.copy_program_file(
                    source,
                    target_dir=bundle_rel,
                    preferred_name=preferred_name,
                )
            summary = self.inspect_bundle(bundle_rel)
            if urp_plan["normalization_needed"]:
                summary["primary_urp_was_normalized"] = True
                summary["primary_urp_original_filename"] = urp_plan["original_filename"]
                summary["primary_urp_runtime_safe_filename"] = urp_plan["runtime_safe_filename"]
                summary["primary_urp_normalization_needed"] = False
                summary["normalization_note"] = (
                    "Primary .urp filename was normalized for runtime-safe dashboard load."
                )
            return summary
        except Exception as exc:
            raise LibraryError(f"Failed to create bundle '{bundle_rel}': {exc}") from exc

    def preview_bundle_import(
        self,
        upload_filenames: list[str],
        target_dir: str | None = None,
        bundle_name: str | None = None,
    ) -> dict[str, Any]:
        names = [Path(name).name for name in upload_filenames if str(name).strip()]
        if not names:
            raise LibraryError("No local files were provided for bundle import.")

        safe_bundle_name = (
            self._sanitize_bundle_name(bundle_name)
            if bundle_name
            else self._derive_bundle_name_from_names(names)
        )
        target_root = "" if target_dir is None else str(target_dir).strip("/")
        bundle_path = f"{target_root}/{safe_bundle_name}" if target_root else safe_bundle_name
        return self._build_bundle_summary_from_relative_files(bundle_path, names)

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
        try:
            path = self.storage.resolve_path(path_ref)
        except ValueError as exc:
            raise LibraryError(str(exc)) from exc
        if not path.exists():
            raise LibraryError(f"Library path not found: {path_ref}")
        item = self._serialize_entry(path)
        if path.is_dir():
            item["bundle_summary"] = self._build_bundle_summary(path)
        return item

    def inspect_item_enriched(self, path_ref: str) -> dict[str, Any]:
        item = self.inspect_item(path_ref)
        if item["item_kind"] == "directory":
            bundle_summary = item.get("bundle_summary")
            if bundle_summary and bundle_summary.get("primary_urp_path"):
                try:
                    primary_path = self.get_stored_file(bundle_summary["primary_urp_path"])
                    bundle_summary["primary_urp_analysis"] = parse_urp_metadata(primary_path)
                except LibraryError as exc:
                    bundle_summary["primary_urp_analysis"] = {
                        "parse_success": False,
                        "parse_error": str(exc),
                    }
            return item
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
            raise LibraryError(f"Stored library file not found for '{path_ref}': {exc}") from exc
        except ValueError as exc:
            raise LibraryError(str(exc)) from exc

    def inspect_bundle(self, path_ref: str) -> dict[str, Any]:
        try:
            path = self.storage.resolve_path(path_ref)
        except ValueError as exc:
            raise LibraryError(str(exc)) from exc
        if not path.exists() or not path.is_dir():
            raise LibraryError(f"Library bundle not found: {path_ref}")
        return self._build_bundle_summary(path)

    def prepare_runtime_safe_bundle_copy(self, path_ref: str) -> dict[str, Any]:
        try:
            source_bundle_dir = self.storage.resolve_path(path_ref)
        except ValueError as exc:
            raise LibraryError(str(exc)) from exc
        if not source_bundle_dir.exists() or not source_bundle_dir.is_dir():
            raise LibraryError(f"Library bundle not found: {path_ref}")

        source_summary = self._build_bundle_summary(source_bundle_dir)
        primary_urp_path = str(source_summary.get("primary_urp_path") or "").strip()
        if not primary_urp_path:
            raise LibraryError(
                "Runtime-safe copy requires one deterministic primary .urp. "
                "Current bundle is missing or has ambiguous primary .urp."
            )

        original_primary_name = str(source_summary.get("primary_urp_filename") or "").strip()
        runtime_safe_primary_name = normalize_runtime_safe_filename(original_primary_name)

        source_bundle_rel = self.storage.relative_path(source_bundle_dir)
        source_bundle_name = source_bundle_dir.name
        safe_bundle_name = f"{self._sanitize_bundle_name(source_bundle_name)}_safe"
        target_bundle_dir = self._create_unique_bundle_dir(
            str(Path(source_bundle_rel).parent).strip(".").strip("/"),
            safe_bundle_name,
        )

        try:
            for path in sorted(source_bundle_dir.rglob("*")):
                if path.is_dir():
                    continue
                rel = path.relative_to(source_bundle_dir)
                preferred_name = rel.name
                if rel.as_posix() == str(Path(primary_urp_path).relative_to(Path(source_bundle_rel))):
                    preferred_name = runtime_safe_primary_name
                target_rel_dir = (
                    self.storage.relative_path(target_bundle_dir / rel.parent)
                    if str(rel.parent) != "."
                    else self.storage.relative_path(target_bundle_dir)
                )
                self.storage.copy_program_file(
                    path,
                    target_dir=target_rel_dir,
                    preferred_name=preferred_name,
                )
        except Exception as exc:
            shutil.rmtree(target_bundle_dir, ignore_errors=True)
            raise LibraryError(f"Failed to prepare runtime-safe bundle copy: {exc}") from exc

        target_summary = self._build_bundle_summary(target_bundle_dir)
        target_summary["source_bundle_path"] = source_bundle_rel
        target_summary["primary_urp_was_normalized"] = original_primary_name != runtime_safe_primary_name
        target_summary["primary_urp_original_filename"] = original_primary_name
        target_summary["primary_urp_runtime_safe_filename"] = runtime_safe_primary_name
        target_summary["normalization_note"] = (
            "Created runtime-safe non-destructive bundle copy."
        )
        return target_summary

    def get_runtime_candidate_file(self, path_ref: str) -> Path:
        item = self.inspect_item(path_ref)
        if item["item_kind"] == "file":
            self.ensure_urp_item(path_ref)
            return self.get_stored_file(path_ref)

        bundle_summary = item.get("bundle_summary") or self.inspect_bundle(path_ref)
        primary_urp_path = bundle_summary.get("primary_urp_path")
        if not primary_urp_path:
            raise LibraryError(
                f"Bundle has no deterministic primary .urp runtime candidate: {path_ref}"
            )
        return self.get_stored_file(primary_urp_path)

    def ensure_script_item(self, path_ref: str) -> dict[str, Any]:
        item = self.inspect_item(path_ref)
        if item["item_kind"] != "file" or str(item.get("extension", "")).lower() != "script":
            raise LibraryError(f"Library item is not a .script program: {path_ref}")
        return item

    def ensure_urp_item(self, path_ref: str) -> dict[str, Any]:
        item = self.inspect_item(path_ref)
        if item["item_kind"] != "file" or str(item.get("extension", "")).lower() != "urp":
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
        item = self.inspect_item(path_ref)
        if item["item_kind"] == "directory":
            return self.get_runtime_candidate_file(path_ref).name
        return self.get_stored_file(path_ref).name

    def remove_item(self, path_ref: str) -> dict[str, Any]:
        item = self.inspect_item(path_ref)
        try:
            self.storage.remove_path(path_ref)
            return item
        except FileNotFoundError as exc:
            raise LibraryError(str(exc)) from exc

    def _serialize_entry(self, path: Path) -> dict[str, Any]:
        rel_path = self.storage.relative_path(path)
        stat = path.stat()
        extension = path.suffix.lower().lstrip(".") if path.is_file() else ""
        top_level = Path(rel_path).parts[0] if rel_path else ""
        source_robot = None
        if "/" in rel_path and re.fullmatch(r"robot\d+", top_level):
            source_robot = top_level
        elif "/" not in rel_path:
            robot_prefix_match = re.match(r"^(robot\d+)_", Path(rel_path).name)
            if robot_prefix_match:
                source_robot = robot_prefix_match.group(1)
        origin = "robot_remote" if source_robot else "local"
        item_kind = "directory" if path.is_dir() else "file"
        payload_status = "ok" if path.is_file() else ""

        return {
            "program_id": rel_path,
            "library_path": rel_path,
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

    def _build_bundle_summary(self, bundle_dir: Path) -> dict[str, Any]:
        bundle_path = self.storage.relative_path(bundle_dir)
        files = [path for path in sorted(bundle_dir.rglob("*")) if path.is_file()]
        relative_files = [path.relative_to(bundle_dir).as_posix() for path in files]
        return self._build_bundle_summary_from_relative_files(bundle_path, relative_files)

    def _build_bundle_summary_from_relative_files(
        self,
        bundle_path: str,
        relative_files: list[str],
    ) -> dict[str, Any]:
        files = [Path(rel) for rel in relative_files]
        grouped: dict[str, list[str]] = {
            "urp": [],
            "installation": [],
            "variables": [],
            "script": [],
            "text": [],
            "other": [],
        }

        for file_path in files:
            rel = file_path.as_posix()
            suffix = file_path.suffix.lower()
            if suffix == ".urp":
                grouped["urp"].append(rel)
            elif suffix == ".installation":
                grouped["installation"].append(rel)
            elif suffix == ".variables":
                grouped["variables"].append(rel)
            elif suffix == ".script":
                grouped["script"].append(rel)
            elif suffix == ".txt":
                grouped["text"].append(rel)
            else:
                grouped["other"].append(rel)

        warnings: list[str] = []
        primary_urp_rel: str | None = None
        urp_files = grouped["urp"]
        if len(urp_files) == 1:
            primary_urp_rel = urp_files[0]
        elif len(urp_files) == 0:
            warnings.append("No primary .urp file was found in this bundle.")
        else:
            warnings.append("Multiple .urp files were found in this bundle. Primary runtime file is ambiguous.")

        installation_present = bool(grouped["installation"])
        variables_present = bool(grouped["variables"])
        script_present = bool(grouped["script"])
        text_present = bool(grouped["text"])
        primary_urp_filename = Path(primary_urp_rel).name if primary_urp_rel else None
        primary_runtime_safe_filename = (
            normalize_runtime_safe_filename(primary_urp_filename)
            if primary_urp_filename
            else None
        )
        primary_normalization_needed = bool(
            primary_urp_filename
            and primary_runtime_safe_filename
            and primary_runtime_safe_filename != primary_urp_filename
        )
        runtime_name_warning = (
            runtime_name_safety_warning(primary_urp_filename)
            if primary_urp_filename
            else None
        )

        if not installation_present:
            warnings.append("No .installation file is present in this bundle.")
        if not variables_present:
            warnings.append("No .variables file is present in this bundle.")
        if primary_normalization_needed:
            warnings.append(
                "Primary .urp filename is not runtime-safe for dashboard load. "
                "Bundle import commit will normalize it by default."
            )

        if primary_urp_rel is None:
            readiness_state = "invalid"
        elif warnings:
            readiness_state = "warning"
        else:
            readiness_state = "ready"

        primary_urp_path = (
            f"{bundle_path}/{primary_urp_rel}" if primary_urp_rel is not None else None
        )
        return {
            "bundle_name": Path(bundle_path).name,
            "bundle_directory_path": bundle_path,
            "primary_urp_path": primary_urp_path,
            "primary_urp_filename": primary_urp_filename,
            "primary_urp_original_filename": primary_urp_filename,
            "primary_urp_runtime_safe_filename": primary_runtime_safe_filename,
            "primary_urp_normalization_needed": primary_normalization_needed,
            "primary_urp_was_normalized": False,
            "files_by_type": grouped,
            "installation_present": installation_present,
            "variables_present": variables_present,
            "script_present": script_present,
            "text_present": text_present,
            "readiness_state": readiness_state,
            "warnings": warnings,
            "file_count": len(files),
            "runtime_name_warning": runtime_name_warning,
            "normalization_note": None,
        }

    def _derive_bundle_name(self, sources: list[Path]) -> str:
        return self._derive_bundle_name_from_names([source.name for source in sources])

    def _derive_bundle_name_from_names(self, names: list[str]) -> str:
        urp_names = [name for name in names if Path(name).suffix.lower() == ".urp"]
        if len(urp_names) == 1:
            base = Path(urp_names[0]).stem
        else:
            base = Path(names[0]).stem
        return self._sanitize_bundle_name(base or "bundle")

    def _sanitize_bundle_name(self, name: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
        normalized = re.sub(r"_+", "_", normalized)
        normalized = normalized.strip("._-")
        return normalized or "bundle"

    def _build_primary_urp_plan(self, names: list[str]) -> dict[str, Any]:
        urp_names = [Path(name).name for name in names if Path(name).suffix.lower() == ".urp"]
        if len(urp_names) != 1:
            return {
                "original_filename": None,
                "runtime_safe_filename": None,
                "normalization_needed": False,
            }
        original = urp_names[0]
        safe = normalize_runtime_safe_filename(original)
        return {
            "original_filename": original,
            "runtime_safe_filename": safe,
            "normalization_needed": safe != original,
        }

    def _create_unique_bundle_dir(self, target_dir: str, bundle_name: str) -> Path:
        base_dir = self.storage.resolve_path(target_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        candidate = base_dir / bundle_name
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate

        index = 1
        while True:
            candidate = base_dir / f"{bundle_name}_{index}"
            if not candidate.exists():
                candidate.mkdir(parents=True, exist_ok=False)
                return candidate
            index += 1
