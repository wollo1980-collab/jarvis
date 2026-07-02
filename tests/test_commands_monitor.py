"""Tests für commands/monitor.py - psutil/winreg/wevtutil (subprocess)
werden gemockt, es wird nichts vom echten System gelesen."""
from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import commands.monitor as monitor_commands
from commands.monitor import AnalyzeEventLogCommand, AnalyzePcCommand, SystemStatusCommand
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


# --- analyze_pc (v0.7 Phase 1, ADR-020) -----------------------------------


def _configure_fake_ai(answer_text: str = "Alles im gruenen Bereich.") -> MagicMock:
    fake_ai = MagicMock()
    fake_ai.answer.return_value = answer_text
    monitor_commands.configure(fake_ai)
    return fake_ai


def _fake_process(pid, name, cpu, ram_bytes):
    proc = MagicMock()
    proc.pid = pid
    proc.info = {"name": name}
    proc.cpu_percent.return_value = cpu
    proc.memory_info.return_value = MagicMock(rss=ram_bytes)
    return proc


def _fake_disk_partition(device):
    part = MagicMock()
    part.device = device
    part.mountpoint = device
    return part


def _patch_registry(monkeypatch, hkcu_entries=(), hklm_entries=(), hkcu_fails=False, hklm_fails=False):
    def fake_open_key(hive, path):
        if hive == monitor_commands.winreg.HKEY_CURRENT_USER and hkcu_fails:
            raise OSError("HKCU nicht lesbar")
        if hive == monitor_commands.winreg.HKEY_LOCAL_MACHINE and hklm_fails:
            raise OSError("HKLM nicht lesbar")
        cm = MagicMock()
        cm.__enter__.return_value = hive
        cm.__exit__.return_value = False
        return cm

    def fake_enum_value(key, index):
        entries = hkcu_entries if key == monitor_commands.winreg.HKEY_CURRENT_USER else hklm_entries
        if index >= len(entries):
            raise OSError("keine weiteren Werte")
        name, value = entries[index]
        return name, value, 1

    monkeypatch.setattr(monitor_commands.winreg, "OpenKey", fake_open_key)
    monkeypatch.setattr(monitor_commands.winreg, "EnumValue", fake_enum_value)


def _base_patches(monkeypatch, tmp_path, processes=(), disks=("C:\\",)):
    monkeypatch.setattr(monitor_commands.platform, "system", lambda: "Windows")
    monkeypatch.setattr(monitor_commands.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        monitor_commands.psutil, "disk_partitions", lambda: [_fake_disk_partition(d) for d in disks]
    )
    monkeypatch.setattr(
        monitor_commands.psutil,
        "disk_usage",
        lambda _: MagicMock(total=100 * 1024**3, used=50 * 1024**3, free=50 * 1024**3, percent=50.0),
    )
    monkeypatch.setattr(monitor_commands.psutil, "process_iter", lambda attrs=None: list(processes))
    # leere, aber funktionierende Autostart-Quellen als Default.
    _patch_registry(monkeypatch)
    appdata = tmp_path / "AppData"
    programdata = tmp_path / "ProgramData"
    monkeypatch.setattr(monitor_commands.os, "environ", {"APPDATA": str(appdata), "PROGRAMDATA": str(programdata)})


def test_analyze_pc_fails_clearly_on_non_windows(monkeypatch):
    _configure_fake_ai()
    monkeypatch.setattr(monitor_commands.platform, "system", lambda: "Linux")
    cmd = AnalyzePcCommand()

    result = cmd.execute(Plan(intent="analyze_pc"))

    assert result.status == Status.FAILED


def test_analyze_pc_collects_disk_usage(monkeypatch, tmp_path):
    fake_ai = _configure_fake_ai()
    _base_patches(monkeypatch, tmp_path, disks=("C:\\", "D:\\"))
    cmd = AnalyzePcCommand()

    result = cmd.execute(Plan(intent="analyze_pc"))

    assert result.status == Status.SUCCESS
    assert len(result.data["disks"]) == 2
    assert result.data["disks"][0]["laufwerk"] == "C:\\"
    assert result.data["disks"][0]["prozent"] == 50.0
    fake_ai.answer.assert_called_once()


def test_analyze_pc_top_processes_by_cpu_and_ram(monkeypatch, tmp_path):
    _configure_fake_ai()
    processes = [
        _fake_process(1, "chrome.exe", cpu=80.0, ram_bytes=100 * 1024**2),
        _fake_process(2, "idle.exe", cpu=0.5, ram_bytes=10 * 1024**2),
        _fake_process(3, "heavy_ram.exe", cpu=1.0, ram_bytes=900 * 1024**2),
    ]
    _base_patches(monkeypatch, tmp_path, processes=processes)
    cmd = AnalyzePcCommand()

    result = cmd.execute(Plan(intent="analyze_pc"))

    assert result.status == Status.SUCCESS
    assert result.data["top_cpu"][0]["name"] == "chrome.exe"
    assert result.data["top_ram"][0]["name"] == "heavy_ram.exe"


