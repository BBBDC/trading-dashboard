#!/usr/bin/env python3
"""
TradingView Super-Analyst – Telegram Bot Engine.
Bietet eine mobile Kachel- & Button-Steuerung für:
- Eingabe, Verwaltung und Schließen von eigenen Positionen (Multi-User)
- Sofortige Synchronisation mit dem Raspberry Pi & Git-Web-Dashboard
- Live-Marktübersicht & Auslösen von Master-Scans
- Autonome Benachrichtigungen und Nutzer-Freigaben
"""

import os
import sys
import time
import json
import logging
import threading
import subprocess
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone
import requests

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "telegram_config.json"
POSITIONS_FILE = BASE_DIR / "knowledge_base" / "user_positions.json"
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"
PORTFOLIO_FILE = BASE_DIR / "knowledge_base" / "autonomous_portfolio.json"

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("telegram_bot")

# In-Memory User Sessions für mehrstufige Wizards
USER_SESSIONS = {}
SCAN_LOCK = threading.Lock()
SCAN_RUNNING = False


# ==============================================================================
# 1. KONFIGURATION & RECHTEVERWALTUNG
# ==============================================================================
def load_config():
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Konfigurationsdatei {CONFIG_FILE} nicht gefunden.")
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ==============================================================================
# BENUTZER-BENACHRICHTIGUNGSPRÄFERENZEN
# ==============================================================================
USER_PREFS_FILE = BASE_DIR / "knowledge_base" / "user_alert_preferences.json"
LIVE_WATCHLISTS_FILE = BASE_DIR / "knowledge_base" / "live_watchlists.json"

def get_available_tv_watchlists():
    if LIVE_WATCHLISTS_FILE.exists():
        try:
            with open(LIVE_WATCHLISTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                names = [wl.get("name") for wl in data.get("watchlists", []) if wl.get("name")]
                if names:
                    return names
        except Exception:
            pass
    return ["Aktien", "Crypto", "Commodities", "Rohstoffe", "Devisen", "Eigene Trades"]

DEFAULT_ALERT_PREFS = {
    "enabled": True,
    "categories": ["cat_crypto", "cat_ustech", "cat_dax", "cat_commodities"],
    "watchlists": ["Aktien", "Crypto", "Commodities", "Rohstoffe", "Devisen", "Eigene Trades"],
    "min_score": 85,
    "only_my_trades": False
}

def load_all_user_preferences():
    if USER_PREFS_FILE.exists():
        try:
            with open(USER_PREFS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_all_user_preferences(prefs):
    USER_PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(USER_PREFS_FILE, "w", encoding="utf-8") as f:
        json.dump(prefs, f, indent=2, ensure_ascii=False)

def get_user_preferences(user_id):
    all_prefs = load_all_user_preferences()
    uid = str(user_id)
    if uid not in all_prefs:
        all_prefs[uid] = dict(DEFAULT_ALERT_PREFS)
        save_all_user_preferences(all_prefs)
    else:
        updated = False
        for k, v in DEFAULT_ALERT_PREFS.items():
            if k not in all_prefs[uid]:
                all_prefs[uid][k] = v
                updated = True
        if updated:
            save_all_user_preferences(all_prefs)
    return all_prefs[uid]

def update_user_preference(user_id, key, val):
    all_prefs = load_all_user_preferences()
    uid = str(user_id)
    if uid not in all_prefs:
        all_prefs[uid] = dict(DEFAULT_ALERT_PREFS)
    all_prefs[uid][key] = val
    save_all_user_preferences(all_prefs)
    return all_prefs[uid]


def check_auth(user_id, username):
    """Prüft, ob ein Nutzer Admin oder autorisierter Trader ist."""
    cfg = load_config()
    user_id_str = str(user_id)
    username_clean = (username or "").lstrip("@").lower()

    admin_unames = [u.lower() for u in cfg.get("admin_usernames", [])]
    admin_cids = [str(cid) for cid in cfg.get("admin_chat_ids", [])]

    is_admin = (username_clean in admin_unames) or (user_id_str in admin_cids)

    # Wenn der Nutzer Admin ist, seine Chat-ID ggf. dauerhaft speichern
    if is_admin and user_id_str not in admin_cids:
        cfg.setdefault("admin_chat_ids", []).append(user_id_str)
        cfg.setdefault("authorized_users", {})[username or user_id_str] = {
            "name": username or f"User_{user_id}",
            "chat_id": user_id_str,
            "role": "admin",
            "added_at": datetime.now(timezone.utc).isoformat()
        }
        save_config(cfg)
        return "admin"

    if is_admin:
        return "admin"

    # Autorisierte reguläre Trader prüfen
    auth_users = cfg.get("authorized_users", {})
    for uname, udata in auth_users.items():
        if uname.lower() == username_clean or str(udata.get("chat_id")) == user_id_str:
            return udata.get("role", "trader")

    return None


# ==============================================================================
# 2. TELEGRAM API HELPER (REST-POLLING & MESSAGING)
# ==============================================================================
class TelegramAPI:
    def __init__(self, token):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.session = requests.Session()

    def get_updates(self, offset=None, timeout=25):
        params = {"timeout": timeout}
        if offset:
            params["offset"] = offset
        try:
            resp = self.session.get(f"{self.base_url}/getUpdates", params=params, timeout=timeout + 5)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result", [])
        except Exception as e:
            logger.debug(f"getUpdates Timeout/Fehler: {e}")
        return []

    def send_message(self, chat_id, text, reply_markup=None, parse_mode="HTML"):
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        try:
            resp = self.session.post(f"{self.base_url}/sendMessage", json=payload, timeout=10)
            return resp.json()
        except Exception as e:
            logger.error(f"sendMessage Fehler an {chat_id}: {e}")
            return None

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        try:
            resp = self.session.post(f"{self.base_url}/editMessageText", json=payload, timeout=10)
            return resp.json()
        except Exception as e:
            logger.error(f"editMessageText Fehler: {e}")
            return None

    def answer_callback_query(self, callback_query_id, text=None, show_alert=False):
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
            payload["show_alert"] = show_alert
        try:
            self.session.post(f"{self.base_url}/answerCallbackQuery", json=payload, timeout=5)
        except Exception as e:
            logger.debug(f"answerCallbackQuery Fehler: {e}")

    def delete_message(self, chat_id, message_id):
        try:
            self.session.post(f"{self.base_url}/deleteMessage", json={"chat_id": chat_id, "message_id": message_id}, timeout=5)
        except Exception:
            pass


# ==============================================================================
# 3. KACHEL-MENÜS & UI-KOMPONENTEN (INLINE KEYBOARDS)
# ==============================================================================
def get_main_menu_keyboard(role="trader"):
    if role == "admin":
        kb = [
            [
                {"text": "➕ Neuer Trade", "callback_data": "menu_new_trade"},
                {"text": "📊 Meine Trades", "callback_data": "menu_my_trades"}
            ],
            [
                {"text": "🎯 Top-Setups", "callback_data": "menu_top_setups"},
                {"text": "🚀 Marktübersicht", "callback_data": "menu_market_scan"}
            ],
            [
                {"text": "🔔 Benachrichtigungen", "callback_data": "menu_alert_settings"},
                {"text": "⚙️ Admin-Zentrale", "callback_data": "menu_admin_hub"}
            ],
            [
                {"text": "🌐 Web-Dashboard", "callback_data": "menu_dashboard_links"},
                {"text": "🔄 Aktualisieren", "callback_data": "menu_refresh"}
            ]
        ]
    else:
        # Reguläre Trader: Kein Modellportfolio und keine Admin-Zentrale
        kb = [
            [
                {"text": "➕ Neuer Trade", "callback_data": "menu_new_trade"},
                {"text": "📊 Meine Trades", "callback_data": "menu_my_trades"}
            ],
            [
                {"text": "🎯 Top-Setups", "callback_data": "menu_top_setups"},
                {"text": "🚀 Marktübersicht", "callback_data": "menu_market_scan"}
            ],
            [
                {"text": "🔔 Benachrichtigungen", "callback_data": "menu_alert_settings"},
                {"text": "🌐 Web-Dashboard", "callback_data": "menu_dashboard_links"}
            ],
            [
                {"text": "🔄 Aktualisieren", "callback_data": "menu_refresh"}
            ]
        ]
    return {"inline_keyboard": kb}


def get_alert_settings_text_and_markup(user_id):
    prefs = get_user_preferences(user_id)
    enabled = prefs.get("enabled", True)
    cats = prefs.get("categories", ["cat_crypto", "cat_ustech", "cat_dax", "cat_commodities"])
    min_score = prefs.get("min_score", 85)
    my_trades = prefs.get("only_my_trades", False)
    all_wls = get_available_tv_watchlists()
    user_wls = prefs.get("watchlists", list(all_wls))

    status_str = "🟢 <b>AKTIV</b> (Push-Alerts eingeschaltet)" if enabled else "🔴 <b>PAUSIERT</b> (Stummgeschaltet)"
    wl_active_count = len([w for w in user_wls if w in all_wls])
    
    text = (
        "🔔 <b>Meine Benachrichtigungseinstellungen</b>\n\n"
        f"• <b>Status:</b> {status_str}\n"
        f"• <b>Min. Setup-Score:</b> <b>{min_score}%</b>\n"
        f"• <b>TradingView-Listen:</b> <b>{wl_active_count} von {len(all_wls)} aktiv</b>\n"
        f"• <b>Filter-Modus:</b> {'⭐ Nur eigene Trades' if my_trades else '🌐 Alle überwachten Märkte'}\n\n"
        "<i>Wähle deine bevorzugten Asset-Klassen und TradingView-Listen (Tippen schaltet um):</i>"
    )

    def c_mark(c):
        return "✅" if c in cats else "❌"

    kb = [
        [
            {"text": f"{c_mark('cat_crypto')} ₿ Krypto", "callback_data": "toggle_alert_cat_cat_crypto"},
            {"text": f"{c_mark('cat_ustech')} 💻 US Tech", "callback_data": "toggle_alert_cat_cat_ustech"}
        ],
        [
            {"text": f"{c_mark('cat_dax')} 🇩🇪 DAX / EU", "callback_data": "toggle_alert_cat_cat_dax"},
            {"text": f"{c_mark('cat_commodities')} 🥇 Rohstoffe", "callback_data": "toggle_alert_cat_cat_commodities"}
        ],
        [
            {"text": f"📋 TradingView-Listen filtern ({wl_active_count}/{len(all_wls)}) »", "callback_data": "menu_alert_tv_lists"}
        ],
        [
            {"text": f"🎯 Min-Score: {min_score}% ▾", "callback_data": "cycle_alert_score"},
            {"text": f"⭐ Modus: {'Eigene Trades' if my_trades else 'Alle Märkte'}", "callback_data": "toggle_alert_my_trades"}
        ],
        [
            {"text": f"{'⏸️ Alerts stummschalten' if enabled else '▶️ Alerts aktivieren'}", "callback_data": "toggle_alert_master"}
        ],
        [
            {"text": "◀️ Zurück zum Hauptmenü", "callback_data": "menu_refresh"}
        ]
    ]
    return text, {"inline_keyboard": kb}


def get_alert_tv_lists_text_and_markup(user_id):
    prefs = get_user_preferences(user_id)
    all_wls = get_available_tv_watchlists()
    user_wls = prefs.get("watchlists", list(all_wls))

    text = (
        "📋 <b>TradingView-Listen Benachrichtigungs-Filter</b>\n\n"
        "Hier kannst du gezielt festlegen, für welche deiner TradingView-Watchlists du Signale erhalten möchtest.\n\n"
        f"Aktuell aktiv: <b>{len(user_wls)} von {len(all_wls)} Listen</b>\n"
        "<i>Tippe auf eine Liste, um sie zu aktivieren oder zu deaktivieren:</i>"
    )

    wl_icons = {
        "Aktien": "📈",
        "Crypto": "₿",
        "Commodities": "🥇",
        "Rohstoffe": "🛢️",
        "Devisen": "💱",
        "Eigene Trades": "⭐"
    }

    kb = []
    row = []
    for wl in all_wls:
        is_active = wl in user_wls
        mark = "✅" if is_active else "❌"
        icon = wl_icons.get(wl, "📁")
        btn_text = f"{mark} {icon} {wl}"
        row.append({"text": btn_text, "callback_data": f"toggle_alert_wl_{wl}"})
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)

    kb.append([
        {"text": "✅ Alle aktivieren", "callback_data": "set_alert_wl_all_on"},
        {"text": "❌ Alle deaktivieren", "callback_data": "set_alert_wl_all_off"}
    ])
    kb.append([
        {"text": "◀️ Zurück zu Einstellungen", "callback_data": "menu_alert_settings"}
    ])

    return text, {"inline_keyboard": kb}


def get_category_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "₿ Krypto", "callback_data": "cat_crypto"},
                {"text": "💻 US Tech", "callback_data": "cat_ustech"}
            ],
            [
                {"text": "🇩🇪 DAX / EU", "callback_data": "cat_dax"},
                {"text": "🥇 Rohstoffe", "callback_data": "cat_commodities"}
            ],
            [
                {"text": "✍️ Eigenen Ticker eingeben", "callback_data": "cat_custom"}
            ],
            [
                {"text": "❌ Abbrechen", "callback_data": "action_cancel"}
            ]
        ]
    }


