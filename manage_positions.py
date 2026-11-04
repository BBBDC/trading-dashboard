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


def update_position(symbol_or_id, user_id=None, stop_loss=None, take_profit=None, entry_price=None, leverage=None, note=None, clear_sl=False, clear_tp=False, sync_db=True, git_push=True):
    """Aktualisiert Stop-Loss, Take-Profit oder Parameter einer bestehenden Position."""
    positions = load_positions()
    found = False
    updated_pos = None

    for i, p in enumerate(positions):
        match_id = (p.get("id") == symbol_or_id or p.get("symbol") == symbol_or_id)
        match_user = (str(p.get("user_id")) == str(user_id)) if user_id else True
        if match_id and match_user:
            if clear_sl:
                p["stop_loss"] = None
            elif stop_loss is not None and str(stop_loss).strip() != "":
                p["stop_loss"] = float(stop_loss)

            if clear_tp:
                p["take_profit"] = None
            elif take_profit is not None and str(take_profit).strip() != "":
                p["take_profit"] = float(take_profit)

            if entry_price is not None:
                p["entry_price"] = float(entry_price)
            if leverage is not None:
                p["leverage"] = float(leverage)
            if note is not None:
                p["note"] = note

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
    print(f"   SL: {updated_pos.get('stop_loss')} | TP: {updated_pos.get('take_profit')}")

    if sync_db:
        sync_dashboard_state(git_push=git_push)

    return updated_pos


def remove_position(symbol_or_id, user_id=None, sync_db=True, git_push=True):
    positions = load_positions()
    initial_len = len(positions)
    
    if user_id:
        positions = [p for p in positions if not ((p.get("symbol") == symbol_or_id or p.get("id") == symbol_or_id) and str(p.get("user_id")) == str(user_id))]
    else:
        positions = [p for p in positions if p.get("symbol") != symbol_or_id and p.get("id") != symbol_or_id]

    if len(positions) < initial_len:
        save_positions(positions)
        print(f"✅ Position '{symbol_or_id}' erfolgreich entfernt.")
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
            if self.path == "/api/positions":
                positions = load_positions()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"positions": positions}, ensure_ascii=False).encode("utf-8"))
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
                    clear_sl = data.get("clear_sl", False)
                    clear_tp = data.get("clear_tp", False)
                    user_id = data.get("user_id")

                    if pos_id:
                        res = update_position(pos_id, user_id=user_id, stop_loss=sl, take_profit=tp, clear_sl=clear_sl, clear_tp=clear_tp)
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

    # remove
    rem_p = subparsers.add_parser("remove", help="Position löschen")
    rem_p.add_argument("symbol_or_id", help="Symbol oder Position ID")

    # list
    subparsers.add_parser("list", help="Alle Positionen anzeigen")

    # serve
    srv_p = subparsers.add_parser("serve", help="Micro-API starten")
    srv_p.add_argument("--port", type=int, default=8085)

    args = parser.parse_args()

    if args.command == "add":
        add_position(args.symbol, args.direction, args.entry_price, args.leverage, args.note, stop_loss=args.stop_loss, take_profit=args.take_profit)
    elif args.command in ("update", "edit"):
        update_position(args.symbol_or_id, stop_loss=args.stop_loss, take_profit=args.take_profit, clear_sl=args.clear_sl, clear_tp=args.clear_tp, entry_price=args.entry_price, leverage=args.leverage, note=args.note)
    elif args.command == "remove":
        remove_position(args.symbol_or_id)
    elif args.command == "list" or not args.command:
        list_positions()
    elif args.command == "serve":
        run_api_server(args.port)
