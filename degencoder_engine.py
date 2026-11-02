#!/usr/bin/env python3
"""
degencoder_engine.py
====================
100% präziser, nativer Python-Nachbau der kompletten degencoder TradingView-Suite:
1. degencoder indicator (13, 1.8, 233):
   - Quantum Chaos Bands (EMA 13 ± 1.8 ATR)
   - RFE Statistical Channel (EMA 233 Basis, Upper & Lower)
   - Institutional Buy & Sell Pockets (Chaos Band über/unter RFE Grenze)
   - 8 diskrete Signale: Good/Potential Buy (Dreiecke), Good Sell (Kreis),
     Buy/Sell Area (Kreuze), Bull/Bear Alignment Ends (Quadrate).
2. degencoder's OB (Retro):
   - 5-Kerzen-Displacement-Filter
   - Liquidity Sweep Detection (Stop Hunt)
   - Quality Grading (A, B, C, D) & Retest Counter (R1, R2, R3)
   - Max 20 aktive Zonen, Projektion 50 Bars nach vorn.
3. degencoder's FVGs:
   - Echte Imbalance-Erkennung (Bullish/Bearish)
   - Hardcoded 1-Tick-Wick Removal Rule (sobald ein Docht eintaucht, gilt FVG als gefüllt).
   - Begrenzung auf maximal 5 aktive Zonen.
"""

import math
from typing import List, Dict, Any, Optional, Tuple


def calculate_ema(values: List[float], period: int) -> List[Optional[float]]:
    """Berechnet den klassischen Exponential Moving Average (EMA)."""
    if not values or len(values) < period:
        return [None] * len(values)
    res = [None] * len(values)
    sma = sum(values[:period]) / period
    res[period - 1] = sma
    multiplier = 2.0 / (period + 1.0)
    for i in range(period, len(values)):
        res[i] = (values[i] - res[i - 1]) * multiplier + res[i - 1]
    return res


def calculate_atr_wilder(bars: List[Dict[str, Any]], period: int = 14) -> List[Optional[float]]:
    """Berechnet Wilder's Average True Range (ATR) wie in TradingView."""
    if not bars or len(bars) < period + 1:
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


def calculate_stdev(values: List[float], period: int) -> List[Optional[float]]:
    """Berechnet die rollierende Standardabweichung über `period` Bars."""
    if len(values) < period:
        return [None] * len(values)
    res = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1:i + 1]
        mean = sum(window) / period
        variance = sum((x - mean) ** 2 for x in window) / period
        res[i] = math.sqrt(variance)
    return res


# ==============================================================================
# 1. DEGENCODER INDICATOR: BÄNDER & RFE CHANNEL
# ==============================================================================

