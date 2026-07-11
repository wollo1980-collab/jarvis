"""Tests für core/planner.py - AIEngine gemockt, es wird nur die
Splitting-Logik geprüft, kein echter API-Aufruf."""
from __future__ import annotations

from unittest.mock import MagicMock

from core.models import Message, Plan
from core.planner import Planner, _dismiss_proposal_plan, _guard_disruptive

_IDEAS_REPLY = (
    "Ein paar Gedanken, Sir:\n"
    "1. Lass uns eine Systemdiagnose machen. Sag einfach: „Zeig mir den Systemstatus.“\n"
    "2. Jarvis kann alte Temporärdateien analysieren, ohne was zu löschen. "
    "Sag einfach: „Analysiere meine Temp-Dateien.“\n"
    "3. Wir könnten ein neues Software-Projekt vorbereiten. Sag einfach: „Starte ein neues Projekt.“\n\n"
    "Soll ich eine davon vertiefen? Sag einfach: recherchier Idee 2."
)


def test_plan_single_step_passthrough():
    ai = MagicMock()
    ai.get_plan.return_value = Plan(intent="chat", raw_input="wie spät ist es")
    planner = Planner(ai)

    steps = planner.plan("wie spät ist es", [])

    assert len(steps) == 1
    ai.get_plan.assert_called_once_with("wie spät ist es", [])


def test_plan_splits_on_und():
    ai = MagicMock()
    ai.get_plan.side_effect = lambda text, history: Plan(intent="chat", raw_input=text)
    planner = Planner(ai)

    steps = planner.plan("öffne excel und schreibe eine notiz", [])

    assert [s.raw_input for s in steps] == ["öffne excel", "schreibe eine notiz"]


def test_plan_splits_on_und_dann_not_double_split():
    ai = MagicMock()
    ai.get_plan.side_effect = lambda text, history: Plan(intent="chat", raw_input=text)
    planner = Planner(ai)

    steps = planner.plan("öffne excel und dann schließe den browser", [])

    assert [s.raw_input for s in steps] == ["öffne excel", "schließe den browser"]


def test_plan_splits_on_semicolon():
    ai = MagicMock()
    ai.get_plan.side_effect = lambda text, history: Plan(intent="chat", raw_input=text)
    planner = Planner(ai)

    steps = planner.plan("mach a; mach b", [])

    assert [s.raw_input for s in steps] == ["mach a", "mach b"]


def test_plan_preserves_order():
    ai = MagicMock()
    calls = []

    def fake_get_plan(text, history):
        calls.append(text)
        return Plan(intent="chat", raw_input=text)

    ai.get_plan.side_effect = fake_get_plan
    planner = Planner(ai)

    planner.plan("erst a und dann b und dann c", [])

    assert calls == ["erst a", "b", "c"]


def test_colon_payload_is_never_split():
    """Live-Befund 2026-07-10 (AP1-Auftrag): 'Erledige in jkc: ... title und
    body ... anlegen und auflisten' wurde an jedem 'und' zerhackt - jeder
    Fetzen ein eigener delegate_work-Schritt mit Fragment-Spezifikation.
    Ein ':' markiert 'Befehl: Nutzlast' - die Nutzlast bleibt EIN Schritt."""
    from unittest.mock import MagicMock

    from core.planner import Planner

    ai = MagicMock()
    ai.get_plan.side_effect = lambda text, history: Plan(intent="delegate_work", raw_input=text)
    planner = Planner(ai)

    text = "Erledige in jkc: Index ueber title und body anlegen und Tests schreiben; danach Doku."
    steps = planner.plan(text, history=[])

    assert len(steps) == 1
    assert steps[0].raw_input == text  # Wortlaut ungeteilt beim einen Schritt


def test_idea_deepening_builds_search_web_without_llm():
    """Live-Befund 11.07. nachts (zweimal!): das LLM führte bei
    'recherchier Idee 2' den in der Idee genannten Befehl aus statt zu
    recherchieren. Deshalb deterministisch VOR dem LLM: search_web mit
    dem Idee-Wortlaut (ohne den 'Sag einfach:'-Schwanz) als Thema."""
    ai = MagicMock()
    planner = Planner(ai)
    history = [
        Message(role="user", content="was koennten wir machen?"),
        Message(role="assistant", content=_IDEAS_REPLY),
    ]

    steps = planner.plan("recherchier Idee 2", history)

    assert len(steps) == 1
    assert steps[0].intent == "search_web"
    assert "Temporärdateien" in steps[0].target
    assert "Sag einfach" not in steps[0].target
    ai.get_plan.assert_not_called()


def test_idea_deepening_variants_and_latest_list_wins():
    ai = MagicMock()
    planner = Planner(ai)
    old = Message(role="assistant", content="1. Alte Idee von gestern. Sag einfach: „Egal.“")
    history = [old, Message(role="assistant", content=_IDEAS_REPLY)]

    steps = planner.plan("vertief bitte Nummer 1", history)

    assert steps[0].intent == "search_web"
    assert "Systemdiagnose" in steps[0].target  # jüngste Liste, nicht die alte


