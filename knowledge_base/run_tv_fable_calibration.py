#!/usr/bin/env python3
"""
run_tv_fable_calibration.py
===========================
Automated quantitative reverse-engineering script using Claude Fable 5.2.
Provides empirical OHLCV + TV plot values to solve for exact Pine Script formulas.
"""

import subprocess
import csv
import json
import sys
from pathlib import Path

CLAUDE_BIN = "/home/admin/.local/bin/claude"
ENV = {"PATH": "/home/admin/.local/bin:/usr/local/bin:/usr/bin:/bin"}

def get_usage():
    try:
        res = subprocess.run([CLAUDE_BIN, "-p", "/usage"], capture_output=True, text=True, env=ENV)
        return res.stdout.strip()
    except Exception as e:
        return f"Fehler: {e}"

print("=== Vorab-Prüfung der Claude Nutzungslimits ===")
print(get_usage())
print("================================================")

# Extract sample rows from BTC 4h
btc_path = "/home/admin/trading/knowledge_base/tv_exports/BTCUSD_4h_Coinbase.csv"
with open(btc_path) as f:
    btc_rows = list(csv.DictReader(f))

# Sample 1: First 20 bars
btc_sample_1 = []
for i in range(20):
    r = btc_rows[i]
    btc_sample_1.append({
        "bar": i, "t": r["time"], "o": r["open"], "h": r["high"], "l": r["low"], "c": r["close"],
        "UB": r["Upper Band"], "LB": r["Lower Band"],
        "RFE_B": r["RFE Basis"], "RFE_U": r["RFE Upper"], "RFE_L": r["RFE Lower"],
        "signals": {k: r[k] for k in ["Good Buy Signal", "Potential Buy Signal", "Good Sell Signal", "No Trade Zone", "Sell Area", "Buy Area", "Bull Alignment Ends", "Bear Alignment Ends", "Bullish OB", "Bearish OB", "Bullish OB Sweep", "Bearish OB Sweep"] if r.get(k, "") not in ("", "0", "0.0")}
    })

# Sample 2: Bars around Good Buy signal (Bar 745 to 755)
btc_sample_signal = []
for i in range(745, 756):
    r = btc_rows[i]
    btc_sample_signal.append({
        "bar": i, "t": r["time"], "o": r["open"], "h": r["high"], "l": r["low"], "c": r["close"],
        "UB": r["Upper Band"], "LB": r["Lower Band"],
        "RFE_B": r["RFE Basis"], "RFE_U": r["RFE Upper"], "RFE_L": r["RFE Lower"], "RSI": r["RSI"],
        "signals": {k: r[k] for k in ["Good Buy Signal", "Potential Buy Signal", "Good Sell Signal", "No Trade Zone", "Sell Area", "Buy Area", "Bull Alignment Ends", "Bear Alignment Ends", "Bullish OB", "Bearish OB", "Bullish OB Sweep", "Bearish OB Sweep"] if r.get(k, "") not in ("", "0", "0.0")}
    })

# Extract sample rows from AMZN 1D
amzn_path = "/home/admin/trading/knowledge_base/tv_exports/BATS_AMZN, 1D.csv"
with open(amzn_path) as f:
    amzn_rows = list(csv.DictReader(f))

amzn_sample = []
for i in range(15):
    r = amzn_rows[i]
    amzn_sample.append({
        "bar": i, "t": r["time"], "o": r["open"], "h": r["high"], "l": r["low"], "c": r["close"],
        "UB": r["Upper Band"], "LB": r["Lower Band"],
        "RFE_B": r["RFE Basis"], "RFE_U": r["RFE Upper"], "RFE_L": r["RFE Lower"],
        "signals": {k: r[k] for k in ["Good Buy Signal", "Potential Buy Signal", "Good Sell Signal", "No Trade Zone", "Sell Area", "Buy Area", "Bull Alignment Ends", "Bear Alignment Ends", "Bullish OB", "Bearish OB", "Bullish OB Sweep", "Bearish OB Sweep"] if r.get(k, "") not in ("", "0", "0.0")}
    })

