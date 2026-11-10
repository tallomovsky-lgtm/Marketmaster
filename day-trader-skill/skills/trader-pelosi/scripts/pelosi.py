#!/usr/bin/env python3
"""/trader-pelosi: track stock trades disclosed by members of the US Congress.

Congress disclosures are public (STOCK Act) but there is no free open API, so Claude
collects recent trades with web search (Capitol Trades, Quiver Quantitative, the House
Clerk and Senate eFD sites, news) into trades.json, then:

  python3 pelosi.py trades.json            # render + add price moves since each trade
  python3 pelosi.py trades.json --no-prices

trades.json: [{"member":"Nancy Pelosi","party":"D","chamber":"House","ticker":"NVDA",
               "asset":"NVIDIA Corp","type":"buy","amount":"$1,000,001 - $5,000,000",
               "traded":"2026-09-12","disclosed":"2026-10-02","source":"https://..."}]
type: buy | sell | exchange   party: D | R | I   chamber: House | Senate
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradelib as T  # noqa: E402

TYPE_HE = {"buy": ("קנייה", "up"), "purchase": ("קנייה", "up"), "sell": ("מכירה", "down"),
           "sale": ("מכירה", "down"), "sell (partial)": ("מכירה חלקית", "down"), "exchange": ("החלפה", "flat")}
PARTY = {"D": ("דמוקרט", "#2b5ea7"), "R": ("רפובליקני", "#b8453a"), "I": ("עצמאי", "#6f6a60")}


def amount_mid(s):
    nums = [float(x.replace(",", "")) for x in re.findall(r"[\d,]+(?:\.\d+)?", s or "") if x.replace(",", "")]
    if not nums:
        return 0
    return sum(nums[:2]) / len(nums[:2])


def d(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except Exception:  # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--no-prices", action="store_true")
    ap.add_argument("--title", default="מעקב קונגרס")
    ap.add_argument("--out")
    a = ap.parse_args()
    with open(a.file, encoding="utf-8") as f:
        trades = json.load(f)
    if not trades:
        T.die("הקובץ ריק")
    for t in trades:
        t["ticker"] = (t.get("ticker") or "").upper().replace(".", "-")
        t["type"] = (t.get("type") or "").lower()
        t["traded_d"], t["disclosed_d"] = d(t.get("traded")), d(t.get("disclosed"))
        t["lag"] = (t["disclosed_d"] - t["traded_d"]).days if t["traded_d"] and t["disclosed_d"] else None
        t["mid"] = amount_mid(t.get("amount"))
    trades.sort(key=lambda t: t["disclosed_d"] or t["traded_d"] or dt.date.min, reverse=True)

    if not a.no_prices:
        tick = sorted({t["ticker"] for t in trades if t["ticker"]})
        sp = T.yahoo_spark(tick, "2y", "1d")
        for t in trades:
            x = sp.get(t["ticker"])
            if not x or not x["c"] or not t["traded_d"]:
                continue
            at = [c for ts, c in zip(x["t"], x["c"]) if T.ny(ts).date() <= t["traded_d"]]
            if at:
                t["px_trade"], t["px_now"] = at[-1], x["c"][-1]
                t["since"] = T.pct(x["c"][-1], at[-1])

    buys = [t for t in trades if TYPE_HE.get(t["type"], ("", ""))[1] == "up"]
    sells = [t for t in trades if TYPE_HE.get(t["type"], ("", ""))[1] == "down"]
    lags = [t["lag"] for t in trades if t["lag"] is not None]
    by_tk, by_mem = {}, {}
    for t in trades:
        by_tk.setdefault(t["ticker"], []).append(t)
        by_mem.setdefault(t.get("member", "?"), []).append(t)
    top_tk = sorted(by_tk.items(), key=lambda kv: (-len(kv[1]), -sum(x["mid"] for x in kv[1])))[:8]
    top_mem = sorted(by_mem.items(), key=lambda kv: -len(kv[1]))[:6]

    icon = (f'<div class="sheet" style="position:relative;padding-top:18px"><div class="top" style="margin:0">'
            f'<h2 style="font-size:30px;margin:0">{T.esc(a.title)}</h2><span class="pill">/trader-pelosi</span></div>'
            f'<div class="icon">{T.ICONS["radar"]}</div>'
            f'<div style="text-align:center;font-weight:900;font-size:clamp(28px,6vw,44px)">{len(trades)} <span style="color:var(--orange)">עסקאות</span></div></div>')
    stats = ('<div class="grid g4" style="margin-bottom:18px">'
             + T.stat("קניות", f"{len(buys)}", T.he("היקף משוער " + T.ltr(f"${sum(t['mid'] for t in buys) / 1e6:,.1f}M")), "up")
             + T.stat("מכירות", f"{len(sells)}", T.he("היקף משוער " + T.ltr(f"${sum(t['mid'] for t in sells) / 1e6:,.1f}M")), "down")
             + T.stat("עיכוב דיווח ממוצע", f"{sum(lags) / len(lags):.0f}" if lags else "—", "ימים מהעסקה עד הגילוי")
             + T.stat("המניה הכי פופולרית", T.ltr(top_tk[0][0]) if top_tk else "—", T.he(f"{len(top_tk[0][1])} עסקאות") if top_tk else "")
             + "</div>")
    tk_rows = []
    for tk, ts in top_tk:
        b = sum(1 for x in ts if TYPE_HE.get(x["type"], ("", ""))[1] == "up")
        s = sum(1 for x in ts if TYPE_HE.get(x["type"], ("", ""))[1] == "down")
        since = next((x.get("since") for x in ts if x.get("since") is not None), None)
        tk_rows.append([f"<b>{T.ltr(T.esc(tk))}</b>", f'<span class="up">{b}</span> / <span class="down">{s}</span>',
                        f"${sum(x['mid'] for x in ts) / 1e3:,.0f}K",
                        f'<span class="{T.tone(since)}">{T.fmt_pct(since, 1)}</span>' if since is not None else "—"])
    mem_rows = [[f"<b>{T.esc(m)}</b>", T.chip(PARTY.get((ts[0].get('party') or '?')[0].upper(), ('?', ''))[0],
                                                "ink"), str(len(ts)),
                 T.esc(", ".join(sorted({x['ticker'] for x in ts})[:5]))] for m, ts in top_mem]
    side = (f'<div class="sheet"><h3>המניות הכי נסחרות</h3>{T.table(["מניה", "קנייה / מכירה", "היקף משוער", "מאז העסקה"], tk_rows, (1, 2, 3))}</div>'
            f'<div class="sheet"><h3>חברי הקונגרס הכי פעילים</h3>{T.table(["שם", "מפלגה", "עסקאות", "מניות"], mem_rows, (2,))}</div>')
    rows = []
    for t in trades:
        lab, cls = TYPE_HE.get(t["type"], (t["type"] or "—", "flat"))
        pty = PARTY.get((t.get("party") or "?")[0].upper(), ("?", "#6f6a60"))
        since = t.get("since")
        lag_txt = T.he("אחרי %d ימים" % t["lag"]) if t["lag"] is not None else ""
        src = f'<a href="{T.esc(t["source"])}" target="_blank" rel="noopener">מקור</a>' if t.get("source") else ""
        rows.append([f'<b>{T.esc(t.get("member"))}</b><div style="font-size:12px;color:{pty[1]};font-weight:700">'
                     f'{pty[0]} · {"סנאט" if (t.get("chamber") or "").lower().startswith("s") else "בית הנבחרים"}</div>',
                     f'<b>{T.ltr(T.esc(t["ticker"]))}</b><div style="font-size:12px;color:var(--muted)">{T.esc((t.get("asset") or "")[:28])}</div>',
                     T.chip(lab, cls), T.ltr(T.esc(t.get("amount") or "—")),
                     T.fmt_date(t["traded_d"]) if t["traded_d"] else "—",
                     (f'{T.fmt_date(t["disclosed_d"])}<div style="font-size:12px;color:var(--muted)">{lag_txt}</div>'
                      if t["disclosed_d"] else "—"),
                     f'<span class="{T.tone(since)}">{T.fmt_pct(since, 1)}</span>' if since is not None else "—", src])
    tbl = T.table(["חבר קונגרס", "מניה", "פעולה", "סכום", "תאריך עסקה", "תאריך גילוי", "מאז העסקה", ""], rows, (3, 6))
    body = (f'<div class="grid g2"><div>{icon}</div><div>{stats.replace("g4", "g2")}{side}</div></div>'
            f'<div class="sheet"><h2>כל העסקאות</h2>{tbl}</div>'
            '<div class="sheet" style="font-size:14px;line-height:1.8"><b>חשוב לדעת:</b> חברי קונגרס חייבים לדווח על עסקאות '
            'עד 45 יום אחרי שבוצעו, ומדווחים טווח סכומים ולא סכום מדויק (ההיקף כאן הוא אמצע הטווח). '
            '"מאז העסקה" = שינוי המחיר מיום העסקה עד היום. העתקת עסקאות שדווחו באיחור לא מבטיחה את אותה תוצאה.</div>')
    span = [t["disclosed_d"] for t in trades if t["disclosed_d"]]
    sub = (f"גילויים מ-{T.fmt_date(min(span))} עד {T.fmt_date(max(span))} · " if span else "") + T.stamp_line()
    p = T.save(T.page("מעקב קונגרס", body, None, sub), "congress", a.out)
    print("SUMMARY: " + json.dumps({"trades": len(trades), "buys": len(buys), "sells": len(sells),
                                    "avg_lag_days": round(sum(lags) / len(lags), 1) if lags else None,
                                    "top_tickers": [tk for tk, _ in top_tk], "report": p}, ensure_ascii=False))


if __name__ == "__main__":
    main()
