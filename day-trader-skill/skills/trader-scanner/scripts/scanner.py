#!/usr/bin/env python3
"""/trader-scanner: scan every US-listed stock, then chart-check the liquid ones
for setups (breakouts, gaps, momentum, oversold, moving-average crosses, squeezes).

  python3 scanner.py                       # whole US market, all setups
  python3 scanner.py --setup breakout      # only one setup
  python3 scanner.py --tickers TSLA,NVDA,AMD,PLTR --setup all
  python3 scanner.py --min-price 10 --min-mcap 2e9 --deep 600 --top 24
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradelib as T  # noqa: E402

SETUPS = {
    "breakout": "פריצת שיא 20 יום",
    "newhigh": "ליד שיא 3 חודשים",
    "gap": "גאפ חזק היום",
    "momentum": "מומנטום חזק",
    "oversold": "מכירת יתר (RSI<30)",
    "cross": "חציית ממוצעים 20/50",
    "squeeze": "התכווצות תנודתיות",
    "volume": "נפח חריג",
}


def analyze(sym, closes, day_pct, volume, avg_vol):
    if len(closes) < 40:
        return None
    c = closes[-1]
    sig, why = [], {}
    hi20 = max(closes[-21:-1])
    if c > hi20:
        sig.append("breakout")
        why["breakout"] = T.pct(c, hi20)
    hi3m = max(closes)
    if c >= hi3m * 0.985:
        sig.append("newhigh")
    if day_pct is not None and abs(day_pct) >= 4:
        sig.append("gap")
    r20 = T.pct(c, closes[-21])
    if r20 is not None and r20 >= 15:
        sig.append("momentum")
    rs = T.rsi(closes, 14)[-1]
    if rs is not None and rs < 30:
        sig.append("oversold")
    if len(closes) >= 52:
        s20, s50 = T.sma(closes, 20), T.sma(closes, 50)
        for k in (-1, -2, -3):
            if s20[k - 1] and s50[k - 1] and s20[k] and s50[k] and s20[k - 1] <= s50[k - 1] and s20[k] > s50[k]:
                sig.append("cross")
                break
    rets = T.log_returns(closes)
    if len(rets) > 50:
        v10, v60 = T.stdev(rets[-10:]), T.stdev(rets[-60:])
        if v60 and v10 / v60 < 0.55:
            sig.append("squeeze")
    if avg_vol and volume and volume > 2.5 * avg_vol:
        sig.append("volume")
        why["volume"] = volume / avg_vol
    strength = (len(sig) + (abs(day_pct or 0) / 5) + max(0, (r20 or 0)) / 30
                + (why.get("breakout", 0) / 2) + min(why.get("volume", 0), 6) / 4)
    return {"symbol": sym, "price": c, "day_pct": day_pct, "r20": r20, "rsi": rs, "signals": sig,
            "score": round(strength, 3), "closes": closes[-60:], "hi20": hi20}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", default="all", help="all | " + " | ".join(SETUPS))
    ap.add_argument("--tickers", help="comma list instead of the whole market")
    ap.add_argument("--min-price", type=float, default=5)
    ap.add_argument("--min-mcap", type=float, default=300e6)
    ap.add_argument("--min-volume", type=float, default=300_000)
    ap.add_argument("--deep", type=int, default=500, help="how many liquid names get a full chart check")
    ap.add_argument("--top", type=int, default=24)
    ap.add_argument("--out")
    a = ap.parse_args()
    want = None if a.setup == "all" else set(a.setup.split(","))
    if want and not want <= set(SETUPS):
        T.die(f"setup לא מוכר. אפשרויות: {', '.join(SETUPS)}")

    info, source = {}, "list"
    if a.tickers:
        cands = [s.strip().upper() for s in a.tickers.split(",") if s.strip()]
        total = liquid_n = len(cands)
    else:
        uni, source = T.market_universe()
        info = {r["symbol"]: r for r in uni}
        total = len(uni)

        def ok(r):
            if r["price"] is None:  # core large caps listed without a quote
                return True
            return r["price"] >= a.min_price and (r["mcap"] or 0) >= a.min_mcap and (r["volume"] or 0) >= a.min_volume
        liquid = [r for r in uni if ok(r)]
        liquid_n = len(liquid)
        by_dollar = sorted(liquid, key=lambda r: -(r["price"] or 0) * (r["volume"] or 0))[: int(a.deep * 0.7)]
        by_move = sorted(liquid, key=lambda r: -abs(r["pct"] or 0))[: int(a.deep * 0.3)]
        core = [r for r in liquid if r["price"] is None]
        seen, cands = set(), []
        for r in by_dollar + by_move + core:
            if r["symbol"] not in seen:
                seen.add(r["symbol"])
                cands.append(r["symbol"])

    spark = T.yahoo_spark(cands, "3mo", "1d")
    res = []
    for s in cands:
        sp = spark.get(s)
        if not sp:
            continue
        r = info.get(s, {})
        closes = sp["c"]
        day_pct = r.get("pct")
        if day_pct is None and len(closes) > 1:
            day_pct = T.pct(closes[-1], closes[-2])
        x = analyze(s, closes, day_pct, r.get("volume"), r.get("avgvol"))
        if x:
            x["name"] = r.get("name", "")
            x["sector"] = r.get("sector", "")
            x["mcap"] = r.get("mcap", 0)
            res.append(x)
    checked = len(res)
    if want:
        hits = [x for x in res if want & set(x["signals"])]
    else:  # "all": a single common signal is noise, ask for two or more
        hits = [x for x in res if len(x["signals"]) >= 2]
    hits.sort(key=lambda x: -x["score"])
    top = hits[: a.top]

    # ---------- HTML ----------
    tiles = []
    for i, x in enumerate(top):
        hero = i < 4
        ch = x["day_pct"]
        order = sorted(x["signals"], key=lambda k: list(SETUPS).index(k))
        tag = SETUPS[order[0]] + (f" +{len(order) - 1}" if len(order) > 1 else "")
        ref = x["hi20"] if "breakout" in x["signals"] else None
        tiles.append(
            f'<div class="tile{" hit" if hero else ""}"><span class="tag">{tag}</span>'
            f'<div class="tk" style="margin-top:20px"><span class="ch {T.tone(ch)}">{T.fmt_pct(ch)}</span>{T.esc(x["symbol"])}</div>'
            f'<div class="nm">{T.esc(x["name"][:34])}</div>'
            f'{T.spark_svg(x["closes"], 220, 56, T.INK, 1.8, ref)}</div>')
    if not tiles:
        tiles.append('<div class="sheet" style="grid-column:1/-1;text-align:center">לא נמצאו מניות שעומדות בתנאים כרגע.</div>')

    rows = []
    for x in hits[:30]:
        chips = " ".join(T.chip(SETUPS[s], "o" if s in ("breakout", "gap", "volume") else "ink") for s in x["signals"])
        rows.append([f'<b>{T.ltr(T.esc(x["symbol"]))}</b><div style="font-size:12px;color:var(--muted);direction:ltr;text-align:right">{T.esc(x["name"][:40])}</div>',
                     T.fmt_price(x["price"]), f'<span class="{T.tone(x["day_pct"])}">{T.fmt_pct(x["day_pct"])}</span>',
                     f'<span class="{T.tone(x["r20"])}">{T.fmt_pct(x["r20"], 1)}</span>',
                     f'{x["rsi"]:.0f}' if x["rsi"] is not None else "—", T.fmt_big(x["mcap"]), chips])

    head = (f'<div class="row" style="margin:4px 0 22px"><span class="badge">{len(hits):,}</span>'
            f'<span class="headline" style="margin:0">מניות עברו את <span class="o">הסינון</span></span></div>')
    if not want:
        head += '<div class="sub" style="margin-top:-12px">מוצגות מניות עם 2 סטאפים ומעלה, החזקות ביותר קודם</div>'
    funnel = ('<div class="grid g4" style="margin-bottom:18px">'
              + T.stat("נסרקו", f"{total:,}", "מניות אמריקאיות" + (" (Nasdaq)" if source == "nasdaq" else " הכי פעילות" if source == "yahoo" else ""))
              + T.stat("עברו סינון נזילות", f"{liquid_n:,}", T.he(f"מחיר ≥ ${a.min_price:g}, שווי ≥ {T.fmt_big(a.min_mcap)}"))
              + T.stat("נבדקו גרף מלא", f"{checked:,}", "3 חודשים, נרות יומיים")
              + T.stat("סטאפים שנמצאו", f"{len(hits):,}", "ממוינים לפי חוזק", "up")
              + "</div>")
    grid = f'<div class="sheet"><div class="grid g4">{"".join(tiles)}</div></div>'
    tbl = (f'<div class="sheet"><h2>30 המובילות</h2>'
           + T.table(["מניה", "מחיר", "היום", "20 יום", "RSI", "שווי", "סטאפ"], rows, num_cols=(1, 2, 3, 4, 5)) + "</div>")
    legend = ('<div class="sheet"><h3>מה כל סטאפ אומר</h3><div style="font-size:14px;line-height:1.9">'
              '<b>פריצת שיא 20 יום</b>: סגירה מעל השיא של 20 הימים הקודמים (הקו הכתום המקווקו בגרף). '
              '<b>ליד שיא 3 חודשים</b>: עד 1.5% מהשיא. <b>גאפ חזק</b>: שינוי של 4% ומעלה היום. '
              '<b>מומנטום</b>: עלייה של 15%+ ב-20 יום. <b>מכירת יתר</b>: RSI(14) מתחת ל-30. '
              '<b>חציית ממוצעים</b>: ממוצע 20 חצה את ממוצע 50 כלפי מעלה ב-3 הימים האחרונים. '
              '<b>התכווצות</b>: תנודתיות 10 הימים האחרונים פחות מ-55% מהרגיל. לרוב באה לפני תנועה גדולה.</div></div>')
    sub = f"{T.stamp_line()} · " + ("כל השוק האמריקאי" if not a.tickers else "רשימה אישית")
    if want:
        sub += " · " + ", ".join(SETUPS[w] for w in want)
    body = head + funnel + grid + tbl + legend
    p = T.save(T.page("סורק גרפים", body, "/trader-scanner", sub), "scanner", a.out)
    print("SUMMARY: " + json.dumps({
        "scanned": total, "universe_source": source, "liquid": liquid_n, "chart_checked": checked, "hits": len(hits), "report": p,
        "top": [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in x.items() if k not in ("closes",)}
                for x in hits[:12]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
