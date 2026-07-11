"""
Robuste Datei-I/O-Helfer (Audit-Härtung 2026-07-07).

Zwei Probleme, eine Datei:
- **Atomares Schreiben von JSON-Zustand:** ein Crash mitten im `open(..,"w")`+
  `json.dump` lässt eine halb geschriebene, kaputte Datei zurück - und der Reader
  fiel bisher still auf einen leeren Default zurück (= Datenverlust). Lösung:
  in eine Temp-Datei im selben Verzeichnis schreiben, `flush`+`fsync`, dann
  atomar per `os.replace` an ihren Platz ziehen (auf demselben Dateisystem
  atomar). Beim Lesen wird ein kaputtes JSON nicht mehr still verworfen, sondern
  zur Seite gelegt (`.corrupt-<zeit>`) - so ist der Zustand höchstens beschädigt,
  nie unbemerkt gelöscht.
- **Additives Schreiben ohne Überschreiben:** langlaufende Vorschläge/Artefakte
  versprechen „neue Datei, kein Überschreiben". Bei reiner Sekundenauflösung im
  Namen konnten zwei Läufe in dieselbe Datei schreiben. `write_text_create_only`
  erzwingt das Versprechen strukturell (`open(.., "x")` + eindeutiger Suffix bei
  Kollision).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.fileio")


def write_json_atomic(path: Path, data: Any) -> None:
    """Schreibt `data` als JSON atomar nach `path`: erst in eine Temp-Datei im
    selben Verzeichnis (damit `os.replace` auf demselben Dateisystem bleibt und
    wirklich atomar ist), dann umbenennen. Ein Crash hinterlässt entweder die
    alte, intakte Datei oder die neue, vollständige - nie eine halbe."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        # Bei einem Fehler vor os.replace darf keine verwaiste Temp-Datei bleiben.
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                logger.warning("Verwaiste Temp-Datei konnte nicht entfernt werden: %s", tmp)


def read_json(path: Path, default: Any) -> Any:
    """Liest JSON aus `path`. Fehlt die Datei → `default`. Ist sie **kaputt**
    (unlesbares JSON), wird sie zur Seite gelegt (`.corrupt-<zeit>`) statt still
    verworfen, gewarnt und `default` geliefert - so ist der Zustand nachweislich
    nicht unbemerkt gelöscht, sondern zur Analyse erhalten."""
    path = Path(path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, ValueError, OSError) as e:
        _preserve_corrupt(path, e)
        return default


def _preserve_corrupt(path: Path, error: Exception) -> None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.corrupt-{stamp}")
    try:
        os.replace(path, backup)
        logger.warning(
            "Kaputte JSON-Datei %s erkannt (%s) - zur Seite gelegt als %s, Default verwendet.",
            path, error, backup.name,
        )
    except OSError:
        logger.error("Kaputte JSON-Datei %s (%s) - konnte nicht gesichert werden.", path, error)


def read_text_capped(path: Path, cap: int) -> str:
    """Liest eine Textdatei fail-safe und deckelt sie auf `cap` Zeichen (Kopf,
    da PROJECT_STATE/CHANGELOG/logbook Neues oben führen). Nie ein harter
    Fehler: fehlt oder klemmt die Datei, kommt eine Notiz statt eines
    Absturzes - der Aufrufer entscheidet, ob das reicht."""
    try:
        text = Path(path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return "(nicht lesbar)"
    if len(text) <= cap:
        return text
    return text[:cap] + " …[gekürzt]"


def write_text_create_only(directory: Path, filename: str, content: str) -> Path:
    """Schreibt `content` als NEUE Textdatei nach `directory/filename`. Existiert
    der Name bereits, wird ein eindeutiger Suffix angehängt (`stem-2.ext`,
    `stem-3.ext`, …) - es wird **niemals** eine bestehende Datei überschrieben.
    Liefert den tatsächlich geschriebenen Pfad."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stem, dot, ext = filename.rpartition(".")
    if not dot:  # kein Punkt -> ganzer Name ist der Stamm
        stem, ext = filename, ""
    suffix = f".{ext}" if ext else ""

    candidate = directory / filename
    counter = 2
    while True:
        try:
            with open(candidate, "x", encoding="utf-8") as fh:
                fh.write(content)
            return candidate
        except FileExistsError:
            candidate = directory / f"{stem}-{counter}{suffix}"
            counter += 1
