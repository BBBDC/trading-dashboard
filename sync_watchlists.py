#!/usr/bin/env python3
"""
Dynamic Watchlist Synchronizer & Pruner.
- Synchronisiert Symbole direkt mit den TradingView-Watchlists.
- Erkennt neu hinzugefügte Symbole automatisch und analysiert sie.
- Entfernt gelöschte Symbole sauber aus der Datenbank und löscht verwaiste Charts.
- Aktualisiert das Dashboard und die Artifacts automatisch.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"
CHARTS_DIR = BASE_DIR / "dashboard" / "charts"
WL_CACHE = BASE_DIR / "knowledge_base" / "live_watchlists.json"


def get_base_ticker(sym):
    parts = sym.split(":")
    ticker = parts[1] if len(parts) > 1 else parts[0]
    for quote in ["USD", "USDT", "USDC", "EUR", "BTC"]:
        if ticker.endswith(quote) and len(ticker) > len(quote):
            ticker = ticker[:-len(quote)]
            break
    return ticker.upper()


def infer_meta(sym, wl_name="Watchlist"):
    s = sym.upper()
    ticker = sym.split(":")[1] if ":" in sym else sym
    if any(ex in s for ex in ["BINANCE:", "COINBASE:", "KRAKEN:", "BITSTAMP:", "UNISWAP", "AERODROME"]) or any(s.endswith(q) for q in ["USD", "USDT", "USDC", "BTC", "ETH", "USDT.P"]):
        if "BTC.D" in s or "TOTAL" in s:
            return ticker, "Krypto-Makro", "Macro"
        return ticker, "Crypto", "Crypto"
    elif any(ex in s for ex in ["COMEX:", "NYMEX:", "ICEEUR:", "CBOT:", "LME:", "CAPITALCOM:", "TVC:GOLD", "TVC:SILVER", "TVC:PLATINUM", "TVC:PALLADIUM", "RUS:BR"]):
        return ticker, "Rohstoffe & Metalle", "Commodity"
    elif any(idx in s for idx in ["SP:SPX", "TVC:NDX", "TVC:DJI", "XETR:DAX", "TVC:DXY", "FX_IDC:"]):
        return ticker, "Indizes / Devisen", "Macro"
    else:
        return ticker, "Aktien", "Stock"


def load_live_watchlists():
    if WL_CACHE.exists():
        try:
            with open(WL_CACHE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "watchlists" in data:
                    return data["watchlists"]
                elif isinstance(data, list):
                    return data
        except Exception as e:
            print(f"Fehler beim Laden von {WL_CACHE}: {e}", file=sys.stderr)
    return []


def sync_watchlists(live_wls=None, rebuild=False):
    if live_wls is None:
        live_wls = load_live_watchlists()

    if not live_wls:
        print("Keine Live-Watchlists verfügbar. Abbruch der Synchronisation.")
        return

    # 1. Sammle alle gültigen Symbole aus den Live-Watchlists
    active_symbols_map = {}
    for wl in live_wls:
        wl_name = wl.get("name", "Watchlist")
        for sym in wl.get("symbols", []):
            if sym.startswith(("MULTPL:", "ECONOMICS:", "FTX:", "BITTREX:")):
                continue
            base = get_base_ticker(sym)
            if base not in active_symbols_map:
                name, cat, asset_type = infer_meta(sym, wl_name)
                active_symbols_map[base] = {
                    "symbol": sym,
                    "name": name,
                    "category": cat,
                    "asset_type": asset_type,
                    "base": base,
                    "source_watchlist": wl_name
                }

    print(f"TradingView Watchlists aktiv: {len(active_symbols_map)} einzigartige Assets identifiziert.")

    # 2. Lade existierende Datenbank
    if not DB_FILE.exists():
        print(f"Datenbank {DB_FILE} nicht gefunden!")
        return

    with open(DB_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)

    existing_assets = db.get("assets", [])
    existing_by_base = {get_base_ticker(a["symbol"]): a for a in existing_assets}

    # 3. Ermittle Hinzugefügte und Gelöschte
    current_bases = set(active_symbols_map.keys())
    db_bases = set(existing_by_base.keys())

    added_bases = current_bases - db_bases
    removed_bases = db_bases - current_bases
    retained_bases = db_bases & current_bases

    print("\n" + "=" * 55)
    print("WATCHLIST-SYNCHRONISATIONS-BERICHT")
    print("=" * 55)
    print(f"Beibehaltene Assets : {len(retained_bases)}")
    print(f"Neu hinzugefügt     : {len(added_bases)}")
    print(f"Aus Watchlists gelöscht: {len(removed_bases)}")

    # 4. Entferne gelöschte Symbole & bereinige Chart-Dateien
    pruned_assets = []
    deleted_charts_count = 0
    for a in existing_assets:
        base = get_base_ticker(a["symbol"])
        if base in removed_bases:
            print(f"  [-] GELÖSCHT: {a['name']} ({a['symbol']}) - Aus Watchlist entfernt.")
            # Lösche zugehörige Charts
            safe_sym = a["symbol"].replace(":", "_").replace("!", "_").replace(".", "_").replace("/", "_")
            for tf in ["4h", "8h", "1D"]:
                chart_path = CHARTS_DIR / f"{safe_sym}_{tf}.svg"
                if chart_path.exists():
                    try:
                        chart_path.unlink()
                        deleted_charts_count += 1
                    except Exception:
                        pass
        else:
            pruned_assets.append(a)

    if deleted_charts_count > 0:
        print(f"  -> {deleted_charts_count} verwaiste Chart-Dateien sauber bereinigt.")

    # 5. Füge neue Symbole hinzu (mit Standardwerten und Basis-Setup)
    from chart_generator import generate_svg_chart

    added_count = 0
    for base in added_bases:
        meta = active_symbols_map[base]
        sym = meta["symbol"]
        safe_sym = sym.replace(":", "_").replace("!", "_").replace(".", "_").replace("/", "_")
        print(f"  [+] NEU HINZUGEFÜGT: {meta['name']} ({sym}) aus '{meta['source_watchlist']}'")

        # Initialer Datenrahmen
        new_entry = {
            "symbol": sym,
            "name": meta["name"],
            "category": meta["category"],
            "asset_type": meta["asset_type"],
            "price": 100.0,
            "signal": "NEUTRAL",
            "setup_name": "Neu synchronisiert - Bereit für HTF-Analyse",
            "score": 50,
            "crv": 2.0,
            "entry_range": [95.0, 98.0],
            "stop_loss": 90.0,
            "take_profit_1": 105.0,
            "take_profit_2": 115.0,
            "reasons": [
                f"Neu aus TradingView-Watchlist '{meta['source_watchlist']}' synchronisiert.",
                "Multi-Timeframe-Scan wird beim nächsten Scan-Zyklus aktualisiert."
            ],
            "timeframes": {
                "1D": {
                    "name": f"{meta['name']} ({sym})",
                    "trend": "NEUTRAL",
                    "rsi": 50.0,
                    "channel_position": "Kanal-Mitte",
                    "vsa_class": "Normal Volume",
                    "golden_pocket": [92.0, 94.0],
                    "in_golden_pocket": False,
                    "divergences": []
                },
                "8h": {
                    "name": f"{meta['name']} ({sym})",
                    "trend": "NEUTRAL",
                    "rsi": 50.0,
                    "channel_position": "Kanal-Mitte",
                    "vsa_class": "Normal Volume",
                    "golden_pocket": [92.0, 94.0],
                    "in_golden_pocket": False,
                    "divergences": []
                },
                "4h": {
                    "name": f"{meta['name']} ({sym})",
                    "trend": "NEUTRAL",
                    "rsi": 50.0,
                    "channel_position": "Kanal-Mitte",
                    "vsa_class": "Normal Volume",
                    "golden_pocket": [92.0, 94.0],
                    "in_golden_pocket": False,
                    "divergences": []
                }
            },
            "analyst_note": f"Frisch aus TV-Watchlist '{meta['source_watchlist']}' synchronisiert. Bereit für automatische Scan-Berechnung.",
            "charts": {}
        }

        # Generiere initiale SVGs
        for tf in ["4h", "8h", "1D"]:
            svg = generate_svg_chart(None, new_entry["timeframes"][tf], timeframe=tf)
            c_path = CHARTS_DIR / f"{safe_sym}_{tf}.svg"
            with open(c_path, "w", encoding="utf-8") as f:
                f.write(svg)
            new_entry["charts"][tf] = f"charts/{safe_sym}_{tf}.svg"

        pruned_assets.append(new_entry)
        added_count += 1

    # 6. Aktualisiere Datenbank
    pruned_assets.sort(key=lambda x: x.get("score", 0), reverse=True)
    db["assets"] = pruned_assets
    db["total_analyzed"] = len(pruned_assets)
    db["long_count"] = sum(1 for a in pruned_assets if a["signal"] == "LONG")
    db["short_count"] = sum(1 for a in pruned_assets if a["signal"] == "SHORT")
    db["neutral_count"] = sum(1 for a in pruned_assets if a["signal"] == "NEUTRAL")
    db["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

    print("=" * 55)
    print(f"Synchronisation erfolgreich abgeschlossen! Gesamt-Assets: {len(pruned_assets)}")
    print(f"LONG: {db['long_count']} | SHORT: {db['short_count']} | NEUTRAL: {db['neutral_count']}")
    print("=" * 55 + "\n")

    # 7. Baue Dashboard und Artifact neu (optional)
    if rebuild:
        import subprocess
        subprocess.run([sys.executable, str(BASE_DIR / "build_dashboard.py")], check=True)


if __name__ == "__main__":
    sync_watchlists(rebuild=True)
