# Audit der drei Hebel (Stand 26.11.2026)

Ich habe Code und Daten stichprobenartig geprüft. Zwei Punkte eurer Faktenlage stimmen so nicht. Das ändert die Bewertung.

**Korrekturen zur Faktenlage**
- **Trade-Zahl:** In `incubator_trades.json` finde ich nur 200 geschlossene Trades: 128 `SL`, 55 `BE`, 12 `TP2`, 5 `TIME`. Die 35,9 % Win-Rate und die −63,1R passen rechnerisch genau zu diesen ~200 Trades, nicht zu 588. Entweder sind Trades doppelt gezählt, oder es gibt ein Archiv, das ich nicht gesehen habe. Das bitte klären, bevor ihr damit Entscheidungen begründet.
- **Zeitebenen der Shadow-Zellen:** Nicht alle 12 `SHADOW_PAPER`-Zellen liegen auf 1h/4h/1D. Drei sind Intraday: `XYZ 15m`, `PG 15m` und `PG 30m`. Und `TSLA` als Live-Zelle ist `30m`.

## 1. Ergeben die Hebel Sinn?

| Hebel | Urteil | Begründung |
|---|---|---|
| 1 (5m aus, auf Shadow-Zellen umstellen) | **Ja, mit dem größten Hebel.** Aber in der vorgeschlagenen Form falsch gebaut (siehe unten). | 5m ist im Datensatz klar negativ. Wichtiger: Stufe 2 erzeugt gerade null Daten. Das blockiert die ganze Kette. |
| 2 (AX-06 umsetzen) | **Ja, aber zweitrangig und überschätzt.** | Den Verlust machen die Einstiege: 128 SL × −1R = −128R. Selbst wenn alle 55 BE-Exits im Schnitt +0,4R mehr bringen, sind das nur etwa +22R. Das dreht −63R nicht. |
| 3 (Live erst nach 30–40 Trades) | **Im Prinzip richtig, als feste Schwelle aber praktisch nicht erreichbar.** | Eine 1D-Zelle auf einem einzelnen Symbol liefert grob 1–3 Signale im Monat. 30 Trades dauern dann 1–2 Jahre, so lange bliebe Live faktisch eingefroren. |

## 2. Risiken und blinde Flecken

**Bei Hebel 1 (das wichtigste Problem überhaupt)**
- **Falsche Signal-Logik:** Der Inkubator nutzt `scan_for_micro_setup` (die degencoder-Mikro-Logik). Die Zellen der Whitelist wurden aber mit einer anderen Signal-Logik im Backtest validiert. Wenn der Inkubator auf `LMT 1D` seine eigene Mikro-Logik paper-tradet, prüft ihr eine andere Strategie. 40 solche Trades beweisen für die Zelle nichts.
- **Code ist fest auf 5m/15m verdrahtet:**
  - `ai_incubator.py:280`: `tf_sec = 300 if timeframe == "5m" else 900`. Ein 1h- oder 1D-Balken würde als 15 Minuten behandelt. Das verfälscht Zeitstempel, Time-Stop und Folgekerzen-Logik.
  - `incubator_time_stop_hours` (Zeile 77) und die Schwellen für ATR-Minimum, VSA und Puffer gibt es nur für 5m/15m/30m.
- **Kein Nachholen aus der Historie:** Der Scan über vergangene Balken (Zeile 1120ff.) darf für Shadow-Zellen nicht laufen. Prospektiv heißt: Signalzeit liegt nach dem Datum, an dem die Zelle auf Stufe 2 gesetzt wurde. Sonst ist es nur ein weiterer Backtest, der wie ein Paper-Trade aussieht.
- **Zuordnung Signal → Zelle ist wackelig:** In `portfolio_engine.py:1003-1010` wird die Zeitebene per Textsuche im Setup-Namen bestimmt (`"1h" in setup_text`). Inkubator und Live-Filter brauchen denselben eindeutigen Schlüssel aus Symbol, Zeitebene und Richtung. Das hängt auch mit dem nächsten Punkt zusammen.
- **Live seit 23.10. ohne Trade:** Dass zwei Live-Zellen in über einem Monat kein einziges Signal liefern, ist bei 1D plausibel, bei `TSLA 30m Short` aber verdächtig. Bitte in den Logs nach `[Triad Whitelist Guard]`-Abweisungen für TSLA und AMT suchen. Ich vermute eine falsche Zuordnung der Zeitebene, nicht fehlende Signale.

