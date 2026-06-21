from io import BytesIO
import hashlib
import json
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
CARD_DETAIL = "Free live ADS-B flights above you"
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
_SNAPSHOT_TTL_SECONDS = 20
_EMPTY_SNAPSHOT_TTL_SECONDS = 15
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


def _route_for_callsign(callsign):
    callsign = _clean(callsign)
    if not callsign:
        return ""
    try:
        url = "https://api.adsbdb.com/v0/callsign/" + urllib.parse.quote(callsign)
        data = _fetch_json_fast(url, seconds=_ROUTE_CACHE_SECONDS, timeout=1.0)
        response = data.get("response") or {}
        route = response.get("flightroute") or response
        origin = _airport_code(route.get("origin"))
        dest = _airport_code(route.get("destination"))
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
    rows = []
    seen = set()
    for provider in providers:
        try:
            for row in provider(lat, lon, radius_nm):
                key = str(row.get("hex") or row.get("icao24") or row.get("flight") or id(row)).lower()
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
        except Exception:
            continue
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
    draw.rectangle((0, 0, 127, 8), fill=(0, 15, 45))
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
    draw_sharp_text(image, (tx, 13), row["airline"][:16], (100, 190, 255), font)
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

    draw.rectangle((0, 0, 63, 8), fill=(0, 15, 45))
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
    draw_sharp_text(image, (1, 23), line4[:14], (150, 200, 255), font)
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
    if opts.get("showAirliners", True):
        allowed.update(("airliner", "heavy"))
    if opts.get("showRegionalJets", True):
        allowed.add("regional")
    if opts.get("showBusinessJets", True):
        allowed.add("business")
    if opts.get("showHelicopters", True):
        allowed.add("helicopter")
    if opts.get("showSmallProps", False):
        allowed.add("prop")
    return allowed or {"airliner", "heavy", "regional"}


def _flight_row(home_lat, home_lon, item, rank):
    dist, row = item
    callsign = (row.get("flight") or row.get("callsign") or "").strip().upper()
    alt_ft = int(_num(row.get("alt_baro") if row.get("alt_baro") != "ground" else row.get("alt_geom")))
    speed_kt = int(_num(row.get("gs") or row.get("speed")))
    lat = _num(row.get("lat"), None)
    lon = _num(row.get("lon"), None)
    direction = compass_dir(home_lat, home_lon, lat, lon)
    airline = lookup_airline(callsign)
    airline_name = airline[0] if airline else callsign[:8]
    iata = airline[1] if airline else _ICAO_TO_IATA.get(callsign[:3])
    flight_num = _display_flight(callsign)
    route = _route_for_callsign(callsign)
    return {
        "rank": rank,
        "callsign": callsign,
        "flight": flight_num or "UNKNOWN",
        "airline": airline_name or "UNKNOWN",
        "iata": iata,
        "distance": dist,
        "direction": direction,
        "alt_ft": alt_ft,
        "speed_kt": speed_kt,
        "route": route,
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


def _render_wide_list(rows):
    frames = []
    for row in rows:
        frames.append(_draw_wide_flight(row))
    return _save_cycle(frames)


def _render_64_list(rows):
    frames = []
    for row in rows:
        frames.append(_draw_64_flight(row))
    return _save_cycle(frames)


def _save_cycle(frames):
    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=5000,
        loop=0,
        lossless=True,
        quality=100,
    )
    return {
        "body": out.getvalue(),
        "dwell_secs": max(1, len(frames) * 5),
        "_stay": False,
    }


def _snapshot_key(opts):
    keys = [
        "zipCode", "radiusMiles", "source", "showAirliners", "showRegionalJets",
        "showBusinessJets", "showHelicopters", "showSmallProps",
    ]
    payload = {key: str((opts or {}).get(key) or "") for key in keys}
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _build_snapshot(opts):
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
    rows = [_flight_row(lat, lon, item, index + 1) for index, item in enumerate(flights[:5])]
    return {"rows": rows, "radius": radius, "updated": time.time()}


def _refresh_snapshot(key, opts):
    try:
        now = time.time()
        try:
            snapshot = _build_snapshot(opts)
            expires = now + (_SNAPSHOT_TTL_SECONDS if snapshot.get("rows") else _EMPTY_SNAPSHOT_TTL_SECONDS)
            snapshot["expires"] = expires
        except Exception as exc:
            snapshot = {"rows": [], "radius": max(10, min(500, int((opts or {}).get("radiusMiles") or 50))), "error": str(exc), "updated": now, "expires": now + _EMPTY_SNAPSHOT_TTL_SECONDS}
        with _SNAPSHOT_LOCK:
            current = _SNAPSHOT_CACHE.get(key)
            if snapshot.get("rows") or not (current and current.get("rows")):
                _SNAPSHOT_CACHE[key] = snapshot
            else:
                current["expires"] = now + _SNAPSHOT_TTL_SECONDS
                current["error"] = snapshot.get("error") or ""
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
        return _render_wide_list(rows) if wide else _render_64_list(rows)
    if _skip_no_data(opts):
        return None
    radius = (snapshot or {}).get("radius") or max(10, min(500, int((opts or {}).get("radiusMiles") or 50)))
    if (snapshot or {}).get("error"):
        return _render_message("Updating flights", wide)
    return _render_message(f"No flights within {radius} mi", wide)


def render(options=None):
    opts = options or {}
    wide = _is_wide(opts)
    snapshot = _queue_snapshot_refresh(_snapshot_key(opts), opts)
    if not snapshot:
        if _skip_no_data(opts):
            return None
        return _render_message("Updating flights", wide)
    return _render_snapshot(snapshot, opts, wide)
