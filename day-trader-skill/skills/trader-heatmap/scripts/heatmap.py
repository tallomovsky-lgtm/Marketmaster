#!/usr/bin/env python3
"""/trader-heatmap: where the money is moving today. Sector ETF board plus a
market-cap treemap of the biggest US stocks, colored by % change.

  python3 heatmap.py
  python3 heatmap.py --stocks 120
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradelib as T  # noqa: E402

NASDAQ_SECTOR = {"Technology": "Technology", "Telecommunications": "Communication", "Finance": "Financials",
                 "Health Care": "Health Care", "Consumer Discretionary": "Consumer Discretionary",
                 "Consumer Staples": "Consumer Staples", "Energy": "Energy", "Industrials": "Industrials",
                 "Basic Materials": "Materials", "Utilities": "Utilities", "Real Estate": "Real Estate"}


def last_change(sp):
    c = sp.get("c") or []
    if len(c) >= 2:
        return T.pct(c[-1], c[-2])
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stocks", type=int, default=90, help="how many of the largest stocks to draw")
    ap.add_argument("--out")
    a = ap.parse_args()

    etf = T.yahoo_spark(list(T.SECTOR_ETFS) + ["SPY", "QQQ", "IWM", "DIA"], "5d", "1d")
    idx = {k: last_change(etf.get(k, {})) for k in ("SPY", "QQQ", "IWM", "DIA")}
    sectors = [(k, T.SECTOR_ETFS[k], last_change(etf.get(k, {}))) for k in T.SECTOR_ETFS]
    sectors.sort(key=lambda x: -(x[2] if x[2] is not None else -99))

    uni, source = T.market_universe(pages=1)
    rows = []
    for r in uni:
        sec = T.SECTOR_OF.get(r["symbol"]) or NASDAQ_SECTOR.get(r.get("sector"), None) or (
            r.get("sector") if r.get("sector") in T.SECTORS_HE else "Other")
        rows.append({**r, "sector": sec})
    # core names without a quote: fill % from spark (no market cap -> they can't be sized, so skipped)
    big = sorted([r for r in rows if r["mcap"] and r["pct"] is not None], key=lambda r: -r["mcap"])[: a.stocks]
    adv = sum(1 for r in rows if (r["pct"] or 0) > 0)
    dec = sum(1 for r in rows if (r["pct"] or 0) < 0)

    # ---- treemap ----
    W, H = 1000, 640
    groups = {}
    for r in big:
        groups.setdefault(r["sector"], []).append(r)
    gl = sorted(groups.items(), key=lambda kv: -sum(x["mcap"] for x in kv[1]))
    svg = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="Heebo,system-ui,sans-serif">']
    srects = T.squarify([sum(x["mcap"] for x in g) for _, g in gl], 0, 0, W, H)
    for (sec, g), (x, y, w, h) in zip(gl, srects):
        g.sort(key=lambda r: -r["mcap"])
        top_pad = 20 if h > 60 and w > 70 else 0
        inner = T.squarify([r["mcap"] for r in g], x + 2, y + top_pad + 2, w - 4, h - top_pad - 4)
        svg.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="#fbf8f1" stroke="#ebe6da" stroke-width="3"/>')
        if top_pad:
            svg.append(f'<text x="{x + w - 8:.1f}" y="{y + 15:.1f}" text-anchor="end" font-size="12.5" font-weight="900" fill="#141414">{T.esc(T.SECTORS_HE.get(sec, sec))}</text>')
        for r, (rx, ry, rw, rh) in zip(g, inner):
            col = T.heat_color(r["pct"])
            strong = abs(r["pct"] or 0) > 1.6
            fg = "#fff" if strong else "#141414"
            svg.append(f'<rect x="{rx + 1:.1f}" y="{ry + 1:.1f}" width="{max(rw - 2, 0):.1f}" height="{max(rh - 2, 0):.1f}" rx="5" fill="{col}"><title>{T.esc(r["symbol"])} {T.fmt_pct(r["pct"])}</title></rect>')
            fs = max(9, min(26, min(rw / 4.2, rh / 2.6)))
            if rw > 34 and rh > 22:
                cy = ry + rh / 2
                svg.append(f'<text x="{rx + rw / 2:.1f}" y="{cy - (fs * .1 if rh > 40 else -fs * .35):.1f}" text-anchor="middle" font-size="{fs:.0f}" font-weight="900" fill="{fg}">{T.esc(r["symbol"])}</text>')
                if rh > 40:
                    svg.append(f'<text x="{rx + rw / 2:.1f}" y="{cy + fs * .85:.1f}" text-anchor="middle" font-size="{max(9, fs * .58):.0f}" font-weight="700" fill="{fg}">{T.fmt_pct(r["pct"])}</text>')
    svg.append("</svg>")

    tiles = "".join(
        f'<div class="tile" style="background:{T.heat_color(p, 2.0)};min-height:0;padding:12px 14px">'
        f'<div style="font-weight:900;font-size:16px;color:{"#fff" if p is not None and abs(p) > 1.1 else "#141414"}">{T.SECTORS_HE[sec]}</div>'
        f'<div style="display:flex;justify-content:space-between;align-items:baseline;color:{"#fff" if p is not None and abs(p) > 1.1 else "#141414"}">'
        f'<b style="font-size:24px;direction:ltr">{T.fmt_pct(p)}</b><span class="kbd" style="font-size:12px;opacity:.75">{tk}</span></div></div>'
        for tk, sec, p in sectors)

    leader, lagger = sectors[0], sectors[-1]
    head = (f'<div class="headline">הכסף זורם ל<span class="o">{T.SECTORS_HE[leader[1]]}</span>, '
            f'בורח מ{T.SECTORS_HE[lagger[1]]}</div>') if leader[2] is not None else ""
    stats = ('<div class="grid g4" style="margin-bottom:18px">'
             + "".join(T.stat(n, T.fmt_pct(idx[k]), k, T.tone(idx[k]))
                       for k, n in (("SPY", "S&P 500"), ("QQQ", "נאסד\"ק 100"), ("DIA", "דאו ג'ונס"), ("IWM", "ראסל 2000")))
             + "</div>")
    breadth = ""
    if adv + dec:
        pa = adv / (adv + dec) * 100
        breadth = (f'<div class="sheet"><div class="row"><h3 style="margin:0">רוחב שוק</h3><span class="spacer"></span>'
                   f'<span class="chip up">{adv:,} עולות</span><span class="chip down">{dec:,} יורדות</span></div>'
                   f'<div style="height:14px;border-radius:99px;background:var(--red);margin-top:12px;overflow:hidden;direction:ltr">'
                   f'<div style="height:100%;width:{pa:.1f}%;background:var(--green)"></div></div>'
                   f'<div style="font-size:13px;color:var(--muted);margin-top:6px">מתוך {adv + dec:,} מניות שנבדקו</div></div>')
    body = (head + stats + f'<div class="sheet"><h2>סקטורים</h2><div class="grid g4">{tiles}</div></div>'
            + f'<div class="sheet chart" style="padding:12px"><h2 style="margin:6px 8px 12px">{len(big)} המניות הגדולות</h2>{"".join(svg)}'
              f'<div class="legend" style="padding:0 8px"><span>גודל = שווי שוק</span><span>צבע = שינוי יומי</span>'
              f'<span class="spacer"></span><span dir="ltr" style="display:inline-flex;gap:8px;align-items:center">−3%'
              f'<span style="display:inline-block;width:160px;height:10px;border-radius:9px;background:linear-gradient(90deg,{T.heat_color(-3)},{T.heat_color(0)},{T.heat_color(3)})"></span>'
              f'+3%</span></div></div>' + breadth)
    sub = f"{T.session_state()} · {T.stamp_line()} · השינוי ביום המסחר האחרון"
    p = T.save(T.page("מפת חום", body, "/trader-heatmap", sub), "heatmap", a.out)
    print("SUMMARY: " + json.dumps({"indices": {k: v and round(v, 2) for k, v in idx.items()},
                                    "sectors": [{"etf": t, "sector": s, "pct": p and round(p, 2)} for t, s, p in sectors],
                                    "advancers": adv, "decliners": dec, "universe_source": source,
                                    "biggest_movers": [{"symbol": r["symbol"], "pct": round(r["pct"], 2)} for r in
                                                       sorted(big, key=lambda r: -abs(r["pct"]))[:8]], "report": p},
                                   ensure_ascii=False))


if __name__ == "__main__":
    main()
