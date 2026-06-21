from collections import deque
from datetime import datetime, timezone
from io import BytesIO
import json
import math
from pathlib import Path
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from card_utils import (
    compass_dir,
    draw_sharp_text,
    fetch_json_request,
    format_distance_miles,
    format_speed_knots,
    haversine_miles,
    _settings_value,
)
from flights_overhead import _aircraft_bucket, _extract_aircraft, _num, _zip_latlon


CARD_ID = "helicopter_tracker"
CARD_NAME = "Helicopter Tracker"
CARD_CATEGORY = "Travel"
CARD_DETAIL = "Live helicopter route trace near a ZIP code"
CARD_ATTRIBUTION = "Map/geocoding (c) OpenStreetMap contributors"
CARD_OPTIONS = [
    {"key": "zipCode", "label": "ZIP Code", "type": "text", "default": "10001", "maxlength": 5, "inputmode": "numeric"},
    {"key": "radiusMiles", "label": "Tracking Radius (mi)", "type": "number", "default": "10"},
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
    {"key": "trailMinutes", "label": "Trail Minutes", "type": "number", "default": "45"},
    {"key": "skipNoData", "label": "Skip if no data", "type": "checkbox", "default": False},
]

DEFAULT_RADIUS_MILES = 10.0
MAX_MAP_VIEW_MILES = 10.0
SOURCE_CACHE_SECONDS = 5
MAX_TRAIL_POINTS = 180
STALE_SECONDS = 120
MAP_ZOOM = 12
TILE_SIZE = 256
_TRAILS = {}
_LAST_SEEN = {}
_TILE_CACHE = {}
_PLACE_CACHE = {}
_STATE_LOCK = threading.RLock()
_TRACKER_THREAD = None
_TRACKER_CONFIG = None
_TRACKER_CONFIG_KEY = None
_TRACKER_LAST_LIVE = []
_TRACKER_LAST_FETCH = 0.0
_TRACKER_LAST_ERROR = ""
_HELICOPTER_ASSET_BASE_URL = "https://raw.githubusercontent.com/bptworld/pixora/main/cards/assets/helicopters"
_HELICOPTER_ASSET_DISPLAY_SIZE = (21, 10)
_HELICOPTER_ASSET_BY_TYPE = {
    "A109": "leonardo_aw109",
    "A119": "leonardo_aw119",
    "A139": "leonardo_aw139",
    "A169": "leonardo_aw169",
    "A189": "leonardo_aw189",
    "AS50": "airbus_h125",
    "AS65": "airbus_as365",
    "AS32": "airbus_h225",
    "B204": "bell_204_205",
    "B205": "bell_204_205",
    "B06": "bell_206",
    "B212": "bell_212",
    "B222": "bell_222",
    "B407": "bell_407",
    "B412": "bell_412",
    "B429": "bell_429",
    "B430": "bell_430",
    "B505": "bell_505",
    "CH47": "boeing_ch47",
    "EC20": "airbus_h120",
    "EC30": "airbus_h130",
    "EC35": "airbus_h135",
    "EC45": "airbus_h145",
    "EC55": "airbus_h155",
    "EC75": "airbus_h175",
    "EH10": "leonardo_aw101",
    "EN48": "schweizer_300",
    "G2CA": "guimbal_cabri_g2",
    "H53": "sikorsky_ch53",
    "H53S": "sikorsky_ch53e_k",
    "H47": "boeing_ch47",
    "H500": "md_500",
    "H60": "sikorsky_uh60",
    "H64": "boeing_ah64",
    "HUCO": "bell_ah1",
    "H160": "airbus_h160",
    "KA32": "kamov_ka32",
    "MI2": "mil_mi2",
    "MI8": "mil_mi8",
    "MI24": "mil_mi24",
    "MD60": "md_600",
    "R22": "robinson_r22",
    "R44": "robinson_r44",
    "R66": "robinson_r66",
    "S300": "schweizer_300",
    "S76": "sikorsky_s76",
    "S92": "sikorsky_s92",
    "SUCO": "bell_ah1",
    "UH1": "bell_204_205",
    "UH1Y": "bell_uh1y",
    "V22": "bell_boeing_v22",
}
_HELICOPTER_PICTURE_CACHE = {}

