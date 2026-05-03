from __future__ import annotations

from pathlib import Path
import stat

from ur_arms_manager.adapters.ur.file_client import FileClient, FileClientError


def test_pull_file_into_existing_directory_returns_full_saved_path(
    tmp_path: Path, monkeypatch
) -> None:
    calls: dict[str, str] = {}

    class FakeSSHClient:
        def close(self) -> None:
            pass

    class FakeSFTPClient:
        def get(self, remote_path: str, local_path: str) -> None:
            calls["remote_path"] = remote_path
            calls["local_path"] = local_path

        def close(self) -> None:
            pass

    def fake_open_sftp(self):
        return FakeSSHClient(), FakeSFTPClient()

    monkeypatch.setattr(FileClient, "_open_sftp", fake_open_sftp)
    client = FileClient(host="127.0.0.1", username="root", password="easybot")

    destination_dir = tmp_path / "downloads"
    destination_dir.mkdir(parents=True, exist_ok=True)
    saved = client.pull_file("/programs/test1.urp", destination_dir)

    expected = destination_dir / "test1.urp"
    assert saved == expected
    assert calls["remote_path"] == "/programs/test1.urp"
    assert calls["local_path"] == str(expected)


def test_list_dir_entries_returns_names_and_directory_flags(monkeypatch) -> None:
    class FakeSSHClient:
        def close(self) -> None:
            pass

    class Attr:
        def __init__(self, filename: str, is_dir: bool):
            self.filename = filename
            self.st_mode = stat.S_IFDIR if is_dir else stat.S_IFREG

    class FakeSFTPClient:
        def listdir_attr(self, remote_dir: str):
            assert remote_dir == "/programs"
            return [Attr("job.urp", False), Attr("subdir", True)]

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        FileClient,
        "_open_sftp",
        lambda self: (FakeSSHClient(), FakeSFTPClient()),
    )
    client = FileClient(host="127.0.0.1", username="root", password="easybot")

    entries = client.list_dir_entries("/programs")

    assert entries == [
        {"name": "job.urp", "is_dir": False, "kind": "file"},
        {"name": "subdir", "is_dir": True, "kind": "directory"},
    ]


def test_create_dir_calls_sftp_mkdir(monkeypatch) -> None:
    calls: dict[str, str] = {}

    class FakeSSHClient:
        def close(self) -> None:
            pass

    class FakeSFTPClient:
        def mkdir(self, remote_dir: str) -> None:
            calls["remote_dir"] = remote_dir

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        FileClient,
        "_open_sftp",
        lambda self: (FakeSSHClient(), FakeSFTPClient()),
    )
    client = FileClient(host="127.0.0.1", username="root", password="easybot")

    result = client.create_dir("/programs/new_folder")

    assert result == "/programs/new_folder"
    assert calls["remote_dir"] == "/programs/new_folder"


def test_remove_file_calls_sftp_remove(monkeypatch) -> None:
    calls: dict[str, str] = {}

    class FakeSSHClient:
        def close(self) -> None:
            pass

    class FakeSFTPClient:
        def remove(self, remote_path: str) -> None:
            calls["remote_path"] = remote_path

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        FileClient,
        "_open_sftp",
        lambda self: (FakeSSHClient(), FakeSFTPClient()),
    )
    client = FileClient(host="127.0.0.1", username="root", password="easybot")

    result = client.remove_file("/programs/demo.urp")

    assert result == "/programs/demo.urp"
    assert calls["remote_path"] == "/programs/demo.urp"


def test_remove_dir_calls_sftp_rmdir(monkeypatch) -> None:
    calls: dict[str, str] = {}

    class FakeSSHClient:
        def close(self) -> None:
            pass

    class FakeSFTPClient:
        def rmdir(self, remote_dir: str) -> None:
            calls["remote_dir"] = remote_dir

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        FileClient,
        "_open_sftp",
        lambda self: (FakeSSHClient(), FakeSFTPClient()),
    )
    client = FileClient(host="127.0.0.1", username="root", password="easybot")

    result = client.remove_dir("/programs/old_folder")

    assert result == "/programs/old_folder"
    assert calls["remote_dir"] == "/programs/old_folder"


