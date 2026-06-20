from __future__ import annotations

from pathlib import Path

from ur_arms_manager.services.library_manager import LibraryError, LibraryManager


def test_library_add_list_inspect_remove_cycle_is_filesystem_first(tmp_path: Path) -> None:
    programs_root = tmp_path / "storage" / "library"
    source = tmp_path / "demo.script"
    source.write_text("def demo():\n  textmsg(\"ok\")\nend\n", encoding="utf-8")

    manager = LibraryManager(programs_root)
    added = manager.add_item(str(source))

    assert added["program_id"] == "demo.script"
    assert Path(added["stored_path"]).is_file()

    items = manager.list_items()
    assert len(items) == 1
    assert items[0]["program_id"] == "demo.script"
    assert items[0]["extension"] == "script"
    assert items[0]["item_kind"] == "file"

    inspected = manager.inspect_item("demo.script")
    assert inspected["stored_filename"] == "demo.script"
    assert inspected["payload_status"] == "ok"
    assert inspected["origin"] == "local"

    removed = manager.remove_item("demo.script")
    assert removed["program_id"] == "demo.script"
    assert manager.list_items() == []


def test_library_add_missing_file_fails_cleanly(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "library")

    try:
        manager.add_item(str(tmp_path / "missing.urp"))
        assert False, "Expected LibraryError"
    except LibraryError as exc:
        assert "Local source file not found" in str(exc)


def test_library_duplicate_add_creates_unique_file_name_in_uploaded(tmp_path: Path) -> None:
    programs_root = tmp_path / "storage" / "library"
    source = tmp_path / "demo.urp"
    source.write_bytes(b"same-data")

    manager = LibraryManager(programs_root)
    first = manager.add_item(str(source))
    second = manager.add_item(str(source))

    assert first["program_id"] == "demo.urp"
    assert second["program_id"] == "demo_1.urp"


def test_library_create_folder_and_list_directory(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "library")

    created = manager.create_folder("uploaded/jobs")
    entries = manager.list_directory("uploaded")

    assert created["program_id"] == "uploaded/jobs"
    assert created["item_kind"] == "directory"
    assert any(entry["program_id"] == "uploaded/jobs" for entry in entries)


def test_library_get_stored_file_fails_when_payload_is_missing(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "library")

    empty_dir = manager.create_folder("uploaded/broken_item")
    assert empty_dir["item_kind"] == "directory"

    try:
        manager.get_stored_file("uploaded/broken_item")
        assert False, "Expected LibraryError"
    except LibraryError as exc:
        assert "Stored library file not found" in str(exc)


def test_library_get_stored_file_uses_real_file_when_stored_path_would_be_stale(
    tmp_path: Path,
) -> None:
    manager = LibraryManager(tmp_path / "storage" / "library")
    source = tmp_path / "demo.script"
    source.write_text("def demo():\nend\n", encoding="utf-8")

    added = manager.add_item(str(source))
    resolved = manager.get_stored_file(added["program_id"])
    inspected = manager.inspect_item(added["program_id"])

    assert resolved == tmp_path / "storage" / "library" / "demo.script"
    assert inspected["stored_path"] == str(resolved)
    assert inspected["payload_status"] == "ok"


def test_library_get_stored_file_rejects_directory_reference(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "library")
    manager.create_folder("uploaded/folder_only")

    try:
        manager.get_stored_file("uploaded/folder_only")
        assert False, "Expected LibraryError"
    except LibraryError as exc:
        assert "Library path is a directory, not a file" in str(exc)


def test_library_add_item_places_robot_import_in_robot_folder_with_prefixed_name(
    tmp_path: Path,
) -> None:
    programs_root = tmp_path / "storage" / "library"
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
    assert inspected["program_id"] == "robot1_robot_file.urp"
    assert inspected["origin"] == "robot_remote"
    assert inspected["source_robot"] == "robot1"


def test_library_move_and_copy_item_use_real_paths(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "library")
    source = tmp_path / "demo.script"
    source.write_text("def demo():\nend\n", encoding="utf-8")

    added = manager.add_item(str(source))
    copied = manager.copy_item(added["program_id"], "robot2/copied_demo.script")
    moved = manager.move_item(added["program_id"], "uploaded/archive/demo.script")

    assert copied["program_id"] == "robot2/copied_demo.script"
    assert moved["program_id"] == "uploaded/archive/demo.script"
    assert manager.inspect_item("robot2/copied_demo.script")["item_kind"] == "file"
    assert manager.inspect_item("uploaded/archive/demo.script")["item_kind"] == "file"


