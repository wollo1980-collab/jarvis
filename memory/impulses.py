"""
Impuls-Speicher (Endsystem-Kampagne, ADR-054) - der persistente Teil des
Impuls-Kreislaufs: Jarvis' eigener Herzschlag legt PROAKTIV Hinweise ab
(Unwetter, erkannte Gewohnheit, fertige Agenten-Arbeit), die als Karte im
Dashboard erscheinen. Ein Impuls INFORMIERT oder FRAGT - er handelt nie.

Zwei eiserne Eigenschaften stecken hier im Datenlayer:
- Entprellung (dedupe): derselbe Impuls (gleicher `key`) wird nie zweimal
  offen gelegt. Der Schluessel traegt bei tagesbezogenen Impulsen das Datum
  (z. B. "weather-storm-2026-07-11"), damit morgen ein frischer Anlauf
  moeglich ist, ohne dass der heutige nachhallt.
- Nein-Liste: ein weggeklickter Impuls landet in `dismissed` - derselbe
  key kommt nicht wieder (wie beim Merk-Angebot ADR-051). "Verstanden"
  statt "nochmal fragen".

Datenmodell (impulses.json):
    {"open": [{"id","kind","key","title","detail","created"}],
     "dismissed": {"<key>": "<iso-zeit>"}}
Atomar (core/fileio), RLock wie memory/lists.py; jede Methode fail-safe -
der Kreislauf darf die Runtime NIE stoeren. Auto-Redaction (ADR-040) auf
den anzeigbaren Texten, weil ein Impuls-Detail theoretisch aus einer
Quelle mit personenbezogenen Fragmenten stammen koennte.
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.fileio import read_json, write_json_atomic
from core.redaction import redact

logger = logging.getLogger("jarvis.memory.impulses")

# Deckel gegen unbegrenztes Wachstum der Nein-Liste: die juengsten N
# Absagen genuegen (tagesbezogene Wetter-Keys altern taeglich weg;
# Gewohnheits-Keys sind wenige und bleiben lange relevant).
_MAX_DISMISSED = 500


class ImpulseStore:
    def __init__(self, memory_dir: Path):
        self.path = Path(memory_dir) / "impulses.json"
        self._lock = threading.RLock()
        with self._lock:
            if not self.path.exists():
                self._write({"open": [], "dismissed": {}})

    def add_if_new(self, kind: str, key: str, title: str, detail: str) -> bool:
        """Legt einen Impuls offen ab - ausser er ist schon offen (dedupe)
        oder wurde weggeklickt (Nein-Liste). Liefert True, wenn wirklich ein
        neuer Impuls entstanden ist. Fail-safe: jeder Fehler -> False."""
        clean_key = (key or "").strip()
        if not clean_key:
            return False
        try:
            with self._lock:
                data = self._read()
                if clean_key in data["dismissed"]:
                    return False
                if any(item.get("key") == clean_key for item in data["open"]):
                    return False
                data["open"].append({
                    "id": uuid.uuid4().hex[:12],
                    "kind": (kind or "").strip(),
                    "key": clean_key,
                    "title": redact((title or "").strip()),
                    "detail": redact((detail or "").strip()),
                    "created": datetime.now().isoformat(timespec="seconds"),
                })
                self._write(data)
            logger.info("Impuls gelegt: %s (%s)", clean_key, kind)
            return True
        except Exception:  # noqa: BLE001 - der Kreislauf stoert nie die Runtime
            logger.exception("Impuls konnte nicht abgelegt werden (%s).", clean_key)
            return False

    def list_open(self) -> list[dict[str, Any]]:
        """Offene Impulse (Kopien), juengste zuerst - fuer die Dashboard-Karten.

        Tageslage-Regel (PO-Reibung 14.07.: die 'Hitze heute'-Karte stand am
        Folgetag um 06:03 noch da - 'ich weiss ja nicht, ob das heute wieder
        gilt'): Impulse sind TAGES-Aussagen. Eintraege frueherer Tage fallen
        beim Lesen still aus `open` (NICHT nach dismissed - gilt die Lage
        weiter, darf die Engine heute einen frischen Impuls legen)."""
        try:
            today = datetime.now().date().isoformat()
            with self._lock:
                data = self._read()
                fresh = [i for i in data["open"] if str(i.get("created", ""))[:10] == today]
                if len(fresh) != len(data["open"]):
                    data["open"] = fresh
                    self._write(data)
                items = list(fresh)
        except Exception:  # noqa: BLE001
            return []
        return sorted(items, key=lambda i: str(i.get("created", "")), reverse=True)

    def count_open(self) -> int:
        """Zaehlt nur HEUTIGE offene Impulse (Live-Befund 15.07.: drei
        Alt-Karten vom 13./14. zaehlten mit und haetten den 5er-Deckel
        verstopft - neue Impulse waeren ausgeblieben). Nutzt list_open(),
        das Vergangenes dabei gleich aus der Datei raeumt."""
        return len(self.list_open())

    def dismiss(self, id_or_key: str) -> bool:
        """Klickt einen Impuls weg: aus `open` entfernen und seinen key in die
        Nein-Liste eintragen (kommt nicht wieder). Trifft per id ODER key.
        Liefert True, wenn etwas entfernt wurde."""
        needle = (id_or_key or "").strip()
        if not needle:
            return False
        try:
            with self._lock:
                data = self._read()
                match = next(
                    (i for i in data["open"] if i.get("id") == needle or i.get("key") == needle),
                    None,
                )
                if match is None:
                    return False
                data["open"] = [i for i in data["open"] if i is not match]
                data["dismissed"][match["key"]] = datetime.now().isoformat(timespec="seconds")
                self._prune_dismissed(data)
                self._write(data)
            logger.info("Impuls weggeklickt: %s", match["key"])
            return True
        except Exception:  # noqa: BLE001
            logger.exception("Impuls konnte nicht weggeklickt werden (%s).", needle)
            return False

    @staticmethod
    def _prune_dismissed(data: dict[str, Any]) -> None:
        dismissed = data.get("dismissed", {})
        if len(dismissed) <= _MAX_DISMISSED:
            return
        # Aelteste (nach Zeitstempel) abschneiden - bounded growth.
        keep = sorted(dismissed.items(), key=lambda kv: str(kv[1]), reverse=True)[:_MAX_DISMISSED]
        data["dismissed"] = dict(keep)

    def _read(self) -> dict[str, Any]:
        data = read_json(self.path, {})
        if not isinstance(data, dict):
            data = {}
        data.setdefault("open", [])
        data.setdefault("dismissed", {})
        return data

    def _write(self, data: dict[str, Any]) -> None:
        write_json_atomic(self.path, data)
