"""
Jarvis Command Center / UI (ADR-046 + ADR-047, Welle 4.3/4.5) - Jarvis'
Gesicht: Orb, Begruessung mit den Tages-Karten, Chat und Status - jede
Zahl aus einer realen Quelle (core/dashboard_data.py), nichts Kulisse.

Zwei Datenpfade, wuerdevolles Degradieren:
- READ-ONLY (immer): dieser Prozess liest memory_data/logs/PROJECT_STATE
  und serviert /api/status - funktioniert auch, wenn Jarvis AUS ist.
- LIVE (wenn die Runtime laeuft): die Seite verbindet sich mit dem
  BrowserChannel (ADR-047, Port ui_port) - Chat + Orb-Zustaende per SSE.
  Runtime aus => Orb "AUSSER DIENST", Eingabe gesperrt, Zahlen bleiben.

Eigener, strikt lesender Prozess: kein Eingriff in die Runtime, kein Lock,
kein Schreiben. stdlib-only, bindet AUSSCHLIESSLICH an 127.0.0.1.

Start:  python dashboard.py           (oeffnet den Browser)
        python dashboard.py --no-browser
"""
from __future__ import annotations

import json
import logging
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from core.config import BASE_DIR, CONFIG_FILE, Config
from core.dashboard_data import collect_status, llm_lineup

logger = logging.getLogger("jarvis.dashboard")

_BIND_HOST = "127.0.0.1"  # bewusst NUR localhost (ADR-046)
_PROJECT_STATE = BASE_DIR / "docs" / "PROJECT_STATE.md"

# Lokale Schriften (PO 2026-07-10 "bau die Schriften ein"): Rajdhani + Inter
# (beide SIL OFL, Lizenztexte liegen daneben) als Repo-Dateien, vom Dashboard
# selbst serviert - KEIN Google-Fonts-Aufruf zur Laufzeit, laeuft offline.
# Fail-closed: nur exakt diese Namen werden ausgeliefert (kein Pfad-Traversal).
_FONT_DIR = BASE_DIR / "assets" / "fonts"
_FONT_FILES = {"inter-var.woff2", "rajdhani-400.woff2", "rajdhani-500.woff2"}

