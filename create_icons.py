#!/usr/bin/env python3
"""
Generiert SVG und PNG App-Icons (Favicon, Apple-Touch-Icon, PWA Icons)
zu 100% in Pure Python (ohne externe C-Bibliotheken).
"""

import math
import zlib
import struct
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ICONS_DIR = BASE_DIR / "dashboard" / "icons"
ICONS_DIR.mkdir(parents=True, exist_ok=True)

# 1. Generiere high-end SVG Icon
svg_content = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <radialGradient id="bgGlow" cx="50%" cy="30%" r="70%">
      <stop offset="0%" stop-color="#1e1b4b" stop-opacity="0.9"/>
      <stop offset="50%" stop-color="#0d1322" stop-opacity="0.95"/>
      <stop offset="100%" stop-color="#070a13" stop-opacity="1"/>
    </radialGradient>
    <linearGradient id="neonEmerald" x1="0%" y1="100%" x2="0%" y2="0%">
      <stop offset="0%" stop-color="#059669"/>
      <stop offset="100%" stop-color="#34d399"/>
    </linearGradient>
    <linearGradient id="neonRose" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#f43f5e"/>
      <stop offset="100%" stop-color="#be123c"/>
    </linearGradient>
    <linearGradient id="trendLine" x1="0%" y1="100%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#6366f1"/>
      <stop offset="50%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#10b981"/>
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="10" result="blur" />
      <feComposite in="SourceGraphic" in2="blur" operator="over" />
    </filter>
  </defs>

  <!-- Squircle App Background -->
  <rect x="16" y="16" width="480" height="480" rx="110" fill="url(#bgGlow)" stroke="#312e81" stroke-width="6"/>

  <!-- Subtle Grid Lines -->
  <line x1="60" y1="160" x2="452" y2="160" stroke="#1e293b" stroke-width="2" stroke-dasharray="6 6"/>
  <line x1="60" y1="260" x2="452" y2="260" stroke="#1e293b" stroke-width="2" stroke-dasharray="6 6"/>
  <line x1="60" y1="360" x2="452" y2="360" stroke="#1e293b" stroke-width="2" stroke-dasharray="6 6"/>

  <!-- Candlestick 1: Bearish Pullback (Left) -->
  <line x1="130" y1="200" x2="130" y2="380" stroke="#f43f5e" stroke-width="5" stroke-linecap="round"/>
  <rect x="110" y="240" width="40" height="90" rx="6" fill="url(#neonRose)" stroke="#fb7185" stroke-width="2"/>

  <!-- Candlestick 2: Liquidity Sweep Hammer (Middle) -->
  <line x1="230" y1="230" x2="230" y2="420" stroke="#38bdf8" stroke-width="5" stroke-linecap="round"/>
  <rect x="210" y="260" width="40" height="60" rx="6" fill="#0284c7" stroke="#38bdf8" stroke-width="2"/>

  <!-- Candlestick 3: Massive Bullish Expansion (Right) -->
  <line x1="330" y1="110" x2="330" y2="350" stroke="#10b981" stroke-width="6" stroke-linecap="round" filter="url(#glow)"/>
  <rect x="306" y="140" width="48" height="150" rx="8" fill="url(#neonEmerald)" stroke="#6ee7b7" stroke-width="2.5" filter="url(#glow)"/>

  <!-- Ascending Super Trend Pulse Curve -->
  <path d="M 80 390 C 180 380, 220 310, 310 220 C 350 170, 380 120, 430 90" 
        fill="none" stroke="url(#trendLine)" stroke-width="8" stroke-linecap="round" filter="url(#glow)"/>

  <!-- Breakout Target Dot (Glowing Star) -->
  <circle cx="430" cy="90" r="14" fill="#10b981" filter="url(#glow)"/>
  <circle cx="430" cy="90" r="6" fill="#ffffff"/>

  <!-- Sleek Badge Text -->
  <rect x="360" y="400" width="90" height="34" rx="8" fill="#1e1b4b" stroke="#6366f1" stroke-width="2"/>
  <text x="405" y="423" fill="#38bdf8" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="16" font-weight="900" text-anchor="middle" letter-spacing="1">TV 24/7</text>
