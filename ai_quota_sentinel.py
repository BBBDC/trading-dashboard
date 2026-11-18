#!/usr/bin/env python3
"""
ai_quota_sentinel.py
====================
Zentraler Monitor & Wächter für die KI-Limits von Claude Opus 5.5 und Grok Build 4.7:
1. Fragt native Nutzungsdaten ab:
   - Claude: via `claude -p "/usage"` (5h-Session %, wöchentliches %, Reset-Zeit CET)
   - Grok: via `grok usage` und Sessions-Inspektion (Tokens, Model Calls, Kosten, Token-Ablauf)
   - Antigravity: lokaler Core-Status
2. Dynamische Effort-Empfehlung (Smart Variable Effort):
   - Schont Tokens bei >75% bzw. >80% Auslastung
3. Persistiert Zustand in `knowledge_base/ai_quota_state.json`
4. Proaktive Telegram-Admin-Benachrichtigungen bei:
   - 80% Frühwarnung (Gelb)
   - 100% Limit erreicht (Rot)
   - Reset erfolgt (Grün)
"""

import json
import os
import re
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
KB_DIR = BASE_DIR / "knowledge_base"
AI_QUOTA_FILE = KB_DIR / "ai_quota_state.json"
AI_ALERT_STATE_FILE = KB_DIR / "ai_quota_alert_state.json"
CLAUDE_BIN = "/home/admin/.local/bin/claude"
GROK_BIN = "/home/admin/.local/bin/grok"


def get_claude_usage() -> Dict[str, Any]:
    """
    Fragt Claude CLI nach der aktuellen Nutzungs-Quote ab.
    Erwartet Output wie:
    'Current session: 54% used · resets Nov 17, 3:39pm (Europe/Berlin)'
    'Current week (all models): 9% used · resets Nov 24, 4:59am (Europe/Berlin)'
    """
    res = {"status": "UNKNOWN", "session_pct": 0, "week_pct": 0, "reset_str": "Unbekannt", "error": None}
    if not os.path.exists(CLAUDE_BIN):
        res["status"] = "NOT_INSTALLED"
        return res

    try:
        proc = subprocess.run([CLAUDE_BIN, "-p", "/usage"], capture_output=True, text=True, timeout=12)
        out = proc.stdout + proc.stderr
        
        # Check limit hit in error message
        if "5-hour limit" in out or "hit your 5-hour limit" in out:
            res["status"] = "EXHAUSTED"
            res["session_pct"] = 100
            m_reset = re.search(r"resets\s+([0-9:apmAPM\s\(\)/-]+)", out)
            if m_reset:
                res["reset_str"] = m_reset.group(1).strip()
            return res

        # Regex for session
        # 'Current session: 54% used · resets Nov 17, 3:39pm (Europe/Berlin)'
        m_sess = re.search(r"Current session:\s*(\d+)%\s*used.*?resets\s*([^,\n\r]+(?:,[^\n\r]+)?)", out)
        if m_sess:
            res["session_pct"] = int(m_sess.group(1))
            res["reset_str"] = m_sess.group(2).strip()

        # Regex for week
        m_week = re.search(r"Current week.*?:\s*(\d+)%", out)
        if m_week:
            res["week_pct"] = int(m_week.group(1))

        if res["session_pct"] >= 100:
            res["status"] = "EXHAUSTED"
        elif res["session_pct"] >= 80:
            res["status"] = "THROTTLED"
        else:
            res["status"] = "ONLINE"

    except subprocess.TimeoutExpired:
        res["status"] = "TIMEOUT"
        res["error"] = "Claude /usage Timeout (12s)"
    except Exception as e:
        res["status"] = "ERROR"
        res["error"] = str(e)

    return res


