"""
Namens-Wunsch -> Anzeigename (ADR-057).

"nenn mich X" / "ich heiße X" setzt `config.owner_name`. Beide Stellen, die
den Namen anzeigen, folgen dann automatisch:

- Chat: der Runtime-Prozess reicht DASSELBE Config-Objekt an die AIEngine wie
  an diesen Command - eine In-Memory-Aenderung greift ab der naechsten Antwort.
- Dashboard: laeuft als EIGENER Prozess und liest owner_name frisch aus
  config.json (dashboard.py::_live_owner_name) - deshalb wird der Wert auch
  auf Platte geschrieben (persist_config_value), nicht nur im Speicher.

Damit gibt es EINE Quelle (owner_name); die Drift zwischen Chat-Anrede und
Dashboard-Begruessung (Live-Befund 11.07.2026) kann nicht mehr entstehen.
Vorher: "nenn mich X" landete nur als loser Fakt, den das Dashboard nie sah.

Die Command-Registry instanziiert Commands beim Import, VOR Config.load() -
deshalb wird das Config-Objekt (und das Langzeitgedaechtnis) per configure()
zur Laufzeit injiziert, genau wie bei commands/memory.py.
"""
from __future__ import annotations

import re
from typing import Optional

from core.config import Config, persist_config_value
from core.models import Plan, Result, Status
from memory.long_term import LongTermMemory

_config: Optional[Config] = None
_long_term: Optional[LongTermMemory] = None

# Alte Namens-FAKTEN aus dem Langzeitgedaechtnis raeumen, wenn der Name neu
# gesetzt wird: der Chat-Prompt liest owner_name UND die Fakten-Zusammenfassung
# (core/ai.py). Bliebe ein frueheres "ich heiße Bob" als Fakt stehen, saehe der
# Chat zwei Namen. Nur klare Selbst-Benennungen greifen hier - ein Fakt wie
# "Max ist mein Sohn" enthaelt kein Benennungs-Verb und bleibt unberuehrt.
_NAMING_FACT_RE = re.compile(
    r"(nenn\w*\s+mich|mich\s+\S+\s+nenn\w*|ich\s+hei(?:ß|ss)e"
    r"|mein\s+name\s+ist|sag\s+\S+\s+zu\s+mir)",
    re.IGNORECASE,
)


def configure(config: Config, long_term: LongTermMemory) -> None:
    """Von main.py und jarvis_runtime.py beim Start aufgerufen - MUSS dasselbe
    Config-Objekt uebergeben, das auch die AIEngine nutzt (sonst folgt der Chat
    nicht live). Tests rufen es mit einer eigenen Config + tmp-Gedaechtnis auf."""
    global _config, _long_term
    _config = config
    _long_term = long_term


def _require_config() -> Config:
    if _config is None:
        raise RuntimeError(
            "Anzeigename nicht konfiguriert - commands.owner.configure() muss "
            "beim Start aufgerufen werden (siehe main.py / jarvis_runtime.py)."
        )
    return _config


class SetOwnerNameCommand:
    name = "set_owner_name"
    description = (
        "Aendert, wie Jarvis den Nutzer anspricht und ihn im Dashboard begruesst "
        "- NUR bei ausdruecklicher Selbst-Benennung ('nenn mich Max', "
        "'ich heiße Max', 'sag Max zu mir', 'mein Name ist Max'). "
        "NICHT fuer Fakten ueber andere Personen (z. B. 'Max ist mein Sohn' "
        "-> das ist ein Fakt fuers Gedaechtnis, kein Anrede-Wunsch)."
    )
    # Unkritisch (Sicherheitsstufe 1): schreibt nur den eigenen Anzeigenamen,
    # lokal und umkehrbar (einfach neu benennen). Keine Bestaetigung noetig.
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        name = (plan.target or "").strip().strip(".,!?;:").strip()
        if not name:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Wie darf ich Sie ab jetzt nennen?",
            )

        config = _require_config()
        config.owner_name = name  # live: der Chat folgt ab der naechsten Antwort
        # auf Platte, damit der eigenstaendige Dashboard-Prozess es frisch liest
        # und der Name einen Neustart ueberlebt.
        persist_config_value("owner_name", name)

        # Drift-Schutz: etwaige alte Benennungs-Fakten entwerten, damit der
        # Chat-Prompt nicht owner_name UND einen widersprechenden Fakt sieht.
        if _long_term is not None:
            for fact in _long_term.all_facts():
                if _NAMING_FACT_RE.search(fact.text):
                    _long_term.forget(fact.text, exact=True)

        return Result(
            status=Status.SUCCESS,
            message=f"Sehr wohl — ab sofort {name}, auch oben im Dashboard.",
        )


# Registrierungspunkt - commands/__init__.py liest diese Liste beim Start ein.
COMMANDS = [SetOwnerNameCommand()]
