# TradingView Super-Analyst & Multi-Timeframe Dashboard

Ein autonomes, hochpräzises Analyse- und Dashboard-System für Krypto, Aktien, Edelmetalle und Rohstoffe. Entwickelt für 24/7-Betrieb auf einem **Raspberry Pi (ARM64)** und Desktop-Umgebungen.

---

## 🌟 Kern-Features

1. **Offizieller TradingView MCP-Datafeed:**
   * Mathematisch unverfälschte, ungerundete Fließkomma-Rohdaten (`open`, `high`, `low`, `close`, `volume`, `timestamp`) direkt über die offizielle TradingView-MCP-Schnittstelle.
   * Keine fehleranfällige Browser-Automatisierung für Berechnungen nötig.
2. **Dynamische Watchlist-Synchronisation (`sync_watchlists.py`):**
   * Erkennt neu hinzugefügte Symbole aus deinen TradingView-Listen (`Aktien`, `Crypto`, `Commodities`, etc.) vollautomatisch.
   * Entfernt gelöschte Symbole sauber aus der Datenbank und bereinigt verwaiste Chartdateien.
3. **Multi-Timeframe Confluence Engine:**
   * Analysiert jedes Asset synchron auf **4h**, **8h** und **1D** mit deinem Indikatoren-Setup:
     * `degencoder indicator` (Parameter: `13, 1.8, 233`): Dynamische Trendkanäle & EMA 233 Baseline.
     * `degencoder's FVGs`: Fair Value Gaps mit 50 % Consequent Encroachment (CE).
     * `degencoder's OB Retro`: Institutionelle Order Blocks / Smart Money Zonen.
     * `RSI divergence` (14): Früherkennung regulärer und versteckter Divergenzen.
     * `VSA Wyckoff Volume`: Farbkodierung für Climax-, Stopping-, High- und No-Supply-Volumen.
     * `Fibonacci Golden Pocket`: Golden Pocket (`0.618 – 0.65`) für maximale Umkehr-Präzision.
4. **Autarke Vektor-Chart-Engine v3 (`chart_generator.py`):**
   * 100 % Pure Python (kein Matplotlib, kein Playwright, keine X11/C-Bibliotheken).
   * Rendert für alle Zeiteinheiten gestochen scharfe Dark-Theme SVGs mit echten Kerzen, dynamischen Volatilitätsbändern, echten Wyckoff-Volumenbalken, RSI-Panels und Zeitstempeln.
5. **Interaktives HTML-Dashboard (`dashboard/index.html`):**
   * Super-Navigation mit Signal-Filtern (LONG, SHORT, NEUTRAL), Asset-Klassen und Suchfunktion.
   * Detail-Modal mit **Dual-View**:
     * **Tab 1:** SMC & Indikatoren Vektor-Chart (Offline / Raspberry Pi).
     * **Tab 2:** Interaktives **TradingView Live-Chart-Widget** mit voller Chart-Bedienung.
   * Trade-Plan-Box (Entry-Zone, Stop-Loss, TP1, TP2, CRV).

---

## 🚀 Schnelleinstieg & Bedienung

### 1. Das gesamte System mit einem Befehl aktualisieren:
```bash
python3 update_dashboard.py
```
*Dieser Befehl synchronisiert deine Watchlists, lädt die neuesten Marktdaten, berechnet alle Signale, rendert 174+ SVG-Charts und baut das Dashboard neu.*

### 2. Schnelldurchlauf (gecachte Daten nutzen):
```bash
python3 update_dashboard.py --skip-download
```

### 3. Dashboard im Browser ansehen:
Öffne einfach die Datei `dashboard/index.html` in deinem Browser (z.B. Safari, Chrome, Firefox) oder starte einen lokalen Webserver:
```bash
python3 -m http.server 8080 --directory dashboard
```
Anschließend im Browser aufrufen: `http://localhost:8080` (bzw. `http://<RASPBERRY_PI_IP>:8080`).

---

## 📁 Projekt-Struktur

```text
Trading/
├── update_dashboard.py         # Master-Runner (führt die gesamte Pipeline aus)
├── sync_watchlists.py          # Synchronisiert Symbole & bereinigt gelöschte Werte
├── fetch_real_ohlcv_cache.py   # MCP-Datafeed & automatischer Token-Refresh
├── chart_generator.py          # Autarke SVG-Vektor-Chart-Engine (v3)
├── generate_all_charts.py      # Generiert alle 174 Charts (4h, 8h, 1D)
├── build_dashboard.py          # Kompiliert das moderne HTML-Dashboard
├── batch_analyzer.py           # Multi-Timeframe Confluence- & Scoring-Engine
├── requirements.txt            # Python-Abhängigkeiten (Standard-Library)
├── .gitignore                  # Schützt Tokens, Credentials & Caches
├── dashboard/
│   ├── index.html              # Das interaktive Dashboard (Web-App)
│   ├── market_analysis_db.json # Zentrale Master-Datenbank aller 58 Assets
│   └── charts/                 # Alle generierten SVG-Vektorgrafiken
└── knowledge_base/
    ├── LEARNINGS_AND_RULES.md  # Architektur-Entscheidungen & Fehler-Log
    ├── STRATEGY_RESEARCH.md    # Hypothesen, Setup-Regeln & Case Studies
    ├── ACTIVE_INDICATORS.md    # Spezifikation aller TradingView-Indikatoren
    ├── PI_MIGRATION_AND_AGENT_HANDOFF.md # Anleitung für den Raspberry Pi Agenten
    └── live_watchlists.json    # Snapshot der TradingView-Watchlists
```

---

## 🛡️ Sicherheitshinweis
Die Datei `.mcp_tokens.json` enthält deine OAuth-Zugangsdaten für TradingView und wird durch die `.gitignore` strikt vor Git-Commits geschützt. Committe niemals Token-Dateien in öffentliche Repositories!
