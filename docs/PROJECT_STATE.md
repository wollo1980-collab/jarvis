---
version: "v0.8 P1+2 (Multi-KI) abgeschlossen; Nutzwert-Phase gestartet"
active_increment: nutzwert-phase
tests: 534
latest_adr: 43
stand: 2026-07-09
---

# PROJECT STATE

Quelle: `README.md`, `docs/handbook/HANDBOOK.md`, `docs/logbook.md`, `docs/CHANGELOG.md`, `docs/adr/*.md`
Der maschinenlesbare Kopf (oben) ist die Single Source der Kern-Kennzahlen; das Konsistenz-Gate prüft ihn gegen die Realität (siehe CONTRIBUTING §7).

**Hinweis (Dokument-Landkarte, siehe `CONTRIBUTING.md` §1):** Dieses Dokument ist die Heimat des *aktuellen Stands* — Version, Teststand, aktives Increment, offene Aufgaben, bekannte Schuld, Roadmap/Backlog und Known Limitations. Zeitlose Festlegungen (Leitbild/DNA, Vision, Prinzipien, Sicherheitsmodell) leben in der Verfassung (`docs/handbook/HANDBOOK.md`), der Entwicklungsprozess in `CONTRIBUTING.md`. Hier steht kein zeitloses Gesetz.

## Current Version
`v0.8 "Multi-KI"` - **Phase 1 + Phase 2 umgesetzt, getestet und committet** (noch kein `v0.8`-Git-Tag: v0.8 ist als Version nicht abgeschlossen, da bewusst kein weiterer Phasenausbau jetzt erfolgt - siehe „Next Planned Version").

Davor abgeschlossen und getaggt: `v0.7` "PC-Admin" (`v0.7` → `a7eb86d`); der **Infrastruktur-/Runtime-Baustein** (ADR-024 bis ADR-028, ohne eigene Versionsnummer/Tag), konsolidiert in Handbook v3.7. `v0.4`/`v0.5`/`v0.6`/`v0.7` sind alle abgeschlossen und getaggt.

Verfassung: **`docs/handbook/HANDBOOK.md`** (`constitution_version 4.3`) — zeitlose Projektverfassung, Leitbild/DNA in Teil 1. Die früheren `.docx`-Handbücher (v3.2–v3.8) liegen als Historie unter `docs/handbook/archive/` (nicht maßgeblich).

## Status

Umgesetzt in **v0.8 "Multi-KI"** (Details: `docs/CHANGELOG.md`, ADR-029/030):
- **Phase 1 - Provider-Abstraktion (ADR-029):** `LLMProvider`-Protokoll + `OpenAIProvider` + `ClaudeProvider` in `core/providers.py`; `AIEngine` delegiert den rohen Modellaufruf, `get_plan`/`answer` unverändert. Auswahl per `ai_provider` ("openai"|"claude"), Claude-Default `claude-sonnet-5`. `anthropic` lazy/optional; `ANTHROPIC_API_KEY` nur per Env. `confirmed`-Strip/JSON-Parsing bleiben zentral in `AIEngine`.
- **Phase 2 - deterministischer Provider-Router (ADR-030):** `TaskType` (PLANNING/GENERATION) + `ProviderRouter` in `core/providers.py`, verdrahtet in `core/ai.py` (`get_plan`→PLANNING, `answer`→GENERATION). Neue Config-Felder `planning_provider`/`answer_provider` mit Rückfall auf `ai_provider` (rückwärtskompatibel). Standardprovider eager als Anker, Nicht-Default lazy; Fallback nur um den `chat()`-Aufruf (WARNING). Kein Auto-Routing, keine Laufzeit-Umschaltung.

Sicherheitsfixes (diese Session, ohne eigene Version):
- **`confirmed`-Strip** in `AIEngine.get_plan` (Trust Boundary - ein vom Modell geliefertes `confirmed` kann die Stufe-2/3-Bestätigung nicht mehr umgehen).
- **Bot-Token-Schutz**: `httpx`/`httpcore`-Logger auf WARNING gedämpft (Token nicht mehr im Klartext-Log).
- **TelegramChannel-Shutdown** thread-/eventloop-konform (`stop()` ohne `RuntimeError`).

Handbook-Konsolidierungen seit v0.7:
- **v3.7**: Infrastruktur-/Runtime-Baustein (ADR-024 bis ADR-028).
- **v3.8**: **Leitbild / DNA** (Produktidentität, EBENE 1) - Kap. 0 Leitbild „Wofür Jarvis existiert" (Identität als Haltung) + 9 Produkt-Leitplanken; Angleichungen in Kap. 1/7/26/32; Mission unverändert. Bewusste, dokumentierte Governance-Ausnahme (reine EBENE-1-Konsolidierung mitten in v0.8, ohne Auswirkung auf die technische Code-Basis).
- **constitution_version 4.1**: Auftreten und Tonfall von Jarvis explizit als Produkt-DNA verankert; Chat-System-Prompt und erste zentrale Alltagsantworten wurden daran angeglichen (ruhig, praezise, loyal, trockene Eleganz statt Show).
- **constitution_version 4.2**: **Governance-Invariante** in Teil 6 verankert (PO-Freigabe 2026-07-07) — Jarvis unterliegt derselben Governance wie jeder Beitragende (keine zweite Regelwelt): analysieren & vorschlagen, nie mehr als freigegeben, Freigabe nur für den konkreten Umfang, nach jedem relevanten Schritt anhalten, ehrlich berichten, Prozesse/Sicherheitsmechanismen nie umgehen. Zielbild zeitlos formuliert (keine Modell-/Produktnamen); Regeln werden im zunehmend unbeaufsichtigten Betrieb strukturell erzwungen. Konsolidiert die Richtung aus ADR-036.
- **constitution_version 4.3**: Zwei gezielte Ergänzungen (PO-Freigabe 2026-07-07) aus der Produktvision — Teil 1: „mitdenkender Partner" (proaktiv im Denken, nie autonom im Handeln; COO als Arbeits-Bild) und Teil 2: „Jarvis ist die Maschine, nicht zwingend das Produkt". Bewusst minimal gehalten (keine Wunschliste in der Verfassung); Roadmap/Meilensteine leben im Nordstern (unten), die volle Vision in `docs/VISION.md`.

Weiterhin gültig aus v0.7 und davor (Details in den jeweiligen ADRs): PC-Admin (ADR-020-023), Infrastruktur-/Runtime-Baustein (ADR-024-028), Telegram-Fernzugriff (ADR-018), Excel/Tabellen-Auswertung/KPI (ADR-014/015/016), Kurz-/Langzeitgedächtnis (ADR-009), PC-Grundsteuerung (ADR-011/012).

## Next Planned Version
**Nutzwert-Phase „Mit Jarvis leben"** (PO-Entscheidung 03.07.2026). Bewusst **kein** weiterer v0.8-Phasenausbau (z. B. Routing-Intelligenz/Orchestrator) jetzt - stattdessen beweisen, dass das gelegte Fundament einem Menschen *täglich* Last abnimmt. Methode: **Dogfooding-Protokoll** sammeln („Warum muss ich dafür noch eine App öffnen?"), dann gemeinsam die größte Alltagsreibung **end-to-end** bauen, bis echte tägliche Verlässlichkeit. Erfolgsmarke: der erste echte „Ohne Jarvis würde mir das täglich 30 Minuten kosten"-Moment (HANDBOOK.md Teil 1 / Leitplanke 9 „Erfolg = weniger Last, nicht mehr Funktion"). Prozess bewusst **leichter** (keine neue Philosophie/Governance-Zeremonie).

