#!/usr/bin/env python3
"""
TradingView Super-Analyst – Google Gemini Multi-Key Quota & Pool Manager.
Intelligentes Management und Monitoring mehrerer Google AI Studio API-Keys:
- Verwaltet einen Pool aus mehreren API-Keys (z.B. Key #1 und Key #2)
- Automatischer unterbrechungsfreier Failover: Ist Key #1 erschöpft (20/20),
  übernimmt sofort nahtlos Key #2 (+20 Anfragen) -> 40 Anfragen/Tag im Free Tier!
- Tracking aller Kennzahlen pro Key und aggregiert für das Gesamtsystem
- Sicherheit: Speichert ausschließlich maskierte Kennungen (AQ.***) in Quota-Dateien,
  die echten API-Keys verbleiben sicher in der lokalen gemini_config.json (.gitignore).
"""

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

BASE_DIR = Path(__file__).resolve().parent
QUOTA_FILE = BASE_DIR / "knowledge_base" / "gemini_quota.json"
CONFIG_FILE = BASE_DIR / "gemini_config.json"


def mask_key(k):
    if not k or len(k) < 12:
        return "AQ.***"
    return f"{k[:6]}...{k[-4:]}"


def get_configured_keys():
    """Liest die konfigurierten Keys aus der lokalen gemini_config.json oder .env."""
    keys = []
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                configured_list = cfg.get("api_keys", [])
                if isinstance(configured_list, list):
                    for k in configured_list:
                        if isinstance(k, str) and k.strip() and not k.startswith("DEIN_"):
                            if k.strip() not in keys:
                                keys.append(k.strip())
                single_key = cfg.get("api_key")
                if single_key and isinstance(single_key, str) and single_key.strip():
                    if single_key.strip() not in keys and not single_key.startswith("DEIN_"):
                        keys.append(single_key.strip())
        except Exception:
            pass

    env_file = BASE_DIR / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        k = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                        if k and k not in keys:
                            keys.append(k)
        except Exception:
            pass

    return keys


