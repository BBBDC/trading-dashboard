#!/usr/bin/env python3
"""
causal_filter_engine.py — Kausalitäts-Filter (No-Trade Rules) für den AI-Incubator
==================================================================================

Vier deterministische Veto-Filter, die VOR einer Ordererteilung geprüft werden:

  1. check_htf_alignment          Trendfolge: Trade nur in Richtung des HTF-Regimes
                                  (Preis vs. WMA233 UND RSI vs. 50 müssen übereinstimmen).
  2. check_vsa_volume_expansion   Breakouts nur mit relativem Volumen >= 1.25x (Ø 20 Bars).
  3. check_atr_noise_floor        Stop-Abstand >= 1.2x ATR(14).
  4. evaluate_setup_causality     Aggregation -> (is_approved, rejection_reasons, causality_score)

Grundsätze:
  * Fail-closed: fehlende, nicht-finite oder nicht-positive Eingaben führen zur Ablehnung.
  * Reine Funktionen ohne Seiteneffekte; keine Abhängigkeiten außerhalb der Stdlib.
  * Der Backtest rekonstruiert den Marktkontext strikt point-in-time (nur Bars, die zum
    Entscheidungszeitpunkt bereits geschlossen waren) aus Binance-/Yahoo-Historie.

WICHTIG zur Interpretation von backtest_filter_improvement():
  Das Ergebnis ist eine In-Sample-Filterung bereits bekannter Trades. Es zeigt, welche
  Trades die Filter verworfen hätten — es ist KEIN Out-of-Sample-Nachweis eines Edges.
  Konfidenzintervalle werden deshalb immer mit ausgegeben.

Aufruf:  python3 causal_filter_engine.py            (Selbsttest + Backtest)
         python3 causal_filter_engine.py --offline  (nur vorhandenen Bar-Cache nutzen)
"""

from __future__ import annotations

import json
import math
import random
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

BASE_DIR = Path(__file__).resolve().parent
KB_DIR = BASE_DIR / "knowledge_base"
INCUBATOR_FILE = KB_DIR / "incubator_trades.json"
BAR_CACHE_DIR = KB_DIR / "ohlcv_cache"          # *.json dort ist per .gitignore ausgeschlossen
BAR_CACHE_PREFIX = "CAUSALBT_"

# ------------------------------------------------------------------------------
# Schwellenwerte (bewusst als Konstanten: nicht an den 200 Trades optimiert)
# ------------------------------------------------------------------------------
HTF_WMA_PERIOD = 233
HTF_RSI_PERIOD = 14
HTF_RSI_MIDLINE = 50.0
ALLOW_NEUTRAL_HTF = False        # False = strikt: bei gemischtem HTF-Bild wird gar nicht gehandelt
MIN_BREAKOUT_RVOL = 1.25
VOLUME_AVG_PERIOD = 20
BREAKOUT_LOOKBACK = 20           # Donchian-Fenster zur Breakout-Erkennung im Backtest
MIN_STOP_ATR_MULT = 1.2
ATR_PERIOD = 14

SCORE_WEIGHTS = {"htf_alignment": 0.40, "vsa_volume": 0.30, "atr_noise_floor": 0.30}

HTF_FOR_LTF = {"5m": "1h", "15m": "1h"}
TF_SECONDS = {"5m": 300, "15m": 900, "1h": 3600}
MAX_STALE_SECONDS = 4 * 86400     # letzte geschlossene LTF-Kerze darf höchstens so alt sein (Wochenende/Feiertag)


# ==============================================================================
# 0. HILFSFUNKTIONEN
# ==============================================================================

def _num(x: Any) -> float:
    """Konvertiert robust nach float; alles Ungültige wird NaN (-> fail-closed)."""
    if isinstance(x, bool) or x is None:
        return math.nan
    try:
        v = float(x)
    except (TypeError, ValueError):
        return math.nan
    return v if math.isfinite(v) else math.nan


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass
class FilterResult:
    """Ergebnis eines Einzel-Filters."""
    name: str
    passed: bool
    reason: str = ""                      # leer bei Freigabe
    score: float = 0.0                    # 0..1 (Qualität der Bestätigung, 0 bei Ablehnung)
    applicable: bool = True               # False = Filter greift für dieses Setup nicht
    metrics: Dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.passed


# ==============================================================================
# 1. DIE VIER KAUSALITÄTS-FILTER
# ==============================================================================

def classify_htf_regime(current_price: Any, htf_wma233: Any, htf_rsi: Any) -> str:
    """
    BULLISH  <=> Preis > WMA233  UND  RSI > 50
    BEARISH  <=> Preis < WMA233  UND  RSI < 50
    NEUTRAL  sonst (Trend und Momentum widersprechen sich)
    INVALID  bei ungültigen Eingaben
    """
    p, w, r = _num(current_price), _num(htf_wma233), _num(htf_rsi)
    if not (p > 0 and w > 0 and 0.0 <= r <= 100.0):
        return "INVALID"
    if p > w and r > HTF_RSI_MIDLINE:
        return "BULLISH"
    if p < w and r < HTF_RSI_MIDLINE:
        return "BEARISH"
    return "NEUTRAL"


