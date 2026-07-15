"""
Planner: zerlegt eine Nutzereingabe in eine geordnete Liste von Plänen
(Schritten). v0.3-Ansatz bewusst einfach (siehe ADR-004): keine eigene
Multi-Step-JSON-Struktur in der KI-Antwort, stattdessen wird die
Eingabe an einfachen Konnektoren ("und", "und dann", "danach", ";")
in Teilsätze gesplittet und jeder Teilsatz einzeln an die KI
geschickt (get_plan bleibt unverändert - kein Bruch an core/ai.py).

Warum so einfach? Regel 6 (Keine Architecture Astronautics) und
Regel 4 (90/10-Prinzip): eine naive Trennung deckt den heutigen
Bedarf (2-3 Aktionen pro Satz) ab. Eine "echte" Multi-Step-Planung
mit Rückfrage-Loops ist ein Later-Feature (siehe Handbook Kap. 27).

Falsifizierbarkeit: gilt als unzureichend, wenn Nutzer regelmäßig
zusammengesetzte Sätze verwenden, die die Splitter-Heuristik nicht
sauber trennt (z. B. verschachtelte "und" in einem Objektnamen).
Dann Review in v0.4.
"""
from __future__ import annotations

import logging
import re
import threading

from core import reasoning
from core.ai import AIEngine
from core.models import Message, Plan

logger = logging.getLogger("jarvis.planner")

# Reihenfolge wichtig: längere Konnektoren zuerst prüfen, damit
# "und dann" nicht schon beim kürzeren "und" auseinandergerissen wird.
_SPLIT_PATTERN = re.compile(r"\s+(?:und dann|danach|und)\s+|;\s*", flags=re.IGNORECASE)

# Ideen-Vertiefung (Angestellten-Vision Stufe 2, Live-Befund 11.07.2026
# nachts): "recherchier Idee 2" soll das THEMA der Idee im Web
# recherchieren - das LLM führte stattdessen zweimal den in der Idee
# genannten Befehl aus (Prompt-Schärfung half nicht). Deshalb
# deterministisch VOR dem LLM: Muster erkennen, Idee-Wortlaut aus der
# letzten IDEEN-Antwort holen, search_web bauen.
_IDEA_DEEPEN_RE = re.compile(
    r"\b(?:recherchier\w*|vertiefe?\w*|informier\w*)\b.{0,40}?"
    r"\b(?:idee|nummer|punkt|vorschlag)\s*(\d+)",
    flags=re.IGNORECASE,
)
_IDEA_LINE_RE = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$", flags=re.MULTILINE)
# Der Ausloese-Satz ("Sag einfach: ...") gehoert nicht ins Suchthema.
_IDEA_TRIGGER_TAIL_RE = re.compile(r"\s*Sag einfach:.*$", flags=re.IGNORECASE)
# Signatur einer propose_ideas-Antwort (Audit-Fund 1, 11.07.2026): NUR
# eine echte Ideen-Antwort darf die Vertiefung ausloesen. News, Listen und
# der Wochen-Rueckblick erzeugen dasselbe "1. ..."-Format - wuerde die
# Heuristik die LETZTE beliebige Nummernliste nehmen, recherchierte sie am
# LLM vorbei das falsche Thema. commands/ideas.py haengt diesen Satz an
# JEDE Ideen-Antwort ("... Sag einfach: recherchier Idee 2.").
_IDEA_ANSWER_MARKER = "recherchier idee"


