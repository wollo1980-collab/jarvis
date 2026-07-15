"""
Entdeckung (Spektakulaer-Kampagne #1, Kundenreview 13.07.2026):
„Was kannst du?" und „Was ist neu?".

Der Review-Kernbefund: Jarvis hat 60+ Faehigkeiten und KEIN Hilfe-Erlebnis -
fuer den Anwender existiert nur, was er zufaellig entdeckt. Zwei Befehle:

- show_help: kuratierte, ehrliche Uebersicht mit echten Beispiel-Saetzen.
  BEWUSST von Hand kuratiert statt aus der Registry generiert (62 rohe
  Befehlsnamen erschlagen; die Auswahl IST das Produkt) - aber gegen die
  Registry ABGESICHERT: ein Test prueft, dass jede referenzierte Faehigkeit
  wirklich existiert (nie erfundene Versprechen).
- whats_new: liest docs/CHANGELOG.md (wird ohnehin in Anwendersprache
  gepflegt) und traegt die juengsten Neuerungen vor.

Beide nur lesend, Stufe 0.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.models import Plan, Result, Status

logger = logging.getLogger("jarvis.commands.help")

_changelog_path: Optional[Path] = None


def configure(changelog_path) -> None:
    """Von der Verdrahtungsschicht beim Start aufgerufen (BASE_DIR/docs/
    CHANGELOG.md). Ohne Aufruf faellt whats_new ehrlich aus."""
    global _changelog_path
    _changelog_path = Path(changelog_path) if changelog_path else None


# Jede hier VERSPROCHENE Faehigkeit muss registriert sein - der Test
# test_help_references_only_real_intents haelt Hilfe und Realitaet synchron.
REFERENCED_INTENTS = (
    "get_briefing", "list_entries", "calendar_add_event", "add_entry",
    "add_to_list", "get_weather", "get_news", "remember_fact", "who_is",
    "list_facts", "forget_fact", "check_mail", "spotify_play", "open_program",
    "system_status", "build_project", "stop_agent", "list_skills",
    "propose_ideas", "self_review", "whats_new", "search_web",
)

_HELP_TEXT = """{gruss} — das Wichtigste, was ich für dich tun kann:

🌅 Alltag: «Briefing» (kommt morgens auch von selbst aufs Handy) · «Was steht morgen an?» · «Trag Zahnarzt Dienstag 9 Uhr ein» · «Erinnere mich alle zwei Wochen ans Gießen» · «Milch auf die Einkaufsliste» · «Wetter morgen» · «Was gibt's Neues in der Welt?»
🧠 Gedächtnis: «Merk dir, dass …» · «Wer ist Anna?» · «Was hast du dir gemerkt?» · «Vergiss das wieder»
📬 Mails: «Was liegt im Postfach an?» — ich sage dir, was zuerst wichtig ist
🎵🖥️ Musik & PC: «Spiel Musik» · «Öffne <Programm>» · «Wie geht es dem PC?» · «Recherchier mir …»
🔨 Bauen: «Bau mir <ein kleines Werkzeug>» — ich baue echte Software, frage vor allem Wichtigen nach, und «stopp den Agenten» hält alles an · «Was hast du schon gebaut?» · «Was könnten wir bauen?»
🪞 Über mich: «Wie schlägst du dich?» (ehrliche Selbstbewertung) · «Was ist neu?» (meine neuesten Fähigkeiten)

