from datetime import datetime, timedelta, timezone
from io import BytesIO
import math
import re
import urllib.parse

from card_utils import (
    _settings_value,
    draw_pixora_bold_number,
    fetch_json_request,
    fetch_json_with_headers,
    pixora_bold_number_size,
    render_text_webp,
)


CARD_ID = "meteor_watch"
CARD_NAME = "Meteor Watch"
CARD_DETAIL = "Meteor showers and tonight sky score"
CARD_OPTIONS = [
    {"key": "zipCode", "label": "ZIP Code", "type": "text", "default": "", "maxlength": 5, "inputmode": "numeric"},
    {
        "key": "mode",
        "label": "Mode",
        "type": "select",
        "default": "auto",
        "choices": [
            {"value": "auto", "label": "Auto"},
            {"value": "score", "label": "Tonight score"},
            {"value": "shower", "label": "Meteor shower"},
        ],
    },
]


_SHOWERS = [
    {"name": "QUADRANTIDS", "short": "QUADS", "start": (12, 28), "peak": (1, 3), "end": (1, 12), "zhr": 80},
    {"name": "LYRIDS", "short": "LYRIDS", "start": (4, 16), "peak": (4, 22), "end": (4, 25), "zhr": 18},
    {"name": "ETA AQUARIIDS", "short": "ETA AQU", "start": (4, 19), "peak": (5, 6), "end": (5, 28), "zhr": 50},
    {"name": "SOUTH DELTA AQUARIIDS", "short": "S DELTA", "start": (7, 12), "peak": (7, 30), "end": (8, 23), "zhr": 25},
    {"name": "PERSEIDS", "short": "PERSEID", "start": (7, 17), "peak": (8, 12), "end": (8, 24), "zhr": 100},
    {"name": "ORIONIDS", "short": "ORIONID", "start": (10, 2), "peak": (10, 21), "end": (11, 7), "zhr": 20},
    {"name": "SOUTH TAURIDS", "short": "S TAUR", "start": (9, 10), "peak": (11, 5), "end": (11, 20), "zhr": 5},
    {"name": "NORTH TAURIDS", "short": "N TAUR", "start": (10, 20), "peak": (11, 12), "end": (12, 10), "zhr": 5},
    {"name": "LEONIDS", "short": "LEONID", "start": (11, 6), "peak": (11, 17), "end": (11, 30), "zhr": 15},
    {"name": "GEMINIDS", "short": "GEMINID", "start": (12, 4), "peak": (12, 14), "end": (12, 20), "zhr": 120},
    {"name": "URSIDS", "short": "URSIDS", "start": (12, 17), "peak": (12, 22), "end": (12, 26), "zhr": 10},
]


_PIXEL = {
    "A": ("010", "101", "111", "101", "101"),
    "B": ("110", "101", "110", "101", "110"),
    "C": ("011", "100", "100", "100", "011"),
    "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"),
    "F": ("111", "100", "110", "100", "100"),
    "G": ("011", "100", "101", "101", "011"),
    "H": ("101", "101", "111", "101", "101"),
    "I": ("111", "010", "010", "010", "111"),
    "J": ("001", "001", "001", "101", "010"),
    "K": ("101", "101", "110", "101", "101"),
    "L": ("100", "100", "100", "100", "111"),
    "M": ("101", "111", "111", "101", "101"),
    "N": ("101", "111", "111", "111", "101"),
    "O": ("010", "101", "101", "101", "010"),
    "P": ("110", "101", "110", "100", "100"),
    "Q": ("010", "101", "101", "111", "011"),
    "R": ("110", "101", "110", "101", "101"),
    "S": ("011", "100", "010", "001", "110"),
    "T": ("111", "010", "010", "010", "010"),
    "U": ("101", "101", "101", "101", "111"),
    "V": ("101", "101", "101", "101", "010"),
    "W": ("101", "101", "111", "111", "101"),
    "X": ("101", "101", "010", "101", "101"),
    "Y": ("101", "101", "010", "010", "010"),
    "Z": ("111", "001", "010", "100", "111"),
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("110", "001", "010", "100", "111"),
    "3": ("110", "001", "010", "001", "110"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "110", "001", "110"),
    "6": ("011", "100", "110", "101", "010"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("010", "101", "010", "101", "010"),
    "9": ("010", "101", "011", "001", "110"),
    "/": ("001", "001", "010", "100", "100"),
    "%": ("101", "001", "010", "100", "101"),
    "-": ("000", "000", "111", "000", "000"),
}


