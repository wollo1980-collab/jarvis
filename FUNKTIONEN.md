# Funktionen — was Jarvis kann (Stand 14.07.2026)

Jede Fähigkeit hier ist gebaut, getestet und in Nutzung — nichts ist Kulisse.
Einrichtungsschritte stehen beim jeweiligen Feature; Grund-Setup in
[INSTALLATION.md](INSTALLATION.md), Sicherheitsmodell in
[SICHERHEIT.md](SICHERHEIT.md).

## Der denkende Kern & das lernende Gedächtnis (ADR-060/061/064/073)

**Verständnis über ein LLM, nicht über Stichwörter.** Der alte
Klassifikator-Planner wird schrittweise durch einen LLM-getriebenen Kern
ersetzt (Strangler-Muster): das Modell hält das Gespräch, überlegt und ruft
die vorhandenen Befehle als *Werkzeuge* auf (Function-Calling, typisierte
Argumente). Der Kern **führt heute den Großteil der Alltags-Intents** (~41
von 66, Whitelist als Sicherheitsgrenze) — auch **mehrschrittig** („mach
Musik an und lauter" = zwei Werkzeuge in einem Zug); der deterministische
Router läuft parallel und trägt den Rest, insbesondere die gefährlichen
Pfade hinter dem Bestätigungs-Gate. Welcher Intent umgehängt wird,
entscheiden Messdaten (`scripts/reasoning_eval.py`), nicht Bauchgefühl —
und die Modell-Sicht bleibt gemessen der **flache Werkzeugkatalog**
(ADR-073). Sicherheits-Invarianten gegen Prompt-Injection: siehe
[SICHERHEIT.md](SICHERHEIT.md).

**Antworten aus einem Guss (ADR-065):** Bei erfolgreichen Schritten
formuliert ein Antwort-Composer die Antwort aus dem vollen Kontext
(Gesprächsfaden + Werkzeug-Ergebnisse) — er versteht „eher etwas anderes"
und „und kürzer", handelt aber nie selbst. Bei Fehlern/Rückfragen bleibt die
klare Befehls-Schablone.

**Gedächtnis, das lernt (opt-in, drei Stufen):** ein einsehbares
Ereignis-Tagebuch (`memory_data/episodes/`), nachts eine kurze Reflexion
daraus (`memory_data/reflections/`, „dreaming"), und erhärtete Gewohnheiten
werden **einmal** als Merk-Angebot vorgeschlagen (ja/nein) — nie heimlich
gespeichert, nie eigenmächtig gehandelt. Alles lokal, Secrets redigiert,
abschaltbar (`episodic_memory_enabled`, `reflection_enabled`,
`reflection_offers_enabled`).

## Einträge: Erinnerungen, Aufgaben & wichtige Merkposten

```text
Du:     erinnere mich morgen um 9 an den Zahnarzt
Jarvis: Notiert, Sir: «Zahnarzt» — morgen um 09:00
Du:     was steht an?
Jarvis: Deine Einträge, Sir: … (+ 🗓 Heute noch im Kalender: …)
Du:     lösch die Zahnarzt-Erinnerung
Jarvis: 🗑 Gestrichen, Sir — «Zahnarzt» ist gestrichen.
        (Falls das ein Versehen war: «stell den Eintrag wieder her».)
```

- Relative Zeiten („morgen", „nächsten Montag") rechnet der Kern um — das
  **Echo nennt die verstandene Zeit**, damit Verhörer sofort auffallen.
- **Papierkorb statt Risiko:** Gelöschtes wandert in den Papierkorb; „stell
  den Eintrag wieder her" holt es unverändert zurück (ohne Suchtext: den
  zuletzt gelöschten).
- Standard-Liste: offene/zukünftige Einträge **plus alle wichtigen**; „was
  steht an?" zeigt zusätzlich die heute noch kommenden Kalender-Termine.
- **Wiederkehrend (ADR-052):** „erinnere mich **täglich** um 19:54 an …" —
  feuert und rückt selbst aufs nächste Vorkommen vor (↻-Marker); nach
  längerem Ausfall genau **eine** Nachholung, keine Flut.
- **Jarvis meldet sich von selbst (ADR-039):** Fällige Einträge pusht die
  Runtime an den autorisierten Telegram-Chat; war Jarvis zur Fälligkeit aus,
  kommt die Nachholung ehrlich als „verspätet" markiert. Jeder Eintrag feuert
  genau einmal. Daten: `memory_data/entries.json`.

## Listen: „Setz das auf die Einkaufsliste"

```text
Du:     Einkaufsliste: Milch, Butter und drei Zwiebeln
Jarvis: Notiert, Sir: Milch, Butter, drei Zwiebeln — steht auf der Einkaufsliste.
Du:     streich Nummer 2
Jarvis: 🗑 Gestrichen, Sir: «Butter» (Einkaufsliste).
Du:     leere die Einkaufsliste
Jarvis: ✓ Geleert, Sir — 2 Posten. Falls das ein Versehen war: «stell die Liste wieder her».
```

Beliebige Listen-Namen; **Undo statt Rückfrage** — „leere die Liste" wirkt
sofort, der Papierkorb fängt Versehen. Löschen per Nummer funktioniert auch
bei Einträgen. Daten: `memory_data/lists.json`.

## Langzeitgedächtnis: „Merk dir, dass …" (ADR-009)

Dauerhafte Fakten über dich — nur auf ausdrückliches „merk dir" (bzw. als
beantwortetes Merk-Angebot), nie automatisch:

