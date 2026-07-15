"""Tests fuer core/spotify.py (Client, HTTP-Schicht injiziert) und
commands/spotify.py (Fake-Client) - ADR-058. Kein Netzwerk, kein echter
Account."""
from __future__ import annotations

import json

import pytest

import commands.spotify as spotify_commands
from core.models import Plan, Status
from core.spotify import (
    NoActiveDeviceError,
    SpotifyAuthError,
    SpotifyClient,
    SpotifyError,
)

_TOKEN_OK = (200, json.dumps({"access_token": "tok", "expires_in": 3600}).encode())


class FakeHttp:
    """Injizierbare HTTP-Schicht: matcht (Methode, Substring-in-URL) in
    Einfuege-Reihenfolge auf eine (status, bytes)-Antwort; sonst Default."""

    def __init__(self):
        self.calls = []
        self._rules = []
        self.default = (200, b"")

    def when(self, method, needle, status, body=b""):
        self._rules.append((method, needle, (status, body if isinstance(body, bytes) else body.encode())))
        return self

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        for m, needle, resp in self._rules:
            if m == method and needle in url:
                return resp
        return self.default

    def urls(self, method=None):
        return [u for (m, u, _h, _b) in self.calls if method is None or m == method]


def _client(http):
    http.when("POST", "accounts.spotify.com/api/token", *_TOKEN_OK)
    return SpotifyClient("cid", "secret", "refresh", http=http)


# --- Auth / Token -----------------------------------------------------------

def test_token_is_fetched_and_cached():
    http = FakeHttp()
    c = _client(http)
    c.pause()
    c.next()
    token_posts = [u for u in http.urls("POST") if "accounts.spotify.com/api/token" in u]
    assert len(token_posts) == 1  # zweimal API, aber nur EINMAL Token geholt (Cache)


def test_bad_refresh_token_raises_auth_error():
    http = FakeHttp()
    http.when("POST", "accounts.spotify.com/api/token", 400, b'{"error":"invalid_grant"}')
    c = SpotifyClient("cid", "secret", "bad", http=http)
    with pytest.raises(SpotifyAuthError):
        c.pause()


# --- Player-Aktionen --------------------------------------------------------

def test_now_playing_parses_title_and_artist():
    http = FakeHttp()
    body = json.dumps({"item": {"name": "Yesterday",
                                "artists": [{"name": "The Beatles"}]}}).encode()
    http.when("GET", "/me/player/currently-playing", 200, body)
    now = _client(http).now_playing()
    assert now == {"title": "Yesterday", "artist": "The Beatles"}


def test_now_playing_returns_none_when_nothing_plays():
    http = FakeHttp()
    http.when("GET", "/me/player/currently-playing", 204, b"")
    assert _client(http).now_playing() is None


def test_pause_next_previous_hit_right_endpoints():
    http = FakeHttp()
    c = _client(http)
    c.pause(); c.next(); c.previous()
    assert any(m == "PUT" and "/me/player/pause" in u for (m, u, _h, _b) in http.calls)
    assert any(m == "POST" and "/me/player/next" in u for (m, u, _h, _b) in http.calls)
    assert any(m == "POST" and "/me/player/previous" in u for (m, u, _h, _b) in http.calls)


def test_set_volume_clamps_to_0_100():
    http = FakeHttp()
    c = _client(http)
    assert c.set_volume(150) == 100
    assert c.set_volume(-5) == 0
    assert any("volume_percent=100" in u for u in http.urls("PUT"))


def test_current_volume_reads_device():
    http = FakeHttp()
    http.when("GET", "/me/player", 200, json.dumps({"device": {"volume_percent": 42}}).encode())
    assert _client(http).current_volume() == 42


def test_play_without_query_resumes():
    http = FakeHttp()
    c = _client(http)
    assert c.play() is None
    assert any(m == "PUT" and u.endswith("/me/player/play") for (m, u, _h, _b) in http.calls)


def test_play_with_query_searches_then_starts_context():
    http = FakeHttp()
    search_body = json.dumps({"playlists": {"items": [
        {"uri": "spotify:playlist:42", "name": "Fokus"}]}}).encode()
    http.when("GET", "/search", 200, search_body)
    c = _client(http)
    name = c.play(query="Fokus", kind="playlist")
    assert name == "Fokus"
    # Der Play-Aufruf traegt den Kontext (Playlist) im Body.
    play_calls = [(m, u, b) for (m, u, _h, b) in http.calls if "/me/player/play" in u]
    assert play_calls and b"spotify:playlist:42" in play_calls[-1][2]
    assert b"context_uri" in play_calls[-1][2]


def test_play_track_uses_uris_list():
    http = FakeHttp()
    search_body = json.dumps({"tracks": {"items": [
        {"uri": "spotify:track:99", "name": "Song"}]}}).encode()
    http.when("GET", "/search", 200, search_body)
    c = _client(http)
    c.play(query="Song", kind="track")
    play_body = [b for (m, u, _h, b) in http.calls if "/me/player/play" in u][-1]
    assert b'"uris"' in play_body and b"spotify:track:99" in play_body


def test_no_active_device_raises():
    http = FakeHttp()
    http.when("PUT", "/me/player/play", 404, b'{"error":{"reason":"NO_ACTIVE_DEVICE"}}')
    with pytest.raises(NoActiveDeviceError):
        _client(http).resume()


