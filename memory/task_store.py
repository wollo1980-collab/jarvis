"""
TaskStore - Ereignisjournal + Projektionen (Phase B.1, Bauschritt B2).

Verbindliche Quelle: Bauvertrag v1.0 §7 (ADR-074, Kernentscheidung 2:
atomare JSON-Ereignisse statt JSONL/SQLite). Die WAHRHEIT ist das
Ereignisjournal (events/, Hash-Kette, Revision je Ereignis +1);
task.json und active.json sind nur Projektionen/Cache.

Schreibprotokoll (unter Lock, mit expected_revision):
  pruefen -> Event atomar schreiben -> Projektionen atomar schreiben ->
  task.json ersetzen -> active.json aktualisieren.

Wiederanlauf (§7): Snapshot hinter Journal -> aus letztem Event
rekonstruieren; beschaedigter Snapshot -> als .corrupt-* sichern und
rekonstruieren; Eventluecke/Hashbruch -> STORE_INCONSISTENT (keinerlei
Ausfuehrung, keine automatische Ueberschreibung); mehrere nichtterminale
Auftraege -> ACTIVE_TASK_CONFLICT.

Rohdaten-Artefakte werden VOR dem referenzierenden Event geschrieben und
beim Schreiben redigiert (Secrets nie im Klartext, ADR-040).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Optional

from core.fileio import read_json, write_json_atomic
from core.redaction import redact
from core.task_models import (
    Action,
    ActionRecord,
    Approval,
    Observation,
    Task,
    TaskStatus,
    new_id,
    utc_now_iso,
    validate_transition,
)

logger = logging.getLogger("jarvis.task_store")

_EVENT_FILE_RE = re.compile(r"^(\d{6})-(.+)\.json$")


class StoreConflict(Exception):
    """Konflikt mit maschinenlesbarem Code (EXPECTED_REVISION_MISMATCH,
    STORE_INCONSISTENT, ACTIVE_TASK_CONFLICT, TASK_NOT_FOUND)."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def _event_hash(event: dict[str, Any]) -> str:
    """SHA-256 ueber das kanonische Event OHNE das eigene hash-Feld -
    prev_hash ist enthalten, so entsteht die Kette."""
    body = {k: v for k, v in event.items() if k != "hash"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _redact_deep(value: Any) -> Any:
    """Redigiert JEDES String-Feld rekursiv (Hardening-Runde 15.07.,
    Sol-Analyse Punkt 4: der Store verlaesst sich nicht darauf, dass alle
    Zulieferer redigieren - Persistenz redigiert GRUNDSAETZLICH)."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [_redact_deep(v) for v in value]
    if isinstance(value, dict):
        return {k: _redact_deep(v) for k, v in value.items()}
    return value


class TaskStore:
    def __init__(self, memory_dir: Path):
        self.root = Path(memory_dir) / "tasks"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # --- Pfade ---------------------------------------------------------------

    def _task_dir(self, task_id: str) -> Path:
        return self.root / task_id

    def _events_dir(self, task_id: str) -> Path:
        return self._task_dir(task_id) / "events"

    def _active_path(self) -> Path:
        return self.root / "active.json"

    # --- Journal-Grundlagen ----------------------------------------------------

    def _event_files(self, task_id: str) -> list[Path]:
        events = self._events_dir(task_id)
        if not events.exists():
            return []
        return sorted(p for p in events.iterdir() if _EVENT_FILE_RE.match(p.name))

    def _read_events(self, task_id: str) -> list[dict[str, Any]]:
        return [read_json(p, {}) for p in self._event_files(task_id)]

    def _verify_chain(self, events: list[dict[str, Any]]) -> Optional[str]:
        """None = Kette intakt; sonst der Grund (fuer STORE_INCONSISTENT)."""
        prev_hash = ""
        for i, event in enumerate(events, start=1):
            if int(event.get("revision", -1)) != i:
                return f"Eventluecke: erwartete Revision {i}, fand {event.get('revision')}"
            if event.get("prev_hash", "") != prev_hash:
                return f"Hash-Kette gebrochen vor Revision {i}"
            if _event_hash(event) != event.get("hash", ""):
                return f"Event-Hash falsch bei Revision {i}"
            prev_hash = event["hash"]
        return None

    def _head(self, task_id: str) -> tuple[int, str]:
        """(hoechste Revision, letzter Hash) - 0/'' bei leerem Journal."""
        events = self._read_events(task_id)
        if not events:
            return 0, ""
        last = events[-1]
        return int(last.get("revision", 0)), str(last.get("hash", ""))

    # --- Schreiben -------------------------------------------------------------

    def create(self, task: Task, actor: str = "service") -> Task:
        """Persistiert einen NEUEN Auftrag (Event TASK_CREATED, Revision 1)."""
        with self._lock:
            if self._event_files(task.task_id):
                raise StoreConflict("EXPECTED_REVISION_MISMATCH",
                                    f"Task {task.task_id} existiert bereits.")
            return self._append(task, "task_created", expected_revision=0, actor=actor)

    def commit(self, task: Task, event_type: str, expected_revision: int,
               actor: str = "runner") -> Task:
        """Persistiert eine Zustandsaenderung als Ereignis. `expected_revision`
        muss der Journal-Spitze entsprechen - sonst Konflikt, KEINE
        Ueberschreibung (optimistische Sperre, Vertrag §7)."""
        with self._lock:
            return self._append(task, event_type, expected_revision, actor)

    def _append(self, task: Task, event_type: str, expected_revision: int,
                actor: str) -> Task:
        head_rev, head_hash = self._head(task.task_id)
        if head_rev != expected_revision:
            raise StoreConflict(
                "EXPECTED_REVISION_MISMATCH",
                f"Journal steht bei {head_rev}, erwartet war {expected_revision}.",
            )
        # Transition-Enforcement (Hardening 15.07., Sol-Analyse Punkt 4):
        # die Zustandsmaschine ist nicht nur getestet, der Store ERZWINGT
        # sie - ein illegaler Uebergang wird nie journalisiert.
        if head_rev > 0:
            events = self._read_events(task.task_id)
            prev_status = TaskStatus(events[-1].get("task", {}).get("status", task.status.value))
            if prev_status is not task.status:
                validate_transition(prev_status, task.status)
        new_rev = head_rev + 1
        task.revision = new_rev
        task.updated_at = utc_now_iso()
        event: dict[str, Any] = {
            "event_id": new_id(),
            "revision": new_rev,
            "type": str(event_type),
            "at": task.updated_at,
            "actor": actor,
            "prev_hash": head_hash,
            "task": _redact_deep(task.to_dict()),
        }
        event["hash"] = _event_hash(event)
        events_dir = self._events_dir(task.task_id)
        events_dir.mkdir(parents=True, exist_ok=True)
        # 1) Event (die Wahrheit) ...
        write_json_atomic(events_dir / f"{new_rev:06d}-{event_type}.json", event)
        # 2) ... dann die Projektionen (dieselbe redigierte Sicht wie das Event).
        write_json_atomic(self._task_dir(task.task_id) / "task.json", event["task"])
        self._update_active(task)
        return task

    def _update_active(self, task: Task) -> None:
        active = read_json(self._active_path(), {})
        if task.is_terminal:
            if active.get("task_id") == task.task_id:
                write_json_atomic(self._active_path(), {"task_id": None})
        else:
            write_json_atomic(self._active_path(), {"task_id": task.task_id})

    # --- Lesen / Wiederanlauf ----------------------------------------------------

    def load(self, task_id: str) -> Task:
        """Laedt den Auftrag MIT Wiederanlauf-Regeln (Vertrag §7): die
        Projektion wird gegen das Journal geprueft und bei Bedarf aus dem
        letzten vollstaendigen Event rekonstruiert. Kette kaputt ->
        StoreConflict(STORE_INCONSISTENT) - keinerlei Ausfuehrung."""
        with self._lock:
            events = self._read_events(task_id)
            if not events:
                raise StoreConflict("TASK_NOT_FOUND", task_id)
            problem = self._verify_chain(events)
            if problem:
                raise StoreConflict("STORE_INCONSISTENT", problem)
            head = events[-1]
            head_rev = int(head["revision"])

            snapshot_path = self._task_dir(task_id) / "task.json"
            snapshot = read_json(snapshot_path, None)
            if not isinstance(snapshot, dict) or "task_id" not in snapshot:
                # Beschaedigt/fehlend: sichern (nie still ueberschreiben) und
                # aus dem Journal rekonstruieren.
                if snapshot_path.exists():
                    backup = snapshot_path.with_name(
                        f"task.json.corrupt-{utc_now_iso().replace(':', '')}")
                    snapshot_path.replace(backup)
                    logger.warning("TaskStore: beschaedigter Snapshot gesichert: %s", backup)
                snapshot = None
            if snapshot is not None:
                snap_rev = int(snapshot.get("revision", -1))
                if snap_rev == head_rev:
                    return Task.from_dict(snapshot)
                if snap_rev > head_rev:
                    raise StoreConflict(
                        "STORE_INCONSISTENT",
                        f"Snapshot-Revision {snap_rev} liegt VOR dem Journal ({head_rev}).",
                    )
                logger.info("TaskStore: Snapshot (%d) hinter Journal (%d) - rekonstruiere.",
                            snap_rev, head_rev)
            task = Task.from_dict(head["task"])
            write_json_atomic(snapshot_path, task.to_dict())
            self._update_active(task)
            return task

    def nonterminal_task_ids(self) -> list[str]:
        """Alle Auftraege, deren Journal-Spitze nicht terminal ist."""
        out: list[str] = []
        with self._lock:
            for entry in sorted(self.root.iterdir()) if self.root.exists() else []:
                if not entry.is_dir():
                    continue
                events = self._read_events(entry.name)
                if not events:
                    continue
                task = Task.from_dict(events[-1].get("task", {}))
                if not task.is_terminal:
                    out.append(task.task_id)
        return out

    def last_terminal_task(self) -> Optional[Task]:
        """Der zuletzt beendete (terminale) Auftrag - damit Status/Ergebnis
        auch NACH dem Abschluss abfragbar bleiben (Hardening 15.07.)."""
        latest: Optional[Task] = None
        with self._lock:
            for entry in sorted(self.root.iterdir()) if self.root.exists() else []:
                if not entry.is_dir():
                    continue
                events = self._read_events(entry.name)
                if not events:
                    continue
                task = Task.from_dict(events[-1].get("task", {}))
                if task.is_terminal and (latest is None or task.updated_at > latest.updated_at):
                    latest = task
        return latest

    def active_task_id(self) -> Optional[str]:
        """Der EINE aktive Auftrag - oder StoreConflict(ACTIVE_TASK_CONFLICT)
        bei mehreren nichtterminalen (Vertrag §7: keine Ausfuehrung)."""
        with self._lock:
            open_ids = self.nonterminal_task_ids()
            if len(open_ids) > 1:
                raise StoreConflict("ACTIVE_TASK_CONFLICT",
                                    f"{len(open_ids)} nichtterminale Auftraege: {open_ids}")
            return open_ids[0] if open_ids else None

    # --- Projektionen: Action/Observation/Approval/Record -------------------------

    def record_action(self, action: Action) -> None:
        with self._lock:
            path = self._task_dir(action.task_id) / "actions" / f"{action.action_id}.json"
            write_json_atomic(path, _redact_deep(action.to_dict()))

    def record_observation(self, observation: Observation) -> None:
        with self._lock:
            path = (self._task_dir(observation.task_id) / "observations"
                    / f"{observation.observation_id}.json")
            write_json_atomic(path, _redact_deep(observation.to_dict()))

    def record_approval(self, approval: Approval) -> None:
        with self._lock:
            path = self._task_dir(approval.task_id) / "approvals" / f"{approval.approval_id}.json"
            write_json_atomic(path, _redact_deep(approval.to_dict()))

    def record_action_record(self, record: ActionRecord) -> None:
        with self._lock:
            path = (self._task_dir(record.task_id) / "actions"
                    / f"{record.action_id}.record-{record.attempt}.json")
            write_json_atomic(path, _redact_deep(record.to_dict()))

    def load_observations(self, task_id: str) -> list[Observation]:
        obs_dir = self._task_dir(task_id) / "observations"
        if not obs_dir.exists():
            return []
        items = [Observation.from_dict(read_json(p, {})) for p in sorted(obs_dir.iterdir())
                 if p.suffix == ".json"]
        return sorted(items, key=lambda o: o.created_at)

    # --- Rohdaten-Artefakte --------------------------------------------------------

    def write_artifact(self, task_id: str, text: str, kind: str = "raw") -> tuple[str, str]:
        """Schreibt ein REDIGIERTES Rohdaten-Artefakt (VOR dem referenzierenden
        Event, Vertrag §7) und liefert (artifact_id, sha256)."""
        clean = redact(text or "")
        digest = hashlib.sha256(clean.encode("utf-8")).hexdigest()
        artifact_id = new_id()
        with self._lock:
            art_dir = self._task_dir(task_id) / "artifacts"
            art_dir.mkdir(parents=True, exist_ok=True)
            (art_dir / f"{artifact_id}.txt").write_text(clean, encoding="utf-8")
            write_json_atomic(art_dir / f"{artifact_id}.json", {
                "artifact_id": artifact_id, "kind": kind, "sha256": digest,
                "chars": len(clean), "created_at": utc_now_iso(),
            })
        return artifact_id, digest

    def read_artifact(self, task_id: str, artifact_id: str) -> str:
        path = self._task_dir(task_id) / "artifacts" / f"{artifact_id}.txt"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def artifact_exists(self, task_id: str, artifact_id: str) -> bool:
        return (self._task_dir(task_id) / "artifacts" / f"{artifact_id}.json").exists()
