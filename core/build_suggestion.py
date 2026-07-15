"""
Proaktiver Bau-Vorschlag (ADR-067 Stufe 1) - „sprudelt Ideen und baut selbst".

Aus dem, was Jarvis BEOBACHTET (Nutzungs-Statistik + jüngste Reibungen), leitet er
HÖCHSTENS EINE konkrete, klein-baubare Werkzeug-Idee ab und legt sie dem Nutzer
vor - MIT dem wörtlichen Auslöse-Satz. Gebaut wird NIE automatisch: der Nutzer
sagt selbst „Bau mir <name>" und löst damit die bestehende, bestätigte Bau-
Pipeline aus (build_project, sandboxed, niemals Jarvis' eigenes Repo).

Geerdet gegen Luftschlösser (wie propose_ideas): nur wirklich Baubares, nichts,
das Jarvis schon kann; sonst „KEINE". Der LLM-Aufruf ist injiziert (testbar).
"""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger("jarvis.build_suggestion")

# generate_fn(system, user_text) -> Text (z. B. AIEngine.generate).
GenerateFn = Callable[[str, str], str]

_SYSTEM = (
    "Du bist Jarvis. Du schlaegst dem Nutzer PROAKTIV genau EIN kleines, von einem "
    "Agenten baubares Werkzeug vor, das ihm echte manuelle Arbeit abnimmt oder eine "
    "wiederkehrende Reibung loest."
)

_PROMPT = (
    "Aus den Nutzungsmustern und Reibungen unten: schlage GENAU EIN kleines, klar "
    "baubares Werkzeug vor (Python-CLI/Skript/kleine Automation).\n"
    "EISERNE REGELN:\n"
    "- Nur etwas WIRKLICH Sinnvolles, das der Nutzer sonst manuell macht oder das "
    "eine echte Reibung loest. Gibt es das nicht, antworte NUR mit dem Wort: KEINE.\n"
    "- NIEMALS ein Werkzeug, das Sicherheitsmechanik entfernt, umgeht oder "
    "abschaltet (Bestaetigungen, Rueckfragen, Gates, Allowlists). Bestaetigungen "
    "sind ABSICHT, keine Reibung - wirkt eine Rueckfrage kaputt, ist das ein "
    "REPARATUR-Fall, kein Werkzeug-Fall: antworte KEINE.\n"
    "- KEINE Luftschloesser; nichts, das Jarvis schon kann; keine grosse App.\n"
    "- Antworte in GENAU EINEM kurzen Absatz in dieser Form:\n"
    "  'Mir ist aufgefallen: <Muster in wenigen Worten>. Ich koennte dir «<kurzer-"
    "name>» bauen, das <was es tut>. Sag «Bau mir <kurzer-name>», dann lege ich los.'\n\n"
    "=== SCHON GEBAUT (NICHT erneut vorschlagen, auch nichts sehr Aehnliches) ===\n{skills}\n\n"
    "=== NUTZUNG (Faehigkeit: Anzahl) ===\n{usage}\n\n"
    "=== JUENGSTE REIBUNGEN (Eingabe -> Antwort) ===\n{frictions}"
)


def usage_text(counts: dict) -> str:
    """Nutzungs-Zaehlwerte je Intent als kompakte Liste (haeufigste zuerst)."""
    if not counts:
        return "(noch keine Nutzungsdaten)"
    totals = sorted(
        ((intent, sum(int(v) for v in buckets.values())) for intent, buckets in counts.items()),
        key=lambda pair: pair[1], reverse=True,
    )
    return "\n".join(f"- {intent}: {count}x" for intent, count in totals[:20])


def frictions_text(episodes: list[dict], limit: int = 8) -> str:
    """Jüngste Reibungen (Fehlgriffe/Rueckfragen) als Beispiele."""
    lines = []
    for ep in episodes:
        resp = (ep.get("response") or "").strip()
        if "✗" in resp or resp.startswith("?"):
            lines.append(f"- «{ep.get('user_input', '')}» -> {resp[:100]}")
        if len(lines) >= limit:
            break
    return "\n".join(lines) or "(keine auffaelligen Reibungen)"


# Sicherheits-Riegel (Live-Befund 15.07.: vorgeschlagen wurde ein Tool, das
# Kalender-Termine "ohne Bestaetigung" loescht - eine Gate-Umgehung). Der
# Prompt verbietet das UND dieser deterministische Filter erzwingt es
# (fail-closed gegen Prompt-Drift). Kleinschreibung, Umlaut-tolerant.
_GATE_BYPASS_PATTERNS = (
    "ohne bestätigung", "ohne bestaetigung", "ohne rückfrage", "ohne rueckfrage",
    "ohne nachfrage", "ohne freigabe", "keine bestätigung", "keine bestaetigung",
    "bestätigung umgeh", "bestaetigung umgeh", "bestätigung abschalt",
    "bestaetigung abschalt", "bestätigung entfern", "bestaetigung entfern",
    "bestätigung übersp", "bestaetigung uebersp", "sicherheitsstufe senk",
)


def _bypasses_security(text: str) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in _GATE_BYPASS_PATTERNS)


def suggest_build(usage: str, frictions: str, generate_fn: GenerateFn,
                  existing_skills: "list[str] | None" = None) -> str:
    """Liefert den fertigen Bau-Vorschlag (ein Absatz mit Auslöse-Satz) oder ''
    (keine sinnvolle Idee / LLM-Fehler / Muell / Sicherheits-Umgehung). Fail-safe.

    `existing_skills` (Plan A1): Namen bereits gebauter Faehigkeiten - sie werden
    dem LLM als „nicht erneut vorschlagen" mitgegeben (kein Doppel-Bau)."""
    skills_text = ", ".join(s for s in (existing_skills or []) if s) or "(noch nichts gebaut)"
    try:
        out = (generate_fn(_SYSTEM, _PROMPT.format(usage=usage or "(keine)",
                                                   frictions=frictions or "(keine)",
                                                   skills=skills_text)) or "").strip()
    except Exception:  # noqa: BLE001 - stoert nie
        logger.warning("Bau-Vorschlag: LLM-Fehler (ignoriert).", exc_info=True)
        return ""
    if not out or out.strip().rstrip(".").upper() == "KEINE" or out.upper().startswith("KEINE"):
        return ""
    if "Bau mir" not in out:                    # Muell-Schutz: der Auslöse-Satz MUSS da sein
        return ""
    if _bypasses_security(out):
        logger.warning("Bau-Vorschlag verworfen (Gate-Umgehung): %s", out[:120])
        return ""
    return out