def get_symbols_keyboard_for_category(cat):
    symbols_map = {
        "cat_crypto": [
            ("₿ BTC / USDT", "BINANCE:BTCUSDT"),
            ("⟠ ETH / USDT", "BINANCE:ETHUSDT"),
            ("☀️ SOL / USDT", "BINANCE:SOLUSDT"),
            ("✕ XRP / USDT", "BINANCE:XRPUSDT"),
            ("🐶 DOGE / USDT", "BINANCE:DOGEUSDT"),
            ("🟡 BNB / USDT", "BINANCE:BNBUSDT")
        ],
        "cat_ustech": [
            ("🟢 NVIDIA (NVDA)", "NASDAQ:NVDA"),
            ("🍎 Apple (AAPL)", "NASDAQ:AAPL"),
            ("⚡ Tesla (TSLA)", "NASDAQ:TSLA"),
            ("🪟 Microsoft (MSFT)", "NASDAQ:MSFT"),
            ("📦 Amazon (AMZN)", "NASDAQ:AMZN"),
            ("👥 Meta (META)", "NASDAQ:META")
        ],
        "cat_dax": [
            ("☁️ SAP", "XETR:SAP"),
            ("⚡ Siemens (SIE)", "XETR:SIE"),
            ("🛡️ Allianz (ALV)", "XETR:ALV"),
            ("🚗 Mercedes (MBG)", "XETR:MBG"),
            ("📈 DAX Index", "INDEX:DAX")
        ],
        "cat_commodities": [
            ("🥇 Gold (XAU)", "TVC:GOLD"),
            ("🥈 Silber (XAG)", "TVC:SILVER"),
            ("🛢️ WTI Rohöl", "TVC:USOIL")
        ]
    }

    raw_list = symbols_map.get(cat, [])
    buttons = []
    # In 2er Spalten anordnen
    for i in range(0, len(raw_list), 2):
        row = [{"text": raw_list[i][0], "callback_data": f"sym_{raw_list[i][1]}"}]
        if i + 1 < len(raw_list):
            row.append({"text": raw_list[i + 1][0], "callback_data": f"sym_{raw_list[i + 1][1]}"})
        buttons.append(row)

    buttons.append([{"text": "✍️ Anderen Ticker eingeben", "callback_data": "cat_custom"}])
    buttons.append([{"text": "🔙 Zurück zu Kategorien", "callback_data": "menu_new_trade"}])
    return {"inline_keyboard": buttons}


