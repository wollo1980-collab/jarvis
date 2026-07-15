"""Tests fuer commands/entries.py - add/list/delete_entry (A1). Der Store
laeuft gegen tmp_path (configure-Muster wie commands/memory.py)."""
from __future__ import annotations

from pathlib import Path

import commands.entries as entries
from core.models import Plan, Status


def _configure(tmp_path: Path) -> None:
    entries.configure(tmp_path)


def test_add_entry_echoes_text_and_readable_time(tmp_path: Path):
    _configure(tmp_path)
    result = entries.AddEntryCommand().execute(
        Plan(
            intent="add_entry",
            parameters={"text": "Zahnarzt", "when": "2099-07-10T09:00"},
        )
    )

    assert result.status == Status.SUCCESS
    assert "«Zahnarzt»" in result.message
    assert "10.07.2099 um 09:00" in result.message  # Echo mit lesbarer Zeit
    assert result.data["id"]


def test_add_entry_important_gets_star_and_date_only_format(tmp_path: Path):
    _configure(tmp_path)
    result = entries.AddEntryCommand().execute(
        Plan(
            intent="add_entry",
            parameters={"text": "Audit in Musterstadt", "when": "2025-07-12", "important": True},
        )
    )

    assert result.status == Status.SUCCESS
    # Persona-Pass 2026-07-09 + Varianten-Pool (Lebendigkeit 2026-07-10).
    assert any(result.message.startswith(p) for p in entries._IMPORTANT_PREFIXES)
    assert "12.07.2025" in result.message  # ganztaegig ohne Uhrzeit


def test_update_entry_reschedules_existing_no_duplicate(tmp_path: Path):
    """Reibung 12.07.: 'aktualisiere den 15-Uhr-Termin auf 14:45' aenderte den
    BESTEHENDEN Eintrag - kein zweiter «Fahre zu meiner Mutter»."""
    _configure(tmp_path)
    entries.AddEntryCommand().execute(Plan(
        intent="add_entry",
        parameters={"text": "Fahre zu meiner Mutter", "when": "2099-07-12T15:00", "important": True},
    ))

    result = entries.UpdateEntryCommand().execute(Plan(
        intent="update_entry",
        parameters={"text": "Mutter", "when": "2099-07-12T14:45"},
    ))

    assert result.status == Status.SUCCESS
    assert "Geändert" in result.message
    assert "12.07.2099 um 14:45" in result.message
    listed = entries.ListEntriesCommand().execute(Plan(intent="list_entries")).message
    assert listed.count("Fahre zu meiner Mutter") == 1        # KEIN Duplikat
    assert "14:45" in listed and "15:00" not in listed        # verschoben, nicht kopiert


def test_update_entry_unknown_offers_to_add(tmp_path: Path):
    _configure(tmp_path)
    result = entries.UpdateEntryCommand().execute(Plan(
        intent="update_entry",
        parameters={"text": "gibt es gar nicht", "when": "2099-07-12T14:45"},
    ))
    assert result.status == Status.NEEDS_CLARIFICATION
    assert "keinen Eintrag" in result.message


def test_add_entry_without_text_asks_back(tmp_path: Path):
    _configure(tmp_path)
    result = entries.AddEntryCommand().execute(Plan(intent="add_entry"))
    assert result.status == Status.NEEDS_CLARIFICATION


def test_add_entry_falls_back_to_target(tmp_path: Path):
    # Der Planner legt den Text idealerweise in parameters.text ab -
    # faellt er auf target zurueck, geht nichts verloren.
    _configure(tmp_path)
    result = entries.AddEntryCommand().execute(Plan(intent="add_entry", target="Milch kaufen"))
    assert result.status == Status.SUCCESS
    assert "«Milch kaufen»" in result.message


def test_list_entries_empty_is_friendly(tmp_path: Path):
    _configure(tmp_path)
    result = entries.ListEntriesCommand().execute(Plan(intent="list_entries"))
    assert result.status == Status.SUCCESS
    assert "keine" in result.message.lower()


