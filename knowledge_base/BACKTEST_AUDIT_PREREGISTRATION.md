# Pre-Registration v1.2: Unabhängiges Backtest-Audit (Strategie 1 & Strategie 2)

**Status:** Pre-Registration v1.2 (final bereinigt nach Opus-Checkpoint-1b; per Git-Commit eingefroren vor erstem Code/Run)  
**Datum:** 2026-11-25  
**Zweck:** Prüfung zweier ökonomisch kausaler, parameterarmer `1D`-Basisstrategien unabhängig von der laufenden `degencoder`-Pipeline.

---

## 1. Gemeinsamer Audit-Rahmen, Datenhygiene & Konventionen

### 1.1 Einheitliche Rendite-, Währungs-, Cash- & Short-Konvention *(inkl. D1–D4, D7, D8, D12, P6)*
- **Vollständig handelbares USD-ETF-Universum:** Beide Strategien werden ausschließlich auf **US-gelisteten, real handelbaren ETFs in USD** gerechnet (kein Index-Mix, kein FX-Spot ohne Carry, kein Zeitzonen-Shift).
- **Total Return (`adjclose`):** Für alle ETFs werden `o, h, l, c` mit dem täglichen Faktor `adjclose / close` skaliert (Dividenden, Kupons, Carry und ETF-TER sind damit real abgebildet).
- **Cash, Hebel & Short-Finanzierung:**
  - Freies (nicht investiertes) Cash verzinst sich täglich mit dem **3M-US-T-Bill-Satz** (`^IRX` / FRED `DTB3`, `r_f / 252` pro Handelstag).
  - Brutto-Long-Engagement `> 100 %` Eigenkapital wird mit `3M-T-Bill + 50 bp` p.a. finanziert.
  - **Short-Seite (`P6`):** Short-Erlöse zählen **nicht** als freies Cash und verzinsen sich (inkl. Leihgebühr) mit **`3M-T-Bill − 50 bp`** p.a.
  - **Alle Sharpe Ratios** (Strategien und Benchmarks) werden einheitlich als **Excess-Return-Sharpe über 3M-T-Bill** berechnet.
- **Handelskalender & Datum:** Einheitlicher US-Börsenkalender (NYSE/NASDAQ/Arca), Zeitstempel strikt auf das lokale US-Handelsdatum normiert.

### 1.2 Zeitlicher 3-Stufen-Split, Vorlauf & Phasengrenzen *(inkl. D5, P9)*
| Phase | Zeitraum | Abgedeckte Marktregime | Rolle |
|---|---|---|---|
| **Vorlauf (Warmup)** | `2007-02-15` – `2008-02-29` | — | Mind. 250 Handelstage Vorlauf (`SMA200` / `Donchian50`), 0 Trades |
| **1. In-Sample (IS)** | `2008-03-01` – `2016-12-31` (~8,8 J.) | Finanzkrise 2008, Eurokrise 2011, Rohstoff-Crash 2014–16 | Technische Plausibilität & Basis-Edge |
| **2. Validation (Val)** | `2017-01-01` – `2021-12-31` (5,0 J.) | Volmageddon 2018, COVID-Crash 2020, Boom 2021 | Regime-Stabilität, Plateau- & Kosten-Check |
| **3. Versiegelter Holdout** | `2022-01-01` – `2026-11-20` (~4,9 J.) | Zinswende 2022, Seitwärts 2023, KI-Rally 2023–26 | **Exakt einmaliger Test nach Öffnungs-Gate.** |

- **Phasengrenzen (`P9`):** Indikatoren rechnen über Phasengrenzen kontinuierlich weiter. Trades werden nach ihrem **Einstiegsdatum** zugeordnet; am Ende jeder Phase (`IS`, `Val`, `Holdout`) werden noch offene Positionen für die Phasenstatistik zum `Close` des letzten Phasentages Mark-to-Market als geschlossen gewertet. Der **Holdout-Lauf startet flach** (ohne übernommene Positionen).
- **Deklaration der Wissensbelastung:** Der Zeitraum `2022–2026` wurde live erlebt, und die `degencoder`-Pipeline hat Teilmengen dieser Instrumente bereits gesehen. Mildernd wirkt, dass beide Strategien unverändert aus der Literatur vor 2022 stammen.

