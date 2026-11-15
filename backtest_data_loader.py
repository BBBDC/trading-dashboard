#!/usr/bin/env python3
"""
backtest_data_loader.py
=======================
Automatisierter, kostenloser (0 € / 0 Tokens) Data-Lake Loader für den Multi-Asset
& Multi-Timeframe Matrix-Backtest.

Quellen:
1. Krypto: Binance REST API (0 € unlimitiert, bis zu 1000 Kerzen pro Chunk)
2. US-Aktien, Deutsche Aktien, Indizes, Forex, Rohstoffe: Yahoo Finance REST API

Timeframes:
- 15m (Intraday Micro-Sweeps)
- 1h  (Intraday & Swing Trend)
- 4h  (Swing & HTF Governance, aggregiert aus 1h)
- 1D  (Tageschart Makro-Trend)
"""

import os
import sys
import json
import time
import math
import urllib.request
from pathlib import Path
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "knowledge_base" / "backtest_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

# ==============================================================================
# 1. BINANCE REST LOADER (KRYPTO)
# ==============================================================================
def fetch_binance_klines_chunk(symbol: str, interval: str = "1h", start_ts: Optional[int] = None, end_ts: Optional[int] = None, limit: int = 1000) -> List[Dict[str, Any]]:
    sym = symbol.upper().replace("-", "").replace("/", "")
    if not sym.endswith("USDT") and not sym.endswith("USD"):
        sym += "USDT"

    url = f"https://api.binance.com/api/v3/klines?symbol={sym}&interval={interval}&limit={limit}"
    if start_ts:
        url += f"&startTime={int(start_ts * 1000)}"
    if end_ts:
        url += f"&endTime={int(end_ts * 1000)}"

    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not isinstance(data, list):
                return []
            bars = []
            for b in data:
                bars.append({
                    "t": int(b[0] // 1000),
                    "o": float(b[1]),
                    "h": float(b[2]),
                    "l": float(b[3]),
                    "c": float(b[4]),
                    "v": float(b[5])
                })
            return bars
    except Exception as e:
        return []

def fetch_binance_history(symbol: str, interval: str = "1h", target_bars: int = 2000) -> List[Dict[str, Any]]:
    """Lädt bis zu target_bars rückwärts über mehrere Chunks."""
    bars_dict = {}
    end_ts = int(time.time())
    chunk_size = 1000
    int_sec = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}.get(interval, 3600)

    # 1. Chunks rückwärts abrufen
    current_end = end_ts
    while len(bars_dict) < target_bars:
        start_ts = current_end - (chunk_size * int_sec)
        chunk = fetch_binance_klines_chunk(symbol, interval=interval, start_ts=start_ts, end_ts=current_end, limit=chunk_size)
        if not chunk:
            break
        for b in chunk:
            bars_dict[b["t"]] = b
        earliest_in_chunk = min(b["t"] for b in chunk)
        if earliest_in_chunk >= current_end:
            break
        current_end = earliest_in_chunk - 1
        time.sleep(0.08) # Rate limit schrumpfen
        if len(chunk) < 50:
            break

    sorted_bars = sorted(bars_dict.values(), key=lambda x: x["t"])
    return sorted_bars[-target_bars:] if sorted_bars else []