Die Nutzwert-Phase läuft als **benannter Block ohne eigene Versionsnummer** (Präzedenz: Runtime-Baustein; Versionsnummer ggf. später), **getrennt von v0.8**. **Baustein 1 umgesetzt: Mail-Briefing „Was liegt an?"** (ADR-031) - erster externer Connector, lokal-lesend, gelernte Absenderregeln. **Baustein 2 umgesetzt: Web v1** (ADR-032) - read-only Websuche mit kurzem Ueberblick und sichtbaren Quellen.

**Präzisiert (PO-Entscheidungen 04.07.2026 und 05.07.2026): Inbetriebnahme vor Features, dann bewusst klein weiterbauen.** Jarvis wird primär als Produkt behandelt, das in den Alltag kommt. Bisheriger Verlauf der Phase:
1. **Live-Inbetriebnahme** der offenen realen Pfade.
2. **Echte Nutzung / Reibungsprüfung** ohne vorschnellen Feature-Ausbau.
3. **Ergebnis der ersten Reibung:** Der Autostart als erste reale Nutzwert-Reibung ist erfolgreich abgeschlossen und end-to-end verifiziert.
4. **PO-Entscheidung 05.07.2026:** Da der aktuelle Funktionsumfang noch begrenzt ist und aus der täglichen Nutzung keine weitere relevante Reibung entsteht, darf als Nächstes **eine kleine Nutzwert-Funktion** umgesetzt werden.

Bewusst nicht in dieser Phase: Framework-Ausbau, Architektur auf Vorrat, Feature-Breite. M3 (README-Body-Chunk) bleibt separates Hygiene-Paket. Nächster Schritt: Auswahl und Freigabe der nächsten kleinen Nutzwert-Funktion nach CONTRIBUTING §4.

