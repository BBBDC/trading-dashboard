#!/usr/bin/env python3
"""
robustness_engine.py
====================
Institutionelle Robustness- & Monte-Carlo Stresstest Suite (Hebel 4).
Entwickelt für das autonome Trading-System auf dem Raspberry Pi.

Kern-Komponenten:
1. Monte-Carlo Permutation, i.i.d.-Bootstrap, Block-Bootstrap und Bootstrap mit
   aktivem Circuit-Breaker (je 1.000 Pfade)
   - Verteilung des maximalen Drawdowns (P10 bis P99) und des End-PnL
   - Auslöse-Wahrscheinlichkeiten für Drosselung (-10R) und Vollstopp (-15R)
   - E(R) mit Standardfehler, t-Statistik und 95%-Konfidenzintervall
2. Cluster- & Systemischer Schock-Stresstest
   - Gap-Verluste aus den echten Stop-Abständen der aktiven Positionen
     (Verlust in R = Gap / Stop-Abstand, nicht pauschal 1.25-1.5R)
   - Bezug auf das aktuelle Eigenkapital, abgestufte Insolvenz-Einstufung
   - Empirischer Verlust-Tail und Prüfung der Heat-Limits
3. Parameter-Sensitivität & Anti-Overfitting Audit
   - Stresstestet die Edge gegen progressive Reibung & Slippage
   - Berechnet Break-Even Friction Point und institutionalen Robustness-Score
4. Regelbasiertes Live-Readiness-Urteil (GO / GO_WITH_CONDITIONS / NO_GO)
"""

import os
import sys
import json
import math
import random
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
PORTFOLIO_FILE = BASE_DIR / "knowledge_base" / "autonomous_portfolio.json"
INCUBATOR_FILE = BASE_DIR / "knowledge_base" / "incubator_trades.json"
REPORT_OUTPUT_FILE = BASE_DIR / "knowledge_base" / "robustness_report.json"

from circuit_breaker import (
    classify_asset_cluster,
    CircuitBreakerConfig,
    DEFAULT_CONFIG,
    _trade_exit_time,
    _trade_r
)


# ==============================================================================
# 0. GEMEINSAME STATISTIK-HELFER
# ==============================================================================

def _extract_r_values(trades: List[Dict[str, Any]], chronological: bool = False) -> List[float]:
    """R-Ergebnisse der Trades; optional chronologisch nach Exit-Zeit sortiert."""
    rows: List[Tuple[float, int, float]] = []
    for i, t in enumerate(trades):
        r = _trade_r(t)
        if r is None:
            r = round(float(t.get("realized_pnl_pct", 0.0) or 0.0) / 2.0, 2)
        ts = _trade_exit_time(t) if chronological else None
        rows.append((ts.timestamp() if ts else float("-inf"), i, float(r)))
    if chronological:
        rows.sort(key=lambda x: (x[0], x[1]))
    return [r for _, _, r in rows]


def _percentile(sorted_list: List[float], p: float) -> float:
    """Perzentil mit linearer Interpolation (Hyndman-Fan Typ 7, wie numpy-Default)."""
    if not sorted_list:
        return 0.0
    pos = min(max(p, 0.0), 1.0) * (len(sorted_list) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_list) - 1)
    return round(sorted_list[lo] + (sorted_list[hi] - sorted_list[lo]) * (pos - lo), 2)


def _max_drawdown(path: List[float]) -> float:
    cum = peak = max_dd = 0.0
    for r in path:
        cum += r
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    return max_dd


def _governed_path(path: List[float], reduce_r: float, halt_r: float) -> Tuple[float, float, int, bool]:
    """
    Wendet den Drawdown-Circuit-Breaker auf einen Pfad an: ab -reduce_r halbes Sizing,
    ab -halt_r Vollstopp. Rückgabe: (End-PnL, Max-DD, ausgeführte Trades, gestoppt?).
    """
    cum = peak = max_dd = 0.0
    taken = 0
    for r in path:
        dd = peak - cum
        if dd >= halt_r:
            return cum, max_dd, taken, True
        cum += r * (0.5 if dd >= reduce_r else 1.0)
        taken += 1
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    return cum, max_dd, taken, (peak - cum) >= halt_r


def _normal_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


# ==============================================================================
# 1. MONTE-CARLO PERMUTATION & BOOTSTRAP ENGINE
# ==============================================================================

