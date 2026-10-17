#!/usr/bin/env python3
"""
Zentrales Benachrichtigungs-Modul für iOS Alerts & Desktop-Pushes.
Unterstützt:
1. ntfy.sh (Kostenlos, ohne Registrierung, sofortige iOS Push-Alerts via ntfy iOS-App)
2. Telegram Bot (Direkte Nachrichten auf das iPhone)
3. Discord / Pushover Webhooks
"""

import json
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "notification_config.json"

DEFAULT_CONFIG = {
    "enabled": False,
    "provider": "ntfy",  # "ntfy" oder "telegram"
    "ntfy": {
        "topic": "bbbdc-trading-alerts",  # In der ntfy iOS-App einfach dieses Topic abonnieren!
        "server": "https://ntfy.sh",
        "priority": "high",
        "tags": ["chart_with_upwards_trend", "bell"],
        "click_url": "https://bbbdc.github.io/trading-dashboard/"
    },
    "telegram": {
        "bot_token": "",
        "chat_id": ""
    },
    "min_score_filter": 90  # Sendet Alerts für Top-Setups >= 90%
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


def send_scan_summary_notification(db_data):
    """
    Formatiert die Scan-Ergebnisse und sendet einen iOS Alert.
    """
    conf = load_config()
    if not conf.get("enabled", False):
        print("ℹ️ iOS Push-Alerts sind in notification_config.json derzeit deaktiviert (enabled: false).")
        return False

    total = db_data.get("total_analyzed", 0)
    longs = db_data.get("long_count", 0)
    shorts = db_data.get("short_count", 0)
    assets = db_data.get("assets", [])

    top_assets = [a for a in assets if a.get("signal") != "NEUTRAL"][:3]

    title = f"🚀 TV Super-Analyst: {longs} Longs | {shorts} Shorts"
    lines = [
        f"📊 Scan abgeschlossen: {total} Assets analysiert.",
        f"🟢 {longs} Longs  |  🔴 {shorts} Shorts\n",
        "🔥 Top High-Conviction Setups:"
    ]

    for a in top_assets:
        lines.append(f"• [{a['signal']} {a['score']}%] {a['name']}: Entry {a['entry_range'][0]:,.2f} | TP2 {a['take_profit_2']:,.2f}")

    click_url = conf.get("ntfy", {}).get("click_url", "https://bbbdc.github.io/trading-dashboard/")
    message = "\n".join(lines)

    provider = conf.get("provider", "ntfy")
    success = False

    if provider == "ntfy" or provider == "all":
        tags = conf.get("ntfy", {}).get("tags", ["chart_with_upwards_trend", "rocket"])
        success = send_ntfy_alert(title, message, click_url=click_url, tags=tags)
        if success:
            print("✅ iOS Alert via ntfy erfolgreich versendet!")

    if provider == "telegram" or provider == "all":
        tg_msg = f"*{title}*\n\n{message}\n\n👉 [Dashboard öffnen]({click_url})"
        if send_telegram_alert(tg_msg):
            print("✅ Telegram Alert erfolgreich versendet!")
            success = True

    return success


if __name__ == "__main__":
    import sys
    print("Testing iOS Alert via ntfy...")
    test_title = "🔔 Test: TradingView Super-Analyst iOS Alert"
    test_msg = "Dieser Test-Alert bestätigt deine iPhone-Verbindung! Das Dashboard ist live."
    res = send_ntfy_alert(test_title, test_msg, click_url="https://bbbdc.github.io/trading-dashboard/")
    print("Resultat:", "Erfolgreich!" if res else "Fehlgeschlagen")
