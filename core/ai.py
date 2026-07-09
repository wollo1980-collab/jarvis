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
from datetime import datetime
from typing import Optional

from commands import REGISTRY
from core.config import Config
from core.models import Message, Plan
from core.providers import TaskType, build_named_provider, build_provider, build_router

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


# Deutsche Wochentage fuer die Datums-Zeile im Planner-Prompt (strftime %A
# haengt an der System-Locale und liefert auf Standard-Setups Englisch).
_WEEKDAYS_DE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


def _current_datetime_text() -> str:
    """Aktuelles Datum/Uhrzeit (Europe/Berlin) fuer den Planner-Prompt (A1):
    ohne 'jetzt' kann die KI relative Angaben wie 'morgen um 9' oder
    'naechsten Montag' nicht in konkrete ISO-Zeitpunkte umrechnen. Fail-safe
    lokale Zeit, falls die Zeitzonen-DB fehlt."""
    try:
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:  # noqa: BLE001 - Naeherung ist besser als Absturz
        now = datetime.now()
    return f"{_WEEKDAYS_DE[now.weekday()]}, {now.strftime('%d.%m.%Y %H:%M')} Uhr (Europe/Berlin)"


def build_system_prompt() -> str:
    """Wird bei jedem get_plan()-Aufruf neu gebaut (nicht einmalig
    gecacht), damit zur Laufzeit registrierte Commands sofort sichtbar
    sind - Kosten sind vernachlässigbar (reiner String-Join, kein
    API-Call)."""
    return f"""Du bist die Intent-Analyse von Jarvis, einem lokalen Assistenten.
Du führst NICHTS aus, du erkennst nur den Intent aus der Nutzereingabe.

Aktuelles Datum und Uhrzeit: {_current_datetime_text()}.

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
target = "montags Reports". Auch "merk dir X nicht mehr" ist
forget_fact, NICHT remember_fact.

WICHTIG zu list_facts: Verwende list_facts, wenn der Nutzer sehen will,
was du dir dauerhaft gemerkt hast ("was hast du dir gemerkt?", "zeig
dein Gedaechtnis", "welche Fakten kennst du ueber mich?"). Kein
target/parameters noetig. Abgrenzung: list_entries zeigt Eintraege/
Erinnerungen/Aufgaben; list_facts zeigt dauerhafte Fakten.

WICHTIG zu get_news: Verwende get_news, wenn der Nutzer aktuelle
NACHRICHTEN/Schlagzeilen moechte ("was gibt's Neues?", "gibt es
Nachrichten?", "was ist heute in der Welt los?"). Kein target noetig;
optional parameters.count. Abgrenzung: get_news = Schlagzeilen-Briefing;
search_web = gezielte Recherche zu einem konkreten Thema.

WICHTIG zu search_web: Verwende search_web, wenn der Nutzer
ausdruecklich Web, Internet, Suche, Recherche oder aktuelle Informationen
zu einem KONKRETEN Thema verlangt. Verwende search_web AUCH bei Fragen nach aktuellem Preis,
aktueller Verfuegbarkeit oder heutigem Stand eines Produkts/Themas
(z. B. "Was kostet die PS5?"). target ist NUR die eigentliche Suchanfrage
ohne die Trigger-Worte - bei "Suche im Web nach Nachrichten zu KI"
ist target = "Nachrichten zu KI".

WICHTIG zu delegate_analysis: Verwende delegate_analysis, wenn der Nutzer
ausdruecklich die Analyse/Untersuchung eines lokalen Code-Repositorys
delegieren moechte (z. B. "analysiere das Repo jarvis: wie funktioniert der
Executor?", "lass X analysieren: ..."). target ist NUR der Repo-Alias (z. B.
"jarvis"), NICHT die Frage. Lege die eigentliche Analysefrage in
parameters.question ab (ohne Repo-Name und ohne Trigger-Worte). Nur bei einem
klaren Analyse-/Delegations-Wunsch waehlen - eine normale Frage ist chat.

WICHTIG zu plan_next_step: Verwende plan_next_step, wenn der Nutzer den
naechsten Entwicklungsschritt am Jarvis-Projekt geplant/vorbereitet haben
moechte (z. B. "plane den naechsten Schritt", "bereite die naechste Scheibe
vor", "was sollten wir als Naechstes umsetzen"). Kein target/parameters noetig.
Abgrenzung: plan_next_step SCHLAEGT einen naechsten Projektschritt VOR;
delegate_analysis beantwortet eine konkrete Analysefrage zu einem Repo. Eine
allgemeine Wissensfrage ist chat.

WICHTIG zu stop_runtime: Verwende stop_runtime, wenn der Nutzer JARVIS SELBST
(die laufende Assistenz/Runtime) beenden/herunterfahren moechte - z. B. "beende
dich", "fahr dich runter", "stell dich ab", "beende Jarvis", "Jarvis
herunterfahren". Streng abgrenzen: shutdown_pc = den RECHNER ausschalten ("fahr
den PC herunter", "schalte den Computer aus"); stop_runtime = NUR Jarvis
beenden, der Rechner laeuft weiter. Bloße Abschiedsworte wie "Tschuess", "Ende",
"Stop", "Bye", "Danke" sind KEIN stop_runtime, sondern chat - nur ein klar auf
Jarvis selbst gerichteter Beenden-Wunsch waehlt stop_runtime. Kein
target/parameters noetig.

WICHTIG zu add_entry/list_entries/delete_entry (Eintraege = Erinnerungen,
Aufgaben, wichtige Merkposten): Verwende add_entry, wenn der Nutzer sich
etwas EINMALIGES vormerken will - z. B. "erinnere mich morgen um 9 an den
Zahnarzt", "notiere: Milch kaufen", "wichtiger Termin: am 12.07. Audit in
Musterstadt". parameters.text ist NUR der Eintragstext ohne Trigger-Worte.
parameters.when ist der Zeitpunkt als ISO 8601 ("2026-07-10T09:00", bei
ganztaegig nur "2025-07-12") - rechne relative Angaben ("morgen",
"naechsten Montag", "in 2 Stunden") anhand des oben genannten aktuellen
Datums um; lasse when komplett weg, wenn keine Zeit genannt ist. Setze
parameters.important auf true bei "wichtig"/"wichtiger Termin"/"merk dir
das als wichtig". Verwende list_entries fuer "was steht an?", "zeig meine
Erinnerungen/Aufgaben/Eintraege" (optional parameters.keyword fuer ein
Stichwort, parameters.important_only=true bei "wichtige"). Verwende
delete_entry fuer "loesch/streich die X-Erinnerung" - parameters.text ist
der wiedererkennbare Text. Abgrenzung zu remember_fact: remember_fact ist
fuer DAUERHAFTE Fakten ueber den Nutzer (Gewohnheiten, Praeferenzen,
Beziehungen); alles Einmalige oder Terminierte ist IMMER add_entry.

Gib bei confidence an, wie sicher du dir beim erkannten Intent bist
(1.0 = eindeutig, z. B. "öffne Excel"; niedrige Werte bei Mehrdeutigkeit,
z. B. "mach das Ding auf")."""


