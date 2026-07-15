"""Tests fuer core/tool_schemas.py (ADR-060, Phase 1 Scheibe 1) - die Registry
wird verlustfrei und im gueltigen Function-Calling-Format zu Werkzeugen."""
from __future__ import annotations

import re

from commands import REGISTRY
from core.tool_schemas import build_tool_schemas, tool_names

_OPENAI_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def test_one_tool_per_registry_command():
    schemas = build_tool_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert names == sorted(REGISTRY)          # genau die Registry, nichts erfunden/verloren
    assert tool_names() == sorted(REGISTRY)


def test_schema_shape_is_valid_function_calling():
    from core.tool_params import PARAM_SCHEMAS

    for s in build_tool_schemas():
        assert s["type"] == "function"
        fn = s["function"]
        assert _OPENAI_NAME_RE.match(fn["name"])     # OpenAI-Namensregel
        assert fn["description"].strip()             # nie leer (Name als Rueckfall)
        params = fn["parameters"]
        assert params["type"] == "object"
        if fn["name"] in PARAM_SCHEMAS:
            # ADR-064: typisiert - echte Felder, additionalProperties False
            assert set(params["properties"]) == set(PARAM_SCHEMAS[fn["name"]]["properties"])
            assert params["additionalProperties"] is False
        else:
            # generischer Rueckfall {target, parameters}
            assert set(params["properties"]) == {"target", "parameters"}
            assert params["properties"]["parameters"]["type"] == "object"


def test_typed_param_schemas_only_reference_real_intents():
    """Contract (ADR-064): jeder Schluessel in PARAM_SCHEMAS ist ein registrierter
    Intent - kein zweiter, driftender Katalog neben der Registry."""
    from core.tool_params import PARAM_SCHEMAS

    assert set(PARAM_SCHEMAS) <= set(REGISTRY)


def test_typed_tool_renders_its_real_fields():
    """add_to_list bekommt ein typisiertes 'items'-Array - der Enabler dafuer,
    dass 'Milch und Brot' parallel als ['Milch','Brot'] ankommt (ADR-064)."""
    schemas = {s["function"]["name"]: s["function"]["parameters"] for s in build_tool_schemas()}
    add = schemas["add_to_list"]
    assert add["properties"]["items"]["type"] == "array"
    assert "items" in add["required"]


def test_descriptions_come_from_registry():
    """Die Werkzeug-Beschreibung ist die Befehls-`description` - EINE Quelle,
    kein zweiter Katalog, der driften kann."""
    schemas = {s["function"]["name"]: s["function"]["description"] for s in build_tool_schemas()}
    for name, cmd in REGISTRY.items():
        expected = (getattr(cmd, "description", "") or name).strip()
        assert schemas[name] == expected


def test_known_commands_are_present_and_chat_is_not():
    names = set(tool_names())
    # Ein paar echte Werkzeuge sind da ...
    assert {"get_weather", "search_web", "build_project", "spotify_play"} <= names
    # ... aber 'chat' ist KEIN Werkzeug (kein Werkzeug-Aufruf = Gespraech).
    assert "chat" not in names