try:
    FONT_7 = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
except Exception:
    FONT_7 = ImageFont.load_default()


def _is_wide(options):
    return (options or {}).get("_target") == "matrixportal-s3-128x32"


def _truthy(value):
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "on"}


def _skip_no_data(options):
    return _truthy((options or {}).get("skipNoData"))


def _clean(value):
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _fit(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1]
    return text


def _home_zip(opts):
    zip_code = re.sub(r"\D", "", str((opts or {}).get("zipCode") or ""))[:5]
    if len(zip_code) == 5:
        return zip_code
    zip_code = re.sub(r"\D", "", str(_settings_value("defaultZipCode", "") or ""))[:5]
    return zip_code if len(zip_code) == 5 else "10001"


def _radius_miles(opts):
    try:
        return max(1.0, min(100.0, float((opts or {}).get("radiusMiles") or DEFAULT_RADIUS_MILES)))
    except Exception:
        return DEFAULT_RADIUS_MILES


def _map_view_miles(radius_miles):
    return max(1.0, min(MAX_MAP_VIEW_MILES, float(radius_miles or DEFAULT_RADIUS_MILES)))


def _aircraft_key(row):
    return _clean(row.get("hex") or row.get("icao24") or row.get("r") or row.get("registration") or row.get("flight") or row.get("callsign")) or "HELI"


def _aircraft_label(row):
    label = _clean(row.get("flight") or row.get("callsign") or row.get("r") or row.get("registration") or row.get("hex"))
    return label[:9] or "HELI"


def _registration(row):
    return _clean(row.get("r") or row.get("reg") or row.get("registration"))[:9]


def _hex_id(row):
    return _clean(row.get("hex") or row.get("icao24"))[:6]


def _type_code(row):
    value = _clean(row.get("t") or row.get("typeCode") or row.get("aircraft_type") or row.get("icao_type"))
    if value:
        return value[:6]
    fallback = _clean(row.get("type"))
    if fallback and "_" not in str(row.get("type")) and fallback not in ("ADSB", "MLAT", "TISB", "MODE"):
        return fallback[:6]
    return "---"


def _source_label(row):
    raw = str(row.get("source") or row.get("data_source") or row.get("type") or "").strip().upper()
    if "MLAT" in raw:
        return "MLAT"
    if "TIS" in raw:
        return "TIS-B"
    if "MODE" in raw:
        return "MODE-S"
    if "ADSB" in raw or "ADS-B" in raw:
        return "ADS-B"
    return "ADS-B"


def _fetch_source(url):
    try:
        return _extract_aircraft(fetch_json_request(url, seconds=SOURCE_CACHE_SECONDS))
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


def _speed(row):
    return int(_num(row.get("gs") or row.get("speed"), 0))


def _altitude(row):
    value = row.get("alt_baro")
    if value == "ground":
        value = row.get("alt_geom")
    return int(_num(value, 0))


def _trail_minutes(opts):
    try:
        return max(5, min(180, int((opts or {}).get("trailMinutes") or 45)))
    except Exception:
        return 45


def _place_name(lat, lon):
    key = (round(float(lat), 2), round(float(lon), 2))
    cached = _PLACE_CACHE.get(key)
    if cached is not None:
        return cached
    query = urllib.parse.urlencode({"lat": f"{lat:.5f}", "lon": f"{lon:.5f}", "format": "jsonv2", "zoom": "12", "addressdetails": "1"})
    request = urllib.request.Request(
        "https://nominatim.openstreetmap.org/reverse?" + query,
        headers={
            "User-Agent": "Pixora/0.1 helicopter_tracker",
            "Accept": "application/json",
            "Accept-Language": "en",
        },
    )
    label = ""
    try:
        with urllib.request.urlopen(request, timeout=1.2) as response:
            data = json.loads(response.read().decode("utf-8"))
        address = data.get("address") or {}
        value = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("hamlet")
            or address.get("municipality")
            or address.get("suburb")
            or address.get("county")
            or ""
        )
        label = _short_place_name(re.sub(r"[^A-Za-z0-9 .'-]", "", str(value).upper()).strip())
    except Exception:
        label = ""
    _PLACE_CACHE[key] = label
    while len(_PLACE_CACHE) > 64:
        _PLACE_CACHE.pop(next(iter(_PLACE_CACHE)), None)
    return label


