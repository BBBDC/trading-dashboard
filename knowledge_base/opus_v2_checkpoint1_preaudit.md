Ich habe die Engine-Stellen geprüft, die v2.0 als Benchmark „identisch zu v1.2“ übernimmt. Hier ist der Checkpoint-1-Bericht.

# Checkpoint 1 (Pre-Audit) für Pre-Registration v2.0 `RP-Trend`

**Urteil: BEDINGT.** Die Hypothese ist sauber und sparsam gebaut: 2 Parameter, Literatur-Standard 12‑1, kein Hebel. Das Gate ist ehrlich. Bevor die erste Code-Zeile entsteht, müssen aber drei Engine-Konventionen und zwei Kontaminations-Hinweise in den Text. Neu gerechnet habe ich nichts, und Holdout-Daten habe ich nicht angefasst.

## 1. Daten-, Lookahead- und Berechnungslücken

**Schwer (ohne Fix verfälscht das Gate oder den Benchmark):**

- **L1: Die Ausführung im Text passt nicht zum Code.** Laut Text wird zum `Open(t+1)` ausgeführt. `run_benchmark_risk_parity_lo` (`engine.py:624-637`) rechnet am Tag t+1 aber die volle Close→Close-Rendite schon mit den neuen Gewichten. Faktisch ist das eine Ausführung zum `Close(t)`, also am selben Close wie das Signal. Weil die Open-Daten mit dem adjclose-Faktor angepasst sind (`data_prep.py:88-95`), ist der korrekte Split möglich. Er muss im Text stehen. Die 0,571 von v1.2 ändern sich dadurch leicht.
- **L2: Die Gewichte driften nicht.** Die Engine hält die Gewichte jeden Tag konstant. Das ist ein tägliches Rebalancing ohne Kosten und kein monatliches. Turnover und Kosten sind dadurch zu niedrig, und der Rebalancing-Effekt ist verzerrt. Das betrifft RP-Trend, RP Long-Only und 60/40 gleichermaßen.
- **L3: Cash-Bug.** `engine.py:642` löst ein Rebalancing aus, sobald `sum(weights) == 0`. Bei RP-Trend ist „alles in Cash“ ein regulärer Zustand. Wird die Logik wiederverwendet, handelt die Strategie in reinen Cash-Monaten täglich. Die Bedingung muss ein expliziter Erster-Tag-Flag werden.
- **L4: Der OLS-Standardfehler setzt unabhängige Renditen voraus** (`engine.py:756`). Bei täglichen Renditen mit Vola-Clustering und zeitvariablem Beta aus dem Timing ist das ungeeignet. Ohne vorab festgelegte HAC-Methode lässt sich nachträglich zwischen täglichen und monatlichen Daten und zwischen Lags wählen. Das ist ein Forking Path.

**Mittel (Text ist unterspezifiziert):**

- **L5: `CumTBillReturn` ist nicht definiert.** Offen sind die Indexgrenzen, die Verzinsung (zusammengesetzt oder addiert) und die Frage, welcher Tageszins gilt. Die Engine verzinst Tag t zudem mit dem IRX-Wert desselben Tages t (`engine.py:57-63, 637`). Das ist ein Lookahead von 1 Tag. Der Betrag ist vernachlässigbar, gehört aber ins Protokoll.
- **L6: Der Start schneidet das erste Signal ab.** `engine.py:620` überspringt alle Tage vor `start_date`. Das Signal vom 29.02.2008 entsteht deshalb nie, der Benchmark investiert erst ab dem 04.03. Dasselbe passiert beim Holdout-Start mit dem Signal vom 31.12.2021.
- **L7: Die Vola-Skalierung ist offen.** Es fehlen der Faktor k, die Kurve, auf der der DD gemessen wird (Total Return oder Excess), und für den Holdout die Herkunft von k. Wird k im Holdout ex post aus Holdout-Daten bestimmt, ist das ein Lookahead.
- **L8: Die Plateau-Zellen sind nicht in Handelstagen definiert.** Es ist auch nicht festgelegt, gegen welchen RP-Benchmark jede Zelle antritt (immer σ60 oder dasselbe σ-Fenster).
- **L9: Snapshot-Text und Manifest stimmen nicht überein.** Im Text steht „2007-02-15“. Laut Manifest beginnen die Daten am 2006-02-01, FXY am 2007-02-13. Das Manifest trägt außerdem noch `preregistration_version: v1.2`.
  - Der Vorlauf reicht trotzdem: Das erste Signal am 29.02.2008 braucht 252 Tage zurück, FXY hat etwa 10 Bars Reserve.
  - Die Hashes sollten vor dem Lauf per `assert` geprüft werden.

