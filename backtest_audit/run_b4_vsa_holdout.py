#!/usr/bin/env python3
"""
backtest_audit/run_b4_vsa_holdout.py
====================================
Einmalige Oeffnung des versiegelten Holdouts (2023-01-01 .. 2026-11-20)
ausschliesslich fuer den einzigen FDR-Gewinner B4_VSA auf Krypto 1D.
"""

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from degencoder_ablation import BT_CACHE_DIR, CRYPTO_UNIVERSE, compute_causal_block_signals
from indicators import atr_wilder

AUDIT_CACHE_DIR = BASE_DIR / "knowledge_base" / "audit_cache"


def simulate_b4_detailed(
    bars_by_sym: Dict[str, List[Dict[str, Any]]],
    sigs_by_sym: Dict[str, Dict[str, List[int]]],
    start_ts: int,
    end_ts: int,
    cost_rt_frac: float,
) -> List[Dict[str, Any]]:
    trades: List[Dict[str, Any]] = []
    for sym, bars in bars_by_sym.items():
        n = len(bars)
        if n < 260:
            continue
        atr14 = atr_wilder([float(b["h"]) for b in bars], [float(b["l"]) for b in bars], [float(b["c"]) for b in bars], 14)
        s_i = sigs_by_sym[sym]["B4_VSA"]

        pos_dir = 0
        entry_p = sl = tp1 = tp2 = init_risk = 0.0
        entry_ts = 0
        tp1_done = False

        for t in range(250, n):
            bt = int(bars[t]["t"])
            if bt < start_ts or bt > end_ts:
                continue
            o_p = float(bars[t]["o"])
            h_p = float(bars[t]["h"])
            l_p = float(bars[t]["l"])
            a = atr14[t]
            if a is None or a <= 0:
                continue

            if pos_dir != 0:
                if pos_dir == 1:
                    if l_p <= sl:
                        fill = min(o_p, sl)
                        gross_r = (0.5 * 1.5 + 0.5 * ((fill - entry_p) / init_risk)) if tp1_done else ((fill - entry_p) / init_risk)
                        r_net = gross_r - (entry_p * cost_rt_frac) / init_risk
                        trades.append({"sym": sym, "dir": "LONG", "entry_ts": entry_ts, "exit_ts": bt, "r": round(r_net, 4)})
                        pos_dir = 0
                        continue
                    if h_p >= tp2:
                        r_net = (2.25 if tp1_done else 3.0) - (entry_p * cost_rt_frac) / init_risk
                        trades.append({"sym": sym, "dir": "LONG", "entry_ts": entry_ts, "exit_ts": bt, "r": round(r_net, 4)})
                        pos_dir = 0
                        continue
                    if not tp1_done and h_p >= tp1:
                        tp1_done = True
                        sl = max(sl, entry_p)
                    if tp1_done:
                        sl = max(sl, h_p - 2.0 * a)
                else:
                    if h_p >= sl:
                        fill = max(o_p, sl)
                        gross_r = (0.5 * 1.5 + 0.5 * ((entry_p - fill) / init_risk)) if tp1_done else ((entry_p - fill) / init_risk)
                        r_net = gross_r - (entry_p * cost_rt_frac) / init_risk
                        trades.append({"sym": sym, "dir": "SHORT", "entry_ts": entry_ts, "exit_ts": bt, "r": round(r_net, 4)})
                        pos_dir = 0
                        continue
                    if l_p <= tp2:
                        r_net = (2.25 if tp1_done else 3.0) - (entry_p * cost_rt_frac) / init_risk
                        trades.append({"sym": sym, "dir": "SHORT", "entry_ts": entry_ts, "exit_ts": bt, "r": round(r_net, 4)})
                        pos_dir = 0
                        continue
                    if not tp1_done and l_p <= tp1:
                        tp1_done = True
                        sl = min(sl, entry_p)
                    if tp1_done:
                        sl = min(sl, l_p + 2.0 * a)

            if pos_dir == 0 and t > 250 and int(bars[t - 1]["t"]) >= start_ts:
                sig_t = t - 1
                dir_sig = s_i[sig_t]
                a_sig = atr14[sig_t]
                if dir_sig != 0 and a_sig is not None and a_sig > 0 and o_p > 0:
                    pos_dir = dir_sig
                    entry_p = o_p
                    entry_ts = bt
                    init_risk = 2.0 * a_sig
                    tp1_done = False
                    if pos_dir == 1:
                        sl, tp1, tp2 = entry_p - init_risk, entry_p + 1.5 * init_risk, entry_p + 3.0 * init_risk
                    else:
                        sl, tp1, tp2 = entry_p + init_risk, entry_p - 1.5 * init_risk, entry_p - 3.0 * init_risk
    return trades


