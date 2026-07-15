"""
BrowserChannel (ADR-047) - vierter Runtime-Kanal: lokale HTTP-API fuer das
Jarvis-UI. Gleiche Entkopplung wie der Telegram-Kanal (ADR-027): hinein nur
ueber runtime.submit(), hinaus nur ueber reply_callback; die Runtime kennt
den Browser nicht.

Transport (stdlib-only):
- POST /message  {"text": "..."}  -> Nachricht in die Pipeline (volle
  Intents, PO-Entscheidung 10.07.2026; Stufe-2/3 laufen ueber den
  Executor-Dialog + ConfirmationGate wie bei Telegram, ADR-045).
- POST /entry/delete {"text": "..."} -> loescht EINEN Eintrag direkt
  (delete_entry, Stufe 0) OHNE Planner und ohne Chat-Echo - fuer das
  ✕ auf den UI-Karten (PO 2026-07-10: "ein Klick ist keine
  Konversation").
- POST /fact/forget {"text": "..."} -> entwertet EINEN dauerhaften Fakt
  (forget_fact, Stufe 0), gleiches Muster - fuer das ✕ in der
  GEDAECHTNIS-Ansicht.
- POST /impulse/dismiss {"key": "..."} -> klickt EINEN proaktiven Impuls
  weg (dismiss_impulse, Stufe 0, ADR-054) - fuer das ✕ auf einer Impuls-
  Karte. Alle Still-Routen sind hart auf ihren einen Intent verdrahtet -
  kein generischer Befehls-Endpunkt (fail-closed).
- GET  /events   -> Server-Sent-Events-Strom: {"type": "reply"|"confirm"|
  "state", "text"|"value": ...}. Der Orb lebt von den state-Events
  (bereit / arbeitet / wartet).
- GET  /health   -> {"ok": true} (Lebenszeichen fuer das UI).

Sicherheit: bindet AUSSCHLIESSLICH 127.0.0.1; zusaetzlich Origin-Pruefung -
eine fremde Webseite im selben Browser darf die lokale API nicht aufrufen
(403, Nachricht wird NICHT verarbeitet). Default aus (ui_enabled=false).
"""
from __future__ import annotations

import json
import logging
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from core.confirmation import ConfirmationGate

logger = logging.getLogger("jarvis.runtime.browser")

_BIND_HOST = "127.0.0.1"
# Zeitfenster fuer die Antwort auf eine Stufe-2/3-Rueckfrage (wie Telegram).
_CONFIRMATION_TIMEOUT = 120.0
# SSE-Keepalive: alle N Sekunden ein Kommentar-Ping, damit tote Verbindungen
# auffallen und Proxies/Browser die Verbindung nicht kappen.
_SSE_KEEPALIVE_SECONDS = 15.0
# Deckel je Client-Queue - ein haengender Tab darf keinen Speicher fressen.
_CLIENT_QUEUE_MAX = 200
_MAX_BODY_BYTES = 64_000


def _origin_allowed(origin: Optional[str]) -> bool:
    """Nur lokale Seiten (und Nicht-Browser-Clients ohne Origin) duerfen die
    API ansprechen - Schutz vor fremden Webseiten im selben Browser."""
    if not origin:
        return True  # curl/Skripte/gleiche Seite ohne Origin-Header
    return origin.startswith("http://127.0.0.1:") or origin.startswith("http://localhost:")


class _BrowserConfirmer:
    """Bestaetigungsweg des Browser-Kanals (ADR-045-Muster): say() wird zum
    confirm-Event im Strom, listen() wartet auf die naechste Nachricht."""

    def __init__(self, channel: "BrowserChannel"):
        self._channel = channel

    def say(self, text: str) -> None:
        self._channel.publish("state", value="wartet")
        self._channel.publish("confirm", text=text)

    def listen(self) -> str:
        answer = self._channel.gate.wait_answer(timeout=_CONFIRMATION_TIMEOUT)
        # Nach der Antwort geht die Arbeit weiter - der Orb blieb sonst auf
        # Gelb-WARTET haengen, waehrend der Executor minutenlang arbeitete
        # (PO-Befund 2026-07-10). Bei Abbruch setzt der reply-Weg ohnehin
        # gleich auf bereit.
        self._channel.publish("state", value="arbeitet")
        return answer


