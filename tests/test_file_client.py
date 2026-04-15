from __future__ import annotations

from pathlib import Path

from ur_arms_manager.adapters.ur.file_client import FileClient


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
