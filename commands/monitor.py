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
"""
from __future__ import annotations

import logging
import os
import platform
import time
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


# Registrierungspunkt für dieses Modul - commands/__init__.py liest
# diese Liste beim Start ein.
COMMANDS = [SystemStatusCommand(), AnalyzePcCommand()]
