#!/usr/bin/env python3
"""/trader-timemachine: run thousands of possible price paths from an entry and
count how often the target is hit before the stop. Monte Carlo, not a forecast.

  python3 timemachine.py TSLA
  python3 timemachine.py TSLA --entry 364.18 --target 370 --stop 358 --sims 10000
  python3 timemachine.py NVDA --target-pct 2 --stop-pct 1 --horizon 5d --side long
"""
import argparse
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradelib as T  # noqa: E402

BARS_PER_DAY = 78  # 6.5h of 5-minute bars


def session_returns(bars):
    """5-minute log returns inside each session + overnight gaps (open vs previous close)."""
    intra, gaps = [], []
    prev = None
    for b in bars:
        d = T.ny(b["t"])
        if not (9 * 60 + 30 <= d.hour * 60 + d.minute < 16 * 60):
            continue
        if prev is not None:
            pd = T.ny(prev["t"]).date()
            if pd == d.date():
                if prev["c"] > 0 and b["c"] > 0:
                    intra.append(math.log(b["c"] / prev["c"]))
            elif prev["c"] > 0 and b["o"] > 0:
                gaps.append(math.log(b["o"] / prev["c"]))
                intra.append(math.log(b["c"] / b["o"]))
        prev = b
    return intra, gaps


