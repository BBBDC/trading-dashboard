#!/usr/bin/env python3
"""
TradingView Live Quotes Engine.
Pulls real-time live market quotes directly from TradingView Scanner API.
- Extremely fast (<0.5s for 150+ symbols in a single batch)
- Does NOT consume MCP tool quota (works even when MCP is rate-limited/suspended)
- Provides real-time close price, 24h change %, open, high, low, volume, and timestamp
- Seamlessly updates ohlcv_cache, market_analysis_db, autonomous_portfolio, and user_positions.
"""

import sys
import json
import time
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
import zoneinfo

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"
CACHE_DIR = BASE_DIR / "knowledge_base" / "ohlcv_cache"
TZ_BERLIN = zoneinfo.ZoneInfo("Europe/Berlin")

# Symbol Aliases für TradingView Scanner
SYMBOL_ALIASES = {
    "TVC:DJI": "DJ:DJI",
    "TVC:NDX": "NASDAQ:NDX",
    "BINANCE:BATUSD": "BINANCE:BATUSDT",
    "INDEX:BTCUSD": "COINBASE:BTCUSD",
    "CAPITALCOM:COPPER": "COMEX:HG1!",
    "CAPITALCOM:ALUMINUM": "TVC:ALUMINUM",
    "CAPITALCOM:CORN": "CBOT:ZC1!",
    "TRADEGATE:34Q0": "NASDAQ:COIN"
}

REVERSE_ALIASES = {v: k for k, v in SYMBOL_ALIASES.items()}


def get_all_database_symbols():
    if not DB_FILE.exists():
        return []
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
        return [a["symbol"] for a in db.get("assets", []) if "symbol" in a]
    except Exception:
        return []


