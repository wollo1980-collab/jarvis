"""
Rollierende Sitzungs-Zusammenfassung (ADR-065 Saeule B1).

Der Kern sieht pro Runde nur das juengste Verlaufsfenster (z. B. 20 Nachrichten).
In langen Gespraechen reisst damit der Faden zu allem, was frueher gesagt wurde.
B1 haelt eine KNAPPE, rollierende Zusammenfassung der aelteren Nachrichten (die
aus dem juengsten Fenster herausfallen) und faltet neue Ueberlaeufe in Bloecken
ein - so bleibt der Kontext erhalten, ohne den ganzen Verlauf jedes Mal neu zu
zusammenzufassen.

NEBENLAEUFIG seit 13.07.2026 (Latenz-Messung: das Einfalten blockierte den
Antwortpfad um 8,3 s - groesster Einzelposten der 16,5-s-Wetterantwort):
`maybe_update_async` faltet im Hintergrund-Thread, die laufende Antwort nutzt
den Stand der VORRUNDE. Das ist verlustfrei: zusammengefasst wird ohnehin nur
der AELTERE Verlauf - ob er eine Runde spaeter einfliesst, aendert am Inhalt
nichts. Ein Lock schuetzt den Zustand, eine Ein-Falter-Garde verhindert
gestapelte LLM-Calls; `_folded` haelt das Ganze idempotent.

Rein und testbar: die eigentliche LLM-Zusammenfassung wird als
`summarize_fn(prev_summary, messages) -> str` INJIZIERT (wie tool_caller bei
reasoning.decide) - kein Netz im Test. Fail-safe beim Aufrufer.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from core.models import Message

logger = logging.getLogger("jarvis.memory.session_summary")

# summarize_fn(bisherige_zusammenfassung, neue_aeltere_nachrichten) -> neue Zusammenfassung
SummarizeFn = Callable[[str, "list[Message]"], str]


class SessionSummary:
    """Haelt die Zusammenfassung der Nachrichten, die aelter sind als das juengste
    Fenster (`recent_window`), und faltet neue Ueberlaeufe ab `chunk` Stueck ein."""

    def __init__(self, recent_window: int = 20, chunk: int = 8):
        self._summary = ""
        self._folded = 0          # wie viele der aeltesten Nachrichten schon eingefaltet sind
        self.recent_window = recent_window
        self.chunk = chunk
        self._lock = threading.RLock()
        self._folding = False     # genau EIN Einfalt-Lauf zur Zeit (kein LLM-Stapel)

    def summary(self) -> str:
        with self._lock:
            return self._summary

    def maybe_update(self, full_history: "list[Message]", summarize_fn: SummarizeFn) -> None:
        """Faltet Nachrichten, die aus dem juengsten Fenster herausgefallen sind,
        in die Zusammenfassung ein - aber erst, wenn mindestens `chunk` neue
        anstehen (nicht jede Runde ein LLM-Call). Idempotent ueber `_folded`.
        Der LLM-Call laeuft OHNE Lock; laeuft bereits ein Einfalten, kehrt der
        Aufruf sofort zurueck (der naechste holt den Rueckstand auf)."""
        with self._lock:
            if self._folding:
                return
            n = len(full_history)
            if self._folded > n:                 # Puffer geschrumpft (Eviction) -> Sicherheits-Reset
                self._folded = 0
                self._summary = ""
            target = max(0, n - self.recent_window)  # alles davor SOLL zusammengefasst sein
            if target - self._folded < self.chunk:
                return                           # noch nicht genug Neues zum Einfalten
            to_fold = full_history[self._folded:target]
            if not to_fold:
                return
            prev = self._summary
            self._folding = True
        try:
            new = (summarize_fn(prev, to_fold) or "").strip()
            with self._lock:
                if new:
                    self._summary = new
                    self._folded = target
        finally:
            with self._lock:
                self._folding = False

    def maybe_update_async(self, full_history: "list[Message]",
                           summarize_fn: SummarizeFn) -> Optional[threading.Thread]:
        """Wie maybe_update, aber im Hintergrund-Daemon-Thread - der Antwortpfad
        wartet nie auf den LLM-Call (Latenz-Befund 13.07.). Erwartet einen
        SNAPSHOT der History (Aufrufer uebergibt eine Kopie). Liefert den
        gestarteten Thread (fuer Tests/join) oder None bei Startfehler."""
        def _run() -> None:
            try:
                self.maybe_update(full_history, summarize_fn)
            except Exception:  # noqa: BLE001 - Hintergrund stoert den Betrieb nie
                logger.warning("Sitzungs-Zusammenfassung (Hintergrund) fehlgeschlagen.", exc_info=True)

        try:
            thread = threading.Thread(target=_run, name="jarvis-session-summary", daemon=True)
            thread.start()
            return thread
        except Exception:  # noqa: BLE001
            logger.warning("Sitzungs-Zusammenfassung: Thread-Start fehlgeschlagen.", exc_info=True)
            return None
