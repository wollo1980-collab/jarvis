"""
Agenten-Backend-Kontrakt + erste Implementierung (Claude Code CLI).
Erster Baustein des Agenten-Arms (ADR-033 Delegationsprozess, ADR-034
read-only Repo-Analyse, Umsetzungs-Scheibe 1: lokal & synchron).

Aufbau bewusst analog core/providers.py (LLMProvider): das Protokoll
`AgentBackend` und seine erste Implementierung `ClaudeCodeBackend` liegen
in einer Datei. Ein Agent ist eine neue Tool-Klasse, kein Parallelsystem
(ADR-033) - deshalb ist der Kontrakt klein und austauschbar: Codex/GPT
folgen spaeter hinter demselben `analyze()`-Vertrag, ohne dass der
Command-Layer (commands/delegate.py) sich aendert.

Sicherheit (ADR-034 Guardrails):
- Read-only ist im Print-Modus (`claude -p`) nicht verhandelbar: nur
  `Read`/`Grep`/`Glob` werden erlaubt (`--allowedTools`). Ohne Bash/Edit/
  Write ist keinerlei git-Operation moeglich (kein Branch/Commit/Push).
- Der harte Guardrail ist der Wall-Clock-Timeout: laeuft der Subprozess
  laenger als `AgentLimits.timeout_seconds`, wird er hart gekillt
  (Kill-Switch). Ein CLI-`--max-turns`-Flag existiert in der genutzten
  `claude`-Version (2.1.201) NICHT - Turn-/Kostendeckel werden deshalb
  nicht vorab erzwungen, sondern aus dem JSON-Ergebnis (`num_turns`,
  `total_cost_usd`) nur protokolliert (Observability).
- Keine stillen Fehler: Timeout, Exit != 0, is_error und nicht parsebares
  JSON fuehren alle zu ok=False mit klarem `detail`.

Auth (ADR-034 §6): Der Subprozess erbt den vorhandenen Account-Login
(~/.claude). Dieses Backend liest selbst KEIN Secret und setzt keinen
API-Key - der spaetere dedizierte ANTHROPIC_API_KEY (Env, ADR-018) ist die
dokumentierte Robustheits-Aufwertung fuer den unbeaufsichtigten Betrieb.
"""
from __future__ import annotations

import json
import logging
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Protocol

logger = logging.getLogger("jarvis.agent_backend")

# Name des CLI-Binaries (kein Magic Value im Aufrufcode). Auf dem PATH
# erwartet; Auth traegt ueber den Account-Login (~/.claude).
CLAUDE_BINARY = "claude"

# Read-only erzwungen: ausschliesslich lesende Tools. Ohne Bash/Edit/Write
# ist keine System-/Repo-Aenderung und keine git-Operation moeglich.
READ_ONLY_TOOLS = ("Read", "Grep", "Glob")


def write_tools(repo: Path) -> tuple[str, ...]:
    """Werkzeugliste fuer den SCHREIBENDEN Kaefig (ADR-050): Edit/Write sind
    per Permission-Regel auf das Ziel-Repo begrenzt (gitignore-Syntax,
    forward slashes) - Schreiben ausserhalb wird von der CLI verweigert.
    Bewusst KEIN Bash: keine git-Operation, keine Prozessausfuehrung."""
    scope = str(repo).replace("\\", "/").rstrip("/")
    return ("Read", "Grep", "Glob", f"Edit({scope}/**)", f"Write({scope}/**)")


def _tool_input_summary(inp) -> str:
    """Kurzer, sprechender Anriss eines Werkzeug-Aufrufs fuer die Durchsicht
    (ADR-056): das aussagekraeftigste Feld (Datei/Muster/Befehl) statt des
    ganzen Input-Objekts. Fail-safe: nie werfend, immer ein String."""
    if not isinstance(inp, dict):
        return ""
    for key in ("file_path", "path", "pattern", "command", "query", "url"):
        if inp.get(key):
            return str(inp[key])[:120]
    return ", ".join(f"{k}={str(v)[:40]}" for k, v in list(inp.items())[:2])

# Poll-Intervall der Warteschleife (Sekunden): so oft werden cancel_event und
# das Gesamt-Timeout geprueft, waehrend der claude-Prozess laeuft. Klein genug
# fuer einen zuegigen Abbruch, gross genug fuer vernachlaessigbare CPU-Last.
_POLL_INTERVAL_SECONDS = 0.2

