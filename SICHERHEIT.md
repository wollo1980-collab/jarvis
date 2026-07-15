# Sicherheit — das Modell hinter Jarvis

Sicherheit ist bei Jarvis Architektur, nicht Beteuerung: fail-closed als
Grundhaltung, Bestätigung vor Folgenreichem, Undo statt Rückfrage bei
Umkehrbarem, und Käfige, die technisch erzwingen, was der Prompt nur erklärt.

## Sicherheitsstufen & Bestätigung

Jeder Befehl trägt eine Sicherheitsstufe:

- **Stufe 0/1** (lesen, eigener Datenlayer): läuft sofort.
- **Stufe 2** (Systemänderung, z. B. Programm installieren): Ja/Nein-Frage in
  Kundendeutsch — die Frage sagt, was ein „ja" bewirkt und dass alles andere
  folgenlos abbricht.
- **Stufe 3** (kritisch, z. B. PC herunterfahren, Temp-Dateien löschen):
  verlangt eine **exakte Bestätigungsphrase** (`HERUNTERFAHREN`, `BEREINIGEN`).

**Undo statt Rückfrage (ADR-068):** Umkehrbares fragt nicht, sondern wirkt
sofort und nennt den Rückweg — gelöschte Fakten, Einträge und geleerte Listen
landen im **Papierkorb** („stell den Fakt/Eintrag/die Liste wieder her");
Kalender-Eintragen/-Verschieben antwortet mit dem Rückweg, nur das Absagen
fragt (nach außen sichtbar).

**Bestätigung remote (ADR-045):** Stufe-2/3-Rückfragen funktionieren auch über
den Runtime-Telegram-Kanal — die nächste **Textnachricht** ist die Antwort und
geht nie durch den Planner. Keine Antwort in 120 s, „nein" oder eine falsche
Phrase ⇒ Abbruch (fail-closed). Sprachnachrichten zählen nie als Bestätigung;
Push-to-talk/Wake-Word bleiben ohne Bestätigungsweg (dort kein Stufe 2/3).

## LLM-Kern: Invarianten gegen Prompt-Injection (ADR-061)

- **(I1)** Kein Secret gelangt je in den an das LLM gesendeten Kontext — die
  Befehls-Schicht nutzt die Keys, der Kern wählt nur Intent + Argumente.
- **(I2)** Werkzeug-Ausgaben (Web-/Mail-Inhalt) sind **Daten, nie Befehle** —
  die Werkzeug-Wahl entscheidet ausschließlich auf Nutzereingabe +
  Gesprächsverlauf. Der häufigste Agenten-Angriff (Prompt-Injection → Aktion)
  ist damit strukturell blockiert.
- Der Kern führt nur **explizit freigegebene** Intents (Whitelist als
  Sicherheitsgrenze); ein einziger nicht freigegebener Schritt in einem
  Mehrschritt-Bündel lässt die ganze Eingabe beim deterministischen Router.
- Fail-safe überall: jede kaputte/unbekannte Werkzeug-Wahl fällt auf ein
  Gespräch zurück — nie auf eine geratene Aktion.

## Agenten-Arm: Käfig statt Vertrauen

Delegiert Jarvis Arbeit an einen Coding-Agenten, erzwingt die Technik den
Rahmen (`--allowedTools` — der Prompt erklärt, der Käfig setzt durch):

- **Analyse:** nur `Read`/`Grep`/`Glob` — read-only garantiert, keine
  git-Operation möglich. Repo-Allowlist fail-closed (nur explizit gelistete
  Pfade).
- **Schreibende Läufe (ADR-050):** `Edit`/`Write` **pfadgebunden** auf das
  freigegebene Ziel-Repo — nie Jarvis' eigenes Repo (Jarvis kann sich per
  Konstruktion nicht selbst umbauen, ADR-056/059). Lesen heißt nie schreiben
  (`agent_repos` ≠ `agent_write_repos`).