def test_analyze_pc_detects_duplicate_processes(monkeypatch, tmp_path):
    _configure_fake_ai()
    processes = [
        _fake_process(1, "discord.exe", cpu=1.0, ram_bytes=1024**2),
        _fake_process(2, "discord.exe", cpu=1.0, ram_bytes=1024**2),
        _fake_process(3, "unique.exe", cpu=1.0, ram_bytes=1024**2),
    ]
    _base_patches(monkeypatch, tmp_path, processes=processes)
    cmd = AnalyzePcCommand()

    result = cmd.execute(Plan(intent="analyze_pc"))

    assert result.data["duplicate_processes"] == [{"name": "discord.exe", "anzahl": 2}]


def test_analyze_pc_process_error_is_skipped_not_fatal(monkeypatch, tmp_path):
    _configure_fake_ai()
    broken = MagicMock()
    broken.cpu_percent.side_effect = monitor_commands.psutil.NoSuchProcess(pid=99)
    ok = _fake_process(1, "ok.exe", cpu=1.0, ram_bytes=1024**2)
    _base_patches(monkeypatch, tmp_path, processes=[broken, ok])
    cmd = AnalyzePcCommand()

    result = cmd.execute(Plan(intent="analyze_pc"))

    assert result.status == Status.SUCCESS
    assert all(p["name"] != "?" for p in result.data["top_cpu"])


def test_analyze_pc_reads_registry_autostart_from_both_hives(monkeypatch, tmp_path):
    _configure_fake_ai()
    _base_patches(monkeypatch, tmp_path)
    _patch_registry(
        monkeypatch,
        hkcu_entries=[("OneDrive", "C:\\OneDrive.exe")],
        hklm_entries=[("Steam", "C:\\Steam.exe")],
    )
    cmd = AnalyzePcCommand()

    result = cmd.execute(Plan(intent="analyze_pc"))

    names = {a["name"] for a in result.data["autostart"]}
    assert names == {"OneDrive", "Steam"}


def test_analyze_pc_registry_failure_is_partial_not_fatal(monkeypatch, tmp_path):
    _configure_fake_ai()
    _base_patches(monkeypatch, tmp_path)
    _patch_registry(monkeypatch, hklm_entries=[("Steam", "C:\\Steam.exe")], hkcu_fails=True)
    cmd = AnalyzePcCommand()

    result = cmd.execute(Plan(intent="analyze_pc"))

    assert result.status == Status.SUCCESS
    assert any("HKCU" in e for e in result.data["autostart_errors"])
    assert any(a["name"] == "Steam" for a in result.data["autostart"])


def test_analyze_pc_reads_startup_folder_entries(monkeypatch, tmp_path):
    _configure_fake_ai()
    _base_patches(monkeypatch, tmp_path)
    startup_dir = tmp_path / "AppData" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    startup_dir.mkdir(parents=True)
    (startup_dir / "Dropbox.lnk").touch()
    cmd = AnalyzePcCommand()

    result = cmd.execute(Plan(intent="analyze_pc"))

    names = {a["name"] for a in result.data["autostart"]}
    assert "Dropbox.lnk" in names


def test_analyze_pc_ai_gets_structured_text_and_disclaimer_is_appended(monkeypatch, tmp_path):
    fake_ai = _configure_fake_ai("Standort-Analyse: alles unauffaellig.")
    _base_patches(monkeypatch, tmp_path)
    cmd = AnalyzePcCommand()

    result = cmd.execute(Plan(intent="analyze_pc"))

    assert "Standort-Analyse: alles unauffaellig." in result.message
    assert "Bitte vor Entscheidungen prüfen" in result.message
    prompt_arg = fake_ai.answer.call_args.args[0]
    assert "[Festplatten]" in prompt_arg
    assert "Rechne selbst nichts nach" in prompt_arg


def test_analyze_pc_raises_clear_error_when_not_configured(monkeypatch, tmp_path):
    monkeypatch.setattr(monitor_commands, "_ai_engine", None)
    _base_patches(monkeypatch, tmp_path)
    cmd = AnalyzePcCommand()

    try:
        cmd.execute(Plan(intent="analyze_pc"))
        assert False, "hätte RuntimeError werfen müssen"
    except RuntimeError as e:
        assert "configure()" in str(e)


def test_analyze_pc_requires_no_confirmation():
    assert AnalyzePcCommand().requires_confirmation is False


