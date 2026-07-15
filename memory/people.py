"""
Personen-Gedaechtnis (ADR-066 Stein 1) - „wer ist wer".

Ein COO kennt das Umfeld. Jarvis merkt sich Menschen, die der Nutzer erwaehnt
(Name -> Rolle/Beziehung/Notizen), und kann den passenden Personen-Kontext
hervorholen, sobald ein Name auftaucht („Meeting mit Anna", „wer ist Anna?").

Bewusst getrennt vom Fakten-Gedaechtnis (das sind Fakten ueber DICH; hier sind
Menschen in deinem Umfeld, mit Namens-Lookup). Lokal, Secrets vor Persistenz
redigiert (ADR-040). Klein und deterministisch.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from core.fileio import read_json, write_json_atomic
from core.redaction import redact

logger = logging.getLogger("jarvis.people")


class PeopleStore:
    def __init__(self, memory_dir: Path):
        self._path = Path(memory_dir) / "people.json"

    def _load(self) -> dict:
        data = read_json(self._path, {})
        return data if isinstance(data, dict) else {}

    def remember(self, name: str, note: str) -> None:
        """Legt eine Person an oder ergaenzt eine Notiz (Rolle/Beziehung).
        Idempotent: dieselbe Notiz wird nicht doppelt gespeichert."""
        name = (name or "").strip()
        note = redact((note or "").strip())
        if not name or not note:
            return
        data = self._load()
        key = name.lower()
        person = data.get(key) or {"name": name, "notes": []}
        person["name"] = name                       # juengste Schreibweise behalten
        if note not in person["notes"]:
            person["notes"].append(note)
        data[key] = person
        write_json_atomic(self._path, data)
        logger.info("Person gemerkt/ergaenzt: %s", name)

    def get(self, name: str) -> Optional[dict]:
        return self._load().get((name or "").strip().lower())

    def all(self) -> list[dict]:
        return list(self._load().values())

    def find_in_text(self, text: str) -> list[dict]:
        """Bekannte Personen, deren Name als Wort in `text` vorkommt (fuer die
        Kontext-Injektion). Deterministisch, wortgrenzen-genau."""
        low = (text or "").lower()
        if not low:
            return []
        hits: list[dict] = []
        for key, person in self._load().items():
            if not key:
                continue
            if re.search(rf"\b{re.escape(key)}\b", low):
                hits.append(person)
        return hits

    @staticmethod
    def context_block(people: list[dict]) -> str:
        """Kurzer Kontext-Block fuer den Prompt (oder '')."""
        lines = [f"- {p.get('name', '?')}: {'; '.join(p.get('notes', []))}"
                 for p in people if p.get("notes")]
        return ("Personen im Kontext:\n" + "\n".join(lines)) if lines else ""
