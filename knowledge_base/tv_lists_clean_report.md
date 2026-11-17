# Watchlist-Audit: alle 7 TradingView-Listen

**Stand:** 16.11.2026, Basis ist die `live_watchlists.json`, die du mitgeschickt hast.

**Wichtig vorab:** Die Websuche wurde mir nicht freigegeben. Ich konnte also keinen Status live prüfen. Alles mit 🔍 bitte vor dem Löschen kurz in TradingView kontrollieren.

**Wie streng eine Streichung ist:**
- **MUSS:** Die Daten sind kaputt, tot oder unbrauchbar.
- **SOLL:** Das Symbol ist doppelt oder überflüssig.
- **OPTIONAL:** Ermessenssache.

**Eine Korrektur an der Vorgabe:** **NASDAQ:SNDK ist nicht delistet.** SanDisk wurde im Februar 2025 von Western Digital abgespalten und ist seitdem eine eigenständig gehandelte Nasdaq-Aktie. Ich empfehle, sie zu **behalten**.

---

## Liste 1: „Aktien" (ID 210838470)

### Ist-Zustand: 39 Ticker
PYPL, AMZN, GOOG, XETR:ADS, TSLA, AVGO, NVDA, PLTR, NFLX, MSFT, AMD, **SP:SPX, TVC:DJI, XETR:DAX, MULTPL:SHILLER_PE_RATIO_MONTH**, AAPL, META, HOOD, ORCL, KO, XETR:BAYN, XETR:NOV, UBER, **ECONOMICS:USMNO**, AG, UAA, IBM, CAG, SNDK, DELL, PANW, MU, **OTC:LIFFF**, INTC, MRVL, XYZ, **NASDAQ:SPCX**, CRWD, ACN

### Streichen
| Ticker | Stufe | Begründung |
|---|---|---|
| MULTPL:SHILLER_PE_RATIO_MONTH | MUSS | Monatliche Bewertungskennzahl ohne Kursdaten (OHLCV). Nicht handelbar, Scanner-Signale sind daraus nicht ableitbar. |
| ECONOMICS:USMNO | MUSS | Makro-Statistik (Auftragseingänge) mit monatlichem Takt. Nicht handelbar. |
| NASDAQ:SPCX 🔍 | MUSS* | *Nur wenn TradingView keine aktuellen Kerzen mehr liefert. Falls es noch der Nischen-ETF für SPACs ist: zu wenig Liquidität, zum Streichen reicht das trotzdem. |
| OTC:LIFFF 🔍 | SOLL | OTC-Pink-Zweitlisting: dünnes Volumen, große Spreads, lückenhafte Kerzen. Besser die Heimatbörse nehmen oder ganz streichen. |
| SP:SPX | SOLL → verschieben | Index, keine Aktie. Gehört in die Liste „Watchlist". |
| TVC:DJI | SOLL → verschieben | wie oben |
| XETR:DAX | SOLL → verschieben | wie oben |

**Behalten, obwohl sie fraglich wirken:**
- **SNDK** ist aktiv gehandelt (siehe oben).
- **XYZ** ist Block (früher SQ). Der Tickerwechsel 2025 ist korrekt.
- **AG** (First Majestic) ist zwar an den Silberpreis gekoppelt, aber gültig.
- **UAA und CAG** sind schwach, aber sauber notiert. CAG bringt sogar Basiskonsumgüter (Consumer Staples) in die Liste.

### Hinzufügen (Sektoren, die schwach mit Tech korrelieren)
| Ticker | Sektor | Begründung |
|---|---|---|
| NYSE:LLY | Healthcare | Größter Pharmawert, eigener Wachstumstreiber (GLP-1-Medikamente) |
| NYSE:JNJ | Healthcare | Defensiv, niedriges Beta |
| NYSE:XOM | Energie | Bisher fehlt Energie komplett. Profitiert, wenn Öl steigt. |
| NASDAQ:WMT 🔍 | Basiskonsum | Walmart ist im Dezember 2025 von der NYSE an die Nasdaq gewechselt. Das Präfix bitte prüfen. |
| NYSE:PG | Basiskonsum | Defensiver Anker |
| NYSE:JPM | Finanzen | Profitiert von Zinsen, bisher keine Bank in der Liste |
| NYSE:V | Finanzen | Zahlungsverkehr mit Qualität (ergänzt PYPL und XYZ) |
| NYSE:CAT | Industrie | Konjunktur- und Infrastrukturzyklus |
| NYSE:NEE | Versorger | Zinssensitiv, gegenläufig zu Wachstumswerten |

