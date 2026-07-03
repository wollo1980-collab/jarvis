---
charter_version: 1.0
gilt_fuer: Alle Entwickler an Jarvis (Mensch oder KI) in der Lead-Software-Engineer-Rolle
status: In Kraft (charter_version 1.0). Umsetzungsstand der beschriebenen Mechanismen: siehe PROJECT_STATE.
aendern: Nur mit PO-Freigabe (Rot). Entwurf/Umsetzung durch den Engineer, Entscheidung/Freigabe durch den PO.
---

# Jarvis Developer Charter

> **Leitsatz:** Im Zweifel gewinnen **Stabilität, Verständlichkeit und Wartbarkeit** vor Tempo und Umfang. (Operationalisiert die Handbook-Prinzipien KISS/YAGNI, „keine Magie" und „Erfolg = weniger Last, nicht mehr Funktion".)

Dies ist die **einzige** Quelle dafür, *wie* an Jarvis entwickelt wird. Sie beschreibt ausschließlich das Verhalten des Entwicklers — **keine** Fakten, **keinen** Projektstatus, **keine** Architektur, **keine** Versionsinfo.

- Für *warum/was* (Vision, DNA, Leitplanken, Architekturprinzipien) → **Handbook** (Projektverfassung).
- Für den *aktuellen Stand* → **PROJECT_STATE**.
- Für *Entscheidungen* → **ADRs**. Für *Historie* → **CHANGELOG** (was) / **logbook** (warum + Lessons).

---

## 0. Rollen: Entscheidung vs. Umsetzung

- **Product Owner (PO):** entscheidet *ob* eine Änderung erfolgen darf (fachlich/strategisch), prüft das Ergebnis und gibt frei. **Pflegt/editiert keine Dokumente.**
- **Lead Engineer (Mensch oder KI):** entscheidet *wie* (technisch/redaktionell), **erstellt und pflegt alle Dokumente — inklusive Verfassung (Handbook) und dieser Charter** — im Rahmen der Delegations-Stufen (§3).

Die Stufe bestimmt nur, *wie viel PO-Zustimmung vor/nach der Umsetzung* nötig ist — **nie, wer editiert.** Der PO editiert nie.

---

## 1. Dokument-Landkarte (wo lebt welcher Fakt)

| Information | Heimat |
|---|---|
| Warum Jarvis existiert · DNA · Vision · Leitplanken · Architekturprinzip · Sicherheitsmodell (Prinzip) | Handbook |
| Aktuelle Version · Teststand · was fertig · aktives Increment + Scope · offene Aufgaben · bekannte Schuld · Known Limitations | PROJECT_STATE |
| Eine konkrete Architektur-/Designentscheidung (+ Alternativen/Konsequenzen) · was ist *bewusst nicht* im Scope | ADR |
| Was hat sich (nutzerseitig) geändert | CHANGELOG |
| Warum wurde etwas so gemacht · Lesson Learned | logbook |
| *Wie* entwickelt wird (dieser Prozess) | CONTRIBUTING (dieses Dokument) |

**Grundregel:** Jeder Fakt hat **genau eine** Heimat. Andere Dokumente **verlinken**, kopieren nie.

**Konflikt-Hierarchie:** Widersprechen sich Quellen über *dauerhafte* Fakten, gilt `HANDBOOK (Verfassung) > ADR > Code > README`. Für den *aktuellen Stand* ist `PROJECT_STATE` maßgeblich (die Verfassung trägt keinen Status).

### Grenzregeln (der eigentliche Anti-Duplizierungs-Mechanismus)

| Grenze | Regel |
|---|---|
| Handbook ↔ CONTRIBUTING | Charter *verweist* auf Verfassungsprinzipien, wiederholt sie nie. |
| Handbook ↔ PROJECT_STATE | Prinzip/Invariante → Handbook. Ist-Zustand/Umsetzungsgrad → PROJECT_STATE. **Kein Status/„umgesetzt" im Handbook.** |
| ADR ↔ logbook | Dauerhafte/architektonische Entscheidung → ADR. Taktische Entscheidung + Lesson → logbook. |
| ADR ↔ PROJECT_STATE | Scope-*Beschluss* unveränderlich in der ADR („bewusst NICHT"). PROJECT_STATE nur der *Zeiger* („aktives Increment = X, Scope laut ADR-Y"). |
| CHANGELOG ↔ logbook | *Was* (nutzerseitig) → CHANGELOG. *Warum* + Lesson → logbook. |
| README ↔ CONTRIBUTING | README = menschlicher Einstieg + Projektüberblick, verweist hierher; beschreibt selbst keinen Prozess. |

---

## 2. Session-Runbook (bei jedem Sitzungsbeginn abzuarbeiten)

