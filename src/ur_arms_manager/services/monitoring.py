from __future__ import annotations

from ur_arms_manager.adapters.ur.dashboard_client import DashboardClient
from ur_arms_manager.adapters.ur.rtde_client import RTDEClient, RTDEError
from ur_arms_manager.models import RobotConfig, RobotStatus


def get_robot_monitoring_status(
    robot: RobotConfig,
    dashboard_client: DashboardClient | None = None,
    rtde_client_factory=RTDEClient,
) -> RobotStatus:
    if not robot.enabled:
        return RobotStatus(
            name=robot.name,
            connected=False,
            assigned_program=robot.assigned_program,
            detail="Robot is disabled in config.",
            monitoring_source="disabled",
        )

    rtde_error_detail = ""

    try:
        rtde_status = rtde_client_factory(robot.host, robot.rtde_port).read_status()
        if rtde_status.connected:
            return RobotStatus(
                name=robot.name,
                connected=True,
                robotmode=rtde_status.robot_mode,
                program_running=rtde_status.runtime_state,
                safety_status=rtde_status.safety_state,
                assigned_program=robot.assigned_program,
                monitoring_source="rtde",
            )
        rtde_error_detail = rtde_status.detail or "RTDE connected flag is false"
    except RTDEError as exc:
        rtde_error_detail = str(exc)
    except Exception as exc:
        rtde_error_detail = str(exc)

    dashboard = dashboard_client or DashboardClient(robot.host, robot.dashboard_port)
    try:
        robotmode = dashboard.get_robotmode()
        program_running = dashboard.get_program_state()
        safety_status = dashboard.get_safety_status()
        return RobotStatus(
            name=robot.name,
            connected=True,
            robotmode=robotmode,
            program_running=program_running,
            safety_status=safety_status,
            assigned_program=robot.assigned_program,
            monitoring_source="dashboard",
        )
    except Exception as exc:
        detail = str(exc)
        if rtde_error_detail:
            detail = f"RTDE failed: {rtde_error_detail}; Dashboard failed: {exc}"
        return RobotStatus(
            name=robot.name,
            connected=False,
            assigned_program=robot.assigned_program,
            detail=detail,
            monitoring_source="dashboard",
        )
