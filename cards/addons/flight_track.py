import atexit
from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import BytesIO
import json
import re
import time
import threading
import urllib.error
import urllib.parse
import urllib.request

from card_utils import (
    compass_dir,
    draw_sharp_text,
    format_distance_miles,
    format_speed_knots,
    haversine_miles,
    iata_to_icao_prefix,
    lookup_airline,
)

try:
    from PIL import ImageFont
    FONT_7 = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    FONT_BOLD = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
except Exception:
    from PIL import ImageFont
    FONT_7 = FONT_BOLD = ImageFont.load_default()

CARD_ID = "flight_track"
CARD_NAME = "Flight Tracker"
CARD_DETAIL = "Free live ADS-B flight tracking"
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
])
del _idx

_AIRPORT_CITY = {
    "ATL": "ATLANTA", "BOS": "BOSTON", "BWI": "BALTIMORE", "DCA": "WASHINGTON",
    "DEN": "DENVER", "DFW": "DALLAS", "EWR": "NEWARK", "IAD": "WASHINGTON",
    "JFK": "NEW YORK", "LAS": "LAS VEGAS", "LAX": "LOS ANGELES", "LGA": "NEW YORK",
    "MCO": "ORLANDO", "MHT": "MANCHESTER", "ORD": "CHICAGO", "PHX": "PHOENIX",
    "SEA": "SEATTLE", "SFO": "SAN FRANCISCO", "TPA": "TAMPA",
}
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
_JSON_CACHE = {}
_SNAPSHOT_CACHE = {}
_SNAPSHOT_PENDING = set()
_SNAPSHOT_LOCK = threading.Lock()
_SNAPSHOT_POOL = None
_SNAPSHOT_WATCHED = {}
_SCHEDULER_THREAD = None
_SCHEDULER_STOP = threading.Event()


def _is_wide(options):
    return (options or {}).get("_target") == "matrixportal-s3-128x32"


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
            for key, opts in list(_SNAPSHOT_WATCHED.items()):
                snapshot = _SNAPSHOT_CACHE.get(key)
                if key not in _SNAPSHOT_PENDING and (not snapshot or snapshot.get("expires", 0) <= now):
                    _SNAPSHOT_PENDING.add(key)
                    due.append((key, dict(opts)))
        for key, opts in due:
            _snapshot_pool().submit(_refresh_snapshot, key, opts)


def _fetch_json(url, seconds=600, timeout=2.0, deadline=None):
    now = time.time()
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
    return data


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
        value = value.get("iata_code") or value.get("icao_code") or value.get("iata") or value.get("icao")
    return _clean(value)[:4] or "---"


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
        return "", ""
    try:
        url = (
            "https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=10&addressdetails=1"
            f"&lat={float(lat):.5f}&lon={float(lon):.5f}"
        )
        data = _fetch_json(url, seconds=86400, timeout=1.2, deadline=deadline)
        address = data.get("address") or {}
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
        return str(city).upper(), state
    except Exception:
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
    last_error = None
    for provider in providers:
        if _time_left(deadline) < 0.4:
            break
        for callsign in callsigns:
            if _time_left(deadline) < 0.4:
                break
            try:
                rows, source_name = provider(callsign, deadline=deadline)
                had_successful_lookup = True
                row = _pick_aircraft(rows, callsign)
                if row:
                    return _build_flight(row, callsign, source_name, opts, deadline=deadline), None
            except Exception:
                last_error = "API ERR"
    return None, "NO LIVE" if had_successful_lookup else (last_error or "NO LIVE")


def _route_from_enrichment(callsign, opts, deadline=None):
    user_origin, user_dest, source = _route_input(opts, int(opts.get("_slot") or 1))
    route = _fetch_adsbdb_route(callsign, deadline=deadline)
    origin = user_origin
    dest = user_dest
    if not origin:
        origin = _airport_code(route.get("origin"))
    if not dest:
        dest = _airport_code(route.get("destination"))
    if (origin and origin != "---") or (dest and dest != "---"):
        return origin or "---", dest or "---", source or "ADSDB"
    return "---", "---", ""


def _route_input(opts, slot=1):
    origin = _clean(_slot_value(opts, "origin", slot) or "")[:4]
    dest = _clean(_slot_value(opts, "destination", slot) or "")[:4]
    source = "USER" if origin or dest else ""
    return origin, dest, source


