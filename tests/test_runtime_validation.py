from __future__ import annotations

from ur_arms_manager.services.runtime_validation import (
    build_runtime_readiness_snapshot,
    classify_dashboard_load_response,
    derive_dashboard_load_argument,
    normalize_runtime_safe_filename,
    runtime_name_safety_warning,
)


def test_derive_dashboard_load_argument_for_programs_prefix() -> None:
    assert derive_dashboard_load_argument("/programs/demo.urp") == "programs/demo.urp"


def test_derive_dashboard_load_argument_for_ursim_profile_root() -> None:
    assert (
        derive_dashboard_load_argument("/ursim/programs.UR5/bundle/main.urp")
        == "bundle/main.urp"
    )


def test_derive_dashboard_load_argument_for_ursim_symlink_root() -> None:
    assert (
        derive_dashboard_load_argument("/ursim/programs/bundle/main.urp")
        == "bundle/main.urp"
    )


def test_derive_dashboard_load_argument_rejects_unknown_absolute_root() -> None:
    try:
        derive_dashboard_load_argument("/tmp/random/main.urp")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Unsupported runtime path strategy" in str(exc)


def test_derive_dashboard_load_argument_rejects_traversal_and_control_characters() -> None:
    for unsafe in ("/programs/jobs/../escape.urp", "/programs/demo.urp\nplay"):
        try:
            derive_dashboard_load_argument(unsafe)
            assert False, f"Expected unsafe path rejection: {unsafe!r}"
        except ValueError as exc:
            assert "not load-safe" in str(exc)


def test_derive_dashboard_load_argument_keeps_relative_paths() -> None:
    assert derive_dashboard_load_argument("bundle/main.urp") == "bundle/main.urp"


def test_classify_dashboard_load_response_parser_error() -> None:
    outcome, notes = classify_dashboard_load_response("could not understand: 'load programs/demo.urp'")
    assert outcome == "parser_error"
    assert notes


def test_classify_dashboard_load_response_file_not_found() -> None:
    outcome, notes = classify_dashboard_load_response("File not found: programs/missing.urp")
    assert outcome == "file_not_found"
    assert notes


def test_classify_dashboard_load_response_success() -> None:
    outcome, notes = classify_dashboard_load_response("Loading program: programs/demo.urp")
    assert outcome == "success"
    assert notes == []


def test_classify_dashboard_load_response_success_with_installation_path() -> None:
    outcome, notes = classify_dashboard_load_response(
        "Loading program: /ursim/programs/demo.urp, /ursim/programs/default.installation"
    )
    assert outcome == "success"
    assert notes == []


def test_classify_dashboard_load_response_path_strategy_unknown() -> None:
    outcome, notes = classify_dashboard_load_response(
        None,
        error=ValueError("Unsupported runtime path strategy for dashboard load."),
    )
    assert outcome == "path_strategy_unknown"
    assert notes


def test_runtime_name_safety_warning_detects_spaces() -> None:
    warning = runtime_name_safety_warning("bundle/name with spaces.urp")
    assert warning is not None
    assert "warning" in warning.lower()


def test_normalize_runtime_safe_filename_replaces_unsafe_chars() -> None:
    assert (
        normalize_runtime_safe_filename("tom_palet_depalet _ ruml_vaverka_venclovsky.urp")
        == "tom_palet_depalet_ruml_vaverka_venclovsky.urp"
    )
    assert normalize_runtime_safe_filename("my program.urp") == "my_program.urp"
    assert normalize_runtime_safe_filename("bad'name.urp") == "bad_name.urp"


def test_normalize_runtime_safe_filename_keeps_safe_name() -> None:
    assert normalize_runtime_safe_filename("demo_bundle_main.urp") == "demo_bundle_main.urp"


def test_build_runtime_readiness_snapshot_for_deployed_only_state() -> None:
    snapshot = build_runtime_readiness_snapshot(
        robot_name="robot1",
        assigned_runtime_path=None,
        deployed_primary_path="/programs/bundle/main.urp",
        latest_load_validation=None,
    )
    assert snapshot.deployed_only is True
    assert snapshot.assigned is False
    assert snapshot.ready_for_play is False
    assert any("deployed" in note.lower() for note in snapshot.notes)


def test_build_runtime_readiness_snapshot_for_failed_load() -> None:
    snapshot = build_runtime_readiness_snapshot(
        robot_name="robot1",
        assigned_runtime_path="/programs/bundle/main.urp",
        deployed_primary_path="/programs/bundle/main.urp",
        latest_load_validation={
            "outcome": "file_not_found",
            "ready_for_play": False,
            "raw_dashboard_response": "file not found",
        },
    )
    assert snapshot.load_attempted is True
    assert snapshot.load_failed is True
    assert snapshot.ready_for_play is False
