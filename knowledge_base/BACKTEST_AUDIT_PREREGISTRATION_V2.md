# Pre-Registration v2.1 (mit Prozess-Fix v1.3): Monatliche Risk-Parity Trend-Allokation (`RP-Trend`)

**Status:** Pre-Registration v2.1 (bereinigt nach Opus-Checkpoint-1; per Git-Commit eingefroren, **FREIGEGEBEN FÜR IS+VAL**)  
**Datum:** 2026-11-25  
**Vorgänger:** `a60749ad9` (Checkpoint 2: `NO_GO` für S1 & S2)

---

## 1. Ausgangslage & Ökonomische Hypothese
Audit #1 hat gezeigt, dass statisches Risk-Parity Long-Only (`1/σ_60`) in `IS+Val` (`2008–2021`) bereits eine `Excess-Sharpe` von `0,571` (Referenzwert der v1.2-Engine) erreicht, während aktives tägliches `50/25`-Donchian-Trading durch Whipsaws und Aktien-Shorts verlor.  
Die Schwäche von statischem Risk-Parity ist die fehlende Ausstiegsbremse in Zins-/Inflations-Bärenmärkten (z. B. `2022`, wenn Aktien *und* Anleihen fallen).

**Hypothese (`RP-Trend`):** Ein **langsamer, monatlicher Absolutes-Momentum-Filter** auf dem 10-ETF-Makro-Korb belässt Kapital nur in Asset-Klassen mit positivem `12-1`-Monats-Excess-Trend und parkt den Rest automatisch in **3M-US-T-Bills**. Dadurch bleibt die monatliche Umschlaghäufigkeit minimal (Kosten: `10 bp` Round-Turn je Einheit Turnover; erwartete Jahreskosten werden berichtet, nicht angenommen), während tiefe Drawdowns abgeschnitten werden.

**Kontaminations-Erklärung:** Die Hypothese ist mit Kenntnis des Bärenmarkts 2022 formuliert. Die Renditen 2022–2026 von `SPY`, `QQQ`, `DIA`, `TLT` und `GLD` sowie ein `SMA200`-Trendbenchmark wurden im S2-Holdout (`s2_holdout_report.json`) bereits gesehen. Das Design (langsamer Trend, nur Long) ist zudem durch die `IS+Val`-Ergebnisse von S1/1B informiert; `IS+Val` wird damit zum dritten Mal verwendet. Der Holdout ist nur technisch unberührt. Sein Drawdown-Kriterium gilt als schwacher Beleg, die Beweislast liegt beim `IS+Val`-Alpha.

---

## 2. Universum, Daten & Konventionen
- **Universum (10 roll-freie US-ETFs, `adjclose` Total Return in USD):**
  `SPY`, `QQQ`, `EWG`, `EWJ`, `TLT`, `IEF`, `FXE`, `FXY`, `GLD`, `DBC`
- **Daten-Snapshot:** Unveränderter Snapshot `knowledge_base/audit_cache/` laut `snapshot_manifest.json` (Dateien ab `2006-02-01`, `FXY` ab `2007-02-13`, Ende `2026-11-20`). Vor jedem Lauf werden alle SHA256 per `assert` geprüft. Kalender = `SPY`-Handelstage. Fehlende Einzeltage werden mit dem Vortagswert fortgeschrieben; ihre Anzahl je ETF wird berichtet.
- **Split:**
  - `IS`: `2008-03-01` – `2016-12-31`
  - `Val`: `2017-01-01` – `2021-12-31`
  - `Holdout` (technisch gesperrt bis Öffnungs-Gate): `2022-01-03` – `2026-11-20` (startet flach)
- **Rendite & Cash:**
  - `rf_d(k) = max(0, IRX_close(k-1)) / 100 / 252` (Vortageswert, bei Lücken fortgeschrieben). Cash und Excess-Return für Tag `k` verwenden `rf_d(k)`.
  - Ungenutztes Cash verzinst mit `rf_d(k)`. **Kein Shorting, kein Hebel (`≤ 1,0×`)**.
- **Kosten:** `10 bp` Round-Turn auf monatlichen Turnover (`5 bp` je Kauf/Verkauf); Pflicht-Stresstest bei `2×` (`20 bp`).

---

## 3. Eingefrorene Regeln (`RP-Trend`, 2 Parameter)

### 3.1 Ausführungs- und Bewertungskonvention (gilt identisch für `RP-Trend`, `RP Long-Only` und `60/40`)
- Signal und Zielgewichte am `Close(t)` des letzten Handelstags im Monat. Die Ausführung erfolgt zum `Open(t+1)`. Die Rendite von Tag `t+1` ist `Σ w_alt,i·(O_i(t+1)/C_i(t) − 1)`, verkettet mit `Σ w_neu,i·(C_i(t+1)/O_i(t+1) − 1)` (`O` mit `adjclose`-Faktor angepasst). Die Kosten fallen zum `Open(t+1)` an.
- Zwischen den Rebalancings driften die Gewichte (Buy-and-Hold). `Turnover = Σ_i |w_target,i − w_drift,i|`, `Kosten = Turnover × 5 bp` (bei `2×` Kosten: `× 10 bp`).
- Erste Allokation: Signal am letzten Handelstag *vor* Periodenbeginn (`2008-02-29` bzw. `2021-12-31`), Ausführung zum ersten `Open` der Periode. Ein Rebalancing wird nur durch den Monatsend-Kalender ausgelöst, nie durch `Σw = 0`.
- Alle Benchmarks werden mit dieser Engine neu berechnet. `0,571` / `17,66 %` dienen nur als Referenz.

