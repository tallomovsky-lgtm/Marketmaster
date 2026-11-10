"""Source of every SKILL.md. build.py writes skills/<name>/SKILL.md = header + body + COMMON.md."""

SKILLS = {}

SKILLS["trader"] = ("""Day-trader-skill menu and router (Hebrew). Use when the user types /trader, asks what the trading skills can do, \
or asks a trading question without naming a tool, e.g. "מה אתה יודע לעשות במסחר", "תפריט טריידר", "כלים למסחר יומי", "day trader tools". \
Shows the 11-skill menu page and routes to the right trader-* skill.""", """
# /trader: the menu

Show the menu page, then route.

```bash
python3 scripts/menu.py
```

## Routing (pick the skill, then follow its own instructions)

| The user wants | Skill |
|---|---|
| find stocks / breakouts / gaps / "מה זז היום" | `trader-scanner` |
| odds a trade hits target before stop, "מה הסיכוי" | `trader-timemachine` |
| what Congress members bought / sold, "פלוסי" | `trader-pelosi` |
| morning brief, futures, "מה קורה לפני הפתיחה" | `trader-premarket` |
| headlines and sentiment on tickers | `trader-news` |
| support / resistance / pivots / VWAP for one stock | `trader-levels` |
| position size, how many shares, R:R | `trader-risk` |
| earnings reactions or earnings calendar | `trader-earnings` |
| sector rotation / heat map / market breadth | `trader-heatmap` |
| log trades, win rate, equity curve | `trader-journal` |

If the request is just "/trader" with nothing else, show the menu and ask what they want to check today, in one line.
""")

SKILLS["trader-scanner"] = ("""Stock chart scanner for US stocks (Hebrew output). Scans the most active US stocks (or the whole Nasdaq list when \
reachable) for breakouts, gaps, momentum, oversold RSI, 20/50 moving-average crosses, volatility squeezes and unusual volume, \
and draws a grid of mini charts. Use for /trader-scanner, "סורק מניות", "תמצא לי פריצות", "מה זז היום", "מניות במומנטום", \
"stock screener", "find breakouts".""", """
# /trader-scanner: סורק גרפים

```bash
python3 scripts/scanner.py                          # all setups, whole universe
python3 scripts/scanner.py --setup breakout         # breakout | newhigh | gap | momentum | oversold | cross | squeeze | volume (comma list ok)
python3 scripts/scanner.py --tickers TSLA,NVDA,AMD  # only the user's list
python3 scripts/scanner.py --min-price 10 --min-mcap 2e9 --deep 600 --top 24
```

- Map the request: "פריצות" → `breakout`, "גאפים" → `gap`, "מכירת יתר" / "זול" → `oversold`, "מומנטום" → `momentum`,
  "שיאים" → `newhigh`, "חציית ממוצעים" → `cross`, "לפני תנועה" / "התכווצות" → `squeeze`, "נפח" → `volume`.
- `--deep` is how many liquid names get a full 3-month chart check (default 500, about 25 requests). Don't raise it above 800.
- In "all" mode a stock needs 2+ signals to count. Results are sorted by a strength score.
- Before the US open the % change is from the last session; say so.
- In your reply: how many were scanned, how many passed, then the top 3–5 tickers with their setups.
""")

SKILLS["trader-timemachine"] = ("""Monte Carlo trade simulator (Hebrew output): runs 10,000 possible price paths for a stock from an entry \
price and counts how often the target is hit before the stop, with an animated chart. Use for /trader-timemachine, "מכונת הזמן", \
"מה הסיכוי שאגיע ליעד", "סימולציה לעסקה", "will my trade hit the target", "monte carlo".""", """
# /trader-timemachine: מכונת הזמן

```bash
python3 scripts/timemachine.py TSLA                                         # entry = last price, target/stop from volatility
python3 scripts/timemachine.py TSLA --entry 364.18 --target 370 --stop 358
python3 scripts/timemachine.py NVDA --target-pct 2 --stop-pct 1 --side long
python3 scripts/timemachine.py AMD --side short --entry 500 --target 490 --stop 505 --horizon 90m
python3 scripts/timemachine.py SPY --horizon 5d --sims 20000
```

- `--horizon`: `session` (rest of today, or a full day when the market is closed), `30m`/`90m`…, `1d`/`3d`/`5d`.
- How it works: bootstraps real 5-minute returns from the last 60 days, scaled to the last 5 days' volatility, drift removed.
  If intraday data is missing it falls back to daily returns split into 5-minute steps (the page says which).
- Short trades: target below entry, stop above.
- In your reply give: % target first, % stop first, % neither, the break-even win rate vs the simulated one, and the expected value per share.
  Always call it a simulation ("סימולציה, לא תחזית").
""")

