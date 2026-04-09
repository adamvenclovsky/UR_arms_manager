from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(slots=True)
class RobotConfig:
    name: str
    host: str
    dashboard_port: int
    script_port: int
    ssh_port: int = 22
    ssh_username: str = "root"
    ssh_password: str = "easybot"
    enabled: bool = True
    assigned_program: Optional[str] = None


@dataclass(slots=True)
class RobotStatus:
    name: str
    connected: bool
    robotmode: str = "unknown"
    program_running: str = "unknown"
    safety_status: str = "unknown"
    assigned_program: Optional[str] = None
    detail: str = ""


@dataclass(slots=True)
class ProgramAssignment:
    robot_name: str
    program_path: Path
