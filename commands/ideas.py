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

from core.models import Plan, Result, Status

logger = logging.getLogger("jarvis.commands.ideas")

_ai = None
_habit_stats = None
_entry_store = None
_list_store = None
_history_provider = None

_CAP_CAPABILITIES = 6000
# Wie viele der letzten Gespraechs-Nachrichten der Ideen-Prompt sieht (damit eine
# Verfeinerung wie 'eher etwas was dich ergaenzt' auf die vorigen Ideen aufbaut).
_HISTORY_TURNS = 6

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
    "- Beziehe dich auf die AKTUELLE FRAGE und das bisherige Gespraech: ist die "
    "Frage eine Verfeinerung ('eher etwas das dich ergaenzt', 'was anderes', "
    "'guenstiger'), baue auf den zuvor genannten Ideen auf und wiederhole NICHT "
    "dieselbe Liste.\n"
    "- Du schlaegst nur vor - du fuehrst nichts aus."
)

# Bau-Modus (Reibung 11.07.2026: "was koennten wir ENTWICKELN?" bekam
# vorhandene Faehigkeiten statt neuer Projekt-Ideen). Signale in der
# Roheingabe schalten von "was TUN" auf "was BAUEN" um.
_BUILD_SIGNALS = (
    "bau", "entwickel", "programmier", "coden", "projekt", "framework",
    "tool", "erstell", "proggen",
)

_BUILDS_PROMPT = (
    "Du bist die Ideen-Faehigkeit von Jarvis. Der Nutzer fragt, was ihr NEU "
    "BAUEN/ENTWICKELN koenntet. Wichtig: Jarvis kann kleine Projekte SELBST "
    "anlegen und bauen - ein Agent schreibt Code (Python-Tools/CLIs/kleine "
    "Skripte/Automationen), testet ihn und legt ein eigenes Projekt an. "
    "Antworte wie ein guter Entwickler-Kollege: 3 bis 4 KONKRETE, KLEINE "
    "Projekt-Ideen, die ein Agent in einem Rutsch bauen koennte.\n\n"
    "EISERNE REGELN:\n"
    "- NUR kleine, klar baubare Dinge (Python-CLI/Tool/Skript/kleine "
    "Automation). KEINE Luftschloesser: keine grosse App mit GUI/Cloud/"
    "Benutzerkonten, kein Mehr-Wochen-Projekt.\n"
    "- Konkret und nuetzlich fuer DIESEN Nutzer - wenn moeglich an seinen "
    "offenen Punkten/Listen andocken.\n"
    "- Jede Idee endet mit einem kurzen natuerlichen Bau-Satz in "
    "Anfuehrungszeichen (z. B. «Sag: 'Bau mir einen Pomodoro-Timer'»).\n"
    "- Kurz und sprechtauglich: nummerierte Punkte, je 1-2 Saetze, kein "
    "Markdown-Fett.\n"
    "- Beziehe dich auf die AKTUELLE FRAGE und das bisherige Gespraech: ist die "
    "Frage eine Verfeinerung ('eher etwas das dich ergaenzt', 'was anderes', "
    "'kleiner'), baue auf den zuvor genannten Projekt-Ideen auf und wiederhole "
    "NICHT dieselbe Liste.\n"
    "- Du schlaegst nur vor - gebaut wird erst nach ausdruecklicher Freigabe."
)


def configure(ai, habit_stats, entry_store, list_store, history_provider=None) -> None:
    """Von main.py/jarvis_runtime.py mit den GETEILTEN Instanzen verdrahtet.
    history_provider() liefert den juengsten Gespraechsverlauf (list[Message]) -
    damit Verfeinerungen kontextbewusst beantwortet werden (Reibung 12.07.)."""
    global _ai, _habit_stats, _entry_store, _list_store, _history_provider
    _ai = ai
    _habit_stats = habit_stats
    _entry_store = entry_store
    _list_store = list_store
    _history_provider = history_provider