def _short_place_name(value):
    words = []
    abbreviations = {
        "NORTH": "N",
        "EAST": "E",
        "WEST": "W",
        "SOUTH": "S",
    }
    for word in str(value or "").split():
        words.append(abbreviations.get(word, word))
    return " ".join(words)


def _prune(now, trail_minutes):
    cutoff = now.timestamp() - trail_minutes * 60
    stale_cutoff = now.timestamp() - max(trail_minutes * 60, STALE_SECONDS)
    for key in list(_TRAILS):
        trail = _TRAILS[key]
        while trail and trail[0]["ts"] < cutoff:
            trail.popleft()
        if not trail or _LAST_SEEN.get(key, 0) < stale_cutoff:
            _TRAILS.pop(key, None)
            _LAST_SEEN.pop(key, None)


def _update_trails(home_lat, home_lon, rows, trail_minutes, radius_miles):
    now = datetime.now(timezone.utc)
    live = []
    with _STATE_LOCK:
        _prune(now, trail_minutes)
        for row in rows:
            if row.get("lat") is None or row.get("lon") is None:
                continue
            if _aircraft_bucket(row) != "helicopter":
                continue
            lat = _num(row.get("lat"), None)
            lon = _num(row.get("lon"), None)
            if lat is None or lon is None:
                continue
            dist = haversine_miles(home_lat, home_lon, lat, lon)
            if dist > radius_miles:
                continue
            key = _aircraft_key(row)
            point = {
                "ts": now.timestamp(),
                "lat": lat,
                "lon": lon,
                "dist": dist,
                "label": _aircraft_label(row),
                "reg": _registration(row),
                "hex": _hex_id(row),
                "type_code": _type_code(row),
                "source": _source_label(row),
                "alt": _altitude(row),
                "speed": _speed(row),
                "track": _num(row.get("track") or row.get("true_heading") or row.get("mag_heading"), None),
                "row": row,
            }
            trail = _TRAILS.setdefault(key, deque(maxlen=MAX_TRAIL_POINTS))
            if not trail or haversine_miles(trail[-1]["lat"], trail[-1]["lon"], lat, lon) >= 0.02:
                trail.append(point)
            else:
                trail[-1] = point
            _LAST_SEEN[key] = now.timestamp()
            live.append((dist, key, point))
    live.sort(key=lambda item: item[0])
    return live


def _tracker_key(zip_code, home_lat, home_lon, radius_miles, source, trail_minutes):
    return (
        str(zip_code),
        round(float(home_lat), 4),
        round(float(home_lon), 4),
        round(float(radius_miles), 1),
        str(source),
        int(trail_minutes),
    )


def _tracker_worker():
    global _TRACKER_LAST_ERROR, _TRACKER_LAST_FETCH, _TRACKER_LAST_LIVE
    while True:
        config = _TRACKER_CONFIG
        if not config:
            time.sleep(1.0)
            continue
        try:
            aircraft = _fetch_aircraft(config["home_lat"], config["home_lon"], config["radius_miles"], config["source"])
            live = _update_trails(config["home_lat"], config["home_lon"], aircraft, config["trail_minutes"], config["radius_miles"])
            with _STATE_LOCK:
                _TRACKER_LAST_LIVE = live
                _TRACKER_LAST_FETCH = time.time()
                _TRACKER_LAST_ERROR = ""
            if live:
                selected = live[0][2]
                _warm_map_cache(selected["lat"], selected["lon"], _map_view_miles(config["radius_miles"]))
        except Exception as err:
            with _STATE_LOCK:
                _TRACKER_LAST_ERROR = str(err)[:80]
        time.sleep(SOURCE_CACHE_SECONDS)


