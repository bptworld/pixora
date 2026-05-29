from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import urllib.request
from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "portfolio_pulse"
CARD_NAME = "Portfolio Pulse"
CARD_DETAIL = "Value and daily gain"
CARD_OPTIONS = [
    {"key": "holdings", "label": "Holdings", "type": "text", "default": "AAPL:1,MSFT:1", "maxlength": 64},
]

_CACHE = {}


def _parse(holdings):
    items = []
    for part in str(holdings or "").split(","):
        if ":" not in part:
            continue
        sym, qty = part.split(":", 1)
        try:
            items.append((sym.strip().upper(), float(qty.strip())))
        except Exception:
            pass
    return items[:6]


def _fetch_one(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    meta = raw["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice") or 0
    prev = meta.get("previousClose") or meta.get("chartPreviousClose") or price
    return {"symbol": meta.get("symbol", symbol).upper(), "price": price, "prev": prev}


def _fetch(symbols):
    symbols = [s.upper() for s in symbols]
    key = ",".join(symbols)
    now = datetime.now(timezone.utc)
    cached = _CACHE.get(key)
    if cached and cached["expires"] > now:
        return cached["data"]
    by_symbol = {}
    for symbol in symbols:
        q = _fetch_one(symbol)
        by_symbol[q["symbol"]] = q
    _CACHE[key] = {"data": by_symbol, "expires": now + timedelta(seconds=60)}
    return by_symbol


def _money(value):
    if abs(value) >= 1000000:
        return f"${value/1000000:.1f}M"
    if abs(value) >= 1000:
        return f"${value/1000:.1f}K"
    return f"${value:.0f}"


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    is_wide = opts.get("_target") == "matrixportal-s3-128x32"
    width = 128 if is_wide else 64
    holdings = _parse(opts.get("holdings") or "AAPL:1,MSFT:1")
    if not holdings:
        return render_text_webp("SET PORT", (100, 180, 255))
    try:
        quotes = _fetch([sym for sym, _ in holdings])
    except Exception:
        return render_text_webp("PORT ERR", (238, 80, 80))

    total = 0.0
    change = 0.0
    for sym, qty in holdings:
        q = quotes.get(sym)
        if not q:
            continue
        price = q.get("price") or 0
        prev = q.get("prev") or price
        total += price * qty
        change += (price - prev) * qty

    if total <= 0:
        return render_text_webp("NO DATA", (160, 160, 160))

    pct = change / (total - change) if total != change else 0
    up = change >= 0
    color = (80, 220, 120) if up else (238, 80, 80)

    image = Image.new("RGB", (width, 32), (0, 5, 15))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("Silkscreen-Regular.ttf", 16)
    except Exception:
        font = bold = big = ImageFont.load_default()

    if is_wide:
        draw.rectangle((0, 0, width - 1, 8), fill=(6, 18, 30))
        title = "PORTFOLIO PULSE"
        tw = draw.textbbox((0, 0), title, font=bold)[2]
        draw_sharp_text(image, ((width - tw) // 2, -3), title, (100, 190, 255), bold)
    else:
        draw_sharp_text(image, (1, -3), "PORTFOLIO", (100, 190, 255), bold)

    val = _money(total)
    vw = draw.textbbox((0, 0), val, font=big)[2]
    ch = f"{'+' if up else ''}{_money(change)}"
    pct_s = f"{pct*100:+.1f}%"
    if is_wide:
        vb = draw.textbbox((0, 0), val, font=big)
        pb = draw.textbbox((0, 0), pct_s, font=font)
        val_y = 8 + (24 - (vb[3] - vb[1])) // 2 - 8
        side_y = 8 + (24 - (pb[3] - pb[1])) // 2 - 3
    else:
        val_y = 3
        side_y = 22
    draw_sharp_text(image, ((width - vw) // 2, val_y), val, (235, 245, 255), big)
    draw_sharp_text(image, (1 if not is_wide else 4, side_y), ch[:8 if not is_wide else 12], color, font)
    pw = draw.textbbox((0, 0), pct_s, font=font)[2]
    draw_sharp_text(image, (width - 1 - pw if not is_wide else width - 4 - pw, side_y), pct_s, color, font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

