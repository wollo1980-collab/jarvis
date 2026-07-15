#!/usr/bin/env python3
"""
Migrations-Prüfbatterie für den denkenden Kern (ADR-060 Phase 2, [[llm-kern-nordstern]]).

Bevor ein Intent vom Klassifikator-Router auf den Kern umgehängt wird
(config.reasoning_route_intents), muss belegt sein, dass der Kern ihn sicher
trifft. Dieses Skript laesst den ECHTEN Kern (reasoning.decide über den realen
OpenAI-Function-Calling-Adapter) gegen eine kuratierte Batterie realistischer
deutscher Formulierungen laufen und misst pro Intent die Trefferquote - plus
die "Gespraech"-Faelle (der Kern darf harmlose Plauderei NICHT faelschlich auf
ein Werkzeug schieben). READ-ONLY: es wird nur die WAHL gemessen, nie etwas
ausgefuehrt.

Aufruf:  python scripts/reasoning_eval.py [--verbose]
Kostet ein paar Cent (ein LLM-Call je Zeile). Exit 0 = Bericht erstellt.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.models import Plan  # noqa: E402

# Erwarteter Intent -> realistische Formulierungen. "chat" = der Kern soll KEIN
# Werkzeug waehlen (Gespraech). Bewusst SICHERE, read-only Kandidaten zuerst -
# ein Fehlgriff hier ist harmlos (falsche/keine Auskunft, keine Aktion).
BATTERY: dict[str, list[str]] = {
    "get_weather": [
        "wie wird das wetter morgen in berlin?",
        "brauche ich heute einen regenschirm in hamburg?",
        "wie warm wird es uebermorgen in muenchen?",
        "wird es am wochenende regnen?",
    ],
    "get_news": [
        "was gibt es neues in der welt?",
        "zeig mir die aktuellen schlagzeilen",
        "gibt es wichtige nachrichten heute?",
    ],
    "system_status": [
        "wie ist der systemstatus?",
        "laeuft bei dir technisch alles rund?",
        "zeig mir deinen systemzustand",
    ],
    # 'was steht an?'/'anstehende termine' akzeptieren seit dem Tages-Blick
    # (PO-Go 14.07.) auch calendar_agenda - die Naht ist bewusst aufgeloest.
    "list_entries|calendar_agenda": [
        "was steht heute noch an?",
        "zeig mir meine anstehenden termine",
    ],
    "list_entries": [
        "welche erinnerungen habe ich?",
    ],
    "list_facts": [
        "was hast du dir ueber mich gemerkt?",
        "was weisst du alles ueber mich?",
    ],
    "get_briefing": [
        "gib mir mein tagesbriefing",
        "was ist heute wichtig fuer mich?",
    ],
    # Welle 2 (2026-07-12): weitere read-only + Medien + Schreib-Aktionen zur
    # Beobachtung. Umgehaengt wird nur, was 100% trifft UND sicher genug ist.
    "show_list": [
        "was steht auf meiner einkaufsliste?",
        "zeig mir die einkaufsliste",
        "welche punkte hat meine todo-liste?",
    ],
    "weekly_review": [
        "was haben wir diese woche geschafft?",
        "gib mir den wochenrueckblick",
    ],
    "search_web": [
        "suche im web nach dem klimawandel",
        "google mal die einwohnerzahl von berlin",
        "recherchier den aktuellen bitcoin-kurs",
    ],
    "propose_ideas": [
        "hast du eine idee was wir entwickeln koennten?",
        "schlag mir etwas vor",
    ],
    "spotify_play": [
        "spiel musik",
        "mach musik an",
    ],
    "spotify_pause": [
        "pausier die musik",
        "stopp die musik",
    ],
    "spotify_next": [
        "naechster song",
        "spiel den naechsten titel",
    ],
    "add_entry": [
        "erinnere mich morgen um 9 an den zahnarzt",
    ],
    # Termin-Regel 14.07. (PO-Reibung Rewe): echte TERMINE gehoeren in den
    # Kalender - die alte Erwartung add_entry war seit heute frueh falsch.
    "calendar_add_event": [
        "trag mir fuer freitag einen termin ein",
    ],
    "remember_fact": [
        "merk dir dass ich meinen kaffee schwarz trinke",
        "behalte im kopf dass ich in musterstadt wohne",
    ],
    # Welle 3 (2026-07-12): restliche sichere Intents (Medien, Oeffnen, Listen,
    # Name, Mail-Lesen). Gefaehrliche Pfade bleiben bewusst DRAUSSEN.
    "spotify_now_playing": [
        "was laeuft gerade?",
        "welcher song spielt jetzt?",
    ],
    "spotify_previous": [
        "vorheriger song",
        "spiel den letzten titel nochmal",
    ],
    "spotify_volume": [
        "mach die musik lauter",
        "stell die lautstaerke auf 50 prozent",
    ],
    "open_program": [
        "oeffne excel",
        "starte den taschenrechner",
        "mach mir word auf",
    ],
    "add_to_list": [
        "setz brot auf die einkaufsliste",
        "fueg milch zur einkaufsliste hinzu",
    ],
    "remove_from_list": [
        "nimm brot von der einkaufsliste",
        "streich milch von der liste",
    ],
    "set_owner_name": [
        "nenn mich ab jetzt martin",
        "sag einfach chef zu mir",
    ],
    "check_mail": [
        "hab ich neue mails?",
        "schau mal in mein postfach",
    ],
    "read_excel": [
        "lies mir die excel-datei vor",
        "was steht in der excel-tabelle?",
    ],
    # Welle 4 (2026-07-12): seltene, aber SICHERE read-only/undo-Faehigkeiten -
    # damit "komplett auf 2026" wirklich komplett ist (nur Gefaehrliches bleibt
    # bewusst beim Router + Gate).
    "restore_list": [
        "stell die geloeschte liste wieder her",
        "mach das loeschen der liste rueckgaengig",
    ],
    "analyze_pc": [
        "analysier meinen pc",
        "pruef mal die systemleistung",
    ],
    "analyze_temp_files": [
        "schau dir meine temporaeren dateien an",
        "analysier die temp-dateien",
    ],
    "analyze_event_log": [
        "gibt es fehler im windows-ereignisprotokoll?",
        "schau ins ereignisprotokoll",
    ],
    "verify_repo": [
        "pruef das jarvis-repo auf konsistenz",
        "verifizier das repo",
    ],
    "show_mail_advertising": [
        "zeig mir die werbe-mails im postfach",
        "welche werbung liegt in den mails?",
    ],
    "chat": [
        "erzaehl mir einen witz",
        "guten morgen jarvis",
        "ich bin heute ziemlich muede",
        "was haeltst du eigentlich von fussball?",
        "danke, das war super",
    ],
}


def evaluate(decide_fn: Callable[[str], Plan], battery: dict = BATTERY) -> dict:
    """Fuehrt die Batterie aus und liefert pro erwartetem Intent Treffer/Gesamt
    + die Fehlgriffe. `decide_fn(phrase)` -> Plan (real: reasoning.decide mit
    dem echten Kern; im Test: eine Attrappe). Rein - kein Netz-Wissen hier."""
    results: dict[str, dict] = {}
    for expected, phrases in battery.items():
        # 'a|b' = mehrere legitime Intents (aufgeloeste Naehte, z. B.
        # list_entries|calendar_agenda seit dem Tages-Blick 14.07.).
        accepted = set(expected.split("|"))
        hits = 0
        misses: list[tuple[str, str]] = []
        errors = 0
        cases: list[dict] = []
        for phrase in phrases:
            try:
                result = decide_fn(phrase)
                # Multi-Step-fair (Fassaden-Messung 14.07.): waehlt der Kern
                # MEHRERE Schritte, laufen live ALLE - ein Treffer darunter
                # zaehlt. decide_fn darf Plan ODER Liste liefern.
                plans = result if isinstance(result, list) else [result]
                intents = [p.intent for p in plans]
                got = "+".join(intents)
            except Exception as e:  # noqa: BLE001 - API-Fehler EHRLICH als ERR,
                # nicht als Fehlgriff zaehlen (sonst verfaelscht z. B. ein
                # Rate-Limit die Trefferquote und man haengt faelschlich nichts um).
                intents, got = [], f"ERR:{type(e).__name__}"
                errors += 1
            ok = bool(accepted & set(intents))
            cases.append({"phrase": phrase, "got": got, "ok": ok})
            if ok:
                hits += 1
            else:
                misses.append((phrase, got))
        results[expected] = {"hits": hits, "total": len(phrases),
                             "errors": errors, "misses": misses, "cases": cases}
    return results


def format_report(results: dict) -> str:
    lines = ["Migrations-Pruefbatterie (Router-Abloesung, ADR-060 Phase 2):", ""]
    total_hits = total = 0
    for expected, r in results.items():
        total_hits += r["hits"]
        total += r["total"]
        quote = r["hits"] / r["total"] * 100 if r["total"] else 0.0
        marker = "[OK]" if r["hits"] == r["total"] else ("[~] " if quote >= 50 else "[X] ")
        label = "gespraech (kein werkzeug)" if expected == "chat" else expected
        lines.append(f"  {marker} {label}: {r['hits']}/{r['total']} ({quote:.0f}%)")
        for phrase, got in r["misses"]:
            lines.append(f"         miss: {phrase!r} -> {got}")
    overall = total_hits / total * 100 if total else 0.0
    # Getrennte Konten (Sol-Review 14.07.: 13/73 vermischte Modell-Wahl und
    # Rate-Limits): API-Fehler explizit, Quote zusaetzlich NUR ueber die
    # erfolgreich beantworteten Faelle.
    total_err = sum(r.get("errors", 0) for r in results.values())
    answered = total - total_err
    lines += ["", f"  Gesamt: {total_hits}/{total} ({overall:.0f}%)"]
    if total_err:
        quote = total_hits / answered * 100 if answered else 0.0
        lines.append(f"  davon API-Fehler: {total_err} · Treffer unter ERFOLGREICHEN "
                     f"Antworten: {total_hits}/{answered} ({quote:.0f}%)")
    lines.append("  [OK] = sicher umhaengbar · [~] = Prompt/Beispiele nachschaerfen · [X] = noch nicht")
    return "\n".join(lines)


# Argument-Batterie (Lehre 2026-07-12, Netflix/Kaffee): die reine Intent-
# Trefferquote sah zwei Live-Bugs NICHT - der Kern traf den Intent, fuellte aber
# die noetigen Felder falsch/leer. Diese Batterie prueft, ob das PFLICHTFELD da
# ist. (phrase, erwarteter Intent, Pruef-Funktion auf den Plan).
ARG_BATTERY = [
    ("um 16 uhr will ich netflix schauen", "add_entry",
     lambda p: bool(p.parameters.get("text") or p.target)),
    ("erinnere mich morgen um 9 an den zahnarzt", "add_entry",
     lambda p: bool(p.parameters.get("when"))),
    ("setz milch auf die einkaufsliste", "add_to_list",
     lambda p: bool(p.parameters.get("items") or p.target)),
    ("merk dir dass ich meinen kaffee schwarz trinke", "remember_fact",
     lambda p: bool(p.target or p.parameters)),
    ("wie wird das wetter morgen in hamburg", "get_weather",
     lambda p: bool(p.target)),
]


def evaluate_args(decide_fn: Callable[[str], Plan], battery=ARG_BATTERY) -> list[dict]:
    """Prueft je Fall: stimmt der Intent UND ist das noetige Argument-Feld
    gefuellt? Ein umgehaengter Schreib-Intent taugt nur, wenn auch die Argumente
    sauber ausfuehren - genau das fangen wir hier VOR dem Live-Betrieb ab."""
    results: list[dict] = []
    for phrase, expected, check in battery:
        try:
            plan = decide_fn(phrase)
            intent_ok = plan.intent == expected
            arg_ok = intent_ok and bool(check(plan))
            results.append({"phrase": phrase, "expected": expected,
                            "got": plan.intent, "intent_ok": intent_ok, "arg_ok": arg_ok})
        except Exception as e:  # noqa: BLE001 - API-Fehler ehrlich als ERR
            results.append({"phrase": phrase, "expected": expected,
                            "got": f"ERR:{type(e).__name__}", "intent_ok": False, "arg_ok": False})
    return results


def format_arg_report(results: list[dict]) -> str:
    lines = ["", "Argument-Pruefung (fuellt der Kern die noetigen Felder?):"]
    ok = sum(1 for r in results if r["arg_ok"])
    for r in results:
        mark = "[OK]" if r["arg_ok"] else ("[~] " if r["intent_ok"] else "[X] ")
        lines.append(f"  {mark} {r['phrase'][:40]!r} -> {r['got']} (args_ok={r['arg_ok']})")
    lines.append(f"  Args vollstaendig: {ok}/{len(results)}")
    return "\n".join(lines)


def _real_decide_fn(throttle_s: float = 1.3, prefilter: bool = False,
                    facade: bool = False, chooser_model: str = ""):
    """Baut den echten Kern aus der Live-Config (config.json). Ein LLM-Call je
    Aufruf. Ruft `ai.choose_tool` DIREKT (nicht ueber reasoning.decide, das API-
    Fehler still auf chat schluckt) - so propagiert ein Rate-Limit/Netzfehler
    nach oben und evaluate() markiert ihn ehrlich als ERR statt als Fehlgriff.
    `throttle_s` haelt den Batch-Lauf unter dem Tokens-pro-Minute-Limit.

    prefilter=True legt den ECHTEN Werkzeug-Vorfilter (Plan B, core/tool_index)
    davor - exakt die Runtime-Verdrahtung (ToolIndex.select, k aus config).
    So misst die Batterie VOR dem Live-Einschalten, ob der Vorfilter
    Trefferquote kostet (Nachtmodus A3, 13.07.: nur an, wenn nicht)."""
    import os
    import time
    from pathlib import Path

    from core.ai import AIEngine
    from core.config import Config
    from core.tool_schemas import build_tool_schemas

    config = Config.load()
    # Mess-Experiment (--model): den WAEHLER staerker besetzen, ohne die
    # Live-Config anzufassen (Diagnose 'verschachtelte Wahl braucht mehr
    # Modell?', Fassaden-Messung 14.07.).
    if chooser_model:
        import dataclasses

        config = dataclasses.replace(config, model=chooser_model)
    ai = AIEngine(config)
    # Fassaden-Messlatte (ADR-073: verworfen fuer die Produktion, hier als
    # Mess-Werkzeug fuer kuenftige Waehler-Modelle): dieselbe Batterie durch
    # die Zwei-Stufen-Wahl aus scripts/facade_eval.py.
    if facade:
        import importlib.util

        _spec = importlib.util.spec_from_file_location(
            "facade_eval", Path(__file__).resolve().parent / "facade_eval.py")
        _facade_mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_facade_mod)
        two_stage_choose = _facade_mod.two_stage_choose

        tools = []  # Zwei-Stufen-Wahl baut ihre Schemas selbst
    else:
        tools = build_tool_schemas()

    select = None
    if prefilter:
        from core.embeddings import embed_texts
        from core.tool_index import ToolIndex

        embed_key = getattr(config, "openai_api_key", "") or os.environ.get("OPENAI_API_KEY", "")
        embed_model = getattr(config, "embedding_model", "") or "text-embedding-3-small"
        index = ToolIndex(
            Path(config.memory_dir) / "tool_index.json",
            lambda texts: embed_texts(texts, embed_key, embed_model),
        )
        k = int(getattr(config, "tool_prefilter_k", 12) or 12)

        def select(text, schemas):
            return index.select(text, schemas, k=k)

    # Verbrauchs-Konto (Eval-Artefakt, Truth Repair II): je LLM-Call ein
    # Eintrag {model, tokens_in, tokens_out} - die Zwei-Stufen-Wahl macht
    # MEHRERE Calls je Phrase, deshalb hier akkumulieren statt nur den
    # letzten zu lesen. main() ordnet die Eintraege den Faellen zu.
    usage_log: list[dict] = []

    def tracked_choose(user_input, history, offered_tools):
        out = ai.choose_tool(user_input, history, offered_tools)
        u = getattr(ai, "last_tool_usage", None)
        if u:
            usage_log.append(dict(u))
        return out

    def decide(phrase: str) -> Plan:
        if throttle_s:
            time.sleep(throttle_s)
        offered = select(phrase, tools) if select else tools
        if facade:
            # Runde 3: Zwei-Stufen-Wahl wie im Live-Pfad (Fehler propagieren -> ERR).
            choices = two_stage_choose(phrase, [], tracked_choose)
        else:
            choices = tracked_choose(phrase, [], offered)  # Fehler propagieren (-> ERR)
        if not choices:
            return Plan(intent="chat", raw_input=phrase)
        # ALLE gewaehlten Schritte zurueckgeben (live laufen alle) -
        # Argumente wie im Live-Pfad flach abbilden (reasoning._to_plan).
        from core.reasoning import _to_plan

        plans = [_to_plan(phrase, name, args) for name, args in choices]
        return plans if len(plans) > 1 else plans[0]

    # Metadaten fuer das Artefakt (aufgeloest, nicht geraten): das tatsaechlich
    # konfigurierte Waehler-Modell + Provider-Besetzung dieser Messung.
    decide.usage_log = usage_log
    decide.resolved = {
        "waehler_modell": chooser_model or getattr(config, "model", "?"),
        "ai_provider": getattr(config, "ai_provider", "?"),
        "planning_provider": getattr(config, "planning_provider", "") or getattr(config, "ai_provider", "?"),
        "sdk_max_retries": getattr(getattr(ai.provider, "client", None), "max_retries", None),
    }
    return decide


def main(argv: list[str]) -> int:
    prefilter = "--prefilter" in argv
    facade = "--facade" in argv
    save = "--save" in argv
    chooser_model = ""
    if "--model" in argv:
        chooser_model = argv[argv.index("--model") + 1]
        print(f"(Waehler-Modell fuer diese Messung: {chooser_model})\n")
    raw_decide = _real_decide_fn(prefilter=prefilter, facade=facade,
                                 chooser_model=chooser_model)
    # Latenz + Verbrauch JE FALL mitmessen (Sol-Review 14.07.: Modellvergleiche
    # brauchen Einzelfall-Latenzen, Tokens/Kosten + reproduzierbare Artefakte).
    # Die Fall-Reihenfolge von evaluate()/evaluate_args() ist deterministisch
    # (Batterie-Reihenfolge) - Index i hier = Fall i dort.
    import time as _time

    latencies: list[float] = []
    case_usages: list[list[dict]] = []   # je Fall die LLM-Calls (facade: >1)

    def decide_fn(phrase):
        start = _time.monotonic()
        before = len(raw_decide.usage_log)
        try:
            return raw_decide(phrase)
        finally:
            latencies.append(round(_time.monotonic() - start, 2))
            case_usages.append(raw_decide.usage_log[before:])

    if prefilter:
        print("(Werkzeug-Vorfilter AKTIV - misst den Plan-B-Pfad)\n")
    if facade:
        print("(ACHT-WERKZEUGE-FASSADE AKTIV - Messlatte ADR-072 Phase A)\n")
    results = evaluate(decide_fn)
    arg_results = evaluate_args(decide_fn)
    print(format_report(results))
    print(format_arg_report(arg_results))
    if save:
        # JSON-Artefakt je Lauf (docs/evals/, committbar): macht Messungen
        # unabhaengig reproduzierbar/nachlesbar statt nur als Chat-Zitat.
        # Truth Repair II (Sol-Review 14.07.): Commit-SHA, aufgeloestes Modell,
        # SDK-Version, Einzelfall-Latenzen, Tokens/Kosten gehoeren hinein -
        # sonst ist ein Artefakt spaeter nicht mehr einordenbar.
        import json
        from datetime import datetime

        out_dir = ROOT / "docs" / "evals"
        out_dir.mkdir(parents=True, exist_ok=True)
        mode = "facade" if facade else ("prefilter" if prefilter else "flach")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Einzelfall-Latenzen + Verbrauch an die Faelle heften (Reihenfolge =
        # Aufruf-Reihenfolge, siehe decide_fn). Erst Batterie, dann Argumente.
        flat_cases = [c for r in results.values() for c in r["cases"]] + arg_results
        for i, case in enumerate(flat_cases):
            case["latenz_s"] = latencies[i] if i < len(latencies) else None
            calls = case_usages[i] if i < len(case_usages) else []
            case["llm_calls"] = len(calls)
            case["tokens_in"] = sum(c.get("tokens_in") or 0 for c in calls) or None
            case["tokens_out"] = sum(c.get("tokens_out") or 0 for c in calls) or None

        tokens_in = sum(c.get("tokens_in") or 0 for u in case_usages for c in u)
        tokens_out = sum(c.get("tokens_out") or 0 for u in case_usages for c in u)
        artefakt = {
            "zeitpunkt": stamp, "modus": mode,
            "commit": _git_state(),
            "modell": raw_decide.resolved,
            "sdk": _sdk_versions(),
            "gesamt": {
                "hits": sum(r["hits"] for r in results.values()),
                "total": sum(r["total"] for r in results.values()),
                "api_fehler": sum(r.get("errors", 0) for r in results.values()),
            },
            "latenz_s": {"avg": round(sum(latencies) / len(latencies), 2) if latencies else None,
                         "max": max(latencies) if latencies else None},
            "verbrauch": {
                "tokens_in": tokens_in or None,
                "tokens_out": tokens_out or None,
                "kosten_usd": _estimate_cost_usd(
                    raw_decide.resolved.get("waehler_modell", ""), tokens_in, tokens_out),
                "hinweis": ("SDK-interne Retries sind nicht je Fall instrumentiert; "
                            "api_fehler zaehlt endgueltig gescheiterte Faelle."),
            },
            "faelle": {k: v["cases"] for k, v in results.items()},
            "argumente": arg_results,
        }
        path = out_dir / f"eval-{stamp}-{mode}.json"
        path.write_text(json.dumps(artefakt, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nArtefakt gespeichert: {path}")
    return 0


def _git_state() -> dict:
    """Commit-SHA + dirty-Flag des Repos (Artefakt-Einordnung). Fail-soft:
    ohne git kommt ein ehrliches None statt eines Absturzes."""
    import subprocess

    try:
        sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
                                    capture_output=True, text=True, check=True).stdout.strip())
        return {"sha": sha, "dirty": dirty}
    except Exception:  # noqa: BLE001 - Metadaten stoeren die Messung nie
        return {"sha": None, "dirty": None}


def _sdk_versions() -> dict:
    """Versionen der beteiligten SDKs (Artefakt-Einordnung). Fail-soft."""
    import platform
    from importlib.metadata import PackageNotFoundError, version

    out = {"python": platform.python_version()}
    for pkg in ("openai", "anthropic"):
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = None
    return out


# Preisliste NUR fuer die Kosten-Schaetzung im Artefakt (USD je 1M Tokens,
# Stand 2026-01, OpenAI-Listenpreise). Unbekanntes Modell -> kosten_usd=None
# (ehrlich statt geraten); bei Preisaenderung Tabelle + Stand aktualisieren.
_PRICES_USD_PER_1M = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}


def _estimate_cost_usd(model: str, tokens_in: int, tokens_out: int):
    prices = _PRICES_USD_PER_1M.get((model or "").strip())
    if not prices or not (tokens_in or tokens_out):
        return None
    return round((tokens_in * prices[0] + tokens_out * prices[1]) / 1_000_000, 4)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
