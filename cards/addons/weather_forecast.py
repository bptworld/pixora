from datetime import datetime
from io import BytesIO
from urllib.parse import urlparse
from card_utils import convert_f_to_c, draw_mini_weather_icon, draw_sharp_text, fetch_json_request, openweather_forecast_for_zip, paste_openweather_icon, pixora_local_now, render_text_webp, temperature_units, weather_for_zip, weather_icon_from_text

CARD_ID = "weather_forecast"
CARD_NAME = "Weather Forecast"
CARD_DETAIL = "4-day forecast with current weather"
CARD_OPTIONS = [
    {"key": "zipCode", "label": "ZIP Code", "type": "text", "default": "10001",
     "maxlength": 5, "inputmode": "numeric"},
]
CARD_RULE_FIELDS = [
    {"id": "current_temp", "label": "Current Temperature"},
    {"id": "current_condition", "label": "Current Condition"},
    {"id": "today_high", "label": "Today High"},
    {"id": "today_low", "label": "Today Low"},
]
PIXEL_WEATHER_ICONS = frozenset({"sun", "moon", "partly", "moon_cloud", "cloud", "rain", "drizzle", "thunder", "snow", "fog"})
NWS_ICON_NAMES = {
    "skc": "sun", "few": "partly", "sct": "partly", "bkn": "cloud", "ovc": "cloud",
    "wind_skc": "sun", "wind_few": "partly", "wind_sct": "partly", "wind_bkn": "cloud", "wind_ovc": "cloud",
    "rain": "rain", "rain_showers": "rain", "rain_showers_hi": "rain",
    "fzra": "rain", "rain_sleet": "snow", "sleet": "snow",
    "tsra": "thunder", "tsra_sct": "thunder", "tsra_hi": "thunder",
    "snow": "snow", "rain_snow": "snow", "snow_sleet": "snow", "blizzard": "snow",
    "fog": "fog", "haze": "fog", "smoke": "fog", "dust": "fog",
}
NWS_ICON_PRIORITY = {"thunder": 6, "snow": 5, "rain": 4, "drizzle": 3, "fog": 2, "cloud": 1, "partly": 1, "sun": 0, "moon": 0}


def _zip_forecast(zip_code):
    try:
        owm_days = openweather_forecast_for_zip(zip_code)
    except Exception:
        owm_days = None
    if owm_days:
        return owm_days
    loc = fetch_json_request(f"https://api.zippopotam.us/us/{zip_code}", seconds=86400)
    p = loc["places"][0]
    lat, lon = float(p["latitude"]), float(p["longitude"])
    pt = fetch_json_request(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}", seconds=86400)
    fc = fetch_json_request(pt["properties"]["forecast"], seconds=3600)
    return fc["properties"]["periods"]


def rule_value(options=None, field=""):
    opts = options or {}
    zip_code = (opts.get("zipCode") or "").strip() or "10001"
    key = str(field or "current_temp").strip()
    try:
        current = weather_for_zip(zip_code)
    except Exception:
        current = {}
    if key == "current_temp":
        return current.get("temperature", "")
    if key == "current_condition":
        return current.get("shortForecast") or current.get("condition") or ""
    forecast = _zip_forecast(zip_code)
    day = next((item for item in forecast if item.get("isDaytime", True)), forecast[0] if forecast else {})
    night = next((item for item in forecast if not item.get("isDaytime", True)), {})
    if key == "today_high":
        return day.get("temperature", "")
    if key == "today_low":
        return day.get("low", night.get("temperature", ""))
    return ""


def _day_label(name):
    n = name.upper()
    if any(x in n for x in ("TODAY", "THIS AFTERNOON", "THIS MORNING", "THIS EVENING")):
        return ["Mo","Tu","We","Th","Fr","Sa","Su"][pixora_local_now().weekday()]
    for full, abbr in [("MONDAY","Mo"),("TUESDAY","Tu"),("WEDNESDAY","We"),
                       ("THURSDAY","Th"),("FRIDAY","Fr"),("SATURDAY","Sa"),("SUNDAY","Su")]:
        if full in n:
            return abbr
    return name[:2].title()


def _icon(text):
    return weather_icon_from_text(text)


def _temp(value, unit="F"):
    if temperature_units() == "C" and str(unit or "F").upper() != "C":
        value = convert_f_to_c(value)
    return str(value if value is not None else "--")


def _weather_icon_name(period):
    icon = str(period.get("icon") or "").strip().lower()
    if icon in PIXEL_WEATHER_ICONS:
        return icon
    if "api.weather.gov/icons/" in icon:
        codes = [part.split(",", 1)[0] for part in urlparse(icon).path.split("/") if part]
        names = [NWS_ICON_NAMES[code] for code in codes if code in NWS_ICON_NAMES]
        if names:
            name = max(names, key=lambda item: NWS_ICON_PRIORITY[item])
            if "/night/" in icon:
                return {"sun": "moon", "partly": "moon_cloud"}.get(name, name)
            return name
    return _icon(period.get("shortForecast", ""))


