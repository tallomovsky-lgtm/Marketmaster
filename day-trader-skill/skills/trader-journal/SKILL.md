---
name: trader-journal
description: "Trading journal (Hebrew output): logs trades to a CSV file and builds a performance report with win rate, profit factor, expectancy, max drawdown, equity curve and results by setup, ticker and weekday. Use for /trader-journal, \"יומן מסחר\", \"תרשום עסקה\", \"סגרתי עסקה\", \"כמה הרווחתי\", \"מה עובד לי\", \"trading journal\"."
---

# /trader-journal: יומן מסחר

```bash
python3 scripts/journal.py add --file journal.csv --ticker TSLA --side long --qty 50 --entry 364.18 --exit 370 \
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
