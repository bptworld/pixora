from concurrent.futures import ThreadPoolExecutor
import atexit
from datetime import datetime, timedelta, timezone
import re
import threading
from zoneinfo import ZoneInfo

from card_utils import (
    _settings_value,
    draw_pixora_bold_number,
    draw_mini_weather_icon,
    draw_sharp_text,
    format_time,
    fetch_json_request,
    pixora_bold_number_size,
    paste_openweather_icon,
    weather_for_zip,
)

CARD_ID = "clock"
CARD_NAME = "Clock"
CARD_DETAIL = "Time plus local weather"
CARD_OPTIONS = [
    {"key": "zipCode", "label": "ZIP", "type": "text", "default": "", "maxlength": 5, "inputmode": "numeric"},
    {"key": "showWeather", "label": "Show weather", "type": "checkbox", "default": True},
    {
        "key": "timezone",
        "label": "Time Zone",
        "type": "select",
        "default": "",
        "choices": [
            {"value": "", "label": "Use global default"},
            {"value": "America/New_York", "label": "Eastern"},
            {"value": "America/Chicago", "label": "Central"},
            {"value": "America/Denver", "label": "Mountain"},
            {"value": "America/Phoenix", "label": "Arizona"},
            {"value": "America/Los_Angeles", "label": "Pacific"},
            {"value": "America/Anchorage", "label": "Alaska"},
            {"value": "Pacific/Honolulu", "label": "Hawaii"},
            {"value": "UTC", "label": "UTC"},
        ],
    },
    {
        "key": "timeFormat",
        "label": "Time Format",
        "type": "select",
        "default": "",
        "choices": [
            {"value": "", "label": "Use global default"},
            {"value": "12", "label": "12-hour"},
            {"value": "24", "label": "24-hour"},
        ],
    },
]

_WEATHER_POOL = None
_WEATHER_CACHE = {}
_WEATHER_PENDING = set()
_WEATHER_LOCK = threading.Lock()
_WEATHER_TTL = timedelta(minutes=10)
_WEATHER_RETRY = timedelta(seconds=30)
_ZIP_TIMEZONE_CACHE = {}
_ZIP_TIMEZONE_TTL = timedelta(days=7)

_SEGMENTS = {
    "0": "abcfed",
    "1": "bc",
    "2": "abged",
    "3": "abgcd",
    "4": "fgbc",
    "5": "afgcd",
    "6": "afgecd",
    "7": "abc",
    "8": "abcdefg",
    "9": "abfgcd",
}


def _bitmap_text_size(text, scale=1, spacing=1):
    width = 0
    for idx, ch in enumerate(text):
        if ch in _SEGMENTS:
            width += 5 * scale
        elif ch == ":":
            width += scale
        elif ch == " ":
            width += 3 * scale
        if idx < len(text) - 1:
            width += spacing
    return max(0, width), 9 * scale


def _draw_bitmap_time(draw, xy, text, color, scale=1, spacing=1):
    x, y = xy
    for ch in text:
        segments = _SEGMENTS.get(ch)
        if segments:
            bar = max(1, scale)

            def hseg(px, py):
                draw.rectangle((x + px * scale, y + py * scale, x + (px + 3) * scale - 1, y + py * scale + bar - 1), fill=color)

            def vseg(px, py):
                draw.rectangle((x + px * scale, y + py * scale, x + px * scale + bar - 1, y + (py + 3) * scale - 1), fill=color)

            if "a" in segments:
                hseg(1, 0)
            if "b" in segments:
                vseg(4, 1)
            if "c" in segments:
                vseg(4, 5)
            if "d" in segments:
                hseg(1, 8)
            if "e" in segments:
                vseg(0, 5)
            if "f" in segments:
                vseg(0, 1)
            if "g" in segments:
                hseg(1, 4)
            x += 5 * scale + spacing
        elif ch == ":":
            draw.rectangle((x, y + 2 * scale, x + scale - 1, y + 3 * scale - 1), fill=color)
            draw.rectangle((x, y + 6 * scale, x + scale - 1, y + 7 * scale - 1), fill=color)
            x += scale + spacing
        elif ch == " ":
            x += 3 * scale + spacing


def _normalize_zip(zip_code):
    return re.sub(r"\D", "", zip_code or "")[:5]


def _default_zip():
    return _normalize_zip(_settings_value("defaultZipCode", "") or "")


def _float_option(options, *keys):
    options = options or {}
    for key in keys:
        value = options.get(key)
        if value in (None, ""):
            value = _settings_value(key, "")
        try:
            return float(value)
        except Exception:
            pass
    return None


