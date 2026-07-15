"""
Auftrags-Befehle (Phase B.1, Bauschritt B7) - Start/Status/Abbruch des
Auftrags-Loops ueber ALLE Kanaele (Bauvertrag v1.0 §9, ADR-074).

Der eigentliche Lauf gehoert dem TaskService (eigener Worker) - diese
Befehle sind nur die Kanal-Tuer: submit quittiert sofort (der Service
arbeitet im Hintergrund, Ergebnis kommt per Push/Outbox bzw. ist per
«wie steht der Auftrag?» jederzeit abfragbar). Kanalparitaet ehrlich
(Nachtrag 7): Konsole = Statusabfrage; Browser/Telegram bekommen
zusaetzlich die Pushs des Notifiers.

configure() injiziert einen GETTER (nicht den Service selbst), weil der
TaskService erst nach der Registry-Instanziierung entsteht - ohne
konfigurierten Portfolio-Root antworten die Befehle ehrlich, dass der
Auftrags-Loop nicht eingerichtet ist.
"""
from __future__ import annotations

from typing import Callable, Optional

from core.models import Plan, Result, Status
from core.redaction import redact

_service_getter: Optional[Callable[[], object]] = None
_portfolio_root: str = ""


def configure(service_getter: Callable[[], object], portfolio_root: str = "") -> None:
    global _service_getter, _portfolio_root
    _service_getter = service_getter
    _portfolio_root = portfolio_root or ""
    # Live-Reibung 15.07. («Analysiere C:KI» landete im Ereignisprotokoll):
    # der KONFIGURIERTE Pfad wandert woertlich in die Beschreibung - Router
    # und Kern bekommen damit das staerkste Wahl-Signal fuer genau die
    # Formulierung, die der Nutzer wirklich benutzt.
    if _portfolio_root:
        compact = _portfolio_root.replace("\\", "")
        PortfolioReviewCommand.description = PortfolioReviewCommand.BASE_DESCRIPTION + (
            f" AUCH bei Nennung des Projektordners: 'analysiere {_portfolio_root}', "
            f"'analysiere {compact}', 'was liegt in {_portfolio_root}?'."
        )


def _service():
    return _service_getter() if _service_getter is not None else None


_NOT_CONFIGURED = (
    "Der Auftrags-Loop ist noch nicht eingerichtet, Sir — dafür muss "
    "`task_portfolio_root` in der config.json gesetzt sein."
)


class PortfolioReviewCommand:
    name = "portfolio_review"
    BASE_DESCRIPTION = (
        "Startet den Portfolio-Review-Auftrag (z. B. 'analysiere mein Portfolio', "
        "'analysiere alle meine Projekte', 'analysiere meinen Projektordner', "
        "'portfolio-review') - Jarvis prueft alle aktiven Projekte im "
        "konfigurierten Projektordner read-only und meldet Stand, Blocker, "
        "naechste Schritte und EINE Prioritaet. NICHT fuer die Analyse EINES "
        "Repos (delegate_analysis), NICHT fuer PC-/Ereignisprotokoll-Analysen "
        "(analyze_pc/analyze_event_log)."
    )
    description = BASE_DESCRIPTION
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        service = _service()
        # Der Service existiert seit H3 immer (Legacy-Adapter) - der
        # Portfolio-AUFTRAG braucht zusaetzlich den konfigurierten Root.
        if service is None or not _portfolio_root:
            return Result(status=Status.FAILED, message=_NOT_CONFIGURED)
        from core.portfolio import default_portfolio_dod
        from core.task_models import Task
        from core.task_service import TaskSubmitError

        task = Task(
            title="Portfolio-Review",
            goal=(f"Analysiere alle aktiven Projekte direkt unter {_portfolio_root}. "
                  "Beruecksichtige die Ziele aus PERSONAL_DEVELOPMENT.md. Nenne pro "
                  "Projekt den tatsaechlichen Stand, Blocker, den sinnvollsten "
                  "naechsten Schritt und den Zielbezug; entscheide dann, woran als "
                  "Naechstes gearbeitet werden sollte."),
            original_request=redact(plan.raw_input or ""),
            definition_of_done=default_portfolio_dod(),
            allowed_actions=["collect_portfolio_evidence"],
            source=str(plan.parameters.get("source", "") or ""),
        )
        try:
            submitted = service.submit(task)
        except TaskSubmitError as err:
            return Result(status=Status.FAILED,
                          message=f"Auftrag nicht gestartet, Sir: {err.message}")
        return Result(
            status=Status.SUCCESS,
            message=(f"Auftrag {submitted.task_id[:8]} «Portfolio-Review» läuft, Sir — "
                     f"max. {submitted.budget.max_rounds} Runden, read-only. "
                     f"Frag jederzeit «wie steht der Auftrag?» oder sag "
                     f"«brich den Auftrag ab»."),
            data={"task_id": submitted.task_id},
        )


class TaskStatusCommand:
    name = "task_status"
    description = (
        "Zeigt den Stand des laufenden Auftrags (z. B. 'wie steht der Auftrag?', "
        "'auftragsstatus', 'was macht dein Auftrag?'). NICHT fuer den "
        "Systemstatus (das ist system_status)."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        service = _service()
        if service is None:
            return Result(status=Status.FAILED, message=_NOT_CONFIGURED)
        return Result(status=Status.SUCCESS, message=str(service.status_line()))


class TaskResumeCommand:
    name = "task_resume"
    description = (
        "Setzt einen blockierten Auftrag fort (z. B. 'setz den Auftrag fort', "
        "'mach mit dem Auftrag weiter' - optional mit Antwort auf die "
        "Rueckfrage: 'setz den Auftrag fort: nimm Root C'). parameters.text = "
        "die Antwort, falls der Auftrag eine Frage gestellt hat."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        service = _service()
        if service is None:
            return Result(status=Status.FAILED, message=_NOT_CONFIGURED)
        answer = str(plan.parameters.get("text") or plan.target or "").strip()
        resumed = service.resume_task(answer)
        if resumed:
            return Result(status=Status.SUCCESS,
                          message=f"Auftrag {resumed[:8]} läuft weiter, Sir"
                                  + (" — deine Antwort ist drin." if answer else "."))
        return Result(status=Status.SUCCESS,
                      message="Es liegt kein blockierter Auftrag zum Fortsetzen vor, Sir. "
                              + str(service.status_line()))


class TaskCancelCommand:
    name = "task_cancel"
    description = (
        "Bricht den laufenden Auftrag ab (z. B. 'brich den Auftrag ab', "
        "'stopp den Auftrag'). NICHT fuer den Bau-Agenten (das ist stop_agent)."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        service = _service()
        if service is None:
            return Result(status=Status.FAILED, message=_NOT_CONFIGURED)
        running = service.cancel()
        if running:
            return Result(status=Status.SUCCESS,
                          message=f"Verstanden, Sir — ich breche Auftrag {running[:8]} ab.")
        return Result(status=Status.SUCCESS,
                      message="Es läuft gerade kein Auftrag, Sir — nichts abzubrechen.")


COMMANDS = [PortfolioReviewCommand(), TaskStatusCommand(), TaskResumeCommand(),
            TaskCancelCommand()]
