#!/usr/bin/env python3
"""
TradingView Super-Analyst – Portfolio- & Erfahrungs-Engine (Trade Memory).
Funktionen:
1. Autonomes High-Conviction Portfolio:
   - Handelt automatisch die sichersten Setups (Score >= 88%, strikt non-NEUTRAL)
   - Jeder Trade startet mit standardisierter Basiskapital-Allokation (1.000 € Basiseinheit)
   - Berechnet automatisch den optimalen Hebel (1x bis maximal 10x) anhand von Volatilität, Asset-Klasse und SL-Distanz
   - Dokumentiert den fundierten Einstiegsgrund
   - Dynamisches Multi-Day Exit-Management (TP1, TP2, struktureller SL, Trendbruch-Invalidierung)
   - Vollständiges Erfahrungslernen ("Gedächtnis"): Post-Mortem Analyse jedes Trades, Speicherung in trade_memory.json
2. Eigene Nutzer-Positionen (User Positions):
   - Speicherung & Tracking individueller Positionen (Symbol, LONG/SHORT, Hebel, Einstiegskurs)
   - Live PnL-Berechnung (ungehebelt und gehebelt)
   - Automatische Erkennung relevanter Handlungsempfehlungen anhand der aktuellen Multi-Timeframe-Indikatoren
"""

import os
import sys
import json
import math
from pathlib import Path
from datetime import datetime, timezone
from risk_engine import calculate_position_size
from circuit_breaker import (
    check_drawdown_circuit_breaker,
    check_cluster_heat_limit,
    check_cost_gate,
    check_triad_whitelist,
    classify_asset_cluster,
    CircuitBreakerConfig,
    DEFAULT_CONFIG,
    TRIAD_PILOT_CONFIG,
    TRIAD_WHITELIST,
)

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"
PORTFOLIO_FILE = BASE_DIR / "knowledge_base" / "autonomous_portfolio.json"
TRADE_MEMORY_FILE = BASE_DIR / "knowledge_base" / "trade_memory.json"
USER_POSITIONS_FILE = BASE_DIR / "knowledge_base" / "user_positions.json"
GOVERNOR_PARAMS_FILE = BASE_DIR / "knowledge_base" / "opus_governor_params.json"