_PAGE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Jarvis</title>
<style>
  * { box-sizing:border-box; margin:0; padding:0; }
  /* Farb-/Typo-Politur (PO-Feedback 2026-07-10 "Farben und Schriften dort
     stimmiger"): Palette von Tuerkis-auf-Schwarz zu Tiefblau + Cyan-Akzent,
     Labels in Bahnschrift (technische DIN-Schrift, auf Windows vorinstalliert
     - kein Font-Download, alles bleibt lokal), staerkere Gewichts-Kontraste. */
  :root { --acc:#38c6f4; --lab:#8fb4cf; --line:rgba(80,170,230,0.17); }
  /* Lokale Schriften (OFL, assets/fonts, vom Dashboard selbst serviert):
     Inter (variabel, 100-900) fuer Flaechentext, Rajdhani fuer Labels.
     Fehlt eine Datei, greifen die Fallbacks (Segoe UI/Bahnschrift). */
  @font-face { font-family:'Inter'; src:url('/fonts/inter-var.woff2') format('woff2');
               font-weight:100 900; font-display:swap; }
  @font-face { font-family:'Rajdhani'; src:url('/fonts/rajdhani-400.woff2') format('woff2');
               font-weight:400; font-display:swap; }
  @font-face { font-family:'Rajdhani'; src:url('/fonts/rajdhani-500.woff2') format('woff2');
               font-weight:500; font-display:swap; }
  body { background:radial-gradient(ellipse at 25% 0%, #0d1c30 0%, #060c18 55%, #040810 100%);
         min-height:100vh; font-family:'Inter','Segoe UI',system-ui,sans-serif; color:#dce8f6; display:flex; }
  body::before { content:''; position:fixed; inset:0; pointer-events:none;
    background-image:linear-gradient(rgba(90,170,235,0.03) 1px, transparent 1px),
                     linear-gradient(90deg, rgba(90,170,235,0.03) 1px, transparent 1px);
    background-size:44px 44px; }
  /* Die fruehere linke Mini-Leiste (Mini-Orb + ONLINE) ist raus (PO-Befund
     2026-07-10: ihr Rand hing als verwaister Strich im Leeren, seit Inhalt
     + Timeline als Paar zentriert sind). ONLINE wohnt jetzt im Header. */
  /* #center haelt Inhalt + Timeline als Paar zusammen und zentriert BEIDE
     (Live-Befund 2026-07-10: auf breiten Monitoren klebte die Spalte am
     Fensterrand, kaum wahrnehmbar). */
  #center { display:flex; flex:1; justify-content:center; min-width:0; }
  /* Groessen-Politur (PO 2026-07-10 "alles etwas groesser"): Inhalt 980px,
     Spalte 340px. Auf sehr breiten Fenstern (>=1820) waechst der Inhalt auf
     1100px (PO 2026-07-11 "wir verschenken Platz") - siehe die Media-Query
     unten. Die Schwelle ist bewusst hoch, damit immer >=20px Rand bleibt
     (kein Kleben am Rand, kein durch Scrollbalken erzwungener Ueberlauf). */
  /* Seite = Fensterhoehe (PO-Reibung "ich muss scrollen"): main ist auf
     100vh gebunden, das Gespraech ist das DEHNBARE Element (flex) und
     scrollt innen. Passt der Inhalt trotzdem nicht (sehr kleine Fenster),
     scrollt main als ehrlicher Rueckfall selbst. */
  main { flex:0 1 980px; padding:24px 32px 18px; max-width:980px; display:flex;
         flex-direction:column; height:100vh; overflow-y:auto; position:relative;
         scrollbar-width:thin; scrollbar-color:rgba(56,198,244,0.2) transparent; }
  /* Grid 1fr auto 1fr (PO-Reibung 2026-07-11 "Name nicht passend zur Orb"):
     die Mittelspalte zentriert das Logo EXAKT ueber dem Orb, unabhaengig von
     den unterschiedlich breiten Seiten (space-between schob es sonst nach
     links, weil ONLINE breiter ist als die Uhr). */
  header { display:grid; grid-template-columns:1fr auto 1fr; align-items:baseline; margin-bottom:16px; }
  header .side { font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif; font-size:13px;
         color:rgba(165,200,225,0.65); font-weight:300; letter-spacing:1px; }
  header .side:last-of-type { justify-self:end; text-align:right; }
  header .logo { font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif; color:var(--acc);
         letter-spacing:8px; font-size:16px; font-weight:400;
         text-shadow:0 0 18px rgba(56,198,244,0.45); }
  .hero { display:flex; flex-direction:column; align-items:center; gap:10px; margin-bottom:18px; }
  /* 180 statt 140 px (PO-Wunsch 2026-07-10): der Orb ist die Hauptfigur -
     Ringe/Halo/Kern proportional mitskaliert. */
  /* 200px (Politur-Runde 2) - Mark-II-Ringe skalieren als SVG automatisch mit. */
  /* margin-bottom (PO-Reibung 2026-07-11 "Orb ist unten im Text drin"): die
     Mark-II-Ringe stehen 14px ueber die Orb-Box hinaus (inset:-14px) und lagen
     sonst auf "BEREIT". Der Abstand gibt den Ringen Luft, ohne den Orb zu
     verkleinern. */
  .orb { position:relative; width:200px; height:200px; margin-bottom:16px;
         display:flex; align-items:center; justify-content:center; }
  .orb .a1 { position:absolute; inset:0; border-radius:50%;
     background:conic-gradient(from 0deg, transparent 0 78%, var(--glow) 92%, transparent 100%);
     -webkit-mask:radial-gradient(farthest-side, transparent calc(100% - 2px), #000 calc(100% - 1.5px));
     mask:radial-gradient(farthest-side, transparent calc(100% - 2px), #000 calc(100% - 1.5px));
     animation:spin var(--spin1, 9s) linear infinite; }
  .orb .a2 { position:absolute; inset:20px; border-radius:50%;
     background:conic-gradient(from 180deg, transparent 0 60%, var(--glow-soft) 80%, transparent 100%);
     -webkit-mask:radial-gradient(farthest-side, transparent calc(100% - 1.5px), #000 calc(100% - 1px));
     mask:radial-gradient(farthest-side, transparent calc(100% - 1.5px), #000 calc(100% - 1px));
     animation:spin var(--spin2, 6s) linear infinite reverse; }
  .orb .halo { position:absolute; inset:46px; border-radius:50%;
     background:radial-gradient(circle, var(--halo) 0%, transparent 72%);
     animation:breathe var(--breathe, 2.6s) ease-in-out infinite; }
  .orb .core { width:88px; height:88px; border-radius:50%;
     background:radial-gradient(circle at 38% 34%, #eafcff 0%, var(--core) 42%, var(--core-deep) 82%);
     box-shadow:0 0 22px var(--shadow1), 0 0 60px var(--shadow2), inset 0 0 14px rgba(255,255,255,0.35);
     animation:breathe var(--breathe, 2.6s) ease-in-out infinite; }
  #state { font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif; font-size:12px;
           letter-spacing:5px; font-weight:400; }
  /* Begruessung in Rajdhani (PO 2026-07-10 "die Schrift gefaellt mir noch
     nicht" - das duenne Inter wirkte hier beliebig): HUD-Stil wie die
     Panel-Titel - Versalien-Zeile oben, kraeftiger Name darunter. */
  .hello { text-align:center; margin:4px 0 8px; }
  .hello .small { font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif; font-size:15px;
        font-weight:400; letter-spacing:4px; text-transform:uppercase;
        color:rgba(160,200,225,0.65); }
  .hello .name { font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif; font-size:50px;
        font-weight:500; letter-spacing:2px; color:#f0f8ff; line-height:1.1;
        text-shadow:0 0 26px rgba(56,198,244,0.25); }
  .hello .sub { font-size:14.5px; font-weight:300; color:rgba(180,210,225,0.6); margin-top:8px; }
  .hello .sub b { color:var(--acc); font-weight:400; }
  /* Live-Zeile (PO 2026-07-10 "cool, wenn er da schreibt, was er gerade
     macht"): waehrend Jarvis arbeitet/wartet/spricht ersetzt der echte
     Taetigkeits-Text die Tages-Zeile - danach kehrt sie zurueck. */
  .hello .sub.sub-live { color:rgba(140,200,240,0.85); }
  /* Kacheln passen sich dem INHALT an (PO-Reibung 2026-07-11: "Wetter-
     Kachel riesig fuer 2 Zeilen"): feste, konsistente Breite, links
     gepackt, Leerraum ans Zeilenende statt in jede Kachel; jede Kachel
     nur so hoch wie ihr Inhalt (align-items:flex-start). */
  .cards { display:flex; flex-wrap:wrap; align-items:flex-start; gap:14px;
           width:100%; margin-bottom:18px; }
  .card { flex:0 1 250px; position:relative; border:1px solid var(--line); border-radius:10px;
          background:linear-gradient(180deg, rgba(30,52,78,0.48) 0%, rgba(12,24,42,0.5) 100%);
          padding:16px; backdrop-filter:blur(6px);
          box-shadow:0 10px 26px rgba(2,6,14,0.45), 0 0 26px rgba(56,198,244,0.05),
                     inset 0 1px 0 rgba(170,220,250,0.08), inset 0 0 26px rgba(56,198,244,0.025); }
  .card .ic { width:38px; height:38px; border-radius:50%; display:flex; align-items:center;
          justify-content:center; margin-bottom:10px; font-size:18px;
          background:rgba(56,198,244,0.08); border:1px solid rgba(56,198,244,0.3); }
  .card .t { font-size:15px; font-weight:600; color:#f0f7ff; }
  .card .t s { color:rgba(185,215,235,0.55); }  /* abgelaufen: durchgestrichen+gedimmt */
  /* Vollbild-Umschalter (PO-Wunsch 2026-07-10 "kleines Konfig-Symbol"):
     die Fullscreen-API braucht eine Nutzer-Geste - und funktioniert damit
     zuverlaessig, waehrend --start-fullscreen bei bereits laufendem
     Browser ignoriert wird. */
  .fs-btn { background:none; border:1px solid var(--line); border-radius:6px;
        color:rgba(150,185,210,0.55); font-size:13px; cursor:pointer;
        padding:2px 8px; margin-left:10px; font-family:inherit;
        transition:color .15s, border-color .15s; vertical-align:middle; }
  .fs-btn:hover { color:var(--acc); border-color:rgba(56,198,244,0.4); }
  /* Stopp-Knopf (ADR-056 Scheibe 2): erscheint nur, waehrend ein Agent
     laeuft - bricht ihn mitten im Flug ab. */
  #agent-stop { margin-top:10px; width:100%; font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif;
        font-size:12px; letter-spacing:1px; text-transform:uppercase; cursor:pointer;
        padding:7px 0; border-radius:7px; background:none;
        color:#e79a8c; border:1px solid rgba(224,138,122,0.45);
        transition:color .15s, border-color .15s, background .15s; }
  #agent-stop:hover { color:#f4b3a5; border-color:rgba(224,138,122,0.8); background:rgba(224,138,122,0.1); }
  #agent-stop:disabled { opacity:.4; cursor:default; }
  #agent-redirect { display:flex; }
  #agent-redirect-input { flex:1 1 auto; min-width:0; font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif;
        font-size:12.5px; padding:6px 9px; border-radius:7px; background:rgba(10,22,34,0.6);
        color:rgba(210,230,242,0.95); border:1px solid rgba(111,157,255,0.35); outline:none;
        transition:border-color .15s; }
  #agent-redirect-input:focus { border-color:rgba(111,157,255,0.75); }
  #agent-redirect-input::placeholder { color:rgba(150,185,205,0.5); }
  #agent-redirect-send { flex:0 0 auto; font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif;
        font-size:12px; letter-spacing:1px; text-transform:uppercase; cursor:pointer;
        padding:0 12px; border-radius:7px; background:none;
        color:#8fb4ff; border:1px solid rgba(111,157,255,0.45);
        transition:color .15s, border-color .15s, background .15s; }
  #agent-redirect-send:hover { color:#b3ccff; border-color:rgba(111,157,255,0.8); background:rgba(111,157,255,0.1); }
  #agent-redirect-send:disabled { opacity:.4; cursor:default; }
  .card-x { position:absolute; top:8px; right:10px; background:none; border:none;
        color:rgba(150,185,210,0.35); font-size:13px; cursor:pointer; padding:4px;
        font-family:inherit; transition:color .15s; }
  .card-x:hover { color:#e08a7a; }
  /* Loesch-Rueckfrage (PO-Reibung 2026-07-11: Erinnerung loeschen ist
     irreversibel - eine Frage statt ein stiller Klick). Inline auf der
     Karte, im HUD-Look statt als Windows-Dialog. */
  .card-confirm { position:absolute; inset:0; border-radius:inherit;
        background:linear-gradient(180deg, rgba(10,16,26,0.93), rgba(8,13,22,0.97));
        backdrop-filter:blur(2px); display:flex; flex-direction:column;
        align-items:center; justify-content:center; gap:14px; text-align:center;
        padding:14px; z-index:3; }
  .card-confirm .cc-q { font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif;
        font-size:15px; font-weight:500; letter-spacing:0.4px; color:#e6f2fb; }
  .card-confirm .cc-btns { display:flex; gap:10px; }
  .card-confirm button { font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif;
        font-size:12px; letter-spacing:0.8px; text-transform:uppercase; cursor:pointer;
        padding:7px 14px; border-radius:7px; border:1px solid transparent;
        background:none; transition:color .15s, border-color .15s, background .15s; }
  .card-confirm .cc-yes { color:#e79a8c; border-color:rgba(224,138,122,0.4); }
  .card-confirm .cc-yes:hover { color:#f4b3a5; border-color:rgba(224,138,122,0.75);
        background:rgba(224,138,122,0.1); }
  .card-confirm .cc-no { color:rgba(185,215,235,0.7); border-color:rgba(150,185,210,0.28); }
  .card-confirm .cc-no:hover { color:#e6f2fb; border-color:rgba(150,185,210,0.5); }
  .card .d { font-size:13px; font-weight:400; margin-top:3px; color:rgba(185,215,235,0.7); }
  .card .s { font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif; font-size:10px;
          color:rgba(150,185,210,0.55); margin-top:9px; font-weight:300; letter-spacing:0.8px; }
  /* HUD-Panel (UI-Kampagne Scheibe 1, Command-Center-Look): gemeinsame
     Optik fuer alle Kaesten - Titelzeile + Ecken-Akzente wie im Film-HUD.
     Reines CSS, kein einziger Fantasie-Wert dahinter. */
  /* Tiefe (PO 2026-07-10 "wie in der Vorlage"): vertikaler Verlauf (oben
     heller), Schlagschatten nach unten (Panel schwebt ueber dem Grund) und
     eine 1px-Lichtkante an der Oberseite - das Trio macht die Plastizitaet. */
  .panel { position:relative; border:1px solid var(--line);
           background:linear-gradient(180deg, rgba(30,52,78,0.5) 0%, rgba(12,24,42,0.55) 100%);
           border-radius:10px; padding:16px 20px; backdrop-filter:blur(6px);
           box-shadow:0 12px 32px rgba(2,6,14,0.5), 0 0 30px rgba(56,198,244,0.05),
                      inset 0 1px 0 rgba(170,220,250,0.09), inset 0 0 30px rgba(56,198,244,0.03);
           transition:box-shadow .5s, border-color .5s; }
  /* Aktiv-Glow (PO 2026-07-10 "auch fuer Fenster, die gerade aktiv sind"):
     ein Panel leuchtet, WAEHREND darin wirklich etwas passiert - Agent
     arbeitet (blau), Schritte laufen (blau), Bestaetigung offen (gelb),
     neue Antwort (kurzes Aufblitzen). Gekoppelt an dieselben echten
     Ereignisse wie Orb und Sprech-Leiste - nie an einen Timer. */
  .panel.glow-work { border-color:rgba(111,157,255,0.45);
      box-shadow:0 12px 32px rgba(2,6,14,0.5), 0 0 32px rgba(111,157,255,0.28),
                 inset 0 1px 0 rgba(170,220,250,0.09), inset 0 0 24px rgba(111,157,255,0.07); }
  .panel.glow-work .panel-head { color:#9db9ff; text-shadow:0 0 10px rgba(111,157,255,0.6); }
  .panel.glow-wait { border-color:rgba(242,207,107,0.45);
      box-shadow:0 12px 32px rgba(2,6,14,0.5), 0 0 32px rgba(242,207,107,0.25),
                 inset 0 1px 0 rgba(170,220,250,0.09), inset 0 0 24px rgba(242,207,107,0.07); }
  .panel.glow-wait .panel-head { color:#f2cf6b; text-shadow:0 0 10px rgba(242,207,107,0.55); }
  @keyframes panelflash { 0% { box-shadow:0 12px 32px rgba(2,6,14,0.5), 0 0 36px rgba(56,198,244,0.4),
      inset 0 1px 0 rgba(170,220,250,0.09), inset 0 0 26px rgba(56,198,244,0.1);
      border-color:rgba(56,198,244,0.6); } 100% { } }
  .panel.glow-flash { animation:panelflash 1.6s ease-out 1; }
  .panel::before, .panel::after { content:''; position:absolute; width:16px; height:16px; pointer-events:none; }
  .panel::before { top:-1px; left:-1px; border-top:1px solid rgba(56,198,244,0.7);
           border-left:1px solid rgba(56,198,244,0.7); border-top-left-radius:10px; }
  .panel::after { bottom:-1px; right:-1px; border-bottom:1px solid rgba(56,198,244,0.7);
           border-right:1px solid rgba(56,198,244,0.7); border-bottom-right-radius:10px; }
  .panel-head { display:flex; justify-content:space-between; align-items:baseline;
           font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif; color:var(--lab);
           font-size:12px; letter-spacing:2.5px; font-weight:500; margin-bottom:10px; }
  /* Ansichten-Nav (Nachtplan Scheibe 4, "sichtbares Gedaechtnis"): die
     Nav kehrt zurueck, weil es jetzt ECHTE zweite Ansicht gibt
     (Attrappen-Verbot von damals bleibt gewahrt). */
  .viewnav { display:flex; gap:8px; justify-content:center; margin-bottom:10px; }
  .vn { font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif; background:none;
        border:1px solid var(--line); border-radius:999px; padding:4px 18px;
        color:rgba(150,185,210,0.6); font-size:12px; letter-spacing:2.5px;
        cursor:pointer; transition:color .15s, border-color .15s; }
  .vn.active { color:var(--acc); border-color:rgba(56,198,244,0.45); }
  .mem-section { font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif;
        color:var(--lab); font-size:11px; letter-spacing:2.5px; margin:12px 0 6px; }
  .mem-row { display:flex; align-items:baseline; gap:10px; padding:5px 0;
        border-bottom:1px solid rgba(80,170,230,0.08); font-size:13.5px; font-weight:400; }
  .mem-row:last-child { border-bottom:none; }
  .mem-text { flex:1; color:rgba(210,232,245,0.9); }
  .mem-meta { font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif;
        font-size:10.5px; letter-spacing:1px; color:rgba(150,185,210,0.55); white-space:nowrap; }
  .mem-x { background:none; border:none; color:rgba(150,185,210,0.35); font-size:12px;
        cursor:pointer; padding:2px 6px; font-family:inherit; transition:color .15s; }
  .mem-x:hover { color:#e08a7a; }
  .mem-old { opacity:.6; font-size:12.5px; }
  #mem-body { max-height:60vh; overflow-y:auto; scrollbar-width:thin;
        scrollbar-color:rgba(56,198,244,0.25) transparent; }
  .qc-row { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:10px; }
  .qc { background:rgba(56,198,244,0.06); color:rgba(170,220,240,0.9); border:1px solid rgba(56,198,244,0.25);
        border-radius:999px; padding:7px 16px; font-size:12.5px; cursor:pointer; font-family:inherit;
        font-weight:400; letter-spacing:0.5px; transition:background .15s, box-shadow .15s; }
  .qc:hover:enabled { background:rgba(56,198,244,0.14); box-shadow:0 0 12px rgba(56,198,244,0.2); }
  .qc:disabled { opacity:.3; cursor:default; }
  .llm-row { display:flex; justify-content:space-between; gap:10px; font-size:12.5px;
        font-weight:400; line-height:2.0; }
  .llm-row .k { font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif;
        color:rgba(150,185,210,0.65); letter-spacing:1.5px; font-size:10.5px; font-weight:300; }
  .llm-row .v { color:rgba(200,230,240,0.9); font-variant-numeric:tabular-nums; text-align:right; }
  .chatbox { margin-bottom:12px; display:flex; flex-direction:column;
             flex:1 1 auto; min-height:190px; }
  #log { flex:1; min-height:0; overflow-y:auto;
         display:flex; flex-direction:column; gap:12px;
         font-size:14.5px; scrollbar-width:thin; scrollbar-color:rgba(56,198,244,0.25) transparent; }
  #log:empty::before { content:'Sprich mit mir, Sir — hier, per Zuruf oder Strg+Alt+J.';
         color:rgba(150,185,205,0.4); font-weight:300; font-size:13px; }
  .me { align-self:flex-end; background:rgba(56,198,244,0.1); border-radius:14px 14px 4px 14px;
        padding:8px 13px; max-width:85%; font-weight:400; white-space:pre-wrap; }
  .jarvis { align-self:flex-start; max-width:92%; font-weight:400; color:#d3e9f5; line-height:1.55;
        padding-left:14px; border-left:2px solid rgba(56,198,244,0.55); white-space:pre-wrap; }
  .confirm { align-self:flex-start; max-width:92%; font-weight:300; color:#f2cf6b; line-height:1.55;
        padding-left:14px; border-left:2px solid rgba(242,207,107,0.6); white-space:pre-wrap; }
  /* Uhrzeit an der Chat-Zeile (PO-Wunsch 2026-07-11): dezent, tabellarische
     Ziffern; rechtsbuendig unter der eigenen Blase, linksbuendig bei Jarvis. */
  .me .ts, .jarvis .ts { display:block; font-size:10px; opacity:.42; margin-top:3px;
        letter-spacing:.5px; font-variant-numeric:tabular-nums; }
  .me .ts { text-align:right; }
  /* Verlauf nach Neuladen (PO-Reibung 2026-07-10): fruehere Zeilen gedimmt,
     darunter ein Trenner - danach beginnt die Live-Sitzung. */
  #log .old { opacity:.55; }
  .log-divider { align-self:center; font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif;
        font-size:9.5px; letter-spacing:3px; color:rgba(150,185,210,0.45); padding:2px 0; }
  .inputrow { display:flex; align-items:center; gap:10px;
        background:linear-gradient(180deg, rgba(30,52,78,0.5) 0%, rgba(14,26,44,0.55) 100%);
        border:1px solid var(--line); border-radius:999px; padding:8px 10px 8px 22px;
        box-shadow:0 8px 22px rgba(2,6,14,0.4), inset 0 1px 0 rgba(170,220,250,0.08); }
  #msg { flex:1; background:transparent; border:none; outline:none; color:#d7e6f2;
        font-size:15px; font-family:inherit; font-weight:400; }
  #msg::placeholder { color:rgba(170,200,215,0.45); }
  #send { background:rgba(56,198,244,0.12); color:var(--acc); border:1px solid rgba(56,198,244,0.4);
        border-radius:999px; padding:10px 24px; font-size:14px; cursor:pointer; letter-spacing:1px;
        font-family:inherit; box-shadow:0 0 16px rgba(56,198,244,0.15); }
  #send:disabled { opacity:.35; cursor:default; box-shadow:none; }
  /* Sprech-Leiste (PO-Wunsch 2026-07-10 "Leuchteffekt wie die Mikroleiste"):
     visualisiert den ECHTEN Kanalzustand aus dem SSE-Strom - die Equalizer-
     Balken sind Deko (laufen nur bei hoert/spricht), der ZUSTAND ist nie
     simuliert. Gleiches Prinzip wie die Orb-Impulse. */
  #voicebar { display:flex; align-items:center; gap:18px; margin-top:12px; padding:11px 22px;
      border:1px solid var(--line); border-radius:999px;
      background:linear-gradient(180deg, rgba(30,52,78,0.42) 0%, rgba(14,26,44,0.48) 100%);
      box-shadow:0 8px 22px rgba(2,6,14,0.4), inset 0 1px 0 rgba(170,220,250,0.07);
      color:rgba(120,170,210,0.35); transition:box-shadow .5s, border-color .5s, color .5s; }
  .vb-label { font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif; font-size:11.5px; letter-spacing:2.5px;
      color:rgba(150,185,210,0.55); white-space:nowrap; transition:color .5s, text-shadow .5s; }
  /* Feine Striche statt Bloecke (PO 2026-07-10 "zu dick"): feste 2.5px
     Breite, der Zwischenraum verteilt sich - Waveform- statt Balken-Optik. */
  .vb-eq { flex:1; display:flex; align-items:center; justify-content:space-between; height:20px; }
  .vb-eq span { flex:0 0 2.5px; height:100%; background:currentColor; border-radius:1px;
      transform:scaleY(0.12); transform-origin:center;
      animation:eq 1.1s ease-in-out infinite; animation-play-state:paused; }
  @keyframes eq { 0%,100% { transform:scaleY(0.12); } 50% { transform:scaleY(1); } }
  #voicebar.vb-hoert { color:#3ddc97; border-color:rgba(61,220,151,0.45);
      box-shadow:0 8px 22px rgba(2,6,14,0.4), 0 0 28px rgba(61,220,151,0.28), inset 0 0 20px rgba(61,220,151,0.08); }
  #voicebar.vb-spricht { color:#c9a5ff; border-color:rgba(201,165,255,0.45);
      box-shadow:0 8px 22px rgba(2,6,14,0.4), 0 0 28px rgba(201,165,255,0.3), inset 0 0 20px rgba(201,165,255,0.09); }
  #voicebar.vb-hoert .vb-eq span, #voicebar.vb-spricht .vb-eq span { animation-play-state:running; }
  #voicebar.vb-hoert .vb-label { color:#7fe9bd; text-shadow:0 0 12px rgba(61,220,151,0.6); }
  #voicebar.vb-spricht .vb-label { color:#dcc6ff; text-shadow:0 0 12px rgba(201,165,255,0.6); }
  #voicebar.vb-arbeitet { color:rgba(111,157,255,0.5);
      box-shadow:0 0 22px rgba(111,157,255,0.18); border-color:rgba(111,157,255,0.3); }
  #voicebar.vb-wartet { color:rgba(242,207,107,0.5);
      box-shadow:0 0 22px rgba(242,207,107,0.2); border-color:rgba(242,207,107,0.35); }
  #voicebar.vb-aus { opacity:.45; }
  footer { display:flex; gap:18px; flex-wrap:wrap; font-size:11.5px; font-weight:300;
        color:rgba(150,185,205,0.6); padding:16px 4px 6px; margin-top:auto; }
  footer { font-family:'Rajdhani','Bahnschrift','Segoe UI',sans-serif; letter-spacing:0.6px; }
  footer .right { margin-left:auto; color:rgba(56,198,244,0.5); }
  #flow-items .flow-pend { opacity:.5; }
  #flow-items .flow-work { color:#f2cf6b; animation:workpulse 1.4s ease-in-out infinite; }
  #flow-items .flow-fail { color:#e08a7a; }
  #flow-items .flow-redirect { color:#8fb4ff; }
  @keyframes workpulse { 0%,100% { opacity:1; } 50% { opacity:.55; } }
  /* Timeline als rechte Spalte (PO-Wunsch 2026-07-10: "da ist ja Platz") -
     auf schmalen Fenstern rutscht sie unter den Inhalt. */
  #rightbar { width:340px; flex-shrink:0; padding:68px 24px 18px 0; }
  #rightbar #flow { position:sticky; top:16px; }
  #flow-items { max-height:70vh; overflow-y:auto; }
  /* Linke Spalte (PO-Reibung 2026-07-11): Benachrichtigungen + "Die Lage"
     wandern nach links, damit das Gespraech in der Mitte mehr Hoehe bekommt.
     Gleiche Breite wie rechts -> das Paar ist symmetrisch, der Orb sitzt ohne
     Gegengewicht-Kniff mittig. Karten stapeln hier einspaltig, volle Breite. */
  #leftbar { width:340px; flex-shrink:0; padding:24px 0 18px 24px;
             display:flex; flex-direction:column; }
  #leftbar .cards { flex-direction:column; align-items:stretch; width:auto; margin-bottom:14px; }
  #leftbar .card { flex:0 1 auto; }
  /* Drei Spalten nur, wo Platz ist (340 + 980 + 340 + Raender ~1780). Darunter
     stapeln sich beide Seitenspalten unter den Inhalt (flex-wrap). */
  @media (max-width:1780px) {
    /* Zu schmal fuer drei Spalten -> saubere vertikale Stapelung: Orb + Chat
       zuerst (main order:-1), darunter die linke, dann die rechte Spalte.
       main gibt die 100vh-Bindung auf, sonst schoebe es den Rest unter die
       Falz. */
    #center { flex-direction:column; align-items:stretch; }
    main { order:-1; height:auto; max-width:none; flex-basis:auto; }
    #leftbar, #rightbar { width:auto; padding:0 24px 18px; }
    #leftbar .cards { flex-direction:row; flex-wrap:wrap; }
    #leftbar .card { flex:0 1 250px; }
    #rightbar #flow { position:static; }
  }
  /* PO-Befund 2026-07-10 ("nicht zentriert"): das Paar Inhalt+Spalte wird
     zentriert, dadurch steht der Orb um die halbe Spaltenbreite links der
     Fenstermitte. Auf breiten Fenstern bekommt der Inhalt ein Gegengewicht
     in Spaltenbreite (340px) - der Orb sitzt dann EXAKT in der Mitte.
     Zwischen 1360 und 1680px bleibt das Paar-Zentrieren (kein Platz fuers
     Gegengewicht ohne Ueberlappung). */
  /* Kein Gegengewicht-Kniff mehr (fruehere margin-left/1100er-Verbreiterung):
     mit gleich breiter linker + rechter Spalte ist das Paar symmetrisch und
     der Orb sitzt von selbst mittig. Der Inhalt bleibt bei 980; die gewonnene
     Flaeche geht in die HOEHE des Gespraechs (Karten/Lage sind jetzt links). */
  /* Niedrige Fenster (PO-Reibung "scrollen"): Hero kompaktieren, damit
     Karten + Gespraech + Eingabe ohne Seiten-Scroll sichtbar bleiben. */
  @media (max-height:1120px) {
    .orb { width:140px; height:140px; }
    .orb .a2 { inset:14px; }
    .orb .halo { inset:33px; }
    .orb .core { width:60px; height:60px; }
    .orb .mk2 { inset:-10px; }
    .hero { gap:5px; margin-bottom:8px; }
    .hello .name { font-size:34px; }
    .hello .small { font-size:12px; letter-spacing:3px; }
    .hello .sub { margin-top:4px; font-size:13.5px; }
    #state { font-size:11px; }
    .cards { margin-bottom:10px; gap:10px; }
    main { padding-top:10px; padding-bottom:12px; }
    header { margin-bottom:6px; }
    .panel { padding:12px 16px; }
    .card { padding:12px; }
    .card .ic { width:32px; height:32px; font-size:15px; margin-bottom:8px; }
    .chatbox { min-height:140px; }
    #news { margin-bottom:10px !important; }
    #news-items { font-size:12.5px !important; line-height:1.6 !important; }
    #voicebar { padding:8px 18px; margin-top:10px; }
    .qc-row { margin-bottom:8px; }
    footer { padding:8px 4px 2px; font-size:10.5px; gap:14px; }
  }
  /* Sprech-Impulse (PO-Wunsch: "lebendiger"): beim Sprechen pulsiert eine
     Welle aus dem Halo - reine Optik, gekoppelt an den ECHTEN spricht-
     Zustand aus dem Event-Strom. */
  .orb.spricht .halo { animation:impulse 0.9s ease-out infinite; }
  @keyframes impulse { 0% { transform:scale(.85); opacity:.95; } 100% { transform:scale(1.45); opacity:0; } }
  .orb.hoert .halo { animation:impulse 2.2s ease-out infinite; }
  /* Orb Mark II (UI-Kampagne Scheibe 3, PO-Wunsch "Film-HUD"): Tick-Ringe,
     Segment-Bogen und Skalen-Band als SVG um den Orb - reine Optik, aber
     Farbe (--core) und Tempo (--spin1/2) haengen an den ECHTEN Zustaenden
     aus dem Event-Strom. Kein Video-Loop, keine simulierten Werte. */
  .orb .mk2 { position:absolute; inset:-14px; color:var(--core); pointer-events:none; }
  .orb .mk2 g { transform-origin:50% 50%; transform-box:view-box; }
  .orb .mk2 .r1 { animation:spin var(--spin1, 9s) linear infinite; }
  .orb .mk2 .r2 { animation:spin var(--spin2, 6s) linear infinite reverse; }
  .orb .mk2 .r3 { animation:spin calc(var(--spin1, 9s) * 1.8) linear infinite reverse; }
  @keyframes spin { to { transform:rotate(360deg); } }
  @keyframes breathe { 0%,100% { transform:scale(1); opacity:1; } 50% { transform:scale(1.08); opacity:.86; } }
</style>
</head>
<body>
<div id="center">
<aside id="leftbar">
  <div class="cards" id="cards"></div>
  <div id="news" class="panel" style="display:none;">
    <div id="news-head" class="panel-head">DIE LAGE</div>
    <div id="news-items" style="font-size:13px; font-weight:400; color:rgba(205,228,242,0.88); line-height:1.5; display:flex; flex-direction:column; gap:8px;"></div>
  </div>
</aside>
<main>
  <header>
    <span class="side" id="clock">–</span>
    <span class="logo">J A R V I S</span>
    <span class="side"><span id="online" style="letter-spacing:1px; color:#5ce6a8;">● ONLINE</span> · <span id="version">lokal</span>
      <button id="fs" class="fs-btn" title="Vollbild an/aus (auch F11)">⛶</button></span>
  </header>
  <div class="hero">
    <div class="orb" id="orb">
      <svg class="mk2" viewBox="0 0 208 208" aria-hidden="true">
        <g class="r1">
          <circle cx="104" cy="104" r="98" fill="none" stroke="currentColor" stroke-opacity=".26" stroke-width="5" stroke-dasharray="1.5 8.76"/>
          <circle cx="104" cy="104" r="98" fill="none" stroke="currentColor" stroke-opacity=".55" stroke-width="7" stroke-dasharray="2.6 48.71"/>
        </g>
        <g class="r2">
          <circle cx="104" cy="104" r="88" fill="none" stroke="currentColor" stroke-opacity=".4" stroke-width="1.5" stroke-dasharray="122 62.31"/>
        </g>
        <g class="r3">
          <circle cx="104" cy="104" r="80" fill="none" stroke="currentColor" stroke-opacity=".14" stroke-width="4" stroke-dasharray="7.5 5.07"/>
        </g>
      </svg>
      <div class="a1"></div><div class="a2"></div><div class="halo"></div><div class="core"></div>
    </div>
    <div id="state">VERBINDE …</div>
    <div class="hello">
      <div class="small" id="greet">Guten Tag,</div>
      <div class="name" id="name">Sir.</div>
      <div class="sub" id="sub">Ich sehe nach, was heute wichtig ist …</div>
    </div>
  </div>
  <nav class="viewnav">
    <button class="vn active" data-view="today">HEUTE</button>
    <button class="vn" data-view="memory">GEDÄCHTNIS</button>
  </nav>
  <div id="view-memory" class="panel" style="display:none; margin-bottom:14px;">
    <div class="panel-head">GEDÄCHTNIS <span>JEDER PUNKT ECHT · ✕ = SOFORT WEG</span></div>
    <div id="mem-body"></div>
  </div>
  <div class="chatbox panel" id="chat">
    <div class="panel-head">GESPRÄCH</div>
    <div id="log"></div>
  </div>
  <!-- Quick Commands (Scheibe 1): jeder Button schickt einen ECHTEN Intent
       ueber den Browser-Kanal - das Kulissen-Tabu galt nur Attrappen. -->
  <div class="qc-row" id="quick">
    <button class="qc" data-cmd="Wie ist die Lage?">◆ Die Lage</button>
    <button class="qc" data-cmd="Wie wird das Wetter heute?">☀ Wetter</button>
    <button class="qc" data-cmd="Was steht an?">☰ Was steht an</button>
    <button class="qc" data-cmd="Wie ist der Systemstatus?">⚙ System</button>
  </div>
  <div class="inputrow">
    <input id="msg" placeholder="Womit soll ich anfangen?" autocomplete="off">
    <button id="send">Senden</button>
  </div>
  <div id="voicebar" class="vb-aus">
    <div class="vb-eq" id="vb-left"></div>
    <div class="vb-label" id="vb-label">VERBINDE …</div>
    <div class="vb-eq" id="vb-right"></div>
  </div>
  <footer id="foot"><span>lade Status …</span></footer>
</main>
<aside id="rightbar">
  <div id="agent" class="panel" style="display:none; margin-bottom:12px;">
    <div class="panel-head">AGENT <span id="agent-state">RUHT</span></div>
    <div id="agent-body" style="font-size:12.5px; font-weight:400; color:rgba(200,225,238,0.85);
         line-height:1.8; font-variant-numeric:tabular-nums;"></div>
    <div id="agent-redirect" style="display:none; margin-top:10px; gap:6px;">
      <input id="agent-redirect-input" type="text" autocomplete="off"
             placeholder="mach's anders …" maxlength="800" />
      <button id="agent-redirect-send" title="dem Agenten mitten im Lauf zurufen">↳ sagen</button>
    </div>
    <button id="agent-stop" style="display:none;">■ Stopp</button>
  </div>
  <div id="llm" class="panel" style="display:none; margin-bottom:12px;">
    <div class="panel-head">BESETZUNG <span style="letter-spacing:1px;">AUS CONFIG</span></div>
    <div id="llm-items"></div>
  </div>
  <div id="flow" class="panel" style="display:none;">
    <div class="panel-head">LIVE-ABLAUF</div>
    <div id="flow-items" style="font-size:12.5px; font-weight:400; color:rgba(200,225,238,0.8); line-height:1.75; font-variant-numeric:tabular-nums;"></div>
  </div>
</aside>
</div>
<script>
const API = 'http://127.0.0.1:{{API_PORT}}';
const $ = id => document.getElementById(id);

// Zustandsfarben bewusst weit auseinander (PO-Wunsch 2026-07-10):
// ruhen=tuerkis, zuhoeren=gruen, arbeiten=blau, sprechen=violett,
// warten=gelb, aus=grau - auf einen Blick unterscheidbar.
const STATES = {
  bereit:   { label:'BEREIT',           c:'#38c6f4', speed:2.6 },
  hoert:    { label:'HÖRT ZU',          c:'#5ce6a8', speed:1.1 },
  arbeitet: { label:'ARBEITET',         c:'#6f9dff', speed:0.55 },
  spricht:  { label:'SPRICHT',          c:'#c9a5ff', speed:0.3 },
  wartet:   { label:'WARTET AUF DICH',  c:'#f2cf6b', speed:1.2 },
  aus:      { label:'AUSSER DIENST',    c:'#8494a5', speed:5.0 },
};
// Laufende Hintergrund-Delegationen (aus ECHTEN timeline-Events gezaehlt):
// solange eine arbeitet, zeigt "bereit" ehrlich ARBEITET - staerkere
// Zustaende (hoert/spricht/wartet) uebersteuern weiter (PO-Befund
// 2026-07-10: "am Orb sieht man nichts", waehrend der Agent baute).
let activeDelegations = 0;
let orbState = 'bereit';
function setOrb(key) {
  orbState = STATES[key] ? key : 'bereit';
  renderOrb();
}
function renderOrb() {
  let key = orbState;
  if (key === 'bereit' && activeDelegations > 0) key = 'arbeitet';
  const s = STATES[key] || STATES.bereit;
  const orb = $('orb');
  // Zustands-Klasse fuer die Sprech-/Hoer-Impulse (reine Optik am Halo).
  orb.className = 'orb ' + key;
  orb.style.setProperty('--glow', s.c + 'e0');
  orb.style.setProperty('--glow-soft', s.c + '80');
  orb.style.setProperty('--halo', s.c + '38');
  orb.style.setProperty('--core', s.c);
  orb.style.setProperty('--core-deep', s.c + '99');
  orb.style.setProperty('--shadow1', s.c + 'bb');
  orb.style.setProperty('--shadow2', s.c + '55');
  orb.style.setProperty('--breathe', s.speed + 's');
  orb.style.setProperty('--spin1', (s.speed * 3.5) + 's');
  orb.style.setProperty('--spin2', (s.speed * 2.3) + 's');
  $('state').textContent = s.label;
  $('state').style.color = s.c;
  $('state').style.textShadow = '0 0 12px ' + s.c + '99';
  // Sprech-Leiste folgt demselben effektiven Zustand wie der Orb.
  $('voicebar').className = 'vb-' + key;
  $('vb-label').textContent = VB_LABELS[key] || VB_LABELS.bereit;
  // Aktiv-Glow GESPRÄCH: gelb, solange eine Bestaetigung wirklich offen ist.
  $('chat').classList.toggle('glow-wait', key === 'wartet');
  updateSub();
}

// Live-Zeile unterm Namen (PO 2026-07-10): zeigt die ECHTE aktuelle
// Taetigkeit (Delegation mit Dauer, aktueller Schritt, Warten, Sprechen);
// bei BEREIT kehrt die Tages-Zeile zurueck. Nichts davon ist simuliert -
// dieselben Quellen wie Orb, Sprech-Leiste und Timeline.
let daySub = '';
let currentStepLabel = '';
function updateSub() {
  const el = $('sub');
  let live = '';
  if (agentLive) {
    live = 'Ich arbeite gerade: ' + agentLive.name + ' — läuft ' + fmtDur(Date.now() - agentLive.startedMs) + '.';
  } else if (orbState === 'wartet') {
    live = 'Ich warte auf deine Bestätigung.';
  } else if (orbState === 'arbeitet') {
    live = currentStepLabel ? 'Ich arbeite gerade: ' + currentStepLabel + ' …' : 'Ich arbeite gerade …';
  } else if (orbState === 'spricht') {
    live = 'Ich spreche …';
  } else if (orbState === 'hoert') {
    live = 'Ich höre zu …';
  }
  if (live) {
    el.textContent = live;
    el.classList.add('sub-live');
  } else {
    el.innerHTML = daySub || el.innerHTML;
    el.classList.remove('sub-live');
  }
}

const VB_LABELS = {
  bereit:   '»HEY JARVIS« · STRG+ALT+J · ODER TIPPEN',
  hoert:    'ICH HÖRE ZU …',
  arbeitet: 'ICH ARBEITE …',
  spricht:  'ICH SPRECHE',
  wartet:   'WARTE AUF DEINE BESTÄTIGUNG',
  aus:      'AUSSER DIENST',
};
// Equalizer-Striche: je Seite 30 feine Striche mit zufaelligem Takt (nur
// Deko - sie LAUFEN ausschliesslich, wenn der echte Zustand hoert/spricht ist).
for (const side of ['vb-left', 'vb-right']) {
  const box = $(side);
  for (let i = 0; i < 30; i++) {
    const bar = document.createElement('span');
    bar.style.animationDelay = (-Math.random() * 1.2).toFixed(2) + 's';
    bar.style.animationDuration = (0.7 + Math.random() * 0.9).toFixed(2) + 's';
    box.appendChild(bar);
  }
}

function nowHM() {
  const t = new Date();
  return String(t.getHours()).padStart(2, '0') + ':' + String(t.getMinutes()).padStart(2, '0');
}
function stampEl(hhmm) {
  const s = document.createElement('span');
  s.className = 'ts';
  s.textContent = hhmm;
  return s;
}
function addLine(cls, text) {
  const div = document.createElement('div');
  div.className = cls;
  div.textContent = text;
  if (cls === 'me' || cls === 'jarvis') div.appendChild(stampEl(nowHM()));  // Uhrzeit
  $('log').appendChild(div);
  $('log').scrollTop = $('log').scrollHeight;
  // Aktiv-Glow: neue Jarvis-Zeile laesst das Gespraechs-Panel kurz aufblitzen
  // (Klasse neu ansetzen, damit die Animation auch bei Folge-Antworten laeuft).
  if (cls === 'jarvis' || cls === 'confirm') {
    const chat = $('chat');
    chat.classList.remove('glow-flash');
    void chat.offsetWidth;
    chat.classList.add('glow-flash');
  }
}

let liveOnline = false;
function setOnline(on) {
  liveOnline = on;
  $('online').textContent = on ? '● ONLINE' : '● OFFLINE';
  $('online').style.color = on ? '#5ce6a8' : '#8494a5';
  $('msg').disabled = !on;
  $('send').disabled = !on;
  // Quick Commands haengen am selben Live-Kanal wie die Eingabe.
  document.querySelectorAll('.qc').forEach(b => { b.disabled = !on; });
  $('msg').placeholder = on ? 'Womit soll ich anfangen?'
                            : 'Jarvis ist außer Dienst — Zahlen unten bleiben aktuell.';
  if (!on) setOrb('aus');
}

const events = new EventSource(API + '/events');
events.onopen = () => setOnline(true);
events.onerror = () => setOnline(false);
events.onmessage = e => {
  const ev = JSON.parse(e.data);
  if (ev.type === 'state') setOrb(ev.value);
  if (ev.type === 'reply') {
    addLine('jarvis', ev.text.replace(/^✓\\s*/, ''));
    // Antworten aendern oft Daten (Eintrag geloescht, Liste ergaenzt ...) -
    // sofort frisch ziehen statt auf den 10s-Poll zu warten (PO-Reibung
    // 2026-07-10: geloeschte Karte blieb bis zum manuellen Reload stehen).
    setTimeout(poll, 500);
  }
  if (ev.type === 'confirm') addLine('confirm', ev.text);
  if (ev.type === 'voice') addLine('me', '🎤 ' + ev.text);
  if (ev.type === 'timeline') addFlow(ev);
  // Durchsicht (ADR-056): die einzelnen Schritte des Agenten, live.
  if (ev.type === 'agent') addAgentStep(ev);
};

// Durchsicht (ADR-056 Scheibe 1): jeder Agenten-Schritt als eingerueckte
// Zeile im Live-Ablauf - du siehst den Agenten arbeiten statt einer Kiste.
// flowLine nutzt textContent -> kein HTML, sicher ohne Escaping.
function addAgentStep(ev) {
  let icon = '·', text = '';
  if (ev.kind === 'start') { icon = '⟐'; text = 'Agent gestartet'; }
  else if (ev.kind === 'done') { icon = ev.label === 'fertig' ? '✓' : '✗'; text = 'Agent ' + (ev.label || ''); }
  else if (ev.kind === 'tool') { icon = '→'; text = (ev.label || 'Werkzeug') + (ev.detail ? ' ' + ev.detail : ''); }
  else if (ev.kind === 'text') { icon = '·'; text = 'überlegt: ' + (ev.detail || ''); }
  else if (ev.kind === 'redirect') { icon = '↳'; text = 'du: ' + (ev.detail || ''); }
  else { text = ev.label || ev.detail || ''; }
  const cls = ev.kind === 'done' ? (ev.label === 'fertig' ? '' : 'flow-fail')
            : (ev.kind === 'redirect' ? 'flow-redirect' : 'flow-work');
  flowLine('    ' + icon + ' ' + text, cls);
}

// Live-Ablauf (UI-Zielbild 2026-07-10): jede Zeile ist eine ECHTE
// Pipeline-Station. Schritte sind ECHTE Zustandszeilen: ○ offen ->
// ⏳ in Arbeit -> ✓/✗ - aktualisiert in place, zugeordnet ueber die
// job-Nummer der Runtime (Delegations-Haken kommen Minuten spaeter).
const FLOW_MAX = 14;
const flowJobs = {};

// Klartext statt Maschinen-Namen (PO-Reibung 2026-07-10 "Der Live-Ablauf
// klingt viel zu maschinell"): jeder Intent bekommt eine menschliche
// Beschriftung. Unbekannte Intents zeigen ehrlich den Rohnamen - lieber
// technisch als falsch geraten.
const INTENT_LABELS = {
  chat: 'Antwort formulieren',
  add_entry: 'Notiz anlegen',
  list_entries: 'Einträge nachsehen',
  delete_entry: 'Eintrag streichen',
  remember_fact: 'Fakt merken',
  forget_fact: 'Fakt vergessen',
  list_facts: 'Gedächtnis zeigen',
  get_news: 'Nachrichtenlage holen',
  get_weather: 'Wetter nachsehen',
  search_web: 'Websuche',
  check_mail: 'Post durchsehen',
  show_mail_advertising: 'Werbepost zeigen',
  mail_hide_sender: 'Absender stummschalten',
  mail_keep_sender: 'Absender behalten',
  read_excel: 'Excel-Datei lesen',
  system_status: 'Systemstatus prüfen',
  analyze_pc: 'PC analysieren',
  analyze_event_log: 'Ereignisprotokoll prüfen',
  analyze_temp_files: 'Temp-Dateien sichten',
  clean_temp_files: 'Temp-Dateien aufräumen',
  install_program: 'Programm installieren',
  open_program: 'Programm öffnen',
  enable_autostart_entry: 'Autostart einschalten',
  disable_autostart_entry: 'Autostart ausschalten',
  enable_jarvis_autostart: 'Jarvis-Autostart einschalten',
  disable_jarvis_autostart: 'Jarvis-Autostart ausschalten',
  shutdown_pc: 'PC herunterfahren',
  stop_runtime: 'Jarvis beenden',
  restart_runtime: 'Jarvis neu starten',
  start_project: 'Projekt anlegen',
  plan_next_step: 'Nächsten Schritt planen',
  delegate_analysis: 'Repo-Analyse',
  delegate_work: 'Schreib-Auftrag',
  project_continue: 'Weiterarbeit',
};
function intentLabel(intent) { return INTENT_LABELS[intent] || intent; }
// Die plan-Events liefern vorformatierte "intent (ziel)"-Strings - fuer die
// Anzeige in Klartext zurueckuebersetzen.
function planLabel(s) {
  const m = String(s).match(/^(\\S+)(?:\\s+\\((.+)\\))?$/);
  if (!m) return s;
  return intentLabel(m[1]) + (m[2] ? ' · ' + m[2] : '');
}

// Active-Agents-Kachel (UI-Kampagne Scheibe 2): gespeist aus ECHTEN
// timeline-Events (Delegations-Start/-Abschluss dieser Sitzung) plus dem
// juengsten abgeschlossenen Lauf aus den Runtime-Logs (/api/status).
// Die Dauer der Live-Beobachtung wird clientseitig gemessen - ehrlich als
// Beobachtung, nicht als Behauptung ueber den Agenten-Prozess.
let agentLive = null;        // { name, startedMs } waehrend ein Agent laeuft
let agentSessionLast = null; // letzte in DIESER Sitzung beobachtete Delegation
let agentStatusLast = null;  // juengster Lauf aus den Logs (Poll)
function fmtDur(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return s >= 60 ? Math.floor(s / 60) + 'm ' + String(s % 60).padStart(2, '0') + 's' : s + 's';
}
function renderAgent() {
  const panel = $('agent');
  if (agentLive) {
    panel.style.display = 'block';
    panel.classList.add('glow-work');  // Aktiv-Glow: der Agent arbeitet JETZT
    $('agent-state').textContent = 'ARBEITET';
    $('agent-state').style.color = '#6f9dff';
    $('agent-body').textContent = agentLive.name + ' — läuft ' + fmtDur(Date.now() - agentLive.startedMs);
    const stop = $('agent-stop');       // Stopp-Knopf nur, waehrend er laeuft
    stop.style.display = 'block'; stop.disabled = false; stop.textContent = '■ Stopp';
    $('agent-redirect').style.display = 'flex';  // Umlenken nur, waehrend er laeuft
    return;
  }
  panel.classList.remove('glow-work');
  $('agent-stop').style.display = 'none';
  $('agent-redirect').style.display = 'none';
  const last = agentSessionLast || agentStatusLast;
  if (!last) return;  // noch nie ein Agent gelaufen -> keine leere Kachel
  panel.style.display = 'block';
  $('agent-state').textContent = 'RUHT';
  $('agent-state').style.color = 'rgba(150,185,205,0.6)';
  $('agent-body').textContent = last;
}
function flowName(ev) { return intentLabel(ev.intent) + (ev.target ? ' · ' + ev.target : ''); }
function flowLine(text, cls) {
  $('flow').style.display = 'block';
  const t = new Date();
  const hh = n => String(n).padStart(2, '0');
  const div = document.createElement('div');
  div.textContent = hh(t.getHours()) + ':' + hh(t.getMinutes()) + ':' + hh(t.getSeconds()) + '  ' + text;
  if (cls) div.className = cls;
  const box = $('flow-items');
  box.appendChild(div);
  while (box.children.length > FLOW_MAX) box.removeChild(box.firstChild);
  return div;
}
function flowUpdate(el, text, cls) {
  const stamp = el.textContent.slice(0, 8);  // Uhrzeit der Zeile behalten
  el.textContent = stamp + '  ' + text;
  el.className = cls || '';
}
function flowStep(job, index) {
  const j = flowJobs[job];
  return j && j.steps ? j.steps[index] : undefined;
}
function addFlow(ev) {
  if (ev.stage === 'plan') {
    const what = (ev.intents || []).map(planLabel).join(', ') || '?';
    const conf = (ev.confidence === null || ev.confidence === undefined)
      ? '' : ' · ' + Math.round(ev.confidence * 100) + ' % sicher';
    flowLine('◆ Verstanden: ' + what + conf + ' · ' + ev.seconds + 's');
    flowJobs[ev.job] = { steps: {} };
    // Mehrschritt-Plan: alle Schritte sofort als offene Liste zeigen.
    if ((ev.intents || []).length > 1) {
      ev.intents.forEach((name, i) => {
        flowJobs[ev.job].steps[i] = flowLine('○ ' + planLabel(name), 'flow-pend');
      });
    }
  } else if (ev.stage === 'schritt_start' || ev.stage === 'delegation') {
    if (ev.stage === 'schritt_start') { currentStepLabel = flowName(ev); updateSub(); }
    const prefix = ev.stage === 'delegation' ? '⚙ ' : '⏳ ';
    const label = prefix + flowName(ev) + ' — arbeitet …';
    const el = flowStep(ev.job, ev.index || 0);
    if (el) flowUpdate(el, label, 'flow-work');
    else {
      if (!flowJobs[ev.job]) flowJobs[ev.job] = { steps: {} };
      flowJobs[ev.job].steps[ev.index || 0] = flowLine(label, 'flow-work');
    }
    if (ev.stage === 'delegation') {
      flowJobs[ev.job].delegation = true;
      activeDelegations += 1;
      renderOrb();
      agentLive = { name: flowName(ev), startedMs: Date.now() };
      renderAgent();
      updateSub();
    }
  } else if (ev.stage === 'schritt') {
    currentStepLabel = '';
    updateSub();
    const label = (ev.ok ? '✓ ' : '✗ ') + flowName(ev);
    const cls = ev.ok ? '' : 'flow-fail';
    const el = flowStep(ev.job, ev.index || 0);
    if (el) flowUpdate(el, label, cls);
    else flowLine(label, cls);
    const j = flowJobs[ev.job];
    if (j && j.delegation && (ev.index || 0) === 0) {
      j.delegation = false;
      activeDelegations = Math.max(0, activeDelegations - 1);
      renderOrb();
      if (agentLive) {
        agentSessionLast = 'zuletzt: ' + flowName(ev) + ' · ' + (ev.ok ? '✓' : '✗')
          + ' · ' + fmtDur(Date.now() - agentLive.startedMs) + ' (live beobachtet)';
        agentLive = null;
      }
      renderAgent();
      updateSub();
    }
  } else if (ev.stage === 'antwort') {
    flowLine('◇ Antwort fertig · ' + ev.seconds + 's gesamt');
  } else {
    flowLine(ev.stage);
  }
  // Aktiv-Glow LIVE-ABLAUF: leuchtet, solange mindestens eine Zeile wirklich
  // arbeitet - direkt aus dem DOM abgeleitet (flow-work wird in place
  // gesetzt/entfernt), kein Zaehler, der driften kann.
  $('flow').classList.toggle('glow-work', !!document.querySelector('#flow-items .flow-work'));
}

async function sendText(text) {
  if (!text || !liveOnline) return;
  addLine('me', text);
  try {
    await fetch(API + '/message', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ text })
    });
  } catch (err) {
    addLine('confirm', 'Nachricht kam nicht durch — ist Jarvis im Dienst?');
  }
}
function send() {
  const text = $('msg').value.trim();
  $('msg').value = '';
  sendText(text);
}
$('send').onclick = send;
$('msg').addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
// Quick Commands (Scheibe 1): identischer Weg wie getippter Text - der
// Planner entscheidet, der Button ist nur eine Abkuerzung fuers Tippen.
document.querySelectorAll('.qc').forEach(b => {
  b.onclick = () => sendText(b.dataset.cmd);
});
// Vollbild-Umschalter (PO-Wunsch 2026-07-10): Fullscreen-API mit Geste.
$('fs').onclick = () => {
  if (document.fullscreenElement) document.exitFullscreen();
  else document.documentElement.requestFullscreen().catch(() => {});
};
// Stopp-Knopf (ADR-056 Scheibe 2): bricht den laufenden Agenten ab. Der
// Abschluss-Haken der Delegation raeumt agentLive auf und blendet den Knopf
// wieder aus - deshalb hier nur senden + „stoppe …" anzeigen.
$('agent-stop').onclick = async () => {
  const btn = $('agent-stop');
  btn.disabled = true; btn.textContent = '■ stoppe …';
  try {
    await fetch(API + '/agent/stop', { method:'POST',
      headers:{'Content-Type':'application/json'}, body:'{}' });
  } catch (e) { btn.disabled = false; btn.textContent = '■ Stopp'; }
};

