from __future__ import annotations

from ur_arms_manager.models import RobotConfig
from ur_arms_manager.services.monitoring import get_robot_monitoring_status


def _robot() -> RobotConfig:
    return RobotConfig(
        name="robot1",
        host="127.0.0.1",
        dashboard_port=29999,
        script_port=30001,
        assigned_program="/programs/demo.urp",
    )


def test_monitoring_uses_rtde_when_available() -> None:
    class FakeDashboardClient:
        def get_robotmode(self) -> str:
            raise AssertionError("dashboard should not be used")

    class FakeRTDEClient:
        def __init__(self, host: str):
            assert host == "127.0.0.1"

        def read_status(self):
            class Status:
                connected = True
                robot_mode = "RUNNING"
                runtime_state = "PLAYING"
                safety_state = "NORMAL"

            return Status()

    status = get_robot_monitoring_status(
        _robot(),
        dashboard_client=FakeDashboardClient(),
        rtde_client_factory=FakeRTDEClient,
    )

    assert status.connected is True
    assert status.robotmode == "RUNNING"
    assert status.program_running == "PLAYING"
    assert status.safety_status == "NORMAL"
    assert status.monitoring_source == "rtde"


def test_monitoring_falls_back_to_dashboard_when_rtde_fails() -> None:
    class FakeDashboardClient:
        def get_robotmode(self) -> str:
            return "Robotmode: RUNNING"

        def get_program_state(self) -> str:
            return "PLAYING"

        def get_safety_status(self) -> str:
            return "NORMAL"

    class FakeRTDEClient:
        def __init__(self, _host: str):
            pass

        def read_status(self):
            raise Exception("rtde unavailable")

    status = get_robot_monitoring_status(
        _robot(),
        dashboard_client=FakeDashboardClient(),
        rtde_client_factory=FakeRTDEClient,
    )

    assert status.connected is True
    assert status.robotmode == "Robotmode: RUNNING"
    assert status.program_running == "PLAYING"
    assert status.safety_status == "NORMAL"
    assert status.monitoring_source == "dashboard"


def test_monitoring_returns_clean_failure_when_both_sources_fail() -> None:
    class FakeDashboardClient:
        def get_robotmode(self) -> str:
            raise RuntimeError("dashboard timeout")

        def get_program_state(self) -> str:
            return "unknown"

        def get_safety_status(self) -> str:
            return "unknown"

    class FakeRTDEClient:
        def __init__(self, _host: str):
            pass

        def read_status(self):
            class Status:
                connected = False
                detail = "rtde disconnected"

            return Status()

    status = get_robot_monitoring_status(
        _robot(),
        dashboard_client=FakeDashboardClient(),
        rtde_client_factory=FakeRTDEClient,
    )

    assert status.connected is False
    assert status.monitoring_source == "dashboard"
    assert "RTDE failed: rtde disconnected" in status.detail
    assert "Dashboard failed: dashboard timeout" in status.detail
