"""Tests fuer core/weather.py + commands/weather.py (ADR-043) - Fetcher
injiziert, kein Netzwerk."""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

import commands.weather as weather_commands
from core.models import Plan, Status
from core.weather import DayForecast, PlaceNotFoundError, get_forecast

_GEO_OK = json.dumps(
    {"results": [{"name": "Musterstadt", "latitude": 50.33, "longitude": 8.54}]}
).encode()
_GEO_EMPTY = json.dumps({"generationtime_ms": 0.1}).encode()
_FORECAST = json.dumps(
    {
        "daily": {
            "time": ["2026-07-09", "2026-07-10", "2026-07-11"],
            "weather_code": [2, 61, 95],
            "temperature_2m_max": [23.4, 19.0, 17.2],
            "temperature_2m_min": [13.6, 12.1, 11.0],
            "precipitation_probability_max": [10, 80, 95],
        }
    }
).encode()


def _fetcher(geo=_GEO_OK, forecast=_FORECAST):
    def fetch(url, timeout):
        return geo if "geocoding" in url else forecast

    return fetch


def test_get_forecast_maps_day_and_wmo_code():
    f = get_forecast("musterstadt", day_offset=1, fetcher=_fetcher())
    assert f.place == "Musterstadt"
    assert f.date == "2026-07-10"
    assert f.condition == "leichter Regen"  # WMO 61
    assert (f.temp_min, f.temp_max) == (12.1, 19.0)
    assert f.rain_probability == 80


def test_get_forecast_unknown_place_raises():
    with pytest.raises(PlaceNotFoundError):
        get_forecast("Nirgendwo-Xyz", fetcher=_fetcher(geo=_GEO_EMPTY))


def test_resolve_day_words_and_iso_dates():
    resolve = weather_commands._resolve_day
    assert resolve("") == 0
    assert resolve("heute") == 0
    assert resolve("morgen") == 1
    assert resolve("übermorgen") == 2
    assert resolve((date.today() + timedelta(days=3)).isoformat()) == 3
    assert resolve((date.today() + timedelta(days=30)).isoformat()) == 6  # Deckel
    assert resolve("irgendwann") == 0  # fail-safe


def test_command_uses_default_location_and_persona(monkeypatch):
    weather_commands.configure("Musterstadt")
    monkeypatch.setattr(
        weather_commands,
        "get_forecast",
        lambda place, day_offset, timeout: DayForecast(
            place=place.title(), date="2026-07-10", condition="wechselnd bewölkt",
            temp_min=12.1, temp_max=19.0, rain_probability=20,
        ),
    )

    result = weather_commands.GetWeatherCommand().execute(
        Plan(intent="get_weather", parameters={"day": "morgen"})
    )

    assert result.status == Status.SUCCESS
    assert result.message.startswith("Morgen in Musterstadt, Sir:")
    assert "12 bis 19 Grad" in result.message
    assert "Regenrisiko 20 Prozent" in result.message


def test_command_named_location_wins(monkeypatch):
    weather_commands.configure("Musterstadt")
    captured = {}

    def fake(place, day_offset, timeout):
        captured["place"] = place
        return DayForecast(place, "2026-07-09", "klarer Himmel", 10.0, 20.0, None)

    monkeypatch.setattr(weather_commands, "get_forecast", fake)
    weather_commands.GetWeatherCommand().execute(
        Plan(intent="get_weather", parameters={"location": "Berlin"})
    )
    assert captured["place"] == "Berlin"


def test_command_asks_back_without_any_location():
    weather_commands.configure("")
    result = weather_commands.GetWeatherCommand().execute(Plan(intent="get_weather"))
    assert result.status == Status.NEEDS_CLARIFICATION


def test_command_reports_unknown_place_and_api_error(monkeypatch):
    weather_commands.configure("Musterstadt")

    def raise_not_found(place, day_offset, timeout):
        raise PlaceNotFoundError(place)

    monkeypatch.setattr(weather_commands, "get_forecast", raise_not_found)
    miss = weather_commands.GetWeatherCommand().execute(Plan(intent="get_weather"))
    assert miss.status == Status.FAILED and "finde ich nicht" in miss.message

    def raise_api(place, day_offset, timeout):
        raise RuntimeError("api down")

    monkeypatch.setattr(weather_commands, "get_forecast", raise_api)
    down = weather_commands.GetWeatherCommand().execute(Plan(intent="get_weather"))
    assert down.status == Status.FAILED and "antwortet gerade nicht" in down.message


