# J.A.R.V.I.S. — ein persönlicher Assistent, der wirklich bei dir wohnt

Sag **„Hey Jarvis"** quer durchs Zimmer. Drück einen Hotkey. Schreib ihm per
Telegram von unterwegs. Oder tipp in sein Fenster mit dem atmenden Orb.
Dahinter arbeitet **eine** Pipeline — mit Gedächtnis, Sicherheitsstufen und
einem Dashboard, in dem **jede Zahl echt ist**. Komplett lokal gehostet,
Cloud nur dort, wo sie gebraucht wird (LLM, Transkription).

![Jarvis-UI: Orb, Tages-Karten und Chat — hier mit leerem Gedächtnis und neutralen Daten](docs/assets/jarvis-ui.png)

**Das Problem:** Assistenten, die beeindruckend aussehen, sind meist Kulisse —
und die echten wohnen in fremden Clouds.
**Die Lösung:** ein Assistent auf dem eigenen Rechner, dessen Fähigkeiten
einzeln, testgetrieben und dokumentiert gewachsen sind.
**Der Nutzen:** Erinnerungen, die sich von selbst melden; Briefings aus echten
Quellen; kritische Aktionen nur mit Bestätigung — und ein Gesicht, das zeigt,
was gerade wirklich passiert.

## Was Jarvis kann (Kurzfassung)

Vollständig und aktuell in **[FUNKTIONEN.md](FUNKTIONEN.md)** — die Essenz:

- **Vier Zugänge, eine Pipeline:** Wake-Word („Hey Jarvis", 100 % lokal
  bewertet), Push-to-talk, Telegram (Text + Sprachnachrichten), Browser-UI —
  alle durch denselben Kern, dieselben Sicherheitsstufen.
- **Ein denkender Kern statt Stichwort-Menü (ADR-060):** ein LLM ruft die
  Befehle als *Werkzeuge* auf und führt heute den Großteil der
  Alltags-Intents, auch mehrschrittig; gefährliche Pfade bleiben hinter dem
  Bestätigungs-Gate. Umgehängt wird nach Messdaten, nicht nach Bauchgefühl.
- **Alltag end-to-end:** Erinnerungen, die sich selbst melden; benannte
  Listen; ein echter Outlook-Kalender (lesen **und** eintragen/verschieben/
  absagen — Umkehrbares sofort mit Undo-Hinweis, nur Absagen fragt);
  Briefings aus echten Quellen (RSS, Open-Meteo, IMAP-Kopfzeilen); Spotify.
- **Ein Agenten-Arm, der wirklich baut:** Repo-Analysen, Umsetzungsarbeit und
  „**Bau mir X**" — im technisch erzwungenen Käfig, mit Live-Erlaubnisfragen
  (🔐), Not-Stopp und Ergebnis-Push, auch mobil. Nie in Jarvis' eigenem Repo.
- **Gedächtnis mit Sicherheitsnetz:** dauerhafte Fakten, Ereignis-Tagebuch,
  nächtliche Reflexion, einmalige Merk-Angebote — und ein **Papierkorb** für
  alles Gelöschte („stell den Fakt/Eintrag/die Liste wieder her").
- **Ein Gesicht, das nicht lügt:** Orb und Tages-Karten zeigen echte
  Zustände und echte Quellen. Nichts ist inszeniert.
- **Sicherheit als Architektur** und **dokumentationsgetriebene Entwicklung**
  (ADRs, Konsistenz-Gate + Vollsuite im Pre-Commit, ehrliches Logbook) —
  Details in [SICHERHEIT.md](SICHERHEIT.md).

## Schnellstart (Windows)

```powershell
git clone <repo-url> jarvis && cd jarvis
powershell -ExecutionPolicy Bypass -File setup.ps1   # venv + Pakete (gepinnt) + config
setx OPENAI_API_KEY "sk-..."                         # Key NUR als Env-Variable
.venv\Scripts\pythonw.exe jarvis_ui.pyw              # Runtime + UI-Fenster
```

Ohne Key startet alles außer LLM/Transkription. Alles Weitere (Telegram,
Sprachausgabe, Wake-Word, Provider-Wahl): **[INSTALLATION.md](INSTALLATION.md)**.

## Ehrliche Grenzen

Windows-first, Deutsch zuerst, Ein-Personen-System by design, braucht einen
OpenAI-Key — die vollständige, gepflegte Liste inklusive der bewussten Gates
steht in **[GRENZEN.md](GRENZEN.md)**.

---

## Dokument-Landkarte

| Frage | Dokument |
| --- | --- |
| Was kann Jarvis heute, im Detail? | [FUNKTIONEN.md](FUNKTIONEN.md) |
| Wie installiere und betreibe ich ihn? | [INSTALLATION.md](INSTALLATION.md) |
| Wie ist das Sicherheitsmodell? | [SICHERHEIT.md](SICHERHEIT.md) |
| Was kann er (noch) nicht? | [GRENZEN.md](GRENZEN.md) |
| Wie ist er gewachsen? | [HISTORIE.md](HISTORIE.md) + `docs/adr/` |

## Für Entwickler (Mensch oder KI)

**Verbindlicher Einstieg: zuerst `CONTRIBUTING.md` lesen** (Jarvis Developer
Charter) — sie beschreibt den vollständigen Entwicklungsprozess.

- **Wofür / was** (Vision, DNA, Leitplanken) → `docs/handbook/HANDBOOK.md`.
- **Wie entwickelt wird** → `CONTRIBUTING.md`.
- **Aktueller Stand** → `docs/PROJECT_STATE.md`. **Entscheidungen** → `docs/adr/`.

## Struktur

Der vollständige, **aktuelle** Verzeichnisbaum wird aus dem Repository
generiert statt von Hand gepflegt: `python scripts/gen_structure.py`

- **`core/`** — Kern: Config, Modelle, AI-Layer/Provider, Planner,
  Reasoning-Kern, Tool-Schemas, Speech, Connectoren (Mail/Web/Kalender/…).
- **`commands/`** — Command-Registry + Befehle.
- **`executor/`** — führt Pläne aus (Bestätigung, ✓/✗/?-Report).
- **`memory/`** — Fakten, Einträge, Listen, Personen, Episoden, Regeln.
- **`scripts/`** — Werkzeuge: Konsistenz-Gate, Eval-Batterien, Auth-Helfer.
- **`tests/`** — pytest, alles gemockt.
- **Einstiegspunkte** — `jarvis_ui.pyw`/`jarvis_runtime.py` (empfohlen),
  `main.py` (Konsole), `telegram_main.py`, `dashboard.py`.