def test_list_entries_shows_star_and_date(tmp_path: Path):
    _configure(tmp_path)
    entries.AddEntryCommand().execute(
        Plan(intent="add_entry", parameters={"text": "Audit", "when": "2025-07-12", "important": True})
    )
    entries.AddEntryCommand().execute(Plan(intent="add_entry", parameters={"text": "Milch kaufen"}))

    result = entries.ListEntriesCommand().execute(Plan(intent="list_entries"))

    assert result.status == Status.SUCCESS
    # Vergangener wichtiger Termin bleibt gelistet (PO-Default), heisst aber
    # ehrlich 'war fällig' (Kundenreview 13.07., 'Eine gemeinsame Wahrheit').
    assert "⭐ «Audit» — war fällig 12.07.2025" in result.message
    assert "«Milch kaufen»" in result.message
    assert result.data["count"] == 2


def test_list_entries_never_calls_past_appointments_upcoming(tmp_path: Path):
    """Kundenreview 13.07. (Vertrauensbruch Rang 1): Startseite sagte abends
    korrekt 'Nichts ist fällig', 'Was steht an?' nannte den 09:00-Termin aber
    weiter wie anstehend. Die Liste traegt jetzt den 'war fällig'-Marker -
    dieselbe Wahrheit wie Tageskarten und Gedaechtnis-Ansicht."""
    from datetime import datetime, timedelta

    _configure(tmp_path)
    vorbei = (datetime.now() - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
    entries.AddEntryCommand().execute(
        Plan(intent="add_entry",
             parameters={"text": "Termin beim Chef", "when": vorbei, "important": True})
    )

    result = entries.ListEntriesCommand().execute(Plan(intent="list_entries"))

    assert "«Termin beim Chef» — war fällig" in result.message


def test_list_entries_appends_todays_upcoming_calendar(tmp_path: Path):
    """Tages-Blick (2. Kundenreview Rang 6, PO-Go): 'Was steht an?' zeigt
    auch heute noch KOMMENDE Kalender-Termine - Vergangenes bleibt draussen
    (eine Wahrheit), ganztaegig zaehlt; gefilterte Rufe bleiben pur."""
    from datetime import datetime, timedelta

    import commands.calendar as calendar_commands

    class FakeClient:
        def agenda(self, start, end):
            now = datetime.now()
            return [
                {"subject": "Termin beim Chef", "start": (now - timedelta(hours=2)).isoformat()},
                {"subject": "Zahnarzt", "start": (now + timedelta(hours=2)).isoformat(),
                 "location": "Musterstadt"},
                {"subject": "Geburtstag Anna", "start": now.strftime("%Y-%m-%d"), "all_day": True},
            ]

    _configure(tmp_path)
    calendar_commands.configure(None, client=FakeClient())
    try:
        entries.AddEntryCommand().execute(Plan(intent="add_entry", parameters={"text": "Milch kaufen"}))

        result = entries.ListEntriesCommand().execute(Plan(intent="list_entries"))
        assert "🗓 Heute noch im Kalender:" in result.message
        assert "Zahnarzt (Musterstadt)" in result.message
        assert "Geburtstag Anna" in result.message           # ganztaegig zaehlt
        assert "Termin beim Chef" not in result.message      # vorbei = steht nicht an

        filtered = entries.ListEntriesCommand().execute(
            Plan(intent="list_entries", parameters={"keyword": "milch"})
        )
        assert "Kalender" not in filtered.message            # gefilterter Ruf bleibt pur
    finally:
        calendar_commands.configure(None)                    # Kalender wieder aus


def test_list_entries_without_calendar_stays_unchanged(tmp_path: Path):
    """Fail-open: ohne Kalender-Zugang exakt die bisherige Antwort."""
    import commands.calendar as calendar_commands

    _configure(tmp_path)
    calendar_commands.configure(None)

    result = entries.ListEntriesCommand().execute(Plan(intent="list_entries"))
    assert "Keine anstehenden Einträge" in result.message
    assert "Kalender" not in result.message


def test_add_entry_with_repeat_echoes_rhythm_and_next_time(tmp_path: Path):
    """ADR-052: das Echo nennt Rhythmus + naechsten Termin - ein Planner-
    Fehlgriff faellt sofort auf; die Liste traegt den ↻-Marker."""
    _configure(tmp_path)
    result = entries.AddEntryCommand().execute(
        Plan(intent="add_entry",
             parameters={"text": "Zusammenfassung der Lage", "when": "2099-07-11T19:54",
                         "repeat": "täglich"})
    )

    assert result.status == Status.SUCCESS
    assert "↻ täglich" in result.message
    assert "nächste: 11.07.2099 um 19:54" in result.message

    listing = entries.ListEntriesCommand().execute(Plan(intent="list_entries"))
    assert "↻ täglich" in listing.message


def test_list_entries_keyword_filter_via_parameters(tmp_path: Path):
    _configure(tmp_path)
    entries.AddEntryCommand().execute(Plan(intent="add_entry", parameters={"text": "Zahnarzt"}))
    entries.AddEntryCommand().execute(Plan(intent="add_entry", parameters={"text": "Milch kaufen"}))

    result = entries.ListEntriesCommand().execute(
        Plan(intent="list_entries", parameters={"keyword": "zahn"})
    )

    assert "Zahnarzt" in result.message
    assert "Milch" not in result.message


def test_delete_entry_found_and_not_found(tmp_path: Path):
    _configure(tmp_path)
    entries.AddEntryCommand().execute(Plan(intent="add_entry", parameters={"text": "Zahnarzt morgen"}))

    ok = entries.DeleteEntryCommand().execute(
        Plan(intent="delete_entry", parameters={"text": "zahnarzt"})
    )
    assert ok.status == Status.SUCCESS
    assert "«Zahnarzt morgen»" in ok.message
    # Undo-Hinweis (Bestaetigungs-Diaet 14.07.): die Antwort nennt den Rueckweg.
    assert "stell den Eintrag wieder her" in ok.message

    miss = entries.DeleteEntryCommand().execute(
        Plan(intent="delete_entry", parameters={"text": "gibtsnicht"})
    )
    assert miss.status == Status.FAILED


def test_delete_entry_without_text_asks_back(tmp_path: Path):
    _configure(tmp_path)
    result = entries.DeleteEntryCommand().execute(Plan(intent="delete_entry"))
    assert result.status == Status.NEEDS_CLARIFICATION


def test_restore_entry_by_text_and_last_deleted(tmp_path: Path):
    """Papierkorb (Bestaetigungs-Diaet 14.07., Muster restore_fact):
    restore_entry holt den Eintrag zurueck (ohne target: den zuletzt
    geloeschten) - mitsamt Termin im Echo."""
    _configure(tmp_path)
    entries.AddEntryCommand().execute(Plan(
        intent="add_entry",
        parameters={"text": "Zahnarzt", "when": "2099-07-10T09:00"},
    ))
    entries.AddEntryCommand().execute(Plan(intent="add_entry", parameters={"text": "Milch kaufen"}))
    entries.DeleteEntryCommand().execute(Plan(intent="delete_entry", parameters={"text": "Zahnarzt"}))
    entries.DeleteEntryCommand().execute(Plan(intent="delete_entry", parameters={"text": "Milch"}))

    by_text = entries.RestoreEntryCommand().execute(
        Plan(intent="restore_entry", target="zahnarzt")
    )
    assert by_text.status == Status.SUCCESS
    assert "«Zahnarzt»" in by_text.message
    assert "10.07.2099 um 09:00" in by_text.message   # Termin ueberlebt

    last = entries.RestoreEntryCommand().execute(Plan(intent="restore_entry", target=None))
    assert last.status == Status.SUCCESS
    assert "«Milch kaufen»" in last.message


def test_restore_entry_empty_trash_fails_honestly(tmp_path: Path):
    _configure(tmp_path)
    result = entries.RestoreEntryCommand().execute(
        Plan(intent="restore_entry", target="gibtsnicht")
    )
    assert result.status == Status.FAILED
    assert "Papierkorb" in result.message


def test_not_configured_raises_clear_error():
    entries._store = None
    try:
        entries.AddEntryCommand().execute(Plan(intent="add_entry", target="x"))
        assert False, "erwartete RuntimeError"
    except RuntimeError as e:
        assert "nicht konfiguriert" in str(e)
