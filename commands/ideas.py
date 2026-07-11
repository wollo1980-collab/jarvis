"""
Ideen-Befehl (Angestellten-Vision Stufe 1, 11.07.2026) - "Was koennten wir
machen?" laesst Jarvis mit KONKRETEN, GEERDETEN Vorschlaegen sprudeln.

Erdung statt Luftschloss: der Vorschlags-Prompt bekommt ausschliesslich
ECHTE Quellen - den Faehigkeits-Katalog (Registry-Beschreibungen), die
tatsaechliche Nutzung (Gewohnheits-Statistik ADR-053: welche Faehigkeit
wie oft), und den aktuellen Stand (offene Eintraege, Listen, Fakten).
Die eiserne Regel steht im Prompt: NUR existierende Faehigkeiten
vorschlagen, jede Idee mit dem woertlichen Ausloese-Satz. Vorschlagen,
nie handeln (Governance-Invariante).

Stufe 0, ein einzelner LLM-Aufruf (AIEngine.generate, Sekunden).
configure() bekommt die AI-Engine und die geteilten Datenquellen.
"""
from __future__ import annotations

import logging
from typing import Optional

from core.models import Plan, Result, Status

logger = logging.getLogger("jarvis.commands.ideas")

_ai = None
_habit_stats = None
_entry_store = None
_list_store = None

_CAP_CAPABILITIES = 6000

_IDEAS_PROMPT = (
    "Du bist die Ideen-Faehigkeit von Jarvis, einem lokalen Assistenten. "
    "Der Nutzer fragt: 'Was koennten wir machen?' Antworte wie ein guter "
    "Mitarbeiter: 3 bis 4 KONKRETE Vorschlaege, was er JETZT mit Jarvis "
    "tun koennte.\n\n"
    "EISERNE REGELN:\n"
    "- NUR Faehigkeiten aus dem Katalog unten - erfinde NIEMALS eine "
    "Faehigkeit, die dort nicht steht (keine Luftschloesser).\n"
    "- Jede Idee endet mit dem woertlichen Satz zum Ausloesen, in "
    "Anfuehrungszeichen (z. B. «Sag einfach: 'Briefing'»). Der "
    "Ausloese-Satz ist ein NATUERLICHER deutscher Satz, wie ihn der "
    "Nutzer sprechen wuerde - NIEMALS der technische Befehlsname aus "
    "dem Katalog (falsch: 'analyze_pc', richtig: 'Analysiere meinen PC').\n"
    "- Bevorzuge UNGENUTZTE oder selten genutzte Faehigkeiten (siehe "
    "Nutzungs-Zahlen) und Kombinationen mit dem aktuellen Stand (offene "
    "Punkte, Listen).\n"
    "- Kurz und sprechtauglich: nummerierte Punkte, je 1-2 Saetze, kein "
    "Markdown-Fett.\n"
    "- Du schlaegst nur vor - du fuehrst nichts aus."
)


def configure(ai, habit_stats, entry_store, list_store) -> None:
    """Von main.py/jarvis_runtime.py mit den GETEILTEN Instanzen verdrahtet."""
    global _ai, _habit_stats, _entry_store, _list_store
    _ai = ai
    _habit_stats = habit_stats
    _entry_store = entry_store
    _list_store = list_store


def _capabilities_text() -> str:
    """Der ehrliche Faehigkeits-Katalog: Namen + ERSTER Beschreibungs-Satz
    aus der Registry (dieselbe Quelle wie der Planner-Prompt) - kompakt,
    damit ALLE Faehigkeiten in den Kontext passen (Vollstaendigkeit schlaegt
    Detailtiefe: eine fehlende Faehigkeit kann nie vorgeschlagen werden)."""
    from commands import REGISTRY

    lines = []
    for name in sorted(REGISTRY):
        description = getattr(REGISTRY[name], "description", "") or ""
        first_sentence = description.split(". ")[0].strip()
        lines.append(f"- {name}: {first_sentence}")
    text = "\n".join(lines)
    return text[:_CAP_CAPABILITIES] + (" …[gekürzt]" if len(text) > _CAP_CAPABILITIES else "")


def _usage_text() -> str:
    """Tatsaechliche Nutzung je Faehigkeit (Gesamt-Zaehlwerte aus der
    Gewohnheits-Statistik) - 'nie benutzt' ist die wertvollste Information."""
    if _habit_stats is None:
        return "(keine Nutzungsdaten)"
    try:
        with _habit_stats._lock:  # noqa: SLF001 - bewusst: geteilte Instanz
            counts = _habit_stats._read()["counts"]  # noqa: SLF001
    except Exception:  # noqa: BLE001
        return "(keine Nutzungsdaten)"
    if not counts:
        return "(noch keine Nutzungsdaten - Statistik laeuft erst seit kurzem)"
    totals = sorted(
        ((intent, sum(int(v) for v in buckets.values())) for intent, buckets in counts.items()),
        key=lambda pair: pair[1], reverse=True,
    )
    return "\n".join(f"- {intent}: {count}x" for intent, count in totals[:25])


def _state_text() -> str:
    parts = []
    try:
        if _entry_store is not None:
            entries = _entry_store.list_open()
            dated = sum(1 for e in entries if e.when)
            undated = len(entries) - dated
            parts.append(f"Offene Eintraege: {dated} terminiert, {undated} Merkposten.")
    except Exception:  # noqa: BLE001
        pass
    try:
        if _list_store is not None:
            overview = _list_store.overview()
            if overview:
                parts.append(
                    "Listen: " + ", ".join(f"{name} ({count})" for name, count in overview[:5]) + "."
                )
    except Exception:  # noqa: BLE001
        pass
    return " ".join(parts) or "(kein besonderer Stand)"


class ProposeIdeasCommand:
    name = "propose_ideas"
    description = (
        "Schlaegt konkrete, sofort ausprobierbare Dinge vor, die der Nutzer "
        "mit Jarvis tun koennte (z. B. 'was koennten wir machen?', 'hast du "
        "Ideen?', 'was schlaegst du vor?'). Geerdet in den echten "
        "Faehigkeiten und der tatsaechlichen Nutzung - schlaegt nur vor, "
        "fuehrt nichts aus. Read-only, Stufe 0."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        if _ai is None:
            return Result(
                status=Status.FAILED,
                message="Die Ideen-Faehigkeit ist nicht verdrahtet, Sir - Details im Log.",
            )
        context = (
            "=== FAEHIGKEITS-KATALOG (nur diese existieren!) ===\n"
            f"{_capabilities_text()}\n\n"
            "=== TATSAECHLICHE NUTZUNG (Zaehlwerte) ===\n"
            f"{_usage_text()}\n\n"
            "=== AKTUELLER STAND ===\n"
            f"{_state_text()}"
        )
        try:
            ideas = _ai.generate(_IDEAS_PROMPT, context, max_tokens=700)
        except Exception:  # noqa: BLE001 - API kann ausfallen
            logger.exception("Ideen-Vorschlag fehlgeschlagen.")
            return Result(
                status=Status.FAILED,
                message="Mir wollen gerade keine Ideen einfallen, Sir - die KI-Verbindung klemmt.",
            )
        return Result(
            status=Status.SUCCESS,
            message=(
                f"Ein paar Gedanken, Sir:\n{ideas.strip()}\n\n"
                "Soll ich eine davon vertiefen? Sag einfach: recherchier Idee 2."
            ),
            data={"chars": len(ideas)},
        )


# Registrierungspunkt - commands/__init__.py liest diese Liste beim Start ein.
COMMANDS = [ProposeIdeasCommand()]
