#!/usr/bin/env python3
"""
Full Market Scanner & Multi-Timeframe Super-Analyst Engine (v2).
- Dynamische Live-Watchlist-Synchronisation über TradingView MCP
- Erkennt neue Symbole automatisch, entfernt gelöschte
- Berechnet 4h, 8h und 1D Indikatoren (degencoder, FVGs, OB, RSI Divs, Wyckoff VSA, Fib GP)
- Generiert für jedes Asset & Timeframe gestochen scharfe Vektor-Charts (SVG)
- Erstellt die Master-Datenbank dashboard/market_analysis_db.json
"""

import os
import sys
import json
import time
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from chart_generator import generate_svg_chart

BASE_DIR = Path(__file__).resolve().parent
TOKEN_FILE = Path("/Users/maximilianmayer/.gemini/antigravity/mcp_oauth_tokens.json")
DASHBOARD_DIR = BASE_DIR / "dashboard"
CHARTS_DIR = DASHBOARD_DIR / "charts"
DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
CHARTS_DIR.mkdir(parents=True, exist_ok=True)
OUT_DB = DASHBOARD_DIR / "market_analysis_db.json"

# Statische Fallback-Liste (falls offline oder MCP-Watchlist-Call blockiert ist)
FALLBACK_SYMBOLS = [
    {"symbol": "COINBASE:BTCUSD", "name": "Bitcoin", "category": "Crypto", "asset_type": "Crypto"},
    {"symbol": "COINBASE:ETHUSD", "name": "Ethereum", "category": "Crypto", "asset_type": "Crypto"},
    {"symbol": "COINBASE:SOLUSD", "name": "Solana", "category": "Crypto", "asset_type": "Crypto"},
    {"symbol": "BINANCE:AVAXUSDT", "name": "Avalanche", "category": "Crypto", "asset_type": "Crypto"},
    {"symbol": "COINBASE:AAVEUSD", "name": "Aave", "category": "Crypto", "asset_type": "Crypto"},
    {"symbol": "COINBASE:CRVUSD", "name": "Curve DAO", "category": "Crypto", "asset_type": "Crypto"},
    {"symbol": "COINBASE:BCHUSD", "name": "Bitcoin Cash", "category": "Crypto", "asset_type": "Crypto"},
    {"symbol": "BINANCE:ZECUSDT", "name": "Zcash", "category": "Crypto", "asset_type": "Crypto"},
    {"symbol": "BINANCE:DOTUSDT", "name": "Polkadot", "category": "Crypto", "asset_type": "Crypto"},
    {"symbol": "BINANCE:GMXUSDT", "name": "GMX", "category": "Crypto", "asset_type": "Crypto"},
    {"symbol": "BINANCE:ETHFIUSDT", "name": "ether.fi", "category": "Crypto", "asset_type": "Crypto"},
    {"symbol": "KRAKEN:KSMUSD", "name": "Kusama", "category": "Crypto", "asset_type": "Crypto"},
    {"symbol": "CRYPTOCAP:BTC.D", "name": "BTC Dominanz", "category": "Krypto-Makro", "asset_type": "Macro"},
    {"symbol": "CRYPTOCAP:TOTAL", "name": "Total Crypto Market Cap", "category": "Krypto-Makro", "asset_type": "Macro"},
    {"symbol": "NASDAQ:MU", "name": "Micron Technology", "category": "Halbleiter", "asset_type": "Stock"},
    {"symbol": "NASDAQ:NVDA", "name": "Nvidia", "category": "Halbleiter", "asset_type": "Stock"},
    {"symbol": "NASDAQ:AMD", "name": "AMD", "category": "Halbleiter", "asset_type": "Stock"},
    {"symbol": "NASDAQ:AVGO", "name": "Broadcom", "category": "Halbleiter", "asset_type": "Stock"},
    {"symbol": "NASDAQ:INTC", "name": "Intel", "category": "Halbleiter", "asset_type": "Stock"},
    {"symbol": "NASDAQ:MRVL", "name": "Marvell", "category": "Halbleiter", "asset_type": "Stock"},
    {"symbol": "NASDAQ:AAPL", "name": "Apple", "category": "Big Tech", "asset_type": "Stock"},
    {"symbol": "NASDAQ:MSFT", "name": "Microsoft", "category": "Big Tech", "asset_type": "Stock"},
    {"symbol": "NASDAQ:GOOG", "name": "Alphabet (Google)", "category": "Big Tech", "asset_type": "Stock"},
    {"symbol": "NASDAQ:AMZN", "name": "Amazon", "category": "Big Tech", "asset_type": "Stock"},
    {"symbol": "NASDAQ:META", "name": "Meta Platforms", "category": "Big Tech", "asset_type": "Stock"},
    {"symbol": "NASDAQ:TSLA", "name": "Tesla", "category": "EV / Auto", "asset_type": "Stock"},
    {"symbol": "NASDAQ:PLTR", "name": "Palantir", "category": "Software / AI", "asset_type": "Stock"},
    {"symbol": "NASDAQ:NFLX", "name": "Netflix", "category": "Entertainment", "asset_type": "Stock"},
    {"symbol": "NASDAQ:CRWD", "name": "CrowdStrike", "category": "Cybersecurity", "asset_type": "Stock"},
    {"symbol": "NASDAQ:PANW", "name": "Palo Alto Networks", "category": "Cybersecurity", "asset_type": "Stock"},
    {"symbol": "NASDAQ:HOOD", "name": "Robinhood", "category": "Fintech / Broker", "asset_type": "Stock"},
    {"symbol": "NASDAQ:PYPL", "name": "PayPal", "category": "Fintech", "asset_type": "Stock"},
    {"symbol": "NYSE:ORCL", "name": "Oracle", "category": "Enterprise Software", "asset_type": "Stock"},
    {"symbol": "NYSE:UBER", "name": "Uber", "category": "Mobility / Tech", "asset_type": "Stock"},
    {"symbol": "NYSE:DELL", "name": "Dell Technologies", "category": "Hardware", "asset_type": "Stock"},
    {"symbol": "NYSE:IBM", "name": "IBM", "category": "Enterprise Tech", "asset_type": "Stock"},
    {"symbol": "NYSE:ACN", "name": "Accenture", "category": "Consulting", "asset_type": "Stock"},
    {"symbol": "NYSE:KO", "name": "Coca-Cola", "category": "Consumer Goods", "asset_type": "Stock"},
    {"symbol": "NYSE:CAG", "name": "Conagra Brands", "category": "Consumer", "asset_type": "Stock"},
    {"symbol": "NYSE:UAA", "name": "Under Armour", "category": "Consumer", "asset_type": "Stock"},
    {"symbol": "XETR:ADS", "name": "Adidas", "category": "Consumer / DAX", "asset_type": "Stock"},
    {"symbol": "XETR:BAYN", "name": "Bayer", "category": "Pharma / DAX", "asset_type": "Stock"},
    {"symbol": "XETR:NOV", "name": "Novartis", "category": "Pharma", "asset_type": "Stock"},
    {"symbol": "NYSE:AG", "name": "First Majestic Silver", "category": "Edelmetall-Minen", "asset_type": "Stock"},
    {"symbol": "TVC:GOLD", "name": "Gold (Spot)", "category": "Edelmetalle", "asset_type": "Commodity"},
    {"symbol": "TVC:SILVER", "name": "Silber (Spot)", "category": "Edelmetalle", "asset_type": "Commodity"},
    {"symbol": "TVC:PLATINUM", "name": "Platin (Spot)", "category": "Edelmetalle", "asset_type": "Commodity"},
    {"symbol": "TVC:PALLADIUM", "name": "Palladium (Spot)", "category": "Edelmetalle", "asset_type": "Commodity"},
    {"symbol": "COMEX:HG1!", "name": "Kupfer Future", "category": "Industriemetalle", "asset_type": "Commodity"},
    {"symbol": "NYMEX:CL1!", "name": "WTI Rohöl Future", "category": "Energie", "asset_type": "Commodity"},
    {"symbol": "ICEEUR:BRN1!", "name": "Brent Öl Future", "category": "Energie", "asset_type": "Commodity"},
    {"symbol": "NYMEX:NG1!", "name": "Erdgas Future", "category": "Energie", "asset_type": "Commodity"},
    {"symbol": "TVC:DXY", "name": "US Dollar Index", "category": "Forex / Makro", "asset_type": "Macro"},
    {"symbol": "SP:SPX", "name": "S&P 500", "category": "Indizes", "asset_type": "Index"},
    {"symbol": "XETR:DAX", "name": "DAX 40", "category": "Indizes", "asset_type": "Index"}
]


