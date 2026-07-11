"""Tests fuer browser_channel.py (ADR-047) - echter HTTP-Server auf Port 0,
FakeRuntime statt Core-Stack. SSE wird roh ueber http.client gelesen."""
from __future__ import annotations

import http.client
import json
import threading
import time

from browser_channel import BrowserChannel, _BrowserConfirmer, _origin_allowed


class FakeRuntime:
    def __init__(self, delegation_active=False):
        self.submitted = []
        self._delegation_active = delegation_active
        self.cancel_calls = 0

    def submit(self, text, reply_callback, plan_filter=None, allow_async=False, confirmer=None, source=""):
        self.submitted.append(
            {"text": text, "plan_filter": plan_filter, "allow_async": allow_async,
             "confirmer": confirmer, "source": source}
        )
        reply_callback(f"Antwort auf: {text}")

    def cancel_delegation(self) -> bool:
        self.cancel_calls += 1
        return self._delegation_active

    def redirect_delegation(self, text: str) -> bool:
        self.redirects = getattr(self, "redirects", [])
        self.redirects.append(text)
        return self._delegation_active

    def dismiss_proposal(self, filename: str) -> bool:
        self.dismissed = getattr(self, "dismissed", [])
        self.dismissed.append(filename)
        return filename == "gibt-es.md"   # bekannt -> True, sonst False


def _start_channel(runtime=None):
    channel = BrowserChannel(runtime or FakeRuntime(), port=0)
    assert channel.start()
    return channel


