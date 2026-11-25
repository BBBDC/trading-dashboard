#!/usr/bin/env python3
"""
backtest_audit/run_s2_holdout.py
================================
Einmalige Oeffnung des versiegelten Holdouts (2022-01-01..2026-11-20)
ausschliesslich fuer Strategie 2 (IBS + RSI(2)), da nur S2 das Oeffnungs-Gate
bestanden hat. Strategie 1 bleibt gesperrt.
"""

import json
import math
import random
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import (
    AUDIT_CACHE_DIR,
    Position,
    S2_CONTROLS,
    S2_UNIVERSE,
    S2_US_INDICES,
    _apply_daily_financing,
    compute_metrics,
    load_audit_data,
    run_benchmark_sma200_hold,
    run_strategy2,
)
from indicators import atr_wilder, sma

IS_START, VAL_END = "2008-03-01", "2021-12-31"
HO_START, HO_END = "2022-01-01", "2026-11-20"


def run_s2_regime_monte_carlo(
    data: Dict[str, Any],
    actual_sharpe: float,
    actual_trades_count: int,
    start_date: str = IS_START,
    end_date: str = HO_END,
    n_mc: int = 1000,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Nullhypothese: Zufaellige Einstiege innerhalb des Regimes Close > SMA(200)
    mit gleicher Signalwahrscheinlichkeit, gleichen Caps und gleicher Exit-Logik.
    """
    dates = data["dates"]
    rf_daily = data["rf_daily"]
    series = data["series"]
    n_bars = len(dates)
    half_cost = (10.0 / 10000.0) / 2.0

    smas = {sym: sma(series[sym]["c"], 200) for sym in S2_UNIVERSE}
    atrs = {sym: atr_wilder(series[sym]["h"], series[sym]["l"], series[sym]["c"], 14) for sym in S2_UNIVERSE}

    # Zaehle verfuegbare Regime-Tage (Close > SMA200) im Fenster
    eligible_pairs = 0
    for t in range(n_bars):
        d = dates[t]
        if d < start_date or d >= end_date:
            continue
        for sym in S2_UNIVERSE:
            sm = smas[sym][t]
            if sm is not None and series[sym]["valid"][t] and series[sym]["c"][t] > sm:
                eligible_pairs += 1

    # Kalibriere Signal-Wahrscheinlichkeit auf ungefaehr gleiche Trade-Anzahl
    p_sig = min(0.25, (actual_trades_count * 1.15) / max(1, eligible_pairs))
    rng = random.Random(seed)
    win_idxs = [i for i, d in enumerate(dates) if start_date <= d <= end_date]

    mc_sharpes: List[float] = []
    ge_cnt = 0
    for _ in range(n_mc):
        equity = 100000.0
        positions: Dict[str, Position] = {}
        pending_exits: set = set()
        pending_entries: List[Any] = []
        excess_rets = [0.0] * n_bars

        for t in win_idxs:
            d = dates[t]
            eq_prev = equity
            prev_closes = {sym: series[sym]["c"][t - 1] for sym in positions}

            for sym in list(pending_exits):
                if sym in positions:
                    pos = positions.pop(sym)
                    fill = series[sym]["o"][t]
                    raw_pnl = pos.shares * (fill - pos.entry_price)
                    exit_cost = pos.shares * fill * half_cost
                    mtm_prev = pos.shares * (prev_closes[sym] - pos.entry_price)
                    equity += (raw_pnl - mtm_prev) - exit_cost
            pending_exits.clear()

            rng.shuffle(pending_entries)
            for sym, atr_sig in pending_entries:
                if sym in positions or len(positions) >= 3:
                    continue
                if sym in S2_US_INDICES and any(p_sym in S2_US_INDICES for p_sym in positions):
                    continue
                fill = series[sym]["o"][t]
                if fill <= 0 or atr_sig <= 0:
                    continue
                stop_dist = 3.0 * atr_sig
                shares = min((0.005 * equity) / stop_dist, (0.33 * equity) / fill)
                cur_gross = sum(p.shares * series[p.symbol]["o"][t] for p in positions.values())
                rem_cap = max(0.0, equity - cur_gross)
                if shares * fill > rem_cap:
                    if rem_cap < 0.10 * (shares * fill):
                        continue
                    shares = rem_cap / fill
                equity -= (shares * fill) * half_cost
                positions[sym] = Position(sym, 1, shares, fill, t, d, shares * stop_dist, fill - stop_dist, fill)
                prev_closes[sym] = fill
            pending_entries.clear()

            for sym in list(positions.keys()):
                pos = positions[sym]
                if series[sym]["l"][t] <= pos.stop_price:
                    positions.pop(sym)
                    fill_s = min(series[sym]["o"][t], pos.stop_price)
                    raw_pnl = pos.shares * (fill_s - pos.entry_price)
                    exit_cost = pos.shares * fill_s * half_cost
                    mtm_prev = pos.shares * (prev_closes[sym] - pos.entry_price)
                    equity += (raw_pnl - mtm_prev) - exit_cost

            long_not = 0.0
            for sym, pos in positions.items():
                c_p = series[sym]["c"][t]
                equity += pos.shares * (c_p - prev_closes[sym])
                long_not += pos.shares * c_p
            equity += _apply_daily_financing(eq_prev, long_not, 0.0, rf_daily[t])
            excess_rets[t] = ((equity / eq_prev - 1.0) if eq_prev > 0 else 0.0) - rf_daily[t]

            if d == end_date or t + 1 >= n_bars or dates[t + 1] > end_date:
                continue

            for sym, pos in positions.items():
                if series[sym]["c"][t] > series[sym]["h"][t - 1] or ((t - pos.entry_idx) + 1) >= 7:
                    pending_exits.add(sym)

            for sym in S2_UNIVERSE:
                if sym in positions or not series[sym]["valid"][t]:
                    continue
                sm = smas[sym][t]
                a14 = atrs[sym][t]
                if sm is not None and a14 is not None and series[sym]["c"][t] > sm:
                    if rng.random() < p_sig:
                        pending_entries.append((sym, a14))

        win_ex = [excess_rets[i] for i in win_idxs]
        m = sum(win_ex) / len(win_ex)
        v = sum((x - m) ** 2 for x in win_ex) / (len(win_ex) - 1)
        sr = (m / math.sqrt(v) * math.sqrt(252.0)) if v > 1e-18 else 0.0
        mc_sharpes.append(sr)
        if sr >= actual_sharpe:
            ge_cnt += 1

    mc_sharpes.sort()
    return {
        "n_mc": n_mc,
        "actual_sharpe": round(actual_sharpe, 3),
        "mc_median_sharpe": round(mc_sharpes[len(mc_sharpes) // 2], 3),
        "mc_p95_sharpe": round(mc_sharpes[int(0.95 * len(mc_sharpes))], 3),
        "p_value_vs_regime_mc": round(ge_cnt / n_mc, 4),
    }


def main() -> None:
    syms = sorted(set(S2_UNIVERSE + S2_CONTROLS))
    # Explizite Oeffnung des Holdouts ausschliesslich fuer Strategie 2 nach bestandenem Gate
    data = load_audit_data(syms, max_date=HO_END, allow_holdout=True)
    dates = data["dates"]
    rf_daily = data["rf_daily"]

    # 1. Separater Holdout-Lauf (startet flach per P9!)
    s2_ho = run_strategy2(data, S2_UNIVERSE, HO_START, HO_END, 0.20, 15.0, 7, cost_bps=10.0)
    s2_ho_2x = run_strategy2(data, S2_UNIVERSE, HO_START, HO_END, 0.20, 15.0, 7, cost_bps=20.0)
    s2_ho_ctrl = run_strategy2(data, S2_CONTROLS, HO_START, HO_END, 0.20, 15.0, 7, cost_bps=10.0)
    b4_ho = run_benchmark_sma200_hold(data, S2_UNIVERSE, HO_START, HO_END, cost_bps=10.0)

    m_ho = compute_metrics(dates, s2_ho["excess_rets"], rf_daily, s2_ho["trades"], HO_START, HO_END)
    m_ho_2x = compute_metrics(dates, s2_ho_2x["excess_rets"], rf_daily, s2_ho_2x["trades"], HO_START, HO_END)
    m_ho_ctrl = compute_metrics(dates, s2_ho_ctrl["excess_rets"], rf_daily, s2_ho_ctrl["trades"], HO_START, HO_END)
    m_b4_ho = compute_metrics(dates, b4_ho, rf_daily, [], HO_START, HO_END)

    # 2. Gesamtzeitraum (2008-03-01 .. 2026-11-20)
    s2_full = run_strategy2(data, S2_UNIVERSE, IS_START, HO_END, 0.20, 15.0, 7, cost_bps=10.0)
    s2_full_2x = run_strategy2(data, S2_UNIVERSE, IS_START, HO_END, 0.20, 15.0, 7, cost_bps=20.0)
    b4_full = run_benchmark_sma200_hold(data, S2_UNIVERSE, IS_START, HO_END, cost_bps=10.0)

    m_full = compute_metrics(dates, s2_full["excess_rets"], rf_daily, s2_full["trades"], IS_START, HO_END)
    m_full_2x = compute_metrics(dates, s2_full_2x["excess_rets"], rf_daily, s2_full_2x["trades"], IS_START, HO_END)
    m_b4_full = compute_metrics(dates, b4_full, rf_daily, [], IS_START, HO_END)

    # 3. Regime-Monte-Carlo auf Gesamtzeitraum
    mc_res = run_s2_regime_monte_carlo(
        data,
        actual_sharpe=m_full["excess_sharpe"],
        actual_trades_count=m_full["trades"],
        start_date=IS_START,
        end_date=HO_END,
        n_mc=1000,
        seed=42,
    )

    out = {
        "holdout_2022_2026": {
            "s2_primary": m_ho,
            "s2_cost_2x": m_ho_2x,
            "s2_neg_control_tlt_gld": m_ho_ctrl,
            "bench_sma200_hold": m_b4_ho,
        },
        "full_2008_2026": {
            "s2_primary": m_full,
            "s2_cost_2x": m_full_2x,
            "bench_sma200_hold": m_b4_full,
            "regime_monte_carlo": mc_res,
        },
    }
    (AUDIT_CACHE_DIR / "s2_holdout_report.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("=== STRATEGIE 2: HOLDOUT (2022-01-01 .. 2026-11-20, flach gestartet) ===")
    print("Holdout :", m_ho)
    print("2xCost  :", m_ho_2x)
    print("NegCtrl :", m_ho_ctrl)
    print("SMA200  :", m_b4_ho)
    print("\n=== STRATEGIE 2: GESAMTZEITRAUM (2008-03-01 .. 2026-11-20) ===")
    print("Full    :", m_full)
    print("2xCost  :", m_full_2x)
    print("SMA200  :", m_b4_full)
    print("RegimeMC:", mc_res)


if __name__ == "__main__":
    main()
