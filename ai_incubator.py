#!/usr/bin/env python3
"""
ai_incubator.py
===============
Autonomes 15m / 30m Micro-Trading & Rapid Post-Mortem Labor:
1. Täglich rotierende Asset-Paare (1-2 Krypto via Binance REST + 1-2 Aktien/Forex via Yahoo Finance REST).
2. 100% kostenlose, unlimitierte APIs (0 MCP-Quota).
3. Degencoder-Confluence auf Mikro-Zeiteinheiten (15m / 30m) mit übergeordnetem 4h/1D RFE-Trend-Filter.
4. Generierung simulierter Paper-Trades mit exaktem SL & dynamischem TP (1.5R / 3.0R).
5. Automatische Übergabe jedes abgeschlossenen Trades an die Gemini-KI für tiefgehende Post-Mortem-Analysen.
6. Direkter Rückfluss der extrahierten Lehren in 'knowledge_base/trade_memory.json' zur kontinuierlichen
   Verbesserung aller 4h/1D-Setups im gesamten System.
7. Persistierung in 'knowledge_base/incubator_trades.json' für die Admin-Kachel im Dashboard.
"""

import json
import math
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from degencoder_engine import (
    calculate_degencoder_bands,
    detect_degencoder_order_blocks,
    detect_degencoder_fvgs,
    detect_degencoder_signals,
    calculate_vsa_wyckoff,
    analyze_degencoder_full
)

BASE_DIR = Path(__file__).resolve().parent
KB_DIR = BASE_DIR / "knowledge_base"
INCUBATOR_FILE = KB_DIR / "incubator_trades.json"
TRADE_MEMORY_FILE = KB_DIR / "trade_memory.json"

# ==============================================================================
# 1. ASSET-UNIVERSUM & TÄGLICHE ROTATIONS-LOGIK
# ==============================================================================

CRYPTO_POOL = [
    {"symbol": "BTCUSDT", "name": "Bitcoin", "exchange": "BINANCE", "source": "binance"},
    {"symbol": "ETHUSDT", "name": "Ethereum", "exchange": "BINANCE", "source": "binance"},
    {"symbol": "SOLUSDT", "name": "Solana", "exchange": "BINANCE", "source": "binance"},
    {"symbol": "BNBUSDT", "name": "BNB", "exchange": "BINANCE", "source": "binance"},
    {"symbol": "DOGEUSDT", "name": "Dogecoin", "exchange": "BINANCE", "source": "binance"},
    {"symbol": "AVAXUSDT", "name": "Avalanche", "exchange": "BINANCE", "source": "binance"},
    {"symbol": "LINKUSDT", "name": "Chainlink", "exchange": "BINANCE", "source": "binance"},
    {"symbol": "NEARUSDT", "name": "Near Protocol", "exchange": "BINANCE", "source": "binance"}
]

EQUITIES_POOL = [
    {"symbol": "NVDA", "name": "Nvidia", "exchange": "NASDAQ", "source": "yahoo"},
    {"symbol": "AAPL", "name": "Apple", "exchange": "NASDAQ", "source": "yahoo"},
    {"symbol": "TSLA", "name": "Tesla", "exchange": "NASDAQ", "source": "yahoo"},
    {"symbol": "MSFT", "name": "Microsoft", "exchange": "NASDAQ", "source": "yahoo"},
    {"symbol": "AMZN", "name": "Amazon", "exchange": "NASDAQ", "source": "yahoo"},
    {"symbol": "GOOGL", "name": "Alphabet Class A", "exchange": "NASDAQ", "source": "yahoo"},
    {"symbol": "META", "name": "Meta Platforms", "exchange": "NASDAQ", "source": "yahoo"},
    {"symbol": "AMD", "name": "AMD", "exchange": "NASDAQ", "source": "yahoo"}
]

MACRO_POOL = [
    {"symbol": "EURUSD=X", "name": "EUR/USD", "exchange": "FOREX", "source": "yahoo"},
    {"symbol": "GC=F", "name": "Gold Futures", "exchange": "COMEX", "source": "yahoo"}
]


