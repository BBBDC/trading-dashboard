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
    """Führt die Kernanalyse auf einer Zeiteinheit aus."""
    if not bars or len(bars) < 15:
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
    ef = ema_fast[-1] if (ema_fast and ema_fast[-1] is not None) else p
    at = atr[-1] if (atr and atr[-1] is not None) else (p * 0.02)
    et = ema_trend[-1] if (ema_trend and ema_trend[-1] is not None) else ef

    upper_band = ef + 1.8 * at
    lower_band = ef - 1.8 * at
    trend = "BULLISH" if p >= et else "BEARISH"

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
    for i in range(max(2, len(bars) - 30), len(bars)):
        c0, c2 = bars[i - 2], bars[i]
        if c2["l"] > c0["h"]:
            gap_pct = (c2["l"] - c0["h"]) / c0["h"] * 100
            ce = (c2["l"] + c0["h"]) / 2.0
            mitigated = any(bars[k]["l"] <= ce for k in range(i + 1, len(bars)))
            if not mitigated and abs(ce - p) / p < 0.15:
                fvgs.append({"type": "Bullish FVG", "top": round(c2["l"], 2), "bottom": round(c0["h"], 2), "ce_50": round(ce, 2), "gap_pct": round(gap_pct, 2)})
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
        "price": round(p, 4) if p < 1 else round(p, 2),
        "rsi": current_rsi,
        "trend": trend,
        "ema_fast": round(ef, 2),
        "ema_trend": round(et, 2),
        "upper_band": round(upper_band, 2),
        "lower_band": round(lower_band, 2),
        "channel_position": channel_pos,
        "vsa_ratio": round(ratio, 2),
        "vsa_class": vsa_class,
        "fvgs": fvgs[:3],
        "divergences": list(set(divs))[-2:],
        "swing_high": round(high_bar["h"], 2),
        "swing_low": round(low_bar["l"], 2),
        "golden_pocket": [gp_min, gp_max],
        "in_golden_pocket": in_golden_pocket
    }


