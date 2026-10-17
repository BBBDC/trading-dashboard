import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / "tradingview_profile"
OUTPUT_DIR = BASE_DIR / "knowledge_base" / "chart_captures"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def test_navigator():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=True,
            viewport={"width": 1920, "height": 1080},
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = context.pages[0] if context.pages else context.new_page()

        print("Lade Basis-Chart...")
        page.goto("https://www.tradingview.com/chart/LJynlFJq/", wait_until="domcontentloaded")
        page.wait_for_timeout(10000)

        print("Initialer Titel:", page.title())
        print("URL:", page.url)

        # Teste Symbol-Wechsel via Tastatureingabe
        # Klicke in die Mitte des Charts
        page.mouse.click(960, 540)
        page.wait_for_timeout(1000)

        # Wechsle Intervall zu 4h (240)
        page.keyboard.type("240")
        page.wait_for_timeout(1000)
        page.keyboard.press("Enter")
        page.wait_for_timeout(5000)

        print("Nach 240:", page.title())

        # Screenshot
        test_shot = OUTPUT_DIR / "test_initial.png"
        page.screenshot(path=str(test_shot))
        print("Screenshot gespeichert:", test_shot)

        context.close()

if __name__ == "__main__":
    test_navigator()
