"""
Spotify-Connector (ADR-058) - Sprachsteuerung der EIGENEN Wiedergabe ueber die
Spotify Web API. Braucht Premium (Wiedergabe-Steuerung ist bei Spotify
Premium-only) und ein aktives Geraet (Spotify laeuft irgendwo - Jarvis ist
selbst kein Abspielgeraet, er dirigiert nur).

Auth: Authorization-Code-Flow, EINMALIG per scripts/spotify_auth.py eingerichtet
(liefert den refresh_token). Zur Laufzeit tauscht der Client den refresh_token
gegen kurzlebige access_token - kein weiterer Login. client_secret/refresh_token
sind Secrets (Config, nie im Repo).

Trust Boundary: steuert ausschliesslich die eigene Wiedergabe des Nutzers -
reversibel (pause = undo play), lokal folgenlos. Kein Loeschen, kein Posten,
keine Ausgabe von Geld.

stdlib-only; die HTTP-Schicht (_http) ist injizierbar, damit Tests ohne
Netzwerk/echten Account laufen (gleiches Muster wie der Wetter-Fetcher).
"""
from __future__ import annotations

import base64
import json
import logging
import time
import urllib.parse
import urllib.request
from typing import Callable, Optional

logger = logging.getLogger("jarvis.spotify")

_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API_BASE = "https://api.spotify.com/v1"
# Wie lange vor dem echten Ablauf wir den access_token erneuern (Sicherheitsband).
_TOKEN_REFRESH_MARGIN = 30.0


class SpotifyError(Exception):
    """Basisfehler des Connectors - der Command uebersetzt ihn in Klartext."""


class SpotifyAuthError(SpotifyError):
    """Token ungueltig/abgelaufen oder Rechte fehlen (Neu-Einrichtung noetig)."""


class NoActiveDeviceError(SpotifyError):
    """Kein aktives Spotify-Geraet - der Nutzer muss Spotify irgendwo starten."""


# (status_code, body_bytes) - die injizierbare HTTP-Schicht liefert genau das.
HttpFn = Callable[[str, str, dict, Optional[bytes]], "tuple[int, bytes]"]


def _default_http(method: str, url: str, headers: dict, body: Optional[bytes]) -> "tuple[int, bytes]":
    """Echte HTTP-Schicht (urllib). Liefert (status, bytes) auch bei 4xx/5xx,
    statt zu werfen - die Fachlogik entscheidet anhand des Status."""
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as e:  # 4xx/5xx: Body trotzdem lesen
        return e.code, e.read() if hasattr(e, "read") else b""


