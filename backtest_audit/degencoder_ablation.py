#!/usr/bin/env python3
"""
backtest_audit/degencoder_ablation.py
=====================================
Kausale Einzel- & Paar-Ablation der 6 orthogonalen degencoder-Bausteine (21 Kombinationen)
gemaess knowledge_base/DEGENCODER_ABLATION_PREREGISTRATION.md.
- Strikt Bar-by-Bar kausal (Anti-Lookahead Unit-Test inklusive).
- Testet ausschliesslich IS+Val; Holdouts (2022-2026 ETF / 2023-2026 Krypto) bleiben gesperrt.
- Bewertet gepoolt ueber Korb A (1D ETFs) und Korb B (4h & 1D Krypto) mit Benjamini-Hochberg FDR.
"""

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from degencoder_engine import calculate_degencoder_bands
from indicators import atr_wilder, rsi_wilder, sma

AUDIT_CACHE_DIR = BASE_DIR / "knowledge_base" / "audit_cache"
BT_CACHE_DIR = BASE_DIR / "knowledge_base" / "backtest_cache"

ETF_UNIVERSE = ["SPY", "QQQ", "DIA", "EWG", "EWU", "EWJ", "TLT", "IEF", "GLD", "DBC"]
CRYPTO_UNIVERSE = ["BTCUSDT", "ETHUSDT", "LTCUSDT", "XRPUSDT", "SOLUSDT", "LINKUSDT"]

BLOCKS = ["B1_BandSig", "B2_FVG", "B3_OB", "B4_VSA", "B5_RSIDiv", "B6_GoldPkt"]