def _idea_deepening_plan(user_input: str, history: list[Message]) -> Plan | None:
    """Baut deterministisch einen search_web-Plan, wenn der Nutzer eine
    nummerierte Idee aus einer ECHTEN Ideen-Antwort vertiefen will. None =
    kein Treffer, normaler Weg (LLM) übernimmt."""
    match = _IDEA_DEEPEN_RE.search(user_input)
    if match is None:
        return None
    wanted = match.group(1)
    for message in reversed(history):
        if message.role != "assistant":
            continue
        # Audit-Fund 1: nur eine propose_ideas-Antwort zaehlt (Signatur),
        # nicht irgendeine Nummernliste (News/Listen/Wochen-Rueckblick).
        if _IDEA_ANSWER_MARKER not in message.content.lower():
            continue
        numbered = {num: text for num, text in _IDEA_LINE_RE.findall(message.content)}
        if not numbered:
            continue
        idea_text = numbered.get(wanted)
        if idea_text is None:
            return None  # Ideen-Liste da, aber Nummer nicht - LLM darf nachfragen
        topic = _IDEA_TRIGGER_TAIL_RE.sub("", idea_text).strip().rstrip(".!?–- ")
        if not topic:
            return None
        logger.info("Ideen-Vertiefung erkannt: Idee %s -> Websuche.", wanted)
        return Plan(intent="search_web", target=topic, confidence=1.0, raw_input=user_input)
    return None


# Anzeigename auf Zuruf (ADR-057): "nenn mich X" soll Chat UND Dashboard
# umbenennen (set_owner_name), nicht als loser Fakt versacken. Deterministisch
# VOR dem LLM, damit es zuverlaessig UND eng greift: NUR echte Selbst-
# Benennung. Ein Fakt wie "Max ist mein Sohn" enthaelt kein Benennungs-
# Verb und faellt bewusst durch -> normaler Weg (merk dir). _NAME = ein
# einzelnes Namenswort (>=2 Zeichen), damit die "zu mir"/"nennen"-Anker sauber
# greifen und keine Satzreste einsammeln.
_NAME = r"(?P<name>[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß'\-]+)"
# Fuellwoerter zwischen "nenn mich" und dem Namen (Live-Reibung 11.07.2026:
# "nenn mich ab sofort WIEDER Martin" las "wieder" als Namen -> Stoppwort ->
# Rueckfrage-Schleife). Beliebig viele davon werden uebersprungen; Mehrwort-
# Varianten stehen VOR ihren Einzelwoertern (Alternation ist links-greedy).
_OWNER_NAME_FILLERS = (
    r"(?:bitte|ab\s+jetzt|ab\s+sofort|ab\s+heute|ab\s+nun|von\s+jetzt\s+an|"
    r"jetzt|sofort|wieder|einfach|doch|mal|gerne|gern|ruhig|halt|eben|nun|immer)"
)
_OWNER_NAME_RES = [
    re.compile(r"\bnenn(?:e)?\s+mich(?:\s+" + _OWNER_NAME_FILLERS + r")*\s+" + _NAME, re.IGNORECASE),
    re.compile(r"\bich\s+hei(?:ß|ss)e\s+" + _NAME, re.IGNORECASE),
    re.compile(r"\bmein\s+name\s+ist\s+" + _NAME, re.IGNORECASE),
    re.compile(r"\bsag(?:\s+bitte)?\s+" + _NAME + r"\s+zu\s+mir\b", re.IGNORECASE),
    re.compile(r"\bdu\s+(?:darfst|kannst|sollst)\s+mich\s+" + _NAME + r"\s+nennen\b", re.IGNORECASE),
]
# Woerter, die die Muster grammatikalisch treffen, aber KEIN Name sind
# ("nenn mich nicht so", "ich heiße dich willkommen") - Fehlanzeige statt
# Fehl-Umbenennung. Klein geschrieben verglichen.
_OWNER_NAME_STOPWORDS = frozenset({
    "dich", "mich", "euch", "ihn", "sie", "uns", "bitte", "nicht", "willkommen",
    "gut", "doch", "mal", "jetzt", "sofort", "immer", "nie", "so", "gerne",
    "gern", "wieder", "auch", "einfach", "ruhig", "halt", "eben",
})


