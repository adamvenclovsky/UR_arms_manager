from __future__ import annotations

import gzip
import re
import zipfile
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from xml.etree import ElementTree as ET

EDITABLE_URP_PARAMS = {
    "installation_name",
    "pallet_rows",
    "pallet_columns",
    "object_height_m",
}


def parse_urp_metadata(file_path: Path) -> dict[str, Any]:
    path = Path(file_path)
    try:
        xml_text = _extract_xml_text(path)
    except Exception as exc:
        return {
            "parse_success": False,
            "parse_error": f"Unable to read URP content: {exc}",
        }

    try:
        root = ET.fromstring(xml_text)
    except Exception as exc:
        sanitized = _escape_bare_ampersands(xml_text)
        if sanitized != xml_text:
            try:
                root = ET.fromstring(sanitized)
                xml_text = sanitized
            except Exception as retry_exc:
                return {
                    "parse_success": False,
                    "parse_error": f"Unable to parse XML from URP: {retry_exc}",
                }
        else:
            return {
                "parse_success": False,
                "parse_error": f"Unable to parse XML from URP: {exc}",
            }

    all_text = " ".join(root.itertext())
    xml_lower = xml_text.lower()

    metadata: dict[str, Any] = {
        "parse_success": True,
        "urcap_names": _extract_urcap_names(root, xml_text),
        "digital_inputs": _extract_indices(xml_lower, "input"),
        "digital_outputs": _extract_indices(xml_lower, "output"),
        "contains_palletizing": "pallet" in xml_lower,
    }

    program_name = (
        root.attrib.get("name")
        or _find_attr_by_name(root, ("programname", "program_name", "name"))
        or _regex_first(xml_text, r"program[_\s-]*name[^A-Za-z0-9]+([A-Za-z0-9_. -]+)")
    )
    if program_name:
        metadata["program_name"] = str(program_name).strip()

    installation_name = (
        _find_attr_by_name(root, ("installation", "installationname"))
        or _regex_first(xml_text, r"([A-Za-z0-9_.-]+\.installation)")
    )
    if installation_name:
        metadata["installation_name"] = str(installation_name).strip()

    polyscope_version = (
        _find_attr_by_name(root, ("polyscopeversion", "softwareversion", "version"))
        or _regex_first(xml_text, r"(\d+\.\d+\.\d+(?:\.\d+)?)")
    )
    if polyscope_version:
        metadata["polyscope_version"] = str(polyscope_version).strip()

    robot_serial_number = (
        _find_attr_by_name(root, ("robotserialnumber", "serialnumber", "serial"))
        or _regex_first(xml_text, r"(?:serial(?:number)?)[^A-Za-z0-9]*([A-Za-z0-9-]+)")
    )
    if robot_serial_number:
        metadata["robot_serial_number"] = str(robot_serial_number).strip()

    if metadata["contains_palletizing"]:
        pallet_rows = _find_attr_by_name(root, ("rows", "rowcount")) or _regex_first(
            all_text, r"(?:rows?|rowcount)\D+(\d+)"
        )
        pallet_columns = _find_attr_by_name(root, ("columns", "colcount")) or _regex_first(
            all_text, r"(?:columns?|colcount)\D+(\d+)"
        )
        object_height = _find_attr_by_name(
            root, ("objectheight", "itemheight", "height")
        ) or _regex_first(
            all_text,
            r"(?:object[_\s-]*height|item[_\s-]*height|height)\D+([0-9]*\.?[0-9]+)",
        )
        if pallet_rows:
            metadata["pallet_rows"] = int(pallet_rows)
        if pallet_columns:
            metadata["pallet_columns"] = int(pallet_columns)
        if object_height:
            try:
                metadata["object_height_m"] = float(object_height)
            except ValueError:
                pass

    return metadata


def list_editable_urp_params(file_path: Path) -> dict[str, str]:
    path = Path(file_path)
    root, _xml_text, _format_info = _load_urp_document(path)
    refs = _collect_editable_refs(root)
    editable: dict[str, str] = {}
    for param_name, ref in refs.items():
        editable[param_name] = str(ref["value"])
    return editable


def update_urp_param(file_path: Path, param_name: str, value: str) -> dict[str, str]:
    path = Path(file_path)
    if param_name not in EDITABLE_URP_PARAMS:
        raise ValueError(f"Unsupported URP parameter: {param_name}")

    root, _xml_text, format_info = _load_urp_document(path)
    refs = _collect_editable_refs(root)
    if param_name not in refs:
        raise ValueError(f"URP parameter not detected in file: {param_name}")

    ref = refs[param_name]
    normalized = _normalize_param_value(param_name, value)
    ref["element"].set(ref["attribute"], normalized)
    updated_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    _write_urp_document_atomic(path, format_info, updated_xml)
    return {param_name: normalized}


def _extract_xml_text(path: Path) -> str:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path, "r") as archive:
            xml_candidates = [
                name for name in archive.namelist() if name.lower().endswith((".xml", ".urp"))
            ]
            ordered = xml_candidates or archive.namelist()
            for name in ordered:
                raw = archive.read(name)
                text = _decode_bytes(raw)
                if "<" in text and ">" in text:
                    return text
        raise ValueError("Zip archive has no XML-like content")

    raw = path.read_bytes()
    if raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
    return _decode_bytes(raw)


