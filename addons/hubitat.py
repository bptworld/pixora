from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import urllib.request
from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "hubitat"
CARD_NAME = "Hubitat Device"
CARD_DETAIL = "Live device attribute"
CARD_OPTIONS = [
    {"key": "hubIp",    "label": "Hub IP",         "type": "text",   "default": "192.168.1.100"},
    {"key": "appId",    "label": "Maker API App #", "type": "text",   "default": ""},
    {"key": "token",    "label": "Access Token",    "type": "text",   "default": ""},
    {"key": "deviceId", "label": "Device ID",       "type": "text",   "default": ""},
    {"key": "attribute","label": "Attribute",       "type": "text",   "default": "temperature"},
    {"key": "label",    "label": "Display Label",   "type": "text",   "default": ""},
]

_CACHE = {}


def _fetch_device(hub_ip, app_id, token, device_id):
    now    = datetime.now(timezone.utc)
    key    = f"{hub_ip}:{device_id}"
    cached = _CACHE.get(key)
    if cached and cached["expires"] > now:
        return cached["data"]
    url = f"http://{hub_ip}/apps/api/{app_id}/devices/{device_id}?access_token={token}"
    req = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    _CACHE[key] = {"data": data, "expires": now + timedelta(seconds=30)}
    return data


def _get_attr(device_data, attr_name):
    for attr in device_data.get("attributes", []):
        if attr.get("name", "").lower() == attr_name.lower():
            return attr.get("currentValue")
    return None


def _fmt(attr_name, value):
    v    = str(value) if value is not None else "--"
    name = attr_name.lower()

    if name == "temperature":
        try:    return f"{float(v):.1f}°", (255, 195, 80)
        except: return v, (255, 195, 80)

    if name == "humidity":
        try:    return f"{float(v):.0f}%", (100, 185, 255)
        except: return v, (100, 185, 255)

    if name in ("battery", "level"):
        try:
            n = float(v)
            col = (80, 220, 120) if n > 20 else (238, 80, 80)
            return f"{n:.0f}%", col
        except: return v, (200, 200, 200)

    if name == "switch":
        on = v.lower() == "on"
        return ("ON" if on else "OFF"), ((80, 220, 120) if on else (100, 130, 160))

    if name == "motion":
        active = v.lower() == "active"
        return ("MOTION" if active else "CLEAR"), ((80, 220, 120) if active else (100, 130, 160))

    if name == "contact":
        open_ = v.lower() == "open"
        return ("OPEN" if open_ else "CLOSED"), ((238, 80, 80) if open_ else (80, 220, 120))

    if name == "presence":
        home = v.lower() in ("present", "home")
        return ("HOME" if home else "AWAY"), ((80, 220, 120) if home else (160, 100, 100))

    if name == "lock":
        locked = v.lower() == "locked"
        return ("LOCKED" if locked else "UNLOCKED"), ((80, 220, 120) if locked else (238, 80, 80))

    if name == "power":
        try:    return f"{float(v):.0f}W", (255, 195, 80)
        except: return v, (255, 255, 255)

    if name == "energy":
        try:    return f"{float(v):.1f}kW", (255, 195, 80)
        except: return v, (255, 255, 255)

    # Generic number or string
    try:
        n = float(v)
        return (f"{n:.1f}" if n != int(n) else str(int(n))), (255, 255, 255)
    except:
        return v.upper()[:8], (255, 255, 255)


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont
    opts      = options or {}
    hub_ip    = (opts.get("hubIp")    or "").strip()
    app_id    = (opts.get("appId")    or "").strip()
    token     = (opts.get("token")    or "").strip()
    device_id = (opts.get("deviceId") or "").strip()
    attribute = (opts.get("attribute") or "temperature").strip()
    label     = (opts.get("label")    or "").strip()

    if not all([hub_ip, app_id, token, device_id]):
        return render_text_webp("SET HUB", (100, 180, 255))

    try:
        device = _fetch_device(hub_ip, app_id, token, device_id)
    except Exception as e:
        return render_text_webp("HUB ERR", (238, 80, 80))

    device_label = label or device.get("label") or device.get("name") or device_id
    value        = _get_attr(device, attribute)
    val_str, val_color = _fmt(attribute, value)

    image = Image.new("RGB", (64, 32), (0, 5, 15))
    draw  = ImageDraw.Draw(image)
    try:
        font  = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold  = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        large = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 16)
    except Exception:
        font = bold = large = ImageFont.load_default()

    if opts.get("_target") == "matrixportal-s3-128x32":
        image = Image.new("RGB", (128, 32), (0, 5, 15))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 127, 8), fill=(0, 15, 40))
        lbl = device_label[:20]
        lw = draw.textbbox((0, 0), lbl, font=bold)[2]
        draw_sharp_text(image, ((128 - lw) // 2, -3), lbl, (160, 190, 230), bold)
        vw = draw.textbbox((0, 0), val_str, font=large)[2]
        if vw <= 98:
            draw_sharp_text(image, ((128 - vw) // 2, 5), val_str, val_color, large)
        else:
            vw = draw.textbbox((0, 0), val_str, font=bold)[2]
            draw_sharp_text(image, ((128 - vw) // 2, 10), val_str, val_color, bold)
        attr_lbl = attribute[:18].upper()
        aw = draw.textbbox((0, 0), attr_lbl, font=font)[2]
        draw_sharp_text(image, ((128 - aw) // 2, 24), attr_lbl, (70, 90, 115), font)
        out = BytesIO()
        image.save(out, "WEBP", lossless=True, quality=100)
        return out.getvalue()

    # Header bar: device label
    draw.rectangle((0, 0, 63, 8), fill=(0, 15, 40))
    lbl = device_label[:10]
    lw  = draw.textbbox((0, 0), lbl, font=bold)[2]
    draw_sharp_text(image, ((64 - lw) // 2, -3), lbl, (160, 190, 230), bold)

    # Large value centered in remaining space
    vw = draw.textbbox((0, 0), val_str, font=large)[2]
    if vw <= 60:
        draw_sharp_text(image, ((64 - vw) // 2, 2), val_str, val_color, large)
    else:
        vw2 = draw.textbbox((0, 0), val_str, font=bold)[2]
        draw_sharp_text(image, ((64 - vw2) // 2, 8), val_str, val_color, bold)

    # Attribute name at bottom, muted
    attr_lbl = attribute[:12]
    aw = draw.textbbox((0, 0), attr_lbl, font=font)[2]
    draw_sharp_text(image, ((64 - aw) // 2, 18), attr_lbl, (70, 90, 115), font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