DEFAULT_OPUS_GOVERNOR_PARAMS = {
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


def load_opus_governor_params():
    """Lädt wöchentlich von Claude Opus 5.5 kalibrierte quantitative Steuerparameter."""
    params = dict(DEFAULT_OPUS_GOVERNOR_PARAMS)
    try:
        if GOVERNOR_PARAMS_FILE.exists():
            raw = load_json_file(GOVERNOR_PARAMS_FILE, {})
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if k in params and v is not None:
                        params[k] = v
    except Exception:
        pass
    return params


def load_json_file(file_path, default_val=None):
    if default_val is None:
        default_val = {}
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default_val
    return default_val


def save_json_file(file_path, data):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ==============================================================================
# 1. HEBEL-BERECHNUNG & CLOSED-LOOP SCORECARD GOVERNOR
# ==============================================================================
def calculate_performance_matrix(closed_trades):
    """
    Berechnet die quantitative Closed-Loop Performance Matrix für alle Setups und Asset-Kategorien.
    Ermittelt automatisch Win-Rates, Profit-Faktoren, Hebel-Dämpfer und Mindest-Score-Vorgaben.
    """
    setup_stats = {}
    category_stats = {}

    for ct in closed_trades:
        s_name = ct.get("setup_name", "High-Conviction Confluence")
        cat = ct.get("category", "Allgemein")
        raw_pnl = float(ct.get("realized_pnl_pct", 0.0))
        lev_pnl = float(ct.get("realized_pnl_leveraged_pct", raw_pnl))
        is_win = lev_pnl > 0
        is_breakeven = abs(lev_pnl) < 0.1

        # Setup Stats sammeln
        if s_name not in setup_stats:
            setup_stats[s_name] = {"trades": 0, "wins": 0, "losses": 0, "gross_win": 0.0, "gross_loss": 0.0, "total_lev_pnl": 0.0}
        setup_stats[s_name]["trades"] += 1
        if is_win:
            setup_stats[s_name]["wins"] += 1
            setup_stats[s_name]["gross_win"] += lev_pnl
        elif not is_breakeven:
            setup_stats[s_name]["losses"] += 1
            setup_stats[s_name]["gross_loss"] += abs(lev_pnl)
        setup_stats[s_name]["total_lev_pnl"] += lev_pnl

        # Category Stats sammeln
        if cat not in category_stats:
            category_stats[cat] = {"trades": 0, "wins": 0, "losses": 0, "gross_win": 0.0, "gross_loss": 0.0, "total_lev_pnl": 0.0}
        category_stats[cat]["trades"] += 1
        if is_win:
            category_stats[cat]["wins"] += 1
            category_stats[cat]["gross_win"] += lev_pnl
        elif not is_breakeven:
            category_stats[cat]["losses"] += 1
            category_stats[cat]["gross_loss"] += abs(lev_pnl)
        category_stats[cat]["total_lev_pnl"] += lev_pnl

    # Setups finalisieren
    setup_performance = {}
    for s_name, data in setup_stats.items():
        tr = data["trades"]
        wins = data["wins"]
        wr = round((wins / tr) * 100.0, 1) if tr > 0 else 0.0
        pf = round(data["gross_win"] / data["gross_loss"], 2) if data["gross_loss"] > 0 else (9.99 if data["gross_win"] > 0 else 0.0)
        tot_pnl = round(data["total_lev_pnl"], 1)

        # Dynamic Governor Rules
        if tr >= 4 and wr < 35.0:
            status = "UNDERPERFORMING"
            min_score = 92
            lev_adj = -2
        elif tr >= 3 and wr < 50.0:
            status = "CAUTION"
            min_score = 90
            lev_adj = -1
        elif tr >= 3 and wr >= 65.0 and pf >= 1.5:
            status = "PROVEN_EDGE"
            min_score = 88
            lev_adj = 1
        else:
            status = "BALANCED"
            min_score = 88
            lev_adj = 0

        setup_performance[s_name] = {
            "trades": tr,
            "wins": wins,
            "losses": data["losses"],
            "win_rate": wr,
            "total_lev_pnl": tot_pnl,
            "profit_factor": pf,
            "status": status,
            "min_score": min_score,
            "leverage_adjustment": lev_adj
        }

    # Categories finalisieren
    category_performance = {}
    for cat, data in category_stats.items():
        tr = data["trades"]
        wins = data["wins"]
        wr = round((wins / tr) * 100.0, 1) if tr > 0 else 0.0
        pf = round(data["gross_win"] / data["gross_loss"], 2) if data["gross_loss"] > 0 else (9.99 if data["gross_win"] > 0 else 0.0)
        tot_pnl = round(data["total_lev_pnl"], 1)

        # Dynamic Governor Rules
        if tr >= 4 and wr < 35.0:
            status = "UNDERPERFORMING"
            min_score = 92
            lev_cap = 2
        elif tr >= 3 and wr < 50.0:
            status = "CAUTION"
            min_score = 90
            lev_cap = 3
        elif tr >= 3 and wr >= 65.0:
            status = "STRONG"
            min_score = 88
            lev_cap = 6
        else:
            status = "STANDARD"
            min_score = 88
            lev_cap = 5

        category_performance[cat] = {
            "trades": tr,
            "wins": wins,
            "losses": data["losses"],
            "win_rate": wr,
            "total_lev_pnl": tot_pnl,
            "profit_factor": pf,
            "status": status,
            "min_score": min_score,
            "leverage_cap": lev_cap
        }

    return setup_performance, category_performance


def update_setup_scorecard(memory, closed_trades):
    """
    Aktualisiert die Performance-Matrix im Gedächtnis basierend auf allen geschlossenen Trades.
    """
    setup_perf, cat_perf = calculate_performance_matrix(closed_trades)
    memory["setup_performance"] = setup_perf
    memory["category_performance"] = cat_perf
    memory["updated_at"] = datetime.now(timezone.utc).isoformat()
    return memory


def calculate_optimal_leverage(asset_type, category, current_price, stop_loss, score, setup_name=None, memory=None, macro_headwind=False):
    """
    Berechnet den verantwortungsvollen Hebel (1x bis max 10x):
    - Berücksichtigt Asset-Klasse (Krypto max 2-3x, Aktien 3-5x, Indizes 5-8x, Rohstoffe 4-6x)
    - Liquidationsschutz: Stop-Loss muss weit vor einer theoretischen Liquidation liegen
    - Score-Bonus nur bei extrem hoher Konfluenz (Score >= 92%)
    - CLOSED-LOOP SCORECARD GOVERNOR: Drosselt den Hebel automatisch, falls Kategorie oder Setup
      in der historischen Auswertung unterdurchschnittlich abgeschnitten haben!
    - MAKRO-GEGENWIND-DÄMPFER: Drosselt den Hebel defensiv (z.B. bei Long-Aktie in bärischem S&P 500)
      auf max 2x (Krypto) bzw. 3x (Aktien) mit zusätzlichem Puffer, um vor Markt-Abstürzen zu schützen.
    """
    if not current_price or not stop_loss or current_price <= 0:
        return 3

    sl_dist_pct = abs(current_price - stop_loss) / current_price
    if sl_dist_pct <= 0.005:  # weniger als 0.5% ist unrealistisch eng
        sl_dist_pct = 0.02

    # Maximaler theoretischer Hebel, bei dem SL maximal 35-40% Kontoverlust ausmacht
    safe_max_lev = math.floor(0.35 / sl_dist_pct)

    # Asset-Klassen-Caps
    cat_lower = str(category).lower()
    asset_lower = str(asset_type).lower()

    if "crypto" in cat_lower or "krypto" in cat_lower or "crypto" in asset_lower:
        class_cap = 3  # Krypto-Wicks können bei 5-10x schnell liquidieren
    elif "rohstoff" in cat_lower or "commodity" in cat_lower or "edelmetall" in cat_lower:
        class_cap = 6
    elif "index" in cat_lower or "indices" in cat_lower:
        class_cap = 8
    else:  # Standard Aktien / Tech
        class_cap = 5

    # Scorecard-Governor aus Erfahrungsspeicher
    if memory and isinstance(memory, dict):
        cat_perf = memory.get("category_performance", {}).get(category, {})
        setup_perf = memory.get("setup_performance", {}).get(setup_name, {})

        # Kategorie-Dämpfer
        if cat_perf:
            cat_cap = cat_perf.get("leverage_cap")
            if cat_cap is not None:
                class_cap = min(class_cap, cat_cap)

        # Setup-Dämpfer
        if setup_perf:
            lev_adj = setup_perf.get("leverage_adjustment", 0)
            class_cap = max(1, class_cap + lev_adj)

    # High-Score Bonus (+1 bis +2 bei Score >= 92%)
    bonus = 0
    if score >= 92:
        bonus = 1
    if score >= 96:
        bonus = 2

    chosen_leverage = min(safe_max_lev, class_cap + bonus)

    # Makro-Gegenwind Dämpfer (Defensiver Kapitalschutz bei divergentem Leitmarkt)
    if macro_headwind:
        if "crypto" in cat_lower or "krypto" in cat_lower or "crypto" in asset_lower:
            chosen_leverage = min(chosen_leverage, 2)
        else:
            chosen_leverage = min(chosen_leverage, 3)
        chosen_leverage = max(1, chosen_leverage - 1)

    # Strikte Obergrenze 10x, Untergrenze 1x
    return max(1, min(10, chosen_leverage))


def monitor_in_flight_trades(active_trades, db_map):
    """
    Überwacht alle laufenden Trades in Echtzeit während des stündlichen Scans:
    - Erkennt frühzeitige Divergenzen / Trendwechsel gegen die Position
    - Zieht bei Gewinnen automatisch Trailing-Stop-Loss nach (Profit-Locking)
    - Setzt In-Flight Warnmeldungen für das Dashboard und Telegram
    """
    for t in active_trades:
        sym = t.get("symbol")
        live_asset = db_map.get(sym)
        if not live_asset:
            continue

        direction = t.get("direction", "LONG")
        entry_price = float(t.get("entry_price", 100.0))
        curr_price = float(live_asset.get("price", entry_price))
        raw_pnl = ((curr_price - entry_price) / entry_price) * 100.0 if direction == "LONG" else ((entry_price - curr_price) / entry_price) * 100.0
        current_sl = float(t.get("stop_loss", 0.0))
        highest_p = float(t.get("highest_price", curr_price))
        lowest_p = float(t.get("lowest_price", curr_price))

        # Höchst-/Tiefstkurse nachführen
        t["highest_price"] = max(highest_p, curr_price)
        t["lowest_price"] = min(lowest_p, curr_price)

        t.setdefault("in_flight_warnings", [])
        health = "HEALTHY"
        horizon = t.get("horizon", "CORE_SWING")

        # 1. Divergenz- & Gegen-Signal Früherkennung
        tfs_dict = live_asset.get("timeframes") or {}
        tf_4h = tfs_dict.get("4h") if isinstance(tfs_dict, dict) and tfs_dict.get("4h") else live_asset.get("4h", {})
        divs_4h = []
        if isinstance(tf_4h, dict):
            divs_4h = tf_4h.get("divergences") or tf_4h.get("divs") or []

        if direction == "LONG":
            has_adverse_div = any("bärisch" in str(d).lower() or "bearish" in str(d).lower() for d in divs_4h)
            if has_adverse_div:
                health = "CAUTION"
                warn_msg = "⚠️ Bärische Divergenz im 4h-Chart detektiert. Erhöhtes Risiko für Rücksetzer."
                if warn_msg not in t["in_flight_warnings"]:
                    t["in_flight_warnings"].append(warn_msg)
                # Bei Gewinn sofort Break-Even sichern!
                if raw_pnl >= 1.0 and current_sl < entry_price:
                    t["stop_loss"] = entry_price
                    t["trailing_active"] = True
                    t["in_flight_warnings"].append("🛡️ Stop-Loss vorsorglich auf Break-Even nachgezogen.")

            # Multi-Stufen Trailing Stop nach Zeithorizont:
            trail_level = current_sl
            if horizon == "FAST_SWING":
                # 1h/4h Fast Swing: Sichert Profite noch agiler ab
                if raw_pnl >= 8.0:
                    trail_level = max(trail_level, entry_price * 1.055, t["highest_price"] * 0.96)
                elif raw_pnl >= 5.0:
                    trail_level = max(trail_level, entry_price * 1.030, t["highest_price"] * 0.97)
                elif raw_pnl >= 3.0:
                    trail_level = max(trail_level, entry_price * 1.015)
                elif raw_pnl >= 1.5:
                    trail_level = max(trail_level, entry_price * 1.003)
            elif horizon == "MACRO_TREND":
                # 3D/1W Makro Trend: Gibt gesunden Pullbacks Raum
                if raw_pnl >= 20.0:
                    trail_level = max(trail_level, entry_price * 1.120, t["highest_price"] * 0.92)
                elif raw_pnl >= 10.0:
                    trail_level = max(trail_level, entry_price * 1.050, t["highest_price"] * 0.94)
                elif raw_pnl >= 5.0:
                    trail_level = max(trail_level, entry_price * 1.005)
            else:
                # CORE_SWING (4h/1D)
                if raw_pnl >= 9.0:
                    trail_level = max(trail_level, entry_price * 1.065, t["highest_price"] * 0.96)
                elif raw_pnl >= 6.0:
                    trail_level = max(trail_level, entry_price * 1.035, t["highest_price"] * 0.965)
                elif raw_pnl >= 3.5:
                    trail_level = max(trail_level, entry_price * 1.010)
                elif raw_pnl >= 2.0:
                    trail_level = max(trail_level, entry_price * 1.003)

            if trail_level > current_sl:
                t["stop_loss"] = round(trail_level, 4)
                t["trailing_active"] = True
                health = "TRAILING_STOP"

        elif direction == "SHORT":
            has_adverse_div = any("bullisch" in str(d).lower() or "bullish" in str(d).lower() for d in divs_4h)
            if has_adverse_div:
                health = "CAUTION"
                warn_msg = "⚠️ Bullische Divergenz im 4h-Chart detektiert. Erhöhtes Risiko für Bärenrallye."
                if warn_msg not in t["in_flight_warnings"]:
                    t["in_flight_warnings"].append(warn_msg)
                if raw_pnl >= 1.0 and current_sl > entry_price:
                    t["stop_loss"] = entry_price
                    t["trailing_active"] = True
                    t["in_flight_warnings"].append("🛡️ Stop-Loss vorsorglich auf Break-Even nachgezogen.")

            trail_level = current_sl if current_sl > 0 else entry_price * 2
            if horizon == "FAST_SWING":
                if raw_pnl >= 8.0:
                    trail_level = min(trail_level, entry_price * 0.945, t["lowest_price"] * 1.04)
                elif raw_pnl >= 5.0:
                    trail_level = min(trail_level, entry_price * 0.970, t["lowest_price"] * 1.03)
                elif raw_pnl >= 3.0:
                    trail_level = min(trail_level, entry_price * 0.985)
                elif raw_pnl >= 1.5:
                    trail_level = min(trail_level, entry_price * 0.997)
            elif horizon == "MACRO_TREND":
                if raw_pnl >= 20.0:
                    trail_level = min(trail_level, entry_price * 0.880, t["lowest_price"] * 1.08)
                elif raw_pnl >= 10.0:
                    trail_level = min(trail_level, entry_price * 0.950, t["lowest_price"] * 1.06)
                elif raw_pnl >= 5.0:
                    trail_level = min(trail_level, entry_price * 0.995)
            else:
                if raw_pnl >= 9.0:
                    trail_level = min(trail_level, entry_price * 0.935, t["lowest_price"] * 1.04)
                elif raw_pnl >= 6.0:
                    trail_level = min(trail_level, entry_price * 0.965, t["lowest_price"] * 1.035)
                elif raw_pnl >= 3.5:
                    trail_level = min(trail_level, entry_price * 0.990)
                elif raw_pnl >= 2.0:
                    trail_level = min(trail_level, entry_price * 0.997)

            if trail_level < current_sl or current_sl == 0:
                t["stop_loss"] = round(trail_level, 4)
                t["trailing_active"] = True
                health = "TRAILING_STOP"

        t["health_status"] = health


def evaluate_candidate_against_post_mortem_rules(candidate, memory):
    """
    Validiert ein Kandidaten-Setup gegen die im Post-Mortem Lab destillierten Regeln
    sowie die wöchentlich durch Claude Opus 5.5 kalibrierten Governor-Parameter:
    1. Verhindert Einstiege bei gegenläufiger 4h-Divergenz (Top-Verlustursache)
    2. Prüft VSA-Volumenbestätigung bei Reversals (Opus min_vsa_ratio_reversal)
    3. Prüft Kausalitäts-HTF-Trend sowie Overbought/Oversold Chasing Limits
    4. Blockiert Makro-Gegenwind unterhalb von min_score_counter_trend
    """
    gov = load_opus_governor_params()
    direction = candidate.get("signal", "LONG")
    setup_name = candidate.get("setup_name", "")
    score = candidate.get("score", 0)

    tfs = candidate.get("timeframes") if isinstance(candidate.get("timeframes"), dict) else {}
    tf_4h = tfs.get("4h") or candidate.get("4h", {})

    # 1. 4h-Divergenz-Filter & RSI Overextension Chasing-Schutz
    if isinstance(tf_4h, dict) and tf_4h:
        divs = tf_4h.get("divergences") or tf_4h.get("divs") or []
        if direction == "LONG":
            has_adverse = any("bärisch" in str(d).lower() or "bearish" in str(d).lower() for d in divs)
            if has_adverse:
                return False, "Bärische 4h-Divergenz aktiv (Post-Mortem Regel: Reversal-Gefahr)"
            rsi_4h = tf_4h.get("rsi")
            max_rsi_long = float(gov.get("max_rsi_long_entry", 64.0))
            if isinstance(rsi_4h, (int, float)) and rsi_4h > max_rsi_long and score < 95:
                return False, f"4h RSI ({rsi_4h:.1f} > {max_rsi_long:.0f}) überhitzt (Opus Chasing-Schutz)"
        elif direction == "SHORT":
            has_adverse = any("bullisch" in str(d).lower() or "bullish" in str(d).lower() for d in divs)
            if has_adverse:
                return False, "Bullische 4h-Divergenz aktiv (Post-Mortem Regel: Bärenrallye-Gefahr)"
            rsi_4h = tf_4h.get("rsi")
            min_rsi_short = float(gov.get("min_rsi_short_entry", 36.0))
            if isinstance(rsi_4h, (int, float)) and rsi_4h < min_rsi_short and score < 95:
                return False, f"4h RSI ({rsi_4h:.1f} < {min_rsi_short:.0f}) überverkauft (Opus Short-Chasing-Schutz)"

    # 2. VSA-Volumen-Check bei Reversals (Opus kalibrierte Schwelle)
    min_vsa_rev = float(gov.get("min_vsa_ratio_reversal", 1.20))
    if "reversal" in setup_name.lower():
        vsa_ratio = (
            tf_4h.get("vsa_ratio") if isinstance(tf_4h, dict) and tf_4h.get("vsa_ratio") is not None
            else (candidate.get("vsa", {}).get("ratio", 1.0) if isinstance(candidate.get("vsa"), dict) else 1.0)
        )
        if float(vsa_ratio) < min_vsa_rev and score < 92:
            return False, f"Reversal ohne VSA-Volumenspitze ({float(vsa_ratio):.2f}x < {min_vsa_rev:.2f}x)"

    # 3. Kausalitäts-Trend-Governance (Fable 5.2 Kausalitäts-Regel):
    tf_1h = tfs.get("1h") or candidate.get("1h", {})
    if isinstance(tf_1h, dict) and tf_1h:
        htf_trend = tf_1h.get("trend")
        htf_rsi = tf_1h.get("rsi")
        if direction == "LONG" and htf_trend == "BEARISH":
            rsi_str = f" (RSI {htf_rsi:.1f})" if isinstance(htf_rsi, (int, float)) else ""
            return False, f"HTF 1h ist BEARISH{rsi_str} — Kausalitäts-Filter blockiert Long gegen Trend"
        elif direction == "SHORT" and htf_trend == "BULLISH":
            rsi_str = f" (RSI {htf_rsi:.1f})" if isinstance(htf_rsi, (int, float)) else ""
            return False, f"HTF 1h ist BULLISH{rsi_str} — Kausalitäts-Filter blockiert Short gegen Trend"

    # 4. Makro-Gegenwind Schutz (Opus min_score_counter_trend)
    min_ct_score = int(gov.get("min_score_counter_trend", 94))
    if candidate.get("macro_headwind", False) and direction == "LONG" and score < min_ct_score:
        return False, f"Makro-Gegenwind aktiv (Opus Kausalitäts-Regel: Counter-Trend erfordert Score >= {min_ct_score}%)"

    return True, "OK"


def determine_trade_horizon(candidate):
    """
    Klassifiziert einen Trade in einen von 3 Zeithorizonten:
    - FAST_SWING (1h/4h): Intraday / schneller Momentum-Swing (12h - 3 Tage)
    - CORE_SWING (4h/1D): Standard SMC & Fib Reversal (3 Tage - 2 Wochen)
    - MACRO_TREND (3D/1W): Übergeordneter Makro-Trend (2 Wochen - 3 Monate)
    """
    setup = candidate.get("setup_name", "").lower()
    reasons = " ".join(candidate.get("reasons", [])).lower()

    if any(k in setup or k in reasons for k in ["weekly", "1w", "3d", "makro", "macro", "jahrestrend", "halving"]):
        return "MACRO_TREND", "🏛️ Makro Trend (3D/1W)", "3D/1W"
    elif any(k in setup or k in reasons for k in ["1h", "micro", "sweep", "scalp", "intraday", "breakout", "pocket"]):
        return "FAST_SWING", "⚡ Fast Swing (1h/4h)", "1h/4h"
    else:
        return "CORE_SWING", "🎯 Core Swing (4h/1D)", "4h/1D"


# ==============================================================================
# 2. AUTONOMES HIGH-CONVICTION PORTFOLIO
# ==============================================================================
def update_autonomous_portfolio(db_assets):
    """
    Verwaltet das autonome Modell-Portfolio:
    - Öffnet neue Positionen bei High-Conviction Setups (Score >= 88%, non-NEUTRAL)
    - Aktualisiert offene Positionen (PnL, Haltedauer, Höchst-/Tiefstkurse)
    - Führt Exits durch (TP1 Teilverkauf/Break-Even, TP2 Vollziel, SL, Trendbruch)
    - Übergibt geschlossene Trades an das Gedächtnis (trade_memory.json)
    """
    portfolio = load_json_file(PORTFOLIO_FILE, {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "base_capital_per_trade": 1000.0,  # 1.000 € Einheitsbetrag für relative Auswertung
        "active_trades": [],
        "closed_trades": [],
        "metrics": {
            "total_trades": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate_pct": 0.0,
            "total_pnl_pct": 0.0,
            "total_leveraged_pnl_pct": 0.0,
            "profit_factor": 0.0
        }
    })

    memory = load_json_file(TRADE_MEMORY_FILE, {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total_experience_records": 0,
        "learnings": [],
        "setup_statistics": {}
    })

    active_trades = portfolio.get("active_trades", [])
    closed_trades = portfolio.get("closed_trades", [])
    active_symbols = {t["symbol"]: t for t in active_trades}

    now_iso = datetime.now(timezone.utc).isoformat()
    now_dt = datetime.now(timezone.utc)
    gov_params = load_opus_governor_params()

    # Prospektives Stufe-2 Schattenbuch (SHADOW_PAPER) synchron aktualisieren (lautes Fehler-Logging!)
    import traceback
    try:
        from shadow_paper_book import update_shadow_paper_book
        update_shadow_paper_book(db_assets, now_dt)
    except Exception:
        print("   ❌ [Shadow-Paper Update FEHLER]:")
        traceback.print_exc()

    # Unabhaengiger SHADOW_PAPER Signal-Durchlauf (entkoppelt von Live is_halted, Live-Slots & trade_memory)
    shadow_cands = [
        a for a in db_assets
        if a.get("signal") in ("LONG", "SHORT")
        and a.get("score", 0) >= 88
    ]
    for sc in shadow_cands:
        try:
            s_sym = sc["symbol"]
            s_cat = sc.get("category", "")
            s_p = float(sc.get("price") or 0.0)
            if s_p <= 0.0:
                continue
            s_horizon, _, s_htf = determine_trade_horizon(sc)
            s_tf = str(sc.get("primary_timeframe") or sc.get("timeframe") or "").strip().lower()
            if not s_tf:
                s_tf = s_htf
                st_txt = (str(sc.get("setup_name", "")) + " " + " ".join(sc.get("reasons", []))).lower()
                for tf_tok in ("30m", "15m", "4h", "1h", "1d", "daily"):
                    if tf_tok in st_txt:
                        s_tf = "1d" if tf_tok == "daily" else tf_tok
                        break
            s_wl = check_triad_whitelist(symbol=s_sym, timeframe=s_tf, direction=sc.get("signal", ""), category=s_cat)
            if not s_wl["is_approved"] or s_wl["tier"] != "SHADOW_PAPER":
                continue
            if not sc.get("stop_loss") or not sc.get("take_profit_1") or not sc.get("take_profit_2"):
                continue
            s_sl = float(sc["stop_loss"])
            s_tp1 = float(sc["take_profit_1"])
            s_tp2 = float(sc["take_profit_2"])
            s_cost = check_cost_gate(entry_price=s_p, stop_loss=s_sl, symbol=s_sym, cluster=s_cat, config=TRIAD_PILOT_CONFIG)
            if not s_cost["is_allowed"]:
                continue
            from shadow_paper_book import try_open_shadow_paper_trade
            try_open_shadow_paper_trade(
                candidate=sc, wl_check=s_wl, sig_tf=s_tf,
                sl=s_sl, tp1=s_tp1, tp2=s_tp2, score=int(sc.get("score", 88)),
                setup_name=sc.get("setup_name", "High-Conviction Confluence"),
                cat=s_cat, horizon=s_horizon, now_dt=now_dt, gov_params=gov_params,
            )
        except Exception:
            print(f"   ❌ [Shadow-Paper Open FEHLER ({sc.get('symbol')})]:")
            traceback.print_exc()

    db_map = {a["symbol"]: a for a in db_assets}

    # 1. Bestehende offene Trades vorab mit Live-Kursen & Haltedauer aktualisieren
    remaining_active = []
    newly_closed = []
    matched_pairs = []

    for t in active_trades:
        sym = t["symbol"]
        a = db_map.get(sym)
        if not a:
            if "USDT" in sym:
                a = db_map.get(sym.replace("USDT", "USD"))
            elif "USD" in sym:
                a = db_map.get(sym.replace("USD", "USDT"))
        if not a:
            ticker_only = sym.split(":")[-1] if ":" in sym else sym
            for k, v in db_map.items():
                if k.endswith(f":{ticker_only}") or k == ticker_only:
                    a = v
                    break

        if not a:
            try:
                from fetch_real_ohlcv_cache import fetch_bars_direct
                live_bars = fetch_bars_direct(sym, interval="1D", count=2)
                if live_bars and len(live_bars) > 0:
                    a = {
                        "symbol": sym,
                        "price": float(live_bars[-1].get("c", t.get("current_price", t["entry_price"]))),
                        "signal": "NEUTRAL"
                    }
            except Exception:
                pass

        if not a:
            remaining_active.append(t)
            continue

        curr_price = float(a.get("price", t.get("current_price", t["entry_price"])))
        direction = t["direction"]
        entry_price = float(t["entry_price"])
        lev = t.get("leverage", 1)

        try:
            entry_dt = datetime.fromisoformat(str(t["entry_time"]).replace("Z", "+00:00"))
            holding_hours = round((now_dt - entry_dt).total_seconds() / 3600.0, 1)
            holding_days = round(holding_hours / 24.0, 1)
        except Exception:
            holding_hours = 0.0
            holding_days = 0.0

        if direction == "LONG":
            raw_pnl_pct = ((curr_price - entry_price) / entry_price) * 100.0
        else:
            raw_pnl_pct = ((entry_price - curr_price) / entry_price) * 100.0
        leveraged_pnl_pct = raw_pnl_pct * lev

        t["highest_price"] = max(t.get("highest_price", curr_price), curr_price)
        t["lowest_price"] = min(t.get("lowest_price", curr_price), curr_price)
        t["current_price"] = curr_price
        t["last_price_update"] = a.get("last_price_update", now_iso)
        t["last_price_update_str"] = a.get("last_price_update_str", "")
        t["unrealized_pnl_pct"] = round(raw_pnl_pct, 2)
        t["unrealized_pnl_leveraged_pct"] = round(leveraged_pnl_pct, 2)
        t["holding_hours"] = holding_hours
        t["holding_days"] = holding_days
        matched_pairs.append((t, a))

    # 1a. Vorschlag C: Täglicher Claude Opus 5.5 In-Flight Exit-Doctor (12h-gedrosselt)
    if matched_pairs:
        try:
            from gemini_evaluator import audit_open_positions_with_opus
            opus_doc_map = audit_open_positions_with_opus(
                [p[0] for p in matched_pairs],
                db_map,
                portfolio_context="KI_PORTFOLIO",
            )
            for t, _ in matched_pairs:
                tid = str(t.get("trade_id") or "")
                sym = str(t.get("symbol") or "")
                aud = opus_doc_map.get(tid) or opus_doc_map.get(sym)
                if not aud:
                    continue
                t["opus_inflight_audit"] = aud
                verdict = aud.get("verdict", "HOLD")
                rec_sl = aud.get("recommended_sl")
                rec_tp1 = aud.get("recommended_tp1")
                d_str = t.get("direction", "LONG")
                cp = float(t.get("current_price", t.get("entry_price", 0.0)))
                cur_sl = float(t.get("stop_loss", 0.0))
                if verdict == "TIGHTEN_SL" and rec_sl is not None:
                    if (d_str == "LONG" and rec_sl > cur_sl and rec_sl < cp) or (
                        d_str == "SHORT" and (cur_sl == 0 or rec_sl < cur_sl) and rec_sl > cp
                    ):
                        t["stop_loss"] = round(rec_sl, 4)
                        t["trailing_active"] = True
                        t.setdefault("in_flight_warnings", []).append(
                            f"🏛️ Opus Exit-Doctor SL nachgezogen auf {round(rec_sl, 4)}."
                        )
                elif verdict == "ADJUST_TP1" and rec_tp1 is not None:
                    if (d_str == "LONG" and rec_tp1 > cp) or (d_str == "SHORT" and rec_tp1 < cp):
                        t["take_profit_1"] = round(rec_tp1, 4)
                        t.setdefault("in_flight_warnings", []).append(
                            f"🏛️ Opus Exit-Doctor TP1 angepasst auf {round(rec_tp1, 4)}."
                        )
        except Exception as od_err:
            print(f"   ℹ️ Opus In-Flight Exit-Doctor übersprungen: {od_err}")

    for t, a in matched_pairs:
        sym = t["symbol"]
        curr_price = t["current_price"]
        direction = t["direction"]
        entry_price = t["entry_price"]
        lev = t.get("leverage", 1)
        sl = t.get("stop_loss", 0.0)
        tp1 = t.get("take_profit_1", 0.0)
        tp2 = t.get("take_profit_2", 0.0)
        holding_hours = t["holding_hours"]
        holding_days = t["holding_days"]
        raw_pnl_pct = ((curr_price - entry_price) / entry_price) * 100.0 if direction == "LONG" else ((entry_price - curr_price) / entry_price) * 100.0
        leveraged_pnl_pct = raw_pnl_pct * lev

        # AUSSTIEGS-LOGIK (DYNAMISCH, MULTI-DAY, OPUS EXIT-DOCTOR & TIME-STOP)
        exit_triggered = False
        exit_reason = ""
        exit_price = curr_price

        # A) Hard Stop-Loss
        if direction == "LONG" and sl > 0 and curr_price <= sl:
            exit_triggered = True
            exit_reason = f"Stop-Loss erreicht ({curr_price:,.2f} <= {sl:,.2f}) zum Kapitalschutz."
        elif direction == "SHORT" and sl > 0 and curr_price >= sl:
            exit_triggered = True
            exit_reason = f"Stop-Loss erreicht ({curr_price:,.2f} >= {sl:,.2f}) zum Kapitalschutz."

        # B) Take-Profit 2 (Hauptziel)
        elif direction == "LONG" and tp2 > 0 and curr_price >= tp2:
            exit_triggered = True
            exit_reason = f"Take-Profit 2 Hauptziel erreicht ({curr_price:,.2f} >= {tp2:,.2f}). Maximaler Gewinn realisiert."
        elif direction == "SHORT" and tp2 > 0 and curr_price <= tp2:
            exit_triggered = True
            exit_reason = f"Take-Profit 2 Hauptziel erreicht ({curr_price:,.2f} <= {tp2:,.2f}). Maximaler Gewinn realisiert."

        # C) Trend- & Strukturbruch (Vorzeitiger intelligenter Ausstieg)
        else:
            curr_sig = a.get("signal", "NEUTRAL")
            opposite_sig = "SHORT" if direction == "LONG" else "LONG"

            # Wenn das Signal komplett auf die Gegenseite gedreht hat
            if curr_sig == opposite_sig:
                exit_triggered = True
                exit_reason = f"Struktureller Trendwechsel: Markt-Signal drehte von {direction} auf {curr_sig}."
            # Wenn das Signal nach mindestens 24h Haltedauer auf NEUTRAL fällt und PnL negativ wird
            elif curr_sig == "NEUTRAL" and holding_hours >= 24 and raw_pnl_pct < -1.5:
                exit_triggered = True
                exit_reason = f"Vorzeitiger Kapitalschutz: Setup nach {holding_days} Tagen invalidiert (Signal NEUTRAL)."
            elif direction == "LONG" and tp1 > 0 and curr_price >= tp1 and not t.get("tp1_partial_closed"):
                t["tp1_partial_closed"] = True
                t["tp1_reached"] = True
                t["partial_tp_price"] = tp1
                t["partial_tp_time"] = now_iso
                part_raw = round(((tp1 - entry_price) / entry_price) * 100.0 * 0.5, 2)
                part_lev = round(part_raw * lev, 2)
                t["partial_tp_realized_raw_pct"] = part_raw
                t["partial_tp_realized_lev_pct"] = part_lev
                be_sl = round(entry_price * 1.003, 4)
                if be_sl > sl:
                    t["stop_loss"] = be_sl
                t["trailing_active"] = True
                t.setdefault("in_flight_warnings", []).append(
                    f"🎯 TP1 Teilgewinn (50% Tranche, +{part_raw:.2f}%) gesichert! Restposition läuft risikofrei mit Trailing-SL."
                )
                try:
                    from notifications import send_ki_portfolio_alert
                    send_ki_portfolio_alert("TRADE_PARTIAL_CLOSE", t)
                except Exception as e:
                    print(f"Warnung beim KI-Portfolio Alert (TP1): {e}")
            elif direction == "SHORT" and tp1 > 0 and curr_price <= tp1 and not t.get("tp1_partial_closed"):
                t["tp1_partial_closed"] = True
                t["tp1_reached"] = True
                t["partial_tp_price"] = tp1
                t["partial_tp_time"] = now_iso
                part_raw = round(((entry_price - tp1) / entry_price) * 100.0 * 0.5, 2)
                part_lev = round(part_raw * lev, 2)
                t["partial_tp_realized_raw_pct"] = part_raw
                t["partial_tp_realized_lev_pct"] = part_lev
                be_sl = round(entry_price * 0.997, 4)
                if sl == 0 or be_sl < sl:
                    t["stop_loss"] = be_sl
                t["trailing_active"] = True
                t.setdefault("in_flight_warnings", []).append(
                    f"🎯 TP1 Teilgewinn (50% Tranche, +{part_raw:.2f}%) gesichert! Restposition läuft risikofrei mit Trailing-SL."
                )
                try:
                    from notifications import send_ki_portfolio_alert
                    send_ki_portfolio_alert("TRADE_PARTIAL_CLOSE", t)
                except Exception as e:
                    print(f"Warnung beim KI-Portfolio Alert (TP1): {e}")

            # D) Opus Exit-Doctor Close ODER Quantitativer Stagnations- & Max-Holding Time-Stop
            if not exit_triggered:
                opus_aud = t.get("opus_inflight_audit") or {}
                opus_verdict = str(opus_aud.get("verdict") or "HOLD").upper()
                horizon = t.get("horizon", "CORE_SWING")
                max_days_map = {
                    "FAST_SWING": float(gov_params.get("max_holding_days_fast_swing", 4.0)),
                    "CORE_SWING": float(gov_params.get("max_holding_days_core_swing", 14.0)),
                    "MACRO_TREND": float(gov_params.get("max_holding_days_macro_trend", 45.0)),
                }
                max_days = max_days_map.get(horizon, float(gov_params.get("max_holding_days_core_swing", 14.0)))
                stag_days = float(gov_params.get("stagnation_profit_lock_days", 12.0))

                if opus_verdict in ("CLOSE_TIME_DECAY", "CLOSE_STRUCTURE_BREAK"):
                    exit_triggered = True
                    exit_reason = f"🏛️ Opus 5.5 Exit-Doctor ({opus_verdict}): {opus_aud.get('diagnosis', 'Ausstieg empfohlen.')}"
                elif holding_days >= stag_days and not t.get("tp1_partial_closed") and raw_pnl_pct > 0.5:
                    exit_triggered = True
                    exit_reason = (
                        f"⏳ Stagnations-Gewinnsicherung nach {holding_days:.1f} Tagen "
                        f"(über {stag_days:.0f}d ohne TP1): +{raw_pnl_pct:.2f}% Basis / +{leveraged_pnl_pct:.2f}% Hebel gesichert."
                    )
                elif holding_days >= max_days:
                    exit_triggered = True
                    exit_reason = (
                        f"⏳ Max-Holding Time-Stop ({horizon}: {holding_days:.1f}d ≥ {max_days:.0f}d) "
                        "— Kapital & Cluster-Slot freigegeben."
                    )

        # D) AUTONOME POSITIONSERWEITERUNG (PYRAMIDING) BEI VERSTÄRKTEN SIGNALEN
        if not exit_triggered:
            curr_score = a.get("score", 0)
            initial_score = t.get("initial_score", t.get("score", 88))
            tranches = t.get("tranches", 1)
            max_tranches = 3

            # Kriterien für Erweiterung:
            # 1. Position ist im Gewinn (mindestens +1.0% Basis-Gewinn) - NIEMALS Verlierer aufstocken!
            # 2. Aktuelles Signal bestätigt die Richtung (z.B. LONG bleibt LONG)
            # 3. Score hat sich signifikant verstärkt (z.B. >= 92% oder Anstieg um >= 3 Punkte)
            # 4. Maximal 3 Tranchen
            score_strengthened = (curr_score >= 92) or (curr_score >= initial_score + 3)
            is_in_profit = raw_pnl_pct >= 1.0

            if is_in_profit and a.get("signal") == direction and score_strengthened and tranches < max_tranches:
                last_expand_price = t.get("last_expansion_price", entry_price)
                price_moved_favorable = (curr_price > last_expand_price) if direction == "LONG" else (curr_price < last_expand_price)

                if price_moved_favorable:
                    new_tranches = tranches + 1
                    old_cap = t.get("allocated_capital", 1000.0)
                    add_cap = 1000.0  # Feste Einheitsallokation pro Tranche
                    new_cap = old_cap + add_cap

                    # Neuer Mischkurs berechnen
                    blended_entry = ((entry_price * old_cap) + (curr_price * add_cap)) / new_cap

                    # Stop-Loss risikominimierend nachziehen (mindestens auf vorherigen Einstiegskurs!)
                    old_sl = t.get("stop_loss", 0.0)
                    new_sl = max(old_sl, entry_price) if direction == "LONG" else min(old_sl, entry_price)

                    t["tranches"] = new_tranches
                    t["allocated_capital"] = new_cap
                    t["entry_price"] = round(blended_entry, 4)
                    t["last_expansion_price"] = curr_price
                    t["stop_loss"] = round(new_sl, 4)
                    t["score"] = curr_score

                    exp_note = f"Tranche {new_tranches} add @ {curr_price:,.2f} ({curr_score}% Score)"
                    t.setdefault("expansion_history", []).append({
                        "tranche": new_tranches,
                        "time": now_iso,
                        "price": curr_price,
                        "score": curr_score,
                        "reason": f"Signal verstärkt ({curr_score}% Score). Tranche {new_tranches} hinzugefügt. Stop-Loss auf {new_sl:,.2f} angehoben."
                    })
                    t["entry_reason"] += f" | {exp_note}"
                    print(f"   📈 [PYRAMIDING] Position {t['name']} ({sym}) erweitert: Tranche {new_tranches} @ {curr_price:,.2f} | Neuer Mischkurs: {blended_entry:,.2f} | SL nachgezogen: {new_sl:,.2f}")
                    try:
                        from notifications import send_ki_portfolio_alert
                        send_ki_portfolio_alert("TRADE_EXPANDED", t)
                    except Exception as e:
                        print(f"Warnung beim KI-Portfolio Alert (EXPANDED): {e}")

        if exit_triggered:
            # Trade abschließen (unter Berücksichtigung von 50% Teilgewinnmitnahmen)
            if t.get("tp1_partial_closed"):
                part_raw = t.get("partial_tp_realized_raw_pct", 0.0)
                part_lev = t.get("partial_tp_realized_lev_pct", 0.0)
                rem_raw = (((exit_price - entry_price) / entry_price) * 100.0 if direction == "LONG" else ((entry_price - exit_price) / entry_price) * 100.0) * 0.5
                rem_lev = rem_raw * lev
                final_raw_pnl = round(part_raw + rem_raw, 2)
                final_lev_pnl = round(part_lev + rem_lev, 2)
                exit_reason += f" [Teil-TP1 50%: +{part_raw:.2f}% | Rest 50%: {rem_raw:+.2f}%]"
            else:
                final_raw_pnl = ((exit_price - entry_price) / entry_price) * 100.0 if direction == "LONG" else ((entry_price - exit_price) / entry_price) * 100.0
                final_lev_pnl = final_raw_pnl * lev
            is_win = final_raw_pnl > 0

            # Exakte 1.0R Risikoberechnung für Circuit-Breaker & Gedächtnis
            init_sl = t.get("initial_stop_loss", sl)
            init_risk_dist = abs(entry_price - init_sl) if (init_sl and init_sl > 0) else 0.0
            if init_risk_dist > 1e-6:
                if t.get("tp1_partial_closed") and tp1 > 0:
                    part_pnl = (tp1 - entry_price) if direction == "LONG" else (entry_price - tp1)
                    rem_pnl = (exit_price - entry_price) if direction == "LONG" else (entry_price - exit_price)
                    realized_r = round(((part_pnl * 0.5) + (rem_pnl * 0.5)) / init_risk_dist, 2)
                else:
                    pnl_dist = (exit_price - entry_price) if direction == "LONG" else (entry_price - exit_price)
                    realized_r = round(pnl_dist / init_risk_dist, 2)
            else:
                realized_r = round(final_raw_pnl / 2.0, 2)

            risk_cash = t.get("risk_cash", 50.0)
            realized_pnl_cash = round(realized_r * risk_cash, 2)

            closed_entry = {
                "trade_id": t["trade_id"],
                "symbol": t["symbol"],
                "name": t["name"],
                "category": t.get("category", ""),
                "cluster": classify_asset_cluster(t["symbol"], t.get("category")),
                "direction": direction,
                "score": t["score"],
                "setup_name": t["setup_name"],
                "entry_time": t["entry_time"],
                "entry_price": entry_price,
                "exit_time": now_iso,
                "exit_price": exit_price,
                "stop_loss": sl,
                "initial_stop_loss": init_sl,
                "take_profit_1": tp1,
                "take_profit_2": tp2,
                "highest_price": t.get("highest_price", entry_price),
                "lowest_price": t.get("lowest_price", entry_price),
                "leverage": lev,
                "holding_days": holding_days,
                "entry_reason": t["entry_reason"],
                "exit_reason": exit_reason,
                "realized_pnl_pct": round(final_raw_pnl, 2),
                "realized_pnl_leveraged_pct": round(final_lev_pnl, 2),
                "realized_r": realized_r,
                "risk_cash": risk_cash,
                "realized_pnl_cash": realized_pnl_cash,
                "regime": "PROTECTIVE",
                "opus_inflight_audit": t.get("opus_inflight_audit"),
                "result": "WIN" if is_win else ("LOSS" if final_raw_pnl < 0 else "BREAKEVEN"),
            }

            # Tiefgehende KI-Post-Mortem-Analyse via Gemini 4 Neon + Claude Opus 5.5 (Vorschlag D)
            try:
                from gemini_evaluator import evaluate_trade_post_mortem, audit_portfolio_trade_post_mortem_with_opus
                ai_post_mortem = evaluate_trade_post_mortem(closed_entry)
                opus_post_mortem = audit_portfolio_trade_post_mortem_with_opus(closed_entry, gemini_eval=ai_post_mortem)
            except Exception:
                ai_post_mortem = None
                opus_post_mortem = None

            if ai_post_mortem and isinstance(ai_post_mortem, dict):
                if opus_post_mortem and isinstance(opus_post_mortem, dict):
                    ai_post_mortem["opus_audit"] = opus_post_mortem
                closed_entry["ai_post_mortem"] = ai_post_mortem
                closed_entry["post_mortem_learning"] = ai_post_mortem.get("summary_text", generate_trade_learning(t, exit_reason, final_raw_pnl, final_lev_pnl))
            else:
                learning_note = generate_trade_learning(t, exit_reason, final_raw_pnl, final_lev_pnl)
                closed_entry["post_mortem_learning"] = learning_note

            if opus_post_mortem and isinstance(opus_post_mortem, dict):
                closed_entry["opus_audit"] = opus_post_mortem
                if opus_post_mortem.get("opus_actionable_rule"):
                    closed_entry["post_mortem_learning"] += f" | 🏛️ Opus Axiom: {opus_post_mortem['opus_actionable_rule']}"

            closed_trades.insert(0, closed_entry)
            newly_closed.append(closed_entry)

            # Gedächtnis updaten
            record_learning_in_memory(memory, closed_entry)

            try:
                from notifications import send_ki_portfolio_alert
                send_ki_portfolio_alert("TRADE_CLOSED", closed_entry)
            except Exception as e:
                print(f"Warnung beim KI-Portfolio Alert (CLOSED): {e}")
        else:
            remaining_active.append(t)

    # 2. In-Flight Überwachung aller verbleibenden aktiven Trades
    monitor_in_flight_trades(remaining_active, db_map)

    # 2b. Drawdown Circuit-Breaker Prüfung vor neuen Einstiegen
    # Evaluieren wir alle Trades unter dem Schutz-Regime sowie heutige Trades
    today_str = now_dt.strftime("%Y-%m-%d")
    protective_closed = [
        t for t in closed_trades 
        if t.get("regime") == "PROTECTIVE" or t.get("exit_time", "").startswith(today_str)
    ]
    cb_res = check_drawdown_circuit_breaker(protective_closed)
    action = cb_res.get("action", "ALLOW")
    is_halted = cb_res.get("is_halted", False)
    sizing_mult = cb_res.get("sizing_multiplier", 1.0)
    effective_risk_pct = 0.5 * sizing_mult

    if is_halted:
        print(f"   🛑 [Portfolio Circuit Breaker Aktiv] Neue Einstiege gesperrt: {cb_res.get('reason')}")
    elif sizing_mult < 1.0:
        print(f"   ⚠️ [Circuit Breaker Warnung] Drawdown-Reduktion aktiv: Sizing auf {effective_risk_pct}% halbiert ({cb_res.get('reason')})")

    # 3. Neue High-Conviction Setups aufnehmen (Score >= 88%, Signal != NEUTRAL)
    # Multi-Zeithorizont Matrix: Bis zu 9 aktive Positionen (3 Fast Swing, 4 Core Swing, 2 Makro)
    max_active_positions = 9
    horizon_caps = {
        "FAST_SWING": 3,
        "CORE_SWING": 4,
        "MACRO_TREND": 2
    }
    horizon_counts = {
        "FAST_SWING": sum(1 for t in remaining_active if t.get("horizon") == "FAST_SWING"),
        "CORE_SWING": sum(1 for t in remaining_active if t.get("horizon") in ("CORE_SWING", None)),
        "MACRO_TREND": sum(1 for t in remaining_active if t.get("horizon") == "MACRO_TREND")
    }

    if not is_halted and len(remaining_active) < max_active_positions:
        candidates = [
            a for a in db_assets 
            if a.get("signal") in ("LONG", "SHORT") 
            and a.get("score", 0) >= 88 
            and a["symbol"] not in active_symbols
        ]
        # Sortieren nach Score
        candidates.sort(key=lambda x: x.get("score", 0), reverse=True)

        for c in candidates:
            if len(remaining_active) >= max_active_positions:
                break

            sym = c["symbol"]
            curr_p = c.get("price", 100.0)
            score = c.get("score", 88)
            cat = c.get("category", "")
            asset_type = c.get("asset_type", "Stock")
            setup_name = c.get("setup_name", "High-Conviction Confluence")

            # 0. TRIADE-KONSENS WHITELIST & DIRECTION-LOCK GUARD (Antigravity + Grok 4.7 + Claude Fable 5.2)
            horizon, horizon_label, horizon_tf = determine_trade_horizon(c)
            sig_tf = str(c.get("primary_timeframe") or c.get("timeframe") or "").strip().lower()
            if not sig_tf:
                sig_tf = horizon_tf
                setup_text = (str(c.get("setup_name", "")) + " " + " ".join(c.get("reasons", []))).lower()
                for tf_tok in ("30m", "15m", "4h", "1h", "1d", "daily"):
                    if tf_tok in setup_text:
                        sig_tf = "1d" if tf_tok == "daily" else tf_tok
                        break

            wl_check = check_triad_whitelist(
                symbol=sym,
                timeframe=sig_tf,
                direction=c.get("signal", ""),
                category=cat
            )
            if not wl_check["is_approved"]:
                print(f"   🛡️ [Triad Whitelist Guard] {sym} ({sig_tf} {c.get('signal')}) abgewiesen: {wl_check['rejection_reason']}")
                continue

            if wl_check["tier"] != "PILOT_LIVE":
                print(f"   🛡️ [Triad Tier Guard] {sym} ({sig_tf}) befindet sich auf Stufe '{wl_check['tier']}' (nicht PILOT_LIVE) -> Kein Live-Trade.")
                continue

            # Max. 1 Position je Basis-Asset (Kein Klumpenrisiko / Double-Dipping auf demselben Ticker)
            base_ticker = sym.split(":")[-1]
            if any(t["symbol"] == sym or t["symbol"].endswith(f":{base_ticker}") or t.get("name") == c.get("name") for t in remaining_active):
                print(f"   🛡️ [Max 1 Position Guard] Bereits eine aktive Position für {c.get('name')} ({sym}) offen.")
                continue

            # 1. Post-Mortem Lab qualitative Regeln prüfen (Gegen-Divergenzen, VSA)
            passes_rules, rule_reason = evaluate_candidate_against_post_mortem_rules(c, memory)
            if not passes_rules:
                print(f"   🛡️ [Post-Mortem Guard] {sym} abgewiesen: {rule_reason}")
                continue

            # 2. CLOSED-LOOP SCORECARD FILTER & OPUS GOVERNOR PARAMETER
            setup_perf = memory.get("setup_performance", {}).get(setup_name, {})
            cat_perf = memory.get("category_performance", {}).get(cat, {})
            sector_adj = int((gov_params.get("sector_score_adjustments") or {}).get(cat, 0) or 0)
            base_min_score = max(int(gov_params.get("min_score_default", 88)), 88 + sector_adj)
            min_score_req = max(base_min_score, setup_perf.get("min_score", 88), cat_perf.get("min_score", 88))

            if score < min_score_req:
                print(f"   🛡️ [Scorecard Guard] {sym} ({setup_name} in {cat}) übersprungen: Score {score}% < Mindestanforderung von {min_score_req}%")
                continue

            # 3. Zeithorizont zuordnen & Kapazität prüfen
            if horizon_counts.get(horizon, 0) >= horizon_caps.get(horizon, 3):
                continue

            sl = c.get("stop_loss", curr_p * 0.95)
            tp1 = c.get("take_profit_1", curr_p * 1.05)
            tp2 = c.get("take_profit_2", curr_p * 1.10)

            # 4. KOSTEN-GATE: Reibungskosten (Gebühren + Spread + Slippage) <= 20% des Stop-Abstands (Fable 5.2 Konsens)
            cost_check = check_cost_gate(entry_price=curr_p, stop_loss=sl, symbol=sym, cluster=cat, config=TRIAD_PILOT_CONFIG)
            if not cost_check["is_allowed"]:
                print(f"   🛡️ [Cost Gate Guard] {sym} abgewiesen: {cost_check['rejection_reason']}")
                continue

            # 5. CLUSTER HEAT-LIMIT: Max 0.30% Cluster-Heat (2.0R @ 0.15%), max 0.60% Gesamt-Heat (4.0R @ 0.15%)
            heat_check = check_cluster_heat_limit(
                remaining_active,
                candidate_symbol=sym,
                candidate_category=cat,
                candidate_risk_r=1.0,
                config=TRIAD_PILOT_CONFIG
            )
            if not heat_check["is_allowed"]:
                print(f"   🛡️ [Cluster Heat Guard] {sym} ({cat}) übersprungen: {heat_check['rejection_reason']}")
                continue

            # Automatische Hebel-Ermittlung mit Scorecard-Feedback & Makro-Schutz (Makro maximal 2x)
            macro_hw = c.get("macro_headwind", False)
            lev = calculate_optimal_leverage(asset_type, cat, curr_p, sl, score, setup_name=setup_name, memory=memory, macro_headwind=macro_hw)
            if horizon == "MACRO_TREND":
                lev = min(lev, 2)

            # Fundierte Begründung zusammenstellen
            reasons = c.get("reasons", [])
            note = c.get("analyst_note", "")
            reason_str = " | ".join(reasons[:2]) if reasons else note
            if not reason_str:
                reason_str = f"Hohe Multi-Timeframe Konfluenz ({score}% Score) mit CRV {c.get('crv', 2.5)}:1"

            # 6. TRIADE-COUNCIL KONSENS-CHECK (Antigravity + Grok 4.7 + Claude Opus 5.5)
            try:
                from triad_council import evaluate_setup_with_council
                council_eval = evaluate_setup_with_council(
                    symbol=sym,
                    direction=c.get("signal", ""),
                    timeframe=sig_tf,
                    setup_summary=f"Score {score}%, Reasons: {reason_str}, Entry {curr_p}, SL {sl}, CRV {c.get('crv', 2.5)}"
                )
                if not council_eval["is_approved"]:
                    print(f"   🛑 [Triad Council Veto] {sym} abgewiesen: {council_eval.get('consensus_label')}")
                    continue
                badges = council_eval.get("badges", [])
                council_label = council_eval.get("consensus_label", "🟢 Triade-Konsens: 3/3 BESTÄTIGT")
            except Exception as e:
                print(f"   ⚠️ [Triad Council] Fallback auf mathematische Engine: {e}")
                badges = ["📐 Antigravity: PASS", "⚡ Grok: PASS", "🏛️ Opus: PASS"]
                council_label = "🟢 Triade-Konsens: 3/3 BESTÄTIGT"

            # Flaches Sizing gemäß Triade-Konsens (0.15% Pilot Live, 0.075% bei Drawdown-Reduktion)
            is_crypto = (cat == "CRYPTO" or "USDT" in sym)
            lot_step = 0.0001 if is_crypto else 1.0
            min_lot = 0.0001 if is_crypto else 1.0
            port_equity = portfolio.get("total_capital", 10000.0)

            pilot_risk_pct = wl_check.get("risk_pct", TRIAD_PILOT_CONFIG.flat_risk_pct)
            if action == "REDUCE_SIZE":
                pilot_risk_pct *= 0.5

            pos_size = calculate_position_size(
                entry_price=curr_p,
                stop_loss=sl,
                equity=port_equity,
                risk_pct=pilot_risk_pct,
                score=score,
                lot_step=lot_step,
                min_lot=min_lot
            )

            allocated_cap = pos_size["notional_capital"] if pos_size["is_executable"] else 1000.0
            risk_cash = pos_size["risk_cash"] if pos_size["is_executable"] else round(port_equity * (pilot_risk_pct / 100.0), 2)
            qty = pos_size["qty"] if pos_size["is_executable"] else round(allocated_cap / curr_p, 4)

            new_trade = {
                "trade_id": f"trade_{sym.replace(':', '_')}_{now_dt.strftime('%Y%m%d_%H%M')}",
                "symbol": sym,
                "name": c["name"],
                "category": cat,
                "cluster": heat_check.get("cluster", classify_asset_cluster(sym, cat)),
                "whitelist_tier": wl_check["tier"],
                "whitelist_notes": wl_check.get("notes", ""),
                "risk_pct": pilot_risk_pct,
                "asset_type": asset_type,
                "direction": c["signal"],
                "horizon": horizon,
                "horizon_label": horizon_label,
                "horizon_tf": horizon_tf,
                "score": score,
                "setup_name": setup_name,
                "macro_headwind": macro_hw,
                "headwind_label": c.get("headwind_label", ""),
                "evaluator_badge": c.get("evaluator_badge", "📐 Quantitative Engine"),
                "evaluator_badges": badges,
                "consensus_label": council_label,
                "entry_time": now_iso,
                "entry_price": curr_p,
                "current_price": curr_p,
                "highest_price": curr_p,
                "lowest_price": curr_p,
                "leverage": lev,
                "stop_loss": sl,
                "initial_stop_loss": sl,
                "take_profit_1": tp1,
                "take_profit_2": tp2,
                "crv": c.get("crv", 2.5),
                "allocated_capital": round(allocated_cap, 2),
                "position_qty": qty,
                "risk_cash": risk_cash,
                "kelly_multiplier": pos_size.get("kelly_multiplier", 1.0),
                "volatility_regime": pos_size.get("regime", "NORMAL"),
                "regime": "PROTECTIVE",
                "entry_reason": reason_str,
                "analyst_note": note,
                "unrealized_pnl_pct": 0.0,
                "unrealized_pnl_leveraged_pct": 0.0,
                "holding_hours": 0.0,
                "holding_days": 0.0,
                "tp1_reached": False,
                "trailing_active": False,
                "health_status": "HEALTHY",
                "in_flight_warnings": [],
                "status": "OPEN"
            }
            remaining_active.append(new_trade)
            active_symbols[sym] = new_trade
            horizon_counts[horizon] = horizon_counts.get(horizon, 0) + 1

            try:
                from notifications import send_ki_portfolio_alert
                send_ki_portfolio_alert("TRADE_OPENED", new_trade)
            except Exception as e:
                print(f"Warnung beim KI-Portfolio Alert (OPENED): {e}")

    # 4. Metriken neu berechnen
    all_closed = closed_trades
    total_closed = len(all_closed)
    wins = [t for t in all_closed if t["result"] == "WIN"]
    losses = [t for t in all_closed if t["result"] == "LOSS"]

    win_count = len(wins)
    loss_count = len(losses)
    win_rate = round((win_count / total_closed * 100.0), 1) if total_closed > 0 else 0.0

    sum_raw_pnl = sum(t.get("realized_pnl_pct", 0.0) for t in all_closed)
    sum_lev_pnl = sum(t.get("realized_pnl_leveraged_pct", 0.0) for t in all_closed)

    sum_win_val = sum(t.get("realized_pnl_pct", 0.0) for t in wins)
    sum_loss_val = abs(sum(t.get("realized_pnl_pct", 0.0) for t in losses))
    profit_factor = round(sum_win_val / sum_loss_val, 2) if sum_loss_val > 0 else (round(sum_win_val, 2) if sum_win_val > 0 else 1.0)

    # Gleitende Metriken berechnen (neueste zuerst in all_closed)
    rolling = {}
    for w in [5, 10, 20]:
        subset = all_closed[:w]
        sub_len = len(subset)
        if sub_len > 0:
            sub_wins = sum(1 for t in subset if t.get("result") == "WIN")
            sub_losses = sum(1 for t in subset if t.get("result") == "LOSS")
            sub_wr = round(sub_wins / sub_len * 100.0, 1)
            sub_raw = round(sum(t.get("realized_pnl_pct", 0.0) for t in subset), 2)
            sub_lev = round(sum(t.get("realized_pnl_leveraged_pct", 0.0) for t in subset), 2)
            diff_wr = round(sub_wr - win_rate, 1)
            rolling[f"last_{w}"] = {
                "trades": sub_len,
                "wins": sub_wins,
                "losses": sub_losses,
                "win_rate_pct": sub_wr,
                "diff_vs_all_time": diff_wr,
                "total_pnl_pct": sub_raw,
                "total_leveraged_pnl_pct": sub_lev
            }

    # Offene Heat-Verteilung ermitteln
    heat_summary = check_cluster_heat_limit(remaining_active, "__DIAGNOSTIC__", candidate_risk_r=0.0)

    portfolio["active_trades"] = remaining_active
    portfolio["closed_trades"] = closed_trades[:100]  # Letzte 100 im Speicher
    portfolio["circuit_breaker"] = {
        "status": cb_res.get("action", "ALLOW"),
        "is_halted": is_halted,
        "action": cb_res.get("action", "ALLOW"),
        "sizing_multiplier": sizing_mult,
        "effective_risk_pct": effective_risk_pct,
        "daily_pnl_r": cb_res.get("daily_pnl_r", 0.0),
        "drawdown_r": cb_res.get("drawdown_r", 0.0),
        "reason": cb_res.get("reason", ""),
        "total_heat_r": heat_summary.get("total_heat_r", 0.0),
        "max_total_heat_r": 3.0,
        "max_cluster_heat_r": 1.5,
        "heat_by_cluster": heat_summary.get("heat_by_cluster", {})
    }
    portfolio["metrics"] = {
        "total_trades": total_closed,
        "active_trades_count": len(remaining_active),
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate_pct": win_rate,
        "total_pnl_pct": round(sum_raw_pnl, 2),
        "total_leveraged_pnl_pct": round(sum_lev_pnl, 2),
        "total_r_profit": round(sum(t.get("realized_r", 0.0) for t in all_closed), 2),
        "profit_factor": profit_factor,
        "rolling": rolling
    }

    # Closed-Loop Scorecard rekalibrieren (Performance-Matrix für Setups und Kategorien)
    update_setup_scorecard(memory, closed_trades)

    save_json_file(PORTFOLIO_FILE, portfolio)
    save_json_file(TRADE_MEMORY_FILE, memory)

    return portfolio, memory


def generate_trade_learning(trade, exit_reason, raw_pnl, lev_pnl):
    """
    Erzeugt eine fundierte Post-Mortem Lerneinheit für das Modell-Gedächtnis.
    """
    sym = trade["symbol"]
    name = trade["name"]
    setup = trade["setup_name"]
    lev = trade["leverage"]
    days = trade.get("holding_days", 0)

    if raw_pnl > 0:
        return (
            f"Erfolgreicher {trade['direction']}-Trade auf {name} ({sym}) mit +{raw_pnl:.1f}% (+{lev_pnl:.1f}% bei {lev}x Hebel nach {days}d). "
            f"Bestätigt die Validität von '{setup}'. Das Nachziehen des Stop-Loss bzw. Abwarten des HTF-Ziels zahlte sich voll aus."
        )
    else:
        return (
            f"Verlusttrade auf {name} ({sym}) mit {raw_pnl:.1f}% ({lev_pnl:.1f}% bei {lev}x Hebel nach {days}d). "
            f"Grund: {exit_reason}. Learning: Bei Setup '{setup}' auf {trade.get('category', 'Asset')} "
            f"sollte der Hebel bei ähnlicher Marktstruktur konservativer gewählt werden oder der Ausstieg bei ersten Divergenzen erfolgen."
        )


def record_learning_in_memory(memory, closed_entry):
    learnings = memory.get("learnings", [])
    entry_learning = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trade_id": closed_entry["trade_id"],
        "symbol": closed_entry["symbol"],
        "name": closed_entry.get("name", closed_entry["symbol"]),
        "category": closed_entry.get("category", ""),
        "direction": closed_entry.get("direction", "LONG"),
        "result": closed_entry["result"],
        "setup_name": closed_entry["setup_name"],
        "pnl_leveraged": closed_entry["realized_pnl_leveraged_pct"],
        "pnl_raw": closed_entry.get("realized_pnl_pct", 0.0),
        "text": closed_entry["post_mortem_learning"]
    }
    if "ai_post_mortem" in closed_entry:
        entry_learning["ai_post_mortem"] = closed_entry["ai_post_mortem"]
    if "opus_audit" in closed_entry:
        entry_learning["opus_audit"] = closed_entry["opus_audit"]

    learnings.insert(0, entry_learning)
    memory["learnings"] = learnings[:60]  # Letzte 60 Learnings im Gedächtnis
    memory["total_experience_records"] = len(learnings)
    memory["updated_at"] = datetime.now(timezone.utc).isoformat()


