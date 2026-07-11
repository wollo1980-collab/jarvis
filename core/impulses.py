"""
Impuls-Engine (Endsystem-Kampagne, ADR-054) - Jarvis' Herzschlag: prueft
in festem Takt seine ECHTEN Quellen und legt Impulse ab, ohne gefragt zu
werden. Das ist der Schritt vom reaktiven Assistenten zum proaktiven
Endsystem (Branchen-Zielbild 2026): relevantes VORLEGEN, statt auf Zuruf
zu warten.

Eiserne Leitplanken (Angestellten-Vision, PO 11.07.2026):
- Vorschlag statt Aktion: ein Impuls informiert oder fragt - er fuehrt
  NIE etwas aus. Kein Arm, nur eine Stimme.
- Nur echte Quellen: Impulse entstehen ausschliesslich aus Daten, die
  wirklich existieren (Wetter-Vorhersage, spaeter Gewohnheits-Statistik,
  Delegations-Logs). Nie eine erfundene Stimmung.
- Still: ein Impuls wird als Dashboard-Karte gelegt, nicht gesprochen
  (PO-Entscheidung 11.07.: "lieber als Karte, nicht selbststaendig reden").
- Gedeckelt: hoechstens eine Handvoll offener Impulse gleichzeitig; nachts
  wird nicht gelegt (ein Assistent, der dauernd zupft, ist keiner).
- Weggeklickt = verstanden: die Nein-Liste im ImpulseStore sorgt dafuer,
  dass ein abgelehnter Impuls nicht wiederkehrt.

Die Pruefer sind reine Funktionen `() -> list[dict]` (kind/key/title/
detail) und werden injiziert - die Engine kennt keine konkrete Quelle
(gleiche Entkopplung wie beim Agenten-Backend). Jeder Pruefer laeuft in
seinem eigenen try/except: faellt einer aus, legen die anderen trotzdem.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Callable, Optional

logger = logging.getLogger("jarvis.impulses")

# Deckel offener Impulse: mehr als das ueberfordert die Karte-Wand und
# widerspraeche dem "zupft nicht dauernd"-Grundsatz.
_MAX_OPEN_IMPULSES = 5
# Ruhefenster: nachts wird nichts gelegt (Ortszeit des Rechners).
_QUIET_FROM_HOUR = 22
_QUIET_TO_HOUR = 6

ImpulseChecker = Callable[[], list[dict]]


class ImpulseEngine:
    """Fuehrt die Pruefer aus und legt neue Impulse im Store ab (dedupe +
    Nein-Liste stecken im Store). Selbst zustandslos bis auf die injizierten
    Pruefer - der Takt/Throttle liegt beim Aufrufer (Runtime-Scheduler)."""

    def __init__(self, store, checkers: list[ImpulseChecker]):
        self._store = store
        self._checkers = list(checkers)

    def run(self, now: Optional[datetime] = None) -> int:
        """Ein Durchlauf: alle Pruefer, dann neue Impulse ablegen (bis zum
        Deckel). Liefert die Zahl neu gelegter Impulse. Fail-safe - wirft nie."""
        now = now or datetime.now()
        if _QUIET_FROM_HOUR <= now.hour or now.hour < _QUIET_TO_HOUR:
            return 0  # Ruhefenster: kein Zupfen
        added = 0
        for checker in self._checkers:
            if self._store.count_open() >= _MAX_OPEN_IMPULSES:
                break
            try:
                candidates = checker() or []
            except Exception:  # noqa: BLE001 - ein kaputter Pruefer stoppt nie die anderen
                logger.exception("Impuls-Pruefer fehlgeschlagen.")
                continue
            for cand in candidates:
                if self._store.count_open() >= _MAX_OPEN_IMPULSES:
                    break
                if self._store.add_if_new(
                    cand.get("kind", ""), cand.get("key", ""),
                    cand.get("title", ""), cand.get("detail", ""),
                ):
                    added += 1
        if added:
            logger.info("Impuls-Kreislauf: %d neue(r) Impuls(e).", added)
        return added


# --- Pruefer: Unwetter (erster echter Herzschlag) --------------------------

# Schwellwerte aus realen Vorhersagewerten (Open-Meteo, core/weather.py).
_STORM_WORDS = ("gewitter", "hagel", "sturm")
_HEAVY_RAIN_PCT = 70
_HEAT_MAX_C = 32
_FROST_MIN_C = -5


def make_weather_checker(location: str, summary_fn: Optional[Callable] = None) -> ImpulseChecker:
    """Baut den Unwetter-Pruefer fuer einen Ort. summary_fn ist injizierbar
    (Tests reichen einen Fake); Default ist der gecachte
    dashboard_data.weather_summary (30-Min-TTL, haemmert die Quelle nie).

    Legt hoechstens EINEN Impuls je Unwetter-Art und Tag: der key traegt das
    Datum, damit morgen ein frischer Anlauf moeglich ist und ein
    weggeklickter Hinweis nur den heutigen Tag betrifft."""
    loc = (location or "").strip()

    def _check() -> list[dict]:
        if not loc:
            return []
        fn = summary_fn
        if fn is None:
            from core.dashboard_data import weather_summary as fn  # lazy: Zyklus vermeiden
        data = fn(loc)
        if not data:
            return []
        today = date.today().isoformat()
        place = str(data.get("place") or loc)
        condition = str(data.get("condition") or "")
        segments = data.get("segments") or []
        out: list[dict] = []

        # Gewitter/Hagel/Sturm - aus der Tagesbedingung.
        if any(w in condition.lower() for w in _STORM_WORDS):
            out.append({
                "kind": "weather",
                "key": f"weather-storm-{today}",
                "title": "Unwetter erwartet",
                "detail": f"Heute {condition} in {place}. Vielleicht Fenster schließen und Empfindliches sichern.",
            })

        # Starkregen: hoechste Segment-Wahrscheinlichkeit ODER Tageswert.
        rain_values = [int(s["rain"]) for s in segments if s.get("rain") is not None]
        if data.get("rain") is not None:
            rain_values.append(int(data["rain"]))
        max_rain = max(rain_values) if rain_values else 0
        if max_rain >= _HEAVY_RAIN_PCT and not any(w in condition.lower() for w in _STORM_WORDS):
            out.append({
                "kind": "weather",
                "key": f"weather-rain-{today}",
                "title": "Regen wahrscheinlich",
                "detail": f"{place}: bis {max_rain} % Regen heute. Schirm einpacken schadet nicht.",
            })

        # Hitze.
        temps = [t for t in (data.get("temp_max"), data.get("current")) if t is not None]
        peak = max(temps) if temps else None
        if peak is not None and peak >= _HEAT_MAX_C:
            out.append({
                "kind": "weather",
                "key": f"weather-heat-{today}",
                "title": "Hitze heute",
                "detail": f"{place}: bis {int(peak)}°. Viel trinken, tagsüber Rollläden runter.",
            })

        # Frost/Glätte.
        temp_min = data.get("temp_min")
        if temp_min is not None and temp_min <= _FROST_MIN_C:
            out.append({
                "kind": "weather",
                "key": f"weather-frost-{today}",
                "title": "Frost heute",
                "detail": f"{place}: bis {int(temp_min)}°. Glätte möglich – vorsichtig unterwegs.",
            })
        return out

    return _check
