#!/usr/bin/env python3
"""
Automated Asset Onboarding & Historical Matrix Evaluator.
=========================================================
Sobald ein neues Symbol in einer TradingView-Watchlist erkannt wird:
1. Automatische Ermittlung von Quelle (Binance / Yahoo Finance) und Ticker-Mapping.
2. Vollständiger historischer Datenabruf (bis zu 15 Jahre, 0 Tokens / kostenlos).
3. Ausführung der vollständigen Multi-Timeframe Matrix (8 Timeframes x 4 Modi).
4. Statistische Konsens-Klassifikation nach Grok & Fable 5.2 Kriterien:
   - PILOT_LIVE    : p < 0.05, PF >= 1.40, OOS E(R) >= +0.25R, Reibung < 20%
   - SHADOW_PAPER  : Positiver E(R), aber OOS-Datenbasis noch im Aufbau -> AI-Incubator
   - REJECTED      : Negativer Drift / Hohe Reibung -> Striktes Trade-Verbot, rein informativ
5. Speicherung des Prüfberichts und Versand einer Telegram/ntfy Push-Nachricht.
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent
KB_DIR = BASE_DIR / "knowledge_base"
EVAL_LOG = KB_DIR / "asset_evaluations.json"

# Bekannte Ticker-Mappings für Tradegate / Deutsche Symbole
TICKER_OVERRIDES = {
    "TRADEGATE:FMV": {"symbol": "FMV.DE", "alt": "FTV", "name": "Fortive Corp", "cat": "Aktien"},
    "TRADEGATE:BW9": {"symbol": "BWA", "alt": "BW9.DE", "name": "BorgWarner", "cat": "Aktien"},
    "TRADEGATE:TL0": {"symbol": "TSLA", "name": "Tesla", "cat": "US-Tech"},
    "TRADEGATE:NVD": {"symbol": "NVDA", "name": "Nvidia", "cat": "US-Tech"},
    "TRADEGATE:MTE": {"symbol": "MU", "name": "Micron", "cat": "US-Tech"},
    "TRADEGATE:RHM": {"symbol": "RHM.DE", "name": "Rheinmetall", "cat": "DAX"},
    "TRADEGATE:SAP": {"symbol": "SAP.DE", "name": "SAP", "cat": "DAX"},
    "TRADEGATE:SIE": {"symbol": "SIE.DE", "name": "Siemens", "cat": "DAX"},
}


def resolve_asset_target(raw_sym: str) -> Dict[str, Any]:
    """Löst ein TradingView-Symbol in ein universelles Daten-Target auf."""
    s = raw_sym.strip().upper()
    if s in TICKER_OVERRIDES:
        o = TICKER_OVERRIDES[s]
        return {
            "raw_symbol": s,
            "symbol": o["symbol"],
            "name": o.get("name", s),
            "category": o.get("cat", "Aktien"),
            "source": "yahoo"
        }

    prefix = s.split(":")[0] if ":" in s else ""
    ticker = s.split(":")[1] if ":" in s else s

    # 1. Krypto
    if any(ex in s for ex in ["BINANCE:", "COINBASE:", "KRAKEN:", "BITSTAMP:"]) or any(s.endswith(q) for q in ["USDT", "USDC", "USD", "BTC", "ETH"]):
        clean_t = ticker.replace("USDT.P", "USDT").replace(".P", "")
        return {
            "raw_symbol": s,
            "symbol": clean_t,
            "name": clean_t,
            "category": "Crypto",
            "source": "binance"
        }

    # 2. Tradegate
    if prefix == "TRADEGATE":
        # Versuche primär .DE, sonst US-Ticker
        return {
            "raw_symbol": s,
            "symbol": f"{ticker}.DE",
            "name": f"{ticker} (Tradegate)",
            "category": "Tradegate / EU",
            "source": "yahoo"
        }

    # 3. XETRA / FWB
    if prefix in ("XETR", "FWB"):
        return {
            "raw_symbol": s,
            "symbol": f"{ticker}.DE",
            "name": ticker,
            "category": "DAX",
            "source": "yahoo"
        }

    # 4. US Aktien (NASDAQ / NYSE)
    if prefix in ("NASDAQ", "NYSE", "AMEX"):
        return {
            "raw_symbol": s,
            "symbol": ticker,
            "name": ticker,
            "category": "US-Tech" if prefix == "NASDAQ" else "Aktien",
            "source": "yahoo"
        }

    # Standard Fallback
    return {
        "raw_symbol": s,
        "symbol": ticker,
        "name": ticker,
        "category": "Aktien",
        "source": "yahoo"
    }


def evaluate_single_symbol(raw_sym: str) -> Dict[str, Any]:
    """
    Führt den vollen Multi-Timeframe Matrix-Backtest für ein Symbol durch.
    Gibt die detaillierte Scorecard und Handlungsempfehlung zurück.
    """
    from backtest_data_loader import get_cached_bars
    from backtest_matrix_engine import run_single_backtest, TIMEFRAMES, MODES

    target = resolve_asset_target(raw_sym)
    sym = target["symbol"]
    name = target["name"]
    cat = target["category"]

    print(f"\n📊 Starte Onboarding-Backtest für: {name} ({raw_sym} ➔ {sym})")

    # Reibungskosten gemäß Asset-Klasse
    if cat == "Forex":
        fee_val, slip_val = 0.00005, 0.0001
    elif cat in ("US-Tech", "DAX", "Index", "Commodity", "Aktien", "Tradegate / EU"):
        fee_val, slip_val = 0.0002, 0.0001
    else:  # Crypto
        fee_val, slip_val = 0.00055, 0.0002

    tf_results = {}
    robust_setups = []
    total_trades_all = 0
    total_r_all = 0.0

    for tf in TIMEFRAMES:
        bars = get_cached_bars(target, interval=tf)
        if len(bars) < 245:
            continue

        tf_results[tf] = {}
        for mode in MODES:
            res = run_single_backtest(bars, mode=mode, timeframe=tf, fee_pct=fee_val, slippage_pct=slip_val)
            if res and res["trades"] > 0:
                tf_results[tf][mode] = res
                total_trades_all += res["trades"]
                total_r_all += res["total_r"]

                # Robuste Edge Kriterien prüfen
                if res["verdict"] == "ROBUST_EDGE" and res["oos_trades"] >= 5 and res["oos_r"] > 1.0:
                    robust_setups.append({
                        "timeframe": tf,
                        "mode": mode,
                        "trades": res["trades"],
                        "win_rate": res["win_rate"],
                        "profit_factor": res["profit_factor"],
                        "expectancy_r": res["expectancy_r"],
                        "oos_trades": res["oos_trades"],
                        "oos_r": res["oos_r"],
                        "oos_wr": res["oos_wr"]
                    })

    # Gesamterwartungswert & Klassifikation ermitteln
    if len(robust_setups) >= 2 or (len(robust_setups) >= 1 and any(s["profit_factor"] >= 1.5 for s in robust_setups)):
        tier = "PILOT_LIVE"
        tier_badge = "🟢 [PILOT_LIVE]"
        recommendation = "Bestätigte statistische Edge! Empfohlen für Whitelist-Aufnahme im KI-Live-Portfolio."
    elif total_r_all > 0 and total_trades_all >= 10:
        tier = "SHADOW_PAPER"
        tier_badge = "🟡 [SHADOW_PAPER]"
        recommendation = "Positiver Gesamterwartungswert, aber Validierungsphase erforderlich. Automatisch im AI-Incubator gestartet."
    else:
        tier = "INFORMATIV"
        tier_badge = "⚪ [INFORMATIV / REJECTED]"
        recommendation = "Keine statistisch robuste Edge nach Reibungskosten. Bleibt rein zur Marktbeobachtung, striktes Trade-Verbot."

    summary = {
        "raw_symbol": raw_sym,
        "symbol": sym,
        "name": name,
        "category": cat,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "tier": tier,
        "tier_badge": tier_badge,
        "recommendation": recommendation,
        "robust_setups_count": len(robust_setups),
        "robust_setups": robust_setups,
        "total_trades": total_trades_all,
        "total_r": round(total_r_all, 2),
        "detailed_results": tf_results
    }

    print(f"  🏁 Ergebnis: {tier_badge} - {recommendation}")
    if robust_setups:
        print(f"     Gefundene robuste Setups: {len(robust_setups)}")
        for rs in robust_setups[:3]:
            print(f"     • {rs['timeframe']} ({rs['mode']}): WR {rs['win_rate']}% | PF {rs['profit_factor']} | OOS {rs['oos_r']:+.1f}R")

    return summary


def send_onboarding_notification(eval_summary: Dict[str, Any]):
    """Sendet eine strukturierte Push-Nachricht (Telegram / ntfy) für das neu evaluierte Asset."""
    try:
        from notifications import send_telegram_alert, send_ntfy_alert
    except Exception:
        return

    name = eval_summary["name"]
    raw_sym = eval_summary["raw_symbol"]
    tier_badge = eval_summary["tier_badge"]
    rec = eval_summary["recommendation"]
    r_count = eval_summary["robust_setups_count"]
    tot_r = eval_summary["total_r"]
    tot_tr = eval_summary["total_trades"]

    lines = [
        f"🆕 <b>TradingView Watchlist: Neues Asset analysiert</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━",
        f"📌 <b>{name}</b> (<code>{raw_sym}</code>)",
        f"🎯 <b>Status:</b> {tier_badge}",
        f"💡 <b>Handlungsempfehlung:</b> {rec}",
        "",
        f"📊 <b>Backtest-Historie (Multi-Timeframe):</b>",
        f"• Gesamt-Trades simuliert: {tot_tr}",
        f"• Kumulativer Ertrag: {tot_r:+.2f}R",
        f"• Robuste Setups gefunden: {r_count}"
    ]

    if eval_summary["robust_setups"]:
        lines.append("\n⭐ <b>Top-Setups:</b>")
        for rs in eval_summary["robust_setups"][:2]:
            lines.append(f"  • {rs['timeframe']} ({rs['mode']}): PF {rs['profit_factor']} | OOS {rs['oos_r']:+.1f}R (WR {rs['win_rate']}%)")

    lines.append("\n🌐 <i>Vollständige Matrix im Dashboard einsehbar.</i>")
    msg = "\n".join(lines)

    send_telegram_alert(msg)
    send_ntfy_alert(
        title=f"Neues Asset: {name} {tier_badge}",
        message=f"{rec}\nTrades: {tot_tr} | Ertrag: {tot_r:+.1f}R",
        click_url="https://bbbdc.github.io/trading-dashboard/backtest_matrix.html"
    )


def evaluate_new_symbols(symbols: List[str]) -> List[Dict[str, Any]]:
    """Evaluierungs-Pipeline für eine Liste neu hinzugefügter Symbole."""
    if not symbols:
        return []

    print("\n" + "=" * 65)
    print(f"🚀 AUTOMATISCHES ONBOARDING FÜR {len(symbols)} NEUE ASSETS")
    print("=" * 65)

    all_evals = []
    if EVAL_LOG.exists():
        try:
            with open(EVAL_LOG, "r", encoding="utf-8") as f:
                all_evals = json.load(f)
        except Exception:
            all_evals = []

    new_results = []
    for s in symbols:
        res = evaluate_single_symbol(s)
        new_results.append(res)
        send_onboarding_notification(res)

        # In History einfügen
        all_evals.insert(0, res)

    all_evals = all_evals[:100]
    EVAL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(EVAL_LOG, "w", encoding="utf-8") as f:
        json.dump(all_evals, f, indent=2, ensure_ascii=False)

    return new_results


if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_syms = sys.argv[1:]
    else:
        test_syms = ["TRADEGATE:FMV", "TRADEGATE:BW9"]
    evaluate_new_symbols(test_syms)
