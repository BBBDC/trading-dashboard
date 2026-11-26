# Urteil: NACHBESSERN

Keiner der drei Punkte ist sauber gelöst. Der wichtigste Befund: Das Shadow-Paper-Buch läuft derzeit überhaupt nicht.

## 1. Bugs und Inkonsistenzen

### P0: Blocker

**1. `shadow_paper_book.py` kann nicht importiert werden, Stufe 2 sammelt also weiterhin null Trades.**
- `shadow_paper_book.py:17` importiert `get_asset_friction` aus `circuit_breaker`. Diese Funktion gibt es dort nicht; im ganzen Repo kommt der Name nur in `shadow_paper_book.py` vor.
- Beide Aufrufe in `portfolio_engine.py` stehen in `try/except` und geben nur eine Warnung aus. Der Fehler fällt deshalb nicht auf.
- Ein weiteres Indiz: `knowledge_base/shadow_paper_portfolio.json` existiert nicht. `update_shadow_paper_book` würde die Datei bei jedem Lauf anlegen, auch bei leerem Buch. Die Datei fehlt allerdings auch dann, wenn der Portfolio-Lauf seit der Änderung noch gar nicht gelaufen ist.
- **Fix:** `get_asset_friction` auf Basis von `ASSET_FRICTION_DEFAULTS` anlegen. Vorsicht bei den Einheiten: Die Tabelle rechnet in Prozentpunkten (2·0,055 + 0,03 + 0,02 = 0,16), der Fallback in Zeile 160 in Anteilen (0,0016). Ohne Umrechnung durch 100 sind die Kosten in R 100-fach zu hoch. Den stummen `except` durch lautes Logging ersetzen und einen Import-Test ergänzen.

**2. Neuer Replay-Fehler im Inkubator: Break-Even wird rückwirkend angewendet.**
- `ai_incubator.py:1445-1446`: Bei jedem Zyklus werden alle Balken seit dem Einstieg erneut durchlaufen.
- `ai_incubator.py:853` setzt den Startwert aber auf `sl = trade["sl"]`. Nach einem TP1-Treffer ist dort schon der Einstiegskurs gespeichert.
- Szenario: Ein Balken *vor* dem TP1-Treffer fällt kurz unter den Einstieg (aber nicht bis zum ursprünglichen SL). Im nächsten Zyklus wird dieser Balken mit Stop = Einstieg geprüft. Ergebnis: `CLOSED_BE` mit einem `exit_timestamp`, der vor `tp1_time` liegt. Die alte Schutzabfrage `t > tp1_bar_ts` wurde entfernt.
- **Fix:** Den Lauf ohne gespeicherten Zustand neu rechnen (Start immer mit `sl = init_sl` und `tp1_reached = False`) oder `last_processed_ts` speichern.

**3. Das Exit-Modell des Shadow-Buchs ist weder „SL vor TP“ noch mit dem Backtest vergleichbar.**
- `shadow_paper_book.py:82-149` arbeitet nur mit dem aktuellen Kurs zum Zeitpunkt des Scans, etwa alle 30 Minuten. Ohne Hoch und Tief gibt es keine Reihenfolge innerhalb eines Balkens. Bei den Zellen `XYZ 15m`, `PG 15m/30m` und `TSLA 30m` werden SL-Berührungen innerhalb des Balkens übersehen (zu optimistisch) und TP1-Berührungen ebenso (zu pessimistisch). Die Richtung der Verzerrung ist unbekannt.
- Das Modell weicht außerdem vom Backtest ab, mit dem die Zellen validiert wurden:

| | Backtest (`backtest_matrix_engine.py:299-307`) | Shadow-Buch |
|---|---|---|
| Nach TP1 | Trailing-Stop mit 2×ATR | Nur Break-Even |
| Signal-Flip-Exit | Nein | Ja |
| Time-Stop | Nein | Ja |

- Damit ist der Test „Zelle nicht schlechter als ihr Backtest“ ungültig.
- **Fix:** Bei jedem Lauf die OHLC-Balken der Zell-Zeitebene seit dem letzten Update nachrechnen, mit *derselben* Exit-Funktion wie im Backtest (in ein gemeinsames Modul auslagern).

### P1: Abweichungen von meinem Review