**Kontamination (lässt sich nicht beheben, muss aber offen deklariert werden):**

- **K1: Der Holdout ist technisch unberührt, inhaltlich aber nicht.** Die Hypothese ist ausdrücklich mit 2022 begründet. Außerdem hat der S2-Holdout-Lauf die Jahre 2022–2026 für SPY, QQQ, DIA, TLT und GLD schon gezeigt, einschließlich eines Trendfilter-Benchmarks (SMA200-Halten SR 0,559 über den Gesamtzeitraum). Damit ist das Drawdown-Kriterium im Holdout weitgehend vorhersehbar. Ende 2021 hatten Anleihen, FX und Gold bereits negativen 12‑1-Trend, RP-Trend geht also ohne den Großteil der Anleihen und FX in 2022. Als Beweis zählt im Holdout im Wesentlichen nur noch die Sharpe.
- **K2: IS+Val ist schon zum dritten Mal im Einsatz.** S1, die Variante 1B und das Plateau haben bereits gezeigt, dass langsamer Trend und nur Long besser abschneiden. Diese Erkenntnis steckt in diesem Design. 12‑1 ist zwar die Literatur-Spezifikation und nicht getunt, die p-Werte auf IS+Val sind aber trotzdem optimistisch.

## 2. Sind Gate und Go-Kriterien fair?

**Ist OLS-Alpha mit p < 0,05 gegen Risk-Parity ein verstecktes No-Go? Nein. Es ist aber das Kriterium, an dem die Strategie am ehesten scheitert, und es muss bleiben.**

- **Was es verlangt:**
  - Einseitig p < 0,05 heißt t ≥ 1,645.
  - Bei T ≈ 13,8 Jahren entspricht das einem Residual-IR ≥ 0,44.
  - Ein Beispiel, das reicht: etwa 1 % Alpha pro Jahr bei rund 2,3 % Residual-Vola.
- **Wie realistisch das ist:**
  - Trend-Overlays auf ihr eigenes Basisportfolio erreichen über lange Zeiträume typischerweise einen IR von etwa 0,2–0,4.
  - 2008–2021 enthält mehrere Phasen mit schnellen V-Erholungen und Whipsaws (2011, 2015/16, Q4 2018, März 2020).
  - Meine Schätzung: Selbst wenn der Effekt echt ist, besteht die Strategie dieses Kriterium mit etwa 25–40 % Wahrscheinlichkeit.
- **Warum es trotzdem bleiben muss:**
  - (a) Es ist das einzige Kriterium, das die Hypothese selbst testet, also echten Mehrwert gegenüber statischem RP. Ohne es prüft das Gate nur „weniger Risiko“, und das liefert Cash auch.
  - (b) Wegen K1 muss der unbelastete Zeitraum IS+Val die statistische Last allein tragen. Diese Hürde auf IS+Val abzusenken, weil man auf 2022 hofft, wäre genau die Selbsttäuschung, die wir verhindern wollen.
- **Was nötig ist:** eine sauber festgelegte Testmethode (L4). Die Hürde selbst bleibt.

**Die übrigen Gate-Kriterien:**

| # | Kriterium | Bewertung |
|---|---|---|
| 1 | SR ≥ 0,60 und > RP | Fair. Der Rückstand von RP-Trend auf RP muss aus derselben Engine stammen; die 0,571 sind nur ein Referenzwert. |
| 2 | Alpha p < 0,05 | Siehe oben: Das Kriterium bindet am stärksten und ist berechtigt. |
| 3 | Skalierter DD ≤ 0,75 × RP | Ehrgeizig, entspricht aber genau der Behauptung der Hypothese. Liegt der DD von RP (17,66 %) in einem schnellen Schock, kann ein monatlicher 12‑1-Filter ihn nicht abfangen. Dann scheitert die Hypothese zu Recht. |
| 4 | 2× Kosten SR > 0,45 | Bei monatlichem Turnover praktisch nicht bindend. Kann bleiben. |
| 5 | Plateau 9/9 | Fair. Die Zellen müssen nach L8 präzisiert werden. |