prompt = f"""Du bist Claude Fable 5.2, das führende quantitative Reasoning-Modell für TradingView Pine Script & algorithmische Systemrekonstruktion.

KONTEXT & ZIEL:
Wir führen einen 100% zentimetergenauen mathematischen Abgleich zwischen den echten TradingView-CSV-Exporten unseres Setups und unserer Python-Engine ('degencoder_engine.py') durch.
Das Setup auf TradingView besteht aus:
1. 'degencoder indicator' mit den Eingabeparametern: (13, 1.8, 233)
2. 'degencoder's OB Retro'
3. 'RSI divergence (14, close)'

BEREITS ZU 100.000000% MATHEMATISCH BEWIESEN & VERIFIZIERT:
Wir haben die folgenden Formeln über alle 11 hochgeladenen CSV-Dateien (BTC, SOL, AMZN, NVDA, SPX, DAX, GOLD auf 4h und 1D) mit einer maximalen Differenz von 0.000000 verifiziert:
1. RFE Basis = ta.wma(close, 233)
2. RFE Upper = ta.wma(close, 233) + 1.618 * ta.stdev(close, 233)
3. RFE Lower = ta.wma(close, 233) - 1.618 * ta.stdev(close, 233)
4. RSI = ta.rsi(close, 14) (Wilder's Smoothing)

DIE NOCH ZU LÖSENDEN ELEMENTE (BEWEISDATEI AUS TRADINGVIEW EXPORTS):

Hier sind echte Datenreihen direkt aus den TradingView CSV-Exporten:

--- DATENSATZ 1: BTCUSD 4h (Coinbase) Bars 0 bis 19 ---
{json.dumps(btc_sample_1, indent=2)}

--- DATENSATZ 2: BTCUSD 4h Signal-Fenster (Bar 745 bis 755 mit Good Buy Signal auf Bar 750) ---
{json.dumps(btc_sample_signal, indent=2)}

--- DATENSATZ 3: BATS AMZN 1D Bars 0 bis 14 ---
{json.dumps(amzn_sample, indent=2)}

BEOBACHTETE MATHEMATISCHE EIGENSCHAFTEN DER BÄNDER (Upper Band & Lower Band):
1. Die Parameter des Indikators sind: lookback = 13, multiplier/sensitivity = 1.8.
2. An manchen Bars (z.B. Bar 9, 11, 12, 19 in BTC 4h) ist die Änderung von Upper Band exakt entgegengesetzt zur Änderung von Lower Band: d(UB) = - d(LB).
   Das beweist, dass der Mittelwert (Upper Band + Lower Band) / 2 an diesen Bars absolut konstant bleibt!
3. Die Bänder verhalten sich wie ein Range Filter (GuavaDave / DonovanWall / Dynamic Volatility Envelope).
4. Wenn der Filter raste/flach bleibt, entspricht das Level oft (High + Low) / 2 eines vorherigen Swings.

DEINE AUFGABEN ALS QUANTITATIVER ANALYTIKER:

1. MATHEMATISCHE FORMEL FÜR UPPER BAND & LOWER BAND (13, 1.8):
   Gib den exakten Pine-Script Algorithmus / Pseudocode an, der aus den OHLC-Daten die Werte von 'Upper Band' und 'Lower Band' erzeugt.
   - Wie wird die Glättungs- bzw. Range-Funktion r(13, 1.8) berechnet?
   - Wie lautet die Rekursionsformel für die Centerline / den Filter?
   - Wie werden Upper Band und Lower Band daraus abgeleitet?

2. REGELN FÜR DIE DISKRETEN SIGNALE:
   Erkläre die exakten Schwellenwerte und logischen Bedingungen für:
   - 'Good Buy Signal' (z.B. Bar 750 in BTC 4h) vs. 'Potential Buy Signal'
   - 'Good Sell Signal'
   - 'Buy Area' vs. 'Sell Area' (grüne / rote Kreuze)
   - 'No Trade Zone'
   - 'Bull Alignment Ends' & 'Bear Alignment Ends'

3. ORDER BLOCKS & SWEEPS (degencoder OB Retro):
   - Welche Kriterien bestimmen die Entstehung eines 'Bullish OB' und 'Bearish OB'?
   - Wann wird ein 'Bullish OB Sweep' bzw. 'Bearish OB Sweep' ausgelöst?

4. KONKRETER PYTHON-CODE FÜR 'degencoder_engine.py':
   Schreibe den drop-in Python-Code für die optimierte Funktion 'calculate_degencoder_bands_v2' und 'detect_degencoder_signals_v2', sodass unser nativer Python-Code 1:1 identisch zu TradingView rechnet.

Antworte mathematisch rigoros, präzise und direkt umsetzbar.
"""

output_prompt_file = Path("/home/admin/trading/knowledge_base/tv_fable_prompt.txt")
output_prompt_file.write_text(prompt, encoding="utf-8")
print(f"Prompt gespeichert ({len(prompt)} Zeichen)")

print("\n🚀 Sende Kalibrierungs-Auftrag an Claude Fable 5.2...")
res = subprocess.run([CLAUDE_BIN, "-p", "--model", "claude-fable-5-2", prompt], capture_output=True, text=True, env=ENV)

if res.returncode != 0:
    print(f"Fehler bei Claude Fable: {res.stderr}")
    sys.exit(res.returncode)

output_text = res.stdout.strip()
print("\n=== Antwort von Claude Fable 5.2 erhalten ===")
print(output_text[:600] + "\n... [Vollständiger Bericht wird gespeichert] ...")

result_file = Path("/home/admin/trading/knowledge_base/tv_fable_calibration_report.md")
result_file.write_text(output_text, encoding="utf-8")
print(f"\nBericht erfolgreich gespeichert in: {result_file}")

print("\n=== Nach-Prüfung der Claude Nutzungslimits ===")
print(get_usage())
print("================================================")