def check_htf_alignment(direction: str, current_price: float, htf_wma233: float,
                        htf_rsi: float,
                        allow_neutral: Optional[bool] = None) -> FilterResult:
    """
    Striktes Trendfolge-Filter.

      LONG  erlaubt  <=>  HTF-Regime BULLISH
      SHORT erlaubt  <=>  HTF-Regime BEARISH
      NEUTRAL: Ablehnung (ALLOW_NEUTRAL_HTF=False) — kein Long gegen bearishen HTF,
               kein Short gegen bullishen HTF gilt in jedem Fall.
               allow_neutral kann z.B. für Micro-Paper-Trading-Laboratorien aktiviert werden.
    """
    effective_allow_neutral = ALLOW_NEUTRAL_HTF if allow_neutral is None else bool(allow_neutral)
    name = "htf_alignment"
    d = str(direction or "").strip().upper()
    if d not in ("LONG", "SHORT"):
        return FilterResult(name, False, f"HTF: ungültige Richtung '{direction}'")

    regime = classify_htf_regime(current_price, htf_wma233, htf_rsi)
    if regime == "INVALID":
        return FilterResult(name, False, "HTF: WMA233/RSI/Preis fehlen oder sind ungültig (fail-closed)",
                            metrics={"regime": regime})

    p, w, r = _num(current_price), _num(htf_wma233), _num(htf_rsi)
    dist_pct = (p / w - 1.0) * 100.0
    metrics = {"regime": regime, "price_vs_wma233_pct": round(dist_pct, 3), "htf_rsi": round(r, 2)}
    wanted = "BULLISH" if d == "LONG" else "BEARISH"

    if regime == wanted:
        score = 0.5 + 0.25 * _clip01(abs(dist_pct) / 2.0) + 0.25 * _clip01(abs(r - HTF_RSI_MIDLINE) / 20.0)
        return FilterResult(name, True, score=score, metrics=metrics)

    if regime == "NEUTRAL":
        if effective_allow_neutral:
            return FilterResult(name, True, score=0.25, metrics=metrics)
        return FilterResult(
            name, False,
            f"HTF neutral: Preis {dist_pct:+.2f}% vs WMA233, RSI {r:.1f} — kein bestätigter Trend für {d}",
            metrics=metrics)

    return FilterResult(
        name, False,
        f"HTF {regime}: {d} gegen den Trend (Preis {dist_pct:+.2f}% vs WMA233, RSI {r:.1f})",
        metrics=metrics)


def check_vsa_volume_expansion(current_volume: float, avg_volume_20: float,
                               is_breakout: bool) -> FilterResult:
    """
    Kein Breakout-Trade ohne Volumenexpansion:  RVOL = current_volume / avg_volume_20 >= 1.25.
    Bei is_breakout=False greift die Regel nicht (applicable=False, passed=True).
    """
    name = "vsa_volume"
    cv, av = _num(current_volume), _num(avg_volume_20)
    rvol = cv / av if (cv >= 0 and av > 0) else math.nan
    metrics = {"rvol": round(rvol, 3) if math.isfinite(rvol) else None, "is_breakout": bool(is_breakout)}

    if not is_breakout:
        return FilterResult(name, True, score=0.0, applicable=False, metrics=metrics)
    if not math.isfinite(rvol):
        return FilterResult(name, False, "VSA: Volumendaten fehlen oder Ø-Volumen = 0 (fail-closed)",
                            metrics=metrics)
    if rvol >= MIN_BREAKOUT_RVOL:
        score = 0.5 + 0.5 * _clip01((rvol - MIN_BREAKOUT_RVOL) / MIN_BREAKOUT_RVOL)
        return FilterResult(name, True, score=score, metrics=metrics)
    return FilterResult(name, False,
                        f"VSA: Breakout ohne Volumenexpansion (RVOL {rvol:.2f}x < {MIN_BREAKOUT_RVOL:.2f}x)",
                        metrics=metrics)


