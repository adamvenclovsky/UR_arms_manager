from __future__ import annotations

import pytest

from ur_arms_manager.adapters.ur.dashboard_client import DashboardClient, DashboardError


@pytest.mark.parametrize("command", ["", "play\nstop", "load demo.urp\rpower off"])
def test_dashboard_rejects_empty_or_multiline_commands_before_connect(
    command: str, monkeypatch
) -> None:
    monkeypatch.setattr(
        "ur_arms_manager.adapters.ur.dashboard_client.socket.create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network used")),
    )

    with pytest.raises(DashboardError, match="one non-empty line"):
        DashboardClient("127.0.0.1", 29999).send_command(command)
