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
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from core.fileio import read_json, write_json_atomic
from core.redaction import redact

logger = logging.getLogger("jarvis.memory.entries")

# Laenge eines reinen ISO-Datums ("2026-07-12") - ohne Uhrzeit gilt der
# Eintrag bis Tagesende als offen (nicht ab Mitternacht als "vergangen").
_DATE_ONLY_LEN = 10

# Papierkorb (Bestaetigungs-Diaet 14.07., Muster memory/long_term.py):
# Geloeschtes wandert in eine EIGENE Datei (kein Schema-Bruch fuer die
# entries.json-Leser) und bleibt wiederherstellbar.
_TRASH_CAP = 100

# Wiederholung (ADR-052): v1 bewusst nur taeglich + woechentlich. Aliase
# normalisieren die Planner-Schreibweisen; Unbekanntes wird ehrlich zu ""
# (einmalig) statt zu einer geratenen Wiederholung.
_REPEAT_ALIASES = {
    "taeglich": "taeglich", "täglich": "taeglich", "daily": "taeglich",
    "jeden tag": "taeglich",
    "woechentlich": "woechentlich", "wöchentlich": "woechentlich",
    "weekly": "woechentlich", "jede woche": "woechentlich",
}
_REPEAT_DELTAS = {"taeglich": timedelta(days=1), "woechentlich": timedelta(days=7)}


def normalize_repeat(raw: str) -> str:
    """Planner-Schreibweise -> kanonischer Wert ("" = einmalig)."""
    return _REPEAT_ALIASES.get((raw or "").strip().lower(), "")


def advance_to_next_occurrence(when: str, repeat: str) -> str:
    """Rueckt einen Zeitpunkt auf das naechste ZUKUENFTIGE Vorkommen vor
    (ADR-052). Ein langer Ausfall springt in einem Schritt ueber alle
    verpassten Vorkommen (eine Nachholung, keine Flut). Reines Datum bleibt
    reines Datum; Unparsebares kommt unveraendert zurueck (fail-safe)."""
    delta = _REPEAT_DELTAS.get(repeat)
    if delta is None or not when:
        return when
    date_only = len(when) == _DATE_ONLY_LEN
    try:
        dt = datetime.fromisoformat(when)
    except ValueError:
        return when
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    probe = dt.replace(hour=23, minute=59, second=59) if date_only else dt
    while probe <= now:
        dt += delta
        probe = dt.replace(hour=23, minute=59, second=59) if date_only else dt
    return dt.strftime("%Y-%m-%d") if date_only else dt.strftime("%Y-%m-%dT%H:%M")


@dataclass
class Entry:
    text: str
    when: str = ""  # ISO 8601 ("2026-07-10T09:00" / "2025-07-12") oder leer
    important: bool = False
    # A2 (ADR-039): True = der Scheduler hat diesen Eintrag bereits gemeldet
    # (oder es gibt nichts zu melden: kein when / bei Anlage schon vergangen).
    notified: bool = False
    # Wiederholung (ADR-052): "" = einmalig, "taeglich" | "woechentlich".
    repeat: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "when": self.when,
            "important": self.important,
            "notified": self.notified,
            "repeat": self.repeat,
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Entry":
        when = data.get("when", "") or ""
        return cls(
            text=data.get("text", ""),
            when=when,
            important=bool(data.get("important", False)),
            # Migration (A2): Eintraege aus A1 haben kein notified-Feld. Ein
            # bereits vergangenes when gilt als gemeldet - sonst wuerden alte
            # Merkposten beim ersten Scheduler-Start faelschlich nachfeuern.
            notified=bool(data.get("notified", is_past(when))),
            # Migration (ADR-052): Bestandseintraege sind einmalig.
            repeat=normalize_repeat(data.get("repeat", "")),
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


def is_due(when: str) -> bool:
    """True, wenn der Zeitpunkt erreicht/ueberschritten ist (Scheduler, A2).
    Bewusst anders als is_past: ein reines Datum ist ab MITTERNACHT faellig
    (Tages-Erinnerung kommt morgens beim ersten Tick), zaehlt fuer die
    Sichtbarkeit (is_past) aber bis Tagesende als offen."""
    if not when:
        return False
    try:
        dt = datetime.fromisoformat(when)
    except ValueError:
        return False
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    return dt <= now


_WEEKDAYS_DE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag",
                "Freitag", "Samstag", "Sonntag")