### 1.3 Datenqualitäts-Gate & Integrität *(inkl. D6, D9)*
- **Snapshot & Hash:** Vor dem ersten Lauf werden alle verwendeten Datendateien als Snapshot eingefroren und mit **SHA256-Hashes** dokumentiert.
- **Zweitquellen-Abgleich:** Stichproben-Abgleich der `adjclose`-Reihen gegen eine zweite Quelle (z. B. Stooq); Akzeptanz-Toleranz: **`|Δ Tagesrendite| < 5 bp` an `≥ 99 %` der Handelstage**.
- **Qualitäts-Gate je Instrument und Jahr:** Prüfung auf `Open == PrevClose`, `High == Low`, `High < max(O,C)`, `Low > min(O,C)` sowie Datenlücken `> 4` Handelstage. Überschreitet ein Fehleranteil `2,0 %` in einem Jahr, wird das Instrument/Jahr für `IBS`/`Open(t+1)`-Tests **und** für die zugehörigen Benchmarks in diesem Jahr gesperrt.

### 1.4 Kausalität, Ereignisreihenfolge & Kosten *(inkl. L5, L8, D10, P5)*
- **Exakte Ereignisreihenfolge je Bar `t+1`:**
  1. Ausstehende Orders vom `Close(t)` zum `Open(t+1)` füllen (bei Reversal Long→Short: Exit und Neueinstieg zum `Open(t+1)` mit doppelten Kosten).
  2. Intraday-Stop-Prüfung gegen `[Open(t+1), Low(t+1)]` (Long) bzw. `[Open(t+1), High(t+1)]` (Short); bei Eröffnungs-Gap jenseits des Stops zählt der schlechtere reale `Open(t+1)`-Preis.
  3. Indikatoren und neue Signale am `Close(t+1)` berechnen (Order-Ausführung erst am nächsten `Open`).
- **Round-Turn-Transaktionskosten (Gebühr + Spread + Slippage):**
  - US-ETFs: **10 bp** (0,10 % Round-Turn) | Krypto-Satellit (rein beschreibend): **30 bp**
  - **Pflicht-Stresstest bei `2×` Kosten (`20 bp`, `P5`):** Sowohl Strategie 1 als auch Strategie 2 müssen im Gesamtzeitraum **`Excess-Sharpe > 0`**, **`PF > 1,0`** und **`Expectancy > 0`** erreichen.

### 1.5 Exakte Indikator-Formeln *(inkl. L1, L6)*
- **Donchian-Kanal (geschlossenes Intervall `[t−n, t−1]`):** `close.shift(1).rolling(n).max()` / `.min()` (exakt `n` Werte inkl. `t-1`).
- **SMA(200):** `close.rolling(200).mean()` inklusive `Close(t)`.
- **RSI(2):** Wilder-Glättung (RMA, `alpha = 1/2`), initialisiert über das arithmetische Mittel von `max(Δ, 0)` bzw. `max(-Δ, 0)` über die ersten `2` Preisänderungen.
- **ATR(14) & ATR(20):** Wilder-Glättung (RMA, `alpha = 1/N`) der True Range, initialisiert über das arithmetische Mittel der ersten `N` True-Range-Werte.
- **Referenz-Check:** Einheitstest der Indikatorwerte an einem Stichtag gegen `TA-Lib`.

---

## 2. Strategie 1 (Primäre Hypothese): Multi-Asset Trend Following (`TSMOM`)

