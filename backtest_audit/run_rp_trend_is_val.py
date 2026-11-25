#!/usr/bin/env python3
"""
backtest_audit/run_rp_trend_is_val.py
=====================================
Fuehrt ausschliesslich IS+Val (2008-03-01 .. 2021-12-31) fuer Pre-Registration v2.1 (RP-Trend)
aus. Holdout (> 2021-12-31) bleibt gesperrt. Prueft alle 5 strengen Gate-Kriterien.
"""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from monthly_engine import (
    AUDIT_CACHE_DIR,
    S1_UNIVERSE,
    compute_curve_metrics,
    deflated_sharpe_ratio,
    load_verified_data,
    make_60_40_fn,
    make_rp_trend_fn,
    ols_newey_west_alpha,
    run_monthly_allocation,
    stationary_bootstrap_sharpe_p,
)

IS_START, IS_END = "2008-03-01", "2016-12-31"
VAL_START, VAL_END = "2017-01-01", "2021-12-31"


def main() -> None:
    data = load_verified_data(S1_UNIVERSE, max_date=VAL_END, allow_holdout=False)

    # 1. Primaere Spezifikation: RP-Trend (L=252, S=21, V=60)
    rp_trend = run_monthly_allocation(
        data, S1_UNIVERSE, make_rp_trend_fn(data, S1_UNIVERSE, 252, 21, 60, True),
        IS_START, VAL_END, cost_bps=10.0,
    )
    rp_trend_2x = run_monthly_allocation(
        data, S1_UNIVERSE, make_rp_trend_fn(data, S1_UNIVERSE, 252, 21, 60, True),
        IS_START, VAL_END, cost_bps=20.0,
    )
    # 2. Benchmarks mit derselben Engine
    rp_lo = run_monthly_allocation(
        data, S1_UNIVERSE, make_rp_trend_fn(data, S1_UNIVERSE, 252, 21, 60, False),
        IS_START, VAL_END, cost_bps=10.0,
    )
    b60_40 = run_monthly_allocation(
        data, S1_UNIVERSE, make_60_40_fn(),
        IS_START, VAL_END, cost_bps=10.0,
    )

    dates, rf = rp_trend["dates"], rp_trend["rf_daily"]
    ex_t, ex_rp, ex_6040 = rp_trend["excess_rets"], rp_lo["excess_rets"], b60_40["excess_rets"]

    m_is = compute_curve_metrics(dates, rf, ex_t, IS_START, IS_END)
    m_val = compute_curve_metrics(dates, rf, ex_t, VAL_START, VAL_END)
    m_all = compute_curve_metrics(dates, rf, ex_t)
    m_2x = compute_curve_metrics(dates, rf, rp_trend_2x["excess_rets"])
    m_rp = compute_curve_metrics(dates, rf, ex_rp)
    m_6040 = compute_curve_metrics(dates, rf, ex_6040)

    # Vol-Skalierungsfaktor k auf IS+Val einfrieren
    k_scale = m_rp["ann_vol_pct"] / m_all["ann_vol_pct"]
    m_all_scaled = compute_curve_metrics(dates, rf, ex_t, vol_scale_k=k_scale)

    # Statistische Tests: 10.000 Stationary Bootstraps & Newey-West HAC (Lag=21)
    boot_p = stationary_bootstrap_sharpe_p(ex_t, mean_block=20.0, n_boot=10_000, seed=42)
    alpha_nw = ols_newey_west_alpha(ex_t, ex_rp, lag=21)

    # Deflated Sharpe (N=12)
    n_obs = len(ex_t)
    mu = sum(ex_t) / n_obs
    sd = math.sqrt(sum((x - mu) ** 2 for x in ex_t) / (n_obs - 1))
    skew = sum(((x - mu) / sd) ** 3 for x in ex_t) / n_obs
    kurt = sum(((x - mu) / sd) ** 4 for x in ex_t) / n_obs
    dsr = deflated_sharpe_ratio(m_all["excess_sharpe"], n_obs, skew, kurt, n_trials=12)

    # Plateau (9 Zellen: {(189,0), (252,0), (252,21)} x {40, 60, 90})
    rp_by_v = {}
    for v in (40, 60, 90):
        res_rp_v = run_monthly_allocation(
            data, S1_UNIVERSE, make_rp_trend_fn(data, S1_UNIVERSE, 252, 21, v, False),
            IS_START, VAL_END, cost_bps=10.0,
        )
        rp_by_v[v] = compute_curve_metrics(res_rp_v["dates"], res_rp_v["rf_daily"], res_rp_v["excess_rets"])

    plateau = []
    plateau_pass = True
    for l_p, s_p in [(189, 0), (252, 0), (252, 21)]:
        for v in (40, 60, 90):
            res = run_monthly_allocation(
                data, S1_UNIVERSE, make_rp_trend_fn(data, S1_UNIVERSE, l_p, s_p, v, True),
                IS_START, VAL_END, cost_bps=10.0,
            )
            mc = compute_curve_metrics(res["dates"], res["rf_daily"], res["excess_rets"])
            kv = rp_by_v[v]["ann_vol_pct"] / mc["ann_vol_pct"]
            mc_sc = compute_curve_metrics(res["dates"], res["rf_daily"], res["excess_rets"], vol_scale_k=kv)
            ok = (mc["excess_sharpe"] >= 0.50) and (mc_sc["max_dd_pct"] < rp_by_v[v]["max_dd_pct"])
            if not ok:
                plateau_pass = False
            plateau.append({
                "L": l_p, "S": s_p, "V": v,
                "sharpe": mc["excess_sharpe"], "scaled_dd": mc_sc["max_dd_pct"],
                "rp_dd": rp_by_v[v]["max_dd_pct"], "ok": ok,
            })

    # Strenge Gate-Pruefung (§4.3)
    g1 = (m_all["excess_sharpe"] >= 0.60) and (m_all["excess_sharpe"] > m_rp["excess_sharpe"])
    g2 = (alpha_nw["alpha_ann_pct"] > 0.0) and (alpha_nw["p_value_nw"] < 0.05)
    g3 = m_all_scaled["max_dd_pct"] <= 0.75 * m_rp["max_dd_pct"]
    g4 = m_2x["excess_sharpe"] > 0.45
    g5 = plateau_pass
    gate_open = g1 and g2 and g3 and g4 and g5

    report = {
        "preregistration_version": "v2.1",
        "ffill_counts": data["ffill_counts"],
        "rp_trend": {
            "is": m_is, "val": m_val, "is_val": m_all,
            "is_val_scaled_to_rp_vol": m_all_scaled, "k_scale_frozen": round(k_scale, 4),
            "cost_2x": m_2x,
            "ann_turnover_pct": rp_trend["ann_turnover_pct"],
            "ann_cost_drag_bp": rp_trend["ann_cost_drag_bp"],
            "cash_months": rp_trend["cash_months"],
        },
        "bench_rp_lo": m_rp,
        "bench_60_40": m_6040,
        "bootstrap_p_10k": boot_p,
        "ols_nw21_alpha_vs_rp": alpha_nw,
        "deflated_sharpe_n12": dsr,
        "plateau_pass": plateau_pass,
        "plateau": plateau,
        "gate_checks": {"g1_sr": g1, "g2_alpha": g2, "g3_dd": g3, "g4_2x": g4, "g5_plateau": g5},
        "holdout_gate_open": gate_open,
    }
    (AUDIT_CACHE_DIR / "rp_trend_is_val_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== RP-TREND (IS+Val 2008-03-01 .. 2021-12-31, Holdout gesperrt) ===")
    print("IS       :", m_is)
    print("Val      :", m_val)
    print("IS+Val   :", m_all)
    print("ScaledDD :", m_all_scaled, f"(k={round(k_scale, 4)})")
    print("2xCost   :", m_2x)
    print("RP LO    :", m_rp)
    print("60/40    :", m_6040)
    print(f"Boot_p(10k)={boot_p} | NW-Alpha={alpha_nw} | DSR(N=12)={dsr}")
    print(f"Turnover={rp_trend['ann_turnover_pct']}% p.a., CostDrag={rp_trend['ann_cost_drag_bp']} bp p.a.")
    print(f"Gate Checks: {report['gate_checks']} => HOLDOUT_GATE={gate_open}")


if __name__ == "__main__":
    main()
