from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import urllib.request
from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "hubitat_safety"
CARD_NAME = "Hubitat Safety"
CARD_DETAIL = "All secure or open list"
CARD_OPTIONS = [
    {"key": "hubIp", "label": "Hub IP", "type": "text", "default": "192.168.1.100"},
    {"key": "appId", "label": "Maker API App #", "type": "text", "default": ""},
    {"key": "token", "label": "Access Token", "type": "text", "default": ""},
    {"key": "devices", "label": "Devices", "type": "hubitatDevices", "default": "", "maxlength": 180},
    {"key": "attribute", "label": "Attribute", "type": "text", "default": "contact"},
    {"key": "goodValue", "label": "Good Value", "type": "text", "default": "closed"},
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


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    hub_ip = (opts.get("hubIp") or "").strip()
    app_id = (opts.get("appId") or "").strip()
    token = (opts.get("token") or "").strip()
    attr = (opts.get("attribute") or "contact").strip()
    good = str(opts.get("goodValue") or "closed").strip().lower()
    devices = _parse_devices(opts.get("devices"))
    if not all([hub_ip, app_id, token]) or not devices:
        return render_text_webp("SET HUB", (100, 180, 255))

    bad = []
    try:
        for label, device_id in devices:
            device = _fetch_device(hub_ip, app_id, token, device_id)
            value = str(_get_attr(device, attr) or "").strip().lower()
            if value != good:
                bad.append((label, value.upper()[:7] or "?"))
    except Exception:
        return render_text_webp("HUB ERR", (238, 80, 80))

    image = Image.new("RGB", (64, 32), (0, 5, 15))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    if opts.get("_target") == "matrixportal-s3-128x32":
        image = Image.new("RGB", (128, 32), (0, 5, 15))
        draw = ImageDraw.Draw(image)
        if not bad:
            draw.rectangle((0, 0, 127, 31), fill=(0, 20, 12))
            draw.rectangle((7, 9, 19, 24), outline=(80, 240, 130))
            draw.arc((9, 3, 17, 13), 180, 360, fill=(80, 240, 130))
            text = "ALL SECURE"
            w = draw.textbbox((0, 0), text, font=bold)[2]
            draw_sharp_text(image, ((128 - w) // 2, 9), text, (80, 240, 130), bold)
            draw.rectangle((109, 9, 121, 24), outline=(80, 240, 130))
            draw.line((112, 17, 115, 21), fill=(80, 240, 130))
            draw.line((115, 21, 120, 13), fill=(80, 240, 130))
        else:
            draw.rectangle((0, 0, 127, 8), fill=(45, 0, 0))
            title = "CHECK DEVICES"
            tw = draw.textbbox((0, 0), title, font=bold)[2]
            draw_sharp_text(image, ((128 - tw) // 2, -3), title, (255, 90, 80), bold)
            for idx, (label, value) in enumerate(bad[:4]):
                col = idx % 2
                row = idx // 2
                x = 2 + col * 64
                y = 9 + row * 11
                draw_sharp_text(image, (x, y - 2), label[:8], (255, 230, 220), font)
                w = draw.textbbox((0, 0), value, font=font)[2]
                draw_sharp_text(image, (x + 61 - w, y - 2), value, (255, 90, 80), font)
        out = BytesIO()
        image.save(out, "WEBP", lossless=True, quality=100)
        return out.getvalue()

    if not bad:
        draw.rectangle((0, 0, 63, 31), fill=(0, 20, 12))
        draw_sharp_text(image, (7, 4), "ALL", (80, 240, 130), bold)
        draw_sharp_text(image, (7, 14), "SECURE", (80, 240, 130), bold)
        draw.rectangle((46, 9, 58, 24), outline=(80, 240, 130))
        draw.arc((48, 3, 56, 13), 180, 360, fill=(80, 240, 130))
    else:
        draw.rectangle((0, 0, 63, 8), fill=(45, 0, 0))
        draw_sharp_text(image, (1, -3), "CHECK", (255, 90, 80), bold)
        y = 7
        for label, value in bad[:3]:
            draw_sharp_text(image, (1, y), label[:8], (255, 230, 220), font)
            w = draw.textbbox((0, 0), value, font=font)[2]
            draw_sharp_text(image, (63 - w, y), value, (255, 90, 80), font)
            y += 8

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

