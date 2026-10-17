# Raspberry Pi Migration & Antigravity Agent Handoff Guide

Dieses Dokument dient als vollständiges Übergabeprotokoll und Arbeitsanweisung für den Antigravity-Agenten auf dem **Raspberry Pi**. Es enthält alle technischen Details, Befehle und Architektur-Regeln, um das Projekt auf dem Pi nahtlos fortzusetzen und im 24/7-Betrieb zu betreiben.

---

## 📌 1. Projekt-Überblick & Status Quo
* **Quell-Workspace (Mac):** `/Users/maximilianmayer/Documents/Trading`
* **Ziel-Workspace (Pi):** `~/Trading` (z.B. `/home/<user>/Trading`)
* **Architektur:** 100 % Pure Python 3.9+ (keine externen C-Bibliotheken, kein Matplotlib, kein Playwright – vollständig headless und für ARM64 optimiert).
* **Datenquelle:** Offizielle TradingView MCP-Schnittstelle (`mcp-tv-get-ohlcv`, `mcp-watchlist-list-watchlists`).
* **Zentrale Master-Steuerung:** `python3 update_dashboard.py` (führt Sync, Datenabruf, Indikatorberechnung, Chart-Rendering und Dashboard-Build in einem Durchlauf aus).

---

## 🚀 2. Schritt-für-Schritt-Anleitung: Übertragung auf den Raspberry Pi

### Schritt 2.1: Projektordner vom Mac auf den Pi kopieren
Führe auf deinem Mac im Terminal folgenden Befehl aus (ersetze `<user>` und `<pi-ip>` mit deinen Pi-Daten):

```bash
# Projektordner via rsync synchronisieren (sehr schnell & sauber):
rsync -avz --exclude='.git' --exclude='tradingview_profile' --exclude='__pycache__' /Users/maximilianmayer/Documents/Trading/ <user>@<pi-ip>:~/Trading/
```

*Hinweis:* Die Datei `.mcp_tokens.json` wird dabei mitkopiert. Sie enthält deine aktiven TradingView-OAuth-Token, die sich über `fetch_real_ohlcv_cache.py` bei Ablauf automatisch erneuern.

---

## ⚙️ 3. Inbetriebnahme auf dem Raspberry Pi

Sobald du dich per SSH auf deinem Raspberry Pi anmeldest (`ssh <user>@<pi-ip>`):

### Schritt 3.1: In das Projektverzeichnis wechseln
```bash
cd ~/Trading
```

### Schritt 3.2: Python-Umgebung prüfen
Da das gesamte System auf Standard-Bibliotheken basiert, ist in der Regel keine komplexe Installation nötig:
```bash
python3 --version   # Sollte Python 3.9 oder höher sein
```

### Schritt 3.3: Ersten Probelauf auf dem Pi starten
```bash
# Testlauf mit gecachten Daten (sehr schnell, ca. 20-30 Sekunden):
python3 update_dashboard.py --skip-download

# Oder vollständiger Live-Lauf mit TradingView MCP:
python3 update_dashboard.py
```

---

## 🌐 4. Git-Repository initialisieren & Web-Bereitstellung (vom Pi aus)

Wie gewünscht wird Git erst direkt auf dem Raspberry Pi initialisiert:

### Schritt 4.1: Lokales Git-Repository auf dem Pi initialisieren
```bash
cd ~/Trading
git init
git branch -M main
git add .
git commit -m "feat: initial commit of TradingView Super-Analyst system on Raspberry Pi"
```

### Schritt 4.2: Bereitstellung des Dashboards (3 Optionen für den Pi)

#### Option A: Lokaler Webserver im Heimnetzwerk (Sofort einsatzbereit)
Damit du das Dashboard von jedem Gerät (Mac, iPad, iPhone) im Heimnetzwerk aufrufen kannst:
```bash
# Startet einen ressourcenschonenden Webserver auf Port 8080:
python3 -m http.server 8080 --directory dashboard
```
Aufruf im Browser: `http://<RASPBERRY_PI_IP>:8080`

