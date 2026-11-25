#!/usr/bin/env python3
"""
backtest_audit/monthly_engine.py
================================
Monatliche Allokations-Engine gemaess Pre-Registration v2.1:
- SHA256-Pruefung aller Snapshot-Dateien per assert
- rf_d(k) = max(0, IRX_close(k-1)) / 100 / 252
- Exakte Ausfuehrung zum Open(t+1) mit Close->Open / Open->Close Split (L1)
- Driftende Buy-and-Hold-Gewichte zwischen Monatsenden (L2)
- Rebalancing ausschliesslich ueber Monatsend-Kalender, kein Rebalancing bei sum(w)==0 (L3)
- Erstes Signal am letzten Handelstag VOR Periodenbeginn (L6)
- Newey-West HAC (Lag=21) Alpha & assert n_boot == 10_000
"""

import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from indicators import rolling_vol_annualized

BASE_DIR = Path(__file__).resolve().parent.parent
AUDIT_CACHE_DIR = BASE_DIR / "knowledge_base" / "audit_cache"
MANIFEST_FILE = AUDIT_CACHE_DIR / "snapshot_manifest.json"

S1_UNIVERSE = ["SPY", "QQQ", "EWG", "EWJ", "TLT", "IEF", "FXE", "FXY", "GLD", "DBC"]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_verified_data(symbols: List[str], max_date: str = "2021-12-31", allow_holdout: bool = False) -> Dict[str, Any]:
    if max_date > "2021-12-31" and not allow_holdout:
        raise PermissionError("Holdout-Daten (> 2021-12-31) sind bis zum Gate gesperrt!")

    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    files_meta = manifest["files"]

    # SHA256-Integritaet aller verwendeten Dateien per assert pruefen
    for sym in list(symbols) + ["IRX"]:
        fname = f"{sym}_1d.json"
        p = AUDIT_CACHE_DIR / fname
        assert fname in files_meta, f"{fname} fehlt im Manifest"
        assert _sha256_file(p) == files_meta[fname]["sha256"], f"SHA256-Mismatch fuer {fname}"

    spy_raw = json.loads((AUDIT_CACHE_DIR / "SPY_1d.json").read_text(encoding="utf-8"))
    dates = [b["date"] for b in spy_raw if b["date"] <= max_date]
    n = len(dates)

    # rf_d(k) = max(0, IRX_close(k-1)) / 100 / 252
    irx_raw = json.loads((AUDIT_CACHE_DIR / "IRX_1d.json").read_text(encoding="utf-8"))
    irx_map = {b["date"]: max(0.0, float(b["c"]) / 100.0) for b in irx_raw if b["date"] <= max_date}
    irx_aligned = [0.0] * n
    last_irx = 0.0436
    for i, d in enumerate(dates):
        if d in irx_map:
            last_irx = irx_map[d]
        irx_aligned[i] = last_irx
    rf_daily = [irx_aligned[i - 1] / 252.0 if i > 0 else irx_aligned[0] / 252.0 for i in range(n)]

    series: Dict[str, Dict[str, List[float]]] = {}
    ffill_counts: Dict[str, int] = {}
    for sym in symbols:
        raw = json.loads((AUDIT_CACHE_DIR / f"{sym}_1d.json").read_text(encoding="utf-8"))
        by_d = {b["date"]: b for b in raw if b["date"] <= max_date}
        o_arr, h_arr, l_arr, c_arr = [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n
        ff = 0
        has_started = False
        for i, d in enumerate(dates):
            if d in by_d:
                b = by_d[d]
                o_arr[i], h_arr[i], l_arr[i], c_arr[i] = float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])
                has_started = True
            elif has_started:
                o_arr[i] = h_arr[i] = l_arr[i] = c_arr[i] = c_arr[i - 1]
                ff += 1
        ffill_counts[sym] = ff
        series[sym] = {"o": o_arr, "h": h_arr, "l": l_arr, "c": c_arr}

    return {"dates": dates, "rf_daily": rf_daily, "series": series, "ffill_counts": ffill_counts}


