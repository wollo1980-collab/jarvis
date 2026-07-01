"""Tests für commands/system.py - subprocess/shutil/os.startfile
gemockt, es wird nichts wirklich gestartet oder heruntergefahren."""
from __future__ import annotations

from unittest.mock import patch

from commands.system import OpenProgramCommand, ShutdownPcCommand
from core.models import Plan, Status


def test_open_program_needs_target():
    cmd = OpenProgramCommand()
    result = cmd.execute(Plan(intent="open_program", target=None))
    assert result.status == Status.NEEDS_CLARIFICATION


def test_open_program_not_found_posix():
    cmd = OpenProgramCommand()
    with patch("commands.system.platform.system", return_value="Linux"), patch(
        "commands.system.shutil.which", return_value=None
    ):
        result = cmd.execute(Plan(intent="open_program", target="nonexistent_prog_xyz"))
    assert result.status == Status.FAILED


def test_open_program_success_posix():
    cmd = OpenProgramCommand()
    with patch("commands.system.platform.system", return_value="Linux"), patch(
        "commands.system.shutil.which", return_value="/usr/bin/foo"
    ), patch("commands.system.subprocess.Popen") as popen:
        result = cmd.execute(Plan(intent="open_program", target="foo"))
    assert result.status == Status.SUCCESS
    popen.assert_called_once()


def test_open_program_success_windows_uses_startfile():
    """os.startfile löst über die App-Paths-Registry auf - shutil.which
    (nur PATH) findet z. B. Excel meist nicht, obwohl installiert."""
    cmd = OpenProgramCommand()
    with patch("commands.system.platform.system", return_value="Windows"), patch(
        "commands.system.os.startfile", create=True
    ) as startfile:
        result = cmd.execute(Plan(intent="open_program", target="excel"))
    assert result.status == Status.SUCCESS
    startfile.assert_called_once()


def test_open_program_not_found_windows():
    cmd = OpenProgramCommand()
    with patch("commands.system.platform.system", return_value="Windows"), patch(
        "commands.system.os.startfile", create=True, side_effect=OSError("nicht gefunden")
    ):
        result = cmd.execute(Plan(intent="open_program", target="nonexistent_prog_xyz"))
    assert result.status == Status.FAILED


def test_shutdown_needs_confirmation():
    cmd = ShutdownPcCommand()
    result = cmd.execute(Plan(intent="shutdown_pc", parameters={}))
    assert result.status == Status.NEEDS_CLARIFICATION


def test_shutdown_confirmed_runs_subprocess():
    cmd = ShutdownPcCommand()
    with patch("commands.system.subprocess.run") as run:
        result = cmd.execute(Plan(intent="shutdown_pc", parameters={"confirmed": True}))
    assert result.status == Status.SUCCESS
    run.assert_called_once()


def test_commands_flag_confirmation_requirement_correctly():
    assert OpenProgramCommand().requires_confirmation is False
    assert ShutdownPcCommand().requires_confirmation is True


def test_shutdown_requires_stufe3_confirmation_phrase():
    # Lesson Learned 2026-07-01: ein einfaches "ja" hat versehentlich
    # einen echten PC-Shutdown ausgelöst - Stufe 3 braucht mehr.
    assert ShutdownPcCommand().confirmation_phrase == "HERUNTERFAHREN"