def _timezone_name_for_lat_lon(lat, lon):
    if lat is None or lon is None:
        return ""
    if 18 <= lat <= 23 and -161 <= lon <= -154:
        return "Pacific/Honolulu"
    if lat >= 50 and lon <= -130:
        return "America/Anchorage"
    if lon <= -114:
        return "America/Los_Angeles"
    if lon <= -101:
        return "America/Denver"
    if lon <= -86:
        return "America/Chicago"
    return "America/New_York"


def _timezone_name_for_zip(zip_code):
    zip_code = _normalize_zip(zip_code)
    if len(zip_code) != 5:
        return ""
    now = datetime.now(timezone.utc)
    cached = _ZIP_TIMEZONE_CACHE.get(zip_code)
    if cached and cached.get("expires", now) > now:
        return cached.get("timezone", "")
    try:
        location = fetch_json_request(f"https://api.zippopotam.us/us/{zip_code}", seconds=86400)
        place = location["places"][0]
        tz_name = _timezone_name_for_lat_lon(float(place["latitude"]), float(place["longitude"]))
    except Exception:
        tz_name = ""
    _ZIP_TIMEZONE_CACHE[zip_code] = {"timezone": tz_name, "expires": now + _ZIP_TIMEZONE_TTL}
    return tz_name


def _clock_now(options=None):
    options = options or {}
    tz_name = (
        str(options.get("timezone") or options.get("timeZone") or "").strip()
        or str(_settings_value("defaultTimezone", "") or _settings_value("defaultTimeZone", "") or "").strip()
    )
    if not tz_name:
        lat = _float_option(options, "latitude", "lat", "defaultLatitude")
        lon = _float_option(options, "longitude", "lon", "lng", "defaultLongitude")
        tz_name = _timezone_name_for_lat_lon(lat, lon)
    if not tz_name:
        tz_name = _timezone_name_for_zip(_normalize_zip(options.get("zipCode", "")) or _default_zip())
    if tz_name:
        try:
            return datetime.now(ZoneInfo(tz_name))
        except Exception:
            pass
    return datetime.now().astimezone()


def _clock_time_text(now, options=None):
    value = str((options or {}).get("timeFormat") or "").strip().lower()
    if value in ("24", "24h", "24-hour", "military"):
        return now.strftime("%H:%M")
    if value in ("12", "12h", "12-hour"):
        return now.strftime("%I:%M").lstrip("0")
    return format_time(now)


def _weather_worker(zip_code):
    try:
        weather = weather_for_zip(zip_code)
        expires = datetime.now(timezone.utc) + _WEATHER_TTL
    except Exception:
        weather = None
        expires = datetime.now(timezone.utc) + _WEATHER_RETRY
    with _WEATHER_LOCK:
        if weather:
            _WEATHER_CACHE[zip_code] = {"weather": weather, "expires": expires}
        else:
            _WEATHER_CACHE.setdefault(zip_code, {"weather": None, "expires": expires})["expires"] = expires
        _WEATHER_PENDING.discard(zip_code)


def _weather_pool():
    global _WEATHER_POOL
    if _WEATHER_POOL is None:
        _WEATHER_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pixora-clock-weather")
    return _WEATHER_POOL


def _shutdown_weather_pool():
    if _WEATHER_POOL is not None:
        _WEATHER_POOL.shutdown(wait=False, cancel_futures=True)


atexit.register(_shutdown_weather_pool)


def _weather_now_or_queue(zip_code):
    zip_code = _normalize_zip(zip_code)
    if len(zip_code) != 5:
        return None
    now = datetime.now(timezone.utc)
    should_fetch_now = False
    should_refresh = False
    with _WEATHER_LOCK:
        cached = _WEATHER_CACHE.get(zip_code)
        if cached and cached.get("weather") and cached.get("expires", now) > now:
            return cached["weather"]
        if cached and cached.get("weather"):
            should_refresh = zip_code not in _WEATHER_PENDING
        else:
            should_fetch_now = zip_code not in _WEATHER_PENDING
        if should_fetch_now or should_refresh:
            _WEATHER_PENDING.add(zip_code)
    if should_fetch_now:
        _weather_worker(zip_code)
        with _WEATHER_LOCK:
            cached = _WEATHER_CACHE.get(zip_code)
            return cached.get("weather") if cached else None
    if should_refresh:
        _weather_pool().submit(_weather_worker, zip_code)
    return cached.get("weather") if cached else None


