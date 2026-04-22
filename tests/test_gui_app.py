from pathlib import Path

from fastapi.testclient import TestClient

from ur_arms_manager.gui import app, create_app
from ur_arms_manager.models import RobotStatus
from ur_arms_manager.services.compatibility import CompatibilityResult
from ur_arms_manager.services.library_manager import LibraryError


client = TestClient(app)


class FakeRobotManager:
    statuses: dict[str, RobotStatus] = {}
    action_results: dict[tuple[str, str], str] = {}
    action_errors: dict[tuple[str, str], str] = {}
    calls: list[tuple[str, str]] = []
    remote_dirs: dict[tuple[str, str], list[str]] = {}
    remote_dir_errors: dict[tuple[str, str], str] = {}

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

    def play_program(self) -> str:
        return self._run_action("play")

    def stop_program(self) -> str:
        return self._run_action("stop")

    def pull_remote_file(self, remote_path: str, local_destination: str) -> Path:
        target = Path(local_destination) / Path(remote_path).name
        target.write_text("remote-payload", encoding="utf-8")
        return target

    def list_remote_files(self, remote_dir: str = "/programs") -> list[str]:
        key = (self.robot.name, remote_dir)
        if key in self.remote_dir_errors:
            raise RuntimeError(self.remote_dir_errors[key])
        return self.remote_dirs.get(key, [])

    def deploy_local_file(self, local_source: Path, remote_destination: str) -> str:
        self.calls.append(("deploy", f"{local_source.name}:{remote_destination}"))
        return remote_destination

    def run_script_file(self, local_script_path: Path) -> str:
        self.calls.append(("run-script", local_script_path.name))
        return f"Script sent from {local_script_path.name}"


