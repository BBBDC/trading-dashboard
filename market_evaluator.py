#!/usr/bin/env python3
"""
TradingView Super-Analyst – Real-Time Market Evaluator & AI Interpretation Engine.
Berechnet für alle 58 Assets im 4h-Zyklus:
1. Multi-Timeframe-Indikatoren (degencoder 13/1.8/233, FVGs, Wyckoff VSA, Fib GP, RSI Divs)
2. Vollständige Interpretation durch Google Gemini KI (falls Key vorhanden)
3. Automatischen Fallback auf das quantitative Confluence-Regelwerk
4. Aktualisiert dashboard/market_analysis_db.json mit echten Kursen & aktuellen Signalen.
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime, timezone

from fetch_real_ohlcv_cache import get_real_bars
from gemini_evaluator import evaluate_batch_with_cascade, load_config as load_gemini_config
from market_schedule import get_market_state
from degencoder_engine import (
    analyze_degencoder_full,
    detect_degencoder_order_blocks,
    detect_degencoder_signals,
    detect_degencoder_fvgs,
    calculate_degencoder_bands,
    calculate_vsa_wyckoff
)

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"
CHARTS_DIR = BASE_DIR / "dashboard" / "charts"


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
    """
    Führt die vollständige Kernanalyse auf einer Zeiteinheit aus:
    - 100% präziser degencoder_engine Nachbau (Bänder, RFE 233, Buy/Sell Pockets, Signale, OB Retro, FVGs, VSA)
    - RSI(14) mit Divergenzerkennung
    - Fibonacci Retracements & Golden Pocket
    """
    if not bars or len(bars) < 15:
        return None
    last_bar = bars[-1]
    closes = [b["c"] for b in bars]
    p = last_bar["c"]

    # 1. degencoder Engine (Bänder, Signale, OB Retro, FVGs, VSA)
    degen = analyze_degencoder_full(bars, timeframe=sym_name)

    # 2. RSI & Divergenzen
    rsi_list = calculate_rsi(closes)
    current_rsi = rsi_list[-1] if rsi_list else 50.0

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

    # 3. Fibonacci Retracement
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

    vsa_info = degen.get("vsa", {})

    return {
        "name": sym_name,
        "price": round(p, 4) if p < 1 else round(p, 2),
        "rsi": current_rsi,
        "trend": degen.get("trend", "BEARISH"),
        "ema_fast": round(degen.get("ema_fast") or p, 2),
        "ema_trend": round(degen.get("rfe_basis") or p, 2),
        "upper_band": round(degen.get("upper_band") or p, 2),
        "lower_band": round(degen.get("lower_band") or p, 2),
        "rfe_basis": round(degen.get("rfe_basis") or p, 2),
        "rfe_upper": round(degen.get("rfe_upper") or p, 2),
        "rfe_lower": round(degen.get("rfe_lower") or p, 2),
        "channel_position": degen.get("channel_position", "Neutral (Im Kanal)"),
        "in_buy_pocket": degen.get("in_buy_pocket", False),
        "in_sell_pocket": degen.get("in_sell_pocket", False),
        "active_signals": degen.get("active_signals", []),
        "recent_signals": degen.get("recent_signals", []),
        "order_blocks": degen.get("order_blocks", []),
        "active_order_block": degen.get("active_order_block"),
        "fvgs": degen.get("fvgs", []),
        "active_fvg": degen.get("active_fvg"),
        "vsa_ratio": vsa_info.get("ratio", 1.0),
        "vsa_class": vsa_info.get("class", "Normal Volume"),
        "vsa_color": vsa_info.get("color", "#22c55e"),
        "divergences": list(set(divs))[-2:],
        "swing_high": round(high_bar["h"], 2),
        "swing_low": round(low_bar["l"], 2),
        "golden_pocket": [gp_min, gp_max],
        "in_golden_pocket": in_golden_pocket
    }


def evaluate_quantitative_confluence(timeframes, asset_info, prev_asset=None):
    """
    Institutionelle Multi-Timeframe Confluence & Hysterese-Engine:
    - Ebene 1: Makro-Regime (1W, 1D, 3D): Bestimmt den Richtungs-Kompass (BULLISH / BEARISH / RANGE).
    - Ebene 2: Taktische Phase (4h): Bestimmt Zonen (Golden Pocket, FVG, Support/Widerstand).
    - Ebene 3: Timing & Trigger (1h): Bestimmt Reversal-Kerzen, RSI-Divergenzen, VSA Stopping Volume.
    - Hysterese: Verhindert Whipsaws/Bias-Flipping bei bloßen 1h/4h-Korrekturen im intakten Trend.
    """
    if isinstance(timeframes, dict) and "1D" in timeframes:
        d_1d = timeframes.get("1D")
        d_1w = timeframes.get("1W")
        d_4h = timeframes.get("4h")
        d_1h = timeframes.get("1h")
        d_3d = timeframes.get("3D")
    else:
        # Legacy Call-Kompatibilität falls Argumente einzeln übergeben wurden
        d_1d = timeframes
        d_1w = None
        d_4h = asset_info if isinstance(asset_info, dict) and "price" in asset_info else None
        d_1h = None
        d_3d = None

    p = d_1d["price"] if d_1d else (d_4h["price"] if d_4h else (d_1h["price"] if d_1h else 0))
    if p == 0:
        return None

    # 1. MAKRO-REGIME BESTIMMEN
    macro_bullish = False
    macro_bearish = False
    reasons = []

    if d_1d:
        if d_1d["trend"] == "BULLISH":
            reasons.append("1D Trend über EMA 233 bullisch")
            if d_1w and d_1w.get("trend") == "BULLISH":
                reasons.append("1W Makro-Trend bullisch bestätigt")
            macro_bullish = True
        else:
            reasons.append("1D Trend unter EMA 233 bärisch")
            if d_1w and d_1w.get("trend") == "BEARISH":
                reasons.append("1W Makro-Trend bärisch bestätigt")
            macro_bearish = True

    # 2. CONFLUENCE PUNKTE
    bull_points = 0
    bear_points = 0

    if macro_bullish:
        bull_points += 25
    elif macro_bearish:
        bear_points += 25

    # A. degencoder Institutional Pockets (Lower Chaos Band unter RFE 233 = Akkumulation)
    in_buy_pocket = False
    in_sell_pocket = False
    if d_1d and d_1d.get("in_buy_pocket"):
        bull_points += 25
        in_buy_pocket = True
        reasons.append("degencoder: 1D Institutional BUY Pocket (Lower Chaos Band unter RFE 233)")
    elif d_4h and d_4h.get("in_buy_pocket"):
        bull_points += 20
        in_buy_pocket = True
        reasons.append("degencoder: 4h Institutional BUY Pocket (Lower Chaos Band unter RFE 233)")

    if d_1d and d_1d.get("in_sell_pocket"):
        bear_points += 25
        in_sell_pocket = True
        reasons.append("degencoder: 1D Institutional SELL Pocket (Upper Chaos Band über RFE 233)")
    elif d_4h and d_4h.get("in_sell_pocket"):
        bear_points += 20
        in_sell_pocket = True
        reasons.append("degencoder: 4h Institutional SELL Pocket (Upper Chaos Band über RFE 233)")

    # B. degencoder Diskrete Signale (Good Buy/Sell, Buy/Sell Area)
    has_degencoder_buy = False
    has_degencoder_sell = False
    for tf_key, tf_data in [("1h", d_1h), ("4h", d_4h), ("1D", d_1d)]:
        if tf_data:
            for sig in tf_data.get("active_signals", []):
                if "Good Buy Signal" in sig:
                    bull_points += 25
                    has_degencoder_buy = True
                    reasons.append(f"degencoder: {tf_key} Good Buy Signal (Blaues Dreieck Umkehrkerze)")
                elif "Potential Buy" in sig or "Buy Area" in sig:
                    bull_points += 15
                    has_degencoder_buy = True
                    reasons.append(f"degencoder: {tf_key} {sig}")
                elif "Good Sell Signal" in sig:
                    bear_points += 25
                    has_degencoder_sell = True
                    reasons.append(f"degencoder: {tf_key} Good Sell Signal (Kreis Top-Erschöpfung)")
                elif "Sell Area" in sig:
                    bear_points += 15
                    has_degencoder_sell = True
                    reasons.append(f"degencoder: {tf_key} {sig}")

    # C. degencoder's OB (Retro) Order Blocks
    active_bull_ob = None
    active_bear_ob = None
    for tf_key, tf_data in [("4h", d_4h), ("1D", d_1d)]:
        if tf_data and tf_data.get("active_order_block"):
            aob = tf_data["active_order_block"]
            if "Bullish" in aob.get("type", ""):
                active_bull_ob = aob
                badge = aob.get("badge", "A")
                pts = 25 if badge in ("A", "R1", "R2", "R3") else 15
                bull_points += pts
                reasons.append(f"degencoder OB: {tf_key} Bullish Order Block [{badge}] ({aob['bottom']} - {aob['top']}) mit Sweep")
            elif "Bearish" in aob.get("type", ""):
                active_bear_ob = aob
                badge = aob.get("badge", "A")
                pts = 25 if badge in ("A", "R1", "R2", "R3") else 15
                bear_points += pts
                reasons.append(f"degencoder OB: {tf_key} Bearish Order Block [{badge}] ({aob['bottom']} - {aob['top']}) mit Sweep")

    # D. degencoder's FVGs (1-Tick Wick Rule)
    for tf_key, tf_data in [("4h", d_4h), ("1D", d_1d)]:
        if tf_data and tf_data.get("active_fvg"):
            afvg = tf_data["active_fvg"]
            if "Bullish" in afvg.get("type", ""):
                bull_points += 15
                reasons.append(f"degencoder FVG: {tf_key} Bullish Imbalance ({afvg['bottom']} - {afvg['top']})")
            elif "Bearish" in afvg.get("type", ""):
                bear_points += 15
                reasons.append(f"degencoder FVG: {tf_key} Bearish Imbalance ({afvg['bottom']} - {afvg['top']})")

    # Golden Pocket (1D / 4h)
    if d_1d and d_1d.get("in_golden_pocket"):
        bull_points += 25
        reasons.append(f"Kurs im 1D Golden Pocket ({d_1d['golden_pocket'][0]} - {d_1d['golden_pocket'][1]})")
    elif d_4h and d_4h.get("in_golden_pocket"):
        bull_points += 20
        reasons.append(f"Kurs im 4h Golden Pocket ({d_4h['golden_pocket'][0]} - {d_4h['golden_pocket'][1]})")

    # Überdehnungen (Channel)
    if d_1d and "Oversold" in d_1d.get("channel_position", ""):
        bull_points += 20
        reasons.append("1D Kurs überdehnt unteres degencoder-Band (Oversold)")
    elif d_1d and "Overbought" in d_1d.get("channel_position", ""):
        bear_points += 20
        reasons.append("1D Kurs überdehnt oberes degencoder-Band (Overbought)")

    # Divergenzen aus 1h, 4h, 1D sammeln
    all_divs = []
    for tf_key, tf_data in [("1h", d_1h), ("4h", d_4h), ("1D", d_1d)]:
        if tf_data:
            for div in tf_data.get("divergences", []):
                all_divs.append(f"{tf_key} {div}")

    for div in all_divs:
        if "Bullische" in div:
            bull_points += 20
            reasons.append(f"Aktiv: {div}")
        elif "Bärische" in div:
            bear_points += 20
            reasons.append(f"Aktiv: {div}")

    # 1h / 4h RSI & VSA
    curr_rsi_1h = d_1h["rsi"] if d_1h else 50
    curr_rsi_4h = d_4h["rsi"] if d_4h else 50
    if curr_rsi_1h < 30 or curr_rsi_4h < 30:
        bull_points += 15
        reasons.append(f"RSI überverkauft (1h: {curr_rsi_1h}, 4h: {curr_rsi_4h})")
    elif curr_rsi_1h > 70 or curr_rsi_4h > 70:
        bear_points += 15
        reasons.append(f"RSI überkauft (1h: {curr_rsi_1h}, 4h: {curr_rsi_4h})")

    curr_vsa_1h = d_1h.get("vsa_class", "") if d_1h else ""
    curr_vsa_4h = d_4h.get("vsa_class", "") if d_4h else ""
    if "Low" in curr_vsa_1h or "Low" in curr_vsa_4h or "Very Low" in curr_vsa_1h:
        if bull_points > bear_points:
            bull_points += 12
            reasons.append("VSA Wyckoff: Verkaufsdruck versiegt ('Low/No Supply')")
    elif "Ultra High" in curr_vsa_1h or "Very High" in curr_vsa_1h:
        reasons.append("VSA Wyckoff: Hoher Volumen-Spike auf 1h")

    # HYSTERESE / ANTI-WHIPSAW:
    prev_sig = (prev_asset or {}).get("signal", "NEUTRAL")

    # LONG VALIDIERUNG (Strikte Trennung Makro vs Pullback):
    long_cand_valid = (
        macro_bullish and
        bull_points >= 65 and
        bull_points > bear_points + 20 and
        curr_rsi_4h <= 65 and
        not (d_1d and "Overbought" in d_1d.get("channel_position", "")) and
        (
            (d_1d and d_1d.get("in_golden_pocket")) or
            (d_4h and d_4h.get("in_golden_pocket")) or
            in_buy_pocket or
            has_degencoder_buy or
            active_bull_ob is not None or
            any("Bullische" in d for d in all_divs) or
            ("Low" in curr_vsa_1h or "Low" in curr_vsa_4h)
        )
    )

    # Wenn zuvor schon LONG war, Trägheit wahren
    if not long_cand_valid and prev_sig == "LONG" and macro_bullish and bull_points >= 50 and curr_rsi_4h <= 65:
        long_cand_valid = True

    # SHORT VALIDIERUNG:
    short_cand_valid = (
        macro_bearish and
        bear_points >= 65 and
        bear_points > bull_points + 20 and
        curr_rsi_4h >= 35 and
        not (d_1d and "Oversold" in d_1d.get("channel_position", "")) and
        (
            (d_1d and "Overbought" in d_1d.get("channel_position", "")) or
            in_sell_pocket or
            has_degencoder_sell or
            active_bear_ob is not None or
            any("Bärische" in d for d in all_divs)
        )
    )

    if not short_cand_valid and prev_sig == "SHORT" and macro_bearish and bear_points >= 50 and curr_rsi_4h >= 35:
        short_cand_valid = True

    if long_cand_valid:
        signal = "LONG"
        score = min(96, 75 + (bull_points - 65) // 2)
        if in_buy_pocket:
            setup_name = "Hypothese 1: degencoder Institutional Buy Pocket Reversal"
        elif active_bull_ob:
            setup_name = f"Hypothese 1: SMC Order Block [{active_bull_ob.get('badge', 'A')}] Confluence"
        elif has_degencoder_buy:
            setup_name = "Hypothese 2: degencoder Indicator Reversal Signal"
        elif (d_1d and d_1d.get("in_golden_pocket")):
            setup_name = "Hypothese 1: SMC Golden Confluence Reversal"
        elif any("1h Bullische" in d for d in all_divs):
            setup_name = "Hypothese 2: Trend Continuation & 1h Trigger"
        else:
            setup_name = "Hypothese 1: SMC Support Reversal"

        entry_low = round(p * 0.992, 2)
        entry_high = round(p * 1.002, 2)
        sl = round(p * 0.965, 2) if asset_info.get("asset_type") != "Crypto" else round(p * 0.95, 2)
        tp1 = round(p + (p - sl) * 1.8, 2)
        tp2 = round(p + (p - sl) * 3.2, 2)
        crv = 3.2
        analyst_note = f"Strikte bullische Konfluenz ({score}%): Makro-Regime intakt ({reasons[0] if reasons else '1D Trend'}). 1h/4h Timing bestätigt nachlassenden Verkaufsdruck an der Support-Zone."

    elif short_cand_valid:
        signal = "SHORT"
        score = min(95, 75 + (bear_points - 65) // 2)
        if in_sell_pocket:
            setup_name = "Hypothese 1: degencoder Institutional Sell Pocket Reversal"
        elif active_bear_ob:
            setup_name = f"Hypothese 1: SMC Order Block [{active_bear_ob.get('badge', 'A')}] Exhaustion"
        elif has_degencoder_sell:
            setup_name = "Hypothese 2: degencoder Indicator Sell Signal"
        elif (d_1d and "Overbought" in d_1d.get("channel_position", "")):
            setup_name = "Hypothese 3: Wyckoff Range Fakeout / Top Exhaustion"
        else:
            setup_name = "Hypothese 1: Bearish Confluence Reversal"

        entry_low = round(p * 0.998, 2)
        entry_high = round(p * 1.008, 2)
        sl = round(p * 1.035, 2) if asset_info.get("asset_type") != "Crypto" else round(p * 1.05, 2)
        tp1 = round(p - (sl - p) * 1.8, 2)
        tp2 = round(p - (sl - p) * 3.2, 2)
        crv = 3.2
        analyst_note = f"Strikte bärische Erschöpfung ({score}%): Überhitzung an HTF-Widerstandszone ({reasons[0] if reasons else 'HTF Resistance'}). Bärische Momentum-Divergenz auf 1h/4h signalisiert Trendwende-Potenzial."

    else:
        signal = "NEUTRAL"
        score = min(58, max(42, 50 + (bull_points - bear_points) // 4))

        # Kristallklare Differenzierung: Gesunder Pullback im Bullentrend vs. Bärenrallye
        if macro_bullish:
            setup_name = "Beobachten / Lauerstellung am Support (Buy the Dip)"
            analyst_note = "Makro-Bullenmarkt intakt: Der 4h/1h-Rücksetzer stellt eine gesunde Konsolidierung dar. Gemäß institutionellem Risikomanagement wird kein Short gehandelt, sondern auf die Bestätigung der nächsten Support-/Value-Zone gelauert."
        elif macro_bearish:
            setup_name = "Beobachten / Warten auf Short-Trigger am Widerstand"
            analyst_note = "Makro-Bärenmarkt aktiv: Temporäre Erholungen auf 1h/4h stellen Bärenmarktrallyes dar. Kein Long-Trade; Abwarten von Erschöpfungs-Signalen an HTF-Resistancen."
        else:
            setup_name = "Konsolidierungsphase / Warten auf HTF-Trigger"
            analyst_note = "Konsolidierungsphase / Kein klares Setup: Der Markt zeigt keine eindeutige Multi-Timeframe-Konfluenz. Gemäß institutionellem Risikomanagement wird Kapital geschont."

        entry_low, entry_high = p, p
        sl = round(p * 0.97, 2)
        tp1, tp2 = round(p * 1.03, 2), round(p * 1.06, 2)
        crv = 2.0

    return {
        "signal": signal,
        "score": score,
        "setup_name": setup_name,
        "crv": crv,
        "entry_range": [entry_low, entry_high],
        "stop_loss": sl,
        "take_profit_1": tp1,
        "take_profit_2": tp2,
        "reasons": reasons[:4],
        "analyst_note": analyst_note,
        "evaluated_by": "quantitative_engine"
    }

    return {
        "signal": signal,
        "score": score,
        "setup_name": setup_name,
        "crv": crv,
        "entry_range": [entry_low, entry_high],
        "stop_loss": sl,
        "take_profit_1": tp1,
        "take_profit_2": tp2,
        "reasons": reasons[:4],
        "analyst_note": analyst_note,
        "evaluated_by": "quantitative_engine"
    }


def analyze_all_markets(due_symbols=None, use_gemini=True, force_all=False):
    """
    Hauptfunktion: Liest alle Assets, lädt frische Kerzen für fällige Märkte, berechnet Indikatoren,
    interpretiert Setups (via Gemini AI oder mathematisches Regelwerk) und speichert DB.
    - due_symbols: Optionales Set/Liste von Symbolen, die aktualisiert werden sollen.
      Nicht fällige Assets behalten ihre vorherige Auswertung und sparen API-Quoten.
    """
    if not DB_FILE.exists():
        print(f"Fehler: {DB_FILE} nicht gefunden!")
        return None

    with open(DB_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)

    assets = db.get("assets", [])
    due_set = set(due_symbols) if due_symbols is not None else None

    if due_set is not None:
        print(f"\nStarte Marktanalyse: {len(due_set)}/{len(assets)} fällige Assets werden aktiv berechnet...")
    else:
        print(f"\nStarte Live-Marktanalyse für alle {len(assets)} Assets...")

    gemini_conf = load_gemini_config()
    has_gemini = use_gemini and gemini_conf.get("enabled", True)
    if has_gemini:
        p_mod = gemini_conf.get("primary_model", "gemini-3.8-flash-high")
        f_mod = gemini_conf.get("fallback_model", "gemini-2.5-flash")
        print("🤖 Gemini KI-Kaskade aktiv:")
        print(f"   • Stufe 1 (Primary Pro): {p_mod}")
        print(f"   • Stufe 2 (Fallback AI): {f_mod}")
        print(f"   • Stufe 3 (Math Core)  : Quantitative SMC & Wyckoff-Engine")
    else:
        print("ℹ️ Verwende quantitative Confluence-Engine (SMC & Wyckoff VSA).")

    analyzed_assets = []
    gemini_batch = []
    now_utc = datetime.now(timezone.utc)

    # Frische TradingView Live-Quotes für alle Assets abrufen & Cache vorab synchronisieren
    try:
        from tv_live_quotes import fetch_tradingview_live_quotes, update_ohlcv_cache_with_live_quotes, SYMBOL_ALIASES
        all_syms = [a["symbol"] for a in assets if "symbol" in a]
        live_quotes = fetch_tradingview_live_quotes(all_syms)
        update_ohlcv_cache_with_live_quotes(live_quotes)
        print(f"⚡ {len(live_quotes)} TradingView Live-Kurse vorab synchronisiert.")
    except Exception as lqe:
        print(f"⚠️ Warnung beim Live-Quotes-Abruf: {lqe}", file=sys.stderr)
        live_quotes = {}
        SYMBOL_ALIASES = {}

    for idx, asset in enumerate(assets, 1):
        sym = asset["symbol"]
        name = asset["name"]
        m_state = get_market_state(sym, now_utc)

        lq = live_quotes.get(sym)
        if not lq:
            alias = SYMBOL_ALIASES.get(sym)
            if alias:
                lq = live_quotes.get(alias)

        # Wenn Asset nicht fällig ist: Vorherige Analyse beibehalten
        if due_set is not None and sym not in due_set:
            cached_asset = dict(asset)
            cached_asset["market_state"] = m_state
            # Wenn Live-Kurs vorliegt: Preis & Zeitstempel immer sofort aktualisieren
            if lq and "price" in lq:
                cached_asset["price"] = lq["price"]
                cached_asset["change_pct"] = lq.get("change_pct", cached_asset.get("change_pct", 0.0))
                cached_asset["last_price_update"] = lq.get("updated_at", now_utc.isoformat())
                cached_asset["last_price_update_str"] = lq.get("updated_at_str", "")
            elif m_state.get("is_open", False):
                try:
                    b_1h_quick = get_real_bars(sym, interval="1h")
                    if b_1h_quick and len(b_1h_quick) > 0:
                        cached_asset["price"] = float(b_1h_quick[-1]["c"])
                except Exception:
                    pass
            analyzed_assets.append(cached_asset)
            continue

        # Echte Kerzen aus Cache holen (1h, 4h, 1D, 1W und 3D für Krypto)
        from market_schedule import classify_symbol
        is_crypto = (classify_symbol(sym).get("category") == "CRYPTO")

        b_1h = get_real_bars(sym, interval="1h")
        b_4h = get_real_bars(sym, interval="4h")
        b_1d = get_real_bars(sym, interval="1D")
        b_1w = get_real_bars(sym, interval="1W")
        b_3d = get_real_bars(sym, interval="3D") if is_crypto else None

        d_1h = analyze_indicators(b_1h, name) if b_1h else None
        d_4h = analyze_indicators(b_4h, name) if b_4h else None
        d_1d = analyze_indicators(b_1d, name) if b_1d else None
        d_1w = analyze_indicators(b_1w, name) if b_1w else None
        d_3d = analyze_indicators(b_3d, name) if b_3d else None

        if lq and "price" in lq:
            current_price = lq["price"]
            change_pct = lq["change_pct"]
            last_price_update = lq["updated_at"]
            last_price_update_str = lq["updated_at_str"]
        else:
            current_price = d_1d["price"] if d_1d else (d_4h["price"] if d_4h else (d_1h["price"] if d_1h else asset.get("price", 100.0)))
            change_pct = asset.get("change_pct", 0.0)
            last_price_update = now_utc.isoformat()
            from tv_live_quotes import TZ_BERLIN
            last_price_update_str = now_utc.astimezone(TZ_BERLIN).strftime("%d.%m. %H:%M CET")

        # Bestehende Charts beibehalten
        charts_info = asset.get("charts", {})

        tf_map = {
            "1h": d_1h,
            "4h": d_4h,
            "1D": d_1d,
            "1W": d_1w
        }
        if is_crypto and d_3d:
            tf_map["3D"] = d_3d

        asset_snapshot = {
            "symbol": sym,
            "name": name,
            "category": asset.get("category", "Allgemein"),
            "asset_type": asset.get("asset_type", "Stock"),
            "price": current_price,
            "change_pct": change_pct,
            "last_price_update": last_price_update,
            "last_price_update_str": last_price_update_str,
            "signal": asset.get("signal", "NEUTRAL"),
            "score": asset.get("score", 50),
            "setup_name": asset.get("setup_name", "Setup-Berechnung"),
            "crv": asset.get("crv", 2.0),
            "entry_range": asset.get("entry_range", [current_price, current_price]),
            "stop_loss": asset.get("stop_loss", round(current_price * 0.95, 2)),
            "take_profit_1": asset.get("take_profit_1", round(current_price * 1.05, 2)),
            "take_profit_2": asset.get("take_profit_2", round(current_price * 1.10, 2)),
            "reasons": asset.get("reasons", ["Initialer Status"]),
            "charts": charts_info,
            "last_analyzed": now_utc.isoformat(),
            "market_state": m_state,
            "timeframes": tf_map
        }

        # Basis quantitative Auswertung durchführen mit Multi-Timeframe & Hysterese
        quant_res = evaluate_quantitative_confluence(tf_map, asset_snapshot, prev_asset=asset)
        if quant_res:
            asset_snapshot.update(quant_res)

        analyzed_assets.append(asset_snapshot)

        if has_gemini:
            prev_sig = asset.get("signal", "NEUTRAL")
            prev_setup = asset.get("setup_name", "")
            m_score = asset_snapshot.get("score", 50)
            in_gp = bool((d_1d and d_1d.get("in_golden_pocket")) or (d_4h and d_4h.get("in_golden_pocket")))
            has_divs = bool((d_1d and d_1d.get("divergences")) or (d_4h and d_4h.get("divergences")) or (d_1h and d_1h.get("divergences")))
            has_degen = bool(
                (d_1d and (d_1d.get("in_buy_pocket") or d_1d.get("in_sell_pocket") or d_1d.get("active_order_block"))) or
                (d_4h and (d_4h.get("in_buy_pocket") or d_4h.get("in_sell_pocket") or d_4h.get("active_order_block") or d_4h.get("active_signals"))) or
                (d_1h and d_1h.get("active_signals"))
            )
            active_setup = (asset_snapshot.get("signal") in ("LONG", "SHORT")) or (prev_sig in ("LONG", "SHORT"))

            # Smart Funnel: Nur Werte mit echtem Setup-Potenzial (Score >= 65, GP/Divergenzen, degencoder Trigger oder aktives Signal)
            if m_score >= 65 or in_gp or has_divs or has_degen or active_setup:
                gemini_batch.append({
                    "symbol": sym,
                    "name": name,
                    "category": asset_snapshot["category"],
                    "current_price": current_price,
                    "previous_signal": prev_sig,
                    "previous_setup": prev_setup,
                    "math_score": m_score,
                    "active_setup": active_setup,
                    "degencoder": {
                        "1D_buy_pocket": d_1d.get("in_buy_pocket", False) if d_1d else False,
                        "1D_sell_pocket": d_1d.get("in_sell_pocket", False) if d_1d else False,
                        "4h_signals": d_4h.get("active_signals", []) if d_4h else [],
                        "1h_signals": d_1h.get("active_signals", []) if d_1h else [],
                        "active_order_block": (d_4h.get("active_order_block") if d_4h else None) or (d_1d.get("active_order_block") if d_1d else None),
                        "active_fvg": (d_4h.get("active_fvg") if d_4h else None) or (d_1d.get("active_fvg") if d_1d else None)
                    },
                    "1W": {"trend": d_1w["trend"] if d_1w else "N/A", "rsi": d_1w["rsi"] if d_1w else 50} if d_1w else {},
                    "1D": {"trend": d_1d["trend"] if d_1d else "N/A", "rsi": d_1d["rsi"] if d_1d else 50, "in_gp": d_1d["in_golden_pocket"] if d_1d else False, "channel": d_1d["channel_position"] if d_1d else "N/A", "divs": d_1d["divergences"] if d_1d else []},
                    "3D": {"trend": d_3d["trend"] if d_3d else "N/A", "rsi": d_3d["rsi"] if d_3d else 50} if d_3d else {},
                    "4h": {"trend": d_4h["trend"] if d_4h else "N/A", "rsi": d_4h["rsi"] if d_4h else 50, "vsa": d_4h["vsa_class"] if d_4h else "N/A", "in_gp": d_4h["in_golden_pocket"] if d_4h else False, "divs": d_4h["divergences"] if d_4h else []},
                    "1h": {"trend": d_1h["trend"] if d_1h else "N/A", "rsi": d_1h["rsi"] if d_1h else 50, "vsa": d_1h["vsa_class"] if d_1h else "N/A", "divs": d_1h["divergences"] if d_1h else []}
                })

    # Falls Gemini aktiv ist: Batches an Gemini Kaskade senden
    last_tier_used = "quantitative_confluence"
    ai_success_count = 0
    if has_gemini and gemini_batch:
        # Smart Funnel: Sortiere nach Dringlichkeit (aktive Setups zuerst, dann Score) und limitiere auf Top-Kandidaten (z. B. 50)
        gemini_batch.sort(key=lambda x: (1 if x.get("active_setup") else 0, x.get("math_score", 0)), reverse=True)
        max_ai_candidates = gemini_conf.get("max_ai_candidates", 50)
        if len(gemini_batch) > max_ai_candidates:
            print(f"\n🌪️ Smart Funnel aktiv: {len(gemini_batch)} potenzielle Setups gefunden -> Fokussiere KI auf Top {max_ai_candidates} High-Conviction Kandidaten.")
            gemini_batch = gemini_batch[:max_ai_candidates]

        batch_size = gemini_conf.get("batch_size", 5)
        print(f"\nSende {len(gemini_batch)} gefilterte High-Conviction Assets in Batches von {batch_size} an KI-Kaskade...")

        # Mapping für schnelles Update
        asset_map = {a["symbol"]: a for a in analyzed_assets}

        for i in range(0, len(gemini_batch), batch_size):
            chunk = gemini_batch[i:i + batch_size]
            print(f"  [KI-Batch {i // batch_size + 1}/{(len(gemini_batch) + batch_size - 1) // batch_size}] Analysiere {len(chunk)} Werte...", end="", flush=True)

            ai_results, err, tier_used = evaluate_batch_with_cascade(chunk)
            last_tier_used = tier_used
            if ai_results and isinstance(ai_results, list):
                for item in ai_results:
                    s = item.get("symbol")
                    if s in asset_map:
                        target = asset_map[s]
                        target["signal"] = item.get("signal", target["signal"])
                        target["score"] = item.get("score", target["score"])
                        target["setup_name"] = item.get("setup_name", target["setup_name"])
                        target["crv"] = item.get("crv", target["crv"])
                        target["entry_range"] = item.get("entry_range", target["entry_range"])
                        target["stop_loss"] = item.get("stop_loss", target["stop_loss"])
                        target["take_profit_1"] = item.get("take_profit_1", target["take_profit_1"])
                        target["take_profit_2"] = item.get("take_profit_2", target["take_profit_2"])
                        if item.get("analyst_note"):
                            target["analyst_note"] = item.get("analyst_note")
                        if item.get("reasons"):
                            target["reasons"] = item.get("reasons")
                        target["evaluated_by"] = tier_used
                        ai_success_count += 1
                print(f" ✅ OK ({tier_used})")
            else:
                print(f" ℹ️ Math-Fallback ({tier_used})")
            time.sleep(0.3)

        print(f"KI-Kaskadenauswertung abgeschlossen: {ai_success_count}/{len(gemini_batch)} Assets erfolgreich durch KI bewertet.")

    # Sortieren nach Score
    analyzed_assets.sort(key=lambda x: x.get("score", 0), reverse=True)

    long_c = sum(1 for a in analyzed_assets if a.get("signal") == "LONG")
    short_c = sum(1 for a in analyzed_assets if a.get("signal") == "SHORT")
    neutral_c = sum(1 for a in analyzed_assets if a.get("signal") == "NEUTRAL")

    db["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    db["total_analyzed"] = len(analyzed_assets)
    db["long_count"] = long_c
    db["short_count"] = short_c
    db["neutral_count"] = neutral_c
    db["assets"] = analyzed_assets
    db["evaluation_engine"] = last_tier_used if (has_gemini and ai_success_count > 0) else "quantitative_confluence"

    # Autonomes Portfolio, Gedächtnis & Nutzer-Positionen aktualisieren
    try:
        from portfolio_engine import update_autonomous_portfolio, evaluate_user_positions
        portfolio_data, memory_data = update_autonomous_portfolio(analyzed_assets)
        user_pos_data = evaluate_user_positions(analyzed_assets)
        db["portfolio"] = portfolio_data
        db["trade_memory"] = memory_data
        db["user_positions"] = user_pos_data.get("positions", [])
        print(f"   🏛️ Autonomes Portfolio aktualisiert: {len(portfolio_data.get('active_trades', []))} offene Trades ({portfolio_data.get('metrics', {}).get('win_rate_pct', 0)}% Win-Rate)")
        print(f"   👤 Eigene Nutzer-Positionen getrackt: {len(user_pos_data.get('positions', []))} Positionen")
    except Exception as pe:
        print(f"   ⚠️ Portfolio-Update Warnung: {pe}")

    try:
        from gemini_quota_tracker import get_quota_summary_for_dashboard
        db["gemini_quota"] = get_quota_summary_for_dashboard()
    except Exception:
        pass

    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Marktanalyse erfolgreich aktualisiert ({len(analyzed_assets)} Werte in {DB_FILE}):")
    print(f"   🟢 Longs: {long_c}  |  🔴 Shorts: {short_c}  |  ⚪ Neutral: {neutral_c}")

    return db


if __name__ == "__main__":
    analyze_all_markets()