def get_direction_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "🟢 LONG (Kauf)", "callback_data": "dir_LONG"},
                {"text": "🔴 SHORT (Verkauf)", "callback_data": "dir_SHORT"}
            ],
            [
                {"text": "❌ Abbrechen", "callback_data": "action_cancel"}
            ]
        ]
    }


def get_entry_price_keyboard(live_price=None):
    buttons = []
    if live_price and live_price > 0:
        price_str = f"{live_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        buttons.append([{"text": f"📍 Live-Kurs ({price_str} $) übernehmen", "callback_data": f"price_{live_price}"}])
    buttons.append([{"text": "❌ Abbrechen", "callback_data": "action_cancel"}])
    return {"inline_keyboard": buttons}


def get_leverage_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "1x (Spot)", "callback_data": "lev_1"},
                {"text": "2x", "callback_data": "lev_2"},
                {"text": "3x", "callback_data": "lev_3"}
            ],
            [
                {"text": "5x", "callback_data": "lev_5"},
                {"text": "10x", "callback_data": "lev_10"},
                {"text": "20x", "callback_data": "lev_20"}
            ],
            [
                {"text": "✍️ Anderer Hebel", "callback_data": "lev_custom"},
                {"text": "❌ Abbrechen", "callback_data": "action_cancel"}
            ]
        ]
    }


def get_note_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "⏭️ Überspringen (Direkt anlegen)", "callback_data": "note_skip"}
            ],
            [
                {"text": "❌ Abbrechen", "callback_data": "action_cancel"}
            ]
        ]
    }


def get_confirm_trade_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Trade bestätigen & speichern", "callback_data": "trade_confirm_save"}
            ],
            [
                {"text": "❌ Abbrechen", "callback_data": "action_cancel"}
            ]
        ]
    }


# ==============================================================================
# 4. DATEN-ABFRAGEN (LIVE-DATEN, PORTFOLIO, POSITIONEN)
# ==============================================================================
def find_asset_price(symbol):
    """Sucht den aktuellen Referenzkurs aus der Marktdatenbank."""
    if not DB_FILE.exists():
        return None
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
        ticker = symbol.split(":")[-1].upper()
        for a in db.get("assets", []):
            sym = a.get("symbol", "").upper()
            if sym == symbol.upper() or sym.endswith(f":{ticker}") or sym == ticker:
                return float(a.get("price", 0.0))
    except Exception:
        pass
    return None


def get_market_overview(role="trader"):
    """Gibt eine kurze Zusammenfassung des letzten Scans zurück."""
    if not DB_FILE.exists():
        return "⚠️ Noch keine Marktdatenbank vorhanden. Bitte starte einen Scan."
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)

        ts = db.get("timestamp", "Unbekannt")
        tot = db.get("total_analyzed", 0)
        longs = db.get("long_count", 0)
        shorts = db.get("short_count", 0)
        neutrals = db.get("neutral_count", 0)
        engine = db.get("evaluation_engine", "Raspberry Pi 24/7 Confluence Engine")

        engine_text = engine if role == "admin" else "24/7 Pi Confluence Multi-Timeframe"

        # Top 3 Longs & Shorts nach Confluence Score
        assets = db.get("assets", [])
        long_candidates = sorted([a for a in assets if a.get("signal") == "LONG"], key=lambda x: x.get("score", x.get("confluence_score", 0)), reverse=True)[:3]
        short_candidates = sorted([a for a in assets if a.get("signal") == "SHORT"], key=lambda x: x.get("score", x.get("confluence_score", 0)), reverse=True)[:3]

        text = (
            f"📊 <b>Marktanalyse Status</b>\n"
            f"<i>Stand: {ts}</i>\n\n"
            f"• <b>Überwachte Werte:</b> {tot}\n"
            f"• 🟢 <b>Long Signale:</b> {longs}\n"
            f"• 🔴 <b>Short Signale:</b> {shorts}\n"
            f"• ⚪ <b>Neutral:</b> {neutrals}\n"
            f"• 🧠 <b>Engine:</b> {engine_text}\n\n"
        )

        if long_candidates:
            text += "<b>Top Long Setups:</b>\n"
            for a in long_candidates:
                score = a.get("score", a.get("confluence_score", 0))
                text += f"  🟢 <b>{a.get('name', a.get('symbol'))}</b> (Score: {score}%) | {a.get('price', 0):,.2f} $\n"
            text += "\n"

        if short_candidates:
            text += "<b>Top Short Setups:</b>\n"
            for a in short_candidates:
                score = a.get("score", a.get("confluence_score", 0))
                text += f"  🔴 <b>{a.get('name', a.get('symbol'))}</b> (Score: {score}%) | {a.get('price', 0):,.2f} $\n"
            text += "\n"

        return text
    except Exception as e:
        return f"Fehler beim Lesen der Marktdatenbank: {e}"


def get_top_setups_text_and_markup():
    """Erstellt eine detaillierte Top-Setups Übersicht für Chat-Nutzer."""
    if not DB_FILE.exists():
        return "⚠️ Noch keine Marktdaten vorhanden.", None
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)

        ts = db.get("timestamp", "Unbekannt")
        assets = db.get("assets", [])

        long_candidates = sorted([a for a in assets if a.get("signal") == "LONG"], key=lambda x: x.get("score", 0), reverse=True)[:3]
        short_candidates = sorted([a for a in assets if a.get("signal") == "SHORT"], key=lambda x: x.get("score", 0), reverse=True)[:3]

        lines = [
            f"🎯 <b>High-Conviction Top-Setups</b>",
            f"<i>Stand: {ts} · Multi-Timeframe Confluence</i>\n"
        ]

        if long_candidates:
            lines.append("🟢 <b>TOP LONG CHANCEN:</b>")
            for a in long_candidates:
                sym = a.get("symbol", "")
                name = a.get("name", sym)
                score = a.get("score", 0)
                setup = a.get("setup_name", "Trend-Setup")
                price = a.get("price", 0)
                entry = a.get("entry_range", "-")
                sl = a.get("stop_loss", "-")
                tp2 = a.get("take_profit_2", "-")
                crv = a.get("crv", "-")

                lines.append(
                    f"• <b>{name}</b> (<code>{sym}</code>) – <b>{score}% Score</b>\n"
                    f"   <i>{setup}</i>\n"
                    f"   Kurs: {price:,.2f} $ | Entry: {entry}\n"
                    f"   SL: {sl} | TP2: {tp2} (CRV: {crv})"
                )
            lines.append("")

        if short_candidates:
            lines.append("🔴 <b>TOP SHORT CHANCEN:</b>")
            for a in short_candidates:
                sym = a.get("symbol", "")
                name = a.get("name", sym)
                score = a.get("score", 0)
                setup = a.get("setup_name", "Reversal-Setup")
                price = a.get("price", 0)
                entry = a.get("entry_range", "-")
                sl = a.get("stop_loss", "-")
                tp2 = a.get("take_profit_2", "-")
                crv = a.get("crv", "-")

                lines.append(
                    f"• <b>{name}</b> (<code>{sym}</code>) – <b>{score}% Score</b>\n"
                    f"   <i>{setup}</i>\n"
                    f"   Kurs: {price:,.2f} $ | Entry: {entry}\n"
                    f"   SL: {sl} | TP2: {tp2} (CRV: {crv})"
                )
            lines.append("")

        kb = {
            "inline_keyboard": [
                [{"text": "➕ Eigenen Trade anlegen", "callback_data": "menu_new_trade"}],
                [{"text": "🌐 Charts im Web-Dashboard öffnen", "url": "https://bbbdc.github.io/trading-dashboard/"}],
                [{"text": "🔙 Hauptmenü", "callback_data": "menu_main"}]
            ]
        }
        return "\n".join(lines), kb
    except Exception as e:
        return f"Fehler bei Top-Setups: {e}", None


