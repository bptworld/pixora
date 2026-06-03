from io import BytesIO
from card_utils import _settings_value, draw_sharp_text, fetch_json_request, openweather_alerts_for_zip, render_text_webp

CARD_ID = "weather_alert"
CARD_NAME = "Weather Alert"
CARD_DETAIL = "Skips when clear"
CARD_OPTIONS = [
    {"key": "zipCode", "label": "ZIP Code", "type": "text", "default": "10001", "maxlength": 5, "inputmode": "numeric"},
]


def _zip_latlon(zip_code):
    loc = fetch_json_request(f"https://api.zippopotam.us/us/{zip_code}", seconds=86400)
    p = loc["places"][0]
    return float(p["latitude"]), float(p["longitude"])


def _default_zip():
    import re

    return re.sub(r"\D", "", _settings_value("defaultZipCode", "") or "")[:5]


def _severity_color(severity):
    sev = (severity or "").lower()
    if sev == "extreme":
        return (255, 60, 90)
    if sev == "severe":
        return (255, 95, 70)
    if sev == "moderate":
        return (255, 190, 70)
    return (255, 230, 90)


def _short_event(event):
    text = (event or "Weather Alert").upper()
    for word in ("WARNING", "WATCH", "ADVISORY", "STATEMENT"):
        text = text.replace(word, word[:4])
    return " ".join(text.split())[:14]


def _fit(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1]
    return text


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    zip_code = (opts.get("zipCode") or "").strip() or _default_zip()
    if len(zip_code) != 5:
        return render_text_webp("SET ZIP", (100, 180, 255))

    alerts = None
    try:
        alerts = openweather_alerts_for_zip(zip_code)
    except Exception:
        alerts = None
    if alerts is None:
        try:
            lat, lon = _zip_latlon(zip_code)
            data = fetch_json_request(f"https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}", seconds=120)
            alerts = data.get("features") or []
        except Exception:
            alerts = []

    if not alerts:
        return None

    props = alerts[0].get("properties", {})
    event = _short_event(props.get("event"))
    severity = props.get("severity", "")
    color = _severity_color(severity)

    is_wide = opts.get("_target") == "matrixportal-s3-128x32"
    width = 128 if is_wide else 64
    image = Image.new("RGB", (width, 32), (18, 6, 0))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    draw.rectangle((0, 0, width - 1, 8), fill=(45, 14, 0))
    title = "WEATHER ALERT" if is_wide else "WX ALERT"
    draw_sharp_text(image, (1, -3), title, color, bold)
    icon_x = width - 16
    draw.ellipse((icon_x, 10, icon_x + 10, 20), outline=color)
    draw.arc((icon_x - 7, 3, icon_x + 17, 27), 205, 335, fill=(80, 110, 130))
    draw.arc((icon_x - 11, -1, icon_x + 21, 31), 205, 335, fill=(45, 70, 90))
    draw.polygon([(icon_x + 5, 7), (icon_x - 1, 20), (icon_x + 6, 17), (icon_x + 1, 28), (icon_x + 13, 13), (icon_x + 6, 15)], fill=(255, 230, 80))
    if is_wide:
        event = _fit(draw, (props.get("event") or "Weather Alert").upper(), font, 105)
    draw_sharp_text(image, (1, 10), event, (245, 245, 245), font)
    sev = (severity or "Alert").upper()[:8]
    draw_sharp_text(image, (1, 21), sev, color, font)
    if len(alerts) > 1:
        draw_sharp_text(image, (width - 15, 21), f"+{len(alerts)-1}", (210, 220, 225), font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