def run_monthly_allocation(
    data: Dict[str, Any],
    universe: List[str],
    target_weights_fn,
    start_date: str = "2008-03-01",
    end_date: str = "2021-12-31",
    cost_bps: float = 10.0,
) -> Dict[str, Any]:
    """
    Exakte monatliche Allokations-Simulation (L1, L2, L3, L6):
    - Signal am Monatsende (inkl. letzter Handelstag vor `start_date`)
    - Ausfuehrung am naechsten Open(t+1) mit Open/Close-Split & Turnover-Kosten
    - Driftende Buy-and-Hold-Gewichte zwischen Rebalancings
    """
    dates = data["dates"]
    rf_daily = data["rf_daily"]
    series = data["series"]
    n_bars = len(dates)
    half_cost = (cost_bps / 10000.0) / 2.0

    # Finde ersten Index >= start_date und letzten <= end_date
    start_idx = next(i for i, d in enumerate(dates) if d >= start_date)
    end_idx = max(i for i, d in enumerate(dates) if d <= end_date)
    assert start_idx > 0, "Fuer das erste Signal vor Periodenbeginn wird t = start_idx - 1 benoetigt"

    # Erste Allokation: Signal am letzten Handelstag VOR Periodenbeginn (L6)
    weights = {s: 0.0 for s in universe}
    pending_weights: Optional[Dict[str, float]] = target_weights_fn(start_idx - 1)

    excess_rets: List[float] = []
    out_dates: List[str] = []
    out_rf: List[float] = []
    total_turnover = 0.0
    total_cost_drag = 0.0
    rebal_count = 0
    cash_months = 0

    for t in range(start_idx, end_idx + 1):
        d = dates[t]
        rf_t = rf_daily[t]

        if pending_weights is not None:
            # L1: Rendite Close(t-1) -> Open(t) mit alten Gewichten
            r_co = 0.0
            for s in universe:
                if weights[s] > 0.0:
                    c_prev = series[s]["c"][t - 1]
                    o_curr = series[s]["o"][t]
                    if c_prev > 0:
                        r_co += weights[s] * (o_curr / c_prev - 1.0)
            w_cash_old = max(0.0, 1.0 - sum(weights.values()))
            # Drifte alte Gewichte bis Open(t) fuer exakten Turnover
            denom_co = 1.0 + r_co
            drifted_open = {}
            for s in universe:
                if weights[s] > 0.0 and series[s]["c"][t - 1] > 0 and denom_co > 0:
                    drifted_open[s] = weights[s] * (series[s]["o"][t] / series[s]["c"][t - 1]) / denom_co
                else:
                    drifted_open[s] = 0.0

            turnover = sum(abs(pending_weights.get(s, 0.0) - drifted_open[s]) for s in universe)
            cost_open = turnover * half_cost
            total_turnover += turnover
            total_cost_drag += cost_open
            rebal_count += 1
            if sum(pending_weights.values()) == 0.0:
                cash_months += 1

            # L1: Rendite Open(t) -> Close(t) mit neuen Gewichten
            weights = {s: pending_weights.get(s, 0.0) for s in universe}
            pending_weights = None

            r_oc = 0.0
            for s in universe:
                if weights[s] > 0.0:
                    o_curr = series[s]["o"][t]
                    c_curr = series[s]["c"][t]
                    if o_curr > 0:
                        r_oc += weights[s] * (c_curr / o_curr - 1.0)
            w_cash_new = max(0.0, 1.0 - sum(weights.values()))

            # Verkettung Close->Open (inkl. Kosten zum Open) mit Open->Close + Tages-Cash
            port_ret = (1.0 + r_co) * (1.0 - cost_open) * (1.0 + r_oc) - 1.0
            # Tages-T-Bill-Verzinsung auf anteiliges Cash
            port_ret += 0.5 * (w_cash_old + w_cash_new) * rf_t

            # Drifte neue Gewichte von Open(t) -> Close(t)
            denom_oc = 1.0 + r_oc
            if denom_oc > 0:
                for s in universe:
                    if weights[s] > 0.0 and series[s]["o"][t] > 0:
                        weights[s] = weights[s] * (series[s]["c"][t] / series[s]["o"][t]) / denom_oc
        else:
            # L2: Normaler Tag ohne Rebalancing -> Gewichte driften mit Close(t)/Close(t-1)
            r_cc = 0.0
            for s in universe:
                if weights[s] > 0.0 and series[s]["c"][t - 1] > 0:
                    r_cc += weights[s] * (series[s]["c"][t] / series[s]["c"][t - 1] - 1.0)
            w_cash = max(0.0, 1.0 - sum(weights.values()))
            port_ret = r_cc + w_cash * rf_t

            denom_cc = 1.0 + r_cc
            if denom_cc > 0:
                for s in universe:
                    if weights[s] > 0.0 and series[s]["c"][t - 1] > 0:
                        weights[s] = weights[s] * (series[s]["c"][t] / series[s]["c"][t - 1]) / denom_cc

        excess_rets.append(port_ret - rf_t)
        out_dates.append(d)
        out_rf.append(rf_t)

        # L3: Rebalancing ausschliesslich am Monatsende (nie ueber sum(weights)==0!)
        if t < end_idx and dates[t + 1][:7] != d[:7]:
            pending_weights = target_weights_fn(t)

    return {
        "dates": out_dates,
        "rf_daily": out_rf,
        "excess_rets": excess_rets,
        "rebal_count": rebal_count,
        "cash_months": cash_months,
        "ann_turnover_pct": round((total_turnover / (len(out_dates) / 252.0)) * 100.0, 1),
        "ann_cost_drag_bp": round((total_cost_drag / (len(out_dates) / 252.0)) * 10000.0, 2),
    }


