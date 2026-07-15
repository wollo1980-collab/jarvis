"""Vertrags-Test 'Eine gemeinsame Wahrheit' (2. Kundenreview 13.07., Rang 1;
Sol-Review: 'Keine widerspruechlichen Kalender-/Reminder-Zustaende in der
Abnahmesuite').

Der teuerste Vertrauensbruch war NIE ein Einzel-Bug, sondern zwei Oberflaechen,
die sich widersprachen ('Nichts ist faellig' vs. '09:00 steht an'). Dieser Test
fuettert EIN entries.json und prueft ALLE drei Oberflaechen gemeinsam:
Tageskarten (entries_status), GEDAECHTNIS (memory_view) und die 'Was steht
an?'-Antwort (ListEntriesCommand). Faellt eine Flaeche zurueck in die alte
Semantik, bricht GENAU EIN Test - nicht erst das naechste Review.

Bewusst nur die Vergangenheits-Seite (der echte Review-Fall): Zukunfts-Faelle
waeren um Mitternacht datumsabhaengig flaky."""
from __future__ import annotations

from datetime import datetime, timedelta
from json import dumps
from pathlib import Path

import commands.entries as entries_commands
from core.dashboard_data import entries_status, memory_view
from core.models import Plan


def test_past_appointment_is_past_on_every_surface(tmp_path: Path):
    vorbei = (datetime.now() - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
    (tmp_path / "entries.json").write_text(
        dumps([{"text": "Termin beim Chef", "when": vorbei, "important": True,
                "notified": True}]),
        encoding="utf-8",
    )

    # Flaeche 1: Tageskarten - nicht 'anstehend', und nach der Gnadenfrist
    # (1 h < 3 h) auch nicht mehr als 'war faellig'-Karte.
    status = entries_status(tmp_path)
    assert status["today"] == []
    assert status["due_today"] == []

    # Flaeche 2: GEDAECHTNIS - gelistet (wichtig!), aber als Vergangenheit.
    view_entries = memory_view(tmp_path)["entries"]
    assert [e["text"] for e in view_entries] == ["Termin beim Chef"]
    assert view_entries[0]["when"].startswith("war fällig")

    # Flaeche 3: 'Was steht an?' - gelistet, aber NIE wie bevorstehend.
    entries_commands.configure(tmp_path)
    message = entries_commands.ListEntriesCommand().execute(
        Plan(intent="list_entries")).message
    assert "«Termin beim Chef» — war fällig" in message
    assert "steht an" not in message
