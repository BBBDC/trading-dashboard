# Grok 4.7 Quantitative Matrix-Analyse (1.272 Simulationen)

**Datum:** 15. November 2026  
**Analysiert von:** Grok 4.7 (xAI)  
**Datenbasis:** `/home/admin/trading/knowledge_base/matrix_backtest_summary.json`

---

## Executive Summary
Von 1.272 Simulationen sind 42 als `ROBUST_EDGE` etikettiert. Nach In-Sample/Out-of-Sample-Zerlegung, nach Abzug verschachtelter Modi und nach einem Stabilitätsfilter bleiben **8 wirtschaftliche Wetten**. Die Summe aller Zellen außerhalb des toten Causal-Modus ist **−3.575R**. Die grünen Zellen (**+432R**) finanzieren die roten (**−4.591R**) nicht. Der Median jeder Zelle mit Trades ist auf jedem Timeframe negativ.

Das Badge ist eine Top-Quintil-Marke, kein Nachweis. Definition im Engine: `trades ≥ 15` und `E[R] ≥ 0.15` und `PF ≥ 1.25` und `OOS-R ≥ 0`. Unter 337 Zellen mit mindestens 15 Trades liegt das mittlere E[R] bei **−0.225**, der Median bei **−0.214**, das 75. Perzentil bei **+0.036**, das 90. bei **+0.241**. Die Schwelle 0.15 sitzt damit in der rechten Flanke einer links verschobenen Verteilung. 50 Zellen schaffen E[R] ≥ 0.15, 47 davon auch PF ≥ 1.25, 42 davon auch OOS-R ≥ 0. Der OOS-Filter wirft nur 5 Zellen hinaus.

---

## 1. Marktstruktur und Timeframe-Dynamik

Das System ist ein Reversal gegen die Lage zur 233-WMA: Long nur unter der Basis, Short nur darüber, Zielgeometrie 50 % bei 1,2R und 50 % bei 2,0R plus Trail. Bei beobachteten durchschnittlichen Gewinnern von etwa 1,9–2,4R und Verlierern von etwa 1,05–1,30R (sobald die Kosten klein sind) liegt die Break-even-Trefferquote bei **rund 42 %**. Die Masse der Zellen handelt mit 30–38 % Trefferquote und verliert deshalb pro Trade, auch wenn einzelne 2R-Gewinner optisch groß sind.

Zwei verschiedene Bruchmechaniken erzeugen die Desaster:

### A. Kostenbruch (Forex unterhalb 8h)
Round-Turn in der Engine ist `2 × (0,055 % + 0,02 %) = 0,15 %` des Nominals. In R umgerechnet:
`R_Kosten ≈ 0,0015 / (Stopdistanz / Preis)`, Mindeststop `1,2 × ATR`.

Daraus folgt die Klippe: bei `ATR/Preis < 0,35 %` frisst die Reibung mehr als etwa 0,3R, bei `ATR/Preis ≈ 0,10 %` mehr als 1R. 
- EUR/USD 15m Long & Short: 41 Trades, Trefferquote 22 %, PF 0,11, **−72,91R**, E[R] = −1,78. Die implizite durchschnittliche Verlustgröße ist **−2,56R**, der durchschnittliche „Gewinner“ nur etwa +1,0R.
- GBP/USD 15m: 47 Trades, Trefferquote 19 %, PF 0,05, **−103,08R**, durchschnittlicher Verlust etwa **−2,85R**.
- EUR/USD 1h: **175 Trades, −104,37R**, E[R] = −0,60, Trefferquote 37,7 %.
- GBP/USD 1h: 178 Trades, **−123,52R**.

**Dieselbe Mathematik auf EUR/USD 8h:** 19 Trades, Trefferquote 52,6 %, PF 1,70, **+8,22R**, E[R] = +0,43, durchschnittlicher Verlust **−1,31R**, durchschnittlicher Gewinner **+2,0R**. Der Stop ist wieder ein Stop, das Ziel ein Ziel. Acht Stunden sind drei Bars pro Tag und treffen die Liquiditätsblöcke Asien, London, New York. Ein 20-Bar-Sweep ist dort ein Mehrtages-Extrem.