def format_when(when: str, mark_past: bool = False) -> str:
    """ISO 8601 -> natuerliches Deutsch, RELATIV wo es natuerlich klingt:
    'heute um 14:45', 'morgen um 9:00', 'am Montag um 9:00', 'gestern um 8:00';
    weiter weg absolut '12.07.2026 um 14:45'. Ganztaegig ohne Uhrzeit ('heute',
    'morgen', 'am Montag', '12.07.2026'). Nicht parsebares when kommt roh
    zurueck (fail-safe). Kein fuehrendes 'um' - Aufrufer setzen keins davor.

    mark_past=True kennzeichnet Vergangenes als 'war fällig heute um 09:00'
    (Kundenreview 13.07., 'Eine gemeinsame Wahrheit': ein 09:00-Termin darf
    abends NIRGENDS mehr wie anstehend klingen - Eintragsliste, Gedaechtnis-
    Ansicht und Antwort-Composer haengen alle an dieser einen Stelle).
    Default False: Echos beim ANLEGEN nennen nie Vergangenes."""
    try:
        dt = datetime.fromisoformat(when)
    except ValueError:
        return when
    delta = (dt.date() - datetime.now().date()).days
    if delta == 0:
        day = "heute"
    elif delta == 1:
        day = "morgen"
    elif delta == 2:
        day = "übermorgen"
    elif delta == -1:
        day = "gestern"
    elif 2 < delta <= 6:
        day = f"am {_WEEKDAYS_DE[dt.weekday()]}"
    else:
        day = dt.strftime("%d.%m.%Y")
    text = day if len(when) == _DATE_ONLY_LEN else f"{day} um {dt.strftime('%H:%M')}"
    if mark_past and is_past(when):
        return f"war fällig {text}"
    return text


def _sort_key(entry: Entry) -> tuple:
    """Terminierte Eintraege zuerst (frueheste vorn), danach die undatierten
    in Erfassungs-Reihenfolge."""
    return (0, entry.when) if entry.when else (1, entry.created)


