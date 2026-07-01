# AI START

## Zweck
Einstiegspunkt fuer jede KI, die an Jarvis arbeitet.

## Erste Regel
Nicht sofort programmieren.
Zuerst Projektstand, Roadmap, ADRs und offene Aufgaben lesen.

## Pflicht-Lesereihenfolge
1. `README.md`
2. `docs/handbook/JARVIS_MASTER_HANDBOOK_v3_2.docx`
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
