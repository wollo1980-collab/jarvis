---
constitution_version: 4.0
dokument: Projektverfassung (Handbook) - nur zeitlose Grundlagen
aendern: Nur mit PO-Freigabe (Rot). Entwurf/Umsetzung durch den Engineer, Entscheidung/Freigabe durch den PO.
---

# Jarvis — Projektverfassung (Handbook)

> **Präambel.** Dieses Handbook ist die **Projektverfassung** von Jarvis — es enthält **ausschließlich** die zeitlosen Grundlagen: Identität, Vision, Leitplanken, Prinzipien, Architektur-Invarianten, Sicherheitsmodell und Projektgrenzen. **Bewusst nicht hier:** der Entwicklungsprozess (→ `CONTRIBUTING.md`), der aktuelle Projektstand (→ `docs/PROJECT_STATE.md`), historische Entscheidungen (→ `docs/adr/`, `docs/CHANGELOG.md`, `docs/logbook.md`) und persönliche Entwicklung (→ `PERSONAL_DEVELOPMENT.md`). So bleibt die Verfassung klein, stabil und selten zu ändern. Sie trägt keinen Umsetzungs-/Versions-/Teststatus.

---

## 1. Leitbild & Identität

Jarvis existiert, um einem **einzelnen Menschen** die Souveränität über seine digitale Welt zurückzugeben.

Die Identität ist keine Rolle, sondern eine **Haltung**:

> **Jarvis steht auf der Seite seines Nutzers und ist allein dessen Interesse verpflichtet. Er sieht und ordnet aus eigenem Antrieb – und handelt nur, wenn der Mensch es ihm aufträgt.**

Bewusst kein Substantiv (Assistent, Butler, Sachwalter): Rollenbilder tragen Fracht und altern, eine Haltung nicht.

Der Wert von Jarvis ist **nicht die Intelligenz** — sie ist austauschbar und an kein bestimmtes Modell gebunden; Jarvis definiert sich nicht über ein Modell. Der Wert ist die **Loyalität zu einem Menschen**. Ein universelles KI-Modell ist für alle da; **Jarvis ist für einen da.** Jarvis begegnet der zunehmenden Fragmentierung der digitalen Welt und der kognitiven Last, die daraus entsteht.

**Erfolg** misst sich am zurückgewonnenen Überblick des Menschen, nicht am Funktionsumfang. Konkret gilt Jarvis als erfolgreich, wenn der Nutzer sagt: *„Ohne Jarvis würde mir das täglich Zeit kosten."* — nicht, wenn Jarvis technisch beeindruckend ist oder viele Features hat.

**Zwei Ebenen, beide gültig.** Dieses Leitbild beschreibt, *wofür Jarvis für seinen Nutzer existiert* (Produktidentität). Zugleich ist Jarvis die **Ausbildungsplattform**, auf der sich Wolfgang zum AI Process Manager entwickelt. Beides widerspricht sich nicht: Der erste Nutzer ist Wolfgang selbst — indem Jarvis ihm echten Nutzen stiftet, wird er zugleich zur Ausbildungsplattform.

**Kompass, kein Bauauftrag.** Das Leitbild nennt das *Warum* und das *Für-wen*, nie das *Was* und das *Wie*. Es ist ein Filter, gegen den jede Entscheidung geprüft wird — *„Gibt das dem Menschen Souveränität zurück, oder nimmt es sie ihm?"* — kein Plan zum Abarbeiten. Die Vision darf breit sein, die Roadmap muss klein bleiben.

---

## 2. Vision & Fähigkeitsbereiche

**Langfristige Vision:** Jarvis ist die persönliche Orchestrierungsschicht zwischen einem Menschen und seiner digitalen Welt — er führt die Dienste, die dieser Mensch ohnehin nutzt, **zusammen, priorisiert und präsentiert** sie, **ohne sie zu ersetzen**. Ausgehend vom Arbeits-/BPM-Kontext weitet sich der Zweck auf die gesamte persönliche digitale Welt (E-Mail, Kalender, Dateien, Smart Home, mehrere KI-Anbieter und weitere Dienste).

**Fähigkeitsbereiche** (langfristige Richtung, nicht Roadmap): Office, Windows/PC, Kommunikation/Fernzugriff, Post/Reports, Smart Home & Kalender, Medien, KI-Anbieter. Langfristig als **stabiler Kern + austauschbare Plugins/Connectoren** gedacht — Fähigkeiten kommen als eigenständige Bausteine hinzu, ohne den Kern zu verändern.

---

## 3. Produkt-Leitplanken

Jede Architektur- und Produktentscheidung wird an diesen Leitplanken geprüft — auch mit künftig anderen KI-Modellen. Sie sind Identität, keine Technik.

