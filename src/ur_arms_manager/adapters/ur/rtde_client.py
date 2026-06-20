from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class RTDEError(Exception):
    pass


@dataclass(slots=True)
class RTDESpikeStatus:
    connected: bool
    robot_mode: str = "unknown"
    runtime_state: str = "unknown"
    safety_state: str = "unknown"
    detail: str = ""


class RTDEClient:
    def __init__(self, host: str, port: int = 30004):
        self.host = host
        self.port = port

    def read_status(self) -> RTDESpikeStatus:
        if self.port != 30004:
            raise RTDEError(
                "RTDEReceiveInterface does not support custom forwarded ports; "
                f"configured RTDE port is {self.port}."
            )

        try:
            interface_cls = self._load_interface_class()
            receiver = interface_cls(self.host)
        except RTDEError:
            raise
        except Exception as exc:
            raise RTDEError(
                f"RTDE connection failed for {self.host}:{self.port}: {exc}"
            ) from exc

        try:
            connected = self._safe_call(receiver, "isConnected", default=True)
            robot_mode = self._safe_call(receiver, "getRobotMode")
            runtime_state = self._safe_call(receiver, "getRuntimeState")
            safety_state = self._safe_call(receiver, "getSafetyMode")
            return RTDESpikeStatus(
                connected=bool(connected),
                robot_mode=str(robot_mode),
                runtime_state=str(runtime_state),
                safety_state=str(safety_state),
                detail="RTDE status read succeeded" if connected else "RTDE connected flag is false",
            )
        except Exception as exc:
            raise RTDEError(
                f"RTDE status read failed for {self.host}:{self.port}: {exc}"
            ) from exc
        finally:
            disconnect = getattr(receiver, "disconnect", None)
            if callable(disconnect):
                disconnect()

    @staticmethod
    def _load_interface_class() -> type[Any]:
        try:
            module = __import__("rtde_receive")
        except ModuleNotFoundError as exc:
            raise RTDEError(
                "RTDE Python dependency is not installed. Install package 'ur-rtde' to use the RTDE spike."
            ) from exc

        interface_cls = getattr(module, "RTDEReceiveInterface", None)
        if interface_cls is None:
            raise RTDEError("rtde_receive.RTDEReceiveInterface is unavailable.")
        return interface_cls

    @staticmethod
    def _safe_call(receiver: Any, method_name: str, default: Any = "unknown") -> Any:
        method = getattr(receiver, method_name, None)
        if not callable(method):
            return default
        try:
            return method()
        except Exception:
            return default
