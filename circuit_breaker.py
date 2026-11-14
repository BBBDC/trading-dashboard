#!/usr/bin/env python3
"""
circuit_breaker.py — Institutionelles Schutz- und Kontrollmodul
================================================================

Drei unabhängige Gates, die VOR jedem neuen Einstieg geprüft werden:

1. Drawdown-Circuit-Breaker  -> check_drawdown_circuit_breaker()
     -3.0R  realisierter Tagesverlust (UTC-Tag)   => HALT_DAY   (keine neuen Einstiege heute)
     -10.0R Drawdown vom Equity-Höchststand       => REDUCE_SIZE (sizing_multiplier 0.5)
     -15.0R Drawdown vom Equity-Höchststand       => HALT_FULL  (Stopp bis Strategy-Review)

2. Portfolio-Heat / Cluster-Limit -> check_cluster_heat_limit()
     max. 3.0R offenes Gesamtrisiko, max. 1.5R je Asset-Cluster
     (CRYPTO, US_EQUITIES, EU_EQUITIES, FOREX, COMMODITIES)

3. Kosten-Gate -> check_cost_gate()
     Round-Trip-Reibung (2x Fee + Spread + Slippage) darf max. 10 % des
     Stop-Abstands (= 0.10R) kosten.

Grundsätze:
  * Fail-closed: ungültige Eingaben (NaN, Preis <= 0, negatives Risiko) führen
    bei Heat- und Kosten-Gate immer zur Ablehnung, nie zu einer Freigabe.
  * Alle Funktionen sind seiteneffektfrei und verändern ihre Eingaben nicht.
  * Grenzwerte sind inklusiv im Sinne der Sicherheit: genau -3.0R Tagesverlust
    löst aus; genau 3.0R Gesamt-Heat bzw. genau 0.10R Kosten sind noch erlaubt.

Nur Standardbibliothek.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "CircuitBreakerConfig",
    "DEFAULT_CONFIG",
    "CLUSTERS",
    "classify_asset_cluster",
    "check_drawdown_circuit_breaker",
    "check_cluster_heat_limit",
    "check_cost_gate",
]

# Toleranz für Float-Vergleiche an den Grenzwerten (z.B. 0.75 + 0.75 == 1.5).
_EPS = 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# 1. Konfiguration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Grenzwerte des Schutzmoduls. Alle R-Limits sind positive Beträge."""

    daily_loss_limit_r: float = 3.0    # -3.0R Tagesverlust => Not-Aus für neue Einstiege heute
    drawdown_reduce_r: float = 10.0    # -10.0R Drawdown vom Peak => Risiko halbieren
    drawdown_halt_r: float = 15.0      # -15.0R Drawdown vom Peak => Vollstopp / Strategy-Review
    max_total_heat_r: float = 3.0      # max. offenes Gesamtrisiko über alle Trades
    max_cluster_heat_r: float = 1.5    # max. offenes Risiko je Asset-Cluster
    flat_risk_pct: float = 0.5         # Basis-Risiko in % Equity pro Trade (statt Kelly)
    max_cost_r_ratio: float = 0.10     # Kosten-Gate: max. 10 % des Stop-Abstands als Reibung

    def __post_init__(self) -> None:
        for name in (
            "daily_loss_limit_r", "drawdown_reduce_r", "drawdown_halt_r",
            "max_total_heat_r", "max_cluster_heat_r", "flat_risk_pct", "max_cost_r_ratio",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(value) or value <= 0:
                raise ValueError(f"CircuitBreakerConfig.{name} muss eine endliche Zahl > 0 sein (ist {value!r})")
        if self.drawdown_reduce_r > self.drawdown_halt_r:
            raise ValueError("drawdown_reduce_r darf nicht größer als drawdown_halt_r sein")


DEFAULT_CONFIG = CircuitBreakerConfig()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Asset-Cluster-Klassifikation
# ─────────────────────────────────────────────────────────────────────────────

CLUSTERS: Tuple[str, ...] = ("CRYPTO", "US_EQUITIES", "EU_EQUITIES", "FOREX", "COMMODITIES")

_CRYPTO_EXCHANGES = {
    "BINANCE", "BINANCEUS", "COINBASE", "KRAKEN", "KUCOIN", "BITSTAMP", "POLONIEX",
    "CRYPTOCAP", "CRYPTO", "BYBIT", "OKX", "BITFINEX", "BITGET", "MEXC", "GATEIO",
    "HTX", "HUOBI", "GEMINI", "DERIBIT", "BITMEX", "PHEMEX", "BINGX", "HYPERLIQUID",
}
_US_EXCHANGES = {"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS", "CBOE", "OTC", "SP", "DJ", "RUSSELL", "IEX"}
_EU_EXCHANGES = {
    "TRADEGATE", "XETR", "XETRA", "FWB", "SWB", "GETTEX", "LSX", "LS", "EURONEXT", "LSE",
    "MIL", "BME", "SIX", "OMXSTO", "OMXCOP", "OMXHEX", "VIE", "EUREX", "HAM", "MUN", "BER", "DUS",
}
_FOREX_EXCHANGES = {"FX_IDC", "FX", "OANDA", "FOREXCOM", "SAXO", "IDC", "PEPPERSTONE", "ICMARKETS"}
_COMMODITY_EXCHANGES = {"NYMEX", "COMEX", "CBOT", "ICEEUR", "ICEUS", "LME", "MCX"}

# Yahoo-artige Börsen-Suffixe europäischer Handelsplätze (SAP.DE, TL0.F, ...).
_EU_SUFFIXES = {
    "DE", "F", "SG", "MU", "BE", "DU", "HM", "HA", "PA", "AS", "BR", "LS", "MI", "MC",
    "L", "SW", "VI", "ST", "CO", "HE", "OL", "IR", "WA",
}

_CRYPTO_BASES = {
    "BTC", "XBT", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "AVAX", "LINK", "DOT", "LTC",
    "BCH", "TRX", "TON", "SHIB", "MATIC", "POL", "UNI", "ATOM", "NEAR", "APT", "ARB", "OP",
    "SUI", "SEI", "INJ", "TIA", "RENDER", "RNDR", "FET", "TAO", "AAVE", "MKR", "CRV", "GMX",
    "PEPE", "WIF", "BONK", "HBAR", "XLM", "XMR", "ETC", "FIL", "ICP", "ALGO", "VET", "SAND",
    "MANA", "AXS", "BAT", "MOVR", "LYXE", "KAS", "STX", "IMX", "LDO", "RUNE", "JUP", "ENA",
    "HYPE", "ONDO", "PENDLE", "WLD", "PYTH", "JTO", "ORDI", "EOS", "XTZ", "ZEC", "DASH",
}
_CRYPTO_QUOTES = ("USDT", "USDC", "BUSD", "FDUSD", "TUSD", "DAI")
_CRYPTO_FUTURE_ROOTS = {"BTC", "MBT", "ETH", "MET", "SOL", "XRP"}
_CRYPTO_ETFS = {"IBIT", "FBTC", "GBTC", "BITO", "ARKB", "BITB", "ETHA", "ETHE", "FETH"}

_FIAT = {
    "USD", "EUR", "JPY", "GBP", "CHF", "AUD", "NZD", "CAD", "SEK", "NOK", "DKK", "PLN",
    "CZK", "HUF", "TRY", "ZAR", "MXN", "SGD", "HKD", "CNH", "CNY", "INR", "BRL", "KRW",
}
_FOREX_NAMES = {"DXY", "DX", "USDX", "EXY", "BXY", "JXY", "SXY", "CXY", "AXY", "ZXY"}
_FOREX_FUTURE_ROOTS = {"6E", "6J", "6B", "6A", "6C", "6S", "6N", "6M", "DX"}

_METALS = {"XAU", "XAG", "XPT", "XPD", "XCU"}
_COMMODITY_NAMES = {
    "GOLD", "SILVER", "PLATINUM", "PALLADIUM", "COPPER", "USOIL", "UKOIL", "WTI", "BRENT",
    "OIL", "OIL_CRUDE", "OIL_BRENT", "CRUDE", "NATGAS", "NATURALGAS", "NGAS", "CORN",
    "WHEAT", "SOYBEAN", "SOYBEANS", "COFFEE", "SUGAR", "COCOA", "COTTON", "ALUMINUM",
    "ALUMINIUM", "NICKEL", "ZINC", "LUMBER",
    # physisch besicherte / Futures-basierte Rohstoff-ETFs
    "GLD", "IAU", "SLV", "PPLT", "PALL", "USO", "BNO", "UNG", "DBC", "DBA", "CPER", "GDX", "GDXJ",
}
_COMMODITY_FUTURE_ROOTS = {
    "CL", "BZ", "BR", "NG", "HO", "RB", "GC", "MGC", "SI", "SIL", "HG", "PL", "PA",
    "ZC", "ZW", "ZS", "ZL", "ZM", "KC", "SB", "CC", "CT", "LE", "HE", "LBR",
}

_US_INDEX_NAMES = {
    "SPX", "SPX500", "US500", "NDX", "NAS100", "US100", "DJI", "US30", "RUT", "US2000",
    "VIX", "IXIC", "SPY", "QQQ", "DIA", "IWM",
}
_EU_INDEX_NAMES = {
    "DAX", "DEU40", "DE40", "GER40", "MDAX", "SDAX", "TECDAX", "SX5E", "EU50", "STOXX50",
    "CAC40", "FRA40", "PX1", "UKX", "UK100", "FTSE", "SMI", "IBEX35", "ESP35", "AEX", "FTSEMIB",
}
_US_FUTURE_ROOTS = {"ES", "MES", "NQ", "MNQ", "YM", "MYM", "RTY", "M2K"}
_EU_FUTURE_ROOTS = {"FDAX", "FDXM", "FDXS", "FESX", "FGBL", "Z"}

_FUTURE_RE = re.compile(r"^([A-Z0-9_]+?)[12]!$")          # Continuous Futures: CL1!, BTC1!
_CAT_CRYPTO_RE = re.compile(r"crypto|krypto|coin|defi|altcoin|blockchain|\bbtc\b|bitcoin")
_CAT_COMMODITY_RE = re.compile(
    r"rohstoff|commodit|edelmetall|metall|gold|silber|silver|\böl\b|\boil\b|energie-rohstoff|agrar")
_CAT_FOREX_RE = re.compile(r"forex|devisen|währung|waehrung|\bfx\b|currenc")
_CAT_INDEX_RE = re.compile(r"indiz|index|indices")
_CAT_US_RE = re.compile(r"\bus\b|\busa\b|nasdaq|nyse|s&p|wall ?street|amerika")
_CAT_EU_RE = re.compile(r"\beu\b|europ|\bdax\b|mdax|tradegate|xetra|deutsch|german|euro ?stoxx")


def _classify_by_ticker(exchange: str, ticker: str) -> Optional[str]:
    """Eindeutige Zuordnung allein aus Börsen-Präfix und Ticker; None wenn unklar."""
    # --- Krypto ---------------------------------------------------------------
    if exchange in _CRYPTO_EXCHANGES or exchange.startswith("UNISWAP") or exchange.startswith("PANCAKE"):
        return "CRYPTO"

    future = _FUTURE_RE.match(ticker)
    root = future.group(1) if future else None
    if root is not None:
        if root in _CRYPTO_FUTURE_ROOTS:
            return "CRYPTO"
        if root in _COMMODITY_FUTURE_ROOTS:
            return "COMMODITIES"
        if root in _FOREX_FUTURE_ROOTS:
            return "FOREX"
        if root in _US_FUTURE_ROOTS:
            return "US_EQUITIES"
        if root in _EU_FUTURE_ROOTS:
            return "EU_EQUITIES"

    base = re.sub(r"\.P$|PERP$|-PERP$", "", ticker)       # Perpetual-Suffixe entfernen
    compact = re.sub(r"[/\-_]", "", base)                 # BTC/USDT, BTC-USD -> BTCUSDT
    for quote in _CRYPTO_QUOTES:
        if compact.endswith(quote) and len(compact) > len(quote):
            return "CRYPTO"
    if compact in _CRYPTO_ETFS:
        return "CRYPTO"
    for quote in ("USD", "EUR", "BTC", "ETH"):
        if compact.endswith(quote) and compact[: -len(quote)] in _CRYPTO_BASES:
            return "CRYPTO"

    # --- Rohstoffe (vor Forex: XAUUSD ist Gold, kein Währungspaar) ---------------
    if compact[:3] in _METALS and (len(compact) == 3 or compact[3:] in _FIAT):
        return "COMMODITIES"
    if compact in _COMMODITY_NAMES or ticker in _COMMODITY_NAMES:
        return "COMMODITIES"
    if exchange in _COMMODITY_EXCHANGES:
        return "COMMODITIES"

    # --- Forex ----------------------------------------------------------------
    if len(compact) == 6 and compact[:3] in _FIAT and compact[3:] in _FIAT:
        return "FOREX"
    if compact in _FOREX_NAMES:
        return "FOREX"

    # --- Aktienindizes ----------------------------------------------------------
    if compact in _US_INDEX_NAMES:
        return "US_EQUITIES"
    if compact in _EU_INDEX_NAMES:
        return "EU_EQUITIES"

    if exchange in _FOREX_EXCHANGES:
        return "FOREX"
    return None


def classify_asset_cluster(symbol: str, category: Optional[str] = None) -> str:
    """
    Ordnet ein Symbol genau einem Risiko-Cluster zu:
    "CRYPTO", "US_EQUITIES", "EU_EQUITIES", "FOREX" oder "COMMODITIES".

    Reihenfolge der Evidenz:
      1. Eindeutige Asset-Klasse aus Börse/Ticker (BINANCE:…, …USDT, XAUUSD, EURUSD, CL1!, SPX)
      2. Asset-Klasse aus der Kategorie ("Crypto", "Edelmetalle", "Forex / Makro")
      3. Region aus der Kategorie ("US-Tech (EUR)" -> US, "Tradegate / EU" -> EU)
      4. Region aus Börsen-Präfix / Suffix (NASDAQ:… -> US, TRADEGATE:… / SAP.DE -> EU)
      5. Fallback: "US_EQUITIES" (Standard-Aktiencluster)

    Die Kategorie schlägt bei Aktien das Börsen-Präfix, weil das ökonomische
    Exposure zählt: eine US-Aktie auf Tradegate korreliert mit dem US-Markt.
    """
    sym = str(symbol or "").strip().upper()
    cat = str(category or "").strip().lower()

    exchange, _, ticker = sym.rpartition(":")
    exchange = exchange.split(":")[-1].strip()
    ticker = ticker.strip()

    # 1. Eindeutige Asset-Klasse aus dem Symbol
    by_ticker = _classify_by_ticker(exchange, ticker)
    if by_ticker is not None:
        return by_ticker

    # 2. Asset-Klasse aus der Kategorie
    if cat:
        if _CAT_CRYPTO_RE.search(cat):
            return "CRYPTO"
        if _CAT_COMMODITY_RE.search(cat):
            return "COMMODITIES"
        # "Indizes / Devisen" ist gemischt -> nicht pauschal als Forex werten
        if _CAT_FOREX_RE.search(cat) and not _CAT_INDEX_RE.search(cat):
            return "FOREX"
        # 3. Region aus der Kategorie
        if _CAT_US_RE.search(cat):
            return "US_EQUITIES"
        if _CAT_EU_RE.search(cat):
            return "EU_EQUITIES"

    # 4. Region aus Börsen-Präfix / Suffix
    if exchange in _US_EXCHANGES:
        return "US_EQUITIES"
    if exchange in _EU_EXCHANGES:
        return "EU_EQUITIES"
    if "." in ticker and ticker.rsplit(".", 1)[1] in _EU_SUFFIXES:
        return "EU_EQUITIES"

    # 5. Fallback
    return "US_EQUITIES"


# ─────────────────────────────────────────────────────────────────────────────
# Interne Helfer
# ─────────────────────────────────────────────────────────────────────────────

def _to_float(value: Any) -> Optional[float]:
    """Robuste Float-Konvertierung; None bei fehlenden/ungültigen/nicht-endlichen Werten."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _to_utc(value: Any) -> Optional[datetime]:
    """
    Wandelt datetime / ISO-String / Epoch (s oder ms) in ein UTC-datetime um.
    Naive Zeitstempel (ohne Zeitzone) werden als UTC interpretiert.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        if not math.isfinite(value) or value <= 0:
            return None
        seconds = value / 1000.0 if value > 1e11 else float(value)
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            try:
                dt = datetime.fromisoformat(text.replace(" ", "T", 1)[:19])
            except ValueError:
                return None
    else:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


_R_KEYS = ("realized_r", "pnl_r", "r_multiple", "realized_pnl_r", "result_r")
_EXIT_TIME_KEYS = ("exit_time", "closed_at", "close_time", "exit_timestamp", "closed_time")


def _trade_r(trade: Dict[str, Any]) -> Optional[float]:
    """
    Realisiertes Ergebnis eines geschlossenen Trades in R.
      1. explizites R-Feld (realized_r, pnl_r, r_multiple, ...)
      2. realized_pnl_cash / risk_cash
      3. realized_pnl_pct / initialer Stop-Abstand in %  (initial_stop_loss bzw. stop_loss)
    None, wenn sich R nicht bestimmen lässt.
    """
    for key in _R_KEYS:
        r = _to_float(trade.get(key))
        if r is not None:
            return r

    pnl_cash = _to_float(trade.get("realized_pnl_cash"))
    risk_cash = _to_float(trade.get("risk_cash"))
    if pnl_cash is not None and risk_cash is not None and risk_cash > 0:
        return pnl_cash / risk_cash

    pnl_pct = _to_float(trade.get("realized_pnl_pct"))
    entry = _to_float(trade.get("entry_price"))
    stop = _to_float(trade.get("initial_stop_loss"))
    if stop is None or stop <= 0:
        stop = _to_float(trade.get("stop_loss"))
    if pnl_pct is not None and entry is not None and entry > 0 and stop is not None and stop > 0:
        stop_pct = abs(entry - stop) / entry * 100.0
        if stop_pct > 0:
            return pnl_pct / stop_pct
    return None


def _trade_exit_time(trade: Dict[str, Any]) -> Optional[datetime]:
    for key in _EXIT_TIME_KEYS:
        dt = _to_utc(trade.get(key))
        if dt is not None:
            return dt
    return None


_OPEN_RISK_KEYS = ("open_risk_r", "current_risk_r", "risk_r")
_CLOSED_STATUSES = {"CLOSED", "CANCELLED", "CANCELED", "EXITED", "STOPPED"}


def _open_risk_r(trade: Dict[str, Any]) -> float:
    """
    Aktuell offenes Risiko einer laufenden Position in R (>= 0).
      1. explizites Feld (open_risk_r, current_risk_r, risk_r)
      2. mit initial_stop_loss: verbleibender Stop-Abstand / initialer Stop-Abstand
      3. sonst: 0.0R, wenn der Stop auf/über Breakeven liegt, andernfalls konservativ 1.0R
    Nach einer 50%-Teilgewinnmitnahme (tp1_partial_closed) halbiert sich das Rest-Risiko.
    """
    for key in _OPEN_RISK_KEYS:
        if key in trade and trade.get(key) is not None:
            explicit = _to_float(trade.get(key))
            # Ungültiger expliziter Wert -> konservativ volles 1R annehmen
            return max(0.0, explicit) if explicit is not None else 1.0

    risk = 1.0
    entry = _to_float(trade.get("entry_price"))
    stop = _to_float(trade.get("stop_loss"))
    direction = str(trade.get("direction") or trade.get("side") or "").strip().upper()
    is_long = direction in ("LONG", "BUY")
    is_short = direction in ("SHORT", "SELL")

    if entry is not None and entry > 0 and stop is not None and stop > 0 and (is_long or is_short):
        remaining = (entry - stop) if is_long else (stop - entry)
        initial_stop = _to_float(trade.get("initial_stop_loss"))
        initial = None
        if initial_stop is not None and initial_stop > 0:
            initial = (entry - initial_stop) if is_long else (initial_stop - entry)
        if remaining <= 0:
            risk = 0.0                       # Stop auf/über Breakeven -> risikofrei
        elif initial is not None and initial > 0:
            risk = remaining / initial       # nachgezogener Stop reduziert das offene R

    if trade.get("tp1_partial_closed"):
        risk *= 0.5
    return max(0.0, risk)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Drawdown-Circuit-Breaker
# ─────────────────────────────────────────────────────────────────────────────

def check_drawdown_circuit_breaker(
    closed_trades: List[Dict[str, Any]],
    current_time: Optional[datetime] = None,
    config: CircuitBreakerConfig = DEFAULT_CONFIG,
) -> Dict[str, Any]:
    """
    Prüft Tagesverlust- und Drawdown-Limits anhand der geschlossenen Trades.

    * daily_pnl_r : Summe der R aller Trades, deren Exit auf den UTC-Kalendertag
                    von `current_time` fällt.
    * drawdown_r  : aktueller Abstand der kumulierten R-Equity-Kurve zu ihrem
                    Höchststand (>= 0; die Kurve startet bei 0R).

    Priorität: HALT_FULL > HALT_DAY > REDUCE_SIZE > ALLOW.

    Rückgabe: is_halted, action, sizing_multiplier (1.0 / 0.5 / 0.0), daily_pnl_r,
    drawdown_r, reason — plus Diagnosefelder (max_drawdown_r, cumulative_r, peak_r,
    trades_today, trades_evaluated, unresolved_trades, effective_risk_pct).

    Trades ohne bestimmbares R werden NICHT geschätzt, sondern übersprungen und in
    `unresolved_trades` gezählt — ein Wert > 0 bedeutet, dass der Breaker blind
    für diese Trades ist.
    """
    now = _to_utc(current_time) or datetime.now(timezone.utc)
    today = now.date()

    # (Exit-Zeit, Original-Index, R) — undatierte Trades erben den Zeitstempel ihres
    # Vorgängers in der Liste, damit die Reihenfolge der Historie erhalten bleibt.
    rows: List[Tuple[datetime, int, float, bool]] = []
    unresolved = 0
    last_time = datetime.min.replace(tzinfo=timezone.utc)
    for idx, trade in enumerate(closed_trades or []):
        if not isinstance(trade, dict):
            unresolved += 1
            continue
        r = _trade_r(trade)
        exit_time = _trade_exit_time(trade)
        if exit_time is not None:
            last_time = exit_time
        if r is None:
            unresolved += 1
            continue
        rows.append((exit_time or last_time, idx, r, exit_time is not None))
    rows.sort(key=lambda row: (row[0], row[1]))

    daily_pnl_r = 0.0
    trades_today = 0
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for exit_time, _, r, dated in rows:
        if dated and exit_time > now:
            continue                         # Zukunfts-Trades (Backtest-Replay) ignorieren
        cumulative += r
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)
        if dated and exit_time.date() == today:
            daily_pnl_r += r
            trades_today += 1
    drawdown_r = max(0.0, peak - cumulative)

    if drawdown_r >= config.drawdown_halt_r - _EPS:
        action, multiplier = "HALT_FULL", 0.0
        reason = (f"Drawdown -{drawdown_r:.2f}R vom Höchststand erreicht das Halt-Limit "
                  f"-{config.drawdown_halt_r:.1f}R: System vollständig gestoppt, Strategy-Review erforderlich.")
    elif daily_pnl_r <= -config.daily_loss_limit_r + _EPS:
        action, multiplier = "HALT_DAY", 0.0
        reason = (f"Tagesverlust {daily_pnl_r:+.2f}R erreicht das Tageslimit "
                  f"-{config.daily_loss_limit_r:.1f}R: keine neuen Einstiege bis zum nächsten UTC-Tag.")
    elif drawdown_r >= config.drawdown_reduce_r - _EPS:
        action, multiplier = "REDUCE_SIZE", 0.5
        reason = (f"Drawdown -{drawdown_r:.2f}R vom Höchststand erreicht das Reduktions-Limit "
                  f"-{config.drawdown_reduce_r:.1f}R: Positionsgröße halbiert.")
    else:
        action, multiplier = "ALLOW", 1.0
        reason = (f"Innerhalb aller Limits (Tag {daily_pnl_r:+.2f}R, Drawdown -{drawdown_r:.2f}R).")

    if unresolved:
        reason += f" WARNUNG: {unresolved} Trade(s) ohne bestimmbares R nicht berücksichtigt."

    return {
        "is_halted": multiplier == 0.0,
        "action": action,
        "sizing_multiplier": multiplier,
        "daily_pnl_r": round(daily_pnl_r, 4),
        "drawdown_r": round(drawdown_r, 4),
        "reason": reason,
        # Diagnose
        "max_drawdown_r": round(max_drawdown, 4),
        "cumulative_r": round(cumulative, 4),
        "peak_r": round(peak, 4),
        "trades_today": trades_today,
        "trades_evaluated": len(rows),
        "unresolved_trades": unresolved,
        "effective_risk_pct": round(config.flat_risk_pct * multiplier, 4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Portfolio-Heat / Cluster-Limit
# ─────────────────────────────────────────────────────────────────────────────

def check_cluster_heat_limit(
    active_trades: List[Dict[str, Any]],
    candidate_symbol: str,
    candidate_category: Optional[str] = None,
    candidate_risk_r: float = 1.0,
    config: CircuitBreakerConfig = DEFAULT_CONFIG,
) -> Dict[str, Any]:
    """
    Prüft, ob ein neuer Trade in das Risiko-Budget passt.

    `total_heat_r` / `cluster_heat_r` sind das AKTUELL offene Risiko (ohne den
    Kandidaten); `projected_*` enthält den Stand inklusive Kandidat. Abgelehnt
    wird, wenn der projizierte Wert ein Limit überschreitet.

    Rückgabe: is_allowed, total_heat_r, cluster_heat_r, rejection_reason
    (leer bei Freigabe) — plus cluster, projected_total_heat_r,
    projected_cluster_heat_r, heat_by_cluster.
    """
    cluster = classify_asset_cluster(candidate_symbol, candidate_category)

    heat_by_cluster: Dict[str, float] = {name: 0.0 for name in CLUSTERS}
    for trade in active_trades or []:
        if not isinstance(trade, dict):
            continue
        if str(trade.get("status") or "").strip().upper() in _CLOSED_STATUSES:
            continue
        trade_cluster = classify_asset_cluster(str(trade.get("symbol") or ""), trade.get("category"))
        heat_by_cluster[trade_cluster] += _open_risk_r(trade)

    total_heat = sum(heat_by_cluster.values())
    cluster_heat = heat_by_cluster[cluster]

    risk = _to_float(candidate_risk_r)
    reasons: List[str] = []
    if risk is None or risk <= 0:
        reasons.append(f"Ungültiges Kandidaten-Risiko ({candidate_risk_r!r}R): muss endlich und > 0 sein.")
        projected_total, projected_cluster = total_heat, cluster_heat
    else:
        projected_total = total_heat + risk
        projected_cluster = cluster_heat + risk
        if projected_cluster > config.max_cluster_heat_r + _EPS:
            reasons.append(
                f"Cluster-Limit {cluster}: {cluster_heat:.2f}R offen + {risk:.2f}R neu = "
                f"{projected_cluster:.2f}R > {config.max_cluster_heat_r:.2f}R.")
        if projected_total > config.max_total_heat_r + _EPS:
            reasons.append(
                f"Gesamt-Heat: {total_heat:.2f}R offen + {risk:.2f}R neu = "
                f"{projected_total:.2f}R > {config.max_total_heat_r:.2f}R.")

    return {
        "is_allowed": not reasons,
        "total_heat_r": round(total_heat, 4),
        "cluster_heat_r": round(cluster_heat, 4),
        "rejection_reason": " | ".join(reasons),
        # Diagnose
        "cluster": cluster,
        "projected_total_heat_r": round(projected_total, 4),
        "projected_cluster_heat_r": round(projected_cluster, 4),
        "heat_by_cluster": {name: round(value, 4) for name, value in heat_by_cluster.items()},
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. Kosten-Gate
# ─────────────────────────────────────────────────────────────────────────────

def check_cost_gate(
    entry_price: float,
    stop_loss: float,
    fee_pct: float = 0.055,
    spread_pct: float = 0.03,
    slippage_pct: float = 0.02,
    config: CircuitBreakerConfig = DEFAULT_CONFIG,
) -> Dict[str, Any]:
    """
    Prüft, ob die Round-Trip-Reibung im Verhältnis zum Stop-Abstand tragbar ist.

        total_cost_pct = 2 * fee_pct + spread_pct + slippage_pct     (Default 0.16 %)
        stop_pct       = |entry - stop| / entry * 100
        cost_r         = total_cost_pct / stop_pct

    Alle Prozentwerte in Prozentpunkten (0.055 = 0.055 %). Abgelehnt wird bei
    cost_r > config.max_cost_r_ratio oder ungültigen Eingaben (dann cost_r = inf).

    Rückgabe: is_allowed, cost_r, rejection_reason (leer bei Freigabe) — plus
    total_cost_pct, stop_pct, min_stop_pct (kleinster zulässiger Stop-Abstand).
    """
    entry = _to_float(entry_price)
    stop = _to_float(stop_loss)
    fee = _to_float(fee_pct)
    spread = _to_float(spread_pct)
    slippage = _to_float(slippage_pct)

    def _reject(reason: str, total_cost: float = math.nan, stop_dist: float = 0.0) -> Dict[str, Any]:
        return {
            "is_allowed": False,
            "cost_r": math.inf,
            "rejection_reason": reason,
            "total_cost_pct": total_cost,
            "stop_pct": stop_dist,
            "min_stop_pct": (round(total_cost / config.max_cost_r_ratio, 6)
                             if math.isfinite(total_cost) else math.nan),
        }

    if fee is None or spread is None or slippage is None or min(fee, spread, slippage) < 0:
        return _reject("Ungültige Kostenparameter: fee/spread/slippage müssen endlich und >= 0 sein.")
    total_cost_pct = 2.0 * fee + spread + slippage

    if entry is None or entry <= 0:
        return _reject(f"Ungültiger Einstiegspreis ({entry_price!r}): muss endlich und > 0 sein.", total_cost_pct)
    if stop is None or stop <= 0:
        return _reject(f"Ungültiger Stop-Loss ({stop_loss!r}): muss endlich und > 0 sein.", total_cost_pct)

    stop_pct = abs(entry - stop) / entry * 100.0
    if stop_pct <= 0:
        return _reject("Stop-Abstand ist 0: Stop-Loss liegt auf dem Einstiegspreis.", total_cost_pct)

    cost_r = total_cost_pct / stop_pct
    is_allowed = cost_r <= config.max_cost_r_ratio + _EPS
    min_stop_pct = total_cost_pct / config.max_cost_r_ratio
    reason = "" if is_allowed else (
        f"Kosten-Gate: Reibung {total_cost_pct:.3f}% bei Stop-Abstand {stop_pct:.3f}% = "
        f"{cost_r:.2f}R > {config.max_cost_r_ratio:.2f}R. Mindest-Stop-Abstand: {min_stop_pct:.2f}%.")

    return {
        "is_allowed": is_allowed,
        "cost_r": round(cost_r, 6),
        "rejection_reason": reason,
        "total_cost_pct": round(total_cost_pct, 6),
        "stop_pct": round(stop_pct, 6),
        "min_stop_pct": round(min_stop_pct, 6),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Standalone Unit-Tests
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from datetime import timedelta

    _failures: List[str] = []
    _count = 0

    def check(name: str, condition: bool, detail: Any = "") -> None:
        """Eigener Assert-Ersatz (funktioniert auch unter `python -O`)."""
        global _count
        _count += 1
        if condition:
            print(f"  ✅ {name}")
        else:
            _failures.append(name)
            print(f"  ❌ {name}  {detail}")

    NOW = datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc)

    def closed(r: float, hours_ago: float = 1.0, **extra: Any) -> Dict[str, Any]:
        trade = {"symbol": "BINANCE:BTCUSDT", "realized_r": r,
                 "exit_time": (NOW - timedelta(hours=hours_ago)).isoformat()}
        trade.update(extra)
        return trade

    def open_trade(symbol: str, category: str = "", **extra: Any) -> Dict[str, Any]:
        trade: Dict[str, Any] = {"symbol": symbol, "category": category, "status": "OPEN"}
        trade.update(extra)
        return trade

    # ── Config ───────────────────────────────────────────────────────────────
    print("\n[1] CircuitBreakerConfig")
    cfg = CircuitBreakerConfig()
    check("Defaults wie spezifiziert",
          (cfg.daily_loss_limit_r, cfg.drawdown_reduce_r, cfg.drawdown_halt_r, cfg.max_total_heat_r,
           cfg.max_cluster_heat_r, cfg.flat_risk_pct, cfg.max_cost_r_ratio)
          == (3.0, 10.0, 15.0, 3.0, 1.5, 0.5, 0.10))
    for bad in ({"daily_loss_limit_r": -3.0}, {"max_cost_r_ratio": 0.0},
                {"max_total_heat_r": float("nan")}, {"drawdown_reduce_r": 20.0}):
        try:
            CircuitBreakerConfig(**bad)
            check(f"Ungültige Config {bad} wird abgelehnt", False)
        except ValueError:
            check(f"Ungültige Config {bad} wird abgelehnt", True)

    # ── Cluster-Klassifikation ────────────────────────────────────────────────
    print("\n[2] classify_asset_cluster")
    cluster_cases = [
        ("BINANCE:BTCUSDT", None, "CRYPTO"),
        ("BTCUSDT", None, "CRYPTO"),
        ("SOLUSDT", "Micro-Incubator (5m)", "CRYPTO"),
        ("KRAKEN:LINKUSD", "Crypto", "CRYPTO"),
        ("COINBASE:ETHBTC", None, "CRYPTO"),
        ("CME:BTC1!", None, "CRYPTO"),
        ("CRYPTOCAP:TOTAL", "Krypto-Makro", "CRYPTO"),
        ("ETH/USDT", None, "CRYPTO"),
        ("UNKNOWNCOIN", "Crypto", "CRYPTO"),
        ("NASDAQ:MSFT", "Big Tech", "US_EQUITIES"),
        ("NYSE:UBER", None, "US_EQUITIES"),
        ("AMEX:SPY", "Indizes", "US_EQUITIES"),
        ("SP:SPX", "Indizes / Devisen", "US_EQUITIES"),
        ("AAPL", None, "US_EQUITIES"),
        ("TRADEGATE:45C", "US-Tech (EUR)", "US_EQUITIES"),
        ("TRADEGATE:9MW", "Tradegate / EU", "EU_EQUITIES"),
        ("TRADEGATE:PTX", "Aktien", "EU_EQUITIES"),
        ("XETR:SAP", None, "EU_EQUITIES"),
        ("SAP.DE", None, "EU_EQUITIES"),
        ("TL0.F", None, "EU_EQUITIES"),
        ("TVC:DAX", "Indizes / Devisen", "EU_EQUITIES"),
        ("FX_IDC:EURUSD", None, "FOREX"),
        ("OANDA:GBPJPY", "Forex / Makro", "FOREX"),
        ("EURUSD", None, "FOREX"),
        ("TVC:DXY", "Indizes / Devisen", "FOREX"),
        ("FX_IDC:XAUUSD", "Edelmetalle", "COMMODITIES"),
        ("OANDA:XAGUSD", None, "COMMODITIES"),
        ("AMEX:GLD", None, "COMMODITIES"),
        ("NYMEX:CL1!", None, "COMMODITIES"),
        ("RUS:BR1!", None, "COMMODITIES"),
        ("CAPITALCOM:CORN", None, "COMMODITIES"),
        ("NYSE:NEM", "Edelmetall-Minen", "COMMODITIES"),
        ("", None, "US_EQUITIES"),
    ]
    for sym, cat, expected in cluster_cases:
        got = classify_asset_cluster(sym, cat)
        check(f"{sym or '<leer>':<18} [{cat or '-'}] -> {expected}", got == expected, f"(erhalten: {got})")
    check("Ergebnis liegt immer in CLUSTERS",
          all(classify_asset_cluster(s, c) in CLUSTERS for s, c, _ in cluster_cases))

    # ── Drawdown-Circuit-Breaker ──────────────────────────────────────────────
    print("\n[3] check_drawdown_circuit_breaker")
    res = check_drawdown_circuit_breaker([], NOW)
    check("Leere Historie -> ALLOW, Multiplikator 1.0",
          res["action"] == "ALLOW" and res["sizing_multiplier"] == 1.0 and not res["is_halted"], res)

    res = check_drawdown_circuit_breaker([closed(-1.0, 5), closed(-1.5, 3), closed(-1.0, 1)], NOW)
    check("Tagesverlust -3.5R -> HALT_DAY (Blockade)",
          res["action"] == "HALT_DAY" and res["is_halted"] and res["sizing_multiplier"] == 0.0
          and math.isclose(res["daily_pnl_r"], -3.5), res)

    res = check_drawdown_circuit_breaker([closed(-1.0, 3), closed(-1.0, 2), closed(-1.0, 1)], NOW)
    check("Tagesverlust exakt -3.0R -> HALT_DAY (Grenze inklusiv)", res["action"] == "HALT_DAY", res)

    res = check_drawdown_circuit_breaker([closed(-1.0, 3), closed(-1.0, 2), closed(-0.9, 1)], NOW)
    check("Tagesverlust -2.9R -> ALLOW", res["action"] == "ALLOW" and not res["is_halted"], res)

    res = check_drawdown_circuit_breaker([closed(-2.0, 30), closed(-2.0, 20), closed(-1.0, 1)], NOW)
    check("Verluste von gestern zählen nicht zum Tages-PnL (UTC-Tag)",
          res["action"] == "ALLOW" and math.isclose(res["daily_pnl_r"], -1.0)
          and math.isclose(res["drawdown_r"], 5.0), res)

    res = check_drawdown_circuit_breaker([closed(-3.5, 15.5)], NOW)   # 23:30 UTC am Vortag
    check("Trade 23:30 UTC am Vortag -> heute 0R, ALLOW",
          res["action"] == "ALLOW" and res["daily_pnl_r"] == 0.0, res)

    res = check_drawdown_circuit_breaker([closed(-4.0, 2), closed(+1.5, 1)], NOW)
    check("Tagesverlust wird durch Gewinne netto gerechnet (-2.5R -> ALLOW)",
          res["action"] == "ALLOW" and math.isclose(res["daily_pnl_r"], -2.5), res)

    # +5R Peak, danach 10 Verlusttage à -1R  => Drawdown 10R
    history = [closed(+5.0, 24 * 20)] + [closed(-1.0, 24 * d) for d in range(11, 1, -1)]
    res = check_drawdown_circuit_breaker(history, NOW)
    check("Drawdown -10R vom Peak -> REDUCE_SIZE, Multiplikator 0.5",
          res["action"] == "REDUCE_SIZE" and res["sizing_multiplier"] == 0.5 and not res["is_halted"]
          and math.isclose(res["drawdown_r"], 10.0) and math.isclose(res["peak_r"], 5.0)
          and math.isclose(res["effective_risk_pct"], 0.25), res)

    res = check_drawdown_circuit_breaker(history[:-1], NOW)
    check("Drawdown -9R -> ALLOW", res["action"] == "ALLOW" and math.isclose(res["drawdown_r"], 9.0), res)

    history15 = [closed(+5.0, 24 * 30)] + [closed(-1.0, 24 * d) for d in range(16, 1, -1)]
    res = check_drawdown_circuit_breaker(history15, NOW)
    check("Drawdown -15R vom Peak -> HALT_FULL, Multiplikator 0.0",
          res["action"] == "HALT_FULL" and res["is_halted"] and res["sizing_multiplier"] == 0.0
          and math.isclose(res["drawdown_r"], 15.0), res)

    res = check_drawdown_circuit_breaker(history15 + [closed(-3.5, 1)], NOW)
    check("HALT_FULL hat Vorrang vor HALT_DAY", res["action"] == "HALT_FULL", res)

    res = check_drawdown_circuit_breaker(history + [closed(-3.0, 1)], NOW)
    check("HALT_DAY hat Vorrang vor REDUCE_SIZE", res["action"] == "HALT_DAY", res)

    recovered = [closed(+2.0, 24 * 40)] + [closed(-1.0, 24 * d) for d in range(30, 18, -1)] \
        + [closed(+3.0, 24 * d) for d in range(10, 5, -1)]
    res = check_drawdown_circuit_breaker(recovered, NOW)
    check("Erholter Drawdown (neues Hoch) -> ALLOW, max_drawdown_r bleibt dokumentiert",
          res["action"] == "ALLOW" and res["drawdown_r"] == 0.0 and math.isclose(res["max_drawdown_r"], 12.0), res)

    shuffled = list(reversed(history))
    res = check_drawdown_circuit_breaker(shuffled, NOW)
    check("Unsortierte Historie wird chronologisch ausgewertet",
          res["action"] == "REDUCE_SIZE" and math.isclose(res["drawdown_r"], 10.0), res)

    mixed = [
        {"pnl_r": -1.0, "closed_at": "2026-11-14T10:00:00Z"},                       # alternatives Feld + Z
        {"realized_pnl_cash": -50.0, "risk_cash": 50.0, "exit_time": "2026-11-14T11:00:00"},   # naive = UTC
        {"realized_pnl_pct": -2.0, "entry_price": 100.0, "stop_loss": 98.0,
         "exit_time": "2026-11-14T13:00:00+01:00"},                                 # 12:00 UTC, -1R
        {"realized_r": -0.5, "exit_time": (NOW - timedelta(hours=1)).timestamp()},  # Epoch
    ]
    res = check_drawdown_circuit_breaker(mixed, NOW)
    check("R aus pnl_r / Cash / Prozent+Stop und gemischte Zeitformate -> -3.5R, HALT_DAY",
          res["action"] == "HALT_DAY" and math.isclose(res["daily_pnl_r"], -3.5)
          and res["unresolved_trades"] == 0, res)

    res = check_drawdown_circuit_breaker(
        [{"realized_pnl_pct": -4.0, "exit_time": NOW.isoformat()}, {"realized_r": "kaputt"},
         {"realized_r": float("nan")}, None, closed(-1.0, 1)], NOW)  # type: ignore[list-item]
    check("Trades ohne bestimmbares R werden gezählt und gemeldet, kein Crash",
          res["unresolved_trades"] == 4 and math.isclose(res["daily_pnl_r"], -1.0)
          and "WARNUNG" in res["reason"], res)

    res = check_drawdown_circuit_breaker([closed(-3.5, 1)], NOW.replace(tzinfo=None))
    check("Naives current_time wird als UTC interpretiert", res["action"] == "HALT_DAY", res)

    res = check_drawdown_circuit_breaker([closed(-3.5, -2)], NOW)
    check("Trades nach current_time (Replay) werden ignoriert", res["action"] == "ALLOW", res)

    res = check_drawdown_circuit_breaker([closed(-1.0, 1)], NOW, CircuitBreakerConfig(daily_loss_limit_r=1.0))
    check("Eigene Config wird respektiert (Tageslimit 1R)", res["action"] == "HALT_DAY", res)

    # ── Cluster-Heat ──────────────────────────────────────────────────────────
    print("\n[4] check_cluster_heat_limit")
    two_crypto = [open_trade("BINANCE:BTCUSDT", "Crypto"), open_trade("ETHUSDT", "Crypto")]

    res = check_cluster_heat_limit(two_crypto, "BINANCE:SOLUSDT", "Crypto")
    check("2 Krypto-Trades offen -> 3. Krypto-Trade blockiert (Cluster-Limit 1.5R)",
          not res["is_allowed"] and res["cluster"] == "CRYPTO" and math.isclose(res["cluster_heat_r"], 2.0)
          and "Cluster-Limit CRYPTO" in res["rejection_reason"], res)

    res = check_cluster_heat_limit(two_crypto, "NASDAQ:MSFT", "Big Tech")
    check("2 Krypto-Trades offen -> US-Aktientrade erlaubt (2.0R + 1.0R = 3.0R, Grenze inklusiv)",
          res["is_allowed"] and res["cluster"] == "US_EQUITIES" and res["cluster_heat_r"] == 0.0
          and math.isclose(res["total_heat_r"], 2.0) and res["rejection_reason"] == "", res)

    res = check_cluster_heat_limit([], "BINANCE:BTCUSDT")
    check("Leeres Portfolio -> 1. Krypto-Trade erlaubt", res["is_allowed"] and res["total_heat_r"] == 0.0, res)

    res = check_cluster_heat_limit(two_crypto[:1], "ETHUSDT")
    check("1 Krypto-Trade (1.0R) offen -> 2. Krypto-Trade mit 1.0R blockiert (2.0R > 1.5R)",
          not res["is_allowed"], res)

    res = check_cluster_heat_limit(two_crypto[:1], "ETHUSDT", candidate_risk_r=0.5)
    check("1 Krypto-Trade (1.0R) offen -> 2. Krypto-Trade mit 0.5R erlaubt (exakt 1.5R)", res["is_allowed"], res)

    half = [open_trade("BTCUSDT", risk_r=0.75), open_trade("ETHUSDT", risk_r=0.75)]
    res = check_cluster_heat_limit(half, "SOLUSDT", candidate_risk_r=0.5)
    check("2 Krypto-Trades à 0.75R (= 1.5R) -> 3. Krypto-Trade blockiert",
          not res["is_allowed"] and math.isclose(res["cluster_heat_r"], 1.5), res)

    nine = [open_trade(f"BINANCE:{c}USDT", "Crypto") for c in
            ("BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "AVAX", "LINK")]
    res = check_cluster_heat_limit(nine, "NASDAQ:NVDA")
    check("9 Krypto-Longs offen -> auch US-Trade blockiert (Gesamt-Heat 9R)",
          not res["is_allowed"] and math.isclose(res["total_heat_r"], 9.0)
          and "Gesamt-Heat" in res["rejection_reason"], res)

    diversified = [open_trade("BTCUSDT"), open_trade("NASDAQ:MSFT"), open_trade("XETR:SAP")]
    res = check_cluster_heat_limit(diversified, "FX_IDC:EURUSD")
    check("3.0R über 3 Cluster verteilt -> Forex-Trade blockiert (Gesamt-Heat 4.0R)",
          not res["is_allowed"] and "Gesamt-Heat" in res["rejection_reason"]
          and "Cluster-Limit" not in res["rejection_reason"], res)

    us_eu = [open_trade("NASDAQ:MSFT", "Big Tech"), open_trade("TRADEGATE:9MW", "Tradegate / EU")]
    res = check_cluster_heat_limit(us_eu, "NYSE:UBER", "Mobility / Tech")
    check("US- und EU-Aktien sind getrennte Cluster; 2. US-Trade mit 1R blockiert",
          not res["is_allowed"] and math.isclose(res["cluster_heat_r"], 1.0), res)

    breakeven = [
        open_trade("BTCUSDT", direction="LONG", entry_price=100.0, stop_loss=100.0),   # Stop auf BE
        open_trade("ETHUSDT", direction="SHORT", entry_price=100.0, stop_loss=99.0),   # Stop im Gewinn
    ]
    res = check_cluster_heat_limit(breakeven, "SOLUSDT")
    check("Positionen mit Stop auf/über Breakeven tragen 0R Heat",
          res["is_allowed"] and res["total_heat_r"] == 0.0, res)

    trailed = [open_trade("BTCUSDT", direction="LONG", entry_price=100.0, stop_loss=98.0,
                          initial_stop_loss=96.0, tp1_partial_closed=True)]
    res = check_cluster_heat_limit(trailed, "ETHUSDT")
    check("Nachgezogener Stop + Teil-TP reduziert offenes R (0.5 * 0.5 = 0.25R)",
          res["is_allowed"] and math.isclose(res["cluster_heat_r"], 0.25), res)

    res = check_cluster_heat_limit(
        [open_trade("BTCUSDT", direction="LONG", entry_price=100.0, stop_loss=0.0),
         open_trade("ETHUSDT", status="CLOSED"), open_trade("SOLUSDT", risk_r="kaputt")], "XRPUSDT")
    check("Fehlender Stop / kaputtes Risiko -> konservativ 1R; geschlossene Trades ignoriert",
          not res["is_allowed"] and math.isclose(res["cluster_heat_r"], 2.0), res)

    for bad_risk in (0.0, -1.0, float("nan"), float("inf")):
        res = check_cluster_heat_limit([], "BTCUSDT", candidate_risk_r=bad_risk)
        check(f"Ungültiges Kandidaten-Risiko {bad_risk} -> abgelehnt (fail-closed)", not res["is_allowed"], res)

    res = check_cluster_heat_limit(two_crypto, "SOLUSDT", config=CircuitBreakerConfig(
        max_cluster_heat_r=3.0, max_total_heat_r=5.0))
    check("Eigene Config wird respektiert (Cluster-Limit 3R)", res["is_allowed"], res)

    snapshot = [dict(t) for t in two_crypto]
    check_cluster_heat_limit(two_crypto, "SOLUSDT")
    check("Eingabe-Trades werden nicht verändert", two_crypto == snapshot)

    # ── Kosten-Gate ───────────────────────────────────────────────────────────
    print("\n[5] check_cost_gate")
    res = check_cost_gate(100.0, 99.8)
    check("Stop zu eng (0.2%) -> blockiert (0.16% / 0.2% = 0.80R)",
          not res["is_allowed"] and math.isclose(res["cost_r"], 0.8, rel_tol=1e-6)
          and math.isclose(res["total_cost_pct"], 0.16) and math.isclose(res["stop_pct"], 0.2, rel_tol=1e-6)
          and "Kosten-Gate" in res["rejection_reason"], res)

    res = check_cost_gate(100.0, 98.0)
    check("Stop 2.0% -> erlaubt (0.08R)",
          res["is_allowed"] and math.isclose(res["cost_r"], 0.08, rel_tol=1e-6)
          and res["rejection_reason"] == "", res)

    res = check_cost_gate(100.0, 98.4)
    check("Stop 1.6% -> exakt 0.10R, erlaubt (Grenze inklusiv)",
          res["is_allowed"] and math.isclose(res["cost_r"], 0.10, rel_tol=1e-6)
          and math.isclose(res["min_stop_pct"], 1.6), res)

    res = check_cost_gate(100.0, 98.5)
    check("Stop 1.5% -> 0.107R, blockiert", not res["is_allowed"], res)

    res = check_cost_gate(100.0, 102.0)
    check("Short (Stop über Entry, 2.0%) -> erlaubt",
          res["is_allowed"] and math.isclose(res["cost_r"], 0.08, rel_tol=1e-6), res)

    res = check_cost_gate(65000.0, 64350.0, fee_pct=0.1, spread_pct=0.05, slippage_pct=0.05)
    check("Höhere Kosten (0.30%) bei 1.0% Stop -> blockiert (0.30R)",
          not res["is_allowed"] and math.isclose(res["cost_r"], 0.3, rel_tol=1e-6), res)

    res = check_cost_gate(100.0, 99.8, fee_pct=0.0, spread_pct=0.01, slippage_pct=0.01)
    check("Enger Stop mit sehr niedrigen Kosten (0.02%) -> erlaubt (0.10R)", res["is_allowed"], res)

    invalid_inputs = [
        ("Stop == Entry", (100.0, 100.0), {}),
        ("Entry 0", (0.0, 99.0), {}),
        ("Entry negativ", (-100.0, 99.0), {}),
        ("Stop 0", (100.0, 0.0), {}),
        ("Entry NaN", (float("nan"), 99.0), {}),
        ("Stop inf", (100.0, float("inf")), {}),
        ("Entry None", (None, 99.0), {}),
        ("Negative Fee", (100.0, 98.0), {"fee_pct": -0.5}),
        ("Spread NaN", (100.0, 98.0), {"spread_pct": float("nan")}),
    ]
    for label, args, kwargs in invalid_inputs:
        res = check_cost_gate(*args, **kwargs)  # type: ignore[arg-type]
        check(f"Ungültige Eingabe ({label}) -> abgelehnt, cost_r = inf",
              not res["is_allowed"] and res["cost_r"] == math.inf and bool(res["rejection_reason"]), res)

    res = check_cost_gate(100.0, 99.0, config=CircuitBreakerConfig(max_cost_r_ratio=0.20))
    check("Eigene Config wird respektiert (max 0.20R bei 1% Stop = 0.16R)", res["is_allowed"], res)

    # ── Zusammenfassung ───────────────────────────────────────────────────────
    print("\n" + "─" * 72)
    if _failures:
        print(f"❌ {len(_failures)} von {_count} Tests fehlgeschlagen:")
        for name in _failures:
            print(f"   - {name}")
        sys.exit(1)
    print(f"✅ Alle {_count} Tests bestanden.")
