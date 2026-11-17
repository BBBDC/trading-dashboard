# Exekutiv-Gutachten: Portfolio-Governance und Risiko

**Stand:** 16.11.2026, 21:00 CET · **Grundlage:** die übergebenen Produktionsdaten. Marktpreise konnte ich nicht unabhängig prüfen. Alle Kennzahlen habe ich aus Entry- und Current-Preisen nachgerechnet. Die `pnl_pct`-Werte stimmen auf 0,01 Prozentpunkte.

---

## Kernaussagen

1. **Die Prozesse sind sauberer geworden. Dass die Performance besser ist, ist noch nicht belegt.** Die Eingriffe beheben echte, typische Backtest-Fehler. Die Stichprobe seit der Bereinigung ist aber statistisch zu klein, um eine Wirkung zu zeigen.
2. **Keine der 7 Live-Positionen steht auf der Pilot-Whitelist** (AVAX 30m, ETH 30m Short, AMZN 4h). Die offenen Gewinne kommen also nicht aus dem neuen Regelwerk. NDX-Short und SMCI-Short widersprechen außerdem direkt der Stufe-3-Regel „US-Megacap-Shorts gestrichen“.
3. **Das größte Risiko liegt nicht im Krypto-Abverkauf.** Es liegt in einem einzigen Makro-Faktor: USD-Stärke und Gold-Schwäche, über drei Positionen verteilt.
4. **Dass im Incubator nichts offen ist, ist plausibel, aber nicht bewiesen.** Ein konkreter Befund muss geprüft werden: SIE 4h wurde als `SHADOW_PAPER` eingestuft, im Schattenbuch ist aber kein Trade offen.

---

## 1. Status des KI-Portfolios

### 1.1 Die einzelnen Positionen

| Position | Richtung | PnL | Impliziter Hebel¹ | Trailing | Faktor-Cluster |
|---|---|---|---|---|---|
| DXY | Long | +1,85 % | **5,0×** | nein | USD-Stärke / Gold-Schwäche |
| GLD | Short | +5,17 % | 2,0× | ja | USD-Stärke / Gold-Schwäche |
| GOLD | Short | +6,25 % | 2,0× | ja | USD-Stärke / Gold-Schwäche |
| NDX | Short | +2,49 % | **6,0×** | ja (`TRAILING_STOP`) | US-Tech-Short |
| 9MW (SMCI) | Short | +5,84 % | 1,0× | ja | US-Tech-Short |
| UKX | Long | +0,92 % | 5,0× | ja | Europa/UK-Aktien Long |
| ADS | Long | −0,37 % | **7,0×** | nein | Europa/UK-Aktien Long |

¹ Berechnet als `pnl_lev_pct / pnl_pct`.

**Bewertung**
- **Verfassung:** 6 von 7 Positionen liegen im Plus, 5 von 7 haben einen aktiven Trailing-Stop. Ein Teil der Gewinne ist damit gesichert. Ungehebelt summiert sich das offene PnL auf etwa +22,2 %, gehebelt auf etwa +54,9 %. Beide Werte sind reine Summen und keine Rendite auf das Konto.
- **Klumpenrisiko:** GLD und GOLD bilden denselben Basiswert ab (Korrelation nahe 1). Zusammen mit dem DXY-Long ergibt das eine einzige Makro-Wette auf drei Tickern. Ein Schock wie eine Fed-Überraschung in Richtung Lockerung oder ein schwacher USD würde alle drei gleichzeitig treffen. Der DXY läuft mit 5×. Das ist das eigentliche Tail-Risiko im Buch.
- **NDX:** Der Status `TRAILING_STOP` weicht vom `HEALTHY` der anderen Positionen ab. Wahrscheinlich ist der Stop ausgelöst oder kurz davor. Bei 6× ist das die Position mit dem größten Hebel.
- **ADS:** 7× auf einen Fast Swing ohne Trailing. Liegt der Stop zum Beispiel 1 % entfernt, kostet er rund 7 % gehebelt. Das passt nur dann zu Flat-Risk-Sizing, wenn der Stop sehr eng sitzt.
- **Governance-Widerspruch:** Der Whitelist Guard hat heute GOOG und XYZ korrekt abgewiesen. Er greift also bei neuen Einstiegen, nicht beim bestehenden Bestand. Die 7 Positionen sind demnach Altbestand ohne ausdrücklich festgelegte Regeln. **NDX-Short und SMCI-Short sind genau die Klasse, die mit 87 % Verlustquote gestrichen wurde.**

