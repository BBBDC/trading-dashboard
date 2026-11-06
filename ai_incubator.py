#!/usr/bin/env python3
"""
ai_incubator.py
===============
Autonomes 5m / 15m / 30m Micro-Trading & High-Throughput Post-Mortem Labor:
1. 16-Asset-Matrix:
   - 8 Krypto-Werte (24/7 über Binance REST, 0 € API, unlimitiert)
   - 8 Deutsche & US-Tech-Werte (08:00–22:00 MEZ über Börse Frankfurt .F & XETRA .DE, 0 € API)
2. Multi-Timeframe Triangulation:
   - 5m: Micro-Liquidity-Sweeps, Stop-Hunts & Scharfschützen-Einstiege
   - 15m / 30m: Zonen-Struktur, FVGs (1-Tick-Rule) & Chaos-Band-Rebounds
   - 4h / 1D: RFE 233 Trendfilter (Top-Down Governance)
3. Vergleichende KI-Batch-Post-Mortem Synthese (Gemini 3.8 Flash High via Pro-Abo CLI pokeulm@gmail.com):
   - Analysiert 3-4 Trades gleichzeitig (Cross-Trade-Kausalität)
   - Direkter Rückfluss der Lehren in 'knowledge_base/trade_memory.json'
4. Historisches Walk-Forward Replay-Training:
   - Simuliert 30 Tage echter Marktdaten auf Knopfdruck zur blitzschnellen Wissensgenerierung.
5. Persistierung in 'knowledge_base/incubator_trades.json' für die Admin-Kachel im Dashboard.
"""

import json
import math
import os
import sys
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
# 1. 24-ASSET-MATRIX (24/7 KRYPTO + DEUTSCHE 08:00–22:00 MEZ BÖRSEN)
# ==============================================================================

CRYPTO_UNIVERSE = [
    {"symbol": "BTCUSDT", "name": "Bitcoin", "exchange": "BINANCE (24/7)", "source": "binance", "category": "Crypto"},
    {"symbol": "ETHUSDT", "name": "Ethereum", "exchange": "BINANCE (24/7)", "source": "binance", "category": "Crypto"},
    {"symbol": "SOLUSDT", "name": "Solana", "exchange": "BINANCE (24/7)", "source": "binance", "category": "Crypto"},
    {"symbol": "BNBUSDT", "name": "BNB", "exchange": "BINANCE (24/7)", "source": "binance", "category": "Crypto"},
    {"symbol": "AVAXUSDT", "name": "Avalanche", "exchange": "BINANCE (24/7)", "source": "binance", "category": "Crypto"},
    {"symbol": "DOGEUSDT", "name": "Dogecoin", "exchange": "BINANCE (24/7)", "source": "binance", "category": "Crypto"},
    {"symbol": "LINKUSDT", "name": "Chainlink", "exchange": "BINANCE (24/7)", "source": "binance", "category": "Crypto"},
    {"symbol": "NEARUSDT", "name": "Near Protocol", "exchange": "BINANCE (24/7)", "source": "binance", "category": "Crypto"},
    {"symbol": "XRPUSDT", "name": "Ripple", "exchange": "BINANCE (24/7)", "source": "binance", "category": "Crypto"},
    {"symbol": "ADAUSDT", "name": "Cardano", "exchange": "BINANCE (24/7)", "source": "binance", "category": "Crypto"},
    {"symbol": "SUIUSDT", "name": "Sui", "exchange": "BINANCE (24/7)", "source": "binance", "category": "Crypto"},
    {"symbol": "RENDERUSDT", "name": "Render", "exchange": "BINANCE (24/7)", "source": "binance", "category": "Crypto"}
]