def test_403_maps_to_spotify_error():
    http = FakeHttp()
    http.when("POST", "/me/player/next", 403, b'{"error":"forbidden"}')
    with pytest.raises(SpotifyError):
        _client(http).next()


# --- Commands (Fake-Client) -------------------------------------------------

class FakeClient:
    def __init__(self, **behaviour):
        self.b = behaviour
        self.calls = []

    def _maybe_raise(self, name):
        exc = self.b.get(f"{name}_raises")
        if exc:
            raise exc

    def now_playing(self):
        self.calls.append("now_playing"); self._maybe_raise("now_playing")
        return self.b.get("now_playing")

    def pause(self):
        self.calls.append("pause"); self._maybe_raise("pause")

    def resume(self):
        self.calls.append("resume"); self._maybe_raise("resume")

    def next(self):
        self.calls.append("next"); self._maybe_raise("next")

    def previous(self):
        self.calls.append("previous"); self._maybe_raise("previous")

    def set_volume(self, p):
        self.calls.append(("set_volume", p)); self._maybe_raise("set_volume")
        return max(0, min(int(p), 100))

    def current_volume(self):
        self.calls.append("current_volume"); return self.b.get("current_volume")

    def play(self, query=None, kind="playlist"):
        self.calls.append(("play", query, kind)); self._maybe_raise("play")
        return self.b.get("play_name")

    def playback(self):
        self.calls.append("playback"); self._maybe_raise("playback")
        return self.b.get("playback")


def test_commands_not_ready_without_client():
    spotify_commands.configure(config=None, client=None)
    # unkonfiguriert -> jede Aktion meldet ehrlich "nicht eingerichtet"
    r = spotify_commands.SpotifyPauseCommand().execute(Plan(intent="spotify_pause"))
    assert r.status == Status.NEEDS_CLARIFICATION
    assert "nicht" in r.message.lower() and "eingerichtet" in r.message.lower()


def test_pause_success():
    fake = FakeClient()
    spotify_commands.configure(config=None, client=fake)
    r = spotify_commands.SpotifyPauseCommand().execute(Plan(intent="spotify_pause"))
    assert r.status == Status.SUCCESS
    assert "pause" in fake.calls


def test_now_playing_success_and_empty():
    spotify_commands.configure(config=None, client=FakeClient(now_playing={"title": "X", "artist": "Y"}))
    r = spotify_commands.SpotifyNowPlayingCommand().execute(Plan(intent="spotify_now_playing"))
    assert r.status == Status.SUCCESS and "X" in r.message and "Y" in r.message

    spotify_commands.configure(config=None, client=FakeClient(now_playing=None))
    r2 = spotify_commands.SpotifyNowPlayingCommand().execute(Plan(intent="spotify_now_playing"))
    assert r2.status == Status.SUCCESS and "nichts" in r2.message.lower()


def test_play_named_playlist():
    fake = FakeClient(play_name="Fokus")
    spotify_commands.configure(config=None, client=fake)
    r = spotify_commands.SpotifyPlayCommand().execute(
        Plan(intent="spotify_play", target="Fokus"))
    assert r.status == Status.SUCCESS and "Fokus" in r.message
    assert ("play", "Fokus", "playlist") in fake.calls


def test_volume_relative_up_uses_current():
    fake = FakeClient(current_volume=40)
    spotify_commands.configure(config=None, client=fake)
    r = spotify_commands.SpotifyVolumeCommand().execute(
        Plan(intent="spotify_volume", raw_input="mach lauter"))
    assert r.status == Status.SUCCESS
    assert ("set_volume", 50) in fake.calls  # 40 + 10


def test_volume_absolute_level():
    fake = FakeClient()
    spotify_commands.configure(config=None, client=fake)
    r = spotify_commands.SpotifyVolumeCommand().execute(
        Plan(intent="spotify_volume", parameters={"level": 30}))
    assert r.status == Status.SUCCESS
    assert ("set_volume", 30) in fake.calls


def test_no_active_device_is_friendly():
    fake = FakeClient(next_raises=NoActiveDeviceError("x"))
    spotify_commands.configure(config=None, client=fake)
    r = spotify_commands.SpotifyNextCommand().execute(Plan(intent="spotify_next"))
    assert r.status == Status.FAILED
    assert "gerät" in r.message.lower() or "geraet" in r.message.lower()


# --- Kachel-Zustand: playback() + now_playing_state() (ADR-058) --------------

def test_playback_includes_is_playing():
    http = FakeHttp()
    body = json.dumps({"is_playing": True,
                       "item": {"name": "S", "artists": [{"name": "A"}]}}).encode()
    http.when("GET", "/me/player/currently-playing", 200, body)
    assert _client(http).playback() == {"title": "S", "artist": "A", "is_playing": True}


def test_now_playing_state_not_configured():
    spotify_commands.configure(config=None, client=None)
    assert spotify_commands.now_playing_state() == {"configured": False, "playing": False}


def test_now_playing_state_reports_track():
    spotify_commands.configure(
        config=None,
        client=FakeClient(playback={"title": "S", "artist": "A", "is_playing": True}))
    assert spotify_commands.now_playing_state() == {
        "configured": True, "playing": True, "title": "S", "artist": "A"}


def test_now_playing_state_failsafe_on_error():
    spotify_commands.configure(config=None, client=FakeClient(playback_raises=SpotifyError("boom")))
    assert spotify_commands.now_playing_state() == {"configured": True, "playing": False}