def _draw_temp(image, xy, number, unit, color, scale, unit_font, spacing=None):
    from PIL import ImageDraw

    spacing = scale if spacing is None else spacing
    x, y = xy
    number = str(number or "--")
    unit = str(unit or "")[:1]
    draw = ImageDraw.Draw(image)
    draw_pixora_bold_number(draw, (x, y), number, color, scale=scale, spacing=spacing)
    num_w, num_h = pixora_bold_number_size(number, scale=scale, spacing=spacing)
    if unit:
        unitb = draw.textbbox((0, 0), unit, font=unit_font)
        unit_h = unitb[3] - unitb[1]
        unit_x = x + num_w + 1 - unitb[0]
        unit_y = y + (num_h - unit_h) // 2 - unitb[1]
        draw_sharp_text(image, (unit_x, unit_y), unit, color, unit_font)


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont
    from io import BytesIO
    from datetime import datetime

    is_wide = (options or {}).get("_target") == "matrixportal-s3-128x32"
    width = 128 if is_wide else 64
    image = Image.new("RGB", (width, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    try:
        time_font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 18 if is_wide else 16)
        temp_font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 14)
        unit_font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        small_font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        time_font = temp_font = unit_font = small_font = ImageFont.load_default()

    now = _clock_now(options)
    text = _clock_time_text(now, options)
    time_scale = 2 if is_wide else 2
    time_spacing = 2 if is_wide else 1
    tw, th = _bitmap_text_size(text, scale=time_scale, spacing=time_spacing)

    show_weather = (options or {}).get("showWeather", True)
    show_weather = show_weather is True or str(show_weather).lower() not in ("false", "0", "off", "no")
    if not show_weather:
        time_x = (width - tw) // 2
        time_y = (32 - th) // 2
        _draw_bitmap_time(draw, (time_x, time_y), text, (20, 149, 255), scale=time_scale, spacing=time_spacing)
        out = BytesIO()
        image.save(out, "WEBP", lossless=True, quality=100)
        return out.getvalue()

    zip_code = _normalize_zip((options or {}).get("zipCode", "")) or _default_zip()
    weather = _weather_now_or_queue(zip_code)
    if zip_code:
        if weather:
            temp_num = str(weather["temperature"])[:3]
            temp_unit = str(weather["temperatureUnit"] or "F")[:1]
            if is_wide:
                temp_w, temp_h = pixora_bold_number_size(temp_num, scale=2, spacing=2)
                unitb = draw.textbbox((0, 0), temp_unit, font=unit_font)
                unit_w = unitb[2] - unitb[0]
                total_w = temp_w + 1 + unit_w
                time_x = (width - tw) // 2
                time_y = (32 - th) // 2
                _draw_bitmap_time(draw, (time_x, time_y), text, (20, 149, 255), scale=time_scale, spacing=time_spacing)
                if not paste_openweather_icon(image, weather.get("openWeatherIcon"), 0, 2, 28):
                    draw_mini_weather_icon(draw, weather["icon"], 14, 11)
                temp_x = width - total_w - 1
                temp_y = (32 - temp_h) // 2
                _draw_temp(image, (temp_x, temp_y), temp_num, temp_unit, (235, 247, 255), 2, unit_font, spacing=2)
                out = BytesIO()
                image.save(out, "WEBP", lossless=True, quality=100)
                return out.getvalue()
            temp_w, temp_h = pixora_bold_number_size(temp_num, scale=1, spacing=1)
            unitb = draw.textbbox((0, 0), temp_unit, font=small_font)
            temp_w += 1 + (unitb[2] - unitb[0])
            icon_h, icon_w = 11, 13
            _draw_bitmap_time(draw, ((64 - tw) // 2, 0), text, (20, 149, 255), scale=time_scale, spacing=time_spacing)
            row_w = icon_w + 5 + temp_w
            row_x = (64 - row_w) // 2
            row_y = 32 - icon_h - 2
            if not paste_openweather_icon(image, weather.get("openWeatherIcon"), row_x, row_y - 2, 15):
                draw_mini_weather_icon(draw, weather["icon"], row_x + icon_w // 2, row_y)
            _draw_temp(
                image,
                (row_x + icon_w + 5, row_y + (icon_h - temp_h) // 2),
                temp_num,
                temp_unit,
                (235, 247, 255),
                1,
                small_font,
                spacing=1,
            )
        else:
            time_x = (width - tw) // 2
            time_y = (32 - th) // 2 if is_wide else 0
            _draw_bitmap_time(draw, (time_x, time_y), text, (20, 149, 255), scale=time_scale, spacing=time_spacing)
    else:
        time_x = (width - tw) // 2
        time_y = (32 - th) // 2 if is_wide else 0
        _draw_bitmap_time(draw, (time_x, time_y), text, (20, 149, 255), scale=time_scale, spacing=time_spacing)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
