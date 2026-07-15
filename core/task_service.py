"""
TaskService - genau eine Queue, genau ein Worker, genau ein aktiver Auftrag
(Phase B.1, Bauschritt B4; Bauvertrag v1.0 §9, ADR-074 Kernentscheidung 1).

Der Service ist ein EIGENER Dienst: die Runtime erzeugt und injiziert ihn,
uebersetzt seine Ereignisse in Kanalnachrichten und enthaelt selbst KEINE
Auftragszustandsmaschine. Er teilt sich die ExecutionLease mit der
Legacy-Delegation (Nachtrag 4) - nie zwei externe Ausfuehrungspfade.

Ergebnis-Zustellung (Nachtrag 7): terminale Ergebnisse wandern in eine
persistente Notification-Outbox (Task-ID+Status als Idempotenzschluessel,
Zustellgarantie 'mindestens einmal, deduplizierbar'); das Ergebnis selbst
bleibt unabhaengig davon im Store abfragbar.
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Callable, Optional

from core.execution_lease import ExecutionLease
from core.fileio import read_json, write_json_atomic
from core.task_models import Observation, Task, TaskStatus, TrustClass, utc_now_iso
from core.task_policy import PolicyViolation, freeze_contract
from core.task_runner import TaskRunner
from memory.task_store import StoreConflict, TaskStore

logger = logging.getLogger("jarvis.task_service")

_LEASE_OWNER = "task_service"
# Deckel fuer die Ergebnis-Zusammenfassung im Push (Kuerzung nur an
# Zeilengrenze; die Kanaele splitten lange Nachrichten selbst).
_OUTBOX_SUMMARY_CAP = 2000


class TaskSubmitError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class TaskService:
    def __init__(self, store: TaskStore, runner: TaskRunner, lease: ExecutionLease,
                 listener: Optional[Callable[[str, Task], None]] = None):
        self.store = store
        self.runner = runner
        self.lease = lease
        self._listener = listener or (lambda kind, task: None)
        self._queue: "queue.Queue" = queue.Queue()
        self._cancel = threading.Event()
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._running_task_id: Optional[str] = None
        self._pending = 0
        self._legacy_cancel: Optional[threading.Event] = None
        self._lock = threading.Lock()
        runner._emit = self._emit  # Runner-Ereignisse laufen ueber den Service

    # --- Lebenszyklus -----------------------------------------------------------

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(target=self._run_worker,
                                        name="jarvis-task-service", daemon=True)
        self._worker.start()

    def stop(self, join_seconds: float = 10.0) -> None:
        """Begrenzter Join (Vertrag §9) - der Worker haengt nie unendlich."""
        self._stop.set()
        self._cancel.set()
        legacy = self._legacy_cancel
        if legacy is not None:
            legacy.set()               # Kill-Switch des Legacy-Laufs (Adapter)
        self._queue.put(None)
        if self._worker is not None:
            self._worker.join(timeout=join_seconds)

    @property
    def is_busy(self) -> bool:
        """Laeuft oder wartet irgendein Ausfuehrungs-Job (Task ODER Legacy)?"""
        with self._lock:
            return bool(self.lease.busy or self._running_task_id is not None or self._pending)

    def _enqueue(self, item) -> None:
        # Selbstheilend (H3): der Service besitzt seine Ausfuehrung - wer
        # einreiht, bekommt einen laufenden Worker (start() ist idempotent).
        self.start()
        with self._lock:
            self._pending += 1
        self._queue.put(item)

    # --- API ----------------------------------------------------------------------

    def submit(self, task: Task) -> Task:
        """Friert den Vertrag ein (DRAFT -> READY), persistiert und reiht ein.
        Genau EIN aktiver Auftrag: laeuft schon einer, wird NICHT unsichtbar
        eingereiht, sondern klar abgelehnt (Vertrag §9)."""
        try:
            active = self.store.active_task_id()
        except StoreConflict as err:
            raise TaskSubmitError(err.code, f"Auftrags-Speicher meldet: {err.detail}") from err
        if active:
            raise TaskSubmitError("ACTIVE_TASK_CONFLICT", self.status_line())
        try:
            freeze_contract(task, self.runner.registry)
        except PolicyViolation as err:
            raise TaskSubmitError(err.code, err.detail) from err
        self.store.create(task)                       # Revision 1, DRAFT
        task.status = TaskStatus.READY
        self.store.commit(task, "contract_frozen", task.revision, actor="service")
        self._cancel.clear()
        self._enqueue(task.task_id)
        self._emit("task_accepted", task)
        return task

    def submit_legacy(self, label: str, fn: Callable[[threading.Event], None]) -> bool:
        """Kompatibilitaetsadapter (Vertrag §9-Migration): fuehrt einen
        Legacy-long_running-Lauf (Delegation/Bau) im TaskService-Worker aus -
        EIN Worker, EINE Lease, keine eigene Thread-Schicht mehr. False =
        es laeuft bereits etwas (der Aufrufer lehnt hoeflich ab, nie
        unsichtbar einreihen). `fn` bekommt ein frisches Cancel-Event."""
        if self.is_busy:
            return False
        self._enqueue(("legacy", label, fn))
        return True

    def cancel(self) -> Optional[str]:
        """Not-Stopp: bricht den laufenden Auftrag ab - und (Hardening 15.07.,
        Sol-Analyse Punkt 1) auch einen LIEGENGEBLIEBENEN nichtterminalen
        Auftrag (BLOCKED/READY/...), den kein Worker mehr haelt. Vorher
        blockierte so ein Auftrag jeden neuen Submit dauerhaft."""
        with self._lock:
            running = self._running_task_id
        self._cancel.set()
        if running:
            return running
        try:
            active = self.store.active_task_id()
        except StoreConflict:
            return None
        if not active:
            return None
        try:
            task = self.store.load(active)
            if not task.is_terminal:
                task.status = TaskStatus.CANCELLED
                self.store.commit(task, "cancelled", task.revision, actor="service")
                self._emit("cancelled", task)
                return active
        except StoreConflict:
            logger.warning("TaskService: liegengebliebener Auftrag %s nicht abbrechbar.", active[:8])
        return None

    def resume_task(self, answer: str = "") -> Optional[str]:
        """Setzt einen BLOCKED-Auftrag fort (Hardening 15.07.: Fortsetzung/
        Rueckfrage, Vertrag §9-Kanalparitaet). Eine mitgegebene Antwort wird
        als USER-Observation journalisiert und erreicht den Entscheider als
        klar markierte, gedeckelte Nutzer-Antwort (nie als Kontrollfakt)."""
        try:
            active = self.store.active_task_id()
        except StoreConflict:
            return None
        if not active:
            return None
        task = self.store.load(active)
        if task.status is not TaskStatus.BLOCKED:
            return None
        if answer.strip():
            question = task.blocker.detail if task.blocker else ""
            self.store.record_observation(Observation(
                task_id=task.task_id, action_id="", source="user_input",
                trust=TrustClass.USER, status="answer",
                control_facts={"question": question[:300], "answer": answer.strip()[:300]},
            ))
        task.status = TaskStatus.RUNNING
        task.blocker = None
        self.store.commit(task, "resumed", task.revision, actor="service")
        self._cancel.clear()
        self._queue.put(task.task_id)
        self._emit("task_accepted", task)
        return active

    def status_line(self) -> str:
        """Menschlicher Status - jederzeit abfragbar: der aktive Auftrag,
        sonst der ZULETZT beendete samt Ergebnis (Hardening 15.07. Punkt 2)."""
        try:
            active = self.store.active_task_id()
        except StoreConflict as err:
            return f"Auftrags-Speicher inkonsistent ({err.code}) — keine Ausführung."
        if not active:
            last = self.store.last_terminal_task()
            if last is None:
                return "Kein aktiver Auftrag."
            line = (f"Kein aktiver Auftrag. Zuletzt: {last.task_id[:8]} «{last.title}» "
                    f"— {last.status.value} ({last.completed_at or last.updated_at})")
            if last.outcome and last.outcome.summary:
                line += f"\n{last.outcome.summary[:600]}"
            return line
        task = self.store.load(active)
        line = (f"Auftrag {task.task_id[:8]} «{task.title}»: {task.status.value}, "
                f"Runde {task.usage.rounds}/{task.budget.max_rounds}")
        if task.blocker:
            line += f" — Blocker: {task.blocker.code} ({task.blocker.detail})"
            if task.blocker.code == "INPUT_REQUIRED":
                line += " — antworte mit «setz den Auftrag fort: <Antwort>»"
        return line

    def resume_on_start(self) -> None:
        """Wiederanlauf beim Runtime-Start (Vertrag §7/§9): nichtterminale
        Auftraege pruefen und Lauffaehiges wieder einreihen."""
        try:
            active = self.store.active_task_id()
        except StoreConflict as err:
            logger.warning("TaskService-Wiederanlauf: %s - keine Ausfuehrung.", err)
            return
        if not active:
            return
        try:
            task = self.runner.resume(active)
        except StoreConflict as err:
            logger.warning("TaskService-Wiederanlauf: %s - keine Ausfuehrung.", err)
            return
        if task is not None:
            logger.info("TaskService: setze Auftrag %s nach Neustart fort.", task.task_id[:8])
            self._queue.put(task.task_id)

    # --- Worker ---------------------------------------------------------------------

    def _run_worker(self) -> None:
        while not self._stop.is_set():
            item = self._queue.get()
            if item is None:
                continue
            with self._lock:
                self._pending = max(0, self._pending - 1)
            is_legacy = isinstance(item, tuple)
            # Lease teilen (Nachtrag 4): nie zwei externe Ausfuehrungspfade.
            while not self.lease.acquire(_LEASE_OWNER):
                if self._stop.wait(0.05):
                    return
                if self._cancel.is_set() and not is_legacy:
                    self._cancel_queued(item)
                    item = None
                    break
            if item is None:
                continue
            try:
                if is_legacy:
                    self._run_legacy(item[1], item[2])
                else:
                    with self._lock:
                        self._running_task_id = item
                    self.runner.run(item, self._cancel)
            except StoreConflict as err:
                logger.warning("TaskService: Store-Konflikt: %s", err)
            except Exception:  # noqa: BLE001 - der Worker stirbt nie still
                logger.exception("TaskService: unerwarteter Fehler im Worker-Job.")
            finally:
                with self._lock:
                    self._running_task_id = None
                self.lease.release(_LEASE_OWNER)

    def _run_legacy(self, label: str, fn: Callable[[threading.Event], None]) -> None:
        """Ein Legacy-Lauf (Adapter): frisches Cancel-Event, das stop() und
        der Kill-Switch des Aufrufers setzen koennen."""
        cancel = threading.Event()
        self._legacy_cancel = cancel
        logger.info("TaskService: Legacy-Lauf %r startet (Adapter §9).", label)
        try:
            fn(cancel)
        finally:
            self._legacy_cancel = None

    def _cancel_queued(self, task_id: str) -> None:
        try:
            task = self.store.load(task_id)
            if not task.is_terminal:
                task.status = TaskStatus.CANCELLED
                self.store.commit(task, "cancelled", task.revision, actor="service")
                self._emit("cancelled", task)
        except StoreConflict:
            logger.warning("TaskService: eingereihter Auftrag %s nicht abbrechbar.", task_id[:8])

    # --- Ereignisse + Outbox -----------------------------------------------------------

    def _emit(self, kind: str, task: Task) -> None:
        if task.is_terminal or task.status is TaskStatus.BLOCKED:
            self._outbox_add(kind, task)
        try:
            self._listener(kind, task)
        except Exception:  # noqa: BLE001 - ein Kanalfehler stoert den Lauf nie
            logger.warning("TaskService: Ereignis-Listener warf (%s).", kind, exc_info=True)

    def _outbox_path(self):
        return self.store.root / "outbox.json"

    def _outbox_add(self, kind: str, task: Task) -> None:
        """Persistente Outbox (Nachtrag 7): Idempotenzschluessel task_id+status -
        'mindestens einmal, deduplizierbar'."""
        entries = read_json(self._outbox_path(), [])
        key = f"{task.task_id}:{task.status.value}"
        if any(e.get("key") == key for e in entries):
            return
        blocker = f" — {task.blocker.code}: {task.blocker.detail}" if task.blocker else ""
        summary = (task.outcome.summary if task.outcome and task.is_terminal else "")
        # Ergebnis-Push NICHT verstuemmeln (Live-Reibung 15.07.: 600 Zeichen
        # rissen den 9-Projekte-Bericht mitten im Wort ab): grosszuegiger
        # Deckel, Kuerzung nur an ZEILEN-Grenze - die Kanaele zerlegen lange
        # Nachrichten ohnehin selbst in sichere Teile.
        if summary and len(summary) > _OUTBOX_SUMMARY_CAP:
            cut = summary[:_OUTBOX_SUMMARY_CAP]
            line_end = cut.rfind("\n")
            summary = (cut[:line_end] if line_end > 0 else cut) + "\n…(gekürzt — «wie steht der Auftrag?» zeigt den Stand)"
        entries.append({
            "key": key, "task_id": task.task_id, "status": task.status.value,
            "kind": kind, "created_at": utc_now_iso(), "delivered_at": None,
            "message": (f"Auftrag {task.task_id[:8]} «{task.title}»: "
                        f"{task.status.value}{blocker}"
                        + (f"\n{summary}" if summary else "")),
        })
        write_json_atomic(self._outbox_path(), entries)

    def flush_outbox(self, notify: Callable[[str], None]) -> int:
        """Stellt unzugestellte Outbox-Eintraege zu (z. B. nach Neustart) und
        markiert sie als geliefert. Liefert die Anzahl."""
        entries = read_json(self._outbox_path(), [])
        sent = 0
        for entry in entries:
            if entry.get("delivered_at"):
                continue
            try:
                notify(str(entry.get("message", "")))
                entry["delivered_at"] = utc_now_iso()
                sent += 1
            except Exception:  # noqa: BLE001 - Zustellung darf scheitern (retry spaeter)
                logger.warning("TaskService: Outbox-Zustellung fehlgeschlagen.", exc_info=True)
        if sent:
            write_json_atomic(self._outbox_path(), entries)
        return sent
