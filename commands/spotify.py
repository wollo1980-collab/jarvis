"""
Spotify-Sprachbefehle (ADR-058) - steuern die EIGENE Wiedergabe des Nutzers
ueber core/spotify.py: abspielen/fortsetzen, pausieren, naechster/vorheriger
Titel, Lautstaerke, "was laeuft gerade?". Braucht Spotify Premium + ein aktives
Geraet (Spotify laeuft irgendwo).

Sicherheitsstufe 0: reversibel, folgenlos (steuert nur die eigene Musik) -
KEINE Bestaetigung noetig, anders als nach-aussen-Aktionen.

configure()-Muster wie commands/weather.py: einmal beim Start aufgerufen; der
Client wird aus der Config gebaut (fehlen Credentials -> None -> die Befehle
antworten ehrlich "nicht eingerichtet"). Fuer Tests ist der Client injizierbar.
"""
from __future__ import annotations

import logging

from core.models import Plan, Result, Status
from core.spotify import (
    NoActiveDeviceError,
    SpotifyAuthError,
    SpotifyClient,
    SpotifyError,
)

logger = logging.getLogger("jarvis.commands.spotify")

_client = None
_configured = False

_VOLUME_STEP = 10  # Prozentpunkte je "lauter"/"leiser"
_DEFAULT_VOLUME = 50  # Startwert, falls die Ist-Lautstaerke nicht zu ermitteln ist


def configure(config, client=None) -> None:
    """Beim Start aufgerufen. Baut den SpotifyClient aus der Config, wenn alle
    drei Credentials da sind; sonst None (fail-closed -> Befehle melden "nicht
    eingerichtet"). client injizierbar fuer Tests."""
    global _client, _configured
    if client is not None:
        _client = client
    elif (getattr(config, "spotify_client_id", "") and
          getattr(config, "spotify_client_secret", "") and
          getattr(config, "spotify_refresh_token", "")):
        _client = SpotifyClient(
            config.spotify_client_id,
            config.spotify_client_secret,
            config.spotify_refresh_token,
        )
    else:
        _client = None
    _configured = True


def now_playing_state() -> dict:
    """Read-only Zustand fuer die UI-Kachel (BrowserChannel GET /spotify/now):
    {'configured','playing','title','artist'}. Fail-safe: wirft nie - eine
    stockende Kachel darf den Kanal nie stoeren."""
    if not _configured or _client is None:
        return {"configured": False, "playing": False}
    try:
        now = _client.playback()
    except Exception:  # noqa: BLE001 - Kachel-Read ist Beiwerk
        logger.debug("Spotify-Zustand nicht abrufbar.", exc_info=True)
        return {"configured": True, "playing": False}
    if not now:
        return {"configured": True, "playing": False}
    return {
        "configured": True,
        "playing": bool(now.get("is_playing")),
        "title": now.get("title", ""),
        "artist": now.get("artist", ""),
    }


def _not_ready() -> Result:
    return Result(
        status=Status.NEEDS_CLARIFICATION,
        message=(
            "Spotify ist noch nicht eingerichtet, Sir. In config.json brauche ich "
            "spotify_client_id, spotify_client_secret und spotify_refresh_token "
            "(Letzteren liefert scripts/spotify_auth.py)."
        ),
    )


def _translate_error(e: Exception) -> str:
    """Uebersetzt Connector-Fehler in eine Jarvis-Antwort im Klartext."""
    if isinstance(e, NoActiveDeviceError):
        return "Ich finde kein aktives Spotify-Gerät, Sir - starten Sie Spotify irgendwo, dann dirigiere ich."
    if isinstance(e, SpotifyAuthError):
        return "Die Spotify-Verbindung ist abgelaufen oder ungültig - eine Neu-Einrichtung wäre nötig."
    if isinstance(e, SpotifyError):
        return f"Spotify spielt gerade nicht mit, Sir: {e}"
    logger.exception("Unerwarteter Spotify-Fehler.")
    return "Bei Spotify ist etwas schiefgelaufen, Sir."


def _guard(action) -> Result:
    """Fuehrt eine Client-Aktion aus und faengt alle Connector-Fehler ab.
    action() liefert die Erfolgsmeldung (str) ODER ein fertiges Result."""
    if not _configured or _client is None:
        return _not_ready()
    try:
        outcome = action()
    except Exception as e:  # noqa: BLE001 - in Klartext uebersetzt, nie werfend
        return Result(status=Status.FAILED, message=_translate_error(e))
    if isinstance(outcome, Result):
        return outcome
    return Result(status=Status.SUCCESS, message=outcome)


