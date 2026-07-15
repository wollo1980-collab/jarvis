#!/usr/bin/env python3
"""
Reasoning-Schatten-Auswertung (ADR-060 Scheibe 3c, [[llm-kern-nordstern]]).

Liest die Runtime-Logs (config.log_dir/*-runtime.log) und traegt vor, wie oft
der denkende Kern im SCHATTEN mit dem Klassifikator-Router uebereinstimmte
(MATCH) und wo er abwich (DIFF) - die Datengrundlage fuer den Umschalt-
Entscheid (Router -> Kern, Intent fuer Intent). Reine Auswertung, READ-ONLY,
kein LLM-Call, kein Netz.

Aufruf:  python scripts/shadow_report.py [LOG_DIR]
Ohne Argument wird config.log_dir benutzt. Solange `reasoning_shadow` aus ist
(Default), gibt es keine Schatten-Zeilen -> ehrlicher Hinweis statt Zahlen.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import Config  # noqa: E402
from core.dashboard_data import format_shadow_report, shadow_stats  # noqa: E402


def _resolve_log_dir(argv: list[str]) -> Path:
    if len(argv) > 1:
        return Path(argv[1])
    return Config.load().log_dir


def main(argv: list[str]) -> int:
    log_dir = _resolve_log_dir(argv)
    if not log_dir.is_dir():
        print(f"Log-Verzeichnis nicht gefunden: {log_dir}")
        return 1
    print(format_shadow_report(shadow_stats(log_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
