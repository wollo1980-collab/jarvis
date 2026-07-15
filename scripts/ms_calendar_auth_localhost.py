#!/usr/bin/env python3
"""Kalender-Anmeldung ueber den localhost-Loopback (sauberster Desktop-Weg).

Warum: Geraete-Code und nativeclient-Redirect scheitern mit privaten
Microsoft-Konten. Der Loopback-Weg (http://localhost:PORT) faengt den Auth-Code
automatisch mit einem winzigen lokalen Server ab - kein URL-Kopieren, keine
Fehlerseite. Nutzt PKCE (S256), holt Calendars.ReadWrite (Lesen + Schreiben).

Voraussetzung (einmalig in der App 'Jarvis_Kalender'):
  Authentifizierung -> Plattform 'Mobile- und Desktopanwendungen' ->
  Umleitungs-URI http://localhost:8400 hinzufuegen.

Aufruf:
  python ms_calendar_auth_localhost.py <CLIENT_ID> [TENANT]
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

_PORT = 8400
_REDIRECT = f"http://localhost:{_PORT}"
_SCOPE = "https://graph.microsoft.com/Calendars.ReadWrite offline_access"

_result: dict = {}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _result.update({k: v[0] for k, v in params.items()})
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        msg = ("<h2>Jarvis-Kalender: Anmeldung abgeschlossen.</h2>"
               "<p>Du kannst dieses Fenster jetzt schliessen.</p>")
        self.wfile.write(msg.encode("utf-8"))

    def log_message(self, *args):
        pass


def _post(url: str, fields: dict) -> "tuple[int, dict]":
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.getcode(), json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Aufruf: python ms_calendar_auth_localhost.py <CLIENT_ID> [TENANT]")
        return 2
    client_id = argv[1]
    tenant = argv[2] if len(argv) > 2 else "common"
    base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"

    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(16)

    authorize = base + "/authorize?" + urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": _REDIRECT,
        "response_mode": "query",
        "scope": _SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })

    server = HTTPServer(("127.0.0.1", _PORT), _Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()

    print("\n" + "=" * 60)
    print("Oeffne diese Adresse im Browser (falls sie sich nicht selbst oeffnet):")
    print(authorize)
    print("=" * 60 + "\nWarte auf die Anmeldung ...")
    try:
        webbrowser.open(authorize)
    except Exception:
        pass

    # Warten, bis der Handler den Code eingetragen hat (handle_request bedient 1x).
    import time
    for _ in range(300):
        if _result:
            break
        time.sleep(1)

    if "error" in _result:
        print(f"\nAnmeldung fehlgeschlagen: {_result.get('error')} - "
              f"{_result.get('error_description','')[:300]}")
        return 1
    code = _result.get("code")
    if not code:
        print("\nKein Code empfangen (Zeitueberschreitung?).")
        return 1

    status, tok = _post(base + "/token", {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _REDIRECT,
        "code_verifier": verifier,
        "scope": _SCOPE,
    })
    if status == 200 and tok.get("refresh_token"):
        print("\nOK_REFRESH_TOKEN=" + tok["refresh_token"])
        print(f'  "ms_calendar_client_id": "{client_id}",')
        print(f'  "ms_calendar_tenant": "{tenant}",')
        print(f'  "ms_calendar_refresh_token": "{tok["refresh_token"]}"')
        return 0
    print(f"\nToken-Umtausch fehlgeschlagen (HTTP {status}): {tok.get('error')} - "
          f"{tok.get('error_description','')[:300]}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