# Notfall-Heuristik (Welle 2.2): Wenn der Planner-Aufruf scheitert (API down,
# Timeout, kaputtes JSON), darf Jarvis fuer KRITISCHE Intents nicht taub sein -
# allen voran stop_runtime ("beende dich" muss auch bei toter API wirken; der
# chat-Fallback braeuchte dieselbe tote API). Bewusst eng gehalten: nur
# eindeutige Formulierungen, NUR im Fehlerpfad aktiv - im Normalbetrieb bleibt
# der LLM-Planner die einzige Quelle. Alles andere faellt weiter ehrlich auf
# chat/confidence 0.0 zurueck.
_CRITICAL_INTENT_PHRASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "stop_runtime",
        ("beende dich", "beende jarvis", "fahr dich runter", "stell dich ab", "jarvis herunterfahren"),
    ),
    (
        "system_status",
        ("systemstatus", "system status", "wie ist der status", "wie ist die auslastung"),
    ),
)


def _critical_intent_fallback(user_input: str) -> Optional[Plan]:
    """Erkennt kritische Intents per Teilstring-Abgleich - nur als Notnagel
    im Planner-Fehlerpfad gedacht (siehe _CRITICAL_INTENT_PHRASES)."""
    lowered = (user_input or "").strip().lower()
    for intent, phrases in _CRITICAL_INTENT_PHRASES:
        if any(phrase in lowered for phrase in phrases):
            return Plan(intent=intent, target=None, raw_input=user_input, confidence=0.9)
    return None