### Soll-Zustand: 41 Ticker
```
Tech/Halbleiter: NASDAQ:NVDA, NASDAQ:AVGO, NASDAQ:AMD, NASDAQ:MU, NASDAQ:INTC, NASDAQ:MRVL, NASDAQ:SNDK, NYSE:DELL, NYSE:IBM, NYSE:ORCL, NYSE:ACN
Software/Security: NASDAQ:MSFT, NASDAQ:PLTR, NASDAQ:PANW, NASDAQ:CRWD
Mega-Cap/Konsum-Tech: NASDAQ:AAPL, NASDAQ:AMZN, NASDAQ:GOOG, NASDAQ:META, NASDAQ:NFLX, NASDAQ:TSLA, NYSE:UBER
Fintech/Finanzen: NASDAQ:PYPL, NASDAQ:HOOD, NYSE:XYZ, NYSE:JPM, NYSE:V
Healthcare: NYSE:LLY, NYSE:JNJ, XETR:NOV, XETR:BAYN
Basiskonsum: NYSE:KO, NYSE:PG, NASDAQ:WMT, NYSE:CAG
Zyklischer Konsum: XETR:ADS, NYSE:UAA
Energie/Rohstoffe: NYSE:XOM, NYSE:AG
Industrie/Versorger: NYSE:CAT, NYSE:NEE
```

---

## Liste 2: „Commodities" (ID 211182381)

### Ist-Zustand: 9 Ticker
TVC:SILVER, TVC:GOLD, **RUS:BR1!**, TVC:PLATINUM, TVC:PALLADIUM, **CAPITALCOM:COPPER**, CAPITALCOM:ALUMINUM, **CAPITALCOM:CORN**, NYMEX:NG1!

### Streichen / Ersetzen
| Ticker | Stufe | Begründung |
|---|---|---|
| RUS:BR1! | MUSS | Brent-Kontrakt der Moskauer Börse. Seit 2022 sanktioniert, für westliche Trader nicht handelbar, Preise weichen von der Referenz ab. Ersatz: TVC:UKOIL. |
| CAPITALCOM:COPPER | SOLL | Preisfeed eines CFD-Brokers mit Broker-Spread. Ersatz: COMEX:HG1! (der Referenz-Future). |
| CAPITALCOM:CORN | SOLL | wie oben. Ersatz: CBOT:ZC1!. |
| CAPITALCOM:ALUMINUM | behalten | Es gibt keinen freien, liquiden Ersatz (LME ist nicht frei verfügbar). Akzeptabel. |

### Hinzufügen
| Ticker | Begründung |
|---|---|
| TVC:USOIL | WTI fehlt. Mit Brent zusammen ist die Spanne zwischen beiden (Brent-WTI-Spread) als Signal nutzbar. |
| CBOT:ZW1! | Weizen. Agrar-Diversifikation, schwach mit Metallen korreliert. |

### Soll-Zustand: 11 Ticker
```
Edelmetalle:  TVC:GOLD, TVC:SILVER, TVC:PLATINUM, TVC:PALLADIUM
Industrie:    COMEX:HG1!, CAPITALCOM:ALUMINUM
Energie:      TVC:UKOIL, TVC:USOIL, NYMEX:NG1!
Agrar:        CBOT:ZC1!, CBOT:ZW1!
```

---

## Liste 3: „Devisen" (ID 211182519)

### Ist-Zustand: 5 Ticker
**FX_IDC:EURINR**, TVC:DXY, **FX_IDC:EURCRC, FX_IDC:EURIDR, FX_IDC:EURLKR**

