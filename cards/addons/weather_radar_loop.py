from datetime import datetime, timedelta
from io import BytesIO
import math
import re
import urllib.request

from card_utils import _settings_value, draw_sharp_text, fetch_json_request, render_text_webp

CARD_ID = "weather_radar_loop"
CARD_NAME = "Weather Radar Loop"
CARD_DETAIL = "Live RainViewer radar loop"
CARD_ATTRIBUTION = {
    "label": "Radar data by RainViewer",
    "url": "https://www.rainviewer.com/",
}
CARD_OPTIONS = [
    {"key": "zipCode", "label": "ZIP Code", "type": "text", "default": "", "maxlength": 5, "inputmode": "numeric"},
]
CARD_RULE_FIELDS = [
    {"id": "condition", "label": "Radar Condition"},
    {"id": "precip_mm", "label": "Precipitation mm"},
    {"id": "snow_mm", "label": "Snowfall mm"},
]

_CACHE = {}
_RAINVIEWER_URL = "https://api.rainviewer.com/public/weather-maps.json"
_RAINVIEWER_USER_AGENT = "Pixora/1.0 (RainViewer radar card)"
_RAINVIEWER_TILE_TIMEOUT = 2.0


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


def _rainviewer_timeline():
    data = fetch_json_request(_RAINVIEWER_URL, seconds=300)
    host = str(data.get("host") or "https://tilecache.rainviewer.com").rstrip("/")
    radar = data.get("radar") or {}
    frames = list(radar.get("past") or [])
    frames.extend(list(radar.get("nowcast") or []))
    frames = [frame for frame in frames if frame.get("path")]
    frames.sort(key=lambda frame: int(frame.get("time") or 0))
    return host, frames


def _fetch_tile(url):
    cached = _CACHE.get("tile:" + url)
    now = datetime.utcnow()
    if cached and cached["expires"] > now:
        return cached["image"].copy()
    from PIL import Image

    request = urllib.request.Request(url, headers={"User-Agent": _RAINVIEWER_USER_AGENT})
    with urllib.request.urlopen(request, timeout=_RAINVIEWER_TILE_TIMEOUT) as response:
        body = response.read()
    image = Image.open(BytesIO(body)).convert("RGBA")
    _CACHE["tile:" + url] = {"image": image.copy(), "expires": now + timedelta(minutes=5)}
    return image


def _radar_frames(zip_code, width):
    lat, lon = _zip_latlon(zip_code)
    host, timeline = _rainviewer_timeline()
    if not timeline:
        return {
            "kind": "dry",
            "precip": 0,
            "snow": 0,
            "prob": 0,
            "intensity": 0,
            "zip": zip_code,
            "frames": [],
            "source": "RainViewer",
        }

    # Keep the matrix loop light while showing enough radar history to feel
    # like a real loop. A lat/lon tile keeps the chosen ZIP centered without
    # doing map math locally.
    max_frames = 6 if width <= 64 else 8
    selected = timeline[-max_frames:] if len(timeline) >= max_frames else timeline
    tile_size = 256
    zoom = 7
    color = 2
    options = "1_1"
    radar_width = 58 if width == 128 else width
    output_frames = []
    max_signal = 0
    for index, frame in enumerate(selected):
        path = str(frame.get("path") or "")
        tile_url = f"{host}{path}/{tile_size}/{zoom}/{lat:.4f}/{lon:.4f}/{color}/{options}.png"
        try:
            tile = _fetch_tile(tile_url)
        except Exception:
            continue
        output_frames.append(_matrix_radar_image(tile, radar_width, index))
        signal, _ = _radar_signal(tile)
        max_signal = max(max_signal, signal)

    if max_signal < 3:
        kind = "dry"
    else:
        kind = "rain"

    return {
        "kind": kind,
        "precip": round(max_signal / 100.0, 2),
        "snow": 0,
        "prob": min(100, int(round(max_signal))),
        "intensity": min(2.5, max_signal / 35.0),
        "zip": zip_code,
        "frames": output_frames,
        "source": "RainViewer",
        "updated": int(selected[-1].get("time") or 0),
    }


def _radar_data(zip_code):
    return _radar_frames(zip_code, 64)


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