### 2.1 Festes Universum (10 roll-freie US-ETFs)
- **Aktien-Indizes (4):** `SPY`, `QQQ`, `EWG`, `EWJ`
- **Staatsanleihen (2):** `TLT`, `IEF`
- **Währungen (2):** `FXE`, `FXY`
- **Rohstoffe (2):** `GLD`, `DBC`
- *(Rein beschreibend, nicht Go-relevant:)* Krypto-Satellit `BTCUSDT` + `ETHUSDT` (`2018–2026`, Long/Flat, 30 bp) sowie Ablation `1B` (Aktien-ETFs nur Long/Flat).
- **Bekanntes Restrisiko (deklariert):** Der Yen-Carry-Cluster (`FXY` Short + `EWJ` Long) und der USD-Cluster (`FXE` + `FXY` gleichzeitig Short) sind durch die Asset-Klassen-Caps nicht vollständig eliminiert und werden über `Leave-2022-out` mitbeobachtet.

### 2.2 Eingefrorene Regeln *(inkl. L1, L2, P7, P8)*
- **Einstieg (Long & Short, Ausführung `Open(t+1)`):**
  - `Long`, wenn `Close(t) > close.shift(1).rolling(50).max()(t)`
  - `Short`, wenn `Close(t) < close.shift(1).rolling(50).min()(t)`
- **Ausstieg (kein fester Take-Profit, kein Break-Even-Stop):**
  - Trend-Exit am `Close(t)`: `Close(t) < close.shift(1).rolling(25).min()(t)` (Long) bzw. `> ...max()(t)` (Short) → Exit zum `Open(t+1)`, **ODER**
  - **Strikt monotoner Chandelier-Stop (`P8`, Auslösung intraday am `Low(t+1)` bzw. `High(t+1)`):**
    - Long: `Stop(t+1) = max(Stop(t), max(Fill_Price, HighestClose[Entry..t]) - 3,0 × ATR20(t))` *(darf nie fallen)*
    - Short: `Stop(t+1) = min(Stop(t), min(Fill_Price, LowestClose[Entry..t]) + 3,0 × ATR20(t))` *(darf nie steigen)*
- **Positionsgröße, R-Definition, Cluster- & Hebel-Caps (`P7`):**
  - **R-Definition:** `1 R = 3,0 × ATR20(t_signal)` am Signal-Bar `t`.
  - **Sizing:** `0,50 %` des aktuellen Kontowerts je Trade (Turtle-Fixierung zum Fill, **keine** tägliche Neugewichtung, **kein** Pyramidisieren).
  - **Cluster-Caps:** Aktien max. `2` Pos. (`1,0 %` Risk), Zinsen max. `1` Pos. (`0,5 %` Risk), FX max. `2` Pos. (`1,0 %` Risk), Rohstoffe max. `2` Pos. (`1,0 %` Risk).
  - **Gesamt-Limits:** max. `6` offene Pos. (`3,0 %` Risk), Brutto-Hebel-Cap **`≤ 2,0×`** Eigenkapital. Greift das `2,0×`-Limit bei einem neuen Signal, wird die neue Position auf die **Restkapazität gekürzt** (und übersprungen, falls Restkapazität `< 10 %` der Zielgröße); bestehende Positionen werden bei Kursdrift nicht angepasst.
  - **Priorität bei Signalüberhang:** Absteigend nach `|Close(t) - Donchian50| / ATR20(t)`.

### 2.3 Benchmarks, Statistik & Go-Kriterien *(inkl. P2, P3, P4, P5)*
- **Exakte Benchmark-Definitionen (`P3`):**
  1. **Risk-Parity Long-Only:** Gewichtung proportional zu `1 / σ_60` (60-Tage-realisierte Volatilität), monatliches Rebalancing (letzter Handelstag `Close` → nächstes `Open`), `10 bp` Kosten auf Turnover, Excess-Return über 3M-T-Bill.
  2. **`12-1`-TSMOM:** 252-Tage-Rendite unter Auslassung der letzten 21 Tage (`t-252` bis `t-22`), Long `> 0` / Short `< 0`, `1 / σ_60`-Sizing, monatliches Rebalancing, `10 bp` Kosten, Short-Carry `T-Bill − 50 bp`.
  3. **`60 % SPY / 40 % IEF`** (monatlich rebalanced) und optional `KMLM`/`DBMF` (beschreibend).
