---
name: trader-timemachine
description: "Monte Carlo trade simulator (Hebrew output): runs 10,000 possible price paths for a stock from an entry price and counts how often the target is hit before the stop, with an animated chart. Use for /trader-timemachine, \"מכונת הזמן\", \"מה הסיכוי שאגיע ליעד\", \"סימולציה לעסקה\", \"will my trade hit the target\", \"monte carlo\"."
---

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
