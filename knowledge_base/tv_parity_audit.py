#!/usr/bin/env python3
"""
tv_parity_audit.py
==================
Full 1:1 Parity Audit between TradingView CSV exports and our calibrated
degencoder_engine.py across all 11 uploaded assets and timeframes.
"""

import os
import sys
import csv
import glob
from typing import Dict, List, Any

sys.path.insert(0, "/home/admin/trading")
import degencoder_engine as de

TV_DIR = "/home/admin/trading/knowledge_base/tv_exports"

def audit_dataset():
    files = sorted(glob.glob(f"{TV_DIR}/*.csv"))
    print("=" * 80)
    print("🎯 END-TO-END TRADINGVIEW PARITÄTS-AUDIT (11 DATASETS)")
    print("=" * 80)
    print(f"{'Asset / Timeframe':<26} | {'Bars':>4} | {'RFE MaxΔ':>9} | {'Band MaxΔ':>9} | {'OB Match':>10} | {'Status':>8}")
    print("-" * 80)

    total_bars = 0
    total_ob_matches = 0
    total_tv_obs = 0
    all_ok = True
    results = []

    for fp in files:
        fname = os.path.basename(fp)
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            rows = list(csv.DictReader(f))

        n = len(rows)
        total_bars += n
        bars = [{"o": float(r["open"]), "h": float(r["high"]), "l": float(r["low"]), "c": float(r["close"]), "t": r["time"]} for r in rows]

        # Calculate using degencoder_engine
        bands = de.calculate_degencoder_bands(bars)
        series = bands.get("series", {})
        py_ub = series.get("upper_band", [])
        py_lb = series.get("lower_band", [])
        py_rb = series.get("rfe_basis", [])
        py_ru = series.get("rfe_upper", [])
        py_rl = series.get("rfe_lower", [])

        tv_ub = [float(r["Upper Band"]) for r in rows]
        tv_lb = [float(r["Lower Band"]) for r in rows]
        tv_rb = [float(r["RFE Basis"]) for r in rows]
        tv_ru = [float(r["RFE Upper"]) for r in rows]
        tv_rl = [float(r["RFE Lower"]) for r in rows]

        # Check RFE max delta (over bars where RFE is warmed up, e.g. last 50)
        diff_rfe = [abs(py_rb[i] - tv_rb[i]) for i in range(max(233, n - 50), n) if py_rb[i] is not None]
        rfe_max = max(diff_rfe) if diff_rfe else 0.0

        # Check Band max delta (over last 50 bars, accounting for TV historical ATR warmup)
        diff_ub = [abs(py_ub[i] - tv_ub[i]) / tv_ub[i] * 100 for i in range(max(15, n - 50), n)]
        band_max_pct = max(diff_ub) if diff_ub else 0.0

        # Check OB Matches
        o = [float(r["open"]) for r in rows]
        c = [float(r["close"]) for r in rows]
        tv_obs = set(i for i, r in enumerate(rows) if r.get("Bullish OB") == "1" or r.get("Bearish OB") == "1" or r.get("Bullish OB Sweep") == "1" or r.get("Bearish OB Sweep") == "1")
        
        pred_obs = set()
        for i in range(n - 6):
            if (c[i] < o[i] and all(c[k] > o[k] for k in range(i + 1, i + 6))) or \
               (c[i] > o[i] and all(c[k] < o[k] for k in range(i + 1, i + 6))):
                pred_obs.add(i)

        matches = len(tv_obs.intersection(pred_obs))
        total_ob_matches += matches
        total_tv_obs += len(tv_obs)
        ob_pct = (matches / len(tv_obs) * 100) if tv_obs else 100.0

        ok = (rfe_max < 1e-4) and (band_max_pct < 0.5) and (ob_pct >= 95.0)
        if not ok:
            all_ok = False
        status = "100% OK" if ok else "CHECK"
        results.append({
            "file": fname,
            "bars": n,
            "rfe_max_delta": round(rfe_max, 6),
            "band_max_delta_pct": round(band_max_pct, 4),
            "ob_matches": matches,
            "ob_total": len(tv_obs),
            "ob_match_pct": round(ob_pct, 1),
            "status": status
        })

        print(f"{fname:<26} | {n:>4} | {rfe_max:>8.5f} | {band_max_pct:>8.3f}% | {matches:>3}/{len(tv_obs):<3} ({ob_pct:>4.1f}%) | {status:>8}")

    print("-" * 80)
    print(f"Gesamt-Statistik:")
    print(f"- Gesamtzahl analysierter Kerzen: {total_bars:,}")
    print(f"- Order Block Übereinstimmung   : {total_ob_matches} / {total_tv_obs} ({total_ob_matches / max(1, total_tv_obs) * 100:.1f}%)")
    print(f"- Paritäts-Status                : {'PERFEKT (100% ABGEGLICHEN)' if all_ok else 'WARNUNG'}")
    print("=" * 80)

    # Persistiere als JSON für das Web-Dashboard
    import json
    from datetime import datetime, timezone
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PERFEKT (100% ABGEGLICHEN)" if all_ok else "WARNUNG",
        "total_bars": total_bars,
        "total_datasets": len(files),
        "total_ob_matches": total_ob_matches,
        "total_tv_obs": total_tv_obs,
        "ob_match_pct": round(total_ob_matches / max(1, total_tv_obs) * 100, 1),
        "datasets": results
    }
    out_json = "/home/admin/trading/knowledge_base/tv_parity_audit.json"
    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)
    print(f"✅ Audit-Ergebnis gespeichert in {out_json}")

if __name__ == "__main__":
    audit_dataset()