**Bei Hebel 2**
- **Optimistische Reihenfolge im selben Balken:** Der Code prüft TP1 und TP2 vor dem SL (Zeilen 843–897). Auf 5m ist das eine kleine Verzerrung, auf 1D eine große, weil ein Tagesbalken oft TP1 und SL zugleich enthält. Mit 1h/4h/1D wächst also das Problem.
- **Kurslücken:** `exit_price = sl` unterstellt eine Ausführung genau am Stop. 1D-Aktien springen über Wochenenden und Earnings. Der Stop müsste bei Lücke zum Eröffnungskurs ausgeführt werden.
- **AX-06 ist ein Rückschau-Befund:** Er schaut nur auf die Runner, die bei BE ausgestoppt wurden. Die Fälle, in denen BE vor einem Rückfall geschützt hat, fehlen. Die Regel selbst (BOS mit Volumen oder neues FVG) ist zudem ermessensabhängig und schwer exakt zu programmieren.
- **Grenzfall nachrechnen:** Mit −0,5R auf die Restposition sinkt der schlechteste Fall nach TP1 von +0,75R auf +0,50R. Das ist vertretbar, muss aber bewusst entschieden werden.

**Vermischung mit `trade_memory.json`**
- Die Lehren (Axiome) stammen aus 5m-Post-Mortems, und AX-06 hat `scope: ALL`. 5m-Lehren steuern damit künftig auch 1D-Trades.
- Ein schlimmerer Fehler wäre ein Rückkanal: Wenn Shadow-Trades in die Post-Mortem-Lernschleife laufen und die Regeln während der Sammelphase verändern, verschiebt sich das Ziel. Dann sind die 30 Trades nicht mehr einer festen Strategie zuzuordnen.
- Nach Hebel 2 sind die alten Trades und die neuen nicht mehr vergleichbar. Jeder Trade braucht deshalb Felder wie `exit_model_version` und `signal_engine_version`.

**Bei Hebel 3 (Statistik)**
- Bei einer Streuung von etwa 1,2–1,4R pro Trade liegt der Standardfehler nach 30 Trades bei rund 0,24R. 30 Trades können also nur einen Vorteil von etwa +0,45R oder mehr sicher von null unterscheiden. Als Test „Vorteil > 0“ taugen 30 Trades kaum.
- Sinnvoller ist ein anderer Test: Ist die Zelle nicht signifikant schlechter als ihr Backtest?

## 3. Meine Empfehlung

1. **Shadow-Paper in `portfolio_engine.py` einbauen, nicht in den Inkubator.** An der Stufen-Prüfung (`portfolio_engine.py:1020-1022`) wird bei `SHADOW_PAPER` statt `continue` ein Paper-Trade protokolliert, mit Live-Größe, Gebühren und Kurslücken-Logik. So ist garantiert, dass der Signalweg identisch zum Live-System ist. Kein Umbau des Inkubators nötig, kein Fehler durch falsche Zeitebene.
2. **Den Inkubator getrennt als reines Forschungslabor weiterführen:** 5m aus, nur 15m/30m. Seine Ergebnisse fließen nie in die Statistik der Stufen-Beförderung ein. `trade_memory.json` bekommt Namensräume nach Stufe und Zeitebene. Shadow-Trades laufen nicht durch die Lernschleife, die Regeln einer Zelle sind während der Sammelphase eingefroren.
3. **Hebel 2 erst nachrechnen, dann einführen:**
   - Zuerst die 55 BE-Exits und 12 TP2-Exits mit den vorhandenen Balkendaten gegenrechnen: BE gegen Swing-Stop gegen ATR-Trailing (z. B. Chandelier 2–3×ATR, höchstens −0,5R auf den Rest).
   - Danach bei jedem neuen Trade alle Exit-Varianten parallel mitbuchen. Das Exit-Modell beeinflusst den Einstieg nicht, so bekommt ihr für jede Variante die volle Stichprobe ohne Mehrkosten.
   - Den Code für TP und SL im selben Balken konservativ machen: SL zuerst, oder über kleinere Balken auflösen.
4. **Hebel 3 als Stufenleiter mit vorher festgelegten Regeln statt einer harten Schwelle:**
   - Ab etwa 15 Trades Beförderung mit 0,25-facher Risikogröße, wenn das Ergebnis mit dem Backtest vereinbar ist.
   - Ab 30 Trades volle Pilot-Größe.
   - Ein fortlaufender Test (z. B. SPRT gegen die Backtest-Erwartung) als Abbruchregel.
   - Zellen derselben Setup-Familie gepoolt auswerten, damit die Zahlen schneller wachsen.
   - Liefert eine Zelle in 90 Tagen weniger als 3 Signale, ist sie ohnehin nicht handelbar und fliegt raus.
   - Die Kriterien schriftlich festlegen, bevor der erste Trade läuft.
5. **Sofort:** Die Trade-Zahl (588 gegen 200) klären und prüfen, warum TSLA und AMT seit dem 23.10. keinen Trade ausgelöst haben.

**Fazit:** Die Richtung stimmt. Die Reihenfolge sollte aber sein: zuerst Shadow-Paper im Live-Signalweg (1), dann die Regeln für die Beförderung festlegen (3), zuletzt AX-06 nach dem Gegenrechnen (2). Der gefährlichste blinde Fleck ist, Paper-Daten mit der falschen Signal-Logik zu sammeln und sie dann für einen Nachweis zu halten.
