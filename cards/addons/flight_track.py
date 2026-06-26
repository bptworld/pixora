import atexit
from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import re
import time
import threading
import urllib.error
import urllib.parse
import urllib.request

from card_utils import (
    compass_dir,
    draw_sharp_text,
    fetch_airline_logo,
    format_distance_miles,
    format_speed_knots,
    haversine_miles,
    iata_to_icao_prefix,
    lookup_airline,
)
from PIL import ImageEnhance, ImageFilter

try:
    from PIL import ImageFont
    FONT_7 = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    FONT_BOLD = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
except Exception:
    from PIL import ImageFont
    FONT_7 = FONT_BOLD = ImageFont.load_default()

CARD_ID = "flight_track"
CARD_NAME = "Flight Tracker"
CARD_DETAIL = "Live ADS-B tracking with FlightStats route details"
_AIRLINE_CHOICES = [
    {"value": "AA", "label": "American"},
    {"value": "UA", "label": "United"},
    {"value": "DL", "label": "Delta"},
    {"value": "WN", "label": "Southwest"},
    {"value": "AS", "label": "Alaska"},
    {"value": "B6", "label": "JetBlue"},
    {"value": "F9", "label": "Frontier"},
    {"value": "NK", "label": "Spirit"},
    {"value": "HA", "label": "Hawaiian"},
    {"value": "BA", "label": "British Airways"},
    {"value": "AF", "label": "Air France"},
    {"value": "LH", "label": "Lufthansa"},
    {"value": "EK", "label": "Emirates"},
    {"value": "AC", "label": "Air Canada"},
]

CARD_OPTIONS = []
for _idx in range(1, 5):
    CARD_OPTIONS.extend([
        {
            "key": f"airline{_idx}",
            "label": f"Airline {_idx}",
            "type": "select",
            "default": "WN" if _idx == 1 else "",
            "choices": ([{"value": "", "label": "-"}] if _idx > 1 else []) + _AIRLINE_CHOICES,
        },
        {
            "key": f"flightNumber{_idx}",
            "label": f"Flight # {_idx}",
            "type": "text",
            "default": "3416" if _idx == 1 else "",
            "maxlength": 6,
            "inputmode": "numeric",
        },
        {"key": f"origin{_idx}", "label": f"Origin {_idx}", "type": "text", "default": "", "maxlength": 4},
        {"key": f"destination{_idx}", "label": f"Destination {_idx}", "type": "text", "default": "", "maxlength": 4},
    ])
CARD_OPTIONS.extend([
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
    {"key": "homeZip", "label": "Home ZIP", "type": "text", "default": "", "maxlength": 5, "inputmode": "numeric"},
    {"key": "repeatDaily", "label": "Track same flight number daily", "type": "checkbox", "default": True},
    {"key": "skipNoData", "label": "Skip if no data", "type": "checkbox", "default": False},
    {
        "key": "landingGraphicTarget",
        "label": "Landing Graphic",
        "type": "select",
        "default": "device",
        "choices": [
            {"value": "device", "label": "Device"},
            {"value": "group_wall", "label": "Group Wall"},
        ],
    },
])
del _idx

_AIRPORT_CITY = {
    "ATL": "ATLANTA", "BOS": "BOSTON", "BWI": "BALTIMORE", "DCA": "WASHINGTON",
    "DEN": "DENVER", "DFW": "DALLAS", "EWR": "NEWARK", "IAD": "WASHINGTON",
    "JFK": "NEW YORK", "LAS": "LAS VEGAS", "LAX": "LOS ANGELES", "LGA": "NEW YORK",
    "MCO": "ORLANDO", "MHT": "MANCHESTER", "ORD": "CHICAGO", "PHX": "PHOENIX",
    "SEA": "SEATTLE", "SFO": "SAN FRANCISCO", "TPA": "TAMPA",
}
_COASTAL_PLACES = [
    ("BOSTON", "MA", 42.3601, -71.0589), ("PROVIDENCE", "RI", 41.8240, -71.4128),
    ("NEW YORK", "NY", 40.7128, -74.0060), ("ATLANTIC CITY", "NJ", 39.3643, -74.4229),
    ("CAPE MAY", "NJ", 38.9351, -74.9060), ("OCEAN CITY", "MD", 38.3365, -75.0849),
    ("VIRGINIA BEACH", "VA", 36.8529, -75.9780), ("WILMINGTON", "NC", 34.2104, -77.8868),
    ("MYRTLE BEACH", "SC", 33.6891, -78.8867), ("CHARLESTON", "SC", 32.7765, -79.9311),
    ("SAVANNAH", "GA", 32.0809, -81.0912), ("JACKSONVILLE", "FL", 30.3322, -81.6557),
    ("DAYTONA BEACH", "FL", 29.2108, -81.0228), ("MELBOURNE", "FL", 28.0836, -80.6081),
    ("MIAMI", "FL", 25.7617, -80.1918), ("NASSAU", "BS", 25.0443, -77.3504),
]
_WATER_KEYS = ("ocean", "sea", "bay", "strait", "sound", "gulf", "water", "waterway")
_ICAO_TO_IATA = {
    "AAL": "AA", "UAL": "UA", "DAL": "DL", "SWA": "WN", "ASA": "AS",
    "JBU": "B6", "FFT": "F9", "NKS": "NK", "HAL": "HA", "BAW": "BA",
    "AFR": "AF", "DLH": "LH", "UAE": "EK", "ACA": "AC",
}
_MARKETING_OPERATOR_PREFIXES = {
    "AA": ["AAL", "ENY", "JIA", "PDT", "RPA", "SKW"],
    "AC": ["ACA", "JZA"],
    "AS": ["ASA", "QXE", "SKW"],
    "B6": ["JBU"],
    "DL": ["DAL", "EDV", "RPA", "SKW"],
    "UA": ["UAL", "SKW", "RPA", "AWI", "GJS", "ASH"],
}
_STATE_ABBR = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA",
    "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE", "DISTRICT OF COLUMBIA": "DC",
    "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL",
    "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA",
    "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI",
    "MINNESOTA": "MN", "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT",
    "NEBRASKA": "NE", "NEVADA": "NV", "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND",
    "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR", "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD", "TENNESSEE": "TN",
    "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
}
_SOURCE_CACHE_SECONDS = 20
_ENRICH_CACHE_SECONDS = 3600
_SOURCE_HTTP_TIMEOUT = 1.2
_ENRICH_HTTP_TIMEOUT = 0.7
_REFRESH_BUDGET_SECONDS = 45.0
_SNAPSHOT_TTL_SECONDS = 300
_WELCOME_RENDER_COUNT = 5
_LANDING_PHOTO_CACHE = None
_JSON_CACHE_MAX_ENTRIES = 128
_SNAPSHOT_CACHE_MAX_ENTRIES = 32
_JSON_CACHE = {}
_SNAPSHOT_CACHE = {}
_SNAPSHOT_PENDING = set()
_SNAPSHOT_LOCK = threading.Lock()
_MAP_TILE_CACHE = {}
_US_STATE_LINES_CACHE = None
_LAST_FLIGHT_POS = {}
_SNAPSHOT_POOL = None
_SNAPSHOT_WATCHED = {}
_SCHEDULER_THREAD = None
_SCHEDULER_STOP = threading.Event()
_LANDED_FLIGHT_EVENTS = {}
_MAP_TILE_SIZE = 256
_MAP_TILE_STYLE = "carto-light-nolabels-v1"
_US_STATE_GEOJSON_URL = "https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json"
_FLIGHTSTATS_ROOT = "https://www.flightstats.com/v2/api-next/flight-tracker"
_FLIGHTSTATS_CACHE_SECONDS = 600
_FLIGHTSTATS_TIMEOUT = 1.4


def _is_wide(options):
    opts = options or {}
    if opts.get("_target") == "matrixportal-s3-128x32" or opts.get("_pixora_target") == "pixora-s3-wide":
        return True
    try:
        return int(opts.get("_width") or 0) >= 96
    except Exception:
        return False


def _truthy(value):
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "on"}


def _skip_no_data(options):
    return _truthy((options or {}).get("skipNoData"))


def _is_no_data_error(error):
    text = str(error or "").strip().lower()
    return not text or text.startswith("no live data")


def _clean(value):
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _time_left(deadline):
    if deadline is None:
        return 999.0
    return max(0.0, deadline - time.monotonic())


def _snapshot_pool():
    global _SNAPSHOT_POOL
    if _SNAPSHOT_POOL is None:
        _SNAPSHOT_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pixora-flight-track")
    return _SNAPSHOT_POOL


def _shutdown_snapshot_pool():
    _SCHEDULER_STOP.set()
    if _SNAPSHOT_POOL is not None:
        _SNAPSHOT_POOL.shutdown(wait=False, cancel_futures=True)


atexit.register(_shutdown_snapshot_pool)


def _ensure_snapshot_scheduler():
    global _SCHEDULER_THREAD
    if _SCHEDULER_THREAD is not None and _SCHEDULER_THREAD.is_alive():
        return
    _SCHEDULER_STOP.clear()
    _SCHEDULER_THREAD = threading.Thread(target=_snapshot_scheduler_loop, name="pixora-flight-track-scheduler", daemon=True)
    _SCHEDULER_THREAD.start()


