from __future__ import annotations

from pathlib import Path
from typing import Dict

import yaml

from ur_arms_manager.models import RobotConfig


class RegistryError(Exception):
    pass


class RobotRegistry:
    def __init__(self, config_path: Path):
        self.config_path = Path(config_path)

    def load(self) -> dict:
        if not self.config_path.exists():
            raise RegistryError(
                f"Konfigurační soubor neexistuje: {self.config_path}. "
                "Vytvoř ho z config/robots.example.yaml"
            )

        with self.config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}

        if "robots" not in data:
            raise RegistryError("V konfiguraci chybí sekce 'robots'.")
        return data

    def save(self, data: dict) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)

    def list_robots(self) -> Dict[str, RobotConfig]:
        raw = self.load()["robots"]
        robots: Dict[str, RobotConfig] = {}
        for name, item in raw.items():
            robots[name] = RobotConfig(
                name=name,
                host=item["host"],
                dashboard_port=int(item["dashboard_port"]),
                script_port=int(item["script_port"]),
                rtde_port=int(item.get("rtde_port", 30004)),
                ssh_port=int(item.get("ssh_port", 22)),
                ssh_username=str(item.get("ssh_username", "root")),
                ssh_password=str(item.get("ssh_password", "easybot")),
                enabled=bool(item.get("enabled", True)),
                assigned_program=item.get("assigned_program"),
                home_program=item.get("home_program"),
            )
        return robots

    def get_robot(self, name: str) -> RobotConfig:
        robots = self.list_robots()
        if name not in robots:
            raise RegistryError(f"Robot '{name}' není v konfiguraci.")
        return robots[name]

    def assign_program(self, robot_name: str, program_path: str) -> None:
        data = self.load()
        robots = data["robots"]
        if robot_name not in robots:
            raise RegistryError(f"Robot '{robot_name}' není v konfiguraci.")
        robots[robot_name]["assigned_program"] = program_path
        self.save(data)

    def assign_remote_program(self, robot_name: str, robot_program_path: str) -> None:
        self.assign_program(robot_name, robot_program_path)
