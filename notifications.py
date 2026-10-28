#!/usr/bin/env python3
"""
TradingView Super-Analyst – Benachrichtigungs- & State-Tracking-Engine.
- Sendet iOS-Push-Nachrichten (ntfy / Telegram) NUR wenn sich Vorhersagen/Einstufungen ändern.
- Informiert gezielt NUR über jene Aktien/Kryptos, die sich tatsächlich geändert haben.
- Führt eine lückenlose Historie aller Benachrichtigungen in dashboard/history.json.
"""

import json
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "notification_config.json"
STATE_FILE = BASE_DIR / "knowledge_base" / "signal_state.json"
HISTORY_FILE = BASE_DIR / "dashboard" / "history.json"
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"

DEFAULT_CONFIG = {
    "enabled": True,
    "provider": "ntfy",
    "only_on_change": True,
    "min_score_filter": 85,
    "ntfy": {
        "topic": "bbbdc-trading-alerts",
        "server": "https://ntfy.sh",
        "priority": "high",
        "tags": ["chart_with_upwards_trend", "bell"],
        "click_url": "https://bbbdc.github.io/trading-dashboard/history.html"
    },
    "telegram": {
        "bot_token": "",
        "chat_id": ""
    }
}


def load_config():
    if not CONFIG_FILE.exists():
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG


def send_ntfy_alert(title, message, click_url=None, priority="high", tags=None):
    conf = load_config().get("ntfy", DEFAULT_CONFIG["ntfy"])
    topic = conf.get("topic")
    if not topic:
        return False

    server = conf.get("server", "https://ntfy.sh").rstrip("/")
    url = f"{server}/{topic}"

    headers = {
        "Title": title.encode("utf-8"),
        "Priority": priority,
    }
    if click_url:
        headers["Click"] = click_url
    if tags:
        headers["Tags"] = ",".join(tags)

    req = urllib.request.Request(url, data=message.encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"ntfy Alert Fehler: {e}")
        return False


TELEGRAM_CONFIG_FILE = BASE_DIR / "telegram_config.json"


USER_PREFS_FILE = BASE_DIR / "knowledge_base" / "user_alert_preferences.json"
POSITIONS_FILE = BASE_DIR / "knowledge_base" / "user_positions.json"
LIVE_WATCHLISTS_FILE = BASE_DIR / "knowledge_base" / "live_watchlists.json"


