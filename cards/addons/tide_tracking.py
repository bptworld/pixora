from datetime import datetime
from io import BytesIO
import math
import re

from card_utils import draw_sharp_text, fetch_json_request, render_text_webp

CARD_ID = "tide_tracking"
CARD_NAME = "Tide Tracking"
CARD_DETAIL = "Next high and low tide"
CARD_CATEGORY = "Weather"
CARD_OPTIONS = [
    {
        "key": "zipCode",
        "label": "ZIP Code",
        "type": "text",
        "default": "02134",
        "maxlength": 5,
        "inputmode": "numeric",
    },
    {
        "key": "stationId",
        "label": "Station",
        "type": "select",
        "default": "",
        "choices": [{"value": "", "label": "Nearest tide station"}],
        "dynamicChoices": {"dependsOn": ["zipCode"]},
    },
    {
        "key": "units",
        "label": "Units",
        "type": "select",
        "default": "english",
        "choices": [
            {"value": "english", "label": "Feet"},
            {"value": "metric", "label": "Meters"},
        ],
    },
]

CARD_RULE_FIELDS = [
    {"id": "next_type", "label": "Next Tide Type"},
    {"id": "next_time", "label": "Next Tide Time"},
    {"id": "next_height", "label": "Next Tide Height"},
    {"id": "direction", "label": "Current Tide Direction"},
]

_API_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
_STATIONS_URL = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=tidepredictions"
_APP = "Pixora"


def _safe_text(value, default=""):
    return re.sub(r"\s+", " ", str(value or default)).strip()


def _zip_code(opts):
    value = re.sub(r"\D", "", _safe_text(opts.get("zipCode")))
    return value[:5] or "02134"


def _zip_lat_lng(zip_code):
    loc = fetch_json_request(f"https://api.zippopotam.us/us/{zip_code}", seconds=86400)
    place = (loc.get("places") or [{}])[0]
    return float(place["latitude"]), float(place["longitude"])


def _miles(lat1, lon1, lat2, lon2):
    radius = 3958.8
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _stations():
    data = fetch_json_request(_STATIONS_URL, seconds=86400)
    stations = []
    for item in data.get("stations") or []:
        station_id = re.sub(r"[^A-Za-z0-9]", "", _safe_text(item.get("id")))
        name = _safe_text(item.get("name"))
        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lng"))
        except Exception:
            continue
        if station_id and name:
            stations.append({"id": station_id, "name": name, "state": _safe_text(item.get("state")), "lat": lat, "lng": lng})
    return stations


def _nearby_stations(zip_code, limit=30, radius_miles=75):
    lat, lng = _zip_lat_lng(zip_code)
    rows = []
    for station in _stations():
        distance = _miles(lat, lng, station["lat"], station["lng"])
        rows.append({**station, "distance": distance})
    rows = sorted(rows, key=lambda item: (item["distance"], item["name"]))
    in_radius = [item for item in rows if item["distance"] <= radius_miles]
    return (in_radius or rows)[:limit]


def _station_from_options(opts):
    station_id = re.sub(r"[^A-Za-z0-9]", "", _safe_text(opts.get("stationId")))
    zip_code = _zip_code(opts)
    nearby = _nearby_stations(zip_code)
    if station_id:
        for station in nearby:
            if station["id"] == station_id:
                return station
        for station in _stations():
            if station["id"] == station_id:
                return station
    return nearby[0] if nearby else {"id": "8443970", "name": "Boston", "state": "MA", "lat": 42.3539, "lng": -71.0503, "distance": 0}


def _units(opts):
    value = _safe_text(opts.get("units"), "english").lower()
    return "metric" if value == "metric" else "english"


def card_option_choices(option_key, options=None):
    if option_key != "stationId":
        return []
    opts = options or {}
    try:
        nearby = _nearby_stations(_zip_code(opts))
    except Exception:
        return [{"value": "", "label": "Nearest tide station"}]
    choices = [{"value": "", "label": "Nearest tide station"}]
    for station in nearby:
        distance = station.get("distance")
        miles = f" - {distance:.0f} mi" if isinstance(distance, (int, float)) else ""
        state = f", {station['state']}" if station.get("state") and len(station["state"]) <= 3 else ""
        choices.append({"value": station["id"], "label": f"{station['name']}{state}{miles}"})
    return choices


