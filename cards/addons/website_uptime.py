from datetime import datetime, timedelta, timezone
from io import BytesIO
import time
import urllib.request

from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "website_uptime"
CARD_NAME = "Website Uptime"
CARD_DETAIL = "URL up/down monitor"
CARD_OPTIONS = [
    {"key": "url", "label": "URL", "type": "text", "default": "https://github.com", "maxlength": 160},
    {"key": "label", "label": "Label", "type": "text", "default": "SITE", "maxlength": 10},
]
CARD_RULE_FIELDS = [
    {"id": "ok", "label": "Is Up"},
    {"id": "status", "label": "HTTP Status"},
    {"id": "ms", "label": "Response Time ms"},
]

_CACHE = {}


def _check(url):
    now = datetime.now(timezone.utc)
    cached = _CACHE.get(url)
    if cached and cached["expires"] > now:
        return cached["data"]
    start = time.perf_counter()
    ok = False
    status = 0
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Pixora/0.1"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            status = resp.status
            ok = 200 <= status < 500
    except Exception:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                status = resp.status
                ok = 200 <= status < 500
        except Exception:
            ok = False
    ms = int((time.perf_counter() - start) * 1000)
    data = {"ok": ok, "status": status, "ms": ms}
    _CACHE[url] = {"data": data, "expires": now + timedelta(seconds=60)}
    return data


def rule_value(options=None, field=""):
    url = ((options or {}).get("url") or "").strip()
    if not url:
        return ""
    data = _check(url)
    key = str(field or "ok").strip()
    if key == "ok":
        return "true" if data.get("ok") else "false"
    return data.get(key, "")


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    url = (opts.get("url") or "").strip()
    label = (opts.get("label") or "SITE").strip() or "SITE"
    if not url:
        return render_text_webp("SET URL", (100, 180, 255))
    data = _check(url)
    color = (80, 220, 120) if data["ok"] else (238, 80, 80)
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    image = Image.new("RGB", (width, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 16)
    except Exception:
        font = bold = big = ImageFont.load_default()
    draw.rectangle((0, 0, width - 1, 8), fill=(5, 18, 25))
    draw_sharp_text(image, (1, -3), label[:20 if width == 128 else 10].upper(), (80, 180, 255), bold)
    status = "UP" if data["ok"] else "DOWN"
    sw = draw.textbbox((0, 0), status, font=big)[2]
    draw_sharp_text(image, ((width - sw) // 2, 5), status, color, big)
    ms = f"{data['ms']}ms" if data["ok"] else "NO REPLY"
    mw = draw.textbbox((0, 0), ms, font=font)[2]
    draw_sharp_text(image, ((width - mw) // 2, 22), ms, (150, 170, 185), font)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
