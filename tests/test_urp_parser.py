from __future__ import annotations

import zipfile
from pathlib import Path

from ur_arms_manager.library.urp_parser import (
    list_editable_urp_params,
    parse_urp_metadata,
    update_urp_param,
)


def test_parse_urp_metadata_from_zip_xml(tmp_path: Path) -> None:
    urp_path = tmp_path / "demo.urp"
    xml = """<?xml version="1.0"?>
<Program name="CellDemo" polyscopeVersion="5.14.6" robotSerialNumber="UR123456">
  <Header installationName="default.installation" />
  <URCap name="Palletizing" />
  <Expression>digital_input_3 && digital_output_5</Expression>
  <Pallet rows="4" columns="5" objectHeight="0.12" />
</Program>
"""
    with zipfile.ZipFile(urp_path, "w") as archive:
        archive.writestr("program.xml", xml)

    data = parse_urp_metadata(urp_path)

    assert data["parse_success"] is True
    assert data["program_name"] == "CellDemo"
    assert data["installation_name"] == "default.installation"
    assert data["polyscope_version"] == "5.14.6"
    assert data["robot_serial_number"] == "UR123456"
    assert data["contains_palletizing"] is True
    assert 3 in data["digital_inputs"]
    assert 5 in data["digital_outputs"]


def test_parse_urp_metadata_malformed_returns_parse_failure(tmp_path: Path) -> None:
    urp_path = tmp_path / "broken.urp"
    urp_path.write_text("<Program><Broken></Program", encoding="utf-8")

    data = parse_urp_metadata(urp_path)

    assert data["parse_success"] is False
    assert "parse_error" in data


def test_list_editable_urp_params_from_zip_xml(tmp_path: Path) -> None:
    urp_path = tmp_path / "editable.urp"
    xml = """<?xml version="1.0"?>
<Program name="CellDemo">
  <Header installationName="default.installation" />
  <Pallet rows="4" columns="5" objectHeight="0.12" />
</Program>
"""
    with zipfile.ZipFile(urp_path, "w") as archive:
        archive.writestr("program.xml", xml)

    params = list_editable_urp_params(urp_path)

    assert params["installation_name"] == "default.installation"
    assert params["pallet_rows"] == "4"
    assert params["pallet_columns"] == "5"
    assert params["object_height_m"] == "0.12"


def test_update_urp_param_updates_and_is_reflected_by_parse(tmp_path: Path) -> None:
    urp_path = tmp_path / "editable.urp"
    xml = """<?xml version="1.0"?>
<Program name="CellDemo">
  <Header installationName="default.installation" />
  <Pallet rows="4" columns="5" objectHeight="0.12" />
</Program>
"""
    with zipfile.ZipFile(urp_path, "w") as archive:
        archive.writestr("program.xml", xml)

    result = update_urp_param(urp_path, "pallet_rows", "9")
    data = parse_urp_metadata(urp_path)

    assert result == {"pallet_rows": "9"}
    assert data["parse_success"] is True
    assert data["pallet_rows"] == 9


def test_update_urp_param_failure_keeps_file_unchanged(tmp_path: Path) -> None:
    urp_path = tmp_path / "broken.urp"
    urp_path.write_bytes(b"<Program><Broken></Program")
    before = urp_path.read_bytes()

    try:
        update_urp_param(urp_path, "installation_name", "other.installation")
        assert False, "Expected failure for malformed URP"
    except Exception:
        pass

    after = urp_path.read_bytes()
    assert before == after
