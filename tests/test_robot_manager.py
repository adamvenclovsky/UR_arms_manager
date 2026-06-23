from __future__ import annotations

from pathlib import Path

from ur_arms_manager.models import RobotConfig
from ur_arms_manager.services import robot_manager


def _robot(assigned_program: str | None = "/programs/demo.urp") -> RobotConfig:
    return RobotConfig(
        name="robot1",
        host="127.0.0.1",
        dashboard_port=29999,
        script_port=30001,
        enabled=True,
        assigned_program=assigned_program,
    )


def test_disabled_robot_blocks_every_command_channel(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []

    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

        def __getattr__(self, name: str):
            def called(*_args, **_kwargs):
                calls.append(name)
                return "unexpected"

            return called

    class FakeScriptClient:
        def __init__(self, _host: str, _port: int):
            pass

        def send_program(self, _text: str) -> None:
            calls.append("script")

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    monkeypatch.setattr(robot_manager, "ScriptClient", FakeScriptClient)
    robot = _robot()
    robot.enabled = False
    manager = robot_manager.RobotManager(robot)
    script = tmp_path / "demo.script"
    script.write_text("def demo():\nend\n", encoding="utf-8")

    commands = (
        manager.power_on,
        manager.brake_release,
        manager.power_off,
        manager.load_assigned_program,
        manager.play_program,
        manager.pause_program,
        manager.stop_program,
        manager.move_home,
        lambda: manager.list_remote_files("/programs"),
        lambda: manager.run_script_file(script),
    )
    for command in commands:
        try:
            command()
            assert False, "Expected disabled robot command to be blocked"
        except RuntimeError as exc:
            assert "disabled in configuration" in str(exc)

    assert calls == []


def test_play_is_single_shot_and_does_not_clear_safety_state(monkeypatch) -> None:
    calls: list[str] = []

    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

        def play(self) -> str:
            calls.append("play")
            return "Failed to execute: play"

        def unlock_protective_stop(self) -> str:
            calls.append("unlock")
            return "unlocked"

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)

    try:
        robot_manager.RobotManager(_robot()).play_program()
        assert False, "Expected rejected Play"
    except RuntimeError:
        pass

    assert calls == ["play"]


def test_load_assigned_program_calls_dashboard(monkeypatch) -> None:
    class FakeDashboardClient:
        def __init__(self, host: str, port: int):
            assert host == "127.0.0.1"
            assert port == 29999

        def load(self, program_path: str) -> str:
            assert program_path == "programs/demo.urp"
            return "Loading program: programs/demo.urp"

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    manager = robot_manager.RobotManager(_robot())

    result = manager.load_assigned_program()

    assert result == "Loading program: programs/demo.urp"


def test_load_assigned_program_rejects_parser_error_response(monkeypatch) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

        def load(self, _program_path: str) -> str:
            return "could not understand: 'load programs/demo.urp'"

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    manager = robot_manager.RobotManager(_robot())

    try:
        manager.load_assigned_program()
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "Load rejected" in str(exc)
        assert "could not understand" in str(exc)


def test_validate_assigned_runtime_load_returns_structured_result(monkeypatch) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

        def load(self, program_path: str) -> str:
            assert program_path == "programs/demo.urp"
            return "Loading program: programs/demo.urp"

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    manager = robot_manager.RobotManager(_robot())

    result = manager.validate_assigned_runtime_load()

    assert result.robot_name == "robot1"
    assert result.assigned_runtime_path == "/programs/demo.urp"
    assert result.derived_dashboard_load_argument == "programs/demo.urp"
    assert result.outcome == "success"
    assert result.ready_for_play is True


def test_validate_assigned_runtime_load_uses_ursim_relative_argument(monkeypatch) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

        def load(self, program_path: str) -> str:
            assert program_path == "bundle/main.urp"
            return "Loading program: bundle/main.urp"

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    manager = robot_manager.RobotManager(
        _robot(assigned_program="/ursim/programs.UR5/bundle/main.urp")
    )

    result = manager.validate_assigned_runtime_load()

    assert result.derived_dashboard_load_argument == "bundle/main.urp"
    assert result.outcome == "success"


def test_validate_assigned_runtime_load_rejects_unknown_absolute_path_strategy(monkeypatch) -> None:
    called = {"load_called": False}

    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

        def load(self, _program_path: str) -> str:
            called["load_called"] = True
            return "should not happen"

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    manager = robot_manager.RobotManager(_robot(assigned_program="/tmp/demo/main.urp"))

    result = manager.validate_assigned_runtime_load()

    assert called["load_called"] is False
    assert result.outcome == "path_strategy_unknown"
    assert result.ready_for_play is False