### 1.2 All-Time 17,7 % gegenüber Rolling 60 % / 40 %

| Fenster | Trefferquote | Ø gehebeltes PnL je Trade | 95-%-Wilson-Intervall |
|---|---|---|---|
| All-Time (n=79, 14 Gewinner) | 17,7 % | −1,57 % | 10,9 % bis 27,6 % |
| Trades 1–69 (abgeleitet) | 14,5 % | −2,04 % | — |
| Trades 6–10 (abgeleitet) | 20 % (1/5) | −0,25 % | — |
| Letzte 10 | 40 % | +1,68 % | **16,8 % bis 68,7 %** |
| Letzte 5 | 60 % | +3,60 % | **23,1 % bis 88,2 %** |

**Was der Kontrast zeigt:**
- **Er ist statistisch nicht signifikant.** Unter der Annahme, dass die wahre Trefferquote bei 17,7 % liegt, gilt:
  - P(≥4 Treffer aus 10) ≈ **8,4 %**
  - P(≥3 Treffer aus 5) ≈ **4,2 %**

  Der zweite Wert liegt nur knapp unter 5 % und gilt nicht, weil das Fenster nachträglich ausgewählt wurde. Die Intervalle überlappen sich weitgehend.
- **Die Verbesserung lässt sich keiner Ursache zuordnen.** Zur selben Zeit lief ein starker Makro-Trend (USD hoch, Gold runter), und genau den reiten die Altbestände. Ob die Filter oder das Marktumfeld die Ursache sind, lässt sich ohne die Trade-Liste je Strategie nicht trennen.
- **Die Trefferquote allein sagt wenig.** Bei 17,7 % bräuchte das System ein Gewinn-Verlust-Verhältnis von mindestens **4,65** für den Break-even. Das wurde offensichtlich verfehlt.
- **Die Kennzahl −124,3 % ist eine Summe gehebelter Prozentwerte.** Als Kontorendite wäre sie ohne Nachschusspflicht unmöglich. Für Steuerungszwecke ist sie ungeeignet.
- **Die Einheiten passen nicht zusammen.** Der Circuit Breaker misst in R, die Portfolio-Statistik in gehebelten Prozent. Ein Drawdown von „−0,00R“ bei −124 % All-Time zeigt, dass der Breaker ab einem Reset-Punkt misst und nur realisierte Ergebnisse zählt. Das offene Risiko der 7 Positionen sieht er nicht.

---

## 2. Post-Mortem Lab: Warum ist nichts offen?

### 2.1 Mechanische Ursachen (gut erklärbar)

1. **Alle Altpositionen sind regulär geschlossen.** Heute gab es 3× Stop-Loss (RHM, ALV, FB2A) und 1× Break-even (SOL, nach TP1 bei +1,5R), am Samstag 1× TP2 (XRP). Kein Exit war unplausibel.
2. **Börsenzeiten und Regel 0:** Xetra hat um 17:30 geschlossen. Für die DE-Werte (RHM, ALV, FB2A, SIE) kann vor morgen früh keine neue Kerze schließen, also entsteht kein neues Signal. Um 21:00 ist ein leerer Aktienteil im Incubator **erwartbar**.
3. **Kein frisches Krypto-Setup:** Die Filter blockieren hier vermutlich *nicht*. Hohe Volatilität erfüllt das ATR-Gate (≥ 0,35 %) leicht, und breitere Stops senken `cost_r`. Der WMA-233-Filter lässt nach dem Abverkauf nur Shorts zu, und genau die waren erfolgreich (XRP bei TP2, SOL bei TP1). Für eine neue Short-Position braucht es nach einem Abverkauf erst eine Erholung oder eine neue Struktur. Bleibt die aus, ist kein Einstieg korrekt.

### 2.2 Disziplin oder Fehler?

**Mit den vorliegenden Daten ist das nicht zu entscheiden.** Ein stilles System sieht genauso aus wie ein ausgefallenes. Drei Auffälligkeiten:

