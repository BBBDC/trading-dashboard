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


def sync_dashboard_auth_async():
    """Kompiliert das Dashboard neu und pusht geänderte Benutzerrechte zu GitHub Pages."""
    def _worker():
        try:
            import subprocess
            subprocess.run([sys.executable, str(BASE_DIR / "build_dashboard.py")], check=True)
            from update_dashboard import git_sync_dashboard
            git_sync_dashboard()
        except Exception as e:
            print(f"Fehler bei Dashboard-Auth-Sync: {e}", file=sys.stderr)

    threading.Thread(target=_worker, daemon=True).start()


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
        "Eigene Trades": "⭐",
        "Tradegate Werte": "🏛️"
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


def fmt_price(val):
    if val is None:
        return "-"
    try:
        val = float(val)
        if val >= 100:
            return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        elif val >= 1:
            return f"{val:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            return f"{val:,.6f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(val)


def get_stop_loss_keyboard(direction="LONG", entry_price=0.0):
    buttons = []
    if entry_price and entry_price > 0:
        row = []
        if direction.upper() == "LONG":
            sl_pcts = [(-2, 0.98), (-5, 0.95), (-10, 0.90)]
        else:
            sl_pcts = [(2, 1.02), (5, 1.05), (10, 1.10)]
        for pct, factor in sl_pcts:
            val = round(entry_price * factor, 4 if entry_price < 10 else 2)
            lbl = f"🛑 {pct:+d}% ({fmt_price(val)})"
            row.append({"text": lbl, "callback_data": f"sl_quick_{val:g}"})
        buttons.append(row)

    buttons.append([{"text": "⏭️ Ohne Stop-Loss fortfahren", "callback_data": "sl_skip"}])
    buttons.append([{"text": "❌ Abbrechen", "callback_data": "action_cancel"}])
    return {"inline_keyboard": buttons}


def get_take_profit_keyboard(direction="LONG", entry_price=0.0):
    buttons = []
    if entry_price and entry_price > 0:
        row = []
        if direction.upper() == "LONG":
            tp_pcts = [(5, 1.05), (10, 1.10), (20, 1.20)]
        else:
            tp_pcts = [(-5, 0.95), (-10, 0.90), (-20, 0.80)]
        for pct, factor in tp_pcts:
            val = round(entry_price * factor, 4 if entry_price < 10 else 2)
            lbl = f"🎯 {pct:+d}% ({fmt_price(val)})"
            row.append({"text": lbl, "callback_data": f"tp_quick_{val:g}"})
        buttons.append(row)

    buttons.append([{"text": "⏭️ Ohne Take-Profit fortfahren", "callback_data": "tp_skip"}])
    buttons.append([{"text": "❌ Abbrechen", "callback_data": "action_cancel"}])
    return {"inline_keyboard": buttons}


def get_edit_sl_keyboard(direction="LONG", entry_price=0.0, current_sl=None):
    buttons = []
    if current_sl is not None:
        buttons.append([{"text": f"🔄 SL beibehalten ({fmt_price(current_sl)} $)", "callback_data": "edit_sl_keep"}])
        buttons.append([{"text": "❌ Stop-Loss entfernen", "callback_data": "edit_sl_clear"}])
    else:
        buttons.append([{"text": "⏭️ Ohne Stop-Loss weiter", "callback_data": "edit_sl_keep"}])

    if entry_price and entry_price > 0:
        row = []
        if direction.upper() == "LONG":
            sl_pcts = [(-2, 0.98), (-5, 0.95), (-10, 0.90)]
        else:
            sl_pcts = [(2, 1.02), (5, 1.05), (10, 1.10)]
        for pct, factor in sl_pcts:
            val = round(entry_price * factor, 4 if entry_price < 10 else 2)
            row.append({"text": f"{pct:+d}% ({fmt_price(val)})", "callback_data": f"edit_sl_quick_{val:g}"})
        buttons.append(row)

    buttons.append([{"text": "🔙 Abbrechen", "callback_data": "menu_my_trades"}])
    return {"inline_keyboard": buttons}


def get_edit_tp_keyboard(direction="LONG", entry_price=0.0, current_tp=None):
    buttons = []
    if current_tp is not None:
        buttons.append([{"text": f"🔄 TP beibehalten ({fmt_price(current_tp)} $)", "callback_data": "edit_tp_keep"}])
        buttons.append([{"text": "❌ Take-Profit entfernen", "callback_data": "edit_tp_clear"}])
    else:
        buttons.append([{"text": "⏭️ Ohne Take-Profit weiter", "callback_data": "edit_tp_keep"}])

    if entry_price and entry_price > 0:
        row = []
        if direction.upper() == "LONG":
            tp_pcts = [(5, 1.05), (10, 1.10), (20, 1.20)]
        else:
            tp_pcts = [(-5, 0.95), (-10, 0.90), (-20, 0.80)]
        for pct, factor in tp_pcts:
            val = round(entry_price * factor, 4 if entry_price < 10 else 2)
            row.append({"text": f"{pct:+d}% ({fmt_price(val)})", "callback_data": f"edit_tp_quick_{val:g}"})
        buttons.append(row)

    buttons.append([{"text": "🔙 Abbrechen", "callback_data": "menu_my_trades"}])
    return {"inline_keyboard": buttons}


def get_confirm_edit_sltp_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "💾 Jetzt speichern & übernehmen", "callback_data": "edit_sltp_save"}],
            [{"text": "❌ Abbrechen", "callback_data": "menu_my_trades"}]
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