Umgesetzt in der Nutzwert-Phase (Details: `docs/CHANGELOG.md`, ADR-031/032):
- **Mail-Briefing** - `commands/mail.py` (check_mail / show_mail_advertising / mail_hide_sender / mail_keep_sender, alle Sicherheitsstufe 0), `core/mail_reader.py` (imaplib/email stdlib, **read-only** via `select(readonly=True)`+`BODY.PEEK`, nur Kopfzeilen), `memory/mail_rules.py` (lokale, korrigierbare Absenderregeln - Regel schlägt Heuristik). `mail_accounts` in Config (Secrets per Env). Rein lokal, kein Mailinhalt an eine KI. `core/ai.py` unverändert.
- **Web v1** - `commands/web.py` (`search_web`, Sicherheitsstufe 0) und `core/web_search.py` (DuckDuckGo-Lite-Suche via stdlib, nur Titel/Snippet/URL). Jarvis gibt einen knappen Ueberblick und die Quellen immer sichtbar zurueck. DuckDuckGo-interne Werbe-/Hilfstreffer werden herausgefiltert; Preis-/Verfuegbarkeitsfragen sind promptseitig ausdruecklich mitgemeint. Falls der Planner bei solchen Fragen nur ein zu generisches Ziel liefert (z. B. Produktname ohne `Preis`), ergaenzt `commands/web.py` die fehlende Suchintention gezielt selbst. Verfuegbar ueber `main.py`, `telegram_main.py` und den Runtime-Telegram-Kanal. Retrieval bleibt modellneutral; `core/ai.py` erhielt nur eine kleine Intent-Klarstellung für Web-/Recherche-Anfragen.
- **Runtime-/Autostart-Pfadfix** - `core/config.py` löst relative `memory_dir`-/`log_dir`-Werte aus `config.json` jetzt gegen `BASE_DIR` statt gegen das aktuelle Prozess-cwd auf. Damit schreiben `jarvis_runtime.py` und der Jarvis-Eigenstart bei relativer Standard-Config wieder repo-gebunden unter dem Installationspfad; absolute Pfade bleiben unverändert möglich.
- **Konsolen-Härtung `main.py` (Live-Fund 2026-07-06)** - beim ersten echten „was liegt an?"-Lauf stürzte `main.py` an einem `UnicodeEncodeError` ab: Das Executor-Häkchen (U+2713) ließ sich auf einer cp1252-Konsole nicht ausgeben. `make_console_output_safe()` setzt `stdout`/`stderr` auf `errors="replace"` - nicht darstellbare Zeichen werden ersetzt statt zu crashen (auf UTF-8-Konsolen unverändert; das Häkchen erscheint auf reiner cp1252-Konsole als `?`).
- **Agenten-Delegation, Scheibe 1 (ADR-033/034)** - erster Baustein des Agenten-Arms: Command `delegate_analysis` (`commands/delegate.py`, Sicherheitsstufe 0) delegiert eine **read-only** Repo-Analyse an das modellneutrale `AgentBackend` (`core/agent_backend.py`); erste Implementierung `ClaudeCodeBackend` (`claude -p --allowedTools Read Grep Glob`). Repo-Allowlist `agent_repos` fail-closed, harter Wall-Clock-Timeout, keine git-Operation, vollständiges Logging, reviewbares Artefakt unter `memory_data/delegations/`.
- **Agenten-Delegation, Scheibe 2 (ADR-035)** - asynchrone Ausführung + Telegram-Push: `delegate_analysis` ist über den **Runtime-Telegram-Kanal** auslösbar (sofortige Quittung → Hintergrundlauf → Ergebnis-Push). Hintergrund-Worker im Besitz der `JarvisRuntime` (`submit(allow_async=...)`, `_run_delegation`, Kill-Switch über `stop()`); Backend cancelbar (`Popen` + `cancel_event`, Abbruch-Präzedenz natürlich>Cancel>Timeout); `memory/store.py` per RLock thread-sicher; **genau 1** gleichzeitige Delegation (Busy-Flag). Telegram bleibt reiner Transportkanal; der Standalone-Bot (`telegram_main.py`) bleibt bewusst ohne diesen Intent. **Bewusst noch nicht:** schreibende Agenten (Fix/Branch, Scheibe 3), mehrere Agenten parallel.

## Tests
Volle Suite grün. Autoritative Zahl (`tests`) und Datum (`stand`) stehen im Kopf.

Bekannter Standardlauf: `C:\KI\jarvis\.venv\Scripts\python.exe -m pytest -q`
(`pytest.ini` setzt ein repo-lokales `--basetemp`, damit `tmp_path` nicht am
System-Temp der Sandbox scheitert).

### Known Failure
Keiner aktuell.

## Offene Aufgaben

