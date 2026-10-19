#!/usr/bin/env python3
"""
TradingView Super-Analyst – Google Gemini API Quota & Usage Tracker.
Verwaltet und überwacht das Kontingent für den konfigurierten Google AI Studio API-Key.
- Zählt die täglichen Requests & Tokens
- Erkennt automatisch Quota-Grenzen (z.B. 20 Requests/Tag im Free Tier für gemini-3.8-flash)
- Speichert den Status in knowledge_base/gemini_quota.json
- Bereitet Statusdaten für das Web-Dashboard auf
"""

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

BASE_DIR = Path(__file__).resolve().parent
QUOTA_FILE = BASE_DIR / "knowledge_base" / "gemini_quota.json"
CONFIG_FILE = BASE_DIR / "gemini_config.json"


def load_quota_state():
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    default_state = {
        "date": today_str,
        "api_key_masked": "AQ.Ab8...Ww",
        "model": "gemini-3.8-flash",
        "daily_limit": 20,  # Google AI Studio Free Tier Limit für gemini-3.8-flash
        "requests_used_today": 0,
        "requests_remaining": 20,
        "tokens_used_today": 0,
        "status": "ACTIVE",
        "is_exhausted": False,
        "reset_time_utc": (datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat(),
        "last_request_timestamp": None,
        "last_error": None
    }

    if QUOTA_FILE.exists():
        try:
            with open(QUOTA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Neuer Tag? -> Zähler zurücksetzen
                if data.get("date") != today_str:
                    default_state["daily_limit"] = data.get("daily_limit", 20)
                    default_state["api_key_masked"] = data.get("api_key_masked", "AQ.Ab8...Ww")
                    save_quota_state(default_state)
                    return default_state
                return data
        except Exception:
            pass

    save_quota_state(default_state)
    return default_state


def save_quota_state(state):
    QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(QUOTA_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def record_successful_request(tokens_used=0):
    state = load_quota_state()
    state["requests_used_today"] = state.get("requests_used_today", 0) + 1
    state["tokens_used_today"] = state.get("tokens_used_today", 0) + int(tokens_used)
    limit = state.get("daily_limit", 20)
    state["requests_remaining"] = max(0, limit - state["requests_used_today"])
    state["last_request_timestamp"] = datetime.now(timezone.utc).isoformat()
    state["status"] = "ACTIVE"
    state["is_exhausted"] = (state["requests_remaining"] == 0)
    state["last_error"] = None
    save_quota_state(state)
    return state


def record_quota_exhausted(err_message, retry_seconds=None):
    state = load_quota_state()
    state["status"] = "EXHAUSTED"
    state["is_exhausted"] = True
    limit = state.get("daily_limit", 20)
    state["requests_used_today"] = max(state.get("requests_used_today", 0), limit)
    state["requests_remaining"] = 0
    state["last_error"] = str(err_message)

    if retry_seconds and retry_seconds > 0:
        reset_dt = datetime.now(timezone.utc) + timedelta(seconds=retry_seconds)
        state["reset_time_utc"] = reset_dt.isoformat()

    save_quota_state(state)
    return state


def get_quota_summary_for_dashboard():
    state = load_quota_state()
    limit = state.get("daily_limit", 20)
    used = state.get("requests_used_today", 0)
    remaining = max(0, limit - used)
    pct_used = round((used / limit * 100.0), 1) if limit > 0 else 100.0

    # Countdown bis Reset berechnen
    reset_str = state.get("reset_time_utc")
    countdown_display = "00:00 UTC"
    if reset_str:
        try:
            reset_dt = datetime.fromisoformat(reset_str)
            diff = reset_dt - datetime.now(timezone.utc)
            if diff.total_seconds() > 0:
                hours = int(diff.total_seconds() // 3600)
                minutes = int((diff.total_seconds() % 3600) // 60)
                countdown_display = f"in {hours}h {minutes}m"
            else:
                countdown_display = "bereit (Reset erfolgt)"
        except Exception:
            pass

    return {
        "api_key_masked": state.get("api_key_masked", "AQ.Ab8...Ww"),
        "model": state.get("model", "gemini-3.8-flash"),
        "daily_limit": limit,
        "requests_used_today": used,
        "requests_remaining": remaining,
        "percent_used": pct_used,
        "tokens_used_today": state.get("tokens_used_today", 0),
        "status": state.get("status", "ACTIVE"),
        "is_exhausted": state.get("is_exhausted", False),
        "reset_countdown": countdown_display,
        "last_error": state.get("last_error")
    }


if __name__ == "__main__":
    summary = get_quota_summary_for_dashboard()
    print("=" * 60)
    print("  GEMINI API-KEY KONTINGENT STATUS")
    print("=" * 60)
    print(f"Key           : {summary['api_key_masked']}")
    print(f"Modell        : {summary['model']}")
    print(f"Kontingent    : {summary['requests_used_today']} / {summary['daily_limit']} Anfragen ({summary['percent_used']}%)")
    print(f"Verbleibend   : {summary['requests_remaining']} Anfragen")
    print(f"Status        : {summary['status']}")
    print(f"Reset         : {summary['reset_countdown']}")
    print("=" * 60)
