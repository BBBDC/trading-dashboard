#!/usr/bin/env python3
"""
TradingView Super-Analyst – Gemini AI Evaluation Engine.
Interpretiert Multi-Timeframe-Marktstrukturen, SMC, Wyckoff VSA und Golden Pocket
vollständig durch das Google Gemini KI-Modell (z.B. gemini-2.5-flash).
Beinhaltet automatischen Fallback auf das quantitative Confluence-Regelwerk,
falls kein API-Key hinterlegt oder das Quota erschöpft ist.
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "gemini_config.json"

DEFAULT_CONFIG = {
    "enabled": True,
    "api_key": "",
    "model": "gemini-2.5-flash",
    "temperature": 0.2,
    "batch_size": 8
}


def load_config():
    if not CONFIG_FILE.exists():
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG


def get_api_key():
    # 1. Aus Umgebungsvariable
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()
    # 2. Aus Konfigurationsdatei
    conf = load_config()
    cfg_key = conf.get("api_key")
    if cfg_key and cfg_key.strip():
        return cfg_key.strip()
    # 3. Aus .env Datei
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return None


def call_gemini_api(prompt, model="gemini-2.5-flash", temperature=0.2):
    """Führt einen direkten, schlanken REST-Call an die Google Gemini API aus."""
    api_key = get_api_key()
    if not api_key:
        return None, "Kein GEMINI_API_KEY gefunden."

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json"
        }
    }

    req_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_bytes,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if not candidates:
                return None, "Keine Antwort-Kandidaten von Gemini erhalten."
            
            first = candidates[0]
            content_parts = first.get("content", {}).get("parts", [])
            if not content_parts:
                return None, "Leere Antwort von Gemini erhalten."

            raw_text = content_parts[0].get("text", "")
            parsed = json.loads(raw_text)
            return parsed, None

    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        return None, f"Gemini HTTP Fehler {e.code}: {err_msg[:200]}"
    except urllib.error.URLError as e:
        return None, f"Gemini Verbindungsfehler: {e.reason}"
    except json.JSONDecodeError as e:
        return None, f"Gemini JSON Parsing Fehler: {e}"
    except Exception as e:
        return None, f"Unerwarteter Gemini Fehler: {e}"


def evaluate_batch_with_gemini(assets_batch):
    """
    Übergibt eine Liste von Assets mit ihren berechneten technischen Indikatoren an Gemini
    und erhält eine fundierte KI-Bewertung mit Einstufung, Score und Begründung zurück.
    """
    conf = load_config()
    if not conf.get("enabled", True):
        return None, "Gemini KI-Bewertung in gemini_config.json deaktiviert."

    api_key = get_api_key()
    if not api_key:
        return None, "Kein Gemini API-Key vorhanden."

    model = conf.get("model", "gemini-2.5-flash")
    temperature = conf.get("temperature", 0.2)

    prompt = f"""Du bist der "TradingView Super-Analyst", ein institutioneller Multi-Timeframe Krypto- & Aktien-Trading-Experte.
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

    return call_gemini_api(prompt, model=model, temperature=temperature)


if __name__ == "__main__":
    print("Prüfe Gemini-Konfiguration...")
    key = get_api_key()
    if key:
        print(f"✅ Gemini API-Key gefunden (Endet auf ...{key[-4:]})")
        print("Teste Verbindung mit kurzem Probe-Prompt...")
        res, err = call_gemini_api("Antworte mit einem JSON: {\"status\": \"ok\", \"model\": \"gemini-2.5-flash\"}")
        if res:
            print("✅ Gemini API erfolgreich angebunden:", res)
        else:
            print("⚠️ Gemini Test fehlgeschlagen:", err)
    else:
        print("ℹ️ Kein GEMINI_API_KEY gefunden.")
        print("   -> Setze deinen Key in /home/admin/trading/gemini_config.json oder als Umgebungsvariable.")
        print("   -> Solange kein Key vorhanden ist, nutzt die Pipeline die mathematische Confluence-Engine.")
