from __future__ import annotations

from pathlib import Path

from ur_arms_manager.adapters.ur.dashboard_client import DashboardClient
from ur_arms_manager.adapters.ur.file_client import FileClient
from ur_arms_manager.adapters.ur.script_client import ScriptClient
from ur_arms_manager.models import RobotConfig, RobotStatus


class RobotManager:
    def __init__(self, robot: RobotConfig):
        self.robot = robot
        self.dashboard = DashboardClient(robot.host, robot.dashboard_port)
        self.script = ScriptClient(robot.host, robot.script_port)
        self._file_client: FileClient | None = None

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
        try:
            robotmode = self.dashboard.get_robotmode()
            program_running = self.dashboard.get_program_state()
            safety_status = self.dashboard.get_safety_status()
            return RobotStatus(
                name=self.robot.name,
                connected=True,
                robotmode=robotmode,
                program_running=program_running,
                safety_status=safety_status,
                assigned_program=self.robot.assigned_program,
            )
        except Exception as exc:
            return RobotStatus(
                name=self.robot.name,
                connected=False,
                assigned_program=self.robot.assigned_program,
                detail=str(exc),
            )

    def load_assigned_program(self) -> str:
        if not self.robot.assigned_program:
            raise ValueError(
                f"Robot '{self.robot.name}' nemá přiřazený program v konfiguraci."
            )

        try:
            return self.dashboard.load(self.robot.assigned_program)
        except Exception as exc:
            raise RuntimeError(f"Load selhal pro robot '{self.robot.name}': {exc}") from exc

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

    def list_remote_files(self, remote_dir: str = "/programs") -> list[str]:
        try:
            return self._get_file_client().list_dir(remote_dir)
        except Exception as exc:
            raise RuntimeError(
                f"Výpis remote souborů selhal pro robot '{self.robot.name}': {exc}"
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