class FakeLibraryManager:
    items: list[dict] = []
    inspect_errors: dict[str, str] = {}
    remove_errors: dict[str, str] = {}
    removed: list[str] = []
    add_error: str | None = None
    editable_params: dict[str, dict[str, str]] = {}
    editable_param_errors: dict[str, str] = {}
    set_param_errors: dict[tuple[str, str], str] = {}
    urp_analysis_by_id: dict[str, dict] = {}

    class _Storage:
        programs_root = Path("storage/programs")

        def list_program_ids(self):
            return []

    def __init__(self) -> None:
        self.storage = self._Storage()
        self.storage.list_program_ids = lambda: [item["program_id"] for item in self.items]

    def inspect_item(self, program_id: str) -> dict:
        if program_id in self.inspect_errors:
            raise LibraryError(self.inspect_errors[program_id])
        for item in self.items:
            if item["program_id"] == program_id:
                return item
        raise LibraryError(f"Library item not found: {program_id}")

    def remove_item(self, program_id: str) -> dict:
        if program_id in self.remove_errors:
            raise LibraryError(self.remove_errors[program_id])
        for item in list(self.items):
            if item["program_id"] == program_id:
                self.items.remove(item)
                self.removed.append(program_id)
                return item
        raise LibraryError(f"Library item not found: {program_id}")

    def add_item(self, local_file_path: str, extra_metadata: dict | None = None) -> dict:
        if self.add_error:
            raise LibraryError(self.add_error)
        source = Path(local_file_path)
        item = {
            "program_id": f"added-{len(self.items) + 1}",
            "original_filename": source.name,
            "extension": source.suffix.lstrip(".") or "unknown",
            "stored_path": f"storage/programs/added-{len(self.items) + 1}/{source.name}",
            "stored_file_exists": True,
            "origin": "local",
        }
        if extra_metadata:
            item.update(extra_metadata)
        self.items.append(item)
        return item

    def get_stored_filename(self, program_id: str) -> str:
        item = self.inspect_item(program_id)
        stored_path = item.get("stored_path")
        if stored_path:
            return Path(str(stored_path)).name
        raise LibraryError(f"Library item has no stored filename: {program_id}")

    def ensure_script_item(self, program_id: str) -> dict:
        item = self.inspect_item(program_id)
        if str(item.get("extension", "")).lower() != "script":
            raise LibraryError(f"Library item is not a .script program: {program_id}")
        return item

    def get_stored_file(self, program_id: str) -> Path:
        item = self.inspect_item(program_id)
        stored_path = item.get("stored_path")
        if not stored_path:
            raise LibraryError(f"Library item has no stored_path: {program_id}")
        if item.get("stored_file_exists") is False:
            raise LibraryError(f"Stored library file not found: {stored_path}")
        path = Path(str(stored_path))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("payload", encoding="utf-8")
        return path

    def inspect_item_enriched(self, program_id: str) -> dict:
        item = dict(self.inspect_item(program_id))
        if str(item.get("extension", "")).lower() == "urp":
            item["urp_analysis"] = self.urp_analysis_by_id.get(
                program_id,
                {"parse_success": False, "parse_error": "No test URP analysis configured"},
            )
        return item

    def ensure_urp_item(self, program_id: str) -> dict:
        item = self.inspect_item(program_id)
        if str(item.get("extension", "")).lower() != "urp":
            raise LibraryError(f"Library item is not a .urp program: {program_id}")
        return item

    def list_urp_editable_params(self, program_id: str) -> dict[str, str]:
        self.ensure_urp_item(program_id)
        if program_id in self.editable_param_errors:
            raise LibraryError(self.editable_param_errors[program_id])
        return dict(self.editable_params.get(program_id, {}))

    def set_urp_param(self, program_id: str, param_name: str, value: str) -> dict[str, str]:
        self.ensure_urp_item(program_id)
        key = (program_id, param_name)
        if key in self.set_param_errors:
            raise LibraryError(self.set_param_errors[key])
        params = self.editable_params.setdefault(program_id, {})
        if param_name not in params:
            raise LibraryError(f"Editable URP param not found: {param_name}")
        params[param_name] = value
        return dict(params)


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
    response = client.get("/")

    assert response.status_code == 200
    assert "UR Arms Manager" in response.text
    assert "Phase 1 GUI Foundation" in response.text
    assert "Robots" in response.text
    assert "Library" in response.text


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
    assigned_program: programs/demo_a.urp
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
            assigned_program="programs/demo_a.urp",
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
    assert "programs/demo_a.urp" in response.text
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
    assigned_program: programs/demo_a.urp
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
            assigned_program="programs/demo_a.urp",
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
    assigned_program: programs/demo_a.urp
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
            assigned_program="programs/demo_a.urp",
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
    assert payload["robot"]["assigned_program"] == "programs/demo_a.urp"


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
    FakeLibraryManager.items = [
        {
            "program_id": "demo-script-1",
            "original_filename": "demo.script",
            "extension": "script",
            "stored_path": str(tmp_path / "storage" / "programs" / "demo-script-1" / "demo.script"),
            "stored_file_exists": True,
        },
        {
            "program_id": "stale-urp-1",
            "original_filename": "stale.urp",
            "extension": "urp",
            "stored_path": str(tmp_path / "storage" / "programs" / "stale-urp-1" / "stale.urp"),
            "stored_file_exists": False,
        },
    ]
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
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
    assigned_program: programs/demo_a.urp
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
    assert "Stale Library Items" in response.text
    assert ">1<" in response.text


def test_system_page_renders_config_error_state(tmp_path: Path) -> None:
    FakeLibraryManager.items = []
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
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
    assigned_program: programs/demo_a.urp
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
    assigned_program: programs/demo_a.urp
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
            assigned_program="programs/demo_a.urp",
            monitoring_source="rtde",
        )
    }
    FakeRobotManager.remote_dirs = {
        ("robot1", "/programs"): ["jobs", "demo.urp"],
        ("robot1", "/programs/jobs"): ["nested.script"],
    }
    FakeRobotManager.remote_dir_errors = {
        ("robot1", "/programs/demo.urp"): "not a directory",
        ("robot1", "/programs/jobs/nested.script"): "not a directory",
    }
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.get("/robots/robot1")

    assert response.status_code == 200
    assert "Robot workspace for robot1." in response.text
    assert "127.0.0.1" in response.text
    assert "29991" in response.text
    assert "30021" in response.text
    assert "2222" in response.text
    assert "programs/demo_a.urp" in response.text
    assert "RUNNING" in response.text
    assert "PLAYING" in response.text
    assert "NORMAL" in response.text
    assert "rtde" in response.text
    assert "Power On" in response.text
    assert "Back to robot overview" in response.text
    assert "SSH/SFTP file browser" in response.text
    assert "/programs" in response.text
    assert "demo.urp" in response.text
    assert "jobs" in response.text
    assert "Import Selected File to Library" in response.text


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
    FakeRobotManager.remote_dirs = {}
    FakeRobotManager.remote_dir_errors = {
        ("robot1", "/programs"): "permission denied",
    }
    gui_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = gui_client.get("/robots/robot1")

    assert response.status_code == 200
    assert "File Browser Error" in response.text
    assert "permission denied" in response.text
    assert "Power On" in response.text


