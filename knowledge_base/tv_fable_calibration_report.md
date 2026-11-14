**Kurzfassung:** Die Bänder, Buy Area, Sell Area und No Trade Zone sind entschlüsselt. Good/Potential Buy, Good Sell und die Alignment-Signale konnte ich nicht herleiten, und die Order-Block-Regel ist nur eine gut gestützte Hypothese. Python, awk und Schreibzugriffe waren in dieser Session gesperrt: Alles unten ist per Hand an einzelnen Zeilen der CSVs in `tv_exports/` nachgerechnet (Genauigkeit etwa 1e-3), der Code ist ungetestet.

## 1. Upper/Lower Band

Es ist kein Range Filter, sondern ein Donchian-Kanal plus ATR-Aufschlag:

```pine
atr = ta.rma(ta.tr(true), 14)            // Wilder-ATR, Länge 14 (nicht 13)
UB  = ta.highest(high, 5) + 1.8 * atr
LB  = ta.lowest(low, 5)   - 1.8 * atr
```

- **Mitte:** `(UB+LB)/2` ist der Mittelpunkt aus höchstem Hoch und tiefstem Tief der letzten 5 Bars. Deshalb bleibt sie konstant, solange beide Extreme im Fenster bleiben, und `d(UB) = -d(LB)` ist dann die reine ATR-Änderung.
- **Fensterlänge 5:** BTC 4h Bar 9 enthält noch das Tief 58800 von Bar 5, Bar 10 nicht mehr.
- **ATR-Länge 14:** BTC 4h Bars 16–19 ergeben ATR 797.409 → 848.063 → 854.451 → 836.393, was exakt `atr[i-1] + (TR - atr[i-1])/14` entspricht; Länge 13 passt nicht.
- **Gegenprobe:** AMZN 1D Bars 4, 5, 9, 12 und BTC 1D Zeilen 139/140 stimmen ebenfalls.
- **Offen:** Wie 5 und 14 aus dem Input 13 entstehen (z. B. `round(13·0.382)` und `13+1`), lässt sich aus einem einzigen Parametersatz nicht bestimmen. Ein Export mit Lookback 21 würde das klären.
- **Warm-up:** Der Export beginnt mitten im Chart, die ATR hat dort schon Historie. Für den Abgleich die ATR aus TradingView seeden (`atr[4] = (UB[4] - max(high[0..4]))/1.8`) oder die ersten rund 300 Bars ignorieren.

Die bestehende Engine rechnet `EMA(13) ± 1.8·ATR(13)` und RFE mit EMA und 1.5·σ; beides ist falsch.

## 2. Signale

| Signal | Regel | Status |
|---|---|---|
| Buy Area | `low < RFE_Lower and high[1] > RFE_Lower` (Vorbar-Hoch gegen den aktuellen Wert) | Erklärt alle 26 geprüften BTC-1D-Bars 113–138 und rund 90 SOL-1D-Bars, inklusive der Ausnahmen |
| Sell Area | `high > RFE_Upper` | Bestätigt an BTC 1D; der symmetrische Zusatz `low[1] < RFE_Upper` ist plausibel, aber nicht trennscharf geprüft |
| No Trade Zone | `(low < Basis and high[1] > Basis) or (high > Basis and low[1] < Basis)` | Bestätigt an BTC 1D Bars 76–100 und AMZN 1D Bars 0–14 |
| Good/Potential Buy, Good Sell | nicht hergeleitet | Rund 50 Ereignisse in 11 Dateien |
| Bull/Bear Alignment Ends | nicht hergeleitet | Vermutlich ein MA-Stack; RFE-Basis-Kreuzung scheidet aus |

Ausgeschlossen für die Buy/Sell-Signale habe ich RSI-30-Kreuzung, Engulfing, neues 5-Bar-Tief und Kreuzung der Bandmitte; jede dieser Regeln scheitert an mindestens einem Fall. Hier hilft nur ein automatischer Regel-Scan.

## 3. Order Blocks (Hypothese)

- **Bearish OB:** eine grüne Kerze, auf die 5 rote Kerzen in Folge schließen; markiert wird rückwirkend die grüne Kerze. Bullish OB spiegelbildlich.
- **Beleg:** In BTC 4h Zeilen 2–130 gibt es genau eine solche Stelle und genau ein Signal. Alle 19 OB-Zeilen in BTC 4h haben die richtige Kerzenfarbe, und drei Folgesequenzen (Zeilen 11, 705, 821) sowie AMZN Bar 7 passen.
- **Sweep:** ersetzt das OB-Flag, wenn das Hoch der OB-Kerze das höchste Hoch der letzten N Bars übertrifft (bullish: Tief unter dem tiefsten Tief). Aus BTC 4h folgt N ≥ 19, weil Zeile 763 kein Sweep ist, Zeile 694 aber schon. Im Code steht N = 20 als Annahme.
- **Nicht geprüft:** eine mögliche Mindestbewegung.