**Weitere Lücken bei Gate und Go-Kriterien:**

- „> 0,30 (mind. ≥ 50 %)“ ist mehrdeutig.
- Im Holdout fehlt eine Prüfung, ob die Strategie nur durch 2022 trägt (Leave-2022-out, schon in CP2 F4 offen).
- Es fehlt die Festlegung, dass nach einem GO zuerst ein prospektiver Shadow-Betrieb folgt (CP2 §4.3).
- Die Deflated Sharpe Ratio fehlt (CP2 F4).

Insgesamt besteht die Strategie das Gate wahrscheinlich nicht, selbst wenn der Effekt klein und echt ist. Das ist angesichts von K1 und K2 die richtige Kalibrierung und keine Selbsttäuschung, sollte aber so im Text stehen.

## 3. Exakte Textkorrekturen (Bedingung für die Freigabe)

**§1, an den Absatz „Hypothese“ anhängen:**
> **Kontaminations-Erklärung:** Die Hypothese ist mit Kenntnis des Bärenmarkts 2022 formuliert. Die Renditen 2022–2026 von SPY, QQQ, DIA, TLT und GLD sowie ein SMA200-Trendbenchmark wurden im S2-Holdout (`s2_holdout_report.json`) bereits gesehen. Das Design (langsamer Trend, nur Long) ist zudem durch die IS+Val-Ergebnisse von S1/1B informiert; IS+Val wird damit zum dritten Mal verwendet. Der Holdout ist nur technisch unberührt. Sein Drawdown-Kriterium gilt als schwacher Beleg, die Beweislast liegt beim IS+Val-Alpha.

**§1, Satz zu den Kosten ersetzen:**
> ~~„(~`10 bp` Kosten)“~~ → „(Kosten: `10 bp` Round-Turn je Einheit Turnover; erwartete Jahreskosten werden berichtet, nicht angenommen)“

**§2 Daten-Snapshot, ersetzen durch:**
> Unveränderter Snapshot `knowledge_base/audit_cache/` laut `snapshot_manifest.json` (Dateien ab `2006-02-01`, FXY ab `2007-02-13`, Ende `2026-11-20`). Vor jedem Lauf werden alle SHA256 per `assert` geprüft. Kalender = SPY-Handelstage. Fehlende Einzeltage werden mit dem Vortagswert fortgeschrieben; ihre Anzahl je ETF wird berichtet.

**§2 Rendite & Cash, ergänzen:**
> `rf_d(k) = max(0, IRX_close(k-1)) / 100 / 252` (Vortageswert, bei Lücken fortgeschrieben). Cash und Excess-Return für Tag k verwenden `rf_d(k)`.

**§3, neuer erster Punkt „Ausführungs- und Bewertungskonvention (gilt identisch für RP-Trend, RP Long-Only und 60/40)“:**
> - Signal und Zielgewichte am `Close(t)` des letzten Handelstags im Monat. Die Ausführung erfolgt zum `Open(t+1)`. Die Rendite von Tag t+1 ist `Σ w_alt,i·(O_i(t+1)/C_i(t) − 1)`, verkettet mit `Σ w_neu,i·(C_i(t+1)/O_i(t+1) − 1)` (O mit adjclose-Faktor angepasst). Die Kosten fallen zum Open(t+1) an.
> - Zwischen den Rebalancings driften die Gewichte (Buy-and-Hold). Turnover = `Σ_i |w_target,i − w_drift,i|`, Kosten = Turnover × 5 bp.
> - Erste Allokation: Signal am letzten Handelstag *vor* Periodenbeginn (`2008-02-29` bzw. `2021-12-31`), Ausführung zum ersten Open der Periode. Ein Rebalancing wird nur durch den Monatsend-Kalender ausgelöst, nie durch `Σw = 0`.
> - Alle Benchmarks werden mit dieser Engine neu berechnet. `0,571` / `17,66 %` dienen nur als Referenz.