# Auftrags-Rahmen des Schreib-Kaefigs (ADR-050): die Grenzen werden dem
# Agenten explizit genannt - zusaetzlich zur technischen Durchsetzung ueber
# --allowedTools (Prompt erklaert, Technik erzwingt).
_WORK_PROMPT = (
    "Du arbeitest als Umsetzungs-Agent in genau einem Projektverzeichnis: "
    "{repo}\n"
    "Regeln: Arbeite AUSSCHLIESSLICH in diesem Verzeichnis. Du hast kein "
    "Bash - keine git-Befehle, keine Programm-/Testausfuehrung. Aendere nur, "
    "was der Auftrag verlangt; keine ungefragten Umbauten. Beachte die "
    "Dokumentationspflichten des Ziel-Repos (CONTRIBUTING/logbook/"
    "PROJECT_STATE nachfuehren, falls dort gefordert - Befund 2026-07-10: "
    "die Gate-Ableitung kam ohne logbook-Eintrag). Fasse am Ende kurz "
    "zusammen, welche Dateien du angelegt oder geaendert hast und "
    "warum.\n\nAuftrag:\n{task}"
)


class RedirectChannel:
    """Bidirektionaler Draht (ADR-056 Scheibe 3): die Runtime legt hier
    Kurskorrekturen des Nutzers hinein ('mach's anders'), das laufende Backend
    zieht sie und schiebt sie dem Agenten mitten im Lauf ueber stdin unter.
    Thread-sicher (Queue). Bewusst schmal - nur Text rein, Text raus; der
    Backend-Adapter entscheidet, wie er ihn dem konkreten Werkzeug zufuehrt
    (werkzeug-agnostisch, ADR-036)."""

    def __init__(self) -> None:
        self._q: "queue.Queue[str]" = queue.Queue()

    def send(self, text: str) -> None:
        """Legt eine Kurskorrektur ab (von der Runtime aufgerufen)."""
        if text and text.strip():
            self._q.put(text.strip())

    def drain(self) -> list[str]:
        """Zieht ALLE anstehenden Korrekturen (vom Backend im Lauf gepollt)."""
        out: list[str] = []
        try:
            while True:
                out.append(self._q.get_nowait())
        except queue.Empty:
            pass
        return out

    def clear(self) -> None:
        """Verwirft stehen gebliebene Korrekturen - zu Beginn eines Laufs, damit
        nie eine alte Nachricht in einen neuen Lauf einsickert."""
        self.drain()


def _user_message_json(text: str) -> str:
    """Eine Nutzer-Nachricht im stream-json-Eingabeformat der Claude-CLI
    (empirisch verifiziert 2026-07-11): eine JSON-Zeile, mit '\\n' abgeschlossen,
    damit die CLI sie sofort verarbeitet (realtime streaming input)."""
    return json.dumps(
        {"type": "user", "message": {"role": "user", "content": text}},
        ensure_ascii=False,
    ) + "\n"


@dataclass
class AgentLimits:
    """Harte Grenzen fuer einen Agentenlauf: der Wall-Clock-Timeout
    (Subprozess-Kill) ist der einzige vorab erzwingbare Guardrail (kein
    CLI-Turn-/Kostendeckel verfuegbar). Ergaenzt wird er zur Laufzeit durch
    den optionalen cancel_event (Kill-Switch der Runtime, ADR-035)."""

    timeout_seconds: float = 300.0


@dataclass
class AgentResult:
    """Ergebnis eines Agentenlaufs - rein informativ (Trust Boundary:
    loest nie selbst eine Aktion aus). num_turns/cost_usd sind, soweit vom
    Backend geliefert, fuer Logging und Artefakt gedacht (Observability),
    nicht fuer eine Steuerungsentscheidung."""

    text: str
    ok: bool
    duration_seconds: float
    detail: str = ""
    num_turns: Optional[int] = None
    cost_usd: Optional[float] = None


