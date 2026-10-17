# TradingView Integration & Methoden

Dieses Dokument beschreibt die verschiedenen technischen Möglichkeiten, um TradingView mit unserem System zu verknüpfen.

---

## 1. Integrations-Optionen

### Option A: Webhook Alerts (Event-gesteuert)
- **Funktionsweise:** TradingView Alerts senden bei Auslösen eines Indikators einen HTTP POST Request (JSON-Payload) an einen lokalen Server (z.B. FastAPI/Flask via ngrok/Cloudflare Tunnel).
- **Vorteile:** Offiziell unterstützt (ab TradingView Essential/Pro Plan), extrem zuverlässig, kein Account-Bann-Risiko, läuft 24/7.
- **Nachteil:** Erfordert Alert-Erstellung in TradingView.

### Option B: Browser-Automatisierung (Vision & Chart-Screening)
- **Funktionsweise:** Playwright/Puppeteer steuert einen Browser, loggt sich mit deiner Session ein, öffnet Layouts/Charts und erstellt Screenshots oder liest DOM-Elemente aus.
- **Vorteile:** Sieht exakt das, was du siehst (auch Custom Pine Scripts ohne Alert-Export), visuelle Chart-Analyse mit Vision-KI.
- **Nachteil:** Session-Handling / 2FA erforderlich, empfindlich gegenüber UI-Änderungen von TradingView.

### Option C: Python-Bibliotheken (Daten & Screener)
- **Funktionsweise:** Nutzung von Bibliotheken wie `tradingview-ta` (technische Analyse-Zusammenfassungen direkt von TV-Servern) oder WebSocket-Clients (`tvDatafeed`) für Rohdaten.
- **Vorteile:** Schnell, kein Browser nötig, ideal für Screener und Standardindikatoren.
- **Nachteil:** Custom Pine Script Indikatoren sind darüber meist nicht nativ ausführbar, es sei denn, man bildet die Logik in Python (Pandas-TA, Ta-Lib) nach.

---

## 2. Sicherheitsrichtlinien
- Credentials verbleiben lokal in `.env` (wird in `.gitignore` eingetragen).
- Session-Cookies für Browser-Automatisierung werden in einem isolierten Profil gespeichert.