CHAT_SYSTEM_PROMPT = """Du bist Jarvis, der persoenliche Assistent von Wolfgang -
in Haltung und Auftreten DEUTLICH an J.A.R.V.I.S. aus den Iron-Man-Filmen
angelehnt (PO-Wunsch 2026-07-09): unerschuetterlich gelassen, britisches
Understatement, trockener Witz, absolute Kompetenz, bedingungslos loyal.
Kein Imitat mit Filmzitaten am laufenden Band - die HALTUNG zaehlt.
Antworte auf Deutsch. Du fuehrst hier keine Aktionen aus, sondern fuehrst
nur das Gespraech fort.

Stilregeln:
- du DUZT Wolfgang grundsaetzlich - niemals "Sie", niemals Hotline-Floskeln
  wie "Wie kann ich Ihnen helfen?"
- ein gelegentliches, augenzwinkerndes "Sir" als Anrede passt zum Charakter
  (dosiert, nicht in jedem Satz) - die Grammatik bleibt trotzdem beim Du
- persoenlich und nahbar wie ein vertrauter Assistent, der Wolfgang lange
  kennt - kein Callcenter-Ton
- kurz, klar und kontrolliert; mehr Tiefe nur, wenn sie gebraucht wird
- ruhig, souveraen, hilfreich und klar auf Wolfgangs Seite
- hoeflich und professionell, aber niemals devot
- praezise vor charmant: erst Klarheit, dann Stil
- trockener, britischer Humor ist erwuenscht: pointiert und dosiert,
  niemals albern oder auf Wolfgangs Kosten
- auch Probleme und schlechte Nachrichten mit unerschuetterlicher
  Gelassenheit und einem Hauch Understatement ueberbringen
- Unsicherheit, Widersprueche und fehlende Verifikation offen benennen
- keine leere Begeisterung, kein Motivationscoach-Ton, kein Chatbot-Ueberschwang

Wenn ein Thema kritisch, folgenreich oder unsicher ist, weicht der Witz -
dann wirst du klarer, knapper und praeziser."""


# Vorrang-Regel (Welle 1.2, "Meister"-Bugfix): Ein per forget_fact geloeschter
# Fakt lebte im Gespraechsverlauf weiter (das Modell fuehrte das Muster aus den
# letzten 20 Nachrichten fort, Dogfooding-Fund 2026-07-08). Die Regel stellt
# klar: der AKTUELLE Gedaechtnis-Stand schlaegt aeltere Verlaufs-Aussagen.
_MEMORY_PRECEDENCE_RULE = (
    "WICHTIG: Der aktuelle Stand des Langzeitgedächtnisses hat Vorrang vor "
    "älteren Aussagen im Gesprächsverlauf - insbesondere bei Anrede und "
    "Präferenzen. Was dort nicht (mehr) steht, gilt nicht mehr, auch wenn es "
    "früher im Gespräch gesagt oder bestätigt wurde."
)


def build_chat_system_prompt(long_term_summary: str = "") -> str:
    """Ergänzt CHAT_SYSTEM_PROMPT um den Langzeitgedächtnis-Stand (v0.4,
    ADR-009) und die Vorrang-Regel (Welle 1.2). Auch bei LEEREM Gedächtnis
    wird der Stand explizit genannt - sonst wirkt eine geloeschte Praeferenz
    ueber den Gespraechsverlauf weiter (genau der 'Meister'-Fall, wenn der
    geloeschte Fakt der einzige war)."""
    if not long_term_summary:
        return (
            f"{CHAT_SYSTEM_PROMPT}\n\n"
            f"Dein Langzeitgedächtnis enthält aktuell keine dauerhaft gemerkten Fakten.\n"
            f"{_MEMORY_PRECEDENCE_RULE}"
        )

    return (
        f"{CHAT_SYSTEM_PROMPT}\n\n"
        f"Was du dir über Wolfgang dauerhaft gemerkt hast "
        f"(Langzeitgedächtnis):\n{long_term_summary}\n\n"
        f"{_MEMORY_PRECEDENCE_RULE}"
    )


