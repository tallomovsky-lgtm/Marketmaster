---
name: trader-earnings
description: "Earnings tools for US stocks (Hebrew output): how a stock moved on its last earnings reports (gap, day move, 5 days later) and its typical earnings move, plus the upcoming earnings calendar. Use for /trader-earnings, \"דוחות\", \"מתי הדוח של\", \"איך המניה מגיבה לדוחות\", \"תנועה צפויה בדוח\", \"earnings calendar\", \"earnings move\"."
---

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
