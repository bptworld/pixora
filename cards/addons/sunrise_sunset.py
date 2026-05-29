from datetime import datetime, timezone
from io import BytesIO

from card_utils import draw_sharp_text, fetch_json_request, format_time, openweather_sun_times_for_zip, render_text_webp

CARD_ID = "sunrise_sunset"
CARD_NAME = "Sunrise / Sunset"
CARD_DETAIL = "Sun and daylight times by ZIP"
CARD_OPTIONS = [
    {"key": "zipCode", "label": "ZIP Code", "type": "text", "default": "01826", "maxlength": 5, "inputmode": "numeric"},
    {
        "key": "mode",
        "label": "Show",
        "type": "select",
        "default": "both",
        "choices": [
            {"value": "both", "label": "Sunrise and sunset"},
            {"value": "sunrise", "label": "Sunrise only"},
            {"value": "sunset", "label": "Sunset only"},
        ],
    },
]


def _location_for_zip(zip_code):
    zip_code = "".join(ch for ch in str(zip_code or "") if ch.isdigit())[:5]
    if len(zip_code) != 5:
        raise ValueError("ZIP needed")
    data = fetch_json_request(f"https://api.zippopotam.us/us/{zip_code}", seconds=86400)
    place = data["places"][0]
    return place["latitude"], place["longitude"]


def _time_label(value):
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    return format_time(dt)


def _sun_data(zip_code):
    try:
        owm = openweather_sun_times_for_zip(zip_code)
    except Exception:
        owm = None
    if owm:
        return _time_label(owm[0]), _time_label(owm[1])
    lat, lon = _location_for_zip(zip_code)
    data = fetch_json_request(
        f"https://api.sunrise-sunset.org/json?lat={lat}&lng={lon}&formatted=0",
        seconds=3600,
    )
    results = data.get("results", {})
    return _time_label(results["sunrise"]), _time_label(results["sunset"])


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    try:
        sunrise, sunset = _sun_data(opts.get("zipCode", "01826"))
    except Exception:
        return render_text_webp("SUN ERR", (255, 190, 80))

    image = Image.new("RGB", (width, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    icon_x = 14 if width == 128 else 5
    draw.ellipse((icon_x, 10, icon_x + 14, 24), fill=(255, 196, 58))
    for line in [(icon_x + 7, 6, icon_x + 7, 8), (icon_x + 7, 26, icon_x + 7, 29), (icon_x - 4, 17, icon_x - 1, 17), (icon_x + 15, 17, icon_x + 18, 17)]:
        draw.line(line, fill=(255, 226, 110))
    draw.line((icon_x - 3, 28, icon_x + 19, 28), fill=(60, 180, 225))

    mode = opts.get("mode", "both")
    if mode == "sunrise":
        rows = [("RISE", sunrise, (255, 210, 80))]
    elif mode == "sunset":
        rows = [("SET", sunset, (255, 125, 80))]
    else:
        rows = [("RISE", sunrise, (255, 210, 80)), ("SET", sunset, (255, 125, 80))]

    x = 54 if width == 128 else 27
    y = -2 if len(rows) == 2 else 2
    for label, value, color in rows:
        draw_sharp_text(image, (x, y), label, color, font)
        draw_sharp_text(image, (x, y + 8), value, (235, 245, 255), bold)
        y += 16

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

