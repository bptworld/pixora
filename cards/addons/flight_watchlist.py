from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from card_utils import (
    draw_pixora_bold_number,
    draw_sharp_text,
    fetch_airline_logo,
    haversine_miles,
    lookup_airline,
    pixora_bold_number_size,
)

CARD_ID = "flight_watchlist"
CARD_NAME = "Flight Watchlist"
CARD_DETAIL = "Watch flights, pickups, countdowns, and near alerts"

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
for _idx in range(1, 6):
    CARD_OPTIONS.extend([
        {
            "key": f"airline{_idx}",
            "label": f"Airline {_idx}",
            "type": "select",
            "default": "DL" if _idx == 1 else "",
            "choices": ([{"value": "", "label": "-"}] if _idx > 1 else []) + _AIRLINE_CHOICES,
        },
        {
            "key": f"flightNumber{_idx}",
            "label": f"Flight # {_idx}",
            "type": "text",
            "default": "977" if _idx == 1 else "",
            "maxlength": 6,
            "inputmode": "numeric",
        },
    ])
CARD_OPTIONS.extend([
    {
        "key": "mode",
        "label": "Mode",
        "type": "select",
        "default": "watchlist",
        "choices": [
            {"value": "watchlist", "label": "Watchlist"},
            {"value": "pickup", "label": "Pickup Mode"},
            {"value": "countdown", "label": "Arrival Countdown"},
            {"value": "near", "label": "Plane Is Near"},
        ],
    },
    {"key": "homeZip", "label": "Home ZIP", "type": "text", "default": "", "maxlength": 5, "inputmode": "numeric"},
    {"key": "nearMiles", "label": "Near Alert Miles", "type": "number", "default": "35"},
    {"key": "delayAlerts", "label": "Delay / cancel alerts", "type": "checkbox", "default": True},
    {"key": "gateAlerts", "label": "Gate change alerts", "type": "checkbox", "default": True},
    {"key": "landedAlerts", "label": "Landed alerts", "type": "checkbox", "default": True},
    {"key": "nearAlerts", "label": "Plane near alerts", "type": "checkbox", "default": True},
    {"key": "skipNoData", "label": "Skip if no data", "type": "checkbox", "default": False},
])
del _idx

_FLIGHTSTATS_ROOT = "https://www.flightstats.com/v2/api-next/flight-tracker"
_ADSB_LOL_ROOT = "https://api.adsb.lol/v2/callsign"
_ADSB_FI_ROOT = "https://opendata.adsb.fi/api/v3/callsign"
_CACHE = {}
_STATE = {}
_CACHE_MAX = 96
_ICAO_TO_IATA = {
    "AAL": "AA", "UAL": "UA", "DAL": "DL", "SWA": "WN", "ASA": "AS",
    "JBU": "B6", "FFT": "F9", "NKS": "NK", "HAL": "HA", "BAW": "BA",
    "AFR": "AF", "DLH": "LH", "UAE": "EK", "ACA": "AC",
}
_IATA_TO_ICAO = {v: k for k, v in _ICAO_TO_IATA.items()}
_AIRLINE_COLORS = {
    "AA": (0, 80, 160),
    "AC": (210, 20, 36),
    "AF": (0, 35, 120),
    "AS": (0, 85, 135),
    "B6": (0, 70, 160),
    "BA": (0, 60, 130),
    "DL": (180, 20, 35),
    "EK": (210, 20, 35),
    "F9": (0, 115, 60),
    "HA": (85, 35, 130),
    "LH": (255, 190, 0),
    "NK": (255, 220, 0),
    "UA": (0, 85, 170),
    "WN": (45, 75, 170),
}


def _clean(value):
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _truthy(value):
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "on"}


def _is_wide(options):
    opts = options or {}
    return opts.get("_target") == "matrixportal-s3-128x32" or opts.get("_pixora_target") == "pixora-s3-wide"


def _parse_int(value, default, lo, hi):
    try:
        number = int(float(value))
    except Exception:
        number = default
    return max(lo, min(hi, number))


def _configured(opts):
    flights = []
    for idx in range(1, 6):
        airline = _clean(opts.get(f"airline{idx}") or "")[:3]
        number = "".join(ch for ch in str(opts.get(f"flightNumber{idx}") or "") if ch.isdigit())
        if airline and number:
            flights.append({"airline": airline, "number": number, "slot": idx, "ident": airline + number})
    return flights


