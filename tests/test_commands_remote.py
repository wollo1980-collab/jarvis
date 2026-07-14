"""Tests für commands/remote.py (Fernbedienung, ADR-058) - subprocess und
Tastendruck-Helfer gemockt, es wird nichts wirklich gesperrt, geschlafen
oder an der Lautstärke gedreht."""
from __future__ import annotations

from unittest.mock import patch

import commands.remote as remote
from commands import REGISTRY
from commands.remote import (
    LockPcCommand,
    MediaControlCommand,
    SetVolumeCommand,
    SleepPcCommand,
)
from core.models import Plan, Status


# -- Registrierung / Sicherheitsstufen ----------------------------------


def test_remote_commands_are_registered():
    for intent in ("lock_pc", "set_volume", "media_control", "sleep_pc"):
        assert intent in REGISTRY


def test_confirmation_flags_match_security_levels():
    # Stufe 1: umkehrbar, keine Bestätigung. Stufe 2: Ja/Nein - bewusst
    # KEINE exakte Phrase (das bleibt shutdown_pc/Stufe 3 vorbehalten).
    assert LockPcCommand().requires_confirmation is False
    assert SetVolumeCommand().requires_confirmation is False
    assert MediaControlCommand().requires_confirmation is False
    assert SleepPcCommand().requires_confirmation is True
    assert getattr(SleepPcCommand(), "confirmation_phrase", None) is None


# -- lock_pc -------------------------------------------------------------


def test_lock_pc_windows_uses_rundll32():
    cmd = LockPcCommand()
    with patch("commands.remote.platform.system", return_value="Windows"), patch(
        "commands.remote.subprocess.run"
    ) as run:
        result = cmd.execute(Plan(intent="lock_pc"))
    assert result.status == Status.SUCCESS
    assert run.call_args[0][0] == ["rundll32.exe", "user32.dll,LockWorkStation"]


def test_lock_pc_posix_uses_loginctl():
    cmd = LockPcCommand()
    with patch("commands.remote.platform.system", return_value="Linux"), patch(
        "commands.remote.subprocess.run"
    ) as run:
        result = cmd.execute(Plan(intent="lock_pc"))
    assert result.status == Status.SUCCESS
    assert run.call_args[0][0] == ["loginctl", "lock-session"]


def test_lock_pc_failure_is_reported():
    cmd = LockPcCommand()
    with patch("commands.remote.platform.system", return_value="Windows"), patch(
        "commands.remote.subprocess.run", side_effect=OSError("kein rundll32")
    ):
        result = cmd.execute(Plan(intent="lock_pc"))
    assert result.status == Status.FAILED


# -- set_volume ----------------------------------------------------------


def test_set_volume_without_direction_asks_back():
    cmd = SetVolumeCommand()
    result = cmd.execute(Plan(intent="set_volume"))
    assert result.status == Status.NEEDS_CLARIFICATION


def test_set_volume_unknown_direction_asks_back_and_taps_nothing():
    cmd = SetVolumeCommand()
    with patch("commands.remote._tap_key") as tap:
        result = cmd.execute(Plan(intent="set_volume", target="maximal"))
    assert result.status == Status.NEEDS_CLARIFICATION
    tap.assert_not_called()


def test_set_volume_up_taps_volume_up_key_multiple_times():
    cmd = SetVolumeCommand()
    with patch("commands.remote.platform.system", return_value="Windows"), patch(
        "commands.remote._tap_key"
    ) as tap:
        result = cmd.execute(Plan(intent="set_volume", parameters={"direction": "lauter"}))
    assert result.status == Status.SUCCESS
    tap.assert_called_once_with(remote._VK_VOLUME_UP, times=remote._VOLUME_TAPS)


def test_set_volume_down_reads_direction_from_target():
    cmd = SetVolumeCommand()
    with patch("commands.remote.platform.system", return_value="Windows"), patch(
        "commands.remote._tap_key"
    ) as tap:
        result = cmd.execute(Plan(intent="set_volume", target="leiser"))
    assert result.status == Status.SUCCESS
    tap.assert_called_once_with(remote._VK_VOLUME_DOWN, times=remote._VOLUME_TAPS)


