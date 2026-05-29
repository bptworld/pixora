from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import math
import re
import urllib.parse
import urllib.request

from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "stocks"
CARD_NAME = "Stock Ticker"
CARD_DETAIL = "Scrolling stocks and crypto"
CARD_OPTIONS = [
    {
        "key": "symbols",
        "label": "Symbols",
        "type": "text",
        "default": "AAPL, MSFT, BTC-USD, ETH-USD",
        "maxlength": 96,
    },
    {
        "key": "scrolls",
        "label": "Scrolls",
        "type": "number",
        "default": "1",
        "inputmode": "numeric",
    },
]

_CACHE = {}
_LOGO_CACHE = {}
_CRYPTO_ALIASES = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "DOGE": "DOGE-USD",
    "SOL": "SOL-USD",
    "XRP": "XRP-USD",
    "ADA": "ADA-USD",
    "LTC": "LTC-USD",
}
_LOGO_DOMAINS = {
    "AAPL": "apple.com",
    "MSFT": "microsoft.com",
    "GOOG": "google.com",
    "GOOGL": "google.com",
    "AMZN": "amazon.com",
    "META": "meta.com",
    "TSLA": "tesla.com",
    "NVDA": "nvidia.com",
    "AMD": "amd.com",
    "INTC": "intel.com",
    "NFLX": "netflix.com",
    "DIS": "disney.com",
    "WMT": "walmart.com",
    "TGT": "target.com",
    "COST": "costco.com",
    "HD": "homedepot.com",
    "LOW": "lowes.com",
    "SBUX": "starbucks.com",
    "MCD": "mcdonalds.com",
    "KO": "coca-cola.com",
    "PEP": "pepsico.com",
    "NKE": "nike.com",
    "V": "visa.com",
    "MA": "mastercard.com",
    "JPM": "jpmorganchase.com",
    "BAC": "bankofamerica.com",
    "XOM": "exxonmobil.com",
    "CVX": "chevron.com",
    "F": "ford.com",
    "GM": "gm.com",
    "BA": "boeing.com",
}


def _symbols(value):
    text = str(value or "").upper()
    raw = re.split(r"[\s,;|]+", text)
    symbols = []
    for item in raw:
        item = item.strip()
        if not item:
            continue
        item = _CRYPTO_ALIASES.get(item, item)
        if re.fullmatch(r"[\^A-Z0-9.\-=]{1,16}", item) and item not in symbols:
            symbols.append(item)
    return sorted(symbols[:12]) or ["AAPL"]


def _fetch_quote(symbol):
    now = datetime.now(timezone.utc)
    cached = _CACHE.get(symbol)
    if cached and cached["expires"] > now:
        return cached["data"]

    encoded = urllib.parse.quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?interval=1d&range=1d"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    result = (raw.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise ValueError("No quote")
    meta = result.get("meta") or {}
    price = float(meta.get("regularMarketPrice") or 0)
    prev = float(meta.get("previousClose") or meta.get("chartPreviousClose") or price or 0)
    change = price - prev
    change_pct = (change / prev) if prev else 0
    quote = {
        "symbol": meta.get("symbol", symbol),
        "price": price,
        "change": change,
        "change_pct": change_pct,
        "state": meta.get("marketState", ""),
    }
    _CACHE[symbol] = {"data": quote, "expires": now + timedelta(seconds=60)}
    return quote


def _display_symbol(symbol):
    symbol = str(symbol or "").upper()
    if symbol.endswith("-USD"):
        return symbol[:-4]
    return symbol[:8]


def _base_symbol(symbol):
    base = str(symbol or "").upper()
    if base.endswith("-USD"):
        base = base[:-4]
    return base.split(".")[0].split("-")[0]


def _fmt_price(value):
    try:
        price = float(value)
    except Exception:
        return "--"
    if price >= 100000:
        return f"{price / 1000:.0f}K"
    if price >= 10000:
        return f"{price / 1000:.1f}K"
    if price >= 1000:
        return f"{price:,.0f}"
    if price >= 100:
        return f"{price:.1f}"
    if price >= 1:
        return f"{price:.2f}"
    return f"{price:.4f}"