- **Statistische Tests & Power (`P2`):**
  - Über `T ≈ 18,7` Jahre hat `Excess-Sharpe = 0,55` eine Teststärke von `t ≈ 2,2` (`p < 0,05`), während ein Sharpe-Differenz-Test gegen `12-1-TSMOM` (`ρ ≈ 0,6`, `SE ≈ 0,21`) unrealistische `+0,34` Sharpe Vorsprung bräuchte.
  - **Go-relevant:** (a) Absolute Excess-Sharpe über Gesamtzeitraum mit **Stationary Bootstrap `p < 0,05`** (mittlere Blocklänge `20` Tage, `10.000` Ziehungen, einseitig) **UND** (b) **positives Alpha** in der Regression auf Risk-Parity Long-Only (`p < 0,05`).
  - **Beschreibend:** Vergleich zu `12-1`-TSMOM (`ΔSharpe ≥ 0` Punktschätzung + `p`-Wert) und `Deflated Sharpe Ratio` (`N = 22` Gesamtkonfigurationen).
- **Go-Kriterien (Strategie 1):**
  - Gesamtzeitraum (`2008–2026`): `Excess-Sharpe ≥ 0,55`, gepoolter `PF ≥ 1,25`, `Expectancy ≥ +0,12 R`, Bootstrap `p < 0,05`, Alpha vs. Risk-Parity `p < 0,05`; bei `2×` Kosten `Excess-Sharpe > 0`, `PF > 1,0`, `Expectancy > 0`.
  - **Holdout-Konsistenz (`2022–2026`):** `Excess-Sharpe > 0` und `≥ 50 %` der `IS+Val`-Sharpe (`Leave-2022-out` beschreibend).
  - **Trendfeindliche Regime (`P4`):** In jedem der 4 Fenster (`2011–12`, `2015–16`, `2018–19`, `2023`) darf der Max-Drawdown von S1 (skaliert auf die `IS+Val`-Volatilität von Benchmark 1 Risk-Parity) maximal `1,25 ×` dem Max-Drawdown von Benchmark 1 in demselben Fenster entsprechen.
  - **Plateau-Stabilität (nur `IS+Val`):** Alle 8 Nachbarn aus `{40/20, 50/25, 60/30} × {2,5×, 3,0×, 3,5×}` erreichen `Excess-Sharpe ≥ 0,5 × primär` und `> 0`, `PF > 1,10`.

---

## 3. Strategie 2 (Primäre Hypothese): Kurzfristige Index-Mean-Reversion (`IBS` + `RSI(2)`)

### 3.1 Festes Universum & Negativ-Kontrolle
- **Kern-Korb (`2008–2026`):** `SPY`, `QQQ`, `DIA`, `EWG`, `EWU`
- *(Rein beschreibende Negativ-Kontrollgruppe:)* `TLT`, `GLD`. **Kein `XLU`, kein Krypto.**

