from __future__ import annotations

from pathlib import Path

from ur_arms_manager import cli

EXAMPLE_CONFIG = """
robots:
  robot1:
    host: 127.0.0.1
    dashboard_port: 29991
    script_port: 30021
    enabled: true
    assigned_program: null
"""


def test_robot_compatibility_outputs_result(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "robots.yaml"
    config_path.write_text(EXAMPLE_CONFIG, encoding="utf-8")

    class FakeCompatibilityService:
        def __init__(self, _library):
            pass

        class Result:
            overall_status = "warning"
            summary = "Compatibility check found warnings."
            findings = ["Installation dependency detected: default.installation"]

        def evaluate(self, _robot, _program_id):
            return self.Result()

    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr(cli, "CompatibilityService", FakeCompatibilityService)

    exit_code = cli._main(["robot", "compatibility", "robot1", "demo-1234"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "overall_status: warning" in output
    assert "summary: Compatibility check found warnings." in output
    assert "Installation dependency detected" in output
