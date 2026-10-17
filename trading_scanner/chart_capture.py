"""
TradingView Chart Capture Engine
Steuert den Browser, lädt Symbole & Zeiteinheiten, bereinigt die UI,
liest Indikatoren aus und speichert hochauflösende Screenshots.
"""

import time
import re
from pathlib import Path
from playwright.sync_api import sync_playwright
from .config import PROFILE_DIR, LAYOUT_ID, TIMEFRAME_MAP, SCREENSHOTS_DIR


class ChartCapture:
    def __init__(self, headless=True):
        self.headless = headless
        self.playwright = None
        self.context = None
        self.page = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def start(self):
        """Startet den persistenten Browser-Kontext."""
        self.playwright = sync_playwright().start()
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=self.headless,
            viewport={"width": 1920, "height": 1080},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--hide-scrollbars"
            ]
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

    def close(self):
        """Schließt den Browser sauber."""
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()

    def clean_ui(self):
        """Entfernt störende Popups, Toasts, Promo-Banner und Dialoge aus dem DOM."""
        try:
            self.page.evaluate("""() => {
                const selectors = [
                    '[class*="toast-"]',
                    '[class*="dialog-"]',
                    '.tv-dialog',
                    'div[data-name="toast-container"]',
                    'div[class*="banner-"]',
                    'div:has(> button:has-text("Start free trial"))'
                ];
                selectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        try { el.remove(); } catch(e) {}
                    });
                });
            }""")
        except Exception:
            pass

    def capture_chart(self, symbol="COINBASE:BTCUSD", timeframe="1D", wait_seconds=9):
        """
        Navigiert zum gewünschten Symbol & Timeframe,
        liest Indikatorwerte aus und nimmt einen Screenshot auf.
        """
        interval_code = TIMEFRAME_MAP.get(timeframe, "D")
        encoded_symbol = symbol.replace(":", "%3A")
        target_url = f"https://www.tradingview.com/chart/{LAYOUT_ID}/?symbol={encoded_symbol}&interval={interval_code}"

        print(f"[{symbol} | {timeframe}] Lade Chart: {target_url}...")
        self.page.goto(target_url, wait_until="domcontentloaded")

        # Wartezeit für Kerzen & Indikator-Berechnung
        time.sleep(wait_seconds)
        self.clean_ui()

        # Dateinamen für Screenshot vorbereiten
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', symbol)
        screenshot_path = SCREENSHOTS_DIR / f"{safe_name}_{timeframe}.png"

        # Screenshot erstellen
        self.page.screenshot(path=str(screenshot_path), full_page=False)

        # Robuste Extraktion aller Legenden-Bereiche
        raw_legends = self.page.evaluate("""() => {
            const list = [];
            const elements = document.querySelectorAll('div[class*="legend-"], div[class*="sources-"], div[data-name="legend"]');
            elements.forEach(el => {
                const text = el.innerText.trim();
                if (text && text.length > 5 && !list.includes(text)) {
                    list.push(text);
                }
            });
            return {
                title: document.title,
                url: window.location.href,
                legends: list
            };
        }""")

        parsed = self._parse_indicator_data(raw_legends["legends"], symbol, timeframe)
        parsed["title"] = raw_legends["title"]
        parsed["url"] = raw_legends["url"]
        parsed["screenshotPath"] = str(screenshot_path)
        parsed["relativeScreenshot"] = f"screenshots/{screenshot_path.name}"
        parsed["legendTexts"] = raw_legends["legends"]

        return parsed

    def _parse_indicator_data(self, legends, symbol, timeframe):
        """Parst die extrahierten Legendenblöcke in strukturierte Felder."""
        data = {
            "symbol": symbol,
            "timeframe": timeframe,
            "currentPrice": None,
            "change": None,
            "ohlc": {},
            "rsi": {"value": None, "divergence": None},
            "vsa": {"volume": None, "params": "20 2.2 1.8 1.2 0.8 0.4"},
            "degencoder": {"params": "13 1.8 233", "bands": [], "signal": None},
            "fvg_active": False,
            "ob_active": False
        }

        full_text = "\n".join(legends)

        # OHLC & Preis aus Haupt-Legende
        m_price = re.search(r'C\s*([0-9,.]+)\s*([−+−-]?\s*[0-9,.]+\s*\([−+−-]?[0-9,.]+%\))', full_text)
        if m_price:
            data["currentPrice"] = m_price.group(1)
            data["change"] = m_price.group(2)

        m_o = re.search(r'O\s*([0-9,.]+)', full_text)
        m_h = re.search(r'H\s*([0-9,.]+)', full_text)
        m_l = re.search(r'L\s*([0-9,.]+)', full_text)
        if m_o: data["ohlc"]["open"] = m_o.group(1)
        if m_h: data["ohlc"]["high"] = m_h.group(1)
        if m_l: data["ohlc"]["low"] = m_l.group(1)
        if m_price: data["ohlc"]["close"] = m_price.group(1)

        # FVG & Order Block Flags
        if "degencoder's FVGs" in full_text:
            data["fvg_active"] = True
        if "degencoder's OB" in full_text:
            data["ob_active"] = True

        # Degencoder Bänder
        m_bands = re.findall(r'[0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2}', full_text)
        if m_bands:
            # Relevante Band-Level filtern
            data["degencoder"]["bands"] = m_bands[:5]

        # BUY / SELL Signale
        if "BUY" in full_text:
            data["degencoder"]["signal"] = "BUY"
        elif "SELL" in full_text:
            data["degencoder"]["signal"] = "SELL"

        # RSI Divergenz
        for block in legends:
            if "RSI divergence" in block:
                lines = [l.strip() for l in block.split("\n") if l.strip()]
                # Suche nach Zahlenwert (z.B. 49.89 oder 52.88)
                for l in lines:
                    if re.match(r'^[0-9]{1,3}(?:\.[0-9]{1,2})?$', l) and l not in ["14"]:
                        data["rsi"]["value"] = float(l)
                        break

        # Divergenz-Labels prüfen
        if "Bull" in full_text:
            data["rsi"]["divergence"] = "Bullische Divergenz (Bull)"
        elif "Bear" in full_text:
            data["rsi"]["divergence"] = "Bärische Divergenz (Bear)"

        # VSA Volume
        for block in legends:
            if "VSA Wyckoff Volume" in block:
                lines = [l.strip() for l in block.split("\n") if l.strip()]
                for l in reversed(lines):
                    if ("K" in l or "M" in l) and re.match(r'^[0-9,.]+\s*[KM]$', l):
                        data["vsa"]["volume"] = l
                        break

        return data