def get_admin_hub_text_and_markup():
    """Generiert die Übersicht für das Master-Admin Kontrollzentrum."""
    try:
        from gemini_quota_tracker import get_quota_summary_for_dashboard
        quota = get_quota_summary_for_dashboard()
    except Exception:
        quota = {
            "total_keys_count": 4, "active_keys_count": 4, "requests_used_today": 0,
            "daily_limit": 80, "percent_used": 0.0, "requests_remaining": 80,
            "reset_countdown": "00:00 UTC", "active_key_masked": "AQ.Ab8...Ww"
        }

    port_active = 0
    win_rate = 0.0
    lev_pnl = 0.0
    if PORTFOLIO_FILE.exists():
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                pdata = json.load(f)
            port_active = len(pdata.get("active_trades", []))
            metrics = pdata.get("metrics", {})
            win_rate = metrics.get("win_rate_pct", 0.0)
            lev_pnl = metrics.get("total_leveraged_pnl_pct", 0.0)
        except Exception:
            pass

    cfg = load_config()
    auth_users = cfg.get("authorized_users", {})

    used = quota.get("requests_used_today", 0)
    limit = quota.get("daily_limit", 80)
    pct = quota.get("percent_used", 0.0)
    rem = quota.get("requests_remaining", 80)
    act_cnt = quota.get("active_keys_count", 4)
    tot_cnt = quota.get("total_keys_count", 4)
    masked = quota.get("active_key_masked", "AQ.***")
    reset_cd = quota.get("reset_countdown", "in wenigen Stunden")

    text = (
        f"⚙️ <b>Master-Admin Kontrollzentrum</b>\n"
        f"<i>Raspberry Pi 24/7 Trading Engine</i>\n\n"
        f"🔑 <b>Google Gemini API-Key Pool:</b>\n"
        f"• Keys aktiv: <b>{act_cnt} von {tot_cnt} Keys</b> ({masked})\n"
        f"• Verbrauch: <b>{used} / {limit} Anfragen</b> ({pct:.1f}%)\n"
        f"• Frei: <b>{rem} Anfragen</b> | Reset: <code>{reset_cd}</code>\n\n"
        f"🏛️ <b>Autonomes KI-Portfolio:</b>\n"
        f"• Win-Rate: <b>{win_rate}%</b> | Offene Trades: <b>{port_active}</b>\n"
        f"• Gehebelter Gesamt-PnL: <b>{lev_pnl:+.1f}%</b>\n\n"
        f"👥 <b>Benutzer:</b> {len(auth_users)} autorisiert\n"
        f"⚡ <b>Hintergrund-Dienst:</b> Systemd 24/7 aktiv\n"
    )

    kb = {
        "inline_keyboard": [
            [
                {"text": "🔑 API-Quota Details", "callback_data": "admin_quota_details"},
                {"text": "🏛️ Modell-Portfolio", "callback_data": "admin_model_portfolio"}
            ],
            [
                {"text": "👥 Benutzerverwaltung", "callback_data": "menu_users"},
                {"text": "⚡ Live Master-Scan", "callback_data": "action_trigger_scan"}
            ],
            [
                {"text": "🔙 Hauptmenü", "callback_data": "menu_main"}
            ]
        ]
    }
    return text, kb


def get_admin_quota_details_text_and_markup():
    """Detaillierte Aufschlüsselung aller API-Keys im Multi-Key Pool."""
    try:
        from gemini_quota_tracker import get_quota_summary_for_dashboard
        quota = get_quota_summary_for_dashboard()
    except Exception:
        quota = {}

    keys_detail = quota.get("keys_detail", [])
    used = quota.get("requests_used_today", 0)
    limit = quota.get("daily_limit", 80)
    pct = quota.get("percent_used", 0.0)

    lines = [
        f"🔑 <b>Google Gemini Multi-Key Quota Pool</b>\n",
        f"<b>Gesamt-Verbrauch:</b> {used} / {limit} Requests ({pct:.1f}%)\n",
        f"<b>Einzel-Key Status:</b>"
    ]

    for idx, kd in enumerate(keys_detail, 1):
        name = kd.get("name", f"Key {idx}")
        masked = kd.get("masked", "AQ.***")
        k_used = kd.get("requests_used", 0)
        k_lim = kd.get("daily_limit", 20)
        k_pct = kd.get("percent_used", 0.0)
        k_rem = kd.get("requests_remaining", 0)
        k_exh = kd.get("is_exhausted", False)
        status_sym = "🔴 Erschöpft" if k_exh else f"🟢 Aktiv ({k_rem} frei)"

        lines.append(
            f"• <b>{name}</b> (<code>{masked}</code>):\n"
            f"   Status: {status_sym}\n"
            f"   Verbrauch: {k_used} / {k_lim} ({k_pct:.0f}%)\n"
        )

    lines.append("🛡️ <i>Automatisches Failover: Sobald ein Key voll ist, switcht der Pi ohne Pause auf den nächsten Key.</i>")

    kb = {
        "inline_keyboard": [
            [{"text": "🔙 Zurück zur Admin-Zentrale", "callback_data": "menu_admin_hub"}]
        ]
    }
    return "\n".join(lines), kb


def get_admin_model_portfolio_text_and_markup():
    """Zeigt das autonome Modell-Portfolio streng für Admins an."""
    if not PORTFOLIO_FILE.exists():
        return "🏛️ Noch kein Modell-Portfolio vorhanden.", {"inline_keyboard": [[{"text": "🔙 Admin-Zentrale", "callback_data": "menu_admin_hub"}]]}

    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            port = json.load(f)
    except Exception as e:
        return f"Fehler beim Lesen des Portfolios: {e}", None

    active = port.get("active_trades", [])
    metrics = port.get("metrics", {})
    win_rate = metrics.get("win_rate_pct", 0)
    lev_pnl = metrics.get("total_leveraged_pnl_pct", 0.0)
    closed = port.get("closed_trades", [])

    lines = [
        f"🏛️ <b>Autonomes KI-High-Conviction Modell-Portfolio</b>\n",
        f"• <b>Win-Rate:</b> {win_rate}%",
        f"• <b>Offene Trades:</b> {len(active)}",
        f"• <b>Geschlossene Trades:</b> {len(closed)}",
        f"• <b>Gehebelter PnL:</b> {lev_pnl:+.2f}%\n"
    ]

    if active:
        lines.append("<b>Aktive Modell-Positionen:</b>")
        for t in active[:5]:
            sig_icon = "🟢" if t.get("direction") == "LONG" else "🔴"
            pnl = t.get("pnl_leveraged_pct", 0.0)
            lines.append(f"• {sig_icon} <b>{t.get('symbol')}</b> (Entry: {t.get('entry_price'):,.2f} $) | PnL: <b>{pnl:+.2f}%</b>")
        lines.append("")

    kb = {
        "inline_keyboard": [
            [{"text": "🌐 Im Web-Dashboard ansehen", "url": "https://bbbdc.github.io/trading-dashboard/"}],
            [{"text": "🔙 Zurück zur Admin-Zentrale", "callback_data": "menu_admin_hub"}]
        ]
    }
    return "\n".join(lines), kb