def compute_causal_block_signals(bars: List[Dict[str, Any]]) -> Dict[str, List[int]]:
    """
    Berechnet fuer jeden Bar t in O(N) strikt kausale Signale (+1 LONG, -1 SHORT, 0 NEUTRAL)
    fuer alle 6 Bausteine B1..B6, ohne jemals Kerzen > t zu verwenden.
    """
    n = len(bars)
    out = {b: [0] * n for b in BLOCKS}
    if n < 250:
        return out

    o = [float(b["o"]) for b in bars]
    h = [float(b["h"]) for b in bars]
    l = [float(b["l"]) for b in bars]
    c = [float(b["c"]) for b in bars]
    v = [float(b.get("v") or 0.0) for b in bars]

    bands = calculate_degencoder_bands(bars)
    series = bands.get("series", {})
    rfe_basis = series.get("rfe_basis", [None] * n)
    rfe_lower = series.get("rfe_lower", [None] * n)
    rfe_upper = series.get("rfe_upper", [None] * n)

    rsi14 = rsi_wilder(c, 14)
    vol_sma20 = sma(v, 20)

    # Kausale Zonen-Zustaende fuer B2 (FVG) & B3 (OB)
    active_bull_fvgs: List[Tuple[float, float]] = []  # (bottom, top)
    active_bear_fvgs: List[Tuple[float, float]] = []
    active_bull_obs: List[Tuple[float, float, int]] = []  # (bottom, top, retests)
    active_bear_obs: List[Tuple[float, float, int]] = []

    # Kausale Swings (2-Bar-Bestaetigung: t-2 ist Extremum von [t-4..t]) fuer B5 & B6
    last_swing_low: Optional[Tuple[int, float, float]] = None   # (idx, price, rsi)
    prev_swing_low: Optional[Tuple[int, float, float]] = None
    last_swing_high: Optional[Tuple[int, float, float]] = None
    prev_swing_high: Optional[Tuple[int, float, float]] = None
    last_swing_dir = 0  # +1 Low->High, -1 High->Low

    for t in range(2, n):
        rf_b = rfe_basis[t]
        rf_l = rfe_lower[t]
        rf_u = rfe_upper[t]

        # --- B1: Degencoder Signal / Chaos-Band ---
        if rf_b is not None and rf_l is not None and rf_u is not None:
            in_ntz = (l[t] < rf_b and h[t - 1] > rf_b) or (h[t] > rf_b and l[t - 1] < rf_b)
            if not in_ntz:
                buy_area = l[t] < rf_l and h[t - 1] > rf_l
                sell_area = h[t] > rf_u and l[t - 1] < rf_u
                good_buy = (l[t] < l[t - 1] or l[t] < rf_l) and (c[t] > o[t]) and (c[t] > c[t - 1]) and (c[t] < rf_b)
                good_sell = (h[t] > h[t - 1] or h[t] > rf_u) and (c[t] < o[t]) and (c[t] < c[t - 1]) and (c[t] > rf_b)
                if good_buy or (buy_area and c[t] > o[t]):
                    out["B1_BandSig"][t] = 1
                elif good_sell or (sell_area and c[t] < o[t]):
                    out["B1_BandSig"][t] = -1

        # --- B2: Fair Value Gap (kausal bei Close(t) bestaetigt) ---
        # Pruefe zuerst Retest/Invalidierung bestehender FVGs an Bar t
        new_bull_fvgs = []
        for bot, top in active_bull_fvgs:
            if l[t] <= bot:
                continue  # komplett gefuellt/invalidiert
            if l[t] <= top and c[t] >= bot and c[t] > o[t]:
                out["B2_FVG"][t] = 1
            new_bull_fvgs.append((bot, top))
        active_bull_fvgs = new_bull_fvgs[-5:]

        new_bear_fvgs = []
        for bot, top in active_bear_fvgs:
            if h[t] >= top:
                continue
            if h[t] >= bot and c[t] <= top and c[t] < o[t]:
                out["B2_FVG"][t] = -1
            new_bear_fvgs.append((bot, top))
        active_bear_fvgs = new_bear_fvgs[-5:]

        if h[t - 2] < l[t]:
            active_bull_fvgs.append((h[t - 2], l[t]))
        if l[t - 2] > h[t]:
            active_bear_fvgs.append((h[t], l[t - 2]))

        # --- B3: Order Block (kausal nach 5 Folgekerzen bei Close(t) bestaetigt) ---
        new_bull_obs = []
        for bot, top, ret in active_bull_obs:
            if c[t] < bot:
                continue
            if l[t] <= top and c[t] >= bot and ret < 2:
                if c[t] > o[t]:
                    out["B3_OB"][t] = 1
                ret += 1
            new_bull_obs.append((bot, top, ret))
        active_bull_obs = new_bull_obs[-10:]

        new_bear_obs = []
        for bot, top, ret in active_bear_obs:
            if c[t] > top:
                continue
            if h[t] >= bot and c[t] <= top and ret < 2:
                if c[t] < o[t]:
                    out["B3_OB"][t] = -1
                ret += 1
            new_bear_obs.append((bot, top, ret))
        active_bear_obs = new_bear_obs[-10:]

        if t >= 5:
            ob_i = t - 5
            if c[ob_i] < o[ob_i] and all(c[k] > o[k] for k in range(ob_i + 1, t + 1)):
                active_bull_obs.append((l[ob_i], max(o[ob_i], c[ob_i]), 0))
            elif c[ob_i] > o[ob_i] and all(c[k] < o[k] for k in range(ob_i + 1, t + 1)):
                active_bear_obs.append((min(o[ob_i], c[ob_i]), h[ob_i], 0))

        # --- B4: VSA Wyckoff Volume ---
        vs = vol_sma20[t]
        if vs is not None and vs > 0:
            ratio = v[t] / vs
            rng = max(h[t] - l[t], 1e-12)
            low_wick = (min(o[t], c[t]) - l[t]) / rng
            up_wick = (h[t] - max(o[t], c[t])) / rng
            if ratio >= 1.5:
                if c[t] > o[t] or low_wick > 0.5:
                    out["B4_VSA"][t] = 1
                elif c[t] < o[t] or up_wick > 0.5:
                    out["B4_VSA"][t] = -1
            elif ratio <= 0.8 and rf_b is not None:
                if c[t] > rf_b and c[t] < c[t - 1]:
                    out["B4_VSA"][t] = 1
                elif c[t] < rf_b and c[t] > c[t - 1]:
                    out["B4_VSA"][t] = -1

        # --- Kausale 5-Bar-Fraktale fuer B5 (Divergenz) & B6 (Golden Pocket) ---
        if t >= 4 and rsi14[t - 2] is not None:
            piv = t - 2
            if l[piv] <= min(l[t - 4 : t + 1]):
                prev_swing_low = last_swing_low
                last_swing_low = (piv, l[piv], float(rsi14[piv]))
                last_swing_dir = 1
            if h[piv] >= max(h[t - 4 : t + 1]):
                prev_swing_high = last_swing_high
                last_swing_high = (piv, h[piv], float(rsi14[piv]))
                last_swing_dir = -1

        # --- B5: RSI(14) / Kausale Divergenz ---
        if rsi14[t] is not None and rsi14[t - 1] is not None:
            bull_div = (
                prev_swing_low is not None and last_swing_low is not None
                and last_swing_low[0] == t - 2
                and last_swing_low[1] < prev_swing_low[1]
                and last_swing_low[2] > prev_swing_low[2]
            )
            bear_div = (
                prev_swing_high is not None and last_swing_high is not None
                and last_swing_high[0] == t - 2
                and last_swing_high[1] > prev_swing_high[1]
                and last_swing_high[2] < prev_swing_high[2]
            )
            if (rsi14[t] < 35.0 and rsi14[t] > rsi14[t - 1]) or bull_div:
                out["B5_RSIDiv"][t] = 1
            elif (rsi14[t] > 65.0 and rsi14[t] < rsi14[t - 1]) or bear_div:
                out["B5_RSIDiv"][t] = -1

        # --- B6: Golden Pocket (0.618 - 0.65) ---
        if last_swing_low is not None and last_swing_high is not None:
            if last_swing_high[0] > last_swing_low[0]:
                # Aufwaertsschwung Low -> High, Pullback ins bullische Golden Pocket
                hi_p, lo_p = last_swing_high[1], last_swing_low[1]
                if hi_p > lo_p:
                    gp_top = hi_p - 0.618 * (hi_p - lo_p)
                    gp_bot = hi_p - 0.650 * (hi_p - lo_p)
                    if gp_bot * 0.995 <= c[t] <= gp_top * 1.005:
                        out["B6_GoldPkt"][t] = 1
            else:
                # Abwaertsschwung High -> Low, Bounce ins baerische Golden Pocket
                hi_p, lo_p = last_swing_high[1], last_swing_low[1]
                if hi_p > lo_p:
                    gp_bot = lo_p + 0.618 * (hi_p - lo_p)
                    gp_top = lo_p + 0.650 * (hi_p - lo_p)
                    if gp_bot * 0.995 <= c[t] <= gp_top * 1.005:
                        out["B6_GoldPkt"][t] = -1

    return out