def test_analyze_pc_registered_in_registry():
    from commands import REGISTRY

    assert "analyze_pc" in REGISTRY


# --- analyze_event_log (v0.7 Phase 2, ADR-021) ----------------------------


def _rendered_xml_event(event_id, provider, level_text, message, system_time="2026-07-01T10:00:00.000000000Z"):
    return (
        '<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">'
        "<System>"
        f'<Provider Name="{provider}" />'
        f"<EventID>{event_id}</EventID>"
        "<Level>2</Level>"
        f'<TimeCreated SystemTime="{system_time}" />'
        "<Channel>System</Channel>"
        "</System>"
        f'<RenderingInfo Culture="de-DE"><Message>{message}</Message><Level>{level_text}</Level></RenderingInfo>'
        "</Event>"
    )


def _fake_wevtutil_result(stdout):
    proc = MagicMock()
    proc.stdout = stdout
    return proc


def test_analyze_event_log_fails_clearly_on_non_windows(monkeypatch):
    _configure_fake_ai()
    monkeypatch.setattr(monitor_commands.platform, "system", lambda: "Linux")
    cmd = AnalyzeEventLogCommand()

    result = cmd.execute(Plan(intent="analyze_event_log"))

    assert result.status == Status.FAILED


def test_parse_event_log_xml_extracts_fields():
    raw = _rendered_xml_event(41, "Kernel-Power", "Fehler", "Unerwarteter Neustart")

    entries = monitor_commands._parse_event_log_xml(raw, "System")

    assert len(entries) == 1
    entry = entries[0]
    assert entry["log"] == "System"
    assert entry["event_id"] == "41"
    assert entry["quelle"] == "Kernel-Power"
    assert entry["stufe"] == "Fehler"
    assert entry["meldung"] == "Unerwarteter Neustart"
    assert entry["zeit"] == "2026-07-01T10:00:00.000000000Z"


def test_parse_event_log_xml_truncates_long_message():
    long_message = "x" * 500
    raw = _rendered_xml_event(1, "SomeProvider", "Warnung", long_message)

    entries = monitor_commands._parse_event_log_xml(raw, "Application")

    assert len(entries[0]["meldung"]) == monitor_commands._MESSAGE_TRUNCATE_LENGTH


def test_parse_event_log_xml_empty_output_returns_no_entries():
    assert monitor_commands._parse_event_log_xml("", "System") == []


def test_collect_event_log_handles_missing_wevtutil(monkeypatch):
    monkeypatch.setattr(
        monitor_commands.subprocess, "run", MagicMock(side_effect=FileNotFoundError())
    )

    entries, error = monitor_commands._collect_event_log("System")

    assert entries == []
    assert "wevtutil nicht gefunden" in error


def test_collect_event_log_handles_timeout(monkeypatch):
    monkeypatch.setattr(
        monitor_commands.subprocess,
        "run",
        MagicMock(side_effect=subprocess.TimeoutExpired(cmd="wevtutil", timeout=15)),
    )

    entries, error = monitor_commands._collect_event_log("System")

    assert entries == []
    assert "Zeitüberschreitung" in error


def test_collect_event_log_handles_called_process_error(monkeypatch):
    err = subprocess.CalledProcessError(returncode=1, cmd="wevtutil", stderr="Zugriff verweigert")
    monkeypatch.setattr(monitor_commands.subprocess, "run", MagicMock(side_effect=err))

    entries, error = monitor_commands._collect_event_log("Application")

    assert entries == []
    assert "Zugriff verweigert" in error


def test_collect_event_log_handles_malformed_xml(monkeypatch):
    monkeypatch.setattr(
        monitor_commands.subprocess,
        "run",
        MagicMock(return_value=_fake_wevtutil_result("<Event><Unclosed>")),
    )

    entries, error = monitor_commands._collect_event_log("System")

    assert entries == []
    assert "System" in error


def test_collect_event_log_success(monkeypatch):
    raw = _rendered_xml_event(41, "Kernel-Power", "Fehler", "Unerwarteter Neustart")
    monkeypatch.setattr(
        monitor_commands.subprocess, "run", MagicMock(return_value=_fake_wevtutil_result(raw))
    )

    entries, error = monitor_commands._collect_event_log("System")

    assert error is None
    assert len(entries) == 1


