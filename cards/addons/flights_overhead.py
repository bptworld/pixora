from io import BytesIO
import hashlib
import json
import math
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from card_utils import (
    draw_sharp_text, fetch_airline_logo, fetch_json_request, lookup_airline,
    haversine_miles, compass_dir, format_distance_miles, format_speed_knots,
)

CARD_ID = "flights_overhead"
CARD_NAME = "Flights Overhead"
CARD_DETAIL = "Live overhead ADS-B with FlightStats routes"
CARD_OPTIONS = [
    {"key": "zipCode",        "label": "ZIP Code",       "type": "text",     "default": "10001", "maxlength": 5, "inputmode": "numeric"},
    {"key": "radiusMiles",    "label": "Radius (mi)",    "type": "number",   "default": "50"},
    {"key": "showAirliners",   "label": "Airliners",      "type": "checkbox", "default": True},
    {"key": "showRegionalJets", "label": "Regional jets", "type": "checkbox", "default": True},
    {"key": "showBusinessJets", "label": "Business jets", "type": "checkbox", "default": True},
    {"key": "showHelicopters", "label": "Helicopters",    "type": "checkbox", "default": True},
    {"key": "showSmallProps",  "label": "Small / prop",   "type": "checkbox", "default": False},
    {"key": "skipNoData",      "label": "Skip if no data", "type": "checkbox", "default": False},
    {
        "key": "source",
        "label": "Live Source",
        "type": "select",
        "default": "auto",
        "choices": [
            {"value": "auto", "label": "Auto"},
            {"value": "adsblol", "label": "ADSB.lol"},
            {"value": "adsbfi", "label": "adsb.fi"},
        ],
    },
]

_SOURCE_CACHE_SECONDS = 20
_ROUTE_CACHE_SECONDS = 3600
_FLIGHTSTATS_CACHE_SECONDS = 600
_SNAPSHOT_TTL_SECONDS = 20
_EMPTY_SNAPSHOT_TTL_SECONDS = 15
_FLIGHT_SLOT_SECONDS = 2
_ROUTE_CACHE = {}
_SNAPSHOT_CACHE = {}
_SNAPSHOT_PENDING = set()
_SNAPSHOT_LOCK = threading.RLock()
_ICAO_TO_IATA = {
    "AAL": "AA", "UAL": "UA", "DAL": "DL", "SWA": "WN", "ASA": "AS",
    "JBU": "B6", "FFT": "F9", "NKS": "NK", "HAL": "HA", "BAW": "BA",
    "AFR": "AF", "DLH": "LH", "UAE": "EK", "ACA": "AC",
}
_REGIONAL_JET_PREFIXES = ("CRJ", "CL", "E1", "E7", "E8", "E9", "ERJ")
_BUSINESS_JET_PREFIXES = ("C25", "C5", "C6", "C7", "C68", "C75", "E5", "F2", "F9", "FA", "GALX", "GL", "GLEX", "H25", "LJ", "PRM")
_AIRLINER_TYPES = {
    "A19", "A20", "A21", "A22", "A30", "A31", "A32", "A33", "A34", "A35", "A38",
    "B37", "B38", "B39", "B40", "B70", "B71", "B72", "B73", "B74", "B75", "B76", "B77", "B78",
    "MD8", "MD9", "B06", "BCS", "C919", "DC10", "DC9", "IL9", "L10",
}
_FLIGHTSTATS_ROOT = "https://www.flightstats.com/v2/api-next/flight-tracker"


def _is_wide(options):
    return (options or {}).get("_target") == "matrixportal-s3-128x32"


def _truthy(value):
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "on"}


def _skip_no_data(options):
    return _truthy((options or {}).get("skipNoData"))


def _zip_latlon(zip_code):
    loc = fetch_json_request(f"https://api.zippopotam.us/us/{zip_code}", seconds=86400)
    p = loc["places"][0]
    return float(p["latitude"]), float(p["longitude"])


def _extract_aircraft(data):
    if not isinstance(data, dict):
        return []
    rows = data.get("ac") or data.get("aircraft") or data.get("data") or []
    return rows if isinstance(rows, list) else []


