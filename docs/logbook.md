# Logbook

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