**4. Die Zeitebene wird weiterhin per Textsuche bestimmt, jetzt sogar schlechter** (`portfolio_engine.py:1008-1013`).
- Die Textsuche überschreibt `primary_timeframe`, obwohl `market_evaluator` dieses Feld immer setzt.
- Gewonnen hat der erste Treffer in der Reihenfolge des Tupels, nicht der relevante. Ein 1D-Setup, dessen Begründung „4h-Divergenz“ erwähnt, wird als `4h` zugeordnet.
- Genau das war mein Kritikpunkt, inklusive des Verdachts zu TSLA und AMT.
- **Fix:** Die Textsuche nur noch als Fallback nutzen, wenn `primary_timeframe` fehlt.

**5. Das Shadow-Buch hängt am Zustand des Live-Buchs. Das führt zu Selektions-Bias und kleiner Stichprobe.**
- Shadow wird nicht protokolliert, wenn:
  - der Live-Circuit-Breaker greift (`is_halted`, Zeile 985),
  - das Live-Buch voll ist (985/996),
  - die Live-Kapazität pro Zeithorizont erreicht ist (1054),
  - das Symbol live bereits gehalten wird (990).
- Dazu kommen Grenzen im Shadow-Buch selbst:
  - `shadow_paper_book.py:215` nutzt `TRIAD_PILOT_CONFIG` mit 1,0R je Trade. Das heißt maximal 2 Trades je Cluster und 4 Trades insgesamt, verteilt auf 12 Zellen.
  - Zeile 212 erlaubt nur einen offenen Trade je Ticker. `PG 15m` blockiert damit `PG 30m`.
- **Fix:** Den Shadow-Zweig direkt hinter die Prüfung der Stufe und die Signal-Filter legen, vor alle Live-Kapazitätsgrenzen. Doppelte Trades nur je `cell_key` ausschließen. Heat-Verstöße als Flag `would_block_heat` mitloggen, statt den Trade zu verwerfen.

**6. Die Regeln sind während der Sammelphase nicht eingefroren.**
- Shadow-Kandidaten laufen durch `evaluate_candidate_against_post_mortem_rules` und den Scorecard-Filter (1037-1051).
- Beide hängen an den wöchentlich neu kalibrierten `opus_governor_params` und an der `setup_performance`/`category_performance` aus `trade_memory.json`.
- Das ist der Rückkanal, vor dem ich gewarnt habe: Das Ziel verschiebt sich während der Messung.
- **Fix:** Beim Eintritt einer Zelle in Stufe 2 einen Snapshot der Filter-Parameter speichern. Mindestens aber einen `gate_params_hash` an jeden Trade schreiben.

**7. Das Namespacing ist nur ein Etikett, kein Konsument filtert danach.**
- `portfolio_engine.py:1359-1363`: Die Axiome der `master_constitution` werden ohne Filter nach `scope` in den Live-Prompt eingefügt.
- `portfolio_engine.py:1405-1408`: Der Fallback `learnings[:3]` nimmt die neuesten Einträge, praktisch also Inkubator-Lehren.
- `opus_whitelist_auditor.py:747-760`: Die Gedächtnis-Synthese liest alle Learnings und reicht `scope`/`source_book` nicht einmal an Opus weiter.
- Der Rückkanal ist damit vollständig intakt: Inkubator → Axiome → Governor-Parameter → Filter für Live und Shadow.

**8. Der Auditor wertet pro Symbol aus, nicht pro Zelle** (`opus_whitelist_auditor.py:196-224`).
- Zeitebene, Richtung und Version werden ignoriert. `PG 15m` und `PG 30m` werden vermischt.
- `incubator_r` landet weiterhin neben den Shadow-Zahlen im Input für die Beförderung (Zeilen 316/341).
- **Fix:** Nach `cell_key` und `exit_model_version` abgleichen. Den Inkubator aus dem Beförderungs-Input entfernen.