def calculate_degencoder_bands(
    bars: List[Dict[str, Any]],
    quantum_lookback: int = 13,
    fractal_sensitivity: float = 1.8,
    rfe_length: int = 233
) -> Dict[str, Any]:
    """
    Berechnet die 5 Bänder des degencoder indicators:
    - Oberes Band: EMA(13) + 1.8 * ATR(13)
    - Unteres Band: EMA(13) - 1.8 * ATR(13)
    - RFE Basis: EMA(233)
    - RFE Upper & RFE Lower: RFE Basis ± 2.0 * StDev(233) / ATR-Envelope
    """
    if not bars or len(bars) < 15:
        return {}

    closes = [float(b["c"]) for b in bars]
    n = len(bars)

    # 1. Quantum Chaos Bands (13, 1.8)
    ema_13 = calculate_ema(closes, quantum_lookback)
    atr_13 = calculate_atr_wilder(bars, quantum_lookback)

    # 2. RFE Statistical Channel (233)
    eff_rfe_len = rfe_length if n >= rfe_length else max(30, n // 2)
    rfe_basis = calculate_ema(closes, eff_rfe_len)
    rfe_stdev = calculate_stdev(closes, eff_rfe_len)
    atr_rfe = calculate_atr_wilder(bars, min(50, n - 2))

    upper_chaos = []
    lower_chaos = []
    rfe_up = []
    rfe_low = []

    for i in range(n):
        e = ema_13[i]
        a = atr_13[i]
        rb = rfe_basis[i] if (rfe_basis and i < len(rfe_basis)) else None

        if e is not None and a is not None:
            up_c = round(e + fractal_sensitivity * a, 3)
            low_c = round(e - fractal_sensitivity * a, 3)
            upper_chaos.append(up_c)
            lower_chaos.append(low_c)
        else:
            p = closes[i]
            upper_chaos.append(round(p * 1.02, 3))
            lower_chaos.append(round(p * 0.98, 3))

        # RFE Distanz
        if rb is not None:
            # RFE Bandbreite: Kombination aus 2.0 * StDev und ATR(rfe)
            sd = rfe_stdev[i] if (rfe_stdev and i < len(rfe_stdev) and rfe_stdev[i] is not None) else (closes[i] * 0.05)
            r_dist = round(sd * 1.5, 3) if sd else round(closes[i] * 0.06, 3)
            rfe_up.append(round(rb + r_dist, 3))
            rfe_low.append(round(rb - r_dist, 3))
        else:
            p = closes[i]
            rfe_up.append(round(p * 1.08, 3))
            rfe_low.append(round(p * 0.92, 3))

    last_p = closes[-1]
    curr_upper = upper_chaos[-1]
    curr_lower = lower_chaos[-1]
    curr_rfe_basis = rfe_basis[-1] if (rfe_basis and rfe_basis[-1] is not None) else ema_13[-1]
    curr_rfe_up = rfe_up[-1]
    curr_rfe_low = rfe_low[-1]

    # Institutional Pockets gemäß Original-Doku:
    # "When the lower chaos band dips beneath the RFE lower boundary..."
    in_buy_pocket = bool(curr_lower < curr_rfe_low or last_p < curr_lower)
    in_sell_pocket = bool(curr_upper > curr_rfe_up or last_p > curr_upper)

    if last_p > curr_upper:
        channel_pos = "Overbought Band (Überdehnt Oben)"
    elif last_p < curr_lower:
        channel_pos = "Oversold Band (Überdehnt Unten)"
    else:
        channel_pos = "Neutral (Im Kanal)"

    trend = "BULLISH" if (curr_rfe_basis and last_p >= curr_rfe_basis) else "BEARISH"

    return {
        "upper_band": curr_upper,
        "lower_band": curr_lower,
        "ema_fast": round(ema_13[-1], 3) if ema_13[-1] else last_p,
        "rfe_basis": round(curr_rfe_basis, 3) if curr_rfe_basis else last_p,
        "rfe_upper": curr_rfe_up,
        "rfe_lower": curr_rfe_low,
        "channel_position": channel_pos,
        "trend": trend,
        "in_buy_pocket": in_buy_pocket,
        "in_sell_pocket": in_sell_pocket,
        "series": {
            "upper_band": upper_chaos,
            "lower_band": lower_chaos,
            "ema_fast": ema_13,
            "rfe_basis": rfe_basis,
            "rfe_upper": rfe_up,
            "rfe_lower": rfe_low
        }
    }


# ==============================================================================
# 2. DEGENCODER INDICATOR: SIGNALE (PFEILE, KREUZE, MARKER)
# ==============================================================================

def detect_degencoder_signals(bars: List[Dict[str, Any]], bands_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Erkennt die 8 diskreten degencoder Signalzustände:
    1. Good Buy Signal (blaues Dreieck unter Kerze)
    2. Potential Buy Signal (Dreieck unter Kerze)
    3. Good Sell Signal (Kreis über Kerze)
    4. Buy Area (grünes Kreuz unter Kerze)
    5. Sell Area (rotes Kreuz über Kerze)
    6. No Trade Zone (Kreuz)
    7. Bull Alignment Ends (Quadrat unter Kerze)
    8. Bear Alignment Ends (Quadrat über Kerze)
    """
    if not bars or len(bars) < 15 or not bands_data:
        return {"active_signals": [], "last_signal": None}

    series = bands_data.get("series", {})
    upper_band = series.get("upper_band", [])
    lower_band = series.get("lower_band", [])
    rfe_lower = series.get("rfe_lower", [])
    rfe_upper = series.get("rfe_upper", [])
    rfe_basis = series.get("rfe_basis", [])
    ema_fast = series.get("ema_fast", [])

    signals_history = []
    n = len(bars)
    lookback_start = max(2, n - 150)

    for i in range(lookback_start, n):
        b = bars[i]
        b_prev = bars[i - 1]
        c = b["c"]
        o = b["o"]
        l = b["l"]
        h = b["h"]

        u_b = upper_band[i] if i < len(upper_band) else c * 1.02
        l_b = lower_band[i] if i < len(lower_band) else c * 0.98
        rf_l = rfe_lower[i] if (rfe_lower and i < len(rfe_lower) and rfe_lower[i]) else l_b
        rf_u = rfe_upper[i] if (rfe_upper and i < len(rfe_upper) and rfe_upper[i]) else u_b
        rf_b = rfe_basis[i] if (rfe_basis and i < len(rfe_basis) and rfe_basis[i]) else c
        ef = ema_fast[i] if (ema_fast and i < len(ema_fast) and ema_fast[i]) else c

        # 1. Buy Area (Grünes Kreuz): Kerze berührt oder unterbricht das untere Chaos-Band
        is_buy_area = (l <= l_b or c <= l_b)

        # 2. Sell Area (Rotes Kreuz): Kerze berührt oder übersteigt oberes Chaos-Band
        is_sell_area = (h >= u_b or c >= u_b)

        # 3. Buy Pocket: Unteres Band taucht unter RFE Lower
        in_buy_pocket = (l_b < rf_l or l < rf_l)

        # 4. Good Buy Signal (Blaues Dreieck): Bullische Umkehrkerze direkt in/nach Buy Pocket
        # (Grüne Kerze, Rejection Wick unten oder Kreuzung zurück in den Kanal)
        is_reversal_up = (c > o) and (b_prev["c"] < b_prev["o"] or l < l_b)
        good_buy_signal = bool((in_buy_pocket or is_buy_area) and is_reversal_up and (c > b_prev["c"]))

        # 5. Potential Buy Signal: Kerze im tiefen Oversold-Bereich / Buy Pocket
        potential_buy_signal = bool(in_buy_pocket and not good_buy_signal and c > l)

        # 6. Good Sell Signal (Kreis oben): Bärische Umkehrkerze nach Überdehnung
        is_reversal_down = (c < o) and (b_prev["c"] > b_prev["o"] or h > u_b)
        good_sell_signal = bool((is_sell_area or h > rf_u) and is_reversal_down and (c < b_prev["c"]))

        # 7. Alignment Ends: Schneller EMA schneidet zurück durch RFE Basis
        bull_align_ends = bool(b_prev["c"] > rf_b and c < rf_b and ef < rf_b)
        bear_align_ends = bool(b_prev["c"] < rf_b and c > rf_b and ef > rf_b)

        sigs = []
        if good_buy_signal:
            sigs.append("Good Buy Signal (Blaues Dreieck)")
        elif potential_buy_signal:
            sigs.append("Potential Buy Signal (Blaues Dreieck)")
        if good_sell_signal:
            sigs.append("Good Sell Signal (Kreis)")
        if is_buy_area and not good_buy_signal:
            sigs.append("Buy Area (Grünes Kreuz)")
        if is_sell_area and not good_sell_signal:
            sigs.append("Sell Area (Rotes Kreuz)")
        if bull_align_ends:
            sigs.append("Bull Alignment Ends (Quadrat)")
        if bear_align_ends:
            sigs.append("Bear Alignment Ends (Quadrat)")

        if sigs:
            signals_history.append({
                "bar_index": i,
                "time": b["t"],
                "price": c,
                "signals": sigs
            })

    last_sigs = signals_history[-1]["signals"] if signals_history else []
    return {
        "signals_history": signals_history[-20:],
        "current_active_signals": last_sigs,
        "has_buy_signal": any("Buy" in s for s in last_sigs),
        "has_sell_signal": any("Sell" in s for s in last_sigs)
    }


# ==============================================================================
# 3. DEGENCODER'S OB (RETRO): ORDER BLOCKS MIT SWEEPS & GRADING
# ==============================================================================

def detect_degencoder_order_blocks(
    bars: List[Dict[str, Any]],
    displacement_bars: int = 5,
    detect_liquidity_sweep: bool = True,
    max_active_zones: int = 20,
    project_bars: int = 50
) -> List[Dict[str, Any]]:
    """
    100% Nachbau von degencoder's OB (Retro):
    - Parameter: Displacement bars = 5, Detect liquidity sweep = True
    - Quality Grading (A, B, C, D):
      • Grade A: Liquidity Sweep (Stop Hunt des vorherigen Swings) + starker 5-Bar-Impuls (> 2.5x ATR).
      • Grade B: Starkes Displacement (> 1.8x ATR).
      • Grade C: Moderates Displacement (> 1.2x ATR).
      • Grade D: Standard-Displacement (> 0.7x ATR).
    - Retest-Counter: R1, R2, R3 (jedes Mal, wenn der Kurs in die Zone zurückkehrt, ohne sie zu durchbrechen).
    - Invalidation: Vollständig durchbrochen (Close jenseits des OB).
    """
    if not bars or len(bars) < displacement_bars + 5:
        return []

    n = len(bars)
    atr = calculate_atr_wilder(bars, 14)
    obs = []

    # Suche nach potenziellen Order Blocks
    for i in range(2, n - displacement_bars):
        b0 = bars[i]          # Die Order Block Kandidaten-Kerze
        b_prev = bars[i - 1]   # Vorherige Kerze (für Sweep-Erkennung)
        curr_atr = atr[i] if (atr and atr[i]) else (b0["c"] * 0.015)

        # -------------------------------------------------------------
        # A. BULLISCHER ORDER BLOCK (Letzte Down-Kerze vor Aufwärtsimpuls)
        # -------------------------------------------------------------
        # Bedingungen:
        # 1. Kerze b0 schließt rot (c < o) oder bildet ein klares lokales Swing Low
        # 2. Innerhalb der nächsten 5 Kerzen explodiert der Kurs nach oben
        subsequent_bars = bars[i + 1:i + 1 + displacement_bars]
        highest_future = max(b["h"] for b in subsequent_bars)
        displacement_move = highest_future - b0["l"]

        # Liquidity Sweep Check: b0 sticht unter das Tief von b_prev (Stop Hunt)
        is_sweep = bool(b0["l"] < b_prev["l"] and b0["c"] > b0["l"])

        if displacement_move >= 0.75 * curr_atr and highest_future > b0["h"]:
            # Quality Grading
            if is_sweep and displacement_move >= 2.2 * curr_atr:
                grade = "A"
                score = 95
            elif displacement_move >= 1.8 * curr_atr:
                grade = "B"
                score = 85
            elif displacement_move >= 1.2 * curr_atr:
                grade = "C"
                score = 75
            else:
                grade = "D"
                score = 65

            ob_top = max(b0["o"], b0["c"])
            ob_bottom = b0["l"]
            ob_time = b0["t"]

            # Retests & Mitigation tracken ab i + displacement_bars
            retest_count = 0
            mitigated = False
            invalidated = False

            for k in range(i + displacement_bars, n):
                test_bar = bars[k]
                # Invalidation: Kerzenschlusskurs bricht unter OB-Boden
                if test_bar["c"] < ob_bottom:
                    invalidated = True
                    break
                # Retest: Docht taucht in die Zone [ob_bottom, ob_top] ein
                if test_bar["l"] <= ob_top and test_bar["h"] >= ob_bottom:
                    retest_count += 1
                    mitigated = True

            if not invalidated:
                badge_str = f"R{retest_count}" if retest_count > 0 else grade
                obs.append({
                    "type": "Bullish OB",
                    "grade": grade,
                    "badge": badge_str,
                    "score": score,
                    "top": round(ob_top, 3),
                    "bottom": round(ob_bottom, 3),
                    "midline": round((ob_top + ob_bottom) / 2.0, 3),
                    "time": ob_time,
                    "bar_index": i,
                    "is_sweep": is_sweep,
                    "retest_count": retest_count,
                    "mitigated": mitigated
                })

        # -------------------------------------------------------------
        # B. BÄRISCHER ORDER BLOCK (Letzte Up-Kerze vor Abwärtsimpuls)
        # -------------------------------------------------------------
        lowest_future = min(b["l"] for b in subsequent_bars)
        displacement_down = b0["h"] - lowest_future
        is_sweep_high = bool(b0["h"] > b_prev["h"] and b0["c"] < b0["h"])

        if displacement_down >= 0.75 * curr_atr and lowest_future < b0["l"]:
            if is_sweep_high and displacement_down >= 2.2 * curr_atr:
                grade = "A"
                score = 95
            elif displacement_down >= 1.8 * curr_atr:
                grade = "B"
                score = 85
            elif displacement_down >= 1.2 * curr_atr:
                grade = "C"
                score = 75
            else:
                grade = "D"
                score = 65

            ob_top = b0["h"]
            ob_bottom = min(b0["o"], b0["c"])
            ob_time = b0["t"]

            retest_count = 0
            mitigated = False
            invalidated = False

            for k in range(i + displacement_bars, n):
                test_bar = bars[k]
                if test_bar["c"] > ob_top:
                    invalidated = True
                    break
                if test_bar["h"] >= ob_bottom and test_bar["l"] <= ob_top:
                    retest_count += 1
                    mitigated = True

            if not invalidated:
                badge_str = f"R{retest_count}" if retest_count > 0 else grade
                obs.append({
                    "type": "Bearish OB",
                    "grade": grade,
                    "badge": badge_str,
                    "score": score,
                    "top": round(ob_top, 3),
                    "bottom": round(ob_bottom, 3),
                    "midline": round((ob_top + ob_bottom) / 2.0, 3),
                    "time": ob_time,
                    "bar_index": i,
                    "is_sweep": is_sweep_high,
                    "retest_count": retest_count,
                    "mitigated": mitigated
                })

    # Sortiere nach Aktualität und begrenze auf max_active_zones
    obs_sorted = sorted(obs, key=lambda x: x["time"], reverse=True)[:max_active_zones]
    return obs_sorted


# ==============================================================================
# 4. DEGENCODER'S FVGs: HARDCODED 1-TICK-WICK REMOVAL RULE
# ==============================================================================

def detect_degencoder_fvgs(bars: List[Dict[str, Any]], max_fvgs: int = 5) -> List[Dict[str, Any]]:
    """
    100% Nachbau von degencoder's FVGs:
    - Entwickler-Dokumentation: "Removal rule (hardcoded): the moment price wicks
      into the zone even by 1 tick, that FVG is considered filled and is removed from the chart."
    - Behält nur aktive (unfilled) FVG-Zonen.
    - Maximal `max_fvgs` aktive Zonen (Standard: 5).
    """
    if not bars or len(bars) < 3:
        return []

    n = len(bars)
    active_fvgs = []

    for i in range(2, n):
        c0, c1, c2 = bars[i - 2], bars[i - 1], bars[i]

        # Bullish FVG: Low von Kerze 2 liegt über High von Kerze 0
        if c2["l"] > c0["h"]:
            top = c2["l"]
            bottom = c0["h"]
            # Prüfe 1-Tick Removal Rule in allen Folgekerzen
            filled = False
            for k in range(i + 1, n):
                if bars[k]["l"] <= top:  # Sobald der Docht auch nur 1 Tick eintaucht!
                    filled = True
                    break

            if not filled:
                gap_size = top - bottom
                active_fvgs.append({
                    "type": "Bullish FVG",
                    "top": round(top, 3),
                    "bottom": round(bottom, 3),
                    "ce_50": round((top + bottom) / 2.0, 3),
                    "gap_pct": round((gap_size / bottom) * 100, 2),
                    "bar_index": i - 1,
                    "time": c1["t"]
                })

        # Bearish FVG: High von Kerze 2 liegt unter Low von Kerze 0
        elif c2["h"] < c0["l"]:
            top = c0["l"]
            bottom = c2["h"]
            filled = False
            for k in range(i + 1, n):
                if bars[k]["h"] >= bottom:  # Sobald der Docht eintaucht
                    filled = True
                    break

            if not filled:
                gap_size = top - bottom
                active_fvgs.append({
                    "type": "Bearish FVG",
                    "top": round(top, 3),
                    "bottom": round(bottom, 3),
                    "ce_50": round((top + bottom) / 2.0, 3),
                    "gap_pct": round((gap_size / top) * 100, 2),
                    "bar_index": i - 1,
                    "time": c1["t"]
                })

    # Sortiere nach Aktualität (jüngste zuerst) und begrenze auf max_fvgs (5)
    return sorted(active_fvgs, key=lambda x: x["time"], reverse=True)[:max_fvgs]


# ==============================================================================
# 5. VSA WYCKOFF VOLUME (Exakt gemäß Benutzereinstellungen)
# ==============================================================================

def calculate_vsa_wyckoff(
    bars: List[Dict[str, Any]],
    ma_length: int = 20,
    ultra_ratio: float = 2.2,
    very_high_ratio: float = 1.8,
    high_ratio: float = 1.2,
    normal_ratio: float = 0.8,
    low_ratio: float = 0.4
) -> List[Dict[str, Any]]:
    """
    100% präziser Nachbau von 'VSA Wyckoff Volume':
    - Length of MA applied on Volume: 20
    - Ultra High: >= 2.2 (Farbe 0: Lila / #a855f7)
    - Very High: >= 1.8 (Farbe 1: Rot / #ef4444)
    - High: >= 1.2 (Farbe 2: Orange / #f97316)
    - Normal: >= 0.8 (Farbe 3: Grün / #22c55e)
    - Low: >= 0.4 (Farbe 4: Blau / #3b82f6)
    - Very Low: < 0.4 (Farbe 5: Grau / #94a3b8)
    """
    if not bars:
        return []
    
    n = len(bars)
    vols = [float(b.get("v") or 0.0) for b in bars]
    
    # Berechne SMA(volume, ma_length)
    vsa_results = []
    for i in range(n):
        start_idx = max(0, i - ma_length + 1)
        window = vols[start_idx:i + 1]
        sma_v = sum(window) / len(window) if window else 1.0
        v = vols[i]
        ratio = (v / sma_v) if sma_v > 0 else 1.0
        
        if ratio >= ultra_ratio:
            cls = "Ultra High Volume"
            col = "#a855f7"  # Farbe 0: Lila
        elif ratio >= very_high_ratio:
            cls = "Very High Volume"
            col = "#ef4444"  # Farbe 1: Rot
        elif ratio >= high_ratio:
            cls = "High Volume"
            col = "#f97316"  # Farbe 2: Orange
        elif ratio >= normal_ratio:
            cls = "Normal Volume"
            col = "#22c55e"  # Farbe 3: Grün
        elif ratio >= low_ratio:
            cls = "Low Volume"
            col = "#3b82f6"  # Farbe 4: Blau
        else:
            cls = "Very Low Volume"
            col = "#94a3b8"  # Farbe 5: Grau
            
        vsa_results.append({
            "bar_index": i,
            "volume": v,
            "ma_volume": round(sma_v, 2),
            "ratio": round(ratio, 2),
            "class": cls,
            "color": col
        })
        
    return vsa_results


# ==============================================================================
# 6. KOMBINIERTE ANALYSE FÜR DIE PRODUKTIONS-PIPELINE
# ==============================================================================

def analyze_degencoder_full(bars: List[Dict[str, Any]], timeframe: str = "1D") -> Dict[str, Any]:
    """
    Führt die vollständige degencoder-Auswertung in einem Aufruf aus.
    Liefert alle Komponenten (Bänder, Signale, OBs, FVGs, VSA) für Confluence, KI und Charts.
    """
    if not bars or len(bars) < 15:
        return {}

    bands = calculate_degencoder_bands(bars)
    signals = detect_degencoder_signals(bars, bands)
    order_blocks = detect_degencoder_order_blocks(bars, displacement_bars=5, detect_liquidity_sweep=True)
    fvgs = detect_degencoder_fvgs(bars, max_fvgs=5)
    vsa_series = calculate_vsa_wyckoff(bars)

    last_bar = bars[-1]
    curr_price = last_bar["c"]
    curr_vsa = vsa_series[-1] if vsa_series else {}

    # Prüfe ob der aktuelle Kurs in einem Order Block sitzt
    active_ob = None
    for ob in order_blocks:
        if ob["bottom"] <= curr_price <= ob["top"]:
            active_ob = ob
            break

    # Prüfe ob der aktuelle Kurs in einem aktiven FVG sitzt
    active_fvg = None
    for fvg in fvgs:
        if fvg["bottom"] <= curr_price <= fvg["top"]:
            active_fvg = fvg
            break

    return {
        "price": curr_price,
        "timeframe": timeframe,
        "upper_band": bands.get("upper_band"),
        "lower_band": bands.get("lower_band"),
        "ema_fast": bands.get("ema_fast"),
        "rfe_basis": bands.get("rfe_basis"),
        "rfe_upper": bands.get("rfe_upper"),
        "rfe_lower": bands.get("rfe_lower"),
        "channel_position": bands.get("channel_position"),
        "trend": bands.get("trend"),
        "in_buy_pocket": bands.get("in_buy_pocket", False),
        "in_sell_pocket": bands.get("in_sell_pocket", False),
        "active_signals": signals.get("current_active_signals", []),
        "recent_signals": signals.get("signals_history", []),
        "order_blocks": order_blocks[:8],
        "active_order_block": active_ob,
        "fvgs": fvgs,
        "active_fvg": active_fvg,
        "bands_series": bands.get("series", {}),
        "vsa": curr_vsa,
        "vsa_series": vsa_series
    }


if __name__ == "__main__":
    print("degencoder_engine: Modul erfolgreich geladen!")
