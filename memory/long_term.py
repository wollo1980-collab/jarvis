"""
Langzeitgedächtnis (v0.4, ADR-009) - getrennt vom Gesprächsverlauf in
memory/store.py::JsonMemoryStore (das bleibt reines Kurzzeitgedächtnis:
letzte N Nachrichten, siehe Handbook Kap. 9).

Hier landen nur Fakten, die Wolfgang Jarvis EXPLIZIT aufträgt sich zu
merken ("Merk dir, dass..."). Bewusst KEINE automatische Extraktion
aus Gesprächen (siehe ADR-009) - das wäre ein zusätzlicher KI-Aufruf
mit Kosten und dem Risiko, falsche oder ungewollt private Dinge zu
speichern, ohne dass Wolfgang das aktiv wollte.

Drei Kategorien laut Handbook (Kap. 3: "Langzeitgedächtnis besitzt:
Projekte, Gewohnheiten, Präferenzen") plus "allgemein" als Fallback,
falls die KI keine eindeutig passende Kategorie erkennt.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.fileio import read_json, write_json_atomic
from core.redaction import redact

logger = logging.getLogger("jarvis.memory.long_term")

VALID_CATEGORIES = {"projekt", "gewohnheit", "praeferenz", "allgemein"}
DEFAULT_CATEGORY = "allgemein"


@dataclass
class Fact:
    text: str
    category: str = DEFAULT_CATEGORY
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "category": self.category, "created_at": self.created_at}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Fact":
        return cls(
            text=data["text"],
            category=data.get("category", DEFAULT_CATEGORY),
            created_at=data.get("created_at", ""),
        )


class LongTermMemory:
    def __init__(self, memory_dir: Path):
        self.path = Path(memory_dir) / "long_term.json"
        if not self.path.exists():
            self._write([])

    def remember(self, text: str, category: str = DEFAULT_CATEGORY) -> Fact:
        """Speichert einen neuen Fakt dauerhaft. Ungültige Kategorien
        fallen bewusst auf 'allgemein' zurück statt einen Fehler zu
        werfen - eine falsch klassifizierte KI-Antwort soll den Fakt
        nicht verwerfen, nur die Kategorie verwässern."""
        if category not in VALID_CATEGORIES:
            logger.info("Unbekannte Kategorie '%s' - falle zurück auf '%s'.", category, DEFAULT_CATEGORY)
            category = DEFAULT_CATEGORY

        # Auto-Redaction (ADR-040): Secrets nie im Klartext auf Platte. Das
        # Echo des Commands zeigt den geschwaerzten Text - der Nutzer SIEHT,
        # dass geschwaerzt wurde.
        fact = Fact(text=redact(text), category=category)
        facts = self._read()
        facts.append(fact.to_dict())
        self._write(facts)
        logger.info("Neuer Fakt gemerkt (%s): %s", category, text)
        return fact

    def forget(self, text: str) -> bool:
        """Entfernt den ersten Fakt, dessen Text den gesuchten Text
        (case-insensitive, als Teilstring) enthält. Gibt True zurück,
        wenn etwas gelöscht wurde, sonst False - der aufrufende
        Command entscheidet, wie das dem Nutzer gemeldet wird."""
        facts = self._read()
        needle = text.strip().lower()
        for i, f in enumerate(facts):
            if needle and needle in f["text"].lower():
                removed = facts.pop(i)
                self._write(facts)
                logger.info("Fakt vergessen: %s", removed["text"])
                return True
        return False

    def all_facts(self) -> list[Fact]:
        return [Fact.from_dict(f) for f in self._read()]

    def summary_text(self, max_facts: int = 30) -> str:
        """Kompakte Textform für den Chat-System-Prompt (core/ai.py).
        Begrenzt auf max_facts (neueste zuerst im Prompt irrelevant,
        Reihenfolge ist chronologisch) - dieselbe Kosten-/Qualitäts-
        Abwägung wie beim Gesprächsverlauf-Limit."""
        facts = self.all_facts()[-max_facts:]
        if not facts:
            return ""
        return "\n".join(f"- ({f.category}) {f.text}" for f in facts)

    def _read(self) -> list[dict[str, Any]]:
        # Kaputtes JSON wird bewahrt statt still verworfen (Audit-Fix P2b).
        return read_json(self.path, [])

    def _write(self, data: list[dict[str, Any]]) -> None:
        # Atomar schreiben - ein Crash darf das Langzeitgedaechtnis nicht
        # still loeschen (Audit-Fix P2b).
        write_json_atomic(self.path, data)