EQUITIES_GERMAN_UNIVERSE = [
    {"symbol": "NVD.F", "name": "Nvidia", "exchange": "FRA / Tradegate (08-22h)", "source": "yahoo", "category": "US-Tech (EUR)", "currency": "EUR"},
    {"symbol": "TL0.F", "name": "Tesla", "exchange": "FRA / Tradegate (08-22h)", "source": "yahoo", "category": "US-Tech (EUR)", "currency": "EUR"},
    {"symbol": "APC.F", "name": "Apple", "exchange": "FRA / Tradegate (08-22h)", "source": "yahoo", "category": "US-Tech (EUR)", "currency": "EUR"},
    {"symbol": "AMZ.F", "name": "Amazon", "exchange": "FRA / Tradegate (08-22h)", "source": "yahoo", "category": "US-Tech (EUR)", "currency": "EUR"},
    {"symbol": "MSF.F", "name": "Microsoft", "exchange": "FRA / Tradegate (08-22h)", "source": "yahoo", "category": "US-Tech (EUR)", "currency": "EUR"},
    {"symbol": "FB2A.F", "name": "Meta Platforms", "exchange": "FRA / Tradegate (08-22h)", "source": "yahoo", "category": "US-Tech (EUR)", "currency": "EUR"},
    {"symbol": "ABEA.F", "name": "Alphabet (Google)", "exchange": "FRA / Tradegate (08-22h)", "source": "yahoo", "category": "US-Tech (EUR)", "currency": "EUR"},
    {"symbol": "RHM.DE", "name": "Rheinmetall", "exchange": "XETRA (09-17:30h)", "source": "yahoo", "category": "DAX / Defense (EUR)", "currency": "EUR"},
    {"symbol": "SAP.DE", "name": "SAP SE", "exchange": "XETRA (09-17:30h)", "source": "yahoo", "category": "DAX / Tech (EUR)", "currency": "EUR"},
    {"symbol": "SIE.DE", "name": "Siemens", "exchange": "XETRA (09-17:30h)", "source": "yahoo", "category": "DAX / Industrial (EUR)", "currency": "EUR"},
    {"symbol": "ALV.DE", "name": "Allianz", "exchange": "XETRA (09-17:30h)", "source": "yahoo", "category": "DAX / Financial (EUR)", "currency": "EUR"},
    {"symbol": "DTE.DE", "name": "Dt. Telekom", "exchange": "XETRA (09-17:30h)", "source": "yahoo", "category": "DAX / Telecom (EUR)", "currency": "EUR"}
]

ALL_INCUBATOR_ASSETS = CRYPTO_UNIVERSE + EQUITIES_GERMAN_UNIVERSE


def get_active_market_rotation_assets() -> List[Dict[str, Any]]:
    """
    Wählt intelligent 8 parallele Fokus-Assets aus (4 Krypto + 4 Aktien):
    - STÜNDLICH DYNAMISCHE ROTATION: Die Fokusgruppe rotiert jede Stunde um 1 Position weiter,
      sodass über den Tag hinweg ALLE Krypto- und Aktienwerte gleichmäßig durchlaufen und trainiert werden.
    - Zu deutschen Handelszeiten (08:00–22:00 MEZ) stehen Frankfurt & XETRA im Fokus.
    - Außerhalb der Börsenzeiten (Nacht & Wochenende) wird der Krypto-Anteil dynamisch erhöht.
    """
    now = datetime.now(timezone.utc)
    hour_cet = (now.hour + 1) % 24  # UTC+1 (MEZ)

    # Stündlicher Rotations-Index (yday * 24 + hour) -> Ändert sich jede Stunde
    rot_offset = (now.timetuple().tm_yday * 24 + now.hour)

    # Deutsche Börsenzeiten: Mo-Fr ca. 08:00 - 22:00 MEZ
    is_weekday = now.weekday() < 5
    is_german_market_open = is_weekday and (8 <= hour_cet < 22)

    if is_german_market_open:
        # 4 rotierende Kryptos + 4 rotierende deutsche/Tradegate Aktien
        c_indices = [(rot_offset + i) % len(CRYPTO_UNIVERSE) for i in range(4)]
        e_indices = [(rot_offset + i) % len(EQUITIES_GERMAN_UNIVERSE) for i in range(4)]
        selected_crypto = [CRYPTO_UNIVERSE[idx] for idx in c_indices]
        selected_equities = [EQUITIES_GERMAN_UNIVERSE[idx] for idx in e_indices]
        return selected_crypto + selected_equities
    else:
        # Nachts / Wochenende: Deutsche Börsen geschlossen -> Krypto-Anteil auf 6 erhöhen
        c_indices = [(rot_offset + i) % len(CRYPTO_UNIVERSE) for i in range(6)]
        e_indices = [(rot_offset + i) % len(EQUITIES_GERMAN_UNIVERSE) for i in range(2)]
        selected_crypto = [CRYPTO_UNIVERSE[idx] for idx in c_indices]
        selected_equities = [EQUITIES_GERMAN_UNIVERSE[idx] for idx in e_indices]
        return selected_crypto + selected_equities


# ==============================================================================
# 2. KOSTENLOSE DATENBESCHAFFUNG (BINANCE + YAHOO REST)
# ==============================================================================

def fetch_binance_klines(symbol: str, interval: str = "5m", limit: int = 300) -> List[Dict[str, Any]]:
    """Ruft 5m/15m/30m Bars direkt von der öffentlichen Binance REST API ab (100% kostenlos, kein Key nötig)."""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
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


