"""
Deutsche Aktions-Namen je Intent - die Python-Seite von 'Klartext statt
Maschinen-Namen' (PO-Reibung 2026-07-10; Live-Reibung 13.07. spät: die
Ja/Nein-Rueckfrage nannte 'build_project (erinnerungs-manager)' - der PO
musste RATEN, was er bestaetigt).

Es gibt bewusst ZWEI Tabellen (diese + INTENT_LABELS im dashboard.py-JS,
das kein Python importieren kann) - beide sind per Drift-Waechter-Test
aneinander UND an die Command-Registry gekoppelt: ein neuer Command ohne
Label oder ein abweichender Wortlaut laesst die Suite durchfallen.
"""
from __future__ import annotations

INTENT_LABELS: dict[str, str] = {
    "chat": "Antwort formulieren",
    "add_entry": "Notiz anlegen",
    "list_entries": "Einträge nachsehen",
    "delete_entry": "Eintrag streichen",
    "remember_fact": "Fakt merken",
    "forget_fact": "Fakt vergessen",
    "list_facts": "Gedächtnis zeigen",
    "get_news": "Nachrichtenlage holen",
    "get_weather": "Wetter nachsehen",
    "search_web": "Websuche",
    "check_mail": "Post durchsehen",
    "show_mail_advertising": "Werbepost zeigen",
    "mail_hide_sender": "Absender stummschalten",
    "mail_keep_sender": "Absender behalten",
    "read_excel": "Excel-Datei lesen",
    "system_status": "Systemstatus prüfen",
    "analyze_pc": "PC analysieren",
    "analyze_event_log": "Ereignisprotokoll prüfen",
    "analyze_temp_files": "Temp-Dateien sichten",
    "clean_temp_files": "Temp-Dateien aufräumen",
    "install_program": "Programm installieren",
    "open_program": "Programm öffnen",
    "enable_autostart_entry": "Autostart einschalten",
    "disable_autostart_entry": "Autostart ausschalten",
    "enable_jarvis_autostart": "Jarvis-Autostart einschalten",
    "disable_jarvis_autostart": "Jarvis-Autostart ausschalten",
    "shutdown_pc": "PC herunterfahren",
    "stop_runtime": "Jarvis beenden",
    "restart_runtime": "Jarvis neu starten",
    "start_project": "Projekt anlegen",
    "plan_next_step": "Nächsten Schritt planen",
    "delegate_analysis": "Repo-Analyse",
    "delegate_work": "Schreib-Auftrag",
    "project_continue": "Weiterarbeit",
    "build_project": "Projekt bauen",
    "stop_agent": "Agenten stoppen",
    "verify_repo": "Repo prüfen",
    "self_review": "Selbstprüfung",
    "weekly_review": "Wochenrückblick",
    "list_skills": "Gebautes aufzählen",
    "show_help": "Fähigkeiten vorstellen",
    "whats_new": "Neuigkeiten erzählen",
    "get_briefing": "Briefing zusammenstellen",
    "prepare_meeting": "Meeting vorbereiten",
    "propose_ideas": "Ideen sprudeln",
    "dismiss_proposal": "Vorschlag verwerfen",
    "calendar_agenda": "Kalender nachsehen",
    "calendar_add_event": "Termin eintragen",
    "calendar_move_event": "Termin verschieben",
    "calendar_cancel_event": "Termin absagen",
    "add_to_list": "Zur Liste hinzufügen",
    "remove_from_list": "Von der Liste streichen",
    "show_list": "Liste zeigen",
    "clear_list": "Liste leeren",
    "restore_list": "Liste wiederherstellen",
    "restore_fact": "Fakt wiederherstellen",
    "restore_entry": "Eintrag wiederherstellen",
    "update_entry": "Eintrag ändern",
    "remember_person": "Person merken",
    "who_is": "Person nachschlagen",
    "set_owner_name": "Anrede festlegen",
    "spotify_play": "Musik abspielen",
    "spotify_pause": "Musik pausieren",
    "spotify_next": "Musik: nächster Titel",
    "spotify_previous": "Musik: voriger Titel",
    "spotify_now_playing": "Musik: was läuft?",
    "spotify_volume": "Lautstärke ändern",
    "portfolio_review": "Portfolio-Durchsicht",
    "task_status": "Auftrags-Status",
    "task_resume": "Auftrag fortsetzen",
    "task_cancel": "Auftrag abbrechen",
}


def label_for(intent: str) -> str:
    """Deutscher Aktions-Name; Unbekanntes faellt EHRLICH auf den Rohnamen
    zurueck (lieber technisch als falsch geraten - wie im Dashboard)."""
    return INTENT_LABELS.get(intent, intent)