def check_atr_noise_floor(entry_price: float, stop_loss: float, atr_14: float) -> FilterResult:
    """Stop-Abstand |entry - stop| muss >= 1.2 x ATR(14) sein."""
    name = "atr_noise_floor"
    e, s, a = _num(entry_price), _num(stop_loss), _num(atr_14)
    if not (e > 0 and s > 0 and a > 0):
        return FilterResult(name, False, "ATR: Entry/Stop/ATR fehlen oder sind ungültig (fail-closed)")
    dist = abs(e - s)
    ratio = dist / a
    metrics = {"stop_distance": dist, "stop_atr_multiple": round(ratio, 3)}
    if dist <= 0:
        return FilterResult(name, False, "ATR: Stop-Abstand ist 0", metrics=metrics)
    # Toleranz gegen Float-Rundung exakt an der Schwelle
    if ratio >= MIN_STOP_ATR_MULT - 1e-9:
        score = 0.5 + 0.5 * _clip01((ratio - MIN_STOP_ATR_MULT) / MIN_STOP_ATR_MULT)
        return FilterResult(name, True, score=score, metrics=metrics)
    return FilterResult(name, False,
                        f"ATR: Stop im Rauschen ({ratio:.2f}x ATR < {MIN_STOP_ATR_MULT:.1f}x ATR)",
                        metrics=metrics)


def _initial_stop(setup: Dict[str, Any]) -> float:
    """
    Ursprünglicher Stop. 'risk_amount' hat Vorrang, weil der Incubator 'sl' nach TP1
    auf Break-Even nachzieht (sl == entry) und der Initial-Stop sonst verloren wäre.
    """
    entry = _num(setup.get("entry_price"))
    risk = _num(setup.get("risk_amount"))
    d = str(setup.get("direction", "")).upper()
    if entry > 0 and risk > 0 and d in ("LONG", "SHORT"):
        return entry - risk if d == "LONG" else entry + risk
    sl = setup.get("sl", setup.get("stop_loss"))
    return _num(sl)


def run_filters(setup_candidate: Dict[str, Any], market_context: Dict[str, Any]) -> List[FilterResult]:
    """Führt die drei Einzel-Filter aus und liefert die Detail-Ergebnisse."""
    setup = setup_candidate or {}
    ctx = market_context or {}
    direction = setup.get("direction")
    entry = setup.get("entry_price")
    price = ctx.get("current_price", entry)
    is_breakout = bool(setup.get("is_breakout", ctx.get("is_breakout", False)))
    allow_neutral = ctx.get("allow_neutral_htf", None)
    return [
        check_htf_alignment(direction, price, ctx.get("htf_wma233"), ctx.get("htf_rsi"), allow_neutral=allow_neutral),
        check_vsa_volume_expansion(ctx.get("current_volume"), ctx.get("avg_volume_20"), is_breakout),
        check_atr_noise_floor(entry, _initial_stop(setup), ctx.get("atr_14")),
    ]


def evaluate_setup_causality(setup_candidate: Dict[str, Any],
                             market_context: Dict[str, Any]) -> Tuple[bool, List[str], float]:
    """
    Fasst alle Filter zusammen.

    setup_candidate: direction, entry_price, sl (oder stop_loss) / risk_amount, optional is_breakout
    market_context : htf_wma233, htf_rsi, current_volume, avg_volume_20, atr_14,
                     optional current_price (Default: entry_price), optional is_breakout

    Rückgabe: (is_approved, rejection_reasons, causality_score)
      is_approved      True nur, wenn KEIN Filter ablehnt.
      causality_score  0..100, gewichtetes Mittel der Filter-Scores über die anwendbaren
                       Filter (abgelehnter Filter = 0). Reines Ranking-Maß, kein Wahrscheinlichkeitswert.
    """
    results = run_filters(setup_candidate, market_context)
    reasons = [r.reason for r in results if not r.passed]
    w_sum = sum(SCORE_WEIGHTS[r.name] for r in results if r.applicable)
    score = 100.0 * sum(SCORE_WEIGHTS[r.name] * r.score for r in results if r.applicable) / w_sum if w_sum else 0.0
    return (not reasons, reasons, round(score, 1))


# ==============================================================================
# 2. INDIKATOREN (TradingView-kompatibel: ta.wma, ta.rsi, ta.atr)
# ==============================================================================

