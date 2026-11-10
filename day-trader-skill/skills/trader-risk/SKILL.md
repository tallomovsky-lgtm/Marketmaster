---
name: trader-risk
description: "Position size and risk calculator (Hebrew output, receipt style): how many shares to buy so a stop-out costs exactly the planned risk, with risk/reward, break-even win rate and warnings. Use for /trader-risk, \"כמה מניות לקנות\", \"גודל פוזיציה\", \"מחשבון סיכון\", \"סטופ לוס\", \"position size\", \"risk reward\"."
---

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
