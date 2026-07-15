"""Tests fuer memory/task_store.py (Phase B.1, Bauschritt B2) - Ereignisjournal,
Projektionen und die Recovery-Matrix aus Bauvertrag §7 (Testmatrix 'Store')."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from core.fileio import read_json, write_json_atomic
from core.task_models import Task, TaskStatus
from memory.task_store import StoreConflict, TaskStore


def _task(**kw) -> Task:
    return Task(title=kw.pop("title", "t"), goal=kw.pop("goal", "g"), **kw)


def _store(tmp_path: Path) -> TaskStore:
    return TaskStore(tmp_path)


def test_create_and_commit_build_hash_chain(tmp_path: Path):
    store = _store(tmp_path)
    task = store.create(_task())
    assert task.revision == 1

    task.status = TaskStatus.READY
    store.commit(task, "contract_frozen", expected_revision=1)
    task.status = TaskStatus.RUNNING
    store.commit(task, "run_started", expected_revision=2)

    events_dir = tmp_path / "tasks" / task.task_id / "events"
    files = sorted(p.name for p in events_dir.iterdir())
    assert files == ["000001-task_created.json", "000002-contract_frozen.json",
                     "000003-run_started.json"]
    e1, e2, e3 = (read_json(events_dir / f, {}) for f in files)
    assert e1["prev_hash"] == "" and e2["prev_hash"] == e1["hash"]
    assert e3["prev_hash"] == e2["hash"]
    # Projektion + Cache folgen dem Journal.
    assert read_json(tmp_path / "tasks" / task.task_id / "task.json", {})["revision"] == 3
    assert read_json(tmp_path / "tasks" / "active.json", {})["task_id"] == task.task_id


def test_wrong_expected_revision_conflicts_without_overwrite(tmp_path: Path):
    store = _store(tmp_path)
    task = store.create(_task())

    with pytest.raises(StoreConflict) as err:
        store.commit(task, "run_started", expected_revision=5)
    assert err.value.code == "EXPECTED_REVISION_MISMATCH"
    assert len(list((tmp_path / "tasks" / task.task_id / "events").iterdir())) == 1


def test_crash_after_event_before_snapshot_rebuilds(tmp_path: Path):
    """Crashpunkt: Event geschrieben, Projektion nicht mehr (Vertrag §7:
    Snapshot eine Revision hinter Journal -> aus letztem Event rekonstruieren)."""
    store = _store(tmp_path)
    task = store.create(_task())
    task.status = TaskStatus.READY
    store.commit(task, "contract_frozen", expected_revision=1)
    # Simulierter Crash: Snapshot auf Revision 1 zuruecksetzen.
    snap = tmp_path / "tasks" / task.task_id / "task.json"
    old = read_json(snap, {})
    old["revision"] = 1
    old["status"] = TaskStatus.DRAFT.value
    write_json_atomic(snap, old)

    loaded = TaskStore(tmp_path).load(task.task_id)

    assert loaded.revision == 2
    assert loaded.status is TaskStatus.READY
    assert read_json(snap, {})["revision"] == 2   # Snapshot repariert


def test_corrupt_snapshot_is_backed_up_and_rebuilt(tmp_path: Path):
    store = _store(tmp_path)
    task = store.create(_task())
    snap = tmp_path / "tasks" / task.task_id / "task.json"
    snap.write_text("{kaputt", encoding="utf-8")

    loaded = TaskStore(tmp_path).load(task.task_id)

    assert loaded.task_id == task.task_id
    backups = list(snap.parent.glob("task.json.corrupt-*"))
    assert len(backups) == 1                       # gesichert, nicht geloescht
    assert read_json(snap, {})["task_id"] == task.task_id


def test_event_gap_and_hash_break_block_execution(tmp_path: Path):
    store = _store(tmp_path)
    task = store.create(_task())
    task.status = TaskStatus.READY
    store.commit(task, "contract_frozen", expected_revision=1)
    task.status = TaskStatus.RUNNING
    store.commit(task, "run_started", expected_revision=2)
    events_dir = tmp_path / "tasks" / task.task_id / "events"

    # Eventluecke: mittleres Event fehlt.
    (events_dir / "000002-contract_frozen.json").unlink()
    with pytest.raises(StoreConflict) as err:
        TaskStore(tmp_path).load(task.task_id)
    assert err.value.code == "STORE_INCONSISTENT"

    # Hashbruch: Event manipuliert (frisches Journal).
    store2 = _store(tmp_path)
    t2 = store2.create(_task(title="t2"))
    path = tmp_path / "tasks" / t2.task_id / "events" / "000001-task_created.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["task"]["goal"] = "MANIPULIERT"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(StoreConflict) as err2:
        TaskStore(tmp_path).load(t2.task_id)
    assert err2.value.code == "STORE_INCONSISTENT"
    # Keine automatische Ueberschreibung des beschaedigten Journals:
    assert json.loads(path.read_text(encoding="utf-8"))["task"]["goal"] == "MANIPULIERT"


def test_two_nonterminal_tasks_are_a_conflict(tmp_path: Path):
    store = _store(tmp_path)
    store.create(_task(title="a"))
    store.create(_task(title="b"))
    with pytest.raises(StoreConflict) as err:
        store.active_task_id()
    assert err.value.code == "ACTIVE_TASK_CONFLICT"


def test_terminal_task_clears_active_and_is_not_listed(tmp_path: Path):
    store = _store(tmp_path)
    task = store.create(_task())
    task.status = TaskStatus.CANCELLED
    store.commit(task, "cancelled", expected_revision=1)

    assert store.nonterminal_task_ids() == []
    assert store.active_task_id() is None
    assert read_json(tmp_path / "tasks" / "active.json", {})["task_id"] is None


def test_concurrent_commits_serialize(tmp_path: Path):
    """Gleichzeitige Store-Aufrufe werden serialisiert (Lock + Revision):
    genau EINER von zwei parallelen Commits mit derselben expected_revision
    gewinnt, der andere bekommt den Konflikt."""
    store = _store(tmp_path)
    task = store.create(_task())
    results: list[str] = []

    def worker():
        clone = Task.from_dict(task.to_dict())
        clone.status = TaskStatus.READY
        try:
            store.commit(clone, "contract_frozen", expected_revision=1)
            results.append("ok")
        except StoreConflict:
            results.append("conflict")

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == ["conflict", "ok"]
    assert store.load(task.task_id).revision == 2


def test_artifacts_are_redacted_hashed_and_written_before_reference(tmp_path: Path):
    store = _store(tmp_path)
    task = store.create(_task())

    artifact_id, digest = store.write_artifact(
        task.task_id, 'api_key = "sk-1234567890abcdef1234"\nREADME-Inhalt', kind="readme")  # release-scan: ok (erfundenes Beispiel-Secret)

    text = store.read_artifact(task.task_id, artifact_id)
    assert "sk-1234567890abcdef1234" not in text      # redigiert (ADR-040); release-scan: ok (erfundenes Beispiel-Secret)
    assert "README-Inhalt" in text
    assert store.artifact_exists(task.task_id, artifact_id)
    meta = read_json(tmp_path / "tasks" / task.task_id / "artifacts" / f"{artifact_id}.json", {})
    assert meta["sha256"] == digest and meta["kind"] == "readme"
