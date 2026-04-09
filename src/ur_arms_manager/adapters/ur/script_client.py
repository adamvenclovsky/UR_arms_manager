from __future__ import annotations

import socket
from contextlib import closing


class ScriptClient:
    def __init__(self, host: str, port: int, timeout: float = 2.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def send_program(self, script_text: str) -> None:
        payload = script_text.strip() + "\n"
        with closing(socket.create_connection((self.host, self.port), timeout=self.timeout)) as sock:
            sock.settimeout(self.timeout)
            sock.sendall(payload.encode("utf-8"))
            try:
                sock.recv(79)
            except Exception:
                pass