def _radar_signal(tile):
    signal = 0
    snow = 0
    sample = tile.resize((32, 32))
    pixels = sample.convert("RGBA").getdata()
    for r, g, b, a in pixels:
        if a < 18:
            continue
        value = max(r, g, b)
        if value < 22:
            continue
        signal += min(4, max(1, value // 64))
        if b > r + 16 and b > g:
            snow += min(4, max(1, b // 64))
    total = max(1, len(pixels))
    return min(100, signal * 100 / total), min(100, snow * 100 / total)


def _matrix_radar_image(tile, width, seed=0):
    from PIL import Image, ImageDraw

    radar = Image.new("RGB", (width, 32), (0, 4, 8))
    # Use the center of RainViewer's lat/lon tile, where the ZIP is anchored.
    crop_w = 196
    crop_h = 126
    left = (tile.width - crop_w) // 2
    top = (tile.height - crop_h) // 2
    resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
    crop = tile.crop((left, top, left + crop_w, top + crop_h)).resize((width, 32), resample)
    rgba = crop.convert("RGBA")
    bg = Image.new("RGBA", (width, 32), (0, 4, 8, 255))
    bg.alpha_composite(rgba)
    radar = bg.convert("RGB")
    draw = ImageDraw.Draw(radar)
    cx, cy = width // 2, 16
    draw.rectangle((cx - 1, cy - 1, cx + 1, cy + 1), outline=(230, 245, 255))
    draw.line((cx - 5, cy, cx - 2, cy), fill=(120, 150, 160))
    draw.line((cx + 2, cy, cx + 5, cy), fill=(120, 150, 160))
    draw.line((cx, cy - 5, cx, cy - 2), fill=(120, 150, 160))
    draw.line((cx, cy + 2, cx, cy + 5), fill=(120, 150, 160))
    for y in range(0, 32, 6):
        for x in range(0, width, 6):
            if _hash(x, y, seed) > 235:
                draw.point((x, y), fill=(0, 22, 28))
    return radar


def _draw_radar_frame(image, info, frame, font, bold):
    from PIL import ImageDraw

    width, height = image.size
    draw = ImageDraw.Draw(image)
    kind = info["kind"]
    radar_frames = info.get("frames") or []
    radar_width = 58 if width == 128 else width
    if radar_frames:
        radar = radar_frames[frame % len(radar_frames)]
        image.paste(radar, (0, 0))
    else:
        for y in range(0, height, 4):
            for x in range(0, radar_width, 4):
                if _hash(x, y, frame) > 215:
                    draw.point((x, y), fill=(0, 18, 24))

    cx = radar_width // 2
    cy = 19
    radius = 17 if width == 64 else 24

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

    if width == 128:
        panel_x = 61
        draw.rectangle((panel_x, 0, 127, 31), fill=(0, 7, 13))
        draw.line((panel_x - 2, 2, panel_x - 2, 29), fill=(16, 52, 62))
        title = {"dry": "DRY", "rain": "RAIN", "snow": "SNOW", "mix": "MIX"}[kind]
        title_color = (90, 238, 170) if kind in ("rain", "mix") else (150, 210, 255) if kind == "snow" else (120, 145, 160)
        draw_sharp_text(image, (panel_x + 3, -3), "RADAR", (118, 245, 210), bold)
        draw_sharp_text(image, (panel_x + 3, 8), title, title_color, bold)
        detail = f"LIVE {info['prob']}%"
        if kind == "snow":
            detail = f"SNOW {info['prob']}%"
        draw_sharp_text(image, (panel_x + 3, 19), detail[:12], (210, 230, 238), font)
    else:
        draw.rectangle((0, 0, 63, 6), fill=(0, 8, 14))
        label = {"dry": "RADAR DRY", "rain": "RADAR RAIN", "snow": "RADAR SNOW", "mix": "RADAR MIX"}[kind]
        draw_sharp_text(image, (1, -3), label[:11], (118, 245, 210), font)


def _render_animation(info, width, dwell_secs):
    from PIL import Image, ImageFont

    dwell_ms = max(3000, min(60000, int(dwell_secs or 10) * 1000))
    source_frames = info.get("frames") or []
    frame_count = len(source_frames) if source_frames else max(10, min(24, int(round(dwell_ms / 240))))
    frame_duration = 180 if source_frames else 120
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
        width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
        info = _radar_frames(zip_code, width)
    except Exception:
        return render_text_webp("RADAR ERR", (238, 80, 80))
    return _render_animation(info, width, opts.get("_dwell", 10))
