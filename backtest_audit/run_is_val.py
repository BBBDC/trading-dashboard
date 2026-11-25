#!/usr/bin/env python3
"""
backtest_audit/run_is_val.py
============================
Fuehrt ausschliesslich In-Sample (2008-03-01..2016-12-31) und Validation (2017-01-01..2021-12-31)
aus. Holdout (> 2021-12-31) bleibt technisch gesperrt. Prueft das Holdout-Oeffnungs-Gate.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import (
    AUDIT_CACHE_DIR,
    S1_UNIVERSE,
    S2_CONTROLS,
    S2_UNIVERSE,
    compute_metrics,
    load_audit_data,
    ols_alpha_vs_benchmark,
    run_benchmark_risk_parity_lo,
    run_benchmark_sma200_hold,
    run_strategy1,
    run_strategy2,
    stationary_bootstrap_sharpe_p,
)

IS_START, IS_END = "2008-03-01", "2016-12-31"
VAL_START, VAL_END = "2017-01-01", "2021-12-31"


def main() -> None:
    all_syms = sorted(set(S1_UNIVERSE + S2_UNIVERSE + S2_CONTROLS))
    data = load_audit_data(all_syms, max_date=VAL_END, allow_holdout=False)
    dates = data["dates"]
    rf_daily = data["rf_daily"]
    is_val_idxs = [i for i, d in enumerate(dates) if IS_START <= d <= VAL_END]

    # --- STRATEGIE 1: TSMOM ---
    s1 = run_strategy1(data, IS_START, VAL_END, 50, 25, 3.0, cost_bps=10.0)
    s1_2x = run_strategy1(data, IS_START, VAL_END, 50, 25, 3.0, cost_bps=20.0)
    s1_1b = run_strategy1(data, IS_START, VAL_END, 50, 25, 3.0, cost_bps=10.0, long_only_equities=True)
    b1_rp = run_benchmark_risk_parity_lo(data, S1_UNIVERSE, IS_START, VAL_END, cost_bps=10.0)

    s1_is = compute_metrics(dates, s1["excess_rets"], rf_daily, s1["trades"], IS_START, IS_END)
    s1_val = compute_metrics(dates, s1["excess_rets"], rf_daily, s1["trades"], VAL_START, VAL_END)
    s1_all = compute_metrics(dates, s1["excess_rets"], rf_daily, s1["trades"], IS_START, VAL_END)
    s1_2x_m = compute_metrics(dates, s1_2x["excess_rets"], rf_daily, s1_2x["trades"], IS_START, VAL_END)
    s1_1b_m = compute_metrics(dates, s1_1b["excess_rets"], rf_daily, s1_1b["trades"], IS_START, VAL_END)
    b1_m = compute_metrics(dates, b1_rp, rf_daily, [], IS_START, VAL_END)

    s1_ex_win = [s1["excess_rets"][i] for i in is_val_idxs]
    b1_ex_win = [b1_rp[i] for i in is_val_idxs]
    s1_boot_p = stationary_bootstrap_sharpe_p(s1_ex_win, mean_block=20.0, n_boot=2000, seed=42)
    s1_alpha = ols_alpha_vs_benchmark(s1_ex_win, b1_ex_win)

    # S1 Plateau auf IS+Val
    s1_plateau = []
    prim_sr1 = s1_all["excess_sharpe"]
    s1_plateau_pass = True
    for ne, nx in [(40, 20), (50, 25), (60, 30)]:
        for am in [2.5, 3.0, 3.5]:
            res = run_strategy1(data, IS_START, VAL_END, ne, nx, am, cost_bps=10.0)
            m = compute_metrics(dates, res["excess_rets"], rf_daily, res["trades"], IS_START, VAL_END)
            ok = (m["excess_sharpe"] >= 0.5 * prim_sr1) and (m["excess_sharpe"] > 0.0) and (m["profit_factor"] > 1.10)
            if not ok:
                s1_plateau_pass = False
            s1_plateau.append({"n_entry": ne, "n_exit": nx, "atr_mult": am, "ok": ok, **m})

    s1_gate_open = (s1_all["excess_sharpe"] > 0.30) and (s1_all["profit_factor"] > 1.15) and s1_plateau_pass

    # --- STRATEGIE 2: IBS + RSI(2) ---
    s2 = run_strategy2(data, S2_UNIVERSE, IS_START, VAL_END, 0.20, 15.0, 7, cost_bps=10.0)
    s2_2x = run_strategy2(data, S2_UNIVERSE, IS_START, VAL_END, 0.20, 15.0, 7, cost_bps=20.0)
    s2_ctrl = run_strategy2(data, S2_CONTROLS, IS_START, VAL_END, 0.20, 15.0, 7, cost_bps=10.0)
    b4_sma = run_benchmark_sma200_hold(data, S2_UNIVERSE, IS_START, VAL_END, cost_bps=10.0)

    s2_is = compute_metrics(dates, s2["excess_rets"], rf_daily, s2["trades"], IS_START, IS_END)
    s2_val = compute_metrics(dates, s2["excess_rets"], rf_daily, s2["trades"], VAL_START, VAL_END)
    s2_all = compute_metrics(dates, s2["excess_rets"], rf_daily, s2["trades"], IS_START, VAL_END)
    s2_2x_m = compute_metrics(dates, s2_2x["excess_rets"], rf_daily, s2_2x["trades"], IS_START, VAL_END)
    s2_ctrl_m = compute_metrics(dates, s2_ctrl["excess_rets"], rf_daily, s2_ctrl["trades"], IS_START, VAL_END)
    b4_m = compute_metrics(dates, b4_sma, rf_daily, [], IS_START, VAL_END)

    # S2 Plateau auf IS+Val
    s2_plateau = []
    prim_sr2 = s2_all["excess_sharpe"]
    s2_plateau_pass = True
    for ib_v, rs_v, ts_v in [
        (0.15, 15.0, 7), (0.25, 15.0, 7),
        (0.20, 10.0, 7), (0.20, 20.0, 7),
        (0.20, 15.0, 5), (0.20, 15.0, 10),
        (0.20, 15.0, 7),
    ]:
        res = run_strategy2(data, S2_UNIVERSE, IS_START, VAL_END, ib_v, rs_v, ts_v, cost_bps=10.0)
        m = compute_metrics(dates, res["excess_rets"], rf_daily, res["trades"], IS_START, VAL_END)
        ok = (m["excess_sharpe"] >= 0.5 * prim_sr2) and (m["excess_sharpe"] > 0.0) and (m["profit_factor"] > 1.10)
        if not ok:
            s2_plateau_pass = False
        s2_plateau.append({"ibs": ib_v, "rsi": rs_v, "time_stop": ts_v, "ok": ok, **m})

    s2_gate_open = (s2_all["excess_sharpe"] > 0.30) and (s2_all["profit_factor"] > 1.15) and s2_plateau_pass

    report = {
        "strategy_1": {
            "is": s1_is, "val": s1_val, "is_val": s1_all,
            "cost_2x": s1_2x_m, "ablation_1b_lo_eq": s1_1b_m,
            "bench_risk_parity_lo": b1_m,
            "bootstrap_p": s1_boot_p, "ols_alpha_vs_rp": s1_alpha,
            "plateau_passed": s1_plateau_pass, "plateau": s1_plateau,
            "holdout_gate_open": s1_gate_open,
        },
        "strategy_2": {
            "is": s2_is, "val": s2_val, "is_val": s2_all,
            "cost_2x": s2_2x_m, "neg_control_tlt_gld": s2_ctrl_m,
            "bench_sma200_hold": b4_m,
            "plateau_passed": s2_plateau_pass, "plateau": s2_plateau,
            "holdout_gate_open": s2_gate_open,
        },
    }
    out_p = AUDIT_CACHE_DIR / "is_val_report.json"
    out_p.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== STRATEGIE 1 (TSMOM, IS+Val 2008-03..2021-12) ===")
    print("IS     :", s1_is)
    print("Val    :", s1_val)
    print("IS+Val :", s1_all)
    print("2xCost :", s1_2x_m)
    print("Abl 1B :", s1_1b_m)
    print("BenchRP:", b1_m)
    print(f"Boot p={s1_boot_p}, OLS Alpha={s1_alpha}, Plateau={s1_plateau_pass}, HOLDOUT_GATE={s1_gate_open}")

    print("\n=== STRATEGIE 2 (IBS+RSI2, IS+Val 2008-03..2021-12) ===")
    print("IS     :", s2_is)
    print("Val    :", s2_val)
    print("IS+Val :", s2_all)
    print("2xCost :", s2_2x_m)
    print("NegCtrl:", s2_ctrl_m)
    print("SMA200 :", b4_m)
    print(f"Plateau={s2_plateau_pass}, HOLDOUT_GATE={s2_gate_open}")


if __name__ == "__main__":
    main()
