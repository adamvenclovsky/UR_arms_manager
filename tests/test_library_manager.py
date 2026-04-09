from __future__ import annotations

from pathlib import Path

from ur_arms_manager.services.library_manager import LibraryError, LibraryManager


def test_library_add_list_inspect_remove_cycle(tmp_path: Path) -> None:
    programs_root = tmp_path / "storage" / "programs"
    source = tmp_path / "demo.script"
    source.write_text("def demo():\n  textmsg(\"ok\")\nend\n", encoding="utf-8")

    manager = LibraryManager(programs_root)
    added = manager.add_item(str(source))

    assert added["program_id"].startswith("demo-")
    assert Path(added["stored_path"]).exists()

    items = manager.list_items()
    assert len(items) == 1
    assert items[0]["program_id"] == added["program_id"]
    assert items[0]["original_filename"] == "demo.script"
    assert items[0]["extension"] == "script"

    inspected = manager.inspect_item(added["program_id"])
    assert inspected["created_at"]
    assert inspected["stored_filename"] == "demo.script"

    removed = manager.remove_item(added["program_id"])
    assert removed["program_id"] == added["program_id"]
    assert manager.list_items() == []


def test_library_add_missing_file_fails_cleanly(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "programs")
    try:
        manager.add_item(str(tmp_path / "missing.urp"))
        assert False, "Expected LibraryError"
    except LibraryError as exc:
        assert "Local source file not found" in str(exc)


def test_library_duplicate_add_creates_unique_program_id(tmp_path: Path) -> None:
    programs_root = tmp_path / "storage" / "programs"
    source = tmp_path / "demo.urp"
    source.write_bytes(b"same-data")

    manager = LibraryManager(programs_root)
    first = manager.add_item(str(source))
    second = manager.add_item(str(source))

    assert first["program_id"] != second["program_id"]
    assert second["program_id"].startswith(first["program_id"])


def test_library_get_stored_file_missing_on_disk_fails(tmp_path: Path) -> None:
    programs_root = tmp_path / "storage" / "programs"
    source = tmp_path / "demo.script"
    source.write_text("def demo():\nend\n", encoding="utf-8")
    manager = LibraryManager(programs_root)
    added = manager.add_item(str(source))

    Path(added["stored_path"]).unlink()

    try:
        manager.get_stored_file(added["program_id"])
        assert False, "Expected LibraryError"
    except LibraryError as exc:
        assert "Stored library file not found" in str(exc)


def test_library_add_item_supports_origin_metadata(tmp_path: Path) -> None:
    programs_root = tmp_path / "storage" / "programs"
    source = tmp_path / "robot_file.urp"
    source.write_bytes(b"robot-data")

    manager = LibraryManager(programs_root)
    item = manager.add_item(
        str(source),
        extra_metadata={
            "origin": "robot_remote",
            "source_robot": "robot1",
            "source_remote_path": "/programs/robot_file.urp",
        },
    )

    inspected = manager.inspect_item(item["program_id"])
    assert inspected["origin"] == "robot_remote"
    assert inspected["source_robot"] == "robot1"
    assert inspected["source_remote_path"] == "/programs/robot_file.urp"