def search_matching_assets(query: str, max_results: int = 6):
    """
    Sucht fuzzy nach passenden Assets in market_analysis_db.json
    anhand von Ticker, Name, Symbol, Börse oder Alias.
    """
    if not query or not query.strip():
        return []

    q = query.strip()
    q_lower = q.lower()
    q_upper = q.upper()

    # Bekannte Ticker- und Namen-Aliase
    aliases = {
        "PAY": ["TRADEGATE:2PP", "NASDAQ:PYPL"],
        "PAYPAL": ["TRADEGATE:2PP", "NASDAQ:PYPL"],
        "RHEIN": ["TRADEGATE:RHM", "XETR:RHM"],
        "RHEINMETALL": ["TRADEGATE:RHM", "XETR:RHM"],
        "BTC": ["COINBASE:BTCUSD", "BINANCE:BTCUSD", "INDEX:BTCUSD"],
        "BITCOIN": ["COINBASE:BTCUSD", "BINANCE:BTCUSD"],
        "ETH": ["COINBASE:ETHUSD", "BITSTAMP:ETHUSD"],
        "ETHEREUM": ["COINBASE:ETHUSD", "BITSTAMP:ETHUSD"],
        "SOL": ["COINBASE:SOLUSD"],
        "SOLANA": ["COINBASE:SOLUSD"],
        "XRP": ["BINANCE:XRPUSDT", "KRAKEN:XRPUSD"],
        "RIPPLE": ["BINANCE:XRPUSDT"],
        "APPLE": ["NASDAQ:AAPL"],
        "AAPL": ["NASDAQ:AAPL"],
        "NVIDIA": ["NASDAQ:NVDA", "TRADEGATE:NVD"],
        "NVDA": ["NASDAQ:NVDA"],
        "MICROSOFT": ["NASDAQ:MSFT", "TRADEGATE:MSF"],
        "MSFT": ["NASDAQ:MSFT"],
        "TESLA": ["NASDAQ:TSLA", "TRADEGATE:TL0"],
        "TSLA": ["NASDAQ:TSLA"],
        "AMAZON": ["NASDAQ:AMZN", "TRADEGATE:AMZ"],
        "AMZN": ["NASDAQ:AMZN"],
        "META": ["NASDAQ:META", "TRADEGATE:FB2A"],
        "ALV": ["XETR:ALV", "TRADEGATE:ALV"],
        "ALLIANZ": ["XETR:ALV", "TRADEGATE:ALV"],
        "SIE": ["XETR:SIE", "TRADEGATE:SIE"],
        "SIEMENS": ["XETR:SIE", "TRADEGATE:SIE"],
        "SAP": ["XETR:SAP", "TRADEGATE:SAP"],
        "BMW": ["XETR:BMW", "TRADEGATE:BMW"],
        "MBG": ["XETR:MBG", "TRADEGATE:MBG"],
        "MERCEDES": ["XETR:MBG", "TRADEGATE:MBG"],
        "GOLD": ["TVC:GOLD", "AMEX:GLD"],
        "SILVER": ["TVC:SILVER"],
        "SILBER": ["TVC:SILVER"],
        "GAS": ["NYMEX:NG1!"],
        "ERDGAS": ["NYMEX:NG1!"],
        "OEL": ["TVC:USOIL"],
        "OIL": ["TVC:USOIL"]
    }

    db_assets = []
    if DB_FILE.exists():
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                db_assets = json.load(f).get("assets", [])
        except Exception:
            pass

    alias_targets = []
    for k, v in aliases.items():
        if k == q_upper or k in q_upper or q_upper in k:
            alias_targets.extend(v)

    scored_candidates = []
    for a in db_assets:
        sym = a.get("symbol", "")
        name = a.get("name", "")
        ticker = sym.split(":")[-1].upper()
        name_lower = name.lower()
        score = 0

        # Exact Matches
        if sym.upper() == q_upper:
            score = 100
        elif sym in alias_targets:
            score = 95
        elif ticker == q_upper:
            score = 90
        elif name_lower == q_lower:
            score = 88
        elif ticker.startswith(q_upper) or q_upper.startswith(ticker):
            score = 80
        elif name_lower.startswith(q_lower):
            score = 75
        elif q_lower in name_lower:
            score = 70
        elif q_upper in ticker or q_upper in sym.upper():
            score = 65
        elif any(part in name_lower for part in q_lower.split() if len(part) > 2):
            score = 50

        if score > 0:
            scored_candidates.append((score, a))

    # Sortieren nach Relevanz
    scored_candidates.sort(key=lambda x: x[0], reverse=True)

    seen = set()
    final_list = []
    for score, a in scored_candidates:
        sym = a.get("symbol", "")
        if sym in seen:
            continue
        seen.add(sym)
        final_list.append({
            "symbol": sym,
            "name": a.get("name", sym),
            "ticker": sym.split(":")[-1],
            "price": float(a.get("price", 0.0)),
            "signal": a.get("signal", "NEUTRAL"),
            "score": a.get("score", 0),
            "currency": "€" if "TRADEGATE" in sym or "XETR" in sym else "$"
        })
        if len(final_list) >= max_results:
            break

    return final_list


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
    """Generiert die formatierten Top-Setups als übersichtliche Signal-Cards mit 1-Klick-Aktionen."""
    if not DB_FILE.exists():
        return "⚠️ Noch keine Marktdatenbank vorhanden. Bitte starte zuerst einen Scan.", None

    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)

        ts = db.get("timestamp", "Unbekannt")
        assets = db.get("assets", [])

        # Top High-Conviction Setups filtern (Score >= 85%)
        candidates = sorted(
            [a for a in assets if a.get("signal") in ("LONG", "SHORT") and a.get("score", 0) >= 85],
            key=lambda x: x.get("score", 0),
            reverse=True
        )[:4]

        if not candidates:
            return (
                "🎯 <b>Aktuell keine Top-Setups mit Score ≥ 85% aktiv.</b>\n\n"
                "Der Markt konsolidiert oder bildet aktuell neue Liquiditätszonen. "
                "Sobald neue High-Conviction Signale vorliegen, wirst du sofort benachrichtigt.",
                {"inline_keyboard": [
                    [{"text": "⚡ Jetzt Live-Scan starten", "callback_data": "action_trigger_scan"}],
                    [{"text": "➕ Eigenen Trade anlegen", "callback_data": "menu_new_trade"}],
                    [{"text": "🔙 Hauptmenü", "callback_data": "menu_main"}]
                ]}
            )

        lines = [
            f"🎯 <b>High-Conviction Top-Setups ({len(candidates)})</b>",
            f"<i>Stand: {ts} · Multi-Timeframe Confluence</i>\n"
        ]

        buttons = []

        for a in candidates:
            sig = a.get("signal", "LONG")
            icon = "🟢" if sig == "LONG" else "🔴"
            sym = a.get("symbol", "")
            name = a.get("name", sym)
            ticker = sym.split(":")[-1]
            score = a.get("score", 0)
            curr = "€" if "TRADEGATE" in sym or "XETR" in sym else "$"

            # Zeithorizont & Handlungs-Timeframe ermitteln
            p_tf = a.get("primary_timeframe") or ("1D" if "1d" in str(a.get("reasons", "")).lower() else "4h")
            tf_lbl = a.get("timeframe_label") or ("1D Position" if p_tf == "1D" else "4h Core Swing")
            holding = a.get("holding_period") or ("1–3 Wochen" if p_tf == "1D" else "2–5 Tage")
            setup = a.get("setup_name", "Konfluenz-Setup")
            reasons = a.get("reasons", [])

            score_badge = "🔥 Exzellent" if score >= 92 else "✨ Stark"

            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"{icon} <b>{sig} · {p_tf} Chart ({holding})</b>")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"📈 <b>{name}</b> (<code>{ticker}</code>) · <i>{a.get('category', 'Asset')}</i>")
            lines.append(f"⏱️ <b>Handlungs-Chart:</b> <b><code>{p_tf} Chart</code></b> · <i>{tf_lbl} ({holding})</i>")
            lines.append(f"🏆 <b>KI-Score:</b> <b>{score}%</b> ({score_badge})\n")

            curr_p = float(a.get("price", 0.0))
            entry = float(a.get("entry_range", [curr_p])[0]) if a.get("entry_range") else curr_p
            sl = float(a.get("stop_loss", 0.0))
            tp1 = float(a.get("take_profit_1", 0.0))
            tp2 = float(a.get("take_profit_2", 0.0))
            crv = a.get("crv", "2.5")

            if entry > 0 and sl > 0:
                if sig == "LONG":
                    sl_pct = ((sl - entry) / entry) * 100.0
                    tp1_pct = ((tp1 - entry) / entry) * 100.0 if tp1 > 0 else 0.0
                    tp2_pct = ((tp2 - entry) / entry) * 100.0 if tp2 > 0 else 0.0
                else:
                    sl_pct = ((entry - sl) / entry) * 100.0
                    tp1_pct = ((entry - tp1) / entry) * 100.0 if tp1 > 0 else 0.0
                    tp2_pct = ((entry - tp2) / entry) * 100.0 if tp2 > 0 else 0.0

                entry_fmt = f"{entry:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                sl_fmt = f"{sl:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                tp1_fmt = f"{tp1:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if tp1 > 0 else "-"
                tp2_fmt = f"{tp2:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if tp2 > 0 else "-"

                lines.append(f"📍 <b>Einstieg:</b>   <code>{entry_fmt} {curr}</code>")
                lines.append(f"🛑 <b>Stop-Loss:</b>  <code>{sl_fmt} {curr}</code> (<b>{sl_pct:+.1f}%</b>)")
                if tp1 > 0:
                    lines.append(f"🎯 <b>Teilziel 1:</b> <code>{tp1_fmt} {curr}</code> (<b>{tp1_pct:+.1f}%</b> · 50% TP)")
                if tp2 > 0:
                    lines.append(f"🚀 <b>Hauptziel 2:</b> <code>{tp2_fmt} {curr}</code> (<b>{tp2_pct:+.1f}%</b> · CRV 1:{crv})\n")

            lines.append(f"💡 <b>Setup:</b> {setup}")
            if reasons:
                lines.append(f"📊 <b>Auslöser:</b> {reasons[0][:110]}")
            lines.append("")

            buttons.append([
                {"text": f"➕ {ticker} Trade mit 1 Klick anlegen", "callback_data": f"wiz_adopt:{sym}"}
            ])

        buttons.append([{"text": "➕ Eigenen Trade manuell anlegen", "callback_data": "menu_new_trade"}])
        buttons.append([{"text": "🌐 Charts im Web-Dashboard öffnen", "url": "https://bbbdc.github.io/trading-dashboard/"}])
        buttons.append([{"text": "🔙 Hauptmenü", "callback_data": "menu_main"}])

        kb = {"inline_keyboard": buttons}
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

    sys_status_str = "🟢 OK (100/100)"
    try:
        from system_health import check_system_health
        shealth = check_system_health()
        stat = shealth.get("status", "OK")
        score = shealth.get("score", 100)
        s_icon = "🟢" if stat == "OK" else ("🟡" if stat == "WARNING" else "🔴")
        sys_status_str = f"{s_icon} {stat} ({score}/100)"
    except Exception:
        pass

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
        f"🏥 <b>System-Gesundheit:</b> <b>{sys_status_str}</b>\n"
        f"⚡ <b>Hintergrund-Dienst:</b> Systemd 24/7 aktiv\n\n"
        f"🔑 <b>Google Gemini API-Key Pool:</b>\n"
        f"• Keys aktiv: <b>{act_cnt} von {tot_cnt} Keys</b> ({masked})\n"
        f"• Verbrauch: <b>{used} / {limit} Anfragen</b> ({pct:.1f}%)\n"
        f"• Frei: <b>{rem} Anfragen</b> | Reset: <code>{reset_cd}</code>\n\n"
        f"🏛️ <b>Autonomes KI-Portfolio:</b>\n"
        f"• Win-Rate: <b>{win_rate}%</b> | Offene Trades: <b>{port_active}</b>\n"
        f"• Gehebelter Gesamt-PnL: <b>{lev_pnl:+.1f}%</b>\n\n"
        f"👥 <b>Benutzer:</b> {len(auth_users)} autorisiert\n"
    )

    kb = {
        "inline_keyboard": [
            [
                {"text": "🏥 System-Gesundheit & Diagnose", "callback_data": "admin_health_check"}
            ],
            [
                {"text": "🔑 API-Quota Details", "callback_data": "admin_quota_details"},
                {"text": "🏛️ Modell-Portfolio", "callback_data": "admin_model_portfolio"}
            ],
            [
                {"text": "🧠 KI-Lernsystem & Scorecard", "callback_data": "admin_learnings_hub"},
                {"text": "👥 Benutzerverwaltung", "callback_data": "menu_users"}
            ],
            [
                {"text": "⚡ Live Master-Scan", "callback_data": "action_trigger_scan"},
                {"text": "🔙 Hauptmenü", "callback_data": "menu_main"}
            ]
        ]
    }
    return text, kb


def get_user_management_text_and_markup():
    """Zeigt die Benutzerverwaltung für Master-Admins an inklusive Lösch-Möglichkeit."""
    cfg = load_config()
    auth_users = cfg.get("authorized_users", {})
    admin_unames = [u.lower() for u in cfg.get("admin_usernames", [])]
    admin_cids = [str(cid) for cid in cfg.get("admin_chat_ids", [])]

    lines = [
        "👥 <b>Benutzerverwaltung (Master-Admin)</b>\n",
        "Hier siehst du alle aktuell autorisierten Personen.",
        "Klicke auf einen Trader, um Zugriffsrechte zu entziehen (Löschen):\n"
    ]

    buttons = []
    for uname, udata in auth_users.items():
        cid = str(udata.get("chat_id", ""))
        role = udata.get("role", "trader")
        name = udata.get("name") or uname or f"User_{cid}"
        is_admin = (uname.lower() in admin_unames) or (cid in admin_cids) or (role == "admin")

        if is_admin:
            lines.append(f"• 👑 <b>@{uname}</b> (Admin) – ID: <code>{cid}</code>")
        else:
            disp_name = f"@{uname}" if uname and uname != "None" and not uname.startswith("User_") else (name or f"User {cid}")
            lines.append(f"• 📈 <b>{disp_name}</b> ({role.capitalize()}) – ID: <code>{cid}</code>")
            btn_label = f"🗑️ {disp_name} löschen"
            buttons.append([{"text": btn_label, "callback_data": f"user_del_ask_{cid}"}])

    lines.append("\n<i>Hinweis: Gelöschte Nutzer müssen bei erneutem Kontakt eine neue Freischaltung anfragen.</i>")

    buttons.append([{"text": "🔙 Zurück zur Admin-Zentrale", "callback_data": "menu_admin_hub"}])
    buttons.append([{"text": "🏠 Hauptmenü", "callback_data": "menu_main"}])

    return "\n".join(lines), {"inline_keyboard": buttons}


