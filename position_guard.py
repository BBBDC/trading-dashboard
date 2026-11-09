#!/usr/bin/env python3
"""
TradingView Super-Analyst – High-Speed Position Guard (5-Minuten-Takt).
Überwacht alle aktiven Nutzer-Positionen ("Meine Positionen") auf 5m- und 15m-Ebene:
1. Ruft echte Live-Kerzen von Binance (Krypto 24/7) und Yahoo Finance (Aktien) ab.
2. Berechnet exakte PnL-, Hebel-, CRV- und SL/TP-Abstände in Echtzeit.
3. Führt Auto-Close bei Erreichen von Hard-SL oder TP durch.
4. Berechnet degencoder-Indikatoren (Order Blocks, Sweeps, Chaos-Bänder, VSA, Divergenzen).
5. Bewertet jede Position mit Google Gemini 3.8 Flash High (inklusive Math-Fallback).
6. Sendet gezielte Push-Benachrichtigungen per Telegram bei Risiken oder Gewinnmitnahmen.
7. Hält user_positions.json und market_analysis_db.json stets auf dem neuesten Stand.
"""

import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent
POSITIONS_FILE = BASE_DIR / "knowledge_base" / "user_positions.json"
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("position_guard")


def load_user_positions() -> List[Dict[str, Any]]:
    if not POSITIONS_FILE.exists():
        return []
    try:
        with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data.get("positions", [])
            elif isinstance(data, list):
                return data
    except Exception as e:
        logger.error(f"Fehler beim Laden von user_positions.json: {e}")
    return []


def save_user_positions(positions: List[Dict[str, Any]]) -> None:
    try:
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "positions": positions
        }
        with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Fehler beim Speichern von user_positions.json: {e}")


def update_db_user_positions(positions: List[Dict[str, Any]]) -> None:
    """Synchronisiert die bewerteten Nutzer-Positionen in market_analysis_db.json."""
    if not DB_FILE.exists():
        return
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
        db["user_positions"] = positions
        db["last_user_positions_guard_time"] = datetime.now(timezone.utc).isoformat()
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Konnte market_analysis_db.json nicht synchronisieren: {e}")


