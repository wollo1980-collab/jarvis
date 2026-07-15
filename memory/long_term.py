"""
Langzeitgedächtnis (v0.4, ADR-009) - getrennt vom Gesprächsverlauf in
memory/store.py::JsonMemoryStore (das bleibt reines Kurzzeitgedächtnis:
letzte N Nachrichten, siehe Handbook Kap. 9).

Hier landen nur Fakten, die der Nutzer Jarvis EXPLIZIT aufträgt sich zu
merken ("Merk dir, dass..."). Bewusst KEINE automatische Extraktion
aus Gesprächen (siehe ADR-009) - das wäre ein zusätzlicher KI-Aufruf
mit Kosten und dem Risiko, falsche oder ungewollt private Dinge zu
speichern, ohne dass der Nutzer das aktiv wollte.

Drei Kategorien laut Handbook (Kap. 3: "Langzeitgedächtnis besitzt:
Projekte, Gewohnheiten, Präferenzen") plus "allgemein" als Fallback,
falls die KI keine eindeutig passende Kategorie erkennt.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from core.fileio import read_json, write_json_atomic
from core.redaction import redact

logger = logging.getLogger("jarvis.memory.long_term")

VALID_CATEGORIES = {"projekt", "gewohnheit", "praeferenz", "allgemein"}
DEFAULT_CATEGORY = "allgemein"

# Papierkorb (Kundenreview 13.07.: '"✕ = sofort weg" ist fuer persoenliche
# Daten zu riskant'): Geloeschtes wandert in eine EIGENE Datei (kein
# Schema-Bruch fuer die long_term.json-Leser) und bleibt wiederherstellbar.
_TRASH_CAP = 100

# Semantische Dedupe (Kundenreview 13.07.: dieselbe Praeferenz stand dreimal
# im Profil): ab dieser Kosinus-Aehnlichkeit gelten zwei Fakten als derselbe.
# Bewusst HOCH (lieber ein Duplikat behalten als einen echten Fakt verlieren).
DEDUPE_THRESHOLD = 0.90


def _norm(text: str) -> str:
    """Normalisierter Vergleichsschluessel fuer die Dedup (Kleinschreibung,
    Whitespace zusammengefasst) - wie in memory/semantic.py::_hash."""
    return " ".join(text.lower().split())


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
        self.trash_path = Path(memory_dir) / "long_term_trash.json"
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
        redacted = redact(text)
        facts = self._read()

        # Dedup (PO-Reibung 12.07.: derselbe Fakt stand "1x Allgemein, 1x
        # Gewohnheit"): ein inhaltsgleicher Fakt wird NICHT ein zweites Mal
        # angelegt. Vergleich normalisiert (Kleinschreibung + Whitespace),
        # kategorie-uebergreifend. Kommt der Fakt mit einer SPEZIFISCHEREN
        # Kategorie erneut, wird eine bisher 'allgemeine' Ablage angehoben
        # statt ein Duplikat zu erzeugen.
        needle = _norm(redacted)
        for existing in facts:
            if _norm(str(existing.get("text", ""))) == needle:
                if existing.get("category") == DEFAULT_CATEGORY and category != DEFAULT_CATEGORY:
                    existing["category"] = category
                    self._write(facts)
                    logger.info("Fakt vorhanden - Kategorie angehoben auf '%s': %s", category, text)
                else:
                    logger.info("Fakt bereits vorhanden - kein Duplikat: %s", text)
                return Fact.from_dict(existing)

        fact = Fact(text=redacted, category=category)
        facts.append(fact.to_dict())
        self._write(facts)
        logger.info("Neuer Fakt gemerkt (%s): %s", category, text)
        return fact

    def forget(self, text: str, exact: bool = False) -> bool:
        """Entfernt den ersten Fakt, dessen Text den gesuchten Text
        (case-insensitive, als Teilstring) enthält. Gibt True zurück,
        wenn etwas gelöscht wurde, sonst False - der aufrufende
        Command entscheidet, wie das dem Nutzer gemeldet wird.

        exact=True (Nacht-Audit-Fix B): NUR exakter Treffer - für die
        stillen UI-Endpunkte, die den vollständigen Text kennen.

        Seit 14.07. (Kundenreview): Geloeschtes wandert in den Papierkorb
        (long_term_trash.json) statt hart zu verschwinden - restore()
        holt es zurueck."""
        facts = self._read()
        needle = text.strip().lower()
        for i, f in enumerate(facts):
            existing = f["text"].lower()
            hit = existing == needle if exact else (needle and needle in existing)
            if hit:
                removed = facts.pop(i)
                self._write(facts)
                self._to_trash(removed, reason="vergessen")
                logger.info("Fakt vergessen (im Papierkorb): %s", removed["text"])
                return True
        return False

    def restore(self, text: str) -> Optional[Fact]:
        """Holt den juengsten passenden Fakt (Teilstring, case-insensitive)
        aus dem Papierkorb zurueck ins Gedaechtnis. None = nichts gefunden.
        Leerer Suchtext = der zuletzt geloeschte Fakt (Undo-Geste)."""
        trash = self._read_trash()
        needle = text.strip().lower()
        for i in range(len(trash) - 1, -1, -1):
            entry = trash[i]
            if needle and needle not in str(entry.get("text", "")).lower():
                continue
            trash.pop(i)
            write_json_atomic(self.trash_path, trash)
            entry.pop("deleted_at", None)
            entry.pop("reason", None)
            facts = self._read()
            facts.append(entry)
            self._write(facts)
            logger.info("Fakt wiederhergestellt: %s", entry.get("text", ""))
            return Fact.from_dict(entry)
        return None

    def trash_facts(self) -> list[Fact]:
        """Der Papierkorb-Inhalt (neueste zuletzt) - fuer Anzeige/Diagnose."""
        return [Fact.from_dict(f) for f in self._read_trash()]

    def dedupe_semantic(self, embed_fn: Callable[["list[str]"], "list[list[float]]"],
                        threshold: float = DEDUPE_THRESHOLD) -> "list[tuple[str, str]]":
        """Raeumt sinngleiche Fakten auf (Kundenreview 13.07.: dieselbe
        Praeferenz dreimal im Profil): bettet alle Fakten in EINEM Aufruf ein,
        findet Paare mit Kosinus >= threshold und verschiebt je Duplikat-
        Gruppe alle bis auf den AELTESTEN in den Papierkorb (nichts geht
        verloren). Liefert [(behalten, in_papierkorb), ...] fuer den Bericht.
        Fail-open: Embedding-Fehler -> keine Aenderung, leere Liste."""
        from core.embeddings import cosine

        facts = self._read()
        if len(facts) < 2:
            return []
        texts = [str(f.get("text", "")) for f in facts]
        try:
            vectors = embed_fn(texts)
        except Exception:  # noqa: BLE001 - Aufraeumen stoert den Betrieb nie
            logger.warning("Gedaechtnis-Dedupe: Embedding fehlgeschlagen (uebersprungen).", exc_info=True)
            return []
        if len(vectors) != len(facts) or any(not v for v in vectors):
            logger.info("Gedaechtnis-Dedupe: unvollstaendige Vektoren (uebersprungen).")
            return []

        moved: list[tuple[str, str]] = []
        keep: list[dict] = []
        keep_vecs: list[list[float]] = []
        for f, vec in zip(facts, vectors):        # chronologisch: aeltester zuerst
            twin = next((k for k, kv in zip(keep, keep_vecs) if cosine(vec, kv) >= threshold), None)
            if twin is None:
                keep.append(f)
                keep_vecs.append(vec)
                continue
            # Kategorie-Anhebung wie in remember(): das spezifischere Label
            # ueberlebt am behaltenen Fakt.
            if twin.get("category") == DEFAULT_CATEGORY and f.get("category") != DEFAULT_CATEGORY:
                twin["category"] = f.get("category")
            self._to_trash(f, reason="duplikat")
            moved.append((str(twin.get("text", "")), str(f.get("text", ""))))
        if moved:
            self._write(keep)
            for kept, gone in moved:
                logger.info("Gedaechtnis-Dedupe: «%s» in den Papierkorb (sinngleich mit «%s»).", gone, kept)
        return moved

    def _to_trash(self, fact_dict: dict, reason: str) -> None:
        trash = self._read_trash()
        entry = dict(fact_dict)
        entry["deleted_at"] = datetime.now(timezone.utc).isoformat()
        entry["reason"] = reason
        trash.append(entry)
        if len(trash) > _TRASH_CAP:
            trash = trash[-_TRASH_CAP:]
        write_json_atomic(self.trash_path, trash)

    def _read_trash(self) -> list[dict]:
        data = read_json(self.trash_path, [])
        return data if isinstance(data, list) else []

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
