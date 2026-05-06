from pathlib import Path
import re

from fastapi.testclient import TestClient

from ur_arms_manager.gui import app, create_app
from ur_arms_manager.models import RobotStatus
from ur_arms_manager.services.compatibility import CompatibilityResult
from ur_arms_manager.services.library_manager import LibraryError
from ur_arms_manager.services.runtime_validation import (
    LoadValidationResult,
    derive_dashboard_load_argument,
    normalize_runtime_safe_filename,
    runtime_name_safety_warning,
)


client = TestClient(app)


class FakeRobotManager:
    statuses: dict[str, RobotStatus] = {}
    action_results: dict[tuple[str, str], str] = {}
    action_errors: dict[tuple[str, str], str] = {}
    calls: list[tuple[str, str]] = []
    remote_dirs: dict[tuple[str, str], list[str]] = {}
    remote_entries: dict[tuple[str, str], list[dict]] = {}
    remote_dir_errors: dict[tuple[str, str], str] = {}
    remote_file_action_errors: dict[tuple[str, str, str], str] = {}
    explicit_load_outcomes: dict[str, str] = {}

    def __init__(self, robot) -> None:
        self.robot = robot

    def status(self) -> RobotStatus:
        return self.statuses[self.robot.name]

    def _run_action(self, action_name: str) -> str:
        key = (self.robot.name, action_name)
        self.calls.append(key)
        if key in self.action_errors:
            raise RuntimeError(self.action_errors[key])
        return self.action_results[key]

    def power_on(self) -> str:
        return self._run_action("power-on")

    def brake_release(self) -> str:
        return self._run_action("brake-release")

    def power_off(self) -> str:
        return self._run_action("power-off")

    def load_assigned_program(self) -> str:
        return self._run_action("load")

    def validate_assigned_runtime_load(
        self, assigned_runtime_path: str | None = None
    ) -> LoadValidationResult:
        key = (self.robot.name, "load")
        self.calls.append(key)
        assigned_path = (
            str(assigned_runtime_path).strip()
            if assigned_runtime_path is not None
            else str(self.robot.assigned_program or "").strip()
        ) or None
        derived = None
        if assigned_path:
            try:
                derived = derive_dashboard_load_argument(assigned_path)
            except Exception:
                derived = assigned_path

        unsafe_warning = runtime_name_safety_warning(derived)
        if unsafe_warning:
            return LoadValidationResult(
                robot_name=self.robot.name,
                assigned_runtime_path=assigned_path,
                derived_dashboard_load_argument=derived,
                raw_dashboard_response=None,
                outcome="unsafe_runtime_path",
                notes=[
                    "Cannot validate dashboard load because the derived load argument contains spaces or unsafe characters. Prepare a runtime-safe bundle first.",
                    unsafe_warning,
                ],
                ready_for_play=False,
            )

        if key in self.action_errors:
            raw = self.action_errors[key]
            normalized = str(raw).lower()
            if "could not understand" in normalized:
                outcome = "parser_error"
            elif "file not found" in normalized:
                outcome = "file_not_found"
            else:
                outcome = self.explicit_load_outcomes.get(self.robot.name, "load_error")
            return LoadValidationResult(
                robot_name=self.robot.name,
                assigned_runtime_path=assigned_path,
                derived_dashboard_load_argument=derived,
                raw_dashboard_response=raw,
                outcome=outcome,
                notes=[],
                ready_for_play=False,
            )

        raw_response = self.action_results.get(key, "Loading program: programs/demo.urp")
        return LoadValidationResult(
            robot_name=self.robot.name,
            assigned_runtime_path=assigned_path,
            derived_dashboard_load_argument=derived,
            raw_dashboard_response=raw_response,
            outcome=self.explicit_load_outcomes.get(self.robot.name, "success"),
            notes=[],
            ready_for_play=self.explicit_load_outcomes.get(self.robot.name, "success") == "success",
        )

    def play_program(self) -> str:
        return self._run_action("play")

    def pause_program(self) -> str:
        return self._run_action("pause")

    def stop_program(self) -> str:
        return self._run_action("stop")

    def reload_loaded_program(self) -> str:
        return self._run_action("reload-loaded")

    def restart_loaded_program(self) -> str:
        return self._run_action("restart-loaded")

    def move_home(self) -> str:
        return self._run_action("move-home")

    def pull_remote_file(self, remote_path: str, local_destination: str) -> Path:
        target = Path(local_destination) / Path(remote_path).name
        target.write_text("remote-payload", encoding="utf-8")
        return target

    def list_remote_files(self, remote_dir: str = "/programs") -> list[str]:
        key = (self.robot.name, remote_dir)
        if key in self.remote_dir_errors:
            raise RuntimeError(self.remote_dir_errors[key])
        return self.remote_dirs.get(key, [])

    def list_remote_entries(self, remote_dir: str = "/programs") -> list[dict]:
        key = (self.robot.name, remote_dir)
        if key in self.remote_dir_errors:
            raise RuntimeError(self.remote_dir_errors[key])
        if key in self.remote_entries:
            return self.remote_entries[key]
        return [
            {
                "name": name,
                "is_dir": False,
                "kind": "file",
            }
            for name in self.remote_dirs.get(key, [])
        ]

    def create_remote_folder(self, remote_dir: str) -> str:
        key = (self.robot.name, "create-folder", remote_dir)
        if key in self.remote_file_action_errors:
            raise RuntimeError(self.remote_file_action_errors[key])
        self.calls.append(("create-folder", remote_dir))
        return remote_dir

    def remove_remote_file(self, remote_path: str) -> str:
        key = (self.robot.name, "remove-file", remote_path)
        if key in self.remote_file_action_errors:
            raise RuntimeError(self.remote_file_action_errors[key])
        self.calls.append(("remove-file", remote_path))
        return remote_path

    def remove_remote_folder(self, remote_dir: str) -> str:
        key = (self.robot.name, "remove-folder", remote_dir)
        if key in self.remote_file_action_errors:
            raise RuntimeError(self.remote_file_action_errors[key])
        self.calls.append(("remove-folder", remote_dir))
        return remote_dir

    def move_remote_path(self, source_path: str, destination_path: str) -> str:
        key = (self.robot.name, "move", source_path)
        if key in self.remote_file_action_errors:
            raise RuntimeError(self.remote_file_action_errors[key])
        self.calls.append(("move", f"{source_path}->{destination_path}"))
        return destination_path

    def copy_remote_file(self, source_path: str, destination_path: str) -> str:
        key = (self.robot.name, "copy", source_path)
        if key in self.remote_file_action_errors:
            raise RuntimeError(self.remote_file_action_errors[key])
        self.calls.append(("copy", f"{source_path}->{destination_path}"))
        return destination_path

    def deploy_local_file(self, local_source: Path, remote_destination: str) -> str:
        key = (self.robot.name, "deploy", remote_destination)
        if key in self.remote_file_action_errors:
            raise RuntimeError(self.remote_file_action_errors[key])
        self.calls.append(("deploy", f"{local_source.name}:{remote_destination}"))
        return remote_destination

    def deploy_local_bundle(
        self, local_source_dir: Path, remote_destination_dir: str
    ) -> dict:
        key = (self.robot.name, "deploy-bundle", remote_destination_dir)
        if key in self.remote_file_action_errors:
            raise RuntimeError(self.remote_file_action_errors[key])
        files = [
            path
            for path in sorted(local_source_dir.rglob("*"))
            if path.is_file()
        ]
        deployed_files = []
        for file_path in files:
            relative = file_path.relative_to(local_source_dir).as_posix()
            remote = f"{remote_destination_dir.rstrip('/')}/{relative}"
            deployed_files.append(
                {
                    "local_path": str(file_path),
                    "relative_path": relative,
                    "remote_path": remote,
                }
            )
        self.calls.append(("deploy-bundle", f"{local_source_dir.name}:{remote_destination_dir}"))
        return {
            "remote_destination_dir": remote_destination_dir,
            "files": deployed_files,
        }

    def run_script_file(self, local_script_path: Path) -> str:
        self.calls.append(("run-script", local_script_path.name))
        return f"Script sent from {local_script_path.name}"


