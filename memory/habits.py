"""
Gewohnheits-Statistik (ADR-053, Datengrundlage fuer Gewohnheits-Lernen
Stufe 2) - zaehlt, WELCHER Intent WANN benutzt wird (Wochentag x Stunde).

Eiserner Grundsatz (Transkript-Grundsatz wie bei activity_today): es werden
AUSSCHLIESSLICH ZAEHLWERTE erhoben - nie Nachrichteninhalte, nie Targets,
nie Parameter. Aus "get_news wurde montags um 7 Uhr dreimal benutzt" laesst
sich eine Gewohnheit VERMUTEN; was gesagt wurde, steht hier nie.

Die Vermutungs-Auswertung (suspects) ist eine reine Lese-API - die
Frage-Mechanik ("Du hoerst montags morgens oft Nachrichten - soll ich
...?") ist bewusst NICHT Teil dieser Scheibe (PO-Feintuning noetig,
siehe Gewohnheits-Vision). Erhoben wird trotzdem ab sofort: Muster
brauchen Wochen an Daten - je frueher die Zaehlung laeuft, desto eher
kann Stufe 2 ehrlich vermuten.

Datenmodell (habit_stats.json):
    {"counts": {"get_news": {"0-07": 3, ...}}, "since": "2026-07-11"}
Schluessel = "<wochentag 0-6>-<stunde 00-23>" (Mo=0). Atomar (core/fileio),
RLock; record() ist fail-safe - Statistik darf die Verarbeitung NIE stoeren.
"""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from core.fileio import read_json, write_json_atomic

logger = logging.getLogger("jarvis.memory.habits")

# Intents, die nie eine "Gewohnheit" im Sinne der Vision sind: zu generisch
# (chat) oder reiner Betrieb. Sie werden trotzdem NICHT gezaehlt - was nie
# Vermutung werden darf, muss auch nicht erhoben werden (Datenminimierung).
_IGNORED_INTENTS = {"chat", "stop_runtime", "restart_runtime", "shutdown_pc"}


class HabitStats:
    def __init__(self, memory_dir: Path):
        self.path = Path(memory_dir) / "habit_stats.json"
        self._lock = threading.RLock()

    def record(self, intent: str, when: Optional[datetime] = None) -> None:
        """Zaehlt eine Intent-Nutzung im (Wochentag, Stunde)-Fach. Fail-safe:
        jeder Fehler wird geschluckt und geloggt - die Nachricht des Nutzers
        ist wichtiger als die Statistik."""
        clean = (intent or "").strip()
        if not clean or clean in _IGNORED_INTENTS:
            return
        try:
            now = when or datetime.now()
            key = f"{now.weekday()}-{now.hour:02d}"
            with self._lock:
                data = self._read()
                bucket = data["counts"].setdefault(clean, {})
                bucket[key] = int(bucket.get(key, 0)) + 1
                self._write(data)
        except Exception:  # noqa: BLE001 - Statistik stoert nie die Pipeline
            logger.exception("Gewohnheits-Zaehlung fehlgeschlagen (%s).", clean)

    def suspects(self, min_count: int = 3) -> list[dict[str, Any]]:
        """Vermutungs-Kandidaten: (intent, wochentag, stunde) mit mindestens
        min_count Nutzungen - sortiert nach Haeufigkeit. Reine Lese-API fuer
        die spaetere Frage-Mechanik (Stufe 2); loest selbst NICHTS aus."""
        with self._lock:
            counts = self._read()["counts"]
        result = []
        for intent, buckets in counts.items():
            for key, count in buckets.items():
                if int(count) < min_count:
                    continue
                try:
                    weekday, hour = (int(p) for p in key.split("-"))
                except ValueError:
                    continue
                result.append(
                    {"intent": intent, "weekday": weekday, "hour": hour, "count": int(count)}
                )
        return sorted(result, key=lambda s: s["count"], reverse=True)

    def _read(self) -> dict[str, Any]:
        data = read_json(self.path, {})
        if not isinstance(data, dict):
            data = {}
        data.setdefault("counts", {})
        data.setdefault("since", date.today().isoformat())
        return data

    def _write(self, data: dict[str, Any]) -> None:
        write_json_atomic(self.path, data)