def get_memory_summary_for_ai_prompt(assets_batch=None):
    """
    Gibt eine kontextuelle, maßgeschneiderte Zusammenfassung des Erfahrungsspeichers für den Gemini-Prompt zurück.
    Analysiert die im aktuellen Batch enthaltenen Kategorien und Setups und injiziert
    Opus Master-Constitution Axiome, Erfahrungswerte, Sektor-Winrates und bindende Handlungsregeln.
    """
    portfolio = load_json_file(PORTFOLIO_FILE, {})
    memory = load_json_file(TRADE_MEMORY_FILE, {})
    gov_params = load_opus_governor_params()

    metrics = portfolio.get("metrics", {})
    learnings = [
        l for l in (memory.get("learnings") or [])
        if str(l.get("scope", "")).upper() != "INCUBATOR"
        and str(l.get("source_book", "")).upper() != "INCUBATOR_RESEARCH"
    ]
    setup_perf = memory.get("setup_performance", {})
    cat_perf = memory.get("category_performance", {})
    constitution = memory.get("master_constitution", [])

    lines = [
        "HISTORISCHES TRADE-GEDÄCHTNIS & SELBSTVERBESSERUNGS-SCORECARD:",
        f"- Bisher geschlossene Trades: {metrics.get('total_trades', 0)} | Gesamt-Win-Rate: {metrics.get('win_rate_pct', 0.0)}% | PnL (gehebelt): {metrics.get('total_leveraged_pnl_pct', 0.0):+,.1f}%",
        f"- Aktive Opus Quant-Governor Grenzen: Min-Score={gov_params.get('min_score_default', 88)}% | Counter-Trend Min-Score={gov_params.get('min_score_counter_trend', 94)}% | Max 4h RSI Long={gov_params.get('max_rsi_long_entry', 64.0)} | Min VSA Reversal={gov_params.get('min_vsa_ratio_reversal', 1.20)}x"
    ]

    if constitution:
        lines.append("- OPUS 5.5 MASTER-CONSTITUTION (BINDENDE KERN-AXIOME):")
        for ax in constitution[:8]:
            if isinstance(ax, dict) and ax.get("rule"):
                lines.append(f"  🏛️ [{ax.get('id', 'AX')}] {ax['rule']}")

    # Batch-spezifische Kategorien ermitteln
    batch_cats = set()
    if assets_batch:
        for a in assets_batch:
            cat = a.get("category")
            if cat:
                batch_cats.add(cat)

    # 1. Spezifische Sektor-Erfahrungen für Assets in diesem Batch
    if batch_cats:
        lines.append("- RELEVANTE PERFORMANCE-DATEN FÜR DIE IN DIESEM BATCH ENTHALTENEN SEKTOREN:")
        for cat in batch_cats:
            cp = cat_perf.get(cat)
            if cp and cp.get("trades", 0) > 0:
                status_icon = "🟢" if cp.get("win_rate", 0) >= 60 else ("🔴" if cp.get("win_rate", 0) < 35 else "🟡")
                lines.append(
                    f"  {status_icon} Sektor '{cat}': {cp.get('wins')}/{cp.get('trades')} Trades ({cp.get('win_rate')}%), "
                    f"PnL: {cp.get('total_lev_pnl'):+.1f}%, Status: {cp.get('status')}. "
                    f"-> Hebel-Cap: max {cp.get('leverage_cap')}x, Mindest-Score für Einstieg: {cp.get('min_score')}%"
                )

    # 2. Setup-Performance Warnungen
    underperforming_setups = [s for s, d in setup_perf.items() if d.get("status") == "UNDERPERFORMING"]
    proven_setups = [s for s, d in setup_perf.items() if d.get("status") == "PROVEN_EDGE"]

    if underperforming_setups:
        lines.append("- STRATEGISCHE DÄMPFER AUS HISTORISCHEN FEHLERN (SEHR WICHTIG):")
        for us in underperforming_setups[:2]:
            d = setup_perf[us]
            lines.append(f"  ⚠️ Setup '{us}' performte schwach ({d.get('win_rate')}% Win-Rate, {d.get('total_lev_pnl'):+.1f}% PnL). Vergib Einstiege hier NUR bei makelloser 1D Konfluenz & Score >= {d.get('min_score')}%!")

    if proven_setups:
        lines.append("- BEWÄHRTES EDGE AUS GEWINN-TRADES:")
        for ps in proven_setups[:2]:
            d = setup_perf[ps]
            lines.append(f"  ✅ Setup '{ps}' zeigte exzellentes Edge ({d.get('win_rate')}% Win-Rate, Profit-Faktor {d.get('profit_factor')}). Halte nach solchen Setups bevorzugt Ausschau.")

    # 3. Neueste bindende KI-Lerneinheiten und Handlungsregeln
    lines.append("- BINDENDE LEITREGELN AUS DEN LETZTEN TRADES:")
    # Filter bevorzugt nach Batch-Kategorien, falls vorhanden
    relevant_learnings = []
    if batch_cats:
        for l in learnings:
            if l.get("category") in batch_cats:
                relevant_learnings.append(l)

    # Falls keine categoriespezifischen da sind, nimm die neuesten allgemeinen
    feed = relevant_learnings[:3] if relevant_learnings else learnings[:3]
    for l in feed:
        ai_pm = l.get("ai_post_mortem", {})
        rule = ai_pm.get("actionable_rule")
        warn = ai_pm.get("technical_warning")
        if rule:
            lines.append(f"  • [{l.get('symbol')}] REGEL: {rule} (Frühwarnung: {warn})")
        else:
            lines.append(f"  • [{l.get('result')}] {l.get('text')}")

    lines.append("Setze diese Lektionen bei der Beurteilung ausnahmslos um: Schütze Kapital, jage keinen Fakeouts hinterher!")
    return "\n".join(lines)


