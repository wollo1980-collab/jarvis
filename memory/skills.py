"""
Skill-Bibliothek (Plan A1, 13.07.2026) - „von Einweg-Bau zu kompound".

Von Jarvis gebaute Projekte werden als benannte, wiederverwendbare FAEHIGKEITEN
registriert. So kann Jarvis (a) auflisten, was er schon gebaut hat, und (b) VOR
einem neuen Bau pruefen, ob es das schon gibt (statt blind neu zu bauen). Reiner
Metadaten-Speicher - das AUSFUEHREN eines Skills (Plan A2) ist Code-Ausfuehrung
ausserhalb des Kaefigs und kommt erst mit S4b (gated).

File-backed (memory_dir/skills.json); mehrere Instanzen auf demselben Pfad sind
konsistent. Fail-safe.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Callable, Optional

from core.embeddings import cosine
from core.fileio import read_json, write_json_atomic

logger = logging.getLogger("jarvis.skills")


class SkillLibrary:
    def __init__(self, path):
        self._path = Path(path)

    def _read(self) -> list[dict]:
        data = read_json(self._path, [])
        return data if isinstance(data, list) else []

    def all(self) -> list[dict]:
        return self._read()

    def names(self) -> list[str]:
        return [s.get("name", "") for s in self._read() if s.get("name")]

    def get(self, name: str) -> Optional[dict]:
        needle = (name or "").strip().lower()
        return next((s for s in self._read() if s.get("name", "").lower() == needle), None)

    def add(self, name: str, description: str, path) -> dict:
        """Registriert (oder aktualisiert) einen Skill. Dedup ueber den Namen -
        ein erneuter Bau desselben Namens ueberschreibt den Eintrag statt zu
        duplizieren. Leerer Name -> nichts. Fail-safe."""
        name = (name or "").strip()
        if not name:
            return {}
        entry = {
            "name": name,
            "description": (description or "").strip(),
            "path": str(path),
            "created": date.today().isoformat(),
        }
        skills = [s for s in self._read() if s.get("name", "").lower() != name.lower()]
        skills.append(entry)
        try:
            write_json_atomic(self._path, skills)
            logger.info("Skill registriert: %s", name)
        except OSError:
            logger.warning("Skill konnte nicht gespeichert werden (ignoriert): %s", name, exc_info=True)
        return entry

    def find_similar(self, query: str, embed_fn: Callable[[list[str]], list[list[float]]],
                     threshold: float = 0.78) -> Optional[dict]:
        """Der aehnlichste vorhandene Skill zu `query` (>= threshold) oder None.
        Fuer die 'schon gebaut?'-Pruefung. Fail-safe: None bei Embedding-Fehler."""
        skills = self._read()
        if not skills:
            return None
        try:
            vecs = embed_fn([query] + [f"{s.get('name','')}: {s.get('description','')}" for s in skills])
        except Exception:  # noqa: BLE001
            return None
        if len(vecs) != len(skills) + 1 or any(not v for v in vecs):
            return None
        query_vec = vecs[0]
        best, best_score = None, threshold
        for skill, vec in zip(skills, vecs[1:]):
            score = cosine(query_vec, vec)
            if score >= best_score:
                best, best_score = skill, score
        return best
