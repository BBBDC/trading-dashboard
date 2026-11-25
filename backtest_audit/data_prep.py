#!/usr/bin/env python3
"""
backtest_audit/data_prep.py
===========================
Daten-Check, Total-Return-Snapshot (adjclose) & Qualitaets-Gate (D6/D9)
gemaess Pre-Registration v1.2 (knowledge_base/BACKTEST_AUDIT_PREREGISTRATION.md).
"""

import hashlib
import json
import math
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent.parent
KB_DIR = BASE_DIR / "knowledge_base"
OLD_CACHE_DIR = KB_DIR / "backtest_cache"
AUDIT_CACHE_DIR = KB_DIR / "audit_cache"
AUDIT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

MANIFEST_FILE = AUDIT_CACHE_DIR / "snapshot_manifest.json"
QUALITY_REPORT_FILE = AUDIT_CACHE_DIR / "data_quality_report.json"

NY_TZ = ZoneInfo("America/New_York")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# 2006-02-01 00:00:00 UTC -> 2026-11-21 00:00:00 UTC (inkl. 2026-11-20 US-Close)
PERIOD1 = 1138752000
PERIOD2 = 1795219200

ETFS = ["SPY", "QQQ", "DIA", "EWG", "EWU", "EWJ", "TLT", "IEF", "FXE", "FXY", "GLD", "DBC"]
RATE_SYM = "^IRX"


