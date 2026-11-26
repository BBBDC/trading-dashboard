# Pre-Registration: Kausale Einzel- & Paar-Ablation der 6 `degencoder`-Bausteine

**Status:** Pre-Registration (Entwurf zur Prüfung vor dem ersten Code/Run)  
**Datum:** 2026-11-26  
**Ziel:** Empirisch klären, welche einzelnen `degencoder`-Indikatorbausteine (und welche Paare) auf `1D` bzw. `4h` tatsächlich einen positiven Roh-Edge nach Kosten liefern – und welche nur Rauschen oder schädliche Filter sind.

---

## 1. Die 6 orthogonalen Bausteine (keine doppelten Sub-Labels)

Um Multiple-Testing-Explosion (2.300+ Kombinationen) zu vermeiden, werden die Indikatoren aus [degencoder_engine.py](file:///home/admin/trading/degencoder_engine.py) und [market_evaluator.py](file:///home/admin/trading/market_evaluator.py) auf **6 klar getrennte Bausteine** verdichtet:

| ID | Baustein | Quelle / Kausale Logik am `Close(t)` |
|---|---|---|
| **B1** | **`Degencoder Signal / Chaos-Band`** | `detect_degencoder_signals`: BUY/SELL bzw. Band-Rebound außerhalb der No-Trade-Zone |
| **B2** | **`Fair Value Gap (FVG)`** | `detect_degencoder_fvgs`: Preis berührt/retestet ein bis Bar `t` entstandenes, noch unmitigiertes FVG |
| **B3** | **`Order Block (OB)`** | `detect_degencoder_order_blocks`: Preis berührt/retestet einen bis Bar `t` bestätigten, aktiven OB |
| **B4** | **`VSA Wyckoff Volume`** | `calculate_vsa_wyckoff`: Volumen-Spike (`≥ 1,5×` SMA20) oder Low-Volume-Pullback (`≤ 0,8×` SMA20) |
| **B5** | **`RSI(14) / Divergenz`** | `RSI(14) < 35 / > 65` oder kausal bestätigte bullische/bärische Divergenz bis Bar `t` |
| **B6** | **`Golden Pocket (0,618–0,65)`** | Preis im `0,618–0,65`-Retracement des letzten bis Bar `t` bestätigten Swings |

**Daraus ergeben sich exakt `6 + 15 = 21` Kombinationen:**
- **6 Einzel-Bausteine:** `B1`, `B2`, `B3`, `B4`, `B5`, `B6` (jeder Baustein triggert allein).
- **15 Paare:** Alle `(Bi, Bj)` mit `i < j` (Zone/Setup + Bestätigungs-Trigger innerhalb eines `≤ 3`-Bar-Fensters).
- **Keine 3er-/4er-Kombinationen** in diesem ersten Sweep!

---

## 2. Strikte Kausalität (Anti-Lookahead-Garantie)

Da Funktionen wie `detect_degencoder_order_blocks` oder Swing-Pivots in Backtests leicht unbewusst zukünftige Kerzen sehen, gilt zwingend:
- **Strikte Bar-by-Bar-Kausalität:** Zu Zeitpunkt `t` sind ausschließlich Kerzen `0..t` sichtbar (ein Swing-Hoch/Tief, OB oder FVG gilt erst ab dem Bestätigungs-Close `t_confirm ≤ t` als existent).
- **Ausführung:** Einstieg immer erst zum **`Open(t+1)`** nach Signal am `Close(t)`.
- **Regel-0-Prüfung:** Ein Unit-Test prüft explizit, dass das Signal an Bar `t` exakt identisch bleibt, wenn alle Bars `> t` abgeschnitten werden.

---

## 3. Einheitliches Exit-, Kosten- & Pooling-Modell (kein Parameter-Tuning)

Alle 21 Kombinationen werden mit **demselben, eingefrorenen** Execution- & Exit-Modell getestet, damit ausschließlich der **Signal-Unterschied** gemessen wird:
- **Stop-Loss:** `2,0 × ATR(14)` unter/über Einstieg (`Open(t+1)`).
- **Exit:** Konservativ **SL vor TP** innerhalb jeder Kerze, Gap-Aware (`min(SL, Open)`):
  - `TP1 = +1,5 R` (50 % realisieren, Rest auf Break-Even + `2,0 × ATR14` Trailing wie `backtest_matrix_engine.py`)
  - `TP2 = +3,0 R` (Rest-Vollziel)
- **Kosten:** US-ETFs/Aktien `10 bp` Round-Turn (`5 bp` je Seite), Krypto `20 bp` Round-Turn; plus `2×`-Kosten-Check.
- **Gepooltes Universum (statt Einzelticker-Cherry-Picking):**
  - **Korb A (`1D` Makro/ETFs, unser eingefrorener `audit_cache`):** `SPY`, `QQQ`, `DIA`, `EWG`, `EWU`, `EWJ`, `TLT`, `IEF`, `GLD`, `DBC` (`IS+Val`: `2008-03` – `2021-12`; `Holdout` `2022–2026` bleibt bis Gate gesperrt).
  - **Korb B (`4h`/`1D` Krypto-Majors, Binance-Cache):** `BTCUSDT`, `ETHUSDT`, `LTCUSDT`, `XRPUSDT`, `SOLUSDT`, `LINKUSDT` (`IS+Val`: `2018-01` – `2022-12`; `Holdout` `2023–2026` gesperrt).

---

## 4. Multiple-Testing-Schutz & Go-Kriterien

Bei `21` Kombinationen × `2` Körben (`N = 42` Tests) würden unter reinem Zufall ~2 Kombinationen scheinbar `p < 0,05` erreichen. Deshalb gelten strenge Hürden:
1. **Mindest-Stichprobe in `IS+Val`:** `≥ 100` gepoolte Trades pro Korb (zu seltene Paare werden verworfen).
2. **Roh-Edge-Schwelle (`IS+Val`):** `Profit Factor ≥ 1,25`, `Expectancy ≥ +0,12 R` nach Kosten, weiterhin `> 0` bei `2×` Kosten.
3. **Multiple-Testing-Korrektur:** **Benjamini-Hochberg FDR (`q < 0,05`)** über alle `21` Kombinationen je Korb *plus* **Deflated Sharpe Ratio** (`N = 21`).
4. **Holdout-Gate:** Erst wenn ein Baustein oder Paar diese `IS+Val`-Hürden besteht (und eine einfache Trend-/Pullback-Baseline schlägt), wird für genau diesen Gewinner der versiegelte Holdout einmalig geöffnet.
