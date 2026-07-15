#!/usr/bin/env python3
"""
Einmalige Microsoft-Kalender-Anmeldung (ADR-062) - holt den refresh_token fuer
den Outlook/M365-Kalender-Connector per Device-Code-Flow (headless: du gibst
nur einen Code im Browser ein, kein Redirect-Server noetig).

Voraussetzung (einmalig im Azure-Portal):
  1. Azure Active Directory -> App registrations -> New registration
     (Supported account types: "personal + work/school" fuer 'common').
  2. Authentication -> "Allow public client flows" = JA.
  3. API permissions -> Microsoft Graph -> Delegated -> Calendars.Read
     (offline_access wird automatisch mit angefordert).
  4. Die "Application (client) ID" kopieren.

Aufruf:
  python scripts/ms_calendar_auth.py <CLIENT_ID> [TENANT]
  (TENANT Standard 'common'; fuer nur-privat 'consumers', fuer eine Firma die
   Tenant-ID.)

Ausgabe: der refresh_token - in config.json unter "ms_calendar_refresh_token"
(und "ms_calendar_client_id"/"ms_calendar_tenant") eintragen. Secret: nie ins Repo.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

_SCOPE = "https://graph.microsoft.com/Calendars.Read offline_access"


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
        print("Aufruf: python scripts/ms_calendar_auth.py <CLIENT_ID> [TENANT]")
        return 2
    client_id = argv[1]
    tenant = argv[2] if len(argv) > 2 else "common"
    base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"

    status, dc = _post(f"{base}/devicecode", {"client_id": client_id, "scope": _SCOPE})
    if status != 200 or "device_code" not in dc:
        print(f"Device-Code-Anforderung fehlgeschlagen (HTTP {status}): {dc}")
        return 1

    print("\n" + "=" * 60)
    print(dc.get("message", f"Gehe zu {dc.get('verification_uri')} und gib den Code ein: {dc.get('user_code')}"))
    print("=" * 60 + "\nWarte auf die Anmeldung ...")

    interval = int(dc.get("interval", 5))
    device_code = dc["device_code"]
    deadline = time.time() + int(dc.get("expires_in", 900))
    while time.time() < deadline:
        time.sleep(interval)
        status, tok = _post(f"{base}/token", {
            "client_id": client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
        })
        if status == 200 and tok.get("refresh_token"):
            print("\n✓ Angemeldet. Trage in config.json ein:")
            print(f'  "ms_calendar_client_id": "{client_id}",')
            print(f'  "ms_calendar_tenant": "{tenant}",')
            print(f'  "ms_calendar_refresh_token": "{tok["refresh_token"]}"')
            return 0
        err = tok.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        print(f"\nAnmeldung fehlgeschlagen: {err} - {tok.get('error_description', '')[:200]}")
        return 1
    print("\nZeit abgelaufen - bitte erneut versuchen.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