1. **Einstieg lesen:** README → CONTRIBUTING (dieses Dokument).
2. **Stand lesen:** PROJECT_STATE (aktuelle Version, aktives Increment, Scope, offene Aufgaben, bekannte Schuld).
3. **Kontext lesen:** alle logbook-/CHANGELOG-Einträge **seit Beginn des aktiven Increments** (`active_increment` im PROJECT_STATE-Kopf) + die regelnde(n) ADR(s) dieses Increments.
4. **Leitplanken lesen:** nur das Leitplanken-Kapitel des Handbooks (immer). Das restliche Handbook **nur bei Bedarf** (wenn eine 🟡/🔴-Änderung Architektur/Prinzipien berührt).
5. **Konsistenz-Gate laufen lassen** (§7).
6. **Gate FAIL → STOP.** Abweichung an den PO melden. **Nicht bauen, nicht committen** auf inkonsistentem Stand.
7. **Gate PASS →** nächsten sinnvollen Schritt aus aktivem Increment + Scope ableiten.
8. Schritt über die **Delegations-Matrix** (§3) einordnen: 🟢 ausführen · 🟡/🔴 oder Scope-Zweifel → **vorschlagen + Freigabe abwarten**.
9. **Vor Abschluss:** Tests laufen (§9) · Doku-Pflichten (§6) erfüllen · **Gate erneut (muss PASS)** · berichten.
10. **Das Repo darf am Sitzungsende nie inkonsistent sein.**

Sonderfälle: kein klarer nächster Schritt → Optionen vorschlagen. Drift *während* der Sitzung bemerkt → stoppen, melden.

---

## 3. Delegations-Matrix

| Stufe | Bedeutung | Beispiele |
|---|---|---|
| 🟢 **Grün** — autonom, ende-zu-ende | Umkehrbare Arbeit in freigegebenem Scope; Doku-Konsistenz | Freigegebene ADR/Scope umsetzen · Bugfix ohne Architektur-/Verhaltensänderung · verhaltenswahrender Refactor in einem Modul · Tests · PROJECT_STATE/CHANGELOG/logbook aktuell halten · Gate laufen · **vorschlagen (immer erlaubt)** |
| 🟡 **Gelb** — vorschlagen → Freigabe, dann umsetzen | Neue Entscheidungen/Fläche | Neue ADR / Architektur-/Querschnittsentscheidung · alles mit **Sicherheit, Datenverarbeitung, Secrets, Lesen/Handeln-Grenze** · neue Abhängigkeit · neuer Connector/Integration · **Scope-Änderung** · Löschen/Überschreiben nicht selbst erstellter Dateien · **Commit** (heute) |
| 🔴 **Rot** — PO-Entscheidung vorab **und** PO-Freigabe des Ergebnisses | Unumkehrbar, nach außen, Autorität. *Umsetzung immer durch den Engineer.* | Unumkehrbare/nach-außen-Aktionen (echte Mail senden, bezahlter Live-Call, force-push, Daten löschen) · Increment als **„fertig" erklären** / Version taggen · **Handbook oder diese Charter ändern** · alles, was die DNA als Nicht-Ziel markiert |

**Commit-Übergang:** Commit ist heute 🟡 (explizite Freigabe je Commit) und wird 🟢, sobald Gate + Tests automatisch vor jedem Commit laufen (pre-commit/CI). *Leitplanke vor Autonomie.*

**Freigabe-Protokollierung (Pflicht des Engineers):** Jede 🟡-/🔴-Freigabe wird im Repo festgehalten — die Commit-Message referenziert sie; bei Handbook-/Charter-Änderungen zusätzlich eine logbook-Zeile „PO-Freigabe am <Datum> für <Änderung>". So bleibt die Entscheidungskette auditierbar, **ohne dass der PO etwas schreibt.**

---

## 4. Änderungs-Lebenszyklus

`Vorschlag → (ADR falls nötig, §5) → PO-Freigabe → Umsetzung → Tests → Doku-Update (§6) → Gate PASS → Commit (auf Freigabe) → ggf. „fertig" (🔴, PO)`

### Entscheidungs-Prozeduren
- **30-Minuten-Regel:** Wird über eine Frage länger als ~30 Minuten diskutiert, prüfe *„Kann ein kleiner Prototyp sie schneller beantworten?"* (Ausnahme: grundlegende Architekturentscheidungen dürfen länger reifen).
- **Design-Review (drei Blickwinkel):** Vor größeren Entscheidungen aus drei Perspektiven prüfen — *Pragmatiker* (Funktioniert das heute?), *Architekt* (In zwei Jahren noch wartbar?), *Produktmanager* (Bringt das Nutzen?).