def get_user_positions_text_and_markup(user_id=None, username=None):
    """Generiert Text & Buttons für offene Trades eines Nutzers."""
    if not POSITIONS_FILE.exists():
        return "Du hast aktuell keine offenen Trades hinterlegt.", None

    try:
        from manage_positions import load_positions
        positions = load_positions()
    except Exception:
        positions = []

    user_id_str = str(user_id) if user_id else ""
    user_name_str = (username or "").lstrip("@").lower()

    # Filtern nach Nutzer (oder alle falls leer)
    matched = []
    for p in positions:
        p_uid = str(p.get("user_id", ""))
        p_uname = (p.get("user_name", "")).lstrip("@").lower()
        if not p_uid and not p_uname:
            # Altdaten ohne User werden zugeordnet
            matched.append(p)
        elif p_uid == user_id_str or (user_name_str and p_uname == user_name_str):
            matched.append(p)

    if not matched:
        kb = {
            "inline_keyboard": [
                [{"text": "➕ Jetzt ersten Trade anlegen", "callback_data": "menu_new_trade"}],
                [{"text": "🔙 Hauptmenü", "callback_data": "menu_main"}]
            ]
        }
        return "Du hast aktuell keine aktiven Trades im Tracking.", kb

    lines = [f"📊 <b>Deine aktiven Positionen ({len(matched)})</b>\n"]
    buttons = []

    for idx, p in enumerate(matched, 1):
        sym = p.get("symbol", "Unbekannt")
        sig = p.get("direction", "LONG")
        entry = float(p.get("entry_price", 0.0))
        lev = float(p.get("leverage", 1.0))
        curr = float(p.get("current_price", entry))
        pnl_base = float(p.get("pnl_pct", 0.0))
        pnl_lev = float(p.get("pnl_leveraged_pct", 0.0))
        rec = p.get("recommendation", {})

        icon = "🟢" if sig == "LONG" else "🔴"
        pnl_icon = "📈" if pnl_lev >= 0 else "📉"
        pnl_sign = "+" if pnl_lev >= 0 else ""

        entry_fmt = f"{entry:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        curr_fmt = f"{curr:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        lines.append(
            f"<b>{idx}. {icon} {p.get('name', sym)}</b> (<code>{sym}</code>)\n"
            f"   • <b>Richtung:</b> {sig} | <b>Hebel:</b> {lev:g}x\n"
            f"   • <b>Einstieg:</b> {entry_fmt} $ | <b>Aktuell:</b> {curr_fmt} $\n"
            f"   • {pnl_icon} <b>PnL:</b> <b>{pnl_sign}{pnl_lev:.2f}%</b> (Basis: {pnl_sign}{pnl_base:.2f}%)\n"
        )
        if rec and rec.get("action"):
            lines.append(f"   • 💡 <b>Empfehlung:</b> [{rec.get('action')}] {rec.get('title')}\n")
        lines.append("")

        pos_id = p.get("id") or sym
        buttons.append([
            {"text": f"🛑 {sym} schließen", "callback_data": f"close_confirm_{pos_id}"}
        ])

    buttons.append([
        {"text": "➕ Weiteren Trade anlegen", "callback_data": "menu_new_trade"},
        {"text": "🔄 Aktualisieren", "callback_data": "menu_my_trades"}
    ])
    buttons.append([
        {"text": "🔙 Zurück zum Hauptmenü", "callback_data": "menu_main"}
    ])

    return "\n".join(lines), {"inline_keyboard": buttons}


# ==============================================================================
# 5. ASYNCHRONE SCAN-AUSFÜHRUNG
# ==============================================================================
def trigger_background_scan(api, chat_id):
    global SCAN_RUNNING
    with SCAN_LOCK:
        if SCAN_RUNNING:
            api.send_message(chat_id, "⏳ Ein Scan läuft bereits im Hintergrund. Bitte warte einen kurzen Moment.")
            return
        SCAN_RUNNING = True

    api.send_message(
        chat_id,
        "🚀 <b>Live-Marktscan gestartet!</b>\n\n"
        "• Lade frische Kerzendaten über TradingView MCP...\n"
        "• Berechne Indikatoren & Confluence-Scores...\n"
        "• Analysiere KI-Setups & aktualisiere das Dashboard...\n\n"
        "<i>Du erhältst eine Benachrichtigung, sobald der Scan fertig ist!</i>"
    )

    def _worker():
        global SCAN_RUNNING
        try:
            cmd = [sys.executable, str(BASE_DIR / "update_dashboard.py"), "--git-push"]
            proc = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True, timeout=600)
            if proc.returncode == 0:
                summary = get_market_overview()
                api.send_message(
                    chat_id,
                    f"✅ <b>Marktscan erfolgreich abgeschlossen!</b>\n\n{summary}",
                    reply_markup=get_main_menu_keyboard("admin")
                )
            else:
                api.send_message(
                    chat_id,
                    f"⚠️ <b>Scan abgeschlossen mit Warnungen:</b>\n<pre>{proc.stderr[-300:]}</pre>"
                )
        except Exception as e:
            api.send_message(chat_id, f"❌ <b>Fehler beim Ausführen des Scans:</b> {e}")
        finally:
            with SCAN_LOCK:
                SCAN_RUNNING = False

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


# ==============================================================================
# 6. MESSAGE & CALLBACK EVENT HANDLER
# ==============================================================================
def handle_update(api, update):
    # Fall A: Callback Query (Klick auf einen Kachel-Button)
    if "callback_query" in update:
        cb = update["callback_query"]
        cb_id = cb["id"]
        from_user = cb.get("from", {})
        user_id = from_user.get("id")
        username = from_user.get("username", "")
        message = cb.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")
        data = cb.get("data", "")

        role = check_auth(user_id, username)
        if not role:
            api.answer_callback_query(cb_id, "Zugriff verweigert.", show_alert=True)
            return

        api.answer_callback_query(cb_id)
        process_callback(api, chat_id, message_id, user_id, username, role, data)
        return

    # Fall B: Reguläre Textnachricht
    if "message" in update:
        msg = update["message"]
        from_user = msg.get("from", {})
        user_id = from_user.get("id")
        username = from_user.get("username", "")
        first_name = from_user.get("first_name", "Trader")
        chat_id = msg.get("chat", {}).get("id")
        text = (msg.get("text") or "").strip()

        role = check_auth(user_id, username)

        # Nicht-autorisierter Benutzer
        if not role:
            handle_unauthorized_user(api, chat_id, user_id, username, first_name)
            return

        # Befehle auswerten
        if text.startswith("/start") or text.startswith("/menu"):
            USER_SESSIONS.pop(chat_id, None)
            welcome_text = (
                f"👋 <b>Willkommen im TradingView Super-Analyst Control Center!</b>\n\n"
                f"👤 <b>Angemeldet als:</b> {username or first_name} (<code>{role.upper()}</code>)\n"
                f"🍓 <b>System:</b> Raspberry Pi 24/7 Engine aktiv\n\n"
                f"Wähle eine Aktion aus den Kacheln unten:"
            )
            api.send_message(chat_id, welcome_text, reply_markup=get_main_menu_keyboard(role))
            return

        if text.startswith("/cancel"):
            USER_SESSIONS.pop(chat_id, None)
            api.send_message(chat_id, "Aktion abgebrochen.", reply_markup=get_main_menu_keyboard(role))
            return

        # Prüfen ob der Nutzer sich in einem Wizard befindet
        session = USER_SESSIONS.get(chat_id)
        if session:
            process_wizard_text_input(api, chat_id, user_id, username, session, text)
            return

        # Standard-Antwort bei beliebigem Text
        api.send_message(
            chat_id,
            "💡 Nutze die Kacheln für die Navigation oder tippe /menu, um das Hauptmenü aufzurufen.",
            reply_markup=get_main_menu_keyboard(role)
        )