def _ensure_tracker(zip_code, home_lat, home_lon, radius_miles, source, trail_minutes):
    global _TRACKER_CONFIG, _TRACKER_CONFIG_KEY, _TRACKER_LAST_ERROR, _TRACKER_LAST_FETCH, _TRACKER_LAST_LIVE, _TRACKER_THREAD
    key = _tracker_key(zip_code, home_lat, home_lon, radius_miles, source, trail_minutes)
    with _STATE_LOCK:
        if key != _TRACKER_CONFIG_KEY:
            _TRAILS.clear()
            _LAST_SEEN.clear()
            _TRACKER_LAST_ERROR = ""
            _TRACKER_LAST_LIVE = []
            _TRACKER_LAST_FETCH = 0.0
            _TRACKER_CONFIG = {
                "zip_code": zip_code,
                "home_lat": home_lat,
                "home_lon": home_lon,
                "radius_miles": radius_miles,
                "source": source,
                "trail_minutes": trail_minutes,
            }
            _TRACKER_CONFIG_KEY = key
        if _TRACKER_THREAD is None or not _TRACKER_THREAD.is_alive():
            _TRACKER_THREAD = threading.Thread(target=_tracker_worker, name="pixora-helicopter-tracker", daemon=True)
            _TRACKER_THREAD.start()


def _latest_live():
    with _STATE_LOCK:
        return list(_TRACKER_LAST_LIVE), _TRACKER_LAST_FETCH, _TRACKER_LAST_ERROR


def _trail_keys():
    with _STATE_LOCK:
        return sorted(_TRAILS)


def _project(center_lat, center_lon, lat, lon, bounds, view_miles):
    left, top, right, bottom = bounds
    cx = (left + right) / 2.0
    cy = (top + bottom) / 2.0
    half_w = max(1.0, (right - left) / 2.0 - 1)
    half_h = max(1.0, (bottom - top) / 2.0 - 1)
    lat_miles = (lat - center_lat) * 69.0
    lon_miles = (lon - center_lon) * 69.0 * max(0.15, math.cos(math.radians(center_lat)))
    x = int(round(cx + (lon_miles / max(1.0, view_miles)) * half_w))
    y = int(round(cy - (lat_miles / max(1.0, view_miles)) * half_h))
    return max(left, min(right, x)), max(top, min(bottom, y))


def _latlon_to_global_pixel(lat, lon, zoom=MAP_ZOOM):
    lat = max(-85.05112878, min(85.05112878, float(lat)))
    lon = ((float(lon) + 180.0) % 360.0) - 180.0
    scale = TILE_SIZE * (2 ** zoom)
    x = (lon + 180.0) / 360.0 * scale
    sin_lat = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * scale
    return x, y


def _tile_url(zoom, x, y):
    return f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"


