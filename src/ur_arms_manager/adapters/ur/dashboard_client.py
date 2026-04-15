from __future__ import annotations

import socket
from contextlib import closing


class DashboardError(Exception):
    pass


class DashboardClient:
    def __init__(self, host: str, port: int, timeout: float = 2.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def send_command(self, command: str) -> str:
        try:
            with closing(socket.create_connection((self.host, self.port), timeout=self.timeout)) as sock:
                sock.settimeout(self.timeout)
                _ = self._recv_line(sock)  # welcome line
                sock.sendall((command.strip() + "\n").encode("ascii"))
                return self._recv_line(sock)
        except socket.timeout as exc:
            raise DashboardError(
                f"Timeout při komunikaci s dashboardem {self.host}:{self.port}"
            ) from exc
        except OSError as exc:
            raise DashboardError(
                f"Nelze se připojit k dashboardu {self.host}:{self.port}: {exc}"
            ) from exc

    def get_robotmode(self) -> str:
        return self.send_command("robotmode")

    def get_program_state(self) -> str:
        return self.send_command("programState")

    def get_safety_status(self) -> str:
        try:
            return self.send_command("safetystatus")
        except Exception:
            return "unknown"

    def stop(self) -> str:
        return self.send_command("stop")

    def play(self) -> str:
        return self.send_command("play")

    def load(self, program_path: str) -> str:
        return self.send_command(f"load {program_path}")

    def power_on(self) -> str:
        return self.send_command("power on")

    def brake_release(self) -> str:
        return self.send_command("brake release")

    def power_off(self) -> str:
        return self.send_command("power off")

    @staticmethod
    def _recv_line(sock: socket.socket) -> str:
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        return data.decode("utf-8", errors="replace").strip()