def _clean(value):
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _airport_code(value):
    if isinstance(value, dict):
        value = value.get("iata_code") or value.get("icao_code") or value.get("iata") or value.get("icao")
    return _clean(value)[:4] or "---"


def _airport_latlon(value):
    if not isinstance(value, dict):
        return None
    try:
        lat = value.get("latitude")
        lon = value.get("longitude")
        if lat is None or lon is None:
            return None
        return float(lat), float(lon)
    except Exception:
        return None


def _bearing_degrees(lat1, lon1, lat2, lon2):
    lat1 = math.radians(float(lat1))
    lat2 = math.radians(float(lat2))
    dlon = math.radians(float(lon2) - float(lon1))
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _heading_delta(a, b):
    return abs((float(a) - float(b) + 180.0) % 360.0 - 180.0)


def _route_near_position(lat, lon, origin_pos, dest_pos):
    if lat is None or lon is None or not origin_pos or not dest_pos:
        return True
    try:
        route_miles = haversine_miles(origin_pos[0], origin_pos[1], dest_pos[0], dest_pos[1])
        if route_miles <= 0:
            return True
        via_plane = (
            haversine_miles(origin_pos[0], origin_pos[1], lat, lon)
            + haversine_miles(lat, lon, dest_pos[0], dest_pos[1])
        )
        slack = max(120.0, route_miles * 0.15)
        return via_plane <= route_miles + slack
    except Exception:
        return True


def _fetch_json_fast(url, seconds=600, timeout=1.2):
    import time

    now = time.time()
    cached = _ROUTE_CACHE.get(url)
    if cached and cached["expires"] > now:
        return cached["data"]
    request = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        if cached and "data" in cached:
            return cached["data"]
        raise
    _ROUTE_CACHE[url] = {"expires": now + seconds, "data": data}
    return data


def _display_ident_parts(callsign):
    callsign = _clean(callsign)
    if len(callsign) > 3 and callsign[:3] in _ICAO_TO_IATA and callsign[3:].isdigit():
        return _ICAO_TO_IATA[callsign[:3]], callsign[3:]
    airline = lookup_airline(callsign)
    if airline and airline[1] and callsign[3:].isdigit():
        return airline[1], callsign[3:]
    match = re.match(r"^([A-Z]{2,3})(\d+)$", callsign)
    return (match.group(1), match.group(2)) if match else ("", "")


def _local_midnights():
    now = time.localtime()
    today = int(time.mktime((now.tm_year, now.tm_mon, now.tm_mday, 0, 0, 0, 0, 0, -1)))
    return [today, today - 86400, today + 86400]


def _flightstats_route_for_callsign(callsign):
    airline, number = _display_ident_parts(callsign)
    if not airline or not number:
        return ""
    for day_ts in _local_midnights():
        day = time.localtime(day_ts)
        url = f"{_FLIGHTSTATS_ROOT}/{urllib.parse.quote(airline)}/{urllib.parse.quote(number)}/{day.tm_year}/{day.tm_mon}/{day.tm_mday}"
        try:
            data = _fetch_json_fast(url, seconds=_FLIGHTSTATS_CACHE_SECONDS, timeout=1.2)
        except urllib.error.HTTPError as err:
            if err.code in (400, 404):
                continue
            return ""
        except Exception:
            continue
        detail = data.get("data") if isinstance(data, dict) else {}
        if not isinstance(detail, dict):
            continue
        departure = detail.get("departureAirport") if isinstance(detail.get("departureAirport"), dict) else {}
        arrival = detail.get("arrivalAirport") if isinstance(detail.get("arrivalAirport"), dict) else {}
        origin = _airport_code(departure)
        dest = _airport_code(arrival)
        if origin != "---" or dest != "---":
            return f"{origin}>{dest}"
    return ""


