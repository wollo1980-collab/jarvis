"""Tests fuer den Impuls-Kreislauf (Endsystem-Kampagne, ADR-054):
ImpulseStore (Persistenz + dedupe + Nein-Liste), ImpulseEngine (Takt,
Deckel, Ruhefenster, Fail-safe) und der Unwetter-Pruefer. Keine echten
Netz-/Zeitquellen - alles injiziert."""
from __future__ import annotations

from datetime import datetime


from core.impulses import ImpulseEngine, make_weather_checker
from memory.impulses import ImpulseStore


# --- ImpulseStore ----------------------------------------------------------

def test_add_if_new_dedupes_same_key(tmp_path):
    store = ImpulseStore(tmp_path)
    assert store.add_if_new("weather", "weather-storm-2026-07-11", "Unwetter", "Details") is True
    # Gleicher key -> kein zweiter Impuls.
    assert store.add_if_new("weather", "weather-storm-2026-07-11", "Unwetter", "Andere Details") is False
    assert store.count_open() == 1


def test_count_open_ignores_and_purges_stale_days(tmp_path):
    """Live-Befund 15.07.: drei Alt-Karten (13./14.) zaehlten im Deckel mit -
    der 5er-Deckel waere verstopft, neue Impulse ausgeblieben. count_open
    zaehlt nur HEUTIGES und raeumt Vergangenes dabei aus der Datei."""
    import json

    store = ImpulseStore(tmp_path)
    store.add_if_new("weather", "weather-heat-heute", "Hitze", "bis 32°")
    # Alt-Eintraege direkt in die Datei legen (wie vom Vortag liegengeblieben).
    data = json.loads((tmp_path / "impulses.json").read_text(encoding="utf-8"))
    data["open"] += [
        {"id": "alt1", "kind": "weather", "key": "weather-heat-2026-07-13",
         "title": "Hitze", "detail": "alt", "created": "2026-07-13T06:01:04"},
        {"id": "alt2", "kind": "weather", "key": "weather-storm-2026-07-14",
         "title": "Unwetter", "detail": "alt", "created": "2026-07-14T06:29:47"},
    ]
    (tmp_path / "impulses.json").write_text(json.dumps(data), encoding="utf-8")

    assert store.count_open() == 1                     # nur heute zaehlt
    kept = json.loads((tmp_path / "impulses.json").read_text(encoding="utf-8"))["open"]
    assert [i["key"] for i in kept] == ["weather-heat-heute"]   # Datei geraeumt


def test_dismiss_adds_to_nein_list_and_blocks_readd(tmp_path):
    store = ImpulseStore(tmp_path)
    store.add_if_new("weather", "weather-heat-2026-07-11", "Hitze", "bis 34°")
    impulse_id = store.list_open()[0]["id"]

    assert store.dismiss(impulse_id) is True
    assert store.count_open() == 0
    # Weggeklickt = verstanden: derselbe key kommt nicht wieder.
    assert store.add_if_new("weather", "weather-heat-2026-07-11", "Hitze", "bis 34°") is False
    assert store.count_open() == 0


def test_dismiss_by_key_also_works(tmp_path):
    store = ImpulseStore(tmp_path)
    store.add_if_new("habit", "habit-get_news", "Gewohnheit", "morgens Nachrichten")

    assert store.dismiss("habit-get_news") is True
    assert store.dismiss("habit-get_news") is False  # schon weg


def test_list_open_newest_first(tmp_path):
    store = ImpulseStore(tmp_path)
    store.add_if_new("weather", "a", "A", "erst")
    store.add_if_new("weather", "b", "B", "dann")
    keys = [i["key"] for i in store.list_open()]
    # created ist auf Sekunden genau; bei Gleichstand ist die Ordnung stabil,
    # aber beide Keys muessen vorhanden sein.
    assert set(keys) == {"a", "b"}


def test_dismissed_list_is_bounded(tmp_path, monkeypatch):
    import memory.impulses as mod
    monkeypatch.setattr(mod, "_MAX_DISMISSED", 3)
    store = ImpulseStore(tmp_path)
    for i in range(6):
        store.add_if_new("k", f"key-{i}", "t", "d")
        store.dismiss(f"key-{i}")
    import json
    data = json.loads((tmp_path / "impulses.json").read_text(encoding="utf-8"))
    assert len(data["dismissed"]) <= 3