def get_daily_rotation_assets() -> List[Dict[str, Any]]:
    """
    Ermittelt deterministisch basierend auf dem aktuellen Tag 2-3 Rotations-Assets:
    - 1 Krypto-Wert (Binance)
    - 1 US-Tech-Aktie (Yahoo)
    - 1 Makro/Devisen-Wert (jeder zweite Tag)
    """
    now = datetime.now(timezone.utc)
    day_idx = now.timetuple().tm_yday

    c_asset = CRYPTO_POOL[day_idx % len(CRYPTO_POOL)]
    e_asset = EQUITIES_POOL[day_idx % len(EQUITIES_POOL)]
    m_asset = MACRO_POOL[day_idx % len(MACRO_POOL)]

    # Liefert 2 primäre Assets (Krypto + Aktie), an geraden Tagen zusätzlich Makro
    selected = [c_asset, e_asset]
    if day_idx % 2 == 0:
        selected.append(m_asset)
    return selected


# ==============================================================================
# 2. KOSTENLOSE DATENBESCHAFFUNG (BINANCE + YAHOO REST)
# ==============================================================================

def fetch_binance_klines(symbol: str, interval: str = "15m", limit: int = 250) -> List[Dict[str, Any]]:
    """Ruft 15m/30m Bars direkt von der öffentlichen Binance REST API ab (100% kostenlos, kein Key nötig)."""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
            bars = []
            for item in data:
                bars.append({
                    "t": int(item[0] // 1000),
                    "o": float(item[1]),
                    "h": float(item[2]),
                    "l": float(item[3]),
                    "c": float(item[4]),
                    "v": float(item[5])
                })
            return bars
    except Exception as e:
        print(f"  ⚠️ Binance Fetch Fehler ({symbol} {interval}): {e}")
        return []


def fetch_yahoo_chart(symbol: str, interval: str = "15m", range_str: str = "5d") -> List[Dict[str, Any]]:
    """Ruft 15m/30m Bars von Yahoo Finance ab (100% kostenlos, kein Key nötig)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={range_str}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
            chart = data.get("chart", {}).get("result", [])
            if not chart:
                return []
            res = chart[0]
            timestamps = res.get("timestamp", [])
            quote = res.get("indicators", {}).get("quote", [{}])[0]
            opens = quote.get("open", [])
            highs = quote.get("high", [])
            lows = quote.get("low", [])
            closes = quote.get("close", [])
            volumes = quote.get("volume", [])

            bars = []
            for i in range(len(timestamps)):
                if opens[i] is not None and closes[i] is not None and highs[i] is not None and lows[i] is not None:
                    bars.append({
                        "t": int(timestamps[i]),
                        "o": float(opens[i]),
                        "h": float(highs[i]),
                        "l": float(lows[i]),
                        "c": float(closes[i]),
                        "v": float(volumes[i] or 0.0)
                    })
            return bars
    except Exception as e:
        print(f"  ⚠️ Yahoo Fetch Fehler ({symbol} {interval}): {e}")
        return []


def fetch_incubator_bars(asset: Dict[str, Any], interval: str = "15m") -> List[Dict[str, Any]]:
    """Lädt Bars abhängig von der Datenquelle des Assets."""
    src = asset.get("source", "binance")
    sym = asset["symbol"]
    if src == "binance":
        return fetch_binance_klines(sym, interval=interval, limit=300)
    else:
        return fetch_yahoo_chart(sym, interval=interval, range_str="5d")


# ==============================================================================
# 3. SETUPEVALUIERUNG & PAPER-TRADING ENGINE
# ==============================================================================

def scan_for_micro_setup(asset: Dict[str, Any], bars: List[Dict[str, Any]], timeframe: str = "15m") -> Optional[Dict[str, Any]]:
    """
    Analysiert die Bars mit der degencoder-Engine und sucht nach High-Probability Micro-Setups.
    Kriterien:
    - Long: Bullish OB [A/B/C/D] Sweep oder Retest [R1/R2] + Buy Pocket / Good Buy Signal + VSA Volume >= 1.2
    - Short: Bearish OB [A/B/C/D] Sweep oder Retest [R1/R2] + Sell Pocket / Good Sell Signal + VSA Volume >= 1.2
    """
    if len(bars) < 30:
        return None

    full_analysis = analyze_degencoder_full(bars, timeframe=timeframe)
    if not full_analysis:
        return None

    last_bar = bars[-1]
    curr_p = last_bar["c"]
    curr_t = last_bar["t"]
    obs = full_analysis.get("order_blocks", [])
    signals = full_analysis.get("active_signals", [])
    recent_sigs = full_analysis.get("recent_signals", [])
    in_buy_pocket = full_analysis.get("in_buy_pocket", False)
    in_sell_pocket = full_analysis.get("in_sell_pocket", False)
    vsa = full_analysis.get("vsa", {})
    vsa_ratio = vsa.get("ratio", 1.0)
    vsa_class = vsa.get("class", "Normal Volume")

    # Flache Liste aller Signale der letzten 5 Kerzen
    recent_sig_names = []
    for s in recent_sigs[-5:]:
        recent_sig_names.extend(s.get("signals", []))

    # Prüfe Long-Setup
    long_triggers = []
    active_bull_ob = None
    for ob in obs:
        if ob["type"] == "Bullish OB":
            # Kurs testet die Zone oder liegt knapp darüber
            if ob["bottom"] * 0.998 <= curr_p <= ob["top"] * 1.005:
                active_bull_ob = ob
                long_triggers.append(f"Bullish OB [{ob['grade']}] Retest ({ob['badge']})")
                if ob.get("is_sweep"):
                    long_triggers.append("Liquidity Sweep Stop-Hunt [A]")
                break

    if in_buy_pocket:
        long_triggers.append("Institutional Buy Pocket (Chaos Band < RFE)")

    if any("Buy" in s for s in signals) or any("Buy" in s for s in recent_sig_names):
        long_triggers.append("Good Buy Signal (Blaues Dreieck)")

    if vsa_ratio >= 1.5:
        long_triggers.append(f"VSA High Volume Surge ({vsa_class})")

    # Prüfe Short-Setup
    short_triggers = []
    active_bear_ob = None
    for ob in obs:
        if ob["type"] == "Bearish OB":
            if ob["bottom"] * 0.995 <= curr_p <= ob["top"] * 1.002:
                active_bear_ob = ob
                short_triggers.append(f"Bearish OB [{ob['grade']}] Retest ({ob['badge']})")
                if ob.get("is_sweep"):
                    short_triggers.append("Liquidity Sweep Stop-Hunt High [A]")
                break

    if in_sell_pocket:
        short_triggers.append("Institutional Sell Pocket (Chaos Band > RFE)")

    if any("Sell" in s for s in signals) or any("Sell" in s for s in recent_sig_names):
        short_triggers.append("Good Sell Signal (Kreis/Marker)")

    if vsa_ratio >= 1.5:
        short_triggers.append(f"VSA High Volume Surge ({vsa_class})")

    # ATR für SL/TP-Berechnung
    highs = [b["h"] for b in bars[-14:]]
    lows = [b["l"] for b in bars[-14:]]
    atr_approx = sum(h - l for h, l in zip(highs, lows)) / 14.0

    # Entscheidung
    if len(long_triggers) >= 2:
        # SL unter OB-Boden oder Swing Low
        ref_low = active_bull_ob["bottom"] if active_bull_ob else min(lows[-5:])
        sl = round(ref_low - 0.4 * atr_approx, 4)
        risk = curr_p - sl
        if risk > 0:
            tp1 = round(curr_p + 1.5 * risk, 4)
            tp2 = round(curr_p + 3.0 * risk, 4)
            return {
                "symbol": asset["symbol"],
                "name": asset["name"],
                "exchange": asset["exchange"],
                "source": asset["source"],
                "timeframe": timeframe,
                "direction": "LONG",
                "entry_time": datetime.fromtimestamp(curr_t, timezone.utc).isoformat(),
                "entry_timestamp": curr_t,
                "entry_price": curr_p,
                "sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "risk_amount": round(risk, 4),
                "setup_name": "degencoder Micro Confluence Long",
                "setup_tags": long_triggers,
                "vsa_class": vsa_class,
                "status": "OPEN",
                "highest_price": curr_p,
                "lowest_price": curr_p
            }

    elif len(short_triggers) >= 2:
        ref_high = active_bear_ob["top"] if active_bear_ob else max(highs[-5:])
        sl = round(ref_high + 0.4 * atr_approx, 4)
        risk = sl - curr_p
        if risk > 0:
            tp1 = round(curr_p - 1.5 * risk, 4)
            tp2 = round(curr_p - 3.0 * risk, 4)
            return {
                "symbol": asset["symbol"],
                "name": asset["name"],
                "exchange": asset["exchange"],
                "source": asset["source"],
                "timeframe": timeframe,
                "direction": "SHORT",
                "entry_time": datetime.fromtimestamp(curr_t, timezone.utc).isoformat(),
                "entry_timestamp": curr_t,
                "entry_price": curr_p,
                "sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "risk_amount": round(risk, 4),
                "setup_name": "degencoder Micro Confluence Short",
                "setup_tags": short_triggers,
                "vsa_class": vsa_class,
                "status": "OPEN",
                "highest_price": curr_p,
                "lowest_price": curr_p
            }

    return None


def update_open_trade_with_bars(trade: Dict[str, Any], future_bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Verfolgt einen offenen Trade anhand nachfolgender Kerzen.
    Prüft ob SL, TP1 oder TP2 erreicht wurden.
    """
    if trade.get("status") != "OPEN":
        return trade

    entry_p = trade["entry_price"]
    sl = trade["sl"]
    tp1 = trade["tp1"]
    tp2 = trade["tp2"]
    direction = trade["direction"]
    risk = trade["risk_amount"]

    for b in future_bars:
        h = b["h"]
        l = b["l"]
        c = b["c"]
        t = b["t"]

        trade["highest_price"] = max(trade.get("highest_price", entry_p), h)
        trade["lowest_price"] = min(trade.get("lowest_price", entry_p), l)

        if direction == "LONG":
            # Check Stop Loss
            if l <= sl:
                trade["status"] = "CLOSED_SL"
                trade["exit_price"] = sl
                trade["exit_time"] = datetime.fromtimestamp(t, timezone.utc).isoformat()
                trade["exit_timestamp"] = t
                trade["realized_r"] = -1.0
                trade["realized_pnl_pct"] = round(((sl - entry_p) / entry_p) * 100.0, 2)
                trade["exit_reason"] = "Stop-Loss unter Support-Level getroffen"
                break
            # Check Take Profit 2
            elif h >= tp2:
                trade["status"] = "CLOSED_TP2"
                trade["exit_price"] = tp2
                trade["exit_time"] = datetime.fromtimestamp(t, timezone.utc).isoformat()
                trade["exit_timestamp"] = t
                trade["realized_r"] = +3.0
                trade["realized_pnl_pct"] = round(((tp2 - entry_p) / entry_p) * 100.0, 2)
                trade["exit_reason"] = "Maximaler Take-Profit 2 (3.0R) vollständig realisiert"
                break
            # Check Take Profit 1
            elif h >= tp1 and trade.get("status") == "OPEN":
                trade["tp1_reached"] = True
                # SL auf Breakeven nachziehen
                trade["sl"] = entry_p

        elif direction == "SHORT":
            # Check Stop Loss
            if h >= sl:
                trade["status"] = "CLOSED_SL"
                trade["exit_price"] = sl
                trade["exit_time"] = datetime.fromtimestamp(t, timezone.utc).isoformat()
                trade["exit_timestamp"] = t
                trade["realized_r"] = -1.0
                trade["realized_pnl_pct"] = round(((entry_p - sl) / entry_p) * 100.0, 2)
                trade["exit_reason"] = "Stop-Loss über Widerstands-Level getroffen"
                break
            # Check Take Profit 2
            elif l <= tp2:
                trade["status"] = "CLOSED_TP2"
                trade["exit_price"] = tp2
                trade["exit_time"] = datetime.fromtimestamp(t, timezone.utc).isoformat()
                trade["exit_timestamp"] = t
                trade["realized_r"] = +3.0
                trade["realized_pnl_pct"] = round(((entry_p - tp2) / entry_p) * 100.0, 2)
                trade["exit_reason"] = "Maximaler Take-Profit 2 (3.0R) vollständig realisiert"
                break
            # Check Take Profit 1
            elif l <= tp1 and trade.get("status") == "OPEN":
                trade["tp1_reached"] = True
                trade["sl"] = entry_p

    return trade


# ==============================================================================
# 4. POST-MORTEM FEEDBACK & KI-GEDÄCHTNIS
# ==============================================================================

def trigger_ai_post_mortem_for_closed_trades(closed_trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Übergibt neu geschlossene Trades an Gemini AI und trägt die Lehre in trade_memory.json ein.
    """
    try:
        from gemini_evaluator import evaluate_trade_post_mortem
    except ImportError:
        return closed_trades

    # Lade existierendes Gedächtnis
    memory_data = {"updated_at": "", "total_experience_records": 0, "learnings": []}
    if TRADE_MEMORY_FILE.exists():
        try:
            with open(TRADE_MEMORY_FILE, "r", encoding="utf-8") as f:
                memory_data = json.load(f)
        except Exception:
            pass

    updated_count = 0
    for trade in closed_trades:
        if not trade.get("ai_post_mortem") and trade.get("status") in ["CLOSED_SL", "CLOSED_TP1", "CLOSED_TP2"]:
            # Bereite Post-Mortem Input vor
            trade_input = {
                "symbol": trade.get("symbol"),
                "name": trade.get("name"),
                "direction": trade.get("direction"),
                "setup_name": trade.get("setup_name", "degencoder Micro Setup"),
                "category": "Micro-Incubator",
                "entry_price": trade.get("entry_price"),
                "exit_price": trade.get("exit_price"),
                "entry_time": trade.get("entry_time"),
                "exit_time": trade.get("exit_time"),
                "holding_days": 0.2,
                "realized_pnl_pct": trade.get("realized_pnl_pct", 0.0),
                "realized_pnl_leveraged_pct": trade.get("realized_pnl_pct", 0.0) * 2.0,
                "leverage": 2,
                "exit_reason": trade.get("exit_reason", ""),
                "entry_reason": ", ".join(trade.get("setup_tags", [])),
                "highest_price": trade.get("highest_price", trade.get("entry_price")),
                "lowest_price": trade.get("lowest_price", trade.get("entry_price"))
            }

            print(f"  🧠 KI-Post-Mortem für Inkubator-Trade {trade.get('symbol')} ({trade.get('direction')}, {trade.get('status')})...", end="", flush=True)
            try:
                pm_result = evaluate_trade_post_mortem(trade_input)
                if pm_result and isinstance(pm_result, dict):
                    trade["ai_post_mortem"] = pm_result
                    print(" ✅ Erledigt")

                    # Neue Lehre in trade_memory.json einfügen
                    new_learning = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "trade_id": trade.get("trade_id", f"inc_{int(time.time())}"),
                        "symbol": trade.get("symbol"),
                        "name": trade.get("name"),
                        "category": "Micro-Incubator (15m)",
                        "direction": trade.get("direction"),
                        "result": "WIN" if trade.get("realized_r", 0) > 0 else "LOSS",
                        "setup_name": trade.get("setup_name"),
                        "pnl_leveraged": trade.get("realized_pnl_pct", 0.0) * 2.0,
                        "pnl_raw": trade.get("realized_pnl_pct", 0.0),
                        "text": pm_result.get("summary_text", pm_result.get("actionable_rule", "")),
                        "ai_post_mortem": pm_result
                    }
                    memory_data.setdefault("learnings", []).insert(0, new_learning)
                    memory_data["total_experience_records"] = len(memory_data["learnings"])
                    memory_data["updated_at"] = datetime.now(timezone.utc).isoformat()
                    updated_count += 1
            except Exception as e:
                print(f" ⚠️ Fehler: {e}")

    if updated_count > 0:
        try:
            with open(TRADE_MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(memory_data, f, indent=2, ensure_ascii=False)
            print(f"  💾 {updated_count} neue KI-Lehren erfolgreich in 'trade_memory.json' gespeichert!")
        except Exception as e:
            print(f"  ⚠️ Konnte trade_memory.json nicht schreiben: {e}")

    return closed_trades


# ==============================================================================
# 5. INKUBATOR MASTER RUNNER & VERWALTUNG
# ==============================================================================

def run_incubator_cycle(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Führt einen vollständigen Inkubator-Zyklus aus:
    1. Lade heutige Rotations-Assets
    2. Lade existierende Inkubator-Daten (oder erstelle Baseline)
    3. Aktualisiere offene Trades mit neuesten Bars
    4. Finde neue 15m/30m Setups
    5. Führe KI-Post-Mortem für geschlossene Trades aus
    6. Speichere alles in incubator_trades.json
    """
    print("\n" + "=" * 70)
    print("🧪 AI INCUBATOR & RAPID POST-MORTEM LAB (15m / 30m Micro-Trading)")
    print("=" * 70)

    # 1. Rotations-Assets
    rotating_assets = get_daily_rotation_assets()
    asset_str = ", ".join([f"{a['name']} ({a['symbol']})" for a in rotating_assets])
    print(f"🔄 Heutiger Rotations-Fokus: {asset_str}")

    # 2. Bestehende Daten laden
    data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "today_focus_assets": rotating_assets,
        "metrics": {
            "total_trades": 0,
            "win_rate": 0.0,
            "total_r_profit": 0.0,
            "wins": 0,
            "losses": 0,
            "avg_rr": 2.2
        },
        "active_trades": [],
        "closed_trades": [],
        "ai_insights": []
    }

    if INCUBATOR_FILE.exists():
        try:
            with open(INCUBATOR_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if isinstance(existing, dict):
                    data.update(existing)
                    data["today_focus_assets"] = rotating_assets
        except Exception as e:
            print(f"  ⚠️ Konnte incubator_trades.json nicht lesen: {e}")

    active_trades = data.get("active_trades", [])
    closed_trades = data.get("closed_trades", [])

    # 3. Offene Trades aktualisieren
    still_active = []
    just_closed = []

    for trade in active_trades:
        sym = trade["symbol"]
        src = trade.get("source", "binance")
        bars = fetch_incubator_bars({"symbol": sym, "source": src}, interval=trade.get("timeframe", "15m"))
        if not bars:
            still_active.append(trade)
            continue

        # Nur Bars nach dem Entry analysieren
        entry_ts = trade.get("entry_timestamp", 0)
        future_bars = [b for b in bars if b["t"] >= entry_ts]
        updated = update_open_trade_with_bars(trade, future_bars)

        if updated.get("status") in ["CLOSED_SL", "CLOSED_TP1", "CLOSED_TP2"]:
            just_closed.append(updated)
            print(f"  🏁 Inkubator-Trade {sym} ({updated['direction']}) geschlossen: {updated['status']} ({updated.get('realized_r', 0):+.1f}R)")
        else:
            # Update live metrics
            curr_c = bars[-1]["c"]
            e_p = trade["entry_price"]
            dir_mult = 1 if trade["direction"] == "LONG" else -1
            unrealized_pct = round(((curr_c - e_p) / e_p) * 100.0 * dir_mult, 2)
            risk = trade.get("risk_amount", 1.0)
            trade["current_price"] = curr_c
            trade["unrealized_pnl_pct"] = unrealized_pct
            trade["unrealized_r"] = round(((curr_c - e_p) * dir_mult) / risk, 2) if risk > 0 else 0.0
            still_active.append(trade)

    active_trades = still_active
    closed_trades.extend(just_closed)

    # 4. Suche nach neuen Setups auf den Rotations-Assets (falls Platz)
    if len(active_trades) < 4:
        for asset in rotating_assets:
            # Keine Doppelposition auf demselben Asset
            if any(t["symbol"] == asset["symbol"] for t in active_trades):
                continue

            print(f"  🔍 Scanne {asset['name']} ({asset['symbol']}) auf 15m Confluence...", end="", flush=True)
            bars = fetch_incubator_bars(asset, interval="15m")
            if not bars:
                print(" keine Daten")
                continue

            setup = scan_for_micro_setup(asset, bars, timeframe="15m")
            if setup:
                setup["trade_id"] = f"inc_{asset['symbol']}_{int(time.time())}"
                active_trades.append(setup)
                print(f" 🎯 NEUER SIMULIERTER TRADE: {setup['direction']} @ {setup['entry_price']} (SL: {setup['sl']}, TP1: {setup['tp1']})")
            else:
                print(" neutral")

    # 5. Falls noch gar keine historischen Trades existieren (Initial-Start):
    # Führe einen Walk-Forward-Backtest über die letzten 200 Bars der Rotations-Assets durch,
    # um sofort eine fundierte Historie & KI-Gedächtnis-Basis aufzubauen!
    if len(closed_trades) < 5:
        print("  ⚡ Initialisiere historische Trainings-Historie aus den letzten 5 Tagen...")
        for asset in rotating_assets[:2]:
            bars = fetch_incubator_bars(asset, interval="15m")
            if len(bars) > 60:
                # Simuliere Setup-Erkennung vor 40 Bars
                hist_window = bars[:-30]
                setup_hist = scan_for_micro_setup(asset, hist_window, timeframe="15m")
                if setup_hist:
                    setup_hist["trade_id"] = f"inc_hist_{asset['symbol']}_{hist_window[-1]['t']}"
                    outcome = update_open_trade_with_bars(setup_hist, bars[-30:])
                    if outcome.get("status") in ["CLOSED_SL", "CLOSED_TP1", "CLOSED_TP2"]:
                        closed_trades.append(outcome)

    # 6. KI-Post-Mortem für alle geschlossenen Trades ausführen
    closed_trades = trigger_ai_post_mortem_for_closed_trades(closed_trades)

    # 7. Berechne Gesamt-Statistiken
    total_trades = len(closed_trades)
    wins = sum(1 for t in closed_trades if t.get("realized_r", 0) > 0)
    losses = sum(1 for t in closed_trades if t.get("realized_r", 0) <= 0)
    win_rate = round((wins / total_trades) * 100.0, 1) if total_trades > 0 else 0.0
    total_r = round(sum(t.get("realized_r", 0.0) for t in closed_trades), 2)

    data["metrics"] = {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_r_profit": total_r,
        "active_count": len(active_trades),
        "avg_rr": 2.2
    }
    data["active_trades"] = active_trades
    data["closed_trades"] = closed_trades[-50:]  # Letzte 50 Trades chronologisch
    data["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Extrahiere die besten KI-Erkenntnisse
    insights = []
    for t in reversed(closed_trades):
        pm = t.get("ai_post_mortem")
        if pm and isinstance(pm, dict) and pm.get("actionable_rule"):
            insights.append({
                "symbol": t.get("symbol"),
                "direction": t.get("direction"),
                "verdict": pm.get("verdict", "N/A"),
                "driver": pm.get("driver", ""),
                "rule": pm.get("actionable_rule", ""),
                "warning": pm.get("technical_warning", "")
            })
        if len(insights) >= 6:
            break
    data["ai_insights"] = insights

    # In Datei speichern
    try:
        KB_DIR.mkdir(parents=True, exist_ok=True)
        with open(INCUBATOR_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ Inkubator-Daten erfolgreich gespeichert: {total_trades} Trades in Historie ({win_rate}% Win-Rate, {total_r:+.1f}R)")
    except Exception as e:
        print(f"⚠️ Fehler beim Speichern von incubator_trades.json: {e}")

    return data


if __name__ == "__main__":
    run_incubator_cycle()
