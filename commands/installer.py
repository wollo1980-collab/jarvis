"""
System-Installation: installiert Programme über winget (Windows
Package Manager) - Sicherheitsstufe 2 (Handbook Kap. 10): Bestätigung
erforderlich, aber (anders als shutdown_pc/Stufe 3) reicht ein
einfaches Ja/Nein, keine exakte Bestätigungsphrase.

winget ist Windows-exklusiv - bewusst kein Posix-Fallback wie bei
OpenProgramCommand, das Handbook (Kap. 17) nennt winget explizit als
das Werkzeug für diese Fähigkeit. "Deinstallieren" ist NICHT enthalten
- Kap. 27 grenzt die v0.4-Priorisierung explizit auf "installieren"
ein, siehe ADR-012.
"""
from __future__ import annotations

import logging
import platform
import shutil
import subprocess

from core.models import Plan, Result, Status

logger = logging.getLogger("jarvis.commands.installer")

# Bekannte Programme -> exakte winget Package-ID. "-e" (exact match)
# vermeidet Mehrdeutigkeiten bei der Namenssuche (mehrere Treffer
# lassen winget sonst ohne -e fehlschlagen). Unbekannte Ziele werden
# als Freitext-Suchbegriff durchgereicht (Best-Effort, wie winget es
# auch über die Kommandozeile anbietet).
KNOWN_PACKAGES = {
    "vlc": "VideoLAN.VLC",
    "7zip": "7zip.7zip",
    "firefox": "Mozilla.Firefox",
    "chrome": "Google.Chrome",
    "notepad++": "Notepad++.Notepad++",
}

# winget-Installationen (Download + Setup) können mehrere Minuten
# dauern - benannte, dokumentierte Konstante statt Magic Value direkt
# in subprocess.run (Handbook Kap. 5: keine Magic Values).
_INSTALL_TIMEOUT_SECONDS = 300


class InstallProgramCommand:
    name = "install_program"
    description = (
        "Installiert ein Programm über winget, z. B. VLC oder 7-Zip "
        "(Systemänderung, Sicherheitsstufe 2 - Bestätigung erforderlich)."
    )
    # Systemänderung (Sicherheitsstufe 2) - einfaches Ja/Nein reicht,
    # kein confirmation_phrase (das ist Stufe 3, siehe ShutdownPcCommand).
    requires_confirmation = True

    def execute(self, plan: Plan) -> Result:
        target = (plan.target or "").strip()
        if not target:
            return Result(
                status=Status.NEEDS_CLARIFICATION,
                message="Welches Programm soll ich installieren?",
            )

        if platform.system() != "Windows":
            return Result(
                status=Status.FAILED,
                message="Programme installieren funktioniert aktuell nur unter Windows (winget).",
            )

        if shutil.which("winget") is None:
            return Result(
                status=Status.FAILED,
                message=(
                    "winget ist nicht verfügbar - bitte den 'App Installer' "
                    "aus dem Microsoft Store installieren."
                ),
            )

        package_id = KNOWN_PACKAGES.get(target.lower())
        if package_id:
            cmd = [
                "winget", "install", "--id", package_id, "-e",
                "--accept-package-agreements", "--accept-source-agreements",
            ]
        else:
            cmd = [
                "winget", "install", target,
                "--accept-package-agreements", "--accept-source-agreements",
            ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_INSTALL_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return Result(
                status=Status.FAILED,
                message=(
                    f"Installation von {target} hat das Zeitlimit "
                    f"({_INSTALL_TIMEOUT_SECONDS}s) überschritten."
                ),
            )
        except OSError as e:
            return Result(status=Status.FAILED, message=f"winget konnte nicht gestartet werden: {e}")

        if proc.returncode != 0:
            detail_lines = (proc.stderr or proc.stdout or "").strip().splitlines()
            last_line = detail_lines[-1] if detail_lines else f"Exit-Code {proc.returncode}"
            return Result(
                status=Status.FAILED,
                message=f"{target} konnte nicht installiert werden: {last_line}",
            )

        return Result(status=Status.SUCCESS, message=f"{target} wurde installiert.")


# Registrierungspunkt für dieses Modul - commands/__init__.py liest
# diese Liste beim Start ein.
COMMANDS = [InstallProgramCommand()]