def _load_urp_document(path: Path) -> tuple[ET.Element, str, dict[str, str]]:
    raw_xml, format_info = _extract_xml_bytes_and_format(path)
    xml_text = _decode_bytes(raw_xml)
    try:
        root = ET.fromstring(xml_text)
        return root, xml_text, format_info
    except Exception:
        sanitized = _escape_bare_ampersands(xml_text)
        if sanitized == xml_text:
            raise
        root = ET.fromstring(sanitized)
        return root, sanitized, format_info


def _extract_xml_bytes_and_format(path: Path) -> tuple[bytes, dict[str, str]]:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path, "r") as archive:
            entry_name = _select_xml_entry_name(archive)
            return archive.read(entry_name), {"kind": "zip", "entry_name": entry_name}

    raw = path.read_bytes()
    if raw.startswith(b"\x1f\x8b"):
        return gzip.decompress(raw), {"kind": "gzip"}
    return raw, {"kind": "plain"}


def _select_xml_entry_name(archive: zipfile.ZipFile) -> str:
    xml_candidates = [
        name for name in archive.namelist() if name.lower().endswith((".xml", ".urp"))
    ]
    ordered = xml_candidates or archive.namelist()
    for name in ordered:
        raw = archive.read(name)
        text = _decode_bytes(raw)
        if "<" in text and ">" in text:
            return name
    raise ValueError("Zip archive has no XML-like content")


def _write_urp_document_atomic(path: Path, format_info: dict[str, str], xml_bytes: bytes) -> None:
    kind = format_info["kind"]
    if kind == "zip":
        _write_zip_urp_atomic(path, format_info["entry_name"], xml_bytes)
        return
    if kind == "gzip":
        payload = gzip.compress(xml_bytes)
    else:
        payload = xml_bytes
    _write_bytes_atomic(path, payload)


def _write_zip_urp_atomic(path: Path, entry_name: str, xml_bytes: bytes) -> None:
    with NamedTemporaryFile(
        delete=False,
        dir=path.parent,
        prefix=f"{path.name}.",
        suffix=".tmp",
    ) as tmp:
        tmp_path = Path(tmp.name)
    try:
        # Windows does not allow os.replace while the source archive still has
        # an open handle, so finish reading it before replacing the original.
        with zipfile.ZipFile(path, "r") as source:
            names = source.namelist()
            with zipfile.ZipFile(tmp_path, "w") as target:
                for name in names:
                    if name == entry_name:
                        target.writestr(name, xml_bytes)
                    else:
                        target.writestr(name, source.read(name))
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    with NamedTemporaryFile(delete=False, dir=path.parent, prefix=f"{path.name}.", suffix=".tmp") as tmp:
        tmp.write(payload)
        tmp.flush()
        tmp_path = Path(tmp.name)
    try:
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _collect_editable_refs(root: ET.Element) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}
    refs["installation_name"] = _single_attr_ref(
        root,
        {"installationname", "installation"},
    )
    refs["pallet_rows"] = _single_attr_ref(root, {"rows", "rowcount"})
    refs["pallet_columns"] = _single_attr_ref(root, {"columns", "colcount"})
    refs["object_height_m"] = _single_attr_ref(root, {"objectheight", "itemheight", "height"})
    return {key: value for key, value in refs.items() if value is not None}


def _single_attr_ref(root: ET.Element, attr_names: set[str]) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    wanted = {name.lower() for name in attr_names}
    for elem in root.iter():
        for key, value in elem.attrib.items():
            if key.lower() in wanted and value:
                matches.append({"element": elem, "attribute": key, "value": value})
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError("Ambiguous editable URP parameter mapping")
    return None


def _normalize_param_value(param_name: str, raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        raise ValueError(f"Empty value is not allowed for {param_name}")
    if param_name in {"pallet_rows", "pallet_columns"}:
        parsed = int(value)
        if parsed <= 0:
            raise ValueError(f"{param_name} must be a positive integer")
        return str(parsed)
    if param_name == "object_height_m":
        parsed = float(value)
        if parsed <= 0:
            raise ValueError("object_height_m must be a positive number")
        return str(parsed)
    return value


def _decode_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _find_attr_by_name(root: ET.Element, attr_names: tuple[str, ...]) -> str | None:
    wanted = {name.lower() for name in attr_names}
    for elem in root.iter():
        for key, value in elem.attrib.items():
            if key.lower() in wanted and value:
                return value
    return None


def _regex_first(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip()


def _extract_indices(xml_lower: str, io_kind: str) -> list[int]:
    pattern = rf"digital[_\s-]*(?:{io_kind}|{io_kind[:2]})[_\s-]*(\d+)"
    indices = {int(m) for m in re.findall(pattern, xml_lower, flags=re.IGNORECASE)}
    return sorted(indices)


def _extract_urcap_names(root: ET.Element, xml_text: str) -> list[str]:
    names: set[str] = set()
    for elem in root.iter():
        tag = elem.tag.lower()
        if "urcap" in tag:
            for key, value in elem.attrib.items():
                if "name" in key.lower() and value:
                    names.add(value.strip())
    for match in re.findall(r"urcap[^A-Za-z0-9]+([A-Za-z0-9_. -]+)", xml_text, flags=re.I):
        candidate = match.strip()
        if candidate:
            names.add(candidate)
    return sorted(names)


def _escape_bare_ampersands(xml_text: str) -> str:
    # Best-effort salvage for malformed XML content like "a && b" in synthetic URP files.
    return re.sub(
        r"&(?!#\d+;|#x[0-9A-Fa-f]+;|[A-Za-z_][A-Za-z0-9_.-]*;)",
        "&amp;",
        xml_text,
    )
