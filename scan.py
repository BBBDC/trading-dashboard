#!/usr/bin/env python3
"""
TradingView Automated Scanner CLI
Startet den Scan für ein Einzelsymbol oder eine Watchlist.

Beispiele:
  python3 scan.py --symbol COINBASE:BTCUSD --timeframe 1D
  python3 scan.py --symbol COINBASE:ETHUSD --timeframe 4h
  python3 scan.py --limit 3
  python3 scan.py --all
"""

import sys
import argparse
from trading_scanner.config import DEFAULT_WATCHLIST
from trading_scanner.chart_capture import ChartCapture
from trading_scanner.reporter import ReportGenerator


def main():
    parser = argparse.ArgumentParser(description="TradingView Automated Scanner & Chart Analyzer")
    parser.add_argument("--symbol", type=str, help="Einzelsymbol zum Scannen (z.B. COINBASE:BTCUSD)")
    parser.add_argument("--timeframe", type=str, default="1D", help="Timeframe (z.B. 15m, 1h, 4h, 1D, 1W)")
    parser.add_argument("--limit", type=int, default=None, help="Begrenzung für Watchlist-Scan")
    parser.add_argument("--all", action="store_true", help="Ganze Watchlist scannen")
    parser.add_argument("--headed", action="store_true", help="Browser sichtbar öffnen")

    args = parser.parse_args()

    # Symbole festlegen
    if args.symbol:
        symbols_to_scan = [args.symbol]
    elif args.all:
        symbols_to_scan = DEFAULT_WATCHLIST
    elif args.limit:
        symbols_to_scan = DEFAULT_WATCHLIST[:args.limit]
    else:
        # Standard: Die Top-3 Krypto-Märkte
        symbols_to_scan = DEFAULT_WATCHLIST[:3]

    print("=" * 60)
    print("TradingView Scanner gestartet")
    print(f"Timeframe: {args.timeframe}")
    print(f"Symbole ({len(symbols_to_scan)}): {', '.join(symbols_to_scan)}")
    print(f"Modus: {'Sichtbar' if args.headed else 'Headless'}")
    print("=" * 60)

    reporter = ReportGenerator()
    results = []

    with ChartCapture(headless=not args.headed) as capture:
        for idx, sym in enumerate(symbols_to_scan, 1):
            print(f"\n[{idx}/{len(symbols_to_scan)}] Scanne {sym}...")
            try:
                data = capture.capture_chart(symbol=sym, timeframe=args.timeframe)
                results.append(data)
                
                # Einzelbericht erstellen
                rep_path = reporter.generate_single_report(data)
                print(f"-> Einzelbericht: {rep_path}")
                print(f"-> Screenshot: {data['screenshotPath']}")
            except Exception as e:
                print(f"Fehler beim Scannen von {sym}: {e}")

    # Zusammenfassungsbericht erstellen
    if results:
        summary_path = reporter.generate_summary(results)
        print("\n" + "=" * 60)
        print("Scan erfolgreich beendet!")
        print(f"Zusammenfassung: {summary_path}")
        print("=" * 60)


if __name__ == "__main__":
    main()
