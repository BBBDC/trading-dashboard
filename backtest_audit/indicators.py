#!/usr/bin/env python3
"""
backtest_audit/indicators.py
============================
Exakte, 100% kausale Indikator-Formeln gemaess Pre-Registration v1.2 (§1.5).
"""

import math
from typing import List, Optional


def sma(series: List[float], length: int) -> List[Optional[float]]:
    """Arithmetisches Mittel der letzten `length` Werte inklusive Index t."""
    n = len(series)
    out: List[Optional[float]] = [None] * n
    if n < length or length <= 0:
        return out
    s = sum(series[:length])
    out[length - 1] = s / length
    for i in range(length, n):
        s += series[i] - series[i - length]
        out[i] = s / length
    return out


def donchian_prev_max(series: List[float], length: int) -> List[Optional[float]]:
    """Geschlossenes Intervall [t-length, t-1]: max(series[t-length : t])."""
    n = len(series)
    out: List[Optional[float]] = [None] * n
    if n <= length or length <= 0:
        return out
    for i in range(length, n):
        out[i] = max(series[i - length : i])
    return out


def donchian_prev_min(series: List[float], length: int) -> List[Optional[float]]:
    """Geschlossenes Intervall [t-length, t-1]: min(series[t-length : t])."""
    n = len(series)
    out: List[Optional[float]] = [None] * n
    if n <= length or length <= 0:
        return out
    for i in range(length, n):
        out[i] = min(series[i - length : i])
    return out


def rsi_wilder(closes: List[float], period: int = 2) -> List[Optional[float]]:
    """Wilder-RSI (RMA, alpha=1/period), initialisiert ueber Mittel der ersten `period` Aenderungen."""
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    if n < period + 1 or period <= 0:
        return out

    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains += diff
        elif diff < 0:
            losses += -diff

    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = 100.0 if avg_loss == 0.0 else (100.0 - 100.0 / (1.0 + avg_gain / avg_loss))

    alpha = 1.0 / period
    for i in range(period + 1, n):
        diff = closes[i] - closes[i - 1]
        g = diff if diff > 0.0 else 0.0
        l = -diff if diff < 0.0 else 0.0
        avg_gain = (1.0 - alpha) * avg_gain + alpha * g
        avg_loss = (1.0 - alpha) * avg_loss + alpha * l
        out[i] = 100.0 if avg_loss == 0.0 else (100.0 - 100.0 / (1.0 + avg_gain / avg_loss))
    return out


def atr_wilder(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[Optional[float]]:
    """Wilder-ATR (RMA, alpha=1/period), initialisiert ueber Mittel der ersten `period` True Ranges."""
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    if n < period or period <= 0:
        return out

    tr = [highs[0] - lows[0]]
    for i in range(1, n):
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))

    rma = sum(tr[:period]) / period
    out[period - 1] = rma
    alpha = 1.0 / period
    for i in range(period, n):
        rma = (1.0 - alpha) * rma + alpha * tr[i]
        out[i] = rma
    return out


def ibs(high: float, low: float, close: float) -> Optional[float]:
    """Internal Bar Strength: (Close - Low) / (High - Low); None bei High == Low."""
    rng = high - low
    if rng <= 0.0:
        return None
    return (close - low) / rng


def rolling_vol_annualized(closes: List[float], window: int = 60) -> List[Optional[float]]:
    """Annualisierte realisierte Volatilitaet der letzten `window` Tagesrenditen."""
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    if n <= window or window < 2:
        return out
    rets = [0.0] * n
    for i in range(1, n):
        rets[i] = (closes[i] / closes[i - 1] - 1.0) if closes[i - 1] > 0 else 0.0
    sqrt252 = math.sqrt(252.0)
    for i in range(window, n):
        sl = rets[i - window + 1 : i + 1]
        mean = sum(sl) / window
        var = sum((x - mean) ** 2 for x in sl) / (window - 1)
        out[i] = math.sqrt(var) * sqrt252
    return out