### Technische TODOs (Definition of Done / Betrieb, kein neuer Scope)
- **Live-Test Mail-Briefing (ADR-031): vollständig verifiziert (2026-07-06)** - „was liegt an?" real gelaufen **lokal** über `main.py` (echte Gmail-IMAP-Verbindung, 2 wichtige Mails erkannt, 48 Werbe-Mails ausgeblendet) **und remote über Telegram** (Gegencheck durch den PO bestanden, Arbeitspaket B). Gmail-App-Passwort per `setx JARVIS_GMAIL_APP_PASSWORD` gesetzt. **Offen bleibt nur: Hotmail-Auth verifizieren** (Microsoft baut Basis-Auth/App-Passwörter ab; ggf. OAuth statt IMAP-Passwort).
- **Live-Test Web v1 (ADR-032): real verifiziert (2026-07-06)** - lokaler `main.py`-Lauf (5 echte Treffer + Überblick mit sichtbaren Quellen), allgemeine/Wetter-/Preisanfragen über Telegram/Runtime, Timeout-/Nichterreichbar-Fall (sauberer `WebSearchError`) und schwache Trefferlage geprüft. Kein offener Restfall.
- **Live-Test Claude-Provider** mit echtem `ANTHROPIC_API_KEY` auf dem echten Windows-Rechner - bewusst verschobener manueller Verifikationsschritt (kein offener Implementierungsfehler). Pfad ist offline bis zur SDK-Grenze verifiziert; nur der bezahlte End-zu-End-Call steht aus.
- Manueller Live-Test der übrigen Kernfunktionen mit echtem API-Key auf dem echten Windows-Rechner (Definition of Done, CONTRIBUTING §8) - bisher nur automatisiert/gemockt. `install_program` real ausführen ist ein bewusster, expliziter Schritt und sollte gezielt vom Product Owner freigegeben/begleitet werden.
- **Smoke-Test der Jarvis-Runtime mit echtem Bot-Token (TelegramChannel): verifiziert (2026-07-06)** - das Mail-Briefing lief real über den Runtime-Telegram-Kanal end-to-end durch (PO-Gegencheck); zusammen mit dem bereits verifizierten Jarvis-Eigenstart nach Windows-Anmeldung ist der Runtime-/Bot-Betrieb damit live bestätigt.
- **Live-Betrieb Agenten-Delegation (ADR-034/035): verifiziert (2026-07-07).** `pythonw`-Auth-Caveat abgehakt - `claude -p` läuft aus einem konsolenlosen `pythonw.exe`-Prozess angemeldet (read-only sauber). Runtime mit neuem Code hochgefahren (Worker + TelegramChannel Long-Polling). **Telegram-End-to-End bestätigt** (PO, echtes Handy): „analysiere jarvis: …" → sofortige Quittung → Ergebnis-Push. Damit sind Scheibe 1 (read-only, lokal) und Scheibe 2 (async über Telegram) real in Betrieb. Zuvor (2026-07-06) isolierter `claude -p`-Rauchtest bestanden inkl. Read-only-Nachweis; dabei ein cp1252-Encoding-Bug gefunden und behoben (UTF-8).
- Piper-Sprachmodell herunterladen und `tts_enabled: true` für einen Live-TTS-Test setzen.
- **DNA-Sprachdurchlauf abgeschlossen (2026-07-07):** `commands/monitor.py`, `commands/reports.py`, `commands/excel.py` durchgesehen. Ergebnis: bereits weitgehend in Jarvis' Stimme (faktisch, ruhig, Grenzen offen benannt). Angeglichen wurden die Ausreißer - drei Rückfragen bei Mehrdeutigkeit fragen jetzt („Welche soll ich nehmen?") statt zu befehlen („Bitte eindeutig machen"), und internes Vokabular („Phase 1") wurde aus einer nutzerseitigen Excel-Meldung entfernt. Reine Wortlaut-Änderung, kein Verhalten.
- `anthropic` ist im `.venv` installiert (0.116.0); `requirements.txt` führt es bewusst optional/auskommentiert (lazy Import, ADR-029).
- `.git_broken_5/` (Reste eines frühen, abgebrochenen git-init-Versuchs) liegt noch im Arbeitsordner, per `.gitignore` ausgeschlossen - bewusst nicht gelöscht (keine destruktive Aktion ohne Rückfrage).

### Reibungsprotokoll (Nutzwert-Phase, Dogfooding)

Durable Sammlung der realen Nutzungserkenntnisse - Grundlage für die Auswahl der nächsten Reibung (kein Umsetzungsauftrag).

