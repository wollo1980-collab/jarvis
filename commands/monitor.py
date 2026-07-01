"""
System-Ueberwachung: liest CPU- und RAM-Auslastung aus (psutil).

Sicherheitsstufe 0 (Handbook Kap. 10) - reine Leseaktion, veraendert
nichts am System, braucht deshalb keine Bestaetigung.

Temperatur (ebenfalls in Kap. 17 genannt) ist bewusst NICHT enthalten:
psutil.sensors_temperatures() ist unter Windows nicht verfuegbar (nur
Linux/macOS) - aehnliche Einschraenkung wie Kokoro TTS ohne Deutsch,
lieber ehrlich weglassen als eine falsche Erwartung wecken.
"""
from __future__ import annotations

import logging

import psutil

from core.models import Plan, Result, Status

logger = logging.getLogger("jarvis.commands.monitor")


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


# Registrierungspunkt für dieses Modul - commands/__init__.py liest
# diese Liste beim Start ein.
COMMANDS = [SystemStatusCommand()]
