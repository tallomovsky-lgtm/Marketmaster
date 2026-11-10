#!/usr/bin/env python3
"""/trader-news: market headlines for your tickers, with a Hebrew summary and a
bullish / bearish read on every story. Two steps:

  1) python3 news.py fetch TSLA NVDA --market --out news.json
       -> collects headlines (Yahoo Finance) and price moves into news.json
  2) Claude fills, for every item: "title_he", "why_he", "sentiment" (bull|bear|neutral),
     and at the top level "brief_he" (2-3 sentences). Then:
     python3 news.py render news.json
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradelib as T  # noqa: E402


def ago(ts):
    if not ts:
        return ""
    m = int((time.time() - ts) // 60)
    if m < 60:
        return f"לפני {max(m, 1)} דק׳"
    h = m // 60
    if h < 24:
        return f"לפני {h} שע׳"
    return f"לפני {h // 24} ימים"


def fetch(a):
    tickers = [t.upper() for t in a.tickers]
    queries = tickers + (["stock market today", "Federal Reserve"] if a.market or not tickers else [])
    items, seen = [], set()
    for q in queries:
        try:
            for n in T.yahoo_news(q, a.per):
                key = (n["title"] or "").strip().lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                n["query"] = q
                n.update({"title_he": None, "why_he": None, "sentiment": None})
                items.append(n)
        except Exception as e:  # noqa: BLE001
            print(f"warn: {q}: {e}", file=sys.stderr)
    items.sort(key=lambda n: -(n["time"] or 0))
    moves = {}
    if tickers:
        sp = T.yahoo_spark(tickers, "5d", "1d")
        for t in tickers:
            c = (sp.get(t) or {}).get("c") or []
            if len(c) >= 2:
                moves[t] = {"last": c[-1], "pct": T.pct(c[-1], c[-2]), "pct5d": T.pct(c[-1], c[0]), "closes": c}
    for i, n in enumerate(items):
        n["id"] = i + 1
    data = {"tickers": tickers, "market": bool(a.market or not tickers), "fetched": int(time.time()),
            "brief_he": None, "moves": moves, "items": items[: a.max]}
    T.save_json(data, a.out)
    print(f"ITEMS: {len(data['items'])} -> fill title_he / why_he / sentiment / brief_he, then run: news.py render {a.out}")


def render(a):
    with open(a.file, encoding="utf-8") as f:
        d = json.load(f)
    items = d.get("items", [])
    cnt = {"bull": 0, "bear": 0, "neutral": 0}
    for n in items:
        cnt[n.get("sentiment") if n.get("sentiment") in cnt else "neutral"] += 1
    tot = max(len(items), 1)
    mood = "חיובי" if cnt["bull"] > cnt["bear"] * 1.3 else "שלילי" if cnt["bear"] > cnt["bull"] * 1.3 else "מעורב"
    head = (f'<div class="row" style="margin:4px 0 18px"><span class="badge">{len(items)}</span>'
            f'<span class="headline" style="margin:0">כותרות, הסנטימנט <span class="o">{mood}</span></span></div>')
    if d.get("brief_he"):
        head += f'<div class="sheet" style="font-size:17px;line-height:1.8"><b>בקצרה:</b> {T.esc(d["brief_he"])}</div>'
    meter = (f'<div class="sheet"><div class="row"><h3 style="margin:0">מד סנטימנט</h3><span class="spacer"></span>'
             f'{T.chip(str(cnt["bull"]) + " חיוביות", "up")} {T.chip(str(cnt["neutral"]) + " ניטרליות")} '
             f'{T.chip(str(cnt["bear"]) + " שליליות", "down")}</div>'
             f'<div style="display:flex;height:14px;border-radius:99px;overflow:hidden;margin-top:12px;direction:rtl">'
             f'<div style="width:{cnt["bull"] / tot * 100:.1f}%;background:var(--green)"></div>'
             f'<div style="width:{cnt["neutral"] / tot * 100:.1f}%;background:#cfc7b6"></div>'
             f'<div style="width:{cnt["bear"] / tot * 100:.1f}%;background:var(--red)"></div></div></div>')
    tiles = ""
    for t, m in (d.get("moves") or {}).items():
        tiles += (f'<div class="tile" style="min-height:0"><div class="tk"><span class="ch {T.tone(m["pct"])}">{T.fmt_pct(m["pct"])}</span>{T.esc(t)}</div>'
                  f'<div class="nm">{T.fmt_price(m["last"])} · {T.he("5 ימים")} {T.fmt_pct(m["pct5d"], 1)}</div>'
                  f'{T.spark_svg(m["closes"], 220, 44)}</div>')
    tgrid = f'<div class="sheet"><div class="grid g4">{tiles}</div></div>' if tiles else ""
    lst = ""
    for n in items:
        s = n.get("sentiment") or "neutral"
        chip = {"bull": T.chip("חיובי", "up"), "bear": T.chip("שלילי", "down")}.get(s, T.chip("ניטרלי"))
        tk = " ".join(T.chip(T.ltr(T.esc(x)), "ink") for x in (n.get("tickers") or [])[:4])
        title = n.get("title_he") or n.get("title")
        orig = f'<div class="meta" dir="ltr" style="text-align:right">{T.esc(n["title"])}</div>' if n.get("title_he") else ""
        why = f'<div style="font-size:14.5px;margin-top:6px;line-height:1.6">{T.esc(n["why_he"])}</div>' if n.get("why_he") else ""
        img = f'<img src="{T.esc(n["thumb"])}" alt="" loading="lazy" onerror="this.remove()">' if n.get("thumb") else ""
        lst += (f'<div class="list-item">{img}<div style="flex:1;min-width:0"><div class="t">'
                f'<a href="{T.esc(n.get("link"))}" target="_blank" rel="noopener" style="text-decoration:none">{T.esc(title)}</a></div>{orig}{why}'
                f'<div class="meta">{chip} {tk} · {T.esc(n.get("publisher"))} · {ago(n.get("time"))}</div></div></div>')
    body = head + tgrid + meter + f'<div class="sheet">{lst or "אין כותרות."}</div>'
    who = ", ".join(d.get("tickers") or []) or "השוק"
    sub = f"{T.esc(who)} · {T.stamp_line()}"
    p = T.save(T.page("חדשות שוק", body, "/trader-news", sub), "news", a.out)
    print("SUMMARY: " + json.dumps({"items": len(items), "sentiment": cnt, "report": p}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("tickers", nargs="*")
    f.add_argument("--market", action="store_true", help="add general market headlines")
    f.add_argument("--per", type=int, default=8, help="headlines per query")
    f.add_argument("--max", type=int, default=24)
    f.add_argument("--out", default="news.json")
    r = sub.add_parser("render")
    r.add_argument("file")
    r.add_argument("--out")
    a = ap.parse_args()
    fetch(a) if a.cmd == "fetch" else render(a)


if __name__ == "__main__":
    main()
