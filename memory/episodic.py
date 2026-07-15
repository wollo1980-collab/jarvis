"""
Episodisches Gedaechtnis (Gedaechtnis-Kampagne, Stufe 1) - ein EINSEHBARES
Tagebuch der Ereignisse: was der Nutzer wollte, was Jarvis tat. Das Fundament
der naechtlichen Reflexion (memory/reflection.py, Stufe 2 - GEBAUT, laeuft
per Flag `reflection_enabled` in der Runtime): dort werden aus den rohen
Episoden Muster/Lehren destilliert ('dreaming'-Muster, konvergent mit
OpenClaw).

Bewusst schmal und robust:
- Append-only JSONL, EIN Datei pro Tag (memory_dir/episodes/<datum>.jsonl) -
  leicht einsehbar (dein Prinzip "sichtbares Gedaechtnis"), leicht zu prunen,
  natuerliche Einheit fuer die taegliche Reflexion.
- Secrets werden vor dem Schreiben redigiert (ADR-040, redact()) - ein
  Schluessel/Token landet nie im Klartext im Tagebuch.
- Fail-safe: ein Fehler beim Schreiben/Lesen darf den Live-Pfad NIE stoeren
  (nur WARNING, dann weiter) - ein Tagebuch ist Beiwerk, nie kritisch.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from core.redaction import redact

logger = logging.getLogger("jarvis.episodic")


class EpisodicMemory:
    def __init__(self, base_dir: Path):
        self._dir = Path(base_dir) / "episodes"

    def _file_for(self, day: date) -> Path:
        return self._dir / f"{day.isoformat()}.jsonl"

    def record(
        self,
        *,
        user_input: str,
        intents: list,
        response: str,
        source: str = "",
        ts: Optional[datetime] = None,
    ) -> None:
        """Haengt EINE Episode an das Tagebuch des heutigen Tages an. Fail-safe:
        wirft nie - ein Schreibfehler ergibt nur eine WARNING (das Tagebuch darf
        die Verarbeitung nie mitreissen). user_input/response werden redigiert,
        damit ein Secret nie im Klartext im Log steht."""
        try:
            now = ts or datetime.now()
            episode = {
                "ts": now.isoformat(timespec="seconds"),
                "source": source or "",
                "user_input": redact(user_input or ""),
                "intents": [str(i) for i in (intents or [])],
                "response": redact(response or ""),
            }
            self._dir.mkdir(parents=True, exist_ok=True)
            with self._file_for(now.date()).open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(episode, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001 - das Tagebuch stoert den Live-Pfad nie
            logger.warning("Episodisches Log: Schreiben fehlgeschlagen (ignoriert).",
                           exc_info=True)

    def for_day(self, day: date) -> list[dict]:
        """Alle Episoden eines Tages, aelteste zuerst. Fehlende Datei oder
        kaputte Zeilen -> das, was lesbar ist (nie ein Absturz)."""
        episodes: list[dict] = []
        try:
            content = self._file_for(day).read_text(encoding="utf-8")
        except OSError:
            return []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                episodes.append(json.loads(line))
            except ValueError:
                continue
        return episodes

    def recent(self, limit: int = 20) -> list[dict]:
        """Die juengsten `limit` Episoden ueber alle Tage hinweg (juengste
        zuletzt). Fuer 'was war?'-Rueckblicke. Liest die Tagesdateien in
        Datums-Reihenfolge von hinten, bis genug gesammelt ist."""
        if limit <= 0:
            return []
        collected: list[dict] = []
        try:
            files = sorted(self._dir.glob("*.jsonl"))
        except OSError:
            return []
        for path in reversed(files):
            try:
                day = date.fromisoformat(path.stem)
            except ValueError:
                continue
            day_eps = self.for_day(day)
            collected = day_eps + collected
            if len(collected) >= limit:
                break
        return collected[-limit:]
