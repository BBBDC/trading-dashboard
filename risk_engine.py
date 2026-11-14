#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
risk_engine.py - Fractional-Kelly & Volatility-Regime Position Sizing Engine
=============================================================================

Zentrales Risikomanagement- und Positionsgrößen-Modul.

Kernformel
----------
    risk_budget = R_base * kelly_multiplier * volatility_factor
    qty         = floor_lot( risk_budget / |entry - stop_loss| )
    qty         = min(qty, Hebel-Deckel)

mit
    R_base             = equity * risk_pct / 100   (oder fixer Betrag, z.B. 100 EUR)
    kelly_multiplier   = Konviktions-Faktor aus Grade/Score (0.0 ... 1.5)
    volatility_factor  = clamp(ATR_baseline / ATR_current, vol_floor, 1.0)

Dadurch ist das Risiko pro Trade unabhängig von der Stop-Distanz: BTC mit 5 %
Stop und eine DAX-Aktie mit 0.8 % Stop verlieren am Stop denselben Geldbetrag
(bei gleichem Grade und gleichem Vol-Regime). Die Stop-Weite bestimmt nur noch
das Notional, nicht mehr den Verlust.

Sicherheitsprinzipien
---------------------
* Es wird IMMER abgerundet (nie auf min_lot aufgerundet). Ist die berechnete
  Menge kleiner als min_lot / min_notional, wird der Trade abgelehnt, statt
  das Risiko-Budget zu überschreiten.
* Kelly-Multiplikator und Vol-Faktor können das Risiko nur innerhalb harter
  Grenzen verändern; zusätzlich gilt ein Kelly-Deckel:
  effektives Risiko <= kelly_fraction * f*  (Quarter-Kelly-Obergrenze).
* Die Funktion wirft bei fehlerhaften Eingaben keine Exception, sondern
  liefert is_executable=False mit rejection_reason (fail-closed).

Hinweis: `risk_cash` ist der Verlust bei Ausführung exakt am Stop-Preis.
Slippage, Gebühren und Gaps über den Stop hinaus (Flash-Crash, Overnight)
können den realen Verlust erhöhen - genau dafür existiert die Vol-Dämpfung.

Nur Standardbibliothek. Python >= 3.8.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Dict, Optional, Sequence, Tuple, TypedDict

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

REGIME_NORMAL = "NORMAL"
REGIME_HIGH = "HIGH_VOLATILITY"
REGIME_LOW = "LOW_VOLATILITY"

GRADE_A_PLUS = "A+"
GRADE_A = "A"
GRADE_B = "B"
GRADE_NTZ = "NTZ"    # No-Trade-Zone (Score < 40)
GRADE_VETO = "VETO"  # Hartes Veto


@dataclass(frozen=True)
class GradeProfile:
    """Empirisches Profil einer Signal-Güteklasse (63.716-Kerzen-Backtest)."""

    min_score: float              # untere Score-Grenze (inklusive)
    max_score: float              # obere Score-Grenze (für Interpolation)
    mult_low: float               # Multiplikator am unteren Band-Ende
    mult_high: float              # Multiplikator am oberen Band-Ende
    win_rate: Optional[float]     # p
    payoff: Optional[float]       # b (Ø Gewinn / Ø Verlust)
    kelly_f: Optional[float]      # f*, falls p/b nicht einzeln vorliegen


# Reihenfolge: höchste Klasse zuerst (wird für das Score-Mapping verwendet).
GRADE_PROFILES: Dict[str, GradeProfile] = {
    # p=0.629, b=2.89 -> f* = 0.629 - 0.371/2.89 ~ 0.50 -> 1.25x .. 1.50x
    GRADE_A_PLUS: GradeProfile(80.0, 100.0, 1.25, 1.50, 0.629, 2.89, None),
    # p=0.51,  b=1.80 -> f* = 0.51 - 0.49/1.80 ~ 0.24 -> 0.85x .. 1.00x
    GRADE_A: GradeProfile(60.0, 80.0, 0.85, 1.00, 0.51, 1.80, None),
    # f* ~ 0.10 (nur aggregiert bekannt) -> 0.50x
    GRADE_B: GradeProfile(40.0, 60.0, 0.50, 0.50, None, None, 0.10),
}