# ==============================================================================
# 2. YAHOO FINANCE REST LOADER (AKTIEN, INDIZES, COMMODITIES, FOREX)
# ==============================================================================
def fetch_yahoo_history(ticker: str, interval: str = "1d", range_str: str = "10y") -> List[Dict[str, Any]]:
    """Lädt historische Kerzen über Yahoo Finance REST."""
    int_map = {"15m": "15m", "1h": "1h", "4h": "1h", "1d": "1d", "1D": "1d"}
    y_int = int_map.get(interval, "1d")

    # Yahoo Limits: 15m max 60d, 1h max 730d (2y), 1d max 20y
    if interval == "15m" and range_str not in ("1d", "5d", "1mo", "60d"):
        range_str = "60d"
    elif interval in ("1h", "4h") and range_str not in ("1mo", "3mo", "6mo", "1y", "2y", "730d"):
        range_str = "730d"

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval={y_int}&range={range_str}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            chart = data.get("chart", {}).get("result", [])
            if not chart:
                return []
            res = chart[0]
            ts = res.get("timestamp", [])
            quote = res.get("indicators", {}).get("quote", [{}])[0]
            opens = quote.get("open", [])
            highs = quote.get("high", [])
            lows = quote.get("low", [])
            closes = quote.get("close", [])
            vols = quote.get("volume", [])

            bars = []
            for i in range(len(ts)):
                if opens[i] is not None and closes[i] is not None and highs[i] is not None and lows[i] is not None:
                    bars.append({
                        "t": int(ts[i]),
                        "o": float(opens[i]),
                        "h": float(highs[i]),
                        "l": float(lows[i]),
                        "c": float(closes[i]),
                        "v": float(vols[i] or 0.0)
                    })

            # Wenn 4h angefragt wurde, aggregieren wir die 1h-Kerzen zu 4h
            if interval == "4h" and y_int == "1h" and bars:
                chunked = []
                for k in range(0, len(bars), 4):
                    chk = bars[k : k + 4]
                    if chk:
                        chunked.append({
                            "t": chk[0]["t"],
                            "o": chk[0]["o"],
                            "h": max(b["h"] for b in chk),
                            "l": min(b["l"] for b in chk),
                            "c": chk[-1]["c"],
                            "v": sum(b["v"] for b in chk)
                        })
                return chunked

            return bars
    except Exception as e:
        return []

# ==============================================================================
# 3. UNIFIZIERTER LOADER MIT LOKALEM CACHING
# ==============================================================================
def get_cached_bars(asset: Dict[str, Any], interval: str = "1d", force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Lädt Kerzen aus dem lokalen Cache oder zieht sie frisch herunter.
    asset: {"symbol": "BTCUSDT", "source": "binance", "name": "Bitcoin"}
    """
    sym = asset["symbol"]
    src = asset.get("source", "yahoo")
    safe_name = f"{src}_{sym.replace(':', '_').replace('=', '_').replace('^', '')}_{interval}.json"
    cache_path = CACHE_DIR / safe_name

    # Cache prüfen (Tagesdaten 24h gültig, Intraday 2h)
    max_age = 86400 if interval == "1d" else 7200
    if not force_refresh and cache_path.exists():
        try:
            mtime = cache_path.stat().st_mtime
            if (time.time() - mtime) < max_age:
                with open(cache_path, "r", encoding="utf-8") as f:
                    bars = json.load(f)
                    if len(bars) >= 30:
                        return bars
        except Exception:
            pass

    # Frisch abrufen
    bars = []
    if src == "binance":
        target = 3000 if interval in ("15m", "1h") else 1500
        bars = fetch_binance_history(sym, interval=interval, target_bars=target)
    else:
        range_s = "60d" if interval == "15m" else ("730d" if interval in ("1h", "4h") else "10y")
        bars = fetch_yahoo_history(sym, interval=interval, range_str=range_s)

    if bars and len(bars) >= 30:
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(bars, f)
        except Exception:
            pass

    return bars

if __name__ == "__main__":
    print("Test-Download 1d & 1h für BTCUSDT & AVGO...")
    b_btc = get_cached_bars({"symbol": "BTCUSDT", "source": "binance"}, interval="1d")
    print(f"BTC 1d: {len(b_btc)} Bars")
    b_avgo = get_cached_bars({"symbol": "AVGO", "source": "yahoo"}, interval="1d")
    print(f"AVGO 1d: {len(b_avgo)} Bars")
    b_btc_1h = get_cached_bars({"symbol": "BTCUSDT", "source": "binance"}, interval="1h")
    print(f"BTC 1h: {len(b_btc_1h)} Bars")
    b_avgo_1h = get_cached_bars({"symbol": "AVGO", "source": "yahoo"}, interval="1h")
    print(f"AVGO 1h: {len(b_avgo_1h)} Bars")