def _snapshot_scheduler_loop():
    while not _SCHEDULER_STOP.wait(10):
        now = time.time()
        due = []
        with _SNAPSHOT_LOCK:
            _prune_snapshot_state(now)
            for key, opts in list(_SNAPSHOT_WATCHED.items()):
                snapshot = _SNAPSHOT_CACHE.get(key)
                if key not in _SNAPSHOT_PENDING and (not snapshot or snapshot.get("expires", 0) <= now):
                    _SNAPSHOT_PENDING.add(key)
                    due.append((key, dict(opts)))
        for key, opts in due:
            _snapshot_pool().submit(_refresh_snapshot, key, opts)


def _fetch_json(url, seconds=600, timeout=2.0, deadline=None):
    now = time.time()
    _prune_json_cache(now)
    cached = _JSON_CACHE.get(url)
    if cached and cached["expires"] > now:
        return cached["data"]
    if _time_left(deadline) < 0.2:
        if cached:
            return cached["data"]
        raise TimeoutError("flight render budget exhausted")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Pixora/0.1", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=max(0.2, min(timeout, _time_left(deadline)))) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        if cached and "data" in cached:
            return cached["data"]
        raise
    _JSON_CACHE[url] = {"expires": now + seconds, "data": data}
    _prune_json_cache(now)
    return data


def _prune_json_cache(now):
    for key, item in list(_JSON_CACHE.items()):
        if item.get("expires", 0) <= now:
            _JSON_CACHE.pop(key, None)
    while len(_JSON_CACHE) > _JSON_CACHE_MAX_ENTRIES:
        _JSON_CACHE.pop(next(iter(_JSON_CACHE)), None)


def _prune_snapshot_state(now):
    for key, item in list(_SNAPSHOT_CACHE.items()):
        if item.get("expires", 0) <= now and key not in _SNAPSHOT_WATCHED:
            _SNAPSHOT_CACHE.pop(key, None)
    while len(_SNAPSHOT_WATCHED) > _SNAPSHOT_CACHE_MAX_ENTRIES:
        key = next(iter(_SNAPSHOT_WATCHED))
        _SNAPSHOT_WATCHED.pop(key, None)
        _SNAPSHOT_CACHE.pop(key, None)
        _SNAPSHOT_PENDING.discard(key)
    while len(_SNAPSHOT_CACHE) > _SNAPSHOT_CACHE_MAX_ENTRIES:
        key = next((item_key for item_key in _SNAPSHOT_CACHE if item_key not in _SNAPSHOT_WATCHED), None)
        if key is None:
            break
        _SNAPSHOT_CACHE.pop(key, None)
        _SNAPSHOT_PENDING.discard(key)


def _slot_value(opts, key, slot):
    value = opts.get(f"{key}{slot}")
    if slot == 1 and value in (None, ""):
        value = opts.get(key)
    return value


def _flight_ident(opts, use_icao=False, slot=1):
    number = "".join(ch for ch in str(_slot_value(opts, "flightNumber", slot) or "") if ch.isdigit())
    airline = _clean(_slot_value(opts, "airline", slot) or "")
    if use_icao and len(airline) == 2:
        airline = iata_to_icao_prefix(airline) or airline
    if airline and number:
        return airline + number
    return _clean(opts.get("callsign") or "")


def _candidate_callsigns(opts, slot=1):
    number = "".join(ch for ch in str(_slot_value(opts, "flightNumber", slot) or "") if ch.isdigit())
    airline = _clean(_slot_value(opts, "airline", slot) or "")
    explicit = _clean(opts.get("callsign") or "")
    candidates = []
    if explicit:
        candidates.append(explicit)
    if airline and number:
        primary = iata_to_icao_prefix(airline) if len(airline) == 2 else airline
        operator_prefixes = list(_MARKETING_OPERATOR_PREFIXES.get(airline, []))
        if primary and primary not in operator_prefixes:
            operator_prefixes.insert(0, primary)
        try:
            flight_no = int(number)
        except Exception:
            flight_no = 0
        if flight_no >= 3000:
            regional = [prefix for prefix in operator_prefixes if prefix != primary]
            ordered = regional + ([primary] if primary else [])
        else:
            ordered = ([primary] if primary else []) + [prefix for prefix in operator_prefixes if prefix != primary]
        for prefix in ordered:
            if prefix:
                candidates.append(prefix + number)
        candidates.append(airline + number)
    unique = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


def _route_option(opts, slot=1):
    origin = _clean(_slot_value(opts, "origin", slot) or "")[:4]
    dest = _clean(_slot_value(opts, "destination", slot) or "")[:4]
    if origin and dest:
        return origin, dest, "USER"
    return "", "", ""


def _airport_code(value):
    if isinstance(value, dict):
        value = value.get("fs") or value.get("iata_code") or value.get("icao_code") or value.get("iata") or value.get("icao")
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


def _airport_lookup_latlon(code, deadline=None):
    code = _clean(code)[:4]
    if not code or code == "---" or _time_left(deadline) < 0.5:
        return None
    query = urllib.parse.urlencode({"format": "jsonv2", "limit": "1", "q": f"{code} airport"})
    url = "https://nominatim.openstreetmap.org/search?" + query
    try:
        data = _fetch_json(url, seconds=86400 * 7, timeout=1.2, deadline=deadline)
        if isinstance(data, list) and data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        return None
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


def _extract_aircraft(data):
    if not isinstance(data, dict):
        return []
    rows = data.get("ac") or data.get("aircraft") or data.get("data") or []
    return rows if isinstance(rows, list) else []


def _fetch_adsb_lol(callsign, deadline=None):
    url = "https://api.adsb.lol/v2/callsign/" + urllib.parse.quote(callsign)
    try:
        data = _fetch_json(url, seconds=_SOURCE_CACHE_SECONDS, timeout=_SOURCE_HTTP_TIMEOUT, deadline=deadline)
    except urllib.error.HTTPError as err:
        if err.code in (400, 404):
            return [], "ADSB.LOL"
        raise
    rows = _extract_aircraft(data)
    return rows, "ADSB.LOL"


def _fetch_adsb_fi(callsign, deadline=None):
    url = "https://opendata.adsb.fi/api/v3/callsign/" + urllib.parse.quote(callsign)
    try:
        data = _fetch_json(url, seconds=_SOURCE_CACHE_SECONDS, timeout=_SOURCE_HTTP_TIMEOUT, deadline=deadline)
    except urllib.error.HTTPError as err:
        if err.code in (400, 404):
            return [], "ADSB.FI"
        raise
    rows = _extract_aircraft(data)
    return rows, "ADSB.FI"


def _log(opts, message):
    logger = (opts or {}).get("_log")
    try:
        if callable(logger):
            logger(message)
    except Exception:
        pass


def _fetch_adsbdb_aircraft(hex_id, registration, deadline=None):
    key = _clean(hex_id or registration)
    if not key or _time_left(deadline) < 0.4:
        return {}
    try:
        url = "https://api.adsbdb.com/v0/aircraft/" + urllib.parse.quote(key)
        data = _fetch_json(url, seconds=_ENRICH_CACHE_SECONDS, timeout=_ENRICH_HTTP_TIMEOUT, deadline=deadline)
        return (data.get("response") or {}).get("aircraft") or data.get("aircraft") or {}
    except Exception:
        return {}


def _fetch_adsbdb_route(callsign, deadline=None):
    callsign = _clean(callsign)
    if not callsign or _time_left(deadline) < 0.4:
        return {}
    try:
        url = "https://api.adsbdb.com/v0/callsign/" + urllib.parse.quote(callsign)
        data = _fetch_json(url, seconds=_ENRICH_CACHE_SECONDS, timeout=_ENRICH_HTTP_TIMEOUT, deadline=deadline)
        response = data.get("response") or {}
        return response.get("flightroute") or response
    except Exception:
        return {}


def _flightstats_ident(opts, slot=1):
    airline = _clean(_slot_value(opts, "airline", slot) or "")[:3]
    number = "".join(ch for ch in str(_slot_value(opts, "flightNumber", slot) or "") if ch.isdigit())
    if airline and number:
        return airline, number
    ident = _flight_ident(opts, use_icao=False, slot=slot)
    match = re.match(r"^([A-Z]{2,3})(\d+)$", ident or "")
    return (match.group(1), match.group(2)) if match else ("", "")


def _flightstats_dates():
    today = datetime_local_date()
    return [today, today - 86400, today + 86400]


def datetime_local_date():
    now = time.localtime()
    return int(time.mktime((now.tm_year, now.tm_mon, now.tm_mday, 0, 0, 0, 0, 0, -1)))


