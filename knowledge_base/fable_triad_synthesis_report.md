# Finale Synthese: Audit von Groks Matrix-Analyse (Claude Fable 5.2)

**Urteil vorab:** Groks Diagnose stimmt in der Richtung, aber seine Whitelist ist statistisch nicht belegt. Keine der 10 Zellen bekommt von mir eine volle Produktionsfreigabe; drei gehen als Pilot mit kleinem Risiko live, sechs laufen nur im Schattenbuch, drei werden gestrichen.

Ich habe alle Zahlen gegen die Rohdaten nachgerechnet und die Engine (`backtest_matrix_engine.py`) für alle 801 gehandelten Zellen auf Einzeltrade-Ebene neu laufen lassen; für die Whitelist-Zellen stimmen Trades und Total-R exakt mit der Summary überein. An Produktionsdateien habe ich nichts geändert.

---

## 1. Mathematisches Audit

### Kosten-Klippe: Formel richtig, Gate falsch platziert
- **Arithmetik stimmt.** Round-Turn ist 2 × (0,055 % + 0,02 %) = 15 bp. Bei ATR/Close = 0,35 % und Mindeststop 1,2 × ATR kostet das 0,36R, bei 0,10 % sind es 1,25R.
- **Empirisch bestätigt** (alle Long-&-Short-Trades nach ATR/Close):

| ATR/Close | Trades | E[R] |
|---|---:|---:|
| < 0,10 % | 279 | −1,30 |
| 0,10–0,20 % | 305 | −0,56 |
| 0,20–0,35 % | 574 | −0,29 |
| 0,35–0,60 % | 1.279 | −0,12 |
| > 0,60 % | 5.083 | −0,14 bis −0,25 |

- **Das Gate ist notwendig, aber nicht hinreichend.** Auch oberhalb der Schwelle ist jede Assetklasse negativ (DAX −0,09R, US-Tech −0,16R, Crypto −0,19R, Index −0,33R je Trade).
- **Regel 1 und Regel 2 widersprechen sich.** 84 % der EUR/USD-8h-Trades haben ATR/Close < 0,35 % (Median 0,32 %). Groks eigenes Gate würde seine Whitelist-Zelle #9 fast vollständig ablehnen.
- **Das Kostenmodell ist für Forex vermutlich falsch.** 15 bp sind Crypto-Taker-Gebühren; EUR/USD kostet nach meiner Einschätzung real einen Bruchteil davon. Die −73R und −103R auf 15m sind damit zum Teil ein Artefakt der Engine und kein reiner Marktbefund.
- **Das Gate gehört auf die Stopdistanz, nicht auf den ATR.** Die Kosten in R hängen vom tatsächlichen Stop ab: `cost_R = Kosten / (|Entry − Stop| / Entry)`.

### Break-Even-Trefferquote: 42 % ist die Obergrenze, nicht der Zentralwert
- Aus Groks eigenen Spannen (Gewinner 1,9–2,4R, Verlierer 1,05–1,30R) folgt eine Break-Even-Quote von 30 % bis 41 %.
- Gemessen über alle Zellen mit mindestens 15 Trades liegt der Median bei 36 % (Quartile 33–40 %), für die Whitelist-Zellen bei 28–41 %.
- Die Schlussfolgerung hält trotzdem: Die Masse handelt mit 31–34 % Trefferquote und liegt damit darunter.

### Buchhaltungsfehler in Groks Summen
- Die −3.575R zählen verschachtelte Modi dreifach. Wirtschaftlich relevant ist nur Long & Short: **−1.793R auf 7.534 Trades, also −0,238R je Trade**.
- Die +432R sind die Summe der 42 Robust-Zellen (inklusive Doppelzählung), nicht aller grünen Zellen. Alle positiven Zellen summieren sich auf +1.079R, alle negativen auf −4.654R.
- Die Executive Summary nennt 8 Wetten, die Tabelle 10.