// Umlenken (ADR-056 Scheibe 3): dem laufenden Agenten mitten im Lauf eine
// Kurskorrektur zurufen. Kein Chat-Echo - die Durchsicht zeigt sie als
// "↳ du: …"-Zeile, sobald das Backend sie dem Agenten untergeschoben hat.
async function sendRedirect() {
  const input = $('agent-redirect-input');
  const btn = $('agent-redirect-send');
  const text = input.value.trim();
  if (!text) return;
  btn.disabled = true; input.disabled = true;
  try {
    await fetch(API + '/agent/redirect', { method:'POST',
      headers:{'Content-Type':'application/json'}, body: JSON.stringify({ text }) });
    input.value = '';
  } catch (e) { /* still: der Agent laeuft weiter, erneut versuchen moeglich */ }
  btn.disabled = false; input.disabled = false; input.focus();
}
$('agent-redirect-send').onclick = sendRedirect;
$('agent-redirect-input').addEventListener('keydown', e => { if (e.key === 'Enter') sendRedirect(); });

function card(icon, title, detail, source, accent, delText, impulseKey, proposalFile) {
  // delText (PO-Reibung 2026-07-10 "einfach zu entfernen"): Eintrags-Karten
  // bekommen ein ✕, das den ECHTEN Loesch-Befehl ueber den Chat schickt.
  // impulseKey (ADR-054): Impuls-Karten tragen ein ✕, das den Impuls
  // wegklickt (data-impulse statt data-del - anderer stiller Endpunkt).
  // proposalFile (PO-Reibung 2026-07-11): die Vorschlags-Karte bekommt ein ✕,
  // das den Vorschlag auf "verworfen" setzt - sonst haengt er ewig.
  const esc = t => String(t).replace(/</g, '&lt;').replace(/"/g, '&quot;');
  let del = '';
  if (impulseKey) {
    del = `<button class="card-x" data-impulse="${esc(impulseKey)}" title="Impuls wegklicken">✕</button>`;
  } else if (proposalFile) {
    del = `<button class="card-x" data-proposal="${esc(proposalFile)}" title="Vorschlag verwerfen">✕</button>`;
  } else if (delText) {
    del = `<button class="card-x" data-del="${esc(delText)}" title="Eintrag löschen">✕</button>`;
  }
  return `<div class="card" style="border-color:${accent}40">${del}
    <div class="ic" style="border-color:${accent}66; background:${accent}14">${icon}</div>
    <div class="t">${title}</div><div class="d" style="color:${accent}cc">${detail}</div>
    <div class="s">${source}</div></div>`;
}
// Karten-Klicks (innerHTML wird je Poll neu gebaut, deshalb ein delegierter
// Listener). Drei Faelle:
//  - Impuls-✕ (data-impulse, ADR-054): EIN Klick, still weg (harmlos,
//    Nein-Liste faengt Wiederkehr). Keine Rueckfrage.
//  - Erinnerungs-✕ (data-del): oeffnet eine Rueckfrage auf der Karte
//    (PO-Reibung 2026-07-11: Loeschen ist irreversibel, kein Papierkorb).
//  - Ja/Abbrechen in der Rueckfrage: loeschen bzw. zuruecknehmen.
async function dismissImpulse(el, key) {
  el.style.opacity = '0.3'; el.style.pointerEvents = 'none';
  try {
    const r = await fetch(API + '/impulse/dismiss', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ key })
    });
    const data = await r.json();
    if (!data.ok) { addLine('confirm', 'Wegklicken fehlgeschlagen: ' + (data.message || 'unbekannt'));
                    el.style.opacity = ''; el.style.pointerEvents = ''; }
  } catch (err) { addLine('confirm', 'Wegklicken kam nicht durch — ist Jarvis im Dienst?');
                  el.style.opacity = ''; el.style.pointerEvents = ''; }
  poll();
}
function askDeleteEntry(el, text) {
  // Rueckfrage auf die Karte legen; poll() pausiert, bis entschieden ist.
  pendingConfirm = true;
  const q = document.createElement('div');
  q.className = 'card-confirm';
  q.innerHTML = `<div class="cc-q">Erinnerung löschen?</div>
    <div class="cc-btns"><button class="cc-yes">Ja, löschen</button>
    <button class="cc-no">Abbrechen</button></div>`;
  q.dataset.text = text;
  el.appendChild(q);
}
async function doDeleteEntry(el, text) {
  pendingConfirm = false;
  el.style.opacity = '0.3'; el.style.pointerEvents = 'none';
  try {
    const r = await fetch(API + '/entry/delete', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ text })
    });
    const data = await r.json();
    if (!data.ok) { addLine('confirm', 'Löschen fehlgeschlagen: ' + (data.message || 'unbekannt'));
                    el.style.opacity = ''; el.style.pointerEvents = ''; }
  } catch (err) { addLine('confirm', 'Löschen kam nicht durch — ist Jarvis im Dienst?');
                  el.style.opacity = ''; el.style.pointerEvents = ''; }
  poll();
}
$('cards').addEventListener('click', async e => {
  if (!liveOnline) return;
  // Antwort auf eine offene Rueckfrage?
  const yes = e.target.closest('.cc-yes');
  const no = e.target.closest('.cc-no');
  if (yes || no) {
    const conf = e.target.closest('.card-confirm');
    const el = e.target.closest('.card');
    if (yes) { doDeleteEntry(el, conf.dataset.text); }
    else { pendingConfirm = false; conf.remove(); poll(); }
    return;
  }
  const btn = e.target.closest('.card-x');
  if (!btn) return;
  const el = btn.closest('.card');
  if (btn.dataset.impulse != null) { dismissImpulse(el, btn.dataset.impulse); return; }
  if (btn.dataset.proposal != null) { dismissProposal(el, btn.dataset.proposal); return; }
  askDeleteEntry(el, btn.dataset.del);  // Erinnerung: erst fragen, dann loeschen
});

