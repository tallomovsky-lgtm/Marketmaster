---
name: trader-news
description: "Market news digest for stock tickers (Hebrew output): fetches the latest headlines from Yahoo Finance, then Claude translates them to Hebrew, explains why each matters and tags it bullish / bearish / neutral, with a sentiment meter. Use for /trader-news, \"חדשות על טסלה\", \"מה החדשות בשוק\", \"למה המניה יורדת\", \"news sentiment\", \"headlines for NVDA\"."
---

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
