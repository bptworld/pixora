from datetime import datetime, timedelta, timezone
from io import BytesIO
import email.utils
import html
import re
import urllib.request
import xml.etree.ElementTree as ET

from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "rss_headlines"
CARD_NAME = "RSS Headlines"
CARD_DETAIL = "Scrolling RSS headline"
CARD_OPTIONS = [
    {"key": "feedUrl", "label": "Feed URL", "type": "text", "default": "https://hnrss.org/frontpage", "maxlength": 180},
    {"key": "sourceLabel", "label": "Source Label", "type": "text", "default": "NEWS", "maxlength": 10},
]

_CACHE = {}


def _clean(text):
    text = html.unescape(re.sub(r"<[^>]+>", "", str(text or "")))
    return " ".join(text.split())


def _item_date(item):
    for key in ("pubDate", "updated", "published"):
        value = item.findtext(key)
        if value:
            try:
                return email.utils.parsedate_to_datetime(value)
            except Exception:
                pass
    return datetime.min.replace(tzinfo=timezone.utc)


def _fetch(feed_url):
    now = datetime.now(timezone.utc)
    cached = _CACHE.get(feed_url)
    if cached and cached["expires"] > now:
        return cached["items"]
    req = urllib.request.Request(feed_url, headers={"User-Agent": "Pixora/0.1"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        root = ET.fromstring(resp.read())
    items = []
    for item in root.findall(".//item") or root.findall(".//{*}entry"):
        title = item.findtext("title") or item.findtext("{*}title") or ""
        if title:
            items.append({"title": _clean(title), "date": _item_date(item)})
    items.sort(key=lambda row: row["date"], reverse=True)
    _CACHE[feed_url] = {"items": items[:10], "expires": now + timedelta(minutes=10)}
    return items[:10]


def _render_scroll(label, headline, width=64):
    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    text = headline.upper()
    text_w = dummy.textbbox((0, 0), text, font=font)[2]
    frames = []
    for step in range(0, width + text_w + 16, 2):
        image = Image.new("RGB", (width, 32), (0, 5, 12))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width - 1, 6), fill=(5, 18, 25))
        draw_sharp_text(image, (1, -3), label[:20 if width == 128 else 10].upper(), (80, 220, 170), bold)
        draw_sharp_text(image, (width - step, 14), text, (245, 250, 255), font)
        frames.append(image)
    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=35, loop=0, lossless=True, quality=100)
    return out.getvalue()


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    feed_url = (opts.get("feedUrl") or "").strip()
    label = (opts.get("sourceLabel") or "NEWS").strip() or "NEWS"
    if not feed_url:
        return render_text_webp("SET RSS", (100, 180, 255))
    try:
        items = _fetch(feed_url)
    except Exception:
        return render_text_webp("RSS ERR", (238, 80, 80))
    if not items:
        return render_text_webp("NO NEWS", (160, 170, 180))
    return _render_scroll(label, items[0]["title"], width)

