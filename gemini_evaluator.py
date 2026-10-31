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
import requests
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


def call_gemini_via_pro_cli(prompt, model="gemini-3.8-flash-high", timeout=120):
    """
    Ruft das Google Gemini Modell direkt über das angemeldete Google Pro-Abo (agy CLI) auf.
    Prüft prioritär, ob das dedizierte 2. Google-Konto (/home/admin/.gemini_trading) autorisiert ist.
    Falls ja: Nutzt exklusiv das 2. Google-Konto (Account 2: pokeulm@gmail.com).
    Falls nein: Nutzt das primäre Google-Konto (Account 1).
    """
    if not AGY_BIN.exists():
        return None, f"agy CLI unter {AGY_BIN} nicht gefunden."

    # Modell für die agy CLI (User-Vorgabe: Immer Gemini 3.8 Flash Pro High)
    cli_model = "gemini-3.8-flash-high"

    cmd = [
        str(AGY_BIN),
        "-p", prompt,
        "--model", cli_model,
        "--disable-slash-commands"
    ]

    env = os.environ.copy()
    dedicated_trading_home = Path("/home/admin/.gemini_trading")
    dedicated_token = dedicated_trading_home / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
    if dedicated_token.exists():
        env["HOME"] = str(dedicated_trading_home)
        acc_label = "Account 2 (Trading Pro)"
    else:
        acc_label = "Account 1 (Coding Pro)"

    try:
        res = subprocess.run(cmd, cwd="/tmp", capture_output=True, text=True, timeout=timeout, env=env)
        if res.returncode != 0:
            err = res.stderr.strip() or f"CLI Exit-Code {res.returncode}"
            return None, f"Pro CLI Fehler ({cli_model} via {acc_label}): {err[:180]}"

        parsed = extract_json_from_text(res.stdout)
        if parsed:
            return parsed, None
        else:
            return None, f"Antwort von {cli_model} via {acc_label} konnte nicht als JSON geparst werden."

    except subprocess.TimeoutExpired:
        return None, f"Pro CLI Timeout ({timeout}s) bei {cli_model} ({acc_label})."
    except Exception as e:
        return None, f"Pro CLI Ausführungsfehler: {e}"