class FakeLibraryManager:
    entries: dict[str, dict] = {}
    list_errors: dict[str, str] = {}
    inspect_errors: dict[str, str] = {}
    remove_errors: dict[str, str] = {}
    add_error: str | None = None
    create_folder_error: str | None = None
    move_errors: dict[tuple[str, str], str] = {}
    copy_errors: dict[tuple[str, str], str] = {}
    stored_file_errors: dict[str, str] = {}
    bundle_errors: dict[str, str] = {}
    safe_copy_errors: dict[str, str] = {}
    removed: list[str] = []

    class _Storage:
        programs_root = Path("storage/library")

        def list_program_ids(self):
            return [
                path
                for path, entry in FakeLibraryManager.entries.items()
                if entry.get("item_kind") == "file"
            ]

    def __init__(self) -> None:
        self.storage = self._Storage()
        self.storage.list_program_ids = lambda: [
            path
            for path, entry in self.entries.items()
            if entry.get("item_kind") == "file"
        ]

    def _default_entry(self, library_path: str, is_dir: bool = False) -> dict:
        path_obj = Path(library_path)
        item_kind = "directory" if is_dir else "file"
        extension = "" if is_dir else path_obj.suffix.lstrip(".")
        return {
            "program_id": library_path,
            "library_path": library_path,
            "relative_path": library_path,
            "name": path_obj.name,
            "original_filename": path_obj.name,
            "extension": extension,
            "item_kind": item_kind,
            "is_dir": is_dir,
            "stored_path": str(self.storage.programs_root / library_path),
            "origin": "robot_remote" if library_path.startswith("robot") else "local",
        }

    def _sanitize_bundle_name(self, name: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or "").strip())
        normalized = re.sub(r"_+", "_", normalized).strip("._-")
        return normalized or "bundle"

    def list_directory(self, relative_dir: str = "") -> list[dict]:
        relative_dir = relative_dir.strip("/")
        if relative_dir in self.list_errors:
            raise LibraryError(self.list_errors[relative_dir])

        children: list[dict] = []
        seen_dirs: set[str] = set()
        prefix = f"{relative_dir}/" if relative_dir else ""
        for path, entry in sorted(self.entries.items()):
            if prefix and not path.startswith(prefix):
                continue
            if not prefix and "/" not in path:
                children.append(dict(entry))
                continue
            if prefix:
                remainder = path[len(prefix):]
            else:
                remainder = path
            if "/" not in remainder:
                children.append(dict(entry))
                continue
            child_name = remainder.split("/", 1)[0]
            child_path = f"{prefix}{child_name}" if prefix else child_name
            if child_path in seen_dirs:
                continue
            seen_dirs.add(child_path)
            children.append(self._default_entry(child_path, is_dir=True))
        return children

    def inspect_item(self, library_path: str) -> dict:
        library_path = library_path.strip("/")
        if library_path in self.inspect_errors:
            raise LibraryError(self.inspect_errors[library_path])
        if library_path in self.entries:
            return dict(self.entries[library_path])

        prefix = f"{library_path}/"
        if any(path.startswith(prefix) for path in self.entries):
            item = self._default_entry(library_path, is_dir=True)
            first_child = next(
                (
                    entry
                    for path, entry in sorted(self.entries.items())
                    if path.startswith(prefix)
                ),
                None,
            )
            if first_child and first_child.get("stored_path"):
                item["stored_path"] = str(Path(first_child["stored_path"]).parent)
            try:
                item["bundle_summary"] = self.inspect_bundle(library_path)
            except LibraryError:
                pass
            return item
        raise LibraryError(f"Library path not found: {library_path}")

    def inspect_item_enriched(self, library_path: str) -> dict:
        return self.inspect_item(library_path)

    def remove_item(self, library_path: str) -> dict:
        library_path = library_path.strip("/")
        if library_path in self.remove_errors:
            raise LibraryError(self.remove_errors[library_path])
        item = self.inspect_item(library_path)
        if item.get("is_dir"):
            prefix = f"{library_path}/"
            for path in list(self.entries):
                if path.startswith(prefix):
                    self.entries.pop(path)
        else:
            self.entries.pop(library_path, None)
        self.removed.append(library_path)
        return item

    def add_item(
        self,
        local_file_path: str,
        extra_metadata: dict | None = None,
        target_dir: str | None = None,
    ) -> dict:
        if self.add_error:
            raise LibraryError(self.add_error)
        source = Path(local_file_path)
        target_dir = "" if target_dir is None else str(target_dir).strip("/")
        if extra_metadata and extra_metadata.get("origin") == "robot_remote":
            source_robot = str(extra_metadata.get("source_robot") or "").strip()
            if source_robot:
                source = source.with_name(f"{source_robot}_{source.name}")
        library_path = f"{target_dir}/{source.name}" if target_dir else source.name
        item = self._default_entry(library_path, is_dir=False)
        if extra_metadata:
            item.update(extra_metadata)
        self.entries[library_path] = item
        return dict(item)

    def add_bundle(
        self,
        local_file_paths: list[str],
        target_dir: str | None = None,
        bundle_name: str | None = None,
    ) -> dict:
        if self.add_error:
            raise LibraryError(self.add_error)
        if not local_file_paths:
            raise LibraryError("No local files were provided for bundle import.")
        names = [Path(path).name for path in local_file_paths]
        urp_names = [name for name in names if name.lower().endswith(".urp")]
        if bundle_name:
            bundle_dir_name = bundle_name
        elif len(urp_names) == 1:
            bundle_dir_name = Path(urp_names[0]).stem
        else:
            bundle_dir_name = Path(names[0]).stem
        bundle_dir_name = self._sanitize_bundle_name(bundle_dir_name)
        target_root = "" if target_dir is None else str(target_dir).strip("/")
        bundle_path = f"{target_root}/{bundle_dir_name}" if target_root else bundle_dir_name
        for local_file_path in local_file_paths:
            filename = Path(local_file_path).name
            if len(urp_names) == 1 and filename == urp_names[0]:
                filename = normalize_runtime_safe_filename(filename)
            item_path = f"{bundle_path}/{filename}"
            self.entries[item_path] = self._default_entry(item_path, is_dir=False)
        summary = self.inspect_bundle(bundle_path)
        if len(urp_names) == 1:
            original = urp_names[0]
            safe = normalize_runtime_safe_filename(original)
            if safe != original:
                summary["primary_urp_was_normalized"] = True
                summary["primary_urp_original_filename"] = original
                summary["primary_urp_runtime_safe_filename"] = safe
                summary["primary_urp_normalization_needed"] = False
                summary["normalization_note"] = (
                    "Primary .urp filename was normalized for runtime-safe dashboard load."
                )
        return summary

    def preview_bundle_import(
        self,
        upload_filenames: list[str],
        target_dir: str | None = None,
        bundle_name: str | None = None,
    ) -> dict:
        if self.add_error:
            raise LibraryError(self.add_error)
        if not upload_filenames:
            raise LibraryError("No local files were provided for bundle import.")
        names = [Path(name).name for name in upload_filenames]
        urp_names = [name for name in names if name.lower().endswith(".urp")]
        if bundle_name:
            bundle_dir_name = bundle_name
        elif len(urp_names) == 1:
            bundle_dir_name = Path(urp_names[0]).stem
        else:
            bundle_dir_name = Path(names[0]).stem
        bundle_dir_name = self._sanitize_bundle_name(bundle_dir_name)
        target_root = "" if target_dir is None else str(target_dir).strip("/")
        bundle_path = f"{target_root}/{bundle_dir_name}" if target_root else bundle_dir_name

        grouped = {
            "urp": [],
            "installation": [],
            "variables": [],
            "script": [],
            "text": [],
            "other": [],
        }
        for name in names:
            suffix = Path(name).suffix.lower()
            if suffix == ".urp":
                grouped["urp"].append(name)
            elif suffix == ".installation":
                grouped["installation"].append(name)
            elif suffix == ".variables":
                grouped["variables"].append(name)
            elif suffix == ".script":
                grouped["script"].append(name)
            elif suffix == ".txt":
                grouped["text"].append(name)
            else:
                grouped["other"].append(name)

        warnings: list[str] = []
        primary_urp_rel = None
        if len(grouped["urp"]) == 1:
            primary_urp_rel = grouped["urp"][0]
        elif len(grouped["urp"]) == 0:
            warnings.append("No primary .urp file was found in this bundle.")
        else:
            warnings.append(
                "Multiple .urp files were found in this bundle. Primary runtime file is ambiguous."
            )
        if not grouped["installation"]:
            warnings.append("No .installation file is present in this bundle.")
        if not grouped["variables"]:
            warnings.append("No .variables file is present in this bundle.")
        primary_urp_filename = Path(primary_urp_rel).name if primary_urp_rel else None
        primary_safe = (
            normalize_runtime_safe_filename(primary_urp_filename)
            if primary_urp_filename
            else None
        )
        normalization_needed = bool(
            primary_urp_filename and primary_safe and primary_safe != primary_urp_filename
        )
        if normalization_needed:
            warnings.append(
                "Primary .urp filename is not runtime-safe for dashboard load. Bundle import commit will normalize it by default."
            )

        if primary_urp_rel is None:
            readiness_state = "invalid"
        elif warnings:
            readiness_state = "warning"
        else:
            readiness_state = "ready"

        return {
            "bundle_name": Path(bundle_path).name,
            "bundle_directory_path": bundle_path,
            "primary_urp_path": (
                f"{bundle_path}/{primary_urp_rel}" if primary_urp_rel else None
            ),
            "primary_urp_filename": primary_urp_filename,
            "primary_urp_original_filename": primary_urp_filename,
            "primary_urp_runtime_safe_filename": primary_safe,
            "primary_urp_normalization_needed": normalization_needed,
            "primary_urp_was_normalized": False,
            "files_by_type": grouped,
            "installation_present": bool(grouped["installation"]),
            "variables_present": bool(grouped["variables"]),
            "script_present": bool(grouped["script"]),
            "text_present": bool(grouped["text"]),
            "readiness_state": readiness_state,
            "warnings": warnings,
            "file_count": len(names),
            "runtime_name_warning": runtime_name_safety_warning(
                f"{bundle_path}/{primary_urp_rel}" if primary_urp_rel else None
            ),
            "normalization_note": None,
        }

    def inspect_bundle(self, library_path: str) -> dict:
        library_path = library_path.strip("/")
        if library_path in self.bundle_errors:
            raise LibraryError(self.bundle_errors[library_path])
        prefix = f"{library_path}/"
        files = [
            path for path, entry in sorted(self.entries.items())
            if path.startswith(prefix) and not entry.get("is_dir")
        ]
        if not files:
            raise LibraryError(f"Library bundle not found: {library_path}")

        grouped = {
            "urp": [],
            "installation": [],
            "variables": [],
            "script": [],
            "text": [],
            "other": [],
        }
        for path in files:
            rel = path[len(prefix):]
            suffix = Path(path).suffix.lower()
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
        primary_urp_rel = None
        if len(grouped["urp"]) == 1:
            primary_urp_rel = grouped["urp"][0]
        elif len(grouped["urp"]) == 0:
            warnings.append("No primary .urp file was found in this bundle.")
        else:
            warnings.append(
                "Multiple .urp files were found in this bundle. Primary runtime file is ambiguous."
            )
        if not grouped["installation"]:
            warnings.append("No .installation file is present in this bundle.")
        if not grouped["variables"]:
            warnings.append("No .variables file is present in this bundle.")
        primary_urp_filename = Path(primary_urp_rel).name if primary_urp_rel else None
        primary_safe = (
            normalize_runtime_safe_filename(primary_urp_filename)
            if primary_urp_filename
            else None
        )
        normalization_needed = bool(
            primary_urp_filename and primary_safe and primary_safe != primary_urp_filename
        )
        if normalization_needed:
            warnings.append(
                "Primary .urp filename is not runtime-safe for dashboard load. Bundle import commit will normalize it by default."
            )

        if primary_urp_rel is None:
            readiness_state = "invalid"
        elif warnings:
            readiness_state = "warning"
        else:
            readiness_state = "ready"

        return {
            "bundle_name": Path(library_path).name,
            "bundle_directory_path": library_path,
            "primary_urp_path": (
                f"{library_path}/{primary_urp_rel}" if primary_urp_rel else None
            ),
            "primary_urp_filename": primary_urp_filename,
            "primary_urp_original_filename": primary_urp_filename,
            "primary_urp_runtime_safe_filename": primary_safe,
            "primary_urp_normalization_needed": normalization_needed,
            "primary_urp_was_normalized": False,
            "files_by_type": grouped,
            "installation_present": bool(grouped["installation"]),
            "variables_present": bool(grouped["variables"]),
            "script_present": bool(grouped["script"]),
            "text_present": bool(grouped["text"]),
            "readiness_state": readiness_state,
            "warnings": warnings,
            "file_count": len(files),
            "runtime_name_warning": runtime_name_safety_warning(
                f"{library_path}/{primary_urp_rel}" if primary_urp_rel else None
            ),
            "normalization_note": None,
        }

    def prepare_runtime_safe_bundle_copy(self, path_ref: str) -> dict:
        path_ref = path_ref.strip("/")
        if path_ref in self.safe_copy_errors:
            raise LibraryError(self.safe_copy_errors[path_ref])
        summary = self.inspect_bundle(path_ref)
        primary_path = str(summary.get("primary_urp_path") or "").strip()
        if not primary_path:
            raise LibraryError(
                "Runtime-safe copy requires one deterministic primary .urp. Current bundle is missing or has ambiguous primary .urp."
            )
        source_prefix = f"{path_ref}/"
        safe_bundle_name = f"{self._sanitize_bundle_name(Path(path_ref).name)}_safe"
        safe_bundle_path = f"{Path(path_ref).parent.as_posix().strip('./')}/{safe_bundle_name}".strip("/")
        if not safe_bundle_path:
            safe_bundle_path = safe_bundle_name

        original_primary_name = summary.get("primary_urp_filename")
        runtime_safe_primary_name = normalize_runtime_safe_filename(original_primary_name or "main.urp")
        primary_rel = Path(primary_path).relative_to(Path(path_ref)).as_posix()

        for source_item_path, entry in list(self.entries.items()):
            if not source_item_path.startswith(source_prefix):
                continue
            rel = source_item_path[len(source_prefix):]
            rel_path = Path(rel)
            target_name = rel_path.name
            if rel == primary_rel:
                target_name = runtime_safe_primary_name
            target_rel = (Path(safe_bundle_path) / rel_path.parent / target_name).as_posix()
            cloned = dict(entry)
            cloned["program_id"] = target_rel
            cloned["library_path"] = target_rel
            cloned["relative_path"] = target_rel
            cloned["name"] = target_name
            cloned["original_filename"] = target_name
            cloned["stored_path"] = str(self.storage.programs_root / target_rel)
            if not cloned.get("is_dir"):
                cloned["extension"] = Path(target_name).suffix.lstrip(".")
            self.entries[target_rel] = cloned

        safe_summary = self.inspect_bundle(safe_bundle_path)
        safe_summary["source_bundle_path"] = path_ref
        safe_summary["primary_urp_was_normalized"] = (
            (original_primary_name or "") != runtime_safe_primary_name
        )
        safe_summary["primary_urp_original_filename"] = original_primary_name
        safe_summary["primary_urp_runtime_safe_filename"] = runtime_safe_primary_name
        safe_summary["normalization_note"] = "Created runtime-safe non-destructive bundle copy."
        return safe_summary

    def create_folder(self, relative_dir: str) -> dict:
        if self.create_folder_error:
            raise LibraryError(self.create_folder_error)
        relative_dir = relative_dir.strip("/")
        item = self._default_entry(relative_dir, is_dir=True)
        return item

    def get_stored_file(self, library_path: str) -> Path:
        library_path = library_path.strip("/")
        if library_path in self.stored_file_errors:
            raise LibraryError(self.stored_file_errors[library_path])
        item = self.inspect_item(library_path)
        if item.get("is_dir"):
            raise LibraryError(f"Library path is a folder, not a file: {library_path}")
        return Path(item["stored_path"])

    def move_item(self, source_rel: str, destination_rel: str) -> dict:
        key = (source_rel, destination_rel)
        if key in self.move_errors:
            raise LibraryError(self.move_errors[key])
        item = self.inspect_item(source_rel)
        moved = dict(item)
        moved["program_id"] = destination_rel
        moved["library_path"] = destination_rel
        moved["relative_path"] = destination_rel
        moved["name"] = Path(destination_rel).name
        moved["original_filename"] = Path(destination_rel).name
        moved["stored_path"] = str(self.storage.programs_root / destination_rel)
        if not moved.get("is_dir"):
            moved["extension"] = Path(destination_rel).suffix.lstrip(".")
        if item.get("is_dir"):
            prefix = f"{source_rel}/"
            for path in list(self.entries):
                if path.startswith(prefix):
                    child = self.entries.pop(path)
                    new_child_path = path.replace(prefix, f"{destination_rel}/", 1)
                    child["program_id"] = new_child_path
                    child["library_path"] = new_child_path
                    child["relative_path"] = new_child_path
                    child["stored_path"] = str(self.storage.programs_root / new_child_path)
                    self.entries[new_child_path] = child
        else:
            self.entries.pop(source_rel, None)
            self.entries[destination_rel] = moved
        return moved

    def copy_item(self, source_rel: str, destination_rel: str) -> dict:
        key = (source_rel, destination_rel)
        if key in self.copy_errors:
            raise LibraryError(self.copy_errors[key])
        item = self.inspect_item(source_rel)
        copied = dict(item)
        copied["program_id"] = destination_rel
        copied["library_path"] = destination_rel
        copied["relative_path"] = destination_rel
        copied["name"] = Path(destination_rel).name
        copied["original_filename"] = Path(destination_rel).name
        copied["stored_path"] = str(self.storage.programs_root / destination_rel)
        if not copied.get("is_dir"):
            copied["extension"] = Path(destination_rel).suffix.lstrip(".")
            self.entries[destination_rel] = copied
        return copied