def _owner_name_plan(user_input: str) -> Plan | None:
    """Erkennt eine ausdrueckliche Selbst-Benennung und baut den
    set_owner_name-Plan. None = keine (oder unplausible) Benennung, normaler
    Weg uebernimmt. Bewusst eng: lieber eine echte Umbenennung verpassen (LLM
    faengt sie als Fallback) als "Max ist mein Sohn" zur Anrede machen."""
    for rx in _OWNER_NAME_RES:
        match = rx.search(user_input)
        if match is None:
            continue
        name = match.group("name").strip().strip("'-")
        if len(name) < 2 or name.lower() in _OWNER_NAME_STOPWORDS:
            continue
        # Eigenname gross schreiben (Sprach-/Kleinschreibung glaetten), Rest
        # unangetastet (McLeod, von-Namen bleiben, wie sie sind).
        name = name[:1].upper() + name[1:]
        logger.info("Anzeigename-Wunsch erkannt -> set_owner_name (%s).", name)
        return Plan(intent="set_owner_name", target=name, confidence=1.0, raw_input=user_input)
    return None


# Vorschlag verwerfen auf Zuruf (PO-Reibung 2026-07-11): "Deinen Entwurf
# verwerfen" fand kein Intent und wurde vom LLM als stop_runtime gedeutet ->
# Jarvis fuhr herunter. Deterministisch VOR dem LLM: eine Verwerf-Formulierung
# + Vorschlags-Objekt -> dismiss_proposal. Kurze Befehle -> Teilstring genuegt.
_DISMISS_VERBS = ("verwirf", "verwerf", "ablehn", "weg mit", "weg damit")
_DISMISS_OBJECTS = ("vorschlag", "entwurf", "empfehlung")


def _dismiss_proposal_plan(user_input: str) -> Plan | None:
    """Erkennt den Wunsch, Jarvis' offenen Eigenvorschlag zu verwerfen. None =
    kein Treffer. Bewusst eng auf das Vorschlags-Objekt begrenzt, damit es nie
    ein Loeschen von Notizen/Fakten kapert."""
    low = (user_input or "").lower()
    has_verb = any(v in low for v in _DISMISS_VERBS) or ("lehn" in low and "ab" in low)
    has_object = any(o in low for o in _DISMISS_OBJECTS)
    if has_verb and has_object:
        logger.info("Vorschlag-Verwerfen erkannt -> dismiss_proposal.")
        return Plan(intent="dismiss_proposal", target=None, confidence=1.0, raw_input=user_input)
    return None


# Brainstorm-Auftakt (PO-Reibung 2026-07-11: "lass uns kurz brainstormen, was
# der naechste Schritt waere" landete in plan_next_step - einer formellen,
# ASYNCHRONEN Agenten-Analyse ("Bericht folgt") statt in einem GESPRAECH).
# "brainstorm" ist ein Gespraechs-Signal: der Nutzer will hin und her denken,
# nicht einen Lauf ausloesen. -> chat. Formelle Planung bleibt beim
# ausdruecklichen "plane den naechsten Schritt".
_BRAINSTORM_RE = re.compile(r"\bbrainstorm\w*\b", re.IGNORECASE)


def _brainstorm_plan(user_input: str) -> Plan | None:
    """Ein 'brainstorm'-Auftakt ist ein Gespraech, keine Delegation/kein Lauf."""
    if _BRAINSTORM_RE.search(user_input or ""):
        logger.info("Brainstorm-Auftakt erkannt -> chat (Gespraech statt Delegation).")
        return Plan(intent="chat", target=None, confidence=1.0, raw_input=user_input)
    return None


