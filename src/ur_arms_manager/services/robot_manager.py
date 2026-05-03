from __future__ import annotations

from pathlib import Path
from pathlib import PurePosixPath
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
                f"Robot '{self.robot.name}' nemá přiřazený program v konfiguraci."
            )
        assigned_program = str(self.robot.assigned_program).strip()
        if assigned_program.startswith("library://"):
            raise ValueError(
                f"Robot '{self.robot.name}' má přiřazený interní library marker. "
                "Pro Load nejdřív přiřaď skutečnou robot-side cestu."
            )
        if not assigned_program.startswith("/"):
            raise ValueError(
                f"Robot '{self.robot.name}' nemá přiřazenou skutečnou robot-side cestu. "
                "Pro Load použij absolutní remote path jako /programs/demo.urp."
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
            return self.dashboard.stop()
        except Exception as exc:
            raise RuntimeError(f"Stop selhal pro robot '{self.robot.name}': {exc}") from exc

    def play_program(self) -> str:
        try:
            return self.dashboard.play()
        except Exception as exc:
            raise RuntimeError(f"Play selhal pro robot '{self.robot.name}': {exc}") from exc

    def power_on(self) -> str:
        try:
            return self.dashboard.power_on()
        except Exception as exc:
            raise RuntimeError(
                f"Power-on selhal pro robot '{self.robot.name}': {exc}"
            ) from exc

    def brake_release(self) -> str:
        try:
            return self.dashboard.brake_release()
        except Exception as exc:
            raise RuntimeError(
                f"Brake-release selhal pro robot '{self.robot.name}': {exc}"
            ) from exc

    def power_off(self) -> str:
        try:
            return self.dashboard.power_off()
        except Exception as exc:
            raise RuntimeError(
                f"Power-off selhal pro robot '{self.robot.name}': {exc}"
            ) from exc

    def list_remote_files(self, remote_dir: str = "/programs") -> list[str]:
        try:
            return self._get_file_client().list_dir(remote_dir)
        except Exception as exc:
            raise RuntimeError(
                f"Výpis remote souborů selhal pro robot '{self.robot.name}': {exc}"
            ) from exc

    def list_remote_entries(self, remote_dir: str = "/programs") -> list[dict[str, Any]]:
        try:
            return self._get_file_client().list_dir_entries(remote_dir)
        except Exception as exc:
            raise RuntimeError(
                f"Výpis remote položek selhal pro robot '{self.robot.name}': {exc}"
            ) from exc

    def remote_file_exists(self, remote_path: str) -> bool:
        try:
            return self._get_file_client().exists(remote_path)
        except Exception as exc:
            raise RuntimeError(
                f"Ověření remote souboru selhalo pro robot '{self.robot.name}': {exc}"
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
                f"Stažení remote souboru selhalo pro robot '{self.robot.name}': {exc}"
            ) from exc

    def deploy_local_file(self, local_source: Path, remote_destination: str) -> str:
        try:
            return self._get_file_client().upload_file(local_source, remote_destination)
        except Exception as exc:
            raise RuntimeError(
                f"Nahrání souboru na robot '{self.robot.name}' selhalo: {exc}"
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
                f"Nahrání bundle adresáře na robot '{self.robot.name}' selhalo: {exc}"
            ) from exc

    def create_remote_folder(self, remote_dir: str) -> str:
        try:
            return self._get_file_client().create_dir(remote_dir)
        except Exception as exc:
            raise RuntimeError(
                f"Vytvoření remote adresáře selhalo pro robot '{self.robot.name}': {exc}"
            ) from exc

    def remove_remote_file(self, remote_path: str) -> str:
        try:
            return self._get_file_client().remove_file(remote_path)
        except Exception as exc:
            raise RuntimeError(
                f"Odstranění remote souboru selhalo pro robot '{self.robot.name}': {exc}"
            ) from exc

    def remove_remote_folder(self, remote_dir: str) -> str:
        try:
            return self._get_file_client().remove_dir(remote_dir)
        except Exception as exc:
            raise RuntimeError(
                f"Odstranění remote adresáře selhalo pro robot '{self.robot.name}': {exc}"
            ) from exc

    def move_remote_path(self, source_path: str, destination_path: str) -> str:
        try:
            return self._get_file_client().rename_path(source_path, destination_path)
        except Exception as exc:
            raise RuntimeError(
                f"Přesun remote cesty selhal pro robot '{self.robot.name}': {exc}"
            ) from exc

    def copy_remote_file(self, source_path: str, destination_path: str) -> str:
        try:
            return self._get_file_client().copy_file(source_path, destination_path)
        except Exception as exc:
            raise RuntimeError(
                f"Kopírování remote souboru selhalo pro robot '{self.robot.name}': {exc}"
            ) from exc

    def run_script_file(self, local_script_path: Path) -> str:
        path = Path(local_script_path)
        try:
            script_text = path.read_text(encoding="utf-8")
        except Exception as exc:
            raise RuntimeError(
                f"Načtení script souboru selhalo pro robot '{self.robot.name}': {exc}"
            ) from exc

        try:
            self.script.send_program(script_text)
            return f"Script sent to robot '{self.robot.name}' from {path}"
        except Exception as exc:
            raise RuntimeError(
                f"Spuštění scriptu selhalo pro robot '{self.robot.name}': {exc}"
            ) from exc

    def _dashboard_load_path(self, assigned_remote_path: str) -> str:
        return derive_dashboard_load_argument(str(PurePosixPath(assigned_remote_path)))

    def _dashboard_load_was_rejected(self, response: str) -> bool:
        outcome, _notes = classify_dashboard_load_response(response)
        return outcome != "success"
