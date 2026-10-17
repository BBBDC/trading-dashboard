"""
Trading Report & Analysis Generator
Erstellt saubere Markdown-Berichte und Confluence-Zusammenfassungen.
"""

import time
from pathlib import Path
from .config import REPORTS_DIR


class ReportGenerator:
    def __init__(self):
        self.reports_dir = REPORTS_DIR

    def generate_single_report(self, chart_data):
        """Erstellt einen detaillierten Einzelbericht für ein analysiertes Symbol."""
        symbol = chart_data.get("symbol", "UNKNOWN")
        timeframe = chart_data.get("timeframe", "1D")
        safe_sym = symbol.replace(":", "_").replace("/", "_")
        timestamp = time.strftime("%Y-%m-%d_%H-%M")
        
        report_file = self.reports_dir / f"{timestamp}_{safe_sym}_{timeframe}.md"

        price = chart_data.get("currentPrice") or "N/A"
        change = chart_data.get("change") or ""
        ohlc = chart_data.get("ohlc", {})
        rsi = chart_data.get("rsi", {})
        vsa = chart_data.get("vsa", {})
        degen = chart_data.get("degencoder", {})

        content = []
        content.append(f"# Chart-Analyse: {symbol} ({timeframe})\n")
        content.append(f"- **Erfasst am:** {time.strftime('%Y-%m-%d %H:%M:%S')}")
        content.append(f"- **Aktueller Kurs:** `{price}` {change}")
        if ohlc:
            content.append(f"- **OHLC:** O: `{ohlc.get('open', '-')}` | H: `{ohlc.get('high', '-')}` | L: `{ohlc.get('low', '-')}` | C: `{ohlc.get('close', '-')}`")
        content.append(f"- **TradingView URL:** [{chart_data.get('url')}]({chart_data.get('url')})")
        content.append(f"- **Screenshot:** `reports/{chart_data.get('relativeScreenshot')}`\n")
        content.append("---\n")

        content.append("## 1. Indikatoren-Snapshot\n")
        content.append("| Indikator | Werte / Messung | Signal / Status |")
        content.append("|---|---|---|")

        # degencoder
        bands_str = ", ".join(degen.get("bands", [])[:3]) if degen.get("bands") else "Bänder aktiv"
        sig_degen = f"**{degen.get('signal')}**" if degen.get("signal") else "Neutral / Bänder"
        content.append(f"| **degencoder indicator** (`13 1.8 233`) | Bänder: `{bands_str}` | {sig_degen} |")

        # FVG & OB
        fvg_stat = "Aktiv (Zonen im Chart)" if chart_data.get("fvg_active") else "Inaktiv"
        ob_stat = "Aktiv (Zonen im Chart)" if chart_data.get("ob_active") else "Inaktiv"
        content.append(f"| **degencoder's FVGs** | Auto Fair Value Gaps | {fvg_stat} |")
        content.append(f"| **degencoder's OB Retro** | Retro Order Blocks | {ob_stat} |")

        # RSI
        rsi_val = f"{rsi.get('value')}" if rsi.get("value") is not None else "Berechnet"
        div_text = f"**{rsi.get('divergence')}**" if rsi.get("divergence") else "Keine neue Divergenz"
        content.append(f"| **RSI divergence** (`14`) | RSI: `{rsi_val}` | {div_text} |")

        # VSA Wyckoff
        vsa_vol = vsa.get("volume") or "Balken im Chart"
        content.append(f"| **VSA Wyckoff Volume** | Volumen: `{vsa_vol}` | Wyckoff Volume Spread Profile |")

        content.append("\n---\n")
        content.append("## 2. Struktur- & Confluence-Bewertung\n")
        
        confluence_score = 0
        notes = []

        if rsi.get("divergence") and "Bull" in rsi.get("divergence"):
            confluence_score += 2
            notes.append("🟢 **Bullische RSI-Divergenz:** Zeigt Erschöpfung des Verkaufsdrucks / Trendwende-Chance.")
        elif rsi.get("divergence") and "Bear" in rsi.get("divergence"):
            confluence_score -= 2
            notes.append("🔴 **Bärische RSI-Divergenz:** Zeigt Erschöpfung des Kaufdrucks / Korrektur-Risiko.")

        if degen.get("signal") == "BUY":
            confluence_score += 1
            notes.append("🟢 **degencoder BUY:** Trendfilter signalisiert Kaufinteresse.")
        elif degen.get("signal") == "SELL":
            confluence_score -= 1
            notes.append("🔴 **degencoder SELL:** Trendfilter signalisiert Abgabedruck.")

        if chart_data.get("ob_active") and chart_data.get("fvg_active"):
            notes.append("ℹ️ **SMC Zonen aktiv:** Reaktionen an Order Blocks & FVG-Liquiditätslücken im Auge behalten.")

        content.append(f"**Confluence Score:** `{confluence_score}`\n")
        if notes:
            for n in notes:
                content.append(f"- {n}")
        else:
            content.append("- Markt konsolidiert in seiner aktuellen Struktur ohne extremes Extrem-Signal.")

        content.append("\n---\n")
        content.append("## 3. Rohdaten der Legende\n")
        content.append("```text")
        for lt in chart_data.get("legendTexts", []):
            content.append(lt)
            content.append("-" * 30)
        content.append("```\n")

        with open(report_file, "w", encoding="utf-8") as f:
            f.write("\n".join(content))

        return str(report_file)

    def generate_summary(self, results):
        """Erstellt eine tabellarische Zusammenfassung über alle gescannten Symbole."""
        summary_file = self.reports_dir / "LATEST_SCAN_SUMMARY.md"

        content = []
        content.append("# Letzter Watchlist-Scan Summary\n")
        content.append(f"**Aktualisiert am:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        content.append("| Symbol | TF | Aktueller Kurs | RSI | Signale / Confluence | Screenshot |")
        content.append("|---|---|---|---|---|---|")

        for res in results:
            sym = res.get("symbol", "")
            tf = res.get("timeframe", "")
            price = res.get("currentPrice") or "-"
            chg = res.get("change") or ""
            
            rsi = res.get("rsi", {})
            rsi_display = f"{rsi.get('value')}" if rsi.get('value') is not None else "-"
            
            signals = []
            if rsi.get("divergence"):
                signals.append(f"🟢 Div" if "Bull" in rsi.get("divergence") else "🔴 Div")
            degen = res.get("degencoder", {})
            if degen.get("signal"):
                signals.append(f"🟢 {degen.get('signal')}" if degen.get("signal") == "BUY" else f"🔴 {degen.get('signal')}")

            sig_str = ", ".join(signals) if signals else "Neutral"
            screen_rel = res.get("relativeScreenshot", "")

            content.append(f"| **`{sym}`** | `{tf}` | `{price}` {chg} | `{rsi_display}` | {sig_str} | [Bild]({screen_rel}) |")

        with open(summary_file, "w", encoding="utf-8") as f:
            f.write("\n".join(content))

        return str(summary_file)