### B. Driftbruch (Tages- und Mehrtageshorizonte bei positiver Risikoprämie)
Auf 1D ist die durchschnittliche Verlustgröße wieder etwa −1,0R. Kosten sind dort irrelevant, weil der ATR mehrere Prozent beträgt. 
- Nvidia 1D Nur Short: 30 Trades, Trefferquote **13,3 %**, PF 0,35, **−17,30R**.
- Apple 1D Short: Trefferquote 13,9 %, **−22,71R**.
- Microsoft: 12,9 %, **−20,92R**.
- Broadcom: 17,1 %, **−19,01R**.
- QQQ: 16,7 %, **−13,96R**; SPY: 17,4 %, **−12,10R**.

**Ursache:** Die 233-WMA auf 1D ist ein Jahresmittel. In einem säkularen Aufwärtstrend notiert der Kurs fast durchgehend darüber. Longs, die einen Close unter der WMA verlangen, feuern selten oder nie (Nvidia 1D Long: 0 Trades). Shorts feuern am oberen 1,618-Band dauernd. Das Band ist in einem Driftmarkt eine trendende Hüllkurve, keine Decke. Jeder Short ist eine Wette gegen die Risikoprämie.

### C. Wo der Horizont zur Liquidität passt

| Block | Gehandelte Zellen | Robust | Median R | Summe R |
|---|---:|---:|---:|---:|
| Forex 15m | 6 | 0 | −56,5 | −352 |
| Forex 1h | 6 | 0 | −63,6 | −458 |
| Forex 8h | 6 | 1 | +1,6 | +4,8 |
| Crypto 30m | 36 | 8 | −3,6 | −126 |
| Crypto 1h | 36 | 8 | ≈ 0 | −4 |
| Crypto 4h | 36 | 0 | −6,3 | −204 |
| DAX 4h | 24 | 6 | **+2,17** | **+43** |
| US-Tech 4h | 36 | 3 | +0,51 | −3 |
| US-Tech 1D | 33 | 2 | −4,1 | −230 |
| Index, alle TF | — | **0** | negativ ab 1h | SPY −32, QQQ −49, DAX-Index −11 |
| Rohstoffe 1h | 9 | 0 | −35,7 | −316 |

**DAX 4h ist der einzige Kategorie-Timeframe-Block mit klar positivem Median.** Xetra plus US-Overlap ergibt zwei bis drei 4h-Blöcke. Ein Sweep auf diesem Takt ist ein Session-Extrem von Siemens, Allianz, Adidas, Telekom.

**Wichtiges Debugging zum Causal-Trend-Filter:** Der Causal-Trend-Filter hat in **318 von 318** Läufen null Trades produziert. Das ist ein Widerspruch im Code, kein Marktergebnis: Der degencoder Long verlangt `Close < WMA233` (Mean Reversion in Discount), während der Filter `Close > WMA233` verlangte. Ein Reversal und ein Filter auf derselben Seite desselben Mittels können geometrisch nicht gleichzeitig wahr sein!

---

## 2. Vier operative Buckets

Kapital bekommen nur Bucket B und Bucket C, und dort nur die genannten Timeframes.

### Bucket A — Short-Sperre, Kapital 0
Shorts am oberen Band sind strukturell negativ, Longs haben keinen Zelleneintrag, der IS- und OOS-Erwartung gleichzeitig positiv hält. Für dieses Reversal-System sind sie ungeeignet:
- Apple, Broadcom, Alphabet, Nvidia, Meta, Palantir, CrowdStrike, Deutsche Telekom, Rheinmetall, Airbus.

### Bucket B — Bidirektional (nur auf dem genannten Takt)
- **Avalanche:** 30m und 1h, beide Seiten (4h/8h negativ).
- **Near Protocol:** 1h, beide Seiten.
- **Amazon:** 4h beide Seiten, 1h nur Long, 1D beide Seiten (Einziger Mega-Cap, dessen 1D-Short funktioniert: 24 Trades, 45,8 % WR, +12,3R).
- **Siemens:** nur 4h, beide Seiten (1h Long & Short +24,74R ist der Irrtum der Rohdaten: OOS nur +1,75R auf 27 Trades, E[R] = 0,065, Trefferquote 33 %).
- **Allianz:** 4h nur Short, 1h nur Long.
- **Adidas:** 4h beide Seiten (halbe Größe).
- **EUR/USD:** nur 8h, beide Seiten (jeder tiefere TF gesperrt).
- **WTI Rohöl:** nur 1D, beide Seiten (halbe Größe).