// Vorschlag verwerfen (PO-Reibung 2026-07-11): ein Klick setzt den Vorschlag
// auf "verworfen" - stiller Endpunkt, kein Chat-Echo, keine Rueckfrage (der
// Vorschlag ist harmlos und kommt als Datei nicht wieder hoch).
async function dismissProposal(el, file) {
  el.style.opacity = '0.3'; el.style.pointerEvents = 'none';
  try {
    const r = await fetch(API + '/proposal/dismiss', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ text: file })
    });
    const data = await r.json();
    if (!data.ok) { el.style.opacity = ''; el.style.pointerEvents = ''; }
  } catch (err) { el.style.opacity = ''; el.style.pointerEvents = ''; }
  poll();
}

// Lebendige Begruessung (PO 2026-07-10 "ein paar Variationen, nach seinem
// Verhalten"): Varianten-Pools wie core/phrases.py - gespeist aus ECHTEN
// Signalen (Tageszeit, laufende Delegation, heutige Anfragen-Zahl).
// Gewaehlt wird einmal je Kontext-Bucket, nicht bei jedem 10s-Poll -
// sonst flackert der Gruss.
let greetPick = '', greetBucket = '';
function greeting(s) {
  const h = new Date().getHours();
  const slot = (h >= 23 || h < 5) ? 'nacht' : h < 11 ? 'morgen' : h < 18 ? 'tag' : 'abend';
  const busy = activeDelegations > 0;
  // "Ein reger Tag heute," (Anfragen-Zahl) wieder entfernt - PO-Befund
  // 2026-07-10: neben "nur eine Sache steht an" wirkte es widerspruechlich
  // (Anfragen an Jarvis != anstehende Dinge; das versteht niemand von allein).
  const w = s.weather || {};
  // Wetter-Signale (PO 2026-07-10 "im Kontext zu Wetter/Lage"): echte
  // Open-Meteo-Werte fuellen den Pool - nie eine erfundene Stimmung.
  const hot = w.current != null && w.current >= 28;
  const cold = w.current != null && w.current <= 3;
  const rainy = w.rain != null && w.rain >= 60;
  const bucket = [slot, busy, hot, cold, rainy].join('|');
  if (bucket === greetBucket && greetPick) return greetPick;
  const pool = {
    nacht:  ['Noch wach,', 'Späte Stunde,'],
    morgen: ['Guten Morgen,', 'Schönen guten Morgen,'],
    tag:    ['Guten Tag,', 'Schön, dass du da bist,'],
    abend:  ['Guten Abend,', 'Schönen Abend,'],
  }[slot].slice();
  if (busy) pool.push('Ich arbeite gerade für dich,');  // echte laufende Delegation
  if (hot) pool.push('Ein heißer Tag,');
  if (cold) pool.push('Zieh dich warm an,');
  if (rainy) pool.push('Schirm-Wetter,');
  greetBucket = bucket;
  greetPick = pool[Math.floor(Math.random() * pool.length)];
  return greetPick;
}
const escText = t => String(t || '').replace(/</g, '&lt;');
let subPick = '', subBucket = '';
function subLine(attention, s) {
  const w = (s && s.weather) || null;
  // Warmer Morgen-Satz (PO 2026-07-11: Briefing-Karte raus, dafuer EIN
  // zusammenfassender Satz im Gruss). Vormittags (5-11h): was braucht dich
  // heute + ein Wetter-Touch NUR bei attention 0 (PO-Regel: Wetter nie
  // neben Anstehendem - sonst liest es sich, als WAERE das Wetter die
  // Aufgabe). Kein News-Touch: "Die Lage" hat ihr eigenes Panel (keine
  // Doppelung). Eigener Anti-Flacker-Bucket.
  const mh = new Date().getHours();
  if (mh >= 5 && mh < 11) {
    const wx = (w && w.current != null)
      ? `, ${escText(w.condition)}${w.temp_max != null ? ' bis ' + w.temp_max + '°' : ''}`
      : '';
    const mBucket = 'm|' + [attention, w ? w.temp_max : '', w ? w.condition : ''].join('|');
    if (mBucket === subBucket && subPick) return subPick;
    subBucket = mBucket;
    let mp;
    if (attention === 0) mp = [
      `Ein ruhiger Morgen: nichts Dringendes${wx}.`,
      `Nichts drängt heute${wx} — ein guter Start.`,
      `Der Tag gehört dir${wx}.`,
    ];
    else if (attention === 1) mp = [
      'Ein guter Morgen — <b>eine Sache</b> steht heute an.',
      'Heute braucht dich nur <b>eine Sache</b>.',
    ];
    else {
      const mw = ['', '', 'zwei Dinge', 'drei Dinge', 'vier Dinge'];
      const mn = `<b>${mw[Math.min(attention, 4)] || attention + ' Dinge'}</b>`;
      mp = [`Guten Morgen — heute stehen ${mn} an.`, `Heute warten ${mn} auf dich.`];
    }
    subPick = mp[Math.floor(Math.random() * mp.length)];
    return subPick;
  }
  const head = (s && s.news && s.news.items && s.news.items[0]) || '';
  const headShort = head.length > 64 ? head.slice(0, 64).replace(/\\s+\\S*$/, '') + ' …' : head;
  const last = (s && s.delegations && s.delegations.last) || null;
  const bucket = [attention, w ? w.current : '', headShort.slice(0, 24), last ? last.repo : ''].join('|');
  if (bucket === subBucket && subPick) return subPick;
  const words = ['nichts', 'eine Sache', 'zwei Dinge', 'drei Dinge', 'vier Dinge'];
  const n = `<b>${words[Math.min(attention, 4)]}</b>`;
  const pool = attention === 0
    ? ['Heute ist nichts dringend. Genieß den Tag.',
       'Nichts ist fällig — der Tag gehört dir.',
       'Alles im grünen Bereich, nichts drängt.']
    : attention === 1
      ? ['Heute ist nur <b>eine Sache</b> wichtig.',
         'Nur <b>eine Sache</b> steht heute an.',
         'Eine <b>einzige Sache</b> braucht dich heute.']
      : [`Heute sind nur ${n} wichtig.`, `${n} stehen heute an.`];
  // Kontext-Fassungen (PO-Wunsch: Weltlage/Wetter/unsere Arbeit) - jede
  // Angabe stammt aus derselben echten Quelle wie die Karte darunter.
  // Wetter-Fassung NUR wenn nichts ansteht (PO-Befund 2026-07-10, 2. Anlauf:
  // "Eine Sache steht an — draußen 25°" las sich, als WAERE das Wetter die
  // Sache. Anstehendes ist abarbeitbar, Wetter ist Kulisse - die beiden
  // gehoeren nie in einen Satz).
  if (w && w.current != null && attention === 0) {
    pool.push(`Draußen ${w.current}° und ${escText(w.condition)} — hier ist nichts fällig.`);
  }
  if (headShort && attention === 0) {
    pool.push(`Nichts ist fällig. Die Welt beschäftigt: „${escText(headShort)}"`);
  }
  if (last && last.ok && attention === 0) {
    pool.push(last.kind === 'arbeit'
      ? `Nichts drängt — zuletzt habe ich in „${escText(last.repo)}" gebaut.`
      : `Nichts drängt — zuletzt habe ich „${escText(last.repo)}" analysiert.`);
  }
  subBucket = bucket;
  subPick = pool[Math.floor(Math.random() * pool.length)];
  return subPick;
}

