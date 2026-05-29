from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import urllib.request
from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "market_indexes"
CARD_NAME = "Market Indexes"
CARD_DETAIL = "Dow, S&P, Nasdaq"
CARD_OPTIONS = [
    {"key": "indexes", "label": "Indexes", "type": "text", "default": "^DJI,^GSPC,^IXIC", "maxlength": 32},
]

_CACHE = {}


def _glyph_width(font, ch):
    try:
        return max(1, font.getbbox(ch)[2] - font.getbbox(ch)[0])
    except Exception:
        return 6


def _tight_text_width(text, font, spacing=-1):
    chars = list(str(text))
    if not chars:
        return 0
    return sum(_glyph_width(font, ch) for ch in chars) + (spacing * (len(chars) - 1))


def _draw_tight_text(image, xy, text, fill, font, spacing=-1):
    x, y = xy
    chars = list(str(text))
    for index, ch in enumerate(chars):
        draw_sharp_text(image, (x, y), ch, fill, font)
        if index < len(chars) - 1:
            x += max(1, _glyph_width(font, ch) + spacing)


def _draw_grouped_text(image, x, y, groups, gap=1, spacing=-1):
    for text, fill, font in groups:
        _draw_tight_text(image, (x, y), text, fill, font, spacing=spacing)
        x += _tight_text_width(text, font, spacing=spacing) + gap


def _fetch_one(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    meta = raw["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice") or 0
    prev = meta.get("previousClose") or meta.get("chartPreviousClose") or price
    pct = ((price - prev) / prev * 100) if prev else 0
    return {"symbol": meta.get("symbol", symbol), "price": price, "pct": pct}


def _fetch(symbols):
    symbols = [s.strip().upper() for s in symbols if s.strip()][:3]
    key = ",".join(symbols)
    now = datetime.now(timezone.utc)
    cached = _CACHE.get(key)
    if cached and cached["expires"] > now:
        return cached["data"]
    data = [_fetch_one(symbol) for symbol in symbols]
    _CACHE[key] = {"data": data, "expires": now + timedelta(seconds=60)}
    return data


def _label(symbol):
    return {"^DJI": "DOW", "^GSPC": "S&P", "^IXIC": "NAS", "^RUT": "RUT"}.get(symbol, symbol.replace("^", "")[:3])


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    is_wide = opts.get("_target") == "matrixportal-s3-128x32"
    width = 128 if is_wide else 64
    symbols = (opts.get("indexes") or "^DJI,^GSPC,^IXIC").split(",")[:3]
    try:
        quotes = _fetch(symbols)
    except Exception:
        return render_text_webp("MKT ERR", (238, 80, 80))

    if not quotes:
        return render_text_webp("NO DATA", (160, 160, 160))

    image = Image.new("RGB", (width, 32), (0, 5, 15))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    draw.rectangle((0, 0, width - 1, 8), fill=(6, 18, 30))
    if is_wide:
        title_w = _tight_text_width("MARKET INDEXES", bold, spacing=0)
        _draw_tight_text(image, ((width - title_w) // 2, -3), "MARKET INDEXES", (100, 190, 255), bold, spacing=0)
        rows = [9, 17, 25]
        for y, q in zip(rows, quotes[:3]):
            symbol = q.get("symbol", "")
            price = q.get("price") or 0
            pct = q.get("pct") or 0
            color = (80, 220, 120) if pct >= 0 else (238, 80, 80)
            label = _label(symbol)
            price_s = f"{price:.0f}"
            pct_s = f"{pct:+.1f}%"
            _draw_tight_text(image, (2, y), label, (235, 245, 255), bold, spacing=0)
            price_w = _tight_text_width(price_s, font, spacing=0)
            _draw_tight_text(image, ((width - price_w) // 2, y), price_s, (235, 245, 255), font, spacing=0)
            pct_w = _tight_text_width(pct_s, font, spacing=0)
            _draw_tight_text(image, (width - pct_w - 2, y), pct_s, color, font, spacing=0)
        out = BytesIO()
        image.save(out, "WEBP", lossless=True, quality=100)
        return out.getvalue()

    _draw_tight_text(image, (1, -3), "MARKETS", (100, 190, 255), bold, spacing=-1)

    y = 7
    for q in quotes[:3]:
        symbol = q.get("symbol", "")
        price = q.get("price") or 0
        pct = q.get("pct") or 0
        color = (80, 220, 120) if pct >= 0 else (238, 80, 80)
        label = _label(symbol)
        price_s = f"{price:.0f}"
        _draw_grouped_text(
            image,
            1,
            y,
            [
                (label, (235, 245, 255), bold),
                (price_s, (235, 245, 255), font),
            ],
            gap=1,
            spacing=-1,
        )
        pct_s = f"{pct:+.1f}"
        w = _tight_text_width(pct_s, font, spacing=-1)
        _draw_tight_text(image, (63 - w, y), pct_s, color, font, spacing=-1)
        y += 8

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

