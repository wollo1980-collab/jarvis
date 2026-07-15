# Ehrliche Grenzen

Jarvis dokumentiert seine Grenzen genauso sorgfältig wie seine Fähigkeiten —
was hier steht, ist Stand der Realität, nicht Bescheidenheits-Prosa.
(Stand: 14.07.2026; der maschinell geprüfte Detailstand lebt im privaten
Projektstand, die Architektur-Entscheidungen in `docs/adr/`.)

## Plattform & Sprache

- **Windows-first:** Sprachausgabe, Single-Instance-Lock, Autostart und die
  PC-Admin-Befehle nutzen Windows-Bordmittel; andere Plattformen sind
  ungetestet.
- **Deutsch zuerst:** Persona, Befehle und Beispiele sind auf Deutsch gebaut.
- **Ein-Personen-System by design:** genau ein Nutzer, genau ein autorisierter
  Telegram-Chat — Mehrbenutzer ist ein Nicht-Ziel.

## Cloud-Abhängigkeiten

- **Braucht einen OpenAI-Key** (Planner/Chat/Transkription) — variable Kosten
  im Cent-Bereich pro Tag; Sprachausgabe geht offline per Piper.
- **Keine lokale Transkription:** Sprach-Eingabe (Push-to-talk, Telegram-Voice)
  läuft über die OpenAI-Cloud; das Wake-Word selbst wird zu 100 % lokal
  bewertet.
- `search_web` hängt an einer externen Suchseite (Trefferlisten, keine ganzen
  Artikel) und kann bei Markup-Änderungen, Bot-Schutz oder fehlender
  Internetverbindung ausfallen.

## Fähigkeits-Grenzen (bewusste Gates, keine Versäumnisse)

- **Genau EINE gleichzeitige Agenten-Delegation** (Single-Flight, Busy-Flag) —
  eine zweite Anfrage wird höflich abgelehnt, bis die erste fertig ist.
- **Asynchrone Delegation nur auf Kanälen mit Async-Opt-in** (Runtime-Telegram,
  Browser-Kanal). Die Konsole wartet synchron; der ältere Standalone-Bot
  (`telegram_main.py`) lehnt Delegations-Intents ab (kein Hintergrund-Worker).
- **Gebaute Skills werden katalogisiert, aber nicht ausgeführt** — das
  Ausführen ist eine bewusst offene Produktentscheidung.
- **Mail: nur lesen.** Senden/Antworten/Löschen ist bewusst nicht gebaut.
- Der **Agenten-Arm hängt am interaktiven CLI-Login** des Coding-Agenten;
  läuft der Login ab, ist der Arm bis zum manuellen Re-Login außer Dienst
  (Jarvis sagt das klar, eine Vorab-Warnung ist technisch nicht möglich).

## Kleinere technische Grenzen

- `system_status`/`analyze_pc`: keine Temperaturen (psutil-Limitierung unter
  Windows).
- `read_excel`: nur `.xlsx`/`.xlsm`, nur Werte, 500 Zeilen je Blatt.
- Sprach-Eingabe: Stille-Fenster fest 1,0 s.
- Kokoro-TTS spricht kein Deutsch (siehe INSTALLATION.md, TTS-Backends).
- Single-Instance-Schutz wirkt pro `memory_dir` gegen gleichzeitigen
  Prozess-START — nicht gegen externes Löschen der Lock-Datei zur Laufzeit
  (akzeptiertes Restrisiko).
- Autostart: fester Registry-Eintragsname `"Jarvis"` = eine Installation pro
  Windows-Benutzerkonto; nach einem Projekt-Umzug repariert ein erneutes
  „aktiviere deinen Autostart" den Pfad (keine Automatik).