def test_rename_path_calls_sftp_rename(monkeypatch) -> None:
    calls: dict[str, str] = {}

    class FakeSSHClient:
        def close(self) -> None:
            pass

    class FakeSFTPClient:
        def rename(self, source_path: str, destination_path: str) -> None:
            calls["source"] = source_path
            calls["destination"] = destination_path

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        FileClient,
        "_open_sftp",
        lambda self: (FakeSSHClient(), FakeSFTPClient()),
    )
    client = FileClient(host="127.0.0.1", username="root", password="easybot")

    result = client.rename_path("/programs/demo.urp", "/programs/archive/demo.urp")

    assert result == "/programs/archive/demo.urp"
    assert calls["source"] == "/programs/demo.urp"
    assert calls["destination"] == "/programs/archive/demo.urp"


def test_copy_file_streams_remote_contents(monkeypatch) -> None:
    writes: list[bytes] = []

    class FakeSSHClient:
        def close(self) -> None:
            pass

    class FakeReader:
        def __init__(self):
            self._chunks = [b"abc", b"def", b""]

        def read(self, _size: int) -> bytes:
            return self._chunks.pop(0)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeWriter:
        def write(self, chunk: bytes) -> None:
            writes.append(chunk)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeSFTPClient:
        def open(self, remote_path: str, mode: str):
            if mode == "rb":
                assert remote_path == "/programs/source.urp"
                return FakeReader()
            assert remote_path == "/programs/copy.urp"
            assert mode == "wb"
            return FakeWriter()

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        FileClient,
        "_open_sftp",
        lambda self: (FakeSSHClient(), FakeSFTPClient()),
    )
    client = FileClient(host="127.0.0.1", username="root", password="easybot")

    result = client.copy_file("/programs/source.urp", "/programs/copy.urp")

    assert result == "/programs/copy.urp"
    assert writes == [b"abc", b"def"]


def test_remove_missing_file_raises_clean_error(monkeypatch) -> None:
    class FakeSSHClient:
        def close(self) -> None:
            pass

    class FakeSFTPClient:
        def remove(self, _remote_path: str) -> None:
            raise FileNotFoundError("missing")

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        FileClient,
        "_open_sftp",
        lambda self: (FakeSSHClient(), FakeSFTPClient()),
    )
    client = FileClient(host="127.0.0.1", username="root", password="easybot")

    try:
        client.remove_file("/programs/missing.urp")
        assert False, "Expected FileClientError"
    except FileClientError as exc:
        assert "Remote soubor neexistuje" in str(exc)


def test_upload_tree_uploads_files_with_relative_paths(tmp_path: Path, monkeypatch) -> None:
    uploads: list[tuple[str, str]] = []
    mkdirs: list[str] = []

    class FakeSSHClient:
        def close(self) -> None:
            pass

    class FakeSFTPClient:
        def stat(self, remote_path: str) -> None:
            if remote_path not in {"/", "/programs", "/programs/jobs"}:
                raise FileNotFoundError(remote_path)

        def mkdir(self, remote_path: str) -> None:
            mkdirs.append(remote_path)

        def put(self, local_path: str, remote_path: str) -> None:
            uploads.append((local_path, remote_path))

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        FileClient,
        "_open_sftp",
        lambda self: (FakeSSHClient(), FakeSFTPClient()),
    )
    client = FileClient(host="127.0.0.1", username="root", password="easybot")

    source_dir = tmp_path / "bundle"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "job.urp").write_text("urp", encoding="utf-8")
    sub = source_dir / "sub"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / "job.script").write_text("script", encoding="utf-8")

    result = client.upload_tree(source_dir, "/programs/jobs")

    assert len(result) == 2
    assert result[0]["relative_path"] == "job.urp"
    assert result[0]["remote_path"] == "/programs/jobs/job.urp"
    assert result[1]["relative_path"] == "sub/job.script"
    assert result[1]["remote_path"] == "/programs/jobs/sub/job.script"
    assert "/programs/jobs/sub" in mkdirs
    assert uploads[0][1] == "/programs/jobs/job.urp"
    assert uploads[1][1] == "/programs/jobs/sub/job.script"