### Feature-Entscheidung (Idee → bauen oder Backlog?)
Jede neue Idee — egal von wem — wird an fünf Fragen geprüft:
1. Löst es ein **echtes Problem** des Nutzers? (sonst → Backlog)
2. Passt es zum **aktuellen Scope/Increment**? (sonst → später)
3. Kann der Nutzer es nach dem Einbau **verstehen/erklären**? (sonst → vereinfachen)
4. Ist der **Wartungsaufwand** langfristig vertretbar? (sonst → Backlog)
5. Gibt es eine **einfachere Lösung** für dasselbe Problem? (dann erst die einfache)

Regel: **Zwei oder mehr „Nein" → Backlog** (nicht in die aktuelle Arbeit). „Interessant" ist kein Grund, „nützlich" schon.

---

## 5. Wann ist eine ADR Pflicht?

Eine ADR ist erforderlich (🟡), wenn eine Änderung mindestens eines erfüllt:
- führt eine **Architektur-/Querschnittsentscheidung** ein oder ändert sie,
- bindet einen **externen Dienst/eine Integration** an,
- berührt **Sicherheit, Datenverarbeitung oder die Lesen/Handeln-Grenze**,
- führt eine **neue Abhängigkeit** oder ein **neues dauerhaftes Datenformat/-Store** ein,
- legt den **Scope eines neuen Increments** fest.

Keine ADR nötig (🟢) für: Bugfixes, verhaltenswahrende Refactorings, Doku-Pflege, Tests, Umsetzung einer bereits per ADR freigegebenen Sache.

### ADR-Format
Jede ADR-Datei unter `docs/adr/ADR-NNN.md` folgt der Struktur: **Problem/Kontext · Entscheidung · Begründung · Alternativen · Konsequenzen · Status**. Der `Status` ist `Accepted` / `Superseded` / `Rejected` — nur er ändert sich nachträglich (Superseded stets durch eine *neue* ADR, siehe §6). Umfangreichere ADRs ergänzen Risiken/Teststrategie. Frühe Seed-ADRs (ADR-000–003) liegen ebenfalls als Dateien in `docs/adr/`.

---

## 6. Doku-Pflichten (nach jeder abgeschlossenen Änderung)

- **PROJECT_STATE** aktualisieren: Version/Teststand/aktives Increment/offene Aufgaben — **und den maschinenlesbaren Kopf** (§7) konsistent halten.
- **CHANGELOG**: nutzerseitige Änderung ergänzen (append).
- **logbook**: Begründung/Lesson + ggf. „PO-Freigabe"-Zeile ergänzen (append).
- **ADR**: bei Architekturentscheidung anlegen; Status pflegen (Accepted → ggf. Superseded durch neue ADR).
- Grenzregeln (§1) einhalten: nichts doppelt ablegen.

### CHANGELOG-Format
Pro Eintrag: Überschrift `## <Version/Baustein> – <Titel> (<Datum>)`, darunter `### Neu` / `### Geändert` (weitere nach Bedarf). Append-only.

### logbook-Eintrag
Pro Eintrag: **Kontext · Umsetzung · Tests · bewusst nicht Umgesetztes · Lessons Learned**. Neueste Einträge oben. Append-only — nie leeren.

### Konsolidierungsprozess
Wenn dauerhafte Erkenntnisse es erfordern (oder nach einem abgeschlossenen größeren Baustein): freigegebene ADRs, `PROJECT_STATE`, `logbook` und `CHANGELOG` durchsehen; **dauerhaft gültige** Entscheidungen in die Verfassung (`HANDBOOK`) übernehmen; **temporäre** Punkte aus `PROJECT_STATE` entfernen oder als erledigt markieren. `logbook` und `CHANGELOG` werden dabei **nie geleert** (permanente, anwachsende Historie). Änderungen an Verfassung/Charter sind 🔴 (§12).

---

## 7. Konsistenz-Gate

Ein kleines, abhängigkeitsarmes Skript (`scripts/check_consistency.py`, stdlib + git), das Doku↔Realität **mechanisch** prüft. Es liest den maschinenlesbaren Kopf von PROJECT_STATE:

```
version: <…>
active_increment: <ADR-id>
tests: <n>
latest_adr: <NNN>
stand: <YYYY-MM-DD>
```

**Prüfungen:**
| Check | Invariante |
|---|---|
| Testzahl | gezählte Testfunktionen in `tests/` == `tests:` |
| Letzte ADR | höchste `ADR-NNN.md` == `latest_adr:` |
| Stand-Frische | `stand:` vs. letztes Commit-Datum (Schwelle → FAIL) |
| Handbook-Reinheit | Handbook enthält keine Status-Tokens (`umgesetzt in`, Testzahlen, Versions-Fortschritt) |

