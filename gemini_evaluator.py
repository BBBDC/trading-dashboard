#!/usr/bin/env python3
"""
TradingView Super-Analyst – Multi-Tier Gemini AI Evaluation Engine.
Unterstützt:
1. Stufe 1 (Primary Pro): Gemini 3.8 Flash (High) / Gemini 4 über aktives Pro-Abo (agy CLI) oder API-Key
2. Stufe 2 (Fallback AI): Gemini 2.5 Flash als schneller, robuster KI-Fallback
3. Stufe 3 (Fallback Math Core): Vollständige quantitative Confluence-Engine (SMC & Wyckoff VSA)

Garantiert, dass der 24/7 Raspberry Pi Markt-Scan unter allen Umständen zuverlässig läuft.
"""

import os
import sys
import json
import time
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "gemini_config.json"
AGY_BIN = Path("/home/admin/.local/bin/agy")

DEFAULT_CONFIG = {
    "enabled": True,
    "primary_model": "gemini-3.8-flash-high",
    "fallback_model": "gemini-2.5-flash",
    "use_pro_subscription": True,
    "api_key": "",
    "temperature": 0.2,
    "batch_size": 8,
    "timeout_seconds": 45,
    "comment": "primary_model: 'gemini-3.8-flash-high' oder 'gemini-4'. use_pro_subscription: nutzt automatisch dein angemeldetes Google Pro-Abo via CLI. api_key: optional falls du einen Google AI Studio Key nutzen möchtest."
}


def load_config():
    if not CONFIG_FILE.exists():
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Standardwerte für neue Felder ergänzen
            for k, v in DEFAULT_CONFIG.items():
                if k not in data:
                    data[k] = v
            return data
    except Exception:
        return DEFAULT_CONFIG


def get_api_key():
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()
    conf = load_config()
    cfg_key = conf.get("api_key")
    if cfg_key and cfg_key.strip() and not cfg_key.startswith("DEIN_"):
        return cfg_key.strip()
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        k = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                        if k:
                            return k
        except Exception:
            pass
    return None


def extract_json_from_text(raw_text):
    """Extrahiert sauberes JSON aus Antworten (auch wenn in ```json Code-Blöcken)."""
    if not raw_text:
        return None
    text = raw_text.strip()
    if "```" in text:
        # Extrahiere Block zwischen ```json und ```
        lines = text.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.strip().startswith("```"):
                if in_block:
                    break
                else:
                    in_block = True
                    continue
            if in_block:
                json_lines.append(line)
        if json_lines:
            text = "\n".join(json_lines).strip()
    
    # Suche erstes '[' oder '{' und letztes ']' oder '}'
    first_sq = text.find('[')
    last_sq = text.rfind(']')
    first_cu = text.find('{')
    last_cu = text.rfind('}')

    if first_sq != -1 and last_sq != -1 and (first_cu == -1 or first_sq < first_cu):
        text = text[first_sq:last_sq + 1]
    elif first_cu != -1 and last_cu != -1:
        text = text[first_cu:last_cu + 1]

    try:
        return json.loads(text)
    except Exception as e:
        return None