def call_gemini_via_rest_api(prompt, model="gemini-3.5-flash", api_key=None, timeout=25):
    """
    Ruft die Google Gemini REST API über einen konkreten API-Key auf.
    """
    if not api_key:
        try:
            from gemini_quota_tracker import get_active_api_key
            api_key, _ = get_active_api_key()
        except Exception:
            api_key = get_api_key()
    if not api_key:
        return None, "Kein GEMINI_API_KEY für REST-API verfügbar."

    target_model = model or "gemini-3.5-flash"
    models_to_try = [
        (target_model, 1024),
        (target_model, 0)
    ]

    last_err = None
    for cur_model, cur_budget in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{cur_model}:generateContent?key={api_key}"
        gen_config = {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
        if cur_budget is not None and cur_budget > 0:
            gen_config["thinkingConfig"] = {"thinkingBudget": cur_budget}

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": gen_config
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
                usage = data.get("usageMetadata", {})
                tokens = usage.get("totalTokenCount", 0)
                try:
                    from gemini_quota_tracker import record_successful_request
                    record_successful_request(api_key, tokens)
                except Exception:
                    pass

                candidates = data.get("candidates", [])
                if not candidates:
                    continue
                txt = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                parsed = extract_json_from_text(txt)
                if parsed and isinstance(parsed, list) and len(parsed) > 0:
                    return parsed, None
        except urllib.error.HTTPError as e:
            raw_body = e.read().decode("utf-8", errors="ignore")
            err_body = raw_body[:300]
            last_err = f"HTTP {e.code} ({cur_model}): {err_body}"
            if e.code == 429:
                try:
                    import re
                    from gemini_quota_tracker import record_quota_exhausted
                    m_delay = re.search(r"retryDelay\":\s*\"?(\d+)", raw_body)
                    sec = int(m_delay.group(1)) if m_delay else 38000
                    record_quota_exhausted(api_key, err_body, retry_seconds=sec)
                except Exception:
                    pass
                break
            if e.code in (404, 400):
                continue
            break
        except Exception as e:
            last_err = str(e)
            break

    return None, f"REST API Fehler: {last_err}"


def call_gemini_via_key_pool(prompt, model="gemini-3.8-flash", timeout=40):
    """
    Intelligenter Multi-Key Pool Aufruf:
    Iteriert durch alle verfügbaren API-Keys im Pool.
    Tritt bei einem Key ein HTTP 429 (Quota Limit) auf, wird dieser Key
    als erschöpft markiert und der nächste Key im Pool wird SOFORT ausprobiert.
    """
    try:
        from gemini_quota_tracker import get_all_available_keys_in_pool
        keys_pool = get_all_available_keys_in_pool()
    except Exception:
        k = get_api_key()
        keys_pool = [(k, f"{k[:6]}...{k[-4:]}")] if k else []

    if not keys_pool:
        return None, "Keine API-Keys im Pool konfiguriert.", "no_keys"

    last_err = None
    for key_str, masked in keys_pool:
        print(f" (Key: {masked})...", end="", flush=True)
        res, err = call_gemini_via_rest_api(prompt, model=model, api_key=key_str, timeout=timeout)
        if res and isinstance(res, list) and len(res) > 0:
            return res, None, masked
        last_err = err
        print(f" [Failover auf nächsten Key]...", end="", flush=True)

    return None, last_err, "exhausted"


def evaluate_trade_post_mortem(trade_data):
    """
    Führt eine tiefgehende KI-Post-Mortem-Analyse eines geschlossenen Trades durch.
    Nutzt prioritär Gemini 3.8 Flash via Account 2 (Google Pro-Abo CLI),
    mit automatischem Fallback auf den Free Key-Pool und deterministische Regeln.
    """
    sym = trade_data.get("symbol", "")
    name = trade_data.get("name", sym)
    direction = trade_data.get("direction", "LONG")
    setup = trade_data.get("setup_name", "High-Conviction Confluence")
    category = trade_data.get("category", "Asset")
    entry_price = float(trade_data.get("entry_price", 0.0))
    exit_price = float(trade_data.get("exit_price", 0.0))
    entry_time = str(trade_data.get("entry_time", ""))
    exit_time = str(trade_data.get("exit_time", ""))
    days = float(trade_data.get("holding_days", 0.0))
    raw_pnl = float(trade_data.get("realized_pnl_pct", 0.0))
    lev_pnl = float(trade_data.get("realized_pnl_leveraged_pct", 0.0))
    lev = int(trade_data.get("leverage", 1))
    exit_reason = str(trade_data.get("exit_reason", ""))
    entry_reason = str(trade_data.get("entry_reason", ""))
    highest = float(trade_data.get("highest_price", entry_price))
    lowest = float(trade_data.get("lowest_price", entry_price))

    verdict = "WIN" if raw_pnl > 0 else ("LOSS" if raw_pnl < 0 else "BREAKEVEN")

    prompt = f"""Du bist ein Senior Prop-Desk Chef-Risikomanager und Trading-Coach mit 20 Jahren Markterfahrung.
Analysiere diesen soeben abgeschlossenen Trade unseres autonomen Handelsportfolios objektiv und schonungslos:
- Asset: {name} ({sym}) | Sektor: {category}
- Richtung: {direction} | Setup-Hypothese: {setup}
- Einstieg: {entry_price:,.4f} am {entry_time} (Begründung: {entry_reason})
- Ausstieg: {exit_price:,.4f} am {exit_time} nach {days:.1f} Tagen
- Ausstiegsgrund: {exit_reason}
- Realisierter PnL: {raw_pnl:+.2f}% unhebelt ({lev_pnl:+.2f}% bei {lev}x Hebel)
- Kursverlauf während Trade: Tiefstkurs {lowest:,.4f}, Höchstkurs {highest:,.4f}

Erstelle ein strukturiertes JSON-Post-Mortem.
Antworte AUSSCHLIESSLICH im folgenden JSON-Format:
{{
  "verdict": "{verdict}",
  "driver": "Konkrete Ursache für Erfolg oder Misserfolg (1 prägnanter deutscher Satz)",
  "technical_warning": "Welches Chart-/Indikator-Signal (z.B. Divergenz, Volumen, HTF-Widerstand, Support-Bruch) hätte früher gewarnt oder den Einstieg besser getimt?",
  "actionable_rule": "Eine glasklare, bindende Handlungsregel für künftige Trades in dieser Assetklasse / bei diesem Setup",
  "recommended_leverage_adjustment": {-2 if lev_pnl < -15 else (-1 if lev_pnl < 0 else (1 if lev_pnl > 20 else 0))},
  "summary_text": "Prägnanter Lernsatz für das Gedächtnis (1-2 Sätze)"
}}
"""
    # 1. Google Pro-Abo CLI mit 3.8 Flash High (Account 2: pokeulm@gmail.com)
    try:
        res, err = call_gemini_via_pro_cli(prompt, model="gemini-3.8-flash-high", timeout=90)
        if res and isinstance(res, dict) and "driver" in res:
            return res
    except Exception:
        pass

    # 2. Key-Pool Failover (3.8 Flash High)
    try:
        res, err, _ = call_gemini_via_key_pool(prompt, model="gemini-3.8-flash", timeout=35)
        if res and isinstance(res, dict) and "driver" in res:
            return res
    except Exception:
        pass

    # 3. Deterministischer Fallback
    if verdict == "WIN":
        return {
            "verdict": "WIN",
            "driver": f"Erfolgreicher {direction}-Trade: Setup '{setup}' bestätigte die übergeordnete Konfluenz.",
            "technical_warning": "Keine negativen Divergenzen während des Laufs aufgetreten.",
            "actionable_rule": f"Bei {category} Gewinne weiter konsequent mit Trailing-Stops schützen.",
            "recommended_leverage_adjustment": 0,
            "summary_text": f"Erfolgreicher {direction}-Trade auf {name} (+{raw_pnl:.1f}%, +{lev_pnl:.1f}% bei {lev}x). HTF-Ziel erreicht."
        }
    else:
        return {
            "verdict": "LOSS",
            "driver": f"Setup '{setup}' durch {exit_reason} invalidiert.",
            "technical_warning": "Fehlende Bestätigung im Volumen oder vorzeitiger Strukturbruch im niedrigen Timeframe.",
            "actionable_rule": f"Bei {category} Hebel bei ähnlicher Marktstruktur konservativer wählen und Bestätigung abwarten.",
            "recommended_leverage_adjustment": -1,
            "summary_text": f"Verlusttrade auf {name} ({raw_pnl:.1f}%, {lev_pnl:.1f}% bei {lev}x). Grund: {exit_reason}."
        }


def build_analysis_prompt(assets_batch):
    try:
        from portfolio_engine import get_memory_summary_for_ai_prompt
        mem_ctx = get_memory_summary_for_ai_prompt(assets_batch)
    except Exception:
        mem_ctx = ""

    memory_block = f"""
5. HISTORISCHES GEDÄCHTNIS & AUS VERGANGENEN TRADES GELERNT:
{mem_ctx}
""" if mem_ctx else ""

    return f"""Du agierst als hochgradig professioneller Trader, Senior-Analyst und Portfolio-Manager mit mehr als 15 Jahren institutioneller Tradingerfahrung an den globalen Finanzmärkten (Equities, Crypto, Commodities, Forex) sowie als Chef-Risikomanager eines führenden Prop-Trading-Desks ("TradingView Super-Analyst").
Dein oberstes Dogma lautet: KAPITALERHALT. Ein schlechter Trade vernichtet echtes Geld; ein verpasster Trade kostet absolut gar nichts.
Du führst die Analyse mit der unnachgiebigen Selektivität und Disziplin eines erfahrenen Markt-Veteranen durch: Du jagst keinen Kursen hinterher, lässt dich von kurzfristigem Marktrauschen (Noise) niemals beirren und empfiehlst Einstiege nur dort, wo asymmetrische Chance-Risiko-Verhältnisse (CRV >= 2.5:1) und mehrfache institutionelle Konfluenzen echtes Trading-Edge bieten.

STRENGSTE INSTITUTIONELLE FILTERREGELN (BITTE GENAUESTENS EINHALTEN):
1. STRIKTE TRENNUNG: MAKRO-REGIME (1W/1D/3D) VS. TAKTISCHES TIMING (4h/1h) – KEIN BIAS-FLIPPING / WHIPSAWS:
   - Ein gesunder Rücksetzer (Pullback) auf 4h oder 1h in einem intakten 1D-Bullenmarkt (über 233 EMA) ist NIEMALS ein "SHORT"-Signal!
   - Solange der 1D-Trend intakt ist, bleibt der Makro-Trend BULLISCH. Wenn der Kurs auf 4h/1h konsolidiert oder zurücksetzt, vergebe "NEUTRAL" mit Setup: "Beobachten / Lauerstellung am Support (Buy the Dip)" und nenne die geplante Entry-Zone (z.B. Golden Pocket oder FVG).
   - Umgekehrt im 1D-Bärenmarkt (unter 233 EMA): 4h/1h Erholungsbewegungen sind Bärenmarktrallyes und NIEMALS ein "LONG"-Signal. Einstufung bleibt "NEUTRAL" mit Setup: "Beobachten / Warten auf Short-Trigger am Widerstand".
   - Ein Trendwechsel von Bullisch zu Bärisch ist AUSSCHLIESSLICH bei nachgewiesenem Bruch der 1D-Marktstruktur (Tagesschlusskurs unter 233 EMA und Bruch des letzten 1D Swing-Lows = CHoCH) zulässig!
   - Beachte das Feld 'previous_signal': Ein professionelles Handelssystem wechselt seine Einstufung nicht bei jeder 1h/4h-Schwankung. Hohe Trägheit (Hysterese) schützt vor Whipsaws!

2. KRITERIEN FÜR EIN ECHTES "LONG"-SIGNAL (SEHR STRIKT):
   - Makro-Trend (1D & 1W) ist bullisch (über 233 EMA) ODER der Kurs sitzt exakt im 1D Fibonacci Golden Pocket (0.618 - 0.650) mit bestätigter Wyckoff-Absorption.
   - Kein Chasing: Niemals Long gehen, wenn der 4h-Kurs bereits am oberen degencoder-Band (Overbought) oder der RSI > 62 ist.
   - Konfluenz & Timing-Trigger: Es muss auf 1h oder 4h eine aktive bullische Divergenz ODER Wyckoff "No Supply / Stopping Volume" vorliegen.
   - Mindest-CRV (Chance-Risiko-Verhältnis) >= 2.5:1 zum nächsten signifikanten FVG / Widerstand.
   - Score >= 88 % wird NUR bei makelloser 3-facher Konfluenz vergeben.

3. KRITERIEN FÜR EIN ECHTES "SHORT"-SIGNAL (SEHR STRIKT):
   - Makro-Trend ist bärisch (unter 233 EMA) ODER klare Top-Erschöpfung am oberen 1D-Kanalband (Overbought) mit bestätigter bärischer Divergenz auf 1h/4h.
   - Niemals Short gegen einen starken intakten 1D-Bullenmarkt.
   - Mindest-CRV >= 2.5:1.

4. STANDARD-EINSTUFUNG BEI UNKLARER LAGE:
   - 70–80 % aller Marktphasen gehören ins "NEUTRAL (Beobachten)".
   - Im Zweifel MUSS das Signal IMMER "NEUTRAL" sein (Score 40–55%).

5. STOP-LOSS & TARGETS:
   - Der Stop-Loss muss strukturell begründet sein (knapp unterhalb des Golden Pocket / Swing-Lows / FVG), niemals willkürlich.
   - Take Profit 1 & 2 müssen an echten Liquiditätszonen oder gegnerischen FVGs liegen.
{memory_block}
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
    "score": 0 bis 100 (Streng konservativ! >85% nur für absolute Top-Tier Setups),
    "setup_name": "z.B. Hypothese 1: SMC Golden Confluence Reversal | Hypothese 2: Trend Continuation | Beobachten / Konsolidierung",
    "crv": 2.5,
    "entry_range": [min_entry, max_entry],
    "stop_loss": stop_loss_kurs,
    "take_profit_1": ziel1,
    "take_profit_2": ziel2,
    "reasons": [
      "Strikte Begründung 1 (HTF Struktur)",
      "Strikte Begründung 2 (SMC / FVG / GP Level)",
      "Strikte Begründung 3 (VSA / Divergenz)"
    ],
    "analyst_note": "Fundierte, professionelle deutsche Chart-Interpretation mit Fokus auf Risiko, Validierung und Trigger-Level (2-4 Sätze)."
  }}
]
"""


_health_cache = {
    "last_checked": 0,
    "model_38_healthy": False,
    "message": ""
}


def probe_key_pool_model_38_health(timeout=3.5):
    """
    Führt vor dem KI-Scan eine kurze Prüfung (Micro-Ping) durch, ob die kostenlosen API-Keys
    aktuell gemini-3.8-flash ohne 503-Überlastung / Timeout verarbeiten können.
    Ergebnis wird für 120 Sekunden gecached, um aufeinanderfolgende Batches nicht zu verlangsamen.
    """
    now = time.time()
    if now - _health_cache["last_checked"] < 120:
        return _health_cache["model_38_healthy"], _health_cache["message"]

    try:
        from gemini_quota_tracker import get_all_available_keys_in_pool
        keys_pool = get_all_available_keys_in_pool()
    except Exception:
        k = get_api_key()
        keys_pool = [(k, f"{k[:6]}...{k[-4:]}")] if k else []

    if not keys_pool:
        _health_cache["last_checked"] = now
        _health_cache["model_38_healthy"] = False
        _health_cache["message"] = "Keine Keys verfügbar"
        return False, _health_cache["message"]

    # Teste Keys aus dem Pool mit einem schnellen Ping auf gemini-3.8-flash
    found_healthy = False
    healthy_msg = ""
    tested_errors = []

    for test_key, masked in keys_pool[:2]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={test_key}"
        try:
            r = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": "Ping"}]}]},
                timeout=timeout
            )
            if r.status_code == 200:
                found_healthy = True
                healthy_msg = f"Key {masked} aktiv & gesund (gemini-3.8-flash, HTTP 200)"
                break
            else:
                err_msg = "503 High Demand" if (r.status_code == 503 or "high demand" in r.text) else f"HTTP {r.status_code}"
                tested_errors.append(f"{masked}: {err_msg}")
        except requests.exceptions.Timeout:
            tested_errors.append(f"{masked}: Timeout ({timeout}s)")
        except Exception as e:
            tested_errors.append(f"{masked}: {str(e)[:25]}")

    _health_cache["last_checked"] = now
    active_tier = "Google Pro-Abo CLI (pokeulm@gmail.com · gemini-3.8-flash-high)"
    if found_healthy:
        _health_cache["model_38_healthy"] = True
        _health_cache["message"] = f"Key-Pool Reserve einsatzbereit ({healthy_msg})"
    else:
        _health_cache["model_38_healthy"] = False
        _health_cache["message"] = f"Key-Pool Reserve 3.8 überlastet ({'; '.join(tested_errors[:2])}) -> Pro-Abo Account 2 (pokeulm) sichert primär"

    try:
        from gemini_quota_tracker import record_health_check
        record_health_check(
            is_healthy=_health_cache["model_38_healthy"],
            message=_health_cache["message"],
            tested_key_masked=keys_pool[0][1] if keys_pool else "AQ.***",
            active_tier=active_tier
        )
    except Exception:
        pass

    return _health_cache["model_38_healthy"], _health_cache["message"]