def _fetch_flightstats_detail(opts, slot=1, deadline=None):
    airline, number = _flightstats_ident(opts, slot=slot)
    if not airline or not number or _time_left(deadline) < 0.6:
        return {}
    for day_ts in _flightstats_dates():
        if _time_left(deadline) < 0.6:
            break
        day = time.localtime(day_ts)
        url = f"{_FLIGHTSTATS_ROOT}/{urllib.parse.quote(airline)}/{urllib.parse.quote(number)}/{day.tm_year}/{day.tm_mon}/{day.tm_mday}"
        now = time.time()
        _prune_json_cache(now)
        cached = _JSON_CACHE.get(url)
        if cached and cached["expires"] > now:
            data = cached["data"]
        else:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Pixora/0.1)", "Accept": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=max(0.2, min(_FLIGHTSTATS_TIMEOUT, _time_left(deadline)))) as response:
                    data = json.loads(response.read().decode("utf-8"))
                _JSON_CACHE[url] = {"expires": now + _FLIGHTSTATS_CACHE_SECONDS, "data": data}
                _prune_json_cache(now)
            except urllib.error.HTTPError as err:
                if err.code in (400, 404):
                    continue
                if cached and "data" in cached:
                    data = cached["data"]
                else:
                    continue
            except Exception:
                if cached and "data" in cached:
                    data = cached["data"]
                else:
                    continue
        detail = data.get("data") if isinstance(data, dict) else {}
        if isinstance(detail, dict) and (detail.get("departureAirport") or detail.get("arrivalAirport")):
            return detail
    return {}


def _fs_airport(detail, key):
    value = detail.get(key) if isinstance(detail, dict) else {}
    return value if isinstance(value, dict) else {}


def _fs_time_text(airport):
    times = airport.get("times") if isinstance(airport, dict) else {}
    if not isinstance(times, dict):
        return ""
    value = times.get("estimatedActual") or times.get("scheduled") or {}
    if not isinstance(value, dict):
        return ""
    text = str(value.get("time") or "")
    ampm = str(value.get("ampm") or "")
    return (text + ampm[:1]).upper().replace(" ", "")


def _flightstats_summary(detail):
    if not isinstance(detail, dict):
        return {}
    departure = _fs_airport(detail, "departureAirport")
    arrival = _fs_airport(detail, "arrivalAirport")
    status = detail.get("status") if isinstance(detail.get("status"), dict) else {}
    note = detail.get("flightNote") if isinstance(detail.get("flightNote"), dict) else {}
    final_status = str(status.get("finalStatus") or status.get("status") or note.get("phase") or "").upper()
    status_text = str(status.get("statusDescription") or status.get("status") or note.get("message") or "").upper()
    gate = str(arrival.get("gate") or departure.get("gate") or "").upper()
    terminal = str(arrival.get("terminal") or departure.get("terminal") or "").upper()
    baggage = str(arrival.get("baggage") or "").upper()
    schedule = detail.get("schedule") if isinstance(detail.get("schedule"), dict) else {}
    additional = detail.get("additionalFlightInfo") if isinstance(detail.get("additionalFlightInfo"), dict) else {}
    equipment = additional.get("equipment") if isinstance(additional.get("equipment"), dict) else {}
    return {
        "origin": _airport_code(departure),
        "destination": _airport_code(arrival),
        "status": final_status or status_text,
        "status_text": status_text,
        "departure_time": _fs_time_text(departure),
        "arrival_time": _fs_time_text(arrival),
        "gate": gate,
        "terminal": terminal,
        "baggage": baggage,
        "aircraft": _clean(equipment.get("iata") or equipment.get("name") or "")[:10],
        "scheduled_arrival_utc": schedule.get("scheduledArrivalUTC") or "",
        "actual_arrival_utc": schedule.get("estimatedActualArrivalUTC") or "",
    }


def _home_latlon(zip_code):
    zip_code = re.sub(r"\D", "", str(zip_code or ""))[:5]
    if len(zip_code) != 5:
        return None
    try:
        loc = _fetch_json(f"https://api.zippopotam.us/us/{zip_code}", seconds=86400, timeout=1.0)
        place = loc["places"][0]
        return float(place["latitude"]), float(place["longitude"])
    except Exception:
        return None


def _city_state_from_latlon(lat, lon, deadline=None):
    if lat is None or lon is None or _time_left(deadline) < 0.6:
        return "", "", ""
    try:
        url = (
            "https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=10&addressdetails=1"
            f"&lat={float(lat):.5f}&lon={float(lon):.5f}"
        )
        data = _fetch_json(url, seconds=86400, timeout=1.2, deadline=deadline)
        address = data.get("address") or {}
        water = ""
        for key in _WATER_KEYS:
            if address.get(key):
                water = str(address.get(key)).upper()
                break
        if not water and data.get("name") and any(word in str(data.get("category") or data.get("type") or "").lower() for word in _WATER_KEYS):
            water = str(data.get("name")).upper()
        city = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or address.get("county")
            or ""
        )
        state = address.get("state") or ""
        iso = address.get("ISO3166-2-lvl4") or ""
        state = str(state).upper()
        if iso.startswith("US-") and len(iso) == 5:
            state = iso[-2:]
        else:
            state = _STATE_ABBR.get(state, state)
        return _clean_place_name(city), state, _clean_place_name(water)
    except Exception:
        return "", "", ""


def _clean_place_name(value):
    text = str(value or "").strip().upper()
    for prefix in ("TOWN OF ", "CITY OF ", "VILLAGE OF ", "BOROUGH OF ", "COUNTY OF "):
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def _nearby_water_place(lat, lon):
    if lat is None or lon is None:
        return "", ""
    try:
        nearest = min(
            _COASTAL_PLACES,
            key=lambda item: haversine_miles(float(lat), float(lon), item[2], item[3]),
        )
        distance = haversine_miles(float(lat), float(lon), nearest[2], nearest[3])
        if distance <= 180:
            return f"OFF {nearest[0]}", nearest[1]
        if -82.5 <= float(lon) <= -50 and 5 <= float(lat) <= 55:
            return "ATLANTIC OCEAN", ""
    except Exception:
        return "", ""
    return "", ""


def _num(value, default=0.0):
    try:
        if value == "ground":
            return 0.0
        return float(value)
    except Exception:
        return default


def _pick_aircraft(rows, callsign):
    callsign = _clean(callsign)
    usable = []
    for row in rows:
        row_callsign = _clean(row.get("flight") or row.get("callsign") or "")
        if callsign and row_callsign and row_callsign != callsign:
            continue
        if row.get("lat") is None or row.get("lon") is None:
            continue
        usable.append(row)
    if not usable:
        usable = rows
    if not usable:
        return None
    usable.sort(key=lambda row: (_num(row.get("seen_pos"), 999), _num(row.get("seen"), 999)))
    return usable[0]


def _load_live(opts, deadline=None):
    callsigns = []
    slot = int(opts.get("_slot") or 1)
    for ident in _candidate_callsigns(opts, slot):
        if ident and ident not in callsigns:
            callsigns.append(ident)
    if not callsigns:
        return None, "SET FLT"

    source = str(opts.get("source") or "auto").lower()
    providers = []
    if source in ("auto", "adsblol"):
        providers.append(_fetch_adsb_lol)
    if source in ("auto", "adsbfi"):
        providers.append(_fetch_adsb_fi)

    had_successful_lookup = False
    for provider in providers:
        if _time_left(deadline) < 0.4:
            break
        for callsign in callsigns:
            if _time_left(deadline) < 0.4:
                break
            try:
                rows, source_name = provider(callsign, deadline=deadline)
                had_successful_lookup = True
                if not rows:
                    _log(opts, f"[flight_track] {source_name} {callsign} returned 0 rows")
                row = _pick_aircraft(rows, callsign)
                if row:
                    return _build_flight(row, callsign, source_name, opts, deadline=deadline), None
            except Exception as exc:
                service = "ADSB.LOL" if provider is _fetch_adsb_lol else "ADSB.FI" if provider is _fetch_adsb_fi else getattr(provider, "__name__", "ADS-B")
                _log(opts, f"[flight_track] {service} {callsign} timed out/error: {type(exc).__name__}: {exc}")
                continue
    return None, "NO LIVE"


def _route_from_enrichment(callsign, opts, lat=None, lon=None, track=None, flightstats=None, deadline=None):
    user_origin, user_dest, source = _route_input(opts, int(opts.get("_slot") or 1))
    route = _fetch_adsbdb_route(callsign, deadline=deadline)
    fs_origin = _clean((flightstats or {}).get("origin") or "")[:4]
    fs_dest = _clean((flightstats or {}).get("destination") or "")[:4]
    origin = user_origin or fs_origin
    dest = user_dest or fs_dest
    route_source = source or ("FSTAT" if (fs_origin or fs_dest) else "ADSDB")
    route_origin_pos = _airport_latlon(route.get("origin"))
    route_dest_pos = _airport_latlon(route.get("destination"))
    origin_pos = _airport_lookup_latlon(origin, deadline=deadline) if origin else None
    dest_pos = _airport_lookup_latlon(dest, deadline=deadline) if dest else None
    if not origin:
        origin = _airport_code(route.get("origin"))
        origin_pos = route_origin_pos
    if not dest:
        dest = _airport_code(route.get("destination"))
        dest_pos = route_dest_pos
    if (origin and origin != "---") or (dest and dest != "---"):
        if not source and route_source != "FSTAT" and lat is not None and lon is not None and track is not None:
            if origin_pos and dest_pos:
                try:
                    to_origin = _bearing_degrees(lat, lon, origin_pos[0], origin_pos[1])
                    to_dest = _bearing_degrees(lat, lon, dest_pos[0], dest_pos[1])
                    origin_delta = _heading_delta(track, to_origin)
                    dest_delta = _heading_delta(track, to_dest)
                    if origin_delta + 35 < dest_delta:
                        origin, dest = dest, origin
                        origin_pos, dest_pos = dest_pos, origin_pos
                        route_source = "INFER"
                except Exception:
                    pass
        if not origin_pos:
            origin_pos = _airport_lookup_latlon(origin, deadline=deadline)
        if not dest_pos:
            dest_pos = _airport_lookup_latlon(dest, deadline=deadline)
        return origin or "---", dest or "---", route_source, origin_pos, dest_pos
    return "---", "---", "", None, None