def _fetch_tile(zoom, x, y, fetch_missing=True):
    max_tile = 2 ** zoom
    if y < 0 or y >= max_tile:
        return None
    x %= max_tile
    key = (zoom, x, y)
    cached = _TILE_CACHE.get(key)
    if cached is not None:
        return cached.copy()
    if not fetch_missing:
        return None
    request = urllib.request.Request(
        _tile_url(zoom, x, y),
        headers={
            "User-Agent": "Pixora/0.1 helicopter_tracker",
            "Accept": "image/png,image/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=1.8) as response:
            tile = Image.open(BytesIO(response.read())).convert("RGB")
    except Exception:
        return None
    _TILE_CACHE[key] = tile
    while len(_TILE_CACHE) > 48:
        _TILE_CACHE.pop(next(iter(_TILE_CACHE)), None)
    return tile.copy()


def _source_pixels_per_mile(home_lat, zoom=MAP_ZOOM):
    earth_circumference_miles = 24901.0
    scale = TILE_SIZE * (2 ** zoom)
    return scale / (earth_circumference_miles * max(0.15, math.cos(math.radians(home_lat))))


def _map_source_geometry(center_lat, center_lon, bounds, view_miles):
    left, top, right, bottom = bounds
    out_w = max(1, right - left + 1)
    out_h = max(1, bottom - top + 1)
    center_x, center_y = _latlon_to_global_pixel(center_lat, center_lon, MAP_ZOOM)
    pixels_per_mile = _source_pixels_per_mile(center_lat, MAP_ZOOM)
    source_w = max(out_w, int(round(max(1.0, view_miles) * 2 * pixels_per_mile)))
    source_h = max(out_h, int(round(max(1.0, view_miles) * 2 * pixels_per_mile)))
    crop_left = int(round(center_x - source_w / 2))
    crop_top = int(round(center_y - source_h / 2))
    tile_left = math.floor(crop_left / TILE_SIZE)
    tile_top = math.floor(crop_top / TILE_SIZE)
    tile_right = math.floor((crop_left + source_w - 1) / TILE_SIZE)
    tile_bottom = math.floor((crop_top + source_h - 1) / TILE_SIZE)
    return out_w, out_h, source_w, source_h, crop_left, crop_top, tile_left, tile_top, tile_right, tile_bottom


def _warm_map_cache(center_lat, center_lon, view_miles):
    bounds = (1, 1, 83, 30)
    *_, tile_left, tile_top, tile_right, tile_bottom = _map_source_geometry(center_lat, center_lon, bounds, view_miles)
    for tx in range(tile_left, tile_right + 1):
        for ty in range(tile_top, tile_bottom + 1):
            _fetch_tile(MAP_ZOOM, tx, ty, fetch_missing=True)


def _map_background(center_lat, center_lon, bounds, view_miles):
    out_w, out_h, source_w, source_h, crop_left, crop_top, tile_left, tile_top, tile_right, tile_bottom = _map_source_geometry(center_lat, center_lon, bounds, view_miles)
    canvas = Image.new("RGB", ((tile_right - tile_left + 1) * TILE_SIZE, (tile_bottom - tile_top + 1) * TILE_SIZE), (2, 9, 18))
    any_tile = False
    for tx in range(tile_left, tile_right + 1):
        for ty in range(tile_top, tile_bottom + 1):
            tile = _fetch_tile(MAP_ZOOM, tx, ty, fetch_missing=False)
            if tile is None:
                continue
            any_tile = True
            canvas.paste(tile, ((tx - tile_left) * TILE_SIZE, (ty - tile_top) * TILE_SIZE))
    if not any_tile:
        return None
    local_left = crop_left - tile_left * TILE_SIZE
    local_top = crop_top - tile_top * TILE_SIZE
    crop = canvas.crop((local_left, local_top, local_left + source_w, local_top + source_h))
    resample = getattr(Image, "Resampling", Image).BILINEAR
    map_image = crop.resize((out_w, out_h), resample)
    map_image = ImageEnhance.Color(map_image).enhance(0.55)
    map_image = ImageEnhance.Contrast(map_image).enhance(1.45)
    map_image = ImageEnhance.Brightness(map_image).enhance(0.42)
    dither = getattr(getattr(Image, "Dither", Image), "NONE", 0)
    map_image = map_image.quantize(colors=16, dither=dither).convert("RGB")
    return map_image


def _draw_grid(draw, bounds):
    left, top, right, bottom = bounds
    draw.rectangle((left, top, right, bottom), fill=(2, 9, 18), outline=(32, 70, 88))
    cx = (left + right) // 2
    cy = (top + bottom) // 2
    for fraction, color in ((0.5, (18, 45, 58)), (1.0, (24, 62, 76))):
        rx = int((right - left) * 0.5 * fraction)
        ry = int((bottom - top) * 0.5 * fraction)
        draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), outline=color)
    draw.line((cx, top + 1, cx, bottom - 1), fill=(20, 48, 62))
    draw.line((left + 1, cy, right - 1, cy), fill=(20, 48, 62))
    draw.line((cx - 2, cy, cx + 2, cy), fill=(255, 220, 90))
    draw.line((cx, cy - 2, cx, cy + 2), fill=(255, 220, 90))