SKILLS["trader-pelosi"] = ("""Congress stock-trade tracker (Hebrew output): collects recent stock trades disclosed by US Congress members \
(Pelosi and others) with web search, then renders a radar-style report with buys vs sells, disclosure delay, most traded tickers \
and the price move since each trade. Use for /trader-pelosi, "מה פלוסי קנתה", "מעקב קונגרס", "עסקאות של חברי קונגרס", \
"congress trades", "Pelosi stock trades".""", """
# /trader-pelosi: מעקב קונגרס

There is no free open API for these disclosures, so **you collect the data first**, then the script renders and enriches it.

1. Search the web for recent disclosures that match the request (a member, a ticker, or "latest"). Good sources:
   capitoltrades.com, quiverquant.com/congresstrading, disclosures-clerk.house.gov, efdsearch.senate.gov, and news reports
   that quote filings. Prefer the filing itself or a tracker page over commentary.
2. Write what you found to `trades.json`, one object per transaction, only with facts you saw:
   ```json
   [{"member":"Nancy Pelosi","party":"D","chamber":"House","ticker":"NVDA","asset":"NVIDIA Corp",
     "type":"buy","amount":"$1,000,001 - $5,000,000","traded":"2026-09-12","disclosed":"2026-10-02",
     "source":"https://..."}]
   ```
   `type`: buy | sell | exchange. Options: put the underlying ticker and say "call options" in `asset`.
   Leave a field out rather than guess it. Aim for 10–40 recent trades.
3. Render (adds price change since each trade from Yahoo):
   ```bash
   python3 scripts/pelosi.py trades.json
   python3 scripts/pelosi.py trades.json --title "מה פלוסי קנתה"
   ```
- In your reply: number of trades, buy/sell split, the most traded tickers, average disclosure delay, and name your sources.
- Remind once that disclosures arrive up to 45 days late, so copying them is not the same trade.
""")

SKILLS["trader-premarket"] = ("""Pre-market morning brief for US day traders (Hebrew output): stock index futures, VIX, 10-year yield, \
dollar, oil, gold, bitcoin, pre-market gaps on a watchlist, and today's events and earnings. Use for /trader-premarket, \
"סקירת בוקר", "מה קורה לפני הפתיחה", "פרה-מרקט", "חוזים עתידיים", "morning brief", "premarket".""", """
# /trader-premarket: לפני הפעמון

```bash
python3 scripts/premarket.py
python3 scripts/premarket.py --watchlist TSLA,NVDA,PLTR,AMD,SMCI
python3 scripts/premarket.py --notes notes.json
```

- Use the user's tickers for `--watchlist` if they gave any (or ones they mentioned earlier); otherwise the default list of popular names.
- **Events:** search the web for today's US economic calendar (CPI, jobs, Fed speakers, FOMC…) and major earnings before
  the open, then pass them in `notes.json` (times in New York time):
  ```json
  {"summary": "שני משפטים בעברית על מה שמזיז את השוק הבוקר",
   "events": [{"time": "08:30", "title": "מדד המחירים לצרכן (CPI)", "impact": "high"}]}
  ```
  `impact`: high | medium | low. Only real, sourced events. Skip `--notes` if you couldn't verify any.
- Gaps are measured from the official close of the previous session.
- In your reply: direction of futures, VIX level, the 3 biggest gaps, and the key events with times (also in Israel time: NY + 7h, or +6h in the weeks when the clock changes don't line up).
""")

SKILLS["trader-news"] = ("""Market news digest for stock tickers (Hebrew output): fetches the latest headlines from Yahoo Finance, \
then Claude translates them to Hebrew, explains why each matters and tags it bullish / bearish / neutral, with a sentiment meter. \
Use for /trader-news, "חדשות על טסלה", "מה החדשות בשוק", "למה המניה יורדת", "news sentiment", "headlines for NVDA".""", """
# /trader-news: חדשות שוק

Two steps: fetch, then you enrich, then render.

```bash
python3 scripts/news.py fetch TSLA NVDA --out news.json         # add --market for general market headlines
```

Open `news.json`. For **every** item fill:
- `title_he`: a faithful Hebrew translation of the headline (no added facts).
- `why_he`: one short Hebrew sentence on why it matters for the stock, based only on the headline (and the article if you read it).
- `sentiment`: `bull`, `bear` or `neutral` for the tickers involved.
And at the top level `brief_he`: 2–3 Hebrew sentences that tie the headlines to the price moves in `moves`.

```bash
python3 scripts/news.py render news.json
```

- If the user asks "why is X down/up", lead with the headline that best explains the move, and say if nothing clearly does.
""")

SKILLS["trader-levels"] = ("""Key price levels for one stock (Hebrew output): yesterday's high/low/close, pivot points, pre-market range, \
VWAP, 20/50/200-day moving averages, 52-week range and swing support/resistance zones on a candlestick chart. Use for \
/trader-levels, "רמות תמיכה והתנגדות", "איפה התמיכה של", "פיבוטים", "רמות למסחר היום", "support and resistance".""", """
# /trader-levels: רמות מפתח

```bash
python3 scripts/levels.py TSLA
python3 scripts/levels.py NVDA --days 120     # more candles on the chart
```

- One ticker per run; for several, run it per ticker.
- In your reply: the price now, the nearest resistance and support (name + price + distance %), and where levels cluster.
  Zones marked ×N were turning points N times in the last 6 months.
""")