def make_rp_trend_fn(
    data: Dict[str, Any],
    universe: List[str],
    lookback: int = 252,
    skip: int = 21,
    vol_win: int = 60,
    use_trend_filter: bool = True,
):
    series = data["series"]
    rf_daily = data["rf_daily"]
    vols = {s: rolling_vol_annualized(series[s]["c"], vol_win) for s in universe}

    def _fn(t: int) -> Dict[str, float]:
        inv_v = {}
        for s in universe:
            v = vols[s][t]
            if v is not None and v > 1e-6:
                inv_v[s] = 1.0 / v
        tot = sum(inv_v.values())
        if tot <= 0:
            return {s: 0.0 for s in universe}
        w_rp = {s: inv_v.get(s, 0.0) / tot for s in universe}
        if not use_trend_filter:
            return w_rp

        # CumTBillReturn[t-lookback : t-skip] = prod_{k=t-lookback+1}^{t-skip} (1 + rf_d(k)) - 1
        end_k = t - skip
        start_k = t - lookback
        cum_tbill = 1.0
        for k in range(start_k + 1, end_k + 1):
            cum_tbill *= (1.0 + rf_daily[k])
        cum_tbill -= 1.0

        out = {}
        for s in universe:
            c0 = series[s]["c"][start_k]
            c1 = series[s]["c"][end_k]
            if c0 > 0 and c1 > 0:
                tr = (c1 / c0 - 1.0) - cum_tbill
                out[s] = w_rp[s] if tr > 0.0 else 0.0
            else:
                out[s] = 0.0
        return out

    return _fn


def make_60_40_fn():
    def _fn(t: int) -> Dict[str, float]:
        w = {s: 0.0 for s in S1_UNIVERSE}
        w["SPY"] = 0.60
        w["IEF"] = 0.40
        return w
    return _fn


def compute_curve_metrics(
    dates: List[str],
    rf_daily: List[float],
    excess_rets: List[float],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    vol_scale_k: float = 1.0,
) -> Dict[str, Any]:
    idxs = [
        i for i, d in enumerate(dates)
        if (start_date is None or d >= start_date) and (end_date is None or d <= end_date)
    ]
    n = len(idxs)
    if n < 2:
        return {"days": n}
    ex = [excess_rets[i] for i in idxs]
    rf = [rf_daily[i] for i in idxs]
    mean_ex = sum(ex) / n
    var_ex = sum((x - mean_ex) ** 2 for x in ex) / (n - 1)
    std_ex = math.sqrt(var_ex)
    sr = (mean_ex / std_ex * math.sqrt(252.0)) if std_ex > 1e-12 else 0.0
    ann_vol = std_ex * math.sqrt(252.0)

    # Max-DD auf taeglich verketteter Kurve prod(1 + rf + k * r_ex)
    eq = 1.0
    peak = 1.0
    max_dd = 0.0
    for r_f, r_e in zip(rf, ex):
        eq *= (1.0 + r_f + vol_scale_k * r_e)
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak
        if dd > max_dd:
            max_dd = dd

    return {
        "days": n,
        "ann_excess_ret_pct": round(mean_ex * 252.0 * 100.0, 2),
        "ann_vol_pct": round(ann_vol * 100.0, 2),
        "excess_sharpe": round(sr, 3),
        "max_dd_pct": round(max_dd * 100.0, 2),
    }