def _pixel_width(text, spacing=1):
    width = 0
    for ch in str(text or "").upper():
        if ch == " ":
            char_width = 2
        else:
            glyph = _PIXEL.get(ch)
            char_width = len(glyph[0]) if glyph else 3
        width += char_width + spacing
    return max(0, width - spacing)


def _pixel_fit(text, max_width):
    text = str(text or "").upper()
    while text and _pixel_width(text) > max_width:
        text = text[:-1].rstrip()
    return text or "-"


def _draw_pixel_text(draw, xy, text, color, spacing=1):
    x, y = xy
    for ch in str(text or "").upper():
        if ch == " ":
            x += 2 + spacing
            continue
        glyph = _PIXEL.get(ch)
        if not glyph:
            x += 3 + spacing
            continue
        for gy, row in enumerate(glyph):
            for gx, pixel in enumerate(row):
                if pixel == "1":
                    draw.point((x + gx, y + gy), fill=color)
        x += len(glyph[0]) + spacing


def _webp(image):
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _webp_frames(frames, duration=120):
    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=1,
        lossless=True,
        quality=100,
    )
    return out.getvalue()


def _option_setting(opts, key, default=""):
    opts = opts or {}
    settings = opts.get("_settings") if isinstance(opts.get("_settings"), dict) else {}
    value = settings.get(key)
    if value not in (None, ""):
        return value
    return _settings_value(key, default)


def _clean_zip(opts):
    value = re.sub(r"\D", "", str((opts or {}).get("zipCode") or ""))[:5]
    if value:
        return value
    return re.sub(r"\D", "", str(_option_setting(opts, "defaultZipCode", "") or ""))[:5]


def _location(zip_code, opts=None):
    if len(zip_code) != 5:
        lat = str(_option_setting(opts, "defaultLatitude", "") or "").strip()
        lon = str(_option_setting(opts, "defaultLongitude", "") or "").strip()
        if lat and lon:
            return float(lat), float(lon)
        raise ValueError("location")
    data = fetch_json_request(f"https://api.zippopotam.us/us/{zip_code}", seconds=86400)
    place = data["places"][0]
    return float(place["latitude"]), float(place["longitude"])


def _log(opts, message):
    logger = (opts or {}).get("_log")
    if callable(logger):
        try:
            logger(message)
        except Exception:
            pass


def _nws_cloud_cover(lat, lon):
    headers = {"User-Agent": "Pixora/1.0 support@pixorahq.com", "Accept": "application/geo+json, application/json"}
    point = fetch_json_with_headers(
        f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}",
        headers=headers,
        seconds=86400,
        cache_key=f"meteor:nws:point:{lat:.3f}:{lon:.3f}",
    )
    grid_url = ((point.get("properties") or {}).get("forecastGridData") or "") if isinstance(point, dict) else ""
    if not grid_url:
        return None
    grid = fetch_json_with_headers(
        grid_url,
        headers=headers,
        seconds=1800,
        cache_key=f"meteor:nws:grid:{lat:.3f}:{lon:.3f}",
    )
    values = (((grid.get("properties") or {}).get("skyCover") or {}).get("values") or []) if isinstance(grid, dict) else []
    nums = [float(item.get("value")) for item in values[:8] if isinstance(item, dict) and isinstance(item.get("value"), (int, float))]
    if not nums:
        return None
    return int(round(sum(nums) / len(nums)))


def _cloud_cover(lat, lon, opts=None):
    params = urllib.parse.urlencode({
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "current": "cloud_cover",
        "hourly": "cloud_cover",
        "forecast_days": 1,
        "timezone": "auto",
    })
    try:
        data = fetch_json_with_headers(
            "https://api.open-meteo.com/v1/forecast?" + params,
            headers={"User-Agent": "Pixora/1.0 meteor_watch"},
            seconds=1800,
            cache_key=f"meteor:cloud:{lat:.3f}:{lon:.3f}",
        )
        current = ((data.get("current") or {}).get("cloud_cover")) if isinstance(data, dict) else None
        if isinstance(current, (int, float)):
            return int(round(float(current)))
        values = ((data.get("hourly") or {}).get("cloud_cover") or []) if isinstance(data, dict) else []
        nums = [float(v) for v in values if isinstance(v, (int, float))]
        if nums:
            return int(round(sum(nums) / len(nums)))
    except Exception as exc:
        _log(opts, f"open-meteo cloud failed: {exc}")
    try:
        fallback = _nws_cloud_cover(lat, lon)
        if fallback is not None:
            return fallback
    except Exception as exc:
        _log(opts, f"nws cloud failed: {exc}")
    return None


