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

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"
PORTFOLIO_FILE = BASE_DIR / "knowledge_base" / "autonomous_portfolio.json"
TRADE_MEMORY_FILE = BASE_DIR / "knowledge_base" / "trade_memory.json"
USER_POSITIONS_FILE = BASE_DIR / "knowledge_base" / "user_positions.json"


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


def calculate_optimal_leverage(asset_type, category, current_price, stop_loss, score, setup_name=None, memory=None):
    """
    Berechnet den verantwortungsvollen Hebel (1x bis max 10x):
    - Berücksichtigt Asset-Klasse (Krypto max 2-3x, Aktien 3-5x, Indizes 5-8x, Rohstoffe 4-6x)
    - Liquidationsschutz: Stop-Loss muss weit vor einer theoretischen Liquidation liegen
    - Score-Bonus nur bei extrem hoher Konfluenz (Score >= 92%)
    - CLOSED-LOOP SCORECARD GOVERNOR: Drosselt den Hebel automatisch, falls Kategorie oder Setup
      in der historischen Auswertung unterdurchschnittlich abgeschnitten haben!
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

        # 1. Divergenz- & Gegen-Signal Früherkennung
        divs_4h = []
        tf_4h = live_asset.get("4h", {})
        if isinstance(tf_4h, dict):
            divs_4h = tf_4h.get("divs", [])

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

            # Profit Locking: Wenn Gewinn >= 2.5% und neuer Peak erreicht, Trailing Stop auf 50% des Peaks
            if raw_pnl >= 2.5:
                trail_level = entry_price + (t["highest_price"] - entry_price) * 0.5
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

            if raw_pnl >= 2.5:
                trail_level = entry_price - (entry_price - t["lowest_price"]) * 0.5
                if trail_level < current_sl:
                    t["stop_loss"] = round(trail_level, 4)
                    t["trailing_active"] = True
                    health = "TRAILING_STOP"

        t["health_status"] = health


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

    db_map = {a["symbol"]: a for a in db_assets}

    # 1. Bestehende offene Trades prüfen & aktualisieren
    remaining_active = []
    newly_closed = []

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

        curr_price = a.get("price", t.get("current_price", t["entry_price"]))
        direction = t["direction"]
        entry_price = t["entry_price"]
        lev = t.get("leverage", 1)
        sl = t.get("stop_loss", 0.0)
        tp1 = t.get("take_profit_1", 0.0)
        tp2 = t.get("take_profit_2", 0.0)

        # Zeitberechnung
        try:
            entry_dt = datetime.fromisoformat(t["entry_time"])
            holding_hours = round((now_dt - entry_dt).total_seconds() / 3600.0, 1)
            holding_days = round(holding_hours / 24.0, 1)
        except Exception:
            holding_hours = 0.0
            holding_days = 0.0

        # PnL Berechnung
        if direction == "LONG":
            raw_pnl_pct = ((curr_price - entry_price) / entry_price) * 100.0
        else:
            raw_pnl_pct = ((entry_price - curr_price) / entry_price) * 100.0

        leveraged_pnl_pct = raw_pnl_pct * lev

        # Höchst- und Tiefststand updaten
        t["highest_price"] = max(t.get("highest_price", curr_price), curr_price)
        t["lowest_price"] = min(t.get("lowest_price", curr_price), curr_price)
        t["current_price"] = curr_price
        t["last_price_update"] = a.get("last_price_update", now_iso)
        t["last_price_update_str"] = a.get("last_price_update_str", "")
        t["unrealized_pnl_pct"] = round(raw_pnl_pct, 2)
        t["unrealized_pnl_leveraged_pct"] = round(leveraged_pnl_pct, 2)
        t["holding_hours"] = holding_hours
        t["holding_days"] = holding_days

        # AUSSTIEGS-LOGIK (DYMANISCH & MULTI-DAY)
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
            elif direction == "LONG" and tp1 > 0 and curr_price >= tp1 and t.get("tp1_reached") is not True:
                t["tp1_reached"] = True
                t["stop_loss"] = entry_price  # Stop-Loss auf Break-Even nachziehen!
                t["trailing_active"] = True
            elif direction == "SHORT" and tp1 > 0 and curr_price <= tp1 and t.get("tp1_reached") is not True:
                t["tp1_reached"] = True
                t["stop_loss"] = entry_price  # Stop-Loss auf Break-Even nachziehen!
                t["trailing_active"] = True

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

        if exit_triggered:
            # Trade abschließen
            final_raw_pnl = ((exit_price - entry_price) / entry_price) * 100.0 if direction == "LONG" else ((entry_price - exit_price) / entry_price) * 100.0
            final_lev_pnl = final_raw_pnl * lev
            is_win = final_raw_pnl > 0

            closed_entry = {
                "trade_id": t["trade_id"],
                "symbol": t["symbol"],
                "name": t["name"],
                "category": t.get("category", ""),
                "direction": direction,
                "score": t["score"],
                "setup_name": t["setup_name"],
                "entry_time": t["entry_time"],
                "entry_price": entry_price,
                "exit_time": now_iso,
                "exit_price": exit_price,
                "highest_price": t.get("highest_price", entry_price),
                "lowest_price": t.get("lowest_price", entry_price),
                "leverage": lev,
                "holding_days": holding_days,
                "entry_reason": t["entry_reason"],
                "exit_reason": exit_reason,
                "realized_pnl_pct": round(final_raw_pnl, 2),
                "realized_pnl_leveraged_pct": round(final_lev_pnl, 2),
                "result": "WIN" if is_win else ("LOSS" if final_raw_pnl < 0 else "BREAKEVEN"),
            }

            # Tiefgehende KI-Post-Mortem-Analyse via Gemini 3.8 Flash (Account 2)
            try:
                from gemini_evaluator import evaluate_trade_post_mortem
                ai_post_mortem = evaluate_trade_post_mortem(closed_entry)
            except Exception:
                ai_post_mortem = None

            if ai_post_mortem and isinstance(ai_post_mortem, dict):
                closed_entry["ai_post_mortem"] = ai_post_mortem
                closed_entry["post_mortem_learning"] = ai_post_mortem.get("summary_text", generate_trade_learning(t, exit_reason, final_raw_pnl, final_lev_pnl))
            else:
                learning_note = generate_trade_learning(t, exit_reason, final_raw_pnl, final_lev_pnl)
                closed_entry["post_mortem_learning"] = learning_note

            closed_trades.insert(0, closed_entry)
            newly_closed.append(closed_entry)

            # Gedächtnis updaten
            record_learning_in_memory(memory, closed_entry)
        else:
            remaining_active.append(t)

    # 2. In-Flight Überwachung aller verbleibenden aktiven Trades
    monitor_in_flight_trades(remaining_active, db_map)

    # 3. Neue High-Conviction Setups aufnehmen (Score >= 88%, Signal != NEUTRAL)
    # Maximal 8 gleichzeitig aktive Positionen für optimale Diversifikation
    max_active_positions = 8
    
    if len(remaining_active) < max_active_positions:
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

            # CLOSED-LOOP SCORECARD FILTER: Dynamischer Mindest-Score
            setup_perf = memory.get("setup_performance", {}).get(setup_name, {})
            cat_perf = memory.get("category_performance", {}).get(cat, {})
            min_score_req = max(88, setup_perf.get("min_score", 88), cat_perf.get("min_score", 88))

            if score < min_score_req:
                print(f"   🛡️ [Scorecard Guard] {sym} ({setup_name} in {cat}) übersprungen: Score {score}% < Mindestanforderung von {min_score_req}%")
                continue

            sl = c.get("stop_loss", curr_p * 0.95)
            tp1 = c.get("take_profit_1", curr_p * 1.05)
            tp2 = c.get("take_profit_2", curr_p * 1.10)

            # Automatische Hebel-Ermittlung mit Scorecard-Feedback
            lev = calculate_optimal_leverage(asset_type, cat, curr_p, sl, score, setup_name=setup_name, memory=memory)

            # Fundierte Begründung zusammenstellen
            reasons = c.get("reasons", [])
            note = c.get("analyst_note", "")
            reason_str = " | ".join(reasons[:2]) if reasons else note
            if not reason_str:
                reason_str = f"Hohe Multi-Timeframe Konfluenz ({score}% Score) mit CRV {c.get('crv', 2.5)}:1"

            new_trade = {
                "trade_id": f"trade_{sym.replace(':', '_')}_{now_dt.strftime('%Y%m%d_%H%M')}",
                "symbol": sym,
                "name": c["name"],
                "category": cat,
                "asset_type": asset_type,
                "direction": c["signal"],
                "score": score,
                "setup_name": setup_name,
                "entry_time": now_iso,
                "entry_price": curr_p,
                "current_price": curr_p,
                "highest_price": curr_p,
                "lowest_price": curr_p,
                "leverage": lev,
                "stop_loss": sl,
                "take_profit_1": tp1,
                "take_profit_2": tp2,
                "crv": c.get("crv", 2.5),
                "allocated_capital": 1000.0,
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

    portfolio["active_trades"] = remaining_active
    portfolio["closed_trades"] = closed_trades[:100]  # Letzte 100 im Speicher
    portfolio["metrics"] = {
        "total_trades": total_closed,
        "active_trades_count": len(remaining_active),
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate_pct": win_rate,
        "total_pnl_pct": round(sum_raw_pnl, 2),
        "total_leveraged_pnl_pct": round(sum_lev_pnl, 2),
        "profit_factor": profit_factor
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

    learnings.insert(0, entry_learning)
    memory["learnings"] = learnings[:60]  # Letzte 60 Learnings im Gedächtnis
    memory["total_experience_records"] = len(learnings)
    memory["updated_at"] = datetime.now(timezone.utc).isoformat()


def get_memory_summary_for_ai_prompt(assets_batch=None):
    """
    Gibt eine kontextuelle, maßgeschneiderte Zusammenfassung des Erfahrungsspeichers für den Gemini-Prompt zurück.
    Analysiert die im aktuellen Batch enthaltenen Kategorien und Setups und injiziert
    präzise Erfahrungswerte, Sektor-Winrates und bindende Handlungsregeln aus vergangenen Trades.
    """
    portfolio = load_json_file(PORTFOLIO_FILE, {})
    memory = load_json_file(TRADE_MEMORY_FILE, {})

    metrics = portfolio.get("metrics", {})
    learnings = memory.get("learnings", [])
    setup_perf = memory.get("setup_performance", {})
    cat_perf = memory.get("category_performance", {})

    lines = [
        "HISTORISCHES TRADE-GEDÄCHTNIS & SELBSTVERBESSERUNGS-SCORECARD:",
        f"- Bisher geschlossene Trades: {metrics.get('total_trades', 0)} | Gesamt-Win-Rate: {metrics.get('win_rate_pct', 0.0)}% | PnL (gehebelt): {metrics.get('total_leveraged_pnl_pct', 0.0):+,.1f}%"
    ]

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

        # Handlungsempfehlung ableiten
        rec = generate_actionable_recommendation(pos, a, curr_p, raw_pnl, lev_pnl)

        pos_copy = dict(pos)
        pos_copy["name"] = asset_name
        pos_copy["current_price"] = curr_p
        pos_copy["pnl_pct"] = round(raw_pnl, 2)
        pos_copy["pnl_leveraged_pct"] = round(lev_pnl, 2)
        pos_copy["recommendation"] = rec
        pos_copy["last_price_update"] = price_update
        pos_copy["last_price_update_str"] = price_update_str
        pos_copy["updated_at"] = datetime.now(timezone.utc).isoformat()

        evaluated_positions.append(pos_copy)

    data["positions"] = evaluated_positions
    data["updated_at"] = datetime.now(timezone.utc).isoformat()

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
    - SL-Gefahr / Strukturbruch
    - Gewinnmitnahme (TP1 / TP2 / Überdehnung im Band)
    - Reversal-Warnung durch RSI-Divergenzen
    """
    direction = pos.get("direction", "LONG").upper()
    lev = float(pos.get("leverage", 1.0))

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