def handle_unauthorized_user(api, chat_id, user_id, username, first_name):
    cfg = load_config()
    api.send_message(
        chat_id,
        f"👋 Hallo {first_name}!\n\n"
        f"Dieses Trading-System ist privat und durch den Raspberry Pi gesichert.\n"
        f"Deine Zugriffsanfrage wurde soeben an den Administrator gesendet. Bitte warte auf Freischaltung."
    )

    # Master-Admin benachrichtigen
    admin_cids = cfg.get("admin_chat_ids", [])
    admin_kb = {
        "inline_keyboard": [
            [
                {"text": f"✅ Freischalten: {username or user_id}", "callback_data": f"approve_user_{user_id}_{username}"},
                {"text": "❌ Ablehnen", "callback_data": f"reject_user_{user_id}"}
            ]
        ]
    }
    for acid in admin_cids:
        api.send_message(
            acid,
            f"🔔 <b>Neue Benutzer-Anfrage</b>\n\n"
            f"• <b>Name:</b> {first_name}\n"
            f"• <b>Username:</b> @{username}\n"
            f"• <b>User-ID:</b> <code>{user_id}</code>\n\n"
            f"Möchtest du diesen Benutzer freischalten?",
            reply_markup=admin_kb
        )


def process_callback(api, chat_id, message_id, user_id, username, role, data):
    # 1. Hauptmenü-Aktionen
    if data == "menu_main" or data == "menu_refresh":
        USER_SESSIONS.pop(chat_id, None)
        text = (
            f"🎛️ <b>Trading Super-Analyst – Hauptmenü</b>\n\n"
            f"👤 <b>Nutzer:</b> {username} ({role})\n"
            f"Wähle eine Aktion:"
        )
        api.edit_message_text(chat_id, message_id, text, reply_markup=get_main_menu_keyboard(role))
        return

    # Benachrichtigungseinstellungen
    if data == "menu_alert_settings":
        text, kb = get_alert_settings_text_and_markup(user_id)
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    if data == "menu_alert_tv_lists":
        text, kb = get_alert_tv_lists_text_and_markup(user_id)
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    if data.startswith("toggle_alert_wl_"):
        wl_name = data.replace("toggle_alert_wl_", "")
        prefs = get_user_preferences(user_id)
        current_wls = list(prefs.get("watchlists", get_available_tv_watchlists()))
        if wl_name in current_wls:
            current_wls.remove(wl_name)
        else:
            current_wls.append(wl_name)
        update_user_preference(user_id, "watchlists", current_wls)
        text, kb = get_alert_tv_lists_text_and_markup(user_id)
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    if data == "set_alert_wl_all_on":
        all_wls = get_available_tv_watchlists()
        update_user_preference(user_id, "watchlists", list(all_wls))
        text, kb = get_alert_tv_lists_text_and_markup(user_id)
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    if data == "set_alert_wl_all_off":
        update_user_preference(user_id, "watchlists", [])
        text, kb = get_alert_tv_lists_text_and_markup(user_id)
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    if data.startswith("toggle_alert_cat_"):
        cat_key = data.replace("toggle_alert_cat_", "")
        prefs = get_user_preferences(user_id)
        current_cats = list(prefs.get("categories", ["cat_crypto", "cat_ustech", "cat_dax", "cat_commodities"]))
        if cat_key in current_cats:
            current_cats.remove(cat_key)
        else:
            current_cats.append(cat_key)
        update_user_preference(user_id, "categories", current_cats)
        text, kb = get_alert_settings_text_and_markup(user_id)
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    if data == "cycle_alert_score":
        prefs = get_user_preferences(user_id)
        curr = prefs.get("min_score", 85)
        scores = [75, 80, 85, 90]
        next_score = scores[(scores.index(curr) + 1) % len(scores)] if curr in scores else 85
        update_user_preference(user_id, "min_score", next_score)
        text, kb = get_alert_settings_text_and_markup(user_id)
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    if data == "toggle_alert_my_trades":
        prefs = get_user_preferences(user_id)
        curr = prefs.get("only_my_trades", False)
        update_user_preference(user_id, "only_my_trades", not curr)
        text, kb = get_alert_settings_text_and_markup(user_id)
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    if data == "toggle_alert_master":
        prefs = get_user_preferences(user_id)
        curr = prefs.get("enabled", True)
        update_user_preference(user_id, "enabled", not curr)
        text, kb = get_alert_settings_text_and_markup(user_id)
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    if data == "menu_new_trade":
        USER_SESSIONS[chat_id] = {
            "wizard": "new_trade",
            "step": "SELECT_CATEGORY",
            "data": {"user_id": str(user_id), "user_name": username or f"User_{user_id}"}
        }
        api.edit_message_text(
            chat_id,
            message_id,
            "➕ <b>Neuen Trade anlegen</b>\n\nSchritt 1: Wähle die Anlageklasse:",
            reply_markup=get_category_keyboard()
        )
        return

    if data == "menu_my_trades":
        text, kb = get_user_positions_text_and_markup(user_id, username)
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    if data == "menu_top_setups":
        text, kb = get_top_setups_text_and_markup()
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    if data == "menu_admin_hub":
        if role != "admin":
            api.edit_message_text(chat_id, message_id, "⚠️ Diese Funktion ist dem Master-Admin vorbehalten.", reply_markup=get_main_menu_keyboard(role))
            return
        text, kb = get_admin_hub_text_and_markup()
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    if data == "admin_quota_details":
        if role != "admin":
            api.edit_message_text(chat_id, message_id, "⚠️ Diese Funktion ist dem Master-Admin vorbehalten.", reply_markup=get_main_menu_keyboard(role))
            return
        text, kb = get_admin_quota_details_text_and_markup()
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    if data == "admin_model_portfolio" or data == "menu_model_portfolio":
        if role != "admin":
            api.edit_message_text(chat_id, message_id, "⚠️ Diese Funktion ist dem Master-Admin vorbehalten.", reply_markup=get_main_menu_keyboard(role))
            return
        text, kb = get_admin_model_portfolio_text_and_markup()
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    if data == "menu_market_scan":
        summary = get_market_overview(role=role)
        if role == "admin":
            kb = {
                "inline_keyboard": [
                    [{"text": "⚡ Jetzt Live-Scan starten", "callback_data": "action_trigger_scan"}],
                    [{"text": "🎯 Top-Setups ansehen", "callback_data": "menu_top_setups"}],
                    [{"text": "🌐 Web-Dashboard öffnen", "url": "https://bbbdc.github.io/trading-dashboard/"}],
                    [{"text": "🔙 Hauptmenü", "callback_data": "menu_main"}]
                ]
            }
        else:
            kb = {
                "inline_keyboard": [
                    [{"text": "🎯 Top-Setups ansehen", "callback_data": "menu_top_setups"}],
                    [{"text": "🌐 Web-Dashboard öffnen", "url": "https://bbbdc.github.io/trading-dashboard/"}],
                    [{"text": "🔙 Hauptmenü", "callback_data": "menu_main"}]
                ]
            }
        api.edit_message_text(chat_id, message_id, summary, reply_markup=kb)
        return

    if data == "action_trigger_scan":
        if role != "admin":
            api.edit_message_text(chat_id, message_id, "⚠️ Der Live Master-Scan ist dem Master-Admin vorbehalten.", reply_markup=get_main_menu_keyboard(role))
            return
        trigger_background_scan(api, chat_id)
        return

    if data == "menu_dashboard_links":
        text = (
            "🌐 <b>Web-Dashboard & Signal-Historie</b>\n\n"
            "Hier kannst du das interaktive Dashboard mit allen Charts und Auswertungen aufrufen:"
        )
        kb = {
            "inline_keyboard": [
                [{"text": "📊 Live Web-Dashboard", "url": "https://bbbdc.github.io/trading-dashboard/"}],
                [{"text": "📜 Signal-Historie & Treffer", "url": "https://bbbdc.github.io/trading-dashboard/history.html"}],
                [{"text": "🔙 Hauptmenü", "callback_data": "menu_main"}]
            ]
        }
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    if data == "menu_users" and role == "admin":
        cfg = load_config()
        users = cfg.get("authorized_users", {})
        u_lines = ["👥 <b>Autorisierte Benutzer</b>\n"]
        for uname, udata in users.items():
            u_lines.append(f"• <b>@{uname}</b> – Rolle: <code>{udata.get('role', 'trader')}</code>")
        kb = {
            "inline_keyboard": [
                [{"text": "🔙 Hauptmenü", "callback_data": "menu_main"}]
            ]
        }
        api.edit_message_text(chat_id, message_id, "\n".join(u_lines), reply_markup=kb)
        return

    if data == "action_cancel":
        USER_SESSIONS.pop(chat_id, None)
        api.edit_message_text(chat_id, message_id, "Aktion abgebrochen.", reply_markup=get_main_menu_keyboard(role))
        return

    # 2. Neuer Trade – Kategorie gewählt
    if data in ("cat_crypto", "cat_ustech", "cat_dax", "cat_commodities"):
        cat_names = {
            "cat_crypto": "₿ Krypto",
            "cat_ustech": "💻 US Tech",
            "cat_dax": "🇩🇪 DAX / EU",
            "cat_commodities": "🥇 Rohstoffe"
        }
        api.edit_message_text(
            chat_id,
            message_id,
            f"Kategorie: <b>{cat_names.get(data)}</b>\n\nWähle das Symbol aus oder gib einen Ticker ein:",
            reply_markup=get_symbols_keyboard_for_category(data)
        )
        return

    if data == "cat_custom":
        session = USER_SESSIONS.setdefault(chat_id, {"wizard": "new_trade", "data": {}})
        session["step"] = "WAITING_TICKER"
        api.edit_message_text(
            chat_id,
            message_id,
            "✍️ <b>Ticker manuell eingeben:</b>\n\n"
            "Schreibe einfach den Namen oder Ticker als Nachricht in den Chat\n"
            "<i>(z. B. <code>BTC</code>, <code>NVDA</code>, <code>SOL</code> oder <code>BINANCE:ETHUSDT</code>):</i>"
        )
        return

    # 3. Symbol gewählt
    if data.startswith("sym_"):
        symbol = data[4:]
        session = USER_SESSIONS.setdefault(chat_id, {"wizard": "new_trade", "data": {}})
        session["data"]["symbol"] = symbol
        session["step"] = "SELECT_DIRECTION"

        live_price = find_asset_price(symbol)
        session["data"]["live_price"] = live_price
        price_info = f" (Live-Referenzpreis: ~{live_price:,.2f} $)" if live_price else ""

        api.edit_message_text(
            chat_id,
            message_id,
            f"Ausgewählt: <b>{symbol}</b>{price_info}\n\nSchritt 2: Wähle die Richtung:",
            reply_markup=get_direction_keyboard()
        )
        return

    # 4. Richtung gewählt
    if data.startswith("dir_"):
        direction = data[4:]
        session = USER_SESSIONS.get(chat_id)
        if not session:
            return
        session["data"]["direction"] = direction
        session["step"] = "WAITING_PRICE"
        live_price = session["data"].get("live_price")

        prompt_text = (
            f"Symbol: <b>{session['data']['symbol']}</b> ({direction})\n\n"
            f"Schritt 3: Gib deinen <b>Einstiegskurs</b> ein.\n"
        )
        if live_price:
            prompt_text += f"Du kannst den aktuellen Kurs per Klick übernehmen oder deinen Wunschpreis tippen:"
        else:
            prompt_text += "Schreibe deinen Einstiegskurs als Zahl in den Chat (z. B. <code>68450</code> oder <code>182.50</code>):"

        api.edit_message_text(chat_id, message_id, prompt_text, reply_markup=get_entry_price_keyboard(live_price))
        return

    # 5. Live-Preis übernommen
    if data.startswith("price_"):
        price_val = float(data[6:])
        session = USER_SESSIONS.get(chat_id)
        if not session:
            return
        session["data"]["entry_price"] = price_val
        session["step"] = "SELECT_LEVERAGE"

        api.edit_message_text(
            chat_id,
            message_id,
            f"Einstieg: <b>{price_val:,.2f} $</b>\n\nSchritt 4: Wähle den <b>Hebel</b>:",
            reply_markup=get_leverage_keyboard()
        )
        return

    # 6. Hebel gewählt
    if data.startswith("lev_"):
        lev_val = data[4:]
        session = USER_SESSIONS.get(chat_id)
        if not session:
            return
        if lev_val == "custom":
            session["step"] = "WAITING_LEVERAGE"
            api.edit_message_text(
                chat_id,
                message_id,
                "✍️ Gib den gewünschten Hebel als Zahl ein (z. B. <code>7</code> oder <code>15</code>):"
            )
            return

        session["data"]["leverage"] = float(lev_val)
        session["step"] = "WAITING_NOTE"
        api.edit_message_text(
            chat_id,
            message_id,
            f"Hebel: <b>{lev_val}x</b>\n\nSchritt 5: Optionale Notiz / Kursziel hinterlegen?\n"
            "<i>(Einfach als Nachricht tippen oder überspringen)</i>",
            reply_markup=get_note_keyboard()
        )
        return

    if data == "note_skip":
        session = USER_SESSIONS.get(chat_id)
        if not session:
            return
        session["data"]["note"] = ""
        render_trade_summary_and_confirm(api, chat_id, message_id, session["data"])
        return

    # 7. Trade final speichern
    if data == "trade_confirm_save":
        session = USER_SESSIONS.get(chat_id)
        if not session:
            return
        t_data = session["data"]
        USER_SESSIONS.pop(chat_id, None)

        api.edit_message_text(
            chat_id,
            message_id,
            f"⏳ Speichere Trade <b>{t_data['symbol']}</b> und aktualisiere Dashboard..."
        )

        try:
            from manage_positions import add_position
            add_position(
                symbol=t_data["symbol"],
                direction=t_data["direction"],
                entry_price=t_data["entry_price"],
                leverage=t_data.get("leverage", 1.0),
                note=t_data.get("note", ""),
                user_id=str(user_id),
                user_name=username or f"User_{user_id}",
                sync_db=True,
                git_push=True
            )
            success_text = (
                f"✅ <b>Position erfolgreich gespeichert!</b>\n\n"
                f"• <b>Symbol:</b> {t_data['symbol']}\n"
                f"• <b>Richtung:</b> {t_data['direction']}\n"
                f"• <b>Einstieg:</b> {t_data['entry_price']:,.2f} $\n"
                f"• <b>Hebel:</b> {t_data.get('leverage', 1.0)}x\n"
                f"• <b>Nutzer:</b> {username}\n\n"
                f"🍓 Der Trade wird ab sofort 24/7 durch den Raspberry Pi überwacht und ist auf deinem Web-Dashboard live!"
            )
            kb = {
                "inline_keyboard": [
                    [{"text": "📊 Meine Trades ansehen", "callback_data": "menu_my_trades"}],
                    [{"text": "🌐 Im Web-Dashboard öffnen", "url": "https://bbbdc.github.io/trading-dashboard/"}],
                    [{"text": "🔙 Hauptmenü", "callback_data": "menu_main"}]
                ]
            }
            api.edit_message_text(chat_id, message_id, success_text, reply_markup=kb)
        except Exception as e:
            api.edit_message_text(chat_id, message_id, f"❌ Fehler beim Speichern: {e}", reply_markup=get_main_menu_keyboard(role))
        return

    # 8. Trade schließen – Bestätigung
    if data.startswith("close_confirm_"):
        pos_id = data[14:]
        kb = {
            "inline_keyboard": [
                [{"text": "🛑 Ja, Trade jetzt schließen", "callback_data": f"close_execute_{pos_id}"}],
                [{"text": "❌ Nein, Trade behalten", "callback_data": "menu_my_trades"}]
            ]
        }
        api.edit_message_text(
            chat_id,
            message_id,
            f"Möchtest du die Position <b>{pos_id}</b> wirklich schließen?",
            reply_markup=kb
        )
        return

    if data.startswith("close_execute_"):
        pos_id = data[14:]
        api.edit_message_text(chat_id, message_id, f"⏳ Schließe Position <b>{pos_id}</b>...")
        try:
            from manage_positions import remove_position
            success = remove_position(pos_id, user_id=str(user_id), sync_db=True, git_push=True)
            if success:
                api.edit_message_text(
                    chat_id,
                    message_id,
                    f"✅ <b>Position {pos_id} wurde erfolgreich geschlossen!</b>\n\nDas Dashboard wurde aktualisiert.",
                    reply_markup=get_main_menu_keyboard(role)
                )
            else:
                api.edit_message_text(
                    chat_id,
                    message_id,
                    f"⚠️ Position konnte nicht gefunden werden.",
                    reply_markup=get_main_menu_keyboard(role)
                )
        except Exception as e:
            api.edit_message_text(chat_id, message_id, f"❌ Fehler beim Schließen: {e}", reply_markup=get_main_menu_keyboard(role))
        return

    # 9. Admin: Benutzer freischalten
    if data.startswith("approve_user_") and role == "admin":
        parts = data.split("_")
        target_uid = parts[2]
        target_uname = parts[3] if len(parts) > 3 else f"User_{target_uid}"

        cfg = load_config()
        cfg.setdefault("authorized_users", {})[target_uname] = {
            "name": target_uname,
            "chat_id": target_uid,
            "role": "trader",
            "added_at": datetime.now(timezone.utc).isoformat()
        }
        save_config(cfg)

        api.edit_message_text(chat_id, message_id, f"✅ Benutzer <b>@{target_uname}</b> (ID: {target_uid}) wurde erfolgreich als Trader freigeschaltet!")
        # Den freigeschalteten Nutzer benachrichtigen
        try:
            api.send_message(
                target_uid,
                "🎉 <b>Dein Zugang wurde freigeschaltet!</b>\n\nTippe /start, um das Hauptmenü zu öffnen.",
                reply_markup=get_main_menu_keyboard("trader")
            )
        except Exception:
            pass
        return


