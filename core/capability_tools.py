"""
Acht Arbeitsbereiche (TOOL_DOMAINS) - Organisations- und Sicherheitsebene
ueber der Command-Registry (ADR-072/073).

Die Bereichs-Struktur traegt: Gate-/Risiko-Zuordnung, Doku, Skill-Katalog
und die Denkstruktur des Auftrags-Loops (Phase B). Sie ist NICHT die
Modell-Sicht - die Fassaden-TOOLAUSWAHL wurde empirisch verworfen (ADR-073:
verschachtelt und zweistufig beide unter der flachen Basislinie); das Modell
sieht weiterhin den flachen Katalog aus core/tool_schemas.py. Der Wahl-Code
lebt als Mess-Werkzeug in scripts/facade_eval.py weiter (reasoning_eval
--facade), fuer einen kuenftigen staerkeren API-Waehler.

Vollstaendigkeit ist testerzwungen: jeder Registry-Intent gehoert zu genau
EINEM Bereich (tests/test_capability_tools.py) - ein neuer Command ohne
Zuordnung laesst die Suite durchfallen (Drift-Waechter-Muster).
"""
from __future__ import annotations

# Arbeitsbereich -> (Beschreibungs-Kopf, [Intents]). Zuschnitt: Design-Doc
# 2026-07-14 (PO + 2 Sol-Reviews). get_briefing liegt bei 'jarvis' (Jarvis'
# eigenes Tages-Produkt), bis es in Phase B zum Rezept/Auftrag wird.
TOOL_DOMAINS: "dict[str, tuple[str, list[str]]]" = {
    "wissen": (
        "Das Wissen ueber den Nutzer: dauerhafte Fakten, Personen, benannte Listen. "
        "Fuer 'merk dir/vergiss/wer ist/was weisst du/Einkaufsliste'.",
        ["remember_fact", "forget_fact", "restore_fact", "list_facts",
         "remember_person", "who_is",
         "add_to_list", "remove_from_list", "show_list", "clear_list",
         "restore_list"],
    ),
    "termine": (
        "Alles ZEITGEBUNDENE: der echte (Outlook-)Kalender UND Jarvis-"
        "Erinnerungen. Echte Termine (Uhrzeit/Treffen/Arzt, auch beilaeufig "
        "erzaehlt) -> Kalender-Aktionen; 'erinnere mich' -> Eintrags-Aktionen.",
        ["calendar_agenda", "calendar_add_event", "calendar_move_event",
         "calendar_cancel_event",
         "add_entry", "update_entry", "delete_entry", "restore_entry",
         "list_entries"],
    ),
    "welt": (
        "Der Blick nach draussen: Websuche, Nachrichtenlage ('die Lage'), "
        "Wetter.",
        ["search_web", "get_news", "get_weather"],
    ),
    "kommunikation": (
        "AUSSCHLIESSLICH das E-Mail-Postfach: neue Mails, Werbepost, "
        "Absender-Regeln. NICHT fuer Termine, Aufgaben oder Listen "
        "(-> termine/wissen).",
        ["check_mail", "show_mail_advertising", "mail_hide_sender",
         "mail_keep_sender"],
    ),
    "computer": (
        "Rechner & Medien des Nutzers: Programme oeffnen/installieren, "
        "PC-Analyse, Autostart, Temp-Dateien, Excel lesen, Musik (Spotify).",
        ["open_program", "install_program", "system_status", "analyze_pc",
         "analyze_event_log", "analyze_temp_files", "clean_temp_files",
         "enable_autostart_entry", "disable_autostart_entry",
         "enable_jarvis_autostart", "disable_jarvis_autostart", "read_excel",
         "shutdown_pc",
         "spotify_play", "spotify_pause", "spotify_next", "spotify_previous",
         "spotify_now_playing", "spotify_volume"],
    ),
    "bauen": (
        "Software entstehen lassen und fuehren: neue Werkzeuge bauen, an "
        "eigenen Projekten weiterarbeiten, Repos analysieren/pruefen, den "
        "laufenden Bau-Agenten stoppen.",
        ["build_project", "start_project", "project_continue",
         "delegate_analysis", "delegate_work", "plan_next_step",
         "verify_repo", "stop_agent"],
    ),
    "skills": (
        "Jarvis' selbstgebaute Faehigkeiten (Skill-Bibliothek): aufzaehlen, "
        "was schon gebaut wurde; Ideen fuer Neues.",
        ["list_skills", "propose_ideas", "dismiss_proposal"],
    ),
    "jarvis": (
        "Jarvis selbst: Hilfe/Neuigkeiten, Tages-Briefing, Meeting-"
        "Vorbereitung, Selbstbewertung, Anrede, Neustart/Beenden, "
        "Auftrags-Loop (Portfolio-Review starten/Status/abbrechen).",
        ["show_help", "whats_new", "get_briefing", "prepare_meeting",
         "self_review", "weekly_review", "set_owner_name",
         "restart_runtime", "stop_runtime",
         "portfolio_review", "task_status", "task_resume", "task_cancel"],
    ),
}


def intent_to_tool() -> "dict[str, str]":
    """Intent -> Bereichsname (fuer Gate-Tabellen, Tests, Diagnose)."""
    mapping: dict[str, str] = {}
    for tool, (_desc, intents) in TOOL_DOMAINS.items():
        for intent in intents:
            mapping[intent] = tool
    return mapping
