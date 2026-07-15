#!/usr/bin/env python3
"""
Faden-Probe (Spektakulaer #3 "Gespraechs-Faden", Design 2026-07-13).

Misst mit ECHTEN LLM-Calls, ob Jarvis bei kurzen Folgefragen den Faden haelt -
an beiden Gliedern der Kette, getrennt:

1. ROUTER-WAHL: der echte Klassifikator-Router (AIEngine.get_plan) bekommt
   Gespraechs-History + Kurz-Nachfrage. Waehlt er das erwartete Ziel?
   Familien: Gegenfragen ("Und bei dir?" -> chat), Anschluss-Nachfragen
   ("Und morgen?" nach Wetter -> Werkzeug! - das Gegenbeispiel, das jeden
   Kurz-Eingabe-Klassifikator widerlegt), Vertiefung, Abschluss, Pronomen.

2. COMPOSER-ANTWORT: der echte Antwort-Composer (ADR-065) bekommt den
   Kundenreview-Fall absichtlich FEHLGEROUTET vorgesetzt (History enthaelt
   die News schon, Werkzeug get_news lief "nochmal") - wiederholt die
   komponierte Antwort die Schlagzeilen, oder beantwortet sie die Frage?

READ-ONLY: nur Wahl + Formulierung, nie Ausfuehrung. Kostet wenige Cent.
Aufruf:  python scripts/thread_eval.py [--router-only|--composer-only]
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.models import Message, Plan, Result, Status  # noqa: E402

# ---------------------------------------------------------------------------
# Router-Batterie: (name, familie, history, eingabe, erwartete intents)
# `erwartet` ist eine MENGE - bei Anschluss-Faellen sind mehrere Werkzeuge
# legitim (list_entries vs. calendar_agenda). Treffer = got in erwartet.
# ---------------------------------------------------------------------------

_NEWS_ANSWER = (
    "Die Lage: Die Koalition plant, Rauchen teurer zu machen. Die EU-"
    "Aussenminister beraten ueber Sanktionen gegen Russland. Und die "
    "'Koalition der Willigen' beraet weitere Unterstuetzung der Ukraine."
)
_WEATHER_ANSWER = "Heute in Musterstadt: bedeckt bei 30 Grad, abends 32 Grad, kein Regen."
_AGENDA_ANSWER = "Heute steht nur eines an: 19:12 Uhr Pizza aus dem Ofen holen."


def _h(*pairs: tuple[str, str]) -> list[Message]:
    return [Message(role=r, content=c) for r, c in pairs]


ROUTER_BATTERY: list[dict] = [
    # --- Familie: Gegenfrage sozial -> Gespraech, KEIN Werkzeug -------------
    {"name": "news-und-bei-dir", "familie": "gegenfrage",
     "history": _h(("user", "was gibt es neues?"), ("assistant", _NEWS_ANSWER)),
     "eingabe": "und bei dir?", "erwartet": {"chat"}},
    {"name": "smalltalk-und-bei-dir", "familie": "gegenfrage",
     "history": _h(("user", "guten abend jarvis"),
                   ("assistant", "Schoenen guten Abend, Sir. Wie war der Tag?"),
                   ("user", "ganz gut, viel geschafft.")),
     "eingabe": "und bei dir?", "erwartet": {"chat"}},
    {"name": "news-echt", "familie": "gegenfrage",
     "history": _h(("user", "was gibt es neues?"), ("assistant", _NEWS_ANSWER)),
     "eingabe": "echt? verrueckt.", "erwartet": {"chat"}},
    {"name": "news-danke-abschluss", "familie": "gegenfrage",
     "history": _h(("user", "was gibt es neues?"), ("assistant", _NEWS_ANSWER)),
     "eingabe": "danke, das reicht mir fuer heute.", "erwartet": {"chat"}},
    # --- Familie: Vertiefung -> Gespraech ueber das Genannte ----------------
    {"name": "news-wieso", "familie": "vertiefung",
     "history": _h(("user", "was gibt es neues?"), ("assistant", _NEWS_ANSWER)),
     "eingabe": "wieso wollen die das rauchen teurer machen?", "erwartet": {"chat", "search_web"}},
    {"name": "news-was-haeltst-du", "familie": "vertiefung",
     "history": _h(("user", "was gibt es neues?"), ("assistant", _NEWS_ANSWER)),
     "eingabe": "und was haeltst du davon?", "erwartet": {"chat"}},
    # --- Familie: Anschluss MIT Werkzeug (Gegenbeispiele!) ------------------
    {"name": "wetter-und-morgen", "familie": "anschluss",
     "history": _h(("user", "wie wird das wetter heute in musterstadt?"),
                   ("assistant", _WEATHER_ANSWER)),
     "eingabe": "und morgen?", "erwartet": {"get_weather"}},
    {"name": "wetter-und-wochenende", "familie": "anschluss",
     "history": _h(("user", "wie wird das wetter morgen?"),
                   ("assistant", _WEATHER_ANSWER)),
     "eingabe": "und am wochenende?", "erwartet": {"get_weather"}},
    {"name": "agenda-und-naechste-woche", "familie": "anschluss",
     "history": _h(("user", "was steht heute an?"), ("assistant", _AGENDA_ANSWER)),
     "eingabe": "und naechste woche?", "erwartet": {"list_entries", "calendar_agenda"}},
    {"name": "liste-noch-butter", "familie": "anschluss",
     "history": _h(("user", "was steht auf der einkaufsliste?"),
                   ("assistant", "Auf der Einkaufsliste: Milch, Brot, Eier.")),
     "eingabe": "setz noch butter drauf", "erwartet": {"add_to_list"}},
    # --- Familie: Pronomen-Bezug -> Werkzeug mit aufgeloestem Ziel ----------
    {"name": "termin-verschieb-den", "familie": "pronomen",
     "history": _h(("user", "was steht heute an?"),
                   ("assistant", "Heute: 14:00 Uhr Termin beim Chef.")),
     "eingabe": "verschieb den mal auf 15 uhr", "erwartet": {"calendar_move_event", "update_entry"}},
]


def evaluate_router(plan_fn: Callable[[str, list[Message]], Plan],
                    battery: list[dict] = ROUTER_BATTERY) -> list[dict]:
    """Fuehrt die Router-Batterie aus. `plan_fn(eingabe, history)` -> Plan
    (real: AIEngine.get_plan; im Test: Attrappe). API-Fehler zaehlen EHRLICH
    als ERR, nie als Fehlgriff (Lehre aus reasoning_eval)."""
    out: list[dict] = []
    for case in battery:
        try:
            got = plan_fn(case["eingabe"], case["history"]).intent
        except Exception as e:  # noqa: BLE001
            got = f"ERR:{type(e).__name__}"
        out.append({"name": case["name"], "familie": case["familie"],
                    "eingabe": case["eingabe"], "erwartet": sorted(case["erwartet"]),
                    "got": got, "ok": got in case["erwartet"]})
    return out


def format_router_report(results: list[dict]) -> str:
    lines = ["Faden-Probe 1/2 - Router-Wahl mit Gespraechs-History:", ""]
    by_family: dict[str, list[dict]] = {}
    for r in results:
        by_family.setdefault(r["familie"], []).append(r)
    for family, rows in by_family.items():
        hits = sum(1 for r in rows if r["ok"])
        lines.append(f"  {family}: {hits}/{len(rows)}")
        for r in rows:
            mark = "[OK]" if r["ok"] else "[X] "
            lines.append(f"    {mark} {r['name']}: {r['eingabe']!r} -> {r['got']}"
                         + ("" if r["ok"] else f" (erwartet: {'/'.join(r['erwartet'])})"))
    total = sum(1 for r in results if r["ok"])
    lines += ["", f"  Gesamt: {total}/{len(results)}"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Composer-Batterie: der Kundenreview-Fall, absichtlich fehlgeroutet.
# Die History enthaelt die News SCHON, das Werkzeug lief "nochmal" - eine
# fadentreue Antwort beantwortet die Frage, statt die Schlagzeilen erneut
# aufzusagen. Deterministische Pruefung: wie viele Schlagzeilen-Marker
# tauchen in der Antwort wieder auf?
# ---------------------------------------------------------------------------

_NEWS_MARKERS = ("rauchen", "russland", "ukraine")

COMPOSER_BATTERY: list[dict] = [
    {"name": "und-bei-dir-nach-news", "eingabe": "und bei dir?",
     "history": _h(("user", "was gibt es neues?"), ("assistant", _NEWS_ANSWER)),
     "marker": _NEWS_MARKERS},
    {"name": "danke-nach-news", "eingabe": "danke dir, das wars erstmal.",
     "history": _h(("user", "was gibt es neues?"), ("assistant", _NEWS_ANSWER)),
     "marker": _NEWS_MARKERS},
    {"name": "wie-gehts-dir-nach-news", "eingabe": "alles klar. wie geht es dir eigentlich?",
     "history": _h(("user", "was gibt es neues?"), ("assistant", _NEWS_ANSWER)),
     "marker": _NEWS_MARKERS},
]


def _misrouted_news_steps() -> tuple[list[Plan], list[Result]]:
    """Der fehlgeroutete Schritt: get_news lief erneut, Ergebnis = dieselben
    Schlagzeilen, die die History schon zeigt."""
    plan = Plan(intent="get_news", raw_input="(fehlgeroutet)")
    result = Result(status=Status.SUCCESS, message=_NEWS_ANSWER)
    return [plan], [result]


def evaluate_composer(compose_fn: Callable[..., str],
                      battery: list[dict] = COMPOSER_BATTERY,
                      repeat_threshold: int = 2) -> list[dict]:
    """`compose_fn(eingabe, history, steps, results)` -> Antworttext (real:
    compose_response mit echtem generate; im Test: Attrappe). `wiederholt` =
    mindestens `repeat_threshold` Schlagzeilen-Marker tauchen wieder auf."""
    out: list[dict] = []
    steps, results = _misrouted_news_steps()
    for case in battery:
        try:
            answer = compose_fn(case["eingabe"], case["history"], steps, results) or ""
        except Exception as e:  # noqa: BLE001
            answer = f"ERR:{type(e).__name__}"
        low = answer.lower()
        repeats = sum(1 for marker in case["marker"] if marker in low)
        out.append({"name": case["name"], "eingabe": case["eingabe"], "antwort": answer,
                    "marker_treffer": repeats,
                    "wiederholt": repeats >= repeat_threshold})
    return out


def format_composer_report(results: list[dict]) -> str:
    lines = ["", "Faden-Probe 2/2 - Composer-Antwort bei absichtlichem Fehlrouting:", ""]
    ok = sum(1 for r in results if not r["wiederholt"])
    for r in results:
        mark = "[OK]" if not r["wiederholt"] else "[X] "
        lines.append(f"  {mark} {r['name']}: {r['eingabe']!r} "
                     f"(Schlagzeilen-Marker wieder aufgesagt: {r['marker_treffer']})")
        lines.append(f"       Antwort: {r['antwort'][:200]!r}")
    lines += ["", f"  Fadentreu (keine Wiederholung): {ok}/{len(results)}"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Echt-Verdrahtung (nur bei direktem Aufruf; Tests injizieren Attrappen).
# ---------------------------------------------------------------------------

def _real_plan_fn(throttle_s: float = 1.3):
    import time

    from core.ai import AIEngine
    from core.config import Config

    ai = AIEngine(Config.load())

    def plan(eingabe: str, history: list[Message]) -> Plan:
        if throttle_s:
            time.sleep(throttle_s)
        return ai.get_plan(eingabe, history)

    return plan


def _real_compose_fn(throttle_s: float = 1.3):
    import time

    from core.ai import AIEngine
    from core.config import Config
    from core.response_composer import compose_response

    config = Config.load()
    ai = AIEngine(config)
    model = getattr(config, "compose_model", "") or "gpt-4o-mini"

    def compose(eingabe: str, history: list[Message], steps, results) -> str:
        if throttle_s:
            time.sleep(throttle_s)
        return compose_response(
            eingabe, history, steps, results,
            lambda system, user_text: ai.generate(system, user_text, model=model),
            owner_name=getattr(config, "owner_name", "") or "",
        )

    return compose


def main(argv: list[str]) -> int:
    if "--composer-only" not in argv:
        print(format_router_report(evaluate_router(_real_plan_fn())))
    if "--router-only" not in argv:
        print(format_composer_report(evaluate_composer(_real_compose_fn())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
