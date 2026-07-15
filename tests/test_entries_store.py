"""Tests fuer memory/entries.py - EntryStore (A1): anlegen, auflisten nach
PO-Default (offen/zukuenftig + alle wichtigen), loeschen, Persistenz."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from memory.entries import Entry, EntryStore, is_past


def _future_iso(hours: float = 24.0) -> str:
    return (datetime.now() + timedelta(hours=hours)).isoformat(timespec="minutes")


def _past_iso(hours: float = 24.0) -> str:
    return (datetime.now() - timedelta(hours=hours)).isoformat(timespec="minutes")


# --- Natuerliche Zeit-Formulierung (Reibung 12.07.: "12.07.2026 14:45" = 1998) --

def test_format_when_is_relative_and_natural():
    from memory.entries import format_when

    now = datetime.now()
    heute = now.replace(hour=14, minute=45, second=0, microsecond=0)
    assert format_when(heute.strftime("%Y-%m-%dT%H:%M")) == "heute um 14:45"

    morgen = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    assert format_when(morgen.strftime("%Y-%m-%dT%H:%M")) == "morgen um 09:00"

    assert format_when(now.strftime("%Y-%m-%d")) == "heute"          # ganztaegig
    in_vier = (now + timedelta(days=4)).replace(hour=9, minute=0)
    assert format_when(in_vier.strftime("%Y-%m-%dT%H:%M")).startswith("am ")  # Wochentag
    assert format_when("2099-07-12T14:45") == "12.07.2099 um 14:45"  # weit weg absolut


def test_format_when_marks_past_when_asked():
    """Kundenreview 13.07. ('Eine gemeinsame Wahrheit'): ein 09:00-Termin darf
    abends nirgends mehr wie anstehend klingen. mark_past=True kennzeichnet
    Vergangenes als 'war fällig ...'; Zukunft und der Default bleiben exakt
    wie bisher (Anlege-Echos nennen nie Vergangenes)."""
    from memory.entries import format_when

    vorbei = _past_iso(2)
    assert format_when(vorbei, mark_past=True).startswith("war fällig ")
    assert not format_when(vorbei).startswith("war fällig ")   # Default unveraendert

    bald = _future_iso(2)
    assert not format_when(bald, mark_past=True).startswith("war fällig ")

    # Ganztaegig heute: bis Tagesende offen (is_past-Semantik), kein Marker.
    assert format_when(datetime.now().strftime("%Y-%m-%d"), mark_past=True) == "heute"


# --- Eintrag aendern/verschieben (Reibung 12.07.: kein Duplikat) ----------

def test_update_changes_when_same_entry_no_duplicate(tmp_path: Path):
    store = EntryStore(tmp_path)
    e = store.add("Fahre zu meiner Mutter", when=_future_iso(6), important=True)

    updated = store.update("mutter", when=_future_iso(3))

    assert updated is not None
    assert updated.id == e.id                 # DERSELBE Eintrag - kein Duplikat
    assert updated.important is True          # nicht uebergebenes Feld bleibt
    assert updated.notified is False          # zukuenftig -> wieder meldbar
    assert len(store.list_open()) == 1        # es entstand KEIN zweiter Eintrag


def test_update_matches_by_time_when_text_fails(tmp_path: Path):
    """Der Nutzer benennt den Termin oft ueber die ZEIT ('den 15-Uhr-Termin')
    statt ueber den Text - dann per Uhrzeit im when finden."""
    store = EntryStore(tmp_path)
    store.add("Fahre zu meiner Mutter", when="2099-07-12T15:00", important=True)

    updated = store.update("15 Uhr", when="2099-07-12T14:45")

    assert updated is not None
    assert "Mutter" in updated.text            # per Uhrzeit gefunden
    assert updated.when == "2099-07-12T14:45"


def test_update_no_match_returns_none(tmp_path: Path):
    store = EntryStore(tmp_path)
    store.add("Zahnarzt", when=_future_iso(5))
    assert store.update("gibt es nicht", when=_future_iso(2)) is None


def test_update_important_only_keeps_when(tmp_path: Path):
    store = EntryStore(tmp_path)
    when = _future_iso(4)
    store.add("Meeting", when=when, important=False)

    updated = store.update("meeting", important=True)

    assert updated.important is True
    assert updated.when == when               # when unveraendert, wenn nicht gesetzt


# --- Wiederkehrende Erinnerungen (ADR-052) --------------------------------

def test_repeat_normalization_and_migration(tmp_path: Path):
    from memory.entries import normalize_repeat

    assert normalize_repeat("täglich") == "taeglich"
    assert normalize_repeat("Wöchentlich") == "woechentlich"
    assert normalize_repeat("alle 3 Tage") == ""  # unbekannt = ehrlich einmalig
    # Migration: Bestandseintrag ohne repeat-Feld ist einmalig.
    assert Entry.from_dict({"text": "alt", "when": _future_iso()}).repeat == ""


def test_add_with_past_time_advances_repeating_entry(tmp_path: Path):
    """'taeglich um 19:54' um 20 Uhr gesagt: der Eintrag rueckt sofort auf
    morgen vor und bleibt meldbar - er darf nie tot (notified) anlegen."""
    store = EntryStore(tmp_path)
    past = _past_iso(hours=1)

    entry = store.add("Zusammenfassung", when=past, repeat="täglich")

    assert entry.repeat == "taeglich"
    assert not is_past(entry.when)      # aufs naechste Vorkommen vorgerueckt
    assert entry.notified is False      # wird gemeldet werden
    # Uhrzeit bleibt erhalten (nur der Tag wandert):
    assert entry.when[11:16] == past[11:16]


def test_advance_skips_all_missed_occurrences_in_one_step():
    """Fuenf verpasste Tage = EIN Sprung in die Zukunft, keine Flut."""
    from memory.entries import advance_to_next_occurrence

    five_days_ago = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")
    advanced = advance_to_next_occurrence(five_days_ago, "taeglich")
    assert not is_past(advanced)
    assert (datetime.fromisoformat(advanced) - datetime.now()) <= timedelta(days=1)

    weekly = advance_to_next_occurrence(five_days_ago, "woechentlich")
    assert not is_past(weekly)
    assert advance_to_next_occurrence("kaputt", "taeglich") == "kaputt"  # fail-safe


def test_reschedule_repeating_advances_and_stays_notifiable(tmp_path: Path):
    store = EntryStore(tmp_path)
    entry = store.add("Tabletten", when=_future_iso(hours=1), repeat="taeglich")
    # Zeit "verstreicht": when in die Vergangenheit ziehen (wie im A2-Test).
    data = store._read()
    data[0]["when"] = _past_iso(hours=1)
    store._write(data)

    new_when = store.reschedule_repeating(entry.id)

    assert new_when is not None and not is_past(new_when)
    refreshed = store.list_open()[0]
    assert refreshed.when == new_when
    assert refreshed.notified is False   # naechstes Vorkommen wird gemeldet
    # Einmaliger Eintrag: reschedule lehnt ehrlich ab.
    once = store.add("einmalig", when=_future_iso())
    assert store.reschedule_repeating(once.id) is None


def test_delete_exact_never_hits_similar_neighbour(tmp_path: Path):
    """Nacht-Audit-Fix B: die stillen UI-Endpunkte loeschen exakt - ein
    Klick auf «Zahnarzt» trifft nie «Zahnarzt Kontrolltermin»."""
    store = EntryStore(tmp_path)
    store.add("Zahnarzt Kontrolltermin")
    store.add("Zahnarzt")

    removed = store.delete("Zahnarzt", exact=True)

    assert removed is not None and removed.text == "Zahnarzt"
    assert [e.text for e in store.list_open()] == ["Zahnarzt Kontrolltermin"]
    # Teilstring-Weg (Sprache/Chat) bleibt tolerant:
    assert store.delete("Kontroll") is not None


def test_add_persists_and_returns_entry(tmp_path: Path):
    store = EntryStore(tmp_path)
    entry = store.add("Zahnarzt", when=_future_iso(), important=False)

    assert entry.id  # id vergeben
    assert entry.text == "Zahnarzt"
    # Persistenz: eine NEUE Store-Instanz liest denselben Eintrag.
    again = EntryStore(tmp_path)
    entries = again.list_open()
    assert [e.text for e in entries] == ["Zahnarzt"]


def test_when_and_important_are_optional(tmp_path: Path):
    store = EntryStore(tmp_path)
    entry = store.add("Milch kaufen")

    assert entry.when == ""
    assert entry.important is False
    assert [e.text for e in store.list_open()] == ["Milch kaufen"]


def test_default_list_shows_open_future_and_all_important(tmp_path: Path):
    """PO-Default: offene/zukuenftige + ALLE wichtigen; nicht-wichtige
    Vergangenheit ist ausgeblendet."""
    store = EntryStore(tmp_path)
    store.add("Zukunft", when=_future_iso())
    store.add("Undatiert")
    store.add("Wichtig-vergangen", when="2025-07-12", important=True)  # Audit-Fall
    store.add("Vergangen", when=_past_iso())

    texts = [e.text for e in store.list_open()]
    assert "Zukunft" in texts
    assert "Undatiert" in texts
    assert "Wichtig-vergangen" in texts  # important schlaegt Vergangenheit
    assert "Vergangen" not in texts      # nicht-wichtige Vergangenheit weg


def test_include_past_shows_everything(tmp_path: Path):
    store = EntryStore(tmp_path)
    store.add("Vergangen", when=_past_iso())

    assert store.list_open() == []
    assert [e.text for e in store.list_open(include_past=True)] == ["Vergangen"]


def test_keyword_and_important_filters(tmp_path: Path):
    store = EntryStore(tmp_path)
    store.add("Audit in Musterstadt", when="2025-07-12", important=True)
    store.add("Zahnarzt", when=_future_iso())

    assert [e.text for e in store.list_open(keyword="audit")] == ["Audit in Musterstadt"]
    assert [e.text for e in store.list_open(important_only=True)] == ["Audit in Musterstadt"]
    assert store.list_open(keyword="nichtvorhanden") == []


def test_sorting_dated_first_then_undated(tmp_path: Path):
    store = EntryStore(tmp_path)
    store.add("Undatiert-frueh")
    store.add("Spaeter", when=_future_iso(hours=48))
    store.add("Frueher", when=_future_iso(hours=2))

    texts = [e.text for e in store.list_open()]
    assert texts == ["Frueher", "Spaeter", "Undatiert-frueh"]


def test_delete_by_id_and_by_text(tmp_path: Path):
    store = EntryStore(tmp_path)
    first = store.add("Zahnarzt morgen")
    store.add("Milch kaufen")

    removed = store.delete(first.id)
    assert removed is not None and removed.text == "Zahnarzt morgen"
    removed2 = store.delete("milch")  # case-insensitive Teilstring
    assert removed2 is not None and removed2.text == "Milch kaufen"
    assert store.list_open() == []


def test_delete_not_found_returns_none(tmp_path: Path):
    store = EntryStore(tmp_path)
    store.add("Etwas")
    assert store.delete("gibtsnicht") is None
    assert store.delete("") is None
    assert len(store.list_open()) == 1  # nichts faelschlich geloescht


# --- Papierkorb (Bestaetigungs-Diaet 14.07., Muster memory/long_term.py) ----

def test_delete_moves_entry_to_trash_and_restore_brings_it_back(tmp_path: Path):
    store = EntryStore(tmp_path)
    entry = store.add("Zahnarzt", when=_future_iso(), important=True)
    store.delete("Zahnarzt")

    assert store.list_open() == []
    assert [e.text for e in store.trash_entries()] == ["Zahnarzt"]

    restored = store.restore("zahnarzt")
    assert restored is not None and restored.text == "Zahnarzt"
    # UNVERAENDERT zurueck: gleiche id, Stern und Termin bleiben.
    assert restored.id == entry.id
    assert restored.important is True
    assert restored.when == entry.when
    assert store.trash_entries() == []
    assert [e.text for e in store.list_open()] == ["Zahnarzt"]
    # Persistenz: eine NEUE Instanz sieht den wiederhergestellten Eintrag.
    assert [e.text for e in EntryStore(tmp_path).list_open()] == ["Zahnarzt"]


def test_restore_without_text_returns_last_deleted(tmp_path: Path):
    """Undo-Geste: «stell den Eintrag wieder her» ohne Suchtext holt den
    ZULETZT geloeschten zurueck."""
    store = EntryStore(tmp_path)
    store.add("Erster")
    store.add("Zweiter")
    store.delete("Erster")
    store.delete("Zweiter")

    restored = store.restore()
    assert restored is not None and restored.text == "Zweiter"
    assert [e.text for e in store.trash_entries()] == ["Erster"]


def test_restore_not_found_returns_none(tmp_path: Path):
    store = EntryStore(tmp_path)
    assert store.restore() is None          # leerer Papierkorb
    store.add("Etwas")
    store.delete("Etwas")
    assert store.restore("gibtsnicht") is None
    assert [e.text for e in store.trash_entries()] == ["Etwas"]  # bleibt liegen


def test_trash_is_capped(tmp_path: Path):
    from memory.entries import _TRASH_CAP

    store = EntryStore(tmp_path)
    for i in range(_TRASH_CAP + 5):
        store.add(f"Eintrag {i}")
        store.delete(f"Eintrag {i}", exact=True)

    trash = store.trash_entries()
    assert len(trash) == _TRASH_CAP
    assert trash[-1].text == f"Eintrag {_TRASH_CAP + 4}"   # juengste ueberleben


def test_is_past_date_only_counts_until_end_of_day():
    today = datetime.now().strftime("%Y-%m-%d")
    assert is_past(today) is False       # heutiges Datum bleibt offen
    assert is_past("2020-01-01") is True
    assert is_past("") is False
    assert is_past("kein-datum") is False  # fail-safe: unparsebar = offen


def test_add_sets_notified_for_past_and_undated(tmp_path: Path):
    """A2 (ADR-039): nichts zu melden bei fehlendem/vergangenem when -
    rueckdatierte Merkposten (Audit-Fall) feuern NIE; Zukunft feuert."""
    store = EntryStore(tmp_path)
    assert store.add("Ohne Zeit").notified is True
    assert store.add("Vergangen", when=_past_iso()).notified is True
    assert store.add("Zukunft", when=_future_iso()).notified is False


def test_due_unnotified_and_mark_notified(tmp_path: Path):
    store = EntryStore(tmp_path)
    future = store.add("Zukunft", when=_future_iso(hours=24))
    # Faellig-aber-ungemeldet laesst sich nicht ueber add() erzeugen (das
    # markiert Vergangenes sofort) - Flag zuruecksetzen simuliert den echten
    # Ablauf: bei Anlage Zukunft, dann verstreicht die Zeit.
    due = store.add("Jetzt faellig", when=_past_iso(hours=0.01))
    data = store._read()
    for d in data:
        if d["id"] == due.id:
            d["notified"] = False
    store._write(data)

    due_list = store.due_unnotified()
    assert [e.text for e in due_list] == ["Jetzt faellig"]  # Zukunft nicht dabei

    assert store.mark_notified(due.id) is True
    assert store.due_unnotified() == []  # genau einmal
    # persistiert: neue Instanz sieht das Flag
    assert EntryStore(tmp_path).due_unnotified() == []
    assert store.mark_notified("gibtsnicht") is False
    assert future.notified is False  # unberuehrt


def test_from_dict_migration_for_a1_entries():
    """A1-Eintraege (ohne notified-Feld): Vergangenes gilt als gemeldet
    (kein Nachfeuern beim ersten Scheduler-Start), Zukunft feuert normal."""
    old_past = Entry.from_dict({"id": "a", "text": "alt", "when": "2020-01-01"})
    old_future = Entry.from_dict({"id": "b", "text": "neu", "when": "2099-01-01T09:00"})
    assert old_past.notified is True
    assert old_future.notified is False


def test_corrupt_when_entry_stays_visible(tmp_path: Path):
    # Fail-safe: ein Eintrag mit kaputtem when verschwindet nicht still.
    store = EntryStore(tmp_path)
    store.add("Kaputte Zeit", when="irgendwann naechste Woche")
    assert [e.text for e in store.list_open()] == ["Kaputte Zeit"]