class SpotifyPlayCommand:
    name = "spotify_play"
    description = (
        "Startet die Musik oder setzt sie fort (z. B. 'spiel Musik', 'weiter', "
        "'mach Musik an', 'spiel die Playlist Fokus', 'spiel den Song Yesterday'). "
        "target = optionaler Name einer Playlist/eines Songs; parameters.kind = "
        "'playlist' oder 'track' (Default playlist). Spotify Premium + aktives Geraet."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        query = str(plan.target or plan.parameters.get("query") or "").strip()
        kind = str(plan.parameters.get("kind") or "playlist").strip().lower()
        if kind not in ("playlist", "track", "album", "artist"):
            kind = "playlist"

        def act():
            started = _client.play(query=query or None, kind=kind)
            if started:
                return f"Ich spiele «{started}», Sir."
            return "Wiedergabe fortgesetzt, Sir."

        return _guard(act)


class SpotifyPauseCommand:
    name = "spotify_pause"
    description = (
        "Pausiert die Musik ('pause', 'stopp die Musik', 'Musik aus', 'halt an'). "
        "Bezieht sich auf die Spotify-Wiedergabe."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        return _guard(lambda: (_client.pause(), "Pausiert, Sir.")[1])


class SpotifyNextCommand:
    name = "spotify_next"
    description = "Spielt den naechsten Titel ('naechstes Lied', 'skip', 'weiter zum naechsten Song')."
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        return _guard(lambda: (_client.next(), "Weiter zum nächsten Titel, Sir.")[1])


class SpotifyPreviousCommand:
    name = "spotify_previous"
    description = "Spielt den vorherigen Titel ('zurueck', 'letztes Lied', 'vorheriger Song')."
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        return _guard(lambda: (_client.previous(), "Zurück zum vorherigen Titel, Sir.")[1])


class SpotifyNowPlayingCommand:
    name = "spotify_now_playing"
    description = (
        "Sagt an, was gerade laeuft ('was laeuft gerade?', 'welcher Song ist das?', "
        "'wie heisst das Lied?'). Read-only."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        def act():
            now = _client.now_playing()
            if not now:
                return "Gerade läuft nichts, Sir."
            artist = f" von {now['artist']}" if now.get("artist") else ""
            return f"Es läuft «{now['title']}»{artist}, Sir."

        return _guard(act)


class SpotifyVolumeCommand:
    name = "spotify_volume"
    description = (
        "Stellt die Lautstaerke der Musik ('lauter', 'leiser', 'Lautstaerke auf 50', "
        "'Musik lauter'). parameters.level = 0-100 (absolut) ODER parameters.direction "
        "= 'up'/'down' (relativ)."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        level = plan.parameters.get("level")
        direction = str(plan.parameters.get("direction") or "").strip().lower()
        raw = (plan.raw_input or "").lower()
        if not direction and level is None:
            if any(w in raw for w in ("lauter", "louder", "hoch")):
                direction = "up"
            elif any(w in raw for w in ("leiser", "quieter", "runter")):
                direction = "down"

        def act():
            if level is not None:
                try:
                    target = int(level)
                except (TypeError, ValueError):
                    return Result(status=Status.NEEDS_CLARIFICATION,
                                  message="Auf welchen Wert soll ich die Lautstärke stellen, Sir? (0 bis 100)")
                return f"Lautstärke auf {_client.set_volume(target)} Prozent, Sir."
            if direction in ("up", "down"):
                current = _client.current_volume()
                base = current if current is not None else _DEFAULT_VOLUME
                target = base + (_VOLUME_STEP if direction == "up" else -_VOLUME_STEP)
                return f"Lautstärke auf {_client.set_volume(target)} Prozent, Sir."
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Lauter oder leiser, Sir - oder ein Wert von 0 bis 100?",
            )

        return _guard(act)


COMMANDS = [
    SpotifyPlayCommand(),
    SpotifyPauseCommand(),
    SpotifyNextCommand(),
    SpotifyPreviousCommand(),
    SpotifyNowPlayingCommand(),
    SpotifyVolumeCommand(),
]
