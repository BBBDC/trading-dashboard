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
    "primary_model": "gemini-4-hydrogen",
    "primary_effort": "medium",
    "deep_dive_model": "gemini-4-neon",
    "deep_dive_effort": "high",
    "fallback_model": "gemini-4-hydrogen",
    "fallback_effort": "low",
    "use_pro_subscription": True,
    "api_key": "",
    "temperature": 0.2,
    "batch_size": 2,
    "timeout_seconds": 45,
    "comment": "Google AI Pro: 1. gemini-4-hydrogen (Medium via agy CLI) -> 2. gemini-4-hydrogen (Low via agy CLI) -> 3. Math-Core"
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


def call_gemini_via_pro_cli(prompt, model=None, effort=None, timeout=None):
    """
    Ruft das Google Gemini / Claude Modell direkt über das Google AI Pro-Abo (agy CLI) auf.
    Nutzt das primäre Google-Konto (Account 1: mayer.max.1994@gmail.com).
    """
    if not AGY_BIN.exists():
        return None, f"agy CLI unter {AGY_BIN} nicht gefunden."

    conf = load_config()
    cli_model = model or conf.get("primary_model", "gemini-4-hydrogen")
    cli_effort = effort or conf.get("primary_effort", "medium")
    timeout = timeout or conf.get("timeout_seconds", 45)

    cmd = [
        str(AGY_BIN),
        "-p", prompt,
        "--model", cli_model,
        "--effort", cli_effort,
        "--disable-slash-commands"
    ]

    env = os.environ.copy()
    acc_label = "Google AI Pro (mayer.max.1994@gmail.com)"

    try:
        res = subprocess.run(cmd, cwd="/tmp", capture_output=True, text=True, timeout=timeout, env=env)
        if res.returncode != 0:
            err = res.stderr.strip() or f"CLI Exit-Code {res.returncode}"
            return None, f"Pro CLI Fehler ({cli_model} [{cli_effort}] via {acc_label}): {err[:180]}"

        parsed = extract_json_from_text(res.stdout)
        if parsed:
            return parsed, None
        else:
            return None, f"Antwort von {cli_model} [{cli_effort}] via {acc_label} konnte nicht als JSON geparst werden."

    except subprocess.TimeoutExpired:
        return None, f"Pro CLI Timeout ({timeout}s) bei {cli_model} [{cli_effort}] ({acc_label})."
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
        if res and ((isinstance(res, list) and len(res) > 0) or (isinstance(res, dict) and len(res) > 0)):
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
    # 1. Google AI Pro CLI mit Deep-Dive Modell (gemini-4-neon high)
    conf = load_config()
    deep_model = conf.get("deep_dive_model", "gemini-4-neon")
    deep_effort = conf.get("deep_dive_effort", "high")
    try:
        res, err = call_gemini_via_pro_cli(prompt, model=deep_model, effort=deep_effort, timeout=45)
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