| Befund | Problem |
|---|---|
| SIE 4h wurde heute als `SHADOW_PAPER` eingestuft | Stufe 2 bedeutet ausdrücklich prospektives Paper-Trading. Das Schattenbuch zeigt aber **0 offene Trades**. Entweder ist das Stufe-2-Buch ein anderes Buch als der Incubator, oder der Paper-Trade wurde nicht angelegt. **Muss geprüft werden.** |
| ALV.DE **Long** im Incubator | ALV 1h Long ist in Stufe 3 gestrichen, ALV 4h ist in Stufe 2 nur Short erlaubt. Ist der Incubator ein freies Forschungsbuch, ist das in Ordnung. Ist er das Stufe-2-Buch, verletzt der Trade den Direction-Lock. |
| Lücke zwischen Live und Paper | Incubator 36,5 % (n=562) gegenüber Live 17,7 % (n=79): z ≈ 3,3, p ≈ 0,001. Mögliche Ursachen sind ein anderes Universum, Execution-Shortfall oder ein verbliebener Optimismus-Bias im Paper-Buch. Außerdem unklar: Wurden die 562 Trades nach dem Stop-vor-TP-Fix **neu berechnet**? |

**Abhilfe:** Ein Ablehnungs-Funnel je Scan-Zyklus und ein Heartbeat. Pro Zyklus sollte geloggt werden: evaluierte Kandidaten, Ablehnungen je Gate (Kosten, ATR, WMA, Whitelist, Richtung), Signale, eröffnete Trades. Erst damit wird aus „0 offen“ ein belegter Zustand.

Die heutigen Ergebnisse passen trotzdem zu den Annahmen des Systems: Trendkonforme Krypto-Shorts haben funktioniert, DE-Einzelwerte im Seitwärtsmarkt nicht (0 von 3). Bei n=5 ist das ein Hinweis, kein Beweis.

---

## 3. Strategie-Aufbau nach der Bereinigung

```
Signal → Regel 0 (nur geschlossene Kerze)
       → WMA-233-Trendfilter (Richtung)
       → ATR/Close ≥ 0,35 % (Mindestvolatilität)
       → Kostengate cost_r ≤ 0,20
       → Triad Whitelist + Direction-Lock
       → Routing: Stufe 1 LIVE (0,15 % Risiko) | Stufe 2 SHADOW (0 %) | Stufe 3 Abweisung
```

**Die Logik der drei Stufen ist richtig.** Sie trennt *Hypothese*, *prospektiven Test* und *Kapitaleinsatz*. Gerade der prospektive Test in Stufe 2 ist der beste Schutz gegen Data-Snooping.

**Quantitative Schwächen:**

- **Multiple Testing:** Feine Zuschnitte wie „ETH 30m nur Short“, „AMZN 4h, aber nicht 1h oder 1D“ oder „ALV 4h nur Short“ deuten auf eine Auswahl aus einem großen Raster hin. Bei 100 getesteten Kombinationen und α = 5 % sind rund 5 falsch-positive Ergebnisse zu erwarten. Alle drei Pilot-Slots könnten Rauschen sein. Gegenmittel:
  - Anzahl der getesteten Kombinationen dokumentieren
  - Benjamini-Hochberg-Korrektur oder Deflated Sharpe anwenden
  - 0,15 % Risiko im Pilot beibehalten (das ist richtig dimensioniert)
- **Kostengate kalibrieren:** Mit Kosten c und Gewinn-Verlust-Verhältnis b liegt die Break-even-Trefferquote bei (1+c)/(1+b).
  - Bei b = 1,5R steigt sie durch c = 0,20 von 40 % auf **48 %**.
  - Bei der Incubator-Quote von 36,5 % braucht das System b ≥ **2,29R** statt 1,74R.

  Die Schwelle sollte also relativ zum gemessenen Brutto-Edge der jeweiligen Strategie gesetzt werden, nicht pauschal auf 20 %.
- **Verzögerung des WMA 233:** Die Verzögerung liegt bei etwa (n−1)/3 ≈ 77 Bars.

  | Zeitrahmen | Verzögerung |
  |---|---|
  | 30m Krypto | ≈ 1,6 Tage |
  | 4h Krypto | ≈ 13 Tage |
  | 4h Aktien | ≈ 1 Monat |

  Nach scharfen Abverkäufen erlaubt der Filter daher Shorts noch spät, nahe am Tief. An Trendwenden kommt es zu Fehlsignalen (Whipsaw).
- **Kriterien für den Aufstieg in eine höhere Stufe:** Die nötige Stichprobe ist etwa n ≈ (1,645·σ/μ)². Bei σ ≈ 1,2R sind das rund **62 Trades** für einen Netto-Edge von +0,25R und rund **173 Trades** für +0,15R. Diese Schwellen sollten vorab festgelegt werden, zusammen mit der Bedingung, dass die untere Konfidenzgrenze der Expectancy größer als 0 ist, *bevor* eine Stufe-2-Strategie live geht.
- **Gezählte Ergebnisse statt Trefferquote:** SOL steht als `CLOSED_BE`, hat aber +1,5R auf eine Teilposition realisiert. Je nach Zählweise ist das ein Gewinn oder nicht. Gesteuert werden sollte nur über die **Expectancy in R**.