def fetch_yahoo_total_return(symbol: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Laedt Daily-OHLCV inkl. adjclose und Dividenden/Split-Events von Yahoo v8."""
    enc = urllib.parse.quote(symbol, safe="=^.-")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{enc}"
        f"?interval=1d&period1={PERIOD1}&period2={PERIOD2}&events=div,split"
    )
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    res = (payload.get("chart") or {}).get("result", [])
    if not res:
        raise RuntimeError(f"Keine Daten fuer {symbol}")
    r0 = res[0]
    timestamps = r0.get("timestamp") or []
    quote = ((r0.get("indicators") or {}).get("quote") or [{}])[0]
    adj_list = ((r0.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose") or []
    events = r0.get("events") or {}

    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    vols = quote.get("volume") or []

    by_date: Dict[str, Dict[str, Any]] = {}
    for i, ts in enumerate(timestamps):
        o = opens[i] if i < len(opens) else None
        h = highs[i] if i < len(highs) else None
        l = lows[i] if i < len(lows) else None
        c = closes[i] if i < len(closes) else None
        v = vols[i] if i < len(vols) else 0.0
        adj = adj_list[i] if i < len(adj_list) else c
        if o is None or h is None or l is None or c is None or adj is None:
            continue
        if c <= 0 or adj <= 0 or not all(math.isfinite(x) for x in (o, h, l, c, adj)):
            continue

        dt_ny = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(NY_TZ)
        date_str = dt_ny.strftime("%Y-%m-%d")
        if date_str > "2026-11-20":
            continue

        factor = float(adj) / float(c)
        by_date[date_str] = {
            "date": date_str,
            "t": int(ts),
            "o": round(float(o) * factor, 6),
            "h": round(float(h) * factor, 6),
            "l": round(float(l) * factor, 6),
            "c": round(float(adj), 6),
            "raw_o": float(o),
            "raw_h": float(h),
            "raw_l": float(l),
            "raw_c": float(c),
            "v": float(v or 0.0),
            "adj_factor": round(factor, 8),
        }

    bars = [by_date[d] for d in sorted(by_date.keys())]
    return bars, events


def check_quality_gate(symbol: str, bars: List[Dict[str, Any]], spy_dates: List[str]) -> Dict[str, Any]:
    """D6-Qualitaets-Gate je Instrument und Jahr (2007-2026)."""
    spy_idx = {d: i for i, d in enumerate(spy_dates)}
    by_year: Dict[str, Dict[str, Any]] = {}
    prev_raw_c: Optional[float] = None
    prev_spy_i: Optional[int] = None

    for b in bars:
        yr = b["date"][:4]
        if yr < "2007":
            prev_raw_c = b["raw_c"]
            prev_spy_i = spy_idx.get(b["date"], prev_spy_i)
            continue

        st = by_year.setdefault(
            yr,
            {
                "bars": 0,
                "open_eq_prev_close": 0,
                "high_eq_low": 0,
                "ohlc_inconsistent": 0,
                "gaps_gt_4d": 0,
                "any_bad": 0,
            },
        )
        st["bars"] += 1
        ro, rh, rl, rc = b["raw_o"], b["raw_h"], b["raw_l"], b["raw_c"]

        bad = False
        if prev_raw_c is not None and abs(ro - prev_raw_c) <= 1e-9:
            st["open_eq_prev_close"] += 1
            bad = True
        if abs(rh - rl) <= 1e-9:
            st["high_eq_low"] += 1
            bad = True
        if rh < max(ro, rc) - 1e-9 or rl > min(ro, rc) + 1e-9:
            st["ohlc_inconsistent"] += 1
            bad = True

        cur_spy_i = spy_idx.get(b["date"])
        if cur_spy_i is not None and prev_spy_i is not None and (cur_spy_i - prev_spy_i) > 4:
            st["gaps_gt_4d"] += 1
            bad = True

        if bad:
            st["any_bad"] += 1

        prev_raw_c = rc
        if cur_spy_i is not None:
            prev_spy_i = cur_spy_i

    flagged_years = []
    for yr, st in sorted(by_year.items()):
        err_pct = (st["any_bad"] / st["bars"] * 100.0) if st["bars"] > 0 else 0.0
        st["error_pct"] = round(err_pct, 2)
        if err_pct > 2.0:
            flagged_years.append({"year": yr, **st})

    return {
        "symbol": symbol,
        "total_bars": len(bars),
        "first_date": bars[0]["date"] if bars else None,
        "last_date": bars[-1]["date"] if bars else None,
        "warmup_bars_before_is": sum(1 for b in bars if b["date"] < "2008-03-01"),
        "is_bars": sum(1 for b in bars if "2008-03-01" <= b["date"] <= "2016-12-31"),
        "val_bars": sum(1 for b in bars if "2017-01-01" <= b["date"] <= "2021-12-31"),
        "holdout_bars": sum(1 for b in bars if b["date"] >= "2022-01-01"),
        "flagged_years_gt_2pct": flagged_years,
        "passed_d6": len(flagged_years) == 0,
    }


def check_d9_cross(symbol: str, bars: List[Dict[str, Any]], events: Dict[str, Any]) -> Dict[str, Any]:
    """D9-Abgleich: (a) gegen bestehenden backtest_cache (raw_c) & (b) interne Dividenden-Konsistenz."""
    old_path = OLD_CACHE_DIR / f"yahoo_{symbol}_1d.json"
    old_match_pct = None
    old_days = 0
    if old_path.exists():
        old_bars = json.loads(old_path.read_text(encoding="utf-8"))
        old_map = {
            datetime.fromtimestamp(int(x["t"]), tz=timezone.utc).astimezone(NY_TZ).strftime("%Y-%m-%d"): float(x["c"])
            for x in old_bars
        }
        cur_map = {b["date"]: b["raw_c"] for b in bars}
        common = sorted(set(old_map.keys()) & set(cur_map.keys()))
        if len(common) >= 10:
            ok = 0
            tot = 0
            for i in range(1, len(common)):
                d0, d1 = common[i - 1], common[i]
                r_old = old_map[d1] / old_map[d0] - 1.0
                r_cur = cur_map[d1] / cur_map[d0] - 1.0
                tot += 1
                if abs(r_old - r_cur) < 0.0005:  # < 5 bp
                    ok += 1
            old_days = tot
            old_match_pct = round(ok / tot * 100.0, 2) if tot > 0 else None

    # Interne Dividenden-Plausibilitaet: an Nicht-Ex-Div-Tagen muss adjclose-Rendite == raw_c-Rendite sein
    div_dates = set()
    for dv in (events.get("dividends") or {}).values():
        dt_ny = datetime.fromtimestamp(int(dv["date"]), tz=timezone.utc).astimezone(NY_TZ)
        div_dates.add(dt_ny.strftime("%Y-%m-%d"))

    non_div_tot = 0
    non_div_ok = 0
    for i in range(1, len(bars)):
        d1 = bars[i]["date"]
        if d1 in div_dates:
            continue
        r_adj = bars[i]["c"] / bars[i - 1]["c"] - 1.0
        r_raw = bars[i]["raw_c"] / bars[i - 1]["raw_c"] - 1.0
        non_div_tot += 1
        if abs(r_adj - r_raw) < 0.0005:  # < 5 bp
            non_div_ok += 1

    adj_consistency_pct = round(non_div_ok / non_div_tot * 100.0, 2) if non_div_tot > 0 else 0.0
    return {
        "old_cache_days_compared": old_days,
        "old_cache_within_5bp_pct": old_match_pct,
        "div_events_count": len(div_dates),
        "non_div_adj_vs_raw_within_5bp_pct": adj_consistency_pct,
        "passed_d9_internal": adj_consistency_pct >= 99.0,
    }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    print("Lade 3M-T-Bill (^IRX) und alle 12 US-ETFs (Total Return via adjclose)...")
    rate_bars, _ = fetch_yahoo_total_return(RATE_SYM)
    rate_path = AUDIT_CACHE_DIR / "IRX_1d.json"
    rate_path.write_text(json.dumps(rate_bars), encoding="utf-8")

    all_data: Dict[str, Tuple[List[Dict[str, Any]], Dict[str, Any]]] = {}
    for sym in ETFS:
        bars, events = fetch_yahoo_total_return(sym)
        all_data[sym] = (bars, events)
        out_p = AUDIT_CACHE_DIR / f"{sym}_1d.json"
        out_p.write_text(json.dumps(bars), encoding="utf-8")
        time.sleep(0.1)

    spy_dates = [b["date"] for b in all_data["SPY"][0]]
    quality_results = []
    manifest_files = {
        "IRX_1d.json": {
            "symbol": RATE_SYM,
            "bars": len(rate_bars),
            "first_date": rate_bars[0]["date"],
            "last_date": rate_bars[-1]["date"],
            "sha256": sha256_file(rate_path),
        }
    }

    for sym in ETFS:
        bars, events = all_data[sym]
        q_res = check_quality_gate(sym, bars, spy_dates)
        d9_res = check_d9_cross(sym, bars, events)
        q_res["d9_cross_check"] = d9_res
        quality_results.append(q_res)

        fname = f"{sym}_1d.json"
        manifest_files[fname] = {
            "symbol": sym,
            "bars": len(bars),
            "first_date": bars[0]["date"],
            "last_date": bars[-1]["date"],
            "sha256": sha256_file(AUDIT_CACHE_DIR / fname),
        }

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "preregistration_version": "v1.2",
        "holdout_cutoff_date": "2021-12-31",
        "files": manifest_files,
    }
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    QUALITY_REPORT_FILE.write_text(json.dumps(quality_results, indent=2), encoding="utf-8")

    print("\n=== DATEN-CHECK ZUSAMMENFASSUNG ===")
    for q in quality_results:
        d9 = q["d9_cross_check"]
        flags = ", ".join(f"{fy['year']}({fy['error_pct']}%)" for fy in q["flagged_years_gt_2pct"]) or "KEINE"
        print(
            f"{q['symbol']:4s} | {q['first_date']} -> {q['last_date']} | "
            f"Warmup={q['warmup_bars_before_is']:3d} IS={q['is_bars']:4d} Val={q['val_bars']:4d} HO={q['holdout_bars']:4d} | "
            f"D6-Flags: {flags} | D9-Old={d9['old_cache_within_5bp_pct']}% D9-Int={d9['non_div_adj_vs_raw_within_5bp_pct']}%"
        )
    print(f"\nIRX  | {rate_bars[0]['date']} -> {rate_bars[-1]['date']} | bars={len(rate_bars)}")
    print(f"Manifest & SHA256 gespeichert: {MANIFEST_FILE}")


if __name__ == "__main__":
    main()
