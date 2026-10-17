# Strategie-Forschung, Hypothesen & Setup-Logik

Dokumentation zur iterativen Erprobung und Optimierung der Trading-Setups.

---

## 1. Verfügbare Indikatoren-Bausteine

| Baustein | Name | Parameter | Primäre Rolle |
|---|---|---|---|
| **Trend / Dynamic Bands** | `degencoder indicator` | `13, 1.8, 233` | Übergeordneter Trend, dynamische Support/Resistance-Bänder, Basis-Signale (BUY/SELL) |
| **Imbalances / Liquidity** | `degencoder's FVGs` | Auto | Fair Value Gaps (ungedeckte Liquidität, Magnetzonen) |
| **Institutionelle Zonen** | `degencoder's OB Retro` | Retro | Order Blocks (SMC: Akkumulations-/Distributionsursprung) |
| **Momentum Trigger** | `RSI divergence` | `14, close` | Früherkennung von Trendwenden ("Bull" / "Bear" Divergenzen) |
| **Volumen / Bestätigung** | `VSA Wyckoff Volume` | `20, 2.2, 1.8, 1.2, 0.8, 0.4` | Volume Spread Analysis: Stopping Volume, Climax, Churn, Low-Volume Pullbacks |
| **Struktur & Levels** | Fibonacci & Wellen | GP (0.618-0.65), 0.786, etc. | Geometrische Retracements und Kursziel-Projektionen |

---

## 2. Zu testende Setup-Hypothesen (Forschungsansätze)

### Hypothese 1: "SMC Golden Confluence Reversal" (Major Swing Turn / Anti-Trend)
*Ziel: Extrem hohes CRV an institutionellen Wendepunkten durch Zusammentreffen mehrerer Schlüssel-Ebenen.*
- **Kontext / HTF-Zone:**
  - Kurs läuft in einen unmitigierten Order Block (`degencoder's OB Retro`).
  - Überschneidung mit dem Fibonacci Golden Pocket (`0.618 – 0.65`) oder extremen Retracement (`0.786 / 0.887`).
  - Ein offenes Fair Value Gap (`degencoder's FVGs`) in der Zone wird gefüllt (Mitigation).
- **Trigger:**
  - **RSI-Divergenz (14, close):** Reguläre bullische/bärische Divergenz (Preis formt neues Extremum, RSI zeigt Schwäche/Gegentrend).
  - **VSA Wyckoff Volume:** Climax- oder Ultra-High Volume Spike (Multiplikator $\ge 1.8$ oder $2.2$) beim Anlaufen der Zone, gefolgt von Stopping Volume / Absorption (Docht-Bildung, geringeres Gegenvolumen).
- **Ausführung & Risikomanagement:**
  - **Entry:** Bestätigter Schlusskurs der Reversal-Kerze (z.B. Hammer/Pinbar) oder Retest des FVG nach Bruch des lokalen Mikro-Swings (Market Structure Shift auf LTF).
  - **Stop-Loss:** 0.2–0.3% ATR-Puffer hinter dem extremen Docht des Order Blocks / Sweeps.
  - **Take-Profit:**
    - TP1 (50%): Nächstes signifikantes Swing-Level / gegenüberliegendes FVG $\rightarrow$ SL auf Break-Even.
    - TP2 (30%): Gegenüberliegendes Band des `degencoder indicator` (dynamischer Kanal).
    - TP3 (20% Runner): Trailing Stop bis zum Bruch der Marktstruktur oder Gegensignal.
  - **Erwartetes CRV:** $3.0:1$ bis $5.0:1$.

---

### Hypothese 2: "Trend Continuation & Hidden RSI Divergence" (Trendfolge / Hohe Trefferquote)
*Ziel: Hohe Winrate durch Einstiege in übergeordnete Trends bei gesunder Erschöpfung des Rücksetzers.*
- **Kontext / HTF-Zone:**
  - Übergeordneter Trend laut `degencoder indicator` intakt (z.B. Kurs über der 233-Baseline / bullische Kanalneigung).
  - Rücklauf (Pullback) in ein frisch entstandenes FVG (`degencoder's FVGs`) oder einen Retest der dynamischen Trendbänder.
- **Trigger:**
  - **Hidden RSI Divergence:** Kurs macht ein *Higher Low* (gesunde Korrektur), aber der RSI fällt tiefer (*Lower Low* = Momentum-Reset).
  - **VSA Wyckoff Volume:** "No Supply" / "Low-Volume Pullback" (Volumen während der Korrektur fällt unter den VSA-Schwellenwert $\le 0.8$ bzw. $0.4$, signalisiert Verkäufermangel).