def simulate_combo(
    bars_by_sym: Dict[str, List[Dict[str, Any]]],
    sigs_by_sym: Dict[str, Dict[str, List[int]]],
    b_i: str,
    b_j: Optional[str],
    start_ts: int,
    end_ts: int,
    cost_rt_frac: float,
) -> Dict[str, Any]:
    """Simuliert Einzel-Baustein oder Paar (Konfluenz <= 3 Bars) mit einheitlichem Exit & SL-vor-TP."""
    r_list: List[float] = []

    for sym, bars in bars_by_sym.items():
        n = len(bars)
        if n < 260:
            continue
        atr14 = atr_wilder([float(b["h"]) for b in bars], [float(b["l"]) for b in bars], [float(b["c"]) for b in bars], 14)
        s_i = sigs_by_sym[sym][b_i]
        s_j = sigs_by_sym[sym][b_j] if b_j else None

        pos_dir = 0
        entry_p = sl = tp1 = tp2 = init_risk = 0.0
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
                    # Konservativ SL vor TP1/TP2!
                    if l_p <= sl:
                        fill = min(o_p, sl)
                        gross_r = (0.5 * 1.5 + 0.5 * ((fill - entry_p) / init_risk)) if tp1_done else ((fill - entry_p) / init_risk)
                        cost_r = (entry_p * cost_rt_frac) / init_risk
                        r_list.append(gross_r - cost_r)
                        pos_dir = 0
                        continue
                    if h_p >= tp2:
                        gross_r = 2.25 if tp1_done else 3.0
                        cost_r = (entry_p * cost_rt_frac) / init_risk
                        r_list.append(gross_r - cost_r)
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
                        cost_r = (entry_p * cost_rt_frac) / init_risk
                        r_list.append(gross_r - cost_r)
                        pos_dir = 0
                        continue
                    if l_p <= tp2:
                        gross_r = 2.25 if tp1_done else 3.0
                        cost_r = (entry_p * cost_rt_frac) / init_risk
                        r_list.append(gross_r - cost_r)
                        pos_dir = 0
                        continue
                    if not tp1_done and l_p <= tp1:
                        tp1_done = True
                        sl = min(sl, entry_p)
                    if tp1_done:
                        sl = min(sl, l_p + 2.0 * a)

            # Signal am Close(t-1) -> Einstieg zum Open(t), falls flach
            if pos_dir == 0 and t > 250 and int(bars[t - 1]["t"]) >= start_ts:
                sig_t = t - 1
                dir_sig = 0
                if s_j is None:
                    dir_sig = s_i[sig_t]
                else:
                    # Paar: beide innerhalb [sig_t-2 .. sig_t], mindestens einer am sig_t
                    w_i = s_i[max(0, sig_t - 2) : sig_t + 1]
                    w_j = s_j[max(0, sig_t - 2) : sig_t + 1]
                    if (s_i[sig_t] == 1 or s_j[sig_t] == 1) and (1 in w_i) and (1 in w_j):
                        dir_sig = 1
                    elif (s_i[sig_t] == -1 or s_j[sig_t] == -1) and (-1 in w_i) and (-1 in w_j):
                        dir_sig = -1

                a_sig = atr14[sig_t]
                if dir_sig != 0 and a_sig is not None and a_sig > 0 and o_p > 0:
                    pos_dir = dir_sig
                    entry_p = o_p
                    init_risk = 2.0 * a_sig
                    tp1_done = False
                    if pos_dir == 1:
                        sl = entry_p - init_risk
                        tp1 = entry_p + 1.5 * init_risk
                        tp2 = entry_p + 3.0 * init_risk
                    else:
                        sl = entry_p + init_risk
                        tp1 = entry_p - 1.5 * init_risk
                        tp2 = entry_p - 3.0 * init_risk

    m = len(r_list)
    if m < 5:
        return {"trades": m, "wr": 0.0, "pf": 0.0, "exp_r": 0.0, "total_r": 0.0, "t_stat": 0.0, "p_val": 1.0}
    wins = [r for r in r_list if r > 0]
    losses = [r for r in r_list if r < 0]
    gw, gl = sum(wins), -sum(losses)
    pf = (gw / gl) if gl > 1e-12 else 99.0
    mean_r = sum(r_list) / m
    sd_r = math.sqrt(sum((r - mean_r) ** 2 for r in r_list) / (m - 1))
    t_stat = (mean_r / (sd_r / math.sqrt(m))) if sd_r > 1e-12 else 0.0
    p_val = 0.5 * math.erfc(t_stat / math.sqrt(2.0))
    return {
        "trades": m,
        "wr": round(len(wins) / m * 100.0, 1),
        "pf": round(pf, 3),
        "exp_r": round(mean_r, 3),
        "total_r": round(sum(r_list), 2),
        "t_stat": round(t_stat, 2),
        "p_val": round(p_val, 5),
    }


