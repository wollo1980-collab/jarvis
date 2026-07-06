"""
System-Ueberwachung: liest CPU- und RAM-Auslastung aus (psutil,
ADR-011) sowie einen erweiterten PC-Gesundheitsbericht (v0.7 Phase 1,
ADR-020): Festplattenbelegung, Top-Prozesse, mehrfach laufende
Prozesse, Autostart-Programme.

Sicherheitsstufe 0 (Handbook Kap. 10) fuer beide Commands - reine
Leseaktionen, veraendern nichts am System, brauchen deshalb keine
Bestaetigung.

Temperatur (ebenfalls in Kap. 17 genannt) ist bewusst NICHT enthalten:
psutil.sensors_temperatures() ist unter Windows nicht verfuegbar (nur
Linux/macOS) - aehnliche Einschraenkung wie Kokoro TTS ohne Deutsch,
lieber ehrlich weglassen als eine falsche Erwartung wecken.

analyze_pc (ADR-020) ruft wie analyze_report/calculate_kpi
(ADR-015/016) direkt die KI auf: Python sammelt und strukturiert alle
Daten deterministisch, die KI formuliert nur den Bericht und
interpretiert Auffaelligkeiten - sie rechnet nichts nach. Eigenes,
zu commands/reports.py bewusst dupliziertes configure()-Muster statt
einer gemeinsamen Abstraktion (Wolfgangs Entscheidung: erst pruefen,
wenn ein dritter Bereich KI-Zugriff braucht).

analyze_event_log (v0.7 Phase 2, ADR-021) liest ueber wevtutil
(Windows-Bordmittel, subprocess, keine neue Abhaengigkeit) die
juengsten Fehler/Warnungen aus System- und Application-Log und nutzt
dasselbe deterministisch-sammeln/KI-nur-formuliert-Muster wie
analyze_pc.

disable_autostart_entry/enable_autostart_entry (v0.7 Phase 3, ADR-022)
sind die ersten SCHREIBENDEN PC-Admin-Commands - Sicherheitsstufe 2,
beschraenkt auf HKCU Run-Key und Startup-Ordner (Benutzer), kein
HKLM-Schreibzugriff, keine Administratorrechte. Deaktivieren entfernt
den Eintrag aus der echten Quelle und sichert ihn (Registry: Klartext
in einem eigenen Jarvis-Registry-Zweig, kein StartupApproved-
Binaerformat; Startup-Ordner: Verschieben in einen Jarvis-Unterordner)
- nie loeschen. Kein KI-Zugriff noetig (deterministischer Text).

analyze_temp_files/clean_temp_files (v0.7 Phase 4, ADR-023):
analyze_temp_files (Sicherheitsstufe 0) zeigt, wie viele Temp-Dateien
(aelter als _TEMP_FILE_MIN_AGE_HOURS) im Benutzer-Temp-Ordner liegen.
clean_temp_files (Sicherheitsstufe 3, confirmation_phrase
"BEREINIGEN") loescht sie - erster tatsaechlich LOESCHENDER PC-Admin-
Command (anders als das reversible Deaktivieren in Phase 3). Nutzt den
neuen, optionalen Executor-Hook preview() (ADR-023), um vor der
Bestaetigung eine frisch gescannte Vorschau zu zeigen - execute()
verlaesst sich nie auf das preview()-Ergebnis, sondern scannt beim
tatsaechlichen Loeschen erneut. Beschraenkt auf %TEMP%, nur Dateien
(nie Ordner), Pfad-Eindaemmung gegen Ziele ausserhalb von %TEMP%.

enable_jarvis_autostart/disable_jarvis_autostart (Jarvis-Eigenstart,
ADR-028): registrieren/entfernen Jarvis selbst (jarvis_runtime.py) als
Windows-Autostart-Eintrag - eigener, fester HKCU-Run-Key-Name "Jarvis",
kein Bezug zu disable_/enable_autostart_entry (die verwalten FREMDE,
bereits existierende Eintraege; hier wird ein eigener Eintrag erzeugt/
geloescht). Sicherheitsstufe 2. Ziel ist pythonw.exe (kein
Konsolenfenster - ein versehentliches Schliessen wuerde sonst den
gesamten Runtime-Prozess inkl. Telegram-Kanal beenden), mit Fallback
auf sys.executable, falls pythonw.exe nicht gefunden wird.
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import psutil

from core.config import BASE_DIR
from core.models import Plan, Result, Status

try:
    import winreg
except ImportError:  # pragma: no cover - winreg existiert nur unter Windows
    winreg = None  # type: ignore[assignment]

if TYPE_CHECKING:
    # Nur fuer Type Hints - core.ai importiert seinerseits commands.REGISTRY
    # auf Modulebene. Ein echter (nicht TYPE_CHECKING-) Import hier wuerde
    # bei "core.ai zuerst importiert" einen Zirkelimport ausloesen, siehe
    # ADR-015.
    from core.ai import AIEngine

logger = logging.getLogger("jarvis.commands.monitor")

_ai_engine: Optional["AIEngine"] = None

_TOP_N_PROCESSES = 5
# Sekunden zwischen den zwei cpu_percent()-Messungen pro Prozess - ohne
# Pause liefert psutil beim ersten Aufruf nur 0.0 (Kap. 5: keine Magic
# Values, benannte Konstante statt Literal im Code).
_PROCESS_SAMPLE_INTERVAL = 0.5

_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_STARTUP_FOLDER_SOURCES = (
    ("APPDATA", "Startup (Benutzer)"),
    ("PROGRAMDATA", "Startup (Alle Benutzer)"),
)
_STARTUP_FOLDER_SUFFIX = ("Microsoft", "Windows", "Start Menu", "Programs", "Startup")

# Pflicht-Hinweis (Wolfgangs Entscheidung, siehe ADR-015): KI-Analyse
# kann falsch liegen - Jarvis behauptet keine geschaeftskritische
# Wahrheit, sondern liefert einen Assistenzhinweis. Bewusst als eigene
# Konstante dupliziert statt aus commands.reports importiert (kein
# Zugriff auf private Namen eines anderen Moduls).
_DISCLAIMER = "Analyse auf Basis der gelieferten Daten. Bitte vor Entscheidungen prüfen."

_ANALYSIS_PROMPT_TEMPLATE = (
    "Erstelle aus den folgenden, bereits berechneten PC-Analysedaten einen "
    "kurzen, zusammenhängenden Gesundheitsbericht auf Deutsch. Interpretiere "
    "Auffälligkeiten (z. B. hohe Festplattenbelegung, auffällig hohe CPU-/"
    "RAM-Verbraucher, mehrfach laufende Prozesse, ungewöhnlich viele "
    "Autostart-Einträge). Rechne selbst nichts nach - die Zahlen sind "
    "bereits final.\n\nDaten:\n{data}"
)

# --- analyze_event_log (v0.7 Phase 2, ADR-021) ---------------------------

_EVENT_LOG_NAMES = ("System", "Application")
# Anzahl statt Zeitraum-Filter (Wolfgangs Vorgabe erlaubte beides) - konsistent
# mit _TOP_N_PROCESSES, kein kompletter Log-Dump.
_MAX_EVENTS_PER_LOG = 20
_EVENT_QUERY_TIMEOUT = 15
# Level 2 = Error, Level 3 = Warning (wevtutil-Standardwerte) - bewusst kein
# Level 1 (Critical) oder 4/5 (Information/Verbose), siehe ADR-021.
_EVENT_LEVEL_XPATH = "*[System[(Level=2 or Level=3)]]"
_EVENT_XML_NS = "{http://schemas.microsoft.com/win/2004/08/events/event}"
_MESSAGE_TRUNCATE_LENGTH = 200

_EVENT_LOG_PROMPT_TEMPLATE = (
    "Erstelle aus den folgenden, bereits gesammelten Ereignisprotokoll-"
    "Einträgen (Windows System-/Application-Log, nur Fehler/Warnungen, "
    "neueste zuerst) einen kurzen, zusammenhängenden Bericht auf Deutsch. "
    "Fasse wiederkehrende oder auffällige Einträge zusammen. Rechne/zähle "
    "selbst nichts nach - die Daten sind bereits final.\n\nDaten:\n{data}"
)

# --- disable_autostart_entry / enable_autostart_entry (v0.7 Phase 3, ADR-022) --

# Jarvis-eigener Registry-Zweig (HKCU) fuer deaktivierte Run-Key-Eintraege -
# Klartext-Sicherung statt des internen, undokumentierten
# StartupApproved-Binaerformats (Product-Owner-Entscheidung, ADR-022).
_JARVIS_DISABLED_REGISTRY_PATH = r"Software\Jarvis\DisabledAutostart\Run"
# Jarvis-eigener Unterordner innerhalb des echten Benutzer-Startup-Ordners.
_STARTUP_DISABLED_SUBFOLDER_NAME = "_jarvis_disabled"

# --- analyze_temp_files / clean_temp_files (v0.7 Phase 4, ADR-023) -------

# Nur Dateien, die seit mindestens so vielen Stunden nicht mehr
# geaendert wurden, gelten als "bereinigbar" - vermeidet, gerade aktiv
# geschriebene Dateien zu treffen.
_TEMP_FILE_MIN_AGE_HOURS = 24
_CLEAN_TEMP_CONFIRMATION_PHRASE = "BEREINIGEN"


def configure(ai_engine: "AIEngine") -> None:
    """Von main.py einmal beim Start aufgerufen (analog
    commands/reports.py, ADR-015) - die Registry instanziiert Commands
    beim Modul-Import, bevor AIEngine existiert."""
    global _ai_engine
    _ai_engine = ai_engine


def _require_ai_engine() -> "AIEngine":
    if _ai_engine is None:
        raise RuntimeError(
            "AIEngine nicht konfiguriert - commands.monitor.configure() "
            "muss beim Start aufgerufen werden (siehe main.py)."
        )
    return _ai_engine


class SystemStatusCommand:
    name = "system_status"
    description = "Zeigt aktuelle CPU- und RAM-Auslastung an (nur lesen, Sicherheitsstufe 0)."
    # Reine Leseaktion (Sicherheitsstufe 0) - keine Bestaetigung noetig.
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        try:
            cpu_percent = psutil.cpu_percent(interval=0.5)
            memory = psutil.virtual_memory()
        except Exception as e:
            return Result(
                status=Status.FAILED,
                message=f"Systemstatus konnte nicht ermittelt werden: {e}",
            )

        message = (
            f"CPU-Auslastung: {cpu_percent:.0f} %. "
            f"RAM: {memory.percent:.0f} % belegt "
            f"({_format_gb(memory.used)} von {_format_gb(memory.total)})."
        )
        return Result(
            status=Status.SUCCESS,
            message=message,
            data={"cpu_percent": cpu_percent, "ram_percent": memory.percent},
        )


def _format_gb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 ** 3):.1f} GB"


# --- analyze_pc (v0.7 Phase 1, ADR-020) ----------------------------------


def _collect_disk_usage() -> list[dict]:
    disks = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        disks.append(
            {
                "laufwerk": part.device,
                "gesamt_gb": round(usage.total / (1024**3), 1),
                "belegt_gb": round(usage.used / (1024**3), 1),
                "frei_gb": round(usage.free / (1024**3), 1),
                "prozent": usage.percent,
            }
        )
    return disks


def _collect_process_data() -> tuple[list[dict], list[dict], list[dict]]:
    """Liefert (top_cpu, top_ram, duplikate). Zwei Messpunkte mit Pause
    (_PROCESS_SAMPLE_INTERVAL), da cpu_percent() sonst nur 0.0 liefert."""
    procs = list(psutil.process_iter(["pid", "name"]))
    for p in procs:
        try:
            p.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    time.sleep(_PROCESS_SAMPLE_INTERVAL)

    collected = []
    for p in procs:
        try:
            cpu = p.cpu_percent(None)
            ram_bytes = p.memory_info().rss
            name = p.info.get("name") or "?"
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        collected.append({"pid": p.pid, "name": name, "cpu_percent": cpu, "ram_bytes": ram_bytes})

    top_cpu = sorted(collected, key=lambda x: x["cpu_percent"], reverse=True)[:_TOP_N_PROCESSES]
    top_ram = sorted(collected, key=lambda x: x["ram_bytes"], reverse=True)[:_TOP_N_PROCESSES]

    name_counts = Counter(p["name"] for p in collected)
    duplicates = [
        {"name": name, "anzahl": count} for name, count in sorted(name_counts.items()) if count > 1
    ]
    return top_cpu, top_ram, duplicates


def _collect_registry_autostart() -> tuple[list[dict], list[str]]:
    entries: list[dict] = []
    errors: list[str] = []
    for hive, hive_name in ((winreg.HKEY_CURRENT_USER, "HKCU"), (winreg.HKEY_LOCAL_MACHINE, "HKLM")):
        try:
            with winreg.OpenKey(hive, _RUN_KEY_PATH) as key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                    except OSError:
                        break
                    entries.append({"quelle": hive_name, "name": name, "befehl": value})
                    i += 1
        except OSError as e:
            errors.append(f"{hive_name}: {e}")
    return entries, errors


def _collect_startup_folder_autostart() -> tuple[list[dict], list[str]]:
    entries: list[dict] = []
    errors: list[str] = []
    for env_var, quelle in _STARTUP_FOLDER_SOURCES:
        base = os.environ.get(env_var)
        if not base:
            errors.append(f"{quelle}: Umgebungsvariable {env_var} nicht gesetzt")
            continue
        folder = Path(base).joinpath(*_STARTUP_FOLDER_SUFFIX)
        try:
            for item in folder.iterdir():
                # Nur Dateien (v0.7 Phase 3, ADR-022): Windows startet ohnehin
                # keine Unterordner-Inhalte direkt aus dem Startup-Ordner -
                # ohne diesen Filter wuerde der neue, Jarvis-eigene
                # _jarvis_disabled-Unterordner faelschlich als Autostart-
                # Eintrag auftauchen.
                if item.is_file():
                    entries.append({"quelle": quelle, "name": item.name})
        except OSError as e:
            errors.append(f"{quelle}: {e}")
    return entries, errors


def _format_report_data(data: dict) -> str:
    lines = ["[Festplatten]"]
    for d in data["disks"]:
        lines.append(
            f"{d['laufwerk']}: {d['belegt_gb']} GB von {d['gesamt_gb']} GB belegt "
            f"({d['prozent']} %), {d['frei_gb']} GB frei"
        )

    lines.append("[Top Prozesse nach CPU]")
    for p in data["top_cpu"]:
        lines.append(f"{p['name']} (PID {p['pid']}): {p['cpu_percent']:.1f} % CPU")

    lines.append("[Top Prozesse nach RAM]")
    for p in data["top_ram"]:
        lines.append(f"{p['name']} (PID {p['pid']}): {p['ram_bytes'] / (1024 ** 2):.0f} MB RAM")

    if data["duplicate_processes"]:
        lines.append("[Mehrfach laufende Prozesse]")
        for d in data["duplicate_processes"]:
            lines.append(f"{d['name']}: {d['anzahl']}x")
    else:
        lines.append("[Mehrfach laufende Prozesse] keine")

    lines.append(f"[Autostart] {len(data['autostart'])} Eintraege")
    for a in data["autostart"]:
        lines.append(f"{a['quelle']}: {a['name']}")
    if data["autostart_errors"]:
        lines.append("[Autostart - nicht lesbare Quellen] " + "; ".join(data["autostart_errors"]))

    return "\n".join(lines)


class AnalyzePcCommand:
    name = "analyze_pc"
    description = (
        "Erstellt einen PC-Gesundheitsbericht (Festplattenbelegung, Top-"
        "Prozesse nach CPU/RAM, mehrfach laufende Prozesse, Autostart-"
        "Programme) - nur Lesen, Sicherheitsstufe 0. Kein target/parameters "
        "nötig."
    )
    # Reine Leseaktion (Sicherheitsstufe 0) - keine Bestaetigung noetig,
    # kein Schreibzugriff irgendeiner Art.
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        if platform.system() != "Windows" or winreg is None:
            return Result(
                status=Status.FAILED,
                message="PC-Analyse ist aktuell nur unter Windows verfügbar.",
            )

        try:
            disks = _collect_disk_usage()
            top_cpu, top_ram, duplicates = _collect_process_data()
        except Exception as e:
            return Result(status=Status.FAILED, message=f"PC-Analyse fehlgeschlagen: {e}")

        registry_autostart, registry_errors = _collect_registry_autostart()
        folder_autostart, folder_errors = _collect_startup_folder_autostart()

        data = {
            "disks": disks,
            "top_cpu": top_cpu,
            "top_ram": top_ram,
            "duplicate_processes": duplicates,
            "autostart": registry_autostart + folder_autostart,
            "autostart_errors": registry_errors + folder_errors,
        }

        prompt = _ANALYSIS_PROMPT_TEMPLATE.format(data=_format_report_data(data))
        analysis = _require_ai_engine().answer(prompt, history=[])

        message = f"{analysis}\n\n{_DISCLAIMER}"
        return Result(status=Status.SUCCESS, message=message, data=data)


def _query_event_log(log_name: str) -> str:
    """Ruft wevtutil fuer ein einzelnes Log auf. Wirft bei Fehlern
    (Aufrufer faengt gezielt ab, siehe _collect_event_log)."""
    proc = subprocess.run(
        [
            "wevtutil", "qe", log_name,
            f"/q:{_EVENT_LEVEL_XPATH}",
            f"/c:{_MAX_EVENTS_PER_LOG}",
            "/rd:true",
            "/f:RenderedXml",
        ],
        capture_output=True,
        text=True,
        timeout=_EVENT_QUERY_TIMEOUT,
        check=True,
    )
    return proc.stdout


def _parse_event_log_xml(raw_xml: str, log_name: str) -> list[dict]:
    """wevtutil /f:RenderedXml liefert mehrere <Event>-Wurzelelemente ohne
    gemeinsame Klammer - vor dem Parsen in ein synthetisches Wurzelelement
    huellen. Tag-Namen sind sprachunabhaengig, nur Textinhalte (z. B.
    Level) sind lokalisiert (siehe ADR-021)."""
    if not raw_xml.strip():
        return []

    ns = _EVENT_XML_NS
    root = ET.fromstring(f"<Events>{raw_xml}</Events>")
    entries = []
    for event in root.findall(f"{ns}Event"):
        system = event.find(f"{ns}System")
        rendering = event.find(f"{ns}RenderingInfo")

        time_el = system.find(f"{ns}TimeCreated") if system is not None else None
        provider_el = system.find(f"{ns}Provider") if system is not None else None
        event_id_el = system.find(f"{ns}EventID") if system is not None else None
        level_el = rendering.find(f"{ns}Level") if rendering is not None else None
        message_el = rendering.find(f"{ns}Message") if rendering is not None else None

        message = (message_el.text or "").strip() if message_el is not None else ""
        entries.append(
            {
                "log": log_name,
                "zeit": time_el.get("SystemTime") if time_el is not None else "?",
                "quelle": provider_el.get("Name") if provider_el is not None else "?",
                "event_id": event_id_el.text if event_id_el is not None else "?",
                "stufe": level_el.text if level_el is not None else "?",
                "meldung": message[:_MESSAGE_TRUNCATE_LENGTH],
            }
        )
    return entries


def _collect_event_log(log_name: str) -> tuple[list[dict], Optional[str]]:
    """Liefert (Eintraege, Fehlertext-oder-None). Ein Fehlschlag bei
    diesem Log ist kein Totalausfall - gleiches Prinzip wie bei den vier
    Autostart-Quellen in ADR-020."""
    try:
        raw_xml = _query_event_log(log_name)
    except FileNotFoundError:
        return [], f"{log_name}: wevtutil nicht gefunden"
    except subprocess.TimeoutExpired:
        return [], f"{log_name}: Zeitüberschreitung bei der Abfrage"
    except subprocess.CalledProcessError as e:
        detail = e.stderr.strip() if e.stderr else str(e)
        return [], f"{log_name}: {detail}"

    try:
        return _parse_event_log_xml(raw_xml, log_name), None
    except ET.ParseError as e:
        return [], f"{log_name}: Antwort konnte nicht gelesen werden ({e})"


def _format_event_log_report_data(data: dict) -> str:
    lines = []
    for log_name in _EVENT_LOG_NAMES:
        entries = data["events"].get(log_name, [])
        lines.append(f"[{log_name}] {len(entries)} Eintraege")
        for e in entries:
            lines.append(
                f"{e['zeit']} | Stufe {e['stufe']} | {e['quelle']} (ID {e['event_id']}): {e['meldung']}"
            )
    if data["errors"]:
        lines.append("[Ereignisprotokoll - nicht lesbare Quellen] " + "; ".join(data["errors"]))
    return "\n".join(lines)


class AnalyzeEventLogCommand:
    name = "analyze_event_log"
    description = (
        "Analysiert die jüngsten Fehler/Warnungen im Windows-"
        "Ereignisprotokoll (System und Application) - nur Lesen, "
        "Sicherheitsstufe 0. Kein target/parameters nötig."
    )
    # Reine Leseaktion (Sicherheitsstufe 0) - keine Bestaetigung noetig,
    # kein Schreibzugriff irgendeiner Art.
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        if platform.system() != "Windows":
            return Result(
                status=Status.FAILED,
                message="Ereignisprotokoll-Analyse ist aktuell nur unter Windows verfügbar.",
            )

        events: dict[str, list[dict]] = {}
        errors: list[str] = []
        for log_name in _EVENT_LOG_NAMES:
            entries, error = _collect_event_log(log_name)
            events[log_name] = entries
            if error:
                errors.append(error)

        if errors and not any(events[log_name] for log_name in _EVENT_LOG_NAMES):
            return Result(
                status=Status.FAILED,
                message="Ereignisprotokoll konnte nicht gelesen werden: " + "; ".join(errors),
            )

        data = {"events": events, "errors": errors}
        prompt = _EVENT_LOG_PROMPT_TEMPLATE.format(data=_format_event_log_report_data(data))
        analysis = _require_ai_engine().answer(prompt, history=[])

        message = f"{analysis}\n\n{_DISCLAIMER}"
        return Result(status=Status.SUCCESS, message=message, data=data)


def _user_startup_folder() -> Optional[Path]:
    env_var, _quelle = _STARTUP_FOLDER_SOURCES[0]  # ("APPDATA", "Startup (Benutzer)")
    base = os.environ.get(env_var)
    if base is None:
        return None
    return Path(base).joinpath(*_STARTUP_FOLDER_SUFFIX)


def _matches(entries: list[dict], name: str) -> list[dict]:
    name_lower = name.lower()
    return [e for e in entries if name_lower in e["name"].lower()]


def _find_live_hkcu_run_matches(name: str) -> list[dict]:
    entries, _errors = _collect_registry_autostart()
    return _matches([e for e in entries if e["quelle"] == "HKCU"], name)


def _find_live_user_startup_matches(name: str) -> list[dict]:
    entries, _errors = _collect_startup_folder_autostart()
    return _matches([e for e in entries if e["quelle"] == "Startup (Benutzer)"], name)


def _find_out_of_scope_matches(name: str) -> list[dict]:
    """HKLM- bzw. Alle-Benutzer-Treffer - fuer eine praezise Fehlermeldung
    ('gefunden, aber nicht aenderbar') statt einer irrefuehrenden
    'nicht gefunden'-Meldung (Kap. 11, ADR-022)."""
    reg_entries, _e1 = _collect_registry_autostart()
    folder_entries, _e2 = _collect_startup_folder_autostart()
    out_of_scope = _matches([e for e in reg_entries if e["quelle"] == "HKLM"], name)
    out_of_scope += _matches(
        [e for e in folder_entries if e["quelle"] == "Startup (Alle Benutzer)"], name
    )
    return out_of_scope


def _find_disabled_registry_matches(name: str) -> list[dict]:
    entries: list[dict] = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _JARVIS_DISABLED_REGISTRY_PATH) as key:
            i = 0
            while True:
                try:
                    value_name, value, _type = winreg.EnumValue(key, i)
                except OSError:
                    break
                entries.append({"quelle": "HKCU Run-Key (deaktiviert)", "name": value_name, "befehl": value})
                i += 1
    except OSError:
        pass  # Zweig existiert noch nicht - keine Treffer, kein Fehler.
    return _matches(entries, name)


def _find_disabled_startup_matches(name: str) -> list[dict]:
    folder = _user_startup_folder()
    if folder is None:
        return []
    disabled_folder = folder / _STARTUP_DISABLED_SUBFOLDER_NAME
    entries: list[dict] = []
    try:
        for item in disabled_folder.iterdir():
            if item.is_file():
                entries.append({"quelle": "Startup (Benutzer, deaktiviert)", "name": item.name})
    except OSError:
        pass  # Ordner existiert noch nicht - keine Treffer, kein Fehler.
    return _matches(entries, name)


def _disable_registry_entry(name: str, value: str) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _JARVIS_DISABLED_REGISTRY_PATH) as disabled_key:
        winreg.SetValueEx(disabled_key, name, 0, winreg.REG_SZ, value)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as run_key:
        winreg.DeleteValue(run_key, name)


def _enable_registry_entry(name: str, value: str) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as run_key:
        winreg.SetValueEx(run_key, name, 0, winreg.REG_SZ, value)
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _JARVIS_DISABLED_REGISTRY_PATH, 0, winreg.KEY_SET_VALUE
    ) as disabled_key:
        winreg.DeleteValue(disabled_key, name)


def _disable_startup_entry(filename: str) -> None:
    folder = _user_startup_folder()
    if folder is None:
        raise OSError("APPDATA nicht gesetzt")
    disabled_folder = folder / _STARTUP_DISABLED_SUBFOLDER_NAME
    disabled_folder.mkdir(parents=True, exist_ok=True)
    (folder / filename).rename(disabled_folder / filename)


def _enable_startup_entry(filename: str) -> None:
    folder = _user_startup_folder()
    if folder is None:
        raise OSError("APPDATA nicht gesetzt")
    disabled_folder = folder / _STARTUP_DISABLED_SUBFOLDER_NAME
    (disabled_folder / filename).rename(folder / filename)


def _candidate_list_text(matches: list[dict]) -> str:
    return ", ".join(f"{m['quelle']}: {m['name']}" for m in matches)


# Fester Eintragsname fuer den Jarvis-eigenen Autostart (ADR-028) - taucht
# dadurch auch in analyze_pc/system_status' Autostart-Uebersicht auf, da
# diese den HKCU-Run-Key ohnehin generisch auslesen.
_JARVIS_AUTOSTART_NAME = "Jarvis"


def _pythonw_executable() -> Path:
    """Liefert pythonw.exe (kein Konsolenfenster) neben dem aktuell
    laufenden Interpreter, falls vorhanden - sonst Fallback auf
    sys.executable (python.exe, sichtbares Fenster). ADR-028: ein
    versehentlich geschlossenes Konsolenfenster wuerde sonst den
    gesamten Runtime-Prozess inkl. Telegram-Kanal beenden."""
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return candidate if candidate.exists() else Path(sys.executable)


def _jarvis_autostart_value() -> tuple[str, bool]:
    """Liefert (Registry-Wert, pythonw_gefunden) fuer den Jarvis-eigenen
    Autostart-Eintrag (ADR-028)."""
    python_path = _pythonw_executable()
    runtime_path = BASE_DIR / "jarvis_runtime.py"
    return f'"{python_path}" "{runtime_path}"', python_path.name == "pythonw.exe"


class EnableJarvisAutostartCommand:
    name = "enable_jarvis_autostart"
    description = (
        "Registriert Jarvis (jarvis_runtime.py) als Windows-Autostart-"
        "Eintrag (HKCU Run-Key, fester Name 'Jarvis') - startet ab der "
        "naechsten Windows-Anmeldung automatisch. Sicherheitsstufe 2, "
        "Bestätigung erforderlich. Erneutes Ausführen aktualisiert einen "
        "bestehenden Eintrag (z. B. nach einem Projekt-Umzug)."
    )
    requires_confirmation = True

    def execute(self, plan: Plan) -> Result:
        if platform.system() != "Windows" or winreg is None:
            return Result(
                status=Status.FAILED,
                message="Autostart-Verwaltung ist aktuell nur unter Windows verfügbar.",
            )

        value, used_pythonw = _jarvis_autostart_value()
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE
            ) as run_key:
                winreg.SetValueEx(run_key, _JARVIS_AUTOSTART_NAME, 0, winreg.REG_SZ, value)
        except OSError as e:
            return Result(
                status=Status.FAILED, message=f"Jarvis-Eigenstart konnte nicht aktiviert werden: {e}"
            )

        message = "Jarvis-Eigenstart wurde aktiviert - startet ab der nächsten Windows-Anmeldung automatisch."
        if not used_pythonw:
            message += (
                " Hinweis: pythonw.exe wurde nicht gefunden, Jarvis startet deshalb mit "
                "sichtbarem Konsolenfenster."
            )
        return Result(status=Status.SUCCESS, message=message)


class DisableJarvisAutostartCommand:
    name = "disable_jarvis_autostart"
    description = (
        "Entfernt den Jarvis-eigenen Windows-Autostart-Eintrag (HKCU "
        "Run-Key, fester Name 'Jarvis') wieder. Sicherheitsstufe 2, "
        "Bestätigung erforderlich."
    )
    requires_confirmation = True

    def execute(self, plan: Plan) -> Result:
        if platform.system() != "Windows" or winreg is None:
            return Result(
                status=Status.FAILED,
                message="Autostart-Verwaltung ist aktuell nur unter Windows verfügbar.",
            )

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE
            ) as run_key:
                winreg.DeleteValue(run_key, _JARVIS_AUTOSTART_NAME)
        except FileNotFoundError:
            return Result(status=Status.FAILED, message="Jarvis-Eigenstart ist aktuell nicht aktiviert.")
        except OSError as e:
            return Result(
                status=Status.FAILED, message=f"Jarvis-Eigenstart konnte nicht deaktiviert werden: {e}"
            )

        return Result(status=Status.SUCCESS, message="Jarvis-Eigenstart wurde deaktiviert.")


class DisableAutostartEntryCommand:
    name = "disable_autostart_entry"
    description = (
        "Deaktiviert einen Autostart-Eintrag anhand des Namens - nur HKCU "
        "Run-Key und Startup-Ordner (Benutzer), kein HKLM, keine "
        "Administratorrechte. Sicherheitsstufe 2, Bestätigung erforderlich. "
        "target = Name des Eintrags."
    )
    # Systemänderung (Sicherheitsstufe 2, Kap. 10) - einfaches Ja/Nein reicht,
    # kein confirmation_phrase (das waere Stufe 3, siehe ShutdownPcCommand).
    requires_confirmation = True

    def execute(self, plan: Plan) -> Result:
        if platform.system() != "Windows" or winreg is None:
            return Result(
                status=Status.FAILED,
                message="Autostart-Verwaltung ist aktuell nur unter Windows verfügbar.",
            )

        name = (plan.target or "").strip()
        if not name:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Welchen Autostart-Eintrag soll ich deaktivieren?",
            )

        live_matches = _find_live_hkcu_run_matches(name) + _find_live_user_startup_matches(name)

        if len(live_matches) > 1:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message=f"Ich habe mehrere Treffer für '{name}': {_candidate_list_text(live_matches)}. Welchen meinst du genau?",
            )

        if len(live_matches) == 1:
            match = live_matches[0]
            try:
                if match["quelle"] == "HKCU":
                    _disable_registry_entry(match["name"], match["befehl"])
                else:
                    _disable_startup_entry(match["name"])
            except OSError as e:
                return Result(status=Status.FAILED, message=f"Deaktivieren fehlgeschlagen: {e}")
            return Result(
                status=Status.SUCCESS,
                message=(
                    f"'{match['name']}' ({match['quelle']}) wurde im Autostart deaktiviert. "
                    f"Sag 'aktiviere {match['name']} wieder', um es zurückzusetzen."
                ),
            )

        # Kein aktiver Treffer - bereits deaktiviert, ausserhalb des Scopes,
        # oder gar nicht vorhanden? Reihenfolge wichtig fuer eine praezise
        # Meldung statt zu raten (Kap. 11).
        disabled_matches = _find_disabled_registry_matches(name) + _find_disabled_startup_matches(name)
        if len(disabled_matches) > 1:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message=(
                    f"Mehrere Treffer für '{name}' (bereits deaktiviert): "
                    f"{_candidate_list_text(disabled_matches)}. Bitte genauer angeben."
                ),
            )
        if len(disabled_matches) == 1:
            return Result(status=Status.SUCCESS, message=f"'{disabled_matches[0]['name']}' ist bereits deaktiviert.")

        out_of_scope = _find_out_of_scope_matches(name)
        if out_of_scope:
            return Result(
                status=Status.FAILED,
                message=(
                    f"'{name}' gefunden ({_candidate_list_text(out_of_scope)}), liegt aber außerhalb "
                    f"des änderbaren Bereichs (nur HKCU Run-Key und Startup-Ordner Benutzer)."
                ),
            )

        return Result(status=Status.FAILED, message=f"Kein Autostart-Eintrag mit dem Namen '{name}' gefunden.")


class EnableAutostartEntryCommand:
    name = "enable_autostart_entry"
    description = (
        "Aktiviert einen zuvor von Jarvis deaktivierten Autostart-Eintrag "
        "wieder - nur HKCU Run-Key und Startup-Ordner (Benutzer). "
        "Sicherheitsstufe 2, Bestätigung erforderlich. target = Name des "
        "Eintrags."
    )
    requires_confirmation = True

    def execute(self, plan: Plan) -> Result:
        if platform.system() != "Windows" or winreg is None:
            return Result(
                status=Status.FAILED,
                message="Autostart-Verwaltung ist aktuell nur unter Windows verfügbar.",
            )

        name = (plan.target or "").strip()
        if not name:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Welchen Autostart-Eintrag soll ich wieder aktivieren?",
            )

        disabled_matches = _find_disabled_registry_matches(name) + _find_disabled_startup_matches(name)

        if len(disabled_matches) > 1:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message=(
                    f"Mehrere deaktivierte Treffer für '{name}': "
                    f"{_candidate_list_text(disabled_matches)}. Bitte genauer angeben."
                ),
            )

        if len(disabled_matches) == 1:
            match = disabled_matches[0]
            try:
                if match["quelle"] == "HKCU Run-Key (deaktiviert)":
                    _enable_registry_entry(match["name"], match["befehl"])
                else:
                    _enable_startup_entry(match["name"])
            except OSError as e:
                return Result(status=Status.FAILED, message=f"Aktivieren fehlgeschlagen: {e}")
            return Result(status=Status.SUCCESS, message=f"'{match['name']}' wurde im Autostart wieder aktiviert.")

        live_matches = _find_live_hkcu_run_matches(name) + _find_live_user_startup_matches(name)
        if len(live_matches) > 1:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message=(
                    f"Mehrere Treffer für '{name}' (bereits aktiv): "
                    f"{_candidate_list_text(live_matches)}. Bitte genauer angeben."
                ),
            )
        if len(live_matches) == 1:
            return Result(status=Status.SUCCESS, message=f"'{live_matches[0]['name']}' ist bereits aktiv.")

        return Result(
            status=Status.FAILED,
            message=f"Kein von Jarvis deaktivierter Autostart-Eintrag mit dem Namen '{name}' gefunden.",
        )


def _scan_eligible_temp_files() -> tuple[list[Path], int, list[str]]:
    """Scannt %TEMP% rekursiv nach Dateien, die aelter als
    _TEMP_FILE_MIN_AGE_HOURS sind (v0.7 Phase 4, ADR-023). Liefert
    (Dateien, Gesamtgroesse in Bytes, Fehlertexte pro uebersprungener
    Datei). Wird von analyze_temp_files, CleanTempFilesCommand.preview()
    UND execute() unabhaengig aufgerufen - execute() verlaesst sich nie
    auf das Ergebnis eines frueheren Aufrufs (Product-Owner-Vorgabe,
    ADR-023: immer frisch scannen)."""
    temp_dir = os.environ.get("TEMP") or os.environ.get("TMP")
    if not temp_dir:
        raise OSError("TEMP-/TMP-Umgebungsvariable nicht gesetzt")
    base = Path(temp_dir).resolve()
    cutoff = time.time() - _TEMP_FILE_MIN_AGE_HOURS * 3600

    files: list[Path] = []
    total_size = 0
    errors: list[str] = []
    for item in base.rglob("*"):
        try:
            if not item.is_file():
                continue
            resolved = item.resolve()
            # Pfad-Eindaemmung: nur Dateien tatsaechlich innerhalb von
            # %TEMP% anfassen (Schutz gegen Symlinks/Junctions, die nach
            # aussen zeigen), ADR-023.
            if not resolved.is_relative_to(base):
                continue
            if item.stat().st_mtime > cutoff:
                continue
            size = item.stat().st_size
        except OSError as e:
            errors.append(f"{item}: {e}")
            continue
        files.append(item)
        total_size += size

    return files, total_size, errors


def _format_temp_summary(count: int, total_bytes: int) -> str:
    return f"{count} Datei(en) mit insgesamt {_format_gb(total_bytes)}"


class AnalyzeTempFilesCommand:
    name = "analyze_temp_files"
    description = (
        "Zeigt an, wie viele Temp-Dateien (älter als 24h) im Benutzer-"
        "Temp-Ordner liegen und wie viel Platz sie belegen - nur Lesen, "
        "Sicherheitsstufe 0. Kein target/parameters nötig."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        if platform.system() != "Windows":
            return Result(
                status=Status.FAILED,
                message="Temp-Analyse ist aktuell nur unter Windows verfügbar.",
            )

        try:
            files, total_size, errors = _scan_eligible_temp_files()
        except OSError as e:
            return Result(status=Status.FAILED, message=f"Temp-Ordner konnte nicht gelesen werden: {e}")

        message = (
            f"Im Temp-Ordner liegen {_format_temp_summary(len(files), total_size)}, "
            f"die älter als {_TEMP_FILE_MIN_AGE_HOURS}h sind."
        )
        if errors:
            message += f" ({len(errors)} Datei(en) konnten nicht geprüft werden.)"

        return Result(
            status=Status.SUCCESS,
            message=message,
            data={"count": len(files), "total_bytes": total_size, "errors": errors},
        )


class CleanTempFilesCommand:
    name = "clean_temp_files"
    description = (
        "Löscht Temp-Dateien (älter als 24h) im Benutzer-Temp-Ordner "
        "unwiderruflich - Sicherheitsstufe 3, exakte Bestätigungsphrase "
        "erforderlich. Kein target/parameters nötig."
    )
    # Datei loeschen = Sicherheitsstufe 3 laut Handbook Kap. 10 ("kritisch",
    # mehrfache Bestaetigung) - anders als das reversible Deaktivieren in
    # Phase 3 (Stufe 2), ADR-023.
    requires_confirmation = True
    confirmation_phrase = _CLEAN_TEMP_CONFIRMATION_PHRASE

    def preview(self, plan: Plan) -> Optional[str]:
        """Optionaler Executor-Hook (ADR-023): frischer Scan fuer die
        Vorschau VOR der Bestaetigung. execute() verlaesst sich NICHT auf
        dieses Ergebnis, sondern scannt beim tatsaechlichen Loeschen
        erneut - der Zustand kann sich zwischen Vorschau und Bestaetigung
        geaendert haben."""
        if platform.system() != "Windows":
            return None
        try:
            files, total_size, _errors = _scan_eligible_temp_files()
        except OSError:
            return None
        return f"Ich würde {_format_temp_summary(len(files), total_size)} löschen."

    def execute(self, plan: Plan) -> Result:
        if platform.system() != "Windows":
            return Result(
                status=Status.FAILED,
                message="Temp-Bereinigung ist aktuell nur unter Windows verfügbar.",
            )

        try:
            files, _total_size, scan_errors = _scan_eligible_temp_files()
        except OSError as e:
            return Result(status=Status.FAILED, message=f"Temp-Ordner konnte nicht gelesen werden: {e}")

        deleted_count = 0
        deleted_bytes = 0
        skipped: list[str] = list(scan_errors)
        for file_path in files:
            try:
                size = file_path.stat().st_size
                file_path.unlink()
            except OSError as e:
                skipped.append(f"{file_path}: {e}")
                continue
            deleted_count += 1
            deleted_bytes += size

        message = f"{_format_temp_summary(deleted_count, deleted_bytes)} gelöscht."
        if skipped:
            message += f" {len(skipped)} Datei(en) konnten nicht gelöscht werden."

        return Result(
            status=Status.SUCCESS,
            message=message,
            data={"deleted_count": deleted_count, "deleted_bytes": deleted_bytes, "skipped": skipped},
        )


# Registrierungspunkt für dieses Modul - commands/__init__.py liest
# diese Liste beim Start ein.
COMMANDS = [
    SystemStatusCommand(),
    AnalyzePcCommand(),
    AnalyzeEventLogCommand(),
    DisableAutostartEntryCommand(),
    EnableAutostartEntryCommand(),
    AnalyzeTempFilesCommand(),
    CleanTempFilesCommand(),
    EnableJarvisAutostartCommand(),
    DisableJarvisAutostartCommand(),
]
