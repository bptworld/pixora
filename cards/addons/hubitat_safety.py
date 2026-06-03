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
    {"key": "devices", "label": "Devices", "type": "hubitatDevices", "default": "", "maxlength": 320},
    {"key": "customHeader", "label": "Custom Header", "type": "text", "default": "", "maxlength": 18},
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
        pieces = part.split(":")
        if len(pieces) >= 4:
            label = ":".join(pieces[:-3])
            device_id = pieces[-3]
            alias = pieces[-1]
        elif len(pieces) >= 2:
            label, device_id = pieces[0], pieces[1]
            alias = ""
        else:
            label, device_id, alias = part, part, ""
        label = alias.strip() or label.strip() or device_id.strip()
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


def _fit_text(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1]
    return text


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    hub_ip = (opts.get("hubIp") or "").strip()
    app_id = (opts.get("appId") or "").strip()
    token = (opts.get("token") or "").strip()
    attr = (opts.get("attribute") or "contact").strip()
    good = str(opts.get("goodValue") or "closed").strip().lower()
    custom_header = (opts.get("customHeader") or "").strip()
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
        if not bad:
            image = Image.new("RGB", (128, 32), (0, 5, 15))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 127, 31), fill=(0, 20, 12))
            draw.rectangle((7, 9, 19, 24), outline=(80, 240, 130))
            draw.arc((9, 3, 17, 13), 180, 360, fill=(80, 240, 130))
            text = "ALL SECURE"
            w = draw.textbbox((0, 0), text, font=bold)[2]
            draw_sharp_text(image, ((128 - w) // 2, 9), text, (80, 240, 130), bold)
            draw.rectangle((109, 9, 121, 24), outline=(80, 240, 130))
            draw.line((112, 17, 115, 21), fill=(80, 240, 130))
            draw.line((115, 21, 120, 13), fill=(80, 240, 130))
            out = BytesIO()
            image.save(out, "WEBP", lossless=True, quality=100)
            return out.getvalue()

        row_h = 8
        visible_h = 24
        content_h = max(visible_h, len(bad) * row_h)
        content = Image.new("RGB", (128, content_h), (0, 5, 15))
        cdraw = ImageDraw.Draw(content)
        for idx, (label, value) in enumerate(bad):
            y = idx * row_h
            if idx:
                cdraw.line((0, y, 127, y), fill=(28, 14, 18))
            w = cdraw.textbbox((0, 0), value, font=font)[2]
            value_x = 126 - w
            label_text = _fit_text(cdraw, label, font, max(0, value_x - 4))
            draw_sharp_text(content, (2, y - 2), label_text, (255, 230, 220), font)
            draw_sharp_text(content, (value_x, y - 2), value, (255, 90, 80), font)

        def frame(offset):
            image = Image.new("RGB", (128, 32), (0, 5, 15))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 127, 8), fill=(45, 0, 0))
            title = _fit_text(draw, (custom_header or "CHECK DEVICES").upper(), bold, 126)
            tw = draw.textbbox((0, 0), title, font=bold)[2]
            draw_sharp_text(image, ((128 - tw) // 2, -3), title, (255, 90, 80), bold)
            image.paste(content.crop((0, offset, 128, offset + visible_h)), (0, 8))
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

    if not bad:
        draw.rectangle((0, 0, 63, 31), fill=(0, 20, 12))
        draw_sharp_text(image, (7, 4), "ALL", (80, 240, 130), bold)
        draw_sharp_text(image, (7, 14), "SECURE", (80, 240, 130), bold)
        draw.rectangle((46, 9, 58, 24), outline=(80, 240, 130))
        draw.arc((48, 3, 56, 13), 180, 360, fill=(80, 240, 130))
    else:
        row_h = 8
        visible_h = 24
        content_h = max(visible_h, len(bad) * row_h)
        content = Image.new("RGB", (64, content_h), (0, 5, 15))
        cdraw = ImageDraw.Draw(content)
        for idx, (label, value) in enumerate(bad):
            y = idx * row_h
            w = cdraw.textbbox((0, 0), value, font=font)[2]
            value_x = 63 - w
            label_text = _fit_text(cdraw, label, font, max(0, value_x - 2))
            draw_sharp_text(content, (1, y), label_text, (255, 230, 220), font)
            draw_sharp_text(content, (value_x, y), value, (255, 90, 80), font)

        def frame(offset):
            image = Image.new("RGB", (64, 32), (0, 5, 15))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 63, 8), fill=(45, 0, 0))
            title = _fit_text(draw, (custom_header or "CHECK").upper(), bold, 62)
            tw = draw.textbbox((0, 0), title, font=bold)[2]
            draw_sharp_text(image, ((64 - tw) // 2, -3), title, (255, 90, 80), bold)
            image.paste(content.crop((0, offset, 64, offset + visible_h)), (0, 8))
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

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
