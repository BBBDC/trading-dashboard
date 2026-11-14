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
    Institutionelle 3-Säulen Konfluenz- & Hysterese-Engine (Stufe 2 Empirisch Kalibriert):
    Basiert auf 80.150 realen Signal-Events und schützt vor Fehlausbrüchen:
    - Säule 1: Zonen-Potenzial Z (Wo steht der Kurs? Max 30 Pkt)
      * degencoder Institutional Pocket: 25 Pkt
      * SMC Order Block Grade A mit Sweep: 20 Pkt
      * Golden Pocket (0.618 - 0.65): 15 Pkt
      * SMC Order Block Grade B/C: 12 Pkt
      * SMC FVG Imbalance: 10 Pkt
      (Zonen kumulieren nicht endlos: Cap bei 30 Pkt)

    - Säule 2: Timing & Trigger T (Was macht die Kerze JETZT? Max 40 Pkt)
      * degencoder Good Buy Signal (Blaues Dreieck): 35 Pkt (6.81x Asymmetrie!)
      * degencoder Buy Area (Grünes Kreuz): 25 Pkt (56.5% Win-Rate)
      * VSA Wyckoff "No Supply" am Support: 20 Pkt (52.6% Win-Rate)
      * RSI Bullische Divergenz (1h/4h): 20 Pkt
      * Rausch-Filter: Bear Alignment Ends / Noise-Spikes: 0 Pkt (Penalisierung)

    - Konfluenz-Gate & Trigger-Sperre C:
      * Liegt Zone (Z >= 15) UND Trigger (T >= 20) vor -> +15 Pkt Konfluenz-Bonus!
      * Liegt NUR eine Zone vor (T < 15) -> Trigger-Sperre: Maximaler Score 68% (Kein Trade-Einstieg!)

    - Säule 3: Regime-Multiplikator M:
      * Trendfolge (1D & 1W über 233-EMA für Longs): x 1.15
      * Range / Neutral: x 1.00
      * Counter-Trend (Short im Bullenmarkt): x 0.75 (Schutz vor Bull-Squeezes)
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

    # 1. MAKRO-REGIME BESTIMMEN (1D & 1W Trend gegen 233 EMA)
    macro_bullish = False
    macro_bearish = False
    reasons = []

    if d_1d:
        if d_1d.get("trend") == "BULLISH":
            reasons.append("1D Trend über EMA 233 bullisch")
            if d_1w and d_1w.get("trend") == "BULLISH":
                reasons.append("1W Makro-Trend bullisch bestätigt")
            macro_bullish = True
        else:
            reasons.append("1D Trend unter EMA 233 bärisch")
            if d_1w and d_1w.get("trend") == "BEARISH":
                reasons.append("1W Makro-Trend bärisch bestätigt")
            macro_bearish = True

    # -------------------------------------------------------------
    # SÄULE 1: ZONEN-POTENZIAL Z (Max. 30 Punkte)
    # -------------------------------------------------------------
    z_bull = 0
    z_bear = 0

    # A. degencoder Institutional Pockets
    in_buy_pocket = False
    in_sell_pocket = False
    if d_1d and d_1d.get("in_buy_pocket"):
        z_bull += 25
        in_buy_pocket = True
        reasons.append("degencoder: 1D Institutional BUY Pocket (Lower Chaos < RFE 233)")
    elif d_4h and d_4h.get("in_buy_pocket"):
        z_bull += 20
        in_buy_pocket = True
        reasons.append("degencoder: 4h Institutional BUY Pocket (Lower Chaos < RFE 233)")

    if d_1d and d_1d.get("in_sell_pocket"):
        z_bear += 25
        in_sell_pocket = True
        reasons.append("degencoder: 1D Institutional SELL Pocket (Upper Chaos > RFE 233)")
    elif d_4h and d_4h.get("in_sell_pocket"):
        z_bear += 20
        in_sell_pocket = True
        reasons.append("degencoder: 4h Institutional SELL Pocket (Upper Chaos > RFE 233)")

    # B. SMC Order Blocks (Retests)
    active_bull_ob = None
    active_bear_ob = None
    for tf_key, tf_data in [("4h", d_4h), ("1D", d_1d)]:
        if tf_data and tf_data.get("active_order_block"):
            aob = tf_data["active_order_block"]
            if "Bullish" in aob.get("type", ""):
                active_bull_ob = aob
                badge = aob.get("badge", "A")
                is_sweep = aob.get("is_sweep", False)
                pts = 20 if is_sweep else 12
                z_bull += pts
                reasons.append(f"SMC OB: {tf_key} Bullish Order Block [{badge}] Retest")
            elif "Bearish" in aob.get("type", ""):
                active_bear_ob = aob
                badge = aob.get("badge", "A")
                is_sweep = aob.get("is_sweep", False)
                pts = 20 if is_sweep else 12
                z_bear += pts
                reasons.append(f"SMC OB: {tf_key} Bearish Order Block [{badge}] Retest")

    # C. Fibonacci Golden Pocket (0.618 - 0.650)
    if d_1d and d_1d.get("in_golden_pocket"):
        z_bull += 15
        reasons.append(f"SMC: Kurs im 1D Golden Pocket ({d_1d['golden_pocket'][0]} - {d_1d['golden_pocket'][1]})")
    elif d_4h and d_4h.get("in_golden_pocket"):
        z_bull += 12
        reasons.append(f"SMC: Kurs im 4h Golden Pocket ({d_4h['golden_pocket'][0]} - {d_4h['golden_pocket'][1]})")

    # D. SMC Fair Value Gaps (FVG Imbalance)
    for tf_key, tf_data in [("4h", d_4h), ("1D", d_1d)]:
        if tf_data and tf_data.get("active_fvg"):
            afvg = tf_data["active_fvg"]
            if "Bullish" in afvg.get("type", ""):
                z_bull += 10
                reasons.append(f"SMC FVG: {tf_key} Bullish Imbalance ({afvg['bottom']} - {afvg['top']})")
            elif "Bearish" in afvg.get("type", ""):
                z_bear += 10
                reasons.append(f"SMC FVG: {tf_key} Bearish Imbalance ({afvg['bottom']} - {afvg['top']})")

    # E. Überdehnungen (Channel)
    if d_1d and "Oversold" in d_1d.get("channel_position", ""):
        z_bull += 10
    elif d_1d and "Overbought" in d_1d.get("channel_position", ""):
        z_bear += 10

    # Zonen deckeln auf max 30 Punkte (Zwei Zonen ohne Trigger machen keinen Trade!)
    z_bull = min(30, z_bull)
    z_bear = min(30, z_bear)

    # -------------------------------------------------------------
    # SÄULE 2: TIMING & REVERSAL-TRIGGER T (Max. 40 Punkte)
    # -------------------------------------------------------------
    t_bull = 0
    t_bear = 0
    has_good_buy = False
    has_good_sell = False
    has_buy_trigger = False
    has_sell_trigger = False

    # A. Diskrete degencoder Signale
    for tf_key, tf_data in [("1h", d_1h), ("4h", d_4h), ("1D", d_1d)]:
        if tf_data:
            for sig in tf_data.get("active_signals", []):
                # 🌟 Elite Edge: Good Buy Signal (6.81x Asymmetrie!)
                if "Good Buy Signal" in sig:
                    t_bull += 35
                    has_good_buy = True
                    has_buy_trigger = True
                    reasons.append(f"🌟 degencoder: {tf_key} Good Buy Signal (Blaues Dreieck Umkehrkerze)")
                elif "Buy Area" in sig:
                    t_bull += 25
                    has_buy_trigger = True
                    reasons.append(f"🟢 degencoder: {tf_key} Buy Area (Grünes Kreuz am Band-Boden)")
                elif "Potential Buy" in sig:
                    t_bull += 20
                    has_buy_trigger = True
                    reasons.append(f"degencoder: {tf_key} Potential Buy Signal")
                elif "Good Sell Signal" in sig:
                    t_bear += 35
                    has_good_sell = True
                    has_sell_trigger = True
                    reasons.append(f"🌟 degencoder: {tf_key} Good Sell Signal (Kreis Top-Erschöpfung)")
                elif "Sell Area" in sig:
                    t_bear += 25
                    has_sell_trigger = True
                    reasons.append(f"🟢 degencoder: {tf_key} Sell Area (Rotes Kreuz am Band-Top)")
                # 🔴 Rausch-Filterung: Bear/Bull Alignment Ends erhalten 0 Bonuspunkte!
                elif "Alignment Ends" in sig:
                    pass

    # B. Divergenzen (1h, 4h, 1D RSI)
    all_divs = []
    for tf_key, tf_data in [("1h", d_1h), ("4h", d_4h), ("1D", d_1d)]:
        if tf_data:
            for div in tf_data.get("divergences", []):
                all_divs.append(f"{tf_key} {div}")

    for div in all_divs:
        if "Bullische" in div:
            t_bull += 20
            has_buy_trigger = True
            reasons.append(f"Aktiv: {div}")
        elif "Bärische" in div:
            t_bear += 20
            has_sell_trigger = True
            reasons.append(f"Aktiv: {div}")

    # C. VSA Wyckoff Volumen-Trigger
    curr_vsa_1h = d_1h.get("vsa_class", "") if d_1h else ""
    curr_vsa_4h = d_4h.get("vsa_class", "") if d_4h else ""
    if "Low" in curr_vsa_1h or "Low" in curr_vsa_4h or "Very Low" in curr_vsa_1h:
        if z_bull > 0 and macro_bullish:
            t_bull += 20
            has_buy_trigger = True
            reasons.append("VSA Wyckoff: Verkaufsdruck versiegt ('No Supply' am Support)")
        elif z_bear > 0 and macro_bearish:
            t_bear += 15
            has_sell_trigger = True
            reasons.append("VSA Wyckoff: Geringes Kaufvolumen am Widerstand ('No Demand')")

    # RSI Extremwerte
    curr_rsi_1h = d_1h["rsi"] if d_1h else 50
    curr_rsi_4h = d_4h["rsi"] if d_4h else 50
    if curr_rsi_1h < 30 or curr_rsi_4h < 30:
        t_bull += 10
    elif curr_rsi_1h > 70 or curr_rsi_4h > 70:
        t_bear += 10

    # Trigger deckeln auf max 40 Punkte
    t_bull = min(40, t_bull)
    t_bear = min(40, t_bear)

    # -------------------------------------------------------------
    # KONFLUENZ-GATE & TRIGGER-SPERRE C
    # -------------------------------------------------------------
    # Liegt eine Zone vor (Z >= 15) UND ein Trigger (T >= 20)?
    bull_confluence = bool(z_bull >= 15 and t_bull >= 20)
    bear_confluence = bool(z_bear >= 15 and t_bear >= 20)

    confluence_bonus_bull = 15 if bull_confluence else 0
    confluence_bonus_bear = 15 if bear_confluence else 0

    if bull_confluence:
        reasons.append("🎯 Empirischer Konfluenz-Bonus: Zone + Reversal-Trigger bestätigt (+15 Pkt)")
    if bear_confluence:
        reasons.append("🎯 Empirischer Konfluenz-Bonus: Widerstandszone + Sell-Trigger bestätigt (+15 Pkt)")

    # -------------------------------------------------------------
    # SÄULE 3: REGIME-MULTIPLIKATOR M & AGGREGATION
    # -------------------------------------------------------------
    base_bull_points = z_bull + t_bull + confluence_bonus_bull + (25 if macro_bullish else 0)
    base_bear_points = z_bear + t_bear + confluence_bonus_bear + (25 if macro_bearish else 0)

    # Regime Multiplikatoren: Trendfolge belohnen, Gegen-Trend dämpfen
    mult_bull = 1.15 if macro_bullish else 0.85
    mult_bear = 1.15 if macro_bearish else 0.75  # Stärkere Dämpfung für Shorts im Bullenmarkt!

    bull_points = round(base_bull_points * mult_bull)
    bear_points = round(base_bear_points * mult_bear)

    # HYSTERESE / ANTI-WHIPSAW:
    prev_sig = (prev_asset or {}).get("signal", "NEUTRAL")

    # TRIGGER-SPERRE:
    # Ohne Reversal-Trigger (t_bull < 15) darf NIEMALS ein Kauf-Signal generiert werden!
    trigger_lock_bull = not (has_buy_trigger or t_bull >= 20)
    trigger_lock_bear = not (has_sell_trigger or t_bear >= 20)

    # LONG VALIDIERUNG (Strikte Trennung Makro vs Pullback + Trigger-Pflicht):
    long_cand_valid = (
        macro_bullish and
        not trigger_lock_bull and
        bull_points >= 65 and
        bull_points > bear_points + 20 and
        curr_rsi_4h <= 65 and
        not (d_1d and "Overbought" in d_1d.get("channel_position", "")) and
        (z_bull >= 15 or in_buy_pocket or active_bull_ob is not None)
    )

    # Wenn zuvor schon LONG war, Trägheit wahren solange Makro intakt und kein Verkaufsdruck
    if not long_cand_valid and prev_sig == "LONG" and macro_bullish and bull_points >= 50 and curr_rsi_4h <= 65:
        long_cand_valid = True

    # SHORT VALIDIERUNG (Erfordert intakten Bärenmarkt + Sell-Trigger):
    short_cand_valid = (
        macro_bearish and
        not trigger_lock_bear and
        bear_points >= 65 and
        bear_points > bull_points + 20 and
        curr_rsi_4h >= 35 and
        not (d_1d and "Oversold" in d_1d.get("channel_position", "")) and
        (z_bear >= 15 or in_sell_pocket or active_bear_ob is not None)
    )

    if not short_cand_valid and prev_sig == "SHORT" and macro_bearish and bear_points >= 50 and curr_rsi_4h >= 35:
        short_cand_valid = True

    # -------------------------------------------------------------
    # FINALE SCORE- & SETUP-BESTIMMUNG
    # -------------------------------------------------------------
    if long_cand_valid:
        signal = "LONG"
        # Score-Berechnung: Skaliert von 80 bis 98%
        if bull_confluence and (has_good_buy or in_buy_pocket):
            score = min(98, 88 + (bull_points - 80) // 2)
            setup_name = "🌟 A+ Konfluenz: degencoder Pocket/Trigger & Trendfolge"
        elif active_bull_ob and bull_confluence:
            score = min(95, 84 + (bull_points - 75) // 2)
            setup_name = f"Hypothese 1: SMC Order Block [{active_bull_ob.get('badge', 'A')}] Confirmed Retest"
        elif in_buy_pocket:
            score = min(92, 82 + (bull_points - 70) // 2)
            setup_name = "Hypothese 1: degencoder Institutional Buy Pocket Reversal"
        elif has_good_buy:
            score = min(92, 82 + (bull_points - 70) // 2)
            setup_name = "Hypothese 2: degencoder Indicator Reversal Signal"
        else:
            score = min(88, 80 + (bull_points - 65) // 2)
            setup_name = "Hypothese 1: SMC Support Reversal"

        entry_low = round(p * 0.992, 2)
        entry_high = round(p * 1.002, 2)

        # Stop-Loss strukturell verankern
        if active_bull_ob and active_bull_ob.get("bottom"):
            sl = round(active_bull_ob["bottom"] * 0.995, 2)
        elif in_buy_pocket and d_1d and d_1d.get("lower_band"):
            sl = round(d_1d["lower_band"] * 0.995, 2)
        else:
            sl = round(p * 0.965, 2) if asset_info.get("asset_type") != "Crypto" else round(p * 0.95, 2)

        tp1 = round(p + (p - sl) * 1.8, 2)
        tp2 = round(p + (p - sl) * 3.5, 2)
        crv = round((tp1 - p) / max(0.0001, (p - sl)), 1)
        analyst_note = f"3-Säulen-Konfluenz ({score}%): Makro-Trend intakt, Zone bestätigt, Reversal-Trigger aktiv ({reasons[0] if reasons else 'Intakt'})."

    elif short_cand_valid:
        signal = "SHORT"
        if bear_confluence and (has_good_sell or in_sell_pocket):
            score = min(98, 88 + (bear_points - 80) // 2)
            setup_name = "🌟 A+ Konfluenz: degencoder Sell-Pocket & Reversal Trigger"
        elif active_bear_ob and bear_confluence:
            score = min(95, 84 + (bear_points - 75) // 2)
            setup_name = f"Hypothese 1: SMC Order Block [{active_bear_ob.get('badge', 'A')}] Confirmed Exhaustion"
        elif in_sell_pocket:
            score = min(92, 82 + (bear_points - 70) // 2)
            setup_name = "Hypothese 1: degencoder Institutional Sell Pocket Reversal"
        elif has_good_sell:
            score = min(92, 82 + (bear_points - 70) // 2)
            setup_name = "Hypothese 2: degencoder Indicator Sell Signal"
        else:
            score = min(88, 80 + (bear_points - 65) // 2)
            setup_name = "Hypothese 1: Bearish Confluence Reversal"

        entry_low = round(p * 0.998, 2)
        entry_high = round(p * 1.008, 2)

        if active_bear_ob and active_bear_ob.get("top"):
            sl = round(active_bear_ob["top"] * 1.005, 2)
        elif in_sell_pocket and d_1d and d_1d.get("upper_band"):
            sl = round(d_1d["upper_band"] * 1.005, 2)
        else:
            sl = round(p * 1.035, 2) if asset_info.get("asset_type") != "Crypto" else round(p * 1.05, 2)

        tp1 = round(p - (sl - p) * 1.8, 2)
        tp2 = round(p - (sl - p) * 3.5, 2)
        crv = round((p - tp1) / max(0.0001, (sl - p)), 1)
        analyst_note = f"3-Säulen-Erschöpfung ({score}%): Makro-Bärenmarkt aktiv, Widerstandszone bestätigt, Sell-Trigger aktiv."

    else:
        signal = "NEUTRAL"
        # Wenn eine Zone vorliegt, aber kein Trigger -> Trigger-Sperre greift (Score 65-68%)
        if z_bull >= 15 or in_buy_pocket or active_bull_ob is not None:
            score = 68
            setup_name = "Beobachten / Lauerstellung am Support (Warten auf Trigger)"
            analyst_note = "Unterstützungszone erreicht: Der Kurs sitzt in einer validen Zone, wartet jedoch auf einen bestätigenden Reversal-Trigger (Trigger-Sperre aktiv, Score auf 68% gedeckelt)."
        elif z_bear >= 15 or in_sell_pocket or active_bear_ob is not None:
            score = 68
            setup_name = "Beobachten / Warten auf Short-Trigger am Widerstand"
            analyst_note = "Widerstandszone erreicht: Keine vorzeitige Positionierung ohne Reversal-Bestätigung (Trigger-Sperre aktiv)."
        elif macro_bullish:
            score = min(62, max(45, 52 + (bull_points - bear_points) // 4))
            setup_name = "Beobachten / Lauerstellung am Support (Buy the Dip)"
            analyst_note = "Makro-Bullenmarkt intakt: Der Rücksetzer stellt eine gesunde Konsolidierung dar. Noch keine Konfluenzzone erreicht."
        elif macro_bearish:
            score = min(62, max(45, 52 + (bear_points - bull_points) // 4))
            setup_name = "Beobachten / Warten auf Short-Trigger am Widerstand"
            analyst_note = "Makro-Bärenmarkt aktiv: Temporäre Erholungen auf 1h/4h stellen Bärenmarktrallyes dar."
        else:
            score = 50
            setup_name = "Konsolidierungsphase / Warten auf HTF-Trigger"
            analyst_note = "Konsolidierungsphase / Kein klares Setup: Der Markt zeigt keine eindeutige Multi-Timeframe-Richtung."

        entry_low, entry_high = p, p
        sl = round(p * 0.97, 2)
        tp1, tp2 = round(p * 1.03, 2), round(p * 1.06, 2)
        crv = 2.0

    # Primären Handlungs-Timeframe & Zeithorizont ableiten
    res_asset_probe = {
        "signal": signal,
        "score": score,
        "setup_name": setup_name,
        "reasons": reasons[:4],
        "analyst_note": analyst_note,
        "timeframes": timeframes if isinstance(timeframes, dict) else {}
    }
    primary_tf, tf_label, holding_period = derive_asset_timeframe_context(res_asset_probe)

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
        "evaluated_by": "quantitative_engine",
        "primary_timeframe": primary_tf,
        "timeframe_label": tf_label,
        "holding_period": holding_period
    }


def derive_asset_timeframe_context(asset):
    """
    Ermittelt den primären Handlungs-Timeframe (1h, 4h, 1D, 3D, 1W),
    das Timeframe-Label (z. B. '4h Core Swing') sowie die erwartete Haltedauer (z. B. '2–5 Tage').
    Basiert auf den konkreten Trigger-Kerzen, Order-Blocks und Zeithorizonten.
    """
    sig = asset.get("signal", "NEUTRAL")
    setup = asset.get("setup_name", "")
    reasons = asset.get("reasons", [])
    reasons_text = " ".join(reasons).lower()
    tfs = asset.get("timeframes", {})
    d1 = tfs.get("1D") if isinstance(tfs, dict) else None
    d4 = tfs.get("4h") if isinstance(tfs, dict) else None
    d1h = tfs.get("1h") if isinstance(tfs, dict) else None
    d1w = tfs.get("1W") if isinstance(tfs, dict) else None

    if sig in ("LONG", "SHORT"):
        # 1. 1h Fast Swing Trigger
        if any(k in reasons_text for k in ["1h good buy", "1h good sell", "1h buy area", "1h sell area", "1h rsi", "1h divergence"]):
            return "1h", "1h Fast Swing", "6–24 Std."

        # 2. 4h Core Swing Trigger / Zone Retest
        if any(k in reasons_text for k in [
            "4h good buy", "4h good sell", "4h buy area", "4h sell area", "4h rsi",
            "4h bullish order block", "4h bearish order block", "4h institutional",
            "4h golden pocket", "4h imbalance"
        ]):
            return "4h", "4h Core Swing", "2–5 Tage"

        # 3. 1D Position Trigger / Zone Retest
        if any(k in reasons_text for k in [
            "1d good buy", "1d good sell", "1d buy area", "1d sell area", "1d rsi",
            "1d bullish order block", "1d bearish order block", "1d institutional",
            "1d golden pocket", "1d imbalance"
        ]):
            return "1D", "1D Position", "1–3 Wochen"

        # 4. 3D / 1W Makro Trend
        if any(k in setup.lower() or k in reasons_text for k in ["weekly", "1w", "3d", "makro", "macro"]):
            return "1W", "3D/1W Makro", "Mehrere Wochen"

        # 5. Rückgriff auf Timeframe-Indikatordaten
        if d4 and (d4.get("active_order_block") or d4.get("in_buy_pocket") or d4.get("in_sell_pocket") or d4.get("active_signals")):
            return "4h", "4h Core Swing", "2–5 Tage"
        if d1 and (d1.get("active_order_block") or d1.get("in_buy_pocket") or d1.get("in_sell_pocket") or d1.get("active_signals")):
            return "1D", "1D Position", "1–3 Wochen"
        if d1h and d1h.get("active_signals"):
            return "1h", "1h Fast Swing", "6–24 Std."

        # Standard-Fallback für institutionelle Swings
        return "4h", "4h Core Swing", "2–5 Tage"

    else:
        # Neutral / Watchlist
        if d4 and (d4.get("active_order_block") or d4.get("in_buy_pocket") or d4.get("in_sell_pocket") or d4.get("in_golden_pocket")):
            return "4h", "4h Lauerstellung", "Warten auf Trigger"
        if d1 and (d1.get("active_order_block") or d1.get("in_buy_pocket") or d1.get("in_sell_pocket") or d1.get("in_golden_pocket")):
            return "1D", "1D Lauerstellung", "Warten auf Trigger"
        if "unterstützungszone" in asset.get("analyst_note", "").lower() or "support" in setup.lower():
            return "4h", "4h Lauerstellung", "Warten auf Trigger"
        if "widerstandszone" in asset.get("analyst_note", "").lower() or "widerstand" in setup.lower():
            return "4h", "4h Lauerstellung", "Warten auf Trigger"
        if d1 and d1.get("trend") in ("BULLISH", "BEARISH"):
            return "4h", "4h Beobachtung", "Konsolidierung"
        return "1D", "1D Neutral", "Kein Setup"


def assign_macro_headwind_and_evaluator_labels(analyzed_assets):
    """
    Ermittelt den übergeordneten Trend der Leitmärkte (SPY, DAX, BTC) und markiert
    jedes Asset mit Makro-Gegenwind-Status und lesbarem Evaluator-Badge.
    """
    benchmark_trends = {}
    for a in analyzed_assets:
        sym = a.get("symbol", "")
        tfs = a.get("timeframes") or {}
        d1 = tfs.get("1D") or {}
        t1d = d1.get("trend")
        if sym == "AMEX:SPY":
            benchmark_trends["US"] = t1d or "NEUTRAL"
        elif sym == "XETR:DAX":
            benchmark_trends["EU"] = t1d or "NEUTRAL"
        elif "BTCUSD" in sym and "CRYPTO" not in benchmark_trends:
            benchmark_trends["CRYPTO"] = t1d or "NEUTRAL"

    for a in analyzed_assets:
        cat = str(a.get("category", "")).lower()
        sym = str(a.get("symbol", ""))
        atype = str(a.get("asset_type", ""))

        if atype == "Crypto" or "crypto" in cat or "btcusd" in sym.lower():
            bm_key = "CRYPTO"
            bm_name = "Bitcoin"
        elif "dax" in cat or sym.startswith(("XETR:", "FWB:", "TRADEGATE:")):
            bm_key = "EU"
            bm_name = "DAX"
        else:
            bm_key = "US"
            bm_name = "S&P 500"

        bm_trend = benchmark_trends.get(bm_key, "NEUTRAL")
        sig = a.get("signal", "NEUTRAL")

        macro_headwind = False
        headwind_label = ""
        if sig == "LONG" and bm_trend == "BEARISH":
            macro_headwind = True
            headwind_label = f"⚠️ Makro-Gegenwind ({bm_name} 1D bärisch)"
        elif sig == "SHORT" and bm_trend == "BULLISH":
            macro_headwind = True
            headwind_label = f"⚠️ Makro-Gegenwind gegen Short ({bm_name} 1D bullisch)"

        a["macro_headwind"] = macro_headwind
        a["headwind_label"] = headwind_label
        a["benchmark_market"] = f"{bm_name} ({bm_trend})"

        ev = str(a.get("evaluated_by", "quantitative_engine"))
        if "gemini-3.8" in ev or "pro" in ev.lower():
            eval_badge = "🤖 Gemini 3.8 Pro"
        elif "gemini" in ev:
            eval_badge = "⚡ Gemini Flash"
        elif "quantitative" in ev or ev in ("math", "confluence"):
            eval_badge = "📐 Quantitative Engine"
        else:
            eval_badge = "📐 Algorithmus"
        a["evaluator_badge"] = eval_badge

        # Handlungs-Timeframe & Haltedauer sicherstellen
        tf, tf_lbl, hp = derive_asset_timeframe_context(a)
        a["primary_timeframe"] = tf
        a["timeframe_label"] = tf_lbl
        a["holding_period"] = hp


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

    # Makro-Gegenwind der Leitmärkte & Evaluator-Badges ermitteln
    assign_macro_headwind_and_evaluator_labels(analyzed_assets)

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