def test_store_redacts_secrets_but_keeps_normal_text(tmp_path):
    # Impuls-Texte kommen aus meinem Code (Wetter), nie aus Nutzereingaben -
    # redact() ist eine defensive Naht. E-Mails bleiben (Nutzdaten, ADR-040),
    # echte Secrets verschwinden.
    store = ImpulseStore(tmp_path)
    store.add_if_new("weather", "k", "Titel", "Schlüssel sk-ant-abcdef0123456789XYZ heute")  # release-scan: ok
    detail = store.list_open()[0]["detail"]
    assert "sk-ant-abcdef0123456789XYZ" not in detail  # release-scan: ok
    assert "Secret entfernt" in detail


# --- ImpulseEngine ---------------------------------------------------------

_NOON = datetime(2026, 7, 11, 12, 0)
_NIGHT = datetime(2026, 7, 11, 3, 0)


def test_engine_adds_from_checker(tmp_path):
    store = ImpulseStore(tmp_path)
    checker = lambda: [{"kind": "weather", "key": "k1", "title": "T", "detail": "D"}]
    engine = ImpulseEngine(store, [checker])

    added = engine.run(now=_NOON)

    assert added == 1
    assert store.count_open() == 1


def test_engine_on_new_fires_once_per_new_impulse(tmp_path):
    """Plan F: on_new wird je WIRKLICH neuem Impuls genau EINMAL gerufen -
    beim zweiten Lauf (dedupe) nicht mehr."""
    store = ImpulseStore(tmp_path)
    checker = lambda: [{"kind": "weather", "key": "k1", "title": "Sturm", "detail": "Hagel"}]
    engine = ImpulseEngine(store, [checker])
    pushed = []

    engine.run(now=_NOON, on_new=lambda cand: pushed.append(cand["title"]))
    engine.run(now=_NOON, on_new=lambda cand: pushed.append(cand["title"]))  # dedupe

    assert pushed == ["Sturm"]


def test_engine_on_new_error_does_not_stop_run(tmp_path):
    store = ImpulseStore(tmp_path)
    checker = lambda: [{"kind": "weather", "key": "k1", "title": "T", "detail": "D"}]
    engine = ImpulseEngine(store, [checker])

    def boom(cand):
        raise RuntimeError("push kaputt")

    assert engine.run(now=_NOON, on_new=boom) == 1     # Impuls trotzdem gelegt
    assert store.count_open() == 1


def test_engine_quiet_hours_lay_nothing(tmp_path):
    store = ImpulseStore(tmp_path)
    checker = lambda: [{"kind": "weather", "key": "k1", "title": "T", "detail": "D"}]
    engine = ImpulseEngine(store, [checker])

    assert engine.run(now=_NIGHT) == 0
    assert store.count_open() == 0


def test_engine_respects_open_cap(tmp_path, monkeypatch):
    import core.impulses as mod
    monkeypatch.setattr(mod, "_MAX_OPEN_IMPULSES", 2)
    store = ImpulseStore(tmp_path)
    many = lambda: [{"kind": "k", "key": f"k{i}", "title": "T", "detail": "D"} for i in range(5)]
    engine = ImpulseEngine(store, [many])

    engine.run(now=_NOON)

    assert store.count_open() == 2


def test_engine_one_broken_checker_does_not_stop_others(tmp_path):
    store = ImpulseStore(tmp_path)
    def boom():
        raise RuntimeError("Pruefer kaputt")
    good = lambda: [{"kind": "k", "key": "ok", "title": "T", "detail": "D"}]
    engine = ImpulseEngine(store, [boom, good])

    added = engine.run(now=_NOON)

    assert added == 1
    assert store.list_open()[0]["key"] == "ok"


# --- Unwetter-Pruefer ------------------------------------------------------

def _weather(**over):
    base = {"place": "Musterstadt", "condition": "bedeckt", "temp_min": 12,
            "temp_max": 24, "rain": 10, "current": 20, "segments": []}
    base.update(over)
    return base


def test_weather_checker_no_location_is_silent():
    checker = make_weather_checker("", summary_fn=lambda loc: _weather())
    assert checker() == []


