#!/usr/bin/env python3
"""
backtest_matrix_engine.py
=========================
Deterministische Multi-Asset & Multi-Timeframe Matrix-Backtest-Engine (0 Tokens, 0 €).
Simuliert die exakte Pine Script / degencoder-Mathematik über 40 Kern-Assets
auf 4 Zeitskalen (15m, 1h, 4h, 1D) in 4 strategischen Modi:

Modi:
1. 'Long & Short'          - Unkorrigierte Baseline (TradingView Standard)
2. 'Nur Long'              - Rein bullische Ausrichtung (Megatrend-Hypothese)
3. 'Nur Short'             - Rein bearische Ausrichtung (Hedge-Hypothese)
4. 'Causal Trend-Filter'   - Trendfolge-Governance (Longs nur über 233 WMA, Shorts darunter)

Features:
- Reibungs-Rechner: 0.055% Gebühr + Slippage / Spread pro Transaktion
- Out-of-Sample Validierung: 70% In-Sample (IS) vs. 30% Out-of-Sample (OOS)
- Institutionelle Metriken: Win-Rate, Profit-Faktor, E(R), Max Drawdown, OOS-Stabilität
- Output: JSON-Matrix für KI-Synthese + HTML-Heatmap für das Dashboard
"""

import json
import math
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from backtest_data_loader import get_cached_bars

BASE_DIR = Path(__file__).resolve().parent
KB_DIR = BASE_DIR / "knowledge_base"
DASH_DIR = BASE_DIR / "dashboard"
OUT_RESULTS_JSON = KB_DIR / "matrix_backtest_results.json"
OUT_SUMMARY_JSON = KB_DIR / "matrix_backtest_summary.json"
OUT_HTML_REPORT = DASH_DIR / "backtest_matrix.html"

# ==============================================================================
# 1. 40-ASSET TEST-UNIVERSUM
# ==============================================================================
UNIVERSE = [
    # Krypto (Binance REST 24/7)
    {"symbol": "BTCUSDT", "name": "Bitcoin", "category": "Crypto", "source": "binance"},
    {"symbol": "ETHUSDT", "name": "Ethereum", "category": "Crypto", "source": "binance"},
    {"symbol": "SOLUSDT", "name": "Solana", "category": "Crypto", "source": "binance"},
    {"symbol": "BNBUSDT", "name": "BNB", "category": "Crypto", "source": "binance"},
    {"symbol": "AVAXUSDT", "name": "Avalanche", "category": "Crypto", "source": "binance"},
    {"symbol": "DOGEUSDT", "name": "Dogecoin", "category": "Crypto", "source": "binance"},
    {"symbol": "LINKUSDT", "name": "Chainlink", "category": "Crypto", "source": "binance"},
    {"symbol": "NEARUSDT", "name": "Near Protocol", "category": "Crypto", "source": "binance"},
    {"symbol": "XRPUSDT", "name": "Ripple", "category": "Crypto", "source": "binance"},
    {"symbol": "ADAUSDT", "name": "Cardano", "category": "Crypto", "source": "binance"},
    {"symbol": "SUIUSDT", "name": "Sui", "category": "Crypto", "source": "binance"},
    {"symbol": "RENDERUSDT", "name": "Render", "category": "Crypto", "source": "binance"},

    # US Big Tech & Semiconductors (Yahoo)
    {"symbol": "NVDA", "name": "Nvidia", "category": "US-Tech", "source": "yahoo"},
    {"symbol": "AAPL", "name": "Apple", "category": "US-Tech", "source": "yahoo"},
    {"symbol": "MSFT", "name": "Microsoft", "category": "US-Tech", "source": "yahoo"},
    {"symbol": "AMZN", "name": "Amazon", "category": "US-Tech", "source": "yahoo"},
    {"symbol": "META", "name": "Meta Platforms", "category": "US-Tech", "source": "yahoo"},
    {"symbol": "GOOGL", "name": "Alphabet (Google)", "category": "US-Tech", "source": "yahoo"},
    {"symbol": "TSLA", "name": "Tesla", "category": "US-Tech", "source": "yahoo"},
    {"symbol": "AVGO", "name": "Broadcom", "category": "US-Tech", "source": "yahoo"},
    {"symbol": "AMD", "name": "Advanced Micro Devices", "category": "US-Tech", "source": "yahoo"},
    {"symbol": "CRWD", "name": "CrowdStrike", "category": "US-Tech", "source": "yahoo"},
    {"symbol": "PLTR", "name": "Palantir", "category": "US-Tech", "source": "yahoo"},
    {"symbol": "NFLX", "name": "Netflix", "category": "US-Tech", "source": "yahoo"},

    # Deutsche Blue Chips (XETRA .DE / Tradegate)
    {"symbol": "SAP.DE", "name": "SAP", "category": "DAX", "source": "yahoo"},
    {"symbol": "SIE.DE", "name": "Siemens", "category": "DAX", "source": "yahoo"},
    {"symbol": "ALV.DE", "name": "Allianz", "category": "DAX", "source": "yahoo"},
    {"symbol": "RHM.DE", "name": "Rheinmetall", "category": "DAX", "source": "yahoo"},
    {"symbol": "ADS.DE", "name": "Adidas", "category": "DAX", "source": "yahoo"},
    {"symbol": "DTE.DE", "name": "Deutsche Telekom", "category": "DAX", "source": "yahoo"},
    {"symbol": "BMW.DE", "name": "BMW", "category": "DAX", "source": "yahoo"},
    {"symbol": "AIR.DE", "name": "Airbus", "category": "DAX", "source": "yahoo"},

    # Globale Indizes, Forex & Rohstoffe (Yahoo)
    {"symbol": "SPY", "name": "S&P 500 ETF", "category": "Index", "source": "yahoo"},
    {"symbol": "QQQ", "name": "Nasdaq 100 ETF", "category": "Index", "source": "yahoo"},
    {"symbol": "^GDAXI", "name": "DAX 40 Index", "category": "Index", "source": "yahoo"},
    {"symbol": "GC=F", "name": "Gold Future", "category": "Commodity", "source": "yahoo"},
    {"symbol": "SI=F", "name": "Silber Future", "category": "Commodity", "source": "yahoo"},
    {"symbol": "CL=F", "name": "Rohöl WTI", "category": "Commodity", "source": "yahoo"},
    {"symbol": "EURUSD=X", "name": "EUR/USD", "category": "Forex", "source": "yahoo"},
    {"symbol": "GBPUSD=X", "name": "GBP/USD", "category": "Forex", "source": "yahoo"}
]