```text
Du: Merk dir, dass ich montags immer Reports mache
Du: Vergiss das wieder   →  landet im Papierkorb («stell den Fakt wieder her»)
Du: Was weißt du über mich?
```

Fakten fließen automatisch in Chat-Antworten ein (mit Herkunfts-Halbsatz
„aus unserem Gedächtnis weiß ich …"). Sinngleiche Neuzugänge werden erkannt
und nicht doppelt angelegt; ein Aufräum-Lauf je Start verschiebt Duplikate
in den Papierkorb (nichts geht verloren). Daten: `memory_data/long_term.json`.

## Merk-Angebot: Jarvis fragt, ob er sich etwas merken soll (ADR-051)

Erwähnst du **nebenbei** einen dauerhaften Fakt („ich trinke meinen Kaffee
übrigens immer schwarz"), fragt Jarvis: „Soll ich mir dauerhaft merken: ‚…'?
(ja/nein)". „Nein" landet auf der Nein-Liste und wird nie wieder angeboten;
gespeichert wird **niemals** automatisch. Schalter: `memory_offers_enabled`.

## Kalender: lesen, eintragen, verschieben, absagen (Outlook/M365, ADR-062/063)

- **Lesen:** „Was habe ich morgen?", „Zeig meine Termine am Freitag" — der
  Kalender fließt auch in Briefing und Tages-Blick ein.
- **Eintragen:** „Trag mir morgen 14 Uhr Zahnarzt ein" (ohne Uhrzeit →
  ganztägig). **Verschieben:** „Verschieb den Zahnarzt auf 15 Uhr".
  **Absagen:** „Sag das Meeting morgen ab".
- **Bestätigungs-Diät (ADR-068):** Eintragen und Verschieben passieren
  **sofort** — die Antwort nennt den Rückweg gleich mit („vorher Donnerstag
  09:00 — sag es, falls ich zurückschieben soll"). Nur das **Absagen** fragt
  nach, weil es nach außen sichtbar ist.
- **Proaktiv (ADR-063, opt-in `proactive_prep_enabled`):** Jarvis schaut
  abends voraus und *bietet einmal an*, dich an den Termin von morgen zu
  erinnern.
- Termine erzählt Jarvis auch **beiläufig richtig zu**: „Ich habe um 16 Uhr
  einen Termin beim Rewe" landet im Kalender, „erinnere mich an …" bleibt
  eine Jarvis-Erinnerung.

**Zwei Wege — Lesen und Schreiben getrennt:**

*Lesen (ohne OAuth, empfohlen für private Outlook.com-Konten):* Kalender in
Outlook.com **veröffentlichen**, den ICS-Link als `ms_calendar_ics_url` in
`config.json` (der Link ist ein Geheimnis; der Feed aktualisiert verzögert).

*Schreiben (Microsoft Graph):* einmalige App-Registrierung —
1. Azure-Portal → *App registrations* → *New registration* (Kontotyp „… und
   persönliche Microsoft-Konten"), Plattform **Mobile/Desktop** mit
   Redirect-URI `http://localhost:8400`, „Allow public client flows" = Ja,
   API-Permission Microsoft Graph → Delegated → **Calendars.ReadWrite**.
2. `python scripts/ms_calendar_auth_localhost.py <CLIENT_ID>` (der
   localhost-Weg funktioniert auch mit privaten Konten, wo der Geräte-Code
   scheitert) → Browser-Login → das Skript druckt den `refresh_token`.
3. `ms_calendar_client_id`, `ms_calendar_tenant`, `ms_calendar_refresh_token`
   in `config.json` (Secrets — nie ins Repo), Jarvis neu starten.

## Briefings & Welt

- **Tages-Briefing** — „Briefing" / „wie sieht mein Tag aus?": EIN Überblick
  aus Terminen (Kalender + Einträge), Wetter, Listen-Stand und Nachrichtenlage.
  Jede Quelle fail-safe. Bewusst nur auf Zuruf.
- **News (ADR-042):** „Was gibt's Neues?" — Top-Schlagzeilen aus RSS (Standard
  tagesschau, erweiterbar via `news_feeds`); mit Orts-/Themenangabe über die
  Google-News-RSS-Suche. „Wie ist die Lage?" heißt **immer** Nachrichtenlage.
- **Wetter (ADR-043):** Open-Meteo (kostenlos, kein Key), versteht
  heute/morgen/übermorgen/Datum und jeden Ort; ohne Ort gilt
  `weather_default_location`.
- **Websuche (ADR-032):** auf ausdrückliche Recherche-Anfragen ein knapper
  Überblick mit **sichtbaren Quellen** (DuckDuckGo-Lite, nur Titel/Snippet/
  URL). Bewusst kein Browser, kein Öffnen von Treffern, keine Aktionen.

## Mail-Briefing „Was liegt an?" (ADR-031)

Knapper Überblick über neue/ungelesene private Mails — Werbung/Newsletter
ausgeblendet (aber gezählt, nie stumm verworfen). **Rein lesend, rein lokal:**
nur Kopfzeilen, **kein Mailinhalt geht an eine KI**.

Einrichtung (Beispiel Gmail): Postfach in `config.json` unter `mail_accounts`
(nur nicht-geheime Felder), App-Passwort **als Umgebungsvariable**
(`setx JARVIS_GMAIL_APP_PASSWORD "…"`). Nicht gesetztes Passwort = Konto wird
übersprungen. Hotmail/Outlook.com: IMAP-Host `outlook.office365.com` —
Microsoft baut Basis-Auth ab, zuerst Gmail nutzen.

**Lernen (korrigierbare Regeln):** „von Amazon will ich nichts mehr" /
„von X will ich immer hören" — Regeln liegen menschenlesbar in
`memory_data/mail_rules.json` und schlagen die Automatik. „zeig mir die
Werbung" blendet Ausgeblendetes einmalig ein.

## Musik: Spotify steuern (ADR-058)

„spiel Musik", „pause", „nächster Song", „lauter"/„Lautstärke auf 50", „spiel
die Playlist Fokus", „was läuft gerade?" — reversibel, Stufe 0.
Voraussetzungen: Spotify **Premium** + ein aktives Gerät (Jarvis dirigiert,
er spielt nicht selbst ab). Einrichtung: App auf developer.spotify.com,
`spotify_client_id`/`spotify_client_secret` in `config.json`,
`python scripts/spotify_auth.py` → `spotify_refresh_token` eintragen.

## Der Agenten-Arm: analysieren, bauen, weiterarbeiten

Jarvis delegiert echte Arbeit an einen Coding-Agenten (erstes Backend:
Claude Code CLI als Subprozess) — **asynchron** über Runtime-Telegram und
Browser-Kanal (Quittung sofort → Hintergrundlauf → Ergebnis-Push), synchron
an der Konsole. Genau eine Delegation gleichzeitig; „**stopp den Agenten**"
bricht jederzeit hart ab. Käfig-Details: [SICHERHEIT.md](SICHERHEIT.md).

**Repo-Analyse (ADR-033/034/035):** „analysiere jarvis: wie funktioniert der
Executor?" — strikt read-only, Repo-Allowlist (`agent_repos`) fail-closed,
Ergebnis als Markdown-Artefakt unter `memory_data/delegations/`.

**Schreibende Delegation im Käfig (ADR-050):** „erledige in jkc: …" —
Umsetzungsarbeit in einem **eigens schreib-freigegebenen** Projekt-Repo
(`agent_write_repos`; lesen heißt nie schreiben). Nach dem Bau prüft Jarvis
**selbst** (Gate + Tests, ADR-055) und legt ein Diff-Artefakt ab.
Bestätigung vor dem Lauf; nicht-kuratierte Befehle fragen live per
🔐-Erlaubnis-Haken (ADR-071) — auch aufs Handy.

**Ampel-Gating + Auto-Commit (ADR-056, Opt-in `agent_auto_commit`):** grün
geprüfte, grün klassifizierte Ergebnisse committet Jarvis selbst (lokal, kein
Push); Löschungen/folgenreiche Flächen gehen immer auf Vorlage. Default aus.

**„Mach weiter an <projekt>" (project_continue):** Jarvis liest den
Projektstand des Ziels (read-only), formuliert **selbst** den nächsten
Arbeitsauftrag und zeigt ihn in der Vorschau. Findet sich kein dokumentiertes
nächstes Arbeitspaket, wird keins erfunden. In eigenen, von Jarvis angelegten
Projekten läuft die Weiterarbeit ohne erneute Ja/Nein-Frage — dort tragen
Käfig, 🔐-Haken, Not-Stopp und Prüf-Ampel die Verantwortung.

**„Bau mir X" (ADR-059/069):** „bau mir einen Pomodoro-Timer" legt ein neues
Projekt unter `projects_root` an (Framework-Gerüst), gibt **genau dieses**
Projekt dem Bau-Agenten frei und baut die erste Fassung — mit Vorschau in der
Bestätigung, Selbstprüfung und Bau-Bullauge (deutsche Live-Erzählung, was der
Agent gerade tut). Die Schreib-Freigabe ist sitzungs-lokal, nur unterhalb von
`projects_root`, **nie** Jarvis' eigenes Repo. Auch mobil per Telegram.

**„Plane den nächsten Schritt" (ADR-036):** liest read-only den eigenen
Projektstand und legt EINEN klein geschnittenen Vorschlag als Entwurf unter
`memory_data/proposals/` ab — Vorschlag statt Umsetzung; findet sich kein
begründbarer Schritt, sagt Jarvis das ehrlich.

**Gebaute Skills** werden katalogisiert („was hast du schon gebaut?");
Ausführen ist bewusst noch nicht freigeschaltet.

## Die Zugänge: vier Wege, eine Pipeline

Alle Zugänge laufen durch denselben Kern, dieselben Befehle, dieselben
Sicherheitsstufen.

**Jarvis-UI / Command Center (ADR-046/047):** `pythonw jarvis_ui.pyw` startet
Jarvis' Gesicht als eigenes Fenster — Tages-Karten aus **echten Quellen**
(nächste Erinnerung, Wetter, Merkposten), der **Orb** atmet den Live-Zustand
(bereit/arbeitet/wartet/außer Dienst), die Chat-Leiste spricht mit der
normalen Pipeline inkl. Stufe-2/3-Bestätigungsdialog. GEDÄCHTNIS-Ansicht zum
Blättern durch Fakten/Einträge/Listen/Verlauf (✕ räumt auf — alles landet im
Papierkorb), Live-Zeile („Ich arbeite gerade: …"), AGENT-Kachel, Equalizer
nur bei echtem Hören/Sprechen. Läuft die Runtime nicht, degradiert die Seite
würdevoll zur read-only-Anzeige. Self-contained (kein CDN), nur localhost.

**Browser-Kanal/Runtime-API (ADR-047):** `"ui_enabled": true` startet die
lokale API (`POST /message`, `GET /events` als SSE) — nur `127.0.0.1` +
Origin-Prüfung. Delegationen laufen hier asynchron.

**„Hey Jarvis" — Wake-Word (ADR-044):** `"wake_word_enabled": true` — Zuruf
quer durchs Zimmer, Antwort „Ja, Sir?", dann sprechen. Erkennung **100 %
lokal** (openwakeword); kein Audio verlässt den Rechner, bis das Wake-Word
erkannt ist. Kurzes Anschluss-Fenster für Folgefragen ohne erneutes
„Hey Jarvis". Standard aus (bewusste Entscheidung fürs Dauer-Mikrofon).

**Push-to-talk (ADR-041):** `Strg+Alt+J` → sprechen → gesprochene Antwort
(erster Ton nach ~1 s dank Streaming-TTS). Aufnahme nur im Speicher,
Transkript-Inhalte werden nicht geloggt. Stufe-2/3 bleibt hier fail-closed.

**Telegram (ADR-018/027/038/045):** Text und **Sprachnachrichten** von
unterwegs — Jarvis echoot das Verstandene (🎤 „Verstanden: …"). Über den
Runtime-Kanal inklusive Bestätigungen, Erinnerungs-Pushs, Bau-Arm und
Ergebnis-Meldungen. Audio wird nur nach Autorisierung verarbeitet und nie
gespeichert.

## PC-Admin (Windows)

- **Systemüberwachung (ADR-011):** „Wie ist die Auslastung?" — CPU/RAM via
  psutil, Stufe 0. (Temperatur: von psutil unter Windows nicht unterstützt.)
- **PC-Analyse (ADR-020):** Gesundheitsbericht — Festplatten, Top-Prozesse,
  Doppel-Läufer, Autostarts. Python sammelt deterministisch, die KI
  formuliert nur.
- **Ereignisprotokoll (ADR-021):** jüngste Fehler/Warnungen aus System- und
  Application-Log (`wevtutil`, sprachversions-unabhängig geparst).
- **Programme öffnen/installieren (ADR-012):** Installieren über `winget`,
  Stufe 2 mit Ja/Nein-Bestätigung; bekannte Namen sind auf exakte Package-IDs
  gemappt.
- **Autostart verwalten (ADR-022):** fremde Autostart-Einträge deaktivieren/
  reaktivieren — nur HKCU/Benutzer-Startup, deaktivieren statt löschen
  (vollständig umkehrbar), Stufe 2.
- **Temp-Bereinigung (ADR-023):** `analyze_temp_files` zeigt (Stufe 0),
  `clean_temp_files` löscht unwiderruflich — Stufe 3 mit exakter Phrase
  `BEREINIGEN` und Vorschau (Anzahl/GB) vor der Frage. Nur `%TEMP%`, nur
  Dateien älter 24 h.
- **Excel lesen (ADR-014):** `.xlsx`/`.xlsm` über openpyxl — Blätter,
  Dimensionen, Werte (500 Zeilen/Blatt), Stufe 0.

## Jarvis steuern

- **Neustart:** „starte dich neu" — Staffelstab-Neustart (Nachfolger wartet
  auf den Single-Instance-Lock). Liegt eine neue Version auf der Platte,
  übernimmt der **Voll-Automat** sie selbst — aber nur im Leerlauf
  (`auto_restart_enabled`); ein ✨-Hinweis kündigt Neues an.
- **Beenden:** „beende dich" / „fahr dich runter" fährt die **Runtime** sauber
  herunter (gemeint ist Jarvis, nicht der Rechner — das wäre `shutdown_pc`
  mit Stufe-3-Phrase).
- **Selbstauskunft:** „was ist neu?" (echte Changelog-Einträge), „was kannst
  du?" (Fähigkeiten), Wochen-Rückblick, Selbstbewertung.

## Pipeline (technisch)

Eingabe (beliebiger Kanal) → **LLM-Kern und Router parallel**: der Kern
führt freigegebene Intents (auch mehrschrittig), der Router den Rest →
pro Schritt: Tool-Manager löst Intent → Command auf → Executor führt aus
(mit Bestätigung bei kritischen Aktionen) → Antwort-Composer formuliert bei
Erfolg aus dem vollen Kontext (sonst Schablone) → Memory speichert
(Auto-Redaction, History-Limit).

## Neuen Command hinzufügen

1. Klasse mit `name`, `description`, `requires_confirmation` und
   `execute(plan) -> Result` in einem Modul unter `commands/`.
2. Instanz in die `COMMANDS`-Liste des Moduls, Modul in
   `commands/__init__.py::_register_all()`.
3. Die **Drift-Wächter** verlangen (Suite fällt sonst): deutsches Label in
   `core/intent_labels.py` **und** wortgleich in der Dashboard-JS-Tabelle,
   plus Zuordnung zu genau EINEM Bereich in `core/capability_tools.py`
   (`TOOL_DOMAINS`).

Kein Anfassen von `main.py`, `planner.py`, `tool_manager.py` oder `executor.py`
nötig.
