from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
import re
from typing import Literal


LoadOutcome = Literal[
    "success",
    "unsafe_runtime_path",
    "parser_error",
    "file_not_found",
    "load_error",
    "path_strategy_unknown",
    "timeout",
    "installation_or_safety_block",
    "wrong_mode_or_remote_control_issue",
    "unknown_failure",
]


@dataclass(slots=True)
class LoadValidationResult:
    robot_name: str
    assigned_runtime_path: str | None
    derived_dashboard_load_argument: str | None
    raw_dashboard_response: str | None
    outcome: LoadOutcome
    notes: list[str]
    ready_for_play: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class RuntimeReadinessSnapshot:
    robot_name: str
    deployed_primary_path: str | None
    assigned_runtime_path: str | None
    deployed_only: bool
    assigned: bool
    load_attempted: bool
    load_succeeded: bool
    load_failed: bool
    ready_for_play: bool
    not_ready_for_play: bool
    notes: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def derive_dashboard_load_argument(assigned_runtime_path: str) -> str:
    raw_value = str(assigned_runtime_path or "").strip()
    if not raw_value:
        raise ValueError("Assigned runtime path is empty.")

    candidate = str(PurePosixPath(raw_value))
    if not candidate.startswith("/"):
        relative = candidate.strip()
        if not relative or relative in {".", "/"}:
            raise ValueError("Assigned runtime path does not point to a loadable program file.")
        if ".." in PurePosixPath(relative).parts:
            raise ValueError("Assigned runtime path contains traversal segments and is not load-safe.")
        return relative

    if candidate.startswith("/programs/"):
        return candidate.lstrip("/")

    ursim_roots = ("/ursim/programs.UR5", "/ursim/programs")
    for root in ursim_roots:
        if candidate == root:
            raise ValueError(
                f"Assigned runtime path points to URSim root '{root}', not to a .urp program file."
            )
        prefix = f"{root}/"
        if candidate.startswith(prefix):
            relative = candidate[len(prefix) :].strip("/")
            if not relative:
                raise ValueError("Assigned runtime path does not point to a loadable program file.")
            return relative

    raise ValueError(
        "Unsupported runtime path strategy for dashboard load. "
        f"Current profile expects '/ursim/programs.UR5/...', '/ursim/programs/...', or '/programs/...'; got '{candidate}'."
    )


def runtime_name_safety_warning(path_or_argument: str | None) -> str | None:
    candidate = str(path_or_argument or "").strip()
    if not candidate:
        return None
    filename = PurePosixPath(candidate).name
    unsafe_chars = {" ", "'", '"', ";", "\t", "`"}
    if any(char in filename for char in unsafe_chars):
        return (
            "Runtime warning: filename contains spaces or unsafe characters. "
            "Dashboard load parser may reject this program path."
        )
    return None


def normalize_runtime_safe_filename(filename: str) -> str:
    source_name = PurePosixPath(str(filename or "").strip()).name
    if not source_name:
        raise ValueError("Runtime-safe filename cannot be derived from an empty value.")

    path = PurePosixPath(source_name)
    suffix = path.suffix or ".urp"
    stem = path.stem if path.suffix else source_name
    if not stem:
        stem = "program"

    # Keep filename operator-readable while removing parser-risk characters.
    safe_stem = re.sub(r"[\s'\";`\t]+", "_", stem)
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", safe_stem)
    safe_stem = re.sub(r"_+", "_", safe_stem).strip("._-")
    if not safe_stem:
        safe_stem = "program"

    return f"{safe_stem}{suffix}"


def classify_dashboard_load_response(
    raw_dashboard_response: str | None,
    error: Exception | None = None,
) -> tuple[LoadOutcome, list[str]]:
    notes: list[str] = []

    if error is not None:
        text = str(error).strip()
        normalized_error = text.lower()
        if "unsafe runtime path" in normalized_error:
            return (
                "unsafe_runtime_path",
                [text],
            )
        if "unsupported runtime path strategy" in normalized_error:
            return (
                "path_strategy_unknown",
                [text],
            )
        if isinstance(error, TimeoutError) or "timeout" in normalized_error:
            return "timeout", [f"Dashboard load call timed out: {text}"]
        if "remote control" in normalized_error or "manual mode" in normalized_error:
            return (
                "wrong_mode_or_remote_control_issue",
                [f"Dashboard load call failed; robot may not be in remote control mode: {text}"],
            )
        return "load_error", [f"Dashboard load call failed: {text}"]

    response = str(raw_dashboard_response or "").strip()
    normalized = response.lower()
    if not normalized:
        return "unknown_failure", ["Dashboard returned empty load response."]

    if "could not understand" in normalized:
        return (
            "parser_error",
            ["Dashboard rejected the load command syntax or format."],
        )
    if (
        "file not found" in normalized
        or "no such file" in normalized
        or "unable to open" in normalized
    ):
        return (
            "file_not_found",
            ["Dashboard could not resolve the requested program path."],
        )
    if "loading program" in normalized or "loaded program" in normalized:
        return "success", notes
    if (
        "remote control" in normalized
        or "manual mode" in normalized
        or "local control" in normalized
    ):
        return (
            "wrong_mode_or_remote_control_issue",
            ["Dashboard response indicates remote-control mode is not ready for load/play."],
        )
    if (
        "installation" in normalized
        or "safety" in normalized
        or "protective stop" in normalized
    ):
        return (
            "installation_or_safety_block",
            ["Dashboard response indicates installation/safety/runtime preconditions are not met."],
        )
    if (
        "error" in normalized
        or "failed" in normalized
        or "cannot" in normalized
        or "unable" in normalized
    ):
        return "load_error", ["Dashboard returned an explicit load error."]

    return (
        "unknown_failure",
        ["Dashboard response was not recognized as a confirmed success."],
    )


def build_runtime_readiness_snapshot(
    robot_name: str,
    assigned_runtime_path: str | None,
    deployed_primary_path: str | None,
    latest_load_validation: dict | None,
) -> RuntimeReadinessSnapshot:
    assigned = bool(str(assigned_runtime_path or "").strip())
    load_attempted = bool(latest_load_validation)
    load_succeeded = bool(latest_load_validation) and latest_load_validation.get("outcome") == "success"
    load_failed = load_attempted and not load_succeeded
    ready_for_play = load_succeeded
    not_ready_for_play = not ready_for_play
    notes: list[str] = []

    deployed = str(deployed_primary_path or "").strip() or None
    assigned_path = str(assigned_runtime_path or "").strip() or None
    deployed_only = bool(deployed) and (not assigned_path or assigned_path != deployed)

    if deployed and not assigned_path:
        notes.append("Bundle appears deployed, but no runtime path is assigned yet.")
    if deployed and assigned_path and assigned_path != deployed:
        notes.append("Assigned runtime path differs from last deployed primary .urp path.")
    if assigned_path and not load_attempted:
        notes.append("No load attempt has been recorded yet for the current assignment.")
    if load_failed and latest_load_validation:
        notes.append(
            f"Last load attempt failed with outcome '{latest_load_validation.get('outcome')}'."
        )

    return RuntimeReadinessSnapshot(
        robot_name=robot_name,
        deployed_primary_path=deployed,
        assigned_runtime_path=assigned_path,
        deployed_only=deployed_only,
        assigned=assigned,
        load_attempted=load_attempted,
        load_succeeded=load_succeeded,
        load_failed=load_failed,
        ready_for_play=ready_for_play,
        not_ready_for_play=not_ready_for_play,
        notes=notes,
    )
