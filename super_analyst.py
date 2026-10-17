#!/usr/bin/env python3
"""
Super-Analyst Engine: Multi-Timeframe Analysis (4h, 8h, 1D)
für Bitcoin (COINBASE:BTCUSD) und Micron Technology (NASDAQ:MU).
Berechnet alle Indikatoren mathematisch exakt auf Basis der TradingView MCP-Rohdaten.
"""

import json
import math
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "knowledge_base" / "mcp_data"


def load_json(filename):
    with open(DATA_DIR / filename, "r", encoding="utf-8") as f:
        content = f.read().strip()
        # Manche MCP-Outputs enthalten json-Strings
        return json.loads(content)


def aggregate_to_8h(bars_4h):
    """Aggregiert 4h-Kerzen zu sauberen 8h-Kerzen (2x 4h = 8h)."""
    # Sortiere nach Timestamp aufsteigend
    sorted_bars = sorted(bars_4h, key=lambda x: x["t"])
    bars_8h = []
    
    # Ausrichtung an 8h-Blöcken (z.B. Modulo 8*3600 = 28800)
    # Ein 8h-Block startet typischerweise bei 00:00, 08:00, 16:00 UTC
    block_size = 8 * 3600
    current_block = None
    accum = None
    
    for b in sorted_bars:
        t = b["t"]
        block_start = (t // block_size) * block_size
        
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
                "v": b["v"]
            }
        else:
            accum["h"] = max(accum["h"], b["h"])
            accum["l"] = min(accum["l"], b["l"])
            accum["c"] = b["c"]
            accum["v"] += b["v"]
            
    if accum:
        bars_8h.append(accum)
        
    return bars_8h


def calculate_ema(values, period):
    if len(values) < period:
        return [None] * len(values)
    ema = [None] * len(values)
    # Initial SMA
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
        h = bars[i]["h"]
        l = bars[i]["l"]
        prev_c = bars[i - 1]["c"]
        tr_val = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr.append(tr_val)
    
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


def analyze_vsa_wyckoff(bars, period=20, thresholds=(2.2, 1.8, 1.2, 0.8, 0.4)):
    """
    Wyckoff Volume Spread Analysis:
    Vergleicht Kerzenvolumen mit 20 SMA & analysiert den Spread (High - Low) und Close-Position.
    """
    vols = [b["v"] for b in bars]
    if len(vols) < period:
        return []
    
    results = []
    for i in range(period, len(bars)):
        b = bars[i]
        sma_v = sum(vols[i - period:i]) / period
        ratio = b["v"] / sma_v if sma_v > 0 else 1.0
        
        # Einstufung
        c22, c18, c12, c08, c04 = thresholds
        if ratio >= c22:
            vol_class = "Ultra-High / Climax"
        elif ratio >= c18:
            vol_class = "Very High / Stopping"
        elif ratio >= c12:
            vol_class = "High"
        elif ratio >= c08:
            vol_class = "Average / Normal"
        elif ratio >= c04:
            vol_class = "Low"
        else:
            vol_class = "Ultra-Low / No Supply-Demand"
            
        spread = b["h"] - b["l"]
        close_pos = (b["c"] - b["l"]) / spread if spread > 0 else 0.5
        
        results.append({
            "index": i,
            "time": b["t"],
            "volume": b["v"],
            "sma_volume": sma_v,
            "ratio": round(ratio, 2),
            "classification": vol_class,
            "spread": spread,
            "close_pos": round(close_pos, 2)  # 0.0 = low, 1.0 = high
        })
    return results