def evaluate_quantitative_confluence(d_1d, d_8h, d_4h, asset_info):
    """Fallback: Mathematische SMC & Wyckoff Confluence-Engine."""
    p = d_1d["price"] if d_1d else (d_4h["price"] if d_4h else 0)
    if p == 0:
        return None

    bull_points = 0
    bear_points = 0
    reasons = []

    if d_1d:
        if d_1d["trend"] == "BULLISH":
            bull_points += 15
            reasons.append("1D Trend über EMA 233 bullisch")
        else:
            bear_points += 15
            reasons.append("1D Trend unter EMA 233 bärisch")

        if d_1d["in_golden_pocket"]:
            bull_points += 25
            reasons.append(f"Kurs im 1D Golden Pocket ({d_1d['golden_pocket'][0]} - {d_1d['golden_pocket'][1]})")

        if "Oversold" in d_1d["channel_position"]:
            bull_points += 20
            reasons.append("1D Kurs überdehnt unteres degencoder-Band (Oversold)")
        elif "Overbought" in d_1d["channel_position"]:
            bear_points += 20
            reasons.append("1D Kurs überdehnt oberes degencoder-Band (Overbought)")

    all_divs = []
    for tf_dict in [d_1d, d_8h, d_4h]:
        if tf_dict:
            all_divs.extend(tf_dict.get("divergences", []))

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

    # ========================================================
    # STRENGSTE INSTITUTIONELLE RISK-MANAGER FILTERREGELN:
    # 70-80% aller Märkte gehören ins "NEUTRAL (Beobachten)".
    # "LONG" und "SHORT" erfordern kompromisslose Multi-Timeframe Konfluenz.
    # ========================================================
    long_cand_valid = (
        bull_points >= 65 and
        bull_points > bear_points + 25 and
        curr_rsi <= 60 and
        not (d_1d and "Overbought" in d_1d.get("channel_position", "")) and
        (
            (d_1d and d_1d.get("in_golden_pocket")) or
            any("Bullische" in d for d in all_divs) or
            ("No Supply" in curr_vsa or "Stopping" in curr_vsa)
        )
    )

    short_cand_valid = (
        bear_points >= 65 and
        bear_points > bull_points + 25 and
        curr_rsi >= 40 and
        not (d_1d and "Oversold" in d_1d.get("channel_position", "")) and
        (
            (d_1d and "Overbought" in d_1d.get("channel_position", "")) or
            any("Bärische" in d for d in all_divs)
        )
    )

    if long_cand_valid:
        signal = "LONG"
        score = min(96, 75 + (bull_points - 65) // 2)
        setup_name = "Hypothese 1: SMC Golden Confluence Reversal" if (d_1d and d_1d.get("in_golden_pocket")) else ("Hypothese 2: Trend Continuation & Hidden Div" if any("Versteckte Bullische" in d for d in all_divs) else "Hypothese 1: SMC Support Reversal")
        entry_low = round(p * 0.992, 2)
        entry_high = round(p * 1.002, 2)
        sl = round(p * 0.965, 2) if asset_info.get("asset_type") != "Crypto" else round(p * 0.95, 2)
        tp1 = round(p + (p - sl) * 1.8, 2)
        tp2 = round(p + (p - sl) * 3.2, 2)
        crv = 3.2
        analyst_note = f"Strikte bullische Konfluenz ({score}%): Multi-Timeframe Support verifiziert ({reasons[0] if reasons else 'HTF Support'}). VSA/RSI bestätigen nachlassenden Verkaufsdruck bei intakter Struktur."

    elif short_cand_valid:
        signal = "SHORT"
        score = min(95, 75 + (bear_points - 65) // 2)
        setup_name = "Hypothese 3: Wyckoff Range Fakeout / Top Exhaustion" if (d_1d and "Overbought" in d_1d.get("channel_position", "")) else "Hypothese 1: Bearish Confluence Reversal"
        entry_low = round(p * 0.998, 2)
        entry_high = round(p * 1.008, 2)
        sl = round(p * 1.035, 2) if asset_info.get("asset_type") != "Crypto" else round(p * 1.05, 2)
        tp1 = round(p - (sl - p) * 1.8, 2)
        tp2 = round(p - (sl - p) * 3.2, 2)
        crv = 3.2
        analyst_note = f"Strikte bärische Erschöpfung ({score}%): Überhitzung an HTF-Widerstandszone ({reasons[0] if reasons else 'HTF Resistance'}). Bärische Momentum-Divergenz signalisiert Trendwende-Potenzial."

    else:
        signal = "NEUTRAL"
        net_diff = abs(bull_points - bear_points)
        score = min(58, max(42, 50 + (bull_points - bear_points) // 4))
        setup_name = "Beobachten / Warten auf HTF-Trigger"
        entry_low, entry_high = p, p
        sl = round(p * 0.97, 2)
        tp1, tp2 = round(p * 1.03, 2), round(p * 1.06, 2)
        crv = 2.0
        analyst_note = "Konsolidierungsphase / Kein klares Setup: Der Markt zeigt keine eindeutige Multi-Timeframe-Konfluenz. Gemäß institutionellem Risikomanagement wird Kapital geschont und auf einen echten Ausbruch oder Re-Test der Key-Levels gewartet."

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


def analyze_all_markets(use_gemini=True):
    """
    Hauptfunktion: Liest alle Assets, lädt frische Kerzen, berechnet Indikatoren,
    interpretiert Setups (via Gemini AI oder mathematisches Regelwerk) und speichert DB.
    """
    if not DB_FILE.exists():
        print(f"Fehler: {DB_FILE} nicht gefunden!")
        return None

    with open(DB_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)

    assets = db.get("assets", [])
    print(f"\nStarte Live-Marktanalyse für {len(assets)} Assets...")

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

    for idx, asset in enumerate(assets, 1):
        sym = asset["symbol"]
        name = asset["name"]

        # Echte Kerzen aus Cache holen
        b_1d = get_real_bars(sym, interval="1D")
        b_8h = get_real_bars(sym, interval="8h")
        b_4h = get_real_bars(sym, interval="4h")

        d_1d = analyze_indicators(b_1d, name) if b_1d else None
        d_8h = analyze_indicators(b_8h, name) if b_8h else None
        d_4h = analyze_indicators(b_4h, name) if b_4h else None

        current_price = d_1d["price"] if d_1d else (d_4h["price"] if d_4h else asset.get("price", 100.0))

        # Bestehende Charts beibehalten
        charts_info = asset.get("charts", {})

        asset_snapshot = {
            "symbol": sym,
            "name": name,
            "category": asset.get("category", "Allgemein"),
            "asset_type": asset.get("asset_type", "Stock"),
            "price": current_price,
            "charts": charts_info,
            "timeframes": {
                "1D": d_1d,
                "8h": d_8h,
                "4h": d_4h
            }
        }

        # Basis quantitative Auswertung durchführen (dient gleichzeitig als Stufe-3-Basis)
        quant_res = evaluate_quantitative_confluence(d_1d, d_8h, d_4h, asset_snapshot)
        if quant_res:
            asset_snapshot.update(quant_res)

        analyzed_assets.append(asset_snapshot)

        if has_gemini:
            gemini_batch.append({
                "symbol": sym,
                "name": name,
                "category": asset_snapshot["category"],
                "current_price": current_price,
                "1D": {"trend": d_1d["trend"] if d_1d else "N/A", "rsi": d_1d["rsi"] if d_1d else 50, "in_gp": d_1d["in_golden_pocket"] if d_1d else False, "channel": d_1d["channel_position"] if d_1d else "N/A", "divs": d_1d["divergences"] if d_1d else []},
                "4h": {"trend": d_4h["trend"] if d_4h else "N/A", "rsi": d_4h["rsi"] if d_4h else 50, "vsa": d_4h["vsa_class"] if d_4h else "N/A", "divs": d_4h["divergences"] if d_4h else []}
            })

    # Falls Gemini aktiv ist: Batches an Gemini Kaskade senden
    last_tier_used = "quantitative_confluence"
    ai_success_count = 0
    if has_gemini and gemini_batch:
        batch_size = gemini_conf.get("batch_size", 8)
        print(f"\nSende {len(gemini_batch)} Assets in Batches von {batch_size} an KI-Kaskade...")

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

    long_c = sum(1 for a in analyzed_assets if a["signal"] == "LONG")
    short_c = sum(1 for a in analyzed_assets if a["signal"] == "SHORT")
    neutral_c = sum(1 for a in analyzed_assets if a["signal"] == "NEUTRAL")

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

    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Marktanalyse erfolgreich aktualisiert ({len(analyzed_assets)} Werte in {DB_FILE}):")
    print(f"   🟢 Longs: {long_c}  |  🔴 Shorts: {short_c}  |  ⚪ Neutral: {neutral_c}")

    return db


if __name__ == "__main__":
    analyze_all_markets()
