from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ur_arms_manager.models import RobotConfig
from ur_arms_manager.services.library_manager import LibraryError, LibraryManager
from ur_arms_manager.services.robot_manager import RobotManager


@dataclass(slots=True)
class CompatibilityResult:
    overall_status: str
    summary: str
    findings: list[str]


class CompatibilityService:
    def __init__(
        self,
        library: LibraryManager,
        robot_manager_factory: Callable[[RobotConfig], RobotManager] = RobotManager,
    ):
        self.library = library
        self.robot_manager_factory = robot_manager_factory

    def evaluate(self, robot: RobotConfig, program_id: str) -> CompatibilityResult:
        findings: list[str] = []
        severity = 0  # 0=ok, 1=warning, 2=blocked

        item_available = True
        try:
            item = self.library.inspect_item_enriched(program_id)
        except LibraryError as exc:
            item_available = False
            item = {"extension": "", "urp_analysis": {}}
            severity = max(severity, 2)
            findings.append(f"Stored library file is missing: {exc}")
        extension = str(item.get("extension", "")).lower()

        # 1) Stored file existence (hard blocker).
        if item_available:
            try:
                _ = self.library.get_stored_file(program_id)
            except Exception as exc:
                severity = max(severity, 2)
                findings.append(f"Stored library file is missing: {exc}")

        # 2) File extension baseline.
        if extension == "script":
            findings.append("File type .script is generally compatible for direct script execution.")
        elif extension == "urp":
            analysis = item.get("urp_analysis", {})
            parse_success = bool(analysis.get("parse_success"))

            # 5) Parse failure -> warning.
            if not parse_success:
                severity = max(severity, 1)
                findings.append(
                    "URP analysis failed; compatibility cannot be fully validated."
                )
                if analysis.get("parse_error"):
                    findings.append(f"URP parse detail: {analysis['parse_error']}")

            # 3) URCap usage -> warning.
            urcaps = analysis.get("urcap_names") or []
            if urcaps:
                severity = max(severity, 1)
                findings.append(f"URCap dependency detected: {', '.join(str(x) for x in urcaps)}")

            # 4) Installation dependency -> warning.
            installation_name = analysis.get("installation_name")
            if installation_name:
                severity = max(severity, 1)
                findings.append(f"Installation dependency detected: {installation_name}")
        else:
            severity = max(severity, 1)
            findings.append(f"Unknown file extension '{extension or '<none>'}'; compatibility uncertain.")

        # 6) Robot reachability check (warning unless already blocked).
        try:
            status = self.robot_manager_factory(robot).status()
            if not status.connected:
                severity = max(severity, 1)
                detail = status.detail or "unknown reason"
                findings.append(f"Robot is currently unreachable: {detail}")
        except Exception as exc:
            severity = max(severity, 1)
            findings.append(f"Robot reachability check failed: {exc}")

        if severity == 2:
            overall_status = "blocked"
            summary = "Compatibility check found blocking issues."
        elif severity == 1:
            overall_status = "warning"
            summary = "Compatibility check found warnings."
        else:
            overall_status = "ok"
            summary = "Compatibility check found no obvious issues."

        return CompatibilityResult(
            overall_status=overall_status,
            summary=summary,
            findings=findings,
        )
