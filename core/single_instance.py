"""
Single-Instance-Schutz für memory_data/ (ADR-026). Alle drei
Einstiegspunkte (main.py, telegram_main.py, jarvis_runtime.py) zeigen
per Default auf denselben memory_dir - JsonMemoryStore hat kein
Locking. SingleInstanceLock verhindert, dass zwei Prozesse gleichzeitig
gegen dasselbe memory_dir laufen.

Schutz pro memory_dir (nicht global): eine Lock-Datei innerhalb des
jeweiligen memory_dir enthält PID, Entry-Point-Name und Zeitstempel.
Die eigentliche Exklusivität kommt vom atomaren os.open(O_CREAT|O_EXCL)
- verwaiste Lock-Dateien (Prozess nicht mehr am Leben, oder PID durch
Windows wiederverwendet) werden vor dem Erwerb automatisch entfernt.
Zusätzlich wird das Datei-Handle für die Laufzeit offengehalten und per
msvcrt.locking() gesperrt - Windows gibt es beim Absturz automatisch
frei, ohne dass eigener Aufräum-Code laufen muss.
"""
from __future__ import annotations

import json
import logging
import msvcrt
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import psutil

logger = logging.getLogger("jarvis.single_instance")

LOCK_FILENAME = "jarvis.lock"


class InstanceAlreadyRunningError(RuntimeError):
    """Wird geworfen, wenn memory_dir bereits von einer aktiven Jarvis-
    Instanz verwendet wird. Trägt die Diagnosedaten aus der Lock-Datei,
    damit Aufrufer eine klare Fehlermeldung ausgeben können."""

    def __init__(self, pid: object, entry_point: object, timestamp: object):
        self.pid = pid
        self.entry_point = entry_point
        self.timestamp = timestamp
        super().__init__(
            f"Jarvis läuft bereits (PID {pid}, gestartet über {entry_point} "
            f"um {timestamp})."
        )


class SingleInstanceLock:
    """Schützt ein memory_dir vor gleichzeitigem Zugriff mehrerer Jarvis-
    Prozesse (ADR-026). Verwendung: lock.acquire() als allererste Aktion
    in main(), lock.release() in einem finally-Block - oder als Context
    Manager (`with SingleInstanceLock(...):`)."""

    def __init__(self, memory_dir: Path, entry_point: str):
        self.lock_path = memory_dir / LOCK_FILENAME
        self.entry_point = entry_point
        self._fh = None

    def acquire(self) -> None:
        self._clear_if_stale()
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except FileExistsError:
            self._raise_active_lock_error()
            return  # unreachable - _raise_active_lock_error() wirft immer

        self._fh = os.fdopen(fd, "r+", encoding="utf-8")
        try:
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            # os.open(O_EXCL) hat die Exklusivitaet bereits garantiert -
            # ein fehlgeschlagener zusaetzlicher OS-Lock ist nicht fatal,
            # nur die Haertung (Punkt 5, ADR-026) faellt dann weg.
            logger.warning("Zusaetzlicher msvcrt-Lock auf %s fehlgeschlagen.", self.lock_path)

        self._fh.seek(0)
        content = {
            "pid": os.getpid(),
            "entry_point": self.entry_point,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        self._fh.write(json.dumps(content))
        self._fh.truncate()
        self._fh.flush()
        os.fsync(self._fh.fileno())
        logger.info("Single-Instance-Lock erworben (%s, PID %s).", self.entry_point, os.getpid())

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            self._fh.seek(0)
            msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        try:
            self._fh.close()
        except OSError:
            pass
        self._fh = None
        try:
            self.lock_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Konnte Lock-Datei %s beim Beenden nicht entfernen.", self.lock_path)
        logger.info("Single-Instance-Lock freigegeben (%s).", self.entry_point)

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.release()
        return False

    # -- intern ---------------------------------------------------------

    def _clear_if_stale(self) -> None:
        if not self.lock_path.exists():
            return
        try:
            with open(self.lock_path, "r", encoding="utf-8") as f:
                info = json.load(f)
        except PermissionError:
            # Windows verweigert das Lesen, weil eine andere, aktive
            # Instanz die Datei per msvcrt.locking() exklusiv gesperrt
            # haelt - das ist selbst schon der Beweis fuer "aktiv", nicht
            # fuer "verwaist". Nichts tun, os.open(O_EXCL) schlaegt gleich
            # im Anschluss ohnehin fehl.
            return
        except (OSError, json.JSONDecodeError):
            # Datei existiert, ist aber nicht lesbar/kaputt und NICHT
            # durch eine aktive Instanz gesperrt - echt verwaist.
            self._remove_lock_file()
            return

        if self._is_active(info):
            return  # aktiv - der anschliessende os.open(O_EXCL) erkennt das
        logger.warning(
            "Verwaiste Lock-Datei erkannt (PID %s, %s) - wird entfernt.",
            info.get("pid"),
            info.get("entry_point"),
        )
        self._remove_lock_file()

    def _read_lock_info(self) -> Optional[dict]:
        """Bestmoeglicher, toleranter Lesezugriff fuer Diagnose-Zwecke
        (Fehlermeldung bei InstanceAlreadyRunningError) - anders als
        _clear_if_stale() hier bewusst KEINE Sonderbehandlung von
        PermissionError, da hier nichts geloescht wird."""
        try:
            with open(self.lock_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def _is_active(self, info: dict) -> bool:
        pid = info.get("pid")
        entry_point = info.get("entry_point")
        if not isinstance(pid, int) or not psutil.pid_exists(pid):
            return False
        try:
            proc = psutil.Process(pid)
            cmdline = proc.cmdline()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
        # PID-Wiederverwendung: nur als aktiv gelten lassen, wenn der
        # tatsaechlich laufende Prozess denselben Entry-Point-Dateinamen
        # in der Kommandozeile hat (exakter Dateiname, kein Substring -
        # "main.py" ist sonst auch Substring von "telegram_main.py").
        filenames = {os.path.basename(part) for part in cmdline}
        return bool(entry_point) and entry_point in filenames

    def _remove_lock_file(self) -> None:
        try:
            self.lock_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Konnte verwaiste Lock-Datei %s nicht entfernen.", self.lock_path)

    def _raise_active_lock_error(self) -> None:
        info = self._read_lock_info() or {}
        raise InstanceAlreadyRunningError(
            pid=info.get("pid", "?"),
            entry_point=info.get("entry_point", "?"),
            timestamp=info.get("timestamp", "?"),
        )
