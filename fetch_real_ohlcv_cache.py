#!/usr/bin/env python3
"""
Echter Multi-Timeframe OHLCV Datafeed-Manager & Cache.
Holt echte historische Kerzen (Open, High, Low, Close, Volume, Timestamp)
direkt von den TradingView MCP-Servern für 4h, 8h und 1D.
Beinhaltet automatisches OAuth-Token-Management.
"""

import sys
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
TOKEN_FILE = BASE_DIR / ".mcp_tokens.json"
CACHE_DIR = BASE_DIR / "knowledge_base" / "ohlcv_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"


def refresh_access_token():
    """Erneuert das TradingView OAuth-Token automatisch via refresh_token."""
    if not TOKEN_FILE.exists():
        return None
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            conf = json.load(f)

        token_url = conf.get("token_url", "https://www.tradingview.com/mcp/oauth/token")
        client_id = conf.get("client_id")
        refresh_token = conf.get("refresh_token")

        if not refresh_token or not client_id:
            return conf.get("access_token")

        data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id
        }).encode("utf-8")

        req = urllib.request.Request(token_url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            new_tokens = json.loads(resp.read().decode("utf-8"))
            conf["access_token"] = new_tokens.get("access_token", conf["access_token"])
            if "refresh_token" in new_tokens:
                conf["refresh_token"] = new_tokens["refresh_token"]
            conf["expiry"] = datetime.now(timezone.utc).isoformat()
            with open(TOKEN_FILE, "w", encoding="utf-8") as f_out:
                json.dump(conf, f_out, indent=2)
            print("TradingView MCP OAuth-Token erfolgreich erneuert!")
            return conf["access_token"]
    except Exception as e:
        print(f"Token-Refresh fehlgeschlagen ({e}) -> nutze bestehendes Token.", file=sys.stderr)
        if TOKEN_FILE.exists():
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("access_token")
    return None


def get_token():
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                conf = json.load(f)
                return conf.get("access_token")
        except Exception:
            pass
    return refresh_access_token()


def fetch_bars_direct(symbol, interval="1D", count=120, retries=2):
    """Ruft echte historische Kerzen direkt über TradingView MCP ab."""
    safe_sym = symbol.replace(":", "_").replace("!", "_").replace(".", "_").replace("/", "_")
    cache_file = CACHE_DIR / f"{safe_sym}_{interval}.json"

    # Cache prüfen (10 Min Gültigkeit)
    if cache_file.exists():
        try:
            mtime = cache_file.stat().st_mtime
            if time.time() - mtime < 600:
                with open(cache_file, "r", encoding="utf-8") as f:
                    bars = json.load(f).get("bars", [])
                    if len(bars) >= 15:
                        return bars
        except Exception:
            pass

    token = get_token()
    if not token:
        return []

    url = "https://mcp.tradingview.com/mcp"
    req_data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "mcp-tv-get-ohlcv",
            "arguments": {
                "symbol": symbol,
                "interval": interval,
                "count": count
            }
        }
    }

    for attempt in range(retries):
        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream, application/json"
            }
            req = urllib.request.Request(url, data=json.dumps(req_data).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                body = resp.read().decode("utf-8")
                res = json.loads(body)
                if "result" in res and "content" in res["result"]:
                    txt = res["result"]["content"][0].get("text", "{}")
                    parsed = json.loads(txt)
                    bars = parsed.get("bars", [])
                    if bars:
                        # Cache speichern
                        with open(cache_file, "w", encoding="utf-8") as f_out:
                            json.dump({"symbol": symbol, "interval": interval, "bars": bars}, f_out)
                        return bars
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt == 0:
                print(f"401 Unauthorized bei {symbol} -> Erneuere Token...")
                token = refresh_access_token()
                continue
            print(f"HTTP Fehler bei {symbol} ({interval}): {e}", file=sys.stderr)
        except Exception as e:
            print(f"Verbindungsfehler bei {symbol} ({interval}): {e}", file=sys.stderr)

        time.sleep(1)

    # Wenn Abruf fehlschlägt, aber alter Cache existiert
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f).get("bars", [])
        except Exception:
            pass

    return []


def aggregate_to_8h(bars_4h):
    """Aggregiert 4h-Kerzen mathematisch präzise in 8h-Kerzen."""
    if not bars_4h:
        return []
    res = []
    # Sortiere nach Timestamp
    bars_sorted = sorted(bars_4h, key=lambda x: x["t"])
    for i in range(0, len(bars_sorted), 2):
        chunk = bars_sorted[i:i+2]
        if not chunk:
            continue
        c_open = chunk[0]["o"]
        c_close = chunk[-1]["c"]
        c_high = max(b["h"] for b in chunk)
        c_low = min(b["l"] for b in chunk)
        c_vol = sum(b.get("v") or 0.0 for b in chunk)
        c_time = chunk[0]["t"]
        res.append({
            "t": c_time,
            "o": c_open,
            "h": c_high,
            "l": c_low,
            "c": c_close,
            "v": c_vol
        })
    return res


def get_real_bars(symbol, interval="1D"):
    """Liefert echte historische Kerzen für symbol und interval."""
    if interval == "8h":
        safe_sym = symbol.replace(":", "_").replace("!", "_").replace(".", "_").replace("/", "_")
        cache_8h = CACHE_DIR / f"{safe_sym}_8h.json"
        if cache_8h.exists():
            try:
                with open(cache_8h, "r", encoding="utf-8") as f:
                    bars = json.load(f).get("bars", [])
                    if bars:
                        return bars
            except Exception:
                pass
        bars_4h = fetch_bars_direct(symbol, interval="4h", count=180)
        bars_8h = aggregate_to_8h(bars_4h)
        if bars_8h:
            with open(cache_8h, "w", encoding="utf-8") as f:
                json.dump({"symbol": symbol, "interval": "8h", "bars": bars_8h}, f)
        return bars_8h
    else:
        cnt = 180 if interval == "4h" else 120
        return fetch_bars_direct(symbol, interval=interval, count=cnt)


def sync_all_real_data(limit=None):
    """Lädt echte Kerzen für alle Assets in der Datenbank herunter und cacht sie."""
    if not DB_FILE.exists():
        print(f"Datenbank {DB_FILE} nicht gefunden!")
        return

    with open(DB_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)

    assets = db.get("assets", [])
    if limit:
        assets = assets[:limit]

    print(f"\nStarte echten OHLCV-Download für {len(assets)} Assets über TradingView MCP...")
    success_count = 0

    for idx, a in enumerate(assets, 1):
        sym = a["symbol"]
        print(f"[{idx}/{len(assets)}] Lade echte Kerzen für {a['name']} ({sym})...", end="", flush=True)

        b_1d = get_real_bars(sym, interval="1D")
        b_4h = get_real_bars(sym, interval="4h")
        b_8h = get_real_bars(sym, interval="8h")

        if b_1d and b_4h:
            print(f" OK (1D: {len(b_1d)} Bars | 4h: {len(b_4h)} Bars | 8h: {len(b_8h)} Bars)")
            success_count += 1
        else:
            print(f" WARNUNG: Unvollständige Daten (1D: {len(b_1d)}, 4h: {len(b_4h)})")

        time.sleep(0.12)

    print(f"\nDownload abgeschlossen: {success_count}/{len(assets)} Assets mit echten TradingView-Daten versorgt!")


if __name__ == "__main__":
    sync_all_real_data()