Sag es einfach in deinen Worten — ich verstehe normales Deutsch. Und vieles biete ich dir von selbst an, bevor du fragst."""


def _greeting(now: Optional[datetime] = None) -> str:
    hour = (now or datetime.now()).hour
    if 5 <= hour < 11:
        return "Guten Morgen, Sir"
    if 18 <= hour < 24:
        return "Guten Abend, Sir"
    return "Gern, Sir"


class ShowHelpCommand:
    name = "show_help"
    description = (
        "Stellt vor, was Jarvis alles kann - die Hilfe/Uebersicht der "
        "Faehigkeiten mit Beispiel-Saetzen (z. B. 'was kannst du?', 'hilfe', "
        "'was kann ich dich fragen?', 'welche befehle gibt es?', 'was geht?'). "
        "Nur lesend. Abgrenzung: 'was hast du gebaut' ist list_skills, 'was ist "
        "neu (bei dir)' ist whats_new, Welt-Nachrichten sind get_news."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        return Result(status=Status.SUCCESS,
                      message=_HELP_TEXT.format(gruss=_greeting()))


def _latest_blocks(text: str, max_blocks: int = 2, max_chars: int = 1400) -> str:
    """Die juengsten CHANGELOG-Bloecke (## ...) als vortragbarer Text:
    Markdown-Fett raus (sprechtauglich), Abschnitts-Kopfzeilen (###) raus."""
    blocks = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    out: list[str] = []
    for block in blocks[:max_blocks]:
        lines = [ln for ln in block.splitlines() if not ln.startswith("###")]
        cleaned = "\n".join(lines).replace("**", "").strip()
        out.append(cleaned)
    joined = "\n\n".join(out).strip()
    if len(joined) <= max_chars:
        return joined
    # Live-Reibung 13.07. 23:00: der harte [:max_chars]-Schnitt endete mitten
    # im Wort («... ist ent …»). An der letzten VOLLSTAENDIGEN Zeile schneiden
    # und ehrlich abrunden - nie ein Wortstumpf.
    cut = joined[:max_chars]
    boundary = cut.rfind("\n")
    if boundary > 200:  # fail-safe: genug Substanz behalten
        cut = cut[:boundary]
    return cut.rstrip() + "\n\n… und ein paar Dinge mehr."


def latest_headline(changelog_path=None) -> str:
    """Die Titelzeile des juengsten Eintrags ('' wenn keiner) - fuer den
    einmaligen 'Neu bei mir'-Hinweis der Runtime. Fail-safe."""
    path = Path(changelog_path) if changelog_path else _changelog_path
    try:
        if path is None or not path.is_file():
            return ""
        match = re.search(r"^## (.+)$", path.read_text(encoding="utf-8"), re.MULTILINE)
        return match.group(1).strip() if match else ""
    except Exception:  # noqa: BLE001
        return ""


class WhatsNewCommand:
    name = "whats_new"
    description = (
        "Traegt vor, was JARVIS SELBST Neues gelernt hat - seine neuesten "
        "Faehigkeiten/Verbesserungen (z. B. 'was ist neu?', 'was ist neu bei "
        "dir?', 'was hast du neues gelernt?', 'gibt es updates?'). Nur lesend. "
        "NICHT fuer Welt-/Tagesnachrichten - das ist get_news ('was gibt es "
        "Neues in der Welt?')."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        if _changelog_path is None or not _changelog_path.is_file():
            return Result(
                status=Status.SUCCESS,
                message="Ich habe gerade keine Neuigkeiten-Liste zur Hand, Sir.",
            )
        try:
            body = _latest_blocks(_changelog_path.read_text(encoding="utf-8"))
        except OSError:
            return Result(status=Status.SUCCESS,
                          message="Ich habe gerade keine Neuigkeiten-Liste zur Hand, Sir.")
        if not body:
            return Result(status=Status.SUCCESS,
                          message="Nichts Neues zu berichten, Sir — ich bin auf dem Stand.")
        return Result(
            status=Status.SUCCESS,
            message=f"Das habe ich zuletzt gelernt, Sir:\n\n{body}",
            data={"compose_context": (
                "Trage die folgenden Neuerungen als kurzes, warmes Update vor "
                "(die 3-4 wichtigsten zuerst, nicht alles aufzaehlen):\n" + body)},
        )


COMMANDS = [ShowHelpCommand(), WhatsNewCommand()]
