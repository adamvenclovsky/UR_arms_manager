from __future__ import annotations

import sys
import types

import pytest

from ur_arms_manager.adapters.ur.rtde_client import RTDEClient, RTDEError


def test_read_status_returns_normalized_structure(monkeypatch) -> None:
    disconnected: list[bool] = []

    class FakeRTDEReceiveInterface:
        def __init__(self, host: str):
            assert host == "127.0.0.1"

        def isConnected(self) -> bool:
            return True

        def getRobotMode(self) -> str:
            return "RUNNING"

        def getRuntimeState(self) -> str:
            return "PLAYING"

        def getSafetyMode(self) -> str:
            return "NORMAL"

        def disconnect(self) -> None:
            disconnected.append(True)

    fake_module = types.SimpleNamespace(RTDEReceiveInterface=FakeRTDEReceiveInterface)
    monkeypatch.setitem(sys.modules, "rtde_receive", fake_module)

    client = RTDEClient(host="127.0.0.1")
    status = client.read_status()

    assert status.connected is True
    assert status.robot_mode == "RUNNING"
    assert status.runtime_state == "PLAYING"
    assert status.safety_state == "NORMAL"
    assert status.detail == "RTDE status read succeeded"
    assert disconnected == [True]


def test_read_status_handles_missing_dependency(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "rtde_receive", raising=False)

    original_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "rtde_receive":
            raise ModuleNotFoundError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    client = RTDEClient(host="127.0.0.1")

    with pytest.raises(RTDEError) as exc_info:
        client.read_status()

    assert "dependency is not installed" in str(exc_info.value)


def test_read_status_wraps_connection_failures(monkeypatch) -> None:
    class FakeRTDEReceiveInterface:
        def __init__(self, _host: str):
            raise RuntimeError("connection refused")

    fake_module = types.SimpleNamespace(RTDEReceiveInterface=FakeRTDEReceiveInterface)
    monkeypatch.setitem(sys.modules, "rtde_receive", fake_module)

    client = RTDEClient(host="127.0.0.1")

    with pytest.raises(RTDEError) as exc_info:
        client.read_status()

    assert "RTDE connection failed" in str(exc_info.value)
    assert "connection refused" in str(exc_info.value)


def test_read_status_falls_back_to_unknown_for_unstable_fields(monkeypatch) -> None:
    class FakeRTDEReceiveInterface:
        def __init__(self, _host: str):
            pass

        def isConnected(self) -> bool:
            return False

        def getRobotMode(self) -> str:
            raise RuntimeError("not available")

        def disconnect(self) -> None:
            pass

    fake_module = types.SimpleNamespace(RTDEReceiveInterface=FakeRTDEReceiveInterface)
    monkeypatch.setitem(sys.modules, "rtde_receive", fake_module)

    client = RTDEClient(host="127.0.0.1")
    status = client.read_status()

    assert status.connected is False
    assert status.robot_mode == "unknown"
    assert status.runtime_state == "unknown"
    assert status.safety_state == "unknown"
    assert status.detail == "RTDE connected flag is false"