- **Kernbefund (PO, 2026-07-06):** Jarvis wird kaum genutzt. Die vorhandenen Einzeldienst-Features verlieren gegen native Apps: Mail-Briefing < Outlook-App, Web-Suche < Browser, `system_status` remote nutzlos (Rechner ist idle, weiß man auch so). Ursache: Diese Bausteine **bauen einzelne Dienste nach, statt zu orchestrieren** - Abdrift von Leitplanke 3 („Orchestrieren statt ersetzen"). Konsequenz: Wert entsteht nur durch Orchestrierung über Dienste hinweg **oder** durch eine Fähigkeit, die keine App hat. Bequemlichkeit (Sprache, UI) ist erst danach sinnvoll.
- **Nordstern (PO):** Orchestrierung von Outlook/Kalender/Browser - **nicht** nachbauen. Nutzungslandschaft: Gmail (privates Postfach, bereits angebunden), Outlook-Kalender privat **und** Arbeit, Teams.
  - Einschränkung, die noch zu prüfen ist: Kalender = Microsoft → Microsoft Graph/OAuth2 (schwerer als der IMAP-Mail-Connector, neue Abhängigkeit, Token=Secret, ADR). Der **Arbeits**-Tenant ist vermutlich IT-gesperrt für Drittanbieter-Apps. Echter Orchestrierungswert entsteht **cross-provider** (Gmail-Mail + Outlook-Kalender in einem Überblick - das leistet keine App allein).
- **Reibung „Eingabe":** Tippen in Telegram mühsam (→ Sprache/STT); keine Desktop-Oberfläche. Beides betrifft nur den **Zugang**, nicht den Wert - bewusst nachgeordnet.
- **Kandidat-Richtung „Fernsteuerung PC":** konkrete PO-Wünsche (Spiel remote laden/auf schnellste Platte installieren; „was kann weg" bei Platzmangel). Einzige Klasse **ohne** native Konkurrenz. Gemeinsamer harter Kern: **sichere Fernausführung von Stufe-2/3-Aktionen** = bewusste Erweiterung des Fernzugriff-Modells (ADR, aber intern - kein OAuth/keine IT-Sperre).
- **Gewählte Richtung (PO, 2026-07-06): Agenten-Arm.** Vision-Modell (drei Ebenen): Jarvis = Vermittlungsschicht über **Informationen** (Outlook/Teams/Kalender/Browser/OneDrive/GitHub), **Agenten** (Claude/Codex/GPT) und **Geräte** (PC/NAS/Smartphone/Smart Home) — Kandidat für eine bewusste Handbook-Teil-2-Schärfung (🔴, später). Der Dienst-/Kalender-Arm ist bis dahin geparkt (Microsoft-Graph/OAuth + wahrscheinlich IT-gesperrter Arbeits-Tenant). Konkretes Ziel: „während ich unterwegs bin, Repo X analysieren / einen Fix vorbereiten, fertig zum Review bei Rückkehr" - zeitversetzt, Governance intakt (kein Commit auf `main` ohne menschliches Review).
- **Delegationsprozess:** Der modellunabhängige 9-Schritte-Orchestrierungsprozess ist in **ADR-033** (accepted) festgehalten. **ADR-034** (accepted) wählt Claude Code als erstes Backend und die erste Fähigkeit read-only Repo-Analyse; **Scheibe 1 (lokal-synchron, A–D) ist umgesetzt und committet** (`delegate_analysis`, `core/agent_backend.py`). **ADR-035 (accepted, PO-Freigabe 2026-07-06)** legt **Scheibe 2 (E/F: asynchrone Ausführung + Telegram-Push)** fest — **umgesetzt und committet**: Hintergrund-Worker im Besitz der `JarvisRuntime`, Telegram reiner Transportkanal, genau 1 gleichzeitige Delegation, Auth über Account-Login. Scheibe 3 (Schreiben/Fix) bleibt weiter tabu.

