from datetime import datetime
from io import BytesIO
import math
import re

from card_utils import draw_sharp_text, fetch_json_request

BLUE = (95, 220, 255)
CYAN = (120, 245, 235)
GREEN = (120, 255, 150)
YELLOW = (255, 218, 84)
ORANGE = (255, 165, 72)
RED = (255, 92, 86)
WHITE = (240, 248, 255)
MUTED = (145, 165, 182)

TIDE_API_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
STATIONS_URL = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=tidepredictions"
APP = "Pixora"


def safe_text(value, default=""):
    return re.sub(r"\s+", " ", str(value or default)).strip()


def zip_code(opts):
    value = re.sub(r"\D", "", safe_text((opts or {}).get("zipCode")))
    return value[:5] or "02134"


def zip_lat_lng(zip_value):
    loc = fetch_json_request(f"https://api.zippopotam.us/us/{zip_value}", seconds=86400)
    place = (loc.get("places") or [{}])[0]
    return float(place["latitude"]), float(place["longitude"])


def miles(lat1, lon1, lat2, lon2):
    radius = 3958.8
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def tide_stations():
    data = fetch_json_request(STATIONS_URL, seconds=86400)
    rows = []
    for item in data.get("stations") or []:
        station_id = re.sub(r"[^A-Za-z0-9]", "", safe_text(item.get("id")))
        name = safe_text(item.get("name"))
        try:
            lat = float(item.get("lat"))
            lng = float(item.get("lng"))
        except Exception:
            continue
        if station_id and name:
            rows.append({"id": station_id, "name": name, "state": safe_text(item.get("state")), "lat": lat, "lng": lng})
    return rows


def nearby_stations(zip_value, limit=30, radius_miles=75):
    lat, lng = zip_lat_lng(zip_value)
    rows = []
    for station in tide_stations():
        rows.append({**station, "distance": miles(lat, lng, station["lat"], station["lng"])})
    rows = sorted(rows, key=lambda item: (item["distance"], item["name"]))
    in_radius = [item for item in rows if item["distance"] <= radius_miles]
    return (in_radius or rows)[:limit]


def station_choices(zip_value):
    try:
        nearby = nearby_stations(zip_value)
    except Exception:
        return [{"value": "", "label": "Nearest station"}]
    choices = [{"value": "", "label": "Nearest station"}]
    for station in nearby:
        state = f", {station['state']}" if station.get("state") and len(station["state"]) <= 3 else ""
        choices.append({"value": station["id"], "label": f"{station['name']}{state} - {station['distance']:.0f} mi"})
    return choices


def station_from_options(opts):
    opts = opts or {}
    selected = re.sub(r"[^A-Za-z0-9]", "", safe_text(opts.get("stationId")))
    nearby = nearby_stations(zip_code(opts))
    if selected:
        for station in nearby:
            if station["id"] == selected:
                return station
        for station in tide_stations():
            if station["id"] == selected:
                return station
    return nearby[0] if nearby else {"id": "8443970", "name": "Boston", "state": "MA", "lat": 42.3539, "lng": -71.0503}


def coops_latest(station_id, product, units="english"):
    today = datetime.now().strftime("%Y%m%d")
    url = (
        f"{TIDE_API_URL}?product={product}&application={APP}&begin_date={today}&range=24"
        f"&station={station_id}&time_zone=lst_ldt&units={units}&format=json"
    )
    data = fetch_json_request(url, seconds=900)
    key = product if product.endswith("s") else f"{product}s"
    rows = data.get(key) or data.get("data") or []
    for item in reversed(rows):
        try:
            value = float(item.get("v") if item.get("v") is not None else item.get("s"))
            return value
        except Exception:
            continue
    return None


def tide_events(station_id, units="english"):
    today = datetime.now().strftime("%Y%m%d")
    url = (
        f"{TIDE_API_URL}?product=predictions&application={APP}&begin_date={today}&range=72"
        f"&datum=MLLW&station={station_id}&time_zone=lst_ldt&units={units}&interval=hilo&format=json"
    )
    data = fetch_json_request(url, seconds=1800)
    rows = []
    for item in data.get("predictions") or []:
        stamp = parse_time(item.get("t"))
        kind = safe_text(item.get("type")).upper()[:1]
        if stamp and kind in ("H", "L"):
            try:
                height = float(item.get("v"))
            except Exception:
                height = None
            rows.append({"time": stamp, "type": kind, "height": height})
    return sorted(rows, key=lambda row: row["time"])


def next_tide(station_id, units="english"):
    now = datetime.now()
    previous = None
    upcoming = []
    for row in tide_events(station_id, units):
        if row["time"] <= now:
            previous = row
        else:
            upcoming.append(row)
    return upcoming[0] if upcoming else previous


def nws_point(zip_value):
    lat, lng = zip_lat_lng(zip_value)
    point = fetch_json_request(f"https://api.weather.gov/points/{lat:.4f},{lng:.4f}", seconds=86400)
    props = point.get("properties") or {}
    return lat, lng, props


def nws_hourly(zip_value):
    _lat, _lng, props = nws_point(zip_value)
    data = fetch_json_request(props["forecastHourly"], seconds=1800)
    return (data.get("properties") or {}).get("periods") or []


def nws_alerts(zip_value):
    lat, lng = zip_lat_lng(zip_value)
    data = fetch_json_request(f"https://api.weather.gov/alerts/active?point={lat:.4f},{lng:.4f}", seconds=900)
    return data.get("features") or []