def evaluate_batch_with_cascade(assets_batch):
    """
    Intelligente 4-Stufen Kaskade (User-Priorität: Erst pokeulm, dann die Keys auf 3.8 High, dann 3.5 Fallback, dann Math-Core):
    - STUFE 1 (PRIMÄR): Google Pro-Abo via CLI (gemini-3.8-flash-high mit Account 2 pokeulm@gmail.com).
      -> Volle Skalierbarkeit ohne 50er-Limit.
    - STUFE 2 (FAILOVER 1): Multi-Key Free Pool mit gemini-3.8-flash (High Thinking).
    - STUFE 3 (FAILOVER 2): Multi-Key Free Pool mit gemini-3.5-flash (bei 503-Überlastung von 3.8).
    - STUFE 4 (SAFETY NET): Quantitative Confluence Math-Engine (SMC, Wyckoff VSA, Golden Pocket).
    """
    conf = load_config()
    if not conf.get("enabled", True):
        return None, "KI-Auswertung in gemini_config.json deaktiviert", "disabled"

    primary_model = "gemini-3.8-flash-high"
    fallback_model = conf.get("fallback_model", "gemini-3.5-flash")
    timeout = conf.get("timeout_seconds", 120)
    use_pro_sub = conf.get("use_pro_subscription", True)

    prompt = build_analysis_prompt(assets_batch)

    # =========================================================================
    # STUFE 1: Google Pro-Abo CLI mit gemini-3.8-flash-high (Account 2: pokeulm@gmail.com)
    # =========================================================================
    if use_pro_sub:
        try:
            from gemini_quota_tracker import is_pro_quota_available, record_pro_cli_request
            pro_allowed = is_pro_quota_available()
        except Exception:
            pro_allowed = True

        if pro_allowed:
            print(f" (Stufe 1: Google Pro-Abo CLI {primary_model} [pokeulm@gmail.com])...", end="", flush=True)
            res, err = call_gemini_via_pro_cli(prompt, model=primary_model, timeout=timeout)
            if res and isinstance(res, list) and len(res) > 0:
                try:
                    record_pro_cli_request()
                except Exception:
                    pass
                t_token = Path("/home/admin/.gemini_trading/.gemini/antigravity-cli/antigravity-oauth-token")
                acc_label = "Account 2 Pro (pokeulm@gmail.com)" if t_token.exists() else "Account 1 Pro (mayer.max.1994@gmail.com)"
                return res, None, f"{primary_model} [{acc_label}]"
            print(f" [Stufe 1 Pro-Abo CLI ({err}) -> Failover auf Stufe 2 Keys]...", end="", flush=True)
        else:
            print(f" [Stufe 1 Google 5h-Limit erreicht -> Failover auf Stufe 2 Keys]...", end="", flush=True)

    # =========================================================================
    # STUFE 2: Multi-Key Pool (REST) mit gemini-3.8-flash High
    # =========================================================================
    print(f" (Stufe 2: Multi-Key Pool REST gemini-3.8-flash High)...", end="", flush=True)
    res, err, used_key_info = call_gemini_via_key_pool(prompt, model="gemini-3.8-flash", timeout=45)
    if res and isinstance(res, list) and len(res) > 0:
        return res, None, f"gemini-3.8-flash High [{used_key_info}]"

    # =========================================================================
    # STUFE 3: Multi-Key Pool (REST) Fallback auf gemini-3.5-flash
    # =========================================================================
    print(f" (Stufe 3: Multi-Key Pool Fallback {fallback_model})...", end="", flush=True)
    res, err, used_key_info = call_gemini_via_key_pool(prompt, model=fallback_model, timeout=30)
    if res and isinstance(res, list) and len(res) > 0:
        return res, None, f"{fallback_model} [{used_key_info}]"

    # =========================================================================
    # STUFE 4: Fallback auf quantitative Confluence-Engine
    # =========================================================================
    print(f"\n      ⚠️ KI-Auswertung nicht verfügbar ({err}) -> Aktiviere Stufe 4 (Mathematische Confluence-Engine)...", end="", flush=True)
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