### Streichen
| Ticker | Stufe | Begründung |
|---|---|---|
| FX_IDC:EURINR | MUSS | Exotisches Paar, die Rupie ist kapitalverkehrsbeschränkt. FX_IDC liefert nur Indikationskurse. |
| FX_IDC:EURCRC | MUSS | Costa-Rica-Colón: praktisch kein Markt, riesige Spreads |
| FX_IDC:EURIDR | MUSS | Indonesische Rupiah: exotisch, gesteuerter Markt |
| FX_IDC:EURLKR | MUSS | Sri-Lanka-Rupie: kaum Liquidität, Kursrisiko durch frühere Staatspleite |

Diese vier sind wahrscheinlich Überbleibsel von Reise- oder Umrechnungsbedarf. Als Scanner-Basis taugen sie nicht.

### Hinzufügen
OANDA:EURUSD, OANDA:USDJPY, OANDA:GBPUSD, OANDA:USDCHF, OANDA:AUDUSD, OANDA:USDCAD, OANDA:EURCHF. Das sind die Majors plus EURCHF als Paar für sichere Häfen. Alle sind sehr liquide, haben enge Spreads, und der OANDA-Feed steckt schon in deinem Setup.

### Soll-Zustand: 8 Ticker
```
TVC:DXY, OANDA:EURUSD, OANDA:USDJPY, OANDA:GBPUSD, OANDA:USDCHF, OANDA:AUDUSD, OANDA:USDCAD, OANDA:EURCHF
```

---

## Liste 4: „Rohstoffe" (ID 318230601)

- **Ist-Zustand:** 0 Ticker, die Liste ist leer.
- **Streichen:** die **ganze Liste**. Sie ist leer und deckt dasselbe ab wie „Commodities". Der Scanner verbraucht damit nur einen unnötigen Sync- bzw. API-Aufruf.
- **Hinzufügen:** nichts.
- **Soll-Zustand:** **Liste löschen.** Alternativ „Commodities" in „Rohstoffe" umbenennen, falls dir der deutsche Name lieber ist. Dann gibt es nur noch eine Liste.

---

## Liste 5: „Tradegate Werte" (ID 352764127)

### Ist-Zustand: 27 Ticker, mit Zuordnung
| Code | Wert | | Code | Wert | | Code | Wert |
|---|---|---|---|---|---|---|---|
| MTE | Micron | | ABEA | Alphabet A | | CSA | Accenture |
| TL0 | Tesla | | PTX | Palantir | | 45C | CrowdStrike (vermutlich) |
| NVD | NVIDIA | | 2PP | PayPal | | IBM | IBM |
| RHM | Rheinmetall | | FB2A | Meta | | IFX | Infineon |
| AMD | AMD | | APC | Apple | | SAP | SAP |
| AMZ | Amazon | | 1YD | Broadcom | | FMV | First Majestic (vermutlich) |
| SIE | Siemens | | INL | Intel | | **YDX** 🔍 | wahrscheinlich Nebius (ex-Yandex) |
| MSF | Microsoft | | NFC | Netflix | | **SPX** 🔍 | Zuordnung unklar |
| 9MW | Marvell (vermutlich) | | | | | **34Q0** 🔍 / **BW9** 🔍 | Zuordnung unklar |

### Streichen
Nichts muss sicher raus. Es gibt aber zwei Prüfaufträge:
1. **YDX, SPX, 34Q0, BW9 🔍:** In TradingView öffnen. Wenn keine aktuellen Kerzen kommen oder die Aktie nicht zu deinem Universum passt, streichen.
2. **Doppelte Signale:** Rund 20 Werte sind dieselben Basiswerte wie in „Aktien", nur in EUR an der Tradegate. Für die Ausführung ist das sinnvoll, für den Scanner nicht. Der Scanner sollte nach Basiswert (ISIN) deduplizieren. Sonst zählt z. B. ein NVDA-Ausbruch doppelt.

### Hinzufügen (EUR-Pendants der neuen Sektor-Werte und deutsche Werte zur Streuung)
| Code 🔍 | Wert | Sektor |
|---|---|---|
| LLY | Eli Lilly | Healthcare |
| XONA | ExxonMobil | Energie |
| WMT | Walmart | Basiskonsum |
| PRG | Procter & Gamble | Basiskonsum |
| CMC | JPMorgan | Finanzen |
| ALV | Allianz | Versicherung (DE) |
| MUV2 | Münchener Rück | Versicherung (DE) |
| DTE | Deutsche Telekom | Telekom (DE, defensiv) |