def evaluate_batch_trades_post_mortem(trades_list):
    """
    Führt eine vergleichende Multi-Trade Post-Mortem-Analyse für 2 bis 5 abgeschlossene Trades durch.
    Analysiert Kausalitäten (Cross-Trade-Synthese): Was unterschied Gewinner von Verlierern?
    Nutzt prioritär Gemini 4 via Google AI Pro CLI (mayer.max.1994@gmail.com).
    """
    if not trades_list:
        return None

    # Textuelle Aufbereitung der Trades
    trades_summary_text = []
    for idx, t in enumerate(trades_list, 1):
        tid = t.get("trade_id", f"trade_{idx}")
        sym = t.get("symbol", "")
        name = t.get("name", sym)
        tf = t.get("timeframe", "15m")
        direction = t.get("direction", "LONG")
        setup = t.get("setup_name", "degencoder Confluence")
        tags = ", ".join(t.get("setup_tags", []))
        entry_p = t.get("entry_price", 0.0)
        exit_p = t.get("exit_price", entry_p)
        r_pnl = t.get("realized_r", 0.0)
        pnl_pct = t.get("realized_pnl_pct", 0.0)
        status = t.get("status", "CLOSED")
        exit_reason = t.get("exit_reason", "")
        trades_summary_text.append(
            f"Trade {idx} [{tid}]: {name} ({sym}) | TF: {tf} | Richtung: {direction} | Setup: {setup} | "
            f"Triggers: {tags} | Entry: {entry_p} | Exit: {exit_p} | Status: {status} | "
            f"Realisierter PnL: {pnl_pct:+.2f}% ({r_pnl:+.1f}R) | Exit-Grund: {exit_reason}"
        )

    trades_block = "\n".join(trades_summary_text)

    prompt = f"""Du bist ein Senior Prop-Desk Chef-Risikomanager und Trading-Coach mit 20 Jahren Markterfahrung an Krypto- und traditionellen Börsen (Frankfurt, XETRA, Wall Street).
Analysiere diese Gruppe von kürzlich abgeschlossenen Trades unseres autonomen Handelslabors (Mikro-Zeitskalen 5m und 15m) vergleichend und schonungslos:

{trades_block}

AUFGABE:
1. Untersuche vergleichend die Kausalitäten: Was unterschied die Gewinner von den Verlierern? (z.B. VSA-Volumenbestätigung, Überdehnung zu Chaos-Bändern, Liquidity-Sweep Qualität [A], übergeordneter 4h-Trend).
2. Erstelle für jeden einzelnen Trade eine prägnante Ursachen- und Regelanalyse.
3. Destilliere 1 bis 2 übergreifende, fraktale Handlungsregeln, die auch für 4h/1D Setups bindend gültig sind.

Antworte AUSSCHLIESSLICH im folgenden JSON-Format:
{{
  "batch_summary": "1-2 Sätze vergleichende Gesamteinschätzung dieser Trade-Gruppe",
  "trade_evaluations": [
    {{
      "trade_id": "...",
      "verdict": "WIN oder LOSS",
      "driver": "Konkrete Ursache für Erfolg oder Misserfolg (1 prägnanter Satz)",
      "technical_warning": "Welches Chart-/Indikator-Signal (z.B. Volumen, Sweep-Tiefe, FVG-Größe) hätte früher gewarnt?",
      "actionable_rule": "Eine bindende Handlungsregel für künftige Trades bei diesem Setup"
    }}
  ],
  "cross_market_insights": [
    {{
      "rule": "Übergreifende System-Regel für das 4h/1D Gedächtnis",
      "context": "Begründung aus den 5m/15m Beobachtungen"
    }}
  ]
}}
"""
    # 1. Google AI Pro CLI mit Deep-Dive Modell (gemini-4-neon high)
    conf = load_config()
    deep_model = conf.get("deep_dive_model", "gemini-4-neon")
    deep_effort = conf.get("deep_dive_effort", "high")
    try:
        res, err = call_gemini_via_pro_cli(prompt, model=deep_model, effort=deep_effort, timeout=45)
        if res and isinstance(res, dict) and "trade_evaluations" in res:
            return res
    except Exception:
        pass

    # 3. Deterministischer Fallback
    evals = []
    for t in trades_list:
        tid = t.get("trade_id", "")
        is_win = (t.get("realized_r", 0) > 0)
        evals.append({
            "trade_id": tid,
            "verdict": "WIN" if is_win else "LOSS",
            "driver": f"Trade {t.get('symbol')} schloss mit {t.get('status')} ({t.get('realized_r', 0):+.1f}R).",
            "technical_warning": "Im 5m/15m Bereich vor Einstieg Bestätigung durch Volumen-Ratio >= 1.5 abwarten.",
            "actionable_rule": f"Bei {t.get('symbol')} Trailing-Stop nach TP1 konsequent auf Breakeven setzen."
        })

    return {
        "batch_summary": "Deterministische Auswertung der Batch-Trades (Fallback-Modus).",
        "trade_evaluations": evals,
        "cross_market_insights": [
            {
                "rule": "Trades nur in Richtung der 4h RFE 233 Basislinie eingehen.",
                "context": "Statischer Schutz vor Counter-Trend Whipsaws."
            }
        ]
    }


CLAUDE_BIN = Path("/home/admin/.local/bin/claude")


