"""Tests fuer core/dashboard_data.py + dashboard.py (ADR-046) - jede
Dashboard-Zahl kommt aus einer realen Quelle; hier gegen Fixture-Dateien
geprueft. Der HTTP-Teil laeuft gegen einen echten Server auf Port 0."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path

from core.dashboard_data import (
    activity_today,
    collect_status,
    delegation_stats,
    entries_status,
    memory_status,
    project_version,
    runtime_status,
)


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_runtime_status_off_without_lock(tmp_path):
    assert runtime_status(tmp_path)["running"] is False


def test_runtime_status_off_when_lock_pid_dead(tmp_path, monkeypatch):
    _write(tmp_path / "jarvis.lock", {"pid": 999999, "timestamp": "2026-07-10T10:00:00"})
    import core.dashboard_data as dd

    monkeypatch.setattr("psutil.pid_exists", lambda pid: False)
    assert runtime_status(tmp_path)["running"] is False


def test_runtime_status_on_when_lock_pid_alive(tmp_path, monkeypatch):
    _write(tmp_path / "jarvis.lock", {"pid": 4242, "timestamp": "2026-07-10T10:00:00"})
    monkeypatch.setattr("psutil.pid_exists", lambda pid: pid == 4242)

    status = runtime_status(tmp_path)
    # Datumsformat deutsch (PO-Vorgabe 10.07.2026): Tag.Monat.Jahr.
    assert status == {"running": True, "pid": 4242, "since": "10.07.2026 10:00"}


def test_runtime_status_on_when_lock_unreadable(tmp_path, monkeypatch):
    """Die msvcrt-Sperre der laufenden Instanz macht die Datei unlesbar -
    genau DAS ist der Laufzeit-Beweis (gleiche Logik wie ADR-026)."""
    lock = tmp_path / "jarvis.lock"
    lock.write_text("{}", encoding="utf-8")

    original_read_text = Path.read_text

    def denied(self, *args, **kwargs):
        if self.name == "jarvis.lock":
            raise PermissionError("gesperrt")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", denied)
    assert runtime_status(tmp_path)["running"] is True


def test_entries_status_counts_upcoming_undated_important(tmp_path):
    now = datetime(2026, 7, 10, 12, 0)
    _write(
        tmp_path / "entries.json",
        [
            {"text": "vorbei", "when": "2026-07-09T09:00", "important": False},
            {"text": "Muellsaecke", "when": "2026-07-10T09:00", "important": False},
            {"text": "Audit", "when": "2026-07-12T09:00", "important": True},
            {"text": "Zahnarzt", "when": "2026-07-11T09:00", "important": False},
            {"text": "Tabs kaufen", "when": "", "important": False},
        ],
    )

    status = entries_status(tmp_path, now=now)

    assert status["total"] == 5
    assert status["upcoming"] == 2
    assert status["undated"] == 1
    assert status["important"] == 1
    # Tages-Fokus (PO 2026-07-11): heute steht nichts mehr AN (Muellsaecke
    # war schon faellig), die kuenftigen (11./12.07.) zaehlen nur ueber
    # `upcoming` in die Fusszeile - keine Karte.
    assert status["today"] == []
    assert "next" not in status
    assert "later_count" not in status  # totes Feld entfernt (Audit-Fund 5)
    # Live-Befund 2026-07-10: heute Faelliges verschwindet nicht stumm -
    # es bleibt bis Tagesende als "war faellig" sichtbar (gestern nicht).
    assert status["due_today"] == [{"when": "09:00", "text": "Muellsaecke"}]


def test_entries_status_shows_only_today_upcoming_as_cards(tmp_path):
    """Ein heute noch anstehender Termin gehoert in `today` (Tageskarte),
    ein Termin naechste Woche NICHT (PO-Reibung 2026-07-11: 'den 18.07. muss
    ich nicht schon heute sehen') - er zaehlt nur ueber `upcoming`."""
    now = datetime(2026, 7, 11, 8, 0)
    _write(
        tmp_path / "entries.json",
        [
            {"text": "Mittagessen", "when": "2026-07-11T12:30", "important": False},
            {"text": "Gewohnheits-Frage", "when": "2026-07-18T09:00", "important": False},
        ],
    )

    status = entries_status(tmp_path, now=now)

    assert status["today"] == [{"when": "12:30", "text": "Mittagessen"}]
    assert status["upcoming"] == 2                 # Fusszeile zaehlt beide (heute + 18.07.)


def test_lists_status_reads_named_lists(tmp_path):
    """Listen-Karte (PO 2026-07-10): Name, Anzahl, Vorschau der ersten drei."""
    from core.dashboard_data import lists_status

    _write(
        tmp_path / "lists.json",
        {"lists": {"einkaufsliste": ["Milch", "Butter", "Brot", "Eier"], "leer": []},
         "trash": {"packliste": ["Zelt"]}},
    )

    result = lists_status(tmp_path)

    # Leere Listen und Papierkorb erscheinen nicht.
    assert result == [
        {"name": "einkaufsliste", "count": 4, "preview": "Milch, Butter, Brot"}
    ]


def test_recent_history_returns_last_lines_for_reload(tmp_path):
    """PO-Reibung 2026-07-10 ('nach F5 ist der Chat blank'): die letzten
    Zeilen der geteilten, bereits redigierten History - kaputte Eintraege
    werden uebersprungen, das Limit greift."""
    from core.dashboard_data import recent_history

    _write(tmp_path / "history.json", [
        {"role": "user", "content": "alt", "timestamp": "t"},
        {"role": "user", "content": "Wie ist die Lage?", "timestamp": "2026-07-11T09:14:02"},
        {"role": "assistant", "content": "Die Lage, Sir ...", "timestamp": "t"},
        {"role": "kaputt"}, "unfug",
        {"role": "assistant", "content": "  ", "timestamp": "t"},
    ])

    result = recent_history(tmp_path, limit=5)

    # time (PO-Wunsch 2026-07-11): ISO-Zeitstempel -> HH:MM; unparsebar -> "".
    assert result == [
        {"role": "user", "content": "Wie ist die Lage?", "time": "09:14"},
        {"role": "assistant", "content": "Die Lage, Sir ...", "time": ""},
    ]
    assert recent_history(tmp_path / "gibtsnicht") == []  # fail-safe leer


def test_config_ui_window_mode(tmp_path):
    """PO-Wunsch 2026-07-10: Vollbild als EINSTELLUNG (ui_window)."""
    import json as json_module

    from core.config import Config

    config_file = tmp_path / "config.json"
    config_file.write_text(json_module.dumps({"ui_window": "fullscreen"}), encoding="utf-8")
    assert Config.load(config_file).ui_window == "fullscreen"
    assert Config().ui_window == "normal"  # Default unveraendert


def test_memory_view_collects_facts_entries_lists(tmp_path):
    """GEDAECHTNIS-Ansicht (Nachtplan Scheibe 4): Fakten mit Kategorie,
    offene Eintraege mit Marker-Daten, Listen mit Posten - fail-safe."""
    from core.dashboard_data import memory_view

    _write(tmp_path / "long_term.json",
           [{"text": "trinkt Kaffee schwarz", "category": "gewohnheit"}])
    _write(tmp_path / "entries.json",
           [{"text": "Zahnarzt", "when": "2099-07-11T09:00", "important": True,
             "notified": False, "repeat": "taeglich", "id": "x", "created": "c"}])
    _write(tmp_path / "lists.json", {"lists": {"einkaufsliste": ["Milch"]}, "trash": {}})

    view = memory_view(tmp_path)

    assert view["facts"] == [{"text": "trinkt Kaffee schwarz", "category": "gewohnheit"}]
    assert view["entries"][0]["text"] == "Zahnarzt"
    assert view["entries"][0]["important"] is True
    assert view["entries"][0]["repeat"] == "taeglich"
    assert view["lists"] == [{"name": "einkaufsliste", "items": ["Milch"]}]
    # Fail-safe: leeres Verzeichnis liefert leere Ansicht, wirft nie.
    empty = memory_view(tmp_path / "gibtsnicht")
    assert empty == {"facts": [], "entries": [], "lists": []}


def test_memory_status_reads_facts_and_history(tmp_path):
    _write(tmp_path / "long_term.json", [{"text": "Max ist mein Sohn"}])
    _write(tmp_path / "history.json", [1, 2, 3])

    status = memory_status(tmp_path)

    assert status["facts"] == 1
    assert status["last_fact"] == "Max ist mein Sohn"
    assert status["history_entries"] == 3


def test_delegation_stats_parses_cost_lines(tmp_path):
    (tmp_path / "2026-07-07-runtime.log").write_text(
        "2026-07-07 00:09:04,339 INFO jarvis.commands.delegate: Repo-Analyse beendet: "
        "repo=jarvis status=✓ dauer=26.1s turns=3 kosten=0.1367 artefakt=a.md\n"
        "2026-07-07 09:40:20,293 INFO jarvis.commands.delegate: Repo-Analyse beendet: "
        "repo=jarvis status=✗ dauer=5.0s turns=1 kosten=0.0100 artefakt=b.md\n",
        encoding="utf-8",
    )

    stats = delegation_stats(tmp_path)

    assert stats["runs"] == 2
    assert stats["ok"] == 1
    assert stats["total_cost_usd"] == 0.1467
    assert stats["last"]["ok"] is False


def test_delegation_stats_includes_work_runs_in_log_order(tmp_path):
    """Scheibe 2 (Agent-Kachel): auch Kaefig-Laeufe (ADR-050) zaehlen, und
    'last' ist der juengste Lauf BEIDER Arten (Log-Reihenfolge, nicht
    Art-Reihenfolge)."""
    (tmp_path / "2026-07-10-runtime.log").write_text(
        "2026-07-10 10:00:00,100 INFO jarvis.commands.delegate: Repo-Analyse beendet: "
        "repo=jarvis status=✓ dauer=26.1s turns=3 kosten=0.1367 artefakt=a.md\n"
        "2026-07-10 15:00:00,100 INFO jarvis.commands.delegate: Schreib-Delegation beendet: "
        "repo=jkc status=✓ dauer=248.0s dateien=4 kosten=0.9500 artefakt=b-arbeit.md\n",
        encoding="utf-8",
    )

    stats = delegation_stats(tmp_path)

    assert stats["runs"] == 2
    assert stats["ok"] == 2
    assert stats["total_cost_usd"] == 1.0867
    assert stats["last"]["kind"] == "arbeit"
    assert stats["last"]["repo"] == "jkc"
    assert stats["last"]["dateien"] == 4
    assert stats["last"]["kosten"] == 0.95


def test_usage_uptime_and_voice_latency_from_logs(tmp_path):
    """Scheibe 7 (Nachtplan): KI-Verbrauch, Uptime und Sprach-Antwortzeit
    aus echten Log-Zeilen - fehlende Daten liefern ehrlich None/0."""
    from datetime import date as date_cls, datetime as dt_cls

    from core.dashboard_data import (
        avg_voice_response_seconds,
        uptime_seconds,
        usage_today,
    )

    today = date_cls(2026, 7, 11)
    (tmp_path / "2026-07-11-runtime.log").write_text(
        "2026-07-11 00:02:24,730 INFO jarvis.runtime: Erinnerungs-Scheduler gestartet (Poll alle 30s).\n"
        "2026-07-11 08:00:00,100 INFO jarvis.providers: Verbrauch: provider=openai modell=gpt-4o-mini tokens_in=500 tokens_out=120\n"
        "2026-07-11 08:00:05,100 INFO jarvis.providers: Verbrauch: provider=openai modell=gpt-5-chat-latest tokens_in=1500 tokens_out=380\n"
        "2026-07-11 08:01:00,100 INFO jarvis.runtime.hotkey: Latenz: Transkription 1.2s · Verarbeitung 2.4s (Antwort 200 Zeichen).\n"
        "2026-07-11 08:02:00,100 INFO jarvis.runtime.hotkey: Latenz: Transkription 0.8s · Verarbeitung 1.6s (Antwort 90 Zeichen).\n",
        encoding="utf-8",
    )

    usage = usage_today(tmp_path, today=today)
    assert usage == {"calls": 2, "tokens_in": 2000, "tokens_out": 500}

    assert avg_voice_response_seconds(tmp_path, today=today) == 2.0

    now = dt_cls(2026, 7, 11, 1, 2, 24)  # exakt 1h nach dem Start-Marker
    assert uptime_seconds(tmp_path, now=now) == 3600

    # Leeres Verzeichnis: ehrliche Leere statt geratener Zahlen.
    assert usage_today(tmp_path / "leer", today=today)["calls"] == 0
    assert avg_voice_response_seconds(tmp_path / "leer", today=today) is None
    assert uptime_seconds(tmp_path / "leer", now=now) is None


def test_activity_today_counts_requests_and_wake_words(tmp_path):
    from datetime import date

    today = date(2026, 7, 10)
    (tmp_path / "2026-07-10-runtime.log").write_text(
        "2026-07-10 09:00:00,100 INFO jarvis.ai: Router: task=planning -> provider=openai\n"
        "2026-07-10 09:00:01,100 INFO jarvis.ai: Router: task=generation -> provider=openai\n"
        "2026-07-10 09:05:00,100 INFO jarvis.runtime.hotkey: Wake-Word erkannt (Score 0.96).\n"
        "2026-07-10 09:06:00,100 INFO jarvis.ai: Router: task=planning -> provider=openai\n",
        encoding="utf-8",
    )

    activity = activity_today(tmp_path, today=today)

    assert activity["requests"] == 2
    assert activity["wake_words"] == 1
    assert activity["last_seen"] == "2026-07-10 09:06:00"


def test_format_de_handles_date_datetime_and_garbage():
    from core.dashboard_data import format_de

    assert format_de("2026-07-12") == "12.07.2026"
    assert format_de("2026-07-10T09:05:00") == "10.07.2026 09:05"
    assert format_de("kaputt") == "kaputt"  # fail-safe roh
    assert format_de(None) is None


def test_project_version_parses_state_head(tmp_path):
    state = tmp_path / "PROJECT_STATE.md"
    state.write_text(
        '---\nversion: "v1.0 — Alltagsassistent"\nactive_increment: x\ntests: 573\n---\n',
        encoding="utf-8",
    )

    info = project_version(state)

    assert info["version"] == "v1.0 — Alltagsassistent"
    assert info["tests"] == 573


def test_collect_status_has_all_sections(tmp_path):
    memory_dir = tmp_path / "memory_data"
    log_dir = tmp_path / "logs"
    memory_dir.mkdir()
    log_dir.mkdir()
    state = tmp_path / "PROJECT_STATE.md"
    state.write_text('---\nversion: "v1.0"\ntests: 1\n---\n', encoding="utf-8")

    status = collect_status(memory_dir, log_dir, state)

    for key in ("generated_at", "runtime", "entries", "memory", "delegations", "activity", "project", "proposal", "impulses"):
        assert key in status
    # Die Briefing-Karte ist raus (PO 2026-07-11) - kein briefing-Feld mehr.
    assert "briefing" not in status


def test_open_impulses_reads_and_orders(tmp_path):
    """Impuls-Karten (ADR-054): der Dashboard-Prozess liest impulses.json
    (die Runtime legt die Impulse; die Datei ist die Bruecke)."""
    import json
    from core.dashboard_data import open_impulses

    (tmp_path / "impulses.json").write_text(json.dumps({
        "open": [
            {"id": "a", "key": "weather-heat-2026-07-11", "kind": "weather",
             "title": "Hitze", "detail": "bis 34°", "created": "2026-07-11T08:00:00"},
            {"id": "b", "key": "weather-storm-2026-07-11", "kind": "weather",
             "title": "Unwetter", "detail": "Gewitter", "created": "2026-07-11T09:00:00"},
        ],
        "dismissed": {},
    }), encoding="utf-8")

    result = open_impulses(tmp_path)

    assert [i["key"] for i in result] == ["weather-storm-2026-07-11", "weather-heat-2026-07-11"]
    assert result[0]["title"] == "Unwetter"


def test_open_impulses_empty_without_file(tmp_path):
    from core.dashboard_data import open_impulses

    assert open_impulses(tmp_path) == []


def test_dashboard_page_renders_impulse_card_and_dismiss():
    import dashboard

    assert "s.impulses" in dashboard._PAGE
    assert "/impulse/dismiss" in dashboard._PAGE
    assert "data-impulse" in dashboard._PAGE
    assert "Jarvis hat mitgedacht" in dashboard._PAGE


def test_dashboard_has_agent_stop_button():
    """Stopp-Knopf (ADR-056 Scheibe 2): das UI hat einen Stopp-Knopf, der auf
    /agent/stop feuert, und den Agenten-Schritt-Strom (Durchsicht)."""
    import dashboard

    page = dashboard._PAGE
    assert "agent-stop" in page
    assert "/agent/stop" in page
    assert "addAgentStep" in page          # Durchsicht (Scheibe 1) im UI


def test_dashboard_has_agent_redirect_input():
    """Umlenken (ADR-056 Scheibe 3): das UI hat ein Eingabefeld, das dem
    laufenden Agenten eine Kurskorrektur ueber /agent/redirect zuruft, und
    stellt das 'redirect'-Durchsicht-Ereignis als Zeile dar."""
    import dashboard

    page = dashboard._PAGE
    assert "agent-redirect-input" in page
    assert "/agent/redirect" in page
    assert "sendRedirect" in page
    assert "flow-redirect" in page          # 'du: ...'-Zeile in der Durchsicht


def test_dashboard_has_left_column_and_chat_timestamps():
    """PO-Reibung 2026-07-11: Benachrichtigungen + 'Die Lage' wandern in eine
    linke Spalte (Chat wird groesser); Chat-Zeilen bekommen eine Uhrzeit."""
    import dashboard

    page = dashboard._PAGE
    assert 'id="leftbar"' in page              # neue linke Spalte
    assert "#leftbar" in page                  # ihr CSS
    # Karten + "Die Lage" wohnen jetzt in der linken Spalte, nicht in main.
    assert page.index('id="leftbar"') < page.index('id="cards"')
    assert page.index('id="cards"') < page.index("<main>")
    # Zeitstempel: Helfer + Stil vorhanden.
    assert "stampEl" in page and "nowHM" in page
    assert ".me .ts" in page


def test_dashboard_orb_header_centered_and_clear_of_text():
    """PO-Reibung 2026-07-11: (1) der JARVIS-Name soll exakt ueber dem Orb
    sitzen (Header per Grid zentriert statt space-between, das ihn seitlich
    verschob); (2) der Orb darf nicht im Text darunter liegen (die Mark-II-
    Ringe stehen ueber die Box hinaus -> margin-bottom gibt Luft)."""
    import dashboard

    page = dashboard._PAGE
    assert "grid-template-columns:1fr auto 1fr" in page   # echtes Zentrieren
    assert "margin-bottom:16px" in page                   # Orb-Abstand zu den Ringen
    assert "space-between; align-items:baseline; margin-bottom:16px" not in page  # alt raus


def test_dashboard_proposal_card_is_dismissable():
    """PO-Reibung 2026-07-11: die Vorschlags-Karte bekommt ein ✕, das den
    Vorschlag verwirft (sonst haengt er den halben Tag)."""
    import dashboard

    page = dashboard._PAGE
    assert "data-proposal" in page
    assert "dismissProposal" in page
    assert "/proposal/dismiss" in page


def test_dismiss_proposal_marks_verworfen(tmp_path):
    """dismiss_proposal setzt den Status offen -> verworfen; danach ist der
    Vorschlag nicht mehr offen (Karte verschwindet). Fail-closed gegen
    Pfad-Traversal und unbekannte Dateien."""
    from core.dashboard_data import dismiss_proposal, open_proposal

    prop_dir = tmp_path / "proposals"
    prop_dir.mkdir()
    (prop_dir / "20260711-075653-plan.md").write_text(
        "# Ein Vorschlag\n\n<!-- status: offen -->\n\nerstellt 2026-07-11T07:56\n",
        encoding="utf-8",
    )
    assert open_proposal(tmp_path) is not None          # zuerst offen

    assert dismiss_proposal(tmp_path, "20260711-075653-plan.md") is True
    assert open_proposal(tmp_path) is None              # danach weg (verworfen)

    # Zweiter Versuch: schon verworfen -> nichts zu ersetzen.
    assert dismiss_proposal(tmp_path, "20260711-075653-plan.md") is False
    # Unbekannte Datei / Traversal -> fail-closed False.
    assert dismiss_proposal(tmp_path, "gibtsnicht.md") is False
    assert dismiss_proposal(tmp_path, "../../etc/passwd") is False


def test_dashboard_tiles_are_content_sized():
    """PO-Reibung 2026-07-11 (UI): Kacheln passen sich dem Inhalt an (feste,
    konsistente Breite statt gestreckter auto-fit/1fr-Kaesten). 'Die Lage'
    wohnt jetzt in der linken Spalte und stapelt dort einspaltig (siehe
    test_dashboard_has_left_column_and_chat_timestamps)."""
    import dashboard

    page = dashboard._PAGE
    assert ".cards { display:flex; flex-wrap:wrap" in page
    assert "flex:0 1 250px" in page
    assert "repeat(auto-fit,minmax(190px,1fr))" not in page   # alt raus
    # In der linken Spalte stapeln die Karten einspaltig, volle Breite.
    assert "#leftbar .cards { flex-direction:column" in page


def test_dashboard_layout_is_symmetric_without_counterweight():
    """PO-Reibung 2026-07-11: mit gleich breiter linker + rechter Spalte (je
    340px) ist das Layout symmetrisch - der fruehere Gegengewicht-Kniff
    (margin-left:340px) und die 1100er-Verbreiterung sind weg; die gewonnene
    Flaeche geht in die Hoehe des Gespraechs. Drei Spalten nur oberhalb 1780px,
    darunter saubere vertikale Stapelung."""
    import dashboard

    page = dashboard._PAGE
    assert "#leftbar { width:340px" in page        # gleich breit wie rightbar
    assert "#rightbar { width:340px" in page
    assert "max-width:980px" in page               # Inhalt bleibt 980
    assert "margin-left:340px" not in page         # kein Gegengewicht mehr
    assert "flex-basis:1100px" not in page         # keine Verbreiterung mehr
    assert "@media (max-width:1780px)" in page      # Stapel-Breakpoint


def test_dashboard_entry_delete_asks_before_deleting():
    """PO-Reibung 2026-07-11: Erinnerung loeschen ist irreversibel (kein
    Papierkorb) - das ✕ oeffnet erst eine Rueckfrage, statt still zu
    loeschen. Impuls-✕ bleibt bewusst Ein-Klick."""
    import dashboard

    page = dashboard._PAGE
    assert "Erinnerung löschen?" in page          # die Rueckfrage
    assert "askDeleteEntry" in page               # Erinnerungs-✕ -> fragen
    assert "pendingConfirm" in page               # Poll pausiert waehrend der Frage
    assert "dismissImpulse" in page               # Impuls-✕ -> direkt (kein Confirm)


def _write_proposal_file(memory_dir, name, status_line, title):
    proposals = memory_dir / "proposals"
    proposals.mkdir(exist_ok=True)
    (proposals / name).write_text(
        "<!-- Jarvis-Vorschlag, erstellt 2026-07-11T00:53:57 - Entwurf zur Freigabe, nicht umgesetzt -->\n"
        + status_line
        + f"\n\n# {title}\n\n## Kurzfassung\nText.\n",
        encoding="utf-8",
    )


def test_open_proposal_returns_newest_open_only(tmp_path):
    """Vorschlags-Karte (PO-Go 11.07.2026): nur Status 'offen' erscheint -
    Umgesetztes/Verworfenes nie als offen zeigen (Attrappen-Verbot)."""
    from core.dashboard_data import open_proposal

    _write_proposal_file(tmp_path, "20260710-100000-plan-next-step.md",
                         "<!-- status: offen -->", "Der offene Vorschlag")
    _write_proposal_file(tmp_path, "20260711-100000-plan-next-step.md",
                         "<!-- status: umgesetzt (abc1234) -->", "Der erledigte Vorschlag")

    result = open_proposal(tmp_path)

    assert result is not None
    assert result["title"] == "Der offene Vorschlag"
    assert result["created"] == "11.07.2026 00:53"
    assert result["file"] == "20260710-100000-plan-next-step.md"


def test_open_proposal_ignores_unmarked_legacy_and_empty(tmp_path):
    from core.dashboard_data import open_proposal

    assert open_proposal(tmp_path) is None  # kein proposals/-Ordner
    _write_proposal_file(tmp_path, "20260708-100000-plan-next-step.md",
                         "", "Altbestand ohne Status")

    # Ohne status-Zeile: unbewertet, erscheint nicht (koennte laengst
    # umgesetzt sein - nie Erledigtes als offen zeigen).
    assert open_proposal(tmp_path) is None


def test_dashboard_page_renders_proposal_card():
    import dashboard

    assert "s.proposal" in dashboard._PAGE
    assert "Jarvis schlägt vor" in dashboard._PAGE


def test_dashboard_briefing_card_removed_warm_morning_line_instead():
    """PO-Reibung 2026-07-11: die 'Dein Morgen-Briefing'-Textkarte war eine
    Wall of Text und wiederholte Wetter+Lage (eigene Kacheln). Sie ist raus;
    stattdessen traegt der Untertitel morgens einen warmen Zusammenfassungs-
    Satz. Der gesprochene 'Briefing'-Befehl (commands/briefing.py) bleibt."""
    import dashboard

    page = dashboard._PAGE
    assert "Dein Morgen-Briefing" not in page      # Textkarte weg
    assert "s.briefing" not in page                # kein Briefing-Feld mehr im UI
    assert "ruhiger Morgen" in page                # warmer Morgen-Satz im Untertitel

    # Der gesprochene Briefing-Befehl bleibt unangetastet.
    from commands import REGISTRY
    assert "get_briefing" in REGISTRY


def test_llm_lineup_reads_real_config_values():
    """BESETZUNG-Kachel (UI-Kampagne Scheibe 1): reine Config-Werte,
    inkl. answer_model-Override und Provider-Rueckfall auf ai_provider."""
    from types import SimpleNamespace

    from core.dashboard_data import llm_lineup

    config = SimpleNamespace(
        ai_provider="openai", planning_provider="", answer_provider="",
        model="gpt-4o-mini", claude_model="claude-sonnet-5",
        answer_model="gpt-5-chat-latest", transcription_model="gpt-4o-mini-transcribe",
        tts_enabled=True, tts_backend="openai",
        openai_tts_model="gpt-4o-mini-tts", openai_tts_voice="onyx",
    )

    lineup = llm_lineup(config)

    assert lineup["planner"] == {"provider": "openai", "model": "gpt-4o-mini"}
    assert lineup["answer"] == {"provider": "openai", "model": "gpt-5-chat-latest"}
    assert lineup["transcription"]["model"] == "gpt-4o-mini-transcribe"
    assert lineup["tts"] == {"backend": "openai", "model": "gpt-4o-mini-tts", "voice": "onyx"}


def test_llm_lineup_shows_agent_backend_when_delegation_enabled():
    """PO-Befund 2026-07-10: die Claude-Code-CLI (Agenten-Arm) fehlte in
    der Besetzung - gezeigt nur, wenn Delegation freigeschaltet ist."""
    from types import SimpleNamespace

    from core.dashboard_data import llm_lineup

    base = dict(ai_provider="openai", planning_provider="", answer_provider="",
                model="gpt-4o-mini", claude_model="", answer_model="",
                transcription_model="whisper-1", tts_enabled=False)

    with_agent = llm_lineup(SimpleNamespace(**base, agent_repos=[{"alias": "jarvis", "path": "x"}]))
    assert with_agent["agent"] == {"backend": "Claude Code"}

    without_agent = llm_lineup(SimpleNamespace(**base, agent_repos=[], agent_write_repos=[]))
    assert without_agent["agent"] is None  # keine Behauptung ohne Freischaltung


def test_llm_lineup_claude_provider_and_tts_off():
    from types import SimpleNamespace

    from core.dashboard_data import llm_lineup

    config = SimpleNamespace(
        ai_provider="openai", planning_provider="", answer_provider="claude",
        model="gpt-4o-mini", claude_model="claude-sonnet-5", answer_model="",
        transcription_model="whisper-1", tts_enabled=False,
    )

    lineup = llm_lineup(config)

    # Gerouteter Claude bekommt NIE einen OpenAI-Modellnamen (ADR-030-Logik).
    assert lineup["answer"] == {"provider": "claude", "model": "claude-sonnet-5"}
    assert lineup["planner"]["model"] == "gpt-4o-mini"
    assert lineup["tts"] is None  # TTS aus => keine Behauptung


def test_http_server_serves_page_and_status(tmp_path):
    """End-to-End: echter Server auf Port 0, echte GETs - Seite und JSON."""
    import dashboard as dashboard_module
    from core.config import Config

    memory_dir = tmp_path / "memory_data"
    log_dir = tmp_path / "logs"
    memory_dir.mkdir()
    log_dir.mkdir()
    config = Config(memory_dir=memory_dir, log_dir=log_dir)

    server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_module.make_handler(config))
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
            page = response.read().decode("utf-8")
            assert response.status == 200
            assert "J A R V I S" in page
            assert "AUSSER DIENST" in page          # Degradations-Zustand vorhanden
            assert "http://127.0.0.1:8766" in page  # ui_port injiziert (Default)
            # UI-Kampagne Scheibe 1: BESETZUNG-Kachel + Quick Commands mit
            # ECHTEN Intents dahinter (data-cmd = die gesendete Nachricht).
            assert "BESETZUNG" in page
            assert 'data-cmd="Wie ist die Lage?"' in page
            assert 'data-cmd="Was steht an?"' in page
            # Scheibe 2: Agent-Kachel (Delegationen live + letzter Lauf).
            assert 'id="agent"' in page and "AGENT" in page
            # Scheibe 3: Orb Mark II - HUD-Ringe vorhanden, an die echten
            # Zustands-Variablen gekoppelt (Farbe --core, Tempo --spin).
            assert 'class="mk2"' in page
            assert "var(--spin1" in page
            # Politur-Runde 2: Sprech-Leiste mit Equalizer - Balken laufen
            # NUR bei echtem hoert/spricht-Zustand (animation-play-state).
            assert 'id="voicebar"' in page
            assert "animation-play-state:running" in page
            # Aktiv-Glow: Panels leuchten, waehrend darin etwas passiert
            # (glow-work/glow-wait an echte Ereignisse gekoppelt).
            assert "glow-work" in page and "glow-wait" in page

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert data["runtime"]["running"] is False  # kein Lock im Fixture
            assert "entries" in data
            assert "weather" in data                    # Karte fail-safe (None ohne Ort)
            assert "owner" in data
            assert data["llm"]["planner"]["model"]      # Besetzung aus der Config

        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/geheim", timeout=5)
            assert False, "404 erwartet"
        except urllib.error.HTTPError as e:
            assert e.code == 404

        # Lokale Schriften (OFL, assets/fonts): Whitelist-Datei kommt als
        # font/woff2, alles andere unter /fonts/ ist fail-closed 404 -
        # insbesondere Pfad-Traversal Richtung config.json.
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/fonts/inter-var.woff2", timeout=5) as response:
            assert response.status == 200
            assert response.headers["Content-Type"] == "font/woff2"
            assert response.read()[:4] == b"wOF2"  # echtes woff2-Magic
        for evil in ("/fonts/../config.json", "/fonts/gibtsnicht.woff2"):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}{evil}", timeout=5)
                assert False, f"404 erwartet fuer {evil}"
            except urllib.error.HTTPError as e:
                assert e.code == 404
        assert "@font-face" in page and "Rajdhani" in page  # Stacks verdrahtet
    finally:
        server.shutdown()
        server.server_close()