def load_live_watchlists_map():
    wl_map = {}
    if LIVE_WATCHLISTS_FILE.exists():
        try:
            with open(LIVE_WATCHLISTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for wl in data.get("watchlists", []):
                    name = wl.get("name")
                    if name:
                        wl_map[name] = set(wl.get("symbols", []))
        except Exception:
            pass
    return wl_map


def map_symbol_to_category_key(symbol):
    try:
        from market_schedule import classify_symbol
        c = classify_symbol(symbol).get("category")
        if c == "CRYPTO":
            return "cat_crypto"
        elif c == "US_STOCKS":
            return "cat_ustech"
        elif c == "EU_STOCKS":
            return "cat_dax"
        elif c == "COMMODITIES_FUTURES":
            return "cat_commodities"
    except Exception:
        pass
    return "cat_crypto" if any(x in symbol for x in ["BTC", "ETH", "USDT"]) else "cat_ustech"


def send_telegram_alert(message, parse_mode="HTML", target_chat_ids=None):
    token = None
    chat_ids = set()

    # 1. Aus telegram_config.json lesen (bevorzugt)
    if TELEGRAM_CONFIG_FILE.exists():
        try:
            with open(TELEGRAM_CONFIG_FILE, "r", encoding="utf-8") as f:
                tconf = json.load(f)
                token = tconf.get("bot_token")
                for cid in tconf.get("admin_chat_ids", []):
                    chat_ids.add(str(cid))
                for uname, udata in tconf.get("authorized_users", {}).items():
                    if isinstance(udata, dict) and udata.get("chat_id"):
                        chat_ids.add(str(udata.get("chat_id")))
        except Exception:
            pass

    # 2. Fallback auf notification_config.json
    if not token or not chat_ids:
        conf = load_config().get("telegram", {})
        token = token or conf.get("bot_token")
        if conf.get("chat_id"):
            chat_ids.add(str(conf.get("chat_id")))

    # Falls gezielte Empfänger übergeben wurden
    if target_chat_ids:
        chat_ids = set(str(c) for c in target_chat_ids if str(c))

    if not token or not chat_ids:
        return False

    success = False
    for chat_id in chat_ids:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": "true"
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    success = True
        except Exception as e:
            print(f"Telegram Alert Fehler für {chat_id}: {e}")

    return success


def load_signal_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_signal_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_history():
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "events" in data:
                    return data["events"]
        except Exception:
            pass
    return []


def record_history_event(event):
    history = load_history()
    history.insert(0, event)  # Neueste zuerst
    history = history[:150]   # Maximal 150 Events im Speicher halten
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    try:
        from build_history import generate_history_html
        generate_history_html()
    except Exception:
        pass


def detect_signal_changes(current_assets):
    """
    Vergleicht den aktuellen Scan mit dem vorherigen Scan-Zustand.
    Erkennt:
    - Signal-Änderungen (z.B. NEUTRAL -> LONG, LONG -> NEUTRAL, etc.)
    - Signifikante Score-Sprünge (>= 6 Punkte oder Über-/Unterschreiten von 85%)
    - Setup-Wechsel bei aktiven Setups
    """
    prev_state = load_signal_state()
    is_initial_run = (len(prev_state) == 0)

    changes = []
    new_state = {}

    for a in current_assets:
        sym = a["symbol"]
        curr_sig = a.get("signal", "NEUTRAL")
        curr_score = a.get("score", 50)
        curr_setup = a.get("setup_name", "")
        curr_price = a.get("price", 0.0)

        new_state[sym] = {
            "symbol": sym,
            "name": a["name"],
            "signal": curr_sig,
            "score": curr_score,
            "setup_name": curr_setup,
            "price": curr_price,
            "entry_range": a.get("entry_range", [curr_price, curr_price]),
            "stop_loss": a.get("stop_loss", 0.0),
            "take_profit_2": a.get("take_profit_2", 0.0),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        if is_initial_run:
            continue

        if sym not in prev_state:
            # Neues Symbol in Watchlist mit aktivem Signal
            if curr_sig != "NEUTRAL":
                changes.append({
                    "symbol": sym,
                    "name": a["name"],
                    "category": a.get("category", ""),
                    "change_type": "NEW_ASSET",
                    "old_signal": "NEU",
                    "new_signal": curr_sig,
                    "old_score": 0,
                    "new_score": curr_score,
                    "price": curr_price,
                    "setup_name": curr_setup,
                    "entry_range": a.get("entry_range", []),
                    "stop_loss": a.get("stop_loss", 0),
                    "take_profit_2": a.get("take_profit_2", 0),
                    "reasons": a.get("reasons", []),
                    "change_reason": f"Neues aktives Setup ({curr_sig}) mit {curr_score}% Konfluenz.",
                    "note": a.get("analyst_note", ""),
                    "evaluated_by": a.get("evaluated_by", "Confluence")
                })
            continue

        p_entry = prev_state[sym]
        old_sig = p_entry.get("signal", "NEUTRAL")
        old_score = p_entry.get("score", 50)
        old_setup = p_entry.get("setup_name", "")

        signal_changed = (curr_sig != old_sig)
        score_jump = abs(curr_score - old_score) >= 6
        crossed_threshold = (old_score < 85 and curr_score >= 85) or (old_score >= 85 and curr_score < 85)
        setup_changed = (old_sig != "NEUTRAL" and curr_sig != "NEUTRAL" and old_setup != curr_setup)

        if signal_changed or (curr_sig != "NEUTRAL" and (score_jump or crossed_threshold or setup_changed)):
            change_type = "SIGNAL_CHANGE" if signal_changed else ("SCORE_JUMP" if score_jump else "SETUP_UPDATE")
            
            # Konkrete Begründung ermitteln
            reasons = a.get("reasons", [])
            primary_reason = reasons[0] if reasons else a.get("analyst_note", "")
            if signal_changed:
                if old_sig == "NEUTRAL" and curr_sig in ("LONG", "SHORT"):
                    change_reason = f"Einstiegssignal: 3-fache Konfluenz bestätigt ({primary_reason})."
                elif old_sig in ("LONG", "SHORT") and curr_sig == "NEUTRAL":
                    change_reason = f"Ausstieg/Invalidierung: Setup nicht mehr aktiv ({primary_reason or 'Struktur verloren'})."
                else:
                    change_reason = f"Signal-Drehung ({old_sig} ➔ {curr_sig}): Marktstruktur hat gedreht ({primary_reason})."
            elif score_jump:
                change_reason = f"Konfluenz-Veränderung: Score springt von {old_score}% auf {curr_score}% ({primary_reason})."
            else:
                change_reason = f"Setup-Update: Wechsel auf '{curr_setup}' ({primary_reason})."

            changes.append({
                "symbol": sym,
                "name": a["name"],
                "category": a.get("category", ""),
                "change_type": change_type,
                "old_signal": old_sig,
                "new_signal": curr_sig,
                "old_score": old_score,
                "new_score": curr_score,
                "price": curr_price,
                "setup_name": curr_setup,
                "entry_range": a.get("entry_range", []),
                "stop_loss": a.get("stop_loss", 0),
                "take_profit_2": a.get("take_profit_2", 0),
                "reasons": reasons,
                "change_reason": change_reason,
                "note": a.get("analyst_note", ""),
                "evaluated_by": a.get("evaluated_by", "Confluence")
            })

    return changes, new_state, is_initial_run


def format_telegram_change_notification(changes, click_url):
    """
    Formatiert eine kristallklare HTML-Benachrichtigung für Telegram mit Emojis,
    Fettungen und direkten Setup-Kennzahlen.
    """
    count = len(changes)
    unit_str = "Asset" if count == 1 else "Assets"

    lines = [
        f"🔔 <b>TradingView Signal-Update: {count} {unit_str} aktualisiert</b>\n",
        f"<i>Echte Signal- & Einstufungswechsel:</i>\n"
    ]

    for c in changes[:6]:
        sig = c["new_signal"]
        icon = "🟢" if sig == "LONG" else ("🔴" if sig == "SHORT" else "⚪")
        name = c["name"]
        ticker = c["symbol"].split(":")[-1]
        old_s = c["old_signal"]
        new_s = c["new_signal"]
        score = c["new_score"]

        lines.append(f"{icon} <b>{name}</b> (<code>{ticker}</code>)")
        if old_s != new_s:
            lines.append(f"   • <b>Signalwechsel:</b> {old_s} ➔ <b>{new_s}</b> (Score: <b>{score}%</b>)")
        else:
            lines.append(f"   • <b>Score-Sprung:</b> {c['old_score']}% ➔ <b>{score}%</b> ({new_s})")

        if c.get("change_reason"):
            lines.append(f"   • 💡 <b>Grund:</b> {c['change_reason']}")
        elif c.get("reasons"):
            lines.append(f"   • 💡 <b>Grund:</b> {' | '.join(c['reasons'][:2])}")

        if c.get("note") and len(c.get("note")) > 10:
            lines.append(f"   • 📝 <i>KI: {c['note'][:130]}...</i>")

        if sig != "NEUTRAL" and c.get("entry_range"):
            entry_fmt = f"{c['entry_range'][0]:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            sl_fmt = f"{c['stop_loss']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            tp_fmt = f"{c['take_profit_2']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            lines.append(f"   • 🎯 <b>Setup:</b> {c['setup_name']}")
            lines.append(f"   • 📍 <b>Entry:</b> {entry_fmt} $ | <b>SL:</b> {sl_fmt} $ | <b>TP2:</b> {tp_fmt} $")
        lines.append("")

    if count > 6:
        lines.append(f"<i>... und {count - 6} weitere Änderungen.</i>\n")

    lines.append(f"📜 <a href=\"{click_url}\">Signal-Historie & Live-Charts im Web öffnen</a>")
    return "\n".join(lines)


USER_POS_ALERT_STATE = BASE_DIR / "knowledge_base" / "user_pos_alert_state.json"


def check_and_notify_user_positions(evaluated_positions):
    """
    Prüft alle Nutzerpositionen und sendet eine gezielte Push-Warnung, wenn:
    - SL-Gefahr / Liquidationsrisiko besteht (CRITICAL)
    - Take-Profit erreicht ist / Teilgewinne anstehen (TAKE_PROFIT)
    - Reversal-Divergenzen gegen die Position vorliegen (WARNING)
    Benachrichtigt nur einmal pro Statuswechsel (kein Spam).
    """
    if not evaluated_positions:
        return

    prev_state = {}
    if USER_POS_ALERT_STATE.exists():
        try:
            with open(USER_POS_ALERT_STATE, "r", encoding="utf-8") as f:
                prev_state = json.load(f)
        except Exception:
            pass

    new_state = dict(prev_state)

    for pos in evaluated_positions:
        pos_id = pos.get("id") or pos.get("symbol")
        rec = pos.get("recommendation", {})
        status = rec.get("status", "NEUTRAL")
        sym = pos.get("symbol")
        user_id = pos.get("user_id")

        if status not in ("CRITICAL", "TAKE_PROFIT", "WARNING"):
            new_state[pos_id] = status
            continue

        last_status = prev_state.get(pos_id)
        if last_status == status:
            continue

        new_state[pos_id] = status

        sig = pos.get("direction", "LONG")
        sig_icon = "🟢" if sig == "LONG" else "🔴"
        lev = pos.get("leverage", 1.0)
        pnl = pos.get("pnl_leveraged_pct", 0.0)
        pnl_sign = "+" if pnl >= 0 else ""

        if status == "CRITICAL":
            alert_header = f"🚨 <b>Dringende Warnung bei deinem Trade {sym}</b>"
        elif status == "TAKE_PROFIT":
            alert_header = f"🎯 <b>Gewinnmitnahme empfohlen bei {sym}</b>"
        else:
            alert_header = f"⚠️ <b>Achtung bei deiner Position {sym}</b>"

        msg_lines = [
            alert_header,
            "",
            f"• <b>Position:</b> {sig_icon} <b>{sym}</b> ({sig} | {lev:g}x Hebel)",
            f"• <b>Aktuelle Performance:</b> <b>{pnl_sign}{pnl:.2f}%</b>",
            f"• 💡 <b>Empfehlung:</b> <b>[{rec.get('action')}]</b> {rec.get('title')}",
            f"• <i>{rec.get('message')}</i>",
            "",
            "👉 Öffne den Bot oder das Dashboard, um deinen Stop-Loss anzupassen oder den Trade zu schließen."
        ]
        alert_msg = "\n".join(msg_lines)

        # 1. An den jeweiligen Trade-Inhaber senden
        if user_id:
            send_telegram_alert(alert_msg, parse_mode="HTML", target_chat_ids=[user_id])

        # 2. Master-Admin erhält IMMER Benachrichtigungen zu ALLEN Positionen
        admin_cids = []
        if TELEGRAM_CONFIG_FILE.exists():
            try:
                with open(TELEGRAM_CONFIG_FILE, "r", encoding="utf-8") as f:
                    admin_cids = json.load(f).get("admin_chat_ids", [])
            except Exception:
                pass

        admin_targets = [str(acid) for acid in admin_cids if str(acid) != str(user_id)]
        if admin_targets:
            uname = pos.get("user_name") or f"User_{user_id}"
            admin_msg = f"👤 <b>Nutzer-Trade (@{uname}):</b>\n\n{alert_msg}"
            send_telegram_alert(admin_msg, parse_mode="HTML", target_chat_ids=admin_targets)

    USER_POS_ALERT_STATE.parent.mkdir(parents=True, exist_ok=True)
    with open(USER_POS_ALERT_STATE, "w", encoding="utf-8") as f:
        json.dump(new_state, f, indent=2, ensure_ascii=False)


def format_change_notification(changes, click_url):
    """
    Formatiert eine kristallklare Benachrichtigung, die AUSSCHLIESSLICH die geänderten Assets
    und die exakte Begründung für den Signalwechsel enthält.
    """
    count = len(changes)
    unit_str = "Asset" if count == 1 else "Assets"
    title = f"🔔 TV-Signaländerung: {count} {unit_str} aktualisiert"

    lines = [
        f"🔄 Folgende {count} Einstufungen haben sich geändert:\n"
    ]

    for c in changes[:6]:  # Bis zu 6 Änderungen in einem Push
        sig = c["new_signal"]
        icon = "🟢" if sig == "LONG" else ("🔴" if sig == "SHORT" else "⚪")
        name = c["name"]
        ticker = c["symbol"].split(":")[-1]
        old_s = c["old_signal"]
        new_s = c["new_signal"]
        score = c["new_score"]

        lines.append(f"{icon} {name} ({ticker}):")
        if old_s != new_s:
            lines.append(f"   Signalwechsel: {old_s} ➔ {new_s} (Score: {score}%)")
        else:
            lines.append(f"   Score-Sprung: {c['old_score']}% ➔ {score}% ({new_s})")

        # Ausführliche Begründung für den Nutzer
        if c.get("change_reason"):
            lines.append(f"   💡 Grund: {c['change_reason']}")
        elif c.get("reasons"):
            lines.append(f"   💡 Grund: {' | '.join(c['reasons'][:2])}")
        
        if c.get("note") and len(c.get("note")) > 10:
            lines.append(f"   📝 KI-Rationale: {c['note'][:130]}...")

        lines.append(f"   Setup: {c['setup_name']}")
        if sig != "NEUTRAL" and c["entry_range"]:
            lines.append(f"   Entry: {c['entry_range'][0]:,.2f} | SL: {c['stop_loss']:,.2f} | TP2: {c['take_profit_2']:,.2f}")
        lines.append("")

    if count > 6:
        lines.append(f"... und {count - 6} weitere Änderungen.")

    lines.append(f"📜 Historie & Charts: {click_url}")
    return title, "\n".join(lines)


def send_scan_summary_notification(db_data, force_send=False):
    """
    Hauptfunktion für Benachrichtigungen:
    Prüft Änderungen, filtert Duplikate und sendet Push-Alerts nur bei echten Signalwechseln.
    Speichert jede Benachrichtigung in dashboard/history.json.
    """
    conf = load_config()
    if not conf.get("enabled", True):
        print("ℹ️ iOS Push-Alerts sind in notification_config.json derzeit deaktiviert (enabled: false).")
        return False

    assets = db_data.get("assets", [])
    if not assets:
        return False

    changes, new_state, is_initial = detect_signal_changes(assets)
    save_signal_state(new_state)

    click_url = conf.get("ntfy", {}).get("click_url", "https://bbbdc.github.io/trading-dashboard/history.html")

    # Bei allererstem Lauf: System-Start initialisieren
    if is_initial:
        print("ℹ️ Signal-State initialisiert (Baseline für 58 Assets angelegt).")
        init_event = {
            "id": f"evt_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "timestamp_display": datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC"),
            "title": "System-Start: Baseline-Scan initialisiert",
            "type": "SYSTEM_INIT",
            "change_count": 0,
            "changes": [],
            "summary": f"Initialisierung abgeschlossen. 58 Assets im 4h-Überwachungszyklus aktiv ({db_data.get('long_count', 0)} Longs, {db_data.get('short_count', 0)} Shorts). Zukünftige Signalwechsel werden automatisch erfasst.",
            "notification_sent": False
        }
        record_history_event(init_event)
        return False

    only_on_change = conf.get("only_on_change", True)

    if only_on_change and not changes and not force_send:
        print(f"ℹ️ Keine Signal- oder Einstufungsänderungen festgestellt ({len(assets)} Assets unverändert). Push-Benachrichtigung unterdrückt.")
        return False

    if not changes and force_send:
        # Fallback bei manueller Test-Ausführung
        top_assets = [a for a in assets if a.get("signal") != "NEUTRAL"][:3]
        title = f"ℹ️ Test-Scan: {len(assets)} Assets überwacht"
        lines = ["Manuell ausgelöster Testlauf. Aktuelle Top-Setups:\n"]
        for a in top_assets:
            lines.append(f"• [{a['signal']} {a['score']}%] {a['name']}: Entry {a['entry_range'][0]:,.2f} | TP2 {a['take_profit_2']:,.2f}")
        lines.append(f"\n👉 Historie: {click_url}")
        message = "\n".join(lines)
    else:
        title, message = format_change_notification(changes, click_url)

    provider = conf.get("provider", "ntfy")
    success = False

    if provider in ("ntfy", "all"):
        tags = ["chart_with_upwards_trend", "bell"]
        success = send_ntfy_alert(title, message, click_url=click_url, tags=tags)
        if success:
            print(f"✅ iOS Alert via ntfy erfolgreich versendet! ({len(changes)} Änderungen gemeldet)")

    if provider in ("telegram", "all"):
        user_targets = {}
        if TELEGRAM_CONFIG_FILE.exists():
            try:
                with open(TELEGRAM_CONFIG_FILE, "r", encoding="utf-8") as f:
                    tconf = json.load(f)
                    for cid in tconf.get("admin_chat_ids", []):
                        user_targets[str(cid)] = "admin"
                    for uname, udata in tconf.get("authorized_users", {}).items():
                        if isinstance(udata, dict) and udata.get("chat_id"):
                            user_targets[str(udata.get("chat_id"))] = udata.get("name") or uname
            except Exception:
                pass

        # User Positions laden (für Filter 'nur eigene Trades')
        active_user_symbols = {}
        if POSITIONS_FILE.exists():
            try:
                with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                    pos_data = json.load(f).get("positions", [])
                    for p in pos_data:
                        uid = str(p.get("user_id", ""))
                        if uid:
                            active_user_symbols.setdefault(uid, set()).add(p.get("symbol", ""))
            except Exception:
                pass

        # Alle gespeicherten Nutzerpräferenzen laden
        user_prefs_all = {}
        if USER_PREFS_FILE.exists():
            try:
                with open(USER_PREFS_FILE, "r", encoding="utf-8") as f:
                    user_prefs_all = json.load(f)
            except Exception:
                pass

        # TradingView Watchlists Map laden
        live_wl_map = load_live_watchlists_map()

        tg_sent_count = 0
        if not user_targets:
            tg_msg = format_telegram_change_notification(changes, click_url) if changes else f"<b>{title}</b>\n\n{message}"
            if send_telegram_alert(tg_msg, parse_mode="HTML"):
                tg_sent_count += 1
        else:
            for uid, uname in user_targets.items():
                u_pref = user_prefs_all.get(uid, {
                    "enabled": True,
                    "categories": ["cat_crypto", "cat_ustech", "cat_dax", "cat_commodities"],
                    "watchlists": ["Aktien", "Crypto", "Commodities", "Rohstoffe", "Devisen", "Eigene Trades"],
                    "min_score": 85,
                    "only_my_trades": False
                })

                if not u_pref.get("enabled", True):
                    continue

                u_cats = set(u_pref.get("categories", ["cat_crypto", "cat_ustech", "cat_dax", "cat_commodities"]))
                u_min_score = u_pref.get("min_score", 85)
                u_only_my_trades = u_pref.get("only_my_trades", False)
                u_wls = u_pref.get("watchlists")

                if u_wls is not None:
                    allowed_wl_symbols = set()
                    for wl_name in u_wls:
                        allowed_wl_symbols.update(live_wl_map.get(wl_name, set()))
                else:
                    allowed_wl_symbols = None

                # Filter changes für diesen spezifischen Nutzer
                filtered_changes = []
                for c in changes:
                    sym = c.get("symbol", "")
                    if c.get("new_score", 0) < u_min_score:
                        continue
                    cat_k = map_symbol_to_category_key(sym)
                    if cat_k not in u_cats:
                        continue
                    if allowed_wl_symbols is not None and sym not in allowed_wl_symbols:
                        continue
                    if u_only_my_trades:
                        user_syms = active_user_symbols.get(uid, set())
                        if sym not in user_syms:
                            continue
                    filtered_changes.append(c)

                if filtered_changes:
                    u_msg = format_telegram_change_notification(filtered_changes, click_url)
                    if send_telegram_alert(u_msg, parse_mode="HTML", target_chat_ids=[uid]):
                        tg_sent_count += 1
                        print(f"✅ Personalisierter Telegram Alert an @{uname} ({len(filtered_changes)} Treffer) gesendet.")
                elif force_send:
                    # Bei manuellem Testlauf trotzdem Bescheid geben
                    fallback_msg = f"<b>{title}</b>\n\n{message}"
                    send_telegram_alert(fallback_msg, parse_mode="HTML", target_chat_ids=[uid])
                    tg_sent_count += 1

        if tg_sent_count > 0:
            print(f"✅ Telegram Alerts erfolgreich an {tg_sent_count} Empfänger zugestellt!")
            success = True

    # In Web-Historie protokollieren
    event_entry = {
        "id": f"evt_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "timestamp_display": datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC"),
        "title": title,
        "type": "SIGNAL_UPDATE",
        "change_count": len(changes),
        "changes": changes,
        "notification_sent": success,
        "provider": provider,
        "raw_message": message
    }
    record_history_event(event_entry)

    return success


if __name__ == "__main__":
    print("Prüfe Benachrichtigungs-System & Historie...")
    if HISTORY_FILE.exists():
        h = load_history()
        print(f"Bestehende Historie-Einträge: {len(h)}")
    else:
        print("Noch keine Historie-Datei vorhanden.")

    if DB_FILE.exists():
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
        print("Führe Test-Prüfung auf Änderungen durch...")
        send_scan_summary_notification(db)
