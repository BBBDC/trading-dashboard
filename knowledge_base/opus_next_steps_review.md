# Frage 1: Reihenfolge

**Empfehlung: zuerst Punkt 3, dann Punkt 1, dann starten. Punkt 2 kommt danach.**

| Punkt | Wann | Grund |
|---|---|---|
| **3: SL vor TP** | **JETZT, als Erstes** | Diese Reihenfolge legt fest, gegen welchen Sollwert das Shadow-Buch gemessen wird. Bleibt die Engine bei TP1 vor SL, misst du echte Trades gegen einen zu optimistischen Backtest. Auf Krypto `1D` treffen TP und SL oft in derselben Kerze, der Fehler ist dort also groß. Danach `B4_VSA` (IS, Val, Holdout) neu rechnen und einfrieren. Prüfen, ob `portfolio_engine.py` im Shadow-Fill dieselbe Konvention nutzt, sonst ist die gesammelte Datenbasis verzerrt. |
| **1: Stufenleiter + Archiv** | **JETZT, direkt danach** | Die Regeln müssen festgeschrieben sein, bevor Daten fließen. Wer Schwellen nach dem Blick auf die Daten setzt, bekommt Pfadabhängigkeit (Forking Paths). Ohne `shadow_paper_archive.json` gehen prospektive Trades verloren, und die lassen sich nicht nachholen. |
| **2: AX-06** | **DANACH** | Der Vergleich BE-nach-TP1 gegen Trail reagiert extrem auf die Intrabar-Reihenfolge. Vor Punkt 3 ausgewertet ist er wertlos. Den Exit während der Sammelphase zu wechseln, verunreinigt das Buch. |

**Zwei Pflicht-Ergänzungen zu Punkt 1:**
- **Die 90-Tage-Regel (<3 Signale) erst ab Tag 90 scharf schalten.** Sonst fliegen in Woche 1 alle Zellen raus. Außerdem „Regime aus“ (Filter blockiert) von „Signal tot“ trennen. Das ist kein Abbau des Edges.
- **Ehrliche Einordnung der Leiter:** Bei σ≈1R/Trade liegt der Standardfehler von E[R] bei 30 Trades bei etwa 0,18R, also so groß wie der Effekt selbst. Die Stufe 1.0x bei 30 Trades ist damit Risikosteuerung und kein Beweis. Das Kriterium sollte „kein Widerspruch zum Backtest“ heißen (z. B. untere Grenze des Konfidenzintervalls nicht unter 0 beim konservativen Sollwert), nicht „positiv“.

**Zu AX-06:** Wenn möglich, schreibt das Shadow-Buch zu jedem Entry beide Exit-Varianten parallel mit (gleicher Entry, zwei Exit-Pfade, getrennter `cell_key`). Dann entscheidest du AX-06 prospektiv, ohne Neustart. Falls das nicht geht: aktuellen Exit einfrieren und AX-06 erst nach der Phase als neue Version mit neuem `cell_key` einführen.

**Realitätscheck:** 233 Holdout-Trades in rund 3,9 Jahren sind etwa 5 Trades pro Monat. In 2–4 Wochen bekommst du also nur ~2–5 `B4_VSA`-Trades. Für `1D` prüft die Phase nur, ob die Pipeline technisch läuft, statistisch belegt sie nichts. Die Stufe 15 erreichst du nach etwa 3 Monaten, die Stufe 30 nach etwa 6.

---

# Frage 2: `B4_VSA` Long-Only als Shadow-Hypothese

**Ja, aufnehmen, aber als explorative Hypothese aus der Zeit nach dem Holdout, nicht als validiert.** Drei Einwände sind quantitativ berechtigt:

1. **Der Holdout ist verbraucht.** Vorab festgelegt war `Long & Short`, und das ist im Holdout gescheitert. „Long-Only“ wurde gewählt, nachdem der Holdout bekannt war. Die `t=2.22` sind deshalb keine Bestätigung. Genau dafür gibt es das prospektive Shadow-Buch, also gehört es dorthin, korrekt beschriftet.

2. **Beta statt Alpha.** 2023–2026 war ein Krypto-Bullenmarkt. Dass die Shorts −35R verloren haben, passt genau dazu. Ein Long-Signal über `WMA233` misst deshalb vermutlich vor allem Trend-Beta. Die entscheidende Frage ist, was `B4_VSA` über einen naiven Trend-Long hinaus bringt.
   - **Vor der Aufnahme:** Auf denselben Holdout-Daten (schon mit SL vor TP) einen Benchmark rechnen: Long-Einstiege nach Zufall oder bei jedem Bar mit `Close > WMA233`, gleicher Exit, gleiche Assets. Das ist keine Optimierung, sondern eine Beta-Bereinigung.
   - Liegt `B4_VSA` nicht klar über diesem Benchmark, gehört es nicht ins Buch.
   - Der Benchmark selbst kommt als eigene Shadow-Zelle dazu. Bewertet wird dann die Differenz zwischen `B4_VSA` und dem Benchmark, nicht der absolute Wert.

3. **Die t-Statistik ist zu hoch angesetzt.** 233 Krypto-Trades sind nicht unabhängig. Altcoins bewegen sich mit BTC, die Signale ballen sich zeitlich. Mit Cluster-robusten Fehlern nach Woche oder Datum liegt `t` sehr wahrscheinlich unter 2. Das bitte nachrechnen und notieren.

**Strikte Regeln für die Zelle:**
- **Nur `WMA233`, kein Wechsel auf `SMA200`.** Getestet wurde `WMA233`. Jede Alternative ist ein neuer Freiheitsgrad, also Data Snooping.
- Parameter, Universum und Exit vor dem Start einfrieren. Beschriftung: `exploratory_post_holdout`.
- Kippt das Regime, liefert die Zelle kaum noch Signale. Das ist dann ein Regime-Stopp und kein Scheitern (siehe Ergänzung zur 90-Tage-Regel oben).

**Fazit:** Rechne zuerst SL vor TP, dann den Beta-Benchmark und die cluster-robuste `t`, und nimm `B4_VSA` erst danach auf. Ohne den Benchmark-Abstand sagt ein positives Shadow-Ergebnis in einer Bullenphase nichts aus.