def test_validate_assigned_runtime_load_blocks_unsafe_runtime_argument(monkeypatch) -> None:
    called = {"load_called": False}

    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

        def load(self, _program_path: str) -> str:
            called["load_called"] = True
            return "should not happen"

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    manager = robot_manager.RobotManager(
        _robot(assigned_program="/ursim/programs.UR5/jobs/my program.urp")
    )

    result = manager.validate_assigned_runtime_load()

    assert called["load_called"] is False
    assert result.outcome == "unsafe_runtime_path"
    assert result.ready_for_play is False
    assert result.derived_dashboard_load_argument == "jobs/my program.urp"


def test_validate_assigned_runtime_load_classifies_file_not_found(monkeypatch) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

        def load(self, _program_path: str) -> str:
            return "File not found: programs/missing.urp"

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    manager = robot_manager.RobotManager(_robot())

    result = manager.validate_assigned_runtime_load()

    assert result.outcome == "file_not_found"
    assert result.ready_for_play is False


def test_load_assigned_program_requires_assignment(monkeypatch) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    manager = robot_manager.RobotManager(_robot(assigned_program=None))

    try:
        manager.load_assigned_program()
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "has no assigned program" in str(exc)


def test_load_assigned_program_rejects_library_marker(monkeypatch) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    manager = robot_manager.RobotManager(_robot(assigned_program="library://uploaded/demo.script"))

    try:
        manager.load_assigned_program()
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "library marker" in str(exc)


def test_load_assigned_program_rejects_non_remote_path(monkeypatch) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    manager = robot_manager.RobotManager(_robot(assigned_program="programs/demo.urp"))

    try:
        manager.load_assigned_program()
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "real robot-side path" in str(exc)


def test_play_and_stop_wrap_dashboard_failures(monkeypatch) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

        def play(self) -> str:
            raise RuntimeError("connection refused")

        def stop(self) -> str:
            raise RuntimeError("timeout")

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    manager = robot_manager.RobotManager(_robot())

    try:
        manager.play_program()
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "Play failed" in str(exc)

    try:
        manager.stop_program()
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "Stop failed" in str(exc)


def test_move_home_loads_and_starts_configured_home_program(monkeypatch) -> None:
    calls: list[tuple[str, str | None]] = []

    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

        def load(self, program_path: str) -> str:
            calls.append(("load", program_path))
            return f"Loading program: {program_path}"

        def play(self) -> str:
            calls.append(("play", None))
            return "Starting program"

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    robot = _robot()
    robot.home_program = "/programs/go_home.urp"
    manager = robot_manager.RobotManager(robot)

    result = manager.move_home()

    assert calls == [("load", "programs/go_home.urp"), ("play", None)]
    assert "Home program loaded and started" in result


def test_play_wraps_dashboard_rejection_response(monkeypatch) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

        def play(self) -> str:
            return "Failed to execute: play"

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    manager = robot_manager.RobotManager(_robot())

    try:
        manager.play_program()
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        message = str(exc)
        assert "Play failed" in message
        assert "Dashboard rejected Play" in message
        assert "Failed to execute: play" in message


def test_play_rejection_explains_disabled_remote_control(monkeypatch) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

        def play(self) -> str:
            return "Failed to execute: play"

        def get_robotmode(self) -> str:
            return "Robotmode: RUNNING"

        def get_safety_status(self) -> str:
            return "Safetystatus: NORMAL"

        def get_program_state(self) -> str:
            return "STOPPED final.urp"

        def is_in_remote_control(self) -> str:
            return "false"

        def get_loaded_program(self) -> str:
            return "Loaded program: /programs/final.urp"

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    manager = robot_manager.RobotManager(_robot())

    try:
        manager.play_program()
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "Remote Control is disabled" in str(exc)
        assert "Automove confirmation" in str(exc)


def test_power_commands_call_dashboard(monkeypatch) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

        def power_on(self) -> str:
            return "Powering on"

        def brake_release(self) -> str:
            return "Brake releasing"

        def power_off(self) -> str:
            return "Powering off"

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    manager = robot_manager.RobotManager(_robot())

    assert manager.power_on() == "Powering on"
    assert manager.brake_release() == "Brake releasing"
    assert manager.power_off() == "Powering off"