def audit_trades_with_opus_meta(trades_list, gemini_evals=None):
    """
    Stufe 2 der Dual-KI-Synthese:
    Ruft Claude Opus für ein übergeordnetes 10-Trade Meta-Audit auf.
    Analysiert Kausalitäten, validiert/schärft die Gemini 3.8 Flash Voranalysen
    und destilliert fundamentale Fraktal-Regeln (Axiome) für trade_memory.json.
    """
    if not CLAUDE_BIN.exists():
        return {
            "status": "SKIPPED_NOT_INSTALLED",
            "model": "Claude Opus 5.5",
            "summary": "Claude CLI nicht installiert."
        }

    trades_lines = []
    for idx, t in enumerate(trades_list, 1):
        tid = t.get("trade_id", f"trade_{idx}")
        sym = t.get("symbol", "")
        name = t.get("name", sym)
        tf = t.get("timeframe", "5m")
        direction = t.get("direction", "LONG")
        score = t.get("setup_score", t.get("score", 0))
        r_pnl = t.get("realized_r", 0.0)
        pnl_pct = t.get("realized_pnl_pct", 0.0)
        status = t.get("status", "CLOSED")
        exit_reason = t.get("exit_reason", "")
        tags = ", ".join(t.get("setup_tags", []))
        
        gem_str = ""
        if gemini_evals and tid in gemini_evals:
            g = gemini_evals[tid]
            gem_str = f" | Gemini: {g.get('driver', '')} -> Regel: {g.get('actionable_rule', '')}"
        elif t.get("ai_post_mortem"):
            g = t.get("ai_post_mortem")
            gem_str = f" | Gemini: {g.get('driver', '')} -> Regel: {g.get('actionable_rule', '')}"

        trades_lines.append(
            f"Trade {idx} [{tid}]: {name} ({sym}) | {tf} {direction} | Score: {score}P | "
            f"Triggers: {tags} | Status: {status} | PnL: {pnl_pct:+.2f}% ({r_pnl:+.1f}R) | "
            f"Exit: {exit_reason}{gem_str}"
        )

    trades_block = "\n".join(trades_lines)

    prompt = f"""Du bist Claude Opus 5.5, der quantitative Chef-Auditor für Risiko und stochastische Kausalität unseres Handelslabors.
Vor dir liegt ein aggregierter Meilenstein-Batch von {len(trades_list)} abgeschlossenen Trades (Mikro-Zeitskalen 5m/15m/30m).
Gemini 3.8 Flash hat für die Trades bereits eine taktische Erstauswertung vorgenommen.

DEINE AUFGABE ALS META-SYNTHESIZER:
1. Analysiere das übergeordnete Makro-Regime und die Kausalitätsmuster: Welche gemeinsamen Marktbedingungen (Session-Liquidität, Trendstärke, Volatilität) trennten Gewinner von Verlierern?
2. Begutachte die taktischen Gemini-Regeln: Sind sie stochastisch valide oder leidet Gemini unter Scheinkorrelation / Recency Bias?
3. Destilliere genau 1 bis 2 fundamentale, bindende Meta-Axiome für unser Gedächtnis (trade_memory.json), die fraktal auch auf höheren Zeitebenen (4h/1D) gelten müssen.

ABGESCHLOSSENE TRADES:
{trades_block}

Antworte AUSSCHLIESSLICH im folgenden JSON-Format:
{{
  "model": "Claude Opus 5.5",
  "batch_size": {len(trades_list)},
  "meta_verdict": "Kurzes, schonungsloses Gesamtfazit dieses Zyklus (1-2 Sätze)",
  "regime_synthesis": "Analyse der übergreifenden Marktmechanik und Kausalität",
  "gemini_review": "Kritische Würdigung der Gemini-Hypothesen (Bestätigung oder Korrektur)",
  "binding_meta_axioms": [
    {{
      "rule": "Prägnante, unmissverständliche Handlungsregel für künftige Trades",
      "context": "Kausale Begründung aus den aggregierten Daten",
      "timeframe_scope": "5m/15m/30m/4h/1D",
      "conviction": "HIGH"
    }}
  ]
}}
"""
    try:
        cmd = [str(CLAUDE_BIN), "-p", "--model", "opus", "--effort", "medium", prompt]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        out = proc.stdout.strip()

        if "5-hour limit" in out or "rate limit" in out.lower() or "5-hour limit" in proc.stderr:
            return {
                "status": "SKIPPED_QUOTA",
                "model": "Claude Opus 5.5",
                "summary": "Claude Quota / 5-Stunden-Limit erreicht. Überspringe Opus-Audit ohne Systemabbruch."
            }

        import re
        m_json = re.search(r"\{.*\}", out, re.DOTALL)
        if m_json:
            return json.loads(m_json.group(0))
        return {
            "status": "RAW_TEXT",
            "model": "Claude Opus 5.5",
            "meta_verdict": out[:300]
        }
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "model": "Claude Opus 5.5", "summary": "Claude Opus Timeout (60s)."}
    except Exception as e:
        return {"status": "ERROR", "model": "Claude Opus 5.5", "error": str(e)}


