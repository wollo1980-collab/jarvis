"""
Memory-Layer: JSON-basiert für v0.2, noch keine Vektordatenbank.

Alle Zugriffe laufen über MemoryStore, damit ein späterer Wechsel
(z. B. SQLite oder eine Vektor-DB in v0.4) nur diese eine Datei
betrifft, nicht die Aufrufer in main.py/ai.py.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Protocol

from core.models import Message

logger = logging.getLogger("jarvis.memory")


class MemoryStore(Protocol):
    def get(self, key: str) -> Any: ...
    def set(self, key: str, value: Any) -> None: ...
    def append_history(self, message: Message) -> None: ...
    def get_history(self, limit: int | None = None) -> list[Message]: ...


class JsonMemoryStore:
    def __init__(self, memory_dir: Path, max_history_entries: int = 200):
        self.memory_dir = memory_dir
        self.max_history_entries = max_history_entries

        # Serialisiert die read-modify-write-Zugriffe auf die JSON-Dateien.
        # Seit ADR-035 laeuft die asynchrone Repo-Analyse in einem eigenen
        # Hintergrund-Thread NEBEN dem seriellen Nachrichten-Worker - beide
        # koennen gleichzeitig history.json schreiben. Ohne dieses Lock ginge
        # dabei ein Eintrag verloren oder die Datei wuerde beschaedigt. RLock,
        # damit ein Aufrufer bei Bedarf mehrere Store-Methoden verschachteln
        # koennte, ohne sich selbst zu blockieren.
        self._lock = threading.RLock()

        self.preferences_path = memory_dir / "preferences.json"
        self.history_path = memory_dir / "history.json"
        self.context_path = memory_dir / "context.json"

        for path in (self.preferences_path, self.history_path, self.context_path):
            if not path.exists():
                default: Any = [] if path == self.history_path else {}
                self._write(path, default)

    # -- Preferences / Context -------------------------------------------

    def get(self, key: str) -> Any:
        with self._lock:
            prefs = self._read(self.preferences_path)
            return prefs.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            prefs = self._read(self.preferences_path)
            prefs[key] = value
            self._write(self.preferences_path, prefs)

    # -- Gesprächsgedächtnis (history) -------------------------------------

    def append_history(self, message: Message) -> None:
        with self._lock:
            history = self._read(self.history_path)
            history.append(
                {"role": message.role, "content": message.content, "timestamp": message.timestamp}
            )

            # History-Limit: verhindert unbegrenztes Wachstum von history.json.
            if len(history) > self.max_history_entries:
                history = history[-self.max_history_entries:]

            self._write(self.history_path, history)

    def get_history(self, limit: int | None = None) -> list[Message]:
        with self._lock:
            history = self._read(self.history_path)
        if limit:
            history = history[-limit:]
        return [
            Message(role=h["role"], content=h["content"], timestamp=h["timestamp"])
            for h in history
        ]

    # -- intern -------------------------------------------------------------

    def _read(self, path: Path) -> Any:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning("Konnte %s nicht lesen (%s), verwende leeren Default.", path, e)
            return [] if path.name == "history.json" else {}

    def _write(self, path: Path, data: Any) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