def evaluate_position_with_gemini_ai(pos: Dict[str, Any], tech_5m: Dict[str, Any], tech_15m: Dict[str, Any], fallback_rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fragt Google Gemini nach einer blitzschnellen, präzisen Einschätzung der Position.
    Nutzt ultra-schnelle Flash-Lite Modelle (0.8s) mit nahtlosem Math-Fallback.
    """
    sym = pos.get("symbol", "")
    direction = pos.get("direction", "LONG").upper()
    entry = float(pos.get("entry_price", 0.0))
    curr = float(pos.get("current_price", entry))
    lev = float(pos.get("leverage", 1.0))
    raw_pnl = float(pos.get("pnl_pct", 0.0))
    lev_pnl = float(pos.get("pnl_leveraged_pct", 0.0))
    sl = pos.get("stop_loss")
    tp = pos.get("take_profit")

    rsi_5m = tech_5m.get("rsi", 50.0) if tech_5m else 50.0
    rsi_15m = tech_15m.get("rsi", 50.0) if tech_15m else 50.0
    divs_5m = tech_5m.get("divergences", []) if tech_5m else []
    divs_15m = tech_15m.get("divergences", []) if tech_15m else []
    trend_5m = tech_5m.get("trend", "NEUTRAL") if tech_5m else "NEUTRAL"
    trend_15m = tech_15m.get("trend", "NEUTRAL") if tech_15m else "NEUTRAL"

    prompt = f"""Du bist der TradingView Super-Analyst Position Guard. Analysiere diesen aktiven Trade eines Traders auf Basis frischer 5m- und 15m-Kerzendaten:

Symbol: {sym}
Richtung: {direction}
Einstieg: {entry:,.2f} $ | Aktuell: {curr:,.2f} $ | Hebel: {lev:g}x
Aktueller PnL: {lev_pnl:+.2f}% (Basis: {raw_pnl:+.2f}%)
Stop-Loss: {sl if sl else 'Keiner gesetzt'} | Take-Profit: {tp if tp else 'Keiner gesetzt'}

Technische Daten:
- 5m-Chart: Trend {trend_5m}, RSI {rsi_5m:.1f}, Divergenzen: {', '.join(divs_5m) if divs_5m else 'Keine'}
- 15m-Chart: Trend {trend_15m}, RSI {rsi_15m:.1f}, Divergenzen: {', '.join(divs_15m) if divs_15m else 'Keine'}

Aufgabe:
Bewerte die Situation objektiv.
Gib die Antwort AUSSCHLIESSLICH als gültiges JSON-Objekt ohne Markdown-Codeblöcke zurück:
{{
  "status": "HEALTHY" | "WARNING" | "CRITICAL" | "TAKE_PROFIT" | "NEUTRAL",
  "badge_color": "emerald" | "amber" | "rose" | "indigo" | "slate",
  "action": "POSITION ENTSPANNT HALTEN" | "STOP NACHZIEHEN" | "TEILGEWINNE REALISIEREN" | "STOP-LOSS IN GEFAHR" | "BEOBACHTEN",
  "title": "Prägnanter Titel mit Emoji (max 45 Zeichen)",
  "message": "Konkrete Begründung und Handlungsempfehlung in 1-2 klaren Sätzen auf Deutsch.",
  "suggested_sl": null oder Zahl für empfohlenen Trailing-Stop
}}
"""
    try:
        from gemini_evaluator import get_api_key, extract_json_from_text
        import urllib.request
        api_key = get_api_key()
        if api_key:
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1}
            }
            # Ultra-schnelle Modelle priorisieren
            for mod in ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.5-flash"]:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent?key={api_key}"
                req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        res = json.loads(resp.read().decode("utf-8"))
                        txt = res["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = extract_json_from_text(txt)
                        if isinstance(parsed, dict) and "action" in parsed and "message" in parsed:
                            parsed["source"] = f"{mod} (AI)"
                            return parsed
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"Gemini Position Guard Anfrage übersprungen ({e}), nutze mathematische Fallback-Regel.")

    # Fallback auf bewährtes Regelwerk
    fallback_rec["source"] = "Quantitative Confluence Rules"
    return fallback_rec


def run_position_guard_cycle() -> int:
    """Führt einen kompletten 5-Minuten-Überwachungszyklus für alle Nutzerpositionen aus."""
    t0 = time.time()
    positions = load_user_positions()
    if not positions:
        logger.info("ℹ️ Keine aktiven Nutzer-Positionen vorhanden. Position Guard beendet.")
        return 0

    logger.info(f"🛡️ Starte High-Speed Position Guard für {len(positions)} aktive Positionen...")

    from fetch_real_ohlcv_cache import fetch_bars_direct
    from degencoder_engine import analyze_degencoder_full
    from portfolio_engine import generate_actionable_recommendation

    evaluated_positions = []
    now_iso = datetime.now(timezone.utc).isoformat()
    now_str = datetime.now(timezone.utc).strftime("%d.%m. %H:%M UTC")

    for pos in positions:
        sym = pos.get("symbol", "")
        direction = pos.get("direction", "LONG").upper()
        entry_p = float(pos.get("entry_price", 0.0))
        lev = float(pos.get("leverage", 1.0))
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

        # 1. Frische 5m- und 15m-Kerzen laden
        bars_5m = fetch_bars_direct(sym, interval="5m", count=80)
        bars_15m = fetch_bars_direct(sym, interval="15m", count=60)

        curr_p = entry_p
        if bars_5m and len(bars_5m) > 0:
            curr_p = float(bars_5m[-1]["c"])
        elif bars_15m and len(bars_15m) > 0:
            curr_p = float(bars_15m[-1]["c"])
        else:
            curr_p = float(pos.get("current_price", entry_p))

        # 2. PnL berechnen
        if direction == "LONG":
            raw_pnl = ((curr_p - entry_p) / entry_p) * 100.0 if entry_p > 0 else 0.0
        else:
            raw_pnl = ((entry_p - curr_p) / entry_p) * 100.0 if entry_p > 0 else 0.0

        lev_pnl = raw_pnl * lev

        # 3. Auto-Close Prüfung (Hard Stop-Loss oder Take-Profit)
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
                pos_to_close["pnl_pct"] = round(raw_pnl, 2)
                pos_to_close["pnl_leveraged_pct"] = round(lev_pnl, 2)

                closed_rec = archive_closed_position(
                    pos_to_close,
                    exit_price=exit_p,
                    exit_reason=exit_reason,
                    exit_reason_display=reason_disp
                )
                send_user_position_closed_notification(closed_rec)
                logger.info(f"⚡ [AUTO-CLOSE] {sym} ({direction}) automatisch geschlossen: {reason_disp} | Realisierter PnL: {closed_rec.get('realized_pnl_leveraged_pct'):+.2f}%")
            except Exception as ace:
                logger.error(f"Fehler bei Auto-Close für {sym}: {ace}")

            continue

        # 4. Abstände & CRV berechnen
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

        pos_eval = dict(pos)
        pos_eval["current_price"] = curr_p
        pos_eval["pnl_pct"] = round(raw_pnl, 2)
        pos_eval["pnl_leveraged_pct"] = round(lev_pnl, 2)
        pos_eval["stop_loss"] = sl_val
        pos_eval["take_profit"] = tp_val
        pos_eval["sl_distance_pct"] = sl_dist_pct
        pos_eval["tp_distance_pct"] = tp_dist_pct
        pos_eval["crv"] = crv
        pos_eval["last_price_update"] = now_iso
        pos_eval["last_price_update_str"] = now_str
        pos_eval["updated_at"] = now_iso

        # 5. Technische Analyse auf 5m und 15m
        tech_5m = analyze_degencoder_full(bars_5m, timeframe="5m") if bars_5m else {}
        tech_15m = analyze_degencoder_full(bars_15m, timeframe="15m") if bars_15m else {}

        # 6. Fallback-Regelwerk vorberechnen
        asset_mock = {
            "symbol": sym,
            "signal": "LONG" if direction == "LONG" else "SHORT",
            "timeframes": {"4h": tech_15m, "1D": tech_15m}
        }
        math_rec = generate_actionable_recommendation(pos_eval, asset_mock, curr_p, raw_pnl, lev_pnl)

        # 7. KI-Bewertung mit Gemini 3.8 Flash High
        ai_rec = evaluate_position_with_gemini_ai(pos_eval, tech_5m, tech_15m, math_rec)
        pos_eval["recommendation"] = ai_rec

        evaluated_positions.append(pos_eval)
        logger.info(f"  • {sym} ({direction} {lev:g}x): Kurs={curr_p:,.2f} $ | PnL={lev_pnl:+.2f}% ({raw_pnl:+.2f}% Basis) | Status=[{ai_rec.get('action')}]")

    # Speichern
    save_user_positions(evaluated_positions)
    update_db_user_positions(evaluated_positions)

    # 8. Push-Warnungen bei kritischen Statuswechseln auslösen
    try:
        from notifications import check_and_notify_user_positions
        check_and_notify_user_positions(evaluated_positions)
    except Exception as ne:
        logger.warning(f"Benachrichtigungs-Check übersprungen: {ne}")

    elapsed = time.time() - t0
    logger.info(f"✅ Position Guard erfolgreich abgeschlossen ({len(evaluated_positions)} Trades aktiv überwacht in {elapsed:.2f}s).")
    return len(evaluated_positions)


if __name__ == "__main__":
    run_position_guard_cycle()