def _fmt_pct(value):
    try:
        pct = float(value) * 100
    except Exception:
        return "--"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def _quote_item(symbol):
    try:
        q = _fetch_quote(symbol)
        q["display"] = _display_symbol(q["symbol"])
        q["ok"] = True
        return q
    except Exception:
        return {
            "symbol": symbol,
            "display": _display_symbol(symbol),
            "price": None,
            "change": 0,
            "change_pct": 0,
            "ok": False,
        }


def _text_width(draw, text, font):
    if not text:
        return 0
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _draw_icon(draw, x, y, symbol, up):
    base = _base_symbol(symbol)
    if base == "ETH":
        draw.polygon([(x + 8, y), (x + 15, y + 10), (x + 8, y + 14), (x + 1, y + 10)], fill=(210, 220, 235))
        draw.polygon([(x + 8, y + 2), (x + 8, y + 13), (x + 2, y + 10)], fill=(145, 155, 175))
        draw.polygon([(x + 8, y + 16), (x + 15, y + 12), (x + 8, y + 22), (x + 1, y + 12)], fill=(175, 185, 205))
        draw.polygon([(x + 8, y + 17), (x + 8, y + 22), (x + 2, y + 13)], fill=(105, 115, 135))
    elif base == "BTC":
        draw.ellipse((x + 1, y + 2, x + 15, y + 16), fill=(245, 165, 40), outline=(255, 220, 90))
        draw.rectangle((x + 6, y + 5, x + 10, y + 13), fill=(255, 255, 255))
        draw.point((x + 11, y + 6), fill=(245, 165, 40))
        draw.point((x + 11, y + 10), fill=(245, 165, 40))
    else:
        fill = (26, 52, 72)
        edge = (100, 190, 255)
        draw.rectangle((x + 1, y + 3, x + 15, y + 17), fill=fill, outline=edge)
        color = (80, 235, 130) if up else (245, 80, 90)
        if up:
            draw.line((x + 4, y + 13, x + 8, y + 9, x + 12, y + 5), fill=color, width=2)
            draw.point((x + 13, y + 5), fill=color)
        else:
            draw.line((x + 4, y + 5, x + 8, y + 9, x + 12, y + 13), fill=color, width=2)
            draw.point((x + 13, y + 13), fill=color)