**§3 Trend-Signal, ergänzen:**
> `CumTBillReturn[t-252 : t-21] = Π_{k=t-251}^{t-21} (1 + rf_d(k)) − 1` (zusammengesetzt, gleiches Intervall wie die Preisrendite). Indizes sind SPY-Handelstage. `Trend = 0` gilt als inaktiv.

**§3 Gewichtung, ergänzen:**
> `σ_V(i,t)`: Standardabweichung der einfachen täglichen adjclose-Renditen über `[t-V+1, t]` (ddof = 1) × √252, identisch zu `indicators.py:107`.

**§4.2 OLS, ersetzen durch:**
> OLS der täglichen Excess-Renditen von RP-Trend auf RP Long-Only (beide nach Kosten, gleiche Engine). Standardfehler nach Newey-West HAC mit Lag = 21, einseitiger Test `H0: α ≤ 0`, `p < 0,05`. Zusätzlich (nur Bericht): monatliche Regression mit NW-Lag 3 und Treynor-Mazuy-Spezifikation.

**§4.2, neuer Punkt:**
> **Max-DD-Definition:** Peak-to-Trough auf der täglich verketteten Kurve `Π(1 + rf + r_ex)`. Vola-skaliert: `Π(1 + rf + k·r_ex)` mit `k = σ(r_ex, Benchmark) / σ(r_ex, RP-Trend)`, beide auf IS+Val. Das auf IS+Val bestimmte k wird eingefroren und unverändert im Holdout verwendet.

**§4.2, neuer Punkt „Pflichtbericht, nicht Gate“:**
> Deflated Sharpe Ratio mit `N_trials = 12` (S1, 1B, S2 sowie die 9 Plateau-Zellen) und Kalenderjahres-Tabelle für RP-Trend, RP LO und 60/40.

**§4.2, `assert`-Klausel präzisieren:**
> `assert n_boot == 10_000` in `stationary_bootstrap_sharpe_p`. Der Standardwert 5000 (`engine.py:708`) wird entfernt. Seed = 42, `mean_block = 20`.

**§4.3 Punkt 5, ersetzen durch:**
> Plateau: `L/S ∈ {(189,0), (252,0), (252,21)}` × `V ∈ {40, 60, 90}` Handelstage. Jede Zelle erreicht `Excess-Sharpe ≥ 0,50` und einen vola-skalierten Max-DD unter dem von RP Long-Only mit *demselben* `V`.

**§4.3, Satz anhängen:**
> Scheitert ein Gate-Kriterium, lautet das Urteil NO_GO ohne Öffnung des Holdouts. Varianten dieser Spezifikation auf IS+Val sind danach ausgeschlossen.

**§4.4 Holdout, ersetzen durch:**
> **Holdout (`2022-01-03` – `2026-11-20`):** `Excess-Sharpe ≥ max(0,30; 0,5 × SR_IS+Val)` **UND** niedrigerer Max-DD (unskaliert sowie vola-skaliert mit eingefrorenem IS+Val-k) als RP Long-Only und 60/40 **UND** Leave-2022-out (`2023-01-01` – `2026-11-20`) `Excess-Sharpe > 0`.

**§4.4 No-Go-Regel, ergänzen:**
> Mit diesem einmaligen Öffnen ist der Holdout 2022–2026 für **alle** Trend- und Allokations-Hypothesen verbraucht. Auch ein GO führt nur zu 12 Monaten prospektivem Shadow-Betrieb ohne Kapital. Eine Live-Allokation erfordert eine eigene Pre-Registration.

## 4. End-Urteil

**BEDINGT.** Sobald die Korrekturen aus §3 wörtlich eingearbeitet sind und das Dokument als v2.1 eingefroren und committet ist (mit aktualisiertem `preregistration_version` im Manifest), ist die Spezifikation **FREIGEGEBEN FÜR IS+VAL**. Eine weitere Vorab-Runde ist nicht nötig. Die Engine-Fixes L1–L3 und L6 gehören in den ersten Commit, mit einem Unit-Test für einen Monat, in dem alles in Cash liegt (L3).

Diesen Bericht habe ich wie in CP2 nur hier ausgegeben. Soll ich ihn unter `knowledge_base/opus_v2_checkpoint1_preaudit.md` ablegen? Dort liegt bereits eine Datei mit diesem Namen, die ich vorher ansehen würde.
