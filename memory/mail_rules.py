"""
Gelernte Absenderregeln für das Mail-Briefing (Nutzwert-Phase, ADR-031).

Der „Lern"-Anteil von „Jarvis, was liegt an?": KEIN statistisches/ML-Modell,
sondern ein kleiner, menschenlesbarer, lokaler Speicher mit ausdrücklichen
Korrekturen des Nutzers (Leitplanke 8 - Nachvollziehbarkeit). Der Nutzer sagt
„von X will ich nichts mehr" (hide) oder „das ist keine Werbung" (keep); die
explizite Regel schlägt immer die Werbung-Heuristik (core/mail_reader.py).

Konzeptuell eine Schwester des Langzeitgedächtnisses (memory/long_term.py,
ADR-009): eine JSON-Datei im memory_dir, nichts verlässt den Rechner.

Regeln sind Substring-Muster (case-insensitive), abgeglichen gegen die
vollständige From-Kopfzeile (Anzeigename + Adresse). So passt „amazon" auf
`Amazon.de <versand@amazon.de>` - der Nutzer denkt in Absendernamen, nicht in
E-Mail-Adressen.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from core.fileio import read_json, write_json_atomic

logger = logging.getLogger("jarvis.memory.mail_rules")


class MailRules:
    def __init__(self, memory_dir: Path):
        self.path = Path(memory_dir) / "mail_rules.json"
        if not self.path.exists():
            self._write({"hide": [], "keep": []})

    def hide(self, pattern: str) -> bool:
        """Absender künftig ausblenden. Aus 'keep' entfernen, falls dort.
        Gibt False bei leerem Muster zurück (nichts gemerkt)."""
        return self._add(pattern, "hide", "keep")

    def keep(self, pattern: str) -> bool:
        """Absender künftig immer zeigen (schlägt die Werbung-Heuristik)."""
        return self._add(pattern, "keep", "hide")

    def classify(self, from_header: str) -> Optional[str]:
        """'keep' | 'hide' | None. keep gewinnt vor hide (im Zweifel zeigen)."""
        haystack = (from_header or "").lower()
        data = self._read()
        for p in data.get("keep", []):
            if p and p in haystack:
                return "keep"
        for p in data.get("hide", []):
            if p and p in haystack:
                return "hide"
        return None

    def all_rules(self) -> dict[str, list[str]]:
        data = self._read()
        return {"hide": data.get("hide", []), "keep": data.get("keep", [])}

    def _add(self, pattern: str, target: str, opposite: str) -> bool:
        norm = (pattern or "").strip().lower()
        if not norm:
            return False
        data = self._read()
        data.setdefault(target, [])
        data.setdefault(opposite, [])
        if norm in data[opposite]:
            data[opposite].remove(norm)
        if norm not in data[target]:
            data[target].append(norm)
        self._write(data)
        logger.info("Mail-Regel gemerkt (%s): %s", target, norm)
        return True

    def _read(self) -> dict[str, list[str]]:
        # Kaputtes JSON wird bewahrt statt still verworfen (Audit-Fix P2b);
        # unerwarteter Typ faellt auf leere Regeln zurueck.
        data = read_json(self.path, {"hide": [], "keep": []})
        if not isinstance(data, dict):
            return {"hide": [], "keep": []}
        return data

    def _write(self, data: dict[str, list[str]]) -> None:
        # Atomar schreiben - ein Crash darf die Mail-Regeln nicht still
        # loeschen (Audit-Fix P2b).
        write_json_atomic(self.path, data)
