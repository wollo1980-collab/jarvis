"""Tests für commands/installer.py - subprocess/shutil/platform
gemockt, es wird nie wirklich winget aufgerufen."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from commands.installer import InstallProgramCommand
from core.models import Plan, Status


def test_install_needs_target():
    cmd = InstallProgramCommand()
    result = cmd.execute(Plan(intent="install_program", target=None))
    assert result.status == Status.NEEDS_CLARIFICATION


def test_install_fails_on_non_windows():
    cmd = InstallProgramCommand()
    with patch("commands.installer.platform.system", return_value="Linux"):
        result = cmd.execute(Plan(intent="install_program", target="vlc"))
    assert result.status == Status.FAILED


def test_install_fails_when_winget_missing():
    cmd = InstallProgramCommand()
    with patch("commands.installer.platform.system", return_value="Windows"), patch(
        "commands.installer.shutil.which", return_value=None
    ):
        result = cmd.execute(Plan(intent="install_program", target="vlc"))
    assert result.status == Status.FAILED


def test_install_success_known_package_uses_exact_id():
    cmd = InstallProgramCommand()
    fake_proc = MagicMock(returncode=0, stdout="", stderr="")
    with patch("commands.installer.platform.system", return_value="Windows"), patch(
        "commands.installer.shutil.which", return_value="C:\\winget.exe"
    ), patch("commands.installer.subprocess.run", return_value=fake_proc) as run:
        result = cmd.execute(Plan(intent="install_program", target="vlc"))
    assert result.status == Status.SUCCESS
    assert result.message == "Ich habe vlc installiert."
    called_cmd = run.call_args.args[0]
    assert "--id" in called_cmd
    assert "VideoLAN.VLC" in called_cmd


def test_install_success_unknown_package_uses_freetext():
    cmd = InstallProgramCommand()
    fake_proc = MagicMock(returncode=0, stdout="", stderr="")
    with patch("commands.installer.platform.system", return_value="Windows"), patch(
        "commands.installer.shutil.which", return_value="C:\\winget.exe"
    ), patch("commands.installer.subprocess.run", return_value=fake_proc) as run:
        result = cmd.execute(Plan(intent="install_program", target="SomeUnknownTool"))
    assert result.status == Status.SUCCESS
    called_cmd = run.call_args.args[0]
    assert "--id" not in called_cmd
    assert "SomeUnknownTool" in called_cmd


def test_install_reports_failure_on_nonzero_returncode():
    cmd = InstallProgramCommand()
    fake_proc = MagicMock(returncode=1, stdout="", stderr="No package found matching input criteria.")
    with patch("commands.installer.platform.system", return_value="Windows"), patch(
        "commands.installer.shutil.which", return_value="C:\\winget.exe"
    ), patch("commands.installer.subprocess.run", return_value=fake_proc):
        result = cmd.execute(Plan(intent="install_program", target="doesnotexist"))
    assert result.status == Status.FAILED
    assert "No package found" in result.message


def test_install_handles_timeout():
    cmd = InstallProgramCommand()
    with patch("commands.installer.platform.system", return_value="Windows"), patch(
        "commands.installer.shutil.which", return_value="C:\\winget.exe"
    ), patch(
        "commands.installer.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="winget", timeout=300),
    ):
        result = cmd.execute(Plan(intent="install_program", target="vlc"))
    assert result.status == Status.FAILED


def test_install_requires_confirmation_stufe_2_not_stufe_3():
    cmd = InstallProgramCommand()
    assert cmd.requires_confirmation is True
    assert getattr(cmd, "confirmation_phrase", None) is None