# --- Tagesverlauf (PO-Wunsch 2026-07-10: "detaillierter als 12-29 Grad") ---

def _hourly_fixture():
    """48 Stundenwerte (Tag 0 flach, Tag 1 mit klarem Verlauf):
    Tag 1: Vormittag max 18, Nachmittag max 29, Abend max 21;
    Regen nur am Nachmittag (40 %), Codes: VM bedeckt / NM leichter Regen /
    Abend klar."""
    temps = [15.0] * 24
    rains = [5] * 24
    codes = [3] * 24
    day1_temp = [12.0] * 6 + [14, 15, 16, 17, 18, 17.5] + [22, 25, 27, 29, 28, 26] + [24, 23, 21, 20, 19, 18]
    day1_rain = [5] * 12 + [10, 20, 40, 35, 15, 10] + [5] * 6
    day1_code = [3] * 12 + [61] * 6 + [0] * 6
    return {
        "temperature_2m": temps + day1_temp,
        "precipitation_probability": rains + day1_rain,
        "weather_code": codes + day1_code,
    }


_FORECAST_HOURLY = json.dumps(
    {
        "daily": json.loads(_FORECAST.decode())["daily"],
        "hourly": _hourly_fixture(),
        "current": {"temperature_2m": 24.3, "weather_code": 3},
    }
).encode()


def test_segments_computed_from_hourly_blocks():
    f = get_forecast("musterstadt", day_offset=1, fetcher=_fetcher(forecast=_FORECAST_HOURLY))

    labels = [(s.label, s.temp, s.rain_probability) for s in f.segments]
    assert labels == [
        ("Vormittag", 18.0, 5),
        ("Nachmittag", 29.0, 40),
        ("Abend", 24.0, 5),
    ]
    assert f.segments[1].condition == "leichter Regen"  # Code 61 in Blockmitte
    # current gilt NUR fuer heute (day_offset 0):
    assert f.current_temp is None


def test_current_only_for_today():
    f = get_forecast("musterstadt", day_offset=0, fetcher=_fetcher(forecast=_FORECAST_HOURLY))
    assert f.current_temp == 24.3
    assert f.current_condition == "bedeckt"


def test_forecast_without_hourly_degrades_gracefully():
    """Alte API-Antworten (ohne hourly/current) liefern exakt das alte
    Verhalten - keine Segmente, kein Jetzt-Wert, kein Crash."""
    f = get_forecast("musterstadt", day_offset=1, fetcher=_fetcher())
    assert f.segments == []
    assert f.current_temp is None


def test_command_message_includes_daily_course(monkeypatch):
    from core.weather import DaySegment

    weather_commands.configure("Musterstadt")
    monkeypatch.setattr(
        weather_commands,
        "get_forecast",
        lambda place, day_offset, timeout: DayForecast(
            place="Musterstadt", date="2026-07-10", condition="bedeckt",
            temp_min=12.0, temp_max=29.0, rain_probability=40,
            current_temp=24.3, current_condition="bedeckt",
            segments=[
                DaySegment("Vormittag", 18.0, "bedeckt", 5),
                DaySegment("Nachmittag", 29.0, "leichter Regen", 40),
                DaySegment("Abend", 21.0, "klarer Himmel", 5),
            ],
        ),
    )

    result = weather_commands.GetWeatherCommand().execute(Plan(intent="get_weather"))

    assert "Jetzt 24 Grad (bedeckt)" in result.message
    assert "Vormittag bis 18°" in result.message
    assert "Nachmittag bis 29°" in result.message
    assert "Regen: Nachmittag 40 %." in result.message
    assert "Vormittag 5 %" not in result.message  # unter 20 % kein Regen-Alarm
    # PO-Befund 2026-07-10: mit Verlauf ist die Tages-Spanne doppelt - weg.
    assert "12 bis 29 Grad" not in result.message
