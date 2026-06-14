from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import urllib.parse
import urllib.request

from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "commodities_watch"
CARD_NAME = "Commodities Watch"
CARD_DETAIL = "Gold, oil, and metals"
CARD_OPTIONS = [
    {"key": "symbols", "label": "Symbols", "type": "text", "default": "GC=F,CL=F,SI=F", "maxlength": 64},
]
CARD_RULE_FIELDS = [
    {"id": "first_price", "label": "First Price"},
    {"id": "first_change_pct", "label": "First Change %"},
    {"id": "any_down", "label": "Any Commodity Down"},
]

_CACHE = {}
_LABELS = {
    "GC=F": "GOLD",
    "SI=F": "SILV",
    "CL=F": "OIL",
    "BZ=F": "BRENT",
    "NG=F": "GAS",
    "HG=F": "COPR",
    "PL=F": "PLAT",
}


def _symbols(value):
    symbols = []
    for raw in str(value or "").upper().replace(";", ",").split(","):
        symbol = raw.strip()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols[:3] or ["GC=F", "CL=F", "SI=F"]


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
    return _LABELS.get(str(symbol or "").upper(), str(symbol or "").replace("=F", "")[:4])


def _price(value):
    value = float(value or 0)
    if value >= 1000:
        return f"{value:.0f}"
    if value >= 100:
        return f"{value:.1f}"
    return f"{value:.2f}"


def _text_width(draw, text, font):
    return draw.textbbox((0, 0), str(text), font=font)[2]


def rule_value(options=None, field=""):
    quotes = _fetch(_symbols((options or {}).get("symbols")))
    first = quotes[0] if quotes else {}
    key = str(field or "").strip()
    if key == "first_price":
        return first.get("price", "")
    if key == "first_change_pct":
        return first.get("pct", "")
    if key == "any_down":
        return "true" if any(float(q.get("pct") or 0) < 0 for q in quotes) else "false"
    return ""


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    is_wide = opts.get("_target") == "matrixportal-s3-128x32"
    width = 128 if is_wide else 64
    try:
        quotes = _fetch(_symbols(opts.get("symbols")))
    except Exception:
        return render_text_webp("CMDTY ERR", (238, 80, 80), width=width)

    image = Image.new("RGB", (width, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/Silkscreen-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    draw.rectangle((0, 0, width - 1, 8), fill=(25, 18, 5))
    title = "COMMODITIES" if is_wide else "CMDTY"
    tw = _text_width(draw, title, bold)
    draw_sharp_text(image, ((width - tw) // 2, -3), title, (255, 205, 80), bold)
    y = 8
    for q in quotes[:3]:
        pct = float(q.get("pct") or 0)
        color = (80, 220, 120) if pct >= 0 else (238, 80, 80)
        label = _label(q.get("symbol"))
        price = _price(q.get("price"))
        draw_sharp_text(image, (2, y - 1), label[:5 if is_wide else 4], (245, 250, 255), bold)
        pw = _text_width(draw, price, font)
        draw_sharp_text(image, ((width - pw) // 2, y - 1), price, (235, 245, 255), font)
        pct_s = f"{pct:+.1f}%"
        cw = _text_width(draw, pct_s, font)
        draw_sharp_text(image, (width - cw - 2, y - 1), pct_s, color, font)
        y += 8

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
