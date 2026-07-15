"""Tests fuer den Anzeigenamen auf Zuruf (ADR-057): Planner-Erkennung,
set_owner_name-Command, config.persist_config_value und das Frisch-Lesen
im Dashboard. Kein echter config.json wird angefasst - CONFIG_FILE wird je
Test auf tmp_path umgelenkt."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import core.config as config_module
import dashboard
from core.config import Config, persist_config_value
from core.models import Plan, Status
from core.planner import Planner, _owner_name_plan
from memory.long_term import LongTermMemory

import commands.owner as owner_commands
from commands.owner import SetOwnerNameCommand


# --- Planner-Erkennung (eng: nur echte Selbst-Benennung) --------------------

def test_owner_name_plan_erkennt_nenn_mich():
    plan = _owner_name_plan("nenn mich Max")
    assert plan is not None
    assert plan.intent == "set_owner_name"
    assert plan.target == "Max"


def test_owner_name_plan_erkennt_ich_heisse():
    plan = _owner_name_plan("ich heiße max")
    assert plan is not None
    assert plan.target == "Max"  # Eigenname wird gross geschrieben


def test_owner_name_plan_erkennt_mein_name_ist():
    plan = _owner_name_plan("mein Name ist Max")
    assert plan is not None and plan.target == "Max"


def test_owner_name_plan_erkennt_sag_x_zu_mir():
    plan = _owner_name_plan("sag Alex zu mir")
    assert plan is not None and plan.target == "Alex"


def test_owner_name_plan_erkennt_du_darfst_mich_nennen():
    plan = _owner_name_plan("du darfst mich Max nennen")
    assert plan is not None and plan.target == "Max"


def test_owner_name_plan_ueberspringt_fuellwoerter():
    """Live-Reibung 11.07.2026: Fuellwoerter zwischen 'nenn mich' und dem Namen
    ('ab sofort wieder', 'ab jetzt wieder') brachen die Extraktion -> 'wieder'
    wurde als Name gelesen -> Stoppwort -> Rueckfrage-Schleife. Jetzt egal."""
    for satz in (
        "Nenn mich ab sofort wieder Martin.",
        "Nenn mich ab jetzt wieder Martin.",
        "nenn mich bitte wieder Martin",
        "nenn mich einfach Martin",
        "nenne mich von jetzt an Martin",
    ):
        plan = _owner_name_plan(satz)
        assert plan is not None and plan.target == "Martin", satz


def test_owner_name_plan_ignoriert_fakt_ueber_dritte():
    # Der Kernfall: "Max ist mein Sohn" darf NIE die Anrede kapern.
    assert _owner_name_plan("Max ist mein Sohn") is None


def test_owner_name_plan_ignoriert_stoppwort():
    assert _owner_name_plan("nenn mich nicht so") is None
    assert _owner_name_plan("ich heiße dich willkommen") is None


def test_owner_name_plan_bei_belanglosem_satz_none():
    assert _owner_name_plan("wie wird das Wetter morgen?") is None


def test_planner_routet_namenswunsch_ohne_llm():
    # Der deterministische Vor-Check greift VOR dem LLM und splittet nicht.
    ai = MagicMock()
    planner = Planner(ai)

    steps = planner.plan("nenn mich Max", [])

    assert len(steps) == 1
    assert steps[0].intent == "set_owner_name"
    assert steps[0].target == "Max"
    ai.get_plan.assert_not_called()


# --- Command: setzt live + persistiert + raeumt Fakten ----------------------

def _wire(tmp_path: Path, monkeypatch, owner_start: str = "PO"):
    """Config auf tmp umlenken, frischen config.json + Gedaechtnis anlegen."""
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps({"owner_name": owner_start, "dashboard_port": 8765}, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "CONFIG_FILE", cfg_path)
    monkeypatch.setattr(dashboard, "CONFIG_FILE", cfg_path)
    config = Config()
    config.owner_name = owner_start
    long_term = LongTermMemory(tmp_path)
    owner_commands.configure(config, long_term)
    return config, long_term, cfg_path


def test_set_owner_name_aktualisiert_live_config(tmp_path, monkeypatch):
    config, _lt, _p = _wire(tmp_path, monkeypatch)
    cmd = SetOwnerNameCommand()

    result = cmd.execute(Plan(intent="set_owner_name", target="Max"))

    assert result.status == Status.SUCCESS
    assert "Max" in result.message
    assert config.owner_name == "Max"  # live: der Chat folgt sofort


def test_set_owner_name_schreibt_config_json(tmp_path, monkeypatch):
    _config, _lt, cfg_path = _wire(tmp_path, monkeypatch)
    SetOwnerNameCommand().execute(Plan(intent="set_owner_name", target="Max"))

    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert data["owner_name"] == "Max"
    # andere Schluessel bleiben unberuehrt
    assert data["dashboard_port"] == 8765


def test_set_owner_name_leer_fragt_nach(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    result = SetOwnerNameCommand().execute(Plan(intent="set_owner_name", target="  "))
    assert result.status == Status.NEEDS_CLARIFICATION


def test_set_owner_name_raeumt_alte_namens_fakten(tmp_path, monkeypatch):
    _config, long_term, _p = _wire(tmp_path, monkeypatch)
    long_term.remember("ich möchte, dass du mich PO nennst")
    long_term.remember("Max ist mein Sohn")  # kein Benennungs-Verb

    SetOwnerNameCommand().execute(Plan(intent="set_owner_name", target="Max"))

    texte = [f.text for f in long_term.all_facts()]
    assert "ich möchte, dass du mich PO nennst" not in texte  # entwertet
    assert "Max ist mein Sohn" in texte  # Fakt ueber Dritte bleibt


# --- config.persist_config_value: schmal + verlustfrei ----------------------

def test_persist_config_value_erhaelt_andere_schluessel(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps({"owner_name": "PO", "volume": 0.8, "hotword": "jarvis"}),
        encoding="utf-8",
    )

    persist_config_value("owner_name", "Max", path=cfg_path)

    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert data == {"owner_name": "Max", "volume": 0.8, "hotword": "jarvis"}


def test_persist_config_value_legt_schluessel_an(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"volume": 0.8}), encoding="utf-8")

    persist_config_value("owner_name", "Max", path=cfg_path)

    assert json.loads(cfg_path.read_text(encoding="utf-8"))["owner_name"] == "Max"


# --- Dashboard liest owner_name frisch --------------------------------------

def test_dashboard_live_owner_name_liest_frisch(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"owner_name": "Max"}), encoding="utf-8")
    monkeypatch.setattr(dashboard, "CONFIG_FILE", cfg_path)

    assert dashboard._live_owner_name("PO") == "Max"


def test_dashboard_live_owner_name_fallback_bei_fehler(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "CONFIG_FILE", tmp_path / "fehlt.json")
    # Datei fehlt -> Fallback auf die gebundene Config, Endpunkt bricht nie.
    assert dashboard._live_owner_name("PO") == "PO"