def _fetch_json(url, seconds=600, timeout=2.0):
    now = time.time()
    for key, item in list(_CACHE.items()):
        if item.get("expires", 0) <= now:
            _CACHE.pop(key, None)
    cached = _CACHE.get(url)
    if cached and cached["expires"] > now:
        return cached["data"]
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; Pixora/0.1)", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    _CACHE[url] = {"expires": now + seconds, "data": data}
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)), None)
    return data


def _local_midnights():
    now = time.localtime()
    today = int(time.mktime((now.tm_year, now.tm_mon, now.tm_mday, 0, 0, 0, 0, 0, -1)))
    return [today, today - 86400, today + 86400]


def _airport_code(value):
    if isinstance(value, dict):
        value = value.get("fs") or value.get("iata") or value.get("iata_code") or value.get("icao")
    return _clean(value)[:4] or "---"


def _time_text(airport, bucket="estimatedActual"):
    times = airport.get("times") if isinstance(airport, dict) else {}
    if not isinstance(times, dict):
        return ""
    value = times.get(bucket) or times.get("estimatedActual") or times.get("scheduled") or {}
    if not isinstance(value, dict):
        return ""
    text = str(value.get("time") or "")
    ampm = str(value.get("ampm") or "")
    return (text + ampm[:1]).upper().replace(" ", "")


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _fetch_flightstats(flight):
    airline = flight["airline"]
    number = flight["number"]
    for day_ts in _local_midnights():
        day = time.localtime(day_ts)
        url = f"{_FLIGHTSTATS_ROOT}/{urllib.parse.quote(airline)}/{urllib.parse.quote(number)}/{day.tm_year}/{day.tm_mon}/{day.tm_mday}"
        try:
            data = _fetch_json(url, seconds=600, timeout=2.2)
        except urllib.error.HTTPError as err:
            if err.code in (400, 404):
                continue
            return {}
        except Exception:
            continue
        detail = data.get("data") if isinstance(data, dict) else {}
        if isinstance(detail, dict) and (detail.get("departureAirport") or detail.get("arrivalAirport")):
            return detail
    return {}


def _summary(flight):
    detail = _fetch_flightstats(flight)
    dep = detail.get("departureAirport") if isinstance(detail.get("departureAirport"), dict) else {}
    arr = detail.get("arrivalAirport") if isinstance(detail.get("arrivalAirport"), dict) else {}
    status = detail.get("status") if isinstance(detail.get("status"), dict) else {}
    note = detail.get("flightNote") if isinstance(detail.get("flightNote"), dict) else {}
    schedule = detail.get("schedule") if isinstance(detail.get("schedule"), dict) else {}
    final = str(status.get("finalStatus") or status.get("status") or note.get("phase") or "").upper()
    status_text = str(status.get("statusDescription") or status.get("status") or note.get("message") or final or "").upper()
    arr_dt = _parse_iso(schedule.get("estimatedActualArrivalUTC") or schedule.get("scheduledArrivalUTC"))
    dep_dt = _parse_iso(schedule.get("estimatedActualDepartureUTC") or schedule.get("scheduledDepartureUTC"))
    return {
        **flight,
        "origin": _airport_code(dep),
        "destination": _airport_code(arr),
        "status": final or status_text or "SCHEDULED",
        "status_text": status_text or "SCHEDULED",
        "departure_time": _time_text(dep),
        "arrival_time": _time_text(arr),
        "gate": str(arr.get("gate") or dep.get("gate") or "").upper(),
        "terminal": str(arr.get("terminal") or dep.get("terminal") or "").upper(),
        "baggage": str(arr.get("baggage") or "").upper(),
        "arrival_dt": arr_dt,
        "departure_dt": dep_dt,
    }


def _home_latlon(zip_code):
    zip_code = re.sub(r"\D", "", str(zip_code or ""))[:5]
    if len(zip_code) != 5:
        return None
    try:
        data = _fetch_json(f"https://api.zippopotam.us/us/{zip_code}", seconds=86400, timeout=1.4)
        place = data["places"][0]
        return float(place["latitude"]), float(place["longitude"])
    except Exception:
        return None


def _extract_aircraft(data):
    if not isinstance(data, dict):
        return []
    rows = data.get("ac") or data.get("aircraft") or data.get("data") or []
    return rows if isinstance(rows, list) else []


def _callsign_candidates(item):
    airline = item.get("airline") or ""
    number = item.get("number") or ""
    values = [airline + number]
    if airline in _IATA_TO_ICAO:
        values.insert(0, _IATA_TO_ICAO[airline] + number)
    return [value for idx, value in enumerate(values) if value and value not in values[:idx]]


