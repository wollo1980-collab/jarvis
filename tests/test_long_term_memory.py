"""Tests für memory/long_term.py - arbeitet auf tmp_path, keine
Berührung des echten memory_data-Ordners."""
from __future__ import annotations

from pathlib import Path

from memory.long_term import LongTermMemory


def test_creates_default_file(tmp_path: Path):
    LongTermMemory(tmp_path)
    assert (tmp_path / "long_term.json").exists()


def test_remember_and_list_roundtrip(tmp_path: Path):
    store = LongTermMemory(tmp_path)
    store.remember("arbeitet an Jarvis", category="projekt")
    store.remember("macht montags Reports", category="gewohnheit")

    facts = store.all_facts()
    assert [f.text for f in facts] == ["arbeitet an Jarvis", "macht montags Reports"]
    assert [f.category for f in facts] == ["projekt", "gewohnheit"]


def test_remember_persists_after_reload(tmp_path: Path):
    store_a = LongTermMemory(tmp_path)
    store_a.remember("mag trockenen Humor", category="praeferenz")

    store_b = LongTermMemory(tmp_path)
    facts = store_b.all_facts()
    assert [f.text for f in facts] == ["mag trockenen Humor"]


def test_unknown_category_falls_back_to_allgemein(tmp_path: Path):
    store = LongTermMemory(tmp_path)
    store.remember("irgendwas", category="nicht_vorgesehen")

    facts = store.all_facts()
    assert facts[0].category == "allgemein"


# --- Papierkorb + Wiederherstellen (Kundenreview 13.07.) -------------------

def test_forget_moves_to_trash_and_restore_brings_back(tmp_path: Path):
    """'✕ = sofort weg' war fuer persoenliche Daten zu riskant: Vergessen
    landet im Papierkorb, restore() holt es zurueck - inkl. Kategorie."""
    store = LongTermMemory(tmp_path)
    store.remember("trinkt Kaffee schwarz", category="praeferenz")

    assert store.forget("kaffee") is True
    assert store.all_facts() == []
    assert [f.text for f in store.trash_facts()] == ["trinkt Kaffee schwarz"]

    restored = store.restore("kaffee")
    assert restored is not None and restored.category == "praeferenz"
    assert [f.text for f in store.all_facts()] == ["trinkt Kaffee schwarz"]
    assert store.trash_facts() == []


def test_restore_without_text_takes_most_recent(tmp_path: Path):
    """Undo-Geste: 'stell den Fakt wieder her' ohne Angabe = der zuletzt
    geloeschte."""
    store = LongTermMemory(tmp_path)
    store.remember("Fakt eins")
    store.remember("Fakt zwei")
    store.forget("eins")
    store.forget("zwei")

    restored = store.restore("")
    assert restored is not None and restored.text == "Fakt zwei"
    assert store.restore("gibtsnicht") is None


def test_dedupe_semantic_moves_twins_to_trash_keeps_oldest(tmp_path: Path):
    """Kundenreview 13.07.: dieselbe Praeferenz dreimal im Profil. Sinngleiche
    Fakten (Kosinus >= Schwelle) wandern in den Papierkorb, der AELTESTE
    bleibt; eine spezifischere Kategorie wird angehoben. Fake-Embedding:
    gleicher Vektor = sinngleich."""
    store = LongTermMemory(tmp_path)
    store.remember("trinkt Kaffee schwarz", category="allgemein")
    store.remember("mag seinen Kaffee schwarz", category="praeferenz")
    store.remember("wohnt in Musterstadt", category="allgemein")

    vectors = {"trinkt Kaffee schwarz": [1.0, 0.0], "mag seinen Kaffee schwarz": [1.0, 0.0],
               "wohnt in Musterstadt": [0.0, 1.0]}
    moved = store.dedupe_semantic(lambda texts: [vectors[t] for t in texts])

    assert moved == [("trinkt Kaffee schwarz", "mag seinen Kaffee schwarz")]
    facts = store.all_facts()
    assert [f.text for f in facts] == ["trinkt Kaffee schwarz", "wohnt in Musterstadt"]
    assert facts[0].category == "praeferenz"          # Kategorie angehoben
    assert [f.text for f in store.trash_facts()] == ["mag seinen Kaffee schwarz"]


