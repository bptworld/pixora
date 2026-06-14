from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import urllib.parse
import urllib.request

from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "currency_rates"
CARD_NAME = "Currency Rates"
CARD_DETAIL = "FX pairs and daily moves"
CARD_OPTIONS = [
    {"key": "pairs", "label": "Pairs", "type": "text", "default": "EURUSD=X,USDJPY=X,GBPUSD=X", "maxlength": 64},
]
CARD_RULE_FIELDS = [
    {"id": "first_rate", "label": "First Rate"},
    {"id": "first_change_pct", "label": "First Change %"},
    {"id": "first_pair", "label": "First Pair"},
]

_CACHE = {}


def _pairs(value):
    pairs = []
    for raw in str(value or "").upper().replace(";", ",").split(","):
        pair = raw.strip()
        if not pair:
            continue
        if "=" not in pair and len(pair) == 6:
            pair += "=X"
        if pair not in pairs:
            pairs.append(pair)
    return pairs[:3] or ["EURUSD=X", "USDJPY=X", "GBPUSD=X"]


def _fetch_one(symbol):
    encoded = urllib.parse.quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?interval=1d&range=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    meta = raw["chart"]["result"][0]["meta"]
    price = float(meta.get("regularMarketPrice") or 0)
    prev = float(meta.get("previousClose") or meta.get("chartPreviousClose") or price or 0)
    pct = ((price - prev) / prev * 100) if prev else 0
    return {"symbol": meta.get("symbol", symbol).upper(), "price": price, "pct": pct}


def _fetch(symbols):
    key = ",".join(symbols)
    now = datetime.now(timezone.utc)
    cached = _CACHE.get(key)
    if cached and cached["expires"] > now:
        return cached["data"]
    data = [_fetch_one(symbol) for symbol in symbols]
    _CACHE[key] = {"data": data, "expires": now + timedelta(seconds=60)}
    return data


def _label(symbol):
    return str(symbol or "").upper().replace("=X", "")[:6]


def _rate(value):
    value = float(value or 0)
    if value >= 100:
        return f"{value:.1f}"
    if value >= 10:
        return f"{value:.2f}"
    return f"{value:.4f}"


def _text_width(draw, text, font):
    return draw.textbbox((0, 0), str(text), font=font)[2]


def rule_value(options=None, field=""):
    quotes = _fetch(_pairs((options or {}).get("pairs")))
    first = quotes[0] if quotes else {}
    key = str(field or "").strip()
    if key == "first_rate":
        return first.get("price", "")
    if key == "first_change_pct":
        return first.get("pct", "")
    if key == "first_pair":
        return first.get("symbol", "")
    return ""


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    is_wide = opts.get("_target") == "matrixportal-s3-128x32"
    width = 128 if is_wide else 64
    try:
        quotes = _fetch(_pairs(opts.get("pairs")))
    except Exception:
        return render_text_webp("FX ERR", (238, 80, 80), width=width)

    image = Image.new("RGB", (width, 32), (0, 4, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/Silkscreen-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    draw.rectangle((0, 0, width - 1, 8), fill=(5, 18, 28))
    title = "CURRENCY RATES" if is_wide else "FX RATES"
    tw = _text_width(draw, title, bold)
    draw_sharp_text(image, ((width - tw) // 2, -3), title, (120, 220, 255), bold)
    y = 8
    for q in quotes[:3]:
        pct = float(q.get("pct") or 0)
        color = (80, 220, 120) if pct >= 0 else (238, 80, 80)
        label = _label(q.get("symbol"))
        rate = _rate(q.get("price"))
        draw_sharp_text(image, (2, y - 1), label[:6 if is_wide else 3], (235, 245, 255), bold)
        rw = _text_width(draw, rate, font)
        draw_sharp_text(image, ((width - rw) // 2, y - 1), rate, (235, 245, 255), font)
        pct_s = f"{pct:+.1f}%"
        pw = _text_width(draw, pct_s, font)
        draw_sharp_text(image, (width - pw - 2, y - 1), pct_s, color, font)
        y += 8

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
