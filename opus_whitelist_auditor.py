#!/usr/bin/env python3
"""
Autonomer Claude Opus 5.5 Whitelist- & Memory-Auditor (wöchentlich / nach Deep-Backtest).
=========================================================================================
Vorschlag A (Bidirektionale Whitelist-Governance):
  - Auditiert SOWOHL bestehende statische/dynamische Whitelist-Zellen (inkl. Upgrades
    SHADOW_PAPER -> PILOT_LIVE, Downgrades, Direction-Locks & Deaktivierung verfallener Edges)
    ALS AUCH neu qualifizierte Matrix-Backtest-Kandidaten.
  - Erzwingt harte Python-Mathe-Gates (nicht durch Opus überstimmbar!):
    PILOT_LIVE nur bei math_pilot_eligible == True, SECULAR_BULL_TICKERS Drift-Sperre,
    Cluster-Cap max. 5/Cluster, Gesamt-Cap max. 15 PILOT_LIVE.

Vorschlag B (Wöchentliche Gedächtnis-Synthese):
  - Dedupliziert redundante Learnings in knowledge_base/trade_memory.json, destilliert
    eine kompakte "master_constitution" (Top-Axiome) und erzeugt maschinenlesbare,
    geclampte Steuerparameter in knowledge_base/opus_governor_params.json.
"""

import argparse
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
KB_DIR = BASE_DIR / "knowledge_base"
BULK_FILE = KB_DIR / "asset_evaluations_bulk.json"
ONBOARD_FILE = KB_DIR / "asset_evaluations.json"
DYN_WL_FILE = KB_DIR / "triad_whitelist_dynamic.json"
AUDIT_REPORT_FILE = KB_DIR / "opus_whitelist_audit_report.json"
TRADE_MEMORY_FILE = KB_DIR / "trade_memory.json"
PORTFOLIO_FILE = KB_DIR / "autonomous_portfolio.json"
SHADOW_PAPER_FILE = KB_DIR / "shadow_paper_portfolio.json"
SHADOW_ARCHIVE_FILE = KB_DIR / "shadow_paper_archive.json"
INCUBATOR_FILE = KB_DIR / "incubator_trades.json"
GOVERNOR_PARAMS_FILE = KB_DIR / "opus_governor_params.json"
CLAUDE_BIN = "/home/admin/.local/bin/claude"

DEFAULT_GOVERNOR_PARAMS: Dict[str, Any] = {
    "min_score_default": 88,
    "min_score_counter_trend": 94,
    "min_vsa_ratio_reversal": 1.20,
    "max_rsi_long_entry": 64.0,
    "min_rsi_short_entry": 36.0,
    "max_holding_days_fast_swing": 4.0,
    "max_holding_days_core_swing": 14.0,
    "max_holding_days_macro_trend": 45.0,
    "stagnation_profit_lock_days": 12.0,
    "incubator_time_stop_hours": {"5m": 12.0, "15m": 18.0, "30m": 24.0},
    "sector_score_adjustments": {},
}


def _load(path: Path, default):
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _save_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _clamp(val: Any, lo: float, hi: float, default: float, as_int: bool = False):
    try:
        num = float(val)
        if not math.isfinite(num):
            num = float(default)
    except (TypeError, ValueError):
        num = float(default)
    clamped = max(float(lo), min(float(hi), num))
    return int(round(clamped)) if as_int else round(clamped, 2)


def _bootstrap_p_value(r_list: List[float], n_boot: int = 2000, seed: int = 42) -> float:
    n = len(r_list)
    if n < 5:
        return 1.0
    rng = random.Random(seed)
    non_pos = 0
    for _ in range(n_boot):
        s = sum(r_list[rng.randrange(n)] for _ in range(n))
        if s <= 0.0:
            non_pos += 1
    return round(non_pos / n_boot, 4)


def _t_stat(r_list: List[float]) -> float:
    n = len(r_list)
    if n < 2:
        return 0.0
    mean = sum(r_list) / n
    var = sum((x - mean) ** 2 for x in r_list) / (n - 1)
    sd = math.sqrt(var)
    if sd <= 1e-12:
        return 0.0
    return round(mean / (sd / math.sqrt(n)), 2)


def _allowed_dirs_from_mode(mode: str) -> List[str]:
    if mode == "Nur Long":
        return ["LONG"]
    if mode == "Nur Short":
        return ["SHORT"]
    return ["LONG", "SHORT"]


def _mode_from_allowed_dirs(dirs: List[str]) -> str:
    d_set = {str(d).upper() for d in (dirs or [])}
    if d_set == {"LONG"}:
        return "Nur Long"
    if d_set == {"SHORT"}:
        return "Nur Short"
    return "Long & Short"


def _norm_tf(tf: str) -> str:
    s = str(tf or "").strip().lower()
    return "1d" if s == "1d" else s


def _make_cell_key(raw_sym: str, tf: str, mode: str) -> str:
    clean = re.sub(r"[^A-Z0-9]+", "_", raw_sym.upper()).strip("_")
    suffix = "_LONG" if mode == "Nur Long" else ("_SHORT" if mode == "Nur Short" else "")
    return f"DYN_{clean}_{tf.upper()}{suffix}"


def _fee_slip_for_cat(cat: str) -> tuple:
    if cat == "Forex":
        return 0.00005, 0.0001
    if cat in ("US-Tech", "DAX", "Index", "Commodity", "Aktien", "Tradegate / EU", "Anleihen/ETF"):
        return 0.0002, 0.0001
    return 0.00055, 0.0002


