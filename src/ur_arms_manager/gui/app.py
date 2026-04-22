from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
from typing import Any, Callable
from urllib.parse import urlencode

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


GUI_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = GUI_DIR / "templates"
STATIC_DIR = GUI_DIR / "static"
POLL_INTERVAL_MS = 2500
ROBOT_FILES_ROOT = "/programs"
ACTION_LABELS = {
    "power-on": "Power On",
    "brake-release": "Brake Release",
    "power-off": "Power Off",
    "load": "Load",
    "play": "Play",
    "stop": "Stop",
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
    return {
        "name": robot.name,
        "host": robot.host,
        "dashboard_port": robot.dashboard_port,
        "script_port": robot.script_port,
        "ssh_port": robot.ssh_port,
        "enabled": robot.enabled,
        "assigned_program": robot.assigned_program or "None assigned",
        "can_load": bool(robot.assigned_program),
        "actions_enabled": robot.enabled,
        "actions_disabled_reason": (
            None
            if robot.enabled
            else "Robot is disabled in config. Enable it before sending commands."
        ),
        "load_disabled_reason": (
            "Assign a robot-visible program path before using Load."
            if robot.enabled and not robot.assigned_program
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
) -> RedirectResponse:
    params: dict[str, str] = {
        "flash_kind": flash_kind,
        "flash_message": flash_message,
    }
    if selected:
        params["selected"] = selected
    return RedirectResponse(url=f"/library?{urlencode(params)}", status_code=303)


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
    entries: list[dict[str, str | bool]] = []

    try:
        names = manager.list_remote_files(current_dir)
        for name in names:
            remote_path = _join_remote_path(current_dir, name)
            try:
                manager.list_remote_files(remote_path)
                entry_kind = "directory"
                entry_label = "Directory"
            except Exception:
                entry_kind = "file"
                entry_label = "File"
            entries.append(
                {
                    "name": name,
                    "remote_path": remote_path,
                    "kind": entry_kind,
                    "kind_label": entry_label,
                }
            )
    except Exception as exc:
        listing_error = str(exc)

    return {
        "current_dir": current_dir,
        "parent_dir": _parent_remote_dir(current_dir),
        "entries": entries,
        "listing_error": listing_error,
    }


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

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "title": "Dashboard",
                "active_page": "home",
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
        selected_remote_path = request.query_params.get("selected_remote_path")
        flash_kind = request.query_params.get("flash_kind")
        flash_message = request.query_params.get("flash_message")
        remote_dir = _normalize_remote_dir(request.query_params.get("remote_dir"))

        try:
            robot = registry.get_robot(robot_name)
            robot_card = _serialize_robot_card(robot, manager_factory)
            file_browser = _serialize_robot_file_browser(robot, manager_factory, remote_dir)
        except RegistryError as exc:
            error_message = str(exc)

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
                "flash_kind": flash_kind,
                "flash_message": flash_message,
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
                    "status": robot_card["status"],
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
            params = urlencode(
                {
                    "remote_dir": remote_dir,
                    "flash_kind": "error",
                    "flash_message": "Import failed: no remote file was selected",
                }
            )
            return RedirectResponse(
                url=f"/robots/{robot_name}?{params}",
                status_code=303,
            )

        try:
            robot = registry.get_robot(robot_name)
            with tempfile.TemporaryDirectory(prefix="uam-gui-robot-import-") as tmp_dir:
                pulled_path = manager_factory(robot).pull_remote_file(remote_path, tmp_dir)
                item = library_manager.add_item(
                    str(pulled_path),
                    extra_metadata={
                        "origin": "robot_remote",
                        "source_robot": robot_name,
                        "source_remote_path": remote_path,
                    },
                )
        except Exception as exc:
            params = urlencode(
                {
                    "remote_dir": remote_dir,
                    "selected_remote_path": remote_path,
                    "flash_kind": "error",
                    "flash_message": f"Import failed: {exc}",
                }
            )
            return RedirectResponse(
                url=f"/robots/{robot_name}?{params}",
                status_code=303,
            )

        params = urlencode(
            {
                "selected": item["program_id"],
                "flash_kind": "success",
                "flash_message": f"Imported from robot '{robot_name}': {item['program_id']}",
            }
        )
        return RedirectResponse(url=f"/library?{params}", status_code=303)

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

    @app.get("/library", response_class=HTMLResponse)
    def library(request: Request) -> HTMLResponse:
        library_manager: LibraryManager = request.app.state.library_manager
        registry: RobotRegistry = request.app.state.registry
        compatibility_factory = request.app.state.compatibility_service_factory
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )
        selected_program_id = request.query_params.get("selected")
        compatibility_robot_name = request.query_params.get("compat_robot")
        flash_kind = request.query_params.get("flash_kind")
        flash_message = request.query_params.get("flash_message")
        robot_options: list[dict[str, str]] = []
        robot_config_error = None
        compatibility_result: CompatibilityResult | None = None
        compatibility_error: str | None = None
        editable_params: dict[str, str] = {}
        editable_params_error: str | None = None

        try:
            robot_options = [
                {"name": robot.name, "host": robot.host}
                for robot in registry.list_robots().values()
            ]
        except RegistryError as exc:
            robot_config_error = str(exc)

        items = _serialize_library_items(library_manager)
        selected_item = _build_selected_library_item(
            library_manager, items, selected_program_id
        )

        if (
            selected_item
            and selected_item.get("extension") == "urp"
            and not selected_item.get("error")
        ):
            try:
                editable_params = library_manager.list_urp_editable_params(
                    selected_item["program_id"]
                )
            except Exception as exc:
                editable_params_error = str(exc)

            if compatibility_robot_name:
                try:
                    robot = registry.get_robot(compatibility_robot_name)
                    compatibility_service = (
                        compatibility_factory(library_manager, manager_factory)
                        if compatibility_factory is not None
                        else CompatibilityService(library_manager, manager_factory)
                    )
                    compatibility_result = compatibility_service.evaluate(
                        robot, selected_item["program_id"]
                    )
                except Exception as exc:
                    compatibility_error = str(exc)

        return templates.TemplateResponse(
            request,
            "library.html",
            {
                "title": "Library",
                "active_page": "library",
                "library_items": items,
                "selected_item": selected_item,
                "flash_kind": flash_kind,
                "flash_message": flash_message,
                "robot_options": robot_options,
                "robot_config_error": robot_config_error,
                "compatibility_robot_name": compatibility_robot_name,
                "compatibility_result": compatibility_result,
                "compatibility_error": compatibility_error,
                "editable_params": editable_params,
                "editable_params_error": editable_params_error,
            },
        )

    @app.post("/library/upload")
    async def upload_library_item(
        request: Request, upload_file: UploadFile = File(...)
    ) -> RedirectResponse:
        library_manager: LibraryManager = request.app.state.library_manager

        if not upload_file.filename:
            params = urlencode(
                {
                    "flash_kind": "error",
                    "flash_message": "Upload failed: no file selected",
                }
            )
            return RedirectResponse(url=f"/library?{params}", status_code=303)

        try:
            with tempfile.TemporaryDirectory(prefix="uam-gui-upload-") as tmp_dir:
                temp_path = Path(tmp_dir) / Path(upload_file.filename).name
                data = await upload_file.read()
                temp_path.write_bytes(data)
                item = library_manager.add_item(str(temp_path))
        except Exception as exc:
            params = urlencode(
                {
                    "flash_kind": "error",
                    "flash_message": f"Upload failed: {exc}",
                }
            )
            return RedirectResponse(url=f"/library?{params}", status_code=303)
        finally:
            await upload_file.close()

        params = urlencode(
            {
                "selected": item["program_id"],
                "flash_kind": "success",
                "flash_message": f"Uploaded to library: {item['program_id']}",
            }
        )
        return RedirectResponse(url=f"/library?{params}", status_code=303)

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
                "selected": item["program_id"],
                "flash_kind": "success",
                "flash_message": f"Imported from robot '{robot_name}': {item['program_id']}",
            }
        )
        return RedirectResponse(url=f"/library?{params}", status_code=303)

    @app.post("/library/{program_id}/remove")
    def remove_library_item(program_id: str, request: Request) -> RedirectResponse:
        library_manager: LibraryManager = request.app.state.library_manager

        try:
            removed = library_manager.remove_item(program_id)
            return _build_library_redirect(
                "success",
                f"Removed library item: {removed.get('program_id', program_id)}",
            )
        except Exception as exc:
            return _build_library_redirect(
                "error",
                f"Remove failed: {exc}",
                selected=program_id,
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
        remote_dir: str = Form("/programs"),
    ) -> RedirectResponse:
        registry: RobotRegistry = request.app.state.registry
        library_manager: LibraryManager = request.app.state.library_manager
        manager_factory: Callable[[RobotConfig], RobotManager] = (
            request.app.state.robot_manager_factory
        )

        robot_name = robot_name.strip()
        program_id = program_id.strip()
        remote_dir = remote_dir.strip() or "/programs"
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