def test_library_move_refuses_to_replace_existing_destination(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "library")
    first = tmp_path / "first.script"
    second = tmp_path / "second.script"
    first.write_text("def first():\nend\n", encoding="utf-8")
    second.write_text("def second():\nend\n", encoding="utf-8")
    manager.add_item(str(first))
    manager.add_item(str(second))

    try:
        manager.move_item("first.script", "second.script")
        assert False, "Expected LibraryError"
    except LibraryError as exc:
        assert "destination already exists" in str(exc)

    assert manager.get_stored_file("first.script").read_text(encoding="utf-8").startswith(
        "def first"
    )
    assert manager.get_stored_file("second.script").read_text(encoding="utf-8").startswith(
        "def second"
    )


def test_library_inspect_directory_by_relative_path(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "library")

    created = manager.create_folder("robot2/jobs")
    inspected = manager.inspect_item("robot2/jobs")

    assert created["library_path"] == "robot2/jobs"
    assert inspected["item_kind"] == "directory"
    assert inspected["library_path"] == "robot2/jobs"


def test_library_rejects_path_escape_attempts(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "library")

    try:
        manager.inspect_item("../outside.txt")
        assert False, "Expected LibraryError"
    except LibraryError as exc:
        assert "Library path escapes root" in str(exc)


def test_library_bundle_inspection_detects_primary_urp_and_related_files(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "library")
    bundle_dir = tmp_path / "incoming"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "cell.urp").write_text("<urp/>", encoding="utf-8")
    (bundle_dir / "cell.installation").write_text("installation", encoding="utf-8")
    (bundle_dir / "cell.variables").write_text("variables", encoding="utf-8")
    (bundle_dir / "notes.txt").write_text("note", encoding="utf-8")

    bundle = manager.add_bundle(
        [
            str(bundle_dir / "cell.urp"),
            str(bundle_dir / "cell.installation"),
            str(bundle_dir / "cell.variables"),
            str(bundle_dir / "notes.txt"),
        ],
        target_dir="uploaded",
    )

    assert bundle["bundle_directory_path"] == "uploaded/cell"
    assert bundle["primary_urp_filename"] == "cell.urp"
    assert bundle["installation_present"] is True
    assert bundle["variables_present"] is True
    assert bundle["text_present"] is True
    assert bundle["readiness_state"] == "ready"
    assert bundle["warnings"] == []


def test_library_bundle_inspection_warns_on_missing_installation_and_variables(
    tmp_path: Path,
) -> None:
    manager = LibraryManager(tmp_path / "storage" / "library")
    source_urp = tmp_path / "demo.urp"
    source_urp.write_text("<urp/>", encoding="utf-8")

    bundle = manager.add_bundle([str(source_urp)], target_dir="uploaded")

    assert bundle["primary_urp_filename"] == "demo.urp"
    assert bundle["installation_present"] is False
    assert bundle["variables_present"] is False
    assert bundle["readiness_state"] == "warning"
    assert "No .installation file is present in this bundle." in bundle["warnings"]
    assert "No .variables file is present in this bundle." in bundle["warnings"]


def test_library_bundle_inspection_marks_multiple_urps_as_invalid(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "library")
    source_a = tmp_path / "a.urp"
    source_b = tmp_path / "b.urp"
    source_a.write_text("<urp/>", encoding="utf-8")
    source_b.write_text("<urp/>", encoding="utf-8")

    bundle = manager.add_bundle([str(source_a), str(source_b)], target_dir="uploaded")

    assert bundle["primary_urp_path"] is None
    assert bundle["readiness_state"] == "invalid"
    assert any("Multiple .urp files" in warning for warning in bundle["warnings"])


def test_library_preview_bundle_import_returns_bundle_summary_without_writing_files(
    tmp_path: Path,
) -> None:
    manager = LibraryManager(tmp_path / "storage" / "library")

    preview = manager.preview_bundle_import(
        ["demo.urp", "demo.installation", "demo.variables", "notes.txt"],
        target_dir="uploaded/jobs",
    )

    assert preview["bundle_directory_path"] == "uploaded/jobs/demo"
    assert preview["primary_urp_path"] == "uploaded/jobs/demo/demo.urp"
    assert preview["installation_present"] is True
    assert preview["variables_present"] is True
    assert preview["readiness_state"] == "ready"
    assert preview["primary_urp_normalization_needed"] is False
    # Preview should not create the bundle path yet.
    assert not (tmp_path / "storage" / "library" / "uploaded" / "jobs" / "demo").exists()