@dataclass(frozen=True)
class RiskConfig:
    """Globale Risiko-Parameter. Alle Werte sind konservative Defaults."""

    risk_pct: float = 1.0             # 1.0R in % der Equity
    kelly_fraction: float = 0.25      # Quarter-Kelly
    max_leverage: float = 3.0         # max. Gesamt-Notional / Equity
    atr_period: int = 14              # ATR-Periode
    atr_baseline_period: int = 20     # SMA-Periode der ATR (Baseline)
    high_vol_ratio: float = 1.25      # ATR/Baseline >= 1.25 -> HIGH_VOLATILITY
    low_vol_ratio: float = 0.75       # ATR/Baseline <= 0.75 -> LOW_VOLATILITY
    vol_floor: float = 0.25           # Vol-Faktor fällt nie unter 0.25
    max_stop_pct: float = 50.0        # Plausibilitätsgrenze Stop-Distanz in %


DEFAULT_CONFIG = RiskConfig()


class PositionSize(TypedDict):
    """Rückgabe-Struktur von calculate_position_size()."""

    qty: float                  # Einheiten (Shares/Coins), auf Lot-Raster abgerundet
    notional_capital: float     # qty * entry
    risk_cash: float            # qty * |entry - SL|
    effective_risk_pct: float   # risk_cash in % der Equity
    kelly_multiplier: float     # angewendeter Kelly-Faktor
    volatility_factor: float    # angewendeter Vol-Faktor
    regime: str                 # NORMAL / HIGH_VOLATILITY / LOW_VOLATILITY
    is_executable: bool
    rejection_reason: str       # "" falls ausführbar
    # --- Zusatzinfos für Logging / Dashboard ---
    side: str                   # LONG / SHORT
    grade: str                  # A+ / A / B / NTZ / VETO
    kelly_f_star: float         # volles Kelly f* der Güteklasse
    target_risk_cash: float     # Risiko-Budget vor Lot-Rundung und Deckeln
    leverage: float             # notional_capital / equity
    limited_by: str             # RISK / LEVERAGE_CAP / KELLY_CAP


# ---------------------------------------------------------------------------
# Kelly
# ---------------------------------------------------------------------------

def kelly_fraction_full(win_rate: float, payoff: float) -> float:
    """Volles Kelly-Kriterium: f* = p - (1 - p) / b. Negativ = kein Edge -> 0."""
    if not (0.0 < win_rate < 1.0) or payoff <= 0.0:
        return 0.0
    return max(0.0, win_rate - (1.0 - win_rate) / payoff)


def grade_from_score(score: float) -> str:
    """Score (0-100) -> Güteklasse."""
    for name, prof in GRADE_PROFILES.items():
        if score >= prof.min_score:
            return name
    return GRADE_NTZ


def _normalize_grade(grade: str) -> str:
    g = grade.strip().upper().replace(" ", "").replace("PLUS", "+")
    if g in GRADE_PROFILES:
        return g
    if g in ("VETO", "BLOCK", "BLOCKED"):
        return GRADE_VETO
    return GRADE_NTZ  # unbekannt -> fail-closed