### Bucket C — Nur Short
- **Ethereum:** 30m Short. (Long-Summe −55,1R. Der 30m-Short: 18 Trades, 66,7 % WR, PF 2,85, +13,72R, IS E[R] 0,71, OOS E[R] 0,85, DD 2,3 %).
- **BMW:** 15m und 1D, halbe Größe, nicht im Kernbuch (Long-Summe −18,1R. 15m-Short +10,1R).

### Bucket D — Handelsverbot für dieses System
- GBP/USD auf allen Timeframes (Summe **−301R**).
- Gold (Summe **−155R**), Silber.
- Bitcoin (Long −35R, der 30m-Short hat IS-E[R] = −0,02).
- Solana, BNB, Cardano, Ripple, Dogecoin, Chainlink, Sui, Render.
- SPY, QQQ, DAX-Index.
- Netflix, Microsoft, AMD, SAP, Tesla.

---

## 3. Out-of-Sample-Stabilität & Die Top-10-Kombinationen

Stabilitätsfilter, den ein Live-Eintrag bestehen muss: `E[R]_IS > 0,10`, `E[R]_OOS > 0,25`, `OOS-Trades ≥ 7`, `Trades ≥ 17`, `PF ≥ 1,40`.

| # | Kombination | n | OOS n | Total R | IS E[R] | OOS E[R] | PF | DD | WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | Avalanche 30m Long & Short | 38 | 18 | +27,90 | 0,46 | 1,04 | 2,37 | 4,4 % | 52,6 % |
| 2 | Near 1h Long & Short | 44 | 17 | +15,30 | 0,35 | 0,34 | 1,52 | 6,2 % | 40,9 % |
| 3 | Amazon 4h Long & Short | 18 | 7 | +14,24 | 0,44 | 1,34 | 2,57 | 5,1 % | 50,0 % |
| 4 | Ethereum 30m Nur Short | 18 | 7 | +13,72 | 0,71 | 0,85 | 2,85 | 2,3 % | 66,7 % |
| 5 | Siemens 4h Long & Short | 25 | 9 | +8,83 | 0,25 | 0,54 | 1,58 | 4,6 % | 44,0 % |
| 6 | Allianz 4h Nur Short | 17 | 7 | +10,19 | 0,60 | 0,60 | 1,99 | 3,3 % | 47,1 % |
| 7 | Avalanche 1h Long & Short | 44 | 16 | +13,93 | 0,25 | 0,44 | 1,53 | 7,5 % | 47,7 % |
| 8 | Amazon 1h Nur Long | 25 | 8 | +12,33 | 0,26 | 0,98 | 1,89 | 5,2 % | 48,0 % |
| 9 | EUR/USD 8h Long & Short | 19 | 8 | +8,22 | 0,19 | 0,76 | 1,70 | 3,6 % | 52,6 % |
| 10 | Amazon 1D Long & Short | 28 | 10 | +11,03 | 0,40 | 0,38 | 1,64 | 4,9 % | 42,9 % |

---

## 4. Die 5 harten Regeln für das System

1. **Whitelist und Cluster-Cap:** `portfolio_engine.py` und der Pine-Strategiekopf führen nur diese 10 Kombinationen aus. Pro Trade 0,35 % des Kontos. Offenes Risiko pro Cluster 0,50 %, Portfolio-Cap 2,0 %.
2. **ATR-Kostengate vor jeder Order:** Ablehnung, wenn `ATR(14) / Close < 0,0035`.
3. **Richtungs- und Takt-Sperren:** Ethereum nur Short, Allianz 4h nur Short, Allianz 1h nur Long, Amazon 1h nur Long, Forex nur EUR/USD 8h. Kein 3D, kein 1W, keine Indizes.
4. **Promotion nur über OOS-Erwartung, nie über Total-R:** Neue Setups benötigen `OOS-E[R] > 0,20` und mindestens 8 OOS-Trades.
5. **Ein aktives Signal pro Namen:** Live-Kapital sitzt in den 7 Clustern oder es sitzt in Cash.