def _draw_map_or_grid(image, draw, center_lat, center_lon, bounds, view_miles):
    map_image = _map_background(center_lat, center_lon, bounds, view_miles)
    if map_image is not None:
        image.paste(map_image, (bounds[0], bounds[1]))
        draw.rectangle(bounds, outline=(32, 70, 88))
        cx = (bounds[0] + bounds[2]) // 2
        cy = (bounds[1] + bounds[3]) // 2
        draw.line((cx - 2, cy, cx + 2, cy), fill=(255, 220, 90))
        draw.line((cx, cy - 2, cx, cy + 2), fill=(255, 220, 90))
        return
    _draw_grid(draw, bounds)


def _helicopter_asset_name(point=None):
    type_code = str((point or {}).get("type_code") or "").strip().upper()
    return _HELICOPTER_ASSET_BY_TYPE.get(type_code, "robinson_r22")


def _fit_helicopter_picture(image):
    image = image.convert("RGBA")
    image.thumbnail(_HELICOPTER_ASSET_DISPLAY_SIZE, Image.LANCZOS)
    fitted = Image.new("RGBA", _HELICOPTER_ASSET_DISPLAY_SIZE, (0, 0, 0, 0))
    x = (_HELICOPTER_ASSET_DISPLAY_SIZE[0] - image.width) // 2
    y = (_HELICOPTER_ASSET_DISPLAY_SIZE[1] - image.height) // 2
    fitted.alpha_composite(image, (x, y))
    return fitted


def _helicopter_picture(point=None):
    asset_name = _helicopter_asset_name(point)
    cached = _HELICOPTER_PICTURE_CACHE.get(asset_name)
    if cached is not None:
        return cached or None

    sources = (
        ("remote", f"{_HELICOPTER_ASSET_BASE_URL}/{asset_name}.png"),
        ("local", Path(__file__).resolve().parent.parent / "assets" / "helicopters" / f"{asset_name}.png"),
        ("local", Path(__file__).resolve().parent.parent / "assets" / "helicopter_r22.png"),
    )
    for source_type, source in sources:
        try:
            if source_type == "remote":
                request = urllib.request.Request(str(source), headers={"User-Agent": "Pixora/0.1"})
                with urllib.request.urlopen(request, timeout=2) as response:
                    data = response.read()
                image = Image.open(BytesIO(data))
            else:
                image = Image.open(source)
            _HELICOPTER_PICTURE_CACHE[asset_name] = _fit_helicopter_picture(image)
            return _HELICOPTER_PICTURE_CACHE[asset_name]
        except Exception:
            continue

    _HELICOPTER_PICTURE_CACHE[asset_name] = False
    return None


def _draw_map_helicopter_picture(image, draw, bounds, point=None):
    asset = _helicopter_picture(point)
    if not asset:
        return
    x = bounds[0] + 3
    y = bounds[1] + 2
    draw.rectangle((x - 1, y - 1, x + asset.width, y + asset.height), fill=(0, 7, 14), outline=(35, 78, 96))
    image.paste(asset, (x, y), asset)


def _draw_trail(draw, center_lat, center_lon, key, selected_key, bounds, view_miles):
    with _STATE_LOCK:
        trail = list(_TRAILS.get(key) or [])
    if not trail:
        return
    color = (65, 235, 180) if key == selected_key else (38, 120, 112)
    points = [_project(center_lat, center_lon, point["lat"], point["lon"], bounds, view_miles) for point in trail]
    if len(points) > 1:
        for idx in range(1, len(points)):
            shade = color if idx >= len(points) - 6 else tuple(max(10, int(part * 0.55)) for part in color)
            draw.line((points[idx - 1][0], points[idx - 1][1], points[idx][0], points[idx][1]), fill=shade)
    x, y = points[-1]
    if key == selected_key:
        x = max(bounds[0] + 2, min(bounds[2] - 2, x))
        y = max(bounds[1] + 2, min(bounds[3] - 2, y))
        draw.rectangle((x - 1, y - 1, x + 1, y + 1), fill=(255, 220, 90))
    else:
        draw.rectangle((x - 1, y - 1, x + 1, y + 1), fill=color)