### Streichung der Pseudo-Edges: richtig entschieden, aber nicht wasserdicht
- **Siemens 1h:** In-Sample 0,43R (54 Trades) gegen Out-of-Sample 0,06R (27 Trades) ist eine Differenz von 0,37R bei einem Standardfehler von 0,42R, also z ≈ 0,9. Das ist mit Rauschen vereinbar.
- **Die Logik ist asymmetrisch.** Siemens 4h bleibt wegen 0,54R auf 9 OOS-Trades drin, bei einem Standardfehler von etwa 0,57R. Diese Zahl ist von null nicht unterscheidbar. Siemens 1h hat mit 81 Trades sogar die bessere Gesamtevidenz (t = 1,54 gegen 1,04).
- **Der OOS-Filter ist selbst ein Selektionsschritt.** Wer 308 Zellen nach ihrem OOS-Ergebnis filtert, hat kein Out-of-Sample mehr.

### Der eigentliche Befund: Die Whitelist ist vom Zufall nicht zu trennen
- **Zufallserwartung:** Wenn jede Zelle wahres E[R] = 0 hätte, würden etwa 19 Zellen Groks Filter zufällig bestehen; bei wahrem E[R] = −0,2 etwa 5. Tatsächlich bestehen 14 (10 nach Entschachtelung).
- **Einzelsignifikanz:** Nur drei Zellen erreichen einseitig p < 0,05. Bei 308 getesteten Zellen bräuchte man t ≈ 3,6; das Maximum ist 2,38.
- **Geschrumpfte Schätzung:** Mit der Zellverteilung als Prior (ohne Forex: Mittel −0,17R, Streuung 0,19R) liegt jede Whitelist-Zelle bei −0,06 bis +0,08R ± 0,17R.

| Zelle | n | E[R] roh | t | p (Bootstrap) | E[R] geschrumpft | P(E>0) |
|---|---:|---:|---:|---:|---:|---:|
| Avalanche 30m L&S | 38 | 0,73 | 2,38 | 0,007 | +0,08 | 0,70 |
| Ethereum 30m Short | 18 | 0,76 | 2,11 | 0,017 | +0,04 | 0,59 |
| Amazon 4h L&S | 18 | 0,79 | 1,65 | 0,041 | −0,04 | 0,42 |
| Avalanche 1h L&S | 44 | 0,32 | 1,36 | 0,084 | +0,03 | 0,57 |
| Near 1h L&S | 44 | 0,35 | 1,28 | 0,093 | 0,00 | 0,51 |
| Amazon 1h Long | 25 | 0,49 | 1,40 | 0,077 | −0,02 | 0,46 |
| Allianz 4h Short | 17 | 0,60 | 1,27 | 0,096 | −0,06 | 0,37 |
| Amazon 1D L&S | 28 | 0,39 | 1,16 | 0,124 | −0,03 | 0,42 |
| EUR/USD 8h L&S | 19 | 0,43 | 1,09 | 0,135 | −0,05 | 0,38 |
| Siemens 4h L&S | 25 | 0,35 | 1,04 | 0,149 | −0,04 | 0,40 |

### Drei Engine-Schwächen, die Grok nicht erwähnt
- **Crypto-OOS ist ein einziges Regime.** 3.000 Bars auf 30m sind 63 Tage; das OOS-Fenster ist 28.10.–15.11.2026, also 19 Tage. Avalanche 30m und Ethereum 30m teilen sich dieselben 19 Tage. Auf 1h sind es 37 Tage.
- **Stops füllen immer exakt am Stop, auch bei Gaps.** Korrigiert auf den Eröffnungskurs fällt Amazon 1h Long von 0,49R auf 0,24R (5 Gap-Stops) und Allianz 1h Long von 0,43R auf 0,28R.
- **Im selben Bar wird TP2 vor dem Stop geprüft.** Das ist ein optimistischer Bias in allen Zellen.

### Causal-Trend-Filter: Bug im Testaufbau, nicht im Live-System
- **Groks Befund ist korrekt:** 318 von 318 Läufen ohne Trade. `good_buy` verlangt `Close < WMA233`, der Filter `Close > WMA233` auf derselben Serie; das ist eine leere Menge.
- **Seine Deutung greift zu kurz.** Live prüft `ai_incubator.py` den Entry auf 5m/15m gegen die 233-WMA des **1h**-Charts. Ein Rücksetzer im niedrigen Timeframe innerhalb eines übergeordneten Aufwärtstrends ist widerspruchsfrei.
- **Konsequenz:** Die Matrix hat die Live-Logik nie getestet. Der Filter ist weder widerlegt noch bestätigt; 25 % des Simulationsbudgets haben keine Information geliefert. Der Modus muss mit einer WMA aus dem höheren Timeframe neu laufen.

