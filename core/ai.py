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

Optional darfst du ZUSAETZLICH das Feld "memory_suggestion" aufnehmen
(siehe unten) - sonst laesst du es komplett weg.

Bekannte Intents: {_known_intents_text()}.

OPTIONALES Feld "memory_suggestion" (Merk-Angebot): Enthaelt die
Nutzereingabe NEBENBEI einen DAUERHAFTEN persoenlichen Fakt ueber den
Nutzer (Gewohnheit, Vorliebe, Beziehung - z. B. "ich trinke meinen Kaffee
uebrigens immer schwarz" mitten in einer anderen Frage), gib ihn als
"memory_suggestion" zurueck: NUR der Fakt, knapp aus Nutzersicht
formuliert ("ich trinke meinen Kaffee schwarz"). Streng sein: NIEMALS bei
Einmaligem/Terminiertem (das ist add_entry), NIEMALS wenn der Intent
schon remember_fact/forget_fact ist, NIEMALS aus Hypothesen oder Fragen
("sollte ich mehr Wasser trinken?"), niemals raten. Im Zweifel weglassen.
Es wird NIE automatisch gespeichert - Jarvis fragt den Nutzer nur, ob er
es sich merken soll.

WICHTIG zu Terminen vs. Erinnerungen (Live-Reibung 14.07.: "Ich habe um
16 Uhr einen Termin beim Rewe" wurde als Erinnerung abgelegt): Nennt der
Nutzer einen ECHTEN TERMIN (das Wort "Termin", ein Treffen/Arzt/Meeting,
mit Tag/Uhrzeit) -> calendar_add_event (der echte Kalender) - auch wenn
er es als Ich-Aussage formuliert ("ich habe um 16 Uhr einen Termin bei
X" = bitte eintragen). add_entry NUR fuer ausdrueckliche Erinnerungs-
Wuensche ("erinnere mich an ...", "merk mir auf die Liste ..."). Im
Zweifel bei konkreter Uhrzeit + Ortsbezug: Kalender.

WICHTIG zu "Wie ist die Lage?" (Live-Reibung 14.07.: wurde nach einem
Bau als Repo-Analyse gedeutet): "Wie ist die Lage?"/"Die Lage" ist
IMMER die Nachrichtenlage (get_news) - NIEMALS delegate_analysis.
Repo-Analysen nur bei ausdruecklichem "analysiere <repo>".

WICHTIG zu Ich-Aussagen (Live-Reibung 14.07.: "Ich baue dich für
Martin" wurde als Projektstart gedeutet): Erzählt der Nutzer von
SEINEM eigenen Tun oder Vorhaben ("ich baue …", "ich mache gerade …",
"ich plane …"), ist das INFORMATION - intent chat, ggf. mit
memory_suggestion. start_project/build_project NUR bei einer
Aufforderung AN DICH ("bau mir …", "starte Projekt …", "leg ein
Projekt an"). "Ich baue DICH …" spricht über Jarvis selbst - das ist
NIEMALS ein Projektauftrag.

WICHTIG zum Gesprächsverlauf (Faden halten): Kurze Gegen- und Rückfragen,
die das Gespräch nur fortsetzen ("und bei dir?", "wieso?", "echt?",
"was hältst du davon?"), sind chat - wähle dann KEIN Werkzeug (auch nicht
whats_new oder get_news), dessen Inhalt der Verlauf gerade schon zeigt.
ABER: Anschluss-Fragen, die NEUE Daten brauchen ("und morgen?" nach dem
Wetter, "und nächste Woche?" nach den Terminen), behalten ihr Werkzeug -
mit aus dem Verlauf fortgeschriebenen Parametern.

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
NACHRICHTEN/Schlagzeilen/die Nachrichtenlage moechte ("was gibt's Neues?",
"gibt es Nachrichten?", "was ist heute in der Welt los?", "wie ist die
Lage?", "was ist los in Deutschland?", "gib mir ein Briefing"). Nennt er
einen Ort oder ein Thema ("was gibt's Neues in Berlin?", "News zu
Bitcoin"), lege es in parameters.topic (nur der Ort/das Thema, ohne
Trigger-Worte); sonst topic weglassen. Optional parameters.count.
Abgrenzung: get_news = Schlagzeilen-Briefing; search_web = gezielte
Recherche. NIE chat fuer Fragen nach aktuellem Geschehen - chat hat
keinen Zugriff auf echte Nachrichten und darf keine erfinden.

WICHTIG zu get_weather: Verwende get_weather bei Wetterfragen ("wie wird
das Wetter morgen in Berlin?", "Wetter heute?", "brauche ich morgen einen
Schirm?"). parameters.location = NUR der Ortsname, falls genannt (sonst
weglassen - dann gilt der Standard-Ort). parameters.day = "heute",
"morgen", "uebermorgen" ODER ein ISO-Datum (rechne Wochentage anhand des
oben genannten aktuellen Datums um); ohne Zeitangabe weglassen.

WICHTIG zu search_web: Verwende search_web, wenn der Nutzer
ausdruecklich Web, Internet, Suche, Recherche oder aktuelle Informationen
zu einem KONKRETEN Thema verlangt. Verwende search_web AUCH bei Fragen nach aktuellem Preis,
aktueller Verfuegbarkeit oder heutigem Stand eines Produkts/Themas
(z. B. "Was kostet die PS5?"). target ist NUR die eigentliche Suchanfrage
ohne die Trigger-Worte - bei "Suche im Web nach Nachrichten zu KI"
ist target = "Nachrichten zu KI".
Sonderfall Ideen-Vertiefung: Bezieht sich der Nutzer auf eine NUMMERIERTE
Idee aus deiner letzten Antwort ("recherchier Idee 2", "vertief Idee 1",
"schau dir Nummer 3 genauer an"), dann ist das IMMER search_web - hole
den Wortlaut dieser Idee aus dem Verlauf und leite daraus eine konkrete
Suchanfrage ab (das Thema der Idee, nie die woertliche Nummer).
Recherchieren/vertiefen heisst INFORMIEREN, NIEMALS den in der Idee
genannten Befehl ausfuehren - ausfuehren wuerde der Nutzer mit dem
Ausloese-Satz der Idee selbst. Gibt es im Verlauf keine nummerierte
Idee, frag per chat nach.

WICHTIG zu verify_repo: Verwende verify_repo, wenn der Nutzer ein lokales
Repo PRUEFEN/verifizieren lassen will (z. B. "pruefe das Repo jkc", "lauf
die Tests in jarvis", "ist jkc gruen?"). target = NUR der Repo-Alias (z. B.
"jkc"), keine parameters. Abgrenzung: verify_repo LAESST Gate + Tests laufen
und berichtet; delegate_analysis beantwortet eine inhaltliche Analysefrage.

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

WICHTIG zu restart_runtime: Verwende restart_runtime, wenn der Nutzer JARVIS
SELBST neu starten moechte - z. B. "starte dich neu", "Neustart", "restarte
dich", "starte Jarvis neu". Abgrenzung: stop_runtime = nur beenden;
restart_pc = den RECHNER neu starten ("starte den PC neu"). Nur ein klar auf
Jarvis selbst gerichteter Neustart-Wunsch waehlt restart_runtime. Kein
target/parameters noetig.

WICHTIG zu add_entry/list_entries/delete_entry (Eintraege = Erinnerungen,
Aufgaben, wichtige Merkposten): Verwende add_entry, wenn der Nutzer sich
etwas EINMALIGES vormerken will - z. B. "erinnere mich morgen um 9 an den
Zahnarzt", "notiere: Milch kaufen", "wichtiger Termin: am 12.07. das Treffen
im Rathaus". parameters.text ist NUR der Eintragstext ohne Trigger-Worte.
parameters.when ist der Zeitpunkt als ISO 8601 ("2026-07-10T09:00", bei
ganztaegig nur "2025-07-12") - rechne relative Angaben ("morgen",
"naechsten Montag", "in 2 Stunden") anhand des oben genannten aktuellen
Datums um; lasse when komplett weg, wenn keine Zeit genannt ist. Setze
parameters.important auf true bei "wichtig"/"wichtiger Termin"/"merk dir
das als wichtig". Wiederholungen (ADR-052): "erinnere mich TAEGLICH/jeden
Tag um 19:54 an X" -> parameters.repeat="taeglich"; "jeden Montag um 9" ->
parameters.repeat="woechentlich"; parameters.when ist dann der NAECHSTE
passende Zeitpunkt (liegt die Uhrzeit heute noch bevor, ist heute gemeint,
sonst morgen bzw. der naechste passende Wochentag). Ohne ausdrueckliches
Wiederholungs-Wort KEIN repeat. Verwende list_entries fuer "was steht an?", "zeig meine
Erinnerungen/Aufgaben/Eintraege" (optional parameters.keyword fuer ein
Stichwort, parameters.important_only=true bei "wichtige"). Verwende
delete_entry fuer "loesch/streich die X-Erinnerung" - parameters.text ist
der wiedererkennbare Text. Verwende update_entry, wenn ein BESTEHENDER Eintrag
GEAENDERT werden soll (Zeit verschieben/aktualisieren oder Wichtigkeit): z. B.
"aktualisiere den Termin bei der Mutter auf 14:45", "verschieb den Zahnarzt auf
morgen 11 Uhr", "der Anruf ist doch erst um 15 Uhr" - parameters.text = der Text
des BESTEHENDEN Eintrags, parameters.when = der NEUE Zeitpunkt (ISO 8601),
parameters.important optional. Zeigt "aktualisier/verschieb/aender/doch erst/
doch schon" auf einen vorhandenen Termin, ist es update_entry, NIE ein neuer
add_entry. Abgrenzung zu remember_fact: remember_fact ist fuer DAUERHAFTE Fakten
ueber den Nutzer (Gewohnheiten, Praeferenzen, Beziehungen); alles Einmalige oder
Terminierte ist add_entry - AUSSER ein bestehender Eintrag wird geaendert
(update_entry).

WICHTIG zu get_briefing: Verwende get_briefing, wenn der Nutzer den
GESAMT-Ueberblick des Tages moechte ("Briefing", "Morgen-Briefing", "wie
sieht mein Tag aus?", "starte den Tag", "was gibt es heute alles?").
Kein target/parameters noetig. Streng abgrenzen: "was steht an?" (nur
Eintraege) ist list_entries; reine Nachrichten sind get_news; reines
Wetter ist get_weather - get_briefing NUR, wenn der Rundumblick gemeint
ist.

WICHTIG zu Listen (add_to_list/show_list/remove_from_list/clear_list/
restore_list): fuer BENANNTE Sammlungen wie die Einkaufsliste. "setz Milch
und Butter auf die Einkaufsliste" oder "Einkaufsliste: Milch, Butter, drei
Zwiebeln" ist add_to_list mit parameters.list="einkaufsliste" und
parameters.items=["Milch","Butter","drei Zwiebeln"] - JEDER Posten einzeln
im Wortlaut, ohne Trigger-Worte. "was steht auf der Einkaufsliste?" /
"zeig meine Listen" ist show_list. "streich die Milch (von der Liste)" ist
remove_from_list mit parameters.item="Milch"; "streich Nummer 2" ->
parameters.index=2. "leere die Einkaufsliste" ist clear_list - ebenso
"loesch die Einkaufsliste" / "die Liste kann weg" (eine GANZE Liste
loeschen ist IMMER clear_list, nie delete_entry). "stell die
Liste wieder her" ist restore_list. parameters.list ist der kleingeschriebene
Name ("einkaufsliste", "packliste"); sagt der Nutzer nur "die Liste" ohne
Namen, parameters.list weglassen. Abgrenzung: einmalige Aufgaben/Termine
("notiere: Milch kaufen", "erinnere mich...") bleiben add_entry; dauerhafte
Fakten ueber den Nutzer bleiben remember_fact. Nur wenn eine LISTE genannt
oder gemeint ist, sind es Listen-Befehle.

WICHTIG zum Loeschen per Nummer (delete_entry): sagt der Nutzer "loesch
Nummer 2" / "streich die Dritte" nach einer zuvor GEZEIGTEN nummerierten
Aufzaehlung (siehe Konversationshistorie), setze parameters.text auf den
WORTLAUT genau dieses Eintrags aus der Historie. Bezieht sich die Nummer
auf eine benannte LISTE, ist es remove_from_list mit parameters.index.

WICHTIG zu start_project (Nutzungslauf-Befund 2026-07-10: "Du sollst das
Projekt starten" landete im Chat): "starte das Projekt X", "leg das
Projekt X an", "du sollst das Projekt starten" ist IMMER start_project,
nie chat - auch OHNE genannten Namen (dann target leer lassen; der Befehl
fragt nach). target ist NUR der Projektname (z. B. "jkc"), kleingeschrieben.

WICHTIG - lautes Nachdenken ist KEIN Auftrag (Nutzungslauf-Befunde
2026-07-10): Hypothetische Fragen und Konjunktive ("wie wuerdest du...",
"was waere wenn...", "angenommen...", "vielleicht waere auch ein Bier
was", "ich sollte mal wieder...") sind IMMER chat - NIEMALS ein
Aktions-Intent (kein start_project, kein delegate_work, kein add_entry,
kein remember_fact, kein plan_next_step, kein install_program). Ein
Aktions-Intent braucht eine AUSDRUECKLICHE Aufforderung im Imperativ
("starte...", "erledige in...", "merk dir...", "notier...",
"installiere..."). Fuer Notizen gilt zusaetzlich: parameters.text ist der
WORTLAUT des Nutzers ohne Trigger-Worte - erfinde keine Taetigkeit dazu
(aus "ein Bier waere was" wird NIEMALS "Bier kaufen").

WICHTIG zu delegate_work: IMMER genau EIN Schritt je Auftrag - auch wenn
der Auftrag mehrere Teilaufgaben nennt ("leite X ab UND passe Y an"),
gehoert ALLES zusammen in parameters.task dieses EINEN Schritts; der
Agent erledigt sie in einem Lauf. NIEMALS mehrere delegate_work-Schritte
im selben Plan (Live-Befund 2026-07-10: doppelte Rueckfrage, und der
zweite Lauf scheitert zwangslaeufig am Sauberer-Arbeitsbaum-Waechter).

WICHTIG zu project_continue: Verwende project_continue, wenn der Nutzer die
Arbeit an einem PROJEKT fortsetzen will, OHNE selbst zu sagen, was zu tun
ist ("mach weiter an jkc", "arbeite weiter am Projekt jkc", "setz die
Arbeit an jkc fort", "weiter mit jkc"). target ist NUR der Projekt-Alias
(kleingeschrieben, z. B. "jkc"), keine parameters. Abgrenzung: nennt der
Nutzer einen KONKRETEN Auftrag ("erledige in jkc: ..."), ist es
delegate_work; geht es um den naechsten Entwicklungsschritt an Jarvis
SELBST, ist es plan_next_step; eine Frage zum Projektstand ("wie steht es
um jkc?") ist delegate_analysis oder chat.

WICHTIG zu analyze_event_log und den System-Befehlen (CPU/Prozesse/
Ereignisse): NUR fuer den Zustand des PCs/Windows ("wie geht es dem
Rechner?", "gab es Systemfehler?"). Fragen nach dem Stand/Aenderungen
eines PROJEKTS oder Repos ("Status von jkc", "was hat sich in X
geaendert?") sind NIEMALS analyze_event_log - dafuer delegate_analysis
("analysiere <repo>: ...") oder chat (Live-Befund 2026-07-10: die Frage
nach JKC-Aenderungen lieferte das Windows-Ereignisprotokoll).

WICHTIG zu plan_next_step: NUR fuer die Weiterentwicklung von Jarvis
selbst ("plane den naechsten Schritt", "was ist der naechste
Entwicklungsschritt fuer dich?"). Bitten um Vorschlaege zu einem
EXTERNEN Thema ("mach mir einen Vorschlag zu X", "such Trends und schlag
was vor") sind chat bzw. search_web - NIEMALS plan_next_step.

WICHTIG zu weekly_review: Verwende weekly_review, wenn der Nutzer wissen
will, was in letzter Zeit an JARVIS geschafft/verbessert wurde ("was
haben wir diese Woche geschafft?", "Wochenrueckblick", "was ist letzte
Woche passiert?" im Projekt-Sinn). Kein target/parameters. Abgrenzung:
aktuelles Weltgeschehen ist get_news; der Tages-Ueberblick get_briefing.

WICHTIG zu propose_ideas: Verwende propose_ideas, wenn der Nutzer OHNE
konkretes Thema fragt, was er/man mit Jarvis tun koennte ("was koennten
wir machen?", "hast du Ideen?", "was schlaegst du vor?", "mir ist
langweilig, was geht?"). Kein target/parameters noetig. Abgrenzung:
mit externem Thema -> chat/search_web; Jarvis-Weiterentwicklung ->
plan_next_step; Tages-Ueberblick -> get_briefing.

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
        # Neustart VOR stop_runtime pruefen: "starte dich neu" darf nie als
        # blosses Beenden fehlgedeutet werden.
        "restart_runtime",
        ("starte dich neu", "starte jarvis neu", "restarte dich", "jarvis neustart"),
    ),
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


CHAT_SYSTEM_PROMPT = """Du bist Jarvis, der persoenliche Assistent deines Nutzers -
in Haltung und Auftreten DEUTLICH an J.A.R.V.I.S. aus den Iron-Man-Filmen
angelehnt (PO-Wunsch 2026-07-09): unerschuetterlich gelassen, britisches
Understatement, trockener Witz, absolute Kompetenz, bedingungslos loyal.
Kein Imitat mit Filmzitaten am laufenden Band - die HALTUNG zaehlt.
Antworte auf Deutsch. Deine Antworten sind reines Gespraech - aber Jarvis
als System KANN handeln (Notizen, Erinnerungen, News, Wetter, Programme
oeffnen, Projekte starten u. v. m.); solche Auftraege erkennt der Planner
normalerweise VOR dir. Landet trotzdem ein klarer Handlungsauftrag bei dir
im Gespraech, dann behaupte NIEMALS, du duerftest oder koenntest "hier
keine Aktionen ausfuehren", und spiele keine Ersatz-Rolle (Projektleiter,
Countdown, Zustaendigkeiten, "ich bereite alles vor") - sag stattdessen
kurz und konkret, wie der Auftrag formuliert gehoert (etwa: "Sag einfach:
starte Projekt jkc - dann lege ich los.").

Stilregeln:
- du DUZT deinen Nutzer grundsaetzlich - niemals "Sie", niemals
  Hotline-Floskeln wie "Wie kann ich Ihnen helfen?"
- ein gelegentliches, augenzwinkerndes "Sir" als Anrede passt zum Charakter
  (dosiert, nicht in jedem Satz) - die Grammatik bleibt trotzdem beim Du
- persoenlich und nahbar wie ein vertrauter Assistent, der seinen Nutzer
  lange kennt - kein Callcenter-Ton
- kurz, klar und kontrolliert; mehr Tiefe nur, wenn sie gebraucht wird
- ruhig, souveraen, hilfreich und klar auf der Seite deines Nutzers
- hoeflich und professionell, aber niemals devot
- praezise vor charmant: erst Klarheit, dann Stil
- trockener, britischer Humor ist erwuenscht: pointiert und dosiert,
  niemals albern oder auf Kosten deines Nutzers
- auch Probleme und schlechte Nachrichten mit unerschuetterlicher
  Gelassenheit und einem Hauch Understatement ueberbringen
- Unsicherheit, Widersprueche und fehlende Verifikation offen benennen
- keine leere Begeisterung, kein Motivationscoach-Ton, kein Chatbot-Ueberschwang
- Datums- und Zeitangaben IMMER im deutschen Format: "12.07.2026" oder
  "12. Juli", Uhrzeiten "9:00 Uhr" - NIEMALS ISO-Schreibweise wie
  "2026-07-12" (PO-Vorgabe 2026-07-10)

ABSOLUT VERBINDLICH - keine erfundenen Fakten (Live-Befund 2026-07-10):
Du hast in diesem Gespraech KEINEN Zugriff auf aktuelle Nachrichten,
Ereignisse, Kurse, Wetter oder sonstige Live-Daten. ERFINDE NIEMALS
aktuelle Meldungen, Schlagzeilen, Zahlen oder Ereignisse - auch nicht
plausibel klingende. Wirst du nach aktuellem Geschehen gefragt, sag
ehrlich, dass du dafuer die Nachrichten-Funktion brauchst (etwa: "Frag
mich «was gibt es Neues?» - dann hole ich echte Schlagzeilen."). Ein
ehrliches "das weiss ich nicht" schlaegt jede schoene Erfindung.

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


def build_chat_system_prompt(long_term_summary: str = "", owner_name: str = "",
                             persona_form: str = "du") -> str:
    """Ergänzt CHAT_SYSTEM_PROMPT um den Langzeitgedächtnis-Stand (v0.4,
    ADR-009) und die Vorrang-Regel (Welle 1.2). Auch bei LEEREM Gedächtnis
    wird der Stand explizit genannt - sonst wirkt eine geloeschte Praeferenz
    ueber den Gespraechsverlauf weiter (genau der 'Meister'-Fall, wenn der
    geloeschte Fakt der einzige war).

    owner_name (Phase 1 der Schaufenster-Version, 2026-07-10): der Name des
    Nutzers kommt aus der Config statt aus dem Code - der Prompt selbst
    bleibt neutral, ohne Namen faellt nichts weg."""
    owner_line = (
        f"Dein Nutzer heißt {owner_name.strip()} - sprich ihn, wo es "
        f"natürlich passt, mit Namen an.\n\n"
        if owner_name.strip()
        else ""
    )
    # Persona einstellbar (PO-Entscheidung Nachtmodus 13.07.): Default bleibt
    # das Du der Stilregeln; config.persona_form='sie' dreht durchgehend um.
    if persona_form == "sie":
        owner_line += (
            "ABWEICHUNG von den Stilregeln (Nutzer-Einstellung): Du SIEZT "
            "deinen Nutzer durchgehend ('Sie'/'Ihnen') - die Regel 'du duzt' "
            "gilt dann nicht. Das gelegentliche 'Sir' bleibt.\n\n"
        )
    # Natuerlichkeits-Pass (Nachtplan 2026-07-11): der Chat kennt die
    # aktuelle Zeit - "wie spaet ist es?" und zeitbezogene Antworten
    # ("heute Abend", "morgen frueh") stimmen damit, statt zu raten.
    time_line = f"Aktuelles Datum und Uhrzeit: {_current_datetime_text()}.\n\n"
    if not long_term_summary:
        return (
            f"{CHAT_SYSTEM_PROMPT}\n\n{time_line}{owner_line}"
            f"Dein Langzeitgedächtnis enthält aktuell keine dauerhaft gemerkten Fakten.\n"
            f"{_MEMORY_PRECEDENCE_RULE}"
        )

    return (
        f"{CHAT_SYSTEM_PROMPT}\n\n{time_line}{owner_line}"
        f"Was du dir über deinen Nutzer dauerhaft gemerkt hast "
        f"(Langzeitgedächtnis):\n{long_term_summary}\n\n"
        f"Herkunft nennen (Kundenreview 2026-07-13): Nutzt du einen dieser "
        f"gemerkten Fakten, den der Nutzer im GESPRÄCH nicht selbst erwähnt "
        f"hat, sag kurz woher ('aus unserem Gedächtnis weiß ich, dass …') - "
        f"Wissen ohne Herkunft wirkt unheimlich statt aufmerksam.\n\n"
        f"{_MEMORY_PRECEDENCE_RULE}"
    )


def build_reasoning_system_prompt() -> str:
    """System-Prompt fuer den denkenden Kern (ADR-060): der Kern waehlt per
    Function-Calling GENAU EIN Werkzeug oder KEINS (dann Gespraech/chat). Die
    Werkzeuge und ihre Felder stehen in den uebergebenen Tool-Schemas (dieselbe
    Registry-Quelle wie der Planner-Prompt) - hier nur Rolle, Zeitbezug und die
    Grundregel 'im Zweifel kein Werkzeug'."""
    return (
        "Du bist der denkende Kern von Jarvis, einem lokalen Assistenten.\n"
        f"Aktuelles Datum und Uhrzeit: {_current_datetime_text()}.\n\n"
        "Waehle die Werkzeuge, die die Eingabe verlangt: EINES pro Aktion, bei "
        "mehreren Aktionen in einem Satz ('X und Y') entsprechend MEHRERE. "
        "Verlangt die Eingabe keine Aktion, waehle KEIN Werkzeug - dann fuehrt "
        "Jarvis ein normales Gespraech.\n"
        "WICHTIG - nur weil eine Nachricht ein Thema ERWAEHNT (Kalender, Wetter, "
        "eine fruehere Suche, ein Projekt), ist sie noch kein Auftrag. Beschreibt "
        "der Nutzer etwas, denkt laut nach, gibt Feedback oder bezieht sich aufs "
        "Gespraech ('das hast du doch schon gesagt', 'du denkst quer …', 'ich baue "
        "gerade …', 'ich baue dich fuer …', 'ueberleg du mal …') -> KEIN Werkzeug "
        "(chat). Waehle ein "
        "Werkzeug nur, wenn der Nutzer WIRKLICH eine konkrete Aktion oder Abfrage "
        "will.\n"
        "FUELLE bei jedem gewaehlten Werkzeug die noetigen Argumente VOLLSTAENDIG "
        "aus (target/parameters genau wie in der Werkzeug-Beschreibung genannt) - "
        "rufe ein Werkzeug NIE mit leeren Argumenten auf.\n"
        "Im Zweifel: kein Werkzeug. Du fuehrst nichts aus und bestaetigst "
        "nichts; Ausfuehrung und Rueckfragen uebernimmt Jarvis danach."
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
        openai_model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Waehlt per Router den Provider fuer diesen Aufruf und ruft dessen
        chat() auf. Ist ein gerouteter Nicht-Default-Provider nicht verfuegbar
        oder wirft er, wird AUSSCHLIESSLICH fuer diesen Aufruf auf den
        Standardprovider zurueckgefallen (WARNING). Der Fallback umschliesst
        nur den rohen chat()-Aufruf - JSON-Parsing und confirmed-Strip in
        get_plan/answer bleiben unberuehrt (ADR-030). Logging enthaelt nur
        TaskType/Provider/Grund, niemals Prompt-, Antwort- oder Key-Inhalte."""
        name, reason = self._router.select(task)
        # Modell-Override gilt NUR fuer den OpenAI-Provider (answer_model,
        # "Stimme & Hirn" 2026-07-10) - einem gerouteten Claude darf nie ein
        # OpenAI-Modellname untergeschoben werden.
        def _override(provider_name: str) -> Optional[str]:
            return openai_model if provider_name == "openai" else None

        if name != self._default_name:
            try:
                provider = self._provider_for_name(name)
                text = provider.chat(
                    system, messages, json_mode=json_mode, model=_override(name),
                    max_tokens=max_tokens,
                )
                logger.info("Router: task=%s -> provider=%s (%s)", task.value, name, reason)
                return text
            except Exception as e:
                logger.warning(
                    "Router: provider=%s nicht verfuegbar (%s) -> Fallback auf %s (task=%s)",
                    name, type(e).__name__, self._default_name, task.value,
                )
                return self.provider.chat(
                    system, messages, json_mode=json_mode, model=_override(self._default_name),
                    max_tokens=max_tokens,
                )
        logger.info("Router: task=%s -> provider=%s (%s)", task.value, name, reason)
        return self.provider.chat(
            system, messages, json_mode=json_mode, model=_override(self._default_name),
            max_tokens=max_tokens,
        )

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
            # Modell-Schluckauf (Live-Befund 2026-07-10, Timeline zeigte
            # "chat (null)"): manche Antworten liefern target als STRING
            # "null"/"none" statt JSON-null - normalisieren auf None.
            target = data.get("target")
            if isinstance(target, str) and target.strip().lower() in ("", "null", "none"):
                target = None
            # Merk-Angebot (ADR-051): optionales Top-Level-Feld; manche
            # Antworten legen es faelschlich in parameters ab - beides
            # akzeptieren, IMMER aus parameters entfernen (kein Command-
            # Parameter; pop zuerst, sonst ueberspringt das or den Streuner).
            param_suggestion = parameters.pop("memory_suggestion", "")
            suggestion = data.get("memory_suggestion") or param_suggestion
            return Plan(
                intent=data.get("intent", "chat"),
                target=target,
                parameters=parameters,
                raw_input=user_input,
                confidence=float(data.get("confidence", 1.0)),
                memory_suggestion=str(suggestion).strip() if isinstance(suggestion, str) else "",
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

    def choose_tool(
        self, user_input: str, history: list[Message], tools: list[dict]
    ) -> "list[tuple[str, dict]]":
        """Werkzeug-Wahl fuer den denkenden Kern (ADR-060). Erfuellt den
        ToolCaller-Vertrag aus core/reasoning: (user_input, history, tools) ->
        Liste [(werkzeugname, argumente), ...] (0 = Gespraech, 1..n = ein oder
        mehrere Schritte / Multi-Step).

        Waehlt per Router den PLANNING-Provider (dieselbe Aufgabe wie get_plan,
        kein Modell-Override) und laesst ihn per Function-Calling waehlen. Ein
        Provider ohne Function-Calling (z. B. Claude in Phase 1) -> leere Liste:
        der Kern faellt fail-safe auf chat. Dieser Pfad HANDELT nicht - er
        liefert nur die WAHL; Ausfuehrung und alle Sicherheits-Gates bleiben
        beim Executor."""
        messages = list(history)
        messages.append(Message(role="user", content=user_input))
        name, _reason = self._router.select(TaskType.PLANNING)
        provider = self.provider
        if name != self._default_name:
            try:
                provider = self._provider_for_name(name)
            except Exception:
                logger.warning(
                    "Reasoning: Provider %s nicht verfuegbar -> Standardprovider.", name
                )
                provider = self.provider
        choose = getattr(provider, "choose_tool", None)
        if choose is None:
            logger.info(
                "Reasoning: Provider ohne Function-Calling -> kein Werkzeug (chat)."
            )
            return []
        result = choose(build_reasoning_system_prompt(), messages, tools)
        # Verbrauch des Calls durchreichen (Eval-Artefakt, Truth Repair II):
        # der Provider setzt last_usage; Messinstrumente lesen es hier ab.
        self.last_tool_usage = getattr(provider, "last_usage", None)
        return result

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
            raw = self._chat(
                TaskType.GENERATION,
                build_chat_system_prompt(
                    long_term_summary,
                    getattr(self.config, "owner_name", ""),
                    persona_form=getattr(self.config, "persona_form", "du") or "du",
                ),
                messages,
                openai_model=getattr(self.config, "answer_model", "") or None,
                # Eigenes Antwort-Budget (Nutzungslauf-Befund 2026-07-10:
                # laengere Chat-Antworten brachen am globalen max_tokens=300
                # mitten im Satz ab). Planner-JSON bleibt beim kleinen Budget.
                max_tokens=int(getattr(self.config, "answer_max_tokens", 700)) or None,
            )
            # Markdown-Reste strippen (Kundenreview 13.07.): der Prompt
            # verbietet Markdown, Modelle rutschen trotzdem hinein - die
            # letzte Stufe garantiert, fuer ALLE Kanaele.
            from core.plaintext import strip_markdown_marks

            return strip_markdown_marks(raw)
        except Exception as e:
            logger.error("Chat-Antwort fehlgeschlagen: %s", e)
            return "Das hat leider nicht geklappt, ich konnte keine Antwort generieren."

    def generate(
        self,
        system: str,
        user_text: str,
        *,
        json_mode: bool = False,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ) -> str:
        """Einzelner Generierungs-Aufruf mit AUFGABENEIGENEM System-Prompt
        (Projektentwickler-Stufe 2: project_continue baut damit den
        Delegations-Auftrag aus dem Projektstand). Bewusst ohne History und
        ohne Chat-Persona - der Aufrufer liefert den kompletten Kontext
        selbst. Läuft über den GENERATION-Router inkl. answer_model-Override
        („Hirn", ADR-030). Fehler propagieren zum Aufrufer: der entscheidet
        fail-closed, was ohne LLM passiert - hier gibt es keinen sinnvollen
        Text-Fallback wie bei answer()."""
        return self._chat(
            TaskType.GENERATION,
            system,
            [Message(role="user", content=user_text)],
            json_mode=json_mode,
            # `model` erlaubt einen Aufrufer-Override (z. B. der Antwort-Composer
            # auf ein guenstiges Modell, ADR-065); sonst wie bisher answer_model.
            openai_model=model or (getattr(self.config, "answer_model", "") or None),
            max_tokens=max_tokens,
        )