def kelly_multiplier_for(
    score: Optional[float] = None,
    grade: Optional[str] = None,
    veto: bool = False,
) -> Tuple[float, str, float]:
    """
    Liefert (multiplier, grade, f*).

    * Ist `grade` gesetzt, bestimmt es die Klasse; `score` verfeinert nur die
      Position innerhalb des Bandes. Ohne Score gilt das untere (konservative)
      Band-Ende.
    * Innerhalb eines Bandes wird linear interpoliert
      (A+: Score 80 -> 1.25x, Score 100 -> 1.50x; A: 60 -> 0.85x, 80 -> 1.00x).
    * VETO / NTZ / kein Edge -> 0.0.
    """
    if veto:
        return 0.0, GRADE_VETO, 0.0
    if grade is not None:
        g = _normalize_grade(grade)
    elif score is not None and math.isfinite(score):
        g = grade_from_score(score)
    else:
        return 0.0, GRADE_NTZ, 0.0

    prof = GRADE_PROFILES.get(g)
    if prof is None:
        return 0.0, g, 0.0

    if prof.win_rate is not None and prof.payoff is not None:
        f_star = kelly_fraction_full(prof.win_rate, prof.payoff)
    else:
        f_star = max(0.0, prof.kelly_f or 0.0)
    if f_star <= 0.0:
        return 0.0, g, 0.0

    mult = prof.mult_low
    if score is not None and math.isfinite(score) and prof.max_score > prof.min_score:
        t = (score - prof.min_score) / (prof.max_score - prof.min_score)
        t = min(1.0, max(0.0, t))  # Score außerhalb des Bandes wird geklemmt
        mult = prof.mult_low + t * (prof.mult_high - prof.mult_low)
    return mult, g, f_star


# ---------------------------------------------------------------------------
# Volatilität
# ---------------------------------------------------------------------------

