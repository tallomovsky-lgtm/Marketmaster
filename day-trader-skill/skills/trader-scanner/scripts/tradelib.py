"""tradelib: shared helpers for the day-trader-skill pack.

Pure standard library (no pip install needed). Three parts:
  1. Data: Yahoo Finance charts/spark/news and Nasdaq screener/earnings.
  2. Math: indicators and small statistics helpers.
  3. Look: the cream "receipt" theme (Hebrew, RTL) and SVG chart builders.

Every skill ships its own copy of this file (see build.py), so a skill
uploaded alone to claude.ai still works.

Offline / blocked network: set TRADER_DATA=/path/data.json to feed bars
yourself (for example from the IBKR connector). Format:
  {"TSLA": {"daily": [{"t": 1794258000, "o":1, "h":1, "l":1, "c":1, "v":1}, ...],
            "intraday": [...same, 5-minute bars...]}}
"""
from __future__ import annotations

import datetime as _dt
import html as _html
import json
import math
import os
import random
import ssl
import statistics
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (compatible; day-trader-skill/1.0)"


class RateLimited(RuntimeError):
    pass

# --------------------------------------------------------------------------
# Time
# --------------------------------------------------------------------------
try:
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
except Exception:  # Windows without tzdata
    NY = _dt.timezone(_dt.timedelta(hours=-5), "ET")

HE_DAYS = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]


def ny(ts: float) -> _dt.datetime:
    return _dt.datetime.fromtimestamp(ts, NY)


def now_ny() -> _dt.datetime:
    return _dt.datetime.now(NY)


def fmt_date(d: _dt.datetime | _dt.date) -> str:
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def fmt_time(d: _dt.datetime) -> str:
    return f"{d.hour:02d}:{d.minute:02d}"


def session_state(n: _dt.datetime | None = None) -> str:
    n = n or now_ny()
    m = n.hour * 60 + n.minute
    if n.weekday() >= 5:
        return "סוף שבוע, השוק סגור"
    if m < 4 * 60:
        return "השוק סגור"
    if m < 9 * 60 + 30:
        return "לפני הפתיחה"
    if m < 16 * 60:
        return "בזמן מסחר"
    if m < 20 * 60:
        return "אחרי הסגירה"
    return "השוק סגור"


def stamp_line() -> str:
    n = now_ny()
    return f"{fmt_date(n)} · {fmt_time(n)} שעון ניו יורק"


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def _ctx():
    ctx = ssl.create_default_context()
    bundle = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if bundle and os.path.exists(bundle):
        ctx.load_verify_locations(bundle)
    return ctx


def http_get(url: str, accept: str = "application/json", retries: int = 2, timeout: int = 25) -> bytes:
    """GET with polite retries. On HTTP 429 it waits (Retry-After, capped) and then gives up
    with RateLimited so callers can fall back to another source."""
    import urllib.error
    host = urllib.parse.urlsplit(url).netloc
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": accept, "Accept-Language": "en-US,en;q=0.9"})
            with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                if i == retries:
                    raise RateLimited(f"{host} הגביל את קצב הבקשות (429). נסה שוב בעוד כמה דקות.") from e
                wait = e.headers.get("Retry-After")
                time.sleep(min(float(wait) if wait and wait.isdigit() else 4 * (i + 1), 20))
                continue
            if 400 <= e.code < 500:
                break
            time.sleep(1.0 * (i + 1))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.0 * (i + 1))
    raise RuntimeError(f"לא הצלחתי למשוך נתונים מ-{host}: {last}")


def http_json(url: str, **kw):
    return json.loads(http_get(url, **kw).decode("utf-8"))


# --------------------------------------------------------------------------
# Offline override (IBKR / manual data)
# --------------------------------------------------------------------------
_OVERRIDE = None


def _override():
    global _OVERRIDE
    if _OVERRIDE is None:
        p = os.environ.get("TRADER_DATA")
        _OVERRIDE = {}
        if p and os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                _OVERRIDE = {k.upper(): v for k, v in json.load(f).items()}
    return _OVERRIDE


# --------------------------------------------------------------------------
# Yahoo Finance
# --------------------------------------------------------------------------
def yahoo_chart(symbol: str, range_: str = "6mo", interval: str = "1d", prepost: bool = False) -> dict:
    """Return {"symbol", "meta", "bars": [{t,o,h,l,c,v}]} with empty bars removed."""
    sym = symbol.upper()
    ov = _override().get(sym)
    if ov:
        key = "daily" if interval in ("1d", "1wk", "1mo") else "intraday"
        bars = ov.get(key) or []
        return {"symbol": sym, "meta": ov.get("meta", {}), "bars": bars}
    q = urllib.parse.urlencode({"range": range_, "interval": interval,
                                "includePrePost": "true" if prepost else "false"})
    try:
        data = http_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?{q}")
    except Exception as e:  # noqa: BLE001
        if interval == "1d":  # daily bars: Nasdaq has the same history
            days = {"5d": 7, "1mo": 31, "3mo": 92, "6mo": 183, "1y": 366, "2y": 731, "5y": 1827}.get(range_, 366)
            try:
                bars = nasdaq_history(sym, days)
            except Exception:  # noqa: BLE001
                bars = []
            if bars:
                return {"symbol": sym, "meta": {"regularMarketPrice": bars[-1]["c"], "source": "nasdaq"},
                        "bars": bars}
        raise e
    res = (data.get("chart") or {}).get("result")
    if not res:
        err = (data.get("chart") or {}).get("error") or {}
        raise RuntimeError(f"Yahoo: אין נתונים ל-{sym} ({err.get('description', 'unknown')})")
    r = res[0]
    ts = r.get("timestamp") or []
    q0 = (r.get("indicators", {}).get("quote") or [{}])[0]
    bars = []
    for i, t in enumerate(ts):
        o, h, l, c, v = (q0.get(k, [None] * len(ts))[i] for k in ("open", "high", "low", "close", "volume"))
        if c is None or o is None:
            continue
        bars.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v or 0})
    return {"symbol": sym, "meta": r.get("meta", {}), "bars": bars}


