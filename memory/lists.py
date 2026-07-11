"""
Benannte Listen (PO-Reibung 2026-07-10 "ich haette gerne, dass ich ihm
einfach ne Einkaufsliste erzaehlen kann") - dritter Gedaechtnis-Typ neben
Eintraegen (einmalig/terminiert, memory/entries.py) und Fakten (dauerhaft
ueber den Nutzer, memory/long_term.py): eine Liste ist eine benannte
Sammlung kurzer Posten ("einkaufsliste": Milch, Butter, ...).

Loeschen ist ABSICHTLICH leichtgewichtig (PO: "das Loeschen ist im Moment
sehr umstaendlich"): clear() leert ohne Rueckfrage, legt den alten Stand
aber in den Papierkorb - restore() holt ihn zurueck. Undo statt Rueckfrage
(PIS-Prinzip): sprachtauglich, weil der Sprachkanal keine Stufe-2-
Bestaetigung geben kann (ADR-045 by design), und trotzdem nichts endgueltig
verloren geht.

Datenmodell (lists.json):
    {"lists": {"einkaufsliste": ["Milch", ...]}, "trash": {"einkaufsliste": [...]}}
Namen sind kleingeschriebene Schluessel; die Anzeige kapitalisiert.
JSON atomar (core/fileio), RLock wie memory/entries.py, Auto-Redaction
(ADR-040) auf jedem Posten.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Optional

from core.fileio import read_json, write_json_atomic
from core.redaction import redact

logger = logging.getLogger("jarvis.memory.lists")


def normalize_name(raw: str) -> str:
    """Listen-Name als Schluessel: kleingeschrieben, getrimmt."""
    return (raw or "").strip().lower()


def display_name(name: str) -> str:
    """Anzeigename: erster Buchstabe gross ('einkaufsliste' -> 'Einkaufsliste')."""
    clean = (name or "").strip()
    return clean[:1].upper() + clean[1:] if clean else clean


class ListStore:
    def __init__(self, memory_dir: Path):
        self.path = Path(memory_dir) / "lists.json"
        self._lock = threading.RLock()
        with self._lock:
            if not self.path.exists():
                self._write({"lists": {}, "trash": {}})

    def add(self, name: str, items: list[str]) -> tuple[list[str], list[str]]:
        """Haengt Posten an die Liste an (legt sie bei Bedarf an). Doppelte
        Posten (case-insensitive) werden uebersprungen - zweimal 'Milch'
        heisst beim Einkaufen einmal Milch. Liefert (neu, uebersprungen)."""
        key = normalize_name(name)
        if not key:
            raise ValueError("Listen-Name darf nicht leer sein.")
        cleaned = [redact(i.strip()) for i in items if i and i.strip()]
        added: list[str] = []
        skipped: list[str] = []
        with self._lock:
            data = self._read()
            existing = data["lists"].setdefault(key, [])
            seen = {e.lower() for e in existing}
            for item in cleaned:
                if item.lower() in seen:
                    skipped.append(item)
                    continue
                existing.append(item)
                seen.add(item.lower())
                added.append(item)
            self._write(data)
        logger.info("Liste '%s': %d Posten ergaenzt, %d uebersprungen.", key, len(added), len(skipped))
        return added, skipped

    def get(self, name: str) -> Optional[list[str]]:
        """Posten einer Liste (Kopie) oder None, wenn sie nicht existiert."""
        key = normalize_name(name)
        with self._lock:
            lists = self._read()["lists"]
            return list(lists[key]) if key in lists else None

    def overview(self) -> list[tuple[str, int]]:
        """(name, anzahl) aller existierenden Listen, alphabetisch."""
        with self._lock:
            lists = self._read()["lists"]
        return sorted((name, len(items)) for name, items in lists.items())

    def remove(self, name: Optional[str], item: str = "", index: int = 0) -> Optional[tuple[str, str]]:
        """Streicht EINEN Posten: per index (1-basiert, aus der nummerierten
        Anzeige) oder per Text (Teilstring, case-insensitive). Ohne Namen
        wird ueber alle Listen gesucht, wenn der Treffer eindeutig ist.
        Liefert (listen_name, posten) oder None."""
        key = normalize_name(name) if name else ""
        with self._lock:
            data = self._read()
            lists = data["lists"]
            candidates = [key] if key else sorted(lists)
            hits: list[tuple[str, int]] = []
            for cand in candidates:
                items = lists.get(cand, [])
                if index:
                    if 1 <= index <= len(items):
                        hits.append((cand, index - 1))
                else:
                    needle = item.strip().lower()
                    if not needle:
                        continue
                    for i, existing in enumerate(items):
                        if needle in existing.lower():
                            hits.append((cand, i))
            # Ohne Namen nur bei EINDEUTIGEM Treffer handeln - nie raten.
            if len(hits) != 1:
                return None
            cand, i = hits[0]
            removed = lists[cand].pop(i)
            if not lists[cand]:
                del lists[cand]  # leere Liste verschwindet aus der Uebersicht
            self._write(data)
        logger.info("Liste '%s': Posten gestrichen: %s", cand, removed)
        return cand, removed

    def clear(self, name: str) -> Optional[list[str]]:
        """Leert die Liste OHNE Rueckfrage, sichert den Stand im Papierkorb
        (Undo statt Rueckfrage). Liefert die geleerten Posten oder None."""
        key = normalize_name(name)
        with self._lock:
            data = self._read()
            items = data["lists"].pop(key, None)
            if items is None:
                return None
            data["trash"][key] = items
            self._write(data)
        logger.info("Liste '%s' geleert (%d Posten im Papierkorb).", key, len(items))
        return items

    def restore(self, name: str = "") -> Optional[tuple[str, list[str]]]:
        """Holt eine geleerte Liste aus dem Papierkorb zurueck (bestehende
        Posten bleiben, Papierkorb-Posten kommen dazu). Ohne Namen nur bei
        genau EINER Liste im Papierkorb. Liefert (name, posten) oder None."""
        key = normalize_name(name)
        with self._lock:
            data = self._read()
            trash = data["trash"]
            if not key:
                if len(trash) != 1:
                    return None
                key = next(iter(trash))
            items = trash.pop(key, None)
            if items is None:
                return None
            existing = data["lists"].setdefault(key, [])
            seen = {e.lower() for e in existing}
            existing.extend(i for i in items if i.lower() not in seen)
            self._write(data)
        logger.info("Liste '%s' wiederhergestellt (%d Posten).", key, len(items))
        return key, items

    def _read(self) -> dict[str, Any]:
        data = read_json(self.path, {})
        if not isinstance(data, dict):
            data = {}
        data.setdefault("lists", {})
        data.setdefault("trash", {})
        return data

    def _write(self, data: dict[str, Any]) -> None:
        write_json_atomic(self.path, data)
