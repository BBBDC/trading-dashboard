# Checkpoint 1b: Prüfung der Pre-Registration v1.1

Ich habe v1.1 gegen mein eigenes Pre-Audit (`knowledge_base/opus_checkpoint1_preaudit.md`) geprüft. Es lief weder Code noch ein Backtest. Der Text, den du geschickt hast, steht so auch in `knowledge_base/BACKTEST_AUDIT_PREREGISTRATION.md`. Laut dem Git-Status zu Sitzungsbeginn ist die Datei aber noch nicht in Git eingecheckt, also nicht eingefroren.

## 1. Die 9 Blocker

| # | Status | Kurzbegründung |
|---|---|---|
| D1 Uneinheitliche Rendite-Basis | **GELÖST** | Nur noch USD-ETFs, alle Kurse (O/H/L/C) über `adjclose` als Total Return. Das gilt für Strategien und Benchmarks gleich. |
| D2 Cash und Finanzierung | **GELÖST** (Rest siehe P6) | Freies Cash verzinst mit T-Bill, Hebel kostet T-Bill + 50 bp, alle Sharpes als Überrendite. Die Short-Seite ist noch nicht geregelt. |
| D3 FX ohne Carry | **GELÖST** | FXE und FXY enthalten die Zinsen im NAV, schließen synchron mit den US-Börsen und sind handelbar. |
| D4 Offene Wahl DXY/FXE | **GELÖST** | FXE ist fest eingetragen, DXY gestrichen. |
| D5 Zu wenig Vorlauf | **GELÖST** | Vom 2007-02-15 bis 2008-02-29 sind es etwa 263 Handelstage, also mindestens 250. Das reicht knapp, auch für 12-1-TSMOM auf FXY. |
| L1 Off-by-one | **GELÖST** | Geschlossenes Intervall, `shift(1).rolling(n)`, gleich für 50/25. |
| L2 Chandelier unklar | **GELÖST** (Rest siehe P8) | ATR rollierend, Auslösung intraday, Gap zum Open, Startreferenz = Fill-Preis. |
| L3 Keine Größe/kein R in Strategie 2 | **GELÖST** (Rest siehe P8) | R = 3×ATR14, 0,5 % Risiko pro Trade, höchstens 0,33× je Position und 1,0× gesamt. |
| L4 Keine Prioritätsregel | **GELÖST** | Erst nach RSI, dann nach IBS. Kein Pyramidisieren, keine Verdrängung, höchstens 1 US-Index. |

**Alle 9 Blocker sind inhaltlich geschlossen.**

## 2. Restrisiken bei Major-, Faktor-, Statistik- und Benchmark-Punkten

### Pflicht vor dem ersten Code (Textänderungen für v1.2)

**P1 – Einfrieren.** Die Datei ist noch nicht in Git eingecheckt. Das war meine ausdrückliche Bedingung für die Freigabe.

**P2 – Der Bootstrap-Test von Strategie 1 ist praktisch nicht zu bestehen.** Den Fehler habe ich in meinem Pre-Audit (Punkt 4b) selbst angelegt:
- Offen ist auch, ob der Test gegen beide Benchmarks bestanden werden muss (UND) oder gegen einen davon (ODER).
- Bei T ≈ 18,7 Jahren und einer Korrelation von etwa 0,6 zu 12-1-TSMOM liegt der Standardfehler der Sharpe-Differenz bei etwa 0,21. Für p < 0,05 bräuchte Strategie 1 also rund **+0,34 Sharpe Vorsprung**.
- Gegenüber Risk-Parity-Long-Only, das 2008–2020 von den Anleihen profitiert hat, wären es sogar rund **+0,5**.
- Damit ist das Ergebnis faktisch ein vorab feststehendes No-Go, oder es lädt dazu ein, das Kriterium später umzudeuten.
- **Vorschlag:** Go-relevant sind (a) eine absolute Überrendite-Sharpe mit Bootstrap-p < 0,05 über den Gesamtzeitraum (t ≈ 2,2 bei einer Sharpe von 0,55) und (b) ein positives Alpha bei Regression auf Risk-Parity-Long-Only (p < 0,05). Der Vergleich mit 12-1-TSMOM wird nur beschrieben: Punktschätzung der Differenz ≥ 0, p-Wert ausgewiesen.

**P3 – Go-relevante Benchmarks sind nicht genau beschrieben.** Für Risk-Parity-Long-Only und 12-1-TSMOM fehlen Volatilitäts-Lookback, Rebalancing-Takt, Long/Short-Regel, Ausführung und Kosten. Beim „SMA(200)-Halten“ in Strategie 2 ist die „gleiche Positionsbegrenzung“ offen: Welche 3 von 5 ETFs, welche Gewichte? Vorschlag: 1/σ60, monatlich, Signal zum Close, Ausführung zum nächsten Open, 10 bp Kosten. Für SMA-Halten gleichgewichtet über alle ETFs, die über ihrer SMA200 liegen.

