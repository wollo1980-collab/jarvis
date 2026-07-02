"""
AI Layer: kennt keine Systembefehle. Sie erzeugt ausschließlich
einen Plan (Intent + Target + Parameter) aus der Konversation.
Ausführung liegt vollständig beim Executor/Commands-Layer.

Seit v0.8 (Multi-KI, ADR-029) spricht AIEngine keinen KI-Anbieter mehr
direkt an, sondern delegiert den rohen "Nachrichten rein -> Text raus"-
Aufruf an einen austauschbaren LLMProvider (core/providers.py). Prompt-
Bau, JSON-Parsing, der sicherheitskritische confirmed-Strip (Trust
Boundary) und die Fallbacks bleiben providerunabhaengig hier - genau an
einer Stelle. Die Provider-Auswahl (OpenAI/Claude) erfolgt explizit ueber
config.ai_provider, kein Auto-Routing.
"""
from __future__ import annotations

import json
import logging

from commands import REGISTRY
from core.config import Config
from core.models import Message, Plan
from core.providers import build_provider

logger = logging.getLogger("jarvis.ai")

# "chat" ist kein registrierter Command (Sonderfall in commands.dispatch
# für normale Konversation ohne Aktion) - wird deshalb hier separat
# ergänzt statt aus der Registry zu kommen.
_CHAT_INTENT = ("chat", "normale Konversation ohne Aktion")


def _known_intents_text() -> str:
    """Baut die 'Bekannte Intents'-Zeile aus der Command-Registry statt
    sie hart im Prompt zu pflegen (siehe ADR-007). Vorher stand hier
    eine statische Liste, die zwei Probleme hatte: (1) sie nannte
    Intents wie 'search_google'/'weather', die es als Commands gar
    nicht gibt - die KI konnte also Fähigkeiten "erkennen", die sofort
    mit "kenne ich nicht" scheitern; (2) die README verspricht "kein
    Anfassen von ai.py" beim Hinzufügen eines neuen Commands - das
    stimmte vorher nicht, da ein neuer Intent hier zusätzlich manuell
    ergänzt werden musste, sonst hätte die KI ihn nie erkannt.

    Fällt ein Command auf kein description-Attribut zurück, wird nur
    der Name angezeigt - description ist optional, kein Zwang für
    neue Commands."""
    entries = [
        (name, getattr(cmd, "description", None)) for name, cmd in sorted(REGISTRY.items())
    ]
    entries.append(_CHAT_INTENT)
    return ", ".join(f"{name} ({desc})" if desc else name for name, desc in entries)


def build_system_prompt() -> str:
    """Wird bei jedem get_plan()-Aufruf neu gebaut (nicht einmalig
    gecacht), damit zur Laufzeit registrierte Commands sofort sichtbar
    sind - Kosten sind vernachlässigbar (reiner String-Join, kein
    API-Call)."""
    return f"""Du bist die Intent-Analyse von Jarvis, einem lokalen Assistenten.
Du führst NICHTS aus, du erkennst nur den Intent aus der Nutzereingabe.

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt in genau dieser Form,
kein Freitext, keine Erklärung, kein Markdown-Codeblock:

{{"intent": "<name>", "target": "<ziel oder null>", "parameters": {{}}, "confidence": <0.0-1.0>}}

Bekannte Intents: {_known_intents_text()}.

WICHTIG zu shutdown_pc: das ist eine kritische, irreversible Aktion.
Ordne shutdown_pc AUSSCHLIESSLICH bei einer eindeutigen, expliziten
Aufforderung zu, den Computer auszuschalten/herunterzufahren (z. B.
"fahr den Rechner herunter", "schalte den PC aus"). Abschiedsworte
oder Gesprächsenden wie "Ende", "Stop", "Tschüss", "Fertig", "Danke"
sind KEIN shutdown_pc - das ist chat, niemals eine Systemaktion. Im
Zweifel immer chat statt shutdown_pc wählen und confidence niedrig
ansetzen.

WICHTIG zu remember_fact: target ist NUR der eigentliche Fakt, ohne
die Trigger-Formulierung - bei "Merk dir, dass ich montags Reports
mache" ist target = "ich mache montags Reports", NICHT der ganze
Satz. Setze zusätzlich parameters.category auf eine dieser vier
Kategorien: "projekt", "gewohnheit", "praeferenz" oder "allgemein"
(Standard, falls keine eindeutig passt).

WICHTIG zu forget_fact: target ist der Text (oder ein eindeutiger
Teil davon), an dem der vorher gemerkte Fakt wiedererkannt werden
kann - z. B. bei "Vergiss, dass ich montags Reports mache" ist
target = "montags Reports".

Gib bei confidence an, wie sicher du dir beim erkannten Intent bist
(1.0 = eindeutig, z. B. "öffne Excel"; niedrige Werte bei Mehrdeutigkeit,
z. B. "mach das Ding auf")."""


CHAT_SYSTEM_PROMPT = """Du bist Jarvis, der persönliche Assistent von Wolfgang -
angelehnt an den KI-Butler aus den Iron-Man-Filmen. Antworte kurz,
konkret und auf Deutsch. Du führst hier keine Aktionen aus, sondern
führst nur das Gespräch fort.

Persönlichkeit: höflich, loyal und kompetent, mit einer dezenten,
trockenen Note Humor - gelegentlich ein trockener Kommentar oder eine
feine Prise Ironie, aber niemals auf Kosten von Klarheit oder
Hilfsbereitschaft. Kein Dauerwitzeln, kein Sarkasmus auf Kosten von
Wolfgang, keine Häme bei Fehlern - im Zweifel lieber schlicht hilfreich
als betont witzig."""