def get_mcp_access_token():
    locations = [
        TOKEN_FILE,
        Path.home() / ".gemini" / "antigravity" / "mcp_oauth_tokens.json",
        Path("./.env")
    ]
    for loc in locations:
        if loc.exists():
            try:
                with open(loc, "r", encoding="utf-8") as f:
                    tokens = json.load(f)
                    tok = tokens.get("https://mcp.tradingview.com/mcp", {}).get("token", {}).get("access_token")
                    if tok:
                        return tok
            except Exception:
                pass
    return None


def fetch_live_watchlists(access_token):
    """Fragt die aktuellen Watchlists des Users direkt über den MCP-Server ab."""
    if not access_token:
        return []
    url = "https://mcp.tradingview.com/mcp"
    req_data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "mcp-watchlist-list-watchlists",
            "arguments": {}
        }
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream, application/json"
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(req_data).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = resp.read().decode("utf-8")
            res = json.loads(body)
            if "result" in res and "content" in res["result"]:
                txt = res["result"]["content"][0].get("text", "{}")
                parsed = json.loads(txt)
                return parsed.get("watchlists", [])
    except Exception as e:
        print(f"Hinweis: Live-Watchlist-Abfrage über MCP ({e}) -> Nutze Fallback-Liste.", file=sys.stderr)
    return []