# Fehlrouting-Schutz fuer STILL wirkende, disruptive Intents (PO-Reibung
# 2026-07-11: "Deinen Entwurf verwerfen" -> stop_runtime -> Jarvis 2 Min
# offline). stop_runtime laeuft OHNE Rueckfrage (ueber Telegram waere eine
# gesperrt) - ein Fehlgriff des schnellen Planners nimmt Jarvis also still aus
# dem Dienst. Deshalb: stop_runtime feuert NUR, wenn die Eingabe wirklich eine
# Abschalt-Formulierung traegt; sonst ist es fast sicher ein Fehlrouting -> chat
# (der Nutzer bekommt eine Antwort statt eines stillen Shutdowns).
_SHUTDOWN_TRIGGER_RE = re.compile(
    r"(?i)(beende?\s+(dich|jarvis)|beenden?\b.{0,12}\bjarvis|fahr\w*\s+dich\s+(runter|herunter)"
    r"|stell\s+dich\s+ab|schalt\w*\s+dich\s+(ab|aus)|leg\s+dich\s+schlafen"
    r"|geh\s+(offline|schlafen)|mach\s+dich\s+aus|herunterfahren|runterfahren)"
)


def _guard_disruptive(plan: Plan) -> Plan:
    """Faengt ein Fehlrouting auf stop_runtime ab: fehlt in der Eingabe eine
    klare Abschalt-Formulierung, wird der Intent zu chat entschaerft (statt
    Jarvis still herunterzufahren). Nur stop_runtime - shutdown_pc hat als
    Stufe-3-Befehl ohnehin eine Rueckfrage als Netz."""
    if plan.intent == "stop_runtime" and not _SHUTDOWN_TRIGGER_RE.search(plan.raw_input or ""):
        logger.info(
            "stop_runtime ohne klare Abschalt-Formulierung in %r -> chat (Fehlrouting-Schutz).",
            plan.raw_input,
        )
        return Plan(intent="chat", target=None, confidence=0.0, raw_input=plan.raw_input)
    return plan


