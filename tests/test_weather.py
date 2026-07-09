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
    {"results": [{"name": "Usingen", "latitude": 50.33, "longitude": 8.54}]}
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
    f = get_forecast("usingen", day_offset=1, fetcher=_fetcher())
    assert f.place == "Usingen"
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
    weather_commands.configure("Usingen")
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
    assert result.message.startswith("Morgen in Usingen, Sir:")
    assert "12 bis 19 Grad" in result.message
    assert "Regenrisiko 20 Prozent" in result.message


def test_command_named_location_wins(monkeypatch):
    weather_commands.configure("Usingen")
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
    weather_commands.configure("Usingen")

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
