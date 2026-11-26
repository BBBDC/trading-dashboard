#!/usr/bin/env python3
"""
shadow_paper_book.py
====================
Prospektives Stufe-2 Schattenbuch (SHADOW_PAPER) direkt im Live-Signalweg von portfolio_engine.py.
- Isoliert in knowledge_base/shadow_paper_portfolio.json (kein Rueckkanal in trade_memory.json).
- Nutzt OHLC-Balken der jeweiligen Zell-Zeitebene mit identischem Exit-Modell wie backtest_matrix_engine.py
  (konservativ SL-vor-TP, Gap-Ausfuehrung, nach TP1 Break-Even + 2.0*ATR14 Trailing-Stop).
- Entkoppelt von Live-Kapazitaets- & Circuit-Breaker-Limits; dedupliziert pro cell_key.
"""

import hashlib
import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from circuit_breaker import (
    ASSET_FRICTION_DEFAULTS,
    TRIAD_PILOT_CONFIG,
    check_cluster_heat_limit,
    classify_asset_cluster,
)
from risk_engine import calculate_position_size

BASE_DIR = Path(__file__).resolve().parent
SHADOW_PAPER_FILE = BASE_DIR / "knowledge_base" / "shadow_paper_portfolio.json"
SHADOW_ARCHIVE_FILE = BASE_DIR / "knowledge_base" / "shadow_paper_archive.json"
SIGNAL_ENGINE_VERSION = "portfolio_v2"
EXIT_MODEL_VERSION = "backtest_parity_sl_first_v1"


def get_round_turn_friction_frac(symbol: str, category: str = "") -> float:
    """Berechnet Round-Turn-Reibung als Anteil (z.B. 0.0018 = 18 bp) aus ASSET_FRICTION_DEFAULTS (%-Punkte)."""
    cluster = classify_asset_cluster(symbol, category)
    fr = ASSET_FRICTION_DEFAULTS.get(cluster, ASSET_FRICTION_DEFAULTS["CRYPTO"])
    rt_pct = 2.0 * float(fr["fee_pct"]) + float(fr["spread_pct"]) + 2.0 * float(fr["slippage_pct"])
    return rt_pct / 100.0