class AgentBackend(Protocol):
    """Rohschnittstelle der Delegation: Repo + Frage rein, Ergebnis raus.
    Read-only ist Teil des Vertrags - eine Implementierung MUSS das
    Schreiben/Ausfuehren im Ziel-Repo ausschliessen. cancel_event (optional,
    ADR-035) erlaubt der Runtime, einen laufenden Agentenlauf hart
    abzubrechen (Kill-Switch)."""

    # Anzeigename des Backends. Der Adapter kennt seinen eigenen Namen (ADR-036);
    # die Fachlogik liest ihn nur (z. B. fuer Artefakt-Header/Logs) und nennt
    # kein konkretes Backend hart.
    name: str

    def analyze(
        self,
        repo: Path,
        question: str,
        limits: AgentLimits,
        cancel_event: "Optional[threading.Event]" = None,
        on_event: "Optional[Callable[[dict], None]]" = None,
        redirect: "Optional[RedirectChannel]" = None,
    ) -> AgentResult:
        ...

    def work(
        self,
        repo: Path,
        task: str,
        limits: AgentLimits,
        cancel_event: "Optional[threading.Event]" = None,
        on_event: "Optional[Callable[[dict], None]]" = None,
        redirect: "Optional[RedirectChannel]" = None,
    ) -> AgentResult:
        """Schreibender Lauf im Kaefig (ADR-050): Edit/Write NUR im Ziel-Repo,
        kein Bash (keine git-Operation, keine Ausfuehrung). Das Ergebnis ist
        rein informativ - Sichtung/Commit bleiben ausserhalb des Agenten.

        on_event (optional, ADR-056): generischer Ereignis-Rueckruf pro Schritt
        (Durchsicht). Teil des Vertrags, damit jedes Backend dieselbe Form
        liefert und den Harnisch erbt.

        redirect (optional, ADR-056 Scheibe 3): bidirektionaler Draht - liegt
        eine Kurskorrektur an, schiebt der Adapter sie dem Agenten mitten im
        Lauf unter. Nur wirksam zusammen mit on_event (interaktiv setzt
        Durchsicht voraus)."""
        ...