def apply_bh_fdr(rows: List[Dict[str, Any]]) -> None:
    """Benjamini-Hochberg FDR-Korrektur ueber alle 21 Kombinationen."""
    m = len(rows)
    indexed = sorted(enumerate(rows), key=lambda x: x[1]["p_val"])
    prev_q = 1.0
    for rank_rev in range(m - 1, -1, -1):
        orig_i, row = indexed[rank_rev]
        rank = rank_rev + 1
        q = min(prev_q, row["p_val"] * m / rank)
        rows[orig_i]["q_fdr"] = round(q, 5)
        prev_q = q


def run_causality_unit_test(bars: List[Dict[str, Any]]) -> None:
    """Prueft strikt, dass Abschneiden aller Balken > t identische Signale an t liefert."""
    sample = bars[:320]
    full_sigs = compute_causal_block_signals(sample)
    for t_cut in (280, 300, 315):
        trunc_sigs = compute_causal_block_signals(sample[: t_cut + 1])
        for b in BLOCKS:
            assert trunc_sigs[b][t_cut] == full_sigs[b][t_cut], f"Lookahead in {b} at bar {t_cut}!"
    print("CAUSALITY_UNIT_TEST_OK (0 Lookahead ueber alle 6 Bausteine)")


def run_basket(name: str, bars_by_sym: Dict[str, List[Dict[str, Any]]], start_ts: int, end_ts: int, cost_rt: float) -> List[Dict[str, Any]]:
    sigs_by_sym = {sym: compute_causal_block_signals(bars) for sym, bars in bars_by_sym.items()}
    rows = []
    combos: List[Tuple[str, Optional[str], str]] = [(b, None, b) for b in BLOCKS]
    for i in range(len(BLOCKS)):
        for j in range(i + 1, len(BLOCKS)):
            combos.append((BLOCKS[i], BLOCKS[j], f"{BLOCKS[i]}+{BLOCKS[j]}"))

    for bi, bj, label in combos:
        m1 = simulate_combo(bars_by_sym, sigs_by_sym, bi, bj, start_ts, end_ts, cost_rt)
        m2 = simulate_combo(bars_by_sym, sigs_by_sym, bi, bj, start_ts, end_ts, cost_rt * 2.0)
        rows.append({
            "combo": label,
            **m1,
            "exp_r_2x_cost": m2["exp_r"],
            "pf_2x_cost": m2["pf"],
        })
    apply_bh_fdr(rows)
    rows.sort(key=lambda x: (x["exp_r"] if x["trades"] >= 100 else -99.0), reverse=True)
    print(f"\n=== {name} (IS+Val, Holdout gesperrt) ===")
    for r in rows[:10]:
        gate = (r["trades"] >= 100 and r["pf"] >= 1.25 and r["exp_r"] >= 0.12 and r["exp_r_2x_cost"] > 0 and r["q_fdr"] < 0.05)
        print(f"  {r['combo']:22s} | tr={r['trades']:4d} WR={r['wr']:4.1f}% PF={r['pf']:5.3f} E[R]={r['exp_r']:+6.3f} (2x={r['exp_r_2x_cost']:+6.3f}) t={r['t_stat']:+5.2f} q_FDR={r['q_fdr']:.4f} | GATE={gate}")
    return rows