**Wann:** Session-Start (Runbook 5), vor jedem Commit, in CI beim Push.
**FAIL bedeutet:** STOP — nicht bauen, nicht committen. Melden.

*Hinweis:* Solange das Gate-Skript nicht vorhanden ist, führt der Engineer die obigen Prüfungen manuell nach dieser Liste durch; der Umsetzungsstand wird in PROJECT_STATE geführt.

---

## 8. Definition of Done (je Increment)

- Code umgesetzt; **Tests grün** (§9).
- Doku-Pflichten (§6) erfüllt; **Gate PASS**.
- ADR-Status aktuell.
- Keine offenen `TODO`/`FIXME`-Marker im Code (oder bewusst in `PROJECT_STATE` als offene Aufgabe geführt).
- Nicht selbst verifizierbare Schritte (z. B. echte Live-Tests auf dem Windows-Rechner, bezahlte API-Calls) sind als „**umgesetzt, wartet auf PO-Live-Verifikation**" markiert — der Engineer kann sie nicht selbst schließen.
- Ein Increment als **„fertig" zu erklären ist 🔴** (PO).

---

## 9. Tests & Reproduzierbarkeit

- **Ein** bekannter Testbefehl; die Sandbox-/`--basetemp`-Eigenheit gehört in `pytest.ini`/`conftest.py`, nicht in mündliche Regeln.
- Externe Systeme (LLM-APIs, IMAP, Telegram, Registry, Windows-only) werden **gemockt**; Tests laufen ohne echte Keys/Netzwerk.
- Neue Funktion ⇒ neue Tests. „Keep it Working": kein Merge/Commit auf rotem Stand.

---

## 10. Git-/Commit-Konventionen

- Auf dem Default-Branch nur mit Bedacht; sonst Branch. (Aktuelle Praxis des Projekts beachten.)
- **Kleine, für sich lauffähige Commits** — kein roter Zwischenstand.
- **Commit nur nach Freigabe** (🟡), nachdem das Gate PASST.
- Commit-Message: prägnant, mit Präfix nach Art der Änderung (`feat:` · `fix:` · `docs:` · `refactor:` · `test:`), referenziert die **PO-Freigabe** und ggf. die ADR.
- Abschluss der Commit-Message mit der Co-Author-Zeile des jeweiligen Engineers.
- Keine Secrets in Git (Handbook/ADR-018). Kein `--no-verify`, kein Umgehen von Hooks.

---

## 11. Sicherheits-Gate

Alles, was **handelt** statt nur zu lesen, **fremde/nicht-vertrauenswürdige Inhalte** verarbeitet oder **Secrets/Daten** berührt, ist mindestens 🟡 und erfordert einen expliziten Sicherheits-Review gegen die Handbook-Leitplanke „Wissen fließt, Handeln braucht Erlaubnis". Prompt-Injection ist als Standard-Risiko mitzudenken, sobald fremde Inhalte in ein Modell fließen, das Aktionen auslösen kann.

---

## 12. Änderung dieser Charter und des Handbooks (Meta)

Beides ist **🔴**: Der PO entscheidet und gibt frei, **der Engineer entwirft und setzt um**. Jede solche Änderung erhöht die jeweilige Version (`charter_version` / `constitution_version`) und wird in der Commit-Message + logbook mit PO-Freigabe protokolliert. Verfassung und Charter sind bewusst *schwerer* zu ändern als normale Arbeit (Entrenchment).

---

## 13. Governance-Version

Jedes „Gesetz"-Dokument trägt seine Version im **eigenen** Kopf — nicht in PROJECT_STATE:
- `CONTRIBUTING.md` → `charter_version`
- `HANDBOOK.md` → `constitution_version`

So erkennt jeder Entwickler/jedes KI-Modell die geltende Governance sofort beim Lesen des jeweiligen Dokuments, ohne Cross-Doc-Abgleich.

---

## 14. Coding Standards

- **Sprache:** Python 3.11+.
- **Namen:** Dateien/Funktionen/Variablen `snake_case`, Klassen `PascalCase`, Konstanten `UPPER_CASE`.
- **Imports:** Reihenfolge Standardbibliothek → Third-party → lokale Module, je Gruppe durch eine Leerzeile getrennt.
- **Typing:** alle Funktionen mit Type Hints.
- **Docstrings:** jede Funktion mit kurzem Docstring.
- **Formatter/Linting:** Black (Formatierung), Ruff (Linting).
- **Kommentare** erklären das *Warum*, nicht das *Was*.
- Betriebsprinzipien (Testbarkeit, Logging, nie lautlos scheitern, kein `except: pass`) stehen als Prinzipien in der Verfassung (`HANDBOOK`, Engineering-Prinzipien) — hier bewusst nicht wiederholt.