def _route_for_callsign(callsign, lat=None, lon=None, track=None):
    callsign = _clean(callsign)
    if not callsign:
        return ""
    fs_route = _flightstats_route_for_callsign(callsign)
    if fs_route:
        return fs_route
    try:
        url = "https://api.adsbdb.com/v0/callsign/" + urllib.parse.quote(callsign)
        data = _fetch_json_fast(url, seconds=_ROUTE_CACHE_SECONDS, timeout=1.0)
        response = data.get("response") or {}
        route = response.get("flightroute") or response
        origin_raw = route.get("origin")
        dest_raw = route.get("destination")
        origin = _airport_code(origin_raw)
        dest = _airport_code(dest_raw)
        origin_pos = _airport_latlon(origin_raw)
        dest_pos = _airport_latlon(dest_raw)
        if lat is not None and lon is not None and track is not None and origin_pos and dest_pos:
            try:
                to_origin = _bearing_degrees(lat, lon, origin_pos[0], origin_pos[1])
                to_dest = _bearing_degrees(lat, lon, dest_pos[0], dest_pos[1])
                if _heading_delta(track, to_origin) + 35 < _heading_delta(track, to_dest):
                    origin, dest = dest, origin
                    origin_pos, dest_pos = dest_pos, origin_pos
            except Exception:
                pass
        if not _route_near_position(lat, lon, origin_pos, dest_pos):
            return f"{origin}>" if origin != "---" else ""
        if origin != "---" or dest != "---":
            return f"{origin}>{dest}"
    except Exception:
        pass
    return ""


