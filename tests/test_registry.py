from pathlib import Path

from ur_arms_manager.registry import RegistryError, RobotRegistry

EXAMPLE = """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: programs/robot1/demo_hello.script
"""


def test_assign_program_updates_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE, encoding="utf-8")

    registry = RobotRegistry(config_path)
    registry.assign_program("robot1", "programs/robot1/another.script")

    robot = registry.get_robot("robot1")
    assert robot.assigned_program == "programs/robot1/another.script"


def test_assign_remote_program_stores_exact_string(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE, encoding="utf-8")

    registry = RobotRegistry(config_path)
    registry.assign_remote_program("robot1", "/programs/Cell A/demo_run.urp")

    robot = registry.get_robot("robot1")
    assert robot.assigned_program == "/programs/Cell A/demo_run.urp"


def test_robot_defaults_to_disabled_and_has_no_default_password(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        "robots:\n  robot1:\n    host: 127.0.0.1\n    dashboard_port: 29999\n    script_port: 30002\n",
        encoding="utf-8",
    )

    robot = RobotRegistry(config_path).get_robot("robot1")

    assert robot.enabled is False
    assert robot.ssh_password == ""


def test_malformed_yaml_raises_friendly_registry_error(tmp_path: Path) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text("robots: [broken", encoding="utf-8")

    try:
        RobotRegistry(config_path).list_robots()
        assert False, "Expected malformed config failure"
    except RegistryError as exc:
        assert "Cannot read robot configuration" in str(exc)