### 3.2 Eingefrorene Regeln *(inkl. L3, L4, L5, L7, P8)*
- **Regime-Filter:** `Close(t) > SMA(200)(t)`.
- **Trigger am `Close(t)`:** `IBS(t) < 0,20` (bei `High == Low` kein Signal) **UND** `RSI(2)(t) < 15`.
- **Ausführung:** Strikt **`Open(t+1)`** für Go/No-Go. *(`Close(t)`-Variante rein beschreibend als theoretische Obergrenze.)*
- **Ausstieg:** `Close(t) > High(t-1)` → Exit `Open(t+1)`, **ODER** Time-Stop (`Open(Tag 8)` bei Einstiegstag = Tag 1), **ODER** Katastrophen-Stop `Fill_Price − 3,0 × ATR14(t_signal)` (`ATR14` vom **Signal-Bar `t`**, Auslösung intraday am `Low`).
- **Sizing & Caps:** `1 R = 3,0 × ATR14(t_signal)`, `0,50 %` Kontorisiko je Trade, max. `0,33 ×` Eigenkapital je Position, `≤ 1,0×` Brutto-Gesamtallokation. Max. `3` gleichzeitige Positionen, davon **max. `1` US-Index (`SPY`, `QQQ`, `DIA`)**. Kein Pyramidisieren, keine Slot-Verdrängung. Priorität: aufsteigend nach `RSI(2)(t)`, Tie-Breaker niedrigstes `IBS(t)`.

### 3.3 Benchmarks, Statistik & Go-Kriterien *(inkl. P3, P5)*
- **Exakte Benchmark-Definition (`P3`):** `SMA(200)`-Halten = je `20 %` (`1/5`) des Eigenkapitals in jedem der 5 ETFs mit `Close(t) > SMA200(t)` (Signal `Close(t)` → Rebalancing `Open(t+1)`, `10 bp` Kosten, Rest-Cash zu 3M-T-Bill). Dazu Equal-Weight Buy & Hold (auf gleiche Volatilität skaliert).
- **Statistische Tests:** Reine **Monte-Carlo-Simulation** (`10.000` Ziehungen, einseitig) mit zufälligen Einstiegen *innerhalb* `Close > SMA(200)` bei gleicher Haltedauer-Verteilung, Investitionsquote und denselben Caps (max. 3 Pos., max. 1 US-Index, `1,0×` Cap). Zusätzlich Ausweis **unabhängiger Signal-Episoden** (`±2` Handelstage = 1 Episode).
- **Go-Kriterien:**
  - Stichprobe: `≥ 150` Trades (`≥ 80` Episoden) in `IS+Val` und `≥ 50` Trades (`≥ 25` Episoden) im Holdout.
  - Gesamtzeitraum: Gepoolter `PF ≥ 1,35`, `Expectancy ≥ +0,15 R`, Win-Rate `≥ 58 %`, `p < 0,05` gegen Regime-Monte-Carlo, **höhere Excess-Sharpe als `SMA(200)`-Halten**; bei `2×` Kosten `Excess-Sharpe > 0`, `PF > 1,0`, `Expectancy > 0`.
  - **Holdout-Konsistenz (`2022–2026`):** `Excess-Sharpe > 0` und `PF ≥ 1,15`.
  - **Plateau-Stabilität (nur `IS+Val`):** Nachbarn `IBS < 0,15 / 0,25`, `RSI(2) < 10 / 20`, Time-Stop `5 / 10` Tage erreichen `Excess-Sharpe ≥ 0,5 × primär` und `> 0`, `PF > 1,10`.

---

## 4. Ensemble (beschreibend) & Prozess-Gates

- **Ensemble (ausdrücklich rein beschreibend, nicht Go-relevant):** 50/50-Risikoallokation über inverse 60-Tage-realisierte Strategie-Volatilität, wöchentliches Rebalancing (Fr `Close` → Mo `Open`), Brutto-Cap `≤ 2,0×`. Ausweis von Wochen-Korrelation (`Fr→Fr`), **Tail-Korrelation** (schlechteste 10 % der `SPY`-Wochen) und Drawdown-Überlappung.
- **Holdout-Öffnungs-Gate:** Der Holdout (`2022–2026`) bleibt technisch abgeschnitten (`<= 2021-12-31`), bis auf `IS+Val` mindestens `Excess-Sharpe > 0,30`, `PF > 1,15` und das Plateau bestanden sind.
- **Endgültiges No-Go-Protokoll:** Scheitert eine Strategie im Holdout, ist diese Spezifikation endgültig gescheitert; jede Änderung erfordert einen `6–12`-monatigen prospektiven Paper-Test.
