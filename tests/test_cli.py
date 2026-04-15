from __future__ import annotations

from pathlib import Path

import yaml

from ur_arms_manager import cli
from ur_arms_manager.models import RobotStatus


EXAMPLE_CONFIG = """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: null
"""

EXAMPLE_CONFIG_WITH_REMOTE = """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: /programs/demo_controller.urp
"""


def test_robots_list_prints_expected_fields(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)

    exit_code = cli._main(["robots", "list"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "name: robot1" in output
    assert "host: 127.0.0.1" in output
    assert "dashboard_port: 29991" in output
    assert "script_port: 30021" in output
    assert "enabled: True" in output
    assert "assigned_program: None" in output


def test_robot_status_unreachable_is_clean(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def status(self) -> RobotStatus:
            return RobotStatus(
                name="robot1",
                connected=False,
                assigned_program=None,
                detail="connection refused",
            )

    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)

    exit_code = cli._main(["robot", "status", "robot1"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "connected: False" in output
    assert "detail: connection refused" in output


def test_robot_assign_saves_project_relative_path(tmp_path: Path, monkeypatch, capsys) -> None:
    root_dir = tmp_path
    config_dir = root_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")

    program = root_dir / "programs" / "robot1" / "demo.script"
    program.parent.mkdir(parents=True, exist_ok=True)
    program.write_text("def demo():\n  textmsg(\"ok\")\nend\n", encoding="utf-8")

    monkeypatch.setattr(cli, "ROOT_DIR", root_dir)
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)

    exit_code = cli._main(["robot", "assign", "robot1", "programs/robot1/demo.script"])
    output = capsys.readouterr().out
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "programs/robot1/demo.script" in output
    assert saved["robots"]["robot1"]["assigned_program"] == "programs/robot1/demo.script"


def test_robot_load_prints_dashboard_response(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG_WITH_REMOTE, encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)

    class FakeRobotManager:
        def __init__(self, robot):
            self.robot = robot

        def load_assigned_program(self) -> str:
            return f"Loading program: {self.robot.assigned_program}"

    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)

    exit_code = cli._main(["robot", "load", "robot1"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "load_response: Loading program: /programs/demo_controller.urp" in output


def test_robot_load_file_not_found_prints_dashboard_path_note(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG_WITH_REMOTE, encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def load_assigned_program(self) -> str:
            return "File not found: test1.urp"

    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)

    exit_code = cli._main(["robot", "load", "robot1"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "load_response: File not found: test1.urp" in output
    assert "Dashboard load používá controller-visible program cesty/jména" in output


def test_robot_play_prints_dashboard_response(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def play_program(self) -> str:
            return "Starting program"

    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)

    exit_code = cli._main(["robot", "play", "robot1"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "play_response: Starting program" in output


def test_robot_stop_prints_dashboard_response(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def stop_program(self) -> str:
            return "Stopped"

    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)

    exit_code = cli._main(["robot", "stop", "robot1"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "stop_response: Stopped" in output


def test_robot_power_on_prints_dashboard_response(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def power_on(self) -> str:
            return "Powering on"

    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)

    exit_code = cli._main(["robot", "power-on", "robot1"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "power_on_response: Powering on" in output


def test_robot_brake_release_prints_dashboard_response(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def brake_release(self) -> str:
            return "Brake releasing"

    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)

    exit_code = cli._main(["robot", "brake-release", "robot1"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "brake_release_response: Brake releasing" in output


def test_robot_power_off_prints_dashboard_response(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def power_off(self) -> str:
            return "Powering off"

    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)

    exit_code = cli._main(["robot", "power-off", "robot1"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "power_off_response: Powering off" in output


def test_robot_power_on_failure_returns_clean_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def power_on(self) -> str:
            raise RuntimeError("Power-on selhal pro robot 'robot1': connection refused")

    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)
    monkeypatch.setattr(cli.sys, "argv", ["uam", "robot", "power-on", "robot1"])

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "[error] Power-on selhal pro robot 'robot1': connection refused" in output


def test_robot_load_without_assigned_program_returns_clean_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def load_assigned_program(self) -> str:
            raise ValueError("Robot 'robot1' nemá přiřazený program v konfiguraci.")

    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)
    monkeypatch.setattr(cli.sys, "argv", ["uam", "robot", "load", "robot1"])

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "[error] Robot 'robot1' nemá přiřazený program v konfiguraci." in output


def test_robot_assign_remote_stores_exact_string_without_local_validation(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)

    remote_path = "/programs/Cell A/demo run.urp"
    exit_code = cli._main(["robot", "assign-remote", "robot1", remote_path])
    output = capsys.readouterr().out
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert f"remote program: {remote_path}" in output
    assert saved["robots"]["robot1"]["assigned_program"] == remote_path


def test_robot_files_list_defaults_to_programs(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def list_remote_files(self, remote_dir: str = "/programs") -> list[str]:
            assert remote_dir == "/programs"
            return ["demo_a.urp", "demo_b.urp"]

    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)

    exit_code = cli._main(["robot", "files", "list", "robot1"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "demo_a.urp" in output
    assert "demo_b.urp" in output


def test_robot_files_list_with_remote_dir(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def list_remote_files(self, remote_dir: str = "/programs") -> list[str]:
            assert remote_dir == "/programs/subdir"
            return ["nested.urp"]

    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)

    exit_code = cli._main(["robot", "files", "list", "robot1", "/programs/subdir"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "nested.urp" in output


def test_robot_files_exists_outputs_yes_no(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def remote_file_exists(self, remote_path: str) -> bool:
            return remote_path == "/programs/found.urp"

    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)

    yes_code = cli._main(["robot", "files", "exists", "robot1", "/programs/found.urp"])
    yes_output = capsys.readouterr().out
    no_code = cli._main(["robot", "files", "exists", "robot1", "/programs/missing.urp"])
    no_output = capsys.readouterr().out

    assert yes_code == 0
    assert "exists: yes" in yes_output
    assert no_code == 0
    assert "exists: no" in no_output


def test_robot_files_pull_outputs_saved_path(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def pull_remote_file(self, remote_path: str, local_destination: str) -> Path:
            assert remote_path == "/programs/demo.urp"
            assert local_destination == "downloads"
            return Path("/tmp/downloads/demo.urp")

    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)

    exit_code = cli._main(
        ["robot", "files", "pull", "robot1", "/programs/demo.urp", "downloads"]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "pulled: /programs/demo.urp -> /tmp/downloads/demo.urp" in output


def test_robot_assign_library_sets_default_remote_path(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    storage_root = tmp_path / "storage" / "programs" / "demo-1234"
    storage_root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "program_id": "demo-1234",
        "original_filename": "demo.urp",
        "stored_filename": "demo.urp",
        "stored_path": str(storage_root / "demo.urp"),
        "extension": "urp",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    (storage_root / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")

    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")

    exit_code = cli._main(["robot", "assign-library", "robot1", "demo-1234"])
    output = capsys.readouterr().out
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "/programs/demo.urp" in output
    assert saved["robots"]["robot1"]["assigned_program"] == "/programs/demo.urp"


def test_robot_deploy_uses_default_programs_dir(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    storage_root = tmp_path / "storage" / "programs" / "demo-1234"
    storage_root.mkdir(parents=True, exist_ok=True)
    local_file = storage_root / "demo.urp"
    local_file.write_bytes(b"payload")

    manifest = {
        "program_id": "demo-1234",
        "original_filename": "demo.urp",
        "stored_filename": "demo.urp",
        "stored_path": str(local_file),
        "extension": "urp",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    (storage_root / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def deploy_local_file(self, source_file: Path, remote_path: str) -> str:
            assert source_file == local_file
            assert remote_path == "/programs/demo.urp"
            return remote_path

    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)

    exit_code = cli._main(["robot", "deploy", "robot1", "demo-1234"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "destination=/programs/demo.urp" in output


def test_robot_deploy_library_missing_returns_clean_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    monkeypatch.setattr(cli.sys, "argv", ["uam", "robot", "deploy", "robot1", "missing-id"])

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 3
    assert "[library error] Library item not found: missing-id" in output


def test_robot_deploy_with_custom_remote_dir(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    storage_root = tmp_path / "storage" / "programs" / "demo-1234"
    storage_root.mkdir(parents=True, exist_ok=True)
    local_file = storage_root / "demo.urp"
    local_file.write_bytes(b"payload")

    manifest = {
        "program_id": "demo-1234",
        "original_filename": "demo.urp",
        "stored_filename": "demo.urp",
        "stored_path": str(local_file),
        "extension": "urp",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    (storage_root / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def deploy_local_file(self, source_file: Path, remote_path: str) -> str:
            assert source_file == local_file
            assert remote_path == "/my_programs/demo.urp"
            return remote_path

    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)

    exit_code = cli._main(["robot", "deploy", "robot1", "demo-1234", "/my_programs"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "destination=/my_programs/demo.urp" in output


def test_robot_run_script_success(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    storage_root = tmp_path / "storage" / "programs" / "demo-script-1234"
    storage_root.mkdir(parents=True, exist_ok=True)
    local_file = storage_root / "demo.script"
    local_file.write_text("def demo():\n  textmsg(\"ok\")\nend\n", encoding="utf-8")

    manifest = {
        "program_id": "demo-script-1234",
        "original_filename": "demo.script",
        "stored_filename": "demo.script",
        "stored_path": str(local_file),
        "extension": "script",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    (storage_root / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def run_script_file(self, script_file: Path) -> str:
            assert script_file == local_file
            return "Script sent to robot 'robot1' from local storage"

    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)

    exit_code = cli._main(["robot", "run-script", "robot1", "demo-script-1234"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "run_script_response: Script sent to robot 'robot1' from local storage" in output


def test_robot_run_script_rejects_non_script_item(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    storage_root = tmp_path / "storage" / "programs" / "demo-urp-1234"
    storage_root.mkdir(parents=True, exist_ok=True)
    local_file = storage_root / "demo.urp"
    local_file.write_text("<Program/>", encoding="utf-8")

    manifest = {
        "program_id": "demo-urp-1234",
        "original_filename": "demo.urp",
        "stored_filename": "demo.urp",
        "stored_path": str(local_file),
        "extension": "urp",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    (storage_root / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")

    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    monkeypatch.setattr(cli.sys, "argv", ["uam", "robot", "run-script", "robot1", "demo-urp-1234"])

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 3
    assert "[library error] Library item is not a .script program: demo-urp-1234" in output


def test_robot_assign_script_stores_library_marker(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    storage_root = tmp_path / "storage" / "programs" / "demo-script-5678"
    storage_root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "program_id": "demo-script-5678",
        "original_filename": "demo.script",
        "stored_filename": "demo.script",
        "stored_path": str(storage_root / "demo.script"),
        "extension": "script",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    (storage_root / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")

    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")

    exit_code = cli._main(["robot", "assign-script", "robot1", "demo-script-5678"])
    output = capsys.readouterr().out
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "library://demo-script-5678" in output
    assert saved["robots"]["robot1"]["assigned_program"] == "library://demo-script-5678"


def test_robot_run_script_connection_failure_returns_clean_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    storage_root = tmp_path / "storage" / "programs" / "demo-script-9999"
    storage_root.mkdir(parents=True, exist_ok=True)
    local_file = storage_root / "demo.script"
    local_file.write_text("def demo():\nend\n", encoding="utf-8")

    manifest = {
        "program_id": "demo-script-9999",
        "original_filename": "demo.script",
        "stored_filename": "demo.script",
        "stored_path": str(local_file),
        "extension": "script",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    (storage_root / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def run_script_file(self, _script_file: Path) -> str:
            raise RuntimeError("Spuštění scriptu selhalo pro robot 'robot1': connection refused")

    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)
    monkeypatch.setattr(
        cli.sys, "argv", ["uam", "robot", "run-script", "robot1", "demo-script-9999"]
    )

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "[error] Spuštění scriptu selhalo pro robot 'robot1': connection refused" in output
