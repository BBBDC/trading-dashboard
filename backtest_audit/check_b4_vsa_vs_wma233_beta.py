#!/usr/bin/env python3
"""
backtest_audit/check_b4_vsa_vs_wma233_beta.py
=============================================
Prueft Opus' Beta-Einwand vor Aufnahme von B4_VSA Long-Only (WMA233) ins Shadow-Buch:
1. Strikt konservativ: SL vor TP1 und TP2 innerhalb jeder Kerze.
2. Vergleich gegen naiven Trend-Long (jeder Bar mit Close > WMA233, gleicher Exit, gleiche Assets).
3. Cluster-robuste t-Statistik (gruppiert nach ISO-Kalenderwoche YYYY-Www).
"""

import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from degencoder_ablation import BT_CACHE_DIR, CRYPTO_UNIVERSE, compute_causal_block_signals
from degencoder_engine import calculate_wma
from indicators import atr_wilder

AUDIT_CACHE_DIR = BASE_DIR / "knowledge_base" / "audit_cache"


def simulate_long_only_sl_first(
    bars_by_sym: Dict[str, List[Dict[str, Any]]],
    sig_fn,
    start_ts: int,
    end_ts: int,
    cost_rt_frac: float = 0.0020,
) -> List[Dict[str, Any]]:
    trades: List[Dict[str, Any]] = []
    for sym, bars in bars_by_sym.items():
        n = len(bars)
        if n < 260:
            continue
        atr14 = atr_wilder([float(b["h"]) for b in bars], [float(b["l"]) for b in bars], [float(b["c"]) for b in bars], 14)
        sigs = sig_fn(sym, bars)

        pos = False
        entry_p = sl = tp1 = tp2 = init_risk = 0.0
        entry_ts = 0
        tp1_done = False

        for t in range(250, n):
            bt = int(bars[t]["t"])
            if bt < start_ts or bt > end_ts:
                continue
            o_p, h_p, l_p = float(bars[t]["o"]), float(bars[t]["h"]), float(bars[t]["l"])
            a = atr14[t]
            if a is None or a <= 0:
                continue

            if pos:
                # 1. Strikt SL ZUERST (vor TP1 und TP2!)
                if l_p <= sl:
                    fill = min(o_p, sl)
                    gross_r = (0.5 * 1.5 + 0.5 * ((fill - entry_p) / init_risk)) if tp1_done else ((fill - entry_p) / init_risk)
                    r_net = gross_r - (entry_p * cost_rt_frac) / init_risk
                    trades.append({"sym": sym, "entry_ts": entry_ts, "r": round(r_net, 4)})
                    pos = False
                    continue
                # 2. TP2
                if h_p >= tp2:
                    r_net = (2.25 if tp1_done else 3.0) - (entry_p * cost_rt_frac) / init_risk
                    trades.append({"sym": sym, "entry_ts": entry_ts, "r": round(r_net, 4)})
                    pos = False
                    continue
                # 3. TP1 + Trailing fuer Folgekerzen
                if not tp1_done and h_p >= tp1:
                    tp1_done = True
                    sl = max(sl, entry_p)
                if tp1_done:
                    sl = max(sl, h_p - 2.0 * a)

            if not pos and t > 250 and int(bars[t - 1]["t"]) >= start_ts:
                sig_t = t - 1
                a_sig = atr14[sig_t]
                if sigs[sig_t] == 1 and a_sig is not None and a_sig > 0 and o_p > 0:
                    pos = True
                    entry_p = o_p
                    entry_ts = bt
                    init_risk = 2.0 * a_sig
                    tp1_done = False
                    sl = entry_p - init_risk
                    tp1 = entry_p + 1.5 * init_risk
                    tp2 = entry_p + 3.0 * init_risk
    return trades


def summarize_clustered(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    m = len(trades)
    if m < 2:
        return {"trades": m}
    r_list = [t["r"] for t in trades]
    wins = [r for r in r_list if r > 0]
    losses = [r for r in r_list if r < 0]
    pf = (sum(wins) / (-sum(losses))) if losses else 99.0
    mean_r = sum(r_list) / m
    sd_r = math.sqrt(sum((r - mean_r) ** 2 for r in r_list) / (m - 1))
    t_iid = mean_r / (sd_r / math.sqrt(m)) if sd_r > 1e-12 else 0.0

    # Cluster-robuste t-Statistik (Gruppierung nach ISO-Kalenderwoche des Einstiegs)
    by_week: Dict[str, List[float]] = defaultdict(list)
    for t in trades:
        dt = datetime.fromtimestamp(t["entry_ts"], tz=timezone.utc)
        iso = dt.isocalendar()
        by_week[f"{iso.year}-W{iso.week:02d}"].append(t["r"])

    # Standardfehler des Gesamtmittelwerts aus Cluster-Summen (Liang-Zeger / Cam-Miller)
    g = len(by_week)
    cluster_dev = [sum(r - mean_r for r in w_rs) for w_rs in by_week.values()]
    var_cluster = (g / (g - 1)) * sum(d * d for d in cluster_dev) / (m * m) if g > 1 else (sd_r * sd_r / m)
    se_cluster = math.sqrt(max(1e-18, var_cluster))
    t_cluster = mean_r / se_cluster

    return {
        "trades": m,
        "weeks": g,
        "wr": round(len(wins) / m * 100.0, 1),
        "pf": round(pf, 3),
        "exp_r": round(mean_r, 3),
        "total_r": round(sum(r_list), 2),
        "t_iid": round(t_iid, 2),
        "t_cluster_week": round(t_cluster, 2),
    }


def main() -> None:
    cry_1d = {s: json.loads((BT_CACHE_DIR / f"binance_{s}_1d.json").read_text(encoding="utf-8")) for s in CRYPTO_UNIVERSE}
    b4_sigs = {s: compute_causal_block_signals(bars)["B4_VSA"] for s, bars in cry_1d.items()}
    wma_sigs: Dict[str, List[int]] = {}
    for s, bars in cry_1d.items():
        closes = [float(b["c"]) for b in bars]
        wma233 = calculate_wma(closes, 233)
        wma_sigs[s] = [
            1 if (wma233[i] is not None and closes[i] > float(wma233[i])) else 0
            for i in range(len(bars))
        ]

    t_is0 = int(datetime(2018, 1, 1, tzinfo=timezone.utc).timestamp())
    t_is1 = int(datetime(2022, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())
    t_ho0 = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp())
    t_ho1 = int(datetime(2026, 11, 20, 23, 59, 59, tzinfo=timezone.utc).timestamp())

    res = {}
    for label, s_ts, e_ts in [("IS+Val (2018-2022)", t_is0, t_is1), ("Holdout (2023-2026)", t_ho0, t_ho1)]:
        tr_b4 = simulate_long_only_sl_first(cry_1d, lambda s, b: b4_sigs[s], s_ts, e_ts)
        tr_naive = simulate_long_only_sl_first(cry_1d, lambda s, b: wma_sigs[s], s_ts, e_ts)
        res[label] = {
            "b4_vsa_long_only": summarize_clustered(tr_b4),
            "naive_wma233_long": summarize_clustered(tr_naive),
        }
        print(f"=== {label} (Strikt SL vor TP) ===")
        print("  B4_VSA Long-Only :", res[label]["b4_vsa_long_only"])
        print("  Naive > WMA233   :", res[label]["naive_wma233_long"])

    (AUDIT_CACHE_DIR / "b4_vsa_beta_benchmark.json").write_text(json.dumps(res, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