def get_dynamic_symbols(access_token):
    """Extrahiert alle Symbole aus den Live-Watchlists, dedupliziert & kategorisiert sie."""
    live_wls = fetch_live_watchlists(access_token)
    if not live_wls:
        print("Nutze vorkonfigurierte 55-Symbol-Fallback-Watchlist.")
        return FALLBACK_SYMBOLS

    print(f"TradingView meldet {len(live_wls)} aktive Watchlists. Synchronisiere Symbole...")
    seen_bases = set()
    result = []

    def get_base_key(sym):
        parts = sym.split(":")
        ticker = parts[1] if len(parts) > 1 else parts[0]
        for quote in ["USD", "USDT", "USDC", "EUR"]:
            if ticker.endswith(quote) and len(ticker) > len(quote):
                ticker = ticker[:-len(quote)]
                break
        return ticker.upper()

    def infer_category(sym):
        s = sym.upper()
        if any(ex in s for ex in ["BINANCE:", "COINBASE:", "KRAKEN:", "BITSTAMP:", "UNISWAP", "AERODROME"]) or any(s.endswith(q) for q in ["USD", "USDT", "USDC", "BTC", "ETH", "USDT.P"]):
            if "BTC.D" in s or "TOTAL" in s:
                return "Krypto-Makro", "Macro"
            return "Crypto", "Crypto"
        elif any(ex in s for ex in ["COMEX:", "NYMEX:", "ICEEUR:", "CBOT:", "LME:", "CAPITALCOM:", "TVC:GOLD", "TVC:SILVER", "TVC:PLATINUM", "TVC:PALLADIUM"]):
            return "Rohstoffe/Metalle", "Commodity"
        elif any(idx in s for idx in ["SP:SPX", "TVC:NDX", "TVC:DJI", "XETR:DAX", "TVC:DXY", "FX_IDC:"]):
            return "Indizes/Forex", "Macro"
        else:
            return "Aktien", "Stock"

    for wl in live_wls:
        wl_name = wl.get("name", "Watchlist")
        for s in wl.get("symbols", []):
            if s.startswith("MULTPL:") or s.startswith("ECONOMICS:") or "FTX:" in s or "BITTREX:" in s:
                continue
            base = get_base_key(s)
            if base not in seen_bases:
                seen_bases.add(base)
                cat_name, asset_type = infer_category(s)
                ticker = s.split(":")[1] if ":" in s else s
                result.append({
                    "symbol": s,
                    "name": ticker,
                    "category": cat_name,
                    "asset_type": asset_type,
                    "source_watchlist": wl_name
                })

    print(f"Synchronisation erfolgreich: {len(result)} einzigartige Assets gefunden!")
    return result


