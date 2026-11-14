#!/usr/bin/env python3
"""
verify_protective_measures.py
==============================
Institutionelles A/B-Verifikations- & Auditmodul für Risikoschutz-Maßnahmen:
1. Flaches Sizing (0.5% Flat Risk)
2. Cluster-Heat-Limit (max 1.5R je Cluster, max 3.0R Gesamt-Heat)
3. Drawdown Circuit-Breaker (-3.0R Tagesverlust, -10.0R Sizing halbieren, -15.0R Vollstopp)
4. Kosten-Gate (Reibung <= 10% des Stop-Abstands)

Vergleicht die ungeschützte historische Baseline mit dem gegenfaktisch geschützten Verlauf
auf Basis der echten Trades aus dem Portfolio und dem AI Incubator.
"""

import os
import sys
import json
import math
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Tuple

BASE_DIR = Path(__file__).resolve().parent
PORTFOLIO_FILE = BASE_DIR / "knowledge_base" / "autonomous_portfolio.json"
INCUBATOR_FILE = BASE_DIR / "knowledge_base" / "incubator_trades.json"
AUDIT_OUTPUT_FILE = BASE_DIR / "knowledge_base" / "protective_measures_audit.json"

from circuit_breaker import (
    classify_asset_cluster,
    check_cost_gate,
    check_drawdown_circuit_breaker,
    check_cluster_heat_limit,
    CircuitBreakerConfig,
    DEFAULT_CONFIG,
    _to_utc,
    _trade_exit_time,
    _trade_r
)