class ClaudeCodeBackend:
    """Erste AgentBackend-Implementierung: startet `claude -p` als
    Subprozess im Ziel-Repo, read-only erzwungen. Statt `subprocess.run`
    wird `subprocess.Popen` genutzt, damit ein laufender Prozess auf
    cancel_event/Timeout hin hart beendet werden kann (Kill-Switch der
    Runtime, ADR-035) - ohne Popen wuerde `runtime.stop()` bis zum Timeout
    (bis 300 s) haengen. Die Popen-Factory ist injizierbar, damit Tests ohne
    echten `claude`-Aufruf/Netzwerk laufen (gleiches Muster wie ein
    injizierter reader/searcher in den bestehenden Commands)."""

    name = "Claude Code"

    def __init__(self, popen=subprocess.Popen, binary: str = CLAUDE_BINARY):
        self._popen = popen
        self._binary = binary

    def _build_argv(
        self, repo: Path, prompt: str, tools: tuple[str, ...],
        stream: bool = False, interactive: bool = False,
    ) -> list[str]:
        """Baut die Kommandozeile. Werkzeug-Kaefig ueber --allowedTools
        (read-only bzw. pfadgebunden schreibend, ADR-050); das Ziel-Repo wird
        ueber --add-dir freigegeben und ist zusaetzlich das cwd.

        stream=True (Durchsicht, ADR-056): stream-json liefert die Schritte
        als Ereignis-Zeilen, waehrend sie passieren (statt EINes JSON am Ende).
        Die CLI verlangt dafuer zusaetzlich --verbose.

        interactive=True (Umlenken, ADR-056 Scheibe 3): --input-format
        stream-json macht stdin zum realtime-Eingabekanal - der Auftrag UND
        spaetere Kurskorrekturen kommen als JSON-Zeilen ueber stdin (nicht als
        Positions-Argument). --replay-user-messages spiegelt injizierte
        Nachrichten zur Quittung zurueck. Setzt Stream voraus."""
        if interactive:
            return [
                self._binary, "-p", "--allowedTools", *tools,
                "--output-format", "stream-json", "--verbose",
                "--input-format", "stream-json", "--replay-user-messages",
                "--add-dir", str(repo),
            ]
        fmt = ["--output-format", "stream-json", "--verbose"] if stream else ["--output-format", "json"]
        return [self._binary, "-p", prompt, "--allowedTools", *tools, *fmt, "--add-dir", str(repo)]

    def analyze(
        self,
        repo: Path,
        question: str,
        limits: AgentLimits,
        cancel_event: Optional[threading.Event] = None,
        on_event: Optional[Callable[[dict], None]] = None,
        redirect: Optional[RedirectChannel] = None,
    ) -> AgentResult:
        interactive = redirect is not None and on_event is not None
        argv = self._build_argv(
            repo, question, READ_ONLY_TOOLS, stream=on_event is not None, interactive=interactive
        )
        return self._run(argv, repo, limits, cancel_event, on_event,
                         redirect=redirect, initial_message=question if interactive else None)

    def work(
        self,
        repo: Path,
        task: str,
        limits: AgentLimits,
        cancel_event: Optional[threading.Event] = None,
        on_event: Optional[Callable[[dict], None]] = None,
        redirect: Optional[RedirectChannel] = None,
    ) -> AgentResult:
        """Schreibender Lauf im Kaefig (ADR-050): Edit/Write pfadgebunden auf
        das Ziel-Repo, kein Bash. Der Auftrags-Rahmen nennt dem Agenten seine
        Grenzen zusaetzlich explizit (Technik erzwingt, Prompt erklaert).

        on_event (Durchsicht, ADR-056): wird bei jedem Schritt mit einem
        GENERISCHEN Ereignis aufgerufen ({kind,label,detail}) - dann laeuft der
        Agent im Stream-Modus. Ohne on_event bleibt alles beim Stapel-Modus
        (rueckwaertskompatibel).

        redirect (Scheibe 3): mit on_event zusammen laeuft der Agent INTERAKTIV
        (stdin-Eingabekanal) - der Nutzer kann ihn mitten im Lauf umlenken."""
        prompt = _WORK_PROMPT.format(repo=repo, task=task)
        interactive = redirect is not None and on_event is not None
        argv = self._build_argv(
            repo, prompt, write_tools(repo), stream=on_event is not None, interactive=interactive
        )
        return self._run(argv, repo, limits, cancel_event, on_event,
                         redirect=redirect, initial_message=prompt if interactive else None)

    def _run(
        self,
        argv: list[str],
        repo: Path,
        limits: AgentLimits,
        cancel_event: Optional[threading.Event],
        on_event: Optional[Callable[[dict], None]] = None,
        redirect: Optional[RedirectChannel] = None,
        initial_message: Optional[str] = None,
    ) -> AgentResult:
        started = time.monotonic()
        interactive = redirect is not None and on_event is not None and initial_message is not None
        try:
            proc = self._popen(
                argv,
                cwd=str(repo),
                # Interaktiv (Scheibe 3): stdin offen als Eingabekanal. Sonst
                # bleibt stdin ungenutzt (der Auftrag steht im Argument).
                stdin=subprocess.PIPE if interactive else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                # claude -p gibt UTF-8 aus. Ohne explizites encoding dekodiert
                # subprocess unter Windows mit der locale-Codepage (cp1252) und
                # zerschiesst Umlaute/Pfeile (Live-Fund Rauchtest 2026-07-06:
                # "ausfuehrt" -> "ausfÃ¼hrt"). errors="replace" haelt den Lauf am
                # Leben, falls doch ein nicht dekodierbares Byte auftaucht.
                encoding="utf-8",
                errors="replace",
                # Kein aufpoppendes Konsolenfenster (PO-Befund 2026-07-10):
                # die Runtime laeuft fensterlos (pythonw), der claude-
                # Subprozess bekaeme sonst ein eigenes Terminal. Unter
                # Nicht-Windows ist das Flag 0 (wirkungslos).
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except FileNotFoundError:
            return AgentResult(
                text="",
                ok=False,
                duration_seconds=time.monotonic() - started,
                detail=(
                    f"Agenten-Backend '{self._binary}' nicht gefunden (nicht im PATH). "
                    "Claude Code muss installiert und angemeldet sein (ADR-034)."
                ),
            )

        if interactive:
            redirect.clear()  # keine alte Korrektur in den neuen Lauf einsickern lassen
            self._send_user(proc, initial_message)  # der Auftrag als erste stdin-Nachricht
            return self._wait_interactive(
                proc, repo, limits, cancel_event, started, on_event, redirect
            )
        if on_event is not None:
            return self._wait_streaming(proc, repo, limits, cancel_event, started, on_event)
        return self._wait(proc, repo, limits, cancel_event, started)

    @staticmethod
    def _send_user(proc, text: str) -> bool:
        """Schiebt eine Nutzer-Nachricht ueber stdin in den laufenden Agenten.
        Fail-safe: ist die Pipe schon zu (Prozess beendet), wird das nur
        vermerkt - eine spaete Korrektur darf nie den Lauf zum Absturz bringen."""
        try:
            proc.stdin.write(_user_message_json(text))
            proc.stdin.flush()
            return True
        except Exception:  # noqa: BLE001 - Pipe kann jederzeit brechen
            logger.debug("Konnte Nachricht nicht an Agenten-stdin schreiben.", exc_info=True)
            return False

    @staticmethod
    def _close_stdin(proc) -> None:
        """Schliesst den Eingabekanal - das Signal an die CLI, dass keine
        weitere Nachricht kommt: sie beendet die laufende Antwort und exit-et."""
        try:
            if getattr(proc, "stdin", None) is not None and not proc.stdin.closed:
                proc.stdin.close()
        except Exception:  # noqa: BLE001 - Aufraeumen darf nie werfen
            logger.debug("stdin-close unvollstaendig.", exc_info=True)

    def _wait_interactive(
        self, proc, repo: Path, limits: AgentLimits,
        cancel_event: Optional[threading.Event], started: float,
        on_event: Callable[[dict], None], redirect: RedirectChannel,
    ) -> AgentResult:
        """Interaktiver Lauf (ADR-056 Scheibe 3): wie die Durchsicht, aber der
        Nutzer kann mitten im Lauf umlenken. stdin bleibt offen; anstehende
        Korrekturen werden dem Agenten als weitere Nutzer-Nachrichten
        untergeschoben. Lebenszyklus (empirisch verifiziert 2026-07-11): claude
        beantwortet jede Nachricht und WARTET dann auf weitere Eingabe - erst
        wenn wir stdin schliessen, beendet es sich. Wir schliessen, sobald ein
        Zug fertig ist (result) UND keine Korrektur mehr aussteht (received >=
        sent). So endet der Lauf natuerlich, laesst aber jede rechtzeitige
        Kurskorrektur noch zu. Abbruch-Praezedenz wie sonst (Cancel/Timeout ->
        harter Kill als Backstop)."""
        line_q: "queue.Queue" = queue.Queue()
        sentinel = object()

        def _read_stdout():
            try:
                for line in proc.stdout:
                    line_q.put(line)
            except Exception:  # noqa: BLE001
                pass
            finally:
                line_q.put(sentinel)

        threading.Thread(target=_read_stdout, name="jarvis-agent-reader", daemon=True).start()
        if getattr(proc, "stderr", None) is not None:
            def _drain_stderr():
                try:
                    for _ in proc.stderr:
                        pass
                except Exception:  # noqa: BLE001
                    pass
            threading.Thread(target=_drain_stderr, name="jarvis-agent-stderr", daemon=True).start()

        stdin_closed = False
        start_shown = False
        result_data = None

        def _inject_pending() -> int:
            """Zieht anstehende Korrekturen und schiebt sie dem Agenten unter.
            Liefert die Anzahl tatsaechlich injizierter Nachrichten - der
            Aufrufer entscheidet daran, ob der Lauf endet oder weitergeht."""
            if stdin_closed:
                return 0
            n = 0
            for text in redirect.drain():
                if self._send_user(proc, text):
                    n += 1
                    try:
                        on_event({"kind": "redirect", "label": "du sagst", "detail": text[:160]})
                    except Exception:  # noqa: BLE001
                        logger.debug("on_event(redirect) warf.", exc_info=True)
            return n

        while True:
            _inject_pending()
            try:
                item = line_q.get(timeout=_POLL_INTERVAL_SECONDS)
            except queue.Empty:
                if cancel_event is not None and cancel_event.is_set():
                    self._close_stdin(proc)
                    return self._terminate(proc, started, "Lauf gestoppt.")
                if (time.monotonic() - started) >= limits.timeout_seconds:
                    self._close_stdin(proc)
                    return self._terminate(
                        proc, started,
                        f"Zeitlimit ({limits.timeout_seconds:.0f}s) ueberschritten - Lauf abgebrochen.",
                    )
                continue
            if item is sentinel:
                break
            try:
                raw = json.loads(item)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(raw, dict):
                continue
            if raw.get("type") == "result":
                result_data = raw  # jeder Zug ueberschreibt; am Ende gilt der letzte
                # Ein Zug ist fertig. Steht (noch) eine Korrektur an, schieben wir
                # sie unter und lassen den Agenten weiterlaufen. Steht NICHTS an,
                # ist er fertig -> stdin schliessen, er beendet sich. Bewusst NICHT
                # ueber "so viele Ergebnisse wie Nachrichten" (Live-Fund 2026-07-11:
                # der Agent faltet eine mid-turn-Korrektur in DENSELBEN Zug -> ein
                # result statt zwei -> die Zaehlung haette ewig gewartet).
                if _inject_pending() == 0 and not stdin_closed:
                    self._close_stdin(proc)
                    stdin_closed = True
            for event in self._normalize_events(raw):
                kind = event.get("kind")
                if kind == "start":
                    if start_shown:
                        continue  # jeder Zug re-emittiert init - nur einmal zeigen
                    start_shown = True
                elif kind == "done":
                    continue  # das finale "fertig" setzen wir selbst, EINmal, am Ende
                try:
                    on_event(event)
                except Exception:  # noqa: BLE001 - kaputter Zuhoerer stoert nie
                    logger.debug("on_event-Zuhoerer warf.", exc_info=True)

        self._close_stdin(proc)
        try:
            proc.wait(timeout=_POLL_INTERVAL_SECONDS)
        except Exception:  # noqa: BLE001
            pass
        duration = time.monotonic() - started
        returncode = proc.returncode if proc.returncode is not None else 0
        if result_data is not None:
            ok = not result_data.get("is_error")
            try:
                on_event({"kind": "done", "label": "fertig" if ok else "abgebrochen",
                          "detail": str(result_data.get("subtype", ""))})
            except Exception:  # noqa: BLE001
                logger.debug("on_event(done) warf.", exc_info=True)
            return self._result_from_data(result_data, returncode, duration)
        return AgentResult(
            text="", ok=False, duration_seconds=duration,
            detail="Agenten-Stream endete ohne Ergebnis-Ereignis.",
        )

    def _wait(
        self,
        proc,
        repo: Path,
        limits: AgentLimits,
        cancel_event: Optional[threading.Event],
        started: float,
    ) -> AgentResult:
        """Wartet auf den Prozess und setzt die Abbruch-Praezedenz durch:
        **natuerlicher Abschluss > Cancel > Timeout**. Ist der Prozess in
        einer Iteration bereits fertig, gewinnt sein Ergebnis (die Arbeit ist
        getan). Laeuft er noch, wird zuerst cancel_event, dann das
        Gesamt-Timeout geprueft - jeweils genau ein gemeldeter Grund, kein
        Zombie-Prozess."""
        while True:
            try:
                stdout, stderr = proc.communicate(timeout=_POLL_INTERVAL_SECONDS)
            except subprocess.TimeoutExpired:
                # Prozess laeuft noch: Cancel hat Vorrang vor Timeout.
                if cancel_event is not None and cancel_event.is_set():
                    return self._terminate(
                        proc, started, "Analyse abgebrochen - Lauf gestoppt."
                    )
                if (time.monotonic() - started) >= limits.timeout_seconds:
                    logger.warning(
                        "Agentenlauf abgebrochen: Zeitlimit %.0fs ueberschritten (Repo %s).",
                        limits.timeout_seconds,
                        repo,
                    )
                    return self._terminate(
                        proc,
                        started,
                        f"Zeitlimit ({limits.timeout_seconds:.0f}s) ueberschritten - Lauf abgebrochen.",
                    )
                continue
            # Natuerlicher Abschluss - gewinnt auch, falls gleichzeitig ein
            # Cancel eintraf (das Ergebnis liegt bereits vor).
            return self._parse_output(
                proc.returncode, stdout, stderr, time.monotonic() - started
            )

    def _terminate(self, proc, started: float, detail: str) -> AgentResult:
        """Killt den laufenden Prozess und leert die Pipes (kein Zombie)."""
        try:
            proc.kill()
            proc.communicate(timeout=_POLL_INTERVAL_SECONDS)
        except Exception:  # noqa: BLE001 - Aufraeumen darf nie selbst scheitern
            logger.debug("Aufraeumen nach kill() unvollstaendig.", exc_info=True)
        return AgentResult(
            text="", ok=False, duration_seconds=time.monotonic() - started, detail=detail
        )

    def _parse_output(
        self, returncode: int, stdout: str, stderr: str, duration: float
    ) -> AgentResult:
        """Uebersetzt das Subprozess-Ergebnis in ein AgentResult. Keine
        stillen Fehler: Exit != 0, is_error und nicht parsebares JSON werden
        klar als ok=False mit `detail` gemeldet.

        Die JSON-Ausgabe wird IMMER zuerst verstanden - auch bei Exit != 0:
        claude meldet Fehler (z. B. Session-Limit/429) als JSON mit
        is_error=true und einer menschenlesbaren Meldung im Feld `result`.
        Frueher griff bei Exit != 0 ein Vorab-Zweig, der das rohe stdout (das
        JSON) als detail durchreichte -> beim Nutzer landete eine JSON-Wand
        statt der Klartext-Meldung (Dogfooding-Fund 2026-07-08)."""
        stdout = (stdout or "").strip()
        stderr = (stderr or "").strip()

        data = None
        if stdout:
            try:
                parsed = json.loads(stdout)
            except (json.JSONDecodeError, ValueError):
                parsed = None
            if isinstance(parsed, dict):
                data = parsed

        if data is None:
            # Kein/kaputtes JSON. Bei Exit != 0 ehrlich mit stderr/stdout/
            # Exit-Code, bei Exit 0 als "kein gueltiges JSON" markieren (kein
            # stiller Erfolg) - Verhalten wie bisher.
            if returncode != 0:
                detail = stderr or stdout or f"Exit-Code {returncode}"
                return AgentResult(
                    text=stdout,
                    ok=False,
                    duration_seconds=duration,
                    detail=f"Agentenlauf fehlgeschlagen: {detail}",
                )
            return AgentResult(
                text=stdout,
                ok=False,
                duration_seconds=duration,
                detail="Antwort des Agenten war kein gueltiges JSON.",
            )

        return self._result_from_data(data, returncode, duration)

    def _result_from_data(self, data: dict, returncode: int, duration: float) -> AgentResult:
        """Ergebnis-Dict (Stapel-JSON ODER das result-Ereignis des Streams,
        ADR-056) -> AgentResult. Eine Quelle fuer beide Modi. Exit != 0 gilt
        auch bei sauberem JSON als Fehler (etwas ging schief)."""
        is_error = bool(data.get("is_error", False)) or returncode != 0
        text = (data.get("result") or "").strip()
        num_turns = data.get("num_turns")
        cost = data.get("total_cost_usd")
        turns = num_turns if isinstance(num_turns, int) else None
        cost_usd = float(cost) if isinstance(cost, (int, float)) else None
        if is_error or not text:
            return AgentResult(
                text=text, ok=False, duration_seconds=duration,
                detail=self._error_detail(data, text), num_turns=turns, cost_usd=cost_usd,
            )
        return AgentResult(
            text=text, ok=True, duration_seconds=duration,
            detail=data.get("subtype", "success"), num_turns=turns, cost_usd=cost_usd,
        )

    def _wait_streaming(
        self, proc, repo: Path, limits: AgentLimits,
        cancel_event: Optional[threading.Event], started: float,
        on_event: Callable[[dict], None],
    ) -> AgentResult:
        """Durchsicht (ADR-056): liest die stream-json-Zeilen Zeile fuer Zeile,
        ruft on_event pro Schritt mit einem GENERISCHEN Ereignis auf und setzt
        dieselbe Abbruch-Praezedenz durch (Abschluss > Cancel > Timeout). Ein
        Leser-Thread entkoppelt das blockierende readline vom Cancel-/Timeout-
        Poll (Windows-tauglich); ein zweiter leert stderr (kein Pipe-Stau)."""
        line_q: "queue.Queue" = queue.Queue()
        sentinel = object()

        def _read_stdout():
            try:
                for line in proc.stdout:
                    line_q.put(line)
            except Exception:  # noqa: BLE001 - Lesefehler beenden den Strom, kein Absturz
                pass
            finally:
                line_q.put(sentinel)

        threading.Thread(target=_read_stdout, name="jarvis-agent-reader", daemon=True).start()
        if getattr(proc, "stderr", None) is not None:
            def _drain_stderr():
                try:
                    for _ in proc.stderr:
                        pass
                except Exception:  # noqa: BLE001
                    pass
            threading.Thread(target=_drain_stderr, name="jarvis-agent-stderr", daemon=True).start()

        result_data = None
        while True:
            try:
                item = line_q.get(timeout=_POLL_INTERVAL_SECONDS)
            except queue.Empty:
                if cancel_event is not None and cancel_event.is_set():
                    return self._terminate(proc, started, "Lauf gestoppt.")
                if (time.monotonic() - started) >= limits.timeout_seconds:
                    return self._terminate(
                        proc, started,
                        f"Zeitlimit ({limits.timeout_seconds:.0f}s) ueberschritten - Lauf abgebrochen.",
                    )
                continue
            if item is sentinel:
                break
            try:
                raw = json.loads(item)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(raw, dict):
                continue
            if raw.get("type") == "result":
                result_data = raw
            for event in self._normalize_events(raw):
                try:
                    on_event(event)
                except Exception:  # noqa: BLE001 - ein kaputter Zuhoerer stoert den Lauf nie
                    logger.debug("on_event-Zuhoerer warf.", exc_info=True)

        try:
            proc.wait(timeout=_POLL_INTERVAL_SECONDS)
        except Exception:  # noqa: BLE001
            pass
        duration = time.monotonic() - started
        returncode = proc.returncode if proc.returncode is not None else 0
        if result_data is not None:
            return self._result_from_data(result_data, returncode, duration)
        return AgentResult(
            text="", ok=False, duration_seconds=duration,
            detail="Agenten-Stream endete ohne Ergebnis-Ereignis.",
        )

    @staticmethod
    def _normalize_events(raw: dict) -> list:
        """Ein Claude-stream-json-Ereignis -> 0..n GENERISCHE UI-Ereignisse
        {kind,label,detail} (ADR-056). Werkzeug-agnostisch: ein anderes Backend
        liefert dieselbe Form. Werkzeug-Ergebnisse (Rauschen) uebersprungen."""
        t = raw.get("type")
        if t == "system" and raw.get("subtype") == "init":
            return [{"kind": "start", "label": "Agent gestartet", "detail": ""}]
        if t == "result":
            ok = not raw.get("is_error")
            return [{"kind": "done", "label": "fertig" if ok else "abgebrochen",
                     "detail": str(raw.get("subtype", ""))}]
        if t == "assistant":
            content = (raw.get("message") or {}).get("content") or []
            out = []
            for item in content if isinstance(content, list) else []:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    txt = str(item.get("text", "")).strip()
                    if txt:
                        out.append({"kind": "text", "label": "überlegt", "detail": txt[:160]})
                elif item.get("type") == "tool_use":
                    out.append({"kind": "tool", "label": str(item.get("name", "Werkzeug")),
                                "detail": _tool_input_summary(item.get("input"))})
            return out
        return []

    @staticmethod
    def _error_detail(data: dict, text: str) -> str:
        """Baut aus einem Fehler-JSON eine nutzerfreundliche `detail`-Meldung.
        Der Session-Limit-/429-Fall bekommt eine freundliche, Jarvis-
        gesprochene Meldung mitsamt dem Reset-Hinweis aus `result`; sonst wird
        die menschenlesbare `result`-Meldung bevorzugt, erst zuletzt der
        (oft wenig sagende) `subtype`."""
        is_session_limit = (
            data.get("api_error_status") == 429 or "session limit" in text.lower()
        )
        if is_session_limit:
            hint = text or "Session-Limit erreicht."
            return (
                "Der Agenten-Arm ist gerade am Session-Limit und pausiert. "
                f"Hinweis: {hint}"
            )
        if text:
            return text
        return data.get("subtype") or "Agent meldete einen Fehler oder lieferte keinen Text."
