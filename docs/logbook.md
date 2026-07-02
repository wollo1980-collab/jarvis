# Logbook

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
