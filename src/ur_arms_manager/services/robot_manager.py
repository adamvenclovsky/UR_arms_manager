from __future__ import annotations

from pathlib import Path

from ur_arms_manager.adapters.ur.dashboard_client import DashboardClient
from ur_arms_manager.adapters.ur.script_client import ScriptClient
from ur_arms_manager.models import RobotConfig, RobotStatus


class RobotManager:
    def __init__(self, robot: RobotConfig):
        self.robot = robot
        self.dashboard = DashboardClient(robot.host, robot.dashboard_port)
        self.script = ScriptClient(robot.host, robot.script_port)

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

    def run_assigned_program(self, root_dir: Path) -> str:
        if not self.robot.assigned_program:
            raise ValueError(f"Robot '{self.robot.name}' nemá přiřazený program.")

        program_path = root_dir / self.robot.assigned_program
        if not program_path.exists():
            raise FileNotFoundError(f"Soubor neexistuje: {program_path}")

        script_text = program_path.read_text(encoding="utf-8")
        self.script.send_program(script_text)
        return f"Program odeslán do {self.robot.name}: {self.robot.assigned_program}"

    def stop_program(self) -> str:
        return self.dashboard.stop()