def test_dedupe_semantic_fails_open_on_embedding_error(tmp_path: Path):
    store = LongTermMemory(tmp_path)
    store.remember("Fakt eins")
    store.remember("Fakt zwei")

    def broken(texts):
        raise RuntimeError("kein Netz")

    assert store.dedupe_semantic(broken) == []
    assert len(store.all_facts()) == 2                # nichts angefasst


def test_forget_removes_matching_fact(tmp_path: Path):
    store = LongTermMemory(tmp_path)
    store.remember("macht montags Reports", category="gewohnheit")

    removed = store.forget("montags Reports")

    assert removed is True
    assert store.all_facts() == []


def test_forget_returns_false_when_nothing_matches(tmp_path: Path):
    store = LongTermMemory(tmp_path)
    store.remember("macht montags Reports", category="gewohnheit")

    removed = store.forget("nichts passt hier")

    assert removed is False
    assert len(store.all_facts()) == 1


def test_remember_dedups_same_text_same_category(tmp_path: Path):
    """PO-Reibung 12.07.: derselbe Fakt darf nicht mehrfach in der Ablage
    landen. Zweiter Aufruf mit gleichem Text -> kein Duplikat."""
    store = LongTermMemory(tmp_path)
    store.remember("mag mehr Kontext in Antworten", category="praeferenz")
    store.remember("Mag mehr  Kontext in Antworten", category="praeferenz")  # Casing/Whitespace egal

    facts = store.all_facts()
    assert len(facts) == 1


def test_remember_dedups_across_categories_and_upgrades(tmp_path: Path):
    """Der Kernfall aus dem Log: erst 'allgemein', dann 'gewohnheit' fuer
    denselben Fakt -> EIN Eintrag, Kategorie auf die spezifischere angehoben
    (statt '1x Allgemein, 1x Gewohnheit')."""
    store = LongTermMemory(tmp_path)
    store.remember("stellt bei Unsicherheit Rueckfragen")               # -> allgemein
    store.remember("stellt bei Unsicherheit Rueckfragen", category="gewohnheit")

    facts = store.all_facts()
    assert len(facts) == 1
    assert facts[0].category == "gewohnheit"


def test_remember_specific_category_not_downgraded_by_allgemein(tmp_path: Path):
    """Umgekehrt: eine bereits spezifische Kategorie wird durch einen spaeteren
    'allgemein'-Aufruf NICHT verwaessert."""
    store = LongTermMemory(tmp_path)
    store.remember("wohnt in Musterstadt", category="praeferenz")
    store.remember("wohnt in Musterstadt")  # allgemein

    facts = store.all_facts()
    assert len(facts) == 1
    assert facts[0].category == "praeferenz"


def test_summary_text_empty_when_no_facts(tmp_path: Path):
    store = LongTermMemory(tmp_path)
    assert store.summary_text() == ""


def test_summary_text_lists_all_facts(tmp_path: Path):
    store = LongTermMemory(tmp_path)
    store.remember("arbeitet an Jarvis", category="projekt")
    store.remember("mag trockenen Humor", category="praeferenz")

    summary = store.summary_text()

    assert "(projekt) arbeitet an Jarvis" in summary
    assert "(praeferenz) mag trockenen Humor" in summary


def test_summary_text_respects_max_facts(tmp_path: Path):
    store = LongTermMemory(tmp_path)
    for i in range(5):
        store.remember(f"fakt {i}")

    summary = store.summary_text(max_facts=2)

    assert "fakt 3" in summary
    assert "fakt 4" in summary
    assert "fakt 0" not in summary