def test_robot_workspace_import_remote_file_redirects_to_library(tmp_path: Path) -> None:
    FakeLibraryManager.items = []
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
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
    FakeRobotManager.remote_dirs = {
        ("robot1", "/programs"): ["demo.urp"],
    }
    FakeRobotManager.remote_dir_errors = {
        ("robot1", "/programs/demo.urp"): "not a directory",
    }
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
    assert "Imported from robot &#39;robot1&#39;: added-1" in response.text
    assert "/programs/demo.urp" in response.text


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
    assigned_program: programs/demo_a.urp
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
    assigned_program: programs/demo_a.urp
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


def test_robot_action_endpoint_returns_not_found_for_unknown_robot(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text("robots: {}\n", encoding="utf-8")
    phase_a_client = TestClient(
        create_app(config_path=config_path, robot_manager_factory=FakeRobotManager)
    )

    response = phase_a_client.post("/api/robots/robot1/actions/play")

    assert response.status_code == 404


def test_library_page_renders_items_and_selected_detail(tmp_path: Path) -> None:
    FakeLibraryManager.items = [
        {
            "program_id": "demo-script-1",
            "original_filename": "demo.script",
            "extension": "script",
            "stored_path": str(tmp_path / "storage" / "programs" / "demo-script-1" / "demo.script"),
            "origin": "local",
            "created_at": "2026-04-16T10:00:00Z",
        },
        {
            "program_id": "demo-urp-1",
            "original_filename": "robot_job.urp",
            "extension": "urp",
            "stored_path": str(tmp_path / "storage" / "programs" / "demo-urp-1" / "robot_job.urp"),
            "origin": "robot_remote",
            "source_robot": "robot1",
            "source_remote_path": "/programs/robot_job.urp",
        },
    ]
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.removed = []
    FakeLibraryManager.add_error = None
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.get("/library?selected=demo-urp-1")

    assert response.status_code == 200
    assert "Managed program library." in response.text
    assert "demo.script" in response.text
    assert "robot_job.urp" in response.text
    assert "robot_remote" in response.text
    assert "/programs/robot_job.urp" in response.text
    assert ".script" in response.text
    assert ".urp" in response.text
    assert "Remove Item" in response.text


def test_library_page_renders_empty_state() -> None:
    FakeLibraryManager.items = []
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.get("/library")

    assert response.status_code == 200
    assert "Library is empty." in response.text


def test_library_page_tolerates_malformed_item_metadata() -> None:
    FakeLibraryManager.items = [
        {"program_id": "broken-item"},
    ]
    FakeLibraryManager.inspect_errors = {"broken-item": "manifest parse failed"}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.get("/library?selected=broken-item")

    assert response.status_code == 200
    assert "Unknown file" in response.text
    assert "manifest parse failed" in response.text


def test_library_page_shows_missing_stored_file_warning() -> None:
    FakeLibraryManager.items = [
        {
            "program_id": "stale-script-1",
            "original_filename": "stale.script",
            "extension": "script",
            "stored_path": "storage/programs/stale-script-1/stale.script",
            "stored_file_exists": False,
        }
    ]
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.get("/library?selected=stale-script-1")

    assert response.status_code == 200
    assert "Stored file is missing from library storage." in response.text
    assert "Missing from library storage" in response.text


def test_library_page_disables_script_forms_when_no_script_items(tmp_path: Path) -> None:
    FakeLibraryManager.items = [
        {
            "program_id": "demo-urp-1",
            "original_filename": "robot_job.urp",
            "extension": "urp",
            "stored_path": str(tmp_path / "storage" / "programs" / "demo-urp-1" / "robot_job.urp"),
            "stored_file_exists": True,
        }
    ]
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
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

    response = gui_client.get("/library?selected=demo-urp-1")

    assert response.status_code == 200
    assert "No `.script` items are currently available in the library." in response.text


def test_library_remove_redirects_with_success_feedback() -> None:
    FakeLibraryManager.items = [
        {
            "program_id": "demo-script-1",
            "original_filename": "demo.script",
            "extension": "script",
            "stored_path": "storage/programs/demo-script-1/demo.script",
        }
    ]
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.removed = []
    FakeLibraryManager.add_error = None
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post("/library/demo-script-1/remove", follow_redirects=True)

    assert response.status_code == 200
    assert "Removed library item: demo-script-1" in response.text
    assert FakeLibraryManager.removed == ["demo-script-1"]


def test_library_remove_redirects_with_error_feedback() -> None:
    FakeLibraryManager.items = [
        {
            "program_id": "demo-script-1",
            "original_filename": "demo.script",
            "extension": "script",
            "stored_path": "storage/programs/demo-script-1/demo.script",
        }
    ]
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {"demo-script-1": "remove blocked"}
    FakeLibraryManager.removed = []
    FakeLibraryManager.add_error = None
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post("/library/demo-script-1/remove", follow_redirects=True)

    assert response.status_code == 200
    assert "Remove failed: remove blocked" in response.text


def test_library_page_renders_ingest_forms(tmp_path: Path) -> None:
    FakeLibraryManager.items = [
        {
            "program_id": "demo-script-1",
            "original_filename": "demo.script",
            "extension": "script",
            "stored_path": "storage/programs/demo-script-1/demo.script",
        }
    ]
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
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

    response = gui_client.get("/library")

    assert response.status_code == 200
    assert "Upload Local File" in response.text
    assert "Import Remote File" in response.text
    assert "robot1 (127.0.0.1)" in response.text
    assert "Assign Remote" in response.text
    assert "Assign Library" in response.text
    assert "Assign Script" in response.text
    assert "Deploy" in response.text
    assert "Run Script" in response.text


def test_library_upload_redirects_with_success_feedback() -> None:
    FakeLibraryManager.items = []
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/upload",
        files={"upload_file": ("demo.script", b"def demo():\nend\n", "text/plain")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Uploaded to library: added-1" in response.text
    assert "demo.script" in response.text


def test_library_upload_redirects_with_error_feedback() -> None:
    FakeLibraryManager.items = []
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = "upload blocked"
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
        )
    )

    response = gui_client.post(
        "/library/upload",
        files={"upload_file": ("demo.script", b"def demo():\nend\n", "text/plain")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Upload failed: upload blocked" in response.text


def test_library_remote_import_redirects_with_success_feedback(tmp_path: Path) -> None:
    FakeLibraryManager.items = []
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
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
        "/library/import-remote",
        data={"robot_name": "robot1", "remote_path": "/programs/demo.urp"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Imported from robot &#39;robot1&#39;: added-1" in response.text
    assert "/programs/demo.urp" in response.text


def test_library_remote_import_redirects_with_error_feedback(tmp_path: Path) -> None:
    FakeLibraryManager.items = []
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
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
        "/library/import-remote",
        data={"robot_name": "robot1", "remote_path": "/programs/demo.urp"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Import failed:" in response.text


def test_library_assign_remote_redirects_with_success_feedback(tmp_path: Path) -> None:
    FakeLibraryManager.items = []
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    gui_client = TestClient(create_app(config_path=config_path, library_manager_factory=FakeLibraryManager, robot_manager_factory=FakeRobotManager))

    response = gui_client.post(
        "/library/assign-remote",
        data={"robot_name": "robot1", "robot_program_path": "programs/demo.urp"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Assigned remote path to robot &#39;robot1&#39;: programs/demo.urp" in response.text
    assert "programs/demo.urp" in config_path.read_text(encoding="utf-8")


def test_library_assign_library_redirects_with_success_feedback(tmp_path: Path) -> None:
    FakeLibraryManager.items = [
        {
            "program_id": "demo-urp-1",
            "original_filename": "robot_job.urp",
            "extension": "urp",
            "stored_path": "storage/programs/demo-urp-1/robot_job.urp",
        }
    ]
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    gui_client = TestClient(create_app(config_path=config_path, library_manager_factory=FakeLibraryManager, robot_manager_factory=FakeRobotManager))

    response = gui_client.post(
        "/library/assign-library",
        data={"robot_name": "robot1", "program_id": "demo-urp-1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Assigned library item &#39;demo-urp-1&#39; to robot &#39;robot1&#39;" in response.text
    assert "/programs/robot_job.urp" in config_path.read_text(encoding="utf-8")


def test_library_assign_script_rejects_non_script_item(tmp_path: Path) -> None:
    FakeLibraryManager.items = [
        {
            "program_id": "demo-urp-1",
            "original_filename": "robot_job.urp",
            "extension": "urp",
            "stored_path": "storage/programs/demo-urp-1/robot_job.urp",
        }
    ]
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    gui_client = TestClient(create_app(config_path=config_path, library_manager_factory=FakeLibraryManager, robot_manager_factory=FakeRobotManager))

    response = gui_client.post(
        "/library/assign-script",
        data={"robot_name": "robot1", "program_id": "demo-urp-1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Assign script failed:" in response.text
    assert "not a .script" in response.text


def test_library_deploy_redirects_with_success_feedback(tmp_path: Path) -> None:
    FakeLibraryManager.items = [
        {
            "program_id": "demo-script-1",
            "original_filename": "demo.script",
            "extension": "script",
            "stored_path": str(tmp_path / "storage" / "programs" / "demo-script-1" / "demo.script"),
        }
    ]
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeRobotManager.calls = []
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    gui_client = TestClient(create_app(config_path=config_path, library_manager_factory=FakeLibraryManager, robot_manager_factory=FakeRobotManager))

    response = gui_client.post(
        "/library/deploy",
        data={"robot_name": "robot1", "program_id": "demo-script-1", "remote_dir": "/custom_dir"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Deployed &#39;demo-script-1&#39; to robot &#39;robot1&#39;: /custom_dir/demo.script" in response.text


def test_library_run_script_redirects_with_success_feedback(tmp_path: Path) -> None:
    FakeLibraryManager.items = [
        {
            "program_id": "demo-script-1",
            "original_filename": "demo.script",
            "extension": "script",
            "stored_path": str(tmp_path / "storage" / "programs" / "demo-script-1" / "demo.script"),
        }
    ]
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeRobotManager.calls = []
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    gui_client = TestClient(create_app(config_path=config_path, library_manager_factory=FakeLibraryManager, robot_manager_factory=FakeRobotManager))

    response = gui_client.post(
        "/library/run-script",
        data={"robot_name": "robot1", "program_id": "demo-script-1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Run script succeeded for robot &#39;robot1&#39;" in response.text
    assert ("run-script", "demo.script") in FakeRobotManager.calls


def test_library_run_script_rejects_non_script_item(tmp_path: Path) -> None:
    FakeLibraryManager.items = [
        {
            "program_id": "demo-urp-1",
            "original_filename": "robot_job.urp",
            "extension": "urp",
            "stored_path": str(tmp_path / "storage" / "programs" / "demo-urp-1" / "robot_job.urp"),
        }
    ]
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: null
""".strip(),
        encoding="utf-8",
    )
    gui_client = TestClient(create_app(config_path=config_path, library_manager_factory=FakeLibraryManager, robot_manager_factory=FakeRobotManager))

    response = gui_client.post(
        "/library/run-script",
        data={"robot_name": "robot1", "program_id": "demo-urp-1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Run script failed:" in response.text
    assert "not a .script" in response.text


def test_library_page_renders_urp_detail_compatibility_and_safe_params(tmp_path: Path) -> None:
    FakeLibraryManager.items = [
        {
            "program_id": "demo-urp-1",
            "original_filename": "robot_job.urp",
            "extension": "urp",
            "stored_path": str(tmp_path / "storage" / "programs" / "demo-urp-1" / "robot_job.urp"),
            "origin": "local",
        }
    ]
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.editable_param_errors = {}
    FakeLibraryManager.set_param_errors = {}
    FakeLibraryManager.editable_params = {
        "demo-urp-1": {
            "installation_name": "cell_a",
            "pallet_rows": "4",
        }
    }
    FakeLibraryManager.urp_analysis_by_id = {
        "demo-urp-1": {
            "parse_success": True,
            "program_name": "robot_job",
            "installation_name": "cell_a",
            "polyscope_version": "5.15.0",
            "urcap_names": ["GripKit"],
            "contains_palletizing": True,
            "pallet_rows": "4",
        }
    }
    FakeCompatibilityService.errors = {}
    FakeCompatibilityService.results = {
        ("robot1", "demo-urp-1"): CompatibilityResult(
            overall_status="warning",
            summary="Compatibility check found warnings.",
            findings=["Installation dependency detected: cell_a"],
        )
    }
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
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
            compatibility_service_factory=FakeCompatibilityService,
        )
    )

    response = gui_client.get("/library?selected=demo-urp-1&compat_robot=robot1")

    assert response.status_code == 200
    assert "URP Detail" in response.text
    assert "robot_job" in response.text
    assert "GripKit" in response.text
    assert "Compatibility check found warnings." in response.text
    assert "Installation dependency detected: cell_a" in response.text
    assert "installation_name" in response.text
    assert "pallet_rows" in response.text
    assert "Set Safe Param" in response.text


def test_library_page_tolerates_urp_parse_failure_and_param_lookup_failure(tmp_path: Path) -> None:
    FakeLibraryManager.items = [
        {
            "program_id": "demo-urp-1",
            "original_filename": "robot_job.urp",
            "extension": "urp",
            "stored_path": str(tmp_path / "storage" / "programs" / "demo-urp-1" / "robot_job.urp"),
        }
    ]
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.urp_analysis_by_id = {
        "demo-urp-1": {
            "parse_success": False,
            "parse_error": "xml parse failed",
        }
    }
    FakeLibraryManager.editable_params = {}
    FakeLibraryManager.editable_param_errors = {"demo-urp-1": "param scan failed"}
    FakeLibraryManager.set_param_errors = {}
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
            compatibility_service_factory=FakeCompatibilityService,
        )
    )

    response = gui_client.get("/library?selected=demo-urp-1")

    assert response.status_code == 200
    assert "URP parse failed: xml parse failed" in response.text
    assert "Editable param lookup failed: param scan failed" in response.text


def test_library_set_urp_param_redirects_with_success_feedback(tmp_path: Path) -> None:
    FakeLibraryManager.items = [
        {
            "program_id": "demo-urp-1",
            "original_filename": "robot_job.urp",
            "extension": "urp",
            "stored_path": str(tmp_path / "storage" / "programs" / "demo-urp-1" / "robot_job.urp"),
        }
    ]
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.editable_param_errors = {}
    FakeLibraryManager.set_param_errors = {}
    FakeLibraryManager.editable_params = {
        "demo-urp-1": {
            "installation_name": "cell_a",
        }
    }
    FakeLibraryManager.urp_analysis_by_id = {
        "demo-urp-1": {
            "parse_success": True,
            "program_name": "robot_job",
        }
    }
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
            compatibility_service_factory=FakeCompatibilityService,
        )
    )

    response = gui_client.post(
        "/library/urp-set",
        data={
            "program_id": "demo-urp-1",
            "param_name": "installation_name",
            "value": "cell_b",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Updated URP param &#39;installation_name&#39; for &#39;demo-urp-1&#39; to &#39;cell_b&#39;" in response.text
    assert "cell_b" in response.text


def test_library_set_urp_param_rejects_invalid_param_value_update(tmp_path: Path) -> None:
    FakeLibraryManager.items = [
        {
            "program_id": "demo-urp-1",
            "original_filename": "robot_job.urp",
            "extension": "urp",
            "stored_path": str(tmp_path / "storage" / "programs" / "demo-urp-1" / "robot_job.urp"),
        }
    ]
    FakeLibraryManager.inspect_errors = {}
    FakeLibraryManager.remove_errors = {}
    FakeLibraryManager.add_error = None
    FakeLibraryManager.editable_param_errors = {}
    FakeLibraryManager.editable_params = {
        "demo-urp-1": {
            "installation_name": "cell_a",
        }
    }
    FakeLibraryManager.set_param_errors = {
        ("demo-urp-1", "installation_name"): "invalid installation value"
    }
    FakeLibraryManager.urp_analysis_by_id = {
        "demo-urp-1": {
            "parse_success": True,
            "program_name": "robot_job",
        }
    }
    gui_client = TestClient(
        create_app(
            library_manager_factory=FakeLibraryManager,
            robot_manager_factory=FakeRobotManager,
            compatibility_service_factory=FakeCompatibilityService,
        )
    )

    response = gui_client.post(
        "/library/urp-set",
        data={
            "program_id": "demo-urp-1",
            "param_name": "installation_name",
            "value": "bad!",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Set URP param failed: invalid installation value" in response.text