def yahoo_spark(symbols: list[str], range_: str = "3mo", interval: str = "1d", workers: int = 3) -> dict:
    """Closes for many symbols. Returns {SYM: {"t": [...], "c": [...], "prev": float|None}}."""
    out: dict = {}
    syms = [s.upper() for s in symbols]
    ov = _override()
    for s in [s for s in syms if s in ov]:
        bars = ov[s].get("daily" if interval == "1d" else "intraday") or []
        out[s] = {"t": [b["t"] for b in bars], "c": [b["c"] for b in bars], "prev": None}
    todo = [s for s in syms if s not in out]
    chunks = [todo[i:i + 20] for i in range(0, len(todo), 20)]

    def one(chunk):
        q = urllib.parse.urlencode({"symbols": ",".join(chunk), "range": range_, "interval": interval})
        try:
            d = http_json(f"https://query1.finance.yahoo.com/v8/finance/spark?{q}", retries=1)
        except Exception:  # noqa: BLE001
            return {}
        got = {}
        for k, v in d.items():
            if not isinstance(v, dict) or "close" not in v:
                continue
            ts, cs = v.get("timestamp") or [], v.get("close") or []
            pairs = [(t, c) for t, c in zip(ts, cs) if c is not None]
            got[k.upper()] = {"t": [p[0] for p in pairs], "c": [p[1] for p in pairs],
                              "prev": v.get("chartPreviousClose")}
        return got

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for got in ex.map(one, chunks):
            out.update(got)
    missing = [s for s in todo if s not in out]
    if missing and interval == "1d" and len(missing) <= 300:
        days = {"1mo": 31, "3mo": 92, "6mo": 183, "1y": 366}.get(range_, 92)
        out.update(nasdaq_spark(missing, days))
    return out


def nasdaq_spark(symbols: list[str], days: int = 92, workers: int = 4) -> dict:
    """Fallback for yahoo_spark (daily only): one Nasdaq request per symbol."""
    def one(s):
        try:
            b = nasdaq_history(s, days)
            return s, {"t": [x["t"] for x in b], "c": [x["c"] for x in b], "prev": None}
        except Exception:  # noqa: BLE001
            return s, None
    out = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for s, v in ex.map(one, [s.upper() for s in symbols]):
            if v and v["c"]:
                out[s] = v
    return out


def yahoo_news(query: str, count: int = 10) -> list[dict]:
    q = urllib.parse.urlencode({"q": query, "newsCount": count, "quotesCount": 0})
    d = http_json(f"https://query1.finance.yahoo.com/v1/finance/search?{q}")
    items = []
    for n in d.get("news", []):
        thumb = None
        for r in ((n.get("thumbnail") or {}).get("resolutions") or []):
            if r.get("width", 0) <= 400:
                thumb = r.get("url")
        items.append({"title": n.get("title"), "publisher": n.get("publisher"), "link": n.get("link"),
                      "time": n.get("providerPublishTime"), "tickers": n.get("relatedTickers") or [],
                      "thumb": thumb})
    return items