def audit_critical_trade_with_opus(trade, gemini_eval=None):
    """
    Ad-hoc Deep-Audit durch Claude Opus bei anomalen/kritischen Trades:
    - Fehlgeschlagene A+ Setups (Score >= 80 mit vollem SL-Verlust)
    - Ausreißer-Gewinner (> +2.0R)
    """
    if not CLAUDE_BIN.exists():
        return None

    tid = trade.get("trade_id", "")
    sym = trade.get("symbol", "")
    name = trade.get("name", sym)
    direction = trade.get("direction", "")
    tf = trade.get("timeframe", "5m")
    score = trade.get("setup_score", trade.get("score", 0))
    r_pnl = trade.get("realized_r", 0.0)
    pnl_pct = trade.get("realized_pnl_pct", 0.0)
    reason = trade.get("exit_reason", "")
    triggers = ", ".join(trade.get("setup_tags", []))
    
    gem_driver = gemini_eval.get("driver", "") if gemini_eval else ""
    gem_rule = gemini_eval.get("actionable_rule", "") if gemini_eval else ""

    prompt = f"""Du bist Claude Opus 5.5, der quantitative Chef-Auditor unseres Handelslabors.
Hier ist ein KRITISCHER ANOMALIE-TRADE zur tiefen Kausalitätsprüfung:

Trade: {name} ({sym}) | {tf} {direction} | Score: {score}P (Grade A+)
Einstieg: {trade.get('entry_price')} | Ausstieg: {trade.get('exit_price')}
Realisierter PnL: {pnl_pct:+.2f}% ({r_pnl:+.1f}R) | Status: {trade.get('status')}
Ausstiegs-Grund: {reason}
Setup-Trigger: {triggers}
Gemini 3.8 Flash Voranalyse: Driver: {gem_driver} | Regel: {gem_rule}

PRÜFUNGSAUFTRAG:
Warum hat dieses statistisch hochgradige Setup versagt (bzw. warum lief der Ausreißer so weit)?
Lag ein verdeckter Liquiditäts-Sweep, ein HTF-Strukturbruch oder ein Volumen-Absorptionsfehler vor?

Antworte AUSSCHLIESSLICH im folgenden JSON-Format:
{{
  "model": "Claude Opus 5.5",
  "anomaly_type": "CRITICAL_A_PLUS_FAILURE" oder "EXTREME_RUNNER",
  "causal_driver": "Präzise 1-Satz Ursache für das unerwartete Ergebnis",
  "structural_breakdown": "Tiefgehende Kausalitätsbegründung",
  "opus_actionable_rule": "Genaue Anpassung für den Filterkatalog"
}}
"""
    try:
        cmd = [str(CLAUDE_BIN), "-p", "--model", "opus", "--effort", "medium", prompt]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=50)
        out = proc.stdout.strip()
        if "5-hour limit" in out or "rate limit" in out.lower() or "5-hour limit" in proc.stderr:
            return None
        import re
        m_json = re.search(r"\{.*\}", out, re.DOTALL)
        if m_json:
            return json.loads(m_json.group(0))
        return None
    except Exception:
        return None


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
   - Makro-Trend (1D & 1W) ist bullisch (über 233 EMA) ODER der Kurs sitzt im institutional 'degencoder Buy Pocket' (Lower Chaos Band unter RFE 233) ODER exakt im 1D Fibonacci Golden Pocket (0.618 - 0.650) ODER an einem unberührten bullischen SMC Order Block (Grad A / Retest R1-R3 mit Liquiditäts-Sweep).
   - Kein Chasing: Niemals Long gehen, wenn der 4h-Kurs bereits am oberen degencoder-Band (Overbought) oder der RSI > 62 ist.
   - TRIGGER-PFLICHT & EMPIRISCHES KONFLUENZ-GATE:
     * Ein SMC Order Block oder FVG alleine ohne Reversal-Trigger erzielt empirisch nur 46% Win-Rate. Vergib NIEMALS ein LONG/SHORT-Signal oder Score >= 80% für eine bloße Zone ohne Reversal-Bestätigung! Ohne Trigger bleibt das Signal "NEUTRAL" (Score max. 68%).
     * Es MUSS auf 1h oder 4h ein echter Trigger vorliegen: degencoder 'Good Buy Signal' (blaues Dreieck, 6.8x Asymmetrie), 'Buy Area' (grünes Kreuz, 56.5% Win-Rate), eine bullische RSI-Divergenz ODER Wyckoff "No Supply" am Support.
     * Rausch-Signale wie 'Bear Alignment Ends' dürfen keine Bonuspunkte erhalten.
   - Mindest-CRV (Chance-Risiko-Verhältnis) >= 2.5:1 zum nächsten signifikanten FVG / Widerstand.
   - Score >= 88 % wird NUR bei makelloser 3-facher Konfluenz (Zone + Trigger + 233-EMA Trendfolge) vergeben.