// Verlauf beim Laden (einmalig): die letzten Zeilen der ECHTEN, bereits
// redigierten History aller Kanaele - nach F5 weiss man wieder, was war.
let historyLoaded = false;
function renderHistory(items) {
  if (historyLoaded) return;
  historyLoaded = true;
  if (!items || !items.length || $('log').children.length > 0) return;
  for (const h of items) {
    const div = document.createElement('div');
    div.className = (h.role === 'user' ? 'me' : 'jarvis') + ' old';
    div.textContent = h.content;
    if (h.time) div.appendChild(stampEl(h.time));  // gespeicherte Uhrzeit, falls vorhanden
    $('log').appendChild(div);
  }
  const divider = document.createElement('div');
  divider.className = 'log-divider';
  divider.textContent = '— VORHER —';
  $('log').appendChild(divider);
  $('log').scrollTop = $('log').scrollHeight;
}

// --- Ansichten (Nachtplan Scheibe 4): HEUTE | GEDÄCHTNIS -------------------
let view = 'today';
let lastStatus = null;
// Loesch-Rueckfrage offen (PO-Reibung 2026-07-11): solange die Frage
// "Erinnerung loeschen?" auf einer Karte steht, darf der 10s-Poll die
// Karten NICHT neu bauen - sonst verschwaende die Frage vor der Antwort.
let pendingConfirm = false;
function setView(v) {
  view = v;
  document.querySelectorAll('.vn').forEach(b => b.classList.toggle('active', b.dataset.view === v));
  const today = v === 'today';
  // Karten + "Die Lage" wohnen jetzt in der linken Spalte (#leftbar) - im
  // GEDAECHTNIS-Modus die ganze Spalte ausblenden statt der Einzelbloecke.
  for (const id of ['leftbar', 'chat', 'quick']) $(id).style.display = today ? '' : 'none';
  document.querySelector('.inputrow').style.display = today ? '' : 'none';
  $('view-memory').style.display = today ? 'none' : 'block';
  if (today) { $('news').style.display = 'none'; poll(); }
  else renderMemoryView();
}
document.querySelectorAll('.vn').forEach(b => { b.onclick = () => setView(b.dataset.view); });

