#!/usr/bin/env python3
"""/trader-risk: how many shares to buy so a stop-out costs exactly what you chose to risk.

  python3 risk.py --account 25000 --risk-pct 1 --entry 364.18 --stop 358 --target 370
  python3 risk.py --account 10000 --risk-usd 100 --ticker TSLA          # stop from ATR, entry = last price
  python3 risk.py --account 25000 --entry 50 --stop 51.5 --side short --max-pos-pct 25
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradelib as T  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", type=float, required=True, help="account size in $")
    ap.add_argument("--risk-pct", type=float, default=1.0, help="%% of account to risk (default 1)")
    ap.add_argument("--risk-usd", type=float, help="fixed $ risk instead of %%")
    ap.add_argument("--ticker")
    ap.add_argument("--entry", type=float)
    ap.add_argument("--stop", type=float)
    ap.add_argument("--target", type=float)
    ap.add_argument("--side", choices=["long", "short"], default="long")
    ap.add_argument("--atr-mult", type=float, default=1.0, help="stop distance in daily ATRs when --stop is missing")
    ap.add_argument("--max-pos-pct", type=float, default=100.0, help="cap position value at %% of account")
    ap.add_argument("--commission", type=float, default=0.0, help="$ per side")
    ap.add_argument("--out")
    a = ap.parse_args()
    sgn = 1 if a.side == "long" else -1
    sym = (a.ticker or "").upper()
    atr_v = None
    if sym and (a.entry is None or a.stop is None):
        try:
            ch = T.yahoo_chart(sym, "3mo", "1d")
            bars = ch["bars"]
            atr_v = T.atr(bars, 14)[-1]
            if a.entry is None:
                a.entry = ch["meta"].get("regularMarketPrice") or bars[-1]["c"]
        except Exception as e:  # noqa: BLE001
            T.die(f"לא הצלחתי למשוך נתונים ל-{sym}: {e}")
    if a.entry is None:
        T.die("צריך --entry (או --ticker כדי לקחת את המחיר האחרון)")
    if a.stop is None:
        if atr_v is None:
            T.die("צריך --stop (או --ticker כדי לחשב סטופ לפי ATR)")
        a.stop = a.entry - sgn * a.atr_mult * atr_v
    per_share = (a.entry - a.stop) * sgn
    if per_share <= 0:
        T.die("הסטופ חייב להיות מתחת לכניסה בלונג ומעל הכניסה בשורט")

    risk_usd = a.risk_usd if a.risk_usd else a.account * a.risk_pct / 100
    budget = risk_usd - 2 * a.commission
    shares = max(0, math.floor(budget / per_share))
    cap_shares = math.floor(a.account * a.max_pos_pct / 100 / a.entry)
    capped = shares > cap_shares
    shares = min(shares, cap_shares)
    pos_value = shares * a.entry
    real_risk = shares * per_share + 2 * a.commission
    rr = reward = None
    if a.target:
        reward = (a.target - a.entry) * sgn
        rr = reward / per_share if per_share else None
    be = 1 / (1 + rr) if rr else None

    title = "מחשבון פוזיציה" + (f" · {T.ltr(sym)}" if sym else "")
    sub = f"{'לונג' if a.side == 'long' else 'שורט'} · חשבון ${a.account:,.0f} · {T.stamp_line()}"
    rows = [("כניסה", T.fmt_price(a.entry)),
            ("סטופ", f'<span class="down">{T.fmt_price(a.stop)}</span>'),
            ("סיכון למניה", f"${per_share:,.2f} ({abs(per_share / a.entry * 100):.2f}%)")]
    if a.target:
        rows += [("יעד", f'<span class="up">{T.fmt_price(a.target)}</span>'),
                 ("רווח פוטנציאלי", f'<span class="up">${shares * reward:,.0f}</span>'),
                 ("יחס סיכוי/סיכון", f"1 : {rr:.2f}"),
                 ("אחוז הצלחה נדרש לאיזון", f"{be * 100:.1f}%")]
    rows += [("שווי הפוזיציה", f"${pos_value:,.0f} ({pos_value / a.account * 100:.1f}%)"),
             ("סיכון בפועל", f"${real_risk:,.0f} ({real_risk / a.account * 100:.2f}%)")]
    if atr_v:
        rows.append(("ATR יומי (14)", f"${atr_v:,.2f}"))
    rec = T.receipt(f"{sym or 'TRADE'} · {'LONG' if a.side == 'long' else 'SHORT'}",
                    f"סיכון מתוכנן: ${risk_usd:,.0f}" + (f" ({a.risk_pct:g}% מהחשבון)" if not a.risk_usd else ""),
                    rows, "כמות מניות", f"{shares:,}")

    warn = []
    if capped:
        warn.append(f"הכמות הוגבלה ל-{a.max_pos_pct:g}% מהחשבון, אז הסיכון בפועל נמוך מהמתוכנן.")
    if shares == 0:
        warn.append("הסטופ רחוק מדי ביחס לסיכון שבחרת: אפילו מניה אחת עוברת את התקציב.")
    if rr is not None and rr < 1:
        warn.append("היעד קרוב יותר מהסטופ. צריך אחוז הצלחה גבוה מ-50% כדי להרוויח לאורך זמן.")
    if atr_v and per_share < 0.5 * atr_v:
        warn.append(f"הסטופ צמוד מאוד: פחות מחצי מהתנודה היומית הממוצעת (${atr_v:,.2f}). רעש רגיל עלול להוציא אותך.")
    warn_html = "".join(f'<div class="list-item"><span class="chip o">שים לב</span><div>{w}</div></div>' for w in warn)

    # ladder: what 0.5% .. 2% risk would mean
    ladder = []
    for rp in (0.25, 0.5, 1, 1.5, 2):
        sh = min(math.floor((a.account * rp / 100 - 2 * a.commission) / per_share), cap_shares)
        ladder.append([f"{rp:g}%", f"${a.account * rp / 100:,.0f}", f"{max(sh, 0):,}", f"${max(sh, 0) * a.entry:,.0f}",
                       f"${max(sh, 0) * reward:,.0f}" if reward else "—"])
    tbl = T.table(["סיכון", "בדולרים", "מניות", "שווי פוזיציה", "רווח ביעד"], ladder, num_cols=(0, 1, 2, 3, 4))

    stamp = '<div style="text-align:center;margin:-6px 0 18px"><span class="stamp">' + (
        "מאושר" if shares > 0 and (rr is None or rr >= 1.5) else "לבדוק שוב") + "</span></div>"
    body = (f'<div class="grid g2"><div>{rec}{stamp}</div><div>'
            f'<div class="sheet"><h3>מה היה קורה בגדלי סיכון אחרים</h3>{tbl}</div>'
            + (f'<div class="sheet">{warn_html}</div>' if warn else "")
            + '<div class="sheet" style="font-size:14px;line-height:1.8"><b>הנוסחה:</b> כמות = סיכון בדולרים ÷ (כניסה − סטופ). '
              'ככה כל עסקה שנעצרת עולה לך אותו סכום, לא משנה כמה המניה יקרה או תנודתית.</div></div></div>')
    p = T.save(T.page(title, body, "/trader-risk", sub), "risk" + (f"-{sym}" if sym else ""), a.out)
    print("SUMMARY: " + json.dumps({"shares": shares, "position_value": round(pos_value, 2), "risk_usd": round(real_risk, 2),
                                    "entry": a.entry, "stop": round(a.stop, 4), "rr": rr and round(rr, 2),
                                    "capped": capped, "warnings": warn, "report": p}, ensure_ascii=False))


if __name__ == "__main__":
    main()