def call_gemini_via_pro_cli(prompt, model="gemini-3.8-flash-high", timeout=50):
    """
    Ruft das Google Gemini Modell direkt über das angemeldete Google Pro-Abo (agy CLI) auf.
    Benötigt KEINEN separaten API-Key und nutzt das aktive Pro-Kontingent.
    """
    if not AGY_BIN.exists():
        return None, f"agy CLI unter {AGY_BIN} nicht gefunden."

    cmd = [
        str(AGY_BIN),
        "-p", prompt,
        "--model", model,
        "--disable-slash-commands"
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if res.returncode != 0:
            err = res.stderr.strip() or f"CLI Exit-Code {res.returncode}"
            return None, f"Pro CLI Fehler ({model}): {err[:180]}"

        parsed = extract_json_from_text(res.stdout)
        if parsed:
            return parsed, None
        else:
            return None, f"Antwort von {model} konnte nicht als JSON geparst werden."

    except subprocess.TimeoutExpired:
        return None, f"Pro CLI Timeout ({timeout}s) bei {model}."
    except Exception as e:
        return None, f"Pro CLI Ausführungsfehler: {e}"


def call_gemini_via_rest_api(prompt, model="gemini-2.5-flash", api_key=None, timeout=30):
    """
    Ruft die offizielle Google Gemini REST API über einen API-Key auf.
    Schlank, extrem schnell und standardbibliothek-basiert.
    """
    if not api_key:
        api_key = get_api_key()
    if not api_key:
        return None, "Kein GEMINI_API_KEY für REST-API verfügbar."

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if not candidates:
                return None, "Keine Kandidaten von Gemini REST API erhalten."
            txt = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            parsed = extract_json_from_text(txt)
            if parsed:
                return parsed, None
            return None, "Gemini REST API: Ungültiges JSON in Antwort."
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="ignore")[:160]
        return None, f"HTTP {e.code} bei {model}: {err}"
    except Exception as e:
        return None, f"REST API Verbindungsfehler ({model}): {e}"


def build_analysis_prompt(assets_batch):
    return f"""Du bist der "TradingView Super-Analyst", ein institutioneller Multi-Timeframe Krypto- & Aktien-Trading-Experte.
Deine Strategie basiert auf:
1. Smart Money Concepts (SMC): Fair Value Gaps (FVG), Order Blocks (OB), Liquidity Sweeps
2. Fibonacci Golden Pocket (0.618 - 0.650 Retracement)
3. degencoder Trend- & Volatilitätsbänder (13 EMA, 1.8 ATR, 233 EMA Trendfilter)
4. Wyckoff Volume Spread Analysis (VSA): Climax, Absorption, No Supply / No Demand
5. Multi-Timeframe RSI Divergenzen (1D, 8h, 4h)

Hier sind die aktuellen Marktdaten und technischen Messungen für {len(assets_batch)} Assets:

{json.dumps(assets_batch, indent=2, ensure_ascii=False)}

AUFGABE:
Analysiere jedes Asset gründlich. Berücksichtige übergeordnete Trends (1D) vs untergeordnete Einstiege (4h/8h).
Erstelle für JEDES Asset im Input eine exakte Handelsbewertung.

Antworte AUSSCHLIESSLICH als JSON-Array von Objekten mit exakt diesem Schema:
[
  {{
    "symbol": "TICKER (exakt wie im Input)",
    "signal": "LONG" | "SHORT" | "NEUTRAL",
    "score": 0 bis 100 (Conviction-Score. >85% nur bei echter High-Conviction Confluence!),
    "setup_name": "z.B. Hypothese 1: SMC Golden Confluence Reversal | Hypothese 2: Trend Continuation | Hypothese 3: Wyckoff Fakeout | Beobachten",
    "crv": 2.5,
    "entry_range": [min_entry, max_entry],
    "stop_loss": stop_loss_kurs,
    "take_profit_1": ziel1,
    "take_profit_2": ziel2,
    "reasons": [
      "Stichpunkt 1 mit Indikator-Fakt",
      "Stichpunkt 2 mit SMC/GP Level",
      "Stichpunkt 3 mit RSI/VSA Bestätigung"
    ],
    "analyst_note": "Prägnante, professionelle deutsche Chart-Interpretation der KI für das Dashboard (2-4 Sätze)."
  }}
]
"""


