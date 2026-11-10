#!/usr/bin/env python3
"""/trader-levels: the price levels day traders watch for one stock: yesterday's
high/low/close, pivot points, pre-market range, VWAP, moving averages, 52-week
range and swing support/resistance zones.

  python3 levels.py TSLA
  python3 levels.py NVDA --days 90
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradelib as T  # noqa: E402


def swings(bars, win=4):
    hi, lo = [], []
    for i in range(win, len(bars) - win):
        h, l = bars[i]["h"], bars[i]["l"]
        if all(h >= bars[j]["h"] for j in range(i - win, i + win + 1)):
            hi.append(h)
        if all(l <= bars[j]["l"] for j in range(i - win, i + win + 1)):
            lo.append(l)
    return hi, lo


def cluster(vals, tol=0.012):
    vals = sorted(vals)
    groups = []
    for v in vals:
        if groups and abs(v / groups[-1][-1] - 1) <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [(sum(g) / len(g), len(g)) for g in groups]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--days", type=int, default=70, help="candles shown on the chart")
    ap.add_argument("--out")
    a = ap.parse_args()
    sym = a.ticker.upper()
    try:
        d = T.yahoo_chart(sym, "1y", "1d")
    except Exception as e:  # noqa: BLE001
        T.die(str(e))
    bars = d["bars"]
    if len(bars) < 30:
        T.die(f"אין מספיק נתונים ל-{sym}")
    now = T.now_ny()
    today = now.date()
    last_date = T.ny(bars[-1]["t"]).date()
    session_open = now.weekday() < 5 and (9 * 60 + 30) <= now.hour * 60 + now.minute < 16 * 60
    # last *completed* session
    prev = bars[-2] if (last_date == today and session_open) else bars[-1]
    price = d["meta"].get("regularMarketPrice") or bars[-1]["c"]

    intra, pm_hi, pm_lo, vw = [], None, None, None
    try:
        idata = T.yahoo_chart(sym, "1d", "5m", prepost=True)
        intra = [b for b in idata["bars"] if T.ny(b["t"]).date() == today]
        pre = [b for b in intra if T.ny(b["t"]).hour * 60 + T.ny(b["t"]).minute < 9 * 60 + 30]
        reg = [b for b in intra if 9 * 60 + 30 <= T.ny(b["t"]).hour * 60 + T.ny(b["t"]).minute < 16 * 60]
        if pre:
            pm_hi, pm_lo = max(b["h"] for b in pre), min(b["l"] for b in pre)
            if not reg:
                price = pre[-1]["c"]
        if reg:
            vw = T.vwap(reg)[-1]
            price = reg[-1]["c"]
    except Exception:  # noqa: BLE001
        pass

    H, L, C = prev["h"], prev["l"], prev["c"]
    P = (H + L + C) / 3
    closes = [b["c"] for b in bars]
    s20, s50, s200 = T.sma(closes, 20)[-1], T.sma(closes, 50)[-1], T.sma(closes, 200)[-1] if len(closes) >= 200 else None
    hi52, lo52 = max(b["h"] for b in bars), min(b["l"] for b in bars)
    atr_v = T.atr(bars, 14)[-1]

    lv = [("שיא אתמול", H, "res"), ("שפל אתמול", L, "sup"), ("סגירה אתמול", C, "piv"),
          ("פיבוט P", P, "piv"), ("R1", 2 * P - L, "res"), ("R2", P + (H - L), "res"),
          ("S1", 2 * P - H, "sup"), ("S2", P - (H - L), "sup"),
          ("ממוצע 20", s20, "ma"), ("ממוצע 50", s50, "ma"), ("ממוצע 200", s200, "ma"),
          ("שיא 52 שבועות", hi52, "res"), ("שפל 52 שבועות", lo52, "sup")]
    if pm_hi:
        lv += [("שיא פרה-מרקט", pm_hi, "res"), ("שפל פרה-מרקט", pm_lo, "sup")]
    if vw:
        lv.append(("VWAP היום", vw, "piv"))
    sh, sl = swings(bars[-130:])
    zones = cluster(sh + sl)
    above = sorted([z for z in zones if z[0] > price], key=lambda z: z[0])[:3]
    below = sorted([z for z in zones if z[0] < price], key=lambda z: -z[0])[:3]
    for z, n in above:
        lv.append((f"התנגדות ×{n}", z, "res"))
    for z, n in below:
        lv.append((f"תמיכה ×{n}", z, "sup"))
    lv = [x for x in lv if x[1] is not None]
    lv.sort(key=lambda x: -x[1])

    colors = {"res": T.RED, "sup": T.GREEN, "piv": T.INK, "ma": T.ORANGE}
    show = bars[-a.days:]
    lo_r, hi_r = min(b["l"] for b in show), max(b["h"] for b in show)
    span = hi_r - lo_r
    near = [x for x in lv if lo_r - span * 0.08 <= x[1] <= hi_r + span * 0.08]
    near.sort(key=lambda x: abs(x[1] - price))
    hl = [{"y": v, "color": colors[k], "label": n, "dash": "2 4" if k == "ma" else "6 5"} for n, v, k in near[:8]]
    hl.append({"y": price, "color": T.ORANGE, "label": "עכשיו", "dash": "", "width": 2.4})
    step = max(1, len(show) // 5)
    xl = [(i, f"{T.ny(b['t']).day:02d}.{T.ny(b['t']).month:02d}") for i, b in enumerate(show) if i % step == 0]
    ma20 = T.sma(closes, 20)[-len(show):]
    chart = T.candles_svg(show, hl, xl, pad=(16, 190, 34, 10), overlays=[{"values": ma20, "color": T.ORANGE, "width": 1.6, "opacity": .7}])

    rows, placed = [], False
    for n, v, k in lv:
        if not placed and v < price:
            rows.append([f'<b class="chip o">עכשיו</b>', f"<b>{T.fmt_price(price)}</b>", "", ""])
            placed = True
        dist = (v / price - 1) * 100
        kind = {"res": T.chip("התנגדות", "down"), "sup": T.chip("תמיכה", "up"),
                "piv": T.chip("ציר", "ink"), "ma": T.chip("ממוצע", "o")}[k]
        rows.append([f"<b>{T.esc(n)}</b>", T.fmt_price(v), f'<span class="{T.tone(dist)}">{T.fmt_pct(dist)}</span>', kind])
    if not placed:
        rows.append([f'<b class="chip o">עכשיו</b>', f"<b>{T.fmt_price(price)}</b>", "", ""])
    tbl = T.table(["רמה", "מחיר", "מרחק", "סוג"], rows, num_cols=(1, 2))

    up = min([x for x in lv if x[1] > price * 1.0005], key=lambda x: x[1], default=None)
    dn = max([x for x in lv if x[1] < price * 0.9995], key=lambda x: x[1], default=None)
    stats = ('<div class="grid g4" style="margin-bottom:18px">'
             + T.stat("מחיר עכשיו", T.fmt_price(price), T.he("שעון ניו יורק " + T.fmt_time(now)))
             + T.stat("התנגדות קרובה", T.fmt_price(up[1]) if up else "—", T.he(up[0]) if up else "", "down")
             + T.stat("תמיכה קרובה", T.fmt_price(dn[1]) if dn else "—", T.he(dn[0]) if dn else "", "up")
             + T.stat("ATR יומי", T.fmt_price(atr_v), T.he(f"{atr_v / price * 100:.1f}% תנודה ממוצעת ליום"))
             + "</div>")
    body = (stats + f'<div class="sheet chart">{chart}<div class="legend">'
            f'<span><i style="border-color:{T.RED}"></i>התנגדות</span><span><i style="border-color:{T.GREEN}"></i>תמיכה</span>'
            f'<span><i style="border-color:{T.INK}"></i>ציר / סגירה / VWAP</span><span><i style="border-color:{T.ORANGE}"></i>ממוצע נע 20</span></div></div>'
            f'<div class="sheet"><h2>סולם הרמות</h2>{tbl}</div>'
            '<div class="sheet" style="font-size:14px;line-height:1.8"><b>איך לקרוא:</b> רמות מעל המחיר הן מקומות שבהם '
            'מוכרים נכנסו בעבר, רמות מתחת הן מקומות שבהם קונים נכנסו. כמה רמות קרובות זו לזו יוצרות אזור חזק יותר. '
            'פיבוטים מחושבים מהשיא, השפל והסגירה של אתמול. אזורי תמיכה והתנגדות נבנו מנקודות מפנה ב-6 החודשים האחרונים; '
            '×3 אומר שהמחיר הסתובב באזור הזה 3 פעמים.</div>')
    sub = f"{T.esc(d['meta'].get('longName') or d['meta'].get('shortName') or '')} · {T.stamp_line()}"
    p = T.save(T.page(f"רמות מפתח · {T.ltr(sym)}", body, "/trader-levels", sub), f"levels-{sym}", a.out)
    print("SUMMARY: " + json.dumps({"ticker": sym, "price": price, "levels": [{"name": n, "price": round(v, 2), "type": k} for n, v, k in lv],
                                    "atr": round(atr_v, 2), "report": p}, ensure_ascii=False))


if __name__ == "__main__":
    main()