class SpotifyClient:
    """Duenner Client um die paar Player-Endpunkte, die Jarvis braucht.
    access_token wird gecacht und rechtzeitig erneuert."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        http: Optional[HttpFn] = None,
    ):
        self._cid = client_id
        self._secret = client_secret
        self._rt = refresh_token
        self._http: HttpFn = http or _default_http
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    # --- Auth ---------------------------------------------------------------

    def _access_token(self) -> str:
        if self._token and time.monotonic() < self._token_expiry - _TOKEN_REFRESH_MARGIN:
            return self._token
        basic = base64.b64encode(f"{self._cid}:{self._secret}".encode()).decode("ascii")
        body = urllib.parse.urlencode(
            {"grant_type": "refresh_token", "refresh_token": self._rt}
        ).encode()
        status, data = self._http(
            "POST", _TOKEN_URL,
            {"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            body,
        )
        if status != 200:
            raise SpotifyAuthError(
                f"Token-Erneuerung fehlgeschlagen (HTTP {status}) - Spotify neu einrichten?"
            )
        token = (json.loads(data or b"{}") or {}).get("access_token")
        if not token:
            raise SpotifyAuthError("Spotify lieferte keinen access_token.")
        self._token = token
        self._token_expiry = time.monotonic() + float(json.loads(data).get("expires_in", 3600))
        return token

    # --- Low-level API ------------------------------------------------------

    def _api(self, method: str, path: str, params: Optional[dict] = None,
             body: Optional[dict] = None) -> "tuple[int, bytes]":
        token = self._access_token()
        url = _API_BASE + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        raw = json.dumps(body).encode() if body is not None else None
        status, data = self._http(
            method, url,
            {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            raw,
        )
        if status == 401:
            raise SpotifyAuthError("Spotify-Token abgelehnt (401) - neu einrichten?")
        if status == 404 and b"NO_ACTIVE_DEVICE" in (data or b""):
            raise NoActiveDeviceError("Kein aktives Spotify-Geraet.")
        if status == 403:
            raise SpotifyError(
                "Spotify verweigert die Aktion (403) - Premium nötig oder gerade eingeschränkt."
            )
        if status >= 400:
            raise SpotifyError(f"Spotify-Fehler (HTTP {status}).")
        return status, data

    # --- Player-Aktionen ----------------------------------------------------

    def now_playing(self) -> Optional[dict]:
        """{'title','artist'} des laufenden Titels, oder None wenn nichts spielt."""
        status, data = self._api("GET", "/me/player/currently-playing")
        if status == 204 or not data:
            return None
        item = (json.loads(data) or {}).get("item") or {}
        if not item:
            return None
        artists = ", ".join(a.get("name", "") for a in item.get("artists", []) if a.get("name"))
        return {"title": item.get("name", "?"), "artist": artists}

    def playback(self) -> Optional[dict]:
        """Fuer die UI-Kachel: {'title','artist','is_playing'} des laufenden
        Titels, oder None wenn nichts laeuft/kein Geraet. Wie now_playing, aber
        mit dem is_playing-Flag (Play/Pause-Symbol der Kachel)."""
        status, data = self._api("GET", "/me/player/currently-playing")
        if status == 204 or not data:
            return None
        payload = json.loads(data) or {}
        item = payload.get("item") or {}
        if not item:
            return None
        artists = ", ".join(a.get("name", "") for a in item.get("artists", []) if a.get("name"))
        return {
            "title": item.get("name", "?"),
            "artist": artists,
            "is_playing": bool(payload.get("is_playing")),
        }

    def pause(self) -> None:
        self._api("PUT", "/me/player/pause")

    def resume(self) -> None:
        self._api("PUT", "/me/player/play")

    def next(self) -> None:
        self._api("POST", "/me/player/next")

    def previous(self) -> None:
        self._api("POST", "/me/player/previous")

    def set_volume(self, percent: int) -> int:
        vol = max(0, min(int(percent), 100))
        self._api("PUT", "/me/player/volume", params={"volume_percent": vol})
        return vol

    def current_volume(self) -> Optional[int]:
        """Aktuelle Geraete-Lautstaerke in Prozent (fuer 'lauter'/'leiser'
        relativ zum Ist-Wert), oder None wenn kein Geraet meldet."""
        status, data = self._api("GET", "/me/player")
        if status == 204 or not data:
            return None
        dev = (json.loads(data) or {}).get("device") or {}
        vol = dev.get("volume_percent")
        return int(vol) if vol is not None else None

    def _search_uri(self, query: str, kind: str) -> "tuple[str, str]":
        """(uri, name) des ersten Treffers. kind in {playlist,track,album,artist}."""
        status, data = self._api(
            "GET", "/search", params={"q": query, "type": kind, "limit": 1}
        )
        block = (json.loads(data or b"{}") or {}).get(f"{kind}s", {})
        items = [it for it in block.get("items", []) if it]  # Spotify kann null-Items liefern
        if not items:
            raise SpotifyError(f"Nichts gefunden für «{query}».")
        return items[0].get("uri", ""), items[0].get("name", query)

    def play(self, query: Optional[str] = None, kind: str = "playlist") -> Optional[str]:
        """Ohne query: Wiedergabe fortsetzen. Mit query: ersten Treffer suchen und
        abspielen; liefert den Namen des gestarteten Titels/der Playlist."""
        if not query:
            self.resume()
            return None
        uri, name = self._search_uri(query, kind)
        # Tracks als uris-Liste, Sammlungen (playlist/album/artist) als Kontext.
        body = {"uris": [uri]} if kind == "track" else {"context_uri": uri}
        self._api("PUT", "/me/player/play", body=body)
        return name