def wma_last(values: Sequence[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    window = values[-period:]
    return sum(v * (i + 1) for i, v in enumerate(window)) / (period * (period + 1) / 2.0)


def rsi_wilder_last(closes: Sequence[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(1, period + 1):
        ch = closes[i] - closes[i - 1]
        gains += max(ch, 0.0)
        losses += max(-ch, 0.0)
    ag, al = gains / period, losses / period
    for i in range(period + 1, len(closes)):
        ch = closes[i] - closes[i - 1]
        ag = (ag * (period - 1) + max(ch, 0.0)) / period
        al = (al * (period - 1) + max(-ch, 0.0)) / period
    if al == 0:
        return 100.0 if ag > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + ag / al)


def atr_wilder_last(bars: Sequence[Dict[str, float]], period: int = 14) -> Optional[float]:
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["h"], bars[i]["l"], bars[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


# ==============================================================================
# 3. HISTORISCHE BARS (Binance / Yahoo) MIT LOKALEM CACHE
# ==============================================================================

def _http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _fetch_binance(symbol: str, interval: str, start_ts: int, end_ts: int) -> List[Dict[str, float]]:
    bars: List[Dict[str, float]] = []
    cursor = start_ts * 1000
    while cursor < end_ts * 1000:
        url = (f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}"
               f"&startTime={cursor}&endTime={end_ts * 1000}&limit=1000")
        chunk = _http_json(url)
        if not chunk:
            break
        bars.extend({"t": int(k[0] // 1000), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]),
                     "c": float(k[4]), "v": float(k[5])} for k in chunk)
        if len(chunk) < 1000:
            break
        cursor = int(chunk[-1][0]) + 1
        time.sleep(0.1)
    return bars


def _fetch_yahoo(symbol: str, interval: str, start_ts: int, end_ts: int) -> List[Dict[str, float]]:
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?interval={interval}&period1={start_ts}&period2={end_ts}")
    res = (_http_json(url).get("chart", {}).get("result") or [None])[0]
    if not res:
        return []
    ts = res.get("timestamp") or []
    q = (res.get("indicators", {}).get("quote") or [{}])[0]
    bars = []
    for i, t in enumerate(ts):
        o, h, l, c = (q.get(k, [None] * len(ts))[i] for k in ("open", "high", "low", "close"))
        if None in (o, h, l, c):
            continue
        bars.append({"t": int(t), "o": float(o), "h": float(h), "l": float(l), "c": float(c),
                     "v": float((q.get("volume") or [0] * len(ts))[i] or 0.0)})
    return bars


def load_bars(source: str, symbol: str, interval: str, start_ts: int, end_ts: int,
              offline: bool = False) -> List[Dict[str, float]]:
    """Lädt Bars für [start_ts, end_ts]; nutzt/aktualisiert einen lokalen Cache (reproduzierbar)."""
    cache_file = BAR_CACHE_DIR / f"{BAR_CACHE_PREFIX}{source}_{symbol.replace('.', '-')}_{interval}.json"
    cached: Dict[str, Any] = {}
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text())
        except (OSError, ValueError):
            cached = {}
    if cached and cached.get("start", math.inf) <= start_ts and cached.get("end", -math.inf) >= end_ts:
        return cached["bars"]
    if offline:
        return cached.get("bars", [])
    try:
        fetch = _fetch_binance if source == "binance" else _fetch_yahoo
        bars = fetch(symbol, interval, start_ts, end_ts)
    except Exception as e:  # Netzwerk-/API-Fehler: Trade wird später als "nicht evaluierbar" geführt
        print(f"  ⚠️ Fetch-Fehler {source}:{symbol} {interval}: {e}")
        return cached.get("bars", [])
    bars = sorted({b["t"]: b for b in bars}.values(), key=lambda b: b["t"])
    if bars:
        try:
            BAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps({"start": start_ts, "end": end_ts, "bars": bars}))
        except OSError as e:
            print(f"  ⚠️ Cache nicht schreibbar ({cache_file.name}): {e}")
    return bars


# ==============================================================================
# 4. POINT-IN-TIME-REKONSTRUKTION DES MARKTKONTEXTS
# ==============================================================================

def build_market_context(trade: Dict[str, Any], ltf_bars: Sequence[Dict[str, float]],
                         htf_bars: Sequence[Dict[str, float]]) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Baut den Kontext, wie er zum Entscheidungszeitpunkt vorlag — ohne Look-Ahead.

    Informations-Cutoff ist entry_timestamp: Es zählen ausschließlich Kerzen, die bis dahin
    geschlossen waren (t + tf <= entry_timestamp). Empirisch belegt an den Incubator-Trades:
    entry_timestamp ist die Öffnungszeit der beim Scan noch LAUFENDEN Kerze (Binance, Scan im
    Median 83 s nach Öffnung) bzw. der Zeitstempel des letzten verzögerten Yahoo-Ticks. Die
    laufende Kerze (inkl. ihres Endvolumens) war nicht bekannt und wird nicht verwendet.
    Für Trades, deren entry_timestamp die Öffnung einer bereits geschlossenen Signalkerze ist,
    kann 'signal_bar_closed': True gesetzt werden; dann zählt diese Kerze mit.

    Rückgabe: (context | None, fehlergrund)
    """
    tf = TF_SECONDS.get(trade.get("timeframe", ""))
    htf_sec = TF_SECONDS[HTF_FOR_LTF.get(trade.get("timeframe", ""), "1h")]
    ets = int(trade.get("entry_timestamp") or 0)
    entry = _num(trade.get("entry_price"))
    if not tf or not ets or not entry > 0:
        return None, "Timeframe/Entry-Zeit/Entry-Preis unbekannt"

    decision_ts = ets + tf if (trade.get("signal_bar_closed") and ets % tf == 0) else ets
    ltf = [b for b in ltf_bars if b["t"] + tf <= decision_ts]
    htf = [b for b in htf_bars if b["t"] + htf_sec <= decision_ts]

    need_ltf = max(ATR_PERIOD + 1, VOLUME_AVG_PERIOD + 1, BREAKOUT_LOOKBACK + 1)
    if len(ltf) < need_ltf:
        return None, f"zu wenig LTF-Historie ({len(ltf)} Bars)"
    if decision_ts - (ltf[-1]["t"] + tf) > MAX_STALE_SECONDS:
        return None, "LTF-Historie endet zu lange vor dem Entry"
    if len(htf) < HTF_WMA_PERIOD:
        return None, f"zu wenig HTF-Historie ({len(htf)} < {HTF_WMA_PERIOD} Bars)"

    last = ltf[-1]                                   # letzte GESCHLOSSENE Kerze
    prior = ltf[-BREAKOUT_LOOKBACK:]
    vols = [b["v"] for b in ltf[-(VOLUME_AVG_PERIOD + 1):-1]]
    direction = str(trade.get("direction", "")).upper()
    # Breakout: Entry-Preis liegt jenseits des Donchian-Kanals der letzten 20 geschlossenen Kerzen
    if direction == "LONG":
        is_breakout = entry > max(b["h"] for b in prior)
    else:
        is_breakout = entry < min(b["l"] for b in prior)

    # Diagnose (fließt in keinen Filter ein): Liegt der geloggte Entry in der Spanne der
    # Kerze, die entry_timestamp enthält? Prüft, dass Symbol/Zeitachse korrekt zugeordnet sind.
    live = next((b for b in ltf_bars if b["t"] <= ets < b["t"] + tf), None)
    in_range = None
    if live:
        tol = 0.0005 * entry
        in_range = (live["l"] - tol) <= entry <= (live["h"] + tol)

    htf_closes = [b["c"] for b in htf]
    return {
        "current_price": entry,
        "htf_wma233": wma_last(htf_closes, HTF_WMA_PERIOD),
        "htf_rsi": rsi_wilder_last(htf_closes[-(HTF_RSI_PERIOD * 20):], HTF_RSI_PERIOD),
        "current_volume": last["v"],
        "avg_volume_20": sum(vols) / len(vols),
        "atr_14": atr_wilder_last(ltf[-(ATR_PERIOD * 20):], ATR_PERIOD),
        "is_breakout": is_breakout,
        "_entry_in_live_bar_range": in_range,
    }, ""


def reconstruct_contexts(trades: Sequence[Dict[str, Any]], offline: bool = False
                         ) -> List[Tuple[Optional[Dict[str, Any]], str]]:
    """Lädt die nötige Historie je Symbol/Timeframe und baut den Kontext pro Trade."""
    groups: Dict[Tuple[str, str, str], List[int]] = {}
    for i, t in enumerate(trades):
        groups.setdefault((t.get("source", "binance"), t.get("symbol", ""), t.get("timeframe", "")), []).append(i)

    out: List[Tuple[Optional[Dict[str, Any]], str]] = [(None, "nicht geladen")] * len(trades)
    htf_cache: Dict[Tuple[str, str, str], List[Dict[str, float]]] = {}
    for (source, symbol, tf_name), idxs in sorted(groups.items()):
        tf = TF_SECONDS.get(tf_name)
        if not tf:
            for i in idxs:
                out[i] = (None, f"Timeframe '{tf_name}' nicht unterstützt")
            continue
        ts = [int(trades[i]["entry_timestamp"]) for i in idxs]
        lo, hi = min(ts), max(ts) + tf
        # Aktien handeln nur ~9-14h/Tag: großzügige Vorlaufzeit in Kalendertagen
        ltf_pad = 2 * 86400 if source == "binance" else 6 * 86400
        htf_pad = 16 * 86400 if source == "binance" else 75 * 86400
        ltf_bars = load_bars(source, symbol, tf_name, lo - ltf_pad, hi, offline)
        htf_name = HTF_FOR_LTF[tf_name]
        key = (source, symbol, htf_name)
        if key not in htf_cache:
            all_ts = [int(t["entry_timestamp"]) for t in trades
                      if t.get("source", "binance") == source and t.get("symbol") == symbol]
            htf_cache[key] = load_bars(source, symbol, htf_name, min(all_ts) - htf_pad,
                                       max(all_ts) + 900, offline)
        for i in idxs:
            out[i] = build_market_context(trades[i], ltf_bars, htf_cache[key])
    return out


# ==============================================================================
# 5. STATISTIK
# ==============================================================================

def _wilson(wins: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = wins / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (100 * (mid - half), 100 * (mid + half))


def _bootstrap_mean_ci(xs: Sequence[float], n_boot: int = 5000, seed: int = 233) -> Tuple[float, float]:
    if len(xs) < 2:
        return (math.nan, math.nan)
    rng = random.Random(seed)
    n = len(xs)
    means = sorted(sum(rng.choices(xs, k=n)) / n for _ in range(n_boot))
    return (means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1])


def summarize(rs: Sequence[float]) -> Dict[str, Any]:
    """Kennzahlen einer R-Serie. Win = realized_r > 0 (TP1-Teilgewinn + BE zählt als Win)."""
    n = len(rs)
    wins = sum(1 for r in rs if r > 0)
    lo, hi = _wilson(wins, n)
    e_lo, e_hi = _bootstrap_mean_ci(rs)
    return {
        "n": n, "wins": wins, "losses": n - wins,
        "win_rate": round(100 * wins / n, 1) if n else math.nan,
        "win_rate_ci95": (round(lo, 1), round(hi, 1)),
        "total_r": round(sum(rs), 2),
        "expectancy_r": round(sum(rs) / n, 3) if n else math.nan,
        "expectancy_ci95": (round(e_lo, 3), round(e_hi, 3)),
    }


# ==============================================================================
# 6. BACKTEST
# ==============================================================================

def backtest_filter_improvement(trades: Sequence[Dict[str, Any]],
                                contexts: Optional[Sequence[Optional[Dict[str, Any]]]] = None,
                                offline: bool = False) -> Dict[str, Any]:
    """
    Simuliert, wie Win-Rate und E(R) der geschlossenen Incubator-Trades ausgesehen hätten,
    wenn die Kausalitäts-Filter aktiv gewesen wären.

    trades   : geschlossene Trades (Schema incubator_trades.json -> closed_trades)
    contexts : optional vorberechnete market_context-Dicts (gleiche Reihenfolge, None = nicht
               evaluierbar). Ohne Angabe wird der Kontext point-in-time aus Marktdaten rekonstruiert.

    Trades ohne rekonstruierbaren Kontext werden NICHT stillschweigend als "abgelehnt" oder
    "freigegeben" gezählt, sondern separat ausgewiesen; der Vorher/Nachher-Vergleich läuft
    ausschließlich über die evaluierbare Teilmenge.
    """
    trades = [t for t in trades if _num(t.get("realized_r")) == _num(t.get("realized_r"))]
    if contexts is None:
        ctx_pairs = reconstruct_contexts(trades, offline=offline)
    else:
        ctx_pairs = [(c, "" if c else "kein Kontext übergeben") for c in contexts]

    rows = []
    unevaluable: Dict[str, int] = {}
    for t, (ctx, err) in zip(trades, ctx_pairs):
        if ctx is None:
            unevaluable[err] = unevaluable.get(err, 0) + 1
            continue
        results = run_filters(t, ctx)
        approved, reasons, score = evaluate_setup_causality(t, ctx)
        rows.append({"trade": t, "ctx": ctx, "r": float(t["realized_r"]), "approved": approved,
                     "reasons": reasons, "score": score,
                     "fails": {r.name for r in results if not r.passed},
                     "regime": results[0].metrics.get("regime"),
                     "vol_applicable": results[1].applicable})

    def rs(pred) -> List[float]:
        return [x["r"] for x in rows if pred(x)]

    report: Dict[str, Any] = {
        "n_input": len(trades),
        "n_evaluable": len(rows),
        "unevaluable": unevaluable,
        "baseline_all": summarize([float(t["realized_r"]) for t in trades]),
        "baseline_evaluable": summarize(rs(lambda x: True)),
        "approved": summarize(rs(lambda x: x["approved"])),
        "rejected": summarize(rs(lambda x: not x["approved"])),
        "per_filter_rejected": {
            name: summarize(rs(lambda x, n=name: n in x["fails"])) for name in SCORE_WEIGHTS
        },
        "per_filter_alone_approved": {
            name: summarize(rs(lambda x, n=name: n not in x["fails"])) for name in SCORE_WEIGHTS
        },
        "by_regime_direction": {},
        "approved_by_tf_direction": {},
        "breakout_trades": sum(1 for x in rows if x["vol_applicable"]),
        "rows": rows,
    }
    for x in rows:
        k = f"{x['regime']} / {x['trade'].get('direction')}"
        report["by_regime_direction"].setdefault(k, []).append(x["r"])
        if x["approved"]:
            k2 = f"{x['trade'].get('timeframe')} {x['trade'].get('direction')}"
            report["approved_by_tf_direction"].setdefault(k2, []).append(x["r"])
    report["by_regime_direction"] = {k: summarize(v) for k, v in sorted(report["by_regime_direction"].items())}
    report["approved_by_tf_direction"] = {k: summarize(v) for k, v in sorted(report["approved_by_tf_direction"].items())}

    checks = [x["ctx"].get("_entry_in_live_bar_range") for x in rows]
    checks = [c for c in checks if c is not None]
    report["reconstruction_check"] = {
        "n": len(checks),
        "share_entry_in_bar_range": round(100 * sum(checks) / len(checks), 1) if checks else None,
    }
    return report


def _fmt(s: Dict[str, Any]) -> str:
    if not s["n"]:
        return "n=0"
    return (f"n={s['n']:>3}  {s['wins']:>3}W/{s['losses']:>3}L  WR {s['win_rate']:>5.1f}% "
            f"[{s['win_rate_ci95'][0]:.1f}; {s['win_rate_ci95'][1]:.1f}]  "
            f"ΣR {s['total_r']:>+7.2f}  E(R) {s['expectancy_r']:>+6.3f} "
            f"[{s['expectancy_ci95'][0]:+.3f}; {s['expectancy_ci95'][1]:+.3f}]")


def print_backtest_report(rep: Dict[str, Any]) -> None:
    line = "=" * 118
    print(line)
    print("KAUSALITÄTS-FILTER — BACKTEST AUF GESCHLOSSENEN INCUBATOR-TRADES   (Klammern = 95%-Konfidenzintervall)")
    print(line)
    print(f"Trades gesamt: {rep['n_input']}   evaluierbar: {rep['n_evaluable']}   "
          f"nicht evaluierbar: {rep['n_input'] - rep['n_evaluable']}")
    for reason, n in rep["unevaluable"].items():
        print(f"   · {n}x {reason}")
    rc = rep["reconstruction_check"]
    if rc["n"]:
        print(f"Rekonstruktions-Check: geloggter Entry liegt bei {rc['share_entry_in_bar_range']}% von {rc['n']} "
              f"Trades in der High/Low-Spanne der Kerze zum Entry-Zeitpunkt")
    print()
    print(f"  Baseline (alle)           {_fmt(rep['baseline_all'])}")
    print(f"  Baseline (evaluierbar)    {_fmt(rep['baseline_evaluable'])}")
    print(f"  ✅ Freigegeben            {_fmt(rep['approved'])}")
    print(f"  ⛔ Abgelehnt              {_fmt(rep['rejected'])}")
    print()
    print("Abgelehnte Trades je Filter (Überschneidungen möglich):")
    for name, s in rep["per_filter_rejected"].items():
        print(f"  {name:<18}        {_fmt(s)}")
    print("Ergebnis, wenn NUR dieser eine Filter aktiv wäre (freigegebene Trades):")
    for name, s in rep["per_filter_alone_approved"].items():
        print(f"  {name:<18}        {_fmt(s)}")
    print(f"\nVolumen-Filter anwendbar (Breakout laut {BREAKOUT_LOOKBACK}-Bar-Donchian): "
          f"{rep['breakout_trades']} von {rep['n_evaluable']} Trades")
    print("\nHTF-Regime (1h WMA233 + RSI14) × Richtung, alle evaluierbaren Trades:")
    for k, s in rep["by_regime_direction"].items():
        print(f"  {k:<22}    {_fmt(s)}")
    if rep["approved_by_tf_direction"]:
        print("\nFreigegebene Trades nach Timeframe × Richtung:")
        for k, s in rep["approved_by_tf_direction"].items():
            print(f"  {k:<22}    {_fmt(s)}")

    a, b = rep["approved"], rep["baseline_evaluable"]
    print("\n" + "-" * 118)
    if not a["n"]:
        print("FAZIT: Die Filter hätten keinen einzigen Trade freigegeben — keine Aussage über E(R) möglich.")
    else:
        lo, hi = a["expectancy_ci95"]
        print(f"FAZIT: E(R) {b['expectancy_r']:+.3f} -> {a['expectancy_r']:+.3f} bei {a['n']} statt {b['n']} Trades "
              f"(Win-Rate {b['win_rate']:.1f}% -> {a['win_rate']:.1f}%).")
        if lo > 0:
            print("       Untere CI-Grenze > 0: in dieser Stichprobe positiv — Out-of-Sample-Bestätigung steht aus.")
        elif a["expectancy_r"] > 0:
            print(f"       Punktwert positiv, aber das 95%-Intervall [{lo:+.3f}; {hi:+.3f}] schließt 0 ein: "
                  f"kein belastbarer Nachweis von E(R) > 0.")
        else:
            print("       Auch gefiltert bleibt E(R) <= 0: Die Filter reduzieren Verluste, erzeugen aber keinen Edge.")
    print("       In-Sample-Auswertung über wenige Handelstage in einem einzigen Marktregime.")
    print(line)


# ==============================================================================
# 7. SELBSTTEST
# ==============================================================================

def _selftest() -> None:
    # --- HTF ---
    assert check_htf_alignment("LONG", 105, 100, 60).passed
    assert not check_htf_alignment("LONG", 95, 100, 40).passed            # Long gegen bearishen HTF
    assert check_htf_alignment("SHORT", 95, 100, 40).passed
    assert not check_htf_alignment("SHORT", 105, 100, 60).passed
    assert not check_htf_alignment("LONG", 105, 100, 45).passed           # neutral -> strikt abgelehnt
    assert not check_htf_alignment("LONG", 100, 100, 50).passed           # exakt auf der Schwelle = neutral
    assert not check_htf_alignment("LONG", 105, None, 60).passed          # fail-closed
    assert not check_htf_alignment("LONG", 105, float("nan"), 60).passed
    assert not check_htf_alignment("HOLD", 105, 100, 60).passed
    # --- Volumen ---
    assert check_vsa_volume_expansion(125, 100, True).passed              # exakt 1.25x
    assert not check_vsa_volume_expansion(124.9, 100, True).passed
    assert not check_vsa_volume_expansion(500, 0, True).passed            # Ø-Volumen 0 -> fail-closed
    r = check_vsa_volume_expansion(10, 100, False)
    assert r.passed and not r.applicable                                  # kein Breakout -> nicht anwendbar
    # --- ATR ---
    assert check_atr_noise_floor(100, 98.8, 1.0).passed                   # exakt 1.2x ATR
    assert not check_atr_noise_floor(100, 98.9, 1.0).passed
    assert check_atr_noise_floor(100, 101.5, 1.0).passed                  # Short-Stop oberhalb
    assert not check_atr_noise_floor(100, 100, 1.0).passed
    assert not check_atr_noise_floor(100, 98, 0).passed
    # --- Aggregation ---
    ctx = {"htf_wma233": 100, "htf_rsi": 62, "current_volume": 200, "avg_volume_20": 100, "atr_14": 1.0}
    ok, reasons, score = evaluate_setup_causality(
        {"direction": "LONG", "entry_price": 104, "sl": 102, "is_breakout": True}, ctx)
    assert ok and not reasons and 50 <= score <= 100, (ok, reasons, score)
    ok, reasons, score = evaluate_setup_causality(
        {"direction": "LONG", "entry_price": 96, "sl": 95.5, "is_breakout": True},
        {**ctx, "htf_rsi": 35, "current_volume": 80})
    assert not ok and len(reasons) == 3 and score == 0.0, (ok, reasons, score)
    # Break-Even-nachgezogener Stop (sl == entry): Initial-Stop kommt aus risk_amount
    ok, _, _ = evaluate_setup_causality(
        {"direction": "LONG", "entry_price": 104, "sl": 104, "risk_amount": 2.0}, ctx)
    assert ok
    ok, reasons, _ = evaluate_setup_causality({}, {})
    assert not ok and len(reasons) == 2                                   # leer -> abgelehnt
    # --- Indikatoren ---
    assert abs(wma_last([1, 2, 3], 3) - (1 + 4 + 9) / 6) < 1e-12
    assert rsi_wilder_last(list(range(1, 40)), 14) == 100.0
    assert abs(rsi_wilder_last([1, 2] * 20, 14) - 50.0) < 5.0
    flat = [{"h": 2.0, "l": 1.0, "c": 1.5}] * 30
    assert abs(atr_wilder_last(flat, 14) - 1.0) < 1e-12
    # --- Kein Look-Ahead: Bars nach dem Entscheidungszeitpunkt dürfen den Kontext nicht ändern ---
    ltf = [{"t": 300 * i, "o": 10, "h": 10.5, "l": 9.5, "c": 10 + 0.01 * i, "v": 100 + i} for i in range(400)]
    htf = [{"t": 3600 * i - 3600 * 290, "o": 10, "h": 11, "l": 9, "c": 9 + 0.005 * i, "v": 1} for i in range(330)]
    ets = 300 * 200
    trade = {"timeframe": "5m", "direction": "LONG", "entry_timestamp": ets, "entry_price": 10.2}
    c1, _ = build_market_context(trade, ltf, htf)
    # Alles ab der laufenden Kerze (t >= ets) bzw. jede HTF-Kerze, die nach ets schließt, vergiften:
    p_ltf = [b if b["t"] < ets else {**b, "c": 999, "h": 999, "l": 998, "v": 1e9} for b in ltf]
    p_htf = [b if b["t"] + 3600 <= ets else {**b, "c": 999} for b in htf]
    c2, _ = build_market_context(trade, p_ltf, p_htf)
    strip = lambda c: {k: v for k, v in c.items() if not k.startswith("_")}
    assert c1 is not None and strip(c1) == strip(c2), "Look-Ahead-Leck in build_market_context"
    assert c1["current_volume"] == 100 + 199                              # letzte geschlossene Kerze
    print("✅ Selbsttest bestanden (Filter-Schwellen, Fail-Closed, Indikatoren, No-Look-Ahead)\n")


def main(argv: Sequence[str]) -> int:
    _selftest()
    if not INCUBATOR_FILE.exists():
        print(f"⚠️ {INCUBATOR_FILE} nicht gefunden — Backtest übersprungen.")
        return 1
    closed = json.loads(INCUBATOR_FILE.read_text()).get("closed_trades", [])
    print(f"Lade Marktdaten und rekonstruiere Kontext für {len(closed)} geschlossene Trades ...")
    rep = backtest_filter_improvement(closed, offline="--offline" in argv)
    print_backtest_report(rep)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
