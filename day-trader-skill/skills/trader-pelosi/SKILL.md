---
name: trader-pelosi
description: "Congress stock-trade tracker (Hebrew output): collects recent stock trades disclosed by US Congress members (Pelosi and others) with web search, then renders a radar-style report with buys vs sells, disclosure delay, most traded tickers and the price move since each trade. Use for /trader-pelosi, \"מה פלוסי קנתה\", \"מעקב קונגרס\", \"עסקאות של חברי קונגרס\", \"congress trades\", \"Pelosi stock trades\"."
---

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

## Running it

- Run the script from this skill's folder with `python3` (standard library only, nothing to install).
- The script prints `REPORT: <path>` (an HTML page in the cream "receipt" style) and `SUMMARY: {json}`.
- **Show the page to the user.** In claude.ai the file lands in `/mnt/user-data/outputs/`; share it so it renders. In Claude Code, give the path, or publish it as an artifact if that tool is available.
- Then answer in the user's language (Hebrew by default) in 3–6 short lines, built only from `SUMMARY`. Lead with the one number that matters.

## When data can't be fetched

- Prices come from Yahoo Finance (`query1.finance.yahoo.com`, `query2.finance.yahoo.com`); some lists also try `api.nasdaq.com`.
- In claude.ai, code execution needs network access to those domains (Settings → Capabilities → code execution → allowed domains). If the script fails with a network error, tell the user exactly that, once, in plain words.
- If the user has the Interactive Brokers connector, you may pull bars with it instead, save them as JSON
  `{"TSLA": {"daily": [{"t": unix, "o":…, "h":…, "l":…, "c":…, "v":…}], "intraday": [5-minute bars]}}`
  and run the script with `TRADER_DATA=/path/data.json`. The scripts read that file instead of the network.
- Never invent prices, trades or headlines. If something is missing, say so.

## Ground rules

- This is research and education, not investment advice. Don't tell the user to buy or sell; describe what the data shows.
- Simulations are simulations, history is history: say "בעבר" / "בסימולציה", never "יקרה".
