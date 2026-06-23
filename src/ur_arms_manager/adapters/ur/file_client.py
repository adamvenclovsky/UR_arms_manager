from __future__ import annotations

import socket
import stat
from pathlib import Path, PurePosixPath

import paramiko


class FileClientError(Exception):
    pass


REMOTE_PROGRAM_ROOTS = (
    PurePosixPath("/programs"),
    PurePosixPath("/ursim/programs"),
    PurePosixPath("/ursim/programs.UR5"),
)


def validate_remote_program_path(remote_path: str, *, allow_root: bool = True) -> str:
    raw = str(remote_path or "")
    if not raw or raw != raw.strip():
        raise FileClientError("Remote path must be a non-empty absolute path without surrounding whitespace.")
    if any(ord(char) < 32 or ord(char) == 127 for char in raw):
        raise FileClientError("Remote path contains control characters.")
    if "\\" in raw:
        raise FileClientError("Remote paths must use POSIX '/' separators.")
    path = PurePosixPath(raw)
    if not path.is_absolute() or ".." in path.parts:
        raise FileClientError(f"Remote path is not a safe absolute program path: {raw}")
    normalized = PurePosixPath("/", *[part for part in path.parts if part not in {"/", "."}])
    matching_root = next(
        (root for root in REMOTE_PROGRAM_ROOTS if normalized == root or root in normalized.parents),
        None,
    )
    if matching_root is None:
        raise FileClientError(
            "Remote path must remain under /programs, /ursim/programs, or /ursim/programs.UR5."
        )
    if not allow_root and normalized == matching_root:
        raise FileClientError(f"Operation is not allowed on remote program root: {normalized}")
    return str(normalized)


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
        ssh.load_system_host_keys()
        if self.host in {"127.0.0.1", "localhost", "::1"}:
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        else:
            ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
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
                f"SSH authentication failed for {self.username}@{self.host}:{self.port}"
            ) from exc
        except (paramiko.SSHException, socket.timeout, OSError) as exc:
            ssh.close()
            raise FileClientError(
                f"Cannot connect to SSH at {self.host}:{self.port}: {exc}"
            ) from exc

    def list_dir(self, remote_dir: str) -> list[str]:
        return [entry["name"] for entry in self.list_dir_entries(remote_dir)]

    def list_dir_entries(self, remote_dir: str) -> list[dict[str, str | bool]]:
        remote_dir = validate_remote_program_path(remote_dir)
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
            raise FileClientError(f"Remote directory does not exist: {remote_dir}") from exc
        except OSError as exc:
            raise FileClientError(f"Cannot list remote directory '{remote_dir}': {exc}") from exc
        finally:
            sftp.close()
            ssh.close()

    def exists(self, remote_path: str) -> bool:
        remote_path = validate_remote_program_path(remote_path)
        ssh, sftp = self._open_sftp()
        try:
            sftp.stat(remote_path)
            return True
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise FileClientError(f"Cannot check remote path '{remote_path}': {exc}") from exc
        finally:
            sftp.close()
            ssh.close()

    def pull_file(self, remote_path: str, local_destination: Path) -> Path:
        remote_path = validate_remote_program_path(remote_path, allow_root=False)
        destination = Path(local_destination)
        if destination.exists() and destination.is_dir():
            destination = destination / Path(remote_path).name
        destination.parent.mkdir(parents=True, exist_ok=True)

        ssh, sftp = self._open_sftp()
        try:
            sftp.get(remote_path, str(destination))
            return destination
        except FileNotFoundError as exc:
            raise FileClientError(f"Remote file does not exist: {remote_path}") from exc
        except OSError as exc:
            raise FileClientError(
                f"Downloading remote file '{remote_path}' failed: {exc}"
            ) from exc
        finally:
            sftp.close()
            ssh.close()

    def upload_file(self, local_source: Path, remote_destination: str) -> str:
        remote_destination = validate_remote_program_path(remote_destination, allow_root=False)
        source = Path(local_source)
        if not source.exists() or not source.is_file():
            raise FileClientError(f"Local file does not exist: {source}")

        ssh, sftp = self._open_sftp()
        try:
            sftp.put(str(source), remote_destination)
            return remote_destination
        except FileNotFoundError as exc:
            raise FileClientError(
                f"Remote destination does not exist: {remote_destination}"
            ) from exc
        except OSError as exc:
            raise FileClientError(
                f"Uploading file to remote path '{remote_destination}' failed: {exc}"
            ) from exc
        finally:
            sftp.close()
            ssh.close()

    def upload_tree(self, local_source_dir: Path, remote_destination_dir: str) -> list[dict[str, str]]:
        source_dir = Path(local_source_dir)
        if not source_dir.exists() or not source_dir.is_dir():
            raise FileClientError(f"Local directory does not exist: {source_dir}")

        ssh, sftp = self._open_sftp()
        try:
            destination_dir = validate_remote_program_path(
                remote_destination_dir, allow_root=False
            )
            self._ensure_remote_dir(sftp, destination_dir)
            results: list[dict[str, str]] = []
            for local_file in sorted(source_dir.rglob("*")):
                if not local_file.is_file():
                    continue
                if local_file.is_symlink() or source_dir.resolve() not in local_file.resolve().parents:
                    raise FileClientError(
                        f"Bundle contains a file outside its source directory: {local_file}"
                    )
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
                f"Uploading directory '{source_dir}' to '{remote_destination_dir}' failed: {exc}"
            ) from exc
        finally:
            sftp.close()
            ssh.close()

    def create_dir(self, remote_dir: str) -> str:
        remote_dir = validate_remote_program_path(remote_dir, allow_root=False)
        ssh, sftp = self._open_sftp()
        try:
            sftp.mkdir(remote_dir)
            return remote_dir
        except FileNotFoundError as exc:
            raise FileClientError(f"Remote parent directory does not exist: {remote_dir}") from exc
        except OSError as exc:
            raise FileClientError(f"Creating remote directory '{remote_dir}' failed: {exc}") from exc
        finally:
            sftp.close()
            ssh.close()

    def remove_file(self, remote_path: str) -> str:
        remote_path = validate_remote_program_path(remote_path, allow_root=False)
        ssh, sftp = self._open_sftp()
        try:
            sftp.remove(remote_path)
            return remote_path
        except FileNotFoundError as exc:
            raise FileClientError(f"Remote file does not exist: {remote_path}") from exc
        except IsADirectoryError as exc:
            raise FileClientError(f"Remote path is a directory, not a file: {remote_path}") from exc
        except OSError as exc:
            raise FileClientError(f"Removing remote file '{remote_path}' failed: {exc}") from exc
        finally:
            sftp.close()
            ssh.close()

    def remove_dir(self, remote_dir: str) -> str:
        remote_dir = validate_remote_program_path(remote_dir, allow_root=False)
        ssh, sftp = self._open_sftp()
        try:
            self._remove_remote_tree(sftp, remote_dir)
            sftp.rmdir(remote_dir)
            return remote_dir
        except FileClientError:
            raise
        except FileNotFoundError as exc:
            raise FileClientError(f"Remote directory does not exist: {remote_dir}") from exc
        except OSError as exc:
            raise FileClientError(f"Removing remote directory '{remote_dir}' failed: {exc}") from exc
        finally:
            sftp.close()
            ssh.close()

    def rename_path(self, source_path: str, destination_path: str) -> str:
        source_path = validate_remote_program_path(source_path, allow_root=False)
        destination_path = validate_remote_program_path(destination_path, allow_root=False)
        ssh, sftp = self._open_sftp()
        try:
            sftp.rename(source_path, destination_path)
            return destination_path
        except FileNotFoundError as exc:
            raise FileClientError(f"Remote path does not exist: {source_path}") from exc
        except OSError as exc:
            raise FileClientError(
                f"Moving or renaming remote path '{source_path}' failed: {exc}"
            ) from exc
        finally:
            sftp.close()
            ssh.close()

    def copy_file(self, remote_source: str, remote_destination: str) -> str:
        remote_source = validate_remote_program_path(remote_source, allow_root=False)
        remote_destination = validate_remote_program_path(remote_destination, allow_root=False)
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
            raise FileClientError(f"Remote file does not exist: {remote_source}") from exc
        except OSError as exc:
            raise FileClientError(
                f"Copying remote file '{remote_source}' failed: {exc}"
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
