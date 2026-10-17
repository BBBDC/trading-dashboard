"""
Konfiguration für den TradingView Scanner & Analyzer
"""

from pathlib import Path

# Basis-Verzeichnisse
BASE_DIR = Path(__file__).resolve().parent.parent
PROFILE_DIR = BASE_DIR / "tradingview_profile"
REPORTS_DIR = BASE_DIR / "reports"
SCREENSHOTS_DIR = REPORTS_DIR / "screenshots"
KB_DIR = BASE_DIR / "knowledge_base"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# TradingView Layout
LAYOUT_ID = "LJynlFJq"
BASE_CHART_URL = f"https://www.tradingview.com/chart/{LAYOUT_ID}/"

# Timeframe Mappings (TradingView URL-Parameter)
TIMEFRAME_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "2h": "120",
    "4h": "240",
    "8h": "480",
    "12h": "720",
    "1D": "D",
    "1W": "W",
    "1M": "M"
}

# Standard-Watchlist aus deinem Account
DEFAULT_WATCHLIST = [
    "COINBASE:BTCUSD",
    "COINBASE:ETHUSD",
    "COINBASE:SOLUSD",
    "BINANCE:AVAXUSDT",
    "COINBASE:AAVEUSD",
    "BINANCE:GMXUSDT",
    "CRYPTOCAP:BTC.D",
    "CRYPTOCAP:TOTAL",
    "COINBASE:ETHBTC"
]
