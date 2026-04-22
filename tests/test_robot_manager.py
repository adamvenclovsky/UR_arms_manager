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


def test_load_assigned_program_calls_dashboard(monkeypatch) -> None:
    class FakeDashboardClient:
        def __init__(self, host: str, port: int):
            assert host == "127.0.0.1"
            assert port == 29999

        def load(self, program_path: str) -> str:
            assert program_path == "/programs/demo.urp"
            return "Loading program: /programs/demo.urp"

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    manager = robot_manager.RobotManager(_robot())

    result = manager.load_assigned_program()

    assert result == "Loading program: /programs/demo.urp"


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
        assert "nemá přiřazený program" in str(exc)


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
        assert "Play selhal" in str(exc)

    try:
        manager.stop_program()
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "Stop selhal" in str(exc)


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
            assert kwargs["password"] == "easybot"

        def list_dir(self, remote_dir: str) -> list[str]:
            assert remote_dir == "/programs"
            return ["a.urp", "b.urp"]

    monkeypatch.setattr(robot_manager, "DashboardClient", FakeDashboardClient)
    monkeypatch.setattr(robot_manager, "FileClient", FakeFileClient)
    manager = robot_manager.RobotManager(_robot())

    files = manager.list_remote_files()

    assert files == ["a.urp", "b.urp"]


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
