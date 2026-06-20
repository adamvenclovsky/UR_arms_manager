from __future__ import annotations

import socket
from contextlib import closing


class DashboardError(Exception):
    pass


class DashboardClient:
    def __init__(
        self,
        host: str,
        port: int,
        timeout: float = 2.0,
        load_timeout: float = 15.0,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.load_timeout = load_timeout

    def send_command(self, command: str, timeout: float | None = None) -> str:
        command_timeout = self.timeout if timeout is None else timeout
        try:
            with closing(
                socket.create_connection((self.host, self.port), timeout=command_timeout)
            ) as sock:
                sock.settimeout(command_timeout)
                _ = self._recv_line(sock)  # welcome line
                sock.sendall((command.strip() + "\n").encode("ascii"))
                return self._recv_line(sock)
        except socket.timeout as exc:
            raise DashboardError(
                f"Dashboard communication timed out for {self.host}:{self.port}"
            ) from exc
        except OSError as exc:
            raise DashboardError(
                f"Cannot connect to Dashboard at {self.host}:{self.port}: {exc}"
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

    def pause(self) -> str:
        return self.send_command("pause")

    def play(self) -> str:
        return self.send_command("play")

    def close_popup(self) -> str:
        return self.send_command("close popup")

    def close_safety_popup(self) -> str:
        return self.send_command("close safety popup")

    def unlock_protective_stop(self) -> str:
        return self.send_command("unlock protective stop")

    def is_in_remote_control(self) -> str:
        return self.send_command("is in remote control")

    def get_loaded_program(self) -> str:
        return self.send_command("get loaded program")

    def load(self, program_path: str) -> str:
        # PolyScope may need several seconds to parse a bundle and activate its
        # installation. Keep routine status commands responsive while allowing
        # load enough time to return its actual result.
        return self.send_command(f"load {program_path}", timeout=self.load_timeout)

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
