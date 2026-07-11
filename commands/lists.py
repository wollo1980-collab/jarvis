"""
Commands fuer benannte Listen (PO-Reibung 2026-07-10 "Einkaufsliste
erzaehlen" + "Loeschen ist umstaendlich"). Datenlayer: memory/lists.py.

Sicherheitsstufe 0/1 (eigener Datenlayer wie Eintraege) - KEINE
Bestaetigungen; clear_list setzt stattdessen auf Undo (Papierkorb +
restore_list): sprachtauglich, nichts geht endgueltig verloren.

Namens-Aufloesung fail-soft: nennt der Nutzer keine Liste, nimmt der
Command die einzige existierende; bei mehreren fragt er nach (nie raten).
configure() wie commands/entries.py.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from core.models import Plan, Result, Status
from core.phrases import pick
from memory.lists import ListStore, display_name

# Antwort-Varianten (Natuerlichkeits-Pass 2026-07-11, Muster
# commands/entries.py): Fakten bleiben exakt, nur der Rahmen atmet.
# Tests pruefen gegen die Pools, nicht gegen Festsaetze.
_ADD_PREFIXES = ("Notiert, Sir", "Steht drauf, Sir", "Erledigt, Sir")
_REMOVE_PREFIXES = ("🗑 Gestrichen, Sir", "🗑 Ist runter, Sir", "🗑 Weg damit, Sir")
_CLEAR_PREFIXES = ("✓ Geleert, Sir", "✓ Alles abgehakt, Sir", "✓ Tabula rasa, Sir")

_store: Optional[ListStore] = None

_MAX_SHOWN = 30
# Aufzaehlungs-Splitter fuer den Rueckfall (Posten aus der Doppelpunkt-
# Nutzlast): Kommas und alleinstehendes "und".
_ITEM_SPLIT = re.compile(r"\s*,\s*|\s+und\s+", re.IGNORECASE)


def configure(memory_dir: Path) -> ListStore:
    """Von main.py/jarvis_runtime.py einmal beim Start aufgerufen; Tests
    rufen dies mit tmp_path auf."""
    global _store
    _store = ListStore(memory_dir)
    return _store


def _require_store() -> ListStore:
    if _store is None:
        raise RuntimeError(
            "Listen nicht konfiguriert - commands.lists.configure() "
            "muss beim Start aufgerufen werden (siehe main.py)."
        )
    return _store


def _named_or_single(plan: Plan) -> tuple[str, list[tuple[str, int]]]:
    """DIE eine Kern-Aufloesung fuer alle Listen-Commands (Audit-Befund E,
    11.07.2026): Name aus parameters.list/target, sonst die einzige
    existierende Liste. Liefert (name, uebersicht); name == "" heisst
    "nicht aufloesbar" - was DANN passiert (Rueckfrage, Default,
    Uebersicht) entscheidet bewusst jeder Command selbst."""
    name = str(plan.parameters.get("list") or plan.target or "").strip()
    if name:
        return name, []
    existing = _require_store().overview()
    if len(existing) == 1:
        return existing[0][0], existing
    return "", existing


def _resolve_name(plan: Plan) -> tuple[str, Optional[Result]]:
    """Aufloesung mit Rueckfrage-Rueckfall (Remove/Clear): Liefert
    (name, None) oder ("", Rueckfrage-Result) - nie raten."""
    name, existing = _named_or_single(plan)
    if name:
        return name, None
    if not existing:
        return "", Result(
            status=Status.NEEDS_CLARIFICATION,
            message="Du hast noch keine Liste, Sir - wie soll sie heissen? (z. B. Einkaufsliste)",
        )
    names = ", ".join(display_name(n) for n, _ in existing)
    return "", Result(
        status=Status.NEEDS_CLARIFICATION,
        message=f"Welche Liste meinst du, Sir? Du hast: {names}.",
    )


def _items_from_plan(plan: Plan) -> list[str]:
    """Posten aus parameters.items (Array oder String); Rueckfall: die
    Doppelpunkt-Nutzlast der Roheingabe, an Kommas/'und' getrennt (der
    Satz-Splitter laesst sie seit dem Doppelpunkt-Schutz unangetastet)."""
    raw_items = plan.parameters.get("items")
    if isinstance(raw_items, list):
        items = [str(i).strip() for i in raw_items if str(i).strip()]
        if items:
            return items
    if isinstance(raw_items, str) and raw_items.strip():
        return [i for i in _ITEM_SPLIT.split(raw_items) if i.strip()]
    raw = (plan.raw_input or "").strip()
    if ":" in raw:
        payload = raw.split(":", 1)[1].strip()
        return [i for i in _ITEM_SPLIT.split(payload) if i.strip()]
    return []


def _numbered(items: list[str]) -> str:
    """Nummerierte Anzeige - Grundlage fuer 'streich Nummer 2' (C-Scheibe)."""
    return "\n".join(f"{i}. {item}" for i, item in enumerate(items, start=1))


class AddToListCommand:
    name = "add_to_list"
    description = (
        "Setzt einen oder mehrere Posten auf eine benannte Liste (z. B. "
        "'setz Milch und Butter auf die Einkaufsliste', 'Einkaufsliste: "
        "Milch, Butter, drei Zwiebeln'). parameters.list = Listen-Name, "
        "parameters.items = die einzelnen Posten. Fuer Sammlungen - einmalige "
        "Aufgaben/Termine sind add_entry, dauerhafte Fakten remember_fact."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        items = _items_from_plan(plan)
        if not items:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Was darf ich auf die Liste setzen, Sir?",
            )
        name, _ = _named_or_single(plan)
        if not name:
            # Ohne aufloesbaren Namen: Einkaufsliste als naheliegendster
            # Default fuers Anlegen (nie Rueckfrage beim Hinzufuegen).
            name = "einkaufsliste"

        added, skipped = _require_store().add(name, items)
        total = len(_require_store().get(name) or [])
        parts = []
        if added:
            parts.append(f"{', '.join(added)} — steht auf der {display_name(name)}")
        if skipped:
            parts.append(f"{', '.join(skipped)} stand schon drauf")
        return Result(
            status=Status.SUCCESS,
            message=f"{pick(*_ADD_PREFIXES)}: {'; '.join(parts)}. ({total} Posten gesamt)",
            data={"list": name, "added": added, "skipped": skipped, "total": total},
        )


class ShowListCommand:
    name = "show_list"
    description = (
        "Zeigt eine benannte Liste nummeriert (z. B. 'was steht auf der "
        "Einkaufsliste?', 'zeig die Packliste') oder ohne Namen die "
        "Uebersicht aller Listen. parameters.list = Listen-Name (optional)."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        name, existing = _named_or_single(plan)
        store = _require_store()
        if not name:
            if not existing:
                return Result(status=Status.SUCCESS, message="Du hast noch keine Listen, Sir.")
            lines = "\n".join(
                f"- {display_name(n)} ({count} Posten)" for n, count in existing
            )
            return Result(
                status=Status.SUCCESS,
                message=f"Deine Listen, Sir:\n{lines}",
                data={"lists": [n for n, _ in existing]},
            )

        items = store.get(name)
        if items is None:
            return Result(
                status=Status.FAILED,
                message=f"Eine Liste namens {display_name(name)} habe ich nicht, Sir.",
            )
        shown = items[:_MAX_SHOWN]
        more = f"\n… und {len(items) - len(shown)} weitere." if len(items) > len(shown) else ""
        return Result(
            status=Status.SUCCESS,
            message=f"{display_name(name)} ({len(items)} Posten):\n{_numbered(shown)}{more}",
            data={"list": name, "count": len(items)},
        )


class RemoveFromListCommand:
    name = "remove_from_list"
    description = (
        "Streicht EINEN Posten von einer Liste (z. B. 'streich die Milch von "
        "der Einkaufsliste', 'nimm Nummer 2 von der Liste'). parameters.item "
        "= der Posten-Text ODER parameters.index = die Nummer aus der "
        "Anzeige; parameters.list = Listen-Name (optional bei eindeutigem "
        "Posten)."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        item = str(plan.parameters.get("item") or "").strip()
        try:
            index = int(plan.parameters.get("index") or 0)
        except (TypeError, ValueError):
            index = 0
        if not item and not index:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Welchen Posten darf ich streichen, Sir?",
            )
        name = str(plan.parameters.get("list") or plan.target or "").strip()
        if index and not name:
            # Eine Nummer ohne Liste ist nur bei genau einer Liste eindeutig.
            resolved, clarification = _resolve_name(plan)
            if clarification is not None:
                return clarification
            name = resolved

        removed = _require_store().remove(name or None, item=item, index=index)
        if removed is None:
            what = f"Nummer {index}" if index else f"«{item}»"
            return Result(
                status=Status.FAILED,
                message=(
                    f"Dazu habe ich keinen eindeutigen Posten gefunden ({what}), Sir - "
                    "nenn mir ggf. die Liste dazu."
                ),
            )
        list_name, text = removed
        return Result(
            status=Status.SUCCESS,
            message=f"{pick(*_REMOVE_PREFIXES)}: «{text}» ({display_name(list_name)}).",
            data={"list": list_name, "removed": text},
        )


class ClearListCommand:
    name = "clear_list"
    description = (
        "Leert eine benannte Liste komplett (z. B. 'leere die Einkaufsliste' "
        "- nach dem Einkauf). Kein Datenverlust: der Stand wandert in den "
        "Papierkorb, 'stell die Liste wieder her' holt ihn zurueck. "
        "parameters.list = Listen-Name."
    )
    requires_confirmation = False  # Undo statt Rueckfrage (Papierkorb + restore_list)

    def execute(self, plan: Plan) -> Result:
        name, clarification = _resolve_name(plan)
        if clarification is not None:
            return clarification
        items = _require_store().clear(name)
        if items is None:
            return Result(
                status=Status.FAILED,
                message=f"Eine Liste namens {display_name(name)} habe ich nicht, Sir.",
            )
        return Result(
            status=Status.SUCCESS,
            message=(
                f"{pick(*_CLEAR_PREFIXES)} — {display_name(name)}, {len(items)} Posten. "
                "Falls das ein Versehen war: «stell die Liste wieder her»."
            ),
            data={"list": name, "cleared": len(items)},
        )


class RestoreListCommand:
    name = "restore_list"
    description = (
        "Holt eine geleerte Liste aus dem Papierkorb zurueck ('stell die "
        "Liste wieder her', 'die Einkaufsliste war ein Versehen'). "
        "parameters.list = Listen-Name (optional)."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        name = str(plan.parameters.get("list") or plan.target or "").strip()
        restored = _require_store().restore(name)
        if restored is None:
            return Result(
                status=Status.FAILED,
                message="Im Papierkorb liegt dazu nichts, Sir - da gibt es nichts wiederherzustellen.",
            )
        list_name, items = restored
        return Result(
            status=Status.SUCCESS,
            message=f"✓ Wiederhergestellt, Sir: {display_name(list_name)} ({len(items)} Posten).",
            data={"list": list_name, "count": len(items)},
        )


# Registrierungspunkt - commands/__init__.py liest diese Liste beim Start ein.
COMMANDS = [
    AddToListCommand(),
    ShowListCommand(),
    RemoveFromListCommand(),
    ClearListCommand(),
    RestoreListCommand(),
]