**9. Die Exit-Variante `trail_05r_floor_r` misst nicht, was AX-06 wissen will** (`ai_incubator.py:817`).
- Nach TP1 gilt `best_p ≥ entry + 1,5R`. Daraus folgt `best_p − 1,5R ≥ entry`.
- Ab dem zweiten Balken nach TP1 liegt der Stop also *über* Break-Even. Diese Variante ist enger als BE, nicht lockerer. Die Frage hinter AX-06 („dem Runner Luft geben“) wird damit gar nicht getestet.
- Zusätzlich fehlt der Time-Stop in der Simulation. Bei `CLOSED_TIME` sind die Varianten deshalb nicht mit dem echten Ergebnis vergleichbar.
- **Fix:**
  - Stop = max(Einstieg − 0,5R, Hoch − k·ATR) mit k = 2–3.
  - Time-Stop in die Simulation aufnehmen.
  - Prüfen, dass `be_after_tp1_r == realized_r` gilt.

### P2: Kleinere Punkte

- **Falsche Versions-Etiketten:** `ai_incubator.py:1002-1003` stempelt auch Trades, die vor der Änderung eröffnet wurden, als `v2` / `conservative_sl_first_v1`. Bei diesen alten Trades greift der Fallback in Zeile 852 außerdem auf `trade["sl"]` zurück. Steht der schon auf Break-Even, ist `init_sl` falsch und die Varianten sind wertlos.
- **Gelockertes Kosten-Gate:** `ai_incubator.py:67` erhöht `max_cost_r_ratio` von 0,20 auf 0,25. Das habe ich nicht empfohlen. Es verändert, welche Trades überhaupt zustande kommen, braucht also mindestens einen Versionssprung.
- **Heat wird nicht frei:** `open_risk_r: 0.5` ist fest gesetzt (Zeilen 616/750). Auch nach Break-Even wird das Risiko nicht freigegeben. Das ist konservativ, aber es verschenkt Slots.
- **Shadow-Buch:**
  - Zeile 221: Fallback-Preis `100.0` erzeugt bei fehlendem Kurs einen Unsinns-Trade.
  - Zeile 180: Nur die letzten 500 Trades werden behalten, ältere fallen aus der Statistik. Besser in ein Archiv schreiben.
- **Referenz-Backtest selbst zu optimistisch:** In `backtest_matrix_engine.py:299-310` wird TP1 mit sofortigem Break-Even *vor* dem SL im selben Balken geprüft. Der Maßstab für Hebel 3 ist damit nach oben verzerrt.

## 2. Status der drei Kritikpunkte

| Punkt | Status |
|---|---|
| Shadow-Paper im Live-Signalweg | **Nicht gelöst.** Läuft wegen des Import-Fehlers nicht. Auch nach der Reparatur hängt es am Live-Zustand (Punkt 5), hat ein anderes Exit-Modell als der Backtest (Punkt 3) und keine eingefrorenen Regeln (Punkt 6). |
| Inkubator-Trennung / Namespacing | **Nicht gelöst.** 5m ist zwar abgeschaltet, aber der Rückkanal in Live- und Shadow-Filter besteht weiter (Punkte 7 und 8). |
| SL vor TP + paralleles Exit-Tracking | **Teilweise.** Die Reihenfolge innerhalb eines Balkens und die Gap-Logik im Inkubator stimmen. Der Replay-Fehler (Punkt 2) macht das aber wieder kaputt. Die Varianten sind falsch spezifiziert (Punkt 9). |

## 3. Reihenfolge der Nachbesserung

1. **P0:** Punkte 1 bis 3 beheben, dazu Punkt 4. Ohne korrekte Zuordnung der Zeitebene landet das Shadow-Buch in den falschen Zellen.
2. **Vor dem ersten gezählten Shadow-Trade:** Punkte 5 bis 8. Danach die Kriterien für die Beförderung schriftlich festlegen.
3. **Danach:** Punkt 9 und die P2-Punkte.

Was ich geprüft habe: Ich habe den Code gelesen und per grep gesucht. Den Import-Test (`python3 -c "import shadow_paper_book"`) hast du nicht freigegeben, er lief also nicht. Dass `get_asset_friction` fehlt, ist trotzdem eindeutig: Es gibt keine Definition, und die Shadow-Datei existiert nicht. Die neuen Opus-Exit-Doctor-Teile im Diff habe ich nur am Rand angeschaut. Sie ändern Stop-Loss und Take-Profit der Live-Trades von Lauf zu Lauf unterschiedlich, und genau dieses Live-Exit-Modell soll das Shadow-Buch eigentlich messen.
