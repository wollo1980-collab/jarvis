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


def test_load_reads_agent_repos_and_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "BASE_DIR", tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "agent_repos": [{"alias": "jarvis", "path": "C:\\KI\\jarvis"}],
                "agent_timeout": 120.0,
            }
        ),
        encoding="utf-8",
    )

    cfg = Config.load(path=config_path)

    assert cfg.agent_repos == [{"alias": "jarvis", "path": "C:\\KI\\jarvis"}]
    assert cfg.agent_timeout == 120.0


def test_agent_defaults_are_empty_and_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "BASE_DIR", tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    cfg = Config.load(path=config_path)

    # Fail-closed by default: ohne Config-Eintrag ist kein Repo delegierbar.
    assert cfg.agent_repos == []
    assert cfg.agent_timeout == 300.0
    # Reasoning-Schatten (ADR-060 Scheibe 3c) ist Opt-in, Default aus.
    assert cfg.reasoning_shadow is False
    # Strangler-Schalter (ADR-060 Phase 2): leer = nichts umgehaengt.
    assert cfg.reasoning_route_intents == []
    # Episodisches Gedaechtnis (Stufe 1): Opt-in, Default aus.
    assert cfg.episodic_memory_enabled is False
    # Naechtliche Reflexion (Stufe 2): Opt-in, Default aus.
    assert cfg.reflection_enabled is False
    # Outlook-Kalender (ADR-062): ohne Zugang leer, tenant Default 'common'.
    assert cfg.ms_calendar_client_id == "" and cfg.ms_calendar_refresh_token == ""
    assert cfg.ms_calendar_tenant == "common"
    # Merk-Vorschlag aus der Reflexion (Stufe 2b): Opt-in, Default aus.
    assert cfg.reflection_offers_enabled is False


def test_load_reads_reasoning_shadow_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "BASE_DIR", tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"reasoning_shadow": True}), encoding="utf-8")

    cfg = Config.load(path=config_path)

    assert cfg.reasoning_shadow is True


def test_load_reads_reasoning_route_intents(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "BASE_DIR", tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"reasoning_route_intents": ["get_weather", "open_program"]}),
        encoding="utf-8",
    )

    cfg = Config.load(path=config_path)

    assert cfg.reasoning_route_intents == ["get_weather", "open_program"]


def test_load_reads_episodic_memory_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "BASE_DIR", tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"episodic_memory_enabled": True}), encoding="utf-8")

    cfg = Config.load(path=config_path)

    assert cfg.episodic_memory_enabled is True


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