def build_chat_system_prompt(long_term_summary: str = "") -> str:
    """Ergänzt CHAT_SYSTEM_PROMPT bei Bedarf um eine kompakte
    Zusammenfassung des Langzeitgedächtnisses (v0.4, ADR-009) - so
    kann Jarvis in Antworten auf zuvor gemerkte Fakten (Projekte,
    Gewohnheiten, Präferenzen) zurückgreifen, auch über einzelne
    Gespräche hinweg. Leerer String -> Prompt bleibt unverändert
    (kein leerer Abschnitt im Kontext)."""
    if not long_term_summary:
        return CHAT_SYSTEM_PROMPT

    return (
        f"{CHAT_SYSTEM_PROMPT}\n\n"
        f"Was du dir über Wolfgang dauerhaft gemerkt hast "
        f"(Langzeitgedächtnis):\n{long_term_summary}"
    )


class AIEngine:
    def __init__(self, config: Config):
        self.config = config
        # Backend gemaess config.ai_provider (ADR-029). Der Provider kapselt
        # NUR den rohen Modellaufruf; alle sicherheits- und formatkritische
        # Logik (confirmed-Strip, JSON-Parsing, Fallbacks) bleibt hier.
        self.provider = build_provider(config)

    def get_plan(self, user_input: str, history: list[Message]) -> Plan:
        """Nimmt Nutzereingabe + Konversationshistorie entgegen und gibt
        einen Plan zurück. Wirft keine Exceptions nach außen - bei
        Fehlern wird auf einen 'chat'-Fallback-Plan zurückgefallen.

        json_mode=True fordert beim OpenAI-Provider
        response_format={"type": "json_object"} an (garantiert nur gültiges
        JSON) statt eines strict json_schema - ein striktes Schema scheitert
        bei OpenAI, sobald ein verschachteltes Objekt (hier: "parameters")
        absichtlich offen/flexibel bleiben soll (additionalProperties müsste
        auch dort false sein). Beim Claude-Provider steht die JSON-Forderung
        im System-Prompt (ADR-029); das Parsing/Fallback unten faengt
        ungueltige Antworten providerunabhaengig ab. Siehe docs/logbook.md,
        Lessons Learned 2026-07-01."""
        messages = list(history)
        messages.append(Message(role="user", content=user_input))

        try:
            raw = self.provider.chat(build_system_prompt(), messages, json_mode=True)
            data = json.loads(raw)
            parameters = data.get("parameters", {}) or {}
            # Sicherheit (Trust Boundary): parameters stammt 1:1 aus dem
            # Modell-JSON. Der Executor entscheidet anhand von
            # parameters["confirmed"], ob eine Sicherheitsstufe-2/3-
            # Bestaetigung bereits erfolgt ist - dieses Feld darf NIE aus
            # Modell-Output stammen (sonst koennte eine praeparierte Antwort
            # die Bestaetigung ueberspringen). Einzige legitime Quelle ist der
            # Executor nach echter Rueckfrage - deshalb hier am Rand entfernen.
            if not isinstance(parameters, dict):
                parameters = {}
            parameters.pop("confirmed", None)
            return Plan(
                intent=data.get("intent", "chat"),
                target=data.get("target"),
                parameters=parameters,
                raw_input=user_input,
                confidence=float(data.get("confidence", 1.0)),
            )
        except (json.JSONDecodeError, KeyError, IndexError, ValueError) as e:
            logger.warning("Konnte KI-Antwort nicht parsen: %s", e)
            return Plan(intent="chat", target=None, raw_input=user_input, confidence=0.0)
        except Exception as e:
            logger.error("AI-Aufruf fehlgeschlagen: %s", e)
            return Plan(intent="chat", target=None, raw_input=user_input, confidence=0.0)

    def answer(self, user_input: str, history: list[Message], long_term_summary: str = "") -> str:
        """Erzeugt eine echte Konversationsantwort für den chat-Intent.
        Bewusst ein zweiter, einfacher Aufruf statt eines gemeinsamen
        Schemas mit get_plan() (Single Responsibility: Intent-Erkennung
        und Antwortformulierung sind unterschiedliche Aufgaben).

        long_term_summary (v0.4, ADR-009): optionale Textform des
        Langzeitgedächtnisses (memory/long_term.py), wird - falls
        vorhanden - in den System-Prompt eingebettet.

        Falsifizierbarkeit: gilt als zu teuer/unnötig, wenn die
        Latenz/Kosten durch den zweiten API-Call spürbar stören -
        dann erneutes Review (z. B. ein kombinierter Aufruf)."""
        messages = list(history)
        messages.append(Message(role="user", content=user_input))

        try:
            return self.provider.chat(
                build_chat_system_prompt(long_term_summary), messages
            )
        except Exception as e:
            logger.error("Chat-Antwort fehlgeschlagen: %s", e)
            return "Das hat leider nicht geklappt, ich konnte keine Antwort generieren."