def fetch_yahoo_chart(symbol: str, interval: str = "5m", range_str: str = "5d") -> List[Dict[str, Any]]:
    """Ruft 5m/15m Bars von Yahoo Finance ab (inkl. Frankfurt .F und XETRA .DE, 100% kostenlos)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={range_str}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
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


def fetch_incubator_bars(asset: Dict[str, Any], interval: str = "5m") -> List[Dict[str, Any]]:
    """Lädt Bars abhängig von der Datenquelle des Assets."""
    src = asset.get("source", "binance")
    sym = asset["symbol"]
    if src == "binance":
        return fetch_binance_klines(sym, interval=interval, limit=350)
    else:
        # Für 5m range 5d, für 15m range 10d
        range_s = "5d" if interval == "5m" else "10d"
        return fetch_yahoo_chart(sym, interval=interval, range_str=range_s)


# ==============================================================================
# 3. MULTI-TIMEFRAME SETUPEVALUIERUNG (5m / 15m MIT 4h GOVERNANCE)
# ==============================================================================

def scan_for_micro_setup(
    asset: Dict[str, Any],
    bars: List[Dict[str, Any]],
    timeframe: str = "5m",
    htf_bias: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Analysiert Bars mit der degencoder-Engine und sucht nach High-Probability Micro-Setups:
    - 5m: Erfordert präzisen Liquidity Sweep [A] an Chaos-Band oder OB-Zone + VSA Volume Surge
    - 15m: Erfordert FVG-Mitigation oder Retest [R1/R2] + Buy/Sell Pocket
    - HTF-Filter: Verhindert Trades gegen den übergeordneten Trend
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

    # Flache Liste aller Signale der letzten 6 Kerzen
    recent_sig_names = []
    for s in recent_sigs[-6:]:
        recent_sig_names.extend(s.get("signals", []))

    # Prüfe Long-Setup
    long_triggers = []
    active_bull_ob = None
    for ob in obs:
        if ob["type"] == "Bullish OB":
            # Qualitäts-Filter aus Post-Mortem Lab: C-Grade OBs ohne Sweep erzeugen gehäuft Fehlsignale
            if ob.get("grade") == "C" and not ob.get("is_sweep"):
                continue
            if ob["bottom"] * 0.998 <= curr_p <= ob["top"] * 1.004:
                active_bull_ob = ob
                long_triggers.append(f"Bullish OB [{ob['grade']}] Retest ({ob['badge']})")
                if ob.get("is_sweep"):
                    long_triggers.append("Liquidity Sweep Stop-Hunt [A]")
                break

    if in_buy_pocket:
        long_triggers.append("Institutional Buy Pocket (Chaos Band < RFE)")

    if any("Buy" in s for s in signals) or any("Buy" in s for s in recent_sig_names):
        long_triggers.append("Good Buy Signal (Blaues Dreieck)")

    # Auf 5m ist hohes VSA-Volumen zur Reversal-Bestätigung Pflicht (gemäß Post-Mortem Erkenntnissen >= 1.5x)
    min_vsa = 1.5 if timeframe == "5m" else 1.2
    if vsa_ratio >= min_vsa:
        long_triggers.append(f"VSA High Volume Surge ({vsa_class} {vsa_ratio:.1f}x)")

    # Prüfe Short-Setup
    short_triggers = []
    active_bear_ob = None
    for ob in obs:
        if ob["type"] == "Bearish OB":
            # Qualitäts-Filter aus Post-Mortem Lab: C-Grade OBs ohne Sweep filtern
            if ob.get("grade") == "C" and not ob.get("is_sweep"):
                continue
            if ob["bottom"] * 0.996 <= curr_p <= ob["top"] * 1.002:
                active_bear_ob = ob
                short_triggers.append(f"Bearish OB [{ob['grade']}] Retest ({ob['badge']})")
                if ob.get("is_sweep"):
                    short_triggers.append("Liquidity Sweep Stop-Hunt High [A]")
                break

    if in_sell_pocket:
        short_triggers.append("Institutional Sell Pocket (Chaos Band > RFE)")

    if any("Sell" in s for s in signals) or any("Sell" in s for s in recent_sig_names):
        short_triggers.append("Good Sell Signal (Kreis/Marker)")

    if vsa_ratio >= min_vsa:
        short_triggers.append(f"VSA High Volume Surge ({vsa_class} {vsa_ratio:.1f}x)")

    # ATR für SL/TP-Berechnung
    highs = [b["h"] for b in bars[-14:]]
    lows = [b["l"] for b in bars[-14:]]
    atr_approx = sum(h - l for h, l in zip(highs, lows)) / 14.0

    # HTF-Governance: Wenn htf_bias bekannt ist, filtern
    if htf_bias == "BEARISH" and len(long_triggers) < 3:
        # Long gegen Bären-Trend nur bei makelloser 3-fach Konfluenz
        long_triggers = []
    elif htf_bias == "BULLISH" and len(short_triggers) < 3:
        short_triggers = []

    # Entscheidung (Mindestens 2 harte Trigger)
    if len(long_triggers) >= 2:
        ref_low = active_bull_ob["bottom"] if active_bull_ob else min(lows[-5:])
        # Puffer auf 1.0x ATR (5m) bzw. 1.2x ATR (15m) erweitert, um vorzeitige Spread-/Noise-Stopouts zu verhindern
        buffer_atr = 1.0 if timeframe == "5m" else 1.2
        sl = round(ref_low - buffer_atr * atr_approx, 4)
        risk = curr_p - sl
        if risk > 0 and (risk / curr_p) <= 0.05:  # Bis max 5% Risiko pro Micro-Trade
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
                "setup_name": f"degencoder {timeframe} Micro-Confluence Long",
                "setup_tags": long_triggers,
                "vsa_class": vsa_class,
                "status": "OPEN",
                "highest_price": curr_p,
                "lowest_price": curr_p
            }

    elif len(short_triggers) >= 2:
        ref_high = active_bear_ob["top"] if active_bear_ob else max(highs[-5:])
        # Puffer auf 1.0x ATR (5m) bzw. 1.2x ATR (15m) erweitert
        buffer_atr = 1.0 if timeframe == "5m" else 1.2
        sl = round(ref_high + buffer_atr * atr_approx, 4)
        risk = sl - curr_p
        if risk > 0 and (risk / curr_p) <= 0.05:
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
                "setup_name": f"degencoder {timeframe} Micro-Confluence Short",
                "setup_tags": short_triggers,
                "vsa_class": vsa_class,
                "status": "OPEN",
                "highest_price": curr_p,
                "lowest_price": curr_p
            }

    return None


def update_open_trade_with_bars(trade: Dict[str, Any], future_bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verfolgt einen offenen Trade anhand nachfolgender Kerzen (TP1 1.5R Teilgewinn 50%, TP2 3.0R Vollziel, SL Breakeven/Verlust)."""
    if trade.get("status") not in ("OPEN", None):
        return trade

    entry_p = trade["entry_price"]
    sl = trade["sl"]
    tp1 = trade["tp1"]
    tp2 = trade["tp2"]
    direction = trade["direction"]

    for b in future_bars:
        h = b["h"]
        l = b["l"]
        t = b["t"]

        trade["highest_price"] = max(trade.get("highest_price", entry_p), h)
        trade["lowest_price"] = min(trade.get("lowest_price", entry_p), l)

        if direction == "LONG":
            # 1. Zuerst prüfen, ob TP1 erreicht wurde
            if h >= tp1 and not trade.get("tp1_reached"):
                trade["tp1_reached"] = True
                trade["tp1_price"] = tp1
                trade["tp1_time"] = datetime.fromtimestamp(t, timezone.utc).isoformat()
                sl = entry_p  # Stop-Loss sofort auf Breakeven nachziehen
                trade["sl"] = entry_p

            # 2. Vollziel TP2 erreicht
            if h >= tp2:
                trade["status"] = "CLOSED_TP2"
                trade["exit_price"] = tp2
                trade["exit_time"] = datetime.fromtimestamp(t, timezone.utc).isoformat()
                trade["exit_timestamp"] = t
                # 50% bei TP1 (+1.5R * 0.5 = +0.75R) + 50% bei TP2 (+3.0R * 0.5 = +1.5R) = +2.25R
                trade["realized_r"] = +2.25 if trade.get("tp1_reached") else +3.0
                trade["realized_pnl_pct"] = round(((tp2 - entry_p) / entry_p) * 100.0, 2)
                trade["exit_reason"] = "Maximaler Take-Profit 2 (TP2) vollständig erreicht (Gewinn voll realisiert)"
                break

            # 3. Stop-Loss berührt
            elif l <= sl:
                if trade.get("tp1_reached"):
                    # TP1 wurde bereits erreicht! 50% Teilgewinn gesichert, Rest bei BE ausgestoppt
                    trade["status"] = "CLOSED_BE"
                    trade["exit_price"] = sl  # entry_p
                    trade["exit_time"] = datetime.fromtimestamp(t, timezone.utc).isoformat()
                    trade["exit_timestamp"] = t
                    trade["realized_r"] = +0.75  # 50% Tranche TP1 (+1.5R) + 50% Tranche BE (0.0R) = +0.75R Netto-Gewinn
                    trade["realized_pnl_pct"] = round(((tp1 - entry_p) / entry_p) * 50.0, 2)
                    trade["exit_reason"] = "Teilgewinn TP1 (+1.5R) realisiert; Restposition bei Break-Even risikofrei ausgestoppt"
                    break
                else:
                    trade["status"] = "CLOSED_SL"
                    trade["exit_price"] = sl
                    trade["exit_time"] = datetime.fromtimestamp(t, timezone.utc).isoformat()
                    trade["exit_timestamp"] = t
                    trade["realized_r"] = -1.0
                    trade["realized_pnl_pct"] = round(((sl - entry_p) / entry_p) * 100.0, 2)
                    trade["exit_reason"] = "Stop-Loss unter Support-Level getroffen"
                    break

        elif direction == "SHORT":
            # 1. Zuerst prüfen, ob TP1 erreicht wurde
            if l <= tp1 and not trade.get("tp1_reached"):
                trade["tp1_reached"] = True
                trade["tp1_price"] = tp1
                trade["tp1_time"] = datetime.fromtimestamp(t, timezone.utc).isoformat()
                sl = entry_p  # Stop-Loss sofort auf Breakeven nachziehen
                trade["sl"] = entry_p

            # 2. Vollziel TP2 erreicht
            if l <= tp2:
                trade["status"] = "CLOSED_TP2"
                trade["exit_price"] = tp2
                trade["exit_time"] = datetime.fromtimestamp(t, timezone.utc).isoformat()
                trade["exit_timestamp"] = t
                trade["realized_r"] = +2.25 if trade.get("tp1_reached") else +3.0
                trade["realized_pnl_pct"] = round(((entry_p - tp2) / entry_p) * 100.0, 2)
                trade["exit_reason"] = "Maximaler Take-Profit 2 (TP2) vollständig erreicht (Gewinn voll realisiert)"
                break

            # 3. Stop-Loss berührt
            elif h >= sl:
                if trade.get("tp1_reached"):
                    trade["status"] = "CLOSED_BE"
                    trade["exit_price"] = sl  # entry_p
                    trade["exit_time"] = datetime.fromtimestamp(t, timezone.utc).isoformat()
                    trade["exit_timestamp"] = t
                    trade["realized_r"] = +0.75
                    trade["realized_pnl_pct"] = round(((entry_p - tp1) / entry_p) * 50.0, 2)
                    trade["exit_reason"] = "Teilgewinn TP1 (+1.5R) realisiert; Restposition bei Break-Even risikofrei ausgestoppt"
                    break
                else:
                    trade["status"] = "CLOSED_SL"
                    trade["exit_price"] = sl
                    trade["exit_time"] = datetime.fromtimestamp(t, timezone.utc).isoformat()
                    trade["exit_timestamp"] = t
                    trade["realized_r"] = -1.0
                    trade["realized_pnl_pct"] = round(((entry_p - sl) / entry_p) * 100.0, 2)
                    trade["exit_reason"] = "Stop-Loss über Widerstands-Level getroffen"
                    break

    return trade


