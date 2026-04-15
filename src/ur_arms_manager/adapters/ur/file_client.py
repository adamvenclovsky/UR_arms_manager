from __future__ import annotations

import socket
from pathlib import Path

import paramiko


class FileClientError(Exception):
    pass


class FileClient:
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 22,
        timeout: float = 5.0,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout

    def _open_sftp(self) -> tuple[paramiko.SSHClient, paramiko.SFTPClient]:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=self.timeout,
                banner_timeout=self.timeout,
                auth_timeout=self.timeout,
            )
            return ssh, ssh.open_sftp()
        except paramiko.AuthenticationException as exc:
            ssh.close()
            raise FileClientError(
                f"SSH autentizace selhala pro {self.username}@{self.host}:{self.port}"
            ) from exc
        except (paramiko.SSHException, socket.timeout, OSError) as exc:
            ssh.close()
            raise FileClientError(
                f"Nelze se připojit na SSH {self.host}:{self.port}: {exc}"
            ) from exc

    def list_dir(self, remote_dir: str) -> list[str]:
        ssh, sftp = self._open_sftp()
        try:
            return sorted(sftp.listdir(remote_dir))
        except FileNotFoundError as exc:
            raise FileClientError(f"Remote adresář neexistuje: {remote_dir}") from exc
        except OSError as exc:
            raise FileClientError(f"Nelze vypsat remote adresář '{remote_dir}': {exc}") from exc
        finally:
            sftp.close()
            ssh.close()

    def exists(self, remote_path: str) -> bool:
        ssh, sftp = self._open_sftp()
        try:
            sftp.stat(remote_path)
            return True
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise FileClientError(f"Nelze ověřit remote cestu '{remote_path}': {exc}") from exc
        finally:
            sftp.close()
            ssh.close()

    def pull_file(self, remote_path: str, local_destination: Path) -> Path:
        destination = Path(local_destination)
        if destination.exists() and destination.is_dir():
            destination = destination / Path(remote_path).name
        destination.parent.mkdir(parents=True, exist_ok=True)

        ssh, sftp = self._open_sftp()
        try:
            sftp.get(remote_path, str(destination))
            return destination
        except FileNotFoundError as exc:
            raise FileClientError(f"Remote soubor neexistuje: {remote_path}") from exc
        except OSError as exc:
            raise FileClientError(
                f"Stažení remote souboru '{remote_path}' selhalo: {exc}"
            ) from exc
        finally:
            sftp.close()
            ssh.close()

    def upload_file(self, local_source: Path, remote_destination: str) -> str:
        source = Path(local_source)
        if not source.exists() or not source.is_file():
            raise FileClientError(f"Lokální soubor neexistuje: {source}")

        ssh, sftp = self._open_sftp()
        try:
            sftp.put(str(source), remote_destination)
            return remote_destination
        except FileNotFoundError as exc:
            raise FileClientError(
                f"Remote cílová cesta neexistuje: {remote_destination}"
            ) from exc
        except OSError as exc:
            raise FileClientError(
                f"Nahrání souboru na remote cestu '{remote_destination}' selhalo: {exc}"
            ) from exc
        finally:
            sftp.close()
            ssh.close()
