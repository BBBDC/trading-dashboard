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
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent
TOKEN_FILE = BASE_DIR / ".mcp_tokens.json"
CACHE_DIR = BASE_DIR / "knowledge_base" / "ohlcv_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"

_mcp_quota_suspended_until = 0


def is_mcp_quota_suspended():
    global _mcp_quota_suspended_until
    return time.time() < _mcp_quota_suspended_until


def mark_mcp_quota_suspended(msg=""):
    global _mcp_quota_suspended_until
    now_utc = datetime.now(timezone.utc)
    from datetime import timedelta
    midnight_utc = now_utc.replace(hour=0, minute=5, second=0, microsecond=0)
    if midnight_utc <= now_utc:
        midnight_utc += timedelta(days=1)
    _mcp_quota_suspended_until = midnight_utc.timestamp()
    print(f"⚠️ TradingView MCP Quota aktiv: Pausiere MCP-Tool-Aufrufe bis {midnight_utc.strftime('%H:%M UTC')}. Nutze TV Live-Scanner.", file=sys.stderr)


_MCP_AUTH_INVALID = False


def refresh_access_token():
    """Erneuert das TradingView OAuth-Token automatisch via refresh_token."""
    global _MCP_AUTH_INVALID
    if not TOKEN_FILE.exists():
        return None
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            conf = json.load(f)

        # Unterstütze sowohl verschachteltes als auch flaches Token-Format
        is_nested = ("https://mcp.tradingview.com/mcp" in conf)
        target = conf["https://mcp.tradingview.com/mcp"] if is_nested else conf
        tok_data = target.get("token", target)

        token_url = target.get("token_url", conf.get("token_url", "https://www.tradingview.com/mcp/oauth/token"))
        client_id = target.get("client_id", conf.get("client_id"))
        refresh_token = tok_data.get("refresh_token", conf.get("refresh_token"))

        if not refresh_token or not client_id:
            return tok_data.get("access_token")

        data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id
        }).encode("utf-8")

        req = urllib.request.Request(token_url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            new_tokens = json.loads(resp.read().decode("utf-8"))
            tok_data["access_token"] = new_tokens.get("access_token", tok_data.get("access_token"))
            if "refresh_token" in new_tokens:
                tok_data["refresh_token"] = new_tokens["refresh_token"]
            target["expiry"] = datetime.now(timezone.utc).isoformat()
            with open(TOKEN_FILE, "w", encoding="utf-8") as f_out:
                json.dump(conf, f_out, indent=2)
            print("TradingView MCP OAuth-Token erfolgreich erneuert!")
            _MCP_AUTH_INVALID = False
            return tok_data.get("access_token")
    except Exception as e:
        _MCP_AUTH_INVALID = True
        print(f"Token-Refresh fehlgeschlagen ({e}) -> nutze bestehendes Token / lokalen Cache.", file=sys.stderr)
        if TOKEN_FILE.exists():
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                c = json.load(f)
                if "https://mcp.tradingview.com/mcp" in c:
                    return c["https://mcp.tradingview.com/mcp"].get("token", {}).get("access_token")
                return c.get("access_token")
    return None


def get_token():
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                conf = json.load(f)
                if "https://mcp.tradingview.com/mcp" in conf:
                    entry = conf["https://mcp.tradingview.com/mcp"]
                    tok = entry.get("token", {}).get("access_token")
                    if tok:
                        return tok
                tok = conf.get("access_token")
                if tok:
                    return tok
        except Exception:
            pass
    return refresh_access_token()


def fetch_crypto_bars_direct(symbol: str, interval: str = "1D", count: int = 120) -> List[Dict[str, Any]]:
    """
    Holt 100% echte historische Kerzen für Krypto völlig kostenlos, unbegrenzt und
    in Millisekunden direkt über die offizielle Binance- oder Coinbase-REST-API.
    Verbraucht 0 MCP-Quota!
    """
    clean_sym = symbol.split(":")[-1].replace("/", "")
    if clean_sym.endswith("USD") and not clean_sym.endswith("USDT") and not clean_sym.startswith("USDT"):
        clean_sym += "T"

    # Timeframe-Mapping
    tf_map = {"5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h", "4h": "4h", "1D": "1d", "1W": "1w", "3D": "3d"}
    binance_tf = tf_map.get(interval, "1d")

    url = f"https://api.binance.com/api/v3/klines?symbol={clean_sym}&interval={binance_tf}&limit={count}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(req, timeout=7) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data and isinstance(data, list):
                bars = []
                for b in data:
                    bars.append({
                        "t": int(b[0]) // 1000,
                        "o": round(float(b[1]), 4) if float(b[1]) < 1 else round(float(b[1]), 2),
                        "h": round(float(b[2]), 4) if float(b[2]) < 1 else round(float(b[2]), 2),
                        "l": round(float(b[3]), 4) if float(b[3]) < 1 else round(float(b[3]), 2),
                        "c": round(float(b[4]), 4) if float(b[4]) < 1 else round(float(b[4]), 2),
                        "v": round(float(b[5]), 2)
                    })
                return bars
    except Exception:
        pass

    # Coinbase Fallback
    try:
        cb_id = clean_sym.replace("USDT", "-USD").replace("USD", "-USD")
        gran_map = {"1h": 3600, "1D": 86400}
        gran = gran_map.get(interval, 86400)
        url_cb = f"https://api.exchange.coinbase.com/products/{cb_id}/candles?granularity={gran}"
        req_cb = urllib.request.Request(url_cb, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req_cb, timeout=7) as resp:
            data_cb = json.loads(resp.read().decode("utf-8"))
            if data_cb and isinstance(data_cb, list):
                bars = []
                for b in reversed(data_cb[:count]):
                    bars.append({
                        "t": int(b[0]),
                        "l": round(float(b[1]), 2),
                        "h": round(float(b[2]), 2),
                        "o": round(float(b[3]), 2),
                        "c": round(float(b[4]), 2),
                        "v": round(float(b[5]), 2)
                    })
                return bars
    except Exception:
        pass

    return []


def fetch_yahoo_bars_direct(symbol: str, interval: str = "1D", count: int = 120) -> List[Dict[str, Any]]:
    """
    Holt echte historische Kerzen für US-Aktien kostenlos über Yahoo Finance REST.
    Entlastet TradingView MCP vollständig.
    """
    ticker = symbol.split(":")[-1]
    now = int(time.time())
    start = now - (count + 45) * 86400
    int_map = {"1h": "1h", "4h": "1h", "1D": "1d", "1W": "1wk"}
    y_int = int_map.get(interval, "1d")

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={start}&period2={now}&interval={y_int}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(req, timeout=7) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            res = data.get("chart", {}).get("result", [])
            if not res:
                return []
            entry = res[0]
            ts = entry.get("timestamp", [])
            q = entry.get("indicators", {}).get("quote", [{}])[0]
            opens = q.get("open", [])
            highs = q.get("high", [])
            lows = q.get("low", [])
            closes = q.get("close", [])
            vols = q.get("volume", [])

            bars = []
            for i in range(len(ts)):
                if opens[i] is not None and closes[i] is not None:
                    bars.append({
                        "t": ts[i],
                        "o": round(float(opens[i]), 2),
                        "h": round(float(highs[i]), 2),
                        "l": round(float(lows[i]), 2),
                        "c": round(float(closes[i]), 2),
                        "v": float(vols[i] or 0.0)
                    })

            # Wenn 4h angefragt wurde und wir 1h Kerzen haben -> aggregieren
            if interval == "4h" and y_int == "1h" and bars:
                chunked = []
                for k in range(0, len(bars), 4):
                    chk = bars[k:k + 4]
                    if chk:
                        chunked.append({
                            "t": chk[0]["t"],
                            "o": chk[0]["o"],
                            "h": max(b["h"] for b in chk),
                            "l": min(b["l"] for b in chk),
                            "c": chk[-1]["c"],
                            "v": sum(b["v"] for b in chk)
                        })
                return chunked[-count:]

            return bars[-count:]
    except Exception:
        pass
    return []


def is_crypto_symbol(symbol: str) -> bool:
    s = symbol.upper()
    return any(ex in s for ex in ["BINANCE", "COINBASE", "KRAKEN", "BITSTAMP", "UNISWAP", "AERODROME", "CRYPTOCAP", "KUCOIN", "BYBIT", "OKX", "MEXC", "GATEIO", "BITGET", "COINGECKO", "DEXSCREENER"]) or any(s.endswith(q) for q in ["USD", "USDT", "USDC", "BTC", "ETH", "USDT.P"])


def is_us_stock_symbol(symbol: str) -> bool:
    s = symbol.upper()
    return s.startswith("NASDAQ:") or s.startswith("NYSE:") or s.startswith("AMEX:")


def fetch_bars_direct(symbol, interval="1D", count=120, retries=2):
    """Ruft echte historische Kerzen ab – Krypto via Binance/Coinbase, US-Aktien via Yahoo, Rest via MCP/Cache."""
    safe_sym = symbol.replace(":", "_").replace("!", "_").replace(".", "_").replace("/", "_")
    cache_file = CACHE_DIR / f"{safe_sym}_{interval}.json"

    # 1. KRYPTO-ROUTING (100% entkoppelt von MCP)
    if is_crypto_symbol(symbol):
        crypto_bars = fetch_crypto_bars_direct(symbol, interval=interval, count=count)
        if crypto_bars and len(crypto_bars) >= 10:
            with open(cache_file, "w", encoding="utf-8") as f_out:
                json.dump({"symbol": symbol, "interval": interval, "bars": crypto_bars}, f_out)
            return crypto_bars

    # 2. US-AKTIEN-ROUTING (Kostenlos via Yahoo Finance)
    if is_us_stock_symbol(symbol):
        us_bars = fetch_yahoo_bars_direct(symbol, interval=interval, count=count)
        if us_bars and len(us_bars) >= 10:
            with open(cache_file, "w", encoding="utf-8") as f_out:
                json.dump({"symbol": symbol, "interval": interval, "bars": us_bars}, f_out)
            return us_bars

    # 3. Cache prüfen (10 Min Gültigkeit für Tradegate & Rohstoffe)
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

    # MCP Quota-Sperre oder ungültiges Token prüfen: direkt aus Cache laden
    global _MCP_AUTH_INVALID
    if is_mcp_quota_suspended() or _MCP_AUTH_INVALID:
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f).get("bars", [])
            except Exception:
                pass
        return []

    token = get_token()
    if not token:
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f).get("bars", [])
            except Exception:
                pass
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
                "Accept": "application/json"
            }
            req = urllib.request.Request(url, data=json.dumps(req_data).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                body = resp.read().decode("utf-8")
                res = json.loads(body)
                if "result" in res and "content" in res["result"]:
                    content = res["result"]["content"]
                    if content and isinstance(content, list):
                        txt = content[0].get("text", "")
                        if "TOOL_QUOTA_EXCEEDED" in txt or "suspended" in txt:
                            mark_mcp_quota_suspended(txt)
                            break
                        try:
                            parsed = json.loads(txt)
                            bars = parsed.get("bars", [])
                            if bars:
                                # Cache speichern
                                with open(cache_file, "w", encoding="utf-8") as f_out:
                                    json.dump({"symbol": symbol, "interval": interval, "bars": bars}, f_out)
                                return bars
                        except (json.JSONDecodeError, ValueError):
                            pass
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


def aggregate_to_1w(bars_1d):
    """Aggregiert 1D-Kerzen mathematisch präzise in 1W-Wochenkerzen (5 Handelstage pro Woche)."""
    if not bars_1d:
        return []
    bars_sorted = sorted(bars_1d, key=lambda x: x["t"])
    res = []
    for i in range(0, len(bars_sorted), 5):
        chunk = bars_sorted[i:i+5]
        if not chunk:
            continue
        res.append({
            "t": chunk[0]["t"],
            "o": chunk[0]["o"],
            "h": max(b["h"] for b in chunk),
            "l": min(b["l"] for b in chunk),
            "c": chunk[-1]["c"],
            "v": sum(b.get("v") or 0.0 for b in chunk)
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
    elif interval in ("1h", "4h"):
        return fetch_bars_direct(symbol, interval=interval, count=180)
    elif interval in ("1D", "3D"):
        return fetch_bars_direct(symbol, interval=interval, count=120)
    elif interval == "1W":
        bars = fetch_bars_direct(symbol, interval=interval, count=100)
        if not bars or len(bars) < 10:
            bars_1d = get_real_bars(symbol, interval="1D")
            bars_agg = aggregate_to_1w(bars_1d)
            if bars_agg:
                safe_sym = symbol.replace(":", "_").replace("!", "_").replace(".", "_").replace("/", "_")
                cache_1w = CACHE_DIR / f"{safe_sym}_1W.json"
                try:
                    with open(cache_1w, "w", encoding="utf-8") as f:
                        json.dump({"symbol": symbol, "interval": "1W", "bars": bars_agg}, f)
                except Exception:
                    pass
                return bars_agg
        return bars
    else:
        return fetch_bars_direct(symbol, interval=interval, count=120)


def fetch_premarket_batch_data(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """Holt vorbörsliche Snapshot-Daten (premarket_close, premarket_gap, premarket_volume) in Batches."""
    if not symbols:
        return {}
    token = get_token()
    if not token:
        return {}

    url = "https://mcp.tradingview.com/mcp"
    results = {}

    # In Blöcken von 40 Symbolen abfragen
    for i in range(0, len(symbols), 40):
        chunk = symbols[i:i + 40]
        req_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "mcp-tv-get-symbol-data-batch",
                "arguments": {
                    "symbols": chunk,
                    "columns": ["close", "premarket_close", "premarket_change", "premarket_gap", "premarket_volume"]
                }
            }
        }
        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            req = urllib.request.Request(url, data=json.dumps(req_data).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if "result" in res and "content" in res["result"]:
                    txt = res["result"]["content"][0].get("text", "{}")
                    parsed = json.loads(txt)
                    data_map = parsed.get("data", {})
                    results.update(data_map)
        except Exception as e:
            print(f"Fehler bei Premarket-Abfrage für {len(chunk)} Symbole: {e}", file=sys.stderr)

    return results


def sync_all_real_data(due_symbols=None, limit=None, collect_only=False):
    """
    Lädt echte Kerzen für fällige Assets herunter und cacht sie.
    - due_symbols: Optionales Set oder Liste von Symbolen (z. B. vom Market Gatekeeper).
    - collect_only: Wenn True, werden nur 1h und 4h Kerzen zur schnellen, token-freien Datensammlung geladen.
    """
    if is_mcp_quota_suspended():
        print("ℹ️ TradingView MCP Tool-Quota ist temporär pausiert (bis 00:05 UTC). Nutze TV Live-Scanner & bestehenden Cache.")
        return

    if not DB_FILE.exists():
        print(f"Datenbank {DB_FILE} nicht gefunden!")
        return

    with open(DB_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)

    all_assets = db.get("assets", [])
    if limit:
        all_assets = all_assets[:limit]

    # Filter auf fällige Symbole anwenden
    if due_symbols is not None:
        due_set = set(due_symbols)
        assets_to_fetch = [a for a in all_assets if a["symbol"] in due_set]
        skipped_count = len(all_assets) - len(assets_to_fetch)
        print(f"\nGatekeeper aktiv: {len(assets_to_fetch)} Assets fällig ({skipped_count} geschlossene/aktuelle pausiert).")
    else:
        assets_to_fetch = all_assets

    if not assets_to_fetch:
        print("Keine fälligen Assets zum Herunterladen.")
        return

    from market_schedule import classify_symbol

    mode_label = "Schnell-Cache (1h/4h)" if collect_only else "Voll-Sync (1h, 4h, 1D, 1W"
    print(f"Starte echten OHLCV-Download ({mode_label}) für {len(assets_to_fetch)} Assets über TradingView MCP...")
    success_count = 0

    for idx, a in enumerate(assets_to_fetch, 1):
        sym = a["symbol"]
        print(f"[{idx}/{len(assets_to_fetch)}] Lade echte Kerzen für {a['name']} ({sym})...", end="", flush=True)

        is_crypto = (classify_symbol(sym).get("category") == "CRYPTO")
        b_1h = get_real_bars(sym, interval="1h")
        b_4h = get_real_bars(sym, interval="4h")

        if collect_only:
            if b_1h and b_4h:
                print(f" OK (1h: {len(b_1h)} Bars | 4h: {len(b_4h)} Bars)")
                success_count += 1
            else:
                print(f" WARNUNG: Unvollständig (1h: {len(b_1h)}, 4h: {len(b_4h)})")
        else:
            b_1d = get_real_bars(sym, interval="1D")
            b_1w = get_real_bars(sym, interval="1W")
            b_3d = get_real_bars(sym, interval="3D") if is_crypto else None

            info_parts = [f"1h: {len(b_1h)}", f"4h: {len(b_4h)}", f"1D: {len(b_1d)}", f"1W: {len(b_1w)}"]
            if is_crypto and b_3d:
                info_parts.append(f"3D: {len(b_3d)}")

            if b_1d and b_4h and b_1h:
                print(f" OK ({' | '.join(info_parts)})")
                success_count += 1
            else:
                print(f" WARNUNG: Unvollständige Daten (1D: {len(b_1d)}, 4h: {len(b_4h)})")

        time.sleep(0.12)

    print(f"\nDownload abgeschlossen: {success_count}/{len(assets_to_fetch)} Assets aktualisiert!")


if __name__ == "__main__":
    sync_all_real_data()