def run_monte_carlo_permutation(
    trades: List[Dict[str, Any]],
    n_simulations: int = 1000,
    seed: int = 42,
    reduce_r: float = DEFAULT_CONFIG.drawdown_reduce_r,
    halt_r: float = DEFAULT_CONFIG.drawdown_halt_r
) -> Dict[str, Any]:
    """
    Permutation (ohne Zurücklegen), i.i.d.-Bootstrap, Block-Bootstrap (serielle Abhängigkeit)
    und Bootstrap unter aktivem Circuit-Breaker auf den realisierten R-Ergebnissen.
    """
    rng = random.Random(seed)
    r_values = _extract_r_values(trades, chronological=True)

    n_trades = len(r_values)
    if n_trades == 0:
        return {"error": "Keine Trades für Monte-Carlo Simulation vorhanden."}

    # --- Stichprobenstatistik (ungerundeter Mittelwert, Stichprobenvarianz n-1) ---
    total_r = sum(r_values)
    mean_r = total_r / n_trades
    var_r = sum((x - mean_r) ** 2 for x in r_values) / (n_trades - 1) if n_trades > 1 else 0.0
    std_r = math.sqrt(var_r)
    downside_std = math.sqrt(sum(min(0.0, x) ** 2 for x in r_values) / n_trades)
    se_mean = std_r / math.sqrt(n_trades) if n_trades > 1 else 0.0
    t_stat = mean_r / se_mean if se_mean > 0 else 0.0
    # Einseitiger p-Wert für H0: E(R) <= 0 (Normal-Approximation; bei n >= 30 vertretbar)
    p_edge_le_zero = 1.0 - _normal_cdf(t_stat) if se_mean > 0 else (0.0 if mean_r > 0 else 1.0)

    wins = [x for x in r_values if x > 0]
    losses = [x for x in r_values if x < 0]
    gross_win, gross_loss = sum(wins), -sum(losses)
    avg_win = gross_win / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0
    breakeven_wr = avg_loss / (avg_win + avg_loss) * 100.0 if (avg_win + avg_loss) > 0 else 0.0
    worst = min(r_values)
    mean_ex_worst = (total_r - worst) / (n_trades - 1) if n_trades > 1 else mean_r
    lag1 = 0.0
    if n_trades > 2 and var_r > 0:
        lag1 = sum((a - mean_r) * (b - mean_r) for a, b in zip(r_values, r_values[1:])) / (var_r * (n_trades - 1))

    # A) Permutation (Reihenfolge-Risiko; Endergebnis ist auf jedem Pfad identisch)
    perm_max_dds: List[float] = []
    for _ in range(n_simulations):
        shuffled = list(r_values)
        rng.shuffle(shuffled)
        perm_max_dds.append(_max_drawdown(shuffled))
    perm_max_dds.sort()

    # B) i.i.d.-Bootstrap + derselbe Pfad unter aktivem Circuit-Breaker
    boot_max_dds: List[float] = []
    boot_final: List[float] = []
    gov_final: List[float] = []
    gov_max_dds: List[float] = []
    gov_trades_to_halt: List[int] = []
    gov_halts = 0
    for _ in range(n_simulations):
        path = [rng.choice(r_values) for _ in range(n_trades)]
        boot_final.append(sum(path))
        boot_max_dds.append(_max_drawdown(path))
        g_final, g_dd, g_taken, g_halted = _governed_path(path, reduce_r, halt_r)
        gov_final.append(g_final)
        gov_max_dds.append(g_dd)
        if g_halted:
            gov_halts += 1
            gov_trades_to_halt.append(g_taken)
    boot_max_dds.sort(); boot_final.sort(); gov_final.sort(); gov_max_dds.sort(); gov_trades_to_halt.sort()

    # C) Zirkulärer Block-Bootstrap (erhält Verlust-Cluster / serielle Korrelation)
    block_len = max(2, int(round(n_trades ** (1.0 / 3.0))))
    rng_block = random.Random(seed + 1)
    block_max_dds: List[float] = []
    block_final: List[float] = []
    for _ in range(n_simulations):
        path: List[float] = []
        while len(path) < n_trades:
            start = rng_block.randrange(n_trades)
            path.extend(r_values[(start + k) % n_trades] for k in range(block_len))
        path = path[:n_trades]
        block_final.append(sum(path))
        block_max_dds.append(_max_drawdown(path))
    block_max_dds.sort(); block_final.sort()

    def dd_block(sorted_dds: List[float]) -> Dict[str, float]:
        return {
            "P10": _percentile(sorted_dds, 0.10),
            "P25": _percentile(sorted_dds, 0.25),
            "P50_median": _percentile(sorted_dds, 0.50),
            "P75": _percentile(sorted_dds, 0.75),
            "P90": _percentile(sorted_dds, 0.90),
            "P95": _percentile(sorted_dds, 0.95),
            "P99": _percentile(sorted_dds, 0.99)
        }

    def pnl_block(sorted_pnl: List[float]) -> Dict[str, float]:
        return {
            "P01": _percentile(sorted_pnl, 0.01),
            "P05": _percentile(sorted_pnl, 0.05),
            "P25": _percentile(sorted_pnl, 0.25),
            "P50_median": _percentile(sorted_pnl, 0.50),
            "P75": _percentile(sorted_pnl, 0.75),
            "P95": _percentile(sorted_pnl, 0.95),
            "P99": _percentile(sorted_pnl, 0.99)
        }

    def prob(values: List[float], threshold: float) -> float:
        return round(sum(1 for v in values if v >= threshold) / n_simulations * 100.0, 1)

    dd_floor = round(max(0.0, -total_r), 2)

    return {
        "trades_evaluated": n_trades,
        "simulations_count": n_simulations,
        "sample_statistics": {
            "total_r": round(total_r, 2),
            "mean_r_per_trade": round(mean_r, 4),
            "std_r": round(std_r, 4),
            "downside_std_r": round(downside_std, 4),
            "sharpe_ratio_r": round(mean_r / std_r, 3) if std_r > 0 else 0.0,
            "sortino_ratio_r": round(mean_r / downside_std, 3) if downside_std > 0 else 0.0,
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate_pct": round(len(wins) / n_trades * 100.0, 1),
            "breakeven_win_rate_pct": round(breakeven_wr, 1),
            "avg_win_r": round(avg_win, 3),
            "avg_loss_r": round(-avg_loss, 3),
            "profit_factor": round(gross_win / gross_loss, 3) if gross_loss > 0 else None,
            "std_error_mean_r": round(se_mean, 4),
            "t_statistic": round(t_stat, 2),
            "mean_r_ci95": [round(mean_r - 1.96 * se_mean, 4), round(mean_r + 1.96 * se_mean, 4)],
            "p_value_true_edge_positive": round(p_edge_le_zero, 5),
            "edge_significance": (
                "SIGNIFIKANT_NEGATIV" if mean_r + 1.96 * se_mean < 0 else
                "SIGNIFIKANT_POSITIV" if mean_r - 1.96 * se_mean > 0 else
                "NICHT_SIGNIFIKANT"
            ),
            "worst_trade_r": round(worst, 2),
            "mean_r_ex_worst_trade": round(mean_ex_worst, 4),
            "losses_worse_than_1_5r": sum(1 for x in r_values if x < -1.5),
            "lag1_autocorrelation": round(lag1, 3),
            "historical_max_drawdown_r": round(_max_drawdown(r_values), 2)
        },
        "permutation_test": {
            "description": "Zufällige Permutation der Trade-Reihenfolge (Original-Sample)",
            "note": (
                "Das Endergebnis ist auf jedem Permutationspfad identisch; der Max-DD hat daher die "
                f"harte Untergrenze max(0, -Summe R) = {dd_floor}R. Bei negativer Summe misst dieser Test "
                "nur Reihenfolge-Streuung oberhalb des Gesamtverlusts, kein Überlebensrisiko."
            ),
            "max_dd_lower_bound_r": dd_floor,
            "prob_dd_ge_10r_pct": prob(perm_max_dds, reduce_r),
            "prob_dd_ge_15r_pct": prob(perm_max_dds, halt_r),
            "percentiles_max_dd_r": dd_block(perm_max_dds)
        },
        "bootstrap_test": {
            "description": "Resampling mit Zurücklegen (Synthetische Marktpfade, i.i.d.)",
            "prob_dd_ge_10r_pct": prob(boot_max_dds, reduce_r),
            "prob_dd_ge_15r_pct": prob(boot_max_dds, halt_r),
            "prob_profitable_path_pct": round(sum(1 for x in boot_final if x > 0) / n_simulations * 100.0, 1),
            "percentiles_max_dd_r": dd_block(boot_max_dds),
            "percentiles_final_pnl_r": pnl_block(boot_final)
        },
        "block_bootstrap_test": {
            "description": "Zirkulärer Block-Bootstrap (erhält serielle Abhängigkeit / Verlust-Cluster)",
            "block_length": block_len,
            "prob_dd_ge_10r_pct": prob(block_max_dds, reduce_r),
            "prob_dd_ge_15r_pct": prob(block_max_dds, halt_r),
            "prob_profitable_path_pct": round(sum(1 for x in block_final if x > 0) / n_simulations * 100.0, 1),
            "percentiles_max_dd_r": dd_block(block_max_dds),
            "percentiles_final_pnl_r": pnl_block(block_final)
        },
        "governed_bootstrap_test": {
            "description": (
                f"i.i.d.-Bootstrap mit aktivem Circuit-Breaker (ab -{reduce_r:g}R halbes Sizing, "
                f"ab -{halt_r:g}R Vollstopp). Zeigt Verlustbegrenzung, nicht Profitabilität."
            ),
            "prob_full_halt_pct": round(gov_halts / n_simulations * 100.0, 1),
            "median_trades_until_halt": (
                gov_trades_to_halt[len(gov_trades_to_halt) // 2] if gov_trades_to_halt else None
            ),
            "prob_profitable_path_pct": round(sum(1 for x in gov_final if x > 0) / n_simulations * 100.0, 1),
            "percentiles_max_dd_r": dd_block(gov_max_dds),
            "percentiles_final_pnl_r": pnl_block(gov_final)
        }
    }


# ==============================================================================
# 2. CLUSTER- & SYSTEMISCHER SCHOCK-STRESSTEST
# ==============================================================================

# Adverse Gap-Annahmen je Cluster (Anteil des Kurses) für den systemischen Schock
SHOCK_GAP_BY_CLUSTER: Dict[str, float] = {
    "CRYPTO": 0.25,
    "US_EQUITIES": 0.07,
    "EU_EQUITIES": 0.07,
    "COMMODITIES": 0.05,
    "FOREX": 0.02,
}
DEFAULT_SHOCK_GAP = 0.07


def _f(value: Any) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _position_profile(t: Dict[str, Any], default_risk_cash: float) -> Dict[str, Any]:
    """Liest Stop-Abstand, offenes Risiko und Nominal einer aktiven Position."""
    entry = _f(t.get("entry_price"))
    cur = _f(t.get("current_price")) or entry
    init_stop = _f(t.get("initial_stop_loss")) or _f(t.get("stop_loss")) or _f(t.get("sl"))
    stop = _f(t.get("stop_loss")) or _f(t.get("sl")) or init_stop
    is_long = str(t.get("direction", "LONG")).upper() != "SHORT"
    r_dist = abs(entry - init_stop) if entry and init_stop else None
    if r_dist is not None and r_dist <= 0:
        r_dist = None

    open_risk_r = 1.0
    if r_dist and entry and stop:
        open_risk_r = max(0.0, ((entry - stop) if is_long else (stop - entry)) / r_dist)

    risk_cash = _f(t.get("risk_cash")) or default_risk_cash
    alloc = _f(t.get("allocated_capital"))
    lev = _f(t.get("leverage")) or 1.0
    return {
        "symbol": t.get("symbol", ""),
        "cluster": classify_asset_cluster(t.get("symbol", ""), t.get("category", "")),
        "is_long": is_long,
        "current_price": cur,
        "r_distance": r_dist,
        "stop_distance_pct": round(r_dist / entry * 100.0, 2) if r_dist and entry else None,
        "open_risk_r": round(open_risk_r, 2),
        "risk_cash": risk_cash,
        "notional_eur": alloc * lev if alloc else None,
    }


def _gap_scenario(
    profiles: List[Dict[str, Any]],
    gaps: Dict[str, float],
    mode: str,
    fallback_r_multiple: float
) -> Dict[str, Any]:
    """
    mode='down'    : Markt gappt nach unten -> nur Long-Positionen verlieren; Shorts erhalten
                     konservativ KEINE Gutschrift.
    mode='adverse' : Gap läuft gegen jede Position (Korrelation -> 1, Whipsaw/Short-Squeeze).
    Verlust in R = Gap * Kurs / initialer Stop-Abstand (Mark-to-Market ab aktuellem Kurs);
    ein Gap überspringt den Stop, der Verlust ist NICHT auf ~1R gedeckelt.
    """
    loss_r = loss_eur_r = loss_eur_notional = naive_r = 0.0
    affected = 0
    unaffected_shorts = 0
    notional_known = True
    details = []
    for p in profiles:
        gap = gaps.get(p["cluster"])
        if gap is None:
            continue
        if mode == "down" and not p["is_long"]:
            unaffected_shorts += 1
            continue
        affected += 1
        naive_r += fallback_r_multiple
        if p["r_distance"] and p["current_price"]:
            pos_r = gap * p["current_price"] / p["r_distance"]
        else:
            pos_r = fallback_r_multiple
        loss_r += pos_r
        loss_eur_r += pos_r * p["risk_cash"]
        if p["notional_eur"] is not None:
            loss_eur_notional += gap * p["notional_eur"]
        else:
            notional_known = False
        details.append({
            "symbol": p["symbol"], "cluster": p["cluster"],
            "direction": "LONG" if p["is_long"] else "SHORT",
            "gap_pct": round(gap * 100.0, 1), "stop_distance_pct": p["stop_distance_pct"],
            "loss_r": round(pos_r, 2)
        })
    return {
        "affected_positions": affected,
        "shorts_without_credit": unaffected_shorts,
        "loss_r": round(loss_r, 2),
        "loss_eur": round(loss_eur_r, 2),
        "loss_eur_declared_notional": round(loss_eur_notional, 2) if (affected and notional_known) else None,
        "naive_flat_slippage_loss_r": round(naive_r, 2),
        "positions": details
    }


def _grade_insolvency(loss_pct_of_equity: float) -> str:
    """Abgestufte Einstufung. 'ZERO' existiert bewusst nicht: Gap-Risiko ist nie null."""
    if loss_pct_of_equity >= 100.0:
        return "INSOLVENT"
    if loss_pct_of_equity >= 50.0:
        return "SEVERE"
    if loss_pct_of_equity >= 25.0:
        return "HIGH"
    if loss_pct_of_equity >= 10.0:
        return "MODERATE"
    return "LOW"


def run_cluster_stress_test(
    active_trades: List[Dict[str, Any]],
    total_capital: float = 10000.0,
    closed_trades: Optional[List[Dict[str, Any]]] = None,
    config: CircuitBreakerConfig = DEFAULT_CONFIG
) -> Dict[str, Any]:
    """
    Schock-Stresstest auf Basis der ECHTEN Stop-Abstände der aktiven Positionen:
    1. CRYPTO_FLASH_CRASH : -25% Gap auf Krypto
    2. EQUITY_FLASH_CRASH : -7% Gap auf US- und EU-Aktien
    3. SYSTEMIC_BLACK_SWAN: adverser Gap gegen jede Position (Cluster-spezifische Gap-Größe)
    4. EMPIRICAL_TAIL     : jede Position realisiert den historisch beobachteten Verlust-Tail

    EUR-Verluste in zwei Lesarten: (a) R-Buchhaltung (R * risk_cash) und
    (b) deklariertes Nominal (allocated_capital * leverage * Gap).
    Bezugsgröße ist das aktuelle Eigenkapital (Startkapital + realisierte PnL), nicht das Startkapital.
    """
    default_risk_cash = total_capital * config.flat_risk_pct / 100.0
    profiles = [_position_profile(t, default_risk_cash) for t in active_trades]
    total_active = len(profiles)

    realized_cash = 0.0
    hist_r: List[float] = []
    if closed_trades:
        hist_r = _extract_r_values(closed_trades)
        for t, r in zip(closed_trades, hist_r):
            cash = _f(t.get("realized_pnl_cash"))
            realized_cash += cash if cash is not None else r * (_f(t.get("risk_cash")) or default_risk_cash)
    current_equity = total_capital + realized_cash
    equity_base = max(current_equity, 1e-9)

    def pct(eur: Optional[float]) -> Optional[float]:
        return round(eur / equity_base * 100.0, 2) if eur is not None else None

    # Offenes Risiko (Heat) gegen die Limits prüfen
    heat_by_cluster: Dict[str, float] = {}
    count_by_cluster: Dict[str, int] = {}
    for p in profiles:
        heat_by_cluster[p["cluster"]] = round(heat_by_cluster.get(p["cluster"], 0.0) + p["open_risk_r"], 2)
        count_by_cluster[p["cluster"]] = count_by_cluster.get(p["cluster"], 0) + 1
    total_heat = round(sum(heat_by_cluster.values()), 2)
    cluster_breaches = {c: h for c, h in heat_by_cluster.items() if h > config.max_cluster_heat_r + 1e-9}
    gross_notional = sum(p["notional_eur"] or 0.0 for p in profiles)

    crypto = _gap_scenario(profiles, {"CRYPTO": 0.25}, "down", 1.25)
    equity = _gap_scenario(profiles, {"US_EQUITIES": 0.07, "EU_EQUITIES": 0.07}, "down", 1.30)
    all_gaps = {p["cluster"]: SHOCK_GAP_BY_CLUSTER.get(p["cluster"], DEFAULT_SHOCK_GAP) for p in profiles}
    swan = _gap_scenario(profiles, all_gaps, "adverse", 1.50)

    swan_worst_eur = max(swan["loss_eur"], swan["loss_eur_declared_notional"] or 0.0)
    swan_dd_pct = pct(swan_worst_eur) or 0.0

    # Empirischer Tail: historische Verlustverteilung statt angenommener Slippage-Multiplikatoren
    empirical: Dict[str, Any] = {"available": False}
    hist_losses = sorted(-r for r in hist_r if r < 0)
    if hist_losses and total_active:
        p95, worst = _percentile(hist_losses, 0.95), hist_losses[-1]
        avg_risk_cash = sum(p["risk_cash"] for p in profiles) / total_active
        empirical = {
            "available": True,
            "description": "Alle aktiven Positionen realisieren gleichzeitig den historisch beobachteten Verlust-Tail",
            "historical_loss_p50_r": _percentile(hist_losses, 0.50),
            "historical_loss_p95_r": p95,
            "historical_worst_loss_r": round(worst, 2),
            "share_losses_beyond_1_5r_pct": round(sum(1 for x in hist_losses if x > 1.5) / len(hist_losses) * 100.0, 1),
            "all_positions_at_p95_loss_r": round(total_active * p95, 2),
            "all_positions_at_p95_loss_pct_of_equity": pct(total_active * p95 * avg_risk_cash),
            "all_positions_at_worst_loss_r": round(total_active * worst, 2),
            "all_positions_at_worst_loss_pct_of_equity": pct(total_active * worst * avg_risk_cash)
        }

    return {
        "active_positions_count": total_active,
        "clusters_detected": count_by_cluster,
        "equity": {
            "initial_capital_eur": round(total_capital, 2),
            "realized_pnl_eur": round(realized_cash, 2),
            "current_equity_eur": round(current_equity, 2),
            "realized_drawdown_pct_of_initial": round(-realized_cash / total_capital * 100.0, 2) if total_capital else None,
            "gross_declared_notional_eur": round(gross_notional, 2),
            "gross_leverage_on_current_equity": round(gross_notional / equity_base, 2)
        },
        "open_risk": {
            "total_heat_r": total_heat,
            "max_total_heat_r": config.max_total_heat_r,
            "total_heat_breached": total_heat > config.max_total_heat_r + 1e-9,
            "heat_by_cluster_r": heat_by_cluster,
            "max_cluster_heat_r": config.max_cluster_heat_r,
            "cluster_breaches": cluster_breaches
        },
        "scenarios": {
            "CRYPTO_FLASH_CRASH": {
                "description": "Krypto gappt -25%; Verlust je Long = Gap / Stop-Abstand (Shorts ohne Gutschrift)",
                "affected_positions": crypto["affected_positions"],
                "shorts_without_credit": crypto["shorts_without_credit"],
                "portfolio_loss_r": crypto["loss_r"],
                "portfolio_loss_eur": crypto["loss_eur"],
                "portfolio_loss_eur_declared_notional": crypto["loss_eur_declared_notional"],
                "loss_pct_of_equity": pct(crypto["loss_eur"]),
                "naive_flat_slippage_loss_r": crypto["naive_flat_slippage_loss_r"],
                "cluster_cap_protected": crypto["loss_r"] <= config.max_cluster_heat_r,
                "evaluation": (
                    "Kein Long-Krypto-Exposure betroffen" if crypto["affected_positions"] == 0 else
                    "Innerhalb des Cluster-Budgets" if crypto["loss_r"] <= config.max_cluster_heat_r else
                    f"Warnung: Gap-Verlust übersteigt Cluster-Budget ({config.max_cluster_heat_r}R)"
                ),
                "positions": crypto["positions"]
            },
            "EQUITY_FLASH_CRASH": {
                "description": "US-/EU-Aktien gappen -7%; Verlust je Long = Gap / Stop-Abstand (Shorts ohne Gutschrift)",
                "affected_positions": equity["affected_positions"],
                "shorts_without_credit": equity["shorts_without_credit"],
                "portfolio_loss_r": equity["loss_r"],
                "portfolio_loss_eur": equity["loss_eur"],
                "portfolio_loss_eur_declared_notional": equity["loss_eur_declared_notional"],
                "loss_pct_of_equity": pct(equity["loss_eur"]),
                "naive_flat_slippage_loss_r": equity["naive_flat_slippage_loss_r"],
                "cluster_cap_protected": equity["loss_r"] <= 2 * config.max_cluster_heat_r,
                "positions": equity["positions"]
            },
            "SYSTEMIC_BLACK_SWAN": {
                "description": (
                    "Globaler Schock: adverser Gap gegen JEDE Position (Krypto 25%, Aktien 7%, "
                    "Rohstoffe 5%, FX 2%); Stops werden übersprungen"
                ),
                "affected_positions": swan["affected_positions"],
                "total_loss_r": swan["loss_r"],
                "total_loss_eur": swan["loss_eur"],
                "total_loss_eur_declared_notional": swan["loss_eur_declared_notional"],
                "total_account_drawdown_pct": swan_dd_pct,
                "drawdown_pct_r_accounting": pct(swan["loss_eur"]),
                "drawdown_pct_declared_notional": pct(swan["loss_eur_declared_notional"]),
                "naive_flat_slippage_loss_r": swan["naive_flat_slippage_loss_r"],
                "exceeds_halt_limit_in_one_event": swan["loss_r"] >= config.drawdown_halt_r,
                "insolvency_risk": _grade_insolvency(swan_dd_pct),
                "protective_verdict": (
                    f"Schock-Verlust {swan['loss_r']:.1f}R = {swan_dd_pct}% des aktuellen Eigenkapitals "
                    f"(ungünstigere der beiden EUR-Lesarten). Die frühere Annahme 'max. 1.5R je Position' "
                    f"ergäbe nur {swan['naive_flat_slippage_loss_r']:.1f}R und ist bei Gaps nicht haltbar."
                ),
                "positions": swan["positions"]
            },
            "EMPIRICAL_TAIL": empirical
        }
    }


# ==============================================================================
# 3. PARAMETER-SENSITIVITÄT & ANTI-OVERFITTING AUDIT
# ==============================================================================

def run_parameter_sensitivity_test(
    trades: List[Dict[str, Any]],
    friction_penalties: Optional[List[float]] = None
) -> Dict[str, Any]:
    """
    Testet die Robustheit der Setups gegen systematische Verschlechterung (Edge Degradation).
    Zieht schrittweise zusätzliche Reibung (Slippage/Gebühren) von +0.02R bis +0.25R ab.
    Berechnet den Break-Even Friction Point und den institutionalen Robustness Score.
    """
    if friction_penalties is None:
        friction_penalties = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25]

    r_values = _extract_r_values(trades)

    n_trades = len(r_values)
    if n_trades == 0:
        return {"error": "Keine Trades vorhanden"}

    baseline_total_r = sum(r_values)
    baseline_mean_r = baseline_total_r / n_trades

    degradation_curve = []
    break_even_friction = None

    for pen in friction_penalties:
        pen_r = [x - pen for x in r_values]
        tot_r = round(sum(pen_r), 2)
        mean_r = round(sum(pen_r) / n_trades, 4)
        wins = sum(1 for x in pen_r if x > 0)
        wr = round(wins / n_trades * 100.0, 1)

        degradation_curve.append({
            "additional_friction_r": pen,
            "total_pnl_r": tot_r,
            "mean_r_per_trade": mean_r,
            "win_rate_pct": wr,
            "is_profitable": tot_r > 0
        })

    # Reibung wirkt linear pro Trade -> der Break-Even-Punkt ist exakt der Baseline-Mittelwert
    # (nicht der nächste Rasterpunkt). Bei negativer Baseline existiert kein Puffer.
    break_even_friction = round(max(0.0, baseline_mean_r), 4)
    required_improvement = round(max(0.0, -baseline_mean_r), 4)

    # Robustness-Score (0.0 bis 1.0)
    # Wenn die Edge selbst bei 0.15R Reibung profitabel bleibt -> hoher Score (> 0.75)
    # Wenn die Strategie schon bei 0.03R Reibung ins Minus kippt -> Overfitted (< 0.30)
    robustness_score = round(min(1.0, max(0.0, break_even_friction / 0.15)), 2)

    if robustness_score >= 0.80:
        grade = "INSTITUTIONAL_ROBUST"
        verdict = "Sehr robuster Edge. Hält auch massiver Reibung und weiten Spreads stand."
    elif robustness_score >= 0.50:
        grade = "MODERAT_ROBUST"
        verdict = "Solider Edge bei Standard-Reibung. Erfordert sauberes Kosten-Gate."
    elif robustness_score >= 0.25:
        grade = "FRAGIL"
        verdict = "Gefahr von Overfitting. Empfindlich gegenüber Slippage und Micro-Spreads."
    else:
        grade = "OVERFITTED_OR_NEGATIVE"
        verdict = "Kein Puffer gegen Marktreibung. Strategie benötigt strukturelle Kausalitäts-Filter."

    return {
        "trades_evaluated": n_trades,
        "baseline_mean_r": round(baseline_mean_r, 4),
        "break_even_friction_point_r": break_even_friction,
        "required_edge_improvement_r_per_trade": required_improvement,
        "robustness_score": robustness_score,
        "robustness_grade": grade,
        "verdict": verdict,
        "degradation_steps": degradation_curve
    }


