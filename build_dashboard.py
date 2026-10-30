#!/usr/bin/env python3
"""
Dashboard Generator: Erstellt ein interaktives, hochmodernes HTML-Dashboard
mit Tailwind CSS, Super-Navigation, Multi-Timeframe-Modal und robuster Datenanbindung.
"""

import json
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"
OUT_HTML = BASE_DIR / "dashboard" / "index.html"
ARTIFACT_DIR = Path("/Users/maximilianmayer/.gemini/antigravity/brain/eeb75350-6985-4121-862b-6a5bd07b0cf8")
OUT_ARTIFACT = ARTIFACT_DIR / "dashboard.html"

with open(DB_FILE, "r", encoding="utf-8") as f:
    db_data = json.load(f)

# Quota Tracker Status für den konfigurierten API-Key abfragen
try:
    from gemini_quota_tracker import get_quota_summary_for_dashboard
    quota_info = get_quota_summary_for_dashboard()
except Exception:
    quota_info = db_data.get("gemini_quota", {
        "api_key_masked": "AQ.Ab8...Ww",
        "model": "gemini-3.8-flash",
        "daily_limit": 20,
        "requests_used_today": 0,
        "requests_remaining": 20,
        "percent_used": 0.0,
        "tokens_used_today": 0,
        "status": "ACTIVE",
        "is_exhausted": False,
        "reset_countdown": "00:00 UTC",
        "last_error": None
    })

# Telegram Auth-Metadaten für Rollenbasierte Website-Freigabe
TELEGRAM_CONFIG = BASE_DIR / "telegram_config.json"
auth_config = {
    "admin_usernames": ["Bdc_Gumb_Drop", "bdc_gumb_drop"],
    "admin_chat_ids": ["15231751"],
    "authorized_users": {}
}
if TELEGRAM_CONFIG.exists():
    try:
        with open(TELEGRAM_CONFIG, "r", encoding="utf-8") as f:
            tcfg = json.load(f)
            auth_config["admin_usernames"] = tcfg.get("admin_usernames", auth_config["admin_usernames"])
            auth_config["admin_chat_ids"] = [str(x) for x in tcfg.get("admin_chat_ids", auth_config["admin_chat_ids"])]
            for uname, udata in tcfg.get("authorized_users", {}).items():
                if isinstance(udata, dict):
                    auth_config["authorized_users"][uname] = {
                        "role": udata.get("role", "trader"),
                        "chat_id": str(udata.get("chat_id", ""))
                    }
    except Exception:
        pass

db_data["auth_config"] = auth_config
db_data["gemini_quota"] = quota_info

# Vorab frische Live-Preise von TradingView ziehen & Cache synchronisieren
try:
    from tv_live_quotes import fetch_tradingview_live_quotes, update_ohlcv_cache_with_live_quotes, SYMBOL_ALIASES
    all_syms = [a["symbol"] for a in db_data.get("assets", []) if "symbol" in a]
    portfolio_syms = [t["symbol"] for t in db_data.get("portfolio", {}).get("active_trades", [])]
    user_syms = [p["symbol"] for p in db_data.get("user_positions", [])]
    all_q_syms = list(set(all_syms + portfolio_syms + user_syms))
    live_quotes = fetch_tradingview_live_quotes(all_q_syms)
    if live_quotes:
        update_ohlcv_cache_with_live_quotes(live_quotes)
        for a in db_data.get("assets", []):
            s = a.get("symbol")
            lq = live_quotes.get(s) or live_quotes.get(SYMBOL_ALIASES.get(s, ""))
            if lq:
                a["price"] = lq["price"]
                a["change_pct"] = lq["change_pct"]
                a["last_price_update"] = lq["updated_at"]
                a["last_price_update_str"] = lq["updated_at_str"]
        db_data["last_quotes_update"] = datetime.now(timezone.utc).isoformat()
except Exception as lqe:
    print(f"Warnung beim Vorab-Livequote-Sync in build_dashboard: {lqe}")

# Synchronisiere aktuelle Nutzer-Positionen & Portfolio mit Live-Preisen & TV-Daten
try:
    from portfolio_engine import evaluate_user_positions, update_autonomous_portfolio
    analyzed_assets = db_data.get("assets", [])
    if analyzed_assets:
        user_pos_data = evaluate_user_positions(analyzed_assets)
        db_data["user_positions"] = user_pos_data.get("positions", [])
        port_data, mem_data = update_autonomous_portfolio(analyzed_assets)
        db_data["portfolio"] = port_data
        db_data["trade_memory"] = mem_data
except Exception as pe:
    print(f"Warnung beim Synchronisieren des Portfolios/Nutzer-Positionen: {pe}")

json_str = json.dumps(db_data, ensure_ascii=False)

try:
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db_data, f, ensure_ascii=False, indent=2)
except Exception as e:
    print(f"Warnung beim Speichern von DB_FILE: {e}")

total_keys_count = quota_info.get("total_keys_count", 2)
active_keys_count = quota_info.get("active_keys_count", 1)
active_key_masked = quota_info.get("active_key_masked", "AQ.Ab8...zg")

last_quotes_iso = db_data.get("last_quotes_update")
if last_quotes_iso:
    try:
        import zoneinfo
        dt_q = datetime.fromisoformat(last_quotes_iso)
        dt_q_berlin = dt_q.astimezone(zoneinfo.ZoneInfo("Europe/Berlin"))
        last_quotes_update_display = dt_q_berlin.strftime("%H:%M CET")
    except Exception:
        last_quotes_update_display = "Live"
else:
    last_quotes_update_display = "Live"

engine_display = f"Gemini 3.8 Flash · {total_keys_count}x Key Pool"

quota_used = quota_info.get("requests_used_today", 0)
quota_limit = quota_info.get("daily_limit", 40)
quota_pct = quota_info.get("percent_used", 0.0)
quota_remaining = quota_info.get("requests_remaining", 0)
quota_countdown = quota_info.get("reset_countdown", "in wenigen Stunden")
quota_exhausted = quota_info.get("is_exhausted", False)
quota_tokens = quota_info.get("tokens_used_today", 0)

if quota_exhausted:
    quota_badge_class = "bg-rose-500/15 text-rose-300 border border-rose-500/30 hover:bg-rose-500/25"
    quota_num_class = "text-rose-200"
    quota_status_text = f"Reset {quota_countdown}"
    quota_bar_color = "bg-rose-500"
    engine_dot_class = "bg-rose-400"
else:
    quota_badge_class = "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25"
    quota_num_class = "text-emerald-200"
    quota_status_text = f"{quota_remaining} frei ({active_keys_count}/{total_keys_count} Keys)"
    quota_bar_color = "bg-emerald-500"
    engine_dot_class = "bg-emerald-400 animate-pulse"

keys_detail = quota_info.get("keys_detail", [])
keys_cards_html = ""
for kd in keys_detail:
    k_is_exh = kd.get("is_exhausted", False)
    k_badge = "bg-rose-500/20 text-rose-300 border border-rose-500/40" if k_is_exh else "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
    k_dot = "bg-rose-400" if k_is_exh else "bg-emerald-400 animate-pulse"
    k_bar = "bg-rose-500" if k_is_exh else "bg-emerald-500"
    k_name = kd.get("name", "Key")
    k_masked = kd.get("masked", "AQ.***")
    k_used = kd.get("requests_used", 0)
    k_lim = kd.get("daily_limit", 20)
    k_pct = kd.get("percent_used", 0.0)
    k_rem = kd.get("requests_remaining", 0)
    k_reset = kd.get("reset_countdown", "00:00 UTC")
    k_status_label = "Erschöpft" if k_is_exh else f"Aktiv ({k_rem} frei)"

    keys_cards_html += f"""
        <div class="p-3 rounded-xl bg-slate-900/90 border border-slate-800/90 space-y-2">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full {k_dot}"></span>
              <span class="font-bold text-white text-xs">{k_name}</span>
              <span class="font-mono text-[10px] text-slate-400">({k_masked})</span>
            </div>
            <span class="px-2 py-0.5 rounded text-[10px] font-bold font-mono {k_badge}">{k_status_label}</span>
          </div>
          <div class="space-y-1">
            <div class="flex items-center justify-between text-[11px]">
              <span class="text-slate-400">Verbrauch:</span>
              <span class="font-mono font-bold text-slate-200">{k_used} / {k_lim} ({k_pct}%)</span>
            </div>
            <div class="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
              <div class="h-1.5 rounded-full {k_bar}" style="width: {min(100.0, k_pct)}%"></div>
            </div>
          </div>
          <div class="flex items-center justify-between text-[10px] text-slate-500 font-mono">
            <span>Verbleibend: {k_rem} Anfragen</span>
            <span>Reset: {k_reset}</span>
          </div>
        </div>
    """

# Health Check & Routing Status für Admin-Bereich
health_info = quota_info.get("health_check", {})
health_is_ok = health_info.get("is_healthy", False)
health_badge_class = "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40" if health_is_ok else "bg-amber-500/20 text-amber-300 border border-amber-500/40"
health_badge_text = "🟢 HEALTH-CHECK: FREE POOL BEREIT" if health_is_ok else "🛡️ PRO-ABO GUARD AKTIV (503 FALLBACK)"
health_active_tier = health_info.get("active_tier", "Google Pro-Abo CLI (gemini-3.8-flash-low)")
health_msg = health_info.get("message", "Vorab-Healthcheck vor jedem Scan aktiv")
health_dot = "bg-emerald-400 animate-pulse" if health_is_ok else "bg-amber-400 animate-pulse"

routing_health_card_html = f"""
      <!-- Card Health & Routing: Übersicht Kaskade & Vorab-Check -->
      <section class="rounded-2xl bg-gradient-to-br from-slate-900/95 via-sky-950/20 to-slate-900 border border-sky-500/40 p-5 shadow-xl space-y-4">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-3 border-b border-slate-800">
          <div class="flex items-center gap-2.5">
            <span class="text-2xl">🛡️</span>
            <div>
              <div class="flex items-center gap-2">
                <h3 class="font-bold text-white text-base">KI-Routing & Vorab-Healthcheck Status</h3>
                <span class="px-2 py-0.5 rounded text-[10px] font-bold font-mono {health_badge_class}">{health_badge_text}</span>
              </div>
              <p class="text-xs text-slate-400">Automatische Kaskade: Free Keys sparen das Pro-Budget &bull; Pro-Abo sichert 100% Ausfallsicherheit</p>
            </div>
          </div>
          <span class="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold bg-sky-500/20 text-sky-300 border border-sky-500/30 self-start sm:self-auto">
            Aktive Engine: {health_active_tier}
          </span>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
          <div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
            <span class="text-[10px] text-slate-400 block uppercase">1. Primär (Stufe 1A)</span>
            <span class="font-bold text-base text-emerald-400">Free Multi-Key Pool</span>
            <span class="block text-[10px] text-slate-400 mt-0.5">4x Keys &bull; 80 Requests/Tag frei</span>
          </div>
          <div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
            <span class="text-[10px] text-slate-400 block uppercase">2. Ausfallsicherung (Stufe 1B)</span>
            <span class="font-bold text-base text-indigo-300">Google Pro-Abo (CLI)</span>
            <span class="block text-[10px] text-slate-400 mt-0.5">50 Requests Puffer &bull; High-Speed Guard</span>
          </div>
          <div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
            <span class="text-[10px] text-slate-400 block uppercase">Vorab-Healthcheck</span>
            <span class="font-bold text-base text-sky-300">Aktiv vor jedem Scan</span>
            <span class="block text-[10px] text-slate-400 mt-0.5">Automatischer Micro-Ping</span>
          </div>
        </div>

        <div class="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 text-xs text-slate-300 flex items-center justify-between">
          <span class="flex items-center gap-2">
            <span class="w-2 h-2 rounded-full {health_dot}"></span>
            <span><b>Health-Check Diagnose:</b> {health_msg}</span>
          </span>
          <span class="text-[10px] text-slate-500 font-mono">Dynamischer Schutz</span>
        </div>
      </section>
"""

# Pro-Abo Quota Informationen für Admin-Bereich
pro_info = quota_info.get("pro_subscription", {})
pro_enabled = pro_info.get("enabled", True)
pro_model = pro_info.get("model", "gemini-3.8-flash-high")
pro_budget = pro_info.get("daily_budget", 50)
pro_used = pro_info.get("requests_used", 0)
pro_rem = pro_info.get("requests_remaining", 50)
pro_pct = pro_info.get("percent_used", 0.0)
pro_status = pro_info.get("status", "ACTIVE")
pro_last_used = pro_info.get("last_used")
if pro_last_used:
    try:
        dt = datetime.fromisoformat(pro_last_used)
        pro_last_used_str = dt.strftime("%H:%M:%S UTC")
    except Exception:
        pro_last_used_str = str(pro_last_used)
else:
    pro_last_used_str = "Noch keine Anfragen heute"

pro_badge = "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40" if pro_status == "ACTIVE" else "bg-amber-500/20 text-amber-300 border border-amber-500/40"
pro_bar = "bg-indigo-500" if pro_status == "ACTIVE" else "bg-amber-500"

pro_card_html = f"""
      <!-- Card Pro-Abo: Google Pro Subscription Status -->
      <section class="rounded-2xl bg-gradient-to-br from-slate-900/95 via-indigo-950/30 to-slate-900 border border-indigo-500/40 p-5 shadow-xl space-y-4">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-3 border-b border-slate-800">
          <div class="flex items-center gap-2.5">
            <span class="text-2xl">💎</span>
            <div>
              <div class="flex items-center gap-2">
                <h3 class="font-bold text-white text-base">Google Pro-Abo (CLI Integration)</h3>
                <span class="px-2 py-0.5 rounded text-[10px] font-bold font-mono {pro_badge}">STUFE 1B: AUSFALLSICHERUNG (FAILOVER GUARD)</span>
              </div>
              <p class="text-xs text-slate-400">Automatische Schutzschaltung: Übernimmt nahtlos bei 503-Überlastung des Free Pools &bull; Geschützt durch Smart Funnel</p>
            </div>
          </div>
          <span class="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 self-start sm:self-auto">
            {pro_model}
          </span>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs font-mono">
          <div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
            <span class="text-[10px] text-slate-400 block uppercase">Tages-Verbrauch</span>
            <span class="font-bold text-base text-indigo-300">{pro_used} / {pro_budget} Requests</span>
            <span class="block text-[10px] text-slate-500 mt-0.5">{pro_pct}% des Tages-Puffers</span>
          </div>
          <div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
            <span class="text-[10px] text-slate-400 block uppercase">Verbleibender Puffer</span>
            <span class="font-bold text-base text-emerald-400">{pro_rem} Requests frei</span>
            <span class="block text-[10px] text-slate-500 mt-0.5">Sicherheits-Limit für agy</span>
          </div>
          <div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
            <span class="text-[10px] text-slate-400 block uppercase">Smart Funnel</span>
            <span class="font-bold text-base text-amber-300">Aktiv (Max. 10)</span>
            <span class="block text-[10px] text-slate-500 mt-0.5">Nur High-Conviction Setups</span>
          </div>
          <div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
            <span class="text-[10px] text-slate-400 block uppercase">Zuletzt genutzt</span>
            <span class="font-bold text-base text-slate-200">{pro_last_used_str}</span>
            <span class="block text-[10px] text-slate-500 mt-0.5">Reset um 00:00 UTC</span>
          </div>
        </div>

        <div class="space-y-1.5">
          <div class="flex items-center justify-between text-[11px] font-mono">
            <span class="text-slate-400">Tages-Budget Auslastung ({pro_used} von max. {pro_budget} Requests):</span>
            <span class="font-bold text-indigo-300">{pro_pct}%</span>
          </div>
          <div class="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
            <div class="h-2 rounded-full {pro_bar}" style="width: {min(100.0, pro_pct)}%"></div>
          </div>
        </div>

        <div class="p-3 rounded-xl bg-indigo-950/30 border border-indigo-500/20 text-xs text-slate-300 flex items-start gap-2.5">
          <span class="text-sm">🛡️</span>
          <div class="leading-relaxed text-[11px]">
            <strong class="text-indigo-300">Wochenlimit-Schonung für agy aktiv:</strong>
            Die KI analysiert vorselektiert nur Werte mit mathematischem Confluence-Score &ge; 65%, Golden Pocket oder aktiven Divergenzen. 
            Sollte das Tages-Sicherheitsbudget von {pro_budget} Anfragen erreicht werden, schaltet das System automatisch und unterbrechungsfrei auf Stufe 2 (Multi-Key Pool) um.
          </div>
        </div>
      </section>
"""

def get_asset_currency(a):
    if isinstance(a, dict) and a.get("currency"):
        return a.get("currency")
    sym = (a.get("symbol") or "").upper() if isinstance(a, dict) else ""
    cat = (a.get("category") or "").upper() if isinstance(a, dict) else ""
    wls = a.get("watchlists") or [] if isinstance(a, dict) else []
    if sym.startswith(("TRADEGATE:", "XETR:", "FWB:")) or "Tradegate Werte" in wls or "TRADEGATE" in cat or "DEUTSCHE AKTIEN" in cat or "DAX" in sym:
        return "EUR"
    return "USD"

def get_asset_currency_symbol(a):
    return "€" if get_asset_currency(a) == "EUR" else "$"

# Top Longs & Shorts für Tab 2 (Top-Setups)
def render_top_picks_html(candidates, sig_type="LONG"):
    if not candidates:
        return '<p class="text-xs text-slate-500 italic p-3 text-center">Aktuell keine Setups in dieser Kategorie.</p>'
    out = ""
    for c in candidates:
        badge_border = "border-emerald-500/30" if sig_type == "LONG" else "border-rose-500/30"
        score_color = "text-emerald-400" if sig_type == "LONG" else "text-rose-400"
        sym = c.get("symbol", "")
        name = c.get("name", sym)
        score = c.get("score", 0)
        setup = c.get("setup_name", "Setup")
        price = c.get("price", 0)
        curr_sym = get_asset_currency_symbol(c)
        entry_val = c.get("entry_range", "-")
        if isinstance(entry_val, (list, tuple)) and len(entry_val) == 2:
            entry = f"{entry_val[0]:,.2f} - {entry_val[1]:,.2f} {curr_sym}"
        else:
            entry = f"{entry_val}"
        sl = f"{c.get('stop_loss', '-'):,.2f} {curr_sym}" if isinstance(c.get('stop_loss'), (int, float)) else str(c.get('stop_loss', '-'))
        tp2 = f"{c.get('take_profit_2', '-'):,.2f} {curr_sym}" if isinstance(c.get('take_profit_2'), (int, float)) else str(c.get('take_profit_2', '-'))
        crv = c.get("crv", "-")

        out += f"""
        <div class="p-3.5 rounded-xl bg-slate-950/70 border {badge_border} hover:border-slate-600 transition flex flex-col gap-2">
          <div class="flex items-center justify-between">
            <div class="min-w-0">
              <span class="font-bold text-white text-xs sm:text-sm truncate block">{name}</span>
              <span class="font-mono text-[10px] text-slate-400">{sym}</span>
            </div>
            <div class="text-right shrink-0">
              <span class="font-mono font-bold text-xs {score_color}">{score}% Score</span>
              <span class="block text-[10px] font-mono text-slate-400">{price:,.2f} {curr_sym}</span>
            </div>
          </div>
          <div class="grid grid-cols-3 gap-1.5 text-[10px] font-mono bg-slate-900/60 p-2 rounded-lg border border-slate-800">
            <div><span class="text-slate-500 block">Entry:</span><span class="text-slate-200 font-semibold truncate block">{entry}</span></div>
            <div><span class="text-slate-500 block">SL:</span><span class="text-rose-400 font-semibold truncate block">{sl}</span></div>
            <div><span class="text-slate-500 block">TP2 / CRV:</span><span class="text-cyan-400 font-semibold truncate block">{tp2} ({crv})</span></div>
          </div>
          <div class="flex items-center justify-between pt-1 border-t border-slate-800/60">
            <span class="text-[10px] text-slate-400 truncate max-w-[220px]">{setup}</span>
            <button onclick="openDetailModal('{sym}')" class="text-[11px] font-bold text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition cursor-pointer">
              Multi-Timeframe Details →
            </button>
          </div>
        </div>
        """
    return out

raw_assets = db_data.get("assets", [])
top_long_candidates = sorted([a for a in raw_assets if a.get("signal") == "LONG"], key=lambda x: x.get("score", 0), reverse=True)[:3]
top_short_candidates = sorted([a for a in raw_assets if a.get("signal") == "SHORT"], key=lambda x: x.get("score", 0), reverse=True)[:3]
top_longs_cards_html = render_top_picks_html(top_long_candidates, "LONG")
top_shorts_cards_html = render_top_picks_html(top_short_candidates, "SHORT")

# TradingView Watchlists aggregieren und Filter-Pills erstellen
wl_counts = {}
for a in raw_assets:
    for w in a.get("watchlists", []):
        wl_counts[w] = wl_counts.get(w, 0) + 1

preferred_order = ["Tradegate Werte", "Aktien", "Crypto", "Commodities", "Devisen", "Watchlist"]
ordered_wls = [w for w in preferred_order if w in wl_counts]
for w in sorted(wl_counts.keys()):
    if w not in ordered_wls:
        ordered_wls.append(w)

