from __future__ import annotations

import zipfile
from pathlib import Path

from ur_arms_manager.models import RobotConfig, RobotStatus
from ur_arms_manager.services.compatibility import CompatibilityService
from ur_arms_manager.services.library_manager import LibraryManager


def _robot() -> RobotConfig:
    return RobotConfig(
        name="robot1",
        host="127.0.0.1",
        dashboard_port=29999,
        script_port=30001,
        enabled=True,
    )


class _ReachableRobotManager:
    def __init__(self, _robot: RobotConfig):
        pass

    def status(self) -> RobotStatus:
        return RobotStatus(name="robot1", connected=True)


class _UnreachableRobotManager:
    def __init__(self, _robot: RobotConfig):
        pass

    def status(self) -> RobotStatus:
        return RobotStatus(name="robot1", connected=False, detail="connection refused")


def test_script_item_is_likely_ok(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "programs")
    script = tmp_path / "demo.script"
    script.write_text("def demo():\nend\n", encoding="utf-8")
    item = manager.add_item(str(script))

    result = CompatibilityService(manager, _ReachableRobotManager).evaluate(
        _robot(), item["program_id"]
    )

    assert result.overall_status == "ok"


def test_urp_with_installation_dependency_is_warning(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "programs")
    urp = tmp_path / "demo.urp"
    with zipfile.ZipFile(urp, "w") as archive:
        archive.writestr(
            "program.xml",
            '<Program name="Demo"><Header installationName="default.installation"/></Program>',
        )
    item = manager.add_item(str(urp))

    result = CompatibilityService(manager, _ReachableRobotManager).evaluate(
        _robot(), item["program_id"]
    )

    assert result.overall_status == "warning"
    assert any("Installation dependency detected" in f for f in result.findings)


def test_urp_parse_failure_is_warning(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "programs")
    broken = tmp_path / "broken.urp"
    broken.write_text("<Program><Broken></Program", encoding="utf-8")
    item = manager.add_item(str(broken))

    result = CompatibilityService(manager, _ReachableRobotManager).evaluate(
        _robot(), item["program_id"]
    )

    assert result.overall_status == "warning"
    assert any("URP analysis failed" in f for f in result.findings)


def test_missing_stored_file_is_blocked(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "programs")
    urp = tmp_path / "demo.urp"
    urp.write_text("<Program/>", encoding="utf-8")
    item = manager.add_item(str(urp))
    Path(item["stored_path"]).unlink()

    result = CompatibilityService(manager, _ReachableRobotManager).evaluate(
        _robot(), item["program_id"]
    )

    assert result.overall_status == "blocked"
    assert any("Stored library file is missing" in f for f in result.findings)


def test_unreachable_robot_is_warning_not_crash(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "programs")
    script = tmp_path / "demo.script"
    script.write_text("def demo():\nend\n", encoding="utf-8")
    item = manager.add_item(str(script))

    result = CompatibilityService(manager, _UnreachableRobotManager).evaluate(
        _robot(), item["program_id"]
    )

    assert result.overall_status == "warning"
    assert any("Robot is currently unreachable" in f for f in result.findings)