Die Codes bitte vor dem Import in der TradingView-Symbolsuche bestätigen.

### Soll-Zustand: 35 Ticker (Annahme: alle vier 🔍-Codes sind gültig)
```
TRADEGATE: NVD, AMD, MTE, 1YD, INL, 9MW, IFX, IBM, CSA, SAP, MSF, PTX, 45C, APC, AMZ, ABEA, FB2A, NFC, TL0, 2PP,
           SIE, RHM, FMV, YDX, SPX, 34Q0, BW9,
           LLY, XONA, WMT, PRG, CMC, ALV, MUV2, DTE
```

---

## Liste 6: „Watchlist" (ID 24978044)

**Diagnose:** Das ist die älteste Liste und eine Mischung aus allem. Sie enthält die meisten toten Feeds und Duplikate im ganzen System. **Empfehlung:** Daraus wird eine reine Liste „Indizes & Makro-Benchmarks".

### Ist-Zustand: 32 Ticker
OANDA:SPX500USD, AMEX:SPY, TVC:NDX, TVC:UKX, TVC:NI225, BITSTAMP:BTCUSD, BITSTAMP:XRPUSD, COINBASE:EOSUSD, COINBASE:LTCUSD, FX_IDC:XAUUSD, AMEX:DIA, AMEX:GLD, AMEX:FXE, KRAKEN:DAIEUR, COINBASE:ETHUSD, COINBASE:BTCUSD, NASDAQ:TSLA, BINANCE:BATUSD, CME:BTC1!, NASDAQ:AAPL, KRAKEN:DOTUSD, KRAKEN:LINKUSD, KUCOIN:EWTUSDT, KUCOIN:EWTBTC, KUCOIN:LYXEUSDT, FTX:UNIUSD, POLONIEX:SWAPUSD, COINBASE:ETHBTC, POLONIEX:POLSUSDT, CRYPTOCAP:BTC.D, BITTREX:OCEANUSDT, FTX:TRUMP

### Streichen: 28 Ticker (davon 4 nach „Crypto" verschoben)
| Ticker | Stufe | Begründung |
|---|---|---|
| FTX:UNIUSD | MUSS | FTX ist seit November 2022 insolvent. Der Feed ist tot. |
| FTX:TRUMP | MUSS | wie oben (war ein Prognosemarkt-Token) |
| BITTREX:OCEANUSDT | MUSS | Bittrex hat Ende 2023 den Betrieb eingestellt. OCEAN ist 2024 in ASI (Fetch.ai) aufgegangen. |
| KUCOIN:LYXEUSDT | MUSS | LYXe ist der alte ERC-20-Token von LUKSO, abgelöst durch das LYX-Mainnet |
| COINBASE:EOSUSD 🔍 | MUSS | EOS wurde 2025 in Vaulta (A) umbenannt. Der Feed ist veraltet bzw. ausgesetzt. |
| KRAKEN:DAIEUR | MUSS | Stablecoin (inzwischen USDS/Sky). Liefert kein Kurssignal, im Grunde nur EURUSD. |
| KUCOIN:EWTUSDT / EWTBTC | MUSS | Kleiner Coin mit geringer Liquidität, dreifach geführt (auch KRAKEN:EWTUSD) |
| POLONIEX:SWAPUSD | MUSS | Kaum Liquidität, Börse mit Sicherheitsvorfällen (Hack 2023) |
| POLONIEX:POLSUSDT | MUSS | wie oben |
| BINANCE:BATUSD | SOLL | Randständiges USD-Paar, geringe Relevanz |
| OANDA:SPX500USD | SOLL | CFD-Doppel zu SPX/SPY |
| AMEX:DIA | SOLL | Doppel zum Dow-Index (TVC:DJI) |
| FX_IDC:XAUUSD, AMEX:GLD | SOLL | Gold ist doppelt bzw. dreifach. TVC:GOLD steht schon in „Commodities". |
| AMEX:FXE | SOLL | Euro-ETF, doppelt zu EURUSD in „Devisen" |
| NASDAQ:TSLA, NASDAQ:AAPL | SOLL | Doppelt in „Aktien" |
| BITSTAMP:BTCUSD, COINBASE:BTCUSD, COINBASE:ETHUSD, COINBASE:ETHBTC, CRYPTOCAP:BTC.D, KRAKEN:DOTUSD | SOLL | Doppelt in „Crypto" |
| BITSTAMP:XRPUSD, COINBASE:LTCUSD, KRAKEN:LINKUSD, CME:BTC1! | SOLL → verschieben | Gültig, gehören aber nach „Crypto" |

