"""Tests für core/planner.py - AIEngine gemockt, es wird nur die
Splitting-Logik geprüft, kein echter API-Aufruf."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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


def test_brainstorm_opener_routes_to_chat_without_llm():
    """PO-Reibung 11.07.: 'lass uns kurz brainstormen, was der naechste Schritt
    waere' landete in plan_next_step (formelle async-Analyse, 'Bericht folgt')
    statt im Gespraech. 'brainstorm' -> chat, deterministisch vor dem LLM."""
    ai = MagicMock()
    planner = Planner(ai)

    steps = planner.plan("können wir kurz brainstormen was der nächste Schritt wäre", [])

    assert len(steps) == 1 and steps[0].intent == "chat"
    ai.get_plan.assert_not_called()          # kein LLM, keine Delegation


def test_explicit_planning_not_caught_by_brainstorm():
    """'plane den naechsten Schritt' traegt kein Brainstorm-Wort -> geht wie
    bisher zum LLM (dort ggf. plan_next_step)."""
    ai = MagicMock()
    ai.get_plan.return_value = Plan(intent="plan_next_step",
                                    raw_input="plane den nächsten Schritt")
    planner = Planner(ai)

    steps = planner.plan("plane den nächsten Schritt", [])

    ai.get_plan.assert_called()              # ging durch zum LLM
    assert steps[0].intent == "plan_next_step"


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


# --- Reasoning-Kern im Schatten (ADR-060 Scheibe 3c) ----------------------

def _shadow_ai(reasoning_shadow: bool):
    """MagicMock-AIEngine mit echter bool-Flag (statt MagicMock-Attribut, das
    truthy waere) - so ist der Opt-in-Schalter exakt kontrollierbar."""
    ai = MagicMock()
    ai.config.reasoning_shadow = reasoning_shadow
    ai.get_plan.return_value = Plan(intent="chat", raw_input="oeffne excel")
    return ai


def test_shadow_off_does_not_run_core():
    ai = _shadow_ai(reasoning_shadow=False)
    planner = Planner(ai)

    steps = planner.plan("oeffne excel", [])

    assert steps[0].intent == "chat"          # Router unveraendert
    ai.choose_tool.assert_not_called()         # Kern lief gar nicht


def test_shadow_on_logs_comparison_without_affecting_plans(caplog):
    ai = _shadow_ai(reasoning_shadow=True)
    # Der Kern (ueber ai.choose_tool) waehlt ein real registriertes Werkzeug.
    ai.choose_tool.return_value = [("open_program", {"target": "excel"})]
    planner = Planner(ai)

    with caplog.at_level("INFO", logger="jarvis.planner"):
        steps = planner.plan("oeffne excel", [])

    # Live-Pfad bleibt der Router-Plan - der Schatten aendert NICHTS daran.
    assert [s.intent for s in steps] == ["chat"]
    ai.choose_tool.assert_called_once()
    text = "\n".join(r.message for r in caplog.records)
    assert "Reasoning-Schatten" in text
    assert "router=chat" in text and "kern=open_program" in text
    assert "DIFF" in text                       # chat != open_program


def test_shadow_log_line_is_parseable_by_shadow_stats(tmp_path, caplog):
    """Contract Producer<->Consumer: die Zeile, die der Schatten TATSAECHLICH
    schreibt (core/planner), wird von core.dashboard_data.shadow_stats gelesen.
    Verhindert, dass eine spaetere Formataenderung still die Auswertung auf 0
    fallen laesst (die zwei Haelften sind sonst nur per Konvention gekoppelt)."""
    from core.dashboard_data import shadow_stats

    ai = _shadow_ai(reasoning_shadow=True)
    ai.choose_tool.return_value = [("open_program", {"target": "excel"})]
    planner = Planner(ai)
    with caplog.at_level("INFO", logger="jarvis.planner"):
        planner.plan("oeffne excel", [])

    shadow_lines = [r.getMessage() for r in caplog.records
                    if "Reasoning-Schatten" in r.getMessage()]
    assert shadow_lines, "der Schatten hat keine Logzeile erzeugt"
    (tmp_path / "2026-07-12-runtime.log").write_text(
        "\n".join(shadow_lines) + "\n", encoding="utf-8"
    )

    stats = shadow_stats(tmp_path)
    assert stats["total"] == 1
    assert stats["diff"] == 1
    assert stats["top_diffs"][0] == {"router": "chat", "kern": "open_program", "count": 1}


def test_shadow_failure_never_breaks_live_path(caplog):
    """Wirft der Kern selbst (nicht nur die Werkzeug-Wahl, die decide schon
    abfaengt), faengt der Schatten-Wrapper es ab: Live-Pfad bleibt heil,
    nur eine WARNING."""
    ai = _shadow_ai(reasoning_shadow=True)
    planner = Planner(ai)

    with patch("core.planner.reasoning.decide", side_effect=RuntimeError("kern kaputt")), \
         caplog.at_level("WARNING", logger="jarvis.planner"):
        steps = planner.plan("oeffne excel", [])

    assert steps[0].intent == "chat"            # Router liefert trotzdem
    assert any("fehlgeschlagen" in r.message for r in caplog.records)


# --- Strangler-Schalter: Kern fuehrt freigegebene Intents (ADR-060 Phase 2) --

def _routing_ai(route_intents, shadow=False, tools=(("open_program", {"target": "excel"}),)):
    """AIEngine-Attrappe mit ECHTER Config (SimpleNamespace) - fuer die
    Strangler-Schalter-Tests, die eine echte Whitelist brauchen. Router liefert
    'chat', der Kern (choose_tool) waehlt `tools` (Liste von (name, args) -
    ein oder mehrere Schritte)."""
    ai = MagicMock()
    ai.config = SimpleNamespace(
        reasoning_shadow=shadow, reasoning_route_intents=list(route_intents)
    )
    ai.get_plan.return_value = Plan(intent="chat", raw_input="x")
    ai.choose_tool.return_value = list(tools)
    return ai


def test_whitelisted_core_intent_takes_over_from_router():
    """Waehlt der Kern einen FREIGEGEBENEN Intent, uebernimmt SEIN Plan statt
    des Router-'chat'."""
    ai = _routing_ai(route_intents=["open_program"])
    steps = Planner(ai).plan("mach mir excel auf", [])

    assert len(steps) == 1
    assert steps[0].intent == "open_program"
    assert steps[0].target == "excel"


def test_routing_works_without_shadow():
    """Der Schalter haengt an der Whitelist, nicht am Schatten - Umhaengen geht
    auch mit reasoning_shadow=False (ein LLM-Call, aber kein Schatten-Log noetig)."""
    ai = _routing_ai(route_intents=["open_program"], shadow=False)
    steps = Planner(ai).plan("oeffne excel", [])

    assert steps[0].intent == "open_program"


def test_non_whitelisted_core_intent_stays_with_router():
    """Waehlt der Kern einen NICHT freigegebenen Intent, bleibt der Router
    handlungsfuehrend (Whitelist = Sicherheitsgrenze)."""
    ai = _routing_ai(route_intents=["get_weather"], tools=[("open_program", {"target": "excel"})])
    steps = Planner(ai).plan("oeffne excel", [])

    assert steps[0].intent == "chat"        # Router-Plan bleibt
    ai.choose_tool.assert_called_once()      # Kern lief, aber nicht geroutet


def test_empty_whitelist_never_routes_even_with_shadow():
    """Reiner Schatten (Whitelist leer): der Kern loggt, handelt aber nie."""
    ai = _routing_ai(route_intents=[], shadow=True, tools=[("open_program", {"target": "excel"})])
    steps = Planner(ai).plan("oeffne excel", [])

    assert steps[0].intent == "chat"


def test_routed_plan_still_passes_through_guard_disruptive():
    """Sicherheit: auch ein umgehaengter Kern-Plan laeuft durch
    _guard_disruptive - ein stop_runtime ohne echte Abschalt-Ansage wird zu
    chat (kein stiller Shutdown), selbst wenn stop_runtime freigegeben ist."""
    ai = _routing_ai(route_intents=["stop_runtime"], tools=[("stop_runtime", {})])
    steps = Planner(ai).plan("zeig mir die lage", [])

    assert steps[0].intent == "chat"


def test_multistep_routes_to_core_when_all_whitelisted():
    """ADR-064: Multi-Step wandert JETZT zum Kern, wenn ALLE Schritte freigegeben
    sind. Die frueher leeren Parallel-Args waren strukturell (generisches Schema);
    typisierte Pro-Werkzeug-Schemas (core/tool_params) fuellen sie zuverlaessig
    (Eval 2026-07-12: 24/24)."""
    ai = _routing_ai(
        route_intents=["get_weather", "get_news"],
        tools=[("get_weather", {"target": "Berlin"}), ("get_news", {})],
    )
    steps = Planner(ai).plan("wetter in berlin und die news", [])

    assert [s.intent for s in steps] == ["get_weather", "get_news"]   # Kern, nicht Router-Split
    assert steps[0].target == "Berlin"


def test_multistep_with_one_non_whitelisted_step_stays_with_router():
    """Sicherheitsgrenze (ADR-064): ist auch nur EIN Schritt nicht freigegeben,
    faellt die GANZE Eingabe auf den Router-Split zurueck - nie wandert ein
    gemischtes Buendel ueber den Kern."""
    ai = _routing_ai(
        route_intents=["get_weather"],   # get_news NICHT freigegeben
        tools=[("get_weather", {"target": "Berlin"}), ("get_news", {})],
    )
    steps = Planner(ai).plan("wetter in berlin und die news", [])

    assert [s.intent for s in steps] == ["chat", "chat"]   # Router-Split (Mock)


def test_single_whitelisted_step_still_routes_to_core():
    """Gegenprobe: der zuverlaessige EINZELschritt-Fall wandert weiterhin zum
    Kern (das ist der 95%-Alltag)."""
    ai = _routing_ai(route_intents=["get_weather"], tools=[("get_weather", {"target": "Berlin"})])
    steps = Planner(ai).plan("wie ist das wetter in berlin", [])

    assert [s.intent for s in steps] == ["get_weather"]
    assert steps[0].target == "Berlin"


def test_core_off_by_default_matches_router_exactly():
    """Weder Schatten noch Whitelist: der Kern laeuft gar nicht (kein
    choose_tool-Call), Verhalten exakt wie heute."""
    ai = _routing_ai(route_intents=[], shadow=False)
    steps = Planner(ai).plan("oeffne excel", [])

    assert steps[0].intent == "chat"
    ai.choose_tool.assert_not_called()


# --- Parallel-Planung (Latenz-Trio A2, 13.07.2026) -------------------------

def test_router_and_core_run_in_parallel():
    """Latenz-Fix: Router und Kern ueberlappen. Der Router-Fake WARTET auf den
    Kern-Start - im alten seriellen Code (Router zuerst, Kern danach) liefe er
    in den Timeout; parallel setzt der Kern das Signal, waehrend der Router
    laeuft."""
    import threading

    core_started = threading.Event()
    router_saw_core: list[bool] = []

    ai = _routing_ai(route_intents=["open_program"])

    def waiting_get_plan(user_input, history):
        router_saw_core.append(core_started.wait(timeout=5))
        return Plan(intent="chat", raw_input=user_input)

    def signalling_choose_tool(*args, **kwargs):
        core_started.set()
        return [("open_program", {"target": "excel"})]

    ai.get_plan.side_effect = waiting_get_plan
    ai.choose_tool.side_effect = signalling_choose_tool

    steps = Planner(ai).plan("mach mir excel auf", [])

    assert router_saw_core == [True]          # Router sah den Kern LAUFEN
    assert [s.intent for s in steps] == ["open_program"]  # Uebernahme unveraendert


def test_router_error_still_propagates_with_parallel_core():
    """Semantik-Erhalt: wirft der Router, propagiert seine Exception wie im
    seriellen Code - der parallel gelaufene Kern aendert daran nichts."""
    import pytest

    ai = _routing_ai(route_intents=["open_program"])
    ai.get_plan.side_effect = RuntimeError("router kaputt")

    with pytest.raises(RuntimeError, match="router kaputt"):
        Planner(ai).plan("mach mir excel auf", [])


def test_core_error_in_parallel_path_keeps_router_result(caplog):
    """Fail-safe unveraendert: wirft der Kern im Parallel-Pfad, liefert der
    Router - nur eine WARNING."""
    ai = _routing_ai(route_intents=["open_program"])
    ai.get_plan.side_effect = None
    ai.get_plan.return_value = Plan(intent="chat", raw_input="x")

    with patch("core.planner.reasoning.decide", side_effect=RuntimeError("kern kaputt")), \
         caplog.at_level("WARNING", logger="jarvis.planner"):
        steps = Planner(ai).plan("oeffne excel", [])

    assert [s.intent for s in steps] == ["chat"]
    assert any("fehlgeschlagen" in r.message for r in caplog.records)