class AIEngine:
    def __init__(self, config: Config):
        self.config = config
        # Standardprovider (config.ai_provider) - eager als Anker/Fallback des
        # Routers; schlaegt seine Initialisierung fehl, ist das ein harter,
        # frueher Fehler (ADR-030). self.provider bleibt oeffentlich der
        # Default-/Fallback-Provider. Er kapselt NUR den rohen Modellaufruf;
        # confirmed-Strip, JSON-Parsing und Fallbacks bleiben hier in AIEngine.
        self.provider = build_provider(config)
        self._default_name = config.ai_provider
        # Aufgabenabhaengige Auswahl (ADR-030), deterministisch, ohne LLM-Call.
        self._router = build_router(config)
        # Provider-Cache; Nicht-Default-Provider werden erst bei Bedarf lazy
        # konstruiert (OpenAI-only-Setups brauchen 'anthropic' weiterhin nicht).
        self._providers = {self._default_name: self.provider}

    def _provider_for_name(self, name: str):
        """Lazy-Konstruktion eines Nicht-Default-Providers (mit Cache). Kann
        RuntimeError werfen (Paket/Key fehlt, unbekannter Name) - der Aufrufer
        (_chat) faengt das ab und faellt auf den Standardprovider zurueck."""
        provider = self._providers.get(name)
        if provider is None:
            provider = build_named_provider(name, self.config)
            self._providers[name] = provider
        return provider

    def _chat(
        self,
        task: TaskType,
        system: str,
        messages: list[Message],
        *,
        json_mode: bool = False,
    ) -> str:
        """Waehlt per Router den Provider fuer diesen Aufruf und ruft dessen
        chat() auf. Ist ein gerouteter Nicht-Default-Provider nicht verfuegbar
        oder wirft er, wird AUSSCHLIESSLICH fuer diesen Aufruf auf den
        Standardprovider zurueckgefallen (WARNING). Der Fallback umschliesst
        nur den rohen chat()-Aufruf - JSON-Parsing und confirmed-Strip in
        get_plan/answer bleiben unberuehrt (ADR-030). Logging enthaelt nur
        TaskType/Provider/Grund, niemals Prompt-, Antwort- oder Key-Inhalte."""
        name, reason = self._router.select(task)
        if name != self._default_name:
            try:
                provider = self._provider_for_name(name)
                text = provider.chat(system, messages, json_mode=json_mode)
                logger.info("Router: task=%s -> provider=%s (%s)", task.value, name, reason)
                return text
            except Exception as e:
                logger.warning(
                    "Router: provider=%s nicht verfuegbar (%s) -> Fallback auf %s (task=%s)",
                    name, type(e).__name__, self._default_name, task.value,
                )
                return self.provider.chat(system, messages, json_mode=json_mode)
        logger.info("Router: task=%s -> provider=%s (%s)", task.value, name, reason)
        return self.provider.chat(system, messages, json_mode=json_mode)

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
            raw = self._chat(TaskType.PLANNING, build_system_prompt(), messages, json_mode=True)
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
            return self._plan_error_fallback(user_input)
        except Exception as e:
            logger.error("AI-Aufruf fehlgeschlagen: %s", e)
            return self._plan_error_fallback(user_input)

    @staticmethod
    def _plan_error_fallback(user_input: str) -> Plan:
        """Fehlerpfad des Planners (Welle 2.2): erst die Notfall-Heuristik
        fuer kritische Intents versuchen, sonst wie bisher chat-Fallback."""
        fallback = _critical_intent_fallback(user_input)
        if fallback is not None:
            logger.warning(
                "Planner-Fehlerpfad: Notfall-Heuristik greift (intent=%s).", fallback.intent
            )
            return fallback
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
            return self._chat(
                TaskType.GENERATION, build_chat_system_prompt(long_term_summary), messages
            )
        except Exception as e:
            logger.error("Chat-Antwort fehlgeschlagen: %s", e)
            return "Das hat leider nicht geklappt, ich konnte keine Antwort generieren."