- **Ausführung & Risikomanagement:**
  - **Entry:** Limit-Order bei 50% des FVGs (Consequent Encroachment) oder Market-Entry bei bullischer Bestätigungskerze am FVG/Band.
  - **Stop-Loss:** Knapp unter dem Tief des FVGs bzw. unter der dynamischen Support-Linie des `degencoder indicator`.
  - **Take-Profit:**
    - TP1 (60%): Retest des letzten Trend-Hochs (CRV ca. $1.5:1$ – $2.0:1$).
    - TP2 (40% Runner): Trailing Stop entlang der mittleren Trendlinie des `degencoder indicator`.
  - **Erwartetes CRV:** $2.0:1$ bis $3.5:1$ (Fokus auf Winrate $\ge 60\%$).

---

### Hypothese 3: "Wyckoff Liquidity Hunt & Range Fakeout" (Spring / Upthrust)
*Ziel: Ausnutzen von institutionellen Stop-Runs / Traps an Schlüsselmarken.*
- **Kontext / HTF-Zone:**
  - Deutliche Range-Struktur oder markantes lokales Swing-High / Swing-Low (Key Liquidity Pool).
  - Kurs überdehnt sich bis an die äußeren Volatilitätsbänder des `degencoder indicator`.
- **Trigger:**
  - **Liquidity Sweep (Fakeout):** Kurs sticht über das Hoch / unter das Tief, wird aber innerhalb von 1–2 Kerzen aggressiv abverkauft/hochgekauft ("Reclaim" des Levels).
  - **VSA Wyckoff Volume:** Gewaltiger Volume-Spike (*Climax / Ultra-High Volume*, Multiplikator $> 2.2$) beim Sweep-Docht, der sofort absorbiert wird.
  - **RSI-Divergenz:** Starke Divergenz bestätigt, dass der Ausbruch keine echte Momentum-Kraft hatte.
- **Ausführung & Risikomanagement:**
  - **Entry:** Sobald die Kerze wieder innerhalb des Range-Niveaus schließt (Bestätigung des False Breakout).
  - **Stop-Loss:** Knapp hinter dem Sweep-Docht.
  - **Take-Profit:**
    - TP1 (50%): Range-Mitte (Equilibrium / 0.5 Fib).
    - TP2 (50%): Gegenüberliegendes Range-Extremum / Order Block.
  - **Erwartetes CRV:** $3.5:1$ bis $6.0:1$.

---

## 3. Testprotokoll & Evaluierungsmetriken
- **Winrate:** % der Trades im Profit
- **Durchschnittliches CRV (Risk/Reward):** Ziel $\ge 2.5:1$
- **Profit Factor & Expectancy:** $(Gewinn-Summe / Verlust-Summe)$
- **Max Drawdown:** Maximaler Rückgang
- **Filter-Effizienz:** Wie viele Fehlsignale werden durch die Kombination (OB + FVG + VSA + RSI) gegenüber reinen Einzelindikator-Signalen eliminiert?

---

## 4. Live-Markt-Erprobung & Case Studies (17.10.2026)

### Case 1: Bitcoin (COINBASE:BTCUSD) – 4h / 8h / 1D
- **1D:** Makro-Trend bullisch (über EMA 233 bei 75.774 USD). Letzter dominant Swing 64.1k -> 87.4k USD. Wichtigster HTF-Support: Bullish FVG 77.105 – 80.822 USD (CE 50%: 78.963 USD konfluent mit 0.382 Fib 78.502 USD).
- **8h:** Reguläre bullische RSI-Divergenz aktiv (Tief 82.7k -> 80.6k USD vs RSI 40.4 -> 42.9). VSA zeigt "No Supply" (Ratio 0.12).
- **4h:** Versteckte bullische Divergenz (Higher Low bei 81.271 vs 79.676 USD bei tieferem RSI). Unmittelbarer Widerstand: 4h Bearish OB 81.732 – 82.322 USD.
- **Strategie-Zuordnung:** Entspricht **Hypothese 2 ("Trend Continuation & Hidden RSI Divergence")**. Ein Durchbruch über 82.322 USD öffnet das Ziel zum Golden Pocket / Bearish FVG bei 84.350 – 84.850 USD.

### Case 2: Micron Technology (NASDAQ:MU) – 4h / 8h / 1D
- **1D:** Reines **Hypothese 1 Setup ("SMC Golden Confluence Reversal")**:
  - Kurs bei **878,84 USD** trifft exakt das **Fibonacci Golden Pocket 0.618 (867,67 – 879,54 USD)** des Swings 737 -> 1.108 USD.
  - Kurs überdehnt das untere `degencoder`-Band (895,09 USD) nach unten (Oversold Band).
- **8h / 4h:** **RSI tief überverkauft (26.64)** mit **aktiver bullischer Divergenz** (Preis bildete neues Tief bei 858 USD, RSI stieg von 32.2 auf 33.5).
- **VSA Wyckoff Volume:** Verkaufsdruck trocknet aus (Ratio 0.76, Low Volume).
- **Rebound-Ziele:** Bearish FVG bei 899,37 – 903,41 USD (TP1) und 949,42 – 978,50 USD (TP2).