def _fetch_tides(station, units):
    today = datetime.now().strftime("%Y%m%d")
    url = (
        f"{_API_URL}?product=predictions&application={_APP}&begin_date={today}&range=72"
        f"&datum=MLLW&station={station}&time_zone=lst_ldt&units={units}"
        "&interval=hilo&format=json"
    )
    data = fetch_json_request(url, seconds=1800)
    if not isinstance(data, dict) or data.get("error"):
        raise ValueError("NOAA tide API error")
    rows = []
    for item in data.get("predictions") or []:
        stamp = _parse_time(item.get("t"))
        kind = _safe_text(item.get("type")).upper()[:1]
        if stamp and kind in ("H", "L"):
            try:
                height = float(item.get("v"))
            except Exception:
                height = None
            rows.append({"time": stamp, "type": kind, "height": height})
    return sorted(rows, key=lambda row: row["time"])


def _parse_time(value):
    try:
        return datetime.strptime(str(value or ""), "%Y-%m-%d %H:%M")
    except Exception:
        return None


def _time_label(dt):
    if not dt:
        return "--"
    label = dt.strftime("%I:%M%p").lstrip("0")
    return label.replace(":00", "").replace("AM", "A").replace("PM", "P")


def _short_date(dt):
    if not dt:
        return ""
    now = datetime.now()
    if dt.date() == now.date():
        return "TODAY"
    return dt.strftime("%a").upper()


def _height_label(value, units):
    if value is None:
        return "--"
    suffix = "FT" if units == "english" else "M"
    return f"{value:.1f}{suffix}"


def _next_events(rows):
    now = datetime.now()
    previous = None
    upcoming = []
    for row in rows:
        if row["time"] <= now:
            previous = row
        else:
            upcoming.append(row)
    if not upcoming and rows:
        upcoming = rows[-2:]
    return previous, upcoming


def _direction(next_event):
    if not next_event:
        return "--"
    return "RISING TO HIGH" if next_event["type"] == "H" else "FALLING TO LOW"


def _direction_short(next_event):
    if not next_event:
        return "--"
    return "RISING" if next_event["type"] == "H" else "FALLING"


def _tide_label(kind):
    return "HIGH" if kind == "H" else "LOW"


def _station_label(name):
    text = _safe_text(name, "TIDES").upper()
    text = text.replace("AMELIA EARHART", "AMELIA")
    text = re.sub(r"\b(BAY|HARBOR|RIVER|ENTRANCE|CHANNEL|BEACH|ISLAND|POINT|DAM|BRIDGE)\b", "", text)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "TIDES"


def _fit(draw, text, font, max_width):
    text = _safe_text(text).upper()
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1].rstrip()
    return text


def _fonts():
    from PIL import ImageFont

    try:
        return {
            "header": ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8),
            "text": ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8),
            "tiny": ImageFont.truetype("assets/fonts/PixelifySans.ttf", 6),
        }
    except Exception:
        font = ImageFont.load_default()
        return {"header": font, "text": font, "tiny": font}


def _draw_wave(draw, width, y, color):
    for x in range(-2, width + 2, 8):
        draw.arc((x, y - 3, x + 8, y + 5), 0, 180, fill=color)


def _draw_background(img, draw):
    for y in range(32):
        blend = y / 31
        color = (
            round(1 + 1 * blend),
            round(8 + 16 * blend),
            round(22 + 34 * blend),
        )
        draw.line((0, y, img.width - 1, y), fill=color)
    draw.line((0, 9, img.width - 1, 9), fill=(24, 90, 125))
    _draw_wave(draw, img.width, 30, (20, 92, 130))


def _draw_arrow(draw, x, y, direction, color):
    if direction == "RISING":
        pts = [(x, y + 6), (x + 4, y), (x + 8, y + 6)]
    elif direction == "FALLING":
        pts = [(x, y), (x + 4, y + 6), (x + 8, y)]
    else:
        pts = [(x, y + 3), (x + 8, y + 3)]
    draw.line(pts, fill=color, width=2, joint="curve")


