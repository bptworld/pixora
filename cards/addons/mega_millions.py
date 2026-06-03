from datetime import datetime, timedelta, timezone
from html import unescape
from io import BytesIO
import re
import urllib.request

from card_utils import draw_pixora_bold_number, draw_sharp_text, format_short_date, pixora_bold_number_size, render_text_webp

CARD_ID = "mega_millions"
CARD_NAME = "Mega Millions"
CARD_DETAIL = "Latest Mega Millions draw"
CARD_OPTIONS = []

URL = "https://www.lottery.net/mega-millions/numbers"
CACHE = {}
MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _fetch_html(url, seconds=21600):
    now = datetime.now(timezone.utc)
    if CACHE.get("expires", now) > now and CACHE.get("html"):
        return CACHE["html"]
    request = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1"})
    with urllib.request.urlopen(request, timeout=10) as response:
        html = response.read().decode("utf-8", errors="ignore")
    CACHE["html"] = html
    CACHE["expires"] = now + timedelta(seconds=seconds)
    return html


def _clean_html(text):
    text = re.sub(r"<sup>.*?</sup>", "", text, flags=re.I | re.S)
    text = re.sub(r"<.*?>", " ", text, flags=re.S)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _parse_draw_date(text):
    match = re.search(r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})\b", text or "", re.I)
    if not match:
        return None
    month = MONTHS.get(match.group(1)[:3].lower())
    if not month:
        return None
    try:
        return datetime(int(match.group(3)), month, int(match.group(2))).date()
    except Exception:
        return None


def _next_draw_text(date_text):
    draw_date = _parse_draw_date(date_text)
    if not draw_date:
        return ""
    next_date = draw_date + timedelta(days=1)
    while next_date.weekday() not in (1, 4):
        next_date += timedelta(days=1)
    return f"Next Draw: {format_short_date(next_date)}"


def _latest():
    html = _fetch_html(URL)
    block_match = re.search(r'<div class="[^"]*latestResults[^"]*".*?</div>\s*</div>\s*</div>', html, re.I | re.S)
    block = block_match.group(0) if block_match else html
    date_match = re.search(r'<div class="latest"[^>]*>(.*?)</div>', block, re.I | re.S)
    date_text = _clean_html(date_match.group(1)) if date_match else "LATEST"
    numbers = re.findall(r'<li class="ball">(\d+)</li>', block, re.I)
    special_match = re.search(r'<li class="mega-ball">(\d+)</li>', block, re.I)
    jackpot_match = re.search(r'Jackpot for this draw:\s*<br>\s*<span>(.*?)</span>', block, re.I | re.S)
    if len(numbers) < 5 or not special_match:
        raise ValueError("Mega Millions numbers not found")
    return {
        "date": date_text,
        "numbers": numbers[:5],
        "special": special_match.group(1),
        "jackpot": _clean_html(jackpot_match.group(1)) if jackpot_match else "",
        "next": _next_draw_text(date_text),
    }


def _center(image, text, y, color, font, x1=0, x2=63):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    width = draw.textbbox((0, 0), str(text), font=font)[2]
    draw_sharp_text(image, (x1 + ((x2 - x1 + 1) - width) // 2, y), str(text), color, font)


def _center_numbers(image, text, y, color, x1=0, x2=63):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    width = pixora_bold_number_size(text)[0]
    draw_pixora_bold_number(draw, (x1 + ((x2 - x1 + 1) - width) // 2, y), text, color)


def _draw(data, width=64):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (width, 32), (0, 4, 10))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    draw.rectangle((0, 0, width - 1, 8), fill=(23, 9, 38))
    _center(image, "MEGA MILLIONS" if width == 128 else "MEGA MILL", -3, (255, 215, 70), bold, x2=width - 1)
    nums = data["numbers"]
    if width == 128:
        _center_numbers(image, " ".join(nums[:5]) + f" +{data['special']}", 9, (245, 250, 255), x2=width - 1)
        _center(image, data.get("next") or "", 15, (120, 230, 255), font, x2=width - 1)
        bottom = (data.get("jackpot") or data.get("date") or "")[:26].upper()
        _center(image, bottom, 23, (175, 150, 205), font, x2=width - 1)
    else:
        _center_numbers(image, " ".join(nums[:3]), 8, (245, 250, 255))
        _center_numbers(image, f"{nums[3]} {nums[4]} +{data['special']}", 16, (255, 220, 80))
        bottom = (data.get("jackpot") or data.get("date") or "")[:12].upper()
        _center(image, bottom, 23, (175, 150, 205), font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def render(options=None):
    try:
        opts = options or {}
        width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
        return _draw(_latest(), width)
    except Exception:
        return render_text_webp("MEGA ERR", (255, 210, 80))
