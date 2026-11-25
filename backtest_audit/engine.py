#!/usr/bin/env python3
"""
backtest_audit/engine.py
========================
Deterministische Backtest-Engine gemaess Pre-Registration v1.2.
Erzwingt strikte Kausalitaet, T-Bill-Excess-Returns, Short-Carry (T-Bill - 50 bp),
Hebel-Finanzierung (T-Bill + 50 bp), Cluster-/Hebel-Caps und Holdout-Abschottung.
"""

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from indicators import (
    atr_wilder,
    donchian_prev_max,
    donchian_prev_min,
    ibs,
    rolling_vol_annualized,
    rsi_wilder,
    sma,
)

BASE_DIR = Path(__file__).resolve().parent.parent
AUDIT_CACHE_DIR = BASE_DIR / "knowledge_base" / "audit_cache"

S1_UNIVERSE = ["SPY", "QQQ", "EWG", "EWJ", "TLT", "IEF", "FXE", "FXY", "GLD", "DBC"]
S1_CLUSTERS = {
    "SPY": "EQUITY", "QQQ": "EQUITY", "EWG": "EQUITY", "EWJ": "EQUITY",
    "TLT": "BOND", "IEF": "BOND",
    "FXE": "FX", "FXY": "FX",
    "GLD": "COMM", "DBC": "COMM",
}
S1_CLUSTER_CAPS = {"EQUITY": 2, "BOND": 1, "FX": 2, "COMM": 2}

S2_UNIVERSE = ["SPY", "QQQ", "DIA", "EWG", "EWU"]
S2_US_INDICES = {"SPY", "QQQ", "DIA"}
S2_CONTROLS = ["TLT", "GLD"]


def load_audit_data(symbols: List[str], max_date: str = "2021-12-31", allow_holdout: bool = False) -> Dict[str, Any]:
    """
    Laedt eingefrorene Audit-Daten und richtet sie auf den SPY-Handelskalender aus.
    Technisches Holdout-Gate: `max_date > '2021-12-31'` ist ohne `allow_holdout=True` gesperrt.
    """
    if max_date > "2021-12-31" and not allow_holdout:
        raise PermissionError("Holdout-Daten (> 2021-12-31) sind bis zur Erfuellung des Gates gesperrt!")

    spy_raw = json.loads((AUDIT_CACHE_DIR / "SPY_1d.json").read_text(encoding="utf-8"))
    dates = [b["date"] for b in spy_raw if b["date"] <= max_date]
    date_to_idx = {d: i for i, d in enumerate(dates)}

    irx_raw = json.loads((AUDIT_CACHE_DIR / "IRX_1d.json").read_text(encoding="utf-8"))
    irx_map = {b["date"]: max(0.0, float(b["c"]) / 100.0) for b in irx_raw if b["date"] <= max_date}
    rf_daily: List[float] = []
    last_rf = 0.04
    for d in dates:
        if d in irx_map:
            last_rf = irx_map[d]
        rf_daily.append(last_rf / 252.0)

    series: Dict[str, Dict[str, List[float]]] = {}
    for sym in symbols:
        raw = json.loads((AUDIT_CACHE_DIR / f"{sym}_1d.json").read_text(encoding="utf-8"))
        by_d = {b["date"]: b for b in raw if b["date"] <= max_date}
        n = len(dates)
        o_arr, h_arr, l_arr, c_arr, valid = [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n, [False] * n
        for i, d in enumerate(dates):
            if d in by_d:
                b = by_d[d]
                o_arr[i], h_arr[i], l_arr[i], c_arr[i] = float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])
                valid[i] = True
            elif i > 0 and valid[i - 1]:
                # Selten fehlender Einzeltag: flach fortschreiben
                o_arr[i] = h_arr[i] = l_arr[i] = c_arr[i] = c_arr[i - 1]
                valid[i] = True
        series[sym] = {"o": o_arr, "h": h_arr, "l": l_arr, "c": c_arr, "valid": valid}

    return {"dates": dates, "date_to_idx": date_to_idx, "rf_daily": rf_daily, "series": series}