def last_days_vol(bars, days=5):
    by_day = {}
    for b in bars:
        by_day.setdefault(T.ny(b["t"]).date(), []).append(b)
    keys = sorted(by_day)[-days:]
    rets = []
    for k in keys:
        cs = [b["c"] for b in by_day[k]]
        rets += T.log_returns(cs)
    return T.stdev(rets) if len(rets) > 10 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--entry", type=float)
    ap.add_argument("--target", type=float)
    ap.add_argument("--stop", type=float)
    ap.add_argument("--target-pct", type=float)
    ap.add_argument("--stop-pct", type=float)
    ap.add_argument("--side", choices=["long", "short"], default="long")
    ap.add_argument("--horizon", default="session",
                    help="session (until today's close / a full day) | 30m | 90m | 1d | 3d | 5d")
    ap.add_argument("--sims", type=int, default=10000)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.seed is not None:
        random.seed(a.seed)
    sym = a.ticker.upper()

    mode = "intraday"
    try:
        ch = T.yahoo_chart(sym, "60d", "5m")
        bars = ch["bars"]
        if len(bars) < 200:
            raise RuntimeError("short")
        intra, gaps = session_returns(bars)
        mu = sum(intra) / len(intra)
        intra = [r - mu for r in intra]  # neutral drift: a simulation, not a forecast
        base_vol = T.stdev(intra)
        recent = last_days_vol(bars) or base_vol
        k = recent / base_vol if base_vol else 1.0
        pool = [r * k for r in intra]
        gmu = sum(gaps) / len(gaps) if gaps else 0
        gpool = [g - gmu for g in gaps] or [0.0]
        last_px = ch["meta"].get("regularMarketPrice") or bars[-1]["c"]
    except Exception:  # noqa: BLE001  -> daily-volatility fallback (Nasdaq/Yahoo daily bars)
        mode = "daily"
        try:
            ch = T.yahoo_chart(sym, "1y", "1d")
        except Exception as e:  # noqa: BLE001
            T.die(str(e))
        closes = [b["c"] for b in ch["bars"]]
        if len(closes) < 60:
            T.die(f"אין מספיק נתונים ל-{sym}")
        dr = T.log_returns(closes)
        mu = sum(dr) / len(dr)
        dr = [r - mu for r in dr]
        base_vol = T.stdev(dr) / math.sqrt(BARS_PER_DAY)
        recent_d = T.stdev(dr[-20:]) / math.sqrt(BARS_PER_DAY)
        k = recent_d / base_vol if base_vol else 1.0
        pool = [r / math.sqrt(BARS_PER_DAY) * k for r in dr]  # fat tails kept, per 5-minute step
        gpool = [0.0]
        last_px = closes[-1]

    entry = a.entry or last_px

    # Horizon in 5-minute steps, plus where the overnight gaps fall
    now = T.now_ny()
    mins_now = now.hour * 60 + now.minute
    in_session = now.weekday() < 5 and 9 * 60 + 30 <= mins_now < 16 * 60
    hz = a.horizon.lower()
    if hz == "session":
        steps = max(6, (16 * 60 - mins_now) // 5) if in_session else BARS_PER_DAY
        start_min = mins_now - mins_now % 5 if in_session else 9 * 60 + 30
        days = 1
    elif hz.endswith("m"):
        steps = max(1, int(hz[:-1]) // 5)
        start_min = mins_now - mins_now % 5 if in_session else 9 * 60 + 30
        days = 1
    elif hz.endswith("d"):
        days = max(1, int(hz[:-1]))
        steps = BARS_PER_DAY * days
        start_min = 9 * 60 + 30
    else:
        T.die("horizon לא מוכר")
    gap_at = set(range(BARS_PER_DAY, steps, BARS_PER_DAY)) if hz.endswith("d") else set()

    sigma_h = base_vol * k * math.sqrt(steps)
    move = round(max(0.3, sigma_h * 100 * 0.8), 1)
    sgn = 1 if a.side == "long" else -1
    target = a.target or entry * (1 + sgn * (a.target_pct if a.target_pct else move) / 100)
    stop = a.stop or entry * (1 - sgn * (a.stop_pct if a.stop_pct else move) / 100)
    if (target - entry) * sgn <= 0 or (entry - stop) * sgn <= 0:
        T.die("היעד והסטופ צריכים להיות משני צידי מחיר הכניסה (בהתאם לכיוון העסקה)")

    n_keep = min(a.sims, 500)
    every = max(1, steps // 90)
    hit_t = hit_s = 0
    t_times, ends, kept, kept_out = [], [], [], []
    up_lvl, dn_lvl = max(target, stop), min(target, stop)
    for s in range(a.sims):
        p = entry
        outcome, when = 0, None
        path = [0] if s < n_keep else None
        for i in range(steps):
            r = random.choice(pool)
            if i in gap_at:
                r += random.choice(gpool)
            p *= math.exp(r)
            if outcome == 0:
                if p >= up_lvl:
                    outcome, when = (1 if up_lvl == target else -1), i
                elif p <= dn_lvl:
                    outcome, when = (1 if dn_lvl == target else -1), i
            if path is not None and (i % every == every - 1 or i == steps - 1):
                path.append(round((p / entry - 1) * 10000))
        ends.append(p)
        if outcome == 1:
            hit_t += 1
            t_times.append(when)
        elif outcome == -1:
            hit_s += 1
        if path is not None:
            kept.append(path)
            kept_out.append(outcome)

    n = a.sims
    p_t, p_s = hit_t / n, hit_s / n
    p_n = 1 - p_t - p_s
    ends.sort()
    reward, risk = abs(target - entry), abs(entry - stop)
    # expected value: closed at target / stop, otherwise marked at horizon end
    ev = p_t * reward - p_s * risk + p_n * 0  # neutral drift: unresolved paths average ~0
    rr = reward / risk if risk else None
    be = risk / (reward + risk) if reward + risk else None
    med_t = sorted(t_times)[len(t_times) // 2] if t_times else None

    # x labels
    def lab(step):
        if hz.endswith("d"):
            return f"יום {step // BARS_PER_DAY + 1}"
        m = start_min + step * 5
        return f"{m // 60:02d}:{m % 60:02d}"
    npts = len(kept[0]) if kept else 2
    ticks = 4
    xl = [(round(j * (npts - 1) / ticks), lab(round(j * (steps) / ticks))) for j in range(ticks + 1)]

    pct_t = (target / entry - 1) * 100
    pct_s = (stop / entry - 1) * 100
    payload = {"paths": kept, "out": kept_out, "sims": n, "entry": entry, "target": target, "stop": stop,
               "xl": xl, "npts": npts}

    title = f"מכונת הזמן · {T.ltr(sym)}"
    sub = (f"כניסה {T.ltr(T.fmt_price(entry))} · {T.fmt_date(now)} · "
           f"{'לונג' if a.side == 'long' else 'שורט'} · סימולציה, לא תחזית")

    big = (f'<div class="row" style="margin:6px 0 18px"><span class="badge">{n:,}</span>'
           f'<span class="headline" style="margin:0">עתידים אפשריים</span></div>')
    canvas = f"""
<div class="sheet chart" style="padding:18px 14px 10px">
 <div class="row" style="padding:0 6px 6px"><b style="font-size:20px">סימולציות: <span id="cnt" dir="ltr">0</span></b>
 <span class="spacer"></span><span class="chip up">יעד {T.ltr(T.fmt_price(target))} ({T.ltr(T.fmt_pct(pct_t, 1))})</span>
 <span class="chip down">סטופ {T.ltr(T.fmt_price(stop))} ({T.ltr(T.fmt_pct(pct_s, 1))})</span></div>
 <canvas id="tm" class="tm-canvas"></canvas>
 <div class="legend"><span><i style="border-color:{T.GREEN}"></i>הגיעו ליעד קודם</span>
 <span><i style="border-color:{T.RED}"></i>נעצרו בסטופ</span><span><i style="border-color:#555"></i>לא הגיעו לאף אחד</span>
 <span class="spacer"></span><button id="replay" style="font:inherit;font-weight:800;border:2px solid #141414;background:none;border-radius:999px;padding:3px 14px;cursor:pointer">▶ הרץ שוב</button></div>
</div>"""

    stats = (
        '<div class="grid g3" style="margin-bottom:18px">'
        + T.stat("הגיעו ליעד לפני הסטופ", f"{p_t * 100:.1f}%", f"{T.ltr(f'{hit_t:,}')} מתוך {T.ltr(f'{n:,}')}", "up")
        + T.stat("נעצרו בסטופ קודם", f"{p_s * 100:.1f}%", f"{T.ltr(f'{hit_s:,}')} מתוך {T.ltr(f'{n:,}')}", "down")
        + T.stat("לא הגיעו לאף אחד", f"{p_n * 100:.1f}%", "נשארו פתוחים בסוף הטווח", "flat")
        + "</div>")

    verdict = "יתרון סטטיסטי קל לעסקה" if ev > 0.02 * risk else ("בערך מטבע הוגן" if ev > -0.02 * risk else "הסיכויים נגדך")
    rec = T.receipt(
        f"{sym} · {'LONG' if a.side == 'long' else 'SHORT'}", f"{lab(0)} → {lab(steps)} · {steps} נרות של 5 דקות",
        rows=[("כניסה", T.fmt_price(entry)),
              ("יעד", f'<span class="up">{T.fmt_price(target)}</span>'),
              ("סטופ", f'<span class="down">{T.fmt_price(stop)}</span>'),
              ("יחס סיכוי/סיכון", f"1 : {rr:.2f}" if rr else "—"),
              ("אחוז הצלחה נדרש לאיזון", f"{be * 100:.1f}%" if be else "—"),
              ("אחוז הצלחה בסימולציה", f"{p_t / (p_t + p_s) * 100:.1f}%" if p_t + p_s else "—"),
              ("זמן חציוני עד היעד (דקות)", f"{(med_t + 1) * 5}" if med_t is not None else "—")],
        total_label=f"תוחלת לעסקה, למניה · {verdict}",
        total_value=f'<span class="{T.tone(ev)}">{"+" if ev >= 0 else "−"}${abs(ev):.2f}</span>')

    pcts = [T.percentile(ends, q) for q in (0.05, 0.25, 0.5, 0.75, 0.95)]
    dist = T.table(["", "5%", "25%", "חציון", "75%", "95%"],
                   [["מחיר בסוף הטווח"] + [T.fmt_price(v) for v in pcts],
                    ["שינוי מהכניסה"] + [f'<span class="{T.tone(v / entry - 1)}">{T.fmt_pct((v / entry - 1) * 100)}</span>' for v in pcts]],
                   num_cols=(1, 2, 3, 4, 5))

    if mode == "intraday":
        src = (f"לקחתי {len(pool):,} תשואות אמיתיות של נרות 5 דקות של {T.ltr(sym)} מ-60 ימי המסחר האחרונים, "
               f"התאמתי אותן לתנודתיות של 5 הימים האחרונים (×{k:.2f}), הסרתי את המגמה, ")
    else:
        src = (f"נתונים תוך-יומיים לא היו זמינים, אז לקחתי {len(pool):,} תשואות יומיות אמיתיות של {T.ltr(sym)} מהשנה האחרונה, "
               f"פירקתי אותן לצעדים של 5 דקות והתאמתי לתנודתיות של 20 הימים האחרונים (×{k:.2f}), ")
    method = (f"<b>איך זה עובד:</b> {src}"
              f"ובניתי מהן {n:,} מסלולים אקראיים. כל מסלול נבדק: האם נגע ביעד או בסטופ קודם. "
              "זו סימולציה של מה שיכול לקרות, לא תחזית של מה שיקרה.")

    body = (big + canvas + stats + '<div class="grid g2">'
            + f'<div>{rec}</div><div><div class="sheet"><h3>טווח המחירים בסוף</h3>{dist}'
            f'<p style="font-size:14px;line-height:1.7;margin:16px 0 0">{method}</p></div></div></div>')

    js = """<script>
const D=__DATA__;const cv=document.getElementById('tm'),cx=cv.getContext('2d');
function size(){const r=cv.getBoundingClientRect(),d=window.devicePixelRatio||1;cv.width=r.width*d;cv.height=r.height*d;cx.setTransform(d,0,0,d,0,0);return[r.width,r.height]}
let W,H,run=0;const pad={t:16,r:58,b:30,l:Math.min(52,innerWidth*.06)};
function bounds(){let lo=Math.min((D.stop/D.entry-1)*1e4,(D.target/D.entry-1)*1e4),hi=-lo;lo=Math.min(lo,(D.target/D.entry-1)*1e4);hi=Math.max((D.target/D.entry-1)*1e4,(D.stop/D.entry-1)*1e4);
for(const p of D.paths)for(const v of p){if(v<lo)lo=v;if(v>hi)hi=v}const m=(hi-lo)*.05;return[lo-m,hi+m]}
const [LO,HI]=bounds();
const X=i=>pad.l+i*(W-pad.l-pad.r)/(D.npts-1),Y=v=>pad.t+(HI-v)*(H-pad.t-pad.b)/(HI-LO),bp=p=>(p/D.entry-1)*1e4;
function frame(){cx.font='800 13px Heebo,system-ui,sans-serif';
 const L=(v,c,dash,lab)=>{const y=Y(bp(v));cx.setLineDash(dash);cx.strokeStyle=c;cx.lineWidth=2;cx.beginPath();cx.moveTo(pad.l,y);cx.lineTo(W-pad.r,y);cx.stroke();cx.setLineDash([]);cx.fillStyle=c;cx.textAlign='left';cx.fillText(v.toFixed(2),W-pad.r+6,y+5);if(lab){cx.textAlign='right';cx.fillText(lab,W-pad.r-4,y-7)}};
 L(D.target,'#2f7d55',[8,7],'יעד');L(D.stop,'#b8453a',[8,7],'סטופ');L(D.entry,'#141414',[2,5],'');
 cx.fillStyle='#6f6a60';cx.textAlign='center';for(const [i,l] of D.xl)cx.fillText(l,X(i),H-8);
 cx.fillStyle='#141414';cx.beginPath();cx.arc(X(0),Y(0),6,0,7);cx.fill();}
function draw(i,alpha,w){const p=D.paths[i],o=D.out[i];cx.strokeStyle=o==1?`rgba(47,125,85,${alpha})`:o==-1?`rgba(184,69,58,${alpha})`:`rgba(40,40,40,${alpha*.8})`;
 cx.lineWidth=w;cx.beginPath();cx.moveTo(X(0),Y(p[0]));for(let j=1;j<p.length;j++)cx.lineTo(X(j),Y(p[j]));cx.stroke();}
function play(){const id=++run;[W,H]=size();cx.clearRect(0,0,W,H);frame();const N=D.paths.length,cnt=document.getElementById('cnt');let k=0;const t0=performance.now(),dur=2600;
 const hero=D.out.indexOf(-1)>=0?D.out.indexOf(-1):0;
 (function step(now){if(id!==run)return;const f=Math.min(1,(now-t0)/dur),e=1-Math.pow(1-f,3),to=Math.floor(e*N);
  for(;k<to;k++)draw(k,.16,1);cnt.textContent=Math.round(e*D.sims).toLocaleString('en-US');
  if(f<1)requestAnimationFrame(step);else{draw(hero,1,2.6);frame()}})(t0);}
document.getElementById('replay').onclick=play;window.addEventListener('resize',()=>{clearTimeout(window.__r);window.__r=setTimeout(play,200)});
if('IntersectionObserver'in window){new IntersectionObserver((e,o)=>{if(e[0].isIntersecting){o.disconnect();play()}}).observe(cv)}else play();
</script>""".replace("__DATA__", json.dumps(payload, separators=(",", ":")))

    p = T.save(T.page(title, body + js, "/trader-timemachine", sub), f"timemachine-{sym}", a.out)
    summary = {"ticker": sym, "entry": round(entry, 4), "target": round(target, 4), "stop": round(stop, 4),
               "side": a.side, "sims": n, "p_target_first": round(p_t, 4), "p_stop_first": round(p_s, 4),
               "p_neither": round(p_n, 4), "ev_per_share": round(ev, 4), "rr": rr and round(rr, 3),
               "breakeven_winrate": be and round(be, 4), "steps_5m": steps, "vol_scale": round(k, 3),
               "end_price_pcts": {"p5": pcts[0], "p50": pcts[2], "p95": pcts[4]}, "report": p}
    print("SUMMARY: " + json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
