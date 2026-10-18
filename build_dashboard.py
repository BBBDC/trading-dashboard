#!/usr/bin/env python3
"""
Dashboard Generator: Erstellt ein interaktives, hochmodernes HTML-Dashboard
mit Tailwind CSS, Super-Navigation, Multi-Timeframe-Modal und robuster Datenanbindung.
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"
OUT_HTML = BASE_DIR / "dashboard" / "index.html"
ARTIFACT_DIR = Path("/Users/maximilianmayer/.gemini/antigravity/brain/eeb75350-6985-4121-862b-6a5bd07b0cf8")
OUT_ARTIFACT = ARTIFACT_DIR / "dashboard.html"

with open(DB_FILE, "r", encoding="utf-8") as f:
    db_data = json.load(f)

json_str = json.dumps(db_data, ensure_ascii=False)

raw_engine = db_data.get("evaluation_engine", "Gemini 3.8 Flash (High) · Pro Abo")
if "3.8" in raw_engine:
    engine_display = "Gemini 3.8 High · Pro"
elif "gemini-4" in raw_engine.lower():
    engine_display = "Gemini 4 · Pro"
elif "2.5-pro" in raw_engine.lower():
    engine_display = "Gemini 2.5 Pro · Pro"
elif "2.5-flash" in raw_engine.lower():
    engine_display = "Gemini 2.5 Flash · Fallback"
elif "quantitative" in raw_engine.lower() or "confluence" in raw_engine.lower():
    engine_display = "SMC Confluence · Math Core"
else:
    engine_display = raw_engine

html_content = f"""<!DOCTYPE html>
<html lang="de" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>TradingView Super-Analyst Dashboard</title>

  <!-- App Icons & Favicon -->
  <link rel="icon" type="image/svg+xml" href="icons/favicon.svg">
  <link rel="alternate icon" type="image/png" href="icons/favicon-32.png">
  <link rel="apple-touch-icon" sizes="180x180" href="icons/apple-touch-icon.png">
  <link rel="apple-touch-icon-precomposed" href="icons/apple-touch-icon.png">

  <!-- iOS Standalone Web App Meta Tags -->
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="Super-Analyst">
  <meta name="theme-color" content="#0b0f19">
  <meta name="mobile-web-app-capable" content="yes">
  <link rel="manifest" href="manifest.json">

  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
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
    .glow-emerald {{
      box-shadow: 0 0 25px -5px rgba(16, 185, 129, 0.3);
    }}
    .glow-rose {{
      box-shadow: 0 0 25px -5px rgba(244, 63, 94, 0.3);
    }}
  </style>
