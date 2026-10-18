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


def send_telegram_alert(message):
    conf = load_config().get("telegram", {})
    token = conf.get("bot_token")
    chat_id = conf.get("chat_id")
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": "false"
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Telegram Alert Fehler: {e}")
        return False


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
                "note": a.get("analyst_note", ""),
                "evaluated_by": a.get("evaluated_by", "Confluence")
            })

    return changes, new_state, is_initial_run


def format_change_notification(changes, click_url):
    """
    Formatiert eine kristallklare Benachrichtigung, die AUSSCHLIESSLICH die geänderten Assets enthält.
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
            lines.append(f"   Einstufung: {old_s} ➔ {new_s} (Score: {score}%)")
        else:
            lines.append(f"   Score-Sprung: {c['old_score']}% ➔ {score}% ({new_s})")

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
        tg_msg = f"*{title}*\n\n{message}"
        if send_telegram_alert(tg_msg):
            print("✅ Telegram Alert erfolgreich versendet!")
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