def _month_day(year, value):
    return datetime(year, value[0], value[1], tzinfo=timezone.utc).date()


def _window_for_year(shower, year):
    start = _month_day(year, shower["start"])
    peak = _month_day(year, shower["peak"])
    end = _month_day(year, shower["end"])
    if start > end:
        if peak < start:
            peak = _month_day(year + 1, shower["peak"])
            end = _month_day(year + 1, shower["end"])
    return start, peak, end


def _shower_status(today=None):
    today = today or datetime.now(timezone.utc).date()
    active = []
    upcoming = []
    for shower in _SHOWERS:
        for year in (today.year - 1, today.year, today.year + 1):
            start, peak, end = _window_for_year(shower, year)
            if start <= today <= end:
                active.append((abs((peak - today).days), peak, shower))
            elif peak >= today:
                upcoming.append(((peak - today).days, peak, shower))
    if active:
        active.sort(key=lambda item: (-item[2]["zhr"], item[0]))
        dist, peak, shower = active[0]
        return {**shower, "active": True, "days": (peak - today).days, "peak_date": peak}
    upcoming.sort(key=lambda item: item[0])
    days, peak, shower = upcoming[0]
    return {**shower, "active": False, "days": days, "peak_date": peak}


def _moon_illumination(now=None):
    now = now or datetime.now(timezone.utc)
    known_new = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    days = (now - known_new).total_seconds() / 86400.0
    age = days % 29.53058867
    phase = age / 29.53058867
    illum = (1 - math.cos(2 * math.pi * phase)) / 2
    return int(round(illum * 100)), age


def _score(shower, cloud, moon):
    cloud_penalty = (cloud if cloud is not None else 45) * 0.45
    moon_penalty = moon * 0.25
    shower_bonus = min(35, shower["zhr"] * (0.22 if shower.get("active") else 0.08))
    if shower.get("active"):
        shower_bonus += max(0, 12 - abs(shower.get("days", 0)) * 3)
    score = int(round(72 + shower_bonus - cloud_penalty - moon_penalty))
    return max(0, min(99, score))


def _data(opts):
    zip_code = _clean_zip(opts)
    cloud = None
    try:
        lat, lon = _location(zip_code, opts)
        cloud = _cloud_cover(lat, lon, opts)
    except Exception as exc:
        _log(opts, f"meteor location/cloud failed zip={zip_code or '-'}: {exc}")
        pass
    shower = _shower_status()
    moon, age = _moon_illumination()
    return {"zip": zip_code, "cloud": cloud, "moon": moon, "moon_age": age, "shower": shower, "score": _score(shower, cloud, moon)}


def _score_color(score):
    if score >= 75:
        return (95, 230, 135)
    if score >= 50:
        return (255, 220, 90)
    return (255, 100, 100)


