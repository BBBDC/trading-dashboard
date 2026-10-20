#!/usr/bin/env python3
"""
High-Fidelity Vektor-Chart-Engine (v3).
- Rendert 100% echte historische Candlesticks aus TradingView MCP Daten.
- Dynamische, kurvenförmige degencoder Bänder (EMA 13 ± 1.8 ATR) und EMA 233 Trendlinie.
- Echte Wyckoff VSA Volumenbalken (Ultra-High / High / Normal / Low) mit 20-Perioden-MA.
- Echtes Bar-by-Bar Wilder's RSI(14) Momentum-Panel mit Divergenz-Markern.
- SMC Fair Value Gaps (FVG) mit 50% Consequent Encroachment (CE) & Fibonacci Golden Pocket (0.618-0.65).
- Reale Datums- und Zeitachsenbeschriftungen.
- 100% autark in Python (Pure SVG, keine C/GUI-Bibliotheken, optimiert für Raspberry Pi).
"""

import math
from datetime import datetime, timezone
from pathlib import Path


def calculate_ema(values, period):
    if not values or len(values) < period:
        # Fallback auf SMA wenn Historie kurz
        if not values:
            return []
        sma = sum(values) / len(values)
        return [sma] * len(values)
    ema = []
    k = 2.0 / (period + 1.0)
    # Start mit SMA
    current_ema = sum(values[:period]) / period
    for _ in range(period - 1):
        ema.append(current_ema)
    ema.append(current_ema)
    for v in values[period:]:
        current_ema = v * k + current_ema * (1.0 - k)
        ema.append(current_ema)
    return ema


def calculate_atr(bars, period=13):
    if len(bars) < period + 1:
        return [0.0] * len(bars)
    trs = [bars[0]["h"] - bars[0]["l"]]
    for i in range(1, len(bars)):
        h = bars[i]["h"]
        l = bars[i]["l"]
        prev_c = bars[i-1]["c"]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    # Wilder's smoothing
    atrs = []
    curr_atr = sum(trs[:period]) / period
    for _ in range(period - 1):
        atrs.append(curr_atr)
    atrs.append(curr_atr)
    for tr in trs[period:]:
        curr_atr = (curr_atr * (period - 1) + tr) / period
        atrs.append(curr_atr)
    return atrs


def calculate_rsi_series(closes, period=14):
    if len(closes) < period + 1:
        return [50.0] * len(closes)
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(0.0, diff))
        losses.append(max(0.0, -diff))

    rsis = [50.0] * period
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        rsis.append(100.0)
    else:
        rs = avg_gain / avg_loss
        rsis.append(100.0 - (100.0 / (1.0 + rs)))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsis.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsis.append(100.0 - (100.0 / (1.0 + rs)))
    return rsis


def format_timestamp(ts, tf):
    try:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        if tf == "1D":
            return dt.strftime("%d. %b")
        else:
            return dt.strftime("%d.%m %H:%M")
    except Exception:
        return ""


