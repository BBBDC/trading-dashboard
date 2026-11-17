import subprocess
import json
from pathlib import Path

# Load current data
with open('/home/admin/trading/knowledge_base/autonomous_portfolio.json') as f:
    port = json.load(f)

with open('/home/admin/trading/knowledge_base/incubator_trades.json') as f:
    inc = json.load(f)

active_portfolio_trades = port.get('active_trades', [])
port_metrics = port.get('metrics', {})
circuit = port.get('circuit_breaker', {})

inc_active = inc.get('active_trades', [])
inc_closed = inc.get('closed_trades', [])[-5:]
inc_metrics = inc.get('metrics', {})

prompt = f"""Du bist Claude Opus 5.5, das führende quantitative Reasoning-Modell für institutionelle Portfolio-Governance, Risiko-Management und algorithmische Trading-Systeme.
Du agierst hier als der quantitative Chef-Auditor des Systems mit höchster analytischer Tiefe (High Effort Reasoning).

Analysiere den aktuellen Zustand des Gesamtsystems basierend auf den realen Produktionsdaten und beantworte die Fragen des Nutzers mit schonungsloser quantitativer Präzision:

======================================================================
1. REALE PRODUKTIONSDATEN DES SYSTEMS (STAND: 16. NOVEMBER 2026, 21:00 CET)
======================================================================

A. AUTONOMES KI-PORTFOLIO (Live-Trading):
- Aktive Trades: {len(active_portfolio_trades)} offene Positionen:
{json.dumps([{
    'symbol': t.get('symbol'),
    'name': t.get('name'),
    'direction': t.get('direction'),
    'horizon': t.get('horizon_label'),
    'entry_price': t.get('entry_price'),
    'current_price': t.get('current_price'),
    'pnl_pct': t.get('unrealized_pnl_pct'),
    'pnl_lev_pct': t.get('unrealized_pnl_leveraged_pct'),
    'trailing_active': t.get('trailing_active'),
    'status': t.get('health_status')
} for t in active_portfolio_trades], indent=2)}

- Portfolio Metrics:
  * Total Trades (All-Time): {port_metrics.get('total_trades')} (Win-Rate: {port_metrics.get('win_rate_pct')}%, PnL: {port_metrics.get('total_pnl_pct')}%)
  * Rolling Last 5: Win-Rate {port_metrics.get('rolling', {}).get('last_5', {}).get('win_rate_pct')}%, Lev PnL: +{port_metrics.get('rolling', {}).get('last_5', {}).get('total_leveraged_pnl_pct')}%
  * Rolling Last 10: Win-Rate {port_metrics.get('rolling', {}).get('last_10', {}).get('win_rate_pct')}%, Lev PnL: +{port_metrics.get('rolling', {}).get('last_10', {}).get('total_leveraged_pnl_pct')}%
  * Circuit Breaker: {circuit.get('reason')} (Daily PnL: {circuit.get('daily_pnl_r')}R)

- Verhalten im heutigen Scan:
  * NASDAQ:GOOG (4h SHORT) wurde durch [Triad Whitelist Guard] ABGEWIESEN (nicht auf der signifikanten OOS-Whitelist).
  * NYSE:XYZ (4h LONG) wurde durch [Triad Whitelist Guard] ABGEWIESEN.
  * TRADEGATE:SIE (4h) wurde als Stufe 2 'SHADOW_PAPER' eingestuft -> Kein Live-Trade ausgeführt.

B. POST-MORTEM LAB & AI INCUBATOR (Schattenbuch / Forschung):
- Aktuell offene Trades: {len(inc_active)} (0 aktiv!)
- Zuletzt geschlossene Trades:
{json.dumps([{
    'symbol': t.get('symbol'),
    'direction': t.get('direction'),
    'status': t.get('status'),
    'exit_reason': t.get('exit_reason'),
    'exit_time': t.get('exit_time')
} for t in inc_closed], indent=2)}
- Letzte Trades heute: SOLUSDT (SHORT, CLOSED_BE nach TP1 +1.5R Teilgewinn), FB2A.F (CLOSED_SL), ALV.DE (CLOSED_SL).
- Metrics: 562 Trades, 36.5% Win-Rate.

C. DIE VON FABLE 5.2 & GROK 4.7 IMPLEMENTIERTEN STRATEGIEN & REGELN:
1. 3-Stufen-Modell:
   - Stufe 1 (PILOT LIVE): Nur AVAX 30m, ETH 30m Short-only, AMZN 4h (0.15% Flat Risk).
   - Stufe 2 (SHADOW PAPER): NEAR 1h, AVAX 1h, SIE 4h/1h, ALV 4h Short, AMZN 1D (0% Live-Risiko, prospektives Testen).
   - Stufe 3 (GESTRICHEN): EUR/USD 8h (Reibung), AMZN/ALV 1h Long (Gap-Verluste), US-Megacap Shorts im Daily-Trend (87% Verlustquote).
2. Die 4 Kausalitäts- & Governance-Filter:
   - Triad Whitelist Guard & Direction-Lock (Portfolio Engine).
   - Kostengate auf Stop-Basis (cost_r <= 0.20: Reibung darf max 20% des Stop-Abstands betragen).
   - ATR / Close Gate (>= 0.35%: Reibung frisst sonst Edge).
   - Kausalitäts-Filter Guard: WMA 233 Trendfolge-Governance (keine Trend-konträren Trades im Rauschen).
   - Regel 0: Nur vollständig geschlossene Kerzen auswerten (kein Intrabar Repainting).

======================================================================
AUFTRAG AN CLAUDE OPUS 5.5:
======================================================================
Erstelle ein fundiertes, professionelles Exekutiv-Gutachten zu folgenden Punkten:

1. STATUS KI-PORTFOLIO:
   - Wie ist die Verfassung der 7 offenen Live-Positionen (DXY, UKX, GLD, GOLD, US100, 9MW, ADS)?
   - Was sagt der Kontrast zwischen All-Time Win-Rate (17.7%) und Rolling Last-5/10 (60%/40%) aus?

2. POST-MORTEM LAB (WARUM SIND HIER KEINE TRADES MEHR OFFEN?):
   - Erkläre die exakten mathematischen und markttechnischen Gründe, warum aktuell 0 Trades im Incubator offen sind.
   - Ist dieser Leerlauf ein Fehler oder ein Beweis für funktionierende Disziplin und Rausch-Unterdrückung?

3. STRATEGIE-AUFBAU:
   - Erläutere, wie die dahinter liegenden Strategien nach der Bereinigung nun sauber getrennt und aufgebaut sind (Pilot vs. Shadow vs. Gestrichen, Kausalitätsfilter).

4. ZWISCHENFAZIT ZU DEN FABLE-ÄNDERUNGEN:
   - Welches Fazit zieht Opus 5.5 zu den von Fable 5.2 vorgenommenen Eingriffen (Causal Filters, Kostengate, Stop-vor-TP Bias-Fix, Whitelist Lock)?
   - Wurde das System robuster und wie schützt es das Kapital in schwierigen Marktphasen wie dem aktuellen Krypto-Abverkauf?
"""

with open('/home/admin/trading/knowledge_base/opus_audit_prompt.txt', 'w') as f:
    f.write(prompt)

print("Prompt written successfully. Ready to invoke Claude Opus 5.5.")