def _route_input(opts, slot=1):
    origin = _clean(_slot_value(opts, "origin", slot) or "")[:4]
    dest = _clean(_slot_value(opts, "destination", slot) or "")[:4]
    source = "USER" if origin or dest else ""
    return origin, dest, source


def _position_cache_key(callsign, registration, hex_id):
    return _clean(hex_id or registration or callsign)


def _remember_position(callsign, registration, hex_id, lat, lon):
    if lat is None or lon is None:
        return
    key = _position_cache_key(callsign, registration, hex_id)
    if key:
        _LAST_FLIGHT_POS[key] = {"lat": float(lat), "lon": float(lon), "ts": time.time()}
    while len(_LAST_FLIGHT_POS) > 64:
        _LAST_FLIGHT_POS.pop(next(iter(_LAST_FLIGHT_POS)), None)


def _cached_position(callsign, registration, hex_id):
    key = _position_cache_key(callsign, registration, hex_id)
    item = _LAST_FLIGHT_POS.get(key) if key else None
    if not item or time.time() - item.get("ts", 0) > 3600:
        return None
    return item["lat"], item["lon"]


def _ground_position(callsign, registration, hex_id, origin_pos, dest_pos):
    cached = _cached_position(callsign, registration, hex_id)
    if cached:
        if origin_pos and dest_pos:
            origin_dist = haversine_miles(cached[0], cached[1], origin_pos[0], origin_pos[1])
            dest_dist = haversine_miles(cached[0], cached[1], dest_pos[0], dest_pos[1])
            return dest_pos if dest_dist + 8 < origin_dist else origin_pos
        return cached
    return origin_pos or dest_pos


def _build_flight(row, query_callsign, source_name, opts, deadline=None):
    callsign = _clean(row.get("flight") or row.get("callsign") or query_callsign)
    marketing_ident = _flight_ident(opts, use_icao=False, slot=int(opts.get("_slot") or 1))
    flightstats = _flightstats_summary(_fetch_flightstats_detail(opts, slot=int(opts.get("_slot") or 1), deadline=deadline))
    registration = _clean(row.get("r") or row.get("reg") or row.get("registration"))
    hex_id = _clean(row.get("hex") or row.get("icao24"))
    aircraft = _fetch_adsbdb_aircraft(hex_id, registration, deadline=deadline)
    aircraft_type = _clean(row.get("t") or row.get("typeCode") or aircraft.get("icao_type") or aircraft.get("type") or flightstats.get("aircraft"))[:10]
    description = str(row.get("desc") or aircraft.get("type") or aircraft.get("manufacturer") or "").upper()
    lat = _num(row.get("lat"), None)
    lon = _num(row.get("lon"), None)
    track = _num(row.get("track") or row.get("true_heading") or row.get("mag_heading"), None)
    origin, dest, route_source, origin_pos, dest_pos = _route_from_enrichment(callsign, opts, lat=lat, lon=lon, track=track, flightstats=flightstats, deadline=deadline)
    is_ground_row = row.get("alt_baro") == "ground" or (_num(row.get("gs")) < 35 and _num(row.get("alt_baro")) < 200)
    if lat is not None and lon is not None:
        _remember_position(callsign, registration, hex_id, lat, lon)
    elif is_ground_row:
        inferred_pos = _ground_position(callsign, registration, hex_id, origin_pos, dest_pos)
        if inferred_pos:
            lat, lon = inferred_pos
    over_city, over_state, over_water = _city_state_from_latlon(lat, lon, deadline=deadline)
    if not over_city and not over_water:
        offshore_place, offshore_state = _nearby_water_place(lat, lon)
        over_city = offshore_place
        over_state = offshore_state or over_state
    return {
        "callsign": callsign,
        "flight": marketing_ident or _display_ident(callsign),
        "operating_callsign": callsign,
        "hex": hex_id,
        "registration": registration or _clean(aircraft.get("registration")),
        "aircraft_type": aircraft_type or "AIRCRAFT",
        "description": description,
        "operator": str(row.get("ownOp") or aircraft.get("registered_owner") or "").upper(),
        "origin": origin,
        "destination": dest,
        "origin_latlon": origin_pos,
        "destination_latlon": dest_pos,
        "route_source": route_source,
        "source": source_name,
        "flightstats": flightstats,
        "gate": flightstats.get("gate") or "",
        "terminal": flightstats.get("terminal") or "",
        "baggage": flightstats.get("baggage") or "",
        "scheduled_departure": flightstats.get("departure_time") or "",
        "scheduled_arrival": flightstats.get("arrival_time") or "",
        "scheduled_status": flightstats.get("status") or "",
        "scheduled_status_text": flightstats.get("status_text") or "",
        "lat": lat,
        "lon": lon,
        "over_city": over_city,
        "over_state": over_state,
        "over_water": over_water,
        "alt_ft": int(_num(row.get("alt_baro") if row.get("alt_baro") != "ground" else 0)),
        "speed_kt": int(_num(row.get("gs"))),
        "vertical_rate_fpm": int(_num(row.get("baro_rate") or row.get("geom_rate"))),
        "track": track,
        "squawk": str(row.get("squawk") or "").strip(),
        "emergency": str(row.get("emergency") or "none").lower(),
        "seen": _num(row.get("seen"), 0),
        "seen_pos": _num(row.get("seen_pos"), 0),
        "on_ground": is_ground_row,
    }


def _display_ident(callsign):
    callsign = _clean(callsign)
    airline = lookup_airline(callsign)
    if airline and airline[1] and callsign[3:]:
        return airline[1] + callsign[3:]
    if len(callsign) > 3 and callsign[:3] in _ICAO_TO_IATA:
        return _ICAO_TO_IATA[callsign[:3]] + callsign[3:]
    return callsign or "FLIGHT"


def _airline_iata(flight):
    airline = lookup_airline(flight.get("callsign") or "")
    if airline:
        return airline[1]
    callsign = _clean(flight.get("callsign") or "")
    if len(callsign) > 3 and callsign[:3] in _ICAO_TO_IATA:
        return _ICAO_TO_IATA[callsign[:3]]
    ident = str(flight.get("flight") or "")
    return ident[:2] if len(ident) >= 2 and ident[:2].isalpha() else None


def _status(flight):
    if flight.get("emergency") and flight["emergency"] != "none":
        return "EMERG", (255, 70, 70)
    scheduled = str(flight.get("scheduled_status") or "").upper()
    scheduled_text = str(flight.get("scheduled_status_text") or "").upper()
    if "CANCEL" in scheduled or "CANCEL" in scheduled_text:
        return "CANCEL", (255, 70, 70)
    if "DELAY" in scheduled or "DELAY" in scheduled_text:
        return "DELAY", (255, 190, 90)
    if "ARRIVED" in scheduled or "LANDED" in scheduled:
        return "ARRIVED", (100, 190, 255)
    speed = _num(flight.get("speed_kt"), 0)
    alt = _num(flight.get("alt_ft"), 0)
    vertical = _num(flight.get("vertical_rate_fpm"), 0)
    if flight.get("on_ground"):
        if speed >= 5:
            return "TAXI", (255, 220, 90)
        return "GROUND", (255, 220, 90)
    dest_pos = flight.get("destination_latlon")
    lat = flight.get("lat")
    lon = flight.get("lon")
    if dest_pos and lat is not None and lon is not None:
        try:
            dist = haversine_miles(float(lat), float(lon), dest_pos[0], dest_pos[1])
            if dist <= 35 and vertical < -200 and alt < 12000:
                return "APPROACH", (255, 190, 90)
        except Exception:
            pass
    if alt > 0:
        if vertical > 500:
            return "CLIMB", (95, 230, 135)
        if vertical < -500:
            return "DESCEND", (255, 190, 90)
        if alt >= 18000:
            return "CRUISE", (100, 190, 255)
        return "LIVE", (95, 230, 135)
    return "TRACK", (100, 190, 255)


def _route_label(flight):
    origin = flight.get("origin") or "---"
    dest = flight.get("destination") or "---"
    if origin != "---" or dest != "---":
        suffix = "" if flight.get("route_source") in ("USER", "FSTAT") else "?"
        return f"{origin}>{dest}{suffix}"
    return "ROUTE BEST EFFORT"


def _location_line(flight, opts):
    city = str(flight.get("over_city") or "").strip()
    if city:
        return city
    water = str(flight.get("over_water") or "").strip()
    if water:
        return water
    nearby, _nearby_state = _nearby_water_place(flight.get("lat"), flight.get("lon"))
    if nearby:
        return nearby
    home = opts.get("_home_latlon")
    lat = flight.get("lat")
    lon = flight.get("lon")
    if home and lat is not None and lon is not None:
        miles = haversine_miles(home[0], home[1], lat, lon)
        direction = compass_dir(home[0], home[1], lat, lon)
        return f"{format_distance_miles(miles, 0)} {direction}"
    if lat is not None and lon is not None:
        return f"{lat:.1f},{lon:.1f}"
    destination = flight.get("destination")
    if destination and destination != "---":
        return _AIRPORT_CITY.get(destination[:3], destination)
    return "POSITION LIVE"