---

## 4. Fazit zu den Eingriffen von Fable 5.2

| Eingriff | Bewertung | Einschränkung |
|---|---|---|
| Regel 0 / keine Auswertung innerhalb laufender Kerzen | **Richtig und der wichtigste Fix.** Er beseitigt Lookahead durch Repainting. | Kostet bis zu einen Bar Einstiegsverzögerung. |
| Stop-vor-TP-Fix | **Richtig.** Berührt eine Kerze sowohl Stop als auch Ziel, wird pessimistisch der Stop angenommen. Das macht die Backtests ehrlicher. | Die historischen Kennzahlen (562 Trades) müssen nachweislich neu berechnet sein, sonst ist der Vergleich verzerrt. |
| Kostengate und ATR-Gate | **Sinnvoll.** Die Gates verhindern Trades, die schon vor dem Einstieg verloren sind (Beispiel EUR/USD 8h). | Die Schwelle 0,20 ist für Strategien mit kleinem b zu großzügig (siehe Abschnitt 3). |
| Whitelist und Direction-Lock | **Wirkt bei neuen Einstiegen** (GOOG und XYZ abgewiesen). | **Wirkt nicht auf den Bestand.** NDX- und SMCI-Short laufen gegen Stufe 3. |
| WMA-233-Kausalitätsfilter | Ein solider Regime-Filter. | Er reduziert Rauschen, schafft aber keinen Edge. Die Verzögerung ist auf hohen Zeitrahmen erheblich. |

**Ist das System robuster geworden?** Prozessual ja, deutlich. Die Eingriffe beheben die drei häufigsten Ursachen, warum Backtests besser aussehen als die Realität: Lookahead, Mehrdeutigkeit innerhalb einer Kerze und ignorierte Kosten. Ob die Performance besser ist, ist noch unbewiesen. Der Pilot hat noch keinen nachweisbaren Live-Beitrag geliefert.

**Schutz im Krypto-Abverkauf:** Formal ja, denn das Live-Buch hat kein Krypto-Exposure. Das kommt aber **durch Abwesenheit** zustande, nicht durch nachgewiesene Filterqualität. Der ETH-30m-Short-Slot ist genau für dieses Marktumfeld gebaut und hat nicht ausgelöst. Am Funnel sollte geprüft werden, ob es kein Setup gab oder ob ein Gate blockiert hat. Das Risiko im Buch liegt woanders: im USD/Gold-Cluster und im ungeregelten Altbestand.

---

## 5. Maßnahmen nach Priorität

1. **Altbestand regeln:** Positionen als `LEGACY` kennzeichnen, keine Aufstockungen, Auslaufen über die bestehenden Stops. Für NDX- und SMCI-Short ausdrücklich entscheiden, ob schließen oder geduldet.
2. **Faktor-Limit:** Das Risiko im USD/Gold-Cluster begrenzen, zum Beispiel auf höchstens das 1,5-Fache des Einzelpositionsrisikos. GLD und GOLD zusammenführen.
3. **Circuit Breaker auf Marktbewertung umstellen:** Offenes Risiko einbeziehen, nicht nur realisiertes Ergebnis.
4. **SIE-Shadow-Routing prüfen** und die Bücher eindeutig trennen: Incubator (freie Forschung) und Stufe-2-Schattenbuch (Whitelist mit Direction-Lock).
5. **Ablehnungs-Funnel und Heartbeat** für alle Scanner einführen.
6. **Reporting in R** mit Expectancy und Konfidenzintervall. Summen gehebelter Prozentwerte aufgeben.
7. **Abgleich Live gegen Paper** auf demselben Universum, um den Execution-Shortfall zu messen.
8. **Aufstiegskriterien vorab festlegen:** Mindest-n und untere Konfidenzgrenze der Expectancy über 0, nach Kosten.

**Gesamturteil:** Die Architektur ist jetzt richtig aufgebaut. Ein Nachweis, dass sie funktioniert, steht noch aus. Das aktuelle Plus kommt aus einem Altbestand außerhalb des Regelwerks und aus einem günstigen Makro-Umfeld. Das ist kein Beleg für das neue System.