def test_library_preview_bundle_import_shows_runtime_safe_rename_plan(
    tmp_path: Path,
) -> None:
    manager = LibraryManager(tmp_path / "storage" / "library")

    preview = manager.preview_bundle_import(
        ["my program.urp", "my program.installation", "my program.variables"],
        target_dir="uploaded/jobs",
    )

    assert preview["primary_urp_original_filename"] == "my program.urp"
    assert preview["primary_urp_runtime_safe_filename"] == "my_program.urp"
    assert preview["primary_urp_normalization_needed"] is True
    assert any("runtime-safe" in warning for warning in preview["warnings"])


def test_library_preview_bundle_import_marks_multiple_urp_as_ambiguous(
    tmp_path: Path,
) -> None:
    manager = LibraryManager(tmp_path / "storage" / "library")

    preview = manager.preview_bundle_import(
        ["a.urp", "b.urp", "bundle.installation", "bundle.variables"],
        target_dir="uploaded",
    )

    assert preview["primary_urp_path"] is None
    assert preview["readiness_state"] == "invalid"
    assert any("Multiple .urp files" in warning for warning in preview["warnings"])


def test_library_new_root_starts_empty_without_default_folders(tmp_path: Path) -> None:
    root = tmp_path / "storage" / "library"
    manager = LibraryManager(root)

    assert manager.list_directory("") == []
    assert not (root / "uploaded").exists()
    assert not (root / "robot1").exists()
    assert not (root / "robot2").exists()
    assert not (root / "robot3").exists()


def test_library_add_bundle_normalizes_primary_urp_filename_by_default(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "library")
    incoming = tmp_path / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    (incoming / "my program.urp").write_text("<urp/>", encoding="utf-8")
    (incoming / "my program.installation").write_text("installation", encoding="utf-8")
    (incoming / "my program.variables").write_text("variables", encoding="utf-8")

    bundle = manager.add_bundle(
        [
            str(incoming / "my program.urp"),
            str(incoming / "my program.installation"),
            str(incoming / "my program.variables"),
        ],
        target_dir="uploaded/jobs",
    )

    assert bundle["primary_urp_was_normalized"] is True
    assert bundle["primary_urp_original_filename"] == "my program.urp"
    assert bundle["primary_urp_runtime_safe_filename"] == "my_program.urp"
    assert bundle["primary_urp_filename"] == "my_program.urp"
    assert bundle["primary_urp_path"] == "uploaded/jobs/my_program/my_program.urp"
    assert (tmp_path / "storage" / "library" / "uploaded" / "jobs" / "my_program" / "my_program.urp").exists()


def test_prepare_runtime_safe_bundle_copy_creates_non_destructive_safe_copy(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "library")
    # Simulate legacy pre-normalization bundle directly on filesystem.
    legacy_bundle = tmp_path / "storage" / "library" / "uploaded" / "legacy_bundle"
    legacy_bundle.mkdir(parents=True, exist_ok=True)
    (legacy_bundle / "main file.urp").write_text("<urp/>", encoding="utf-8")
    (legacy_bundle / "main.installation").write_text("installation", encoding="utf-8")
    (legacy_bundle / "main.variables").write_text("variables", encoding="utf-8")

    prepared = manager.prepare_runtime_safe_bundle_copy("uploaded/legacy_bundle")

    assert prepared["bundle_directory_path"] == "uploaded/legacy_bundle_safe"
    assert prepared["primary_urp_original_filename"] == "main file.urp"
    assert prepared["primary_urp_runtime_safe_filename"] == "main_file.urp"
    assert prepared["primary_urp_path"] == "uploaded/legacy_bundle_safe/main_file.urp"
    assert (tmp_path / "storage" / "library" / "uploaded" / "legacy_bundle" / "main file.urp").exists()
    assert (tmp_path / "storage" / "library" / "uploaded" / "legacy_bundle_safe" / "main_file.urp").exists()


def test_prepare_runtime_safe_bundle_copy_keeps_safe_primary_name_unchanged(tmp_path: Path) -> None:
    manager = LibraryManager(tmp_path / "storage" / "library")
    incoming = tmp_path / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    (incoming / "main.urp").write_text("<urp/>", encoding="utf-8")
    (incoming / "main.installation").write_text("installation", encoding="utf-8")
    (incoming / "main.variables").write_text("variables", encoding="utf-8")
    manager.add_bundle(
        [
            str(incoming / "main.urp"),
            str(incoming / "main.installation"),
            str(incoming / "main.variables"),
        ],
        target_dir="uploaded",
        bundle_name="safe_bundle",
    )

    prepared = manager.prepare_runtime_safe_bundle_copy("uploaded/safe_bundle")

    assert prepared["primary_urp_original_filename"] == "main.urp"
    assert prepared["primary_urp_runtime_safe_filename"] == "main.urp"
    assert prepared["primary_urp_path"] == "uploaded/safe_bundle_safe/main.urp"
