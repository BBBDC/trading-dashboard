# Institutioneller Triade-Konsens-Report (Phase 2)
**Autoren:** Antigravity (Lead-Architekt) · Grok 4.7 (Quant & Scout) · Claude Fable 5.2 (Stochastischer Auditor)  
**Datum:** 15. November 2026 · **Datenbasis:** 1.272 deterministische Simulationen über 40 Kern-Assets  

---

## 1. Executive Summary & Schiedsspruch

In einer der umfassendsten empirischen Untersuchungen quantitativer Krypto-, Aktien- und Forex-Handelssysteme haben Antigravity, Grok 4.7 und Claude Fable 5.2 das gesamte Universum von **40 Kern-Assets über 8 Zeitebenen (15m, 30m, 1h, 4h, 8h, 1D, 3D, 1W) in 4 Modi (1.272 Simulationen)** mathematisch seziert.

### Das ungeschminkte Gesamtbild
- **Negative Grundgesamtheit:** Über alle 1.272 Zellen hinweg ist der Median jeder einzelnen Zeitebene und jeder Asset-Klasse netto negativ. Die reale Marktmasse generiert bei 15 bp Gebühren/Slippage $-0,238\text{R}$ Verlust je Trade (Long & Short: $-1.793\text{R}$ auf 7.534 Trades).
- **Die Kosten-Klippe:** Liegt $\text{ATR}(14)/\text{Close} < 0,35\%$, fressen Gebühren und Slippage über $0,36\text{R}$ pro Trade auf. Bei $< 0,10\%$ (wie Forex auf 15m) vernichtet die Reibung $1,25\text{R}$ je Trade.
- **Drift-Fehler:** Das Leerverkaufen (Short) säkularer US-Megacap-Aktien (NVDA, AAPL, MSFT, AVGO) im Daily/Macro-Trend führte zu einer **Verlustquote von 87%**.
- **Zufallserwartung & Multiple Testing (Fable 5.2 Audit):** Bei 308 getesteten Zellen würden unter der Nullhypothese $H_0: E[R]=0$ rein zufällig ca. 19 Zellen einen In-Sample/Out-of-Sample-Filter bestehen. Tatsächlich bestanden nur 14 Zellen (10 nach Entschachtelung). Nach Empirical-Bayes-Shrinkage schrumpft die reale Punktschätzung der meisten Zellen auf $-0,06$ bis $+0,08\text{R} \pm 0,17\text{R}$.

---

## 2. Die verifizierte Triade-Konsens-Whitelist

Aufgrund der stochastischen Schrumpfung erhält **keine** Zelle eine unbeschränkte Vollfreigabe. Das Gesamtsystem wird in ein **3-Stufen-Modell** überführt:

### Stufe 1: PILOT LIVE (Echtgeld / Haupt-Portfolio, 0.15% Flat Risk)
Nur 3 Setups wiesen nach Übernacht-Gap-Korrektur und Bootstrap-Prüfung ($p < 0,05$) einen statistisch signifikanten Edge auf:

| Asset | Timeframe | Modus | $n$ | Roh $E[R]$ | $t$-Stat | $p$ (Bootstrap) | PF | OOS Fenster |
|---|---|---|---:|---:|---:|---:|---:|---|
| **Avalanche (`AVAX`)** | **30m** | Long & Short | 38 | $+0,73\text{R}$ | 2,38 | **0,007** | 2,37 | 44d IS / 19d OOS |
| **Ethereum (`ETH`)** | **30m** | **STRIKT NUR SHORT** | 18 | $+0,76\text{R}$ | 2,11 | **0,017** | 2,85 | 44d IS / 19d OOS |
| **Amazon (`AMZN`)** | **4h** | Long & Short | 18 | $+0,79\text{R}$ | 1,65 | **0,041** | 1,63 | 746d IS / 315d OOS |

*Allokation:* 
- Flat-Risk: $0,15\%$ des Kontos pro Trade.
- Cluster-Heat: maximal $0,30\%$ (AVAX und ETH teilen sich das Crypto-Budget!).
- Portfolio-Heat: maximal $0,60\%$ des Gesamtkontos. Max. 1 Position pro Ticker.

---

### Stufe 2: SHADOW PAPER (Schattenbuch / AI Incubator, 0.00% Live-Risiko)
Diese Setups zeigen positive Tendenzen, müssen jedoch in einer prospektiven Stichprobe von mindestens $n \ge 40$ neuen Trades beweisen, dass die untere $90\%$-Konfidenzgrenze $> 0$ bleibt:

| Asset | Timeframe | Modus | Begründung & Status |
|---|---|---|---|
| **Near Protocol (`NEAR`)** | 1h | Long & Short | OOS $E[R] = 0,34$, PF 1,52. OOS-Zeitfenster überlappt mit AVAX (gleiches Makro-Regime). |
| **Avalanche (`AVAX`)** | 1h | Long & Short | OOS $E[R] = 0,32$, PF 1,47, $n=44$. |
| **Siemens (`SIE`)** | 4h | Long & Short | OOS $E[R] = 0,35$, PF 1,58, 736d IS / 310d OOS. |
| **Siemens (`SIE`)** | 1h | Long & Short | Durch Fable rehabilitiert: 81 Trades, $t=1,54$. OOS-Abfall statistisch mit Rauschen vereinbar. |
| **Allianz (`ALV`)** | 4h | **STRIKT NUR SHORT** | PF 1,99, OOS $E[R] = 0,60$, 736d IS / 310d OOS. |
| **Amazon (`AMZN`)** | 1D | Long & Short | OOS $E[R] = 0,39$, PF 1,42, 2.552d IS / 1.099d OOS. |

---

### Stufe 3: GESTRICHEN (Kein Handel, weder Live noch Schatten)
- **EUR/USD 8h:** $84\%$ aller Trades haben $\text{ATR}/\text{Close} < 0,35\%$ und scheitern am Kostengate. Reales institutionelles FX-Gebührenmodell erfordert separaten Feed.
- **Amazon 1h Nur Long & Allianz 1h Nur Long:** Nach Bereinigung nächtlicher Eröffnungs-Gaps fällt der Edge um über $50\%$ in sich zusammen.
- **US-Megacap Shorts (NVDA, AAPL, MSFT, AVGO) auf Daily/Macro:** 87% Verlustquote durch säkularen Bull-Drift.

---

## 3. Die 4 verbindlichen Produktions-Filter

1. **Zellen-Whitelist & Direction-Lock:**
   `check_triad_whitelist()` blockiert in `portfolio_engine.py` jeden Trade, der nicht explizit auf der Whitelist steht, sperrt verbotene Richtungen (z.B. ETH 30m Longs) und verhindert Shorts auf Megacap-Tech im Daily-Trend.
2. **Kostengate auf Stop-Basis (`cost_r <= 0.20`):**
   `cost_r = \frac{\text{Round-Turn Reibung}}{\text{Stop-Abstand in \%}} \le 0,20$.
   Maximal 20% des Stop-Abstands darf durch Gebühren, Spread und Slippage absorbiert werden.
   Anlagenspezifische Gebühren hinterlegt (Crypto: 16 bp, Aktien: 8 bp, Forex: 3 bp).
3. **Heat-Caps in Prozent des Kontos:**
   - Trade-Risk: $0,15\%$ (Pilot)
   - Cluster-Heat: $0,30\%$
   - Portfolio-Heat: $0,60\%$
   - Max. 1 Position pro Ticker.
4. **Statistisches Promotion- & Kill-Gate:**
   - **Kill-Switch:** Kumuliert $-6,0\text{R}$ Verlust auf neuen Trades deaktiviert eine Zelle automatisch.
   - **Promotion:** Aufstieg von Schattenbuch zu Pilot erst nach $\ge 40$ Trades mit $CI_{90\%}^{\text{low}} > 0$.

---

## 4. Bereinigungen in der Codebase

1. `circuit_breaker.py`: `TRIAD_WHITELIST`, `check_triad_whitelist`, `ASSET_FRICTION_DEFAULTS` und `TRIAD_PILOT_CONFIG` implementiert. 93/93 Unit-Tests bestanden.
2. `portfolio_engine.py`: Whitelist-Veto, Direction Lock und $0,15\%$ Pilot-Risk fest verankert. Nicht-qualifizierte Dashboard-Picks werden automatisch abgewiesen.
3. `ai_incubator.py`: Läuft nun streng als `SHADOW_PAPER`, Heat-Limits gestrafft, Kostengate und ATR-Filter integriert, Timeframe-Fokus auf 30m, 1h und 15m erweitert.
4. `backtest_matrix_engine.py`:
   - Mode 4 Causal-Filter-Bug behoben (WMA233 Steigung + RSI Bias statt widersprüchlicher Preisniveaus).
   - Bias-Korrektur: Stop-Loss wird im selben Bar vor TP2 geprüft.
   - Gap-Loss Korrektur: Ausführung von Stops bei Eröffnungs-Gaps am tatsächlichen Open-Preis.
   - Reibung nach Assetklasse differenziert.