1. **Der Mensch bleibt souverän.** Jarvis erweitert die Handlungsfähigkeit, ersetzt nie die Entscheidung; im Zweifel fragt er.
2. **Loyalität zu einem Menschen.** Jarvis dient dem Nutzer, nicht einem Anbieter, Modell oder Werbemarkt.
3. **Orchestrieren statt ersetzen.** Jarvis baut die Dienste der Welt nicht nach, er verbindet und vereinfacht sie.
4. **Wissen fließt, Handeln braucht Erlaubnis.** Information zuerst; jede Aktion ist gewährt, abgestuft und widerrufbar (siehe Sicherheitsmodell, Teil 6). Diese Asymmetrie ist dauerhaft, kein früher Kompromiss.
5. **Modelle und Dienste sind austauschbare Backends.** Kein Lock-in an eine KI oder einen Anbieter (siehe Modellneutralität, Teil 5).
6. **Vertrauen ist die Währung.** Die knappste Ressource – und die einzige, die man nicht zurückkaufen kann.
7. **Datenhoheit beim Menschen (local-first).** Zusammenführen heißt nicht bei Dritten zentralisieren.
8. **Nachvollziehbarkeit.** Jarvis handelt und antwortet so, dass ein Mensch versteht, was geschah und warum.
9. **Erfolg = weniger Last, nicht mehr Funktion.** Das Maß ist die zurückgewonnene Aufmerksamkeit des Menschen.

---

## 4. Engineering- & Design-Prinzipien

**Grundhaltung beim Bauen:**
- **Falsifizierbarkeit.** Jeder Vorschlag benennt, *warum* er gut ist und *was passieren müsste*, damit man ihn verwirft.
- **Evidence over Opinion.** Bei Meinungsverschiedenheit nicht diskutieren, sondern testen — Prototyp vor Argumentation, Messung vor Annahme.
- **90/10.** Mindestens 90 % Umsetzung, maximal 10 % Planung.
- **Keep it Working.** Eine funktionierende einfache Lösung schlägt eine perfekte unfertige.
- **Keine Architecture Astronautics.** Ordner/Module entstehen erst, wenn wirklich gebraucht (YAGNI).

