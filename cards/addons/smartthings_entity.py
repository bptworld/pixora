from io import BytesIO
import urllib.parse

from card_utils import draw_sharp_text, fetch_json_with_headers, render_text_webp

CARD_ID = "smartthings_entity"
CARD_NAME = "SmartThings Entity"
CARD_DETAIL = "Live SmartThings state"
CARD_OPTIONS = [
    {"key": "token", "label": "SmartThings PAT Token", "type": "password", "default": ""},
    {"key": "deviceId", "label": "Device", "type": "smartthingsDevices", "default": "", "maxlength": 120},
    {"key": "capability", "label": "Capability", "type": "text", "default": "temperatureMeasurement", "maxlength": 80},
    {"key": "attribute", "label": "Attribute", "type": "text", "default": "temperature", "maxlength": 60},
    {"key": "component", "label": "Component", "type": "text", "default": "main", "maxlength": 40},
    {"key": "label", "label": "Display Label", "type": "text", "default": "", "maxlength": 12},
]
CARD_RULE_FIELDS = [
    {"id": "value", "label": "Value"},
    {"id": "unit", "label": "Unit"},
    {"id": "device_label", "label": "Device Label"},
]

API_ROOT = "https://api.smartthings.com/v1"


def _device_id(value):
    text = str(value or "").strip()
    if ":" in text:
        return text.split(":")[-1].strip()
    return text


def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "Pixora/0.1",
    }


def _device(token, device_id):
    url = API_ROOT + "/devices/" + urllib.parse.quote(device_id, safe="")
    return fetch_json_with_headers(url, _headers(token), seconds=120, cache_key=f"st:device:{device_id}")


def _status(token, device_id):
    url = API_ROOT + "/devices/" + urllib.parse.quote(device_id, safe="") + "/status"
    return fetch_json_with_headers(url, _headers(token), seconds=30, cache_key=f"st:status:{device_id}")


def _status_value(status, component, capability, attribute):
    components = status.get("components") or {}
    comp = components.get(component) or components.get("main") or {}
    cap = comp.get(capability) or {}
    attr = cap.get(attribute) or {}
    if isinstance(attr, dict):
        return attr.get("value"), attr.get("unit")
    return attr, ""


def _fmt_value(capability, attribute, value, unit):
    if value is None:
        return "--", (150, 160, 170)
    raw = str(value)
    key = f"{capability}.{attribute}".lower()
    suffix = unit or ""
    if attribute.lower() in ("temperature", "humidity", "battery", "level", "power", "energy"):
        try:
            n = float(raw)
            if not suffix:
                suffix = {
                    "temperature": "°",
                    "humidity": "%",
                    "battery": "%",
                    "level": "%",
                    "power": "W",
                    "energy": "kWh",
                }.get(attribute.lower(), "")
            color = (255, 195, 80) if attribute.lower() in ("temperature", "power", "energy") else (100, 185, 255)
            return f"{n:.0f}{suffix}"[:10], color
        except Exception:
            pass
    if key.endswith(".switch"):
        return raw.upper()[:8], (80, 220, 120) if raw.lower() == "on" else (100, 130, 160)
    if key.endswith(".contact"):
        return raw.upper()[:8], (238, 80, 80) if raw.lower() == "open" else (80, 220, 120)
    if key.endswith(".motion"):
        active = raw.lower() == "active"
        return ("MOTION" if active else "CLEAR"), (238, 80, 80) if active else (80, 220, 120)
    if key.endswith(".lock"):
        locked = raw.lower() == "locked"
        return ("LOCKED" if locked else "UNLOCK"), (80, 220, 120) if locked else (238, 80, 80)
    return raw.upper()[:10], (245, 250, 255)


def rule_value(options=None, field=""):
    opts = options or {}
    token = str(opts.get("token") or "").strip()
    device_id = _device_id(opts.get("deviceId"))
    capability = str(opts.get("capability") or "temperatureMeasurement").strip()
    attribute = str(opts.get("attribute") or "temperature").strip()
    component = str(opts.get("component") or "main").strip()
    if not token or not device_id or not capability or not attribute:
        return ""
    key = str(field or "value").strip()
    device = _device(token, device_id)
    status = _status(token, device_id)
    value, unit = _status_value(status, component, capability, attribute)
    if key == "value":
        return "" if value is None else value
    if key == "unit":
        return unit or ""
    if key == "device_label":
        return device.get("label") or device.get("name") or device_id
    return ""


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    token = str(opts.get("token") or "").strip()
    device_id = _device_id(opts.get("deviceId"))
    capability = str(opts.get("capability") or "temperatureMeasurement").strip()
    attribute = str(opts.get("attribute") or "temperature").strip()
    component = str(opts.get("component") or "main").strip()
    label = str(opts.get("label") or "").strip()
    if not token or not device_id or not capability or not attribute:
        return render_text_webp("SET ST", (100, 180, 255))

    try:
        device = _device(token, device_id)
        status = _status(token, device_id)
        value, unit = _status_value(status, component, capability, attribute)
        value_text, value_color = _fmt_value(capability, attribute, value, unit)
    except Exception:
        return render_text_webp("ST ERR", (238, 80, 80))

    title = label or device.get("label") or device.get("name") or device_id
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    image = Image.new("RGB", (width, 32), (0, 5, 15))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 16)
    except Exception:
        font = bold = big = ImageFont.load_default()

    if width == 128:
        draw.rectangle((0, 0, 127, 6), fill=(0, 18, 38))
        title = title[:20].upper()
        tw = draw.textbbox((0, 0), title, font=bold)[2]
        draw_sharp_text(image, ((128 - tw) // 2, -3), title, (120, 200, 255), bold)
        vw = draw.textbbox((0, 0), value_text, font=big)[2]
        value_font = big if vw <= 94 else bold
        vw = draw.textbbox((0, 0), value_text, font=value_font)[2]
        draw_sharp_text(image, ((128 - vw) // 2, 6 if value_font == big else 10), value_text, value_color, value_font)
        meta = attribute.upper()[:18]
        mw = draw.textbbox((0, 0), meta, font=font)[2]
        draw_sharp_text(image, ((128 - mw) // 2, 22), meta, (80, 105, 130), font)
    else:
        draw.rectangle((0, 0, 63, 6), fill=(0, 18, 38))
        title = title[:12].upper()
        tw = draw.textbbox((0, 0), title, font=bold)[2]
        draw_sharp_text(image, ((64 - tw) // 2, -3), title, (120, 200, 255), bold)
        vw = draw.textbbox((0, 0), value_text, font=big)[2]
        value_font = big if vw <= 62 else bold
        vw = draw.textbbox((0, 0), value_text, font=value_font)[2]
        draw_sharp_text(image, ((64 - vw) // 2, 6 if value_font == big else 10), value_text, value_color, value_font)
        meta = attribute.upper()[:12]
        mw = draw.textbbox((0, 0), meta, font=font)[2]
        draw_sharp_text(image, ((64 - mw) // 2, 22), meta, (80, 105, 130), font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