def _post_message(port, text, origin=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    conn.request("POST", "/message", json.dumps({"text": text}), headers)
    response = conn.getresponse()
    body = json.loads(response.read().decode("utf-8"))
    conn.close()
    return response.status, body


def _read_sse_events(port, count, timeout=5.0):
    """Liest die ersten `count` data:-Events des Stroms."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    conn.request("GET", "/events")
    response = conn.getresponse()
    events = []
    deadline = time.monotonic() + timeout
    while len(events) < count and time.monotonic() < deadline:
        line = response.fp.readline().decode("utf-8").strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    conn.close()
    return events


def test_post_message_reaches_runtime_with_full_access():
    runtime = FakeRuntime()
    channel = _start_channel(runtime)
    try:
        status, body = _post_message(channel.port, "wie ist der Status?")

        assert status == 202 and body["ok"] is True
        assert len(runtime.submitted) == 1
        job = runtime.submitted[0]
        assert job["text"] == "wie ist der Status?"
        assert job["plan_filter"] is None          # Vollzugriff (PO 10.07.2026)
        assert job["allow_async"] is True
        assert job["confirmer"] is not None        # Stufe-2/3-Weg vorhanden
    finally:
        channel.stop()


def test_entry_delete_endpoint_is_silent_and_direct(tmp_path):
    """PO 2026-07-10 'ein Klick ist keine Konversation': POST /entry/delete
    loescht direkt ueber delete_entry (kein Planner, kein runtime.submit,
    kein Chat-Echo). Fail-closed: nur dieser eine Intent, hart verdrahtet."""
    import commands.entries as entries_commands
    from core.models import Plan

    store = entries_commands.configure(tmp_path)
    store.add("Zahnarzt anrufen")
    runtime = FakeRuntime()
    channel = _start_channel(runtime)
    try:
        # Voller exakter Text - wie ihn das UI aus memory_view kennt
        # (Nacht-Audit-Fix B: die Endpunkte loeschen nur exakt).
        conn = http.client.HTTPConnection("127.0.0.1", channel.port, timeout=5)
        conn.request("POST", "/entry/delete", json.dumps({"text": "Zahnarzt anrufen"}),
                     {"Content-Type": "application/json"})
        response = conn.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        conn.close()

        assert response.status == 200 and body["ok"] is True
        assert store.list_open() == []              # wirklich geloescht
        assert runtime.submitted == []              # NICHT durch die Pipeline

        # Unbekannter Eintrag: ehrlicher Fehler, nichts passiert still.
        conn = http.client.HTTPConnection("127.0.0.1", channel.port, timeout=5)
        conn.request("POST", "/entry/delete", json.dumps({"text": "gibtsnicht"}),
                     {"Content-Type": "application/json"})
        response = conn.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        conn.close()
        assert response.status == 404 and body["ok"] is False
    finally:
        channel.stop()


def test_agent_stop_endpoint_cancels_delegation():
    """Stopp-Knopf (ADR-056 Scheibe 2): POST /agent/stop bricht eine laufende
    Delegation ab (setzt den Kill-Switch), kein Body noetig, kein Chat-Echo."""
    runtime = FakeRuntime(delegation_active=True)
    channel = _start_channel(runtime)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", channel.port, timeout=5)
        conn.request("POST", "/agent/stop", "{}", {"Content-Type": "application/json"})
        response = conn.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        conn.close()

        assert response.status == 200
        assert body["ok"] is True and body["stopped"] is True
        assert runtime.cancel_calls == 1
        assert runtime.submitted == []            # nicht durch die Pipeline

        # Nichts aktiv -> ok, aber stopped=False.
        runtime2 = FakeRuntime(delegation_active=False)
        channel2 = _start_channel(runtime2)
        try:
            conn = http.client.HTTPConnection("127.0.0.1", channel2.port, timeout=5)
            conn.request("POST", "/agent/stop", "{}", {"Content-Type": "application/json"})
            r = conn.getresponse()
            b = json.loads(r.read().decode("utf-8"))
            conn.close()
            assert r.status == 200 and b["ok"] is True and b["stopped"] is False
        finally:
            channel2.stop()
    finally:
        channel.stop()


def test_agent_redirect_endpoint_delivers_to_runtime():
    """Umlenken (ADR-056 Scheibe 3): POST /agent/redirect schiebt dem laufenden
    Agenten eine Kurskorrektur unter (via runtime.redirect_delegation), kein
    Chat-Echo, nicht durch die Pipeline."""
    runtime = FakeRuntime(delegation_active=True)
    channel = _start_channel(runtime)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", channel.port, timeout=5)
        conn.request("POST", "/agent/redirect",
                     json.dumps({"text": "nimm lieber Y"}), {"Content-Type": "application/json"})
        response = conn.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        conn.close()

        assert response.status == 200
        assert body["ok"] is True and body["delivered"] is True
        assert runtime.redirects == ["nimm lieber Y"]
        assert runtime.submitted == []            # nicht durch die Pipeline

        # Leerer Text -> 400 (wie die anderen Body-Routen).
        conn = http.client.HTTPConnection("127.0.0.1", channel.port, timeout=5)
        conn.request("POST", "/agent/redirect", json.dumps({"text": "  "}),
                     {"Content-Type": "application/json"})
        r = conn.getresponse(); r.read(); conn.close()
        assert r.status == 400
    finally:
        channel.stop()


def test_agent_redirect_endpoint_reports_nothing_active():
    """Laeuft keine Delegation, meldet der Endpunkt delivered=False (die
    Kurskorrektur wird nicht in einen kuenftigen Lauf eingesickert)."""
    runtime = FakeRuntime(delegation_active=False)
    channel = _start_channel(runtime)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", channel.port, timeout=5)
        conn.request("POST", "/agent/redirect", json.dumps({"text": "mach's anders"}),
                     {"Content-Type": "application/json"})
        r = conn.getresponse()
        b = json.loads(r.read().decode("utf-8"))
        conn.close()
        assert r.status == 200 and b["ok"] is True and b["delivered"] is False
    finally:
        channel.stop()


def test_proposal_dismiss_endpoint_marks_and_reports():
    """Vorschlag verwerfen (PO-Reibung 2026-07-11): POST /proposal/dismiss
    reicht den Dateinamen an runtime.dismiss_proposal; bekannt -> 200/ok,
    unbekannt -> 404. Kein Chat-Echo, nicht durch die Pipeline."""
    runtime = FakeRuntime()
    channel = _start_channel(runtime)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", channel.port, timeout=5)
        conn.request("POST", "/proposal/dismiss", json.dumps({"text": "gibt-es.md"}),
                     {"Content-Type": "application/json"})
        r = conn.getresponse()
        b = json.loads(r.read().decode("utf-8"))
        conn.close()
        assert r.status == 200 and b["ok"] is True
        assert runtime.dismissed == ["gibt-es.md"]
        assert runtime.submitted == []            # nicht durch die Pipeline

        # Unbekannte Datei -> 404, ok=False.
        conn = http.client.HTTPConnection("127.0.0.1", channel.port, timeout=5)
        conn.request("POST", "/proposal/dismiss", json.dumps({"text": "weg.md"}),
                     {"Content-Type": "application/json"})
        r = conn.getresponse()
        b = json.loads(r.read().decode("utf-8"))
        conn.close()
        assert r.status == 404 and b["ok"] is False
    finally:
        channel.stop()


def test_impulse_dismiss_endpoint_is_silent_and_direct(tmp_path):
    """Impuls-Karte (ADR-054): POST /impulse/dismiss klickt einen Impuls
    weg (per 'key'), direkt ueber die Modul-Funktion - kein Planner, kein
    Registry-Command, kein Chat-Echo."""
    import commands.impulses as impulses_commands
    from memory.impulses import ImpulseStore

    store = ImpulseStore(tmp_path)
    store.add_if_new("weather", "weather-storm-2026-07-11", "Unwetter", "Gewitter")
    impulses_commands.configure(store)
    runtime = FakeRuntime()
    channel = _start_channel(runtime)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", channel.port, timeout=5)
        conn.request("POST", "/impulse/dismiss", json.dumps({"key": "weather-storm-2026-07-11"}),
                     {"Content-Type": "application/json"})
        response = conn.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        conn.close()

        assert response.status == 200 and body["ok"] is True
        assert store.count_open() == 0                # wirklich weggeklickt
        assert runtime.submitted == []               # NICHT durch die Pipeline

        # Unbekannter key: ehrlicher Fehler, nichts passiert still.
        conn = http.client.HTTPConnection("127.0.0.1", channel.port, timeout=5)
        conn.request("POST", "/impulse/dismiss", json.dumps({"key": "gibtsnicht"}),
                     {"Content-Type": "application/json"})
        response = conn.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        conn.close()
        assert response.status == 404 and body["ok"] is False
    finally:
        channel.stop()


def test_fact_forget_endpoint_is_silent_and_direct(tmp_path):
    """GEDAECHTNIS-Ansicht (Scheibe 4): POST /fact/forget entwertet einen
    Fakt direkt (forget_fact, Stufe 0) - kein Planner, kein Chat-Echo."""
    import commands.memory as memory_commands
    from memory.long_term import LongTermMemory

    memory_commands.configure(tmp_path)
    LongTermMemory(tmp_path).remember("trinkt Kaffee schwarz", category="gewohnheit")
    runtime = FakeRuntime()
    channel = _start_channel(runtime)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", channel.port, timeout=5)
        conn.request("POST", "/fact/forget", json.dumps({"text": "trinkt Kaffee schwarz"}),
                     {"Content-Type": "application/json"})
        response = conn.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        conn.close()

        assert response.status == 200 and body["ok"] is True
        assert LongTermMemory(tmp_path).all_facts() == []  # wirklich vergessen
        assert runtime.submitted == []                     # NICHT durch die Pipeline
    finally:
        channel.stop()


def test_events_stream_delivers_state_and_reply():
    channel = _start_channel()
    try:
        collected = {}
        done = threading.Event()

        def listen():
            collected["events"] = _read_sse_events(channel.port, count=4)
            done.set()

        thread = threading.Thread(target=listen, daemon=True)
        thread.start()
        time.sleep(0.3)  # Stream verbinden lassen
        _post_message(channel.port, "hallo")
        assert done.wait(timeout=5.0)

        types = [(e["type"], e.get("value")) for e in collected["events"]]
        assert types[0] == ("state", "bereit")     # Startzustand fuer den Orb
        assert ("state", "arbeitet") in types
        assert any(e["type"] == "reply" and "hallo" in e.get("text", "") for e in collected["events"])
        assert types[-1] == ("state", "bereit")
    finally:
        channel.stop()


def test_foreign_origin_is_rejected_without_processing():
    runtime = FakeRuntime()
    channel = _start_channel(runtime)
    try:
        status, body = _post_message(channel.port, "boese Nachricht", origin="http://evil.example")

        assert status == 403
        assert runtime.submitted == []             # NICHT verarbeitet
    finally:
        channel.stop()


def test_local_origin_is_allowed():
    runtime = FakeRuntime()
    channel = _start_channel(runtime)
    try:
        status, _body = _post_message(channel.port, "hallo", origin="http://127.0.0.1:8765")
        assert status == 202
        assert len(runtime.submitted) == 1
    finally:
        channel.stop()


def test_origin_rules():
    assert _origin_allowed(None) is True
    assert _origin_allowed("http://127.0.0.1:8765") is True
    assert _origin_allowed("http://localhost:3000") is True
    assert _origin_allowed("http://evil.example") is False
    assert _origin_allowed("https://127.0.0.1.evil.example") is False


def test_pending_confirmation_consumes_next_message():
    """ADR-045-Muster im Browser: waehrend einer offenen Rueckfrage ist die
    naechste Nachricht die ANTWORT - sie erreicht nie den Planner."""
    runtime = FakeRuntime()
    channel = _start_channel(runtime)
    try:
        confirmer = _BrowserConfirmer(channel)
        received = {}
        waiter = threading.Thread(
            target=lambda: received.setdefault("answer", confirmer.listen()), daemon=True
        )
        waiter.start()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            status, _ = _post_message(channel.port, "HERUNTERFAHREN")
            waiter.join(timeout=0.1)
            if not waiter.is_alive():
                break

        assert received.get("answer") == "HERUNTERFAHREN"
        assert runtime.submitted == []             # Antwort ging nie durch den Planner
    finally:
        channel.stop()


def test_confirmer_publishes_confirm_event():
    channel = _start_channel()
    try:
        published = []
        channel.publish = lambda event_type, text=None, value=None: published.append((event_type, text, value))
        _BrowserConfirmer(channel).say("Bitte tippe: HERUNTERFAHREN")

        assert ("state", None, "wartet") in published
        assert any(t == "confirm" and "HERUNTERFAHREN" in (x or "") for t, x, _ in published)
    finally:
        channel.stop()


def test_health_endpoint_answers():
    channel = _start_channel()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", channel.port, timeout=5)
        conn.request("GET", "/health")
        response = conn.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["ok"] is True
        conn.close()
    finally:
        channel.stop()


def test_empty_or_broken_body_is_rejected():
    runtime = FakeRuntime()
    channel = _start_channel(runtime)
    try:
        status, _ = _post_message(channel.port, "   ")
        assert status == 400

        conn = http.client.HTTPConnection("127.0.0.1", channel.port, timeout=5)
        conn.request("POST", "/message", "kein json", {"Content-Type": "application/json"})
        assert conn.getresponse().status == 400
        conn.close()
        assert runtime.submitted == []
    finally:
        channel.stop()


def test_ui_disabled_by_default():
    from core.config import Config

    assert Config().ui_enabled is False
    assert Config().ui_port == 8766


def test_publish_delivers_arbitrary_event_fields():
    """Integrations-Luecke 2026-07-10: die feste text=/value=-Signatur liess
    Timeline-Events (stage/intents/seconds) mit TypeError abprallen - und der
    Emitter schluckt Beiwerk-Fehler bewusst. publish() ist jetzt generisch;
    None-Felder werden weggelassen."""
    channel = _start_channel()
    try:
        collected = {}
        done = threading.Event()

        def listen():
            collected["events"] = _read_sse_events(channel.port, count=2)
            done.set()

        thread = threading.Thread(target=listen, daemon=True)
        thread.start()
        time.sleep(0.3)  # Stream verbinden lassen
        channel.publish("timeline", stage="plan", intents=["chat"], seconds=1.2, leer=None)
        assert done.wait(timeout=5.0)

        timeline = [e for e in collected["events"] if e["type"] == "timeline"]
        assert timeline, collected["events"]
        assert timeline[0]["stage"] == "plan"
        assert timeline[0]["intents"] == ["chat"]
        assert timeline[0]["seconds"] == 1.2
        assert "leer" not in timeline[0]
    finally:
        channel.stop()
