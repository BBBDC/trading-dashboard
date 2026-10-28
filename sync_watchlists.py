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
import time
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"
CHARTS_DIR = BASE_DIR / "dashboard" / "charts"
WL_CACHE = BASE_DIR / "knowledge_base" / "live_watchlists.json"

TRADEGATE_NAMES = {
    "TL0": "Tesla (Tradegate)",
    "NVD": "Nvidia (Tradegate)",
    "MTE": "Micron (Tradegate)",
    "RHM": "Rheinmetall",
    "AMD": "AMD (Tradegate)",
    "AMZ": "Amazon (Tradegate)",
    "SIE": "Siemens",
    "YDX": "BYD Company",
    "SPX": "S&P 500 (Tradegate)",
    "MSF": "Microsoft (Tradegate)",
    "ABEA": "Alphabet A (Tradegate)",
    "PTX": "Palantir (Tradegate)",
    "2PP": "PayPal (Tradegate)",
    "FB2A": "Meta Platforms (Tradegate)",
    "APC": "Apple (Tradegate)",
    "1YD": "Eli Lilly (Tradegate)",
    "INL": "Intel (Tradegate)",
    "NFC": "Netflix (Tradegate)",
    "9MW": "Super Micro Computer",
    "CSA": "Cisco Systems (Tradegate)",
    "45C": "Broadcom (Tradegate)",
    "IBM": "IBM (Tradegate)",
    "IFX": "Infineon Technologies",
    "34Q0": "Coinbase (Tradegate)",
    "SAP": "SAP SE"
}


def infer_meta(sym, wl_name="Watchlist"):
    s = sym.upper()
    prefix = s.split(":")[0] if ":" in s else ""
    ticker = s.split(":")[1] if ":" in s else s

    if prefix == "TRADEGATE":
        name = TRADEGATE_NAMES.get(ticker, f"{ticker} (Tradegate)")
        return name, "Tradegate / EU", "Stock"
    elif any(ex in s for ex in ["BINANCE:", "COINBASE:", "KRAKEN:", "BITSTAMP:", "UNISWAP", "AERODROME"]) or any(s.endswith(q) for q in ["USD", "USDT", "USDC", "BTC", "ETH", "USDT.P"]):
        if "BTC.D" in s or "TOTAL" in s:
            return ticker, "Krypto-Makro", "Macro"
        return ticker, "Crypto", "Crypto"
    elif any(ex in s for ex in ["COMEX:", "NYMEX:", "ICEEUR:", "CBOT:", "LME:", "CAPITALCOM:", "TVC:GOLD", "TVC:SILVER", "TVC:PLATINUM", "TVC:PALLADIUM", "RUS:BR"]):
        return ticker, "Rohstoffe & Metalle", "Commodity"
    elif any(idx in s for idx in ["SP:SPX", "TVC:NDX", "TVC:DJI", "XETR:DAX", "TVC:DXY", "FX_IDC:"]):
        return ticker, "Indizes / Devisen", "Macro"
    elif prefix in ("XETR", "FWB"):
        return ticker, "Deutsche Aktien", "Stock"
    else:
        return ticker, "Aktien", "Stock"


def load_live_watchlists(refresh_from_mcp=True):
    """
    Lädt Watchlists direkt live von TradingView via MCP.
    Falls der API-Aufruf fehlschlägt, wird nahtlos der lokale Cache verwendet.
    """
    if refresh_from_mcp:
        try:
            from fetch_real_ohlcv_cache import refresh_access_token
            from batch_analyzer import fetch_live_watchlists
            tok = refresh_access_token()
            if tok:
                remote_wls = fetch_live_watchlists(tok)
                if remote_wls and isinstance(remote_wls, list) and len(remote_wls) > 0:
                    cache_payload = {
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "source": "TradingView Official MCP Server (mcp-watchlist-list-watchlists)",
                        "watchlists": remote_wls
                    }
                    WL_CACHE.parent.mkdir(parents=True, exist_ok=True)
                    with open(WL_CACHE, "w", encoding="utf-8") as f:
                        json.dump(cache_payload, f, indent=2, ensure_ascii=False)
                    print(f"✅ Live-Watchlists von TradingView MCP synchronisiert: {len(remote_wls)} Listen geladen.")
                    return remote_wls
        except Exception as e:
            print(f"⚠️ Hinweis: Live-Watchlist-Abfrage über MCP ({e}) -> Nutze lokalen Snapshot.", file=sys.stderr)

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
        live_wls = load_live_watchlists(refresh_from_mcp=True)

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
            if sym not in active_symbols_map:
                name, cat, asset_type = infer_meta(sym, wl_name)
                active_symbols_map[sym] = {
                    "symbol": sym,
                    "name": name,
                    "category": cat,
                    "asset_type": asset_type,
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
    existing_by_sym = {a["symbol"]: a for a in existing_assets}

    # 3. Ermittle Hinzugefügte und Gelöschte
    current_syms = set(active_symbols_map.keys())
    db_syms = set(existing_by_sym.keys())

    added_syms = current_syms - db_syms
    removed_syms = db_syms - current_syms
    retained_syms = db_syms & current_syms

    print("\n" + "=" * 55)
    print("WATCHLIST-SYNCHRONISATIONS-BERICHT")
    print("=" * 55)
    print(f"Beibehaltene Assets : {len(retained_syms)}")
    print(f"Neu hinzugefügt     : {len(added_syms)}")
    print(f"Aus Watchlists gelöscht: {len(removed_syms)}")

    # 4. Entferne gelöschte Symbole & bereinige Chart-Dateien
    pruned_assets = []
    deleted_charts_count = 0
    for a in existing_assets:
        sym = a["symbol"]
        if sym in removed_syms:
            print(f"  [-] GELÖSCHT: {a['name']} ({sym}) - Aus Watchlist entfernt.")
            safe_sym = sym.replace(":", "_").replace("!", "_").replace(".", "_").replace("/", "_")
            for tf in ["1h", "4h", "1D", "1W", "3D", "8h"]:
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
    for sym in added_syms:
        meta = active_symbols_map[sym]
        safe_sym = sym.replace(":", "_").replace("!", "_").replace(".", "_").replace("/", "_")
        print(f"  [+] NEU HINZUGEFÜGT: {meta['name']} ({sym}) aus '{meta['source_watchlist']}'")

        # Initialer Datenrahmen (ohne last_analyzed -> Gatekeeper erkennt: sofort fällig!)
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
                "4h": {
                    "name": f"{meta['name']} ({sym})",
                    "trend": "NEUTRAL",
                    "rsi": 50.0,
                    "channel_position": "Kanal-Mitte",
                    "vsa_class": "Normal Volume",
                    "golden_pocket": [92.0, 94.0],
                    "in_golden_pocket": False,
                    "divergences": []
                },
                "1h": {
                    "name": f"{meta['name']} ({sym})",
                    "trend": "NEUTRAL",
                    "rsi": 50.0,
                    "channel_position": "Kanal-Mitte",
                    "vsa_class": "Normal Volume",
                    "golden_pocket": [92.0, 94.0],
                    "in_golden_pocket": False,
                    "divergences": []
                },
                "1W": {
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
            "charts": {},
            "last_analyzed": None
        }

        # Generiere initiale SVGs
        for tf in ["1h", "4h", "1D", "1W"]:
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
