#!/usr/bin/env python3
"""/trader-premarket: the morning brief before the opening bell. Futures, VIX, yields,
dollar, oil, gold, bitcoin, pre-market gaps on your watchlist, today's earnings and
(optionally) an events list Claude collected with web search.

  python3 premarket.py
  python3 premarket.py --watchlist TSLA,NVDA,PLTR,AMD
  python3 premarket.py --notes notes.json     # {"events":[{"time":"08:30","title":"CPI","impact":"high"}],
                                              #  "summary":"..."}
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradelib as T  # noqa: E402

MACRO = [("ES=F", "חוזי S&P 500"), ("NQ=F", "חוזי נאסד\"ק"), ("YM=F", "חוזי דאו"), ("RTY=F", "חוזי ראסל"),
         ("^VIX", "מדד הפחד VIX"), ("^TNX", "תשואת 10 שנים"), ("DX-Y.NYB", "מדד הדולר"), ("CL=F", "נפט"),
         ("GC=F", "זהב"), ("BTC-USD", "ביטקוין")]
DEFAULT_WATCH = "TSLA,NVDA,AAPL,AMD,META,AMZN,MSFT,GOOGL,PLTR,AVGO,MU,COIN,MSTR,NFLX,HOOD,SMCI"


def _mins(b):
    d = T.ny(b["t"])
    return d.hour * 60 + d.minute


def gap(sym, daily=None):
    """Gap = latest price (pre-market included) vs the last regular-session close of the previous day.
    Computed from the bars themselves: Yahoo's chartPreviousClose can point one session too far back."""
    try:
        d = T.yahoo_chart(sym, "5d", "5m", prepost=True)
    except Exception:  # noqa: BLE001
        return None
    m, bars = d["meta"], d["bars"]
    if not bars:
        return None
    days = sorted({T.ny(b["t"]).date() for b in bars})
    cur = days[-1]
    tb = [b for b in bars if T.ny(b["t"]).date() == cur]
    older = [b for b in bars if T.ny(b["t"]).date() < cur and 9 * 60 + 30 <= _mins(b) < 16 * 60]
    if not older:
        return None
    prev = older[-1]["c"]
    if daily and daily.get("c"):  # official close (closing auction) of that same day
        same = [c for t, c in zip(daily["t"], daily["c"]) if T.ny(t).date() == T.ny(older[-1]["t"]).date()]
        if same:
            prev = same[-1]
    last = tb[-1]["c"]
    return {"symbol": sym, "name": m.get("shortName") or m.get("longName") or "", "prev": prev, "last": last,
            "gap": T.pct(last, prev), "closes": [b["c"] for b in tb]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watchlist", default=DEFAULT_WATCH)
    ap.add_argument("--notes", help="JSON with events / summary gathered by Claude")
    ap.add_argument("--out")
    a = ap.parse_args()
    watch = [s.strip().upper() for s in a.watchlist.split(",") if s.strip()]

    syms = [s for s, _ in MACRO]
    lines = T.yahoo_spark(syms, "1d", "5m")       # intraday shape for the mini charts
    daily = T.yahoo_spark(syms, "5d", "1d")       # change vs the last settlement / close
    macro = []
    for s, n in MACRO:
        dl, ln = daily.get(s.upper()), lines.get(s.upper())
        if not dl or len(dl["c"]) < 2:
            continue
        last = ln["c"][-1] if ln and ln["c"] else dl["c"][-1]
        macro.append((s, n, last, T.pct(last, dl["c"][-2]), (ln or dl)["c"]))
    wdaily = T.yahoo_spark(watch, "5d", "1d")
    with ThreadPoolExecutor(max_workers=3) as ex:
        gaps = [g for g in ex.map(lambda s: gap(s, wdaily.get(s)), watch) if g]
    gaps.sort(key=lambda g: -abs(g["gap"] or 0))

    earn, earn_note = [], ""
    try:
        earn = sorted(T.nasdaq_earnings(T.now_ny().date()), key=lambda r: -r["mcap"])[:12]
    except Exception:  # noqa: BLE001
        earn_note = "לוח הדוחות של Nasdaq לא זמין מכאן."
    notes = {}
    if a.notes:
        with open(a.notes, encoding="utf-8") as f:
            notes = json.load(f)

    es = next((m for m in macro if m[0] == "ES=F"), None)
    vix = next((m for m in macro if m[0] == "^VIX"), None)
    mood, word = "שקט", "פתיחה שטוחה"
    if es and es[3] is not None:
        if es[3] > 0.25:
            word, mood = "עולה", "up"
        elif es[3] < -0.25:
            word, mood = "יורד", "down"
    head = (f'<div class="headline">השוק <span class="o">{word}</span> לפני הפתיחה</div>' if word != "פתיחה שטוחה"
            else '<div class="headline">צפויה <span class="o">פתיחה שטוחה</span></div>')
    if notes.get("summary"):
        head += f'<div class="sheet" style="font-size:16px;line-height:1.75">{T.esc(notes["summary"])}</div>'

    def mtile(s, n, v, p, cs):
        dec = 2 if s not in ("BTC-USD",) else 0
        unit = "%" if s == "^TNX" else ""
        return (f'<div class="tile" style="min-height:0"><div style="font-weight:800;font-size:13.5px">{n}</div>'
                f'<div class="row" style="justify-content:space-between;margin-top:2px"><b style="font-size:22px;direction:ltr">'
                f'{T.fmt_price(v, dec)}{unit}</b><span class="chip {T.tone(p)}" dir="ltr">{T.fmt_pct(p)}</span></div>'
                f'{T.spark_svg(cs, 220, 40, T.GREEN if (p or 0) >= 0 else T.RED, 1.6)}</div>')
    mgrid = f'<div class="sheet"><h2>מאקרו ועתידיים</h2><div class="grid g4">{"".join(mtile(*m) for m in macro)}</div></div>'

    gtiles = "".join(
        f'<div class="tile{" hit" if i < 4 else ""}"><div class="tk"><span class="ch {T.tone(g["gap"])}">{T.fmt_pct(g["gap"])}</span>{g["symbol"]}</div>'
        f'<div class="nm">{T.esc(g["name"][:30])} · {T.fmt_price(g["last"])}</div>'
        f'{T.spark_svg(g["closes"], 220, 50, T.INK, 1.7, g["prev"])}</div>' for i, g in enumerate(gaps))
    ggrid = (f'<div class="sheet"><h2>גאפים ברשימת המעקב</h2><div class="grid g4">{gtiles}</div>'
             f'<div class="legend"><span><i style="border-color:{T.ORANGE};border-top-style:dashed"></i>סגירה אתמול</span>'
             f'<span>הגרף: היום כולל פרה-מרקט, נרות 5 דקות</span></div></div>')

    rec_rows = [(f'{T.ltr(e.get("time", ""))} · {T.esc(e.get("title", ""))}',
                 T.chip({"high": "השפעה גבוהה", "medium": "בינונית", "low": "נמוכה"}.get(e.get("impact"), e.get("impact", "")),
                        "o" if e.get("impact") == "high" else "flat")) for e in notes.get("events", [])]
    for e in earn:
        rec_rows.append((f'{T.ltr(e["symbol"])} · דוח {e["time"]}', f'{T.fmt_big(e["mcap"])}'))
    side = ""
    if rec_rows:
        side = T.receipt("לוח היום", T.fmt_date(T.now_ny()) + " · שעון ניו יורק", rec_rows, he_title=True)
    elif earn_note:
        side = f'<div class="sheet" style="font-size:14px;color:var(--muted)">{earn_note} בקש מ-Claude להוסיף אירועים ודוחות מחיפוש ברשת.</div>'

    stats = ""
    if vix:
        lvl = "נמוך" if vix[2] < 15 else "רגיל" if vix[2] < 20 else "גבוה" if vix[2] < 30 else "קיצוני"
        stats = (f'<div class="grid g3" style="margin-bottom:18px">'
                 + T.stat("חוזי S&P 500", T.fmt_pct(es[3]) if es else "—", T.ltr(T.fmt_price(es[2])) if es else "", T.tone(es[3]) if es else "")
                 + T.stat("VIX", T.fmt_price(vix[2]), T.he(f"פחד {lvl}"), "down" if vix[2] >= 20 else "up")
                 + T.stat("הכי זז ברשימה", T.ltr(gaps[0]["symbol"]) if gaps else "—", T.ltr(T.fmt_pct(gaps[0]["gap"])) if gaps else "",
                          T.tone(gaps[0]["gap"]) if gaps else "")
                 + "</div>")
    body = head + stats + mgrid + ggrid + (f'<div style="max-width:560px">{side}</div>' if side else "")
    sub = f"סקירת בוקר · {T.session_state()} · {T.stamp_line()}"
    p = T.save(T.page("לפני הפעמון", body, "/trader-premarket", sub), "premarket", a.out)
    print("SUMMARY: " + json.dumps({
        "macro": [{"symbol": s, "name": n, "last": round(v, 3), "pct": p and round(p, 2)} for s, n, v, p, _ in macro],
        "gaps": [{"symbol": g["symbol"], "gap_pct": g["gap"] and round(g["gap"], 2), "last": g["last"], "prev_close": g["prev"]} for g in gaps],
        "earnings_today": [{"symbol": e["symbol"], "time": e["time"]} for e in earn], "report": p}, ensure_ascii=False))


if __name__ == "__main__":
    main()