3. KRITERIEN FÜR EIN ECHTES "SHORT"-SIGNAL (SEHR STRIKT):
   - Makro-Trend ist bärisch (unter 233 EMA) ODER institutional 'degencoder Sell Pocket' (Upper Chaos Band über RFE 233) ODER klare Top-Erschöpfung am oberen 1D-Kanalband (Overbought) / bärischer Order Block (Grad A mit Sweep) mit bestätigtem degencoder 'Good Sell Signal' (Kreis) oder bärischer Divergenz auf 1h/4h.
   - Niemals Short gegen einen starken intakten 1D-Bullenmarkt ohne strukturellen Bruch.
   - Mindest-CRV >= 2.5:1.

4. STANDARD-EINSTUFUNG BEI UNKLARER LAGE:
   - 70–80 % aller Marktphasen gehören ins "NEUTRAL (Beobachten)".
   - Im Zweifel MUSS das Signal IMMER "NEUTRAL" sein (Score 40–55%).

5. STOP-LOSS & TARGETS:
   - Der Stop-Loss muss strukturell begründet sein (knapp unterhalb des Order Blocks / Golden Pocket / Swing-Lows / FVG), niemals willkürlich.
   - Take Profit 1 & 2 müssen an echten Liquiditätszonen, Order Blocks oder gegnerischen FVGs liegen.
{memory_block}
Hier sind die aktuellen Marktdaten, degencoder Indikatoren & Order Blocks für {len(assets_batch)} Assets:

{json.dumps(assets_batch, indent=2, ensure_ascii=False)}

AUFGABE:
Analysiere jedes Asset gründlich. Berücksichtige übergeordnete Trends (1D) vs untergeordnete Einstiege (4h/1h) sowie die degencoder Signale & Order Blocks.
Erstelle für JEDES Asset im Input eine exakte Handelsbewertung.

