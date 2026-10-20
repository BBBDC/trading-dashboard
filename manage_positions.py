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


def add_position(symbol, direction, entry_price, leverage=1.0, note="", user_id="", user_name="", sync_db=True, git_push=True):
    positions = load_positions()
    direction = direction.upper()
    if direction not in ("LONG", "SHORT"):
        print("Fehler: Art der Position muss 'LONG' oder 'SHORT' sein.")
        return False

    pos_id = f"pos_{symbol.replace(':', '_')}_{int(datetime.now(timezone.utc).timestamp())}"
    new_pos = {
        "id": pos_id,
        "symbol": symbol,
        "direction": direction,
        "entry_price": float(entry_price),
        "leverage": float(leverage),
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
            positions[i] = new_pos
            updated = True
            break
    if not updated:
        positions.append(new_pos)

    save_positions(positions)
    print(f"✅ Position erfolgreich {'aktualisiert' if updated else 'hinzugefügt'}:")
    print(f"   {symbol} | {direction} | Entry: {entry_price:,.2f} | Hebel: {leverage}x | User: {user_name or 'Default'}")

    if sync_db:
        sync_dashboard_state(git_push=git_push)

    return new_pos


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
        print("  python3 manage_positions.py add NASDAQ:NVDA LONG 180.50 5")
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

        icon = "🟢" if sig == "LONG" else "🔴"
        pnl_sign = "+" if lev_pnl >= 0 else ""
        print(f"{idx}. {icon} {p.get('name', sym)} ({sym})")
        print(f"   Typ: {sig} | Hebel: {lev:g}x | Entry: {entry:,.2f} | Aktuell: {curr:,.2f}")
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
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
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
                    if sym and entry > 0:
                        add_position(sym, direction, entry, lev, note)
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self._send_cors_headers()
                        self.end_headers()
                        self.wfile.write(b'{"status": "ok"}')
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
    add_p.add_argument("--note", default="", help="Optionale Notiz")

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
        add_position(args.symbol, args.direction, args.entry_price, args.leverage, args.note)
    elif args.command == "remove":
        remove_position(args.symbol_or_id)
    elif args.command == "list" or not args.command:
        list_positions()
    elif args.command == "serve":
        run_api_server(args.port)
