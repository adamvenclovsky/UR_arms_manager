from __future__ import annotations

from pathlib import Path
import zipfile

import yaml

from ur_arms_manager import cli


def test_library_list_empty(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    exit_code = cli._main(["library", "list"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Library is empty." in output


def test_library_add_inspect_remove_via_cli(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    monkeypatch.setattr(cli, "ROOT_DIR", tmp_path)

    source = tmp_path / "programs" / "robot1" / "demo.script"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def demo():\n  textmsg(\"ok\")\nend\n", encoding="utf-8")

    add_code = cli._main(["library", "add", "programs/robot1/demo.script"])
    add_output = capsys.readouterr().out
    assert add_code == 0
    assert "Added to library:" in add_output
    program_id = add_output.split("Added to library: ", maxsplit=1)[1].splitlines()[0].strip()

    inspect_code = cli._main(["library", "inspect", program_id])
    inspect_output = capsys.readouterr().out
    assert inspect_code == 0
    assert f"program_id: {program_id}" in inspect_output
    assert "original_filename: demo.script" in inspect_output

    list_code = cli._main(["library", "list"])
    list_output = capsys.readouterr().out
    assert list_code == 0
    assert f"program_id: {program_id}" in list_output

    remove_code = cli._main(["library", "remove", program_id])
    remove_output = capsys.readouterr().out
    assert remove_code == 0
    assert f"Removed from library: {program_id}" in remove_output


def test_library_inspect_missing_returns_clean_error(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    monkeypatch.setattr(cli.sys, "argv", ["uam", "library", "inspect", "missing-id"])

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 3
    assert "[library error] Library item not found: missing-id" in output


def test_library_inspect_non_urp_behavior_unchanged(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    monkeypatch.setattr(cli, "ROOT_DIR", tmp_path)

    source = tmp_path / "demo.script"
    source.write_text("def demo():\nend\n", encoding="utf-8")
    add_code = cli._main(["library", "add", str(source)])
    add_output = capsys.readouterr().out
    assert add_code == 0
    program_id = add_output.split("Added to library: ", maxsplit=1)[1].splitlines()[0].strip()

    inspect_code = cli._main(["library", "inspect", program_id])
    inspect_output = capsys.readouterr().out

    assert inspect_code == 0
    assert "extension: script" in inspect_output
    assert "urp_analysis:" not in inspect_output


def test_library_inspect_urp_shows_analysis(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    monkeypatch.setattr(cli, "ROOT_DIR", tmp_path)

    urp_path = tmp_path / "demo.urp"
    with zipfile.ZipFile(urp_path, "w") as archive:
        archive.writestr(
            "program.xml",
            """<Program name="DemoProg" polyscopeVersion="5.14.0">
<Header installationName="default.installation"/>
<Expression>digital_input_1 || digital_output_2</Expression>
</Program>""",
        )

    add_code = cli._main(["library", "add", str(urp_path)])
    add_output = capsys.readouterr().out
    assert add_code == 0
    program_id = add_output.split("Added to library: ", maxsplit=1)[1].splitlines()[0].strip()

    inspect_code = cli._main(["library", "inspect", program_id])
    inspect_output = capsys.readouterr().out

    assert inspect_code == 0
    assert "extension: urp" in inspect_output
    assert "urp_analysis:" in inspect_output
    assert "parse_success: True" in inspect_output
    assert "program_name: DemoProg" in inspect_output


def test_library_inspect_malformed_urp_is_failure_tolerant(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    monkeypatch.setattr(cli, "ROOT_DIR", tmp_path)

    broken = tmp_path / "broken.urp"
    broken.write_text("<Program><Broken></Program", encoding="utf-8")

    add_code = cli._main(["library", "add", str(broken)])
    add_output = capsys.readouterr().out
    assert add_code == 0
    program_id = add_output.split("Added to library: ", maxsplit=1)[1].splitlines()[0].strip()

    inspect_code = cli._main(["library", "inspect", program_id])
    inspect_output = capsys.readouterr().out

    assert inspect_code == 0
    assert "urp_analysis:" in inspect_output
    assert "parse_success: False" in inspect_output


def test_library_import_remote_success(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: null
""",
        encoding="utf-8",
    )

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def pull_remote_file(self, remote_path: str, local_destination: str) -> Path:
            target = Path(local_destination) / Path(remote_path).name
            target.write_bytes(b"payload")
            return target

    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)

    exit_code = cli._main(["library", "import-remote", "robot1", "/programs/demo.urp"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Imported from robot 'robot1': /programs/demo.urp" in output
    assert "program_id=" in output

    programs_root = tmp_path / "storage" / "programs"
    manifests = list(programs_root.glob("*/manifest.yaml"))
    assert len(manifests) == 1
    data = yaml.safe_load(manifests[0].read_text(encoding="utf-8"))
    assert data["origin"] == "robot_remote"
    assert data["source_robot"] == "robot1"
    assert data["source_remote_path"] == "/programs/demo.urp"


def test_library_import_remote_failure_returns_clean_error(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(
        """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: null
""",
        encoding="utf-8",
    )

    class FakeRobotManager:
        def __init__(self, _robot):
            pass

        def pull_remote_file(self, _remote_path: str, _local_destination: str) -> Path:
            raise RuntimeError("remote file not found")

    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    monkeypatch.setattr(cli, "RobotManager", FakeRobotManager)
    monkeypatch.setattr(
        cli.sys, "argv", ["uam", "library", "import-remote", "robot1", "/programs/missing.urp"]
    )

    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "[error] remote file not found" in output


def test_library_urp_params_lists_detected_editable_fields(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    monkeypatch.setattr(cli, "ROOT_DIR", tmp_path)

    urp_path = tmp_path / "editable.urp"
    with zipfile.ZipFile(urp_path, "w") as archive:
        archive.writestr(
            "program.xml",
            """<Program name="DemoProg">
<Header installationName="default.installation"/>
<Pallet rows="4" columns="5" objectHeight="0.12"/>
</Program>""",
        )

    add_code = cli._main(["library", "add", str(urp_path)])
    add_output = capsys.readouterr().out
    assert add_code == 0
    program_id = add_output.split("Added to library: ", maxsplit=1)[1].splitlines()[0].strip()

    params_code = cli._main(["library", "urp-params", program_id])
    params_output = capsys.readouterr().out

    assert params_code == 0
    assert "editable_urp_params:" in params_output
    assert "installation_name: default.installation" in params_output
    assert "pallet_rows: 4" in params_output
    assert "pallet_columns: 5" in params_output
    assert "object_height_m: 0.12" in params_output


def test_library_urp_set_updates_and_inspect_reflects_value(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    monkeypatch.setattr(cli, "ROOT_DIR", tmp_path)

    urp_path = tmp_path / "editable.urp"
    with zipfile.ZipFile(urp_path, "w") as archive:
        archive.writestr(
            "program.xml",
            """<Program name="DemoProg">
<Header installationName="default.installation"/>
<Pallet rows="4" columns="5" objectHeight="0.12"/>
</Program>""",
        )

    add_code = cli._main(["library", "add", str(urp_path)])
    add_output = capsys.readouterr().out
    assert add_code == 0
    program_id = add_output.split("Added to library: ", maxsplit=1)[1].splitlines()[0].strip()

    set_code = cli._main(["library", "urp-set", program_id, "pallet_rows", "9"])
    set_output = capsys.readouterr().out
    assert set_code == 0
    assert "Updated URP param: pallet_rows=9" in set_output

    inspect_code = cli._main(["library", "inspect", program_id])
    inspect_output = capsys.readouterr().out
    assert inspect_code == 0
    assert "urp_analysis:" in inspect_output
    assert "pallet_rows: 9" in inspect_output


def test_library_urp_params_rejects_non_urp_item(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    monkeypatch.setattr(cli, "ROOT_DIR", tmp_path)

    source = tmp_path / "demo.script"
    source.write_text("def demo():\nend\n", encoding="utf-8")
    add_code = cli._main(["library", "add", str(source)])
    add_output = capsys.readouterr().out
    assert add_code == 0
    program_id = add_output.split("Added to library: ", maxsplit=1)[1].splitlines()[0].strip()

    monkeypatch.setattr(cli.sys, "argv", ["uam", "library", "urp-params", program_id])
    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 3
    assert f"[library error] Library item is not a .urp program: {program_id}" in output


def test_library_urp_set_rejects_unsupported_or_undetected_param(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    monkeypatch.setattr(cli, "ROOT_DIR", tmp_path)

    urp_path = tmp_path / "editable.urp"
    with zipfile.ZipFile(urp_path, "w") as archive:
        archive.writestr(
            "program.xml",
            """<Program name="DemoProg">
<Header installationName="default.installation"/>
</Program>""",
        )

    add_code = cli._main(["library", "add", str(urp_path)])
    add_output = capsys.readouterr().out
    assert add_code == 0
    program_id = add_output.split("Added to library: ", maxsplit=1)[1].splitlines()[0].strip()

    monkeypatch.setattr(
        cli.sys, "argv", ["uam", "library", "urp-set", program_id, "pallet_rows", "9"]
    )
    exit_code = cli.main()
    output = capsys.readouterr().out

    assert exit_code == 3
    assert (
        f"[library error] Failed to update URP param 'pallet_rows' for '{program_id}': "
        "URP parameter not detected in file: pallet_rows"
    ) in output


def test_library_urp_set_malformed_is_failure_safe(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "LIBRARY_PROGRAMS_DIR", tmp_path / "storage" / "programs")
    monkeypatch.setattr(cli, "ROOT_DIR", tmp_path)

    broken = tmp_path / "broken.urp"
    broken.write_bytes(b"<Program><Broken></Program")

    add_code = cli._main(["library", "add", str(broken)])
    add_output = capsys.readouterr().out
    assert add_code == 0
    program_id = add_output.split("Added to library: ", maxsplit=1)[1].splitlines()[0].strip()

    stored_file = next((tmp_path / "storage" / "programs").glob(f"{program_id}/*.urp"))
    before = stored_file.read_bytes()

    monkeypatch.setattr(
        cli.sys, "argv", ["uam", "library", "urp-set", program_id, "installation_name", "x.installation"]
    )
    exit_code = cli.main()
    output = capsys.readouterr().out
    after = stored_file.read_bytes()

    assert exit_code == 3
    assert "[library error] Failed to update URP param 'installation_name'" in output
    assert before == after