def _draw_helicopter_picture(draw, x, y):
    orange = (255, 126, 38)
    dark = (35, 18, 8)
    light = (255, 214, 120)
    glass = (22, 45, 62)
    draw.line((x - 1, y, x + 15, y), fill=dark)
    draw.line((x, y - 1, x + 14, y - 1), fill=orange)
    draw.line((x + 6, y, x + 6, y + 2), fill=light)
    draw.ellipse((x, y + 2, x + 8, y + 8), fill=orange, outline=dark)
    draw.pieslice((x + 1, y + 3, x + 7, y + 8), 90, 270, fill=glass)
    draw.rectangle((x + 6, y + 4, x + 10, y + 7), fill=orange, outline=dark)
    draw.line((x + 10, y + 5, x + 17, y + 3), fill=orange)
    draw.line((x + 16, y + 1, x + 17, y + 5), fill=dark)
    draw.line((x + 2, y + 10, x + 9, y + 10), fill=dark)
    draw.line((x + 2, y + 8, x, y + 10), fill=dark)
    draw.line((x + 8, y + 8, x + 10, y + 10), fill=dark)
    draw.point((x + 3, y + 5), fill=light)


def _altitude_label(value):
    value = int(value or 0)
    return f"{value}FT" if value > 0 else "GROUND"


def _bottom_label(draw, home_lat, home_lon, point, max_width, compact=False):
    distance = format_distance_miles(point["dist"], 1).upper()
    if compact and distance.endswith("MI"):
        distance = distance[:-2]
    direction = compass_dir(home_lat, home_lon, point["lat"], point["lon"])
    place = str(point.get("place") or "").strip()
    label = f"{distance}{direction}" if compact else f"{distance} {direction}"
    if place:
        label = f"{label} {place}"
    return _fit(draw, label, FONT_7, max_width)


def _draw_data_card(image, draw, box, point, compact=False):
    left, top, right, bottom = box
    draw.rectangle((left, top, right, bottom), fill=(7, 15, 22), outline=(68, 96, 110))
    draw.line((left + 1, top + 8, right - 1, top + 8), fill=(66, 190, 185))
    title = point.get("reg") or point.get("label") or "HELI"
    draw_sharp_text(image, (left + 2, top - 3), _fit(draw, title, FONT_7, right - left - 3), (245, 250, 255), FONT_7)
    if compact:
        draw_sharp_text(image, (left + 2, top + 7), _fit(draw, point.get("type_code") or "---", FONT_7, right - left - 3), (180, 205, 220), FONT_7)
        draw_sharp_text(image, (left + 2, top + 15), _fit(draw, _altitude_label(point.get("alt")), FONT_7, right - left - 3), (160, 210, 255), FONT_7)
        return
    hex_id = point.get("hex") or "---"
    type_code = point.get("type_code") or "---"
    speed = format_speed_knots(point.get("speed"))
    draw_sharp_text(image, (left + 2, top + 6), _fit(draw, hex_id, FONT_7, right - left - 3), (180, 205, 220), FONT_7)
    draw_sharp_text(image, (left + 2, top + 13), _fit(draw, f"{type_code} {_altitude_label(point.get('alt'))}", FONT_7, right - left - 3), (160, 210, 255), FONT_7)
    draw_sharp_text(image, (left + 2, top + 20), _fit(draw, f"{speed} {point.get('source') or 'ADS-B'}", FONT_7, right - left - 3), (80, 235, 180), FONT_7)


