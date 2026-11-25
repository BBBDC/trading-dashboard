# Checkpoint 2: Red-Team-Post-Audit gegen Pre-Registration v1.2 (f49177f0f)

Beide Strategien sind **NO_GO**, keine kommt in den Shadow-Betrieb. Grundlage sind die beiden JSON-Reports und ein Abgleich mit `backtest_audit/run_is_val.py`, `run_s2_holdout.py` und `engine.py`. Ich habe nichts neu gerechnet und den Holdout nicht angefasst. Das Speichern unter `knowledge_base/opus_checkpoint2_postaudit.md` hast du nicht freigegeben, deshalb steht der Bericht hier.

## 0. Urteile

| | Urteil |
|---|---|
| **S1** TSMOM 50/25, 3× ATR, Long & Short | **NO_GO** |
| **S2** IBS + RSI(2), Einstieg Open(t+1) | **NO_GO, endgültig nach §4** |

## 1. S1: Kriterien-Check

**Öffnungs-Gate:**
- SR 0,353 > 0,30 ✓
- PF 1,247 > 1,15 ✓
- Plateau nur 7/8 ✗: Bei 40/20 / 2,5× liegt SR bei 0,081 (verlangt ≥ 0,177) und PF bei 1,058 (verlangt > 1,10). Der Holdout blieb korrekt zu, die Sperre sitzt technisch in `engine.py:49`.

**Go-Kriterien, nur zur Einordnung auf IS+Val gerechnet:**

| Kriterium | Schwelle | Ist | |
|---|---|---|---|
| Excess-Sharpe | ≥ 0,55 | 0,353 | ✗ |
| PF | ≥ 1,25 | 1,247 | ✗ (knapp) |
| Expectancy | ≥ 0,12 R | 0,100 R | ✗ |
| Bootstrap | p < 0,05 | 0,08 | ✗ |
| Alpha vs. Risk-Parity | p < 0,05 | 0,068 (t = 1,49) | ✗ |
| 2× Kosten (SR / PF / Expectancy) | > 0 / > 1 / > 0 | 0,202 / 1,144 / 0,062 R | ✓ |

Um über 2008–2026 auf SR ≥ 0,55 zu kommen, müsste der Holdout grob SR ≈ 1,1 liefern. Auch ein Blick in den Holdout hätte S1 also nicht gerettet.

**Ökonomische Ursache:** Die Aktien-Shorts sind der größte erkennbare Verlusttreiber, aber nicht der einzige.
- **Was die Shorts kosten:** Ohne Aktien-Shorts (Ablation 1B, nur Long/Flat) steigt Total-R von 64,4 auf 79,7 bei 87 Trades weniger. Die Shorts kosteten also rund −15 R, etwa −0,18 R pro Trade. Das ist grob gerechnet, weil die Wechselwirkung mit den Positions-Caps fehlt.
- **Warum Shorts hier scheitern:**
  - Sie wetten gegen die Aktienrisikoprämie.
  - Die meisten Abverkäufe in IS+Val waren schnelle V-Formen (2010, 2011, 2015, Q4 2018, 2020). Der 50-Tage-Breakout kommt spät, und Bärenmarkt-Rallys sowie die Fed-Stützung lösen dann den Stop aus.
  - Der Carry ist negativ: Der Short zahlt die Dividende und erhält nur T-Bill − 50 bp.
- **Auch ohne Shorts reicht es nicht:**
  - 1B erreicht SR 0,523 und liegt damit unter der Hürde von 0,55 und unter dem Risk-Parity-Benchmark mit 0,571.
  - Das Plateau wird zu langsameren Lookbacks und breiteren Stops hin stetig besser und bricht im schnellen Eck ein. Der Edge ist eine langsame Trendprämie mit hohen Whipsaw-Kosten.
  - S1 diversifiziert (β −0,07), hat aber kein belegtes eigenständiges Alpha.

## 2. S2: Kriterien-Check

| Kriterium | Ist | |
|---|---|---|
| Stichprobe IS+Val / Holdout (Trades / Episoden) | 277/189 und 113/78 | ✓ |
| **Holdout Excess-Sharpe > 0** | **−0,024** | ✗ |
| **Holdout PF ≥ 1,15** | **1,075** | ✗ |
| Gesamt PF ≥ 1,35 | 1,381 | ✓ |
| **Gesamt Expectancy ≥ 0,15 R** | **0,060 R** | ✗ |
| Gesamt Trefferquote ≥ 58 % | 65,9 % | ✓ |
| Regime-Monte-Carlo p < 0,05 | 0,034 | ✓ |
| **Sharpe über SMA200-Halten** | **0,367 vs. 0,559** | ✗ |
| 2× Kosten gesamt | 0,166 / 1,18 / 0,03 R | ✓ |
| Plateau | 6/6 | ✓ |

Im Holdout bei doppelten Kosten liegt der PF bei 0,91, S2 verliert dort also Geld. Vier harte Kriterien sind verfehlt, zwei davon im Holdout. Damit greift §4.