def _eval_backtest_metrics(bt: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not bt or bt["trades"] < 5:
        return None
    r_list = bt.get("trade_r_list") or []
    p_boot = _bootstrap_p_value(r_list)
    t_stat = _t_stat(r_list)
    oos_trades = int(bt["oos_trades"] or 0)
    oos_exp_r = round(bt["oos_r"] / oos_trades, 3) if oos_trades > 0 else 0.0
    math_pilot = (
        bt["trades"] >= 30
        and oos_trades >= 10
        and bt["profit_factor"] >= 1.35
        and bt["expectancy_r"] >= 0.15
        and bt["oos_r"] > 0.0
        and oos_exp_r >= 0.10
        and p_boot < 0.05
        and t_stat >= 1.60
        and bt["max_dd_pct"] <= 25.0
    )
    math_shadow = (
        bt["trades"] >= 15
        and oos_trades >= 5
        and bt["profit_factor"] >= 1.25
        and bt["expectancy_r"] >= 0.10
        and bt["oos_r"] > 0.0
        and p_boot < 0.12
    )
    return {
        "trades": bt["trades"],
        "win_rate": bt["win_rate"],
        "profit_factor": bt["profit_factor"],
        "expectancy_r": bt["expectancy_r"],
        "total_r": bt["total_r"],
        "max_dd_pct": bt["max_dd_pct"],
        "oos_trades": oos_trades,
        "oos_wr": bt["oos_wr"],
        "oos_r": bt["oos_r"],
        "oos_exp_r": oos_exp_r,
        "p_boot": p_boot,
        "t_stat": t_stat,
        "math_pilot_eligible": math_pilot,
        "math_shadow_eligible": math_shadow,
    }


def _live_stats_for_symbols(
    symbols: List[str],
    port_closed: List[dict],
    shadow_closed: Optional[List[dict]] = None,
    cell_key: str = "",
) -> Dict[str, Any]:
    norm_syms = {str(s).upper() for s in symbols if s}
    norm_ticks = {s.split(":")[-1] for s in norm_syms}
    ck_u = str(cell_key or "").upper()
    p_r, s_r = [], []
    earliest_shadow_ts = None
    for t in port_closed:
        ts = str(t.get("symbol", "")).upper()
        tt = ts.split(":")[-1]
        if ts in norm_syms or tt in norm_ticks:
            p_r.append(float(t.get("realized_r", 0.0) or 0.0))
    for t in (shadow_closed or []):
        t_ck = str(t.get("cell_key", "")).upper()
        if ck_u and t_ck == ck_u and t.get("exit_model_version") == "backtest_parity_sl_first_v2":
            s_r.append(float(t.get("realized_r", 0.0) or 0.0))
            ets = t.get("entry_timestamp")
            if ets and (earliest_shadow_ts is None or ets < earliest_shadow_ts):
                earliest_shadow_ts = ets

    n_s = len(s_r)
    s_mean = (sum(s_r) / n_s) if n_s > 0 else 0.0
    if n_s >= 2:
        s_var = sum((x - s_mean) ** 2 for x in s_r) / (n_s - 1)
        s_se = math.sqrt(s_var / n_s)
        ci95_low = round(s_mean - 1.96 * s_se, 3)
    else:
        ci95_low = None

    if n_s >= 30 and ci95_low is not None and ci95_low >= 0.0:
        promo_stage = "ELIGIBLE_PILOT_FULL_1_0X"
    elif n_s >= 15 and ci95_low is not None and ci95_low >= -0.05:
        promo_stage = "ELIGIBLE_PILOT_QUARTER_0_25X"
    else:
        promo_stage = "COLLECTING_SHADOW"

    days_observed = round((datetime.now(timezone.utc).timestamp() - earliest_shadow_ts) / 86400.0, 1) if earliest_shadow_ts else 0.0
    stalled_90d = (days_observed >= 90.0 and n_s < 3)

    return {
        "live_portfolio_trades": len(p_r),
        "live_portfolio_r": round(sum(p_r), 2),
        "shadow_paper_trades": n_s,
        "shadow_paper_r": round(sum(s_r), 2),
        "shadow_paper_ci95_low": ci95_low,
        "promotion_stage": promo_stage,
        "shadow_days_observed": days_observed,
        "stalled_90d": stalled_90d,
    }


def collect_existing_whitelist_cells() -> Tuple[List[Dict[str, Any]], set]:
    """
    Vorschlag A: Sammelt ALLE bestehenden statischen und dynamischen Whitelist-Zellen
    und bewertet sie anhand des aktuellsten tiefen Historien-Backtests sowie realer Live/Paper-Trades.
    Gibt (existing_cells, covered_signatures) zurück.
    """
    from asset_onboarding_evaluator import resolve_asset_target
    from backtest_data_loader import get_cached_bars
    from backtest_matrix_engine import precompute_indicators, run_single_backtest
    from circuit_breaker import _STATIC_WHITELIST_BASE, classify_asset_cluster

    dyn_raw = _load(DYN_WL_FILE, {})
    dyn_entries = dyn_raw.get("entries", {}) if isinstance(dyn_raw, dict) else {}
    disabled_keys = set(str(k) for k in (dyn_raw.get("disabled_keys") or [])) if isinstance(dyn_raw, dict) else set()

    port_closed = (_load(PORTFOLIO_FILE, {}) or {}).get("closed_trades") or []
    shadow_closed = list((_load(SHADOW_PAPER_FILE, {}) or {}).get("closed_trades") or [])
    shadow_arch = _load(SHADOW_ARCHIVE_FILE, [])
    if isinstance(shadow_arch, list):
        shadow_closed.extend(shadow_arch)
    inc_closed = (_load(INCUBATOR_FILE, {}) or {}).get("closed_trades") or []

    all_cells: Dict[str, Dict[str, Any]] = {k: dict(v) for k, v in _STATIC_WHITELIST_BASE.items()}
    for k, v in (dyn_entries or {}).items():
        if isinstance(v, dict):
            all_cells[str(k)] = dict(v)

    existing_cells: List[Dict[str, Any]] = []
    covered_signatures: set = set()

    for cell_key, cell in all_cells.items():
        is_static = cell_key in _STATIC_WHITELIST_BASE
        syms = cell.get("symbols") or []
        tf = str(cell.get("timeframe") or "1d")
        tf_norm = _norm_tf(tf)
        dirs = [str(d).upper() for d in (cell.get("allowed_directions") or ["LONG", "SHORT"])]
        cur_mode = _mode_from_allowed_dirs(dirs)
        cur_tier = "DISABLED" if cell_key in disabled_keys else str(cell.get("tier") or "SHADOW_PAPER")

        best_target = None
        best_bars: List[dict] = []
        raw_sym = str(syms[0]) if syms else cell_key
        for s in syms:
            t = resolve_asset_target(str(s))
            if t.get("untestable") or t.get("source") == "none":
                continue
            bars = get_cached_bars(t, interval=tf_norm)
            if bars and len(bars) > len(best_bars):
                best_bars = bars
                best_target = t
                raw_sym = str(s)
            if len(best_bars) >= 200:
                break

        modes_detail: Dict[str, Dict[str, Any]] = {}
        modes_alt_summary: Dict[str, Dict[str, Any]] = {}
        data_sym = best_target["symbol"] if best_target else raw_sym
        cat = best_target.get("category", "Aktien") if best_target else ""
        name = best_target.get("name", cell_key) if best_target else cell_key

        if best_target and len(best_bars) >= 30:
            fee_val, slip_val = _fee_slip_for_cat(cat)
            pre = precompute_indicators(best_bars)
            if pre is not None:
                for m_name in ("Long & Short", "Nur Long", "Nur Short"):
                    bt = run_single_backtest(
                        best_bars, mode=m_name, timeframe=tf_norm,
                        fee_pct=fee_val, slippage_pct=slip_val,
                        precomputed=pre, return_trades=True
                    )
                    m_eval = _eval_backtest_metrics(bt)
                    if m_eval:
                        modes_detail[m_name] = m_eval
                        modes_alt_summary[m_name] = {
                            "trades": m_eval["trades"],
                            "pf": m_eval["profit_factor"],
                            "exp": m_eval["expectancy_r"],
                            "oos_t": m_eval["oos_trades"],
                            "oos_r": m_eval["oos_r"],
                            "p": m_eval["p_boot"],
                            "pilot": m_eval["math_pilot_eligible"],
                        }

        cur_metrics = modes_detail.get(cur_mode) or {
            "trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "expectancy_r": 0.0, "total_r": 0.0, "max_dd_pct": 0.0,
            "oos_trades": 0, "oos_wr": 0.0, "oos_r": 0.0, "oos_exp_r": 0.0,
            "p_boot": 1.0, "t_stat": 0.0,
            "math_pilot_eligible": False, "math_shadow_eligible": False,
        }

        cluster = cell.get("cluster") or classify_asset_cluster(raw_sym, cat)
        live_stats = _live_stats_for_symbols(syms, port_closed, shadow_closed=shadow_closed, cell_key=cell_key)

        covered_signatures.add((cell_key, ""))
        if data_sym:
            covered_signatures.add((str(data_sym).upper(), tf_norm))
        for s in syms:
            covered_signatures.add((str(s).upper(), tf_norm))

        existing_cells.append({
            "cell_key": cell_key,
            "is_static_base": is_static,
            "current_tier": cur_tier,
            "symbols": syms,
            "raw_symbol": raw_sym,
            "data_symbol": data_sym,
            "name": name,
            "category": cat,
            "cluster": cluster,
            "timeframe": tf,
            "tf_norm": tf_norm,
            "mode": cur_mode,
            "allowed_directions": dirs,
            "bars": len(best_bars),
            "no_backtest_data": not (best_target and len(best_bars) >= 30 and bool(modes_detail)),
            **cur_metrics,
            **live_stats,
            "modes_alt": modes_alt_summary,
            "_modes_detail": modes_detail,
            "previous_notes": cell.get("notes", ""),
        })

    return existing_cells, covered_signatures


def collect_candidates(covered_signatures: Optional[set] = None) -> List[Dict[str, Any]]:
    from asset_onboarding_evaluator import resolve_asset_target
    from backtest_data_loader import get_cached_bars
    from backtest_matrix_engine import precompute_indicators, run_single_backtest
    from circuit_breaker import classify_asset_cluster

    bulk = _load(BULK_FILE, {})
    onb = _load(ONBOARD_FILE, [])
    covered = covered_signatures or set()

    by_raw: Dict[str, Dict[str, Any]] = {}
    for ev in (bulk.get("results") or []):
        if isinstance(ev, dict) and ev.get("raw_symbol"):
            by_raw[ev["raw_symbol"].upper()] = ev
    for ev in (onb if isinstance(onb, list) else []):
        if isinstance(ev, dict) and ev.get("raw_symbol"):
            rk = ev["raw_symbol"].upper()
            if rk not in by_raw:
                by_raw[rk] = ev

    candidates: List[Dict[str, Any]] = []
    seen_keys = set()
    for raw_sym, ev in sorted(by_raw.items()):
        detailed = ev.get("detailed_results") or {}
        robust_cells = []
        for tf, modes in detailed.items():
            if not isinstance(modes, dict):
                continue
            for mode, res in modes.items():
                if not isinstance(res, dict):
                    continue
                if res.get("verdict") == "ROBUST_EDGE" and (res.get("oos_r") or 0) > 0 and (res.get("oos_trades") or 0) >= 5:
                    robust_cells.append((tf, mode, res))
        if not robust_cells:
            continue

        target = resolve_asset_target(raw_sym)
        if target.get("untestable") or target.get("source") == "none":
            continue
        fee_val, slip_val = _fee_slip_for_cat(target.get("category", "Aktien"))
        cluster = classify_asset_cluster(raw_sym, ev.get("category", ""))

        for tf, mode, _ in robust_cells:
            tf_norm = _norm_tf(tf)
            ck = _make_cell_key(raw_sym, tf, mode)
            if (ck, "") in covered or ck in seen_keys:
                continue
            if (raw_sym.upper(), tf_norm) in covered or (str(target["symbol"]).upper(), tf_norm) in covered:
                continue

            bars = get_cached_bars(target, interval=tf)
            pre = precompute_indicators(bars)
            if pre is None:
                continue
            bt = run_single_backtest(
                bars, mode=mode, timeframe=tf,
                fee_pct=fee_val, slippage_pct=slip_val,
                precomputed=pre, return_trades=True
            )
            if not bt or bt["trades"] < 15:
                continue
            m_eval = _eval_backtest_metrics(bt)
            if not m_eval or not m_eval["math_shadow_eligible"]:
                continue

            seen_keys.add(ck)
            candidates.append({
                "cell_key": ck,
                "raw_symbol": raw_sym,
                "data_symbol": target["symbol"],
                "name": ev.get("name") or target.get("name") or raw_sym,
                "category": ev.get("category") or target.get("category") or "",
                "cluster": cluster,
                "timeframe": tf,
                "mode": mode,
                "allowed_directions": _allowed_dirs_from_mode(mode),
                "bars": len(bars),
                **m_eval,
                "asset_total_r_all_combos": ev.get("total_r", 0.0),
            })

    candidates.sort(key=lambda c: (not c["math_pilot_eligible"], c["p_boot"], -c["oos_r"]))
    return candidates


def _strip_internal(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned = []
    for r in rows:
        cleaned.append({k: v for k, v in r.items() if not str(k).startswith("_")})
    return cleaned


def evaluate_with_opus(candidates: List[Dict[str, Any]], existing_cells: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not os.path.exists(CLAUDE_BIN):
        raise RuntimeError(f"Claude CLI nicht gefunden unter {CLAUDE_BIN}")

    existing_clean = _strip_internal(existing_cells)
    cands_clean = _strip_internal(candidates)

    prompt = f"""Du bist Claude Opus 5.5, quantitativer Chef-Auditor des Trading-Systems.
Du führst heute das BIDIREKTIONALE wöchentliche Audit der TRIAD_WHITELIST durch:
Teil 1: Prüfe ALLE bestehenden Whitelist-Zellen (statische Altlasten + bestehende dynamische Zellen) anhand der neuesten tiefen Historien-Backtests (`bars`) & Live/Paper-Daten -> Upgrades (`SHADOW_PAPER -> PILOT_LIVE`), Downgrades (`PILOT_LIVE -> SHADOW_PAPER`), Direction-Locks (`modes_alt` vergleichen!) oder Deaktivierung (`REJECTED` bei klar negativem Drift/Edge-Verfall).
Teil 2: Prüfe ALLE neuen Backtest-Kandidaten für eine mögliche Aufnahme.

BESTEHENDE WHITELIST-ZELLEN (inkl. `modes_alt` zum Vergleich Long&Short vs Nur Long vs Nur Short):
{json.dumps(existing_clean, ensure_ascii=False, indent=2)}

NEUE KANDIDATEN AUS DEM TIEFEN MATRIX-BACKTEST (bereits durch Python-Vorfilter auf >=15 Trades, OOS>0, p_boot<0.12 geprüft):
{json.dumps(cands_clean, ensure_ascii=False, indent=2)}

BEWERTUNGSREGELN (STRIKT EINHALTEN):
1. "PILOT_LIVE" (0.15% Echtgeld-Risiko) darfst du NUR vergeben, wenn für die gewählten `allowed_directions` gilt: `math_pilot_eligible == true` (TR>=30, OOS>=10, PF>=1.35, Exp>=0.15R, OOS_Exp>=0.10R, p<0.05, t>=1.60, DD<=25%) UND die Kausalität überzeugt.
2. Wenn eine bestehende `PILOT_LIVE`-Zelle auf tiefer Historie `math_pilot_eligible == false` ist, stufe sie auf "SHADOW_PAPER" herunter (oder auf "REJECTED", falls PF < 1.0 / stark negative Expectancy wie NEAR_1H / AVAX_1H).
3. STUFENLEITER FÜR SHADOW -> PILOT BEFÖRDERUNG (verbindlich vorab festgelegt):
   - Ab >= 15 sauberen `shadow_paper_trades` mit `shadow_paper_ci95_low >= -0.05` (kein Widerspruch zum Backtest) -> Hochstufung auf `PILOT_LIVE` (mit 0.25x Pilot-Größe) prüfen.
   - Ab >= 30 `shadow_paper_trades` mit `shadow_paper_ci95_low >= 0.0` -> volle 1.0x Pilot-Größe.
   - `stalled_90d == true` (< 3 Signale nach >= 90 Tagen) -> prüfen, ob Regime-Filter pausiert oder Signal tot ist (ggf. absetzen).
4. Nutze `modes_alt`: Falls nur eine Richtung stark positiv ist (z.B. Long&Short schwach, Nur Short stark), enge `allowed_directions` gezielt ein!
5. Bei mehreren Zeitrahmen desselben Symbols nur die stärksten 1-2 Zellen freigeben; auf Diversifikation (Aktien, Rohstoffe, FX, Krypto) achten.

Antworte AUSSCHLIESSLICH mit einem validen JSON-Objekt genau in diesem Schema (keine Markdown-Prosa außerhalb des JSON):
{{
  "summary": "Kurze Gesamteinschätzung in 2-4 Sätzen",
  "existing_decisions": [
    {{
      "cell_key": "exakter cell_key aus EXISTING",
      "decision": "PILOT_LIVE" | "SHADOW_PAPER" | "REJECTED",
      "allowed_directions": ["LONG", "SHORT"] | ["LONG"] | ["SHORT"],
      "reason": "knappe quantitative & kausale Begründung (1-2 Sätze)"
    }}
  ],
  "new_decisions": [
    {{
      "cell_key": "exakter cell_key aus NEW_CANDIDATES",
      "raw_symbol": "exaktes raw_symbol",
      "decision": "PILOT_LIVE" | "SHADOW_PAPER" | "REJECTED",
      "allowed_directions": ["LONG", "SHORT"] | ["LONG"] | ["SHORT"],
      "reason": "knappe quantitative & kausale Begründung (1-2 Sätze)"
    }}
  ]
}}
"""
    cmd = [CLAUDE_BIN, "-p", "--model", "opus", "--effort", "high", prompt]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

    if proc.returncode != 0 and not out:
        raise RuntimeError(f"Claude Opus CLI Fehler (rc={proc.returncode}): {err[:300]}")
    if "limit" in out.lower() and "decision" not in out.lower():
        raise RuntimeError(f"Claude Opus Quota/Limit: {out[:300]}")

    m = re.search(r"\{.*\}", out, re.DOTALL)
    if not m:
        raise RuntimeError(f"Kein JSON in Opus-Antwort gefunden: {out[:400]}")
    return json.loads(m.group(0))


def _apply_cell_guardrails(
    cell: Dict[str, Any],
    dec_row: Dict[str, Any],
    pilot_total_ref: List[int],
    pilot_by_cluster: Dict[str, int],
    sec_bull: set,
) -> Tuple[str, List[str], List[str], Dict[str, Any]]:
    req_dec = str(dec_row.get("decision") or "REJECTED").upper().strip()
    if req_dec not in ("PILOT_LIVE", "SHADOW_PAPER", "REJECTED"):
        req_dec = "REJECTED"

    req_dirs = dec_row.get("allowed_directions") or cell.get("allowed_directions") or ["LONG", "SHORT"]
    req_dirs = [str(d).upper() for d in req_dirs if str(d).upper() in ("LONG", "SHORT")]
    if not req_dirs:
        req_dirs = list(cell.get("allowed_directions") or ["LONG", "SHORT"])
    sel_mode = _mode_from_allowed_dirs(req_dirs)

    # Wähle passende Kennzahlen falls Opus die Richtung angepasst hat
    eff_metrics = cell
    modes_detail = cell.get("_modes_detail") or {}
    if sel_mode in modes_detail:
        eff_metrics = {**cell, **modes_detail[sel_mode]}

    final_dec = req_dec
    guard_notes: List[str] = []

    raw_sym = str(cell.get("raw_symbol", ""))
    data_sym = str(cell.get("data_symbol", ""))
    raw_ticker = re.sub(r"[^A-Z]", "", raw_sym.split(":")[-1].upper())
    data_ticker = re.sub(r"[^A-Z]", "", data_sym.split(".")[0].upper())
    tf_low = str(cell.get("timeframe", "")).lower()

    # Leitplanke 2: Säkulare Bull-Aktien niemals SHORT auf 1d/3d/1w
    if (raw_ticker in sec_bull or data_ticker in sec_bull) and "SHORT" in req_dirs and tf_low in ("1d", "3d", "1w"):
        if req_dirs == ["SHORT"]:
            final_dec = "REJECTED"
            guard_notes.append("Drift-Sperre: Short auf Megacap-Tech im HTF verboten")
        else:
            req_dirs = ["LONG"]
            guard_notes.append("Drift-Sperre: SHORT entfernt (HTF Megacap-Tech)")

    # Leitplanke 1: PILOT_LIVE nur mit erfülltem harten Mathe-Gate
    if final_dec == "PILOT_LIVE" and not eff_metrics.get("math_pilot_eligible", False):
        final_dec = "SHADOW_PAPER"
        guard_notes.append(
            f"Auto-Downgrade auf SHADOW_PAPER (trades={eff_metrics.get('trades', 0)}, "
            f"oos={eff_metrics.get('oos_trades', 0)}, pf={eff_metrics.get('profit_factor', 0)}, "
            f"p={eff_metrics.get('p_boot', 1.0)}, t={eff_metrics.get('t_stat', 0)})"
        )

    # Leitplanke 3: Cluster-Cap (max 5/Cluster) & Gesamt-Cap (max 15 PILOT_LIVE)
    cl = str(cell.get("cluster") or "OTHER")
    if final_dec == "PILOT_LIVE":
        if pilot_total_ref[0] >= 15 or pilot_by_cluster.get(cl, 0) >= 5:
            final_dec = "SHADOW_PAPER"
            guard_notes.append(f"Cluster-/Gesamt-Cap erreicht ({cl}: {pilot_by_cluster.get(cl, 0)}/5, gesamt: {pilot_total_ref[0]}/15)")
        else:
            pilot_total_ref[0] += 1
            pilot_by_cluster[cl] = pilot_by_cluster.get(cl, 0) + 1

    return final_dec, req_dirs, guard_notes, eff_metrics


def apply_guardrails(
    candidates: List[Dict[str, Any]],
    existing_cells: List[Dict[str, Any]],
    opus_out: Dict[str, Any],
) -> Dict[str, Any]:
    from circuit_breaker import SECULAR_BULL_TICKERS, _STATIC_WHITELIST_BASE

    exist_map = {c["cell_key"]: c for c in existing_cells}
    cand_map = {c["cell_key"]: c for c in candidates}

    existing_decisions = opus_out.get("existing_decisions") or []
    new_decisions = opus_out.get("new_decisions") or opus_out.get("decisions") or []

    # Für bestehende Zellen ohne explizite Opus-Antwort konservativ aktuellen Status als Default behalten
    exist_dec_map = {d.get("cell_key"): d for d in existing_decisions if isinstance(d, dict) and d.get("cell_key")}
    for c in existing_cells:
        if c["cell_key"] not in exist_dec_map:
            fallback_tier = c.get("current_tier", "SHADOW_PAPER")
            if fallback_tier == "DISABLED":
                fallback_tier = "REJECTED"
            exist_dec_map[c["cell_key"]] = {
                "cell_key": c["cell_key"],
                "decision": fallback_tier,
                "allowed_directions": c.get("allowed_directions", ["LONG", "SHORT"]),
                "reason": "Keine Änderung durch Opus gemeldet (Mathe-Gate geprüft).",
            }

    pilot_total_ref = [0]
    pilot_by_cluster: Dict[str, int] = {}
    dynamic_entries: Dict[str, Any] = {}
    disabled_keys: List[str] = []
    audit_rows: List[Dict[str, Any]] = []

    # Bestehende Zellen zuerst (PILOT_LIVE-Kandidaten zuerst nach Qualität sortiert)
    ordered_existing = sorted(
        existing_cells,
        key=lambda c: (
            exist_dec_map.get(c["cell_key"], {}).get("decision") != "PILOT_LIVE",
            c.get("p_boot", 1.0),
            -float(c.get("oos_r", 0.0)),
        ),
    )

    for c in ordered_existing:
        ck = c["cell_key"]
        d = exist_dec_map[ck]
        final_dec, final_dirs, guard_notes, eff = _apply_cell_guardrails(
            c, d, pilot_total_ref, pilot_by_cluster, SECULAR_BULL_TICKERS
        )
        prev_tier = c.get("current_tier", "SHADOW_PAPER")
        tier_changed = (final_dec != prev_tier) or (final_dirs != c.get("allowed_directions"))

        row_clean = {k: v for k, v in eff.items() if not str(k).startswith("_") and k != "modes_alt"}
        audit_rows.append({
            **row_clean,
            "audit_scope": "EXISTING",
            "previous_tier": prev_tier,
            "opus_decision": str(d.get("decision") or "REJECTED").upper(),
            "final_decision": final_dec,
            "final_directions": final_dirs,
            "tier_changed": tier_changed,
            "opus_reason": d.get("reason", ""),
            "guardrail_notes": guard_notes,
        })

        if final_dec in ("PILOT_LIVE", "SHADOW_PAPER"):
            sym_list = list(dict.fromkeys([str(s) for s in (c.get("symbols") or [c["raw_symbol"], c["data_symbol"]])]))
            note = (
                f"Opus 5.5 Audit ({final_dec}): TR={eff.get('trades', 0)}, OOS={eff.get('oos_trades', 0)} "
                f"({float(eff.get('oos_r', 0)):+.1f}R), PF={eff.get('profit_factor', 0)}, "
                f"p={eff.get('p_boot', 1.0)}, t={eff.get('t_stat', 0)}. {d.get('reason', '')}"
            )
            static_base = _STATIC_WHITELIST_BASE.get(ck)
            differs_from_static = (
                static_base is None
                or final_dec != static_base.get("tier")
                or final_dirs != [str(x).upper() for x in (static_base.get("allowed_directions") or [])]
            )
            if differs_from_static:
                dynamic_entries[ck] = {
                    "symbols": sym_list,
                    "timeframe": c["timeframe"],
                    "allowed_directions": final_dirs,
                    "tier": final_dec,
                    "risk_pct": 0.15 if final_dec == "PILOT_LIVE" else 0.0,
                    "max_risk_cash": 15.0 if final_dec == "PILOT_LIVE" else 0.0,
                    "cluster": c["cluster"],
                    "notes": note[:320],
                }
        else:
            if ck in _STATIC_WHITELIST_BASE:
                disabled_keys.append(ck)

    # Neue Kandidaten verarbeiten
    seen_new = set()
    for d in new_decisions:
        if not isinstance(d, dict):
            continue
        ck = d.get("cell_key")
        c = cand_map.get(ck)
        if not c or ck in seen_new or ck in exist_map:
            continue
        seen_new.add(ck)

        final_dec, final_dirs, guard_notes, eff = _apply_cell_guardrails(
            c, d, pilot_total_ref, pilot_by_cluster, SECULAR_BULL_TICKERS
        )
        audit_rows.append({
            **eff,
            "audit_scope": "NEW",
            "previous_tier": "NONE",
            "opus_decision": str(d.get("decision") or "REJECTED").upper(),
            "final_decision": final_dec,
            "final_directions": final_dirs,
            "tier_changed": final_dec != "REJECTED",
            "opus_reason": d.get("reason", ""),
            "guardrail_notes": guard_notes,
        })

        if final_dec in ("PILOT_LIVE", "SHADOW_PAPER"):
            sym_list = sorted({c["raw_symbol"], c["data_symbol"], c["raw_symbol"].split(":")[-1]})
            note = (
                f"Opus 5.5 Audit ({final_dec}): TR={eff['trades']}, OOS={eff['oos_trades']} ({eff['oos_r']:+.1f}R), "
                f"PF={eff['profit_factor']}, p={eff['p_boot']}, t={eff['t_stat']}. {d.get('reason', '')}"
            )
            dynamic_entries[ck] = {
                "symbols": sym_list,
                "timeframe": c["timeframe"],
                "allowed_directions": final_dirs,
                "tier": final_dec,
                "risk_pct": 0.15 if final_dec == "PILOT_LIVE" else 0.0,
                "max_risk_cash": 15.0 if final_dec == "PILOT_LIVE" else 0.0,
                "cluster": c["cluster"],
                "notes": note[:320],
            }

    return {
        "entries": dynamic_entries,
        "disabled_keys": sorted(set(disabled_keys)),
        "audit_rows": audit_rows,
        "summary": opus_out.get("summary", ""),
    }


def _deduplicate_learnings(learnings: List[Dict[str, Any]], max_keep: int = 60) -> List[Dict[str, Any]]:
    """Entfernt doppelte/redundante Lerneinträge unter Erhalt der neuesten & Opus-Einträge."""
    seen = set()
    unique: List[Dict[str, Any]] = []
    for l in learnings:
        if not isinstance(l, dict):
            continue
        ai_pm = l.get("ai_post_mortem") or {}
        rule_txt = str(ai_pm.get("actionable_rule") or l.get("text") or "").strip().lower()
        rule_norm = re.sub(r"\s+", " ", rule_txt)[:140]
        sym = str(l.get("symbol") or "").upper()
        key = (sym, rule_norm) if sym in ("SYSTEM-AXIOM", "MULTI-ASSET") else (str(l.get("trade_id") or ""), sym, rule_norm)
        if key in seen:
            continue
        seen.add(key)
        unique.append(l)
        if len(unique) >= max_keep:
            break
    return unique


def run_opus_memory_synthesis(apply: bool = True) -> Dict[str, Any]:
    """
    Vorschlag B: Wöchentliche Gedächtnis-Synthese durch Claude Opus 5.5.
    - Dedupliziert learnings in trade_memory.json
    - Destilliert Top 8–10 Master-Constitution Axiome
    - Generiert maschinenlesbare, hart geclampte Steuerparameter in opus_governor_params.json
    """
    if not os.path.exists(CLAUDE_BIN):
        raise RuntimeError(f"Claude CLI nicht gefunden unter {CLAUDE_BIN}")

    memory = _load(TRADE_MEMORY_FILE, {"updated_at": "", "total_experience_records": 0, "learnings": []})
    portfolio = _load(PORTFOLIO_FILE, {})
    incubator = _load(INCUBATOR_FILE, {})

    raw_learnings = [
        l for l in (memory.get("learnings") or [])
        if str(l.get("scope", "")).upper() != "INCUBATOR"
        and str(l.get("source_book", "")).upper() != "INCUBATOR_RESEARCH"
    ]
    dedup_learnings = _deduplicate_learnings(raw_learnings, max_keep=60)

    compact_learnings = []
    for l in dedup_learnings[:40]:
        ai_pm = l.get("ai_post_mortem") or {}
        compact_learnings.append({
            "symbol": l.get("symbol"),
            "category": l.get("category"),
            "direction": l.get("direction"),
            "result": l.get("result"),
            "setup_name": l.get("setup_name"),
            "pnl_lev": l.get("pnl_leveraged"),
            "driver": ai_pm.get("driver", ""),
            "rule": ai_pm.get("actionable_rule") or l.get("text", ""),
        })

    prompt = f"""Du bist Claude Opus 5.5, der Chef-Architekt des quantitativen Closed-Loop-Handelsgedächtnisses.
Vor dir liegen die aggregierten Performance-Daten des echten High-Conviction KI-Portfolios, des Micro-Inkubators sowie die destillierten Trade-Learnings.

PORTFOLIO-METRIKEN:
{json.dumps(portfolio.get("metrics", {}), ensure_ascii=False, indent=2)}

INKUBATOR-METRIKEN:
{json.dumps(incubator.get("metrics", {}), ensure_ascii=False, indent=2)}

SETUP- & SEKTOR-SCORECARD:
{json.dumps({"setup_performance": memory.get("setup_performance", {}), "category_performance": memory.get("category_performance", {})}, ensure_ascii=False, indent=2)}

AKTUELLE PARAMETER (Vorwoche / Baseline):
{json.dumps(DEFAULT_GOVERNOR_PARAMS, ensure_ascii=False, indent=2)}

LETZTE TRADE-LEARNINGS (aus Post-Mortems & Cross-Market-Synthesen):
{json.dumps(compact_learnings, ensure_ascii=False, indent=2)}

DEINE AUFGABE:
1. Destilliere genau 8 bis 10 widerspruchsfreie, präzise Master-Constitution Axiome ("master_constitution"), die das System als eiserne Leitlinien nutzt.
2. Kalibriere auf Basis der empirischen Ergebnisse die quantitativen Code-Steuerparameter ("governor_params") innerhalb seriöser Grenzen:
   - min_score_default [86..92]
   - min_score_counter_trend [92..96]
   - min_vsa_ratio_reversal [1.10..1.60]
   - max_rsi_long_entry [58.0..70.0]
   - min_rsi_short_entry [30.0..42.0]
   - max_holding_days_fast_swing [2.0..6.0]
   - max_holding_days_core_swing [7.0..21.0]
   - max_holding_days_macro_trend [21.0..60.0]
   - stagnation_profit_lock_days [7.0..20.0]
   - incubator_time_stop_hours: {{"5m": [6..18], "15m": [12..36], "30m": [18..48]}}
   - sector_score_adjustments: Map Kategorie -> Int [-2..+4]

Antworte AUSSCHLIESSLICH mit einem validen JSON-Objekt:
{{
  "synthesis_summary": "Prägnante Zusammenfassung der wichtigsten Lehren (2-3 Sätze)",
  "master_constitution": [
    {{
      "id": "AX-01",
      "scope": "ALL" | "PORTFOLIO" | "INCUBATOR",
      "rule": "Unmissverständliche, knappe Handelsregel",
      "rationale": "Kurze empirische Begründung (1 Satz)"
    }}
  ],
  "governor_params": {{
    "min_score_default": 88,
    "min_score_counter_trend": 94,
    "min_vsa_ratio_reversal": 1.20,
    "max_rsi_long_entry": 64.0,
    "min_rsi_short_entry": 36.0,
    "max_holding_days_fast_swing": 4.0,
    "max_holding_days_core_swing": 14.0,
    "max_holding_days_macro_trend": 45.0,
    "stagnation_profit_lock_days": 12.0,
    "incubator_time_stop_hours": {{"5m": 12.0, "15m": 18.0, "30m": 24.0}},
    "sector_score_adjustments": {{}}
  }}
}}
"""
    cmd = [CLAUDE_BIN, "-p", "--model", "opus", "--effort", "high", prompt]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

    if proc.returncode != 0 and not out:
        raise RuntimeError(f"Opus Memory-Synthese CLI Fehler (rc={proc.returncode}): {err[:300]}")
    if "limit" in out.lower() and "governor_params" not in out.lower():
        raise RuntimeError(f"Opus Memory-Synthese Quota/Limit: {out[:300]}")

    m = re.search(r"\{.*\}", out, re.DOTALL)
    if not m:
        raise RuntimeError(f"Kein JSON in Opus Memory-Synthese gefunden: {out[:400]}")
    raw_out = json.loads(m.group(0))

    gp_in = raw_out.get("governor_params") or {}
    inc_ts_in = gp_in.get("incubator_time_stop_hours") or {}
    sec_adj_in = gp_in.get("sector_score_adjustments") or {}

    sec_adj_clean: Dict[str, int] = {}
    if isinstance(sec_adj_in, dict):
        for k, v in sec_adj_in.items():
            if k:
                sec_adj_clean[str(k)] = _clamp(v, -2, 4, 0, as_int=True)

    clamped_params = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "auditor": "Claude Opus 5.5 (High Effort)",
        "synthesis_summary": str(raw_out.get("synthesis_summary", "")).strip(),
        "min_score_default": _clamp(gp_in.get("min_score_default"), 86, 92, 88, as_int=True),
        "min_score_counter_trend": _clamp(gp_in.get("min_score_counter_trend"), 92, 96, 94, as_int=True),
        "min_vsa_ratio_reversal": _clamp(gp_in.get("min_vsa_ratio_reversal"), 1.10, 1.60, 1.20),
        "max_rsi_long_entry": _clamp(gp_in.get("max_rsi_long_entry"), 58.0, 70.0, 64.0),
        "min_rsi_short_entry": _clamp(gp_in.get("min_rsi_short_entry"), 30.0, 42.0, 36.0),
        "max_holding_days_fast_swing": _clamp(gp_in.get("max_holding_days_fast_swing"), 2.0, 6.0, 4.0),
        "max_holding_days_core_swing": _clamp(gp_in.get("max_holding_days_core_swing"), 7.0, 21.0, 14.0),
        "max_holding_days_macro_trend": _clamp(gp_in.get("max_holding_days_macro_trend"), 21.0, 60.0, 45.0),
        "stagnation_profit_lock_days": _clamp(gp_in.get("stagnation_profit_lock_days"), 7.0, 20.0, 12.0),
        "incubator_time_stop_hours": {
            "5m": _clamp(inc_ts_in.get("5m"), 6.0, 18.0, 12.0),
            "15m": _clamp(inc_ts_in.get("15m"), 12.0, 36.0, 18.0),
            "30m": _clamp(inc_ts_in.get("30m"), 18.0, 48.0, 24.0),
        },
        "sector_score_adjustments": sec_adj_clean,
    }

    constitution = []
    for idx, ax in enumerate(raw_out.get("master_constitution") or [], 1):
        if isinstance(ax, dict) and ax.get("rule"):
            constitution.append({
                "id": str(ax.get("id") or f"AX-{idx:02d}"),
                "scope": str(ax.get("scope") or "ALL").upper(),
                "rule": str(ax.get("rule")).strip(),
                "rationale": str(ax.get("rationale", "")).strip(),
            })

    if apply:
        _save_atomic(GOVERNOR_PARAMS_FILE, clamped_params)
        memory["learnings"] = dedup_learnings
        memory["total_experience_records"] = len(dedup_learnings)
        memory["master_constitution"] = constitution
        memory["opus_synthesis_summary"] = clamped_params["synthesis_summary"]
        memory["opus_synthesis_updated_at"] = clamped_params["updated_at"]
        memory["updated_at"] = clamped_params["updated_at"]
        _save_atomic(TRADE_MEMORY_FILE, memory)

    return {
        "governor_params": clamped_params,
        "master_constitution": constitution,
        "dedup_before": len(raw_learnings),
        "dedup_after": len(dedup_learnings),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Speichert dynamische Whitelist & Opus-Governor-Parameter")
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--skip-memory", action="store_true", help="Überspringt die wöchentliche Memory-Synthese")
    args = ap.parse_args()

    from circuit_breaker import load_dynamic_triad_whitelist, TRIAD_WHITELIST

    print("📐 Stufe 1: Auditiere bestehende Whitelist-Zellen & sammle Backtest-Kandidaten...", flush=True)
    existing_cells, covered = collect_existing_whitelist_cells()
    candidates = collect_candidates(covered_signatures=covered)
    pilot_math_new = sum(1 for c in candidates if c["math_pilot_eligible"])
    pilot_math_ex = sum(1 for c in existing_cells if c["math_pilot_eligible"])
    print(
        f"   Bestehende Zellen: {len(existing_cells)} (Mathe-Pilot: {pilot_math_ex}) | "
        f"Neue Kandidaten: {len(candidates)} (Mathe-Pilot: {pilot_math_new})",
        flush=True,
    )

    print("🏛️ Stufe 2: Starte Claude Opus 5.5 (--effort high) Bidirektionales Whitelist-Audit...", flush=True)
    opus_out = evaluate_with_opus(candidates, existing_cells)

    print("🛡️ Stufe 3: Wende harte mathematische Leitplanken & Cluster-Caps an...", flush=True)
    res = apply_guardrails(candidates, existing_cells, opus_out)
    entries = res["entries"]
    disabled_keys = res["disabled_keys"]
    rows = res["audit_rows"]

    pilots = [r for r in rows if r["final_decision"] == "PILOT_LIVE"]
    shadows = [r for r in rows if r["final_decision"] == "SHADOW_PAPER"]
    rejected = [r for r in rows if r["final_decision"] == "REJECTED"]
    changed = [r for r in rows if r.get("audit_scope") == "EXISTING" and r.get("tier_changed")]

    print(
        f"   Ergebnis Gesamt: PILOT_LIVE={len(pilots)} | SHADOW_PAPER={len(shadows)} | "
        f"REJECTED={len(rejected)} | Bestehende geändert={len(changed)}",
        flush=True,
    )

    report = {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "applied": bool(args.apply),
        "existing_total": len(existing_cells),
        "candidates_total": len(candidates),
        "math_pilot_eligible": pilot_math_ex + pilot_math_new,
        "counts": {"PILOT_LIVE": len(pilots), "SHADOW_PAPER": len(shadows), "REJECTED": len(rejected)},
        "disabled_keys": disabled_keys,
        "existing_changes_count": len(changed),
        "summary": res["summary"],
        "decisions": rows,
    }
    _save_atomic(AUDIT_REPORT_FILE, report)

    if args.apply:
        if DYN_WL_FILE.exists():
            shutil.copy2(DYN_WL_FILE, KB_DIR / "triad_whitelist_dynamic.json.bak")
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "auditor": "Claude Opus 5.5 (High Effort) + Python Math-Guardrails (Bidirektional)",
            "disabled_keys": disabled_keys,
            "entries": entries,
        }
        _save_atomic(DYN_WL_FILE, payload)
        loaded = load_dynamic_triad_whitelist(force=True)
        print(f"💾 triad_whitelist_dynamic.json gespeichert ({loaded} Overrides/Erweiterungen, {len(TRIAD_WHITELIST)} aktive Zellen gesamt).", flush=True)

    mem_res = None
    if not args.skip_memory:
        print("🧠 Stufe 4: Starte Wöchentliche Gedächtnis-Synthese (Opus Master-Constitution & Quant-Governor)...", flush=True)
        mem_res = run_opus_memory_synthesis(apply=bool(args.apply))
        print(
            f"   ✅ {len(mem_res['master_constitution'])} Master-Axiome destilliert | "
            f"Learnings dedupliziert ({mem_res['dedup_before']} -> {mem_res['dedup_after']}) | "
            f"Governor-Parameter kalibriert.",
            flush=True,
        )

    if args.apply and not args.no_notify:
        try:
            from notifications import send_telegram_alert
            lines = [
                "🏛️ <b>Claude Opus 5.5 Wochen-Audit abgeschlossen</b>",
                "━━━━━━━━━━━━━━━━━━━━━━",
                f"Bestehende Zellen: {len(existing_cells)} (geändert: {len(changed)}) | Neue Kandidaten: {len(candidates)}",
                f"🟢 <b>PILOT_LIVE:</b> {len(pilots)} | 🟡 <b>SHADOW_PAPER:</b> {len(shadows)} | ⚪ <b>REJECTED:</b> {len(rejected)}",
            ]
            if changed:
                lines.append("\n🔄 <b>Status-Änderungen bestehender Zellen:</b>")
                for c in changed[:6]:
                    lines.append(f"  • <b>{c['cell_key']}</b>: {c['previous_tier']} ➔ {c['final_decision']} (PF {c['profit_factor']}, OOS {c['oos_r']:+.1f}R)")
            new_pilots = [p for p in pilots if p.get("audit_scope") == "NEW"]
            if new_pilots:
                lines.append("\n⭐ <b>Neu in PILOT_LIVE:</b>")
                for p in new_pilots[:6]:
                    lines.append(f"  • <b>{p['name']}</b> ({p['timeframe']} {p['mode']}): PF {p['profit_factor']} | OOS {p['oos_r']:+.1f}R | p={p['p_boot']}")
            if mem_res:
                lines.append(f"\n🧠 <b>Memory-Synthese:</b> {len(mem_res['master_constitution'])} Master-Axiome &amp; Quant-Governor aktualisiert.")
            if res["summary"]:
                lines.append(f"\n💡 <i>{res['summary'][:300]}</i>")
            send_telegram_alert("\n".join(lines))
        except Exception as e:
            print(f"Hinweis Telegram-Versand: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