### Feature-TODOs & Backlog (nächste Bausteine, NICHT jetzt umsetzen)
Roadmap und Backlog leben **hier** in PROJECT_STATE — die Verfassung (`HANDBOOK`) trägt keine Roadmap/Status; abgeschlossene Versionen stehen in `CHANGELOG`. Technische Detail-Notizen:
- Spätere v0.8-Phasen (nach der Nutzwert-Phase, falls fortgesetzt): aufgabenabhängiges Routing/Orchestrierung, ggf. `ANALYSIS`-Trennung (optionaler `task`-Parameter an `answer()`), lokale Modelle (Ollama). Bewusst NICHT jetzt (siehe ADR-030 „Bewusst NICHT Bestandteil von Phase 2").
- Weiterer KI-Verwender: `configure()`-Duplizierung (`reports.py`/`monitor.py`/`web.py`) zu einer gemeinsamen Abstraktion zusammenführen prüfen, sobald daraus echter Strukturgewinn entsteht.
- Den `preview()`-Hook (ADR-023) für weitere schreibende PC-Admin-Commands nutzen, sobald umgesetzt.

**Langfristige Produktvision — Nordstern & Ausbaustufen (aus `docs/VISION.md`; Richtung, kein Umsetzungsauftrag):**
Jarvis als persönlicher **digitaler COO** — mitdenkender Sparringspartner, der Entscheidungen vorbereitet und die Umsetzung koordiniert; der Mensch bleibt CEO und entscheidet. Ausbaustufen:
- **Phase 1 — Persönlicher Assistent.**
- **Phase 2 — Digitaler COO** (Projekt-/Selbstanalyse, Priorisierung, Planung, Roadmaps, Verbesserungsvorschläge). **`plan_next_step` (2026-07-07) ist der erste Baustein.**
- **Phase 3 — Spezialisierte Mitarbeiter** (SW-Entwicklung, Architektur, QA, Doku, Recherche, Marketing, Content, E-Commerce …), von Jarvis koordiniert.
- **Self-Improvement-Meilenstein:** Jarvis analysiert sich selbst, schlägt priorisierte Verbesserungen vor, wir reviewen gemeinsam, ein Spezialist (Claude/Codex/…) setzt das **Freigegebene** um — Jarvis ändert sich nie eigenständig.
- **Wirtschaftliches Nordstern-Ziel:** Jarvis trägt zuerst seine eigenen Betriebskosten (Claude, API, Hosting), danach baut er mit an Produkten/Unternehmen. *(Etappenziel, bewusst nicht in der Verfassung.)*
- **Operative Leitfrage** für Roadmap-Entscheidungen: „Macht das Jarvis zu einem besseren digitalen COO?" (neben dem zeitlosen Verfassungsfilter „gibt das Souveränität zurück?").

**Langfristige Produktziele / Leitplanken (ADR-037, accepted — kein Umsetzungsauftrag):**
- **Distributierbarkeit:** Jarvis soll später als ZIP/Setup auf einem fremden Windows-Rechner laufen (z. B. der Bruder als Testnutzer), ohne die Entwicklungsumgebung des Autors — saubere Trennung Code/Konfig/Secrets/Nutzerdaten, portabler Start, API-Keys lokal eingerichtet. Künftige Entscheidungen dürfen nicht an die Autor-Umgebung binden.
- **Namens-/Branding-Entkopplung:** Produktidentität (Anzeigename, Logo, Wakeword, Bot-Anzeigename, Fenstertitel) zentral konfigurierbar; „Jarvis" bleibt Code-/Projektname. Rebranding ohne Fachlogik-Änderung möglich halten.

**Backlog (zurückgestellte Ideen, kein aktueller Scope — Grund je Zeile):**
- **`stop_jarvis` / Runtime-Kill-Switch (2026-07-06)** — es gibt aktuell keinen Jarvis-Befehl, der die laufende Runtime (`jarvis_runtime.py`, `pythonw`, headless) beendet: `shutdown_pc` fährt den ganzen PC herunter, `disable_jarvis_autostart` entfernt nur den Autostart-Registry-Eintrag (beendet den laufenden Prozess NICHT, siehe `commands/monitor.py`), Exit-Wörter greifen nur in einer Konsolen-Session. Kandidat für einen eigenen Command (Sicherheitsstufe 2 mit Bestätigung, sauberer Runtime-Stopp) — eigenes, getrennt freizugebendes Arbeitspaket, kein Teil von ADR-034/035.
- **Backend-Entkopplung `commands/delegate.py` (ADR-036): erledigt (2026-07-08).** Der Command nennt kein konkretes Backend mehr — es wird aus der Verdrahtungsschicht injiziert (`main.py`/`jarvis_runtime.py`), der Anzeigename kommt aus `AgentBackend.name`. Damit ist die **Modellunabhängigkeits-Invariante aus ADR-036 vollständig geschlossen** (keine Modell-/Werkzeugnamen mehr in der Fachlogik). Erster voll geschlossener „Vorschlag→Umsetzung"-Kreis: `plan_next_step` hatte genau diesen Schritt selbst vorgeschlagen.
- **Spotify-/Medien-Steuerung** — kein echtes Arbeitsproblem.
- **Wake-Word** (z. B. Porcupine) — aktuell reicht „jarvis" im Text; nach der Nutzwert-Phase erneut prüfen. (Lokale Modelle/Ollama siehe oben „Spätere v0.8-Phasen".)
- **Power-BI-Integration** — liegt im Firmenumfeld/auf dem Firmenrechner; im privaten Jarvis-Rahmen aktuell nicht praktikabel.
- **Generalisierung der Post-Arbeitsmodule** → allgemeine Excel-/Report-Analyse — die bestehenden Commands bleiben bewusst spezifisch, bis mehrere Report-Typen es rechtfertigen (Regel 6).
- **Fernzugriff-Ausbau** (Web-Interface, VPN) — Alternativen/Ergänzungen zu Telegram, aktuell nicht nötig.