### 3.2 Trend-Signal & Gewichtung
- **Trend-Signal (`L = 252`, Skip `S = 21`):**
  - `Trend(i, t) = (AdjClose_i(t-21) / AdjClose_i(t-252) - 1) - CumTBillReturn[t-252 : t-21]`
  - `CumTBillReturn[t-252 : t-21] = Π_{k=t-251}^{t-21} (1 + rf_d(k)) − 1` (zusammengesetzt, gleiches Intervall wie die Preisrendite). Indizes sind `SPY`-Handelstage. `Trend = 0` gilt als inaktiv.
  - ETF `i` ist **aktiv**, wenn `Trend(i, t) > 0`; sonst **inaktiv (Gewicht = 0)**.
- **Gewichtung (`V = 60`):**
  - `σ_V(i, t)`: Standardabweichung der einfachen täglichen `adjclose`-Renditen über `[t-V+1, t]` (`ddof = 1`) × `√252`, identisch zu `indicators.py`.
  - Basis-Risk-Parity-Gewicht über **alle 10** ETFs: `w_rp(i, t) = (1 / σ_V(i, t)) / sum_{j=1..10}(1 / σ_V(j, t))`.
  - **Zielgewicht in `RP-Trend`:** `w_target(i, t) = w_rp(i, t)` falls `Trend(i, t) > 0`, sonst `0`.
  - **Cash-Quote:** `w_cash(t) = 1 - sum_i(w_target(i, t))` geht in 3M-T-Bills.

---

## 4. Benchmarks, Statistik & Strenges Prozess-Fix v1.3

### 4.1 Benchmarks
1. **Risk-Parity Long-Only (`1/σ_60`)** über dieselben 10 ETFs, monatlich rebalanced, `10 bp` Kosten (gleiche Engine).
2. **`60 % SPY / 40 % IEF`** monatlich rebalanced, `10 bp` Kosten (gleiche Engine).

### 4.2 Verpflichtende statistische Tests (`assert n_boot == 10_000`)
- **Stationary Bootstrap:** `assert n_boot == 10_000` in `stationary_bootstrap_sharpe_p`, `Seed = 42`, `mean_block = 20`, einseitig `p < 0,05` für `Excess-Sharpe > 0`.
- **OLS-Regression auf Risk-Parity Long-Only:** OLS der täglichen Excess-Renditen von `RP-Trend` auf `RP Long-Only` (beide nach Kosten, gleiche Engine). Standardfehler nach **Newey-West HAC mit Lag = 21**, einseitiger Test `H0: α ≤ 0`, `p < 0,05`. Zusätzlich (nur Bericht): monatliche Regression mit `NW-Lag 3` und Treynor-Mazuy-Spezifikation.
- **Max-DD-Definition:** Peak-to-Trough auf der täglich verketteten Kurve `Π(1 + rf + r_ex)`. Vola-skaliert: `Π(1 + rf + k·r_ex)` mit `k = σ(r_ex, Benchmark) / σ(r_ex, RP-Trend)`, beide auf `IS+Val`. Das auf `IS+Val` bestimmte `k` wird eingefroren und unverändert im Holdout verwendet.
- **Pflichtbericht, nicht Gate:** Deflated Sharpe Ratio mit `N_trials = 12` (S1, 1B, S2 sowie die 9 Plateau-Zellen) und Kalenderjahres-Tabelle für `RP-Trend`, `RP LO` und `60/40`.

### 4.3 Verschärftes Holdout-Öffnungs-Gate (Prozess-Fix v1.3)
Der Holdout (`2022–2026`) darf **nur** geöffnet werden, wenn auf `IS+Val` (`2008-03-01` – `2021-12-31`) **alle** folgenden Kriterien erfüllt sind:
1. `Excess-Sharpe ≥ 0,60` **UND** `Excess-Sharpe > Excess-Sharpe(Risk-Parity Long-Only)`
2. `OLS-Alpha vs. Risk-Parity Long-Only > 0` mit `p < 0,05` (Newey-West HAC Lag 21)
3. Skalierter `Max-DD` auf `IS+Val` **`≤ 0,75 × Max-DD(Risk-Parity Long-Only)`**
4. `2× Kosten` (`20 bp`): `Excess-Sharpe > 0,45`
5. **Plateau (9 Zellen auf `IS+Val`):** `L/S ∈ {(189,0), (252,0), (252,21)}` × `V ∈ {40, 60, 90}` Handelstage. Jede Zelle erreicht `Excess-Sharpe ≥ 0,50` und einen vola-skalierten Max-DD unter dem von `RP Long-Only` mit *demselben* `V`.

Scheitert ein Gate-Kriterium, lautet das Urteil `NO_GO` ohne Öffnung des Holdouts. Varianten dieser Spezifikation auf `IS+Val` sind danach ausgeschlossen.

### 4.4 Finale Go-Kriterien (nach einmaligem Holdout)
- **Holdout (`2022-01-03` – `2026-11-20`):** `Excess-Sharpe ≥ max(0,30; 0,5 × SR_IS+Val)` **UND** niedrigerer Max-DD (unskaliert sowie vola-skaliert mit eingefrorenem `IS+Val`-`k`) als `RP Long-Only` und `60/40` **UND** `Leave-2022-out` (`2023-01-01` – `2026-11-20`) `Excess-Sharpe > 0`.
- **Gesamtzeitraum (`2008–2026`):** `Excess-Sharpe ≥ 0,60`, `Bootstrap p < 0,05` (`10.000` Ziehungen), `OLS-Alpha vs. Risk-Parity p < 0,05`.
- **No-Go- & Shadow-Regel:** Mit diesem einmaligen Öffnen ist der Holdout `2022–2026` für **alle** Trend- und Allokations-Hypothesen verbraucht. Auch ein `GO` führt nur zu 12 Monaten prospektivem Shadow-Betrieb ohne Kapital. Eine Live-Allokation erfordert eine eigene Pre-Registration.
