#!/usr/bin/env python3
"""/trader-journal: a trading journal in a plain CSV file, plus a performance report.

  python3 journal.py add --file journal.csv --ticker TSLA --side long --qty 50 --entry 364.18 --exit 370 \
                         --date 2026-11-10 --setup breakout --note "פריצה מעל שיא הבוקר"
  python3 journal.py report --file journal.csv
  python3 journal.py report --file journal.csv --since 2026-10-01

CSV columns: date,ticker,side,qty,entry,exit,fees,setup,note   (side = long | short)
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradelib as T  # noqa: E402

COLS = ["date", "ticker", "side", "qty", "entry", "exit", "fees", "setup", "note"]


def load(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = []
        for r in csv.DictReader(f):
            try:
                r["qty"], r["entry"], r["exit"] = float(r["qty"]), float(r["entry"]), float(r["exit"])
                r["fees"] = float(r.get("fees") or 0)
                r["d"] = dt.date.fromisoformat(r["date"][:10])
                r["side"] = (r.get("side") or "long").strip().lower()
                sgn = 1 if r["side"] == "long" else -1
                r["pnl"] = (r["exit"] - r["entry"]) * r["qty"] * sgn - r["fees"]
                r["ret"] = (r["exit"] / r["entry"] - 1) * 100 * sgn
                rows.append(r)
            except Exception:  # noqa: BLE001
                continue
    rows.sort(key=lambda r: r["d"])
    return rows


def add(a):
    new = not os.path.exists(a.file)
    with open(a.file, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLS)
        w.writerow([a.date or T.now_ny().date().isoformat(), a.ticker.upper(), a.side, a.qty, a.entry, a.exit,
                    a.fees, a.setup or "", a.note or ""])
    rows = load(a.file)
    last = rows[-1] if rows else None
    print(f"ADDED: {a.ticker.upper()} -> {a.file} ({len(rows)} trades)" + (f", P&L ${last['pnl']:,.2f}" if last else ""))


def report(a):
    rows = load(a.file)
    if a.since:
        rows = [r for r in rows if r["d"] >= dt.date.fromisoformat(a.since)]
    if not rows:
        T.die("אין עסקאות ביומן")
    pnl = [r["pnl"] for r in rows]
    wins, losses = [p for p in pnl if p > 0], [p for p in pnl if p <= 0]
    total = sum(pnl)
    wr = len(wins) / len(pnl) * 100
    aw = sum(wins) / len(wins) if wins else 0
    al = sum(losses) / len(losses) if losses else 0
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) else None
    exp = total / len(pnl)
    eq, peak, mdd, cur = [], 0.0, 0.0, 0.0
    for p in pnl:
        cur += p
        eq.append(cur)
        peak = max(peak, cur)
        mdd = min(mdd, cur - peak)
    best, worst = max(rows, key=lambda r: r["pnl"]), min(rows, key=lambda r: r["pnl"])

    def group(key):
        g = {}
        for r in rows:
            g.setdefault(key(r), []).append(r["pnl"])
        return g
    by_setup = sorted(group(lambda r: r.get("setup") or "ללא").items(), key=lambda kv: -sum(kv[1]))
    by_tk = sorted(group(lambda r: r["ticker"]).items(), key=lambda kv: -sum(kv[1]))
    wd = group(lambda r: r["d"].weekday())

    head = (f'<div class="row" style="margin:4px 0 20px"><span class="badge">{T.money(total)}</span>'
            f'<span class="headline" style="margin:0">ב-{len(rows)} <span class="o">עסקאות</span></span></div>')
    stats = ('<div class="grid g4" style="margin-bottom:18px">'
             + T.stat("אחוז הצלחה", f"{wr:.0f}%", T.he(f"{len(wins)} רווח · {len(losses)} הפסד"), "up" if wr >= 50 else "down")
             + T.stat("פקטור רווח", f"{pf:.2f}" if pf else "∞", "רווחים ÷ הפסדים", "up" if (pf or 9) >= 1 else "down")
             + T.stat("תוחלת לעסקה", T.money(exp), "רווח ממוצע לעסקה", T.tone(exp))
             + T.stat("ירידה מקסימלית", T.money(mdd, sign=False), "מהשיא של העקומה", "down" if mdd < 0 else "flat")
             + "</div>")
    xl = [(0, T.fmt_date(rows[0]["d"])), (len(rows) - 1, T.fmt_date(rows[-1]["d"]))]
    curve = T.line_chart_svg([{"values": [0] + eq, "color": T.GREEN if total >= 0 else T.RED, "width": 3, "area": True}],
                             [{"y": 0, "color": T.MUTED, "dash": "3 5", "width": 1.4}], xl, 900, 300)
    rec = T.receipt("סיכום היומן", f"{T.fmt_date(rows[0]['d'])} – {T.fmt_date(rows[-1]['d'])}",
                    [("רווח ממוצע", f'<span class="up">${aw:,.0f}</span>'),
                     ("הפסד ממוצע", f'<span class="down">{T.money(al)}</span>'),
                     ("יחס רווח/הפסד", f"{aw / abs(al):.2f}" if al else "—"),
                     ("העסקה הטובה", f'{T.ltr(best["ticker"])} <span class="up">{T.money(best["pnl"])}</span>'),
                     ("העסקה הגרועה", f'{T.ltr(worst["ticker"])} <span class="down">{T.money(worst["pnl"])}</span>')],
                    "רווח נקי", f'<span class="{T.tone(total)}">{T.money(total)}</span>')
    stamp = f'<div style="text-align:center;margin:-8px 0 18px"><span class="stamp">{"ברווח" if total > 0 else "בהפסד"}</span></div>'
    srows = [[T.esc(k), str(len(v)), f"{sum(1 for x in v if x > 0) / len(v) * 100:.0f}%",
              f'<span class="{T.tone(sum(v))}">{T.money(sum(v))}</span>'] for k, v in by_setup]
    trows = [[f"<b>{T.ltr(T.esc(k))}</b>", str(len(v)), f'<span class="{T.tone(sum(v))}">{T.money(sum(v))}</span>'] for k, v in by_tk[:10]]
    wd_lab = [T.HE_DAYS[i] for i in range(5)]
    wd_val = [sum(wd.get(i, [0])) for i in range(5)]
    last = [[T.fmt_date(r["d"]), f"<b>{T.ltr(T.esc(r['ticker']))}</b>", "לונג" if r["side"] == "long" else "שורט",
             f"{r['qty']:g}", T.fmt_price(r["entry"]), T.fmt_price(r["exit"]),
             f'<span class="{T.tone(r["pnl"])}">{T.money(r["pnl"])}</span>', T.esc(r.get("setup") or ""),
             f'<span style="font-size:13px">{T.esc(r.get("note") or "")}</span>'] for r in reversed(rows[-25:])]
    body = (head + stats + f'<div class="sheet chart"><h2>עקומת ההון</h2>{curve}</div>'
            + f'<div class="grid g2"><div>{rec}{stamp}</div><div>'
            + f'<div class="sheet"><h3>לפי סטאפ</h3>{T.table(["סטאפ", "עסקאות", "הצלחה", "רווח"], srows, (1, 2, 3))}</div>'
            + f'<div class="sheet chart"><h3>לפי יום בשבוע</h3>{T.bar_svg(wd_lab, wd_val, 460, 200, fs=15)}</div>'
            + f'<div class="sheet"><h3>לפי מניה</h3>{T.table(["מניה", "עסקאות", "רווח"], trows, (1, 2))}</div></div></div>'
            + f'<div class="sheet"><h2>עסקאות אחרונות</h2>{T.table(["תאריך", "מניה", "כיוון", "כמות", "כניסה", "יציאה", "רווח", "סטאפ", "הערה"], last, (3, 4, 5, 6))}</div>')
    p = T.save(T.page("יומן מסחר", body, "/trader-journal", T.stamp_line(), note="היומן נשמר בקובץ CSV שלך בלבד."), "journal", a.out)
    print("SUMMARY: " + json.dumps({"trades": len(rows), "net": round(total, 2), "win_rate": round(wr, 1),
                                    "profit_factor": pf and round(pf, 2), "expectancy": round(exp, 2),
                                    "max_drawdown": round(mdd, 2), "best_setup": by_setup[0][0], "report": p}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    ad = sub.add_parser("add")
    ad.add_argument("--file", default="journal.csv")
    ad.add_argument("--date")
    ad.add_argument("--ticker", required=True)
    ad.add_argument("--side", choices=["long", "short"], default="long")
    ad.add_argument("--qty", type=float, required=True)
    ad.add_argument("--entry", type=float, required=True)
    ad.add_argument("--exit", type=float, required=True)
    ad.add_argument("--fees", type=float, default=0)
    ad.add_argument("--setup")
    ad.add_argument("--note")
    rp = sub.add_parser("report")
    rp.add_argument("--file", default="journal.csv")
    rp.add_argument("--since")
    rp.add_argument("--out")
    a = ap.parse_args()
    add(a) if a.cmd == "add" else report(a)


if __name__ == "__main__":
    main()