# --------------------------------------------------------------------------
# Nasdaq
# --------------------------------------------------------------------------
def _num(s):
    if s in (None, "", "NA", "N/A"):
        return None
    try:
        return float(str(s).replace("$", "").replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def nasdaq_universe(us_only: bool = True) -> list[dict]:
    """All Nasdaq/NYSE/AMEX listed stocks with last price, % change, volume, market cap, sector."""
    d = http_json("https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true", timeout=60)
    rows = []
    for r in d["data"]["rows"]:
        sym = (r.get("symbol") or "").strip().upper()
        if not sym or any(ch in sym for ch in "^/ "):
            continue
        if us_only and (r.get("country") or "") != "United States":
            continue
        rows.append({"symbol": sym.replace(".", "-"), "name": (r.get("name") or "").strip(),
                     "price": _num(r.get("lastsale")), "pct": _num(r.get("pctchange")),
                     "volume": _num(r.get("volume")) or 0, "mcap": _num(r.get("marketCap")) or 0,
                     "sector": (r.get("sector") or "").strip() or "Other",
                     "industry": (r.get("industry") or "").strip()})
    return rows


def nasdaq_history(symbol: str, days: int = 366, assetclass: str = "stocks") -> list[dict]:
    """Daily OHLCV bars (oldest first) from Nasdaq. Works for US stocks and ETFs."""
    end = _dt.date.today()
    start = end - _dt.timedelta(days=days)
    q = urllib.parse.urlencode({"assetclass": assetclass, "fromdate": start.isoformat(),
                                "todate": end.isoformat(), "limit": 9999})
    d = http_json(f"https://api.nasdaq.com/api/quote/{urllib.parse.quote(symbol.upper())}/historical?{q}")
    rows = (((d.get("data") or {}).get("tradesTable") or {}).get("rows")) or []
    if not rows and assetclass == "stocks":
        return nasdaq_history(symbol, days, "etf")
    bars = []
    for r in rows:
        try:
            m, dd, y = (int(x) for x in r["date"].split("/"))
            t = _dt.datetime(y, m, dd, 16, 0, tzinfo=NY).timestamp()
            bars.append({"t": int(t), "o": _num(r["open"]), "h": _num(r["high"]), "l": _num(r["low"]),
                         "c": _num(r["close"]), "v": _num(r["volume"]) or 0})
        except Exception:  # noqa: BLE001
            continue
    bars = [b for b in bars if b["c"] is not None and b["o"] is not None]
    bars.sort(key=lambda b: b["t"])
    return bars


def nasdaq_earnings(day: _dt.date) -> list[dict]:
    d = http_json(f"https://api.nasdaq.com/api/calendar/earnings?date={day.isoformat()}")
    rows = (d.get("data") or {}).get("rows") or []
    out = []
    for r in rows:
        out.append({"symbol": r.get("symbol"), "name": r.get("name"),
                    "time": {"time-pre-market": "לפני הפתיחה", "time-after-hours": "אחרי הסגירה"}.get(
                        r.get("time"), "לא ידוע"),
                    "time_code": r.get("time"),
                    "mcap": _num(r.get("marketCap")) or 0, "eps_forecast": r.get("epsForecast"),
                    "n_est": r.get("noOfEsts"), "last_eps": r.get("lastYearEPS"),
                    "quarter": r.get("fiscalQuarterEnding")})
    return out


def nasdaq_earnings_history(symbol: str) -> list[dict]:
    d = http_json(f"https://api.nasdaq.com/api/company/{symbol.upper()}/earnings-surprise")
    rows = (((d.get("data") or {}).get("earningsSurpriseTable") or {}).get("rows")) or []
    out = []
    for r in rows:
        try:
            m, dd, y = (int(x) for x in r["dateReported"].split("/"))
            out.append({"date": _dt.date(y, m, dd), "quarter": r.get("fiscalQtrEnd"), "eps": r.get("eps"),
                        "forecast": r.get("consensusForecast"), "surprise": _num(r.get("percentageSurprise"))})
        except Exception:  # noqa: BLE001
            continue
    return out


# --------------------------------------------------------------------------
# Math
# --------------------------------------------------------------------------
def pct(a, b):
    return (a / b - 1) * 100 if a is not None and b else None


def sma(vals, n):
    out, s = [], 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        out.append(s / n if i >= n - 1 else None)
    return out


def ema(vals, n):
    out, k, e = [], 2 / (n + 1), None
    for v in vals:
        e = v if e is None else v * k + e * (1 - k)
        out.append(e)
    return out


def rsi(vals, n=14):
    if len(vals) <= n:
        return [None] * len(vals)
    out = [None] * len(vals)
    gains = [max(vals[i] - vals[i - 1], 0) for i in range(1, len(vals))]
    losses = [max(vals[i - 1] - vals[i], 0) for i in range(1, len(vals))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    out[n] = 100 - 100 / (1 + ag / al) if al else 100.0
    for i in range(n + 1, len(vals)):
        ag = (ag * (n - 1) + gains[i - 1]) / n
        al = (al * (n - 1) + losses[i - 1]) / n
        out[i] = 100 - 100 / (1 + ag / al) if al else 100.0
    return out


def atr(bars, n=14):
    trs = []
    for i, b in enumerate(bars):
        pc = bars[i - 1]["c"] if i else b["c"]
        trs.append(max(b["h"] - b["l"], abs(b["h"] - pc), abs(b["l"] - pc)))
    return sma(trs, n)


def vwap(bars):
    pv = vv = 0.0
    out = []
    for b in bars:
        tp = (b["h"] + b["l"] + b["c"]) / 3
        pv += tp * (b["v"] or 0)
        vv += b["v"] or 0
        out.append(pv / vv if vv else tp)
    return out


def log_returns(vals):
    return [math.log(vals[i] / vals[i - 1]) for i in range(1, len(vals)) if vals[i - 1] > 0 and vals[i] > 0]


def percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    return sorted_vals[f] if f == c else sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def stdev(vals):
    return statistics.pstdev(vals) if len(vals) > 1 else 0.0


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------
def esc(s) -> str:
    return _html.escape("" if s is None else str(s))


def fmt_price(v, dec=None) -> str:
    if v is None:
        return "—"
    if dec is None:
        dec = 2 if abs(v) < 1000 else 0
        if 0 < abs(v) < 1:
            dec = 4
    return f"{v:,.{dec}f}"


def money(v, dec=0, sign=True) -> str:
    """+$1,234 / −$140 (real minus sign, dollar after the sign)."""
    if v is None:
        return "—"
    s = f"${abs(v):,.{dec}f}"
    if v < 0:
        return "−" + s
    return ("+" + s) if sign and v > 0 else s


def fmt_pct(v, dec=2, sign=True) -> str:
    if v is None:
        return "—"
    return f"{v:+.{dec}f}%" if sign else f"{v:.{dec}f}%"


def fmt_big(v) -> str:
    if not v:
        return "—"
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= div:
            return f"{v / div:,.1f}{suf}"
    return f"{v:,.0f}"


def tone(v) -> str:
    if v is None or abs(v) < 1e-9:
        return "flat"
    return "up" if v > 0 else "down"


def he(s) -> str:
    """Isolate a Hebrew phrase that sits inside a left-to-right (numeric) slot."""
    return f'<bdi dir="rtl">{s}</bdi>'


def ltr(s) -> str:
    """Wrap Latin/number text so it reads left-to-right inside Hebrew."""
    return f'<bdi dir="ltr">{s}</bdi>'


# --------------------------------------------------------------------------
# Theme
# --------------------------------------------------------------------------
INK, MUTED, PAPER, BG = "#141414", "#6f6a60", "#fbf8f1", "#ebe6da"
ORANGE, GREEN, RED, GRID = "#d8693b", "#2f7d55", "#b8453a", "#d9d1c0"

CSS = r"""
:root{--bg:#ebe6da;--grid:rgba(70,58,35,.075);--paper:#fbf8f1;--tile:#efe9dc;--ink:#141414;
--muted:#6f6a60;--line:#d3cab7;--orange:#d8693b;--orange-d:#b4542c;--green:#2f7d55;--red:#b8453a;
--green-bg:#e3eee4;--red-bg:#f4e2dd}
*{box-sizing:border-box}
html{background:var(--bg)}
body{margin:0;color:var(--ink);font-family:"Heebo","Rubik","Assistant",system-ui,-apple-system,"Segoe UI",Arial,sans-serif;
background-color:var(--bg);background-image:linear-gradient(var(--grid) 1px,transparent 1px),
linear-gradient(90deg,var(--grid) 1px,transparent 1px);background-size:34px 34px;min-height:100vh;
font-feature-settings:"tnum" 1;-webkit-font-smoothing:antialiased}
.wrap{max-width:1000px;margin:0 auto;padding:28px 16px 64px}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 6px;flex-wrap:wrap}
h1{font-size:clamp(28px,5.4vw,46px);font-weight:900;letter-spacing:-.5px;margin:0;line-height:1.05}
h2{font-size:22px;font-weight:900;margin:0 0 12px}
h3{font-size:16px;font-weight:800;margin:0 0 8px}
.sub{color:var(--muted);font-size:15px;margin:2px 0 22px}
.pill{display:inline-block;background:var(--ink);color:#fff;border-radius:999px;padding:7px 18px 8px;
font-weight:800;font-size:17px;direction:ltr;letter-spacing:.2px;white-space:nowrap}
.pill.light{background:transparent;color:var(--ink);border:2px solid var(--ink)}
.sheet{background:var(--paper);border-radius:18px;padding:22px;box-shadow:0 1px 0 rgba(0,0,0,.04),
0 10px 30px -12px rgba(60,45,20,.25);margin:0 0 18px}
.receipt-wrap{filter:drop-shadow(0 10px 14px rgba(60,45,20,.16));margin:0 0 26px}
.receipt{background:var(--paper);padding:24px 26px 34px;
-webkit-mask:conic-gradient(from -45deg at bottom,#0000,#000 1deg 89deg,#0000 90deg) 50%/22px 100%;
mask:conic-gradient(from -45deg at bottom,#0000,#000 1deg 89deg,#0000 90deg) 50%/22px 100%}
.receipt .r-title{font-weight:900;font-size:30px;line-height:1.1;direction:ltr;text-align:right}
.receipt .r-title.he{direction:rtl}
.receipt .r-sub{color:var(--muted);font-size:15px;margin-top:4px}
.dash{border:0;border-top:2px dashed var(--line);margin:14px 0}
.r-row{display:flex;justify-content:space-between;align-items:baseline;gap:10px;padding:5px 0;font-size:17px;font-weight:700}
.r-row .k{font-weight:700}.r-row .v{font-weight:800;direction:ltr}
.r-row .muted{color:var(--muted);font-weight:500}
.r-total{font-size:15px;color:var(--ink);font-weight:800;margin-top:4px}
.r-big{font-size:clamp(46px,9vw,72px);font-weight:900;line-height:1;direction:ltr;text-align:right;letter-spacing:-1px}
.check{color:var(--green);font-weight:900}
.cross{color:var(--red);font-weight:900}
.badge{display:inline-block;background:var(--orange);color:#fff;font-weight:900;border-radius:12px;
padding:6px 18px 8px;box-shadow:0 5px 0 var(--orange-d);font-size:clamp(26px,5vw,44px);line-height:1;direction:ltr}
.badge.sm{font-size:18px;padding:4px 12px 5px;border-radius:9px;box-shadow:0 3px 0 var(--orange-d)}
.stamp{display:inline-block;color:var(--orange);border:5px solid var(--orange);border-radius:16px;
padding:4px 22px 8px;font-weight:900;font-size:clamp(34px,7vw,58px);transform:rotate(-7deg);
filter:url(#rough);opacity:.92;line-height:1.05;background:transparent}
.headline{font-size:clamp(30px,6vw,52px);font-weight:900;line-height:1.08;margin:14px 0 22px;letter-spacing:-.5px}
.headline .o{color:var(--orange)}
.grid{display:grid;gap:14px}
.g2{grid-template-columns:repeat(2,minmax(0,1fr))}
.g3{grid-template-columns:repeat(3,minmax(0,1fr))}
.g4{grid-template-columns:repeat(4,minmax(0,1fr))}
@media (max-width:720px){.g4,.g3{grid-template-columns:repeat(2,minmax(0,1fr))}.g2{grid-template-columns:minmax(0,1fr)}}
@media (max-width:440px){.g3{grid-template-columns:minmax(0,1fr)}.wrap{padding:20px 12px 48px}.sheet{padding:16px}.receipt{padding:20px 18px 32px}}
.grid>*{min-width:0}
.tm-canvas{width:100%;aspect-ratio:900/420;display:block}@media (max-width:600px){.tm-canvas{aspect-ratio:4/3.4}}
.stat{background:var(--paper);border-radius:14px;padding:14px 16px;box-shadow:0 6px 18px -12px rgba(60,45,20,.35)}
.stat .l{color:var(--muted);font-size:13px;font-weight:600}
.stat .v{font-size:28px;font-weight:900;direction:ltr;text-align:right;line-height:1.15;margin-top:2px}
.stat .s{font-size:13px;color:var(--muted)}
.up{color:var(--green)}.down{color:var(--red)}.flat{color:var(--muted)}
.tile{background:var(--tile);border-radius:12px;padding:10px 12px 6px;position:relative;min-height:96px}
.tile.hit{background:#fffdf8;box-shadow:0 8px 20px -10px rgba(60,45,20,.45);outline:2px solid var(--ink)}
.tile .tk{font-weight:900;font-size:16px;direction:ltr;display:flex;gap:8px;align-items:baseline;justify-content:flex-end}
.tile .tk .ch{font-size:13px;font-weight:800}
.tile .nm{font-size:11px;color:var(--muted);direction:ltr;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile .tag{position:absolute;top:9px;right:10px;background:var(--orange);color:#fff;font-size:11px;font-weight:800;
border-radius:6px;padding:1px 7px 2px}
.tile svg{display:block;width:100%;height:56px;margin-top:4px}
table{width:100%;border-collapse:collapse;font-size:14.5px}
th{text-align:right;color:var(--muted);font-weight:700;font-size:12.5px;padding:8px 8px;border-bottom:2px solid var(--ink)}
td{padding:9px 8px;border-bottom:1px dashed var(--line);vertical-align:middle}
td.n,th.n{direction:ltr;text-align:left;white-space:nowrap}
td b{font-weight:900}
.tbl{overflow-x:auto}
.chip{display:inline-block;border-radius:999px;padding:2px 10px 3px;font-size:12.5px;font-weight:800;white-space:nowrap}
.chip.up{background:var(--green-bg);color:var(--green)}.chip.down{background:var(--red-bg);color:var(--red)}
.chip.flat{background:#ece7dc;color:var(--muted)}.chip.o{background:var(--orange);color:#fff}
.chip.ink{background:var(--ink);color:#fff}
.note{font-size:13px;color:var(--muted);margin-top:26px;line-height:1.6;text-align:center}
.note b{color:var(--ink)}
.chart svg{display:block;width:100%;height:auto;direction:ltr}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--muted);margin-top:8px}
.legend i{display:inline-block;width:18px;height:0;border-top:3px solid;vertical-align:middle;margin-left:6px}
.icon{display:flex;justify-content:center;padding:6px 0}
.row{display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.spacer{flex:1}
a{color:inherit}
.list-item{display:flex;gap:14px;padding:14px 0;border-bottom:1px dashed var(--line);align-items:flex-start}
.list-item:last-child{border-bottom:0}
.list-item .meta{font-size:12.5px;color:var(--muted);margin-top:4px}
.list-item .t{font-weight:800;font-size:16px;line-height:1.35}
.list-item img{width:84px;height:64px;object-fit:cover;border-radius:10px;flex:none;background:var(--tile)}
.kbd{font-family:ui-monospace,Menlo,Consolas,monospace;direction:ltr;font-size:.92em}
"""

ROUGH = ('<svg width="0" height="0" style="position:absolute" aria-hidden="true"><filter id="rough">'
         '<feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7"/>'
         '<feDisplacementMap in="SourceGraphic" scale="3"/></filter></svg>')

DISCLAIMER = ("המידע מוצג למטרות לימוד ומחקר בלבד ואינו ייעוץ השקעות או המלצה לקנות או למכור. "
              "נתונים: Yahoo Finance ו-Nasdaq, ייתכנו עיכובים וטעויות.")


def page(title: str, body: str, cmd: str | None = None, sub: str | None = None,
         extra_head: str = "", note: str | None = DISCLAIMER) -> str:
    top = f'<div class="top"><h1>{title}</h1>{f"<span class=pill>{esc(cmd)}</span>" if cmd else ""}</div>'
    subline = f'<div class="sub">{sub}</div>' if sub else ""
    foot = f'<div class="note">{note}<br><span class="kbd">day-trader-skill</span></div>' if note else ""
    return f"""<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html.unescape(_strip_tags(title))}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;700;800;900&display=swap" rel="stylesheet">
<style>{CSS}</style>{extra_head}</head>
<body>{ROUGH}<div class="wrap">{top}{subline}{body}{foot}</div></body></html>"""


def _strip_tags(s: str) -> str:
    out, inside = [], False
    for ch in s:
        if ch == "<":
            inside = True
        elif ch == ">":
            inside = False
        elif not inside:
            out.append(ch)
    return "".join(out)


def receipt(title: str, sub: str = "", rows: list | None = None, total_label: str = "",
            total_value: str = "", extra: str = "", he_title: bool = False) -> str:
    """rows: list of (label, value_html) or (label, value_html, cls). value None -> green check."""
    rh = ""
    for r in rows or []:
        label, val = r[0], r[1]
        cls = r[2] if len(r) > 2 else ""
        v = '<span class="check">✓</span>' if val is None else val
        rh += f'<div class="r-row"><span class="k {cls}">{label}</span><span class="v">{v}</span></div>'
    body = f'<div class="r-title{" he" if he_title else ""}">{title}</div>'
    if sub:
        body += f'<div class="r-sub">{sub}</div>'
    if rh:
        body += f'<hr class="dash">{rh}'
    if total_label or total_value:
        body += f'<hr class="dash"><div class="r-total">{total_label}</div><div class="r-big">{total_value}</div>'
    body += extra
    return f'<div class="receipt-wrap"><div class="receipt">{body}</div></div>'


def stat(label: str, value: str, sub: str = "", cls: str = "") -> str:
    return (f'<div class="stat"><div class="l">{label}</div><div class="v {cls}">{value}</div>'
            f'{f"<div class=s>{sub}</div>" if sub else ""}</div>')


def chip(text: str, cls: str = "flat") -> str:
    return f'<span class="chip {cls}">{text}</span>'


def table(headers: list, rows: list, num_cols: tuple = ()) -> str:
    th = "".join(f'<th class="{"n" if i in num_cols else ""}">{h}</th>' for i, h in enumerate(headers))
    trs = ""
    for r in rows:
        trs += "<tr>" + "".join(f'<td class="{"n" if i in num_cols else ""}">{c}</td>' for i, c in enumerate(r)) + "</tr>"
    return f'<div class="tbl"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


# --------------------------------------------------------------------------
# SVG charts (always left-to-right time axis)
# --------------------------------------------------------------------------
def _scale(lo, hi, a, b):
    span = (hi - lo) or 1.0
    return lambda v: a + (v - lo) * (b - a) / span


def spark_svg(vals: list, w: int = 220, h: int = 60, color: str = INK, width: float = 1.8,
              ref: float | None = None, ref_color: str = ORANGE) -> str:
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return f'<svg viewBox="0 0 {w} {h}"></svg>'
    lo, hi = min(vals + ([ref] if ref else [])), max(vals + ([ref] if ref else []))
    sx, sy = _scale(0, len(vals) - 1, 3, w - 3), _scale(lo, hi, h - 4, 4)
    pts = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(vals))
    refl = (f'<line x1="0" x2="{w}" y1="{sy(ref):.1f}" y2="{sy(ref):.1f}" stroke="{ref_color}" '
            f'stroke-width="1.4" stroke-dasharray="4 4"/>') if ref else ""
    return (f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none">{refl}<polyline points="{pts}" fill="none" '
            f'stroke="{color}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round" '
            f'vector-effect="non-scaling-stroke"/></svg>')


def line_chart_svg(series: list[dict], hlines: list[dict] | None = None, xlabels: list | None = None,
                   w: int = 900, h: int = 380, n: int | None = None, pad=(18, 70, 34, 14),
                   ylo: float | None = None, yhi: float | None = None, area: bool = False) -> str:
    """series: [{"values": [...], "color": "#", "width": 2, "dash": "", "opacity": 1}]
    hlines: [{"y": v, "color": "#", "dash": "6 6", "label": "יעד"}]
    xlabels: [(index, "10:15"), ...]. pad = (top, right, bottom, left)."""
    hlines = hlines or []
    allv = [v for s in series for v in s["values"] if v is not None] + [hl["y"] for hl in hlines]
    lo = ylo if ylo is not None else min(allv)
    hi = yhi if yhi is not None else max(allv)
    m = (hi - lo) * 0.06 or 1
    lo, hi = lo - m, hi + m
    n = n or max(len(s["values"]) for s in series)
    t, r, b, l = pad
    sx, sy = _scale(0, max(n - 1, 1), l, w - r), _scale(lo, hi, h - b, t)
    out = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" font-family="Heebo,system-ui,sans-serif">']
    for hl in hlines:
        y = sy(hl["y"])
        out.append(f'<line x1="{l}" x2="{w - r}" y1="{y:.1f}" y2="{y:.1f}" stroke="{hl.get("color", INK)}" '
                   f'stroke-width="{hl.get("width", 2)}" stroke-dasharray="{hl.get("dash", "7 7")}"/>')
        lab = hl.get("label")
        txt = f'{fmt_price(hl["y"])}'
        out.append(f'<text x="{w - r + 6}" y="{y + 5:.1f}" font-size="14" font-weight="800" fill="{hl.get("color", INK)}">{txt}</text>')
        if lab:
            out.append(f'<text x="{w - r - 4}" y="{y - 7:.1f}" text-anchor="end" font-size="13" font-weight="800" '
                       f'fill="{hl.get("color", INK)}" direction="rtl">{esc(lab)}</text>')
    for s in series:
        pts = [(sx(i), sy(v)) for i, v in enumerate(s["values"]) if v is not None]
        if len(pts) < 2:
            continue
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        if area or s.get("area"):
            out.append(f'<path d="{d} L{pts[-1][0]:.1f},{h - b} L{pts[0][0]:.1f},{h - b} Z" fill="{s.get("color", INK)}" opacity=".08"/>')
        out.append(f'<path d="{d}" fill="none" stroke="{s.get("color", INK)}" stroke-width="{s.get("width", 2)}" '
                   f'stroke-dasharray="{s.get("dash", "")}" opacity="{s.get("opacity", 1)}" stroke-linejoin="round" stroke-linecap="round"/>')
        if s.get("dot_start"):
            out.append(f'<circle cx="{pts[0][0]:.1f}" cy="{pts[0][1]:.1f}" r="7" fill="{INK}"/>')
    for i, lab in xlabels or []:
        anchor = "start" if i <= 0 else "end" if i >= n - 1 else "middle"
        out.append(f'<text x="{sx(i):.1f}" y="{h - 8}" text-anchor="{anchor}" font-size="13" font-weight="700" fill="{MUTED}">{esc(lab)}</text>')
    out.append("</svg>")
    return "".join(out)


def candles_svg(bars: list[dict], hlines: list[dict] | None = None, xlabels: list | None = None,
                w: int = 900, h: int = 420, pad=(16, 120, 34, 10), overlays: list[dict] | None = None) -> str:
    hlines = hlines or []
    overlays = overlays or []
    lo = min([b["l"] for b in bars] + [x["y"] for x in hlines if x.get("in_range", True)])
    hi = max([b["h"] for b in bars] + [x["y"] for x in hlines if x.get("in_range", True)])
    m = (hi - lo) * 0.04 or 1
    lo, hi = lo - m, hi + m
    t, r, b, l = pad
    n = len(bars)
    sx, sy = _scale(-0.5, n - 0.5, l, w - r), _scale(lo, hi, h - b, t)
    cw = max(1.5, (w - r - l) / n * 0.62)
    out = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" font-family="Heebo,system-ui,sans-serif">']
    placed = []
    for hl in sorted(hlines, key=lambda x: -x["y"]):
        if not (lo <= hl["y"] <= hi):
            continue
        y = sy(hl["y"])
        c = hl.get("color", INK)
        out.append(f'<line x1="{l}" x2="{w - r}" y1="{y:.1f}" y2="{y:.1f}" stroke="{c}" stroke-width="{hl.get("width", 1.6)}" '
                   f'stroke-dasharray="{hl.get("dash", "6 5")}" opacity=".9"/>')
        ty = y + 4
        while any(abs(ty - p) < 15 for p in placed):
            ty += 15
        placed.append(ty)
        out.append(f'<text x="{w - r + 6}" y="{ty:.1f}" font-size="12.5" font-weight="800" fill="{c}">'
                   f'{esc(hl.get("label", ""))} {fmt_price(hl["y"])}</text>')
    for i, bar in enumerate(bars):
        up = bar["c"] >= bar["o"]
        c = GREEN if up else RED
        x = sx(i)
        out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{sy(bar["h"]):.1f}" y2="{sy(bar["l"]):.1f}" stroke="{c}" stroke-width="1.2"/>')
        y1, y2 = sy(max(bar["o"], bar["c"])), sy(min(bar["o"], bar["c"]))
        out.append(f'<rect x="{x - cw / 2:.1f}" y="{y1:.1f}" width="{cw:.1f}" height="{max(y2 - y1, 1):.1f}" '
                   f'fill="{c if not up else PAPER}" stroke="{c}" stroke-width="1.2" rx="1"/>')
    for ov in overlays:
        pts = [(sx(i), sy(v)) for i, v in enumerate(ov["values"]) if v is not None]
        if len(pts) > 1:
            d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            out.append(f'<path d="{d}" fill="none" stroke="{ov.get("color", INK)}" stroke-width="{ov.get("width", 1.6)}" '
                       f'opacity="{ov.get("opacity", .8)}" stroke-dasharray="{ov.get("dash", "")}"/>')
    for i, lab in xlabels or []:
        out.append(f'<text x="{sx(i):.1f}" y="{h - 8}" text-anchor="middle" font-size="12.5" font-weight="700" fill="{MUTED}">{esc(lab)}</text>')
    out.append("</svg>")
    return "".join(out)


def bar_svg(labels: list[str], values: list[float], w: int = 900, h: int = 240, pad=(20, 10, 40, 10), fs: int = 13) -> str:
    t, r, b, l = pad
    n = len(values)
    if not n:
        return ""
    vmax = max(abs(v) for v in values) or 1
    zero = t + (h - t - b) / 2 if min(values) < 0 else h - b
    scale = ((h - t - b) / 2 if min(values) < 0 else (h - t - b)) / vmax
    bw = (w - l - r) / n
    out = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" font-family="Heebo,system-ui,sans-serif">',
           f'<line x1="{l}" x2="{w - r}" y1="{zero:.1f}" y2="{zero:.1f}" stroke="{INK}" stroke-width="1.5"/>']
    for i, (lab, v) in enumerate(zip(labels, values)):
        x = l + i * bw + bw * 0.18
        hh = abs(v) * scale
        y = zero - hh if v >= 0 else zero
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw * 0.64:.1f}" height="{max(hh, 1):.1f}" rx="4" fill="{GREEN if v >= 0 else RED}"/>')
        out.append(f'<text x="{x + bw * 0.32:.1f}" y="{h - 12}" text-anchor="middle" font-size="{fs}" font-weight="700" fill="{MUTED}">{esc(lab)}</text>')
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------
# Treemap (squarified)
# --------------------------------------------------------------------------
def squarify(values: list[float], x: float, y: float, w: float, h: float) -> list[tuple]:
    """Return rectangles (x, y, w, h) for values (sorted desc recommended)."""
    total = sum(values)
    if total <= 0 or not values:
        return []
    areas = [v * w * h / total for v in values]
    rects: list[tuple] = []

    def worst(row, side):
        s = sum(row)
        return max(max(side * side * a / (s * s), (s * s) / (side * side * a)) for a in row)

    def layout(row, x, y, w, h):
        s = sum(row)
        if w >= h:
            cw = s / h
            yy = y
            for a in row:
                rh = a / cw
                rects.append((x, yy, cw, rh))
                yy += rh
            return x + cw, y, w - cw, h
        rh = s / w
        xx = x
        for a in row:
            cw = a / rh
            rects.append((xx, y, cw, rh))
            xx += cw
        return x, y + rh, w, h - rh

    row: list[float] = []
    i = 0
    while i < len(areas):
        side = min(w, h)
        a = areas[i]
        if not row or worst(row + [a], side) <= worst(row, side):
            row.append(a)
            i += 1
        else:
            x, y, w, h = layout(row, x, y, w, h)
            row = []
    if row:
        layout(row, x, y, w, h)
    return rects