def get_wl_icon(w):
    if "Tradegate" in w:
        return "🏛️ "
    elif "Aktien" in w:
        return "📈 "
    elif "Crypto" in w:
        return "🪙 "
    elif "Commodities" in w or "Rohstoffe" in w:
        return "🛢️ "
    elif "Devisen" in w:
        return "💱 "
    return "📋 "

tab2_watchlist_pills_html = f"""
  <button onclick="setWatchlistFilter('ALL')" id="tab2-wl-ALL" class="tab2-wl-btn px-3 py-1.5 rounded-lg text-xs font-semibold transition bg-indigo-600 text-white cursor-pointer shadow-sm shadow-indigo-500/20">
    Alle Listen ({len(raw_assets)})
  </button>
"""
for w in ordered_wls:
    cnt = wl_counts[w]
    safe_id = w.replace(" ", "_").replace("/", "_")
    icon = get_wl_icon(w)
    tab2_watchlist_pills_html += f"""
  <button onclick="setWatchlistFilter('{w}')" id="tab2-wl-{safe_id}" class="tab2-wl-btn px-3 py-1.5 rounded-lg text-xs font-semibold transition bg-slate-900 border border-slate-800 text-slate-300 hover:text-white hover:bg-slate-800 cursor-pointer">
    {icon}{w} ({cnt})
  </button>
"""

scanner_watchlist_pills_html = f"""
  <button onclick="setWatchlistFilter('ALL')" id="filter-wl-ALL" class="filter-wl-btn px-2.5 py-1 rounded-md transition bg-indigo-600 text-white font-medium cursor-pointer shadow-sm shadow-indigo-500/20">
    Alle ({len(raw_assets)})
  </button>
"""
for w in ordered_wls:
    cnt = wl_counts[w]
    safe_id = w.replace(" ", "_").replace("/", "_")
    icon = get_wl_icon(w)
    scanner_watchlist_pills_html += f"""
  <button onclick="setWatchlistFilter('{w}')" id="filter-wl-{safe_id}" class="filter-wl-btn px-2.5 py-1 rounded-md transition text-slate-400 hover:text-white hover:bg-slate-800 font-medium cursor-pointer">
    {icon}{w} ({cnt})
  </button>
"""


def render_hero_cards_html(raw_assets):
    def is_crypto_asset(a):
        sym = a.get("symbol", "").upper()
        cat = (a.get("category") or "").upper()
        atype = (a.get("asset_type") or "").upper()
        if atype == "CRYPTO" or "CRYPTO" in cat or "KRYPTO" in cat:
            return True
        if sym.startswith(("BINANCE:", "COINBASE:", "KRAKEN:", "BYBIT:", "CRYPTOCAP:")):
            return True
        if any(coin in sym for coin in ["BTC", "ETH", "SOL", "AVAX", "DOT", "BCH", "CRV", "AAVE", "KSM", "GMX", "ETHFI"]):
            return True
        return False

    def is_tradable_crypto(a):
        sym = a.get("symbol", "").upper()
        if "CRYPTOCAP:" in sym or sym in ("TOTAL", "BTC.D"):
            return False
        return is_crypto_asset(a)

    # 1. Top Opportunity Card (Aktien & Traditionelle Märkte)
    trad_assets = [a for a in raw_assets if not is_crypto_asset(a)]
    trad_active = [a for a in trad_assets if a.get("signal") in ("LONG", "SHORT")]
    if trad_active:
        top_pick = sorted(trad_active, key=lambda x: (x.get("score", 0), x.get("crv", 0)), reverse=True)[0]
    elif trad_assets:
        top_pick = sorted(trad_assets, key=lambda x: x.get("score", 0), reverse=True)[0]
    else:
        top_pick = None

    # 2. Top Crypto Opportunity Card (Dynamisch nach bestem Krypto-Setup)
    crypto_assets = [a for a in raw_assets if is_tradable_crypto(a)]
    crypto_active = [a for a in crypto_assets if a.get("signal") in ("LONG", "SHORT")]
    if crypto_active:
        crypto_pick = sorted(crypto_active, key=lambda x: (x.get("score", 0), x.get("crv", 0)), reverse=True)[0]
    elif crypto_assets:
        crypto_pick = sorted(crypto_assets, key=lambda x: x.get("score", 0), reverse=True)[0]
    else:
        crypto_pick = None

    # Top Pick HTML rendern (Aktien / Traditionell)
    if top_pick:
        tp_sym = top_pick.get("symbol", "")
        tp_name = top_pick.get("name", tp_sym)
        tp_cat = top_pick.get("category", "Aktien")
        tp_price = top_pick.get("price", 0.0)
        tp_score = top_pick.get("score", 50)
        tp_sig = top_pick.get("signal", "NEUTRAL")
        tp_setup = top_pick.get("setup_name", "Setup Confluence")
        tp_crv = top_pick.get("crv", 2.5)
        tp_entry = top_pick.get("entry_range", [tp_price, tp_price])
        tp_sl = top_pick.get("stop_loss", tp_price * 0.95)
        tp_tp2 = top_pick.get("take_profit_2", tp_price * 1.05)
        tp_note = top_pick.get("analyst_note") or f"{tp_sig}-Setup mit {tp_score}% Confluence. Risikomanagement und Key-Level strikt beachten."

        is_long = (tp_sig == "LONG")
        is_short = (tp_sig == "SHORT")

        tp_badge_bg = "bg-emerald-500 text-slate-950" if is_long else ("bg-rose-500 text-white" if is_short else "bg-slate-700 text-white")
        tp_glow = "glow-emerald border-emerald-500/30" if is_long else ("glow-rose border-rose-500/30" if is_short else "border-slate-700")
        tp_score_color = "text-emerald-400" if is_long else ("text-rose-400" if is_short else "text-slate-300")
        tp_price_color = "text-emerald-400" if is_long else ("text-rose-400" if is_short else "text-white")
        tp_curr_sym = get_asset_currency_symbol(top_pick)
        tp_curr_code = get_asset_currency(top_pick)
        tp_entry_str = f"{tp_entry[0]:,.2f} - {tp_entry[1]:,.2f} {tp_curr_sym}" if isinstance(tp_entry, (list, tuple)) and len(tp_entry) == 2 else f"{tp_price:,.2f} {tp_curr_sym}"
        tp_sl_str = f"{tp_sl:,.2f} {tp_curr_sym}"
        tp_tp_str = f"{tp_tp2:,.2f} {tp_curr_sym} ({tp_crv} CRV)"
        tp_sub_badge = f"{tp_score}% Score · {tp_sig}"
        tp_detail_link_color = "text-emerald-400 hover:text-emerald-300" if is_long else "text-rose-400 hover:text-rose-300"

        top_pick_html = f"""
        <!-- Top Pick Aktien/Traditionell: {tp_name} ({tp_sym}) -->
        <div class="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900/90 via-[#0d1322] to-slate-900 border {tp_glow} p-5">
          <div class="absolute -right-12 -top-12 w-48 h-48 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none"></div>
          <div class="flex items-start justify-between">
            <div class="flex items-center gap-3">
              <span class="px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wider {tp_badge_bg}">
                Top Opportunity · Aktien
              </span>
              <span class="text-xs font-mono {tp_score_color} font-semibold">{tp_sub_badge}</span>
            </div>
            <span class="font-mono text-xs text-slate-400">{tp_sym}</span>
          </div>

          <div class="mt-3 flex items-baseline justify-between">
            <div>
              <h3 class="text-2xl font-bold text-white tracking-tight">{tp_name}</h3>
              <p class="text-xs text-slate-400">{tp_cat}</p>
            </div>
            <div class="text-right">
              <span class="font-mono text-2xl font-extrabold {tp_price_color}">{tp_price:,.2f} {tp_curr_code}</span>
              <span class="block text-xs font-mono text-slate-400">Live aus Markt-Scan</span>
            </div>
          </div>

          <div class="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
            <div class="p-2 rounded-lg bg-slate-800/60 border border-slate-700/60">
              <span class="text-slate-400 block text-[11px]">Setup</span>
              <span class="{tp_score_color} font-semibold truncate block">{tp_setup}</span>
            </div>
            <div class="p-2 rounded-lg bg-slate-800/60 border border-slate-700/60">
              <span class="text-slate-400 block text-[11px]">Entry Zone</span>
              <span class="text-white font-semibold">{tp_entry_str}</span>
            </div>
            <div class="p-2 rounded-lg bg-slate-800/60 border border-slate-700/60">
              <span class="text-slate-400 block text-[11px]">Stop-Loss</span>
              <span class="text-rose-400 font-semibold">{tp_sl_str}</span>
            </div>
            <div class="p-2 rounded-lg bg-slate-800/60 border border-slate-700/60">
              <span class="text-slate-400 block text-[11px]">Take-Profit 2</span>
              <span class="text-cyan-400 font-semibold">{tp_tp_str}</span>
            </div>
          </div>

          <p class="mt-3 text-xs text-slate-300 leading-relaxed">
            <strong>Super-Analyst Rationale:</strong> {tp_note}
          </p>

          <div class="mt-4 flex items-center justify-between pt-3 border-t border-slate-800/80">
            <button onclick="openDetailModal('{tp_sym}')" class="text-xs font-semibold {tp_detail_link_color} flex items-center gap-1 transition cursor-pointer">
              Multi-Timeframe Details →
            </button>
            <a href="https://www.tradingview.com/chart/?symbol={tp_sym}" target="_blank" class="text-xs text-slate-400 hover:text-white transition flex items-center gap-1">
              TradingView Chart ↗
            </a>
          </div>
        </div>
        """
    else:
        top_pick_html = '<div class="p-5 rounded-2xl bg-slate-900 border border-slate-800 text-slate-400">Keine Top Opportunity aktiv.</div>'

    # Top Crypto Opportunity HTML rendern
    if crypto_pick:
        c_sym = crypto_pick.get("symbol", "")
        c_name = crypto_pick.get("name", c_sym)
        c_cat = crypto_pick.get("category", "Crypto")
        c_price = crypto_pick.get("price", 0.0)
        c_score = crypto_pick.get("score", 50)
        c_sig = crypto_pick.get("signal", "NEUTRAL")
        c_setup = crypto_pick.get("setup_name", "Krypto Setup")
        c_crv = crypto_pick.get("crv", 2.5)
        c_entry = crypto_pick.get("entry_range", [c_price, c_price])
        c_sl = crypto_pick.get("stop_loss", c_price * 0.95)
        c_tp2 = crypto_pick.get("take_profit_2", c_price * 1.05)
        c_note = crypto_pick.get("analyst_note") or f"{c_sig}-Krypto-Setup mit {c_score}% Confluence. 24/7 Marktvolatilität beachten."

        c_is_long = (c_sig == "LONG")
        c_is_short = (c_sig == "SHORT")

        c_badge_bg = "bg-emerald-500 text-slate-950" if c_is_long else ("bg-rose-500 text-white" if c_is_short else "bg-indigo-600 text-white")
        c_glow = "glow-emerald border-emerald-500/30" if c_is_long else ("glow-rose border-rose-500/30" if c_is_short else "border-indigo-500/30")
        c_score_color = "text-emerald-400" if c_is_long else ("text-rose-400" if c_is_short else "text-indigo-300")
        c_price_color = "text-emerald-400" if c_is_long else ("text-rose-400" if c_is_short else "text-white")
        c_entry_str = f"{c_entry[0]:,.2f} - {c_entry[1]:,.2f} $" if isinstance(c_entry, (list, tuple)) and len(c_entry) == 2 else f"{c_price:,.2f} $"
        c_sl_str = f"{c_sl:,.2f} $"
        c_tp_str = f"{c_tp2:,.2f} $ ({c_crv} CRV)"
        c_sub_badge = f"{c_score}% Score · {c_sig}"
        c_detail_link_color = "text-emerald-400 hover:text-emerald-300" if c_is_long else ("text-rose-400 hover:text-rose-300" if c_is_short else "text-indigo-400 hover:text-indigo-300")

        d_1d = crypto_pick.get("timeframes", {}).get("1D") or {}
        c_trend = d_1d.get("trend", "BULLISH")
        c_trend_badge = f"{c_trend} (1D)"

        crypto_card_html = f"""
        <!-- Top Crypto Opportunity: {c_name} ({c_sym}) -->
        <div class="relative overflow-hidden rounded-2xl bg-gradient-to-br from-indigo-950/40 via-slate-900/90 to-slate-900 border {c_glow} p-5">
          <div class="absolute -right-12 -top-12 w-48 h-48 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none"></div>
          <div class="flex items-start justify-between">
            <div class="flex items-center gap-3">
              <span class="px-2.5 py-1 rounded-md text-xs font-bold uppercase tracking-wider {c_badge_bg}">
                Top Opportunity · Krypto
              </span>
              <span class="text-xs font-mono {c_score_color} font-semibold">{c_sub_badge}</span>
            </div>
            <span class="font-mono text-xs text-slate-400">{c_sym}</span>
          </div>

          <div class="mt-3 flex items-baseline justify-between">
            <div>
              <h3 class="text-2xl font-bold text-white tracking-tight">{c_name}</h3>
              <p class="text-xs text-slate-400">{c_cat} · 24/7 Krypto</p>
            </div>
            <div class="text-right">
              <span class="font-mono text-2xl font-extrabold {c_price_color}">{c_price:,.2f} USD</span>
              <span class="block text-xs font-mono text-slate-400">{c_trend_badge}</span>
            </div>
          </div>

          <div class="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
            <div class="p-2 rounded-lg bg-slate-800/60 border border-slate-700/60">
              <span class="text-slate-400 block text-[11px]">Setup</span>
              <span class="{c_score_color} font-semibold truncate block">{c_setup}</span>
            </div>
            <div class="p-2 rounded-lg bg-slate-800/60 border border-slate-700/60">
              <span class="text-slate-400 block text-[11px]">Entry / Trigger</span>
              <span class="text-white font-semibold">{c_entry_str}</span>
            </div>
            <div class="p-2 rounded-lg bg-slate-800/60 border border-slate-700/60">
              <span class="text-slate-400 block text-[11px]">Stop-Loss</span>
              <span class="text-rose-400 font-semibold">{c_sl_str}</span>
            </div>
            <div class="p-2 rounded-lg bg-slate-800/60 border border-slate-700/60">
              <span class="text-slate-400 block text-[11px]">Take-Profit 2</span>
              <span class="text-cyan-400 font-semibold">{c_tp_str}</span>
            </div>
          </div>

          <p class="mt-3 text-xs text-slate-300 leading-relaxed">
            <strong>Super-Analyst Rationale:</strong> {c_note}
          </p>

          <div class="mt-4 flex items-center justify-between pt-3 border-t border-slate-800/80">
            <button onclick="openDetailModal('{c_sym}')" class="text-xs font-semibold {c_detail_link_color} flex items-center gap-1 transition cursor-pointer">
              Multi-Timeframe Details →
            </button>
            <a href="https://www.tradingview.com/chart/?symbol={c_sym}" target="_blank" class="text-xs text-slate-400 hover:text-white transition flex items-center gap-1">
              TradingView Chart ↗
            </a>
          </div>
        </div>
        """
    else:
        crypto_card_html = '<div class="p-5 rounded-2xl bg-slate-900 border border-slate-800 text-slate-400">Keine Krypto-Daten gefunden.</div>'

    return f"""
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {top_pick_html}
        {crypto_card_html}
      </div>
    """

