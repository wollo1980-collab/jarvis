"""
Typisierte Parameter-Schemas pro Werkzeug (ADR-064, Multi-Step-Enabler).

Warum: der denkende Kern (ADR-060) trifft den INTENT zuverlaessig, fuellt bei
MEHREREN parallelen Tool-Aufrufen mit dem generischen {target, parameters}-Schema
aber die Argumente unzuverlaessig leer (verifiziert 2026-07-12: gpt-4o-mini/4o/
4.1 gleichermassen). Ursache ist strukturell - ein generisches
`parameters`-Objekt zwingt das Modell nicht zu den echten Feldern. Die Loesung
(so schon im Gate-Kommentar benannt): jedem arg-nehmenden Werkzeug ein
TYPISIERTES Schema mit seinen echten Feldern geben. Dann fuellt das Modell
`items: ["Milch","Brot"]`, `subject`, `time` auch parallel zuverlaessig.

EINE zentrale Spec statt verteilter Attribute (weniger Drift-Flaeche); ein
Contract-Test koppelt jeden Schluessel an einen registrierten Intent, und die
Feld-Semantik bleibt konsistent mit der jeweiligen Befehls-`description` (der
Prosa-Quelle). Werkzeuge OHNE Eintrag hier behalten das generische Schema
(reine Lese-/Nullargument-Befehle brauchen es nicht).
"""
from __future__ import annotations

_STR = "string"

# intent -> {"properties": {feld: json-schema}, "required": [...]}. 'target'
# bildet (wie im Plan) das Ziel/Objekt ab; alle anderen Felder landen in
# Plan.parameters. Beschreibungen bewusst knapp und handlungsnah.
PARAM_SCHEMAS: dict[str, dict] = {
    "get_weather": {
        "properties": {
            "target": {"type": _STR, "description": "Ort/Stadt; leer = Standardort"},
            "day": {"type": _STR, "description": "'heute'/'morgen'/'uebermorgen' oder Wochentag; leer = heute"},
        },
        "required": [],
    },
    "search_web": {
        "properties": {
            "target": {"type": _STR, "description": "Die Suchanfrage ohne Trigger-Worte"},
        },
        "required": ["target"],
    },
    "add_entry": {
        "properties": {
            "text": {"type": _STR, "description": "Wortlaut der Erinnerung/Aufgabe OHNE Trigger-Worte"},
            "when": {"type": _STR, "description": "Zeitpunkt als EIN ISO-8601-String (z. B. '2026-07-12T15:00'); weglassen wenn keine Zeit genannt"},
            "important": {"type": "boolean", "description": "true bei 'wichtig'/'wichtiger Termin'"},
            "repeat": {"type": _STR, "description": "'taeglich' oder 'woechentlich' bei Wiederholung, sonst weglassen"},
        },
        "required": ["text"],
    },
    "update_entry": {
        "properties": {
            "target": {"type": _STR, "description": "Text des BESTEHENDEN Eintrags (Teilstring genuegt)"},
            "when": {"type": _STR, "description": "NEUER Zeitpunkt als ISO-8601-String"},
            "important": {"type": "boolean", "description": "neues Wichtig-Flag"},
        },
        "required": ["target"],
    },
    "remember_person": {
        "properties": {
            "name": {"type": _STR, "description": "Name der Person (z. B. 'Anna', 'Tom')"},
            "note": {"type": _STR, "description": "Wer sie ist / Rolle / Beziehung, ohne Trigger-Worte (z. B. 'meine Steuerberaterin')"},
        },
        "required": ["name", "note"],
    },
    "who_is": {
        "properties": {
            "name": {"type": _STR, "description": "Name der Person, nach der gefragt wird"},
        },
        "required": ["name"],
    },
    "remember_fact": {
        "properties": {
            "target": {"type": _STR, "description": "Der dauerhaft zu merkende Fakt / die Vorliebe"},
            "category": {"type": _STR, "description": "optionale Kategorie, z. B. 'gewohnheit'"},
        },
        "required": ["target"],
    },
    "add_to_list": {
        "properties": {
            "target": {"type": _STR, "description": "Name der Liste (Standard 'einkaufsliste')"},
            "items": {"type": "array", "items": {"type": _STR},
                      "description": "ALLE zu ergaenzenden Posten als Liste - auch mehrere mit 'und', z. B. ['Milch','Brot']"},
        },
        "required": ["items"],
    },
    "remove_from_list": {
        "properties": {
            "target": {"type": _STR, "description": "Name der Liste"},
            "items": {"type": "array", "items": {"type": _STR},
                      "description": "Zu entfernende Posten als Liste"},
        },
        "required": ["items"],
    },
    "show_list": {
        "properties": {
            "target": {"type": _STR, "description": "Name der Liste; leer = Einkaufsliste"},
        },
        "required": [],
    },
    "open_program": {
        "properties": {
            "target": {"type": _STR, "description": "Name des Programms, z. B. 'Notepad', 'Spotify'"},
        },
        "required": ["target"],
    },
    "set_owner_name": {
        "properties": {
            "target": {"type": _STR, "description": "Der Name / die Anrede des Nutzers"},
        },
        "required": ["target"],
    },
    "spotify_volume": {
        "properties": {
            "level": {"type": "integer", "description": "Lautstaerke 0-100"},
        },
        "required": ["level"],
    },
    "calendar_agenda": {
        "properties": {
            "day": {"type": _STR, "description": "'heute'/'morgen'/'uebermorgen', Wochentag oder ISO-Datum; leer = heute"},
        },
        "required": [],
    },
    "calendar_add_event": {
        "properties": {
            "subject": {"type": _STR, "description": "Titel des Termins (ohne Trigger-Worte)"},
            "day": {"type": _STR, "description": "'heute'/'morgen'/'uebermorgen', Wochentag oder ISO-Datum"},
            "time": {"type": _STR, "description": "Uhrzeit 'HH:MM'; weglassen = ganztaegig"},
            "location": {"type": _STR, "description": "Ort, optional"},
        },
        "required": ["subject"],
    },
    "calendar_move_event": {
        "properties": {
            "subject": {"type": _STR, "description": "Stichwort des bestehenden Termins"},
            "time": {"type": _STR, "description": "NEUE Uhrzeit 'HH:MM'"},
            "day": {"type": _STR, "description": "neuer Tag, optional (sonst gleicher Tag)"},
        },
        "required": ["subject", "time"],
    },
    "calendar_cancel_event": {
        "properties": {
            "subject": {"type": _STR, "description": "Stichwort des abzusagenden Termins"},
        },
        "required": ["subject"],
    },
}