def _find_live_position(item):
    for callsign in _callsign_candidates(item):
        for root in (_ADSB_LOL_ROOT, _ADSB_FI_ROOT):
            url = f"{root}/{urllib.parse.quote(callsign)}"
            try:
                data = _fetch_json(url, seconds=25, timeout=1.8)
            except Exception:
                continue
            rows = _extract_aircraft(data)
            usable = []
            for row in rows:
                row_callsign = _clean(row.get("flight") or row.get("callsign") or "")
                if row_callsign and row_callsign != callsign:
                    continue
                if row.get("lat") is not None and row.get("lon") is not None:
                    usable.append(row)
            if usable:
                usable.sort(key=lambda row: float(row.get("seen_pos") or row.get("seen") or 999))
                return usable[0]
    return None


def _near_info(item, home, threshold):
    if not home:
        return None
    row = _find_live_position(item)
    if not row:
        return None
    try:
        lat = float(row.get("lat"))
        lon = float(row.get("lon"))
        miles = haversine_miles(home[0], home[1], lat, lon)
    except Exception:
        return None
    return {"miles": miles, "near": miles <= threshold, "alt": int(float(row.get("alt_baro") if row.get("alt_baro") != "ground" else 0) or 0)}


def _status_color(text):
    text = str(text or "").upper()
    if "CANCEL" in text:
        return (255, 70, 70)
    if "DELAY" in text:
        return (255, 190, 90)
    if "LANDED" in text or "ARRIVED" in text:
        return (100, 190, 255)
    return (95, 230, 135)


def _airline_color(item):
    airline = _clean((item or {}).get("airline") or "")[:2]
    return _AIRLINE_COLORS.get(airline, (0, 17, 45))


def _draw_flight_header(image, draw, item, bold, width, x=1):
    from PIL import Image, ImageDraw
    title = _fit(draw, item["ident"], bold, width - x - 1)
    mask = Image.new("1", image.size, 0)
    ImageDraw.Draw(mask).text((x, -3), title, fill=1, font=bold)
    title_bbox = mask.getbbox() or (0, 0, 0, 7)
    draw.rectangle((0, 0, width - 1, min(image.height - 1, title_bbox[3])), fill=_airline_color(item))
    draw_sharp_text(image, (x, -3), title, (255, 255, 255), bold)


def _countdown_value(minutes):
    if minutes is None:
        return "--"
    if minutes <= 0:
        return "NOW"
    if minutes < 60:
        return f"{minutes}M"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}H {mins}M" if mins else f"{hours}H"


def _bold_value_parts(value):
    text = str(value or "").upper()
    if not any(ch.isdigit() for ch in text):
        return []
    parts = []
    idx = 0
    numeric_chars = set("0123456789:.,+-/$%")
    while idx < len(text):
        is_numeric = text[idx] in numeric_chars
        start = idx
        idx += 1
        while idx < len(text) and ((text[idx] in numeric_chars) == is_numeric):
            idx += 1
        parts.append((is_numeric, text[start:idx]))
    return parts


def _bold_value_size(draw, value, suffix_font, scale=2, spacing=1, suffix_gap=2):
    parts = _bold_value_parts(value)
    if not parts:
        bbox = draw.textbbox((0, 0), str(value or ""), font=suffix_font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    width = 0
    height = 7 * scale
    previous_numeric = False
    for is_numeric, text in parts:
        if width and (is_numeric != previous_numeric):
            width += suffix_gap
        if is_numeric:
            part_w, part_h = pixora_bold_number_size(text, scale=scale, spacing=spacing)
        else:
            bbox = draw.textbbox((0, 0), text, font=suffix_font)
            part_w, part_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        width += part_w
        height = max(height, part_h)
        previous_numeric = is_numeric
    return width, height


def _draw_bold_value(image, draw, xy, value, color, suffix_font, scale=2, spacing=1, suffix_gap=2):
    parts = _bold_value_parts(value)
    if not parts:
        draw_sharp_text(image, xy, str(value or ""), color, suffix_font)
        return
    x, y = xy
    previous_numeric = False
    for idx, (is_numeric, text) in enumerate(parts):
        if idx and (is_numeric != previous_numeric):
            x += suffix_gap
        if is_numeric:
            draw_pixora_bold_number(draw, (x, y), text, color, scale=scale, spacing=spacing)
            x += pixora_bold_number_size(text, scale=scale, spacing=spacing)[0]
        else:
            try:
                suffix_top = suffix_font.getbbox(text)[1]
            except Exception:
                suffix_top = 0
            draw_sharp_text(image, (x, y - suffix_top), text, color, suffix_font)
            x += draw.textbbox((0, 0), text, font=suffix_font)[2]
        previous_numeric = is_numeric


def _fit(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1]
    return text


def _fonts():
    from PIL import ImageFont
    try:
        return (
            ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8),
            ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8),
            ImageFont.truetype("assets/fonts/Silkscreen-Bold.ttf", 16),
        )
    except Exception:
        font = ImageFont.load_default()
        return font, font, font


