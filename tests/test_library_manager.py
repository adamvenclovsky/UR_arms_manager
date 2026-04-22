from __future__ import annotations

from pathlib import Path

from ur_arms_manager.services.library_manager import LibraryError, LibraryManager


def test_library_add_list_inspect_remove_cycle_is_filesystem_first(tmp_path: Path) -> None:
    programs_root = tmp_path / "storage" / "programs"
    source = tmp_path / "demo.script"
    source.write_text("def demo():\n  textmsg(\"ok\")\nend\n", encoding="utf-8")

    manager = LibraryManager(programs_root)
    added = manager.add_item(str(source))

    assert added["program_id"] == "uploaded/demo.script"
    assert Path(added["stored_path"]).is_file()

    items = manager.list_items()
    assert len(items) == 1
    assert items[0]["program_id"] == "uploaded/demo.script"
    assert items[0]["extension"] == "script"
    assert items[0]["item_kind"] == "file"

    inspected = manager.inspect_item("uploaded/demo.script")
    assert inspected["stored_filename"] == "demo.script"
    assert inspected["payload_status"] == "ok"
    assert inspected["origin"] == "local"

    removed = manager.remove_item("uploaded/demo.script")
    assert removed["program_id"] == "uploaded/demo.script"
    assert manager.list_items() == []


def test_library_add_missing_file_fails_cleanly(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "programs")

    try:
        manager.add_item(str(tmp_path / "missing.urp"))
        assert False, "Expected LibraryError"
    except LibraryError as exc:
        assert "Local source file not found" in str(exc)


def test_library_duplicate_add_creates_unique_file_name_in_uploaded(tmp_path: Path) -> None:
    programs_root = tmp_path / "storage" / "programs"
    source = tmp_path / "demo.urp"
    source.write_bytes(b"same-data")

    manager = LibraryManager(programs_root)
    first = manager.add_item(str(source))
    second = manager.add_item(str(source))

    assert first["program_id"] == "uploaded/demo.urp"
    assert second["program_id"] == "uploaded/demo_1.urp"


def test_library_create_folder_and_list_directory(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "programs")

    created = manager.create_folder("uploaded/jobs")
    entries = manager.list_directory("uploaded")

    assert created["program_id"] == "uploaded/jobs"
    assert created["item_kind"] == "directory"
    assert any(entry["program_id"] == "uploaded/jobs" for entry in entries)


def test_library_get_stored_file_fails_when_payload_is_missing(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "programs")

    empty_dir = manager.create_folder("uploaded/broken_item")
    assert empty_dir["item_kind"] == "directory"

    try:
        manager.get_stored_file("uploaded/broken_item")
        assert False, "Expected LibraryError"
    except LibraryError as exc:
        assert "Stored library payload not found" in str(exc)


def test_library_get_stored_file_uses_real_file_when_stored_path_would_be_stale(
    tmp_path: Path,
) -> None:
    manager = LibraryManager(tmp_path / "storage" / "programs")
    source = tmp_path / "demo.script"
    source.write_text("def demo():\nend\n", encoding="utf-8")

    added = manager.add_item(str(source))
    resolved = manager.get_stored_file(added["program_id"])
    inspected = manager.inspect_item(added["program_id"])

    assert resolved == tmp_path / "storage" / "programs" / "uploaded" / "demo.script"
    assert inspected["stored_path"] == str(resolved)
    assert inspected["payload_status"] == "ok"


def test_library_get_stored_file_falls_back_to_single_file_directory_scan(
    tmp_path: Path,
) -> None:
    programs_root = tmp_path / "storage" / "programs"
    legacy_dir = programs_root / "legacy-item"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    payload = legacy_dir / "demo.urp"
    payload.write_text("<Program/>", encoding="utf-8")

    manager = LibraryManager(programs_root)

    resolved = manager.get_stored_file("legacy-item")
    inspected = manager.inspect_item("legacy-item")

    assert resolved == payload
    assert inspected["program_id"] == "legacy-item"
    assert inspected["stored_filename"] == "demo.urp"


def test_library_get_stored_file_fails_cleanly_when_directory_contains_no_payload(
    tmp_path: Path,
) -> None:
    programs_root = tmp_path / "storage" / "programs"
    broken_dir = programs_root / "legacy-empty"
    broken_dir.mkdir(parents=True, exist_ok=True)
    (broken_dir / "manifest.yaml").write_text("program_id: legacy-empty\n", encoding="utf-8")

    manager = LibraryManager(programs_root)

    try:
        manager.get_stored_file("legacy-empty")
        assert False, "Expected LibraryError"
    except LibraryError as exc:
        assert "Stored library payload not found" in str(exc)


def test_library_get_stored_file_fails_cleanly_when_multiple_payload_files_exist(
    tmp_path: Path,
) -> None:
    programs_root = tmp_path / "storage" / "programs"
    broken_dir = programs_root / "legacy-ambiguous"
    broken_dir.mkdir(parents=True, exist_ok=True)
    (broken_dir / "a.script").write_text("def a():\nend\n", encoding="utf-8")
    (broken_dir / "b.script").write_text("def b():\nend\n", encoding="utf-8")

    manager = LibraryManager(programs_root)

    try:
        manager.get_stored_file("legacy-ambiguous")
        assert False, "Expected LibraryError"
    except LibraryError as exc:
        assert "Stored library payload is ambiguous" in str(exc)


def test_library_add_item_places_robot_import_in_robot_folder_with_prefixed_name(
    tmp_path: Path,
) -> None:
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
    assert inspected["program_id"] == "robot1/robot1_robot_file.urp"
    assert inspected["origin"] == "robot_remote"
    assert inspected["source_robot"] == "robot1"


def test_library_move_and_copy_item_use_real_paths(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "programs")
    source = tmp_path / "demo.script"
    source.write_text("def demo():\nend\n", encoding="utf-8")

    added = manager.add_item(str(source))
    copied = manager.copy_item(added["program_id"], "robot2/copied_demo.script")
    moved = manager.move_item(added["program_id"], "uploaded/archive/demo.script")

    assert copied["program_id"] == "robot2/copied_demo.script"
    assert moved["program_id"] == "uploaded/archive/demo.script"
    assert manager.inspect_item("robot2/copied_demo.script")["item_kind"] == "file"
    assert manager.inspect_item("uploaded/archive/demo.script")["item_kind"] == "file"