def _build_flight(row, query_callsign, source_name, opts, deadline=None):
    callsign = _clean(row.get("flight") or row.get("callsign") or query_callsign)
    marketing_ident = _flight_ident(opts, use_icao=False, slot=int(opts.get("_slot") or 1))
    registration = _clean(row.get("r") or row.get("reg") or row.get("registration"))
    hex_id = _clean(row.get("hex") or row.get("icao24"))
    aircraft = _fetch_adsbdb_aircraft(hex_id, registration, deadline=deadline)
    origin, dest, route_source = _route_from_enrichment(callsign, opts, deadline=deadline)
    aircraft_type = _clean(row.get("t") or row.get("typeCode") or aircraft.get("icao_type") or aircraft.get("type"))[:10]
    description = str(row.get("desc") or aircraft.get("type") or aircraft.get("manufacturer") or "").upper()
    lat = _num(row.get("lat"), None)
    lon = _num(row.get("lon"), None)
    over_city, over_state = _city_state_from_latlon(lat, lon, deadline=deadline)
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
        "route_source": route_source,
        "source": source_name,
        "lat": lat,
        "lon": lon,
        "over_city": over_city,
        "over_state": over_state,
        "alt_ft": int(_num(row.get("alt_baro") if row.get("alt_baro") != "ground" else 0)),
        "speed_kt": int(_num(row.get("gs"))),
        "track": _num(row.get("track") or row.get("true_heading") or row.get("mag_heading")),
        "squawk": str(row.get("squawk") or "").strip(),
        "emergency": str(row.get("emergency") or "none").lower(),
        "seen": _num(row.get("seen"), 0),
        "seen_pos": _num(row.get("seen_pos"), 0),
        "on_ground": row.get("alt_baro") == "ground" or (_num(row.get("gs")) < 35 and _num(row.get("alt_baro")) < 200),
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
    if flight.get("on_ground"):
        return "GROUND", (255, 220, 90)
    if flight.get("alt_ft", 0) > 0:
        return "LIVE", (95, 230, 135)
    return "TRACK", (100, 190, 255)


def _route_label(flight):
    origin = flight.get("origin") or "---"
    dest = flight.get("destination") or "---"
    if origin != "---" or dest != "---":
        suffix = "" if flight.get("route_source") == "USER" else "?"
        return f"{origin}>{dest}{suffix}"
    return "ROUTE BEST EFFORT"


def _location_line(flight, opts):
    city = str(flight.get("over_city") or "").strip()
    if city:
        return city
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
    _draw_plane(draw, x, y + 2)


def _draw_main_panel(flight, opts, width):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, 32), (0, 5, 18))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, 8), fill=(0, 17, 45))
    status, status_color = _status(flight)
    sw = draw.textbbox((0, 0), status, font=FONT_7)[2] if width > 64 else 0
    ident_max = width - 24 - sw if width > 64 else width - 21
    ident = _fit(draw, flight.get("flight"), FONT_BOLD, ident_max)
    _logo_or_plane(image, draw, flight, 1, 0)
    draw_sharp_text(image, (20, -3), ident, (245, 250, 255), FONT_BOLD)
    if width > 64:
        draw_sharp_text(image, (width - sw - 1, -3), status, status_color, FONT_7)

    route_x = 16 if width <= 64 else 1
    route = _fit(draw, _route_label(flight), FONT_7, width - route_x - 1)
    aircraft = _fit(draw, flight.get("aircraft_type") or "AIRCRAFT", FONT_7, width - 2)
    alt = flight.get("alt_ft", 0)
    altitude = f"FL{alt // 100}" if alt >= 10000 else (f"{alt}FT" if alt > 0 else "GROUND")
    speed = format_speed_knots(flight.get("speed_kt", 0))
    stats = _fit(draw, f"{altitude} {speed}", FONT_7, width - 2)

    row_y = (7, 15, 22) if width <= 64 else (8, 16, 24)
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
    state = _fit(draw, flight.get("over_state") or "", FONT_7, width - 2)

    draw.rectangle((0, 0, width - 1, 8), fill=(0, 17, 45))
    draw_sharp_text(image, (1, -3), tail, (245, 250, 255), FONT_BOLD)
    row_y = (7, 15, 22) if width <= 64 else (8, 16, 24)
    draw_sharp_text(image, (1, row_y[0]), location, (255, 220, 90), FONT_7)
    draw_sharp_text(image, (1, row_y[1]), state, (190, 220, 255), FONT_7)
    draw_sharp_text(image, (1, row_y[2]), status, status_color, FONT_7)
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
    return {"body": out.getvalue(), "dwell_secs": max(1, len(frames) * dwell // 1000), "_stay": False}


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
            current = _SNAPSHOT_CACHE.get(key)
            if flights:
                _SNAPSHOT_CACHE[key] = {
                    "flights": flights,
                    "errors": errors,
                    "home": home,
                    "updated": now,
                    "expires": now + _SNAPSHOT_TTL_SECONDS,
                }
            elif current and current.get("flights"):
                current["errors"] = errors
                current["expires"] = now + _SNAPSHOT_TTL_SECONDS
            else:
                _SNAPSHOT_CACHE[key] = {
                    "flights": [],
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
    for entry in snapshot.get("flights") or []:
        slot_opts = dict(render_opts)
        slot_opts["_slot"] = entry.get("slot") or 1
        flight = entry.get("flight")
        if flight:
            frames.append(_draw_main_panel(flight, slot_opts, width))
            frames.append(_draw_detail_panel(flight, slot_opts, width))
    if frames:
        return _save_cycle(frames)
    errors = snapshot.get("errors") or []
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
    return _render_error("Updating flight data", width)