- **🔐-Live-Erlaubnis (ADR-071):** erlaubt ist nur ein kuratierter
  Dev-Befehlssatz; alles andere löst eine Echtzeit-Rückfrage aus („🔐
  Erlauben?" — auch aufs Handy), fail-closed bei Nicht-Antwort.
- **Kill-Switch:** „stopp den Agenten" bricht jederzeit hart ab; zusätzlich
  harter Wall-Clock-Timeout. Kosten/Turns werden protokolliert.
- **Ampel-Commit-Gate (ADR-056):** Auto-Commit nur als Opt-in und nur für
  grün geprüfte, grün klassifizierte Ergebnisse; Löschungen/Umbenennungen und
  folgenreiche Flächen (Verfassung, Charter, ADRs, Kern) gehen immer auf
  Vorlage.
- **Genau eine Delegation gleichzeitig** (Single-Flight) — bewusstes Gate.

## Fernzugriff: zwei Telegram-Wege, zwei Vertrauensstufen

- **Runtime-Kanal** (empfohlen): breite kuratierte Whitelist inkl.
  bestätigungspflichtiger Aktionen — möglich, weil der Kanal seit ADR-045
  einen echten Bestätigungsweg hat. Der Bau-Arm ist mobil nutzbar
  (Bestätigung vor dem Lauf, Not-Stopp, Ergebnis-Push, 🔐-Fragen aufs Handy).
- **Standalone-Bot** (`telegram_main.py`, älter): bewusst eng — nur rein
  lesende/bestätigungsfreie Intents (aktuell 10, `ALLOWED_INTENTS`); kein
  Hintergrund-Worker, keine Delegation. Enthält eine Mehrschritt-Anfrage
  auch nur einen nicht erlaubten Befehl, wird die **gesamte** Anfrage
  abgelehnt.
- Beide: genau **ein** autorisierter Chat; fremde Chat-IDs werden ignoriert.

## Secrets & Daten

- **Keys nur als Umgebungsvariablen** (bzw. in der gitignorierten
  `config.json`) — nie im Repo. Auto-Schwärzung (ADR-040): Secrets werden vor
  jeder Persistenz redigiert (Gedächtnis, Einträge, Episoden-Tagebuch, Logs).
- **Alles lokal:** Gedächtnis, Regeln, Artefakte liegen als einsehbare Dateien
  unter `memory_data/`. Mail wird nur als Kopfzeilen gelesen — kein Mailinhalt
  geht an eine KI.
- **Release-Hygiene-Scanner:** `python scripts/release_scan.py` prüft die
  git-getrackten Dateien vor jeder Veröffentlichung auf Secret-Muster,
  verbotene Pfade (config.json, memory_data/, logs/, voices/), E-Mail-Adressen
  und persönliche Begriffe aus einer lokalen, selbst gitignorierten Liste.
  Funde werden maskiert ausgegeben; Exit 1 = nicht veröffentlichen.

## Lokale APIs & Prozess-Schutz

- **Browser-Kanal/Runtime-API (ADR-047):** nur `127.0.0.1` (Port `ui_port`)
  plus Origin-Prüfung — fremde Webseiten im selben Browser werden abgewiesen.
  Standard: aus. Die stillen Lösch-Endpunkte des UIs sind hart auf zwei
  Aktionen begrenzt und treffen nur exakte Texte.
- **Single-Instance-Schutz (ADR-026):** jeder Einstiegspunkt erwirbt als
  allererste Aktion einen Lock (`jarvis.lock` im `memory_dir`, atomare
  Dateierzeugung + `msvcrt.locking`); ein zweiter Prozess bricht sofort mit
  klarer Meldung ab. Verwaiste Locks (Absturz) werden beim nächsten Start
  erkannt und entfernt.
- **Governance als Sicherung:** Konsistenz-Gate + komplette Testsuite laufen
  vor jedem Commit (Pre-Commit-Hook); Drift-Wächter-Tests koppeln
  Sicherheits-Tabellen an die Realität (jeder Befehl braucht Bereich +
  deutsches Label, sonst fällt die Suite).