def summarize(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    m = len(trades)
    if m == 0:
        return {"trades": 0, "wr": 0.0, "pf": 0.0, "exp_r": 0.0, "total_r": 0.0, "t_stat": 0.0}
    r_list = [t["r"] for t in trades]
    wins = [r for r in r_list if r > 0]
    losses = [r for r in r_list if r < 0]
    gw, gl = sum(wins), -sum(losses)
    pf = (gw / gl) if gl > 1e-12 else 99.0
    mean_r = sum(r_list) / m
    sd_r = math.sqrt(sum((r - mean_r) ** 2 for r in r_list) / (m - 1)) if m > 1 else 0.0
    t_stat = (mean_r / (sd_r / math.sqrt(m))) if sd_r > 1e-12 else 0.0
    return {
        "trades": m,
        "wr": round(len(wins) / m * 100.0, 1),
        "pf": round(pf, 3),
        "exp_r": round(mean_r, 3),
        "total_r": round(sum(r_list), 2),
        "t_stat": round(t_stat, 2),
    }


def main() -> None:
    cry_1d = {s: json.loads((BT_CACHE_DIR / f"binance_{s}_1d.json").read_text(encoding="utf-8")) for s in CRYPTO_UNIVERSE}
    sigs_1d = {s: compute_causal_block_signals(bars) for s, bars in cry_1d.items()}

    t_is_start = int(datetime(2018, 1, 1, tzinfo=timezone.utc).timestamp())
    t_is_end = int(datetime(2022, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())
    t_ho_start = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp())
    t_ho_end = int(datetime(2026, 11, 20, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    tr_is = simulate_b4_detailed(cry_1d, sigs_1d, t_is_start, t_is_end, 0.0020)
    tr_ho = simulate_b4_detailed(cry_1d, sigs_1d, t_ho_start, t_ho_end, 0.0020)
    tr_ho_2x = simulate_b4_detailed(cry_1d, sigs_1d, t_ho_start, t_ho_end, 0.0040)

    out = {
        "is_val_2018_2022": {
            "all": summarize(tr_is),
            "long": summarize([t for t in tr_is if t["dir"] == "LONG"]),
            "short": summarize([t for t in tr_is if t["dir"] == "SHORT"]),
        },
        "holdout_2023_2026": {
            "all": summarize(tr_ho),
            "all_2x_cost": summarize(tr_ho_2x),
            "long": summarize([t for t in tr_ho if t["dir"] == "LONG"]),
            "short": summarize([t for t in tr_ho if t["dir"] == "SHORT"]),
            "by_symbol": {s: summarize([t for t in tr_ho if t["sym"] == s]) for s in CRYPTO_UNIVERSE},
        },
    }
    (AUDIT_CACHE_DIR / "b4_vsa_holdout_report.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("=== B4_VSA KRYPTO 1D: IS+Val (2018-2022) ===")
    print("All  :", out["is_val_2018_2022"]["all"])
    print("Long :", out["is_val_2018_2022"]["long"])
    print("Short:", out["is_val_2018_2022"]["short"])

    print("\n=== B4_VSA KRYPTO 1D: VERSIEGELTER HOLDOUT (2023-2026, flach gestartet) ===")
    print("All    :", out["holdout_2023_2026"]["all"])
    print("2xCost :", out["holdout_2023_2026"]["all_2x_cost"])
    print("Long   :", out["holdout_2023_2026"]["long"])
    print("Short  :", out["holdout_2023_2026"]["short"])
    print("BySym  :")
    for s, m in out["holdout_2023_2026"]["by_symbol"].items():
        print(f"  {s:10s}: {m}")


if __name__ == "__main__":
    main()
