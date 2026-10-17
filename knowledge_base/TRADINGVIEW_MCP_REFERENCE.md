# TradingView MCP Server Dokumentation & Referenz

Dokumentation basierend auf der offiziellen TradingView MCP Dokumentation (`https://www.tradingview.com/mcp/docs`).

---

## 1. Server-Konfiguration
- **Server URL:** `https://mcp.tradingview.com/mcp`
- **Transport-Typ:** `http` / `Streamable HTTP`
- **Authentifizierung:** OAuth 2.1 (Login mit deinem bezahlten TradingView-Account, keine API-Keys nötig)
- **Voraussetzung:** TradingView Essential, Plus oder Premium (du hast Premium ✅)

### Konfigurationsdateien in unserem Workspace:
1. `.vscode/mcp.json` (für VS Code / Antigravity IDE)
2. `mcp_config.json` (im Projektordner)
3. `.agents/mcp_config.json` (für Antigravity Agent Framework)
4. `~/.gemini/config/mcp_config.json` (global für alle Antigravity-Sessions)

---

## 2. Verfügbare MCP-Tools

### Watchlists
- `list_watchlists`: Listet alle Watchlists deines Accounts auf.
- `get_active_watchlist`: Ruft deine aktuell aktive Watchlist mit allen Symbolen ab.
- `get_watchlist(watchlist_id)`: Ruft eine spezifische Watchlist ab.
- `create_watchlist`, `add_to_watchlist`, `remove_from_watchlist`: Watchlist-Verwaltung.

### Marktdaten (OHLCV)
- `get_ohlcv(symbol, interval, count)`: Liefert historische Kerzen (Open, High, Low, Close, Volume) bis zu 5000 Bars.
  - Zeiteinheiten: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1D`, `1W`, `M`.

### Technische Indikatoren & Screener
- `get_technicals_rating(symbol, interval)`: Liefert sofortige Momentaufnahmen für RSI, MACD, Stochastik, ADX, EMAs/SMAs (10-200), VWMA etc.
- `get_symbol_data(symbol, columns)` / `get_symbol_data_batch`: Screener-Kennzahlen.
- `run_screener`: Marktscreener mit Filtern.

### Alerts & News
- `list_alerts`, `create_alert`: Alerts in TradingView verwalten.
- `get_news`, `get_forecasts`, `get_financials`: Fundamentaldaten und Nachrichten.

---

## 3. Strategie für Custom Indikatoren (SMC & FVGs)
Da der MCP-Server Kerzendaten (`get_ohlcv`) und Standardindikatoren (`get_technicals_rating`) nativ liefert, berechnen wir die Smart Money Concepts (FVGs, Order Blocks und RSI-Divergenzen) direkt algorithmisch in Python auf den echten TradingView-Kerzen.
- **Vorteil:** Kein Browser, keine Screenshots, extrem schnell, exakte mathematische Werte.
