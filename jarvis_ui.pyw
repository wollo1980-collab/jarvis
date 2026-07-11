"""
Jarvis-Starter (.pyw = ohne Konsolenfenster, PO-Wunsch 10.07.2026:
"beides ueber einen Start"): EIN Doppelklick prueft und startet alles -
1. die Jarvis-RUNTIME (unsichtbar, pythonw), falls sie nicht laeuft
   (Erkennung ueber die Lock-Datei, ADR-026 - kein Doppelstart moeglich),
2. den Dashboard-SERVER (unsichtbar), falls er nicht laeuft,
3. und oeffnet Jarvis als EIGENES Fenster im Browser-App-Modus (ohne
   Tabs/Adressleiste) - Chrome oder Edge, sonst Standard-Browser.

Laeuft bereits alles, oeffnet sich einfach nur das Fenster. Die Prozesse
bleiben nach dem Schliessen des Fensters aktiv ("Jarvis, beende dich"
stoppt die Runtime; Dashboard-Server bei Bedarf per Task-Manager).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8765/"

_BROWSER_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


def server_running() -> bool:
    try:
        with urllib.request.urlopen(URL + "api/status", timeout=1.5):
            return True
    except Exception:  # noqa: BLE001
        return False


def runtime_running() -> bool:
    """Lock-Datei-Logik aus core/dashboard_data (unlesbar = aktiv gesperrt =
    laeuft). Fail-safe True bei Import-Problemen - lieber nicht doppelt
    starten (der Lock wuerde den Doppelstart ohnehin abfangen)."""
    try:
        sys.path.insert(0, str(BASE_DIR))
        from core.config import Config
        from core.dashboard_data import runtime_status

        return bool(runtime_status(Config.load().memory_dir)["running"])
    except Exception:  # noqa: BLE001
        return True


def _spawn_hidden(script: str, *args: str) -> None:
    pythonw = BASE_DIR / ".venv" / "Scripts" / "pythonw.exe"
    subprocess.Popen(
        [str(pythonw), str(BASE_DIR / script), *args],
        cwd=str(BASE_DIR),
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )


def start_server() -> None:
    _spawn_hidden("dashboard.py", "--no-browser")


def start_runtime() -> None:
    _spawn_hidden("jarvis_runtime.py")


def _window_flags() -> list[str]:
    """Fenster-Modus aus der Config (PO-Wunsch 2026-07-10 "Vollbild als
    Einstellung"): fullscreen (F11 verlaesst es) / maximized / normal.
    Fail-safe normal - das Fenster bleibt in jedem Modus verschiebbar."""
    mode = "normal"
    try:
        sys.path.insert(0, str(BASE_DIR))
        from core.config import Config

        mode = str(Config.load().ui_window).strip().lower()
    except Exception:  # noqa: BLE001 - Starter darf nie an der Config sterben
        pass
    if mode == "fullscreen":
        return ["--start-fullscreen"]
    if mode == "maximized":
        return ["--start-maximized"]
    return ["--window-size=1150,900"]


def open_app_window() -> None:
    for candidate in _BROWSER_CANDIDATES:
        if os.path.exists(candidate):
            subprocess.Popen([candidate, f"--app={URL}", *_window_flags()])
            return
    webbrowser.open(URL)  # Rueckfall: normaler Tab


def main() -> None:
    if not runtime_running():
        start_runtime()  # nicht warten - das UI zeigt den Hochlauf live
    if not server_running():
        start_server()
        for _ in range(20):  # bis ~5 s auf den Server warten
            time.sleep(0.25)
            if server_running():
                break
    open_app_window()


if __name__ == "__main__":
    sys.exit(main())
