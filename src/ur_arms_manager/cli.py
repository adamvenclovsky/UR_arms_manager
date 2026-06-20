from __future__ import annotations

import sys
import tempfile
from pathlib import Path, PurePosixPath

from ur_arms_manager.config import DEFAULT_CONFIG_PATH, LIBRARY_PROGRAMS_DIR, ROOT_DIR
from ur_arms_manager.registry import RegistryError, RobotRegistry
from ur_arms_manager.services.compatibility import CompatibilityService
from ur_arms_manager.services.library_manager import LibraryError, LibraryManager
from ur_arms_manager.services.robot_manager import RobotManager

USAGE = """
Usage:
  uam robots list
  uam robot status <robot_name>
  uam robot assign <robot_name> <local_program_path>
  uam robot assign-remote <robot_name> <robot_program_path>
  uam robot assign-library <robot_name> <program_id>
  uam robot assign-script <robot_name> <program_id>
  uam robot run-script <robot_name> <program_id>
  uam robot load <robot_name>
  uam robot play <robot_name>
  uam robot stop <robot_name>
  uam robot power-on <robot_name>
  uam robot brake-release <robot_name>
  uam robot power-off <robot_name>
  uam robot deploy <robot_name> <program_id> [remote_dir]
  uam robot files list <robot_name> [remote_dir]
  uam robot files exists <robot_name> <remote_path>
  uam robot files pull <robot_name> <remote_path> <local_destination>
  uam robot compatibility <robot_name> <program_id>
  uam library list
  uam library add <local_file_path>
  uam library import-remote <robot_name> <remote_path>
  uam library inspect <program_id>
  uam library urp-params <program_id>
  uam library urp-set <program_id> <param_name> <value>
  uam library remove <program_id>
""".strip()


def main() -> int:
    try:
        return _main(sys.argv[1:])
    except RegistryError as exc:
        print(f"[config error] {exc}")
        return 2
    except LibraryError as exc:
        print(f"[library error] {exc}")
        return 3
    except Exception as exc:
        print(f"[error] {exc}")
        return 1


