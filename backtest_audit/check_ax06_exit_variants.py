#!/usr/bin/env python3
"""
backtest_audit/check_ax06_exit_variants.py
==========================================
Historischer Backcheck (Weg B) fuer AX-06 auf allen aktiven Whitelist-Zellen (12 SHADOW_PAPER + 2 PILOT_LIVE).
Vergleicht auf IDENTISCHEN Einstiegen (strikt SL vor TP1/TP2, Gap-Aware, asset-spezifische Reibung):
  - V1_BE_ATR2        : Nach TP1 (+1.5R) BE + 2.0*ATR14 Trail (Standard v2)
  - V2_BE_FIXED       : Nach TP1 (+1.5R) starrer BE (Inkubator-Standard)
  - V3_AX06_FLOOR_05R : Nach TP1 (+1.5R) Floor bei -0.5R + Trail best_p - 2.5*R (AX-06)
"""

import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from asset_onboarding_evaluator import resolve_asset_target
from backtest_data_loader import get_cached_bars
from backtest_matrix_engine import precompute_indicators
from opus_whitelist_auditor import _fee_slip_for_cat, _mode_from_allowed_dirs, _norm_tf

DYN_WL_FILE = BASE_DIR / "knowledge_base" / "triad_whitelist_dynamic.json"
OUT_FILE = BASE_DIR / "knowledge_base" / "audit_cache" / "ax06_backcheck_report.json"


