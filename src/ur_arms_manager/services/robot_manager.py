from __future__ import annotations

import time
from pathlib import Path, PurePosixPath
from typing import Any

from ur_arms_manager.adapters.ur.dashboard_client import DashboardClient
from ur_arms_manager.adapters.ur.file_client import FileClient
from ur_arms_manager.adapters.ur.script_client import ScriptClient
from ur_arms_manager.models import RobotConfig, RobotStatus
from ur_arms_manager.services.monitoring import get_robot_monitoring_status
from ur_arms_manager.services.runtime_validation import (
    LoadValidationResult,
    classify_dashboard_load_response,
    derive_dashboard_load_argument,
    runtime_name_safety_warning,
)


class RobotManager:
    def __init__(self, robot: RobotConfig):
        self.robot = robot
        self.dashboard = DashboardClient(robot.host, robot.dashboard_port)
        self.script = ScriptClient(robot.host, robot.script_port)
        self._file_client: FileClient | None = None
        self._last_load_validation: LoadValidationResult | None = None

    def _get_file_client(self) -> FileClient:
        if self._file_client is None:
            self._file_client = FileClient(
                host=self.robot.host,
                port=self.robot.ssh_port,
                username=self.robot.ssh_username,
                password=self.robot.ssh_password,
            )
        return self._file_client

    def status(self) -> RobotStatus:
        return get_robot_monitoring_status(self.robot, dashboard_client=self.dashboard)

    def get_assigned_remote_program_path(self) -> str:
        if not self.robot.assigned_program:
            raise ValueError(
                f"Robot '{self.robot.name}' has no assigned program in configuration."
            )
        assigned_program = str(self.robot.assigned_program).strip()
        if assigned_program.startswith("library://"):
            raise ValueError(
                f"Robot '{self.robot.name}' has an internal library marker assigned. "
                "Assign a real robot-side path before using Load."
            )
        if not assigned_program.startswith("/"):
            raise ValueError(
                f"Robot '{self.robot.name}' does not have a real robot-side path assigned. "
                "Use an absolute remote path such as /programs/demo.urp for Load."
            )
        return assigned_program

    def load_assigned_program(self) -> str:
        assigned_runtime_path = self.get_assigned_remote_program_path()
        result = self.validate_assigned_runtime_load(assigned_runtime_path=assigned_runtime_path)
        if result.outcome != "success":
            details = result.raw_dashboard_response or "; ".join(result.notes) or "Unknown load failure."
            raise RuntimeError(
                f"Load rejected for robot '{self.robot.name}' using "
                f"'{result.derived_dashboard_load_argument or '<none>'}' "
                f"(outcome={result.outcome}): {details}"
            )
        return result.raw_dashboard_response or "Loading program."

    def validate_assigned_runtime_load(
        self,
        assigned_runtime_path: str | None = None,
    ) -> LoadValidationResult:
        assigned_runtime_path_value: str | None = assigned_runtime_path
        derived_load_argument: str | None = None
        raw_dashboard_response: str | None = None

        try:
            if assigned_runtime_path_value is None:
                assigned_runtime_path_value = self.get_assigned_remote_program_path()
            derived_load_argument = derive_dashboard_load_argument(assigned_runtime_path_value)
            warning = runtime_name_safety_warning(derived_load_argument)
            if warning:
                outcome = "unsafe_runtime_path"
                notes = [
                    "Cannot validate dashboard load because the derived load argument contains spaces or unsafe characters. Prepare a runtime-safe bundle first.",
                    warning,
                ]
                result = LoadValidationResult(
                    robot_name=self.robot.name,
                    assigned_runtime_path=assigned_runtime_path_value,
                    derived_dashboard_load_argument=derived_load_argument,
                    raw_dashboard_response=None,
                    outcome=outcome,
                    notes=notes,
                    ready_for_play=False,
                )
                self._last_load_validation = result
                return result
            raw_dashboard_response = self.dashboard.load(derived_load_argument)
            outcome, notes = classify_dashboard_load_response(raw_dashboard_response)
        except Exception as exc:
            if assigned_runtime_path_value is None:
                assigned_runtime_path_value = str(self.robot.assigned_program or "").strip() or None
                outcome = "load_error"
                notes = [str(exc)]
            else:
                outcome, notes = classify_dashboard_load_response(raw_dashboard_response, error=exc)

        result = LoadValidationResult(
            robot_name=self.robot.name,
            assigned_runtime_path=assigned_runtime_path_value,
            derived_dashboard_load_argument=derived_load_argument,
            raw_dashboard_response=raw_dashboard_response,
            outcome=outcome,
            notes=notes,
            ready_for_play=(outcome == "success"),
        )
        self._last_load_validation = result
        return result

    def stop_program(self) -> str:
        try:
            response = self.dashboard.stop()
            self._raise_for_dashboard_rejection("Stop", response)
            return response
        except Exception as exc:
            raise RuntimeError(f"Stop failed for robot '{self.robot.name}': {exc}") from exc

    def pause_program(self) -> str:
        try:
            response = self.dashboard.pause()
            self._raise_for_dashboard_rejection("Pause", response)
            return response
        except Exception as exc:
            raise RuntimeError(f"Pause failed for robot '{self.robot.name}': {exc}") from exc

    def play_program(self) -> str:
        try:
            return self._play_with_retries("Play")
        except Exception as exc:
            raise RuntimeError(f"Play failed for robot '{self.robot.name}': {exc}") from exc

    def move_home(self) -> str:
        try:
            home_program = str(self.robot.home_program or "").strip()
            if not home_program:
                raise RuntimeError(
                    "Robot does not have home_program configured. "
                    "Set it to an existing robot-side .urp path, for example /programs/go_home.urp."
                )

            load_response, load_argument = self._load_program_with_dashboard_fallbacks(
                home_program,
                "Home program load",
            )

            play_message = self._play_with_retries("Move Home play", initial_delay_seconds=1.0)
            return (
                f"Home program loaded and started. Load response: {load_response}. "
                f"Play response: {play_message}. Home path: {home_program}."
            )
        except Exception as exc:
            raise RuntimeError(f"Move Home failed for robot '{self.robot.name}': {exc}") from exc

    def power_on(self) -> str:
        try:
            response = self.dashboard.power_on()
            self._raise_for_dashboard_rejection("Power-on", response)
            return response
        except Exception as exc:
            raise RuntimeError(
                f"Power-on failed for robot '{self.robot.name}': {exc}"
            ) from exc

    def brake_release(self) -> str:
        try:
            response = self.dashboard.brake_release()
            self._raise_for_dashboard_rejection("Brake-release", response)
            return response
        except Exception as exc:
            raise RuntimeError(
                f"Brake-release failed for robot '{self.robot.name}': {exc}"
            ) from exc

    def power_off(self) -> str:
        try:
            response = self.dashboard.power_off()
            self._raise_for_dashboard_rejection("Power-off", response)
            return response
        except Exception as exc:
            raise RuntimeError(
                f"Power-off failed for robot '{self.robot.name}': {exc}"
            ) from exc

    def list_remote_files(self, remote_dir: str = "/programs") -> list[str]:
        try:
            return self._get_file_client().list_dir(remote_dir)
        except Exception as exc:
            raise RuntimeError(
                f"Listing remote files failed for robot '{self.robot.name}': {exc}"
            ) from exc

    def list_remote_entries(self, remote_dir: str = "/programs") -> list[dict[str, Any]]:
        try:
            return self._get_file_client().list_dir_entries(remote_dir)
        except Exception as exc:
            raise RuntimeError(
                f"Listing remote entries failed for robot '{self.robot.name}': {exc}"
            ) from exc

    def remote_file_exists(self, remote_path: str) -> bool:
        try:
            return self._get_file_client().exists(remote_path)
        except Exception as exc:
            raise RuntimeError(
                f"Checking remote path failed for robot '{self.robot.name}': {exc}"
            ) from exc

    def pull_remote_file(self, remote_path: str, local_destination: str) -> Path:
        destination = Path(local_destination)
        if destination.exists() and destination.is_dir():
            destination = destination / Path(remote_path).name
        elif local_destination.endswith("/") or local_destination.endswith("\\"):
            destination = destination / Path(remote_path).name
        try:
            return self._get_file_client().pull_file(remote_path, destination)
        except Exception as exc:
            raise RuntimeError(
                f"Downloading remote file failed for robot '{self.robot.name}': {exc}"
            ) from exc

    def deploy_local_file(self, local_source: Path, remote_destination: str) -> str:
        try:
            return self._get_file_client().upload_file(local_source, remote_destination)
        except Exception as exc:
            raise RuntimeError(
                f"Uploading file to robot '{self.robot.name}' failed: {exc}"
            ) from exc

    def deploy_local_bundle(self, local_source_dir: Path, remote_destination_dir: str) -> dict[str, Any]:
        try:
            files = self._get_file_client().upload_tree(local_source_dir, remote_destination_dir)
            return {
                "remote_destination_dir": remote_destination_dir,
                "files": files,
            }
        except Exception as exc:
            raise RuntimeError(
                f"Uploading bundle to robot '{self.robot.name}' failed: {exc}"
            ) from exc

    def create_remote_folder(self, remote_dir: str) -> str:
        try:
            return self._get_file_client().create_dir(remote_dir)
        except Exception as exc:
            raise RuntimeError(
                f"Creating remote directory failed for robot '{self.robot.name}': {exc}"
            ) from exc

    def remove_remote_file(self, remote_path: str) -> str:
        try:
            return self._get_file_client().remove_file(remote_path)
        except Exception as exc:
            raise RuntimeError(
                f"Removing remote file failed for robot '{self.robot.name}': {exc}"
            ) from exc

    def remove_remote_folder(self, remote_dir: str) -> str:
        try:
            return self._get_file_client().remove_dir(remote_dir)
        except Exception as exc:
            raise RuntimeError(
                f"Removing remote directory failed for robot '{self.robot.name}': {exc}"
            ) from exc

    def move_remote_path(self, source_path: str, destination_path: str) -> str:
        try:
            return self._get_file_client().rename_path(source_path, destination_path)
        except Exception as exc:
            raise RuntimeError(
                f"Moving remote path failed for robot '{self.robot.name}': {exc}"
            ) from exc

    def copy_remote_file(self, source_path: str, destination_path: str) -> str:
        try:
            return self._get_file_client().copy_file(source_path, destination_path)
        except Exception as exc:
            raise RuntimeError(
                f"Copying remote file failed for robot '{self.robot.name}': {exc}"
            ) from exc

    def run_script_file(self, local_script_path: Path) -> str:
        path = Path(local_script_path)
        try:
            script_text = path.read_text(encoding="utf-8")
        except Exception as exc:
            raise RuntimeError(
                f"Reading script file failed for robot '{self.robot.name}': {exc}"
            ) from exc

        try:
            self.script.send_program(script_text)
            return f"Script sent to robot '{self.robot.name}' from {path}"
        except Exception as exc:
            raise RuntimeError(
                f"Running script failed for robot '{self.robot.name}': {exc}"
            ) from exc

    def _dashboard_load_path(self, assigned_remote_path: str) -> str:
        return derive_dashboard_load_argument(str(PurePosixPath(assigned_remote_path)))

    def _dashboard_load_was_rejected(self, response: str) -> bool:
        outcome, _notes = classify_dashboard_load_response(response)
        return outcome != "success"

    def _raise_for_dashboard_rejection(
        self,
        action_label: str,
        response: str,
        include_context: bool = False,
    ) -> None:
        normalized = str(response or "").strip().lower()
        rejection_markers = (
            "failed to execute",
            "could not understand",
            "not allowed",
            "not able",
            "rejected",
        )
        if any(marker in normalized for marker in rejection_markers):
            context = f" Context: {self._dashboard_context_summary()}" if include_context else ""
            hint = self._play_rejection_hint(context) if include_context else ""
            raise RuntimeError(f"Dashboard rejected {action_label}: {response}.{context}{hint}")

    def _play_with_retries(
        self,
        action_label: str,
        attempts: int = 3,
        initial_delay_seconds: float = 0.0,
        retry_delay_seconds: float = 0.75,
    ) -> str:
        if initial_delay_seconds > 0:
            time.sleep(initial_delay_seconds)

        last_response = ""
        prepare_note = ""
        for attempt in range(1, attempts + 1):
            prepare_note = self._prepare_for_remote_play()
            response = self.dashboard.play()
            last_response = response
            try:
                self._raise_for_dashboard_rejection(action_label, response, include_context=True)
                retry_note = f" after {attempt} attempt(s)" if attempt > 1 else ""
                return f"{prepare_note}{response}{retry_note}"
            except RuntimeError:
                if attempt >= attempts:
                    raise
                time.sleep(retry_delay_seconds)

        raise RuntimeError(f"Dashboard rejected {action_label}: {last_response}")

    def _play_rejection_hint(self, context: str) -> str:
        normalized = context.lower()
        if "remotecontrol=false" in normalized:
            return (
                " Possible causes: Remote Control is disabled, or this motion program "
                "requires operator-side start-position/Automove confirmation. URSim can "
                "report remoteControl=false even when other Dashboard actions work; use "
                "PolyScope Run to confirm the start position for MoveJ programs."
            )
        if (
            "remotecontrol=true" in normalized
            and "safetystatus: normal" in normalized
            and "programstate=stopped" in normalized
            and "loaded=loaded program:" in normalized
        ):
            return (
                " Likely cause: PolyScope cannot start the loaded program remotely because "
                "it requires an operator-side start-position/Automove confirmation or the "
                "program itself blocks before first motion. Dashboard play cannot press that "
                "PolyScope confirmation button."
            )
        return ""

    def _prepare_for_remote_play(self) -> str:
        notes: list[str] = []
        for label, command_name in (
            ("close safety popup", "close_safety_popup"),
            ("close popup", "close_popup"),
        ):
            try:
                command = getattr(self.dashboard, command_name)
                response = command()
                normalized = str(response or "").strip().lower()
                if normalized and not any(
                    marker in normalized
                    for marker in ("could not understand", "failed", "not allowed")
                ):
                    notes.append(f"{label}: {response}")
            except Exception:
                continue

        try:
            safety_status = self.dashboard.get_safety_status()
            if "protective_stop" in safety_status.lower() or "protective stop" in safety_status.lower():
                notes.append(f"unlock protective stop: {self.dashboard.unlock_protective_stop()}")
        except Exception:
            pass

        return f"Prepare: {'; '.join(notes)}. " if notes else ""

    def _dashboard_context_summary(self) -> str:
        checks = (
            ("robotmode", "get_robotmode"),
            ("safety", "get_safety_status"),
            ("programState", "get_program_state"),
            ("remoteControl", "is_in_remote_control"),
            ("loaded", "get_loaded_program"),
        )
        parts: list[str] = []
        for label, command_name in checks:
            try:
                command = getattr(self.dashboard, command_name)
                parts.append(f"{label}={command()}")
            except Exception as exc:
                parts.append(f"{label}=unavailable({exc})")
        return "; ".join(parts)

    def _load_program_with_dashboard_fallbacks(
        self,
        robot_side_program_path: str,
        action_label: str,
    ) -> tuple[str, str]:
        load_argument = derive_dashboard_load_argument(robot_side_program_path)
        candidates = [load_argument]
        warning = runtime_name_safety_warning(load_argument)
        if warning and '"' not in load_argument:
            candidates.append(f'"{load_argument}"')

        failures: list[str] = []
        for candidate in candidates:
            response = self.dashboard.load(candidate)
            outcome, notes = classify_dashboard_load_response(response)
            if outcome == "success":
                return response, candidate
            detail = response or "; ".join(notes) or "unknown Dashboard response"
            failures.append(f"{candidate}: {detail}")

        safety_note = f" {warning}" if warning else ""
        raise RuntimeError(
            f"Dashboard rejected {action_label}.{safety_note} Tried: {' | '.join(failures)}"
        )