def wilder_atr_series(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> list:
    """
    ATR nach Wilder. Gibt eine Liste der ATR-Werte ab der ersten vollständigen
    Periode zurück (Länge = len(closes) - period). Leere Liste bei zu wenig Daten.
    """
    n = min(len(highs), len(lows), len(closes))
    if period < 1 or n < period + 1:
        return []
    trs = []
    for i in range(1, n):
        trs.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    atr = sum(trs[:period]) / period
    out = [atr]
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
        out.append(atr)
    return out


def atr_and_baseline(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    config: RiskConfig = DEFAULT_CONFIG,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Bequemlichkeits-Helfer: (ATR_current, ATR_baseline) aus OHLC-Reihen
    (älteste Kerze zuerst). Baseline = SMA(atr_baseline_period) der ATR.
    Liefert (None, None), wenn die Historie nicht ausreicht.
    """
    series = wilder_atr_series(highs, lows, closes, config.atr_period)
    if len(series) < config.atr_baseline_period:
        return None, None
    window = series[-config.atr_baseline_period:]
    return series[-1], sum(window) / len(window)


def volatility_regime(
    atr_current: Optional[float],
    atr_baseline: Optional[float],
    config: RiskConfig = DEFAULT_CONFIG,
) -> Tuple[float, str]:
    """
    Liefert (volatility_factor, regime).

    factor = clamp(ATR_baseline / ATR_current, vol_floor, 1.0)

    Der Faktor ist stetig (keine Sprungstelle an der Regime-Grenze) und wirkt
    ausschließlich dämpfend: In ruhigen Phasen (LOW_VOLATILITY) wird NICHT
    hochskaliert, da Volatilitäts-Kompression typischerweise einer Expansion
    vorausgeht. Fehlen ATR-Daten, gilt NORMAL / 1.0.
    """
    if (
        atr_current is None or atr_baseline is None
        or not math.isfinite(atr_current) or not math.isfinite(atr_baseline)
        or atr_current <= 0.0 or atr_baseline <= 0.0
    ):
        return 1.0, REGIME_NORMAL

    ratio = atr_current / atr_baseline
    if ratio >= config.high_vol_ratio:
        regime = REGIME_HIGH
    elif ratio <= config.low_vol_ratio:
        regime = REGIME_LOW
    else:
        regime = REGIME_NORMAL
    factor = min(1.0, max(config.vol_floor, 1.0 / ratio))
    return factor, regime


# ---------------------------------------------------------------------------
# Lot-Rundung
# ---------------------------------------------------------------------------

def floor_to_step(value: float, step: float) -> float:
    """
    Rundet `value` auf das Lot-Raster `step` AB (nie auf). Decimal-basiert, um
    Float-Artefakte (0.1 + 0.2) zu vermeiden. step <= 0 -> keine Rundung.
    """
    if step <= 0.0 or value <= 0.0:
        return max(0.0, value)
    try:
        d_step = Decimal(str(step))
        d_val = Decimal(str(value))
        steps = (d_val / d_step).to_integral_value(rounding=ROUND_DOWN)
        return float(steps * d_step)
    except (InvalidOperation, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------

def _is_pos(x: Optional[float]) -> bool:
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x) and x > 0.0


def calculate_position_size(
    equity: float,
    entry_price: float,
    stop_loss: float,
    *,
    score: Optional[float] = None,
    grade: Optional[str] = None,
    veto: bool = False,
    atr_current: Optional[float] = None,
    atr_baseline: Optional[float] = None,
    risk_pct: Optional[float] = None,
    fixed_risk_cash: Optional[float] = None,
    max_leverage: Optional[float] = None,
    open_notional: float = 0.0,
    lot_step: float = 1.0,
    min_lot: float = 0.0,
    min_notional: float = 0.0,
    config: RiskConfig = DEFAULT_CONFIG,
) -> PositionSize:
    """
    Berechnet die Positionsgröße für einen Trade.

    Parameter
    ---------
    equity          Konto-Equity in Kontowährung.
    entry_price     Geplanter Einstiegspreis.
    stop_loss       Stop-Loss-Preis. Richtung wird abgeleitet:
                    SL < Entry -> LONG, SL > Entry -> SHORT.
    score           Signal-Score 0-100 (bestimmt Grade + Feinabstufung).
    grade           Optional explizit: "A+", "A", "B", "NTZ", "VETO".
    veto            True blockiert den Trade unabhängig von Score/Grade.
    atr_current     Aktuelle ATR(14).
    atr_baseline    SMA(20) der ATR. Fehlt einer der Werte -> keine Dämpfung.
    risk_pct        1.0R in % der Equity (Default: config.risk_pct).
    fixed_risk_cash 1.0R als fixer Betrag (z.B. 100.0); hat Vorrang vor risk_pct.
    max_leverage    Max. Gesamt-Notional / Equity (Default: config.max_leverage).
    open_notional   Bereits gebundenes Notional offener Positionen; wird auf
                    den Hebel-Deckel angerechnet.
    lot_step        Mengen-Raster (1 = ganze Aktien, 0.0001 = Krypto).
    min_lot         Mindestmenge der Börse.
    min_notional    Mindest-Ordergegenwert der Börse.

    Rückgabe: PositionSize-Dict. Bei is_executable=False sind qty,
    notional_capital und risk_cash immer 0.
    """
    cfg = config
    lev_cap = cfg.max_leverage if max_leverage is None else max_leverage

    result: PositionSize = {
        "qty": 0.0,
        "notional_capital": 0.0,
        "risk_cash": 0.0,
        "effective_risk_pct": 0.0,
        "kelly_multiplier": 0.0,
        "volatility_factor": 1.0,
        "regime": REGIME_NORMAL,
        "is_executable": False,
        "rejection_reason": "",
        "side": "",
        "grade": GRADE_NTZ,
        "kelly_f_star": 0.0,
        "target_risk_cash": 0.0,
        "leverage": 0.0,
        "limited_by": "",
    }

    def reject(reason: str) -> PositionSize:
        result.update(
            qty=0.0, notional_capital=0.0, risk_cash=0.0,
            effective_risk_pct=0.0, leverage=0.0,
            is_executable=False, rejection_reason=reason,
        )
        return result

    # --- 1) Eingabe-Validierung (fail-closed) -------------------------------
    if not _is_pos(equity):
        return reject("INVALID_INPUT: equity muss > 0 sein")
    if not _is_pos(entry_price):
        return reject("INVALID_INPUT: entry_price muss > 0 sein")
    if not _is_pos(stop_loss):
        return reject("INVALID_INPUT: stop_loss muss > 0 sein")
    if not _is_pos(lev_cap):
        return reject("INVALID_INPUT: max_leverage muss > 0 sein")
    if lot_step < 0 or min_lot < 0 or min_notional < 0 or open_notional < 0:
        return reject("INVALID_INPUT: lot_step/min_lot/min_notional/open_notional < 0")

    stop_distance = abs(entry_price - stop_loss)
    if stop_distance <= 0.0:
        return reject("INVALID_STOP: stop_loss ist identisch mit entry_price")
    result["side"] = "LONG" if stop_loss < entry_price else "SHORT"

    stop_pct = stop_distance / entry_price * 100.0
    if stop_pct > cfg.max_stop_pct:
        return reject(
            f"INVALID_STOP: Stop-Distanz {stop_pct:.1f}% > Plausibilitätsgrenze "
            f"{cfg.max_stop_pct:.0f}%"
        )

    # --- 2) Vol-Regime (wird auch bei Ablehnung für das Logging geliefert) --
    vol_factor, regime = volatility_regime(atr_current, atr_baseline, cfg)
    result["volatility_factor"] = round(vol_factor, 4)
    result["regime"] = regime

    # --- 3) Kelly-Multiplikator ---------------------------------------------
    mult, g, f_star = kelly_multiplier_for(score=score, grade=grade, veto=veto)
    result["kelly_multiplier"] = round(mult, 4)
    result["grade"] = g
    result["kelly_f_star"] = round(f_star, 4)
    if mult <= 0.0:
        if g == GRADE_VETO:
            return reject("VETO: Trade durch Veto blockiert")
        return reject("NTZ: Score/Grade in No-Trade-Zone (kein positiver Kelly-Edge)")

    # --- 4) Risiko-Budget ----------------------------------------------------
    if fixed_risk_cash is not None:
        if not _is_pos(fixed_risk_cash):
            return reject("INVALID_INPUT: fixed_risk_cash muss > 0 sein")
        base_risk = float(fixed_risk_cash)
    else:
        rp = cfg.risk_pct if risk_pct is None else risk_pct
        if not _is_pos(rp):
            return reject("INVALID_INPUT: risk_pct muss > 0 sein")
        base_risk = equity * rp / 100.0

    target_risk = base_risk * mult * vol_factor
    limited_by = "RISK"

    # Harter Kelly-Deckel: nie mehr als kelly_fraction * f* der Equity riskieren,
    # egal wie risk_pct / fixed_risk_cash konfiguriert sind.
    kelly_cap_cash = equity * cfg.kelly_fraction * f_star
    if target_risk > kelly_cap_cash:
        target_risk = kelly_cap_cash
        limited_by = "KELLY_CAP"
    result["target_risk_cash"] = round(target_risk, 2)

    # --- 5) Menge aus Risiko --------------------------------------------------
    qty_raw = target_risk / stop_distance

    # --- 6) Hebel-/Notional-Deckel -------------------------------------------
    notional_room = lev_cap * equity - open_notional
    if notional_room <= 0.0:
        return reject(
            f"LEVERAGE_CAP: Hebel-Limit {lev_cap:.2f}x durch offene Positionen "
            f"ausgeschöpft"
        )
    qty_lev_max = notional_room / entry_price
    if qty_raw > qty_lev_max:
        qty_raw = qty_lev_max
        limited_by = "LEVERAGE_CAP"

    # --- 7) Lot-Rundung (immer abrunden) -------------------------------------
    qty = floor_to_step(qty_raw, lot_step)
    result["limited_by"] = limited_by

    if qty <= 0.0:
        return reject(
            f"BELOW_MIN_LOT: berechnete Menge {qty_raw:.8g} < Lot-Raster {lot_step:g}"
        )
    if qty < min_lot:
        return reject(f"BELOW_MIN_LOT: Menge {qty:g} < min_lot {min_lot:g}")

    notional = qty * entry_price
    if notional < min_notional:
        return reject(
            f"BELOW_MIN_NOTIONAL: Notional {notional:.2f} < min_notional "
            f"{min_notional:.2f}"
        )

    # --- 8) Ergebnis -----------------------------------------------------------
    risk_cash = qty * stop_distance
    result.update(
        qty=qty,
        notional_capital=round(notional, 2),
        risk_cash=round(risk_cash, 2),
        effective_risk_pct=round(risk_cash / equity * 100.0, 4),
        leverage=round(notional / equity, 4),
        is_executable=True,
        rejection_reason="",
    )
    return result


# ---------------------------------------------------------------------------
# Standalone-Tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    EQUITY = 100_000.0
    _failures = []

    def check(name: str, cond: bool) -> None:
        print(f"    [{'OK' if cond else 'FAIL'}] {name}")
        if not cond:
            _failures.append(name)

    def show(title: str, r: PositionSize) -> None:
        print(f"\n=== {title} ===")
        if r["is_executable"]:
            print(
                f"    {r['side']} qty={r['qty']:g}  notional={r['notional_capital']:,.2f}"
                f"  risk={r['risk_cash']:,.2f} ({r['effective_risk_pct']:.3f}%)"
                f"  lev={r['leverage']:.2f}x"
            )
        else:
            print(f"    ABGELEHNT: {r['rejection_reason']}")
        print(
            f"    grade={r['grade']}  kelly_mult={r['kelly_multiplier']}"
            f"  f*={r['kelly_f_star']}  vol_factor={r['volatility_factor']}"
            f"  regime={r['regime']}  limited_by={r['limited_by'] or '-'}"
        )

    # Kelly-Formel gegen die Backtest-Werte
    print("=== Kelly-Formel ===")
    check("A+: f* ~ 0.50", abs(kelly_fraction_full(0.629, 2.89) - 0.50) < 0.01)
    check("A : f* ~ 0.24", abs(kelly_fraction_full(0.51, 1.80) - 0.24) < 0.01)
    check("kein Edge -> 0", kelly_fraction_full(0.30, 1.0) == 0.0)

    # 1) BTC 90k, 5% Stop, Grade A am oberen Band-Ende (explizites Grade, Score geklemmt -> 1.00x)
    btc = calculate_position_size(
        EQUITY, 90_000.0, 85_500.0, score=80, grade="A",
        atr_current=2_000.0, atr_baseline=2_000.0,
        lot_step=0.0001, min_lot=0.0001, min_notional=10.0,
    )
    show("BTC 90k | 5% Stop | Grade A | Normal-Vol", btc)
    check("ausführbar", btc["is_executable"])
    check("Risiko ~1.0R (<= 1000, Abrundung < 1 Lot)", 995.0 <= btc["risk_cash"] <= 1000.0)
    check("Notional ~20k (statt fixer Allokation)", 19_900 <= btc["notional_capital"] <= 20_000)

    # 2) SAP 220 EUR, 1% Stop, gleicher Grade -> gleiches Risiko, 5x Notional
    sap = calculate_position_size(
        EQUITY, 220.0, 217.80, score=80, grade="A",
        atr_current=3.0, atr_baseline=3.0, lot_step=1.0, min_lot=1.0,
    )
    show("SAP 220 | 1% Stop | Grade A | Normal-Vol", sap)
    check("ausführbar", sap["is_executable"])
    check("Risiko ~1.0R", 995.0 <= sap["risk_cash"] <= 1000.0)
    check("ganze Aktien", sap["qty"] == int(sap["qty"]))
    check(
        "Risiko-Parität BTC vs. SAP (< 0.5% Abweichung)",
        abs(btc["risk_cash"] - sap["risk_cash"]) / 1000.0 < 0.005,
    )

    # 3) BTC Flash-Crash: ATR = 2.5x Baseline -> Faktor 0.4
    crash = calculate_position_size(
        EQUITY, 90_000.0, 85_500.0, score=80, grade="A",
        atr_current=5_000.0, atr_baseline=2_000.0,
        lot_step=0.0001, min_lot=0.0001, min_notional=10.0,
    )
    show("BTC 90k | 5% Stop | Grade A | FLASH-CRASH (ATR 2.5x)", crash)
    check("Regime HIGH_VOLATILITY", crash["regime"] == REGIME_HIGH)
    check("Vol-Faktor 0.4", abs(crash["volatility_factor"] - 0.4) < 1e-9)
    check("Risiko ~0.4R", 395.0 <= crash["risk_cash"] <= 400.0)

    # 4) Extreme Vol-Explosion: Faktor wird bei vol_floor geklemmt
    extreme = calculate_position_size(
        EQUITY, 90_000.0, 85_500.0, grade="A",
        atr_current=20_000.0, atr_baseline=2_000.0, lot_step=0.0001,
    )
    show("BTC | ATR 10x Baseline (Floor)", extreme)
    check("Vol-Faktor = Floor 0.25", extreme["volatility_factor"] == 0.25)

    # 5) Niedrige Vol: Label LOW, aber KEIN Hochskalieren
    low = calculate_position_size(
        EQUITY, 220.0, 217.80, score=80, grade="A",
        atr_current=1.5, atr_baseline=3.0, lot_step=1.0,
    )
    show("SAP | Low-Vol (ATR 0.5x)", low)
    check("Regime LOW_VOLATILITY", low["regime"] == REGIME_LOW)
    check("Faktor bleibt 1.0", low["volatility_factor"] == 1.0)
    check("Menge identisch zu Normal-Vol", low["qty"] == sap["qty"])

    # 6) Grade-Staffel
    a_plus = calculate_position_size(EQUITY, 220.0, 217.80, score=100, lot_step=1.0)
    a_plus_lo = calculate_position_size(EQUITY, 220.0, 217.80, score=80, lot_step=1.0)
    a_lo = calculate_position_size(EQUITY, 220.0, 217.80, score=60, lot_step=1.0)
    b = calculate_position_size(EQUITY, 220.0, 217.80, score=50, lot_step=1.0)
    show("SAP | Grade A+ (Score 100)", a_plus)
    show("SAP | Grade B (Score 50)", b)
    check("A+ Score 100 -> 1.50x", a_plus["kelly_multiplier"] == 1.5)
    check("A+ Score 80  -> 1.25x", a_plus_lo["kelly_multiplier"] == 1.25)
    check("A  Score 60  -> 0.85x", a_lo["kelly_multiplier"] == 0.85)
    check("B  Score 50  -> 0.50x", b["kelly_multiplier"] == 0.5)
    check("Risiko A+ ~1.5R", 1490.0 <= a_plus["risk_cash"] <= 1500.0)
    check("Risiko B  ~0.5R", 495.0 <= b["risk_cash"] <= 500.0)

    # 7) VETO / NTZ
    veto = calculate_position_size(EQUITY, 220.0, 217.80, score=95, veto=True)
    ntz = calculate_position_size(EQUITY, 220.0, 217.80, score=35)
    nograde = calculate_position_size(EQUITY, 220.0, 217.80)
    show("VETO trotz Score 95", veto)
    show("NTZ (Score 35)", ntz)
    check("VETO blockiert", not veto["is_executable"] and veto["qty"] == 0.0
          and veto["rejection_reason"].startswith("VETO"))
    check("NTZ blockiert", not ntz["is_executable"] and ntz["rejection_reason"].startswith("NTZ"))
    check("ohne Score/Grade blockiert (fail-closed)", not nograde["is_executable"])

    # 8) Hebel-Deckel: enger 0.2%-Stop würde 750k Notional (7.5x) verlangen
    tight = calculate_position_size(EQUITY, 220.0, 219.56, score=100, lot_step=1.0)
    show("SAP | 0.2% Stop | A+ -> Hebel-Deckel 3x", tight)
    check("limited_by LEVERAGE_CAP", tight["limited_by"] == "LEVERAGE_CAP")
    check("Notional <= 3x Equity", tight["notional_capital"] <= 3.0 * EQUITY)
    check("Risiko unter Budget", tight["risk_cash"] < tight["target_risk_cash"])

    full = calculate_position_size(
        EQUITY, 220.0, 217.80, grade="A", open_notional=300_000.0
    )
    show("Hebel bereits ausgeschöpft (open_notional = 3x)", full)
    check("abgelehnt LEVERAGE_CAP", full["rejection_reason"].startswith("LEVERAGE_CAP"))

    # 9) Fixer Risikobetrag 100 EUR, SHORT, kleines Konto
    short = calculate_position_size(
        5_000.0, 90_000.0, 94_500.0, grade="A", score=80,
        fixed_risk_cash=100.0, lot_step=0.0001, min_notional=10.0,
    )
    show("BTC SHORT | fix 100 EUR Risiko | 5k Konto", short)
    check("Seite SHORT", short["side"] == "SHORT")
    check("Risiko ~100 EUR", 95.0 <= short["risk_cash"] <= 100.0)

    # 10) Mindestgrößen: Menge wird NICHT aufgerundet, sondern abgelehnt
    tiny = calculate_position_size(
        1_000.0, 90_000.0, 85_500.0, grade="B",
        lot_step=0.001, min_lot=0.01, min_notional=10.0,
    )
    show("BTC | 1k Konto | Grade B | min_lot 0.01", tiny)
    check("abgelehnt BELOW_MIN_LOT", tiny["rejection_reason"].startswith("BELOW_MIN_LOT"))

    min_not = calculate_position_size(
        1_000.0, 2.0, 1.0, grade="B", lot_step=1.0, min_notional=50.0,
    )
    show("Pennystock | min_notional 50", min_not)
    check("abgelehnt BELOW_MIN_NOTIONAL",
          min_not["rejection_reason"].startswith("BELOW_MIN_NOTIONAL"))

    # 11) Kelly-Deckel: absurd hohes risk_pct wird auf Quarter-Kelly begrenzt
    greedy = calculate_position_size(
        EQUITY, 90_000.0, 85_500.0, grade="B", risk_pct=20.0, lot_step=0.0001,
    )
    show("risk_pct=20% bei Grade B -> Kelly-Deckel", greedy)
    check("limited_by KELLY_CAP", greedy["limited_by"] == "KELLY_CAP")
    check("Risiko <= 0.25 * f* = 2.5%", greedy["effective_risk_pct"] <= 2.5)

    # 12) Ungültige Eingaben
    print("\n=== Ungültige Eingaben ===")
    for label, kwargs in [
        ("SL == Entry", dict(equity=EQUITY, entry_price=100.0, stop_loss=100.0)),
        ("Equity 0", dict(equity=0.0, entry_price=100.0, stop_loss=99.0)),
        ("NaN-Preis", dict(equity=EQUITY, entry_price=float("nan"), stop_loss=99.0)),
        ("negativer SL", dict(equity=EQUITY, entry_price=100.0, stop_loss=-1.0)),
        ("Stop 60% entfernt", dict(equity=EQUITY, entry_price=100.0, stop_loss=40.0)),
    ]:
        r = calculate_position_size(grade="A", **kwargs)
        check(f"{label}: {r['rejection_reason']}",
              not r["is_executable"] and r["qty"] == 0.0)

    # 13) ATR-Helfer + Lot-Rundung
    print("\n=== Helfer ===")
    closes = [100.0 + (i % 5) for i in range(60)]
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    atr_now, atr_base = atr_and_baseline(highs, lows, closes)
    check("ATR/Baseline aus OHLC berechnet",
          atr_now is not None and atr_base is not None and atr_now > 0)
    check("zu kurze Historie -> (None, None)",
          atr_and_baseline(highs[:10], lows[:10], closes[:10]) == (None, None))
    check("floor_to_step(0.29999, 0.0001) == 0.2999", floor_to_step(0.29999, 0.0001) == 0.2999)
    check("floor_to_step(0.3, 0.1) == 0.3 (kein Float-Artefakt)", floor_to_step(0.3, 0.1) == 0.3)
    check("floor_to_step(454.9, 1) == 454", floor_to_step(454.9, 1.0) == 454.0)

    print("\n" + "=" * 60)
    if _failures:
        print(f"{len(_failures)} TEST(S) FEHLGESCHLAGEN:")
        for f in _failures:
            print(f"  - {f}")
        raise SystemExit(1)
    print("ALLE TESTS BESTANDEN")