def _draw_score_number(draw, score, x, y, color, scale=2):
    text = str(score)
    w, _h = pixora_bold_number_size(text, scale=scale, spacing=1)
    draw_pixora_bold_number(draw, (x - w // 2, y), text, color, scale=scale, spacing=1)


def _draw_stars(draw, width, offset=0):
    stars = [(4, 3), (54, 4), (75, 4), (101, 8), (119, 25)]
    for x, y in stars:
        if x < width:
            draw.point((x, y), fill=(88, 130, 165) if (x + y + offset) % 3 else (150, 200, 230))


def _draw_fireball(draw, width, height, step, total):
    t = step / max(1, total - 1)
    x = int(round(width + 4 - t * (width + 18)))
    y = int(round(7 + t * (height + 4)))
    radius = 1 + int(round(t * 5))
    tail = [
        (4, -2, (95, 230, 255)),
        (8, -4, (60, 180, 225)),
        (12, -6, (34, 120, 170)),
        (16, -8, (18, 72, 112)),
    ]
    for dx, dy, color in reversed(tail):
        px, py = x + dx, y + dy
        if -2 <= px < width + 2 and -2 <= py < height + 2:
            draw.rectangle((px, py, px + 1, py + 1), fill=color)
    flame = (255, 190, 75) if radius >= 3 else (95, 230, 255)
    glow = (255, 90, 80) if radius >= 3 else (80, 210, 240)
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=glow)
    inner = max(1, radius - 1)
    draw.ellipse((x - inner, y - inner, x + inner, y + inner), fill=flame)
    draw.point((x - 1, y - 1), fill=(255, 255, 255))


def _draw_header(draw, width, title="METEOR WATCH"):
    draw.rectangle((0, 0, width - 1, 6), fill=(5, 25, 38))
    _draw_pixel_text(draw, (1, 1), title, (120, 245, 255))


def _render_64(data, mode, meteor_step=0, meteor_total=1):
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (64, 32), (1, 5, 18))
    draw = ImageDraw.Draw(image)
    _draw_stars(draw, 64)
    _draw_header(draw, 64)
    _draw_fireball(draw, 64, 32, meteor_step, meteor_total)
    shower = data["shower"]
    score = data["score"]
    color = _score_color(score)
    if mode == "shower":
        days = abs(int(shower.get("days", 0)))
        value = days if not shower.get("active") else shower["zhr"]
        _draw_score_number(draw, value, 24, 11, (255, 255, 255), scale=1)
        suffix = "/HR" if shower.get("active") else "D"
        _draw_pixel_text(draw, (35, 12), suffix, (95, 230, 135))
        _draw_pixel_text(draw, (1, 20), "NEXT PEAK" if not shower.get("active") else "ACTIVE", (255, 220, 90))
        if shower.get("active"):
            footer = f"MOON {data['moon']}%"
        else:
            footer = shower["peak_date"].strftime("%b %d").upper()
        _draw_pixel_text(draw, (1, 26), _pixel_fit(footer, 62), (160, 190, 230))
    else:
        _draw_score_number(draw, score, 25, 9, color, scale=1)
        _draw_pixel_text(draw, (36, 10), "/99", (180, 210, 230))
        cloud = "--" if data["cloud"] is None else str(data["cloud"])
        peak = shower["peak_date"].strftime("%b %d").upper()
        _draw_pixel_text(draw, (1, 19), _pixel_fit(f"CLOUD {cloud}%", 62), (155, 205, 255))
        _draw_pixel_text(draw, (1, 26), _pixel_fit(f"PEAK {peak}", 62), (255, 220, 90))
    return image


def _render_128(data, mode, meteor_step=0, meteor_total=1):
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (128, 32), (1, 5, 18))
    draw = ImageDraw.Draw(image)
    _draw_stars(draw, 128)
    _draw_header(draw, 128)
    _draw_fireball(draw, 128, 32, meteor_step, meteor_total)
    shower = data["shower"]
    score = data["score"]
    color = _score_color(score)
    _draw_score_number(draw, score, 18, 11, color, scale=1)
    _draw_pixel_text(draw, (29, 12), "/99", (180, 210, 230))
    name = _pixel_fit(shower["name"], 72)
    _draw_pixel_text(draw, (52, 10), name, (255, 220, 90))
    status = "ACTIVE" if shower.get("active") else f"PEAK {shower['peak_date'].strftime('%b').upper()} {shower['peak_date'].day}"
    cloud = "--" if data["cloud"] is None else str(data["cloud"])
    detail = f"{status} CLOUD {cloud}% MOON {data['moon']}%"
    _draw_pixel_text(draw, (52, 20), _pixel_fit(detail, 74), (155, 205, 255))
    return image


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    try:
        data = _data(opts)
    except Exception:
        return render_text_webp("METEOR ERR", (238, 80, 80))
    mode = str(opts.get("mode") or "auto").lower()
    if mode == "auto":
        mode = "shower" if data["shower"].get("active") and abs(data["shower"].get("days", 0)) <= 2 else "score"
    frame_count = 10
    if width == 128:
        frames = [_render_128(data, mode, idx, frame_count) for idx in range(frame_count)]
    else:
        frames = [_render_64(data, mode, idx, frame_count) for idx in range(frame_count)]
    return _webp_frames(frames)