def test_status_unreachable_returns_clean_result(monkeypatch) -> None:
    def fake_get_robot_monitoring_status(robot, dashboard_client):
        assert robot.name == "robot1"
        assert dashboard_client is not None
        return robot_manager.RobotStatus(
            name="robot1",
            connected=False,
            assigned_program=robot.assigned_program,
            detail="network unreachable",
            monitoring_source="dashboard",
        )

    monkeypatch.setattr(
        robot_manager, "get_robot_monitoring_status", fake_get_robot_monitoring_status
    )
    monkeypatch.setattr(
        robot_manager, "DashboardClient", lambda _host, _port: object()
    )
    manager = robot_manager.RobotManager(_robot())

    status = manager.status()

    assert status.connected is False
    assert status.detail == "network unreachable"


def test_list_remote_files_uses_default_programs_dir(monkeypatch) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

    class FakeFileClient:
        def __init__(self, **kwargs):
            assert kwargs["host"] == "127.0.0.1"
            assert kwargs["port"] == 22
            assert kwargs["username"] == "root"
            assert kwargs["password"] == ""

        def list_dir(self, remote_dir: str) -> list[str]:
            assert remote_dir == "/programs"
            return ["a.urp", "b.urp"]

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    monkeypatch.setattr(robot_manager, "FileClient", FakeFileClient)
    manager = robot_manager.RobotManager(_robot())

    files = manager.list_remote_files()

    assert files == ["a.urp", "b.urp"]


def test_list_remote_entries_returns_file_manager_metadata(monkeypatch) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

    class FakeFileClient:
        def __init__(self, **_kwargs):
            pass

        def list_dir_entries(self, remote_dir: str) -> list[dict[str, str | bool]]:
            assert remote_dir == "/programs"
            return [
                {"name": "job.urp", "is_dir": False, "kind": "file"},
                {"name": "subdir", "is_dir": True, "kind": "directory"},
            ]

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    monkeypatch.setattr(robot_manager, "FileClient", FakeFileClient)
    manager = robot_manager.RobotManager(_robot())

    entries = manager.list_remote_entries()

    assert entries[0]["name"] == "job.urp"
    assert entries[1]["is_dir"] is True


def test_remote_file_exists_calls_file_client(monkeypatch) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

    class FakeFileClient:
        def __init__(self, **_kwargs):
            pass

        def exists(self, remote_path: str) -> bool:
            return remote_path == "/programs/x.urp"

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    monkeypatch.setattr(robot_manager, "FileClient", FakeFileClient)
    manager = robot_manager.RobotManager(_robot())

    assert manager.remote_file_exists("/programs/x.urp") is True
    assert manager.remote_file_exists("/programs/y.urp") is False


def test_pull_remote_file_uses_basename_when_destination_is_directory(
    tmp_path: Path, monkeypatch
) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

    captured: dict[str, Path] = {}

    class FakeFileClient:
        def __init__(self, **_kwargs):
            pass

        def pull_file(self, remote_path: str, local_destination: Path) -> Path:
            assert remote_path == "/programs/sub/demo.urp"
            captured["dest"] = local_destination
            return local_destination

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    monkeypatch.setattr(robot_manager, "FileClient", FakeFileClient)
    manager = robot_manager.RobotManager(_robot())

    destination_dir = tmp_path / "downloads"
    destination_dir.mkdir(parents=True, exist_ok=True)
    result = manager.pull_remote_file("/programs/sub/demo.urp", str(destination_dir))

    assert result == destination_dir / "demo.urp"
    assert captured["dest"] == destination_dir / "demo.urp"


def test_pull_remote_file_uses_basename_when_destination_has_trailing_slash(
    tmp_path: Path, monkeypatch
) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

    captured: dict[str, Path] = {}

    class FakeFileClient:
        def __init__(self, **_kwargs):
            pass

        def pull_file(self, remote_path: str, local_destination: Path) -> Path:
            assert remote_path == "/programs/sub/demo.urp"
            captured["dest"] = local_destination
            return local_destination

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    monkeypatch.setattr(robot_manager, "FileClient", FakeFileClient)
    manager = robot_manager.RobotManager(_robot())

    destination_as_dir = str(tmp_path / "downloads") + "/"
    result = manager.pull_remote_file("/programs/sub/demo.urp", destination_as_dir)

    assert result == tmp_path / "downloads" / "demo.urp"
    assert captured["dest"] == tmp_path / "downloads" / "demo.urp"


