# framework_feedback

Rückfluss-Sammlung von Jarvis an das AI Project Framework (CONTRIBUTING §15). Einträge werden hier dokumentiert und nie direkt im Framework-Repository umgesetzt.

## 2026-07-04

### FF-J-001 - PROJECT_INIT deckt die Adoption von Bestandsprojekten nicht ab

- Herkunftsprojekt: `jarvis`
- Konkreter Beleg: Bei der Delta-Analyse von Jarvis gegen Framework v1.0 (04.07.2026) zeigte sich, dass `docs/PROJECT_INIT.md` ausschließlich den Greenfield-Start regelt. Für ein Bestandsprojekt mit eigener, gereifter Governance gibt es keinen definierten Adoptionsweg — die Migration musste als „assoziierte Angleichung" mit eigenem Abweichungsregister (Jarvis-CONTRIBUTING §15) improvisiert werden.
- Vorgeschlagene Änderung: PROJECT_INIT (oder ein Folgeabschnitt) sollte neben dem Greenfield-Start einen Adoptionsmodus für Bestandsprojekte beschreiben: Delta-Analyse statt Ableitung, bewusste Einzelübernahmen per Freigabe, dokumentiertes Abweichungsregister statt erzwungener Konformität.

### FF-J-002 - Handbook-Reinheits-Check: laufender Datenpunkt aus Jarvis

- Herkunftsprojekt: `jarvis`
- Konkreter Beleg: Das Framework hat den Verfassungs-Reinheits-Check zweimal bewusst nicht übernommen (Evidenz-Argument, zuletzt ADR-006). Jarvis betreibt den Check seit dem Governance-Umbau produktiv (`scripts/check_consistency.py`, Prüfung auf Status-Tokens im Handbook) — er hat dort historisch echte Verstöße verhindert, seit der Handbook-Konsolidierung aber nicht mehr angeschlagen.
- Vorgeschlagene Änderung: Keine sofortige — Jarvis liefert als Betreiber des Checks fortlaufend den Datenpunkt für die offene Framework-Frage. Schlägt der Check in Jarvis erneut real an, wird das hier als Beleg nachgetragen; bleibt er über längere Zeit stumm, stützt das die Framework-Position.

### FF-J-003 - Nutzungslauf vor Abschluss / bewusster Abschluss vor Ausbau

- Herkunftsprojekt: `jarvis`
- Konkreter Beleg: In der Nutzwert-Phase wurden drei reale Live-Funde nicht als Anlass für Scope-Ausbau genommen, sondern als minimale Produktkorrekturen innerhalb des bereits freigegebenen Web-v1-Bausteins behandelt (DuckDuckGo-Bot-Challenge -> Lite-Route + Fehlererkennung, überlange Werbe-URLs -> Trefferfilter + Telegram-Chunking, generische Preisfrage -> gezielte Query-Ergänzung). Direkt davor wurde die erste reale Reibung (Autostart nach Umstrukturierung) erst end-to-end verifiziert und sauber abgeschlossen, bevor der nächste Baustein begonnen wurde.
- Vorgeschlagene Änderung: Die zwei Pattern sollten im Framework als explizit benennbare Abschluss-/Qualitätsmuster geprüft werden: **"Nutzungslauf vor Abschluss"** (Live-Funde eines bereits begonnenen Bausteins zuerst absorbieren) und **"Bewusster Abschluss vor Ausbau"** (eine behobene reale Reibung sichtbar abschließen, bevor der nächste Scope beginnt). Jarvis liefert dafür jetzt einen n=2-Datenpunkt.