def _compact_watchlist_font():
    from PIL import ImageFont
    try:
        return ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 6)
    except Exception:
        return _fonts()[0]


def _webp(image):
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _draw_alert(title, line1, line2="", width=64, color=(255, 190, 90)):
    from PIL import Image, ImageDraw
    font, bold, big = _fonts()
    image = Image.new("RGB", (width, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, 6), fill=(42, 10, 18))
    title = _fit(draw, title.upper(), bold, width - 2)
    draw_sharp_text(image, (1, -3), title, color, bold)
    draw_sharp_text(image, (1, 9), _fit(draw, line1.upper(), font, width - 2), (245, 250, 255), font)
    if line2:
        draw_sharp_text(image, (1, 19), _fit(draw, line2.upper(), font, width - 2), (150, 200, 255), font)
    return image


def _draw_watchlist(items, width=64):
    from PIL import Image, ImageDraw
    font, bold, _big = _fonts()
    image = Image.new("RGB", (width, 32), (0, 5, 18))
    draw = ImageDraw.Draw(image)
    title = "FLIGHT WATCH" if width > 64 else "WATCH"
    title_bbox = draw.textbbox((1, -3), title, font=bold)
    draw.rectangle((0, 0, min(width - 1, title_bbox[2]), 8), fill=(0, 17, 45))
    draw_sharp_text(image, (1, -3), title, (100, 190, 255), bold)
    compact = width <= 64
    row_font = _compact_watchlist_font() if compact else font
    rows = items[:3] if compact else items[:4]
    for idx, item in enumerate(rows):
        y = (8 + idx * 7) if compact else (8 + idx * 6)
        route = f"{item.get('origin','---')}>{item.get('destination','---')}"
        status = item.get("status") or ""
        text = f"{item['ident']} {route} {item.get('arrival_time') or item.get('departure_time') or status}"
        color = _status_color(status)
        draw_sharp_text(image, (1, y), _fit(draw, text, row_font, width - 2), color, row_font)
    return image


def _draw_pickup(item, width=64):
    from PIL import Image, ImageDraw
    font, bold, _big = _fonts()
    image = Image.new("RGB", (width, 32), (0, 5, 18))
    draw = ImageDraw.Draw(image)
    logo = fetch_airline_logo(item["airline"])
    x = 1
    if logo and width > 64:
        image.paste(logo, (1, 0), logo)
        x = 18
    _draw_flight_header(image, draw, item, bold, width, x=x)
    route = f"{item.get('origin','---')}>{item.get('destination','---')} ARR {item.get('arrival_time') or '--'}"
    extras = " ".join(part for part in (("G" + item["gate"]) if item.get("gate") else "", ("T" + item["terminal"]) if item.get("terminal") else "", ("BAG " + item["baggage"]) if item.get("baggage") else "") if part)
    draw_sharp_text(image, (1, 8), _fit(draw, route, font, width - 2), (100, 190, 255), font)
    draw_sharp_text(image, (1, 16), _fit(draw, extras or item.get("status_text") or "FLIGHT STATUS", font, width - 2), (255, 220, 90), font)
    status_y = 20 if width <= 64 else 24
    draw_sharp_text(image, (1, status_y), _fit(draw, item.get("status") or "SCHEDULED", font, width - 2), _status_color(item.get("status")), font)
    return image


def _minutes_until(item):
    target = item.get("arrival_dt") or item.get("departure_dt")
    if not target:
        return None
    now = datetime.now(timezone.utc)
    return int(round((target.astimezone(timezone.utc) - now).total_seconds() / 60.0))


