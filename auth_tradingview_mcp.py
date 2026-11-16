#!/usr/bin/env python3
"""
TradingView MCP OAuth 2.1 Authenticator & Token Manager.
- Registriert bei Bedarf einen neuen Client mit verifizierten redirect_uris.
- Führt den standardkonformen OAuth 2.1 PKCE Flow mit TradingView durch.
- Erstellt die Login-URL für die Benutzer-Zustimmung im Browser.
- Tauscht den Authorization Code gegen ein frisches Token-Paar ein und speichert es in .mcp_tokens.json.
"""

import sys
import json
import base64
import hashlib
import secrets
import argparse
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
TOKEN_FILE = BASE_DIR / ".mcp_tokens.json"
PENDING_FILE = BASE_DIR / "knowledge_base" / "tv_oauth_pending.json"
CLIENT_REG_FILE = BASE_DIR / "knowledge_base" / "tv_client_registration.json"

AUTH_ENDPOINT = "https://www.tradingview.com/mcp/oauth/authorize"
TOKEN_ENDPOINT = "https://www.tradingview.com/mcp/oauth/token"
REGISTER_ENDPOINT = "https://www.tradingview.com/mcp/oauth/register"
REDIRECT_URI = "http://localhost:8080/oauth/callback"
SCOPES = ["mcp:read", "mcp:tools"]


def register_new_client():
    """Registriert einen neuen OAuth-Client bei TradingView mit exakt passenden redirect_uris."""
    payload = {
        "client_name": "TradingView Super-Analyst",
        "redirect_uris": [
            REDIRECT_URI,
            "http://127.0.0.1:8080/oauth/callback",
            "https://antigravity.google/oauth-callback"
        ],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none"
    }
    req = urllib.request.Request(
        REGISTER_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        CLIENT_REG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CLIENT_REG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return data["client_id"]


def get_client_id(force_refresh=False):
    """Gibt die registrierte Client-ID zurück oder registriert eine frische."""
    if not force_refresh and CLIENT_REG_FILE.exists():
        try:
            with open(CLIENT_REG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                cid = data.get("client_id")
                if cid:
                    return cid
        except Exception:
            pass
    return register_new_client()


def generate_auth_url():
    """Erzeugt die PKCE-Verifizierer, speichert sie zwischen und baut die Authorize-URL."""
    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    client_id = get_client_id(force_refresh=True)

    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    state = secrets.token_urlsafe(16)

    pending_data = {
        "client_id": client_id,
        "verifier": verifier,
        "state": state,
        "redirect_uri": REDIRECT_URI,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(pending_data, f, indent=2)

    params = {
        "client_id": client_id,
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "state": state
    }
    auth_url = f"{AUTH_ENDPOINT}?" + urllib.parse.urlencode(params)
    return auth_url, pending_data


def exchange_code(auth_code_or_url):
    """Tauscht einen Authorization Code oder eine Redirect-URL gegen echte Tokens ein."""
    code = auth_code_or_url.strip()
    if "code=" in code:
        parsed = urllib.parse.urlparse(code)
        q = urllib.parse.parse_qs(parsed.query or parsed.fragment)
        if "code" in q:
            code = q["code"][0]

    if not PENDING_FILE.exists():
        print(f"❌ Fehler: Keine offene Authentifizierung gefunden ({PENDING_FILE} existiert nicht).", file=sys.stderr)
        return False

    with open(PENDING_FILE, "r", encoding="utf-8") as f:
        pending = json.load(f)

    client_id = pending.get("client_id")
    verifier = pending.get("verifier")
    redirect_uri = pending.get("redirect_uri", REDIRECT_URI)

    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier
    }).encode("utf-8")

    req = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"}
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            tokens = json.loads(resp.read().decode("utf-8"))
            access_token = tokens.get("access_token")
            refresh_token = tokens.get("refresh_token")
            expires_in = tokens.get("expires_in", 900)

            if not access_token:
                print("❌ Serverantwort enthielt kein access_token:", tokens, file=sys.stderr)
                return False

            now_iso = datetime.now(timezone.utc).isoformat()
            token_payload = {
                "https://mcp.tradingview.com/mcp": {
                    "client_id": client_id,
                    "token": {
                        "access_token": access_token,
                        "token_type": tokens.get("token_type", "Bearer"),
                        "refresh_token": refresh_token,
                        "expiry": now_iso,
                        "expires_in": expires_in
                    },
                    "token_url": TOKEN_ENDPOINT
                }
            }

            with open(TOKEN_FILE, "w", encoding="utf-8") as f_out:
                json.dump(token_payload, f_out, indent=2)

            # Pending-Datei nach Erfolg löschen
            if PENDING_FILE.exists():
                PENDING_FILE.unlink()

            print("=" * 60)
            print("✅ TradingView MCP OAuth-Token erfolgreich aktualisiert!")
            print(f"   Gültig ab: {now_iso}")
            print(f"   Access Token: {access_token[:25]}... (Länge: {len(access_token)})")
            print(f"   Refresh Token: {refresh_token[:15]}... vorhanden.")
            print(f"   Gespeichert in: {TOKEN_FILE}")
            print("=" * 60)
            return True

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"❌ HTTP-Fehler beim Token-Austausch ({e.code}): {body}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"❌ Unerwarteter Fehler: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="TradingView MCP OAuth 2.1 Authenticator")
    parser.add_argument("code", nargs="?", help="Der Authorization-Code oder die vollständige Redirect-URL aus dem Browser")
    parser.add_argument("--url", action="store_true", help="Gibt nur die Login-URL aus")
    args = parser.parse_args()

    if args.code:
        success = exchange_code(args.code)
        sys.exit(0 if success else 1)
    else:
        url, pending = generate_auth_url()
        print("\n" + "=" * 70)
        print("🔐 TRADINGVIEW MCP OAUTH 2.1 AUTHENTIFIZIERUNG")
        print("=" * 70)
        print("1. Öffne folgenden Link in deinem Browser (auf Mac, PC oder Smartphone):")
        print("\n" + url + "\n")
        print("2. Melde dich bei TradingView an und klicke auf 'Authorize' / 'Zulassen'.")
        print("3. Nach der Bestätigung leitet der Browser weiter auf:")
        print("   http://localhost:8080/oauth/callback?code=DEIN_CODE&state=...")
        print("4. Kopiere die gesamte URL aus der Adresszeile oder nur den Code-Wert und führe aus:")
        print(f"   python3 auth_tradingview_mcp.py \"<URL_ODER_CODE>\"")
        print("   (Oder sende die URL/den Code einfach hier im Chat!)")
        print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