def test_deploy_local_file_calls_upload(monkeypatch, tmp_path: Path) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

    class FakeFileClient:
        def __init__(self, **_kwargs):
            pass

        def upload_file(self, local_source: Path, remote_destination: str) -> str:
            assert local_source.name == "demo.urp"
            assert remote_destination == "/programs/demo.urp"
            return remote_destination

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    monkeypatch.setattr(robot_manager, "FileClient", FakeFileClient)
    manager = robot_manager.RobotManager(_robot())

    local_file = tmp_path / "demo.urp"
    local_file.write_bytes(b"payload")
    result = manager.deploy_local_file(local_file, "/programs/demo.urp")
    assert result == "/programs/demo.urp"


def test_deploy_local_bundle_calls_upload_tree(monkeypatch, tmp_path: Path) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

    class FakeFileClient:
        def __init__(self, **_kwargs):
            pass

        def upload_tree(self, local_source_dir: Path, remote_destination_dir: str) -> list[dict]:
            assert local_source_dir.name == "bundle"
            assert remote_destination_dir == "/programs/jobs/bundle"
            return [
                {
                    "local_path": str(local_source_dir / "main.urp"),
                    "relative_path": "main.urp",
                    "remote_path": "/programs/jobs/bundle/main.urp",
                }
            ]

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    monkeypatch.setattr(robot_manager, "FileClient", FakeFileClient)
    manager = robot_manager.RobotManager(_robot())

    local_bundle = tmp_path / "bundle"
    local_bundle.mkdir(parents=True, exist_ok=True)
    (local_bundle / "main.urp").write_text("urp", encoding="utf-8")

    result = manager.deploy_local_bundle(local_bundle, "/programs/jobs/bundle")
    assert result["remote_destination_dir"] == "/programs/jobs/bundle"
    assert result["files"][0]["remote_path"] == "/programs/jobs/bundle/main.urp"


def test_create_remove_move_and_copy_remote_paths_call_file_client(monkeypatch) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

    calls: dict[str, tuple[str, ...] | str] = {}

    class FakeFileClient:
        def __init__(self, **_kwargs):
            pass

        def create_dir(self, remote_dir: str) -> str:
            calls["mkdir"] = remote_dir
            return remote_dir

        def remove_file(self, remote_path: str) -> str:
            calls["remove_file"] = remote_path
            return remote_path

        def remove_dir(self, remote_dir: str) -> str:
            calls["remove_dir"] = remote_dir
            return remote_dir

        def rename_path(self, source_path: str, destination_path: str) -> str:
            calls["rename"] = (source_path, destination_path)
            return destination_path

        def copy_file(self, source_path: str, destination_path: str) -> str:
            calls["copy"] = (source_path, destination_path)
            return destination_path

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    monkeypatch.setattr(robot_manager, "FileClient", FakeFileClient)
    manager = robot_manager.RobotManager(_robot())

    assert manager.create_remote_folder("/programs/jobs") == "/programs/jobs"
    assert manager.remove_remote_file("/programs/demo.urp") == "/programs/demo.urp"
    assert manager.remove_remote_folder("/programs/jobs") == "/programs/jobs"
    assert (
        manager.move_remote_path("/programs/demo.urp", "/programs/archive/demo.urp")
        == "/programs/archive/demo.urp"
    )
    assert (
        manager.copy_remote_file("/programs/demo.urp", "/programs/copy/demo.urp")
        == "/programs/copy/demo.urp"
    )

    assert calls["mkdir"] == "/programs/jobs"
    assert calls["remove_file"] == "/programs/demo.urp"
    assert calls["remove_dir"] == "/programs/jobs"
    assert calls["rename"] == ("/programs/demo.urp", "/programs/archive/demo.urp")
    assert calls["copy"] == ("/programs/demo.urp", "/programs/copy/demo.urp")


def test_remote_file_manager_operations_wrap_errors_cleanly(monkeypatch) -> None:
    class FakeDashboardClient:
        def __init__(self, _host: str, _port: int):
            pass

    class FakeFileClient:
        def __init__(self, **_kwargs):
            pass

        def create_dir(self, _remote_dir: str) -> str:
            raise RuntimeError("permission denied")

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    monkeypatch.setattr(robot_manager, "FileClient", FakeFileClient)
    manager = robot_manager.RobotManager(_robot())

    try:
        manager.create_remote_folder("/programs/jobs")
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "Creating remote directory failed" in str(exc)