class BrowserChannel:
    def __init__(self, runtime, port: int = 8766):
        self.runtime = runtime
        self.port = port
        self.gate = ConfirmationGate()
        self._clients: list[queue.Queue] = []
        self._clients_lock = threading.Lock()
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    # -- Lebenszyklus -----------------------------------------------------

    def start(self) -> bool:
        try:
            self._server = ThreadingHTTPServer((_BIND_HOST, self.port), _make_handler(self))
        except OSError:
            logger.warning("BrowserChannel: Port %s belegt - Kanal bleibt aus.", self.port)
            return False
        # Port merken (im Test 0 -> vom OS vergeben).
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="jarvis-browser-channel", daemon=True
        )
        self._thread.start()
        logger.info("BrowserChannel aktiv: http://%s:%s (ADR-047).", _BIND_HOST, self.port)
        return True

    def stop(self) -> None:
        server = self._server
        if server is None:
            return
        server.shutdown()
        server.server_close()
        self._server = None

    # -- Event-Strom ------------------------------------------------------

    def register_client(self) -> queue.Queue:
        client: queue.Queue = queue.Queue(maxsize=_CLIENT_QUEUE_MAX)
        with self._clients_lock:
            self._clients.append(client)
        return client

    def unregister_client(self, client: queue.Queue) -> None:
        with self._clients_lock:
            if client in self._clients:
                self._clients.remove(client)

    def publish(self, event_type: str, **fields) -> None:
        """Broadcast an alle verbundenen Tabs. Volle Queues werden
        uebersprungen (haengender Tab), nie blockiert.

        Generische Felder (Fix 2026-07-10): die feste text=/value=-Signatur
        liess Timeline-Events (stage/intents/seconds, d41c973) mit TypeError
        abprallen - unsichtbar, weil der Emitter Beiwerk-Fehler bewusst
        schluckt. None-Werte werden weiterhin weggelassen."""
        event = {"type": event_type}
        event.update({k: v for k, v in fields.items() if v is not None})
        with self._clients_lock:
            clients = list(self._clients)
        for client in clients:
            try:
                client.put_nowait(event)
            except queue.Full:
                logger.debug("BrowserChannel: Client-Queue voll - Event verworfen.")

    # -- Eingang ----------------------------------------------------------

    def handle_message(self, text: str) -> None:
        """Eine eingehende Browser-Nachricht: erst dem Bestaetigungs-Gate
        anbieten (offene Stufe-2/3-Rueckfrage? Dann ist DAS die Antwort und
        sie geht nie durch den Planner, ADR-045), sonst normale Pipeline."""
        if self.gate.offer_answer(text):
            logger.info("Browser-Nachricht als Bestaetigungs-Antwort konsumiert (Laenge %d).", len(text))
            return

        self.publish("state", value="arbeitet")

        def reply(answer: str) -> None:
            self.publish("reply", text=answer)
            self.publish("state", value="bereit")

        # Vollzugriff (PO 10.07.2026): kein plan_filter - localhost ist so
        # vertrauenswuerdig wie die Konsole. allow_async: Delegationen
        # blockieren den Worker nicht; der Push kommt ueber denselben reply.
        self.runtime.submit(
            text, reply, allow_async=True, confirmer=_BrowserConfirmer(self),
            source="browser",
        )


