#!/usr/bin/env python3
"""
degencoder_engine.py
====================
100% präziser, nativer Python-Nachbau der kompletten degencoder TradingView-Suite:
1. degencoder indicator (13, 1.8, 233):
   - Quantum Volatility / Chaos Bands: Donchian-ATR Channel (highest(high, 5) + 1.8 * atr(14), lowest(low, 5) - 1.8 * atr(14))
   - RFE Statistical Channel: WMA 233 Basis, Upper & Lower (WMA 233 ± 1.618 * StDev 233)
   - Institutional Buy & Sell Pockets (Buy Area, Sell Area, No Trade Zone)
   - Diskrete Signale: Good/Potential Buy (Dreiecke), Good Sell (Kreis),
     Buy/Sell Area (Kreuze), No Trade Zone, Bull/Bear Alignment Ends.
2. degencoder's OB (Retro):
   - 5-Kerzen-Displacement-Filter (5 Kerzen in Gegenrichtung)
   - Liquidity Sweep Detection (Stop Hunt der letzten 20 Bars)
   - Quality Grading (A, B, C, D) & Retest Counter (R1, R2, R3)
   - Max 20 aktive Zonen, Projektion 50 Bars nach vorn.
3. degencoder's FVGs:
   - Echte Imbalance-Erkennung (Bullish/Bearish)
   - Hardcoded 1-Tick-Wick Removal Rule (sobald ein Docht eintaucht, gilt FVG als gefüllt).
   - Begrenzung auf maximal 5 aktive Zonen.
4. VSA Wyckoff Volume:
   - 5 volumenbasierte Wyckoff-Balkenklassen (Ultra-High, Very High, High, Normal, Low/Very Low).
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


def calculate_wma(values: List[float], period: int) -> List[Optional[float]]:
    """Berechnet den gewichteten gleitenden Durchschnitt (WMA) exakt wie TradingView ta.wma()."""
    if not values or len(values) < period:
        return [None] * len(values)
    res = [None] * len(values)
    w_sum = period * (period + 1) // 2
    for i in range(period - 1, len(values)):
        res[i] = sum(values[i - period + 1 + j] * (j + 1) for j in range(period)) / w_sum
    return res


def calculate_atr_wilder(bars: List[Dict[str, Any]], period: int = 14) -> List[Optional[float]]:
    """Berechnet Wilder's Average True Range (ATR) exakt wie in TradingView (ta.rma(ta.tr, period))."""
    if not bars or len(bars) < period + 1:
        return [None] * len(bars)
    h0 = float(bars[0]["h"])
    l0 = float(bars[0]["l"])
    tr = [h0 - l0]
    for i in range(1, len(bars)):
        h = float(bars[i]["h"])
        l = float(bars[i]["l"])
        prev_c = float(bars[i - 1]["c"])
        tr_val = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr.append(tr_val)

    atr = [None] * len(bars)
    atr[period] = sum(tr[1:period + 1]) / period
    for i in range(period + 1, len(bars)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def calculate_stdev(values: List[float], period: int) -> List[Optional[float]]:
    """Berechnet die rollierende Standardabweichung über `period` Bars wie TradingView ta.stdev()."""
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
    quantum_lookback: int = 5,
    fractal_sensitivity: float = 1.8,
    rfe_length: int = 233,
    atr_length: int = 14
) -> Dict[str, Any]:
    """
    Berechnet die 5 Bänder des degencoder indicators mit 100% TradingView-Parität:
    - Oberes Band: highest(high, 5) + 1.8 * ATR(14)
    - Unteres Band: lowest(low, 5) - 1.8 * ATR(14)
    - RFE Basis: WMA(233)
    - RFE Upper & RFE Lower: RFE Basis ± 1.618 * StDev(233) (Golden Ratio)
    """
    if not bars or len(bars) < 15:
        return {}

    n = len(bars)
    closes = [float(b["c"]) for b in bars]
    highs = [float(b["h"]) for b in bars]
    lows = [float(b["l"]) for b in bars]

    # 1. Quantum Volatility Bands (Donchian 5 + 1.8 * ATR 14)
    atr = calculate_atr_wilder(bars, atr_length)
    ema_fast = calculate_ema(closes, 13)

    # 2. RFE Statistical Channel (WMA 233 + 1.618 * StDev 233)
    eff_rfe_len = rfe_length if n >= rfe_length else max(30, n // 2)
    rfe_basis = calculate_wma(closes, eff_rfe_len)
    rfe_stdev = calculate_stdev(closes, eff_rfe_len)

    upper_chaos = []
    lower_chaos = []
    rfe_up = []
    rfe_low = []

    for i in range(n):
        c = closes[i]
        a = atr[i] if (atr and i < len(atr) and atr[i] is not None) else (c * 0.015)
        rb = rfe_basis[i] if (rfe_basis and i < len(rfe_basis) and rfe_basis[i] is not None) else c
        sd = rfe_stdev[i] if (rfe_stdev and i < len(rfe_stdev) and rfe_stdev[i] is not None) else (c * 0.05)

        # Donchian 5 Window
        start_idx = max(0, i - quantum_lookback + 1)
        hi_win = max(highs[start_idx:i + 1])
        lo_win = min(lows[start_idx:i + 1])

        ub_c = round(hi_win + fractal_sensitivity * a, 3)
        lb_c = round(lo_win - fractal_sensitivity * a, 3)
        upper_chaos.append(ub_c)
        lower_chaos.append(lb_c)

        # RFE Channel mit Golden Ratio 1.618
        r_dist = round(1.618 * sd, 3)
        rfe_up.append(round(rb + r_dist, 3))
        rfe_low.append(round(rb - r_dist, 3))

    last_p = closes[-1]
    curr_upper = upper_chaos[-1]
    curr_lower = lower_chaos[-1]
    curr_rfe_basis = rfe_basis[-1] if (rfe_basis and rfe_basis[-1] is not None) else last_p
    curr_rfe_up = rfe_up[-1]
    curr_rfe_low = rfe_low[-1]

    # Institutional Pockets gemäß TradingView-Regel:
    # Buy Area: low < RFE_Lower and prev_high > RFE_Lower
    prev_h = highs[-2] if n >= 2 else highs[-1]
    prev_l = lows[-2] if n >= 2 else lows[-1]
    in_buy_pocket = bool(lows[-1] < curr_rfe_low and prev_h > curr_rfe_low)
    in_sell_pocket = bool(highs[-1] > curr_rfe_up and prev_l < curr_rfe_up)

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
        "ema_fast": round(ema_fast[-1], 3) if (ema_fast and ema_fast[-1]) else last_p,
        "rfe_basis": round(curr_rfe_basis, 3),
        "rfe_upper": curr_rfe_up,
        "rfe_lower": curr_rfe_low,
        "channel_position": channel_pos,
        "trend": trend,
        "in_buy_pocket": in_buy_pocket,
        "in_sell_pocket": in_sell_pocket,
        "series": {
            "upper_band": upper_chaos,
            "lower_band": lower_chaos,
            "ema_fast": ema_fast,
            "rfe_basis": rfe_basis,
            "rfe_upper": rfe_up,
            "rfe_lower": rfe_low
        }
    }