def _schedule_line(flight):
    parts = []
    gate = str(flight.get("gate") or "").strip()
    terminal = str(flight.get("terminal") or "").strip()
    baggage = str(flight.get("baggage") or "").strip()
    arrival = str(flight.get("scheduled_arrival") or "").strip()
    departure = str(flight.get("scheduled_departure") or "").strip()
    if gate:
        parts.append("G" + gate)
    if terminal:
        parts.append("T" + terminal)
    if baggage:
        parts.append("B" + baggage)
    if arrival:
        parts.append("ARR " + arrival)
    elif departure:
        parts.append("DEP " + departure)
    return " ".join(parts)


def _fit(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1]
    return text


def _draw_plane(draw, x, y, color=(120, 195, 255)):
    draw.line((x, y + 7, x + 16, y + 2), fill=color, width=2)
    draw.polygon([(x + 6, y + 5), (x + 1, y), (x + 10, y + 4)], fill=(180, 225, 255))
    draw.polygon([(x + 8, y + 5), (x + 4, y + 13), (x + 13, y + 5)], fill=color)
    draw.line((x + 13, y + 2, x + 17, y + 1), fill=(235, 250, 255))


def _logo_or_plane(image, draw, flight, x, y):
    logo = fetch_airline_logo(_airline_iata(flight))
    if logo:
        image.paste(logo, (x, y), logo)
        return
    _draw_plane(draw, x, y + 2)


def _draw_main_panel(flight, opts, width):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, 32), (0, 5, 18))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, 6), fill=(0, 17, 45))
    status, status_color = _status(flight)
    sw = draw.textbbox((0, 0), status, font=FONT_7)[2] if width > 64 else 0
    ident_max = width - 24 - sw if width > 64 else width - 21
    ident = _fit(draw, flight.get("flight"), FONT_BOLD, ident_max)
    _logo_or_plane(image, draw, flight, 1, 0)
    draw_sharp_text(image, (20, -3), ident, (245, 250, 255), FONT_BOLD)
    if width > 64:
        draw_sharp_text(image, (width - sw - 1, -3), status, status_color, FONT_7)

    route_x = 16 if width <= 64 else 20
    route = _fit(draw, _route_label(flight), FONT_7, width - route_x - 1)
    aircraft = _fit(draw, flight.get("aircraft_type") or "AIRCRAFT", FONT_7, width - 2)
    alt = flight.get("alt_ft", 0)
    altitude = f"FL{alt // 100}" if alt >= 10000 else (f"{alt}FT" if alt > 0 else "GROUND")
    speed = format_speed_knots(flight.get("speed_kt", 0))
    stats = _fit(draw, f"{altitude} {speed}", FONT_7, width - 2)

    row_y = (7, 15, 22) if width <= 64 else (6, 14, 21)
    draw_sharp_text(image, (route_x, row_y[0]), route, (100, 190, 255), FONT_7)
    draw_sharp_text(image, (1, row_y[1]), aircraft, (190, 220, 255), FONT_7)
    draw_sharp_text(image, (1, row_y[2]), stats, (255, 220, 90), FONT_7)
    return image


def _draw_detail_panel(flight, opts, width):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, 32), (0, 5, 18))
    draw = ImageDraw.Draw(image)
    status, status_color = _status(flight)
    tail = _fit(draw, flight.get("registration") or flight.get("hex") or "NO TAIL", FONT_BOLD, width - 2)
    location = _fit(draw, _location_line(flight, opts), FONT_7, width - 2)
    schedule = _fit(draw, _schedule_line(flight) or flight.get("over_state") or "", FONT_7, width - 2)

    draw.rectangle((0, 0, width - 1, 6), fill=(0, 17, 45))
    draw_sharp_text(image, (1, -3), tail, (245, 250, 255), FONT_BOLD)
    row_y = (7, 15, 22) if width <= 64 else (6, 14, 21)
    draw_sharp_text(image, (1, row_y[0]), location, (255, 220, 90), FONT_7)
    draw_sharp_text(image, (1, row_y[1]), schedule, (190, 220, 255), FONT_7)
    draw_sharp_text(image, (1, row_y[2]), status, status_color, FONT_7)
    return image


def _unwrap_route_lons(points):
    if not points:
        return []
    unwrapped = [float(points[0][1])]
    for _lat, lon in points[1:]:
        lon = float(lon)
        prev = unwrapped[-1]
        while lon - prev > 180:
            lon -= 360
        while lon - prev < -180:
            lon += 360
        unwrapped.append(lon)
    return [(float(point[0]), lon) for point, lon in zip(points, unwrapped)]


def _project_route_point(lat, lon, min_lat, max_lat, min_lon, max_lon, bounds):
    left, top, right, bottom = bounds
    lat_span = max(0.01, max_lat - min_lat)
    lon_span = max(0.01, max_lon - min_lon)
    x = left + int(round((float(lon) - min_lon) / lon_span * (right - left)))
    y = bottom - int(round((float(lat) - min_lat) / lat_span * (bottom - top)))
    return max(left, min(right, x)), max(top, min(bottom, y))


def _latlon_to_tile_pixel(lat, lon, zoom):
    lat = max(-85.05112878, min(85.05112878, float(lat)))
    lon = ((float(lon) + 180.0) % 360.0) - 180.0
    scale = _MAP_TILE_SIZE * (2 ** zoom)
    x = (lon + 180.0) / 360.0 * scale
    sin_lat = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * scale
    return x, y


def _fetch_map_tile(zoom, x, y):
    from PIL import Image

    max_tile = 2 ** zoom
    if y < 0 or y >= max_tile:
        return None
    x %= max_tile
    key = (_MAP_TILE_STYLE, zoom, x, y)
    cached = _MAP_TILE_CACHE.get(key)
    if cached is not None:
        return cached
    url = f"https://basemaps.cartocdn.com/light_nolabels/{zoom}/{x}/{y}.png"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1 flight_track"})
        with urllib.request.urlopen(request, timeout=1.8) as response:
            tile = Image.open(BytesIO(response.read())).convert("RGB")
    except Exception:
        return None
    _MAP_TILE_CACHE[key] = tile
    while len(_MAP_TILE_CACHE) > 48:
        _MAP_TILE_CACHE.pop(next(iter(_MAP_TILE_CACHE)), None)
    return tile