def _draw_countdown(item, width=64):
    from PIL import Image, ImageDraw
    font, bold, big = _fonts()
    image = Image.new("RGB", (width, 32), (0, 5, 18))
    draw = ImageDraw.Draw(image)
    minutes = _minutes_until(item)
    label = "ARRIVES" if item.get("arrival_dt") else "DEPARTS"
    value = _countdown_value(minutes)
    _draw_flight_header(image, draw, item, bold, width)
    vw, _vh = _bold_value_size(draw, value, font)
    value_y = 8 if width <= 64 else 9
    _draw_bold_value(image, draw, ((width - vw) // 2, value_y), value, (255, 220, 90), font)
    route = f"{item.get('origin','---')}>{item.get('destination','---')} {label}"
    route_y = 20 if width <= 64 else 24
    draw_sharp_text(image, (1, route_y), _fit(draw, route, font, width - 2), (100, 190, 255), font)
    return image


def _draw_near(item, near, width=64):
    from PIL import Image, ImageDraw
    font, bold, big = _fonts()
    image = Image.new("RGB", (width, 32), (0, 5, 18))
    draw = ImageDraw.Draw(image)
    miles = near.get("miles") if near else None
    value = "--MI" if miles is None else f"{int(round(miles))}MI"
    _draw_flight_header(image, draw, item, bold, width)
    vw, _vh = _bold_value_size(draw, value, font)
    value_y = 8 if width <= 64 else 9
    _draw_bold_value(image, draw, ((width - vw) // 2, value_y), value, (255, 220, 90), font)
    route = f"{item.get('origin','---')}>{item.get('destination','---')}"
    route_y = 20 if width <= 64 else 24
    draw_sharp_text(image, (1, route_y), _fit(draw, route, font, width - 2), (100, 190, 255), font)
    return image


def _save_cycle(frames):
    if not frames:
        return None
    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=3800, loop=0, lossless=True, quality=100)
    return {"body": out.getvalue(), "dwell_secs": max(5, len(frames) * 4), "_stay": False}


def _state_key(item):
    return item.get("ident") or f"{item.get('airline')}{item.get('number')}"


def _alert_for(opts, items, near_by_ident):
    for item in items:
        key = _state_key(item)
        current = {
            "status": item.get("status") or "",
            "gate": item.get("gate") or "",
            "near": bool((near_by_ident.get(key) or {}).get("near")),
        }
        previous = _STATE.get(key)
        _STATE[key] = current
        if not previous:
            continue
        status = current["status"].upper()
        if _truthy(opts.get("delayAlerts", True)) and current["status"] != previous.get("status") and ("DELAY" in status or "CANCEL" in status):
            return _draw_alert("FLIGHT ALERT", item["ident"], status), 7
        if _truthy(opts.get("landedAlerts", True)) and current["status"] != previous.get("status") and ("LANDED" in status or "ARRIVED" in status):
            return _draw_alert("LANDED", item["ident"], item.get("destination") or "", color=(100, 190, 255)), 7
        if _truthy(opts.get("gateAlerts", True)) and current["gate"] and previous.get("gate") and current["gate"] != previous.get("gate"):
            return _draw_alert("GATE CHANGE", item["ident"], f"{previous.get('gate')} > {current['gate']}"), 7
        if _truthy(opts.get("nearAlerts", True)) and current["near"] and not previous.get("near"):
            near = near_by_ident.get(key) or {}
            return _draw_alert("PLANE NEAR", item["ident"], f"{int(round(near.get('miles', 0)))} MI"), 7
    return None, 0


def render(options=None):
    opts = options or {}
    width = 128 if _is_wide(opts) else 64
    flights = _configured(opts)
    if not flights:
        image = _draw_alert("FLIGHT WATCH", "SET FLIGHT", width=width, color=(100, 190, 255))
        return {"body": _webp(image), "dwell_secs": 5, "_stay": False}
    items = [_summary(flight) for flight in flights]
    items = [item for item in items if item.get("origin") != "---" or item.get("destination") != "---"]
    if not items:
        if _truthy(opts.get("skipNoData")):
            return None
        image = _draw_alert("FLIGHT WATCH", "NO DATA", width=width, color=(100, 190, 255))
        return {"body": _webp(image), "dwell_secs": 5, "_stay": False}

    home = _home_latlon(opts.get("homeZip"))
    threshold = _parse_int(opts.get("nearMiles"), 35, 1, 500)
    near_by_ident = {}
    mode = str(opts.get("mode") or "watchlist").lower()
    if home and (_truthy(opts.get("nearAlerts", True)) or mode == "near"):
        for item in items:
            near = _near_info(item, home, threshold)
            if near:
                near_by_ident[_state_key(item)] = near

    alert, dwell = _alert_for(opts, items, near_by_ident)
    if alert is not None:
        return {"body": _webp(alert), "dwell_secs": dwell, "_stay": False, "_priority_graphic": True}

    if mode == "pickup":
        frames = [_draw_pickup(item, width) for item in items]
    elif mode == "countdown":
        frames = [_draw_countdown(item, width) for item in items]
    elif mode == "near":
        frames = [_draw_near(item, near_by_ident.get(_state_key(item)), width) for item in items]
    else:
        frames = [_draw_watchlist(items, width)]
    return _save_cycle(frames)
