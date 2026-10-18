#!/usr/bin/env python3
"""
TradingView Super-Analyst – Master Update Engine.
Führt die gesamte Analyse-Pipeline in einem einzigen Befehl aus:
1. Synchronisation der Live-Watchlists (Erkennt neue Symbole, löscht entfernte)
2. Abruf & Caching der echten OHLCV-Marktdaten über TradingView MCP
3. Berechnung aller Indikatoren (degencoder, FVGs, OBs, Fib GP, VSA, RSI Divs)
4. Evaluierung der Setups, Confluence-Scoring & Trade-Planung
5. Generierung aller 174+ Vektor-Charts (SVG) mit echten Kerzen und dynamischen Kurven
6. Erstellung des interaktiven HTML-Dashboards (dashboard/index.html)
"""

import os
import sys
import time
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"
CHARTS_DIR = BASE_DIR / "dashboard" / "charts"
DASHBOARD_HTML = BASE_DIR / "dashboard" / "index.html"


def stage_banner(title):
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)


def run_pipeline(force_download=False, skip_download=False, git_push=False):
    start_time = time.time()
    stage_banner("🚀 STARTE TRADINGVIEW SUPER-ANALYST MASTER PIPELINE")

    # STAGE 1: Watchlist Synchronisation
    stage_banner("STUFE 1: Watchlists mit TradingView synchronisieren")
    from sync_watchlists import sync_watchlists
    sync_watchlists()

    # STAGE 2: Echte Marktdaten herunterladen / cachen
    if not skip_download:
        stage_banner("STUFE 2: Echte OHLCV-Marktdaten über TV MCP laden")
        from fetch_real_ohlcv_cache import sync_all_real_data
        sync_all_real_data()
    else:
        print("Überspringe OHLCV-Download (Cache wird verwendet).")

    # STAGE 3: Multi-Timeframe-Marktanalyse & KI-Interpretation
    stage_banner("STUFE 3: Multi-Timeframe-Analyse & KI-Interpretation (Gemini / SMC)")
    from market_evaluator import analyze_all_markets
    analyze_all_markets()

    # STAGE 4: Charts generieren
    stage_banner("STUFE 4: Vektor-Charts mit echten Kerzen & Indikatoren rendern")
    from generate_all_charts import CHARTS_DIR as CD
    import subprocess
    subprocess.run([sys.executable, str(BASE_DIR / "generate_all_charts.py")], check=True)

    # STAGE 5: Dashboard & Historie kompilieren
    stage_banner("STUFE 5: HTML-Dashboard & Live-Historie aktualisieren")
    subprocess.run([sys.executable, str(BASE_DIR / "build_dashboard.py")], check=True)

    # STAGE 6: Git-Hosting Synchronisation (optional / bei --git-push)
    if git_push:
        git_sync_dashboard()

    # STAGE 7: Executive Summary & Smart Alerts
    elapsed = round(time.time() - start_time, 1)
    stage_banner(f"✅ PIPELINE ERFOLGREICH ABGESCHLOSSEN ({elapsed}s)")

    if DB_FILE.exists():
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)

        total = db.get("total_analyzed", 0)
        long_cnt = db.get("long_count", 0)
        short_cnt = db.get("short_count", 0)
        neutral_cnt = db.get("neutral_count", 0)

        print(f"Gescannte Assets : {total}")
        print(f"LONG-Setups      : {long_cnt}")
        print(f"SHORT-Setups     : {short_cnt}")
        print(f"NEUTRAL (Wait)   : {neutral_cnt}")
        print("-" * 65)
        print("TOP 5 HIGH-CONVICTION SETUPS:")
        top_assets = [a for a in db.get("assets", []) if a.get("signal") != "NEUTRAL"][:5]
        for idx, a in enumerate(top_assets, 1):
            sym = a["symbol"]
            sig = a["signal"]
            score = a["score"]
            crv = a["crv"]
            entry = a["entry_range"][0]
            sl = a["stop_loss"]
            tp2 = a["take_profit_2"]
            print(f"  {idx}. [{sig} | {score}%] {a['name']} ({sym})")
            print(f"     Setup: {a['setup_name']} | CRV: {crv}:1")
            print(f"     Entry: {entry:,.2f} | SL: {sl:,.2f} | TP2: {tp2:,.2f}")
        print("=" * 65)
        print(f"Dashboard verfügbar unter: file://{DASHBOARD_HTML.resolve()}\n")

        # iOS Alerts versenden
        try:
            from notifications import send_scan_summary_notification
            send_scan_summary_notification(db)
        except Exception as e:
            print(f"Benachrichtigungs-Fehler: {e}")


def git_sync_dashboard():
    stage_banner("STUFE 6: Git-Hosting Synchronisation")
    import subprocess
    try:
        res = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=str(BASE_DIR), capture_output=True, text=True)
        if res.returncode != 0:
            print("Kein Git-Repository gefunden.")
            return

        subprocess.run(["git", "add", "dashboard/", "knowledge_base/live_watchlists.json"], cwd=str(BASE_DIR), check=True)

        diff_res = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(BASE_DIR))
        if diff_res.returncode == 0:
            print("Keine neuen Dashboard-Änderungen zum Committen.")
        else:
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            commit_msg = f"chore(dashboard): auto-update scan results ({now_str})"
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=str(BASE_DIR), check=True)
            print(f"✅ Dashboard erfolgreich committet: {commit_msg}")

        remote_res = subprocess.run(["git", "remote", "get-url", "origin"], cwd=str(BASE_DIR), capture_output=True, text=True)
        if remote_res.returncode == 0 and remote_res.stdout.strip():
            origin_url = remote_res.stdout.strip()
            print(f"Pushe Dashboard-Update zu Git-Hosting ({origin_url})...")
            push_res = subprocess.run(["git", "push", "origin", "main"], cwd=str(BASE_DIR), capture_output=True, text=True)
            if push_res.returncode == 0:
                print("✅ Git Push erfolgreich abgeschlossen! Dashboard-Hosting ist aktuell.")
            else:
                print(f"⚠️ Git Push Warnung: {push_res.stderr.strip()}")
        else:
            print("ℹ️ Lokales Dashboard committet. Kein Git-Remote 'origin' konfiguriert.")
            print("   Tipp: Sobald du 'git remote add origin <url>' ausführst, wird automatisch gepusht.")
    except Exception as e:
        print(f"Git-Sync Fehler: {e}")


def main():
    parser = argparse.ArgumentParser(description="TradingView Super-Analyst Master Update Pipeline")
    parser.add_argument("--skip-download", action="store_true", help="Überspringt den MCP-Download und nutzt vorhandene gecachte Bars")
    parser.add_argument("--force-download", action="store_true", help="Erzwingt vollständigen Neuabruf aller OHLCV-Bars")
    parser.add_argument("--git-push", action="store_true", help="Committet und pusht Dashboard-Änderungen automatisch in das Git-Hosting")
    args = parser.parse_args()

    run_pipeline(force_download=args.force_download, skip_download=args.skip_download, git_push=args.git_push)


if __name__ == "__main__":
    main()