def _us_state_lines():
    global _US_STATE_LINES_CACHE
    if _US_STATE_LINES_CACHE is not None:
        return _US_STATE_LINES_CACHE
    try:
        request = urllib.request.Request(_US_STATE_GEOJSON_URL, headers={"User-Agent": "Pixora/0.1 flight_track"})
        with urllib.request.urlopen(request, timeout=1.5) as response:
            data = json.loads(response.read().decode("utf-8"))
        lines = []
        for feature in data.get("features") or []:
            geometry = feature.get("geometry") or {}
            coords = geometry.get("coordinates") or []
            polygons = coords if geometry.get("type") == "MultiPolygon" else [coords]
            for polygon in polygons:
                if not polygon:
                    continue
                ring = polygon[0]
                line = []
                step = max(1, len(ring) // 80)
                for lon, lat, *_rest in ring[::step]:
                    line.append((float(lat), float(lon)))
                if len(line) > 1:
                    lines.append(line)
        _US_STATE_LINES_CACHE = lines
    except Exception:
        _US_STATE_LINES_CACHE = []
    return _US_STATE_LINES_CACHE


def _draw_us_state_lines(draw, bounds, map_ref):
    if not map_ref:
        return
    left, top, right, bottom = bounds
    zoom = map_ref["zoom"]
    crop_left = map_ref["crop_left"]
    crop_top = map_ref["crop_top"]
    for line in _us_state_lines():
        prev = None
        for lat, lon in line:
            x, y = _latlon_to_tile_pixel(lat, lon, zoom)
            point = (bounds[0] + int(round(x - crop_left)), bounds[1] + int(round(y - crop_top)))
            in_range = left - 2 <= point[0] <= right + 2 and top - 2 <= point[1] <= bottom + 2
            if prev and (prev[1] or in_range):
                draw.line((prev[0][0], prev[0][1], point[0], point[1]), fill=(78, 92, 88))
            prev = (point, in_range)


def _route_pixels_at_zoom(route_points, zoom):
    return [_latlon_to_tile_pixel(lat, lon, zoom) for lat, lon in route_points]


def _route_pixel_span(pixels):
    xs = [point[0] for point in pixels]
    ys = [point[1] for point in pixels]
    return max(xs) - min(xs), max(ys) - min(ys)


def _style_route_map(background):
    background = background.convert("RGB")
    pixels = background.load()
    width, height = background.size
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            if b > 185 and g > 175 and b >= r + 8:
                pixels[x, y] = (7, 58, 96)
            elif r > 218 and g > 218 and b > 205:
                pixels[x, y] = (22, 37, 42)
            elif b > r + 18 and b > g + 8:
                pixels[x, y] = (7, 58, 96)
            elif g > r + 12 and g > b:
                pixels[x, y] = (28, 55, 41)
            elif r > 175 and g > 160 and b < 150:
                pixels[x, y] = (55, 50, 39)
            elif abs(r - g) < 18 and abs(g - b) < 22 and r > 120:
                pixels[x, y] = (24, 38, 43)
            else:
                pixels[x, y] = (max(0, r // 4), max(6, g // 4), max(12, b // 4))
    background = ImageEnhance.Color(background).enhance(1.45)
    background = ImageEnhance.Contrast(background).enhance(1.75)
    background = ImageEnhance.Sharpness(background).enhance(2.2)
    return background.filter(ImageFilter.SHARPEN)


def _choose_route_map_zoom(route_points, bounds, fill_x=0.95, fill_y=0.9, min_zoom=2):
    width = max(1, bounds[2] - bounds[0] + 1)
    height = max(1, bounds[3] - bounds[1] + 1)
    for zoom in range(9, 1, -1):
        pixels = [_latlon_to_tile_pixel(lat, lon, zoom) for lat, lon in route_points]
        span_x, span_y = _route_pixel_span(pixels)
        if zoom >= min_zoom and span_x <= width * fill_x and span_y <= height * fill_y:
            return zoom, pixels
    zoom = max(2, min_zoom)
    return zoom, _route_pixels_at_zoom(route_points, zoom)


def _route_map_background(route_points, bounds, focus_index=1, min_zoom=2):
    from PIL import Image

    zoom, pixels = _choose_route_map_zoom(route_points, bounds, min_zoom=min_zoom)
    xs = [point[0] for point in pixels]
    ys = [point[1] for point in pixels]
    source_w = bounds[2] - bounds[0] + 1
    source_h = bounds[3] - bounds[1] + 1
    if 0 <= focus_index < len(pixels):
        focus_x, focus_y = pixels[focus_index]
    else:
        focus_x = (min(xs) + max(xs)) / 2.0
        focus_y = (min(ys) + max(ys)) / 2.0
    center_x = focus_x
    center_y = focus_y
    crop_left = int(round(center_x - source_w / 2))
    crop_top = int(round(center_y - source_h / 2))
    tile_left = math.floor(crop_left / _MAP_TILE_SIZE)
    tile_top = math.floor(crop_top / _MAP_TILE_SIZE)
    tile_right = math.floor((crop_left + source_w - 1) / _MAP_TILE_SIZE)
    tile_bottom = math.floor((crop_top + source_h - 1) / _MAP_TILE_SIZE)

    canvas = Image.new(
        "RGB",
        ((tile_right - tile_left + 1) * _MAP_TILE_SIZE, (tile_bottom - tile_top + 1) * _MAP_TILE_SIZE),
        (1, 11, 24),
    )
    any_tile = False
    for tx in range(tile_left, tile_right + 1):
        for ty in range(tile_top, tile_bottom + 1):
            tile = _fetch_map_tile(zoom, tx, ty)
            if tile is None:
                continue
            any_tile = True
            canvas.paste(tile, ((tx - tile_left) * _MAP_TILE_SIZE, (ty - tile_top) * _MAP_TILE_SIZE))
    if not any_tile:
        return None, None, None
    local_left = crop_left - tile_left * _MAP_TILE_SIZE
    local_top = crop_top - tile_top * _MAP_TILE_SIZE
    background = _style_route_map(canvas.crop((local_left, local_top, local_left + source_w, local_top + source_h)))
    projected = [
        (bounds[0] + int(round(x - crop_left)), bounds[1] + int(round(y - crop_top)))
        for x, y in pixels
    ]
    return background, projected, {"zoom": zoom, "crop_left": crop_left, "crop_top": crop_top}


def _route_map_bounds(route_points, max_right=84):
    top = 0
    bottom = 31
    available_w = max(32, max_right + 1)
    height = bottom - top + 1
    zoom, pixels = _choose_route_map_zoom(route_points, (0, 0, available_w - 1, height - 1), fill_x=0.99, fill_y=0.96)
    route_w, route_h = _route_pixel_span(pixels)
    route_w = max(1.0, route_w)
    route_h = max(1.0, route_h)
    width = int(round(height * (route_w / route_h) * 1.12))
    width = max(48, min(available_w, width))
    left = max(0, (available_w - width) // 2)
    return (left, top, left + width - 1, bottom)


def _route_map_min_zoom(flight):
    try:
        origin_pos = flight.get("origin_latlon")
        dest_pos = flight.get("destination_latlon")
        lat = flight.get("lat")
        lon = flight.get("lon")
        if lat is None or lon is None:
            return 2
        distances = []
        if origin_pos:
            distances.append(haversine_miles(float(lat), float(lon), origin_pos[0], origin_pos[1]))
        if dest_pos:
            distances.append(haversine_miles(float(lat), float(lon), dest_pos[0], dest_pos[1]))
        if not distances:
            return 2
        miles = min(distances)
        if miles <= 25:
            return 6
        if miles <= 60:
            return 5
        if miles <= 150:
            return 4
    except Exception:
        return 2
    return 2


def _draw_star(draw, x, y, color):
    draw.point((x, y), fill=color)
    draw.line((x - 2, y, x + 2, y), fill=color)
    draw.line((x, y - 2, x, y + 2), fill=color)
    draw.point((x - 1, y - 1), fill=color)
    draw.point((x + 1, y - 1), fill=color)
    draw.point((x - 1, y + 1), fill=color)
    draw.point((x + 1, y + 1), fill=color)


def _draw_aircraft_marker(draw, x, y, track, color=(255, 90, 210)):
    if track is None:
        draw.rectangle((x - 1, y - 1, x + 1, y + 1), fill=color)
        return
    angle = math.radians(float(track) - 90)
    nose = (x + int(round(math.cos(angle) * 3)), y + int(round(math.sin(angle) * 3)))
    tail = (x - int(round(math.cos(angle) * 2)), y - int(round(math.sin(angle) * 2)))
    draw.line((tail[0], tail[1], nose[0], nose[1]), fill=color)
    draw.rectangle((x - 1, y - 1, x + 1, y + 1), fill=color)


def _draw_route_map_body(image, draw, flight, bounds):
    depart_color = (95, 230, 135)
    arrive_color = (255, 190, 90)
    route_shadow = (12, 18, 36)
    route_color = (145, 210, 255)
    plane_color = (255, 80, 210)
    origin_pos = flight.get("origin_latlon")
    dest_pos = flight.get("destination_latlon")
    lat = flight.get("lat")
    lon = flight.get("lon")
    if not origin_pos or not dest_pos or lat is None or lon is None:
        return False

    raw_points = [origin_pos, (float(lat), float(lon)), dest_pos]
    route_points = _unwrap_route_lons(raw_points)
    min_zoom = _route_map_min_zoom(flight)
    background, projected, map_ref = _route_map_background(route_points, bounds, min_zoom=min_zoom)
    if background is not None and projected:
        image.paste(background, (bounds[0], bounds[1]))
        _draw_us_state_lines(draw, bounds, map_ref)
        origin_xy, plane_xy, dest_xy = projected
    else:
        draw.rectangle(bounds, fill=(1, 11, 24))
        lats = [point[0] for point in route_points]
        lons = [point[1] for point in route_points]
        lat_pad = max(1.0, (max(lats) - min(lats)) * 0.18)
        lon_pad = max(1.0, (max(lons) - min(lons)) * 0.12)
        min_lat, max_lat = min(lats) - lat_pad, max(lats) + lat_pad
        min_lon, max_lon = min(lons) - lon_pad, max(lons) + lon_pad
        origin_xy = _project_route_point(route_points[0][0], route_points[0][1], min_lat, max_lat, min_lon, max_lon, bounds)
        plane_xy = _project_route_point(route_points[1][0], route_points[1][1], min_lat, max_lat, min_lon, max_lon, bounds)
        dest_xy = _project_route_point(route_points[2][0], route_points[2][1], min_lat, max_lat, min_lon, max_lon, bounds)
    draw.rectangle(bounds, outline=(34, 92, 125))
    draw.line((origin_xy[0], origin_xy[1], dest_xy[0], dest_xy[1]), fill=route_shadow, width=3)
    draw.line((origin_xy[0], origin_xy[1], dest_xy[0], dest_xy[1]), fill=route_color)
    _draw_star(draw, origin_xy[0], origin_xy[1], depart_color)
    _draw_star(draw, dest_xy[0], dest_xy[1], arrive_color)
    _draw_aircraft_marker(draw, plane_xy[0], plane_xy[1], flight.get("track"), plane_color)
    return True


def _draw_route_map_panel(flight, opts):
    from PIL import Image, ImageDraw

    depart_color = (95, 230, 135)
    arrive_color = (255, 190, 90)
    origin_pos = flight.get("origin_latlon")
    dest_pos = flight.get("destination_latlon")
    lat = flight.get("lat")
    lon = flight.get("lon")
    if not origin_pos or not dest_pos or lat is None or lon is None:
        return None

    image = Image.new("RGB", (128, 32), (0, 5, 18))
    draw = ImageDraw.Draw(image)
    info_x = 78
    draw.rectangle((info_x - 1, 0, 127, 31), fill=(0, 5, 18))
    draw.line((info_x - 2, 0, info_x - 2, 31), fill=(70, 130, 190))
    origin = flight.get("origin") or "---"
    dest = flight.get("destination") or "---"
    info_w = 127 - info_x
    origin_text = _fit(draw, origin, FONT_7, 18)
    dest_text = _fit(draw, dest, FONT_7, 18)
    origin_w = draw.textbbox((0, 0), origin_text, font=FONT_7)[2]
    arrow_x = info_x + origin_w + 2
    status, status_color = _status(flight)
    city = _fit(draw, _location_line(flight, opts), FONT_7, info_w)
    state = _fit(draw, flight.get("over_state") or "", FONT_7, info_w)
    draw_sharp_text(image, (info_x, -3), origin_text, depart_color, FONT_7)
    draw_sharp_text(image, (arrow_x, -3), ">", (100, 190, 255), FONT_7)
    draw_sharp_text(image, (arrow_x + 6, -3), dest_text, arrive_color, FONT_7)
    draw_sharp_text(image, (info_x, 6), city, (255, 220, 90), FONT_7)
    draw_sharp_text(image, (info_x, 14), state, (190, 220, 255), FONT_7)
    draw_sharp_text(image, (info_x, 22), _fit(draw, status, FONT_7, info_w), status_color, FONT_7)

    raw_points = [origin_pos, (float(lat), float(lon)), dest_pos]
    route_points = _unwrap_route_lons(raw_points)
    bounds = _route_map_bounds(route_points, max_right=74)
    if not _draw_route_map_body(image, draw, flight, bounds):
        return None

    return image


def _draw_route_map_64(flight):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (64, 32), (0, 5, 18))
    draw = ImageDraw.Draw(image)
    if not _draw_route_map_body(image, draw, flight, (0, 0, 63, 31)):
        return None
    return image


def _draw_wide_panel(flight, opts):
    from PIL import Image, ImageDraw

    width = 128
    image = Image.new("RGB", (width, 32), (0, 5, 18))
    draw = ImageDraw.Draw(image)
    status, status_color = _status(flight)
    draw.rectangle((0, 0, width - 1, 6), fill=(0, 17, 45))
    draw.line((63, 9, 63, 31), fill=(70, 130, 190))

    _logo_or_plane(image, draw, flight, 1, 0)
    ident = _fit(draw, flight.get("flight"), FONT_BOLD, 42)
    draw_sharp_text(image, (20, -3), ident, (245, 250, 255), FONT_BOLD)

    route = _fit(draw, _route_label(flight), FONT_7, 42)
    aircraft = _fit(draw, flight.get("aircraft_type") or "AIRCRAFT", FONT_7, 61)
    alt = flight.get("alt_ft", 0)
    altitude = f"FL{alt // 100}" if alt >= 10000 else (f"{alt}FT" if alt > 0 else "GROUND")
    speed = format_speed_knots(flight.get("speed_kt", 0))
    stats = _fit(draw, f"{altitude} {speed}", FONT_7, 61)

    tail = _fit(draw, flight.get("registration") or flight.get("hex") or "NO TAIL", FONT_7, 62)
    location = _fit(draw, _location_line(flight, opts), FONT_7, 62)
    schedule = _fit(draw, _schedule_line(flight) or flight.get("over_state") or "", FONT_7, 62)
    tail_w = draw.textbbox((0, 0), tail, font=FONT_7)[2]

    draw_sharp_text(image, (20, 6), route, (100, 190, 255), FONT_7)
    draw_sharp_text(image, (1, 14), aircraft, (190, 220, 255), FONT_7)
    draw_sharp_text(image, (1, 21), stats, (255, 220, 90), FONT_7)
    draw_sharp_text(image, (max(66, 127 - tail_w), -3), tail, (245, 250, 255), FONT_7)
    draw_sharp_text(image, (66, 6), location, (255, 220, 90), FONT_7)
    draw_sharp_text(image, (66, 14), schedule, (190, 220, 255), FONT_7)
    draw_sharp_text(image, (66, 21), status, status_color, FONT_7)
    return image


def _save_cycle(frames, dwell=4200):
    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=dwell,
        loop=0,
        lossless=True,
        quality=100,
    )
    return {"body": out.getvalue(), "_stay": False}


def _render_error_image(message, width):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    title = "FLIGHT TRACKER" if width > 64 else "FLIGHT TRK"
    tw = draw.textbbox((0, 0), title, font=FONT_7)[2]
    draw_sharp_text(image, ((width - tw) // 2, -3), title, (100, 190, 255), FONT_7)
    raw_message = str(message or "NO DATA").upper()
    no_live_match = re.match(r"^NO LIVE DATA\s+(.+)$", raw_message)
    if no_live_match:
        lines = ["NO LIVE", "DATA", no_live_match.group(1)]
        message_y = 8
        line_h = 7
    else:
        words = raw_message.split()
        lines = []
        current = ""
        for word in words:
            candidate = (current + " " + word).strip()
            if current and draw.textbbox((0, 0), candidate, font=FONT_7)[2] > width - 2:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        message_y = 6 if width <= 64 else 9
        line_h = 7 if width <= 64 else 8
    for index, line in enumerate(lines[:3]):
        lw = draw.textbbox((0, 0), line, font=FONT_7)[2]
        draw_sharp_text(image, ((width - lw) // 2, message_y + index * line_h), line, (255, 220, 90), FONT_7)
    return image


def _render_error(message, width):
    image = _render_error_image(message, width)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _airport_display_name(code):
    code = _clean(code)[:4]
    if not code or code == "---":
        return "DESTINATION"
    if code in _AIRPORT_CITY:
        return _AIRPORT_CITY[code]
    if len(code) == 4 and code[1:] in _AIRPORT_CITY:
        return _AIRPORT_CITY[code[1:]]
    return code


def _destination_name(flight):
    flight = flight or {}
    destination = _clean(flight.get("destination") or "")[:4]
    origin = _clean(flight.get("origin") or "")[:4]
    try:
        lat = flight.get("lat")
        lon = flight.get("lon")
        origin_pos = flight.get("origin_latlon")
        dest_pos = flight.get("destination_latlon")
        if lat is not None and lon is not None and origin_pos and dest_pos:
            origin_dist = haversine_miles(float(lat), float(lon), origin_pos[0], origin_pos[1])
            dest_dist = haversine_miles(float(lat), float(lon), dest_pos[0], dest_pos[1])
            if origin and origin_dist + 8 < dest_dist:
                return _airport_display_name(origin)
            if destination:
                return _airport_display_name(destination)
    except Exception:
        pass
    if not destination or destination == "---":
        return "DESTINATION"
    return _airport_display_name(destination)


def _draw_welcome_panel(destination, width):
    return _draw_landing_frame(width, 1.0)


def _landing_plane_asset():
    global _LANDING_PHOTO_CACHE
    from PIL import Image

    if _LANDING_PHOTO_CACHE is None:
        asset = Path(__file__).resolve().parents[1] / "assets" / "flight_landing_airplane.png"
        try:
            _LANDING_PHOTO_CACHE = Image.open(asset).convert("RGBA")
        except Exception:
            _LANDING_PHOTO_CACHE = False
    return _LANDING_PHOTO_CACHE or None


def _draw_landing_frame(width, progress, plane_width=None):
    from PIL import Image, ImageDraw

    width = max(64, int(width or 64))
    image = Image.new("RGB", (width, 32), (96, 166, 222))
    draw = ImageDraw.Draw(image)
    horizon = 21
    draw.rectangle((0, horizon, width - 1, 31), fill=(32, 45, 50))
    draw.rectangle((0, 27, width - 1, 31), fill=(20, 22, 24))
    draw.line((0, 27, width - 1, 27), fill=(210, 210, 190))
    for x in range(-width, width * 2, 18):
        draw.line((x, 30, x + 8, 30), fill=(240, 215, 120))
    draw.rectangle((0, horizon - 2, width - 1, horizon), fill=(70, 98, 86))
    for x in range(4, width, 22):
        draw.rectangle((x, horizon - 5, x + 4, horizon - 2), fill=(92, 112, 118))

    plane = _landing_plane_asset()
    if plane is None:
        return image
    plane_w = int(plane_width) if plane_width else max(24, min(width - 10 if width <= 64 else int(width * 0.42), int(width * 0.82)))
    plane_w = max(24, min(plane_w, width - 5))
    plane_h = max(11, int(round(plane.height * plane_w / plane.width)))
    if plane_h > 26:
        plane_h = 26
        plane_w = max(32, int(round(plane.width * plane_h / plane.height)))
    sprite = plane.resize((plane_w, plane_h), Image.Resampling.LANCZOS)

    p = max(0.0, min(1.0, float(progress or 0.0)))
    final_x = width - plane_w - 3
    touchdown_x = max(-plane_w // 3, final_x - max(8, int(width * 0.18)))
    landing_y = 25 - plane_h
    if p < 0.82:
        t = p / 0.82
        start_x = -int(round(plane_w * 0.55))
        x = int(round(start_x + (touchdown_x - start_x) * t))
        air_t = min(1.0, t / 0.88)
        start_y = 1
        y = int(round(start_y + (landing_y - start_y) * air_t))
    else:
        t = (p - 0.82) / 0.18
        x = int(round(touchdown_x + (final_x - touchdown_x) * t))
        y = landing_y
    if 0.78 <= p <= 0.93:
        smoke_t = (p - 0.78) / 0.15
        smoke_anchor_x = x + max(2, int(plane_w * 0.40))
        smoke_y = 24
        smoke_color = (235, 238, 232) if smoke_t < 0.55 else (198, 204, 200)
        puffs = [
            (0, 0, 4),
            (-5, 1, 3),
            (-10, 1, 2),
        ]
        if smoke_t > 0.35:
            puffs.append((-15, 2, 2))
        if smoke_t > 0.6:
            puffs.append((-20, 2, 1))
        for dx, dy, radius in puffs:
            cx = smoke_anchor_x + dx - int(smoke_t * 8)
            cy = smoke_y + dy
            if -radius <= cx < width + radius:
                draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=smoke_color)
    image.paste(sprite, (x, y), sprite)
    return image


def _landing_animation_frames(width):
    steps = (0.0, 0.12, 0.24, 0.36, 0.50, 0.64, 0.76, 0.82, 0.88, 0.94, 1.0, 1.0, 1.0)
    return [_draw_landing_frame(width, step) for step in steps]


def _landing_wall_animation_frames(width):
    plane_w = max(24, min(118, int(128 * 0.42)))
    steps = (0.0, 0.12, 0.24, 0.36, 0.50, 0.64, 0.76, 0.82, 0.88, 0.94, 1.0, 1.0, 1.0)
    return [_draw_landing_frame(width, step, plane_width=plane_w) for step in steps]


def _landing_animation_durations(frame_count):
    return [150] * max(0, frame_count - 3) + [450, 450, 450]


def _landing_animation_body(width):
    frames = _landing_animation_frames(width)
    durations = _landing_animation_durations(len(frames))
    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=1,
        lossless=True,
        quality=100,
    )
    return out.getvalue()


def _render_landing_wall_frames(team, kind=None):
    width = max(128, int((team or {}).get("_width") or 128))
    frames = _landing_wall_animation_frames(width)
    return frames, _landing_animation_durations(len(frames))


def _display_error(error, opts):
    if error == "SET FLT":
        return "Set airline and flight number"
    if error == "NO LIVE":
        ident = _flight_ident(opts, use_icao=False, slot=int(opts.get("_slot") or 1)) or "flight"
        return f"No live data {ident}"
    if error == "API ERR":
        return "Open ADS-B source unavailable"
    return error or "No flight data"


def _configured_slots(opts):
    slots = []
    for slot in range(1, 5):
        airline = _clean(_slot_value(opts, "airline", slot) or "")
        number = "".join(ch for ch in str(_slot_value(opts, "flightNumber", slot) or "") if ch.isdigit())
        if airline and number:
            slot_opts = dict(opts)
            slot_opts["_slot"] = slot
            slots.append(slot_opts)
    return slots


def _landing_event_key(flight, slot):
    flight = flight or {}
    parts = [
        time.strftime("%Y%m%d", time.localtime()),
        str(slot or 1),
        _clean(flight.get("flight") or ""),
        _clean(flight.get("operating_callsign") or flight.get("callsign") or ""),
        _clean(flight.get("hex") or flight.get("registration") or ""),
        _clean(flight.get("origin") or ""),
        _clean(flight.get("destination") or ""),
    ]
    return "|".join(parts)


def _landing_welcome_for_flights(flights, now):
    cutoff = now - 36 * 60 * 60
    for key, seen in list(_LANDED_FLIGHT_EVENTS.items()):
        if seen < cutoff:
            _LANDED_FLIGHT_EVENTS.pop(key, None)
    welcome = []
    for entry in flights or []:
        flight = entry.get("flight") if isinstance(entry, dict) else None
        if not flight:
            continue
        slot = entry.get("slot") or 1
        event_key = _landing_event_key(flight, slot)
        airborne_reset = (
            not flight.get("on_ground")
            and (_num(flight.get("alt_ft"), 0) > 500 or _num(flight.get("speed_kt"), 0) > 80)
        )
        if airborne_reset:
            _LANDED_FLIGHT_EVENTS.pop(event_key, None)
            continue
        if not flight.get("on_ground"):
            continue
        if event_key in _LANDED_FLIGHT_EVENTS:
            continue
        _LANDED_FLIGHT_EVENTS[event_key] = now
        welcome.append({"destination": _destination_name(flight), "slot": slot})
    return welcome


def _snapshot_key(opts):
    keys = ["source", "homeZip"]
    for slot in range(1, 5):
        keys.extend([f"airline{slot}", f"flightNumber{slot}", f"origin{slot}", f"destination{slot}"])
    payload = {key: str(opts.get(key) or "") for key in keys}
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _refresh_snapshot(key, opts):
    try:
        deadline = time.monotonic() + _REFRESH_BUDGET_SECONDS
        slots = _configured_slots(opts)
        flights = []
        errors = []
        home = _home_latlon(opts.get("homeZip"))
        for slot_opts in slots:
            if _time_left(deadline) < 0.4:
                break
            flight, error = _load_live(slot_opts, deadline=deadline)
            if flight:
                flights.append({"flight": flight, "slot": int(slot_opts.get("_slot") or 1)})
            elif error:
                errors.append(_display_error(error, slot_opts))

        now = time.time()
        with _SNAPSHOT_LOCK:
            if flights:
                welcome = _landing_welcome_for_flights(flights, now)
                _SNAPSHOT_CACHE[key] = {
                    "flights": flights,
                    "welcome": welcome,
                    "welcome_remaining": 1 if welcome else 0,
                    "errors": errors,
                    "home": home,
                    "updated": now,
                    "expires": now + _SNAPSHOT_TTL_SECONDS,
                }
            else:
                _SNAPSHOT_CACHE[key] = {
                    "flights": [],
                    "welcome": [],
                    "welcome_remaining": 0,
                    "errors": errors,
                    "home": home,
                    "updated": now,
                    "expires": now + 60,
                }
    finally:
        with _SNAPSHOT_LOCK:
            _SNAPSHOT_PENDING.discard(key)


def _queue_snapshot_refresh(key, opts):
    now = time.time()
    with _SNAPSHOT_LOCK:
        _SNAPSHOT_WATCHED[key] = dict(opts)
        snapshot = _SNAPSHOT_CACHE.get(key)
        stale = not snapshot or snapshot.get("expires", 0) <= now
        if not stale or key in _SNAPSHOT_PENDING:
            _ensure_snapshot_scheduler()
            return snapshot
        _SNAPSHOT_PENDING.add(key)
    _ensure_snapshot_scheduler()
    _snapshot_pool().submit(_refresh_snapshot, key, dict(opts))
    return snapshot


def _render_snapshot(snapshot, opts, width):
    frames = []
    render_opts = dict(opts)
    render_opts["_home_latlon"] = snapshot.get("home")
    welcome = snapshot.get("welcome") or []
    if welcome:
        remaining = int(snapshot.get("welcome_remaining") or 0)
        if remaining > 0:
            snapshot["welcome_remaining"] = remaining - 1
            target = str((opts or {}).get("landingGraphicTarget") or "device").strip().lower()
            wall = target in ("group", "group_wall", "wall") or target.startswith("group:")
            if wall:
                destination = (welcome[0] or {}).get("destination") or "DESTINATION"
                return {
                    "body": None,
                    "dwell_secs": 6,
                    "_stay": False,
                    "_group_wall": {
                        "type": "landing",
                        "renderer": "_render_landing_wall_frames",
                        "team": {"destination": destination},
                        "kind": "landing",
                        "dwell_secs": 3,
                    },
                }
            return {"body": _landing_animation_body(width), "dwell_secs": 6, "_stay": False, "_priority_graphic": True}
        if _skip_no_data(opts):
            return None
    for entry in snapshot.get("flights") or []:
        slot_opts = dict(render_opts)
        slot_opts["_slot"] = entry.get("slot") or 1
        flight = entry.get("flight")
        if flight:
            if width > 64:
                frames.append(_draw_wide_panel(flight, slot_opts))
                route_map = _draw_route_map_panel(flight, slot_opts)
                if route_map is not None:
                    frames.append(route_map)
            else:
                frames.append(_draw_main_panel(flight, slot_opts, width))
                frames.append(_draw_detail_panel(flight, slot_opts, width))
                route_map = _draw_route_map_64(flight)
                if route_map is not None:
                    frames.append(route_map)
    if frames:
        return _save_cycle(frames)
    errors = snapshot.get("errors") or []
    if _skip_no_data(opts) and (not errors or all(_is_no_data_error(error) for error in errors)):
        return None
    return _save_cycle([_render_error_image(errors[0], width)]) if errors else _render_error("Updating flight data", width)


def render(options=None):
    opts = options or {}
    width = 128 if _is_wide(opts) else 64
    slots = _configured_slots(opts)
    if not slots:
        return _render_error("Set airline and flight number", width)
    snapshot = _queue_snapshot_refresh(_snapshot_key(opts), opts)
    if snapshot:
        return _render_snapshot(snapshot, opts, width)
    if _skip_no_data(opts):
        return None
    return _render_error("Updating flight data", width)
