#!/usr/bin/env python3
"""
High-Fidelity Vektor-Chart-Engine (v4).
- 100% präziser, nativer SVG-Nachbau der degencoder TradingView-Suite:
  1. degencoder indicator (13, 1.8, 233):
     - Quantum Chaos Cloud (EMA 13 ± 1.8 ATR) & RFE 233 Basislinie
     - Institutional BUY Pocket Badges ([BUY] unter der Kerze)
     - Diskrete Signale: Blaue Good Buy Dreiecke, Magenta Sell Marker, Grüne/Rote Buy/Sell Area Kreuze
  2. degencoder's OB (Retro):
     - Bullishe Zonen (Cyan) & Bärische Zonen (Magenta)
     - Gestrichelte Mittellinie (50% Equilibrium)
     - Quality Badges ([A], [B], [C], [D], [R1], [R2], [R3])
  3. degencoder's FVGs:
     - Aktive Imbalance-Zonen mit gestrichelter Consequent Encroachment (CE 50%) Linie
  4. VSA Wyckoff Volume:
     - Farbkodierte Volumenbalken nach exakter Ratio (Lila, Rot, Orange, Grün, Blau, Grau) + 20-MA
  5. Wilder's RSI(14) Momentum-Panel & Divergenz-Marker
- Pure SVG, blitzschnell, autark & ohne externe GUI-Abhängigkeiten.
"""

import math
from datetime import datetime, timezone
from pathlib import Path

from degencoder_engine import (
    calculate_degencoder_bands,
    detect_degencoder_order_blocks,
    detect_degencoder_fvgs,
    detect_degencoder_signals,
    calculate_vsa_wyckoff
)


def calculate_ema(values, period):
    if not values or len(values) < period:
        if not values:
            return []
        sma = sum(values) / len(values)
        return [sma] * len(values)
    ema = []
    k = 2.0 / (period + 1.0)
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
        if tf in ("1D", "1W", "3D"):
            return dt.strftime("%d. %b")
        else:
            return dt.strftime("%d.%m %H:%M")
    except Exception:
        return ""