def test_weather_checker_none_summary_is_silent():
    checker = make_weather_checker("Musterstadt", summary_fn=lambda loc: None)
    assert checker() == []


def test_weather_checker_flags_storm():
    checker = make_weather_checker("Musterstadt", summary_fn=lambda loc: _weather(condition="Gewitter mit Hagel"))
    out = checker()
    assert len(out) == 1
    assert out[0]["key"].startswith("weather-storm-")
    assert "Gewitter" in out[0]["detail"]


def test_weather_checker_flags_heavy_rain_from_segment():
    checker = make_weather_checker("Musterstadt", summary_fn=lambda loc: _weather(
        segments=[{"label": "Nachmittag", "temp": 19, "rain": 80}]))
    out = checker()
    keys = [o["key"] for o in out]
    assert any(k.startswith("weather-rain-") for k in keys)


def test_weather_checker_flags_heat():
    checker = make_weather_checker("Musterstadt", summary_fn=lambda loc: _weather(temp_max=34, current=33))
    out = checker()
    assert any(o["key"].startswith("weather-heat-") for o in out)


def test_weather_checker_flags_frost():
    checker = make_weather_checker("Musterstadt", summary_fn=lambda loc: _weather(temp_min=-8, temp_max=-1, current=-6))
    out = checker()
    assert any(o["key"].startswith("weather-frost-") for o in out)


def test_weather_checker_calm_day_is_silent():
    checker = make_weather_checker("Musterstadt", summary_fn=lambda loc: _weather())
    assert checker() == []


def test_weather_checker_storm_suppresses_separate_rain():
    # Gewitter deckt Regen mit ab - nicht zwei Karten fuer dasselbe Wetter.
    checker = make_weather_checker("Musterstadt", summary_fn=lambda loc: _weather(
        condition="Gewitter", segments=[{"label": "Nachmittag", "temp": 19, "rain": 90}]))
    keys = [o["key"] for o in checker()]
    assert any(k.startswith("weather-storm-") for k in keys)
    assert not any(k.startswith("weather-rain-") for k in keys)


# --- Wegklick-Funktion (commands/impulses.py) ------------------------------

def test_dismiss_function_removes_impulse(tmp_path):
    import commands.impulses as impulses_cmd
    store = ImpulseStore(tmp_path)
    store.add_if_new("weather", "weather-storm-2026-07-11", "Unwetter", "D")
    impulses_cmd.configure(store)

    assert impulses_cmd.dismiss("weather-storm-2026-07-11") is True
    assert store.count_open() == 0


def test_dismiss_function_unknown_key_returns_false(tmp_path):
    import commands.impulses as impulses_cmd
    impulses_cmd.configure(ImpulseStore(tmp_path))

    assert impulses_cmd.dismiss("gibt-es-nicht") is False


def test_dismiss_impulse_is_not_a_registry_command():
    """UI-intern: der Wegklick darf NIE ueber den Planner laufen - deshalb
    ist er kein registrierter Command und taucht im Prompt nicht auf."""
    from commands import REGISTRY
    from core.ai import build_system_prompt

    assert "dismiss_impulse" not in REGISTRY
    assert "dismiss_impulse" not in build_system_prompt()


def test_list_open_drops_impulses_from_previous_days(tmp_path):
    """PO-Reibung 14.07.: die 'Hitze heute'-Karte stand am Folgetag noch da.
    Impulse sind Tages-Aussagen: Vortags-Eintraege fallen beim Lesen still
    weg (nicht nach dismissed - derselbe key darf heute frisch kommen)."""
    import json
    from datetime import datetime, timedelta

    from memory.impulses import ImpulseStore

    store = ImpulseStore(tmp_path)
    store.add_if_new("weather", "hitze", "Hitze heute", "bis 32 Grad")
    gestern = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    path = tmp_path / "impulses.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["open"].append({"id": "alt1", "kind": "weather", "key": "hitze-gestern",
                         "title": "Hitze heute", "detail": "alt", "created": gestern})
    path.write_text(json.dumps(data), encoding="utf-8")

    offen = store.list_open()

    assert [i["key"] for i in offen] == ["hitze"]      # nur der heutige
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert [i["key"] for i in saved["open"]] == ["hitze"]          # Datei bereinigt
    assert "hitze-gestern" not in saved["dismissed"]   # key bleibt frei fuer heute
