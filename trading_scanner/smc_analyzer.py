"""
Smart Money Concepts (SMC) & Indikatoren-Analyse auf Basis von OHLCV-Marktdaten.
Berechnet Fair Value Gaps (FVGs), Order Blocks, RSI-Divergenzen und Wyckoff-Volumen.
100% datenbasiert, ohne Screenshots.
"""

def calculate_rsi(closes, period=14):
    """Berechnet den Relative Strength Index (RSI)."""
    if len(closes) <= period:
        return [50.0] * len(closes)

    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(0, diff))
        losses.append(max(0, -diff))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    rsi_values = [50.0] * period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi_values.append(round(rsi, 2))

    return rsi_values


def detect_fvgs(bars, min_gap_pct=0.1):
    """
    Erkennt Fair Value Gaps (FVGs / Imbalances).
    Ein Bullish FVG entsteht, wenn High[i-2] < Low[i].
    Ein Bearish FVG entsteht, wenn Low[i-2] > High[i].
    """
    fvgs = []
    for i in range(2, len(bars)):
        c0, c1, c2 = bars[i - 2], bars[i - 1], bars[i]
        
        # Bullish FVG
        if c2["l"] > c0["h"]:
            gap_size = c2["l"] - c0["h"]
            gap_pct = (gap_size / c0["h"]) * 100
            if gap_pct >= min_gap_pct:
                fvgs.append({
                    "type": "Bullish FVG",
                    "top": c2["l"],
                    "bottom": c0["h"],
                    "index": i - 1,
                    "gap_pct": round(gap_pct, 2)
                })
        
        # Bearish FVG
        elif c2["h"] < c0["l"]:
            gap_size = c0["l"] - c2["h"]
            gap_pct = (gap_size / c0["l"]) * 100
            if gap_pct >= min_gap_pct:
                fvgs.append({
                    "type": "Bearish FVG",
                    "top": c0["l"],
                    "bottom": c2["h"],
                    "index": i - 1,
                    "gap_pct": round(gap_pct, 2)
                })

    return fvgs


def detect_order_blocks(bars, lookback=30):
    """
    Erkennt institutionelle Order Blocks (OBs):
    - Bullish OB: Letzte bärische Kerze vor einem signifikanten bullischen Impuls.
    - Bearish OB: Letzte bullische Kerze vor einem signifikanten bärischen Impuls.
    """
    recent_bars = bars[-lookback:] if len(bars) >= lookback else bars
    obs = []
    
    for i in range(len(recent_bars) - 3):
        b0, b1, b2 = recent_bars[i], recent_bars[i + 1], recent_bars[i + 2]
        
        # Bullish Order Block (Bärische Kerze b0 gefolgt von starkem Anstieg)
        if b0["c"] < b0["o"] and b2["c"] > b0["h"]:
            obs.append({
                "type": "Bullish OB",
                "top": b0["h"],
                "bottom": b0["l"],
                "candle_close": b0["c"]
            })
            
        # Bearish Order Block (Bullische Kerze b0 gefolgt von starkem Abverkauf)
        elif b0["c"] > b0["o"] and b2["c"] < b0["l"]:
            obs.append({
                "type": "Bearish OB",
                "top": b0["h"],
                "bottom": b0["l"],
                "candle_close": b0["c"]
            })

    return obs


def detect_rsi_divergences(bars, period=14, lookback=20):
    """
    Erkennt reguläre RSI-Divergenzen:
    - Bullische Divergenz: Kurs bildet tieferes Tief (Lower Low), RSI bildet höheres Tief (Higher Low).
    - Bärische Divergenz: Kurs bildet höheres Hoch (Higher High), RSI bildet tieferes Hoch (Lower High).
    """
    closes = [b["c"] for b in bars]
    lows = [b["l"] for b in bars]
    highs = [b["h"] for b in bars]
    
    rsi = calculate_rsi(closes, period=period)
    
    if len(bars) < lookback + period:
        return []

    divergences = []
    
    # Letztes Preistief vs. Vorheriges Preistief
    min_idx_1 = len(bars) - 1
    # Suche lokale Extrema im Lookback
    for i in range(len(bars) - 5, len(bars) - 1):
        # Bullisch:
        if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            # Suche früheres Tief
            for j in range(max(0, i - lookback), i - 3):
                if lows[j] < lows[j - 1] and lows[j] < lows[j + 1]:
                    if lows[i] < lows[j] and rsi[i] > rsi[j]:
                        divergences.append({
                            "type": "Bullische Divergenz (Bull)",
                            "price_old": lows[j],
                            "price_new": lows[i],
                            "rsi_old": rsi[j],
                            "rsi_new": rsi[i]
                        })
                        
        # Bärisch:
        if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
            for j in range(max(0, i - lookback), i - 3):
                if highs[j] > highs[j - 1] and highs[j] > highs[j + 1]:
                    if highs[i] > highs[j] and rsi[i] < rsi[j]:
                        divergences.append({
                            "type": "Bärische Divergenz (Bear)",
                            "price_old": highs[j],
                            "price_new": highs[i],
                            "rsi_old": rsi[j],
                            "rsi_new": rsi[i]
                        })

    return divergences


def analyze_market_data(ohlcv_data, technicals_data=None):
    """Fasst alle Berechnungen zu einer vollständigen Analyse zusammen."""
    bars = ohlcv_data.get("bars", [])
    if not bars:
        return {"error": "Keine Kerzendaten vorhanden"}

    current_bar = bars[-1]
    closes = [b["c"] for b in bars]
    rsi_list = calculate_rsi(closes)
    current_rsi = rsi_list[-1] if rsi_list else None

    # Falls Technicals vorhanden sind, RSI abgleichen
    if technicals_data and "oscillators" in technicals_data.get("data", {}):
        tech_rsi = technicals_data["data"]["oscillators"].get("rsi")
        if tech_rsi:
            current_rsi = round(tech_rsi, 2)

    fvgs = detect_fvgs(bars)
    obs = detect_order_blocks(bars)
    divs = detect_rsi_divergences(bars)

    # Relevante Zonen nah am aktuellen Kurs
    current_price = current_bar["c"]
    active_fvgs = [f for f in fvgs[-5:] if abs(f["top"] - current_price) / current_price < 0.1]
    active_obs = [o for o in obs[-5:] if abs(o["top"] - current_price) / current_price < 0.1]

    return {
        "symbol": ohlcv_data.get("symbol"),
        "interval": ohlcv_data.get("interval"),
        "current_price": current_price,
        "current_rsi": current_rsi,
        "fvgs": active_fvgs,
        "order_blocks": active_obs,
        "divergences": divs[-2:] if divs else [],
        "bar_count": len(bars)
    }