def run_counterfactual_audit(
    trades: List[Dict[str, Any]], 
    name: str = "Portfolio",
    config: CircuitBreakerConfig = DEFAULT_CONFIG
) -> Dict[str, Any]:
    """
    Simuliert den Trade-Stream einmal ungeschützt (Baseline) und einmal
    streng nach den Sofort-Schutz-Regeln (Managed Counterfactual).
    """
    # Chronologisch sortieren (älteste zuerst)
    sorted_trades = []
    for t in trades:
        ex_time = _trade_exit_time(t) or _to_utc(t.get("entry_time")) or datetime.min.replace(tzinfo=timezone.utc)
        sorted_trades.append((ex_time, t))
    sorted_trades.sort(key=lambda x: x[0])
    ordered = [t for _, t in sorted_trades]

    # --- 1. BASELINE (UNMANAGED) ---
    base_trades_count = 0
    base_wins = 0
    base_losses = 0
    base_r_pnl = 0.0
    base_peak_r = 0.0
    base_max_dd_r = 0.0
    base_curve = []

    for t in ordered:
        r = _trade_r(t)
        if r is None:
            r = round(float(t.get("realized_pnl_pct", 0.0)) / 2.0, 2)
        base_trades_count += 1
        if r > 0:
            base_wins += 1
        elif r < 0:
            base_losses += 1
        base_r_pnl += r
        base_peak_r = max(base_peak_r, base_r_pnl)
        dd = base_peak_r - base_r_pnl
        base_max_dd_r = max(base_max_dd_r, dd)
        base_curve.append(round(base_r_pnl, 2))

    base_win_rate = round(base_wins / base_trades_count * 100.0, 1) if base_trades_count > 0 else 0.0

    # --- 2. MANAGED (PROTECTIVE REGIME COUNTERFACTUAL) ---
    managed_trades = []
    cost_gate_rejected = 0
    cluster_heat_rejected = 0
    daily_halt_rejected = 0
    drawdown_halt_rejected = 0

    managed_closed_history: List[Dict[str, Any]] = []
    active_virtual_trades: List[Dict[str, Any]] = []

    managed_r_pnl = 0.0
    managed_peak_r = 0.0
    managed_max_dd_r = 0.0
    managed_wins = 0
    managed_losses = 0
    managed_curve = []

    current_day = None
    daily_loss_r = 0.0

    for t in ordered:
        t_entry_time = _to_utc(t.get("entry_time")) or _trade_exit_time(t) or datetime.now(timezone.utc)
        t_exit_time = _trade_exit_time(t) or t_entry_time

        # Tag-Wechsel prüfen
        t_date = t_entry_time.date()
        if current_day != t_date:
            current_day = t_date
            daily_loss_r = 0.0

        # Aktive virtuelle Trades bereinigen (Positions-Lifecycle)
        active_virtual_trades = [
            av for av in active_virtual_trades 
            if (_trade_exit_time(av) or datetime.max.replace(tzinfo=timezone.utc)) > t_entry_time
        ]

        entry_p = float(t.get("entry_price") or 100.0)
        sl = float(t.get("stop_loss") or t.get("sl") or (entry_p * 0.95))
        sym = str(t.get("symbol") or "UNKNOWN")
        cat = str(t.get("category") or "")

        # A) Kosten-Gate prüfen
        cost_chk = check_cost_gate(entry_price=entry_p, stop_loss=sl, config=config)
        if not cost_chk["is_allowed"]:
            cost_gate_rejected += 1
            continue

        # B) Drawdown Circuit-Breaker prüfen
        cb_res = check_drawdown_circuit_breaker(managed_closed_history, current_time=t_entry_time, config=config)
        if cb_res["is_halted"]:
            if cb_res["action"] == "HALT_FULL":
                drawdown_halt_rejected += 1
            else:
                daily_halt_rejected += 1
            continue

        # C) Cluster-Heat Limit prüfen
        heat_chk = check_cluster_heat_limit(active_virtual_trades, candidate_symbol=sym, candidate_category=cat, candidate_risk_r=1.0, config=config)
        if not heat_chk["is_allowed"]:
            cluster_heat_rejected += 1
            continue

        # Trade wird ausgeführt!
        active_virtual_trades.append(t)
        sizing_mult = cb_res["sizing_multiplier"]

        r_raw = _trade_r(t)
        if r_raw is None:
            r_raw = round(float(t.get("realized_pnl_pct", 0.0)) / 2.0, 2)

        effective_r = round(r_raw * sizing_mult, 2)
        managed_r_pnl += effective_r
        managed_peak_r = max(managed_peak_r, managed_r_pnl)
        curr_dd = managed_peak_r - managed_r_pnl
        managed_max_dd_r = max(managed_max_dd_r, curr_dd)

        if effective_r > 0:
            managed_wins += 1
        elif effective_r < 0:
            managed_losses += 1

        managed_curve.append(round(managed_r_pnl, 2))
        managed_closed_copy = dict(t)
        managed_closed_copy["realized_r"] = effective_r
        managed_closed_copy["exit_time"] = t_exit_time.isoformat()
        managed_closed_history.append(managed_closed_copy)

    managed_trades_count = len(managed_closed_history)
    managed_win_rate = round(managed_wins / managed_trades_count * 100.0, 1) if managed_trades_count > 0 else 0.0

    r_saved = round(managed_r_pnl - base_r_pnl, 2)
    dd_reduction = round(base_max_dd_r - managed_max_dd_r, 2)
    dd_reduction_pct = round((dd_reduction / base_max_dd_r * 100.0), 1) if base_max_dd_r > 0 else 0.0

    return {
        "dataset_name": name,
        "total_historical_trades": len(ordered),
        "baseline": {
            "trades_taken": base_trades_count,
            "wins": base_wins,
            "losses": base_losses,
            "win_rate_pct": base_win_rate,
            "total_pnl_r": round(base_r_pnl, 2),
            "max_drawdown_r": round(base_max_dd_r, 2),
            "capital_pnl_est_eur": round(base_r_pnl * 100.0, 2)
        },
        "managed": {
            "trades_taken": managed_trades_count,
            "wins": managed_wins,
            "losses": managed_losses,
            "win_rate_pct": managed_win_rate,
            "total_pnl_r": round(managed_r_pnl, 2),
            "max_drawdown_r": round(managed_max_dd_r, 2),
            "capital_pnl_est_eur": round(managed_r_pnl * 50.0, 2)  # 50€ pro 1R (0.5% auf 10k€)
        },
        "protection_impact": {
            "cost_gate_filtered": cost_gate_rejected,
            "cluster_heat_filtered": cluster_heat_rejected,
            "daily_loss_halt_filtered": daily_halt_rejected,
            "drawdown_halt_filtered": drawdown_halt_rejected,
            "total_filtered_trades": cost_gate_rejected + cluster_heat_rejected + daily_halt_rejected + drawdown_halt_rejected,
            "capital_saved_r": r_saved,
            "drawdown_reduction_r": dd_reduction,
            "drawdown_reduction_pct": dd_reduction_pct
        }
    }