def marine_data(zip_value):
    lat, lng = zip_lat_lng(zip_value)
    url = (
        "https://marine-api.open-meteo.com/v1/marine"
        f"?latitude={lat:.4f}&longitude={lng:.4f}"
        "&hourly=wave_height,wave_period,wave_direction,swell_wave_height,swell_wave_period,wind_wave_height"
        "&timezone=auto&forecast_days=2"
    )
    data = fetch_json_request(url, seconds=1800)
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return {}
    now = datetime.now()
    index = 0
    best_delta = None
    for i, raw in enumerate(times):
        stamp = parse_time(str(raw).replace("T", " "))
        if not stamp:
            continue
        delta = abs((stamp - now).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta = delta
            index = i

    def value(key):
        values = hourly.get(key) or []
        try:
            return float(values[index])
        except Exception:
            return None

    return {
        "wave_m": value("wave_height"),
        "period": value("wave_period"),
        "direction": value("wave_direction"),
        "swell_m": value("swell_wave_height"),
        "swell_period": value("swell_wave_period"),
        "wind_wave_m": value("wind_wave_height"),
    }


def parse_time(value):
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(value or ""), fmt)
        except Exception:
            pass
    return None


def time_label(dt):
    if not dt:
        return "--"
    return dt.strftime("%I:%M%p").lstrip("0").replace(":00", "").replace("AM", "A").replace("PM", "P")


def ft(meters):
    return None if meters is None else meters * 3.28084


def fmt_number(value, suffix="", decimals=0):
    if value is None:
        return "--"
    return f"{value:.{decimals}f}{suffix}"


def wind_mph(period):
    text = safe_text((period or {}).get("windSpeed"))
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else None


def wind_dir(period):
    return safe_text((period or {}).get("windDirection"), "--")[:3].upper()


def fonts():
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


def fit(draw, text, font, max_width):
    text = safe_text(text).upper()
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1].rstrip()
    return text


def draw_background(img, draw):
    for y in range(32):
        blend = y / 31
        draw.line((0, y, img.width - 1, y), fill=(round(2 + blend), round(9 + blend * 20), round(25 + blend * 36)))
    draw.line((0, 9, img.width - 1, 9), fill=(24, 90, 125))
    for x in range(-2, img.width + 2, 8):
        draw.arc((x, 27, x + 8, 35), 0, 180, fill=(20, 92, 130))


def render_simple(title, primary, secondary="", tertiary="", accent=BLUE, width=64):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, 32), (2, 9, 25))
    draw = ImageDraw.Draw(img)
    f = fonts()
    draw_background(img, draw)
    if width >= 128:
        draw_sharp_text(img, (1, -3), fit(draw, title, f["header"], 62), accent, f["header"])
        pw = draw.textbbox((0, 0), primary, font=f["header"])[2]
        draw_sharp_text(img, (127 - pw, -3), fit(draw, primary, f["header"], 64), WHITE, f["header"])
        draw_sharp_text(img, (1, 11), fit(draw, secondary, f["header"], 78), YELLOW, f["header"])
        tw = draw.textbbox((0, 0), fit(draw, tertiary, f["text"], 48), font=f["text"])[2]
        draw_sharp_text(img, (127 - tw, 21), fit(draw, tertiary, f["text"], 48), MUTED, f["text"])
    else:
        tw = draw.textbbox((0, 0), fit(draw, title, f["header"], 62), font=f["header"])[2]
        draw_sharp_text(img, ((64 - tw) // 2, -3), fit(draw, title, f["header"], 62), accent, f["header"])
        pw = draw.textbbox((0, 0), fit(draw, primary, f["header"], 62), font=f["header"])[2]
        draw_sharp_text(img, ((64 - pw) // 2, 9), fit(draw, primary, f["header"], 62), WHITE, f["header"])
        sw = draw.textbbox((0, 0), fit(draw, secondary, f["text"], 62), font=f["text"])[2]
        draw_sharp_text(img, ((64 - sw) // 2, 21), fit(draw, secondary, f["text"], 62), MUTED, f["text"])
    out = BytesIO()
    img.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def render_labeled_card(title, rows, status="", accent=BLUE, width=64):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, 32), (2, 9, 25))
    draw = ImageDraw.Draw(img)
    f = fonts()
    draw_background(img, draw)
    rows = list(rows or [])
    if width >= 128:
        draw_sharp_text(img, (1, -3), fit(draw, title, f["header"], 62), accent, f["header"])
        if status:
            status = fit(draw, status, f["header"], 62)
            sw = draw.textbbox((0, 0), status, font=f["header"])[2]
            draw_sharp_text(img, (127 - sw, -3), status, accent, f["header"])
        positions = [(1, 10), (65, 10), (1, 21), (65, 21)]
        for (label, value, color), (x, y) in zip(rows[:4], positions):
            text = fit(draw, f"{label} {value}", f["text"], 62)
            draw_sharp_text(img, (x, y), text, color or WHITE, f["text"])
    else:
        header = fit(draw, status or title, f["header"], 62)
        hw = draw.textbbox((0, 0), header, font=f["header"])[2]
        draw_sharp_text(img, ((64 - hw) // 2, -3), header, accent, f["header"])
        for index, (label, value, color) in enumerate(rows[:2]):
            text = fit(draw, f"{label} {value}", f["text"], 62)
            tw = draw.textbbox((0, 0), text, font=f["text"])[2]
            draw_sharp_text(img, ((64 - tw) // 2, 9 + index * 12), text, color or WHITE, f["text"])
    out = BytesIO()
    img.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def condition_color(label):
    text = safe_text(label).upper()
    if text in ("GOOD", "LOW", "CALM", "CLEAR"):
        return GREEN
    if text in ("FAIR", "MOD", "MODERATE"):
        return YELLOW
    return RED
