from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import urllib.request
from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "hubitat_multi"
CARD_NAME = "Hubitat Multi"
CARD_DETAIL = "Several Hubitat devices"
CARD_OPTIONS = [
    {"key": "hubIp", "label": "Hub IP", "type": "text", "default": "192.168.1.100"},
    {"key": "appId", "label": "Maker API App #", "type": "text", "default": ""},
    {"key": "token", "label": "Access Token", "type": "text", "default": ""},
    {"key": "devices", "label": "Devices", "type": "hubitatDevices", "default": "", "maxlength": 220, "perDeviceAttributes": True},
]

_CACHE = {}


def _parse_devices(value):
    devices = []
    for part in str(value or "").split(","):
        part = part.strip()
        if not part:
            continue
        pieces = part.split(":")
        if len(pieces) >= 3:
            label = ":".join(pieces[:-2])
            device_id = pieces[-2]
            attribute = pieces[-1]
        elif len(pieces) == 2:
            label, device_id = pieces
            attribute = ""
        else:
            label, device_id, attribute = part, part, ""
        label = label.strip()[:10]
        device_id = device_id.strip()
        attribute = attribute.strip()
        if device_id:
            devices.append((label or device_id, device_id, attribute))
    return devices[:4]


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
    _CACHE[key] = {"data": data, "expires": now + timedelta(seconds=30)}
    return data


def _get_attr(device, attr_name):
    for attr in device.get("attributes", []):
        if attr.get("name", "").lower() == attr_name.lower():
            return attr.get("currentValue")
    return None


def _fmt(value, attr):
    if value is None:
        return "--", (150, 160, 170)
    name = attr.lower()
    raw = str(value)
    if name in ("temperature", "humidity", "battery", "level", "power"):
        try:
            n = float(raw)
            suffix = {"temperature": "°", "humidity": "%", "battery": "%", "level": "%", "power": "W"}.get(name, "")
            return f"{n:.0f}{suffix}", (255, 195, 80) if name in ("temperature", "power") else (100, 185, 255)
        except Exception:
            pass
    if name in ("contact", "motion", "switch", "lock", "presence", "water"):
        state = raw.lower()
        if state in ("open", "active", "on", "unlocked", "present", "wet"):
            return raw.upper()[:4], (255, 116, 126)
        if state in ("closed", "inactive", "off", "locked", "not present", "dry"):
            return raw.upper()[:4], (120, 230, 150)
    return raw.upper()[:7], (235, 245, 255)


def _attr_tag(attr):
    name = str(attr or "").strip().lower()
    tags = {
        "temperature": "T",
        "humidity": "H",
        "battery": "B",
        "level": "L",
        "power": "W",
        "contact": "C",
        "motion": "M",
        "switch": "S",
        "lock": "K",
        "presence": "P",
        "water": "W",
        "illuminance": "I",
        "lux": "I",
    }
    return tags.get(name, (name[:1] or "?").upper())


def _attr_short(attr):
    name = str(attr or "").strip().lower()
    labels = {
        "temperature": "TEMP",
        "humidity": "HUM",
        "battery": "BATT",
        "level": "LVL",
        "power": "PWR",
        "contact": "CNCT",
        "motion": "MOT",
        "switch": "SW",
        "lock": "LOCK",
        "presence": "PRES",
        "water": "WATR",
        "illuminance": "LUX",
        "lux": "LUX",
    }
    return labels.get(name, name.upper()[:4] or "ATTR")


def _fit_text(draw, text, font, max_width):
    text = str(text or "")
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1]
    return text


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    hub_ip = (opts.get("hubIp") or "").strip()
    app_id = (opts.get("appId") or "").strip()
    token = (opts.get("token") or "").strip()
    attr = (opts.get("attribute") or "temperature").strip()
    devices = _parse_devices(opts.get("devices"))
    if not all([hub_ip, app_id, token]) or not devices:
        return render_text_webp("SET HUB", (100, 180, 255))

    rows = []
    try:
        for label, device_id, device_attr in devices:
            row_attr = device_attr or attr
            device = _fetch_device(hub_ip, app_id, token, device_id)
            value, color = _fmt(_get_attr(device, row_attr), row_attr)
            rows.append((label, value, color, row_attr))
    except Exception:
        return render_text_webp("HUB ERR", (238, 80, 80))

    image = Image.new("RGB", (64, 32), (0, 5, 15))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    if opts.get("_target") == "matrixportal-s3-128x32":
        header_h = 8
        row_h = 8
        visible_h = 24
        content_h = max(visible_h, len(rows[:4]) * row_h)

        content = Image.new("RGB", (128, content_h), (0, 5, 15))
        cdraw = ImageDraw.Draw(content)
        for idx, (label, value, color, row_attr) in enumerate(rows[:4]):
            y = idx * row_h
            if idx:
                cdraw.line((0, y, 127, y), fill=(12, 28, 38))
            tag = _attr_tag(row_attr)
            cdraw.rectangle((2, y + 1, 9, y + 7), fill=(12, 35, 48))
            draw_sharp_text(content, (4, y - 1), tag, (120, 230, 255), font)
            w = cdraw.textbbox((0, 0), value, font=font)[2]
            value_x = 126 - w
            label_x = 14
            label_text = _fit_text(cdraw, label, font, max(0, value_x - label_x - 3))
            draw_sharp_text(content, (label_x, y - 1), label_text, (185, 205, 225), font)
            draw_sharp_text(content, (value_x, y - 1), value, color, font)

        def frame(offset):
            image = Image.new("RGB", (128, 32), (0, 5, 15))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 127, 7), fill=(0, 15, 40))
            draw_sharp_text(image, (2, -3), "HUBITAT MULTI", (120, 190, 255), bold)
            image.paste(content.crop((0, offset, 128, offset + visible_h)), (0, header_h))
            return image

        out = BytesIO()
        max_offset = max(0, content_h - visible_h)
        if max_offset:
            offsets = [0] * 20 + list(range(1, max_offset + 1)) + [max_offset] * 28
            frames = [frame(offset) for offset in offsets]
            durations = [90] * len(frames)
            frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=durations, loop=0, lossless=True, quality=100)
        else:
            frame(0).save(out, "WEBP", lossless=True, quality=100)
        return out.getvalue()

    draw.rectangle((0, 0, 63, 8), fill=(0, 15, 40))
    draw_sharp_text(image, (1, -3), "HUB MULTI", (120, 190, 255), bold)
    y = 7
    for label, value, color, row_attr in rows:
        tag = _attr_tag(row_attr)
        draw.rectangle((0, y + 1, 7, y + 7), fill=(12, 35, 48))
        draw_sharp_text(image, (2, y - 1), tag, (120, 230, 255), font)
        draw_sharp_text(image, (10, y), label[:6], (185, 205, 225), font)
        w = draw.textbbox((0, 0), value, font=font)[2]
        draw_sharp_text(image, (63 - w, y), value, color, font)
        y += 8

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
