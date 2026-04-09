from __future__ import annotations

import socket
from contextlib import closing


class DashboardClient:
    def __init__(self, host: str, port: int, timeout: float = 2.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def send_command(self, command: str) -> str:
        with closing(socket.create_connection((self.host, self.port), timeout=self.timeout)) as sock:
            sock.settimeout(self.timeout)
            _ = self._recv_line(sock)  # welcome line
            sock.sendall((command.strip() + "\n").encode("ascii"))
            return self._recv_line(sock)

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

    @staticmethod
    def _recv_line(sock: socket.socket) -> str:
        data = b""
        while not data.endswith(b"\n"):
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        return data.decode("utf-8", errors="replace").strip()
