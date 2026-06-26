from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import urllib.parse
import urllib.request

from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "sector_heat"
CARD_NAME = "Sector Heat"
CARD_DETAIL = "ETF sector daily moves"
CARD_OPTIONS = [
    {"key": "symbols", "label": "Sector ETFs", "type": "text", "default": "XLK,XLF,XLE,XLV,XLY,XLI", "maxlength": 64},
]
CARD_RULE_FIELDS = [
    {"id": "leader_symbol", "label": "Top Sector"},
    {"id": "leader_change_pct", "label": "Top Sector Change %"},
    {"id": "any_down", "label": "Any Sector Down"},
]

_CACHE = {}
_LABELS = {
    "XLK": "TECH",
    "XLF": "FIN",
    "XLE": "ENER",
    "XLV": "HLTH",
    "XLY": "CONS",
    "XLI": "IND",
    "XLP": "STAP",
    "XLU": "UTIL",
    "XLB": "MAT",
    "XLRE": "REAL",
    "XLC": "COMM",
}


def _symbols(value):
    symbols = []
    for raw in str(value or "").upper().replace(";", ",").split(","):
        symbol = raw.strip()
        if symbol and len(symbol) <= 12 and symbol not in symbols:
            symbols.append(symbol)
    return symbols[:6] or ["XLK", "XLF", "XLE"]


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
    return _LABELS.get(str(symbol or "").upper(), str(symbol or "").replace("^", "")[:4].upper())


def _pct(value):
    return f"{float(value):+.1f}%"


def _text_width(draw, text, font):
    return draw.textbbox((0, 0), str(text), font=font)[2]


def _center(image, draw, text, y, color, font, x1, x2):
    w = _text_width(draw, text, font)
    draw_sharp_text(image, (x1 + ((x2 - x1 + 1) - w) // 2, y), text, color, font)


def rule_value(options=None, field=""):
    quotes = _fetch(_symbols((options or {}).get("symbols")))
    leader = max(quotes, key=lambda q: float(q.get("pct") or 0)) if quotes else {}
    key = str(field or "").strip()
    if key == "leader_symbol":
        return leader.get("symbol", "")
    if key == "leader_change_pct":
        return leader.get("pct", "")
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
        return render_text_webp("SECT ERR", (238, 80, 80), width=width)

    image = Image.new("RGB", (width, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/Silkscreen-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    draw.rectangle((0, 0, width - 1, 6), fill=(5, 18, 25))
    _center(image, draw, "SECTOR HEAT" if is_wide else "SECTORS", -3, (100, 190, 255), bold, 0, width - 1)
    rows = quotes[:3]
    y = 8
    for q in rows:
        pct = float(q.get("pct") or 0)
        color = (80, 220, 120) if pct >= 0 else (238, 80, 80)
        label = _label(q.get("symbol"))
        pct_s = _pct(pct)
        draw_sharp_text(image, (2, y - 1), label[:5 if is_wide else 4], (235, 245, 255), bold)
        if is_wide:
            price = f"{float(q.get('price') or 0):.1f}"
            pw = _text_width(draw, price, font)
            draw_sharp_text(image, ((width - pw) // 2, y - 1), price, (235, 245, 255), font)
        w = _text_width(draw, pct_s, font)
        draw_sharp_text(image, (width - w - 2, y - 1), pct_s, color, font)
        y += 8

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
