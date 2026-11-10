---
name: trader
description: "Day-trader-skill menu and router (Hebrew). Use when the user types /trader, asks what the trading skills can do, or asks a trading question without naming a tool, e.g. \"מה אתה יודע לעשות במסחר\", \"תפריט טריידר\", \"כלים למסחר יומי\", \"day trader tools\". Shows the 11-skill menu page and routes to the right trader-* skill."
---

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