const escHtml = t => String(t || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
function memRow(text, meta, kind, key) {
  // kind gesetzt = loeschbar ueber den passenden stillen Endpunkt.
  // key = der ECHTE Text fuers Backend (Anzeige darf ⭐ etc. tragen).
  const x = kind
    ? `<button class="mem-x" data-kind="${kind}" data-key="${escHtml(key || text)}" title="löschen">✕</button>`
    : '';
  return `<div class="mem-row"><span class="mem-text">${escHtml(text)}</span>`
    + (meta ? `<span class="mem-meta">${escHtml(meta)}</span>` : '') + x + '</div>';
}
function renderMemoryView() {
  const s = lastStatus;
  if (!s || !s.memory_view) return;
  const mv = s.memory_view;
  const parts = [];
  parts.push(`<div class="mem-section">FAKTEN (${mv.facts.length})</div>`);
  parts.push(mv.facts.length
    ? mv.facts.map(f => memRow(f.text, f.category, 'fact')).join('')
    : '<div class="mem-row mem-old">Noch keine dauerhaften Fakten.</div>');
  parts.push(`<div class="mem-section">EINTRÄGE (${mv.entries.length})</div>`);
  parts.push(mv.entries.length
    ? mv.entries.map(e => memRow(
        (e.important ? '⭐ ' : '') + e.text,
        (e.when || 'ohne Termin') + (e.repeat ? ' ↻' : ''), 'entry', e.text)).join('')
    : '<div class="mem-row mem-old">Keine offenen Einträge.</div>');
  for (const l of (mv.lists || [])) {
    const cap = l.name.charAt(0).toUpperCase() + l.name.slice(1);
    parts.push(`<div class="mem-section">LISTE: ${escHtml(cap.toUpperCase())} (${l.items.length})</div>`);
    parts.push(l.items.map(i => memRow(i, '', '')).join(''));
  }
  if (s.history && s.history.length) {
    parts.push(`<div class="mem-section">VERLAUF (letzte ${s.history.length})</div>`);
    parts.push(s.history.map(h => `<div class="mem-row mem-old"><span class="mem-text">`
      + `<b>${h.role === 'user' ? 'Du' : 'Jarvis'}:</b> ${escHtml(h.content.slice(0, 140))}`
      + `${h.content.length > 140 ? ' …' : ''}</span></div>`).join(''));
  }
  $('mem-body').innerHTML = parts.join('');
}
// Loeschen in der Ansicht: derselbe stille Weg wie das Karten-✕.
$('view-memory').addEventListener('click', async e => {
  const btn = e.target.closest('.mem-x');
  if (!btn || !liveOnline) return;
  const row = btn.closest('.mem-row');
  row.style.opacity = '0.3';
  row.style.pointerEvents = 'none';
  const endpoint = btn.dataset.kind === 'fact' ? '/fact/forget' : '/entry/delete';
  try {
    const r = await fetch(API + endpoint, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ text: btn.dataset.key })
    });
    const data = await r.json();
    if (!data.ok) { row.style.opacity = ''; row.style.pointerEvents = ''; }
  } catch (err) {
    row.style.opacity = ''; row.style.pointerEvents = '';
  }
  poll();
});