def _recent_conversation() -> str:
    """Die letzten Gespraechs-Nachrichten als knapper Text (oder ''). Fail-safe -
    ohne History-Provider / bei Fehler bleibt der Kontext einfach leer."""
    if _history_provider is None:
        return ""
    try:
        messages = _history_provider() or []
    except Exception:  # noqa: BLE001 - Kontext ist Kuer, nie Pflicht
        return ""
    lines = []
    for m in list(messages)[-_HISTORY_TURNS:]:
        who = "Nutzer" if getattr(m, "role", "") == "user" else "Jarvis"
        content = (getattr(m, "content", "") or "").strip().replace("\n", " ")
        if content:
            lines.append(f"{who}: {content[:300]}")
    return "\n".join(lines)


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
        "Schlaegt konkrete Vorschlaege vor - je nach Frage in ZWEI Modi: "
        "(a) sofort ausprobierbare Dinge, die der Nutzer mit Jarvis TUN "
        "koennte ('was koennten wir machen?', 'hast du Ideen?'), oder "
        "(b) NEUE kleine Projekte, die Jarvis BAUEN koennte ('was koennten "
        "wir bauen/entwickeln?', 'hast du Projekt-Ideen?', 'was koennten wir "
        "mit dem Framework machen?'). Geerdet, schlaegt nur vor, fuehrt nichts "
        "aus. Read-only, Stufe 0."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        if _ai is None:
            return Result(
                status=Status.FAILED,
                message="Die Ideen-Faehigkeit ist nicht verdrahtet, Sir - Details im Log.",
            )
        convo = _recent_conversation()
        raw = (plan.raw_input or "").lower()
        # Bau-Modus auch aus dem Gespraech (Reibung 12.07.: die Verfeinerung
        # 'eher etwas was dich ergaenzt' verlor die Bau-Signale und kippte auf
        # die Faehigkeiten-Liste). War das Gespraech bau-lastig, bleibt es dabei.
        build_mode = any(sig in raw for sig in _BUILD_SIGNALS) or any(
            sig in convo.lower() for sig in _BUILD_SIGNALS
        )
        # Die AKTUELLE Frage + der Verlauf ganz nach vorn - so beantwortet der
        # Ideen-Prompt auch eine Verfeinerung, statt eine generische Liste zu
        # wiederholen (frueher sah er die Frage gar nicht).
        focus = f"=== DIE AKTUELLE FRAGE DES NUTZERS ===\n{(plan.raw_input or '').strip()}\n\n"
        if convo:
            focus += f"=== BISHERIGES GESPRAECH (worauf sich die Frage bezieht) ===\n{convo}\n\n"
        if build_mode:
            prompt = _BUILDS_PROMPT
            context = (
                f"{focus}"
                "=== WAS JARVIS BAUEN KANN ===\n"
                "Kleine eigenstaendige Projekte: Python-CLIs, Tools, Skripte, "
                "kleine Automationen. Ein Agent schreibt + testet den Code, es "
                "wird ein eigenes Projekt angelegt. Schon gebaut: jkc (ein "
                "kleiner Wissens-Speicher).\n\n"
                "=== AKTUELLER STAND DES NUTZERS (Andock-Punkte) ===\n"
                f"{_state_text()}"
            )
            opener, closing = "Ein paar Bau-Ideen, Sir:", "Welche reizt dich, Sir? Dann legen wir los."
        else:
            prompt = _IDEAS_PROMPT
            context = (
                f"{focus}"
                "=== FAEHIGKEITS-KATALOG (nur diese existieren!) ===\n"
                f"{_capabilities_text()}\n\n"
                "=== TATSAECHLICHE NUTZUNG (Zaehlwerte) ===\n"
                f"{_usage_text()}\n\n"
                "=== AKTUELLER STAND ===\n"
                f"{_state_text()}"
            )
            opener, closing = "Ein paar Gedanken, Sir:", "Soll ich eine davon vertiefen? Sag einfach: recherchier Idee 2."
        try:
            ideas = _ai.generate(prompt, context, max_tokens=700)
        except Exception:  # noqa: BLE001 - API kann ausfallen
            logger.exception("Ideen-Vorschlag fehlgeschlagen.")
            return Result(
                status=Status.FAILED,
                message="Mir wollen gerade keine Ideen einfallen, Sir - die KI-Verbindung klemmt.",
            )
        return Result(
            status=Status.SUCCESS,
            message=f"{opener}\n{ideas.strip()}\n\n{closing}",
            data={"chars": len(ideas), "mode": "build" if build_mode else "use"},
        )


# Registrierungspunkt - commands/__init__.py liest diese Liste beim Start ein.
COMMANDS = [ProposeIdeasCommand()]
