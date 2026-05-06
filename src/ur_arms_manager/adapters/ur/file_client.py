from __future__ import annotations

import socket
from pathlib import Path
from pathlib import PurePosixPath
import stat

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
        return [entry["name"] for entry in self.list_dir_entries(remote_dir)]

    def list_dir_entries(self, remote_dir: str) -> list[dict[str, str | bool]]:
        ssh, sftp = self._open_sftp()
        try:
            entries: list[dict[str, str | bool]] = []
            for entry in sorted(sftp.listdir_attr(remote_dir), key=lambda item: item.filename.lower()):
                entries.append(
                    {
                        "name": entry.filename,
                        "is_dir": stat.S_ISDIR(entry.st_mode),
                        "kind": "directory" if stat.S_ISDIR(entry.st_mode) else "file",
                    }
                )
            return entries
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

    def upload_tree(self, local_source_dir: Path, remote_destination_dir: str) -> list[dict[str, str]]:
        source_dir = Path(local_source_dir)
        if not source_dir.exists() or not source_dir.is_dir():
            raise FileClientError(f"Lokální adresář neexistuje: {source_dir}")

        ssh, sftp = self._open_sftp()
        try:
            destination_dir = self._normalize_remote_dir(remote_destination_dir)
            self._ensure_remote_dir(sftp, destination_dir)
            results: list[dict[str, str]] = []
            for local_file in sorted(source_dir.rglob("*")):
                if not local_file.is_file():
                    continue
                relative_path = local_file.relative_to(source_dir).as_posix()
                remote_path = self._join_remote_path(destination_dir, relative_path)
                self._ensure_remote_dir(sftp, str(PurePosixPath(remote_path).parent))
                sftp.put(str(local_file), remote_path)
                results.append(
                    {
                        "local_path": str(local_file),
                        "relative_path": relative_path,
                        "remote_path": remote_path,
                    }
                )
            return results
        except OSError as exc:
            raise FileClientError(
                f"Nahrání adresáře '{source_dir}' na remote cestu '{remote_destination_dir}' selhalo: {exc}"
            ) from exc
        finally:
            sftp.close()
            ssh.close()

    def create_dir(self, remote_dir: str) -> str:
        ssh, sftp = self._open_sftp()
        try:
            sftp.mkdir(remote_dir)
            return remote_dir
        except FileNotFoundError as exc:
            raise FileClientError(f"Nadřazená remote cesta neexistuje: {remote_dir}") from exc
        except OSError as exc:
            raise FileClientError(f"Vytvoření remote adresáře '{remote_dir}' selhalo: {exc}") from exc
        finally:
            sftp.close()
            ssh.close()

    def remove_file(self, remote_path: str) -> str:
        ssh, sftp = self._open_sftp()
        try:
            sftp.remove(remote_path)
            return remote_path
        except FileNotFoundError as exc:
            raise FileClientError(f"Remote soubor neexistuje: {remote_path}") from exc
        except IsADirectoryError as exc:
            raise FileClientError(f"Remote cesta je adresář, ne soubor: {remote_path}") from exc
        except OSError as exc:
            raise FileClientError(f"Odstranění remote souboru '{remote_path}' selhalo: {exc}") from exc
        finally:
            sftp.close()
            ssh.close()

    def remove_dir(self, remote_dir: str) -> str:
        ssh, sftp = self._open_sftp()
        try:
            remote_dir = self._normalize_remote_dir(remote_dir)
            if remote_dir == "/":
                raise FileClientError("Nelze odstranit kořenový remote adresář.")
            self._remove_remote_tree(sftp, remote_dir)
            sftp.rmdir(remote_dir)
            return remote_dir
        except FileClientError:
            raise
        except FileNotFoundError as exc:
            raise FileClientError(f"Remote adresář neexistuje: {remote_dir}") from exc
        except OSError as exc:
            raise FileClientError(f"Odstranění remote adresáře '{remote_dir}' selhalo: {exc}") from exc
        finally:
            sftp.close()
            ssh.close()

    def rename_path(self, source_path: str, destination_path: str) -> str:
        ssh, sftp = self._open_sftp()
        try:
            sftp.rename(source_path, destination_path)
            return destination_path
        except FileNotFoundError as exc:
            raise FileClientError(f"Remote cesta neexistuje: {source_path}") from exc
        except OSError as exc:
            raise FileClientError(
                f"Přesun nebo přejmenování remote cesty '{source_path}' selhalo: {exc}"
            ) from exc
        finally:
            sftp.close()
            ssh.close()

    def copy_file(self, remote_source: str, remote_destination: str) -> str:
        ssh, sftp = self._open_sftp()
        try:
            with sftp.open(remote_source, "rb") as source_handle:
                with sftp.open(remote_destination, "wb") as destination_handle:
                    while True:
                        chunk = source_handle.read(1024 * 1024)
                        if not chunk:
                            break
                        destination_handle.write(chunk)
            return remote_destination
        except FileNotFoundError as exc:
            raise FileClientError(f"Remote soubor neexistuje: {remote_source}") from exc
        except OSError as exc:
            raise FileClientError(
                f"Kopírování remote souboru '{remote_source}' selhalo: {exc}"
            ) from exc
        finally:
            sftp.close()
            ssh.close()

    def _ensure_remote_dir(self, sftp: paramiko.SFTPClient, remote_dir: str) -> None:
        remote_dir = self._normalize_remote_dir(remote_dir)
        if remote_dir == "/":
            return

        parts = [part for part in PurePosixPath(remote_dir).parts if part != "/"]
        current = ""
        for part in parts:
            current = self._join_remote_path(current or "/", part)
            try:
                sftp.stat(current)
            except FileNotFoundError:
                sftp.mkdir(current)

    def _remove_remote_tree(self, sftp: paramiko.SFTPClient, remote_dir: str) -> None:
        for entry in sftp.listdir_attr(remote_dir):
            child_path = self._join_remote_path(remote_dir, entry.filename)
            if stat.S_ISDIR(entry.st_mode):
                self._remove_remote_tree(sftp, child_path)
                sftp.rmdir(child_path)
            else:
                sftp.remove(child_path)

    def _normalize_remote_dir(self, remote_dir: str) -> str:
        candidate = str(remote_dir or "").strip() or "/"
        if not candidate.startswith("/"):
            candidate = f"/{candidate}"
        if len(candidate) > 1:
            candidate = candidate.rstrip("/")
        return candidate

    def _join_remote_path(self, remote_dir: str, child_path: str) -> str:
        remote_dir = self._normalize_remote_dir(remote_dir)
        child = str(child_path).strip("/")
        if remote_dir == "/":
            return f"/{child}"
        return f"{remote_dir}/{child}"
