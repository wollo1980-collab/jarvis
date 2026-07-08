"""Test-Infrastruktur: eindeutiger Basetemp pro Lauf.

Ein *fester* Basetemp (frueher `--basetemp=.pytest_tmp` im Repo) wird unter
Windows/Codex-Sandbox gelegentlich von einem offenen Handle gesperrt. pytest
scheitert dann beim Aufraeumen des alten Verzeichnisses (PermissionError,
"Zugriff verweigert"), und ALLE tmp_path-Fixtures brechen schon im Setup ab -
das blockiert auch den Pre-Commit-Hook (Vollsuite). Der pytest-Standard-Basetemp
hilft nicht: auch er raeumt alte (evtl. gesperrte) Laufverzeichnisse auf.

Loesung: pro Lauf ein frischer, noch NICHT existierender Basetemp. Weil das
Verzeichnis neu ist, muss pytest nichts (potenziell Gesperrtes) loeschen.
Vorrang-Reihenfolge: explizites --basetemp > JARVIS_PYTEST_BASETEMP (als
Basis-Verzeichnis) > OS-Temp. In allen Faellen ausserhalb des Repos.
"""
from __future__ import annotations

import os
import tempfile
import uuid


def pytest_configure(config):
    # Ein ausdruecklich uebergebenes --basetemp behaelt Vorrang.
    if config.option.basetemp:
        return
    base = os.environ.get("JARVIS_PYTEST_BASETEMP") or tempfile.gettempdir()
    config.option.basetemp = os.path.join(base, f"jarvis-pytest-{uuid.uuid4().hex[:8]}")