class EntryStore:
    def __init__(self, memory_dir: Path):
        self.path = Path(memory_dir) / "entries.json"
        self.trash_path = Path(memory_dir) / "entries_trash.json"
        self._lock = threading.RLock()
        with self._lock:
            if not self.path.exists():
                self._write([])

    def add(self, text: str, when: str = "", important: bool = False, repeat: str = "") -> Entry:
        clean_when = (when or "").strip()
        clean_repeat = normalize_repeat(repeat)
        # Wiederkehrend (ADR-052): ein bei der Anlage schon vergangener
        # Zeitpunkt rueckt sofort aufs naechste Vorkommen vor ("taeglich um
        # 19:54" um 20 Uhr gesagt = ab morgen) - er darf nie tot anlegen.
        if clean_repeat and clean_when and is_past(clean_when):
            clean_when = advance_to_next_occurrence(clean_when, clean_repeat)
        # A2: nichts zu melden, wenn kein Zeitpunkt existiert ODER er bei der
        # Anlage schon vergangen ist (rueckdatierter Merkposten, z. B. das
        # Audit vom 12.07.25) - solche Eintraege feuern NIE.
        # Auto-Redaction (ADR-040): Secrets nie im Klartext auf Platte.
        entry = Entry(
            text=redact(text.strip()),
            when=clean_when,
            important=important,
            notified=(not clean_when or is_past(clean_when)),
            repeat=clean_repeat if clean_when else "",
        )
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

    def due_unnotified(self) -> list[Entry]:
        """Faellige, noch nicht gemeldete Eintraege (Scheduler, A2/ADR-039) -
        frueheste zuerst, damit Nachholungen in sinnvoller Reihenfolge kommen."""
        with self._lock:
            entries = [Entry.from_dict(d) for d in self._read()]
        due = [e for e in entries if e.when and not e.notified and is_due(e.when)]
        return sorted(due, key=lambda e: e.when)

    def reschedule_repeating(self, entry_id: str) -> Optional[str]:
        """Rueckt einen wiederkehrenden Eintrag aufs naechste ZUKUENFTIGE
        Vorkommen vor und macht ihn wieder meldbar (ADR-052). Wird vom
        Scheduler VOR dem Push aufgerufen (at-most-once pro Vorkommen,
        gleiche Vorsicht wie mark_notified in ADR-039). Liefert das neue
        when oder None (id fehlt / nicht wiederkehrend)."""
        with self._lock:
            data = self._read()
            for d in data:
                if d.get("id") == entry_id:
                    repeat = normalize_repeat(d.get("repeat", ""))
                    when = d.get("when", "")
                    if not repeat or not when:
                        return None
                    new_when = advance_to_next_occurrence(when, repeat)
                    d["when"] = new_when
                    d["notified"] = False
                    self._write(data)
                    logger.info(
                        "Wiederkehrender Eintrag vorgerueckt (%s): %s -> %s",
                        repeat, when, new_when,
                    )
                    return new_when
        return None

    def mark_notified(self, entry_id: str) -> bool:
        """Markiert einen Eintrag als gemeldet (einmaliges Feuern). True bei
        Erfolg; False, wenn die id nicht (mehr) existiert."""
        with self._lock:
            data = self._read()
            for d in data:
                if d.get("id") == entry_id:
                    d["notified"] = True
                    self._write(data)
                    return True
        return False

    def delete(self, id_or_text: str, exact: bool = False) -> Optional[Entry]:
        """Loescht zuerst per exakter id, sonst den ersten Eintrag, dessen
        Text den gesuchten Text enthaelt (case-insensitive). Gibt den
        entfernten Eintrag zurueck oder None - der Command entscheidet, wie
        das gemeldet wird (Muster wie LongTermMemory.forget).

        exact=True (Nacht-Audit-Fix B): NUR exakter Text-Treffer - fuer die
        stillen UI-Endpunkte, die den vollstaendigen Text kennen. Ein Klick
        auf «Zahnarzt» darf nie «Zahnarzt Kontrolltermin» treffen.

        Seit 14.07. (Bestaetigungs-Diaet): Geloeschtes wandert in den
        Papierkorb (entries_trash.json) statt hart zu verschwinden -
        restore() holt es zurueck."""
        needle = (id_or_text or "").strip()
        if not needle:
            return None
        with self._lock:
            data = self._read()
            for i, d in enumerate(data):
                if d.get("id") == needle:
                    removed = data.pop(i)
                    self._write(data)
                    self._to_trash(removed)
                    logger.info("Eintrag geloescht (per id, im Papierkorb): %s", removed.get("text"))
                    return Entry.from_dict(removed)
            lowered = needle.lower()
            for i, d in enumerate(data):
                existing = d.get("text", "").lower()
                hit = existing == lowered if exact else lowered in existing
                if hit:
                    removed = data.pop(i)
                    self._write(data)
                    self._to_trash(removed)
                    logger.info("Eintrag geloescht (per Text, im Papierkorb): %s", removed.get("text"))
                    return Entry.from_dict(removed)
        return None

    def restore(self, text: str = "") -> Optional[Entry]:
        """Holt den juengsten passenden Eintrag (Teilstring, case-insensitive)
        aus dem Papierkorb zurueck. None = nichts gefunden. Leerer Suchtext =
        der zuletzt geloeschte Eintrag (Undo-Geste). Der Eintrag kommt
        UNVERAENDERT zurueck (gleiche id, gleicher notified-Stand) - das
        Loeschen war ein Versehen, also gilt wieder der alte Zustand."""
        needle = (text or "").strip().lower()
        with self._lock:
            trash = self._read_trash()
            for i in range(len(trash) - 1, -1, -1):
                entry = trash[i]
                if needle and needle not in str(entry.get("text", "")).lower():
                    continue
                trash.pop(i)
                write_json_atomic(self.trash_path, trash)
                entry.pop("deleted_at", None)
                data = self._read()
                data.append(entry)
                self._write(data)
                logger.info("Eintrag wiederhergestellt: %s", entry.get("text", ""))
                return Entry.from_dict(entry)
        return None

    def trash_entries(self) -> list[Entry]:
        """Der Papierkorb-Inhalt (neueste zuletzt) - fuer Anzeige/Diagnose."""
        with self._lock:
            return [Entry.from_dict(d) for d in self._read_trash()]

    def _to_trash(self, entry_dict: dict[str, Any]) -> None:
        trash = self._read_trash()
        entry = dict(entry_dict)
        entry["deleted_at"] = datetime.now(timezone.utc).isoformat()
        trash.append(entry)
        if len(trash) > _TRASH_CAP:
            trash = trash[-_TRASH_CAP:]
        write_json_atomic(self.trash_path, trash)

    def _read_trash(self) -> list[dict[str, Any]]:
        data = read_json(self.trash_path, [])
        return data if isinstance(data, list) else []

    def update(
        self,
        id_or_text: str,
        when: Optional[str] = None,
        important: Optional[bool] = None,
    ) -> Optional[Entry]:
        """Aendert einen BESTEHENDEN Eintrag: verschiebt den Zeitpunkt und/oder
        setzt das Wichtig-Flag. Findet ihn per exakter id, sonst per Text-
        Teilstring (case-insensitive), wie delete(). Nur uebergebene Felder
        (nicht None) werden geaendert. Ein neuer, zukuenftiger Zeitpunkt macht
        den Eintrag wieder MELDBAR (notified=False, damit der Scheduler ihn
        erneut feuert); ein vergangener/leerer bleibt still. Gibt den
        geaenderten Eintrag zurueck oder None (kein Treffer)."""
        needle = (id_or_text or "").strip()
        if not needle:
            return None
        lowered = needle.lower()
        with self._lock:
            data = self._read()
            match = None
            for d in data:
                if d.get("id") == needle:
                    match = d
                    break
            if match is None:
                for d in data:
                    if lowered in d.get("text", "").lower():
                        match = d
                        break
            # Kein Text-Treffer? Der Nutzer benennt den Termin oft ueber seine
            # ZEIT ("der 15-Uhr-Termin") - dann per Uhrzeit im when suchen.
            if match is None:
                hm = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*uhr\b|\b(\d{1,2}):(\d{2})\b", lowered)
                if hm:
                    hh = int(hm.group(1) or hm.group(3))
                    mm = hm.group(2) or hm.group(4) or "00"
                    stamp = f"T{hh:02d}:{mm}"
                    for d in data:
                        if stamp in (d.get("when") or ""):
                            match = d
                            break
            if match is None:
                return None
            if when is not None:
                clean = when.strip()
                match["when"] = clean
                # Neuer zukuenftiger Zeitpunkt -> wieder meldbar; sonst still.
                match["notified"] = (not clean or is_past(clean))
            if important is not None:
                match["important"] = bool(important)
            self._write(data)
            updated = Entry.from_dict(match)
        logger.info("Eintrag geaendert: %s (faellig %s, %s)",
                    updated.text, updated.when or "-",
                    "wichtig" if updated.important else "normal")
        return updated

    def _read(self) -> list[dict[str, Any]]:
        return read_json(self.path, [])

    def _write(self, data: list[dict[str, Any]]) -> None:
        write_json_atomic(self.path, data)