def test_set_volume_mute_taps_mute_key_once():
    cmd = SetVolumeCommand()
    with patch("commands.remote.platform.system", return_value="Windows"), patch(
        "commands.remote._tap_key"
    ) as tap:
        result = cmd.execute(Plan(intent="set_volume", target="stumm"))
    assert result.status == Status.SUCCESS
    tap.assert_called_once_with(remote._VK_VOLUME_MUTE)


def test_set_volume_non_windows_fails_honestly():
    cmd = SetVolumeCommand()
    with patch("commands.remote.platform.system", return_value="Linux"), patch(
        "commands.remote._tap_key"
    ) as tap:
        result = cmd.execute(Plan(intent="set_volume", target="lauter"))
    assert result.status == Status.FAILED
    tap.assert_not_called()


# -- media_control -------------------------------------------------------


def test_media_control_without_action_asks_back():
    cmd = MediaControlCommand()
    result = cmd.execute(Plan(intent="media_control"))
    assert result.status == Status.NEEDS_CLARIFICATION


def test_media_control_play_pause():
    cmd = MediaControlCommand()
    with patch("commands.remote.platform.system", return_value="Windows"), patch(
        "commands.remote._tap_key"
    ) as tap:
        result = cmd.execute(Plan(intent="media_control", parameters={"action": "pause"}))
    assert result.status == Status.SUCCESS
    tap.assert_called_once_with(remote._VK_MEDIA_PLAY_PAUSE)


def test_media_control_next_and_previous_and_stop():
    cmd = MediaControlCommand()
    cases = {
        "naechster": remote._VK_MEDIA_NEXT,
        "vorheriger": remote._VK_MEDIA_PREV,
        "stopp": remote._VK_MEDIA_STOP,
    }
    for word, vk in cases.items():
        with patch("commands.remote.platform.system", return_value="Windows"), patch(
            "commands.remote._tap_key"
        ) as tap:
            result = cmd.execute(Plan(intent="media_control", target=word))
        assert result.status == Status.SUCCESS
        tap.assert_called_once_with(vk)


def test_media_control_non_windows_fails_honestly():
    cmd = MediaControlCommand()
    with patch("commands.remote.platform.system", return_value="Linux"), patch(
        "commands.remote._tap_key"
    ) as tap:
        result = cmd.execute(Plan(intent="media_control", target="pause"))
    assert result.status == Status.FAILED
    tap.assert_not_called()


# -- sleep_pc ------------------------------------------------------------


def test_sleep_pc_needs_confirmation():
    cmd = SleepPcCommand()
    with patch("commands.remote.subprocess.run") as run:
        result = cmd.execute(Plan(intent="sleep_pc", parameters={}))
    assert result.status == Status.NEEDS_CLARIFICATION
    run.assert_not_called()


def test_sleep_pc_confirmed_windows_uses_powrprof():
    cmd = SleepPcCommand()
    with patch("commands.remote.platform.system", return_value="Windows"), patch(
        "commands.remote.subprocess.run"
    ) as run:
        result = cmd.execute(Plan(intent="sleep_pc", parameters={"confirmed": True}))
    assert result.status == Status.SUCCESS
    assert run.call_args[0][0] == ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]


def test_sleep_pc_confirmed_posix_uses_systemctl():
    cmd = SleepPcCommand()
    with patch("commands.remote.platform.system", return_value="Linux"), patch(
        "commands.remote.subprocess.run"
    ) as run:
        result = cmd.execute(Plan(intent="sleep_pc", parameters={"confirmed": True}))
    assert result.status == Status.SUCCESS
    assert run.call_args[0][0] == ["systemctl", "suspend"]


def test_sleep_pc_failure_is_reported():
    cmd = SleepPcCommand()
    with patch("commands.remote.platform.system", return_value="Windows"), patch(
        "commands.remote.subprocess.run", side_effect=OSError("kein rundll32")
    ):
        result = cmd.execute(Plan(intent="sleep_pc", parameters={"confirmed": True}))
    assert result.status == Status.FAILED
