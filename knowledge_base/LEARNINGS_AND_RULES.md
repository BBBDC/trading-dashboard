# Arbeitsanweisungen, Richtlinien & Learnings

Dieses Dokument dient als zentrale Wissensbasis für die Qualitätskontrolle, Fehleranalyse und kontinuierliche Verbesserung des Projekts.

---

## 1. Grundlegende Arbeitsprinzipien
1. **Präzision & Transparenz:** Vor Beginn von Implementierungen oder größeren Schritten unklare Anforderungen klären und Rückfragen stellen.
2. **Dokumentation first:** Jede wichtige Entscheidung, Architekturkomponente und jedes Setup wird in der `knowledge_base/` dokumentiert.
3. **Schrittweises Vorgehen:** Komplexe Abläufe in kleine, testbare Teilschritte unterteilen.
4. **Themenbasierte Struktur:** Wenn Themen zu umfangreich werden, Aufteilung in separate Chat-Threads vorschlagen.

---

## 2. Selbstreflexion & Fehler-Log (Learnings)

| Datum | Thema / Kontext | Fehler / Herausforderung | Ursache | Gelernte Regel / Gegenmaßnahme |
|---|---|---|---|---|
| 2026-10-12 | Projektstart | Initiales Setup & Scope-Definition | Unklare Schnittstellen zu TradingView | Erst Integrationspfade klären, bevor Code geschrieben wird. |
| 2026-10-12 | Paketinstallation | Pip install schlägt mit Errno 8 fehl | Standard-Sandbox hat keinen Internetzugriff | Für Paketinstallationen und externe Downloads gezielt `BypassSandbox: true` anfragen. |
| 2026-10-12 | TradingView-Setup | Automatische Login-Erkennung | TradingView öffnet Layouts teils in neuem Context | Browser-Profil persistent speichern (`./tradingview_profile`), Inspektion gezielt auf dem Chart-Layout ausführen. |
| 2026-10-12 | Chart-Analyse | Setup-Erkennung | Kombination aus SMC (FVG/OB), Wyckoff & RSI Divergenzen | Die Indikatoren greifen ineinander: Bestätigung immer über Confluence (z.B. OB + FVG + VSA Volume Spike + RSI Divergenz) prüfen. |
| 2026-10-12 | Chat-Organisation | Multi-Chat-Koordination | Wissensstand geht zwischen Chats verloren | Alle Chats lesen und schreiben synchron in `knowledge_base/` (insb. `ACTIVE_INDICATORS.md`, `STRATEGY_RESEARCH.md`). |
| 2026-10-12 | Scanner-Engine | Direkte Layout-Navigation | Timeframe & Symbole via URL | URL-Parameter `?symbol=EXCHANGE:SYM&interval=CODE` lädt das Layout `LJynlFJq` verlässlich mit allen Indikatoren & Zeichnungen. |
| 2026-10-12 | DOM-Parsing | Indikator-Werte auslesen | Klassen im TradingView-DOM variieren | Über `div[class*="legend-"], div[class*="sources-"]` lassen sich alle Indikatorwerte (RSI, VSA, Degen-Bänder, OHLC) robust abgreifen. |
| 2026-10-12 | TradingView MCP | Server & Auth-Anforderung | Server `https://mcp.tradingview.com/mcp` erfordert OAuth 2.1 | Konfiguration via `type: "http"`, `url` in `mcp_config.json` / `.vscode/mcp.json`. Authentifizierung muss einmalig über den Browser-OAuth-Flow freigegeben werden. |
| 2026-10-12 | TradingView MCP | Live-Verbindung erfolgreich | Alle 35 MCP-Tools aktiv | Datenabruf (`get_ohlcv`, `get_technicals_rating`, `list_watchlists`) liefert exakte Live-Daten direkt aus dem TV-Account. |
| 2026-10-12 | Performance | Browser-Freies Arbeiten | Playwright / Chromium nicht mehr nötig | Chromium-Cache (~557 MB) gelöscht, Playwright deinstalliert, Analysen laufen zu 100% screenshot-frei über MCP. |
| 2026-10-12 | Custom Indikatoren | MCP unterstützt nur Standard-Tools | Private Pine Scripts nicht nativ im MCP | Über `get_ohlcv` Kerzen laden und SMC-Logik (FVG, Order Blocks, RSI Divergenzen) direkt algorithmisch berechnen (100% screenshot-frei). |
| 2026-10-12 | Strategie-Design | RSI-Divergenzen isoliert fehleranfällig | Divergenzen im Niemandsland führen zu Whipsaws | RSI-Divergenzen ausschließlich als sekundärer Trigger verwenden, wenn HTF-Zone (OB, FVG, Golden Pocket) + Wyckoff-Volumen (Climax/Absorption) vorliegen. |
| 2026-10-17 | Watchlist-Sync | Statische vs. dynamische Listen | Bisherige Scans nutzten Snapshot | Scanner auf `mcp-watchlist-list-watchlists` umgestellt: Neu hinzugefügte Symbole werden automatisch analysiert, gelöschte Symbole werden aus der DB entfernt und verwaiste Charts bereinigt (`sync_watchlists.py`). |
| 2026-10-17 | Chart-Visualisierung | Schwere GUI/C-Abhängigkeiten auf Pi | Matplotlib/Playwright brauchen X11/C-Libs | Autarke, pure-Python SVG-Vektorengine (`chart_generator.py`) entwickelt: Rendert Candlesticks, degencoder-Bänder, FVGs, Golden Pocket, RSI-Divergenzen & VSA ohne jede externe Library (100% Pi-kompatibel). |
| 2026-10-17 | Chart-Genauigkeit | Synthetische Kerzen wichen von Realität ab | Zuvor wurden nur für BTC und MU echte Bars geladen; Bänder waren flache Linien | Alle 58 Assets werden nun über `fetch_real_ohlcv_cache.py` mit 100% echten TV-MCP-Bars versorgt. Chart-Engine v3 zeichnet dynamische EMA 233-Kurven, degencoder-Volatilitätsbänder, echte Wyckoff-Volumenbalken & RSI(14) mit echten Zeitstempeln. |
| 2026-10-17 | Dashboard-Interaktivität | Statische Charts vs. echtes TV-Feeling | User wünscht exakte Chart-Übereinstimmung | Dual-View im Modal: Tab 1 zeigt autarkes SMC-Vektorchart (für Raspberry Pi/Offline); Tab 2 bettet das offizielle interaktive TradingView-Live-Widget ein. |
| 2026-10-17 | Pi-Migration & Git | Umzug auf 24/7 Raspberry Pi | Sauberer Stand vor Übertragung nötig | Vor dem Transfer auf den Pi: `.gitignore` härten, dynamische Watchlist und visuelle Chart-Bilder fertigstellen, SSH-Verbindung für headless Antigravity-Workflow einrichten. |
| 2026-10-17 | Pi 24/7 Betrieb & Git-Hosting | Inbetriebnahme auf Raspberry Pi | Git & Cron mussten eingerichtet werden | Lokales Git-Repository auf Branch main initialisiert, 24/7 Cron-Job für 4h-Zyklen eingerichtet, GitHub Pages Deploy-Workflow (`deploy-pages.yml`) & `--git-push` für automatisiertes Dashboard-Hosting integriert. |

---

## 3. Best Practices für dieses Projekt
- **Primäre Schnittstelle ist TradingView MCP:** Sämtliche Chart-Analysen, Indikatorberechnungen und Datenerfassungen erfolgen primär zu 100% über den offiziellen TradingView MCP-Server (`mcp-tv-*`). Keine Browser-Automatisierung für Berechnungen oder Scans verwenden.
- **Datenqualität durch MCP:** Über MCP erhalten wir unverfälschte, ungerundete mathematische Rohdaten (`open`, `high`, `low`, `close`, `volume`) direkt aus dem TradingView-Datenfeed. Indikatoren (RSI 14, VSA Wyckoff Volume Bänder, Degencoder Trendkanäle, FVGs, Order Blocks und Fibonacci Swings) werden darauf mit voller Fließkommapräzision berechnet – frei von UI-Glitches, Pixelrauschen oder DOM-Rundungen.
- **Sicherheit & Credentials:** Keine Passwörter oder sensitiven API-Keys im Klartext committen oder loggen. Nutzung von `.env` bzw. MCP-Token.
- **Risikomanagement:** Analysen müssen immer ein klar definiertes Risikomanagement (Stop-Loss, Take-Profit, CRV) berücksichtigen, keine blinden Signale.

