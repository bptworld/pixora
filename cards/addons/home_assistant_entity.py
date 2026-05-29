from io import BytesIO
import urllib.parse

from card_utils import draw_sharp_text, fetch_json_with_headers, render_text_webp

CARD_ID = "home_assistant_entity"
CARD_NAME = "Home Assistant Entity"
CARD_DETAIL = "Live Home Assistant state"
CARD_OPTIONS = [
    {"key": "host", "label": "Home Assistant URL", "type": "text", "default": "http://homeassistant.local:8123", "maxlength": 100},
    {"key": "token", "label": "Long-Lived Access Token", "type": "password", "default": ""},
    {"key": "entityId", "label": "Entity ID", "type": "text", "default": "sensor.outdoor_temperature", "maxlength": 80},
    {"key": "label", "label": "Display Label", "type": "text", "default": "", "maxlength": 12},
]


def _state(host, token, entity_id):
    host = host.rstrip("/")
    url = host + "/api/states/" + urllib.parse.quote(entity_id, safe="")
    return fetch_json_with_headers(url, {"Authorization": f"Bearer {token}"}, seconds=30, cache_key=f"ha:{host}:{entity_id}")


def _fmt_state(data):
    state = str(data.get("state", "--"))
    unit = (data.get("attributes") or {}).get("unit_of_measurement") or ""
    friendly = (data.get("attributes") or {}).get("friendly_name") or data.get("entity_id") or "HA"
    value = (state + unit)[:10]
    return friendly, value


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    host = (opts.get("host") or "").strip()
    token = (opts.get("token") or "").strip()
    entity_id = (opts.get("entityId") or "").strip()
    label = (opts.get("label") or "").strip()
    if not host or not token or not entity_id:
        return render_text_webp("SET HA", (100, 180, 255))
    try:
        data = _state(host, token, entity_id)
        friendly, value = _fmt_state(data)
    except Exception:
        return render_text_webp("HA ERR", (238, 80, 80))
    title = label or friendly
    image = Image.new("RGB", (64, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 16)
    except Exception:
        font = bold = big = ImageFont.load_default()
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    if width == 128:
        image = Image.new("RGB", (128, 32), (0, 5, 12))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 127, 8), fill=(0, 20, 35))
        title = title[:20].upper()
        tw = draw.textbbox((0, 0), title, font=bold)[2]
        draw_sharp_text(image, ((128 - tw) // 2, -3), title, (65, 190, 255), bold)
        vw = draw.textbbox((0, 0), value, font=big)[2]
        if vw <= 92:
            draw_sharp_text(image, ((128 - vw) // 2, 6), value, (245, 250, 255), big)
        else:
            vw = draw.textbbox((0, 0), value, font=bold)[2]
            draw_sharp_text(image, ((128 - vw) // 2, 10), value, (245, 250, 255), bold)
        domain = entity_id.split(".")[0][:12].upper()
        draw_sharp_text(image, (2, 24), domain, (150, 170, 185), font)
        entity = entity_id.split(".")[-1].replace("_", " ")[:16].upper()
        ew = draw.textbbox((0, 0), entity, font=font)[2]
        draw_sharp_text(image, (126 - ew, 24), entity, (80, 105, 130), font)
        out = BytesIO()
        image.save(out, "WEBP", lossless=True, quality=100)
        return out.getvalue()

    draw.rectangle((0, 0, 63, 8), fill=(0, 20, 35))
    title = title[:12].upper()
    tw = draw.textbbox((0, 0), title, font=bold)[2]
    draw_sharp_text(image, ((64 - tw) // 2, -3), title, (65, 190, 255), bold)
    vw = draw.textbbox((0, 0), value, font=big)[2]
    if vw <= 62:
        draw_sharp_text(image, ((64 - vw) // 2, 6), value, (245, 250, 255), big)
    else:
        vw = draw.textbbox((0, 0), value, font=bold)[2]
        draw_sharp_text(image, ((64 - vw) // 2, 10), value, (245, 250, 255), bold)
    draw_sharp_text(image, (1, 24), entity_id.split(".")[0][:8].upper(), (150, 170, 185), font)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