def test_idea_deepening_ignores_newer_non_ideas_numbered_message():
    """Audit-Fund 1 (11.07.2026): News/Listen/Wochen-Rueckblick erzeugen
    dasselbe '1. ...'-Format. Eine solche Nachricht NACH der Ideenliste darf
    die Vertiefung NICHT kapern - nur die echte Ideen-Antwort (Signatur
    'recherchier Idee') zaehlt, sonst wuerde das falsche Thema recherchiert."""
    ai = MagicMock()
    planner = Planner(ai)
    news_reply = (
        "Die Lage, Sir:\n"
        "1. Gespräche zwischen USA und Iran\n"
        "2. Neues Bundespolizeigesetz\n"
        "3. Stabile Krankenkassenbeiträge"
    )
    history = [
        Message(role="user", content="was koennten wir machen?"),
        Message(role="assistant", content=_IDEAS_REPLY),   # Ideen (mit Signatur)
        Message(role="user", content="und die lage?"),
        Message(role="assistant", content=news_reply),      # NEUER, aber keine Ideen
    ]

    steps = planner.plan("recherchier Idee 2", history)

    # Muss die IDEE (Temp-Dateien) treffen, NICHT die News-Nummer 2.
    assert steps[0].intent == "search_web"
    assert "Temporärdateien" in steps[0].target
    assert "Bundespolizeigesetz" not in steps[0].target
    ai.get_plan.assert_not_called()


def test_idea_deepening_falls_through_without_numbered_history():
    ai = MagicMock()
    ai.get_plan.return_value = Plan(intent="chat", raw_input="recherchier Idee 2")
    planner = Planner(ai)

    steps = planner.plan("recherchier Idee 2", [Message(role="assistant", content="Gern, Sir.")])

    assert steps[0].intent == "chat"
    ai.get_plan.assert_called_once()


def test_idea_deepening_unknown_number_falls_through():
    ai = MagicMock()
    ai.get_plan.return_value = Plan(intent="chat", raw_input="recherchier Idee 9")
    planner = Planner(ai)
    history = [Message(role="assistant", content=_IDEAS_REPLY)]

    steps = planner.plan("recherchier Idee 9", history)

    assert steps[0].intent == "chat"
    ai.get_plan.assert_called_once()


# --- Vorschlag verwerfen + Fehlrouting-Schutz (PO-Reibung 2026-07-11) --------

def test_dismiss_proposal_plan_recognizes_discard_phrasings():
    for text in ("Deinen Entwurf verwerfen", "verwirf den Vorschlag",
                 "lehn den Entwurf ab", "weg mit dem Vorschlag",
                 "die Empfehlung brauchen wir nicht, verwirf sie"):
        plan = _dismiss_proposal_plan(text)
        assert plan is not None and plan.intent == "dismiss_proposal", text


def test_dismiss_proposal_plan_ignores_unrelated():
    # Kein Vorschlags-Objekt / anderes Loeschen -> nicht kapern.
    assert _dismiss_proposal_plan("lösch die Einkaufsliste") is None
    assert _dismiss_proposal_plan("vergiss dass ich Kaffee mag") is None
    assert _dismiss_proposal_plan("verwirf das") is None
    assert _dismiss_proposal_plan("wie wird das Wetter?") is None


def test_planner_routes_entwurf_verwerfen_to_dismiss_not_shutdown():
    """Der Kernfall: 'Deinen Entwurf verwerfen' geht deterministisch an
    dismiss_proposal - NIE mehr ans (stille) Herunterfahren."""
    ai = MagicMock()
    planner = Planner(ai)

    steps = planner.plan("Deinen Entwurf verwerfen", [])

    assert len(steps) == 1 and steps[0].intent == "dismiss_proposal"
    ai.get_plan.assert_not_called()


def test_guard_downgrades_stray_stop_runtime_to_chat():
    """stop_runtime ohne echte Abschalt-Formulierung = fast sicher ein
    Fehlrouting -> chat (kein stiller Shutdown)."""
    stray = Plan(intent="stop_runtime", raw_input="mach die Kacheln bunt")
    assert _guard_disruptive(stray).intent == "chat"


def test_guard_allows_real_shutdown_phrases():
    for phrase in ("beende dich", "fahr dich runter", "stell dich ab",
                   "jarvis herunterfahren", "schalt dich aus"):
        p = Plan(intent="stop_runtime", raw_input=phrase)
        assert _guard_disruptive(p).intent == "stop_runtime", phrase


def test_guard_leaves_other_intents_untouched():
    p = Plan(intent="get_weather", raw_input="wie wird das wetter")
    assert _guard_disruptive(p) is p


def test_planner_guards_llm_stop_runtime_misroute():
    """Wenn das LLM eine harmlose Eingabe faelschlich als stop_runtime deutet,
    faengt der Planner-Guard es ab (Eingabe traegt keine Abschalt-Ansage)."""
    ai = MagicMock()
    ai.get_plan.return_value = Plan(intent="stop_runtime", raw_input="zeig mir die Lage")
    planner = Planner(ai)

    steps = planner.plan("zeig mir die Lage", [])

    assert steps[0].intent == "chat"