def test_analyze_event_log_success_calls_ai_with_structured_text_and_disclaimer(monkeypatch):
    fake_ai = _configure_fake_ai("Ein Neustart war ungeplant, sonst unauffaellig.")
    monkeypatch.setattr(monitor_commands.platform, "system", lambda: "Windows")

    system_xml = _rendered_xml_event(41, "Kernel-Power", "Fehler", "Unerwarteter Neustart")
    app_xml = _rendered_xml_event(1000, "Application Error", "Warnung", "App abgestuerzt")

    def fake_run(cmd, **kwargs):
        log_name = cmd[2]
        raw = system_xml if log_name == "System" else app_xml
        return _fake_wevtutil_result(raw)

    monkeypatch.setattr(monitor_commands.subprocess, "run", MagicMock(side_effect=fake_run))
    cmd = AnalyzeEventLogCommand()

    result = cmd.execute(Plan(intent="analyze_event_log"))

    assert result.status == Status.SUCCESS
    assert "Ein Neustart war ungeplant, sonst unauffaellig." in result.message
    assert "Bitte vor Entscheidungen prüfen" in result.message
    prompt_arg = fake_ai.answer.call_args.args[0]
    assert "[System]" in prompt_arg
    assert "[Application]" in prompt_arg
    assert "Kernel-Power" in prompt_arg
    assert "Rechne/zähle selbst nichts nach" in prompt_arg
    assert len(result.data["events"]["System"]) == 1
    assert len(result.data["events"]["Application"]) == 1


def test_analyze_event_log_uses_level_and_count_filter_and_two_logs(monkeypatch):
    _configure_fake_ai()
    monkeypatch.setattr(monitor_commands.platform, "system", lambda: "Windows")
    run_mock = MagicMock(return_value=_fake_wevtutil_result(""))
    monkeypatch.setattr(monitor_commands.subprocess, "run", run_mock)
    cmd = AnalyzeEventLogCommand()

    cmd.execute(Plan(intent="analyze_event_log"))

    assert run_mock.call_count == 2
    called_logs = {call.args[0][2] for call in run_mock.call_args_list}
    assert called_logs == {"System", "Application"}
    for call in run_mock.call_args_list:
        cmd_args = call.args[0]
        assert cmd_args[0] == "wevtutil"
        assert f"/c:{monitor_commands._MAX_EVENTS_PER_LOG}" in cmd_args
        assert any("Level=2" in a and "Level=3" in a for a in cmd_args)


def test_analyze_event_log_partial_failure_still_succeeds(monkeypatch):
    fake_ai = _configure_fake_ai()
    monkeypatch.setattr(monitor_commands.platform, "system", lambda: "Windows")
    app_xml = _rendered_xml_event(1000, "Application Error", "Warnung", "App abgestuerzt")

    def fake_run(cmd, **kwargs):
        log_name = cmd[2]
        if log_name == "System":
            raise subprocess.CalledProcessError(returncode=1, cmd="wevtutil", stderr="nicht lesbar")
        return _fake_wevtutil_result(app_xml)

    monkeypatch.setattr(monitor_commands.subprocess, "run", MagicMock(side_effect=fake_run))
    cmd = AnalyzeEventLogCommand()

    result = cmd.execute(Plan(intent="analyze_event_log"))

    assert result.status == Status.SUCCESS
    assert any("System" in e for e in result.data["errors"])
    assert len(result.data["events"]["Application"]) == 1
    fake_ai.answer.assert_called_once()


def test_analyze_event_log_fails_when_both_logs_unreadable(monkeypatch):
    fake_ai = _configure_fake_ai()
    monkeypatch.setattr(monitor_commands.platform, "system", lambda: "Windows")
    err = subprocess.CalledProcessError(returncode=1, cmd="wevtutil", stderr="nicht lesbar")
    monkeypatch.setattr(monitor_commands.subprocess, "run", MagicMock(side_effect=err))
    cmd = AnalyzeEventLogCommand()

    result = cmd.execute(Plan(intent="analyze_event_log"))

    assert result.status == Status.FAILED
    assert "nicht lesbar" in result.message
    fake_ai.answer.assert_not_called()


def test_analyze_event_log_raises_clear_error_when_not_configured(monkeypatch):
    monkeypatch.setattr(monitor_commands, "_ai_engine", None)
    monkeypatch.setattr(monitor_commands.platform, "system", lambda: "Windows")
    raw = _rendered_xml_event(41, "Kernel-Power", "Fehler", "Unerwarteter Neustart")
    monkeypatch.setattr(
        monitor_commands.subprocess, "run", MagicMock(return_value=_fake_wevtutil_result(raw))
    )
    cmd = AnalyzeEventLogCommand()

    try:
        cmd.execute(Plan(intent="analyze_event_log"))
        assert False, "hätte RuntimeError werfen müssen"
    except RuntimeError as e:
        assert "configure()" in str(e)


def test_analyze_event_log_requires_no_confirmation():
    assert AnalyzeEventLogCommand().requires_confirmation is False


def test_analyze_event_log_registered_in_registry():
    from commands import REGISTRY

    assert "analyze_event_log" in REGISTRY