def generate_svg_chart(bars, analysis_data, timeframe="4h", width=920, height=520, user_position=None):
    """
    Rendert ein realistisches, hochauflösendes Chart mit echten Kerzen und dynamischen Indikatorkurven.
    """
    if not bars or len(bars) < 10:
        # Fallback falls keine Kerzen verfügbar
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%" style="background:#090d16;"><text x="460" y="260" fill="#64748b" text-anchor="middle" font-family="monospace">Lade Marktdaten...</text></svg>'

    # Wir nutzen 40-50 Kerzen für optimale Übersicht
    total_bars = len(bars)
    n_display = min(50, total_bars)
    display_bars = bars[-n_display:]
    closes = [b["c"] for b in bars]

    # Berechne Indikatoren über die gesamte Historie
    ema_233_all = calculate_ema(closes, min(233, max(20, len(closes) - 1)))
    ema_13_all = calculate_ema(closes, 13)
    atr_13_all = calculate_atr(bars, 13)
    rsi_all = calculate_rsi_series(closes, 14)

    # Schneide auf display_bars zu
    offset = total_bars - n_display
    ema_233_disp = ema_233_all[offset:]
    ema_13_disp = ema_13_all[offset:]
    atr_13_disp = atr_13_all[offset:]
    rsi_disp = rsi_all[offset:]

    # Volatilitätsbänder (degencoder 13, 1.8)
    mult = 1.8
    upper_band_disp = [ema_13_disp[i] + mult * atr_13_disp[i] for i in range(n_display)]
    lower_band_disp = [ema_13_disp[i] - mult * atr_13_disp[i] for i in range(n_display)]

    # Layout Dimensionen
    margin_left = 65
    margin_right = 80
    margin_top = 40
    price_height = 270
    vol_gap = 12
    vol_height = 65
    rsi_gap = 12
    rsi_height = 80
    margin_bottom = 40

    chart_width = width - margin_left - margin_right
    bar_width = chart_width / n_display
    candle_body_width = max(3.5, bar_width * 0.68)

    # Preis-Extrema für Skalierung (inkl. Bänder & Swings)
    all_highs = [b["h"] for b in display_bars] + upper_band_disp
    all_lows = [b["l"] for b in display_bars] + lower_band_disp

    if analysis_data:
        gp = analysis_data.get("golden_pocket", [])
        if gp:
            all_highs.append(max(gp))
            all_lows.append(min(gp))

    if user_position:
        try:
            ep = float(user_position.get("entry_price", 0.0))
            if ep > 0:
                all_highs.append(ep)
                all_lows.append(ep)
        except Exception:
            pass

    min_p = min(all_lows)
    max_p = max(all_highs)
    p_padding = (max_p - min_p) * 0.05
    min_p -= p_padding
    max_p += p_padding
    p_range = max_p - min_p if max_p > min_p else 1.0

    def y_price(val):
        ratio = (val - min_p) / p_range
        return margin_top + price_height - (ratio * price_height)

    def x_bar(idx):
        return margin_left + idx * bar_width + bar_width / 2.0

    # Volumen-Skalierung
    volumes = [b.get("v") or 0.0 for b in display_bars]
    max_vol = max(volumes) if volumes and max(volumes) > 0 else 1.0

    # 20-Perioden Volumen MA
    vol_ma_all = calculate_ema([b.get("v") or 0.0 for b in bars], 20)
    vol_ma_disp = vol_ma_all[offset:]

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%" style="background:#070a13; font-family:\'JetBrains Mono\', monospace;">')
    svg.append('<defs>')
    svg.append('<linearGradient id="cloud-grad" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#38bdf8" stop-opacity="0.12"/><stop offset="100%" stop-color="#38bdf8" stop-opacity="0.02"/></linearGradient>')
    svg.append('<linearGradient id="rsi-overbought" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#f43f5e" stop-opacity="0.25"/><stop offset="100%" stop-color="#f43f5e" stop-opacity="0.0"/></linearGradient>')
    svg.append('<linearGradient id="rsi-oversold" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#10b981" stop-opacity="0.0"/><stop offset="100%" stop-color="#10b981" stop-opacity="0.25"/></linearGradient>')
    svg.append('</defs>')

    # 1. Panels Backgrounds
    y_vol_top = margin_top + price_height + vol_gap
    y_rsi_top = y_vol_top + vol_height + rsi_gap

    svg.append(f'<rect x="{margin_left}" y="{margin_top}" width="{chart_width}" height="{price_height}" fill="#0b101d" rx="6" stroke="#172033" stroke-width="1"/>')
    svg.append(f'<rect x="{margin_left}" y="{y_vol_top}" width="{chart_width}" height="{vol_height}" fill="#0b101d" rx="6" stroke="#172033" stroke-width="1"/>')
    svg.append(f'<rect x="{margin_left}" y="{y_rsi_top}" width="{chart_width}" height="{rsi_height}" fill="#0b101d" rx="6" stroke="#172033" stroke-width="1"/>')

    # Grid-Linien Preis (5 Stufen)
    for i in range(6):
        grid_p = min_p + (p_range * (i / 5.0))
        y_pos = y_price(grid_p)
        svg.append(f'<line x1="{margin_left}" y1="{y_pos:.1f}" x2="{margin_left + chart_width}" y2="{y_pos:.1f}" stroke="#172033" stroke-dasharray="3,3" stroke-width="1"/>')
        svg.append(f'<text x="{margin_left + chart_width + 8}" y="{y_pos + 4:.1f}" fill="#64748b" font-size="10" text-anchor="start">{grid_p:,.2f}</text>')

    # 2. Fibonacci Golden Pocket (0.618 - 0.65)
    if analysis_data and "golden_pocket" in analysis_data:
        gp = analysis_data["golden_pocket"]
        if gp and len(gp) >= 2:
            y_gp_top = y_price(max(gp))
            y_gp_bot = y_price(min(gp))
            gp_h = abs(y_gp_bot - y_gp_top)
            if gp_h > 1:
                svg.append(f'<rect x="{margin_left}" y="{min(y_gp_top, y_gp_bot):.1f}" width="{chart_width}" height="{max(4.0, gp_h):.1f}" fill="rgba(245, 158, 11, 0.12)" stroke="#f59e0b" stroke-dasharray="4,3" stroke-width="1.2"/>')
                svg.append(f'<text x="{margin_left + 12}" y="{min(y_gp_top, y_gp_bot) + 14:.1f}" fill="#fbbf24" font-size="10" font-weight="bold">★ GOLDEN POCKET (0.618 - 0.65): {min(gp):,.2f} - {max(gp):,.2f}</text>')

    # 3. Fair Value Gaps (FVGs) aus echten Kerzen ableiten & zeichnen
    for i in range(2, n_display):
        # Bullish FVG: Bar i-2 High < Bar i Low
        if display_bars[i]["l"] > display_bars[i-2]["h"]:
            top = display_bars[i]["l"]
            bot = display_bars[i-2]["h"]
            x_start = x_bar(i-2)
            y_t = y_price(top)
            y_b = y_price(bot)
            h_f = abs(y_b - y_t)
            ce = (top + bot) / 2.0
            svg.append(f'<rect x="{x_start:.1f}" y="{min(y_t, y_b):.1f}" width="{margin_left + chart_width - x_start:.1f}" height="{max(2.5, h_f):.1f}" fill="rgba(16, 185, 129, 0.13)" stroke="#10b981" stroke-width="1" rx="2"/>')
            svg.append(f'<line x1="{x_start:.1f}" y1="{y_price(ce):.1f}" x2="{margin_left + chart_width}" y2="{y_price(ce):.1f}" stroke="#10b981" stroke-dasharray="2,2" stroke-width="1"/>')
        # Bearish FVG: Bar i-2 Low > Bar i High
        elif display_bars[i-2]["l"] > display_bars[i]["h"]:
            top = display_bars[i-2]["l"]
            bot = display_bars[i]["h"]
            x_start = x_bar(i-2)
            y_t = y_price(top)
            y_b = y_price(bot)
            h_f = abs(y_b - y_t)
            ce = (top + bot) / 2.0
            svg.append(f'<rect x="{x_start:.1f}" y="{min(y_t, y_b):.1f}" width="{margin_left + chart_width - x_start:.1f}" height="{max(2.5, h_f):.1f}" fill="rgba(244, 63, 94, 0.13)" stroke="#f43f5e" stroke-width="1" rx="2"/>')
            svg.append(f'<line x1="{x_start:.1f}" y1="{y_price(ce):.1f}" x2="{margin_left + chart_width}" y2="{y_price(ce):.1f}" stroke="#f43f5e" stroke-dasharray="2,2" stroke-width="1"/>')

    # 4. Dynamische degencoder Bänder (Cloud & Polylines)
    pts_upper = []
    pts_lower = []
    pts_center = []
    for i in range(n_display):
        xc = x_bar(i)
        pts_upper.append(f"{xc:.1f},{y_price(upper_band_disp[i]):.1f}")
        pts_lower.append(f"{xc:.1f},{y_price(lower_band_disp[i]):.1f}")
        pts_center.append(f"{xc:.1f},{y_price(ema_13_disp[i]):.1f}")

    # Cloud
    rev_lower = list(reversed(pts_lower))
    cloud_points = " ".join(pts_upper + rev_lower)
    svg.append(f'<polygon points="{cloud_points}" fill="url(#cloud-grad)"/>')

    # Upper & Lower Lines
    svg.append(f'<polyline points="{" ".join(pts_upper)}" fill="none" stroke="#38bdf8" stroke-width="1.3" stroke-dasharray="4,3"/>')
    svg.append(f'<polyline points="{" ".join(pts_lower)}" fill="none" stroke="#38bdf8" stroke-width="1.3" stroke-dasharray="4,3"/>')
    svg.append(f'<polyline points="{" ".join(pts_center)}" fill="none" stroke="#0284c7" stroke-width="1.0" stroke-opacity="0.6"/>')

    # 5. Dynamische EMA 233 Trend-Kurve (Smooth polyline)
    pts_ema233 = []
    for i in range(n_display):
        xc = x_bar(i)
        y_ema = y_price(ema_233_disp[i])
        pts_ema233.append(f"{xc:.1f},{y_ema:.1f}")
    svg.append(f'<polyline points="{" ".join(pts_ema233)}" fill="none" stroke="#818cf8" stroke-width="2.2" stroke-linecap="round"/>')

    # 6. Candlesticks (Echte Kerzen)
    for i, b in enumerate(display_bars):
        xc = x_bar(i)
        yo = y_price(b["o"])
        yc = y_price(b["c"])
        yh = y_price(b["h"])
        yl = y_price(b["l"])

        is_green = b["c"] >= b["o"]
        col = "#10b981" if is_green else "#f43f5e"

        # Wick
        svg.append(f'<line x1="{xc:.1f}" y1="{yh:.1f}" x2="{xc:.1f}" y2="{yl:.1f}" stroke="{col}" stroke-width="1.2"/>')

        # Body
        body_top = min(yo, yc)
        body_h = max(2.0, abs(yo - yc))
        svg.append(f'<rect x="{xc - candle_body_width / 2.0:.1f}" y="{body_top:.1f}" width="{candle_body_width:.1f}" height="{body_h:.1f}" fill="{col}" rx="1"/>')

    # Aktueller Kurs Badge am rechten Rand
    last_c = display_bars[-1]["c"]
    y_last = y_price(last_c)
    svg.append(f'<line x1="{margin_left}" y1="{y_last:.1f}" x2="{margin_left + chart_width}" y2="{y_last:.1f}" stroke="#f8fafc" stroke-width="1.2" stroke-dasharray="2,2"/>')
    svg.append(f'<rect x="{margin_left + chart_width + 4}" y="{y_last - 10:.1f}" width="72" height="20" fill="#f8fafc" rx="4"/>')
    svg.append(f'<text x="{margin_left + chart_width + 40}" y="{y_last + 4:.1f}" fill="#070a13" font-size="10" font-weight="bold" text-anchor="middle">{last_c:,.2f}</text>')

    # 6b. Nutzer-Position visuell im Chart einzeichnen (Einstiegskurs, Richtung & Hebel)
    if user_position:
        try:
            entry_p = float(user_position.get("entry_price", 0.0))
            if entry_p > 0 and min_p <= entry_p <= max_p:
                y_ent = y_price(entry_p)
                p_dir = user_position.get("direction", "LONG").upper()
                p_col = "#10b981" if p_dir == "LONG" else "#f43f5e"
                p_lev = user_position.get("leverage", 1.0)
                p_user = user_position.get("user_name", "")
                user_suffix = f" · @{p_user}" if p_user else ""

                # Horizontale gestrichelte Einstiegslinie
                svg.append(f'<line x1="{margin_left}" y1="{y_ent:.1f}" x2="{margin_left + chart_width}" y2="{y_ent:.1f}" stroke="{p_col}" stroke-dasharray="6,4" stroke-width="2"/>')

                # Prominentes Badge
                badge_w = 230
                svg.append(f'<rect x="{margin_left + chart_width - badge_w - 6}" y="{y_ent - 11:.1f}" width="{badge_w}" height="22" fill="{p_col}" rx="4" opacity="0.95"/>')
                svg.append(f'<text x="{margin_left + chart_width - (badge_w / 2) - 6}" y="{y_ent + 4:.1f}" fill="#ffffff" font-size="10" font-weight="bold" text-anchor="middle">📍 DEIN EINSTIEG: {entry_p:,.2f} $ ({p_dir} {p_lev:g}x{user_suffix})</text>')
        except Exception:
            pass

    # 7. Wyckoff VSA Volumen Panel
    svg.append(f'<text x="{margin_left + 8}" y="{y_vol_top + 14}" fill="#64748b" font-size="9" font-weight="bold">VSA WYCKOFF VOLUMEN</text>')
    avg_vol_disp = sum(volumes) / len(volumes) if volumes else 1.0

    for i, b in enumerate(display_bars):
        xc = x_bar(i)
        v = b.get("v") or 0.0
        v_ratio = v / max_vol if max_vol > 0 else 0.0
        bar_h = max(2.0, v_ratio * (vol_height - 18))
        y_bar = y_vol_top + vol_height - bar_h

        is_green = b["c"] >= b["o"]
        # Wyckoff Farbkodierung
        if avg_vol_disp > 0 and v > 2.0 * avg_vol_disp:
            v_col = "#c084fc"  # Ultra-High Climax (Lila)
        elif avg_vol_disp > 0 and v > 1.4 * avg_vol_disp:
            v_col = "#38bdf8"  # High Volume (Cyan)
        elif avg_vol_disp > 0 and v < 0.5 * avg_vol_disp:
            v_col = "#f59e0b"  # Low / No Supply (Amber)
        else:
            v_col = "#10b981" if is_green else "#f43f5e"

        svg.append(f'<rect x="{xc - candle_body_width / 2.0:.1f}" y="{y_bar:.1f}" width="{candle_body_width:.1f}" height="{bar_h:.1f}" fill="{v_col}" opacity="0.85" rx="1"/>')

    # Volumen MA Linie
    pts_vol_ma = []
    for i in range(n_display):
        xc = x_bar(i)
        vm = vol_ma_disp[i]
        v_ratio = vm / max_vol if max_vol > 0 else 0.0
        y_vm = y_vol_top + vol_height - (v_ratio * (vol_height - 18))
        pts_vol_ma.append(f"{xc:.1f},{y_vm:.1f}")
    svg.append(f'<polyline points="{" ".join(pts_vol_ma)}" fill="none" stroke="#64748b" stroke-width="1.2"/>')

    # 8. Wilder's RSI(14) Panel
    y_rsi_70 = y_rsi_top + rsi_height * 0.3
    y_rsi_30 = y_rsi_top + rsi_height * 0.7
    y_rsi_50 = y_rsi_top + rsi_height * 0.5

    # Shaded Zones
    svg.append(f'<rect x="{margin_left}" y="{y_rsi_top}" width="{chart_width}" height="{rsi_height * 0.3:.1f}" fill="url(#rsi-overbought)"/>')
    svg.append(f'<rect x="{margin_left}" y="{y_rsi_30:.1f}" width="{chart_width}" height="{rsi_height * 0.3:.1f}" fill="url(#rsi-oversold)"/>')

    svg.append(f'<line x1="{margin_left}" y1="{y_rsi_70:.1f}" x2="{margin_left + chart_width}" y2="{y_rsi_70:.1f}" stroke="#334155" stroke-dasharray="3,3" stroke-width="1"/>')
    svg.append(f'<text x="{margin_left + chart_width + 8}" y="{y_rsi_70 + 3:.1f}" fill="#64748b" font-size="9">70</text>')
    svg.append(f'<line x1="{margin_left}" y1="{y_rsi_50:.1f}" x2="{margin_left + chart_width}" y2="{y_rsi_50:.1f}" stroke="#1e293b" stroke-dasharray="2,2" stroke-width="1"/>')
    svg.append(f'<line x1="{margin_left}" y1="{y_rsi_30:.1f}" x2="{margin_left + chart_width}" y2="{y_rsi_30:.1f}" stroke="#334155" stroke-dasharray="3,3" stroke-width="1"/>')
    svg.append(f'<text x="{margin_left + chart_width + 8}" y="{y_rsi_30 + 3:.1f}" fill="#64748b" font-size="9">30</text>')

    # RSI Polyline
    pts_rsi = []
    for i in range(n_display):
        xc = x_bar(i)
        r = rsi_disp[i]
        y_r = y_rsi_top + rsi_height - ((r / 100.0) * rsi_height)
        pts_rsi.append(f"{xc:.1f},{y_r:.1f}")

    svg.append(f'<polyline points="{" ".join(pts_rsi)}" fill="none" stroke="#a855f7" stroke-width="1.8" stroke-linecap="round"/>')

    # RSI Divergence Markers
    divs = analysis_data.get("divergences", []) if analysis_data else []
    if any("Bullische" in d for d in divs):
        x_div = x_bar(n_display - 4)
        y_div = y_rsi_top + rsi_height - 12
        svg.append(f'<g transform="translate({x_div}, {y_div})">')
        svg.append('<path d="M 0 -10 L 4 0 L -4 0 Z" fill="#10b981"/>')
        svg.append('<text x="7" y="-2" fill="#10b981" font-size="9" font-weight="bold">BULL DIV</text>')
        svg.append('</g>')

    if any("Bärische" in d for d in divs):
        x_div = x_bar(n_display - 4)
        y_div = y_rsi_top + 16
        svg.append(f'<g transform="translate({x_div}, {y_div})">')
        svg.append('<path d="M 0 10 L 4 0 L -4 0 Z" fill="#f43f5e"/>')
        svg.append('<text x="7" y="6" fill="#f43f5e" font-size="9" font-weight="bold">BEAR DIV</text>')
        svg.append('</g>')

    curr_rsi_text = f"{rsi_disp[-1]:.1f}"
    svg.append(f'<text x="{margin_left + 8}" y="{y_rsi_top + 14}" fill="#64748b" font-size="9" font-weight="bold">RSI (14): <tspan fill="#c084fc">{curr_rsi_text}</tspan></text>')

    # 9. X-Achse Datums- und Zeitstempel
    step = max(6, n_display // 6)
    for i in range(0, n_display, step):
        xc = x_bar(i)
        t_label = format_timestamp(display_bars[i]["t"], timeframe)
        svg.append(f'<line x1="{xc:.1f}" y1="{margin_top + price_height}" x2="{xc:.1f}" y2="{margin_top + price_height + 4}" stroke="#334155" stroke-width="1"/>')
        svg.append(f'<line x1="{xc:.1f}" y1="{y_rsi_top + rsi_height}" x2="{xc:.1f}" y2="{y_rsi_top + rsi_height + 4}" stroke="#334155" stroke-width="1"/>')
        svg.append(f'<text x="{xc:.1f}" y="{y_rsi_top + rsi_height + 15}" fill="#64748b" font-size="9" text-anchor="middle">{t_label}</text>')

    # 10. Header & Badges
    asset_name = analysis_data.get("name", "") if analysis_data else ""
    svg.append(f'<text x="{margin_left}" y="{margin_top - 14}" fill="#f8fafc" font-size="13" font-weight="bold">{asset_name} ({timeframe})</text>')
    svg.append(f'<text x="{margin_left + chart_width}" y="{margin_top - 14}" fill="#64748b" font-size="10" text-anchor="end">Echte TradingView MCP Marktdaten</text>')

    svg.append('</svg>')
    return "\n".join(svg)


if __name__ == "__main__":
    print("Vektor-Chart-Engine v3 geladen.")