hero_cards_html = render_hero_cards_html(raw_assets)

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

  <!-- Immediate Theme Application to prevent FOUC / flickering -->
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
    }})();
  </script>

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

    /* =========================================================================
       THEME SYSTEM: LIGHT & DARK MODE SUPPORT
       ========================================================================= */
    :root {{
      --theme-name: dark;
    }}
    html.light {{
      --theme-name: light;
      color-scheme: light;
    }}
    html.dark {{
      --theme-name: dark;
      color-scheme: dark;
    }}

    /* Light Theme Palette & Overrides */
    html.light body {{
      background-color: #f8fafc !important;
      color: #0f172a !important;
    }}
    html.light header {{
      background-color: rgba(255, 255, 255, 0.95) !important;
      border-color: #e2e8f0 !important;
      box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
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
    html.light .text-cyan-400 {{
      color: #0891b2 !important;
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

    /* Gradients in Light Mode */
    html.light [class*="from-emerald-950"] {{
      background-image: linear-gradient(to bottom right, #f0fdf4, #ffffff, #ffffff) !important;
    }}
    html.light [class*="from-indigo-950"] {{
      background-image: linear-gradient(to bottom right, #eef2ff, #ffffff, #ffffff) !important;
    }}
    html.light [class*="from-slate-900"] {{
      background-image: linear-gradient(to bottom right, #ffffff, #f8fafc) !important;
    }}

    /* Modals in Light Mode */
    html.light #quota-modal,
    html.light #positions-modal,
    html.light #alerts-modal,
    html.light #hypotheses-modal,
    html.light #detail-modal {{
      background-color: rgba(15, 23, 42, 0.65) !important;
    }}
    html.light #quota-modal > div,
    html.light #positions-modal > div,
    html.light #alerts-modal > div,
    html.light #hypotheses-modal > div,
    html.light #detail-modal > div {{
      background-color: #ffffff !important;
      border-color: #e2e8f0 !important;
      color: #0f172a !important;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25) !important;
    }}
    html.light #quota-modal .border-slate-800,
    html.light #positions-modal .border-slate-800,
    html.light #alerts-modal .border-slate-800,
    html.light #hypotheses-modal .border-slate-800,
    html.light #detail-modal .border-slate-800 {{
      border-color: #e2e8f0 !important;
    }}
    html.light input[type="text"],
    html.light input[type="number"],
    html.light select {{
      background-color: #f8fafc !important;
      border-color: #cbd5e1 !important;
      color: #0f172a !important;
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
      box-shadow: 0 0 25px -5px rgba(16, 185, 129, 0.3);
    }}
    .glow-rose {{
      box-shadow: 0 0 25px -5px rgba(244, 63, 94, 0.3);
    }}
    html.light .glow-emerald {{
      box-shadow: 0 4px 20px -2px rgba(16, 185, 129, 0.2);
    }}
    html.light .glow-rose {{
      box-shadow: 0 4px 20px -2px rgba(244, 63, 94, 0.2);
    }}

    /* Mobile Utilities & Touch Enhancements */
    .no-scrollbar::-webkit-scrollbar {{
      display: none;
    }}
    .no-scrollbar {{
      -ms-overflow-style: none;
      scrollbar-width: none;
    }}
    @media (max-width: 640px) {{
      input, select, textarea {{
        font-size: 16px !important; /* Prevents iOS auto-zoom on input focus */
      }}
    }}
  </style>
  <script>
    // Globaler Callback für Telegram Widget (wird aufgerufen sobald der Login erfolgt)
    window.onTelegramAuth = function(user) {{
      console.log('Telegram Auth Callback empfangen:', user);
      if (typeof handleTelegramLogin === 'function') {{
        handleTelegramLogin(user);
      }} else {{
        try {{
          localStorage.setItem('tg_user', JSON.stringify(user));
        }} catch(e) {{}}
        window.location.reload();
      }}
    }};
  </script>
</head>
<body class="bg-[#0b0f19] text-slate-100 min-h-screen antialiased selection:bg-indigo-500 selection:text-white">

  <!-- Telegram Authentication Gate Overlay -->
  <div id="telegram-auth-gate" class="fixed inset-0 z-[100] flex items-center justify-center bg-[#070a13]/95 backdrop-blur-xl p-4 transition-all duration-300">
    <div class="w-full max-w-md rounded-2xl bg-slate-900/95 border border-indigo-500/30 p-6 sm:p-8 shadow-2xl text-center space-y-5 relative overflow-hidden">
      <div class="absolute -top-24 -left-24 w-48 h-48 bg-indigo-500/20 rounded-full blur-3xl pointer-events-none"></div>
      <div class="absolute -bottom-24 -right-24 w-48 h-48 bg-purple-500/20 rounded-full blur-3xl pointer-events-none"></div>

      <div class="w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center mx-auto text-3xl shadow-lg shadow-indigo-500/20">
        🔐
      </div>

      <div>
        <h2 class="text-xl font-bold text-white tracking-tight">Privater Systemzugang</h2>
        <p class="text-xs text-slate-400 mt-1.5 leading-relaxed">
          TradingView Super-Analyst auf Raspberry Pi. Bitte authentifiziere dich über Telegram, um Zugriff auf deine Trades und Live-Marktanalysen zu erhalten.
        </p>
      </div>

      <!-- Telegram Official Login Widget -->
      <div id="tg-widget-mount" class="py-2 flex flex-col items-center justify-center min-h-[50px]">
        <script async src="https://telegram.org/js/telegram-widget.js?22" 
                data-telegram-login="aitradeanalystbot" 
                data-size="large" 
                data-radius="12" 
                data-onauth="onTelegramAuth(user)" 
                data-auth-url="https://bbbdc.github.io/trading-dashboard/index.html"
                data-request-access="write"></script>
      </div>

      <div id="tg-auth-error" class="hidden text-left"></div>

      <!-- Schnell-Login / Fallback Toggle -->
      <div class="pt-1">
        <button type="button" onclick="toggleFallbackLogin()" class="text-[11px] text-slate-500 hover:text-indigo-400 transition cursor-pointer underline">
          Alternative: Über Nutzernamen anmelden
        </button>
        <div id="fallback-login-container" class="hidden mt-3 p-3 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2 text-left">
          <label class="block text-[11px] text-slate-400">Telegram Benutzername:</label>
          <div class="flex gap-2">
            <input type="text" id="fallback-username-input" placeholder="z. B. Bdc_Gumb_Drop" class="flex-1 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-xs text-white focus:outline-none focus:border-indigo-500">
            <button type="button" onclick="submitFallbackLogin()" class="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs transition cursor-pointer shadow-md">
              Login
            </button>
          </div>
        </div>
      </div>

      <div class="pt-3 border-t border-slate-800 text-[11px] text-slate-500 space-y-1">
        <p>Zugriff nur für autorisierte Telegram-Nutzer.</p>
        <p>Noch nicht freigeschaltet? Öffne <a href="https://t.me/aitradeanalystbot" target="_blank" class="text-indigo-400 hover:text-indigo-300 font-semibold underline">@aitradeanalystbot</a> und sende <code class="bg-slate-800 px-1 py-0.5 rounded">/start</code>.</p>
      </div>
    </div>
  </div>

  <!-- Pull-Down-to-Refresh Visual Indicator (Touch & iOS) -->
  <div id="pull-refresh-indicator" class="fixed top-0 left-0 right-0 z-50 flex items-center justify-center pointer-events-none transition-transform duration-200 -translate-y-full">
    <div class="mt-3 px-4 py-2 rounded-full bg-[#0d1322]/95 border border-indigo-500/50 shadow-2xl backdrop-blur-md flex items-center gap-2.5 text-xs font-semibold text-slate-100">
      <svg id="pull-icon" class="w-4 h-4 text-indigo-400 transition-transform duration-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <path stroke-linecap="round" stroke-linejoin="round" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
      </svg>
      <span id="pull-text">Nach unten ziehen zum Aktualisieren</span>
    </div>
  </div>

  <!-- Toast Notification Banner -->
  <div id="toast-banner" class="fixed bottom-6 right-6 z-50 transform translate-y-24 opacity-0 transition-all duration-300 pointer-events-none">
    <div class="px-4 py-3 rounded-xl bg-slate-900/95 border border-emerald-500/50 text-white text-xs font-semibold shadow-2xl flex items-center gap-2 backdrop-blur-md">
      <span class="text-emerald-400 text-base">✓</span>
      <span id="toast-message">Dashboard erfolgreich aktualisiert!</span>
    </div>
  </div>

  <!-- Top Navigation Header -->
  <header class="border-b border-slate-800/80 bg-[#0d1322]/90 backdrop-blur sticky top-0 z-40 px-3 sm:px-6 py-2.5 sm:py-3.5">
    <div class="max-w-7xl mx-auto flex flex-col gap-3">
      
      <!-- Top Row: Brand & Theme Mode Switcher -->
      <div class="flex items-center justify-between gap-3">
        
        <!-- Brand & Engine Badge -->
        <div class="flex items-center gap-2.5 sm:gap-3 min-w-0">
          <div class="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-slate-900 border border-indigo-500/40 p-1 flex items-center justify-center shadow-lg shadow-indigo-500/20 shrink-0">
            <img src="icons/favicon.svg" alt="TV" class="w-7 h-7 sm:w-8 sm:h-8">
          </div>
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-1.5 sm:gap-2">
              <h1 class="font-bold text-base sm:text-lg tracking-tight text-white truncate">Super-Analyst</h1>
              <span class="hidden sm:inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">24/7 Pi</span>
              <span id="header-engine-badge" class="hidden md:inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-500/15 text-indigo-200 border border-indigo-500/30 items-center gap-1.5 shadow-sm">
                <span class="w-1.5 h-1.5 rounded-full {engine_dot_class}"></span>
                <span class="text-slate-400">KI:</span>
                <span class="font-bold text-white">{engine_display}</span>
              </span>
              <button id="header-quota-badge" onclick="switchDashboardTab('admin')" class="inline-flex px-2 py-0.5 rounded-full text-[10px] sm:text-[11px] font-semibold {quota_badge_class} items-center gap-1 shadow-sm cursor-pointer transition active:scale-95 shrink-0" title="Google AI Studio API-Key Kontingent & Status">
                <span>🔑</span>
                <span>Quota: <strong class="{quota_num_class}">{quota_used}/{quota_limit}</strong></span>
                <span class="hidden sm:inline text-[9px] opacity-80">· {quota_status_text}</span>
              </button>
              <span id="header-trader-badge" class="inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 items-center gap-1.5" title="TradingView Live-Feed Status">
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                <span>⚡ TV Live: {last_quotes_update_display}</span>
              </span>
            </div>
            <p class="hidden sm:block text-[11px] text-slate-400 mt-0.5">Multi-Timeframe Confluence (4h · 8h · 1D) | SMC · Wyckoff VSA · RSI Divs</p>
          </div>
        </div>

        <!-- Right Side: Telegram User Profile & Theme Control -->
        <div class="flex items-center gap-2 shrink-0">

          <!-- User Profile Pill (Visible when authenticated) -->
          <div id="auth-user-badge" class="hidden flex items-center gap-1.5 p-1 pl-2 rounded-xl bg-slate-800/80 border border-slate-700/60 text-xs shrink-0 shadow-sm">
            <div class="flex items-center gap-1.5">
              <img id="auth-user-photo" src="" alt="" class="w-5 h-5 rounded-full object-cover hidden">
              <span id="auth-user-avatar-fallback" class="w-5 h-5 rounded-full bg-indigo-500/20 text-indigo-300 flex items-center justify-center text-[10px] font-bold">👤</span>
              <span id="auth-user-name" class="font-bold text-slate-200 text-[11px]">User</span>
              <span id="auth-user-role-badge" class="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-indigo-500/20 text-indigo-300">TRADER</span>
            </div>
            <button onclick="logoutTelegram()" title="Abmelden" class="w-6 h-6 rounded-lg bg-slate-900/60 hover:bg-rose-500/20 text-slate-400 hover:text-rose-400 flex items-center justify-center text-xs transition cursor-pointer">
              ✕
            </button>
          </div>

          <div class="inline-flex p-0.5 rounded-xl bg-slate-800/80 border border-slate-700/60 text-xs font-semibold shrink-0 shadow-sm" id="theme-segmented-control" role="group" aria-label="Theme Modus">
            <button type="button" onclick="setThemeMode('auto')" id="theme-btn-auto" class="px-2 py-1 rounded-lg transition active:scale-95 cursor-pointer text-[10px] sm:text-[11px] font-bold" title="Automatisch nach Tageszeit (07:00-19:00 Hell, danach Dunkel)">
              <span>⏰</span><span class="ml-1 hidden xs:inline sm:inline">Auto</span>
            </button>
            <button type="button" onclick="setThemeMode('light')" id="theme-btn-light" class="px-2 py-1 rounded-lg transition active:scale-95 cursor-pointer text-[10px] sm:text-[11px] font-bold" title="Heller Modus dauerhaft aktiv">
              <span>☀️</span><span class="ml-1 hidden xs:inline sm:inline">Hell</span>
            </button>
            <button type="button" onclick="setThemeMode('dark')" id="theme-btn-dark" class="px-2 py-1 rounded-lg transition active:scale-95 cursor-pointer text-[10px] sm:text-[11px] font-bold" title="Dunkler Modus dauerhaft aktiv">
              <span>🌙</span><span class="ml-1 hidden xs:inline sm:inline">Dunkel</span>
            </button>
          </div>
        </div>

      </div>

      <!-- Action & Navigation Bar: Desktop Tabs & Quick Actions -->
      <div class="flex items-center justify-between gap-2 pt-1 border-t border-slate-800/60 overflow-hidden">
        
        <!-- Desktop Segment Navigation Bar -->
        <div id="desktop-tab-navigation" class="hidden md:flex items-center gap-1 p-1 rounded-xl bg-slate-900/90 border border-slate-800 shrink-0">
          <button id="nav-tab-positions" onclick="switchDashboardTab('positions')" class="dashboard-nav-btn flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold transition bg-indigo-600 text-white shadow-md shadow-indigo-600/30 cursor-pointer">
            <span>👤</span>
            <span>Positionen</span>
            <span id="nav-badge-positions" class="hidden ml-1 px-1.5 py-0.2 rounded-full text-[10px] bg-white/20 text-white font-mono">0</span>
          </button>
          <button id="nav-tab-topsetups" onclick="switchDashboardTab('topsetups')" class="dashboard-nav-btn flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold transition text-slate-400 hover:text-white hover:bg-slate-800/60 cursor-pointer">
            <span>🎯</span>
            <span>Top-Setups</span>
          </button>
          <button id="nav-tab-scanner" onclick="switchDashboardTab('scanner')" class="dashboard-nav-btn flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold transition text-slate-400 hover:text-white hover:bg-slate-800/60 cursor-pointer">
            <span>🚀</span>
            <span>Markt-Scanner</span>
            <span class="ml-1 px-1.5 py-0.2 rounded-full text-[10px] bg-slate-800 text-slate-300 font-mono">55</span>
          </button>
          <button id="nav-tab-admin" onclick="switchDashboardTab('admin')" class="dashboard-nav-btn hidden flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold transition border border-amber-500/30 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20 cursor-pointer">
            <span>⚙️</span>
            <span>Admin-Zentrale</span>
          </button>
        </div>

        <!-- Navigation Buttons Strip (Horizontal Scroll on Mobile) -->
        <div class="flex items-center gap-1.5 sm:gap-2 overflow-x-auto no-scrollbar py-1 shrink min-w-0 touch-pan-x">
          
          <!-- Next Scan Live Countdown Timer -->
          <div class="px-2.5 py-1.5 rounded-xl bg-indigo-950/40 border border-indigo-500/30 flex items-center gap-1.5 shadow-sm shrink-0" title="Market Gatekeeper: Dynamischer Check jede Stunde (:05)">
            <span class="relative flex h-2 w-2">
              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
              <span class="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
            </span>
            <div class="flex items-baseline gap-1">
              <span class="text-[9px] uppercase font-semibold text-slate-400">Scan:</span>
              <span class="font-mono font-bold text-xs text-indigo-300 leading-tight" id="next-scan-countdown">--:--</span>
            </div>
          </div>

          <!-- Smart Refresh Button (Admin triggers Pi scan, Trader re-reads data) -->
          <button id="btn-manual-refresh" onclick="triggerSmartRefresh()" class="px-2.5 py-1.5 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700/60 text-xs font-semibold text-slate-200 hover:text-white flex items-center gap-1.5 transition active:scale-95 shadow-sm cursor-pointer shrink-0" title="Aktualisieren">
            <svg id="refresh-icon" class="w-3.5 h-3.5 text-indigo-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            <span id="refresh-label">Refresh</span>
          </button>

          <!-- Signal-Historie Link Button -->
          <a href="history.html" class="px-2.5 py-1.5 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/40 text-xs font-semibold text-indigo-300 hover:text-white flex items-center gap-1.5 transition active:scale-95 shadow-sm cursor-pointer shrink-0">
            <span>📜</span>
            <span class="whitespace-nowrap">Historie</span>
          </a>

          <!-- iOS Alerts Info Button -->
          <button onclick="openAlertsModal()" class="px-2.5 py-1.5 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/40 text-xs font-semibold text-indigo-300 hover:text-white flex items-center gap-1.5 transition active:scale-95 shadow-sm cursor-pointer shrink-0">
            <span>🔔</span>
            <span>Alerts</span>
          </button>

          <!-- Hypothesen Guide Info Button -->
          <button onclick="openHypothesesModal()" class="px-2.5 py-1.5 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/40 text-xs font-semibold text-indigo-300 hover:text-white flex items-center gap-1.5 transition active:scale-95 shadow-sm cursor-pointer shrink-0">
            <span>💡</span>
            <span>Guide</span>
          </button>

        </div>

        <!-- Quick Metrics Counter -->
        <div class="flex items-center gap-1 sm:gap-1.5 shrink-0 pl-1 border-l border-slate-800/60">
          <div class="px-2 py-1 rounded-lg bg-slate-800/60 border border-slate-700/50 flex items-center gap-1 text-[11px]" title="Gesamt">
            <span class="text-slate-400 hidden sm:inline">Tot:</span>
            <span class="font-mono font-bold text-white" id="stat-total">{db_data.get('total_analyzed', 0)}</span>
          </div>
          <div class="px-2 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center gap-1 text-[11px]" title="Longs">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            <span class="text-emerald-300 hidden sm:inline">L:</span>
            <span class="font-mono font-bold text-emerald-400" id="stat-long">{db_data.get('long_count', 0)}</span>
          </div>
          <div class="px-2 py-1 rounded-lg bg-rose-500/10 border border-rose-500/30 flex items-center gap-1 text-[11px]" title="Shorts">
            <span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
            <span class="text-rose-300 hidden sm:inline">S:</span>
            <span class="font-mono font-bold text-xs text-rose-400" id="stat-short">{db_data.get('short_count', 0)}</span>
          </div>
          <div class="hidden sm:flex px-2 py-1 rounded-lg bg-slate-800/60 border border-slate-700/50 items-center gap-1 text-[11px]" title="Neutral">
            <span class="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
            <span class="text-slate-400">N:</span>
            <span class="font-mono font-bold text-slate-300" id="stat-neutral">{db_data.get('neutral_count', 0)}</span>
          </div>
        </div>

      </div>

        <!-- Quick Metrics Counter -->
        <div class="flex items-center gap-1 sm:gap-1.5 shrink-0 pl-1 border-l border-slate-800/60">
          <div class="px-2 py-1 rounded-lg bg-slate-800/60 border border-slate-700/50 flex items-center gap-1 text-[11px]" title="Gesamt">
            <span class="text-slate-400 hidden sm:inline">Tot:</span>
            <span class="font-mono font-bold text-white" id="stat-total">{db_data.get('total_analyzed', 0)}</span>
          </div>
          <div class="px-2 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center gap-1 text-[11px]" title="Longs">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            <span class="text-emerald-300 hidden sm:inline">L:</span>
            <span class="font-mono font-bold text-emerald-400" id="stat-long">{db_data.get('long_count', 0)}</span>
          </div>
          <div class="px-2 py-1 rounded-lg bg-rose-500/10 border border-rose-500/30 flex items-center gap-1 text-[11px]" title="Shorts">
            <span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
            <span class="text-rose-300 hidden sm:inline">S:</span>
            <span class="font-mono font-bold text-xs text-rose-400" id="stat-short">{db_data.get('short_count', 0)}</span>
          </div>
          <div class="hidden sm:flex px-2 py-1 rounded-lg bg-slate-800/60 border border-slate-700/50 items-center gap-1 text-[11px]" title="Neutral">
            <span class="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
            <span class="text-slate-400">N:</span>
            <span class="font-mono font-bold text-slate-300" id="stat-neutral">{db_data.get('neutral_count', 0)}</span>
          </div>
        </div>

      </div>
    </div>
  </header>

  <!-- Main Container with Tab Views -->
  <main class="max-w-7xl mx-auto px-3 sm:px-6 py-5 space-y-6 pb-28 md:pb-12">

    <!-- =========================================================================
         TAB 1: EIGENE POSITIONEN (COCKPIT)
         ========================================================================= -->
    <div id="tab-content-positions" class="tab-pane space-y-6">
      <!-- 👤 EIGENE NUTZER-POSITIONEN & SMARTE HANDLUNGSEMPFEHLUNGEN -->
      <section id="user-positions-section" class="rounded-2xl bg-gradient-to-br from-slate-900/90 via-[#0d1322] to-slate-900 border border-indigo-500/30 p-5 shadow-xl space-y-4">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800/80 pb-3.5">
          <div>
            <div class="flex items-center gap-2">
              <h2 class="text-base sm:text-lg font-bold text-white tracking-tight flex items-center gap-2">
                <span>👤 Meine Positionen</span>
              </h2>
              <span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">24/7 Raspberry Pi Überwachung</span>
            </div>
            <p class="text-xs text-slate-400 mt-0.5">Eigene Trades mit Hebel tracken &bull; Automatische Handlungsempfehlungen bei Divergenzen & TP-Zonen</p>
          </div>
          <div class="flex items-center gap-2">
            <button onclick="openPositionsModal()" class="px-3.5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold transition flex items-center gap-1.5 shadow-lg shadow-indigo-600/30 active:scale-95 cursor-pointer">
              <span>+</span>
              <span>Position hinzufügen</span>
            </button>
          </div>
        </div>

        <!-- Container für Nutzer-Positionen -->
        <div id="user-positions-container" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
          <!-- Dynamisch gerendert durch JS -->
        </div>
      </section>
    </div>

    <!-- =========================================================================
         TAB 2: TOP-SETUPS & HERO CHANCEN
         ========================================================================= -->
    <div id="tab-content-topsetups" class="tab-pane hidden space-y-6">
      
      <!-- Top-Setups Header Banner -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-4 rounded-xl bg-gradient-to-r from-slate-900 via-indigo-950/40 to-slate-900 border border-indigo-500/30">
        <div>
          <div class="flex items-center gap-2">
            <span class="text-xl">🎯</span>
            <h2 class="text-base sm:text-lg font-bold text-white tracking-tight">High-Conviction Top-Setups</h2>
            <span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Score ≥ 85%</span>
          </div>
          <p class="text-xs text-slate-400 mt-0.5">Handverlesene Setup-Chancen mit maximalem CRV &bull; Multi-Timeframe Confluence (4h · 8h · 1D)</p>
        </div>
        <button onclick="openHypothesesModal()" class="self-start sm:self-auto px-3 py-1.5 rounded-lg bg-indigo-600/30 hover:bg-indigo-600/50 border border-indigo-500/40 text-indigo-200 text-xs font-semibold transition cursor-pointer">
          Hypothesen-Guide 💡
        </button>
      </div>

      <!-- Dynamische Highlight Opportunity Hero Cards: Top Opportunity & Krypto Leitwolf -->
      {hero_cards_html}

      <!-- TradingView Watchlist Filter Bar for Top Setups -->
      <div class="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2.5">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div class="flex items-center gap-2">
            <span class="text-xs font-bold text-white uppercase tracking-wider">TradingView Listen-Filter:</span>
            <span class="text-[11px] text-slate-400">Wähle eine Liste für isolierte Top Longs / Shorts</span>
          </div>
          <span class="text-[10px] font-mono text-indigo-300">Live Confluence Filter</span>
        </div>
        <div class="flex flex-wrap items-center gap-1.5">
          {tab2_watchlist_pills_html}
        </div>
      </div>

      <!-- Top 3 Longs & Top 3 Shorts Ranking Cards Grid -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <!-- Top 3 Longs Card -->
        <div class="rounded-2xl bg-gradient-to-br from-slate-900/90 via-[#0d1322] to-slate-900 border border-emerald-500/30 p-4 sm:p-5 shadow-xl space-y-3">
          <div class="flex items-center justify-between pb-2.5 border-b border-slate-800">
            <div class="flex items-center gap-2">
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
              <h3 id="top-longs-title" class="font-bold text-white text-sm">🟢 Top Long Setups</h3>
            </div>
            <span id="top-longs-subtitle" class="text-[11px] font-mono text-emerald-400">Beste Long Confluence</span>
          </div>
          <div id="top-longs-container" class="space-y-2.5">
            {top_longs_cards_html}
          </div>
        </div>

        <!-- Top Short Setups Card -->
        <div class="rounded-2xl bg-gradient-to-br from-slate-900/90 via-[#0d1322] to-slate-900 border border-rose-500/30 p-4 sm:p-5 shadow-xl space-y-3">
          <div class="flex items-center justify-between pb-2.5 border-b border-slate-800">
            <div class="flex items-center gap-2">
              <span class="w-2.5 h-2.5 rounded-full bg-rose-400"></span>
              <h3 id="top-shorts-title" class="font-bold text-white text-sm">🔴 Top Short Setups</h3>
            </div>
            <span id="top-shorts-subtitle" class="text-[11px] font-mono text-rose-400">Stärkste Reversal-Divergenzen</span>
          </div>
          <div id="top-shorts-container" class="space-y-2.5">
            {top_shorts_cards_html}
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

    </div>

    <!-- =========================================================================
         TAB 3: MARKT-SCANNER (58 ASSET MATRIX & FILTER)
         ========================================================================= -->
    <div id="tab-content-scanner" class="tab-pane hidden space-y-6">

      <!-- Filter & Navigation Control Center -->
      <div class="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-4">
        <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          
          <!-- Direction Filter Pills -->
          <div class="flex flex-wrap items-center gap-2">
            <button onclick="setDirectionFilter('ALL')" id="filter-dir-ALL" class="filter-dir-btn px-3 py-1.5 rounded-lg text-xs font-semibold transition bg-indigo-600 text-white shadow-sm shadow-indigo-500/20 cursor-pointer">
              Alle (<span id="count-all">55</span>)
            </button>
            <button onclick="setDirectionFilter('LONG')" id="filter-dir-LONG" class="filter-dir-btn px-3 py-1.5 rounded-lg text-xs font-semibold transition bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 cursor-pointer">
              🟢 Long Setups (<span id="count-long">14</span>)
            </button>
            <button onclick="setDirectionFilter('SHORT')" id="filter-dir-SHORT" class="filter-dir-btn px-3 py-1.5 rounded-lg text-xs font-semibold transition bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 cursor-pointer">
              🔴 Short Setups (<span id="count-short">20</span>)
            </button>
            <button onclick="setDirectionFilter('NEUTRAL')" id="filter-dir-NEUTRAL" class="filter-dir-btn px-3 py-1.5 rounded-lg text-xs font-semibold transition bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 cursor-pointer">
              ⚪ Neutral / Watchlist (<span id="count-neutral">21</span>)
            </button>
          </div>

          <!-- Search Bar -->
          <div class="relative w-full lg:w-72">
            <input type="text" id="search-input" oninput="applyFilters()" placeholder="Symbol oder Name suchen..." class="w-full px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-700/80 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition">
            <span class="absolute right-3 top-2.5 text-xs text-slate-500 pointer-events-none">🔍</span>
          </div>

        </div>

        <!-- TradingView Watchlists Filter Row -->
        <div class="flex flex-wrap items-center gap-1.5 text-xs pt-3 border-t border-slate-800/80">
          <span class="text-slate-400 mr-1 text-[11px] uppercase tracking-wider font-semibold">TV Liste:</span>
          {scanner_watchlist_pills_html}
        </div>

        <!-- Secondary Filter Row: Asset Class, Sorting, View Toggle -->
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-3 border-t border-slate-800/80">
          
          <!-- Category Buttons -->
          <div class="flex flex-wrap items-center gap-1.5 text-xs">
            <span class="text-slate-400 mr-1 text-[11px] uppercase tracking-wider font-semibold">Klasse:</span>
            <button onclick="setCategoryFilter('ALL')" id="filter-cat-ALL" class="filter-cat-btn px-2.5 py-1 rounded-md transition bg-slate-700 text-white font-medium cursor-pointer">Alle</button>
            <button onclick="setCategoryFilter('Crypto')" id="filter-cat-Crypto" class="filter-cat-btn px-2.5 py-1 rounded-md transition text-slate-400 hover:text-white hover:bg-slate-800 font-medium cursor-pointer">Crypto</button>
            <button onclick="setCategoryFilter('Stock')" id="filter-cat-Stock" class="filter-cat-btn px-2.5 py-1 rounded-md transition text-slate-400 hover:text-white hover:bg-slate-800 font-medium cursor-pointer">Aktien</button>
            <button onclick="setCategoryFilter('Commodity')" id="filter-cat-Commodity" class="filter-cat-btn px-2.5 py-1 rounded-md transition text-slate-400 hover:text-white hover:bg-slate-800 font-medium cursor-pointer">Rohstoffe</button>
            <button onclick="setCategoryFilter('Macro')" id="filter-cat-Macro" class="filter-cat-btn px-2.5 py-1 rounded-md transition text-slate-400 hover:text-white hover:bg-slate-800 font-medium cursor-pointer">Makro/Indizes</button>
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
              <button onclick="setViewMode('grid')" id="view-grid-btn" class="px-2 py-1 rounded text-xs font-semibold bg-indigo-600 text-white cursor-pointer">Cards</button>
              <button onclick="setViewMode('table')" id="view-table-btn" class="px-2 py-1 rounded text-xs font-semibold text-slate-400 hover:text-white cursor-pointer">Tabelle</button>
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

    </div>

    <!-- =========================================================================
         TAB 4: MASTER-ADMIN ZENTRALE (STRENG VERTRAULICH)
         ========================================================================= -->
    <div id="tab-content-admin" class="tab-pane hidden space-y-6">

      <!-- Admin Top Banner -->
      <div class="p-5 rounded-2xl bg-gradient-to-r from-amber-950/40 via-slate-900 to-slate-900 border border-amber-500/40 shadow-xl flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div class="flex items-center gap-3.5">
          <div class="w-12 h-12 rounded-xl bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-2xl shrink-0">
            ⚙️
          </div>
          <div>
            <div class="flex items-center gap-2">
              <h2 class="text-base sm:text-lg font-bold text-white tracking-tight">Master-Admin Kontrollzentrum</h2>
              <span class="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">STRENG VERTRAULICH</span>
            </div>
            <p class="text-xs text-slate-400 mt-0.5">Google AI Studio API-Key Quota Pool &bull; KI High-Conviction Modell-Portfolio &bull; Benutzerverwaltung &bull; Pi Engine</p>
          </div>
        </div>

        <button onclick="triggerManualRefresh()" class="self-start sm:self-auto px-4 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition flex items-center gap-2 shadow-lg shadow-amber-500/20 active:scale-95 cursor-pointer shrink-0">
          <span>⚡</span>
          <span>Master Live-Scan starten (Pi)</span>
        </button>
      </div>

      <!-- Card Health & Routing: Übersicht Kaskade & Vorab-Check -->
      {routing_health_card_html}

      <!-- Card A: Google Gemini API-Key Pool (Stufe 1A) -->
      <section class="rounded-2xl bg-gradient-to-br from-slate-900/95 via-[#0d1322] to-slate-900 border border-indigo-500/30 p-5 shadow-xl space-y-4">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-3 border-b border-slate-800">
          <div class="flex items-center gap-2.5">
            <span class="text-xl">🔑</span>
            <div>
              <div class="flex items-center gap-2">
                <h3 class="font-bold text-white text-base">Google Gemini API-Key Quota Pool</h3>
                <span class="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">STUFE 1A: PRIMÄR-ROUTING (KOSTENLOS)</span>
              </div>
              <p class="text-xs text-slate-400">Intelligentes Failover & Multi-Key Lastverteilung ({total_keys_count}x AI Studio Keys)</p>
            </div>
          </div>
          <span class="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 self-start sm:self-auto">
            Modell: gemini-3.8-flash
          </span>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
          <div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
            <span class="text-[10px] text-slate-400 block uppercase">Gesamt-Verbrauch</span>
            <span class="font-bold text-base {quota_num_class}">{quota_used} / {quota_limit} Requests</span>
            <span class="block text-[10px] text-slate-500 mt-0.5">{quota_pct}% des Tageslimits</span>
          </div>
          <div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
            <span class="text-[10px] text-slate-400 block uppercase">Verbleibend</span>
            <span class="font-bold text-base text-emerald-400">{quota_remaining} Requests</span>
            <span class="block text-[10px] text-slate-500 mt-0.5">{active_keys_count} von {total_keys_count} Keys aktiv</span>
          </div>
          <div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
            <span class="text-[10px] text-slate-400 block uppercase">Tages-Reset</span>
            <span class="font-bold text-base text-indigo-300">{quota_countdown}</span>
            <span class="block text-[10px] text-slate-500 mt-0.5">00:00 UTC</span>
          </div>
        </div>

        <div class="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
          <div class="h-2 rounded-full {quota_bar_color}" style="width: {min(100.0, quota_pct)}%"></div>
        </div>

        <!-- Einzel-Keys Breakdown Grid -->
        <div class="space-y-2 pt-2">
          <span class="text-xs font-bold text-slate-300 uppercase tracking-wider block">Einzel-Key Status & Kontingente:</span>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {keys_cards_html}
          </div>
        </div>
      </section>

      <!-- Card Pro-Abo: Google Pro Subscription Status (Stufe 1B) -->
      {pro_card_html}

      <!-- Card B: Autonomes KI High-Conviction Modell-Portfolio & Gedächtnis -->
      <section id="portfolio-section" class="rounded-2xl bg-gradient-to-br from-slate-900/95 via-emerald-950/20 to-slate-900 border border-emerald-500/30 p-5 shadow-xl space-y-5">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800/80 pb-3.5">
          <div>
            <div class="flex items-center gap-2">
              <h2 class="text-base sm:text-lg font-bold text-white tracking-tight flex items-center gap-2">
                <span>🏛️ KI High-Conviction Modell-Portfolio</span>
              </h2>
              <span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                Autonom & Lernend
              </span>
            </div>
            <p class="text-xs text-slate-400 mt-0.5">Nur sicherste Setups (Score ≥ 88%) &bull; Identischer Einheitsbetrag (1.000 €) für relative Performance &bull; Hebel (max 10x) durch KI &bull; Permanenter Erfahrungsspeicher</p>
          </div>

          <!-- Portfolio Performance KPIs -->
          <div class="flex flex-wrap items-center gap-2 text-xs font-mono">
            <div class="px-3 py-1.5 rounded-xl bg-slate-950/80 border border-slate-800">
              <span class="text-[10px] text-slate-400 block uppercase">Gehebelt</span>
              <span class="font-bold text-sm text-emerald-400" id="port-metric-lev-pnl">+0.0%</span>
            </div>
            <div class="px-3 py-1.5 rounded-xl bg-slate-950/80 border border-slate-800">
              <span class="text-[10px] text-slate-400 block uppercase">Basis (1x)</span>
              <span class="font-bold text-sm text-white" id="port-metric-raw-pnl">+0.0%</span>
            </div>
            <div class="px-3 py-1.5 rounded-xl bg-slate-950/80 border border-slate-800">
              <span class="text-[10px] text-slate-400 block uppercase">Win-Rate</span>
              <span class="font-bold text-sm text-indigo-300" id="port-metric-winrate">0.0%</span>
            </div>
          </div>
        </div>

        <!-- Aktive Trades des KI-Portfolios -->
        <div>
          <div class="flex items-center justify-between mb-2.5">
            <h3 class="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <span>Aktuell laufende Trades</span>
              <span class="px-2 py-0.5 rounded-full text-[10px] bg-slate-800 text-slate-300 font-mono" id="port-active-count">0</span>
            </h3>
            <span class="text-[11px] text-slate-500 font-mono">Multi-Day Exit nach SMC/CRV-Regeln</span>
          </div>
          <div id="portfolio-active-trades" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
            <!-- Dynamisch via JS -->
          </div>
        </div>

        <!-- Trade Memory & Erfahrungs-Gedächtnis (Accordion) -->
        <div class="border-t border-slate-800/80 pt-4">
          <button onclick="toggleMemoryAccordion()" class="w-full flex items-center justify-between p-3 rounded-xl bg-slate-950/60 hover:bg-slate-950/90 border border-slate-800 text-left transition cursor-pointer">
            <div class="flex items-center gap-2.5">
              <span class="text-base">🧠</span>
              <div>
                <span class="text-xs font-bold text-slate-200">Trade-Gedächtnis & Post-Mortem Lerneinheiten</span>
                <span class="block text-[10px] text-slate-400" id="memory-status-summary">Lade Erfahrungsspeicher...</span>
              </div>
            </div>
            <span id="memory-accordion-icon" class="text-slate-400 text-xs font-mono transition">▼</span>
          </button>

          <div id="memory-accordion-content" class="hidden mt-3 space-y-3">
            <div id="memory-learnings-list" class="space-y-2">
              <!-- Dynamisch via JS -->
            </div>
            <div id="portfolio-closed-trades" class="space-y-2">
              <!-- Dynamisch via JS -->
            </div>
          </div>
        </div>
      </section>

      <!-- Card C: Autorisierte Benutzer & Rollenverwaltung -->
      <section class="rounded-2xl bg-gradient-to-br from-slate-900/95 via-[#0d1322] to-slate-900 border border-slate-800 p-5 shadow-xl space-y-4">
        <div class="flex items-center justify-between pb-3 border-b border-slate-800">
          <div class="flex items-center gap-2.5">
            <span class="text-xl">👥</span>
            <div>
              <h3 class="font-bold text-white text-base">Autorisierte Benutzer & Rollen</h3>
              <p class="text-xs text-slate-400">Verwaltet über Telegram-Bot (@aitradeanalystbot) und telegram_config.json</p>
            </div>
          </div>
          <span class="px-2.5 py-1 rounded-full text-[10px] font-mono bg-slate-800 text-slate-300">
            Gesichert durch Pi
          </span>
        </div>

        <div id="admin-users-list" class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <!-- Dynamisch via JS gefüllt -->
        </div>
      </section>

      <!-- Card D: Raspberry Pi 24/7 Engine Status -->
      <section class="rounded-2xl bg-gradient-to-br from-slate-900/95 via-[#0d1322] to-slate-900 border border-slate-800 p-5 shadow-xl space-y-4">
        <div class="flex items-center justify-between pb-3 border-b border-slate-800">
          <div class="flex items-center gap-2.5">
            <span class="text-xl">🍓</span>
            <div>
              <h3 class="font-bold text-white text-base">Raspberry Pi 24/7 Engine Status</h3>
              <p class="text-xs text-slate-400">Autonomer Scan- und Überwachungs-Daemon</p>
            </div>
          </div>
          <span class="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
            ● 24/7 System Online
          </span>
        </div>

        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
          <div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
            <span class="text-[10px] text-slate-400 block uppercase">Scan-Intervall</span>
            <span class="font-bold text-white block mt-0.5">Dynamisch / Stündlich</span>
            <span class="text-[10px] text-indigo-300">Market Gatekeeper</span>
          </div>
          <div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
            <span class="text-[10px] text-slate-400 block uppercase">TradingView MCP</span>
            <span class="font-bold text-white block mt-0.5">Bridge Aktiv</span>
            <span class="text-[10px] text-emerald-400">Live Kerzen 4h/8h/1D</span>
          </div>
          <div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
            <span class="text-[10px] text-slate-400 block uppercase">Telegram Bot</span>
            <span class="font-bold text-white block mt-0.5">Service Active</span>
            <span class="text-[10px] text-emerald-400">Systemd Daemon</span>
          </div>
          <div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800">
            <span class="text-[10px] text-slate-400 block uppercase">Auto-Deploy</span>
            <span class="font-bold text-white block mt-0.5">GitHub Pages</span>
            <span class="text-[10px] text-cyan-400">bbbdc.github.io</span>
          </div>
        </div>
      </section>

    </div>

  </main>

  <!-- Multi-Timeframe Inspection Modal -->
  <div id="detail-modal" onclick="if(event.target === this) closeDetailModal()" ontouchend="if(event.target === this) {{ event.preventDefault(); closeDetailModal(); }}" class="fixed inset-0 z-50 hidden bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-2 sm:p-4 overflow-y-auto">
    <div class="bg-[#0f172a] border border-slate-700/80 rounded-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto shadow-2xl p-4 sm:p-6 space-y-5 my-auto">
      
      <!-- Modal Header -->
      <div class="flex items-start justify-between pb-4 border-b border-slate-800">
        <div>
          <div class="flex items-center gap-2 flex-wrap">
            <span id="modal-signal-badge" class="px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider"></span>
            <h2 id="modal-asset-name" class="text-xl font-bold text-white tracking-tight"></h2>
            <span id="modal-asset-ticker" class="text-xs font-mono text-slate-400"></span>
            <span id="modal-market-state" class="inline-flex items-center"></span>
          </div>
          <div class="flex items-center gap-2 mt-1">
            <p id="modal-setup-title" class="text-xs text-indigo-400 font-semibold"></p>
            <button onclick="openHypothesesModal(document.getElementById('modal-setup-title').innerText)" class="px-2 py-0.5 rounded bg-indigo-500/10 hover:bg-indigo-500/25 text-indigo-300 hover:text-white border border-indigo-500/30 text-[10px] font-semibold transition cursor-pointer flex items-center gap-1" title="Erklärung zu dieser Setup-Hypothese anzeigen">
              💡 Setup-Logik
            </button>
          </div>
        </div>
        <button onclick="closeDetailModal()" aria-label="Schließen" class="w-11 h-11 min-w-[44px] min-h-[44px] rounded-xl bg-slate-800 text-slate-300 hover:text-white flex items-center justify-center transition active:scale-95 cursor-pointer text-lg font-bold">
          ✕
        </button>
      </div>

      <!-- Active User Position Highlight Banner (if user has open trade) -->
      <div id="modal-user-pos-box" class="hidden"></div>

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
            <button id="btn-chart-tf-1h" onclick="selectModalTimeframe('1h')" class="px-2.5 py-1 rounded text-xs font-mono font-semibold bg-transparent text-slate-400 hover:text-white hover:bg-slate-800">1h</button>
            <button id="btn-chart-tf-4h" onclick="selectModalTimeframe('4h')" class="px-2.5 py-1 rounded text-xs font-mono font-bold bg-indigo-600 text-white shadow-sm shadow-indigo-500/30">4h</button>
            <button id="btn-chart-tf-1D" onclick="selectModalTimeframe('1D')" class="px-2.5 py-1 rounded text-xs font-mono font-semibold bg-transparent text-slate-400 hover:text-white hover:bg-slate-800">1D</button>
            <button id="btn-chart-tf-3D" onclick="selectModalTimeframe('3D')" class="px-2.5 py-1 rounded text-xs font-mono font-semibold bg-transparent text-slate-400 hover:text-white hover:bg-slate-800 hidden">3D</button>
            <button id="btn-chart-tf-1W" onclick="selectModalTimeframe('1W')" class="px-2.5 py-1 rounded text-xs font-mono font-semibold bg-transparent text-slate-400 hover:text-white hover:bg-slate-800">1W</button>
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
    let activeWatchlist = 'ALL';
    let currentViewMode = 'grid';

    // Versuche Live-JSON nachzuladen
    fetch('market_analysis_db.json')
      .then(r => r.json())
      .then(data => {{
        const authCfg = data.auth_config || (currentData && currentData.auth_config) || (typeof EMBEDDED_DATABASE !== 'undefined' && EMBEDDED_DATABASE.auth_config);
        currentData = data;
        if (authCfg && !currentData.auth_config) {{
          currentData.auth_config = authCfg;
        }}
        filteredAssets = [...currentData.assets];
        updateStats();
        applyFilters();
        renderTopPicksForWatchlist(activeWatchlist);
        if (typeof initAuthOnLoad === 'function') {{
          initAuthOnLoad();
        }}
      }})
      .catch(e => {{
        console.log("Nutze integrierte Datenbank (Offline/File-Modus)");
        updateStats();
        applyFilters();
        renderTopPicksForWatchlist(activeWatchlist);
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

    function setWatchlistFilter(wl) {{
      activeWatchlist = wl;

      // Update pills in Tab 3 (Scanner)
      document.querySelectorAll('.filter-wl-btn').forEach(btn => {{
        btn.classList.remove('bg-indigo-600', 'text-white', 'shadow-sm', 'shadow-indigo-500/20');
        btn.classList.add('text-slate-400');
      }});
      const safeId = wl.replace(/\\s+/g, '_').replace(/\\//g, '_');
      const activeScanBtn = document.getElementById('filter-wl-' + safeId);
      if (activeScanBtn) {{
        activeScanBtn.classList.remove('text-slate-400');
        activeScanBtn.classList.add('bg-indigo-600', 'text-white', 'shadow-sm', 'shadow-indigo-500/20');
      }}

      // Update pills in Tab 2 (Top Picks)
      document.querySelectorAll('.tab2-wl-btn').forEach(btn => {{
        btn.classList.remove('bg-indigo-600', 'text-white', 'shadow-sm', 'shadow-indigo-500/20');
        btn.classList.add('bg-slate-900', 'border', 'border-slate-800', 'text-slate-300');
      }});
      const activeTab2Btn = document.getElementById('tab2-wl-' + safeId);
      if (activeTab2Btn) {{
        activeTab2Btn.classList.remove('bg-slate-900', 'border', 'border-slate-800', 'text-slate-300');
        activeTab2Btn.classList.add('bg-indigo-600', 'text-white', 'shadow-sm', 'shadow-indigo-500/20');
      }}

      // Top Picks in Tab 2 dynamisch für diese Watchlist anpassen
      renderTopPicksForWatchlist(wl);

      // Filter im Scanner anwenden
      applyFilters();
    }}

    function getAssetCurrencySymbol(c) {{
      if (c && c.currency === 'EUR') return '€';
      const sym = (c && c.symbol ? c.symbol : '').toUpperCase();
      const cat = (c && c.category ? c.category : '').toUpperCase();
      const wls = (c && c.watchlists) ? c.watchlists : [];
      if (sym.startsWith('TRADEGATE:') || sym.startsWith('XETR:') || sym.startsWith('FWB:') || wls.includes('Tradegate Werte') || cat.includes('TRADEGATE') || cat.includes('DEUTSCHE AKTIEN') || sym.includes('DAX')) {{
        return '€';
      }}
      return '$';
    }}

    function getAssetCurrencyCode(c) {{
      return getAssetCurrencySymbol(c) === '€' ? 'EUR' : 'USD';
    }}

    function createTopPickCardHtml(c, sigType) {{
      const badgeBorder = sigType === 'LONG' ? 'border-emerald-500/30' : 'border-rose-500/30';
      const scoreColor = sigType === 'LONG' ? 'text-emerald-400' : 'text-rose-400';
      const sym = c.symbol || '';
      const name = c.name || sym;
      const score = c.score || 0;
      const setup = c.setup_name || 'Setup';
      const currSym = getAssetCurrencySymbol(c);
      const price = formatNumber(c.price || 0);
      const entry = (c.entry_range && c.entry_range.length === 2) ? `${{formatNumber(c.entry_range[0])}} - ${{formatNumber(c.entry_range[1])}} ${{currSym}}` : '-';
      const sl = (c.stop_loss !== null && c.stop_loss !== undefined) ? `${{formatNumber(c.stop_loss)}} ${{currSym}}` : '-';
      const tp2 = (c.take_profit_2 !== null && c.take_profit_2 !== undefined) ? `${{formatNumber(c.take_profit_2)}} ${{currSym}}` : '-';
      const crv = c.crv || '-';

      return `
        <div class="p-3.5 rounded-xl bg-slate-950/70 border ${{badgeBorder}} hover:border-slate-600 transition flex flex-col gap-2">
          <div class="flex items-center justify-between">
            <div class="min-w-0">
              <span class="font-bold text-white text-xs sm:text-sm truncate block">${{name}}</span>
              <span class="font-mono text-[10px] text-slate-400">${{sym}}</span>
            </div>
            <div class="text-right shrink-0">
              <span class="font-mono font-bold text-xs ${{scoreColor}}">${{score}}% Score</span>
              <span class="block text-[10px] font-mono text-slate-400">${{price}} ${{currSym}}</span>
            </div>
          </div>
          <div class="grid grid-cols-3 gap-1.5 text-[10px] font-mono bg-slate-900/60 p-2 rounded-lg border border-slate-800">
            <div><span class="text-slate-500 block">Entry:</span><span class="text-slate-200 font-semibold truncate block">${{entry}}</span></div>
            <div><span class="text-slate-500 block">SL:</span><span class="text-rose-400 font-semibold truncate block">${{sl}}</span></div>
            <div><span class="text-slate-500 block">TP2 / CRV:</span><span class="text-cyan-400 font-semibold truncate block">${{tp2}} (${{crv}})</span></div>
          </div>
          <div class="flex items-center justify-between pt-1 border-t border-slate-800/60">
            <span class="text-[10px] text-slate-400 truncate max-w-[220px]">${{setup}}</span>
            <button onclick="openDetailModal('${{sym}}')" class="text-[11px] font-bold text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition cursor-pointer">
              Multi-Timeframe Details →
            </button>
          </div>
        </div>
      `;
    }}

    function renderTopPicksForWatchlist(wl) {{
      const longsContainer = document.getElementById('top-longs-container');
      const shortsContainer = document.getElementById('top-shorts-container');
      const longsTitle = document.getElementById('top-longs-title');
      const shortsTitle = document.getElementById('top-shorts-title');
      const longsSub = document.getElementById('top-longs-subtitle');
      const shortsSub = document.getElementById('top-shorts-subtitle');

      if (!longsContainer || !shortsContainer) return;

      const wlLabel = (wl === 'ALL') ? 'Alle Listen' : wl;
      if (longsTitle) longsTitle.innerText = `🟢 Top Long Setups (${{wlLabel}})`;
      if (shortsTitle) shortsTitle.innerText = `🔴 Top Short Setups (${{wlLabel}})`;
      if (longsSub) longsSub.innerText = (wl === 'ALL') ? 'Beste Long Confluence' : `${{wl}} Top Longs`;
      if (shortsSub) shortsSub.innerText = (wl === 'ALL') ? 'Stärkste Reversal-Divergenzen' : `${{wl}} Top Shorts`;

      const pool = (wl === 'ALL') 
        ? currentData.assets 
        : currentData.assets.filter(a => a.watchlists && a.watchlists.includes(wl));

      const topLongs = pool
        .filter(a => a.signal === 'LONG')
        .sort((a, b) => (b.score || 0) - (a.score || 0))
        .slice(0, 3);

      const topShorts = pool
        .filter(a => a.signal === 'SHORT')
        .sort((a, b) => (b.score || 0) - (a.score || 0))
        .slice(0, 3);

      longsContainer.innerHTML = topLongs.length > 0 
        ? topLongs.map(c => createTopPickCardHtml(c, 'LONG')).join('')
        : `<p class="text-xs text-slate-500 italic p-4 text-center bg-slate-950/40 rounded-xl border border-slate-800/60">Aktuell keine aktiven Long-Setups in ${{wlLabel}}.</p>`;

      shortsContainer.innerHTML = topShorts.length > 0 
        ? topShorts.map(c => createTopPickCardHtml(c, 'SHORT')).join('')
        : `<p class="text-xs text-slate-500 italic p-4 text-center bg-slate-950/40 rounded-xl border border-slate-800/60">Aktuell keine aktiven Short-Setups in ${{wlLabel}}.</p>`;
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
        // TradingView Watchlist
        if (activeWatchlist !== 'ALL' && !(a.watchlists && a.watchlists.includes(activeWatchlist))) return false;
        // Search
        if (query) {{
          const matchSym = a.symbol.toLowerCase().includes(query);
          const matchName = a.name.toLowerCase().includes(query);
          const matchCat = a.category.toLowerCase().includes(query);
          const matchWl = a.watchlists && a.watchlists.some(w => w.toLowerCase().includes(query));
          if (!matchSym && !matchName && !matchCat && !matchWl) return false;
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

    function formatUpdateTime(isoStr, strFallback) {{
      if (!isoStr && !strFallback) return 'Live';
      try {{
        if (isoStr) {{
          const dt = new Date(isoStr);
          if (!isNaN(dt.getTime())) {{
            const now = new Date();
            const diffMs = now.getTime() - dt.getTime();
            const diffMins = Math.floor(diffMs / 60000);
            if (diffMins < 1) return 'Gerade eben';
            if (diffMins < 60) return `vor ${{diffMins}}m`;
            return dt.toLocaleTimeString('de-DE', {{ hour: '2-digit', minute: '2-digit' }}) + ' Uhr';
          }}
        }}
        if (strFallback) return strFallback;
      }} catch (e) {{}}
      return 'Live';
    }}

    function formatTimeExact(isoStr, strFallback) {{
      if (!isoStr && !strFallback) return 'Live';
      try {{
        if (isoStr) {{
          const dt = new Date(isoStr);
          if (!isNaN(dt.getTime())) {{
            return dt.toLocaleString('de-DE', {{ 
              day: '2-digit', 
              month: '2-digit', 
              hour: '2-digit', 
              minute: '2-digit', 
              second: '2-digit' 
            }}) + ' CET';
          }}
        }}
        if (strFallback) return strFallback;
      }} catch (e) {{}}
      return 'Live';
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

        // Market Gatekeeper Badge
        const mState = a.market_state || {{ status: 'OPEN', status_text: 'Aktiv', session_name: 'Markt aktiv' }};
        let marketBadgeHtml = '';
        if (mState.status === 'OPEN') {{
          marketBadgeHtml = `<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-medium bg-emerald-500/15 text-emerald-300 border border-emerald-500/30" title="${{mState.session_name || 'Markt geöffnet'}}"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>${{mState.status_text || 'Offen'}}</span>`;
        }} else if (mState.status === 'PRE_MARKET') {{
          marketBadgeHtml = `<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-medium bg-amber-500/15 text-amber-300 border border-amber-500/30" title="${{mState.session_name || 'Vorbörse aktiv'}}"><span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>${{mState.status_text || 'Vorbörse'}}</span>`;
        }} else {{
          marketBadgeHtml = `<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-medium bg-slate-800/90 text-slate-400 border border-slate-700/60" title="${{mState.session_name || 'Markt pausiert / geschlossen'}}"><span class="w-1.5 h-1.5 rounded-full bg-slate-500"></span>${{mState.status_text || 'Pausiert'}}</span>`;
        }}

        const currSym = getAssetCurrencySymbol(a);
        const currCode = getAssetCurrencyCode(a);

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
                <div class="flex items-center gap-2 mt-1">
                  <span class="text-[11px] text-slate-400">${{a.category}}</span>
                  ${{marketBadgeHtml}}
                </div>
              </div>
              <div class="text-right">
                <span class="px-2 py-0.5 rounded text-xs font-mono font-bold border ${{badgeColor}}">
                  ${{a.signal}}
                </span>
                <span class="block text-[11px] font-mono text-slate-400 mt-1">${{a.score}}% Score</span>
              </div>
            </div>

            <!-- Price & Core Metrics -->
            <div class="mt-3 pb-3 border-b border-slate-800/60">
              <div class="flex items-baseline justify-between">
                <span class="font-mono text-lg font-bold text-white">${{formatNumber(a.price)}} <span class="text-xs text-slate-400 font-normal">${{currCode}}</span></span>
                <div class="flex items-center gap-1.5 text-xs font-mono">
                  <span class="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">RSI: <span class="${{rsiColor}}">${{rsiVal}}</span></span>
                  ${{hasBullDiv ? '<span class="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 text-[10px]">Bull Div</span>' : ''}}
                  ${{hasBearDiv ? '<span class="px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-300 border border-rose-500/20 text-[10px]">Bear Div</span>' : ''}}
                </div>
              </div>
              <div class="flex items-center justify-between text-[10px] font-mono text-slate-400 mt-1">
                <span class="flex items-center gap-1" title="TradingView Live-Quote Stand"><span class="text-indigo-400">⏱️</span> Stand: ${{formatUpdateTime(a.last_price_update, a.last_price_update_str)}}</span>
                ${{a.change_pct !== undefined ? `<span class="${{a.change_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}} font-semibold">${{a.change_pct >= 0 ? '+' : ''}}${{Number(a.change_pct).toFixed(2)}}% 24h</span>` : ''}}
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
                <span class="text-white font-semibold truncate block">${{formatNumber(a.entry_range[0])}} ${{currSym}}</span>
              </div>
              <div>
                <span class="text-slate-400 block text-[10px]">Stop-Loss</span>
                <span class="text-rose-400 font-semibold truncate block">${{formatNumber(a.stop_loss)}} ${{currSym}}</span>
              </div>
              <div>
                <span class="text-slate-400 block text-[10px]">TP2 (CRV)</span>
                <span class="text-emerald-400 font-semibold truncate block">${{formatNumber(a.take_profit_2)}} ${{currSym}} <span class="text-[10px] text-slate-400">(${{a.crv}}:1)</span></span>
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
            <div class="flex items-center gap-2">
              <span class="font-bold text-white text-xs">${{a.name}}</span>
              ${{marketBadgeHtml}}
            </div>
            <div class="text-[10px] text-slate-400">${{a.symbol}}</div>
          </td>
          <td class="p-3">
            <span class="px-2 py-0.5 rounded text-[11px] font-bold border ${{badgeColor}}">${{a.signal}}</span>
          </td>
          <td class="p-3 font-semibold text-slate-200">${{a.score}}%</td>
          <td class="p-3">
            <div class="text-white font-bold">${{formatNumber(a.price)}} ${{currSym}}</div>
            <div class="text-[9px] text-slate-400 font-mono mt-0.5">⏱️ ${{formatUpdateTime(a.last_price_update, a.last_price_update_str)}}</div>
          </td>
          <td class="p-3 text-slate-300">${{d1 ? d1.trend : '-'}}</td>
          <td class="p-3 ${{rsiColor}}">${{rsiVal}}</td>
          <td class="p-3 max-w-xs truncate text-slate-300">
            <div class="flex items-center gap-1.5">
              <span class="text-indigo-300 font-semibold truncate">${{a.setup_name}}</span>
              <button onclick="event.stopPropagation(); openHypothesesModal('${{a.setup_name}}')" class="px-1.5 py-0.5 rounded bg-indigo-500/10 hover:bg-indigo-500/30 text-indigo-300 hover:text-white border border-indigo-500/20 text-[9px] font-semibold transition shrink-0 cursor-pointer" title="Setup-Hypothese erklären">
                💡 Info
              </button>
            </div>
            <span class="block text-[10px] text-slate-400">Entry: ${{formatNumber(a.entry_range[0])}} ${{currSym}} | SL: ${{formatNumber(a.stop_loss)}} ${{currSym}}</span>
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

      ['1h', '4h', '1D', '3D', '1W'].forEach(t => {{
        const btn = document.getElementById('btn-chart-tf-' + t);
        if (btn) {{
          if (t === tf) {{
            btn.className = 'px-2.5 py-1 rounded text-xs font-mono font-bold bg-indigo-600 text-white shadow-sm shadow-indigo-500/30';
          }} else {{
            btn.className = 'px-2.5 py-1 rounded text-xs font-mono font-semibold bg-transparent text-slate-400 hover:text-white hover:bg-slate-800' + (btn.classList.contains('hidden') ? ' hidden' : '');
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
      const btn3d = document.getElementById('btn-chart-tf-3D');
      if (btn3d) {{
        if (a.timeframes && a.timeframes['3D']) {{
          btn3d.classList.remove('hidden');
        }} else {{
          btn3d.classList.add('hidden');
        }}
      }}
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

      // Market State in Modal Header
      const mState = a.market_state || {{ status: 'OPEN', status_text: 'Aktiv', session_name: 'Markt aktiv' }};
      const mStateElem = document.getElementById('modal-market-state');
      if (mStateElem) {{
        if (mState.status === 'OPEN') {{
          mStateElem.className = 'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-mono font-medium bg-emerald-500/15 text-emerald-300 border border-emerald-500/30';
          mStateElem.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>${{mState.session_name || 'Offen'}}`;
        }} else if (mState.status === 'PRE_MARKET') {{
          mStateElem.className = 'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-mono font-medium bg-amber-500/15 text-amber-300 border border-amber-500/30';
          mStateElem.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>${{mState.session_name || 'Vorbörse'}}`;
        }} else {{
          mStateElem.className = 'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-mono font-medium bg-slate-800 text-slate-400 border border-slate-700/60';
          mStateElem.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-slate-500"></span>${{mState.session_name || 'Pausiert (Geschlossen)'}}`;
        }}
      }}

      const modalCurrSym = getAssetCurrencySymbol(a);
      const modalCurrCode = getAssetCurrencyCode(a);

      // Active Position Check & Highlight in Modal
      const userPositions = getUserPositions();
      const authUser = getAuthenticatedUser();
      const activePos = userPositions.find(p => {{
        const match = (p.symbol === symbol || p.symbol.endsWith(':' + symbol) || symbol.endsWith(':' + p.symbol));
        if (!match) return false;
        if (authUser && authUser.role !== 'admin') {{
          return (p.user_name && p.user_name.toLowerCase() === (authUser.username || '').toLowerCase()) || (p.user_id && String(p.user_id) === String(authUser.id));
        }}
        return true;
      }});

      const posBox = document.getElementById('modal-user-pos-box');
      if (posBox) {{
        if (activePos) {{
          const isL = activePos.direction === 'LONG';
          const levP = Number(activePos.leverage) || 1;
          const entP = Number(activePos.entry_price) || a.price;
          const curP = Number(a.price) || entP;
          const rawP = isL ? ((curP - entP) / entP) * 100 : ((entP - curP) / entP) * 100;
          const lPnl = rawP * levP;
          const pCol = lPnl >= 0 ? 'text-emerald-400' : 'text-rose-400';
          const bCol = isL ? 'emerald' : 'rose';
          const recAction = (activePos.recommendation && activePos.recommendation.action) || 'HALTEN';

          posBox.innerHTML = `
            <div class="p-3.5 rounded-xl bg-indigo-950/70 border border-indigo-500/50 flex flex-wrap items-center justify-between gap-3 shadow-lg shadow-indigo-950/40">
              <div class="flex items-center gap-2.5 flex-wrap">
                <span class="px-2.5 py-1 rounded text-xs font-bold uppercase tracking-wider bg-${{bCol}}-500/20 text-${{bCol}}-400 border border-${{bCol}}-500/40 flex items-center gap-1">
                  <span>📍</span>
                  <span>DEINE POSITION: ${{activePos.direction}} ${{levP}}x</span>
                </span>
                <span class="text-xs font-mono text-slate-300">Einstieg: <strong class="text-white">${{entP.toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}} ${{modalCurrSym}}</strong></span>
                <span class="text-xs font-mono text-slate-400">Live: <strong class="text-white">${{curP.toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}} ${{modalCurrSym}}</strong></span>
                ${{activePos.user_name ? `<span class="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-indigo-300 border border-slate-700">👤 @${{activePos.user_name}}</span>` : ''}}
              </div>
              <div class="flex items-center gap-2">
                <span class="text-xs font-mono font-bold ${{pCol}}">PnL: ${{lPnl >= 0 ? '+' : ''}}${{lPnl.toFixed(2)}}%</span>
                <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                  ${{recAction}}
                </span>
              </div>
            </div>
          `;
          posBox.classList.remove('hidden');
        }} else {{
          posBox.classList.add('hidden');
        }}
      }}

      // Trade Plan Banner
      const plan = document.getElementById('modal-trade-plan');
      plan.innerHTML = `
        <div>
          <span class="text-slate-400 block text-[11px]">Aktueller Kurs</span>
          <span class="text-white font-bold text-sm">${{formatNumber(a.price)}} ${{modalCurrCode}}</span>
          <span class="text-[10px] text-slate-400 block font-mono mt-0.5">⏱️ Stand: ${{formatTimeExact(a.last_price_update, a.last_price_update_str)}}</span>
        </div>
        <div>
          <span class="text-slate-400 block text-[11px]">Empfohlene Entry-Zone</span>
          <span class="text-emerald-300 font-bold text-sm">${{formatNumber(a.entry_range[0])}} - ${{formatNumber(a.entry_range[1])}} ${{modalCurrSym}}</span>
        </div>
        <div>
          <span class="text-slate-400 block text-[11px]">Stop-Loss (Invalidierung)</span>
          <span class="text-rose-400 font-bold text-sm">${{formatNumber(a.stop_loss)}} ${{modalCurrSym}}</span>
        </div>
        <div>
          <span class="text-slate-400 block text-[11px]">Take-Profit 1 & 2 (CRV)</span>
          <span class="text-cyan-400 font-bold text-sm">${{formatNumber(a.take_profit_2)}} ${{modalCurrSym}} (${{a.crv}}:1)</span>
        </div>
      `;

      // Timeframes Matrix
      const tfGrid = document.getElementById('modal-timeframes-grid');
      tfGrid.innerHTML = '';

      ['1W', '3D', '1D', '4h', '1h'].filter(tf => a.timeframes && a.timeframes[tf]).forEach(tf => {{
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
      document.body.style.overflow = 'hidden';
    }}

    function closeDetailModal() {{
      const m = document.getElementById('detail-modal');
      if (m) m.classList.add('hidden');
      if (!isAnyModalOpen()) document.body.style.overflow = '';
    }}

    // ==========================================
    // 🔔 Alerts Modal Handlers
    // ==========================================
    function openAlertsModal() {{
      const m = document.getElementById('alerts-modal');
      if (m) {{
        m.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
      }}
    }}

    function closeAlertsModal() {{
      const m = document.getElementById('alerts-modal');
      if (m) m.classList.add('hidden');
      if (!isAnyModalOpen()) document.body.style.overflow = '';
    }}

    // ==========================================
    // 💡 Hypothesen Guide Modal Handlers
    // ==========================================
    function openHypothesesModal(highlight) {{
      const m = document.getElementById('hypotheses-modal');
      if (m) {{
        m.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
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
      if (!isAnyModalOpen()) document.body.style.overflow = '';
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
    // ⏱️ Nächster Scan Countdown (Stündlicher Market Gatekeeper: Minute :05)
    // ==========================================
    function updateNextScanCountdown() {{
      const now = new Date();
      const candidate = new Date(now.getTime());

      if (candidate.getMinutes() < 5) {{
        candidate.setMinutes(5, 0, 0);
      }} else {{
        candidate.setHours(candidate.getHours() + 1);
        candidate.setMinutes(5, 0, 0);
      }}

      const diff = Math.max(0, candidate.getTime() - now.getTime());
      const totalSec = Math.floor(diff / 1000);
      const mins = Math.floor(totalSec / 60);
      const secs = totalSec % 60;

      const pad = (n) => String(n).padStart(2, '0');
      const el = document.getElementById('next-scan-countdown');

      if (totalSec <= 0) {{
        if (el) el.innerText = 'Scan läuft... 🔄';
      }} else {{
        if (el) el.innerText = `${{pad(mins)}}m ${{pad(secs)}}s`;
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
          const authCfg = newData.auth_config || (currentData && currentData.auth_config) || (typeof EMBEDDED_DATABASE !== 'undefined' && EMBEDDED_DATABASE.auth_config);
          currentData = newData;
          if (authCfg && !currentData.auth_config) {{
            currentData.auth_config = authCfg;
          }}
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
        if (isAnyModalOpen()) {{
          isPulling = false;
          return;
        }}
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

    // ==========================================
    // 🏛️ KI High-Conviction Modell-Portfolio
    // ==========================================
    function renderPortfolioSection() {{
      const port = currentData.portfolio || {{}};
      const metrics = port.metrics || {{}};
      const activeTrades = port.active_trades || [];
      const closedTrades = port.closed_trades || [];
      const memory = currentData.trade_memory || {{}};
      const learnings = memory.learnings || [];

      // KPIs
      const levPnl = metrics.total_leveraged_pnl_pct || 0;
      const rawPnl = metrics.total_pnl_pct || 0;
      const winRate = metrics.win_rate_pct || 0;

      const levElem = document.getElementById('port-metric-lev-pnl');
      if (levElem) {{
        levElem.textContent = (levPnl >= 0 ? '+' : '') + levPnl.toFixed(1) + '%';
        levElem.className = 'font-bold text-sm ' + (levPnl >= 0 ? 'text-emerald-400' : 'text-rose-400');
      }}

      const rawElem = document.getElementById('port-metric-raw-pnl');
      if (rawElem) {{
        rawElem.textContent = (rawPnl >= 0 ? '+' : '') + rawPnl.toFixed(1) + '%';
        rawElem.className = 'font-bold text-sm ' + (rawPnl >= 0 ? 'text-slate-200' : 'text-rose-300');
      }}

      const wrElem = document.getElementById('port-metric-winrate');
      if (wrElem) {{
        wrElem.textContent = winRate.toFixed(1) + '% (' + (metrics.win_count || 0) + 'W / ' + (metrics.loss_count || 0) + 'L)';
      }}

      const cntElem = document.getElementById('port-active-count');
      if (cntElem) cntElem.textContent = activeTrades.length;

      // Active Trades Cards
      const activeContainer = document.getElementById('portfolio-active-trades');
      if (activeContainer) {{
        if (activeTrades.length === 0) {{
          activeContainer.innerHTML = `
            <div class="col-span-full p-4 rounded-xl bg-slate-950/40 border border-slate-800 text-center text-xs text-slate-400">
              Aktuell keine Positionen im KI-Portfolio. Neue Trades werden vollautomatisch bei High-Conviction-Setups (Score ≥ 88%) eröffnet.
            </div>
          `;
        }} else {{
          activeContainer.innerHTML = activeTrades.map(t => {{
            const isLong = t.direction === 'LONG';
            const sigColor = isLong ? 'emerald' : 'rose';
            const pnl = t.unrealized_pnl_pct || 0;
            const levPnl = t.unrealized_pnl_leveraged_pct || 0;
            const pnlColor = levPnl >= 0 ? 'text-emerald-400' : 'text-rose-400';
            const ticker = t.symbol.split(':').pop();

            return `
              <div class="rounded-xl bg-slate-950/80 border border-slate-800/80 p-4 space-y-3 hover:border-slate-700 transition">
                <div class="flex items-start justify-between">
                  <div>
                    <div class="flex items-center gap-1.5">
                      <span class="text-sm font-bold text-white">${{t.name}}</span>
                      <span class="text-xs font-mono text-slate-400">(${{ticker}})</span>
                    </div>
                    <span class="text-[10px] text-slate-500 font-mono">${{t.setup_name || 'SMC Confluence'}}</span>
                  </div>
                  <div class="flex items-center gap-1.5">
                    ${{(t.tranches && t.tranches > 1) ? `<span class="px-2 py-0.5 rounded text-[11px] font-bold font-mono bg-amber-500/20 text-amber-300 border border-amber-500/30" title="Position bei Signalverstärkung aufgestockt">Tranche ${{t.tranches}}/3</span>` : ''}}
                    <span class="px-2 py-0.5 rounded text-[11px] font-bold font-mono bg-${{sigColor}}-500/10 text-${{sigColor}}-400 border border-${{sigColor}}-500/30">
                      ${{t.direction}}
                    </span>
                    <span class="px-2 py-0.5 rounded text-[11px] font-bold font-mono bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                      ${{t.leverage}}x Hebel
                    </span>
                  </div>
                </div>

                <div class="grid grid-cols-2 gap-2 text-xs font-mono bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/60">
                  <div>
                    <span class="text-[10px] text-slate-400 block">Einstieg:</span>
                    <span class="text-slate-200 font-semibold">${{Number(t.entry_price).toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</span>
                  </div>
                  <div class="text-right">
                    <span class="text-[10px] text-slate-400 block">Aktueller Kurs:</span>
                    <span class="text-white font-bold">${{Number(t.current_price).toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</span>
                    <span class="text-[9px] text-slate-400 block font-mono mt-0.5">⏱️ ${{formatUpdateTime(t.last_price_update, t.last_price_update_str)}}</span>
                  </div>
                  <div class="pt-1 border-t border-slate-800/80">
                    <span class="text-[10px] text-slate-400 block">Performance:</span>
                    <span class="${{pnlColor}} font-extrabold text-sm">${{levPnl >= 0 ? '+' : ''}}${{levPnl.toFixed(2)}}%</span>
                    <span class="text-[10px] text-slate-400 block">(${{pnl >= 0 ? '+' : ''}}${{pnl.toFixed(2)}}% Basis)</span>
                  </div>
                  <div class="pt-1 border-t border-slate-800/80 text-right">
                    <span class="text-[10px] text-slate-400 block">Haltedauer:</span>
                    <span class="text-indigo-300 font-semibold">${{t.holding_days ? t.holding_days + ' Tage' : (t.holding_hours || 0) + ' Std.'}}</span>
                  </div>
                </div>

                <div class="text-[11px] text-slate-300 bg-slate-900/40 p-2.5 rounded-lg border border-slate-800/40">
                  <span class="text-emerald-400 font-semibold block text-[10px] uppercase">Einstiegsgrund:</span>
                  <p class="leading-relaxed text-[11px]">${{t.entry_reason || t.analyst_note || 'Multi-Timeframe SMC-Konfluenz'}}</p>
                </div>

                <div class="flex items-center justify-between text-[10px] font-mono text-slate-400 pt-1 border-t border-slate-800/60">
                  <span>SL: ${{Number(t.stop_loss).toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</span>
                  <span>TP2: ${{Number(t.take_profit_2).toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</span>
                  <button onclick="openDetailModal('${{t.symbol}}')" class="text-indigo-400 hover:text-indigo-300 font-bold transition">Chart →</button>
                </div>
              </div>
            `;
          }}).join('');
        }}
      }}

      // Gedächtnis Summary & Accordion
      const memSum = document.getElementById('memory-status-summary');
      if (memSum) {{
        memSum.textContent = learnings.length + ' Lerneinheiten im Gedächtnis &bull; ' + closedTrades.length + ' geschlossene Trades historisch';
      }}

      const learnList = document.getElementById('memory-learnings-list');
      if (learnList) {{
        if (learnings.length === 0) {{
          learnList.innerHTML = `<p class="text-xs text-slate-400 italic">Noch keine geschlossenen Trades. Das System lernt automatisch aus jedem Trade-Ausstieg.</p>`;
        }} else {{
          learnList.innerHTML = learnings.map(l => `
            <div class="p-3 rounded-xl bg-slate-900/90 border border-slate-800 text-xs text-slate-300 space-y-1">
              <div class="flex items-center justify-between">
                <span class="font-bold font-mono ${{l.result === 'WIN' ? 'text-emerald-400' : 'text-rose-400'}}">${{l.result === 'WIN' ? '✅ Erfolg' : '❌ Verlust'}} (${{l.pnl_leveraged >= 0 ? '+' : ''}}${{l.pnl_leveraged}}%)</span>
                <span class="text-[10px] text-slate-500 font-mono">${{l.setup_name || 'Trade'}}</span>
              </div>
              <p class="text-[11px] leading-relaxed text-slate-300">${{l.text}}</p>
            </div>
          `).join('');
        }}
      }}

      // Geschlossene Trades Historie
      const closedList = document.getElementById('portfolio-closed-trades');
      if (closedList) {{
        if (closedTrades.length === 0) {{
          closedList.innerHTML = `<p class="text-xs text-slate-400 italic">Keine geschlossenen Trades vorhanden.</p>`;
        }} else {{
          closedList.innerHTML = `
            <div class="pt-3 border-t border-slate-800 space-y-2">
              <span class="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">📜 Geschlossene Trades Historie (${{closedTrades.length}}):</span>
              <div class="space-y-1.5">
                ${{closedTrades.slice().reverse().map(ct => {{
                  const isWin = (ct.realized_pnl_leveraged_pct !== undefined ? ct.realized_pnl_leveraged_pct : (ct.realized_pnl_pct || 0)) >= 0;
                  const levPnl = ct.realized_pnl_leveraged_pct !== undefined ? ct.realized_pnl_leveraged_pct : (ct.realized_pnl_pct || 0);
                  const pCol = isWin ? 'text-emerald-400' : 'text-rose-400';
                  const exitTime = ct.exit_time ? new Date(ct.exit_time).toLocaleString('de-DE', {{ day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }}) : '-';
                  return `
                    <div class="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800 flex items-center justify-between text-xs font-mono">
                      <div class="flex items-center gap-2">
                        <span class="font-bold text-white">${{ct.name || ct.symbol}}</span>
                        <span class="px-1.5 py-0.5 rounded text-[10px] font-bold ${{ct.direction === 'LONG' ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30' : 'bg-rose-500/10 text-rose-300 border border-rose-500/30'}}">${{ct.direction}}</span>
                        <span class="text-[10px] text-slate-400 hidden sm:inline">${{ct.exit_reason || 'Exit'}}</span>
                      </div>
                      <div class="flex items-center gap-3">
                        <span class="text-[10px] text-slate-400">⏱️ ${{exitTime}}</span>
                        <span class="font-bold ${{pCol}}">${{levPnl >= 0 ? '+' : ''}}${{Number(levPnl).toFixed(2)}}%</span>
                      </div>
                    </div>
                  `;
                }}).join('')}}
              </div>
            </div>
          `;
        }}
      }}
    }}

    function toggleMemoryAccordion() {{
      const content = document.getElementById('memory-accordion-content');
      const icon = document.getElementById('memory-accordion-icon');
      if (!content) return;
      if (content.classList.contains('hidden')) {{
        content.classList.remove('hidden');
        if (icon) icon.textContent = '▲';
      }} else {{
        content.classList.add('hidden');
        if (icon) icon.textContent = '▼';
      }}
    }}

    // ==========================================
    // 👤 Eigene Nutzer-Positionen Management
    // ==========================================
    let currentPosDirection = 'LONG';
    let currentAuthUser = null;
    let currentAdminPosFilter = 'all';

    function getAuthenticatedUser() {{
      if (currentAuthUser) return currentAuthUser;
      try {{
        const raw = localStorage.getItem('tg_user');
        if (raw) currentAuthUser = JSON.parse(raw);
      }} catch (e) {{}}
      return currentAuthUser;
    }}

    function checkUserRole(user) {{
      if (!user) return null;
      const authCfg = (currentData && currentData.auth_config) || (typeof EMBEDDED_DATABASE !== 'undefined' && EMBEDDED_DATABASE.auth_config) || {{}};
      const admins = authCfg.admin_usernames || ['Bdc_Gumb_Drop', 'bdc_gumb_drop'];
      const adminIds = (authCfg.admin_chat_ids || ['15231751']).map(String);
      const uname = (user.username || '').toLowerCase().replace(/^@/, '');
      const uid = String(user.id || '');

      if (admins.some(a => a.toLowerCase().replace(/^@/, '') === uname) || adminIds.includes(uid)) {{
        return 'admin';
      }}

      const authUsers = authCfg.authorized_users || {{}};
      for (const [k, udata] of Object.entries(authUsers)) {{
        const keyUname = k.toLowerCase().replace(/^@/, '');
        const udataUname = ((udata && udata.name) || '').toLowerCase().replace(/^@/, '');
        const udataChatId = String((udata && udata.chat_id) || '');
        if ((uname && (keyUname === uname || udataUname === uname)) || (uid && udataChatId && uid === udataChatId)) {{
          return (udata && udata.role) || 'trader';
        }}
      }}
      return null;
    }}

    window.handleTelegramLogin = function(user) {{
      if (!user) return;
      const role = checkUserRole(user);
      user.role = role;

      if (!role) {{
        const errBox = document.getElementById('tg-auth-error');
        if (errBox) {{
          errBox.className = 'p-3.5 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-300 text-xs space-y-2 mt-3 text-left';
          errBox.innerHTML = `
            <div class="font-bold text-rose-400 flex items-center gap-1.5">
              <span>⛔</span> Zugriff nicht freigeschaltet
            </div>
            <p>Dein Telegram-Account <strong>@${{user.username || user.first_name || 'Unbekannt'}}</strong> ist in diesem System noch nicht autorisiert.</p>
            <p class="text-[11px] text-slate-400">Bitte öffne <a href="https://t.me/aitradeanalystbot" target="_blank" class="text-indigo-400 font-bold underline">@aitradeanalystbot</a> in Telegram und sende <code>/start</code>. Sobald der Administrator dich freigeschaltet hat, lade diese Seite neu.</p>
            <button onclick="logoutTelegram()" class="mt-2 w-full py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs transition cursor-pointer">
              Mit anderem Account anmelden
            </button>
          `;
          errBox.classList.remove('hidden');
        }}
        return;
      }}

      currentAuthUser = user;
      try {{
        localStorage.setItem('tg_user', JSON.stringify(user));
      }} catch (e) {{}}

      applyAuthenticatedState(user);
    }};

    window.onTelegramAuth = window.handleTelegramLogin;

    function switchDashboardTab(tabId) {{
      const user = getAuthenticatedUser();
      const isAdmin = user && (user.role === 'admin' || checkUserRole(user) === 'admin');

      if (tabId === 'admin' && !isAdmin) {{
        tabId = 'positions';
      }}

      const tabs = ['positions', 'topsetups', 'scanner', 'admin'];
      tabs.forEach(t => {{
        const pane = document.getElementById('tab-content-' + t);
        if (pane) {{
          if (t === tabId) {{
            pane.classList.remove('hidden');
          }} else {{
            pane.classList.add('hidden');
          }}
        }}

        // Desktop nav button state
        const deskBtn = document.getElementById('nav-tab-' + t);
        if (deskBtn) {{
          if (t === tabId) {{
            if (t === 'admin') {{
              deskBtn.className = 'dashboard-nav-btn flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold transition bg-amber-500 text-slate-950 shadow-md shadow-amber-500/20 cursor-pointer';
            }} else {{
              deskBtn.className = 'dashboard-nav-btn flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold transition bg-indigo-600 text-white shadow-md shadow-indigo-600/30 cursor-pointer';
            }}
          }} else {{
            if (t === 'admin') {{
              deskBtn.className = 'dashboard-nav-btn flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold transition border border-amber-500/30 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20 cursor-pointer';
            }} else {{
              deskBtn.className = 'dashboard-nav-btn flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold transition text-slate-400 hover:text-white hover:bg-slate-800/60 cursor-pointer';
            }}
          }}
        }}

        // Mobile bottom nav button state
        const mobBtn = document.getElementById('mob-tab-' + t);
        if (mobBtn) {{
          if (t === tabId) {{
            mobBtn.className = t === 'admin'
              ? 'mob-nav-btn flex flex-col items-center justify-center py-1 px-2.5 rounded-xl transition text-amber-400 font-bold active:scale-95 bg-amber-500/10 cursor-pointer'
              : 'mob-nav-btn flex flex-col items-center justify-center py-1 px-2.5 rounded-xl transition text-indigo-400 font-bold active:scale-95 bg-indigo-500/10 cursor-pointer';
          }} else {{
            mobBtn.className = t === 'admin'
              ? 'mob-nav-btn flex flex-col items-center justify-center py-1 px-2.5 rounded-xl transition text-amber-300/60 active:scale-95 cursor-pointer'
              : 'mob-nav-btn flex flex-col items-center justify-center py-1 px-2.5 rounded-xl transition text-slate-400 active:scale-95 cursor-pointer';
          }}
        }}
      }});

      try {{
        sessionStorage.setItem('active_tab', tabId);
      }} catch (e) {{}}

      window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }}

    function triggerSmartRefresh() {{
      const user = getAuthenticatedUser();
      const isAdmin = user && (user.role === 'admin' || checkUserRole(user) === 'admin');
      if (isAdmin) {{
        triggerManualRefresh();
      }} else {{
        // Trader: Instant UI Refresh from loaded data
        const label = document.getElementById('refresh-label');
        const icon = document.getElementById('refresh-icon');
        if (icon) icon.classList.add('animate-spin');
        if (label) label.innerText = 'Lade...';
        setTimeout(() => {{
          renderUserPositions();
          applyFilters();
          if (icon) icon.classList.remove('animate-spin');
          if (label) label.innerText = 'Aktuell';
          if (typeof showToast === 'function') showToast('Dashboard erfolgreich aktualisiert!');
          setTimeout(() => {{ if (label) label.innerText = 'Refresh'; }}, 2000);
        }}, 350);
      }}
    }}

    function renderAdminUsersList() {{
      const container = document.getElementById('admin-users-list');
      if (!container || !currentData || !currentData.auth_config) return;
      const cfg = currentData.auth_config;
      const users = cfg.authorized_users || {{}};
      const admins = cfg.admin_usernames || ['Bdc_Gumb_Drop'];
      let html = '';

      admins.forEach(adm => {{
        html += `
          <div class="p-3.5 rounded-xl bg-slate-950/80 border border-amber-500/30 flex items-center justify-between">
            <div class="flex items-center gap-2.5">
              <span class="w-8 h-8 rounded-lg bg-amber-500/20 text-amber-300 flex items-center justify-center text-sm font-bold">👑</span>
              <div>
                <div class="text-xs font-bold text-white flex items-center gap-1.5">
                  <span>@${{adm}}</span>
                  <span class="px-1.5 py-0.2 rounded text-[9px] bg-amber-500/20 text-amber-300 font-mono font-bold">MASTER-ADMIN</span>
                </div>
                <span class="text-[10px] text-slate-400">Vollzugriff: Quota Pool, Modell-Portfolio, Pi Live-Scan</span>
              </div>
            </div>
            <span class="text-[10px] font-mono text-emerald-400 font-bold">Aktiv</span>
          </div>
        `;
      }});

      Object.keys(users).forEach(uname => {{
        if (admins.map(a => a.toLowerCase()).includes(uname.toLowerCase())) return;
        const udata = users[uname];
        html += `
          <div class="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 flex items-center justify-between">
            <div class="flex items-center gap-2.5">
              <span class="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-300 flex items-center justify-center text-sm font-bold">👤</span>
              <div>
                <div class="text-xs font-bold text-white flex items-center gap-1.5">
                  <span>@${{uname}}</span>
                  <span class="px-1.5 py-0.2 rounded text-[9px] bg-indigo-500/20 text-indigo-300 font-mono font-bold">${{(udata.role || 'TRADER').toUpperCase()}}</span>
                </div>
                <span class="text-[10px] text-slate-400">Chat-ID: ${{udata.chat_id || 'unbekannt'}} &bull; Eigene Trades & Marktsignale</span>
              </div>
            </div>
            <span class="text-[10px] font-mono text-slate-400 font-bold">Autorisiert</span>
          </div>
        `;
      }});

      container.innerHTML = html;
    }}

    function applyAuthenticatedState(user) {{
      const gate = document.getElementById('telegram-auth-gate');
      if (gate) gate.classList.add('hidden');

      const badge = document.getElementById('auth-user-badge');
      if (badge) {{
        badge.classList.remove('hidden');
        const nameEl = document.getElementById('auth-user-name');
        const roleEl = document.getElementById('auth-user-role-badge');
        const photoEl = document.getElementById('auth-user-photo');
        const fallbackEl = document.getElementById('auth-user-avatar-fallback');

        if (nameEl) nameEl.innerText = user.username ? '@' + user.username : (user.first_name || 'Trader');
        if (roleEl) {{
          roleEl.innerText = (user.role || 'TRADER').toUpperCase();
          if (user.role === 'admin') {{
            roleEl.className = 'px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30';
          }} else {{
            roleEl.className = 'px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30';
          }}
        }}
        if (user.photo_url && photoEl) {{
          photoEl.src = user.photo_url;
          photoEl.classList.remove('hidden');
          if (fallbackEl) fallbackEl.classList.add('hidden');
        }}
      }}

      // Admin vs Trader Visibility Control
      const isAdmin = user.role === 'admin';
      const navTabAdmin = document.getElementById('nav-tab-admin');
      const mobTabAdmin = document.getElementById('mob-tab-admin');
      const headerQuota = document.getElementById('header-quota-badge');
      const headerEngine = document.getElementById('header-engine-badge');
      const headerTrader = document.getElementById('header-trader-badge');

      if (isAdmin) {{
        if (navTabAdmin) navTabAdmin.classList.remove('hidden');
        if (mobTabAdmin) mobTabAdmin.classList.remove('hidden');
        if (headerQuota) headerQuota.classList.remove('hidden');
        if (headerEngine) headerEngine.classList.remove('hidden');
        if (headerTrader) headerTrader.classList.add('hidden');
        renderAdminUsersList();
      }} else {{
        if (navTabAdmin) navTabAdmin.classList.add('hidden');
        if (mobTabAdmin) mobTabAdmin.classList.add('hidden');
        if (headerQuota) headerQuota.classList.add('hidden');
        if (headerEngine) headerEngine.classList.add('hidden');
        if (headerTrader) headerTrader.classList.remove('hidden');

        // Falls Trader auf admin-Tab steht, zurücksetzen
        const curTab = sessionStorage.getItem('active_tab') || 'positions';
        if (curTab === 'admin') {{
          sessionStorage.setItem('active_tab', 'positions');
        }}
      }}

      const savedTab = sessionStorage.getItem('active_tab') || 'positions';
      switchDashboardTab(savedTab);
      renderUserPositions();
    }}

    function logoutTelegram() {{
      try {{
        localStorage.removeItem('tg_user');
        sessionStorage.removeItem('active_tab');
      }} catch (e) {{}}
      currentAuthUser = null;
      const badge = document.getElementById('auth-user-badge');
      if (badge) badge.classList.add('hidden');
      const errBox = document.getElementById('tg-auth-error');
      if (errBox) errBox.classList.add('hidden');
      const navTabAdmin = document.getElementById('nav-tab-admin');
      if (navTabAdmin) navTabAdmin.classList.add('hidden');
      const mobTabAdmin = document.getElementById('mob-tab-admin');
      if (mobTabAdmin) mobTabAdmin.classList.add('hidden');
      const gate = document.getElementById('telegram-auth-gate');
      if (gate) gate.classList.remove('hidden');
    }}

    function setAdminPosFilter(f) {{
      currentAdminPosFilter = f;
      renderUserPositions();
    }}

    function toggleFallbackLogin() {{
      const c = document.getElementById('fallback-login-container');
      if (c) c.classList.toggle('hidden');
    }}

    function submitFallbackLogin() {{
      const inp = document.getElementById('fallback-username-input');
      if (!inp) return;
      const raw = inp.value.trim().replace(/^@/, '');
      if (!raw) return;

      const dummyUser = {{
        id: 'user_' + raw,
        username: raw,
        first_name: raw
      }};

      const role = checkUserRole(dummyUser);
      if (!role) {{
        const errBox = document.getElementById('tg-auth-error');
        if (errBox) {{
          errBox.className = 'p-3 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-300 text-xs space-y-1 mt-2 text-left';
          errBox.innerHTML = `Der Nutzername <strong>@${{raw}}</strong> ist nicht autorisiert. Bitte öffne <a href="https://t.me/aitradeanalystbot" target="_blank" class="text-indigo-400 underline font-bold">@aitradeanalystbot</a> in Telegram.`;
          errBox.classList.remove('hidden');
        }}
        return;
      }}

      dummyUser.role = role;
      window.handleTelegramLogin(dummyUser);
    }}

    function initAuthOnLoad() {{
      // 1. Erst URL Query-Parameter prüfen (Telegram redirect Mode)
      try {{
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('id') || urlParams.get('username')) {{
          const qUser = {{
            id: urlParams.get('id') || ('user_' + urlParams.get('username')),
            first_name: urlParams.get('first_name') || urlParams.get('username') || 'Trader',
            last_name: urlParams.get('last_name') || '',
            username: urlParams.get('username') || '',
            photo_url: urlParams.get('photo_url') || '',
            auth_date: urlParams.get('auth_date') || '',
            hash: urlParams.get('hash') || ''
          }};
          window.handleTelegramLogin(qUser);
          window.history.replaceState({{}}, document.title, window.location.pathname);
          return;
        }}
      }} catch (e) {{}}

      // 2. Gespeicherten Nutzer prüfen
      const user = getAuthenticatedUser();
      if (user && (user.id || user.username)) {{
        const role = checkUserRole(user);
        if (role) {{
          user.role = role;
          applyAuthenticatedState(user);
          return;
        }}
      }}

      // Nicht eingeloggt -> Gate sichtbar halten
      const gate = document.getElementById('telegram-auth-gate');
      if (gate) gate.classList.remove('hidden');
    }}

    // 1. Bereinige Altlasten (z.B. Demo BTC-Position aus früheren Versionen)
    try {{
      const legacyRaw = localStorage.getItem('tv_user_positions');
      if (legacyRaw) {{
        let legacyList = JSON.parse(legacyRaw);
        legacyList = legacyList.filter(p => {{
          if (!p || !p.symbol) return false;
          const id = (p.id || '').toLowerCase();
          const note = (p.note || '').toLowerCase();
          if (id.includes('dummy') || id.includes('sample') || note.includes('beispiel') || note.includes('initialer demo-trade')) return false;
          return true;
        }});
        localStorage.setItem('tv_user_positions', JSON.stringify(legacyList));
      }}
    }} catch (e) {{}}

    function getUserPositions() {{
      let positions = [];
      let deleted = [];
      try {{
        deleted = JSON.parse(localStorage.getItem('tv_deleted_positions') || '[]');
      }} catch (e) {{}}

      try {{
        const stored = localStorage.getItem('tv_user_positions');
        if (stored) positions = JSON.parse(stored);
      }} catch (e) {{}}

      // Filtere gelöschte & Dummy-Positionen aus dem lokalen Speicher
      positions = positions.filter(p => {{
        if (!p || !p.symbol) return false;
        if (deleted.includes(p.id) || deleted.includes(p.symbol)) return false;
        const note = (p.note || '').toLowerCase();
        const id = (p.id || '').toLowerCase();
        if (id.includes('dummy') || id.includes('sample') || note.includes('beispiel') || note.includes('initialer demo-trade')) return false;
        return true;
      }});

      // Mit Raspberry Pi Server-Positionen mergen (falls vorhanden, aber gelöschte ignorieren)
      if (currentData.user_positions && Array.isArray(currentData.user_positions)) {{
        const validServerPositions = currentData.user_positions.filter(p => {{
          if (!p || !p.symbol) return false;
          if (deleted.includes(p.id) || deleted.includes(p.symbol)) return false;
          const note = (p.note || '').toLowerCase();
          const id = (p.id || '').toLowerCase();
          if (id.includes('dummy') || id.includes('sample') || note.includes('beispiel') || note.includes('initialer demo-trade')) return false;
          return true;
        }});

        const localMap = new Map();
        validServerPositions.forEach(p => localMap.set(p.id || p.symbol, p));
        positions.forEach(p => localMap.set(p.id || p.symbol, p));
        positions = Array.from(localMap.values());
      }}
      return positions;
    }}

    function saveUserPositionsLocally(positions) {{
      try {{
        localStorage.setItem('tv_user_positions', JSON.stringify(positions));
      }} catch (e) {{}}
    }}

    function renderUserPositions() {{
      const container = document.getElementById('user-positions-container');
      if (!container) return;

      const allPositions = getUserPositions();
      const authUser = getAuthenticatedUser();
      let displayPositions = allPositions;

      // Filterung nach Nutzer
      if (authUser && authUser.role !== 'admin') {{
        const myUname = (authUser.username || '').toLowerCase();
        const myUid = String(authUser.id || '');
        displayPositions = allPositions.filter(p => {{
          const pUname = (p.user_name || '').toLowerCase();
          const pUid = String(p.user_id || '');
          return (pUname && pUname === myUname) || (pUid && pUid === myUid);
        }});
      }} else if (authUser && authUser.role === 'admin') {{
        if (currentAdminPosFilter === 'mine') {{
          const myUname = (authUser.username || '').toLowerCase();
          displayPositions = allPositions.filter(p => (p.user_name || '').toLowerCase() === myUname);
        }} else if (currentAdminPosFilter !== 'all') {{
          displayPositions = allPositions.filter(p => (p.user_name || '').toLowerCase() === currentAdminPosFilter.toLowerCase());
        }}
      }}

      // Positionen-Badge in der Segment-Navigation aktualisieren
      const navBadge = document.getElementById('nav-badge-positions');
      if (navBadge) {{
        if (displayPositions.length > 0) {{
          navBadge.innerText = displayPositions.length;
          navBadge.classList.remove('hidden');
        }} else {{
          navBadge.classList.add('hidden');
        }}
      }}

      // Admin Filter Bar
      let adminFilterHtml = '';
      if (authUser && authUser.role === 'admin' && allPositions.length > 0) {{
        const userSet = new Set();
        allPositions.forEach(p => {{ if (p.user_name) userSet.add(p.user_name); }});

        adminFilterHtml = `
          <div class="col-span-full flex items-center gap-1.5 overflow-x-auto no-scrollbar pb-1 text-xs">
            <span class="text-[11px] text-slate-400 font-mono">Ansicht:</span>
            <button onclick="setAdminPosFilter('all')" class="px-2.5 py-1 rounded-lg font-semibold transition cursor-pointer ${{currentAdminPosFilter === 'all' ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-300 hover:text-white'}}">
              Alle Trades (${{allPositions.length}})
            </button>
            <button onclick="setAdminPosFilter('mine')" class="px-2.5 py-1 rounded-lg font-semibold transition cursor-pointer ${{currentAdminPosFilter === 'mine' ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-300 hover:text-white'}}">
              Nur meine
            </button>
            ${{Array.from(userSet).map(u => `
              <button onclick="setAdminPosFilter('${{u}}')" class="px-2.5 py-1 rounded-lg font-semibold transition cursor-pointer ${{currentAdminPosFilter.toLowerCase() === u.toLowerCase() ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-300 hover:text-white'}}">
                @${{u}}
              </button>
            `).join('')}}
          </div>
        `;
      }}

      if (displayPositions.length === 0) {{
        container.innerHTML = adminFilterHtml + `
          <div class="col-span-full p-8 rounded-2xl bg-slate-950/60 border border-slate-800 text-center space-y-3">
            <div class="w-12 h-12 rounded-full bg-indigo-500/10 text-indigo-400 mx-auto flex items-center justify-center text-xl">
              👤
            </div>
            <div>
              <h4 class="text-sm font-bold text-white">Keine aktiven Positionen gefunden</h4>
              <p class="text-xs text-slate-400 mt-1 max-w-md mx-auto">Du hast aktuell keine offenen Trades hinterlegt. Trage hier oder im Telegram-Bot neue Positionen ein, um sie 24/7 überwachen zu lassen.</p>
            </div>
            <button onclick="openPositionsModal()" class="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs transition shadow-md shadow-indigo-600/30 cursor-pointer">
              + Jetzt erste Position eintragen
            </button>
          </div>
        `;
        return;
      }}

      const cardsHtml = displayPositions.map(pos => {{
        const sym = pos.symbol;
        const isLong = pos.direction === 'LONG';
        const sigColor = isLong ? 'emerald' : 'rose';
        const lev = Number(pos.leverage) || 1;
        const entry = Number(pos.entry_price) || 0;
        
        // Aktuellen Live-Kurs aus den gescannten Assets ziehen
        const matched = (currentData.assets || []).find(a => 
          a.symbol === sym || 
          a.symbol.endsWith(':' + sym) || 
          a.symbol.toUpperCase() === sym.toUpperCase() ||
          a.symbol.split(':').pop().toUpperCase() === sym.toUpperCase()
        );
        const curr = matched ? Number(matched.price) : (Number(pos.current_price) || entry);
        
        // Live-PnL frisch berechnen
        const rawPnl = isLong 
          ? (entry > 0 ? ((curr - entry) / entry) * 100 : 0)
          : (entry > 0 ? ((entry - curr) / entry) * 100 : 0);
        const levPnl = rawPnl * lev;
        const pnlColor = levPnl >= 0 ? 'text-emerald-400' : 'text-rose-400';
        
        let rec = pos.recommendation;
        if (!rec || !rec.action) {{
          rec = {{ action: 'BEOBACHTEN', title: 'Position aktiv', message: '24/7 Raspberry Pi Überwachung läuft.', badge_color: 'indigo' }};
        }}
        const ticker = sym.split(':').pop();

        return `
          <div class="rounded-xl bg-slate-950/80 border border-slate-800/90 p-4 space-y-3.5 hover:border-slate-700 transition">
            <div class="flex items-start justify-between">
              <div>
                <div class="flex items-center gap-1.5 flex-wrap">
                  <span class="text-sm font-bold text-white">${{pos.name || sym}}</span>
                  <span class="text-xs font-mono text-slate-400">(${{ticker}})</span>
                  ${{pos.user_name ? `<span class="px-1.5 py-0.5 rounded text-[10px] font-medium bg-indigo-500/10 text-indigo-300 border border-indigo-500/30">👤 ${{pos.user_name}}</span>` : ''}}
                </div>
                <span class="text-[10px] text-slate-500 font-mono">${{sym}}</span>
              </div>

              <div class="flex items-center gap-1.5">
                <span class="px-2 py-0.5 rounded text-[11px] font-bold font-mono bg-${{sigColor}}-500/10 text-${{sigColor}}-400 border border-${{sigColor}}-500/30">
                  ${{pos.direction}}
                </span>
                <span class="px-2 py-0.5 rounded text-[11px] font-bold font-mono bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                  ${{lev}}x
                </span>
                <button onclick="deleteUserPosition('${{pos.id || sym}}')" title="Position schließen / löschen" class="w-6 h-6 rounded bg-slate-900 hover:bg-rose-500/20 text-slate-400 hover:text-rose-400 flex items-center justify-center text-xs transition cursor-pointer">
                  ✕
                </button>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-2 text-xs font-mono bg-slate-900/60 p-2.5 rounded-lg border border-slate-800/60">
              <div>
                <span class="text-[10px] text-slate-400 block">Einstieg:</span>
                <span class="text-slate-200 font-semibold">${{entry.toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</span>
              </div>
              <div class="text-right">
                <span class="text-[10px] text-slate-400 block">Live-Kurs:</span>
                <span class="text-white font-bold">${{curr.toLocaleString('de-DE', {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</span>
                <span class="text-[9px] text-slate-400 block font-mono mt-0.5">⏱️ ${{formatUpdateTime(matched ? matched.last_price_update : pos.last_price_update, matched ? matched.last_price_update_str : pos.last_price_update_str)}}</span>
              </div>
              <div class="pt-1 border-t border-slate-800/80 col-span-2 flex items-center justify-between">
                <div>
                  <span class="text-[10px] text-slate-400 block">Performance (${{lev}}x Hebel):</span>
                  <span class="${{pnlColor}} font-extrabold text-base">${{levPnl >= 0 ? '+' : ''}}${{levPnl.toFixed(2)}}%</span>
                </div>
                <div class="text-right">
                  <span class="text-[10px] text-slate-400 block">Ungehebelt:</span>
                  <span class="text-slate-300 font-semibold text-xs">${{rawPnl >= 0 ? '+' : ''}}${{rawPnl.toFixed(2)}}%</span>
                </div>
              </div>
            </div>

            <!-- Handlungsempfehlung Box -->
            <div class="p-3 rounded-lg border bg-${{rec.badge_color || 'indigo'}}-500/10 border-${{rec.badge_color || 'indigo'}}-500/30 text-xs space-y-1">
              <div class="flex items-center gap-1.5 font-bold text-${{rec.badge_color || 'indigo'}}-400">
                <span>💡</span>
                <span>${{rec.action || 'EMPFEHLUNG'}}</span>
              </div>
              <p class="text-[11px] text-slate-300 leading-relaxed font-medium">${{rec.message || rec.title || 'Position beobachten.'}}</p>
            </div>

            <div class="flex items-center justify-between text-[11px] text-slate-500 pt-1">
              <span>24/7 Scan aktiv</span>
              <button onclick="openDetailModal('${{sym}}')" class="text-indigo-400 hover:text-indigo-300 font-semibold cursor-pointer">Chart & Indikatoren →</button>
            </div>
          </div>
        `;
      }}).join('');

      container.innerHTML = adminFilterHtml + cardsHtml;
    }}

    function openPositionsModal() {{
      const m = document.getElementById('positions-modal');
      if (!m) return;

      // Dropdown mit allen gescannten Assets befüllen
      const sel = document.getElementById('pos-symbol-select');
      if (sel && sel.options.length <= 1) {{
        sel.innerHTML = '<option value="">-- Wähle aus überwachten Assets --</option>' + 
          currentData.assets.map(a => `<option value="${{a.symbol}}" data-price="${{a.price}}" data-name="${{a.name}}">${{a.name}} (${{a.symbol.split(':').pop()}}) - ${{Number(a.price).toLocaleString('de-DE', {{minimumFractionDigits: 2}})}}</option>`).join('');
      }}

      m.classList.remove('hidden');
      document.body.style.overflow = 'hidden';
    }}

    function closePositionsModal() {{
      const m = document.getElementById('positions-modal');
      if (m) m.classList.add('hidden');
      if (!isAnyModalOpen()) document.body.style.overflow = '';
    }}

    function selectPosDirection(dir) {{
      currentPosDirection = dir;
      const btnLong = document.getElementById('pos-btn-long');
      const btnShort = document.getElementById('pos-btn-short');
      if (dir === 'LONG') {{
        btnLong.className = 'py-1.5 rounded-md font-bold text-center bg-emerald-600 text-white';
        btnShort.className = 'py-1.5 rounded-md font-bold text-center text-slate-400 hover:text-white';
      }} else {{
        btnShort.className = 'py-1.5 rounded-md font-bold text-center bg-rose-600 text-white';
        btnLong.className = 'py-1.5 rounded-md font-bold text-center text-slate-400 hover:text-white';
      }}
    }}

    function onAssetSelectChange() {{
      const sel = document.getElementById('pos-symbol-select');
      const customInp = document.getElementById('pos-symbol-custom');
      const priceInp = document.getElementById('pos-entry-price');
      if (!sel || !sel.value) return;

      const opt = sel.options[sel.selectedIndex];
      if (opt && opt.dataset.price && priceInp) {{
        priceInp.value = opt.dataset.price;
      }}
      if (customInp) customInp.value = '';
    }}

    function saveUserPosition(e) {{
      e.preventDefault();
      const sel = document.getElementById('pos-symbol-select');
      const customInp = document.getElementById('pos-symbol-custom');
      const priceInp = document.getElementById('pos-entry-price');
      const levInp = document.getElementById('pos-leverage-val');
      const noteInp = document.getElementById('pos-note');

      let rawSymbol = (customInp && customInp.value.trim()) ? customInp.value.trim() : (sel ? sel.value : '');
      if (!rawSymbol) {{
        alert('Bitte wähle ein Symbol aus oder gib ein Kürzel ein.');
        return;
      }}

      const rawPriceStr = (priceInp ? priceInp.value : '').trim().replace(',', '.');
      const entryPrice = parseFloat(rawPriceStr);
      if (isNaN(entryPrice) || entryPrice <= 0) {{
        alert('Bitte gib einen gültigen Einstiegskurs ein.');
        return;
      }}

      const leverage = parseFloat(levInp ? levInp.value : 1) || 1.0;
      const note = noteInp ? noteInp.value.trim() : '';

      // Match asset data
      const matched = (currentData.assets || []).find(a => 
        a.symbol === rawSymbol || 
        a.symbol.endsWith(':' + rawSymbol) || 
        a.symbol.toUpperCase() === rawSymbol.toUpperCase() ||
        a.symbol.split(':').pop().toUpperCase() === rawSymbol.toUpperCase()
      );
      const symbol = matched ? matched.symbol : rawSymbol.toUpperCase();
      const assetName = matched ? matched.name : symbol;
      const currPrice = matched ? Number(matched.price) : entryPrice;

      // Performance & Empfehlung kalkulieren
      const isLong = currentPosDirection === 'LONG';
      const rawPnl = isLong 
        ? ((currPrice - entryPrice) / entryPrice) * 100
        : ((entryPrice - currPrice) / entryPrice) * 100;
      const levPnl = rawPnl * leverage;

      let recAction = 'BEOBACHTEN';
      let recTitle = 'Position aktiv';
      let recMsg = '24/7 Raspberry Pi Überwachung läuft.';
      let recColor = 'indigo';

      if (matched) {{
        const sig = (matched.signal || '').toUpperCase();
        if (isLong) {{
          if (sig.includes('BUY')) {{
            recAction = 'HALTEN / LAUFEN LASSEN';
            recTitle = 'Bullisches Signal bestätigt';
            recMsg = `Marktsignal steht auf ${{matched.signal}} (${{matched.score}}% Score). Setup intakt, Gewinne laufen lassen.`;
            recColor = 'emerald';
          }} else if (sig.includes('SELL')) {{
            recAction = 'VORSICHT / STOP NACHZIEHEN';
            recTitle = 'Bärischer Signalwechsel';
            recMsg = `Achtung: Marktsignal drehte auf ${{matched.signal}} (${{matched.score}}% Score). Stop-Loss eng nachziehen oder Teilgewinne sichern!`;
            recColor = 'rose';
          }}
        }} else {{
          if (sig.includes('SELL')) {{
            recAction = 'HALTEN / SHORT PROFITIEREN';
            recTitle = 'Bärisches Signal bestätigt';
            recMsg = `Marktsignal steht auf ${{matched.signal}} (${{matched.score}}% Score). Short-Setup intakt.`;
            recColor = 'emerald';
          }} else if (sig.includes('BUY')) {{
            recAction = 'VORSICHT / SHORT ABSICHERN';
            recTitle = 'Bullischer Signalwechsel';
            recMsg = `Achtung: Marktsignal drehte auf ${{matched.signal}} (${{matched.score}}% Score). Aufwärtsreversal möglich – Short absichern!`;
            recColor = 'rose';
          }}
        }}
      }}

      const newPos = {{
        id: 'pos_' + symbol.replace(/[^a-zA-Z0-9]/g, '_') + '_' + Date.now(),
        symbol: symbol,
        name: assetName,
        direction: currentPosDirection,
        entry_price: entryPrice,
        current_price: currPrice,
        leverage: leverage,
        pnl_pct: Math.round(rawPnl * 100) / 100,
        pnl_leveraged_pct: Math.round(levPnl * 100) / 100,
        note: note,
        recommendation: {{
          action: recAction,
          title: recTitle,
          message: recMsg,
          badge_color: recColor
        }},
        created_at: new Date().toISOString()
      }};

      // Aus tv_deleted_positions entfernen (falls das Symbol vorher gelöscht wurde)
      try {{
        let deleted = JSON.parse(localStorage.getItem('tv_deleted_positions') || '[]');
        deleted = deleted.filter(d => d !== symbol && d !== newPos.id);
        localStorage.setItem('tv_deleted_positions', JSON.stringify(deleted));
      }} catch (err) {{}}

      // 1. In localStorage speichern
      let storedList = [];
      try {{
        const raw = localStorage.getItem('tv_user_positions');
        if (raw) storedList = JSON.parse(raw);
      }} catch (err) {{}}
      storedList = storedList.filter(p => p.symbol !== symbol && p.id !== newPos.id);
      storedList.unshift(newPos);
      saveUserPositionsLocally(storedList);

      // 2. Auch in currentData.user_positions in-memory ablegen
      if (!currentData.user_positions || !Array.isArray(currentData.user_positions)) {{
        currentData.user_positions = [];
      }}
      currentData.user_positions = currentData.user_positions.filter(p => p.symbol !== symbol && p.id !== newPos.id);
      currentData.user_positions.unshift(newPos);

      // Formular zurücksetzen & Modal schließen
      const form = document.getElementById('position-form');
      if (form) form.reset();
      closePositionsModal();

      // Sofort neu rendern & Toast anzeigen
      renderUserPositions();
      showToast('Position für ' + assetName + ' erfolgreich gespeichert!');
    }}

    function deleteUserPosition(id) {{
      if (!confirm('Möchtest du diese Position wirklich schließen / entfernen?')) return;
      
      // 1. Tombstone in localStorage anlegen, damit gelöschte Positionen nie wieder auftauchen
      try {{
        let deleted = JSON.parse(localStorage.getItem('tv_deleted_positions') || '[]');
        if (!deleted.includes(id)) deleted.push(id);
        const currentList = getUserPositions();
        const found = currentList.find(p => p.id === id || p.symbol === id);
        if (found && !deleted.includes(found.symbol)) {{
          deleted.push(found.symbol);
        }}
        localStorage.setItem('tv_deleted_positions', JSON.stringify(deleted));
      }} catch (e) {{}}

      // 2. Aus localStorage entfernen
      try {{
        let stored = JSON.parse(localStorage.getItem('tv_user_positions') || '[]');
        stored = stored.filter(p => p.id !== id && p.symbol !== id);
        localStorage.setItem('tv_user_positions', JSON.stringify(stored));
      }} catch (e) {{}}

      // 3. Aus currentData.user_positions im RAM entfernen
      if (currentData.user_positions && Array.isArray(currentData.user_positions)) {{
        currentData.user_positions = currentData.user_positions.filter(p => p.id !== id && p.symbol !== id);
      }}

      // 4. Neu rendern & Feedback
      renderUserPositions();
      showToast('Position entfernt.');
    }}

    // Modal Management Helpers
    function isAnyModalOpen() {{
      const ids = ['quota-modal', 'positions-modal', 'detail-modal', 'alerts-modal', 'hypotheses-modal'];
      return ids.some(id => {{
        const el = document.getElementById(id);
        return el && !el.classList.contains('hidden');
      }});
    }}

    function closeAllModals() {{
      ['quota-modal', 'positions-modal', 'detail-modal', 'alerts-modal', 'hypotheses-modal'].forEach(id => {{
        const el = document.getElementById(id);
        if (el) el.classList.add('hidden');
      }});
      document.body.style.overflow = '';
    }}

    window.addEventListener('keydown', (e) => {{
      if (e.key === 'Escape') closeAllModals();
    }});

    // Quota Modal Funktionen
    function openQuotaModal() {{
      const m = document.getElementById('quota-modal');
      if (m) {{
        m.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
      }}
    }}

    function closeQuotaModal() {{
      const m = document.getElementById('quota-modal');
      if (m) m.classList.add('hidden');
      if (!isAnyModalOpen()) document.body.style.overflow = '';
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

      const activeClass = 'bg-indigo-600 text-white shadow-sm shadow-indigo-500/20';
      const inactiveClass = 'text-slate-400 hover:text-white';

      [btnAuto, btnLight, btnDark].forEach(btn => {{
        if (!btn) return;
        btn.className = 'px-2 py-1 rounded-lg transition active:scale-95 cursor-pointer text-[10px] sm:text-[11px] font-bold ' + inactiveClass;
      }});

      if (mode === 'auto' && btnAuto) {{
        btnAuto.className = 'px-2 py-1 rounded-lg transition active:scale-95 cursor-pointer text-[10px] sm:text-[11px] font-bold ' + activeClass;
        btnAuto.innerHTML = `<span>⏰</span><span class="ml-1 hidden xs:inline sm:inline">Auto (${{effective === 'light' ? 'Tag' : 'Nacht'}})</span>`;
      }} else if (mode === 'light' && btnLight) {{
        btnLight.className = 'px-2 py-1 rounded-lg transition active:scale-95 cursor-pointer text-[10px] sm:text-[11px] font-bold ' + activeClass;
      }} else if (mode === 'dark' && btnDark) {{
        btnDark.className = 'px-2 py-1 rounded-lg transition active:scale-95 cursor-pointer text-[10px] sm:text-[11px] font-bold ' + activeClass;
      }}
    }}

    function setThemeMode(mode) {{
      applyTheme(mode, true);
      const label = mode === 'auto' ? 'Automatisch an Tageszeit angepasst' : (mode === 'light' ? 'Heller Modus aktiviert' : 'Dunkler Modus aktiviert');
      if (typeof showToast === 'function') showToast(label);
    }}

    // Check daylight every 60s if in auto mode
    setInterval(() => {{
      const currentMode = getThemeMode();
      if (currentMode === 'auto') {{
        applyTheme('auto', false);
      }}
    }}, 60000);

    // Initial render
    initAuthOnLoad();
    updateStats();
    applyFilters();
    renderPortfolioSection();
    renderUserPositions();
    applyTheme(getThemeMode(), false);

    // Deep-Link aus Historie (?asset=SYMBOL oder ?symbol=SYMBOL)
    const urlParams = new URLSearchParams(window.location.search);
    const targetAsset = urlParams.get('asset') || urlParams.get('symbol');
    if (targetAsset) {{
      setTimeout(() => {{
        openDetailModal(targetAsset);
      }}, 350);
    }}
  </script>

  <!-- User Positions Modal -->
  <div id="positions-modal" onclick="if(event.target === this) closePositionsModal()" ontouchend="if(event.target === this) {{ event.preventDefault(); closePositionsModal(); }}" class="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm hidden flex items-center justify-center p-2 sm:p-4 overflow-y-auto">
    <div class="max-w-md w-full max-h-[88vh] flex flex-col rounded-2xl bg-[#0d1322] border border-indigo-500/40 shadow-2xl relative text-slate-200 my-auto overflow-hidden">
      <div class="flex items-center justify-between p-4 sm:p-5 pb-3 border-b border-slate-800 bg-[#0d1322] shrink-0">
        <div class="flex items-center gap-2.5">
          <div class="w-9 h-9 rounded-xl bg-indigo-500/20 border border-indigo-500/40 flex items-center justify-center text-lg shrink-0">
            👤
          </div>
          <div>
            <h3 class="text-base font-bold text-white tracking-tight">Eigene Position eintragen</h3>
            <p class="text-xs text-slate-400">Wird mit 24/7 Live-Indikatoren überwacht</p>
          </div>
        </div>
        <button onclick="closePositionsModal()" aria-label="Schließen" class="w-11 h-11 min-w-[44px] min-h-[44px] rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white flex items-center justify-center transition active:scale-95 cursor-pointer text-lg font-bold">✕</button>
      </div>

      <form id="position-form" onsubmit="saveUserPosition(event)" class="p-4 sm:p-5 overflow-y-auto space-y-3.5 text-xs flex-1 overscroll-contain">
        <div>
          <label class="block text-slate-400 font-semibold mb-1">Asset / Symbol auswählen:</label>
          <select id="pos-symbol-select" onchange="onAssetSelectChange()" class="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700/80 text-white font-mono focus:outline-none focus:border-indigo-500">
            <!-- Dynamisch befüllt mit allen 58 Assets -->
          </select>
        </div>

        <div>
          <label class="block text-slate-400 font-semibold mb-1">Oder alternatives Symbol eingeben:</label>
          <input type="text" id="pos-symbol-custom" placeholder="z.B. BINANCE:SOLUSDT oder NASDAQ:TSLA" class="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700/80 text-white font-mono focus:outline-none focus:border-indigo-500">
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-slate-400 font-semibold mb-1">Richtung:</label>
            <div class="grid grid-cols-2 gap-1.5 p-1 rounded-lg bg-slate-950 border border-slate-800">
              <button type="button" id="pos-btn-long" onclick="selectPosDirection('LONG')" class="py-1.5 rounded-md font-bold text-center bg-emerald-600 text-white">LONG</button>
              <button type="button" id="pos-btn-short" onclick="selectPosDirection('SHORT')" class="py-1.5 rounded-md font-bold text-center text-slate-400 hover:text-white">SHORT</button>
            </div>
          </div>
          <div>
            <label class="block text-slate-400 font-semibold mb-1">Hebel (1x - 10x):</label>
            <div class="flex items-center gap-2">
              <input type="range" id="pos-leverage-slider" min="1" max="10" step="0.5" value="3" oninput="document.getElementById('pos-leverage-val').value = this.value" class="w-full accent-indigo-500 cursor-pointer">
              <input type="number" id="pos-leverage-val" min="1" max="10" step="0.5" value="3" oninput="document.getElementById('pos-leverage-slider').value = this.value" class="w-16 px-2 py-1.5 rounded-lg bg-slate-950 border border-slate-700/80 text-white font-mono text-center">
            </div>
          </div>
        </div>

        <div>
          <label class="block text-slate-400 font-semibold mb-1">Einstiegskurs:</label>
          <input type="number" step="any" id="pos-entry-price" required placeholder="z.B. 182.50" class="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700/80 text-white font-mono focus:outline-none focus:border-indigo-500">
        </div>

        <div>
          <label class="block text-slate-400 font-semibold mb-1">Optionale Notiz:</label>
          <input type="text" id="pos-note" placeholder="z.B. Ausbruch über 1D Golden Pocket" class="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700/80 text-white focus:outline-none focus:border-indigo-500">
        </div>
      </form>

      <div class="p-3 sm:p-4 border-t border-slate-800 bg-[#0d1322] flex items-center justify-end gap-2.5 shrink-0">
        <button type="button" onclick="closePositionsModal()" class="px-4 py-2.5 rounded-xl bg-slate-800 text-slate-300 hover:bg-slate-700 font-semibold transition cursor-pointer active:scale-95 text-xs">Abbrechen</button>
        <button type="submit" form="position-form" class="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold transition shadow-lg shadow-indigo-600/30 cursor-pointer active:scale-95 text-xs">Speichern & Tracken</button>
      </div>
    </div>
  </div>

  <!-- API Quota Modal -->
  <div id="quota-modal" onclick="if(event.target === this) closeQuotaModal()" ontouchend="if(event.target === this) {{ event.preventDefault(); closeQuotaModal(); }}" class="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm hidden flex items-center justify-center p-2 sm:p-4 overflow-y-auto">
    <div class="max-w-lg w-full max-h-[88vh] flex flex-col rounded-2xl bg-[#0d1322] border border-indigo-500/40 shadow-2xl relative text-slate-200 my-auto overflow-hidden">
      <div class="flex items-center justify-between p-4 sm:p-5 pb-3 border-b border-slate-800 bg-[#0d1322] shrink-0">
        <div class="flex items-center gap-2.5">
          <div class="w-10 h-10 rounded-xl bg-indigo-500/20 border border-indigo-500/40 flex items-center justify-center text-xl shrink-0">
            🔑
          </div>
          <div>
            <h3 class="font-bold text-base text-white">Google Gemini API-Key Pool</h3>
            <p class="text-xs text-slate-400">Intelligentes Multi-Key Management & Failover</p>
          </div>
        </div>
        <button onclick="closeQuotaModal()" aria-label="Schließen" class="w-11 h-11 min-w-[44px] min-h-[44px] rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white flex items-center justify-center transition active:scale-95 cursor-pointer text-lg font-bold">✕</button>
      </div>

      <div class="p-4 sm:p-5 overflow-y-auto space-y-3.5 text-xs flex-1 overscroll-contain">
        <div class="grid grid-cols-2 gap-2.5">
          <div class="p-3 rounded-xl bg-slate-900/80 border border-slate-800">
            <span class="text-[10px] text-slate-400 block font-semibold">Aktives KI-Modell</span>
            <span class="text-white font-mono font-bold text-sm block mt-0.5">gemini-3.8-flash</span>
            <span class="text-[10px] text-emerald-400">High Reasoning Core</span>
          </div>
          <div class="p-3 rounded-xl bg-slate-900/80 border border-slate-800">
            <span class="text-[10px] text-slate-400 block font-semibold">Aktiver Primär-Key</span>
            <span class="text-white font-mono font-bold text-sm block mt-0.5">{active_key_masked}</span>
            <span class="text-[10px] text-indigo-300">{active_keys_count} von {total_keys_count} Keys aktiv</span>
          </div>
        </div>

        <!-- Gesamt-Pool Übersicht -->
        <div class="p-4 rounded-xl bg-slate-900/90 border border-indigo-500/30 space-y-2">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-1.5">
              <span class="text-xs font-bold text-white">Gesamt-Pool Kontingent</span>
              <span class="px-1.5 py-0.2 rounded text-[10px] bg-indigo-500/20 text-indigo-300 font-mono">{total_keys_count}x Keys</span>
            </div>
            <span class="font-mono font-bold text-xs {quota_num_class}">{quota_used} / {quota_limit} Requests ({quota_pct}%)</span>
          </div>
          <div class="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
            <div class="h-2 rounded-full {quota_bar_color}" style="width: {min(100.0, quota_pct)}%"></div>
          </div>
          <div class="flex items-center justify-between text-[11px] text-slate-400 pt-0.5">
            <span>Verbleibend: <strong class="text-white font-mono">{quota_remaining} Requests</strong></span>
            <span>Status: <strong class="text-emerald-400 font-mono">Aktiv (24/7)</strong></span>
          </div>
        </div>

        <!-- Einzel-Keys Aufschlüsselung -->
        <div class="space-y-2">
          <span class="text-[11px] font-bold text-slate-400 uppercase tracking-wider block">Einzel-Key Status & Kontingente:</span>
          <div class="space-y-2">
            {keys_cards_html}
          </div>
        </div>

        <div class="p-3.5 rounded-xl bg-indigo-950/30 border border-indigo-500/30 space-y-1.5 text-[11px] leading-relaxed text-slate-300">
          <div class="font-bold text-indigo-300 flex items-center gap-1.5">
            <span>🛡️</span>
            <span>Intelligentes Failover & Lastverteilung</span>
          </div>
          <p>
            Alle <strong>{total_keys_count} Google AI Studio API-Keys</strong> werden intelligent im Verbund betrieben. Sobald ein Key sein Tageslimit (20 Requests) erreicht, wechselt der Raspberry Pi <strong>vollautomatisch und ohne Scanunterbrechung</strong> auf den nächsten Key im Pool.
          </p>
          <p>
            Dadurch multipliziert sich dein kostenfreies Kontingent auf <strong>{quota_limit} KI-Analysen pro Tag</strong>. Sollten alle Keys temporär voll sein, sichert die mathematische 3-Timeframe Confluence-Engine weiterhin lückenlos jeden 4-Stunden-Scanzyklus ab.
          </p>
        </div>
      </div>

      <div class="p-3 sm:p-4 border-t border-slate-800 bg-[#0d1322] flex items-center justify-end shrink-0">
        <button onclick="closeQuotaModal()" class="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs transition cursor-pointer text-center active:scale-95">Schließen</button>
      </div>
    </div>
  </div>

  <!-- iOS Alerts Info Modal -->
  <div id="alerts-modal" onclick="if(event.target === this) closeAlertsModal()" ontouchend="if(event.target === this) {{ event.preventDefault(); closeAlertsModal(); }}" class="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm hidden flex items-center justify-center p-2 sm:p-4 overflow-y-auto">
    <div class="max-w-lg w-full max-h-[88vh] flex flex-col rounded-2xl bg-[#0d1322] border border-indigo-500/40 shadow-2xl relative text-slate-200 my-auto overflow-hidden">
      <div class="flex items-center justify-between p-4 sm:p-5 pb-3 border-b border-slate-800 bg-[#0d1322] shrink-0">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-indigo-500/20 border border-indigo-500/40 flex items-center justify-center text-xl shrink-0">
            🔔
          </div>
          <div>
            <h3 class="font-bold text-base sm:text-lg text-white">iOS Lockscreen Alerts</h3>
            <p class="text-xs text-slate-400">Push-Benachrichtigungen direkt auf dein iPhone</p>
          </div>
        </div>
        <button onclick="closeAlertsModal()" aria-label="Schließen" class="w-11 h-11 min-w-[44px] min-h-[44px] rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white flex items-center justify-center transition active:scale-95 cursor-pointer text-lg font-bold">✕</button>
      </div>

      <div class="p-4 sm:p-5 overflow-y-auto space-y-4 text-xs leading-relaxed flex-1 overscroll-contain">
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

      <div class="p-3 sm:p-4 border-t border-slate-800 bg-[#0d1322] flex items-center justify-end shrink-0">
        <button onclick="closeAlertsModal()" class="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs transition cursor-pointer active:scale-95 text-center">
          Verstanden & Schließen
        </button>
      </div>
    </div>
  </div>

  <!-- Setup Hypotheses Guide Modal -->
  <div id="hypotheses-modal" onclick="if(event.target === this) closeHypothesesModal()" ontouchend="if(event.target === this) {{ event.preventDefault(); closeHypothesesModal(); }}" class="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm hidden flex items-center justify-center p-2 sm:p-5 overflow-y-auto">
    <div class="max-w-3xl w-full max-h-[90vh] flex flex-col rounded-2xl bg-[#0d1322] border border-indigo-500/40 shadow-2xl relative text-slate-200 my-auto overflow-hidden">
      
      <!-- Modal Header -->
      <div class="flex items-center justify-between p-4 sm:p-5 pb-3 border-b border-slate-800 bg-[#0d1322] shrink-0">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-indigo-500/20 border border-indigo-500/40 flex items-center justify-center text-xl shrink-0">
            💡
          </div>
          <div>
            <div class="flex items-center gap-2">
              <h3 class="font-bold text-base sm:text-lg text-white">Setup-Hypothesen & Trade-Plan Guide</h3>
              <span class="px-2 py-0.5 rounded-full text-[10px] font-mono bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">Strategy Rules</span>
            </div>
            <p class="text-xs text-slate-400 mt-0.5">Verstehe die institutionelle Logik hinter jedem Signal (SMC, Wyckoff VSA, RSI & Fibonacci)</p>
          </div>
        </div>
        <button onclick="closeHypothesesModal()" aria-label="Schließen" class="w-11 h-11 min-w-[44px] min-h-[44px] rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white flex items-center justify-center transition active:scale-95 cursor-pointer text-lg font-bold shrink-0">✕</button>
      </div>

      <!-- Quick Filter Switcher within Modal -->
      <div class="px-4 sm:px-5 pt-3 pb-2 flex flex-wrap items-center gap-2 shrink-0 border-b border-slate-800/60">
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
      <div class="p-4 sm:p-5 overflow-y-auto space-y-4 text-xs leading-relaxed flex-1 overscroll-contain">
        
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
      <div class="p-3 sm:p-4 border-t border-slate-800 bg-[#0d1322] flex items-center justify-between shrink-0 text-xs">
        <span class="text-slate-500 font-mono text-[11px] hidden sm:inline">TradingView Super-Analyst Strategy Engine</span>
        <button onclick="closeHypothesesModal()" class="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold transition cursor-pointer active:scale-95 text-center">
          Schließen
        </button>
      </div>

    </div>
  </div>

  <!-- Mobile Sticky Bottom Navigation Bar -->
  <nav id="mobile-bottom-nav" class="fixed bottom-0 left-0 right-0 z-40 bg-[#0d1322]/95 backdrop-blur-lg border-t border-slate-800/80 px-3 py-2 flex items-center justify-around md:hidden shadow-2xl safe-area-pb">
    <button id="mob-tab-positions" onclick="switchDashboardTab('positions')" class="mob-nav-btn flex flex-col items-center justify-center py-1 px-2.5 rounded-xl transition text-indigo-400 font-bold active:scale-95 bg-indigo-500/10 cursor-pointer">
      <span class="text-xl">👤</span>
      <span class="text-[10px] tracking-tight mt-0.5">Positionen</span>
    </button>
    <button id="mob-tab-topsetups" onclick="switchDashboardTab('topsetups')" class="mob-nav-btn flex flex-col items-center justify-center py-1 px-2.5 rounded-xl transition text-slate-400 active:scale-95 cursor-pointer">
      <span class="text-xl">🎯</span>
      <span class="text-[10px] tracking-tight mt-0.5">Top-Setups</span>
    </button>
    <button id="mob-tab-scanner" onclick="switchDashboardTab('scanner')" class="mob-nav-btn flex flex-col items-center justify-center py-1 px-2.5 rounded-xl transition text-slate-400 active:scale-95 cursor-pointer">
      <span class="text-xl">🚀</span>
      <span class="text-[10px] tracking-tight mt-0.5">Scanner</span>
    </button>
    <button id="mob-tab-admin" onclick="switchDashboardTab('admin')" class="mob-nav-btn hidden flex flex-col items-center justify-center py-1 px-2.5 rounded-xl transition text-amber-400 active:scale-95 cursor-pointer">
      <span class="text-xl">⚙️</span>
      <span class="text-[10px] tracking-tight mt-0.5">Admin</span>
    </button>
  </nav>
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