def _make_handler(channel: BrowserChannel):
    class BrowserApiHandler(BaseHTTPRequestHandler):
        def _drain_request_body(self) -> None:
            """Ungelesenen Request-Body abraeumen, BEVOR eine Fehlantwort
            rausgeht: sonst schliesst der Server mit ungelesenen Bytes im
            Socket - Windows quittiert das mit RST, und der Client sieht
            sporadisch ConnectionAborted statt der Fehlantwort (flackernder
            Origin-Test, 3. Auftreten 10.07.2026)."""
            try:
                length = min(int(self.headers.get("Content-Length", 0) or 0), _MAX_BODY_BYTES)
                if length > 0:
                    self.rfile.read(length)
            except (ValueError, OSError):
                pass

        def _deny_forbidden_origin(self) -> bool:
            origin = self.headers.get("Origin")
            if _origin_allowed(origin):
                return False
            logger.warning("BrowserChannel: fremder Origin abgewiesen: %r", origin)
            self._drain_request_body()
            self._respond(403, {"error": "Origin nicht erlaubt."}, origin=None)
            return True

        def _respond(self, code: int, payload: dict, origin: Optional[str] = "") -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(body)

        def _send_cors_headers(self) -> None:
            origin = self.headers.get("Origin")
            if origin and _origin_allowed(origin):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")

        def do_OPTIONS(self):  # noqa: N802 - Preflight fuer POST mit JSON
            if self._deny_forbidden_origin():
                return
            self.send_response(204)
            self._send_cors_headers()
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_POST(self):  # noqa: N802
            if self._deny_forbidden_origin():
                return
            if self.path not in ("/message", "/entry/delete", "/fact/forget", "/impulse/dismiss", "/agent/stop", "/agent/redirect", "/proposal/dismiss", "/spotify/control"):
                self._drain_request_body()
                self._respond(404, {"error": "Unbekannter Pfad."})
                return
            if self.path == "/agent/stop":
                # Stopp-Knopf (ADR-056 Scheibe 2): bricht eine laufende
                # Delegation ab. Kein Body noetig; direkter Runtime-Aufruf.
                self._drain_request_body()
                stopped = False
                try:
                    stopped = bool(channel.runtime.cancel_delegation())
                except Exception:  # noqa: BLE001 - Stopp ist Beiwerk, nie werfen
                    logger.exception("Agenten-Stopp fehlgeschlagen.")
                logger.info("UI-Still-Aktion Stopp: %s", "gestoppt" if stopped else "nichts aktiv")
                self._respond(200, {"ok": True, "stopped": stopped})
                return
            if self.path == "/spotify/control":
                # Media-Controls der Kachel (ADR-058): direkter Stufe-0-Dispatch
                # des passenden Spotify-Intents - kein Planner, kein Chat-Echo,
                # keine TTS-Ansage (Media-Knopf soll lautlos wirken). Body traegt
                # "action", nicht "text" - deshalb ein eigener frueher Zweig.
                try:
                    length = min(int(self.headers.get("Content-Length", 0)), _MAX_BODY_BYTES)
                    action = str(json.loads(self.rfile.read(length).decode("utf-8")).get("action", "")).strip().lower()
                except (ValueError, json.JSONDecodeError):
                    self._respond(400, {"error": "Ungueltiger JSON-Body."})
                    return
                intents = {"play": "spotify_play", "pause": "spotify_pause",
                           "next": "spotify_next", "previous": "spotify_previous"}
                intent = intents.get(action)
                if not intent:
                    self._respond(400, {"error": "Unbekannte Aktion."})
                    return
                from commands import dispatch
                from core.models import Plan

                result = dispatch(Plan(intent=intent))
                logger.info("UI-Still-Aktion Spotify %s: %s", action,
                            "ok" if result.ok else result.message[:80])
                self._respond(200 if result.ok else 502, {"ok": result.ok, "message": result.message})
                return
            try:
                length = min(int(self.headers.get("Content-Length", 0)), _MAX_BODY_BYTES)
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                # /impulse/dismiss traegt "key", die uebrigen Routen "text".
                # Beide mit Default "" (Audit-Fund 4): ein Body ohne Feld wird
                # sonst zu "None" statt leer und umgeht die 400-Pruefung.
                raw = data.get("key", "") if self.path == "/impulse/dismiss" else data.get("text", "")
                text = str(raw).strip()
            except (ValueError, json.JSONDecodeError):
                self._respond(400, {"error": "Ungueltiger JSON-Body."})
                return
            if not text:
                self._respond(400, {"error": "Leere Nachricht."})
                return
            if self.path == "/agent/redirect":
                # Umlenken (ADR-056 Scheibe 3): schiebt dem laufenden Agenten
                # eine Kurskorrektur unter. KEIN Chat-Echo, kein History-
                # Schreiben - die Nachricht geht direkt an den Agenten; die
                # Durchsicht zeigt sie als "du sagst"-Zeile.
                delivered = False
                try:
                    delivered = bool(channel.runtime.redirect_delegation(text))
                except Exception:  # noqa: BLE001 - Beiwerk, nie werfen
                    logger.exception("Kurskorrektur an Agenten fehlgeschlagen.")
                logger.info("UI-Still-Aktion Umlenken: %s (%s)",
                            "zugestellt" if delivered else "nichts aktiv", text[:60])
                self._respond(200, {"ok": True, "delivered": delivered})
                return
            if self.path == "/proposal/dismiss":
                # Vorschlag verwerfen (PO-Reibung 2026-07-11): setzt den Status
                # im Artefakt auf "verworfen" -> Karte weg. Still, kein Echo.
                ok = False
                try:
                    ok = bool(channel.runtime.dismiss_proposal(text))
                except Exception:  # noqa: BLE001 - Beiwerk, nie werfen
                    logger.exception("Vorschlag verwerfen fehlgeschlagen.")
                logger.info("UI-Still-Aktion Vorschlag verwerfen: %s (%s)",
                            "ok" if ok else "fehlgeschlagen", text[:60])
                self._respond(200 if ok else 404,
                              {"ok": ok, "message": "" if ok else "Diesen Vorschlag gibt es nicht mehr."})
                return
            if self.path == "/impulse/dismiss":
                # Impuls wegklicken (ADR-054): direkte Modul-Funktion, KEIN
                # Registry-Command (bewusst kein Planner-Intent, siehe
                # commands/impulses.py). Kein Chat-Echo - "verstanden".
                from commands.impulses import dismiss as dismiss_impulse

                ok = dismiss_impulse(text)
                logger.info("UI-Still-Aktion Impuls-Wegklick: %s (%s)",
                            "ok" if ok else "fehlgeschlagen", text[:60])
                self._respond(200 if ok else 404,
                              {"ok": ok, "message": "" if ok else "Diesen Impuls gibt es nicht mehr."})
                return
            if self.path in ("/entry/delete", "/fact/forget"):
                # Direkter Stufe-0-Dispatch (kein Planner, kein Chat-Echo):
                # die Stores sind RLock-gesichert, der HTTP-Thread darf das.
                # Hart verdrahtete Intent-Zuordnung - nie aus dem Body.
                from commands import dispatch
                from core.models import Plan

                intent = "delete_entry" if self.path == "/entry/delete" else "forget_fact"
                # exact=True (Nacht-Audit-Fix B): das UI kennt den vollen
                # Text - ein Klick trifft nie einen aehnlichen Nachbarn.
                result = dispatch(Plan(intent=intent, target=text,
                                       parameters={"text": text, "exact": True}))
                logger.info(
                    "UI-Still-Aktion %s: %s (%s)",
                    intent, "ok" if result.ok else "fehlgeschlagen", text[:60],
                )
                self._respond(200 if result.ok else 404, {"ok": result.ok, "message": result.message})
                return
            channel.handle_message(text)
            self._respond(202, {"ok": True})

        def do_GET(self):  # noqa: N802
            if self._deny_forbidden_origin():
                return
            if self.path == "/health":
                self._respond(200, {"ok": True, "channel": "browser"})
                return
            if self.path == "/spotify/now":
                # Read-only Zustand fuer die Kachel (ADR-058), fail-safe.
                from commands.spotify import now_playing_state

                self._respond(200, now_playing_state())
                return
            if self.path != "/events":
                self._respond(404, {"error": "Unbekannter Pfad."})
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self._send_cors_headers()
            self.end_headers()

            client = channel.register_client()
            try:
                # Startzustand, damit der Orb sofort lebt.
                self.wfile.write(_sse({"type": "state", "value": "bereit"}))
                self.wfile.flush()
                while True:
                    try:
                        event = client.get(timeout=_SSE_KEEPALIVE_SECONDS)
                        self.wfile.write(_sse(event))
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass  # Tab zu - normal
            finally:
                channel.unregister_client(client)

        def log_message(self, fmt, *args):  # kein Request-Spam im Log
            logger.debug("%s - %s", self.address_string(), fmt % args)

    return BrowserApiHandler


def _sse(event: dict) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