def heat_color(p: float | None, cap: float = 3.0) -> str:
    if p is None:
        return "#e6e0d3"
    t = max(-1.0, min(1.0, p / cap))
    base = (238, 233, 222)
    tgt = (47, 125, 85) if t > 0 else (184, 69, 58)
    k = abs(t) ** 0.8
    c = tuple(round(base[j] + (tgt[j] - base[j]) * k) for j in range(3))
    return "#%02x%02x%02x" % c


# --------------------------------------------------------------------------
# Line icons (outline style, like the reel)
# --------------------------------------------------------------------------
ICONS = {
    "radar": """<svg viewBox="0 0 220 220" width="200" height="200" fill="none" stroke="#141414" stroke-width="3" stroke-linejoin="round">
<circle cx="110" cy="110" r="104" stroke="#d8693b" stroke-width="2.5"/>
<path d="M40 150 L110 185 L180 150 L110 115 Z" fill="#fbf8f1"/><path d="M40 150 v10 L110 195 v-10 M180 150 v10 L110 195"/>
<ellipse cx="110" cy="150" rx="26" ry="13"/><path d="M84 150 v-12 M136 150 v-12"/><ellipse cx="110" cy="138" rx="26" ry="13" fill="#fbf8f1"/>
<path d="M78 128 L70 70 L86 66 L96 124 M142 128 L150 70 L134 66 L124 124"/><circle cx="78" cy="78" r="4"/><circle cx="142" cy="78" r="4"/>
<ellipse cx="110" cy="82" rx="46" ry="40" transform="rotate(-20 110 82)" fill="#fbf8f1"/>
<ellipse cx="110" cy="82" rx="30" ry="26" transform="rotate(-20 110 82)" stroke="#9b958a" stroke-width="2"/>
<path d="M110 82 L152 64 M110 82 L76 58 M110 82 L104 122" stroke-width="2"/><circle cx="110" cy="82" r="7" fill="#fbf8f1"/></svg>""",
    "clock": """<svg viewBox="0 0 220 220" width="180" height="180" fill="none" stroke="#141414" stroke-width="3">
<circle cx="110" cy="110" r="104" stroke="#d8693b" stroke-width="2.5"/><circle cx="110" cy="110" r="62" fill="#fbf8f1"/>
<path d="M110 66 v44 l30 18" stroke-linecap="round"/><path d="M60 64 l-14 -10 M160 64 l14 -10"/><circle cx="110" cy="110" r="5" fill="#141414"/></svg>""",
}


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def out_dir() -> str:
    """claude.ai sandbox -> /mnt/user-data/outputs, otherwise ./trader-reports."""
    for d in (os.environ.get("TRADER_OUT"), "/mnt/user-data/outputs"):
        if d and os.path.isdir(d):
            return d
    d = os.path.join(os.getcwd(), "trader-reports")
    os.makedirs(d, exist_ok=True)
    return d