function renderStatus(s) {
  lastStatus = s;
  // Waehrend eine Loesch-Rueckfrage offen ist, den letzten Stand merken,
  // aber NICHTS neu zeichnen - die Frage bleibt stehen, bis der Nutzer
  // entscheidet (danach holt poll() ohnehin die Wahrheit vom Server).
  if (pendingConfirm) return;
  renderHistory(s.history);
  if (view === 'memory') renderMemoryView();
  $('greet').textContent = greeting(s);
  $('name').textContent = (s.owner || 'Sir') + '.';
  if (s.project && s.project.version) {
    $('version').textContent = s.project.version.split('—')[0].trim() + ' · lokal';
  }

  const cards = [];
  // Tages-Fokus (PO-Reibung 2026-07-11): nur HEUTE Relevantes als Karte -
  // ferne Termine (18.07.) stehen im Briefing/GEDÄCHTNIS, nicht hier.
  if (s.entries && s.entries.today) {
    for (const t of s.entries.today) {
      cards.push(card('🔔', t.text, 'heute fällig · ' + t.when + ' Uhr',
        'aus deinen Erinnerungen', '#f2cf6b', t.text));
    }
  }
  if (s.entries && s.entries.due_today) {
    for (const d of s.entries.due_today) {
      // Abgelaufen klar markiert (PO-Reibung 2026-07-10): durchgestrichen
      // + gedimmt, und per ✕ mit einem Klick zu entfernen.
      cards.push(card('✔', '<s>' + d.text + '</s>', 'ABGELAUFEN — war fällig ' + d.when + ' Uhr',
        'aus deinen Erinnerungen', '#9ab8cc', d.text));
    }
  }
  if (s.entries && s.entries.undated > 0) {
    cards.push(card('☰', s.entries.undated + (s.entries.undated === 1 ? ' Merkposten offen' : ' Merkposten offen'),
      'ohne Termin', 'aus deinen Einträgen', '#9ab8cc'));
  }
  // "Wichtige Sachen" sind NUR die Eintrags-Karten bis hier - das Wetter ist
  // Service, keine Sache (PO-Widerspruchs-Befund 2026-07-10: das UI sagte
  // "eine Sache wichtig", der Chat ehrlich "keine Eintraege"; gezaehlt war
  // die Wetter-Karte).
  const attention = cards.length;
  // Die fruehere Briefing-Textkarte ist RAUS (PO-Reibung 2026-07-11: sie
  // war eine Wall of Text und wiederholte Wetter + Lage, die schon eigene
  // Kacheln/Panels haben). Das Dashboard IST das visuelle Briefing (Gruss
  // + Kacheln); der warme Morgen-Satz lebt jetzt im Untertitel (subLine).
  // Der gesprochene Briefing-Befehl bleibt voll erhalten.
  // IMPULSE (Endsystem-Kampagne, ADR-054): Jarvis hat von selbst an etwas
  // gedacht (Unwetter u. a.) - Vorschlag statt Aktion, still als Karte,
  // wegklickbar per ✕ (kommt dann nicht wieder). Ganz oben, weil ein
  // Unwetter-Hinweis das Dringendste ist; zaehlt NICHT als "wichtige Sache".
  if (s.impulses && s.impulses.length) {
    for (const im of s.impulses.slice().reverse()) {
      cards.unshift(card('⚡', escText(im.title), escText(im.detail),
        'Jarvis hat mitgedacht', '#f2b74b', null, im.key));
    }
  }
  // VORSCHLAG (Angestellten-Vision Stufe 3, PO-Go 11.07.2026): der
  // juengste OFFENE Eigenvorschlag - Vorschlag statt Aktion. Zaehlt
  // nicht als "wichtige Sache"; ohne offenen Vorschlag keine Karte.
  if (s.proposal && s.proposal.title) {
    cards.push(card('💡', 'Jarvis schlägt vor', escText(s.proposal.title)
      + (s.proposal.created ? ' · vom ' + s.proposal.created : ''),
      'Entwurf zur Freigabe — ' + escText(s.proposal.file), '#b48cf2',
      null, null, s.proposal.file));
  }
  // Benannte Listen (2026-07-10): stehende Sammlungen, zaehlen bewusst
  // NICHT als "wichtige Sachen" - sie sind da, aber sie draengen nicht.
  if (s.lists) {
    for (const l of s.lists) {
      const cap = l.name.charAt(0).toUpperCase() + l.name.slice(1);
      const preview = String(l.preview || '').replace(/</g, '&lt;')
        + (l.count > 3 ? ' …' : '');
      cards.push(card('🧾', cap.replace(/</g, '&lt;') + ' · ' + l.count + ' Posten',
        preview, 'aus deinen Listen', '#9ab8cc'));
    }
  }
  if (s.weather) {
    // Tagesverlauf (PO-Wunsch 2026-07-10): Jetzt-Wert im Titel, Bloecke als
    // Detail. Die Tages-Spanne (12-29 Grad) entfaellt, sobald es einen
    // Jetzt-Wert gibt (PO-Befund: mit Verlauf daneben ist sie doppelt) -
    // ohne Stundendaten bleibt sie der ehrliche Rueckfall.
    const w = s.weather;
    const title = w.current != null
      ? `Jetzt ${w.current}° · ${w.condition}`
      : `${w.temp_min}–${w.temp_max} °C, ${w.condition}`;
    let detail = w.place + (w.rain != null ? ` · Regen ${w.rain} %` : '');
    if (w.segments && w.segments.length) {
      detail = w.segments.map(seg =>
        seg.label.slice(0, 5) + '. ' + seg.temp + '°'
        + ((seg.rain != null && seg.rain >= 20) ? ' ☂' + seg.rain + '%' : '')
      ).join(' · ') + ' — ' + w.place;
    }
    cards.push(card('☀', title, detail, 'Open-Meteo, live', '#7fdbe6'));
  }
  $('cards').innerHTML = cards.join('');
  daySub = subLine(attention, s);
  updateSub();

  // AGENT (Scheibe 2): juengster abgeschlossener Lauf aus den Runtime-Logs -
  // Kosten sind API-GEGENWERT (Abo, Grenzkosten 0), deshalb so benannt.
  if (s.delegations && s.delegations.last) {
    const L = s.delegations.last;
    agentStatusLast = 'zuletzt: ' + (L.kind === 'arbeit' ? 'Arbeit in' : 'Analyse von') + " '"
      + L.repo + "' · " + (L.ok ? '✓' : '✗') + ' · ' + Math.round(L.dauer) + 's · $'
      + L.kosten.toFixed(2) + ' Gegenwert';
    renderAgent();
  }

  // BESETZUNG (Scheibe 1): die echte Modell-Aufstellung aus der Config -
  // kein "Connected"-Badge, denn Verbindungs-Status waere eine Behauptung.
  if (s.llm) {
    const esc = t => String(t || '—').replace(/</g, '&lt;');
    const rows = [];
    rows.push({ k:'PLANNER', v: esc(s.llm.planner.model) + ' · ' + esc(s.llm.planner.provider) });
    rows.push({ k:'ANTWORT', v: esc(s.llm.answer.model) + ' · ' + esc(s.llm.answer.provider) });
    if (s.llm.transcription && s.llm.transcription.model) {
      rows.push({ k:'GEHÖR', v: esc(s.llm.transcription.model) });
    }
    if (s.llm.tts) {
      rows.push({ k:'STIMME', v: s.llm.tts.voice
        ? esc(s.llm.tts.voice) + ' · ' + esc(s.llm.tts.model)
        : esc(s.llm.tts.backend) });
    }
    if (s.llm.agent) {
      rows.push({ k:'AGENT', v: esc(s.llm.agent.backend) + ' CLI' });
    }
    $('llm-items').innerHTML = rows.map(r =>
      `<div class="llm-row"><span class="k">${r.k}</span><span class="v">${r.v}</span></div>`).join('');
    $('llm').style.display = 'block';
  }

  if (s.news && s.news.items && s.news.items.length) {
    document.getElementById('news').style.display = 'block';
    $('news-head').textContent = 'DIE LAGE · ' + s.news.source.toUpperCase();
    $('news-items').innerHTML = s.news.items
      .map(t => '<div>◆&nbsp; ' + t.replace(/</g, '&lt;') + '</div>').join('');
  }

  const f = [];
  f.push(`<span style="color:${s.runtime.running ? '#5ce6a8' : '#8494a5'}">●</span> ${s.runtime.running ? 'IM DIENST' : 'AUSSER DIENST'}`);
  // Scheibe 7 (Nachtplan): Uptime, Sprach-Antwortzeit, KI-Verbrauch -
  // jede Zahl aus echten Log-/Lock-Quellen, fehlende Daten = keine Anzeige.
  if (s.runtime.running && s.uptime_seconds != null) {
    const h = Math.floor(s.uptime_seconds / 3600), m = Math.floor((s.uptime_seconds % 3600) / 60);
    f.push(`Uptime ${h ? h + 'h ' : ''}${m}m`);
  }
  if (s.avg_voice_seconds != null) f.push(`Ø Antwort ${String(s.avg_voice_seconds).replace('.', ',')}s (Sprache)`);
  if (s.usage && s.usage.calls > 0) {
    const kt = Math.round((s.usage.tokens_in + s.usage.tokens_out) / 1000);
    f.push(`KI heute: ${s.usage.calls} Aufrufe · ${kt}k Token`);
  }
  if (s.system) f.push(`CPU ${s.system.cpu} %`, `RAM ${s.system.ram} %`);
  if (s.memory) f.push(`${s.memory.facts} Fakten`);
  if (s.entries) f.push(`${s.entries.upcoming + s.entries.undated} Einträge offen`);
  if (s.delegations && s.delegations.runs) f.push(`Delegationen ${s.delegations.ok}/${s.delegations.runs} · Ø $${s.delegations.avg_cost_usd.toFixed(2)}`);
  if (s.activity) f.push(`${s.activity.requests} Anfragen heute`);
  $('foot').innerHTML = '<span>' + f.join('</span><span>') + '</span>'
    + '<span class="right">jede Zahl aus realen Quellen · Stand ' + s.generated_at + '</span>';
}