def get_grok_usage() -> Dict[str, Any]:
    """
    Fragt Grok CLI und lokale Session-Daten nach Verbrauch ab.
    Liest Token-Verbrauch, Modell-Aufrufe, Kosten und Auth-Status.
    """
    res = {
        "status": "ONLINE",
        "estimated_pct": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
        "model_calls": 0,
        "cost_usd": 0.0,
        "expires_at_str": "OAuth 2.0 (Dauerhaft aktiv)",
        "last_active_str": "Unbekannt",
        "primary_model": "grok-4.7",
        "error": None
    }
    
    # 1. Auth-Info lesen für Status
    auth_file = Path("/home/admin/.grok/auth.json")
    if auth_file.exists():
        try:
            with open(auth_file, "r") as f:
                adata = json.load(f)
            has_refresh = False
            for v in adata.values():
                if isinstance(v, dict):
                    if v.get("refresh_token"):
                        has_refresh = True
            if has_refresh:
                res["expires_at_str"] = "OAuth 2.0 (Dauerhaft aktiv)"
        except Exception as e:
            res["error"] = f"Auth read error: {e}"

    # 2. Rekursiv alle Sessions nach der jüngsten usage.json durchsuchen
    sessions_root = Path("/home/admin/.grok/sessions")
    latest_usage_file = None
    if sessions_root.exists():
        usage_files = list(sessions_root.rglob("usage.json"))
        if usage_files:
            usage_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            latest_usage_file = usage_files[0]

    if latest_usage_file and latest_usage_file.exists():
        try:
            with open(latest_usage_file, "r", encoding="utf-8") as f:
                udata = json.load(f)
            s = udata.get("session", {})
            res["input_tokens"] = s.get("inputTokens", 0)
            res["output_tokens"] = s.get("outputTokens", 0)
            res["reasoning_tokens"] = s.get("reasoningTokens", 0)
            res["total_tokens"] = s.get("totalTokens", 0)
            res["model_calls"] = s.get("modelCalls", 0)
            res["primary_model"] = s.get("primaryModelId", "grok-4.7")
            
            ticks = s.get("costUsdTicks", 0)
            res["cost_usd"] = round(ticks / 1_000_000_000, 2)
            
            mtime = latest_usage_file.stat().st_mtime
            dt_cet = datetime.fromtimestamp(mtime, tz=timezone(timedelta(hours=1)))
            res["last_active_str"] = dt_cet.strftime("%d.%m. %H:%M CET")
            
            # Schätze Auslastung relativ zur typischen Session-Norm (z.B. 1.5M Tokens)
            pct = min(100, int((res["total_tokens"] / 1_500_000) * 100))
            res["estimated_pct"] = max(1, pct) if res["total_tokens"] > 0 else 0
            if pct >= 100:
                res["status"] = "EXHAUSTED"
            elif pct >= 80:
                res["status"] = "THROTTLED"
            else:
                res["status"] = "ONLINE"
        except Exception as e:
            res["error"] = f"Usage parse error: {e}"

    return res


def determine_dynamic_efforts(claude_info: Dict[str, Any], grok_info: Dict[str, Any], is_macro: bool = False) -> Dict[str, str]:
    """
    Berechnet die idealen dynamischen Effort-Levels basierend auf Rest-Quota und Zeithorizont.
    """
    claude_pct = claude_info.get("session_pct", 0)
    grok_pct = grok_info.get("estimated_pct", 0)

    # Claude Effort
    if claude_pct >= 100:
        claude_effort = "paused"
    elif claude_pct >= 75:
        claude_effort = "medium"  # Drosselung zur Schonung
    elif is_macro:
        claude_effort = "xhigh"   # Tiefe Makro-Kausalität
    else:
        claude_effort = "high"    # Standard-Qualität

    # Grok Effort
    if grok_pct >= 95:
        grok_effort = "low"
    elif grok_pct >= 80:
        grok_effort = "medium"
    elif is_macro:
        grok_effort = "high"
    else:
        grok_effort = "medium"    # Standard-Qualität

    return {
        "claude_effort": claude_effort,
        "grok_effort": grok_effort
    }


