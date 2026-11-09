#!/usr/bin/env python3
"""
TradingView Super-Analyst – User Positions Manager & Micro-API.
Ermöglicht das bequeme Eintragen, Anzeigen und Löschen von eigenen Nutzer-Positionen
entweder über das Terminal (CLI) oder über einen sicheren lokalen REST-Endpunkt.
"""

import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
POSITIONS_FILE = BASE_DIR / "knowledge_base" / "user_positions.json"
USER_HISTORY_FILE = BASE_DIR / "knowledge_base" / "user_positions_history.json"
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"


def sync_dashboard_state(git_push=True):
    """Aktualisiert Berechnungen, baut das Dashboard neu und pusht optional zu GitHub."""
    try:
        from portfolio_engine import evaluate_user_positions
        if DB_FILE.exists():
            with open(DB_FILE, "r", encoding="utf-8") as f:
                db = json.load(f)
            evaluated = evaluate_user_positions(db.get("assets", []))
            db["user_positions"] = evaluated.get("positions", [])
            db["user_positions_history"] = load_history()
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(db, f, indent=2, ensure_ascii=False)
        
        # HTML neu bauen
        subprocess.run([sys.executable, str(BASE_DIR / "build_dashboard.py")], cwd=str(BASE_DIR), check=True)

        # Git Sync falls gewünscht
        if git_push:
            from update_dashboard import git_sync_dashboard
            git_sync_dashboard()
    except Exception as e:
        print(f"Sync Dashboard Fehler: {e}")


