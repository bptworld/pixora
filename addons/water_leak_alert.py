from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import urllib.request
from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "water_leak_alert"
CARD_NAME = "Water Leak Alert"
CARD_DETAIL = "Skips when all dry"
CARD_OPTIONS = [
    {"key": "hubIp", "label": "Hub IP", "type": "text", "default": "192.168.1.100"},
    {"key": "appId", "label": "Maker API App #", "type": "text", "default": ""},
    {"key": "token", "label": "Access Token", "type": "text", "default": ""},
    {"key": "devices", "label": "Leak Devices", "type": "hubitatDevices", "default": "", "maxlength": 180},
]

_CACHE = {}


def _parse_devices(value):
    devices = []
    for part in str(value or "").split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            label, device_id = part.split(":", 1)
        else:
            label, device_id = part, part
        label = label.strip()[:10]
        device_id = device_id.strip()
        if device_id:
            devices.append((label or device_id, device_id))
    return devices[:8]


def _fetch_device(hub_ip, app_id, token, device_id):
    now = datetime.now(timezone.utc)
    key = f"{hub_ip}:{app_id}:{device_id}"
    cached = _CACHE.get(key)
    if cached and cached["expires"] > now:
        return cached["data"]
    url = f"http://{hub_ip}/apps/api/{app_id}/devices/{device_id}?access_token={token}"
    req = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    _CACHE[key] = {"data": data, "expires": now + timedelta(seconds=20)}
    return data


def _get_attr(device, attr_name):
    for attr in device.get("attributes", []):
        if attr.get("name", "").lower() == attr_name.lower():
            return attr.get("currentValue")
    return None


def _wet(value):
    return str(value or "").strip().lower() in ("wet", "detected", "active", "open", "leak")


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    hub_ip = (opts.get("hubIp") or "").strip()
    app_id = (opts.get("appId") or "").strip()
    token = (opts.get("token") or "").strip()
    devices = _parse_devices(opts.get("devices"))
    if not all([hub_ip, app_id, token]) or not devices:
        return render_text_webp("SET LEAK", (100, 180, 255))

    wet = []
    try:
        for label, device_id in devices:
            device = _fetch_device(hub_ip, app_id, token, device_id)
            value = _get_attr(device, "water") or _get_attr(device, "moisture") or _get_attr(device, "contact")
            if _wet(value):
                wet.append(label)
    except Exception:
        return render_text_webp("LEAK ERR", (238, 80, 80))

    if not wet:
        return None

    image = Image.new("RGB", (64, 32), (18, 0, 0))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    if opts.get("_target") == "matrixportal-s3-128x32":
        image = Image.new("RGB", (128, 32), (18, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 127, 8), fill=(65, 0, 0))
        title = "WATER LEAK!"
        tw = draw.textbbox((0, 0), title, font=bold)[2]
        draw_sharp_text(image, ((128 - tw) // 2, -3), title, (255, 90, 80), bold)
        draw.polygon([(114, 7), (108, 18), (114, 27), (120, 18)], fill=(80, 180, 255))
        draw.ellipse((109, 17, 119, 28), fill=(80, 180, 255))
        for idx, label in enumerate(wet[:4]):
            col = idx % 2
            row = idx // 2
            draw_sharp_text(image, (2 + col * 58, 9 + row * 10), label[:10], (255, 230, 220), font)
        out = BytesIO()
        image.save(out, "WEBP", lossless=True, quality=100)
        return out.getvalue()

    draw.rectangle((0, 0, 63, 8), fill=(65, 0, 0))
    draw_sharp_text(image, (1, -3), "WATER!", (255, 90, 80), bold)
    draw.polygon([(54, 7), (48, 18), (54, 27), (60, 18)], fill=(80, 180, 255))
    draw.ellipse((49, 17, 59, 28), fill=(80, 180, 255))
    y = 8
    for label in wet[:3]:
        draw_sharp_text(image, (1, y), label[:10], (255, 230, 220), font)
        y += 8

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

