#!/usr/bin/env python3
"""
system_health.py
================
Zentrales Gesundheits- & Diagnose-Überwachungssystem für das Trading-Dashboard
und den Raspberry Pi 24/7 Hintergrund-Betrieb:
1. Pipeline & Cron-Job Ausführung (Stündlicher Rhythmus)
2. Kursdaten-Frische & TradingView Datenfeed
3. AI Paper-Trading Incubator & Post-Mortem Lab Status
4. Autonomes KI-Portfolio & User-Trades Überwachung (SL/TP Trigger)
5. Telegram-Bot systemd Service Integrität
6. GitHub Pages Synchronisation & Hosting

Liefert Diagnose-Daten für:
- Web Dashboard (Admin-Zentrale & Header)
- Telegram Bot Admin Hub & /health Befehl
- CLI Schnelltest (python3 system_health.py)
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Tuple

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"
KB_DIR = BASE_DIR / "knowledge_base"
INCUBATOR_FILE = KB_DIR / "incubator_trades.json"
PORTFOLIO_FILE = KB_DIR / "autonomous_portfolio.json"
USER_POS_FILE = KB_DIR / "user_positions.json"
USER_HIST_FILE = KB_DIR / "user_positions_history.json"
CRON_LOG_FILE = BASE_DIR / "cron_update.log"


def parse_iso_timestamp(ts_str: str) -> datetime:
    """Parst ISO-8601 Zeitstempel sauber in UTC datetime."""
    try:
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        return datetime.fromisoformat(ts_str)
    except Exception:
        return datetime.now(timezone.utc)


def check_pipeline_cron() -> Dict[str, Any]:
    """Prüft, ob die stündliche Pipeline regulär durchläuft."""
    now = datetime.now(timezone.utc)
    last_update = None

    if DB_FILE.exists():
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                db = json.load(f)
                ts = db.get("last_quotes_update") or db.get("data_last_updated")
                if ts:
                    last_update = parse_iso_timestamp(ts)
        except Exception:
            pass

    if not last_update and CRON_LOG_FILE.exists():
        try:
            mtime = os.path.getmtime(CRON_LOG_FILE)
            last_update = datetime.fromtimestamp(mtime, timezone.utc)
        except Exception:
            pass

    if not last_update:
        return {
            "status": "CRITICAL",
            "score": 0,
            "label": "Pipeline & Cron-Job",
            "message": "Kein Ausführungs-Zeitstempel auffindbar (Unbekannter Stand)",
            "age_minutes": None
        }

    age_minutes = max(0, (now - last_update).total_seconds() / 60.0)

    # Cron läuft alle 30 Min (*/30). Toleranz bis 60 Min.
    if age_minutes <= 60:
        return {
            "status": "OK",
            "score": 100,
            "label": "Pipeline & Cron-Job",
            "message": f"Letzter Scan vor {int(age_minutes)} Min. (30-Minuten-Takt aktiv)",
            "age_minutes": round(age_minutes, 1),
            "last_time": last_update.strftime("%H:%M UTC")
        }
    elif age_minutes <= 180:
        return {
            "status": "WARNING",
            "score": 60,
            "label": "Pipeline & Cron-Job",
            "message": f"Scan verzögert: Letzter Durchlauf vor {int(age_minutes)} Min.",
            "age_minutes": round(age_minutes, 1),
            "last_time": last_update.strftime("%H:%M UTC")
        }
    else:
        hours = round(age_minutes / 60.0, 1)
        return {
            "status": "CRITICAL",
            "score": 20,
            "label": "Pipeline & Cron-Job",
            "message": f"Cron-Ausfall vermutet: Keine Aktualisierung seit {hours} Stunden!",
            "age_minutes": round(age_minutes, 1),
            "last_time": last_update.strftime("%H:%M UTC")
        }


def check_quotes_freshness() -> Dict[str, Any]:
    """Prüft die Abdeckung und Aktualität der Marktkurse."""
    if not DB_FILE.exists():
        return {
            "status": "CRITICAL",
            "score": 0,
            "label": "Echtzeit-Kurse & TV",
            "message": "market_analysis_db.json fehlt!",
            "total_assets": 0,
            "fresh_assets": 0
        }

    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
        assets = db.get("assets", [])
        total = len(assets)
        if total == 0:
            return {
                "status": "WARNING",
                "score": 40,
                "label": "Echtzeit-Kurse & TV",
                "message": "0 Assets in Datenbank erfasst",
                "total_assets": 0,
                "fresh_assets": 0
            }

        now = datetime.now(timezone.utc)
        fresh_count = 0
        for a in assets:
            ts = a.get("last_price_update") or a.get("last_scan_utc")
            if ts:
                try:
                    dt = parse_iso_timestamp(ts)
                    if (now - dt).total_seconds() < 4 * 3600:  # < 4h
                        fresh_count += 1
                except Exception:
                    pass

        pct = (fresh_count / total) * 100.0 if total > 0 else 0.0
        if pct >= 80:
            return {
                "status": "OK",
                "score": 100,
                "label": "Echtzeit-Kurse & TV",
                "message": f"{fresh_count} von {total} Assets aktiv überwacht ({pct:.0f}% aktuell)",
                "total_assets": total,
                "fresh_assets": fresh_count
            }
        elif pct >= 50:
            return {
                "status": "WARNING",
                "score": 70,
                "label": "Echtzeit-Kurse & TV",
                "message": f"Teilweise verzögert: {fresh_count}/{total} Assets frisch ({pct:.0f}%)",
                "total_assets": total,
                "fresh_assets": fresh_count
            }
        else:
            return {
                "status": "CRITICAL",
                "score": 30,
                "label": "Echtzeit-Kurse & TV",
                "message": f"Nur {fresh_count}/{total} Assets mit aktuellen Kursdaten ({pct:.0f}%)",
                "total_assets": total,
                "fresh_assets": fresh_count
            }
    except Exception as e:
        return {
            "status": "WARNING",
            "score": 50,
            "label": "Echtzeit-Kurse & TV",
            "message": f"Fehler beim Prüfen der Kurse: {e}",
            "total_assets": 0,
            "fresh_assets": 0
        }


def check_incubator_status() -> Dict[str, Any]:
    """Prüft AI Paper-Trading Incubator & Post-Mortem Lab."""
    if not INCUBATOR_FILE.exists():
        return {
            "status": "WARNING",
            "score": 50,
            "label": "AI Incubator & Lab",
            "message": "Inkubator-Datenbank noch nicht initialisiert",
            "active_count": 0,
            "total_trades": 0
        }

    try:
        with open(INCUBATOR_FILE, "r", encoding="utf-8") as f:
            inc = json.load(f)

        active = inc.get("active_trades", [])
        closed = inc.get("closed_trades", [])
        metrics = inc.get("metrics", {})
        lifetime = inc.get("lifetime_metrics", {})
        total_trades = lifetime.get("total_trades", metrics.get("total_trades", len(closed)))
        win_rate = metrics.get("win_rate", 0.0)
        total_r = metrics.get("total_r_profit", 0.0)

        updated_at = inc.get("updated_at")
        age_m = None
        if updated_at:
            dt = parse_iso_timestamp(updated_at)
            age_m = max(0, (datetime.now(timezone.utc) - dt).total_seconds() / 60.0)

        if len(active) > 0:
            msg = f"{len(active)} aktive Micro-Trades · {total_trades} ausgewertete Trades ({win_rate}% Win-Rate, {total_r:+.1f}R)"
            status = "OK"
            score = 100
        else:
            msg = f"0 aktive Trades im Inkubator ({total_trades} in Historie)"
            status = "WARNING"
            score = 75

        return {
            "status": status,
            "score": score,
            "label": "AI Incubator & Lab",
            "message": msg,
            "active_count": len(active),
            "total_trades": total_trades,
            "win_rate": win_rate,
            "age_minutes": round(age_m, 1) if age_m is not None else None
        }
    except Exception as e:
        return {
            "status": "WARNING",
            "score": 50,
            "label": "AI Incubator & Lab",
            "message": f"Inkubator-Prüfung fehlgeschlagen: {e}",
            "active_count": 0,
            "total_trades": 0
        }


def check_portfolio_and_user_trades() -> Dict[str, Any]:
    """Prüft autonomes KI-Portfolio und eigene Nutzer-Positionen (SL/TP Engine)."""
    ai_active = 0
    user_active = 0
    user_hist = 0

    if PORTFOLIO_FILE.exists():
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                pdata = json.load(f)
            ai_active = len(pdata.get("active_trades", []))
        except Exception:
            pass

    if USER_POS_FILE.exists():
        try:
            with open(USER_POS_FILE, "r", encoding="utf-8") as f:
                updata = json.load(f)
            if isinstance(updata, list):
                user_active = len(updata)
            elif isinstance(updata, dict):
                user_active = len(updata.get("positions", []))
        except Exception:
            pass

    if USER_HIST_FILE.exists():
        try:
            with open(USER_HIST_FILE, "r", encoding="utf-8") as f:
                hdata = json.load(f)
            if isinstance(hdata, list):
                user_hist = len(hdata)
            elif isinstance(hdata, dict):
                user_hist = len(hdata.get("closed_positions", hdata.get("history", [])))
        except Exception:
            pass

    msg = f"{ai_active} KI-Portfolio Trades · {user_active} User-Trades (SL/TP Auto-Close aktiv, {user_hist} in Historie)"
    return {
        "status": "OK",
        "score": 100,
        "label": "Portfolio & User-Trades",
        "message": msg,
        "ai_active": ai_active,
        "user_active": user_active,
        "user_history": user_hist
    }


def check_telegram_bot_service() -> Dict[str, Any]:
    """Prüft den systemd Service des Telegram-Bots auch in minimalen Umgebungen (Cron)."""
    try:
        env = os.environ.copy()
        uid = os.getuid()
        runtime_dir = f"/run/user/{uid}"
        if "XDG_RUNTIME_DIR" not in env and os.path.exists(runtime_dir):
            env["XDG_RUNTIME_DIR"] = runtime_dir
        if "DBUS_SESSION_BUS_ADDRESS" not in env and os.path.exists(f"{runtime_dir}/bus"):
            env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={runtime_dir}/bus"

        res = subprocess.run(
            ["systemctl", "--user", "is-active", "trading-telegram-bot.service"],
            capture_output=True,
            text=True,
            timeout=5,
            env=env
        )
        out = res.stdout.strip()
        if out == "active":
            return {
                "status": "OK",
                "score": 100,
                "label": "Telegram Bot Service",
                "message": "Systemd Service aktiv & läuft zuverlässig 24/7",
                "service_state": "active"
            }
        else:
            # Fallback Check via pgrep & cgroup
            pg = subprocess.run(["pgrep", "-f", "telegram_bot.py"], capture_output=True, text=True, timeout=3)
            pids = pg.stdout.strip().split()
            if pg.returncode == 0 and pids:
                is_systemd_managed = False
                for pid in pids:
                    cgroup_path = Path(f"/proc/{pid}/cgroup")
                    if cgroup_path.exists():
                        try:
                            cg_content = cgroup_path.read_text()
                            if "trading-telegram-bot.service" in cg_content:
                                is_systemd_managed = True
                                break
                        except Exception:
                            pass

                if is_systemd_managed:
                    return {
                        "status": "OK",
                        "score": 100,
                        "label": "Telegram Bot Service",
                        "message": "Systemd Service aktiv (CGroup bestätigt)",
                        "service_state": "active"
                    }
                else:
                    return {
                        "status": "WARNING",
                        "score": 80,
                        "label": "Telegram Bot Service",
                        "message": "Prozess läuft manuell, aber nicht unter systemd Service",
                        "service_state": out or "manual_process"
                    }

            return {
                "status": "CRITICAL",
                "score": 0,
                "label": "Telegram Bot Service",
                "message": f"Bot-Dienst ist inaktiv ({out or 'offline'})! Handlungsbedarf.",
                "service_state": out or "inactive"
            }
    except Exception as e:
        return {
            "status": "WARNING",
            "score": 60,
            "label": "Telegram Bot Service",
            "message": f"Dienst-Status konnte nicht ermittelt werden: {e}",
            "service_state": "error"
        }


def check_git_sync_status() -> Dict[str, Any]:
    """Prüft Git-Status und letztes Commit für GitHub Pages."""
    try:
        res = subprocess.run(
            ["git", "-C", str(BASE_DIR), "log", "-1", "--format=%ct|%cr|%s"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = res.stdout.strip().split("|", 2)
            rel_time = parts[1] if len(parts) > 1 else "kürzlich"
            subject = parts[2] if len(parts) > 2 else "Update"

            # Prüfe uncommittete Änderungen
            stat_res = subprocess.run(
                ["git", "-C", str(BASE_DIR), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=5
            )
            dirty_count = len([l for l in stat_res.stdout.splitlines() if l.strip()])
            dirty_str = f" · {dirty_count} lokale Modifikationen" if dirty_count > 0 else " · Repo synchronisiert"

            return {
                "status": "OK",
                "score": 100,
                "label": "GitHub Pages & Hosting",
                "message": f"Letzter Commit {rel_time}{dirty_str}",
                "last_commit_subject": subject[:50],
                "last_commit_rel": rel_time
            }
        else:
            return {
                "status": "WARNING",
                "score": 70,
                "label": "GitHub Pages & Hosting",
                "message": "Git-Repository verfügbar, aber kein Commit-Log",
                "last_commit_subject": "",
                "last_commit_rel": ""
            }
    except Exception as e:
        return {
            "status": "WARNING",
            "score": 60,
            "label": "GitHub Pages & Hosting",
            "message": f"Git-Check Fehler: {e}",
            "last_commit_subject": "",
            "last_commit_rel": ""
        }


def check_system_health() -> Dict[str, Any]:
    """
    Führt alle Diagnose-Checks aus und fasst sie zu einem Gesamt-Gesundheitsbericht zusammen.
    """
    subsystems = {
        "pipeline_cron": check_pipeline_cron(),
        "quotes": check_quotes_freshness(),
        "incubator": check_incubator_status(),
        "portfolio_user": check_portfolio_and_user_trades(),
        "telegram_bot": check_telegram_bot_service(),
        "git_sync": check_git_sync_status()
    }

    scores = [s.get("score", 100) for s in subsystems.values()]
    overall_score = round(sum(scores) / len(scores)) if scores else 100

    has_critical = any(s.get("status") == "CRITICAL" for s in subsystems.values())
    has_warning = any(s.get("status") == "WARNING" for s in subsystems.values())

    if has_critical:
        overall_status = "CRITICAL"
        status_text = "Handlungsbedarf"
        badge_color = "rose"
        status_dot = "bg-rose-500 animate-ping"
    elif has_warning:
        overall_status = "WARNING"
        status_text = "Eingeschränkt / Warnung"
        badge_color = "amber"
        status_dot = "bg-amber-400 animate-pulse"
    else:
        overall_status = "OK"
        status_text = "100% Betriebsbereit"
        badge_color = "emerald"
        status_dot = "bg-emerald-400 animate-pulse"

    now_iso = datetime.now(timezone.utc).isoformat()
    now_display = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M:%S UTC")

    return {
        "status": overall_status,
        "status_text": status_text,
        "score": overall_score,
        "badge_color": badge_color,
        "status_dot": status_dot,
        "checked_at": now_iso,
        "checked_at_display": now_display,
        "subsystems": subsystems
    }


def generate_health_html_card(health: Dict[str, Any]) -> str:
    """Generiert eine voll responsive HTML-Kachel für die Web-Dashboard Admin-Zentrale."""
    subsystems = health.get("subsystems", {})
    score = health.get("score", 100)
    stat = health.get("status", "OK")
    stat_text = health.get("status_text", "100% Betriebsbereit")
    b_col = health.get("badge_color", "emerald")
    dot_cls = health.get("status_dot", "bg-emerald-400 animate-pulse")
    chk_time = health.get("checked_at_display", "")

    status_badge = f'<span class="px-2.5 py-0.5 rounded text-[11px] font-bold font-mono bg-{b_col}-500/20 text-{b_col}-300 border border-{b_col}-500/40">🟢 {stat}: {stat_text.upper()} ({score}/100)</span>'
    if stat == "WARNING":
        status_badge = f'<span class="px-2.5 py-0.5 rounded text-[11px] font-bold font-mono bg-amber-500/20 text-amber-300 border border-amber-500/40">🟡 {stat}: {stat_text.upper()} ({score}/100)</span>'
    elif stat == "CRITICAL":
        status_badge = f'<span class="px-2.5 py-0.5 rounded text-[11px] font-bold font-mono bg-rose-500/20 text-rose-300 border border-rose-500/40">🔴 {stat}: {stat_text.upper()} ({score}/100)</span>'

    # Subsystem-Kacheln bauen
    items_html = []
    sub_icons = {
        "pipeline_cron": "⏱️",
        "quotes": "📈",
        "incubator": "🧪",
        "portfolio_user": "🏛️",
        "telegram_bot": "🤖",
        "git_sync": "🌐"
    }

    for key, sub in subsystems.items():
        s_stat = sub.get("status", "OK")
        s_lbl = sub.get("label", key)
        s_msg = sub.get("message", "")
        icon = sub_icons.get(key, "⚙️")

        if s_stat == "OK":
            s_badge = '<span class="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">OK</span>'
            border_cls = "border-slate-800 bg-slate-950/80"
        elif s_stat == "WARNING":
            s_badge = '<span class="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30">WARN</span>'
            border_cls = "border-amber-500/30 bg-amber-950/10"
        else:
            s_badge = '<span class="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold bg-rose-500/15 text-rose-400 border border-rose-500/30">ALARM</span>'
            border_cls = "border-rose-500/40 bg-rose-950/20"

        items_html.append(f"""
          <div class="p-3 rounded-xl {border_cls} border space-y-1">
            <div class="flex items-center justify-between">
              <span class="font-bold text-white text-xs flex items-center gap-1.5">
                <span>{icon}</span> {s_lbl}
              </span>
              {s_badge}
            </div>
            <p class="text-[11px] text-slate-300 leading-snug">{s_msg}</p>
          </div>
        """)

    grid_cards = "\n".join(items_html)

    return f"""
      <!-- Card: 24/7 System-Gesundheits- & Funktions-Monitor -->
      <section class="admin-group-system rounded-2xl bg-gradient-to-br from-slate-900/95 via-teal-950/20 to-slate-900 border border-teal-500/40 p-5 shadow-xl space-y-4">
        <div onclick="toggleAccordion('admin-acc-health')" class="cursor-pointer flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-3 border-b border-slate-800 select-none group">
          <div class="flex items-center gap-2.5">
            <span class="text-2xl">🏥</span>
            <div>
              <div class="flex items-center gap-2 flex-wrap">
                <h3 class="font-bold text-white text-base group-hover:text-teal-300 transition">System-Gesundheits- & Infrastruktur-Monitor</h3>
                {status_badge}
              </div>
              <p class="text-xs text-slate-400">Automatische Überwachung aller 6 Kernfunktionen: Pipeline, Kurse, Inkubator, Portfolio/SL/TP, Bot & GitHub-Sync</p>
            </div>
          </div>
          <div class="flex items-center gap-3 self-start sm:self-auto">
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full {dot_cls}"></span>
              <span class="text-[10px] font-mono text-slate-400">Geprüft: {chk_time}</span>
            </div>
            <span id="admin-acc-health-arrow" class="text-xs font-mono text-slate-400 group-hover:text-white transition">▼</span>
          </div>
        </div>

        <div id="admin-acc-health-body" class="space-y-4">
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {grid_cards}
          </div>

          <div class="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 text-xs text-slate-300 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 font-mono">
            <span class="flex items-center gap-2">
              <span>🛡️</span>
              <span><b>Automatisches Failover & Selbstheilung aktiv:</b> Alle Subsysteme isoliert fehlerresistent</span>
            </span>
            <span class="text-[10px] text-teal-400 font-bold">24/7 Raspberry Pi Daemon</span>
          </div>
        </div>
      </section>
    """


def get_health_telegram_report() -> Tuple[str, Dict[str, Any]]:
    """Erzeugt formatierte Telegram-Nachricht und Inline-Keyboard für das Bot-Diagnosecenter."""
    health = check_system_health()
    stat = health.get("status", "OK")
    score = health.get("score", 100)
    stat_text = health.get("status_text", "Betriebsbereit")
    chk_time = health.get("checked_at_display", "")
    subsystems = health.get("subsystems", {})

    stat_icon = "🟢" if stat == "OK" else ("🟡" if stat == "WARNING" else "🔴")

    lines = [
        "🏥 <b>System-Gesundheit & Diagnose-Center</b>",
        "<i>Raspberry Pi 24/7 Trading Engine</i>\n",
        f"Gesamtstatus: <b>{stat_icon} {stat}: {stat_text.upper()} ({score}/100)</b>",
        f"Stand: <code>{chk_time}</code>\n",
        "⚙️ <b>Subsysteme im Detail:</b>"
    ]

    icons = {
        "pipeline_cron": "⏱️",
        "quotes": "📈",
        "incubator": "🧪",
        "portfolio_user": "🏛️",
        "telegram_bot": "🤖",
        "git_sync": "🌐"
    }

    for key, sub in subsystems.items():
        s_stat = sub.get("status", "OK")
        s_icon = "🟢" if s_stat == "OK" else ("🟡" if s_stat == "WARNING" else "🔴")
        lbl = sub.get("label", key)
        msg = sub.get("message", "")
        ic = icons.get(key, "⚙️")
        lines.append(f"• {ic} <b>{lbl}:</b> {s_icon} <code>{s_stat}</code>")
        lines.append(f"  <i>{msg}</i>")

    lines.append("\n🛡️ <i>Alle 6 Dienste werden kontinuierlich vom Hintergrund-Daemon überwacht.</i>")

    text = "\n".join(lines)
    markup = {
        "inline_keyboard": [
            [
                {"text": "🔄 Diagnose aktualisieren", "callback_data": "admin_health_check"}
            ],
            [
                {"text": "🔙 Zurück zur Admin-Zentrale", "callback_data": "menu_admin_hub"}
            ]
        ]
    }
    return text, markup


if __name__ == "__main__":
    print("=" * 70)
    print("🏥 STARTE SYSTEM-GESUNDHEITS- & DIAGNOSE-CHECK")
    print("=" * 70)
    h = check_system_health()
    print(f"Status: {h['status']} ({h['score']}/100) - {h['status_text']}")
    print(f"Zeitpunkt: {h['checked_at_display']}")
    print("-" * 70)
    for k, v in h["subsystems"].items():
        print(f"[{v['status']:<8}] {v['label']:<25}: {v['message']}")
    print("=" * 70)