def main() -> None:
    # 1. Korb A: 10 US-ETFs (1D, IS+Val 2008-03-01 .. 2021-12-31)
    etf_bars = {s: json.loads((AUDIT_CACHE_DIR / f"{s}_1d.json").read_text(encoding="utf-8")) for s in ETF_UNIVERSE}
    run_causality_unit_test(etf_bars["SPY"])

    t_etf_start = int(datetime(2008, 3, 1, tzinfo=timezone.utc).timestamp())
    t_etf_end = int(datetime(2021, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())
    res_etf = run_basket("KORB A: 10 US-ETFs (1D, 2008-2021, 10bp)", etf_bars, t_etf_start, t_etf_end, 0.0010)

    # 2. Korb B: 6 Krypto-Majors (1D & 4h, IS+Val 2018-01-01 .. 2022-12-31)
    t_cry_start = int(datetime(2018, 1, 1, tzinfo=timezone.utc).timestamp())
    t_cry_end = int(datetime(2022, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    cry_1d = {s: json.loads((BT_CACHE_DIR / f"binance_{s}_1d.json").read_text(encoding="utf-8")) for s in CRYPTO_UNIVERSE}
    cry_4h = {s: json.loads((BT_CACHE_DIR / f"binance_{s}_4h.json").read_text(encoding="utf-8")) for s in CRYPTO_UNIVERSE}

    res_cry_1d = run_basket("KORB B1: 6 Krypto-Majors (1D, 2018-2022, 20bp)", cry_1d, t_cry_start, t_cry_end, 0.0020)
    res_cry_4h = run_basket("KORB B2: 6 Krypto-Majors (4h, 2018-2022, 20bp)", cry_4h, t_cry_start, t_cry_end, 0.0020)

    out_p = AUDIT_CACHE_DIR / "degencoder_ablation_is_val.json"
    out_p.write_text(json.dumps({"etf_1d": res_etf, "crypto_1d": res_cry_1d, "crypto_4h": res_cry_4h}, indent=2), encoding="utf-8")
    print(f"\nGespeichert: {out_p}")


if __name__ == "__main__":
    main()