class FakeCompatibilityService:
    results: dict[tuple[str, str], CompatibilityResult] = {}
    errors: dict[tuple[str, str], str] = {}

    def __init__(self, library_manager, robot_manager_factory) -> None:
        self.library_manager = library_manager
        self.robot_manager_factory = robot_manager_factory

    def evaluate(self, robot, program_id: str) -> CompatibilityResult:
        key = (robot.name, program_id)
        if key in self.errors:
            raise RuntimeError(self.errors[key])
        return self.results[key]


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_homepage_renders_foundation_placeholders() -> None:
    response = client.get("/", follow_redirects=True)

    assert response.status_code == 200
    assert "UR Arms Manager" in response.text
    assert "Phase 1 GUI Foundation" in response.text
    assert "Fleet Overview" in response.text
    assert "Jump to workspace" in response.text or "No robots are configured." in response.text


def test_transfer_page_renders_bundle_first_sources() -> None:
    FakeLibraryManager.entries = {
        "uploaded/demo_bundle/main.urp": _make_library_file("uploaded/demo_bundle/main.urp"),
        "uploaded/demo_bundle/main.installation": _make_library_file(
            "uploaded/demo_bundle/main.installation", extension="installation"
        ),
        "uploaded/demo.script": _make_library_file("uploaded/demo.script"),
    }
    FakeLibraryManager.bundle_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.get("/transfer")

    assert response.status_code == 200
    assert "Guided bundle-first transfer." in response.text
    assert "[Bundle] uploaded/demo_bundle" in response.text
    assert "[File] uploaded/demo.script" in response.text


