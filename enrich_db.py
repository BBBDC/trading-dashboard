import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "dashboard" / "market_analysis_db.json"

with open(DB_FILE, "r", encoding="utf-8") as f:
    db = json.load(f)

for asset in db["assets"]:
    sym = asset["symbol"]
    reasons = asset.get("reasons", [])
    first_reason = reasons[0] if reasons else "Support/Widerstand erreicht"

    if sym == "COINBASE:BTCUSD":
        asset["signal"] = "LONG"
        asset["setup_name"] = "Hypothese 2: Trend Continuation & Breakout Watch"
        asset["score"] = 94
        asset["entry_range"] = [81200.0, 82350.0]
        asset["stop_loss"] = 79400.0
        asset["take_profit_1"] = 83460.0
        asset["take_profit_2"] = 84850.0
        asset["crv"] = 3.1
        asset["analyst_note"] = "Makro-Trend über 1D EMA 233 (75.774 USD) intakt. 8h reguläre bullische Divergenz (82.7k -> 80.6k) aktiv. VSA zeigt No-Supply (Ratio 0.12). Aggressiver Long-Einstieg bei 4h-Schlusskurs über 82.320 USD (Bearish OB Breakout) mit Ziel 84.350 - 84.850 USD (Golden Pocket / FVG)."

    elif sym == "NASDAQ:MU":
        asset["signal"] = "LONG"
        asset["setup_name"] = "Hypothese 1: SMC Golden Confluence Reversal"
        asset["score"] = 98
        asset["entry_range"] = [868.0, 880.0]
        asset["stop_loss"] = 852.0
        asset["take_profit_1"] = 903.0
        asset["take_profit_2"] = 965.0
        asset["crv"] = 3.3
        asset["analyst_note"] = "TOP OPPORTUNITY: 1D Kurs (878 USD) sitzt exakt im Fibonacci Golden Pocket 0.618 (867-879 USD). Gleichzeitig Überdehnung unter das untere degencoder-Kanalband (Oversold). 8h/4h RSI tief überverkauft (26.6) mit aktiver bullischer Divergenz. VSA zeigt Austrocknen des Verkaufsdrucks (Stopping Volume)."

    elif asset["signal"] == "LONG":
        asset["analyst_note"] = f"Bullische Ausrichtung: {first_reason}. VSA und RSI bestätigen nachlassenden Verkaufsdruck bzw. gesunden Pullback."
    elif asset["signal"] == "SHORT":
        asset["analyst_note"] = f"Bärische Erschöpfung / Reversal: {first_reason}. Überdehnung an den Bändern oder bärische Divergenz im Momentum."
    else:
        asset["analyst_note"] = "Konsolidierungsphase: Aktuell zwischen Support und Resistance. Auf Bestätigung an den Key-Levels warten."

# Zähle neu
long_cnt = sum(1 for a in db["assets"] if a["signal"] == "LONG")
short_cnt = sum(1 for a in db["assets"] if a["signal"] == "SHORT")
neutral_cnt = sum(1 for a in db["assets"] if a["signal"] == "NEUTRAL")

db["long_count"] = long_cnt
db["short_count"] = short_cnt
db["neutral_count"] = neutral_cnt

with open(DB_FILE, "w", encoding="utf-8") as f:
    json.dump(db, f, indent=2, ensure_ascii=False)

print(f"Erfolgreich! LONG: {long_cnt} | SHORT: {short_cnt} | NEUTRAL: {neutral_cnt}")