def test_weather_summary_caches_and_never_raises(monkeypatch):
    import core.dashboard_data as dd
    import core.weather

    calls = {"n": 0}

    class FakeForecast:
        place = "Musterhausen"
        condition = "sonnig"
        temp_min = 11.6
        temp_max = 19.4
        rain_probability = 10
        current_temp = None      # Tagesverlauf 2026-07-10
        current_condition = None
        segments = []

    def fake_forecast(place, day_offset=0, timeout=10.0, fetcher=None):
        calls["n"] += 1
        return FakeForecast()

    monkeypatch.setattr(core.weather, "get_forecast", fake_forecast)
    dd._weather_cache.clear()

    first = dd.weather_summary("Musterhausen")
    second = dd.weather_summary("Musterhausen")  # aus dem Cache

    assert first == {"place": "Musterhausen", "condition": "sonnig", "temp_min": 12,
                     "temp_max": 19, "rain": 10, "current": None, "segments": []}
    assert second == first
    assert calls["n"] == 1  # Open-Meteo nur einmal gefragt (30-min-Cache)

    dd._weather_cache.clear()
    monkeypatch.setattr(core.weather, "get_forecast", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    assert dd.weather_summary("Musterhausen") is None  # fail-safe, wirft nie
    assert dd.weather_summary("") is None


def test_config_owner_name(tmp_path):
    import json as json_module

    from core.config import Config

    config_file = tmp_path / "config.json"
    config_file.write_text(json_module.dumps({"owner_name": "Alex"}), encoding="utf-8")
    assert Config.load(config_file).owner_name == "Alex"
    assert Config().owner_name == ""  # Default neutral (Release-Hygiene)


def test_config_load_survives_utf8_bom(tmp_path):
    """Live-Befund 10.07.2026: PowerShell schrieb config.json mit BOM -
    Jarvis starb beim Start am JSON-Parser. Nie wieder."""
    import json as json_module

    from core.config import Config

    config_file = tmp_path / "config.json"
    config_file.write_bytes(b"\xef\xbb\xbf" + json_module.dumps({"ui_enabled": True}).encode("utf-8"))

    assert Config.load(config_file).ui_enabled is True


def test_config_reads_dashboard_port(tmp_path):
    import json as json_module

    config_file = tmp_path / "config.json"
    config_file.write_text(json_module.dumps({"dashboard_port": 9999}), encoding="utf-8")
    from core.config import Config

    assert Config.load(config_file).dashboard_port == 9999
    assert Config().dashboard_port == 8765