SKILLS["trader-risk"] = ("""Position size and risk calculator (Hebrew output, receipt style): how many shares to buy so a stop-out costs \
exactly the planned risk, with risk/reward, break-even win rate and warnings. Use for /trader-risk, "כמה מניות לקנות", \
"גודל פוזיציה", "מחשבון סיכון", "סטופ לוס", "position size", "risk reward".""", """
# /trader-risk: מחשבון פוזיציה

```bash
python3 scripts/risk.py --account 25000 --risk-pct 1 --entry 364.18 --stop 358 --target 370
python3 scripts/risk.py --account 10000 --risk-usd 100 --ticker TSLA          # entry = last price, stop = 1 daily ATR
python3 scripts/risk.py --account 25000 --ticker AMD --side short --atr-mult 0.5 --target 480
python3 scripts/risk.py --account 25000 --entry 50 --stop 48.5 --max-pos-pct 25 --commission 1
```

- Ask only for what's missing and essential: account size and either a stop price or a ticker. Default risk is 1% of the account.
- "25 אלף" = 25000. Assume dollars unless the user says shekels (then say the result is in the same currency).
- In your reply: the share count, position value, the real dollar risk, R:R, and any warning the script raised.
""")

SKILLS["trader-earnings"] = ("""Earnings tools for US stocks (Hebrew output): how a stock moved on its last earnings reports \
(gap, day move, 5 days later) and its typical earnings move, plus the upcoming earnings calendar. Use for /trader-earnings, \
"דוחות", "מתי הדוח של", "איך המניה מגיבה לדוחות", "תנועה צפויה בדוח", "earnings calendar", "earnings move".""", """
# /trader-earnings: דוחות

**One stock, past reactions**
```bash
python3 scripts/earnings.py history NVDA
python3 scripts/earnings.py history NVDA --dates 2026-08-27,2026-05-28,2026-02-25,2025-11-19
```
Report dates come from Nasdaq. If the script says Nasdaq is unreachable, search the web for the company's last 4–8 report
dates and pass them with `--dates`.

**Calendar**
```bash
python3 scripts/earnings.py calendar --days 5
python3 scripts/earnings.py calendar --file cal.json
```
If Nasdaq is unreachable, search the web for this week's notable US earnings and write `cal.json`:
`[{"date":"2026-11-12","symbol":"CSCO","name":"Cisco","time":"after","eps_forecast":"0.98"}]`
(`time`: before | after). Only verified dates.

- In your reply: the typical move (±%), how many times it rose, the biggest reaction, and the next report date if known.
""")

SKILLS["trader-heatmap"] = ("""Market heat map (Hebrew output): sector ETF board, index changes, a market-cap treemap of the largest US \
stocks colored by % change, and market breadth (advancers vs decliners). Use for /trader-heatmap, "מפת חום", "איזה סקטור עולה", \
"לאן הכסף זורם", "רוחב שוק", "sector rotation", "market heatmap".""", """
# /trader-heatmap: מפת חום

```bash
python3 scripts/heatmap.py
python3 scripts/heatmap.py --stocks 120
```

- Changes are vs the previous close; before the open they describe the last session.
- In your reply: the 4 indices, the leading and lagging sectors, breadth, and the 3 biggest movers among the large caps.
""")

SKILLS["trader-journal"] = ("""Trading journal (Hebrew output): logs trades to a CSV file and builds a performance report with win rate, \
profit factor, expectancy, max drawdown, equity curve and results by setup, ticker and weekday. Use for /trader-journal, \
"יומן מסחר", "תרשום עסקה", "סגרתי עסקה", "כמה הרווחתי", "מה עובד לי", "trading journal".""", """
# /trader-journal: יומן מסחר

```bash
python3 scripts/journal.py add --file journal.csv --ticker TSLA --side long --qty 50 --entry 364.18 --exit 370 \\
    --date 2026-11-10 --setup "פריצה" --note "מעל שיא הבוקר" --fees 1
python3 scripts/journal.py report --file journal.csv
python3 scripts/journal.py report --file journal.csv --since 2026-10-01
```

- Parse trades from free text ("קניתי 50 TSLA ב-364 ומכרתי ב-370") into `add`. Ask only if qty, entry or exit is missing.
- If the user uploads a broker export, map its columns to `date,ticker,side,qty,entry,exit,fees,setup,note`, write a new CSV, then `report`.
- Where the CSV lives: in Claude Code keep it in the project folder (default `journal.csv`). In claude.ai the sandbox resets
  between chats, so after adding trades also save `journal.csv` to `/mnt/user-data/outputs/` and tell the user to keep it
  and upload it next time.
- In your reply: net P&L, win rate, profit factor, the best and worst setup, and one honest observation from the numbers.
""")
