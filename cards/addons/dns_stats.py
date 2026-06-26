from datetime import datetime, timedelta, timezone
from io import BytesIO
import base64
import json
import urllib.parse
import urllib.request

from card_utils import draw_sharp_text, format_compact_number, render_text_webp

CARD_ID = "dns_stats"
CARD_NAME = "DNS Stats"
CARD_DETAIL = "Pi-hole or AdGuard stats"
CARD_OPTIONS = [
    {
        "key": "service",
        "label": "Service",
        "type": "select",
        "default": "pihole",
        "choices": [
            {"value": "pihole", "label": "Pi-hole"},
            {"value": "adguard", "label": "AdGuard Home"},
        ],
    },
    {"key": "host", "label": "Host URL", "type": "text", "default": "http://192.168.1.2", "maxlength": 80},
    {"key": "apiToken", "label": "Pi-hole API Token", "type": "password", "default": ""},
    {"key": "username", "label": "AdGuard Username", "type": "text", "default": ""},
    {"key": "password", "label": "AdGuard Password", "type": "password", "default": ""},
]

_CACHE = {}


def _fetch(url, headers=None, seconds=60):
    now = datetime.now(timezone.utc)
    key = url + "|" + json.dumps(headers or {}, sort_keys=True)
    cached = _CACHE.get(key)
    if cached and cached["expires"] > now:
        return cached["data"]
    req = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1", "Accept": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    _CACHE[key] = {"data": data, "expires": now + timedelta(seconds=seconds)}
    return data


def _base(host):
    host = (host or "").strip().rstrip("/")
    if not host:
        raise ValueError("host required")
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host


def _pihole(opts):
    host = _base(opts.get("host"))
    token = (opts.get("apiToken") or "").strip()
    qs = "?summaryRaw"
    if token:
        qs += "&auth=" + urllib.parse.quote(token)
    data = _fetch(host + "/admin/api.php" + qs, seconds=60)
    total = data.get("dns_queries_today") or data.get("queries") or 0
    blocked = data.get("ads_blocked_today") or data.get("blocked_queries") or 0
    pct = data.get("ads_percentage_today")
    if pct is None and total:
        pct = float(blocked) / float(total) * 100
    return "PI-HOLE", total, blocked, pct


def _adguard(opts):
    host = _base(opts.get("host"))
    user = (opts.get("username") or "").strip()
    password = (opts.get("password") or "").strip()
    headers = {}
    if user or password:
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = "Basic " + token
    data = _fetch(host + "/control/stats", headers, seconds=60)
    total = data.get("num_dns_queries") or 0
    blocked = data.get("num_blocked_filtering") or 0
    pct = (float(blocked) / float(total) * 100) if total else 0
    return "ADGUARD", total, blocked, pct


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    try:
        if (opts.get("service") or "pihole") == "adguard":
            title, total, blocked, pct = _adguard(opts)
        else:
            title, total, blocked, pct = _pihole(opts)
    except Exception:
        return render_text_webp("DNS ERR", (238, 80, 80))

    image = Image.new("RGB", (64, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    if opts.get("_target") == "matrixportal-s3-128x32":
        image = Image.new("RGB", (128, 32), (0, 5, 12))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 127, 6), fill=(5, 18, 24))
        title_w = draw.textbbox((0, 0), title[:16], font=bold)[2]
        draw_sharp_text(image, ((128 - title_w) // 2, -3), title[:16], (80, 220, 170), bold)
        rows = [
            ("BLOCKED", format_compact_number(blocked), (245, 250, 255), bold),
            ("TOTAL", format_compact_number(total), (200, 220, 235), font),
            ("RATE", f"{float(pct or 0):.1f}%", (255, 210, 80), font),
        ]
        y = 8
        for label, value, color, value_font in rows:
            draw_sharp_text(image, (2, y - 2), label, (145, 165, 182), font)
            w = draw.textbbox((0, 0), value, font=value_font)[2]
            draw_sharp_text(image, (126 - w, y - 2), value, color, value_font)
            y += 8
        out = BytesIO()
        image.save(out, "WEBP", lossless=True, quality=100)
        return out.getvalue()

    draw.rectangle((0, 0, 63, 6), fill=(5, 18, 24))
    draw_sharp_text(image, (1, -3), title[:12], (80, 220, 170), bold)
    draw_sharp_text(image, (1, 9), "BLOCK", (145, 165, 182), font)
    b = format_compact_number(blocked)
    bw = draw.textbbox((0, 0), b, font=bold)[2]
    draw_sharp_text(image, (63 - bw, 8), b, (245, 250, 255), bold)
    draw_sharp_text(image, (1, 18), "TOTAL", (145, 165, 182), font)
    t = format_compact_number(total)
    tw = draw.textbbox((0, 0), t, font=font)[2]
    draw_sharp_text(image, (63 - tw, 18), t, (200, 220, 235), font)
    p = f"{float(pct or 0):.1f}%"
    pw = draw.textbbox((0, 0), p, font=font)[2]
    draw_sharp_text(image, (63 - pw, 22), p, (255, 210, 80), font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
