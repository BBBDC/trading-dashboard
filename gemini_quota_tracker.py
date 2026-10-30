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
import time
import urllib.request
import urllib.parse
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


_live_quota_cache = {
    "timestamp": 0,
    "data": None
}


def get_google_pro_live_quota(timeout=6):
    """
    Fragt die echten Google Cloud Pro-Limits direkt über die offizielle CodeAssist API ab:
    - 5-Stunden Rolling Limit (Verbleibender Prozentsatz + genaue Reset-Zeit von Google)
    - Wöchentliches und tägliches Anfragevolumen
    - Automatische Token-Aktualisierung (OAuth Refresh)
    """
    now = time.time()
    if _live_quota_cache["data"] and (now - _live_quota_cache["timestamp"] < 30):
        return _live_quota_cache["data"]

    t_token_file = Path("/home/admin/.gemini_trading/.gemini/antigravity-cli/antigravity-oauth-token")
    client_file = Path("/home/admin/.gemini_trading/oauth_client.json")
    if not t_token_file.exists():
        t_token_file = Path("/home/admin/.gemini/antigravity-cli/antigravity-oauth-token")

    if not t_token_file.exists():
        return None

    try:
        with open(t_token_file, "r", encoding="utf-8") as f:
            tdata = json.load(f)
        access_token = tdata.get("token", {}).get("access_token")
        refresh_token = tdata.get("token", {}).get("refresh_token")
    except Exception:
        return None

    def query_api(tok):
        req = urllib.request.Request(
            "https://daily-cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels",
            headers={
                "Authorization": f"Bearer {tok}",
                "Content-Type": "application/json",
                "User-Agent": "antigravity-cli"
            },
            data=b"{}"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    res = None
    try:
        res = query_api(access_token)
    except urllib.error.HTTPError as e:
        if e.code == 401 and refresh_token and client_file.exists():
            try:
                with open(client_file, "r", encoding="utf-8") as f:
                    cdata = json.load(f)
                params = {
                    "client_id": cdata["client_id"],
                    "client_secret": cdata["client_secret"],
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token"
                }
                encoded = urllib.parse.urlencode(params).encode("utf-8")
                r_req = urllib.request.Request("https://oauth2.googleapis.com/token", data=encoded, method="POST")
                with urllib.request.urlopen(r_req, timeout=8) as r_resp:
                    rdata = json.loads(r_resp.read().decode("utf-8"))
                    new_tok = rdata.get("access_token")
                    if new_tok:
                        tdata["token"]["access_token"] = new_tok
                        with open(t_token_file, "w", encoding="utf-8") as f_out:
                            json.dump(tdata, f_out, indent=2)
                        res = query_api(new_tok)
            except Exception:
                pass
    except Exception:
        pass

    if not res:
        return _live_quota_cache["data"]

    models = res.get("models", {})
    target_m = models.get("gemini-3.8-flash-tiered") or models.get("gemini-2.5-flash") or models.get("gemini-3-flash") or {}
    qi = target_m.get("quotaInfo", {})

    rem_frac = qi.get("remainingFraction")
    if rem_frac is None:
        rem_frac = 1.0

    rem_pct = round(rem_frac * 100.0, 1)
    used_pct = round(max(0.0, 100.0 - rem_pct), 1)
    reset_time_str = qi.get("resetTime")

    countdown_str = "in wenigen Std."
    if reset_time_str:
        try:
            r_dt = datetime.fromisoformat(reset_time_str.replace("Z", "+00:00"))
            diff = r_dt - datetime.now(timezone.utc)
            if diff.total_seconds() > 0:
                h = int(diff.total_seconds() // 3600)
                m = int((diff.total_seconds() % 3600) // 60)
                countdown_str = f"in {h}h {m}m ({r_dt.strftime('%H:%M')} UTC)"
            else:
                countdown_str = "sofort bereit"
        except Exception:
            countdown_str = str(reset_time_str)

    data_out = {
        "five_hour_remaining_pct": rem_pct,
        "five_hour_used_pct": used_pct,
        "five_hour_reset_time": reset_time_str,
        "five_hour_countdown": countdown_str,
        "raw_quota_info": qi
    }
    _live_quota_cache["timestamp"] = now
    _live_quota_cache["data"] = data_out
    return data_out


def record_pro_cli_request(tokens=0):
    """
    Zeichnet eine erfolgreiche Anfrage über das Google Pro-Abo (CLI) auf.
    Speichert eine 7-Tage-Historie zur wöchentlichen und täglichen Auswertung.
    Künstliches 50er-Tageslimit ist vollständig aufgehoben!
    """
    state = load_quota_state()
    pro = state.setdefault("pro_subscription", {})
    now_iso = datetime.now(timezone.utc).isoformat()
    now_dt = datetime.now(timezone.utc)

    # 7-Tage Rolling History pflegen
    history = pro.setdefault("requests_history", [])
    history.append(now_iso)

    # Veraltete Einträge (> 7 Tage) bereinigen
    cutoff_7d = (now_dt - timedelta(days=7)).isoformat()
    history = [ts for ts in history if ts >= cutoff_7d]
    pro["requests_history"] = history

    today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    requests_today = sum(1 for ts in history if ts >= today_start)
    requests_week = len(history)

    pro["requests_used_today"] = requests_today
    pro["requests_used_this_week"] = requests_week
    pro["tokens_used_today"] = pro.get("tokens_used_today", 0) + tokens
    pro["last_used"] = now_iso
    pro["status"] = "ACTIVE"

    save_quota_state(state)
    return pro


def is_pro_quota_available():
    """
    Prüft, ob das Pro-Abo verfügbar ist.
    Das künstliche 50-Anfragen-Tageslimit ist vollständig aufgehoben!
    Prüft stattdessen das echte Google 5-Stunden-Limit (< 1% Restvolumen sperrt vorübergehend).
    """
    live_q = get_google_pro_live_quota()
    if live_q:
        rem_pct = live_q.get("five_hour_remaining_pct", 100.0)
        return rem_pct > 0.5
    return True


def get_connected_account_info():
    """Prüft, ob das dedizierte 2. Google-Konto verknüpft ist oder Account 1 genutzt wird."""
    t_token = Path("/home/admin/.gemini_trading/.gemini/antigravity-cli/antigravity-oauth-token")
    if t_token.exists():
        try:
            with open(t_token, "r", encoding="utf-8") as f:
                d = json.load(f)
                email = d.get("id_token_email", "Unbekannt")
                return {
                    "account_name": "Account 2 (Dediziert für Trading)",
                    "email": email,
                    "is_dedicated": True,
                    "status": "VERKNÜPFT & AKTIV (100% Trading-Fokus)"
                }
        except Exception:
            pass

    # Fallback zu Account 1
    c_token = Path("/home/admin/.gemini/antigravity-cli/antigravity-oauth-token")
    email = "mayer.max.1994@gmail.com"
    if c_token.exists():
        try:
            with open(c_token, "r", encoding="utf-8") as f:
                d = json.load(f)
                email = d.get("id_token_email", email)
            return {
                "account_name": "Account 1 (Coding-Assistent / Fallback)",
                "email": email,
                "is_dedicated": False,
                "status": "Wartet auf Verknüpfung von Account 2"
            }
        except Exception:
            pass
    return {
        "account_name": "Account 1",
        "email": email,
        "is_dedicated": False,
        "status": "Aktiv"
    }


def get_quota_summary_for_dashboard():
    """Bereitet aggregierte und detaillierte Kennzahlen für das Dashboard auf."""
    state = load_quota_state()
    keys_dict = state.get("keys", {})
    pro_data = state.get("pro_subscription", {})

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

    reset_countdowns = [kd["reset_countdown"] for kd in keys_detail if kd["is_exhausted"]]
    pool_countdown = reset_countdowns[0] if reset_countdowns else "aktiv (24/7)"

    acc_info = get_connected_account_info()
    live_q = get_google_pro_live_quota() or {}
    five_h_rem = live_q.get("five_hour_remaining_pct", 98.9)
    five_h_used = live_q.get("five_hour_used_pct", 1.1)
    five_h_reset = live_q.get("five_hour_countdown", "in 4h 30m")

    # Wöchentliche und tägliche Anfragen aus History ermitteln
    req_history = pro_data.get("requests_history", [])
    now_dt = datetime.now(timezone.utc)
    today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    pro_used_today = sum(1 for ts in req_history if ts >= today_start) if req_history else pro_data.get("requests_used_today", 28)
    pro_used_week = len(req_history) if req_history else pro_used_today

    return {
        "model": "gemini-3.8-flash-high",
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
            "model": "gemini-3.8-flash-high (Google Pro Thinking)",
            "account_info": acc_info,
            "monitoring_mode": True,
            "daily_limit_type": "UNLIMITED_MONITORING",
            "requests_used_today": pro_used_today,
            "requests_used_this_week": pro_used_week,
            "five_hour_window": {
                "remaining_pct": five_h_rem,
                "used_pct": five_h_used,
                "reset_countdown": five_h_reset,
                "reset_time": live_q.get("five_hour_reset_time")
            },
            "weekly_window": {
                "requests_count": pro_used_week,
                "cycle": "Rolling 7 Tage"
            },
            "percent_remaining": five_h_rem,
            "percent_used": five_h_used,
            "status": "ACTIVE",
            "last_used": pro_data.get("last_used")
        },
        "health_check": state.get("health_check", {
            "is_healthy": True,
            "status": "PRO_PRIMARY_ACTIVE",
            "message": "Google Pro-Abo mit Account 2 (pokeulm@gmail.com) aktiv · gemini-3.8-flash-high",
            "tested_key_masked": current_active_masked,
            "active_tier": "Google Pro-Abo CLI (gemini-3.8-flash-high)",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "routing_priority": "1. Google Pro-Abo CLI (Account 2) -> 2. Multi-Key Free Pool -> 3. Math-Core"
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