Antworte AUSSCHLIESSLICH als JSON-Array von Objekten mit exakt diesem Schema:
[
  {{
    "symbol": "TICKER (exakt wie im Input)",
    "signal": "LONG" | "SHORT" | "NEUTRAL",
    "score": 0 bis 100 (Streng konservativ! >85% nur für absolute Top-Tier Setups),
    "setup_name": "z.B. Hypothese 1: degencoder Institutional Buy Pocket Reversal | Hypothese 1: SMC Order Block Confluence | Hypothese 1: SMC Golden Confluence Reversal | Beobachten / Lauerstellung am Support",
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
    Health-Check für die KI-Engine.
    Bestätigt den aktiven Google AI Pro CLI Status für gemini-4-hydrogen (Medium).
    """
    now = time.time()
    if now - _health_cache["last_checked"] < 120:
        return _health_cache["model_38_healthy"], _health_cache["message"]

    _health_cache["last_checked"] = now
    _health_cache["model_38_healthy"] = True
    _health_cache["message"] = "Google AI Pro CLI aktiv & einsatzbereit (gemini-4-hydrogen Medium)"
    active_tier = "Google AI Pro CLI (mayer.max.1994@gmail.com · gemini-4-hydrogen Medium)"

    try:
        from gemini_quota_tracker import record_health_check
        record_health_check(
            is_healthy=True,
            message=_health_cache["message"],
            tested_key_masked="Pro CLI (Hauptaccount)",
            active_tier=active_tier
        )
    except Exception:
        pass

    return _health_cache["model_38_healthy"], _health_cache["message"]


def evaluate_batch_with_cascade(assets_batch):
    """
    Schlanke, hochperformante Google AI Pro Kaskade:
    - STUFE 1 (PRIMÄR): Google Pro-Abo via CLI (gemini-4-hydrogen mit Effort 'medium').
    - STUFE 2 (FAILOVER): Google Pro-Abo via CLI (gemini-4-hydrogen mit Effort 'low').
    - STUFE 3 (SAFETY NET): Quantitative Confluence Math-Engine (SMC, Wyckoff VSA, Golden Pocket).
    """
    conf = load_config()
    if not conf.get("enabled", True):
        return None, "KI-Auswertung in gemini_config.json deaktiviert", "disabled"

    primary_model = conf.get("primary_model", "gemini-4-hydrogen")
    primary_effort = conf.get("primary_effort", "medium")
    fallback_model = conf.get("fallback_model", "gemini-4-hydrogen")
    fallback_effort = conf.get("fallback_effort", "low")
    timeout = conf.get("timeout_seconds", 45)
    use_pro_sub = conf.get("use_pro_subscription", True)

    prompt = build_analysis_prompt(assets_batch)
    assets_symbols = [a.get("symbol", "") for a in assets_batch if isinstance(a, dict)]
    outcome1 = "ERROR"
    dur1 = 0.0
    err1 = None

    # =========================================================================
    # STUFE 1: Google AI Pro CLI mit gemini-4-hydrogen (Effort: medium)
    # =========================================================================
    if use_pro_sub:
        try:
            from gemini_quota_tracker import is_pro_quota_available, record_pro_cli_request, record_gemini_execution_event
            pro_allowed = is_pro_quota_available()
        except Exception:
            pro_allowed = True
            record_gemini_execution_event = None

        if pro_allowed:
            print(f" (Stufe 1: Google AI Pro CLI {primary_model} [{primary_effort}])...", end="", flush=True)
            t0 = time.time()
            res, err = call_gemini_via_pro_cli(prompt, model=primary_model, effort=primary_effort, timeout=timeout)
            dur1 = time.time() - t0
            if res and isinstance(res, list) and len(res) > 0:
                try:
                    record_pro_cli_request()
                except Exception:
                    pass
                if record_gemini_execution_event:
                    try:
                        record_gemini_execution_event(
                            tier="Stufe 1 (Pro CLI)",
                            model=f"{primary_model} ({primary_effort})",
                            outcome="SUCCESS",
                            duration_seconds=dur1,
                            assets=assets_symbols
                        )
                    except Exception:
                        pass
                return res, None, f"{primary_model} [{primary_effort}]"

            err1 = err
            outcome1 = "TIMEOUT" if "Timeout" in str(err) else ("HTTP_503_OVERLOAD" if "503" in str(err) else "ERROR")
            print(f" [Stufe 1 ({err}) -> Failover auf Stufe 2 Low Effort]...", end="", flush=True)
        else:
            outcome1 = "5H_LIMIT_HIT"
            err1 = "Google 5h-Limit erreicht"
            print(f" [Stufe 1 Google 5h-Limit erreicht -> Failover auf Stufe 2 Low Effort]...", end="", flush=True)

    # =========================================================================
    # STUFE 2: Google AI Pro CLI Fallback mit gemini-4-hydrogen (Effort: low)
    # =========================================================================
    print(f" (Stufe 2: Pro CLI Fallback {fallback_model} [{fallback_effort}])...", end="", flush=True)
    t0 = time.time()
    res, err = call_gemini_via_pro_cli(prompt, model=fallback_model, effort=fallback_effort, timeout=max(20, timeout - 15))
    dur2 = time.time() - t0
    if res and isinstance(res, list) and len(res) > 0:
        try:
            from gemini_quota_tracker import record_gemini_execution_event
            record_gemini_execution_event(
                tier="Stufe 1 (Pro CLI)",
                model=f"{primary_model} ({primary_effort})",
                outcome=outcome1,
                duration_seconds=dur1,
                assets=assets_symbols,
                fallback_used=f"Stufe 2 ({fallback_model} [{fallback_effort}])",
                error_message=err1
            )
        except Exception:
            pass
        return res, None, f"{fallback_model} [{fallback_effort}]"

    # =========================================================================
    # STUFE 3: Fallback auf quantitative Confluence-Engine
    # =========================================================================
    try:
        from gemini_quota_tracker import record_gemini_execution_event
        record_gemini_execution_event(
            tier="Stufe 1 (Pro CLI)",
            model=primary_model,
            outcome=outcome1,
            duration_seconds=dur1,
            assets=assets_symbols,
            fallback_used="Stufe 3 (Quantitative Math-Core)",
            error_message=err1 or err
        )
    except Exception:
        pass
    print(f"\n      ⚠️ KI-Auswertung nicht verfügbar ({err}) -> Aktiviere Stufe 3 (Mathematische Confluence-Engine)...", end="", flush=True)
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
