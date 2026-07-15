"""Deterministisches Undo bei nacktem «nein» nach einer umkehrbaren Tat
(Live-Befund 15.07.: auf «nein» nach «Vermerkt, Sir» BEHAUPTETE der Chat eine
Loeschung, die nie lief - der Eintrag blieb im Gedaechtnis). Jetzt loescht
ein echtes Werkzeug, die Antwort ist die ehrliche Werkzeug-Antwort."""
from __future__ import annotations

from pathlib import Path

from core.config import Config
from core.models import Plan
from jarvis_runtime import JarvisRuntime
from memory.entries import EntryStore


class ScriptedAI:
    """FakeAI: liefert je Eingabe den passenden Plan; wirft bei «nein»,
    um zu BEWEISEN, dass das Undo den Planner nie erreicht."""

    def get_plan(self, user_input, history):
        text = user_input.lower()
        assert "nein" != text.strip(), "nacktes «nein» darf den Planner nie erreichen"
        if "erinnere" in text or "vormerken" in text:
            return Plan(intent="add_entry", parameters={"text": "Bau-Vormerkung"},
                        raw_input=user_input)
        if "merk dir" in text:
            return Plan(intent="remember_fact", target="ich trinke Kaffee schwarz",
                        raw_input=user_input)
        return Plan(intent="chat", raw_input=user_input)

    def answer(self, user_input, history, long_term_summary=""):
        return "Antwort."


def _runtime(tmp_path: Path) -> JarvisRuntime:
    memory_dir = tmp_path / "memory_data"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs").mkdir(exist_ok=True)
    config = Config(memory_dir=memory_dir, log_dir=tmp_path / "logs",
                    max_history_entries=20)
    return JarvisRuntime(config, ai=ScriptedAI())


def test_bare_nein_after_add_entry_really_deletes(tmp_path):
    runtime = _runtime(tmp_path)
    replies: list[str] = []
    runtime._process_inner("bitte vormerken", replies.append, source="browser")
    store = EntryStore(tmp_path / "memory_data")
    assert [e.text for e in store.list_open()] == ["Bau-Vormerkung"]

    runtime._process_inner("nein", replies.append, source="browser")

    # WIRKLICH geloescht (Papierkorb faengt es) - und die Antwort ist die
    # ehrliche Werkzeug-Antwort, kein behaupteter Vollzug.
    assert store.list_open() == []
    assert [e.text for e in store.trash_entries()] == ["Bau-Vormerkung"]
    assert "gestrichen" in replies[-1].lower()
    assert "stell den eintrag wieder her" in replies[-1].lower()


def test_bare_nein_after_remember_fact_really_forgets(tmp_path):
    from memory.long_term import LongTermMemory

    runtime = _runtime(tmp_path)
    replies: list[str] = []
    runtime._process_inner("merk dir das", replies.append, source="browser")
    memory = LongTermMemory(tmp_path / "memory_data")
    assert len(memory.all_facts()) == 1

    runtime._process_inner("nein", replies.append, source="browser")

    assert memory.all_facts() == []
    assert "nicht mehr" in replies[-1] or "entfernt" in replies[-1]


def test_undo_is_channel_bound_and_single_use(tmp_path):
    runtime = _runtime(tmp_path)
    replies: list[str] = []
    runtime._process_inner("bitte vormerken", replies.append, source="browser")
    store = EntryStore(tmp_path / "memory_data")

    # Fremder Kanal: kein Undo - Nachricht laeuft normal (Planner wird
    # gerufen; ScriptedAI wirft bei nacktem «nein», also via Umweg pruefen).
    runtime._last_undoable["source"] = "telegram"
    try:
        runtime._process_inner("nein", replies.append, source="browser")
        raise AssertionError("haette den Planner erreichen muessen (Kanal-Bindung)")
    except AssertionError as err:
        if "Kanal-Bindung" in str(err):
            raise
    assert [e.text for e in store.list_open()] == ["Bau-Vormerkung"]  # nichts geloescht
    # Der Merker ist nach dem Versuch verbraucht (einmalig):
    assert runtime._last_undoable is None


def test_other_messages_do_not_trigger_undo(tmp_path):
    runtime = _runtime(tmp_path)
    replies: list[str] = []
    runtime._process_inner("bitte vormerken", replies.append, source="browser")
    store = EntryStore(tmp_path / "memory_data")

    runtime._process_inner("wie geht es dir?", replies.append, source="browser")

    assert [e.text for e in store.list_open()] == ["Bau-Vormerkung"]  # bleibt
    assert runtime._last_undoable is None      # neue Tat/Antwort loescht den Merker


def test_note_undoable_ignores_multistep(tmp_path):
    from core.models import Result, Status

    runtime = _runtime(tmp_path)
    ok = Result(status=Status.SUCCESS, message="x", data={"id": "abc"})
    runtime._note_undoable([Plan(intent="add_entry"), Plan(intent="get_weather")],
                           [ok, ok], "browser")
    assert runtime._last_undoable is None      # nie raten, was gemeint ist