def save(html_text: str, name: str, out: str | None = None) -> str:
    path = out or os.path.join(out_dir(), f"{name}-{now_ny():%Y%m%d-%H%M}.html")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_text)
    print(f"REPORT: {os.path.abspath(path)}")
    return path


def save_json(obj, path: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=str)
    print(f"JSON: {os.path.abspath(path)}")
    return path


def die(msg: str, code: int = 2):
    import sys
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


# --------------------------------------------------------------------------
# Yahoo predefined screeners + built-in core list (used when Nasdaq refuses)
# --------------------------------------------------------------------------
SECTORS_HE = {
    "Technology": "טכנולוגיה", "Communication": "תקשורת", "Consumer Discretionary": "צריכה מחזורית",
    "Consumer Staples": "צריכה בסיסית", "Health Care": "בריאות", "Financials": "פיננסים", "Energy": "אנרגיה",
    "Industrials": "תעשייה", "Materials": "חומרי גלם", "Utilities": "תשתיות", "Real Estate": "נדל\"ן", "Other": "אחר",
}
CORE = {
    "Technology": "AAPL MSFT NVDA AVGO ORCL CRM ADBE AMD INTC CSCO QCOM TXN IBM NOW INTU AMAT MU LRCX KLAC ADI MRVL "
                  "PANW CRWD SNPS CDNS ANET FTNT PLTR SNOW DDOG NET MDB ZS SHOP DELL HPQ HPE SMCI ARM TSM ASML "
                  "MSTR IONQ SOUN RGTI APP APH GLW WDC STX SNDK ADSK WDAY TEAM ACN",
    "Communication": "GOOGL META NFLX DIS CMCSA T VZ TMUS CHTR EA TTWO SPOT RBLX PINS SNAP TTD",
    "Consumer Discretionary": "AMZN TSLA HD MCD NKE SBUX LOW TJX BKNG CMG ORLY AZO ROST MAR HLT GM F LULU DECK "
                              "RIVN LCID DKNG ETSY EBAY UBER ABNB CVNA ROKU SE RCL CCL NCLH PDD BABA JD MELI",
    "Consumer Staples": "WMT COST PG KO PEP PM MO MDLZ CL KMB GIS KHC TGT DG DLTR KR STZ MNST",
    "Health Care": "UNH JNJ LLY ABBV MRK PFE TMO ABT DHR BMY AMGN GILD VRTX REGN ISRG MDT SYK BSX CVS CI HUM "
                   "ELV ZTS MRNA HIMS NVO AZN",
    "Financials": "JPM BAC WFC C GS MS SCHW BLK AXP V MA PYPL COF USB PNC SPGI MCO ICE CME CB PGR MET AIG BRK-B "
                  "COIN HOOD SOFI AFRM UPST KKR BX APO HDB IBN ITUB SAN MFG",
    "Energy": "XOM CVX COP SLB EOG OXY PSX MPC VLO HAL DVN WMB KMI BP SHEL PBR PBR-A CNQ ENB",
    "Industrials": "CAT DE BA GE HON UPS FDX LMT RTX NOC GD UNP CSX MMM ETN EMR ITW WM DAL UAL AAL LUV GEV PWR VRT",
    "Materials": "LIN APD SHW FCX NEM DOW NUE AEM",
    "Utilities": "NEE DUK SO D AEP EXC SRE CEG VST",
    "Real Estate": "PLD AMT EQIX CCI SPG O PSA",
}
SECTOR_OF = {s: sec for sec, syms in CORE.items() for s in syms.split()}
SECTOR_ETFS = {"XLK": "Technology", "XLC": "Communication", "XLY": "Consumer Discretionary",
               "XLP": "Consumer Staples", "XLV": "Health Care", "XLF": "Financials", "XLE": "Energy",
               "XLI": "Industrials", "XLB": "Materials", "XLU": "Utilities", "XLRE": "Real Estate"}
