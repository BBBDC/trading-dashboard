# Projekt-Roadmap & Chat-Organisation

## 1. Projektziel
Aufbau eines intelligenten Trading-Assistenten, der an TradingView angebunden wird, Charts anhand bestehender (und neuer) Indikatoren analysiert und strukturierte Entscheidungshilfen liefert.

---

## 2. Phasenplan

### Phase 1: Setup & Anbindung (Erledigt ✅)
- [x] TradingView MCP-Server via OAuth 2.1 erfolgreich angebunden.
- [x] 35 native TradingView MCP-Tools aktiv (Watchlists, OHLCV, Technicals, Screener).
- [x] Chromium und Browser-Cache vollständig deinstalliert (100% screenshot-frei).
- [x] Live-Testabruf von Watchlists, Bars und Indikatoren erfolgreich verifiziert.

### Phase 2: Indikatoren- & Strategie-Katalog (In Arbeit in Chat 2 🔄)
- [x] Dokumentation deiner bestehenden Indikatoren in `ACTIVE_INDICATORS.md`.
- [x] Mathematische SMC-Erkennung (FVGs, Order Blocks, RSI-Divergenzen) in `smc_analyzer.py`.
- [ ] Confluence-Scoring & Einstiegsregeln mit Chat 2 finalisieren.

### Phase 3: Analyse-Engine & Scanner (Erledigt ✅ / MCP Native)
- [x] Direkte Watchlist- und Symbolabfrage via TradingView MCP.
- [x] Live-OHLCV- und Technicals-Ratings per Knopfdruck.
- [x] Strukturierte Marktberichte ohne Browser-Overhead.

### Phase 4: Reporting & Automatisierung (Nächster Schritt)
- [ ] Erweiterung auf Multi-Timeframe-Scanning (z.B. 1D Trend + 4h Entry).
- [ ] Regelmäßige automatische Scan-Läufe oder Benachrichtigungen.

---

## 3. Empfohlene Chat-Thread-Aufteilung
Sobald das Fundament steht, können wir separate Chats nutzen:
1. **Chat 1 (Hauptchat / Infrastruktur):** Verbindung mit TradingView, Tools, Server & Datenanbindung.
2. **Chat 2 (Strategie & Indikatoren):** Feinschliff deiner Pine-Scripts, Indikator-Kombinationen & Setup-Regeln.
3. **Chat 3 (Live-Analyse & Daily Review):** Täglicher Einsatz für Marktanalysen und Auswertungen.
