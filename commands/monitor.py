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
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import psutil

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


# Registrierungspunkt für dieses Modul - commands/__init__.py liest
# diese Liste beim Start ein.
COMMANDS = [SystemStatusCommand(), AnalyzePcCommand(), AnalyzeEventLogCommand()]