YAHOO_SCREENS = ["most_actives", "day_gainers", "day_losers", "small_cap_gainers", "aggressive_small_caps",
                 "undervalued_growth_stocks", "growth_technology_stocks", "undervalued_large_caps",
                 "most_shorted_stocks"]


def yahoo_screener(scr_id: str, count: int = 250, start: int = 0) -> list[dict]:
    q = urllib.parse.urlencode({"scrIds": scr_id, "count": count, "start": start})
    d = http_json(f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?{q}", retries=1)
    res = ((d.get("finance") or {}).get("result") or [{}])[0]
    out = []
    for x in res.get("quotes") or []:
        sym = (x.get("symbol") or "").upper()
        if not sym or x.get("quoteType", "EQUITY") != "EQUITY" or "." in sym:
            continue
        out.append({"symbol": sym, "name": x.get("shortName") or x.get("longName") or "",
                    "price": x.get("regularMarketPrice"), "pct": x.get("regularMarketChangePercent"),
                    "volume": x.get("regularMarketVolume") or 0, "avgvol": x.get("averageDailyVolume3Month") or 0,
                    "mcap": x.get("marketCap") or 0, "hi52": x.get("fiftyTwoWeekHigh"),
                    "sector": SECTOR_OF.get(sym, "Other"), "industry": ""})
    return out


def market_universe(pages: int = 2) -> tuple[list[dict], str]:
    """Return (rows, source). Tries Nasdaq's full US list first, then Yahoo screeners + core list."""
    try:
        rows = nasdaq_universe()
        if len(rows) > 1000:
            return rows, "nasdaq"
    except Exception:  # noqa: BLE001
        pass
    seen: dict = {}
    jobs = [(sid, p * 250) for sid in YAHOO_SCREENS for p in range(pages)]

    def one(job):
        try:
            return yahoo_screener(job[0], 250, job[1])
        except Exception:  # noqa: BLE001
            return []
    with ThreadPoolExecutor(max_workers=3) as ex:
        for rows in ex.map(one, jobs):
            for r in rows:
                seen.setdefault(r["symbol"], r)
    for sym, sec in SECTOR_OF.items():
        seen.setdefault(sym, {"symbol": sym, "name": "", "price": None, "pct": None, "volume": 0, "avgvol": 0,
                              "mcap": 0, "hi52": None, "sector": sec, "industry": ""})
    return list(seen.values()), "yahoo"
