from io import BytesIO
import re

from card_utils import _settings_value, draw_sharp_text, weather_for_zip

CARD_ID = "weather_mood"
CARD_NAME = "Weather Mood"
CARD_DETAIL = "Animated current weather scene"
CARD_OPTIONS = [
    {"key": "zipCode", "label": "ZIP", "type": "text", "default": "", "maxlength": 5, "inputmode": "numeric"},
]


def _normalize_zip(value):
    return re.sub(r"\D", "", value or "")[:5]


def _default_zip():
    return _normalize_zip(_settings_value("defaultZipCode", "") or "")


def _weather(zip_code):
    try:
        weather = weather_for_zip(zip_code)
    except Exception:
        weather = {}
    text = str((weather.get("icon") or "") + " " + (weather.get("shortForecast") or "")).lower()
    if any(x in text for x in ("snow", "sleet", "ice")):
        kind = "snow"
    elif any(x in text for x in ("rain", "storm", "shower", "drizzle", "thunder")):
        kind = "storm" if "thunder" in text or "storm" in text else "rain"
    elif any(x in text for x in ("cloud", "fog", "mist", "haze", "partly")):
        kind = "cloud"
    else:
        kind = "sun"
    label = {
        "sun": "SUNNY",
        "cloud": "CLOUDS",
        "rain": "RAIN",
        "storm": "STORM",
        "snow": "SNOW",
    }[kind]
    return {
        "kind": kind,
        "label": label,
        "temp": weather.get("temperature", "--"),
        "unit": weather.get("temperatureUnit", _settings_value("temperatureUnits", "F") or "F"),
    }


def _cloud(draw, x, y, shade=0, scale=1):
    c1 = (95 + shade, 118 + shade, 138 + shade)
    c2 = (130 + shade, 150 + shade, 166 + shade)
    draw.ellipse((x, y + 5 * scale, x + 12 * scale, y + 15 * scale), fill=c1)
    draw.ellipse((x + 7 * scale, y, x + 23 * scale, y + 16 * scale), fill=c2)
    draw.ellipse((x + 18 * scale, y + 4 * scale, x + 31 * scale, y + 16 * scale), fill=c1)
    draw.rectangle((x + 2 * scale, y + 10 * scale, x + 30 * scale, y + 18 * scale), fill=c2)


def _sun(draw, cx, cy, frame, radius=8):
    pulse = frame % 4
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(255, 204, 46))
    for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1)):
        r = radius + 4 + pulse
        draw.line((cx + dx * (radius + 1), cy + dy * (radius + 1), cx + dx * r, cy + dy * r), fill=(255, 236, 110))


def _draw_text(image, width, info, font, bold):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    temp = f"{info['temp']}{str(info['unit'])[:1]}"
    if width == 128:
        draw.rectangle((0, 0, 127, 8), fill=(4, 16, 28))
        draw_sharp_text(image, (2, -3), info["label"], (120, 220, 255), bold)
        tw = draw.textbbox((0, 0), temp, font=bold)[2]
        draw_sharp_text(image, (126 - tw, -3), temp, (245, 250, 255), bold)
    else:
        draw.rectangle((0, 0, 63, 8), fill=(4, 16, 28))
        label = info["label"][:7]
        draw_sharp_text(image, (1, -3), label, (120, 220, 255), bold)
        tw = draw.textbbox((0, 0), temp, font=font)[2]
        draw_sharp_text(image, (63 - tw, -3), temp, (245, 250, 255), font)


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    zip_code = _normalize_zip(opts.get("zipCode", "")) or _default_zip()
    info = _weather(zip_code)
    kind = info["kind"]
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    dwell_ms = max(3000, min(60000, int(opts.get("_dwell", 10) or 10) * 1000))
    # Keep animated cards light enough for the ESP32-S3 decoder. The 128-wide
    # panel doubles the pixels per frame, so it gets fewer frames with a longer
    # frame duration instead of a huge 90-frame WebP.
    max_frames = 32 if width == 128 else 45
    frame_count = max(16, min(max_frames, int(round(dwell_ms / 180))))
    frame_duration = max(35, int(round(dwell_ms / frame_count)))
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    frames = []
    for frame in range(frame_count):
        bg = {
            "sun": (2, 20, 46),
            "cloud": (2, 14, 30),
            "rain": (0, 8, 22),
            "storm": (2, 5, 18),
            "snow": (3, 12, 24),
        }[kind]
        image = Image.new("RGB", (width, 32), bg)
        draw = ImageDraw.Draw(image)

        if kind == "sun":
            _sun(draw, width - 18, 19, frame, 8)
            for i in range(0, width, 9):
                y = 27 + ((frame + i) % 3)
                draw.point((i, y), fill=(35, 120, 180))
        elif kind == "cloud":
            drift = (frame // 3) % 8
            _sun(draw, width - 15, 15, frame, 5)
            _cloud(draw, 5 + drift, 10, 12, 1)
            if width == 128:
                _cloud(draw, 62 - drift, 12, -8, 1)
        elif kind in ("rain", "storm"):
            drift = (frame // 4) % 6
            _cloud(draw, 5 + drift, 7, -18 if kind == "storm" else 0, 1)
            if width == 128:
                _cloud(draw, 54 - drift, 8, -12 if kind == "storm" else 8, 1)
            for x in range(3, width, 7):
                y = 9 + ((frame * 3 + x) % 23)
                draw.line((x, y, x - 2, y + 4), fill=(72, 174, 255))
            if kind == "storm" and frame % 10 in (0, 1, 2):
                bx = width - 26
                draw.polygon([(bx, 9), (bx - 5, 20), (bx + 1, 18), (bx - 4, 30), (bx + 8, 14), (bx + 2, 16)], fill=(255, 230, 65))
        else:
            _cloud(draw, 7, 7, 20, 1)
            if width == 128:
                _cloud(draw, 62, 8, 4, 1)
            for x in range(2, width, 6):
                y = 10 + ((frame * 2 + x) % 22)
                draw.point((x, y), fill=(235, 250, 255))
                if x % 12 == 2:
                    draw.point((x + 1, y), fill=(235, 250, 255))

        _draw_text(image, width, info, font, bold)
        frames.append(image)

    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=frame_duration,
        loop=1,
        lossless=True,
        quality=100,
    )
    return out.getvalue()
