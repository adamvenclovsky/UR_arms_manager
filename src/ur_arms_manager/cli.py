from __future__ import annotations

import sys
from pathlib import Path

from ur_arms_manager.config import DEFAULT_CONFIG_PATH, ROOT_DIR
from ur_arms_manager.registry import RegistryError, RobotRegistry
from ur_arms_manager.services.robot_manager import RobotManager


USAGE = """
Použití:
  uam robots list
  uam robot status <robot_name>
  uam robot assign <robot_name> <program_path>
  uam robot run <robot_name>
  uam robot stop <robot_name>
""".strip()


def main() -> int:
    try:
        return _main(sys.argv[1:])
    except RegistryError as exc:
        print(f"[config error] {exc}")
        return 2
    except Exception as exc:
        print(f"[error] {exc}")
        return 1


def _main(args: list[str]) -> int:
    if not args:
        print(USAGE)
        return 0

    registry = RobotRegistry(DEFAULT_CONFIG_PATH)

    match args:
        case ["robots", "list"]:
            robots = registry.list_robots()
            for robot in robots.values():
                print(
                    f"- {robot.name}: {robot.host} "
                    f"(dashboard={robot.dashboard_port}, script={robot.script_port}) "
                    f"enabled={robot.enabled} assigned={robot.assigned_program}"
                )
            return 0

        case ["robot", "status", robot_name]:
            robot = registry.get_robot(robot_name)
            status = RobotManager(robot).status()
            print(f"name: {status.name}")
            print(f"connected: {status.connected}")
            print(f"robotmode: {status.robotmode}")
            print(f"program_running: {status.program_running}")
            print(f"safety_status: {status.safety_status}")
            print(f"assigned_program: {status.assigned_program}")
            if status.detail:
                print(f"detail: {status.detail}")
            return 0

        case ["robot", "assign", robot_name, program_path]:
            absolute_program = Path(program_path)
            if not absolute_program.is_absolute():
                absolute_program = (ROOT_DIR / absolute_program).resolve()

            if not absolute_program.exists():
                raise FileNotFoundError(f"Program neexistuje: {absolute_program}")

            relative_program = absolute_program.relative_to(ROOT_DIR)
            registry.assign_program(robot_name, str(relative_program))
            print(f"Robotu '{robot_name}' přiřazen program: {relative_program}")
            return 0

        case ["robot", "run", robot_name]:
            robot = registry.get_robot(robot_name)
            message = RobotManager(robot).run_assigned_program(ROOT_DIR)
            print(message)
            return 0

        case ["robot", "stop", robot_name]:
            robot = registry.get_robot(robot_name)
            response = RobotManager(robot).stop_program()
            print(response)
            return 0

        case _:
            print(USAGE)
            return 1