TIMEFRAMES = ["15m", "30m", "1h", "4h", "8h", "1d", "3d", "1w"]
MODES = ["Long & Short", "Nur Long", "Nur Short", "Causal Trend-Filter"]

# ==============================================================================
# 2. INDIKATOREN-MATHEMATIK (IDENTISCH ZU PINE SCRIPT)
# ==============================================================================
def calc_rma(series: List[float], length: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(series)
    if len(series) < length:
        return out
    alpha = 1.0 / length
    s = sum(series[:length]) / length
    out[length - 1] = s
    for i in range(length, len(series)):
        s = alpha * series[i] + (1 - alpha) * s
        out[i] = s
    return out

def calc_wma(series: List[float], length: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(series)
    if len(series) < length:
        return out
    denom = length * (length + 1) / 2.0
    for i in range(length - 1, len(series)):
        win = series[i - length + 1 : i + 1]
        out[i] = sum(v * (k + 1) for k, v in enumerate(win)) / denom
    return out

def calc_stdev(series: List[float], length: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(series)
    if len(series) < length:
        return out
    for i in range(length - 1, len(series)):
        win = series[i - length + 1 : i + 1]
        m = sum(win) / length
        var = sum((x - m) ** 2 for x in win) / length
        out[i] = math.sqrt(var)
    return out

def calc_rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(closes)
    if len(closes) < period + 1:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains += max(diff, 0.0)
        losses += max(-diff, 0.0)
    ag, al = gains / period, losses / period
    out[period] = 100.0 if al == 0 else (100.0 - 100.0 / (1.0 + ag / al))

    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        ag = (ag * (period - 1) + max(diff, 0.0)) / period
        al = (al * (period - 1) + max(-diff, 0.0)) / period
        out[i] = 100.0 if al == 0 else (100.0 - 100.0 / (1.0 + ag / al))
    return out

# ==============================================================================
# 3. EINZELNER BACKTEST-DURCHLAUF
# ==============================================================================
def run_single_backtest(
    bars: List[Dict[str, Any]],
    mode: str = "Long & Short",
    timeframe: str = "1d",
    fee_pct: float = 0.00055, # 0.055% Kommission pro Halfturn
    slippage_pct: float = 0.0002 # 0.02% Slippage
) -> Optional[Dict[str, Any]]:
    n = len(bars)
    # Mindestens 245 Bars für WMA 233
    if n < 245:
        return None

    closes = [b["c"] for b in bars]
    highs = [b["h"] for b in bars]
    lows = [b["l"] for b in bars]
    opens = [b["o"] for b in bars]
    vols = [b["v"] for b in bars]

    # True Range & ATR
    tr = [highs[0] - lows[0]]
    for i in range(1, n):
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    atr14 = calc_rma(tr, 14)

    # RFE WMA 233 & StDev
    wma_len = 233 if n >= 233 else n
    rfe_wma = calc_wma(closes, wma_len)
    rfe_std = calc_stdev(closes, wma_len)
    rsi14 = calc_rsi(closes, 14)

    # VSA SMA20
    vol_sma = [None] * n
    for i in range(19, n):
        vol_sma[i] = sum(vols[i - 19 : i + 1]) / 20.0

    # 70% In-Sample / 30% Out-of-Sample Split-Index
    split_idx = int(n * 0.70)

    # State Variables
    equity = 10000.0
    initial_equity = 10000.0
    risk_pct = 0.01 # 1% Risiko je Trade

    pos_dir = 0 # 1 long, -1 short
    entry_price = 0.0
    sl = 0.0
    tp1 = 0.0
    tp2 = 0.0
    tp1_done = False
    init_risk = 0.0
    pos_size = 0.0
    entry_bar = 0

    trades: List[Dict[str, Any]] = []

    # Timeframe-spezifischer ATR-Puffer
    if timeframe in ("15m", "30m"):
        sl_mult = 0.6
    elif timeframe in ("1h", "4h", "8h"):
        sl_mult = 1.0
    else:  # 1d, 3d, 1w
        sl_mult = 1.5

    start_scan = max(wma_len, 25)

    for i in range(start_scan, n):
        curr_p = closes[i]
        curr_h = highs[i]
        curr_l = lows[i]
        curr_o = opens[i]
        a = atr14[i]
        if a is None or a <= 0:
            continue

        # In-Flight Position Management
        if pos_dir == 1:
            # TP1 Touch (50% Tranche realisieren & SL auf Breakeven)
            if not tp1_done and curr_h >= tp1:
                tp1_done = True
                sl = max(sl, entry_price)

            # Trailing-Stop nach TP1
            if tp1_done:
                trail_stop = curr_h - 2.0 * a
                sl = max(sl, trail_stop)

            # Stop-Loss Touch (Konservativer Schutz vor Optimismus-Bias: Stop-Loss VOR TP2 prüfen!)
            if curr_l <= sl:
                actual_exit = min(sl, curr_o)  # Wenn Eröffnungskurs mit Gap unter Stop liegt
                exit_p = actual_exit * (1.0 - slippage_pct)
                eff_entry = entry_price * (1.0 + slippage_pct)
                if tp1_done:
                    # 50% bei TP1 gesichert, Rest bei Breakeven/Trailing ausgestoppt
                    raw_gain = ((tp1 - eff_entry) * 0.5 + (exit_p - eff_entry) * 0.5)
                else:
                    raw_gain = exit_p - eff_entry
                cost = (eff_entry + exit_p) * fee_pct * pos_size
                pnl = (raw_gain * pos_size) - cost
                realized_r = round(pnl / (equity * risk_pct), 2)
                equity += pnl
                trades.append({
                    "dir": "LONG", "entry_bar": entry_bar, "exit_bar": i,
                    "entry_p": entry_price, "exit_p": exit_p, "pnl": pnl,
                    "r": realized_r, "is_win": pnl > 0, "is_oos": i >= split_idx
                })
                pos_dir = 0
                pos_size = 0.0

            # TP2 Vollziel
            elif curr_h >= tp2:
                exit_p = tp2 * (1.0 - slippage_pct)
                eff_entry = entry_price * (1.0 + slippage_pct)
                raw_gain = ((tp1 - eff_entry) * 0.5 + (exit_p - eff_entry) * 0.5) if tp1_done else (exit_p - eff_entry)
                cost = (eff_entry + exit_p) * fee_pct * pos_size
                pnl = (raw_gain * pos_size) - cost
                realized_r = round(pnl / (equity * risk_pct), 2)
                equity += pnl
                trades.append({
                    "dir": "LONG", "entry_bar": entry_bar, "exit_bar": i,
                    "entry_p": entry_price, "exit_p": exit_p, "pnl": pnl,
                    "r": realized_r, "is_win": pnl > 0, "is_oos": i >= split_idx
                })
                pos_dir = 0
                pos_size = 0.0

        elif pos_dir == -1:
            # TP1 Touch (Short)
            if not tp1_done and curr_l <= tp1:
                tp1_done = True
                sl = min(sl, entry_price)

            if tp1_done:
                trail_stop = curr_l + 2.0 * a
                sl = min(sl, trail_stop)

            # SL Touch (Short: Konservativ vor TP2 prüfen + Gap-Adjust)
            if curr_h >= sl:
                actual_exit = max(sl, curr_o)  # Wenn Eröffnungskurs mit Gap über Stop liegt
                exit_p = actual_exit * (1.0 + slippage_pct)
                eff_entry = entry_price * (1.0 - slippage_pct)
                if tp1_done:
                    raw_gain = ((eff_entry - tp1) * 0.5 + (eff_entry - exit_p) * 0.5)
                else:
                    raw_gain = eff_entry - exit_p
                cost = (eff_entry + exit_p) * fee_pct * pos_size
                pnl = (raw_gain * pos_size) - cost
                realized_r = round(pnl / (equity * risk_pct), 2)
                equity += pnl
                trades.append({
                    "dir": "SHORT", "entry_bar": entry_bar, "exit_bar": i,
                    "entry_p": entry_price, "exit_p": exit_p, "pnl": pnl,
                    "r": realized_r, "is_win": pnl > 0, "is_oos": i >= split_idx
                })
                pos_dir = 0
                pos_size = 0.0

            # TP2 Vollziel
            elif curr_l <= tp2:
                exit_p = tp2 * (1.0 + slippage_pct)
                eff_entry = entry_price * (1.0 - slippage_pct)
                raw_gain = ((eff_entry - tp1) * 0.5 + (eff_entry - exit_p) * 0.5) if tp1_done else (eff_entry - exit_p)
                cost = (eff_entry + exit_p) * fee_pct * pos_size
                pnl = (raw_gain * pos_size) - cost
                realized_r = round(pnl / (equity * risk_pct), 2)
                equity += pnl
                trades.append({
                    "dir": "SHORT", "entry_bar": entry_bar, "exit_bar": i,
                    "entry_p": entry_price, "exit_p": exit_p, "pnl": pnl,
                    "r": realized_r, "is_win": pnl > 0, "is_oos": i >= split_idx
                })
                pos_dir = 0
                pos_size = 0.0

        # Wenn flat: Setup-Prüfung für neuen Trade
        if pos_dir == 0:
            c_high = max(highs[i - 4 : i + 1])
            c_low = min(lows[i - 4 : i + 1])
            up_chaos = c_high + 1.8 * a
            lo_chaos = c_low - 1.8 * a
            mid_chaos = (c_high + c_low) / 2.0

            r_basis = rfe_wma[i]
            r_std = rfe_std[i]
            if r_basis is None or r_std is None:
                continue
            r_upper = r_basis + 1.618 * r_std
            r_lower = r_basis - 1.618 * r_std

            # Diskrete Signale
            buy_area = (curr_l < r_lower) and (highs[i - 1] > r_lower)
            sell_area = (curr_h > r_upper) and (lows[i - 1] < r_upper)
            ntz = ((curr_l < r_basis) and (highs[i - 1] > r_basis)) or ((curr_h > r_basis) and (lows[i - 1] < r_basis))

            good_buy = (curr_l < lows[i - 1] or curr_l < r_lower) and (curr_p > curr_o) and (curr_p < r_basis) and (curr_l <= lo_chaos or buy_area)
            good_sell = (curr_h > highs[i - 1] or curr_h > r_upper) and (curr_p < curr_o) and (curr_p > r_basis) and (curr_h >= up_chaos or sell_area)

            # Sweeps & VSA
            sweep_bull = curr_l == min(lows[i - 19 : i + 1])
            sweep_bear = curr_h == max(highs[i - 19 : i + 1])
            vsa_spike = vols[i] > 1.3 * (vol_sma[i] or 1.0)

            # 3-Säulen A+ Scoring
            p1_l = (25 if buy_area else 0) + (10 if curr_p < mid_chaos else 0)
            p2_l = (25 if good_buy else 0) + (15 if sweep_bull else 0)
            p3_l = 10 if vsa_spike else 0
            score_l = 0 if ntz else (p1_l + p2_l + p3_l)

            p1_s = (25 if sell_area else 0) + (10 if curr_p > mid_chaos else 0)
            p2_s = (25 if good_sell else 0) + (15 if sweep_bear else 0)
            p3_s = 10 if vsa_spike else 0
            score_s = 0 if ntz else (p1_s + p2_s + p3_s)

            # Causal Trend Filter (Governance: Trend-Steigung des WMA233 über 5 Bars + RSI Bias)
            # Behebt den Code-Bug der Vorversion: Erlaubt Discount-Käufe (curr_p < r_basis), solange der übergeordnete 233-Trend aufwärts zeigt!
            prev_basis = rfe_wma[i - 5] if (i >= 5 and rfe_wma[i - 5] is not None) else r_basis
            wma_slope_bull = (r_basis >= prev_basis)
            wma_slope_bear = (r_basis <= prev_basis)
            curr_rsi = rsi14[i] or 50.0
            is_causal_long_ok = wma_slope_bull and (curr_rsi > 45.0)
            is_causal_short_ok = wma_slope_bear and (curr_rsi < 55.0)

            # Modus-Prüfung
            allow_long = mode in ("Long & Short", "Nur Long") or (mode == "Causal Trend-Filter" and is_causal_long_ok)
            allow_short = mode in ("Long & Short", "Nur Short") or (mode == "Causal Trend-Filter" and is_causal_short_ok)

            # Exekution Long
            swing_low = min(lows[i - 9 : i + 1])
            swing_high = max(highs[i - 9 : i + 1])
            sl_buf = sl_mult * a

            if allow_long and score_l >= 60 and curr_p > (swing_low - sl_buf):
                sl_cand = swing_low - sl_buf
                risk_dist = curr_p - sl_cand
                # Stop muss mindestens 1.2x ATR entfernt sein (Anti-Rausch-Gate)
                if risk_dist >= 1.2 * a and (risk_dist / curr_p) <= 0.08:
                    pos_dir = 1
                    entry_price = curr_p
                    sl = sl_cand
                    init_risk = risk_dist
                    t1_target = max(r_basis, curr_p + 1.2 * risk_dist)
                    t2_target = max(up_chaos, curr_p + 2.0 * risk_dist)
                    tp1 = min(t1_target, t2_target)
                    tp2 = max(t1_target, t2_target)
                    tp1_done = False
                    entry_bar = i
                    risk_cash = equity * risk_pct
                    pos_size = risk_cash / risk_dist

            elif allow_short and score_s >= 60 and (swing_high + sl_buf) > curr_p and pos_dir == 0:
                sl_cand = swing_high + sl_buf
                risk_dist = sl_cand - curr_p
                if risk_dist >= 1.2 * a and (risk_dist / curr_p) <= 0.08:
                    pos_dir = -1
                    entry_price = curr_p
                    sl = sl_cand
                    init_risk = risk_dist
                    t1_target = min(r_basis, curr_p - 1.2 * risk_dist)
                    t2_target = min(lo_chaos, curr_p - 2.0 * risk_dist)
                    tp1 = max(t1_target, t2_target)
                    tp2 = min(t1_target, t2_target)
                    tp1_done = False
                    entry_bar = i
                    risk_cash = equity * risk_pct
                    pos_size = risk_cash / risk_dist

    # Metriken auswerten
    total_trades = len(trades)
    if total_trades == 0:
        return {
            "trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "total_return_pct": 0.0, "expectancy_r": 0.0, "total_r": 0.0,
            "max_dd_pct": 0.0, "is_wr": 0.0, "oos_wr": 0.0, "oos_trades": 0,
            "oos_r": 0.0, "verdict": "NO_TRADES"
        }

    wins = [t for t in trades if t["is_win"]]
    losses = [t for t in trades if not t["is_win"]]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)
    wr = round(len(wins) / total_trades * 100.0, 1)
    tot_r = round(sum(t["r"] for t in trades), 2)
    exp_r = round(tot_r / total_trades, 3)
    ret_pct = round(((equity - initial_equity) / initial_equity) * 100.0, 2)

    # Max Drawdown
    peak = initial_equity
    max_dd = 0.0
    cur_eq = initial_equity
    for t in trades:
        cur_eq += t["pnl"]
        if cur_eq > peak:
            peak = cur_eq
        dd = (peak - cur_eq) / peak * 100.0
        if dd > max_dd:
            max_dd = dd

    # In-Sample vs Out-of-Sample
    is_trades = [t for t in trades if not t["is_oos"]]
    oos_trades = [t for t in trades if t["is_oos"]]
    is_wr = round(sum(1 for t in is_trades if t["is_win"]) / len(is_trades) * 100.0, 1) if is_trades else 0.0
    oos_wr = round(sum(1 for t in oos_trades if t["is_win"]) / len(oos_trades) * 100.0, 1) if oos_trades else 0.0
    oos_r = round(sum(t["r"] for t in oos_trades), 2)

    # Einstufung / Urteil (Institutionelle Klassifikation)
    if total_trades >= 15 and exp_r >= 0.15 and oos_r >= 0 and pf >= 1.25:
        verdict = "ROBUST_EDGE" # Grün
    elif exp_r >= -0.05 and oos_r >= -2.0:
        verdict = "NEUTRAL_UNCERTAIN" # Gelb
    else:
        verdict = "TOXIC_BLEED" # Rot

    return {
        "trades": total_trades,
        "win_rate": wr,
        "profit_factor": pf,
        "total_return_pct": ret_pct,
        "expectancy_r": exp_r,
        "total_r": tot_r,
        "max_dd_pct": round(max_dd, 1),
        "is_trades": len(is_trades),
        "is_wr": is_wr,
        "oos_trades": len(oos_trades),
        "oos_wr": oos_wr,
        "oos_r": oos_r,
        "verdict": verdict
    }

# ==============================================================================
# 4. GESAMTE MATRIX-AUSFÜHRUNG ÜBER ALLE ASSETS & TIMEFRAMES
# ==============================================================================
def run_full_matrix_suite():
    print("\n" + "=" * 78)
    print("🚀 STARTE MULTI-ASSET & MULTI-TIMEFRAME MATRIX-BACKTEST (0 TOKENS)")
    print(f"   Universum: {len(UNIVERSE)} Assets | Timeframes: {len(TIMEFRAMES)} | Modi: {len(MODES)}")
    print(f"   Gesamt-Kombinationen: {len(UNIVERSE) * len(TIMEFRAMES) * len(MODES)} Simulationen")
    print("=" * 78)

    start_time = time.time()
    results = {}
    summary_list = []

    total_combos = len(UNIVERSE) * len(TIMEFRAMES)
    progress_count = 0

    for asset in UNIVERSE:
        sym = asset["symbol"]
        name = asset["name"]
        cat = asset["category"]
        results[sym] = {"name": name, "category": cat, "source": asset["source"], "timeframes": {}}

        for tf in TIMEFRAMES:
            progress_count += 1
            # 1. Daten aus Cache / API laden
            bars = get_cached_bars(asset, interval=tf)
            results[sym]["timeframes"][tf] = {"bars_count": len(bars), "modes": {}}

            if len(bars) < 245:
                # print(f"  [{progress_count}/{total_combos}] ⚠️ {sym} ({tf}): zu wenige Bars ({len(bars)} < 245)")
                continue

            # 2. Reibungskosten je Asset-Klasse (gemäß Fable 5.2 Realitäts-Audit)
            if cat == "Forex":
                fee_val = 0.00005    # 0.5 bp Gebühr
                slip_val = 0.0001    # 1.0 bp Slippage (reale FX-Liquidität)
            elif cat in ("US-Tech", "DAX", "Index", "Commodity"):
                fee_val = 0.0002     # 2 bp
                slip_val = 0.0001    # 1 bp
            else:  # Crypto
                fee_val = 0.00055    # 5.5 bp
                slip_val = 0.0002    # 2 bp

            # 3. Die 4 Modi simulieren
            for mode in MODES:
                res = run_single_backtest(bars, mode=mode, timeframe=tf, fee_pct=fee_val, slippage_pct=slip_val)
                if res:
                    results[sym]["timeframes"][tf]["modes"][mode] = res
                    summary_list.append({
                        "symbol": sym,
                        "name": name,
                        "category": cat,
                        "timeframe": tf,
                        "mode": mode,
                        "trades": res["trades"],
                        "win_rate": res["win_rate"],
                        "profit_factor": res["profit_factor"],
                        "total_return_pct": res["total_return_pct"],
                        "expectancy_r": res["expectancy_r"],
                        "total_r": res["total_r"],
                        "max_dd_pct": res["max_dd_pct"],
                        "oos_trades": res["oos_trades"],
                        "oos_wr": res["oos_wr"],
                        "oos_r": res["oos_r"],
                        "verdict": res["verdict"]
                    })

        print(f"  ✓ [{progress_count}/{total_combos}] {name:20s} ({sym:10s}) vollständig gerechnet.")

    elapsed = round(time.time() - start_time, 1)
    print(f"\n✅ Alle Simulationen in {elapsed}s erfolgreich abgeschlossen!")

    # 1. Speichern der Rohdaten-Matrix
    with open(OUT_RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"  💾 Rohdaten gespeichert: {OUT_RESULTS_JSON}")

    # 2. Speichern der Zusammenfassung für LLMs
    with open(OUT_SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary_list, f, indent=2, ensure_ascii=False)
    print(f"  💾 KI-Zusammenfassung gespeichert: {OUT_SUMMARY_JSON}")

    # 3. Interaktiven HTML-Report erstellen
    generate_html_matrix_report(summary_list, elapsed)

    return summary_list

# ==============================================================================
# 5. HTML REPORT GENERIERUNG
# ==============================================================================
def generate_html_matrix_report(summary: List[Dict[str, Any]], elapsed_s: float):
    """Baut eine responsive HTML-Heatmap für das Dashboard."""
    robust_count = sum(1 for s in summary if s["verdict"] == "ROBUST_EDGE")
    neutral_count = sum(1 for s in summary if s["verdict"] == "NEUTRAL_UNCERTAIN")
    toxic_count = sum(1 for s in summary if s["verdict"] == "TOXIC_BLEED")
    total_sims = len(summary)

    # Sortiere nach Erwartungswert E(R) absteigend
    sorted_summary = sorted(summary, key=lambda x: x["expectancy_r"], reverse=True)

    rows_html = []
    for item in sorted_summary:
        v = item["verdict"]
        badge_cls = "bg-emerald-950/80 text-emerald-400 border border-emerald-500/40" if v == "ROBUST_EDGE" else (
            "bg-amber-950/80 text-amber-300 border border-amber-500/40" if v == "NEUTRAL_UNCERTAIN" else
            "bg-rose-950/80 text-rose-400 border border-rose-500/40"
        )
        badge_txt = "✅ ROBUST EDGE" if v == "ROBUST_EDGE" else (
            "⚠️ NEUTRAL / CHOP" if v == "NEUTRAL_UNCERTAIN" else "🛑 TOXIC BLEED"
        )

        r_color = "text-emerald-400 font-bold" if item["total_r"] > 0 else (
            "text-slate-400" if item["total_r"] == 0 else "text-rose-400 font-bold"
        )
        exp_color = "text-emerald-400" if item["expectancy_r"] > 0 else (
            "text-slate-400" if item["expectancy_r"] == 0 else "text-rose-400"
        )

        rows_html.append(f"""
        <tr class="border-b border-slate-800/60 hover:bg-slate-800/30 transition text-xs font-mono">
            <td class="p-2.5 font-sans font-bold text-white flex items-center gap-1.5">
                <span>{item['name']}</span>
                <span class="text-[10px] text-slate-500">({item['symbol']})</span>
            </td>
            <td class="p-2.5 text-slate-400">{item['category']}</td>
            <td class="p-2.5 font-bold text-indigo-400">{item['timeframe']}</td>
            <td class="p-2.5 font-sans text-slate-300">{item['mode']}</td>
            <td class="p-2.5 text-right">{item['trades']}</td>
            <td class="p-2.5 text-right font-bold text-white">{item['win_rate']}%</td>
            <td class="p-2.5 text-right">{item['profit_factor']}</td>
            <td class="p-2.5 text-right {r_color}">{item['total_r']:+.1f}R</td>
            <td class="p-2.5 text-right {exp_color}">{item['expectancy_r']:+.3f}R</td>
            <td class="p-2.5 text-right text-slate-400">{item['max_dd_pct']}%</td>
            <td class="p-2.5 text-right font-sans text-[11px]">{item['oos_trades']} Tr. | {item['oos_wr']}% | {item['oos_r']:+.1f}R</td>
            <td class="p-2.5 text-center">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold {badge_cls}">{badge_txt}</span>
            </td>
        </tr>
        """)

    html_content = f"""<!DOCTYPE html>
<html lang="de" class="dark">
<head>
  <meta charset="UTF-8">
  <title>Cross-Asset & Multi-Timeframe Matrix Backtest</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-200 p-6 max-w-7xl mx-auto space-y-6">
  <div class="flex items-center justify-between border-b border-slate-800 pb-4">
    <div>
      <h1 class="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
        <span>📊 Cross-Asset & Multi-Timeframe Matrix-Backtest</span>
      </h1>
      <p class="text-xs text-slate-400 mt-1">40 Kern-Assets &bull; 8 Timeframes (15m, 30m, 1h, 4h, 8h, 1D, 3D, 1W) &bull; 4 strategische Modi &bull; Berechnet in {elapsed_s}s (0 Tokens)</p>
    </div>
    <div class="flex items-center gap-3">
      <a href="index.html" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-bold rounded-lg border border-slate-700 transition">
        ← Zurück zum Dashboard
      </a>
    </div>
  </div>

  <!-- KPI Summary Cards -->
  <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
    <div class="p-4 rounded-xl bg-slate-900 border border-slate-800">
      <span class="text-xs text-slate-400">Simulationen Gesamt</span>
      <div class="text-2xl font-bold text-white mt-1">{total_sims}</div>
    </div>
    <div class="p-4 rounded-xl bg-emerald-950/40 border border-emerald-500/30">
      <span class="text-xs text-emerald-400 font-bold">Robuster Edge (Grün)</span>
      <div class="text-2xl font-bold text-emerald-400 mt-1">{robust_count}</div>
    </div>
    <div class="p-4 rounded-xl bg-amber-950/40 border border-amber-500/30">
      <span class="text-xs text-amber-300 font-bold">Neutral / Fragil (Gelb)</span>
      <div class="text-2xl font-bold text-amber-300 mt-1">{neutral_count}</div>
    </div>
    <div class="p-4 rounded-xl bg-rose-950/40 border border-rose-500/30">
      <span class="text-xs text-rose-400 font-bold">Toxisch / Bleed (Rot)</span>
      <div class="text-2xl font-bold text-rose-400 mt-1">{toxic_count}</div>
    </div>
  </div>

  <!-- Filter Bar -->
  <div class="flex flex-wrap items-center justify-between gap-3 bg-slate-900/60 p-3 rounded-xl border border-slate-800 text-xs">
    <div class="flex items-center gap-2">
      <span class="font-bold text-slate-400">Filter Verdict:</span>
      <button onclick="filterVerdict('ALL')" class="px-2.5 py-1 rounded bg-indigo-600 text-white font-bold">Alle ({total_sims})</button>
      <button onclick="filterVerdict('ROBUST_EDGE')" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-emerald-950 text-emerald-400 font-bold border border-slate-700">Robust ({robust_count})</button>
      <button onclick="filterVerdict('NEUTRAL_UNCERTAIN')" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-amber-950 text-amber-300 font-bold border border-slate-700">Neutral ({neutral_count})</button>
      <button onclick="filterVerdict('TOXIC_BLEED')" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-rose-950 text-rose-400 font-bold border border-slate-700">Toxisch ({toxic_count})</button>
    </div>
    <input type="text" id="search-input" onkeyup="filterSearch()" placeholder="Asset oder Symbol suchen..." class="px-3 py-1 bg-slate-950 border border-slate-800 rounded text-xs text-white placeholder-slate-500 w-48">
  </div>

  <!-- Main Matrix Table -->
  <div class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/40">
    <table id="matrix-table" class="w-full text-left border-collapse">
      <thead>
        <tr class="bg-slate-900 text-slate-400 text-[11px] uppercase font-bold border-b border-slate-800 select-none">
          <th class="p-2.5">Asset</th>
          <th class="p-2.5">Kategorie</th>
          <th class="p-2.5">TF</th>
          <th class="p-2.5">Modus</th>
          <th class="p-2.5 text-right">Trades</th>
          <th class="p-2.5 text-right">Win-Rate</th>
          <th class="p-2.5 text-right">PF</th>
          <th class="p-2.5 text-right">ΣR PnL</th>
          <th class="p-2.5 text-right">E(R)</th>
          <th class="p-2.5 text-right">Max DD</th>
          <th class="p-2.5 text-right">Out-of-Sample (30%)</th>
          <th class="p-2.5 text-center">Urteil</th>
        </tr>
      </thead>
      <tbody>
        {"".join(rows_html)}
      </tbody>
    </table>
  </div>

  <script>
    function filterVerdict(v) {{
      const trs = document.querySelectorAll('#matrix-table tbody tr');
      trs.forEach(tr => {{
        if (v === 'ALL') {{
          tr.style.display = '';
        }} else {{
          tr.style.display = tr.innerHTML.includes(v) ? '' : 'none';
        }}
      }});
    }}

    function filterSearch() {{
      const q = document.getElementById('search-input').value.toLowerCase();
      const trs = document.querySelectorAll('#matrix-table tbody tr');
      trs.forEach(tr => {{
        tr.style.display = tr.textContent.toLowerCase().includes(q) ? '' : 'none';
      }});
    }}
  </script>
</body>
</html>
"""
    with open(OUT_HTML_REPORT, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"  🌐 Interaktiver HTML-Report erstellt: {OUT_HTML_REPORT}")

if __name__ == "__main__":
    run_full_matrix_suite()