class Planner:
    def __init__(self, ai: AIEngine, tool_selector=None):
        self.ai = ai
        # Plan B (Tool-Vorfilter): optionaler Selector(user_input, schemas) ->
        # gefilterte Schemas. Von der Runtime injiziert; nur aktiv, wenn
        # config.tool_prefilter_enabled. Fehlt er, laeuft alles wie bisher.
        self._tool_selector = tool_selector

    def plan(self, user_input: str, history: list[Message]) -> list[Plan]:
        """Router-Entscheidung + optionaler denkender Kern (ADR-060).

        Der Router liefert wie bisher die Plaene. Ist der Kern aktiv (Schatten
        ODER mindestens ein Intent freigegeben), entscheidet er NEBENHER mit:
        - immer wird der Vergleich Router vs. Kern geloggt (Schatten, Scheibe 3c);
        - waehlt der Kern einen FREIGEGEBENEN Intent (Whitelist
          `reasoning_route_intents`, Phase 2 Strangler-Schalter), uebernimmt SEIN
          Plan - durch denselben `_guard_disruptive` und denselben Executor +
          ConfirmationGate wie jeder Router-Plan.
        Leere Whitelist = der Kern handelt nie (reiner Schatten / heutiges
        Verhalten). Fail-safe: der ganze Kern-Pfad ist gekapselt - wirft er,
        bleibt der Router allein zustaendig.

        PARALLEL statt seriell (Latenz-Messung 13.07.: Router 3,6 s + Kern
        2,5-10,3 s NACHEINANDER vor jedem Handgriff): ist der Kern aktiv,
        laeuft der Router im Nebenthread, der Kern im aufrufenden - beide
        LLM-Calls ueberlappen, die Planung wird um die kleinere der beiden
        Zeiten schneller. Semantik unveraendert: wirft der Router, propagiert
        seine Exception wie bisher; wirft der Kern, bleibt der Router allein
        zustaendig; Kern-Uebernahme nur ueber dieselbe Whitelist-Grenze."""
        if not self._core_path_active():
            return self._route(user_input, history)

        router_box: dict = {}

        def _run_router() -> None:
            try:
                router_box["plans"] = self._route(user_input, history)
            except BaseException as e:  # noqa: BLE001 - im Hauptthread re-raisen
                router_box["error"] = e

        router_thread = threading.Thread(
            target=_run_router, name="jarvis-router", daemon=True
        )
        router_thread.start()

        core_plans: "list[Plan]" = []
        try:
            core_plans = self._core_decision(user_input, history)
        except Exception:  # noqa: BLE001 - der Kern-Pfad stoert den Router nie
            logger.warning("Reasoning-Kern-Pfad fehlgeschlagen (ignoriert) -> Router.",
                           exc_info=True)

        router_thread.join()
        if "error" in router_box:
            raise router_box["error"]  # heutiges Verhalten: Router-Fehler propagiert
        router_plans = router_box["plans"]

        try:
            if core_plans:
                self._log_shadow(router_plans, core_plans)
                # Der Kern uebernimmt jetzt auch MEHRSCHRITTIG (ADR-064): die
                # frueher unzuverlaessig leeren Argumente bei parallelen Tool-
                # Aufrufen waren strukturell (generisches {target, parameters}-
                # Schema), NICHT Modell-Staerke. Mit TYPISIERTEN Schemas pro
                # Werkzeug (core/tool_params) fuellt der Kern die Felder auch
                # parallel zuverlaessig (Eval 2026-07-12: 24/24, inkl. 'Milch
                # UND Brot' -> items:['Milch','Brot']). Sicherheitsgrenze bleibt
                # _should_route: ALLE Schritte muessen freigegeben (Whitelist) und
                # keiner 'chat' sein - sonst faellt die GANZE Eingabe auf den
                # Router-Split zurueck (nie wandert ein gemischtes/gefaehrliches
                # Buendel ueber diesen Pfad). Ausfuehrung + alle Gates unveraendert.
                if self._should_route(core_plans):
                    logger.info(
                        "Reasoning-Kern FUEHRT %d Schritt(e): %s (Whitelist, ADR-064).",
                        len(core_plans), "+".join(p.intent for p in core_plans),
                    )
                    return [_guard_disruptive(p) for p in core_plans]
        except Exception:  # noqa: BLE001 - Vergleich/Uebernahme stoert den Router nie
            logger.warning("Reasoning-Kern-Pfad fehlgeschlagen (ignoriert) -> Router.",
                           exc_info=True)
        return router_plans

    def _core_path_active(self) -> bool:
        """Spiegelt die Aktiv-Bedingung von _core_decision (Schatten an ODER
        Whitelist nicht leer) - nur dann lohnt der Parallel-Thread; sonst
        laeuft der Router allein, ganz ohne Thread-Kosten."""
        config = getattr(self.ai, "config", None)
        return getattr(config, "reasoning_shadow", False) is True or bool(self._route_whitelist())

    def _core_decision(self, user_input: str, history: list[Message]) -> "list[Plan]":
        """Laesst den denkenden Kern entscheiden - aber NUR, wenn er gebraucht
        wird: Schatten an ODER mindestens ein Intent freigegeben. Sonst leere
        Liste (kein LLM-Call, Router allein). config defensiv ueber self.ai
        (manche AIEngine-Attrappen in Tests haben kein `config`)."""
        config = getattr(self.ai, "config", None)
        shadow_on = getattr(config, "reasoning_shadow", False) is True
        whitelist = self._route_whitelist()
        if not shadow_on and not whitelist:
            return []
        selector = self._tool_selector if getattr(config, "tool_prefilter_enabled", False) else None
        return reasoning.decide(user_input, history, self.ai.choose_tool,
                                select_tools=selector)

    def _route_whitelist(self) -> frozenset[str]:
        """Die freigegebenen Intents (`config.reasoning_route_intents`) als
        Menge. Fehlt/kaputt -> leer (fail-closed: nichts wird umgehaengt).
        `is True`-Analogon fuer Listen: nicht-iterierbares (z. B. ein MagicMock-
        Attribut in Mock-basierten Tests) faellt sauber auf leer zurueck."""
        config = getattr(self.ai, "config", None)
        raw = getattr(config, "reasoning_route_intents", None)
        if not isinstance(raw, (list, tuple, set, frozenset)):
            return frozenset()
        return frozenset(str(x) for x in raw)

    def _should_route(self, core_plans: "list[Plan]") -> bool:
        """Der Kern uebernimmt nur, wenn ALLE Schritte explizit freigegeben sind
        (Whitelist = Sicherheitsgrenze) und keiner 'chat' ist. Ein einziger
        nicht-freigegebener Schritt (z. B. ein gefaehrliches shutdown_pc in
        'wetter und fahr runter') -> die GANZE Eingabe bleibt beim Router; ueber
        diesen Pfad wandert nie ein gemischtes/gefaehrliches Bündel."""
        wl = self._route_whitelist()
        return bool(core_plans) and all(
            p.intent != "chat" and p.intent in wl for p in core_plans
        )

    def _log_shadow(self, router_plans: list[Plan], core_plans: "list[Plan]") -> None:
        """Vergleich Router vs. Kern (ADR-060 Scheibe 3c) - nur Intent-Namen und
        Ziel, nie Prompt-/Antwortinhalte. Mehrschrittig werden die Intents mit
        '+' verkettet (kern=get_weather+get_news). Consumer: core/dashboard_data.
        shadow_stats / scripts/shadow_report.py (per Contract-Test gekoppelt)."""
        router_intents = "+".join(p.intent for p in router_plans) or "?"
        kern_intents = "+".join(p.intent for p in core_plans) or "?"
        same = [p.intent for p in router_plans] == [p.intent for p in core_plans]
        logger.info(
            "Reasoning-Schatten [%s]: router=%s kern=%s (target=%r)",
            "MATCH" if same else "DIFF",
            router_intents, kern_intents,
            core_plans[0].target if core_plans else None,
        )

    def _route(self, user_input: str, history: list[Message]) -> list[Plan]:
        """Zerlegt user_input in 1..n Teilsätze und holt für jeden
        Teilsatz einen eigenen Plan von der KI. Reihenfolge bleibt
        erhalten - Schritt 1 wird vor Schritt 2 ausgeführt.

        AUSNAHME (Live-Befund 2026-07-10, Falsifizierbarkeit aus dem
        Moduldoc eingetreten): Ein ':' markiert "Befehl: Nutzlast"
        ("erledige in jkc: ...", "analysiere X: ...", "notiere: ...") -
        die Nutzlast darf Konnektoren wie "und" enthalten und wird NIE
        gesplittet. Der lange AP1-Delegations-Auftrag wurde sonst an
        jedem "und" zerhackt: Doppel-Rueckfragen, und der Agent bekam
        nur Spezifikations-Fragmente."""
        deepening = _idea_deepening_plan(user_input, history)
        if deepening is not None:
            return [deepening]

        # Anzeigename auf Zuruf (ADR-057): VOR dem Split, damit "nenn mich X"
        # nicht am "und" zerhackt wird und der Name-Wunsch zuverlaessig greift.
        naming = _owner_name_plan(user_input)
        if naming is not None:
            return [naming]

        # Vorschlag verwerfen (PO-Reibung 2026-07-11): deterministisch, damit
        # "verwirf den Entwurf" nie mehr als Herunterfahren fehlgedeutet wird.
        dismiss = _dismiss_proposal_plan(user_input)
        if dismiss is not None:
            return [dismiss]

        # Brainstorm-Auftakt -> Gespraech (nicht plan_next_step/Delegation).
        brainstorm = _brainstorm_plan(user_input)
        if brainstorm is not None:
            return [brainstorm]

        if ":" in user_input:
            return [_guard_disruptive(self.ai.get_plan(user_input, history))]

        parts = [p.strip() for p in _SPLIT_PATTERN.split(user_input) if p.strip()]

        if not parts:
            parts = [user_input]

        if len(parts) > 1:
            logger.info("Eingabe in %d Schritte zerlegt: %s", len(parts), parts)

        # _guard_disruptive faengt ein Fehlrouting auf stop_runtime ab (still
        # wirkender Shutdown ohne klare Ansage -> chat).
        return [_guard_disruptive(self.ai.get_plan(part, history)) for part in parts]
