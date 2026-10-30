#!/usr/bin/env python3
"""
Helper zur Einbindung des 2. Google-Kontos für das Trading-System.
Ermöglicht die eigenständige Authentifizierung über Google OAuth (PKCE)
ohne Beeinflussung des primären Antigravity Coding-Kontos.
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

TRADING_HOME = Path("/home/admin/.gemini_trading")
TRADING_CLI_DIR = TRADING_HOME / ".gemini" / "antigravity-cli"
PENDING_FILE = TRADING_HOME / "oauth_pending.json"
TOKEN_FILE = TRADING_CLI_DIR / "antigravity-oauth-token"
SETTINGS_FILE = TRADING_CLI_DIR / "settings.json"

CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
REDIRECT_URI = "https://antigravity.google/oauth-callback"
SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs",
    "https://www.googleapis.com/auth/aicode",
    "openid"
]


def generate_login_url():
    TRADING_HOME.mkdir(parents=True, exist_ok=True)
    TRADING_CLI_DIR.mkdir(parents=True, exist_ok=True)

    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    state = secrets.token_urlsafe(16)

    # Verifier speichern für späteren Token-Exchange
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "verifier": verifier,
            "state": state,
            "created_at": secrets.token_hex(4)
        }, f, indent=2)

    params = {
        "access_type": "offline",
        "client_id": CLIENT_ID,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "consent",
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state
    }
    url = "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(params)
    return url


def exchange_code_for_token(auth_code_or_url):
    code = auth_code_or_url.strip()
    if "code=" in code:
        parsed = urllib.parse.urlparse(code)
        q = urllib.parse.parse_qs(parsed.query or parsed.fragment)
        if "code" in q:
            code = q["code"][0]

    if not PENDING_FILE.exists():
        print(f"Fehler: Keine offene Authentifizierung gefunden ({PENDING_FILE} fehlt). Bitte zuerst ohne Parameter aufrufen.")
        return False

    with open(PENDING_FILE, "r", encoding="utf-8") as f:
        pending = json.load(f)

    verifier = pending.get("verifier")
    if not verifier:
        print("Fehler: Kein code_verifier in oauth_pending.json gefunden.")
        return False

    data = {
        "client_id": CLIENT_ID,
        "code": code,
        "code_verifier": verifier,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI
    }
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=encoded, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            token_resp = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"Fehler beim Token-Austausch (HTTP {e.code}): {err_body}")
        return False
    except Exception as e:
        print(f"Netzwerkfehler beim Token-Austausch: {e}")
        return False

    # E-Mail aus id_token extrahieren falls vorhanden
    email = "second_account@google.com"
    id_token = token_resp.get("id_token")
    if id_token and "." in id_token:
        try:
            parts = id_token.split(".")
            padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
            email = payload.get("email", email)
        except Exception:
            pass

    # Speichern im Format von antigravity-oauth-token
    oauth_data = {
        "token": {
            "access_token": token_resp.get("access_token"),
            "token_type": token_resp.get("token_type", "Bearer"),
            "refresh_token": token_resp.get("refresh_token"),
            "expires_in": token_resp.get("expires_in", 3599)
        },
        "auth_method": "consumer",
        "id_token_email": email
    }

    TRADING_CLI_DIR.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(oauth_data, f, indent=2)

    # settings.json kopieren falls nicht vorhanden
    src_settings = Path("/home/admin/.gemini/antigravity-cli/settings.json")
    if src_settings.exists() and not SETTINGS_FILE.exists():
        with open(src_settings, "r", encoding="utf-8") as f_in, open(SETTINGS_FILE, "w", encoding="utf-8") as f_out:
            f_out.write(f_in.read())

    # Pending-Datei entfernen
    PENDING_FILE.unlink(missing_ok=True)

    print(f"✅ Zweites Google-Konto erfolgreich autorisiert!")
    print(f"   • Account-E-Mail: {email}")
    print(f"   • Gespeichert in: {TOKEN_FILE}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Google Zweitkonto Authentifizierung")
    parser.add_argument("--code", type=str, help="Der Google Authorization Code oder die gesamte Callback-URL")
    args = parser.parse_args()

    if args.code:
        success = exchange_code_for_token(args.code)
        sys.exit(0 if success else 1)
    else:
        url = generate_login_url()
        print("\n" + "=" * 70)
        print("  🔑 VERKNÜPFUNG DES 2. GOOGLE-KONTOS (DEDIZIERTES TRADING PRO-ABO)")
        print("=" * 70)
        print("\nBitte öffne den folgenden Link in einem Browser, in dem du mit deinem")
        print("2. Google-Konto angemeldet bist:\n")
        print(url)
        print("\n" + "-" * 70)
        print("Schritte:")
        print("1. Klicke auf den obigen Link und erteile die Berechtigung.")
        print("2. Google leitet dich auf eine Seite weiter (https://antigravity.google/oauth-callback?code=...).")
        print("3. Kopiere die URL aus der Adresszeile oder den 'code=' Wert und führe aus:")
        print(f"   python3 {Path(__file__).resolve()} --code \"DEIN_CODE_ODER_URL\"")
        print("   (Oder sende mir einfach den Code direkt hier im Chat!)")
        print("=" * 70 + "\n")