def _draw_64(img, draw, rows, station_name, units, f):
    previous, upcoming = _next_events(rows)
    next_event = upcoming[0] if upcoming else previous
    if not next_event:
        draw_sharp_text(img, (10, 13), "NO DATA", (255, 120, 120), f["text"])
        return
    color = (95, 230, 255) if next_event["type"] == "H" else (255, 210, 90)
    top = f"NEXT {_tide_label(next_event['type'])}"
    time = _time_label(next_event["time"])
    height = _height_label(next_event["height"], units)
    tw = draw.textbbox((0, 0), top, font=f["header"])[2]
    draw_sharp_text(img, ((64 - tw) // 2, -3), top, color, f["header"])
    time_w = draw.textbbox((0, 0), time, font=f["header"])[2]
    draw_sharp_text(img, ((64 - time_w) // 2, 9), time, (245, 250, 255), f["header"])
    bottom = f"{next_event['type']} {height}"
    bw = draw.textbbox((0, 0), bottom, font=f["text"])[2]
    draw_sharp_text(img, ((64 - bw) // 2, 21), bottom, (145, 210, 235), f["text"])


def _draw_128(img, draw, rows, station_name, units, f):
    previous, upcoming = _next_events(rows)
    next_event = upcoming[0] if upcoming else previous
    if not next_event:
        draw_sharp_text(img, (38, 13), "NO DATA", (255, 120, 120), f["text"])
        return
    station = _fit(draw, _station_label(station_name), f["tiny"], 58)
    color = (95, 230, 255) if next_event["type"] == "H" else (255, 210, 90)
    draw_sharp_text(img, (1, -3), "TIDE", (120, 220, 255), f["header"])
    label = f"NEXT {_tide_label(next_event['type'])}"
    lw = draw.textbbox((0, 0), label, font=f["header"])[2]
    draw_sharp_text(img, (127 - lw, -3), label, color, f["header"])

    _draw_arrow(draw, 3, 15, _direction_short(next_event), color)
    direction = _direction_short(next_event)
    draw_sharp_text(img, (15, 11), direction, color, f["header"])
    time = _time_label(next_event["time"])
    time_w = draw.textbbox((0, 0), time, font=f["header"])[2]
    draw_sharp_text(img, (127 - time_w, 11), time, (245, 250, 255), f["header"])
    height = _height_label(next_event["height"], units)
    draw_sharp_text(img, (15, 21), height, (145, 210, 235), f["text"])
    station_w = draw.textbbox((0, 0), station, font=f["tiny"])[2]
    draw_sharp_text(img, (127 - station_w, 23), station, (145, 165, 182), f["tiny"])


def _render(rows, station_name, units, width):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, 32), (0, 10, 25))
    draw = ImageDraw.Draw(img)
    f = _fonts()
    _draw_background(img, draw)
    if width >= 128:
        _draw_128(img, draw, rows, station_name, units, f)
    else:
        _draw_64(img, draw, rows, station_name, units, f)
    out = BytesIO()
    img.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _data(options=None):
    opts = options or {}
    units = _units(opts)
    station = _station_from_options(opts)
    rows = _fetch_tides(station["id"], units)
    previous, upcoming = _next_events(rows)
    next_event = upcoming[0] if upcoming else previous
    return rows, next_event, units, station


def rule_value(options=None, field=""):
    key = _safe_text(field)
    try:
        rows, next_event, units, _station = _data(options)
    except Exception:
        return ""
    if not next_event:
        return ""
    if key == "next_type":
        return _tide_label(next_event["type"])
    if key == "next_time":
        return _time_label(next_event["time"])
    if key == "next_height":
        return _height_label(next_event["height"], units)
    if key == "direction":
        return _direction_short(next_event)
    return ""


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    try:
        rows, _next_event, units, station = _data(opts)
    except Exception:
        return render_text_webp("TIDE ERR", (238, 80, 80))
    if not rows:
        return render_text_webp("NO TIDES", (160, 160, 160))
    return _render(rows, station.get("name") or "TIDES", units, width)