def evaluate_batch_with_cascade(assets_batch):
    """
    Führt die 3-Stufen-Kaskade für einen Asset-Batch aus:
    Stufe 1: Primäres Pro-Modell (z.B. gemini-3.8-flash-high oder gemini-4)
    Stufe 2: Fallback-KI-Modell (z.B. gemini-2.5-flash)
    Stufe 3: Rückgabe None -> Caller nutzt quantitative Confluence-Engine
    """
    conf = load_config()
    if not conf.get("enabled", True):
        return None, "KI-Auswertung in gemini_config.json deaktiviert", "disabled"

    primary_model = conf.get("primary_model", "gemini-3.8-flash-high")
    fallback_model = conf.get("fallback_model", "gemini-2.5-flash")
    timeout = conf.get("timeout_seconds", 45)
    use_pro_sub = conf.get("use_pro_subscription", True)
    api_key = get_api_key()

    prompt = build_analysis_prompt(assets_batch)

    # ========================================================
    # STUFE 1: Primäres Pro-Modell (Gemini 3.8 High / Gemini 4)
    # ========================================================
    print(f" (Stufe 1: {primary_model})...", end="", flush=True)

    res = None
    err = None

    # Zuerst Pro-Abo via CLI versuchen (oder via REST falls API-Key da ist)
    if api_key:
        res, err = call_gemini_via_rest_api(prompt, model=primary_model, api_key=api_key, timeout=timeout)
    elif use_pro_sub:
        res, err = call_gemini_via_pro_cli(prompt, model=primary_model, timeout=timeout)
    else:
        err = "Weder API-Key noch Pro-Subscription konfiguriert."

    if res and isinstance(res, list) and len(res) > 0:
        return res, None, f"{primary_model} [Pro Abo]"

    # ========================================================
    # STUFE 2: Fallback-KI (Gemini 2.5 Flash)
    # ========================================================
    print(f"\n      ⚠️ Stufe 1 ({primary_model}) nicht erfolgreich ({err}) -> Aktiviere Stufe 2 ({fallback_model})...", end="", flush=True)

    if api_key:
        res, err = call_gemini_via_rest_api(prompt, model=fallback_model, api_key=api_key, timeout=25)
    elif use_pro_sub:
        res, err = call_gemini_via_pro_cli(prompt, model=fallback_model, timeout=30)

    if res and isinstance(res, list) and len(res) > 0:
        return res, None, f"{fallback_model} [Fallback AI]"

    # ========================================================
    # STUFE 3: Fallback auf quantitative Confluence-Engine
    # ========================================================
    print(f"\n      ⚠️ Stufe 2 ({fallback_model}) ebenfalls nicht verfügbar ({err}) -> Aktiviere Stufe 3 (Mathematische Confluence-Engine)...", end="", flush=True)
    return None, err, "quantitative_confluence [Math Core]"


if __name__ == "__main__":
    print("=" * 65)
    print("Test: Gemini Multi-Tier Kaskaden-Evaluator (Pro Abo & Fallback)")
    print("=" * 65)
    conf = load_config()
    print(f"Primäres Modell : {conf.get('primary_model')}")
    print(f"Fallback Modell : {conf.get('fallback_model')}")
    print(f"Pro-Subscription: {'Aktiv (via agy CLI)' if conf.get('use_pro_subscription') else 'Deaktiviert'}")
    print(f"API-Key Status  : {'Vorhanden' if get_api_key() else 'Nicht gesetzt (nutzt Pro-Abo CLI)'}")
    print("-" * 65)

    test_sample = [
        {
            "symbol": "NASDAQ:MU",
            "name": "Micron Technology",
            "category": "Halbleiter",
            "current_price": 878.84,
            "1D": {"trend": "BEARISH", "rsi": 34.0, "in_gp": True, "channel": "Oversold Band", "divs": ["Reguläre Bullische Divergenz (Reversal)"]},
            "4h": {"trend": "BULLISH", "rsi": 42.0, "vsa": "Stopping Volume", "divs": ["Bullische Divergenz"]}
        }
    ]

    print("Starte Test-Evaluation für 1 Test-Asset...")
    results, error, tier_used = evaluate_batch_with_cascade(test_sample)

    if results:
        print(f"\n✅ ERFOLG! Ausgeführt über: {tier_used}")
        first = results[0]
        print(f"Asset : {first.get('name')} ({first.get('symbol')})")
        print(f"Signal: {first.get('signal')} | Score: {first.get('score')}%")
        print(f"Setup : {first.get('setup_name')} | CRV: {first.get('crv')}")
        print(f"Note  : {first.get('analyst_note')}")
    else:
        print(f"\n⚠️ Kaskaden-Rückfall auf Stufe 3 (Grund: {error})")
    print("=" * 65)