### Hinzufügen
| Ticker | Begründung |
|---|---|
| SP:SPX, TVC:DJI, XETR:DAX | Aus „Aktien" hierher verschoben |
| NASDAQ:QQQ | Nasdaq-100 mit echtem Volumen. Indizes selbst haben keine Volumendaten. |
| AMEX:IWM | Small Caps. Zeigt, wie breit eine Rally getragen ist. |
| TVC:VIX | Filter für das Marktumfeld (Risk-on/off). Nur Kontext, kein Handelssignal. |

### Soll-Zustand: 10 Ticker (Vorschlag: umbenennen in „Indizes & Makro")
```
USA:     SP:SPX, AMEX:SPY, TVC:NDX, NASDAQ:QQQ, TVC:DJI, AMEX:IWM
Global:  XETR:DAX, TVC:UKX, TVC:NI225
Regime:  TVC:VIX
```

---

## Liste 7: „Crypto" (ID 26061514)

### Ist-Zustand: 24 Ticker
BITSTAMP:BTCUSD, COINBASE:BTCUSD, INDEX:BTCUSD, BINANCE:BTCUSD, CRYPTOCAP:BTC.D, BITSTAMP:ETHUSD, COINBASE:ETHUSD, COINBASE:ETHBTC, BINANCE:DOTUSDT, KRAKEN:KSMUSD, UNISWAP3ETH:SAMAWETH_854B57.USD, KRAKEN:RPLUSD, KRAKEN:EWTUSD, CRYPTOCAP:TOTAL, BINANCE:ETHFIUSDT, COINBASE:SOLUSD, BINANCE:GMXUSDT, AERODROME:KVCMUSDC_5C0D76, BINANCE:ZECUSDT, COINBASE:AAVEUSD, BINANCE:AVAXUSDT, COINBASE:BCHUSD, COINBASE:CRVUSD, BINANCE:HYPEUSDT.P

### Streichen: 8 Ticker
| Ticker | Stufe | Begründung |
|---|---|---|
| UNISWAP3ETH:SAMAWETH_854B57.USD | MUSS | Einzelner DEX-Pool: wenig Liquidität im Pool, Manipulationsgefahr, Kerzen mit Lücken |
| AERODROME:KVCMUSDC_5C0D76 | MUSS | wie oben |
| BITSTAMP:BTCUSD, INDEX:BTCUSD, BINANCE:BTCUSD | SOLL | BTC steht viermal drin. Ein Referenz-Feed (Coinbase, USD-Spot mit viel Volumen) reicht. |
| BITSTAMP:ETHUSD | SOLL | Doppel zu COINBASE:ETHUSD |
| KRAKEN:EWTUSD | SOLL | Kleiner Coin mit wenig Liquidität, kaum Signalqualität |
| KRAKEN:KSMUSD | SOLL | Geringe Liquidität, läuft fast im Gleichschritt mit DOT (das bleibt drin) |

**Optional:** KRAKEN:RPLUSD (kleiner Coin mit hoher ETH-Abhängigkeit). Er bleibt vorerst drin.

**Hinweis:** BTC.D und TOTAL sind nicht handelbar. Sie bleiben trotzdem, weil sie intraday Daten zur Marktstruktur liefern. Der Scanner sollte sie aber als **Kontext** markieren und daraus keine Signale erzeugen.