def simulate_variant(
    bars: List[Dict[str, Any]],
    pre: Dict[str, Any],
    mode: str,
    tf: str,
    fee_pct: float,
    slip_pct: float,
    variant: str,
) -> List[float]:
    n = pre["n"]
    closes, highs, lows, opens, vols = pre["closes"], pre["highs"], pre["lows"], pre["opens"], pre["vols"]
    atr14, rfe_wma, rfe_std, rsi14, vol_sma, wma_len = (
        pre["atr14"], pre["rfe_wma"], pre["rfe_std"], pre["rsi14"], pre["vol_sma"], pre["wma_len"]
    )
    sl_mult = 0.6 if tf in ("15m", "30m") else (1.0 if tf in ("1h", "4h", "8h") else 1.5)
    start_scan = max(wma_len, 25)

    pos_dir = 0
    entry_p = sl = tp1 = tp2 = init_risk = best_p = 0.0
    tp1_done = False
    r_list: List[float] = []

    for i in range(start_scan, n):
        curr_p, curr_h, curr_l, curr_o = closes[i], highs[i], lows[i], opens[i]
        a = atr14[i]
        if a is None or a <= 0:
            continue

        if pos_dir == 1:
            if curr_l <= sl:
                actual_exit = min(sl, curr_o)
                exit_p = actual_exit * (1.0 - slip_pct)
                eff_entry = entry_p * (1.0 + slip_pct)
                raw_gain = ((tp1 - eff_entry) * 0.5 + (exit_p - eff_entry) * 0.5) if tp1_done else (exit_p - eff_entry)
                net = raw_gain - (eff_entry + exit_p) * fee_pct
                r_list.append(round(net / init_risk, 3))
                pos_dir = 0
            elif curr_h >= tp2:
                exit_p = tp2 * (1.0 - slip_pct)
                eff_entry = entry_p * (1.0 + slip_pct)
                raw_gain = ((tp1 - eff_entry) * 0.5 + (exit_p - eff_entry) * 0.5) if tp1_done else (exit_p - eff_entry)
                net = raw_gain - (eff_entry + exit_p) * fee_pct
                r_list.append(round(net / init_risk, 3))
                pos_dir = 0
            else:
                if not tp1_done and curr_h >= tp1:
                    tp1_done = True
                    best_p = max(entry_p, curr_h)
                    if variant == "V1_BE_ATR2":
                        sl = max(sl, entry_p, curr_h - 2.0 * a)
                    elif variant == "V2_BE_FIXED":
                        sl = max(sl, entry_p)
                    elif variant == "V3_AX06_FLOOR_05R":
                        sl = max(sl, entry_p - 0.5 * init_risk, best_p - 2.5 * init_risk)
                elif tp1_done:
                    best_p = max(best_p, curr_h)
                    if variant == "V1_BE_ATR2":
                        sl = max(sl, curr_h - 2.0 * a)
                    elif variant == "V3_AX06_FLOOR_05R":
                        sl = max(sl, entry_p - 0.5 * init_risk, best_p - 2.5 * init_risk)

        elif pos_dir == -1:
            if curr_h >= sl:
                actual_exit = max(sl, curr_o)
                exit_p = actual_exit * (1.0 + slip_pct)
                eff_entry = entry_p * (1.0 - slip_pct)
                raw_gain = ((eff_entry - tp1) * 0.5 + (eff_entry - exit_p) * 0.5) if tp1_done else (eff_entry - exit_p)
                net = raw_gain - (eff_entry + exit_p) * fee_pct
                r_list.append(round(net / init_risk, 3))
                pos_dir = 0
            elif curr_l <= tp2:
                exit_p = tp2 * (1.0 + slip_pct)
                eff_entry = entry_p * (1.0 - slip_pct)
                raw_gain = ((eff_entry - tp1) * 0.5 + (eff_entry - exit_p) * 0.5) if tp1_done else (eff_entry - exit_p)
                net = raw_gain - (eff_entry + exit_p) * fee_pct
                r_list.append(round(net / init_risk, 3))
                pos_dir = 0
            else:
                if not tp1_done and curr_l <= tp1:
                    tp1_done = True
                    best_p = min(entry_p, curr_l)
                    if variant == "V1_BE_ATR2":
                        sl = min(sl, entry_p, curr_l + 2.0 * a)
                    elif variant == "V2_BE_FIXED":
                        sl = min(sl, entry_p)
                    elif variant == "V3_AX06_FLOOR_05R":
                        sl = min(sl, entry_p + 0.5 * init_risk, best_p + 2.5 * init_risk)
                elif tp1_done:
                    best_p = min(best_p, curr_l)
                    if variant == "V1_BE_ATR2":
                        sl = min(sl, curr_l + 2.0 * a)
                    elif variant == "V3_AX06_FLOOR_05R":
                        sl = min(sl, entry_p + 0.5 * init_risk, best_p + 2.5 * init_risk)

        if pos_dir == 0:
            c_high, c_low = max(highs[i - 4 : i + 1]), min(lows[i - 4 : i + 1])
            up_chaos, lo_chaos, mid_chaos = c_high + 1.8 * a, c_low - 1.8 * a, (c_high + c_low) / 2.0
            r_basis, r_std = rfe_wma[i], rfe_std[i]
            if r_basis is None or r_std is None:
                continue
            r_upper, r_lower = r_basis + 1.618 * r_std, r_basis - 1.618 * r_std
            buy_area = (curr_l < r_lower) and (highs[i - 1] > r_lower)
            sell_area = (curr_h > r_upper) and (lows[i - 1] < r_upper)
            ntz = ((curr_l < r_basis) and (highs[i - 1] > r_basis)) or ((curr_h > r_basis) and (lows[i - 1] < r_basis))
            good_buy = (curr_l < lows[i - 1] or curr_l < r_lower) and (curr_p > curr_o) and (curr_p < r_basis) and (curr_l <= lo_chaos or buy_area)
            good_sell = (curr_h > highs[i - 1] or curr_h > r_upper) and (curr_p < curr_o) and (curr_p > r_basis) and (curr_h >= up_chaos or sell_area)
            sweep_bull = curr_l == min(lows[i - 19 : i + 1])
            sweep_bear = curr_h == max(highs[i - 19 : i + 1])
            vsa_spike = vols[i] > 1.3 * (vol_sma[i] or 1.0)
            score_l = 0 if ntz else ((25 if buy_area else 0) + (10 if curr_p < mid_chaos else 0) + (25 if good_buy else 0) + (15 if sweep_bull else 0) + (10 if vsa_spike else 0))
            score_s = 0 if ntz else ((25 if sell_area else 0) + (10 if curr_p > mid_chaos else 0) + (25 if good_sell else 0) + (15 if sweep_bear else 0) + (10 if vsa_spike else 0))

            allow_long = mode in ("Long & Short", "Nur Long")
            allow_short = mode in ("Long & Short", "Nur Short")
            swing_low, swing_high = min(lows[i - 9 : i + 1]), max(highs[i - 9 : i + 1])
            sl_buf = sl_mult * a

            if allow_long and score_l >= 60 and curr_p > (swing_low - sl_buf):
                sl_cand = swing_low - sl_buf
                rd = curr_p - sl_cand
                if rd >= 1.2 * a and (rd / curr_p) <= 0.08:
                    pos_dir, entry_p, sl, init_risk, tp1_done = 1, curr_p, sl_cand, rd, False
                    tp1, tp2 = curr_p + 1.5 * rd, curr_p + 3.0 * rd
            elif allow_short and score_s >= 60 and curr_p < (swing_high + sl_buf):
                sl_cand = swing_high + sl_buf
                rd = sl_cand - curr_p
                if rd >= 1.2 * a and (rd / curr_p) <= 0.08:
                    pos_dir, entry_p, sl, init_risk, tp1_done = -1, curr_p, sl_cand, rd, False
                    tp1, tp2 = curr_p - 1.5 * rd, curr_p - 3.0 * rd
    return r_list


