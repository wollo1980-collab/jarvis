"""Tests für commands/monitor.py - psutil wird gemockt, es wird nichts
vom echten System gelesen."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from commands.monitor import SystemStatusCommand
from core.models import Plan, Status


def test_system_status_success():
    cmd = SystemStatusCommand()
    fake_memory = MagicMock(percent=42.0, used=4 * 1024**3, total=16 * 1024**3)
    with patch("commands.monitor.psutil.cpu_percent", return_value=13.0), patch(
        "commands.monitor.psutil.virtual_memory", return_value=fake_memory
    ):
        result = cmd.execute(Plan(intent="system_status"))
    assert result.status == Status.SUCCESS
    assert "13" in result.message
    assert "42" in result.message
    assert result.data["cpu_percent"] == 13.0
    assert result.data["ram_percent"] == 42.0


def test_system_status_failure_is_reported_not_silent():
    cmd = SystemStatusCommand()
    with patch("commands.monitor.psutil.cpu_percent", side_effect=OSError("boom")):
        result = cmd.execute(Plan(intent="system_status"))
    assert result.status == Status.FAILED


def test_system_status_requires_no_confirmation():
    assert SystemStatusCommand().requires_confirmation is False
