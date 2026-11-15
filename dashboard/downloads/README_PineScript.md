# degencoder Master Suite – Pine Script v5

Vollständige TradingView-Suite aus Indikator und Backtesting-Strategie mit identischer Signal-Mathematik.

| Datei | Typ | Zweck |
|---|---|---|
| `degencoder_master_suite.pine` | `indicator()` | Chart-Overlay, HUD, Order Blocks, FVGs, Webhook-Alerts |
| `degencoder_master_strategy.pine` | `strategy()` | Backtest mit risikobasierter Positionsgröße, Teilgewinn, Break-Even, ATR-Trailing |
| `README.md` | Doku | Diese Datei |

> **Prüfstatus:** Beide Skripte wurden statisch geprüft (Klammerbalance, Einrückung, keine v4-Funktionen, keine Zeilenumbrüche innerhalb von Ausdrücken). Ein Pine-Compiler steht außerhalb von TradingView nicht zur Verfügung – die Skripte sind also **noch nicht im Pine Editor kompiliert worden**. Bitte beim ersten Einfügen auf die Konsole des Editors achten.

---

## 1. Installation

1. TradingView öffnen → unten **Pine Editor**.
2. **Öffnen → Neuer Indikator**, gesamten Inhalt löschen, `degencoder_master_suite.pine` einfügen.
3. **Speichern** → **Zum Chart hinzufügen**.
4. Für den Backtest dasselbe mit `degencoder_master_strategy.pine` (**Neue Strategie**). Ergebnisse erscheinen im **Strategietester**.
5. Empfohlener Chart-Timeframe: 5m–15m bei HTF `60`. Der Chart-Timeframe sollte kleiner als der HTF-Timeframe sein.

Der RFE-Channel braucht 233 Bars Vorlauf; davor entstehen keine Setups.

---

## 2. Mathematik

### 2.1 Quantum Chaos Bänder (Donchian-ATR)

```
atr14         = ta.rma(ta.tr(true), 14)
upper_chaos   = ta.highest(high, 5) + 1.8 * atr14
lower_chaos   = ta.lowest(low, 5)  - 1.8 * atr14
midline_chaos = (ta.highest(high, 5) + ta.lowest(low, 5)) / 2
```

Darstellung: Cyan, transparente Füllung.

### 2.2 RFE Golden Ratio Channel

```
rfe_basis = ta.wma(close, 233)
rfe_stdev = ta.stdev(close, 233)
rfe_upper = rfe_basis + 1.618 * rfe_stdev
rfe_lower = rfe_basis - 1.618 * rfe_stdev
```

Darstellung: Indigo-Bänder mit Füllung, Basis in Gold.

### 2.3 Diskrete Signale

| Signal | Marker | Bedingung |
|---|---|---|
| Buy Area | grünes Kreuz unter Kerze | `low < rfe_lower and high[1] > rfe_lower` |
| Sell Area | rotes Kreuz über Kerze | `high > rfe_upper and low[1] < rfe_upper` |
| No Trade Zone | gelber Punkt auf Kerze (hl2) | `(low < rfe_basis and high[1] > rfe_basis) or (high > rfe_basis and low[1] < rfe_basis)` |
| Good Buy | Cyan-Dreieck nach oben | `(low < low[1] or low < rfe_lower) and close > open and close < rfe_basis and (low <= lower_chaos or buy_area)` |
| Good Sell | Magenta-Dreieck nach unten | `(high > high[1] or high > rfe_upper) and close < open and close > rfe_basis and (high >= upper_chaos or sell_area)` |

**Hinweis zur Spezifikation:** `lower_chaos` liegt per Definition immer `1.8 * ATR` unter dem 5-Bar-Tief, also unter dem aktuellen `low`. Der Teil `low <= lower_chaos` kann deshalb nur bei `ATR = 0` wahr werden. Praktisch gilt: **Good Buy tritt nur zusammen mit Buy Area auf** (analog Good Sell / Sell Area). Die Formel ist exakt wie spezifiziert umgesetzt, um die Parität nicht zu brechen. Falls ein Berühren des Bandes der Vorkerze gemeint war (`lower_chaos[1]`), ist das eine Ein-Zeilen-Änderung.

### 2.4 Retro Order Blocks

