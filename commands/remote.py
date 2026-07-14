"""
Fernbedienungs-Commands (ADR-058): Bildschirm sperren, Lautstärke,
Medienwiedergabe, Ruhezustand - der PC vom Sofa oder von unterwegs aus
steuerbar, als wäre Jarvis die Fernbedienung.

Windows-first wie das übrige System: Lautstärke und Medien laufen über
die virtuellen Medientasten (keybd_event, stdlib/ctypes - kein neues
Paket), Sperren/Ruhezustand über die Windows-Bordmittel (rundll32).
Auf anderen Plattformen wird ehrlich abgelehnt bzw. das POSIX-Pendant
versucht - nichts wird stillschweigend simuliert.

Sicherheitsstufen (Handbook Kap. 10):
- lock_pc, set_volume, media_control: Stufe 1 - jederzeit umkehrbar
  (entsperren, Lautstärke zurückdrehen, Wiedergabe fortsetzen), keine
  Bestätigung nötig.
- sleep_pc: Stufe 2 (Ja/Nein) - der Rechner ist danach bis zum Wecken
  weg, aber anders als shutdown_pc (Stufe 3, exakte Phrase) per
  Tastendruck wieder da.
"""
from __future__ import annotations

import logging
import platform
import subprocess

from core.models import Plan, Result, Status

logger = logging.getLogger("jarvis.commands.remote")

# Virtuelle Tastencodes der Windows-Medientasten (WinUser.h). Jede
# Betätigung wirkt wie der Druck auf die physische Taste der Tastatur.
_VK_VOLUME_MUTE = 0xAD
_VK_VOLUME_DOWN = 0xAE
_VK_VOLUME_UP = 0xAF
_VK_MEDIA_NEXT = 0xB0
_VK_MEDIA_PREV = 0xB1
_VK_MEDIA_STOP = 0xB2
_VK_MEDIA_PLAY_PAUSE = 0xB3

_KEYEVENTF_KEYUP = 0x0002

# Ein Tastendruck ändert die Windows-Lautstärke um 2 % - fünf Drücke
# (±10 %) sind ein spürbarer, aber nicht erschreckender Schritt.
_VOLUME_TAPS = 5


def _tap_key(vk_code: int, times: int = 1) -> None:
    """Drückt eine virtuelle Taste n-mal (nur Windows). In Tests gemockt -
    es wird nie wirklich eine Taste ausgelöst."""
    import ctypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    for _ in range(times):
        user32.keybd_event(vk_code, 0, 0, 0)
        user32.keybd_event(vk_code, 0, _KEYEVENTF_KEYUP, 0)


def _direction_of(plan: Plan) -> str:
    """Richtung/Aktion aus dem Plan lesen: erst parameters, dann target.
    Kein Freitext wird weitergereicht - nur bekannte Wörter zählen."""
    raw = plan.parameters.get("direction") or plan.parameters.get("action") or plan.target or ""
    return str(raw).lower().strip().strip(".,!?")