## 4. Python (ungetestet)

```python
import math
from typing import List, Dict, Any, Optional

def _rma(v: List[float], n: int, seed: Optional[float] = None, seed_idx: int = 0):
    out = [None] * len(v)
    if seed is not None:
        out[seed_idx] = seed; start = seed_idx + 1
    else:
        if len(v) < n: return out
        out[n - 1] = sum(v[:n]) / n; start = n
    for i in range(start, len(v)):
        out[i] = (out[i - 1] * (n - 1) + v[i]) / n
    return out

def calculate_degencoder_bands_v2(bars, donchian_len=5, mult=1.8, atr_len=14,
                                  rfe_len=233, rfe_mult=1.618,
                                  atr_seed=None, atr_seed_idx=0) -> Dict[str, Any]:
    n = len(bars)
    h = [float(b["h"]) for b in bars]; l = [float(b["l"]) for b in bars]
    c = [float(b["c"]) for b in bars]
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
                          for i in range(1, n)]
    atr = _rma(tr, atr_len, atr_seed, atr_seed_idx)
    ub, lb, rb, ru, rl = ([None] * n for _ in range(5))
    wsum = rfe_len * (rfe_len + 1) / 2.0
    for i in range(n):
        if i >= donchian_len - 1 and atr[i] is not None:
            ub[i] = max(h[i - donchian_len + 1:i + 1]) + mult * atr[i]
            lb[i] = min(l[i - donchian_len + 1:i + 1]) - mult * atr[i]
        if i >= rfe_len - 1:
            w = c[i - rfe_len + 1:i + 1]
            wma = sum(x * (k + 1) for k, x in enumerate(w)) / wsum
            m = sum(w) / rfe_len
            sd = math.sqrt(sum((x - m) ** 2 for x in w) / rfe_len)
            rb[i], ru[i], rl[i] = wma, wma + rfe_mult * sd, wma - rfe_mult * sd
    return {"series": {"upper_band": ub, "lower_band": lb, "atr": atr,
                       "rfe_basis": rb, "rfe_upper": ru, "rfe_lower": rl}}

def detect_degencoder_signals_v2(bars, bands) -> Dict[str, List[bool]]:
    s = bands["series"]; n = len(bars)
    out = {k: [False] * n for k in ("buy_area", "sell_area", "no_trade_zone")}
    for i in range(1, n):
        if s["rfe_basis"][i] is None: continue
        hi, lo = float(bars[i]["h"]), float(bars[i]["l"])
        ph, pl = float(bars[i-1]["h"]), float(bars[i-1]["l"])
        b, u, d = s["rfe_basis"][i], s["rfe_upper"][i], s["rfe_lower"][i]
        out["buy_area"][i] = lo < d and ph > d
        out["sell_area"][i] = hi > u            # ggf. "and pl < u" – ungeprüft
        out["no_trade_zone"][i] = (lo < b and ph > b) or (hi > b and pl < b)
    return out

def detect_degencoder_obs_v2(bars, periods=5, sweep_len=20):
    """Hypothese: N Folgekerzen in Gegenrichtung; sweep_len ist eine Annahme (>=19)."""
    n = len(bars); res = {k: [False] * n for k in
                          ("bull_ob", "bear_ob", "bull_sweep", "bear_sweep")}
    o = [float(b["o"]) for b in bars]; c = [float(b["c"]) for b in bars]
    h = [float(b["h"]) for b in bars]; l = [float(b["l"]) for b in bars]
    for i in range(sweep_len, n - periods):
        nxt = range(i + 1, i + 1 + periods)
        if c[i] > o[i] and all(c[k] < o[k] for k in nxt):
            sw = h[i] > max(h[i - sweep_len:i])
            res["bear_sweep" if sw else "bear_ob"][i] = True
        if c[i] < o[i] and all(c[k] > o[k] for k in nxt):
            sw = l[i] < min(l[i - sweep_len:i])
            res["bull_sweep" if sw else "bull_ob"][i] = True
    return res
```

## Nächster Schritt

Gib Python-Ausführung und Schreibrechte in `trading/` frei. Dann prüfe ich die Funktionen gegen alle 11 CSVs auf 1e-6 und suche die fehlenden Regeln (Good/Potential Buy, Good Sell, Alignment, Sweep-N) automatisch.