- **Bullish OB:** rote Kerze (`close < open`), danach 5 aufeinanderfolgende höhere Schlusskurse (`close > close[1]`).
- **Bearish OB:** grüne Kerze (`close > open`), danach 5 aufeinanderfolgende tiefere Schlusskurse.
- Zone = Hoch bis Tief der OB-Kerze; die Box startet an der OB-Kerze und wächst mit jeder Kerze nach rechts.
- **Liquidity Sweep:** OB-Kerze markiert das 20-Bar-Tief (`low == ta.lowest(low, 20)`) bzw. 20-Bar-Hoch.
- **Mitigation:** Schließt eine Kerze durch die Zone (Bullish: `close < Zonen-Tief`, Bearish: `close > Zonen-Hoch`), wird der OB entfernt (optional ausgegraut behalten).
- **Retest:** Docht taucht in die Zone ein, ohne sie per Schlusskurs zu durchbrechen. Jeder neue Eintritt zählt als ein Retest.

Badges (die Spezifikation nennt nur die Namen; die Zuordnung ist folgende Festlegung):

| Badge | Bedeutung |
|---|---|
| `[A/SWEEP]` | OB mit Liquidity Sweep, frisch oder im ersten Retest |
| `[A/R1]` | OB ohne Sweep, frisch oder im ersten Retest (R1) |
| `[B]` | zweiter Retest |
| `[C]` | dritter Retest oder mehr |

### 2.5 Fair Value Gaps

- **Bullish FVG:** `low > high[2]` → Zone `high[2]` bis `low`.
- **Bearish FVG:** `high < low[2]` → Zone `high` bis `low[2]`.
- **1-Tick Wick Mitigation:** Sobald ein Docht einer späteren Kerze die Zone berührt (`low <= Zonen-Hoch` bzw. `high >= Zonen-Tief`), gilt sie als gefüllt und wird entfernt (optional ausgegraut behalten).

### 2.6 HTF Trend-Governance

```
htfWma = request.security(syminfo.tickerid, "60", ta.wma(close, 233),
                          gaps=barmerge.gaps_off, lookahead=barmerge.lookahead_off)
```

- Long gegen den Trend (`close < htfWma`) ist gesperrt, **außer** Score ≥ 80 **und** Bullish Liquidity Sweep auf der Signalkerze.
- Shorts werden standardmäßig gespiegelt behandelt (`close > htfWma`); abschaltbar über „Governance für Shorts spiegeln".
- Historisch liefert `lookahead_off` den Wert der zuletzt geschlossenen HTF-Kerze (kein Blick in die Zukunft). In Echtzeit fließt die laufende HTF-Kerze ein, der Wert kann sich daher bis zum HTF-Schluss minimal bewegen.

### 2.7 3-Säulen A+ Scoring (0–100)

Harter Veto: **No Trade Zone aktiv → Score = 0**.

| Säule | Komponente | Punkte |
|---|---|---|
| 1 Zone & Value (max 35) | Buy / Sell Area | +25 |
| | In Chaos Band | +10 |
| 2 Trigger & Reversal (max 40) | Good Buy / Good Sell | +25 |
| | Liquidity Sweep (aktuelle Kerze) | +15 |
| 3 Struktur & Volumen (max 25) | Order Block Retest | +15 |
| | VSA: `volume > 1.3 * sma(volume, 20)` | +10 |

Grade: **A+** ≥ 80, **A** ≥ 60, **B** ≥ 40, **VETO** < 40 oder NTZ.

„In Chaos Band" ist umgesetzt als Schlusskurs in der unteren Kanalhälfte für Longs (`close < midline_chaos`) bzw. in der oberen für Shorts. Die wörtliche Lesart „Preis am äußeren Band" wäre aus dem in 2.3 genannten Grund nie erfüllt.

Ein Setup entsteht, wenn Score ≥ Mindest-Score (Standard 60), die HTF-Governance zustimmt und das Risiko positiv ist. Optional kann Good Buy/Sell als Pflicht-Trigger erzwungen werden.

### 2.8 Dynamisches TP/SL

Long (Short gespiegelt), Einstieg = Schlusskurs der Signalkerze:

```
SL    = (OB-Tief bei Retest, sonst 10-Bar Swing-Low) - 0.5 * ATR
R     = Einstieg - SL
ZielA = max(rfe_basis,   Einstieg + 1.2 * R)     // RFE Basis, min 1.2R
ZielB = max(upper_chaos, Einstieg + 2.0 * R)     // gegenüberliegendes Chaos-Band, min 2R
TP1   = min(ZielA, ZielB)
TP2   = max(ZielA, ZielB)
```

