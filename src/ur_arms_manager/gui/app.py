from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable
from urllib.parse import urlencode
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ur_arms_manager.config import DEFAULT_CONFIG_PATH, LIBRARY_PROGRAMS_DIR, ROOT_DIR
from ur_arms_manager.models import RobotConfig, RobotStatus
from ur_arms_manager.registry import RegistryError, RobotRegistry
from ur_arms_manager.services.compatibility import CompatibilityResult, CompatibilityService
from ur_arms_manager.services.library_manager import LibraryError, LibraryManager
from ur_arms_manager.services.robot_manager import RobotManager
from ur_arms_manager.services.runtime_validation import (
    build_runtime_readiness_snapshot,
    derive_dashboard_load_argument,
    runtime_name_safety_warning,
)


GUI_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = GUI_DIR / "templates"
STATIC_DIR = GUI_DIR / "static"
POLL_INTERVAL_MS = 2500
URSIM_REMOTE_ROOT_PROFILE = "/ursim/programs.UR5"
ROBOT_FILES_ROOT = URSIM_REMOTE_ROOT_PROFILE
ACTION_LABELS = {
    "power-on": "Power On",
    "brake-release": "Brake Release",
    "power-off": "Power Off",
    "load": "Load",
    "play": "Play",
    "stop": "Stop",
}


def _describe_assignment(assigned_program: str | None) -> dict[str, Any]:
    assigned = str(assigned_program or "").strip()
    if not assigned:
        return {
            "display": "None assigned",
            "kind": "missing",
            "kind_label": "None",
            "is_runtime_loadable": False,
            "runtime_note": "Assign one real robot-side file path before using Load.",
        }
    if assigned.startswith("library://"):
        return {
            "display": assigned,
            "kind": "library-marker",
            "kind_label": "Library Marker",
            "is_runtime_loadable": False,
            "runtime_note": "This is not a real robot-side file path. Use direct Run Script, or assign one remote file path before using Load.",
        }
    if assigned.startswith("/"):
        return {
            "display": assigned,
            "kind": "remote-path",
            "kind_label": "Remote Runtime Path",
            "is_runtime_loadable": True,
            "runtime_note": "Load uses this assigned robot-side path. It is separate from the currently selected SSH/SFTP browser path.",
        }
    return {
        "display": assigned,
        "kind": "legacy-path",
        "kind_label": "Legacy Path",
        "is_runtime_loadable": False,
        "runtime_note": "This assignment is not a real absolute robot-side path. Reassign it to a remote path like /programs/demo.urp before using Load.",
    }


def _normalize_remote_dir(remote_dir: str | None) -> str:
    candidate = str(remote_dir or "").strip() or ROBOT_FILES_ROOT
    if not candidate.startswith("/"):
        candidate = f"/{candidate}"
    if len(candidate) > 1:
        candidate = candidate.rstrip("/")
    return candidate or "/"


def _join_remote_path(base_dir: str, name: str) -> str:
    base_dir = _normalize_remote_dir(base_dir)
    if base_dir == "/":
        return f"/{name}"
    return f"{base_dir}/{name}"


def _parent_remote_dir(remote_dir: str) -> str | None:
    path = _normalize_remote_dir(remote_dir)
    if path == "/":
        return None
    parent = str(Path(path).parent).replace("\\", "/")
    return parent or "/"


def _serialize_robot_status(status: RobotStatus) -> dict[str, str | bool]:
    if status.connected:
        detail = (
            "RTDE monitoring active"
            if status.monitoring_source == "rtde"
            else "Dashboard monitoring active"
        )
        state_label = "Connected"
        state_class = "status-connected"
    else:
        detail = status.detail or "Robot unreachable"
        state_label = "Disconnected"
        state_class = "status-disconnected"

    return {
        "connected": status.connected,
        "robotmode": status.robotmode,
        "safety_status": status.safety_status,
        "program_state": status.program_running,
        "detail": detail,
        "state_label": state_label,
        "state_class": state_class,
        "monitoring_source": status.monitoring_source,
    }


def _serialize_robot_card(
    robot: RobotConfig,
    robot_manager_factory: Callable[[RobotConfig], RobotManager],
) -> dict[str, Any]:
    status = robot_manager_factory(robot).status()
    assignment = _describe_assignment(robot.assigned_program)
    return {
        "name": robot.name,
        "host": robot.host,
        "dashboard_port": robot.dashboard_port,
        "script_port": robot.script_port,
        "ssh_port": robot.ssh_port,
        "enabled": robot.enabled,
        "assigned_program": assignment["display"],
        "assignment_kind": assignment["kind"],
        "assignment_kind_label": assignment["kind_label"],
        "assignment_runtime_note": assignment["runtime_note"],
        "can_load": bool(assignment["is_runtime_loadable"]),
        "actions_enabled": robot.enabled,
        "actions_disabled_reason": (
            None
            if robot.enabled
            else "Robot is disabled in config. Enable it before sending commands."
        ),
        "load_disabled_reason": (
            assignment["runtime_note"]
            if robot.enabled and not assignment["is_runtime_loadable"]
            else (
                "Robot is disabled in config. Enable it before sending commands."
                if not robot.enabled
                else None
            )
        ),
        "status": _serialize_robot_status(status),
    }


def _get_action_methods(manager: RobotManager) -> dict[str, Callable[[], str]]:
    return {
        "power-on": manager.power_on,
        "brake-release": manager.brake_release,
        "power-off": manager.power_off,
        "load": manager.load_assigned_program,
        "play": manager.play_program,
        "stop": manager.stop_program,
    }


def _serialize_robot_cards(
    registry: RobotRegistry,
    robot_manager_factory: Callable[[RobotConfig], RobotManager],
) -> list[dict[str, Any]]:
    robots = registry.list_robots()
    cards: list[dict[str, Any]] = []

    for robot in robots.values():
        cards.append(_serialize_robot_card(robot, robot_manager_factory))

    return cards


def _suggest_next_robot_action(robot_card: dict[str, Any], latest_load_validation: dict[str, Any] | None) -> str:
    if not robot_card.get("enabled"):
        return "Enable robot in config before runtime actions."
    if not robot_card["status"]["connected"]:
        return "Verify robot connectivity and remote-control mode."
    if not robot_card.get("can_load"):
        return "Assign one real remote .urp path before dashboard Load."
    if latest_load_validation and latest_load_validation.get("outcome") != "success":
        return "Fix load validation failure before Play."
    if latest_load_validation and latest_load_validation.get("outcome") == "success":
        return "Load succeeded. Play can be attempted."
    return "Run Load validation for assigned runtime path."


