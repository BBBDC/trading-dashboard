#!/usr/bin/env python3
"""
Echter Multi-Timeframe Chart-Generator (v3).
- Generiert für jedes der 58 Assets im Dashboard gestochen scharfe Vektor-Charts (SVG).
- Nutzt für ausnahmslos JEDEN Wert und Timeframe (4h, 8h, 1D) 100% echte historische Kerzendaten aus dem TradingView MCP Feed.
- Zeichnet dynamische kurvenförmige degencoder-Bänder, dynamische EMA 233, Wyckoff VSA Volumen und RSI(14).
"""

import os
import sys
import json
import argparse
from pathlib import Path
from fetch_real_ohlcv_cache import get_real_bars
from chart_generator import generate_svg_chart

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"
CHARTS_DIR = BASE_DIR / "dashboard" / "charts"
ARTIFACT_CHARTS = Path("/Users/maximilianmayer/.gemini/antigravity/brain/eeb75350-6985-4121-862b-6a5bd07b0cf8/charts")

parser = argparse.ArgumentParser(description="Chart Generator")
parser.add_argument("--symbols", type=str, default="", help="Kommagetrennte Liste von Symbolen zur selektiven Chart-Generierung")
args, _ = parser.parse_known_args()

CHARTS_DIR.mkdir(parents=True, exist_ok=True)
has_artifact_charts = False
try:
    if ARTIFACT_CHARTS.parent.exists():
        ARTIFACT_CHARTS.mkdir(parents=True, exist_ok=True)
        has_artifact_charts = True
except Exception:
    pass

if not DB_FILE.exists():
    print(f"Fehler: {DB_FILE} nicht gefunden!")
    sys.exit(1)

with open(DB_FILE, "r", encoding="utf-8") as f:
    db = json.load(f)

all_assets = db.get("assets", [])
if args.symbols:
    filter_set = set(s.strip() for s in args.symbols.split(",") if s.strip())
    assets = [a for a in all_assets if a["symbol"] in filter_set]
    print(f"Starte selektive Chart-Generierung für {len(assets)}/{len(all_assets)} fällige Assets...")
else:
    assets = all_assets
    print(f"Starte Chart-Generierung mit ECHTEN Daten für alle {len(assets)} Assets (4h, 8h, 1D)...")

total_generated = 0
for idx, asset in enumerate(assets, 1):
    sym = asset["symbol"]
    name = asset["name"]
    safe_sym = sym.replace(":", "_").replace("!", "_").replace(".", "_").replace("/", "_")
    timeframes = asset.get("timeframes", {})
    charts_info = {}

    print(f"[{idx}/{len(assets)}] Generiere Charts für {name} ({sym})...", end="", flush=True)

    from market_schedule import classify_symbol
    is_crypto = (classify_symbol(sym).get("category") == "CRYPTO")
    chart_tfs = ["1h", "4h", "1D", "1W"]
    if is_crypto:
        chart_tfs.append("3D")

    for tf in chart_tfs:
        tf_data = timeframes.get(tf, {}) or {}
        tf_data["name"] = f"{name} ({sym})"

        # ECHTE historische Kerzen aus MCP abrufen
        bars = get_real_bars(sym, interval=tf)
        if not bars:
            continue

        # SVG Chart generieren
        svg_str = generate_svg_chart(bars, tf_data, timeframe=tf)

        # Speichere im Workspace
        out_file = CHARTS_DIR / f"{safe_sym}_{tf}.svg"
        with open(out_file, "w", encoding="utf-8") as f_out:
            f_out.write(svg_str)

        # Speichere parallel im Artifact-Ordner für sofortige Live-Vorschau (falls vorhanden)
        if has_artifact_charts:
            try:
                art_file = ARTIFACT_CHARTS / f"{safe_sym}_{tf}.svg"
                with open(art_file, "w", encoding="utf-8") as f_art:
                    f_art.write(svg_str)
            except Exception:
                pass

        charts_info[tf] = f"charts/{safe_sym}_{tf}.svg"
        total_generated += 1

    asset["charts"] = charts_info
    print(" OK")

# Speichere aktualisierte Datenbank
with open(DB_FILE, "w", encoding="utf-8") as f:
    json.dump(db, f, indent=2, ensure_ascii=False)

print(f"\nErfolgreich! {total_generated} echte SVG-Charts in {CHARTS_DIR} und Artifact-Ordner generiert.")

# Recompile Dashboard (falls direkt als Skript ausgeführt)
if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, str(BASE_DIR / "build_dashboard.py")], check=True)