def _draw_icon(image, period, cx, y):
    from PIL import Image, ImageDraw
    canvas = Image.new("RGBA", (17, 14), (0, 0, 0, 0))
    draw_mini_weather_icon(ImageDraw.Draw(canvas), _weather_icon_name(period), 8, 0)
    compact = canvas.resize((11, 9), Image.Resampling.NEAREST)
    image.paste(compact, (cx - 5, y - 3), compact)


def _draw_big_icon(image, draw, weather, x, y):
    if paste_openweather_icon(image, weather.get("openWeatherIcon"), x, y, 24):
        return
    draw_mini_weather_icon(draw, weather.get("icon") or _icon(weather.get("shortForecast", "")), x + 12, y + 7)


def _draw_64(image, draw, days, nights, font, bold):
    cols = [8, 24, 40, 56]
    dividers = [16, 32, 48]

    for x in dividers:
        draw.line((x, 0, x, 31), fill=(25, 35, 50))

    for i, (cx, period) in enumerate(zip(cols, days)):
        label = _day_label(period["name"])
        unit = period.get("temperatureUnit", "F")
        night = nights[i] if i < len(nights) else {}
        high = _temp(period.get("temperature", "--"), unit)
        low = _temp(period.get("low", night.get("temperature", "--")), period.get("lowUnit", night.get("temperatureUnit", unit)))

        label_color = (24, 182, 163) if i == 0 else (160, 190, 215)
        lw = draw.textbbox((0, 0), label, font=font)[2]
        draw_sharp_text(image, (cx - lw // 2, -3), label, label_color, font)
        _draw_icon(image, period, cx, 10)
        hw = draw.textbbox((0, 0), high, font=font)[2]
        draw_sharp_text(image, (cx - hw // 2, 15), high, (255, 175, 70), font)
        lw2 = draw.textbbox((0, 0), low, font=font)[2]
        draw_sharp_text(image, (cx - lw2 // 2, 22), low, (110, 175, 255), font)


def _draw_128(image, draw, days, nights, current, font, bold, small):
    left_w = 36
    draw.rectangle((0, 0, left_w - 1, 31), fill=(0, 9, 22))
    draw.line((left_w, 0, left_w, 31), fill=(35, 50, 65))

    if current:
        _draw_big_icon(image, draw, current, 6, 0)
        temp = str(current.get("temperature", "--"))[:3]
        unit = str(current.get("temperatureUnit") or temperature_units() or "F")[:1]
        tb = draw.textbbox((0, 0), temp, font=bold)
        ub = draw.textbbox((0, 0), unit, font=small)
        tw = tb[2] - tb[0]
        total = tw + 1 + (ub[2] - ub[0])
        tx = (left_w - total) // 2
        draw_sharp_text(image, (tx, 20), temp, (235, 247, 255), bold)
        draw_sharp_text(image, (tx + tw + 1, 20), unit, (235, 247, 255), small)
    else:
        draw_sharp_text(image, (4, 8), "NOW", (100, 180, 255), bold)
        draw_sharp_text(image, (5, 19), "--", (235, 247, 255), bold)

    cols = [48, 68, 88, 111]
    dividers = [58, 78, 100]
    for x in dividers:
        draw.line((x, 1, x, 31), fill=(22, 32, 45))

    for i, (cx, period) in enumerate(zip(cols, days)):
        label = _day_label(period["name"])
        unit = period.get("temperatureUnit", "F")
        night = nights[i] if i < len(nights) else {}
        high = _temp(period.get("temperature", "--"), unit)
        low = _temp(period.get("low", night.get("temperature", "--")), period.get("lowUnit", night.get("temperatureUnit", unit)))
        label_color = (24, 182, 163) if i == 0 else (160, 190, 215)
        lw = draw.textbbox((0, 0), label, font=font)[2]
        draw_sharp_text(image, (cx - lw // 2, -3), label, label_color, font)
        _draw_icon(image, period, cx, 10)
        hw = draw.textbbox((0, 0), high, font=font)[2]
        draw_sharp_text(image, (cx - hw // 2, 15), high, (255, 175, 70), font)
        lw2 = draw.textbbox((0, 0), low, font=font)[2]
        draw_sharp_text(image, (cx - lw2 // 2, 22), low, (110, 175, 255), font)


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont
    opts = options or {}
    zip_code = (opts.get("zipCode") or "").strip()
    if len(zip_code) != 5:
        return render_text_webp("SET ZIP", (100, 180, 255))

    try:
        periods = _zip_forecast(zip_code)
    except Exception:
        return render_text_webp("WTHR ERR", (238, 80, 80))

    days  = [p for p in periods if p.get("isDaytime", True)][:4]
    nights = [p for p in periods if not p.get("isDaytime", True)][:4]

    if not days:
        return render_text_webp("NO DATA", (150, 150, 150))

    is_wide = opts.get("_target") == "matrixportal-s3-128x32"
    width = 128 if is_wide else 64
    image = Image.new("RGB", (width, 32), (0, 5, 15))
    draw  = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        small = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 6)
    except Exception:
        font = bold = small = ImageFont.load_default()

    if is_wide:
        try:
            current = weather_for_zip(zip_code)
        except Exception:
            current = None
        _draw_128(image, draw, days, nights, current, font, bold, small)
    else:
        _draw_64(image, draw, days, nights, font, bold)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