---

## 5. Full Market Watchlist Scan (55 Assets) – 17.10.2026

- **Gesamtergebnis:** 55 einzigartige Assets über TradingView MCP gescannt (4h, 8h, 1D).
  - **14 High-Conviction Long Setups:**
    1. **NASDAQ:MU (98% Score):** 1D Golden Pocket Confluence + RSI 26.6 Bull Div.
    2. **NASDAQ:HOOD (96% Score):** Golden Pocket Confluence + oversold bounce.
    3. **COINBASE:BTCUSD (94% Score):** No Supply + 8h Bull Div + Breakout Watch > 82.3k.
    4. **BINANCE:AVAXUSDT (96% Score):** SMC Oversold Reversal.
    5. **COINBASE:AAVEUSD (96% Score):** Trend Continuation & Hidden Div.
    6. **BINANCE:DOTUSDT (96% Score):** Trend Continuation & Hidden Div.
    7. **BINANCE:GMXUSDT (96% Score):** Trend Continuation & Hidden Div.
    8. **NASDAQ:AMD (96% Score):** Oversold Band Bounce.
    9. **NASDAQ:INTC (95% Score):** Oversold Band Bounce.
    10. **NASDAQ:MRVL (96% Score):** Trend Continuation.
    11. **NASDAQ:PLTR (96% Score):** Trend Continuation & Hidden Div.
    12. **NASDAQ:CRWD (96% Score):** Trend Continuation & Hidden Div.
    13. **NYMEX:NG1! (96% Score):** Erdgas Trendfortsetzung.
    14. **XETR:DAX (96% Score):** DAX 40 Reversal Bounce.
  - **20 High-Conviction Short / Erschöpfungs-Setups:**
    - Edelmetalle & Rohstoffe überdehnt: Gold (TVC:GOLD), Silber (TVC:SILVER), Palladium, Kupfer.
    - Konsum / Overextended Tops: Adidas (XETR:ADS), Accenture (NYSE:ACN), Tesla (NASDAQ:TSLA), Amazon (NASDAQ:AMZN), Alphabet (NASDAQ:GOOG), Oracle, IBM.
  - **21 Neutral / Konsolidierung:** Warten auf Trigger (ETH, SOL, NVDA, AAPL, MSFT, META).
- **Dashboard & Datenbank:**
  - JSON-Datenbank: `dashboard/market_analysis_db.json`
  - HTML-Dashboard: `dashboard/index.html` (und Artifact `dashboard.html`)

---

## 6. Dynamic Watchlist Sync & Visual Chart Integration (v2 Update)

### Watchlist-Synchronisations-Architektur (`sync_watchlists.py`)
- **Automatisches Delta-Management:**
  - Fragt Live-Watchlists (`Aktien`, `Crypto`, `Commodities`, `Devisen`, `Rohstoffe`, `Watchlist`) über den TradingView MCP-Server ab.
  - **Gelöschte Assets:** Werden sofort aus `market_analysis_db.json` entfernt; verwaiste SVG-Charts in `dashboard/charts/` werden automatisch gelöscht.
  - **Neue Assets:** Werden sofort dedupliziert, kategorisiert, mit Initialwerten & 4h/8h/1D-Indikatoren berechnet und im nächsten Scanzyklus voll integriert.
  - Aktueller Stand: **58 einzigartige Assets**, 174 generierte SVG-Charts.

### Autarke Vektor-Chart-Engine (`chart_generator.py`)
- **Pure-Python SVG-Generierung (ohne externe C/GUI-Bibliotheken, optimiert für Raspberry Pi ARM64):**
  - **Candlestick Price Action:** Dochte, Kerzenkörper in Dark-Theme (`#090d16`).
  - **degencoder Bänder & Trend:** Dynamische Volatilitätsbänder und EMA 233 Baseline.
  - **Fair Value Gaps (FVGs):** Transparente Shading-Boxen (Emerald = Bullish, Rose = Bearish) mit gestrichelter 50% Consequent Encroachment-Linie.
  - **Fibonacci Golden Pocket:** Golden schattierte Box mit Strichlinie für 0.618 – 0.65.
  - **Wyckoff VSA Volumen:** 4-Farben-Balken (Ultra-High / High / Normal / Low).
  - **RSI 14 Momentum:** Überverkauft-/Überkauft-Zonen (30/70) und eingezeichnete "Bull Div" / "Bear Div" Pfeilmarker.
- **Interaktive Dashboard-Integration:**
  - Klick auf ein beliebiges Asset öffnet das Detail-Modal mit direktem 4h / 8h / 1D-Chart-Umschalter, Vollbild-Ansicht und synoptischer Indikatoren-Matrix.