Abweichung von der Spezifikation, bewusst: Aus einer Buy Area heraus liegt die RFE-Basis meist **weiter** entfernt als das obere Chaos-Band. Bei starrer Zuordnung läge TP2 dann vor TP1. Deshalb werden beide Ziele nach Entfernung sortiert, und das Chaos-Ziel hat einen Mindestabstand von 2R (einstellbar).

---

## 3. HUD

Dunkles Table oben rechts (Position und Größe einstellbar):

| Zeile | Inhalt |
|---|---|
| Symbol | Ticker · Timeframe |
| HTF Bias | BULLISH / BEARISH relativ zur HTF WMA 233 |
| Score L / S | aktueller Long- und Short-Score der laufenden Kerze |
| Grade | Grade der stärkeren Seite |
| NTZ Status | FREI oder AKTIV · VETO |
| Aktives Setup | Richtung und Score des zuletzt ausgelösten, noch laufenden Setups |
| TP1 / TP2 / SL | Level des aktiven Setups |
| R:R | Chance-Risiko-Verhältnis zu TP1 und TP2 |

Die Strategie ergänzt Net Profit, Trades / Win %, Profit Factor und Max Drawdown.

Ein Setup im Indikator endet, sobald SL oder TP2 erreicht wird. Liegen SL und TP in derselben Kerze, zählt konservativ der SL.

---

## 4. Webhook-Integration

### 4.1 Indikator – zwei Wege

**A) `alert()` mit dynamischem JSON (empfohlen)**

1. Alarm erstellen → Bedingung: **DGC Master Suite** → **Beliebiger alert() Funktionsaufruf**.
2. Reiter **Benachrichtigungen** → **Webhook-URL** aktivieren und URL des Bots eintragen.
3. Das Nachrichtenfeld wird ignoriert; der Payload kommt aus dem Skript.

Payload:

```json
{
  "bot": "degencoder",
  "passphrase": "DEIN_GEHEIMNIS",
  "action": "buy",
  "side": "long",
  "symbol": "BTCUSDT",
  "exchange": "BINANCE",
  "interval": "15",
  "grade": "A+",
  "score": 85,
  "price": 64250.5,
  "sl": 63810.2,
  "tp1": 64900.0,
  "tp2": 65480.7,
  "htf_bias": "bull",
  "time": 1731600000000
}
```

`action`: `buy`, `sell`, `tp1`, `tp2`, `sl`. Bei Exit-Events ist `price` das erreichte Level. `time` ist die Öffnungszeit der Kerze in Unix-Millisekunden. Die Passphrase wird im Input „Webhook Passphrase" gesetzt.

**B) `alertcondition()` mit statischem JSON**

Im Alarm-Dialog einzeln wählbar: `DGC Long Entry`, `DGC Short Entry`, `DGC Long TP1`, `DGC Long TP2`, `DGC Long SL`, `DGC Short TP1`, `DGC Short TP2`, `DGC Short SL`, `DGC No Trade Zone`.

Das Nachrichtenfeld ist vorbefüllt, zum Beispiel:

```json
{"bot":"degencoder","action":"buy","side":"long","symbol":"{{ticker}}","exchange":"{{exchange}}","interval":"{{interval}}","price":{{close}},"score":{{plot("Long Score")}},"sl":{{plot("SL")}},"tp1":{{plot("TP1")}},"tp2":{{plot("TP2")}},"time":"{{timenow}}"}
```

`alertcondition()` erlaubt nur konstante Texte. Eine Passphrase muss hier bei Bedarf von Hand in das Nachrichtenfeld geschrieben werden. Trigger-Einstellung: **Einmal pro Balken (Schlusskurs)**.

### 4.2 Strategie

1. Alarm erstellen → Bedingung: **DGC Master Strategy** → **Nur Order-Ausführungen**.
2. Nachrichtenfeld exakt: `{{strategy.order.alert_message}}`
3. Webhook-URL eintragen.

Die Strategie sendet dasselbe JSON-Schema plus `qty`. Aktionen: `buy`, `sell`, `tp1`, `tp2`, `sl`, `trail_stop`.

