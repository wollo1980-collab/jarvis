"""
Einmaliger Spotify-OAuth-Helfer (Authorization Code Flow) - holt den
refresh_token, mit dem Jarvis danach dauerhaft (ohne weiteren Login) die
Wiedergabe steuert.

Voraussetzung: in config.json stehen `spotify_client_id` und
`spotify_client_secret` (aus der bei developer.spotify.com registrierten App),
und die dort hinterlegte Redirect-URI stimmt mit `spotify_redirect_uri`
ueberein (Default http://127.0.0.1:8888/callback).

Ablauf:
    python scripts/spotify_auth.py
  -> Browser oeffnet sich, du klickst "Zustimmen"
  -> dieser Helfer faengt den Callback lokal ab, tauscht den Code gegen
     Tokens und zeigt den refresh_token
  -> den refresh_token in config.json unter `spotify_refresh_token` eintragen.

stdlib-only, bindet ausschliesslich an 127.0.0.1. Der Client-Secret wird nie
ausgegeben; der refresh_token schon (den brauchst du zum Eintragen - wie ein
Passwort behandeln, nicht teilen).
"""
from __future__ import annotations

import base64
import json
import secrets
import sys
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.config import Config  # noqa: E402

_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
_TOKEN_URL = "https://accounts.spotify.com/api/token"
# Genau die Rechte, die Jarvis fuer Wiedergabe-Steuerung + Anzeige braucht.
_SCOPES = (
    "user-read-playback-state user-modify-playback-state "
    "user-read-currently-playing playlist-read-private"
)

_result: dict = {}


def _make_handler(expected_state: str):
    class _CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # Server-Rauschen unterdruecken
            pass

        def do_GET(self):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            _result["code"] = (params.get("code") or [None])[0]
            _result["state"] = (params.get("state") or [None])[0]
            _result["error"] = (params.get("error") or [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            ok = _result["code"] and _result["state"] == expected_state and not _result["error"]
            msg = ("Jarvis: Spotify verbunden. Du kannst dieses Fenster schliessen."
                   if ok else "Jarvis: Etwas ging schief - siehe Konsole.")
            self.wfile.write(f"<html><body style='font-family:sans-serif'>{msg}</body></html>"
                             .encode("utf-8"))

    return _CallbackHandler


def _exchange_code(code: str, cid: str, secret: str, redirect: str) -> dict:
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect,
    }).encode("utf-8")
    basic = base64.b64encode(f"{cid}:{secret}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        _TOKEN_URL, data=body,
        headers={"Authorization": f"Basic {basic}",
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    cfg = Config.load()
    cid, secret, redirect = cfg.spotify_client_id, cfg.spotify_client_secret, cfg.spotify_redirect_uri
    if not cid or not secret:
        print("FEHLER: spotify_client_id und spotify_client_secret muessen in "
              "config.json stehen (aus deiner Spotify-App). Dann erneut starten.")
        return 2

    parsed = urllib.parse.urlparse(redirect)
    host, port = parsed.hostname or "127.0.0.1", parsed.port or 8888

    state = secrets.token_urlsafe(16)
    auth_url = _AUTHORIZE_URL + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": cid, "scope": _SCOPES,
        "redirect_uri": redirect, "state": state,
    })

    server = HTTPServer((host, port), _make_handler(state))
    print(f"Oeffne den Browser fuer die Spotify-Anmeldung ...\n  {auth_url}\n"
          f"(Warte auf den Callback an {redirect} - Strg+C bricht ab.)")
    import webbrowser
    webbrowser.open(auth_url)
    server.handle_request()  # genau eine Anfrage: der Callback
    server.server_close()

    if _result.get("error"):
        print(f"FEHLER von Spotify: {_result['error']}")
        return 1
    if not _result.get("code"):
        print("FEHLER: kein Authorization-Code empfangen.")
        return 1
    if _result.get("state") != state:
        print("FEHLER: state stimmt nicht (moeglicher CSRF) - abgebrochen.")
        return 1

    try:
        tokens = _exchange_code(_result["code"], cid, secret, redirect)
    except Exception as e:  # noqa: BLE001
        print(f"FEHLER beim Token-Tausch: {e}")
        return 1

    refresh = tokens.get("refresh_token")
    if not refresh:
        print(f"FEHLER: kein refresh_token in der Antwort: {tokens}")
        return 1

    print("\n=== ERFOLG ===")
    print("Trage diesen Wert in config.json unter \"spotify_refresh_token\" ein")
    print("(wie ein Passwort behandeln, nicht teilen):\n")
    print(refresh)
    print("\nDanach: Jarvis neu starten - die Sprachsteuerung ist scharf.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