# ==============================================================================
# 4. GESAMT-SUITE EXECUTION & EXPORT
# ==============================================================================

def run_full_robustness_suite() -> Dict[str, Any]:
    print("=" * 72)
    print("🔬 INSTITUTIONAL ROBUSTNESS & MONTE-CARLO STRESSTEST SUITE")
    print("=" * 72)

    report: Dict[str, Any] = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "architecture": {
            "sizing_model": "Flat Risk Parity (0.50% Equity / 1.0R)",
            "cluster_limit_r": 1.5,
            "max_portfolio_heat_r": 3.0,
            "drawdown_reduce_limit_r": 10.0,
            "drawdown_halt_limit_r": 15.0,
            "max_cost_r_ratio": 0.10
        },
        "audits": {}
    }

    # 1. Portfolio Stresstest
    if PORTFOLIO_FILE.exists():
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            p_data = json.load(f)
        p_closed = p_data.get("closed_trades", [])
        p_active = p_data.get("active_trades", [])
        capital = float(p_data.get("total_capital", 10000.0) or 10000.0)

        print(f"📊 Analysiere Modell-Portfolio ({len(p_closed)} geschlossene, {len(p_active)} aktive Positionen)...")
        mc_port = run_monte_carlo_permutation(p_closed, n_simulations=1000)
        stress_port = run_cluster_stress_test(p_active, total_capital=capital, closed_trades=p_closed)
        sens_port = run_parameter_sensitivity_test(p_closed)

        report["audits"]["portfolio"] = {
            "monte_carlo": mc_port,
            "cluster_stress": stress_port,
            "sensitivity": sens_port
        }

    # 2. Incubator Stresstest
    if INCUBATOR_FILE.exists():
        with open(INCUBATOR_FILE, "r", encoding="utf-8") as f:
            inc_data = json.load(f)
        inc_closed = inc_data.get("closed_trades", [])
        inc_active = inc_data.get("active_trades", [])

        print(f"🧪 Analysiere AI Incubator ({len(inc_closed)} geschlossene, {len(inc_active)} aktive Positionen)...")
        mc_inc = run_monte_carlo_permutation(inc_closed, n_simulations=1000)
        sens_inc = run_parameter_sensitivity_test(inc_closed)

        report["audits"]["incubator"] = {
            "monte_carlo": mc_inc,
            "sensitivity": sens_inc
        }

    report["live_readiness"] = evaluate_live_readiness(report["audits"])

    # Bericht atomar speichern
    tmp_file = REPORT_OUTPUT_FILE.with_suffix(".json.tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    os.replace(tmp_file, REPORT_OUTPUT_FILE)

    print(f"\n✅ Vollständiger Stresstest-Bericht gespeichert: {REPORT_OUTPUT_FILE}\n")
    _print_report(report)
    return report


def evaluate_live_readiness(audits: Dict[str, Any]) -> Dict[str, Any]:
    """Regelbasiertes Gesamturteil. Schutzmechanik ersetzt keinen positiven Erwartungswert."""
    blockers: List[str] = []
    warnings: List[str] = []

    for name, aud in audits.items():
        st = aud.get("monte_carlo", {}).get("sample_statistics")
        if not st:
            continue
        ci = st["mean_r_ci95"]
        if st["edge_significance"] == "SIGNIFIKANT_NEGATIV":
            blockers.append(
                f"{name}: Erwartungswert signifikant negativ (E(R) = {st['mean_r_per_trade']:+.3f}R, "
                f"95%-KI [{ci[0]:+.3f}, {ci[1]:+.3f}], t = {st['t_statistic']:.2f}, n = {aud['monte_carlo']['trades_evaluated']})."
            )
        elif st["edge_significance"] == "NICHT_SIGNIFIKANT":
            blockers.append(f"{name}: kein statistisch nachgewiesener positiver Erwartungswert (95%-KI [{ci[0]:+.3f}, {ci[1]:+.3f}]).")
        if st["win_rate_pct"] < st["breakeven_win_rate_pct"]:
            warnings.append(
                f"{name}: Trefferquote {st['win_rate_pct']}% liegt unter der Break-Even-Quote {st['breakeven_win_rate_pct']}%."
            )
        if st["losses_worse_than_1_5r"] > 0:
            warnings.append(
                f"{name}: {st['losses_worse_than_1_5r']} Verluste schlechter als -1.5R (schlechtester {st['worst_trade_r']}R) "
                f"- Stops begrenzen den Verlust nicht zuverlässig auf 1R."
            )

    cs = audits.get("portfolio", {}).get("cluster_stress")
    if cs:
        risk = cs["open_risk"]
        if risk["total_heat_breached"]:
            blockers.append(f"Offenes Gesamtrisiko {risk['total_heat_r']}R verletzt das Limit von {risk['max_total_heat_r']}R.")
        for cl, heat in risk["cluster_breaches"].items():
            blockers.append(f"Cluster {cl}: {heat}R offen, Limit {risk['max_cluster_heat_r']}R.")
        swan = cs["scenarios"]["SYSTEMIC_BLACK_SWAN"]
        if swan["insolvency_risk"] in ("HIGH", "SEVERE", "INSOLVENT"):
            blockers.append(
                f"Black-Swan-Verlust {swan['total_account_drawdown_pct']}% des aktuellen Eigenkapitals "
                f"(Einstufung {swan['insolvency_risk']})."
            )
        elif swan["insolvency_risk"] == "MODERATE":
            warnings.append(f"Black-Swan-Verlust {swan['total_account_drawdown_pct']}% des aktuellen Eigenkapitals.")
        hist_dd = audits["portfolio"]["monte_carlo"]["sample_statistics"]["historical_max_drawdown_r"]
        if hist_dd >= DEFAULT_CONFIG.drawdown_halt_r:
            blockers.append(
                f"Realisierter Drawdown {hist_dd}R liegt über dem Vollstopp-Limit {DEFAULT_CONFIG.drawdown_halt_r}R "
                f"- nach eigenem Regelwerk ist ein Strategy-Review fällig."
            )

    return {
        "decision": "NO_GO" if blockers else ("GO_WITH_CONDITIONS" if warnings else "GO"),
        "blockers": blockers,
        "warnings": warnings
    }


def _print_report(report: Dict[str, Any]) -> None:
    line = "─" * 70
    for name, aud in report.get("audits", {}).items():
        mc = aud.get("monte_carlo", {})
        st = mc.get("sample_statistics")
        if not st:
            continue
        print(f"┌{line}┐")
        print(f"│ {name.upper():<69}│")
        print(f"├{line}┤")
        ci = st["mean_r_ci95"]
        print(f"  Stichprobe   : n={mc['trades_evaluated']}, Summe {st['total_r']:+.2f}R, E(R) {st['mean_r_per_trade']:+.4f}R "
              f"(95%-KI {ci[0]:+.3f} .. {ci[1]:+.3f}), t={st['t_statistic']:.2f}")
        print(f"                 Trefferquote {st['win_rate_pct']}% (Break-Even {st['breakeven_win_rate_pct']}%), "
              f"Profit-Faktor {st['profit_factor']}, schlechtester Trade {st['worst_trade_r']}R")
        print(f"                 Historischer Max-DD {st['historical_max_drawdown_r']}R -> {st['edge_significance']}")
        for key, label in (("permutation_test", "Permutation "), ("bootstrap_test", "Bootstrap   "),
                           ("block_bootstrap_test", "Block-Boot. "), ("governed_bootstrap_test", "Mit Breaker ")):
            res = mc.get(key, {})
            dd = res.get("percentiles_max_dd_r", {})
            extra = ""
            if "prob_profitable_path_pct" in res:
                extra = f" | P(profitabel) {res['prob_profitable_path_pct']}%"
            if "prob_full_halt_pct" in res:
                extra += f" | P(Vollstopp) {res['prob_full_halt_pct']}%"
            print(f"  {label} : Max-DD P50 {dd.get('P50_median', 0):.2f}R  P90 {dd.get('P90', 0):.2f}R  "
                  f"P95 {dd.get('P95', 0):.2f}R  P99 {dd.get('P99', 0):.2f}R{extra}")

        cs = aud.get("cluster_stress")
        if cs:
            eq, risk, sc = cs["equity"], cs["open_risk"], cs["scenarios"]
            print(f"├{line}┤")
            print(f"  Eigenkapital : {eq['current_equity_eur']:.2f} € (Start {eq['initial_capital_eur']:.2f} €, "
                  f"realisiert {eq['realized_pnl_eur']:+.2f} €), Brutto-Hebel {eq['gross_leverage_on_current_equity']}x")
            print(f"  Offenes Risiko: {risk['total_heat_r']}R (Limit {risk['max_total_heat_r']}R)"
                  f"{' ⚠ VERLETZT' if risk['total_heat_breached'] else ''}; Cluster-Verstöße: {risk['cluster_breaches'] or 'keine'}")
            for key, label in (("CRYPTO_FLASH_CRASH", "Krypto-Crash "), ("EQUITY_FLASH_CRASH", "Aktien-Crash ")):
                x = sc[key]
                print(f"  {label}: {x['portfolio_loss_r']:.2f}R = {x['loss_pct_of_equity']}% Eigenkapital "
                      f"(naive Annahme: {x['naive_flat_slippage_loss_r']:.2f}R)")
            sw = sc["SYSTEMIC_BLACK_SWAN"]
            print(f"  Black Swan   : {sw['total_loss_r']:.2f}R (naive Annahme: {sw['naive_flat_slippage_loss_r']:.2f}R) -> "
                  f"{sw['drawdown_pct_r_accounting']}% (R-Buchhaltung) / {sw['drawdown_pct_declared_notional']}% (Nominal) "
                  f"des Eigenkapitals | Risiko: {sw['insolvency_risk']}")
            et = sc["EMPIRICAL_TAIL"]
            if et.get("available"):
                print(f"  Empir. Tail  : alle Positionen @P95-Verlust {et['all_positions_at_p95_loss_r']}R "
                      f"({et['all_positions_at_p95_loss_pct_of_equity']}%), @Worst {et['all_positions_at_worst_loss_r']}R "
                      f"({et['all_positions_at_worst_loss_pct_of_equity']}%)")

        sens = aud.get("sensitivity", {})
        if "robustness_score" in sens:
            print(f"├{line}┤")
            print(f"  Robustness   : {sens['robustness_score']:.2f} / 1.00 ({sens['robustness_grade']}), "
                  f"Break-Even-Reibung {sens['break_even_friction_point_r']}R, "
                  f"fehlende Edge {sens['required_edge_improvement_r_per_trade']}R/Trade")
        print(f"└{line}┘")

    lr = report.get("live_readiness", {})
    print(f"\n🏛  LIVE-READINESS: {lr.get('decision')}")
    for b in lr.get("blockers", []):
        print(f"   ✖ {b}")
    for w in lr.get("warnings", []):
        print(f"   ⚠ {w}")


if __name__ == "__main__":
    run_full_robustness_suite()
