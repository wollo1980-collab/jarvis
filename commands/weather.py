"""
Wetter-Command (ADR-043) - "Wie wird das Wetter morgen in Usingen?" ueber
core/weather.py (Open-Meteo, keyless). Ohne Ortsangabe gilt der Standard-Ort
aus der Config (weather_default_location); ein genannter Ort gewinnt nur
fuer diese Frage. Read-only, Stufe 0.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from core.models import Plan, Result, Status
from core.weather import PlaceNotFoundError, get_forecast

logger = logging.getLogger("jarvis.commands.weather")

_default_location: str = ""
_timeout: float = 10.0

_DAY_WORDS = {"heute": 0, "morgen": 1, "übermorgen": 2, "uebermorgen": 2}
_DAY_LABELS = {0: "Heute", 1: "Morgen", 2: "Übermorgen"}


def configure(default_location: str, timeout_seconds: float = 10.0) -> None:
    """Von main.py/jarvis_runtime.py beim Start aufgerufen."""
    global _default_location, _timeout
    _default_location = (default_location or "").strip()
    _timeout = timeout_seconds


def _resolve_day(raw: str) -> int:
    """'heute'/'morgen'/'übermorgen' oder ISO-Datum -> Tages-Offset (0-6).
    Unbekanntes faellt fail-safe auf heute zurueck."""
    value = (raw or "").strip().lower()
    if not value:
        return 0
    if value in _DAY_WORDS:
        return _DAY_WORDS[value]
    try:
        offset = (datetime.fromisoformat(value).date() - date.today()).days
        return max(0, min(offset, 6))
    except ValueError:
        return 0


def _day_label(offset: int, iso_date: str) -> str:
    if offset in _DAY_LABELS:
        return _DAY_LABELS[offset]
    try:
        return "Am " + datetime.fromisoformat(iso_date).strftime("%d.%m.")
    except ValueError:
        return "Dann"


class GetWeatherCommand:
    name = "get_weather"
    description = (
        "Sagt das Wetter fuer einen Ort und Tag an (z. B. 'wie wird das Wetter "
        "morgen in Usingen?', 'Wetter heute?'). Ohne Ortsangabe gilt der "
        "konfigurierte Standard-Ort. Read-only."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        place = str(plan.parameters.get("location") or plan.target or "").strip() or _default_location
        if not place:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Für welchen Ort, Sir? (Ein Standard-Ort lässt sich in der Config hinterlegen.)",
            )

        offset = _resolve_day(str(plan.parameters.get("day") or ""))
        try:
            forecast = get_forecast(place, day_offset=offset, timeout=_timeout)
        except PlaceNotFoundError:
            return Result(
                status=Status.FAILED,
                message=f"Den Ort «{place}» finde ich nicht, Sir — ein Tippfehler vielleicht?",
            )
        except Exception:  # noqa: BLE001 - Netz/API koennen vielfaeltig scheitern
            logger.exception("Wetterabruf fehlgeschlagen (%s).", place)
            return Result(
                status=Status.FAILED,
                message="Der Wetterdienst antwortet gerade nicht, Sir.",
            )

        rain = (
            f", Regenrisiko {forecast.rain_probability} Prozent"
            if forecast.rain_probability is not None
            else ""
        )
        return Result(
            status=Status.SUCCESS,
            message=(
                f"{_day_label(offset, forecast.date)} in {forecast.place}, Sir: "
                f"{forecast.condition}, {forecast.temp_min:.0f} bis {forecast.temp_max:.0f} Grad{rain}."
            ),
            data={"place": forecast.place, "date": forecast.date},
        )


COMMANDS = [GetWeatherCommand()]