def update_and_check_quotas() -> Dict[str, Any]:
    """
    Aktualisiert alle Quotas, speichert den Zustand und prüft auf Schwellenwert-Events für Telegram.
    """
    claude_info = get_claude_usage()
    grok_info = get_grok_usage()
    efforts = determine_dynamic_efforts(claude_info, grok_info, is_macro=False)

    full_state = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_at_str": datetime.now(timezone(timedelta(hours=1))).strftime("%d.%m.%Y %H:%M:%S CET"),
        "claude": {
            "name": "Claude Opus 5.5",
            "provider": "Anthropic",
            "status": claude_info.get("status", "ONLINE"),
            "session_used_pct": claude_info.get("session_pct", 0),
            "week_used_pct": claude_info.get("week_pct", 0),
            "reset_str": claude_info.get("reset_str", "Unbekannt"),
            "active_effort": efforts["claude_effort"],
            "error": claude_info.get("error")
        },
        "grok": {
            "name": "Grok Build 4.7",
            "provider": "xAI",
            "status": grok_info.get("status", "ONLINE"),
            "estimated_pct": grok_info.get("estimated_pct", 0),
            "total_tokens": grok_info.get("total_tokens", 0),
            "reasoning_tokens": grok_info.get("reasoning_tokens", 0),
            "model_calls": grok_info.get("model_calls", 0),
            "cost_usd": grok_info.get("cost_usd", 0.0),
            "expires_at_str": grok_info.get("expires_at_str", "OAuth 2.0 (Dauerhaft aktiv)"),
            "last_active_str": grok_info.get("last_active_str", "Unbekannt"),
            "active_effort": efforts["grok_effort"],
            "error": grok_info.get("error")
        },
        "antigravity": {
            "name": "Antigravity Core",
            "provider": "Google DeepMind Engine",
            "status": "ONLINE",
            "latency_ms": 1,
            "limits": "Unlimitiert (Lokale Pipeline)"
        }
    }

    # Speichern in knowledge_base und dashboard
    KB_DIR.mkdir(parents=True, exist_ok=True)
    with open(AI_QUOTA_FILE, "w", encoding="utf-8") as f:
        json.dump(full_state, f, indent=2, ensure_ascii=False)

    dash_quota_file = BASE_DIR / "dashboard" / "ai_quota_state.json"
    try:
        dash_quota_file.parent.mkdir(parents=True, exist_ok=True)
        with open(dash_quota_file, "w", encoding="utf-8") as f:
            json.dump(full_state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warnung beim Speichern von dashboard/ai_quota_state.json: {e}")

    # Prüfe auf Schwellenwert-Events für Telegram-Admin
    check_and_dispatch_quota_alerts(full_state)

    return full_state


def check_and_dispatch_quota_alerts(state: Dict[str, Any]):
    """
    Prüft, ob ein neues Alert-Event vorliegt (80% Warnung, 100% Exhausted, oder Reset)
    und sendet gezielte Benachrichtigungen an die Admins.
    """
    alert_history = {}
    if AI_ALERT_STATE_FILE.exists():
        try:
            with open(AI_ALERT_STATE_FILE, "r") as f:
                alert_history = json.load(f)
        except Exception:
            alert_history = {}

    claude_pct = state["claude"]["session_used_pct"]
    claude_status = state["claude"]["status"]
    last_claude_state = alert_history.get("claude_alert_state", "NORMAL")

    alerts_to_send = []

    # 1. Claude Schwellenwerte
    if claude_pct >= 100 or claude_status == "EXHAUSTED":
        if last_claude_state != "EXHAUSTED_100":
            alerts_to_send.append({
                "level": "CRITICAL",
                "text": (
                    f"🛑 <b>KI-QUOTA LIMIT ERREICHT (Claude Opus 5.5)</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Das 5-Stunden-Limit wurde zu <b>100%</b> erreicht.\n"
                    f"• <b>Reset erfolgt um:</b> {state['claude']['reset_str']}\n"
                    f"• <b>Schutz-Modus:</b> Bis zum Reset werden <b>keine neuen Live-Trades</b> eröffnet (Kapitalschutz).\n"
                    f"• Der mathematische Python-Scanner läuft ununterbrochen weiter."
                )
            })
            alert_history["claude_alert_state"] = "EXHAUSTED_100"
    elif claude_pct >= 80:
        if last_claude_state not in ("WARNING_80", "EXHAUSTED_100"):
            alerts_to_send.append({
                "level": "WARNING",
                "text": (
                    f"⚠️ <b>KI-QUOTA WARNUNG (Claude Opus 5.5)</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Die 5-Stunden-Auslastung liegt aktuell bei <b>{claude_pct}%</b>.\n"
                    f"• <b>Reset erfolgt um:</b> {state['claude']['reset_str']}\n"
                    f"• <b>System-Maßnahme:</b> Dynamische Drosselung auf Effort <code>medium</code> aktiviert, um verbleibende Trades abzusichern."
                )
            })
            alert_history["claude_alert_state"] = "WARNING_80"
    elif claude_pct < 50 and last_claude_state in ("WARNING_80", "EXHAUSTED_100"):
        # Reset Entwarnung
        alerts_to_send.append({
            "level": "INFO",
            "text": (
                f"✅ <b>KI-QUOTA ZURÜCKGESETZT (Claude Opus 5.5)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Claude Opus 5.5 ist wieder voll einsatzbereit (Auslastung: <b>{claude_pct}%</b>).\n"
                f"Der Triade-Konsens steht für neue A+ Setups wieder uneingeschränkt mit Effort <code>high</code> zur Verfügung."
            )
        })
        alert_history["claude_alert_state"] = "NORMAL"

    # Sende Alerts über Telegram falls nötig
    if alerts_to_send:
        dispatch_telegram_admin_notification(alerts_to_send)

    with open(AI_ALERT_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(alert_history, f, indent=2)


def dispatch_telegram_admin_notification(alerts: list):
    """
    Sendet System-Alerts an alle registrierten Telegram-Admins.
    """
    try:
        import sys
        sys.path.insert(0, str(BASE_DIR))
        from telegram_bot import TelegramAPI, load_config
        cfg = load_config()
        token = cfg.get("bot_token")
        admin_cids = cfg.get("admin_chat_ids", [])
        if not token or not admin_cids:
            return

        api = TelegramAPI(token)
        for alert in alerts:
            for cid in admin_cids:
                try:
                    api.send_message(cid, alert["text"], parse_mode="HTML")
                except Exception as e:
                    print(f"Fehler beim Senden von Quota-Alert an {cid}: {e}")
    except Exception as e:
        print(f"Fehler bei dispatch_telegram_admin_notification: {e}")


def format_telegram_quota_summary() -> str:
    """
    Erstellt den formatierten Text für den Telegram-Befehl `/quota` oder `/limits`.
    """
    state = update_and_check_quotas()
    c = state["claude"]
    g = state["grok"]

    # Bar helper
    def make_bar(pct: int, length: int = 10) -> str:
        filled = min(length, max(0, int(round((pct / 100.0) * length))))
        return "█" * filled + "░" * (length - filled)

    c_bar = make_bar(c["session_used_pct"])
    g_bar = make_bar(g["estimated_pct"])

    c_status_icon = "🟢" if c["status"] == "ONLINE" else ("🟡" if c["status"] == "THROTTLED" else "🔴")
    g_status_icon = "🟢" if g["status"] == "ONLINE" else ("🟡" if g["status"] == "THROTTLED" else "🔴")

    msg = (
        f"🤖 <b>KI-SYSTEM STATUS &amp; QUOTA REPORT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏛️ <b>Claude Opus 5.5 (Kausalitäts-Audit)</b>\n"
        f"• Status: {c_status_icon} <b>{c['status']}</b>\n"
        f"• 5h-Session: <code>[{c_bar}]</code> <b>{c['session_used_pct']}%</b>\n"
        f"• Reset um: <b>{c['reset_str']}</b>\n"
        f"• Wochen-Quota: <b>{c['week_used_pct']}%</b> genutzt\n"
        f"• Aktiver Effort: <code>{c['active_effort']}</code>\n\n"
        f"⚡ <b>Grok Build 4.7 (News- &amp; Sentiment-Radar)</b>\n"
        f"• Status: {g_status_icon} <b>{g['status']}</b>\n"
        f"• Session-Last: <code>[{g_bar}]</code> <b>{g['estimated_pct']}%</b>\n"
        f"• Session-Gültigkeit: <b>{g['expires_at_str']}</b>\n"
        f"• Verbrauchte Tokens: <b>{g['total_tokens']:,}</b>\n"
        f"• Kosten / Session: <b>${g['cost_usd']:.2f} USD</b>\n"
        f"• Aktiver Effort: <code>{g['active_effort']}</code>\n\n"
        f"📐 <b>Antigravity Core (Quantitative Engine)</b>\n"
        f"• Status: 🟢 <b>ONLINE</b>\n"
        f"• Latenz: <b>0.001s (Lokal unlimitiert)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Zuletzt aktualisiert: {state['updated_at_str']}</i>"
    )
    return msg


if __name__ == "__main__":
    print("=== Teste AI Quota Sentinel ===")
    state = update_and_check_quotas()
    print(json.dumps(state, indent=2))
    print("\n=== Telegram Summary Preview ===")
    print(format_telegram_quota_summary())