def _fetch_company_logo(symbol):
    from PIL import Image, ImageEnhance

    base = _base_symbol(symbol)
    domain = _LOGO_DOMAINS.get(base)
    if not domain:
        return None
    cached = _LOGO_CACHE.get(base)
    now = datetime.now(timezone.utc)
    if cached and cached["expires"] > now:
        return cached["logo"]
    try:
        raw = None
        for url in (
            "https://logo.clearbit.com/" + domain,
            "https://www.google.com/s2/favicons?" + urllib.parse.urlencode({"domain": domain, "sz": "64"}),
        ):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    raw = resp.read()
                if raw:
                    break
            except Exception:
                raw = None
        if not raw:
            raise ValueError("No logo")
        logo = Image.open(BytesIO(raw)).convert("RGBA")
        logo.thumbnail((18, 22), Image.LANCZOS)
        canvas = Image.new("RGBA", (18, 22), (0, 0, 0, 0))
        canvas.alpha_composite(logo, ((18 - logo.width) // 2, (22 - logo.height) // 2))

        # Dark single-color marks disappear on the black matrix. Lift them to white
        # while preserving colored marks when they already have visible color.
        pixels = canvas.getdata()
        visible = [p for p in pixels if p[3] > 20]
        if visible:
            avg = sum((p[0] + p[1] + p[2]) / 3 for p in visible) / len(visible)
            chroma = sum(max(p[:3]) - min(p[:3]) for p in visible) / len(visible)
            if avg < 90 and chroma < 35:
                rgb = Image.new("RGBA", canvas.size, (245, 245, 245, 0))
                rgb.putalpha(canvas.getchannel("A"))
                canvas = rgb
            elif avg < 70:
                rgb = canvas.convert("RGB")
                rgb = ImageEnhance.Brightness(rgb).enhance(2.2)
                canvas = Image.merge("RGBA", (*rgb.split(), canvas.getchannel("A")))
        _LOGO_CACHE[base] = {"logo": canvas, "expires": now + timedelta(hours=12)}
        return canvas
    except Exception:
        _LOGO_CACHE[base] = {"logo": None, "expires": now + timedelta(minutes=10)}
        return None


def _fit_text(draw, text, font, max_width):
    text = str(text or "")
    while text and _text_width(draw, text, font) > max_width:
        text = text[:-1]
    return text


def _panel_width(draw, item, font, bold):
    price = "ERR" if not item.get("ok") else "$" + _fmt_price(item.get("price"))
    symbol_w = _text_width(draw, item.get("display", ""), bold)
    price_w = _text_width(draw, price, bold)
    return max(64, 23 + max(symbol_w, price_w) + 24)


def _draw_quote_panel(image, x, item, font, bold):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    up = item.get("change", 0) >= 0
    main = (90, 235, 125) if up else (245, 80, 90)
    symbol = _fit_text(draw, item.get("display", ""), bold, 38)
    price = "ERR" if not item.get("ok") else "$" + _fmt_price(item.get("price"))
    price = _fit_text(draw, price, bold, 40)
    pct = _fmt_pct(item.get("change_pct", 0)) if item.get("ok") else "NO DATA"
    dollars = _fmt_price(abs(item.get("change", 0))) if item.get("ok") else ""
    arrow = "^" if up else "v"

    logo = _fetch_company_logo(item.get("symbol"))
    if logo:
        image.alpha_composite(logo, (x + 0, 4)) if image.mode == "RGBA" else image.paste(logo, (x + 0, 4), logo)
    else:
        _draw_icon(draw, x + 1, 5, item.get("symbol"), up)
    draw_sharp_text(image, (x + 21, -3), symbol, (235, 245, 255), bold)
    draw_sharp_text(image, (x + 21, 5), price, main, font)
    draw_sharp_text(image, (x + 21, 13), f"{arrow}{pct}", main, font)
    if dollars:
        draw_sharp_text(image, (x + 21, 21), "$" + dollars, (100, 190, 255), font)


def _draw_ticker_frame(x, items, widths, font, bold, panel_width=64):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (panel_width, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    cursor = x
    for item, width in zip(items, widths):
        if cursor < panel_width and cursor + width > -1:
            _draw_quote_panel(image, cursor, item, font, bold)
        cursor += width
    return image


def _render_ticker(symbols, dwell, scrolls=1, panel_width=64):
    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    items = [_quote_item(symbol) for symbol in symbols]
    widths = [_panel_width(measure, item, font, bold) for item in items]
    total_width = sum(widths)
    total = panel_width + total_width + 16
    step = 2
    one_pass_frames = max(20, math.ceil(total / step))
    scrolls = max(1, min(20, int(scrolls or 1)))
    frame_count = one_pass_frames * scrolls
    frame_ms = max(25, min(80, int((max(4, dwell) * 1000) / frame_count)))

    frames = []
    for index in range(frame_count):
        pass_index = index % one_pass_frames
        x = panel_width - pass_index * step
        frames.append(_draw_ticker_frame(x, items, widths, font, bold, panel_width=panel_width))

    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=frame_ms,
        loop=1,
        lossless=True,
        quality=100,
    )
    return out.getvalue()


def render(options=None):
    opts = options or {}
    symbols = _symbols(opts.get("symbols") or opts.get("symbol"))
    dwell = max(4, int(opts.get("_dwell", 30) or 30))
    scrolls = opts.get("scrolls") or 1
    panel_width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    try:
        body = _render_ticker(symbols, dwell, scrolls, panel_width=panel_width)
    except Exception as err:
        return render_text_webp(str(err)[:12] or "QUOTE ERR", (238, 80, 80))
    return {
        "body": body,
        "dwell_secs": 1,
        "_stay": False,
    }