def load_quota_state():
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    midnight_utc = (datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat()
    configured_keys = get_configured_keys()

    state = {
        "date": today_str,
        "model": "gemini-3.8-flash",
        "keys": {},
        "pro_subscription": {
            "daily_budget": 50,
            "requests_used_today": 0,
            "requests_remaining": 50,
            "status": "ACTIVE",
            "last_used": None
        }
    }

    if QUOTA_FILE.exists():
        try:
            with open(QUOTA_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if saved.get("date") == today_str and isinstance(saved.get("keys"), dict):
                    state["keys"] = saved.get("keys", {})
                    state["model"] = saved.get("model", "gemini-3.8-flash")
                    if isinstance(saved.get("pro_subscription"), dict):
                        state["pro_subscription"] = saved["pro_subscription"]
                    if isinstance(saved.get("health_check"), dict):
                        state["health_check"] = saved["health_check"]
        except Exception:
            pass

    # Sicherstellen, dass alle konfigurierten Keys maskiert im State existieren
    for idx, k in enumerate(configured_keys, 1):
        k_mask = mask_key(k)
        if k_mask not in state["keys"]:
            state["keys"][k_mask] = {
                "id": f"key_{idx}",
                "name": f"API-Key #{idx}",
                "masked": k_mask,
                "daily_limit": 20,
                "requests_used_today": 0,
                "requests_remaining": 20,
                "tokens_used_today": 0,
                "status": "ACTIVE",
                "is_exhausted": False,
                "reset_time_utc": midnight_utc,
                "last_used_timestamp": None,
                "last_error": None
            }

    save_quota_state(state)
    return state


def save_quota_state(state):
    QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(QUOTA_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def get_active_api_key():
    """
    Liefert den aktuell besten / verfügbaren API-Key aus dem Pool.
    Priorisiert aktive Keys mit verbleibendem Kontingent.
    """
    state = load_quota_state()
    keys_dict = state.get("keys", {})
    configured_keys = get_configured_keys()

    # 1. Suche nach Keys mit Status ACTIVE und verbleibenden Requests
    for k in configured_keys:
        k_mask = mask_key(k)
        info = keys_dict.get(k_mask, {})
        if info.get("status") == "ACTIVE" and info.get("requests_remaining", 0) > 0:
            return k, k_mask

    # 2. Falls alle voll/erschöpft sind, liefere den ersten Key zurück
    if configured_keys:
        return configured_keys[0], mask_key(configured_keys[0])

    return None, "Kein Key konfiguriert"


def get_all_available_keys_in_pool():
    """Gibt alle Keys des Pools in Prioritätsreihenfolge zurück (aktive zuerst)."""
    state = load_quota_state()
    keys_dict = state.get("keys", {})
    configured_keys = get_configured_keys()

    available = []
    exhausted = []

    for k in configured_keys:
        k_mask = mask_key(k)
        info = keys_dict.get(k_mask, {})
        if info.get("status") == "ACTIVE" and info.get("requests_remaining", 0) > 0:
            available.append((k, k_mask))
        else:
            exhausted.append((k, k_mask))

    return available + exhausted


def record_successful_request(key, tokens_used=0):
    """Protokolliert einen erfolgreichen API-Aufruf für den entsprechenden Key."""
    state = load_quota_state()
    keys_dict = state.get("keys", {})
    k_mask = mask_key(key)

    if k_mask not in keys_dict:
        idx = len(keys_dict) + 1
        keys_dict[k_mask] = {
            "id": f"key_{idx}",
            "name": f"API-Key #{idx}",
            "masked": k_mask,
            "daily_limit": 20,
            "requests_used_today": 0,
            "requests_remaining": 20,
            "tokens_used_today": 0,
            "status": "ACTIVE",
            "is_exhausted": False,
            "reset_time_utc": (datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat(),
            "last_used_timestamp": None,
            "last_error": None
        }

    k_info = keys_dict[k_mask]
    k_info["requests_used_today"] = k_info.get("requests_used_today", 0) + 1
    k_info["tokens_used_today"] = k_info.get("tokens_used_today", 0) + int(tokens_used)
    limit = k_info.get("daily_limit", 20)
    k_info["requests_remaining"] = max(0, limit - k_info["requests_used_today"])
    k_info["last_used_timestamp"] = datetime.now(timezone.utc).isoformat()
    k_info["status"] = "ACTIVE"
    k_info["is_exhausted"] = (k_info["requests_remaining"] == 0)
    if k_info["is_exhausted"]:
        k_info["status"] = "EXHAUSTED"
    k_info["last_error"] = None

    save_quota_state(state)
    return state


def record_quota_exhausted(key, err_message, retry_seconds=None):
    """Markiert einen konkreten Key als erschöpft (HTTP 429) und berechnet den Reset-Zeitpunkt."""
    state = load_quota_state()
    keys_dict = state.get("keys", {})
    k_mask = mask_key(key)

    if k_mask in keys_dict:
        k_info = keys_dict[k_mask]
        k_info["status"] = "EXHAUSTED"
        k_info["is_exhausted"] = True
        limit = k_info.get("daily_limit", 20)
        k_info["requests_used_today"] = max(k_info.get("requests_used_today", 0), limit)
        k_info["requests_remaining"] = 0
        k_info["last_error"] = str(err_message)

        if retry_seconds and retry_seconds > 0:
            reset_dt = datetime.now(timezone.utc) + timedelta(seconds=retry_seconds)
            k_info["reset_time_utc"] = reset_dt.isoformat()

    save_quota_state(state)
    return state


def record_health_check(is_healthy: bool, message: str, tested_key_masked: str, active_tier: str = "Google Pro-Abo CLI"):
    """Speichert das Ergebnis des vorangehenden Health-Checks im Quota-State."""
    state = load_quota_state()
    state["health_check"] = {
        "is_healthy": is_healthy,
        "status": "HEALTHY" if is_healthy else "HIGH_DEMAND_FALLBACK",
        "message": message,
        "tested_key_masked": tested_key_masked,
        "active_tier": active_tier,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "routing_priority": "1. Multi-Key Pool (Free Tier) -> 2. Google Pro CLI (Failover) -> 3. Math-Core"
    }
    save_quota_state(state)


def record_pro_cli_request(tokens=0):
    """Zeichnet eine erfolgreiche Anfrage über das Google Pro-Abo (CLI) auf."""
    state = load_quota_state()
    pro = state.setdefault("pro_subscription", {
        "daily_budget": 50,
        "requests_used_today": 0,
        "requests_remaining": 50,
        "tokens_used_today": 0,
        "status": "ACTIVE",
        "last_used": None
    })
    pro["requests_used_today"] = pro.get("requests_used_today", 0) + 1
    budget = pro.get("daily_budget", 50)
    pro["requests_remaining"] = max(0, budget - pro["requests_used_today"])
    pro["tokens_used_today"] = pro.get("tokens_used_today", 0) + tokens
    pro["last_used"] = datetime.now(timezone.utc).isoformat()
    if pro["requests_remaining"] == 0:
        pro["status"] = "BUDGET_REACHED"
    else:
        pro["status"] = "ACTIVE"
    save_quota_state(state)
    return pro


def is_pro_quota_available():
    """Prüft, ob das Tages-Sicherheitsbudget (50 Anfragen) für das Pro-Abo noch verfügbar ist."""
    state = load_quota_state()
    pro = state.get("pro_subscription", {})
    budget = pro.get("daily_budget", 50)
    used = pro.get("requests_used_today", 0)
    return used < budget


def get_quota_summary_for_dashboard():
    """Bereitet aggregierte und detaillierte Kennzahlen für das Dashboard auf."""
    state = load_quota_state()
    keys_dict = state.get("keys", {})
    pro_data = state.get("pro_subscription", {
        "daily_budget": 50,
        "requests_used_today": 0,
        "requests_remaining": 50,
        "tokens_used_today": 0,
        "status": "ACTIVE",
        "last_used": None
    })

    total_limit = 0
    total_used = 0
    total_remaining = 0
    total_tokens = 0
    active_count = 0
    keys_detail = []

    for k_mask, info in keys_dict.items():
        limit = info.get("daily_limit", 20)
        used = info.get("requests_used_today", 0)
        rem = info.get("requests_remaining", max(0, limit - used))
        tokens = info.get("tokens_used_today", 0)
        status = info.get("status", "ACTIVE")
        is_exh = (status == "EXHAUSTED" or rem == 0)
        pct = round((used / limit * 100.0), 1) if limit > 0 else 100.0

        if not is_exh:
            active_count += 1

        total_limit += limit
        total_used += used
        total_remaining += rem
        total_tokens += tokens

        # Countdown für diesen Key
        reset_str = info.get("reset_time_utc")
        countdown = "in wenigen Std."
        if reset_str:
            try:
                reset_dt = datetime.fromisoformat(reset_str)
                diff = reset_dt - datetime.now(timezone.utc)
                if diff.total_seconds() > 0:
                    h = int(diff.total_seconds() // 3600)
                    m = int((diff.total_seconds() % 3600) // 60)
                    countdown = f"in {h}h {m}m"
                else:
                    countdown = "bereit"
            except Exception:
                pass

        keys_detail.append({
            "id": info.get("id"),
            "name": info.get("name", "Key"),
            "masked": info.get("masked", k_mask),
            "daily_limit": limit,
            "requests_used": used,
            "requests_remaining": rem,
            "percent_used": pct,
            "tokens_used": tokens,
            "status": "EXHAUSTED" if is_exh else "ACTIVE",
            "is_exhausted": is_exh,
            "reset_countdown": countdown,
            "last_error": info.get("last_error")
        })

    pool_pct = round((total_used / total_limit * 100.0), 1) if total_limit > 0 else 100.0
    pool_exhausted = (total_remaining == 0)
    current_active_key, current_active_masked = get_active_api_key()

    # Nächster globaler Reset
    reset_countdowns = [kd["reset_countdown"] for kd in keys_detail if kd["is_exhausted"]]
    pool_countdown = reset_countdowns[0] if reset_countdowns else "aktiv (24/7)"

    pro_budget = pro_data.get("daily_budget", 50)
    pro_used = pro_data.get("requests_used_today", 0)
    pro_rem = max(0, pro_budget - pro_used)
    pro_pct = round(pro_used / pro_budget * 100.0, 1) if pro_budget > 0 else 100.0

    return {
        "model": state.get("model", "gemini-3.8-flash"),
        "pool_mode": "MULTI_KEY_FAILOVER",
        "total_keys_count": len(keys_detail),
        "active_keys_count": active_count,
        "daily_limit": total_limit,
        "requests_used_today": total_used,
        "requests_remaining": total_remaining,
        "percent_used": pool_pct,
        "tokens_used_today": total_tokens,
        "status": "EXHAUSTED" if pool_exhausted else "ACTIVE",
        "is_exhausted": pool_exhausted,
        "reset_countdown": pool_countdown,
        "active_key_masked": current_active_masked,
        "keys_detail": keys_detail,
        "pro_subscription": {
            "enabled": True,
            "model": "gemini-3.8-flash-high (Google Pro CLI)",
            "daily_budget": pro_budget,
            "requests_used": pro_used,
            "requests_remaining": pro_rem,
            "percent_used": pro_pct,
            "tokens_used": pro_data.get("tokens_used_today", 0),
            "status": "ACTIVE" if pro_rem > 0 else "BUDGET_REACHED",
            "last_used": pro_data.get("last_used")
        },
        "health_check": state.get("health_check", {
            "is_healthy": False,
            "status": "PRO_ACTIVE",
            "message": "Vorab-Healthcheck aktiv: Free Keys unter Last -> Pro-Abo schützt zuverlässig",
            "tested_key_masked": current_active_masked,
            "active_tier": "Google Pro-Abo CLI",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "routing_priority": "1. Multi-Key Pool (Free Tier) -> 2. Google Pro CLI (Failover) -> 3. Math-Core"
        })
    }


if __name__ == "__main__":
    summary = get_quota_summary_for_dashboard()
    print("=" * 65)
    print(f"  GEMINI MULTI-KEY POOL STATUS ({summary['total_keys_count']}x API-KEYS INTEGRIERT)")
    print("=" * 65)
    print(f"Modell              : {summary['model']}")
    print(f"Aktiver Key         : {summary['active_key_masked']}")
    print(f"Keys im Pool        : {summary['active_keys_count']} / {summary['total_keys_count']} aktiv")
    print(f"Gesamt-Kontingent   : {summary['requests_used_today']} / {summary['daily_limit']} Anfragen ({summary['percent_used']}%)")
    print(f"Verbleibend         : {summary['requests_remaining']} Anfragen")
    print(f"Pool-Status         : {summary['status']}")
    print("-" * 65)
    for kd in summary["keys_detail"]:
        print(f"• {kd['name']} ({kd['masked']}): {kd['requests_used']}/{kd['daily_limit']} Req ({kd['percent_used']}%) | Status: {kd['status']} | Reset: {kd['reset_countdown']}")
    print("=" * 65)