async function poll() {
  try {
    const r = await fetch('/api/status');
    renderStatus(await r.json());
  } catch (e) { /* Anzeige behaelt den letzten Stand */ }
}
function tick() {
  const now = new Date();
  const days = ['So','Mo','Di','Mi','Do','Fr','Sa'];
  // Sekunden sichtbar (Scheibe 1, HUD-Look): eine lebende Uhr ist ehrlich -
  // sie zeigt nur die Zeit, aber sie zeigt, dass die Seite lebt.
  $('clock').textContent = days[now.getDay()] + '., ' +
    now.toLocaleDateString('de-DE') + ' · ' +
    now.toLocaleTimeString('de-DE', { hour:'2-digit', minute:'2-digit', second:'2-digit' });
  // Dauer-Ticker der Agent-Kachel (Scheibe 2) - nur solange einer arbeitet;
  // die Live-Zeile unterm Namen tickt mit.
  if (agentLive) { renderAgent(); updateSub(); }
}
tick(); setInterval(tick, 1000);
poll(); setInterval(poll, 10000);
setOrb('aus');
</script>
</body>
</html>
"""


def _live_owner_name(fallback: str) -> str:
    """Liest owner_name FRISCH aus config.json (ADR-057). Das Dashboard laeuft
    als eigener Prozess und bindet seine Config beim Start - eine In-Memory-
    Aenderung im Runtime-Prozess (set_owner_name) erreicht es sonst nie. So
    zieht die Begruessung beim naechsten Poll (<=10 s) nach, ohne Neustart.
    Faellt bei jedem Fehler auf die gebundene Config zurueck, damit der
    Status-Endpunkt nie an einer halb geschriebenen/gesperrten Datei bricht."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:
            return str(json.load(f).get("owner_name", "")) or fallback
    except Exception:
        return fallback


def make_handler(config: Config):
    """Handler-Klasse mit gebundener Config (http.server-Muster)."""
    page = _PAGE.replace("{{API_PORT}}", str(getattr(config, "ui_port", 8766)))

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server-API
            if self.path == "/" or self.path == "/index.html":
                self._respond(200, "text/html; charset=utf-8", page.encode("utf-8"))
            elif self.path.startswith("/fonts/"):
                # Lokale Schrift-Auslieferung: Whitelist-Abgleich statt
                # Dateisystem-Zugriff mit Nutzer-Pfad (kein Traversal moeglich).
                name = self.path[len("/fonts/"):]
                font_path = _FONT_DIR / name
                if name in _FONT_FILES and font_path.is_file():
                    body = font_path.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "font/woff2")
                    self.send_header("Content-Length", str(len(body)))
                    # Fonts aendern sich praktisch nie - dem Browser einen Tag
                    # Cache goennen (spart das Neuladen bei jedem F5).
                    self.send_header("Cache-Control", "max-age=86400")
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self._respond(404, "text/plain; charset=utf-8", b"Not found")
            elif self.path == "/api/status":
                status = collect_status(
                    config.memory_dir,
                    config.log_dir,
                    _PROJECT_STATE,
                    weather_location=getattr(config, "weather_default_location", ""),
                    news_feeds=getattr(config, "news_feeds", None),
                )
                status["owner"] = _live_owner_name(getattr(config, "owner_name", ""))
                # Echte Modell-Besetzung aus der Config (Scheibe 1) - reine
                # Config-Werte, kein behaupteter Verbindungs-Status.
                status["llm"] = llm_lineup(config)
                body = json.dumps(status, ensure_ascii=False).encode("utf-8")
                self._respond(200, "application/json; charset=utf-8", body)
            else:
                self._respond(404, "text/plain; charset=utf-8", b"Not found")

        def _respond(self, code: int, content_type: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):  # leise - kein Request-Spam
            logger.debug("%s - %s", self.address_string(), fmt % args)

    return DashboardHandler


def main() -> None:
    config = Config.load()
    port = getattr(config, "dashboard_port", 8765)
    # --port <n> ueberschreibt den Config-Port - fuer eine Vorschau-Instanz
    # neben der laufenden (Entwicklungs-Ergonomie, keine Fachaenderung).
    if "--port" in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        except (ValueError, IndexError):
            print("--port braucht eine Zahl; nutze Config-Port.")
    server = ThreadingHTTPServer((_BIND_HOST, port), make_handler(config))
    url = f"http://{_BIND_HOST}:{port}/"
    print(f"Jarvis UI: {url}  (Beenden: Strg+C)")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
