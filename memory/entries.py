"""
Eintraege (A1, Welle 1 Offensiv-Fahrplan) - Erinnerungen, Aufgaben und
wichtige Merkposten in EINEM Store, getrennt vom Langzeitgedaechtnis
(memory/long_term.py = dauerhafte Fakten UEBER den Nutzer; hier = einmalige,
oft terminierte Eintraege).

Vereinheitlichtes Datenmodell (PO-Freigabe 2026-07-08):
    Eintrag = { id, text, when (ISO 8601, optional), important, created }
- Erinnerung: when in der Zukunft (feuert erst mit A2-Scheduler, ADR-039).
- Aufgabe/Notiz: kein when.
- Wichtiger Merkposten: important=true, when darf auch in der Vergangenheit
  liegen ("am 12.07.25 war das Audit in Musterstadt") - wird nie gefeuert,
  bleibt aber nachschlagbar.

Listen-Default (PO): offene/zukuenftige Eintraege + ALLE wichtigen; die
restliche Vergangenheit nur auf ausdruecklichen Filter (include_past).

JSON atomar ueber core/fileio (Audit-Fix P2b); RLock analog memory/store.py,
vorwaertskompatibel zum A2-Scheduler-Thread, der denselben Store liest.
"""
from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.fileio import read_json, write_json_atomic

logger = logging.getLogger("jarvis.memory.entries")

# Laenge eines reinen ISO-Datums ("2026-07-12") - ohne Uhrzeit gilt der
# Eintrag bis Tagesende als offen (nicht ab Mitternacht als "vergangen").
_DATE_ONLY_LEN = 10


@dataclass
class Entry:
    text: str
    when: str = ""  # ISO 8601 ("2026-07-10T09:00" / "2025-07-12") oder leer
    important: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "when": self.when,
            "important": self.important,
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Entry":
        return cls(
            text=data.get("text", ""),
            when=data.get("when", "") or "",
            important=bool(data.get("important", False)),
            id=data.get("id", ""),
            created=data.get("created", ""),
        )


def is_past(when: str) -> bool:
    """True, wenn der Zeitpunkt eindeutig in der Vergangenheit liegt.
    Reines Datum zaehlt bis Tagesende als offen; nicht parsebares when gilt
    fail-safe als offen (der Eintrag bleibt sichtbar statt still zu
    verschwinden)."""
    if not when:
        return False
    try:
        dt = datetime.fromisoformat(when)
    except ValueError:
        return False
    if len(when) == _DATE_ONLY_LEN:
        dt = dt.replace(hour=23, minute=59, second=59)
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    return dt < now


def _sort_key(entry: Entry) -> tuple:
    """Terminierte Eintraege zuerst (frueheste vorn), danach die undatierten
    in Erfassungs-Reihenfolge."""
    return (0, entry.when) if entry.when else (1, entry.created)


class EntryStore:
    def __init__(self, memory_dir: Path):
        self.path = Path(memory_dir) / "entries.json"
        self._lock = threading.RLock()
        with self._lock:
            if not self.path.exists():
                self._write([])

    def add(self, text: str, when: str = "", important: bool = False) -> Entry:
        entry = Entry(text=text.strip(), when=(when or "").strip(), important=important)
        with self._lock:
            data = self._read()
            data.append(entry.to_dict())
            self._write(data)
        logger.info(
            "Eintrag angelegt (%s%s): %s",
            "wichtig" if important else "normal",
            f", faellig {entry.when}" if entry.when else "",
            entry.text,
        )
        return entry

    def list_open(
        self,
        keyword: Optional[str] = None,
        important_only: bool = False,
        include_past: bool = False,
    ) -> list[Entry]:
        """Listet Eintraege nach dem PO-Default: offene/zukuenftige plus ALLE
        wichtigen; nicht-wichtige Vergangenheit nur mit include_past=True.
        keyword filtert case-insensitive als Teilstring im Text."""
        with self._lock:
            entries = [Entry.from_dict(d) for d in self._read()]

        needle = (keyword or "").strip().lower()
        result = []
        for e in entries:
            if needle and needle not in e.text.lower():
                continue
            if important_only and not e.important:
                continue
            if not include_past and not e.important and is_past(e.when):
                continue
            result.append(e)
        return sorted(result, key=_sort_key)

    def delete(self, id_or_text: str) -> Optional[Entry]:
        """Loescht zuerst per exakter id, sonst den ersten Eintrag, dessen
        Text den gesuchten Text enthaelt (case-insensitive). Gibt den
        entfernten Eintrag zurueck oder None - der Command entscheidet, wie
        das gemeldet wird (Muster wie LongTermMemory.forget)."""
        needle = (id_or_text or "").strip()
        if not needle:
            return None
        with self._lock:
            data = self._read()
            for i, d in enumerate(data):
                if d.get("id") == needle:
                    removed = data.pop(i)
                    self._write(data)
                    logger.info("Eintrag geloescht (per id): %s", removed.get("text"))
                    return Entry.from_dict(removed)
            lowered = needle.lower()
            for i, d in enumerate(data):
                if lowered in d.get("text", "").lower():
                    removed = data.pop(i)
                    self._write(data)
                    logger.info("Eintrag geloescht (per Text): %s", removed.get("text"))
                    return Entry.from_dict(removed)
        return None

    def _read(self) -> list[dict[str, Any]]:
        return read_json(self.path, [])

    def _write(self, data: list[dict[str, Any]]) -> None:
        write_json_atomic(self.path, data)