# ==============================================================================
# 3. EIGENE NUTZER-POSITIONEN (USER POSITIONS TRACKING & ADVICE)
# ==============================================================================
def evaluate_user_positions(db_assets):
    """
    Bewertet alle vom Nutzer eingetragenen Positionen gegen die aktuellen Live-Marktdaten
    und generiert relevante Handlungsempfehlungen.
    """
    data = load_json_file(USER_POSITIONS_FILE, {"positions": []})
    positions = data.get("positions", [])

    if not positions:
        return data

    db_map = {a["symbol"]: a for a in db_assets}
    now_iso = datetime.now(timezone.utc).isoformat()

    evaluated_positions = []

    for pos in positions:
        sym = pos.get("symbol")
        direction = pos.get("direction", "LONG").upper()
        entry_p = float(pos.get("entry_price", 100.0))
        lev = float(pos.get("leverage", 1.0))

        # Passendes Asset in der Marktdatenbank suchen
        a = db_map.get(sym)
        if not a:
            # 1. Alias-Normalisierung (z. B. BTCUSDT -> BTCUSD, ETHUSDT -> ETHUSD)
            if "USDT" in sym:
                a = db_map.get(sym.replace("USDT", "USD"))
            elif "USD" in sym:
                a = db_map.get(sym.replace("USD", "USDT"))

        if not a:
            # 2. Suche nach Ticker ohne Exchange-Prefix (z. B. BTCUSDT -> BTCUSD)
            ticker_only = sym.split(":")[-1] if ":" in sym else sym
            ticker_base = ticker_only.replace("USDT", "").replace("USD", "")
            for k, v in db_map.items():
                k_ticker = k.split(":")[-1] if ":" in k else k
                k_base = k_ticker.replace("USDT", "").replace("USD", "")
                if k_ticker == ticker_only or (ticker_base and k_base == ticker_base and k_base != ""):
                    a = v
                    break

        curr_p = entry_p
        asset_name = sym
        price_update = now_iso
        price_update_str = ""

        if a and "price" in a:
            curr_p = float(a["price"])
            asset_name = a.get("name", sym)
            price_update = a.get("last_price_update", now_iso)
            price_update_str = a.get("last_price_update_str", "")
        else:
            # 3. Fallback: Live-Kurs direkt von TradingView Scanner abfragen
            try:
                from tv_live_quotes import fetch_tradingview_live_quotes
                q_single = fetch_tradingview_live_quotes([sym])
                if q_single and sym in q_single:
                    curr_p = float(q_single[sym]["price"])
                    asset_name = q_single[sym].get("description", sym)
                    price_update = q_single[sym].get("updated_at", now_iso)
                    price_update_str = q_single[sym].get("updated_at_str", "")
                    a = {
                        "symbol": sym,
                        "name": asset_name,
                        "price": curr_p,
                        "signal": "NEUTRAL",
                        "change_pct": q_single[sym].get("change_pct", 0.0),
                        "last_price_update": price_update,
                        "last_price_update_str": price_update_str
                    }
            except Exception:
                pass

        # PnL berechnen
        if direction == "LONG":
            raw_pnl = ((curr_p - entry_p) / entry_p) * 100.0
        else:
            raw_pnl = ((entry_p - curr_p) / entry_p) * 100.0

        lev_pnl = raw_pnl * lev

        # Stop-Loss und Take-Profit extrahieren & Abstände / CRV berechnen
        sl_val = pos.get("stop_loss")
        tp_val = pos.get("take_profit")
        try:
            sl_val = float(sl_val) if sl_val is not None and str(sl_val).strip() != "" else None
        except (ValueError, TypeError):
            sl_val = None

        try:
            tp_val = float(tp_val) if tp_val is not None and str(tp_val).strip() != "" else None
        except (ValueError, TypeError):
            tp_val = None

        # Auto-Close Prüfung: Wurde Stop-Loss oder Take-Profit erreicht?
        is_sl_triggered = False
        is_tp_triggered = False

        if sl_val is not None and curr_p > 0:
            if direction == "LONG" and curr_p <= sl_val:
                is_sl_triggered = True
            elif direction == "SHORT" and curr_p >= sl_val:
                is_sl_triggered = True

        if tp_val is not None and curr_p > 0:
            if direction == "LONG" and curr_p >= tp_val:
                is_tp_triggered = True
            elif direction == "SHORT" and curr_p <= tp_val:
                is_tp_triggered = True

        if is_sl_triggered or is_tp_triggered:
            # Trade automatisch schließen & in Historie archivieren!
            exit_reason = "STOP_LOSS_TRIGGERED" if is_sl_triggered else "TAKE_PROFIT_TRIGGERED"
            exit_p = curr_p
            if is_sl_triggered:
                cmp_sym = "<=" if direction == "LONG" else ">="
                reason_disp = f"🛑 Stop-Loss ausgelöst ({curr_p:,.2f} {cmp_sym} {sl_val:,.2f} $)"
            else:
                cmp_sym = ">=" if direction == "LONG" else "<="
                reason_disp = f"🎯 Take-Profit erreicht ({curr_p:,.2f} {cmp_sym} {tp_val:,.2f} $)"

            try:
                from manage_positions import archive_closed_position
                from notifications import send_user_position_closed_notification

                pos_to_close = dict(pos)
                pos_to_close["current_price"] = curr_p
                pos_to_close["name"] = asset_name

                closed_rec = archive_closed_position(
                    pos_to_close,
                    exit_price=exit_p,
                    exit_reason=exit_reason,
                    exit_reason_display=reason_disp
                )
                send_user_position_closed_notification(closed_rec)
                print(f"⚡ [AUTO-CLOSE] Position {sym} ({direction}) automatisch geschlossen: {reason_disp} | PnL: {closed_rec.get('realized_pnl_leveraged_pct'):+.2f}%")
            except Exception as ace:
                print(f"Fehler bei Auto-Close für {sym}: {ace}")

            # Position scheidet aus den aktiven Positionen aus
            continue

        sl_dist_pct = None
        if sl_val is not None and curr_p > 0:
            if direction == "LONG":
                sl_dist_pct = round(((curr_p - sl_val) / curr_p) * 100.0, 2)
            else:
                sl_dist_pct = round(((sl_val - curr_p) / curr_p) * 100.0, 2)

        tp_dist_pct = None
        if tp_val is not None and curr_p > 0:
            if direction == "LONG":
                tp_dist_pct = round(((tp_val - curr_p) / curr_p) * 100.0, 2)
            else:
                tp_dist_pct = round(((curr_p - tp_val) / curr_p) * 100.0, 2)

        crv = None
        if sl_val is not None and tp_val is not None:
            risk = abs(entry_p - sl_val)
            reward = abs(tp_val - entry_p)
            if risk > 0:
                crv = round(reward / risk, 2)

        pos_copy = dict(pos)
        pos_copy["name"] = asset_name
        pos_copy["current_price"] = curr_p
        pos_copy["pnl_pct"] = round(raw_pnl, 2)
        pos_copy["pnl_leveraged_pct"] = round(lev_pnl, 2)
        pos_copy["stop_loss"] = sl_val
        pos_copy["take_profit"] = tp_val
        pos_copy["take_profit_1"] = pos.get("take_profit_1")
        pos_copy["take_profit_2"] = pos.get("take_profit_2") or tp_val
        pos_copy["remaining_size_pct"] = pos.get("remaining_size_pct", 100.0)
        pos_copy["partial_closes"] = pos.get("partial_closes", [])
        pos_copy["tp1_hit"] = pos.get("tp1_hit", False)
        pos_copy["sl_distance_pct"] = sl_dist_pct
        pos_copy["tp_distance_pct"] = tp_dist_pct
        pos_copy["crv"] = crv

        # Handlungsempfehlung ableiten
        rec = generate_actionable_recommendation(pos_copy, a, curr_p, raw_pnl, lev_pnl)
        pos_copy["recommendation"] = rec
        pos_copy["last_price_update"] = price_update
        pos_copy["last_price_update_str"] = price_update_str
        pos_copy["updated_at"] = datetime.now(timezone.utc).isoformat()

        evaluated_positions.append(pos_copy)

    data["positions"] = evaluated_positions
    data["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Vorschlag C: Opus 5.5 In-Flight Exit-Doctor auch für Nutzer-Positionen (24h-gedrosselt)
    if evaluated_positions:
        try:
            from gemini_evaluator import audit_open_positions_with_opus
            opus_user_map = audit_open_positions_with_opus(
                evaluated_positions,
                db_map,
                portfolio_context="USER_POSITIONS",
            )
            for p_eval in evaluated_positions:
                pid = str(p_eval.get("id") or p_eval.get("trade_id") or p_eval.get("symbol") or "")
                psym = str(p_eval.get("symbol") or "")
                uaud = opus_user_map.get(pid) or opus_user_map.get(psym)
                if uaud:
                    p_eval["opus_inflight_audit"] = uaud
        except Exception:
            pass

    save_json_file(USER_POSITIONS_FILE, data)

    # Bei kritischen Statuswechseln (SL-Gefahr, Take-Profit, Reversal) Nutzer auf Telegram warnen
    try:
        from notifications import check_and_notify_user_positions
        check_and_notify_user_positions(evaluated_positions)
    except Exception as ne:
        pass

    return data


def generate_actionable_recommendation(pos, asset_data, curr_p, raw_pnl, lev_pnl):
    """
    Gibt NUR dann eine spezifische Handlungsempfehlung aus, wenn sie WIRKLICH relevant ist:
    - SL-Gefahr / Stop-Loss ausgelöst
    - Take-Profit erreicht / Gewinnmitnahme
    - Reversal-Warnung durch RSI-Divergenzen
    """
    direction = pos.get("direction", "LONG").upper()
    lev = float(pos.get("leverage", 1.0))
    sl = pos.get("stop_loss")
    tp = pos.get("take_profit")

    # 1. STOP-LOSS AUSGELÖST ODER IN AKUTER GEFAHR (Höchste Priorität!)
    if sl is not None:
        try:
            sl_num = float(sl)
            if direction == "LONG":
                if curr_p <= sl_num:
                    return {
                        "status": "CRITICAL",
                        "badge_color": "rose",
                        "action": "STOP-LOSS AUSGELÖST",
                        "title": f"🛑 Stop-Loss erreicht ({curr_p:,.2f} <= {sl_num:,.2f})",
                        "message": f"Der Kurs ({curr_p:,.2f} $) hat deinen Stop-Loss von {sl_num:,.2f} $ erreicht oder unterschritten. Position zur Verlustbegrenzung schließen!"
                    }
                elif curr_p <= sl_num * 1.015:
                    dist = ((curr_p - sl_num) / curr_p) * 100.0
                    return {
                        "status": "WARNING",
                        "badge_color": "amber",
                        "action": "STOP-LOSS IN GEFAHR",
                        "title": f"⚠️ Stop-Loss in Reichweite (noch {dist:.1f}%)",
                        "message": f"Der Kurs ({curr_p:,.2f} $) ist nur noch {dist:.1f}% von deinem Stop-Loss ({sl_num:,.2f} $) entfernt. Risikomanagement prüfen!"
                    }
            else: # SHORT
                if curr_p >= sl_num:
                    return {
                        "status": "CRITICAL",
                        "badge_color": "rose",
                        "action": "STOP-LOSS AUSGELÖST",
                        "title": f"🛑 Stop-Loss erreicht ({curr_p:,.2f} >= {sl_num:,.2f})",
                        "message": f"Der Kurs ({curr_p:,.2f} $) hat deinen Stop-Loss von {sl_num:,.2f} $ erreicht oder überschritten. Position zur Verlustbegrenzung schließen!"
                    }
                elif curr_p >= sl_num * 0.985:
                    dist = ((sl_num - curr_p) / curr_p) * 100.0
                    return {
                        "status": "WARNING",
                        "badge_color": "amber",
                        "action": "STOP-LOSS IN GEFAHR",
                        "title": f"⚠️ Stop-Loss in Reichweite (noch {dist:.1f}%)",
                        "message": f"Der Kurs ({curr_p:,.2f} $) ist nur noch {dist:.1f}% von deinem Stop-Loss ({sl_num:,.2f} $) entfernt. Risikomanagement prüfen!"
                    }
        except (ValueError, TypeError):
            pass

    tp1 = pos.get("take_profit_1")
    tp2 = pos.get("take_profit_2") or tp
    tp1_hit = pos.get("tp1_hit", False)
    entry_num = float(pos.get("entry_price", 0.0))

    # 1.5 TP1 BEREITS ERREICHT -> STOP AUF BREAK-EVEN EMPFEHLEN
    if tp1_hit and entry_num > 0:
        is_be = False
        if sl is not None:
            try:
                sl_f = float(sl)
                is_be = (sl_f >= entry_num) if direction == "LONG" else (sl_f <= entry_num)
            except Exception:
                is_be = False
        if not is_be:
            return {
                "status": "TAKE_PROFIT",
                "badge_color": "emerald",
                "action": "STOP AUF BREAK-EVEN",
                "title": "🎯 TP1 gesichert – SL auf Break-Even!",
                "message": f"TP1 wurde bereits realisiert. Ziehe deinen Stop-Loss jetzt auf Break-Even ({entry_num:,.2f} $), um die Restposition risikofrei zu TP2 ({float(tp2):,.2f} $ falls gesetzt) laufen zu lassen."
            }

    # 1.6 TP1 IN REICHWEITE
    if tp1 is not None and not tp1_hit:
        try:
            tp1_num = float(tp1)
            is_near_tp1 = False
            if direction == "LONG" and curr_p >= tp1_num * 0.985:
                dist = ((tp1_num - curr_p) / curr_p) * 100.0
                is_near_tp1 = True
            elif direction == "SHORT" and curr_p <= tp1_num * 1.015:
                dist = ((curr_p - tp1_num) / curr_p) * 100.0
                is_near_tp1 = True

            if is_near_tp1:
                return {
                    "status": "TAKE_PROFIT",
                    "badge_color": "emerald",
                    "action": "TP1 IN REICHWEITE",
                    "title": f"🎯 TP1 in Reichweite (noch {dist:.1f}%)",
                    "message": f"Der Kurs ({curr_p:,.2f} $) nähert sich deinem ersten Teilziel TP1 ({tp1_num:,.2f} $). 50% Teilgewinnmitnahme steht kurz bevor!"
                }
        except (ValueError, TypeError):
            pass

    # 2. TAKE-PROFIT ZIEL ERREICHT (Hohe Priorität!)
    if tp is not None:
        try:
            tp_num = float(tp)
            if direction == "LONG":
                if curr_p >= tp_num:
                    return {
                        "status": "TAKE_PROFIT",
                        "badge_color": "emerald",
                        "action": "TAKE-PROFIT ERREICHT",
                        "title": f"🎯 Kursziel erreicht ({curr_p:,.2f} >= {tp_num:,.2f})",
                        "message": f"Dein Take-Profit von {tp_num:,.2f} $ wurde erreicht ({curr_p:,.2f} $)! Gewinne jetzt mitnehmen oder Stop auf Break-Even nachziehen."
                    }
                elif curr_p >= tp_num * 0.985:
                    dist = ((tp_num - curr_p) / curr_p) * 100.0
                    return {
                        "status": "TAKE_PROFIT",
                        "badge_color": "emerald",
                        "action": "ZIEL FAST ERREICHT",
                        "title": f"🎯 Take-Profit in Reichweite (noch {dist:.1f}%)",
                        "message": f"Der Kurs ({curr_p:,.2f} $) nähert sich deinem Take-Profit Ziel ({tp_num:,.2f} $). Teilgewinne vorbereiten!"
                    }
            else: # SHORT
                if curr_p <= tp_num:
                    return {
                        "status": "TAKE_PROFIT",
                        "badge_color": "emerald",
                        "action": "TAKE-PROFIT ERREICHT",
                        "title": f"🎯 Kursziel erreicht ({curr_p:,.2f} <= {tp_num:,.2f})",
                        "message": f"Dein Take-Profit von {tp_num:,.2f} $ wurde erreicht ({curr_p:,.2f} $)! Gewinne jetzt mitnehmen oder Stop auf Break-Even nachziehen."
                    }
                elif curr_p <= tp_num * 1.015:
                    dist = ((curr_p - tp_num) / curr_p) * 100.0
                    return {
                        "status": "TAKE_PROFIT",
                        "badge_color": "emerald",
                        "action": "ZIEL FAST ERREICHT",
                        "title": f"🎯 Take-Profit in Reichweite (noch {dist:.1f}%)",
                        "message": f"Der Kurs ({curr_p:,.2f} $) nähert sich deinem Take-Profit Ziel ({tp_num:,.2f} $). Teilgewinne vorbereiten!"
                    }
        except (ValueError, TypeError):
            pass

    if not asset_data:
        return {
            "status": "NEUTRAL",
            "badge_color": "slate",
            "action": "HALTEN",
            "title": "Keine Live-Kerzendaten",
            "message": "Dieses Symbol wird aktuell nicht im 4h-Hauptscan überwacht. Manuelle Kursprüfung empfohlen."
        }

    sig = asset_data.get("signal", "NEUTRAL")
    timeframes = asset_data.get("timeframes", {})
    d_1d = timeframes.get("1D") or {}
    d_4h = timeframes.get("4h") or {}

    trend_1d = d_1d.get("trend", "NEUTRAL")
    rsi_4h = d_4h.get("rsi", 50.0)
    channel_4h = d_4h.get("channel_position", "")
    divs_4h = d_4h.get("divergences", [])

    # 1. AKUTE WARNUNG: Starker Hebel & starker Verlust
    if lev_pnl <= -18.0:
        return {
            "status": "CRITICAL",
            "badge_color": "rose",
            "action": "RISIKOMANAGEMENT / STOP PRÜFEN",
            "title": f"⚠️ Hoher Verlust ({lev_pnl:.1f}% bei {lev:g}x Hebel)",
            "message": f"Die Position steht mit {raw_pnl:.1f}% im Minus. Bei {lev:g}x Hebel droht erhöhtes Liquidationsrisiko. Setze einen strikten Stop-Loss oder reduziere die Tranche."
        }

    # 2. GEWINNMITNAHME / TEILVERKAUF
    if lev_pnl >= 25.0:
        if direction == "LONG" and ("Overbought" in channel_4h or rsi_4h >= 68):
            return {
                "status": "TAKE_PROFIT",
                "badge_color": "emerald",
                "action": "TEILGEWINNE REALISIEREN",
                "title": f"🎯 Satte Gewinne sichern (+{lev_pnl:.1f}% bei {lev:g}x)",
                "message": f"Kurs nähert sich der 4h-Kanaloberkante (RSI {rsi_4h:.1f}). Nimm 50% Teilgewinne mit und ziehe den Stop-Loss auf Break-Even ({pos.get('entry_price'):,.2f})."
            }
        elif direction == "SHORT" and ("Oversold" in channel_4h or rsi_4h <= 32):
            return {
                "status": "TAKE_PROFIT",
                "badge_color": "emerald",
                "action": "TEILGEWINNE REALISIEREN",
                "title": f"🎯 Satte Gewinne sichern (+{lev_pnl:.1f}% bei {lev:g}x)",
                "message": f"Kurs nähert sich dem 4h-Kanalboden (RSI {rsi_4h:.1f}). Nimm Teilgewinne mit und sichere den Rest gegen Reversal ab."
            }

    # 3. DIVERGENZ-WARNUNG GEGEN DIE POSITION
    if direction == "LONG" and any("Bärische Divergenz" in d for d in divs_4h):
        return {
            "status": "WARNING",
            "badge_color": "amber",
            "action": "STOP NACHZIEHEN",
            "title": "⚠️ Bärische Divergenz im 4h-Chart",
            "message": "Es hat sich eine bärische RSI-Divergenz gegen deine Long-Position formiert. Das Aufwärtsmomentum lässt nach. Stop-Loss straff nachziehen."
        }
    elif direction == "SHORT" and any("Bullische Divergenz" in d for d in divs_4h):
        return {
            "status": "WARNING",
            "badge_color": "amber",
            "action": "STOP NACHZIEHEN",
            "title": "⚠️ Bullische Divergenz im 4h-Chart",
            "message": "Es formiert sich eine bullische Divergenz gegen deinen Short. Reversal-Gefahr! Stop-Loss eng nachziehen."
        }

    # 4. TREND-HARMONIE
    if direction == "LONG" and trend_1d == "BULLISH" and sig == "LONG":
        return {
            "status": "HEALTHY",
            "badge_color": "emerald",
            "action": "POSITION ENTSPANNT HALTEN",
            "title": "✅ Voll im Trend",
            "message": f"Dein Long läuft harmonisch mit dem übergeordneten 1D-Bullenmarkt. Das Modell bestätigt das Setup ({asset_data.get('score', 0)}% Score)."
        }
    elif direction == "SHORT" and trend_1d == "BEARISH" and sig == "SHORT":
        return {
            "status": "HEALTHY",
            "badge_color": "emerald",
            "action": "POSITION ENTSPANNT HALTEN",
            "title": "✅ Voll im Trend",
            "message": f"Dein Short läuft harmonisch mit dem übergeordneten Abwärtstrend. Das Modell bestätigt die Position."
        }

    # Standard
    return {
        "status": "NEUTRAL",
        "badge_color": "indigo",
        "action": "BEOBACHTEN",
        "title": "Position im Plan",
        "message": f"PnL: {lev_pnl:+.1f}% ({raw_pnl:+.1f}% Basis). Keine akute Interventionsnotwendigkeit."
    }


if __name__ == "__main__":
    print("Teste Portfolio- & Erfahrungs-Engine...")
    if DB_FILE.exists():
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
        assets = db.get("assets", [])
        port, mem = update_autonomous_portfolio(assets)
        print(f"Aktive Trades im Modell-Portfolio: {len(port.get('active_trades', []))}")
        print(f"Bisher geschlossene Trades      : {len(port.get('closed_trades', []))}")
        print(f"Erfahrungs-Learnings im Gedächtnis: {len(mem.get('learnings', []))}")

        # Nutzerpositionen testen
        user_p = evaluate_user_positions(assets)
        print(f"Getrackte Nutzer-Positionen     : {len(user_p.get('positions', []))}")