def get_admin_quota_details_text_and_markup():
    """Detaillierte Aufschlüsselung aller API-Keys und des Pro-Abos (View Usage)."""
    try:
        from gemini_quota_tracker import get_quota_summary_for_dashboard
        quota = get_quota_summary_for_dashboard()
    except Exception:
        quota = {}

    keys_detail = quota.get("keys_detail", [])
    used = quota.get("requests_used_today", 0)
    limit = quota.get("daily_limit", 80)
    pct = quota.get("percent_used", 0.0)

    pro = quota.get("pro_subscription", {})
    five_h = pro.get("five_hour_window", {})
    five_h_rem = five_h.get("remaining_pct", pro.get("percent_remaining", 98.9))
    five_h_used = five_h.get("used_pct", 1.1)
    five_h_reset = five_h.get("reset_countdown", "in wenigen Stunden")

    req_today = pro.get("requests_used_today", 0)
    req_week = pro.get("requests_used_this_week", req_today)
    acc_info = pro.get("account_info", {})
    acc_name = acc_info.get("account_name", "Account 2 (Dediziert für Trading)")
    acc_email = acc_info.get("email", "pokeulm@gmail.com")

    # Fortschrittsbalken für Google 5h Rolling Limit (10 Blöcke)
    filled_blocks = int(round(five_h_rem / 10.0))
    bar = "█" * filled_blocks + "░" * (10 - filled_blocks)

    lines = [
        f"⚡ <b>Google Pro-Abo · View Usage (Gemini 3.8 Flash High)</b>",
        f"👤 <b>Account:</b> {acc_name}",
        f"📧 <b>E-Mail:</b> <code>{acc_email}</code> (Dediziert für Trading)",
        f"🧠 <b>Modell:</b> <code>gemini-3.8-flash-high</code> (Pro Thinking aktiv)\n",
        f"⏳ <b>Echtes Google 5-Stunden-Limit:</b>",
        f"• Restvolumen: <b>{five_h_rem}% frei</b> ({five_h_used}% verbraucht)",
        f"• Reset-Zeitfenster: <code>{five_h_reset}</code>",
        f"• <code>[{bar}]</code> {five_h_rem:.1f}% verfügbar\n",
        f"📈 <b>Nutzungs-Monitoring (50er-Limit aufgehoben):</b>",
        f"• Anfragen heute: <b>{req_today} Requests</b>",
        f"• Anfragen 7-Tage (Woche): <b>{req_week} Requests</b>",
        f"• Status: 🟢 <b>Unbegrenzter Monitoring-Modus aktiv</b>\n",
        f"🔑 <b>Google Gemini Multi-Key Quota Pool (Failover-Reserve)</b>",
        f"<b>Pool-Verbrauch:</b> {used} / {limit} Requests ({pct:.1f}%)\n",
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
            f"   Status: {status_sym} | {k_used}/{k_lim} ({k_pct:.0f}%)\n"
        )

    lines.append("🛡️ <i>Kaskade: 1. Google Pro-Abo (pokeulm@gmail.com · 3.8 Flash High) -> 2. Multi-Key Pool (3.8 Flash High) -> 3. Multi-Key Pool (3.5 Flash) -> 4. SMC Math-Core.</i>")

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
    rolling = metrics.get("rolling", {})
    r5 = rolling.get("last_5", {})
    r10 = rolling.get("last_10", {})

    wr_line = f"• <b>Win-Rate (All-Time):</b> {win_rate}%"
    if r10 or r5:
        wr10 = r10.get("win_rate_pct", 0)
        wr5 = r5.get("win_rate_pct", 0)
        wr_line = (
            f"• <b>Win-Rate:</b> {win_rate}% (All-Time)\n"
            f"   ↳ <b>Gleitend L10:</b> <b>{wr10}%</b> | <b>L5:</b> <b>{wr5}%</b> 🔥"
        )

    lines = [
        f"🏛️ <b>Autonomes KI-High-Conviction Modell-Portfolio</b>\n",
        wr_line,
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


def get_admin_learnings_text_and_markup():
    """Zeigt das KI-Trade-Lernsystem und die Closed-Loop Scorecard an."""
    trade_mem_file = BASE_DIR / "knowledge_base" / "trade_memory.json"
    if not trade_mem_file.exists():
        return "🧠 Noch kein Erfahrungsspeicher vorhanden.", {"inline_keyboard": [[{"text": "🔙 Admin-Zentrale", "callback_data": "menu_admin_hub"}]]}

    try:
        with open(trade_mem_file, "r", encoding="utf-8") as f:
            mem = json.load(f)
    except Exception as e:
        return f"Fehler beim Lesen des Lernspeichers: {e}", None

    learnings = mem.get("learnings", [])
    setup_perf = mem.get("setup_performance", {})
    cat_perf = mem.get("category_performance", {})

    lines = [
        "🧠 <b>KI-Trade-Lernsystem & Closed-Loop Scorecard</b>\n",
        f"• <b>Gespeicherte Lerneinheiten:</b> {len(learnings)}",
        f"• <b>Gemini 3.8 Flash Engine:</b> Account 2 (pokeulm@gmail.com)\n",
        "📊 <b>Setup-Performance & Mindest-Scores:</b>"
    ]

    if setup_perf:
        for s_name, sp in list(setup_perf.items())[:3]:
            short_name = s_name.replace("Hypothese ", "Hyp. ")
            status_icon = "🟢" if sp.get("status") == "PROVEN_EDGE" else ("🔴" if sp.get("status") == "UNDERPERFORMING" else "🟡")
            lines.append(
                f"{status_icon} <b>{short_name}</b>: {sp.get('wins')}/{sp.get('trades')} ({sp.get('win_rate')}%) | PnL: {sp.get('total_lev_pnl'):+.1f}%\n"
                f"   ↳ Min-Score: <code>{sp.get('min_score')}%</code> | Hebel: <code>{sp.get('leverage_adjustment', 0):+d}x</code>"
            )
        lines.append("")

    if cat_perf:
        lines.append("🌐 <b>Sektor-Governors (Dämpfer aktiv):</b>")
        for cat, cp in list(cat_perf.items())[:3]:
            p_icon = "🟢" if cp.get("total_lev_pnl", 0) >= 0 else "🔴"
            lines.append(f"{p_icon} <b>{cat}</b>: {cp.get('win_rate')}% Win-Rate | Cap: <code>{cp.get('leverage_cap')}x</code> | Min-Score: <code>{cp.get('min_score')}%</code>")
        lines.append("")

    lines.append("🔬 <b>Neueste KI-Post-Mortem Lerneinheiten:</b>")
    ai_learnings = [l for l in learnings if l.get("ai_post_mortem")][:2]
    if ai_learnings:
        for l in ai_learnings:
            ai = l.get("ai_post_mortem", {})
            res_icon = "✅" if l.get("result") == "WIN" else "❌"
            lines.append(
                f"{res_icon} <b>{l.get('symbol')}</b> ({l.get('pnl_leveraged'):+.1f}%):\n"
                f"• <i>Ursache:</i> {ai.get('driver')}\n"
                f"• <i>Regel:</i> <code>{ai.get('actionable_rule')}</code>\n"
            )
    else:
        for l in learnings[:2]:
            lines.append(f"• [{l.get('result')}] {l.get('symbol')}: {l.get('text')[:120]}...\n")

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
                [{"text": "📜 Meine Trade-Historie", "callback_data": "menu_my_history"}],
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

        sl = p.get("stop_loss")
        tp = p.get("take_profit")
        sl_str = f"{float(sl):,.2f} $".replace(",", "X").replace(".", ",").replace("X", ".") if sl is not None else "<i>-</i>"
        tp_str = f"{float(tp):,.2f} $".replace(",", "X").replace(".", ",").replace("X", ".") if tp is not None else "<i>-</i>"

        sltp_info = f"   • 🛑 <b>SL:</b> {sl_str} | 🎯 <b>TP:</b> {tp_str}"
        if sl is not None and tp is not None:
            risk = abs(entry - float(sl))
            reward = abs(float(tp) - entry)
            if risk > 0:
                sltp_info += f" <i>(CRV 1:{reward / risk:.2f})</i>"

        lines.append(
            f"<b>{idx}. {icon} {p.get('name', sym)}</b> (<code>{sym}</code>)\n"
            f"   • <b>Richtung:</b> {sig} | <b>Hebel:</b> {lev:g}x\n"
            f"   • <b>Einstieg:</b> {entry_fmt} $ | <b>Aktuell:</b> {curr_fmt} $\n"
            f"{sltp_info}\n"
            f"   • {pnl_icon} <b>PnL:</b> <b>{pnl_sign}{pnl_lev:.2f}%</b> (Basis: {pnl_sign}{pnl_base:.2f}%)\n"
        )
        if rec and rec.get("action"):
            lines.append(f"   • 💡 <b>Empfehlung:</b> [{rec.get('action')}] {rec.get('title')}\n")
        lines.append("")

        pos_id = p.get("id") or sym
        short_sym = sym.split(":")[-1]
        buttons.append([
            {"text": f"⚙️ {short_sym} anpassen", "callback_data": f"pos_manage_open_{pos_id}"},
            {"text": f"🛑 {short_sym} schließen", "callback_data": f"close_confirm_{pos_id}"}
        ])

    buttons.append([
        {"text": "📜 Meine Trade-Historie", "callback_data": "menu_my_history"},
        {"text": "➕ Neuer Trade", "callback_data": "menu_new_trade"}
    ])
    buttons.append([
        {"text": "🔄 Aktualisieren", "callback_data": "menu_my_trades"},
        {"text": "🔙 Zurück zum Hauptmenü", "callback_data": "menu_main"}
    ])

    return "\n".join(lines), {"inline_keyboard": buttons}


def get_manage_position_text_and_markup(pos_id, user_id=None):
    """Generiert die detaillierte Bearbeitungs-Zentrale für eine einzelne Nutzer-Position."""
    from manage_positions import load_positions
    positions = load_positions()
    pos = None
    for p in positions:
        if p.get("id") == pos_id or p.get("symbol") == pos_id:
            pos = p
            break

    if not pos:
        return "⚠️ Position nicht gefunden oder bereits geschlossen.", {"inline_keyboard": [[{"text": "🔙 Meine Trades", "callback_data": "menu_my_trades"}]]}

    sym = pos.get("symbol", "Unbekannt")
    short_sym = sym.split(":")[-1]
    sig = pos.get("direction", "LONG").upper()
    entry = float(pos.get("entry_price", 0.0))
    lev = float(pos.get("leverage", 1.0))
    curr = float(pos.get("current_price", entry))
    note = pos.get("note", "")

    pnl_base = ((curr - entry) / entry * 100) if sig == "LONG" else ((entry - curr) / entry * 100) if entry > 0 else 0.0
    pnl_lev = pnl_base * lev
    pnl_icon = "📈" if pnl_lev >= 0 else "📉"
    pnl_sign = "+" if pnl_lev >= 0 else ""

    sl = pos.get("stop_loss")
    tp = pos.get("take_profit")
    sl_str = f"{float(sl):,.2f} $".replace(",", "X").replace(".", ",").replace("X", ".") if sl is not None else "<i>Kein SL</i>"
    tp_str = f"{float(tp):,.2f} $".replace(",", "X").replace(".", ",").replace("X", ".") if tp is not None else "<i>Kein TP</i>"

    icon = "🟢" if sig == "LONG" else "🔴"
    entry_fmt = f"{entry:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    curr_fmt = f"{curr:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    text = (
        f"⚙️ <b>Trade bearbeiten: {pos.get('name', short_sym)}</b> (<code>{sym}</code>)\n\n"
        f"• <b>Richtung:</b> {icon} <b>{sig}</b>\n"
        f"• <b>Hebel:</b> <b>{lev:g}x</b>\n"
        f"• <b>Einstieg:</b> <code>{entry_fmt} $</code> (Live: <code>{curr_fmt} $</code>)\n"
        f"• 🛑 <b>Stop-Loss:</b> {sl_str}\n"
        f"• 🎯 <b>Take-Profit:</b> {tp_str}\n"
        f"• {pnl_icon} <b>Aktueller PnL:</b> <b>{pnl_sign}{pnl_lev:.2f}%</b> ({pnl_sign}{pnl_base:.2f}% Basis)\n"
    )
    if note:
        text += f"• 📝 <i>Notiz: {note}</i>\n"

    text += "\n<i>Welchen Parameter möchtest du verändern?</i>"

    kb = {
        "inline_keyboard": [
            [
                {"text": "⚡ Hebel anpassen", "callback_data": f"pos_lev_menu_{pos_id}"},
                {"text": "📍 Einstieg ändern", "callback_data": f"pos_entry_menu_{pos_id}"}
            ],
            [
                {"text": "🎯 SL & TP anpassen", "callback_data": f"edit_sltp_open_{pos_id}"},
                {"text": "🔄 Richtung wechseln", "callback_data": f"pos_toggle_dir_{pos_id}"}
            ],
            [
                {"text": "🛑 Position schließen", "callback_data": f"close_confirm_{pos_id}"}
            ],
            [
                {"text": "🔙 Zurück zu Meinen Trades", "callback_data": "menu_my_trades"}
            ]
        ]
    }
    return text, kb


def get_user_history_text_and_markup(user_id=None, username=None, page=1):
    """Generiert Text & Buttons für die Historie der geschlossenen Nutzer-Trades."""
    try:
        from manage_positions import load_history
        history = load_history()
    except Exception:
        history = []

    user_id_str = str(user_id) if user_id else ""
    user_name_str = (username or "").lstrip("@").lower()

    # Filtern nach Nutzer (oder alle falls leer / Altdaten)
    matched = []
    for h in history:
        h_uid = str(h.get("user_id", ""))
        h_uname = (h.get("user_name", "")).lstrip("@").lower()
        if not h_uid and not h_uname:
            matched.append(h)
        elif h_uid == user_id_str or (user_name_str and h_uname == user_name_str):
            matched.append(h)

    if not matched:
        kb = {
            "inline_keyboard": [
                [{"text": "📊 Zu den aktiven Trades", "callback_data": "menu_my_trades"}],
                [{"text": "🔙 Hauptmenü", "callback_data": "menu_main"}]
            ]
        }
        return (
            "📜 <b>Deine Trade-Historie</b>\n\n"
            "Noch keine geschlossenen Trades vorhanden.\n"
            "Sobald ein Trade manuell oder durch Stop-Loss / Take-Profit beendet wird, erscheint er hier mit vollständiger Auswertung.",
            kb
        )

    # Statistiken berechnen
    total_count = len(matched)
    wins = [t for t in matched if (float(t.get("realized_pnl_pct", 0.0)) > 0)]
    losses = [t for t in matched if (float(t.get("realized_pnl_pct", 0.0)) < 0)]
    win_rate = (len(wins) / total_count * 100.0) if total_count > 0 else 0.0
    tot_lev_pnl = sum(float(t.get("realized_pnl_leveraged_pct", 0.0)) for t in matched)
    pnl_sign = "+" if tot_lev_pnl >= 0 else ""

    per_page = 4
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_items = matched[start_idx:end_idx]

    lines = [
        f"📜 <b>Deine Trade-Historie ({total_count} Trades)</b>\n",
        f"• <b>Win-Rate:</b> <b>{win_rate:.1f}%</b> ({len(wins)}W / {len(losses)}L)",
        f"• <b>Gesamt-Performance:</b> <b>{pnl_sign}{tot_lev_pnl:.2f}%</b> (gehebelt)\n",
        "━━━━━━━━━━━━━━━━━━━━\n"
    ]

    for idx, t in enumerate(page_items, start=start_idx + 1):
        sym = t.get("symbol", "Unbekannt")
        sig = t.get("direction", "LONG")
        entry = float(t.get("entry_price", 0.0))
        exit_p = float(t.get("exit_price", entry))
        lev = float(t.get("leverage", 1.0))
        pnl_base = float(t.get("realized_pnl_pct", 0.0))
        pnl_lev = float(t.get("realized_pnl_leveraged_pct", 0.0))
        reason_disp = t.get("exit_reason_display", t.get("exit_reason", "Geschlossen"))
        dur = t.get("holding_duration_str", "")

        icon = "🟢" if sig == "LONG" else "🔴"
        pnl_icon = "📈" if pnl_lev >= 0 else "📉"
        pnl_s = "+" if pnl_lev >= 0 else ""

        entry_fmt = f"{entry:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        exit_fmt = f"{exit_p:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        dur_info = f" | ⏱️ {dur}" if dur and dur != "-" else ""
        closed_date = (t.get("closed_at") or "")[:10]
        if closed_date:
            try:
                parts = closed_date.split("-")
                closed_date_fmt = f"{parts[2]}.{parts[1]}."
            except Exception:
                closed_date_fmt = closed_date
        else:
            closed_date_fmt = ""

        lines.append(
            f"<b>{idx}. {icon} {t.get('name', sym)}</b> (<code>{sym}</code>)\n"
            f"   • <b>Typ:</b> {sig} ({lev:g}x Hebel)\n"
            f"   • <b>Kurs:</b> {entry_fmt} $ ➔ {exit_fmt} $\n"
            f"   • {pnl_icon} <b>Realisierter PnL:</b> <b>{pnl_s}{pnl_lev:.2f}%</b> ({pnl_s}{pnl_base:.2f}% Basis)\n"
            f"   • 💡 <b>Grund:</b> {reason_disp}\n"
            f"   • 📅 <b>Ende:</b> {closed_date_fmt}{dur_info}\n"
        )

    buttons = []
    # Pagination
    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append({"text": "⬅️ Vorherige", "callback_data": f"my_history_page_{page - 1}"})
        nav_row.append({"text": f"Seite {page}/{total_pages}", "callback_data": "noop"})
        if page < total_pages:
            nav_row.append({"text": "Nächste ➡️", "callback_data": f"my_history_page_{page + 1}"})
        buttons.append(nav_row)

    buttons.append([
        {"text": "📊 Zu den aktiven Trades", "callback_data": "menu_my_trades"},
        {"text": "🔄 Aktualisieren", "callback_data": f"my_history_page_{page}"}
    ])
    buttons.append([
        {"text": "🌐 Im Web-Dashboard öffnen", "url": "https://bbbdc.github.io/trading-dashboard/"},
        {"text": "🔙 Hauptmenü", "callback_data": "menu_main"}
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

        if text.startswith("/dashboard") or text.startswith("/login"):
            USER_SESSIONS.pop(chat_id, None)
            login_param = f"?user={username}" if username else f"?id={user_id}"
            dash_text = (
                f"🌐 <b>Direktzugang zum Web-Dashboard</b>\n\n"
                f"Klicke auf den Button unten, um dich automatisch als <b>@{username or first_name}</b> im Dashboard anzumelden:"
            )
            dash_kb = {
                "inline_keyboard": [
                    [{"text": "📊 Web-Dashboard öffnen (Auto-Login)", "url": f"https://bbbdc.github.io/trading-dashboard/{login_param}"}],
                    [{"text": "🔙 Hauptmenü", "callback_data": "menu_main"}]
                ]
            }
            api.send_message(chat_id, dash_text, reply_markup=dash_kb)
            return

        if text.startswith("/learnings") or text.startswith("/scorecard"):
            if role != "admin":
                api.send_message(chat_id, "⚠️ Diese Funktion ist dem Master-Admin vorbehalten.", reply_markup=get_main_menu_keyboard(role))
                return
            t, kb = get_admin_learnings_text_and_markup()
            api.send_message(chat_id, t, reply_markup=kb)
            return

        if text.startswith("/health") or text.startswith("/status"):
            if role != "admin":
                api.send_message(chat_id, "⚠️ Diese Funktion ist dem Master-Admin vorbehalten.", reply_markup=get_main_menu_keyboard(role))
                return
            from system_health import get_health_telegram_report
            htext, hkb = get_health_telegram_report()
            api.send_message(chat_id, htext, reply_markup=hkb)
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
    uname_str = username if username else ""
    disp_btn_user = f"@{username}" if username else f"User {user_id}"
    admin_kb = {
        "inline_keyboard": [
            [
                {"text": f"✅ Freischalten: {disp_btn_user}", "callback_data": f"approve_user_{user_id}_{uname_str}"},
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

    if data == "menu_my_history" or data.startswith("my_history_page_"):
        page = 1
        if data.startswith("my_history_page_"):
            try:
                page = int(data[len("my_history_page_"):])
            except Exception:
                page = 1
        text, kb = get_user_history_text_and_markup(user_id, username, page=page)
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    if data == "noop":
        api.answer_callback_query(callback_query_id)
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

    if data == "admin_health_check":
        if role != "admin":
            api.edit_message_text(chat_id, message_id, "⚠️ Diese Funktion ist dem Master-Admin vorbehalten.", reply_markup=get_main_menu_keyboard(role))
            return
        from system_health import get_health_telegram_report
        htext, hkb = get_health_telegram_report()
        api.edit_message_text(chat_id, message_id, htext, reply_markup=hkb)
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

    if data == "admin_learnings_hub":
        if role != "admin":
            api.edit_message_text(chat_id, message_id, "⚠️ Diese Funktion ist dem Master-Admin vorbehalten.", reply_markup=get_main_menu_keyboard(role))
            return
        text, kb = get_admin_learnings_text_and_markup()
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    if data == "menu_market_scan":
        summary = get_market_overview(role=role)
        login_param = f"?user={username}" if username else f"?id={user_id}"
        if role == "admin":
            kb = {
                "inline_keyboard": [
                    [{"text": "⚡ Jetzt Live-Scan starten", "callback_data": "action_trigger_scan"}],
                    [{"text": "🎯 Top-Setups ansehen", "callback_data": "menu_top_setups"}],
                    [{"text": "🌐 Web-Dashboard öffnen", "url": f"https://bbbdc.github.io/trading-dashboard/{login_param}"}],
                    [{"text": "🔙 Hauptmenü", "callback_data": "menu_main"}]
                ]
            }
        else:
            kb = {
                "inline_keyboard": [
                    [{"text": "🎯 Top-Setups ansehen", "callback_data": "menu_top_setups"}],
                    [{"text": "🌐 Web-Dashboard öffnen", "url": f"https://bbbdc.github.io/trading-dashboard/{login_param}"}],
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
        login_param = f"?user={username}" if username else f"?id={user_id}"
        text = (
            "🌐 <b>Web-Dashboard & Signal-Historie</b>\n\n"
            "Hier kannst du das interaktive Dashboard mit allen Charts und Auswertungen aufrufen:"
        )
        kb = {
            "inline_keyboard": [
                [{"text": "📊 Live Web-Dashboard (Auto-Login)", "url": f"https://bbbdc.github.io/trading-dashboard/{login_param}"}],
                [{"text": "📜 Signal-Historie & Treffer", "url": "https://bbbdc.github.io/trading-dashboard/history.html"}],
                [{"text": "🔙 Hauptmenü", "callback_data": "menu_main"}]
            ]
        }
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    if data == "menu_users":
        if role != "admin":
            api.edit_message_text(chat_id, message_id, "⚠️ Diese Funktion ist dem Master-Admin vorbehalten.", reply_markup=get_main_menu_keyboard(role))
            return
        text, kb = get_user_management_text_and_markup()
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
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

    # 2b. 1-Klick Signal-Übernahme (Direktes Vorbefüllen von Symbol, Richtung, Entry, SL, TP)
    if data.startswith("wiz_adopt:"):
        symbol = data[len("wiz_adopt:"):]
        asset = None
        if DB_FILE.exists():
            try:
                with open(DB_FILE, "r", encoding="utf-8") as f:
                    for a in json.load(f).get("assets", []):
                        if a.get("symbol") == symbol:
                            asset = a
                            break
            except Exception:
                pass

        if not asset:
            api.send_message(chat_id, f"⚠️ Setup für {symbol} nicht mehr aktuell oder nicht gefunden.")
            return

        direction = asset.get("signal", "LONG")
        entry = float(asset.get("price", 0.0))
        sl = float(asset.get("stop_loss", entry * 0.96 if direction == "LONG" else entry * 1.04))
        tp1 = float(asset.get("take_profit_1", 0.0))
        if tp1 <= 0:
            tp1 = float(asset.get("take_profit_2", entry * 1.08 if direction == "LONG" else entry * 0.92))

        session = USER_SESSIONS.setdefault(chat_id, {"wizard": "new_trade", "data": {}})
        session["data"] = {
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit": tp1,
            "user_id": str(user_id),
            "user_name": username or f"User_{user_id}",
            "note": f"Übernommen aus Signal ({asset.get('score', 88)}% Score)"
        }
        session["step"] = "SELECT_LEVERAGE"

        curr_sym = "€" if "TRADEGATE" in symbol or "XETR" in symbol else "$"
        msg = (
            f"🎯 <b>Signal-Setup übernommen: {asset.get('name', symbol)}</b>\n\n"
            f"• <b>Symbol:</b> <code>{symbol}</code>\n"
            f"• <b>Richtung:</b> {'🟢 LONG' if direction == 'LONG' else '🔴 SHORT'}\n"
            f"• <b>Einstiegskurs:</b> <code>{entry:,.2f} {curr_sym}</code>\n"
            f"• 🛑 <b>Stop-Loss:</b> <code>{sl:,.2f} {curr_sym}</code>\n"
            f"• 🎯 <b>Take-Profit:</b> <code>{tp1:,.2f} {curr_sym}</code>\n\n"
            f"Wähle deinen <b>Hebel</b> für diese Position:"
        )
        api.send_message(chat_id, msg, reply_markup=get_leverage_keyboard())
        return

    # 3. Symbol gewählt (Kategorie, Vorschlags-Button oder direkte Auswahl)
    if data.startswith("sym_") or data.startswith("wiz_sel_sym:") or data.startswith("wiz_sel_sym_raw:"):
        if data.startswith("sym_"):
            symbol = data[4:]
        elif data.startswith("wiz_sel_sym:"):
            symbol = data[len("wiz_sel_sym:"):]
        else:
            raw_s = data[len("wiz_sel_sym_raw:"):]
            # Falls kein Doppelpunkt vorhanden, passende Standard-Präfixe prüfen
            if ":" not in raw_s:
                if raw_s in ("BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "ADA", "AVAX"):
                    symbol = f"BINANCE:{raw_s}USDT"
                elif raw_s in ("NVDA", "AAPL", "TSLA", "MSFT", "AMZN", "META", "GOOGL"):
                    symbol = f"NASDAQ:{raw_s}"
                elif raw_s in ("SAP", "SIE", "ALV", "MBG", "BMW"):
                    symbol = f"XETR:{raw_s}"
                elif raw_s in ("GOLD", "SILVER"):
                    symbol = f"TVC:{raw_s}"
                else:
                    symbol = raw_s
            else:
                symbol = raw_s

        session = USER_SESSIONS.setdefault(chat_id, {"wizard": "new_trade", "data": {}})
        session["data"]["symbol"] = symbol
        session["step"] = "SELECT_DIRECTION"

        live_price = find_asset_price(symbol)
        session["data"]["live_price"] = live_price
        curr_sym = "€" if "TRADEGATE" in symbol or "XETR" in symbol else "$"
        price_info = f" (Live-Referenzpreis: ~{fmt_price(live_price)} {curr_sym})" if live_price else ""

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
        session["step"] = "WAITING_SL"
        direction = session["data"].get("direction", "LONG")
        entry_p = float(session["data"].get("entry_price", 0.0))
        api.edit_message_text(
            chat_id,
            message_id,
            f"Hebel: <b>{lev_val}x</b>\n\n"
            f"Schritt 5: 🛑 <b>Stop-Loss (SL) festlegen</b>\n\n"
            f"Gib deinen gewünschten Stop-Loss Kurs als Zahl in den Chat ein, "
            f"wähle einen Schnell-Vorschlag oder überspringe diesen Schritt:",
            reply_markup=get_stop_loss_keyboard(direction, entry_p)
        )
        return

    # 6a. Stop-Loss gewählt (Button)
    if data.startswith("sl_quick_"):
        sl_val = float(data[9:])
        session = USER_SESSIONS.get(chat_id)
        if not session:
            return
        session["data"]["stop_loss"] = sl_val
        session["step"] = "WAITING_TP"
        direction = session["data"].get("direction", "LONG")
        entry_p = float(session["data"].get("entry_price", 0.0))
        api.edit_message_text(
            chat_id,
            message_id,
            f"Stop-Loss: <b>{fmt_price(sl_val)} $</b>\n\n"
            f"Schritt 6: 🎯 <b>Take-Profit (TP) festlegen</b>\n\n"
            f"Gib dein Kursziel als Zahl in den Chat ein, wähle einen Schnell-Vorschlag oder überspringe:",
            reply_markup=get_take_profit_keyboard(direction, entry_p)
        )
        return

    if data == "sl_skip":
        session = USER_SESSIONS.get(chat_id)
        if not session:
            return
        session["data"]["stop_loss"] = None
        session["step"] = "WAITING_TP"
        direction = session["data"].get("direction", "LONG")
        entry_p = float(session["data"].get("entry_price", 0.0))
        api.edit_message_text(
            chat_id,
            message_id,
            f"Stop-Loss: <i>Kein Stop-Loss gesetzt</i>\n\n"
            f"Schritt 6: 🎯 <b>Take-Profit (TP) festlegen</b>\n\n"
            f"Gib dein Kursziel als Zahl in den Chat ein, wähle einen Schnell-Vorschlag oder überspringe:",
            reply_markup=get_take_profit_keyboard(direction, entry_p)
        )
        return

    # 6b. Take-Profit gewählt (Button)
    if data.startswith("tp_quick_"):
        tp_val = float(data[9:])
        session = USER_SESSIONS.get(chat_id)
        if not session:
            return
        session["data"]["take_profit"] = tp_val
        session["step"] = "WAITING_NOTE"
        api.edit_message_text(
            chat_id,
            message_id,
            f"Take-Profit: <b>{fmt_price(tp_val)} $</b>\n\n"
            f"Schritt 7: Optionale Notiz hinterlegen?\n"
            f"<i>(Einfach als Nachricht tippen oder überspringen)</i>",
            reply_markup=get_note_keyboard()
        )
        return

    if data == "tp_skip":
        session = USER_SESSIONS.get(chat_id)
        if not session:
            return
        session["data"]["take_profit"] = None
        session["step"] = "WAITING_NOTE"
        api.edit_message_text(
            chat_id,
            message_id,
            f"Take-Profit: <i>Kein Take-Profit gesetzt</i>\n\n"
            f"Schritt 7: Optionale Notiz hinterlegen?\n"
            f"<i>(Einfach als Nachricht tippen oder überspringen)</i>",
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
            sl_to_save = t_data.get("stop_loss")
            tp_to_save = t_data.get("take_profit")
            add_position(
                symbol=t_data["symbol"],
                direction=t_data["direction"],
                entry_price=t_data["entry_price"],
                leverage=t_data.get("leverage", 1.0),
                stop_loss=sl_to_save,
                take_profit=tp_to_save,
                note=t_data.get("note", ""),
                user_id=str(user_id),
                user_name=username or f"User_{user_id}",
                sync_db=True,
                git_push=True
            )
            sl_info_txt = f"{fmt_price(sl_to_save)} $" if sl_to_save is not None else "Keiner"
            tp_info_txt = f"{fmt_price(tp_to_save)} $" if tp_to_save is not None else "Keines"
            success_text = (
                f"✅ <b>Position erfolgreich gespeichert!</b>\n\n"
                f"• <b>Symbol:</b> {t_data['symbol']}\n"
                f"• <b>Richtung:</b> {t_data['direction']}\n"
                f"• <b>Einstieg:</b> {t_data['entry_price']:,.2f} $\n"
                f"• <b>Hebel:</b> {t_data.get('leverage', 1.0)}x\n"
                f"• 🛑 <b>Stop-Loss:</b> {sl_info_txt}\n"
                f"• 🎯 <b>Take-Profit:</b> {tp_info_txt}\n"
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

    # 7b. Stop-Loss & Take-Profit: Änderungen final speichern
    if data == "edit_sltp_save":
        session = USER_SESSIONS.get(chat_id)
        if not session or session.get("wizard") != "edit_sltp":
            return
        target_pos_id = session.get("pos_id")
        sym = session.get("symbol")
        new_sl = session["data"].get("stop_loss")
        new_tp = session["data"].get("take_profit")
        clear_sl = (new_sl is None)
        clear_tp = (new_tp is None)
        USER_SESSIONS.pop(chat_id, None)

        api.edit_message_text(chat_id, message_id, f"⏳ Speichere Änderungen für <b>{sym}</b> und aktualisiere Dashboard...")

        try:
            from manage_positions import update_position
            update_position(
                symbol_or_id=target_pos_id,
                user_id=str(user_id),
                stop_loss=new_sl,
                take_profit=new_tp,
                clear_sl=clear_sl,
                clear_tp=clear_tp,
                sync_db=True,
                git_push=True
            )
            sl_fmt = f"{fmt_price(new_sl)} $" if new_sl is not None else "Kein SL"
            tp_fmt = f"{fmt_price(new_tp)} $" if new_tp is not None else "Kein TP"
            success_txt = (
                f"✅ <b>Position erfolgreich aktualisiert!</b>\n\n"
                f"• <b>Symbol:</b> {sym}\n"
                f"• 🛑 <b>Stop-Loss:</b> {sl_fmt}\n"
                f"• 🎯 <b>Take-Profit:</b> {tp_fmt}\n\n"
                f"🍓 Die Parameter wurden synchronisiert und sind ab sofort im Bot und auf dem Web-Dashboard aktiv."
            )
            kb = {
                "inline_keyboard": [
                    [{"text": "📊 Meine Trades ansehen", "callback_data": "menu_my_trades"}],
                    [{"text": "🌐 Im Web-Dashboard öffnen", "url": "https://bbbdc.github.io/trading-dashboard/"}],
                    [{"text": "🔙 Hauptmenü", "callback_data": "menu_main"}]
                ]
            }
            api.edit_message_text(chat_id, message_id, success_txt, reply_markup=kb)
        except Exception as e:
            api.edit_message_text(chat_id, message_id, f"❌ Fehler beim Aktualisieren: {e}", reply_markup=get_main_menu_keyboard(role))
        return

    # 7b1. Positionen anpassen Hub (Hebel, Entry, Richtung, SL/TP)
    if data.startswith("pos_manage_open_"):
        USER_SESSIONS.pop(chat_id, None)
        pos_id = data[len("pos_manage_open_"):]
        text, kb = get_manage_position_text_and_markup(pos_id, user_id)
        api.edit_message_text(chat_id, message_id, text, reply_markup=kb)
        return

    # 7b2. Hebel-Auswahl Menü
    if data.startswith("pos_lev_menu_"):
        pos_id = data[len("pos_lev_menu_"):]
        from manage_positions import load_positions
        positions = load_positions()
        pos = next((p for p in positions if p.get("id") == pos_id or p.get("symbol") == pos_id), None)
        sym = pos.get("symbol", "") if pos else pos_id
        curr_lev = pos.get("leverage", 1.0) if pos else 1.0

        session = USER_SESSIONS.setdefault(chat_id, {"wizard": "edit_pos", "data": {}})
        session["step"] = "WAITING_EDIT_LEVERAGE"
        session["pos_id"] = pos.get("id") or pos_id
        session["symbol"] = sym
        session["curr_lev"] = curr_lev

        kb = {
            "inline_keyboard": [
                [
                    {"text": f"{'✅ ' if curr_lev == 1 else ''}1x (Basis)", "callback_data": f"pos_set_lev_{pos_id}_1"},
                    {"text": f"{'✅ ' if curr_lev == 2 else ''}2x", "callback_data": f"pos_set_lev_{pos_id}_2"},
                    {"text": f"{'✅ ' if curr_lev == 3 else ''}3x", "callback_data": f"pos_set_lev_{pos_id}_3"}
                ],
                [
                    {"text": f"{'✅ ' if curr_lev == 5 else ''}5x", "callback_data": f"pos_set_lev_{pos_id}_5"},
                    {"text": f"{'✅ ' if curr_lev == 10 else ''}10x", "callback_data": f"pos_set_lev_{pos_id}_10"},
                    {"text": f"{'✅ ' if curr_lev == 20 else ''}20x", "callback_data": f"pos_set_lev_{pos_id}_20"}
                ],
                [
                    {"text": "🔙 Abbrechen", "callback_data": f"pos_manage_open_{pos_id}"}
                ]
            ]
        }
        msg = (
            f"⚡ <b>Hebel für {sym} anpassen:</b>\n\n"
            f"• <b>Aktueller Hebel:</b> <b>{curr_lev:g}x</b>\n\n"
            f"Wähle einen Hebel per Button oder tippe deine Wunschzahl (z. B. <code>7</code>, <code>12.5</code> oder <code>50x</code>) direkt in den Chat:"
        )
        api.edit_message_text(chat_id, message_id, msg, reply_markup=kb)
        return

    # 7b3. Hebel direkt setzen
    if data.startswith("pos_set_lev_"):
        USER_SESSIONS.pop(chat_id, None)
        parts = data[len("pos_set_lev_"):].rsplit("_", 1)
        if len(parts) == 2:
            pos_id, lev_str = parts
            try:
                new_lev = float(lev_str)
                from manage_positions import update_position
                update_position(symbol_or_id=pos_id, user_id=str(user_id), leverage=new_lev, sync_db=True, git_push=True)
                text, kb = get_manage_position_text_and_markup(pos_id, user_id)
                api.edit_message_text(chat_id, message_id, f"✅ <b>Hebel erfolgreich auf {new_lev:g}x geändert!</b>\n\n" + text, reply_markup=kb)
            except Exception as e:
                api.edit_message_text(chat_id, message_id, f"❌ Fehler beim Ändern des Hebels: {e}", reply_markup={"inline_keyboard": [[{"text": "🔙 Zurück", "callback_data": f"pos_manage_open_{pos_id}"}]]})
        return

    # 7b4. Einstiegskurs anpassen Menü
    if data.startswith("pos_entry_menu_"):
        pos_id = data[len("pos_entry_menu_"):]
        from manage_positions import load_positions
        positions = load_positions()
        pos = next((p for p in positions if p.get("id") == pos_id or p.get("symbol") == pos_id), None)
        if not pos:
            api.send_message(chat_id, "⚠️ Position nicht gefunden.")
            return

        sym = pos.get("symbol", "")
        entry = float(pos.get("entry_price", 0.0))
        live_p = float(pos.get("current_price", 0.0))
        if live_p <= 0:
            live_p = find_asset_price(sym) or entry

        session = USER_SESSIONS.setdefault(chat_id, {"wizard": "edit_pos", "data": {}})
        session["step"] = "WAITING_EDIT_ENTRY"
        session["pos_id"] = pos.get("id") or pos_id
        session["symbol"] = sym
        session["live_price"] = live_p

        buttons = []
        if live_p > 0:
            buttons.append([{"text": f"⚡ Live-Kurs ({live_p:,.2f} $) übernehmen", "callback_data": f"pos_set_entry_live_{pos_id}"}])
        buttons.append([{"text": "🔙 Abbrechen", "callback_data": f"pos_manage_open_{pos_id}"}])

        msg = (
            f"📍 <b>Einstiegskurs anpassen für {sym}</b>\n\n"
            f"• <b>Bisheriger Einstieg:</b> {entry:,.2f} $\n"
            f"• <b>Aktueller Marktpreis:</b> {live_p:,.2f} $\n\n"
            f"Tippe den neuen Einstiegskurs einfach in den Chat oder übernimm den Live-Kurs mit 1 Klick:"
        )
        api.edit_message_text(chat_id, message_id, msg, reply_markup={"inline_keyboard": buttons})
        return

    # 7b5. Einstiegskurs auf Live-Kurs setzen
    if data.startswith("pos_set_entry_live_"):
        pos_id = data[len("pos_set_entry_live_"):]
        session = USER_SESSIONS.pop(chat_id, None) or {}
        live_p = session.get("live_price")
        if not live_p:
            from manage_positions import load_positions
            positions = load_positions()
            pos = next((p for p in positions if p.get("id") == pos_id or p.get("symbol") == pos_id), None)
            if pos:
                live_p = float(pos.get("current_price", 0.0)) or find_asset_price(pos.get("symbol"))
        if live_p and live_p > 0:
            from manage_positions import update_position
            update_position(symbol_or_id=pos_id, user_id=str(user_id), entry_price=float(live_p), sync_db=True, git_push=True)
            text, kb = get_manage_position_text_and_markup(pos_id, user_id)
            api.edit_message_text(chat_id, message_id, f"✅ <b>Einstiegskurs erfolgreich auf Live-Kurs ({live_p:,.2f} $) geändert!</b>\n\n" + text, reply_markup=kb)
        else:
            api.send_message(chat_id, "⚠️ Live-Kurs konnte nicht ermittelt werden.")
        return

    # 7b6. Richtung umschalten (LONG ↔ SHORT)
    if data.startswith("pos_toggle_dir_"):
        pos_id = data[len("pos_toggle_dir_"):]
        from manage_positions import load_positions, update_position
        positions = load_positions()
        pos = next((p for p in positions if p.get("id") == pos_id or p.get("symbol") == pos_id), None)
        if pos:
            curr_dir = pos.get("direction", "LONG").upper()
            new_dir = "SHORT" if curr_dir == "LONG" else "LONG"
            update_position(symbol_or_id=pos_id, user_id=str(user_id), direction=new_dir, sync_db=True, git_push=True)
            text, kb = get_manage_position_text_and_markup(pos_id, user_id)
            api.edit_message_text(chat_id, message_id, f"✅ <b>Richtung erfolgreich auf {new_dir} geändert!</b>\n\n" + text, reply_markup=kb)
        return

    # 7c. Stop-Loss & Take-Profit bei bestehenden Positionen anpassen
    if data.startswith("edit_sltp_open_") or (data.startswith("edit_sltp_") and not data.startswith("edit_sl_") and not data.startswith("edit_tp_")):
        if data.startswith("edit_sltp_open_"):
            pos_id = data[len("edit_sltp_open_"):]
        else:
            pos_id = data[len("edit_sltp_"):]

        from manage_positions import load_positions
        positions = load_positions()
        target_pos = None
        for p in positions:
            if p.get("id") == pos_id or p.get("symbol") == pos_id:
                target_pos = p
                break
        if not target_pos:
            api.send_message(chat_id, "⚠️ Position nicht gefunden.")
            return

        session = USER_SESSIONS.setdefault(chat_id, {"wizard": "edit_sltp", "data": {}})
        session["step"] = "WAITING_EDIT_SL"
        session["pos_id"] = target_pos.get("id") or pos_id
        session["symbol"] = target_pos.get("symbol")
        session["direction"] = target_pos.get("direction", "LONG")
        session["entry_price"] = float(target_pos.get("entry_price", 0.0))
        session["orig_sl"] = target_pos.get("stop_loss")
        session["orig_tp"] = target_pos.get("take_profit")
        session["data"]["stop_loss"] = target_pos.get("stop_loss")
        session["data"]["take_profit"] = target_pos.get("take_profit")

        sym = target_pos.get("symbol")
        entry = float(target_pos.get("entry_price", 0.0))
        sl = target_pos.get("stop_loss")
        tp = target_pos.get("take_profit")
        sl_str = f"{fmt_price(sl)} $" if sl is not None else "Nicht gesetzt"
        tp_str = f"{fmt_price(tp)} $" if tp is not None else "Nicht gesetzt"

        msg = (
            f"🎯 <b>SL & TP anpassen für {sym}</b> ({target_pos.get('direction')})\n\n"
            f"• <b>Einstieg:</b> {entry:,.2f} $\n"
            f"• <b>Aktueller SL:</b> {sl_str}\n"
            f"• <b>Aktueller TP:</b> {tp_str}\n\n"
            f"<b>Schritt 1 von 2: Neuer Stop-Loss (SL)</b>\n"
            f"Tippe den neuen Kurs in den Chat oder nutze die Buttons:"
        )
        api.edit_message_text(
            chat_id,
            message_id,
            msg,
            reply_markup=get_edit_sl_keyboard(target_pos.get("direction"), entry, sl)
        )
        return

    if data == "edit_sl_keep":
        session = USER_SESSIONS.get(chat_id)
        if not session or session.get("wizard") != "edit_sltp":
            return
        session["step"] = "WAITING_EDIT_TP"
        entry = float(session.get("entry_price", 0.0))
        direction = session.get("direction", "LONG")
        current_tp = session.get("orig_tp")
        sl_val = session["data"].get("stop_loss")
        sl_str = f"{fmt_price(sl_val)} $" if sl_val is not None else "<i>Kein SL</i>"
        api.edit_message_text(
            chat_id,
            message_id,
            f"Stop-Loss: <b>{sl_str}</b>\n\n"
            f"<b>Schritt 2 von 2: Neuer Take-Profit (TP)</b>\n"
            f"Tippe das neue Kursziel in den Chat oder wähle eine Option:",
            reply_markup=get_edit_tp_keyboard(direction, entry, current_tp)
        )
        return

    if data == "edit_sl_clear":
        session = USER_SESSIONS.get(chat_id)
        if not session or session.get("wizard") != "edit_sltp":
            return
        session["data"]["stop_loss"] = None
        session["step"] = "WAITING_EDIT_TP"
        entry = float(session.get("entry_price", 0.0))
        direction = session.get("direction", "LONG")
        current_tp = session.get("orig_tp")
        api.edit_message_text(
            chat_id,
            message_id,
            f"Stop-Loss: <i>Gelöscht / entfernt</i>\n\n"
            f"<b>Schritt 2 von 2: Neuer Take-Profit (TP)</b>\n"
            f"Tippe das neue Kursziel in den Chat oder wähle eine Option:",
            reply_markup=get_edit_tp_keyboard(direction, entry, current_tp)
        )
        return

    if data.startswith("edit_sl_quick_"):
        sl_val = float(data[14:])
        session = USER_SESSIONS.get(chat_id)
        if not session or session.get("wizard") != "edit_sltp":
            return
        session["data"]["stop_loss"] = sl_val
        session["step"] = "WAITING_EDIT_TP"
        entry = float(session.get("entry_price", 0.0))
        direction = session.get("direction", "LONG")
        current_tp = session.get("orig_tp")
        api.edit_message_text(
            chat_id,
            message_id,
            f"Neuer Stop-Loss: <b>{fmt_price(sl_val)} $</b>\n\n"
            f"<b>Schritt 2 von 2: Neuer Take-Profit (TP)</b>\n"
            f"Tippe das neue Kursziel in den Chat oder wähle eine Option:",
            reply_markup=get_edit_tp_keyboard(direction, entry, current_tp)
        )
        return

    if data == "edit_tp_keep":
        session = USER_SESSIONS.get(chat_id)
        if not session or session.get("wizard") != "edit_sltp":
            return
        render_edit_sltp_confirm(api, chat_id, message_id, session)
        return

    if data == "edit_tp_clear":
        session = USER_SESSIONS.get(chat_id)
        if not session or session.get("wizard") != "edit_sltp":
            return
        session["data"]["take_profit"] = None
        render_edit_sltp_confirm(api, chat_id, message_id, session)
        return

    if data.startswith("edit_tp_quick_"):
        tp_val = float(data[14:])
        session = USER_SESSIONS.get(chat_id)
        if not session or session.get("wizard") != "edit_sltp":
            return
        session["data"]["take_profit"] = tp_val
        render_edit_sltp_confirm(api, chat_id, message_id, session)
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
            from manage_positions import close_position
            closed_rec = close_position(pos_id, user_id=str(user_id), exit_reason="MANUAL_CLOSE", sync_db=True, git_push=True, notify=True)
            if closed_rec:
                sym = closed_rec.get("symbol", pos_id)
                lev_pnl = closed_rec.get("realized_pnl_leveraged_pct", 0.0)
                pnl_s = "+" if lev_pnl >= 0 else ""
                kb = {
                    "inline_keyboard": [
                        [{"text": "📜 Trade-Historie ansehen", "callback_data": "menu_my_history"}],
                        [{"text": "📊 Zu meinen Trades", "callback_data": "menu_my_trades"}],
                        [{"text": "🔙 Hauptmenü", "callback_data": "menu_main"}]
                    ]
                }
                api.edit_message_text(
                    chat_id,
                    message_id,
                    f"✅ <b>Position {sym} erfolgreich geschlossen!</b>\n\n"
                    f"• Realisierter PnL: <b>{pnl_s}{lev_pnl:.2f}%</b>\n"
                    f"• Der Trade wurde in deiner <b>Trade-Historie</b> archiviert und das Dashboard aktualisiert.",
                    reply_markup=kb
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
        parts = data.split("_", 3)
        target_uid = parts[2]
        raw_uname = parts[3] if len(parts) > 3 else ""
        if raw_uname and raw_uname != "None":
            target_uname = raw_uname
        else:
            target_uname = f"User_{target_uid}"

        cfg = load_config()
        auth_users = cfg.setdefault("authorized_users", {})
        # Vorherige Alt-/Dummy-Einträge für diese User-ID bereinigen
        keys_to_del = [k for k, v in auth_users.items() if str(v.get("chat_id")) == str(target_uid)]
        for k in keys_to_del:
            del auth_users[k]

        auth_users[target_uname] = {
            "name": target_uname,
            "chat_id": str(target_uid),
            "role": "trader",
            "added_at": datetime.now(timezone.utc).isoformat()
        }
        save_config(cfg)
        sync_dashboard_auth_async()

        disp_uname = f"@{target_uname}" if not target_uname.startswith("User_") else target_uname
        api.edit_message_text(chat_id, message_id, f"✅ Benutzer <b>{disp_uname}</b> (ID: {target_uid}) wurde erfolgreich als Trader freigeschaltet!")
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

    # Admin: Benutzer-Anfrage ablehnen
    if data.startswith("reject_user_") and role == "admin":
        target_uid = data.split("_", 2)[2]
        api.edit_message_text(chat_id, message_id, f"❌ Zugriffsanfrage für User-ID <code>{target_uid}</code> wurde abgelehnt.")
        try:
            api.send_message(
                target_uid,
                "❌ <b>Deine Zugriffsanfrage wurde leider abgelehnt.</b>"
            )
        except Exception:
            pass
        return

    # 10. Admin: Benutzer löschen / Zugriff entziehen - Abfrage
    if data.startswith("user_del_ask_") and role == "admin":
        target_uid = data[len("user_del_ask_"):]
        cfg = load_config()
        auth_users = cfg.get("authorized_users", {})

        target_info = None
        target_key = None
        for k, v in auth_users.items():
            if str(v.get("chat_id")) == str(target_uid) or str(k) == str(target_uid):
                target_info = v
                target_key = k
                break

        if not target_info:
            api.edit_message_text(
                chat_id,
                message_id,
                "⚠️ Benutzer wurde nicht gefunden oder bereits entfernt.",
                reply_markup={"inline_keyboard": [[{"text": "🔙 Zurück", "callback_data": "menu_users"}]]}
            )
            return

        disp_name = f"@{target_key}" if target_key and target_key != "None" and not target_key.startswith("User_") else (target_info.get("name") or f"User {target_uid}")
        confirm_text = (
            f"⚠️ <b>Benutzerzugriff entfernen?</b>\n\n"
            f"Möchtest du <b>{disp_name}</b> (ID: <code>{target_uid}</code>) wirklich aus dem Trading-System löschen?\n\n"
            f"• Der Zugriff auf Bot, Signale und Dashboard wird sofort gesperrt.\n"
            f"• Bei der nächsten Kontaktaufnahme muss die Person eine neue Freischaltungsanfrage stellen."
        )
        confirm_kb = {
            "inline_keyboard": [
                [{"text": f"🚨 Ja, {disp_name} löschen", "callback_data": f"user_del_confirm_{target_uid}"}],
                [{"text": "🔙 Abbrechen", "callback_data": "menu_users"}]
            ]
        }
        api.edit_message_text(chat_id, message_id, confirm_text, reply_markup=confirm_kb)
        return

    # 11. Admin: Benutzer löschen - Bestätigt
    if data.startswith("user_del_confirm_") and role == "admin":
        target_uid = data[len("user_del_confirm_"):]
        cfg = load_config()
        auth_users = cfg.setdefault("authorized_users", {})

        deleted_name = f"User {target_uid}"
        keys_to_del = []
        for k, v in auth_users.items():
            if str(v.get("chat_id")) == str(target_uid) or str(k) == str(target_uid):
                keys_to_del.append(k)
                deleted_name = f"@{k}" if k and k != "None" and not k.startswith("User_") else (v.get("name") or f"User {target_uid}")

        for k in keys_to_del:
            del auth_users[k]

        save_config(cfg)
        sync_dashboard_auth_async()

        # Optional User-Präferenzen aufräumen
        try:
            all_prefs = load_all_user_preferences()
            if str(target_uid) in all_prefs:
                del all_prefs[str(target_uid)]
                save_all_user_preferences(all_prefs)
        except Exception:
            pass

        result_text = (
            f"✅ <b>Benutzerzugriff erfolgreich entfernt!</b>\n\n"
            f"Benutzer <b>{deleted_name}</b> (ID: <code>{target_uid}</code>) wurde aus der Autorisierungsliste gelöscht.\n\n"
            f"Sobald sich die Person erneut meldet (z. B. mit neuem Benutzernamen), erhältst du eine neue Freischaltungsanfrage zur Bestätigung."
        )
        result_kb = {
            "inline_keyboard": [
                [{"text": "👥 Zurück zur Benutzerverwaltung", "callback_data": "menu_users"}],
                [{"text": "🏠 Hauptmenü", "callback_data": "menu_main"}]
            ]
        }
        api.edit_message_text(chat_id, message_id, result_text, reply_markup=result_kb)
        return


def process_wizard_text_input(api, chat_id, user_id, username, session, text):
    step = session.get("step")

    if step == "WAITING_TICKER":
        raw_ticker = text.strip()
        candidates = search_matching_assets(raw_ticker, max_results=5)

        # Fall 1: Exakt ein eindeutiges Ergebnis
        if len(candidates) == 1:
            cand = candidates[0]
            symbol = cand["symbol"]
            session["data"]["symbol"] = symbol
            session["data"]["name"] = cand["name"]
            session["data"]["live_price"] = cand["price"]
            session["step"] = "SELECT_DIRECTION"
            p_fmt = f"{fmt_price(cand['price'])} {cand['currency']}"
            api.send_message(
                chat_id,
                f"🎯 <b>Asset erkannt:</b> {cand['name']} (<code>{symbol}</code>)\n"
                f"• Aktueller Live-Kurs: ~<b>{p_fmt}</b>\n\n"
                f"Schritt 2: Wähle die Richtung:",
                reply_markup=get_direction_keyboard()
            )
            return

        # Fall 2: Mehrere Vorschläge gefunden (Fuzzy-Matches & Alternativen)
        elif len(candidates) > 1:
            buttons = []
            for c in candidates:
                p_fmt = f"{fmt_price(c['price'])} {c['currency']}"
                btn_txt = f"🟢 {c['name']} ({c['ticker']}) - {p_fmt}"
                buttons.append([{"text": btn_txt, "callback_data": f"wiz_sel_sym:{c['symbol']}"}])

            raw_upper = raw_ticker.upper()
            buttons.append([{"text": f"✏️ '{raw_upper}' manuell verwenden", "callback_data": f"wiz_sel_sym_raw:{raw_upper}"}])
            buttons.append([{"text": "❌ Abbrechen", "callback_data": "action_cancel"}])

            kb = {"inline_keyboard": buttons}
            api.send_message(
                chat_id,
                f"🔍 <b>Vorschläge für '{raw_ticker}':</b>\n"
                f"Meintest du eines dieser Assets? Bitte wähle aus:",
                reply_markup=kb
            )
            return

        # Fall 3: Kein Match gefunden
        else:
            raw_upper = raw_ticker.upper()
            kb = {
                "inline_keyboard": [
                    [{"text": f"✅ Als '{raw_upper}' anlegen", "callback_data": f"wiz_sel_sym_raw:{raw_upper}"}],
                    [{"text": "🔄 Anderen Ticker eingeben", "callback_data": "cat_custom"}],
                    [{"text": "❌ Abbrechen", "callback_data": "action_cancel"}]
                ]
            }
            api.send_message(
                chat_id,
                f"⚠️ Kein bekanntes Asset für '<b>{raw_ticker}</b>' im System gefunden.\n\n"
                f"Möchtest du <code>{raw_upper}</code> trotzdem als individuelles Symbol tracken oder einen anderen Begriff eingeben?",
                reply_markup=kb
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
        session["step"] = "WAITING_SL"
        direction = session["data"].get("direction", "LONG")
        entry_p = float(session["data"].get("entry_price", 0.0))
        api.send_message(
            chat_id,
            f"Hebel: <b>{lev_val:g}x</b>\n\nSchritt 5: 🛑 <b>Stop-Loss (SL) festlegen</b>\n\n"
            f"Gib deinen gewünschten Stop-Loss Kurs als Zahl in den Chat ein, "
            f"wähle einen Schnell-Vorschlag oder überspringe diesen Schritt:",
            reply_markup=get_stop_loss_keyboard(direction, entry_p)
        )
        return

    if step == "WAITING_SL":
        cleaned = text.replace("$", "").replace("€", "").replace(",", ".").strip()
        try:
            sl_val = float(cleaned)
            if sl_val <= 0:
                raise ValueError()
        except ValueError:
            api.send_message(chat_id, "⚠️ Ungültiger Stop-Loss Kurs. Bitte gib eine positive Zahl ein (z. B. 65000 oder 270.50):")
            return

        session["data"]["stop_loss"] = sl_val
        session["step"] = "WAITING_TP"
        direction = session["data"].get("direction", "LONG")
        entry_p = float(session["data"].get("entry_price", 0.0))
        api.send_message(
            chat_id,
            f"Stop-Loss: <b>{fmt_price(sl_val)} $</b>\n\nSchritt 6: 🎯 <b>Take-Profit (TP) festlegen</b>\n\n"
            f"Gib dein Kursziel als Zahl in den Chat ein, wähle einen Schnell-Vorschlag oder überspringe diesen Schritt:",
            reply_markup=get_take_profit_keyboard(direction, entry_p)
        )
        return

    if step == "WAITING_TP":
        cleaned = text.replace("$", "").replace("€", "").replace(",", ".").strip()
        try:
            tp_val = float(cleaned)
            if tp_val <= 0:
                raise ValueError()
        except ValueError:
            api.send_message(chat_id, "⚠️ Ungültiger Take-Profit Kurs. Bitte gib eine positive Zahl ein (z. B. 92000 oder 310.00):")
            return

        session["data"]["take_profit"] = tp_val
        session["step"] = "WAITING_NOTE"
        api.send_message(
            chat_id,
            f"Take-Profit: <b>{fmt_price(tp_val)} $</b>\n\nSchritt 7: Optionale Notiz hinterlegen?\n"
            "<i>(Einfach als Nachricht antworten oder Button unten nutzen)</i>",
            reply_markup=get_note_keyboard()
        )
        return

    if step == "WAITING_NOTE":
        session["data"]["note"] = text.strip()
        render_trade_summary_and_confirm(api, chat_id, None, session["data"])
        return

    if step == "WAITING_EDIT_SL":
        cleaned = text.replace("$", "").replace("€", "").replace(",", ".").strip()
        try:
            sl_val = float(cleaned)
            if sl_val <= 0:
                raise ValueError()
        except ValueError:
            api.send_message(chat_id, "⚠️ Ungültiger Stop-Loss Kurs. Bitte gib eine positive Zahl ein:")
            return

        session["data"]["stop_loss"] = sl_val
        session["step"] = "WAITING_EDIT_TP"
        entry_p = float(session.get("entry_price", 0.0))
        direction = session.get("direction", "LONG")
        current_tp = session.get("orig_tp")
        api.send_message(
            chat_id,
            f"Neuer Stop-Loss: <b>{fmt_price(sl_val)} $</b>\n\n"
            f"<b>Schritt 2 von 2: Neuer Take-Profit (TP)</b>\n"
            f"Tippe das neue Kursziel in den Chat oder wähle eine Option:",
            reply_markup=get_edit_tp_keyboard(direction, entry_p, current_tp)
        )
        return

    if step == "WAITING_EDIT_TP":
        cleaned = text.replace("$", "").replace("€", "").replace(",", ".").strip()
        try:
            tp_val = float(cleaned)
            if tp_val <= 0:
                raise ValueError()
        except ValueError:
            api.send_message(chat_id, "⚠️ Ungültiger Take-Profit Kurs. Bitte gib eine positive Zahl ein:")
            return

        session["data"]["take_profit"] = tp_val
        render_edit_sltp_confirm(api, chat_id, None, session)
        return

    if step == "WAITING_EDIT_ENTRY":
        cleaned = text.replace("$", "").replace("€", "").replace(",", ".").strip()
        try:
            entry_val = float(cleaned)
            if entry_val <= 0:
                raise ValueError()
        except ValueError:
            api.send_message(chat_id, "⚠️ Ungültiger Einstiegskurs. Bitte gib eine positive Zahl ein (z. B. 125.50):")
            return

        pos_id = session.get("pos_id")
        sym = session.get("symbol", "")
        USER_SESSIONS.pop(chat_id, None)

        try:
            from manage_positions import update_position
            update_position(symbol_or_id=pos_id, user_id=str(user_id), entry_price=entry_val, sync_db=True, git_push=True)
            text_resp, kb = get_manage_position_text_and_markup(pos_id, user_id)
            api.send_message(chat_id, f"✅ <b>Einstiegskurs für {sym} erfolgreich auf {fmt_price(entry_val)} $ geändert!</b>\n\n" + text_resp, reply_markup=kb)
        except Exception as e:
            api.send_message(chat_id, f"❌ Fehler beim Aktualisieren: {e}", reply_markup=get_main_menu_keyboard(role="trader"))
        return

    if step == "WAITING_EDIT_LEVERAGE":
        cleaned = text.lower().replace("x", "").replace(",", ".").strip()
        try:
            lev_val = float(cleaned)
            if lev_val < 1.0 or lev_val > 125.0:
                raise ValueError("out_of_range")
        except ValueError as ve:
            if str(ve) == "out_of_range":
                api.send_message(chat_id, "⚠️ Der Hebel muss zwischen <b>1x</b> (ungehebelt) und maximal <b>125x</b> liegen. Bitte gib einen gültigen Hebel ein (z. B. <code>5</code>, <code>7.5</code> oder <code>20x</code>):")
            else:
                api.send_message(chat_id, "⚠️ Ungültige Eingabe für den Hebel. Bitte gib eine Zahl ein (z. B. <code>5</code>, <code>10</code> oder <code>25x</code>):")
            return

        pos_id = session.get("pos_id")
        sym = session.get("symbol", "")
        USER_SESSIONS.pop(chat_id, None)

        try:
            from manage_positions import update_position
            update_position(symbol_or_id=pos_id, user_id=str(user_id), leverage=lev_val, sync_db=True, git_push=True)
            text_resp, kb = get_manage_position_text_and_markup(pos_id, user_id)
            api.send_message(chat_id, f"✅ <b>Hebel für {sym} erfolgreich auf {lev_val:g}x geändert!</b>\n\n" + text_resp, reply_markup=kb)
        except Exception as e:
            api.send_message(chat_id, f"❌ Fehler beim Aktualisieren des Hebels: {e}", reply_markup=get_main_menu_keyboard(role="trader"))
        return


def render_trade_summary_and_confirm(api, chat_id, message_id, data):
    sym = data.get("symbol")
    sig = data.get("direction")
    entry = data.get("entry_price", 0.0)
    lev = data.get("leverage", 1.0)
    sl = data.get("stop_loss")
    tp = data.get("take_profit")
    note = data.get("note", "")

    sig_icon = "🟢" if sig == "LONG" else "🔴"
    sl_str = f"{fmt_price(sl)} $" if sl is not None else "<i>Nicht gesetzt</i>"
    tp_str = f"{fmt_price(tp)} $" if tp is not None else "<i>Nicht gesetzt</i>"

    crv_line = ""
    if sl is not None and tp is not None and entry > 0:
        risk = abs(entry - float(sl))
        reward = abs(float(tp) - entry)
        if risk > 0:
            crv_line = f"\n• ⚖️ <b>CRV:</b> 1 : {reward / risk:.2f}"

    summary_text = (
        f"📋 <b>Trade-Zusammenfassung</b>\n\n"
        f"• <b>Symbol:</b> <code>{sym}</code>\n"
        f"• <b>Richtung:</b> {sig_icon} <b>{sig}</b>\n"
        f"• <b>Einstiegskurs:</b> {entry:,.2f} $\n"
        f"• <b>Hebel:</b> {lev:g}x\n"
        f"• 🛑 <b>Stop-Loss:</b> {sl_str}\n"
        f"• 🎯 <b>Take-Profit:</b> {tp_str}{crv_line}\n"
    )
    if note:
        summary_text += f"• <b>Notiz:</b> <i>{note}</i>\n"

    summary_text += "\nKlicke auf <b>Bestätigen</b>, um den Trade sofort anzulegen:"

    if message_id:
        api.edit_message_text(chat_id, message_id, summary_text, reply_markup=get_confirm_trade_keyboard())
    else:
        api.send_message(chat_id, summary_text, reply_markup=get_confirm_trade_keyboard())


def render_edit_sltp_confirm(api, chat_id, message_id, session):
    sym = session.get("symbol")
    sig = session.get("direction", "LONG")
    entry = float(session.get("entry_price", 0.0))
    sl = session["data"].get("stop_loss")
    tp = session["data"].get("take_profit")

    sl_str = f"{fmt_price(sl)} $" if sl is not None else "<i>Kein Stop-Loss</i>"
    tp_str = f"{fmt_price(tp)} $" if tp is not None else "<i>Kein Take-Profit</i>"

    crv_line = ""
    if sl is not None and tp is not None and entry > 0:
        risk = abs(entry - float(sl))
        reward = abs(float(tp) - entry)
        if risk > 0:
            crv_line = f"\n• ⚖️ <b>Neues CRV:</b> 1 : {reward / risk:.2f}"

    text = (
        f"🎯 <b>Neue Parameter für {sym} ({sig})</b>\n\n"
        f"• <b>Einstieg:</b> {entry:,.2f} $\n"
        f"• 🛑 <b>Neuer Stop-Loss:</b> {sl_str}\n"
        f"• 🎯 <b>Neuer Take-Profit:</b> {tp_str}{crv_line}\n\n"
        f"Möchtest du diese Werte jetzt speichern & übernehmen?"
    )

    if message_id:
        api.edit_message_text(chat_id, message_id, text, reply_markup=get_confirm_edit_sltp_keyboard())
    else:
        api.send_message(chat_id, text, reply_markup=get_confirm_edit_sltp_keyboard())


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
