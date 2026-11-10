#!/usr/bin/env python3
"""/trader-earnings: earnings season tools.

  python3 earnings.py history TSLA
      how the stock reacted to its last reports (gap, day move), typical move,
      and the range that typical move implies from today's price.
      Report dates come from Nasdaq; if Nasdaq is unreachable pass them yourself:
  python3 earnings.py history TSLA --dates 2026-10-21,2026-07-22,2026-04-22,2026-01-28

  python3 earnings.py calendar --days 5
      upcoming reports (Nasdaq). If Nasdaq is unreachable, Claude collects the calendar
      with web search into a JSON list and passes it:
  python3 earnings.py calendar --file cal.json
      cal.json: [{"date":"2026-11-12","symbol":"CSCO","name":"Cisco","time":"after","eps_forecast":"0.98"}]
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradelib as T  # noqa: E402

TIME_HE = {"before": "לפני הפתיחה", "after": "אחרי הסגירה", "time-pre-market": "לפני הפתיחה",
           "time-after-hours": "אחרי הסגירה"}


def reaction(bars, day):
    """Pick the reaction session: report day (pre-market report) or the next day (after-close).
    We take whichever of the two has the bigger opening gap."""
    idx = {T.ny(b["t"]).date(): i for i, b in enumerate(bars)}
    cand = []
    for d in (day, day + dt.timedelta(days=1), day + dt.timedelta(days=2), day + dt.timedelta(days=3)):
        i = idx.get(d)
        if i and i > 0:
            cand.append(i)
        if len(cand) == 2:
            break
    best = None
    for i in cand:
        prev = bars[i - 1]["c"]
        g = T.pct(bars[i]["o"], prev)
        if best is None or abs(g) > abs(best[1]):
            best = (i, g)
    if not best:
        return None
    i, g = best
    prev = bars[i - 1]["c"]
    return {"session": T.ny(bars[i]["t"]).date(), "gap": g, "day": T.pct(bars[i]["c"], prev),
            "range": (bars[i]["h"] - bars[i]["l"]) / prev * 100,
            "next5": T.pct(bars[min(i + 5, len(bars) - 1)]["c"], prev)}


def history(a):
    sym = a.ticker.upper()
    rows = []
    if a.dates:
        rows = [{"date": dt.date.fromisoformat(x.strip()), "quarter": "", "eps": None, "forecast": None, "surprise": None}
                for x in a.dates.split(",") if x.strip()]
    else:
        try:
            rows = T.nasdaq_earnings_history(sym)
        except Exception as e:  # noqa: BLE001
            T.die(f"לא הצלחתי למשוך תאריכי דוחות מ-Nasdaq ({e}). העבר אותם עם --dates YYYY-MM-DD,...")
    if not rows:
        T.die("אין תאריכי דוחות")
    ch = T.yahoo_chart(sym, "2y", "1d")
    bars = ch["bars"]
    price = ch["meta"].get("regularMarketPrice") or bars[-1]["c"]
    res = []
    for r in sorted(rows, key=lambda r: r["date"]):
        x = reaction(bars, r["date"])
        if x:
            res.append({**r, **x})
    if not res:
        T.die("לא נמצאו נתוני מחיר סביב תאריכי הדוחות")
    abs_moves = [abs(x["day"]) for x in res]
    typ = sum(abs_moves) / len(abs_moves)
    ups = sum(1 for x in res if x["day"] > 0)
    labels = [f"{x['session'].month:02d}.{str(x['session'].year)[2:]}" for x in res]
    chart = T.bar_svg(labels, [x["day"] for x in res], 460, 220, fs=15)
    trs = [[T.fmt_date(x["date"]), T.esc(x.get("quarter") or ""),
            T.fmt_pct(x["surprise"], 1) if x.get("surprise") is not None else "—",
            f'<span class="{T.tone(x["gap"])}">{T.fmt_pct(x["gap"])}</span>',
            f'<span class="{T.tone(x["day"])}">{T.fmt_pct(x["day"])}</span>',
            f'{x["range"]:.1f}%', f'<span class="{T.tone(x["next5"])}">{T.fmt_pct(x["next5"])}</span>'] for x in reversed(res)]
    tbl = T.table(["דוח", "רבעון", "הפתעה ב-EPS", "גאפ", "יום התגובה", "טווח היום", "אחרי 5 ימים"], trs, (2, 3, 4, 5, 6))
    rec = T.receipt(f"{sym} · דוחות", f"{len(res)} הדוחות האחרונים",
                    [("עלתה אחרי הדוח", f"{ups} מתוך {len(res)}"),
                     ("התנועה הגדולה ביותר", T.fmt_pct(max((x["day"] for x in res), key=abs))),
                     ("מחיר עכשיו", T.fmt_price(price)),
                     ("טווח צפוי לפי הממוצע", f"{T.fmt_price(price * (1 - typ / 100))} – {T.fmt_price(price * (1 + typ / 100))}")],
                    "תנועה ממוצעת ביום הדוח", f"±{typ:.1f}%")
    head = (f'<div class="row" style="margin:4px 0 20px"><span class="badge">±{typ:.1f}%</span>'
            f'<span class="headline" style="margin:0">תנועה <span class="o">טיפוסית</span> בדוח</span></div>')
    body = (head + f'<div class="grid g2"><div>{rec}</div><div><div class="sheet chart"><h3>תגובת המניה ביום הדוח</h3>{chart}</div>'
            '<div class="sheet" style="font-size:14px;line-height:1.8"><b>איך זה מחושב:</b> לכל דוח נבחר יום המסחר הראשון '
            'שאחריו (יום הדוח אם פורסם לפני הפתיחה, או היום שאחרי אם פורסם אחרי הסגירה). התנועה נמדדת מול הסגירה שלפני הדוח. '
            'זה מה שקרה בעבר, לא הבטחה למה שיקרה הפעם.</div></div></div>'
            f'<div class="sheet"><h2>דוח אחרי דוח</h2>{tbl}</div>')
    p = T.save(T.page(f"דוחות · {T.ltr(sym)}", body, "/trader-earnings", T.stamp_line()), f"earnings-{sym}", a.out)
    print("SUMMARY: " + json.dumps({"ticker": sym, "typical_move_pct": round(typ, 2), "up_count": ups, "n": len(res),
                                    "reactions": [{"date": str(x["date"]), "gap": round(x["gap"], 2), "day": round(x["day"], 2)} for x in res],
                                    "report": p}, ensure_ascii=False))


def calendar(a):
    items = []
    if a.file:
        with open(a.file, encoding="utf-8") as f:
            for r in json.load(f):
                items.append({"date": dt.date.fromisoformat(r["date"]), "symbol": r["symbol"].upper(), "name": r.get("name", ""),
                              "time": TIME_HE.get(r.get("time", ""), r.get("time", "") or "לא ידוע"),
                              "mcap": r.get("mcap") or 0, "eps_forecast": r.get("eps_forecast"), "last_eps": r.get("last_eps")})
    else:
        day = dt.date.fromisoformat(a.date) if a.date else T.now_ny().date()
        n = 0
        while n < a.days:
            if day.weekday() < 5:
                try:
                    for r in T.nasdaq_earnings(day):
                        items.append({**r, "date": day})
                except Exception as e:  # noqa: BLE001
                    T.die(f"לוח הדוחות של Nasdaq לא זמין ({e}). אסוף את הלוח בחיפוש ושלח עם --file cal.json")
                n += 1
            day += dt.timedelta(days=1)
    items = [x for x in items if not x["mcap"] or x["mcap"] >= a.min_mcap]
    by_day = {}
    for x in items:
        by_day.setdefault(x["date"], []).append(x)
    cols = ""
    for d in sorted(by_day):
        rows = sorted(by_day[d], key=lambda x: -(x["mcap"] or 0))[: a.per_day]
        rr = [(f'<b>{T.ltr(T.esc(x["symbol"]))}</b> <span class="muted" style="font-size:13px">{T.esc((x["name"] or "")[:22])}</span>',
               T.he(T.esc(x["time"])) + (f' · {T.esc(x["eps_forecast"])}' if x.get("eps_forecast") else "")) for x in rows]
        cols += T.receipt(f"יום {T.HE_DAYS[d.weekday()]}", T.fmt_date(d) + f" · {len(by_day[d])} חברות", rr, he_title=True)
    total = len(items)
    head = (f'<div class="row" style="margin:4px 0 20px"><span class="badge">{total}</span>'
            f'<span class="headline" style="margin:0">דוחות <span class="o">בדרך</span></span></div>')
    body = head + f'<div class="grid g2">{cols or "<div class=sheet>אין דוחות בטווח.</div>"}</div>'
    p = T.save(T.page("לוח דוחות", body, "/trader-earnings", T.stamp_line() + " · EPS = תחזית הקונצנזוס"), "earnings-calendar", a.out)
    print("SUMMARY: " + json.dumps({"reports": total, "days": [str(d) for d in sorted(by_day)],
                                    "biggest": [x["symbol"] for x in sorted(items, key=lambda x: -(x["mcap"] or 0))[:15]], "report": p},
                                   ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("history")
    h.add_argument("ticker")
    h.add_argument("--dates", help="comma list of report dates YYYY-MM-DD (if Nasdaq is unreachable)")
    h.add_argument("--out")
    c = sub.add_parser("calendar")
    c.add_argument("--date")
    c.add_argument("--days", type=int, default=5)
    c.add_argument("--file")
    c.add_argument("--min-mcap", type=float, default=2e9)
    c.add_argument("--per-day", type=int, default=12)
    c.add_argument("--out")
    a = ap.parse_args()
    history(a) if a.cmd == "history" else calendar(a)


if __name__ == "__main__":
    main()
