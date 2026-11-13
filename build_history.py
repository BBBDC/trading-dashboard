#!/usr/bin/env python3
"""
Generator für die separate Historie-Webseite (dashboard/history.html).
Erstellt eine responsive, dark-mode Web-App zur Nachverfolgung aller
Push-Benachrichtigungen, Signalwechsel und Score-Änderungen.
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
HISTORY_FILE = BASE_DIR / "dashboard" / "history.json"
OUT_FILE = BASE_DIR / "dashboard" / "history.html"


def generate_history_html():
    events = []
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                events = json.load(f)
        except Exception:
            events = []

    events_json_str = json.dumps(events, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="de" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Signal- & Benachrichtigungs-Historie | TradingView Super-Analyst</title>

  <!-- App Icons & Favicon -->
  <link rel="icon" type="image/svg+xml" href="icons/favicon.svg">
  <link rel="alternate icon" type="image/png" href="icons/favicon-32.png">
  <link rel="apple-touch-icon" sizes="180x180" href="icons/apple-touch-icon.png">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="TV Historie">
  <meta name="theme-color" content="#0b0f19">

  <!-- Immediate Theme & Liquid Glass Preload (Prevents FOUC) -->
  <script>
    (function() {{
      const saved = localStorage.getItem('tv_theme_mode') || 'auto';
      let effective = saved;
      if (saved === 'auto') {{
        const hour = new Date().getHours();
        effective = (hour >= 7 && hour < 19) ? 'light' : 'dark';
      }}
      if (effective === 'light') {{
        document.documentElement.classList.remove('dark');
        document.documentElement.classList.add('light');
      }} else {{
        document.documentElement.classList.remove('light');
        document.documentElement.classList.add('dark');
      }}

      // Preload user glass settings
      try {{
        const savedGlass = localStorage.getItem('tv_glass_settings');
        if (savedGlass) {{
          const g = JSON.parse(savedGlass);
          if (g && g.opacity !== undefined) {{
            document.documentElement.style.setProperty('--user-glass-opacity', g.opacity / 100);
            document.documentElement.style.setProperty('--user-glass-blur', (g.blur || 28) + 'px');
            document.documentElement.style.setProperty('--user-bg-vibrancy', (g.bgGlow || 75) / 100);
          }}
        }}
      }} catch(e) {{}}
    }})();
  </script>

  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    body {{
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }}
    .font-mono {{
      font-family: 'JetBrains Mono', monospace;
    }}

    /* =========================================================================
       APPLE "LIQUID GLASS" DESIGN SYSTEM (iOS 26 / macOS 26) - TRADING
       ========================================================================= */
    :root {{
      --theme-name: light;
      --liquid-font: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif;
      --spring-bounce: cubic-bezier(0.22, 1.2, 0.36, 1);
      --spring-smooth: cubic-bezier(0.16, 1, 0.3, 1);

      /* User Controllable Glass & Wallpaper Parameters */
      --user-glass-opacity: 0.60;
      --user-glass-blur: 28px;
      --user-bg-vibrancy: 0.75;
      --user-sheen-opacity: 0.35;

      /* Apple Liquid Glass - Light Mode */
      --glass-surface-bg: rgba(255, 255, 255, var(--user-glass-opacity, 0.60));
      --glass-surface-bg-hover: rgba(255, 255, 255, min(0.98, calc(var(--user-glass-opacity, 0.60) + 0.08)));
      --glass-surface-blur: blur(var(--user-glass-blur, 28px)) saturate(200%) brightness(1.06);
      --glass-surface-border: 1px solid rgba(255, 255, 255, 0.65);
      --glass-surface-border-specular: 1.5px solid rgba(255, 255, 255, 0.85);
      --glass-surface-shadow: 
        inset 0 1.5px 1px 0 rgba(255, 255, 255, 0.95),
        inset 0 -1px 1px 0 rgba(255, 255, 255, 0.25),
        inset 0 0 24px 0 rgba(255, 255, 255, 0.08),
        0 20px 45px -10px rgba(15, 23, 42, 0.12),
        0 4px 14px -2px rgba(15, 23, 42, 0.05);

      /* Floating Navigation & Pills */
      --glass-floating-bg: rgba(255, 255, 255, min(0.98, calc(var(--user-glass-opacity, 0.60) + 0.10)));
      --glass-floating-blur: blur(calc(var(--user-glass-blur, 28px) + 6px)) saturate(215%) brightness(1.08);
      --glass-floating-shadow: 
        inset 0 2px 1.5px 0 rgba(255, 255, 255, 0.98),
        inset 0 -1px 1px 0 rgba(255, 255, 255, 0.3),
        0 24px 56px -10px rgba(15, 23, 42, 0.16),
        0 6px 18px -2px rgba(15, 23, 42, 0.07);

      /* Nested Tiles & Inputs (Glass on Glass) */
      --glass-nested-bg: rgba(255, 255, 255, min(0.95, calc(var(--user-glass-opacity, 0.60) + 0.06)));
      --glass-nested-border: 1px solid rgba(255, 255, 255, 0.6);
      --glass-nested-shadow: 
        inset 0 1px 1px 0 rgba(255, 255, 255, 0.8),
        0 4px 12px -2px rgba(15, 23, 42, 0.03);

      /* Spotlight Glow */
      --glass-spotlight: rgba(255, 255, 255, 0.4);

      /* Canvas & Typography */
      --bg-canvas: #eaf0fb;
      --text-main: #0f172a;
      --text-sub: #334155;
      --text-muted: #64748b;

      color-scheme: light;
    }}

    html.dark {{
      --theme-name: dark;

      /* Apple Liquid Glass - Dark Mode */
      --glass-surface-bg: rgba(18, 24, 38, min(0.96, calc(var(--user-glass-opacity, 0.60) * 1.15)));
      --glass-surface-bg-hover: rgba(24, 32, 50, min(0.98, calc(var(--user-glass-opacity, 0.60) * 1.25)));
      --glass-surface-blur: blur(var(--user-glass-blur, 28px)) saturate(200%) brightness(1.03);
      --glass-surface-border: 1px solid rgba(255, 255, 255, 0.14);
      --glass-surface-border-specular: 1.5px solid rgba(255, 255, 255, 0.28);
      --glass-surface-shadow: 
        inset 0 1.5px 1px 0 rgba(255, 255, 255, 0.28),
        inset 0 -1px 1px 0 rgba(0, 0, 0, 0.6),
        inset 0 0 24px 0 rgba(255, 255, 255, 0.03),
        0 24px 52px -10px rgba(0, 0, 0, 0.7),
        0 6px 18px -2px rgba(0, 0, 0, 0.45);

      /* Floating Navigation & Pills */
      --glass-floating-bg: rgba(14, 18, 30, min(0.98, calc(var(--user-glass-opacity, 0.60) * 1.25)));
      --glass-floating-blur: blur(calc(var(--user-glass-blur, 28px) + 6px)) saturate(215%) brightness(1.05);
      --glass-floating-shadow: 
        inset 0 2px 1.5px 0 rgba(255, 255, 255, 0.35),
        inset 0 -1px 1px 0 rgba(0, 0, 0, 0.7),
        0 28px 64px -12px rgba(0, 0, 0, 0.8),
        0 8px 24px -3px rgba(0, 0, 0, 0.55);

      /* Nested Tiles & Inputs */
      --glass-nested-bg: rgba(255, 255, 255, 0.06);
      --glass-nested-border: 1px solid rgba(255, 255, 255, 0.1);
      --glass-nested-shadow: 
        inset 0 1px 1px 0 rgba(255, 255, 255, 0.12),
        0 4px 12px -2px rgba(0, 0, 0, 0.3);

      /* Spotlight Glow */
      --glass-spotlight: rgba(255, 255, 255, 0.18);

      --bg-canvas: #070912;
      --text-main: #f8fafc;
      --text-sub: #cbd5e1;
      --text-muted: #94a3b8;

      color-scheme: dark;
    }}

    /* Living Wallpaper Mesh Stage (Hardware-Accelerated & Static for 0% Idle GPU) */
    #living-mesh-stage {{
      position: fixed;
      inset: 0;
      pointer-events: none;
      z-index: -10;
      contain: strict;
      transform: translateZ(0);
      background-image: 
        radial-gradient(circle at 10% 12%, rgba(99, 102, 241, 0.70) 0%, transparent 48%),
        radial-gradient(circle at 90% 16%, rgba(16, 185, 129, 0.65) 0%, transparent 46%),
        radial-gradient(circle at 25% 70%, rgba(6, 182, 212, 0.65) 0%, transparent 52%),
        radial-gradient(circle at 85% 82%, rgba(245, 158, 11, 0.60) 0%, transparent 50%),
        radial-gradient(circle at 50% 40%, rgba(244, 63, 94, 0.40) 0%, transparent 45%);
      background-attachment: fixed;
      background-size: cover;
      transition: opacity 0.3s ease;
    }}
    html.dark #living-mesh-stage {{
      background-image: 
        radial-gradient(circle at 10% 12%, rgba(99, 102, 241, 0.55) 0%, transparent 48%),
        radial-gradient(circle at 90% 16%, rgba(16, 185, 129, 0.48) 0%, transparent 46%),
        radial-gradient(circle at 25% 70%, rgba(6, 182, 212, 0.52) 0%, transparent 52%),
        radial-gradient(circle at 85% 82%, rgba(245, 158, 11, 0.48) 0%, transparent 50%),
        radial-gradient(circle at 50% 40%, rgba(244, 63, 94, 0.32) 0%, transparent 45%);
    }}

    body {{
      background-color: var(--bg-canvas);
      min-height: 100vh;
      color: var(--text-main);
    }}

    /* Floating Island (Navigation, Header) */
    .liquid-floating-island {{
      position: relative;
      background: var(--glass-floating-bg) !important;
      backdrop-filter: var(--glass-floating-blur);
      -webkit-backdrop-filter: var(--glass-floating-blur);
      border: var(--glass-surface-border-specular) !important;
      box-shadow: var(--glass-floating-shadow) !important;
      transition: transform 0.35s var(--spring-bounce), box-shadow 0.35s var(--spring-smooth);
      overflow: visible !important;
      contain: layout;
      transform: translateZ(0);
      will-change: transform;
    }}

    /* Specular Reflection Sheen (Pure GPU, Zero Reflows) */
    .liquid-floating-island::after,
    #timeline-container > div::after,
    .liquid-card::after,
    .liquid-kpi-card::after {{
      content: "";
      position: absolute;
      inset: 0;
      border-radius: inherit;
      background: linear-gradient(135deg, rgba(255, 255, 255, 0.45) 0%, rgba(255, 255, 255, 0.10) 32%, transparent 62%);
      pointer-events: none;
      z-index: 1;
      opacity: calc(var(--user-sheen-opacity, 0.35) / 0.35);
      transition: opacity 0.25s ease;
    }}
    html.dark .liquid-floating-island::after,
    html.dark #timeline-container > div::after,
    html.dark .liquid-card::after,
    html.dark .liquid-kpi-card::after {{
      background: linear-gradient(135deg, rgba(255, 255, 255, 0.20) 0%, rgba(255, 255, 255, 0.03) 32%, transparent 62%);
    }}

    /* History Cards & KPI Cards */
    #timeline-container > div,
    .liquid-card,
    .liquid-kpi-card {{
      position: relative;
      background: var(--glass-surface-bg) !important;
      backdrop-filter: var(--glass-surface-blur);
      -webkit-backdrop-filter: var(--glass-surface-blur);
      border: var(--glass-surface-border) !important;
      box-shadow: var(--glass-surface-shadow) !important;
      border-radius: 20px !important;
      contain: layout paint;
      transform: translateZ(0);
      transition: transform 0.25s var(--spring-bounce), box-shadow 0.25s ease, background-color 0.25s ease;
    }}
    #timeline-container > div:hover,
    .liquid-card:hover,
    .liquid-kpi-card:hover {{
      transform: translateY(-2px) scale(1.004);
      background: var(--glass-surface-bg-hover) !important;
    }}

    /* Nested Tiles & Inputs (Glass on Glass) */
    .liquid-nested-tile {{
      background-color: var(--glass-nested-bg) !important;
      border: var(--glass-nested-border) !important;
      box-shadow: var(--glass-nested-shadow) !important;
      border-radius: 14px;
    }}

    /* Apple Modal & Popover Glass */
    .liquid-modal-glass {{
      background: var(--glass-floating-bg) !important;
      backdrop-filter: blur(36px) saturate(210%) brightness(1.05);
      -webkit-backdrop-filter: blur(36px) saturate(210%) brightness(1.05);
      border: var(--glass-surface-border-specular) !important;
      box-shadow: 0 32px 64px -12px rgba(0, 0, 0, 0.75) !important;
      border-radius: 28px !important;
      transform: translateZ(0);
    }}

    /* Spring Button Physics */
    .liquid-btn {{
      transition: transform 0.25s var(--spring-bounce), background-color 0.2s ease, box-shadow 0.25s ease, color 0.2s ease;
    }}
    .liquid-btn:hover {{
      transform: scale(1.03);
    }}
    .liquid-btn:active {{
      transform: scale(0.97);
    }}

    /* Light Theme Palette & Overrides */
    html.light body {{
      background-color: #f8fafc !important;
      color: #0f172a !important;
    }}
    html.light [class*="bg-[#0b0f19]"] {{
      background-color: #f8fafc !important;
    }}
    html.light [class*="bg-[#0d1322]"],
    html.light [class*="bg-[#0f172a]"] {{
      background-color: #ffffff !important;
    }}
    html.light .bg-slate-900,
    html.light [class*="bg-slate-900/"] {{
      background-color: #ffffff !important;
      box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04), 0 1px 2px -1px rgba(0, 0, 0, 0.04);
    }}
    html.light .bg-slate-950,
    html.light [class*="bg-slate-950/"] {{
      background-color: #f1f5f9 !important;
    }}
    html.light .bg-slate-800,
    html.light [class*="bg-slate-800/"] {{
      background-color: #f1f5f9 !important;
      color: #334155 !important;
    }}
    html.light .bg-slate-700,
    html.light [class*="bg-slate-700/"] {{
      background-color: #e2e8f0 !important;
      color: #1e293b !important;
    }}
    html.light .border-slate-800,
    html.light [class*="border-slate-800/"],
    html.light .border-slate-700,
    html.light [class*="border-slate-700/"] {{
      border-color: #e2e8f0 !important;
    }}

    /* Light Mode Typography */
    html.light .text-white {{
      color: #0f172a !important;
    }}
    html.light .text-slate-100,
    html.light .text-slate-200 {{
      color: #1e293b !important;
    }}
    html.light .text-slate-300 {{
      color: #334155 !important;
    }}
    html.light .text-slate-400 {{
      color: #64748b !important;
    }}
    html.light .text-slate-500 {{
      color: #94a3b8 !important;
    }}

    /* Status & Badges in Light Mode */
    html.light .text-emerald-400,
    html.light .text-emerald-300 {{
      color: #059669 !important;
    }}
    html.light .text-rose-400,
    html.light .text-rose-300 {{
      color: #e11d48 !important;
    }}
    html.light .text-indigo-400,
    html.light .text-indigo-300,
    html.light .text-indigo-200 {{
      color: #4f46e5 !important;
    }}
    html.light .text-amber-400,
    html.light .text-amber-300 {{
      color: #d97706 !important;
    }}

    html.light [class*="bg-emerald-500/"],
    html.light [class*="bg-emerald-600/"] {{
      background-color: #ecfdf5 !important;
      border-color: #a7f3d0 !important;
      color: #047857 !important;
    }}
    html.light [class*="bg-rose-500/"] {{
      background-color: #fff1f2 !important;
      border-color: #fecdd3 !important;
      color: #be123c !important;
    }}
    html.light [class*="bg-indigo-500/"],
    html.light [class*="bg-indigo-600/"],
    html.light [class*="bg-indigo-950/"] {{
      background-color: #eef2ff !important;
      border-color: #c7d2fe !important;
      color: #4338ca !important;
    }}

    /* Custom Scrollbar */
    ::-webkit-scrollbar {{
      width: 8px;
      height: 8px;
    }}
    ::-webkit-scrollbar-track {{
      background: #0f172a;
    }}
    ::-webkit-scrollbar-thumb {{
      background: #334155;
      border-radius: 4px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
      background: #475569;
    }}
    html.light ::-webkit-scrollbar-track {{
      background: #f1f5f9;
    }}
    html.light ::-webkit-scrollbar-thumb {{
      background: #cbd5e1;
    }}
    html.light ::-webkit-scrollbar-thumb:hover {{
      background: #94a3b8;
    }}

    .glow-emerald {{
      box-shadow: 0 0 20px -3px rgba(16, 185, 129, 0.25);
    }}
    .glow-rose {{
      box-shadow: 0 0 20px -3px rgba(244, 63, 94, 0.25);
    }}
    html.light .glow-emerald {{
      box-shadow: 0 4px 15px -2px rgba(16, 185, 129, 0.2);
    }}
    html.light .glow-rose {{
      box-shadow: 0 4px 15px -2px rgba(244, 63, 94, 0.2);
    }}

    .no-scrollbar::-webkit-scrollbar {{
      display: none;
    }}
    .no-scrollbar {{
      -ms-overflow-style: none;
      scrollbar-width: none;
    }}
  </style>
</head>
<body class="bg-[#0b0f19] text-slate-100 min-h-screen antialiased selection:bg-indigo-500 selection:text-white pb-12">

  <!-- Living Wallpaper Mesh Stage (Static Hardware Accelerated Gradients for 0% CPU) -->
  <div id="living-mesh-stage"></div>

  <!-- Top Navigation Header (Apple Liquid Floating Island) -->
  <header class="sticky top-2 sm:top-4 z-40 px-3 sm:px-6 max-w-7xl mx-auto w-full transition-all duration-300">
    <div class="liquid-floating-island rounded-2xl sm:rounded-3xl p-3 sm:p-4 flex flex-col gap-3 relative">
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        
        <!-- Brand & Back Button -->
        <div class="flex items-center justify-between sm:justify-start gap-3 w-full sm:w-auto">
          <a href="index.html" class="liquid-btn px-3 py-1.5 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700/60 text-xs font-semibold text-indigo-300 hover:text-white flex items-center gap-1.5 transition active:scale-95 shadow-sm cursor-pointer" title="Zurück zur Marktübersicht">
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path stroke-linecap="round" stroke-linejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            <span>Dashboard</span>
          </a>

          <div class="h-6 w-px bg-slate-800 hidden sm:block"></div>

          <div>
            <div class="flex items-center gap-2">
              <h1 class="font-bold text-sm sm:text-lg tracking-tight text-white flex items-center gap-1.5">
                <span>📜 Signal-Historie</span>
              </h1>
              <span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Live-Log</span>
            </div>
            <p class="hidden sm:block text-xs text-slate-400">Chronologisches Protokoll aller Push-Alerts & KI-Signalwechsel</p>
          </div>

          <!-- Mobile Theme & Glass Control -->
          <div class="sm:hidden flex items-center gap-1.5">
            <div class="inline-flex p-0.5 rounded-xl bg-slate-800/80 border border-slate-700/60 text-xs font-semibold shrink-0" role="group">
              <button type="button" onclick="setThemeMode('auto')" id="theme-btn-auto-m" class="px-2 py-1 rounded-lg text-[10px] font-bold">⏰</button>
              <button type="button" onclick="setThemeMode('light')" id="theme-btn-light-m" class="px-2 py-1 rounded-lg text-[10px] font-bold">☀️</button>
              <button type="button" onclick="setThemeMode('dark')" id="theme-btn-dark-m" class="px-2 py-1 rounded-lg text-[10px] font-bold">🌙</button>
            </div>
            <button id="glass-settings-btn-m" type="button" onclick="toggleGlassSettingsPopover()" class="liquid-btn p-1.5 rounded-xl bg-slate-800/80 border border-slate-700/60 text-slate-300 text-xs" title="Liquid Glass">🎛️</button>
          </div>
        </div>

        <!-- Controls & Desktop Theme Switcher & Liquid Glass Controller -->
        <div class="flex items-center justify-between sm:justify-end gap-2 w-full sm:w-auto">
          <!-- Desktop Theme Switcher -->
          <div class="hidden sm:inline-flex p-0.5 rounded-xl bg-slate-800/80 border border-slate-700/60 text-xs font-semibold shrink-0 shadow-sm" role="group">
            <button type="button" onclick="setThemeMode('auto')" id="theme-btn-auto" class="px-2.5 py-1.5 rounded-lg transition active:scale-95 cursor-pointer text-[11px] font-bold" title="Automatisch nach Tageszeit">
              <span>⏰</span><span class="ml-1">Auto</span>
            </button>
            <button type="button" onclick="setThemeMode('light')" id="theme-btn-light" class="px-2.5 py-1.5 rounded-lg transition active:scale-95 cursor-pointer text-[11px] font-bold" title="Heller Modus">
              <span>☀️</span><span class="ml-1">Hell</span>
            </button>
            <button type="button" onclick="setThemeMode('dark')" id="theme-btn-dark" class="px-2.5 py-1.5 rounded-lg transition active:scale-95 cursor-pointer text-[11px] font-bold" title="Dunkler Modus">
              <span>🌙</span><span class="ml-1">Dunkel</span>
            </button>
          </div>

          <!-- Liquid Glass Control Center Button -->
          <button id="glass-settings-btn" type="button" onclick="toggleGlassSettingsPopover()" class="liquid-btn p-1.5 sm:p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700/60 text-slate-300 hover:text-white transition active:scale-95 shadow-sm cursor-pointer flex items-center justify-center shrink-0" title="Liquid Glass Optik anpassen">
            <span class="text-sm">🎛️</span>
          </button>

          <button onclick="refreshHistory()" class="liquid-btn px-3 py-1.5 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700/60 text-xs font-semibold text-slate-200 hover:text-white flex items-center gap-1.5 transition active:scale-95 shadow-sm cursor-pointer">
            <svg id="refresh-icon" class="w-3.5 h-3.5 text-indigo-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            <span>Aktualisieren</span>
          </button>

          <a href="https://ntfy.sh/bbbdc-trading-alerts" target="_blank" rel="noopener" class="liquid-btn px-3 py-1.5 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/40 text-xs font-semibold text-indigo-300 hover:text-white flex items-center gap-1.5 transition active:scale-95 shadow-sm">
            <span>🔔</span>
            <span class="hidden sm:inline">ntfy Feed</span>
          </a>
        </div>

      </div>

      <!-- Apple Control Center: Liquid Glass Feineinstellung Popover -->
      <div id="glass-settings-popover" class="hidden absolute top-16 right-3 sm:right-6 w-80 sm:w-88 p-4 rounded-3xl liquid-modal-glass shadow-2xl z-50 space-y-3.5 border border-white/40 dark:border-white/10 text-slate-800 dark:text-slate-100">
        <div class="flex items-center justify-between pb-2 border-b border-slate-200/40 dark:border-white/10">
          <div class="flex items-center gap-2">
            <div class="w-6 h-6 rounded-lg bg-gradient-to-br from-indigo-400 to-indigo-600 text-white flex items-center justify-center text-xs shadow-sm shadow-indigo-500/40">
              <span>✨</span>
            </div>
            <div>
              <span class="font-bold text-sm text-slate-900 dark:text-white block leading-tight">Liquid Glass Optik</span>
              <span class="text-[10px] text-slate-500 dark:text-slate-400">Echtzeit-Anpassung der Glasphysik</span>
            </div>
          </div>
          <button type="button" onclick="toggleGlassSettingsPopover()" class="liquid-btn p-1.5 rounded-full text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-white/20 transition cursor-pointer">
            ✕
          </button>
        </div>

        <!-- Slider 1: Glas-Deckkraft (Karten) -->
        <div class="space-y-1.5">
          <div class="flex justify-between items-center text-xs">
            <span class="font-semibold text-slate-700 dark:text-slate-300">Glas-Deckkraft (Karten)</span>
            <span class="font-bold text-slate-900 dark:text-white font-mono bg-white/60 dark:bg-white/10 px-2 py-0.5 rounded-md border border-white/50 dark:border-white/10" id="val-glass-opacity">60%</span>
          </div>
          <input type="range" id="slider-glass-opacity" min="10" max="95" value="60" step="1" oninput="onGlassOpacityChange(this.value)" class="w-full accent-indigo-500 cursor-pointer">
          <div class="flex justify-between text-[10px] text-slate-400 font-medium">
            <span>Kristall (10%)</span>
            <span>Mittel (50%)</span>
            <span>Opak (95%)</span>
          </div>
        </div>

        <!-- Slider 2: Hintergrund-Leuchtkraft (Wallpaper Glow) -->
        <div class="space-y-1.5">
          <div class="flex justify-between items-center text-xs">
            <span class="font-semibold text-slate-700 dark:text-slate-300">Hintergrund-Transparenz / Glow</span>
            <span class="font-bold text-slate-900 dark:text-white font-mono bg-white/60 dark:bg-white/10 px-2 py-0.5 rounded-md border border-white/50 dark:border-white/10" id="val-bg-glow">75%</span>
          </div>
          <input type="range" id="slider-bg-glow" min="10" max="95" value="75" step="1" oninput="onBgGlowChange(this.value)" class="w-full accent-emerald-500 cursor-pointer">
          <div class="flex justify-between text-[10px] text-slate-400 font-medium">
            <span>Subtil (10%)</span>
            <span>Mittel (50%)</span>
            <span>Vibrant (95%)</span>
          </div>
        </div>

        <!-- Schnellwahl Presets -->
        <div class="pt-2 border-t border-slate-200/40 dark:border-white/10 space-y-2">
          <span class="text-[10px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider block">Schnellwahl-Profile:</span>
          <div class="grid grid-cols-3 gap-1.5 text-xs">
            <button type="button" onclick="applyGlassPreset('silky')" class="liquid-btn p-2 rounded-xl liquid-nested-tile text-[11px] font-semibold text-center hover:scale-[1.02] transition active:scale-95 cursor-pointer">
              🍏 Seidig (60/75)
            </button>
            <button type="button" onclick="applyGlassPreset('maximum')" class="liquid-btn p-2 rounded-xl liquid-nested-tile text-[11px] font-bold text-center hover:scale-[1.02] transition active:scale-95 cursor-pointer">
              🔥 Max (95/95)
            </button>
            <button type="button" onclick="applyGlassPreset('crystal')" class="liquid-btn p-2 rounded-xl liquid-nested-tile text-[11px] font-semibold text-center hover:scale-[1.02] transition active:scale-95 cursor-pointer">
              💎 Kristall (20/80)
            </button>
          </div>
        </div>
      </div>

    </div>
  </header>

  <!-- Main Content -->
  <main class="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">

    <!-- KPI Overview Cards -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
      
      <div class="liquid-kpi-card p-4">
        <div class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Archivierte Alerts</div>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-2xl font-bold font-mono text-white" id="stat-total-events">-</span>
          <span class="text-xs text-indigo-400">Events</span>
        </div>
      </div>

      <div class="liquid-kpi-card p-4">
        <div class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Benachrichtigungs-Modus</div>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-sm font-bold text-emerald-400 flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            Smart Delta
          </span>
        </div>
        <div class="text-[10px] text-slate-500 mt-0.5">Kein Spam bei unveränderten Kursen</div>
      </div>

      <div class="liquid-kpi-card p-4">
        <div class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Überwachte Märkte</div>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-2xl font-bold font-mono text-white">58</span>
          <span class="text-xs text-slate-400">Aktien & Krypto</span>
        </div>
      </div>

      <div class="liquid-kpi-card p-4">
        <div class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Scan-Intervall</div>
        <div class="mt-1 flex items-baseline gap-2">
          <span class="text-lg font-bold font-mono text-indigo-300">Alle 4 Stunden</span>
        </div>
        <div class="text-[10px] text-slate-500 mt-0.5">01:05, 05:05, 09:05, 13:05, 17:05, 21:05 UTC</div>
      </div>

    </div>

    <!-- Filter Bar -->
    <div class="liquid-card flex flex-wrap items-center justify-between gap-3 p-3">
      <div class="flex flex-wrap items-center gap-1.5">
        <button onclick="setFilter('ALL')" id="filter-btn-all" class="liquid-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white transition cursor-pointer">
          Alle Ereignisse
        </button>
        <button onclick="setFilter('LONG')" id="filter-btn-long" class="liquid-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800/60 hover:bg-slate-700/60 text-slate-300 transition cursor-pointer flex items-center gap-1.5">
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
          Nur Long
        </button>
        <button onclick="setFilter('SHORT')" id="filter-btn-short" class="liquid-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800/60 hover:bg-slate-700/60 text-slate-300 transition cursor-pointer flex items-center gap-1.5">
          <span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
          Nur Short
        </button>
        <button onclick="setFilter('REVERSAL')" id="filter-btn-reversal" class="liquid-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800/60 hover:bg-slate-700/60 text-slate-300 transition cursor-pointer flex items-center gap-1.5">
          <span>🔄</span>
          Nur Signalwechsel
        </button>
      </div>

      <div class="text-xs text-slate-400 px-2" id="event-counter-text">
        Lade Historie...
      </div>
    </div>

    <!-- Timeline Container -->
    <div id="timeline-container" class="space-y-4">
      <!-- Dynamisch befüllt durch JavaScript -->
    </div>

  </main>

  <script>
    let initialEvents = {events_json_str};
    let currentFilter = 'ALL';

    function timeAgo(dateString) {{
      const date = new Date(dateString);
      const now = new Date();
      const seconds = Math.floor((now - date) / 1000);
      if (seconds < 60) return "Gerade eben";
      const minutes = Math.floor(seconds / 60);
      if (minutes < 60) return "vor " + minutes + " Min.";
      const hours = Math.floor(minutes / 60);
      if (hours < 24) return "vor " + hours + " Std.";
      const days = Math.floor(hours / 24);
      return "vor " + days + " Tagen";
    }}

    function renderEvents(events) {{
      const container = document.getElementById('timeline-container');
      const statTotal = document.getElementById('stat-total-events');
      const counterText = document.getElementById('event-counter-text');

      statTotal.textContent = events.length;

      if (!events || events.length === 0) {{
        container.innerHTML = `
          <div class="rounded-2xl bg-[#0d1322]/80 border border-slate-800/80 p-8 text-center space-y-3">
            <div class="w-12 h-12 mx-auto rounded-full bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-xl">
              🔔
            </div>
            <h3 class="text-base font-bold text-white">Noch keine Benachrichtigungen erfasst</h3>
            <p class="text-xs text-slate-400 max-w-md mx-auto">
              Sobald der 4-stündige Scan eine relevante Signaländerung (z.B. Wechsel von Neutral auf Long) erkennt, wird sie hier mit allen Details archiviert.
            </p>
          </div>
        `;
        counterText.textContent = "0 Ereignisse";
        return;
      }}

      // Filter anwenden
      let filtered = events.filter(evt => {{
        if (currentFilter === 'ALL') return true;
        if (!evt.changes || evt.changes.length === 0) return currentFilter === 'ALL';
        if (currentFilter === 'LONG') {{
          return evt.changes.some(c => c.new_signal === 'LONG');
        }}
        if (currentFilter === 'SHORT') {{
          return evt.changes.some(c => c.new_signal === 'SHORT');
        }}
        if (currentFilter === 'REVERSAL') {{
          return evt.changes.some(c => c.old_signal !== c.new_signal);
        }}
        return true;
      }});

      counterText.textContent = filtered.length + " von " + events.length + " Ereignissen angezeigt";

      if (filtered.length === 0) {{
        container.innerHTML = `
          <div class="rounded-2xl bg-[#0d1322]/80 border border-slate-800/80 p-8 text-center text-slate-400 text-xs">
            Keine Ereignisse für den ausgewählten Filter ("${{currentFilter}}").
          </div>
        `;
        return;
      }}

      let html = '';
      filtered.forEach((evt, idx) => {{
        const isInit = (evt.type === 'SYSTEM_INIT');
        const relativeTime = evt.timestamp ? timeAgo(evt.timestamp) : '';
        const displayTime = evt.timestamp_display || (evt.timestamp ? new Date(evt.timestamp).toLocaleString('de-DE') : '');
        const changes = evt.changes || [];

        html += `
          <div class="rounded-2xl bg-[#0d1322]/90 border border-slate-800/80 p-5 space-y-4 hover:border-slate-700/80 transition">
            
            <!-- Event Header -->
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-slate-800/60 pb-3.5">
              <div class="flex items-center gap-2.5">
                <div class="w-8 h-8 rounded-lg ${{isInit ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20' : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'}} flex items-center justify-center text-sm font-bold">
                  ${{isInit ? '⚙️' : '🔔'}}
                </div>
                <div>
                  <h3 class="text-sm font-bold text-white tracking-tight">${{evt.title || 'Signal-Update'}}</h3>
                  <div class="flex items-center gap-2 text-[11px] text-slate-400">
                    <span>${{displayTime}}</span>
                    <span>•</span>
                    <span class="text-indigo-400 font-medium">${{relativeTime}}</span>
                  </div>
                </div>
              </div>

              <div class="flex items-center gap-2">
                ${{evt.notification_sent ? `
                  <span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                    Push gesendet (ntfy)
                  </span>
                ` : `
                  <span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-800 text-slate-400 border border-slate-700">
                    Protokolliert
                  </span>
                `}}
              </div>
            </div>
        `;

        if (isInit) {{
          html += `
            <div class="p-3.5 rounded-xl bg-indigo-950/20 border border-indigo-500/20 text-xs text-indigo-200">
              ${{evt.summary || 'Baseline-Initialisierung des Marktes durchgeführt.'}}
            </div>
          `;
        }} else if (changes.length > 0) {{
          html += `<div class="grid grid-cols-1 md:grid-cols-2 gap-3">`;

          changes.forEach(c => {{
            const isLong = c.new_signal === 'LONG';
            const isShort = c.new_signal === 'SHORT';
            const sigColor = isLong ? 'emerald' : (isShort ? 'rose' : 'slate');
            const ticker = c.symbol.split(':').pop();

            html += `
              <div class="rounded-xl bg-slate-900/80 border border-slate-800 p-3.5 space-y-2.5">
                <div class="flex items-start justify-between gap-2">
                  <div>
                    <div class="flex items-center gap-1.5">
                      <span class="text-xs font-bold text-white">${{c.name}}</span>
                      <span class="text-[10px] font-mono text-slate-400">(${{ticker}})</span>
                    </div>
                    <div class="text-[10px] text-slate-500">${{c.category || 'Asset'}}</div>
                  </div>

                  <!-- Transition Badge -->
                  <div class="flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-bold font-mono bg-${{sigColor}}-500/10 text-${{sigColor}}-400 border border-${{sigColor}}-500/30">
                    <span>${{c.old_signal}}</span>
                    <span>➔</span>
                    <span>${{c.new_signal}}</span>
                    <span>(${{c.new_score}}%)</span>
                  </div>
                </div>

                <div class="text-[11px] text-slate-300 font-medium bg-slate-950/40 px-2.5 py-1.5 rounded-lg border border-slate-800/60 flex items-center justify-between">
                  <div><span class="text-indigo-400 font-semibold">Setup:</span> ${{c.setup_name}}</div>
                  ${{c.evaluated_by ? `<span class="text-[9px] font-mono text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">🤖 ${{c.evaluated_by}}</span>` : ''}}
                </div>

                ${{c.change_reason ? `
                  <div class="text-[11px] text-amber-200/95 bg-amber-500/10 border border-amber-500/20 px-2.5 py-1.5 rounded-lg flex items-start gap-1.5">
                    <span class="text-amber-400 font-bold shrink-0">💡 Grund:</span>
                    <span class="leading-relaxed">${{c.change_reason}}</span>
                  </div>
                ` : ''}}

                ${{c.entry_range && c.entry_range.length > 0 ? `
                  <div class="grid grid-cols-3 gap-1.5 text-center text-[10px] font-mono pt-1">
                    <div class="bg-slate-950/60 p-1.5 rounded border border-slate-800/80">
                      <span class="text-slate-400 block text-[9px] uppercase">Entry</span>
                      <span class="font-bold text-white">${{c.entry_range[0].toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</span>
                    </div>
                    <div class="bg-slate-950/60 p-1.5 rounded border border-slate-800/80">
                      <span class="text-rose-400 block text-[9px] uppercase">Stop Loss</span>
                      <span class="font-bold text-rose-300">${{c.stop_loss.toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</span>
                    </div>
                    <div class="bg-slate-950/60 p-1.5 rounded border border-slate-800/80">
                      <span class="text-emerald-400 block text-[9px] uppercase">Ziel (TP2)</span>
                      <span class="font-bold text-emerald-300">${{c.take_profit_2.toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</span>
                    </div>
                  </div>
                ` : ''}}

                ${{c.note ? `
                  <p class="text-[11px] text-slate-400 italic border-l-2 border-indigo-500/40 pl-2 py-0.5">
                    ${{c.note}}
                  </p>
                ` : ''}}

                <div class="pt-1 text-right">
                  <a href="index.html?asset=${{encodeURIComponent(c.symbol)}}" class="text-[11px] text-indigo-400 hover:text-indigo-300 font-semibold inline-flex items-center gap-1">
                    <span>Chart & Setup im Dashboard öffnen</span>
                    <span>→</span>
                  </a>
                </div>
              </div>
            `;
          }});

          html += `</div>`;
        }}

        html += `</div>`;
      }});

      container.innerHTML = html;
    }}

    function setFilter(filter) {{
      currentFilter = filter;
      ['all', 'long', 'short', 'reversal'].forEach(f => {{
        const btn = document.getElementById('filter-btn-' + f);
        if (btn) {{
          if (f.toUpperCase() === filter) {{
            btn.className = "px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white transition cursor-pointer";
          }} else {{
            btn.className = "px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800/60 hover:bg-slate-700/60 text-slate-300 transition cursor-pointer flex items-center gap-1.5";
          }}
        }}
      }});
      renderEvents(initialEvents);
    }}

    function refreshHistory() {{
      const icon = document.getElementById('refresh-icon');
      if (icon) icon.classList.add('animate-spin');
      fetch('history.json?nocache=' + Date.now())
        .then(res => res.json())
        .then(data => {{
          initialEvents = data;
          renderEvents(initialEvents);
          if (icon) icon.classList.remove('animate-spin');
        }})
        .catch(err => {{
          console.warn("Konnte history.json nicht nachladen, nutze gecachte Daten:", err);
          if (icon) icon.classList.remove('animate-spin');
        }});
    }}

    // ==========================================
    // 🎨 Theme Manager: Light / Dark Mode & Tageszeit-Automatik
    // ==========================================
    function getThemeMode() {{
      return localStorage.getItem('tv_theme_mode') || 'auto';
    }}

    function computeEffectiveTheme(mode) {{
      if (mode === 'light') return 'light';
      if (mode === 'dark') return 'dark';
      // 'auto': Tagmodus von 07:00 bis 19:00 Uhr
      const hour = new Date().getHours();
      return (hour >= 7 && hour < 19) ? 'light' : 'dark';
    }}

    function applyTheme(mode, persist = false) {{
      if (persist) {{
        localStorage.setItem('tv_theme_mode', mode);
      }}
      const effective = computeEffectiveTheme(mode);
      const root = document.documentElement;

      if (effective === 'light') {{
        root.classList.remove('dark');
        root.classList.add('light');
      }} else {{
        root.classList.remove('light');
        root.classList.add('dark');
      }}

      // Dynamic theme-color for iOS / Android mobile browser chrome
      const metaTheme = document.querySelector('meta[name="theme-color"]');
      if (metaTheme) {{
        metaTheme.setAttribute('content', effective === 'light' ? '#f8fafc' : '#0b0f19');
      }}

      updateThemeToggleUI(mode, effective);
    }}

    function updateThemeToggleUI(mode, effective) {{
      const btnAuto = document.getElementById('theme-btn-auto');
      const btnLight = document.getElementById('theme-btn-light');
      const btnDark = document.getElementById('theme-btn-dark');

      const btnAutoM = document.getElementById('theme-btn-auto-m');
      const btnLightM = document.getElementById('theme-btn-light-m');
      const btnDarkM = document.getElementById('theme-btn-dark-m');

      const activeClass = 'bg-indigo-600 text-white shadow-sm shadow-indigo-500/20';
      const inactiveClass = 'text-slate-400 hover:text-white';

      [btnAuto, btnLight, btnDark].forEach(btn => {{
        if (!btn) return;
        btn.className = 'px-2.5 py-1.5 rounded-lg transition active:scale-95 cursor-pointer text-[11px] font-bold ' + inactiveClass;
      }});

      [btnAutoM, btnLightM, btnDarkM].forEach(btn => {{
        if (!btn) return;
        btn.className = 'px-2 py-1 rounded-lg text-[10px] font-bold ' + inactiveClass;
      }});

      if (mode === 'auto') {{
        if (btnAuto) btnAuto.className = 'px-2.5 py-1.5 rounded-lg transition active:scale-95 cursor-pointer text-[11px] font-bold ' + activeClass;
        if (btnAutoM) btnAutoM.className = 'px-2 py-1 rounded-lg text-[10px] font-bold ' + activeClass;
      }} else if (mode === 'light') {{
        if (btnLight) btnLight.className = 'px-2.5 py-1.5 rounded-lg transition active:scale-95 cursor-pointer text-[11px] font-bold ' + activeClass;
        if (btnLightM) btnLightM.className = 'px-2 py-1 rounded-lg text-[10px] font-bold ' + activeClass;
      }} else if (mode === 'dark') {{
        if (btnDark) btnDark.className = 'px-2.5 py-1.5 rounded-lg transition active:scale-95 cursor-pointer text-[11px] font-bold ' + activeClass;
        if (btnDarkM) btnDarkM.className = 'px-2 py-1 rounded-lg text-[10px] font-bold ' + activeClass;
      }}
    }}

    function setThemeMode(mode) {{
      applyTheme(mode, true);
    }}

    setInterval(() => {{
      const currentMode = getThemeMode();
      if (currentMode === 'auto') {{
        applyTheme('auto', false);
      }}
    }}, 60000);

    // Liquid Glass Runtime Controller
    let glassSettings = {{
      opacity: 60,
      bgGlow: 75,
      blur: 28,
      sheen: 35
    }};

    function initGlassSettings() {{
      try {{
        const saved = localStorage.getItem('tv_glass_settings');
        if (saved) {{
          const parsed = JSON.parse(saved);
          if (parsed && typeof parsed.opacity === 'number') {{
            glassSettings.opacity = parsed.opacity;
            glassSettings.bgGlow = parsed.bgGlow ?? 75;
            glassSettings.blur = parsed.blur ?? 28;
            glassSettings.sheen = parsed.sheen ?? 35;
          }}
        }}
      }} catch(e) {{}}
      applyGlassDOM();
    }}

    function applyGlassDOM() {{
      const root = document.documentElement;
      const op = Math.min(0.95, Math.max(0.10, glassSettings.opacity / 100));
      const glow = Math.min(0.95, Math.max(0.10, glassSettings.bgGlow / 100));
      const blur = glassSettings.blur || 28;

      root.style.setProperty('--user-glass-opacity', op);
      root.style.setProperty('--user-glass-blur', `${{blur}}px`);
      root.style.setProperty('--user-bg-vibrancy', glow);

      const stage = document.getElementById('living-mesh-stage');
      if (stage) stage.style.opacity = glow;

      const sliderOp = document.getElementById('slider-glass-opacity');
      const valOp = document.getElementById('val-glass-opacity');
      if (sliderOp) sliderOp.value = glassSettings.opacity;
      if (valOp) valOp.textContent = `${{glassSettings.opacity}}%`;

      const sliderGlow = document.getElementById('slider-bg-glow');
      const valGlow = document.getElementById('val-bg-glow');
      if (sliderGlow) sliderGlow.value = glassSettings.bgGlow;
      if (valGlow) valGlow.textContent = `${{glassSettings.bgGlow}}%`;
    }}

    function onGlassOpacityChange(val) {{
      glassSettings.opacity = Math.min(95, Math.max(10, parseInt(val, 10) || 60));
      glassSettings.blur = Math.round(18 + (glassSettings.opacity / 95) * 18);
      saveGlassSettings();
      applyGlassDOM();
    }}

    function onBgGlowChange(val) {{
      glassSettings.bgGlow = Math.min(95, Math.max(10, parseInt(val, 10) || 75));
      saveGlassSettings();
      applyGlassDOM();
    }}

    function applyGlassPreset(type) {{
      if (type === 'silky') {{
        glassSettings = {{ opacity: 60, bgGlow: 75, blur: 28, sheen: 35 }};
      }} else if (type === 'maximum' || type === 'balance') {{
        glassSettings = {{ opacity: 95, bgGlow: 95, blur: 36, sheen: 40 }};
      }} else if (type === 'crystal') {{
        glassSettings = {{ opacity: 20, bgGlow: 80, blur: 24, sheen: 45 }};
      }}
      saveGlassSettings();
      applyGlassDOM();
    }}

    function saveGlassSettings() {{
      try {{
        localStorage.setItem('tv_glass_settings', JSON.stringify(glassSettings));
      }} catch(e) {{}}
    }}

    function toggleGlassSettingsPopover() {{
      const pop = document.getElementById('glass-settings-popover');
      if (!pop) return;
      pop.classList.toggle('hidden');
    }}

    // Close popover when clicking outside
    document.addEventListener('click', (e) => {{
      const pop = document.getElementById('glass-settings-popover');
      const btn = document.getElementById('glass-settings-btn');
      const btnM = document.getElementById('glass-settings-btn-m');
      if (pop && !pop.classList.contains('hidden')) {{
        if (!pop.contains(e.target) && !btn?.contains(e.target) && !btnM?.contains(e.target)) {{
          pop.classList.add('hidden');
        }}
      }}
    }});

    // Initial render
    initGlassSettings();
    applyTheme(getThemeMode(), false);
    renderEvents(initialEvents);
  </script>
</body>
</html>
"""

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Historie-Webseite erfolgreich erstellt: {OUT_FILE}")


if __name__ == "__main__":
    generate_history_html()