### Hinzufügen
| Ticker | Begründung |
|---|---|
| CME:BTC1! | Aus „Watchlist": institutioneller Future, Referenz für CME-Kurslücken |
| BITSTAMP:XRPUSD | Aus „Watchlist": Top-5-Coin, sehr liquide |
| COINBASE:LTCUSD | Aus „Watchlist" |
| COINBASE:LINKUSD | Ersetzt KRAKEN:LINKUSD: liquideres Orderbuch, einheitliche Börse |
| BINANCE:BNBUSDT | Top-5-Coin, fehlte bisher |

### Soll-Zustand: 21 Ticker
```
Markt-Kontext:  CRYPTOCAP:BTC.D, CRYPTOCAP:TOTAL, COINBASE:ETHBTC
Bitcoin:        COINBASE:BTCUSD, CME:BTC1!
Large Caps:     COINBASE:ETHUSD, COINBASE:SOLUSD, BITSTAMP:XRPUSD, BINANCE:BNBUSDT
Layer 1:        BINANCE:AVAXUSDT, BINANCE:DOTUSDT, COINBASE:LTCUSD, COINBASE:BCHUSD, BINANCE:ZECUSDT
DeFi/Infra:     COINBASE:LINKUSD, COINBASE:AAVEUSD, COINBASE:CRVUSD, BINANCE:GMXUSDT, BINANCE:ETHFIUSDT, KRAKEN:RPLUSD
Perps:          BINANCE:HYPEUSDT.P
```

---

## Gesamtbilanz

| Liste | Ist | Raus | Rein | Soll |
|---|---|---|---|---|
| Aktien | 39 | 7 (3 davon verschoben) | 9 | **41** |
| Commodities | 9 | 3 (ersetzt) | 5 | **11** |
| Devisen | 5 | 4 | 7 | **8** |
| Rohstoffe | 0 | Liste weg | – | **gelöscht** |
| Tradegate | 27 | 0 (4 zu prüfen) | 8 | **35** |
| Watchlist | 32 | 28 (4 davon verschoben) | 7 | **10** |
| Crypto | 24 | 8 | 5 | **21** |
| **Gesamt** | **136** in 7 Listen | | | **126** in 6 Listen |

## Fazit: Datenqualität und Effizienz des Scanners

- **Tote oder unbrauchbare Feeds: 12 → 0.** Dazu zählen FTX ×2, Bittrex, LYXe, EOS, DAI, die sanktionierte MOEX-Brent, 2 DEX-Pools, Shiller-PE, USMNO und SPCX 🔍. Sie liefern leere oder verfälschte Kerzen und Scheinsignale.
- **Duplikate: über 20 → 0.** Vorher stand BTC sechsmal im System, Gold viermal, ETH dreimal, EWT dreimal. Der Scanner zählt jetzt jeden Basiswert nur einmal. Einzige Ausnahme ist Tradegate, und die ist bewusst gewählt. Dafür braucht es die ISIN-Deduplizierung im Scanner.
- **Diversifikation:** Bisher dominierten Tech-Werte mit hoher Beta-Korrelation. Neu dazu kommen Healthcare, Energie, Basiskonsum, Finanzen, Industrie und Versorger. Damit entstehen auch dann Signale, wenn Tech seitwärts läuft.
- **Klarere Struktur:** Jede Liste hat jetzt genau einen Zweck: Aktien, Ausführung in EUR (Tradegate), Rohstoffe, FX, Indizes/Makro, Krypto. Makro-Kontext (VIX, BTC.D, TOTAL) ist ausdrücklich als „kein Handelssignal" markiert.
- **Effizienz:** Die Zahl der Symbole sinkt nur um rund 7 %. Der Anteil der Ticker, die echte und eigenständige Signale liefern, steigt aber deutlich. Die Fehlalarme aus toten und illiquiden Feeds verschwinden ganz.

**Vor dem Umsetzen bitte prüfen (🔍):** NASDAQ:SPCX, OTC:LIFFF, die Tradegate-Codes YDX/SPX/34Q0/BW9 sowie die neuen Tradegate-Codes, das Präfix von NASDAQ:WMT und COINBASE:EOSUSD. Sag Bescheid, wenn ich daraus ein Skript für die Änderungen an `live_watchlists.json` bauen soll.