def fetch_tradingview_live_quotes(symbols=None):
    """
    Holt echte Live-Kurse von TradingView über den Bulk-Scanner.
    Gibt ein Dict mapping original_symbol -> Quote-Objekt zurück.
    """
    if symbols is None:
        symbols = get_all_database_symbols()

    if not symbols:
        return {}

    now_utc = datetime.now(timezone.utc)
    now_berlin = now_utc.astimezone(TZ_BERLIN)
    now_iso = now_utc.isoformat()
    now_str = now_berlin.strftime("%d.%m. %H:%M CET")

    # Mappe Symbole für den Scanner
    scanner_to_orig = {}
    tickers_to_query = []
    for s in symbols:
        scan_sym = SYMBOL_ALIASES.get(s, s)
        scanner_to_orig[scan_sym] = s
        tickers_to_query.append(scan_sym)

    quotes_map = {}

    # 1. Hauptabfrage: TradingView Global Scanner
    url_global = "https://scanner.tradingview.com/global/scan"
    payload = {
        "symbols": {"tickers": tickers_to_query},
        "columns": ["close", "change", "open", "high", "low", "volume", "description", "currency", "update_mode"]
    }

    try:
        req = urllib.request.Request(
            url_global,
            data=json.dumps(payload).encode("utf-8"),
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for row in data.get("data", []):
                s = row.get("s")
                d = row.get("d", [])
                if not s or not d or d[0] is None:
                    continue

                orig_sym = scanner_to_orig.get(s, s)
                price = float(d[0])
                change_pct = round(float(d[1]), 2) if d[1] is not None else 0.0
                open_p = float(d[2]) if d[2] is not None else price
                high_p = float(d[3]) if d[3] is not None else price
                low_p = float(d[4]) if d[4] is not None else price
                vol = float(d[5]) if d[5] is not None else 0.0
                desc = str(d[6]) if len(d) > 6 and d[6] else orig_sym
                curr = str(d[7]) if len(d) > 7 and d[7] else "USD"

                quotes_map[orig_sym] = {
                    "symbol": orig_sym,
                    "price": price,
                    "change_pct": change_pct,
                    "open": open_p,
                    "high": high_p,
                    "low": low_p,
                    "volume": vol,
                    "description": desc,
                    "currency": curr,
                    "updated_at": now_iso,
                    "updated_at_str": now_str
                }
    except Exception as e:
        print(f"Warnung bei TradingView Global Scanner: {e}", file=sys.stderr)

    # 2. Crypto-Fallback für fehlende Symbole
    missing_crypto = [s for s in symbols if s not in quotes_map and any(c in s for c in ["BINANCE", "COINBASE", "KRAKEN", "KUCOIN", "BTC", "ETH", "USDT"])]
    if missing_crypto:
        try:
            url_crypto = "https://scanner.tradingview.com/crypto/scan"
            payload_c = {
                "symbols": {"tickers": missing_crypto},
                "columns": ["close", "change", "open", "high", "low", "volume", "description"]
            }
            req = urllib.request.Request(
                url_crypto,
                data=json.dumps(payload_c).encode("utf-8"),
                headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for row in data.get("data", []):
                    s = row.get("s")
                    d = row.get("d", [])
                    if s and d and d[0] is not None:
                        quotes_map[s] = {
                            "symbol": s,
                            "price": float(d[0]),
                            "change_pct": round(float(d[1]), 2) if d[1] is not None else 0.0,
                            "open": float(d[2]) if d[2] is not None else float(d[0]),
                            "high": float(d[3]) if d[3] is not None else float(d[0]),
                            "low": float(d[4]) if d[4] is not None else float(d[0]),
                            "volume": float(d[5]) if d[5] is not None else 0.0,
                            "description": str(d[6]) if len(d) > 6 and d[6] else s,
                            "currency": "USD",
                            "updated_at": now_iso,
                            "updated_at_str": now_str
                        }
        except Exception:
            pass

    return quotes_map


def update_ohlcv_cache_with_live_quotes(quotes_map):
    """
    Aktualisiert die letzte Kerze im OHLCV-Cache (1D, 4h, 1h) mit den echten Live-Kursen.
    Stellt sicher, dass Charts und Indikatoren exakt den aktuellen Kurs widerspiegeln.
    """
    if not quotes_map or not CACHE_DIR.exists():
        return 0

    updated_count = 0
    now_ts = int(time.time())

    for sym, q in quotes_map.items():
        price = q["price"]
        high_p = q["high"]
        low_p = q["low"]
        vol = q["volume"]
        safe_sym = sym.replace(":", "_").replace("!", "_").replace(".", "_").replace("/", "_")

        for interval in ["1D", "4h", "1h"]:
            cache_file = CACHE_DIR / f"{safe_sym}_{interval}.json"
            if not cache_file.exists():
                continue

            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                bars = cdata.get("bars", [])
                if not bars:
                    continue

                last_bar = bars[-1]
                # Aktualisiere die letzte Kerze mit dem Live-Kurs
                last_bar["c"] = price
                last_bar["h"] = max(last_bar.get("h", price), price, high_p)
                last_bar["l"] = min(last_bar.get("l", price), price, low_p)
                if vol > 0:
                    last_bar["v"] = max(last_bar.get("v", 0), vol)

                with open(cache_file, "w", encoding="utf-8") as f_out:
                    json.dump(cdata, f_out)
                updated_count += 1
            except Exception:
                pass

    return updated_count


def sync_all_live_prices():
    """
    Führt einen vollen Live-Preis-Sync für alle Assets, das KI-Portfolio und die Nutzer-Positionen durch.
    Gibt (success, quotes_count, msg) zurück.
    """
    if not DB_FILE.exists():
        return False, 0, f"DB {DB_FILE} existiert nicht"

    with open(DB_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)

    all_assets = db.get("assets", [])
    symbols = [a["symbol"] for a in all_assets if "symbol" in a]

    # Portfolio-Symbole und Nutzer-Positionen ebenfalls erfassen
    portfolio_symbols = [t["symbol"] for t in db.get("portfolio", {}).get("active_trades", [])]
    user_symbols = [p["symbol"] for p in db.get("user_positions", [])]
    all_query_symbols = list(set(symbols + portfolio_symbols + user_symbols))

    quotes_map = fetch_tradingview_live_quotes(all_query_symbols)
    if not quotes_map:
        return False, 0, "Keine Live-Kurse von TradingView empfangen"

    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()
    now_str = now_utc.astimezone(TZ_BERLIN).strftime("%d.%m. %H:%M CET")

    # 1. Assets in DB aktualisieren
    for a in all_assets:
        sym = a.get("symbol")
        q = quotes_map.get(sym)
        if not q and sym:
            # Alias Check
            alias = SYMBOL_ALIASES.get(sym)
            if alias:
                q = quotes_map.get(alias)
        if q:
            a["price"] = q["price"]
            a["change_pct"] = q["change_pct"]
            a["last_price_update"] = q["updated_at"]
            a["last_price_update_str"] = q["updated_at_str"]

    db["assets"] = all_assets
    db["last_quotes_update"] = now_iso
    db["last_quotes_update_str"] = now_str

    # 2. Cache-Dateien aktualisieren
    cache_updates = update_ohlcv_cache_with_live_quotes(quotes_map)

    # 3. Autonomes Portfolio und Nutzer-Positionen updaten
    try:
        from portfolio_engine import update_autonomous_portfolio, evaluate_user_positions
        port_data, mem_data = update_autonomous_portfolio(all_assets)
        user_pos_data = evaluate_user_positions(all_assets)
        db["portfolio"] = port_data
        db["trade_memory"] = mem_data
        db["user_positions"] = user_pos_data.get("positions", [])
    except Exception as pe:
        print(f"Warnung bei Portfolio-Update: {pe}", file=sys.stderr)

    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

    return True, len(quotes_map), f"{len(quotes_map)} Live-Kurse aktualisiert ({cache_updates} Cache-Dateien synchronisiert)"


if __name__ == "__main__":
    ok, count, msg = sync_all_live_prices()
    print(f"Status: {ok} | {msg}")