def stats(r_list: List[float]) -> Dict[str, Any]:
    m = len(r_list)
    if m == 0:
        return {"trades": 0, "wr": 0.0, "pf": 0.0, "exp_r": 0.0, "total_r": 0.0}
    wins = [r for r in r_list if r > 0]
    losses = [r for r in r_list if r < 0]
    pf = (sum(wins) / (-sum(losses))) if losses else 99.0
    return {
        "trades": m,
        "wr": round(len(wins) / m * 100.0, 1),
        "pf": round(pf, 3),
        "exp_r": round(sum(r_list) / m, 3),
        "total_r": round(sum(r_list), 2),
    }


def main() -> None:
    dw = json.loads(DYN_WL_FILE.read_text(encoding="utf-8"))
    entries = dw.get("entries", {})
    variants = ["V1_BE_ATR2", "V2_BE_FIXED", "V3_AX06_FLOOR_05R"]
    pooled = {v: [] for v in variants}
    per_cell = []

    for ck, cell in entries.items():
        if not isinstance(cell, dict) or cell.get("tier") not in ("PILOT_LIVE", "SHADOW_PAPER"):
            continue
        tf = _norm_tf(cell.get("timeframe", "1d"))
        mode = _mode_from_allowed_dirs(cell.get("allowed_directions") or ["LONG", "SHORT"])
        best_bars, best_t = [], None
        for s in (cell.get("symbols") or []):
            t = resolve_asset_target(str(s))
            if t.get("untestable") or t.get("source") == "none":
                continue
            b = get_cached_bars(t, interval=tf)
            if b and len(b) > len(best_bars):
                best_bars, best_t = b, t
        if not best_t or len(best_bars) < 250:
            continue
        pre = precompute_indicators(best_bars)
        if pre is None:
            continue
        fee, slip = _fee_slip_for_cat(best_t.get("category", "Aktien"))
        cell_res = {"cell_key": ck, "tf": tf, "mode": mode}
        for v in variants:
            rl = simulate_variant(best_bars, pre, mode, tf, fee, slip, v)
            pooled[v].extend(rl)
            cell_res[v] = stats(rl)
        per_cell.append(cell_res)

    summary = {v: stats(pooled[v]) for v in variants}
    OUT_FILE.write_text(json.dumps({"pooled": summary, "per_cell": per_cell}, indent=2), encoding="utf-8")

    print("=== AX-06 BACKCHECK UEBER ALLE AKTIVEN WHITELIST-ZELLEN (SL vor TP) ===")
    for v, st in summary.items():
        print(f"  {v:20s}: {st}")
    print("\n=== PRO ZELLE (Total R Vergleich) ===")
    for c in per_cell:
        print(f"  {c['cell_key']:28s} ({c['tf']:3s}) | V1_BE_ATR2={c['V1_BE_ATR2']['total_r']:+6.2f}R | V2_BE_FIXED={c['V2_BE_FIXED']['total_r']:+6.2f}R | V3_AX06_05R={c['V3_AX06_FLOOR_05R']['total_r']:+6.2f}R")


if __name__ == "__main__":
    main()