Im Code wurden keine `TODO`-/`FIXME`-Marker gefunden.

## Latest Architecture Change
**Erste Orchestrierungs-Kette (`plan_next_step`, ADR-036 / Handbook 4.2):** Neuer Command `commands/plan.py` — Jarvis liest read-only den eigenen Projektstand und schlägt EINEN nächsten Entwicklungsschritt in fester Struktur vor (Empfehlung + Risiken + ADR-/Governance-Prüfung), legt den Entwurf additiv unter `memory_data/proposals/` ab und setzt nichts um (Governance-Invariante). Damit wird die read-only Analyse (ADR-034/035) zum Werkzeug einer Kette mit Ziel. Wichtige Eigenschaften: der Agent bleibt strikt read-only (den Entwurf schreibt Jarvis selbst — additiv, kein Überschreiben, kein Code, strukturell garantiert); die Fachlogik nennt kein konkretes Backend (ADR-036, injiziert aus der Verdrahtungsschicht); ehrlicher „kein sinnvoller Schritt"-Fall statt erzwungenem Vorschlag; Async-Pfad der Runtime (ADR-035) für einen zweiten `long_running`-Command wiederverwendet, die Quittung dafür generisch gemacht.

Davor - **Erste asynchrone Hintergrund-Ausführung (ADR-035, Scheibe 2):** Die `JarvisRuntime` besitzt neben dem seriellen Nachrichten-Worker jetzt einen von ihr verwalteten **Hintergrund-Worker** für langlaufende (`long_running`) Commands - die read-only Repo-Analyse. Ein Kanal opt-in per `submit(..., allow_async=True)` (nur der Telegram-Runtime-Kanal); der Command signalisiert Async über das Attribut `long_running` (kein hartkodierter Intent-Name). Ablauf: sofortige Quittung → Hintergrund-Thread → Ergebnis-Push über denselben `reply_callback` (Telegram bleibt reiner Transportkanal, ADR-027-Entkopplung gewahrt). `core/agent_backend.py` nutzt jetzt `subprocess.Popen` + `cancel_event` (echter Kill-Switch beim `runtime.stop()`, Abbruch-Präzedenz natürlich>Cancel>Timeout); `memory/store.py` serialisiert seine JSON-Zugriffe per RLock (Delegations-Thread + Nachrichten-Worker schreiben parallel). Nebenläufigkeit bewusst = 1 (Busy-Flag, kein Scheduler). Executor-Kern und `AIEngine`-Schnittstelle unverändert.

Davor - **Zweiter externer Connector (ADR-032, Nutzwert-Phase):** neuer `commands/web.py` mit read-only Websuche über `core/web_search.py` (stdlib, DuckDuckGo-Lite-Suche) und sichtbaren Quellen. Der Connector ist jetzt in `main.py`, `telegram_main.py` und `jarvis_runtime.py` verdrahtet; Telegram erlaubt `search_web` als sicheren read-only Intent. Nach dem Live-Fund einer DuckDuckGo-Bot-Challenge auf der alten HTML-Route wurde bewusst auf die Lite-Suche umgestellt; Bot-/Captcha-Seiten werden jetzt explizit als Fehler gemeldet, und DuckDuckGo-interne Werbe-/Hilfstreffer werden aus der finalen Trefferliste gefiltert. `telegram_channel.py` zerlegt lange Antworten zusaetzlich in Telegram-sichere Teilnachrichten, statt bei ueberschiessender Laenge still zu scheitern. Trotz zweitem Dienst bewusst noch KEINE generische Connector-Abstraktion: Mail und Web teilen noch kein tragfähiges gemeinsames Interface. `core/ai.py` erhielt nur eine kleine Intent-Klarstellung für `search_web`; Executor-Kern und `AIEngine`-Schnittstelle bleiben unverändert.

Davor - v0.8 „Multi-KI", Phase 1+2 (ADR-029/030): Die KI-Anbindung ist nicht mehr fest an OpenAI gebunden. `AIEngine` delegiert den rohen Modellaufruf an einen austauschbaren `LLMProvider` (`core/providers.py`, OpenAI/Claude), gewählt über `config.ai_provider`. Ein deterministischer `ProviderRouter` erlaubt pro Aufgabentyp (`get_plan`=PLANNING, `answer`=GENERATION) einen eigenen Provider (`planning_provider`/`answer_provider`, Rückfall auf `ai_provider`), mit Fallback auf den Standardprovider. Öffentliche `AIEngine`-Schnittstelle und alle Aufrufer unverändert; `confirmed`-Strip zentral. Details: ADR-029, ADR-030.

