"""
Bau-Reflexionen (Plan G, 13.07.2026) - der Bau-Arm lernt aus Fehlläufen.

Scheitert die Selbstprüfung eines Käfig-Baus (Gate/Tests ROT), hält Jarvis eine
kurze natürlichsprachige „warum"-Notiz je Projekt fest. Beim NÄCHSTEN Versuch in
demselben Projekt werden die jüngsten Notizen dem Auftrag mitgegeben („das ist
letztes Mal schiefgegangen - nicht wiederholen"). Das ist das Reflexion-Muster
(aus dem Deep Research) auf den Bau-Arm angewandt.

File-backed (memory_dir/build_reflections.json: {projekt: [{text, date}]}),
je Projekt gedeckelt, durchgehend fail-safe - stört den Bau nie.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from core.fileio import read_json, write_json_atomic

logger = logging.getLogger("jarvis.build_reflections")

_MAX_PER_PROJECT = 10


class BuildReflections:
    def __init__(self, memory_dir):
        self._path = Path(memory_dir) / "build_reflections.json"

    def _read(self) -> dict:
        data = read_json(self._path, {})
        return data if isinstance(data, dict) else {}

    def record(self, project: str, text: str) -> None:
        """Hält eine Fehlschlag-Notiz für ein Projekt fest (gedeckelt). Fail-safe."""
        project = (project or "").strip()
        text = (text or "").strip()
        if not project or not text:
            return
        try:
            data = self._read()
            entries = data.get(project)
            if not isinstance(entries, list):
                entries = []
            entries.append({"text": text, "date": date.today().isoformat()})
            data[project] = entries[-_MAX_PER_PROJECT:]
            write_json_atomic(self._path, data)
            logger.info("Bau-Reflexion fuer '%s' festgehalten.", project)
        except OSError:
            logger.warning("Bau-Reflexion konnte nicht gespeichert werden (ignoriert).", exc_info=True)

    def recent(self, project: str, n: int = 3) -> list[str]:
        """Die jüngsten n Notizen eines Projekts (Text). Fail-safe: []."""
        entries = self._read().get((project or "").strip(), [])
        if not isinstance(entries, list):
            return []
        return [e.get("text", "") for e in entries[-n:] if isinstance(e, dict) and e.get("text")]
