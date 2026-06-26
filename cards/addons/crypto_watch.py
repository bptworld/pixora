from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import urllib.request
from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "crypto_watch"
CARD_NAME = "Crypto Watch"
CARD_DETAIL = "BTC, ETH, and more"
CARD_OPTIONS = [
    {"key": "symbols", "label": "Coins", "type": "text", "default": "BTC-USD,ETH-USD,SOL-USD", "maxlength": 40},
]
CARD_RULE_FIELDS = [
    {"id": "first_price", "label": "First Coin Price"},
    {"id": "first_change_pct", "label": "First Coin Change %"},
    {"id": "first_symbol", "label": "First Coin"},
    {"id": "any_down", "label": "Any Coin Down"},
]

_CACHE = {}


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


def _coin(symbol):
    return symbol.replace("-USD", "")[:4]


def _price(value):
    if value >= 1000:
        return f"{value/1000:.1f}K"
    if value >= 1:
        return f"{value:.2f}"
    return f"{value:.4f}"


def rule_value(options=None, field=""):
    symbols = ((options or {}).get("symbols") or "BTC-USD,ETH-USD,SOL-USD").split(",")[:3]
    quotes = _fetch(symbols)
    first = quotes[0] if quotes else {}
    key = str(field or "first_price").strip()
    if key == "first_price":
        return first.get("price", "")
    if key == "first_change_pct":
        return first.get("pct", "")
    if key == "first_symbol":
        return first.get("symbol", "")
    if key == "any_down":
        return "true" if any(float(q.get("pct") or 0) < 0 for q in quotes) else "false"
    return ""


def _text_width(draw, text, font):
    return draw.textbbox((0, 0), str(text), font=font)[2]


def _center_text(image, text, y, color, font, x1, x2):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    text = str(text)
    w = _text_width(draw, text, font)
    draw_sharp_text(image, (x1 + ((x2 - x1 + 1) - w) // 2, y), text, color, font)


def _draw_coin_icon(draw, symbol, x, y):
    coin = _coin(symbol).upper()
    if coin == "BTC":
        draw.ellipse((x, y + 1, x + 7, y + 8), fill=(245, 165, 40), outline=(255, 220, 90))
        draw.rectangle((x + 3, y + 3, x + 5, y + 7), fill=(255, 255, 255))
        draw.point((x + 6, y + 4), fill=(245, 165, 40))
        draw.point((x + 6, y + 6), fill=(245, 165, 40))
    elif coin == "ETH":
        draw.polygon([(x + 4, y), (x + 8, y + 5), (x + 4, y + 8), (x, y + 5)], fill=(220, 230, 240))
        draw.polygon([(x + 4, y + 1), (x + 4, y + 7), (x + 1, y + 5)], fill=(140, 152, 175))
    elif coin == "SOL":
        colors = [(125, 255, 205), (180, 80, 255), (70, 185, 255)]
        for i, color in enumerate(colors):
            yy = y + 1 + i * 3
            draw.polygon([(x + 1, yy), (x + 8, yy), (x + 6, yy + 2), (x, yy + 2)], fill=color)
    else:
        draw.ellipse((x, y + 1, x + 8, y + 9), fill=(18, 42, 60), outline=(100, 190, 255))
        mid = x + 4
        draw.line((mid - 2, y + 6, mid, y + 4, mid + 2, y + 6), fill=(80, 235, 130))


def _render_wide(quotes, font, bold):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (128, 32), (0, 4, 12))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 127, 6), fill=(5, 18, 25))
    _center_text(image, "CRYPTO WATCH", -3, (255, 200, 80), bold, 0, 127)

    y = 8
    for q in quotes[:3]:
        symbol = q.get("symbol", "")
        price = q.get("price") or 0
        pct = q.get("pct") or 0
        color = (80, 220, 120) if pct >= 0 else (238, 80, 80)
        coin = _coin(symbol)
        price_s = "$" + _price(price)
        pct_s = f"{pct:+.1f}%"
        _draw_coin_icon(draw, symbol, 2, y - 1)
        draw_sharp_text(image, (14, y - 2), coin, (245, 250, 255), bold)
        price_w = _text_width(draw, price_s, font)
        draw_sharp_text(image, (64 - price_w // 2, y - 2), price_s, (235, 245, 255), font)
        pct_w = _text_width(draw, pct_s, font)
        draw_sharp_text(image, (127 - pct_w, y - 2), pct_s, color, font)
        y += 8

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    symbols = (opts.get("symbols") or "BTC-USD,ETH-USD,SOL-USD").split(",")[:3]
    try:
        quotes = _fetch(symbols)
    except Exception:
        return render_text_webp("CRYP ERR", (238, 80, 80))

    image = Image.new("RGB", (64, 32), (0, 4, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/Silkscreen-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    if opts.get("_target") == "matrixportal-s3-128x32":
        return _render_wide(quotes, font, bold)

    draw_sharp_text(image, (1, -3), "CRYPTO", (255, 200, 80), bold)
    y = 7
    for q in quotes[:3]:
        symbol = q.get("symbol", "")
        price = q.get("price") or 0
        draw_sharp_text(image, (1, y), _coin(symbol), (245, 250, 255), bold)
        price_s = "$" + _price(price)
        w = draw.textbbox((0, 0), price_s, font=font)[2]
        draw_sharp_text(image, (63 - w, y), price_s, (235, 245, 255), font)
        y += 8

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
