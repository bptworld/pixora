from datetime import datetime, timedelta, timezone
from io import BytesIO
import math
import re
import urllib.parse

from card_utils import (
    _settings_value,
    draw_pixora_bold_number,
    draw_sharp_text,
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


def _font(size=8, bold=False):
    from PIL import ImageFont
    try:
        name = "Silkscreen-Bold.ttf" if bold else "Silkscreen-Regular.ttf"
        return ImageFont.truetype("assets/fonts/" + name, size)
    except Exception:
        return ImageFont.load_default()


FONT = _font(8)
SMALL = _font(6)
TINY = _font(5)


def _webp(image):
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _clean_zip(opts):
    value = re.sub(r"\D", "", str((opts or {}).get("zipCode") or ""))[:5]
    if value:
        return value
    return re.sub(r"\D", "", str(_settings_value("defaultZipCode", "") or ""))[:5]


def _location(zip_code):
    if len(zip_code) != 5:
        lat = str(_settings_value("defaultLatitude", "") or "").strip()
        lon = str(_settings_value("defaultLongitude", "") or "").strip()
        if lat and lon:
            return float(lat), float(lon)
        raise ValueError("location")
    data = fetch_json_request(f"https://api.zippopotam.us/us/{zip_code}", seconds=86400)
    place = data["places"][0]
    return float(place["latitude"]), float(place["longitude"])


def _cloud_cover(lat, lon):
    params = urllib.parse.urlencode({
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "hourly": "cloud_cover",
        "forecast_days": 1,
        "timezone": "auto",
    })
    data = fetch_json_with_headers(
        "https://api.open-meteo.com/v1/forecast?" + params,
        headers={"User-Agent": "Pixora/1.0 meteor_watch"},
        seconds=1800,
        cache_key=f"meteor:cloud:{lat:.3f}:{lon:.3f}",
    )
    values = ((data.get("hourly") or {}).get("cloud_cover") or []) if isinstance(data, dict) else []
    nums = [float(v) for v in values if isinstance(v, (int, float))]
    if not nums:
        return None
    return int(round(sum(nums) / len(nums)))


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
        lat, lon = _location(zip_code)
        cloud = _cloud_cover(lat, lon)
    except Exception:
        pass
    shower = _shower_status()
    moon, age = _moon_illumination()
    return {"zip": zip_code, "cloud": cloud, "moon": moon, "moon_age": age, "shower": shower, "score": _score(shower, cloud, moon)}


def _fit(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1].rstrip()
    return text or "-"


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
    stars = [(3, 3), (12, 14), (21, 5), (31, 23), (43, 8), (55, 25), (70, 4), (86, 20), (101, 8), (119, 25)]
    for x, y in stars:
        if x < width:
            draw.point((x, y), fill=(88, 130, 165) if (x + y + offset) % 3 else (150, 200, 230))


def _draw_meteor(draw, x, y, color=(95, 230, 255)):
    draw.line((x - 10, y + 5, x, y), fill=(18, 80, 110))
    draw.line((x - 6, y + 3, x, y), fill=color)
    draw.point((x + 1, y), fill=(255, 255, 255))


def _render_64(data, mode):
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (64, 32), (1, 5, 18))
    draw = ImageDraw.Draw(image)
    _draw_stars(draw, 64)
    _draw_meteor(draw, 58, 3)
    shower = data["shower"]
    score = data["score"]
    color = _score_color(score)
    if mode == "shower":
        title = _fit(draw, shower["short"], FONT, 62)
        draw_sharp_text(image, (1, -2), title, (95, 230, 255), FONT)
        label = "ACTIVE" if shower.get("active") else "PEAK IN"
        days = abs(int(shower.get("days", 0)))
        draw_sharp_text(image, (1, 8), label, (255, 220, 90), TINY)
        _draw_score_number(draw, days if not shower.get("active") else shower["zhr"], 34, 12, (255, 255, 255), scale=2)
        suffix = "/HR" if shower.get("active") else "D"
        draw_sharp_text(image, (49, 19), suffix, (95, 230, 135), TINY)
        draw_sharp_text(image, (1, 26), f"MOON {data['moon']}%", (160, 190, 230), TINY)
    else:
        draw_sharp_text(image, (1, -2), "METEOR", (95, 230, 255), FONT)
        _draw_score_number(draw, score, 24, 11, color, scale=2)
        draw_sharp_text(image, (43, 13), "/99", (180, 210, 230), TINY)
        cloud = "--" if data["cloud"] is None else str(data["cloud"])
        draw_sharp_text(image, (1, 26), _fit(draw, shower["short"], TINY, 36), (255, 220, 90), TINY)
        draw_sharp_text(image, (43, 26), _fit(draw, f"C{cloud}%", TINY, 20), (155, 205, 255), TINY)
    return image


def _render_128(data, mode):
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (128, 32), (1, 5, 18))
    draw = ImageDraw.Draw(image)
    _draw_stars(draw, 128)
    _draw_meteor(draw, 118, 4)
    shower = data["shower"]
    score = data["score"]
    color = _score_color(score)
    draw_sharp_text(image, (1, -2), "METEOR", (95, 230, 255), FONT)
    _draw_score_number(draw, score, 21, 12, color, scale=2)
    draw_sharp_text(image, (39, 14), "/99", (180, 210, 230), TINY)
    name = _fit(draw, shower["name"], FONT, 72)
    draw_sharp_text(image, (55, 2), name, (255, 220, 90), FONT)
    status = "ACTIVE" if shower.get("active") else f"PEAK {shower['peak_date'].strftime('%b').upper()} {shower['peak_date'].day}"
    cloud = "--" if data["cloud"] is None else str(data["cloud"])
    detail = f"{status} {shower['zhr']}/HR C{cloud}% M{data['moon']}%"
    draw_sharp_text(image, (55, 19), _fit(draw, detail, TINY, 72), (155, 205, 255), TINY)
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
    image = _render_128(data, mode) if width == 128 else _render_64(data, mode)
    return _webp(image)