def test_transfer_page_renders_remote_robot_storage_browser_for_selected_robot(tmp_path: Path) -> None:
    FakeLibraryManager.entries = {
        "uploaded/demo_bundle/main.urp": _make_library_file("uploaded/demo_bundle/main.urp"),
    }
    FakeLibraryManager.bundle_errors = {}
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    FakeRobotManager.remote_entries = {
        ("robot1", "/ursim/programs.UR5"): [
            {"name": "programs", "is_dir": True, "kind": "directory"},
            {"name": "manual.txt", "is_dir": False, "kind": "file"},
        ]
    }
    gui_client = TestClient(
        create_app(
            config_path=config_path,
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.get("/transfer?source_path=uploaded/demo_bundle&robot_name=robot1")

    assert response.status_code == 200
    assert "Remote Robot Storage Browser" in response.text
    assert "/ursim/programs.UR5" in response.text
    assert "Use as Destination Parent" in response.text


def test_transfer_page_shows_predicted_assign_target_for_selected_bundle() -> None:
    FakeLibraryManager.entries = {
        "uploaded/demo_bundle/main.urp": _make_library_file("uploaded/demo_bundle/main.urp"),
        "uploaded/demo_bundle/main.installation": _make_library_file(
            "uploaded/demo_bundle/main.installation", extension="installation"
        ),
        "uploaded/demo_bundle/main.variables": _make_library_file(
            "uploaded/demo_bundle/main.variables", extension="variables"
        ),
    }
    FakeLibraryManager.bundle_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.get(
        "/transfer?source_path=uploaded/demo_bundle&robot_name=robot1&remote_dir=/programs/jobs"
    )

    assert response.status_code == 200
    assert "Predicted assign target after deploy" in response.text
    assert "/programs/jobs/demo_bundle/main.urp" in response.text


def test_transfer_page_shows_runtime_filename_warning_for_space_in_primary_urp(
    tmp_path: Path,
) -> None:
    FakeLibraryManager.entries = {
        "uploaded/demo_bundle/main file.urp": _make_library_file("uploaded/demo_bundle/main file.urp"),
        "uploaded/demo_bundle/main.installation": _make_library_file(
            "uploaded/demo_bundle/main.installation", extension="installation"
        ),
        "uploaded/demo_bundle/main.variables": _make_library_file(
            "uploaded/demo_bundle/main.variables", extension="variables"
        ),
    }
    FakeLibraryManager.bundle_errors = {}
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    FakeRobotManager.remote_entries = {("robot1", "/ursim/programs.UR5"): []}
    FakeRobotManager.remote_dir_errors = {}
    gui_client = TestClient(
        create_app(
            config_path=config_path,
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.get("/transfer?source_path=uploaded/demo_bundle&robot_name=robot1")

    assert response.status_code == 200
    assert "Runtime warning: filename contains spaces or unsafe characters." in response.text


def test_transfer_page_marks_ordinary_folder_as_non_deployable() -> None:
    FakeLibraryManager.entries = {
        "robot1/readme.txt": _make_library_file("robot1/readme.txt", extension="txt"),
    }
    FakeLibraryManager.bundle_errors = {}
    FakeLibraryManager.safe_copy_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.get("/transfer?source_path=robot1")

    assert response.status_code == 200
    assert "[Folder] robot1" in response.text
    assert "Deploy is blocked for selected source." in response.text


def test_transfer_page_shows_nested_bundle_destination_warning(tmp_path: Path) -> None:
    FakeLibraryManager.entries = {
        "uploaded/demo_bundle/main.urp": _make_library_file("uploaded/demo_bundle/main.urp"),
        "uploaded/demo_bundle/main.installation": _make_library_file(
            "uploaded/demo_bundle/main.installation", extension="installation"
        ),
        "uploaded/demo_bundle/main.variables": _make_library_file(
            "uploaded/demo_bundle/main.variables", extension="variables"
        ),
    }
    FakeLibraryManager.bundle_errors = {}
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    FakeRobotManager.remote_entries = {
        ("robot1", "/ursim/programs.UR5/demo_bundle"): [],
    }
    gui_client = TestClient(
        create_app(
            config_path=config_path,
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.get(
        "/transfer?source_path=uploaded/demo_bundle&robot_name=robot1&remote_dir=/ursim/programs.UR5/demo_bundle"
    )

    assert response.status_code == 200
    assert "nested path" in response.text.lower()
    assert "/ursim/programs.UR5/demo_bundle/demo_bundle" in response.text


def test_robots_page_renders_configured_robots(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: /programs/demo_a.urp
  robot2:
    host: 192.168.0.20
    dashboard_port: 29992
    script_port: 30022
    enabled: false
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {
        "robot1": RobotStatus(
            name="robot1",
            connected=True,
            robotmode="RUNNING",
            program_running="PLAYING",
            safety_status="NORMAL",
            assigned_program="/programs/demo_a.urp",
        ),
        "robot2": RobotStatus(
            name="robot2",
            connected=False,
            assigned_program=None,
            detail="connection refused",
        ),
    }
    phase_2_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = phase_2_client.get("/robots")

    assert response.status_code == 200
    assert "robot1" in response.text
    assert "127.0.0.1" in response.text
    assert "29991" in response.text
    assert "30021" in response.text
    assert "Enabled" in response.text
    assert "/programs/demo_a.urp" in response.text
    assert "robot2" in response.text
    assert "Disabled" in response.text
    assert "None assigned" in response.text
    assert "RUNNING" in response.text
    assert "PLAYING" in response.text
    assert "NORMAL" in response.text
    assert "Disconnected" in response.text
    assert "connection refused" in response.text


def test_robots_page_renders_empty_state(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text("robots: {}\n", encoding="utf-8")
    phase_2_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = phase_2_client.get("/robots")

    assert response.status_code == 200
    assert "No robots are configured." in response.text


def test_robots_page_renders_config_error(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.yaml"
    phase_2_client = TestClient(
        create_app(config_path=missing_path, robot_manager_factory=FakeRobotManager)
    )

    response = phase_2_client.get("/robots")

    assert response.status_code == 200
    assert "Robot configuration could not be loaded." in response.text
    assert "Konfigurační soubor neexistuje" in response.text


def test_robot_status_endpoint_returns_status_payload(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: /programs/demo_a.urp
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {
        "robot1": RobotStatus(
            name="robot1",
            connected=True,
            robotmode="IDLE",
            program_running="STOPPED",
            safety_status="NORMAL",
            assigned_program="/programs/demo_a.urp",
        )
    }
    phase_3_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = phase_3_client.get("/api/robots/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["robots"][0]["name"] == "robot1"
    assert payload["robots"][0]["status"]["connected"] is True
    assert payload["robots"][0]["status"]["robotmode"] == "IDLE"
    assert payload["robots"][0]["status"]["program_state"] == "STOPPED"


def test_robot_workspace_status_endpoint_returns_single_robot_payload(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: /programs/demo_a.urp
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {
        "robot1": RobotStatus(
            name="robot1",
            connected=True,
            robotmode="RUNNING",
            program_running="PLAYING",
            safety_status="NORMAL",
            assigned_program="/programs/demo_a.urp",
        )
    }
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.get("/api/robots/robot1/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["robot"]["name"] == "robot1"
    assert payload["robot"]["status"]["connected"] is True
    assert payload["robot"]["assigned_program"] == "/programs/demo_a.urp"
    assert payload["robot"]["assignment_kind_label"] == "Remote Runtime Path"
    assert payload["robot"]["runtime_validation"]["derived_load_argument"] == "programs/demo_a.urp"


def test_robot_status_endpoint_returns_config_error_payload(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.yaml"
    phase_3_client = TestClient(
        create_app(config_path=missing_path, robot_manager_factory=FakeRobotManager)
    )

    response = phase_3_client.get("/api/robots/status")

    assert response.status_code == 503
    payload = response.json()
    assert payload["ok"] is False
    assert "Konfigurační soubor neexistuje" in payload["error_message"]


def test_system_page_renders_diagnostics_summary(tmp_path: Path) -> None:
    FakeLibraryManager.entries = {
        "uploaded/demo.script": _make_library_file("uploaded/demo.script"),
        "uploaded/stale.urp": _make_library_file("uploaded/stale.urp"),
    }
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: /programs/demo_a.urp
  robot2:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30022
    enabled: false
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    gui_client = TestClient(
        create_app(
            config_path=config_path,
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.get("/system")

    assert response.status_code == 200
    assert "System and configuration sanity." in response.text
    assert "Configuration loaded" in response.text
    assert str(config_path) in response.text
    assert "robot1" in response.text
    assert "robot2" in response.text
    assert "2222" in response.text
    assert "Disabled" in response.text
    assert "Duplicate dashboard endpoint 127.0.0.1:29991 is shared by: robot1, robot2" in response.text
    assert "Robot is disabled in config." in response.text
    assert "Library Items" in response.text
    assert ">2<" in response.text


def test_system_page_renders_config_error_state(tmp_path: Path) -> None:
    FakeLibraryManager.entries = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    missing_path = tmp_path / "missing.yaml"
    gui_client = TestClient(
        create_app(
            config_path=missing_path,
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.get("/system")

    assert response.status_code == 200
    assert "Configuration problem detected" in response.text
    assert "Konfigurační soubor neexistuje" in response.text


def test_robots_page_renders_action_controls(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: /programs/demo_a.urp
  robot2:
    host: 192.168.0.20
    dashboard_port: 29992
    script_port: 30022
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {
        "robot1": RobotStatus(name="robot1", connected=True),
        "robot2": RobotStatus(name="robot2", connected=True),
    }
    phase_a_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = phase_a_client.get("/robots")

    assert response.status_code == 200
    assert "Power On" in response.text
    assert "Brake Release" in response.text
    assert "Power Off" in response.text
    assert "Load" in response.text
    assert "Play" in response.text
    assert "Stop" in response.text
    assert "Actions" in response.text
    assert "disabled" in response.text
    assert "Assigned Runtime Path" in response.text
    assert "Remote Runtime Path" in response.text


def test_robot_workspace_page_renders_robot_specific_view(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: /programs/demo_a.urp
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {
        "robot1": RobotStatus(
            name="robot1",
            connected=True,
            robotmode="RUNNING",
            program_running="PLAYING",
            safety_status="NORMAL",
            assigned_program="/programs/demo_a.urp",
            monitoring_source="rtde",
        )
    }
    FakeRobotManager.remote_entries = {
        ("robot1", "/programs"): [
            {"name": "jobs", "is_dir": True, "kind": "directory"},
            {"name": "demo.urp", "is_dir": False, "kind": "file"},
        ],
        ("robot1", "/programs/jobs"): [
            {"name": "nested.script", "is_dir": False, "kind": "file"},
        ],
    }
    FakeRobotManager.remote_dir_errors = {}
    FakeRobotManager.remote_file_action_errors = {}
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.get("/robots/robot1?remote_dir=/programs&selected_remote_path=/programs/demo.urp")

    assert response.status_code == 200
    assert "Robot workspace for robot1." in response.text
    assert "127.0.0.1" in response.text
    assert "29991" in response.text
    assert "30021" in response.text
    assert "2222" in response.text
    assert "/programs/demo_a.urp" in response.text
    assert "RUNNING" in response.text
    assert "PLAYING" in response.text
    assert "NORMAL" in response.text
    assert "rtde" in response.text
    assert "Power On" in response.text
    assert "Back to robot overview" in response.text
    assert "Remote file manager" in response.text
    assert "/programs" in response.text
    assert "demo.urp" in response.text
    assert "jobs" in response.text
    assert "Create Remote Folder" in response.text
    assert "Assigned Runtime Path" in response.text
    assert "Load Context" in response.text
    assert "Derived Dashboard Load Argument" in response.text
    assert "programs/demo_a.urp" in response.text
    assert "Assign Selected File for Load" in response.text


def test_robot_workspace_defaults_to_current_remote_root_profile(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    FakeRobotManager.remote_entries = {
        ("robot1", "/ursim/programs.UR5"): [
            {"name": "programs", "is_dir": True, "kind": "directory"},
        ]
    }
    FakeRobotManager.remote_dir_errors = {}
    FakeRobotManager.remote_file_action_errors = {}
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.get("/robots/robot1")

    assert response.status_code == 200
    assert "/ursim/programs.UR5" in response.text
    assert "Current URSim remote root profile" in response.text
    assert "programs" in response.text


def test_robot_workspace_page_renders_unknown_robot_error(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text("robots: {}\n", encoding="utf-8")
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.get("/robots/robot9")

    assert response.status_code == 200
    assert "Robot workspace could not be loaded." in response.text


def test_robot_workspace_page_tolerates_robot_file_listing_error(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {
        "robot1": RobotStatus(name="robot1", connected=True),
    }
    FakeRobotManager.remote_entries = {}
    FakeRobotManager.remote_dir_errors = {
        ("robot1", "/ursim/programs.UR5"): "permission denied",
    }
    FakeRobotManager.remote_file_action_errors = {}
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.get("/robots/robot1")

    assert response.status_code == 200
    assert "File Browser Error" in response.text
    assert "permission denied" in response.text
    assert "Power On" in response.text


def test_robot_workspace_import_remote_file_redirects_to_library(tmp_path: Path) -> None:
    FakeLibraryManager.entries = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    FakeLibraryManager.stored_file_errors = {}
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {
        "robot1": RobotStatus(name="robot1", connected=True),
    }
    FakeRobotManager.remote_entries = {
        ("robot1", "/programs"): [
            {"name": "demo.urp", "is_dir": False, "kind": "file"},
        ],
    }
    FakeRobotManager.remote_dir_errors = {}
    FakeRobotManager.remote_file_action_errors = {}
    gui_client = TestClient(
        create_app(
            config_path=config_path,
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/robots/robot1/import-remote",
        data={"remote_dir": "/programs", "remote_path": "/programs/demo.urp"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Imported from robot &#39;robot1&#39;: /programs/demo.urp -&gt; robot1_demo.urp" in response.text
    assert "robot1_demo.urp" in response.text


def test_robot_workspace_page_renders_empty_directory_state(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    FakeRobotManager.remote_entries = {("robot1", "/ursim/programs.UR5"): []}
    FakeRobotManager.remote_dir_errors = {}
    FakeRobotManager.remote_file_action_errors = {}
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.get("/robots/robot1")

    assert response.status_code == 200
    assert "/ursim/programs.UR5" in response.text
    assert "This remote directory is empty." in response.text


def test_robot_workspace_page_supports_folder_selection(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    FakeRobotManager.remote_entries = {
        ("robot1", "/programs"): [
            {"name": "jobs", "is_dir": True, "kind": "directory"},
        ]
    }
    FakeRobotManager.remote_dir_errors = {}
    FakeRobotManager.remote_file_action_errors = {}
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.get("/robots/robot1?remote_dir=/programs&selected_remote_path=/programs/jobs")

    assert response.status_code == 200
    assert "Selected Remote Path" in response.text
    assert "/programs/jobs" in response.text
    assert "Import to Library is only available for files." in response.text


def test_robot_workspace_assign_remote_file_redirects_with_success_feedback(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    FakeRobotManager.remote_entries = {
        ("robot1", "/programs"): [
            {"name": "demo.urp", "is_dir": False, "kind": "file"},
        ]
    }
    FakeRobotManager.remote_dir_errors = {}
    FakeRobotManager.remote_file_action_errors = {}
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.post(
        "/robots/robot1/assign-remote-file",
        data={
            "remote_dir": "/programs",
            "remote_path": "/programs/demo.urp",
            "item_kind": "file",
            "item_extension": "urp",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Assigned runtime path for robot &#39;robot1&#39;: /programs/demo.urp" in response.text
    assert "Remote Runtime Path" in response.text


def test_robot_workspace_assign_remote_file_rejects_directory(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.post(
        "/robots/robot1/assign-remote-file",
        data={
            "remote_dir": "/programs",
            "remote_path": "/programs/jobs",
            "item_kind": "directory",
            "item_extension": "",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Assign remote path failed: folders cannot be used for Load." in response.text


def test_robot_workspace_assign_remote_file_rejects_script_file(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.post(
        "/robots/robot1/assign-remote-file",
        data={
            "remote_dir": "/programs",
            "remote_path": "/programs/demo.script",
            "item_kind": "file",
            "item_extension": "script",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert ".script files use direct Run Script" in response.text


def test_robot_workspace_run_remote_script_redirects_with_success_feedback(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: /programs/demo.urp
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    FakeRobotManager.remote_entries = {
        ("robot1", "/programs"): [
            {"name": "demo.script", "is_dir": False, "kind": "file"},
        ]
    }
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.post(
        "/robots/robot1/run-remote-script",
        data={"remote_dir": "/programs", "remote_path": "/programs/demo.script"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Direct script run succeeded" in response.text
    assert "Last script run" in response.text


def test_robot_workspace_create_folder_redirects_with_success_feedback(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    FakeRobotManager.remote_entries = {("robot1", "/programs"): []}
    FakeRobotManager.remote_dir_errors = {}
    FakeRobotManager.remote_file_action_errors = {}
    FakeRobotManager.calls = []
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.post(
        "/robots/robot1/files/create-folder",
        data={"remote_dir": "/programs", "folder_name": "jobs"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Created remote folder: /programs/jobs" in response.text
    assert ("create-folder", "/programs/jobs") in FakeRobotManager.calls


def test_robot_workspace_create_folder_works_from_ursim_profile_root(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    FakeRobotManager.remote_entries = {("robot1", "/ursim/programs.UR5"): []}
    FakeRobotManager.remote_dir_errors = {}
    FakeRobotManager.remote_file_action_errors = {}
    FakeRobotManager.calls = []
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.post(
        "/robots/robot1/files/create-folder",
        data={"remote_dir": "/ursim/programs.UR5", "folder_name": "jobs"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Created remote folder: /ursim/programs.UR5/jobs" in response.text
    assert ("create-folder", "/ursim/programs.UR5/jobs") in FakeRobotManager.calls


def test_robot_workspace_create_folder_rejects_path_traversal_name(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    FakeRobotManager.remote_entries = {("robot1", "/ursim/programs.UR5"): []}
    FakeRobotManager.remote_dir_errors = {}
    FakeRobotManager.remote_file_action_errors = {}
    FakeRobotManager.calls = []
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.post(
        "/robots/robot1/files/create-folder",
        data={"remote_dir": "/ursim/programs.UR5", "folder_name": "../escape"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Create folder failed: folder name must be one safe directory name." in response.text
    assert ("create-folder", "/ursim/programs.UR5/../escape") not in FakeRobotManager.calls


def test_robot_workspace_create_folder_redirects_with_error_feedback(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    FakeRobotManager.remote_entries = {("robot1", "/programs"): []}
    FakeRobotManager.remote_dir_errors = {}
    FakeRobotManager.remote_file_action_errors = {
        ("robot1", "create-folder", "/programs/jobs"): "permission denied"
    }
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.post(
        "/robots/robot1/files/create-folder",
        data={"remote_dir": "/programs", "folder_name": "jobs"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Create folder failed: permission denied" in response.text


def test_robot_workspace_remove_redirects_with_success_feedback(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    FakeRobotManager.remote_entries = {
        ("robot1", "/programs"): [
            {"name": "demo.urp", "is_dir": False, "kind": "file"},
        ]
    }
    FakeRobotManager.remote_dir_errors = {}
    FakeRobotManager.remote_file_action_errors = {}
    FakeRobotManager.calls = []
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.post(
        "/robots/robot1/files/remove",
        data={
            "remote_dir": "/programs",
            "remote_path": "/programs/demo.urp",
            "item_kind": "file",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Removed remote path: /programs/demo.urp" in response.text
    assert ("remove-file", "/programs/demo.urp") in FakeRobotManager.calls


def test_robot_workspace_move_redirects_with_success_feedback(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    FakeRobotManager.remote_entries = {
        ("robot1", "/programs"): [
            {"name": "demo.urp", "is_dir": False, "kind": "file"},
        ]
    }
    FakeRobotManager.remote_dir_errors = {}
    FakeRobotManager.remote_file_action_errors = {}
    FakeRobotManager.calls = []
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.post(
        "/robots/robot1/files/move",
        data={
            "remote_dir": "/programs",
            "source_path": "/programs/demo.urp",
            "destination_path": "/programs/archive/demo.urp",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Moved remote path to: /programs/archive/demo.urp" in response.text
    assert ("move", "/programs/demo.urp->/programs/archive/demo.urp") in FakeRobotManager.calls


def test_robot_workspace_move_redirects_with_error_feedback(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    FakeRobotManager.remote_entries = {
        ("robot1", "/programs"): [
            {"name": "demo.urp", "is_dir": False, "kind": "file"},
        ]
    }
    FakeRobotManager.remote_dir_errors = {}
    FakeRobotManager.remote_file_action_errors = {
        ("robot1", "move", "/programs/demo.urp"): "rename blocked"
    }
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.post(
        "/robots/robot1/files/move",
        data={
            "remote_dir": "/programs",
            "source_path": "/programs/demo.urp",
            "destination_path": "/programs/archive/demo.urp",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Move failed: rename blocked" in response.text


def test_robot_workspace_copy_redirects_with_success_feedback(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    FakeRobotManager.remote_entries = {
        ("robot1", "/programs"): [
            {"name": "demo.script", "is_dir": False, "kind": "file"},
        ]
    }
    FakeRobotManager.remote_dir_errors = {}
    FakeRobotManager.remote_file_action_errors = {}
    FakeRobotManager.calls = []
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.post(
        "/robots/robot1/files/copy",
        data={
            "remote_dir": "/programs",
            "source_path": "/programs/demo.script",
            "destination_path": "/programs/demo_copy.script",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Copied remote file to: /programs/demo_copy.script" in response.text
    assert ("copy", "/programs/demo.script->/programs/demo_copy.script") in FakeRobotManager.calls


def test_robot_workspace_copy_redirects_with_error_feedback(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    FakeRobotManager.remote_entries = {
        ("robot1", "/programs"): [
            {"name": "demo.script", "is_dir": False, "kind": "file"},
        ]
    }
    FakeRobotManager.remote_dir_errors = {}
    FakeRobotManager.remote_file_action_errors = {
        ("robot1", "copy", "/programs/demo.script"): "copy blocked"
    }
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.post(
        "/robots/robot1/files/copy",
        data={
            "remote_dir": "/programs",
            "source_path": "/programs/demo.script",
            "destination_path": "/programs/demo_copy.script",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Copy failed: copy blocked" in response.text


def test_robots_page_shows_disabled_robot_action_reason(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: false
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {
        "robot1": RobotStatus(name="robot1", connected=False, detail="disabled in test"),
    }
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.get("/robots")

    assert response.status_code == 200
    assert "Robot is disabled in config. Enable it before sending commands." in response.text


def test_robot_action_endpoint_returns_success_payload(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: /programs/demo_a.urp
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.calls = []
    FakeRobotManager.action_errors = {}
    FakeRobotManager.action_results = {
        ("robot1", "play"): "Starting program",
    }
    FakeRobotManager.statuses = {
        "robot1": RobotStatus(name="robot1", connected=True),
    }
    phase_a_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = phase_a_client.post("/api/robots/robot1/actions/play")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["action_name"] == "play"
    assert payload["action_label"] == "Play"
    assert payload["message"] == "Starting program"
    assert FakeRobotManager.calls == [("robot1", "play")]


def test_robot_action_endpoint_returns_error_payload(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: /programs/demo_a.urp
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.calls = []
    FakeRobotManager.action_results = {}
    FakeRobotManager.action_errors = {
        ("robot1", "load"): "Load selhal pro robot 'robot1': file not found",
    }
    FakeRobotManager.statuses = {
        "robot1": RobotStatus(name="robot1", connected=True),
    }
    phase_a_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = phase_a_client.post("/api/robots/robot1/actions/load")

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["action_name"] == "load"
    assert payload["action_label"] == "Load"
    assert "file not found" in payload["message"]


def test_robot_action_play_is_blocked_after_failed_load_validation(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: /programs/demo_a.urp
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.calls = []
    FakeRobotManager.action_results = {
        ("robot1", "play"): "Starting program",
    }
    FakeRobotManager.action_errors = {
        ("robot1", "load"): "could not understand: 'load programs/demo_a.urp'",
    }
    FakeRobotManager.statuses = {
        "robot1": RobotStatus(name="robot1", connected=True),
    }
    phase_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    load_response = phase_client.post("/api/robots/robot1/actions/load")
    assert load_response.status_code == 400

    play_response = phase_client.post("/api/robots/robot1/actions/play")
    assert play_response.status_code == 400
    payload = play_response.json()
    assert payload["ok"] is False
    assert "Play blocked" in payload["message"]
    assert "parser_error" in payload["message"]


def test_robot_action_load_is_blocked_for_unsafe_runtime_argument(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: /ursim/programs.UR5/jobs/my program.urp
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.calls = []
    FakeRobotManager.action_results = {}
    FakeRobotManager.action_errors = {}
    FakeRobotManager.statuses = {
        "robot1": RobotStatus(name="robot1", connected=True),
    }
    phase_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = phase_client.post("/api/robots/robot1/actions/load")

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["runtime_validation"]["outcome"] == "unsafe_runtime_path"
    assert "runtime-safe bundle first" in payload["message"]


def test_robot_action_endpoint_returns_not_found_for_unknown_robot(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text("robots: {}\n", encoding="utf-8")
    phase_a_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = phase_a_client.post("/api/robots/robot1/actions/play")

    assert response.status_code == 404


def _make_library_file(path: str, extension: str | None = None) -> dict:
    path_obj = Path(path)
    ext = extension if extension is not None else path_obj.suffix.lstrip(".")
    return {
        "program_id": path,
        "library_path": path,
        "relative_path": path,
        "name": path_obj.name,
        "original_filename": path_obj.name,
        "extension": ext,
        "item_kind": "file",
        "is_dir": False,
        "stored_path": f"storage/library/{path}",
        "origin": "robot_remote" if path.startswith("robot") else "local",
    }


def test_library_page_renders_filesystem_browser_and_selected_file() -> None:
    FakeLibraryManager.entries = {
        "uploaded/demo.script": _make_library_file("uploaded/demo.script"),
        "robot1/robot1_test1.urp": _make_library_file("robot1/robot1_test1.urp"),
    }
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    FakeLibraryManager.stored_file_errors = {}
    FakeLibraryManager.removed = []
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.get("/library?dir=uploaded&selected=uploaded/demo.script")

    assert response.status_code == 200
    assert "Local library workspace." in response.text
    assert "uploaded/demo.script" in response.text
    assert "Upload Here" in response.text
    assert "Create Folder" in response.text
    assert "Move Selected Path" in response.text
    assert "Copy Selected Path" in response.text
    assert "Send to Robot Storage" in response.text


def test_library_page_renders_empty_folder_state() -> None:
    FakeLibraryManager.entries = {}
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.get("/library?dir=uploaded")

    assert response.status_code == 200
    assert "This folder is empty." in response.text


def test_library_page_supports_folder_navigation() -> None:
    FakeLibraryManager.entries = {
        "uploaded/jobs/demo.urp": _make_library_file("uploaded/jobs/demo.urp"),
    }
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.get("/library?dir=uploaded")

    assert response.status_code == 200
    assert "uploaded/jobs" in response.text
    assert "Open Folder" in response.text


def test_library_page_supports_folder_selection() -> None:
    FakeLibraryManager.entries = {
        "uploaded/jobs/demo.urp": _make_library_file("uploaded/jobs/demo.urp"),
    }
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.get("/library?dir=uploaded&selected=uploaded/jobs")

    assert response.status_code == 200
    assert "uploaded/jobs" in response.text
    assert "Folder" in response.text
    assert "Remove Selected Path" in response.text


def test_library_page_bundle_selection_shows_bundle_first_actions() -> None:
    FakeLibraryManager.entries = {
        "uploaded/demo_bundle/main.urp": _make_library_file("uploaded/demo_bundle/main.urp"),
        "uploaded/demo_bundle/main.installation": _make_library_file(
            "uploaded/demo_bundle/main.installation", extension="installation"
        ),
        "uploaded/demo_bundle/main.variables": _make_library_file(
            "uploaded/demo_bundle/main.variables", extension="variables"
        ),
    }
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    FakeLibraryManager.bundle_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.get("/library?dir=uploaded&selected=uploaded/demo_bundle")

    assert response.status_code == 200
    assert "Deployable UR Program Bundle" in response.text
    assert "Deploy Bundle via Transfer" in response.text
    assert "/transfer?source_path=uploaded/demo_bundle" in response.text


def test_library_upload_redirects_with_success_feedback() -> None:
    FakeLibraryManager.entries = {}
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/upload",
        data={"current_dir": "uploaded/jobs"},
        files={"upload_file": ("demo.script", b"def demo():\nend\n", "text/plain")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Uploaded to library: uploaded/jobs/demo.script" in response.text


def test_library_upload_to_root_works_with_clean_library_root() -> None:
    FakeLibraryManager.entries = {}
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/upload",
        data={"current_dir": ""},
        files={"upload_file": ("demo.script", b"def demo():\nend\n", "text/plain")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Uploaded to library: demo.script" in response.text


def test_library_upload_multiple_files_creates_bundle_and_shows_summary() -> None:
    FakeLibraryManager.entries = {}
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    FakeLibraryManager.bundle_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/upload",
        data={"current_dir": "uploaded/jobs"},
        files=[
            ("upload_file", ("demo.urp", b"<urp/>", "application/octet-stream")),
            ("upload_file", ("demo.installation", b"install", "text/plain")),
            ("upload_file", ("demo.variables", b"vars", "text/plain")),
        ],
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Imported bundle: uploaded/jobs/demo" in response.text
    assert "readiness: ready" in response.text
    assert "Primary .urp" in response.text
    assert "uploaded/jobs/demo/demo.urp" in response.text


def test_library_upload_multiple_files_to_root_creates_bundle() -> None:
    FakeLibraryManager.entries = {}
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    FakeLibraryManager.bundle_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/upload",
        data={"current_dir": ""},
        files=[
            ("upload_file", ("demo.urp", b"<urp/>", "application/octet-stream")),
            ("upload_file", ("demo.installation", b"install", "text/plain")),
            ("upload_file", ("demo.variables", b"vars", "text/plain")),
        ],
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Imported bundle: demo" in response.text
    assert "demo/demo.urp" in response.text


def test_library_bundle_import_stage_shows_preview_summary() -> None:
    FakeLibraryManager.entries = {}
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    FakeLibraryManager.bundle_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/bundle-import/stage",
        data={"current_dir": "uploaded/jobs"},
        files=[
            ("bundle_files", ("demo.urp", b"<urp/>", "application/octet-stream")),
            ("bundle_files", ("demo.installation", b"install", "text/plain")),
            ("bundle_files", ("demo.variables", b"vars", "text/plain")),
        ],
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Bundle Import Preview" in response.text
    assert "uploaded/jobs/demo" in response.text
    assert "Confirm Bundle Import" in response.text
    assert "uploaded/jobs/demo/demo.urp" in response.text


def test_library_bundle_import_stage_shows_runtime_safe_primary_urp_plan() -> None:
    FakeLibraryManager.entries = {}
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    FakeLibraryManager.bundle_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/bundle-import/stage",
        data={"current_dir": "uploaded/jobs"},
        files=[
            ("bundle_files", ("my program.urp", b"<urp/>", "application/octet-stream")),
            ("bundle_files", ("my program.installation", b"install", "text/plain")),
            ("bundle_files", ("my program.variables", b"vars", "text/plain")),
        ],
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Primary .urp (original)" in response.text
    assert "my program.urp" in response.text
    assert "Primary .urp (runtime-safe)" in response.text
    assert "my_program.urp" in response.text
    assert "Normalization needed" in response.text


def test_library_bundle_import_commit_creates_bundle_and_redirects() -> None:
    FakeLibraryManager.entries = {}
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    FakeLibraryManager.bundle_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    stage_response = gui_client.post(
        "/library/bundle-import/stage",
        data={"current_dir": "uploaded/jobs"},
        files=[
            ("bundle_files", ("demo.urp", b"<urp/>", "application/octet-stream")),
            ("bundle_files", ("demo.installation", b"install", "text/plain")),
            ("bundle_files", ("demo.variables", b"vars", "text/plain")),
        ],
        follow_redirects=True,
    )
    token_prefix = 'name="token" value="'
    assert token_prefix in stage_response.text
    token = stage_response.text.split(token_prefix, 1)[1].split('"', 1)[0]

    commit_response = gui_client.post(
        "/library/bundle-import/commit",
        data={"token": token, "current_dir": "uploaded/jobs"},
        follow_redirects=True,
    )

    assert commit_response.status_code == 200
    assert "Imported bundle: uploaded/jobs/demo" in commit_response.text
    assert "Primary .urp" in commit_response.text
    assert "uploaded/jobs/demo/demo.urp" in commit_response.text


def test_library_bundle_import_commit_reports_runtime_safe_rename_when_primary_was_unsafe() -> None:
    FakeLibraryManager.entries = {}
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    FakeLibraryManager.bundle_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    stage_response = gui_client.post(
        "/library/bundle-import/stage",
        data={"current_dir": "uploaded/jobs"},
        files=[
            ("bundle_files", ("my program.urp", b"<urp/>", "application/octet-stream")),
            ("bundle_files", ("my program.installation", b"install", "text/plain")),
            ("bundle_files", ("my program.variables", b"vars", "text/plain")),
        ],
        follow_redirects=True,
    )
    token_prefix = 'name="token" value="'
    token = stage_response.text.split(token_prefix, 1)[1].split('"', 1)[0]

    commit_response = gui_client.post(
        "/library/bundle-import/commit",
        data={"token": token, "current_dir": "uploaded/jobs"},
        follow_redirects=True,
    )

    assert commit_response.status_code == 200
    assert "Runtime-safe primary .urp rename" in commit_response.text
    assert "my program.urp -&gt; my_program.urp" in commit_response.text
    assert "uploaded/jobs/my_program/my_program.urp" in commit_response.text


def test_library_upload_redirects_with_error_feedback() -> None:
    FakeLibraryManager.entries = {}
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = "upload blocked"
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/upload",
        data={"current_dir": "uploaded"},
        files={"upload_file": ("demo.script", b"def demo():\nend\n", "text/plain")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Upload failed: upload blocked" in response.text


def test_library_create_folder_redirects_with_success_feedback() -> None:
    FakeLibraryManager.entries = {}
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/create-folder",
        data={"current_dir": "uploaded", "folder_name": "jobs"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Created folder: uploaded/jobs" in response.text


def test_library_create_folder_redirects_with_error_feedback() -> None:
    FakeLibraryManager.entries = {}
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = "folder blocked"
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/create-folder",
        data={"current_dir": "uploaded", "folder_name": "jobs"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Create folder failed: folder blocked" in response.text


def test_library_remove_redirects_with_success_feedback() -> None:
    FakeLibraryManager.entries = {
        "uploaded/demo.script": _make_library_file("uploaded/demo.script"),
    }
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    FakeLibraryManager.removed = []
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/remove/uploaded/demo.script",
        data={"current_dir": "uploaded"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Removed library path: uploaded/demo.script" in response.text
    assert FakeLibraryManager.removed == ["uploaded/demo.script"]


def test_library_remove_redirects_with_error_feedback() -> None:
    FakeLibraryManager.entries = {
        "uploaded/demo.script": _make_library_file("uploaded/demo.script"),
    }
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {"uploaded/demo.script": "remove blocked"}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    FakeLibraryManager.removed = []
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/remove/uploaded/demo.script",
        data={"current_dir": "uploaded"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Remove failed: remove blocked" in response.text


def test_library_move_redirects_with_success_feedback() -> None:
    FakeLibraryManager.entries = {
        "uploaded/demo.script": _make_library_file("uploaded/demo.script"),
    }
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/move",
        data={
            "source_path": "uploaded/demo.script",
            "destination_path": "uploaded/archive/demo.script",
            "current_dir": "uploaded",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Moved library path to: uploaded/archive/demo.script" in response.text


def test_library_move_redirects_with_error_feedback() -> None:
    FakeLibraryManager.entries = {
        "uploaded/demo.script": _make_library_file("uploaded/demo.script"),
    }
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {
        ("uploaded/demo.script", "uploaded/archive/demo.script"): "move blocked"
    }
    FakeLibraryManager.copy_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/move",
        data={
            "source_path": "uploaded/demo.script",
            "destination_path": "uploaded/archive/demo.script",
            "current_dir": "uploaded",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Move failed: move blocked" in response.text


def test_library_copy_redirects_with_success_feedback() -> None:
    FakeLibraryManager.entries = {
        "uploaded/demo.script": _make_library_file("uploaded/demo.script"),
    }
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/copy",
        data={
            "source_path": "uploaded/demo.script",
            "destination_path": "uploaded/demo_copy.script",
            "current_dir": "uploaded",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Copied library path to: uploaded/demo_copy.script" in response.text


def test_library_copy_redirects_with_error_feedback() -> None:
    FakeLibraryManager.entries = {
        "uploaded/demo.script": _make_library_file("uploaded/demo.script"),
    }
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {
        ("uploaded/demo.script", "uploaded/demo_copy.script"): "copy blocked"
    }
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/copy",
        data={
            "source_path": "uploaded/demo.script",
            "destination_path": "uploaded/demo_copy.script",
            "current_dir": "uploaded",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Copy failed: copy blocked" in response.text


def test_library_send_to_robot_redirects_with_success_feedback(tmp_path: Path) -> None:
    FakeLibraryManager.entries = {
        "uploaded/demo.script": _make_library_file("uploaded/demo.script"),
    }
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    FakeLibraryManager.stored_file_errors = {}
    FakeRobotManager.calls = []
    FakeRobotManager.remote_file_action_errors = {}
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    gui_client = TestClient(
        create_app(
            config_path=config_path,
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/send-to-robot",
        data={
            "source_path": "uploaded/demo.script",
            "robot_name": "robot1",
            "remote_dir": "/programs/jobs",
            "current_dir": "uploaded",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Sent to robot &#39;robot1&#39;: uploaded/demo.script -&gt; /programs/jobs/demo.script" in response.text
    assert ("deploy", "demo.script:/programs/jobs/demo.script") in FakeRobotManager.calls


def test_library_send_bundle_to_robot_deploys_all_files_and_can_assign_runtime(
    tmp_path: Path,
) -> None:
    bundle_root = tmp_path / "storage" / "library" / "uploaded" / "demo_bundle"
    bundle_root.mkdir(parents=True, exist_ok=True)
    (bundle_root / "main.urp").write_text("<urp/>", encoding="utf-8")
    (bundle_root / "main.installation").write_text("installation", encoding="utf-8")
    (bundle_root / "main.variables").write_text("variables", encoding="utf-8")
    FakeLibraryManager.entries = {
        "uploaded/demo_bundle/main.urp": _make_library_file("uploaded/demo_bundle/main.urp"),
        "uploaded/demo_bundle/main.installation": _make_library_file(
            "uploaded/demo_bundle/main.installation", extension="installation"
        ),
        "uploaded/demo_bundle/main.variables": _make_library_file(
            "uploaded/demo_bundle/main.variables", extension="variables"
        ),
    }
    for path, entry in FakeLibraryManager.entries.items():
        entry["stored_path"] = str(tmp_path / "storage" / "library" / path)
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    FakeLibraryManager.bundle_errors = {}
    FakeLibraryManager.stored_file_errors = {}
    FakeRobotManager.calls = []
    FakeRobotManager.remote_file_action_errors = {}
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    gui_client = TestClient(
        create_app(
            config_path=config_path,
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/send-to-robot",
        data={
            "source_path": "uploaded/demo_bundle",
            "robot_name": "robot1",
            "remote_dir": "/programs/jobs",
            "current_dir": "uploaded",
            "assign_after_deploy": "1",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Deployed bundle to robot" in response.text
    assert "/programs/jobs/demo_bundle/main.urp" in response.text
    assert "Assigned as runtime target." in response.text
    assert ("deploy-bundle", "demo_bundle:/programs/jobs/demo_bundle") in FakeRobotManager.calls


def test_transfer_execute_bundle_shows_explicit_deploy_assign_validate_result(
    tmp_path: Path,
) -> None:
    bundle_root = tmp_path / "storage" / "library" / "uploaded" / "demo_bundle"
    bundle_root.mkdir(parents=True, exist_ok=True)
    (bundle_root / "main.urp").write_text("<urp/>", encoding="utf-8")
    (bundle_root / "main.installation").write_text("installation", encoding="utf-8")
    (bundle_root / "main.variables").write_text("variables", encoding="utf-8")

    FakeLibraryManager.entries = {
        "uploaded/demo_bundle/main.urp": _make_library_file("uploaded/demo_bundle/main.urp"),
        "uploaded/demo_bundle/main.installation": _make_library_file(
            "uploaded/demo_bundle/main.installation", extension="installation"
        ),
        "uploaded/demo_bundle/main.variables": _make_library_file(
            "uploaded/demo_bundle/main.variables", extension="variables"
        ),
    }
    for path, entry in FakeLibraryManager.entries.items():
        entry["stored_path"] = str(tmp_path / "storage" / "library" / path)
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    FakeLibraryManager.bundle_errors = {}
    FakeLibraryManager.stored_file_errors = {}

    FakeRobotManager.calls = []
    FakeRobotManager.remote_file_action_errors = {}
    FakeRobotManager.action_results = {("robot1", "load"): "Loading program: programs/jobs/demo_bundle/main.urp"}
    FakeRobotManager.action_errors = {}
    FakeRobotManager.explicit_load_outcomes = {"robot1": "success"}
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}

    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    gui_client = TestClient(
        create_app(
            config_path=config_path,
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/transfer/execute",
        data={
            "source_path": "uploaded/demo_bundle",
            "robot_name": "robot1",
            "remote_dir": "/programs/jobs",
            "assign_after_deploy": "1",
            "validate_load_after_assign": "1",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Deploy / Assign / Validate outcome" in response.text
    assert "Workflow Result" in response.text
    assert "Assignment Performed" in response.text
    assert "Yes" in response.text
    assert "/programs/jobs/demo_bundle/main.urp" in response.text
    assert "validation outcome" in response.text.lower() or "Validation Outcome" in response.text
    assert "Continue to Robot Workspace" in response.text


def test_transfer_execute_blocks_nested_bundle_destination_without_override(
    tmp_path: Path,
) -> None:
    bundle_root = tmp_path / "storage" / "library" / "uploaded" / "demo_bundle"
    bundle_root.mkdir(parents=True, exist_ok=True)
    (bundle_root / "main.urp").write_text("<urp/>", encoding="utf-8")
    (bundle_root / "main.installation").write_text("installation", encoding="utf-8")
    (bundle_root / "main.variables").write_text("variables", encoding="utf-8")
    FakeLibraryManager.entries = {
        "uploaded/demo_bundle/main.urp": _make_library_file("uploaded/demo_bundle/main.urp"),
        "uploaded/demo_bundle/main.installation": _make_library_file(
            "uploaded/demo_bundle/main.installation", extension="installation"
        ),
        "uploaded/demo_bundle/main.variables": _make_library_file(
            "uploaded/demo_bundle/main.variables", extension="variables"
        ),
    }
    for path, entry in FakeLibraryManager.entries.items():
        entry["stored_path"] = str(tmp_path / "storage" / "library" / path)
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    gui_client = TestClient(
        create_app(
            config_path=config_path,
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/transfer/execute",
        data={
            "source_path": "uploaded/demo_bundle",
            "robot_name": "robot1",
            "remote_dir": "/ursim/programs.UR5/demo_bundle",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "nested bundle path" in response.text.lower()


def test_transfer_execute_blocks_ordinary_folder_source(tmp_path: Path) -> None:
    FakeLibraryManager.entries = {
        "robot1/readme.txt": _make_library_file("robot1/readme.txt", extension="txt"),
    }
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    gui_client = TestClient(
        create_app(
            config_path=config_path,
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/transfer/execute",
        data={
            "source_path": "robot1",
            "robot_name": "robot1",
            "remote_dir": "/ursim/programs.UR5",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Selected bundle has no deterministic primary .urp." in response.text


def test_transfer_result_shows_skipped_assignment_and_validation_note(
    tmp_path: Path,
) -> None:
    library_file = tmp_path / "storage" / "library" / "uploaded" / "demo.urp"
    library_file.parent.mkdir(parents=True, exist_ok=True)
    library_file.write_text("<urp/>", encoding="utf-8")
    FakeLibraryManager.entries = {
        "uploaded/demo.urp": _make_library_file("uploaded/demo.urp"),
    }
    FakeLibraryManager.entries["uploaded/demo.urp"]["stored_path"] = str(library_file)
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: /ursim/programs.UR5/old/old.urp
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    FakeRobotManager.remote_file_action_errors = {}
    gui_client = TestClient(
        create_app(
            config_path=config_path,
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/transfer/execute",
        data={
            "source_path": "uploaded/demo.urp",
            "robot_name": "robot1",
            "remote_dir": "/ursim/programs.UR5",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Runtime assignment was not changed." in response.text
    assert "dashboard load was not validated" in response.text.lower()


def test_library_prepare_runtime_safe_copy_for_legacy_unsafe_bundle() -> None:
    FakeLibraryManager.entries = {
        "uploaded/legacy/main file.urp": _make_library_file("uploaded/legacy/main file.urp"),
        "uploaded/legacy/main.installation": _make_library_file(
            "uploaded/legacy/main.installation", extension="installation"
        ),
        "uploaded/legacy/main.variables": _make_library_file(
            "uploaded/legacy/main.variables", extension="variables"
        ),
    }
    FakeLibraryManager.safe_copy_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/bundle-prepare-safe-copy",
        data={"source_path": "uploaded/legacy", "current_dir": "uploaded"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Prepared runtime-safe copy: uploaded/legacy_safe" in response.text
    assert "main file.urp -&gt; main_file.urp" in response.text
    assert "uploaded/legacy_safe/main_file.urp" in response.text


def test_transfer_execute_validation_is_blocked_for_unsafe_runtime_argument(
    tmp_path: Path,
) -> None:
    bundle_root = tmp_path / "storage" / "library" / "uploaded" / "demo_bundle"
    bundle_root.mkdir(parents=True, exist_ok=True)
    (bundle_root / "main file.urp").write_text("<urp/>", encoding="utf-8")
    (bundle_root / "main.installation").write_text("installation", encoding="utf-8")
    (bundle_root / "main.variables").write_text("variables", encoding="utf-8")

    FakeLibraryManager.entries = {
        "uploaded/demo_bundle/main file.urp": _make_library_file("uploaded/demo_bundle/main file.urp"),
        "uploaded/demo_bundle/main.installation": _make_library_file(
            "uploaded/demo_bundle/main.installation", extension="installation"
        ),
        "uploaded/demo_bundle/main.variables": _make_library_file(
            "uploaded/demo_bundle/main.variables", extension="variables"
        ),
    }
    for path, entry in FakeLibraryManager.entries.items():
        entry["stored_path"] = str(tmp_path / "storage" / "library" / path)
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    FakeLibraryManager.bundle_errors = {}
    FakeLibraryManager.stored_file_errors = {}

    FakeRobotManager.calls = []
    FakeRobotManager.remote_file_action_errors = {}
    FakeRobotManager.action_results = {}
    FakeRobotManager.action_errors = {}
    FakeRobotManager.explicit_load_outcomes = {}
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}

    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    gui_client = TestClient(
        create_app(
            config_path=config_path,
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/transfer/execute",
        data={
            "source_path": "uploaded/demo_bundle",
            "robot_name": "robot1",
            "remote_dir": "/ursim/programs.UR5/jobs",
            "assign_after_deploy": "1",
            "validate_load_after_assign": "1",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "validation was blocked" in response.text
    assert "unsafe_runtime_path" in response.text
    assert "Cannot validate dashboard load because the derived load argument contains spaces or unsafe characters." in response.text


def test_library_send_to_robot_redirects_with_missing_local_file_feedback(tmp_path: Path) -> None:
    FakeLibraryManager.entries = {
        "uploaded/demo.script": _make_library_file("uploaded/demo.script"),
    }
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    FakeLibraryManager.stored_file_errors = {
        "uploaded/demo.script": "Stored library file not found for 'uploaded/demo.script': missing payload"
    }
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    gui_client = TestClient(
        create_app(
            config_path=config_path,
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/send-to-robot",
        data={
            "source_path": "uploaded/demo.script",
            "robot_name": "robot1",
            "remote_dir": "/programs",
            "current_dir": "uploaded",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Send to robot failed: Stored library file not found" in response.text


def test_library_send_to_robot_redirects_with_invalid_robot_feedback(tmp_path: Path) -> None:
    FakeLibraryManager.entries = {
        "uploaded/demo.script": _make_library_file("uploaded/demo.script"),
    }
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    FakeLibraryManager.stored_file_errors = {}
    config_path = tmp_path / "robots.yaml"
    config_path.write_text("robots: {}\n", encoding="utf-8")
    gui_client = TestClient(
        create_app(
            config_path=config_path,
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/send-to-robot",
        data={
            "source_path": "uploaded/demo.script",
            "robot_name": "robot9",
            "remote_dir": "/programs",
            "current_dir": "uploaded",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Send to robot failed:" in response.text
    assert "robot9" in response.text


def test_library_send_to_robot_redirects_with_invalid_remote_destination_feedback(tmp_path: Path) -> None:
    FakeLibraryManager.entries = {
        "uploaded/demo.script": _make_library_file("uploaded/demo.script"),
    }
    FakeLibraryManager.list_errors = {}
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.create_folder_error = None
    FakeLibraryManager.move_errors = {}
    FakeLibraryManager.copy_errors = {}
    FakeLibraryManager.stored_file_errors = {}
    FakeRobotManager.remote_file_action_errors = {
        ("robot1", "deploy", "/invalid/demo.script"): "remote destination blocked"
    }
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    ssh_port: 2222
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    FakeRobotManager.statuses = {"robot1": RobotStatus(name="robot1", connected=True)}
    gui_client = TestClient(
        create_app(
            config_path=config_path,
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/send-to-robot",
        data={
            "source_path": "uploaded/demo.script",
            "robot_name": "robot1",
            "remote_dir": "/invalid",
            "current_dir": "uploaded",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Send to robot failed: remote destination blocked" in response.text