*Als dauerhafter Hintergrunddienst (systemd):*
Erstelle `/etc/systemd/system/trading-dashboard.service`:
```ini
[Unit]
Description=TradingView Dashboard Web Server
After=network.target

[Service]
Type=simple
User=maximilianmayer
WorkingDirectory=/home/maximilianmayer/Trading/dashboard
ExecStart=/usr/bin/python3 -m http.server 8080
Restart=always

[Install]
WantedBy=multi-user.target
```
Aktivieren mit: `sudo systemctl enable --now trading-dashboard`

#### Option B: Automatischer Push auf eine Website (z.B. GitHub Pages / Vercel)
Falls du das Dashboard über eine öffentliche URL abrufen möchtest:
1. Erstelle ein Repository auf GitHub (z.B. `trading-dashboard`).
2. Verbinde das Remote-Repository auf dem Pi:
   ```bash
   git remote add origin git@github.com:<username>/trading-dashboard.git
   ```
3. Das Master-Skript kann so erweitert werden, dass nach jedem Scan-Zyklus automatisch `git commit -am "chore: auto-update dashboard" && git push origin main` ausgeführt wird.

---

## ⏰ 5. 24/7 Automatisierung per Cron-Job auf dem Raspberry Pi

Damit das Dashboard rund um die Uhr automatisch alle Märkte überwacht und aktualisiert:

1. Öffne die Crontab auf dem Pi:
   ```bash
   crontab -e
   ```
2. Füge folgende Zeile ein (führt alle 4 Stunden, jeweils 5 Minuten nach Kerzenschluss, die gesamte Pipeline aus):
   ```cron
   # Alle 4 Stunden um 01:05, 05:05, 09:05, 13:05, 17:05, 21:05 Uhr UTC:
   5 1,5,9,13,17,21 * * * cd /home/<user>/Trading && /usr/bin/python3 update_dashboard.py >> /home/<user>/Trading/cron_update.log 2>&1
   ```

---

## 🧠 6. Arbeitsanweisungen für den Antigravity-Agenten auf dem Raspberry Pi

Wenn du auf dem Raspberry Pi mit Antigravity fortfährst, hat der Agent folgende Leitlinien strikt einzuhalten:

1. **Knowledge Base First:**
   * Vor jeder Änderung `knowledge_base/LEARNINGS_AND_RULES.md` und `knowledge_base/STRATEGY_RESEARCH.md` lesen.
   * Jede neue Erkenntnis und jeder gefundene Fehler müssen dort kontinuierlich dokumentiert werden.
2. **Datenqualität & MCP-First:**
   * Alle Marktdaten (`bars`) müssen primär über `fetch_real_ohlcv_cache.py` bzw. den TradingView MCP-Server bezogen werden.
   * Niemals synthetische Kerzen oder unüberprüfte Schätzwerte in die Charts einbauen.
3. **Plattform-Kompatibilität:**
   * Keine Bibliotheken mit schweren C-/GUI-Abhängigkeiten (wie Playwright, Chromium, Tkinter, Pygame) installieren.
   * Das System muss schlank und autark in Pure-Python bleiben, um auf dem Pi mit minimaler CPU- und RAM-Last zu laufen.
4. **Score-Integrität:**
   * Scores sind auf maximal 98 % für A+ Setups gedeckelt.
   * Neutrale Setups (`NEUTRAL`) liegen immer im Bereich 45–60 % (keine künstlich überhöhten Scores bei Signal-Konflikten).
5. **Chart-Dualität:**
   * Das Dashboard unterstützt sowohl die autarken SVG-Vektorcharts (für Offline/Pi-Betrieb) als auch das offizielle interaktive TradingView-Live-Widget im Modal. Diese Zweiteilung muss beibehalten werden.