### 4.3 Empfehlungen für den Bot

- Passphrase serverseitig prüfen, Requests ohne gültigen Wert verwerfen.
- Idempotenz über `symbol + action + time`, da TradingView Webhooks in Einzelfällen doppelt zustellt.
- TradingView-Webhooks benötigen Port 80 oder 443 und brechen nach etwa 3 Sekunden ab – schnell mit 200 antworten und asynchron ausführen.
- Ein Gegensignal bei offener Position (Indikator) bedeutet Richtungswechsel; der Bot muss entscheiden, ob er schließt oder dreht.

---

## 5. Strategie: Backtest-Engine

| Einstellung | Standard | Bedeutung |
|---|---|---|
| Startkapital | 10 000 | `initial_capital` |
| Kommission | 0.055 % je Seite | in den Strategie-Eigenschaften änderbar |
| Slippage | 2 Ticks | |
| Risiko pro Trade | 1 % Equity | Positionsgröße = Risiko / Abstand zum SL |
| Max. Hebel | 3 | Deckel für Positionswert / Equity |
| Teilgewinn TP1 | 50 % | Rest läuft bis TP2 oder Stop |
| Break-Even | an | Stop nach TP1 auf Einstiegspreis |
| ATR Trailing | an, 2.0 × ATR | nach TP1: Stop folgt `high - 2 * ATR` (Long), nur in Gewinnrichtung |
| Handelsrichtung | Long & Short | |
| Backtest-Zeitraum | 2018 bis offen | |

Ablauf eines Trades:

1. Signal bei Kerzenschluss → Market-Order, Ausführung zur Eröffnung der nächsten Kerze. Stop und Limits werden gleichzeitig platziert, die Position ist ab der ersten Kerze geschützt.
2. TP1 erreicht → Teilgewinn, Stop auf Break-Even, Trailing beginnt.
3. Ausstieg des Rests über TP2 oder Trailing-Stop.
4. Neue Einstiege nur, wenn keine Position offen ist (kein Pyramiding, kein Drehen).

Einschränkungen:

- SL/TP werden auf den Schlusskurs der Signalkerze berechnet, die Ausführung erfolgt zur nächsten Eröffnung. Bei Gaps weicht das reale R leicht ab.
- `margin_long/short = 0`: TradingViews Margin-Simulation ist abgeschaltet; die Hebelgrenze kommt aus dem Input „Max. Hebel".
- Ohne Bar Magnifier nimmt TradingView innerhalb einer Kerze einen festen Kursverlauf an. Treffen Stop und Limit in derselben Kerze, kann das Ergebnis vom realen Ablauf abweichen.
- Die Positionsgröße rechnet in der Kontowährung des Symbols; bei inversen Kontrakten oder Fremdwährungskonten prüfen.

---

## 6. Wichtige Inputs (Indikator)

| Gruppe | Input | Standard |
|---|---|---|
| Quantum Chaos Bänder | Donchian Länge / ATR Länge / Multiplikator | 5 / 14 / 1.8 |
| RFE Channel | Länge / Phi | 233 / 1.618 |
| Retro Order Blocks | Schlusskurse / Sweep Lookback / max. aktiv | 5 / 20 / 20 |
| Fair Value Gaps | max. aktiv | 20 |
| HTF Governance | Timeframe / WMA Länge | 60 / 233 |
| Scoring | Mindest-Score / VSA Länge / VSA Faktor | 60 / 20 / 1.3 |
| Scoring | Setups nur bei Kerzenschluss | an |
| Scoring | kein neues Setup gleicher Richtung, solange eines aktiv | an |
| TP/SL | Swing Lookback / SL-Puffer / Mindest-R | 10 / 0.5 ATR / 1.2 und 2.0 |

Mit den Standardwerten entspricht die Mathematik der Spezifikation aus dem Paritäts-Audit. Marker (Buy/Sell Area, NTZ, Good Buy/Sell) werden auf der laufenden Kerze live gezeichnet und können sich bis zum Kerzenschluss ändern; Setups und Alerts lösen erst bei Schluss aus.

---

## 7. Haftungsausschluss

Diese Skripte sind Analysewerkzeuge und keine Anlageberatung. Backtest-Ergebnisse garantieren keine künftigen Erträge. Vor Live-Betrieb mit einem Bot im Paper-Trading testen.