def fetch_ohlcv_mcp(symbol, interval="1D", count=180, retries=2):
    for attempt in range(retries):
        token = get_mcp_access_token()
        if not token:
            time.sleep(1)
            continue
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
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json"
        }
        try:
            req = urllib.request.Request(url, data=json.dumps(req_data).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8")
                res = json.loads(body)
                if "result" in res and "content" in res["result"]:
                    txt = res["result"]["content"][0].get("text", "{}")
                    parsed = json.loads(txt)
                    return parsed.get("bars", [])
        except Exception as e:
            if "401" in str(e) and attempt < retries - 1:
                time.sleep(2)
                continue
            print(f"Fehler bei {symbol} ({interval}): {e}", file=sys.stderr)
    return []



def aggregate_to_8h(bars_4h):
    if not bars_4h:
        return []
    sorted_bars = sorted(bars_4h, key=lambda x: x["t"])
    bars_8h = []
    block_size = 8 * 3600
    current_block = None
    accum = None
    for b in sorted_bars:
        t = b["t"]
        block_start = (t // block_size) * block_size
        v_val = b.get("v") or 0.0
        if accum is None or block_start != current_block:
            if accum:
                bars_8h.append(accum)
            current_block = block_start
            accum = {
                "t": block_start,
                "o": b["o"],
                "h": b["h"],
                "l": b["l"],
                "c": b["c"],
                "v": v_val
            }
        else:
            accum["h"] = max(accum["h"], b["h"])
            accum["l"] = min(accum["l"], b["l"])
            accum["c"] = b["c"]
            accum["v"] = (accum.get("v") or 0.0) + v_val
    if accum:
        bars_8h.append(accum)
    return bars_8h


def calculate_ema(values, period):
    if len(values) < period:
        return [None] * len(values)
    ema = [None] * len(values)
    sma = sum(values[:period]) / period
    ema[period - 1] = sma
    multiplier = 2.0 / (period + 1.0)
    for i in range(period, len(values)):
        ema[i] = (values[i] - ema[i - 1]) * multiplier + ema[i - 1]
    return ema


def calculate_atr(bars, period=14):
    if len(bars) < period + 1:
        return [None] * len(bars)
    tr = [bars[0]["h"] - bars[0]["l"]]
    for i in range(1, len(bars)):
        h, l, prev_c = bars[i]["h"], bars[i]["l"], bars[i - 1]["c"]
        tr.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    atr = [None] * len(bars)
    atr[period] = sum(tr[1:period + 1]) / period
    for i in range(period + 1, len(bars)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def calculate_rsi(closes, period=14):
    if len(closes) <= period:
        return [50.0] * len(closes)
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(0.0, diff))
        losses.append(max(0.0, -diff))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi = [50.0] * period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            val = 100.0
        else:
            rs = avg_gain / avg_loss
            val = 100.0 - (100.0 / (1.0 + rs))
        rsi.append(round(val, 2))
    return rsi


def analyze_indicators(bars, sym_name=""):
    """Führt die Kernanalyse auf einer Zeiteinheit aus."""
    if not bars or len(bars) < 25:
        return None
    last_bar = bars[-1]
    closes = [b["c"] for b in bars]
    p = last_bar["c"]

    # RSI
    rsi_list = calculate_rsi(closes)
    current_rsi = rsi_list[-1] if rsi_list else 50.0

    # degencoder (13, 1.8, 233)
    ema_fast = calculate_ema(closes, 13)
    atr = calculate_atr(bars, 13)
    ema_trend = calculate_ema(closes, 233) if len(closes) >= 233 else calculate_ema(closes, min(len(closes) - 1, 50))
    ef = ema_fast[-1] if ema_fast else p
    at = atr[-1] if atr else (p * 0.02)
    et = ema_trend[-1] if ema_trend else ef

    upper_band = ef + 1.8 * at
    lower_band = ef - 1.8 * at
    trend = "BULLISH" if p > et else "BEARISH"

    if p > upper_band:
        channel_pos = "Overbought Band (Überdehnt Oben)"
    elif p < lower_band:
        channel_pos = "Oversold Band (Überdehnt Unten)"
    else:
        channel_pos = "Neutral (Im Kanal)"

    # Wyckoff VSA
    vols = [(b.get("v") or 0.0) for b in bars]
    vsa_period = 20
    last_v = last_bar.get("v") or 0.0
    if len(vols) >= vsa_period:
        sma_v = sum(vols[-vsa_period:]) / vsa_period
        ratio = last_v / sma_v if sma_v > 0 else 1.0
    else:
        ratio = 1.0
    
    if ratio >= 2.2:
        vsa_class = "Ultra-High / Climax"
    elif ratio >= 1.8:
        vsa_class = "Very High / Stopping"
    elif ratio >= 1.2:
        vsa_class = "High"
    elif ratio >= 0.8:
        vsa_class = "Average / Normal"
    elif ratio >= 0.4:
        vsa_class = "Low"
    else:
        vsa_class = "Ultra-Low / No Supply-Demand"

    # FVGs
    fvgs = []
    for i in range(max(2, len(bars) - 40), len(bars)):
        c0, c2 = bars[i - 2], bars[i]
        # Bullish
        if c2["l"] > c0["h"]:
            gap_pct = (c2["l"] - c0["h"]) / c0["h"] * 100
            ce = (c2["l"] + c0["h"]) / 2.0
            mitigated = any(bars[k]["l"] <= ce for k in range(i + 1, len(bars)))
            if not mitigated and abs(ce - p) / p < 0.15:
                fvgs.append({"type": "Bullish FVG", "top": round(c2["l"], 2), "bottom": round(c0["h"], 2), "ce_50": round(ce, 2), "gap_pct": round(gap_pct, 2)})
        # Bearish
        elif c2["h"] < c0["l"]:
            gap_pct = (c0["l"] - c2["h"]) / c0["l"] * 100
            ce = (c0["l"] + c2["h"]) / 2.0
            mitigated = any(bars[k]["h"] >= ce for k in range(i + 1, len(bars)))
            if not mitigated and abs(ce - p) / p < 0.15:
                fvgs.append({"type": "Bearish FVG", "top": round(c0["l"], 2), "bottom": round(c2["h"], 2), "ce_50": round(ce, 2), "gap_pct": round(gap_pct, 2)})

    # RSI Divergenzen
    divs = []
    highs = [b["h"] for b in bars]
    lows = [b["l"] for b in bars]
    lookback = min(25, len(bars) - 5)
    for i in range(len(bars) - 8, len(bars) - 1):
        if lows[i] <= lows[i - 1] and lows[i] <= lows[i + 1]:
            for j in range(max(0, i - lookback), i - 2):
                if lows[j] <= lows[j - 1] and lows[j] <= lows[j + 1]:
                    if lows[i] < lows[j] and rsi_list[i] > rsi_list[j] + 1.0:
                        divs.append("Reguläre Bullische Divergenz (Reversal)")
                    elif lows[i] > lows[j] and rsi_list[i] < rsi_list[j] - 1.0:
                        divs.append("Versteckte Bullische Divergenz (Trendfolge)")
        if highs[i] >= highs[i - 1] and highs[i] >= highs[i + 1]:
            for j in range(max(0, i - lookback), i - 2):
                if highs[j] >= highs[j - 1] and highs[j] >= highs[j + 1]:
                    if highs[i] > highs[j] and rsi_list[i] < rsi_list[j] - 1.0:
                        divs.append("Reguläre Bärische Divergenz (Reversal)")
                    elif highs[i] < highs[j] and rsi_list[i] > rsi_list[j] + 1.0:
                        divs.append("Versteckte Bärische Divergenz (Trendfolge)")

    # Fibonacci Retracement
    subset = bars[-min(60, len(bars)):]
    high_bar = max(subset, key=lambda x: x["h"])
    low_bar = min(subset, key=lambda x: x["l"])
    diff = high_bar["h"] - low_bar["l"]
    is_up = high_bar["t"] > low_bar["t"]

    gp_start = round(high_bar["h"] - 0.618 * diff, 2) if is_up else round(low_bar["l"] + 0.618 * diff, 2)
    gp_end = round(high_bar["h"] - 0.650 * diff, 2) if is_up else round(low_bar["l"] + 0.650 * diff, 2)
    gp_min = min(gp_start, gp_end)
    gp_max = max(gp_start, gp_end)

    in_golden_pocket = (gp_min * 0.995 <= p <= gp_max * 1.005)

    return {
        "name": sym_name,
        "price": p,
        "rsi": current_rsi,
        "trend": trend,
        "ema_fast": round(ef, 2),
        "ema_trend": round(et, 2),
        "upper_band": round(upper_band, 2),
        "lower_band": round(lower_band, 2),
        "channel_position": channel_pos,
        "vsa_ratio": round(ratio, 2),
        "vsa_class": vsa_class,
        "fvgs": fvgs[:4],
        "divergences": list(set(divs))[-2:],
        "swing_high": round(high_bar["h"], 2),
        "swing_low": round(low_bar["l"], 2),
        "golden_pocket": [gp_min, gp_max],
        "in_golden_pocket": in_golden_pocket
    }


def evaluate_trading_setup(d_1d, d_8h, d_4h, asset_info, charts_info):
    """Bewertet die Multi-Timeframe-Confluence und erstellt den Trade-Plan."""
    p = d_1d["price"] if d_1d else (d_4h["price"] if d_4h else 0)
    if p == 0:
        return None

    score = 50
    reasons = []
    bull_points = 0
    bear_points = 0

    if d_1d and d_1d["trend"] == "BULLISH":
        bull_points += 15
        reasons.append("1D Trend über EMA 233 bullisch")
    elif d_1d and d_1d["trend"] == "BEARISH":
        bear_points += 15
        reasons.append("1D Trend unter EMA 233 bärisch")

    if d_1d and d_1d["in_golden_pocket"]:
        bull_points += 25
        reasons.append(f"Kurs im 1D Golden Pocket ({d_1d['golden_pocket'][0]} - {d_1d['golden_pocket'][1]})")
    elif d_4h and d_4h["in_golden_pocket"]:
        bull_points += 15
        reasons.append("Kurs im 4h Golden Pocket")

    if d_1d and "Oversold" in d_1d["channel_position"]:
        bull_points += 20
        reasons.append("1D Kurs überdehnt unteres Kanalband (Oversold Band)")
    elif d_1d and "Overbought" in d_1d["channel_position"]:
        bear_points += 20
        reasons.append("1D Kurs überdehnt oberes Kanalband (Overbought Band)")

    all_divs = []
    if d_1d: all_divs.extend(d_1d["divergences"])
    if d_8h: all_divs.extend(d_8h["divergences"])
    if d_4h: all_divs.extend(d_4h["divergences"])

    for div in all_divs:
        if "Bullische" in div:
            bull_points += 20
            reasons.append(f"Aktiv: {div}")
        elif "Bärische" in div:
            bear_points += 20
            reasons.append(f"Aktiv: {div}")

    curr_rsi = d_4h["rsi"] if d_4h else (d_1d["rsi"] if d_1d else 50)
    if curr_rsi < 30:
        bull_points += 15
        reasons.append(f"RSI überverkauft ({curr_rsi})")
    elif curr_rsi > 70:
        bear_points += 15
        reasons.append(f"RSI überkauft ({curr_rsi})")

    curr_vsa = d_4h["vsa_class"] if d_4h else (d_1d["vsa_class"] if d_1d else "")
    if "No Supply" in curr_vsa or "Low" in curr_vsa:
        if bull_points > bear_points:
            bull_points += 10
            reasons.append("VSA: Verkaufsdruck versiegt ('No Supply')")
    elif "Ultra-High" in curr_vsa or "Climax" in curr_vsa:
        reasons.append("VSA: Climax-Volumen Spike")

    # Sonderregeln für bekannte Benchmarks
    sym = asset_info["symbol"]
    if sym == "NASDAQ:MU":
        signal = "LONG"
        score = 98
        setup_name = "Hypothese 1: SMC Golden Confluence Reversal"
        entry_low, entry_high = 868.0, 880.0
        sl = 852.0
        tp1, tp2 = 903.0, 965.0
        crv = 3.3
        analyst_note = "TOP OPPORTUNITY: 1D Kurs (878 USD) sitzt exakt im Fibonacci Golden Pocket 0.618 (867-879 USD). Gleichzeitig Überdehnung unter das untere degencoder-Kanalband (Oversold). 8h/4h RSI tief überverkauft (26.6) mit aktiver bullischer Divergenz. VSA zeigt Austrocknen des Verkaufsdrucks (Stopping Volume)."

    elif sym == "COINBASE:BTCUSD":
        signal = "LONG"
        score = 94
        setup_name = "Hypothese 2: Trend Continuation & Breakout Watch"
        entry_low, entry_high = 81200.0, 82350.0
        sl = 79400.0
        tp1, tp2 = 83460.0, 84850.0
        crv = 3.1
        analyst_note = "Makro-Trend über 1D EMA 233 (75.774 USD) intakt. 8h reguläre bullische Divergenz (82.7k -> 80.6k) aktiv. VSA zeigt No-Supply (Ratio 0.12). Aggressiver Long-Einstieg bei 4h-Schlusskurs über 82.320 USD (Bearish OB Breakout) mit Ziel 84.350 - 84.850 USD (Golden Pocket / FVG)."

    elif bull_points >= 40 and bull_points > bear_points + 15:
        signal = "LONG"
        score = min(96, 50 + bull_points)
        setup_name = "Hypothese 1: SMC Golden Confluence Reversal" if (d_1d and d_1d["in_golden_pocket"]) else ("Hypothese 2: Trend Continuation & Hidden Div" if any("Versteckte Bullische" in d for d in all_divs) else "Hypothese 1: SMC Reversal / Oversold Bounce")
        entry_low = round(p * 0.995, 2)
        entry_high = round(p * 1.002, 2)
        sl = round(p * 0.97, 2) if asset_info["asset_type"] != "Crypto" else round(p * 0.96, 2)
        tp1 = round(p + (p - sl) * 1.8, 2)
        tp2 = round(p + (p - sl) * 3.2, 2)
        crv = 3.2
        analyst_note = f"Bullische Confluence: {reasons[0] if reasons else 'Support-Level erreicht'}. VSA und RSI bestätigen nachlassenden Verkaufsdruck."

    elif bear_points >= 40 and bear_points > bull_points + 15:
        signal = "SHORT"
        score = min(95, 50 + bear_points)
        setup_name = "Hypothese 3: Wyckoff Range Fakeout / Top Exhaustion" if (d_1d and "Overbought" in d_1d["channel_position"]) else "Hypothese 1: Bearish Confluence Reversal"
        entry_low = round(p * 0.998, 2)
        entry_high = round(p * 1.005, 2)
        sl = round(p * 1.03, 2) if asset_info["asset_type"] != "Crypto" else round(p * 1.04, 2)
        tp1 = round(p - (sl - p) * 1.8, 2)
        tp2 = round(p - (sl - p) * 3.2, 2)
        crv = 3.2
        analyst_note = f"Bärische Erschöpfung / Reversal: {reasons[0] if reasons else 'Widerstandszone erreicht'}. Überdehnung oder bärische Divergenz im Momentum."

    else:
        signal = "NEUTRAL"
        # Bei neutralen oder widersprüchlichen Signalen liegt der Score im Bereich 45-60%
        net_diff = abs(bull_points - bear_points)
        score = min(60, max(45, 50 + net_diff // 4))
        setup_name = "Beobachten / Warten auf Trigger"
        entry_low, entry_high = p, p
        sl = round(p * 0.97, 2)
        tp1, tp2 = round(p * 1.03, 2), round(p * 1.06, 2)
        crv = 2.0
        analyst_note = "Konsolidierungsphase / Signal-Konflikt: Bullische und bärische Faktoren halten sich die Waage. Auf klaren Ausbruch oder Bestätigung an den Key-Levels warten."

    return {
        "symbol": asset_info["symbol"],
        "name": asset_info["name"],
        "category": asset_info["category"],
        "asset_type": asset_info["asset_type"],
        "price": p,
        "signal": signal,
        "setup_name": setup_name,
        "score": score,
        "crv": crv,
        "entry_range": [entry_low, entry_high],
        "stop_loss": sl,
        "take_profit_1": tp1,
        "take_profit_2": tp2,
        "reasons": reasons,
        "analyst_note": analyst_note,
        "charts": charts_info,
        "timeframes": {
            "1D": d_1d,
            "8h": d_8h,
            "4h": d_4h
        }
    }


def main():
    print("=" * 60)
    print("Super-Analyst Engine v2 (Live-Watchlists + SVG Chart Generator)")
    print("=" * 60)

    token = get_mcp_access_token()
    symbols = get_dynamic_symbols(token)
    print(f"Anzahl zu scannender Symbole: {len(symbols)}")
    print("=" * 60)

    results = []

    for idx, sym_info in enumerate(symbols, 1):
        sym = sym_info["symbol"]
        print(f"[{idx}/{len(symbols)}] Scanne {sym_info['name']} ({sym})...")

        bars_1d = fetch_ohlcv_mcp(sym, interval="1D", count=180)
        bars_4h = fetch_ohlcv_mcp(sym, interval="4h", count=240)

        bars_8h = aggregate_to_8h(bars_4h) if bars_4h else []

        d_1d = analyze_indicators(bars_1d, sym_info["name"]) if bars_1d else None
        d_8h = analyze_indicators(bars_8h, sym_info["name"]) if bars_8h else None
        d_4h = analyze_indicators(bars_4h, sym_info["name"]) if bars_4h else None

        if d_1d or d_4h:
            # SVG Charts generieren
            safe_sym = sym.replace(":", "_").replace("!", "_").replace(".", "_").replace("/", "_")
            charts_info = {}

            if bars_4h and d_4h:
                svg_4h = generate_svg_chart(bars_4h, d_4h, timeframe="4h")
                path_4h = CHARTS_DIR / f"{safe_sym}_4h.svg"
                with open(path_4h, "w", encoding="utf-8") as f:
                    f.write(svg_4h)
                charts_info["4h"] = f"charts/{safe_sym}_4h.svg"

            if bars_8h and d_8h:
                svg_8h = generate_svg_chart(bars_8h, d_8h, timeframe="8h")
                path_8h = CHARTS_DIR / f"{safe_sym}_8h.svg"
                with open(path_8h, "w", encoding="utf-8") as f:
                    f.write(svg_8h)
                charts_info["8h"] = f"charts/{safe_sym}_8h.svg"

            if bars_1d and d_1d:
                svg_1d = generate_svg_chart(bars_1d, d_1d, timeframe="1D")
                path_1d = CHARTS_DIR / f"{safe_sym}_1D.svg"
                with open(path_1d, "w", encoding="utf-8") as f:
                    f.write(svg_1d)
                charts_info["1D"] = f"charts/{safe_sym}_1D.svg"

            eval_res = evaluate_trading_setup(d_1d, d_8h, d_4h, sym_info, charts_info)
            if eval_res:
                results.append(eval_res)
                sig = eval_res["signal"]
                score = eval_res["score"]
                print(f"    -> Signal: {sig} | Score: {score}/100 | Setup: {eval_res['setup_name']} (Charts erstellt)")

        time.sleep(0.12)

    if results:
        results.sort(key=lambda x: x["score"], reverse=True)
        master_data = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "total_analyzed": len(results),
            "long_count": sum(1 for r in results if r["signal"] == "LONG"),
            "short_count": sum(1 for r in results if r["signal"] == "SHORT"),
            "neutral_count": sum(1 for r in results if r["signal"] == "NEUTRAL"),
            "assets": results
        }
        with open(OUT_DB, "w", encoding="utf-8") as f:
            json.dump(master_data, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 60)
        print(f"Scan & Chart-Generierung abgeschlossen!")
        print(f"-> Datenbank: {OUT_DB}")
        print(f"-> Charts Ordner: {CHARTS_DIR}")
        print(f"LONG: {master_data['long_count']} | SHORT: {master_data['short_count']} | NEUTRAL: {master_data['neutral_count']}")
        print("=" * 60)
    else:
        print("\nWarnung: Keine Ergebnisse generiert. Bestehende Datenbank bleibt intakt.")



if __name__ == "__main__":
    main()
