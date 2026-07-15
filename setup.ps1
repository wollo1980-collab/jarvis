# Jarvis-Einrichtung (Schaufenster Phase 2) - ein Skript statt fuenf Schritte.
# Aufruf:  powershell -ExecutionPolicy Bypass -File setup.ps1
# Macht: venv anlegen -> Pakete installieren -> config.json aus der Vorlage
# anlegen (falls noch keine existiert) -> naechste Schritte erklaeren.
# Schreibt NIEMALS Secrets - der OpenAI-Key gehoert in die Umgebungsvariable.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repo

Write-Host ""
Write-Host "  J A R V I S  -  Einrichtung" -ForegroundColor Cyan
Write-Host "  ---------------------------"

# 1. Python finden (3.11+; entwickelt und getestet mit 3.13)
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "  [FEHLER] Python nicht gefunden - bitte Python 3.11+ von python.org installieren." -ForegroundColor Red
    exit 1
}
$version = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
Write-Host "  [1/4] Python $version gefunden."

# 2. venv anlegen (idempotent)
if (-not (Test-Path "$repo\.venv")) {
    Write-Host "  [2/4] Lege virtuelle Umgebung an (.venv) ..."
    & python -m venv "$repo\.venv"
} else {
    Write-Host "  [2/4] Virtuelle Umgebung existiert bereits."
}

# 3. Pakete installieren - REPRODUZIERBAR: der Laufzeit-Stack
#    (requirements-runtime.txt) wird ueber requirements.lock auf die
#    erprobten Versionen gepinnt (Constraints installieren nichts extra,
#    sie fixieren nur). Dev-Werkzeuge (pytest/ruff) bleiben draussen -
#    Entwickler nehmen requirements-dev.txt (siehe README).
Write-Host "  [3/4] Installiere Pakete (runtime, gepinnt via requirements.lock) - dauert einen Moment ..."
& "$repo\.venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& "$repo\.venv\Scripts\python.exe" -m pip install --quiet -r "$repo\requirements-runtime.txt" -c "$repo\requirements.lock"

# 4. config.json aus der Vorlage (niemals eine bestehende ueberschreiben)
if (-not (Test-Path "$repo\config.json")) {
    Copy-Item "$repo\config.example.json" "$repo\config.json"
    Write-Host "  [4/4] config.json aus der Vorlage angelegt."
} else {
    Write-Host "  [4/4] config.json existiert bereits - unangetastet."
}

Write-Host ""
Write-Host "  Fertig. Noch zwei Handgriffe:" -ForegroundColor Green
Write-Host ""
Write-Host "  1. OpenAI-API-Key als Umgebungsvariable setzen (NIE in config.json):"
Write-Host '       setx OPENAI_API_KEY "sk-..."' -ForegroundColor Yellow
Write-Host "     (neues Terminal oeffnen, damit die Variable greift)"
Write-Host ""
Write-Host "  2. Jarvis starten:"
Write-Host "       .venv\Scripts\pythonw.exe jarvis_ui.pyw" -ForegroundColor Yellow
Write-Host "     (startet Runtime + UI-Fenster; Konsole: python main.py)"
Write-Host ""
Write-Host "  Optional: Telegram, Sprachausgabe, Wake-Word -> siehe README."
Write-Host ""