def _fetch_source(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return _extract_aircraft(json.loads(response.read().decode("utf-8")))
    except urllib.error.HTTPError as err:
        if err.code in (400, 404):
            return []
        raise


def _fetch_adsb_lol(lat, lon, radius_nm):
    url = (
        "https://api.adsb.lol/v2/lat/"
        + urllib.parse.quote(f"{lat:.5f}")
        + "/lon/"
        + urllib.parse.quote(f"{lon:.5f}")
        + "/dist/"
        + urllib.parse.quote(str(radius_nm))
    )
    return _fetch_source(url)


def _fetch_adsb_fi(lat, lon, radius_nm):
    url = (
        "https://opendata.adsb.fi/api/v3/lat/"
        + urllib.parse.quote(f"{lat:.5f}")
        + "/lon/"
        + urllib.parse.quote(f"{lon:.5f}")
        + "/dist/"
        + urllib.parse.quote(str(radius_nm))
    )
    return _fetch_source(url)


def _fetch_aircraft(lat, lon, radius_miles, source):
    radius_nm = max(1, min(250, int(round(float(radius_miles) / 1.15078))))
    providers = []
    if source in ("auto", "adsblol"):
        providers.append(_fetch_adsb_lol)
    if source in ("auto", "adsbfi"):
        providers.append(_fetch_adsb_fi)
    results = []
    errors = []
    result_lock = threading.Lock()

    def fetch(provider):
        try:
            found = provider(lat, lon, radius_nm)
            with result_lock:
                results.append(found)
        except Exception as exc:
            with result_lock:
                errors.append(exc)

    workers = [threading.Thread(target=fetch, args=(provider,), daemon=True) for provider in providers]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=4)
    if not results:
        raise RuntimeError("Live flight sources unavailable") from (errors[0] if errors else None)

    rows = []
    seen = set()
    for result in results:
        for row in result:
            key = str(row.get("hex") or row.get("icao24") or row.get("flight") or id(row)).lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def _draw_wide_flight(row):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (128, 32), (0, 5, 18))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()
    draw.rectangle((0, 0, 127, 6), fill=(0, 15, 45))
    title = "FLIGHTS OVERHEAD"
    tw = draw.textbbox((0, 0), title, font=bold)[2]
    draw_sharp_text(image, ((128 - tw) // 2, -3), title, (100, 190, 255), bold)

    iata = row["iata"]
    logo = fetch_airline_logo(iata) if iata else None
    tx = 4
    if logo:
        image.paste(logo, (3, 8), logo)
        tx = 20
    else:
        _draw_plane_icon(draw, 2, 11)
        tx = 20
    alt_str = f"{row['alt_ft'] // 1000}K ft" if row["alt_ft"] >= 1000 else f"{row['alt_ft']}ft"
    spd_str = format_speed_knots(row["speed_kt"]).lower()
    stats = f"{alt_str}  {spd_str}"
    sw = draw.textbbox((0, 0), stats, font=font)[2]
    stats_x = 127 - sw
    flight = _fit_text(draw, row["flight"], bold, max(12, stats_x - tx - 4))
    draw_sharp_text(image, (tx, 6), flight, (255, 255, 255), bold)
    tail = _clean(row.get("registration") or row.get("hex"))[:8]
    tail_w = draw.textbbox((0, 0), tail, font=font)[2] if tail else 0
    airline_max = max(16, 126 - tx - tail_w - (4 if tail else 0))
    airline = _fit_text(draw, row["airline"], font, airline_max)
    draw_sharp_text(image, (tx, 13), airline, (100, 190, 255), font)
    if tail:
        draw_sharp_text(image, (127 - tail_w, 13), tail, (200, 230, 255), font)
    draw_sharp_text(image, (stats_x, 6), stats, (200, 230, 255), font)
    route = (row.get("route") or "")[:12]
    line4 = f"{format_distance_miles(row['distance'], 0)} {row['direction']}"
    if route:
        draw_sharp_text(image, (tx, 20), route, (150, 200, 255), font)
    lw = draw.textbbox((0, 0), line4[:12], font=font)[2]
    draw_sharp_text(image, (127 - lw, 20), line4[:12], (150, 200, 255), font)
    return image


def _draw_plane_icon(draw, x, y):
    body = (110, 185, 255)
    wing = (170, 220, 255)
    shadow = (35, 70, 110)
    draw.line((x + 0, y + 7, x + 15, y + 2), fill=body, width=2)
    draw.polygon([(x + 6, y + 5), (x + 1, y + 0), (x + 10, y + 4)], fill=wing)
    draw.polygon([(x + 8, y + 5), (x + 4, y + 12), (x + 12, y + 5)], fill=body)
    draw.line((x + 2, y + 8, x + 0, y + 11), fill=shadow)
    draw.line((x + 13, y + 2, x + 16, y + 1), fill=(230, 245, 255))


def _draw_plane_icon_small(draw, x, y):
    body = (110, 185, 255)
    wing = (170, 220, 255)
    shadow = (35, 70, 110)
    draw.line((x + 0, y + 6, x + 12, y + 2), fill=body)
    draw.polygon([(x + 5, y + 4), (x + 1, y + 1), (x + 8, y + 4)], fill=wing)
    draw.polygon([(x + 7, y + 5), (x + 4, y + 10), (x + 10, y + 5)], fill=body)
    draw.line((x + 1, y + 7, x + 0, y + 9), fill=shadow)


def _draw_64_flight(row):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (64, 32), (0, 5, 18))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    draw.rectangle((0, 0, 63, 6), fill=(0, 15, 45))
    logo = fetch_airline_logo(row["iata"]) if row["iata"] else None
    tx = 1
    airline_x = 1
    if logo:
        image.paste(logo, (1, -1), logo)
        tx = 14
    else:
        _draw_plane_icon_small(draw, 1, 0)
        tx = 15
        airline_x = 15

    draw_sharp_text(image, (tx, -3), row["flight"][:9], (255, 255, 255), bold)
    subtitle = row.get("route") or row["airline"]
    draw_sharp_text(image, (airline_x, 7), subtitle[:10], (100, 190, 255), font)
    alt_str = f"{row['alt_ft'] // 1000}K ft" if row["alt_ft"] >= 1000 else f"{row['alt_ft']}ft"
    spd_str = format_speed_knots(row["speed_kt"]).lower()
    draw_sharp_text(image, (1, 15), alt_str, (200, 230, 255), font)
    sw = draw.textbbox((0, 0), spd_str, font=font)[2]
    draw_sharp_text(image, (63 - sw, 15), spd_str, (200, 230, 255), font)
    line4 = f"{format_distance_miles(row['distance'], 0)} {row['direction']}"
    draw_sharp_text(image, (1, 22), line4[:14], (150, 200, 255), font)
    return image


def _render_wide_flight(flight_num, airline_name, iata, alt_ft, speed_kt, line4):
    row = {
        "flight": flight_num,
        "airline": airline_name,
        "iata": iata,
        "alt_ft": alt_ft,
        "speed_kt": speed_kt,
        "distance": 0,
        "direction": "",
        "route": "",
    }
    image = _draw_wide_flight(row)
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        font = ImageFont.load_default()
    lw = draw.textbbox((0, 0), line4[:22], font=font)[2]
    draw.rectangle((64, 20, 127, 31), fill=(0, 5, 18))
    draw_sharp_text(image, (127 - lw, 20), line4[:22], (150, 200, 255), font)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _num(value, default=0.0):
    try:
        if value == "ground":
            return 0.0
        return float(value)
    except Exception:
        return default


def _display_flight(callsign):
    airline = lookup_airline(callsign)
    if airline and airline[1] and callsign[3:]:
        return airline[1] + callsign[3:]
    if len(callsign) > 3 and callsign[:3] in _ICAO_TO_IATA:
        return _ICAO_TO_IATA[callsign[:3]] + callsign[3:]
    return callsign


def _aircraft_bucket(row):
    type_code = _clean(row.get("t") or row.get("type") or row.get("typeCode") or "")
    category = _clean(row.get("category") or row.get("categoryDescription") or "")
    callsign = _clean(row.get("flight") or row.get("callsign") or "")
    airline = lookup_airline(callsign)
    helicopter_type_codes = {"H53", "H53S", "H64", "HUCO", "SUCO", "UH1Y", "V22"}
    if type_code in helicopter_type_codes:
        return "helicopter"
    if category in ("A5", "A6"):
        return "heavy"
    if category == "A4":
        return "airliner"
    if category == "A7":
        return "helicopter"
    if type_code:
        if type_code.startswith(("H", "R22", "R44", "R66")):
            return "helicopter"
        if type_code[:3] in _AIRLINER_TYPES or type_code[:4] in _AIRLINER_TYPES:
            return "airliner"
        if type_code.startswith(_REGIONAL_JET_PREFIXES):
            return "regional"
        if type_code.startswith(_BUSINESS_JET_PREFIXES):
            return "business"
        if type_code.startswith(("AT", "DH", "DHC", "SF", "SB", "SW", "BE", "C1", "C2", "C3", "C4", "P", "PA")):
            return "prop"
    if airline:
        return "airliner"
    return "prop"


def _allowed_buckets(opts):
    allowed = set()
    if _truthy(opts.get("showAirliners", True)):
        allowed.update(("airliner", "heavy"))
    if _truthy(opts.get("showRegionalJets", True)):
        allowed.add("regional")
    if _truthy(opts.get("showBusinessJets", True)):
        allowed.add("business")
    if _truthy(opts.get("showHelicopters", True)):
        allowed.add("helicopter")
    if _truthy(opts.get("showSmallProps", False)):
        allowed.add("prop")
    return allowed or {"airliner", "heavy", "regional"}


def _flight_row(home_lat, home_lon, item, rank, enrich_route=True):
    dist, row = item
    callsign = (row.get("flight") or row.get("callsign") or "").strip().upper()
    alt_ft = int(_num(row.get("alt_baro") if row.get("alt_baro") != "ground" else row.get("alt_geom")))
    speed_kt = int(_num(row.get("gs") or row.get("speed")))
    lat = _num(row.get("lat"), None)
    lon = _num(row.get("lon"), None)
    track = _num(row.get("track") or row.get("true_heading") or row.get("mag_heading"), None)
    direction = compass_dir(home_lat, home_lon, lat, lon)
    airline = lookup_airline(callsign)
    airline_name = airline[0] if airline else callsign[:8]
    iata = airline[1] if airline else _ICAO_TO_IATA.get(callsign[:3])
    flight_num = _display_flight(callsign)
    route = _route_for_callsign(callsign, lat=lat, lon=lon, track=track) if enrich_route else ""
    return {
        "rank": rank,
        "callsign": callsign,
        "flight": flight_num or "UNKNOWN",
        "airline": airline_name or "UNKNOWN",
        "iata": iata,
        "registration": _clean(row.get("r") or row.get("reg") or row.get("registration")),
        "hex": _clean(row.get("hex") or row.get("icao24")),
        "distance": dist,
        "direction": direction,
        "alt_ft": alt_ft,
        "speed_kt": speed_kt,
        "route": route,
        "_lat": lat,
        "_lon": lon,
        "_track": track,
    }


def _render_message(message, wide=False):
    from PIL import Image, ImageDraw, ImageFont

    width = 128 if wide else 64
    image = Image.new("RGB", (width, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        font = ImageFont.load_default()
    title = "FLIGHTS OVERHEAD" if wide else "OVERHEAD"
    tw = draw.textbbox((0, 0), title, font=font)[2]
    draw_sharp_text(image, ((width - tw) // 2, -3), title, (100, 190, 255), font)
    words = str(message or "NO FLIGHTS").upper().split()
    lines = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > width - 2:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    for index, line in enumerate(lines[:3]):
        lw = draw.textbbox((0, 0), line, font=font)[2]
        draw_sharp_text(image, ((width - lw) // 2, 8 + index * 7), line, (255, 220, 90), font)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _fit_text(draw, text, font, max_width):
    text = str(text or "")
    while text and _text_width(draw, text, font) > max_width:
        text = text[:-1]
    return text


def _dwell_seconds(opts):
    try:
        return max(3, min(120, int((opts or {}).get("_dwell") or 10)))
    except Exception:
        return 10


def _limit_rows_for_dwell(rows, opts):
    count = max(1, _dwell_seconds(opts) // _FLIGHT_SLOT_SECONDS)
    return list(rows or [])[:count]


def _render_wide_list(rows, opts):
    frames = []
    for row in _limit_rows_for_dwell(rows, opts):
        frames.append(_draw_wide_flight(row))
    return _save_cycle(frames)


def _render_64_list(rows, opts):
    frames = []
    for row in _limit_rows_for_dwell(rows, opts):
        frames.append(_draw_64_flight(row))
    return _save_cycle(frames)


def _save_cycle(frames):
    durations = [_FLIGHT_SLOT_SECONDS * 1000 for _ in frames]
    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        lossless=True,
        quality=100,
    )
    return {
        "body": out.getvalue(),
        "dwell_secs": max(_FLIGHT_SLOT_SECONDS, len(frames) * _FLIGHT_SLOT_SECONDS),
        "_frame_durations_ms": durations,
        "_stay": False,
    }


def _snapshot_key(opts):
    keys = [
        "zipCode", "radiusMiles", "source", "showAirliners", "showRegionalJets",
        "showBusinessJets", "showHelicopters", "showSmallProps",
    ]
    payload = {key: str((opts or {}).get(key) or "") for key in keys}
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _build_snapshot(opts, enrich_routes=False):
    zip_code = (opts.get("zipCode") or "10001").strip()
    radius = max(10, min(500, int(opts.get("radiusMiles") or 50)))
    source = str(opts.get("source") or "auto").lower()
    allowed_buckets = _allowed_buckets(opts)

    lat, lon = _zip_latlon(zip_code)
    aircraft = _fetch_aircraft(lat, lon, radius, source)

    flights = []
    for row in aircraft:
        if row.get("alt_baro") == "ground" or (row.get("lat") is None or row.get("lon") is None):
            continue
        if _aircraft_bucket(row) not in allowed_buckets:
            continue
        row_lat = _num(row.get("lat"), None)
        row_lon = _num(row.get("lon"), None)
        if row_lat is None or row_lon is None:
            continue
        dist = haversine_miles(lat, lon, row_lat, row_lon)
        if dist <= radius:
            flights.append((dist, row))
    flights.sort(key=lambda x: x[0])
    rows = [_flight_row(lat, lon, item, index + 1, enrich_route=enrich_routes) for index, item in enumerate(flights[:20])]
    return {"rows": rows, "radius": radius, "updated": time.time()}


def _publish_snapshot(key, snapshot):
    with _SNAPSHOT_LOCK:
        current = _SNAPSHOT_CACHE.get(key)
        if snapshot.get("rows") or not (current and current.get("rows")):
            _SNAPSHOT_CACHE[key] = snapshot
        else:
            current["expires"] = snapshot.get("expires") or time.time() + _SNAPSHOT_TTL_SECONDS
            current["error"] = snapshot.get("error") or ""


def _enrich_snapshot_routes(key, snapshot):
    rows = snapshot.get("rows") or []
    for index, row in enumerate(rows):
        route = _route_for_callsign(
            row.get("callsign"), lat=row.get("_lat"), lon=row.get("_lon"), track=row.get("_track")
        )
        if route:
            row["route"] = route
            with _SNAPSHOT_LOCK:
                current = _SNAPSHOT_CACHE.get(key)
                if current is snapshot and index < len(current.get("rows") or []):
                    current["rows"][index]["route"] = route


def _enrich_snapshot_routes_async(key, snapshot):
    def enrich():
        try:
            _enrich_snapshot_routes(key, snapshot)
        finally:
            with _SNAPSHOT_LOCK:
                _SNAPSHOT_PENDING.discard(key)

    with _SNAPSHOT_LOCK:
        if key in _SNAPSHOT_PENDING:
            return
        _SNAPSHOT_PENDING.add(key)
    threading.Thread(target=enrich, name="pixora-flights-overhead-routes", daemon=True).start()


def _refresh_snapshot(key, opts):
    try:
        now = time.time()
        try:
            snapshot = _build_snapshot(opts, enrich_routes=False)
            expires = now + (_SNAPSHOT_TTL_SECONDS if snapshot.get("rows") else _EMPTY_SNAPSHOT_TTL_SECONDS)
            snapshot["expires"] = expires
        except Exception as exc:
            snapshot = {"rows": [], "radius": max(10, min(500, int((opts or {}).get("radiusMiles") or 50))), "error": str(exc), "updated": now, "expires": now + _EMPTY_SNAPSHOT_TTL_SECONDS}
        _publish_snapshot(key, snapshot)
        if snapshot.get("rows"):
            _enrich_snapshot_routes(key, snapshot)
    finally:
        with _SNAPSHOT_LOCK:
            _SNAPSHOT_PENDING.discard(key)


def _queue_snapshot_refresh(key, opts):
    now = time.time()
    with _SNAPSHOT_LOCK:
        snapshot = _SNAPSHOT_CACHE.get(key)
        stale = not snapshot or snapshot.get("expires", 0) <= now
        if not stale or key in _SNAPSHOT_PENDING:
            return snapshot
        _SNAPSHOT_PENDING.add(key)
    thread = threading.Thread(target=_refresh_snapshot, args=(key, dict(opts)), name="pixora-flights-overhead-refresh", daemon=True)
    thread.start()
    return snapshot


def _render_snapshot(snapshot, opts, wide):
    rows = (snapshot or {}).get("rows") or []
    if rows:
        return _render_wide_list(rows, opts) if wide else _render_64_list(rows, opts)
    if _skip_no_data(opts):
        return None
    radius = (snapshot or {}).get("radius") or max(10, min(500, int((opts or {}).get("radiusMiles") or 50)))
    if (snapshot or {}).get("error"):
        return _render_message("Flight data unavailable", wide)
    return _render_message(f"No flights within {radius} mi", wide)


def render(options=None):
    opts = options or {}
    wide = _is_wide(opts)
    key = _snapshot_key(opts)
    if _truthy(opts.get("_is_prefetch")):
        with _SNAPSHOT_LOCK:
            snapshot = _SNAPSHOT_CACHE.get(key)
            if snapshot and snapshot.get("expires", 0) <= time.time():
                snapshot = None
        if snapshot:
            return _render_snapshot(snapshot, opts, wide)
        try:
            snapshot = _build_snapshot(opts, enrich_routes=False)
            snapshot["expires"] = time.time() + (_SNAPSHOT_TTL_SECONDS if snapshot.get("rows") else _EMPTY_SNAPSHOT_TTL_SECONDS)
        except Exception as exc:
            snapshot = {"rows": [], "radius": max(10, min(500, int(opts.get("radiusMiles") or 50))), "error": str(exc), "updated": time.time(), "expires": time.time() + _EMPTY_SNAPSHOT_TTL_SECONDS}
        _publish_snapshot(key, snapshot)
        if snapshot.get("rows"):
            _enrich_snapshot_routes_async(key, snapshot)
        return _render_snapshot(snapshot, opts, wide)

    snapshot = _queue_snapshot_refresh(key, opts)
    if not snapshot:
        if _skip_no_data(opts):
            return None
        return _render_message("Updating flights", wide)
    return _render_snapshot(snapshot, opts, wide)