def analyze_degencoder(bars, ema_fast_len=13, atr_mult=1.8, ema_trend_len=233):
    """
    degencoder indicator (13, 1.8, 233):
    - Trendfilter: EMA 233
    - Dynamischer Kanal: EMA 13 +/- 1.8 * ATR(13)
    """
    closes = [b["c"] for b in bars]
    ema_fast = calculate_ema(closes, ema_fast_len)
    atr = calculate_atr(bars, ema_fast_len)
    ema_trend = calculate_ema(closes, ema_trend_len) if len(closes) >= ema_trend_len else calculate_ema(closes, min(len(closes) // 2, 50))
    
    results = []
    for i in range(len(bars)):
        c = closes[i]
        ef = ema_fast[i]
        at = atr[i]
        et = ema_trend[i] if i < len(ema_trend) else None
        
        if ef is not None and at is not None:
            upper_band = ef + atr_mult * at
            lower_band = ef - atr_mult * at
            trend = "BULLISH" if (et is not None and c > et) else "BEARISH" if (et is not None and c < et) else "NEUTRAL"
            
            # Kanal-Position
            if c > upper_band:
                pos = "Überdehnung Oben (Overbought Band)"
            elif c < lower_band:
                pos = "Überdehnung Unten (Oversold Band)"
            else:
                pos = "Innerhalb des Kanals"
                
            results.append({
                "index": i,
                "time": bars[i]["t"],
                "price": c,
                "ema_fast": round(ef, 2),
                "upper_band": round(upper_band, 2),
                "lower_band": round(lower_band, 2),
                "ema_trend": round(et, 2) if et else None,
                "trend": trend,
                "position": pos
            })
        else:
            results.append(None)
    return results


def detect_fvgs(bars, min_gap_pct=0.05):
    """Erkennt offene & mitigierte FVGs."""
    fvgs = []
    for i in range(2, len(bars)):
        c0, c1, c2 = bars[i - 2], bars[i - 1], bars[i]
        # Bullish FVG
        if c2["l"] > c0["h"]:
            gap = c2["l"] - c0["h"]
            gap_pct = (gap / c0["h"]) * 100
            if gap_pct >= min_gap_pct:
                ce = (c2["l"] + c0["h"]) / 2.0  # Consequent Encroachment
                # Prüfe ob mitigiert in späteren Kerzen
                mitigated = False
                for k in range(i + 1, len(bars)):
                    if bars[k]["l"] <= ce:
                        mitigated = True
                        break
                fvgs.append({
                    "type": "Bullish FVG",
                    "top": round(c2["l"], 2),
                    "bottom": round(c0["h"], 2),
                    "ce_50": round(ce, 2),
                    "gap_pct": round(gap_pct, 2),
                    "index": i - 1,
                    "time": c1["t"],
                    "mitigated": mitigated
                })
        # Bearish FVG
        elif c2["h"] < c0["l"]:
            gap = c0["l"] - c2["h"]
            gap_pct = (gap / c0["l"]) * 100
            if gap_pct >= min_gap_pct:
                ce = (c0["l"] + c2["h"]) / 2.0
                mitigated = False
                for k in range(i + 1, len(bars)):
                    if bars[k]["h"] >= ce:
                        mitigated = True
                        break
                fvgs.append({
                    "type": "Bearish FVG",
                    "top": round(c0["l"], 2),
                    "bottom": round(c2["h"], 2),
                    "ce_50": round(ce, 2),
                    "gap_pct": round(gap_pct, 2),
                    "index": i - 1,
                    "time": c1["t"],
                    "mitigated": mitigated
                })
    return fvgs


def detect_order_blocks(bars, lookback=40):
    """
    Erkennt institutionelle Order Blocks:
    Bullish OB: Letzte Down-Kerze vor starkem Impuls, der vorheriges High bricht.
    Bearish OB: Letzte Up-Kerze vor starkem Impuls, der vorheriges Low bricht.
    """
    obs = []
    start_idx = max(2, len(bars) - lookback)
    for i in range(start_idx, len(bars) - 2):
        b0, b1, b2 = bars[i], bars[i + 1], bars[i + 2]
        # Bullish OB: b0 ist rot, b1+b2 brechen deutlich nach oben aus
        if b0["c"] < b0["o"] and b2["c"] > b0["h"] and (b2["c"] - b0["l"]) / b0["l"] > 0.008:
            # Prüfe ob unmitigiert
            mitigated = False
            for k in range(i + 3, len(bars)):
                if bars[k]["l"] <= b0["h"]:
                    mitigated = True
                    break
            obs.append({
                "type": "Bullish OB",
                "top": round(b0["h"], 2),
                "bottom": round(b0["l"], 2),
                "time": b0["t"],
                "mitigated": mitigated
            })
        # Bearish OB: b0 ist grün, b1+b2 brechen nach unten aus
        elif b0["c"] > b0["o"] and b2["c"] < b0["l"] and (b0["h"] - b2["c"]) / b0["h"] > 0.008:
            mitigated = False
            for k in range(i + 3, len(bars)):
                if bars[k]["h"] >= b0["l"]:
                    mitigated = True
                    break
            obs.append({
                "type": "Bearish OB",
                "top": round(b0["h"], 2),
                "bottom": round(b0["l"], 2),
                "time": b0["t"],
                "mitigated": mitigated
            })
    return obs


def detect_rsi_divergences(bars, period=14, lookback=30):
    """
    Erkennt sowohl reguläre als auch versteckte (Hidden) RSI-Divergenzen.
    - Regular Bull: Price Lower Low, RSI Higher Low (Reversal)
    - Regular Bear: Price Higher High, RSI Lower High (Reversal)
    - Hidden Bull: Price Higher Low, RSI Lower Low (Trend Continuation)
    - Hidden Bear: Price Lower High, RSI Higher High (Trend Continuation)
    """
    closes = [b["c"] for b in bars]
    highs = [b["h"] for b in bars]
    lows = [b["l"] for b in bars]
    rsi = calculate_rsi(closes, period=period)
    
    if len(bars) < lookback + period:
        return []
        
    divs = []
    # Finde Swing-Lows und Swing-Highs
    n = len(bars)
    for i in range(n - 10, n - 1):
        # Ist i ein lokales Tief?
        if lows[i] <= lows[i - 1] and lows[i] <= lows[i + 1]:
            # Suche vorheriges Tief
            for j in range(max(0, i - lookback), i - 2):
                if lows[j] <= lows[j - 1] and lows[j] <= lows[j + 1]:
                    # Regular Bullish
                    if lows[i] < lows[j] and rsi[i] > rsi[j] + 1.0:
                        divs.append({
                            "type": "Reguläre Bullische Divergenz (Reversal-Trigger)",
                            "time_old": bars[j]["t"],
                            "time_new": bars[i]["t"],
                            "price_old": round(lows[j], 2),
                            "price_new": round(lows[i], 2),
                            "rsi_old": rsi[j],
                            "rsi_new": rsi[i],
                            "candle_distance": i - j
                        })
                    # Hidden Bullish
                    elif lows[i] > lows[j] and rsi[i] < rsi[j] - 1.0:
                        divs.append({
                            "type": "Versteckte Bullische Divergenz (Trendfolge-Trigger)",
                            "time_old": bars[j]["t"],
                            "time_new": bars[i]["t"],
                            "price_old": round(lows[j], 2),
                            "price_new": round(lows[i], 2),
                            "rsi_old": rsi[j],
                            "rsi_new": rsi[i],
                            "candle_distance": i - j
                        })
                        
        # Ist i ein lokales Hoch?
        if highs[i] >= highs[i - 1] and highs[i] >= highs[i + 1]:
            for j in range(max(0, i - lookback), i - 2):
                if highs[j] >= highs[j - 1] and highs[j] >= highs[j + 1]:
                    # Regular Bearish
                    if highs[i] > highs[j] and rsi[i] < rsi[j] - 1.0:
                        divs.append({
                            "type": "Reguläre Bärische Divergenz (Reversal-Trigger)",
                            "time_old": bars[j]["t"],
                            "time_new": bars[i]["t"],
                            "price_old": round(highs[j], 2),
                            "price_new": round(highs[i], 2),
                            "rsi_old": rsi[j],
                            "rsi_new": rsi[i],
                            "candle_distance": i - j
                        })
                    # Hidden Bearish
                    elif highs[i] < highs[j] and rsi[i] > rsi[j] + 1.0:
                        divs.append({
                            "type": "Versteckte Bärische Divergenz (Trendfolge-Trigger)",
                            "time_old": bars[j]["t"],
                            "time_new": bars[i]["t"],
                            "price_old": round(highs[j], 2),
                            "price_new": round(highs[i], 2),
                            "rsi_old": rsi[j],
                            "rsi_new": rsi[i],
                            "candle_distance": i - j
                        })
    return divs


def calculate_fibonacci(bars, lookback=60):
    """Berechnet die Fibonacci-Retracements für den letzten dominanten Swing."""
    subset = bars[-lookback:] if len(bars) >= lookback else bars
    high_bar = max(subset, key=lambda x: x["h"])
    low_bar = min(subset, key=lambda x: x["l"])
    
    swing_high = high_bar["h"]
    swing_low = low_bar["l"]
    diff = swing_high - swing_low
    
    # Ist der übergeordnete Swing aufwärts oder abwärts?
    is_up = high_bar["t"] > low_bar["t"]
    
    fibs = {}
    if is_up:
        # Retracement von High nach unten
        fibs["0.0 (High)"] = round(swing_high, 2)
        fibs["0.236"] = round(swing_high - 0.236 * diff, 2)
        fibs["0.382"] = round(swing_high - 0.382 * diff, 2)
        fibs["0.500 (Equilibrium)"] = round(swing_high - 0.500 * diff, 2)
        fibs["0.618 (Golden Pocket Start)"] = round(swing_high - 0.618 * diff, 2)
        fibs["0.650 (Golden Pocket End)"] = round(swing_high - 0.650 * diff, 2)
        fibs["0.786"] = round(swing_high - 0.786 * diff, 2)
        fibs["0.887"] = round(swing_high - 0.887 * diff, 2)
        fibs["1.0 (Low)"] = round(swing_low, 2)
    else:
        # Retracement von Low nach oben
        fibs["0.0 (Low)"] = round(swing_low, 2)
        fibs["0.236"] = round(swing_low + 0.236 * diff, 2)
        fibs["0.382"] = round(swing_low + 0.382 * diff, 2)
        fibs["0.500 (Equilibrium)"] = round(swing_low + 0.500 * diff, 2)
        fibs["0.618 (Golden Pocket Start)"] = round(swing_low + 0.618 * diff, 2)
        fibs["0.650 (Golden Pocket End)"] = round(swing_low + 0.650 * diff, 2)
        fibs["0.786"] = round(swing_low + 0.786 * diff, 2)
        fibs["0.887"] = round(swing_low + 0.887 * diff, 2)
        fibs["1.0 (High)"] = round(swing_high, 2)
        
    return {
        "is_up_swing": is_up,
        "swing_high": swing_high,
        "swing_low": swing_low,
        "levels": fibs
    }


def analyze_timeframe(bars, name, tf_label):
    last_bar = bars[-1]
    closes = [b["c"] for b in bars]
    rsi = calculate_rsi(closes)
    current_rsi = rsi[-1]
    
    degen = analyze_degencoder(bars)
    current_degen = [d for d in degen if d is not None][-1]
    
    vsa = analyze_vsa_wyckoff(bars)
    current_vsa = vsa[-1] if vsa else None
    
    fvgs = detect_fvgs(bars)
    obs = detect_order_blocks(bars)
    divs = detect_rsi_divergences(bars)
    fibs = calculate_fibonacci(bars)
    
    # Filter aktive Zonen nah am Kurs
    p = last_bar["c"]
    recent_fvgs = [f for f in fvgs if not f["mitigated"] and abs(f["ce_50"] - p) / p < 0.12]
    recent_obs = [o for o in obs if not o["mitigated"] and abs(o["top"] - p) / p < 0.12]
    
    dt_str = datetime.fromtimestamp(last_bar["t"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    return {
        "symbol": name,
        "timeframe": tf_label,
        "last_candle_time": dt_str,
        "current_price": p,
        "open": last_bar["o"],
        "high": last_bar["h"],
        "low": last_bar["l"],
        "close": last_bar["c"],
        "volume": last_bar["v"],
        "rsi": current_rsi,
        "degencoder": current_degen,
        "vsa": current_vsa,
        "open_fvgs": recent_fvgs,
        "unmitigated_obs": recent_obs,
        "divergences": divs[-3:] if divs else [],
        "fibonacci": fibs
    }


def main():
    print("Starte präzise Multi-Timeframe-Berechnungen über MCP-Rohdaten...")
    
    btc_1d_raw = load_json("btc_1d_raw.json")["bars"]
    btc_4h_raw = load_json("btc_4h_raw.json")["bars"]
    btc_8h_raw = aggregate_to_8h(btc_4h_raw)
    
    mu_1d_raw = load_json("mu_1d_raw.json")["bars"]
    mu_4h_raw = load_json("mu_4h_raw.json")["bars"]
    mu_8h_raw = aggregate_to_8h(mu_4h_raw)
    
    report = {
        "BTC": {
            "4h": analyze_timeframe(btc_4h_raw, "Bitcoin (BTCUSD)", "4h"),
            "8h": analyze_timeframe(btc_8h_raw, "Bitcoin (BTCUSD)", "8h"),
            "1D": analyze_timeframe(btc_1d_raw, "Bitcoin (BTCUSD)", "1D")
        },
        "MU": {
            "4h": analyze_timeframe(mu_4h_raw, "Micron Technology (MU)", "4h"),
            "8h": analyze_timeframe(mu_8h_raw, "Micron Technology (MU)", "8h"),
            "1D": analyze_timeframe(mu_1d_raw, "Micron Technology (MU)", "1D")
        }
    }
    
    out_file = BASE_DIR / "knowledge_base" / "multi_tf_analysis_result.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        
    print(f"Analyse abgeschlossen! Gespeichert in: {out_file}")


if __name__ == "__main__":
    main()