class LockPcCommand:
    name = "lock_pc"
    description = (
        "Sperrt den Bildschirm/die Sitzung (Windows-Sperrbildschirm), z. B. "
        "'sperr den PC', 'sperr den Bildschirm', 'lock'. Sicherheitsstufe 1 - "
        "jederzeit per Anmeldung umkehrbar. Faehrt NICHTS herunter."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        if platform.system() == "Windows":
            command = ["rundll32.exe", "user32.dll,LockWorkStation"]
        else:
            command = ["loginctl", "lock-session"]
        try:
            subprocess.run(command, check=True)
        except (OSError, subprocess.CalledProcessError) as e:
            return Result(
                status=Status.FAILED,
                message=f"Den Bildschirm konnte ich nicht sperren: {e}",
            )
        return Result(status=Status.SUCCESS, message="Bildschirm gesperrt, Sir.")


# Richtungs-Synonyme -> kanonische Aktion. Bewusst eng: unbekannte Wörter
# führen zur Rückfrage, nie zu einer geratenen Aktion.
_VOLUME_ACTIONS = {
    "lauter": "up",
    "hoch": "up",
    "up": "up",
    "leiser": "down",
    "runter": "down",
    "down": "down",
    "stumm": "mute",
    "mute": "mute",
    "ton aus": "mute",
    "ton an": "mute",  # Mute-Taste ist ein Umschalter - gleiche Taste
    "laut": "up",
}


class SetVolumeCommand:
    name = "set_volume"
    description = (
        "Aendert die System-Lautstaerke: lauter, leiser oder stumm (Umschalter), "
        "z. B. 'mach lauter', 'leiser bitte', 'Ton aus'. Parameter 'direction': "
        "lauter/leiser/stumm. Sicherheitsstufe 1, sofort umkehrbar."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        direction = _VOLUME_ACTIONS.get(_direction_of(plan))
        if direction is None:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Soll ich lauter, leiser oder stumm schalten?",
            )
        if platform.system() != "Windows":
            return Result(
                status=Status.FAILED,
                message="Die Lautstärke steuern kann ich nur unter Windows.",
            )
        try:
            if direction == "mute":
                _tap_key(_VK_VOLUME_MUTE)
                return Result(status=Status.SUCCESS, message="Stummschaltung umgeschaltet.")
            vk = _VK_VOLUME_UP if direction == "up" else _VK_VOLUME_DOWN
            _tap_key(vk, times=_VOLUME_TAPS)
        except OSError as e:
            return Result(
                status=Status.FAILED,
                message=f"Die Lautstärke konnte ich nicht ändern: {e}",
            )
        word = "lauter" if direction == "up" else "leiser"
        return Result(status=Status.SUCCESS, message=f"Etwas {word}, Sir.")


_MEDIA_ACTIONS = {
    "play": ("play_pause", _VK_MEDIA_PLAY_PAUSE),
    "pause": ("play_pause", _VK_MEDIA_PLAY_PAUSE),
    "abspielen": ("play_pause", _VK_MEDIA_PLAY_PAUSE),
    "fortsetzen": ("play_pause", _VK_MEDIA_PLAY_PAUSE),
    "anhalten": ("play_pause", _VK_MEDIA_PLAY_PAUSE),
    "weiter": ("play_pause", _VK_MEDIA_PLAY_PAUSE),
    "next": ("next", _VK_MEDIA_NEXT),
    "naechster": ("next", _VK_MEDIA_NEXT),
    "nächster": ("next", _VK_MEDIA_NEXT),
    "nächstes": ("next", _VK_MEDIA_NEXT),
    "naechstes": ("next", _VK_MEDIA_NEXT),
    "skip": ("next", _VK_MEDIA_NEXT),
    "ueberspringen": ("next", _VK_MEDIA_NEXT),
    "überspringen": ("next", _VK_MEDIA_NEXT),
    "previous": ("previous", _VK_MEDIA_PREV),
    "zurueck": ("previous", _VK_MEDIA_PREV),
    "zurück": ("previous", _VK_MEDIA_PREV),
    "vorheriger": ("previous", _VK_MEDIA_PREV),
    "vorheriges": ("previous", _VK_MEDIA_PREV),
    "stop": ("stop", _VK_MEDIA_STOP),
    "stopp": ("stop", _VK_MEDIA_STOP),
}

_MEDIA_REPLIES = {
    "play_pause": "Wiedergabe umgeschaltet.",
    "next": "Nächster Titel.",
    "previous": "Vorheriger Titel.",
    "stop": "Wiedergabe gestoppt.",
}


class MediaControlCommand:
    name = "media_control"
    description = (
        "Steuert die Medienwiedergabe des PCs wie eine Fernbedienung: Play/Pause "
        "(Umschalter), naechster/vorheriger Titel, Stopp - z. B. 'Musik pause', "
        "'naechstes Lied', 'Wiedergabe stopp'. Parameter 'action': "
        "play/pause/naechster/vorheriger/stopp. Sicherheitsstufe 1."
    )
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        entry = _MEDIA_ACTIONS.get(_direction_of(plan))
        if entry is None:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Was soll ich mit der Wiedergabe tun - Play/Pause, nächster, vorheriger oder Stopp?",
            )
        if platform.system() != "Windows":
            return Result(
                status=Status.FAILED,
                message="Die Medienwiedergabe steuern kann ich nur unter Windows.",
            )
        action, vk = entry
        try:
            _tap_key(vk)
        except OSError as e:
            return Result(
                status=Status.FAILED,
                message=f"Die Medientaste konnte ich nicht auslösen: {e}",
            )
        return Result(status=Status.SUCCESS, message=_MEDIA_REPLIES[action])


class SleepPcCommand:
    name = "sleep_pc"
    description = (
        "Versetzt den PC in den Ruhezustand/Energiesparmodus (per Tastendruck "
        "weckbar), z. B. 'schick den PC schlafen', 'Ruhezustand'. Klar abzugrenzen "
        "von shutdown_pc (Rechner AUSschalten) und stop_runtime (nur Jarvis "
        "beenden). Sicherheitsstufe 2 - einfache Ja/Nein-Bestaetigung."
    )
    # Stufe 2 (Handbook Kap. 10): folgenreich (Rechner ist bis zum Wecken
    # weg), aber anders als shutdown_pc umkehrbar - Ja/Nein genügt, keine
    # exakte Phrase.
    requires_confirmation = True

    def execute(self, plan: Plan) -> Result:
        if not plan.parameters.get("confirmed"):
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Soll ich den PC wirklich in den Ruhezustand versetzen? Bitte bestätige das.",
            )
        if platform.system() == "Windows":
            # SetSuspendState nutzt den Ruhezustand (Hibernate), falls er
            # aktiviert ist, sonst Standby - beides per Tastendruck weckbar.
            command = ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]
        else:
            command = ["systemctl", "suspend"]
        try:
            subprocess.run(command, check=True)
        except (OSError, subprocess.CalledProcessError) as e:
            return Result(
                status=Status.FAILED,
                message=f"Den Ruhezustand konnte ich nicht auslösen: {e}",
            )
        return Result(
            status=Status.SUCCESS,
            message="In Ordnung. Der PC geht jetzt in den Ruhezustand - wecken per Tastendruck.",
        )


COMMANDS = [LockPcCommand(), SetVolumeCommand(), MediaControlCommand(), SleepPcCommand()]
