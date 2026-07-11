"""
Wochen-Rueckblick (Angestellten-Vision, Idee 3 der Nacht-Session
11.07.2026) - "Was haben wir diese Woche geschafft?" traegt vor, was
WIRKLICH passiert ist: nutzerseitige Verbesserungen aus dem CHANGELOG
(Datums-Kopfzeilen der letzten 7 Tage) und die Agenten-Laeufe aus den
Runtime-Logs (delegation_stats, dieselbe Quelle wie das Dashboard).

Bewusst DETERMINISTISCH (kein LLM): ein Rueckblick ist Rechenschaft,
keine Interpretation - jede Zeile ist woertlich belegbar. Stufe 0,
read-only.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.models import Plan, Result, Status

logger = logging.getLogger("jarvis.commands.review")

_changelog_path: Optional[Path] = None
_log_dir: Optional[Path] = None

_HEADER_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2}) - (.+)$", re.MULTILINE)
_MAX_SHOWN = 10


def configure(changelog_path, log_dir) -> None:
    """Von main.py/jarvis_runtime.py beim Start verdrahtet."""
    global _changelog_path, _log_dir
    _changelog_path = Path(changelog_path) if changelog_path else None
    _log_dir = Path(log_dir) if log_dir else None


def _changelog_this_week(today: Optional[date] = None) -> list[str]:
    """Titel der CHANGELOG-Eintraege der letzten 7 Tage (fail-safe leer)."""
    if _changelog_path is None:
        return []
    try:
        content = _changelog_path.read_text(encoding="utf-8")
    except OSError:
        return []
    cutoff = (today or date.today()) - timedelta(days=7)
    titles = []
    for match in _HEADER_RE.finditer(content):
        try:
            entry_date = date.fromisoformat(match.group(1))
        except ValueError:
            continue
        if entry_date >= cutoff:
            titles.append(f"{entry_date.strftime('%d.%m.')} — {match.group(2).strip()}")
    return titles


class WeeklyReviewCommand:
    name = "weekly_review"
    description = (
        "Traegt den Wochen-Rueckblick vor: was in den letzten 7 Tagen an "
        "Jarvis verbessert wurde (aus dem CHANGELOG) und wie viele "
        "Agenten-Laeufe es gab (z. B. 'was haben wir diese Woche "
        "geschafft?', 'Wochenrueckblick'). Read-only, Stufe 0, "
        "deterministisch - jede Zeile belegbar."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        titles = _changelog_this_week()
        parts = []
        if titles:
            shown = titles[:_MAX_SHOWN]
            lines = "\n".join(f"{i}. {t}" for i, t in enumerate(shown, start=1))
            more = f"\n… und {len(titles) - len(shown)} weitere." if len(titles) > len(shown) else ""
            parts.append(
                f"Diese Woche wurden {len(titles)} Verbesserungen geliefert:\n{lines}{more}"
            )
        if _log_dir is not None:
            try:
                from core.dashboard_data import delegation_stats

                stats = delegation_stats(_log_dir)
                if stats["runs"]:
                    parts.append(
                        f"Agenten-Arbeit: {stats['ok']} von {stats['runs']} Läufen erfolgreich, "
                        f"Gegenwert gesamt {stats['total_cost_usd']:.2f} USD (Abo, Grenzkosten 0)."
                    )
            except Exception:  # noqa: BLE001 - Rueckblick kommt auch ohne Statistik
                logger.exception("Wochen-Rueckblick: Delegations-Statistik nicht lesbar.")
        if not parts:
            return Result(
                status=Status.SUCCESS,
                message="Diese Woche steht nichts im Buch, Sir — ein stiller Anfang.",
            )
        return Result(
            status=Status.SUCCESS,
            message="Der Wochen-Rückblick, Sir:\n" + "\n\n".join(parts),
            data={"changelog_entries": len(titles)},
        )


# Registrierungspunkt - commands/__init__.py liest diese Liste beim Start ein.
COMMANDS = [WeeklyReviewCommand()]