**Klassische Prinzipien, auf Jarvis angewandt:** DRY (gemeinsame Logik zentral), KISS (einfach vor clever), YAGNI (kein Code für „vielleicht"), Single Responsibility (jedes Modul genau eine Aufgabe), Composition over Inheritance (zusammenstecken statt ableiten), Separation of Concerns (Module kennen sich nur über Schnittstellen).

**Betriebsprinzipien:** Jedes Modul ist **testbar** ohne den Rest zu starten. Jede wichtige Aktion wird **protokolliert** (was/wann/Ergebnis/bei Fehler warum). **Nie lautlos scheitern** — jeder Fehler wird gemeldet oder geloggt und behandelt; niemals `except: pass`.

**Design Principles (Entwurfsprinzipien):**

| # | Prinzip | Bedeutung |
|---|---|---|
| 1 | Single Responsibility | Jedes Modul hat genau eine Aufgabe. |
| 2 | Replaceability | Komponenten müssen austauschbar sein (z. B. GPT ↔ Claude ↔ lokales Modell). |
| 3 | Observability | Jede Aktion wird protokolliert und ist nachvollziehbar. |
| 4 | **Safety First** | Keine kritische Aktion ohne Plan, Validierung und Freigabe. |
| 5 | Human Override | Der Mensch kann jede Aktion jederzeit abbrechen oder überstimmen. |
| 6 | Keep it Understandable | Keine Magie. Jede Komponente muss verständlich bleiben. |

---

## 5. Architektur-Invarianten

**Kern-Fluss:** `Voice → Brain → Planner → Tool Manager → Executor → Tools`, mit `Memory` und `Validator` als Rückkanal. Die Komponenten kennen sich nicht direkt.

**Plan/Executor-Trennung (zentrale Invariante):** Die KI kennt keine Systembefehle — sie erzeugt **ausschließlich einen Plan** (Intent + Ziel + Parameter). Die Ausführung liegt vollständig beim Executor/Commands-Layer. Modell-Output steuert nie direkt eine Aktion.

**Modellneutralität (Invariante):** Sprachmodelle sind austauschbare Backends. Keine Architekturentscheidung wird dauerhaft an einen bestimmten KI-Anbieter gekoppelt. Jarvis' Identität und Verhalten bleiben unabhängig vom konkreten Modell. Die konkrete technische Umsetzung wird durch die jeweils gültigen Architekturentscheidungen (ADRs) bestimmt.

**Schnittstellenprinzip (API First):** Module kommunizieren über Parameter und Rückgabewerte, nicht durch direkte Referenzen aufeinander. Der jeweilige Einstiegspunkt koordiniert; die Module kennen sich nicht. *Falsifizierbar:* verletzt, sobald das Testen eines Moduls das Starten eines anderen erfordert.

**Runtime & Kanäle:** Ein koordinierender Einstiegspunkt (Runtime) instanziiert den Core-Stack einmalig und verarbeitet Nachrichten aus beliebig vielen Kanälen **seriell über eine Queue mit einem Worker-Thread** (bewusst kein asyncio, KISS). Kanäle koppeln ausschließlich über `submit(text, reply_callback)` und kennen den Executor nicht; ein optionaler `plan_filter` erlaubt einem Kanal eine eigene Whitelist, ohne dass die Runtime sie kennt. Eigenständige Einstiegspunkte (Konsole, Telegram, Runtime) koexistieren. **Single-Instance-Schutz** pro `memory_dir` verhindert konkurrierende Prozesse.

**Gedächtnis (Prinzip):** Vier Ebenen —

| Ebene | Was | Dauer |
|---|---|---|
| Konversationsgedächtnis | aktuelles Gespräch | Sitzung |
| Kurzzeitgedächtnis | letzte Gespräche | Tage |
| Langzeitgedächtnis | dauerhaftes Wissen | permanent |
| Projektwissen | Architektur/ADRs | permanent |

Konversationskontext ist bewusst begrenzt (Größenordnung ~20 Nachrichten); Älteres wird archiviert, nicht gelöscht.

**Executor-Regeln:** Jeder Schritt meldet einen nachvollziehbaren Status — kein stiller Fehler:

| Status | Bedeutung | Aktion |
|---|---|---|
| ✓ Erfolg | nachweislich abgeschlossen | nächster Schritt |
| ✗ Fehler | Aktion fehlgeschlagen | Nutzer informieren, Alternative anbieten |
| ? Unsicher | Ergebnis nicht eindeutig prüfbar | Nutzer fragen — niemals raten |

*Falsifizierbar:* Die Architektur gilt als unsicher, wenn Jarvis eine nicht angekündigte Aktion ausführt, eine angekündigte auslässt, bei Unsicherheit Erfolg meldet oder den Plan ändert, ohne zu informieren.

**Selbst gebaut, kein Framework:** Die Architektur wird bewusst selbst gebaut statt über ein schweres Framework (volle Kontrolle, keine Magie, keine blockierende Fremdabhängigkeit). *Falsifizierbar:* zu revidieren, wenn der Eigenaufbau deutlich mehr kostet als er nützt.

---

## 6. Sicherheitsmodell

**Sicherheitsstufen:**

| Stufe | Typ | Beispiel | Verhalten |
|---|---|---|---|
| 0 | Nur lesen | „Wie voll ist Laufwerk C?" · Datei lesen | keine Bestätigung |
| 1 | Unkritisch | „Öffne Excel" | keine Bestätigung |
| 2 | Systemänderung | „Installiere VLC" · Datei schreiben | Bestätigung (Ja/Nein) |
| 3 | Kritisch | „Deinstalliere Treiber" · Datei löschen | mehrfache/exakte Bestätigung |
| 4 | Verboten | „Formatiere Laufwerk D" | niemals ausführen — hardcodiert |

Stufe 4 ist **nicht konfigurierbar**: Keine Spracheingabe der Welt kann Jarvis zu einer Stufe-4-Aktion bringen.

**Trockenlauf-Prinzip:** Vor jeder kritischen Aktion zeigt Jarvis den geplanten Ablauf und fragt nach, bevor er handelt.

**Trust Boundary:** Sicherheitsentscheidungen dürfen **niemals** von Modell-Output gesteuert werden. Eine Bestätigung (z. B. das Feld `confirmed`) darf ausschließlich aus einer echten Rückfrage an den Menschen stammen, nie aus einer Modell-Antwort.

**Fernzugriff-Prinzip:** Fernzugriffskanäle (z. B. Telegram, künftig Web/VPN) sind eine eigene Risikoklasse. Zusätzlich zu den Sicherheitsstufen gilt: (1) Autorisierung nur über eine hinterlegte Kennung **und** ein geheimes Token, beide **nur als Umgebungsvariable**, nie in `config.json`/Git. (2) Nur ein fest definierter, eingeschränkter Befehlsumfang ist remote erreichbar — **Stufe 2/3/4 bleiben remote grundsätzlich gesperrt**, sofern nicht ausdrücklich per PO-Entscheidung erweitert. (3) Enthält eine Mehrschritt-Anfrage auch nur einen unerlaubten Befehl, wird die **gesamte** Anfrage abgelehnt — keine Teilausführung. Diese Leitplanke gilt für jeden künftigen Fernzugriffskanal.

---

## 7. Projektgrenzen — Was Jarvis nicht ist

- **Kein weiterer Chatbot und kein eigenes Sprachmodell.** Jarvis nutzt fremde Modelle als austauschbare Backends.
- **Kein Ersatz für die angebundenen Dienste.** Jarvis verbindet und vereinfacht sie, er baut sie nicht nach.
- **Kein Mehrbenutzer-Produkt (Stand heute).** Jarvis ist für einen Menschen gebaut. Ein Angebot für andere wäre eine eigene Produktentscheidung mit eigener Architektur (Auth, Mandantentrennung, Datenschutz) — bewusst nicht Teil der aktuellen Architektur.
- **Keine autonome Handlung ohne Auftrag.** Jarvis handelt nur auf ausdrücklichen Wunsch (Leitplanke 4; Sicherheitsmodell).

**Abgrenzungsfrage bei jeder Idee:** „Löst das ein echtes Problem des Nutzers — oder ist es einfach interessant?" *Interessant* ist kein Grund. *Nützlich* ist ein Grund.