def load_history(user_id=None):
    """Lädt die Liste aller bisher geschlossenen Nutzer-Trades aus user_positions_history.json."""
    if USER_HISTORY_FILE.exists():
        try:
            with open(USER_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                closed = data.get("closed_positions", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                if user_id:
                    uid_str = str(user_id)
                    return [p for p in closed if str(p.get("user_id", "")) == uid_str or not p.get("user_id")]
                return closed
        except Exception:
            return []
    return []


def save_history(closed_positions):
    """Speichert geschlossene Positionen atomar in user_positions_history.json."""
    USER_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "closed_positions": closed_positions
    }
    with open(USER_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def format_duration(start_iso, end_iso=None):
    """Berechnet und formatiert die Haltedauer als lesbaren String."""
    if not start_iso:
        return "Unbekannt"
    try:
        if isinstance(start_iso, str):
            dt_start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        else:
            dt_start = start_iso
        if end_iso:
            if isinstance(end_iso, str):
                dt_end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
            else:
                dt_end = end_iso
        else:
            dt_end = datetime.now(timezone.utc)
        
        diff = dt_end - dt_start
        total_seconds = max(0, int(diff.total_seconds()))
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        
        if days > 0:
            return f"{days}T {hours}Std." if hours > 0 else f"{days}T"
        elif hours > 0:
            return f"{hours}Std. {minutes}Min."
        else:
            return f"{max(1, minutes)}Min."
    except Exception:
        return "-"


def load_positions():
    if POSITIONS_FILE.exists():
        try:
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("positions", [])
        except Exception:
            return []
    return []


def save_positions(positions):
    POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "positions": positions
    }
    with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def add_position(symbol, direction, entry_price, leverage=1.0, note="", user_id="", user_name="", stop_loss=None, take_profit=None, sync_db=True, git_push=True):
    positions = load_positions()
    direction = direction.upper()
    if direction not in ("LONG", "SHORT"):
        print("Fehler: Art der Position muss 'LONG' oder 'SHORT' sein.")
        return False

    sl_val = None
    if stop_loss is not None and str(stop_loss).strip() != "":
        try:
            sl_val = float(stop_loss)
        except (ValueError, TypeError):
            sl_val = None

    tp_val = None
    if take_profit is not None and str(take_profit).strip() != "":
        try:
            tp_val = float(take_profit)
        except (ValueError, TypeError):
            tp_val = None

    pos_id = f"pos_{symbol.replace(':', '_')}_{int(datetime.now(timezone.utc).timestamp())}"
    new_pos = {
        "id": pos_id,
        "symbol": symbol,
        "direction": direction,
        "entry_price": float(entry_price),
        "leverage": float(leverage),
        "stop_loss": sl_val,
        "take_profit": tp_val,
        "note": note,
        "user_id": str(user_id) if user_id else "",
        "user_name": str(user_name) if user_name else "",
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    # Falls bereits vorhanden für denselben Nutzer & Symbol, ersetzen, sonst anhängen
    updated = False
    for i, p in enumerate(positions):
        same_user = (p.get("user_id") == str(user_id)) if user_id else True
        if p.get("symbol") == symbol and same_user:
            # Bestehende ID und Erstellzeit beibehalten wenn möglich
            new_pos["id"] = p.get("id", pos_id)
            new_pos["created_at"] = p.get("created_at", new_pos["created_at"])
            positions[i] = new_pos
            updated = True
            break
    if not updated:
        positions.append(new_pos)

    save_positions(positions)
    print(f"✅ Position erfolgreich {'aktualisiert' if updated else 'hinzugefügt'}:")
    sl_txt = f"{sl_val:,.2f}" if sl_val is not None else "Kein SL"
    tp_txt = f"{tp_val:,.2f}" if tp_val is not None else "Kein TP"
    print(f"   {symbol} | {direction} | Entry: {entry_price:,.2f} | Hebel: {leverage}x | SL: {sl_txt} | TP: {tp_txt} | User: {user_name or 'Default'}")

    # Ad-hoc Einzel-Scan & Chart-Generierung für dieses Asset sofort ausführen
    try:
        from single_asset_rescan import rescan_and_evaluate_asset
        rescan_and_evaluate_asset(symbol, user_pos=new_pos)
    except Exception as re:
        print(f"Hinweis: Ad-hoc Einzelscan fehlgeschlagen ({re})")

    if sync_db:
        sync_dashboard_state(git_push=git_push)

    return new_pos


def update_position(symbol_or_id, user_id=None, stop_loss=None, take_profit=None, entry_price=None, leverage=None, direction=None, note=None, clear_sl=False, clear_tp=False, sync_db=True, git_push=True):
    """Aktualisiert Stop-Loss, Take-Profit, Einstieg, Hebel, Richtung oder Notiz einer bestehenden Position."""
    positions = load_positions()
    found = False
    updated_pos = None

    for i, p in enumerate(positions):
        match_id = (p.get("id") == symbol_or_id or p.get("symbol") == symbol_or_id)
        match_user = (str(p.get("user_id")) == str(user_id)) if (user_id and p.get("user_id")) else True
        if match_id and match_user:
            if direction is not None:
                d_up = str(direction).strip().upper()
                if d_up in ("LONG", "SHORT"):
                    p["direction"] = d_up

            if clear_sl:
                p["stop_loss"] = None
            elif stop_loss is not None and str(stop_loss).strip() != "":
                p["stop_loss"] = float(stop_loss)

            if clear_tp:
                p["take_profit"] = None
            elif take_profit is not None and str(take_profit).strip() != "":
                p["take_profit"] = float(take_profit)

            if entry_price is not None and str(entry_price).strip() != "":
                p["entry_price"] = float(entry_price)
            if leverage is not None and str(leverage).strip() != "":
                p["leverage"] = float(leverage)
            if note is not None:
                p["note"] = str(note)

            p["updated_at"] = datetime.now(timezone.utc).isoformat()
            positions[i] = p
            updated_pos = p
            found = True
            break

    if not found:
        print(f"⚠️ Keine Position mit Symbol oder ID '{symbol_or_id}' gefunden.")
        return None

    save_positions(positions)
    print(f"✅ Position '{symbol_or_id}' erfolgreich aktualisiert:")
    print(f"   Richtung: {updated_pos.get('direction')} | Entry: {updated_pos.get('entry_price')} | Hebel: {updated_pos.get('leverage')}x | SL: {updated_pos.get('stop_loss')} | TP: {updated_pos.get('take_profit')}")

    # Ad-hoc Einzelscan für dieses Asset anstoßen
    try:
        from single_asset_rescan import rescan_and_evaluate_asset
        rescan_and_evaluate_asset(updated_pos.get("symbol"), user_pos=updated_pos)
    except Exception:
        pass

    if sync_db:
        sync_dashboard_state(git_push=git_push)

    return updated_pos


def archive_closed_position(pos, exit_price=None, exit_reason="MANUAL_CLOSE", exit_reason_display=None):
    """Archiviert einen geschlossenen Nutzer-Trade in user_positions_history.json."""
    history = load_history()
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    
    direction = str(pos.get("direction", "LONG")).upper()
    entry_p = float(pos.get("entry_price", 0.0))
    lev = float(pos.get("leverage", 1.0))
    
    if exit_price is not None:
        try:
            exit_p = float(exit_price)
        except (ValueError, TypeError):
            exit_p = float(pos.get("current_price", entry_p))
    else:
        exit_p = float(pos.get("current_price", entry_p))
        
    if entry_p > 0:
        if direction == "LONG":
            raw_pnl = ((exit_p - entry_p) / entry_p) * 100.0
        else:
            raw_pnl = ((entry_p - exit_p) / entry_p) * 100.0
    else:
        raw_pnl = 0.0
        
    lev_pnl = raw_pnl * lev
    is_win = raw_pnl > 0
    result = "WIN" if is_win else ("LOSS" if raw_pnl < 0 else "BREAKEVEN")
    
    # Standard-Displaytext für Schließungsgrund
    if not exit_reason_display:
        if exit_reason == "STOP_LOSS_TRIGGERED":
            sl_val = pos.get("stop_loss")
            sl_str = f" bei {sl_val:,.2f} $" if sl_val is not None else ""
            exit_reason_display = f"🛑 Stop-Loss ausgelöst{sl_str}"
        elif exit_reason == "TAKE_PROFIT_TRIGGERED":
            tp_val = pos.get("take_profit")
            tp_str = f" bei {tp_val:,.2f} $" if tp_val is not None else ""
            exit_reason_display = f"🎯 Take-Profit erreicht{tp_str}"
        elif exit_reason == "MANUAL_CLOSE":
            exit_reason_display = "✋ Manuell geschlossen"
        else:
            exit_reason_display = exit_reason
            
    closed_rec = {
        "id": pos.get("id") or f"pos_{pos.get('symbol', '').replace(':', '_')}_{int(now_dt.timestamp())}",
        "symbol": pos.get("symbol"),
        "name": pos.get("name") or pos.get("symbol"),
        "direction": direction,
        "entry_price": round(entry_p, 4 if entry_p < 10 else 2),
        "exit_price": round(exit_p, 4 if exit_p < 10 else 2),
        "leverage": round(lev, 1),
        "stop_loss": pos.get("stop_loss"),
        "take_profit": pos.get("take_profit"),
        "realized_pnl_pct": round(raw_pnl, 2),
        "realized_pnl_leveraged_pct": round(lev_pnl, 2),
        "result": result,
        "exit_reason": exit_reason,
        "exit_reason_display": exit_reason_display,
        "created_at": pos.get("created_at", now_iso),
        "closed_at": now_iso,
        "holding_duration_str": format_duration(pos.get("created_at"), now_iso),
        "user_id": str(pos.get("user_id", "")),
        "user_name": str(pos.get("user_name", "")),
        "note": pos.get("note", "")
    }
    
    # Prepend zu bestehender Historie (vermeide Duplikate)
    history = [h for h in history if h.get("id") != closed_rec["id"]]
    history.insert(0, closed_rec)
    save_history(history)
    return closed_rec


def close_position(symbol_or_id, exit_price=None, exit_reason="MANUAL_CLOSE", exit_reason_display=None, user_id=None, sync_db=True, git_push=True, notify=True):
    """Schließt eine aktive Position, archiviert sie in der Historie und benachrichtigt optional."""
    positions = load_positions()
    found_pos = None
    remaining_positions = []
    
    for p in positions:
        match_id = (p.get("id") == symbol_or_id or p.get("symbol") == symbol_or_id)
        match_user = (str(p.get("user_id")) == str(user_id)) if (user_id and p.get("user_id")) else True
        if match_id and match_user and not found_pos:
            found_pos = p
        else:
            remaining_positions.append(p)
            
    if not found_pos:
        print(f"⚠️ Keine Position mit Symbol oder ID '{symbol_or_id}' gefunden.")
        return None
        
    # In Historie archivieren
    closed_rec = archive_closed_position(found_pos, exit_price=exit_price, exit_reason=exit_reason, exit_reason_display=exit_reason_display)
    
    # Aus aktiven Positionen entfernen
    save_positions(remaining_positions)
    print(f"✅ Position '{symbol_or_id}' geschlossen und archiviert:")
    print(f"   Entry: {closed_rec['entry_price']} -> Exit: {closed_rec['exit_price']} | PnL: {closed_rec['realized_pnl_leveraged_pct']:+.2f}% | Grund: {closed_rec['exit_reason_display']}")
    
    # Optional Benachrichtigung senden
    if notify:
        try:
            from notifications import send_user_position_closed_notification
            send_user_position_closed_notification(closed_rec)
        except Exception as ne:
            print(f"Hinweis: Push-Benachrichtigung fehlgeschlagen ({ne})")
            
    if sync_db:
        sync_dashboard_state(git_push=git_push)
        
    return closed_rec


def remove_position(symbol_or_id, user_id=None, sync_db=True, git_push=True, archive=True):
    """Löscht eine Position. Standardmäßig wird sie in die Trade-Historie archiviert."""
    if archive:
        closed = close_position(symbol_or_id, user_id=user_id, sync_db=sync_db, git_push=git_push, exit_reason="MANUAL_CLOSE")
        return bool(closed)

    positions = load_positions()
    initial_len = len(positions)
    
    if user_id:
        positions = [p for p in positions if not ((p.get("symbol") == symbol_or_id or p.get("id") == symbol_or_id) and str(p.get("user_id")) == str(user_id))]
    else:
        positions = [p for p in positions if p.get("symbol") != symbol_or_id and p.get("id") != symbol_or_id]

    if len(positions) < initial_len:
        save_positions(positions)
        print(f"✅ Position '{symbol_or_id}' erfolgreich entfernt (ohne Archiv).")
        if sync_db:
            sync_dashboard_state(git_push=git_push)
        return True
    else:
        print(f"⚠️ Keine Position mit Symbol oder ID '{symbol_or_id}' gefunden.")
        return False


def list_positions():
    positions = load_positions()
    print("=" * 65)
    print(f"  EIGENE GETRACKTE NUTZER-POSITIONEN ({len(positions)})")
    print("=" * 65)
    if not positions:
        print("Aktuell keine eigenen Positionen hinterlegt.")
        print("Tipp: Trage eine neue Position ein mit:")
        print("  python3 manage_positions.py add NASDAQ:NVDA LONG 180.50 5 --sl 170 --tp 210")
        print("=" * 65)
        return

    for idx, p in enumerate(positions, 1):
        sym = p.get("symbol")
        sig = p.get("direction")
        entry = p.get("entry_price", 0.0)
        curr = p.get("current_price", entry)
        lev = p.get("leverage", 1.0)
        pnl = p.get("pnl_pct", 0.0)
        lev_pnl = p.get("pnl_leveraged_pct", 0.0)
        rec = p.get("recommendation", {})
        sl = p.get("stop_loss")
        tp = p.get("take_profit")

        icon = "🟢" if sig == "LONG" else "🔴"
        pnl_sign = "+" if lev_pnl >= 0 else ""
        print(f"{idx}. {icon} {p.get('name', sym)} ({sym})")
        print(f"   Typ: {sig} | Hebel: {lev:g}x | Entry: {entry:,.2f} | Aktuell: {curr:,.2f}")
        
        sl_str = f"{sl:,.2f} $" if sl is not None else "-"
        tp_str = f"{tp:,.2f} $" if tp is not None else "-"
        crv_info = ""
        if sl is not None and tp is not None:
            risk = abs(entry - float(sl))
            reward = abs(float(tp) - entry)
            if risk > 0:
                crv_info = f" | CRV: 1:{reward / risk:.2f}"
        print(f"   🛑 Stop-Loss: {sl_str} | 🎯 Take-Profit: {tp_str}{crv_info}")
        print(f"   Performance: {pnl_sign}{pnl:.2f}% Basis | {pnl_sign}{lev_pnl:.2f}% Gehebelt")
        if rec and rec.get("action"):
            print(f"   💡 Empfehlung: [{rec.get('action')}] {rec.get('title')} - {rec.get('message')}")
        print("-" * 65)


def list_history(user_id=None):
    """Gibt eine formatierte Tabelle aller bisher geschlossenen Nutzer-Trades aus."""
    history = load_history(user_id=user_id)
    print("=" * 70)
    print(f"  GESCHLOSSENE NUTZER-TRADES / HISTORIE ({len(history)})")
    print("=" * 70)
    if not history:
        print("Bisher keine geschlossenen Trades in der Historie vorhanden.")
        print("=" * 70)
        return
        
    wins = [t for t in history if t.get("realized_pnl_pct", 0) > 0]
    wr = (len(wins) / len(history) * 100.0) if history else 0.0
    tot_pnl = sum(t.get("realized_pnl_leveraged_pct", 0) for t in history)
    print(f"  📊 Statistik: {len(history)} Trades | Win-Rate: {wr:.1f}% ({len(wins)}W/{len(history)-len(wins)}L) | Netto-PnL: {tot_pnl:+.2f}%")
    print("-" * 70)
    
    for idx, t in enumerate(history, 1):
        sym = t.get("symbol")
        sig = t.get("direction", "LONG")
        entry = t.get("entry_price", 0.0)
        exit_p = t.get("exit_price", entry)
        lev = t.get("leverage", 1.0)
        pnl = t.get("realized_pnl_pct", 0.0)
        lev_pnl = t.get("realized_pnl_leveraged_pct", 0.0)
        reason = t.get("exit_reason_display", t.get("exit_reason", ""))
        dur = t.get("holding_duration_str", "-")
        closed_at = t.get("closed_at", "")[:16].replace("T", " ")
        
        icon = "🟢" if sig == "LONG" else "🔴"
        res_badge = "✅ WIN" if pnl > 0 else ("❌ LOSS" if pnl < 0 else "⚪ BE")
        pnl_sign = "+" if lev_pnl >= 0 else ""
        
        print(f"{idx}. {icon} {t.get('name', sym)} ({sym}) [{res_badge}]")
        print(f"   Typ: {sig} {lev:g}x | Entry: {entry:,.2f} $ ➔ Exit: {exit_p:,.2f} $ | Dauer: {dur}")
        print(f"   Realisierter PnL: {pnl_sign}{lev_pnl:.2f}% (Basis: {pnl_sign}{pnl:.2f}%)")
        print(f"   Grund: {reason} | Geschlossen: {closed_at} UTC | User: {t.get('user_name', 'Default')}")
        print("-" * 70)


def run_api_server(port=8085):
    """Startet einen winzigen REST-Endpunkt zur sicheren Synchronisation vom Web-Dashboard."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import urllib.parse

    class PositionsHandler(BaseHTTPRequestHandler):
        def _send_cors_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

        def do_OPTIONS(self):
            self.send_response(200)
            self._send_cors_headers()
            self.end_headers()

        def do_GET(self):
            if self.path.startswith("/api/positions"):
                positions = load_positions()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"positions": positions}, ensure_ascii=False).encode("utf-8"))
            elif self.path.startswith("/api/history"):
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                uid = qs.get("user_id", [None])[0]
                history = load_history(user_id=uid)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"history": history}, ensure_ascii=False).encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path == "/api/positions":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                try:
                    data = json.loads(body)
                    sym = data.get("symbol")
                    direction = data.get("direction", "LONG")
                    entry = float(data.get("entry_price", 0))
                    lev = float(data.get("leverage", 1))
                    note = data.get("note", "")
                    sl = data.get("stop_loss")
                    tp = data.get("take_profit")
                    user_id = data.get("user_id", "")
                    user_name = data.get("user_name", "")

                    if sym and entry > 0:
                        res = add_position(sym, direction, entry, lev, note, user_id=user_id, user_name=user_name, stop_loss=sl, take_profit=tp)
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self._send_cors_headers()
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "ok", "position": res}).encode("utf-8"))
                        return
                except Exception as e:
                    self.send_response(400)
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                    return
            elif self.path == "/api/positions/close":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                try:
                    data = json.loads(body)
                    pos_id = data.get("id") or data.get("symbol")
                    exit_p = data.get("exit_price")
                    exit_reason = data.get("exit_reason", "MANUAL_CLOSE")
                    user_id = data.get("user_id")

                    if pos_id:
                        res = close_position(pos_id, exit_price=exit_p, exit_reason=exit_reason, user_id=user_id)
                        if res:
                            self.send_response(200)
                            self.send_header("Content-Type", "application/json")
                            self._send_cors_headers()
                            self.end_headers()
                            self.wfile.write(json.dumps({"status": "ok", "closed": res}).encode("utf-8"))
                            return
                        else:
                            self.send_response(404)
                            self._send_cors_headers()
                            self.end_headers()
                            self.wfile.write(json.dumps({"error": "Position not found"}).encode("utf-8"))
                            return
                except Exception as e:
                    self.send_response(400)
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                    return
            self.send_response(404)
            self.end_headers()

        def do_PUT(self):
            if self.path == "/api/positions":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                try:
                    data = json.loads(body)
                    pos_id = data.get("id") or data.get("symbol")
                    sl = data.get("stop_loss")
                    tp = data.get("take_profit")
                    entry_p = data.get("entry_price")
                    lev = data.get("leverage")
                    direction = data.get("direction")
                    note = data.get("note")
                    clear_sl = data.get("clear_sl", False)
                    clear_tp = data.get("clear_tp", False)
                    user_id = data.get("user_id")

                    if pos_id:
                        res = update_position(
                            pos_id,
                            user_id=user_id,
                            stop_loss=sl,
                            take_profit=tp,
                            entry_price=entry_p,
                            leverage=lev,
                            direction=direction,
                            note=note,
                            clear_sl=clear_sl,
                            clear_tp=clear_tp
                        )
                        if res:
                            self.send_response(200)
                            self.send_header("Content-Type", "application/json")
                            self._send_cors_headers()
                            self.end_headers()
                            self.wfile.write(json.dumps({"status": "ok", "position": res}).encode("utf-8"))
                            return
                        else:
                            self.send_response(404)
                            self._send_cors_headers()
                            self.end_headers()
                            self.wfile.write(json.dumps({"error": "Position not found"}).encode("utf-8"))
                            return
                except Exception as e:
                    self.send_response(400)
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                    return
            self.send_response(404)
            self.end_headers()

        def do_DELETE(self):
            if self.path.startswith("/api/positions"):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
                try:
                    data = json.loads(body) if body.strip() else {}
                    pos_id = data.get("id") or data.get("symbol")
                    if not pos_id:
                        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                        pos_id = qs.get("id", [None])[0] or qs.get("symbol", [None])[0]
                    if pos_id:
                        res = close_position(pos_id, exit_reason="MANUAL_CLOSE", user_id=data.get("user_id"))
                        if res:
                            self.send_response(200)
                            self.send_header("Content-Type", "application/json")
                            self._send_cors_headers()
                            self.end_headers()
                            self.wfile.write(json.dumps({"status": "ok", "closed": res}).encode("utf-8"))
                            return
                except Exception as e:
                    self.send_response(400)
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                    return
            self.send_response(404)
            self.end_headers()

    server = HTTPServer(("0.0.0.0", port), PositionsHandler)
    print(f"🚀 Positions Micro-API läuft auf Port {port} (0.0.0.0:{port})")
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="User Positions Manager")
    subparsers = parser.add_subparsers(dest="command")

    # add
    add_p = subparsers.add_parser("add", help="Neue Position anlegen")
    add_p.add_argument("symbol", help="Ticker, z.B. NASDAQ:NVDA oder BINANCE:BTCUSDT")
    add_p.add_argument("direction", choices=["LONG", "SHORT", "long", "short"], help="Richtung: LONG oder SHORT")
    add_p.add_argument("entry_price", type=float, help="Einstiegskurs")
    add_p.add_argument("leverage", type=float, default=1.0, nargs="?", help="Hebel (Standard: 1.0)")
    add_p.add_argument("--sl", "--stop-loss", dest="stop_loss", type=float, default=None, help="Stop-Loss Kurs")
    add_p.add_argument("--tp", "--take-profit", dest="take_profit", type=float, default=None, help="Take-Profit Kurs")
    add_p.add_argument("--note", default="", help="Optionale Notiz")

    # update / edit
    upd_p = subparsers.add_parser("update", aliases=["edit"], help="Position bearbeiten (SL/TP nachtragen)")
    upd_p.add_argument("symbol_or_id", help="Symbol oder Position ID")
    upd_p.add_argument("--sl", "--stop-loss", dest="stop_loss", type=float, default=None, help="Neuer Stop-Loss Kurs")
    upd_p.add_argument("--tp", "--take-profit", dest="take_profit", type=float, default=None, help="Neuer Take-Profit Kurs")
    upd_p.add_argument("--clear-sl", action="store_true", help="Stop-Loss entfernen")
    upd_p.add_argument("--clear-tp", action="store_true", help="Take-Profit entfernen")
    upd_p.add_argument("--entry", dest="entry_price", type=float, default=None, help="Neuer Einstiegskurs")
    upd_p.add_argument("--leverage", dest="leverage", type=float, default=None, help="Neuer Hebel")
    upd_p.add_argument("--note", default=None, help="Notiz aktualisieren")

    # close
    close_p = subparsers.add_parser("close", help="Position schließen und in Historie archivieren")
    close_p.add_argument("symbol_or_id", help="Symbol oder Position ID")
    close_p.add_argument("--price", dest="exit_price", type=float, default=None, help="Ausstiegskurs (Standard: aktueller Live-Kurs)")
    close_p.add_argument("--reason", default="MANUAL_CLOSE", help="Schließungsgrund")

    # remove
    rem_p = subparsers.add_parser("remove", help="Position löschen")
    rem_p.add_argument("symbol_or_id", help="Symbol oder Position ID")
    rem_p.add_argument("--no-archive", action="store_true", help="Ohne Archivierung endgültig löschen")

    # list
    subparsers.add_parser("list", help="Alle Positionen anzeigen")

    # history
    hist_p = subparsers.add_parser("history", help="Historie geschlossener Trades anzeigen")
    hist_p.add_argument("--user-id", default=None, help="Nach User-ID filtern")

    # serve
    srv_p = subparsers.add_parser("serve", help="Micro-API starten")
    srv_p.add_argument("--port", type=int, default=8085)

    args = parser.parse_args()

    if args.command == "add":
        add_position(args.symbol, args.direction, args.entry_price, args.leverage, args.note, stop_loss=args.stop_loss, take_profit=args.take_profit)
    elif args.command in ("update", "edit"):
        update_position(args.symbol_or_id, stop_loss=args.stop_loss, take_profit=args.take_profit, clear_sl=args.clear_sl, clear_tp=args.clear_tp, entry_price=args.entry_price, leverage=args.leverage, note=args.note)
    elif args.command == "close":
        close_position(args.symbol_or_id, exit_price=args.exit_price, exit_reason=args.reason)
    elif args.command == "remove":
        remove_position(args.symbol_or_id, archive=not args.no_archive)
    elif args.command == "history":
        list_history(user_id=args.user_id)
    elif args.command == "list" or not args.command:
        list_positions()
    elif args.command == "serve":
        run_api_server(args.port)
