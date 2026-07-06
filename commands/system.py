"""
System-Commands: Programme oeffnen, PC herunterfahren, etc.

Jeder Command prueft selbst seine Voraussetzungen (Existiert das
Programm? Ist Bestaetigung noetig?), bevor er etwas ausfuehrt.
Jarvis fuehrt nie "blind" etwas aus.
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess

from core.models import Plan, Result, Status

logger = logging.getLogger("jarvis.commands.system")

# Bekannte Programme -> tatsaechlicher ausfuehrbarer Name.
# Kein Freitext direkt an subprocess/os.startfile durchreichen.
KNOWN_PROGRAMS = {
    "excel": "EXCEL.EXE" if platform.system() == "Windows" else "excel",
    "notepad": "notepad" if platform.system() == "Windows" else "gedit",
    "browser": "chrome.exe" if platform.system() == "Windows" else "firefox",
}


class OpenProgramCommand:
    name = "open_program"
    description = "Oeffnet ein bekanntes Programm (z. B. Excel, Notepad, Browser)."
    # Unkritische Aktion (Sicherheitsstufe 1) - keine Bestaetigung noetig.
    requires_confirmation = False

    def execute(self, plan: Plan) -> Result:
        target = (plan.target or "").lower().strip()

        if not target:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Welches Programm soll ich für dich öffnen?",
            )

        executable = KNOWN_PROGRAMS.get(target, target)

        if platform.system() == "Windows":
            return self._open_windows(plan.target, executable)
        return self._open_posix(plan.target, executable)

    def _open_windows(self, display_name: str, executable: str) -> Result:
        # os.startfile loest genauso auf wie das Startmenue/der
        # Ausfuehren-Dialog (u. a. ueber die "App Paths"-Registry).
        # shutil.which prueft NUR den PATH - dort steht z. B. Excel bei
        # den meisten Installationen nicht drin, obwohl es vorhanden
        # ist. Lessons Learned siehe docs/logbook.md (2026-07-01).
        try:
            os.startfile(executable)  # type: ignore[attr-defined]
        except OSError as e:
            return Result(
                status=Status.FAILED,
                message=f"{display_name} konnte ich nicht finden oder starten: {e}",
            )
        return Result(status=Status.SUCCESS, message=f"Ich habe {display_name} geöffnet.")

    def _open_posix(self, display_name: str, executable: str) -> Result:
        if shutil.which(executable) is None:
            return Result(
                status=Status.FAILED,
                message=f"{display_name} konnte ich nicht finden.",
            )
        try:
            subprocess.Popen([executable])
        except OSError as e:
            return Result(
                status=Status.FAILED,
                message=f"{display_name} konnte ich nicht starten: {e}",
            )
        return Result(status=Status.SUCCESS, message=f"Ich habe {display_name} geöffnet.")


class ShutdownPcCommand:
    name = "shutdown_pc"
    description = "Faehrt den PC herunter (kritisch - nur bei eindeutiger, expliziter Aufforderung)."
    # Kritische Aktion, Sicherheitsstufe 3 (Handbook Kap. 10): braucht
    # mehrfache/eindeutige Bestaetigung, nicht nur ein einfaches "ja".
    # Der Executor verlangt deshalb das exakte Eintippen von
    # confirmation_phrase statt eines simplen Ja/Nein.
    requires_confirmation = True
    confirmation_phrase = "HERUNTERFAHREN"

    def execute(self, plan: Plan) -> Result:
        # Destruktive Aktion -> erfordert explizite Bestaetigung.
        # main.py/Executor muessen parameters["confirmed"] erst
        # ueber eine Rueckfrage an den Nutzer einholen.
        if not plan.parameters.get("confirmed"):
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Soll ich den PC wirklich herunterfahren? Bitte bestätige das.",
            )

        system_name = platform.system()
        try:
            if system_name == "Windows":
                subprocess.run(["shutdown", "/s", "/t", "0"], check=True)
            else:
                subprocess.run(["shutdown", "-h", "now"], check=True)
        except (subprocess.CalledProcessError, PermissionError) as e:
            return Result(
                status=Status.FAILED,
                message=f"Dafür brauche ich Administratorrechte, oder es ist ein Fehler aufgetreten: {e}",
            )

        return Result(status=Status.SUCCESS, message="In Ordnung. Der PC wird jetzt heruntergefahren.")


# Registrierungspunkt fuer dieses Modul - commands/__init__.py liest
# diese Liste beim Start ein. Neuer Command = neue Klasse + Eintrag hier.
COMMANDS = [OpenProgramCommand(), ShutdownPcCommand()]
