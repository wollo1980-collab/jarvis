# Logbook

## 2026-07-06 - Machbarkeits-Check Agenten-Delegation + ADR-034 (vorgeschlagen)

**Machbarkeits-Check (PO-freigegeben, read-only, kostengedeckelt):** Geprüft, ob Claude Code als erstes Delegations-Backend headless nutzbar ist. Ergebnis positiv: `claude -p` läuft als Subprozess und liefert echte Antworten; **read-only nachweisbar** (Git-Status vor/nach leer, nur `Read`/`Grep`/`Glob` erlaubt); **Auth trägt über den Account-Login** (das anfängliche „Not logged in" lag nur am unfertigen Onboarding, in eigener Gegenprobe am normalen Terminal bestätigt und dann durch interaktiven Login gelöst). Kein zwingender bezahlter API-Key für den Grundlauf. Kosten praktisch null (winzige Prompts).

**Offene Caveats (im ADR adressiert):** OAuth-Token laufen ab → für unbeaufsichtigten Remote-Betrieb ist ein dedizierter `ANTHROPIC_API_KEY` die robustere Auth (vorgemerkt); harte Kosten-/Turn-/Timeout-Limits bleiben Pflicht; vor Produktivbetrieb ist zu verifizieren, dass `claude -p` auch aus Jarvis' `pythonw`-Prozess angemeldet ist.

**ADR-034 (vorgeschlagen):** Aufsatz auf ADR-033. Wählt Claude Code als erstes Backend und definiert die erste Fähigkeit: **read-only Repo-Analyse** — Command `delegate_analysis`, Sicherheitsstufe 0, Allowlist zunächst nur `C:\KI\jarvis`, lokal + Telegram, **asynchrone Übergabe** (Quittung → Hintergrundlauf → Ergebnis-Push + Artefakt), Auth zunächst über Account-Login (API-Key als Robustheits-Aufwertung vorgemerkt), Skizze eines `AgentBackend`-Kontrakts analog `LLMProvider`. `latest_adr` 33 → 34.

**Governance:** Neue ADR = 🟡. Kein Code. Die **Umsetzung** ist ein eigenes, getrennt freizugebendes Arbeitspaket - dieser ADR ist nur die Entscheidung. Reibungsprotokoll auf ADR-034 aktualisiert. Kein Commit vor Review + PO-Freigabe.

**Bewusst nicht:** Scheibe 2 (Schreiben/Fix), Multi-Agenten, Codex/GPT-Backends, Geräte-Ebene, jegliche Implementierung.

## 2026-07-06 - Modellunabhängiger Delegationsprozess entworfen (ADR-033, vorgeschlagen)

**Kontext:** In der Nutzwert-Phase hat der PO die Vision geschärft: Jarvis als **Vermittlungsschicht** über drei Ebenen (Informationen · Agenten · Geräte) und als erste Richtung den **Agenten-Arm** gewählt („während ich unterwegs bin, delegiert Jarvis Arbeit an Claude/Codex/GPT, fertig zum Review bei Rückkehr"). Bewusste Reihenfolge (PO-Wunsch): erst der modellunabhängige Delegationsprozess, dann Agentenwahl und ADR-Umsetzung - damit Agenten austauschbare Backends bleiben (Modellneutralitäts-Invariante).

**Umsetzung:** `docs/adr/ADR-033.md` (vorgeschlagen) hält den 9-Schritte-Lebenszyklus fest: Erfassen · Verstehen & Einstufen · **Priorisieren & Schneiden** · Zuordnen (modellneutral) · Eingrenzen & Freigeben · Ausführen & Beobachten · Verifizieren & Bewerten · Zurückgeben & Übergeben · Protokollieren & Abschließen. Der Schritt „Priorisieren & Schneiden" (auf PO-Wunsch ergänzt) zerlegt große/unklare Wünsche in kleine, reviewbare Arbeitspakete statt sie als Großauftrag zu delegieren. Kern-Erkenntnis: Der Prozess ist die **bestehende Pipeline verallgemeinert** - ein Agent ist eine neue Tool-Klasse, kein Parallelsystem (Evolution statt Revolution). Der ADR legt bewusst nur den Prozess fest, keinen Agenten und keine Fähigkeit.

**Governance:** Neue ADR = 🟡 (vorschlagen → Review → PO-Freigabe → Umsetzung). `latest_adr` 32 → 33; Reibungsprotokoll um die gewählte Richtung und das Drei-Ebenen-Modell ergänzt. Kein Code. Reibungsprotokoll-Kandidat für spätere Handbook-Teil-2-Schärfung (🔴).

**Bewusst nicht umgesetzt:** Agentenwahl, erste Fähigkeit/Scheibe, Backend-Protokoll als Code, Multi-Agenten, Geräte-Ebene. Kein Commit vor Review + PO-Freigabe.

**Lessons Learned:** „Vision breit, Roadmap klein" (Handbook) hat sich hier bewährt: Der PO hat die Vision mehrfach geschärft, aber die Umsetzung bewusst auf eine kleine erste Scheibe eingegrenzt - der Delegationsprozess ist der Kompass, nicht der Bauauftrag.

## 2026-07-06 - Live-Verifikation: Mail-Briefing über Telegram bestanden

**Kontext:** Der Telegram-Gegencheck aus Arbeitspaket B wurde vom PO durchgeführt: „was liegt an?" über Telegram funktioniert. Damit ist das Mail-Briefing jetzt **lokal (main.py) und remote (Runtime-Telegram-Kanal)** end-to-end real verifiziert.

**Bedeutung:** Baustein 1 der Nutzwert-Phase ist nicht mehr nur implementiert und getestet, sondern nachweislich in Betrieb - auf beiden aktiven Kanälen. Die entsprechenden Live-Test-TODOs in PROJECT_STATE (Mail-Gegencheck Telegram, Runtime-/Bot-Smoke-Test) sind geschlossen. Reine Doku-Aktualisierung (🟢), kein Code; Gate PASS.

**Lessons Learned:** Die Inbetriebnahme-vor-Features-Reihenfolge hat sich vollständig bewährt: Erst der Autostart-Fix, dann das Briefing lokal (Unicode-Fund), dann remote (Whitelist-/configure-Fund) - jeder Kanal deckte einen eigenen realen Defekt auf, den kein gemockter Test zeigen konnte.

## 2026-07-06 - Commit-Übergang 🟡 → 🟢 (Charter 1.3)

**PO-Freigabe am 2026-07-06 für die Charter-Änderung** (🔴, Meta-Governance §12; `charter_version` 1.2 → 1.3). Entscheidungen A (🔴-Commits bleiben ausdrücklich freizugeben) und B (gilt nur für Jarvis) vom PO bestätigt.

**Kontext:** Die Charter knüpfte den Commit-Übergang von 🟡 auf 🟢 an die Bedingung „Gate + Tests automatisch vor jedem Commit". Der Pre-Commit-Hook (`.githooks/pre-commit`) erfüllt das seit vier bewährten Läufen. Damit ist die N4-Absicht aus dem Audit eingelöst: Autonomie wächst genau dort, wo eine mechanische Leitplanke sie absichert.

**Umsetzung:** Vier Charter-Stellen geändert - Delegations-Matrix (§3: Commit von der 🟡- in die 🟢-Zeile), Commit-Status-Notiz (§3, neu formuliert + Auslösedatum), Änderungs-Lebenszyklus (§4), Git-Konventionen (§10). Zusätzlich der Begriff **„PO-Freigabe des Arbeitspakets"** eindeutig definiert (PO-Wunsch): Sie schließt die Commit-Freigabe ein - nach ihr ist keine zweite, separate Commit-Freigabe mehr nötig; ein bloßes „Review empfiehlt Freigabe" genügt nicht. Ausnahme: 🔴-Änderungen behalten die ausdrückliche Commit-Freigabe.

**Unverändert:** Selbstprüfung → unabhängiges Review → PO-Freigabe bleiben in jedem Fall Pflicht. Nur der separate zweite Schritt „Commit freigegeben" entfällt für 🟢-Arbeit.

**Selbstbezug:** Diese Charter-Änderung ist selbst eine 🔴-Änderung und wird deshalb - konsequent nach der neuen Ausnahme - noch mit ausdrücklicher Commit-Freigabe des PO committet. Der letzte Commit unter der alten Regel schaltet die neue scharf.

**Tests:** Reine Doku-/Governance-Änderung, kein Code. Konsistenz-Gate PASS, Vollsuite unverändert grün.

**Lessons Learned:** Der sauberste Zeitpunkt, Autonomie zu gewähren, ist der, an dem sie mechanisch abgesichert ist - nicht früher (Vertrauen ersetzt keine Leitplanke) und nicht später (sonst bleibt die Handbremse Ritual ohne Nutzen).

## 2026-07-06 - Mail-Briefing über Telegram freigeschaltet (Arbeitspaket B, Nutzwert-Phase)

**Kontext:** Der Telegram-Gegencheck aus Arbeitspaket A wurde abgelehnt („Anfrage abgelehnt wegen Phase 1") - korrektes Verhalten: `check_mail` war nie in der Telegram-Whitelist. Der PO hat daraufhin entschieden, das rein lesende Briefing remote freizuschalten (Nutzwert > Datenschutz-Trade-off), bewusst als eigenständiges Paket B statt als Nachtrag zu A. Scope + Intent-Auswahl vorab vorgelegt, von Reviewer und PO freigegeben.

**Umsetzung:** `telegram_main.ALLOWED_INTENTS` um `check_mail` und `show_mail_advertising` erweitert (rein lesend, Stufe 0). Beim Check fiel auf: `mail_commands.configure()` lief bisher nur in `main.py` - eine reine Whitelist-Zeile wäre ins Leere gelaufen. Deshalb `mail_commands.configure(config)` in `telegram_main.py` (Bridge) und `jarvis_runtime.py` (Runtime-Stack) nachgezogen, analog zum Web-v1-Muster. `telegram_channel.py` importiert die Whitelist aus `telegram_main` (ADR-027) und propagiert automatisch. Die schreibenden Regel-Lern-Intents bleiben bewusst lokal.

**Governance:** ADR-031-Nachtrag mit explizit abgewogenem Datenhoheit-Trade-off und PO-Freigabe. Bycatch dabei: Der ADR-031-Status stand noch auf „Vorgeschlagen (wartet auf Freigabe)", obwohl das Briefing seit 2026-07-03 umgesetzt und produktiv ist - auf `Accepted` korrigiert und im Status transparent vermerkt. Kein Handbook-Eingriff (Stufe 0 bleibt im Fernzugriff-Prinzip).

**Tests:** 4 neue Tests - Whitelist-Grenze (Briefing-Intents erreichbar, Regel-Intents blockiert) und Verdrahtungs-Anker in beiden Remote-Pfaden. Die Briefing-Logik selbst bleibt in `test_commands_mail.py` abgedeckt und wird durch die Bridge unverändert genutzt; bewusst nicht dupliziert. Vollsuite 373/373 grün, Gate PASS.

**Bewusst nicht umgesetzt:** Schreibende Mail-Intents remote, Hotmail, TTS. Live-Verifikation (Telegram-„was liegt an?") ist ein PO-Schritt nach dem Commit.

**Lessons Learned:** Eine Whitelist-Freischaltung ohne die zugehörige `configure()`-Verdrahtung ist ein stiller Fehlschlag - der Scope-Check „wo wird der Command eigentlich konfiguriert?" hat das vor der Umsetzung sichtbar gemacht statt erst im Live-Test.

## 2026-07-06 - Mail-Briefing in Betrieb genommen (Arbeitspaket A, Nutzwert-Phase)

**Kontext:** Baustein 1 der Nutzwert-Phase (Mail-Briefing „Was liegt an?", ADR-031) war seit dem 03.07. implementiert und getestet, aber nie real gelaufen - das Gmail-App-Passwort fehlte. PO-Auftrag: das Briefing in echten Betrieb nehmen und dabei die drei offenen Web-v1-Restfälle mit abhaken. Bewusster Scope: Inbetriebnahme, keine neuen Features.

**Umsetzung:** `mail_accounts` in `config.json` (nur nicht-geheime Felder; App-Passwort ausschließlich per `setx JARVIS_GMAIL_APP_PASSWORD`). End-to-End-Lauf über `main.py`: **Mail-Briefing lief zum ersten Mal live** - echte Gmail-IMAP-Verbindung (read-only), 2 wichtige Mails erkannt, 48 Werbe-/Newsletter-Mails ausgeblendet. Direkt anschließend `search_web` live: 5 echte Treffer, KI-Überblick mit sichtbaren Quellen.

**Live-Fund + Fix:** Der erste echte Lauf stürzte an einem `UnicodeEncodeError` ab - das Executor-Häkchen U+2713 ist auf einer cp1252-Konsole nicht kodierbar, und `core/speech.py::say()` gibt die Antwort per `print()` aus. Minimal behoben mit `main.make_console_output_safe()` (stdout/stderr auf `errors="replace"`), zwei neue Tests in `tests/test_main.py`. Bewusst klein: keine Änderung an `speech.py`, kein erzwungenes UTF-8 (auf reiner cp1252-Konsole erscheint das Häkchen jetzt als `?` statt zu crashen).

**Web-v1-Restfälle (ADR-032) abgeschlossen:** lokaler `main.py`-Lauf (vorher nur Telegram/Runtime), Timeout-/Nichterreichbar-Fall (sauberer `WebSearchError` verifiziert), schwache Trefferlage (DuckDuckGo liefert selbst für Unsinns-Queries Treffer - die Ehrlichkeit liegt korrekt beim Zusammenfassungs-Prompt).

**Tests:** Vollsuite 369/369 grün (2 neue Konsolen-Härtungstests), Konsistenz-Gate PASS. Runtime nach dem Test wieder headless gestartet (PID-Wechsel, Telegram-Kanal aktiv), damit der Nutzer-Gegencheck über Telegram möglich ist.

**Bewusst nicht umgesetzt:** Hotmail-Auth (erst wenn Gmail im Alltag trägt), Claude-Live-Call, TTS, neue Funktionen. Kein Commit vor Review/Freigabe (Arbeitspaket-Regel).

**Lessons Learned:** Ein Feature gilt erst als in Betrieb, wenn es einmal an der Realität war - nicht wenn seine Tests grün sind. Der Unicode-Crash war in 346+ gemockten Tests unsichtbar und trat in der ersten echten Sekunde auf. Genau dafür ist die Inbetriebnahme-vor-Features-Reihenfolge da.

## 2026-07-06 - Audit-Follow-up: Commit-Leitplanken, Review-Spur und Doku-Nachzug

**Kontext:** Ein externes Jarvis-Audit auf Stand `d63c2e6` bescheinigte dem Produkt einen starken Realzustand, markierte aber eine klare Governance-Luecke auf Git-/Commit-Ebene: vier getrennte Arbeitspakete waren in einem Sammelcommit gelandet, obwohl das logbook die Entscheidungs- und Freigabekette sauber vorbereitet hatte. Dazu kamen kleinere Doku-Inkonsistenzen (ADR-032 ohne Fernzugriffs-Nachtrag, Web-Live-Test-TODO zu pauschal, offene Sprachschuld ohne Heimat, `stand` nicht nachgezogen). **Audit (Claude, 2026-07-06):** Befunde F1-F6, keine Blocker; Empfehlung GO fuer den Follow-up-Commit mit drei kleinen Auflagen (basetemp-Umlenkung fuer Sandbox-Umgebungen, datierter ADR-Status-Nachtrag, saubere Audit-/Review-Trennung in dieser Spur). PO-Freigabe fuer das Follow-up liegt vor. Fuer dieses Follow-up bewusst **kein** History-Rewrite des Sammelcommits `d63c2e6`, sondern nur Vorwaerts-Korrekturen. (Rollen-Hinweis: Reviews liefert ChatGPT, Audits liefert Claude; Umsetzung und Commit dieses Follow-ups erfolgen durch Claude in der Codex-Rolle - PO-Entscheidung 2026-07-06.)

**Umsetzung:** Die mechanische Leitplanke aus der Charter wurde eingelöst: `pytest.ini` setzt ein repo-lokales `--basetemp`, und `.githooks/pre-commit` fuehrt vor jedem Commit das Konsistenz-Gate plus Vollsuite aus. `README.md` dokumentiert den vereinfachten Testlauf und die Hook-Aktivierung. `ADR-032` traegt jetzt explizit nach, dass `search_web` als read-only Intent ueber Telegram/Runtime freigeschaltet ist. `PROJECT_STATE.md` hebt `stand` auf den aktuellen Commit-Tag, praezisiert den Web-Live-Test auf die real offenen Restfaelle und fuehrt die offene Sprachschuld (`monitor.py`, `reports.py`, `excel.py`) sichtbar. `commands/web.py` bekam zusaetzlich eine kleine Prompt-Haertung: Web-Treffer werden explizit als Daten, nicht als Anweisungen markiert. Fuer den Framework-Rueckfluss ergaenzt `docs/framework_feedback.md` jetzt die zwei gelebten Pattern „Nutzungslauf vor Abschluss" und „Bewusster Abschluss vor Ausbau" als n=2-Datenpunkt.

**Tests:** Geplanter Verifikationssatz: `.\.venv\Scripts\python.exe -m pytest -q`, `.\.venv\Scripts\python.exe scripts\check_consistency.py` und ein direkter Lauf des neuen `.githooks/pre-commit`.

**Bewusst nicht umgesetzt:** Kein Rewrite oder Split des historischen Sammelcommits `d63c2e6`. Keine Charter-Aenderung fuer eine neue Review-Regel - das logbook dient hier bewusst als erste feste Review-Spur, ohne gleich die Governance erneut aufzuschrauben. Kein Live-Mail-Test; der bleibt weiterhin der aelteste echte Betriebsrest.

**Lessons Learned:** Gute Governance scheitert selten an der Einsicht, sondern an der letzten mechanischen Leitplanke. Sobald Commit-Hygiene nur als Dokumentregel lebt, faellt sie im Nutzungstempo zurueck. Ein kleiner Hook ist hier wertvoller als eine weitere Mahnung. Und: Review ist erst dann auditierbar, wenn sein Ergebnis im Repo selbst auffindbar ist.

**Review (ChatGPT, 2026-07-06):** Freigeben - die Umsetzung bleibt innerhalb des freigegebenen Scopes, die Audit-Follow-ups wurden sauber umgesetzt, keine zusaetzlichen Baustellen eroeffnet. Beobachtungspunkt: das Hook-Verhalten wird in den naechsten Commits im Dogfooding beobachtet. **PO-Freigabe des Commits `3ed4473` am 2026-07-06.** Damit ist der erste vollstaendige Durchlauf des Vier-Rollen-Modells dokumentiert: Implementierung (Claude in Codex-Rolle), Audit (Claude), Review (ChatGPT), Entscheidung (PO).

## 2026-07-06 - Web v1 als zweiter Connector integriert

**Kontext:** Nach Mail war der naechste kleine Nutzwert-Baustein nicht noch mehr Struktur, sondern eine reale Alltagshilfe fuer aktuelle Informationen. Wolfgangs Auftrag war direkt: `web v1 integrieren`. Gleichzeitig war das die erste Stelle, an der Jarvis' Modellneutralitaet praktisch zaehlt: Web durfte nicht still an OpenAI-Tooling gekettet werden, nur weil es technisch bequem waere.

**Umsetzung:** `core/web_search.py` fuehrt die eigentliche read-only Websuche lokal und provider-neutral ueber die DuckDuckGo-Lite-Suche aus. `commands/web.py` bildet daraus den neuen Command `search_web`, der Treffer holt, einen kurzen Ueberblick formulieren laesst und die Quellen immer sichtbar mitliefert. `main.py` verdrahtet den Connector, `commands/__init__.py` registriert ihn, `core/ai.py` bekam nur eine kleine Intent-Klarstellung fuer Web-/Recherche-Anfragen. Nach dem ersten Live-Check des Produktstands wurde der Connector direkt noch in die aktiven Fernzugriffspfade nachgezogen: `telegram_main.py` konfiguriert Web fuer den eigenstaendigen Bot, `jarvis_runtime.py` fuer den geteilten Runtime-Stack, und die Telegram-Whitelist erlaubt jetzt auch `search_web`. Spaeterer Live-Fund am echten Telegram-Pfad: Die urspruengliche DuckDuckGo-HTML-Route lieferte haeufig eine Bot-Challenge statt Trefferliste; deshalb wurde auf die funktionierende Lite-Suche umgestellt und die Challenge-Erkennung explizit als Webfehler verankert. Zweiter Live-Fund: Preisabfragen wie `PS5 Preis` zogen extrem lange DuckDuckGo-Werbe-/Tracking-URLs in die Quellenliste, wodurch Telegram-Antworten still scheitern konnten. Deshalb filtert `core/web_search.py` jetzt DuckDuckGo-interne Werbe-/Hilfstreffer aus der finalen Trefferliste, und `telegram_channel.py` zerlegt lange Antworten in sichere Teilnachrichten und loggt Sendefehler sichtbar. Dritter Live-Fund: Bei `Wie teuer ist die Switch 2 aktuell?` plante die KI nur `Switch 2` statt einer Preis-Suche. Deshalb ergaenzt `commands/web.py` fehlende Preis-/Verfuegbarkeits-Hinweise jetzt gezielt selbst und fokussiert die Zusammenfassung in solchen Faellen explizit auf Preis bzw. Verfuegbarkeit. Die Architektur blieb bewusst flach: kein Browser, keine generische Connector-Basis, keine neue KI-Methode.

**Tests:** Neue Parser- und Command-Tests plus Prompt-Integrationstest. Nach der Telegram-/Runtime-Nachverdrahtung kamen noch zwei Kanal-Regressionsanker dazu. Geplanter Verifikationssatz: `tests/test_web_search.py`, `tests/test_commands_web.py`, relevanter `test_ai.py`-Ausschnitt, `tests/test_telegram_main.py`, `tests/test_jarvis_runtime.py` und Konsistenz-Gate.

**Bewusst nicht umgesetzt:** Kein Oeffnen von Treffern, keine Browser-Steuerung, keine Extraktion ganzer Seiten, kein provider-spezifischer OpenAI-Web-Shortcut, keine Connector-Abstraktion trotz zweitem Dienst.

**Lessons Learned:** Der zweite Connector erzwingt nicht automatisch die richtige Abstraktion. Entscheidend ist nicht die Anzahl der Dienste, sondern ob bereits ein belastbares gemeinsames Interface sichtbar ist. Bei Mail und Web war das noch nicht der Fall.

## 2026-07-06 - Jarvis-DNA aus dem Prompt in die ersten Alltagsantworten gezogen

**Kontext:** Nach der PO-Freigabe vom 2026-07-05 war die Produkt-DNA zwar in Verfassung und Chat-System-Prompt verankert, die konkret sichtbaren Antworten mehrerer Kern-Commands klangen aber weiterhin generisch-technisch. Damit bestand das Risiko, dass Jarvis in der Konversation ruhig und kontrolliert wirkt, im operativen Alltag jedoch wie ein uneinheitlicher Werkzeugkasten spricht.

**Umsetzung:** Erste direkte Nutzerantworten in `commands/__init__.py`, `commands/memory.py`, `commands/system.py`, `commands/installer.py` und `commands/mail.py` wurden sprachlich an die definierte Haltung angeglichen: ruhiger, praeziser, kontrollierter, ohne Ueberschwang. Der Eingriff blieb bewusst oberflaechennah: keine neue Logik, keine Aenderung am Prompt, keine Architekturarbeit. Bestehende Tests wurden nur dort geschaerft, wo Formulierungen nun bewusst Teil des Produkts sind.

**Tests:** Geplanter Verifikationssatz: gezielte Command-Tests plus Konsistenz-Gate. Testzaehler bleibt unveraendert, weil nur bestehende Tests erweitert wurden.

**Bewusst nicht umgesetzt:** Kein Vollausbau ueber alle Commands. Vor allem `monitor.py`, `reports.py` und `excel.py` bleiben fuer einen spaeteren, getrennten Sprachdurchlauf offen. Keine TTS-/Stimmenarbeit, kein Wake-Word, kein Commit.

**Lessons Learned:** Produktpersoenlichkeit wird erst dann glaubwuerdig, wenn sie an den banalen Stellen sichtbar wird: Rueckfragen, Erfolgsmeldungen, Fehlertexte. Ein guter System-Prompt allein reicht dafuer nicht.

## 2026-07-05 - PO-Freigabe: Jarvis-DNA nicht als Prompt, sondern integriert

**Kontext:** Wolfgang hat fuer Jarvis explizit eine Anlehnung an den Film-Jarvis gewuenscht - nicht als lose Prompt-Spielerei, sondern als integrierten Teil des Produkts. Der bestehende `CHAT_SYSTEM_PROMPT` enthielt bereits eine leichte Richtung (hoeflich, loyal, trockener Humor), die Verfassung trug diese Produkt-DNA jedoch noch nicht explizit genug. Dadurch blieb die Persoenlichkeit eher eine Implementierungsnotiz als eine stabile Produkteigenschaft. **Governance-Einordnung:** Rot, weil die Projektverfassung geaendert wird (`constitution_version` 4.0 -> 4.1); PO-Freigabe liegt vor.

**Umsetzung:** `docs/handbook/HANDBOOK.md` beschreibt Auftreten und Tonfall jetzt ausdruecklich als Teil der Produktidentitaet: ruhig, praezise, souveraen, loyal, funktionale Eleganz statt Show, trockener Humor nur dezent, offene Benennung von Unsicherheit. `core/ai.py` wurde darauf angeglichen; der Chat-System-Prompt transportiert diese Haltung jetzt klarer und vermeidet explizit leere Begeisterung und Chatbot-Ueberschwang. Der bestehende Test in `tests/test_ai.py` wurde auf die geschaerfte DNA erweitert. `PROJECT_STATE.md` und `CHANGELOG.md` wurden auf den neuen Verfassungsstand nachgezogen.

**Tests:** Geplanter Verifikationssatz: gezielter Lauf `tests/test_ai.py` plus Konsistenz-Gate. Keine neue Testfunktion, Testzaehler bleibt unveraendert.

**Bewusst nicht umgesetzt:** Keine breitflaechige Umformulierung aller lokal erzeugten Nutzertexte, keine Aenderung an Mail-/Command-Templates, keine TTS-/Stimmenarbeit, kein Wake-Word, kein Commit.

**Lessons Learned:** Produktpersoenlichkeit gehoert in die Verfassung und in die zentrale Antwortlogik - nicht als freistehender Prompt neben dem Produkt. Erst wenn Haltung und Implementierung dieselbe Quelle haben, wird Persoenlichkeit belastbar statt zufaellig.

## 2026-07-05 - PO-Entscheidung: erste Nutzwert-Reibung abgeschlossen, naechste kleine Funktion darf kommen

**Kontext:** Die erste reale Nutzwert-Reibung der Nutzwert-Phase war der nicht mehr funktionierende Jarvis-Autostart nach der Projektumstrukturierung. Nach Ursachenanalyse, minimalem Pfadfix und realem Live-Smoke-Test ist diese Reibung jetzt erfolgreich **end-to-end verifiziert**. Gleichzeitig zeigte der bewusste Nutzungslauf: Der aktuelle Funktionsumfang ist noch so begrenzt, dass aus der taeglichen Nutzung keine weitere grosse Reibung entstanden ist.

**Umsetzung:** Die PO-Aussage wurde als Produkt-/Scope-Entscheidung fuer die laufende Nutzwert-Phase in `PROJECT_STATE.md` nachgezogen. Autostart gilt nicht mehr als offener Betriebs-TODO. Der Fokus wechselt von reiner Inbetriebnahme/Beobachtung auf die **Auswahl der naechsten kleinen Nutzwert-Funktion** innerhalb des bestehenden Blocks. **Governance-Einordnung:** keine ADR, weil keine Architekturentscheidung und kein neuer Increment-Rahmen, sondern eine dokumentierte Scope-Fortschreibung innerhalb der laufenden Nutzwert-Phase.

**Tests:** Keine Code-Aenderung. Konsistenz-Gate nach Doku-Update: PASS.

**Bewusst nicht umgesetzt:** Noch keine Auswahl oder Implementierung der naechsten Funktion, kein neuer Connector-Beschluss, kein Commit.

**Lessons Learned:** Ein Nutzungslauf kann auch dann erfolgreich sein, wenn er *keine* neue grosse Reibung hervorbringt. In einer fruehen Produktphase ist das ein Signal fuer begrenzten Funktionsumfang - und rechtfertigt bewusst den naechsten kleinen Nutzwert-Baustein statt erzwungen weiterem Dogfooding ohne neues Material.

## 2026-07-05 - Bugfix: repo-gebundene Pfadauflösung fuer Runtime und Autostart

**Kontext:** In der Nutzwert-Phase fiel im echten Benutzerkontext auf, dass die headless Runtime bei Autostart unter `C:\Users\wollo\logs` und `C:\Users\wollo\memory_data` schrieb. Die Ursachenanalyse zeigte: `config.json` wird zwar repo-gebunden geladen, aber `core/config.py` übernahm relative Werte fuer `memory_dir` und `log_dir` bisher unveraendert als `Path(...)`. Dadurch wurden sie implizit gegen das aktuelle Working Directory statt gegen `BASE_DIR` aufgeloest. **Governance-Einordnung:** gruener Bugfix, keine ADR (CONTRIBUTING §3/§5).

**Umsetzung:** In `core/config.py` loest ein kleiner Helper relative Config-Pfade jetzt explizit gegen `BASE_DIR` auf. Absolute Pfade bleiben unveraendert. Es gab bewusst keine Aenderung an der Autostart-Mechanik selbst, keine direkte Registry-Behandlung und keine Runtime-Architektur-Aenderung.

**Tests:** Neue Tests decken relative und absolute Pfade in `Config.load()` ab. Zusaetzlich wurde der bestehende End-to-End-Test `test_end_to_end_tool_execution` plattformneutral stabilisiert, damit die Vollsuite unter Windows denselben Codepfad wie der Produktcode nutzt (`os.startfile` statt eines POSIX-Mocks). Vollsuite 348/348 gruen, Gate PASS.

**Bewusst nicht umgesetzt:** Keine direkte Registry-Aenderung, keine Aenderung an `jarvis_runtime.py`, keine neuen Config-Optionen, kein Auto-Migrationspfad fuer bestehende absolute Nutzerpfade, kein Commit.

**Lessons Learned:** Eine repo-gebundene Config-Datei erzeugt noch kein repo-gebundenes Verhalten. Sobald Pfadwerte relativ bleiben, entscheidet der Prozesskontext. Gerade fuer headless Starts muss die Pfadauflösung deshalb explizit an `BASE_DIR` gebunden werden.

## 2026-07-04 - Produktfokus: Inbetriebnahme vor Features

**PO-Entscheidung am 2026-07-04.** Jarvis wird ab jetzt nicht mehr primär als Architekturprojekt betrachtet, sondern als Produkt, das in den Alltag kommt - vom Projekt zum täglichen Begleiter.

**Entschiedene Reihenfolge der Nutzwert-Phase:** (1) Live-Inbetriebnahme der offenen realen Pfade, (2) eine Woche echte Nutzung mit Reibungsprotokoll ohne neue Features, (3) danach genau eine größte Reibung als nächstes Nutzwert-Inkrement.

**Bewusst ausgeschlossen für diese Phase:** Framework-Ausbau, Architektur auf Vorrat, Feature-Breite. Leitgedanke: Außergewöhnlich heißt nicht viele Funktionen, sondern zuverlässig, loyal und täglich nützlich (HANDBOOK Teil 1, Leitplanke 9).

**Offen bleibende separate Pakete:** M3 README-Body-Chunk (eigene Freigabe) · `.git_broken_5`-Löschung (PO-Entscheid) · M4 passive Pattern-Bewährung (beim nächsten Baustein-Abschluss anwenden).

Keine Code-Änderung; PROJECT_STATE-Fokus entsprechend präzisiert. Gate PASS.

## 2026-07-04 - Migration M1+M2: Assoziierte Angleichung an das AI Project Framework v1.0

**PO-Freigabe am 2026-07-04 für den Migrationsplan** (M1 = Charter-Änderung = 🔴, `charter_version` 1.1 → 1.2).

**Kontext:** Das AI Project Framework — ursprünglich aus Jarvis extrahiert — liegt nach zwei Härtungswellen und einem validierenden Greenfield-Dogfooding (Prompt Manager v1.0) als v1.0 vor. Die Delta-Analyse ergab: ~80 % Deckungsgleichheit; eine Vollmigration scheitert prinzipiell nur an der AI_GUIDELINES-Pflicht (dort ADR-001, hier ADR-010 — beide gültig). Gewählter Migrationstyp: **assoziierte Angleichung** — bewusste Einzelübernahmen, formaler Austauschkanal, dokumentierte Abweichungen.

**Umgesetzt (M1, Charter 1.2):**
- Neuer §15 „Austausch mit dem AI Project Framework": Rückfluss über `docs/framework_feedback.md`, Framework-Übernahmen nur bewusst per Freigabe, Abweichungsregister (AI_GUIDELINES/ADR-010, Zwei-Rollen-Modell, Reinheits-Check, Struktur/Namen).
- Konflikt-Hierarchie um die Charter ergänzt (`HANDBOOK > CONTRIBUTING > ADR > Code > README`).
- §5: Testinfrastruktur-Abgrenzung (erstmalige Einführung 🟡/ADR, weitere Tests 🟢) — Framework-Erkenntnis FF-006.
- §6: Routinepflege von PROJECT_STATE ausdrücklich 🟢, Struktur-/Feld-/Regeländerungen 🟡 — Framework-Erkenntnis aus dem Dogfooding.
- §7: WARN- und SKIP-Semantik prozessual normiert (stand bisher nur im Gate-Skript).
- §11: Sicherheitsgetriebene Versionssteuerung innerhalb freigegebener Abhängigkeiten als Korrektur mit Nachfreigabe + ADR-Nachpflege — Framework-Erkenntnis FF-005.
- §1: PERSONAL_DEVELOPMENT in die Dokument-Landkarte aufgenommen (offener Welle-0-Restpunkt).

**Umgesetzt (M2):**
- PROJECT_STATE „## Git": manuelle Commit-Spiegelung entfernt (aus `git log` ableitbar); nur nicht-ableitbare Fakten bleiben. Granularitäts-Leitplanke aus Framework-PROJECT_INIT.
- `docs/framework_feedback.md` angelegt mit FF-J-001 (PROJECT_INIT deckt Bestandsprojekt-Adoption nicht ab — die Lücke, die diese Migration selbst aufdeckte) und FF-J-002 (Reinheits-Check als laufender Datenpunkt).

**Bewusst NICHT migriert (Abweichungsregister, §15):** AI_GUIDELINES-Einführung · Vier-Rollen-Modell · Entfernung des Reinheits-Checks · Struktur-/Namensangleichungen. **Offen als eigene Pakete:** M3 README-Body-Chunk (vor dem nächsten Nutzwert-Baustein) · `.git_broken_5`-Löschung (separater PO-Entscheid) · M4 passive Pattern-Bewährung (beim nächsten Increment-Abschluss die Framework-Pattern-Kandidaten „Bewusster Abschluss" und „Nutzungslauf" bewusst anwenden und vermerken → möglicher n=2-Rückfluss).

**Lesson:** Ein Bestandsprojekt migriert man nicht auf ein Framework — man gleicht bewusst an und macht die Differenz sichtbar. Das Abweichungsregister verwandelt Divergenz von einem stillen Risiko in einen gepflegten Zustand.

Gate PASS vor und nach den Änderungen; Suite unverändert (reine Doku-Änderungen).

## 2026-07-04 - Welle 0: Doku-Realitäts-Korrekturen aus dem Architektur-Audit

**PO-Freigabe am 2026-07-04 für Welle 0** (enthält eine Charter-Korrektur = 🔴, `charter_version` 1.0 → 1.1).

**Kontext:** Ein unabhängiges Architektur-Audit (Jarvis gegen das AI Project Framework, 03./04.07.2026) fand in Jarvis drei Doku-Realitäts-Drifts, die das Gate nicht erkennen kann, weil es Zahlen und Tokens prüft, aber keine Prosa-Behauptungen.

**Umsetzung:**
- **Echter Testsuite-Lauf:** 346/346 grün (venv-Interpreter, `--basetemp`, 4,9 s). Die Kopfzahl `tests: 346` war bisher nur statisch gezählt (Gate zählt `def test_`-Definitionen), nie durch einen dokumentierten echten Lauf dieser Session verifiziert.
- **`active_increment`:** `governance-rebuild` → `nutzwert-phase` korrigiert (der Umbau ist laut logbook Chunk 5 abgeschlossen; der laufende benannte Block ist die Nutzwert-Phase). `stand` auf 2026-07-04.
- **Charter §5 Seed-ADR-Angabe:** Die Behauptung „Frühe Seed-ADRs (ADR-000–003) liegen ebenfalls als Dateien in `docs/adr/`" wurde per Git-Historie geprüft: Seit dem Initial-Commit (v0.4) wurden ausschließlich ADR-004 bis ADR-031 getrackt; keine weitere Erwähnung im Repo; `.git_broken_5/` enthält nur Hook-Templates, keinen Objektbestand. Die Aussage war falsch und wurde durch die belegbare ersetzt (ADR-Reihe beginnt bei ADR-004; v0.1–v0.3 nur als Text in CHANGELOG/logbook überliefert).

**Tests:** 346 grün (echter Lauf, s. o.). Gate PASS vor und nach den Änderungen.

**Bewusst nicht umgesetzt (außerhalb der Welle-0-Freigabe):** README-Body-Chunk (bekannte Schuld, eigenes Paket) · `PERSONAL_DEVELOPMENT.md` in die Landkarte §1 aufnehmen · Löschung von `.git_broken_5/` (destruktiv, separate PO-Rückfrage). Keine neuen Architekturfragen während der Umsetzung aufgetreten.

**Lesson Learned:** Prosa-Behauptungen in Governance-Dokumenten (Seed-ADR-Satz) und die Aktualität benannter Blöcke (`active_increment` akzeptiert jeden Namen) liegen außerhalb des mechanisch Prüfbaren — sie brauchen periodische manuelle Audits als bewussten Konsolidierungsschritt.

## 2026-07-03 - Verifikations-/Korrektur-Chunk: Doku-Kette nach dem Governance-Umbau bereinigt

**PO-Freigabe am 2026-07-03.**

**Umgesetzt:** Vorwärts-Zeiger auf verschobene Inhalte korrigiert. PROJECT_STATE: „Handbook v3.8 aktuell" → HANDBOOK.md (constitution_version 4.0); veraltete Selbstbeschreibung (Roadmap/Backlog „im Handbook") an CONTRIBUTING §1 angeglichen; DoD-Verweise → CONTRIBUTING §8; Scope-/Detail-Verweise → jeweilige ADRs; Erfolgsmarke-Zitat → HANDBOOK Teil 1/Leitplanke 9 (Roadmap-Substanz unverändert). README: Fernzugriff-Sicherheitsprinzip → HANDBOOK Teil 6 / ADR-019.

**Bewusst NICHT geändert:** README-Feature-/Historie-Tags (Kap. N) — nutzerseitige Doku/Historie, lösen sich ins klar markierte Archiv auf, teils roadmap-nah → eigener README-Body-Chunk. PROJECT_STATE-Konsolidierungshistorie (Kap. 1/7/26/32) als Historie belassen. Historie in logbook/CHANGELOG/ADRs unangetastet.

Gate PASS; Suite 346 grün.

## 2026-07-03 - Governance-Umbau, Chunk 5: Struktur-Generator + README Variante B (Umbau abgeschlossen)

**PO-Freigabe am 2026-07-03** für Chunk 5.

**Umgesetzt:** Generischer `scripts/gen_structure.py` (stdlib, `root`-Parameter, reine `build_tree`, als Projekt-Template wiederverwendbar) leitet die Projektstruktur aus dem Repository ab. README auf Variante B: keine handgepflegte Baumgrafik mehr, Verweis auf den Generator + kurzer Bereichs-Überblick (Begründung im Diff). Vier migrationsbedingt erledigte Schuld-Notizen aus PROJECT_STATE entfernt (EBENE-2-Audit, Struktur-Doppelpflege, .docx→Markdown, v3.5-Fußzeile). 4 Tests, Suite 346 grün.

**Selbstprüfung (Lesson):** cp1252-`UnicodeEncodeError` an den Baumzeichen im Demo-Lauf gefunden → `main()` erzwingt UTF-8-Ausgabe, bevor Freigabe.

**Offen für die finale Konsolidierung:** PROJECT_STATE nennt noch „Handbook v3.8" statt HANDBOOK.md v4.0 (inhaltlich, bewusst außerhalb Chunk 5).

Gate PASS; No-Loss per Substanz-Checkliste. Governance-Umbau damit abgeschlossen.

## 2026-07-03 - Governance-Umbau, Chunk 4: Roadmap/Backlog → PROJECT_STATE, Lessons → logbook, Feature-Matrix → CONTRIBUTING

**PO-Freigabe am 2026-07-03** für Chunk 4 (enthält eine CONTRIBUTING-Änderung = 🔴).

**Umgesetzt:** Offener Backlog (Kap. 29) nach PROJECT_STATE (v0.x-Bezüge gestrippt); die überholte PROJECT_STATE-Zeile „Roadmap/Backlog leben im Handbook (Kap. 13/29)" korrigiert (Roadmap/Backlog leben jetzt hier). Feature-Entscheidungsmatrix (Kap. 29) als „Feature-Entscheidung" nach CONTRIBUTING §4. Frühe Lessons Learned (Kap. 25) hierher übernommen (siehe unten). Kap. 13 Roadmap + Kap. 27 Now/Next/Later = erledigte v0.1–v0.7-Historie, **bewusst NICHT** erneut übernommen (steht in CHANGELOG).

**Frühe Lessons (aus Handbook Kap. 25, v0.1/v0.2-Zeit):**
- `pyttsx3.init()` wurde bei jedem Sprechen neu initialisiert (langsam) → einmalig global initialisieren.
- `chat_verlauf` war definiert, aber nie verwendet → Jarvis hatte kein Gedächtnis; Variablen müssen auch benutzt werden.
- Modellname „gpt-5.5" existierte vermutlich nicht → Modellnamen immer in der API-Dokumentation prüfen.
- Architecture Astronautics: zu früh zu viele leere Ordner → erst anlegen, wenn wirklich gebraucht (Regel 6).

Gate PASS; No-Loss per Substanz-Checkliste.

## 2026-07-03 - Governance-Umbau, Chunk 3: PERSONAL_DEVELOPMENT.md (persönliche Entwicklung ausgelagert)

**PO-Freigabe am 2026-07-03** für Chunk 3. Neue Datei `PERSONAL_DEVELOPMENT.md` = 🟡/Doku (kein Verfassungs-/Charter-Dokument).

**Umgesetzt:** Persönliche/karrierebezogene Inhalte aus dem archivierten Handbook (Kap. 8 Lernpfad, 22 Academy, 23 Portfolio, 24 Karriere + Kap.-0-„Gesamtbild") in ein eigenes, zeitloses Entwicklungs-/Karrierehandbuch überführt. Karrierepipeline bewusst als **Vision** (keine Reihenfolge/Termine).

**Bewusst weggelassen:** Versions-/Statuskopplungen (Tab.-5-„v0.x"-Spalte, Tab.-15-„Jarvis bekommt"+✅, Tab.-17-Projektliste), Modellvergleich (technische Entscheidung → ADR/PROJECT_STATE), Lessons-Learned-Tabelle (→ logbook, Chunk 4). Zwei persönliche Lernprinzipien bewusst als *Lernhaltung* belassen (kein HANDBOOK-Verweis — PO-Entscheidung: unterschiedliche Zielsetzung der Dokumente reicht als Trennung). Gate PASS; No-Loss per Substanz-Checkliste.

## 2026-07-03 - Governance-Umbau, Chunk 2: CONTRIBUTING absorbiert dauerhafte Prozessregeln

**PO-Freigabe am 2026-07-03** für Chunk 2. CONTRIBUTING-Änderung = 🔴 (Charter): Entscheidung/Freigabe PO, Entwurf/Umsetzung Engineer.

**Umgesetzt:** Dauerhafte Arbeitsregeln aus den archivierten Handbook-Prozesskapiteln (2/3/5/14/15/19/20/21/28) nach CONTRIBUTING überführt — Konflikt-Hierarchie (§1), Entscheidungs-Prozeduren 30-Min-Regel + Design-Review (§4), ADR-Format (§5), CHANGELOG-/logbook-Format + Konsolidierungsprozess (§6), „keine offenen TODOs" (§8), Git-Präfixe + kleine lauffähige Commits (§10), neue Sektion Coding Standards (§14).

**Bewusst NICHT übernommen** (Status/Roadmap/überholt): versions-spezifische DoD-Checklisten, konkrete Commit-Reihenfolgen, v3.X→v0.Y-Kopplung, „nur zwischen Versionen"/„neue Handbook-Version je Hauptversion" (im Governance-Umbau gelockert), GPT-Mentor/Claude-Reviewer-Zuordnung (durch rollenbasiertes §0 abgelöst), AI_START als Pflichtdoku (superseded).

**Keine Dopplung:** Neue Subsections spezifizieren Format/Struktur; bestehende §6-Pflichten unverändert. §5 verweist auf §6, §14 verweist auf HANDBOOK (Betriebsprinzipien nicht dupliziert). `pyproject.toml`-Verweis in §14 auf PO-Wunsch entfernt (kein realer Projektstandard). Gate PASS (inkl. Handbook-Reinheit). No-Loss über Substanz-Checkliste je Kapitel nachgewiesen.

## 2026-07-03 - Governance-Umbau, Chunk 1: Handbook nach Markdown migriert + konsolidiert (constitution_version 4.0)

**PO-Freigabe am 2026-07-03** für Chunk 1. Handbook-Migration = 🔴 (Verfassungsebene): Entscheidung/Freigabe PO, Entwurf/Umsetzung Engineer.

**Umgesetzt:** `docs/handbook/HANDBOOK.md` neu (Markdown, maßgeblich), von 32 Kapiteln auf **7 Teile** konsolidiert (Leitbild & Identität · Vision & Fähigkeitsbereiche · Produkt-Leitplanken · Engineering-/Design-Prinzipien · Architektur-Invarianten · Sicherheitsmodell · Projektgrenzen) + Präambel + neue Invariante **Modellneutralität**. Bewusste Konsolidierung statt 1:1; keine Status-/Roadmap-/Prozessinhalte mehr. Die 7 bisherigen `.docx` (v3.2–v3.8) nach `docs/handbook/archive/` (`git mv`, nicht gelöscht). Verweise in README/PROJECT_STATE auf `HANDBOOK.md` umgestellt. Gate PASS inkl. jetzt aktiver **Handbook-Reinheit**.

**No-Loss:** Substanz-Checkliste pro Quell-Kapitel → Ziel (Verfassung bzw. spätere Chunks) vor der Migration erstellt und gegen den Entwurf geprüft.

**Lesson (Migration):** Kern-Verfassungsinhalte (Sicherheitsstufen 0–4, Design Principles, Gedächtnis-Ebenen, Executor-Status ✓/✗/?) standen in **Tabellen** — die python-docx-Absatz-Extraktion überspringt Tabellen. Ohne separate `doc.tables`-Extraktion wäre der wichtigste Inhalt verloren gegangen. Bei künftigen `.docx`-Migrationen immer Tabellen mitlesen.

**Nächste Chunks:** 2 (CONTRIBUTING absorbiert Prozessinhalte), 3 (PERSONAL_DEVELOPMENT), 4 (PROJECT_STATE/logbook: Roadmap + Lessons), 5 (`gen_structure.py`).

## 2026-07-03 - Governance-Umbau, Schritt 1: Developer Charter (CONTRIBUTING.md, charter_version 1.0)

**PO-Freigabe am 2026-07-03** für die Erstellung der Developer Charter. Charter-Erstellung ist 🔴 (Meta/Verfassungsebene): Entscheidung/Freigabe durch den PO, Entwurf/Umsetzung durch den Engineer.

**Inhalt:** einzige Quelle für *wie* an Jarvis entwickelt wird — Rollen (Entscheidung PO / Umsetzung Engineer), Dokument-Landkarte + Grenzregeln, Session-Runbook, Delegations-Matrix (🟢/🟡/🔴, Commit vorerst 🟡), ADR-Pflicht-Kriterien, Doku-Pflichten, Konsistenz-Gate-Konzept, DoD, Sicherheits-Gate, Entrenchment, Governance-Version. Ersetzt AI_START als Prozess-Heimat (AI_START wird noch abgelöst).

**Selbstprüfung vor Freigabe (Lesson/Arbeitsweise):** Zwei driftbare Status-Zeilen (Frontmatter + §7: „Gate ausstehend/noch nicht erstellt") gegen die eigene Grenzregel „kein driftbarer Status im Gesetz-Dokument" erkannt und in neutrale Zeiger auf PROJECT_STATE umformuliert, **bevor** die Freigabe erfolgte. Diese proaktive Selbstprüfung gegen die Governance ist ab jetzt fester Bestandteil der Arbeitsweise (PO-Wunsch).

**Kontext:** Schritt 1 des Governance-Umbaus. Vereinbarte Reihenfolge: CONTRIBUTING → PROJECT_STATE-Kopf → README-Verweis → Konsistenz-Gate → Handbook-Migration (mit Relocation-Map). Strikt in dieser Reihenfolge, keine Schritte vorziehen.

## 2026-07-03 - Nutzwert-Phase, Baustein 1: Mail-Briefing „Was liegt an?" (ADR-031)

**Kontext:** Erste dogfooding-getriebene Alltagsreibung, umgesetzt nach ADR-031.
Erster externer Connector. Auswahl bewusst: private Mail (eigene Daten,
unbedenklich) statt der teureren Firmendaten-Kandidaten (#3/#4 wegen
Arbeitgeber-Freigabe zurückgestellt).

**Umgesetzt:** `commands/mail.py` (check_mail / show_mail_advertising /
mail_hide_sender / mail_keep_sender, alle Stufe 0), `core/mail_reader.py`
(imaplib/email stdlib, strikt read-only via `select(readonly=True)`+`BODY.PEEK`,
nur Kopfzeilen), `memory/mail_rules.py` (lokale, korrigierbare Absenderregeln,
Regel schlägt Heuristik). `mail_accounts` in Config (Secrets per Env, ADR-018).
`core/ai.py` unangetastet - Intent über die Registry.

**Design-Entscheidungen (decken sich mit ADR-031):**
- Lokal-first: nur Kopfzeilen, **kein Mailinhalt an eine KI**; nur der Befehl
  „was liegt an" geht wie immer durch get_plan.
- „Lernen" = transparente, korrigierbare Regeln (kein ML/Blackbox) - der Nutzer
  korrigiert, Jarvis merkt es lokal, die Regel gewinnt immer (Leitplanke 8).
- „Ausblenden ≠ wegwerfen": Werbung wird gezählt/zusammengefaltet, nie stumm
  verworfen (schützt vor False Positives der Heuristik).
- Werbung-Signal primär `List-Unsubscribe`; bewusst konservativ (kein `info@`),
  damit legitime Absender nicht fälschlich gefiltert werden.

**Lesson (Umsetzung):** Typografische Anführungszeichen (`„…"`) in
f-Strings - das schließende ASCII-`"` beendete den String vorzeitig
(SyntaxError). In Message-Strings nun einfache `'…'` verwendet. Beim Schreiben
deutscher Strings darauf achten.

**Tests:** 21 neue (Read-only-Nachweis via gemocktem imaplib, MIME-Decode,
Regel-Vorrang, Zusammenfalten, Korrektur, fail-safe bei Kontofehlern).
**327/327 grün.**

**Offen (bewusst):** Live-Test mit echtem Gmail-App-Passwort auf Windows;
Hotmail-Auth verifizieren (Microsoft baut Basis-Auth ab); später Telegram/TTS.

## 2026-07-03 - Doku-Abgleich + v3.8-Korrektur (Lesson: EBENE 1 trägt keinen Status)

Ein zweiter Agent hat Code und Handbook geprüft und zwei Drift-Funde gemeldet.
(1) PROJECT_STATE/README/AI_START waren auf altem Stand → abgeglichen (Commit
`1f7c516`). (2) **Interner Handbook-Widerspruch**: Kap. 7 (EBENE 1) behauptete
„Provider-Router in v0.8 Phase 1/2 umgesetzt", Kap. 13 (EBENE 2) sagte „v0.8
noch nicht begonnen" - eingeführt durch meine v3.8-Konsolidierung.

**Lesson Learned:** EBENE 1 (zeitlos) darf **keine** Implementierungs-/Phasen-
Status-Aussage tragen - das gehört in EBENE 2 / ADRs / PROJECT_STATE. Ein
zeitloser ADR-Verweis ist ok, ein „umgesetzt in Phase X" nicht. Behoben durch
in-place-Korrektur von v3.8 (Kap. 7 zeitlos umformuliert); Kap. 13 bewusst
nicht angefasst (Product-Owner-Entscheidung: nur den Widerspruch fixen).

**Root Cause (beide Funde):** manuell gepflegte, binäre, nicht diffbare
`.docx`-SSoT ist für einen Solo-Maintainer schwer konsistent zu halten; Drift
bleibt unsichtbar, bis jemand liest. Als Schuld notiert (Markdown-SSoT prüfen),
bewusst aufgeschoben. Ebenso aufgeschoben: EBENE-2-Ist-Stand-Audit (Kap.
12/13/22/23) - nicht in der Nutzwert-Phase.

## 2026-07-03 - Handbook v3.8: Leitbild / DNA verankert (die „Verfassung" von Jarvis)

**Kontext:** Nach der Umsetzung von v0.8 Phase 1/2 verschob sich die Diskussion
von Features zur *Identität*. In einer mehrstufigen Produkt-/Architektur-
Diskussion (02.-03.07.2026) wurde die zeitlose DNA von Jarvis erarbeitet und
vom PO final bestätigt ("Das ist unsere Verfassung"). Dann als EBENE-1-
Konsolidierung ins Handbook (v3.8) gehoben.

**Kern-Identität (als Haltung, bewusst KEIN Rollen-Substantiv):** „Jarvis steht
auf der Seite seines Nutzers und ist allein dessen Interesse verpflichtet. Er
sieht und ordnet aus eigenem Antrieb - und handelt nur, wenn der Mensch es ihm
aufträgt." Essenz: einem *einzelnen* Menschen die Souveränität über seine
digitale Welt zurückgeben; der Wert ist die Loyalität, nicht die (austauschbare)
Intelligenz; "für alle da vs. für einen da".

**Drei Formulierungs-Feinschliffe (PO-getrieben, zeitloser):**
- „dient ausschließlich dessen Interesse" -> „ist **allein** dessen Interesse
  **verpflichtet**": bindet den *Adressaten* der Pflicht (nur ihm, keinem
  Anbieter), nicht den *Umfang* des Handelns; Grenzen/Recht/Missbrauch leben in
  Leitplanke 1/4, Kap. 10 und den Nicht-Zielen.
- „die Intelligenz ist gemietet" -> „austauschbar und an kein bestimmtes Modell
  gebunden" (weg vom heute-gebundenen Geschäftsmodell-Bild).
- „Gegner ist die Fragmentierung" -> „Jarvis *begegnet* der Fragmentierung …"
  (neutrale Problembeschreibung statt Kampfmetapher; passt zum SSoT-Register).

**Umgesetzt (erweiterter Umfang, PO-Entscheidung):** Kap. 0 Leitbild + 9
Produkt-Leitplanken (Mission unverändert); Kap. 1 Vision-Erweiterung; Kap. 7
Orchestrator-Disambiguierung (Modell- vs. Service-Ebene); Kap. 26 Loyalitäts-
Differenzierer; Kap. 32 Nicht-Ziele gefüllt (u.a. Multi-User als eigene, spätere
Produktentscheidung). Frontmatter v3.8 + Kap. 2 Versionszeile.

**Governance-Ausnahme (bewusst, dokumentiert):** Handbook-Änderung mitten in
v0.8 berührt die Regel „nur zwischen Versionen" (Kap. 2). Zulässig eingeordnet,
weil reine EBENE-1-/Identitäts-Konsolidierung ohne Auswirkung auf die technische
Code-Basis; der PO hat die Ausnahme ausdrücklich bestätigt. Der Ausnahmevermerk
steht im v3.8-Änderungsblock.

**Technik/Verifikation:** neue Datei `JARVIS_MASTER_HANDBOOK_v3_8.docx` (v3.7
bleibt Historie), python-docx, anker-basierte Einfügung. 450 -> 476 Absätze
(+26; 27 eingefügt, 1 alter Änderungslisten-Absatz entfernt). Mission, Kap. 10
und Kap. 12 unverändert verifiziert.

## 2026-07-02 - v0.8 Multi-KI, Phase 2: Minimaler Provider-Router (Umsetzung nach ADR-030)

**Kontext:** Zweiter v0.8-Baustein. Nach Phase 1 (ein Provider pro Lauf) soll
Jarvis pro Aufgabentyp einen Provider verwenden koennen - deterministisch,
ohne zweite KI, ohne zusaetzlichen LLM-Call. Architektur in ADR-030
festgehalten (committet `f35f0f7`).

**Umgesetzt (nach ADR-030):**
- `core/providers.py`: `TaskType` (PLANNING/GENERATION) + `ProviderRouter`
  (deterministische Weiche `TaskType -> Provider-Name`, plus Auswahlgrund
  `regel`/`default`) + `build_router(config)`. `build_provider` in
  `build_named_provider(name, config)` refaktoriert (konstruiert per Name);
  `build_provider(config)` delegiert weiter auf `ai_provider`.
- `core/ai.py`: `AIEngine` haelt Provider-Cache + Router. `get_plan` ->
  PLANNING, `answer` -> GENERATION (interner `_chat`-Helfer). Standardprovider
  eager (Anker), Nicht-Default lazy. `_chat` faellt bei nicht verfuegbarem/
  werfendem gerouteten Provider **nur fuer diesen Aufruf** auf den
  Standardprovider zurueck (WARNING). Fallback umschliesst nur `chat()` -
  JSON-Parsing, confirmed-Strip und die bestehenden get_plan/answer-Fallbacks
  bleiben unveraendert. `self.provider` bleibt der oeffentliche Default-/
  Fallback-Provider (Phase-1-Tests unveraendert gruen).
- `core/config.py` + `config.example.json`: `planning_provider`,
  `answer_provider` (leer -> `ai_provider`, rueckwaertskompatibel).

**Bewusste Grenzen (Design-Entscheidungen, decken sich mit ADR-030):**
- Routing-Signal ist ausschliesslich der intern gesetzte `TaskType` - **kein**
  Routing nach Intent (ist Ergebnis von get_plan) oder Sicherheitsstufe (erst
  im Executor bekannt). Nie von Modell-Output beeinflusst -> keine neue
  Trust-Boundary-Flaeche.
- `answer()` bedient Konversation UND Analyse (monitor/reports) ueber denselben
  `GENERATION`-Typ; eine feinere `ANALYSIS`-Trennung bliebe Phase 3.
- Router ist eine Nachschlagetabelle, **kein** Orchestrator (bewertet/lernt
  nichts, nichts parallel).

**Tests:** Router-Unit-Tests (Auswahl + Grund, `build_router`, Rueckwaerts-
kompatibilitaet) in `tests/test_providers.py`; AIEngine-Routing/Fallback in
`tests/test_ai.py` (Planning/Generation zum gerouteten Provider, Fallback bei
Konstruktions- und bei `chat()`-Fehler, confirmed-Strip greift auch nach
Fallback, Logging ohne Prompt-/Antwort-Inhalte). **306/306 gruen** (venv,
beschreibbares `--basetemp`; Sandbox blockiert sonst den System-Temp der
`tmp_path`-Fixture, kein Testdefekt).

**Bewusst NICHT (spaetere Phasen):** LLM-Routing, Intent-/Sicherheitsstufen-
Routing, `ANALYSIS`-Trennung, Laufzeit-Override, Ollama/lokale Modelle, MCP,
RAG, Multi-Agent, paralleles Ausfuehren, Streaming, Handbook-Uebernahme (erst
Konsolidierung nach v0.8).

## 2026-07-02 - v0.8 Multi-KI, Phase 1: technisch abgeschlossen (Product-Owner-Abschluss)

**Status:** Phase 1 ist **technisch abgeschlossen**. Der volle Stand wurde
noch einmal gegen ADR-029 (alle 7 Entscheidungen + Konsequenzenliste) und
Handbook v3.7 (Kap. 7 Multi-KI-Vision, Kap. 13 Roadmap) geprueft - Scope
vollstaendig erfuellt: Provider-Abstraktion (`LLMProvider`) als Backend in
`AIEngine`, `OpenAIProvider` + `ClaudeProvider`, explizite Auswahl nur per
`config.ai_provider`, `anthropic` lazy/optional, `confirmed`-Strip zentral.
Kein Aufrufer ausserhalb `core/ai.py`/`core/providers.py`/`core/config.py`
angefasst. Tests: 294 gruen + Offline-Rauchtest gegen die reale anthropic-SDK
(0.116.0) via httpx-MockTransport (Request-Parameter inkl. `thinking`, ohne
`temperature`; Antwort-Parsing/Text-Extraktion) - alle Checks gruen.

**Bewusst verschoben (kein offener Implementierungsfehler):** Der **Live-
Claude-Smoke-Test** (echter API-Call mit gesetztem `ANTHROPIC_API_KEY`) ist
ein manueller Verifikationsschritt und wird ausdruecklich auf einen spaeteren
Zeitpunkt verschoben. Kein Code-/Architektur-Defekt - der Pfad ist offline bis
zur SDK-Grenze verifiziert; nur der bezahlte End-zu-End-Call gegen die
Anthropic-API steht noch aus. Fertiges Skript liegt bereit (Scratchpad,
`claude_smoke_live.py`), liest den Key ausschliesslich aus der Umgebung.

**venv:** `anthropic` (0.116.0) bleibt im `.venv` installiert. `requirements.txt`
bleibt unveraendert - `anthropic` dort weiterhin optional/auskommentiert
(lazy Import), damit OpenAI-only-Setups ohne das Paket lauffaehig bleiben
(ADR-029).

**Bewusst NICHT Teil von Phase 1 (bleibt spaetere v0.8-Phasen):** Auto-
Routing/Orchestrator, Scoring/Bewertung, Multi-Agent, lokale Modelle (Ollama),
MCP, RAG, Laufzeit-Umschaltung des Providers.

## 2026-07-02 - v0.8 Multi-KI, Phase 1: Provider-Abstraktion + Claude (Umsetzung nach ADR-029)

**Kontext:** Start von v0.8 „Multi-KI". Product-Owner-Phasenschnitt: **nicht**
mit Auto-Routing beginnen, sondern zuerst die Provider-Abstraktion + einen
zweiten echten Provider (Claude/Anthropic), explizit per Config wählbar. Die
Architektur ist in ADR-029 festgehalten (committet `5291cd3`).

**Umgesetzt (nach ADR-029):**
- `core/providers.py` (neu): `LLMProvider`-Protokoll
  (`chat(system, messages, *, json_mode=False) -> str`) + `OpenAIProvider`
  + `ClaudeProvider` + `build_provider(config)`. Beide SDKs werden lazy im
  Konstruktor importiert; `anthropic` ist optional (bleibt nicht installiert),
  fehlendes Paket oder fehlender Key → früher, klarer `RuntimeError`.
- `core/ai.py`: `AIEngine` delegiert den rohen Aufruf an `self.provider`
  (statt `self.client = OpenAI(...)`). Prompt-Bau, JSON-Parsing, Fallbacks und
  der **`confirmed`-Strip** bleiben zentral in `AIEngine` - genau der Grund,
  weshalb der Provider ein Backend ist und **keine** zweite Engine-Klasse
  (Sicherheits-Invariante nur an einer Stelle). Öffentliche Schnittstelle
  (`get_plan`/`answer`) unverändert → kein Aufrufer angefasst.
- `core/config.py`: `ai_provider` (Default `openai`), `claude_model`
  (`claude-sonnet-5`), `anthropic_api_key` aus `ANTHROPIC_API_KEY` (Env-only,
  ADR-018). `config.example.json`, `requirements.txt` (optionales `anthropic`)
  ergänzt.

**Claude-Spezifika (Lessons/Entscheidungen):** system als eigener
`system=`-Parameter (Anthropic-Konvention, nicht als `messages[0]`);
`thinking={"type":"disabled"}`; **kein** `temperature` (Sonnet 5 lehnt
non-default Sampling mit 400 ab); JSON-Modus in Phase 1 nur per
Prompt-Instruktion, kein Structured-Output/Tool-Use - das bestehende
`json.loads`+Fallback in `get_plan` fängt ungültige Antworten
providerunabhängig ab.

**Tests:** `tests/test_providers.py` (neu): Request-Bau/Text-Extraktion beider
Provider, `json_mode`, fehlender Key/fehlendes `anthropic`, `build_provider`-
Auswahl - `anthropic` per `sys.modules` gemockt. `tests/test_ai.py` von
`client.chat.completions.create` auf `provider.chat` umgestellt + Test, dass
`get_plan` `json_mode=True` anfordert. **294/294 grün.**

**Sandbox-Notiz:** Volle Suite nur mit venv-Interpreter
(`.venv/Scripts/python.exe`) und beschreibbarem `--basetemp` grün - die
Sandbox blockiert sonst den System-Temp der `tmp_path`-Fixture
(`WinError 5`); kein Testdefekt.

**Bewusst NICHT (bleibt spätere v0.8-Phasen):** Auto-Routing/Orchestrator,
Scoring, Multi-Agent, Ollama/lokale Modelle, MCP, RAG, Laufzeit-Umschaltung.

## 2026-07-02 - Sicherheits-Fix: Modell kann Bestaetigung nicht mehr faelschen (confirmed-Flag)

**Kontext:** Sicherheitsanalyse (auf Anforderung) der Ausfuehrungskette
Planner -> get_plan -> Plan -> Executor -> Command. Befund: `get_plan`
(`core/ai.py`) uebernahm `parameters` ungefiltert aus dem Modell-JSON; der
Executor (`executor.py:114`) und `shutdown_pc` (`system.py:95`) entscheiden
anhand von `parameters["confirmed"]`, ob eine Stufe-2/3-Bestaetigung schon
erfolgt ist. Ein vom Modell geliefertes `confirmed=true` (z. B. per
Prompt-Injection) haette die Bestaetigung - inkl. Stufe-3-Phrase -
uebersprungen. Bewertung: echter Trust-Boundary-Defekt, aktuell niedrig
ausnutzbar (lokal nur Wolfgangs eigene Eingabe; Telegram per Whitelist
gesperrt), aber gegen Safety First - Fix jetzt (billig, Roadmap macht es
real, sobald untrusted Content in get_plan fliesst).

**Product-Owner-Entscheidung:** Variante 1 - Minimal-Fix am Trust Boundary.

**Umgesetzt:** `core/ai.py` - `get_plan()` entfernt `confirmed` aus den
Modell-`parameters` (`parameters.pop("confirmed", None)`), defensiv nach
einer isinstance-dict-Normalisierung. Einzige legitime `confirmed`-Quelle
bleibt der Executor nach echter Rueckfrage. KEINE Aenderung an Plan-Modell,
Executor oder Commands (per `git diff` verifiziert - `core/models.py`,
`executor/*`, `commands/*` unberuehrt).

**Tests:** 3 neue in `tests/test_ai.py`: (1) gefaelschtes `confirmed` wird
entfernt, andere Parameter bleiben; (2) normale `parameters` bleiben
unveraendert; (3) Ende-zu-Ende - gefaelschtes `confirmed` kann die
Executor-Bestaetigung nicht umgehen, echte Bestaetigung (`listen="ja"`)
funktioniert weiter. 285/285 gruen.

**Bewusst offen/entschieden:** Die `confirmed`-Auswertung in `system.py:95`
bleibt als echte zweite Schicht bestehen (liest jetzt nur noch einen nie
faelschbaren Wert). Variante 2 (dediziertes `Plan.confirmed`-Feld,
strukturelle Trennung) wurde bewusst nicht gewaehlt. Keine ADR. Die separat
analysierte Runtime-Bestaetigung fuer lokale Kanaele bleibt eigener,
offener Baustein.

## 2026-07-02 - Sicherheits-Fix: Bot-Token nicht mehr im Log

**Kontext:** Beim manuellen Runtime-Test (`python jarvis_runtime.py`) fiel im
Log auf, dass `httpx` jeden Telegram-Request-URL auf INFO protokolliert -
inkl. Bot-Token im Pfad (`api.telegram.org/bot<TOKEN>/...`). Da
`setup_logging()` den Root-Logger via `basicConfig` auf INFO setzt, landete
der Token im Klartext in Logdatei UND Konsole. (Derselbe Testlauf bestaetigte
zudem, dass Stufe-2-Commands wie `enable_jarvis_autostart` ueber die
fail-closed Runtime-Kanaele nicht bestaetigbar sind - eigene, noch offene
Design-Entscheidung, siehe unten.)

**Behoben (nur die zwei Telegram-relevanten Einstiegspunkte):**
- `jarvis_runtime.py` und `telegram_main.py`: neue Helper-Funktion
  `_dampen_http_loggers()`, aufgerufen am Ende von `setup_logging()` - hebt
  `httpx` und `httpcore` auf `WARNING`, bewusst auch im Debug-Modus (ein
  Secret gehoert nie ins Log). `WARNING` zeigt echte HTTP-Fehler weiterhin.
- `main.py` unveraendert (kein Secret im URL - OpenAI-Key liegt im Header).
- Je ein Sicherheitstest in `tests/test_jarvis_runtime.py` und
  `tests/test_telegram_main.py` (httpx/httpcore auf WARNING nach
  setup_logging, Logger-Level sauber gesichert/wiederhergestellt). 282/282
  gruen.
- `git diff`: nur `jarvis_runtime.py`, `telegram_main.py` und die zwei
  Testdateien - `core/*`, `executor/*`, `commands/*`, `memory/*`, `main.py`,
  `telegram_channel.py` unberuehrt.

**Bereinigt (Betrieb, ausserhalb Git):** Die zwei Logdateien mit sichtbarem
Token geloescht (`logs/2026-07-02-runtime.log` mit 60, `logs/2026-07-02-telegram.log`
mit 46 Token-Vorkommen). `logs/` ist gitignored und war nie in Git - der Token
war also nie committed. Die zwei `main.py`-Konsolenlogs waren token-frei und
blieben erhalten. Empfehlung an Wolfgang: den bereits exponierten Token beim
@BotFather rotieren.

**Noch offen (bewusst NICHT in diesem Fix):** Haertung des aktuell aus
KI-Output faelschbaren `confirmed`-Flags (core/ai.py -> executor.py) sowie eine
saubere Runtime-Bestaetigung fuer lokale Kanaele - separate Bausteine mit
eigener Freigabe (Analyse liegt vor). Fuer produktive Stufe-2/3-Aktionen bleibt
`main.py` der funktionierende lokale Pfad; Remote-Bestaetigung (Telegram) bleibt
per Kap. 10 gesperrt.

**Vorheriger Schritt am selben Tag** (bereits committed, `af83614`):
TelegramChannel-Shutdown thread-/eventloop-konform gemacht (stop() plant
stop_running() via loop.call_soon_threadsafe ein) - behob den
`RuntimeError: no running event loop` beim Beenden der Runtime.

## 2026-07-02 - Konsolidierung auf Handbook v3.7 (Infrastruktur-/Runtime-Baustein)

**Kontext:** Der gesamte Infrastruktur-/Runtime-Baustein zwischen v0.7 und
v0.8 war abgeschlossen und committed (Jarvis-Runtime v1 `95e5af9`,
Single-Instance-Schutz `987ed0b`, Runtime v2/TelegramChannel `7f9ccb8`,
Jarvis-Eigenstart `3fc13e1`; ADR-024 bis ADR-028). Wolfgang gab den zuvor
erstellten Konsolidierungsplan frei - mit zwei Anpassungen: (1) KEIN
verpflichtender Volltext-Diff v3.6->v3.7, stattdessen eine kurze
Schlusspruefung, dass ausschliesslich die vorgesehenen Kapitel geaendert
wurden; (2) Kapitel 12 (Projektstruktur) bleibt bewusst unveraendert
(Scope-Vermeidung fuer die bekannte Veraltung).

**Governance-Grundlage:** Handbook Kap. 2/19 - der Konsolidierungsprozess
gilt seit v3.7 ausdruecklich auch fuer einen abgeschlossenen, in Kap. 13
benannten Infrastruktur-/Runtime-Baustein ohne eigene vX.Y-Versionsnummer
(diese Klarstellung wurde im Rahmen der Konsolidierung selbst ins Handbook
uebernommen).

**Durchgefuehrt (nur Dokumentation, kein Code, keine neue ADR):**
1. **Handbook v3.7 erstellt** (`docs/handbook/JARVIS_MASTER_HANDBOOK_v3_7.docx`,
   v3.2-v3.6 bleiben Archiv): Titelseite auf 3.7; „Aenderungen in v3.7";
   Kap. 2 (Versionsliste + v3.7-Zeile + Infrastrukturbaustein-Klausel);
   Kap. 7 neuer Abschnitt „Runtime & Kanaele" (dauerhafte Runtime-
   Architektur); Kap. 10 Fernzugriff-Prinzip um Runtime-Telegram ergaenzt;
   Kap. 13 „Jarvis-Runtime & Jarvis-Eigenstart (abgeschlossen)"; Kap. 17
   System-Analyst-Vision praezisiert; Kap. 19 Konsolidierungsprozess-Klausel;
   Kap. 27 „Praezisierung v3.7"; Kap. 28 DoD-Abschnitt „Infrastruktur-/
   Runtime-Baustein - abgeschlossen" (bewusst ohne Git-Tag); Kap. 29 Backlog
   (Wake-Word-Korrektur + drei neue Zeilen); Kap. 31 auf drei Einstiegs-
   punkte verallgemeinert. Umsetzung ueber python-docx (Anker per Textsuche,
   Titelseite auf w:t-Ebene wegen w:br-Umbruechen), verifiziert.
2. **README aktualisiert**: H1-Titel nicht mehr „v0.4", Verweise auf v3_7,
   Archiv-Liste um v3.6 ergaenzt.
3. **AI_START aktualisiert**: Pflicht-Lesereihenfolge auf v3_7, Archiv-Liste,
   Pflichtfrage 6 um Infrastrukturbausteine erweitert.
4. **PROJECT_STATE konsolidiert**: die vier temporaeren Abschnitte
   („Jarvis-Runtime v1 implementiert", „Single-Instance-Schutz
   implementiert", „Runtime v2 implementiert: TelegramChannel",
   „Jarvis-Eigenstart implementiert", ADR-024 bis ADR-028) entfernt -
   Inhalte vollstaendig ins Handbook (Kap. 7/13/27/28/29) uebernommen.
   Feature-TODOs bereinigt (Roadmap/Backlog jetzt im Handbook). Rollierende
   Abschnitte (Current Version, Status, Tests, Latest ADR, Latest
   Architecture Change, Known Limitations, Git) aktualisiert. Quelle-Zeile
   auf v3_7.
5. **CHANGELOG ergaenzt**: neuer oberster Eintrag „Handbook v3.7 -
   Konsolidierung des Infrastruktur-/Runtime-Bausteins".
6. **logbook ergaenzt**: dieser Eintrag.

**Widersprueche:** Keine neuen Widersprueche gefunden. Die im Plan
identifizierten Punkte (Kap. 2 Versionsliste, Kap. 19 Prozess-Reichweite,
Kap. 29 Wake-Word-„v0.4", Kap. 31 „main.py koordiniert", README-H1 „v0.4")
wurden im Rahmen dieser Konsolidierung aufgeloest. Die bekannte Veraltung
von Kap. 12 bleibt bewusst offen (Product-Owner-Entscheidung, fuer eine
spaetere Konsolidierung vorgemerkt).

**Schlusspruefung:** Handbook v3.7 - ausschliesslich die vorgesehenen Kapitel
(2, 7, 10, 13, 17, 19, 27, 28, 29, 31) sowie Titelseite/Aenderungsliste
geaendert; Kap. 12 unveraendert (verifiziert). Nur Dokumentationsdateien
geaendert (Handbook, README, AI_START, PROJECT_STATE, CHANGELOG, logbook) -
keine funktionalen Projektdateien (`core/*`, `commands/*`, `executor/*`,
`memory/*`, `main.py`, `telegram_main.py`, `jarvis_runtime.py`,
`telegram_channel.py`, `tests/*`).

Noch kein Commit - Commit erst nach abschliessendem Product-Owner-Review.

## 2026-07-02 - Jarvis-Eigenstart implementiert (ADR-028)

**Kontext:** Nach Commit von Runtime v2 (`7f9ccb8`, ADR-027) wurde der
Architekturvorschlag fuer Jarvis-Eigenstart erarbeitet - der letzte in
Handbook Kap. 13 vorgesehene Infrastrukturbaustein zwischen v0.7 und
v0.8. Zwei Zwischenfragen praezisierten den Vorschlag vor der ADR:

1. "Soll Runtime beim Autostart wirklich noch den ConsoleDummyChannel
   starten, oder ist es sauberer, ihn im Autostart-Modus gar nicht erst
   zu starten?" - Antwort: ja, sauberer - `sys.stdin is None` ist bei
   `pythonw.exe`-Start dokumentiert `None`, eine explizite, zentrale
   Pruefung in `main()` ist kleiner und praeziser als ein defensives
   `try`/`except` in `ConsoleDummyChannel` selbst (das unveraendert
   bleibt). Dabei zusaetzlich gefunden: dasselbe Problem traf auch
   `setup_logging()`s `StreamHandler` (schreibt nach `sys.stderr`,
   ebenfalls `None` bei `pythonw.exe`) - dieselbe Pruefung deckt beides ab.

**ADR-028 geschrieben und committed** (`f5c0a06`).

**Umsetzung (exakt nach ADR-028, kein separater Implementierungsplan
noetig):**
- `commands/monitor.py`: `EnableJarvisAutostartCommand`/
  `DisableJarvisAutostartCommand` (Sicherheitsstufe 2) - fester
  HKCU-Run-Key-Eintragsname `"Jarvis"`, Wiederverwendung von
  `_RUN_KEY_PATH`/`winreg`-Mechanik aus ADR-022. Ziel `pythonw.exe`
  (Fallback auf `sys.executable`, Antwort weist explizit darauf hin).
  `enable_jarvis_autostart` idempotent, `disable_jarvis_autostart`
  loescht ohne Pfad-Abgleich (Selbstbedienung statt Reparatur-Automatik,
  wie in ADR-028 begruendet).
- `jarvis_runtime.py`: `setup_logging()` laesst den Konsolen-
  `StreamHandler` weg, wenn `sys.stderr is None` (`FileHandler` bleibt
  immer aktiv). `main()` startet `ConsoleDummyChannel` nur, wenn
  `sys.stdin is not None` - sonst haelt sich der Prozess ueber
  `runtime._worker.join()` am Leben, bis er von aussen beendet wird.
  `ConsoleDummyChannel` selbst unveraendert.
- Reale Pruefung auf dieser Maschine: `pythonw.exe` wird im venv korrekt
  gefunden, Registry-Wert korrekt zusammengesetzt (`"...\.venv\Scripts\
  pythonw.exe" "...\jarvis_runtime.py"`).

**Tests:** 16 neue Tests - 14 fuer die beiden Commands (Windows-Guard,
Registry-Schreiben, `pythonw.exe`-Fallback, Idempotenz, Schreibfehler,
Sicherheitsstufe, Registrierung, Abgrenzung zu `disable_/
enable_autostart_entry`) in `tests/test_commands_monitor.py`, 2 fuer die
`setup_logging()`-Weiche in `tests/test_jarvis_runtime.py` (mit
gemocktem `logging.basicConfig`, um globalen Root-Logger-Zustand nicht
anzufassen). 280/280 gesamt gruen (264 vorher + 16 neu).

**Doku:** README (neue Sektion "Jarvis-Eigenstart (ADR-028)" nach
"Single-Instance-Schutz", Struktur-Baum ergaenzt), `docs/CHANGELOG.md`,
dieses Logbook, `docs/PROJECT_STATE.md` aktualisiert.

`git diff --stat` vor dem Commit gegen `core/*`, `executor/executor.py`,
`memory/*`, `telegram_channel.py`, `telegram_main.py`, `main.py`
geprueft - leer, wie in ADR-028 vorgegeben. Geaenderte Dateien:
`commands/monitor.py`, `jarvis_runtime.py`, `tests/test_commands_monitor.py`,
`tests/test_jarvis_runtime.py`, `README.md`, `docs/CHANGELOG.md`,
`docs/logbook.md`, `docs/PROJECT_STATE.md`.

Kein Tag gesetzt. Damit ist der letzte in Handbook Kap. 13 vorgesehene
Infrastrukturbaustein zwischen v0.7 und v0.8 (Jarvis-Runtime + Jarvis-
Eigenstart) abgeschlossen - naechster Schritt laut Handbook waere v0.8
"Multi-KI", noch nicht begonnen. Tray, eigenes UI, Wake-Word und
Runtime v3 bleiben weiterhin eigene, spaetere Entscheidungen.

## 2026-07-02 - Runtime v2 implementiert: TelegramChannel (ADR-027)

**Kontext:** Nach Commit des Single-Instance-Schutzes (`987ed0b`, ADR-026)
wurde ein Architekturvorschlag fuer "Jarvis-Eigenstart / Runtime v2"
angefordert. Ergebnis: Runtime v1 ist fuer unbeaufsichtigten Betrieb
ungeeignet (`ConsoleDummyChannel` blockiert auf `input()`) - Runtime v2
sollte deshalb genau einen echten, konsolenfreien Kanal hinzufuegen.
Wolfgang klaerte per Rueckfrage, ob Telegram direkt Teil von Runtime v2
sein muss oder ob zunaechst nur ein "Framework" ohne Kanal sinnvoll waere -
Antwort: nein, ein telegramloser Zwischenschritt haette nichts Neues zu
beweisen (Mehrkanal-Faehigkeit war bereits durch Runtime v1 bewiesen).
Architekturvorschlag als Richtung freigegeben, danach **ADR-027**
geschrieben und committed (`3b05a95`), danach ein vollstaendiger,
Product-Owner-geprueft er Implementierungsplan erarbeitet (7-Schritte-
Reihenfolge, Test-/Regressions-/Fehlerfall-Liste, kritische Pruefung
gegen Handbook/KISS/YAGNI).

**Wichtige Zwischenfrage vor der Freigabe:** Wolfgang fragte, ob
`jarvis_runtime.py` komplett unveraendert bleiben koennte, indem
`TelegramChannel` `filter_plan()` selbst anwendet und dann unveraendertes
`submit(text, reply_callback)` aufruft. Antwort: technisch moeglich, aber
sicherheitsrelevant riskant (TOCTOU) - eine zweite, unabhaengige
Planungs-Berechnung im Worker (`_process()` plant ohnehin erneut) koennte
wegen KI-Nichtdeterminismus oder echter Nebenlaeufigkeit (History aendert
sich zwischen Vorab-Check und tatsaechlicher Verarbeitung) einen anderen
Plan liefern als den geprueften - eine bestaetigungsfreie, aber nicht
erlaubte Anfrage koennte so ungeprueft durchrutschen. Deshalb blieb es bei
der im Plan vorgesehenen `plan_filter`-Erweiterung von `submit()`/
`_process()`, die Check und Ausfuehrung auf demselben, einmal berechneten
Plan haelt.

**Umsetzung (exakt nach Plan, 7 Schritte):**
1. `jarvis_runtime.py`: `submit()`/`_process()`/`_run_worker()` um
   optionalen `plan_filter`-Parameter erweitert (Default `None`, voll
   rueckwaertskompatibel) - bei Ablehnung kein Executor-Aufruf, keine
   History-Schreibung (Paritaet zu `telegram_main.py::JarvisBridge`).
2. Ein bestehender Test angepasst (`test_worker_does_not_die_on_unexpected_exception`
   - Mock-Signatur um `plan_filter` ergaenzt), 4 neue Tests fuer
   `plan_filter` in `tests/test_jarvis_runtime.py`.
3. Testsuite isoliert gruen (15/15 in `test_jarvis_runtime.py`), bevor
   ueberhaupt Telegram-Code entstand - trennt das hoehere Regressionsrisiko
   der Kernklassen-Aenderung vom Telegram-spezifischen Risiko.
4. `telegram_channel.py` neu angelegt: `TelegramChannel`, `_on_message`-
   Handler, Import von `ALLOWED_INTENTS`/`filter_plan`/`rejection_reason`/
   `is_authorized` unveraendert aus `telegram_main.py` (keine Duplizierung).
   Asyncio-Bruecke: `asyncio.get_running_loop()` beim Erfassen des PTB-Loops,
   `asyncio.run_coroutine_threadsafe()` fuer die Antwort aus dem
   Runtime-Worker-Thread. `run_polling(stop_signals=None)` - vermeidet einen
   bekannten PTB-Absturz bei Signal-Handler-Installation ausserhalb des
   Hauptthreads (dieser Kanal laeuft in einem eigenen Thread).
5. `tests/test_telegram_channel.py` neu angelegt (11 Tests).
6. `jarvis_runtime.py::main()` erweitert: startet `TelegramChannel`
   automatisch in einem eigenen Thread, sobald `JARVIS_TELEGRAM_BOT_TOKEN`/
   `JARVIS_TELEGRAM_ALLOWED_CHAT_ID` gesetzt sind - verzoegerter Import
   (`python-telegram-bot` bleibt optional, `ConsoleDummyChannel` funktioniert
   weiterhin ohne PTB-Installation). Manuell geprueft: ohne Env-Vars liefert
   `_start_telegram_channel()` sauber `None`.
7. Volle Testsuite: 264/264 gruen. `git diff --stat` gegen `core/*`,
   `commands/*`, `executor/*`, `memory/*`, `telegram_main.py`, `main.py`,
   `requirements.txt`, `docs/*` geprueft - leer, wie vorgegeben.

**Sicherheitsschicht unveraendert:** `_RuntimeSpeech` (fail-closed, ADR-025)
gilt automatisch auch fuer Telegram-Nachrichten, da `TelegramChannel` nur
den bereits bestehenden, geteilten Executor ueber `runtime.submit()`
erreicht - kein eigener `TelegramSpeech`-Adapter noetig, anders als bei
`telegram_main.py`.

**Doku:** README (Abschnitt "Jarvis-Runtime" umbenannt/erweitert, neuer
Unterabschnitt "TelegramChannel - zweiter Runtime-Kanal", Struktur-Baum),
`docs/CHANGELOG.md`, dieses Logbook, `docs/PROJECT_STATE.md` aktualisiert.

Kein Tag gesetzt. Jarvis-Eigenstart (Windows-Autostart), Tray, eigenes
UI, Wake-Word und Runtime v3 bleiben weiterhin eigene, spaetere
Entscheidungen.

## 2026-07-02 - Single-Instance-Schutz implementiert (ADR-026)

**Kontext:** Nach Abschluss und Commit von Runtime v1 (`95e5af9`) hat
Wolfgang zunaechst eine Bewertung angefordert, ob der Infrastruktur-/
Runtime-Baustein bereits ausreicht, damit Jarvis-Eigenstart darauf
aufbauen kann. Ergebnis: Runtime v1 beweist nur das Geruest (Queue/
Worker/Shutdown), der einzige Kanal (`ConsoleDummyChannel`) blockiert
aber auf `input()` und ist fuer einen unbeaufsichtigten Autostart nicht
nutzbar - ausserdem ist das Fehlen eines Schutzes vor gleichzeitigem
Betrieb mehrerer Einstiegspunkte gegen dasselbe `memory_dir` ein
eigenstaendiges, von Kanaelen/UI/Autostart unabhaengiges Risiko (bereits
in ADR-025 als offen benannt). Wolfgang entschied: Runtime v2 (Telegram-
Kanal, Channel-Interface, Autostart) explizit vertagt - naechster
Schritt ist ausschliesslich der Single-Instance-Schutz.

**Technischer Vorschlag bewertet und freigegeben** (9 Punkte: welche
Einstiegspunkte, welche Technik, KISS/Windows-Eignung, Scope pro
memory_dir vs. global, Verhalten bei aktiver/abgestuerzter Instanz,
Fehlerfaelle, Tests, ADR-Bedarf). Product-Owner-Entscheidung: Schutz pro
`memory_dir`, Lock-Datei mit PID/Einstiegspunkt/Zeitstempel,
Verwaist-Erkennung mit Selbstheilung, PID-Wiederverwendung
beruecksichtigen, Zweitstart fail-fast, alle drei Einstiegspunkte
(`main.py`/`telegram_main.py`/`jarvis_runtime.py`) geschuetzt. Zusaetzlich:
offenes Datei-Handle waehrend der Laufzeit halten, fuer mehr Robustheit
als eine reine Marker-Datei.

**ADR-026 geschrieben** (`docs/adr/ADR-026.md`).

**Umsetzung:**
- Neue Datei `core/single_instance.py`: `SingleInstanceLock` (Schutz pro
  `memory_dir`), `InstanceAlreadyRunningError`. Lock-Datei `jarvis.lock`
  im jeweiligen `memory_dir`, atomar erzeugt (`os.open(O_CREAT|O_EXCL)`),
  Inhalt PID/Einstiegspunkt/Zeitstempel als JSON. Zusaetzlich
  `msvcrt.locking()` auf dem offen gehaltenen Handle - Windows gibt es
  beim Absturz automatisch frei. Vor jedem Erwerb: Verwaist-Pruefung
  ueber `psutil.pid_exists()` + exakten Dateiname-Abgleich der
  tatsaechlichen Prozess-Cmdline (PID-Wiederverwendungsschutz) -
  verwaiste Lock-Dateien werden automatisch entfernt.
- `main.py`, `telegram_main.py`, `jarvis_runtime.py` erwerben den Lock
  als allererste Aktion in `main()`, geben ihn per `try`/`finally` beim
  Beenden frei. Bei aktivem Lock: sofortiger, kontrollierter Abbruch mit
  Fehlermeldung (PID/Einstiegspunkt/Zeitstempel), kein Command wird
  ausgefuehrt. `core/config.py`, `core/ai.py`, `core/planner.py`,
  `core/speech.py`, `core/tool_manager.py`, `core/models.py`,
  `commands/*`, `executor/*`, `memory/*` unveraendert.

**Waehrend der Implementierung gefundener und behobener Bug:** Ein
frueher Testlauf zeigte `PermissionError` beim Lesen der Lock-Datei
ueber ein frisches Handle, waehrend das eigene, sperrende Handle noch
offen war - `msvcrt.locking()` verweigert das Lesen ueber JEDES andere
Handle, auch innerhalb desselben Prozesses. Die urspruengliche
`_clear_if_stale()`-Implementierung interpretierte diesen Lesefehler
faelschlich als "Datei verwaist/kaputt" und haette eine aktiv gesperrte
Lock-Datei geloescht - ein sicherheitsrelevanter Fehler, der den
Single-Instance-Schutz ausgehebelt haette. Korrektur: `PermissionError`
wird jetzt als eigener Fall behandelt ("aktiv gesperrt, NICHT verwaist"),
getrennt von echter Korruption (`OSError`/`json.JSONDecodeError` ohne
Permission-Ursache). Durch einen dedizierten Regressionstest abgesichert
(`test_actively_held_lock_survives_a_second_acquire_attempt`), der ohne
psutil-Mock einen echten zweiten Erwerbsversuch gegen ein bereits
aktives, echtes Lock durchfuehrt.

**Tests:** 13 neue Tests (`tests/test_single_instance.py`) - Lock-Erwerb
mit korrektem Inhalt, saubere Freigabe, Context-Manager, Isolation
verschiedener `memory_dir`s, Blockade bei echter aktiver Instanz (inkl.
des og. Regressionstests), Selbstheilung bei totem PID, PID-
Wiederverwendung, Substring-Kollision `"main.py"` in
`"telegram_main.py"` explizit als eigener Testfall, `AccessDenied`,
kaputte JSON-Datei, erneuter Erwerb nach sauberer Freigabe. 249/249
gesamt gruen (236 vorher + 13 neu).

**Doku:** README (neue Sektion "Single-Instance-Schutz (ADR-026)" nach
"Jarvis-Runtime v1", Struktur-Baum ergaenzt), `docs/CHANGELOG.md`, dieses
Logbook, `docs/PROJECT_STATE.md` aktualisiert.

`git diff --stat` vor dem Commit gegen `core/config.py`, `core/ai.py`,
`core/planner.py`, `core/speech.py`, `core/tool_manager.py`,
`core/models.py`, `commands/*`, `executor/*`, `memory/*` geprueft - leer,
wie vorgegeben. Geaenderte Dateien: `core/single_instance.py` (neu),
`tests/test_single_instance.py` (neu), `docs/adr/ADR-026.md` (neu),
`main.py`, `telegram_main.py`, `jarvis_runtime.py`, `README.md`,
`docs/CHANGELOG.md`, `docs/logbook.md`, `docs/PROJECT_STATE.md`.

Kein Tag gesetzt. Runtime v2 (Telegram-Kanal, Channel-Interface,
Autostart), UI, Tray, Wake-Word bleiben weiterhin eigene, spaetere
Entscheidungen.

## 2026-07-02 - Jarvis-Runtime v1 implementiert (ADR-025)

**Kontext:** Nach Freigabe des Implementierungsplans fuer Runtime v1
(kleinstmoeglicher Architekturbaustein aus ADR-024) hat Wolfgang die
Umsetzung freigegeben - zuerst ADR-025 schreiben, dann implementieren.

**Product-Owner-Vorgaben (vollstaendig uebernommen):** Neue Datei
`jarvis_runtime.py`, neue Tests `tests/test_jarvis_runtime.py`, keine
Aenderung an `main.py`/`telegram_main.py`/`core/*`/`commands/*`/
`executor/*`, kein UI/Tray/Wake-Word/Telegram-Umbau/Autostart, kein
neues `runtime/`-Package, kein abstraktes Channel-Interface in v1,
`queue.Queue` + ein Worker-Thread, fail-closed Speech-Adapter wie bei
Telegram, `ConsoleDummyChannel` als erster minimaler Kanal,
Sicherheitsstufe-2/3-Commands muessen fail-closed bleiben, Worker darf
bei Fehlern nicht still sterben.

**ADR-025 geschrieben** (`docs/adr/ADR-025.md`) - haelt die Umsetzung
von Runtime v1 fest, aufbauend auf ADR-024s Architekturrichtung.

**Umsetzung** (`jarvis_runtime.py`, ~200 Zeilen, top-level neben
`main.py`/`telegram_main.py`, kein neues Package):

- `JarvisRuntime`: verdrahtet den Core-Stack 1:1 wie `main.py`
  (`AIEngine` -> `Planner` -> `Executor` -> `JsonMemoryStore`/
  `LongTermMemory`, `commands.*.configure(...)`) - einmalig, nicht pro
  Kanal. `ai` injizierbar fuer Tests (gleiches Muster wie
  `JarvisBridge` in `telegram_main.py`).
- `queue.Queue` + ein einzelner Worker-Thread (`start()`/`stop()`/
  `submit(text, reply_callback)`): Nachrichten werden seriell in
  Eingangsreihenfolge verarbeitet. Stop-Pfad ueber ein Sentinel-Objekt
  in der Queue, `stop()` wartet per `thread.join()`.
- Worker faengt jede Exception pro Nachricht einzeln ab
  (`try/except Exception` in der Worker-Schleife) und laeuft mit der
  naechsten Nachricht weiter, statt still zu sterben - inkl. Schutz
  gegen einen kaputten `reply_callback` (Kanal bereits weg).
- `_RuntimeSpeech` (privat): fail-closed `say()`/`listen()`-Adapter fuer
  den geteilten Executor - `listen()` liefert immer `""`, Stufe-2/3-
  Commands werden dadurch sicher ueber den bestehenden Executor-
  Bestaetigungsmechanismus abgelehnt. Bewusst dupliziert statt aus
  `telegram_main.py` importiert (keine `python-telegram-bot`-
  Abhaengigkeit in der Runtime fuer ein reines Sicherheits-Fallback).
- `ConsoleDummyChannel`: liest interaktiv von der Konsole, reicht jede
  Zeile ueber `runtime.submit()` weiter, wartet per `threading.Event`
  auf die Antwort und druckt sie. Einziger Kanal in v1, kein
  Produktivkanal - beweist nur, dass Core-Stack + Queue + Worker-Thread
  + sauberer Shutdown tatsaechlich funktionieren.

**Bewusst nicht enthalten:** UI, Tray, Wake-Word, Telegram-Integration
in die Runtime, Autostart, abstraktes Channel-Interface (YAGNI - erst
beim zweiten echten Kanal), `asyncio`, echte Nebenlaeufigkeits-
Absicherung in `JsonMemoryStore`/`Executor` (nicht noetig, da die Queue
serialisiert). Keine Aenderung an `main.py`, `telegram_main.py`,
`core/*`, `commands/*`, `executor/*`.

**Tests:** 11 neue Tests (`tests/test_jarvis_runtime.py`) - Core-Stack-
Verdrahtung, einzelne Nachricht verarbeitet, mehrere Nachrichten
sequenziell in Eingangsreihenfolge, gleichzeitige `submit()`-Aufrufe
aus mehreren Threads gehen nicht verloren/vermischen sich nicht,
sauberer `stop()` (Worker-Thread danach `is_alive() is False`),
Sicherheitsstufe-2/3 (`shutdown_pc`) fail-closed ueber die Runtime,
Worker ueberlebt eine unerwartete Exception bei der Verarbeitung UND
einen kaputten `reply_callback`, `_RuntimeSpeech` fail-closed,
`ConsoleDummyChannel` reicht Eingaben korrekt weiter und ignoriert
leere Zeilen. Vollstaendige Suite: **236/236 gruen** (225 vorher + 11
neu). `git diff --stat` bestaetigt: nur `jarvis_runtime.py` (neu),
`tests/test_jarvis_runtime.py` (neu), `docs/adr/ADR-025.md` (neu) -
keine Aenderung an `main.py`/`telegram_main.py`/`core/*`/`commands/*`/
`executor/*`.

Kein Tag gesetzt. Jarvis-Eigenstart-Implementierung bleibt weiterhin
verschoben - ob Runtime v1 dafuer bereits ausreicht, ist eine eigene,
spaetere Entscheidung.

## 2026-07-02 - ADR-024: Jarvis-Runtime als koordinierender Einstiegspunkt (Architekturentscheidung)

**Kontext:** Aufbauend auf der zuvor festgehaltenen Architekturrichtung
(Jarvis-Runtime, Koexistenz mit `main.py`/`telegram_main.py`) wurde ein
detaillierter technischer Vorschlag fuer ADR-024 erarbeitet und von
Wolfgang mit fuenf konkretisierenden Entscheidungen freigegeben.

**Product-Owner-Entscheidungen (vollstaendig uebernommen, siehe ADR-024):**
1. **Nebenlaeufigkeitsmodell:** einfache `queue.Queue` mit einem einzelnen
   Worker-Thread fuer den ersten Runtime-Schritt - bewusst KEIN `asyncio`.
   Begruendung: KISS, verstaendlich, gut testbar, keine unnoetige Magie
   (Handbook-Leitmotiv). Loest das Nebenlaeufigkeits-/Locking-Problem bei
   `memory_data/` durch serialisierte Verarbeitung, ohne `JsonMemoryStore`/
   `Executor` anzufassen.
2. **Telegram:** ausdruecklich NICHT Bestandteil von ADR-024.
   `telegram_main.py` bleibt eigenstaendig. Eine spaetere
   Runtime-Integration bleibt optional, separate kuenftige Entscheidung.
3. **Erster Runtime-Kanal:** kein UI, kein Tray, kein Wake-Word. Ein
   minimaler Konsolen-/Dummy-/Status-Kanal soll spaeter zuerst nur das
   Runtime-Geruest (Core-Stack-Instanziierung + Queue + Worker-Thread +
   sauberer Shutdown) und die serielle Verarbeitung beweisen - kein
   Produktivkanal.
4. **Roadmap/Governance:** Runtime bleibt eigenstaendiger Infrastruktur-/
   Runtime-Baustein zwischen v0.7 und v0.8. `v0.8 "Multi-KI"` wird
   weiterhin nicht begonnen.
5. **Wake-Word-Hinweis:** Handbook Kap. 29 (Backlog) nennt fuer
   "Wake-Word (Porcupine)" noch den ueberholten Pruefzeitpunkt "v0.4" -
   als Korrekturbedarf in ADR-024 dokumentiert, Korrektur erst bei der
   naechsten Handbook-Konsolidierung, NICHT jetzt im Handbook geaendert.

**ADR-024 geschrieben** (`docs/adr/ADR-024.md`) - haelt alle obigen
Entscheidungen sowie die bereits zuvor freigegebenen Grundsatzpunkte
(Zweck/Abgrenzung zu `main.py`/`telegram_main.py`, Core-Stack-
Instanziierung, Shutdown-Grundsatz, Bezug zu Jarvis-Eigenstart) formal
fest. Ausdruecklich **keine Implementierung**: `jarvis_runtime.py` wird
durch diese ADR nicht angelegt, keine Aenderung an `main.py`,
`telegram_main.py`, `core/*`, `commands/*`, `executor/*`.

**Dokumentation aktualisiert:** `docs/PROJECT_STATE.md` - Abschnitt
"Architekturrichtung: Jarvis-Runtime" auf ADR-024 verweisend praezisiert
(Nebenlaeufigkeitsmodell, erster Kanal, Telegram-Ausschluss,
Wake-Word-Hinweis ergaenzt), `Latest ADR` auf ADR-024 aktualisiert.
`Latest Architecture Change` bewusst weiterhin bei ADR-023 belassen -
ADR-024 aendert noch keine tatsaechlich laufende Architektur, nur eine
kuenftige.

**Kein Code, keine Runtime-Datei, kein Autostart, kein UI, kein
Telegram-Umbau.** Tests unveraendert (keine Code-Datei beruehrt).

## 2026-07-02 - Architekturrichtung Jarvis-Runtime festgelegt (Jarvis-Eigenstart verschoben)

**Kontext:** Nach Abschluss von v0.7 (Handbook v3.6, Tag `v0.7`) wurde ein
technischer Vorschlag fuer den bereits im Handbook vorgesehenen
"Jarvis-Eigenstart"-Baustein erarbeitet (HKCU Run-Key, Sicherheitsstufe 2,
zwei symmetrische Intents `enable_jarvis_autostart`/
`disable_jarvis_autostart`, `sys.executable`+`BASE_DIR`-Pfadermittlung,
Ziel urspruenglich `main.py`). Wolfgang stoppte vor der Umsetzung: Jarvis
soll langfristig ein eigenes UI im Stil von Film-Jarvis bekommen (UI, Tray,
Wake Word, Telegram und Core sollen koordiniert zusammenspielen) - der
Windows-Autostart sollte deshalb nicht fest auf den Konsolenmodus (`main.py`)
gebaut werden.

**Architekturvorschlag erarbeitet** (rein konzeptionell, kein Code): Kap. 7
(Kern-Architektur, `Voice -> Brain -> Planner -> Tool Manager -> Executor ->
Tools`) ist bereits kanal-agnostisch - `main.py`/`telegram_main.py` sind
schon heute zwei duenne Einstiegspunkte, die denselben Core-Stack einmalig
verdrahten, nur mit je einem Kanal. ADR-018 verhindert bewusst
gleichzeitigen Betrieb (kein Locking auf `memory_data/`) - das ist der
eigentliche Ausloeser fuer eine koordinierende Runtime, nicht UI/Tray/
Wake-Word allein. Kap. 30 (Plugin-Vision, Praezisierung v3.3) liefert das
Leitprinzip: Architektur erst bauen, wenn der echte Bedarf (mehrere
gleichzeitige Kanaele) da ist, nicht vorab.

**Product-Owner-Entscheidungen (vollstaendig uebernommen):**
1. Neuer, kuenftiger Runtime-Einstiegspunkt **`jarvis_runtime.py`** (Name
   festgelegt, noch NICHT implementiert) - koordiniert spaeter mehrere
   gleichzeitige Kanaele ueber einen einmalig instanziierten Core-Stack.
2. **Koexistenz statt Abloesung** (explizite Korrektur/Praezisierung):
   `main.py` bleibt dauerhaft Konsolen-/Entwicklungsmodus.
   `telegram_main.py` bleibt dauerhaft eigenstaendiger, einfacher
   Telegram-Einstiegspunkt - wird NICHT entfernt, NICHT als obsolet
   markiert. Die Runtime kann Telegram spaeter zusaetzlich als Kanal
   einbinden, ohne `telegram_main.py` zu ersetzen. Begruendung: "Funktionierende
   einfache Einstiegspunkte bleiben erhalten. Die Runtime erweitert die
   Architektur, ersetzt sie aber nicht sofort."
3. Jarvis-Eigenstart-**Mechanik** (Sicherheitsstufe 2, zwei Intents,
   Pfadermittlung) bleibt inhaltlich gueltig, zielt aber kuenftig auf
   `jarvis_runtime.py` statt `main.py`. **Implementierung explizit
   verschoben**, bis die Runtime existiert - kein Autostart jetzt.

**Offen fuer die kuenftige Runtime-Umsetzung, hier nur festgehalten, nicht
entschieden:** Nebenlaeufigkeits-/Locking-Problem bei `memory_data/` (ADR-018
umgeht es nur durch "ein Kanal zur Zeit" - empfohlen, nicht entschieden:
einfache serialisierte Warteschlange statt echter Concurrency-Sicherheit);
ob die Runtime Telegram ueber den bestehenden `TelegramSpeech`-Adapter
wiederverwendet oder eigenstaendig neu anbindet.

**Dokumentation (Kap.-19-Mechanismus):** Vollstaendig in
`docs/PROJECT_STATE.md` (neuer Abschnitt "Architekturrichtung:
Jarvis-Runtime") festgehalten - ab sofort massgeblich, wird bei der
naechsten Konsolidierung (nach Runtime-Umsetzung oder spaetestens v0.8)
foermlich ins Handbook uebernommen. **Kein Code, keine ADR, keine
Handbook-Aenderung, keine Runtime-Implementierung, kein Autostart jetzt.**
Tests unveraendert (keine Code-Datei beruehrt).

## 2026-07-02 - v0.7 getaggt (Abschluss)

Nach der Konsolidierung (Handbook v3.6, Commit `a7eb86d`) hat Wolfgang als
Product Owner den Tag `v0.7` freigegeben - separat von der Konsolidierung,
in einer eigenen Freigabe-Runde (gleiches Muster wie bei v0.6: erst
Konsolidierung/Handbook, dann getrennt der Tag). Definition of Done (Kap.
28, "v0.7 - spezifisch") erfuellt, Tests weiterhin 225/225 gruen.
`git tag -a v0.7` gesetzt, zeigt auf `a7eb86d`. `v0.7 "PC-Admin"` ist damit
als Gesamtversion abgeschlossen - naechster geplanter Baustein ist `v0.8
"Multi-KI"` (Handbook Kap. 13), noch nicht begonnen.

## 2026-07-02 - Entwicklungsprozess weiterentwickelt, Handbook v3.6 (Konsolidierung)

**Kontext:** Nach vollständigem Abschluss von v0.7 (Commit `920e32c`) wollte
Wolfgang den Entwicklungsprozess dauerhaft verbessern: das Handbook soll die
einzige Single Source of Truth bleiben, ohne dass `PROJECT_STATE.md`/
`logbook.md` über mehrere Versionen hinweg unbegrenzt wachsen. Ein zehn
Punkte umfassender Vorschlag wurde erarbeitet (rein konzeptionell, kein
Code, keine Dateien) und deckte sich groesstenteils mit bereits gelebter
Praxis (Handbook-Update pro Hauptversion war schon dreimal so gemacht
worden, v3.3/v3.4/v3.5) - neu war im Kern nur EIN Punkt: die explizite
Definition von PROJECT_STATE.md als temporaerer, rueckbaubarer
Arbeitsbereich; alles andere folgt daraus.

**Product-Owner-Entscheidungen:** Sechs Kernregeln freigegeben, mit zwei
Praezisierungen: (1) keine feste Handbook-Nummerierungsregel (v3.6/v3.7/...)
- die Regel lautet nur "nach jeder abgeschlossenen Hauptversion wird eine
neue Handbook-Version erstellt", die konkrete Nummer bleibt
Product-Owner-Entscheidung im Einzelfall; (2) Product-Owner-Rules wandern
vollstaendig und dauerhaft ins Handbook, nicht mehr in PROJECT_STATE.md.

**Konsolidierung durchgefuehrt** (Handbook v3.5 -> v3.6, `python-docx`,
gleiche Methode wie bei v3.3/v3.4/v3.5 - Style-Objekte aus bestehenden
Absaetzen wiederverwendet, Absatz-Referenzen vor jeder Einfuegung neu
erfasst, da Indizes sich bei jeder Einfuegung verschieben):

1. **Kap. 2 (Handbook-Versionierung):** Regel von "darf nur zwischen
   Versionen geaendert werden" zu "WIRD nach jeder abgeschlossenen
   Hauptversion aktualisiert" verschaerft - Pflicht statt Erlaubnis, ohne
   festes Nummerierungsschema (Product-Owner-Entscheidung 1).
2. **Kap. 13 (Roadmap):** v0.7 als abgeschlossen markiert. Neuer Eintrag
   "Jarvis-Eigenstart (geplant zwischen v0.7 und v0.8)" mit vollstaendigem
   Zweck/Scope/Nicht-Scope-Text (aus der fruaheren PROJECT_STATE.md-Notiz
   uebernommen) - bewusst OHNE eigene vX.Y-Versionsnummer und OHNE
   Umnummerierung von v0.8/v0.9 (haette eine eigene Roadmap-Entscheidung
   gebraucht), stattdessen als praezisierender Unterabschnitt nach dem
   etablierten "Praezisierung vX.Y"-Muster.
3. **Kap. 17 (PC-Steuerung):** alle sieben Faehigkeiten mit
   Umsetzungsstand annotiert (umgesetzt/Benutzer-Scope/offen, jeweils mit
   ADR-Verweis). System-Analyst-Vision um einleitenden Satz zum
   Jarvis-Eigenstart ergaenzt.
4. **Kap. 19 (Logbook/Governance) - Kernstueck der Konsolidierung:**
   PROJECT_STATE.md-Bullet um die "temporaerer Arbeitsbereich"-Definition
   erweitert; bestehende Mid-Version-Entscheidungs-Regel (ab v3.4) erweitert
   und praezisiert; NEUER Abschnitt "Konsolidierungsprozess" mit den sieben
   Prozessschritten (ADRs pruefen, PROJECT_STATE.md pruefen, logbook.md
   pruefen, CHANGELOG.md pruefen, dauerhafte Entscheidungen uebernehmen,
   temporaere Punkte entfernen, neue Handbook-Version erzeugen) -
   ausdruecklich klargestellt, dass logbook.md/CHANGELOG.md NICHT geleert
   werden, nur PROJECT_STATE.md; NEUER Abschnitt "Rolle von
   PROJECT_STATE.md" mit der rollierend/akkumulierend-Unterscheidung; NEUER
   Abschnitt "Scope-Erweiterungen und Descoping"; NEUER Abschnitt
   "Product-Owner-Rules" mit den drei aus PROJECT_STATE.md uebernommenen
   Regeln (Product-Owner-Entscheidung 2).
5. **Kap. 27 (Now/Next/Later):** Later-Bullet "Vollstaendige
   PC-Administration" aktualisiert, neue "Praezisierung v3.6: v0.7
   Abschluss" nach dem etablierten Muster (v3.3/v3.4/v3.5) ergaenzt.
6. **Kap. 28 (Definition of Done):** neues allgemeines Kriterium "Neue
   Handbook-Version erstellt" zwischen Changelog und Git-Tag eingefuegt;
   neuer Abschnitt "v0.7 - spezifisch (PC-Admin) - abgeschlossen" mit acht
   Kriterien nach dem etablierten Muster.
7. **Kap. 29 (Feature-Entscheidungsmatrix/Backlog):** Zuordnungsprinzip-Satz
   ergaenzt ("jede Idee bekommt Version oder Backlog"); sechs neue
   Backlog-Zeilen (Treiber, Dienste, HKLM-Autostart, Papierkorb,
   `C:\Windows\Temp`, Browser-Cache/-Profile) in die bestehende
   Backlog-Tabelle eingefuegt.

**Vollstaendiger Text-Diff v3.5 vs. v3.6 geprueft** (gleiche Methode wie
bei allen fruaheren Handbook-Updates: Volltext aus beiden `.docx`
extrahiert, `diff -u`) - ausschliesslich die oben genannten,
beabsichtigten Aenderungen, keine Kollateralschaeden in unveraenderten
Kapiteln (3-12, 14-16, 18, 20-26, 30-32 vollstaendig unberuehrt).

**Begleitdateien aktualisiert:**
- `docs/AI_START.md`: sechste Pflichtfrage zum Konsolidierungsstatus,
  Verweis auf `JARVIS_MASTER_HANDBOOK_v3_6.docx`.
- `README.md`: Handbook-Verweis auf v3.6, Archiv-Liste um v3.5 erweitert.
- `docs/PROJECT_STATE.md`: grundlegend konsolidiert - Abschnitte "Backlog",
  "Ausstehende Handbook-Aktualisierung" und "Product Owner Rules"
  vollstaendig entfernt (Inhalte sind jetzt im Handbook), Status-Abschnitt
  auf knappe Zusammenfassung mit Verweis auf CHANGELOG/ADRs gekuerzt -
  erste praktische Anwendung der neuen Konsolidierungsregel.
- `docs/CHANGELOG.md`: neuer Eintrag "Handbook v3.6 - v0.7-Abschluss,
  Entwicklungsprozess-Weiterentwicklung" nach dem etablierten Muster
  (v3.3/v3.4/v3.5).

**Kein Code geschrieben, keine Architektur geaendert** - reine
Dokumentations-/Governance-Aktualisierung. Kein Tag gesetzt (nur
Konsolidierung war freigegeben, Tag folgt als separater, noch
ausstehender Schritt). Tests unveraendert **225/225 gruen** (keine
Code-Datei beruehrt).

## 2026-07-02 - v0.7-Abschluss vorbereitet (Scope-Entscheidung, Backlog, Dokumentation)

**Kontext:** Nach Commit von v0.7 Phase 4 (Temp-Bereinigung, ADR-023,
`a765c9d`) wurde per AI_START.md neu eingestiegen und der Gesamtstand von
v0.7 erneut gegen das Handbook bewertet: von den drei in Kap. 13 genannten
v0.7-Kernthemen ("System-Analyse, Treiber, Reinigung") war "System-Analyse"
vollstaendig, "Reinigung" im sicheren Benutzer-Scope abgedeckt - nur
"Treiber" blieb komplett unbearbeitet.

**Product-Owner-Entscheidung:** v0.7 wird mit dem aktuellen Umfang
abgeschlossen. Begruendung (vollstaendig uebernommen): System-Analyse ist
vollstaendig abgedeckt, Autostart-Verwaltung ist im Benutzer-Scope
umgesetzt, Temp-Bereinigung ist im sicheren Benutzer-Scope umgesetzt.
Treiber und Dienste bleiben bewusst offen, weil sie die riskantesten
Bausteine sind und separat priorisiert werden sollen.

**Erste Korrektur:** `docs/PROJECT_STATE.md` (Abschnitt "Git") enthielt noch
die veraltete Aussage, die Temp-Bereinigung sei nicht committed - korrigiert
auf Commit `a765c9d`, dazu klargestellt, dass v0.7 bis zum vollstaendigen
Abschlussprozess (Handbook v3.6, Tag) ungetaggt bleibt.

**v0.7-Abschluss vorbereitet:**
1. **Treiber pruefen/aktualisieren** und **Dienste starten/stoppen** (Kap.
   17) explizit ins Backlog verschoben - beide als riskanteste/komplexeste
   Kap.-17-Bausteine begruendet (Treiber ist Handbooks eigenes
   Stufe-3-Beispiel, Kap. 10).
2. Vier weitere offene Erweiterungen als spaetere Bausteine dokumentiert:
   Autostart-Verwaltung auf HKLM/Alle-Benutzer (Administratorrechte),
   Temp-Bereinigung um Papierkorb, Temp-Bereinigung um
   `C:\Windows\Temp` (Administratorrechte), Browser-Cache-/Profil-
   Bereinigung.
3. Neuer, konsolidierter Abschnitt "Backlog" in `docs/PROJECT_STATE.md` -
   alle sechs Punkte an einer Stelle, mit Verweis auf die formale Aufnahme
   in Handbook Kap. 29 beim v3.6-Update (Kap.-19-Mechanismus, gleiches
   Vorgehen wie bei Power BI/v0.5 und Post-Arbeitsmodule-Generalisierung/
   v0.6 - Entscheidung jetzt in PROJECT_STATE.md/logbook.md massgeblich
   festgehalten, Handbook-`.docx` erst beim tatsaechlichen Versionswechsel
   angefasst).
4. Abschnitt "Ausstehende Handbook-Erweiterung" zu "Ausstehende
   Handbook-Aktualisierung (v3.6, vor dem Tag)" erweitert - fasst jetzt
   alle vier fuer v3.6 anstehenden Handbook-Aenderungen zusammen (Kap. 13
   als abgeschlossen markieren, Kap. 29 Backlog-Ergaenzung, Kap. 28
   DoD-Abschnitt fuer v0.7, Jarvis-Eigenstart-Kapitel).
5. `docs/CHANGELOG.md`: neuer, oberster Eintrag "v0.7 - PC-Admin ...
   (Scope abgeschlossen, Tag ausstehend, 02.07.2026)" - konsolidierte
   Zusammenfassung aller vier Phasen plus Backlog-Liste, referenziert
   `PROJECT_STATE.md` fuer den laufend aktuellen Stand (gleiches Muster
   wie die v0.5-/v0.6-Abschluss-Eintraege, nur mit "Tag ausstehend" statt
   "getaggt", da hier bewusst noch kein Tag gesetzt wurde).
6. `docs/PROJECT_STATE.md`: "Current Version"/"Status"/"Current
   Development Phase"/"Next Planned Version"/"Next Goal According To
   Handbook" auf "v0.7 inhaltlich abgeschlossen, Tag noch ausstehend"
   umgestellt.

**Noch NICHT durchgefuehrt (bewusst, wie angewiesen):** kein Tag gesetzt,
Handbook-`.docx` nicht angefasst (Kap.-2-Regel: erst beim tatsaechlichen
Versionswechsel, das ist der naechste, noch ausstehende Schritt). Kein
Code geschrieben, keine neue ADR (reine Scope-/Backlog-Entscheidung, wie
bei der Power-BI-Descoping-Entscheidung).

**Tests:** vollstaendige Suite erneut ausgefuehrt, weiterhin **225/225
gruen** - reine Dokumentationsaenderung, kein Code beruehrt.

## 2026-07-02 - Temp-/Festplatten-Bereinigung implementiert, v0.7 Phase 4 (ADR-023)

**Kontext:** Nach Commit von v0.7 Phase 3 (Autostart verwalten, ADR-022,
`b108c06`) wurde die Gesamtbewertung von v0.7 gegen das Handbook
vorgelegt: von den drei in Kap. 13 genannten v0.7-Kernthemen
("System-Analyse, Treiber, Reinigung") war nur "System-Analyse"
vollstaendig abgedeckt. Wolfgang hat entschieden, v0.7 weiterzufuehren
(kein Tag) und "Temp-/Festplatten-Bereinigung" als naechsten Baustein
priorisiert.

**Technischer Vorschlag und Product-Owner-Entscheidungen:** Zwei
Commands (`analyze_temp_files` Stufe 0, `clean_temp_files` Stufe 3 -
Handbook Kap. 10 klassifiziert "Datei loeschen" explizit als kritisch),
Papierkorb ausdruecklich nicht Bestandteil, 24h-Alters-Schwellwert,
Modul bleibt `commands/monitor.py`. Vor der Implementierung eine
zusaetzliche Architekturentscheidung: `clean_temp_files` soll immer
einen frischen Scan durchfuehren, eine exakte Vorschau zeigen, und erst
NACH Bestaetigung loeschen - als einheitliches Sicherheitsmuster fuer
alle kuenftigen schreibenden PC-Admin-Commands.

**Architekturaenderung:** Der bestehende Executor-Bestaetigungsmechanismus
zeigt nur den rohen Sprachbefehl (`raw_input`) an, bevor `execute()`
ueberhaupt aufgerufen wird - er kann daher keine vom Command berechneten
Vorschau-Daten einbauen. Geloest durch einen neuen, optionalen
`preview(plan) -> Optional[str]`-Hook in `executor/executor.py` - die
**erste Aenderung an dieser Datei in der gesamten v0.7-Entwicklung**.
Implementiert `command.preview()` und liefert sie einen Text, zeigt der
Executor ihn vor der Bestaetigungsfrage an. Commands ohne `preview()`
(alle bisherigen: `InstallProgramCommand`, `ShutdownPcCommand`,
`DisableAutostartEntryCommand` usw.) verhalten sich exakt wie zuvor -
`getattr(command, "preview", None)` liefert fuer sie `None`, keine
Verhaltensaenderung. Kein Zugriff fuer Commands auf `SpeechEngine` - der
Hook bleibt eine reine `Plan -> Optional[str]`-Funktion, die
Anzeige-Logik bleibt vollstaendig im Executor. Keine Aenderung an
`core/planner.py`, `core/tool_manager.py`, `core/ai.py`.

**Umsetzung:** `commands/monitor.py::AnalyzeTempFilesCommand`/
`CleanTempFilesCommand`. Gemeinsame interne Scan-Funktion
`_scan_eligible_temp_files()` - scannt `%TEMP%` rekursiv nach Dateien
aelter als `_TEMP_FILE_MIN_AGE_HOURS` (24h), mit Pfad-Eindaemmung
(`resolved.is_relative_to(base)`) gegen Ziele ausserhalb von `%TEMP%`.
Wird unabhaengig voneinander von `analyze_temp_files.execute()`,
`CleanTempFilesCommand.preview()` UND `CleanTempFilesCommand.execute()`
aufgerufen - **`execute()` verlaesst sich nie auf das
`preview()`-Ergebnis**, sondern scannt beim tatsaechlichen Loeschen
erneut frisch (Product-Owner-Kernvorgabe). Nur Dateien werden geloescht,
nie Ordner. Gesperrte (`PermissionError`) und zwischenzeitlich
verschwundene Dateien (`FileNotFoundError`, Race Condition) werden
einzeln uebersprungen und im Ergebnis vermerkt, kein Totalausfall.

`clean_temp_files`: Sicherheitsstufe 3 (`requires_confirmation = True`,
`confirmation_phrase = "BEREINIGEN"`) - hoeher als Autostart-Verwalten
(Stufe 2, ADR-022), da Handbook Kap. 10 "Datei loeschen" explizit als
kritisch einstuft und eine geloeschte Temp-Datei anders als ein
deaktivierter Autostart-Eintrag nicht ueber einen Jarvis-eigenen
Mechanismus wiederherstellbar ist.

**Bewusst nicht enthalten:** Papierkorb (explizit nicht Bestandteil von
ADR-023), `C:\Windows\Temp`/Administratorrechte, Browser-Cache/-Profile,
Registry-Cleaner, Dienste, Treiber. Keine Aenderung an `core/ai.py`,
`core/planner.py`, `core/tool_manager.py`, `main.py`.

**Tests:** 23 neue Tests - 6 in `tests/test_executor.py` (Rueckwaerts-
kompatibilitaet mit/ohne `preview()`, Stufe 2 und Stufe 3, Fallback bei
`None`-Rueckgabe, unabhaengige Aufrufreihenfolge preview()/execute())
und 17 in `tests/test_commands_monitor.py` (Plattformpruefung,
Alters-Filter, Unterordner-Rekursion, fehlende TEMP-Variable,
Ordner-werden-nie-geloescht, gesperrte/verschwundene Dateien,
Vorschau-vs-Ausfuehrung-scannt-unabhaengig-Test, Stufe-3-Verifikation,
Registrierung). Vollstaendige Suite: **225/225 gruen** (202 vorher + 23
neu). `git diff --stat` bestaetigt: `commands/monitor.py`,
`executor/executor.py`, beide Testdateien geaendert, `docs/adr/ADR-023.md`
neu - keine Aenderung an `core/ai.py`, `core/planner.py`,
`core/tool_manager.py`, `main.py`.

v0.7 bleibt weiterhin offen/ungetaggt (Dienste, Treiber noch offen) -
kein Tag gesetzt, keine v0.7-Abschlussentscheidung getroffen.

## 2026-07-02 - Jarvis-Eigenstart als Roadmap-Baustein aufgenommen (Kap.-19-Dokumentation, wartet auf Handbook v3.6)

**Kontext:** Wolfgang stellte fest, dass automatischer Start von Jarvis mit
Windows im Handbook nicht vorgesehen ist, und wollte dies sauber in
Architektur und Roadmap aufnehmen - zunaechst rein dokumentarisch, kein
Code.

**Prozesskonflikt erkannt und geklaert:** Ein direkter `.docx`-Edit
haette Kap. 2 verletzt (Handbook aendert sich nur ZWISCHEN Versionen,
nicht mitten in v0.7, das weder committed noch getaggt ist). Wolfgang
wurde die Wahl zwischen "Kap.-19-Mechanismus nutzen" (Entscheidung
sofort in PROJECT_STATE.md/logbook.md festhalten, Handbook-Text
vorbereiten, `.docx`-Edit erst bei v3.6) und "Handbook jetzt direkt
bearbeiten" (explizite Ausnahme von Kap. 2) vorgelegt. Entscheidung:
Kap.-19-Mechanismus - identisches Muster wie bei der
Post-Arbeitsmodule-Generalisierung in v0.6.

**Entscheidung (vollstaendig, ab sofort massgeblich bis Handbook v3.6):**
Zweck, Scope, Nicht-Scope und vorbereiteter Handbook-Text stehen im
Abschnitt "Ausstehende Handbook-Erweiterung" von `docs/PROJECT_STATE.md`.
Kurzfassung: Jarvis startet automatisch nach der Windows-Anmeldung,
kein manueller Start noetig, laeuft dauerhaft im Hintergrund. Scope:
HKCU Run-Key oder Benutzer-Startup-Ordner, keine Administratorrechte,
eigener Aktivieren-/Deaktivieren-Command, kein HKLM, keine
Aufgabenplanung, kein Windows-Dienst. Nicht-Scope: keine
Hintergrunddienste, keine Mehrbenutzer-Installation, keine
Administratorrechte.

**Versionsempfehlung (Product-Owner-Korrektur 2026-07-02):** Eigenstaendiger
Infrastruktur-/Runtime-Baustein nach Abschluss von v0.7 und vor Beginn
der Multi-KI-Erweiterung (v0.8) - nicht Ende von v0.7/Phase 4, wie
urspruenglich vorgeschlagen. Begruendung (Wolfgang): der automatische
Start von Jarvis betrifft die Laufzeit des Assistenten selbst und
gehoert architektonisch nicht zum fachlichen Schwerpunkt PC-Admin
(Kap. 13/17), sondern zur spaeteren Runtime des Gesamtsystems. Technische
Naehe zu den in Phase 3 (ADR-022) gebauten Mechanismen (HKCU-
Schreibzugriff, Startup-Ordner-Verschieben) bleibt bestehen und
rechtfertigt weiterhin zeitliche Naehe zu v0.7, auch wenn thematisch
getrennt. Weiterhin nicht v0.8 selbst (thematisch "Multi-KI", nicht
Runtime) und nicht v1.0 (unnoetige Wartezeit fuer einen kleinen,
risikoarmen Baustein). Alle uebrigen Entscheidungen (Zweck, Scope,
Nicht-Scope, kein ADR-Bedarf, keine AI_START.md/README.md-Aenderung)
bleiben unveraendert.

**Keine ADR jetzt** (reine Roadmap-/Scope-Entscheidung, kein Code
betroffen - analog Power-BI-Descoping) - ADR entsteht bei tatsaechlicher
Implementierung. **Keine Aenderung an AI_START.md/README.md** (README
dokumentiert nur bereits Implementiertes, AI_START.md ist
versionsunabhaengig).

Kein Code geschrieben, keine ADR angelegt, Handbook-`.docx` unveraendert.

## 2026-07-02 - Autostart verwalten implementiert, v0.7 Phase 3 (ADR-022)

**Kontext:** Nach Commit von v0.7 Phase 2 (Ereignisprotokoll-Analyse,
ADR-021, `5f330fb`) und einer Dokumentationskorrektur (`efe067f`) wurde
per AI_START.md neu eingestiegen. Vergleich der vier verbleibenden
Kap.-17-Bausteine (Autostart verwalten, Dienste, Bereinigung, Treiber)
vorgelegt. Empfehlung: Autostart verwalten - hoechste Wiederverwendung
aus Phase 1, kleinster architektonischer Sprung. Wolfgang hat diese
Empfehlung freigegeben, aber in zwei Review-Runden wesentliche
Architekturkorrekturen am urspruenglichen Entwurf vorgenommen.

**Product-Owner-Korrekturen gegenueber dem ersten Entwurf:**
1. **Keine Blacklist** - Sicherheitsmodell bleibt bewusst einfach
   (eindeutige Zielauflösung + Stufe 2 + Bestaetigung, keine
   Sonderfaelle).
2. **Kein Nachbilden des internen `StartupApproved`-Binaerformats** -
   stattdessen eine technisch saubere Alternative mit ausschliesslich
   oeffentlich dokumentierten Registry-APIs untersucht und gefunden.
3. **Scope-Reduktion auf HKCU + Benutzer-Startup** - keine
   HKLM-Schreibzugriffe, keine Administratorrechte in dieser Phase.
4. **Kein neues Modul** - beide Commands bleiben in
   `commands/monitor.py` (KISS/YAGNI, thematische Naehe zu
   `system_status`/`analyze_pc`/`analyze_event_log`).

**Umsetzung:** `commands/monitor.py::DisableAutostartEntryCommand`/
`EnableAutostartEntryCommand`. Sicherheitsstufe 2
(`requires_confirmation = True`, kein `confirmation_phrase`).

*Registry (HKCU Run-Key):* Deaktivieren entfernt den Wert per
`winreg.DeleteValue` aus dem echten Run-Key und sichert Name+Wert im
Klartext (`REG_SZ`) in einem eigenen Jarvis-Registry-Zweig
(`HKCU\Software\Jarvis\DisabledAutostart\Run`, per `winreg.CreateKey`/
`SetValueEx`). Aktivieren schreibt den Originalwert zurueck in den
echten Run-Key und entfernt ihn aus dem Jarvis-Zweig. Bewusst
**kein** `StartupApproved`-Flag - bekannter Kompromiss: der
Task-Manager zeigt den Eintrag danach nicht als "Deaktiviert" an,
er verschwindet schlicht aus dessen Liste (funktional identisch).

*Startup-Ordner (Benutzer):* Deaktivieren verschiebt die Datei
(`Path.rename`) in einen Jarvis-Unterordner `_jarvis_disabled`
innerhalb des echten Startup-Ordners. Aktivieren verschiebt sie
zurueck. Reine Dateisystem-Operation, kein Registry-/Binaerformat-
Bezug.

*Notwendige Anpassung an Phase 1 (ADR-020):*
`_collect_startup_folder_autostart()` listete bisher alle
`Path.iterdir()`-Eintraege inklusive Unterordnern - ohne Fix wuerde
der neue `_jarvis_disabled`-Unterordner selbst als scheinbarer
Autostart-Eintrag im `analyze_pc`-Bericht auftauchen. Fix: nur noch
`item.is_file()` wird aufgenommen (Windows startet ohnehin keine
Unterordner-Inhalte direkt aus dem Startup-Ordner) - notwendige
Korrektur innerhalb der bereits freigegebenen Datei, keine
Scope-Erweiterung.

*Namensbasierte Zielauflösung (Kap. 11, nie raten):* frisch bei jedem
Aufruf, case-insensitive Teilstring-Suche. Kein Treffer im relevanten
Bereich, aber ein Treffer in HKLM/Alle-Benutzer (ueber die
Phase-1-Funktionen erkennbar) -> eigener, praeziser Fehlertext
("gefunden, aber ausserhalb des aenderbaren Bereichs") statt
irrefuehrendem "nicht gefunden". Genau ein Treffer -> Aktion wird
ausgefuehrt. Mehrere Treffer -> `Status.NEEDS_CLARIFICATION` mit den
konkreten Kandidaten, keine Aktion. Bereits deaktiviert/aktiv ->
idempotenter `Status.SUCCESS`, kein Fehler.

**Kein Blacklist-Mechanismus** (Product-Owner-Entscheidung) - Sicherheit
entsteht ausschliesslich aus eindeutiger Zielaufloesung + Sicherheitsstufe
2 + Bestaetigung. **Kein KI-Zugriff** - beide Commands liefern
deterministischen Text, kein `configure()`-Bedarf, keine Aenderung an
`main.py`. **Weiterhin in `commands/monitor.py`, kein neues Modul**
(Product-Owner-Entscheidung, KISS/YAGNI).

**Bewusst nicht enthalten:** HKLM-Schreibzugriffe, Administratorrechte/
Elevation, Startup-Ordner (Alle Benutzer) schreibend,
`StartupApproved`-Binaerformat, Blacklist, Loeschen (nur Deaktivieren),
neue Autostart-Eintraege erstellen, Bearbeiten bestehender
Befehle/Pfade, separates Rollback-/Undo-Log-System (Aktivieren selbst
ist der vollstaendige Rollback), Dienste/Bereinigung/Treiber. Keine
Aenderung an `core/ai.py`, `core/planner.py`, `core/tool_manager.py`,
`executor/executor.py` oder anderen `commands/*.py`-Dateien.

**Tests:** 22 neue Tests (`tests/test_commands_monitor.py`) -
Plattformpruefung, fehlendes target, Registry-Erfolgsfall,
Startup-Ordner-Erfolgsfall, kein Treffer, mehrere Treffer, idempotent
bereits deaktiviert/aktiv, Treffer ausserhalb des Scopes (HKLM +
Alle-Benutzer-Startup), Schreibfehler ohne Teilzustand, Stufe-2-ohne-
Phrase-Verifikation, Registrierung (je Command), sowie ein
Regressionstest fuer den `_collect_startup_folder_autostart()`-Fix
(Unterordner wird ignoriert). Vollstaendige Suite: **202/202 gruen**
(180 vorher + 22 neu). `git diff --stat` bestaetigt: nur
`commands/monitor.py` und `tests/test_commands_monitor.py` geaendert,
`docs/adr/ADR-022.md` neu - keine Aenderung an `main.py` oder anderen
Kernmodulen.

v0.7 bleibt weiterhin offen/ungetaggt (Dienste, Bereinigung, Treiber
noch offen) - kein Tag gesetzt, keine v0.7-Abschlussentscheidung
getroffen.

## 2026-07-02 - Ereignisprotokoll-Analyse implementiert, v0.7 Phase 2 (ADR-021)

**Kontext:** Nach Commit von v0.7 Phase 1 (PC-Analyse, ADR-020, `48f0f83`)
wurde per AI_START.md neu eingestiegen und ein technischer Vergleich der
fuenf verbleibenden Kap.-17-Bausteine (Ereignisprotokoll, Dienste,
Autostart-Verwaltung, Bereinigung, Treiber) nach Nutzen, Risiko/
Sicherheitsstufe, Komplexitaet, Testbarkeit, Passung zu ADR-020 und
ADR-Bedarf vorgelegt. Empfehlung: Ereignisprotokoll, da als einziger
Baustein ohne Sicherheitsstufen-Sprung (weiterhin Stufe 0) direkt in
das ADR-020-Muster passt. Wolfgang hat diese Empfehlung als Product
Owner freigegeben.

**Product-Owner-Vorgaben (vollstaendig uebernommen):** Intent
`analyze_event_log`, Sicherheitsstufe 0, rein lesend, Windows-only mit
klarer Fehlermeldung, Auswertung von `System` und `Application`, nur
Fehler/Warnungen, begrenzte Anzahl/Zeitraum (kein kompletter Dump),
Python sammelt/strukturiert deterministisch, KI formuliert nur,
Pflicht-Disclaimer wie bei `analyze_pc`/KPI, Umsetzung in
`commands/monitor.py`, gleiches dupliziertes `configure()`-Muster,
keine neue gemeinsame Abstraktion. ADR-021 zuerst entworfen, danach
implementiert.

**Umsetzung:** `commands/monitor.py::AnalyzeEventLogCommand`.
Datenquelle `wevtutil` (Windows-Bordmittel) ueber `subprocess` -
bewusst keine neue Abhaengigkeit (`pywin32`/`win32evtlog` verworfen).
Aufruf pro Log: `wevtutil qe <Log> /q:"*[System[(Level=2 or Level=3)]]"
/c:20 /rd:true /f:RenderedXml` - serverseitige Filterung auf
Error/Warning, Begrenzung auf 20 Eintraege, neueste zuerst.
`/f:RenderedXml` statt `/f:text` gewaehlt, weil die XML-Tag-Namen
sprachversions-unabhaengig sind (nur Textinhalte wie "Level" sind auf
Windows lokalisiert, z. B. "Fehler") - loest das Problem strukturell
statt mit fragilem Text-Parsing. Parsing ueber
`xml.etree.ElementTree` (Standardbibliothek) - wevtutil liefert pro
Event ein eigenstaendiges `<Event>`-Wurzelelement ohne gemeinsame
Klammer, die rohe Ausgabe wird deshalb vor dem Parsen in ein
synthetisches `<Events>`-Element gehuellt.

Jede der zwei Log-Quellen (System, Application) wird einzeln gegen
`FileNotFoundError`, `subprocess.TimeoutExpired`,
`subprocess.CalledProcessError` und `ET.ParseError` abgesichert - ein
Fehlschlag bei einer Quelle liefert nur einen Fehlertext, kein
Totalausfall (gleiches Prinzip wie die vier Autostart-Quellen in
ADR-020). Schlagen beide Quellen fehl, liefert der Command
`Status.FAILED` ohne die KI mit leeren Daten zu befragen - anders als
bei `analyze_pc` gibt es hier keine weitere unabhaengige Datenquelle,
die den Bericht traegt.

KI bekommt die strukturierten Eintraege (Zeit, Quelle, Event-ID,
Stufe, gekuerzte Meldung) als Text mit der Anweisung, nur zu
formulieren/zusammenzufassen, nichts nachzuzaehlen - derselbe
Pflicht-Disclaimer wie bei `analyze_pc` (bereits vorhandene
`_DISCLAIMER`-Konstante in `monitor.py`, keine neue Duplizierung
noetig). Nutzt die aus ADR-020 bereits vorhandene
`configure()`/`_require_ai_engine()`-Infrastruktur in
`commands/monitor.py` - **keine Aenderung an `main.py`** noetig, die
`monitor_commands.configure(ai)`-Verdrahtung existiert bereits.

**Bewusst nicht enthalten:** Security-Log (sensibler, eigene spaetere
Diskussion), Loeschen von Log-Eintraegen, automatische
Reparaturmassnahmen, Dienste/Autostart-Schreibzugriff/Bereinigung/
Treiber (weiterhin offene, separat zu priorisierende Kap.-17-Bausteine).
Keine Aenderung an `core/ai.py`, `core/planner.py`,
`core/tool_manager.py`, `executor/executor.py` oder anderen
`commands/*.py`-Dateien.

**Tests:** 16 neue Tests (`tests/test_commands_monitor.py`) - Plattform-
pruefung, XML-Parsing (Feldextraktion, Kuerzung langer Meldungen, leere
Ausgabe), alle vier Fehlerpfade pro Log-Quelle, Erfolgsfall mit
KI-Aufruf-Verifikation (strukturierter Text + Disclaimer), Level-/
Anzahl-Filter-Verifikation in den `wevtutil`-Aufrufparametern,
Teilausfall-bleibt-erfolgreich, Totalausfall-beider-Quellen-liefert-
FAILED-ohne-KI-Aufruf, Nicht-konfiguriert-Fehler, keine Bestaetigung
noetig, Registrierung. Vollstaendige Suite: **180/180 gruen** (164 vorher
+ 16 neu). `git diff --stat` bestaetigt: nur `commands/monitor.py` und
`tests/test_commands_monitor.py` geaendert, `docs/adr/ADR-021.md` neu -
keine Aenderung an `main.py` oder anderen Kernmodulen.

v0.7 bleibt weiterhin offen/ungetaggt (Dienste, Treiber, Bereinigung,
Autostart-Schreibzugriff noch offen) - kein Tag gesetzt, keine
v0.7-Abschlussentscheidung getroffen.

## 2026-07-02 - PC-Analyse implementiert, v0.7 Phase 1 (ADR-020)

**Kontext:** Nach Handbook v3.5 war "PC-Admin" (Kap. 13) der naechste
Roadmap-Baustein. Kap. 17 buendelt dafuer sechs bis sieben eigenstaendige
Faehigkeiten - zu gross fuer einen ersten Schritt. Wolfgang hat
"System-Analyse/Ueberwachung erweitern" priorisiert und den Scope auf
drei rein lesende Faehigkeiten praezisiert: Festplattenbelegung,
laufende Prozesse (Top-CPU/Top-RAM), Autostart-Programme (nur
anzeigen) - gemeinsame erste Umsetzung der "System-Analyst-Vision"
(Kap. 17).

**Product-Owner-Entscheidungen (vollstaendig uebernommen):**
1. KI-narrativ wie bei KPI - Python sammelt/strukturiert deterministisch,
   KI formuliert nur den Bericht.
2. Kein neuer gemeinsamer AI-Baustein - `monitor.py` dupliziert das
   `configure()`-Muster aus `reports.py` (ADR-015), Abstraktion erst bei
   einem dritten Verwender pruefen.
3. Doppelte-Prozesse-Erkennung in Phase 1 (nur Hinweis, keine
   Fehlerbewertung).
4. Autostart aus beiden Quellen: Registry Run-Keys UND Startup-Ordner.
5. Top 5 Prozesse je Kategorie (CPU, RAM).
6. Intent-Name `analyze_pc`.

**Umsetzung:** `commands/monitor.py::AnalyzePcCommand` (Sicherheitsstufe
0). Festplatten ueber `psutil.disk_partitions()`/`disk_usage()`.
Prozesse ueber zwei `psutil.process_iter()`-Durchlaeufe mit
`_PROCESS_SAMPLE_INTERVAL` (0,5s) Pause (gleiches Muster wie
`system_status`, ADR-011) - daraus Top 5 CPU, Top 5 RAM,
mehrfach laufende Prozesse (`collections.Counter`). Autostart aus
Registry (`HKCU`+`HKLM` ueber `winreg`, Python-Standardbibliothek,
keine neue Abhaengigkeit) und Startup-Ordner (Benutzer + Alle
Benutzer) - jede der vier Quellen einzeln abgesichert, ein
Fehlschlag liefert nur einen Fehlertext, kein Totalausfall. KI
bekommt die fertige Tabelle als Text mit der Anweisung, nur zu
formulieren, nichts nachzurechnen - derselbe Pflicht-Disclaimer wie
bei `analyze_report`/`calculate_kpi` (als eigene Konstante
dupliziert, kein Zugriff auf `commands.reports`-interne Namen).

**`configure()`-Muster bewusst dupliziert** statt einer gemeinsamen
Abstraktion mit `reports.py` (Wolfgangs Entscheidung 2) - `main.py`
verdrahtet zusaetzlich `monitor_commands.configure(ai)`.

**Zirkelimport von Anfang an vermieden:** gleicher `TYPE_CHECKING`-Trick
wie bei ADR-015, diesmal proaktiv angewendet statt erneut entdeckt -
verifiziert mit `from core.ai import AIEngine` als allererste Zeile
eines frischen Prozesses.

**Plattformpruefung:** `winreg` existiert nur unter Windows - Import
per `try/except ImportError` abgesichert, `execute()` liefert eine
klare Fehlermeldung statt Absturz auf Nicht-Windows-Systemen.

**Keine Aenderung an** `core/ai.py`, `core/planner.py`,
`core/tool_manager.py`, `executor/executor.py` oder anderen
`commands/*.py`-Dateien - per `git diff --stat` verifiziert (leer).

**Tests:** 12 neue Tests (`tests/test_commands_monitor.py`) -
Plattformpruefung, Festplatten, Top-Prozesse CPU/RAM, doppelte
Prozesse, defekter Einzelprozess wird uebersprungen statt den ganzen
Befehl scheitern zu lassen, Registry beide Hives, Registry-Teilausfall,
Startup-Ordner, KI bekommt strukturierten Text + Disclaimer,
Fehlermeldung bei fehlender Konfiguration, keine Bestaetigung noetig,
Registry-Eintrag. 164 Tests gesamt, alle gruen.

**Bewusst nicht umgesetzt (Phase 1):** Windows-Ereignisprotokoll,
Optimierung/Bereinigung, Registry-Aenderungen, Dienste, Treiber.

**Naechster Schritt:** v0.7 Phase 2 NICHT begonnen - naechste
Priorisierung liegt beim Product Owner.

**Siehe auch:** ADR-020 (docs/adr/ADR-020.md), README.md Abschnitt
"PC-Analyse (v0.7 Phase 1, ADR-020)", CHANGELOG (v0.7.0).

## 2026-07-02 - v0.6 abgeschlossen und getaggt, Handbook v3.5 (ADR-019)

**Kontext:** Wolfgang hat als Product Owner nach ausdrücklicher Prüfung
des v0.6-Abschlusses (Handbook-Vergleich, siehe Eintrag "v0.6 – noch
nicht releasebereit" unten) den manuellen Smoke-Test selbst vorbereitet
und durchgeführt.

**Manueller Smoke-Test (Handbook Kap. 14/15/28):** Echten Telegram-Bot
über BotFather angelegt, Bot-Token und eigene Chat-ID ermittelt,
`telegram_main.py` mit echten Umgebungsvariablen gestartet. Getestet
und von Wolfgang bestätigt:
- Bot startet erfolgreich, Verbindung zu Telegram hergestellt
  (Long-Polling-Log sichtbar).
- `chat`, `remember_fact`, `forget_fact`, `system_status` funktionieren
  ueber den echten Bot.
- Nicht erlaubte Befehle (getestet: `install_program`) werden korrekt
  mit einer Ablehnungsmeldung abgewiesen, nicht ausgefuehrt.
- Bot beendet sich sauber per Strg+C (`Application.stop() complete`,
  kein Traceback).
- Keine ERROR-Eintraege im Log (`logs/2026-07-02-telegram.log`).

Damit sind die allgemeinen Definition-of-Done-Kriterien (Kap. 28:
Smoke Test, manueller Test aller Kernfunktionen) fuer v0.6 erstmals
tatsaechlich erfuellt - vorher gab es nur den automatisierten,
gemockten Testlauf.

**Release-Schritte (nach Wolfgangs ausdruecklicher Freigabe):**
1. Komplette Testsuite erneut ausgefuehrt: 152/152 gruen. Arbeitsverzeichnis
   sauber, keine offenen Feature-Aenderungen.
2. Tag `v0.6` gesetzt (annotierter Tag auf Commit `3f81e69`).
3. Handbook auf v3.5 aktualisiert (siehe ADR-019): Kap. 13 (v0.6 als
   abgeschlossen markiert, Lerninhalte-Spalte auf das tatsaechlich
   Genutzte korrigiert), Kap. 16 (Telegram-Bot-Status auf "Umgesetzt",
   neue Praezisierung: Web-Interface/WireGuard VPN sind Alternativen,
   keine Pflichtbestandteile), Kap. 10 (neues, dauerhaftes
   Fernzugriff-Sicherheitsprinzip - gilt fuer alle kuenftigen
   Fernzugriffskanaele, nicht nur Telegram), Kap. 27 (Praezisierung
   v3.5), Kap. 28 (neuer v0.6-DoD-Abschnitt), Kap. 29 (Backlog um die
   Generalisierung der Post-Arbeitsmodule ergaenzt - Wolfgangs Hinweis
   vom Vortag, reine Richtungsdokumentation, keine Architekturaenderung).
4. Vollstaendiger Text-Diff v3.4 -> v3.5 geprueft - nur die
   beabsichtigten Aenderungen, keine Kollateralschaeden.

**Bewusst NICHT geaendert:** Kap. 19 (generalisierte PO-Entscheidungs-
Regel seit v3.4 bleibt gueltig), Kap. 22/30 (keine neuen v0.6-Erkenntnisse
dafuer).

**Tests:** 152/152 gruen (keine Code-Aenderung in dieser Sitzung).

**Naechster Schritt:** Handbook v3.5 vollstaendig lesen und Projektstand
gemaess AI_START.md erneut verifizieren, danach gemeinsam mit Wolfgang
die Planung von v0.7 beginnen (noch nicht begonnen).

**Siehe auch:** ADR-018 (docs/adr/ADR-018.md), ADR-019
(docs/adr/ADR-019.md), README.md Abschnitt "Telegram-Fernzugriff
(v0.6, abgeschlossen, ADR-018)", CHANGELOG (v0.6/Handbook v3.5).

## 2026-07-01 - Product-Owner-Hinweis: Generalisierung Post-Arbeitsmodule (kuenftige Handbook-Version)

**Kontext:** Wolfgang hat nach Abschluss von v0.6 Phase 1 (Telegram)
einen Hinweis fuer die naechste Handbook-Aktualisierung gegeben, keine
sofortige Aenderung.

**Hinweis:** Die bisherigen Post-spezifischen Arbeitsmodule
(`analyze_report`/ADR-015, `calculate_kpi`/ADR-016) sollen
kuenftig staerker verallgemeinert werden, statt dauerhaft
"Tabellen-Auswertung"/Auswertung-spezifisch zu bleiben. Zielbild fuer eine
kommende Version: allgemeine Excel-/Report-Analyse - Dateien lesen,
Datenstrukturen erkennen (statt fester Spalten-Alias-Listen),
Auffaelligkeiten zusammenfassen, KPI aus beliebigen tabellarischen
Daten berechnen, domaenenspezifische Begriffe (Auswertung,
Standort, Ort, ...) nur noch als optionaler Kontext statt als
Voraussetzung.

**Ausdruecklich festgelegt:**
- Keine Codeaenderung jetzt - die bestehenden v0.5-Commands
  (`read_excel`, `analyze_report`, `calculate_kpi`) bleiben
  unveraendert.
- Kein Refactoring waehrend v0.6.
- Keine ADR jetzt - es handelt sich um eine Priorisierungs-/
  Richtungsentscheidung fuer eine kuenftige Handbook-Version (v3.5),
  keine bereits umgesetzte Architekturentscheidung. Eine ADR folgt
  erst, wenn die Generalisierung tatsaechlich als Architekturaenderung
  umgesetzt wird (analog zum Vorgehen bei allen bisherigen Bausteinen).

**Dokumentiert in:** `docs/PROJECT_STATE.md` (neuer Abschnitt
"Product-Owner-Hinweis fuer kuenftige Handbook-Version (v3.5, noch
nicht umgesetzt)" sowie ein Verweis in den Feature-TODOs).

**Naechster Aufgriffspunkt:** Bei der naechsten geplanten
Handbook-Aktualisierung (nach Abschluss von v0.6, analog zum
v3.3->v3.4-Nachzug, Kap. 2) - dann mit vollem
Handbook-Pruefungs-/technischer-Vorschlag-Prozess, nicht vorher.

**Status:** Reine Dokumentation einer Absicht, keine Code- oder
Architekturaenderung. Tests unveraendert 152/152 gruen.

## 2026-07-01 - Telegram-Fernzugriff implementiert, v0.6 Phase 1 (ADR-018)

**Kontext:** Nach Handbook v3.4 war "Handy" (Telegram-Bot, Fernzugriff)
laut Kap. 13 der naechste Baustein. Handbook-Pruefung (Scope/DoD/
Architektur/Sicherheitsmodell/Bibliotheken/Registry-Integration/Tests/
Risiken) zeigte: Kap. 16 empfiehlt Telegram-Bot klar als Einstieg, aber
keine Aussage zu Befehlsumfang, Sicherheitsstufen bei Fernzugriff,
Technik oder Architektur. Fernzugriff ist zudem eine grundsaetzlich
neue Risikoklasse (Kap. 10 adressiert nur lokale Eingabe).

**Product-Owner-Entscheidungen (vollstaendig uebernommen):**
1. Befehlsumfang: nur `chat`/`remember_fact`/`forget_fact`/
   `system_status`, keine Datei-/Report-/KPI-Zugriffe, kein
   `install_program`/`shutdown_pc`.
2. Sicherheitsstufen 0/ausgewaehlte Stufe-1 remote erlaubt, 2/3/4
   gesperrt.
3. Long-Polling statt Webhook/FastAPI/ngrok (einfacher, kein
   oeffentlicher Server, privater Start).
4. Separater Einstiegspunkt `telegram_main.py`, `main.py` unveraendert.
5. Autorisierung ausschliesslich per Umgebungsvariablen
   (`JARVIS_TELEGRAM_BOT_TOKEN`, `JARVIS_TELEGRAM_ALLOWED_CHAT_ID`).
6. Kein gleichzeitiger Betrieb von Konsole und Telegram in Phase 1.
7. Ganzer Plan wird abgelehnt, sobald ein Schritt eines Mehrschritt-Plans
   nicht erlaubt ist (keine Teilausfuehrung) - explizit nachgefragt und
   bestaetigt, nachdem ich das als offene Kleinigkeit im technischen
   Vorschlag benannt hatte.

**Umsetzung:** `telegram_main.py` (neuer, komplett additiver
Einstiegspunkt). Zwei unabhaengige Sicherheitsmechanismen in
`rejection_reason()`: Intent-Whitelist plus ein davon unabhaengiger
Check auf `command.requires_confirmation` (Defense in Depth - greift
auch, falls die Whitelist spaeter versehentlich erweitert wuerde).
`filter_plan()` wertet alle Planschritte aus und verwirft den gesamten
Plan bei einem einzigen nicht erlaubten Schritt. `TelegramSpeech`
erfuellt dieselbe `say()`/`listen()`-Schnittstelle wie `SpeechEngine`,
damit `Executor` unveraendert wiederverwendet werden kann - beide
Methoden sind fail-closed (sollten in Phase 1 nie tatsaechlich
gebraucht werden, da nur bestaetigungsfreie Intents durchkommen).
`JarvisBridge` verdrahtet dieselben Bausteine wie `main.py`
(`Config`/`AIEngine`/`Planner`/`Executor`/`JsonMemoryStore`/
`LongTermMemory`), `ai` ist injizierbar fuer Tests (gleiches Muster wie
`tests/test_integration.py::FakeAI`).

**Keine Aenderung an** `core/ai.py`, `core/planner.py`,
`core/tool_manager.py`, `executor/executor.py`, `main.py` oder
`commands/*.py` - per `git diff --stat` explizit verifiziert (leer).

**Tests:** 18 neue Tests (`tests/test_telegram_main.py`) - Autorisierung,
Whitelist, Stufe-Check (inkl. hypothetischer Erweiterung der Whitelist
um einen Stufe-2-Intent), Ganzer-Plan-Ablehnung, fail-closed
`TelegramSpeech`, `JarvisBridge`-Verhalten (autorisiert/nicht
autorisiert, chat, remember_fact, Ablehnung ohne Ausfuehrung,
Mehrschritt-Ablehnung ohne Teil-Persistenz, History-Persistenz). 152
Tests gesamt, alle gruen.

**Bewusst nicht umgesetzt (Phase 1):** gleichzeitiger Betrieb, Datei-/
Report-/KPI-Zugriffe, `install_program`/`shutdown_pc`, Neustart bei
Absturz des Long-Polling-Prozesses.

**Naechster Schritt:** v0.6 Phase 2 (Erweiterung des Befehlsumfangs)
NICHT begonnen - naechste Entscheidung liegt beim Product Owner.

**Siehe auch:** ADR-018 (docs/adr/ADR-018.md), README.md Abschnitt
"Telegram-Fernzugriff (v0.6 Phase 1, ADR-018)", CHANGELOG (v0.6.0).

## 2026-07-01 - Handbook v3.4: v0.5-Abschluss, Power-BI-Backlog, Governance-Regel (ADR-017)

**Kontext:** Nach dem `v0.5`-Tag hat Wolfgang angeordnet, strikt nach
AI_START.md und Handbook zu arbeiten und zuerst das Handbook auf v3.4
zu aktualisieren, bevor v0.6 geplant wird - ausschliesslich mit den
Erkenntnissen aus dem abgeschlossenen v0.5, keine neuen Features/
Roadmap-Erweiterungen.

**Technischer Weg:** `python-docx` installiert, um die vorhandene
`.docx`-Struktur (Absaetze/Tabellen mit Word-Styles) gezielt zu
bearbeiten statt sie als Text neu zu erzeugen (Tabellen wie Kap. 13
Roadmap und Kap. 29 Backlog muessen echte Word-Tabellen bleiben).
Stolperstein: `document.styles['Heading 3']` warf einen `KeyError`,
obwohl der Style nachweislich existiert (pandoc-generierte
`styles.xml`-Eigenheit) - geloest, indem Style-OBJEKTE von bestehenden
Absaetzen wiederverwendet wurden statt sie per Namens-String
nachzuschlagen.

**Umsetzung (v3.4 gegenueber v3.3):**
- Kap. 13 (Roadmap): v0.5-Kerninhalt aktualisiert - "abgeschlossen
  (siehe ADR-014/015/016)", Power BI aus aktivem Scope genommen,
  Verweis auf Kap. 29 Backlog.
- Kap. 27: neue "Praezisierung v3.4: v0.5 Abschluss".
- Kap. 28 (Definition of Done): zwei neue Abschnitte "Tabellen-Auswertung"
  und "KPI" mit Checklisten, die exakt das tatsaechlich Umgesetzte
  spiegeln (u. a. "keine KI-Arithmetik" bei KPI, "kein Sonderfall in
  core/ai.py" bei beiden). Excel-Abschnitt als "- abgeschlossen"
  markiert.
- Kap. 29 (Backlog): neue Zeile "Power BI-Integration" (Firmenrechner/
  Firmenumfeld, Pruefzeitpunkt "falls sich das Umfeld aendert").
- Kap. 19 (Governance): neue, generalisierte Regel - wie mit
  Product-Owner-Entscheidungen umgegangen wird, die zwischen zwei
  Handbook-Versionen getroffen werden (sofort verbindlich ueber
  PROJECT_STATE.md/logbook.md, Handbook-Nachzug zur naechsten Version).
  Macht einen bereits zweimal angewandten Mechanismus (v3.3-Genese,
  jetzt Power BI) als Regel explizit.
- Versions-Kopfzeile und Freeze-Hinweis auf v3.4/"Basis fuer v0.6"
  aktualisiert.

**Bewusst NICHT geaendert:** Kap. 1 (Vision, Power BI bleibt
mittelfristige Ambition), Kap. 22 (Academy-Lerninhalte), Kap. 30
(Plugin-Vision-Praezisierung aus v3.3 bleibt gueltig - kein neues
Office-Modul seit v3.3 hinzugekommen).

**Konsistenz-Pruefung:** Vollstaendiger Text-Diff zwischen v3.3- und
v3.4-Extraktion zeigt ausschliesslich die oben genannten Aenderungen -
keine unbeabsichtigten Abweichungen. Alle Tabellen (Roadmap, Backlog)
per `python-docx` inspiziert und bestaetigt.

**Tests:** Keine Code-Aenderung, 134/134 weiterhin gruen (nur zur
Bestaetigung erneut ausgefuehrt).

**Naechster Schritt:** Kap. 13/27/28 des neuen Handbooks fuer den
v0.6-Baustein (Handy: Telegram-Bot, Fernzugriff) lesen und einen
technischen Vorschlag erarbeiten - noch kein Code, noch keine
Freigabe.

**Siehe auch:** ADR-017 (docs/adr/ADR-017.md), CHANGELOG (Handbook
v3.4-Abschnitt).

## 2026-07-01 - v0.5 (aktiver Scope) abgeschlossen, finale Pruefung vor Tag

**Kontext:** Wolfgang hat nach dem KPI-Commit eine abschliessende
Pruefung vor dem `v0.5`-Tag angeordnet: komplette Testsuite,
PROJECT_STATE.md gegen Handbook v3.3 abgleichen, Vollstaendigkeit von
v0.5 sicherstellen, CHANGELOG/Logbook finalisieren, danach erst taggen.

**Tests:** `pytest tests -v` erneut vollstaendig ausgefuehrt -
134/134 gruen, keine Regression seit dem letzten Stand.

**Handbook-Abgleich:** Handbook v3.3 erneut extrahiert und Kap. 2, 10,
13, 19, 27, 28, 30 gegen den letzten bekannten Stand verglichen -
unveraendert (keine Zwischen-Versions-Aenderung, korrekt gemaess der
in Kap. 2 selbst festgelegten Regel). Kap. 13 nennt fuer v0.5
weiterhin "Tabellen-Auswertung, KPI, Power BI, Excel", Kap. 28 hat weiterhin
nur eine v0.5-Checkliste fuer Excel Phase 1 (keine fuer Tabellen-Auswertung/
KPI, da diese erst nach v3.3 per ADR-015/ADR-016 entschieden wurden -
das ist erwartet und kein Widerspruch, siehe Kap.-2-Regel: Handbook
wird erst zur naechsten Version nachgezogen).

**Vollstaendigkeit v0.5 (aktiver Scope) bestaetigt:**
- Excel lesen (ADR-014) - erledigt.
- Tabellen-Auswertung analysieren (ADR-015) - erledigt.
- KPI berechnen (ADR-016) - erledigt.
- Power BI bewusst aus aktivem Scope entfernt (Product-Owner-
  Entscheidung, siehe Eintrag oben) - kein offener Punkt, sondern eine
  getroffene Entscheidung.

**Aufgeraeumt:** Eine veraltete Git-Notiz in `docs/PROJECT_STATE.md`
korrigiert (behauptete faelschlich, der KPI-Baustein sei noch nicht
committed - war zum Zeitpunkt der Pruefung laengst committed, siehe
Commit `afe1562`).

**CHANGELOG/Logbook finalisiert:** `docs/CHANGELOG.md` um eine
abschliessende `v0.5`-Zusammenfassung ergaenzt (analog zum
`v0.4`-Abschluss), die alle drei Bausteine sowie die Power-BI-
Entscheidung in einem Eintrag buendelt.

**Status:** Konsistent und gruen - bereit fuer Tag `v0.5`.

**Siehe auch:** docs/PROJECT_STATE.md, docs/CHANGELOG.md (v0.5-Abschnitt).

## 2026-07-01 - KPI implementiert: Kennzahl deterministisch berechnet (ADR-016)

**Kontext:** Nach der Power-BI-Scope-Entscheidung war "KPI" der
naechste und aktuell letzte aktive v0.5-Baustein. Handbook-Pruefung
(wie bei Excel/Tabellen-Auswertung) ergab wieder nur ein Stichwort ohne
Format-/Sicherheits-/DoD-Angaben. Rueckfrage ergab: KI-gestuetzt (wie
Tabellen-Auswertung), Kennzahl = Kennzahl je Standort, Zielwert
aus der Spracheingabe.

**Wichtige Korrektur durch Wolfgang:** Mein erster technischer
Vorschlag sah vor, dass die KI die Prozentrechnung selbst macht
(analog zu Tabellen-Auswertung). Wolfgang hat das explizit korrigiert: KI
soll NICHT rechnen. Python berechnet deterministisch (Ist, Abweichung,
unter Zielwert), die KI bekommt nur die bereits fertige Tabelle zur
Interpretation/Formulierung. Zusaetzlich hat Wolfgang feste,
erweiterbare Alias-Listen fuer die Spalten-Erkennung vorgegeben
(Standort: standort/ort/ort/standort; Ist-Wert: ist/istwert/
wert/quote/kennzahl/kennzahl), case-insensitive,
Leerzeichen ignoriert.

**Umsetzung:** `commands/reports.py::CalculateKpiCommand` (Intent
`calculate_kpi`, Sicherheitsstufe 0) - im selben Modul wie
`analyze_report` (Kap. 27 fuehrt Reports/KPI als einen
gemeinsamen Punkt, gleiche AIEngine-Injection/`read_workbook_sheets()`-
Infrastruktur, kein zweites `configure()` in `main.py` noetig).
Kopfzeile der ersten (oder per `parameters.sheet` gewaehlten) Tabelle
wird gegen die Alias-Listen abgeglichen: 0 Treffer -> `FAILED` mit
Spaltenliste, >1 Treffer -> `NEEDS_CLARIFICATION` - nie geraten (Kap. 4).
Prozentwerte werden geparst (`%`, Komma, oder ein Excel-Bruch zwischen
0 und 1 wird ×100 genommen - dokumentierte Annahme). `zielwert` ist
Pflichtparameter, fehlt er: Rueckfrage. Die KI bekommt nur die fertige
Tabelle als Text, derselbe Pflicht-Disclaimer wie bei Tabellen-Auswertung
wird angehaengt. `Result.data["kpi"]` enthaelt die berechneten Zahlen
selbst, unabhaengig vom KI-Text nachpruefbar.

**Kein Sonderfall in `core/ai.py`:** verifiziert per direktem
`build_system_prompt()`-Aufruf - `calculate_kpi` samt Beschreibung
(inkl. Pflicht-Parameter `zielwert`) erscheint automatisch im Prompt.

**Tests:** 17 neue Tests (`tests/test_commands_reports.py`, u. a.
reine Funktionstests fuer `_parse_percentage`/`_find_matching_columns`,
Szenarien fuer fehlende/mehrdeutige Spalten, deterministische
Berechnung, KI bekommt nur die fertige Tabelle) - 134 Tests gesamt,
alle gruen.

**Damit sind alle drei aktiven v0.5-Bausteine laut Wolfgangs
Reihenfolge umgesetzt:** Excel lesen (ADR-014), Tabellen-Auswertung
(ADR-015), KPI (dieses ADR). Power BI bleibt bewusst aussen vor
(Product-Owner-Entscheidung, siehe Eintrag oben/`docs/PROJECT_STATE.md`).
Naechster Schritt ist eine Product-Owner-Entscheidung: v0.5 abschliessen
(Tag setzen) oder weitere Bausteine ergaenzen.

**Siehe auch:** ADR-016 (docs/adr/ADR-016.md), README.md Abschnitt
"KPI: Kennzahl (v0.5, ADR-016)", CHANGELOG (v0.5.2).

## 2026-07-01 - Product-Owner-Entscheidung: Power BI aus v0.5-Scope genommen

**Kontext:** Nach Tabellen-Auswertung (ADR-015) stand als naechster
Handbook-Baustein "KPI" und danach "Power BI" (Kap. 13: Kerninhalt
"Tabellen-Auswertung, KPI, Power BI, Excel"). Wolfgang hat als Product Owner
entschieden, Power BI aus dem aktiven v0.5-Scope herauszunehmen.

**Entscheidung:** Fuer Jarvis v0.5 bleibt der Fokus auf drei
Bausteinen: (1) Excel lesen (ADR-014, erledigt), (2) Tabellen-Auswertung
analysieren (ADR-015, erledigt), (3) KPI aus Excel-/Reportdaten
berechnen (naechster, aktuell letzter aktiver v0.5-Schritt). Power BI
wird NICHT praktisch implementiert und stattdessen als optionale
Unternehmensintegration bzw. spaeterer Baustein behandelt - keine
Prioritaet aktuell, kein Code geschrieben.

**Begruendung:** Power BI liegt auf dem Firmenrechner/im
Firmenumfeld - keine praktische Implementierbarkeit im aktuellen
Jarvis-Rahmen (privater Desktop-Assistent).

**Bewusst KEINE ADR:** Dies ist eine Priorisierungs-/Scope-Entscheidung
des Product Owner, keine Architekturentscheidung (Kap. 20: ADRs sind
fuer Architekturentscheidungen vorgesehen) - deshalb Dokumentation nur
in `docs/PROJECT_STATE.md` und hier, keine neue ADR-Datei.

**Handbook-Bezug:** Das Master-Handbook (Kap. 13/27) nennt Power BI
weiterhin als Teil von "Arbeitsmodule/v0.5" - der Handbook-Text wird
erst bei der naechsten geplanten Handbook-Version nachgezogen (Kap. 2,
v3.3: "Handbook wird nur ZWISCHEN zwei Versionen geaendert"). Bis
dahin gilt diese Product-Owner-Entscheidung als verbindlich und hat
Vorrang fuer die weitere Entwicklung von v0.5 gegenueber dem
aktuellen Handbook-Wortlaut.

**Status:** Aktiv, keine Code-Aenderung. `docs/PROJECT_STATE.md`
entsprechend aktualisiert (Next Goal, Feature-TODOs, neuer Abschnitt
"Product-Owner-Entscheidung: Power BI aus v0.5-Scope genommen").

**Siehe auch:** docs/PROJECT_STATE.md.

## 2026-07-01 - Tabellen-Auswertung implementiert: Datenauswertung (ADR-015)

**Kontext:** Nach Excel-Lesen (v0.5 Phase 1, ADR-014) war laut
Wolfgangs Reihenfolge "Tabellen-Auswertung" der naechste v0.5-Baustein. Da
das Handbook dafuer (anders als bei Excel) keine Formatangabe, keine
Sicherheitsstufe und keine Definition of Done enthielt, wurde zuerst
eine Handbook-Pruefung (Scope/DoD/Architektur/Sicherheitsmodell, wie
bei Excel) gemacht und dann per Rueckfrage geklaert: Datenquelle =
Excel-Datei (baut auf `read_excel` auf), erster Anwendungsfall =
Auswertung-Quote (Handbook Kap. 1 Vision-Beispiel), KI-Zusammenfassung
ist der Kern der Funktion (anders als bei `read_excel`, wo das bewusst
ausgelassen wurde).

**Architekturentscheidung (mit Wolfgang abgestimmt):** Erster Command
mit direktem KI-Zugriff ueberhaupt - bisher rief nur der Executor
`ai.answer()` auf (fuer den `chat`-Intent). Wolfgang hat Option A
bestaetigt: `AIEngine` wird per `commands.reports.configure(ai)`
injiziert, analog zum Memory-Muster (ADR-009), statt einer
Executor-Sonderbehandlung fuer diesen einen Intent. Ausserdem
bestaetigt: `AIEngine.answer()` wiederverwenden statt einer neuen
`ai.py`-Methode - eine eigene `summarize_report()` wird erst geprueft,
falls die Qualitaet nicht reicht.

**Umsetzung:** `commands/reports.py::AnalyzeReportCommand`
(Intent `analyze_report`, Sicherheitsstufe 0). Baut die
gelesenen Zeilen zu Text zusammen, uebergibt sie mit einem
Analyse-Prompt an `AIEngine.answer()`, haengt danach den von Wolfgang
vorgegebenen Pflicht-Disclaimer an ("Analyse auf Basis der gelieferten
Daten. Bitte vor Entscheidungen pruefen.") - Jarvis behauptet keine
geschaeftskritische Wahrheit.

**Refactor (DRY):** Die openpyxl-Leselogik aus
`ReadExcelCommand.execute()` wurde in eine wiederverwendbare Funktion
`commands/excel.py::read_workbook_sheets()` (plus `ExcelReadError`)
extrahiert. `ReadExcelCommand` verhaelt sich danach nachweislich
identisch - alle neun bestehenden Tests liefen nach dem Refactor
unveraendert gruen, bevor der neue Command dazukam.

**Gefundener und behobener Zirkelimport:** Ein normaler
`from core.ai import AIEngine`-Import in `commands/reports.py` haette
je nach Importreihenfolge gescheitert, weil `core/ai.py` selbst
`commands.REGISTRY` importiert (`core.ai` -> `commands` ->
`commands.reports` -> `core.ai`, noch bevor `AIEngine` dort definiert
ist). Reproduziert mit einem gezielten Test
(`from core.ai import AIEngine` als allererste Zeile eines frischen
Prozesses) - schlug wie erwartet fehl. Geloest ueber einen
`TYPE_CHECKING`-Import (Standardmuster fuer genau diesen Fall) - danach
beide Importreihenfolgen sowie `main.py` selbst erfolgreich getestet.

**Tests:** 7 neue Tests (`tests/test_commands_reports.py`, `AIEngine`
und die Excel-Lesefunktion gemockt, kein echter API-Call, keine echte
Datei) - 117 Tests gesamt, alle gruen.

**Naechster Schritt laut Wolfgangs Reihenfolge:** KPI, danach Power BI
- noch nicht begonnen, noch kein technischer Vorschlag erstellt.

**Siehe auch:** ADR-015 (docs/adr/ADR-015.md), README.md Abschnitt
"Tabellen-Auswertung: Datenauswertung (v0.5, ADR-015)", CHANGELOG
(v0.5.1).

## 2026-07-01 - Excel-Lesen implementiert, v0.5 Phase 1 (ADR-014)

**Kontext:** Nach Handbook v3.3/ADR-013 hat Wolfgang den technischen
Vorschlag fuer den Excel-Lesen-Baustein grundsaetzlich freigegeben,
mit einer Praezisierung: kein neuer command-spezifischer Sonderfall in
`core/ai.py` - die Command-`description` soll ueber den bestehenden
Registry-Mechanismus (ADR-007) ausreichen. Ausserdem: Dateipfad direkt
in der Spracheingabe reicht fuer Phase 1, kein Memory-Automatismus fuer
bekannte Report-Pfade.

**Umsetzung:** `commands/excel.py::ReadExcelCommand` (Intent
`read_excel`, Sicherheitsstufe 0 laut Handbook Kap. 10 v3.3). Liest
`.xlsx`/`.xlsm` ueber `openpyxl` (`read_only=True, data_only=True`).
Arbeitsblatt-Namen + Dimensionen im Ergebnistext, Rohdaten (pro Blatt
auf 500 Zeilen begrenzt - benannte Konstante gegen unbegrenzten
Speicherverbrauch) in `Result.data["sheets"]`. `workbook.close()` in
`finally`, da read-only-Workbooks sonst einen offenen Dateihandle
halten (unter Windows relevant). Registrierung nach dem etablierten
Rezept in `commands/__init__.py::_register_all()`, kein
`configure()`-Mechanismus noetig (zustandslos).

**`core/ai.py` bewusst NICHT angefasst:** verifiziert per direktem
Aufruf von `build_system_prompt()` - `read_excel` samt vollstaendiger
Beschreibung (Dateipfad als target, optionales `parameters.sheet`)
erscheint automatisch im Prompt, ohne dass ein Sonderfall wie bei
`remember_fact`/`forget_fact` noetig war. Unterschied: dort musste eine
feste Kategorien-Werteliste erklaert werden, hier reicht eine
ausfuehrliche `description`.

**Bewusst nicht umgesetzt (Phase 1, siehe ADR-013/ADR-014):**
Schreiben, Formatieren, Power Query, Makros, `.xls` (Legacy-Format,
`openpyxl` unterstuetzt es nicht mehr), KI-Zusammenfassung im Command
selbst (bleibt einem spaeteren Tabellen-Auswertung-Baustein ueberlassen),
bekannte/gemerkte Report-Pfade (explizite Entscheidung von Wolfgang).

**Tests:** 9 neue Tests (`tests/test_commands_excel.py`, `openpyxl`
gemockt, es wird nie eine echte Datei geoeffnet) - 110 Tests gesamt,
alle gruen.

**Naechster Schritt laut Wolfgangs Reihenfolge:** Tabellen-Auswertung (baut
auf `Result.data["sheets"]` auf), danach KPI, danach Power BI - noch
nicht begonnen.

**Siehe auch:** ADR-014 (docs/adr/ADR-014.md), README.md Abschnitt
"Excel-Lesen (v0.5 Phase 1, ADR-014)", CHANGELOG (v0.5.0).

## 2026-07-01 - Handbook v3.3: Excel-Baustein (v0.5) Scope, Sicherheitsstufen, Governance (ADR-013)

**Kontext:** Vor Beginn von `v0.5 "Arbeitsmodule"` hat Wolfgang eine
Handbook-Pruefung (v3.2) angestossen - ausgeloest durch eine externe
Ruecksprache (Handbook-Review + Dialog mit einem Mentor/"GPT") ueber
Luecken im Excel-Umfang. Ergebnis: mehrere explizite
Product-Owner-Entscheidungen, noch VOR jeglicher Excel-Implementierung
("Noch keinen Code schreiben. Erst nach meiner Freigabe implementieren.").

**Entscheidungen (Details siehe ADR-013):**
- Excel-Scope v0.5 = Phase 1, nur Lesen (oeffnen, Arbeitsblaetter/
  Tabellen/Zellen lesen, zusammenfassen). Schreiben, Formatieren,
  Power Query, Makros explizit NICHT Teil von Phase 1.
- Architektur bleibt flach (`commands/`) - keine Migration auf die
  Kap.-30-Zielstruktur (`tools/office/...`) fuer ein einzelnes Modul
  (Regel 6, YAGNI).
- Sicherheitsstufen fuer Dateizugriffe ergaenzt (Kap. 10): Excel lesen
  = Stufe 0, Excel schreiben = Stufe 2, Datei loeschen = Stufe 3.
- Outlook ist NICHT Teil von v0.5, eigene Priorisierung noetig.
- Vor Excel-Code: technischer Vorschlag (Bibliothek, Commands,
  Registry-Integration) noetig, den der Product Owner ausdruecklich
  freigeben muss.

**Handbook-Versionierung:** Da das Handbook (neu in Kap. 2 dokumentiert)
nur zwischen zwei Jarvis-Versionen geaendert werden darf, wurden alle
Praezisierungen jetzt (nach Abschluss von v0.4, vor Beginn von v0.5)
als Handbook v3.3 nachgezogen: `docs/handbook/JARVIS_MASTER_HANDBOOK_v3_3.docx`
neu angelegt (v3.2 bleibt unveraendert als Archiv). Aenderungen im
Detail: Versions-/Aenderungskopf, neue Sicherheitsstufen-Zeilen (Tab. 9),
Roadmap-Praezisierung v0.5 (Tab. 11), Excel/Outlook-Trennung (Kap. 27),
neue v0.4-/v0.5-spezifische Definition-of-Done-Kriterien (Kap. 28),
Plugin-Vision-Praezisierung (Kap. 30), Governance-Dokumente (`AI_START.md`,
`PROJECT_STATE.md`, ADR-System) offiziell in das bisher leere Kap. 19
aufgenommen, Schlussabsatz auf v3.3 aktualisiert.

**Doku-Updates:** `docs/AI_START.md`, `docs/PROJECT_STATE.md` und
`README.md` verweisen jetzt auf `v3_3.docx` statt `v3_2.docx`.
`PROJECT_STATE.md` (Latest ADR, Next Planned Version) und
`docs/CHANGELOG.md` entsprechend ergaenzt.

**Bewusst nicht umgesetzt:** Kein Excel-Code, kein technischer
Vorschlag dafuer - das war explizit NICHT Teil dieser Anweisung
("mach dann das neue Handbuch").

**Tests:** Reiner Doku-Vorgang, keine Code-Aenderung - Testlauf trotzdem
zur Sicherheit wiederholt (siehe Ergebnis weiter unten/CHANGELOG).

**Siehe auch:** ADR-013, docs/PROJECT_STATE.md, docs/CHANGELOG.md,
docs/handbook/JARVIS_MASTER_HANDBOOK_v3_3.docx.

## 2026-07-01 - v0.4 abgeschlossen, Git initialisiert und getaggt

**Kontext:** Wolfgang hat explizit den Abschluss von v0.4 angeordnet:
Dokumentation gegen das Handbook pruefen, v0.4 als vollstaendig
dokumentieren, PROJECT_STATE.md aktualisieren (Version, naechste
Version laut Handbook, technische vs. Feature-TODOs getrennt), keine
neuen Features, danach Git initialisieren/committen/taggen.

**Pruefung gegen Handbook:** Kap. 13 (Roadmap) und Kap. 27
(Now/Next/Later) definieren `v0.4` als `Kurz-/Langzeitgedaechtnis` +
`PC-Grundsteuerung`. Gegenpruefung des Codes ergab: Der
Kurzzeit-Anteil des Gedaechtnisses (`memory/store.py::JsonMemoryStore`,
`history.json`) persistiert bereits seit v0.2 tagesuebergreifend auf
Platte (nicht nur pro Sitzung) - erfuellt damit inhaltlich bereits die
in Kap. 9 beschriebene "Kurzzeit-Gedaechtnis"-Ebene ("Was hast du mir
gestern gesagt?"), zusammen mit dem Langzeitgedaechtnis (ADR-009) und
PC-Grundsteuerung (oeffnen/ueberwachen/installieren, ADR-011/ADR-012)
ist `v0.4` damit inhaltlich vollstaendig. Kein Widerspruch zwischen
PROJECT_STATE.md, Logbook, Changelog und Handbook gefunden - kein
Stop-Regel-Fall (AI_START.md).

**Aufgeraeumt vor dem Commit (kein neues Feature, reine Hygiene):**
- Versehentliche Datei `=5.9.0` geloescht - ein Shell-Redirect-Unfall
  aus einem frueheren `pip install psutil>=5.9.0`-Aufruf in dieser
  Sitzung (`>` wurde von der Shell als Redirect interpretiert), keine
  Nutzerdaten.
- `.gitignore` um `.vendor/` (47 MB gebuendelte Runtime-Pakete, gehoert
  nicht in die Versionierung, gleiche Begruendung wie `.venv/`) und
  `.git_broken_5/` (Reste eines fruehen, abgebrochenen git-init-
  Versuchs) erweitert. Bewusst NICHT geloescht, nur ausgeschlossen -
  keine destruktive Aktion ohne Rueckfrage bei unklarem Ursprung.

**CHANGELOG:** `Unreleased` zu `v0.4.1` (PC-Grundsteuerung: ueberwachen
+ installieren + Governance-Doku) gemacht und eine abschliessende
`v0.4`-Zusammenfassung ergaenzt.

**Git:** Ein vorhandenes, aber leeres `.git`-Verzeichnis (kein `git
init` mehr noetig) wurde mit einem einzigen, ehrlichen Initial-Commit
aus dem kompletten aktuellen Arbeitsstand befuellt - bewusst KEINE
rekonstruierte Commit-Historie aus alten ZIP-Staenden (Wolfgangs
ausdruecklicher Wunsch). Das im Handbook (Kap. 21) urspruenglich
vorgesehene inkrementelle Nachziehen der v0.2-/v0.3-Commit-Historie
entfaellt damit - fruehere Versionen bleiben nur in
`docs/CHANGELOG.md`/`docs/logbook.md` dokumentiert. Tag `v0.4` markiert
diesen Commit.

**Offene technische TODOs (getrennt von Feature-TODOs, siehe
PROJECT_STATE.md):** manueller Live-Test mit echtem API-Key (Definition
of Done, Kap. 28) steht noch aus - insbesondere `install_program`
real auszufuehren installiert tatsaechlich Software und sollte gezielt
freigegeben werden, statt es hier automatisiert/ungefragt zu tun.

**Tests:** 101/101 gruen, letzter Lauf vor dem Commit.

**Siehe auch:** ADR-011, ADR-012, docs/PROJECT_STATE.md, docs/CHANGELOG.md.

## 2026-07-01 - PC-Grundsteuerung Teil 2: Programme installieren (ADR-012)

**Kontext:** Direkte Fortsetzung von PC-Grundsteuerung Teil 1
(Systemueberwachung, ADR-011). Wolfgang wollte direkt weitermachen -
"installieren" war laut PROJECT_STATE.md der letzte offene
PC-Grundsteuerung-Baustein aus Kap. 27.

**Umsetzung:** Neuer Command `commands/installer.py::InstallProgramCommand`
(Intent `install_program`, Sicherheitsstufe 2 - `requires_confirmation
= True`, aber KEINE `confirmation_phrase` wie bei `shutdown_pc`/Stufe
3). Fuehrt `winget install ...` per `subprocess.run()` mit
Argumentliste aus (keine Shell, keine Command-Injection-Flaeche).
Bekannte Namen (`vlc`, `7zip`, `firefox`, `chrome`, `notepad++`) werden
ueber `KNOWN_PACKAGES` auf exakte winget-Package-IDs abgebildet (`--id
... -e`), unbekannte Ziele gehen als Freitext-Suchbegriff an winget.
`--accept-package-agreements --accept-source-agreements` verhindert
ein stilles Haengenbleiben an einer interaktiven Nachfrage. Timeout
von 300s (benannte Konstante `_INSTALL_TIMEOUT_SECONDS`, kein Magic
Value). Windows-exklusiv (winget), klare Fehlermeldung, wenn winget
selbst fehlt.

**Bewusst nicht umgesetzt:** "Deinstallieren" - obwohl Kap. 17
Installieren/Deinstallieren als gemeinsame Faehigkeit nennt, grenzt
Kap. 27 die v0.4-Priorisierung explizit auf "installieren" ein. Ein
Uninstall-Command braucht eine eigene Priorisierung und vermutlich
eine hoehere Sicherheitsstufe als Installieren.

**Tests:** 8 neue Tests (`tests/test_commands_installer.py`, winget/
subprocess/platform gemockt, es wird nie wirklich installiert) - 101
Tests gesamt, alle gruen.

**Damit ist "PC-Grundsteuerung" (Kap. 27) fuer v0.4 inhaltlich
vollstaendig:** oeffnen (v0.3), ueberwachen (ADR-011), installieren
(dieses ADR). Naechster Schritt laut Roadmap waere ein neuer
v0.4-Baustein oder der Abschluss/Tagging von v0.4 - das ist eine
Product-Owner-Entscheidung.

**Siehe auch:** ADR-012 (docs/adr/ADR-012.md), README.md Abschnitt
"PC-Grundsteuerung: Programme installieren", CHANGELOG (Unreleased).

## 2026-07-01 - PC-Grundsteuerung Teil 1: Systemueberwachung (ADR-011)

**Kontext:** Laut AI_START.md/PROJECT_STATE.md ist der naechste offene
Handbook-Baustein nach dem Langzeitgedaechtnis (v0.4, ADR-009)
"PC-Grundsteuerung (oeffnen, installieren, ueberwachen)" (Kap. 27).
"Oeffnen" existiert bereits seit v0.3. Vor der Umsetzung wurde
Wolfgang gefragt, mit welchem der beiden offenen Teile (Installieren
via winget vs. Ueberwachen via psutil) begonnen werden soll -
Entscheidung: **Ueberwachen**.

**Umsetzung:** Neuer Command `commands/monitor.py::SystemStatusCommand`
(Intent `system_status`, Sicherheitsstufe 0 - reine Leseaktion, keine
Bestaetigung noetig). Liest CPU-Auslastung und RAM (belegt/gesamt,
Prozent) ueber `psutil` aus. Registrierung in
`commands/__init__.py::_register_all()` nach dem bestehenden Muster
(Klasse + `COMMANDS`-Liste + Modul-Eintrag) - `core/ai.py`,
`planner.py`, `tool_manager.py` und `executor.py` mussten dafuer nicht
angefasst werden (neuer Intent taucht automatisch ueber die
Registry im KI-Prompt auf, siehe ADR-007). `psutil` wurde von einer
auskommentierten/optionalen Zeile zu einer festen Abhaengigkeit in
`requirements.txt`.

**Bewusst nicht umgesetzt:**
- **Temperatur** - obwohl Kap. 17 sie explizit neben CPU/RAM nennt,
  unterstuetzt `psutil.sensors_temperatures()` Windows nicht (nur
  Linux/macOS). Gleiches Prinzip wie bei Kokoro TTS ohne Deutsch
  (ADR-008): lieber offen als fehlend dokumentieren statt eine
  falsche Erwartung zu wecken.
- **Festplatten-Ueberwachung/-Bereinigung** - im Handbook ein eigener
  Punkt ("Temp-Dateien und Festplatten bereinigen"), nicht Teil der
  jetzt getroffenen Priorisierung (Regel 6, YAGNI).
- **Installieren (winget)** - bleibt der naechste offene
  PC-Grundsteuerung-Baustein.

**Tests:** 3 neue Tests (`tests/test_commands_monitor.py`, psutil
gemockt) - 93 Tests gesamt, alle gruen. Der bisher als bekannter
Fehlschlag dokumentierte Test
`tests/test_integration.py::test_end_to_end_tool_execution` lief in
diesem Durchlauf ebenfalls gruen durch (Umgebungsfrage der
Test-Ausfuehrung, keine inhaltliche Aenderung an diesem Test in
dieser Sitzung) - `docs/PROJECT_STATE.md` wird entsprechend
aktualisiert; sollte der Fehlschlag in einem spaeteren Lauf wieder
auftreten, gilt weiterhin die in ADR/Logbook dokumentierte
Windows-Ursache.

**Siehe auch:** ADR-011 (docs/adr/ADR-011.md), README.md Abschnitt
"PC-Grundsteuerung: Systemueberwachung", CHANGELOG (Unreleased).

## 2026-07-01 - GPT-Review-Follow-up fuer AI_START und PROJECT_STATE

**Entscheidung:** `docs/PROJECT_STATE.md` beschreibt den bestehenden
Testfehlschlag jetzt explizit als bekannten offenen Fehler
(`89 / 90 bestanden`, `Known Failure`, `Status`, `Ursache`) statt nur
als nacktes Testergebnis. `docs/AI_START.md` enthaelt zusaetzlich eine
Stop-Regel: Wenn die eigene Zusammenfassung nicht mit
`docs/PROJECT_STATE.md` uebereinstimmt, darf die KI keinen Code aendern
und muss zuerst den Product Owner fragen.

**Begruendung:** Das macht fuer kuenftige KI-Agenten sofort sichtbar,
dass der Testfehler nicht neu ist, und verhindert voreilige
Codeaenderungen bei widerspruechlichem Projektverstaendnis. Das staerkt
die bereits mit ADR-010 eingefuehrte dokumentationsgetriebene
Projektuebergabe, ohne die Roadmap zu veraendern.

**Tests:** Re-Run von `pytest tests -v` mit zusaetzlichem `PYTHONPATH`
auf die gebuendelten Runtime-Site-Packages bestaetigt den bekannten
Status unveraendert: `89 / 90` gruen, `Known Failure`
`tests/test_integration.py::test_end_to_end_tool_execution`.

**Status:** Dokumentations-/Governance-Schaerfung nach externem Review.
Keine Code- oder Architekturaenderung.

## 2026-07-01 - AI_START und PROJECT_STATE fuer KI-Uebergaben eingefuehrt

**Entscheidung:** `docs/AI_START.md` als verpflichtenden Einstiegspunkt
fuer kuenftige KI-Agenten eingefuehrt und `docs/PROJECT_STATE.md` als
knappe Statusdatei angelegt. Der verbindliche Changelog liegt jetzt
unter `docs/CHANGELOG.md`; `CHANGELOG.md` im Projekt-Root bleibt nur
als Verweis bestehen.

**Begruendung:** Jarvis ist laut Master-Handbook dokumentationsgetrieben.
Andere KI-Agenten sollen das Projekt deshalb nicht ueber spontane
Codeanalyse, sondern ueber dieselbe dokumentierte Lesereihenfolge,
dieselben Entscheidungsgrenzen und denselben Zustandsabgleich
uebernehmen koennen.

**Status:** Governance-/Dokumentations-Ergaenzung. Keine Code- oder
Roadmap-Aenderung.

**Tests:** `pytest tests -v` nach der Dokumentationsaenderung mit
zusaetzlichem `PYTHONPATH` auf die gebuendelten Runtime-Site-Packages
ausgefuehrt. Ergebnis: 89 Tests gruen, 1 bestehender Fehlschlag
(`tests/test_integration.py::test_end_to_end_tool_execution`), weil
der Test den POSIX-Startpfad patcht, der Code auf Windows aber
korrekterweise `os.startfile('EXCEL.EXE')` nutzt.

**Falsifizierbarkeit:** Diese Ergaenzung gilt als unzureichend, wenn
ein neuer KI-Agent trotz `AI_START.md` weiterhin ohne Handbook- und
State-Abgleich implementiert oder wenn `PROJECT_STATE.md` nicht
laufend mit Logbook/Changelog synchron gehalten wird.

**Naechste Schritte:** Kuenftige Aenderungen muessen
`docs/PROJECT_STATE.md`, `docs/CHANGELOG.md` und `docs/logbook.md`
verbindlich mitpflegen. Bei echten Architekturaenderungen kommt wie
bisher eine neue ADR dazu.

## 2026-07-01 - v0.2.1-Patch übernommen + v0.3 gebaut

**Entscheidung:** v0.2.1-Stabilisierungspatch (aus jarvis_v0.2.1.zip)
in den Arbeitsordner übernommen, danach direkt v0.3 (Planner, Tool
Manager, Executor, echte Chat-Antworten, Unit-Tests) aufgesetzt - der
Downloads-Ordner hatte noch den unveränderten v0.2-Stand, der Patch
lag fertig, aber ungenutzt daneben.

**Begründung:** Kein Grund, den fertigen v0.2.1-Patch nicht sofort
einzuspielen (Regel 5: Keep it Working - eine bereits getestete,
kleine Verbesserung nicht liegen lassen). v0.3 war laut Roadmap
(Kap. 13) und Definition of Done (Kap. 28) der nächste Schritt.

**Falsifizierbarkeit:** Diese Reihenfolge (Patch + v0.3 in einer
Sitzung statt einzeln committed) gilt als falsch, wenn dadurch ein
Zwischenschritt nicht mehr einzeln nachvollziehbar/revertierbar ist.
Gegenmaßnahme: Diese Änderungen sind in `git` noch nicht committed -
beim ersten `git init` sollten sie in der Reihenfolge Baseline ->
v0.2.1-Patch -> Planner -> Tool Manager -> Executor -> Tests einzeln
committet werden (siehe docs/CHANGELOG.md fuer die genaue Aufteilung).

**Status:** v0.3 Definition of Done - siehe docs/CHANGELOG.md fuer Details.
Piper TTS (letzter offener Punkt aus Kap. 28, v0.3-spezifisch) bewusst
NICHT umgesetzt - eigenständiges Audio-Thema, separat angehen.

**Nächste Schritte:**
- Piper TTS statt Konsolen-Speech (v0.3 Rest-Scope oder v0.4)
- Echten API-Key in `config.json` eintragen und einmal live testen
- Git-Repo initialisieren und Commit-Historie gemäß Kap. 21 nachziehen

## 2026-07-01 - Lessons Learned: Structured Outputs scheitert bei offenen Objekten

**Fehler:** Live-Test (echter API-Key, echter Aufruf) schlug fehl mit
`400 Bad Request`: "In context=('properties', 'parameters'),
'additionalProperties' is required to be supplied and to be false."
Alle 31 Unit-/Integrationstests waren zu diesem Zeitpunkt grün - der
gemockte OpenAI-Client hat den echten API-seitigen Constraint nicht
abgebildet.

**Ursache:** OpenAI's strict json_schema-Modus verlangt
`additionalProperties: false` auf JEDER Verschachtelungsebene. Unser
`parameters`-Feld ist aber absichtlich ein offenes Objekt (Inhalt
hängt vom Intent ab, z. B. `confirmed` bei shutdown_pc, nichts bei
chat) - das widerspricht sich mit strict mode.

**Entscheidung:** response_format von `json_schema` (strict) auf
`json_object` umgestellt. Garantiert weiterhin gültiges JSON, aber
kein festes Schema mehr - dafür bleibt `parameters` flexibel. Die
Feldstruktur wird stattdessen wieder über den SYSTEM_PROMPT
vorgegeben (wie in v0.2, vor dem v0.2.1-Patch).

**Lesson Learned:** Gemockte Unit-Tests prüfen nur unsere eigene
Parsing-Logik, nicht ob die Anfrage von der echten API akzeptiert
wird. Für Änderungen an `response_format`/Request-Parametern braucht
es zusätzlich mindestens einen echten Live-Test mit gültigem API-Key,
bevor sie als "fertig" gelten - Definition of Done sollte das für
API-Contract-Änderungen künftig explizit fordern.

**Falsifizierbarkeit:** Gilt als behoben, wenn `python main.py` mit
echtem Key mehrfach unterschiedliche Eingaben ohne 400-Fehler
verarbeitet. Gilt als unzureichend, wenn json_object-Modus weiterhin
gelegentlich kein valides JSON liefert (dann: Retry-Logik statt
striktem Schema erwägen).

## 2026-07-01 - Lessons Learned: shutil.which() findet Excel nicht auf Windows

**Fehler:** Live-Test: "öffne excel" wurde korrekt als Intent erkannt
(open_program, target=Excel, confidence=1.0), aber Ausführung meldete
"Excel konnte nicht gefunden werden."

**Ursache:** `shutil.which()` durchsucht ausschließlich die PATH-
Umgebungsvariable. Excel (wie viele andere über den Installer
registrierte Windows-Programme) liegt praktisch nie im PATH, obwohl
es korrekt installiert ist - Windows selbst löst "excel" im
Ausführen-Dialog/Startmenü über die Registry unter
`HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\EXCEL.EXE`
auf, nicht über PATH.

**Entscheidung:** `OpenProgramCommand` verzweigt jetzt nach
`platform.system()`: unter Windows wird `os.startfile(executable)`
verwendet (gleiche Auflösung wie Startmenü/Ausführen-Dialog), unter
Linux/Mac bleibt `shutil.which()` + `subprocess.Popen()` wie bisher.

**Lesson Learned:** Bei Windows-spezifischen System-Commands reicht
es nicht, nur an POSIX-Tools (`shutil.which`, PATH) zu denken - die
Windows-Programmauflösung funktioniert grundlegend anders. Künftige
System-Commands (installer.py, cleaner.py etc. aus Kap. 17) sollten
das von Anfang an berücksichtigen.

**Falsifizierbarkeit:** Gilt als behoben, wenn "öffne excel", "öffne
notepad" und ein nicht existierendes Programm auf dem echten
Windows-Rechner die erwarteten Ergebnisse liefern (✓/✓/✗).

## 2026-07-01 - Piper TTS ergänzt, v0.3 Definition of Done erfüllt

**Entscheidung:** `SpeechEngine.say()` spricht Text zusätzlich zur
Konsolenausgabe über Piper TTS (lokal/offline), wenn Paket, Modell und
Windows-Plattform vorhanden sind - sonst automatischer Fallback auf
reine Konsole. Details siehe ADR-005.

**Begründung:** Letzter offener Punkt der v0.3 Definition of Done
(Kap. 28). Kein automatischer Modell-Download beim Start (Regel 6:
keine Magie) - stattdessen expliziter, dokumentierter Einmal-Schritt.

**Status v0.3 Definition of Done - jetzt vollständig:**
- [x] speech.py/commands.py/ai.py/config.py ausgelagert und getestet
- [x] Gesprächsverlauf aktiv (letzte 20 Nachrichten)
- [x] Planner zerlegt Aufgaben in Schritte
- [x] Tool Manager wählt Tool anhand der Aufgabe
- [x] Executor meldet ✓ / ✗ / ?
- [x] Piper TTS ersetzt pyttsx3 (bzw. ergänzt die bisherige
      Konsolenausgabe - pyttsx3 war in v0.2 bereits entfernt)
- [x] Erste Unit Tests vorhanden (41 Tests: ai, commands, memory,
      planner, executor, speech, integration/e2e)
- [ ] Git-Tag `v0.3` erstellt (noch kein Git-Repo initialisiert -
      siehe Nächste Schritte)

**Nächste Schritte:**
- `git init` + Commit-Historie gemäß Kap. 21 nachziehen, dann `v0.3`
  taggen
- Piper-Sprachmodell einmalig herunterladen und `tts_enabled: true`
  setzen, um die Sprachausgabe live zu testen
- Laut Kap. 27 (Now/Next/Later) ist danach NICHT automatisch "mehr
  Commands" o.ä. dran, sondern erst v0.4 (Kurz-/Langzeitgedächtnis,
  PC-Grundsteuerung) - Regel: kein Next-Feature vor Abschluss aller
  Now-Punkte.

## 2026-07-01 - Sicherheitsvorfall: "Ende" hat echten PC-Shutdown ausgelöst

**Vorfall:** Nutzer tippte "Ende" um Jarvis zu beenden. Wort war nicht
in der Exit-Liste, ging an die KI, wurde als shutdown_pc erkannt.
Nutzer bestätigte mit "ja" (in der Annahme, Jarvis zu beenden) - der
echte Windows-PC wurde heruntergefahren.

**Ursache:** Drei unabhängige Lücken gleichzeitig - siehe ADR-006 für
die volle Analyse. Kernproblem: Sicherheitsstufe 3 ("kritische
Änderungen", Kap. 10) war technisch nicht stärker abgesichert als
Stufe 2 - beide akzeptierten ein einfaches "ja".

**Entscheidung:** Alle drei Lücken behoben (Exit-Wörter erweitert,
SYSTEM_PROMPT-Guardrail, `confirmation_phrase`-Mechanismus für Stufe-
3-Commands). Siehe ADR-006.

**Lesson Learned:** Ein als "Sicherheitsfeature" gedachter
Mechanismus (Bestätigung vor kritischen Aktionen) ist nur so gut wie
seine schwächste Ausprägung. "Bestätigung erforderlich" pauschal für
alle kritischen Aktionen zu implementieren war zu grob - Stufe 2 und
Stufe 3 brauchen unterschiedlich starke Mechanismen, wie im Handbook
eigentlich schon vorgesehen (Kap. 10), aber im Code nicht 1:1
umgesetzt war.

**Falsifizierbarkeit:** Gilt als behoben, wenn "Ende" (und Stop,
Tschüss etc.) Jarvis zuverlässig beendet, ohne die KI überhaupt zu
erreichen, UND ein einfaches "ja" bei shutdown_pc nachweislich NICHT
mehr ausreicht (siehe tests/test_executor.py,
test_executor_stufe3_requires_exact_phrase_not_just_ja).

**Nächste Schritte:** Bei künftigen kritischen Commands (Kap. 17:
Dateien löschen, Programme deinstallieren) von Anfang an
`confirmation_phrase` setzen, nicht nachträglich nachrüsten.

## 2026-07-01 - Review-Prozess: Code-Review von GPT eingearbeitet

**Kontext:** GPT (Kap. 2: Mentor-Rolle im Zusammenspiel mit Claude als
Reviewer) hat den v0.3-Code reviewt, Bewertung 8.5-9/10, mit vier
konkreten Kritikpunkten.

**Bewertung der vier Punkte (Review-Prozess: Claude prüft, Diskussion,
gemeinsame Entscheidung):**

1. **Planner ist ein naiver String-Splitter, keine echte
   Intent-Zerlegung:** Zutreffend, aber bewusst so gebaut (Kap. 27:
   v0.3-Scope war "einfache Mehrschritt-Erkennung über Konnektoren",
   keine KI-basierte Zerlegung). Kein Fix jetzt - keine echte
   Lücke gegenüber dem, was für v0.3 vereinbart war.
2. **SYSTEM_PROMPT hart codiert:** Zutreffend und umgesetzt - siehe
   ADR-007. War der wichtigste Punkt, da er einen echten Widerspruch
   zur README-Zusage aufdeckte (neue Commands ohne ai.py-Änderung).
3. **Bekannte Intents nannten Phantom-Commands (search_google,
   weather):** Zutreffend, direkt mit Punkt 2 zusammen behoben (siehe
   ADR-007) - beides derselbe Root Cause (statische statt
   Registry-basierte Liste).
4. **Planner sollte nicht direkt an AIEngine gekoppelt sein, sondern
   über ein Interface:** Nachvollziehbarer Punkt, aber bewusst
   ZURÜCKGESTELLT - aktuell genau ein Consumer der AIEngine, eine
   Abstraktionsschicht dafür jetzt wäre Overengineering ohne
   konkreten zweiten Anwendungsfall (Regel 6, YAGNI). Wird in ADR-007
   als "erwogene Alternative, verworfen" dokumentiert; erneut prüfen,
   sobald ein zweiter Aufrufer oder Austausch der KI-Implementierung
   ansteht.

**Umsetzung:** `core/ai.py` baut den SYSTEM_PROMPT jetzt zur Laufzeit
aus `commands.REGISTRY` (`build_system_prompt()`,
`_known_intents_text()`). `OpenProgramCommand` und `ShutdownPcCommand`
haben jetzt ein `description`-Attribut. Zwei neue Tests in
tests/test_ai.py. Volle Suite (48 Tests) läuft grün, sowohl im
Scratch-Build als auch nach dem Kopieren nach Downloads/jarvis.

**Lesson Learned:** Ein zweiter Blick von außen (hier: GPT) auf
denselben Code deckt Lücken auf, die man selbst nicht mehr sieht,
weil man die Historie kennt ("das war schon immer so"). Der im
Handbook vorgesehene Review-Prozess (Entwicklung -> Review -> Diskussion
-> gemeinsame Entscheidung -> Logbook) hat hier genau das geleistet,
wofür er gedacht ist.

**Falsifizierbarkeit:** Gilt als korrekt umgesetzt, wenn ein neuer
Command mit `description` automatisch im Prompt auftaucht, ohne
`ai.py` anzufassen (siehe ADR-007 für den konkreten Test-Ansatz).

**Siehe auch:** ADR-007 (docs/adr/ADR-007.md), CHANGELOG v0.3.5.

## 2026-07-01 - Wolfgang-Wunsch: Jarvis-Persönlichkeit + Stimme näher am Film

**Anfrage:** Wolfgang möchte Jarvis perspektivisch näher an den
Film-Jarvis heranbringen - Stimme und Persönlichkeit.

**Persönlichkeit (entschieden: "dezent trocken"):** `CHAT_SYSTEM_PROMPT`
in core/ai.py erweitert um eine Persönlichkeitsbeschreibung (höflich,
loyal, kompetent, gelegentlicher trockener Kommentar/feine Ironie),
mit expliziter Guardrail gegen Dauerwitzeln und Häme bei Fehlern -
Wolfgang wollte ausdrücklich die dezente statt die deutlich
sarkastische Variante. Neuer Test:
`test_chat_prompt_has_dezente_persoenlichkeit` in tests/test_ai.py.
49 Tests grün (Scratch-Build + Downloads/jarvis).

**Stimme (noch offen, bewusst nicht sofort umgesetzt):** Piper TTS ist
komplett offline - ein 1:1 Film-Jarvis-Klang (britisch, Butler-artig)
ist damit nur begrenzt erreichbar. Wolfgang wollte dazu erst
Optionen sehen statt sofort eine Cloud-TTS-Entscheidung zu treffen.
Recherchierte deutsche Piper-Stimmen (huggingface.co/rhasspy/piper-voices,
Stand 01.07.2026): `thorsten` (aktuell genutzt, medium; auch high
verfügbar), `karlsson` (männlich, nur low-Qualität), `pavoque`
(männlich, ernster/tiefer, nur low-Qualität), daneben `eva_k`,
`kerstin`, `ramona` (weiblich), `mls`, `thorsten_emotional`.
Cloud-TTS (z. B. OpenAI/ElevenLabs) würde klanglich näher an den Film
kommen, widerspricht aber dem bisherigen Offline-Prinzip (Internet,
laufende Kosten, Audio geht an Dritte).

**Nächste Schritte (Next, nicht Now):** Wolfgang probiert 2-3
Piper-Stimmen selbst an, danach gemeinsame Entscheidung Offline vs.
Cloud-TTS - siehe Antwort an Nutzer für die konkreten Download-Links.

## 2026-07-01 - TTS-Backend-Abstraktion vorbereitet (ADR-008)

**Anfrage:** Wolfgang wollte die Stimmentscheidung erstmal offen
lassen, aber schon "vorsorgen", falls er später OpenAI, ElevenLabs
oder Kokoro statt Piper nutzen möchte.

**Umsetzung:** Neues Package `core/tts/` mit `TTSBackend`-Protokoll
und vier Implementierungen (Piper, OpenAI, ElevenLabs, Kokoro).
`core/tts/factory.py::create_backend()` wählt anhand von
`Config.tts_backend` (Standard weiterhin `"piper"` - für Wolfgang
ändert sich nichts, solange nicht aktiv umgestellt wird). Jeder
Fehler beim Laden eines Backends (Paket/Modell/Key fehlt) führt zu
`None` statt Crash - Jarvis bleibt bei Konsolenausgabe nutzbar.
`core/speech.py` kennt jetzt nur noch das Protokoll, keine
Piper-Spezifika mehr. `SpeechEngine.__init__` nimmt neu die komplette
`Config` entgegen (`main.py` entsprechend angepasst).

**Wichtiger Fund bei der Recherche:** Kokoro v1.0 unterstützt aktuell
KEIN Deutsch (nur Englisch, Spanisch, Französisch, Hindi, Italienisch,
brasilianisches Portugiesisch, Japanisch, Chinesisch). Das
Kokoro-Backend existiert trotzdem (Wolfgang hatte es explizit
genannt), ist aber im Code UND in README.md klar als "für deutsche
Gespräche aktuell nicht geeignet" markiert - lieber ehrlich
dokumentieren als eine falsche Erwartung wecken.

**Tests:** 18 neue Tests (core/tts/factory.py, core/tts/*_backend.py,
core/speech.py neu geschrieben), 67 Tests gesamt, alle grün -
Scratch-Build und Downloads/jarvis geprüft.

**Lesson Learned:** "Vorsorgen" heißt hier bewusst NICHT "alle vier
Anbieter production-ready mit echten Keys testen", sondern die
Architektur so bauen, dass ein späterer Wechsel eine
Konfigurationsänderung ist statt einer Code-Änderung - das ist der
eigentliche Wert der Abstraktion, nicht die Cloud-Anbindung an sich.

**Siehe auch:** ADR-008 (docs/adr/ADR-008.md), README.md Abschnitt
"TTS-Backend wechseln", CHANGELOG v0.3.7.

## 2026-07-01 - v0.4 gestartet: Langzeitgedächtnis

**Kontext:** v0.3 ist laut Handbook Kap. 28 (Definition of Done)
vollständig abgeschlossen. Kap. 27 (Now/Next/Later) erlaubt jetzt den
Beginn von "Next (v0.4-v0.6)" - fünf mögliche Bausteine
(Kurzzeit-/Langzeitgedächtnis, PC-Grundsteuerung, Post-Arbeitsmodule,
Telegram-Anbindung, Excel/Outlook-Integration). Wolfgang hat
Langzeitgedächtnis als ersten priorisiert und sich zusätzlich
ausdrücklich für "nur auf Zuruf" statt automatischer Erkennung
entschieden (Details/Abwägung siehe ADR-009).

**Umsetzung:** Neues `memory/long_term.py::LongTermMemory`
(kategorisierte Fakten: projekt/gewohnheit/praeferenz/allgemein,
persistiert in `long_term.json`, getrennt vom Gesprächsverlauf).
Neue Commands `remember_fact`/`forget_fact` (commands/memory.py,
Sicherheitsstufe 1, keine Bestätigung nötig). `core/ai.py` erklärt
der KI, wie sie target/category für diese Commands befüllt, und
hängt bei Chat-Antworten optional eine Zusammenfassung aller
gemerkten Fakten an den System-Prompt an. `Executor.run()` und
`main.py` reichen diese Zusammenfassung durch dieselbe Kette wie
schon den Gesprächsverlauf.

**Architektur-Besonderheit:** Die Command-Registry instanziiert alle
Commands beim Modul-Import, bevor `Config.load()` läuft - deshalb
gibt es `commands.memory.configure(memory_dir)` als Einmal-Aufruf
beim Start (main.py), statt LongTermMemory klassisch per Konstruktor
zu injizieren. Dokumentiert in ADR-009, damit das bei zukünftigen
Memory-artigen Commands nicht neu erfunden werden muss.

**Tests:** 23 neue/geänderte Tests (memory/long_term.py,
commands/memory.py, core/ai.py, executor.py, End-to-End-Test in
test_integration.py: merken -> in Chat-Antwort wiederfinden) - 90
Tests gesamt, alle grün (Scratch-Build und Downloads/jarvis geprüft).

**Bewusst nicht gemacht:** Automatische Fakten-Extraktion aus
Gesprächen (Wolfgangs Entscheidung), `knowledge.py`/RAG (steht unter
"Later", wäre ein verfrühtes Vorziehen), eine eigene
Memory-Manager-Koordinationsschicht (nur zwei Speicherarten aktuell,
noch kein Bedarf - Regel 6).

**Siehe auch:** ADR-009 (docs/adr/ADR-009.md), README.md Abschnitt
"Langzeitgedächtnis", CHANGELOG v0.4.0.