@dataclass
class Position:
    symbol: str
    direction: int  # +1 Long, -1 Short
    shares: float
    entry_price: float
    entry_idx: int
    entry_date: str
    init_risk_dollar: float
    stop_price: float
    extreme_close: float
    pending_exit: bool = False


@dataclass
class PendingOrder:
    symbol: str
    direction: int
    target_risk_dollar: float
    atr_at_signal: float
    priority_score: float
    is_reversal: bool = False


def compute_metrics(
    dates: List[str],
    excess_rets: List[float],
    rf_daily: List[float],
    trades: List[Dict[str, Any]],
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    """Berechnet Excess-Sharpe, Max-DD, Profit-Factor, Expectancy in R und Win-Rate fuer ein Fenster."""
    idxs = [i for i, d in enumerate(dates) if start_date <= d <= end_date]
    if not idxs:
        return {"days": 0}

    win_ex = [excess_rets[i] for i in idxs]
    n = len(win_ex)
    mean_ex = sum(win_ex) / n
    var_ex = sum((x - mean_ex) ** 2 for x in win_ex) / (n - 1) if n > 1 else 0.0
    std_ex = math.sqrt(var_ex)
    sharpe = (mean_ex / std_ex * math.sqrt(252.0)) if std_ex > 1e-12 else 0.0
    ann_vol = std_ex * math.sqrt(252.0)

    # Excess Equity Curve fuer Drawdown
    eq = 1.0
    peak = 1.0
    max_dd = 0.0
    for x in win_ex:
        eq *= (1.0 + x)
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak
        if dd > max_dd:
            max_dd = dd

    # Trades nach Einstiegsdatum in diesem Fenster
    w_trades = [t for t in trades if start_date <= t["entry_date"] <= end_date]
    r_list = [float(t["r_mult"]) for t in w_trades]
    wins = [r for r in r_list if r > 0]
    losses = [r for r in r_list if r < 0]
    gross_w = sum(wins)
    gross_l = -sum(losses)
    pf = (gross_w / gross_l) if gross_l > 1e-12 else (99.0 if gross_w > 0 else 0.0)
    exp_r = (sum(r_list) / len(r_list)) if r_list else 0.0
    wr = (len(wins) / len(r_list) * 100.0) if r_list else 0.0

    # Unabhaengige Episoden (±2 Handelstage)
    episodes = 0
    last_ep_idx = -999
    for t in sorted(w_trades, key=lambda x: x["entry_idx"]):
        if (t["entry_idx"] - last_ep_idx) > 2:
            episodes += 1
            last_ep_idx = t["entry_idx"]

    return {
        "days": n,
        "ann_excess_ret_pct": round(mean_ex * 252.0 * 100.0, 2),
        "ann_vol_pct": round(ann_vol * 100.0, 2),
        "excess_sharpe": round(sharpe, 3),
        "max_dd_pct": round(max_dd * 100.0, 2),
        "trades": len(w_trades),
        "episodes": episodes,
        "win_rate_pct": round(wr, 1),
        "profit_factor": round(pf, 3),
        "expectancy_r": round(exp_r, 3),
        "total_r": round(sum(r_list), 2),
    }


def _apply_daily_financing(
    equity: float,
    long_notional: float,
    short_notional: float,
    rf_day: float,
) -> float:
    """T-Bill auf freies Cash, T-Bill + 50bp auf Hebel, T-Bill - 50bp auf Short-Erloese (P6)."""
    free_cash = max(0.0, equity - long_notional)
    borrowed_long = max(0.0, long_notional - equity)
    spread_day = 0.0050 / 252.0
    fin_pnl = (
        free_cash * rf_day
        - borrowed_long * (rf_day + spread_day)
        + short_notional * (rf_day - spread_day)
    )
    return fin_pnl


def run_strategy1(
    data: Dict[str, Any],
    start_date: str = "2008-03-01",
    end_date: str = "2021-12-31",
    n_entry: int = 50,
    n_exit: int = 25,
    atr_mult: float = 3.0,
    cost_bps: float = 10.0,
    long_only_equities: bool = False,
) -> Dict[str, Any]:
    """Strategie 1: Multi-Asset TSMOM gemaess Pre-Registration v1.2."""
    dates = data["dates"]
    rf_daily = data["rf_daily"]
    series = data["series"]
    n_bars = len(dates)
    half_cost = (cost_bps / 10000.0) / 2.0

    # Vorberechnung der Indikatoren auf voller Historie bis end_date
    ind: Dict[str, Dict[str, List[Optional[float]]]] = {}
    for sym in S1_UNIVERSE:
        s = series[sym]
        ind[sym] = {
            "d_hi": donchian_prev_max(s["c"], n_entry),
            "d_lo": donchian_prev_min(s["c"], n_entry),
            "ex_lo": donchian_prev_min(s["c"], n_exit),
            "ex_hi": donchian_prev_max(s["c"], n_exit),
            "atr20": atr_wilder(s["h"], s["l"], s["c"], 20),
        }

    equity = 100000.0
    positions: Dict[str, Position] = {}
    pending_exits: set = set()
    pending_entries: List[PendingOrder] = []
    trades: List[Dict[str, Any]] = []
    excess_rets = [0.0] * n_bars

    for t in range(n_bars):
        d = dates[t]
        if d < start_date or d > end_date:
            continue

        eq_prev = equity
        prev_closes = {sym: series[sym]["c"][t - 1] for sym in positions}

        # 1. Ausstehende Exits zum Open(t) ausfuehren
        for sym in list(pending_exits):
            if sym in positions:
                pos = positions.pop(sym)
                fill = series[sym]["o"][t]
                raw_pnl = pos.direction * pos.shares * (fill - pos.entry_price)
                exit_cost = abs(pos.shares) * fill * half_cost
                # Adjustiere Equity um Veraenderung seit t-1 Close + Exit-Kosten
                mtm_prev = pos.direction * pos.shares * (prev_closes[sym] - pos.entry_price)
                equity += (raw_pnl - mtm_prev) - exit_cost
                total_cost = abs(pos.shares) * pos.entry_price * half_cost + exit_cost
                net_pnl = raw_pnl - total_cost
                trades.append({
                    "symbol": sym,
                    "direction": pos.direction,
                    "entry_idx": pos.entry_idx,
                    "entry_date": pos.entry_date,
                    "exit_idx": t,
                    "exit_date": d,
                    "r_mult": net_pnl / pos.init_risk_dollar,
                    "reason": "DONCHIAN_EXIT",
                })
        pending_exits.clear()

        # 2. Ausstehende Entries zum Open(t) ausfuehren (Cluster-Caps + Hebel-Cap 2.0x)
        pending_entries.sort(key=lambda x: x.priority_score, reverse=True)
        for ord_ in pending_entries:
            sym = ord_.symbol
            if sym in positions or len(positions) >= 6:
                continue
            cl = S1_CLUSTERS[sym]
            cl_cnt = sum(1 for p in positions.values() if S1_CLUSTERS[p.symbol] == cl)
            if cl_cnt >= S1_CLUSTER_CAPS[cl]:
                continue

            fill = series[sym]["o"][t]
            if fill <= 0:
                continue
            stop_dist = atr_mult * ord_.atr_at_signal
            if stop_dist <= 0:
                continue
            shares = ord_.target_risk_dollar / stop_dist
            notional = shares * fill

            # Brutto-Hebel-Cap 2.0x (P7: auf Restkapazitaet kuerzen)
            cur_gross = sum(abs(p.shares) * series[p.symbol]["o"][t] for p in positions.values())
            max_gross = 2.0 * equity
            rem_cap = max(0.0, max_gross - cur_gross)
            if notional > rem_cap:
                if rem_cap < 0.10 * notional:
                    continue
                shares = rem_cap / fill
                notional = rem_cap

            entry_cost = notional * half_cost
            equity -= entry_cost
            init_stop = fill - stop_dist if ord_.direction == 1 else fill + stop_dist
            positions[sym] = Position(
                symbol=sym,
                direction=ord_.direction,
                shares=shares,
                entry_price=fill,
                entry_idx=t,
                entry_date=d,
                init_risk_dollar=shares * stop_dist,
                stop_price=init_stop,
                extreme_close=fill,
            )
            prev_closes[sym] = fill
        pending_entries.clear()

        # 3. Intraday-Stop-Pruefung gegen [Open(t), Low(t)/High(t)]
        for sym in list(positions.keys()):
            pos = positions[sym]
            o_p, h_p, l_p = series[sym]["o"][t], series[sym]["h"][t], series[sym]["l"][t]
            hit = False
            fill_stop = pos.stop_price
            if pos.direction == 1 and l_p <= pos.stop_price:
                hit = True
                fill_stop = min(o_p, pos.stop_price)
            elif pos.direction == -1 and h_p >= pos.stop_price:
                hit = True
                fill_stop = max(o_p, pos.stop_price)

            if hit:
                positions.pop(sym)
                raw_pnl = pos.direction * pos.shares * (fill_stop - pos.entry_price)
                exit_cost = abs(pos.shares) * fill_stop * half_cost
                mtm_prev = pos.direction * pos.shares * (prev_closes[sym] - pos.entry_price)
                equity += (raw_pnl - mtm_prev) - exit_cost
                total_cost = abs(pos.shares) * pos.entry_price * half_cost + exit_cost
                net_pnl = raw_pnl - total_cost
                trades.append({
                    "symbol": sym,
                    "direction": pos.direction,
                    "entry_idx": pos.entry_idx,
                    "entry_date": pos.entry_date,
                    "exit_idx": t,
                    "exit_date": d,
                    "r_mult": net_pnl / pos.init_risk_dollar,
                    "reason": "CHANDELIER_STOP",
                })

        # 4. Mark-to-Market zum Close(t) + taegliche Finanzierung
        long_not = 0.0
        short_not = 0.0
        for sym, pos in positions.items():
            c_p = series[sym]["c"][t]
            equity += pos.direction * pos.shares * (c_p - prev_closes[sym])
            if pos.direction == 1:
                long_not += pos.shares * c_p
            else:
                short_not += pos.shares * c_p
        equity += _apply_daily_financing(eq_prev, long_not, short_not, rf_daily[t])

        day_ret = (equity / eq_prev - 1.0) if eq_prev > 0 else 0.0
        excess_rets[t] = day_ret - rf_daily[t]

        # 5. Signale am Close(t) fuer Open(t+1) berechnen + Chandelier monoton nachziehen
        if d == end_date or t + 1 >= n_bars or dates[t + 1] > end_date:
            continue

        for sym, pos in positions.items():
            c_p = series[sym]["c"][t]
            a20 = ind[sym]["atr20"][t]
            if a20 is None:
                continue
            if pos.direction == 1:
                pos.extreme_close = max(pos.extreme_close, c_p)
                pos.stop_price = max(pos.stop_price, pos.extreme_close - atr_mult * a20)
                ex_lo = ind[sym]["ex_lo"][t]
                if ex_lo is not None and c_p < ex_lo:
                    pending_exits.add(sym)
            else:
                pos.extreme_close = min(pos.extreme_close, c_p)
                pos.stop_price = min(pos.stop_price, pos.extreme_close + atr_mult * a20)
                ex_hi = ind[sym]["ex_hi"][t]
                if ex_hi is not None and c_p > ex_hi:
                    pending_exits.add(sym)

        for sym in S1_UNIVERSE:
            if not series[sym]["valid"][t]:
                continue
            # Bei Reversal darf derselbe Slot wieder besetzt werden, falls exited
            is_open_unchanged = (sym in positions) and (sym not in pending_exits)
            if is_open_unchanged:
                continue
            c_p = series[sym]["c"][t]
            d_hi = ind[sym]["d_hi"][t]
            d_lo = ind[sym]["d_lo"][t]
            a20 = ind[sym]["atr20"][t]
            if d_hi is None or d_lo is None or a20 is None or a20 <= 0:
                continue
            if c_p > d_hi:
                pending_entries.append(PendingOrder(sym, 1, 0.005 * equity, a20, (c_p - d_hi) / a20))
            elif c_p < d_lo and not (long_only_equities and S1_CLUSTERS[sym] == "EQUITY"):
                pending_entries.append(PendingOrder(sym, -1, 0.005 * equity, a20, (d_lo - c_p) / a20))

    # Offene Trades am Ende von end_date Mark-to-Market fuer Trade-Statistik abschliessen (P9)
    end_idx = data["date_to_idx"][end_date]
    for sym, pos in positions.items():
        c_p = series[sym]["c"][end_idx]
        raw_pnl = pos.direction * pos.shares * (c_p - pos.entry_price)
        entry_cost = abs(pos.shares) * pos.entry_price * half_cost
        trades.append({
            "symbol": sym,
            "direction": pos.direction,
            "entry_idx": pos.entry_idx,
            "entry_date": pos.entry_date,
            "exit_idx": end_idx,
            "exit_date": end_date,
            "r_mult": (raw_pnl - entry_cost) / pos.init_risk_dollar,
            "reason": "PHASE_END_MTM",
        })

    return {"excess_rets": excess_rets, "trades": trades}


def run_strategy2(
    data: Dict[str, Any],
    universe: List[str] = None,
    start_date: str = "2008-03-01",
    end_date: str = "2021-12-31",
    ibs_th: float = 0.20,
    rsi_th: float = 15.0,
    time_stop: int = 7,
    cost_bps: float = 10.0,
) -> Dict[str, Any]:
    """Strategie 2: Index Mean-Reversion (IBS + RSI(2)) gemaess Pre-Registration v1.2."""
    if universe is None:
        universe = S2_UNIVERSE
    dates = data["dates"]
    rf_daily = data["rf_daily"]
    series = data["series"]
    n_bars = len(dates)
    half_cost = (cost_bps / 10000.0) / 2.0

    ind: Dict[str, Dict[str, List[Optional[float]]]] = {}
    for sym in universe:
        s = series[sym]
        ind[sym] = {
            "sma200": sma(s["c"], 200),
            "rsi2": rsi_wilder(s["c"], 2),
            "atr14": atr_wilder(s["h"], s["l"], s["c"], 14),
        }

    equity = 100000.0
    positions: Dict[str, Position] = {}
    pending_exits: set = set()
    pending_entries: List[Tuple[float, float, str, float]] = []  # (rsi, ibs, sym, atr14)
    trades: List[Dict[str, Any]] = []
    excess_rets = [0.0] * n_bars

    for t in range(n_bars):
        d = dates[t]
        if d < start_date or d > end_date:
            continue

        eq_prev = equity
        prev_closes = {sym: series[sym]["c"][t - 1] for sym in positions}

        # 1. Ausstehende Exits zum Open(t)
        for sym in list(pending_exits):
            if sym in positions:
                pos = positions.pop(sym)
                fill = series[sym]["o"][t]
                raw_pnl = pos.shares * (fill - pos.entry_price)
                exit_cost = pos.shares * fill * half_cost
                mtm_prev = pos.shares * (prev_closes[sym] - pos.entry_price)
                equity += (raw_pnl - mtm_prev) - exit_cost
                total_cost = pos.shares * pos.entry_price * half_cost + exit_cost
                trades.append({
                    "symbol": sym,
                    "direction": 1,
                    "entry_idx": pos.entry_idx,
                    "entry_date": pos.entry_date,
                    "exit_idx": t,
                    "exit_date": d,
                    "r_mult": (raw_pnl - total_cost) / pos.init_risk_dollar,
                    "reason": "SIGNAL_OR_TIMESTOP",
                })
        pending_exits.clear()

        # 2. Ausstehende Entries zum Open(t) (aufsteigend nach RSI2, Tie-Breaker IBS)
        pending_entries.sort(key=lambda x: (x[0], x[1]))
        for _, _, sym, atr_sig in pending_entries:
            if sym in positions or len(positions) >= 3:
                continue
            if sym in S2_US_INDICES and any(p_sym in S2_US_INDICES for p_sym in positions):
                continue

            fill = series[sym]["o"][t]
            if fill <= 0 or atr_sig <= 0:
                continue
            stop_dist = 3.0 * atr_sig
            risk_dollar = 0.005 * equity
            shares = risk_dollar / stop_dist
            max_pos_notional = 0.33 * equity
            if shares * fill > max_pos_notional:
                shares = max_pos_notional / fill

            cur_gross = sum(p.shares * series[p.symbol]["o"][t] for p in positions.values())
            rem_cap = max(0.0, 1.0 * equity - cur_gross)
            if shares * fill > rem_cap:
                if rem_cap < 0.10 * (shares * fill):
                    continue
                shares = rem_cap / fill

            notional = shares * fill
            equity -= notional * half_cost
            positions[sym] = Position(
                symbol=sym,
                direction=1,
                shares=shares,
                entry_price=fill,
                entry_idx=t,
                entry_date=d,
                init_risk_dollar=shares * stop_dist,
                stop_price=fill - stop_dist,
                extreme_close=fill,
            )
            prev_closes[sym] = fill
        pending_entries.clear()

        # 3. Intraday-Katastrophen-Stop gegen [Open(t), Low(t)]
        for sym in list(positions.keys()):
            pos = positions[sym]
            o_p, l_p = series[sym]["o"][t], series[sym]["l"][t]
            if l_p <= pos.stop_price:
                positions.pop(sym)
                fill_stop = min(o_p, pos.stop_price)
                raw_pnl = pos.shares * (fill_stop - pos.entry_price)
                exit_cost = pos.shares * fill_stop * half_cost
                mtm_prev = pos.shares * (prev_closes[sym] - pos.entry_price)
                equity += (raw_pnl - mtm_prev) - exit_cost
                total_cost = pos.shares * pos.entry_price * half_cost + exit_cost
                trades.append({
                    "symbol": sym,
                    "direction": 1,
                    "entry_idx": pos.entry_idx,
                    "entry_date": pos.entry_date,
                    "exit_idx": t,
                    "exit_date": d,
                    "r_mult": (raw_pnl - total_cost) / pos.init_risk_dollar,
                    "reason": "CATASTROPHE_STOP",
                })

        # 4. Mark-to-Market + Cash-Verzinsung
        long_not = 0.0
        for sym, pos in positions.items():
            c_p = series[sym]["c"][t]
            equity += pos.shares * (c_p - prev_closes[sym])
            long_not += pos.shares * c_p
        equity += _apply_daily_financing(eq_prev, long_not, 0.0, rf_daily[t])
        excess_rets[t] = ((equity / eq_prev - 1.0) if eq_prev > 0 else 0.0) - rf_daily[t]

        # 5. Exit/Entry Signale am Close(t) fuer Open(t+1)
        if d == end_date or t + 1 >= n_bars or dates[t + 1] > end_date:
            continue

        for sym, pos in positions.items():
            days_held = (t - pos.entry_idx) + 1  # Einstiegstag = Tag 1; Close(Tag 7) -> Open(Tag 8)
            c_p = series[sym]["c"][t]
            prev_h = series[sym]["h"][t - 1]
            if c_p > prev_h or days_held >= time_stop:
                pending_exits.add(sym)

        for sym in universe:
            if sym in positions or not series[sym]["valid"][t]:
                continue
            c_p = series[sym]["c"][t]
            h_p = series[sym]["h"][t]
            l_p = series[sym]["l"][t]
            sm = ind[sym]["sma200"][t]
            r2 = ind[sym]["rsi2"][t]
            a14 = ind[sym]["atr14"][t]
            ib = ibs(h_p, l_p, c_p)
            if sm is None or r2 is None or a14 is None or ib is None:
                continue
            if c_p > sm and ib < ibs_th and r2 < rsi_th:
                pending_entries.append((r2, ib, sym, a14))

    end_idx = data["date_to_idx"][end_date]
    for sym, pos in positions.items():
        c_p = series[sym]["c"][end_idx]
        raw_pnl = pos.shares * (c_p - pos.entry_price)
        entry_cost = pos.shares * pos.entry_price * half_cost
        trades.append({
            "symbol": sym,
            "direction": 1,
            "entry_idx": pos.entry_idx,
            "entry_date": pos.entry_date,
            "exit_idx": end_idx,
            "exit_date": end_date,
            "r_mult": (raw_pnl - entry_cost) / pos.init_risk_dollar,
            "reason": "PHASE_END_MTM",
        })

    return {"excess_rets": excess_rets, "trades": trades}


def run_benchmark_risk_parity_lo(
    data: Dict[str, Any],
    universe: List[str] = None,
    start_date: str = "2008-03-01",
    end_date: str = "2021-12-31",
    cost_bps: float = 10.0,
) -> List[float]:
    """Statischer Benchmark 1: 1/sigma_60 Risk-Parity Long-Only, monatlich rebalanced."""
    if universe is None:
        universe = S1_UNIVERSE
    dates, rf_daily, series = data["dates"], data["rf_daily"], data["series"]
    n_bars = len(dates)
    vols = {sym: rolling_vol_annualized(series[sym]["c"], 60) for sym in universe}
    half_cost = (cost_bps / 10000.0) / 2.0

    weights = {sym: 0.0 for sym in universe}
    pending_weights: Optional[Dict[str, float]] = None
    excess_rets = [0.0] * n_bars

    for t in range(n_bars):
        d = dates[t]
        if d < start_date or d > end_date:
            continue

        turnover_cost = 0.0
        if pending_weights is not None:
            turnover = sum(abs(pending_weights[s] - weights[s]) for s in universe)
            turnover_cost = turnover * half_cost
            weights = pending_weights
            pending_weights = None

        port_ret = -turnover_cost
        for s in universe:
            if weights[s] > 0:
                c0, c1 = series[s]["c"][t - 1], series[s]["c"][t]
                if c0 > 0:
                    port_ret += weights[s] * (c1 / c0 - 1.0)
        cash_w = max(0.0, 1.0 - sum(weights.values()))
        port_ret += cash_w * rf_daily[t]
        excess_rets[t] = port_ret - rf_daily[t]

        # Monatsende (oder erster Tag): Zielgewichte am Close(t) fuer Open(t+1) berechnen
        is_month_end = (t + 1 < n_bars) and (dates[t + 1][:7] != d[:7])
        if (sum(weights.values()) == 0.0) or is_month_end:
            inv_v = {}
            for s in universe:
                v = vols[s][t]
                if v is not None and v > 1e-6:
                    inv_v[s] = 1.0 / v
            tot = sum(inv_v.values())
            if tot > 0:
                pending_weights = {s: inv_v.get(s, 0.0) / tot for s in universe}

    return excess_rets


def run_benchmark_sma200_hold(
    data: Dict[str, Any],
    universe: List[str] = None,
    start_date: str = "2008-03-01",
    end_date: str = "2021-12-31",
    cost_bps: float = 10.0,
) -> List[float]:
    """Strategie-2-Benchmark: je 20% (1/5) in jeden ETF mit Close(t) > SMA200(t), Rest T-Bill."""
    if universe is None:
        universe = S2_UNIVERSE
    dates, rf_daily, series = data["dates"], data["rf_daily"], data["series"]
    n_bars = len(dates)
    smas = {sym: sma(series[sym]["c"], 200) for sym in universe}
    half_cost = (cost_bps / 10000.0) / 2.0

    weights = {sym: 0.0 for sym in universe}
    pending_weights: Optional[Dict[str, float]] = None
    excess_rets = [0.0] * n_bars

    for t in range(n_bars):
        d = dates[t]
        if d < start_date or d > end_date:
            continue

        turnover_cost = 0.0
        if pending_weights is not None:
            turnover = sum(abs(pending_weights[s] - weights[s]) for s in universe)
            turnover_cost = turnover * half_cost
            weights = pending_weights
            pending_weights = None

        port_ret = -turnover_cost
        for s in universe:
            if weights[s] > 0:
                c0, c1 = series[s]["c"][t - 1], series[s]["c"][t]
                if c0 > 0:
                    port_ret += weights[s] * (c1 / c0 - 1.0)
        cash_w = max(0.0, 1.0 - sum(weights.values()))
        port_ret += cash_w * rf_daily[t]
        excess_rets[t] = port_ret - rf_daily[t]

        # Signal am Close(t) -> Rebalancing am naechsten Tag
        pending_weights = {}
        for s in universe:
            sm = smas[s][t]
            pending_weights[s] = (1.0 / len(universe)) if (sm is not None and series[s]["c"][t] > sm) else 0.0

    return excess_rets


def stationary_bootstrap_sharpe_p(
    excess_rets: List[float],
    mean_block: float = 20.0,
    n_boot: int = 5000,
    seed: int = 42,
) -> float:
    """Einseitiger Stationary Bootstrap p-Wert fuer H0: Excess-Sharpe <= 0."""
    n = len(excess_rets)
    if n < 20:
        return 1.0
    rng = random.Random(seed)
    p_jump = 1.0 / mean_block
    # Zentriere Renditen unter H0: mean = 0
    mean_orig = sum(excess_rets) / n
    centered = [x - mean_orig for x in excess_rets]
    var_orig = sum(x * x for x in centered) / (n - 1)
    sr_orig = (mean_orig / math.sqrt(var_orig)) if var_orig > 0 else 0.0

    ge_count = 0
    for _ in range(n_boot):
        idx = rng.randrange(n)
        s = 0.0
        s2 = 0.0
        for _ in range(n):
            val = centered[idx]
            s += val
            s2 += val * val
            if rng.random() < p_jump:
                idx = rng.randrange(n)
            else:
                idx = (idx + 1) % n
        m = s / n
        v = max(1e-18, (s2 - n * m * m) / (n - 1))
        if (m / math.sqrt(v)) >= sr_orig:
            ge_count += 1
    return round(ge_count / n_boot, 4)


def ols_alpha_vs_benchmark(strat_ex: List[float], bench_ex: List[float]) -> Dict[str, float]:
    """OLS-Regression strat_ex = alpha + beta * bench_ex; liefert annualisiertes Alpha & p-Wert."""
    n = len(strat_ex)
    if n < 20:
        return {"alpha_ann_pct": 0.0, "beta": 0.0, "t_stat": 0.0, "p_value": 1.0}
    mx = sum(bench_ex) / n
    my = sum(strat_ex) / n
    sxx = sum((x - mx) ** 2 for x in bench_ex)
    sxy = sum((x - mx) * (y - my) for x, y in zip(bench_ex, strat_ex))
    beta = (sxy / sxx) if sxx > 1e-18 else 0.0
    alpha = my - beta * mx
    resid = [y - (alpha + beta * x) for x, y in zip(bench_ex, strat_ex)]
    s2 = sum(r * r for r in resid) / (n - 2)
    se_alpha = math.sqrt(s2 * (1.0 / n + (mx * mx) / sxx)) if sxx > 1e-18 else 1e9
    t_stat = (alpha / se_alpha) if se_alpha > 0 else 0.0
    p_val = 0.5 * math.erfc(t_stat / math.sqrt(2.0))
    return {
        "alpha_ann_pct": round(alpha * 252.0 * 100.0, 2),
        "beta": round(beta, 3),
        "t_stat": round(t_stat, 2),
        "p_value": round(p_val, 5),
    }
