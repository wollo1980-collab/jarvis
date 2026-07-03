# AI START

## Zweck
Einstiegspunkt fuer jede KI, die an Jarvis arbeitet.

## Erste Regel
Nicht sofort programmieren.
Zuerst Projektstand, Roadmap, ADRs und offene Aufgaben lesen.

## Pflicht-Lesereihenfolge
1. `README.md`
2. `docs/handbook/JARVIS_MASTER_HANDBOOK_v3_8.docx` (v3.2/v3.3/v3.4/v3.5/v3.6/v3.7 bleiben als Archiv, Grundlage fuer v0.4/v0.5/v0.6/v0.7, den Runtime-Baustein zwischen v0.7 und v0.8 sowie v0.8 Multi-KI; v3.8 = Leitbild/DNA)
3. `docs/PROJECT_STATE.md`
4. `docs/logbook.md`
5. `docs/CHANGELOG.md`
6. `docs/adr/`

## Single Source of Truth
`Handbook > ADR > Code > README`

## Rolle
- Nutzer ist Product Owner.
- Die KI darf keine Architekturentscheidungen oder Prioritaetsaenderungen selbst treffen.
- Bei Konflikten gewinnt immer das Master-Handbook.

## Vor jeder Aenderung beantworten
1. Welche Version ist abgeschlossen?
2. Welche Version wird entwickelt?
3. Was ist das naechste Ziel laut Handbook?
4. Welche offenen TODOs existieren?
5. Welche ADR war die letzte?
6. Wurde seit der letzten Handbook-Version eine Hauptversion - oder ein eigenstaendiger, in Kap. 13 benannter Infrastruktur-/Runtime-Baustein ohne eigene vX.Y-Versionsnummer - abgeschlossen, fuer die/den die Konsolidierung (Kap. 19) noch aussteht? Falls ja: Konsolidierungsprozess vor jeder weiteren Arbeit einleiten.

## Nach jeder Aenderung
- Tests ausfuehren.
- `docs/CHANGELOG.md` aktualisieren.
- `docs/logbook.md` aktualisieren.
- Bei Architekturaenderung eine neue ADR anlegen.

## Niemals
- Architektur spontan aendern.
- Roadmap aendern.
- Versionen ueberspringen.
- TODOs loeschen.
- Das Handbuch ignorieren.

## Grundsatz
Jarvis ist dokumentationsgetrieben.
Dokumentation beschreibt die Architektur.
Code implementiert die Dokumentation.

## Stop-Regel bei Abweichung
Wenn deine Zusammenfassung nicht mit `docs/PROJECT_STATE.md`
uebereinstimmt, aendere keinen Code.
Frage zuerst den Product Owner.
