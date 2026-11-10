---
name: trader-premarket
description: "Pre-market morning brief for US day traders (Hebrew output): stock index futures, VIX, 10-year yield, dollar, oil, gold, bitcoin, pre-market gaps on a watchlist, and today's events and earnings. Use for /trader-premarket, \"סקירת בוקר\", \"מה קורה לפני הפתיחה\", \"פרה-מרקט\", \"חוזים עתידיים\", \"morning brief\", \"premarket\"."
---

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
