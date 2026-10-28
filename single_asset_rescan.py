#!/usr/bin/env python3
"""
TradingView Super-Analyst – Single Asset Rescan Engine.
Ermöglicht den sofortigen gezielten Abruf, Indikator-Berechnung, Setup-Bewertung
und Chart-Generierung für ein einzelnes Asset (z.B. wenn ein Nutzer eine neue Position eröffnet).
Stellt sicher, dass das Asset auch in die 24/7 Dauer-Überwachung aufgenommen wird.
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"
WATCHLISTS_FILE = BASE_DIR / "knowledge_base" / "live_watchlists.json"
POSITIONS_FILE = BASE_DIR / "knowledge_base" / "user_positions.json"
CHARTS_DIR = BASE_DIR / "dashboard" / "charts"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("single_asset_rescan")


def ensure_symbol_in_watchlists(symbol):
    """Fügt das Symbol dauerhaft zur Watchlist hinzu, damit es alle 4h mitgescannt wird."""
    if not WATCHLISTS_FILE.exists():
        return
    try:
        with open(WATCHLISTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        watchlists = data.get("watchlists", [])
        found = False
        for wl in watchlists:
            if symbol in wl.get("symbols", []):
                found = True
                break

        if not found:
            # Suche nach 'Eigene Trades' oder füge zur ersten passenden Watchlist hinzu
            target_wl = None
            for wl in watchlists:
                if wl.get("name") in ("Eigene Trades", "User Trades"):
                    target_wl = wl
                    break
            if not target_wl and watchlists:
                # Eigene Watchlist-Kategorie anlegen
                target_wl = {
                    "id": 99999999,
                    "name": "Eigene Trades",
                    "type": "custom",
                    "active": True,
                    "symbols": []
                }
                watchlists.append(target_wl)

            if target_wl:
                target_wl.setdefault("symbols", []).append(symbol)
                data["watchlists"] = watchlists
                data["updated_at"] = datetime.now(timezone.utc).isoformat()
                with open(WATCHLISTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                logger.info(f"✅ {symbol} dauerhaft in Watchlist '{target_wl.get('name')}' aufgenommen (24/7 Überwachung aktiv).")
    except Exception as e:
        logger.warning(f"Konnte Symbol nicht in Watchlist eintragen: {e}")


def rescan_and_evaluate_asset(symbol, user_pos=None):
    """
    Lädt frische Kerzen, berechnet SMC/Wyckoff Indikatoren, generiert SVG Charts
    und aktualisiert das Asset in der Marktdatenbank.
    """
    logger.info(f"⚡ Starte Ad-hoc Einzel-Scan für {symbol}...")
    ensure_symbol_in_watchlists(symbol)

    # Falls keine Position übergeben wurde, in user_positions.json nachsehen
    if not user_pos and POSITIONS_FILE.exists():
        try:
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                pos_list = json.load(f).get("positions", [])
            for p in pos_list:
                if p.get("symbol") == symbol:
                    user_pos = p
                    break
        except Exception:
            pass

    from fetch_real_ohlcv_cache import fetch_bars_direct
    from market_evaluator import analyze_indicators, evaluate_quantitative_confluence
    from chart_generator import generate_svg_chart
    from market_schedule import classify_symbol

    is_crypto = (classify_symbol(symbol).get("category") == "CRYPTO")

    # 1. Frische Marktdaten direkt abrufen (1h, 4h, 1D, 1W und 3D für Krypto)
    bars_1h = fetch_bars_direct(symbol, interval="1h", count=180)
    bars_4h = fetch_bars_direct(symbol, interval="4h", count=180)
    bars_1d = fetch_bars_direct(symbol, interval="1D", count=120)
    bars_1w = fetch_bars_direct(symbol, interval="1W", count=100)
    bars_3d = fetch_bars_direct(symbol, interval="3D", count=100) if is_crypto else None

    if not bars_4h and not bars_1d and not bars_1h:
        logger.error(f"Konnte keine Live-Kerzendaten für {symbol} abrufen.")
        return None

    # Ticker & Name ableiten
    ticker = symbol.split(":")[-1]
    name = ticker.replace("USDT", " / USDT").replace("USD", "")
    if "BTC" in ticker:
        name = "Bitcoin"
    elif "ETH" in ticker:
        name = "Ethereum"
    elif "SOL" in ticker:
        name = "Solana"
    elif "NVDA" in ticker:
        name = "NVIDIA Corp."
    elif "AAPL" in ticker:
        name = "Apple Inc."

    # 2. Indikatoren berechnen
    d_1h = analyze_indicators(bars_1h, name) if bars_1h else None
    d_4h = analyze_indicators(bars_4h, name) if b_4h if (b_4h := bars_4h) else None
    d_1d = analyze_indicators(bars_1d, name) if bars_1d else None
    d_1w = analyze_indicators(bars_1w, name) if bars_1w else None
    d_3d = analyze_indicators(bars_3d, name) if bars_3d else None

    current_price = d_1d["price"] if d_1d else (d_4h["price"] if d_4h else (d_1h["price"] if d_1h else 0.0))

    tf_map = {
        "1h": d_1h,
        "4h": d_4h,
        "1D": d_1d,
        "1W": d_1w
    }
    if is_crypto and d_3d:
        tf_map["3D"] = d_3d

    # 3. Charts generieren
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_sym = symbol.replace(":", "_").replace("!", "_").replace(".", "_").replace("/", "_")
    charts_info = {}

    chart_bars = [("1h", bars_1h, d_1h), ("4h", bars_4h, d_4h), ("1D", bars_1d, d_1d), ("1W", bars_1w, d_1w)]
    if is_crypto and bars_3d and d_3d:
        chart_bars.append(("3D", bars_3d, d_3d))

    for tf, b, ind in chart_bars:
        if b and ind:
            svg_content = generate_svg_chart(b, ind, timeframe=tf, user_position=user_pos)
            chart_file = CHARTS_DIR / f"{safe_sym}_{tf}.svg"
            with open(chart_file, "w", encoding="utf-8") as f:
                f.write(svg_content)
            charts_info[tf] = f"charts/{safe_sym}_{tf}.svg"

    # 4. Setup & Confluence Score ermitteln
    category = "Krypto" if "USDT" in symbol or "BINANCE" in symbol else ("Tech" if "NASDAQ" in symbol else "Aktien")
    asset_entry = {
        "symbol": symbol,
        "name": name,
        "category": category,
        "asset_type": "Crypto" if is_crypto else "Stock",
        "price": current_price,
        "charts": charts_info,
        "timeframes": tf_map
    }

    quant_res = evaluate_quantitative_confluence(tf_map, asset_entry)
    if quant_res:
        asset_entry.update(quant_res)
        "category": category,
        "asset_type": "Crypto" if "Krypto" in category else "Stock",
        "price": current_price,
        "charts": charts_info,
        "timeframes": {
            "1D": d_1d,
            "8h": d_8h,
            "4h": d_4h
        }
    }

    quant_res = evaluate_quantitative_confluence(d_1d, d_8h, d_4h, asset_entry)
    if quant_res:
        asset_entry.update(quant_res)

    # 5. In DB mergen
    if DB_FILE.exists():
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                db = json.load(f)
            assets = db.get("assets", [])
            updated = False
            for i, a in enumerate(assets):
                if a.get("symbol") == symbol:
                    assets[i] = asset_entry
                    updated = True
                    break
            if not updated:
                assets.append(asset_entry)

            db["assets"] = assets
            db["total_analyzed"] = len(assets)
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(db, f, indent=2, ensure_ascii=False)
            logger.info(f"✅ Marktdatenbank für {symbol} aktualisiert (Live-Kurs: {current_price:,.2f} $ | Signal: {asset_entry.get('signal')})")
        except Exception as e:
            logger.error(f"Fehler beim Speichern in DB: {e}")

    return asset_entry


if __name__ == "__main__":
    test_sym = sys.argv[1] if len(sys.argv) > 1 else "BINANCE:BTCUSDT"
    res = rescan_and_evaluate_asset(test_sym)
    if res:
        print(f"Erfolg: {res['name']} ({res['symbol']}) - {res.get('signal')} ({res.get('confluence_score')}%)")