---

## 2. Konsens-Portfolio

| Stufe | Zellen | Risiko je Trade |
|---|---|---:|
| **Pilot (live)** | Avalanche 30m L&S, Ethereum 30m nur Short, Amazon 4h L&S | 0,15 % |
| **Schattenbuch (Papier)** | Near 1h L&S, Avalanche 1h L&S, Siemens 4h L&S, Siemens 1h L&S, Allianz 4h nur Short, Amazon 1D L&S | 0 % |
| **Gestrichen** | EUR/USD 8h, Amazon 1h nur Long, Allianz 1h nur Long | — |

- **Gründe für die Streichungen:** EUR/USD 8h scheitert am eigenen Kostengate und hat ein unverifiziertes Kostenmodell. Bei Amazon 1h und Allianz 1h verschwindet die Hälfte des Edges durch die Gap-Korrektur.
- **Siemens 1h** kommt zurück ins Schattenbuch, weil die Streichung nicht belegt ist.
- **`ai_incubator.py` bekommt keine Freigabe.** Er handelt ausschließlich 5m und 15m (184 und 16 der letzten 200 Trades). 5m wurde nie getestet, 15m ist in der Matrix der schlechteste Takt. Er sollte nur als Schattenbuch weiterlaufen.

**Allokation:**
- **Risiko:** 0,15 % statt 0,35 %. Das Ruinrisiko wäre auch bei 0,35 % klein. Der Grund ist, dass der erwartete Edge nach Schrumpfung bei null liegt und der Pilot Information kauft, keinen Ertrag.
- **Cluster-Cap:** 0,30 % offenes Risiko je Cluster. Avalanche, Near und Ethereum zählen als **ein** Crypto-Cluster, nicht als drei.
- **Portfolio-Cap:** 0,60 % offenes Risiko, eine Position je Name.
- **Bestehende Limits sind zu weit.** Der Incubator erlaubt aktuell 16R gesamt und 8R je Cluster bei 0,5 % je Trade, also bis zu 8 % offenes Risiko. `portfolio_engine.py` steht bei 3R und 1,5R.
- **Beförderung auf 0,35 %:** erst nach mindestens 40 neuen Trades je Zelle (live oder Papier, nach dem 15.11.2026), wenn die untere 90-%-Grenze von E[R] über null liegt.
- **Abschaltung:** bei −6R kumuliert auf neuen Trades einer Zelle.

---

## 3. Regelwerk: vier Filter für `portfolio_engine.py` und `ai_incubator.py`

1. **Zellen-Whitelist mit Stufe.** Eine Order ist nur zulässig, wenn (Symbol, Timeframe, Richtung) in der Tabelle steht; die Stufe bestimmt das Risiko (0,15 % oder 0 %). Damit sind Groks Richtungssperren abgedeckt, ebenso sein Driftbefund (Aktien- und Index-Shorts auf 1D mit 13–17 % Trefferquote).
2. **Kostengate auf Stopbasis.** Ablehnung, wenn `cost_R = Kosten_Klasse / (|Entry − Stop| / Entry) > 0,20`. Bei 15 bp heißt das: Stop mindestens 0,75 % vom Entry. Die Kosten müssen je Assetklasse hinterlegt werden. Groks `ATR/Close ≥ 0,35 %` bleibt als grober Vorfilter.
3. **Heat-Caps in Prozent des Kontos.** 0,15 % je Trade, 0,30 % je Korrelations-Cluster, 0,60 % gesamt, eine Position je Name. Die Limits dürfen nicht in R definiert sein, weil sie sonst mit dem Risiko je Trade mitskalieren.
4. **Statistisches Beförderungs- und Abschaltgate.** Beförderung nur über die untere Konfidenzgrenze auf neuen Trades, nie über Total-R oder das OOS-Mittel. Groks Schwelle (OOS-E[R] > 0,20 bei 8 Trades) hat einen Standardfehler von rund 0,6R und trennt nichts.

Vor dem nächsten Matrix-Lauf muss die Engine Gap-Fills am Eröffnungskurs, Stop-vor-Ziel im selben Bar, Kosten je Assetklasse und den Causal-Filter auf höherem Timeframe bekommen. Sonst wiederholt sich die Selektion auf geschönten Zahlen.
