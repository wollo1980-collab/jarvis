"""
Wetter-Connector (ADR-043) - Open-Meteo: kostenlos, ohne API-Key, mit
Geocoding (Ortsname -> Koordinaten) und 7-Tage-Vorhersage. Read-only,
stdlib-only; der Fetcher ist injizierbar (Tests ohne Netzwerk).
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("jarvis.weather")

_GEOCODE_URL = (
    "https://geocoding-api.open-meteo.com/v1/search?name={query}&count=1&language=de&format=json"
)
_FORECAST_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
    "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
    # Tagesverlauf (PO-Wunsch 2026-07-10 "detaillierter als 12-29 Grad"):
    # Stundenwerte fuer die drei Tagesbloecke + aktueller Wert.
    "&hourly=temperature_2m,precipitation_probability,weather_code"
    "&current=temperature_2m,weather_code"
    "&timezone=auto&forecast_days=7"
)

# Tagesbloecke fuer den Verlauf (Stunden [start, end) der Ortszeit).
_SEGMENTS = (("Vormittag", 6, 12), ("Nachmittag", 12, 18), ("Abend", 18, 24))

# WMO-Wettercodes -> Deutsch (Open-Meteo liefert die Codes der WMO-Tabelle).
_WMO_TEXT = {
    0: "klarer Himmel",
    1: "überwiegend sonnig",
    2: "wechselnd bewölkt",
    3: "bedeckt",
    45: "Nebel",
    48: "Reifnebel",
    51: "leichter Nieselregen",
    53: "Nieselregen",
    55: "kräftiger Nieselregen",
    56: "gefrierender Nieselregen",
    57: "gefrierender Nieselregen",
    61: "leichter Regen",
    63: "Regen",
    65: "kräftiger Regen",
    66: "gefrierender Regen",
    67: "gefrierender Regen",
    71: "leichter Schneefall",
    73: "Schneefall",
    75: "kräftiger Schneefall",
    77: "Schneegriesel",
    80: "leichte Regenschauer",
    81: "Regenschauer",
    82: "kräftige Regenschauer",
    85: "Schneeschauer",
    86: "kräftige Schneeschauer",
    95: "Gewitter",
    96: "Gewitter mit Hagel",
    99: "schweres Gewitter mit Hagel",
}


@dataclass
class DaySegment:
    """Ein Tagesblock (Vormittag/Nachmittag/Abend) aus den Stundenwerten."""

    label: str
    temp: float  # Blockmaximum
    condition: str
    rain_probability: Optional[int]  # Blockmaximum


@dataclass
class DayForecast:
    place: str
    date: str  # ISO (YYYY-MM-DD)
    condition: str
    temp_min: float
    temp_max: float
    rain_probability: Optional[int]
    # Tagesverlauf (2026-07-10): aktueller Wert nur fuer heute; Segmente
    # ehrlich leer, wenn die Stundendaten fehlen/unvollstaendig sind.
    current_temp: Optional[float] = None
    current_condition: Optional[str] = None
    segments: list = field(default_factory=list)


def _default_fetcher(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Jarvis-Weather/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


class PlaceNotFoundError(Exception):
    """Der Ortsname liess sich nicht aufloesen."""


def _build_segments(hourly: dict, day_offset: int) -> list:
    """Drei Tagesbloecke aus den Stundenwerten des gewuenschten Tags.
    Unvollstaendige Bloecke werden ehrlich weggelassen (kein Raten)."""
    temps = hourly.get("temperature_2m") or []
    rains = hourly.get("precipitation_probability") or []
    codes = hourly.get("weather_code") or []
    base = day_offset * 24
    segments: list = []
    for label, start, end in _SEGMENTS:
        lo, hi = base + start, base + end
        block = temps[lo:hi]
        if len(block) < (end - start) or any(t is None for t in block):
            continue
        mid = lo + (end - start) // 2
        condition = (
            _WMO_TEXT.get(int(codes[mid]), "unbestimmtes Wetter")
            if mid < len(codes) and codes[mid] is not None
            else ""
        )
        rain_block = [r for r in rains[lo:hi] if r is not None]
        segments.append(
            DaySegment(
                label=label,
                temp=float(max(block)),
                condition=condition,
                rain_probability=int(max(rain_block)) if rain_block else None,
            )
        )
    return segments


def get_forecast(
    place: str,
    day_offset: int = 0,
    timeout: float = 10.0,
    fetcher: Callable[[str, float], bytes] = _default_fetcher,
) -> DayForecast:
    """Vorhersage fuer einen Ort und Tag (0=heute .. 6). Wirft
    PlaceNotFoundError bei unbekanntem Ort; API-/Netzfehler propagieren an
    den Command (der sie nutzerfreundlich meldet)."""
    day_offset = max(0, min(int(day_offset), 6))

    geo_raw = json.loads(fetcher(_GEOCODE_URL.format(query=urllib.parse.quote(place.strip())), timeout))
    results = geo_raw.get("results") or []
    if not results:
        raise PlaceNotFoundError(place)
    hit = results[0]
    resolved = hit.get("name") or place

    forecast_raw = json.loads(
        fetcher(_FORECAST_URL.format(lat=hit["latitude"], lon=hit["longitude"]), timeout)
    )
    daily = forecast_raw["daily"]
    rain = daily.get("precipitation_probability_max") or []

    # Tagesverlauf (fail-safe: fehlen hourly/current, bleibt alles wie frueher).
    segments = _build_segments(forecast_raw.get("hourly") or {}, day_offset)
    current = forecast_raw.get("current") or {}
    current_temp = current.get("temperature_2m") if day_offset == 0 else None
    current_condition = (
        _WMO_TEXT.get(int(current["weather_code"]), "unbestimmtes Wetter")
        if day_offset == 0 and current.get("weather_code") is not None
        else None
    )

    return DayForecast(
        place=resolved,
        date=daily["time"][day_offset],
        condition=_WMO_TEXT.get(int(daily["weather_code"][day_offset]), "unbestimmtes Wetter"),
        temp_min=float(daily["temperature_2m_min"][day_offset]),
        temp_max=float(daily["temperature_2m_max"][day_offset]),
        rain_probability=(
            int(rain[day_offset]) if day_offset < len(rain) and rain[day_offset] is not None else None
        ),
        current_temp=float(current_temp) if current_temp is not None else None,
        current_condition=current_condition,
        segments=segments,
    )
