from datetime import datetime
from io import BytesIO
import math
import re
import urllib.parse

from card_utils import _settings_value, draw_sharp_text, fetch_json_request, render_text_webp

CARD_ID = "weather_radar_loop"
CARD_NAME = "Weather Radar Loop"
CARD_DETAIL = "Animated rain and snow sweep"
CARD_OPTIONS = [
    {"key": "zipCode", "label": "ZIP Code", "type": "text", "default": "", "maxlength": 5, "inputmode": "numeric"},
]
CARD_RULE_FIELDS = [
    {"id": "condition", "label": "Radar Condition"},
    {"id": "precip_mm", "label": "Precipitation mm"},
    {"id": "snow_mm", "label": "Snowfall mm"},
]

_CACHE = {}


def _normalize_zip(value):
    return re.sub(r"\D", "", value or "")[:5]


def _default_zip():
    return _normalize_zip(_settings_value("defaultZipCode", "") or "")


def _zip_latlon(zip_code):
    cached = _CACHE.get("zip:" + zip_code)
    now = datetime.utcnow()
    if cached and cached["expires"] > now:
        return cached["lat"], cached["lon"]
    loc = fetch_json_request(f"https://api.zippopotam.us/us/{zip_code}", seconds=86400)
    place = loc["places"][0]
    lat, lon = float(place["latitude"]), float(place["longitude"])
    _CACHE["zip:" + zip_code] = {"lat": lat, "lon": lon, "expires": now.replace(year=now.year + 1)}
    return lat, lon


def _radar_data(zip_code):
    lat, lon = _zip_latlon(zip_code)
    params = urllib.parse.urlencode({
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "hourly": "precipitation,snowfall,precipitation_probability",
        "forecast_days": 1,
        "timezone": "auto",
    })
    data = fetch_json_request(f"https://api.open-meteo.com/v1/forecast?{params}", seconds=600)
    hourly = data.get("hourly") or {}
    precip = [float(v or 0) for v in (hourly.get("precipitation") or [])[:8]]
    snow = [float(v or 0) for v in (hourly.get("snowfall") or [])[:8]]
    probs = [int(v or 0) for v in (hourly.get("precipitation_probability") or [])[:8]]
    max_precip = max(precip or [0])
    max_snow = max(snow or [0])
    max_prob = max(probs or [0])
    if max_snow >= 0.2 and max_snow >= max_precip * 0.6:
        kind = "snow"
    elif max_snow >= 0.2 and max_precip >= 0.2:
        kind = "mix"
    elif max_precip >= 0.1 or max_prob >= 35:
        kind = "rain"
    else:
        kind = "dry"
    intensity = max(max_precip, max_snow, max_prob / 45.0)
    return {
        "kind": kind,
        "precip": max_precip,
        "snow": max_snow,
        "prob": max_prob,
        "intensity": intensity,
        "zip": zip_code,
    }


def rule_value(options=None, field=""):
    opts = options or {}
    zip_code = _normalize_zip(opts.get("zipCode", "")) or _default_zip()
    if len(zip_code) != 5:
        return ""
    data = _radar_data(zip_code)
    key = str(field or "condition").strip()
    if key == "condition":
        return data["kind"]
    if key == "precip_mm":
        return round(data["precip"], 2)
    if key == "snow_mm":
        return round(data["snow"], 2)
    return ""


def _hash(x, y, seed):
    value = (x * 73856093) ^ (y * 19349663) ^ (seed * 83492791)
    value = (value ^ (value >> 13)) * 1274126177
    return (value ^ (value >> 16)) & 0xFF


def _band_color(kind, strength):
    strength = max(0.0, min(1.0, strength))
    if kind == "snow":
        return (
            int(90 + 120 * strength),
            int(165 + 75 * strength),
            255,
        )
    if kind == "mix":
        return (
            int(120 + 95 * strength),
            int(180 + 50 * strength),
            int(220 + 30 * strength),
        )
    if strength > 0.72:
        return (255, 218, 70)
    return (42, int(145 + 95 * strength), int(72 + 38 * strength))