def process_wizard_text_input(api, chat_id, user_id, username, session, text):
    step = session.get("step")

    if step == "WAITING_TICKER":
        raw_ticker = text.upper().strip()
        # Automatisches Präfixen falls nötig
        if ":" not in raw_ticker:
            if raw_ticker in ("BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "ADA", "AVAX"):
                symbol = f"BINANCE:{raw_ticker}USDT"
            elif raw_ticker in ("NVDA", "AAPL", "TSLA", "MSFT", "AMZN", "META", "GOOGL"):
                symbol = f"NASDAQ:{raw_ticker}"
            elif raw_ticker in ("SAP", "SIE", "ALV", "MBG", "BMW"):
                symbol = f"XETR:{raw_ticker}"
            elif raw_ticker in ("GOLD", "SILVER"):
                symbol = f"TVC:{raw_ticker}"
            else:
                symbol = raw_ticker
        else:
            symbol = raw_ticker

        session["data"]["symbol"] = symbol
        session["step"] = "SELECT_DIRECTION"
        live_price = find_asset_price(symbol)
        session["data"]["live_price"] = live_price
        price_info = f" (Live-Preis: ~{live_price:,.2f} $)" if live_price else ""

        api.send_message(
            chat_id,
            f"Ausgewählt: <b>{symbol}</b>{price_info}\n\nSchritt 2: Wähle die Richtung:",
            reply_markup=get_direction_keyboard()
        )
        return

    if step == "WAITING_PRICE":
        cleaned = text.replace("$", "").replace("€", "").replace(",", ".").strip()
        try:
            price_val = float(cleaned)
            if price_val <= 0:
                raise ValueError()
        except ValueError:
            api.send_message(chat_id, "⚠️ Ungültiger Preis. Bitte gib eine Zahl ein (z. B. 68450.50):")
            return

        session["data"]["entry_price"] = price_val
        session["step"] = "SELECT_LEVERAGE"
        api.send_message(
            chat_id,
            f"Einstiegskurs: <b>{price_val:,.2f} $</b>\n\nSchritt 4: Wähle den <b>Hebel</b>:",
            reply_markup=get_leverage_keyboard()
        )
        return

    if step == "WAITING_LEVERAGE":
        cleaned = text.replace("x", "").replace("X", "").replace(",", ".").strip()
        try:
            lev_val = float(cleaned)
            if lev_val < 1:
                lev_val = 1.0
        except ValueError:
            api.send_message(chat_id, "⚠️ Ungültiger Hebel. Bitte gib eine Zahl ein (z. B. 5):")
            return

        session["data"]["leverage"] = lev_val
        session["step"] = "WAITING_NOTE"
        api.send_message(
            chat_id,
            f"Hebel: <b>{lev_val:g}x</b>\n\nSchritt 5: Optionale Notiz / Kursziel hinterlegen?\n"
            "<i>(Einfach antworten oder Button unten nutzen)</i>",
            reply_markup=get_note_keyboard()
        )
        return

    if step == "WAITING_NOTE":
        session["data"]["note"] = text.strip()
        render_trade_summary_and_confirm(api, chat_id, None, session["data"])
        return


def render_trade_summary_and_confirm(api, chat_id, message_id, data):
    sym = data.get("symbol")
    sig = data.get("direction")
    entry = data.get("entry_price", 0.0)
    lev = data.get("leverage", 1.0)
    note = data.get("note", "")

    sig_icon = "🟢" if sig == "LONG" else "🔴"
    summary_text = (
        f"📋 <b>Trade-Zusammenfassung</b>\n\n"
        f"• <b>Symbol:</b> <code>{sym}</code>\n"
        f"• <b>Richtung:</b> {sig_icon} <b>{sig}</b>\n"
        f"• <b>Einstiegskurs:</b> {entry:,.2f} $\n"
        f"• <b>Hebel:</b> {lev:g}x\n"
    )
    if note:
        summary_text += f"• <b>Notiz:</b> <i>{note}</i>\n"

    summary_text += "\nKlicke auf <b>Bestätigen</b>, um den Trade sofort anzulegen:"

    if message_id:
        api.edit_message_text(chat_id, message_id, summary_text, reply_markup=get_confirm_trade_keyboard())
    else:
        api.send_message(chat_id, summary_text, reply_markup=get_confirm_trade_keyboard())


# ==============================================================================
# 7. BOT RUNNER & SYSTEMD LOOP
# ==============================================================================
def main():
    logger.info("Starte TradingView Telegram Bot...")
    cfg = load_config()
    token = cfg.get("bot_token")
    if not token or "YOUR_" in token:
        logger.error("Kein gültiger Bot Token in telegram_config.json hinterlegt!")
        sys.exit(1)

    api = TelegramAPI(token)

    # Bot Identität abfragen
    try:
        me_resp = api.session.get(f"{api.base_url}/getMe", timeout=10).json()
        if me_resp.get("ok"):
            b_info = me_resp.get("result", {})
            logger.info(f"Bot erfolgreich verbunden: @{b_info.get('username')} ({b_info.get('first_name')})")
        else:
            logger.error(f"Fehler bei getMe: {me_resp}")
    except Exception as e:
        logger.error(f"Verbindung zu Telegram fehlgeschlagen: {e}")

    offset = None
    logger.info("Bot Polling-Schleife gestartet.")

    while True:
        try:
            updates = api.get_updates(offset=offset, timeout=25)
            for upd in updates:
                offset = upd["update_id"] + 1
                try:
                    handle_update(api, upd)
                except Exception as ex:
                    logger.error(f"Fehler bei Update {upd.get('update_id')}: {ex}", exc_info=True)
        except Exception as e:
            logger.error(f"Unerwarteter Fehler im Polling: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