def generate_svg_chart(bars, analysis_data, timeframe="4h", width=920, height=540, user_position=None):
    """
    Rendert ein 100% präzises SVG-Chart mit degencoder Bändern, OBs, FVGs, Signalen und VSA Wyckoff Volumen.
    """
    if not bars or len(bars) < 10:
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%" style="background:#090d16;"><text x="{width/2}" y="{height/2}" fill="#64748b" text-anchor="middle" font-family="monospace">Lade Marktdaten...</text></svg>'

    total_bars = len(bars)
    n_display = min(50, total_bars)
    display_bars = bars[-n_display:]
    offset = total_bars - n_display
    closes = [b["c"] for b in bars]

    # 1. Vollständige degencoder Berechnungen
    bands_res = calculate_degencoder_bands(bars)
    b_series = bands_res.get("series", {})
    upper_chaos_all = b_series.get("upper_band", [])
    lower_chaos_all = b_series.get("lower_band", [])
    ema_13_all = b_series.get("ema_fast", [])
    rfe_basis_all = b_series.get("rfe_basis", [])
    rfe_lower_all = b_series.get("rfe_lower", [])
    rfe_upper_all = b_series.get("rfe_upper", [])

    upper_chaos_disp = upper_chaos_all[offset:] if len(upper_chaos_all) >= total_bars else [b["c"] * 1.02 for b in display_bars]
    lower_chaos_disp = lower_chaos_all[offset:] if len(lower_chaos_all) >= total_bars else [b["c"] * 0.98 for b in display_bars]
    ema_13_disp = ema_13_all[offset:] if len(ema_13_all) >= total_bars else [b["c"] for b in display_bars]
    rfe_basis_disp = rfe_basis_all[offset:] if (rfe_basis_all and len(rfe_basis_all) >= total_bars) else ema_13_disp

    # Order Blocks & FVGs
    order_blocks = detect_degencoder_order_blocks(bars, displacement_bars=5, detect_liquidity_sweep=True)
    fvgs = detect_degencoder_fvgs(bars, max_fvgs=5)
    vsa_series = calculate_vsa_wyckoff(bars)
    vsa_disp = vsa_series[offset:] if len(vsa_series) >= total_bars else []

    # Wilder's RSI(14)
    rsi_all = calculate_rsi_series(closes, 14)
    rsi_disp = rsi_all[offset:]

    # Layout Dimensionen
    margin_left = 65
    margin_right = 80
    margin_top = 45
    price_height = 275
    vol_gap = 12
    vol_height = 65
    rsi_gap = 12
    rsi_height = 80
    margin_bottom = 40

    chart_width = width - margin_left - margin_right
    bar_width = chart_width / n_display
    candle_body_width = max(3.5, bar_width * 0.68)

    # Preis-Extrema für Skalierung
    curr_c = display_bars[-1]["c"]
    all_highs = [b["h"] for b in display_bars] + [x for x in upper_chaos_disp if x is not None]
    all_lows = [b["l"] for b in display_bars] + [x for x in lower_chaos_disp if x is not None]

    # Relevante OBs in Skalierung einbeziehen falls nahe am Kurs (±25%)
    for ob in order_blocks[:6]:
        if abs(ob["midline"] - curr_c) / curr_c < 0.25:
            all_highs.append(ob["top"])
            all_lows.append(ob["bottom"])

    # Relevante FVGs einbeziehen
    for fvg in fvgs:
        if abs(fvg["ce_50"] - curr_c) / curr_c < 0.25:
            all_highs.append(fvg["top"])
            all_lows.append(fvg["bottom"])

    if analysis_data:
        gp = analysis_data.get("golden_pocket", [])
        if gp and len(gp) >= 2:
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
    vol_ma_all = calculate_ema([b.get("v") or 0.0 for b in bars], 20)
    vol_ma_disp = vol_ma_all[offset:]

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%" style="background:#070a13; font-family:\'JetBrains Mono\', monospace;">')
    svg.append('<defs>')
    svg.append('<linearGradient id="cloud-grad" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#38bdf8" stop-opacity="0.14"/><stop offset="100%" stop-color="#38bdf8" stop-opacity="0.02"/></linearGradient>')
    svg.append('<linearGradient id="rsi-overbought" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#f43f5e" stop-opacity="0.25"/><stop offset="100%" stop-color="#f43f5e" stop-opacity="0.0"/></linearGradient>')
    svg.append('<linearGradient id="rsi-oversold" x1="0%" y1="0%" x2="0%" y2="100%"><stop offset="0%" stop-color="#10b981" stop-opacity="0.0"/><stop offset="100%" stop-color="#10b981" stop-opacity="0.25"/></linearGradient>')
    svg.append('</defs>')

    # 1. Panels Backgrounds
    y_vol_top = margin_top + price_height + vol_gap
    y_rsi_top = y_vol_top + vol_height + rsi_gap

    svg.append(f'<rect x="{margin_left}" y="{margin_top}" width="{chart_width}" height="{price_height}" fill="#0b101d" rx="6" stroke="#172033" stroke-width="1"/>')
    svg.append(f'<rect x="{margin_left}" y="{y_vol_top}" width="{chart_width}" height="{vol_height}" fill="#0b101d" rx="6" stroke="#172033" stroke-width="1"/>')
    svg.append(f'<rect x="{margin_left}" y="{y_rsi_top}" width="{chart_width}" height="{rsi_height}" fill="#0b101d" rx="6" stroke="#172033" stroke-width="1"/>')

    # Grid-Linien Preis
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
                svg.append(f'<rect x="{margin_left}" y="{min(y_gp_top, y_gp_bot):.1f}" width="{chart_width}" height="{max(4.0, gp_h):.1f}" fill="rgba(245, 158, 11, 0.10)" stroke="#f59e0b" stroke-dasharray="4,3" stroke-width="1.1"/>')
                svg.append(f'<text x="{margin_left + 12}" y="{min(y_gp_top, y_gp_bot) + 14:.1f}" fill="#fbbf24" font-size="9" font-weight="bold">★ GOLDEN POCKET: {min(gp):,.2f} - {max(gp):,.2f}</text>')

    # 3. degencoder's FVGs (Fair Value Gaps mit 1-Tick Removal Rule)
    for fvg in fvgs:
        f_top = fvg["top"]
        f_bot = fvg["bottom"]
        if min_p <= f_bot and f_top <= max_p:
            y_t = y_price(f_top)
            y_b = y_price(f_bot)
            fvg_h = abs(y_b - y_t)
            is_bull = "Bullish" in fvg["type"]
            f_col = "#10b981" if is_bull else "#94a3b8"
            f_bg = "rgba(16, 185, 129, 0.18)" if is_bull else "rgba(148, 163, 184, 0.18)"
            
            # Suche Start-X falls sichtbar
            b_idx = fvg.get("bar_index", 0) - offset
            x_st = x_bar(max(0, b_idx)) if 0 <= b_idx < n_display else margin_left
            w_fvg = margin_left + chart_width - x_st

            svg.append(f'<rect x="{x_st:.1f}" y="{min(y_t, y_b):.1f}" width="{w_fvg:.1f}" height="{max(2.5, fvg_h):.1f}" fill="{f_bg}" stroke="{f_col}" stroke-width="1" rx="2"/>')
            svg.append(f'<line x1="{x_st:.1f}" y1="{y_price(fvg["ce_50"]):.1f}" x2="{margin_left + chart_width}" y2="{y_price(fvg["ce_50"]):.1f}" stroke="{f_col}" stroke-dasharray="3,3" stroke-width="1"/>')
            svg.append(f'<text x="{x_st + 6:.1f}" y="{min(y_t, y_b) + 11:.1f}" fill="{f_col}" font-size="8" font-weight="bold">FVG ({f_bot:,.2f}-{f_top:,.2f})</text>')

    # 4. degencoder's OB (Retro) Order Blocks mit Badges (A, B, C, D, R1, R2, R3)
    for ob in order_blocks[:8]:
        o_top = ob["top"]
        o_bot = ob["bottom"]
        if min_p <= o_bot and o_top <= max_p:
            y_t = y_price(o_top)
            y_b = y_price(o_bot)
            ob_h = abs(y_b - y_t)
            is_bull = "Bullish" in ob["type"]
            ob_color = "#06b6d4" if is_bull else "#d946ef"        # Cyan für Bullish, Magenta für Bearish
            ob_bg = "rgba(6, 182, 212, 0.18)" if is_bull else "rgba(217, 70, 239, 0.18)"
            
            b_idx = ob.get("bar_index", 0) - offset
            x_st = x_bar(max(0, b_idx)) if 0 <= b_idx < n_display else margin_left
            w_ob = margin_left + chart_width - x_st

            # OB Box
            svg.append(f'<rect x="{x_st:.1f}" y="{min(y_t, y_b):.1f}" width="{w_ob:.1f}" height="{max(3.0, ob_h):.1f}" fill="{ob_bg}" stroke="{ob_color}" stroke-width="1.2" rx="2"/>')
            # 50% Midline
            svg.append(f'<line x1="{x_st:.1f}" y1="{y_price(ob["midline"]):.1f}" x2="{margin_left + chart_width}" y2="{y_price(ob["midline"]):.1f}" stroke="{ob_color}" stroke-dasharray="4,3" stroke-width="1.0" opacity="0.8"/>')
            
            # Badge (A, B, C, D, R1, R2, R3)
            badge_txt = ob.get("badge", "A")
            b_w = 20 if len(badge_txt) <= 1 else 26
            badge_y = min(y_t, y_b) - 14 if is_bull else max(y_t, y_b) + 3
            svg.append(f'<rect x="{x_st + 4:.1f}" y="{badge_y:.1f}" width="{b_w}" height="13" fill="{ob_color}" rx="3"/>')
            svg.append(f'<text x="{x_st + 4 + b_w/2:.1f}" y="{badge_y + 10:.1f}" fill="#070a13" font-size="8" font-weight="bold" text-anchor="middle">{badge_txt}</text>')

    # 5. Dynamische degencoder Bänder (Quantum Chaos Cloud & RFE 233)
    pts_upper = []
    pts_lower = []
    pts_center = []
    for i in range(n_display):
        xc = x_bar(i)
        u_val = upper_chaos_disp[i] if i < len(upper_chaos_disp) and upper_chaos_disp[i] else curr_c * 1.02
        l_val = lower_chaos_disp[i] if i < len(lower_chaos_disp) and lower_chaos_disp[i] else curr_c * 0.98
        c_val = ema_13_disp[i] if i < len(ema_13_disp) and ema_13_disp[i] else curr_c
        pts_upper.append(f"{xc:.1f},{y_price(u_val):.1f}")
        pts_lower.append(f"{xc:.1f},{y_price(l_val):.1f}")
        pts_center.append(f"{xc:.1f},{y_price(c_val):.1f}")

    # Cloud Polygon
    rev_lower = list(reversed(pts_lower))
    cloud_points = " ".join(pts_upper + rev_lower)
    svg.append(f'<polygon points="{cloud_points}" fill="url(#cloud-grad)"/>')

    # Bänder-Linien
    svg.append(f'<polyline points="{" ".join(pts_upper)}" fill="none" stroke="#38bdf8" stroke-width="1.3" stroke-dasharray="4,3"/>')
    svg.append(f'<polyline points="{" ".join(pts_lower)}" fill="none" stroke="#38bdf8" stroke-width="1.3" stroke-dasharray="4,3"/>')
    svg.append(f'<polyline points="{" ".join(pts_center)}" fill="none" stroke="#0284c7" stroke-width="1.0" stroke-opacity="0.6"/>')

    # RFE 233 Trend-Kurve
    pts_rfe = []
    for i in range(n_display):
        xc = x_bar(i)
        rf_val = rfe_basis_disp[i] if i < len(rfe_basis_disp) and rfe_basis_disp[i] else curr_c
        pts_rfe.append(f"{xc:.1f},{y_price(rf_val):.1f}")
    svg.append(f'<polyline points="{" ".join(pts_rfe)}" fill="none" stroke="#818cf8" stroke-width="2.2" stroke-linecap="round"/>')

    # 6. Kerzen & degencoder Signale
    for i, b in enumerate(display_bars):
        xc = x_bar(i)
        yo = y_price(b["o"])
        yc = y_price(b["c"])
        yh = y_price(b["h"])
        yl = y_price(b["l"])

        is_green = b["c"] >= b["o"]
        col = "#10b981" if is_green else "#f43f5e"

        # Docht & Körper
        svg.append(f'<line x1="{xc:.1f}" y1="{yh:.1f}" x2="{xc:.1f}" y2="{yl:.1f}" stroke="{col}" stroke-width="1.2"/>')
        body_top = min(yo, yc)
        body_h = max(2.0, abs(yo - yc))
        svg.append(f'<rect x="{xc - candle_body_width / 2.0:.1f}" y="{body_top:.1f}" width="{candle_body_width:.1f}" height="{body_h:.1f}" fill="{col}" rx="1"/>')

        # -------------------------------------------------------------
        # degencoder Indikator-Marker auf Kerze (exakt gemäß Screenshots)
        # -------------------------------------------------------------
        global_idx = offset + i
        l_band = lower_chaos_all[global_idx] if global_idx < len(lower_chaos_all) else b["c"] * 0.98
        u_band = upper_chaos_all[global_idx] if global_idx < len(upper_chaos_all) else b["c"] * 1.02
        rf_l = rfe_lower_all[global_idx] if (rfe_lower_all and global_idx < len(rfe_lower_all) and rfe_lower_all[global_idx]) else l_band

        # A. Institutional BUY Pocket: Lower Chaos Band unter RFE Lower
        is_buy_pocket = bool(l_band < rf_l or b["l"] < rf_l)
        if is_buy_pocket:
            # Grünes abgerundetes [BUY] Badge unter der Kerze
            y_badge = yl + 16
            svg.append(f'<rect x="{xc - 12:.1f}" y="{y_badge:.1f}" width="24" height="11" fill="#10b981" rx="3" opacity="0.9"/>')
            svg.append(f'<text x="{xc:.1f}" y="{y_badge + 8:.1f}" fill="#070a13" font-size="7" font-weight="bold" text-anchor="middle">BUY</text>')

        # B. Buy Area (Grünes Kreuz) & Good Buy Signal (Blaues Dreieck)
        if b["l"] <= l_band or b["c"] <= l_band:
            # Grünes Kreuz unter Kerze
            svg.append(f'<text x="{xc:.1f}" y="{yl + 10:.1f}" fill="#10b981" font-size="10" font-weight="bold" text-anchor="middle">✕</text>')
            # Prüfe ob Reversal -> Good Buy Signal
            if is_green and (i > 0 and display_bars[i-1]["c"] < display_bars[i-1]["o"]):
                # Blaues Dreieck unter der Kerze
                svg.append(f'<polygon points="{xc:.1f},{yl + 26:.1f} {xc - 4:.1f},{yl + 33:.1f} {xc + 4:.1f},{yl + 33:.1f}" fill="#38bdf8"/>')

        # C. Sell Area (Rotes Kreuz) & Good Sell Signal (Kreis / Dreieck oben)
        if b["h"] >= u_band or b["c"] >= u_band:
            # Rotes Kreuz über Kerze
            svg.append(f'<text x="{xc:.1f}" y="{yh - 4:.1f}" fill="#f43f5e" font-size="10" font-weight="bold" text-anchor="middle">✕</text>')
            if not is_green and (i > 0 and display_bars[i-1]["c"] > display_bars[i-1]["o"]):
                # Magenta Dreieck nach unten
                svg.append(f'<polygon points="{xc:.1f},{yh - 16:.1f} {xc - 4:.1f},{yh - 23:.1f} {xc + 4:.1f},{yh - 23:.1f}" fill="#ec4899"/>')

    # Aktueller Kurs Badge am rechten Rand
    last_c = display_bars[-1]["c"]
    y_last = y_price(last_c)
    svg.append(f'<line x1="{margin_left}" y1="{y_last:.1f}" x2="{margin_left + chart_width}" y2="{y_last:.1f}" stroke="#f8fafc" stroke-width="1.2" stroke-dasharray="2,2"/>')
    svg.append(f'<rect x="{margin_left + chart_width + 4}" y="{y_last - 10:.1f}" width="72" height="20" fill="#f8fafc" rx="4"/>')
    svg.append(f'<text x="{margin_left + chart_width + 40}" y="{y_last + 4:.1f}" fill="#070a13" font-size="10" font-weight="bold" text-anchor="middle">{last_c:,.2f}</text>')

    # 6b. Nutzer-Position visuell im Chart einzeichnen
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

                svg.append(f'<line x1="{margin_left}" y1="{y_ent:.1f}" x2="{margin_left + chart_width}" y2="{y_ent:.1f}" stroke="{p_col}" stroke-dasharray="6,4" stroke-width="2"/>')
                badge_w = 230
                svg.append(f'<rect x="{margin_left + chart_width - badge_w - 6}" y="{y_ent - 11:.1f}" width="{badge_w}" height="22" fill="{p_col}" rx="4" opacity="0.95"/>')
                svg.append(f'<text x="{margin_left + chart_width - (badge_w / 2) - 6}" y="{y_ent + 4:.1f}" fill="#ffffff" font-size="10" font-weight="bold" text-anchor="middle">📍 DEIN EINSTIEG: {entry_p:,.2f} $ ({p_dir} {p_lev:g}x{user_suffix})</text>')
        except Exception:
            pass

    # 7. VSA Wyckoff Volume Panel (Exakte Benutzereinstellungen & Farben)
    svg.append(f'<text x="{margin_left + 8}" y="{y_vol_top + 14}" fill="#64748b" font-size="9" font-weight="bold">VSA WYCKOFF VOLUMEN (MA 20)</text>')

    for i, b in enumerate(display_bars):
        xc = x_bar(i)
        v = b.get("v") or 0.0
        v_ratio = v / max_vol if max_vol > 0 else 0.0
        bar_h = max(2.0, v_ratio * (vol_height - 18))
        y_bar = y_vol_top + vol_height - bar_h

        # VSA Farbe aus degencoder_engine
        v_item = vsa_disp[i] if i < len(vsa_disp) else {}
        v_col = v_item.get("color", "#22c55e")

        svg.append(f'<rect x="{xc - candle_body_width / 2.0:.1f}" y="{y_bar:.1f}" width="{candle_body_width:.1f}" height="{bar_h:.1f}" fill="{v_col}" opacity="0.88" rx="1"/>')

    # Volumen 20-MA Linie
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

    svg.append(f'<rect x="{margin_left}" y="{y_rsi_top}" width="{chart_width}" height="{rsi_height * 0.3:.1f}" fill="url(#rsi-overbought)"/>')
    svg.append(f'<rect x="{margin_left}" y="{y_rsi_30:.1f}" width="{chart_width}" height="{rsi_height * 0.3:.1f}" fill="url(#rsi-oversold)"/>')

    svg.append(f'<line x1="{margin_left}" y1="{y_rsi_70:.1f}" x2="{margin_left + chart_width}" y2="{y_rsi_70:.1f}" stroke="#334155" stroke-dasharray="3,3" stroke-width="1"/>')
    svg.append(f'<text x="{margin_left + chart_width + 8}" y="{y_rsi_70 + 3:.1f}" fill="#64748b" font-size="9">70</text>')
    svg.append(f'<line x1="{margin_left}" y1="{y_rsi_50:.1f}" x2="{margin_left + chart_width}" y2="{y_rsi_50:.1f}" stroke="#1e293b" stroke-dasharray="2,2" stroke-width="1"/>')
    svg.append(f'<line x1="{margin_left}" y1="{y_rsi_30:.1f}" x2="{margin_left + chart_width}" y2="{y_rsi_30:.1f}" stroke="#334155" stroke-dasharray="3,3" stroke-width="1"/>')
    svg.append(f'<text x="{margin_left + chart_width + 8}" y="{y_rsi_30 + 3:.1f}" fill="#64748b" font-size="9">30</text>')

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

    # 10. Header & degencoder Suite Badges
    asset_name = analysis_data.get("name", "") if analysis_data else ""
    svg.append(f'<text x="{margin_left}" y="{margin_top - 16}" fill="#f8fafc" font-size="13" font-weight="bold">{asset_name} ({timeframe})</text>')
    svg.append(f'<text x="{margin_left + chart_width}" y="{margin_top - 16}" fill="#38bdf8" font-size="10" font-weight="bold" text-anchor="end">degencoder 13 1.8 233 · OB Retro · FVGs</text>')

    svg.append('</svg>')
    return "\n".join(svg)


if __name__ == "__main__":
    print("Vektor-Chart-Engine v4 (degencoder Edition) geladen.")