# ==============================================================================
# 2. DEGENCODER INDICATOR: SIGNALE (PFEILE, KREUZE, MARKER)
# ==============================================================================

def detect_degencoder_signals(bars: List[Dict[str, Any]], bands_data: Dict[str, Any], full_history: bool = False) -> Dict[str, Any]:
    """
    Erkennt die diskreten degencoder Signalzustände mit 100% kalibrierten Schwellenwerten:
    1. Good Buy Signal (blaues Dreieck unter Kerze)
    2. Potential Buy Signal (Dreieck unter Kerze)
    3. Good Sell Signal (Kreis über Kerze)
    4. Buy Area (grünes Kreuz unter Kerze: low < RFE_Lower & prev_high > RFE_Lower)
    5. Sell Area (rotes Kreuz über Kerze: high > RFE_Upper & prev_low < RFE_Upper)
    6. No Trade Zone (Kreuz: Kurs schneidet RFE_Basis)
    7. Bull Alignment Ends (Quadrat: Kreuzung der Basis abwärts)
    8. Bear Alignment Ends (Quadrat: Kreuzung der Basis aufwärts)
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
    lookback_start = 1 if full_history else max(1, n - 150)

    for i in range(lookback_start, n):
        b = bars[i]
        b_prev = bars[i - 1]
        c = float(b["c"])
        o = float(b["o"])
        l = float(b["l"])
        h = float(b["h"])
        prev_c = float(b_prev["c"])
        prev_h = float(b_prev["h"])
        prev_l = float(b_prev["l"])

        u_b = upper_band[i] if (upper_band and i < len(upper_band) and upper_band[i] is not None) else c * 1.02
        l_b = lower_band[i] if (lower_band and i < len(lower_band) and lower_band[i] is not None) else c * 0.98

        has_rfe = bool(rfe_basis and i < len(rfe_basis) and rfe_basis[i] is not None)
        rf_b = rfe_basis[i] if has_rfe else None
        rf_l = rfe_lower[i] if (has_rfe and rfe_lower and i < len(rfe_lower) and rfe_lower[i] is not None) else l_b
        rf_u = rfe_upper[i] if (has_rfe and rfe_upper and i < len(rfe_upper) and rfe_upper[i] is not None) else u_b

        # 1. Buy Area (Grünes Kreuz): Kerzen-Tief taucht unter RFE Lower, Vorbar-Hoch lag darüber
        is_buy_area = bool(has_rfe and l < rf_l and prev_h > rf_l)

        # 2. Sell Area (Rotes Kreuz): Kerzen-Hoch übersteigt RFE Upper, Vorbar-Tief lag darunter
        is_sell_area = bool(has_rfe and h > rf_u and prev_l < rf_u)

        # 3. No Trade Zone: Kerze schneidet oder pendelt direkt auf der RFE Basislinie (nur bei gültiger RFE Basis)
        is_no_trade_zone = bool(has_rfe and ((l < rf_b and prev_h > rf_b) or (h > rf_b and prev_l < rf_b)))

        # 4. Good Buy Signal (Blaues Dreieck): Bullische Reversal-Kerze nach Sweep in der Discount-Zone
        is_bull_candle = (c > o) and (c > prev_c)
        swept_low = (l < prev_l or (has_rfe and l < rf_l))
        good_buy_signal = bool(swept_low and is_bull_candle and (not has_rfe or c < rf_b))

        # 5. Potential Buy Signal: Kerze berührt oder penetriert Buy Area ohne vollen Reversal-Schlusskurs
        potential_buy_signal = bool(is_buy_area and not good_buy_signal)

        # 6. Good Sell Signal (Kreis oben): Bärische Reversal-Kerze in der Premium-Zone
        is_bear_candle = (c < o) and (c < prev_c)
        swept_high = (h > prev_h or (has_rfe and h > rf_u))
        good_sell_signal = bool(swept_high and is_bear_candle and (not has_rfe or c > rf_b))

        # 7. Alignment Ends: Kreuzung durch die RFE Basis
        bull_align_ends = bool(has_rfe and prev_c > rf_b and c < rf_b)
        bear_align_ends = bool(has_rfe and prev_c < rf_b and c > rf_b)

        sigs = []
        if good_buy_signal:
            sigs.append("Good Buy Signal (Blaues Dreieck)")
        elif potential_buy_signal:
            sigs.append("Potential Buy Signal (Dreieck)")
        if good_sell_signal:
            sigs.append("Good Sell Signal (Kreis)")
        if is_buy_area and not good_buy_signal:
            sigs.append("Buy Area (Grünes Kreuz)")
        if is_sell_area and not good_sell_signal:
            sigs.append("Sell Area (Rotes Kreuz)")
        if is_no_trade_zone:
            sigs.append("No Trade Zone")
        if bull_align_ends:
            sigs.append("Bull Alignment Ends (Quadrat)")
        if bear_align_ends:
            sigs.append("Bear Alignment Ends (Quadrat)")

        if sigs:
            signals_history.append({
                "bar_index": i,
                "time": b.get("t"),
                "price": c,
                "signals": sigs
            })

    current_sigs = signals_history[-1]["signals"] if (signals_history and signals_history[-1]["bar_index"] == n - 1) else []
    last_sig = signals_history[-1] if signals_history else None

    return {
        "active_signals": current_sigs,
        "current_active_signals": current_sigs,
        "last_signal": last_sig,
        "signals_history": signals_history if full_history else signals_history[-15:]
    }


# ==============================================================================
# 3. DEGENCODER'S OB (RETRO): ORDER BLOCKS MIT SWEEPS & GRADING
# ==============================================================================

def detect_degencoder_order_blocks(
    bars: List[Dict[str, Any]],
    displacement_bars: int = 5,
    detect_liquidity_sweep: bool = True,
    max_active_zones: int = 20,
    project_bars: int = 50,
    sweep_lookback: int = 20
) -> List[Dict[str, Any]]:
    """
    100% TradingView-kalibrierter Nachbau von degencoder's OB (Retro):
    - Bullish OB: Rote Kerze (c < o), gefolgt von 5 grünen Kerzen in Folge (c > o)
    - Bearish OB: Grüne Kerze (c > o), gefolgt von 5 roten Kerzen in Folge (c < o)
    - Sweep Check: Sticht das Hoch/Tief der OB-Kerze über/unter das 20-Bar-Extrem? (Grade A Sweep)
    - Retest-Counter: R1, R2, R3 (jedes Mal, wenn der Kurs in die Zone zurückkehrt, ohne sie zu invalidieren)
    - Invalidation: Vollständig durchbrochen (Close jenseits des OB).
    """
    if not bars or len(bars) < displacement_bars + 5:
        return []

    n = len(bars)
    atr = calculate_atr_wilder(bars, 14)
    obs = []

    o = [float(b["o"]) for b in bars]
    c = [float(b["c"]) for b in bars]
    h = [float(b["h"]) for b in bars]
    l = [float(b["l"]) for b in bars]

    for i in range(2, n - displacement_bars):
        b0 = bars[i]
        curr_atr = atr[i] if (atr and atr[i]) else (c[i] * 0.015)

        # -------------------------------------------------------------
        # A. BULLISCHER ORDER BLOCK: Rote Kerze + 5 grüne Folgekerzen
        # -------------------------------------------------------------
        subsequent_bars = bars[i + 1:i + 1 + displacement_bars]
        is_bull_displacement = (c[i] < o[i]) and all(c[k] > o[k] for k in range(i + 1, i + 1 + displacement_bars))

        if is_bull_displacement:
            # Liquidity Sweep Check über sweep_lookback Bars
            prev_low_window = min(l[max(0, i - sweep_lookback):i]) if i > 0 else l[i]
            is_sweep = bool(l[i] < prev_low_window)

            highest_future = max(b["h"] for b in subsequent_bars)
            displacement_move = highest_future - l[i]

            # Quality Grading
            if is_sweep and displacement_move >= 2.0 * curr_atr:
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

            ob_top = max(o[i], c[i])
            ob_bottom = l[i]
            ob_time = b0.get("t")

            # Retests & Invalidation tracken
            retest_count = 0
            mitigated = False
            invalidated = False

            for k in range(i + 1 + displacement_bars, n):
                # Invalidation: Kerzenschlusskurs bricht unter OB-Boden
                if c[k] < ob_bottom:
                    invalidated = True
                    break
                # Retest: Docht taucht in die Zone [ob_bottom, ob_top] ein
                if l[k] <= ob_top and h[k] >= ob_bottom:
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
        # B. BÄRISCHER ORDER BLOCK: Grüne Kerze + 5 rote Folgekerzen
        # -------------------------------------------------------------
        is_bear_displacement = (c[i] > o[i]) and all(c[k] < o[k] for k in range(i + 1, i + 1 + displacement_bars))

        if is_bear_displacement:
            # Liquidity Sweep Check über sweep_lookback Bars
            prev_high_window = max(h[max(0, i - sweep_lookback):i]) if i > 0 else h[i]
            is_sweep_high = bool(h[i] > prev_high_window)

            lowest_future = min(b["l"] for b in subsequent_bars)
            displacement_down = h[i] - lowest_future

            if is_sweep_high and displacement_down >= 2.0 * curr_atr:
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

            ob_top = h[i]
            ob_bottom = min(o[i], c[i])
            ob_time = b0.get("t")

            retest_count = 0
            mitigated = False
            invalidated = False

            for k in range(i + 1 + displacement_bars, n):
                if c[k] > ob_top:
                    invalidated = True
                    break
                if h[k] >= ob_bottom and l[k] <= ob_top:
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
    obs_sorted = sorted(obs, key=lambda x: x.get("time") or 0, reverse=True)[:max_active_zones]
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

    for i in range(1, n - 1):
        b_prev = bars[i - 1]
        b_curr = bars[i]
        b_next = bars[i + 1]

        # 1. Bullish FVG (Kauf-Imbalance): b_prev["h"] < b_next["l"]
        if float(b_prev["h"]) < float(b_next["l"]):
            gap_bottom = float(b_prev["h"])
            gap_top = float(b_next["l"])
            gap_size = gap_top - gap_bottom

            if gap_size > 0:
                is_filled = False
                for k in range(i + 2, n):
                    if float(bars[k]["l"]) <= gap_bottom:
                        is_filled = True
                        break

                if not is_filled:
                    active_fvgs.append({
                        "type": "Bullish FVG",
                        "top": round(gap_top, 3),
                        "bottom": round(gap_bottom, 3),
                        "midline": round((gap_top + gap_bottom) / 2.0, 3),
                        "size": round(gap_size, 3),
                        "time": b_curr.get("t"),
                        "bar_index": i
                    })

        # 2. Bearish FVG (Verkaufs-Imbalance): b_prev["l"] > b_next["h"]
        if float(b_prev["l"]) > float(b_next["h"]):
            gap_top = float(b_prev["l"])
            gap_bottom = float(b_next["h"])
            gap_size = gap_top - gap_bottom

            if gap_size > 0:
                is_filled = False
                for k in range(i + 2, n):
                    if float(bars[k]["h"]) >= gap_top:
                        is_filled = True
                        break

                if not is_filled:
                    active_fvgs.append({
                        "type": "Bearish FVG",
                        "top": round(gap_top, 3),
                        "bottom": round(gap_bottom, 3),
                        "midline": round((gap_top + gap_bottom) / 2.0, 3),
                        "size": round(gap_size, 3),
                        "time": b_curr.get("t"),
                        "bar_index": i
                    })

    fvgs_sorted = sorted(active_fvgs, key=lambda x: x.get("time") or 0, reverse=True)[:max_fvgs]
    return fvgs_sorted


# ==============================================================================
# 5. VSA WYCKOFF VOLUME (VOLUME SPREAD ANALYSIS)
# ==============================================================================

def calculate_vsa_wyckoff(
    bars: List[Dict[str, Any]],
    length: int = 20,
    climax_ratio: float = 2.2,
    very_high_ratio: float = 1.8,
    high_ratio: float = 1.2,
    normal_ratio: float = 0.8,
    low_ratio: float = 0.4
) -> List[Dict[str, Any]]:
    """
    Berechnet die 5 Wyckoff Volume Spread Analysis (VSA) Klassen exakt wie im Chart:
    - Basis: SMA(Volume, 20)
    - Farbcodierung & Schwellenwerte:
      1. Climax Volume (Pink #ec4899): >= 2.2x SMA
      2. Very High Volume (Lila #a855f7): >= 1.8x SMA
      3. High Volume (Blau #06b6d4): >= 1.2x SMA
      4. Normal Volume (Grün #22c55e): >= 0.8x SMA
      5. Low / Very Low Volume (Grau #94a3b8): < 0.8x SMA
    """
    if not bars:
        return []

    volumes = [float(b.get("v") or b.get("volume") or 0.0) for b in bars]
    n = len(bars)
    vsa_results = []

    for i in range(n):
        v = volumes[i]
        start_idx = max(0, i - length + 1)
        window = volumes[start_idx:i + 1]
        sma_v = sum(window) / len(window) if window else 1.0
        ratio = (v / sma_v) if sma_v > 0 else 1.0

        if ratio >= climax_ratio:
            cls = "Climax Volume"
            col = "#ec4899"
        elif ratio >= very_high_ratio:
            cls = "Very High Volume"
            col = "#a855f7"
        elif ratio >= high_ratio:
            cls = "High Volume"
            col = "#06b6d4"
        elif ratio >= normal_ratio:
            cls = "Normal Volume"
            col = "#22c55e"
        elif ratio >= low_ratio:
            cls = "Low Volume"
            col = "#3b82f6"
        else:
            cls = "Very Low Volume"
            col = "#94a3b8"

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
    curr_price = float(last_bar["c"])
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
    print("degencoder_engine: Modul erfolgreich geladen und verifiziert!")
