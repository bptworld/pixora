from datetime import datetime, timedelta, timezone
from io import BytesIO
import socket
import time

from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "ping_monitor"
CARD_NAME = "Ping Monitor"
CARD_DETAIL = "TCP latency monitor"
CARD_OPTIONS = [
    {"key": "host", "label": "Host", "type": "text", "default": "1.1.1.1", "maxlength": 80},
    {"key": "port", "label": "Port", "type": "number", "default": "443", "min": 1, "max": 65535},
    {"key": "label", "label": "Label", "type": "text", "default": "PING", "maxlength": 10},
]

_CACHE = {}


def _check(host, port):
    key = f"{host}:{port}"
    now = datetime.now(timezone.utc)
    cached = _CACHE.get(key)
    if cached and cached["expires"] > now:
        return cached["data"]
    start = time.perf_counter()
    ok = False
    try:
        with socket.create_connection((host, int(port)), timeout=4):
            ok = True
    except Exception:
        ok = False
    ms = int((time.perf_counter() - start) * 1000)
    data = {"ok": ok, "ms": ms}
    _CACHE[key] = {"data": data, "expires": now + timedelta(seconds=30)}
    return data


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    host = (opts.get("host") or "").strip()
    port = opts.get("port") or "443"
    label = (opts.get("label") or "PING").strip() or "PING"
    if not host:
        return render_text_webp("SET HOST", (100, 180, 255))
    data = _check(host, port)
    color = (80, 220, 120) if data["ok"] else (238, 80, 80)
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    image = Image.new("RGB", (width, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("PixelifySans-Bold.ttf", 16)
    except Exception:
        font = bold = big = ImageFont.load_default()
    draw.rectangle((0, 0, width - 1, 8), fill=(5, 18, 25))
    draw_sharp_text(image, (1, -3), label[:20 if width == 128 else 10].upper(), (80, 220, 170), bold)
    text = f"{data['ms']}ms" if data["ok"] else "FAIL"
    tw = draw.textbbox((0, 0), text, font=big)[2]
    draw_sharp_text(image, ((width - tw) // 2, 5), text, color, big if tw <= width - 2 else bold)
    host_text = host[:26 if width == 128 else 12].upper()
    hw = draw.textbbox((0, 0), host_text, font=font)[2]
    draw_sharp_text(image, ((width - hw) // 2, 23), host_text, (150, 170, 185), font)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

