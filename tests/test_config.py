"""Tests fuer core.config.py - Pfadauflosung fuer repo-gebundene Config."""
from __future__ import annotations

import json

import core.config as config_module
from core.config import Config


def test_load_resolves_relative_dirs_against_base_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "BASE_DIR", tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"memory_dir": "memory_data", "log_dir": "logs"}),
        encoding="utf-8",
    )

    cfg = Config.load(path=config_path)

    assert cfg.memory_dir == tmp_path / "memory_data"
    assert cfg.log_dir == tmp_path / "logs"
    assert cfg.memory_dir.is_dir()
    assert cfg.log_dir.is_dir()


def test_load_keeps_absolute_dirs_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "BASE_DIR", tmp_path / "anderes-repo")
    memory_dir = tmp_path / "custom-memory"
    log_dir = tmp_path / "custom-logs"
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"memory_dir": str(memory_dir), "log_dir": str(log_dir)}),
        encoding="utf-8",
    )

    cfg = Config.load(path=config_path)

    assert cfg.memory_dir == memory_dir
    assert cfg.log_dir == log_dir
    assert cfg.memory_dir.is_dir()
    assert cfg.log_dir.is_dir()
