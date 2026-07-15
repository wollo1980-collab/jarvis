"""
Command-Center-Datensammlung (ADR-046, Welle 4.3) - liefert die ECHTEN
Kennzahlen fuer das lokale Dashboard. Grundsatz: jede Zahl stammt aus einer
realen Quelle (memory_data/-JSONs, logs/-Textdateien, PROJECT_STATE-Kopf,
Lock-Datei) - keine Kulisse, keine Schaetzwerte.

Strikt READ-ONLY und prozess-fremd: dieses Modul schreibt nichts, erwirbt
keinen Lock und haengt nicht an der Runtime - es liest dieselben Dateien,
die die Runtime atomar schreibt (core/fileio.py). Dass die Lock-Datei
gerade nicht lesbar ist (msvcrt-Sperre der laufenden Instanz), ist selbst
das Laufzeit-Signal.
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.dashboard.data")

# Delegations-Abschlusszeilen aus commands/delegate.py:
# "Repo-Analyse beendet: repo=jarvis status=✓ dauer=26.1s turns=3 kosten=0.1367 ..."
# "Schreib-Delegation beendet: repo=jkc status=✓ dauer=248.0s dateien=4 kosten=0.9500 ..."
# (Scheibe 2 der UI-Kampagne: auch die Kaefig-Laeufe ADR-050 zaehlen - vorher
# sah die Statistik nur Analysen.) Zeilen mit kosten=? (unbekannt) bleiben
# bewusst draussen - lieber eine Zahl weniger als eine geratene.
_DELEGATION_RE = re.compile(
    r"Repo-Analyse beendet: repo=(?P<repo>\S+) status=(?P<status>\S+) "
    r"dauer=(?P<dauer>[\d.]+)s turns=(?P<turns>\d+) kosten=(?P<kosten>[\d.]+)"
)
_WORK_DELEGATION_RE = re.compile(
    r"Schreib-Delegation beendet: repo=(?P<repo>\S+) status=(?P<status>\S+) "
    r"dauer=(?P<dauer>[\d.]+)s dateien=(?P<dateien>\d+) kosten=(?P<kosten>[\d.]+)"
)
_LOG_TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def format_de(iso_text: Optional[str]) -> Optional[str]:
    """ISO 8601 -> deutsches Anzeigeformat (PO-Wunsch 10.07.2026:
    Tag.Monat.Jahr statt Jahr-Monat-Tag). Unparsebares kommt roh zurueck."""
    if not iso_text:
        return iso_text
    try:
        dt = datetime.fromisoformat(iso_text)
    except ValueError:
        return iso_text
    if len(iso_text) == 10:  # reines Datum
        return dt.strftime("%d.%m.%Y")
    return dt.strftime("%d.%m.%Y %H:%M")


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return default


def runtime_status(memory_dir: Path) -> dict:
    """Laeuft Jarvis? Quelle: die Lock-Datei (ADR-026). Drei Faelle:
    fehlt -> aus; nicht lesbar (msvcrt-Sperre) -> AN (der Beweis schlechthin);
    lesbar -> Inhalt pruefen (PID am Leben?)."""
    lock_path = memory_dir / "jarvis.lock"
    if not lock_path.exists():
        return {"running": False, "pid": None, "since": None}
    try:
        info = json.loads(lock_path.read_text(encoding="utf-8"))
    except PermissionError:
        # Aktive Instanz haelt die Datei exklusiv gesperrt.
        return {"running": True, "pid": None, "since": None}
    except (OSError, json.JSONDecodeError):
        return {"running": False, "pid": None, "since": None}

    pid = info.get("pid")
    alive = False
    if isinstance(pid, int):
        try:
            import psutil

            alive = psutil.pid_exists(pid)
        except Exception:  # noqa: BLE001 - Dashboard darf nie werfen
            alive = False
    return {
        "running": alive,
        "pid": pid if alive else None,
        "since": format_de(info.get("timestamp")) if alive else None,
    }


# Abgelaufene Eintraege bleiben nach Faelligkeit noch so lange als Karte
# stehen (PO-Reibung 2026-07-13: der 09:00-Termin stand um 19:36 noch da).
# Lang genug, um eine gerade verpasste Erinnerung zu sehen; danach raeumt
# die Karte sich selbst weg. Frueher weg: ✕-Klick; dauerhaft: GEDAECHTNIS.
_DUE_CARD_GRACE = timedelta(hours=1)


def entries_status(memory_dir: Path, now: Optional[datetime] = None) -> dict:
    """Offene Eintraege (A1) - der Tages-Fokus (PO-Reibung 2026-07-11: 'einen
    Termin am 18.07. muss ich nicht schon heute sehen; besser die taeglich
    relevanten'). Als KARTEN erscheinen nur JETZT relevante Eintraege:
      - `today`     : heute noch anstehend (Zeitpunkt spaeter heute),
      - `due_today` : gerade faellig gewesen ('war faellig'); verschwindet
                      _DUE_CARD_GRACE nach Faelligkeit von selbst
                      (PO-Reibung 2026-07-13, ersetzt 'bis Tagesende'
                      vom Live-Befund 2026-07-10).
    Eintraege an kuenftigen Tagen erscheinen NICHT als Karte - sie stehen im
    Briefing und in der GEDAECHTNIS-Ansicht. `upcoming` (alle kuenftigen inkl.
    heute) traegt sie mit in die Fusszeile ('N Eintraege offen')."""
    now = now or datetime.now()
    entries = _read_json(memory_dir / "entries.json", [])
    today_upcoming = []
    later = []
    due_today = []
    undated = 0
    important = 0
    for e in entries:
        if not isinstance(e, dict):
            continue
        if e.get("important"):
            important += 1
        when = str(e.get("when") or "")
        if not when:
            undated += 1
            continue
        try:
            due = datetime.fromisoformat(when)
        except ValueError:
            continue
        if due >= now:
            if due.date() == now.date():
                today_upcoming.append((due, str(e.get("text", ""))))
            else:
                later.append((due, str(e.get("text", ""))))
        elif now - due <= _DUE_CARD_GRACE:
            due_today.append((due, str(e.get("text", ""))))
    today_upcoming.sort(key=lambda pair: pair[0])
    due_today.sort(key=lambda pair: pair[0], reverse=True)  # juengste zuerst
    return {
        "total": len(entries),
        "upcoming": len(today_upcoming) + len(later),
        "undated": undated,
        "important": important,
        "today": [
            {"when": due.strftime("%H:%M"), "text": text} for due, text in today_upcoming[:3]
        ],
        "due_today": [
            {"when": due.strftime("%H:%M"), "text": text} for due, text in due_today[:2]
        ],
    }


def recent_history(memory_dir: Path, limit: int = 12) -> list:
    """Die letzten Gespraechs-Zeilen (history.json, bereits redigiert) fuer
    den Seiten-Neuladen (PO-Reibung 2026-07-10: 'nach F5 ist der Chat blank
    - ich weiss nicht, was vorher gemacht wurde'). Alle Kanaele teilen sich
    diese History (Konsole/Telegram/Sprache/UI) - genau das ist der Wert."""
    history = _read_json(memory_dir / "history.json", [])
    if not isinstance(history, list):
        return []
    result = []
    for entry in history[-limit:]:
        if not isinstance(entry, dict):
            continue
        role = str(entry.get("role", ""))
        content = str(entry.get("content", "")).strip()
        if role in ("user", "assistant") and content:
            # Zeitstempel (Message.timestamp, ISO) auf HH:MM verkuerzt - fuer
            # die Uhrzeit an der Chat-Zeile (PO-Wunsch 2026-07-11). Fehlt/kaputt
            # -> leer (aeltere Eintraege vor dieser Aenderung haben keinen).
            ts = str(entry.get("timestamp", ""))
            hhmm = ts[11:16] if len(ts) >= 16 and ts[10:11] == "T" else ""
            result.append({"role": role, "content": content, "time": hhmm})
    return result


def lists_status(memory_dir: Path) -> list:
    """Benannte Listen (memory/lists.py) fuer die Tages-Karten: Name, Anzahl
    und eine kurze Vorschau. Leere Listen erscheinen nicht."""
    data = _read_json(memory_dir / "lists.json", {})
    lists = data.get("lists", {}) if isinstance(data, dict) else {}
    result = []
    for name in sorted(lists):
        items = lists[name]
        if not isinstance(items, list) or not items:
            continue
        result.append(
            {
                "name": name,
                "count": len(items),
                "preview": ", ".join(str(i) for i in items[:3]),
            }
        )
    return result


def memory_status(memory_dir: Path) -> dict:
    """Sichtbares Gedaechtnis (PIS-Prinzip): Fakten + Verlaufs-Umfang."""
    facts = _read_json(memory_dir / "long_term.json", [])
    history = _read_json(memory_dir / "history.json", [])
    last_fact = None
    if isinstance(facts, list) and facts:
        last = facts[-1]
        if isinstance(last, dict):
            last_fact = str(last.get("text", ""))
    return {
        "facts": len(facts) if isinstance(facts, list) else 0,
        "last_fact": last_fact,
        "history_entries": len(history) if isinstance(history, list) else 0,
    }


_MEMORY_VIEW_CAP = 50


def memory_view(memory_dir: Path) -> dict:
    """Die GEDAECHTNIS-Ansicht (Nachtplan Scheibe 4, PIS-Prinzip
    'sichtbares Gedaechtnis'): alle Fakten (mit Kategorie), alle offenen
    Eintraege (mit Termin/⭐/↻) und alle Listen mit Posten - gedeckelt,
    fail-safe, read-only. Loeschen laeuft ueber die stillen Endpunkte des
    Browser-Kanals, nie ueber diesen lesenden Prozess."""
    facts_raw = _read_json(memory_dir / "long_term.json", [])
    facts = [
        {"text": str(f.get("text", "")), "category": str(f.get("category", ""))}
        for f in (facts_raw if isinstance(facts_raw, list) else [])
        if isinstance(f, dict) and f.get("text")
    ][-_MEMORY_VIEW_CAP:]

    entries = []
    try:
        from memory.entries import EntryStore, format_when

        for e in EntryStore(memory_dir).list_open()[:_MEMORY_VIEW_CAP]:
            entries.append(
                {
                    "text": e.text,
                    # mark_past (Kundenreview 13.07.): auch die Gedaechtnis-
                    # Ansicht nennt Vergangenes 'war fällig ...' - dieselbe
                    # Wahrheit wie Eintragsliste und Tageskarten.
                    "when": format_when(e.when, mark_past=True) if e.when else "",
                    "important": e.important,
                    "repeat": e.repeat,
                }
            )
    except Exception:  # noqa: BLE001 - Ansicht darf nie werfen
        logger.debug("Gedaechtnis-Ansicht: Eintraege nicht lesbar.", exc_info=True)

    lists_raw = _read_json(memory_dir / "lists.json", {})
    lists_data = lists_raw.get("lists", {}) if isinstance(lists_raw, dict) else {}
    lists = [
        {"name": name, "items": [str(i) for i in items][:_MEMORY_VIEW_CAP]}
        for name, items in sorted(lists_data.items())
        if isinstance(items, list) and items
    ]

    return {"facts": facts, "entries": entries, "lists": lists}


def delegation_stats(log_dir: Path) -> dict:
    """Agenten-Delegationen aus den Runtime-Logs (kosten= ist API-Gegenwert,
    nicht abgerechnet - Laeufe laufen ueber das Abo, siehe Kostenbilanz 2.3)."""
    runs = []
    for log_file in sorted(log_dir.glob("*-runtime.log")):
        try:
            content = log_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Beide Lauf-Arten in Log-Reihenfolge mischen (Position im Text),
        # damit "last" wirklich der juengste Lauf ist - nicht der juengste
        # einer Art.
        found = [("analyse", m) for m in _DELEGATION_RE.finditer(content)]
        found += [("arbeit", m) for m in _WORK_DELEGATION_RE.finditer(content)]
        found.sort(key=lambda pair: pair[1].start())
        for kind, match in found:
            run = {
                "kind": kind,
                "repo": match.group("repo"),
                "ok": "✓" in match.group("status"),
                "dauer": float(match.group("dauer")),
                "kosten": float(match.group("kosten")),
            }
            if kind == "analyse":
                run["turns"] = int(match.group("turns"))
            else:
                run["dateien"] = int(match.group("dateien"))
            runs.append(run)
    ok_runs = [r for r in runs if r["ok"]]
    total_cost = sum(r["kosten"] for r in runs)
    return {
        "runs": len(runs),
        "ok": len(ok_runs),
        "total_cost_usd": round(total_cost, 4),
        "avg_cost_usd": round(total_cost / len(runs), 4) if runs else 0.0,
        "last": runs[-1] if runs else None,
    }


# Reasoning-Schatten-Zeilen (ADR-060 Scheibe 3c) aus core/planner.py:
# "Reasoning-Schatten [DIFF]: router=chat kern=open_program (target='excel')"
# router kann mehrteilig sein ("open_program+chat"), kern ist ein Intent,
# target ist das repr() des Ziels (None oder 'text'). $ (MULTILINE) verankert
# am Zeilenende, damit target auch ein ')' enthalten darf.
_SHADOW_RE = re.compile(
    r"Reasoning-Schatten \[(?P<verdict>MATCH|DIFF)\]: "
    r"router=(?P<router>\S+) kern=(?P<kern>\S+) \(target=(?P<target>.*)\)$",
    re.MULTILINE,
)


def shadow_stats(log_dir: Path) -> dict:
    """Reasoning-Schatten-Bilanz (ADR-060 Scheibe 3c) aus den Runtime-Logs:
    wie oft der denkende Kern mit dem Router uebereinstimmte (MATCH) und wo er
    abwich (DIFF) - die Datengrundlage fuer den Umschalt-Entscheid, sobald
    `reasoning_shadow` an ist. Read-only wie die uebrigen Kennzahlen. Bei
    ausgeschaltetem Schatten (keine Zeilen) sind alle Zahlen 0/leer/None -
    ehrlich statt geschaetzt. `top_diffs` nennt die haeufigsten Router->Kern-
    Uneinigkeiten (Kandidaten zum genauen Hinschauen); `last` ist die juengste
    Beobachtung (Log-Reihenfolge ueber nach Datum sortierte Dateien)."""
    total = 0
    matches = 0
    diff_pairs: Counter = Counter()
    last: Optional[dict] = None
    for log_file in sorted(log_dir.glob("*-runtime.log")):
        try:
            content = log_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _SHADOW_RE.finditer(content):
            total += 1
            if m.group("verdict") == "MATCH":
                matches += 1
            else:
                diff_pairs[(m.group("router"), m.group("kern"))] += 1
            last = {
                "verdict": m.group("verdict"),
                "router": m.group("router"),
                "kern": m.group("kern"),
                "target": m.group("target"),
            }
    return {
        "total": total,
        "match": matches,
        "diff": total - matches,
        "match_rate": round(matches / total, 3) if total else 0.0,
        "top_diffs": [
            {"router": router, "kern": kern, "count": count}
            for (router, kern), count in diff_pairs.most_common(5)
        ],
        "last": last,
    }


def format_shadow_report(stats: dict) -> str:
    """Menschenlesbarer Kurzbericht aus shadow_stats() - fuer das CLI
    scripts/shadow_report.py (und spaeter ggf. eine Dashboard-Kachel)."""
    total = stats.get("total", 0)
    if not total:
        return ("Reasoning-Schatten: noch keine Beobachtungen "
                "(reasoning_shadow aus oder noch kein Log).")
    lines = [
        "Reasoning-Schatten (Router vs. denkender Kern):",
        f"  Beobachtungen: {total}",
        f"  MATCH: {stats['match']}  ·  DIFF: {stats['diff']}  ·  "
        f"Uebereinstimmung: {stats['match_rate'] * 100:.1f}%",
    ]
    if stats.get("top_diffs"):
        lines.append("  Haeufigste Abweichungen (router -> kern):")
        for d in stats["top_diffs"]:
            lines.append(f"    {d['count']}x  {d['router']} -> {d['kern']}")
    return "\n".join(lines)


# Scheibe 7 (Nachtplan 11.07.): Verbrauchs-/Latenz-/Startmarker-Zeilen.
_USAGE_RE = re.compile(r"Verbrauch: provider=\S+ modell=\S+ tokens_in=(\d+) tokens_out=(\d+)")
_LATENCY_RE = re.compile(r"Latenz: Transkription [\d.]+s · Verarbeitung ([\d.]+)s")
# Start-Marker fuer die Uptime: MUSS zur echten Scheduler-Start-Logzeile passen
# (jarvis_runtime.start_scheduler: "Scheduler gestartet (Poll alle 30s ...)").
# Der fruehere "Erinnerungs-Scheduler gestartet" driftete vom Log ab -> Uptime
# fand heute keinen Marker und rechnete vom Vortag (falsche 31h). Stabiler
# Teilstring "Scheduler gestartet" (matcht auch die alte Zeile, Test bleibt gruen).
_STARTUP_MARKER = "Scheduler gestartet"


def _read_log(log_dir: Path, day: date) -> str:
    try:
        return (log_dir / f"{day.isoformat()}-runtime.log").read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return ""


def usage_today(log_dir: Path, today: Optional[date] = None) -> dict:
    """KI-Verbrauch heute aus den Verbrauch:-Zeilen (Scheibe 7) - nur
    Zaehlwerte (Aufrufe, Token), nie Inhalte."""
    content = _read_log(log_dir, today or date.today())
    calls, tokens_in, tokens_out = 0, 0, 0
    for match in _USAGE_RE.finditer(content):
        calls += 1
        tokens_in += int(match.group(1))
        tokens_out += int(match.group(2))
    return {"calls": calls, "tokens_in": tokens_in, "tokens_out": tokens_out}


def avg_voice_response_seconds(log_dir: Path, today: Optional[date] = None) -> Optional[float]:
    """Rollende Antwortzeit heute aus den Latenz-Zeilen des Sprachkanals
    (Messinstrument der Latenz-Scheibe) - ehrlich als 'Sprache' beschriftet,
    weil nur dieser Kanal Latenzen loggt."""
    content = _read_log(log_dir, today or date.today())
    values = [float(m.group(1)) for m in _LATENCY_RE.finditer(content)]
    return round(sum(values) / len(values), 1) if values else None


def uptime_seconds(log_dir: Path, now: Optional[datetime] = None) -> Optional[int]:
    """Laufzeit des aktuellen Runtime-Prozesses: Abstand zum LETZTEN
    Start-Marker (heute, sonst gestern - laenger laufende Prozesse zeigen
    ehrlich nichts statt einer geratenen Zahl)."""
    now = now or datetime.now()
    for day in (now.date(), date.fromordinal(now.date().toordinal() - 1)):
        content = _read_log(log_dir, day)
        last_marker = None
        for line in content.splitlines():
            if _STARTUP_MARKER in line:
                stamp = _LOG_TIMESTAMP_RE.match(line)
                if stamp:
                    last_marker = stamp.group(1)
        if last_marker:
            try:
                started = datetime.strptime(last_marker, "%Y-%m-%d %H:%M:%S")
                return max(0, int((now - started).total_seconds()))
            except ValueError:
                return None
    return None


def activity_today(log_dir: Path, today: Optional[date] = None) -> dict:
    """Heutige Aktivitaet aus dem Tages-Log: verarbeitete Anfragen
    (Planner-Aufrufe), Wake-Word-Erkennungen, letzter Log-Zeitstempel.
    Es werden nur ZAHLEN erhoben - nie Inhalte (Transkript-Grundsatz)."""
    today = today or date.today()
    log_file = log_dir / f"{today.isoformat()}-runtime.log"
    requests = 0
    wake_words = 0
    last_seen = None
    try:
        content = log_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"requests": 0, "wake_words": 0, "last_seen": None}
    for line in content.splitlines():
        if "Router: task=planning" in line:
            requests += 1
        if "Wake-Word erkannt" in line:
            wake_words += 1
        stamp = _LOG_TIMESTAMP_RE.match(line)
        if stamp:
            last_seen = stamp.group(1)
    return {"requests": requests, "wake_words": wake_words, "last_seen": last_seen}


# Wetter-Cache (Scheibe 2, ADR-046/047): das UI pollt alle paar Sekunden -
# Open-Meteo wird trotzdem nur alle 30 Minuten gefragt. Auch Fehlschlaege
# werden gecacht (offline nicht haemmern). Fail-safe: None = keine Karte.
_WEATHER_TTL_SECONDS = 1800.0
_weather_cache: dict = {}


def weather_summary(location: str) -> Optional[dict]:
    """Heutiges Wetter fuer die Tages-Karte - echte Quelle (Open-Meteo,
    core/weather.py), gecacht, niemals werfend."""
    if not location:
        return None
    import time as _time

    cached = _weather_cache.get(location)
    if cached and _time.monotonic() - cached[0] < _WEATHER_TTL_SECONDS:
        return cached[1]
    data = None
    try:
        from core.weather import get_forecast

        forecast = get_forecast(location)
        data = {
            "place": forecast.place,
            "condition": forecast.condition,
            "temp_min": round(forecast.temp_min),
            "temp_max": round(forecast.temp_max),
            "rain": forecast.rain_probability,
            # Tagesverlauf (2026-07-10): Jetzt-Wert + Bloecke fuer die Karte.
            "current": (
                round(forecast.current_temp) if forecast.current_temp is not None else None
            ),
            "segments": [
                {"label": s.label, "temp": round(s.temp), "rain": s.rain_probability}
                for s in forecast.segments
            ],
        }
    except Exception:  # noqa: BLE001 - Dashboard darf nie werfen
        logger.debug("Wetter fuer die Tages-Karte nicht abrufbar.", exc_info=True)
    _weather_cache[location] = (_time.monotonic(), data)
    return data


# News-Cache (PO-Wunsch 2026-07-10: "mehr im Dashboard"): Top-Schlagzeilen
# aus den konfigurierten Feeds, alle 15 Minuten frisch - der Sekunden-Poll
# des UIs haemmert nie die Feeds. Fail-safe None = kein Panel.
_NEWS_TTL_SECONDS = 900.0
_news_cache: dict = {}


def news_summary(feeds: Optional[list]) -> Optional[dict]:
    """Top-3-Schlagzeilen fuer das UI-Panel - echte Quelle (RSS,
    core/news_reader.py), gecacht, niemals werfend."""
    if not feeds:
        return None
    import time as _time

    key = tuple(feeds)
    cached = _news_cache.get(key)
    if cached and _time.monotonic() - cached[0] < _NEWS_TTL_SECONDS:
        return cached[1]
    data = None
    try:
        from core.news_reader import fetch_headlines

        headlines = fetch_headlines(list(feeds), limit=3)
        if headlines:
            sources = {h.source for h in headlines}
            data = {
                "source": sources.pop() if len(sources) == 1 else "mehrere Quellen",
                "items": [h.title for h in headlines],
            }
    except Exception:  # noqa: BLE001 - Dashboard darf nie werfen
        logger.debug("Schlagzeilen fuer das UI-Panel nicht abrufbar.", exc_info=True)
    _news_cache[key] = (_time.monotonic(), data)
    return data


# Vorschlags-Karte (Angestellten-Vision Stufe 3, PO-Go 11.07.2026):
# der juengste OFFENE Eigenvorschlag (plan_next_step-Artefakt) erscheint
# als Karte - Vorschlag statt Aktion. Status-Konzept im Artefakt:
# "<!-- status: offen -->" -> beim Landen/Verwerfen auf umgesetzt/
# verworfen nachgefuehrt. Ohne status-Zeile gilt ein Altbestand als
# unbewertet und erscheint NICHT (nie Erledigtes als offen zeigen).
_PROPOSAL_OPEN_RE = re.compile(r"<!--\s*status:\s*offen\s*-->", re.IGNORECASE)
_PROPOSAL_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_PROPOSAL_CREATED_RE = re.compile(r"erstellt (\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2})")


def open_impulses(memory_dir: Path) -> list:
    """Offene proaktive Impulse (ADR-054) fuer die Dashboard-Karten - direkt
    aus impulses.json gelesen (der Dashboard-Prozess ist getrennt von der
    Runtime, die die Impulse legt; Datei ist die Bruecke). Fail-safe []."""
    data = _read_json(memory_dir / "impulses.json", {})
    if not isinstance(data, dict):
        return []
    items = data.get("open", [])
    if not isinstance(items, list):
        return []
    # Tageslage-Regel AUCH hier (Live-Befund 15.07.: die 14.07.-Regel sass
    # nur in ImpulseStore.list_open - DIESER getrennte Lese-Prozess zeigte
    # die Karten vom 13./14. weiter an). Read-only: nur filtern, nie
    # schreiben; das Aufraeumen der Datei erledigt die Runtime beim Lesen.
    today = datetime.now().date().isoformat()
    out = []
    for item in items:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        if str(item.get("created", ""))[:10] != today:
            continue
        out.append({
            "id": str(item.get("id", "")),
            "key": str(item.get("key", "")),
            "kind": str(item.get("kind", "")),
            "title": str(item.get("title", "")),
            "detail": str(item.get("detail", "")),
            "created": str(item.get("created", "")),
        })
    # Juengste zuerst - dieselbe Ordnung wie ImpulseStore.list_open().
    return sorted(out, key=lambda i: i["created"], reverse=True)


def open_proposal(memory_dir: Path) -> Optional[dict]:
    """Der juengste offene Jarvis-Vorschlag fuer die Karte - fail-safe None."""
    try:
        files = sorted((memory_dir / "proposals").glob("*.md"), reverse=True)
    except OSError:
        return None
    for path in files:
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            continue
        if not _PROPOSAL_OPEN_RE.search(head):
            continue
        title = _PROPOSAL_TITLE_RE.search(head)
        created = _PROPOSAL_CREATED_RE.search(head)
        return {
            "title": title.group(1).strip() if title else path.stem,
            "created": f"{created.group(3)}.{created.group(2)}.{created.group(1)} {created.group(4)}" if created else "",
            "file": path.name,
        }
    return None


def dismiss_proposal(memory_dir: Path, filename: str) -> bool:
    """Setzt den Status eines Vorschlags-Artefakts auf 'verworfen' (UI-✕,
    PO-Reibung 2026-07-11: der Vorschlag hing sonst ewig). Akzeptiert NUR
    einen Dateinamen, keinen Pfad (fail-closed gegen Traversal). True, wenn
    eine offene Statuszeile ersetzt wurde; sonst False (fail-safe, nie
    werfend)."""
    name = Path(str(filename)).name  # nur Basename - kein Verzeichniswechsel
    if not name.endswith(".md"):
        return False
    path = memory_dir / "proposals" / name
    try:
        if not path.is_file():
            return False
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    new_text, n = _PROPOSAL_OPEN_RE.subn("<!-- status: verworfen -->", text, count=1)
    if n == 0:
        return False  # kein offener Vorschlag (schon verworfen/umgesetzt)
    try:
        path.write_text(new_text, encoding="utf-8")
    except OSError:
        return False
    return True


# Hinweis (2026-07-11): Die fruehere briefing_summary() fuer die
# Dashboard-Briefing-Karte ist ENTFERNT - die Karte war eine Wall of Text
# und wiederholte Wetter + Lage (eigene Kacheln/Panels). Das Dashboard IST
# das visuelle Briefing; der warme Morgen-Satz lebt im Untertitel des UIs.
# Der gesprochene "Briefing"-Befehl (commands/briefing.py) bleibt davon
# unberuehrt - dort, ohne Kacheln, ist der lineare Text der Wert.


def system_load() -> Optional[dict]:
    """CPU-/RAM-Auslastung (psutil) - dieselbe echte Quelle wie
    system_status, nur als Zahl fuers UI. Fail-safe None."""
    try:
        import psutil

        return {
            "cpu": round(psutil.cpu_percent(interval=None)),
            "ram": round(psutil.virtual_memory().percent),
        }
    except Exception:  # noqa: BLE001
        return None


def llm_lineup(config) -> dict:
    """Die ECHTE Modell-Besetzung aus der Config (UI-Kampagne Scheibe 1,
    'BESETZUNG'-Kachel) - bewusster Gegenentwurf zum Fantasie-Provider-Grid
    kommerzieller Nachahmer: gezeigt wird ausschliesslich, was wirklich
    verdrahtet ist. Reine Config-Werte, kein Verbindungs-Test (das waere
    eine Behauptung, die dieser lesende Prozess nicht pruefen kann)."""
    provider = str(getattr(config, "ai_provider", "") or "")
    planning_provider = str(getattr(config, "planning_provider", "") or "") or provider
    answer_provider = str(getattr(config, "answer_provider", "") or "") or provider
    base_model = str(getattr(config, "model", "") or "")
    claude_model = str(getattr(config, "claude_model", "") or "")

    def _model(prov: str, override: str = "") -> str:
        if prov == "claude":
            return claude_model
        return override or base_model

    tts = None
    if getattr(config, "tts_enabled", False):
        backend = str(getattr(config, "tts_backend", "") or "")
        tts = {"backend": backend, "model": "", "voice": ""}
        if backend == "openai":
            tts["model"] = str(getattr(config, "openai_tts_model", "") or "")
            tts["voice"] = str(getattr(config, "openai_tts_voice", "") or "")
    # Agenten-Arm (PO-Befund 2026-07-10 "Claude CLI fehlt in der Besetzung"):
    # Name aus der Backend-Klasse, die die Verdrahtung tatsaechlich injiziert
    # (main.py/jarvis_runtime.py, ADR-033/036 + PO-Entscheidung "nur Claude
    # Code CLI erstmal") - gezeigt nur, wenn Delegation ueberhaupt
    # freigeschaltet ist (agent_repos/agent_write_repos nicht leer).
    agent = None
    if (getattr(config, "agent_repos", None) or getattr(config, "agent_write_repos", None)):
        from core.agent_backend import ClaudeCodeBackend

        agent = {"backend": ClaudeCodeBackend.name}
    return {
        "planner": {"provider": planning_provider, "model": _model(planning_provider)},
        "answer": {
            "provider": answer_provider,
            "model": _model(answer_provider, str(getattr(config, "answer_model", "") or "")),
        },
        "transcription": {"model": str(getattr(config, "transcription_model", "") or "")},
        "tts": tts,
        "agent": agent,
    }


def project_version(project_state_path: Path) -> dict:
    """Version + Teststand aus dem maschinenlesbaren PROJECT_STATE-Kopf."""
    version = ""
    tests = 0
    try:
        head = project_state_path.read_text(encoding="utf-8")[:1000]
        version_match = re.search(r'^version:\s*"?([^"\n]+)"?', head, re.MULTILINE)
        tests_match = re.search(r"^tests:\s*(\d+)", head, re.MULTILINE)
        if version_match:
            version = version_match.group(1).strip()
        if tests_match:
            tests = int(tests_match.group(1))
    except OSError:
        pass
    return {"version": version, "tests": tests}


def collect_status(
    memory_dir: Path,
    log_dir: Path,
    project_state_path: Path,
    weather_location: str = "",
    news_feeds: Optional[list] = None,
) -> dict:
    """Alles fuer /api/status - jede Kennzahl aus einer realen Quelle."""
    return {
        "generated_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "runtime": runtime_status(memory_dir),
        "entries": entries_status(memory_dir),
        "lists": lists_status(memory_dir),
        "history": recent_history(memory_dir, limit=20),
        "memory": memory_status(memory_dir),
        "memory_view": memory_view(memory_dir),
        "delegations": delegation_stats(log_dir),
        "activity": activity_today(log_dir),
        "project": project_version(project_state_path),
        "usage": usage_today(log_dir),
        "avg_voice_seconds": avg_voice_response_seconds(log_dir),
        "uptime_seconds": uptime_seconds(log_dir),
        "weather": weather_summary(weather_location),
        "news": news_summary(news_feeds),
        "proposal": open_proposal(memory_dir),
        "impulses": open_impulses(memory_dir),
        "system": system_load(),
    }