def main():
    print("=" * 70)
    print("🛡️ STARTE A/B-VERIFIKATION & GEGENFAKTISCHES SCHUTZ-AUDIT")
    print("=" * 70)

    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "flat_risk_pct": DEFAULT_CONFIG.flat_risk_pct,
            "daily_loss_limit_r": DEFAULT_CONFIG.daily_loss_limit_r,
            "drawdown_reduce_r": DEFAULT_CONFIG.drawdown_reduce_r,
            "drawdown_halt_r": DEFAULT_CONFIG.drawdown_halt_r,
            "max_total_heat_r": DEFAULT_CONFIG.max_total_heat_r,
            "max_cluster_heat_r": DEFAULT_CONFIG.max_cluster_heat_r,
            "max_cost_r_ratio": DEFAULT_CONFIG.max_cost_r_ratio
        },
        "audits": {}
    }

    # 1. Portfolio Audit
    if PORTFOLIO_FILE.exists():
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            p_data = json.load(f)
        p_closed = p_data.get("closed_trades", [])
        if p_closed:
            print(f"📊 Analysiere Modell-Portfolio ({len(p_closed)} Trades)...")
            res_port = run_counterfactual_audit(p_closed, name="Modell-Portfolio (High-Conviction)")
            results["audits"]["portfolio"] = res_port

    # 2. AI Incubator Audit
    if INCUBATOR_FILE.exists():
        with open(INCUBATOR_FILE, "r", encoding="utf-8") as f:
            inc_data = json.load(f)
        inc_closed = inc_data.get("closed_trades", [])
        if inc_closed:
            print(f"🧪 Analysiere AI Incubator ({len(inc_closed)} Trades)...")
            res_inc = run_counterfactual_audit(inc_closed, name="AI Incubator & Rapid Post-Mortem Lab")
            results["audits"]["incubator"] = res_inc

    # Speichern
    with open(AUDIT_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Audit-Bericht erfolgreich gespeichert: {AUDIT_OUTPUT_FILE}\n")

    # Zusammenfassung ausgeben
    for k, v in results["audits"].items():
        b = v["baseline"]
        m = v["managed"]
        p = v["protection_impact"]
        print(f"--- ERGEBNIS: {v['dataset_name']} ---")
        print(f"  • Trades Gesamt        : {v['total_historical_trades']}")
        print(f"  • Baseline (Ungeschützt): {b['trades_taken']} Trades | PnL: {b['total_pnl_r']:+.2f}R | Max DD: -{b['max_drawdown_r']:.2f}R | WR: {b['win_rate_pct']}%")
        print(f"  • Mit Schutz-Governance: {m['trades_taken']} Trades | PnL: {m['total_pnl_r']:+.2f}R | Max DD: -{m['max_drawdown_r']:.2f}R | WR: {m['win_rate_pct']}%")
        print(f"  🛡️ Schutz-Wirkung:")
        print(f"     - Not-Aus / Circuit-Breaker Filter: {p['drawdown_halt_filtered'] + p['daily_loss_halt_filtered']} Trades abgefangen")
        print(f"     - Cluster-Heat-Limit Filter        : {p['cluster_heat_filtered']} Klumpen-Trades verhindert")
        print(f"     - Kosten-Gate Filter              : {p['cost_gate_filtered']} unrentable Trades blockiert")
        print(f"     - Gerettetes Kapital               : {p['capital_saved_r']:+.2f}R (Drawdown reduziert um {p['drawdown_reduction_pct']}%)")
        print()

if __name__ == "__main__":
    main()