def _compute_gate_params_hash(wl_check: Dict[str, Any], gov_params: Dict[str, Any]) -> str:
    payload = {
        "cell": wl_check.get("whitelist_cell") or {},
        "signal_engine_version": SIGNAL_ENGINE_VERSION,
        "exit_model_version": EXIT_MODEL_VERSION,
        "min_score_static": 88,
        "gov_updated_at": gov_params.get("updated_at", ""),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def load_shadow_book() -> Dict[str, Any]:
    if SHADOW_PAPER_FILE.exists():
        try:
            with open(SHADOW_PAPER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("active_trades", [])
                data.setdefault("closed_trades", [])
                return data
        except Exception:
            traceback.print_exc()
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "virtual_capital": 10000.0,
        "active_trades": [],
        "closed_trades": [],
        "metrics": {"total_trades": 0, "wins": 0, "losses": 0, "win_rate_pct": 0.0, "total_r": 0.0},
    }


def save_shadow_book(book: Dict[str, Any]) -> None:
    SHADOW_PAPER_FILE.parent.mkdir(parents=True, exist_ok=True)
    book["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = SHADOW_PAPER_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(book, f, indent=2, ensure_ascii=False)
    os.replace(tmp, SHADOW_PAPER_FILE)


def _archive_overflow(overflow_trades: List[Dict[str, Any]]) -> None:
    if not overflow_trades:
        return
    existing = []
    if SHADOW_ARCHIVE_FILE.exists():
        try:
            existing = json.loads(SHADOW_ARCHIVE_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    existing.extend(overflow_trades)
    tmp = SHADOW_ARCHIVE_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
    os.replace(tmp, SHADOW_ARCHIVE_FILE)


def _fetch_ohlc_for_shadow(sym: str, tf: str) -> List[Dict[str, Any]]:
    """Laedt OHLC-Balken der exakten Zell-Zeitebene fuer Backtest-paritaetisches Exit-Tracking."""
    tf_norm = str(tf or "1d").strip().lower()
    try:
        from asset_onboarding_evaluator import resolve_asset_target
        from backtest_data_loader import get_cached_bars
        target = resolve_asset_target(sym)
        if target and not target.get("untestable") and target.get("source") != "none":
            bars = get_cached_bars(target, interval=tf_norm, force_refresh=True)
            if bars:
                return bars
    except Exception:
        pass
    try:
        from fetch_real_ohlcv_cache import fetch_bars_direct
        bars = fetch_bars_direct(sym, interval=tf_norm, count=60)
        if bars:
            return bars
    except Exception:
        pass
    return []


def _tf_seconds(tf: str) -> int:
    s = str(tf or "1d").strip().lower()
    return {
        "5m": 300, "15m": 900, "30m": 1800,
        "1h": 3600, "4h": 14400, "8h": 28800,
        "1d": 86400, "3d": 259200, "1w": 604800,
    }.get(s, 86400)


def _calc_atr14_series(bars: List[Dict[str, Any]]) -> List[Optional[float]]:
    n = len(bars)
    out: List[Optional[float]] = [None] * n
    if n < 14:
        return out
    tr = [float(bars[0]["h"]) - float(bars[0]["l"])]
    for i in range(1, n):
        h, l, pc = float(bars[i]["h"]), float(bars[i]["l"]), float(bars[i - 1]["c"])
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    rma = sum(tr[:14]) / 14.0
    out[13] = rma
    alpha = 1.0 / 14.0
    for i in range(14, n):
        rma = (1.0 - alpha) * rma + alpha * tr[i]
        out[i] = rma
    return out


def update_shadow_paper_book(db_assets: List[Dict[str, Any]], now_dt: datetime) -> Dict[str, Any]:
    """Aktualisiert alle offenen SHADOW_PAPER-Trades auf Basis der OHLC-Balken ihrer Zell-Zeitebene."""
    book = load_shadow_book()
    now_iso = now_dt.isoformat()
    remaining_active = []
    closed_trades = book.get("closed_trades", [])

    for t in book.get("active_trades", []):
        sym = t["symbol"]
        tf = str(t.get("timeframe") or "1d").lower()
        bars = _fetch_ohlc_for_shadow(sym, tf)
        if not bars:
            remaining_active.append(t)
            continue

        atr14 = _calc_atr14_series(bars)
        tf_sec = _tf_seconds(tf)
        now_ts = int(now_dt.timestamp())
        last_ts = int(t.get("last_processed_ts") or t.get("entry_timestamp") or 0)
        entry_p = float(t["entry_price"])
        direction = str(t.get("direction", "LONG")).upper()
        sl = float(t.get("stop_loss", 0.0))
        tp1 = float(t.get("take_profit_1", 0.0))
        tp2 = float(t.get("take_profit_2", 0.0))
        init_risk = float(t.get("initial_risk_dist") or abs(entry_p - float(t.get("initial_stop_loss") or sl)))
        if init_risk <= 0:
            init_risk = max(entry_p * 0.01, 1e-6)

        exit_triggered = False
        exit_price = float(bars[-1]["c"])
        exit_reason = ""
        exit_ts = int(bars[-1]["t"])

        for idx, b in enumerate(bars):
            bt = int(b["t"])
            if bt <= last_ts or (bt + tf_sec) > now_ts:
                continue
            o, h, l, c = float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])
            a = atr14[idx] if atr14[idx] is not None else (init_risk * 0.5)
            t["last_processed_ts"] = bt
            t["current_price"] = c

            if direction == "LONG":
                if not t.get("tp1_partial_closed") and tp1 > 0 and h >= tp1:
                    t["tp1_partial_closed"] = True
                    t["partial_tp_price"] = tp1
                    sl = max(sl, entry_p)
                if t.get("tp1_partial_closed"):
                    sl = max(sl, h - 2.0 * a)
                t["stop_loss"] = sl

                # Konservativ SL vor TP2 (Backtest-Paritaet)
                if sl > 0 and l <= sl:
                    exit_triggered = True
                    exit_price = min(sl, o)
                    exit_reason = "SHADOW_TRAIL_BE_EXIT" if t.get("tp1_partial_closed") else "SHADOW_SL_EXIT"
                    exit_ts = bt
                    break
                if tp2 > 0 and h >= tp2:
                    exit_triggered = True
                    exit_price = tp2
                    exit_reason = "SHADOW_TP2_EXIT"
                    exit_ts = bt
                    break
            else:
                if not t.get("tp1_partial_closed") and tp1 > 0 and l <= tp1:
                    t["tp1_partial_closed"] = True
                    t["partial_tp_price"] = tp1
                    sl = min(sl, entry_p) if sl > 0 else entry_p
                if t.get("tp1_partial_closed"):
                    sl = min(sl, l + 2.0 * a) if sl > 0 else (l + 2.0 * a)
                t["stop_loss"] = sl

                if sl > 0 and h >= sl:
                    exit_triggered = True
                    exit_price = max(sl, o)
                    exit_reason = "SHADOW_TRAIL_BE_EXIT" if t.get("tp1_partial_closed") else "SHADOW_SL_EXIT"
                    exit_ts = bt
                    break
                if tp2 > 0 and l <= tp2:
                    exit_triggered = True
                    exit_price = tp2
                    exit_reason = "SHADOW_TP2_EXIT"
                    exit_ts = bt
                    break

        if exit_triggered:
            move_rem = (exit_price - entry_p) if direction == "LONG" else (entry_p - exit_price)
            if t.get("tp1_partial_closed"):
                tp1_p = float(t.get("partial_tp_price") or tp1)
                move_tp1 = (tp1_p - entry_p) if direction == "LONG" else (entry_p - tp1_p)
                gross_r = 0.5 * (move_tp1 / init_risk) + 0.5 * (move_rem / init_risk)
            else:
                gross_r = move_rem / init_risk

            rt_frac = get_round_turn_friction_frac(sym, t.get("category", ""))
            cost_r = (entry_p * rt_frac) / init_risk
            net_r = round(gross_r - cost_r, 3)

            t["status"] = "CLOSED"
            t["exit_price"] = round(exit_price, 6)
            t["exit_time"] = datetime.fromtimestamp(exit_ts, timezone.utc).isoformat()
            t["closed_at_iso"] = now_iso
            t["exit_reason"] = exit_reason
            t["realized_r"] = net_r
            t["cost_r"] = round(cost_r, 3)
            t["result"] = "WIN" if net_r > 0 else "LOSS"
            closed_trades.insert(0, t)
            print(f"   📋 [Shadow Paper Close] {sym} ({tf}, {direction}): {exit_reason} | {net_r:+.2f}R")
        else:
            remaining_active.append(t)

    if len(closed_trades) > 500:
        _archive_overflow(closed_trades[500:])
        closed_trades = closed_trades[:500]

    all_r = [float(x.get("realized_r", 0.0) or 0.0) for x in closed_trades]
    wins = sum(1 for r in all_r if r > 0)
    book["active_trades"] = remaining_active
    book["closed_trades"] = closed_trades
    book["metrics"] = {
        "total_trades": len(all_r),
        "active_count": len(remaining_active),
        "wins": wins,
        "losses": len(all_r) - wins,
        "win_rate_pct": round((wins / len(all_r) * 100.0), 1) if all_r else 0.0,
        "total_r": round(sum(all_r), 2),
        "expectancy_r": round((sum(all_r) / len(all_r)), 3) if all_r else 0.0,
    }
    save_shadow_book(book)
    return book


def try_open_shadow_paper_trade(
    candidate: Dict[str, Any],
    wl_check: Dict[str, Any],
    sig_tf: str,
    sl: float,
    tp1: float,
    tp2: float,
    score: int,
    setup_name: str,
    cat: str,
    horizon: str,
    now_dt: datetime,
    gov_params: Dict[str, Any],
) -> bool:
    """Eroeffnet einen prospektiven SHADOW_PAPER-Trade (dedupliziert pro cell_key, Heat als Flag)."""
    curr_p = float(candidate.get("price") or 0.0)
    if curr_p <= 0.0:
        return False

    book = load_shadow_book()
    active = book.get("active_trades", [])
    sym = candidate["symbol"]
    cell = wl_check.get("whitelist_cell") or {}
    cell_key = str(cell.get("cell_key") or f"{sym}_{sig_tf}").upper()

    # Nur pro cell_key deduplizieren (PG 15m blockiert nicht PG 30m!)
    if any(str(t.get("cell_key", "")).upper() == cell_key for t in active):
        return False

    heat_check = check_cluster_heat_limit(
        active, candidate_symbol=sym, candidate_category=cat, candidate_risk_r=1.0, config=TRIAD_PILOT_CONFIG
    )
    pos_size = calculate_position_size(
        entry_price=curr_p,
        stop_loss=sl,
        equity=float(book.get("virtual_capital", 10000.0)),
        risk_pct=TRIAD_PILOT_CONFIG.flat_risk_pct,
        score=score,
    )
    new_trade = {
        "trade_id": f"shadow_{cell_key}_{now_dt.strftime('%Y%m%d_%H%M')}",
        "symbol": sym,
        "name": candidate.get("name", sym),
        "category": cat,
        "cluster": heat_check.get("cluster", classify_asset_cluster(sym, cat)),
        "whitelist_tier": "SHADOW_PAPER",
        "cell_key": cell_key,
        "timeframe": sig_tf,
        "direction": candidate.get("signal", ""),
        "horizon": horizon,
        "score": score,
        "setup_name": setup_name,
        "entry_price": curr_p,
        "current_price": curr_p,
        "initial_stop_loss": sl,
        "stop_loss": sl,
        "initial_risk_dist": abs(curr_p - sl),
        "take_profit_1": tp1,
        "take_profit_2": tp2,
        "qty": pos_size.get("qty", 0.0),
        "entry_time": now_dt.isoformat(),
        "entry_timestamp": int(now_dt.timestamp()),
        "last_processed_ts": int(now_dt.timestamp()),
        "status": "OPEN",
        "would_block_heat": not bool(heat_check.get("is_allowed", True)),
        "gate_params_hash": _compute_gate_params_hash(wl_check, gov_params),
        "signal_engine_version": SIGNAL_ENGINE_VERSION,
        "exit_model_version": EXIT_MODEL_VERSION,
    }
    active.append(new_trade)
    book["active_trades"] = active
    save_shadow_book(book)
    print(f"   📋 [Shadow Paper Open] {sym} ({sig_tf}, {new_trade['direction']}) | Cell={cell_key} | HeatFlag={new_trade['would_block_heat']}")
    return True
