"""Tests fuer commands/briefing.py - Komposition aus echten Quellen, jede
Quelle fail-safe. Stores gegen tmp_path, Wetter/News gemockt (Muster
tests/test_weather.py)."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import commands.briefing as briefing
from commands import REGISTRY
from core.models import Plan, Status
from core.weather import DayForecast, DaySegment
from memory.entries import EntryStore
from memory.lists import ListStore


def _today_iso(hour: int = 23, minute: int = 30) -> str:
    return datetime.now().strftime(f"%Y-%m-%dT{hour:02d}:{minute:02d}")


def _configure(tmp_path: Path, location: str = "Musterstadt", feeds=None):
    entry_store = EntryStore(tmp_path)
    list_store = ListStore(tmp_path)
    briefing.configure(entry_store, list_store, location,
                       feeds if feeds is not None else ["https://example.invalid/rss"])
    return entry_store, list_store


class _Headline:
    def __init__(self, title):
        self.title = title
        self.source = "test"


def test_registered_and_stufe_0():
    cmd = REGISTRY["get_briefing"]
    assert cmd.name == "get_briefing"
    assert cmd.requires_confirmation is False


def test_briefing_composes_all_sections(tmp_path, monkeypatch):
    entry_store, list_store = _configure(tmp_path)
    entry_store.add("Zahnarzt", when=_today_iso(), important=True)
    entry_store.add("Zusammenfassung", when=_today_iso(23, 55), repeat="täglich")
    entry_store.add("Reifen wechseln")  # Merkposten
    list_store.add("einkaufsliste", ["Milch", "Brot"])
    monkeypatch.setattr(
        briefing, "get_forecast",
        lambda place, day_offset, timeout: DayForecast(
            place="Musterstadt", date="2026-07-11", condition="bedeckt",
            temp_min=12.0, temp_max=29.0, rain_probability=10,
            current_temp=22.4, current_condition="klar",
            segments=[DaySegment("Nachmittag", 29.0, "bedeckt", 40)],
        ),
    )
    monkeypatch.setattr(
        briefing, "fetch_headlines",
        lambda feeds, limit: [_Headline("Schlagzeile A"), _Headline("Schlagzeile B")],
    )

    result = briefing.GetBriefingCommand().execute(Plan(intent="get_briefing"))

    assert result.status == Status.SUCCESS
    msg = result.message
    assert "wichtig: Zahnarzt" in msg
    assert "(täglich)" in msg                      # Wiederholungs-Marker
    assert "1 Merkposten" in msg
    assert "jetzt 22 Grad" in msg
    assert "nachmittags bis 29" in msg
    assert "Regen moeglich am Nachmittag" in msg   # 40 % >= Schwelle
    assert "Einkaufsliste mit 2 Posten" in msg
    assert "1. Schlagzeile A" in msg
    assert result.data["sections"] == 4
    assert "**" not in msg                          # sprechtauglich, kein Markdown


def test_briefing_survives_every_source_failing(tmp_path, monkeypatch):
    """Fail-safe: Wetter/News werfen, Stores leer -> trotzdem eine ehrliche
    Antwort, nie eine Exception."""
    _configure(tmp_path)
    monkeypatch.setattr(briefing, "get_forecast",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(briefing, "fetch_headlines",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))

    result = briefing.GetBriefingCommand().execute(Plan(intent="get_briefing"))

    assert result.status == Status.SUCCESS
    assert "der Tag gehoert dir" in result.message  # Eintraege-Abschnitt bleibt


def test_briefing_without_location_and_feeds_skips_sections(tmp_path, monkeypatch):
    entry_store, _ = _configure(tmp_path, location="", feeds=[])
    entry_store.add("Zahnarzt", when=_today_iso())
    called = {"weather": False, "news": False}
    monkeypatch.setattr(briefing, "get_forecast",
                        lambda *a, **k: called.__setitem__("weather", True))
    monkeypatch.setattr(briefing, "fetch_headlines",
                        lambda *a, **k: called.__setitem__("news", True))

    result = briefing.GetBriefingCommand().execute(Plan(intent="get_briefing"))

    assert result.status == Status.SUCCESS
    assert called == {"weather": False, "news": False}  # gar nicht erst versucht
    assert "Zahnarzt" in result.message


def test_briefing_never_presents_old_important_entry_as_next(tmp_path, monkeypatch):
    """Nacht-Audit-Fix D: ein vergangener ⭐-Merkposten (list_open zeigt ihn
    bewusst zum Nachschlagen) darf im Briefing nie 'Als Naechstes' werden."""
    entry_store, _ = _configure(tmp_path, location="", feeds=[])
    entry_store.add("Audit in Musterstadt", when="2025-07-12", important=True)

    result = briefing.GetBriefingCommand().execute(Plan(intent="get_briefing"))

    assert result.status == Status.SUCCESS
    assert "Als Naechstes" not in result.message
    assert "Audit in Musterstadt" not in result.message
    assert "der Tag gehoert dir" in result.message


def test_system_prompt_mentions_briefing():
    from core.ai import build_system_prompt

    prompt = build_system_prompt()
    assert "get_briefing" in prompt
    assert "was steht an?" in prompt  # Abgrenzung zu list_entries benannt


def test_briefing_allowed_on_runtime_telegram_channel():
    import telegram_channel
    import telegram_main

    assert "get_briefing" in telegram_channel.RUNTIME_ALLOWED_INTENTS
    assert "get_briefing" not in telegram_main.ALLOWED_INTENTS