## Known Limitations
- Claude-Provider im Prompt-JSON-Modus (Phase 1, ADR-029): keine strukturierte Ausgabe/Tool-Use; ungültiges JSON fällt über das vorhandene `json.loads`-Fallback auf einen `chat`-Plan zurück (akzeptiertes Restrisiko).
- Langzeitgedächtnis funktioniert nur auf Zuruf; keine automatische Fakten-Extraktion.
- Mikrofon/Wake-Word weiterhin nicht umgesetzt.
- Kokoro TTS unterstützt aktuell kein Deutsch.
- `system_status`/`analyze_pc`: keine Temperatur (psutil-Limitierung unter Windows).
- `read_excel`/`analyze_report`/`calculate_kpi`: nur `.xlsx`/`.xlsm`, nur Werte, 500 Zeilen/Blatt.
- `search_web` (ADR-032): hängt an einer externen Suchseite, liest nur Trefferlisten (keine ganzen Artikel) und kann bei Markup-Änderungen, Bot-/Captcha-Schutz des Anbieters oder fehlender Internetverbindung ausfallen.
- `telegram_main.py`: nur sieben rein lesende/bestätigungsfreie Intents erreichbar (`chat`, `remember_fact`, `forget_fact`, `system_status`, `search_web`, `check_mail`, `show_mail_advertising`), kein gleichzeitiger Betrieb mit der Konsole, `TelegramSpeech.listen()` fail-closed (ADR-018). Das Mail-Briefing ist seit 2026-07-06 remote freigeschaltet (ADR-031-Nachtrag, PO-Entscheidung); die schreibenden Mail-Regel-Intents (`mail_hide_sender`/`mail_keep_sender`) bleiben bewusst lokal.
- `analyze_pc`/`analyze_event_log`/`disable_/enable_autostart_entry`/`analyze_/clean_temp_files`: alle Windows-exklusiv, jeweiliger Scope siehe die jeweiligen ADRs (ADR-020–023).
- `jarvis_runtime.py`: kein UI/Tray/Wake-Word, kein abstraktes Channel-Interface. `ConsoleDummyChannel` bleibt für unbeaufsichtigten Betrieb ungeeignet (blockiert auf `input()`) - wird beim Jarvis-Eigenstart (`pythonw.exe`) deshalb gar nicht erst gestartet; Telegram übernimmt die Erreichbarkeit.
- **Asynchrone Repo-Analyse (ADR-035):** **genau eine** gleichzeitige Delegation (bewusst einfaches Busy-Flag, kein Scheduler/keine Warteschlange) - eine zweite Anfrage wird abgelehnt, bis die erste fertig ist. Nur über den **Runtime-Telegram-Kanal** async erreichbar; der Standalone-Bot (`telegram_main.py`) lehnt `delegate_analysis` bewusst ab (kein Hintergrund-Worker). Kein pre-hoc Kosten-/Turn-Deckel (kein CLI-`--max-turns`); der Wall-Clock-Timeout ist der harte Guardrail, Kosten/Turns werden nur protokolliert. Kein hartes Prozess-Kill bei externem Prozessabbruch (nur der von `runtime.stop()` ausgelöste Kill-Switch).
- Single-Instance-Schutz (ADR-026) schützt nur vor gleichzeitigem *Prozessstart* gegen dasselbe `memory_dir` - kein Schutz gegen externes Löschen der Lock-Datei, während eine Instanz läuft (bekanntes, akzeptiertes Restrisiko).
- `telegram_main.py` (eigenständig) und `TelegramChannel` (über die Runtime) dürfen nicht gleichzeitig mit demselben Bot-Token laufen - Telegram erlaubt pro Bot nur eine aktive Long-Polling-Verbindung.
- Jarvis-Eigenstart (ADR-028): fester HKCU-Run-Key-Eintragsname `"Jarvis"` setzt eine einzige Installation pro Windows-Benutzerkonto voraus; veraltete Registry-Pfade nach Projekt-/Interpreter-Umzug werden nicht automatisch repariert (Selbstbedienung per erneutem `enable_jarvis_autostart`).

## Git
Die Commit-Historie wird hier nicht mehr gespiegelt — sie ist über `git log` und die getaggten Versionen (`v0.4`–`v0.7`) direkt ableitbar (Granularitäts-Leitplanke, Framework-Übernahme M2). Nicht aus Git ableitbar und deshalb hier festgehalten: Frühere Versionen (v0.1–v0.3) existieren nur als Text in `docs/CHANGELOG.md`/`docs/logbook.md`; `v0.8` ist bewusst nicht getaggt (Version nicht abgeschlossen, siehe „Current Version").
