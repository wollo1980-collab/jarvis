"""
Zentrale Konfiguration für Jarvis.
Keine Magic Values im Code – alles Konfigurierbare gehört hierher.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config.json"


def _resolve_repo_path(value: str | Path) -> Path:
    """Bindet relative Config-Pfade an das Repo statt ans Prozess-cwd."""
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


@dataclass
class Config:
    # API
    openai_api_key: str = ""
    model: str = "gpt-4o-mini"

    # Sprach-Eingabe (STT, ADR-038): Transkriptionsmodell fuer Telegram-
    # Sprachnachrichten. Nutzt denselben openai_api_key wie oben.
    transcription_model: str = "whisper-1"

    # Push-to-talk am PC (ADR-041): globaler Hotkey -> Mikrofon -> Whisper ->
    # gesprochene Antwort. Startet nur, wenn sounddevice/pynput/Mikrofon/
    # OpenAI-Key vorhanden sind; hier laesst er sich hart abschalten.
    ptt_enabled: bool = True

    # Wake-Word (ADR-044): "Hey Jarvis" per dauerhaft lauschendem Mikrofon,
    # lokal bewertet (openwakeword). Privacy-by-default AUS - bewusst per
    # Config einschalten.
    wake_word_enabled: bool = False
    # Gesprochene Wake-Bestaetigung (beim Start synthetisiert und gecacht).
    # Mehrere Varianten mit "|" trennen ("Ja, Sir?|Sir?|Ich höre.") - pro
    # Zuruf wird zufaellig gewaehlt (Lebendigkeit). Leer = Piepton.
    wake_acknowledgement: str = "Ja, Sir?"

    # News-Briefing (ADR-042): RSS-Feeds fuer "was gibt's Neues?". Read-only,
    # kein Key. Default: tagesschau; beliebig erweiterbar in config.json.
    news_feeds: list = field(
        default_factory=lambda: ["https://www.tagesschau.de/index~rss2.xml"]
    )

    # Wetter (ADR-043, Open-Meteo, keyless): Standard-Ort, wenn der Nutzer
    # keinen nennt ("wie wird das Wetter morgen?"). Leer = Rueckfrage.
    weather_default_location: str = ""

    # Command Center (ADR-046): Port des lokalen Dashboards (dashboard.py,
    # bindet ausschliesslich an 127.0.0.1).
    dashboard_port: int = 8765

    # Browser-Kanal / Jarvis-UI (ADR-047): lokale Runtime-API (Chat +
    # Event-Strom fuer den Orb). Neue Kontroll-Flaeche -> Default AUS,
    # bewusst einschalten (gleiches Prinzip wie wake_word_enabled).
    ui_enabled: bool = False
    ui_port: int = 8766
    # Fenster-Modus des UI-App-Fensters (jarvis_ui.pyw, PO-Wunsch 10.07.2026
    # "Vollbild, aber als Einstellung"): "normal" | "maximized" | "fullscreen".
    # Vollbild verlaesst man mit F11; in allen Modi bleibt es ein normales,
    # verschiebbares Browser-App-Fenster.
    ui_window: str = "normal"
    # Merk-Angebot (ADR-051): Jarvis bietet an, nebenbei erwaehnte dauerhafte
    # Fakten zu speichern (fragt IMMER, speichert nie automatisch). Neues
    # Verhalten -> Default AUS, bewusst einschalten (wie wake_word_enabled).
    memory_offers_enabled: bool = False
    # Impuls-Kreislauf (Endsystem-Kampagne, ADR-054): Jarvis legt proaktiv
    # stille Hinweis-Karten ab (Unwetter u. a.). Anders als das Merk-Angebot
    # standardmaessig AN - der PO hat das proaktive Endsystem ausdruecklich
    # beauftragt (11.07.2026). Ein Impuls handelt nie, er legt nur eine Karte.
    impulses_enabled: bool = True
    # Anzeigename fuer die UI-Begruessung ("Guten Morgen, ..."). Bewusst
    # Config statt Code (kein Personenname im Repo, Release-Hygiene 4.1);
    # leer -> neutrales "Sir".
    owner_name: str = ""

    # Multi-KI Provider-Auswahl (v0.8 Phase 1, ADR-029): "openai" | "claude".
    # Explizite Auswahl per Config, kein Auto-Routing. Claude nutzt einen
    # eigenen Key (ANTHROPIC_API_KEY, ausschliesslich ueber Env, nie in
    # config.json/Git) und ein eigenes Modell.
    ai_provider: str = "openai"
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5"

    # Provider-Router (v0.8 Phase 2, ADR-030): aufgabenabhaengige Auswahl,
    # deterministisch. Leer -> Rueckfall auf ai_provider (rueckwaertskompatibel:
    # ohne diese Felder verhaelt sich alles wie in Phase 1).
    planning_provider: str = ""   # get_plan() / TaskType.PLANNING
    answer_provider: str = ""     # answer()   / TaskType.GENERATION

    # Mail-Briefing (Nutzwert-Phase, ADR-031): Liste privater Postfächer für
    # „Was liegt an?". Nur nicht-geheime Felder hier (label/imap_host/
    # imap_port/username/password_env); das Passwort/App-Passwort steht
    # AUSSCHLIESSLICH in der genannten Umgebungsvariable (ADR-018), nie hier.
    mail_accounts: list = field(default_factory=list)

    # Agenten-Delegation (ADR-034, Umsetzungs-Scheibe 1): Repo-Allowlist fuer
    # die read-only Repo-Analyse. Config-getrieben wie mail_accounts, leerer
    # Default (fail-closed: ohne Eintrag ist kein Repo delegierbar). Jeder
    # Eintrag {"alias": "...", "path": "..."}; nicht gelistete/nicht
    # existierende Pfade werden abgelehnt. Kein Secret hier.
    agent_repos: list = field(default_factory=list)
    # Harter Wall-Clock-Timeout eines Agentenlaufs in Sekunden (Kill-Switch,
    # ADR-034 Guardrails) - bewusst getrennt vom kurzen LLM-`timeout` oben,
    # da eine Repo-Analyse Minuten dauern darf.
    agent_timeout: float = 300.0
    # Schreib-Kaefig (ADR-050): Repos, in denen ein Agent SCHREIBEN darf -
    # bewusst getrennt von agent_repos (lesen heisst nicht schreiben).
    # Fail-closed: leer = keine schreibende Delegation.
    agent_write_repos: list = field(default_factory=list)
    # Warnschwelle je Agentenlauf in USD - GEGENWERT laut CLI (der Agent
    # laeuft ueber das MAX-Abo, Grenzkosten 0; PO-Hinweis 2026-07-10).
    # Zweck: Ausreisser-Wecker fuer ungewoehnlich grosse Laeufe, die das
    # Session-Kontingent fressen. Kein Vorab-Deckel in der CLI verfuegbar.
    agent_cost_warn_usd: float = 2.0
    # Auto-Commit (ADR-056 Scheibe 4, Sicherheitskern): committet Jarvis nach
    # gruener Selbstpruefung + gruener Ampel-Klassifikation das verifizierte
    # Ergebnis einer Schreib-Delegation SELBST (sonst: Vorlage + Freigabe).
    # Default AUS - bewusster Opt-in-Rollout wie ui_enabled; der PO schaltet
    # ihn frei, wenn er der Kette vertraut. Lokal, kein Push (ADR-056).
    agent_auto_commit: bool = False
    # Kuratierter Dev-Werkzeugkasten fuer die Schreib-Delegation (ADR-056
    # Scheibe 4b / Wochenend-Bauplan, PO-Wahl "kuratiert weit"): der Agent darf
    # zusaetzlich Tests/Gate laufen lassen und git LESEN (selbst verifizieren/
    # iterieren) - KEINE freie Shell, kein commit/push. Nur fuer Spielplatz-
    # Repos wirksam; Jarvis' eigener Kern bleibt ausgenommen (delegate-Waechter).
    # Default AUS (fail-closed, Opt-in).
    agent_dev_tools: bool = False

    # Reasoning-Kern im SCHATTEN (ADR-060 Scheibe 3c, der Nordstern-Kurs zum
    # LLM-getriebenen Kern): laeuft der denkende Kern neben dem Klassifikator-
    # Planner nur MIT und loggt, was er TAETE - handelt NIE (der Router bleibt
    # allein handlungsfuehrend). Default AUS, weil an ist ein zusaetzlicher
    # LLM-Call pro Eingabe (Kosten/Latenz) - bewusster Opt-in fuer die
    # Messphase Router vs. Kern.
    reasoning_shadow: bool = False

    # Strangler-Schalter (ADR-060 Phase 2): Liste der Intents, die der denkende
    # Kern WIRKLICH fuehren darf (statt des Klassifikator-Routers) - die
    # Sicherheitsgrenze beim schrittweisen Umhaengen. Waehlt der Kern einen
    # dieser Intents, uebernimmt SEIN Plan; alle anderen Intents bleiben beim
    # Router. Leer = nichts umgehaengt (fail-closed, Default = heutiges
    # Verhalten). Ausfuehrung + ConfirmationGate bleiben unveraendert (der Kern
    # schlaegt vor, das Gate bestaetigt). Ein Intent kommt erst auf die Liste,
    # wenn der Schatten (reasoning_shadow) ihn als sicher belegt hat.
    reasoning_route_intents: list = field(default_factory=list)

    # Antwort-Composer im Schatten (ADR-065 Saeule A, Phase A1): laeuft nebenher,
    # baut EINE Antwort aus dem vollen Kontext (Verlauf + Frage + Werkzeug-
    # Ergebnisse) und LOGGT sie zum Vergleich mit der gezeigten Schablone - noch
    # NICHT gezeigt. Kostet einen zusaetzlichen LLM-Call pro Runde, daher Opt-in,
    # Default AUS. Fail-safe (stoert den Live-Pfad nie).
    response_compose_shadow: bool = False

    # Antwort-Composer ZEIGEN (ADR-065 Saeule A, Phase A2): die komponierte
    # Antwort wird STATT der Schablone gezeigt. `_multistep` = generell bei
    # Mehrfach-Antworten (der groesste Gewinn - kein "✓ | ✓" mehr); `_intents` =
    # zusaetzlich fuer diese einzelnen Intents (Whitelist, spaetere Phasen). Nur
    # bei erfolgreichen Schritten; bei Fehler/Rueckfrage bleibt die klare
    # Schablone. Default AUS/leer, fail-safe (Composer-Fehler -> Schablone).
    response_compose_multistep: bool = False
    response_compose_intents: list = field(default_factory=list)
    # Modell des Composers (ADR-065): bewusst GUENSTIG (Formulieren ist eine
    # leichte Aufgabe) - der Composer laeuft potentiell bei jeder Antwort, daher
    # nicht das teure Generierungs-Modell. Leer = gpt-4o-mini.
    compose_model: str = "gpt-4o-mini"

    # Sitzungs-Zusammenfassung (ADR-065 Saeule B1): in langen Gespraechen faellt
    # der aeltere Verlauf aus dem Fenster - eine rollierende Zusammenfassung haelt
    # den Faden (fliesst ueber long_term_summary zu Chat + Composer). Nutzt das
    # guenstige compose_model, faltet nur in Bloecken (nicht jede Runde ein Call).
    # Default AUS - Opt-in, fail-safe.
    session_summary_enabled: bool = False

    # Semantischer Abruf (ADR-065 Saeule B2, Gedaechtnis Stufe 4): relevante
    # Erinnerungen (Fakten/Episoden) werden pro Anfrage per Embedding-Aehnlichkeit
    # in den Kontext geholt. Anbieter austauschbar (jetzt OpenAI, spaeter lokal mit
    # Ollama) - `embedding_model` waehlt das Modell. Default AUS, fail-safe,
    # Kosten minimal (Embeddings sind sehr guenstig; triviale Eingaben werden
    # uebersprungen). Braucht den OpenAI-Key (wie der Kern).
    semantic_recall_enabled: bool = False
    embedding_model: str = "text-embedding-3-small"

    # Selbst-Verbesserung (ADR-066 Stein 3): Jarvis bewertet aus dem episodischen
    # Log ehrlich die EIGENE Leistung (Reibungen) und legt eine einsehbare
    # Selbstbewertung ab (memory_dir/self_reviews/), abrufbar per 'wie schlaegst
    # du dich?'. Vorschlag/Beobachtung, keine Selbst-Aenderung. Braucht das
    # episodische Log. Default AUS - Opt-in, fail-safe.
    self_review_enabled: bool = False

    # Werkzeug-Vorfilter (Plan B, 13.07.2026): dem denkenden Kern nur die zur
    # Anfrage relevanten Tool-Schemas zeigen (Embedding-Aehnlichkeit) statt aller -
    # Voraussetzung fuer Werkzeug-Wachstum (S4b) und lokale Klein-Modelle. Fail-open
    # (keine Embeddings -> alle Tools). Default AUS, k = Zahl der gewaehlten Tools.
    tool_prefilter_enabled: bool = False
    tool_prefilter_k: int = 12

    # Proaktive Impuls-Zustellung (Plan F, 13.07.2026): ein neuer Impuls (Unwetter
    # etc.) wird nicht nur als Dashboard-Karte gelegt, sondern aktiv an den
    # Besitzer gepusht (ueber den vorhandenen Notifier, z. B. Telegram) - genau
    # EINMAL (Dedupe im Store), Ruhefenster/Deckel bleiben. Default AUS.
    impulse_push_enabled: bool = False

    # Mail-Triage (Plan C1, 13.07.2026): bei mehreren ungelesenen relevanten Mails
    # priorisiert ein LLM-Pass sie ("was zuerst?") statt einer flachen Liste - nur
    # aus Kopfzeilen (Absender/Betreff/Datum), KEINE Mail-Inhalte. Default AUS.
    mail_triage_enabled: bool = False

    # Telegram-Erlaubnis-Haken (S4b Scheibe 2, ADR-071, Zuschnitt A): will der
    # Bau-Agent im Dev-Modus etwas JENSEITS der kuratierten Allowlist (git push,
    # rm, freie Shell), fragt ein PreToolUse-Hook den PO per Telegram (ja/nein).
    # Fail-closed: keine Antwort/keine Runtime/Hook-Fehler = NEIN. Default AUS.
    agent_permission_hook_enabled: bool = False

    # Telegram-Ausbau (a), 13.07.2026 - "COO in der Hosentasche": das Morgen-
    # Briefing (get_briefing + ggf. Mail-Ueberblick, beides read-only) wird einmal
    # pro Tag ab briefing_push_time aktiv ueber den Notifier gepusht. Default AUS.
    briefing_push_enabled: bool = False
    briefing_push_time: str = "07:30"

    # Meeting-Prep-Push (Telegram-Ausbau (a)): startet ein heutiger Termin in den
    # naechsten meeting_prep_lead_minutes, wird die Vorbereitungs-Karte (Plan C4,
    # Termin + Person + verwandte offene Aufgaben) EINMAL gepusht. Default AUS.
    meeting_prep_push_enabled: bool = False
    meeting_prep_lead_minutes: int = 30

    # "Antworten + gleich tun" (ADR-068): stellt der Nutzer eine Frage und faellt
    # dabei eine UMKEHRBARE Aktion (merken/loeschen), beantwortet Jarvis die Frage
    # UND fuehrt die Aktion aus (Undo statt Rueckfrage) - statt stumm zu handeln.
    # PO-Reibung 12.07.: eine Frage nie nur mit einer Tat quittieren. Default AUS.
    answer_and_act_enabled: bool = False

    # Proaktiver Bau-Vorschlag (ADR-067, Koenigsdisziplin): aus Nutzungsmustern +
    # Reibungen leitet Jarvis alle paar Tage EINE baubare Werkzeug-Idee ab und legt
    # sie EINMAL vor (mit Ausloese-Satz). Gebaut wird NIE automatisch - der Nutzer
    # sagt selbst 'Bau mir X' (bestehender gated Pfad). Default AUS, fail-safe.
    build_offers_enabled: bool = False

    # "Neu bei mir"-Hinweis (Spektakulaer-Kampagne #1, Kundenreview 13.07.):
    # aendert sich der juengste CHANGELOG-Eintrag, stellt Jarvis seine neuen
    # Faehigkeiten EINMAL dezent vor ("Frag <Was ist neu?>"). Default AUS.
    whats_new_hint_enabled: bool = False

    # Neue-Version-Hinweis (Spektakulaer #5-light): liegt auf der Platte ein
    # neuerer Commit als der laufende Prozess, sagt Jarvis EINMAL von selbst
    # "sag <starte neu>" - das Update-Ritual muss niemand erraten. Default AUS.
    version_hint_enabled: bool = False

    # Gesprochene Erinnerungen (PO-Reibung 13.07. "Mit Sprache"): faellige
    # Erinnerungen werden zusaetzlich ueber die Lautsprecher gesprochen (wenn
    # der Sprach-Kanal laeuft). Default AUS.
    reminder_speech_enabled: bool = False

    # Episodisches Gedaechtnis (Gedaechtnis-Kampagne Stufe 1): fuehrt ein
    # einsehbares Tagebuch der Ereignisse (memory_dir/episodes/) als Fundament
    # fuer die spaetere naechtliche Reflexion. Rein additiv (nur Schreiben,
    # kein Verhaltensbruch), lokal, Secrets redigiert. Default AUS - Opt-in
    # (wie die uebrigen neuen Faehigkeiten), der PO schaltet es frei.
    episodic_memory_enabled: bool = False

    # Naechtliche Reflexion ('dreaming', Gedaechtnis Stufe 2): destilliert einmal
    # pro Tag die Episoden des Vortags zu einem einsehbaren Reflexions-Journal
    # (memory_dir/reflections/). Braucht episodic_memory_enabled. Vorschlag statt
    # Aktion (handelt nie), fail-safe. Default AUS - Opt-in.
    reflection_enabled: bool = False

    # Merk-Vorschlag aus der Reflexion (Gedaechtnis Stufe 2b): schliesst die
    # Schleife beobachten->reflektieren->EINMAL fragen. Eine Reflexions-Vermutung
    # wird beim naechsten Gespraech als kanalgebundenes Merk-Angebot (ja/nein)
    # vorgeschlagen (reitet auf ADR-051). Braucht reflection_enabled +
    # memory_offers_enabled. Default AUS - der PO prueft erst die Reflexionen,
    # dann schaltet er das Vorschlagen frei. Vorschlag statt Aktion.
    reflection_offers_enabled: bool = False

    # Proaktive Vorbereitung (ADR-063): Jarvis schaut abends selbst im Kalender
    # voraus und bietet EINMAL an, rechtzeitig an einen Termin von morgen zu
    # erinnern ("Morgen 9:00 Steuerberater - um 8:00 erinnern? ja/nein"). Reitet
    # auf der ADR-051-Angebots-Schiene; legt bei 'ja' eine schlichte Erinnerung
    # an. Braucht einen konfigurierten Kalender (Lesen). Default AUS - Opt-in,
    # fail-safe, Vorschlag statt Aktion.
    proactive_prep_enabled: bool = False

    # Projektstart auf Zuruf (ADR-049): Wurzel, UNTER der start_project neue
    # Zielprojekt-Repos anlegt, und der Pfad des AI-Project-Framework-Repos
    # (READ-ONLY-Quelle fuer Herkunfts-Hash/charter_version/ADR-Template).
    # Beide leer = Faehigkeit aus (fail-closed).
    projects_root: str = ""
    framework_repo: str = ""

    # Sprache / Stimme
    voice: str = "default"
    volume: float = 0.8
    # (hotword entfernt 14.07.2026, PO-Entscheidung Nachtmodus: war totes
    # Config - das Wake-Word-Modell ist in hotkey_channel.py fest 'hey_jarvis'.)

    # Persona-Anrede (Kundenreview 13.07. 'du/Sie/Vorname/Sir gemischt';
    # PO-Entscheidung Nachtmodus: Du + «Sir», einstellbar): "du" | "sie".
    # Gilt fuer ALLE formulierten Antworten (Chat + Composer).
    persona_form: str = "du"

    # Voll-Automat Neustart (PO-Entscheidung Nachtmodus 13.07.: bauen +
    # einschalten): liegt eine neue Version auf der Platte, uebernimmt
    # Jarvis sie SELBST - aber NUR im Leerlauf (keine Delegation, kein
    # frisches Gespraech, keine offene Rueckfrage). Default aus.
    auto_restart_enabled: bool = False

    # Auftrags-Loop (Phase B.1, ADR-074): Root fuer den Portfolio-Review
    # (z. B. "C:\\KI"). Leer = TaskService aus (die Auftrags-Befehle
    # antworten dann ehrlich, dass der Loop nicht eingerichtet ist).
    task_portfolio_root: str = ""
    # Anschluss-Fenster nach einer gesprochenen Antwort (ADR-044): so lange
    # hoert Jarvis auf eine Anschlussfrage OHNE erneutes "Hey Jarvis". Zu lang
    # = er verharrt nach dem Wortwechsel unnoetig im Lausch-Modus (PO-Reibung
    # 2026-07-11: "viel zu lange"). 3,5 s reicht fuer eine kurze Folgefrage;
    # per Config feinjustierbar, ohne neu zu bauen.
    voice_followup_seconds: float = 3.5

    # TTS (v0.3) - deaktiviert per Default, da Modell separat
    # heruntergeladen werden muss (siehe README "Piper TTS einrichten").
    tts_enabled: bool = False
    tts_model_path: str = "voices/de_DE-thorsten-medium.onnx"

    # TTS-Backend-Auswahl (v0.3.6, siehe ADR-008): "piper" (Standard,
    # offline) | "openai" | "elevenlabs" | "kokoro". Piper bleibt der
    # Standard - nur wer aktiv umstellt, braucht die Felder darunter.
    tts_backend: str = "piper"

    # OpenAI-TTS (Cloud) - nutzt denselben openai_api_key wie oben.
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "onyx"
    openai_tts_speed: float = 1.0  # 0.25-4.0; PO nutzt 1.3 (config.json)
    # Stil-Anweisung fuer gpt-4o-mini-tts ("Stimme & Hirn" 2026-07-10) -
    # steuert Charakter/Betonung der Stimme. Leer = keine Anweisung
    # (noetig fuer tts-1/tts-1-hd, die keine instructions kennen).
    openai_tts_instructions: str = ""
    # TTS-Streaming (ADR-048, Latenz-Fahrplan Stufe 3): Wiedergabe beginnt
    # mit dem ersten PCM-Chunk statt nach der kompletten Synthese (gemessen
    # 2-5 s Wartezeit). Greift nur bei Backends mit stream_pcm (openai);
    # false = bewaehrter Datei-Weg als Kill-Switch.
    tts_streaming: bool = True

    # ElevenLabs-TTS (Cloud) - eigener API-Key noetig, siehe README.
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model: str = "eleven_multilingual_v2"

    # Kokoro-TTS (offline wie Piper, aber aktuell KEIN Deutsch -
    # siehe core/tts/kokoro_backend.py).
    kokoro_model_path: str = "voices/kokoro-v1.0.onnx"
    kokoro_voices_path: str = "voices/voices-v1.0.bin"
    kokoro_voice: str = "am_onyx"
    kokoro_lang: str = "en-us"

    # Spotify (Sprachsteuerung der eigenen Wiedergabe, braucht Premium).
    # Einmalige App-Registrierung (developer.spotify.com) liefert client_id +
    # client_secret; scripts/spotify_auth.py holt daraus per einmaligem Browser-
    # Login den refresh_token (danach kein Login mehr). Alle drei leer = aus
    # (fail-closed). client_secret/refresh_token sind Secrets - config.json ist
    # gitignoriert + vom release_scan-Tuersteher abgesichert. redirect_uri muss
    # exakt mit der in der Spotify-App registrierten uebereinstimmen.
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_refresh_token: str = ""
    spotify_redirect_uri: str = "http://127.0.0.1:8888/callback"

    # Outlook/M365-Kalender-Connector (ADR-062, read-first). Zugang per
    # scripts/ms_calendar_auth.py eingerichtet (Azure-App-client_id + einmalige
    # Anmeldung -> refresh_token). Leer = Kalender aus (fail-safe). tenant
    # 'common' = persoenliche + Arbeits-Konten. refresh_token ist ein Secret.
    ms_calendar_client_id: str = ""
    ms_calendar_tenant: str = "common"
    ms_calendar_refresh_token: str = ""
    # Alternativer, OAuth-freier Weg (fuer private Outlook.com-Konten, bei denen
    # Microsofts App-Registrierung zu zaeh ist): ein veroeffentlichter ICS-Feed
    # (Outlook.com -> Kalender veroeffentlichen). Read-only Abo-Adresse; hat
    # Vorrang vor dem Graph-Weg. Der Link ist ein Geheimnis (nie ins Repo).
    ms_calendar_ics_url: str = ""

    # Pfade
    memory_dir: Path = BASE_DIR / "memory_data"
    log_dir: Path = BASE_DIR / "logs"

    # Gesprächsgedächtnis
    max_history_entries: int = 200

    # Chat-Antworten auf ein staerkeres OpenAI-Modell heben ("Stimme & Hirn"
    # 2026-07-10), waehrend der Planner beim schnellen `model` bleibt.
    # Leer = kein Override (alles wie bisher). Gilt nur fuer OpenAI.
    answer_model: str = ""
    # Eigenes Token-Budget fuer Chat-ANTWORTEN (Nutzungslauf-Befund
    # 2026-07-10: laengere Antworten brachen am globalen max_tokens=300
    # mitten im Satz ab). 0 = wie max_tokens; Planner-JSON bleibt bei
    # max_tokens (klein = schnell).
    answer_max_tokens: int = 700

    # AI-Aufruf (v0.2.1: keine Magic Values mehr in ai.py)
    temperature: float = 0.0
    timeout: float = 15.0
    max_tokens: int = 300

    # Debug
    debug: bool = False

    @classmethod
    def load(cls, path: Path = CONFIG_FILE) -> "Config":
        data: dict = {}
        if path.exists():
            # utf-8-sig: toleriert ein UTF-8-BOM (schreiben z. B. PowerShell/
            # Editoren gern) - ein BOM darf Jarvis nie am Start hindern
            # (Live-Befund 10.07.2026); ohne BOM identisch zu utf-8.
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

        # Env-Variablen überschreiben Datei (API-Keys gehören nicht in config.json)
        api_key = os.environ.get("OPENAI_API_KEY", data.get("openai_api_key", ""))
        anthropic_key = os.environ.get(
            "ANTHROPIC_API_KEY", data.get("anthropic_api_key", "")
        )
        elevenlabs_key = os.environ.get(
            "ELEVENLABS_API_KEY", data.get("elevenlabs_api_key", "")
        )

        cfg = cls(
            openai_api_key=api_key,
            model=data.get("model", cls.model),
            transcription_model=data.get("transcription_model", cls.transcription_model),
            ptt_enabled=data.get("ptt_enabled", cls.ptt_enabled),
            wake_word_enabled=data.get("wake_word_enabled", cls.wake_word_enabled),
            wake_acknowledgement=data.get("wake_acknowledgement", cls.wake_acknowledgement),
            news_feeds=data.get("news_feeds") or ["https://www.tagesschau.de/index~rss2.xml"],
            weather_default_location=data.get("weather_default_location", cls.weather_default_location),
            dashboard_port=int(data.get("dashboard_port", cls.dashboard_port)),
            ui_enabled=bool(data.get("ui_enabled", cls.ui_enabled)),
            ui_port=int(data.get("ui_port", cls.ui_port)),
            ui_window=str(data.get("ui_window", cls.ui_window)),
            memory_offers_enabled=bool(data.get("memory_offers_enabled", cls.memory_offers_enabled)),
            impulses_enabled=bool(data.get("impulses_enabled", cls.impulses_enabled)),
            owner_name=str(data.get("owner_name", cls.owner_name)),
            ai_provider=data.get("ai_provider", cls.ai_provider),
            anthropic_api_key=anthropic_key,
            claude_model=data.get("claude_model", cls.claude_model),
            planning_provider=data.get("planning_provider", cls.planning_provider),
            answer_provider=data.get("answer_provider", cls.answer_provider),
            mail_accounts=data.get("mail_accounts", []),
            agent_repos=data.get("agent_repos", []),
            agent_timeout=data.get("agent_timeout", cls.agent_timeout),
            agent_write_repos=data.get("agent_write_repos", []),
            agent_cost_warn_usd=float(data.get("agent_cost_warn_usd", cls.agent_cost_warn_usd)),
            agent_auto_commit=bool(data.get("agent_auto_commit", cls.agent_auto_commit)),
            agent_dev_tools=bool(data.get("agent_dev_tools", cls.agent_dev_tools)),
            reasoning_shadow=bool(data.get("reasoning_shadow", cls.reasoning_shadow)),
            reasoning_route_intents=list(data.get("reasoning_route_intents", []) or []),
            response_compose_shadow=bool(data.get("response_compose_shadow", cls.response_compose_shadow)),
            response_compose_multistep=bool(data.get("response_compose_multistep", cls.response_compose_multistep)),
            response_compose_intents=list(data.get("response_compose_intents", []) or []),
            compose_model=str(data.get("compose_model", cls.compose_model) or cls.compose_model),
            session_summary_enabled=bool(data.get("session_summary_enabled", cls.session_summary_enabled)),
            semantic_recall_enabled=bool(data.get("semantic_recall_enabled", cls.semantic_recall_enabled)),
            embedding_model=str(data.get("embedding_model", cls.embedding_model) or cls.embedding_model),
            self_review_enabled=bool(data.get("self_review_enabled", cls.self_review_enabled)),
            answer_and_act_enabled=bool(data.get("answer_and_act_enabled", cls.answer_and_act_enabled)),
            tool_prefilter_enabled=bool(data.get("tool_prefilter_enabled", cls.tool_prefilter_enabled)),
            tool_prefilter_k=int(data.get("tool_prefilter_k", cls.tool_prefilter_k)),
            impulse_push_enabled=bool(data.get("impulse_push_enabled", cls.impulse_push_enabled)),
            agent_permission_hook_enabled=bool(
                data.get("agent_permission_hook_enabled", cls.agent_permission_hook_enabled)),
            briefing_push_enabled=bool(data.get("briefing_push_enabled", cls.briefing_push_enabled)),
            briefing_push_time=str(data.get("briefing_push_time", cls.briefing_push_time) or cls.briefing_push_time),
            meeting_prep_push_enabled=bool(
                data.get("meeting_prep_push_enabled", cls.meeting_prep_push_enabled)),
            meeting_prep_lead_minutes=int(
                data.get("meeting_prep_lead_minutes", cls.meeting_prep_lead_minutes)
                or cls.meeting_prep_lead_minutes),
            mail_triage_enabled=bool(data.get("mail_triage_enabled", cls.mail_triage_enabled)),
            build_offers_enabled=bool(data.get("build_offers_enabled", cls.build_offers_enabled)),
            whats_new_hint_enabled=bool(
                data.get("whats_new_hint_enabled", cls.whats_new_hint_enabled)),
            version_hint_enabled=bool(
                data.get("version_hint_enabled", cls.version_hint_enabled)),
            reminder_speech_enabled=bool(
                data.get("reminder_speech_enabled", cls.reminder_speech_enabled)),
            episodic_memory_enabled=bool(data.get("episodic_memory_enabled", cls.episodic_memory_enabled)),
            reflection_enabled=bool(data.get("reflection_enabled", cls.reflection_enabled)),
            reflection_offers_enabled=bool(data.get("reflection_offers_enabled", cls.reflection_offers_enabled)),
            proactive_prep_enabled=bool(data.get("proactive_prep_enabled", cls.proactive_prep_enabled)),
            projects_root=str(data.get("projects_root", cls.projects_root)),
            framework_repo=str(data.get("framework_repo", cls.framework_repo)),
            voice=data.get("voice", cls.voice),
            voice_followup_seconds=float(data.get("voice_followup_seconds", cls.voice_followup_seconds)),
            volume=data.get("volume", cls.volume),
            persona_form=str(data.get("persona_form", cls.persona_form)).strip().lower() or "du",
            auto_restart_enabled=bool(data.get("auto_restart_enabled", cls.auto_restart_enabled)),
            task_portfolio_root=str(data.get("task_portfolio_root", cls.task_portfolio_root) or ""),
            tts_enabled=data.get("tts_enabled", cls.tts_enabled),
            tts_model_path=data.get("tts_model_path", cls.tts_model_path),
            tts_backend=data.get("tts_backend", cls.tts_backend),
            openai_tts_model=data.get("openai_tts_model", cls.openai_tts_model),
            openai_tts_voice=data.get("openai_tts_voice", cls.openai_tts_voice),
            openai_tts_speed=float(data.get("openai_tts_speed", cls.openai_tts_speed)),
            openai_tts_instructions=str(data.get("openai_tts_instructions", cls.openai_tts_instructions)),
            tts_streaming=bool(data.get("tts_streaming", cls.tts_streaming)),
            answer_model=str(data.get("answer_model", cls.answer_model)),
            answer_max_tokens=int(data.get("answer_max_tokens", cls.answer_max_tokens)),
            elevenlabs_api_key=elevenlabs_key,
            elevenlabs_voice_id=data.get("elevenlabs_voice_id", cls.elevenlabs_voice_id),
            elevenlabs_model=data.get("elevenlabs_model", cls.elevenlabs_model),
            kokoro_model_path=data.get("kokoro_model_path", cls.kokoro_model_path),
            kokoro_voices_path=data.get("kokoro_voices_path", cls.kokoro_voices_path),
            kokoro_voice=data.get("kokoro_voice", cls.kokoro_voice),
            kokoro_lang=data.get("kokoro_lang", cls.kokoro_lang),
            spotify_client_id=os.environ.get("SPOTIFY_CLIENT_ID", data.get("spotify_client_id", "")),
            spotify_client_secret=os.environ.get(
                "SPOTIFY_CLIENT_SECRET", data.get("spotify_client_secret", "")
            ),
            spotify_refresh_token=os.environ.get(
                "SPOTIFY_REFRESH_TOKEN", data.get("spotify_refresh_token", "")
            ),
            spotify_redirect_uri=data.get("spotify_redirect_uri", cls.spotify_redirect_uri),
            ms_calendar_client_id=os.environ.get(
                "MS_CALENDAR_CLIENT_ID", data.get("ms_calendar_client_id", "")),
            ms_calendar_tenant=data.get("ms_calendar_tenant", cls.ms_calendar_tenant),
            ms_calendar_refresh_token=os.environ.get(
                "MS_CALENDAR_REFRESH_TOKEN", data.get("ms_calendar_refresh_token", "")),
            ms_calendar_ics_url=os.environ.get(
                "MS_CALENDAR_ICS_URL", data.get("ms_calendar_ics_url", "")),
            memory_dir=_resolve_repo_path(data.get("memory_dir", cls.memory_dir)),
            log_dir=_resolve_repo_path(data.get("log_dir", cls.log_dir)),
            max_history_entries=data.get("max_history_entries", cls.max_history_entries),
            temperature=data.get("temperature", cls.temperature),
            timeout=data.get("timeout", cls.timeout),
            max_tokens=data.get("max_tokens", cls.max_tokens),
            debug=data.get("debug", cls.debug),
        )
        cfg.memory_dir.mkdir(parents=True, exist_ok=True)
        cfg.log_dir.mkdir(parents=True, exist_ok=True)
        return cfg


def persist_config_value(key: str, value: object, path: Path | None = None) -> None:
    """Aktualisiert EINEN Schluessel in config.json und laesst alle anderen
    Werte und ihre Reihenfolge unberuehrt (liest die Datei, setzt den Wert,
    schreibt sie atomar zurueck). Bewusst schmal: aktuell nur fuer owner_name
    (ADR-057, "nenn mich X" -> Anzeigename). Kein Freibrief fuer beliebige
    Config-Mutation - der aufrufende Command bindet den Schluessel fest.

    Atomar (tmp + os.replace), damit ein Absturz mitten im Schreiben die
    Konfiguration nie zertruemmert - dasselbe Prinzip wie LongTermMemory.

    path=None loest CONFIG_FILE erst zur AUFRUFZEIT auf (nicht als Default-
    Argument beim Import gebunden), damit Tests core.config.CONFIG_FILE
    umlenken koennen, ohne den echten config.json zu beruehren."""
    if path is None:
        path = CONFIG_FILE
    data: dict = {}
    if path.exists():
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    data[key] = value
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
