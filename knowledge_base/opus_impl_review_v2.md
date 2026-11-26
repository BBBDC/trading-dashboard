# Urteil: NACHBESSERN

P0 #1–3 und P1 #4–6, #8 und #9 sind sauber umgesetzt. Das Exit-Modell im Schattenbuch stimmt Zeile für Zeile mit `backtest_matrix_engine.py:298-394` überein: TP1, dann BE plus Trailing mit 2.0·ATR14, dann SL mit Gap-Fill, dann TP2. Die Zeitstempel sind durchgehend in Sekunden, die Signaturen von `get_cached_bars`, `fetch_bars_direct` und `check_cluster_heat_limit(candidate_risk_r=…)` stimmen, und `_live_stats_for_symbols` filtert korrekt nach `cell_key` und `exit_model_version`.

Zwei Punkte verhindern die Freigabe. Beide lassen sich klein beheben.

## Muss behoben werden

**1. Noch nicht geschlossene Kerzen werden verarbeitet und danach nie wieder angefasst** (`shadow_paper_book.py:173-177`)
- Die Lader liefern die gerade laufende Kerze mit, ich finde keinen Filter dagegen.
- Das Schattenbuch wertet diese Kerze mit unvollständigem High/Low aus, setzt `last_processed_ts = bt` und überspringt sie danach dauerhaft.
- Bei 15m/30m-Zellen und einem Update-Zyklus von etwa 30 Minuten trifft das fast jeden Zyklus genau eine Kerze. SL-, TP1- und TP2-Berührungen im restlichen Teil dieser Kerze gehen verloren. Die Statistik im Schattenbuch, auf der die Beförderung beruht, ist damit systematisch verzerrt.
- Fix: Nur Kerzen verarbeiten, für die gilt `bt + tf_seconds(tf) <= now_ts`, und `last_processed_ts` nur für diese setzen.

**2. P1 #7 ist nur teilweise erledigt** (`ai_incubator.py:1125-1187`)
- Nur `new_learning` hat `scope`/`source_book` bekommen.
- `new_cross` (Cross-Market-Heuristik) und `new_axiom` (Opus-Meilenstein-Axiome) stammen ebenfalls aus Inkubator-Trades, sind aber nicht markiert. Laut eigener Kategorie sind sie sogar ausdrücklich als „4h/1D Transfer“ gedacht.
- Deshalb kommen sie ungefiltert über `get_memory_summary_for_ai_prompt` in den Live-Prompt. Genau diese Vermischung sollte #7 verhindern.
- Fix: Beide mit `scope: "INCUBATOR"` und `source_book: "INCUBATOR_RESEARCH"` markieren.

## Sollte mitbehoben werden (kein Blocker für sich allein)

**3. Erfundene SL/TP-Werte im Schatten-Durchlauf** (`portfolio_engine.py:591-593`)
- Fehlen `stop_loss`/`take_profit_*`, setzt der Code ±5 % / ±5 % / ±10 % ein. Das ergibt TP1 = 1R und hat mit der Geometrie aus dem Backtest (Swing-SL, TP1 ≥ 1.2R) nichts zu tun. Auch das Kosten-Gate rechnet dann mit einem fiktiven Stop.
- Fix: Kandidaten ohne echte Level einfach überspringen statt Werte zu erfinden.

**4. Inkubator-Learnings werden beim Schreiben gelöscht** (`portfolio_engine.py:1343`)
- `record_learning_in_memory` filtert beim Schreiben. Dadurch fliegen bei jedem geschlossenen Live-Trade alle Inkubator-Learnings dauerhaft aus `trade_memory.json`.
- Das Herausfiltern beim Lesen (Prompt, Auditor) reicht völlig aus. Den Filter beim Schreiben entfernen, sonst wächst das Lern-Archiv des Inkubators nie.

## Bekannt, nur notieren (P2, nächste Version des Exit-Modells)

- **Gleiche Kerze, optimistische Reihenfolge, in Backtest und Schattenbuch gleichermaßen:** TP1 und Trailing werden vor dem SL-Check derselben Kerze ausgewertet. Eine Kerze mit `l ≤ init_sl` und `h ≥ tp1` wird so als ≈ +0.75R statt −1R gebucht. Die Parität ist erfüllt, aber die Bezeichnung `sl_first` stimmt nur für TP2. Wenn das korrigiert wird, dann in beiden Dateien gleichzeitig und als `…_v2`.
- `_fetch_ohlc_for_shadow` verschluckt Ausnahmen stillschweigend (`:110`, `:117`) und holt pro offenem Trade und Zyklus mit `force_refresh=True` neu, was viele API-Aufrufe erzeugt.
- Die Metriken und `_live_stats_for_symbols` sehen nach dem Archivieren nur die letzten 500 geschlossenen Trades. Für die Beförderungsstatistik sollte das Archiv mit einbezogen werden.
- Inkubator-`realized_r` wird brutto ohne Reibung gebucht, das Schattenbuch dagegen netto. Diese Zahlen also nicht direkt vergleichen.

**Zur Freigabe:** Nach den Fixes 1 und 2, idealerweise auch 3 und 4, reicht ein kurzer Unit-Test: eine laufende Kerze wird nicht verarbeitet, und Cross- und Axiom-Learnings tauchen nicht im Live-Prompt auf. Dann ist von meiner Seite **FREIGEGEBEN**.

Ich habe die eingefügte Datei und das Diff gelesen und gegen den Repo-Code geprüft (Backtest-Engine, Daten-Lader, Heat-Limit, Auditor, Inkubator-Learnings). Ausgeführt habe ich nichts.