def ols_newey_west_alpha(strat_ex: List[float], bench_ex: List[float], lag: int = 21) -> Dict[str, float]:
    """OLS strat_ex = alpha + beta * bench_ex mit Newey-West HAC Standardfehlern (Bartlett-Kernel)."""
    n = len(strat_ex)
    mx = sum(bench_ex) / n
    my = sum(strat_ex) / n
    sxx = sum((x - mx) ** 2 for x in bench_ex)
    sxy = sum((x - mx) * (y - my) for x, y in zip(bench_ex, strat_ex))
    beta = sxy / sxx if sxx > 1e-18 else 0.0
    alpha = my - beta * mx
    u = [y - (alpha + beta * x) for x, y in zip(bench_ex, strat_ex)]

    # X'X / n fuer [1, x]
    m11 = 1.0
    m12 = mx
    m22 = sum(x * x for x in bench_ex) / n
    det = m11 * m22 - m12 * m12
    # (X'X/n)^-1
    inv00 = m22 / det
    inv01 = -m12 / det
    inv11 = m11 / det

    # Newey-West S = Gamma_0 + sum_{l=1..lag} (1 - l/(lag+1)) * (Gamma_l + Gamma_l')
    s00 = s01 = s11 = 0.0
    for i in range(n):
        xi = bench_ex[i]
        ui = u[i]
        s00 += ui * ui
        s01 += ui * ui * xi
        s11 += ui * ui * xi * xi

    for l in range(1, lag + 1):
        w = 1.0 - l / (lag + 1.0)
        g00 = g01 = g10 = g11 = 0.0
        for i in range(l, n):
            ui, uj = u[i], u[i - l]
            xi, xj = bench_ex[i], bench_ex[i - l]
            g00 += ui * uj
            g01 += ui * uj * xj
            g10 += ui * xi * uj
            g11 += ui * xi * uj * xj
        s00 += w * 2.0 * g00
        s01 += w * (g01 + g10)
        s11 += w * 2.0 * g11

    s00 /= n
    s01 /= n
    s11 /= n
    # Var(alpha_hat) = (1/n) * [(X'X/n)^-1 * S * (X'X/n)^-1]_{0,0}
    a0 = inv00 * s00 + inv01 * s01
    a1 = inv00 * s01 + inv01 * s11
    var_alpha = (a0 * inv00 + a1 * inv01) / n
    se_alpha = math.sqrt(max(1e-18, var_alpha))
    t_stat = alpha / se_alpha
    p_val = 0.5 * math.erfc(t_stat / math.sqrt(2.0))
    return {
        "alpha_ann_pct": round(alpha * 252.0 * 100.0, 2),
        "beta": round(beta, 3),
        "t_stat_nw": round(t_stat, 2),
        "p_value_nw": round(p_val, 5),
    }


def stationary_bootstrap_sharpe_p(
    excess_rets: List[float],
    mean_block: float = 20.0,
    n_boot: int = 10_000,
    seed: int = 42,
) -> float:
    assert n_boot == 10_000, "Pre-Registration v2.1 verlangt exakt 10.000 Bootstrap-Ziehungen"
    n = len(excess_rets)
    rng = random.Random(seed)
    p_jump = 1.0 / mean_block
    mean_orig = sum(excess_rets) / n
    centered = [x - mean_orig for x in excess_rets]
    var_orig = sum(x * x for x in centered) / (n - 1)
    sr_orig = mean_orig / math.sqrt(var_orig)

    ge_cnt = 0
    for _ in range(n_boot):
        idx = rng.randrange(n)
        s = s2 = 0.0
        for _ in range(n):
            v = centered[idx]
            s += v
            s2 += v * v
            idx = rng.randrange(n) if rng.random() < p_jump else (idx + 1) % n
        m = s / n
        v = max(1e-18, (s2 - n * m * m) / (n - 1))
        if (m / math.sqrt(v)) >= sr_orig:
            ge_cnt += 1
    return round(ge_cnt / n_boot, 4)


def deflated_sharpe_ratio(sr_ann: float, n_obs: int, skew: float, kurt: float, n_trials: int = 12) -> float:
    """Bailey & Lopez de Prado (2014) Deflated Sharpe Ratio (auf Tagesbasis umgerechnet)."""
    sr_d = sr_ann / math.sqrt(252.0)
    # Erwartetes Maximum unter N_trials unabhaengigen Standardnormalen (Euler-Mascheroni)
    emc = 0.5772156649
    z1 = math.sqrt(2.0 * math.log(n_trials))
    # Normal-Quantil Approximation fuer (1 - 1/N) und (1 - 1/(N*e))
    sr_0 = math.sqrt(max(0.0, (1.0 / n_obs))) * ((1.0 - emc) * z1 + emc * math.sqrt(2.0 * math.log(n_trials * math.e)))
    denom = math.sqrt(max(1e-12, 1.0 - skew * sr_d + ((kurt - 1.0) / 4.0) * (sr_d ** 2)))
    z = (sr_d - sr_0) * math.sqrt(n_obs - 1) / denom
    return round(0.5 * (1.0 + math.erf(z / math.sqrt(2.0))), 4)
