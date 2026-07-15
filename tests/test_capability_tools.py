"""Tests fuer die Bereichs-Struktur (core/capability_tools.py, ADR-072/073)
und das Fassaden-MESS-Werkzeug (scripts/facade_eval.py, ADR-073 Punkt 4).

Der Vollstaendigkeits-Waechter bewacht die PRODUKTION (TOOL_DOMAINS als
Organisations-/Sicherheitsebene); die Wahl-Tests bewachen das Messinstrument,
damit ein kuenftiger staerkerer API-Waehler dieselbe Messlatte vorfindet."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import commands
from core.capability_tools import TOOL_DOMAINS, intent_to_tool

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "facade_eval", _ROOT / "scripts" / "facade_eval.py"
)
facade_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(facade_eval)


def test_every_registry_intent_belongs_to_exactly_one_tool():
    """Drift-Waechter: ein neuer Command ohne Bereichs-Zuordnung (oder eine
    Doppel-Zuordnung) laesst die Suite durchfallen - nie wieder 'Befehl 67'
    ohne Zuhause."""
    mapping = intent_to_tool()
    all_assigned = [i for _, (_d, intents) in TOOL_DOMAINS.items() for i in intents]

    assert len(all_assigned) == len(set(all_assigned)), "Intent doppelt zugeordnet"
    missing = sorted(set(commands.REGISTRY) - set(mapping))
    assert not missing, f"Intents ohne Werkzeug-Bereich: {missing}"
    ghosts = sorted(set(mapping) - set(commands.REGISTRY))
    assert not ghosts, f"Zugeordnete, aber nicht registrierte Intents: {ghosts}"


def test_facade_choice_code_stays_out_of_production():
    """ADR-073 Punkt 4: der verworfene Wahl-Pfad lebt NUR im Eval-Bereich.
    Kehrt er nach core/ zurueck (oder kommt das Flag wieder), bricht dieser
    Test - genau die Wiedereinbau-Gefahr, vor der das Review warnt."""
    core_src = (_ROOT / "core" / "capability_tools.py").read_text(encoding="utf-8")
    for symbol in ("build_capability_schemas", "two_stage_choose", "def to_legacy_choices"):
        assert symbol not in core_src, f"{symbol} gehoert nach scripts/facade_eval.py"
    reasoning_src = (_ROOT / "core" / "reasoning.py").read_text(encoding="utf-8")
    assert "capability" not in reasoning_src
    config_src = (_ROOT / "core" / "config.py").read_text(encoding="utf-8")
    assert "capability_tools_enabled" not in config_src


def test_schemas_are_eight_wellformed_and_much_smaller():
    schemas = facade_eval.build_capability_schemas()

    assert len(schemas) == 8
    for s in schemas:
        fn = s["function"]
        assert fn["parameters"]["required"] == ["aktion"]
        assert fn["parameters"]["additionalProperties"] is False
        enum = fn["parameters"]["properties"]["aktion"]["enum"]
        assert enum == list(TOOL_DOMAINS[fn["name"]][1])
        assert "Aktionen:" in fn["description"]

    # Messbarer Kern des (verworfenen) Umbaus bleibt pruefbar: der Katalog
    # schrumpft DEUTLICH (<45 % des flachen Katalogs).
    import json

    from core.tool_schemas import build_tool_schemas

    facade_size = len(json.dumps(schemas, ensure_ascii=False))
    legacy_size = len(json.dumps(build_tool_schemas(), ensure_ascii=False))
    assert facade_size < legacy_size * 0.45, (facade_size, legacy_size)


def test_to_legacy_choices_maps_and_fails_safe():
    out = facade_eval.to_legacy_choices([
        ("termine", {"aktion": "calendar_add_event", "subject": "Zahnarzt", "day": "morgen"}),
        ("welt", {"aktion": "get_weather", "target": "Musterstadt"}),
        ("welt", {"aktion": "shutdown_pc"}),          # fremde aktion -> skip
        ("quatsch", {"aktion": "get_news"}),           # unbekanntes Tool -> skip
        ("get_news", {}),                              # Legacy-Durchreiche bleibt gueltig
        ("termine", {}),                               # aktion fehlt -> skip
    ])

    assert out == [
        ("calendar_add_event", {"subject": "Zahnarzt", "day": "morgen"}),
        ("get_weather", {"target": "Musterstadt"}),
        ("get_news", {}),
    ]


def test_two_stage_choose_shapes_and_result():
    """Zwei-Stufen-Wahl (Messrunde 3): Stufe 1 sieht NUR die acht Bereiche
    (ohne Argumente), Stufe 2 NUR die flachen Aktionen des gewaehlten
    Bereichs - heraus kommen Legacy-Wahlen wie im flachen Pfad."""
    seen: list[list[str]] = []

    def fake_caller(user_input, history, tools):
        names = [t["function"]["name"] for t in tools]
        seen.append(names)
        if len(seen) == 1:                             # Stufe 1: Bereichs-Wahl
            assert len(names) == 8
            assert "aktion" not in str(tools)          # keine Verschachtelung
            return [("termine", {})]
        # Stufe 2: flaches Menue NUR aus termine-Aktionen, typisiert
        assert set(names) == set(TOOL_DOMAINS["termine"][1])
        return [("add_entry", {"text": "Zahnarzt", "when": "2099-07-15T09:00"})]

    choices = facade_eval.two_stage_choose("erinnere mich", [], fake_caller)

    assert len(seen) == 2                              # genau zwei kleine Calls
    assert choices == [("add_entry", {"text": "Zahnarzt", "when": "2099-07-15T09:00"})]


def test_two_stage_choose_multi_domain_and_failsafe():
    """Mehrere Bereiche laufen alle (gedeckelt); ein kaputter Bereich kippt
    die anderen nicht; bereichsfremde Stufe-2-Wahlen werden verworfen."""
    def fake_caller(user_input, history, tools):
        names = [t["function"]["name"] for t in tools]
        if "wissen" in names and "termine" in names:   # Stufe 1
            return [("welt", {}), ("computer", {}), ("quatsch", {})]
        if "get_weather" in names:                     # Stufe 2 welt
            return [("get_weather", {"target": "Musterstadt"}),
                    ("shutdown_pc", {})]               # fremd -> verworfen
        raise RuntimeError("computer-Stufe kaputt")    # Stufe 2 computer

    out = facade_eval.two_stage_choose("wetter und musik", [], fake_caller)

    assert out == [("get_weather", {"target": "Musterstadt"})]


def test_two_stage_choose_empty_stage1_means_chat():
    assert facade_eval.two_stage_choose("na du", [], lambda u, h, t: []) == []