**Ökonomische Ursache: Die These „S2 verlor wegen der Zinsen“ trifft nur zum kleineren Teil zu.**
- **Grundlage:** In `engine.py` ist `r_mult` netto nach Kosten, enthält aber keine T-Bill-Opportunitätskosten. Die Zinshürde trifft nur das investierte Kapital, weil freies Cash den T-Bill-Satz selbst verdient.
- **1 R in Basispunkten:** Aus der Differenz zum 2×-Kosten-Lauf (0,03 R pro 10 bp) folgt 1 R ≈ 330–345 bp.
- **Netto-Edge pro Trade:** in IS+Val etwa 26 bp, im Holdout etwa 4,5 bp.
- **Pro Jahr:** In IS+Val etwa 0,80 % roh, im Holdout etwa 0,15 % roh. Ausgewiesen sind im Holdout −0,03 % über T-Bill, die Zinslast beträgt also rund 0,18 Prozentpunkte pro Jahr.
- **Zerlegung:** Von rund 0,8 Prozentpunkten Verschlechterung pro Jahr entfallen etwa 80 % auf den Zerfall des Brutto-Edges (PF von 1,52 auf 1,075) und etwa 20 % auf die Zinshürde. Die Zinsen haben das Vorzeichen gedreht, verursacht haben sie den Absturz nicht.
- **Mögliche Gründe für den Edge-Zerfall (nicht getestet):** Die Erholung nach dem Dip passiert zunehmend über Nacht, sodass der Einstieg zu Open(t+1) sie verpasst. Dazu kommen Fehlsignale in den Bärenmarkt-Rallys 2022 und Crowding, seit RSI(2) und IBS breit bekannt sind.
- **Gegen SMA200-Halten:** S2 ist nur selten investiert und deckt einen Teil derselben Marktphasen ab. Um auf Sharpe-Basis zu gewinnen, bräuchte es pro investiertem Tag einen viel höheren Edge. Schon in IS+Val lag S2 hinten (0,491 vs. 0,621).
- **Negativkontrolle:** TLT und GLD lagen in IS+Val mit SR 0,513 über S2 mit 0,491. Der Effekt war also nie spezifisch für Aktienindizes.

## 3. Prozess-Befunde

- **F1 (schwer):** Das Öffnungs-Gate war schwächer als die Go-Kriterien. S2 verfehlte Expectancy (0,079 R statt 0,15 R) und den SMA200-Vergleich (0,491 vs. 0,621) schon auf IS+Val. Der Holdout ging damit an eine Strategie, die nicht bestehen konnte.
- **F2 (mittel):** Bootstrap lief mit 2.000 Ziehungen (`run_is_val.py:55`), Monte Carlo mit 1.000 (`run_s2_holdout.py:206`), registriert waren jeweils 10.000. Für die Urteile ändert das nichts (Fehlerbreite etwa ±0,006), es ist aber eine Abweichung vom Protokoll und muss dokumentiert werden.
- **F3 (mittel):** Die Expectancy-Hürde passte nicht zur Strategie. 0,15 R entsprechen bei 1 R = 3× ATR14 rund 50 bp netto pro Trade, und das hat keine Plateau-Zelle erreicht. Das ist eine Lehre für künftige Registrierungen; nachträglich wird nichts geändert.
- **F4 (niedrig):** In den Reports fehlen bzw. von mir nicht geprüft:
  - Daten-Hashes und Abgleich mit einer Zweitquelle
  - Indikator-Test gegen TA-Lib
  - Drawdown-Check in den trendfeindlichen Fenstern
  - Vergleich mit 12-1-TSMOM
  - Deflated Sharpe Ratio
  - Leave-2022-out

  Für die Urteile spielt das keine Rolle, das Audit-Dossier ist aber unvollständig.
- **F5 (Warnung):** Jetzt im S1-Plateau die bessere Zelle 60/30 oder 3,5× als neue Hauptkonfiguration zu nehmen, wäre klassisches Data-Snooping.

## 4. Nächster Schritt ohne Data-Snooping

1. **Urteile einfrieren und committen.** Keine neuen Parameter, kein weiterer Lauf auf 2022–2026.
2. **Der S1-Holdout bleibt dauerhaft versiegelt.** Er ist der einzige unverbrauchte Out-of-Sample-Zeitraum für Trendstrategien.
3. **1B kommt nicht in den Holdout.** Die Variante wurde ausgewählt, nachdem ihr Ergebnis bekannt war, und verfehlt trotzdem 0,55 und den Risk-Parity-Benchmark. Eine Chance hätte sie nur mit abgesenkten Hürden, und das wäre Snooping. Wenn 1B weiterverfolgt werden soll:
   - neue Pre-Registration v2.0 mit unveränderten Hürden,
   - danach nur ein prospektiver Papertest.
   - Bei SR ≈ 0,5 liefern 6–12 Monate nur t ≈ 0,5. Das prüft die Umsetzung, beweist aber nichts statistisch.
4. **S2:** keine Varianten auf historischen Daten, also kein Einstieg zum Close(t), kein Zinsfilter, kein kleineres Universum. Jede Änderung braucht nach §4 eine neue Pre-Registration und 6–12 Monate prospektiven Papertest.
5. **Prozess-Fix v1.3:**
   - Das Öffnungs-Gate enthält alle Go-Kriterien, die sich schon auf IS+Val prüfen lassen.
   - Die Ziehungszahlen werden im Code fest auf 10.000 gesetzt und per Assertion geprüft.
   - R-Hürden werden pro Trade in Basispunkten bzw. passend zur Haltedauer festgelegt.
6. **Fazit:** Die einfachen, nicht optimierten Benchmarks haben beide Strategien geschlagen (Risk-Parity Long-Only SR 0,571 in IS+Val, SMA200-Halten SR 0,559 über den Gesamtzeitraum). An ihnen muss sich jede künftige Hypothese messen.

Wenn du das Schreiben erlaubst, lege ich den Bericht unter `knowledge_base/opus_checkpoint2_postaudit.md` ab und committe ihn auf Wunsch.