**P4 – Das Kriterium für trendfeindliche Regime ist mehrdeutig.** Offen ist, welcher Benchmark gilt, über welches Fenster die Volatilität skaliert wird und ob „kumulierter Drawdown“ den maximalen Drawdown je Fenster oder die Summe meint. Vorschlag: Benchmark (1), Skalierung mit der Volatilität aus IS+Val, Prüfung je Fenster.

**P5 – Die 2×-Kosten-Regel widerspricht sich.** In §1.4 steht „alle Go-Kriterien … positiv bleiben“, in §2.3/§3.3 nur „Expectancy > 0“. Vorschlag: Bei 2× Kosten gilt Überrendite-Sharpe > 0, PF > 1,0 und Expectancy > 0.

**P6 – Die Short-Seite ist nicht geregelt.** Es fehlen der Zins auf Short-Erlöse und die Leihgebühr. Short FXY 2022–24 ist der Kern des Holdouts, und ohne Regel schwankt allein der Carry-Effekt um etwa 4–5 % p.a. Vorschlag: Short-Erlöse verzinsen sich mit T-Bill − 50 bp und zählen nicht als freies Cash.

**P7 – Was passiert, wenn das Hebel-Limit greift?** Bei S1 ≤ 2,0× wird das 2017–19 tatsächlich passieren: IEF, FXE und FXY ergeben schon etwa 1,4× nominal. Vorschlag: Eine neue Position wird auf die Restkapazität gekürzt. Bestehende Positionen werden auch bei Kursdrift nicht angepasst.

**P8 – Zwei Lücken in der Lookahead-Präzisierung:**
- S1: Steigt der Chandelier-Stop nur oder darf er wieder fallen? Und bleibt der Fill-Preis in `max(Fill, Close[Entry..t])`?
- S2: `ATR14(t_entry)` muss das **Signal-Bar t** sein. Zum Fill am Open(t+1) ist ATR14(t+1) noch unbekannt.

**P9 – Offene Trades an der Phasengrenze.** Festzulegen ist, dass Trades nach Einstiegsdatum zugeordnet werden, am Phasenende für die Statistik zum Mark-to-Market geschlossen gelten, und dass der Holdout-Lauf flach startet.

### Klarstellungen, die bis zum Öffnen der Validation reichen

- **Deflated Sharpe:** N = 10 ist zu niedrig. Tatsächlich sind es 22 oder mehr Konfigurationen: S1 9+1B+Krypto, S2 7+Close-Variante+2 Kontrollen, dazu das Ensemble. Außerdem muss feststehen, ob die DSR Go-relevant ist (dann > 0,95) oder nur beschrieben wird.
- **Ensemble:** Ist es Go-relevant oder nur beschreibend? Für die Tail-Korrelation fehlt eine Schwelle. Und weil S2 sehr niedrige Volatilität hat, läuft die Inverse-Vol-Gewichtung mit hoher Wahrscheinlichkeit sofort in das 2×-Limit. Ich empfehle, das Ensemble ausdrücklich als beschreibend zu führen.
- **Faktor-Klumpen:** Der Yen-Carry-Cluster (FXY short + EWJ long) und der USD-Cluster (FXE + FXY gleichzeitig short) sind durch die Cluster-Caps **nicht** begrenzt. Als bekanntes Restrisiko deklarieren; die Leave-2022-out-Auswertung fängt einen Teil davon ab.
- **Daten-Gate (D6, D9):** Es fehlt eine Rückfallregel für gesperrte Instrument-Jahre (gilt der Ausschluss auch für die Benchmarks?). Für den Abgleich mit Stooq fehlt die Toleranz, z. B. |Δ Tagesrendite| < 5 bp an ≥ 99 % der Tage.
- **Kleinigkeiten:**
  - Die RSI-Initialisierung umformulieren in „Mittel von max(Δ,0) bzw. max(−Δ,0) über die ersten N Änderungen“. Das ist wegen des Vorlaufs zahlenmäßig irrelevant.
  - Referenztest gegen TA-Lib ergänzen.
  - Bei der Nullhypothese von S2 „Monte-Carlo“ statt „Bootstrap/MC“ schreiben, mit denselben Caps.
  - Ein kurzer Power-Absatz fehlt noch.
  - KMLM/DBMF nur beschreibend ist wegen der kurzen Historie akzeptabel.
  - 10 bp für EWU und FXY 2008–12 sind optimistisch; der 2×-Kostentest deckt das ab.

## 3. End-Urteil

**BEDINGT FREIGEGEBEN.**

- **Daten-Check:** Freigegeben, sobald P1 erledigt ist, also v1.1 eingecheckt ist. Vorher werden die Toleranzen für D6/D9 nachgetragen.
- **Backtest-Implementierung:** Erst nach v1.2 mit **P2 bis P9** und neuem Commit, inklusive SHA256 der Daten. Das sind reine Textänderungen, keine neuen Hypothesen. P2 ist der wichtigste Punkt: Ohne die Korrektur wäre Strategie 1 rechnerisch zum Scheitern verurteilt, unabhängig davon, ob sie einen echten Edge hat.

`knowledge_base/opus_checkpoint1_v1_1_approval.md` ist noch leer. Soll ich dieses Urteil dort ablegen?