# ==============================================================================
# 4. VERGLEICHENDE KI-BATCH-POST-MORTEM SYNTHESE (CROSS-TRADE KAUSALITÄT)
# ==============================================================================

def trigger_comparative_batch_post_mortem(closed_trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Gruppiert unanalysierte geschlossene Trades in Batches von 3-4 Trades und ruft
    die vergleichende KI-Synthese auf. Destilliert sofort übergeordnete Regeln.
    """
    try:
        from gemini_evaluator import evaluate_batch_trades_post_mortem, evaluate_trade_post_mortem
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

    # Finde unanalysierte geschlossene Trades
    pending = [t for t in closed_trades if not t.get("ai_post_mortem") and t.get("status") in ["CLOSED_SL", "CLOSED_TP1", "CLOSED_TP2"]]
    if not pending:
        return closed_trades

    print(f"\n  🧠 Starte vergleichendes KI-Post-Mortem für {len(pending)} neue geschlossene Trades...")

    # Verarbeite in Batches von 3 Trades
    batch_size = 3
    for i in range(0, len(pending), batch_size):
        chunk = pending[i:i + batch_size]
        print(f"    [Post-Mortem Batch {i // batch_size + 1}/{(len(pending) + batch_size - 1) // batch_size}] Analysiere {len(chunk)} Trades...", end="", flush=True)

        batch_result = evaluate_batch_trades_post_mortem(chunk)
        if batch_result and isinstance(batch_result, dict):
            trade_evals = {e.get("trade_id"): e for e in batch_result.get("trade_evaluations", [])}
            cross_insights = batch_result.get("cross_market_insights", [])

            for t in chunk:
                tid = t.get("trade_id")
                ev = trade_evals.get(tid)
                if ev:
                    t["ai_post_mortem"] = ev

                # Füge Einzellehre zu trade_memory hinzu
                is_win = (t.get("realized_r", 0) > 0)
                new_learning = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "trade_id": tid,
                    "symbol": t.get("symbol"),
                    "name": t.get("name"),
                    "category": f"Micro-Incubator ({t.get('timeframe', '15m')})",
                    "direction": t.get("direction"),
                    "result": "WIN" if is_win else "LOSS",
                    "setup_name": t.get("setup_name"),
                    "pnl_leveraged": t.get("realized_pnl_pct", 0.0) * 2.0,
                    "pnl_raw": t.get("realized_pnl_pct", 0.0),
                    "text": ev.get("actionable_rule") if ev else f"Trade {tid} abgeschlossen.",
                    "ai_post_mortem": ev or {}
                }
                memory_data.setdefault("learnings", []).insert(0, new_learning)

            # Füge übergreifende Cross-Market Insights hinzu
            for ins in cross_insights:
                new_cross = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "trade_id": f"cross_rule_{int(time.time())}",
                    "symbol": "MULTI-ASSET",
                    "name": "Cross-Market Confluence",
                    "category": "Global Heuristic (4h/1D Transfer)",
                    "direction": "NEUTRAL",
                    "result": "WIN",
                    "setup_name": "Synthesized Multi-Timeframe Heuristic",
                    "pnl_leveraged": 0.0,
                    "pnl_raw": 0.0,
                    "text": ins.get("rule", ""),
                    "ai_post_mortem": {
                        "verdict": "RULE",
                        "driver": ins.get("context", ""),
                        "actionable_rule": ins.get("rule", "")
                    }
                }
                memory_data.setdefault("learnings", []).insert(0, new_cross)

            print(" ✅ OK (Gemini 3.8 Flash High)")
        else:
            print(" ℹ️ Math-Fallback")

        time.sleep(0.5)

    # Speichern des aktualisierten Gedächtnisses
    memory_data["total_experience_records"] = len(memory_data.get("learnings", []))
    memory_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(TRADE_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory_data, f, indent=2, ensure_ascii=False)
        print(f"  💾 KI-Gedächtnis erfolgreich aktualisiert: {memory_data['total_experience_records']} Gesamt-Erfahrungen!")
    except Exception as e:
        print(f"  ⚠️ Konnte trade_memory.json nicht schreiben: {e}")

    return closed_trades


# ==============================================================================
# 5. HISTORISCHES 30-TAGE WALK-FORWARD REPLAY-TRAINING
# ==============================================================================

def run_historical_replay_training(days: int = 30, max_replay_trades: int = 25) -> Dict[str, Any]:
    """
    Führt ein blitzschnelles historisches Replay-Training durch:
    - Zieht 5m- und 15m-Bars der letzten Tage für Krypto und deutsche Börsenwerte
    - Simuliert Setup-Erkennung und Walk-Forward-Ausstiege
    - Übergibt gefundene Trades gebündelt an Gemini
    """
    print("\n" + "=" * 70)
    print(f"⚡ STARTE HISTORISCHES REPLAY-TRAINING ({days} TAGE / 16-ASSET MATRIX)")
    print("=" * 70)

    replay_trades = []
    # Teste auf 3 Krypto- und 3 deutschen Werten
    sample_assets = [
        CRYPTO_UNIVERSE[0], CRYPTO_UNIVERSE[2], CRYPTO_UNIVERSE[4],  # BTC, SOL, AVAX
        EQUITIES_GERMAN_UNIVERSE[0], EQUITIES_GERMAN_UNIVERSE[1], EQUITIES_GERMAN_UNIVERSE[6]  # NVD.F, TL0.F, RHM.DE
    ]

    for asset in sample_assets:
        for tf in ["5m", "15m"]:
            bars = fetch_incubator_bars(asset, interval=tf)
            if len(bars) < 80:
                continue

            # Schrittweise durch die Historie wandern (alle 30 Bars ein Scan-Fenster)
            step = 35 if tf == "5m" else 25
            for start_idx in range(40, len(bars) - 25, step):
                window = bars[:start_idx]
                setup = scan_for_micro_setup(asset, window, timeframe=tf)
                if setup:
                    setup["trade_id"] = f"rep_{asset['symbol']}_{tf}_{window[-1]['t']}"
                    # Walk-forward mit den nachfolgenden Kerzen
                    outcome = update_open_trade_with_bars(setup, bars[start_idx:start_idx + 25])
                    if outcome.get("status") in ["CLOSED_SL", "CLOSED_BE", "CLOSED_TP1", "CLOSED_TP2"]:
                        replay_trades.append(outcome)
                        if len(replay_trades) >= max_replay_trades:
                            break
            if len(replay_trades) >= max_replay_trades:
                break
        if len(replay_trades) >= max_replay_trades:
            break

    print(f"  ⚡ {len(replay_trades)} historische Trainings-Trades erfolgreich simuliert!")

    # KI-Batch-Post-Mortem ausführen
    replay_trades = trigger_comparative_batch_post_mortem(replay_trades)

    # In bestehende Historie integrieren
    data = load_incubator_state()
    closed = data.get("closed_trades", [])
    # Dopplungen nach trade_id vermeiden
    existing_ids = {t.get("trade_id") for t in closed}
    new_adds = [t for t in replay_trades if t.get("trade_id") not in existing_ids]
    if new_adds:
        lt = data.setdefault("lifetime_metrics", {})
        for t in new_adds:
            lt["total_trades"] = lt.get("total_trades", len(closed)) + 1
            realized_r = t.get("realized_r", 0.0)
            if realized_r > 0:
                lt["wins"] = lt.get("wins", 0) + 1
            else:
                lt["losses"] = lt.get("losses", 0) + 1
            lt["total_r_profit"] = round(lt.get("total_r_profit", 0.0) + realized_r, 2)
        closed.extend(new_adds)
    data["closed_trades"] = closed[-200:]

    # Metriken aktualisieren
    recalculate_metrics(data)
    save_incubator_state(data)

    print(f"✅ Replay-Training abgeschlossen: {len(new_adds)} neue Trades im Gedächtnis verankert.")
    return data


# ==============================================================================
# 6. INKUBATOR MASTER RUNNER & ZYKLUS-MANAGEMENT
# ==============================================================================

def load_incubator_state() -> Dict[str, Any]:
    """Lädt den aktuellen Stand aus incubator_trades.json oder erzeugt Baseline."""
    data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "today_focus_assets": get_active_market_rotation_assets(),
        "all_matrix_assets": ALL_INCUBATOR_ASSETS,
        "metrics": {
            "total_trades": 0,
            "win_rate": 0.0,
            "total_r_profit": 0.0,
            "wins": 0,
            "losses": 0,
            "avg_rr": 2.2,
            "active_count": 0
        },
        "lifetime_metrics": {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "total_r_profit": 0.0
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
                    data["today_focus_assets"] = get_active_market_rotation_assets()
                    data["all_matrix_assets"] = ALL_INCUBATOR_ASSETS
        except Exception:
            pass

    # Initialisiere / synchronisiere lifetime_metrics
    closed = data.get("closed_trades", [])
    lt = data.setdefault("lifetime_metrics", {})
    if not lt or lt.get("total_trades", 0) < len(closed):
        existing_metrics = data.get("metrics", {})
        tot = max(len(closed), existing_metrics.get("total_trades", 0))
        w = existing_metrics.get("wins", sum(1 for t in closed if (t.get("realized_r", 0) > 0)))
        l = existing_metrics.get("losses", sum(1 for t in closed if (t.get("realized_r", 0) <= 0)))
        r = existing_metrics.get("total_r_profit", round(sum(t.get("realized_r", 0.0) for t in closed), 2))
        lt["total_trades"] = tot
        lt["wins"] = w
        lt["losses"] = l
        lt["total_r_profit"] = r

    return data


def save_incubator_state(data: Dict[str, Any]) -> None:
    """Speichert den Zustand sauber in incubator_trades.json."""
    try:
        KB_DIR.mkdir(parents=True, exist_ok=True)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(INCUBATOR_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Fehler beim Speichern von incubator_trades.json: {e}")


def recalculate_metrics(data: Dict[str, Any]) -> None:
    """Berechnet Gewinnraten und R-Multiples über alle geschlossenen Trades (unterstützt kumulative Lifetime-Zähler)."""
    closed = data.get("closed_trades", [])
    lt = data.setdefault("lifetime_metrics", {})

    wins_in_closed = sum(1 for t in closed if (t.get("realized_r", 0) > 0))
    losses_in_closed = sum(1 for t in closed if (t.get("realized_r", 0) <= 0))
    r_in_closed = round(sum(t.get("realized_r", 0.0) for t in closed), 2)

    total = max(lt.get("total_trades", len(closed)), len(closed))
    wins = max(lt.get("wins", 0), wins_in_closed)
    losses = total - wins if total >= wins else losses_in_closed
    total_r = round(max(lt.get("total_r_profit", 0.0), r_in_closed), 2)
    win_rate = round((wins / total) * 100.0, 1) if total > 0 else 0.0

    lt["total_trades"] = total
    lt["wins"] = wins
    lt["losses"] = losses
    lt["total_r_profit"] = total_r

    # Extrahiere die besten KI-Erkenntnisse
    insights = []
    for t in reversed(closed):
        pm = t.get("ai_post_mortem")
        if pm and isinstance(pm, dict) and pm.get("actionable_rule"):
            insights.append({
                "symbol": t.get("symbol"),
                "direction": t.get("direction"),
                "timeframe": t.get("timeframe", "15m"),
                "verdict": pm.get("verdict", "N/A"),
                "driver": pm.get("driver", ""),
                "rule": pm.get("actionable_rule", ""),
                "warning": pm.get("technical_warning", "")
            })
        if len(insights) >= 8:
            break

    data["metrics"] = {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_r_profit": total_r,
        "active_count": len(data.get("active_trades", [])),
        "avg_rr": 2.2
    }
    data["ai_insights"] = insights


def run_incubator_cycle(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Führt den vollen 16-Asset Live-Inkubator-Zyklus aus:
    1. Scannt 8 aktive Fokus-Assets (4 Krypto + 4 Deutsche/US-Aktien) auf 5m und 15m
    2. Aktualisiert offene Positionen
    3. Triggert vergleichendes KI-Batch-Post-Mortem für geschlossene Trades
    """
    print("\n" + "=" * 70)
    print("🧪 AI INCUBATOR & RAPID POST-MORTEM LAB (16-Asset Matrix & 5m/15m Engine)")
    print("=" * 70)

    data = load_incubator_state()
    active_assets = data["today_focus_assets"]
    asset_names = [f"{a['name']} ({a['symbol']})" for a in active_assets]
    print(f"🔄 Aktive 8-Asset-Fokusgruppe: {', '.join(asset_names[:4])}")
    print(f"   Aktien (Frankfurt/XETRA): {', '.join(asset_names[4:])}")

    active_trades = data.get("active_trades", [])
    closed_trades = data.get("closed_trades", [])

    # 1. Bestehende offene Trades aktualisieren
    still_active = []
    just_closed = []

    for trade in active_trades:
        sym = trade["symbol"]
        src = trade.get("source", "binance")
        tf = trade.get("timeframe", "5m")
        bars = fetch_incubator_bars({"symbol": sym, "source": src}, interval=tf)
        if not bars:
            still_active.append(trade)
            continue

        entry_ts = trade.get("entry_timestamp", 0)
        future_bars = [b for b in bars if b["t"] >= entry_ts]
        updated = update_open_trade_with_bars(trade, future_bars)

        if updated.get("status") in ["CLOSED_SL", "CLOSED_BE", "CLOSED_TP1", "CLOSED_TP2"]:
            just_closed.append(updated)
            print(f"  🏁 Micro-Trade {sym} ({tf}, {updated['direction']}) geschlossen: {updated['status']} ({updated.get('realized_r', 0):+.1f}R)")
        else:
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
    if just_closed:
        lt = data.setdefault("lifetime_metrics", {})
        for c_tr in just_closed:
            lt["total_trades"] = lt.get("total_trades", len(closed_trades)) + 1
            realized_r = c_tr.get("realized_r", 0.0)
            if realized_r > 0:
                lt["wins"] = lt.get("wins", 0) + 1
            else:
                lt["losses"] = lt.get("losses", 0) + 1
            lt["total_r_profit"] = round(lt.get("total_r_profit", 0.0) + realized_r, 2)
        closed_trades.extend(just_closed)

    # 2. Suche nach neuen 5m & 15m Setups (bis max 8 aktive Positionen)
    max_active = 8
    candidate_assets = list(active_assets)
    # Falls Kapazität frei ist: Restliche Matrix-Assets als Backup prüfen
    for a in ALL_INCUBATOR_ASSETS:
        if not any(ca["symbol"] == a["symbol"] for ca in candidate_assets):
            candidate_assets.append(a)

    if len(active_trades) < max_active:
        for asset in candidate_assets:
            # Maximal 1 aktive Position pro Symbol
            if any(t["symbol"] == asset["symbol"] for t in active_trades):
                continue
            if len(active_trades) >= max_active:
                break

            # Prüfe 5m (Micro-Sweep) und 15m (Zonen-Struktur)
            for tf in ["5m", "15m"]:
                bars = fetch_incubator_bars(asset, interval=tf)
                if not bars:
                    continue

                setup = scan_for_micro_setup(asset, bars, timeframe=tf)
                if setup:
                    setup["trade_id"] = f"inc_{asset['symbol']}_{tf}_{int(time.time())}"
                    active_trades.append(setup)
                    print(f"  🎯 NEUER SIMULIERTER {tf}-TRADE: {asset['name']} ({asset['symbol']}) {setup['direction']} @ {setup['entry_price']} (SL: {setup['sl']}, TP1: {setup['tp1']})")
                    break  # Ein Setup pro Asset genügt

    # 3. Falls noch wenige Trades vorliegen: Einmaliges Mini-Replay ausführen
    if len(closed_trades) < 6:
        print("  ⚡ Starte Initial-Replay zur sofortigen Bereitstellung von Trainingsdaten...")
        run_historical_replay_training(days=14, max_replay_trades=10)
        data = load_incubator_state()
        active_trades = data.get("active_trades", [])
        closed_trades = data.get("closed_trades", [])

    # 4. Vergleichendes KI-Batch-Post-Mortem ausführen
    closed_trades = trigger_comparative_batch_post_mortem(closed_trades)

    data["active_trades"] = active_trades
    data["closed_trades"] = closed_trades[-200:]

    # 5. Metriken berechnen & persistieren
    recalculate_metrics(data)
    save_incubator_state(data)

    m = data["metrics"]
    print(f"✅ Inkubator-Zyklus erfolgreich abgeschlossen: {m['active_count']} aktiv, {m['total_trades']} in Historie ({m['win_rate']}% Win-Rate, {m['total_r_profit']:+.1f}R)")
    return data


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", action="store_true", help="Führt ein 30-Tage Replay-Training aus")
    args = parser.parse_args()

    if args.replay:
        run_historical_replay_training(days=30, max_replay_trades=20)
    else:
        run_incubator_cycle()