</head>
<body class="bg-[#0b0f19] text-slate-100 min-h-screen antialiased selection:bg-indigo-500 selection:text-white">

  <!-- Pull-Down-to-Refresh Visual Indicator (Touch & iOS) -->
  <div id="pull-refresh-indicator" class="fixed top-0 left-0 right-0 z-50 flex items-center justify-center pointer-events-none transition-transform duration-200 -translate-y-full">
    <div class="mt-3 px-4 py-2 rounded-full bg-[#0d1322]/95 border border-indigo-500/50 shadow-2xl backdrop-blur-md flex items-center gap-2.5 text-xs font-semibold text-slate-100">
      <svg id="pull-icon" class="w-4 h-4 text-indigo-400 transition-transform duration-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <path stroke-linecap="round" stroke-linejoin="round" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
      </svg>
      <span id="pull-text">Nach unten ziehen zum Aktualisieren</span>
    </div>
  </div>

  <!-- Toast Notification Notification Banner -->
  <div id="toast-banner" class="fixed bottom-6 right-6 z-50 transform translate-y-24 opacity-0 transition-all duration-300 pointer-events-none">
    <div class="px-4 py-3 rounded-xl bg-slate-900/95 border border-emerald-500/50 text-white text-xs font-semibold shadow-2xl flex items-center gap-2 backdrop-blur-md">
      <span class="text-emerald-400 text-base">✓</span>
      <span id="toast-message">Dashboard erfolgreich aktualisiert!</span>
    </div>
  </div>

  <!-- Top Navigation Header -->
  <header class="border-b border-slate-800/80 bg-[#0d1322]/90 backdrop-blur sticky top-0 z-40 px-4 sm:px-6 py-3.5">
    <div class="max-w-7xl mx-auto flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3.5">
      
      <!-- Brand & Title -->
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-slate-900 border border-indigo-500/40 p-1 flex items-center justify-center shadow-lg shadow-indigo-500/20">
          <img src="icons/favicon.svg" alt="TV" class="w-8 h-8">
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="font-bold text-lg sm:text-xl tracking-tight text-white">Super-Analyst Dashboard</h1>
            <span class="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">24/7 Raspberry Pi</span>
            <span class="inline-flex px-2 py-0.5 rounded-full text-[10px] sm:text-[11px] font-semibold bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 items-center gap-1.5" title="Aktive Analyse-Engine / Kaskade">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              {engine_display}
            </span>
          </div>
          <p class="text-xs text-slate-400">Multi-Timeframe Confluence (4h · 8h · 1D) | SMC · Wyckoff VSA · RSI Divs · Golden Pocket</p>
        </div>
      </div>

      <!-- Action & Metrics Controls -->
      <div class="flex flex-wrap items-center gap-2 sm:gap-3">
        
        <!-- Next Scan Live Countdown Timer -->
        <div class="px-3 py-1.5 rounded-xl bg-indigo-950/40 border border-indigo-500/30 flex items-center gap-2 shadow-sm" title="Scanzyklus: alle 4 Stunden (01:05, 05:05, 09:05, 13:05, 17:05, 21:05 UTC)">
          <span class="relative flex h-2 w-2">
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
            <span class="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
          </span>
          <div class="flex flex-col">
            <span class="text-[9px] uppercase font-semibold tracking-wider text-slate-400 leading-none">Nächster Scan:</span>
            <span class="font-mono font-bold text-xs text-indigo-300 leading-tight mt-0.5" id="next-scan-countdown">Berechne...</span>
          </div>
        </div>

        <!-- Manual Refresh Button -->
        <button id="btn-manual-refresh" onclick="triggerManualRefresh()" class="px-3 py-1.5 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700/60 text-xs font-semibold text-slate-200 hover:text-white flex items-center gap-1.5 transition active:scale-95 shadow-sm cursor-pointer" title="Jetzt aktualisieren oder am Handy nach unten ziehen">
          <svg id="refresh-icon" class="w-3.5 h-3.5 text-indigo-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          <span id="refresh-label">Refresh</span>
        </button>

        <!-- iOS Alerts Info Button -->
        <button onclick="openAlertsModal()" class="px-3 py-1.5 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/40 text-xs font-semibold text-indigo-300 hover:text-white flex items-center gap-1.5 transition active:scale-95 shadow-sm cursor-pointer" title="iOS Lockscreen Push-Alerts">
          <span class="text-sm">🔔</span>
          <span class="hidden sm:inline">iOS Alerts</span>
        </button>

        <!-- Hypothesen Guide Info Button -->
        <button onclick="openHypothesesModal()" class="px-3 py-1.5 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/40 text-xs font-semibold text-indigo-300 hover:text-white flex items-center gap-1.5 transition active:scale-95 shadow-sm cursor-pointer" title="Setup-Hypothesen & Trade-Plan Guide">
          <span class="text-sm">💡</span>
          <span class="hidden sm:inline">Hypothesen-Guide</span>
        </button>

        <!-- Signal-Historie Link Button -->
        <a href="history.html" class="px-3 py-1.5 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/40 text-xs font-semibold text-indigo-300 hover:text-white flex items-center gap-1.5 transition active:scale-95 shadow-sm cursor-pointer" title="Signal- & Benachrichtigungs-Historie">
          <span class="text-sm">📜</span>
          <span class="hidden sm:inline">Historie</span>
        </a>

        <!-- Quick Metrics -->
        <div class="flex items-center gap-1.5 sm:gap-2">
          <div class="px-2.5 py-1.5 rounded-lg bg-slate-800/60 border border-slate-700/50 flex items-center gap-1.5" title="Gesamt gescannte Werte">
            <span class="text-[11px] text-slate-400">Total:</span>
            <span class="font-mono font-bold text-xs text-white" id="stat-total">{db_data.get('total_analyzed', 0)}</span>
          </div>
          <div class="px-2.5 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center gap-1.5" title="High-Conviction Longs">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            <span class="text-[11px] text-emerald-300">L:</span>
            <span class="font-mono font-bold text-xs text-emerald-400" id="stat-long">{db_data.get('long_count', 0)}</span>
          </div>
          <div class="px-2.5 py-1.5 rounded-lg bg-rose-500/10 border border-rose-500/30 flex items-center gap-1.5" title="Short / Erschöpfung">
            <span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
            <span class="text-[11px] text-rose-300">S:</span>
            <span class="font-mono font-bold text-xs text-rose-400" id="stat-short">{db_data.get('short_count', 0)}</span>
          </div>
          <div class="px-2.5 py-1.5 rounded-lg bg-slate-800/60 border border-slate-700/50 flex items-center gap-1.5" title="Neutral / Watchlist">
            <span class="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
            <span class="text-[11px] text-slate-400">N:</span>
            <span class="font-mono font-bold text-xs text-slate-300" id="stat-neutral">{db_data.get('neutral_count', 0)}</span>
          </div>
        </div>

      </div>
    </div>
  </header>

  <!-- Main Container -->
  <main class="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">

    <!-- Highlight Opportunity Hero: Micron (MU) & Bitcoin (BTC) -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      
      <!-- Top Pick: Micron Technology (MU) -->
      <div class="relative overflow-hidden rounded-2xl bg-gradient-to-br from-emerald-950/40 via-slate-900/90 to-slate-900 border border-emerald-500/30 p-5 glow-emerald">
        <div class="absolute -right-12 -top-12 w-48 h-48 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none"></div>
        <div class="flex items-start justify-between">
          <div class="flex items-center gap-3">
            <span class="px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wider bg-emerald-500 text-slate-950">
              Top Opportunity
            </span>
            <span class="text-xs font-mono text-emerald-400 font-semibold">98% Score · Golden Confluence</span>
          </div>
          <span class="font-mono text-xs text-slate-400">NASDAQ:MU</span>
        </div>

        <div class="mt-3 flex items-baseline justify-between">
          <div>
            <h3 class="text-2xl font-bold text-white tracking-tight">Micron Technology</h3>
            <p class="text-xs text-slate-400">Halbleiter · Watchlist Aktien</p>
          </div>
          <div class="text-right">
            <span class="font-mono text-2xl font-extrabold text-emerald-400">878.84 USD</span>
            <span class="block text-xs font-mono text-emerald-300/80">Im 0.618 Golden Pocket</span>
          </div>
        </div>

        <div class="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
          <div class="p-2 rounded-lg bg-slate-800/60 border border-slate-700/60">
            <span class="text-slate-400 block text-[11px]">Setup</span>
            <span class="text-emerald-300 font-semibold truncate block">Hypothese 1 (SMC)</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-800/60 border border-slate-700/60">
            <span class="text-slate-400 block text-[11px]">Entry Zone</span>
            <span class="text-white font-semibold">868 - 880 $</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-800/60 border border-slate-700/60">
            <span class="text-slate-400 block text-[11px]">Stop-Loss</span>
            <span class="text-rose-400 font-semibold">852.00 $ (-2.9%)</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-800/60 border border-slate-700/60">
            <span class="text-slate-400 block text-[11px]">Take-Profit 2</span>
            <span class="text-cyan-400 font-semibold">965.00 $ (3.3 CRV)</span>
          </div>
        </div>

        <p class="mt-3 text-xs text-slate-300 leading-relaxed">
          <strong>Super-Analyst Rationale:</strong> Kurs sitzt exakt im 1D Fibonacci Golden Pocket (867-879 USD). Gleichzeitig Überdehnung unter das untere degencoder-Band. RSI im 4h/8h extrem überverkauft (26.6) mit aktiver bullischer Divergenz. VSA signalisiert stopping volume.
        </p>

        <div class="mt-4 flex items-center justify-between pt-3 border-t border-slate-800/80">
          <button onclick="openDetailModal('NASDAQ:MU')" class="text-xs font-semibold text-emerald-400 hover:text-emerald-300 flex items-center gap-1 transition">
            Multi-Timeframe Details (4h, 8h, 1D) →
          </button>
          <a href="https://www.tradingview.com/chart/?symbol=NASDAQ:MU" target="_blank" class="text-xs text-slate-400 hover:text-white transition flex items-center gap-1">
            TradingView Chart ↗
          </a>
        </div>
      </div>

      <!-- Bitcoin (BTC) -->
      <div class="relative overflow-hidden rounded-2xl bg-gradient-to-br from-indigo-950/40 via-slate-900/90 to-slate-900 border border-indigo-500/30 p-5 glow-emerald">
        <div class="absolute -right-12 -top-12 w-48 h-48 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none"></div>
        <div class="flex items-start justify-between">
          <div class="flex items-center gap-3">
            <span class="px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wider bg-indigo-500 text-white">
              Krypto Leitwolf
            </span>
            <span class="text-xs font-mono text-indigo-400 font-semibold">94% Score · Breakout Watch</span>
          </div>
          <span class="font-mono text-xs text-slate-400">COINBASE:BTCUSD</span>
        </div>

        <div class="mt-3 flex items-baseline justify-between">
          <div>
            <h3 class="text-2xl font-bold text-white tracking-tight">Bitcoin</h3>
            <p class="text-xs text-slate-400">Krypto · Watchlist Crypto</p>
          </div>
          <div class="text-right">
            <span class="font-mono text-2xl font-extrabold text-indigo-300">81,529 USD</span>
            <span class="block text-xs font-mono text-slate-400">Über EMA 233 (75.7k)</span>
          </div>
        </div>

        <div class="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
          <div class="p-2 rounded-lg bg-slate-800/60 border border-slate-700/60">
            <span class="text-slate-400 block text-[11px]">Setup</span>
            <span class="text-indigo-300 font-semibold truncate block">Hypothese 2 (Breakout)</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-800/60 border border-slate-700/60">
            <span class="text-slate-400 block text-[11px]">Trigger-Level</span>
            <span class="text-white font-semibold">> 82,320 $</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-800/60 border border-slate-700/60">
            <span class="text-slate-400 block text-[11px]">Stop-Loss</span>
            <span class="text-rose-400 font-semibold">79,400 $</span>
          </div>
          <div class="p-2 rounded-lg bg-slate-800/60 border border-slate-700/60">
            <span class="text-slate-400 block text-[11px]">Take-Profit 2</span>
            <span class="text-cyan-400 font-semibold">84,850 $ (3.1 CRV)</span>
          </div>
        </div>

        <p class="mt-3 text-xs text-slate-300 leading-relaxed">
          <strong>Super-Analyst Rationale:</strong> 1D Makro-Aufwärtstrend intakt. 8h reguläre bullische Divergenz aktiv. VSA zeigt extreme Austrocknung des Verkaufsdrucks (No Supply, Ratio 0.12). 4h-Bruch über den Bearish Order Block (82.320 USD) aktiviert den Impuls zur FVG-Magnetzone (84.3k-84.8k).
        </p>

        <div class="mt-4 flex items-center justify-between pt-3 border-t border-slate-800/80">
          <button onclick="openDetailModal('COINBASE:BTCUSD')" class="text-xs font-semibold text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition">
            Multi-Timeframe Details (4h, 8h, 1D) →
          </button>
          <a href="https://www.tradingview.com/chart/?symbol=COINBASE:BTCUSD" target="_blank" class="text-xs text-slate-400 hover:text-white transition flex items-center gap-1">
            TradingView Chart ↗
          </a>
        </div>
      </div>

    </div>

    <!-- Hypothesen Quick Guide Banner -->
    <div class="p-4 rounded-xl bg-slate-900/80 border border-indigo-500/30 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs shadow-lg">
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-lg bg-indigo-500/20 border border-indigo-500/40 flex items-center justify-center text-sm shrink-0">
          💡
        </div>
        <div class="space-y-0.5">
          <div class="font-bold text-white flex items-center gap-2">
            <span>Setup-Logik & Hypothesen</span>
            <span class="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 font-mono">3 Strategien</span>
          </div>
          <p class="text-slate-400 text-[11px] leading-relaxed">
            <strong class="text-emerald-400">Hypothese 1:</strong> Reversal am Wende-Extremum (Max CRV) &bull; 
            <strong class="text-indigo-400">Hypothese 2:</strong> Trendfolge im Pullback (Hohe Winrate) &bull; 
            <strong class="text-amber-400">Hypothese 3:</strong> Liquidity Hunt / Range Fakeout
          </p>
        </div>
      </div>
      <button onclick="openHypothesesModal()" class="self-start sm:self-auto px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs transition flex items-center gap-1.5 shadow-sm shrink-0 cursor-pointer">
        Guide & Regeln anzeigen →
      </button>
    </div>

    <!-- Filter & Navigation Control Center -->
    <div class="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
      <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        
        <!-- Direction Filter Pills -->
        <div class="flex flex-wrap items-center gap-2">
          <button onclick="setDirectionFilter('ALL')" id="filter-dir-ALL" class="filter-dir-btn px-3 py-1.5 rounded-lg text-xs font-semibold transition bg-indigo-600 text-white shadow-sm shadow-indigo-500/20">
            Alle (<span id="count-all">55</span>)
          </button>
          <button onclick="setDirectionFilter('LONG')" id="filter-dir-LONG" class="filter-dir-btn px-3 py-1.5 rounded-lg text-xs font-semibold transition bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700">
            🟢 Long Setups (<span id="count-long">14</span>)
          </button>
          <button onclick="setDirectionFilter('SHORT')" id="filter-dir-SHORT" class="filter-dir-btn px-3 py-1.5 rounded-lg text-xs font-semibold transition bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700">
            🔴 Short Setups (<span id="count-short">20</span>)
          </button>
          <button onclick="setDirectionFilter('NEUTRAL')" id="filter-dir-NEUTRAL" class="filter-dir-btn px-3 py-1.5 rounded-lg text-xs font-semibold transition bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700">
            ⚪ Neutral / Watchlist (<span id="count-neutral">21</span>)
          </button>
        </div>

        <!-- Search Bar -->
        <div class="relative w-full lg:w-72">
          <input type="text" id="search-input" oninput="applyFilters()" placeholder="Symbol oder Name suchen..." class="w-full px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-700/80 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition">
          <span class="absolute right-3 top-2.5 text-xs text-slate-500 pointer-events-none">🔍</span>
        </div>

      </div>

      <!-- Secondary Filter Row: Asset Class, Sorting, View Toggle -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-3 border-t border-slate-800/80">
        
        <!-- Category Buttons -->
        <div class="flex flex-wrap items-center gap-1.5 text-xs">
          <span class="text-slate-400 mr-1 text-[11px] uppercase tracking-wider font-semibold">Klasse:</span>
          <button onclick="setCategoryFilter('ALL')" id="filter-cat-ALL" class="filter-cat-btn px-2.5 py-1 rounded-md transition bg-slate-700 text-white font-medium">Alle</button>
          <button onclick="setCategoryFilter('Crypto')" id="filter-cat-Crypto" class="filter-cat-btn px-2.5 py-1 rounded-md transition text-slate-400 hover:text-white hover:bg-slate-800 font-medium">Crypto</button>
          <button onclick="setCategoryFilter('Stock')" id="filter-cat-Stock" class="filter-cat-btn px-2.5 py-1 rounded-md transition text-slate-400 hover:text-white hover:bg-slate-800 font-medium">Aktien</button>
          <button onclick="setCategoryFilter('Commodity')" id="filter-cat-Commodity" class="filter-cat-btn px-2.5 py-1 rounded-md transition text-slate-400 hover:text-white hover:bg-slate-800 font-medium">Rohstoffe</button>
          <button onclick="setCategoryFilter('Macro')" id="filter-cat-Macro" class="filter-cat-btn px-2.5 py-1 rounded-md transition text-slate-400 hover:text-white hover:bg-slate-800 font-medium">Makro/Indizes</button>
        </div>

        <!-- Sort & View Controls -->
        <div class="flex items-center gap-3">
          <div class="flex items-center gap-2">
            <span class="text-xs text-slate-400">Sortierung:</span>
            <select id="sort-select" onchange="applyFilters()" class="px-2.5 py-1.5 rounded-lg bg-slate-950 border border-slate-700/80 text-xs text-white focus:outline-none focus:border-indigo-500">
              <option value="score_desc">Höchster Score</option>
              <option value="crv_desc">Höchstes CRV</option>
              <option value="rsi_asc">RSI Überverkauft (Low)</option>
              <option value="rsi_desc">RSI Überkauft (High)</option>
              <option value="name_asc">Name (A-Z)</option>
            </select>
          </div>

          <!-- View Toggle (Grid vs Table) -->
          <div class="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800">
            <button onclick="setViewMode('grid')" id="view-grid-btn" class="px-2 py-1 rounded text-xs font-semibold bg-indigo-600 text-white">Cards</button>
            <button onclick="setViewMode('table')" id="view-table-btn" class="px-2 py-1 rounded text-xs font-semibold text-slate-400 hover:text-white">Tabelle</button>
          </div>
        </div>

      </div>
    </div>

    <!-- Active Filter Indicators -->
    <div id="results-count" class="text-xs text-slate-400 font-medium">
      Zeige 55 Setups
    </div>

    <!-- Cards Grid View -->
    <div id="assets-grid" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <!-- Dynamisch gerendert via JS -->
    </div>

    <!-- Table View (Hidden by default) -->
    <div id="assets-table-container" class="hidden overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60">
      <table class="w-full text-left text-xs border-collapse">
        <thead>
          <tr class="border-b border-slate-800 bg-slate-950/80 text-slate-400 font-mono uppercase text-[11px]">
            <th class="p-3">Asset</th>
            <th class="p-3">Signal</th>
            <th class="p-3">Score</th>
            <th class="p-3">Kurs</th>
            <th class="p-3">1D Trend</th>
            <th class="p-3">4h RSI</th>
            <th class="p-3">Setup & Trade Plan</th>
            <th class="p-3">CRV</th>
            <th class="p-3 text-right">Details</th>
          </tr>
        </thead>
        <tbody id="assets-table-body" class="divide-y divide-slate-800/60 font-mono">
          <!-- Dynamisch via JS -->
        </tbody>
      </table>
    </div>

  </main>

  <!-- Multi-Timeframe Inspection Modal -->
  <div id="detail-modal" class="fixed inset-0 z-50 hidden bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="bg-[#0f172a] border border-slate-700/80 rounded-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto shadow-2xl p-6 space-y-6">
      
      <!-- Modal Header -->
      <div class="flex items-start justify-between pb-4 border-b border-slate-800">
        <div>
          <div class="flex items-center gap-2">
            <span id="modal-signal-badge" class="px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider"></span>
            <h2 id="modal-asset-name" class="text-xl font-bold text-white tracking-tight"></h2>
            <span id="modal-asset-ticker" class="text-xs font-mono text-slate-400"></span>
          </div>
          <div class="flex items-center gap-2 mt-1">
            <p id="modal-setup-title" class="text-xs text-indigo-400 font-semibold"></p>
            <button onclick="openHypothesesModal(document.getElementById('modal-setup-title').innerText)" class="px-2 py-0.5 rounded bg-indigo-500/10 hover:bg-indigo-500/25 text-indigo-300 hover:text-white border border-indigo-500/30 text-[10px] font-semibold transition cursor-pointer flex items-center gap-1" title="Erklärung zu dieser Setup-Hypothese anzeigen">
              💡 Setup-Logik
            </button>
          </div>
        </div>
        <button onclick="closeDetailModal()" class="w-8 h-8 rounded-lg bg-slate-800 text-slate-400 hover:text-white flex items-center justify-center transition">
          ✕
        </button>
      </div>

      <!-- Trade Plan Banner -->
      <div id="modal-trade-plan" class="p-4 rounded-xl bg-slate-900 border border-slate-800 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
        <!-- Dynamisch -->
      </div>

      <!-- Visuelle Chart-Analyse mit Indikatoren & TradingView Live-Widget -->
      <div class="rounded-xl bg-slate-900/90 border border-slate-800 p-4 space-y-3">
        <!-- Switcher: Vektor-Chart vs. TradingView Live Widget -->
        <div class="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-slate-800/80">
          <div class="flex items-center gap-2">
            <button id="tab-btn-vector" onclick="switchModalView('vector')" class="px-3 py-1.5 rounded-lg text-xs font-bold bg-indigo-600 text-white shadow-sm flex items-center gap-1.5 transition">
              <svg class="w-3.5 h-3.5 text-indigo-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z"></path></svg>
              SMC & Indikatoren Vektor-Chart
            </button>
            <button id="tab-btn-tvwidget" onclick="switchModalView('tvwidget')" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 text-slate-400 hover:text-white flex items-center gap-1.5 transition">
              <svg class="w-3.5 h-3.5 text-sky-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
              TradingView Live-Chart (Interaktiv)
            </button>
          </div>

          <!-- Timeframe Selector Tabs (für Vektor-Chart) -->
          <div id="vector-tf-selectors" class="flex items-center gap-1 bg-slate-950/90 p-1 rounded-lg border border-slate-800">
            <span class="text-[10px] text-slate-400 font-mono px-1.5">Timeframe:</span>
            <button id="btn-chart-tf-4h" onclick="selectModalTimeframe('4h')" class="px-3 py-1 rounded text-xs font-mono font-bold bg-indigo-600 text-white shadow-sm shadow-indigo-500/30">4h</button>
            <button id="btn-chart-tf-8h" onclick="selectModalTimeframe('8h')" class="px-3 py-1 rounded text-xs font-mono font-semibold bg-transparent text-slate-400 hover:text-white hover:bg-slate-800">8h</button>
            <button id="btn-chart-tf-1D" onclick="selectModalTimeframe('1D')" class="px-3 py-1 rounded text-xs font-mono font-semibold bg-transparent text-slate-400 hover:text-white hover:bg-slate-800">1D</button>
          </div>
        </div>

        <!-- 1. Vektor-Chart Container -->
        <div id="modal-vector-container" class="space-y-3">
          <div class="relative w-full rounded-xl overflow-hidden border border-slate-800/80 bg-[#070a13] flex flex-col items-center justify-center p-1">
            <img id="modal-chart-img" src="" alt="Chart Analyse" class="w-full h-auto max-h-[500px] object-contain transition-all duration-200 rounded" />
            
            <!-- Fullscreen Action Button -->
            <div class="absolute top-3 right-3 flex items-center gap-2 opacity-80 hover:opacity-100 transition">
              <button onclick="openChartFullscreen()" title="In voller Auflösung im neuen Tab öffnen" class="px-2.5 py-1 rounded-md bg-slate-900/90 border border-slate-700/80 hover:bg-slate-800 text-[11px] font-mono text-slate-300 hover:text-white flex items-center gap-1 shadow">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                Vollbild ↗
              </button>
            </div>
          </div>

          <!-- Legend / Indicator Key -->
          <div class="pt-2 border-t border-slate-800/60 flex flex-wrap items-center justify-between text-[11px] text-slate-400 gap-y-2">
            <div class="flex flex-wrap items-center gap-3 font-mono text-[10px]">
              <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-sm bg-amber-400/30 border border-amber-400"></span> Golden Pocket (0.618 - 0.65)</span>
              <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-sm bg-emerald-500/30 border border-emerald-500"></span> Bull FVG</span>
              <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-sm bg-rose-500/30 border border-rose-500"></span> Bear FVG</span>
              <span class="flex items-center gap-1.5"><span class="w-3 h-0.5 bg-sky-400"></span> degencoder Bänder</span>
              <span class="flex items-center gap-1.5"><span class="w-3 h-0.5 bg-indigo-400"></span> EMA 233 Trend</span>
              <span class="flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-purple-400"></span> Wyckoff VSA & RSI(14)</span>
            </div>
            <span class="text-[10px] text-slate-400 font-mono">100% Echte Kerzen aus TV MCP</span>
          </div>
        </div>

        <!-- 2. TradingView Interactive Live Widget Container -->
        <div id="modal-tvwidget-container" class="hidden w-full h-[500px] rounded-xl overflow-hidden border border-slate-800 bg-[#070a13]">
          <div id="tv-widget-mount" class="w-full h-full"></div>
        </div>

      </div>

      <!-- Multi-Timeframe Matrix (4h, 8h, 1D Side-by-Side) -->
      <div>
        <h4 class="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">Multi-Timeframe Indikatoren-Matrix</h4>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3" id="modal-timeframes-grid">
          <!-- 1D, 8h, 4h Spalten -->
        </div>
      </div>

      <!-- Super-Analyst Begründung -->
      <div class="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-2">
        <h4 class="text-xs font-bold uppercase tracking-wider text-slate-400">Super-Analyst Rationale & Confluence-Faktoren</h4>
        <p id="modal-analyst-note" class="text-xs text-slate-300 leading-relaxed"></p>
        <ul id="modal-reasons-list" class="text-xs text-slate-400 list-disc list-inside space-y-1 font-mono pt-1"></ul>
      </div>

      <!-- Footer Actions -->
      <div class="flex items-center justify-between pt-3 border-t border-slate-800">
        <span class="text-xs text-slate-500 font-mono">Offizieller TradingView MCP Datafeed</span>
        <div class="flex items-center gap-3">
          <a id="modal-tv-link" href="#" target="_blank" class="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold transition flex items-center gap-1.5">
            TradingView Layout öffnen ↗
          </a>
          <button onclick="closeDetailModal()" class="px-4 py-2 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 text-xs font-semibold transition">
            Schließen
          </button>
        </div>
      </div>

    </div>
  </div>

  <!-- Embedded Database (Offline Fallback & Zero CORS) -->
  <script>
    const EMBEDDED_DATABASE = {json_str};
    let currentData = EMBEDDED_DATABASE;
    let filteredAssets = [...currentData.assets];
    let activeDirection = 'ALL';
    let activeCategory = 'ALL';
    let currentViewMode = 'grid';

    // Versuche Live-JSON nachzuladen
    fetch('market_analysis_db.json')
      .then(r => r.json())
      .then(data => {{
        currentData = data;
        filteredAssets = [...currentData.assets];
        updateStats();
        applyFilters();
      }})
      .catch(e => {{
        console.log("Nutze integrierte Datenbank (Offline/File-Modus)");
        updateStats();
        applyFilters();
      }});

    function updateStats() {{
      const setVal = (id, val) => {{
        const el = document.getElementById(id);
        if (el && val !== undefined && val !== null) el.innerText = val;
      }};

      setVal('stat-total', currentData.total_analyzed);
      setVal('stat-long', currentData.long_count);
      setVal('stat-short', currentData.short_count);
      setVal('stat-neutral', currentData.neutral_count);

      setVal('count-all', currentData.total_analyzed);
      setVal('count-long', currentData.long_count);
      setVal('count-short', currentData.short_count);
      setVal('count-neutral', currentData.neutral_count);
    }}

    function setDirectionFilter(dir) {{
      activeDirection = dir;
      document.querySelectorAll('.filter-dir-btn').forEach(btn => {{
        btn.classList.remove('bg-indigo-600', 'text-white', 'shadow-sm', 'shadow-indigo-500/20');
        btn.classList.add('bg-slate-800', 'text-slate-300');
      }});
      const activeBtn = document.getElementById('filter-dir-' + dir);
      if (activeBtn) {{
        activeBtn.classList.remove('bg-slate-800', 'text-slate-300');
        activeBtn.classList.add('bg-indigo-600', 'text-white', 'shadow-sm', 'shadow-indigo-500/20');
      }}
      applyFilters();
    }}

    function setCategoryFilter(cat) {{
      activeCategory = cat;
      document.querySelectorAll('.filter-cat-btn').forEach(btn => {{
        btn.classList.remove('bg-slate-700', 'text-white');
        btn.classList.add('text-slate-400');
      }});
      const activeBtn = document.getElementById('filter-cat-' + cat);
      if (activeBtn) {{
        activeBtn.classList.remove('text-slate-400');
        activeBtn.classList.add('bg-slate-700', 'text-white');
      }}
      applyFilters();
    }}

    function setViewMode(mode) {{
      currentViewMode = mode;
      const gridContainer = document.getElementById('assets-grid');
      const tableContainer = document.getElementById('assets-table-container');
      const gridBtn = document.getElementById('view-grid-btn');
      const tableBtn = document.getElementById('view-table-btn');

      if (mode === 'grid') {{
        gridContainer.classList.remove('hidden');
        tableContainer.classList.add('hidden');
        gridBtn.classList.add('bg-indigo-600', 'text-white');
        gridBtn.classList.remove('text-slate-400');
        tableBtn.classList.remove('bg-indigo-600', 'text-white');
        tableBtn.classList.add('text-slate-400');
      }} else {{
        gridContainer.classList.add('hidden');
        tableContainer.classList.remove('hidden');
        tableBtn.classList.add('bg-indigo-600', 'text-white');
        tableBtn.classList.remove('text-slate-400');
        gridBtn.classList.remove('bg-indigo-600', 'text-white');
        gridBtn.classList.add('text-slate-400');
      }}
    }}

    function applyFilters() {{
      const searchEl = document.getElementById('search-input');
      const sortEl = document.getElementById('sort-select');
      const countEl = document.getElementById('results-count');

      const query = searchEl ? searchEl.value.toLowerCase().trim() : '';
      const sortMode = sortEl ? sortEl.value : 'score_desc';

      filteredAssets = currentData.assets.filter(a => {{
        // Direction
        if (activeDirection !== 'ALL' && a.signal !== activeDirection) return false;
        // Category
        if (activeCategory !== 'ALL' && a.asset_type !== activeCategory) return false;
        // Search
        if (query) {{
          const matchSym = a.symbol.toLowerCase().includes(query);
          const matchName = a.name.toLowerCase().includes(query);
          const matchCat = a.category.toLowerCase().includes(query);
          if (!matchSym && !matchName && !matchCat) return false;
        }}
        return true;
      }});

      // Sortierung
      filteredAssets.sort((x, y) => {{
        if (sortMode === 'score_desc') return y.score - x.score;
        if (sortMode === 'crv_desc') return y.crv - x.crv;
        if (sortMode === 'name_asc') return x.name.localeCompare(y.name);
        const rsiX = (x.timeframes && x.timeframes['4h']) ? x.timeframes['4h'].rsi : 50;
        const rsiY = (y.timeframes && y.timeframes['4h']) ? y.timeframes['4h'].rsi : 50;
        if (sortMode === 'rsi_asc') return rsiX - rsiY;
        if (sortMode === 'rsi_desc') return rsiY - rsiX;
        return 0;
      }});

      if (countEl) {{
        countEl.innerText = `Zeige ${{filteredAssets.length}} von ${{currentData.assets.length}} Setups`;
      }}
      renderAssets();
    }}

    function formatNumber(num) {{
      if (num === null || num === undefined) return '-';
      if (num >= 1000) {{
        return num.toLocaleString('en-US', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
      }}
      return num.toLocaleString('en-US', {{ minimumFractionDigits: 2, maximumFractionDigits: 4 }});
    }}

    function renderAssets() {{
      const grid = document.getElementById('assets-grid');
      const tableBody = document.getElementById('assets-table-body');
      grid.innerHTML = '';
      tableBody.innerHTML = '';

      if (filteredAssets.length === 0) {{
        grid.innerHTML = `
          <div class="col-span-full p-12 text-center rounded-xl bg-slate-900 border border-slate-800 text-slate-400">
            Keine Assets gefunden für die ausgewählten Filterkriterien.
          </div>
        `;
        return;
      }}

      filteredAssets.forEach(a => {{
        const isLong = a.signal === 'LONG';
        const isShort = a.signal === 'SHORT';

        const badgeColor = isLong 
          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
          : isShort 
          ? 'bg-rose-500/10 text-rose-400 border-rose-500/30'
          : 'bg-slate-800 text-slate-400 border-slate-700';

        const cardBorder = isLong 
          ? 'hover:border-emerald-500/50' 
          : isShort 
          ? 'hover:border-rose-500/50' 
          : 'hover:border-slate-700';

        const d1 = a.timeframes['1D'];
        const d8 = a.timeframes['8h'];
        const d4 = a.timeframes['4h'];

        const rsiVal = d4 ? d4.rsi : (d1 ? d1.rsi : 50);
        const rsiColor = rsiVal <= 32 ? 'text-emerald-400 font-bold' : (rsiVal >= 68 ? 'text-rose-400 font-bold' : 'text-slate-300');

        const divs = [...(d1 ? d1.divergences : []), ...(d8 ? d8.divergences : []), ...(d4 ? d4.divergences : [])];
        const hasBullDiv = divs.some(d => d.includes('Bullische'));
        const hasBearDiv = divs.some(d => d.includes('Bärische'));

        // Grid Card
        const card = document.createElement('div');
        card.className = `p-4 rounded-xl bg-slate-900/90 border border-slate-800/90 transition shadow-sm hover:shadow-lg ${{cardBorder}} flex flex-col justify-between space-y-4`;
        card.innerHTML = `
          <div>
            <!-- Card Header -->
            <div class="flex items-start justify-between">
              <div>
                <div class="flex items-center gap-2">
                  <span class="font-bold text-white text-base tracking-tight">${{a.name}}</span>
                  <span class="text-xs font-mono text-slate-400">${{a.symbol.split(':')[1] || a.symbol}}</span>
                </div>
                <span class="text-[11px] text-slate-400">${{a.category}}</span>
              </div>
              <div class="text-right">
                <span class="px-2 py-0.5 rounded text-xs font-mono font-bold border ${{badgeColor}}">
                  ${{a.signal}}
                </span>
                <span class="block text-[11px] font-mono text-slate-400 mt-1">${{a.score}}% Score</span>
              </div>
            </div>

            <!-- Price & Core Metrics -->
            <div class="mt-3 flex items-baseline justify-between pb-3 border-b border-slate-800/60">
              <span class="font-mono text-lg font-bold text-white">${{formatNumber(a.price)}} <span class="text-xs text-slate-400 font-normal">USD</span></span>
              <div class="flex items-center gap-1.5 text-xs font-mono">
                <span class="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">RSI: <span class="${{rsiColor}}">${{rsiVal}}</span></span>
                ${{hasBullDiv ? '<span class="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 text-[10px]">Bull Div</span>' : ''}}
                ${{hasBearDiv ? '<span class="px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-300 border border-rose-500/20 text-[10px]">Bear Div</span>' : ''}}
              </div>
            </div>

            <!-- Setup Info -->
            <div class="mt-3 space-y-1.5">
              <div class="flex items-center justify-between gap-1">
                <span class="text-xs font-semibold text-indigo-300 truncate">${{a.setup_name}}</span>
                <button onclick="openHypothesesModal('${{a.setup_name}}')" class="px-1.5 py-0.5 rounded bg-indigo-500/10 hover:bg-indigo-500/30 text-indigo-300 hover:text-white border border-indigo-500/20 text-[10px] font-semibold transition shrink-0 cursor-pointer" title="Setup-Hypothese erklären">
                  Info 💡
                </button>
              </div>
              <p class="text-xs text-slate-400 line-clamp-2 leading-relaxed">${{a.analyst_note}}</p>
            </div>

            <!-- Trade Plan Box -->
            <div class="mt-3 p-2.5 rounded-lg bg-slate-950/70 border border-slate-800/80 grid grid-cols-3 gap-2 text-[11px] font-mono">
              <div>
                <span class="text-slate-400 block text-[10px]">Entry</span>
                <span class="text-white font-semibold truncate block">${{formatNumber(a.entry_range[0])}}</span>
              </div>
              <div>
                <span class="text-slate-400 block text-[10px]">Stop-Loss</span>
                <span class="text-rose-400 font-semibold truncate block">${{formatNumber(a.stop_loss)}}</span>
              </div>
              <div>
                <span class="text-slate-400 block text-[10px]">TP2 (CRV)</span>
                <span class="text-emerald-400 font-semibold truncate block">${{formatNumber(a.take_profit_2)}} <span class="text-[10px] text-slate-400">(${{a.crv}}:1)</span></span>
              </div>
            </div>
          </div>

          <!-- Card Actions -->
          <div class="pt-3 border-t border-slate-800/60 flex items-center justify-between text-xs">
            <button onclick="openDetailModal('${{a.symbol}}')" class="px-2.5 py-1 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 hover:text-white font-semibold flex items-center gap-1.5 transition border border-indigo-500/30">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z"></path></svg>
              Chart & Setup →
            </button>
            <a href="https://www.tradingview.com/chart/?symbol=${{encodeURIComponent(a.symbol)}}" target="_blank" class="text-slate-400 hover:text-white transition flex items-center gap-1 font-mono text-[11px]">
              TV Chart ↗
            </a>
          </div>
        `;
        grid.appendChild(card);

        // Table Row
        const tr = document.createElement('tr');
        tr.className = "hover:bg-slate-800/40 transition cursor-pointer";
        tr.onclick = (e) => {{
          if (e.target.tagName !== 'A') openDetailModal(a.symbol);
        }};
        tr.innerHTML = `
          <td class="p-3">
            <div class="font-bold text-white text-xs">${{a.name}}</div>
            <div class="text-[10px] text-slate-400">${{a.symbol}}</div>
          </td>
          <td class="p-3">
            <span class="px-2 py-0.5 rounded text-[11px] font-bold border ${{badgeColor}}">${{a.signal}}</span>
          </td>
          <td class="p-3 font-semibold text-slate-200">${{a.score}}%</td>
          <td class="p-3 text-white font-bold">${{formatNumber(a.price)}}</td>
          <td class="p-3 text-slate-300">${{d1 ? d1.trend : '-'}}</td>
          <td class="p-3 ${{rsiColor}}">${{rsiVal}}</td>
          <td class="p-3 max-w-xs truncate text-slate-300">
            <div class="flex items-center gap-1.5">
              <span class="text-indigo-300 font-semibold truncate">${{a.setup_name}}</span>
              <button onclick="event.stopPropagation(); openHypothesesModal('${{a.setup_name}}')" class="px-1.5 py-0.5 rounded bg-indigo-500/10 hover:bg-indigo-500/30 text-indigo-300 hover:text-white border border-indigo-500/20 text-[9px] font-semibold transition shrink-0 cursor-pointer" title="Setup-Hypothese erklären">
                💡 Info
              </button>
            </div>
            <span class="block text-[10px] text-slate-400">Entry: ${{formatNumber(a.entry_range[0])}} | SL: ${{formatNumber(a.stop_loss)}}</span>
          </td>
          <td class="p-3 text-emerald-400 font-bold">${{a.crv}}:1</td>
          <td class="p-3 text-right">
            <button onclick="openDetailModal('${{a.symbol}}')" class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-indigo-400 text-xs transition">
              Matrix
            </button>
          </td>
        `;
        tableBody.appendChild(tr);
      }});
    }}

    let currentModalAsset = null;
    let currentModalTf = '4h';
    let currentModalView = 'vector';

    function switchModalView(view) {{
      currentModalView = view;
      const vecBox = document.getElementById('modal-vector-container');
      const tvBox = document.getElementById('modal-tvwidget-container');
      const tfSel = document.getElementById('vector-tf-selectors');
      const btnVec = document.getElementById('tab-btn-vector');
      const btnTv = document.getElementById('tab-btn-tvwidget');

      if (view === 'vector') {{
        vecBox.classList.remove('hidden');
        tvBox.classList.add('hidden');
        tfSel.classList.remove('hidden');
        btnVec.className = 'px-3 py-1.5 rounded-lg text-xs font-bold bg-indigo-600 text-white shadow-sm flex items-center gap-1.5 transition';
        btnTv.className = 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 text-slate-400 hover:text-white flex items-center gap-1.5 transition';
      }} else {{
        vecBox.classList.add('hidden');
        tvBox.classList.remove('hidden');
        tfSel.classList.add('hidden');
        btnTv.className = 'px-3 py-1.5 rounded-lg text-xs font-bold bg-indigo-600 text-white shadow-sm flex items-center gap-1.5 transition';
        btnVec.className = 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 text-slate-400 hover:text-white flex items-center gap-1.5 transition';
        renderTradingViewWidget();
      }}
    }}

    function renderTradingViewWidget() {{
      if (!currentModalAsset) return;
      const mount = document.getElementById('tv-widget-mount');
      mount.innerHTML = '';

      const tfInterval = currentModalTf === '1D' ? 'D' : currentModalTf === '8h' ? '480' : '240';
      const containerId = 'tv_chart_' + Math.floor(Math.random() * 100000);
      mount.innerHTML = `<div id="${{containerId}}" style="height:100%;width:100%"></div>`;

      const script = document.createElement('script');
      script.src = 'https://s3.tradingview.com/tv.js';
      script.async = true;
      script.onload = () => {{
        if (typeof TradingView !== 'undefined') {{
          new TradingView.widget({{
            "autosize": true,
            "symbol": currentModalAsset.symbol,
            "interval": tfInterval,
            "timezone": "Europe/Berlin",
            "theme": "dark",
            "style": "1",
            "locale": "de_DE",
            "toolbar_bg": "#070a13",
            "enable_publishing": false,
            "hide_side_toolbar": false,
            "allow_symbol_change": true,
            "container_id": containerId
          }});
        }}
      }};
      mount.appendChild(script);
    }}

    function selectModalTimeframe(tf) {{
      currentModalTf = tf;
      if (!currentModalAsset) return;

      ['4h', '8h', '1D'].forEach(t => {{
        const btn = document.getElementById('btn-chart-tf-' + t);
        if (btn) {{
          if (t === tf) {{
            btn.className = 'px-3 py-1 rounded text-xs font-mono font-bold bg-indigo-600 text-white shadow-sm shadow-indigo-500/30';
          }} else {{
            btn.className = 'px-3 py-1 rounded text-xs font-mono font-semibold bg-transparent text-slate-400 hover:text-white hover:bg-slate-800';
          }}
        }}
      }});

      const img = document.getElementById('modal-chart-img');
      const charts = currentModalAsset.charts || {{}};
      let chartPath = charts[tf];
      if (!chartPath) {{
        const safe = currentModalAsset.symbol.replace(/:/g, '_').replace(/!/g, '_').replace(/\\./g, '_').replace(/\\//g, '_');
        chartPath = `charts/${{safe}}_${{tf}}.svg`;
      }}
      img.src = chartPath;
      img.alt = `${{currentModalAsset.name}} (${{tf}}) Chart`;

      if (currentModalView === 'tvwidget') {{
        renderTradingViewWidget();
      }}
    }}

    function openChartFullscreen() {{
      const img = document.getElementById('modal-chart-img');
      if (img && img.src) {{
        window.open(img.src, '_blank');
      }}
    }}

    function openDetailModal(symbol) {{
      const a = currentData.assets.find(x => x.symbol === symbol);
      if (!a) return;

      currentModalAsset = a;
      switchModalView('vector');
      selectModalTimeframe('4h');

      document.getElementById('modal-asset-name').innerText = a.name;
      document.getElementById('modal-asset-ticker').innerText = a.symbol;
      document.getElementById('modal-setup-title').innerText = a.setup_name + ` (${{a.score}}% Score)`;

      const badge = document.getElementById('modal-signal-badge');
      badge.innerText = a.signal;
      if (a.signal === 'LONG') {{
        badge.className = 'px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider bg-emerald-500/20 text-emerald-400 border border-emerald-500/40';
      }} else if (a.signal === 'SHORT') {{
        badge.className = 'px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider bg-rose-500/20 text-rose-400 border border-rose-500/40';
      }} else {{
        badge.className = 'px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider bg-slate-800 text-slate-300 border border-slate-700';
      }}

      // Trade Plan Banner
      const plan = document.getElementById('modal-trade-plan');
      plan.innerHTML = `
        <div>
          <span class="text-slate-400 block text-[11px]">Aktueller Kurs</span>
          <span class="text-white font-bold text-sm">${{formatNumber(a.price)}} USD</span>
        </div>
        <div>
          <span class="text-slate-400 block text-[11px]">Empfohlene Entry-Zone</span>
          <span class="text-emerald-300 font-bold text-sm">${{formatNumber(a.entry_range[0])}} - ${{formatNumber(a.entry_range[1])}}</span>
        </div>
        <div>
          <span class="text-slate-400 block text-[11px]">Stop-Loss (Invalidierung)</span>
          <span class="text-rose-400 font-bold text-sm">${{formatNumber(a.stop_loss)}}</span>
        </div>
        <div>
          <span class="text-slate-400 block text-[11px]">Take-Profit 1 & 2 (CRV)</span>
          <span class="text-cyan-400 font-bold text-sm">${{formatNumber(a.take_profit_2)}} (${{a.crv}}:1)</span>
        </div>
      `;

      // Timeframes Matrix
      const tfGrid = document.getElementById('modal-timeframes-grid');
      tfGrid.innerHTML = '';

      ['1D', '8h', '4h'].forEach(tf => {{
        const d = a.timeframes[tf];
        const tfCol = document.createElement('div');
        tfCol.className = 'p-3.5 rounded-xl bg-slate-900 border border-slate-800 space-y-2.5 font-mono text-xs';
        
        if (!d) {{
          tfCol.innerHTML = `<span class="font-bold text-white block pb-1 border-b border-slate-800">${{tf}} Chart</span><span class="text-slate-500">Keine Daten</span>`;
        }} else {{
          tfCol.innerHTML = `
            <div class="flex items-center justify-between pb-1.5 border-b border-slate-800">
              <span class="font-bold text-white text-sm">${{tf}} Chart</span>
              <span class="text-[11px] font-semibold ${{d.trend === 'BULLISH' ? 'text-emerald-400' : 'text-rose-400'}}">${{d.trend}}</span>
            </div>
            <div class="space-y-1.5 text-[11px]">
              <div class="flex justify-between"><span class="text-slate-400">RSI (14):</span> <span class="text-white font-bold">${{d.rsi}}</span></div>
              <div class="flex justify-between"><span class="text-slate-400">degen Kanal:</span> <span class="text-slate-300 truncate max-w-[140px]">${{d.channel_position}}</span></div>
              <div class="flex justify-between"><span class="text-slate-400">VSA Wyckoff:</span> <span class="text-slate-300">${{d.vsa_class}}</span></div>
              <div class="flex justify-between"><span class="text-slate-400">Golden Pocket:</span> <span class="text-amber-300">${{d.golden_pocket[0]}} - ${{d.golden_pocket[1]}}</span></div>
              <div class="flex justify-between"><span class="text-slate-400">In Golden Pocket:</span> <span class="${{d.in_golden_pocket ? 'text-emerald-400 font-bold' : 'text-slate-500'}}">${{d.in_golden_pocket ? 'JA (Confluence!)' : 'Nein'}}</span></div>
              <div class="pt-1.5 border-t border-slate-800/60">
                <span class="text-slate-400 block text-[10px] mb-0.5">Divergenzen:</span>
                <span class="text-indigo-300 block text-[10px]">${{d.divergences.length > 0 ? d.divergences.join('<br>') : 'Keine aktive Divergenz'}}</span>
              </div>
            </div>
          `;
        }}
        tfGrid.appendChild(tfCol);
      }});

      document.getElementById('modal-analyst-note').innerText = a.analyst_note;
      
      const reasonsList = document.getElementById('modal-reasons-list');
      reasonsList.innerHTML = '';
      (a.reasons || []).forEach(r => {{
        const li = document.createElement('li');
        li.innerText = r;
        reasonsList.appendChild(li);
      }});

      document.getElementById('modal-tv-link').href = `https://www.tradingview.com/chart/?symbol=${{encodeURIComponent(a.symbol)}}`;

      document.getElementById('detail-modal').classList.remove('hidden');
    }}

    function closeDetailModal() {{
      document.getElementById('detail-modal').classList.add('hidden');
    }}

    // ==========================================
    // 🔔 Alerts Modal Handlers
    // ==========================================
    function openAlertsModal() {{
      const m = document.getElementById('alerts-modal');
      if (m) m.classList.remove('hidden');
    }}

    function closeAlertsModal() {{
      const m = document.getElementById('alerts-modal');
      if (m) m.classList.add('hidden');
    }}

    // ==========================================
    // 💡 Hypothesen Guide Modal Handlers
    // ==========================================
    function openHypothesesModal(highlight) {{
      const m = document.getElementById('hypotheses-modal');
      if (m) {{
        m.classList.remove('hidden');
        if (highlight) {{
          const hStr = String(highlight);
          if (hStr.includes('Hypothese 1') || hStr.includes('Reversal')) filterHypothesisModal('h1');
          else if (hStr.includes('Hypothese 2') || hStr.includes('Continuation') || hStr.includes('Hidden')) filterHypothesisModal('h2');
          else if (hStr.includes('Hypothese 3') || hStr.includes('Fakeout') || hStr.includes('Wyckoff')) filterHypothesisModal('h3');
          else filterHypothesisModal('all');
        }} else {{
          filterHypothesisModal('all');
        }}
      }}
    }}

    function closeHypothesesModal() {{
      const m = document.getElementById('hypotheses-modal');
      if (m) m.classList.add('hidden');
    }}

    function filterHypothesisModal(mode) {{
      const pills = document.querySelectorAll('.hypo-filter-pill');
      pills.forEach(p => {{
        p.classList.remove('bg-indigo-600', 'text-white', 'shadow-sm');
        p.classList.add('bg-slate-800', 'text-slate-300');
      }});
      const activePill = document.getElementById('hypo-pill-' + mode);
      if (activePill) {{
        activePill.classList.remove('bg-slate-800', 'text-slate-300');
        activePill.classList.add('bg-indigo-600', 'text-white', 'shadow-sm');
      }}

      const cards = ['h1', 'h2', 'h3'];
      cards.forEach(c => {{
        const el = document.getElementById('hypo-card-' + c);
        if (el) {{
          if (mode === 'all' || mode === c) {{
            el.classList.remove('hidden');
          }} else {{
            el.classList.add('hidden');
          }}
        }}
      }});
    }}

    // Tastatur-Esc schließt Modals
    window.addEventListener('keydown', (e) => {{
      if (e.key === 'Escape') {{
        closeDetailModal();
        closeAlertsModal();
        closeHypothesesModal();
      }}
    }});

    // ==========================================
    // ⏱️ Nächster Scan Countdown (Cron: 01:05, 05:05, 09:05, 13:05, 17:05, 21:05 UTC)
    // ==========================================
    function updateNextScanCountdown() {{
      const now = new Date();
      const nowUtc = now.getTime();
      const cronHours = [1, 5, 9, 13, 17, 21];
      let nextSlot = null;

      for (let dayOffset = 0; dayOffset <= 2; dayOffset++) {{
        for (const h of cronHours) {{
          const candidate = new Date();
          candidate.setUTCDate(candidate.getUTCDate() + dayOffset);
          candidate.setUTCHours(h, 5, 0, 0);
          if (candidate.getTime() > nowUtc) {{
            nextSlot = candidate;
            break;
          }}
        }}
        if (nextSlot) break;
      }}

      if (!nextSlot) return;

      const diff = Math.max(0, nextSlot.getTime() - nowUtc);
      const totalSec = Math.floor(diff / 1000);
      const hours = Math.floor(totalSec / 3600);
      const mins = Math.floor((totalSec % 3600) / 60);
      const secs = totalSec % 60;

      const pad = (n) => String(n).padStart(2, '0');
      const el = document.getElementById('next-scan-countdown');

      if (totalSec <= 0) {{
        if (el) el.innerText = 'Scan läuft... 🔄';
      }} else {{
        if (el) el.innerText = `${{pad(hours)}}h ${{pad(mins)}}m ${{pad(secs)}}s`;
      }}
    }}
    setInterval(updateNextScanCountdown, 1000);
    updateNextScanCountdown();

    // ==========================================
    // 🔄 Refresh-Funktion & Toast-Banner
    // ==========================================
    let isRefreshing = false;
    function showToast(msg) {{
      const banner = document.getElementById('toast-banner');
      const text = document.getElementById('toast-message');
      if (banner && text) {{
        text.innerText = msg;
        banner.classList.remove('translate-y-24', 'opacity-0');
        setTimeout(() => {{
          banner.classList.add('translate-y-24', 'opacity-0');
        }}, 3000);
      }}
    }}

    function triggerManualRefresh() {{
      if (isRefreshing) return;
      isRefreshing = true;

      const icon = document.getElementById('refresh-icon');
      const label = document.getElementById('refresh-label');
      if (icon) icon.classList.add('animate-spin');
      if (label) label.innerText = 'Lädt...';

      fetch('market_analysis_db.json?nocache=' + Date.now())
        .then(res => res.json())
        .then(newData => {{
          currentData = newData;
          updateStats();
          applyFilters();
          showToast('Dashboard erfolgreich aktualisiert!');
        }})
        .catch(err => {{
          console.warn('Live-Fetch nicht möglich, lade Seite neu...', err);
          window.location.reload();
        }})
        .finally(() => {{
          setTimeout(() => {{
            if (icon) icon.classList.remove('animate-spin');
            if (label) label.innerText = 'Refresh';
            isRefreshing = false;
          }}, 600);
        }});
    }}

    // ==========================================
    // 📱 Pull-down to Refresh (Touch / iOS)
    // ==========================================
    function setupPullToRefresh() {{
      let startY = 0;
      let currentY = 0;
      let isPulling = false;
      const threshold = 65;
      const indicator = document.getElementById('pull-refresh-indicator');
      const pullIcon = document.getElementById('pull-icon');
      const pullText = document.getElementById('pull-text');

      window.addEventListener('touchstart', (e) => {{
        if (window.scrollY === 0) {{
          startY = e.touches[0].clientY;
          isPulling = true;
        }} else {{
          isPulling = false;
        }}
      }}, {{ passive: true }});

      window.addEventListener('touchmove', (e) => {{
        if (!isPulling) return;
        currentY = e.touches[0].clientY;
        const pullDist = currentY - startY;

        if (pullDist > 0 && window.scrollY === 0) {{
          const damped = Math.min(pullDist * 0.45, 90);
          if (indicator) {{
            indicator.style.transform = `translateY(${{damped}}px)`;
          }}
          if (pullDist >= threshold) {{
            if (pullIcon) pullIcon.style.transform = 'rotate(180deg)';
            if (pullText) pullText.innerText = 'Loslassen zum Aktualisieren';
          }} else {{
            if (pullIcon) pullIcon.style.transform = 'rotate(0deg)';
            if (pullText) pullText.innerText = 'Nach unten ziehen...';
          }}
        }}
      }}, {{ passive: true }});

      window.addEventListener('touchend', () => {{
        if (!isPulling) return;
        isPulling = false;
        const pullDist = currentY - startY;

        if (pullDist >= threshold && window.scrollY === 0) {{
          if (pullText) pullText.innerText = 'Aktualisiere Daten...';
          if (pullIcon) pullIcon.classList.add('animate-spin');
          triggerManualRefresh();
          setTimeout(() => {{
            if (indicator) indicator.style.transform = 'translateY(-100%)';
            if (pullIcon) {{
              pullIcon.classList.remove('animate-spin');
              pullIcon.style.transform = 'rotate(0deg)';
            }}
          }}, 800);
        }} else {{
          if (indicator) indicator.style.transform = 'translateY(-100%)';
        }}
        startY = 0;
        currentY = 0;
      }});
    }}
    setupPullToRefresh();

    // Initial render
    updateStats();
    applyFilters();

    // Deep-Link aus Historie (?asset=SYMBOL oder ?symbol=SYMBOL)
    const urlParams = new URLSearchParams(window.location.search);
    const targetAsset = urlParams.get('asset') || urlParams.get('symbol');
    if (targetAsset) {{
      setTimeout(() => {{
        openDetailModal(targetAsset);
      }}, 350);
    }}
  </script>

  <!-- iOS Alerts Info Modal -->
  <div id="alerts-modal" class="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm hidden flex items-center justify-center p-4">
    <div class="max-w-lg w-full rounded-2xl bg-[#0d1322] border border-indigo-500/40 p-6 shadow-2xl relative text-slate-200">
      <div class="flex items-start justify-between pb-4 border-b border-slate-800">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-indigo-500/20 border border-indigo-500/40 flex items-center justify-center text-xl">
            🔔
          </div>
          <div>
            <h3 class="font-bold text-lg text-white">iOS Lockscreen Alerts</h3>
            <p class="text-xs text-slate-400">Push-Benachrichtigungen direkt auf dein iPhone</p>
          </div>
        </div>
        <button onclick="closeAlertsModal()" class="w-8 h-8 rounded-lg bg-slate-800 text-slate-400 hover:text-white flex items-center justify-center transition">✕</button>
      </div>

      <div class="mt-4 space-y-4 text-xs leading-relaxed">
        <p class="text-slate-300">
          Du kannst dir bei jedem automatischen 4h-Scan (und bei Top A+ Setups &ge; 90%) sofort eine echte iOS-Push-Mitteilung mit Ton und Sperrbildschirm-Vorschau auf dein iPhone senden lassen.
        </p>

        <div class="p-3.5 rounded-xl bg-slate-800/60 border border-slate-700/60 space-y-2">
          <span class="font-bold text-indigo-300 block text-sm">📲 In 3 Schritten auf dem iPhone einrichten (Kostenlos via ntfy):</span>
          <ol class="list-decimal list-inside space-y-1.5 text-slate-300">
            <li>Installiere die kostenlose App <strong>ntfy</strong> aus dem Apple App Store auf deinem iPhone.</li>
            <li>Öffne die App, tippe auf <strong>„+“</strong> und abonniere das Topic: <code class="px-1.5 py-0.5 rounded bg-slate-900 text-emerald-400 font-mono font-bold">bbbdc-trading-alerts</code></li>
            <li>Fertig! Der Raspberry Pi ist bereits mit diesem Topic verbunden und sendet dir bei jedem Scan einen Push-Report.</li>
          </ol>
        </div>

        <div class="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center gap-2.5">
          <span class="text-emerald-400 text-lg">💡</span>
          <span class="text-emerald-200 text-[11px]">Du erhältst alle 4 Stunden automatisch den Scan-Report und wirst sofort über A+ High-Conviction Setups informiert – inklusive Direktlink zum Dashboard!</span>
        </div>
      </div>

      <div class="mt-5 flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
        <button onclick="closeAlertsModal()" class="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs transition">
          Verstanden
        </button>
      </div>
    </div>
  </div>

  <!-- Setup Hypotheses Guide Modal -->
  <div id="hypotheses-modal" onclick="if(event.target === this) closeHypothesesModal()" class="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm hidden flex items-center justify-center p-3 sm:p-5">
    <div class="max-w-3xl w-full max-h-[92vh] overflow-y-auto rounded-2xl bg-[#0d1322] border border-indigo-500/40 p-5 sm:p-6 shadow-2xl relative text-slate-200 space-y-5">
      
      <!-- Modal Header -->
      <div class="flex items-start justify-between pb-4 border-b border-slate-800">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-indigo-500/20 border border-indigo-500/40 flex items-center justify-center text-xl shrink-0">
            💡
          </div>
          <div>
            <div class="flex items-center gap-2">
              <h3 class="font-bold text-lg text-white">Setup-Hypothesen & Trade-Plan Guide</h3>
              <span class="px-2 py-0.5 rounded-full text-[10px] font-mono bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">Strategy Rules</span>
            </div>
            <p class="text-xs text-slate-400 mt-0.5">Verstehe die institutionelle Logik hinter jedem Signal (SMC, Wyckoff VSA, RSI & Fibonacci)</p>
          </div>
        </div>
        <button onclick="closeHypothesesModal()" class="w-8 h-8 rounded-lg bg-slate-800 text-slate-400 hover:text-white flex items-center justify-center transition shrink-0">✕</button>
      </div>

      <!-- Quick Filter Switcher within Modal -->
      <div class="flex flex-wrap items-center gap-2">
        <button onclick="filterHypothesisModal('all')" id="hypo-pill-all" class="hypo-filter-pill px-3 py-1.5 rounded-lg text-xs font-semibold transition bg-indigo-600 text-white shadow-sm cursor-pointer">
          Alle 3 im Überblick
        </button>
        <button onclick="filterHypothesisModal('h1')" id="hypo-pill-h1" class="hypo-filter-pill px-3 py-1.5 rounded-lg text-xs font-semibold transition bg-slate-800 text-slate-300 hover:text-white cursor-pointer">
          🔄 Hypothese 1 (Reversal)
        </button>
        <button onclick="filterHypothesisModal('h2')" id="hypo-pill-h2" class="hypo-filter-pill px-3 py-1.5 rounded-lg text-xs font-semibold transition bg-slate-800 text-slate-300 hover:text-white cursor-pointer">
          📈 Hypothese 2 (Trendfolge)
        </button>
        <button onclick="filterHypothesisModal('h3')" id="hypo-pill-h3" class="hypo-filter-pill px-3 py-1.5 rounded-lg text-xs font-semibold transition bg-slate-800 text-slate-300 hover:text-white cursor-pointer">
          🎯 Hypothese 3 (Liquidity Trap)
        </button>
      </div>

      <!-- Cards Container -->
      <div class="space-y-4 text-xs leading-relaxed">
        
        <!-- Hypothese 1 Card -->
        <div id="hypo-card-h1" class="p-4 rounded-xl bg-slate-900/90 border border-emerald-500/40 space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
              <h4 class="font-bold text-sm text-white">Hypothese 1: SMC Golden Confluence Reversal</h4>
            </div>
            <div class="flex items-center gap-1.5 font-mono text-[10px]">
              <span class="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-semibold">Antizyklisch / Wende</span>
              <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">CRV: 3:1 bis 5:1</span>
            </div>
          </div>

          <p class="text-slate-300">
            <strong>Ziel:</strong> Einstieg direkt am institutionellen Wendepunkt einer überdehnten Bewegung – maximales Gewinnpotenzial bei minimalem Risiko.
          </p>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1">
            <div class="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
              <span class="text-emerald-300 font-bold block text-[11px]">📍 Chart-Kontext & Zonen:</span>
              <ul class="list-disc list-inside space-y-1 text-slate-300 text-[11px]">
                <li>Kurs läuft in offenes <strong>Fair Value Gap (FVG)</strong> oder unmitigierten <strong>Order Block</strong>.</li>
                <li>Sitzt exakt im <strong>Fibonacci Golden Pocket (0.618 – 0.65)</strong>.</li>
                <li>Überdehnung über das äußere <strong>degencoder-Kanalband</strong> (Oversold/Overbought).</li>
              </ul>
            </div>

            <div class="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
              <span class="text-emerald-300 font-bold block text-[11px]">⚡ Signal-Trigger & Bestätigung:</span>
              <ul class="list-disc list-inside space-y-1 text-slate-300 text-[11px]">
                <li><strong>Reguläre RSI-Divergenz:</strong> Kurs macht neues Extremum, RSI divergiert bereits (Gegenkraft formt sich).</li>
                <li><strong>VSA Wyckoff:</strong> Climax-Volumen gefolgt von <strong>Stopping Volume</strong> (Verkaufs-/Kaufdruck versiegt).</li>
                <li><strong>SL:</strong> Super eng direkt hinter der Wendezone / dem Docht.</li>
              </ul>
            </div>
          </div>

          <div class="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-[11px] flex items-center gap-2">
            <span>💡</span>
            <span><strong>Merksatz:</strong> <em>„Der Markt dreht hier um.“</em> (Perfekter Einstieg am Tief/Hoch, Maximum CRV).</span>
          </div>
        </div>

        <!-- Hypothese 2 Card -->
        <div id="hypo-card-h2" class="p-4 rounded-xl bg-slate-900/90 border border-indigo-500/40 space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <span class="w-2.5 h-2.5 rounded-full bg-indigo-400 animate-pulse"></span>
              <h4 class="font-bold text-sm text-white">Hypothese 2: Trend Continuation & Hidden Div</h4>
            </div>
            <div class="flex items-center gap-1.5 font-mono text-[10px]">
              <span class="px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/30 font-semibold">Prozyklisch / Trendfolge</span>
              <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">Winrate: &ge; 60%</span>
              <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">CRV: 2:1 bis 3.5:1</span>
            </div>
          </div>

          <p class="text-slate-300">
            <strong>Ziel:</strong> Hohe Trefferquote durch Einstieg in den intakten Haupttrend nach einem gesunden, temporären Rücksetzer (Dip).
          </p>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1">
            <div class="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
              <span class="text-indigo-300 font-bold block text-[11px]">📍 Chart-Kontext & Zonen:</span>
              <ul class="list-disc list-inside space-y-1 text-slate-300 text-[11px]">
                <li>Übergeordneter Trend (1D/8h) intakt (Kurs über/unter <strong>EMA 233</strong> & geneigter Kanal).</li>
                <li>Rücklauf (Pullback) in ein frisch entstandenes <strong>Fair Value Gap</strong> oder an die dynamischen Trendbänder.</li>
                <li>Kein Bruch der Marktstruktur, sondern gesunde Atempause.</li>
              </ul>
            </div>

            <div class="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
              <span class="text-indigo-300 font-bold block text-[11px]">⚡ Signal-Trigger & Bestätigung:</span>
              <ul class="list-disc list-inside space-y-1 text-slate-300 text-[11px]">
                <li><strong>Versteckte (Hidden) RSI-Divergenz:</strong> Kurs formt höheres Tief (Higher Low), RSI formt tieferes Tief (Lower Low = voller Momentum-Reset).</li>
                <li><strong>VSA Wyckoff:</strong> <strong>„No Supply“</strong> (Volumen trocknet beim Dip aus = kein institutioneller Verkaufsdruck).</li>
                <li><strong>SL:</strong> Knapp unter dem FVG / dem Korrekturtief.</li>
              </ul>
            </div>
          </div>

          <div class="p-2.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 text-[11px] flex items-center gap-2">
            <span>💡</span>
            <span><strong>Merksatz:</strong> <em>„Der Trend macht nur Pause und zieht gleich weiter.“</em> (Hohe Trefferquote, Dip kaufen).</span>
          </div>
        </div>

        <!-- Hypothese 3 Card -->
        <div id="hypo-card-h3" class="p-4 rounded-xl bg-slate-900/90 border border-amber-500/40 space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <span class="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
              <h4 class="font-bold text-sm text-white">Hypothese 3: Wyckoff Liquidity Hunt & Range Fakeout</h4>
            </div>
            <div class="flex items-center gap-1.5 font-mono text-[10px]">
              <span class="px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 font-semibold">Trap Trading / Fakeout</span>
              <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">CRV: 2.5:1 bis 4:1</span>
            </div>
          </div>

          <p class="text-slate-300">
            <strong>Ziel:</strong> Schnelle Gewinne durch Abfangen von institutionellen Stop-Runs (Spring / Upthrust) und gefangenen Ausbruchs-Tradern.
          </p>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1">
            <div class="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
              <span class="text-amber-300 font-bold block text-[11px]">📍 Chart-Kontext & Zonen:</span>
              <ul class="list-disc list-inside space-y-1 text-slate-300 text-[11px]">
                <li>Deutliche Range-Struktur oder markantes lokales Swing-High / Swing-Low (Key Liquidity Pool).</li>
                <li>Kurs bricht kurz über/unter die Begrenzung aus und überdehnt das Band.</li>
              </ul>
            </div>

            <div class="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
              <span class="text-amber-300 font-bold block text-[11px]">⚡ Signal-Trigger & Bestätigung:</span>
              <ul class="list-disc list-inside space-y-1 text-slate-300 text-[11px]">
                <li><strong>Spring / Upthrust:</strong> Schnelle Ablehnung (Rejection / Dochtbildung) und sofortige Rückkehr in die Range.</li>
                <li><strong>VSA Volume Spike:</strong> Riesiges Climax-Volumen am Ausbruch, das sofort verpufft (Liquidity Trap).</li>
                <li><strong>SL:</strong> Über dem Ausbruchs-Docht. <strong>TP:</strong> Gegenüberliegende Range-Grenze.</li>
              </ul>
            </div>
          </div>

          <div class="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-300 text-[11px] flex items-center gap-2">
            <span>💡</span>
            <span><strong>Merksatz:</strong> <em>„Gefangene Trader – Stops wurden geholt, jetzt folgt der Gegenschlag.“</em></span>
          </div>
        </div>

        <!-- Summary Table -->
        <div class="rounded-xl border border-slate-800 overflow-hidden">
          <table class="w-full text-left text-[11px]">
            <thead class="bg-slate-950 text-slate-400 font-mono text-[10px] uppercase">
              <tr>
                <th class="p-2.5">Hypothese</th>
                <th class="p-2.5">Handelsansatz</th>
                <th class="p-2.5">Kern-Trigger</th>
                <th class="p-2.5">CRV</th>
                <th class="p-2.5">Hauptstärke</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-800/60 font-mono text-slate-300">
              <tr class="hover:bg-slate-800/30">
                <td class="p-2.5 font-bold text-emerald-400">Hypothese 1</td>
                <td class="p-2.5">Reversal (Wende)</td>
                <td class="p-2.5">Golden Pocket + Reguläre RSI Div + Stopping Vol</td>
                <td class="p-2.5 text-white font-bold">3:1 – 5:1</td>
                <td class="p-2.5 text-slate-200">Maximales CRV, Reversal am Extrempunkt</td>
              </tr>
              <tr class="hover:bg-slate-800/30">
                <td class="p-2.5 font-bold text-indigo-400">Hypothese 2</td>
                <td class="p-2.5">Trendfolge (Pullback)</td>
                <td class="p-2.5">FVG Retest + Versteckte RSI Div + VSA No Supply</td>
                <td class="p-2.5 text-white font-bold">2:1 – 3.5:1</td>
                <td class="p-2.5 text-slate-200">Hohe Winrate (&ge;60%), Dip im Trend kaufen</td>
              </tr>
              <tr class="hover:bg-slate-800/30">
                <td class="p-2.5 font-bold text-amber-400">Hypothese 3</td>
                <td class="p-2.5">Range Fakeout / Trap</td>
                <td class="p-2.5">Spring / Upthrust an Range-Limit + Volume Climax</td>
                <td class="p-2.5 text-white font-bold">2.5:1 – 4:1</td>
                <td class="p-2.5 text-slate-200">Schnelle Gegenzüge nach Stop-Runs</td>
              </tr>
            </tbody>
          </table>
        </div>

      </div>

      <!-- Footer Actions -->
      <div class="flex items-center justify-between pt-3 border-t border-slate-800 text-xs">
        <span class="text-slate-500 font-mono text-[11px]">TradingView Super-Analyst Strategy Engine</span>
        <button onclick="closeHypothesesModal()" class="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition cursor-pointer">
          Verstanden
        </button>
      </div>

    </div>
  </div>
</body>
</html>
"""

# Schreibe in Workspace und optional in Antigravity Artifact
with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html_content)

print("Dashboard erfolgreich erstellt!")
print(f"-> Workspace: {OUT_HTML}")

# Speichere Artifact nur, wenn Antigravity-Artifact-Verzeichnis existiert
try:
    if ARTIFACT_DIR.parent.exists():
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUT_ARTIFACT, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"-> Artifact: {OUT_ARTIFACT}")
except Exception:
    pass

# Auch die separate Historie-Webseite aktualisieren
try:
    from build_history import generate_history_html
    generate_history_html()
except Exception as e:
    print(f"Hinweis: Historie-Seite konnte nicht aktualisiert werden ({e})")