def _render_message(message, width):
    image = Image.new("RGB", (width, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    title = "HELICOPTERS" if width > 64 else "HELI"
    tw = draw.textbbox((0, 0), title, font=FONT_7)[2]
    draw_sharp_text(image, ((width - tw) // 2, -3), title, (100, 190, 255), FONT_7)
    words = str(message or "NO DATA").upper().split()
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
    for index, line in enumerate(lines[:3]):
        lw = draw.textbbox((0, 0), line, font=FONT_7)[2]
        draw_sharp_text(image, ((width - lw) // 2, 8 + index * 7), line, (255, 220, 90), FONT_7)
    return _save(image)


def _render_empty(message, width):
    return {
        "body": _render_message(message, width),
        "_stay": False,
    }


def _draw_wide(home_lat, home_lon, selected_key, selected_point, zip_code, view_miles):
    image = Image.new("RGB", (128, 32), (0, 4, 12))
    draw = ImageDraw.Draw(image)
    bounds = (1, 1, 83, 30)
    center_lat = selected_point["lat"]
    center_lon = selected_point["lon"]
    _draw_map_or_grid(image, draw, center_lat, center_lon, bounds, view_miles)
    for key in _trail_keys():
        _draw_trail(draw, center_lat, center_lon, key, selected_key, bounds, view_miles)
    _draw_map_helicopter_picture(image, draw, bounds, selected_point)
    _draw_data_card(image, draw, (86, 1, 127, 29), selected_point)
    draw.rectangle((1, 22, 83, 30), fill=(0, 12, 28))
    draw_sharp_text(image, (3, 22), _bottom_label(draw, home_lat, home_lon, selected_point, 78), (255, 220, 90), FONT_7)
    return image


def _draw_64(home_lat, home_lon, selected_key, selected_point, zip_code, view_miles):
    image = Image.new("RGB", (64, 32), (0, 4, 12))
    draw = ImageDraw.Draw(image)
    bounds = (0, 0, 35, 31)
    center_lat = selected_point["lat"]
    center_lon = selected_point["lon"]
    _draw_map_or_grid(image, draw, center_lat, center_lon, bounds, view_miles)
    for key in _trail_keys():
        _draw_trail(draw, center_lat, center_lon, key, selected_key, bounds, view_miles)
    _draw_data_card(image, draw, (37, 1, 63, 21), selected_point, compact=True)
    label = _bottom_label(draw, home_lat, home_lon, selected_point, 62, compact=True)
    lw = draw.textbbox((0, 0), label, font=FONT_7)[2]
    draw.rectangle((0, 23, 63, 31), fill=(0, 12, 28))
    draw_sharp_text(image, (max(1, 63 - lw), 23), label, (255, 220, 90), FONT_7)
    return image


def _save(image):
    out = BytesIO()
    dither = getattr(getattr(Image, "Dither", Image), "NONE", 0)
    image = image.quantize(colors=32, dither=dither).convert("RGB")
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def render(options=None):
    opts = options or {}
    width = 128 if _is_wide(opts) else 64
    zip_code = _home_zip(opts)
    source = str(opts.get("source") or "auto").lower()
    trail_minutes = _trail_minutes(opts)
    radius_miles = _radius_miles(opts)
    try:
        home_lat, home_lon = _zip_latlon(zip_code)
        _ensure_tracker(zip_code, home_lat, home_lon, radius_miles, source, trail_minutes)
    except Exception:
        if _skip_no_data(opts):
            return None
        return _render_empty("NO LIVE DATA", width)

    live, last_fetch, last_error = _latest_live()
    if not live:
        if _skip_no_data(opts):
            return None
        if not last_fetch and not last_error:
            return _render_empty("TRACKING HELI", width)
        return _render_empty(f"NO HELI WITHIN {int(round(radius_miles))}MI", width)

    _, selected_key, selected_point = live[0]
    selected_point["place"] = _place_name(selected_point["lat"], selected_point["lon"])
    view_miles = _map_view_miles(radius_miles)
    image = _draw_wide(home_lat, home_lon, selected_key, selected_point, zip_code, view_miles) if width > 64 else _draw_64(home_lat, home_lon, selected_key, selected_point, zip_code, view_miles)
    return {
        "body": _save(image),
        "_stay": False,
    }