def _draw_radar_frame(image, info, frame, font, bold):
    from PIL import ImageDraw

    width, height = image.size
    draw = ImageDraw.Draw(image)
    kind = info["kind"]
    intensity = max(0.0, min(2.5, info["intensity"]))
    cx = 18 if width == 64 else 28
    cy = 19
    radius = 18 if width == 64 else 24

    for y in range(0, height, 4):
        for x in range(0, width, 4):
            if _hash(x, y, frame) > 215:
                draw.point((x, y), fill=(0, 18, 24))

    for r in (7, 13, 19, 25):
        if r <= radius:
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(8, 42, 48))
    draw.line((cx - radius, cy, cx + radius, cy), fill=(5, 34, 40))
    draw.line((cx, cy - radius, cx, cy + radius), fill=(5, 34, 40))
    draw.rectangle((cx - 1, cy - 1, cx + 1, cy + 1), fill=(118, 245, 210))

    sweep = (frame * 14) % 360
    sx = cx + int(math.cos(math.radians(sweep)) * radius)
    sy = cy + int(math.sin(math.radians(sweep)) * radius)
    draw.line((cx, cy, sx, sy), fill=(42, 238, 190))

    if kind != "dry":
        bands = 4 + min(5, int(round(intensity * 2)))
        for i in range(bands):
            base = i * 17 + frame * (2 + i % 3)
            bx = ((base * 3) % (width + 36)) - 28
            by = 8 + ((i * 11 + frame) % 18)
            bw = 18 + (_hash(i, 3, frame) % 18)
            bh = 3 + (_hash(i, 7, frame) % 5)
            strength = min(1.0, 0.3 + intensity / 2.2 + (_hash(i, 13, frame) / 255.0) * 0.25)
            color = _band_color(kind, strength)
            for step in range(0, bw, 4):
                x = bx + step
                y = by + int(math.sin((step + frame + i) / 4.0) * 4)
                draw.rectangle((x, y, x + 5, y + bh), fill=color)

    if width == 128:
        panel_x = 61
        draw.rectangle((panel_x, 0, 127, 31), fill=(0, 7, 13))
        draw.line((panel_x - 2, 2, panel_x - 2, 29), fill=(16, 52, 62))
        title = {"dry": "DRY", "rain": "RAIN", "snow": "SNOW", "mix": "MIX"}[kind]
        title_color = (90, 238, 170) if kind in ("rain", "mix") else (150, 210, 255) if kind == "snow" else (120, 145, 160)
        draw_sharp_text(image, (panel_x + 3, -3), "RADAR", (118, 245, 210), bold)
        draw_sharp_text(image, (panel_x + 3, 8), title, title_color, bold)
        detail = f"{info['prob']}% {info['precip']:.1f}MM"
        if kind == "snow":
            detail = f"{info['prob']}% {info['snow']:.1f}SN"
        draw_sharp_text(image, (panel_x + 3, 19), detail[:12], (210, 230, 238), font)
    else:
        draw.rectangle((0, 0, 63, 8), fill=(0, 8, 14))
        label = {"dry": "RADAR DRY", "rain": "RADAR RAIN", "snow": "RADAR SNOW", "mix": "RADAR MIX"}[kind]
        draw_sharp_text(image, (1, -3), label[:11], (118, 245, 210), font)


def _render_animation(info, width, dwell_secs):
    from PIL import Image, ImageFont

    dwell_ms = max(3000, min(60000, int(dwell_secs or 10) * 1000))
    frame_count = max(18, min(42 if width == 64 else 34, int(round(dwell_ms / 180))))
    frame_duration = max(45, int(round(dwell_ms / frame_count)))
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    frames = []
    for frame in range(frame_count):
        image = Image.new("RGB", (width, 32), (0, 4, 8))
        _draw_radar_frame(image, info, frame, font, bold)
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


def render(options=None):
    opts = options or {}
    zip_code = _normalize_zip(opts.get("zipCode", "")) or _default_zip()
    if len(zip_code) != 5:
        return render_text_webp("SET ZIP", (100, 180, 255))
    try:
        info = _radar_data(zip_code)
    except Exception:
        return render_text_webp("RADAR ERR", (238, 80, 80))
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    return _render_animation(info, width, opts.get("_dwell", 10))
