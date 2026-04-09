from pathlib import Path

from ur_arms_manager.registry import RobotRegistry


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