def _build_fleet_overview_cards(
    robot_cards: list[dict[str, Any]],
    latest_load_validation: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for card in robot_cards:
        validation = latest_load_validation.get(card["name"])
        cards.append(
            {
                **card,
                "last_load_outcome": (
                    validation.get("outcome")
                    if validation is not None
                    else "not_attempted"
                ),
                "next_action": _suggest_next_robot_action(card, validation),
            }
        )
    return cards


def _shorten_stored_path(stored_path: str) -> str:
    path = Path(stored_path)
    parts = path.parts
    if len(parts) <= 4:
        return str(path)
    return str(Path(*parts[-4:]))


def _summarize_stored_file(item: dict[str, Any]) -> tuple[bool, str | None]:
    stored_path = str(item.get("stored_path") or "").strip()
    payload_status = str(item.get("payload_status") or "").strip().lower()
    payload_error = str(item.get("payload_error") or "").strip() or None
    explicit_exists = item.get("stored_file_exists")
    if payload_status == "ok":
        return True, None
    if payload_status in {"missing", "ambiguous"}:
        return False, payload_error
    if explicit_exists is not None:
        has_stored_file = bool(explicit_exists)
    elif stored_path:
        has_stored_file = Path(stored_path).is_file()
    else:
        has_stored_file = False

    if has_stored_file:
        return True, None
    if not stored_path:
        return False, "Stored file location is not recorded for this library item."
    return (
        False,
        "Stored file is missing from library storage. Re-upload or import it again before deploy, run, or edit actions.",
    )


def _serialize_library_item(program_id: str, item: dict[str, Any] | None, error: str | None) -> dict[str, Any]:
    item = item or {}
    extension = str(item.get("extension") or "unknown").lower()
    stored_path = str(item.get("stored_path") or "").strip()
    origin = str(item.get("origin") or "local").strip() or "local"
    has_stored_file, stored_file_issue = _summarize_stored_file(item)
    return {
        "program_id": program_id,
        "original_filename": str(item.get("original_filename") or "Unknown file"),
        "extension": extension,
        "type_label": ".script" if extension == "script" else ".urp" if extension == "urp" else extension,
        "type_class": f"type-{extension}" if extension in {"script", "urp"} else "type-unknown",
        "stored_path": stored_path,
        "stored_path_short": _shorten_stored_path(stored_path) if stored_path else "Unavailable",
        "origin": origin,
        "source_robot": item.get("source_robot"),
        "source_remote_path": item.get("source_remote_path"),
        "created_at": item.get("created_at"),
        "size_bytes": item.get("size_bytes"),
        "error": error,
        "has_stored_file": has_stored_file,
        "stored_file_issue": stored_file_issue,
    }


def _serialize_library_items(library: LibraryManager) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for program_id in library.storage.list_program_ids():
        try:
            raw = library.inspect_item(program_id)
            items.append(_serialize_library_item(program_id, raw, error=None))
        except Exception as exc:
            items.append(_serialize_library_item(program_id, None, error=str(exc)))
    return items


def _find_library_item(items: list[dict[str, Any]], program_id: str | None) -> dict[str, Any] | None:
    if not program_id:
        return items[0] if items else None
    for item in items:
        if item["program_id"] == program_id:
            return item
    return None


def _build_selected_library_item(
    library: LibraryManager,
    items: list[dict[str, Any]],
    program_id: str | None,
) -> dict[str, Any] | None:
    selected_item = _find_library_item(items, program_id)
    if selected_item is None or selected_item.get("error"):
        return selected_item

    if selected_item.get("extension") != "urp":
        return selected_item

    try:
        enriched = library.inspect_item_enriched(selected_item["program_id"])
    except Exception as exc:
        enriched = {"urp_analysis": {"parse_success": False, "parse_error": str(exc)}}

    merged = dict(selected_item)
    merged["urp_analysis"] = enriched.get("urp_analysis")
    return merged


def _build_library_redirect(
    flash_kind: str,
    flash_message: str,
    selected: str | None = None,
    current_dir: str | None = None,
) -> RedirectResponse:
    params: dict[str, str] = {
        "flash_kind": flash_kind,
        "flash_message": flash_message,
    }
    if selected:
        params["selected"] = selected
    if current_dir:
        params["dir"] = current_dir
    return RedirectResponse(url=f"/library?{urlencode(params)}", status_code=303)


def _normalize_library_dir(relative_dir: str | None) -> str:
    candidate = str(relative_dir or "").strip().strip("/")
    return candidate


def _parent_library_dir(relative_dir: str) -> str | None:
    if not relative_dir:
        return None
    parent = Path(relative_dir).parent.as_posix()
    return "" if parent == "." else parent


def _join_library_path(base_dir: str, name: str) -> str:
    base = _normalize_library_dir(base_dir)
    return name if not base else f"{base}/{name}"


def _serialize_library_entry(entry: dict[str, Any], current_dir: str) -> dict[str, Any]:
    relative_path = str(entry.get("library_path") or entry.get("relative_path") or entry.get("program_id") or "")
    name = str(entry.get("name") or Path(relative_path).name or "Unknown")
    item_kind = "directory" if bool(entry.get("is_dir")) or entry.get("item_kind") == "directory" else "file"
    extension = str(entry.get("extension") or "").lower()
    absolute_path = str(entry.get("stored_path") or "").strip()
    if item_kind == "directory":
        copy_suggestion = f"{relative_path}_copy"
    else:
        path_obj = Path(relative_path)
        if path_obj.suffix:
            copy_suggestion = f"{path_obj.with_suffix('').as_posix()}_copy{path_obj.suffix}"
        else:
            copy_suggestion = f"{relative_path}_copy"

    bundle_summary = entry.get("bundle_summary")
    return {
        "library_path": relative_path,
        "name": name,
        "item_kind": item_kind,
        "is_dir": item_kind == "directory",
        "extension": extension,
        "type_label": "Folder" if item_kind == "directory" else f".{extension}" if extension else "File",
        "type_class": "type-folder" if item_kind == "directory" else f"type-{extension}" if extension in {"script", "urp"} else "type-unknown",
        "size_bytes": entry.get("size_bytes"),
        "created_at": entry.get("created_at"),
        "stored_path": absolute_path,
        "stored_path_short": _shorten_stored_path(absolute_path) if absolute_path else relative_path,
        "origin": entry.get("origin"),
        "open_dir": relative_path if item_kind == "directory" else current_dir,
        "select_path": relative_path,
        "copy_suggestion": copy_suggestion,
        "bundle_summary": bundle_summary,
    }


def _cleanup_bundle_import_stage(bundle_stage_store: dict[str, dict[str, Any]], token: str) -> None:
    staged = bundle_stage_store.pop(token, None)
    if not staged:
        return
    temp_dir = str(staged.get("temp_dir") or "").strip()
    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _classify_transfer_directory(summary: dict[str, Any]) -> tuple[str, bool, str | None]:
    files_by_type = summary.get("files_by_type") or {}
    urp_files = files_by_type.get("urp") or []
    readiness = str(summary.get("readiness_state") or "").lower()
    if len(urp_files) > 1:
        return (
            "invalid_bundle",
            False,
            "Multiple .urp files found. Primary runtime file is ambiguous.",
        )
    if len(urp_files) == 1:
        if readiness == "ready":
            return ("deployable_bundle", True, None)
        return ("warning_bundle", True, "Bundle is deployable but has readiness warnings.")
    return (
        "ordinary_folder",
        False,
        "Folder has no deterministic primary .urp and is not deployable as runtime bundle.",
    )


def _transfer_source_label(classification: str) -> str:
    labels = {
        "deployable_bundle": "Deployable Bundle",
        "warning_bundle": "Warning Bundle",
        "invalid_bundle": "Invalid Bundle",
        "ordinary_folder": "Ordinary Folder",
        "ordinary_file": "Ordinary File",
    }
    return labels.get(classification, "Unknown")


def _find_transfer_source(source_options: list[dict[str, Any]], path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    for source in source_options:
        if source.get("path") == path:
            return source
    return None


def _collect_transfer_sources(library_manager: LibraryManager) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    file_sources: list[dict[str, Any]] = []
    directory_sources_by_path: dict[str, dict[str, Any]] = {}

    for program_id in library_manager.storage.list_program_ids():
        try:
            item = library_manager.inspect_item(program_id)
        except Exception:
            continue
        file_sources.append(
            {
                "path": item.get("library_path", program_id),
                "name": item.get("name", Path(program_id).name),
                "kind": "file",
                "classification": "ordinary_file",
                "classification_label": _transfer_source_label("ordinary_file"),
                "is_deployable": True,
                "deploy_block_reason": None,
                "extension": str(item.get("extension") or "").lower(),
            }
        )

        for parent in Path(program_id).parents:
            if str(parent) in {"", "."}:
                continue
            bundle_path = parent.as_posix()
            if bundle_path in directory_sources_by_path:
                continue
            try:
                summary = library_manager.inspect_bundle(bundle_path)
            except Exception:
                continue
            classification, is_deployable, reason = _classify_transfer_directory(summary)
            directory_sources_by_path[bundle_path] = {
                "path": bundle_path,
                "name": summary.get("bundle_name", Path(bundle_path).name),
                "kind": "directory",
                "classification": classification,
                "classification_label": _transfer_source_label(classification),
                "is_deployable": is_deployable,
                "deploy_block_reason": reason,
                "summary": summary,
            }

    directory_sources = sorted(directory_sources_by_path.values(), key=lambda item: item["path"])
    file_sources = sorted(file_sources, key=lambda item: item["path"])
    return directory_sources, file_sources


def _parse_bool_query(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _serialize_system_diagnostics(
    registry: RobotRegistry,
    library_manager: LibraryManager,
) -> dict[str, Any]:
    config_path = registry.config_path
    diagnostics: dict[str, Any] = {
        "config_path": str(config_path),
        "config_loaded": False,
        "config_error": None,
        "robot_count": 0,
        "robots": [],
        "warnings": [],
        "library_root_path": str(getattr(library_manager.storage, "programs_root", "")),
        "library_item_count": 0,
        "stale_library_item_count": 0,
        "rtde_available": importlib.util.find_spec("rtde_receive") is not None,
    }

    try:
        data = registry.load()
        diagnostics["config_loaded"] = True
    except Exception as exc:
        diagnostics["config_error"] = str(exc)
        return diagnostics

    raw_robots = data.get("robots", {})
    diagnostics["robot_count"] = len(raw_robots)
    if not raw_robots:
        diagnostics["warnings"].append("No robots are configured in the robots section.")

    endpoint_seen: dict[tuple[str, str, int], list[str]] = {}
    for name, raw in raw_robots.items():
        raw = raw or {}
        host = str(raw.get("host") or "").strip()
        dashboard_port = _safe_int(raw.get("dashboard_port"))
        script_port = _safe_int(raw.get("script_port"))
        ssh_port = _safe_int(raw.get("ssh_port", 22))
        enabled = bool(raw.get("enabled", True))
        assigned_program = raw.get("assigned_program")
        warnings: list[str] = []

        if not host:
            warnings.append("Host is missing.")
        if dashboard_port is None:
            warnings.append("Dashboard port is missing or invalid.")
        if script_port is None:
            warnings.append("Script port is missing or invalid.")
        if not enabled:
            warnings.append("Robot is disabled in config.")

        for label, port in (
            ("dashboard", dashboard_port),
            ("script", script_port),
            ("ssh", ssh_port),
        ):
            if host and port is not None:
                endpoint_seen.setdefault((host, label, port), []).append(name)

        diagnostics["robots"].append(
            {
                "name": name,
                "host": host or "Missing",
                "dashboard_port": dashboard_port if dashboard_port is not None else "Missing",
                "script_port": script_port if script_port is not None else "Missing",
                "ssh_port": ssh_port if ssh_port is not None else "Missing",
                "enabled": enabled,
                "assigned_program": assigned_program or "None assigned",
                "warnings": warnings,
            }
        )

    for (host, label, port), names in endpoint_seen.items():
        if len(names) > 1:
            diagnostics["warnings"].append(
                f"Duplicate {label} endpoint {host}:{port} is shared by: {', '.join(names)}"
            )

    try:
        program_ids = library_manager.storage.list_program_ids()
    except Exception:
        program_ids = []
    diagnostics["library_item_count"] = len(program_ids)

    stale_count = 0
    for program_id in program_ids:
        try:
            item = library_manager.inspect_item(program_id)
            stored_path = str(item.get("stored_path") or "").strip()
            stored_file_exists = item.get("stored_file_exists")
            if stored_file_exists is False:
                stale_count += 1
                continue
            if not stored_path:
                stale_count += 1
                continue
            if stored_file_exists is not True and not Path(stored_path).is_file():
                stale_count += 1
        except Exception:
            stale_count += 1
    diagnostics["stale_library_item_count"] = stale_count

    return diagnostics


def _serialize_robot_file_browser(
    robot: RobotConfig,
    manager_factory: Callable[[RobotConfig], RobotManager],
    remote_dir: str,
) -> dict[str, Any]:
    manager = manager_factory(robot)
    current_dir = _normalize_remote_dir(remote_dir)
    listing_error = None
    fallback_notice = None
    entries: list[dict[str, str | bool]] = []

    def _entries_for(directory: str) -> list[dict[str, Any]]:
        return manager.list_remote_entries(directory)

    try:
        raw_entries = _entries_for(current_dir)
    except Exception as exc:
        if current_dir != URSIM_REMOTE_ROOT_PROFILE:
            try:
                current_dir = URSIM_REMOTE_ROOT_PROFILE
                raw_entries = _entries_for(current_dir)
                fallback_notice = (
                    "Requested remote path could not be listed. "
                    f"Showing current remote root profile: {URSIM_REMOTE_ROOT_PROFILE}."
                )
            except Exception:
                raw_entries = []
                listing_error = str(exc)
        else:
            raw_entries = []
            listing_error = str(exc)

    try:
        for raw_entry in raw_entries:
            name = str(raw_entry.get("name") or "")
            entry_kind = "directory" if bool(raw_entry.get("is_dir")) else "file"
            remote_path = _join_remote_path(current_dir, name)
            entries.append(
                {
                    "name": name,
                    "remote_path": remote_path,
                    "kind": entry_kind,
                    "kind_label": "Directory" if entry_kind == "directory" else "File",
                    "extension": Path(name).suffix.lower().lstrip(".") if entry_kind == "file" else "",
                    "copy_suggestion": _copy_remote_path_suggestion(
                        remote_path,
                        Path(name).suffix.lower().lstrip(".") if entry_kind == "file" else "",
                    ),
                    "type_class": (
                        "type-folder"
                        if entry_kind == "directory"
                        else "type-script"
                        if name.endswith(".script")
                        else "type-urp"
                        if name.endswith(".urp")
                        else "type-unknown"
                    ),
                }
            )
    except Exception as exc:
        listing_error = str(exc)

    return {
        "current_dir": current_dir,
        "parent_dir": _parent_remote_dir(current_dir),
        "entries": entries,
        "listing_error": listing_error,
        "fallback_notice": fallback_notice,
    }


def _serialize_selected_remote_entry(
    file_browser: dict[str, Any] | None,
    selected_remote_path: str | None,
) -> dict[str, Any] | None:
    if not file_browser or not selected_remote_path:
        return None
    for entry in file_browser.get("entries", []):
        if entry["remote_path"] == selected_remote_path:
            return entry
    return None


def _copy_remote_path_suggestion(remote_path: str, extension: str) -> str:
    if "." in remote_path:
        base = remote_path.rsplit(".", 1)[0]
        suffix = f".{extension}" if extension else ""
        return f"{base}_copy{suffix}"
    return f"{remote_path}_copy"


def _runtime_name_safety_warning(remote_path: str | None) -> str | None:
    return runtime_name_safety_warning(remote_path)


def _serialize_robot_options(registry: RobotRegistry) -> tuple[list[dict[str, str]], str | None]:
    try:
        robots = registry.list_robots()
    except RegistryError as exc:
        return [], str(exc)

    options = [
        {
            "name": robot.name,
            "label": f"{robot.name} ({robot.host})",
        }
        for robot in robots.values()
    ]
    return options, None


def _build_robot_workspace_redirect(
    robot_name: str,
    flash_kind: str,
    flash_message: str,
    remote_dir: str,
    selected_remote_path: str | None = None,
) -> RedirectResponse:
    params: dict[str, str] = {
        "remote_dir": _normalize_remote_dir(remote_dir),
        "flash_kind": flash_kind,
        "flash_message": flash_message,
    }
    if selected_remote_path:
        params["selected_remote_path"] = selected_remote_path
    return RedirectResponse(url=f"/robots/{robot_name}?{urlencode(params)}", status_code=303)


def _serialize_runtime_validation_context(
    robot_name: str,
    assigned_program: str | None,
    latest_load_validation: dict | None,
    deployed_primary_path: str | None,
) -> dict[str, Any]:
    assigned_runtime_path = str(assigned_program or "").strip() or None
    derived_load_argument: str | None = None
    derived_load_argument_error: str | None = None
    if assigned_runtime_path:
        try:
            derived_load_argument = derive_dashboard_load_argument(assigned_runtime_path)
        except Exception as exc:
            derived_load_argument_error = str(exc)

    readiness = build_runtime_readiness_snapshot(
        robot_name=robot_name,
        assigned_runtime_path=assigned_runtime_path,
        deployed_primary_path=deployed_primary_path,
        latest_load_validation=latest_load_validation,
    )

    return {
        "assigned_runtime_path": assigned_runtime_path,
        "derived_load_argument": derived_load_argument,
        "derived_load_argument_error": derived_load_argument_error,
        "latest_load_validation": latest_load_validation,
        "readiness": readiness.to_dict(),
    }


def _stamp_load_validation(result: dict[str, Any]) -> dict[str, Any]:
    stamped = dict(result)
    stamped["validated_at_utc"] = datetime.now(timezone.utc).isoformat()
    return stamped


def _build_overview_alerts(robot_cards: list[dict[str, Any]]) -> list[str]:
    alerts: list[str] = []
    disconnected = [card["name"] for card in robot_cards if not card["status"]["connected"]]
    if disconnected:
        alerts.append(f"Disconnected robots: {', '.join(disconnected)}")
    missing_assignment = [card["name"] for card in robot_cards if not card["can_load"]]
    if missing_assignment:
        alerts.append(
            "No loadable runtime assignment: "
            + ", ".join(missing_assignment)
        )
    return alerts


def create_app(
    config_path: Path | None = None,
    robot_manager_factory: Callable[[RobotConfig], RobotManager] = RobotManager,
    library_manager_factory: Callable[[], LibraryManager] | None = None,
    compatibility_service_factory: Callable[
        [LibraryManager, Callable[[RobotConfig], RobotManager]],
        CompatibilityService,
    ]
    | None = None,
) -> FastAPI:
    app = FastAPI(title="UR Arms Manager GUI")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.registry = RobotRegistry(config_path or DEFAULT_CONFIG_PATH)
    app.state.robot_manager_factory = robot_manager_factory
    app.state.library_manager = (
        library_manager_factory()
        if library_manager_factory is not None
        else LibraryManager(LIBRARY_PROGRAMS_DIR, root_dir=ROOT_DIR)
    )
    app.state.compatibility_service_factory = compatibility_service_factory
    app.state.latest_load_validation: dict[str, dict[str, Any]] = {}
    app.state.latest_deployed_primary_path: dict[str, str] = {}
    app.state.latest_script_run: dict[str, dict[str, str]] = {}
    app.state.bundle_import_staging: dict[str, dict[str, Any]] = {}

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return RedirectResponse(url="/overview", status_code=303)

    @app.get("/overview", response_class=HTMLResponse)
    def overview(request: Request) -> HTMLResponse:
        registry: RobotRegistry = request.app.state.registry
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )
        error_message = None
        overview_cards: list[dict[str, Any]] = []

        try:
            robot_cards = _serialize_robot_cards(registry, manager_factory)
            overview_cards = _build_fleet_overview_cards(
                robot_cards, request.app.state.latest_load_validation
            )
        except RegistryError as exc:
            error_message = str(exc)

        return templates.TemplateResponse(
            request,
            "overview.html",
            {
                "title": "Fleet Overview",
                "active_page": "overview",
                "overview_cards": overview_cards,
                "overview_alerts": _build_overview_alerts(overview_cards) if overview_cards else [],
                "error_message": error_message,
            },
        )

    @app.get("/robots", response_class=HTMLResponse)
    def robots(request: Request) -> HTMLResponse:
        registry: RobotRegistry = request.app.state.registry
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )
        error_message = None
        robot_cards: list[dict[str, Any]] = []

        try:
            robot_cards = _serialize_robot_cards(registry, manager_factory)
        except RegistryError as exc:
            error_message = str(exc)

        return templates.TemplateResponse(
            request,
            "robots.html",
            {
                "title": "Robots",
                "active_page": "robots",
                "robot_cards": robot_cards,
                "error_message": error_message,
                "poll_interval_ms": POLL_INTERVAL_MS,
            },
        )

    @app.get("/robots/{robot_name}", response_class=HTMLResponse)
    def robot_workspace(robot_name: str, request: Request) -> HTMLResponse:
        registry: RobotRegistry = request.app.state.registry
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )

        error_message = None
        robot_card: dict[str, Any] | None = None
        file_browser: dict[str, Any] | None = None
        runtime_validation_context: dict[str, Any] | None = None
        latest_script_run: dict[str, str] | None = None
        latest_deployed_primary_path: str | None = None
        selected_remote_path = request.query_params.get("selected_remote_path")
        flash_kind = request.query_params.get("flash_kind")
        flash_message = request.query_params.get("flash_message")
        remote_dir = _normalize_remote_dir(request.query_params.get("remote_dir"))

        try:
            robot = registry.get_robot(robot_name)
            robot_card = _serialize_robot_card(robot, manager_factory)
            file_browser = _serialize_robot_file_browser(robot, manager_factory, remote_dir)
            latest_load_validation = request.app.state.latest_load_validation.get(robot_name)
            deployed_primary_path = request.app.state.latest_deployed_primary_path.get(robot_name)
            latest_deployed_primary_path = deployed_primary_path
            runtime_validation_context = _serialize_runtime_validation_context(
                robot_name=robot_name,
                assigned_program=robot.assigned_program,
                latest_load_validation=latest_load_validation,
                deployed_primary_path=deployed_primary_path,
            )
            latest_script_run = request.app.state.latest_script_run.get(robot_name)
        except RegistryError as exc:
            error_message = str(exc)

        selected_remote_entry = _serialize_selected_remote_entry(
            file_browser, selected_remote_path
        )
        assigned_under_current_dir = False
        assigned_runtime_path = (
            str(runtime_validation_context.get("assigned_runtime_path") or "").strip()
            if runtime_validation_context
            else ""
        )
        current_remote_dir = (
            str(file_browser.get("current_dir") or "").strip()
            if file_browser
            else ""
        )
        if assigned_runtime_path and current_remote_dir:
            assigned_under_current_dir = (
                assigned_runtime_path == current_remote_dir
                or assigned_runtime_path.startswith(f"{current_remote_dir.rstrip('/')}/")
            )

        return templates.TemplateResponse(
            request,
            "robot_workspace.html",
            {
                "title": f"Robot {robot_name}",
                "active_page": "robots",
                "robot_card": robot_card,
                "robot_name": robot_name,
                "error_message": error_message,
                "poll_interval_ms": POLL_INTERVAL_MS,
                "file_browser": file_browser,
                "selected_remote_path": selected_remote_path,
                "selected_remote_entry": selected_remote_entry,
                "flash_kind": flash_kind,
                "flash_message": flash_message,
                "runtime_validation": runtime_validation_context,
                "latest_script_run": latest_script_run,
                "ursim_remote_root_profile": URSIM_REMOTE_ROOT_PROFILE,
                "latest_deployed_primary_path": latest_deployed_primary_path,
                "assigned_under_current_dir": assigned_under_current_dir,
                "runtime_name_warning": (
                    _runtime_name_safety_warning(selected_remote_path)
                    or _runtime_name_safety_warning(assigned_runtime_path)
                    or _runtime_name_safety_warning(latest_deployed_primary_path)
                ),
            },
        )

    @app.get("/api/robots/status")
    def robot_statuses(request: Request) -> JSONResponse:
        registry: RobotRegistry = request.app.state.registry
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )

        try:
            robot_cards = _serialize_robot_cards(registry, manager_factory)
        except RegistryError as exc:
            return JSONResponse(
                status_code=503,
                content={
                    "ok": False,
                    "error_message": str(exc),
                    "robots": [],
                },
            )

        return JSONResponse(
            {
                "ok": True,
                "error_message": None,
                "robots": [
                    {
                        "name": robot["name"],
                        "status": robot["status"],
                    }
                    for robot in robot_cards
                ],
            }
        )

    @app.get("/api/robots/{robot_name}/status")
    def robot_status(robot_name: str, request: Request) -> JSONResponse:
        registry: RobotRegistry = request.app.state.registry
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )

        try:
            robot = registry.get_robot(robot_name)
            robot_card = _serialize_robot_card(robot, manager_factory)
            runtime_validation_context = _serialize_runtime_validation_context(
                robot_name=robot_name,
                assigned_program=robot.assigned_program,
                latest_load_validation=request.app.state.latest_load_validation.get(robot_name),
                deployed_primary_path=request.app.state.latest_deployed_primary_path.get(robot_name),
            )
        except RegistryError as exc:
            return JSONResponse(
                status_code=404,
                content={
                    "ok": False,
                    "error_message": str(exc),
                    "robot": None,
                },
            )

        return JSONResponse(
            {
                "ok": True,
                "error_message": None,
                "robot": {
                    "name": robot_card["name"],
                    "assigned_program": robot_card["assigned_program"],
                    "can_load": robot_card["can_load"],
                    "assignment_kind_label": robot_card["assignment_kind_label"],
                    "assignment_runtime_note": robot_card["assignment_runtime_note"],
                    "status": robot_card["status"],
                    "runtime_validation": runtime_validation_context,
                },
            }
        )

    @app.post("/robots/{robot_name}/import-remote")
    def import_robot_workspace_file(
        robot_name: str,
        request: Request,
        remote_path: str = Form(...),
        remote_dir: str = Form(ROBOT_FILES_ROOT),
    ) -> RedirectResponse:
        registry: RobotRegistry = request.app.state.registry
        library_manager: LibraryManager = request.app.state.library_manager
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )

        remote_path = remote_path.strip()
        remote_dir = _normalize_remote_dir(remote_dir)
        if not remote_path:
            return _build_robot_workspace_redirect(
                robot_name,
                "error",
                "Import failed: no remote file was selected",
                remote_dir,
            )

        try:
            robot = registry.get_robot(robot_name)
            with tempfile.TemporaryDirectory(prefix="uam-gui-robot-import-") as tmp_dir:
                pulled_path = manager_factory(robot).pull_remote_file(remote_path, tmp_dir)
                item = library_manager.add_item(
                    str(pulled_path),
                    target_dir="",
                    extra_metadata={
                        "origin": "robot_remote",
                        "source_robot": robot_name,
                        "source_remote_path": remote_path,
                    },
                )
        except Exception as exc:
            return _build_robot_workspace_redirect(
                robot_name,
                "error",
                f"Import failed: {exc}",
                remote_dir,
                selected_remote_path=remote_path,
            )

        params = urlencode(
            {
                "selected": item.get("library_path", item["program_id"]),
                "flash_kind": "success",
                "flash_message": (
                    f"Imported from robot '{robot_name}': "
                    f"{remote_path} -> {item.get('library_path', item['program_id'])}"
                ),
            }
        )
        return RedirectResponse(url=f"/library?{params}", status_code=303)

    @app.post("/robots/{robot_name}/assign-remote-file")
    def assign_robot_workspace_remote_file(
        robot_name: str,
        request: Request,
        remote_dir: str = Form(ROBOT_FILES_ROOT),
        remote_path: str = Form(...),
        item_kind: str = Form(...),
        item_extension: str = Form(""),
    ) -> RedirectResponse:
        registry: RobotRegistry = request.app.state.registry

        remote_dir = _normalize_remote_dir(remote_dir)
        remote_path = remote_path.strip()
        item_kind = item_kind.strip().lower()
        item_extension = item_extension.strip().lower()
        if not remote_path:
            return _build_robot_workspace_redirect(
                robot_name,
                "error",
                "Assign remote path failed: no remote file was selected",
                remote_dir,
            )
        if item_kind == "directory":
            return _build_robot_workspace_redirect(
                robot_name,
                "error",
                "Assign remote path failed: folders cannot be used for Load. Select one remote file.",
                remote_dir,
                selected_remote_path=remote_path,
            )
        if item_extension == "script":
            return _build_robot_workspace_redirect(
                robot_name,
                "error",
                "Assign remote path failed: .script files use direct Run Script, not dashboard Load.",
                remote_dir,
                selected_remote_path=remote_path,
            )

        try:
            registry.assign_remote_program(robot_name, remote_path)
            request.app.state.latest_load_validation.pop(robot_name, None)
            return _build_robot_workspace_redirect(
                robot_name,
                "success",
                f"Assigned runtime path for robot '{robot_name}': {remote_path}",
                _parent_remote_dir(remote_path) or remote_dir,
                selected_remote_path=remote_path,
            )
        except Exception as exc:
            return _build_robot_workspace_redirect(
                robot_name,
                "error",
                f"Assign remote path failed: {exc}",
                remote_dir,
                selected_remote_path=remote_path,
            )

    @app.post("/robots/{robot_name}/files/create-folder")
    def create_robot_workspace_folder(
        robot_name: str,
        request: Request,
        remote_dir: str = Form(ROBOT_FILES_ROOT),
        folder_name: str = Form(...),
    ) -> RedirectResponse:
        registry: RobotRegistry = request.app.state.registry
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )

        remote_dir = _normalize_remote_dir(remote_dir)
        folder_name = folder_name.strip().strip("/")
        if not folder_name:
            return _build_robot_workspace_redirect(
                robot_name,
                "error",
                "Create folder failed: folder name is required",
                remote_dir,
            )
        if "/" in folder_name or "\\" in folder_name or folder_name in {".", ".."}:
            return _build_robot_workspace_redirect(
                robot_name,
                "error",
                "Create folder failed: folder name must be one safe directory name.",
                remote_dir,
            )

        target_path = _join_remote_path(remote_dir, folder_name)
        try:
            robot = registry.get_robot(robot_name)
            manager_factory(robot).create_remote_folder(target_path)
            return _build_robot_workspace_redirect(
                robot_name,
                "success",
                f"Created remote folder: {target_path}",
                remote_dir,
                selected_remote_path=target_path,
            )
        except Exception as exc:
            return _build_robot_workspace_redirect(
                robot_name,
                "error",
                f"Create folder failed: {exc}",
                remote_dir,
            )

    @app.post("/robots/{robot_name}/files/remove")
    def remove_robot_workspace_path(
        robot_name: str,
        request: Request,
        remote_dir: str = Form(ROBOT_FILES_ROOT),
        remote_path: str = Form(...),
        item_kind: str = Form(...),
    ) -> RedirectResponse:
        registry: RobotRegistry = request.app.state.registry
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )

        remote_dir = _normalize_remote_dir(remote_dir)
        remote_path = remote_path.strip()
        item_kind = item_kind.strip().lower()
        if not remote_path:
            return _build_robot_workspace_redirect(
                robot_name,
                "error",
                "Remove failed: no remote path was selected",
                remote_dir,
            )

        try:
            robot = registry.get_robot(robot_name)
            manager = manager_factory(robot)
            if item_kind == "directory":
                manager.remove_remote_folder(remote_path)
            else:
                manager.remove_remote_file(remote_path)
            return _build_robot_workspace_redirect(
                robot_name,
                "success",
                f"Removed remote path: {remote_path}",
                remote_dir,
            )
        except Exception as exc:
            return _build_robot_workspace_redirect(
                robot_name,
                "error",
                f"Remove failed: {exc}",
                remote_dir,
                selected_remote_path=remote_path,
            )

    @app.post("/robots/{robot_name}/files/move")
    def move_robot_workspace_path(
        robot_name: str,
        request: Request,
        remote_dir: str = Form(ROBOT_FILES_ROOT),
        source_path: str = Form(...),
        destination_path: str = Form(...),
    ) -> RedirectResponse:
        registry: RobotRegistry = request.app.state.registry
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )

        remote_dir = _normalize_remote_dir(remote_dir)
        source_path = source_path.strip()
        destination_path = destination_path.strip()
        if not source_path or not destination_path:
            return _build_robot_workspace_redirect(
                robot_name,
                "error",
                "Move failed: source and destination paths are required",
                remote_dir,
                selected_remote_path=source_path or None,
            )

        try:
            robot = registry.get_robot(robot_name)
            moved_path = manager_factory(robot).move_remote_path(source_path, destination_path)
            return _build_robot_workspace_redirect(
                robot_name,
                "success",
                f"Moved remote path to: {moved_path}",
                _parent_remote_dir(moved_path) or "/",
                selected_remote_path=moved_path,
            )
        except Exception as exc:
            return _build_robot_workspace_redirect(
                robot_name,
                "error",
                f"Move failed: {exc}",
                remote_dir,
                selected_remote_path=source_path,
            )

    @app.post("/robots/{robot_name}/files/copy")
    def copy_robot_workspace_file(
        robot_name: str,
        request: Request,
        remote_dir: str = Form(ROBOT_FILES_ROOT),
        source_path: str = Form(...),
        destination_path: str = Form(...),
    ) -> RedirectResponse:
        registry: RobotRegistry = request.app.state.registry
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )

        remote_dir = _normalize_remote_dir(remote_dir)
        source_path = source_path.strip()
        destination_path = destination_path.strip()
        if not source_path or not destination_path:
            return _build_robot_workspace_redirect(
                robot_name,
                "error",
                "Copy failed: source and destination paths are required",
                remote_dir,
                selected_remote_path=source_path or None,
            )

        try:
            robot = registry.get_robot(robot_name)
            copied_path = manager_factory(robot).copy_remote_file(source_path, destination_path)
            return _build_robot_workspace_redirect(
                robot_name,
                "success",
                f"Copied remote file to: {copied_path}",
                _parent_remote_dir(copied_path) or "/",
                selected_remote_path=copied_path,
            )
        except Exception as exc:
            return _build_robot_workspace_redirect(
                robot_name,
                "error",
                f"Copy failed: {exc}",
                remote_dir,
                selected_remote_path=source_path,
            )

    @app.post("/robots/{robot_name}/run-remote-script")
    def run_robot_workspace_remote_script(
        robot_name: str,
        request: Request,
        remote_dir: str = Form(ROBOT_FILES_ROOT),
        remote_path: str = Form(...),
    ) -> RedirectResponse:
        registry: RobotRegistry = request.app.state.registry
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )

        remote_dir = _normalize_remote_dir(remote_dir)
        remote_path = remote_path.strip()
        if not remote_path or not remote_path.endswith(".script"):
            return _build_robot_workspace_redirect(
                robot_name,
                "error",
                "Direct script run failed: select one .script file.",
                remote_dir,
                selected_remote_path=remote_path or None,
            )

        try:
            robot = registry.get_robot(robot_name)
            with tempfile.TemporaryDirectory(prefix="uam-gui-run-script-") as tmp_dir:
                pulled_path = manager_factory(robot).pull_remote_file(remote_path, tmp_dir)
                result = manager_factory(robot).run_script_file(pulled_path)
            request.app.state.latest_script_run[robot_name] = {
                "status": "success",
                "message": result,
                "remote_path": remote_path,
            }
            return _build_robot_workspace_redirect(
                robot_name,
                "success",
                f"Direct script run succeeded: {result}",
                remote_dir,
                selected_remote_path=remote_path,
            )
        except Exception as exc:
            request.app.state.latest_script_run[robot_name] = {
                "status": "error",
                "message": str(exc),
                "remote_path": remote_path,
            }
            return _build_robot_workspace_redirect(
                robot_name,
                "error",
                f"Direct script run failed: {exc}",
                remote_dir,
                selected_remote_path=remote_path,
            )

    @app.post("/api/robots/{robot_name}/actions/{action_name}")
    def robot_action(
        robot_name: str, action_name: str, request: Request
    ) -> JSONResponse:
        registry: RobotRegistry = request.app.state.registry
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )

        try:
            robot = registry.get_robot(robot_name)
        except RegistryError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        manager = manager_factory(robot)
        actions = _get_action_methods(manager)
        if action_name not in actions:
            raise HTTPException(status_code=404, detail=f"Unknown action: {action_name}")

        if action_name == "load":
            result = manager.validate_assigned_runtime_load()
            request.app.state.latest_load_validation[robot_name] = _stamp_load_validation(
                result.to_dict()
            )
            if result.outcome != "success":
                message = result.raw_dashboard_response or "; ".join(result.notes) or "Load failed."
                if result.assigned_runtime_path:
                    message = f"{message} Assigned runtime path: {result.assigned_runtime_path}."
                if result.derived_dashboard_load_argument:
                    message = (
                        f"{message} Derived dashboard load argument: "
                        f"{result.derived_dashboard_load_argument}."
                    )
                return JSONResponse(
                    status_code=400,
                    content={
                        "ok": False,
                        "robot_name": robot_name,
                        "action_name": action_name,
                        "action_label": ACTION_LABELS[action_name],
                        "message": message,
                        "runtime_validation": result.to_dict(),
                    },
                )
            return JSONResponse(
                {
                    "ok": True,
                    "robot_name": robot_name,
                    "action_name": action_name,
                    "action_label": ACTION_LABELS[action_name],
                    "message": result.raw_dashboard_response or "Loading program.",
                    "runtime_validation": result.to_dict(),
                }
            )

        if action_name == "play":
            latest_load_validation = request.app.state.latest_load_validation.get(robot_name)
            if latest_load_validation and not latest_load_validation.get("ready_for_play", False):
                message = (
                    f"Play blocked: last load outcome is '{latest_load_validation.get('outcome')}'. "
                    "Resolve load issue first."
                )
                last_response = str(latest_load_validation.get("raw_dashboard_response") or "").strip()
                if last_response:
                    message = f"{message} Last load response: {last_response}"
                elif latest_load_validation.get("notes"):
                    message = (
                        f"{message} "
                        f"{'; '.join(str(note) for note in latest_load_validation.get('notes') or [])}"
                    )
                return JSONResponse(
                    status_code=400,
                    content={
                        "ok": False,
                        "robot_name": robot_name,
                        "action_name": action_name,
                        "action_label": ACTION_LABELS[action_name],
                        "message": message,
                    },
                )

        try:
            result_message = actions[action_name]()
        except Exception as exc:
            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "robot_name": robot_name,
                    "action_name": action_name,
                    "action_label": ACTION_LABELS[action_name],
                    "message": str(exc),
                },
            )

        return JSONResponse(
            {
                "ok": True,
                "robot_name": robot_name,
                "action_name": action_name,
                "action_label": ACTION_LABELS[action_name],
                "message": result_message,
            }
        )

    def _render_library_workspace(
        request: Request,
        current_dir: str,
        selected_path: str | None = None,
        flash_kind: str | None = None,
        flash_message: str | None = None,
        bundle_import_preview: dict[str, Any] | None = None,
    ) -> HTMLResponse:
        library_manager: LibraryManager = request.app.state.library_manager
        registry: RobotRegistry = request.app.state.registry
        listing_error = None
        selected_entry = None
        selected_error = None
        robot_options, robot_options_error = _serialize_robot_options(registry)

        if selected_path:
            selected_path = str(selected_path).strip().strip("/")
            if selected_path and not current_dir:
                selected_parent = _parent_library_dir(selected_path)
                current_dir = selected_parent or ""

        try:
            raw_entries = library_manager.list_directory(current_dir)
            entries = [_serialize_library_entry(entry, current_dir) for entry in raw_entries]
        except Exception as exc:
            entries = []
            listing_error = str(exc)

        if selected_path:
            try:
                selected_entry = _serialize_library_entry(
                    library_manager.inspect_item_enriched(selected_path),
                    current_dir,
                )
                if selected_entry.get("is_dir") and selected_entry.get("bundle_summary"):
                    bundle_summary = selected_entry["bundle_summary"]
                    bundle_summary["runtime_name_warning"] = _runtime_name_safety_warning(
                        bundle_summary.get("primary_urp_path")
                    )
                elif selected_entry.get("extension") == "urp":
                    selected_entry["runtime_name_warning"] = _runtime_name_safety_warning(
                        selected_entry.get("library_path")
                    )
            except Exception as exc:
                selected_error = str(exc)

        if bundle_import_preview and bundle_import_preview.get("summary"):
            bundle_import_preview["summary"]["runtime_name_warning"] = _runtime_name_safety_warning(
                bundle_import_preview["summary"].get("primary_urp_path")
            )

        folder_count = sum(1 for entry in entries if entry["is_dir"])
        file_count = sum(1 for entry in entries if not entry["is_dir"])

        return templates.TemplateResponse(
            request,
            "library.html",
            {
                "title": "Library",
                "active_page": "library",
                "current_dir": current_dir,
                "current_dir_label": current_dir or "/",
                "parent_dir": _parent_library_dir(current_dir),
                "entries": entries,
                "selected_entry": selected_entry,
                "selected_error": selected_error,
                "listing_error": listing_error,
                "folder_count": folder_count,
                "file_count": file_count,
                "flash_kind": flash_kind,
                "flash_message": flash_message,
                "robot_options": robot_options,
                "robot_options_error": robot_options_error,
                "default_robot_remote_dir": ROBOT_FILES_ROOT,
                "bundle_import_preview": bundle_import_preview,
            },
        )

    @app.get("/library", response_class=HTMLResponse)
    def library(request: Request) -> HTMLResponse:
        selected_path = request.query_params.get("selected")
        current_dir = _normalize_library_dir(request.query_params.get("dir"))
        flash_kind = request.query_params.get("flash_kind")
        flash_message = request.query_params.get("flash_message")
        return _render_library_workspace(
            request,
            current_dir=current_dir,
            selected_path=selected_path,
            flash_kind=flash_kind,
            flash_message=flash_message,
        )

    @app.get("/transfer", response_class=HTMLResponse)
    def transfer(request: Request) -> HTMLResponse:
        registry: RobotRegistry = request.app.state.registry
        library_manager: LibraryManager = request.app.state.library_manager
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )
        flash_kind = request.query_params.get("flash_kind")
        flash_message = request.query_params.get("flash_message")
        selected_source = str(request.query_params.get("source_path") or "").strip().strip("/") or None
        selected_robot = str(request.query_params.get("robot_name") or "").strip() or None
        selected_remote_dir = _normalize_remote_dir(request.query_params.get("remote_dir"))
        selected_remote_path = str(request.query_params.get("selected_remote_path") or "").strip() or None

        robot_options, robot_options_error = _serialize_robot_options(registry)
        directory_sources, file_sources = _collect_transfer_sources(library_manager)
        source_options = [*directory_sources, *file_sources]
        selected_summary = None
        selected_error = None
        predicted_remote_primary_urp = None
        predicted_remote_target_path = None
        transfer_file_browser = None
        transfer_selected_remote_entry = None
        transfer_runtime_name_warning = None
        selected_source_meta = _find_transfer_source(source_options, selected_source)
        selected_source_classification = (
            selected_source_meta.get("classification")
            if selected_source_meta
            else None
        )
        selected_source_deployable = (
            bool(selected_source_meta.get("is_deployable"))
            if selected_source_meta
            else False
        )
        selected_source_block_reason = (
            selected_source_meta.get("deploy_block_reason")
            if selected_source_meta
            else None
        )
        nested_deploy_warning = None
        nested_deploy_detected = False

        if selected_source:
            try:
                selected_item = library_manager.inspect_item_enriched(selected_source)
                selected_summary = _serialize_library_entry(selected_item, "")
                bundle_summary = selected_summary.get("bundle_summary")
                if selected_summary.get("is_dir") and bundle_summary and selected_source_deployable:
                    primary_urp_path = str(bundle_summary.get("primary_urp_path") or "").strip()
                    bundle_path = str(bundle_summary.get("bundle_directory_path") or "").strip()
                    bundle_name = str(bundle_summary.get("bundle_name") or Path(bundle_path).name).strip()
                    predicted_remote_target_path = _join_remote_path(selected_remote_dir, bundle_name)
                    if Path(selected_remote_dir).name == bundle_name:
                        nested_deploy_detected = True
                        nested_deploy_warning = (
                            "Selected destination parent already matches bundle folder name. "
                            f"Deploying now would create nested path '{predicted_remote_target_path}/{bundle_name}'."
                        )
                    if primary_urp_path and bundle_path and bundle_name:
                        primary_rel = Path(primary_urp_path).relative_to(Path(bundle_path)).as_posix()
                        predicted_remote_primary_urp = _join_remote_path(predicted_remote_target_path, primary_rel)
                elif selected_summary.get("extension") == "urp":
                    predicted_remote_target_path = _join_remote_path(
                        selected_remote_dir, Path(selected_summary["library_path"]).name
                    )
                    predicted_remote_primary_urp = _join_remote_path(
                        selected_remote_dir, Path(selected_summary["library_path"]).name
                    )
                elif selected_summary.get("is_dir"):
                    predicted_remote_target_path = _join_remote_path(
                        selected_remote_dir, Path(selected_summary["library_path"]).name
                    )
            except Exception as exc:
                selected_error = str(exc)

        if selected_robot:
            try:
                robot = registry.get_robot(selected_robot)
                transfer_file_browser = _serialize_robot_file_browser(
                    robot, manager_factory, selected_remote_dir
                )
                selected_remote_dir = transfer_file_browser["current_dir"]
                transfer_selected_remote_entry = _serialize_selected_remote_entry(
                    transfer_file_browser, selected_remote_path
                )
            except RegistryError as exc:
                selected_error = str(exc)

        transfer_result = {
            "source_path": request.query_params.get("result_source_path"),
            "source_kind": request.query_params.get("result_source_kind"),
            "robot_name": request.query_params.get("result_robot_name"),
            "remote_target_path": request.query_params.get("result_remote_target_path"),
            "deployed_primary_urp": request.query_params.get("result_deployed_primary_urp"),
            "assignment_performed": _parse_bool_query(request.query_params.get("result_assignment_performed")),
            "assigned_runtime_path": request.query_params.get("result_assigned_runtime_path"),
            "previous_assigned_runtime_path": request.query_params.get("result_previous_assigned_runtime_path"),
            "validation_performed": _parse_bool_query(request.query_params.get("result_validation_performed")),
            "validation_outcome": request.query_params.get("result_validation_outcome"),
            "validation_response": request.query_params.get("result_validation_response"),
            "validation_derived_argument": request.query_params.get("result_validation_derived_argument"),
            "validation_ready_for_play": _parse_bool_query(
                request.query_params.get("result_validation_ready_for_play")
            ),
            "assignment_status": request.query_params.get("result_assignment_status"),
            "validation_status": request.query_params.get("result_validation_status"),
            "result_note": request.query_params.get("result_note"),
            "next_action": request.query_params.get("result_next_action"),
            "continue_url": request.query_params.get("continue_url"),
        }
        transfer_runtime_name_warning = (
            _runtime_name_safety_warning(predicted_remote_primary_urp)
            or _runtime_name_safety_warning(transfer_result.get("validation_derived_argument"))
            or _runtime_name_safety_warning(transfer_result.get("deployed_primary_urp"))
        )

        return templates.TemplateResponse(
            request,
            "transfer.html",
            {
                "title": "Transfer & Assignment",
                "active_page": "transfer",
                "flash_kind": flash_kind,
                "flash_message": flash_message,
                "directory_sources": directory_sources,
                "file_sources": file_sources,
                "source_options": source_options,
                "selected_source": selected_source,
                "selected_robot": selected_robot,
                "selected_summary": selected_summary,
                "selected_source_meta": selected_source_meta,
                "selected_source_classification": selected_source_classification,
                "selected_source_deployable": selected_source_deployable,
                "selected_source_block_reason": selected_source_block_reason,
                "selected_error": selected_error,
                "predicted_remote_target_path": predicted_remote_target_path,
                "predicted_remote_primary_urp": predicted_remote_primary_urp,
                "nested_deploy_detected": nested_deploy_detected,
                "nested_deploy_warning": nested_deploy_warning,
                "selected_remote_path": selected_remote_path,
                "transfer_file_browser": transfer_file_browser,
                "transfer_selected_remote_entry": transfer_selected_remote_entry,
                "transfer_runtime_name_warning": transfer_runtime_name_warning,
                "robot_options": robot_options,
                "robot_options_error": robot_options_error,
                "selected_remote_dir": selected_remote_dir or ROBOT_FILES_ROOT,
                "default_remote_dir": ROBOT_FILES_ROOT,
                "transfer_result": transfer_result,
            },
        )

    @app.post("/transfer/execute")
    def transfer_execute(
        request: Request,
        source_path: str = Form(...),
        robot_name: str = Form(...),
        remote_dir: str = Form(ROBOT_FILES_ROOT),
        assign_after_deploy: str | None = Form(None),
        validate_load_after_assign: str | None = Form(None),
        allow_nested_bundle_deploy: str | None = Form(None),
    ) -> RedirectResponse:
        registry: RobotRegistry = request.app.state.registry
        library_manager: LibraryManager = request.app.state.library_manager
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )

        source_path = source_path.strip().strip("/")
        robot_name = robot_name.strip()
        remote_dir = _normalize_remote_dir(remote_dir)
        if not source_path or not robot_name:
            return RedirectResponse(
                url=(
                    f"/transfer?{urlencode({'flash_kind': 'error', 'flash_message': 'Transfer failed: source and robot are required.', 'source_path': source_path, 'robot_name': robot_name, 'remote_dir': remote_dir})}"
                ),
                status_code=303,
            )

        try:
            selected_item = library_manager.inspect_item(source_path)
            robot = registry.get_robot(robot_name)
            manager = manager_factory(robot)
            previous_assigned_runtime_path = str(robot.assigned_program or "").strip()
            assign_status = "skipped"
            validation_status = "skipped"
            result_note = ""
            result_next_action = ""

            if selected_item.get("is_dir"):
                bundle = library_manager.inspect_bundle(source_path)
                primary_urp_path = bundle.get("primary_urp_path")
                if not primary_urp_path:
                    raise LibraryError("Selected bundle has no deterministic primary .urp.")
                bundle_name = str(bundle.get("bundle_name") or Path(source_path).name).strip()
                if Path(remote_dir).name == bundle_name and not allow_nested_bundle_deploy:
                    raise LibraryError(
                        "Selected destination parent already equals the bundle folder name. "
                        "This would create nested bundle path. Choose parent folder or explicitly allow nested deploy."
                    )
                local_bundle_dir = Path(selected_item["stored_path"])
                remote_bundle_dir = _join_remote_path(remote_dir, bundle_name)
                deploy_result = manager.deploy_local_bundle(local_bundle_dir, remote_bundle_dir)
                primary_rel = Path(primary_urp_path).relative_to(Path(source_path)).as_posix()
                remote_primary_urp = _join_remote_path(remote_bundle_dir, primary_rel)
                request.app.state.latest_deployed_primary_path[robot_name] = remote_primary_urp
                load_result = None
                if assign_after_deploy:
                    registry.assign_remote_program(robot_name, remote_primary_urp)
                    assign_status = "performed"
                    request.app.state.latest_load_validation.pop(robot_name, None)
                    if validate_load_after_assign:
                        load_result = manager.validate_assigned_runtime_load(
                            assigned_runtime_path=remote_primary_urp
                        )
                        validation_status = (
                            "blocked" if load_result.outcome == "unsafe_runtime_path" else "performed"
                        )
                        request.app.state.latest_load_validation[robot_name] = _stamp_load_validation(
                            load_result.to_dict()
                        )
                    else:
                        validation_status = "skipped"
                else:
                    assign_status = "skipped"
                    validation_status = "skipped"
                flash_kind_result = "success"
                flash_message_result = (
                    f"Bundle deployed to {robot_name}: {len(deploy_result['files'])} files."
                )
                if load_result and load_result.outcome == "unsafe_runtime_path":
                    flash_kind_result = "error"
                    flash_message_result = (
                        "Bundle deployed and assigned, but dashboard load validation was blocked "
                        "because derived load argument is runtime-unsafe."
                    )
                if assign_status == "skipped":
                    result_note = (
                        "Runtime assignment was not changed. "
                        "Dashboard load was not validated in this transfer. "
                        "Load will still use the previously assigned path."
                    )
                    result_next_action = "Assign runtime path before running dashboard Load."
                elif validation_status == "skipped":
                    result_note = "Dashboard load was not validated in this transfer."
                    result_next_action = "Run Load validation in Robot Workspace before Play."
                elif load_result and load_result.outcome == "success":
                    result_next_action = "Validation succeeded. Continue to Robot Workspace for Play."
                else:
                    result_next_action = "Resolve runtime validation issue before Play."
                params = {
                    "source_path": source_path,
                    "robot_name": robot_name,
                    "remote_dir": remote_bundle_dir,
                    "selected_remote_path": remote_primary_urp,
                    "flash_kind": flash_kind_result,
                    "flash_message": flash_message_result,
                    "result_source_path": source_path,
                    "result_source_kind": "bundle",
                    "result_robot_name": robot_name,
                    "result_remote_target_path": remote_bundle_dir,
                    "result_deployed_primary_urp": remote_primary_urp,
                    "result_assignment_performed": "1" if assign_after_deploy else "0",
                    "result_assigned_runtime_path": remote_primary_urp if assign_after_deploy else "",
                    "result_previous_assigned_runtime_path": previous_assigned_runtime_path,
                    "result_validation_performed": "1" if (assign_after_deploy and validate_load_after_assign) else "0",
                    "result_validation_outcome": load_result.outcome if load_result else "",
                    "result_validation_response": (
                        (
                            load_result.raw_dashboard_response
                            or "; ".join(load_result.notes)
                        )
                        if load_result
                        else ""
                    ),
                    "result_validation_derived_argument": (
                        load_result.derived_dashboard_load_argument if load_result else ""
                    ),
                    "result_validation_ready_for_play": (
                        "1" if (load_result and load_result.ready_for_play) else "0"
                    ),
                    "result_assignment_status": assign_status,
                    "result_validation_status": validation_status,
                    "result_note": result_note,
                    "result_next_action": result_next_action,
                    "continue_url": (
                        f"/robots/{robot_name}?{urlencode({'remote_dir': remote_bundle_dir, 'selected_remote_path': remote_primary_urp})}"
                    ),
                }
                return RedirectResponse(url=f"/transfer?{urlencode(params)}", status_code=303)

            local_source = library_manager.get_stored_file(source_path)
            remote_destination = _join_remote_path(remote_dir, local_source.name)
            saved_remote_path = manager.deploy_local_file(local_source, remote_destination)
            load_result = None
            if local_source.suffix.lower() == ".urp":
                request.app.state.latest_deployed_primary_path[robot_name] = saved_remote_path
                if assign_after_deploy:
                    registry.assign_remote_program(robot_name, saved_remote_path)
                    assign_status = "performed"
                    request.app.state.latest_load_validation.pop(robot_name, None)
                    if validate_load_after_assign:
                        load_result = manager.validate_assigned_runtime_load(
                            assigned_runtime_path=saved_remote_path
                        )
                        validation_status = (
                            "blocked" if load_result.outcome == "unsafe_runtime_path" else "performed"
                        )
                        request.app.state.latest_load_validation[robot_name] = _stamp_load_validation(
                            load_result.to_dict()
                        )
                    else:
                        validation_status = "skipped"
                else:
                    assign_status = "skipped"
                    validation_status = "skipped"
            else:
                assign_status = "skipped"
                validation_status = "skipped"

            flash_kind_result = "success"
            flash_message_result = f"File deployed to {robot_name}: {saved_remote_path}."
            if load_result and load_result.outcome == "unsafe_runtime_path":
                flash_kind_result = "error"
                flash_message_result = (
                    "File deployed and assigned, but dashboard load validation was blocked "
                    "because derived load argument is runtime-unsafe."
                )
            if assign_status == "skipped":
                result_note = (
                    "Runtime assignment was not changed. "
                    "Dashboard load was not validated in this transfer. "
                    "Load will still use the previously assigned path."
                )
                result_next_action = "Assign one deployed .urp before running dashboard Load."
            elif validation_status == "skipped":
                result_note = "Dashboard load was not validated in this transfer."
                result_next_action = "Run Load validation in Robot Workspace before Play."
            elif load_result and load_result.outcome == "success":
                result_next_action = "Validation succeeded. Continue to Robot Workspace for Play."
            else:
                result_next_action = "Resolve runtime validation issue before Play."

            params = {
                "source_path": source_path,
                "robot_name": robot_name,
                "remote_dir": _parent_remote_dir(saved_remote_path) or remote_dir,
                "selected_remote_path": saved_remote_path,
                "flash_kind": flash_kind_result,
                "flash_message": flash_message_result,
                "result_source_path": source_path,
                "result_source_kind": "file",
                "result_robot_name": robot_name,
                "result_remote_target_path": saved_remote_path,
                "result_deployed_primary_urp": saved_remote_path if local_source.suffix.lower() == ".urp" else "",
                "result_assignment_performed": (
                    "1"
                    if (assign_after_deploy and local_source.suffix.lower() == ".urp")
                    else "0"
                ),
                "result_previous_assigned_runtime_path": previous_assigned_runtime_path,
                "result_assigned_runtime_path": (
                    saved_remote_path
                    if (assign_after_deploy and local_source.suffix.lower() == ".urp")
                    else ""
                ),
                "result_validation_performed": (
                    "1"
                    if (
                        assign_after_deploy
                        and validate_load_after_assign
                        and local_source.suffix.lower() == ".urp"
                    )
                    else "0"
                ),
                "result_validation_outcome": load_result.outcome if load_result else "",
                "result_validation_response": (
                    (
                        load_result.raw_dashboard_response
                        or "; ".join(load_result.notes)
                    )
                    if load_result
                    else ""
                ),
                "result_validation_derived_argument": (
                    load_result.derived_dashboard_load_argument if load_result else ""
                ),
                "result_validation_ready_for_play": (
                    "1" if (load_result and load_result.ready_for_play) else "0"
                ),
                "result_assignment_status": assign_status,
                "result_validation_status": validation_status,
                "result_note": result_note,
                "result_next_action": result_next_action,
                "continue_url": (
                    f"/robots/{robot_name}?{urlencode({'remote_dir': _parent_remote_dir(saved_remote_path) or remote_dir, 'selected_remote_path': saved_remote_path})}"
                ),
            }
            return RedirectResponse(url=f"/transfer?{urlencode(params)}", status_code=303)
        except Exception as exc:
            return RedirectResponse(
                url=(
                    f"/transfer?{urlencode({'source_path': source_path, 'robot_name': robot_name, 'remote_dir': remote_dir, 'flash_kind': 'error', 'flash_message': f'Transfer failed: {exc}'})}"
                ),
                status_code=303,
            )

    @app.post("/library/upload")
    async def upload_library_item(
        request: Request,
        current_dir: str = Form(""),
        upload_file: list[UploadFile] = File([]),
    ) -> RedirectResponse:
        library_manager: LibraryManager = request.app.state.library_manager
        current_dir = _normalize_library_dir(current_dir)
        upload_files = list(upload_file)
        selected_uploads = [upload for upload in upload_files if getattr(upload, "filename", None)]
        if not selected_uploads:
            params = urlencode(
                {
                    "flash_kind": "error",
                    "flash_message": "Upload failed: no files selected",
                    "dir": current_dir,
                }
            )
            return RedirectResponse(url=f"/library?{params}", status_code=303)

        try:
            with tempfile.TemporaryDirectory(prefix="uam-gui-upload-") as tmp_dir:
                temp_paths: list[str] = []
                for upload in selected_uploads:
                    temp_path = Path(tmp_dir) / Path(upload.filename or "upload.bin").name
                    data = await upload.read()
                    temp_path.write_bytes(data)
                    temp_paths.append(str(temp_path))
                if len(temp_paths) == 1:
                    item = library_manager.add_item(
                        temp_paths[0],
                        target_dir=current_dir,
                    )
                    selected_path = item.get("library_path", item["program_id"])
                    flash_message = f"Uploaded to library: {selected_path}"
                else:
                    bundle = library_manager.add_bundle(
                        temp_paths,
                        target_dir=current_dir,
                    )
                    selected_path = bundle["bundle_directory_path"]
                    flash_message = (
                        f"Imported bundle: {selected_path} "
                        f"({bundle['file_count']} files, readiness: {bundle['readiness_state']})"
                    )
                    if bundle.get("primary_urp_was_normalized"):
                        flash_message = (
                            f"{flash_message}. Runtime-safe primary .urp rename: "
                            f"{bundle.get('primary_urp_original_filename')} -> "
                            f"{bundle.get('primary_urp_runtime_safe_filename')}"
                        )
        except Exception as exc:
            params = urlencode(
                {
                    "flash_kind": "error",
                    "flash_message": f"Upload failed: {exc}",
                    "dir": current_dir,
                }
            )
            return RedirectResponse(url=f"/library?{params}", status_code=303)
        finally:
            for upload in upload_files:
                await upload.close()

        params = urlencode(
            {
                "selected": selected_path,
                "dir": current_dir,
                "flash_kind": "success",
                "flash_message": flash_message,
            }
        )
        return RedirectResponse(url=f"/library?{params}", status_code=303)

    @app.post("/library/bundle-import/stage", response_class=HTMLResponse)
    async def stage_library_bundle_import(
        request: Request,
        current_dir: str = Form(""),
        bundle_name: str = Form(""),
        bundle_files: list[UploadFile] = File([]),
    ) -> HTMLResponse:
        library_manager: LibraryManager = request.app.state.library_manager
        stage_store: dict[str, dict[str, Any]] = request.app.state.bundle_import_staging
        current_dir = _normalize_library_dir(current_dir)

        upload_files = list(bundle_files)
        selected_uploads = [upload for upload in upload_files if getattr(upload, "filename", None)]

        if not selected_uploads:
            return _render_library_workspace(
                request,
                current_dir=current_dir,
                flash_kind="error",
                flash_message="Bundle import failed: select at least one file",
            )

        stage_token = uuid4().hex
        temp_dir = tempfile.mkdtemp(prefix="uam-gui-bundle-stage-")
        staged_paths: list[str] = []
        filenames: list[str] = []

        try:
            for upload in selected_uploads:
                filename = Path(str(upload.filename or "upload.bin")).name
                target = Path(temp_dir) / filename
                data = await upload.read()
                target.write_bytes(data)
                filenames.append(filename)
                staged_paths.append(str(target))
        finally:
            for upload in upload_files:
                await upload.close()

        try:
            preview_summary = library_manager.preview_bundle_import(
                filenames,
                target_dir=current_dir,
                bundle_name=bundle_name.strip() or None,
            )
        except Exception as exc:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return _render_library_workspace(
                request,
                current_dir=current_dir,
                flash_kind="error",
                flash_message=f"Bundle import failed: {exc}",
            )

        stage_store[stage_token] = {
            "temp_dir": temp_dir,
            "file_paths": staged_paths,
            "current_dir": current_dir,
            "bundle_name": bundle_name.strip() or "",
            "filenames": filenames,
        }

        return _render_library_workspace(
            request,
            current_dir=current_dir,
            bundle_import_preview={
                "token": stage_token,
                "current_dir": current_dir,
                "bundle_name": preview_summary.get("bundle_name"),
                "summary": preview_summary,
                "filenames": filenames,
            },
        )

    @app.post("/library/bundle-import/commit")
    def commit_library_bundle_import(
        request: Request,
        token: str = Form(...),
        current_dir: str = Form(""),
        bundle_name: str = Form(""),
    ) -> RedirectResponse:
        library_manager: LibraryManager = request.app.state.library_manager
        stage_store: dict[str, dict[str, Any]] = request.app.state.bundle_import_staging
        current_dir = _normalize_library_dir(current_dir)
        stage = stage_store.get(token)
        if not stage:
            return _build_library_redirect(
                "error",
                "Bundle import failed: staged upload expired. Please stage files again.",
                current_dir=current_dir,
            )

        staged_paths = [str(path) for path in stage.get("file_paths", [])]
        effective_dir = _normalize_library_dir(str(stage.get("current_dir") or current_dir))
        try:
            bundle = library_manager.add_bundle(
                staged_paths,
                target_dir=effective_dir,
                bundle_name=bundle_name.strip() or None,
            )
        except Exception as exc:
            _cleanup_bundle_import_stage(stage_store, token)
            return _build_library_redirect(
                "error",
                f"Bundle import failed: {exc}",
                current_dir=effective_dir,
            )

        _cleanup_bundle_import_stage(stage_store, token)
        flash_message = (
            f"Imported bundle: {bundle['bundle_directory_path']} "
            f"({bundle['file_count']} files, readiness: {bundle['readiness_state']})"
        )
        if bundle.get("primary_urp_was_normalized"):
            flash_message = (
                f"{flash_message}. Runtime-safe primary .urp rename: "
                f"{bundle.get('primary_urp_original_filename')} -> "
                f"{bundle.get('primary_urp_runtime_safe_filename')}"
            )
        return _build_library_redirect(
            "success",
            flash_message,
            selected=bundle["bundle_directory_path"],
            current_dir=effective_dir,
        )

    @app.post("/library/bundle-import/cancel")
    def cancel_library_bundle_import(
        request: Request,
        token: str = Form(...),
        current_dir: str = Form(""),
    ) -> RedirectResponse:
        stage_store: dict[str, dict[str, Any]] = request.app.state.bundle_import_staging
        _cleanup_bundle_import_stage(stage_store, token)
        return _build_library_redirect(
            "success",
            "Bundle import canceled.",
            current_dir=_normalize_library_dir(current_dir),
        )

    @app.post("/library/bundle-prepare-safe-copy")
    def prepare_runtime_safe_bundle_copy(
        request: Request,
        source_path: str = Form(...),
        current_dir: str = Form(""),
    ) -> RedirectResponse:
        library_manager: LibraryManager = request.app.state.library_manager
        current_dir = _normalize_library_dir(current_dir)
        source_path = source_path.strip().strip("/")
        if not source_path:
            return _build_library_redirect(
                "error",
                "Prepare runtime-safe copy failed: bundle path is required.",
                current_dir=current_dir,
            )
        try:
            bundle = library_manager.prepare_runtime_safe_bundle_copy(source_path)
            return _build_library_redirect(
                "success",
                (
                    f"Prepared runtime-safe copy: {bundle['bundle_directory_path']}. "
                    f"Primary .urp: {bundle.get('primary_urp_original_filename')} -> "
                    f"{bundle.get('primary_urp_runtime_safe_filename')}"
                ),
                selected=bundle["bundle_directory_path"],
                current_dir=current_dir,
            )
        except Exception as exc:
            return _build_library_redirect(
                "error",
                f"Prepare runtime-safe copy failed: {exc}",
                selected=source_path,
                current_dir=current_dir,
            )

    @app.post("/library/create-folder")
    def create_library_folder(
        request: Request,
        current_dir: str = Form(""),
        folder_name: str = Form(...),
    ) -> RedirectResponse:
        library_manager: LibraryManager = request.app.state.library_manager
        current_dir = _normalize_library_dir(current_dir)
        folder_name = folder_name.strip().strip("/")

        if not folder_name:
            return _build_library_redirect(
                "error",
                "Create folder failed: folder name is required",
                current_dir=current_dir,
            )

        target_path = _join_library_path(current_dir, folder_name)
        try:
            created = library_manager.create_folder(target_path)
            return _build_library_redirect(
                "success",
                f"Created folder: {created.get('library_path', created['program_id'])}",
                selected=created.get("library_path", created["program_id"]),
                current_dir=current_dir,
            )
        except Exception as exc:
            return _build_library_redirect(
                "error",
                f"Create folder failed: {exc}",
                current_dir=current_dir,
            )

    @app.post("/library/import-remote")
    def import_remote_library_item(
        request: Request,
        robot_name: str = Form(...),
        remote_path: str = Form(...),
    ) -> RedirectResponse:
        library_manager: LibraryManager = request.app.state.library_manager
        registry: RobotRegistry = request.app.state.registry
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )

        robot_name = robot_name.strip()
        remote_path = remote_path.strip()
        if not robot_name or not remote_path:
            params = urlencode(
                {
                    "flash_kind": "error",
                    "flash_message": "Import failed: robot and remote path are required",
                }
            )
            return RedirectResponse(url=f"/library?{params}", status_code=303)

        try:
            robot = registry.get_robot(robot_name)
            with tempfile.TemporaryDirectory(prefix="uam-gui-import-") as tmp_dir:
                pulled_path = manager_factory(robot).pull_remote_file(remote_path, tmp_dir)
                item = library_manager.add_item(
                    str(pulled_path),
                    target_dir="",
                    extra_metadata={
                        "origin": "robot_remote",
                        "source_robot": robot_name,
                        "source_remote_path": remote_path,
                    },
                )
        except Exception as exc:
            params = urlencode(
                {
                    "flash_kind": "error",
                    "flash_message": f"Import failed: {exc}",
                }
            )
            return RedirectResponse(url=f"/library?{params}", status_code=303)

        params = urlencode(
            {
                "selected": item.get("library_path", item["program_id"]),
                "flash_kind": "success",
                "flash_message": (
                    f"Imported from robot '{robot_name}': "
                    f"{remote_path} -> {item.get('library_path', item['program_id'])}"
                ),
            }
        )
        return RedirectResponse(url=f"/library?{params}", status_code=303)

    @app.post("/library/remove/{library_path:path}")
    def remove_library_item(
        library_path: str,
        request: Request,
        current_dir: str = Form(""),
    ) -> RedirectResponse:
        library_manager: LibraryManager = request.app.state.library_manager
        current_dir = _normalize_library_dir(current_dir)

        try:
            removed = library_manager.remove_item(library_path)
            return _build_library_redirect(
                "success",
                f"Removed library path: {removed.get('library_path', removed.get('program_id', library_path))}",
                current_dir=current_dir,
            )
        except Exception as exc:
            return _build_library_redirect(
                "error",
                f"Remove failed: {exc}",
                selected=library_path,
                current_dir=current_dir,
            )

    @app.post("/library/move")
    def move_library_item(
        request: Request,
        source_path: str = Form(...),
        destination_path: str = Form(...),
        current_dir: str = Form(""),
    ) -> RedirectResponse:
        library_manager: LibraryManager = request.app.state.library_manager
        current_dir = _normalize_library_dir(current_dir)
        source_path = source_path.strip().strip("/")
        destination_path = destination_path.strip().strip("/")

        if not source_path or not destination_path:
            return _build_library_redirect(
                "error",
                "Move failed: source and destination paths are required",
                selected=source_path or None,
                current_dir=current_dir,
            )

        try:
            moved = library_manager.move_item(source_path, destination_path)
            moved_path = moved.get("library_path", moved["program_id"])
            return _build_library_redirect(
                "success",
                f"Moved library path to: {moved_path}",
                selected=moved_path,
                current_dir=_parent_library_dir(moved_path) or "",
            )
        except Exception as exc:
            return _build_library_redirect(
                "error",
                f"Move failed: {exc}",
                selected=source_path,
                current_dir=current_dir,
            )

    @app.post("/library/copy")
    def copy_library_item(
        request: Request,
        source_path: str = Form(...),
        destination_path: str = Form(...),
        current_dir: str = Form(""),
    ) -> RedirectResponse:
        library_manager: LibraryManager = request.app.state.library_manager
        current_dir = _normalize_library_dir(current_dir)
        source_path = source_path.strip().strip("/")
        destination_path = destination_path.strip().strip("/")

        if not source_path or not destination_path:
            return _build_library_redirect(
                "error",
                "Copy failed: source and destination paths are required",
                selected=source_path or None,
                current_dir=current_dir,
            )

        try:
            copied = library_manager.copy_item(source_path, destination_path)
            copied_path = copied.get("library_path", copied["program_id"])
            return _build_library_redirect(
                "success",
                f"Copied library path to: {copied_path}",
                selected=copied_path,
                current_dir=_parent_library_dir(copied_path) or "",
            )
        except Exception as exc:
            return _build_library_redirect(
                "error",
                f"Copy failed: {exc}",
                selected=source_path,
                current_dir=current_dir,
            )

    @app.post("/library/send-to-robot")
    def send_library_item_to_robot(
        request: Request,
        source_path: str = Form(...),
        robot_name: str = Form(...),
        remote_dir: str = Form(ROBOT_FILES_ROOT),
        current_dir: str = Form(""),
        assign_after_deploy: str | None = Form(None),
    ) -> RedirectResponse:
        registry: RobotRegistry = request.app.state.registry
        library_manager: LibraryManager = request.app.state.library_manager
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )

        current_dir = _normalize_library_dir(current_dir)
        source_path = source_path.strip().strip("/")
        robot_name = robot_name.strip()
        remote_dir = _normalize_remote_dir(remote_dir)

        if not source_path or not robot_name:
            return _build_library_redirect(
                "error",
                "Send to robot failed: library file and target robot are required",
                selected=source_path or None,
                current_dir=current_dir,
            )

        try:
            selected_item = library_manager.inspect_item(source_path)
            robot = registry.get_robot(robot_name)
            manager = manager_factory(robot)
            if selected_item.get("is_dir"):
                bundle = library_manager.inspect_bundle(source_path)
                primary_urp_path = bundle.get("primary_urp_path")
                if not primary_urp_path:
                    raise LibraryError(
                        f"Bundle has no deployable primary .urp runtime candidate: {source_path}"
                    )
                local_bundle_dir = Path(selected_item["stored_path"])
                remote_bundle_dir = _join_remote_path(remote_dir, bundle["bundle_name"])
                deploy_result = manager.deploy_local_bundle(local_bundle_dir, remote_bundle_dir)
                primary_rel = Path(primary_urp_path).relative_to(Path(source_path)).as_posix()
                remote_primary_urp = _join_remote_path(remote_bundle_dir, primary_rel)
                request.app.state.latest_deployed_primary_path[robot_name] = remote_primary_urp
                assigned_note = ""
                if assign_after_deploy:
                    registry.assign_remote_program(robot_name, remote_primary_urp)
                    request.app.state.latest_load_validation.pop(robot_name, None)
                    assigned_note = " Assigned as runtime target."
                return _build_library_redirect(
                    "success",
                    (
                        f"Deployed bundle to robot '{robot_name}': {source_path} -> "
                        f"{remote_bundle_dir}; main URP: {remote_primary_urp}; "
                        f"{len(deploy_result['files'])} files deployed."
                        f"{assigned_note}"
                    ),
                    selected=source_path,
                    current_dir=current_dir,
                )

            local_source = library_manager.get_stored_file(source_path)
            remote_destination = _join_remote_path(remote_dir, local_source.name)
            saved_remote_path = manager.deploy_local_file(
                local_source, remote_destination
            )
            if str(selected_item.get("extension", "")).lower() == "urp":
                request.app.state.latest_deployed_primary_path[robot_name] = saved_remote_path
            return _build_library_redirect(
                "success",
                f"Sent to robot '{robot_name}': {source_path} -> {saved_remote_path}",
                selected=source_path,
                current_dir=current_dir,
            )
        except Exception as exc:
            return _build_library_redirect(
                "error",
                f"Send to robot failed: {exc}",
                selected=source_path,
                current_dir=current_dir,
            )

    @app.post("/library/assign-remote")
    def assign_remote_library_item(
        request: Request,
        robot_name: str = Form(...),
        robot_program_path: str = Form(...),
    ) -> RedirectResponse:
        registry: RobotRegistry = request.app.state.registry

        robot_name = robot_name.strip()
        robot_program_path = robot_program_path.strip()
        if not robot_name or not robot_program_path:
            return _build_library_redirect(
                "error",
                "Assign remote failed: robot and controller-visible path are required",
            )

        try:
            registry.assign_remote_program(robot_name, robot_program_path)
            request.app.state.latest_load_validation.pop(robot_name, None)
            return _build_library_redirect(
                "success",
                f"Assigned remote path to robot '{robot_name}': {robot_program_path}",
            )
        except Exception as exc:
            return _build_library_redirect("error", f"Assign remote failed: {exc}")

    @app.post("/library/assign-library")
    def assign_library_item(
        request: Request,
        robot_name: str = Form(...),
        program_id: str = Form(...),
    ) -> RedirectResponse:
        registry: RobotRegistry = request.app.state.registry
        library_manager: LibraryManager = request.app.state.library_manager

        robot_name = robot_name.strip()
        program_id = program_id.strip()
        if not robot_name or not program_id:
            return _build_library_redirect(
                "error",
                "Assign library failed: robot and library item are required",
                selected=program_id or None,
            )

        try:
            stored_filename = library_manager.get_stored_filename(program_id)
            assigned_program = f"/programs/{stored_filename}"
            registry.assign_remote_program(robot_name, assigned_program)
            request.app.state.latest_load_validation.pop(robot_name, None)
            return _build_library_redirect(
                "success",
                f"Assigned library item '{program_id}' to robot '{robot_name}' as {assigned_program}",
                selected=program_id,
            )
        except Exception as exc:
            return _build_library_redirect(
                "error",
                f"Assign library failed: {exc}",
                selected=program_id,
            )

    @app.post("/library/assign-script")
    def assign_script_item(
        request: Request,
        robot_name: str = Form(...),
        program_id: str = Form(...),
    ) -> RedirectResponse:
        registry: RobotRegistry = request.app.state.registry
        library_manager: LibraryManager = request.app.state.library_manager

        robot_name = robot_name.strip()
        program_id = program_id.strip()
        if not robot_name or not program_id:
            return _build_library_redirect(
                "error",
                "Assign script failed: robot and library item are required",
                selected=program_id or None,
            )

        try:
            library_manager.ensure_script_item(program_id)
            assigned_program = f"library://{program_id}"
            registry.assign_program(robot_name, assigned_program)
            request.app.state.latest_load_validation.pop(robot_name, None)
            return _build_library_redirect(
                "success",
                f"Assigned script '{program_id}' to robot '{robot_name}'",
                selected=program_id,
            )
        except Exception as exc:
            return _build_library_redirect(
                "error",
                f"Assign script failed: {exc}",
                selected=program_id,
            )

    @app.post("/library/deploy")
    def deploy_library_item(
        request: Request,
        robot_name: str = Form(...),
        program_id: str = Form(...),
        remote_dir: str = Form(ROBOT_FILES_ROOT),
    ) -> RedirectResponse:
        registry: RobotRegistry = request.app.state.registry
        library_manager: LibraryManager = request.app.state.library_manager
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )

        robot_name = robot_name.strip()
        program_id = program_id.strip()
        remote_dir = remote_dir.strip() or ROBOT_FILES_ROOT
        if not robot_name or not program_id:
            return _build_library_redirect(
                "error",
                "Deploy failed: robot and library item are required",
                selected=program_id or None,
            )

        try:
            robot = registry.get_robot(robot_name)
            source_file = library_manager.get_stored_file(program_id)
            remote_path = str(Path(remote_dir) / source_file.name).replace("\\", "/")
            saved_remote_path = manager_factory(robot).deploy_local_file(
                source_file, remote_path
            )
            if source_file.suffix.lower() == ".urp":
                request.app.state.latest_deployed_primary_path[robot_name] = saved_remote_path
            return _build_library_redirect(
                "success",
                f"Deployed '{program_id}' to robot '{robot_name}': {saved_remote_path}",
                selected=program_id,
            )
        except Exception as exc:
            return _build_library_redirect(
                "error",
                f"Deploy failed: {exc}",
                selected=program_id,
            )

    @app.post("/library/run-script")
    def run_script_library_item(
        request: Request,
        robot_name: str = Form(...),
        program_id: str = Form(...),
    ) -> RedirectResponse:
        registry: RobotRegistry = request.app.state.registry
        library_manager: LibraryManager = request.app.state.library_manager
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )

        robot_name = robot_name.strip()
        program_id = program_id.strip()
        if not robot_name or not program_id:
            return _build_library_redirect(
                "error",
                "Run script failed: robot and script item are required",
                selected=program_id or None,
            )

        try:
            robot = registry.get_robot(robot_name)
            library_manager.ensure_script_item(program_id)
            script_file = library_manager.get_stored_file(program_id)
            response = manager_factory(robot).run_script_file(script_file)
            return _build_library_redirect(
                "success",
                f"Run script succeeded for robot '{robot_name}': {response}",
                selected=program_id,
            )
        except Exception as exc:
            return _build_library_redirect(
                "error",
                f"Run script failed: {exc}",
                selected=program_id,
            )

    @app.post("/library/urp-set")
    def set_urp_param_library_item(
        request: Request,
        program_id: str = Form(...),
        param_name: str = Form(...),
        value: str = Form(...),
    ) -> RedirectResponse:
        library_manager: LibraryManager = request.app.state.library_manager

        program_id = program_id.strip()
        param_name = param_name.strip()
        value = value.strip()
        if not program_id or not param_name:
            return _build_library_redirect(
                "error",
                "Set URP param failed: program and param name are required",
                selected=program_id or None,
            )

        try:
            result = library_manager.set_urp_param(program_id, param_name, value)
            updated_value = result.get(param_name, value)
            return _build_library_redirect(
                "success",
                f"Updated URP param '{param_name}' for '{program_id}' to '{updated_value}'",
                selected=program_id,
            )
        except Exception as exc:
            return _build_library_redirect(
                "error",
                f"Set URP param failed: {exc}",
                selected=program_id,
            )

    @app.get("/system", response_class=HTMLResponse)
    def system(request: Request) -> HTMLResponse:
        registry: RobotRegistry = request.app.state.registry
        library_manager: LibraryManager = request.app.state.library_manager
        diagnostics = _serialize_system_diagnostics(registry, library_manager)
        return templates.TemplateResponse(
            request,
            "system.html",
            {
                "title": "System",
                "active_page": "system",
                "diagnostics": diagnostics,
            },
        )

    return app


app = create_app()


def main() -> None:
    uvicorn.run("ur_arms_manager.gui.app:app", host="127.0.0.1", port=8000)
