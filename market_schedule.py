#!/usr/bin/env python3
"""
TradingView Super-Analyst – Market Schedule & Session Gatekeeper.
Verwaltet dynamische, markt- und asset-spezifische Handelszeiten:
- Krypto (24/7): Alle 4 Stunden kontinuierlich.
- US-Aktien (NYSE/NASDAQ): Nur Mo-Fr zur US-Session (09:30 - 16:05 ET = 15:30 - 22:05 CET) alle ~75 Min.
  Zusätzlich Pre-Market Radar (15:00 - 15:30 CET). Außerhalb und am Wochenende: PAUSE.
- Deutsche Aktien (XETRA): Nur Mo-Fr 09:00 - 17:35 CET (Open, Midday, Close). Außerhalb: PAUSE.
- Rohstoffe & Futures (COMEX/NYMEX/TVC): Mo 00:00 bis Fr 23:00 CET alle 4h. Am Wochenende: PAUSE.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple, List, Optional
import zoneinfo

TZ_BERLIN = zoneinfo.ZoneInfo("Europe/Berlin")
TZ_NEW_YORK = zoneinfo.ZoneInfo("America/New_York")
TZ_UTC = zoneinfo.ZoneInfo("UTC")


# =====================================================================
# ASSET-KLASSIFIZIERUNG
# =====================================================================

def classify_symbol(symbol: str) -> Dict[str, str]:
    """Klassifiziert ein Symbol in eine Marktkategorie und Börse."""
    sym_upper = symbol.upper()
    prefix = sym_upper.split(":")[0] if ":" in sym_upper else ""

    if prefix in ("BINANCE", "COINBASE", "KRAKEN", "CRYPTOCAP") or "USDT" in sym_upper or "USD" in sym_upper and any(c in sym_upper for c in ["BTC", "ETH", "SOL", "AVAX", "DOT", "BCH", "CRV", "AAVE", "KSM", "GMX"]):
        return {
            "category": "CRYPTO",
            "exchange": prefix or "CRYPTO",
            "timezone": "UTC",
            "label": "Krypto (24/7)"
        }

    if prefix in ("NASDAQ", "NYSE"):
        return {
            "category": "US_STOCKS",
            "exchange": prefix,
            "timezone": "America/New_York",
            "label": f"US-Aktien ({prefix})"
        }

    if prefix in ("XETR", "FWB"):
        return {
            "category": "EU_STOCKS",
            "exchange": prefix,
            "timezone": "Europe/Berlin",
            "label": "Deutsche Aktien (XETRA)"
        }

    if prefix in ("COMEX", "NYMEX", "ICEEUR", "TVC", "SP"):
        return {
            "category": "COMMODITIES_FUTURES",
            "exchange": prefix,
            "timezone": "Europe/Berlin",
            "label": "Rohstoffe & Indizes"
        }

    # Standard-Fallback (als US-Aktie oder Global)
    return {
        "category": "US_STOCKS",
        "exchange": prefix or "US",
        "timezone": "America/New_York",
        "label": "Global / US"
    }


# =====================================================================
# MARKT-STATUS ERMITTLUNG
# =====================================================================

def get_market_state(symbol: str, now_utc: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Ermittelt für ein Symbol präzise den aktuellen Marktstatus:
    - is_open: Ist der Markt für reguläre Kerzen geöffnet?
    - is_premarket: Befindet sich der Markt in der Vorbörsen-Phase?
    - session_name: Name der aktuellen Session
    - min_interval_minutes: Erforderlicher Mindestabstand zwischen Scans
    - next_event: Beschreibung des nächsten Markt-Events
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    classification = classify_symbol(symbol)
    cat = classification["category"]

    # 1. KRYPTO (24/7)
    if cat == "CRYPTO":
        return {
            "is_open": True,
            "is_premarket": False,
            "status": "OPEN",
            "session_name": "24/7 Non-Stop",
            "min_interval_minutes": 220,  # ca. 4 Stunden (etwas Puffer für stündlichen Cron)
            "badge_color": "emerald",
            "status_text": "Aktiv (24/7)"
        }

    # 2. US-AKTIEN (Wall Street)
    if cat == "US_STOCKS":
        ny_time = now_utc.astimezone(TZ_NEW_YORK)
        weekday = ny_time.weekday()  # 0=Montag, 4=Freitag, 5=Samstag, 6=Sonntag
        hour = ny_time.hour
        minute = ny_time.minute
        time_hm = (hour, minute)

        # Wochenende (Sa & So)
        if weekday >= 5:
            return {
                "is_open": False,
                "is_premarket": False,
                "status": "CLOSED",
                "session_name": "Wochenende (Geschlossen)",
                "min_interval_minutes": 999999,
                "badge_color": "slate",
                "status_text": "Wochenende (Öffnet Mo 15:30 CET)"
            }

        # Reguläre US-Handelszeit: 09:30 - 16:05 ET (15:30 - 22:05 CET)
        if (9, 30) <= time_hm <= (16, 5):
            return {
                "is_open": True,
                "is_premarket": False,
                "status": "OPEN",
                "session_name": "US Regular Session (Wall Street)",
                "min_interval_minutes": 70,  # stündlicher Scan während der offenen Session!
                "badge_color": "emerald",
                "status_text": f"US Session (Offen bis {22 if ny_time.tzname() == 'EDT' else 22}:00 CET)"
            }

        # US Pre-Market Fenster: 09:00 - 09:30 ET (15:00 - 15:30 CET)
        if (9, 0) <= time_hm < (9, 30):
            return {
                "is_open": False,
                "is_premarket": True,
                "status": "PRE_MARKET",
                "session_name": "US Pre-Market Radar",
                "min_interval_minutes": 25,
                "badge_color": "amber",
                "status_text": "Vorbörse (Eröffnung in Kürze)"
            }

        # Nachbörse / Nachtphase
        return {
            "is_open": False,
            "is_premarket": False,
            "status": "CLOSED",
            "session_name": "US After-Hours / Nachtpause",
            "min_interval_minutes": 999999,
            "badge_color": "slate",
            "status_text": "Geschlossen (Pause bis 15:30 CET)"
        }

    # 3. DEUTSCHE AKTIEN (XETRA)
    if cat == "EU_STOCKS":
        berlin_time = now_utc.astimezone(TZ_BERLIN)
        weekday = berlin_time.weekday()
        time_hm = (berlin_time.hour, berlin_time.minute)

        if weekday >= 5:
            return {
                "is_open": False,
                "is_premarket": False,
                "status": "CLOSED",
                "session_name": "Wochenende (Geschlossen)",
                "min_interval_minutes": 999999,
                "badge_color": "slate",
                "status_text": "Wochenende (Öffnet Mo 09:00 CET)"
            }

        # XETRA Handelszeit: 09:00 - 17:35 CET
        if (9, 0) <= time_hm <= (17, 35):
            return {
                "is_open": True,
                "is_premarket": False,
                "status": "OPEN",
                "session_name": "XETRA Regular Session",
                "min_interval_minutes": 160,  # ~ alle 3-4 Stunden (Open 09:05, Midday 13:05, Close 17:05)
                "badge_color": "emerald",
                "status_text": "XETRA Offen (bis 17:30 CET)"
            }

        return {
            "is_open": False,
            "is_premarket": False,
            "status": "CLOSED",
            "session_name": "XETRA Nachtpause",
            "min_interval_minutes": 999999,
            "badge_color": "slate",
            "status_text": "Geschlossen (Pause bis 09:00 CET)"
        }

    # 4. ROHSTOFFE & FUTURES / INDIZES (COMEX, NYMEX, TVC)
    if cat == "COMMODITIES_FUTURES":
        berlin_time = now_utc.astimezone(TZ_BERLIN)
        weekday = berlin_time.weekday()
        hour = berlin_time.hour

        # Freitag ab 23:00 bis Sonntag 23:00 CET geschlossen
        if weekday == 4 and hour >= 23 or weekday == 5 or (weekday == 6 and hour < 23):
            return {
                "is_open": False,
                "is_premarket": False,
                "status": "CLOSED",
                "session_name": "Wochenendpause Rohstoffe",
                "min_interval_minutes": 999999,
                "badge_color": "slate",
                "status_text": "Wochenende (Pause)"
            }

        # Tägliche Abrechnungspause 23:00 - 00:00 CET
        if hour == 23:
            return {
                "is_open": False,
                "is_premarket": False,
                "status": "CLOSED",
                "session_name": "Settlement Break",
                "min_interval_minutes": 999999,
                "badge_color": "slate",
                "status_text": "Settlement Pause"
            }

        return {
            "is_open": True,
            "is_premarket": False,
            "status": "OPEN",
            "session_name": "Commodities / Global Session",
            "min_interval_minutes": 220,  # 4h-Takt während der Woche
            "badge_color": "emerald",
            "status_text": "Globaler Handel Aktiv"
        }

    return {
        "is_open": True,
        "is_premarket": False,
        "status": "OPEN",
        "session_name": "Default Session",
        "min_interval_minutes": 220,
        "badge_color": "emerald",
        "status_text": "Aktiv"
    }


# =====================================================================
# GATEKEEPER-PRÜFUNG: SOLL EIN ASSET JETZT GESCANNT WERDEN?
# =====================================================================

def should_scan_asset(asset: Dict[str, Any], now_utc: Optional[datetime] = None, force_all: bool = False) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Prüft, ob für ein Asset zum jetzigen Zeitpunkt ein neuer Scan fällig ist.
    Gibt (should_scan, reason, state) zurück.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    sym = asset.get("symbol", "")
    state = get_market_state(sym, now_utc)

    if force_all:
        return True, "Manueller / Erzwungener Voll-Scan (--force)", state

    # Markt geschlossen -> Nicht scannen, alte Werte beibehalten
    if not state["is_open"] and not state["is_premarket"]:
        return False, f"Markt geschlossen ({state['status_text']})", state

    # Letzten Analyse-Zeitpunkt ermitteln
    last_analyzed_str = asset.get("last_analyzed") or asset.get("updated_at")
    if not last_analyzed_str:
        return True, "Noch nie analysiert", state

    try:
        if last_analyzed_str.endswith("Z"):
            last_analyzed_str = last_analyzed_str[:-1] + "+00:00"
        last_analyzed = datetime.fromisoformat(last_analyzed_str)
        if last_analyzed.tzinfo is None:
            last_analyzed = last_analyzed.replace(tzinfo=timezone.utc)
    except Exception:
        return True, "Ungültiger Zeitstempel -> Neu berechnen", state

    elapsed_minutes = (now_utc - last_analyzed).total_seconds() / 60.0

    # Mindestintervall prüfen
    if elapsed_minutes >= state["min_interval_minutes"]:
        return True, f"Fällig (seit {int(elapsed_minutes)}m nicht aktualisiert, Schwelle: {state['min_interval_minutes']}m)", state
    else:
        remaining = int(state["min_interval_minutes"] - elapsed_minutes)
        return False, f"Bereits aktuell (vor {int(elapsed_minutes)}m gescannt, nächste Fälligkeit in {remaining}m)", state


def filter_assets_for_run(assets: List[Dict[str, Any]], now_utc: Optional[datetime] = None, force_all: bool = False) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Teilt eine Liste von Assets in fällige und pausierte Assets auf.
    Gibt (due_assets, skipped_assets, stats_summary) zurück.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    due = []
    skipped = []

    cat_counts = {
        "CRYPTO": {"open": 0, "closed": 0, "due": 0},
        "US_STOCKS": {"open": 0, "closed": 0, "due": 0},
        "EU_STOCKS": {"open": 0, "closed": 0, "due": 0},
        "COMMODITIES_FUTURES": {"open": 0, "closed": 0, "due": 0}
    }

    for a in assets:
        sym = a.get("symbol", "")
        classification = classify_symbol(sym)
        cat = classification["category"]
        if cat not in cat_counts:
            cat_counts[cat] = {"open": 0, "closed": 0, "due": 0}

        should_scan, reason, state = should_scan_asset(a, now_utc, force_all=force_all)
        
        # Marktzustand im Asset-Objekt annotieren
        a["market_state"] = state
        a["market_category"] = cat

        if state["is_open"]:
            cat_counts[cat]["open"] += 1
        else:
            cat_counts[cat]["closed"] += 1

        if should_scan:
            cat_counts[cat]["due"] += 1
            due.append(a)
        else:
            skipped.append((a, reason))

    stats = {
        "total": len(assets),
        "due_count": len(due),
        "skipped_count": len(skipped),
        "categories": cat_counts,
        "timestamp_utc": now_utc.isoformat()
    }

    return due, skipped, stats


if __name__ == "__main__":
    import json
    from pathlib import Path
    db_file = Path(__file__).resolve().parent / "dashboard" / "market_analysis_db.json"
    if db_file.exists():
        with open(db_file, "r", encoding="utf-8") as f:
            assets = json.load(f).get("assets", [])
        due, skipped, stats = filter_assets_for_run(assets)
        print("=== GATEKEEPER STATUS TEST ===")
        print(f"Gesamt-Assets : {stats['total']}")
        print(f"Fällig        : {stats['due_count']}")
        print(f"Übersprungen  : {stats['skipped_count']}\n")
        print("Kategorien-Statistik:")
        for cat, data in stats["categories"].items():
            print(f"  • {cat:<20}: Offen={data['open']} | Geschlossen={data['closed']} | Fällig={data['due']}")