def _main(args: list[str]) -> int:
    if not args:
        print(USAGE)
        return 0

    registry = RobotRegistry(DEFAULT_CONFIG_PATH)
    library = LibraryManager(LIBRARY_PROGRAMS_DIR, root_dir=ROOT_DIR)

    match args:
        case ["robots", "list"]:
            robots = registry.list_robots()
            for robot in robots.values():
                print(f"- name: {robot.name}")
                print(f"  host: {robot.host}")
                print(f"  dashboard_port: {robot.dashboard_port}")
                print(f"  script_port: {robot.script_port}")
                print(f"  enabled: {robot.enabled}")
                print(f"  assigned_program: {robot.assigned_program}")
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
            candidate = Path(program_path)
            if candidate.is_absolute():
                absolute_program = candidate.resolve()
            else:
                absolute_program = (ROOT_DIR / candidate).resolve()

            if not absolute_program.exists():
                raise FileNotFoundError(f"Program does not exist: {absolute_program}")

            try:
                stored_path = absolute_program.relative_to(ROOT_DIR).as_posix()
            except ValueError:
                stored_path = str(absolute_program)

            registry.assign_program(robot_name, stored_path)
            print(f"Assigned local program to robot '{robot_name}': {stored_path}")
            return 0

        case ["robot", "assign-remote", robot_name, robot_program_path]:
            registry.assign_remote_program(robot_name, robot_program_path)
            print(f"Assigned remote program to robot '{robot_name}': {robot_program_path}")
            return 0

        case ["robot", "assign-library", robot_name, program_id]:
            stored_filename = library.get_stored_filename(program_id)
            assigned_program = str(PurePosixPath("/programs") / stored_filename)
            registry.assign_remote_program(robot_name, assigned_program)
            print(
                f"Assigned library program '{program_id}' to robot '{robot_name}': "
                f"{assigned_program}"
            )
            return 0

        case ["robot", "assign-script", robot_name, program_id]:
            library.ensure_script_item(program_id)
            assigned_program = f"library://{program_id}"
            registry.assign_program(robot_name, assigned_program)
            print(
                f"Assigned library script '{program_id}' to robot '{robot_name}': "
                f"{assigned_program}"
            )
            return 0

        case ["robot", "run-script", robot_name, program_id]:
            robot = registry.get_robot(robot_name)
            script_file = library.get_script_file(program_id)
            response = RobotManager(robot).run_script_file(script_file)
            print(f"run_script_response: {response}")
            return 0

        case ["robot", "load", robot_name]:
            robot = registry.get_robot(robot_name)
            response = RobotManager(robot).load_assigned_program()
            print(f"load_response: {response}")
            if "file not found" in response.lower():
                print(
                    "note: Dashboard Load uses controller-visible program paths, which "
                    "can differ from SSH/SFTP filesystem paths in URSim."
                )
            return 0

        case ["robot", "play", robot_name]:
            robot = registry.get_robot(robot_name)
            response = RobotManager(robot).play_program()
            print(f"play_response: {response}")
            return 0

        case ["robot", "stop", robot_name]:
            robot = registry.get_robot(robot_name)
            response = RobotManager(robot).stop_program()
            print(f"stop_response: {response}")
            return 0

        case ["robot", "power-on", robot_name]:
            robot = registry.get_robot(robot_name)
            response = RobotManager(robot).power_on()
            print(f"power_on_response: {response}")
            return 0

        case ["robot", "brake-release", robot_name]:
            robot = registry.get_robot(robot_name)
            response = RobotManager(robot).brake_release()
            print(f"brake_release_response: {response}")
            return 0

        case ["robot", "power-off", robot_name]:
            robot = registry.get_robot(robot_name)
            response = RobotManager(robot).power_off()
            print(f"power_off_response: {response}")
            return 0

        case ["robot", "deploy", robot_name, program_id]:
            robot = registry.get_robot(robot_name)
            source_file = library.get_stored_file(program_id)
            remote_path = str(PurePosixPath("/programs") / source_file.name)
            saved_remote_path = RobotManager(robot).deploy_local_file(source_file, remote_path)
            print(
                f"deployed: program_id={program_id} source={source_file} "
                f"destination={saved_remote_path}"
            )
            return 0

        case ["robot", "deploy", robot_name, program_id, remote_dir]:
            robot = registry.get_robot(robot_name)
            source_file = library.get_stored_file(program_id)
            remote_path = str(PurePosixPath(remote_dir) / source_file.name)
            saved_remote_path = RobotManager(robot).deploy_local_file(source_file, remote_path)
            print(
                f"deployed: program_id={program_id} source={source_file} "
                f"destination={saved_remote_path}"
            )
            return 0

        case ["robot", "files", "list", robot_name]:
            robot = registry.get_robot(robot_name)
            entries = RobotManager(robot).list_remote_files("/programs")
            for entry in entries:
                print(entry)
            return 0

        case ["robot", "files", "list", robot_name, remote_dir]:
            robot = registry.get_robot(robot_name)
            entries = RobotManager(robot).list_remote_files(remote_dir)
            for entry in entries:
                print(entry)
            return 0

        case ["robot", "files", "exists", robot_name, remote_path]:
            robot = registry.get_robot(robot_name)
            exists = RobotManager(robot).remote_file_exists(remote_path)
            print(f"exists: {'yes' if exists else 'no'}")
            return 0

        case ["robot", "files", "pull", robot_name, remote_path, local_destination]:
            robot = registry.get_robot(robot_name)
            saved_path = RobotManager(robot).pull_remote_file(remote_path, local_destination)
            print(f"pulled: {remote_path} -> {Path(saved_path).as_posix()}")
            return 0

        case ["robot", "compatibility", robot_name, program_id]:
            robot = registry.get_robot(robot_name)
            result = CompatibilityService(library).evaluate(robot, program_id)
            print(f"overall_status: {result.overall_status}")
            print(f"summary: {result.summary}")
            print("findings:")
            for finding in result.findings:
                print(f"- {finding}")
            return 0

        case ["library", "list"]:
            items = library.list_items()
            if not items:
                print("Library is empty.")
                return 0

            for item in items:
                print(f"- program_id: {item['program_id']}")
                print(f"  original_filename: {item['original_filename']}")
                print(f"  stored_path: {item['stored_path']}")
                print(f"  extension: {item['extension']}")
            return 0

        case ["library", "add", local_file_path]:
            item = library.add_item(local_file_path)
            print(f"Added to library: {item['program_id']}")
            print(f"stored_path: {item['stored_path']}")
            return 0

        case ["library", "import-remote", robot_name, remote_path]:
            robot = registry.get_robot(robot_name)
            with tempfile.TemporaryDirectory(prefix="uam-import-") as tmp_dir:
                pulled_path = RobotManager(robot).pull_remote_file(remote_path, tmp_dir)
                item = library.add_item(
                    str(pulled_path),
                    extra_metadata={
                        "origin": "robot_remote",
                        "source_robot": robot_name,
                        "source_remote_path": remote_path,
                    },
                )
            print(
                f"Imported from robot '{robot_name}': {remote_path} -> "
                f"program_id={item['program_id']} stored_path={item['stored_path']}"
            )
            return 0

        case ["library", "inspect", program_id]:
            item = library.inspect_item_enriched(program_id)
            print(f"program_id: {item['program_id']}")
            print(f"original_filename: {item['original_filename']}")
            print(f"stored_path: {item['stored_path']}")
            print(f"extension: {item['extension']}")
            print(f"created_at: {item['created_at']}")
            analysis = item.get("urp_analysis")
            if analysis is not None:
                print("urp_analysis:")
                print(f"  parse_success: {analysis.get('parse_success')}")
                if analysis.get("parse_error"):
                    print(f"  parse_error: {analysis['parse_error']}")
                for key in (
                    "program_name",
                    "installation_name",
                    "polyscope_version",
                    "robot_serial_number",
                ):
                    if key in analysis:
                        print(f"  {key}: {analysis[key]}")
                for key in ("urcap_names", "digital_inputs", "digital_outputs"):
                    if key in analysis:
                        print(f"  {key}: {analysis[key]}")
                if "contains_palletizing" in analysis:
                    print(f"  contains_palletizing: {analysis['contains_palletizing']}")
                for key in ("pallet_rows", "pallet_columns", "object_height_m"):
                    if key in analysis:
                        print(f"  {key}: {analysis[key]}")
            return 0

        case ["library", "urp-params", program_id]:
            params = library.list_urp_editable_params(program_id)
            if not params:
                print(f"No editable URP params detected for {program_id}.")
                return 0
            print("editable_urp_params:")
            for key, val in params.items():
                print(f"- {key}: {val}")
            return 0

        case ["library", "urp-set", program_id, param_name, value]:
            updated = library.set_urp_param(program_id, param_name, value)
            updated_value = updated[param_name]
            print(f"Updated URP param: {param_name}={updated_value} for {program_id}")
            return 0

        case ["library", "remove", program_id]:
            item = library.remove_item(program_id)
            print(f"Removed from library: {item['program_id']}")
            return 0

        case _:
            print(USAGE)
            return 1