</svg>
"""

(ICONS_DIR / "favicon.svg").write_text(svg_content, encoding="utf-8")
(ICONS_DIR / "apple-touch-icon.svg").write_text(svg_content, encoding="utf-8")


def create_png_raster(size):
    """
    Rendert ein sauberes, antialiastes RGBA-Bild der Candlesticks & Trendlinie als PNG
    vollständig in Pure Python via zlib/struct.
    """
    w, h = size, size
    scale = size / 512.0
    raw_rows = bytearray()

    # Precalculate key elements in scaled coordinates
    r_corner = 110 * scale
    
    # Background squircle bounds
    pad = 16 * scale
    x0, y0 = pad, pad
    x1, y1 = size - pad, size - pad

    # Candlestick 1 (Rose)
    c1_x0, c1_y0, c1_x1, c1_y1 = 110 * scale, 240 * scale, 150 * scale, 330 * scale
    c1_wick_x = 130 * scale
    c1_wick_y0, c1_wick_y1 = 200 * scale, 380 * scale

    # Candlestick 2 (Blue)
    c2_x0, c2_y0, c2_x1, c2_y1 = 210 * scale, 260 * scale, 250 * scale, 320 * scale
    c2_wick_x = 230 * scale
    c2_wick_y0, c2_wick_y1 = 230 * scale, 420 * scale

    # Candlestick 3 (Emerald)
    c3_x0, c3_y0, c3_x1, c3_y1 = 306 * scale, 140 * scale, 354 * scale, 290 * scale
    c3_wick_x = 330 * scale
    c3_wick_y0, c3_wick_y1 = 110 * scale, 350 * scale

    peak_x, peak_y = 430 * scale, 90 * scale

    for y in range(h):
        raw_rows.append(0) # filter byte 0
        for x in range(w):
            # Check if inside squircle
            dx = max(x0 + r_corner - x, 0, x - (x1 - r_corner))
            dy = max(y0 + r_corner - y, 0, y - (y1 - r_corner))
            dist_sq = dx * dx + dy * dy
            
            if dist_sq > r_corner * r_corner:
                # Outside icon squircle -> Transparent
                raw_rows.extend([0, 0, 0, 0])
                continue

            # Base gradient
            t = (y / float(h))
            # Radial center glow
            center_dist = math.hypot(x - size * 0.5, y - size * 0.3) / size
            glow_factor = max(0.0, 1.0 - center_dist * 1.5)
            
            r = int(11 + 25 * glow_factor)
            g = int(17 + 20 * glow_factor)
            b = int(32 + 55 * glow_factor)
            a = 255

            # Border stroke
            border_dist = math.sqrt(dist_sq) if (dx > 0 and dy > 0) else max(x0 - x, x - x1, y0 - y, y - y1)
            if border_dist >= r_corner - 6 * scale and border_dist <= r_corner:
                r, g, b = 99, 102, 241 # indigo border

            # Grid lines
            for gy in [160 * scale, 260 * scale, 360 * scale]:
                if abs(y - gy) < 1.0 and (int(x / (10 * scale)) % 2 == 0):
                    r, g, b = max(r, 30), max(g, 41), max(b, 59)

            # Draw Candlestick 1 Wick
            if abs(x - c1_wick_x) <= 2.5 * scale and c1_wick_y0 <= y <= c1_wick_y1:
                r, g, b = 244, 63, 94
            # Draw Candlestick 1 Body
            if c1_x0 <= x <= c1_x1 and c1_y0 <= y <= c1_y1:
                r, g, b = 225, 29, 72

            # Draw Candlestick 2 Wick
            if abs(x - c2_wick_x) <= 2.5 * scale and c2_wick_y0 <= y <= c2_wick_y1:
                r, g, b = 56, 189, 248
            # Draw Candlestick 2 Body
            if c2_x0 <= x <= c2_x1 and c2_y0 <= y <= c2_y1:
                r, g, b = 2, 132, 199

            # Draw Candlestick 3 Wick
            if abs(x - c3_wick_x) <= 3.0 * scale and c3_wick_y0 <= y <= c3_wick_y1:
                r, g, b = 16, 185, 129
            # Draw Candlestick 3 Body
            if c3_x0 <= x <= c3_x1 and c3_y0 <= y <= c3_y1:
                r, g, b = 16, 185, 129

            # Approximate Cubic Bezier Trend Curve: y = f(x)
            # From (80, 390) to (430, 90)
            if 70 * scale <= x <= 435 * scale:
                u = (x - 70 * scale) / (365 * scale)
                # Curve approximation
                target_curve_y = size * (0.76 - 0.58 * (u ** 1.35))
                curve_dist = abs(y - target_curve_y)
                if curve_dist <= 4.5 * scale:
                    # Glowing line gradient from indigo to emerald
                    lr = int(99 * (1 - u) + 16 * u)
                    lg = int(102 * (1 - u) + 185 * u)
                    lb = int(241 * (1 - u) + 129 * u)
                    r, g, b = lr, lg, lb
                elif curve_dist <= 9 * scale:
                    # Subtle neon aura
                    alpha_glow = 1.0 - (curve_dist / (9 * scale))
                    r = int(r + (56 - r) * alpha_glow * 0.5)
                    g = int(g + (189 - g) * alpha_glow * 0.5)
                    b = int(b + (248 - b) * alpha_glow * 0.5)

            # Draw Peak dot
            p_dist = math.hypot(x - peak_x, y - peak_y)
            if p_dist <= 6 * scale:
                r, g, b = 255, 255, 255
            elif p_dist <= 14 * scale:
                r, g, b = 16, 185, 129
            elif p_dist <= 24 * scale:
                glow_p = 1.0 - (p_dist / (24 * scale))
                r = int(r + (16 - r) * glow_p)
                g = int(g + (185 - g) * glow_p)
                b = int(b + (129 - b) * glow_p)

            raw_rows.extend([min(255, r), min(255, g), min(255, b), a])

    compressed = zlib.compress(bytes(raw_rows), level=9)
    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xffffffff
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", compressed)
    png += chunk(b"IEND", b"")
    return png


print("Erstelle Raster-PNGs für Apple Touch Icon und PWA...")
# 180x180 für Apple Touch Icon (iPhone Standard)
(ICONS_DIR / "apple-touch-icon.png").write_bytes(create_png_raster(180))
# 192x192 für PWA
(ICONS_DIR / "icon-192.png").write_bytes(create_png_raster(192))
# 512x512 für hochauflösende PWA Displays
(ICONS_DIR / "icon-512.png").write_bytes(create_png_raster(512))
# 32x32 Favicon PNG Fallback
(ICONS_DIR / "favicon-32.png").write_bytes(create_png_raster(32))

print(f"✅ Alle Icons erfolgreich in {ICONS_DIR} generiert!")
