from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import urllib.parse
import urllib.request
from card_utils import (
    draw_sharp_text, fetch_airline_logo, format_speed_knots, format_time, iata_to_icao_prefix, lookup_airline,
    render_text_webp,
)

try:
    from PIL import ImageFont
    FONT_7 = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
except Exception:
    from PIL import ImageFont
    FONT_7 = ImageFont.load_default()

CARD_ID = "flight_track"
CARD_NAME = "Flight Tracker"
CARD_DETAIL = "Flightradar24 live and summary tracking"
CARD_OPTIONS = [
    {
        "key": "airline",
        "label": "Airline",
        "type": "select",
        "default": "WN",
        "choices": [
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
        ],
    },
    {"key": "flightNumber", "label": "Flight Number", "type": "text", "default": "3416", "maxlength": 6, "inputmode": "numeric"},
    {"key": "origin", "label": "Origin", "type": "text", "default": "", "maxlength": 3},
    {"key": "destination", "label": "Destination", "type": "text", "default": "", "maxlength": 3},
    {"key": "repeatDaily", "label": "Repeat this flight every day", "type": "checkbox", "default": False},
    {"key": "apiKey", "label": "Flightradar24 API Token", "type": "text", "default": ""},
]

_CACHE = {}
_CACHE_SECONDS = 300
_GEO_CACHE = {}
_GEO_DETAIL_CACHE = {}
_GEO_CACHE_SECONDS = 30 * 60
_TERMINAL_CACHE = {}
_TERMINAL_CACHE_SECONDS = 18 * 60 * 60
_FLIGHT_POLL_STATE = {}
_DISABLE_POLLING_FOR_TEST = False
_API_ROOT = "https://fr24api.flightradar24.com/api"
_AIRPORT_CITY = {
    "MCO": "ORLANDO FL",
    "MHT": "MANCHESTER NH",
    "SFB": "ORLANDO FL",
    "TPA": "TAMPA FL",
    "BOS": "BOSTON MA",
    "JFK": "NEW YORK NY",
    "LGA": "NEW YORK NY",
    "EWR": "NEWARK NJ",
    "DCA": "WASHINGTON DC",
    "IAD": "WASHINGTON DC",
    "BWI": "BALTIMORE MD",
    "ATL": "ATLANTA GA",
    "ORD": "CHICAGO IL",
    "MDW": "CHICAGO IL",
    "DEN": "DENVER CO",
    "DFW": "DALLAS TX",
    "DAL": "DALLAS TX",
    "LAX": "LOS ANGELES CA",
    "LAS": "LAS VEGAS NV",
    "PHX": "PHOENIX AZ",
    "SEA": "SEATTLE WA",
    "SFO": "SAN FRANCISCO CA",
}


def _version_tuple(value):
    parts = []
    for part in str(value or "").split("."):
        try:
            parts.append(int("".join(ch for ch in part if ch.isdigit()) or "0"))
        except Exception:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _clean(value):
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _ident_from_options(opts, use_icao=False):
    number = "".join(ch for ch in str(opts.get("flightNumber") or "") if ch.isdigit())
    airline = _clean(opts.get("airline") or "")
    if airline and number:
        if use_icao and len(airline) == 2:
            airline = iata_to_icao_prefix(airline) or airline
        return airline + number
    return _clean(opts.get("callsign") or "")


def _flight_number_from_options(opts):
    return "".join(ch for ch in str(opts.get("flightNumber") or "") if ch.isdigit())


def _airline_icao_from_options(opts):
    airline = _clean(opts.get("airline") or "")
    if len(airline) == 2:
        return iata_to_icao_prefix(airline) or airline
    return airline


def _route_from_options(opts):
    origin = _clean(opts.get("origin") or "")[:3]
    destination = _clean(opts.get("destination") or "")[:3]
    if origin and destination:
        return f"{origin}-{destination}"
    return ""


def _truthy(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _service_day_start_local(now_local=None):
    now_local = now_local or datetime.now().astimezone()
    six = now_local.replace(hour=6, minute=0, second=0, microsecond=0)
    if now_local < six:
        six = six - timedelta(days=1)
    return six


def _service_day_id(now_local=None):
    return _service_day_start_local(now_local).strftime("%Y-%m-%d")


def _terminal_key(iata_ident, icao_ident, route, repeat_daily=False):
    service_day = _service_day_id() if repeat_daily else ""
    return "|".join([iata_ident or "", icao_ident or "", route or "", service_day])


def _today_6am_local():
    now = datetime.now().astimezone()
    return now.replace(hour=6, minute=0, second=0, microsecond=0)


def _next_6am_local():
    now = datetime.now().astimezone()
    six = _today_6am_local()
    if now >= six:
        six = six + timedelta(days=1)
    return six


def _utc(dt):
    return dt.astimezone(timezone.utc) if dt else None


def _is_landed(flight):
    return bool(flight and (flight.get("datetime_landed") or flight.get("flight_ended") is True))


def _is_cancelled(flight):
    if not flight:
        return False
    text_parts = []
    for key in (
        "status", "flight_status", "flight_state", "state", "status_text",
        "status_detail", "status_message", "remarks", "message",
        "cancelled", "canceled",
    ):
        value = flight.get(key)
        if isinstance(value, dict):
            value = " ".join(str(v) for v in value.values())
        if value is not None:
            text_parts.append(str(value))
    text = " ".join(text_parts).lower()
    return any(word in text for word in ("cancelled", "canceled", "cncl"))


def _terminal_cached(key):
    cached = _TERMINAL_CACHE.get(key)
    if not cached:
        return None
    if cached["expires"] <= datetime.now(timezone.utc):
        _TERMINAL_CACHE.pop(key, None)
        return None
    return cached["flight"]


def _cache_terminal(key, flight):
    if _is_landed(flight) or _is_cancelled(flight):
        _TERMINAL_CACHE[key] = {
            "flight": flight,
            "expires": datetime.now(timezone.utc) + timedelta(seconds=_TERMINAL_CACHE_SECONDS),
        }


def _parse_time(value):
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _fmt_time(value):
    dt = _parse_time(value)
    if not dt:
        return "--:--"
    return format_time(dt.astimezone())


def _airport_code(value):
    if isinstance(value, str) and value:
        return value[:3].upper()
    if not isinstance(value, dict):
        return "---"
    return value.get("code_iata") or value.get("code_lid") or value.get("code") or "---"


def _flight_number(flight):
    ident = flight.get("flight") or flight.get("ident_iata") or flight.get("ident") or flight.get("callsign") or ""
    if ident:
        return ident.replace(" ", "")[:8]
    op = flight.get("operator_iata") or flight.get("operator") or ""
    num = str(flight.get("flight_number") or "")
    return (op + num)[:8]


def _aircraft_type(flight):
    for key in ("type", "aircraft_type", "aircraft_code", "model_code", "model"):
        value = flight.get(key)
        if isinstance(value, dict):
            value = value.get("code") or value.get("icao") or value.get("iata") or value.get("text")
        text = str(value or "").strip().upper()
        if text:
            return text[:12]
    aircraft = flight.get("aircraft")
    if isinstance(aircraft, dict):
        for key in ("type", "code", "model", "icao"):
            text = str(aircraft.get(key) or "").strip().upper()
            if text:
                return text[:12]
    return "AIRCRAFT"


def _delay_minutes(flight):
    return 0


def _status(flight):
    if _is_cancelled(flight):
        return "CNCL", (238, 80, 80)
    if flight.get("_summary"):
        if flight.get("datetime_landed"):
            return "LAND", (95, 230, 135)
        if _airborne(flight):
            return "ENRT", (100, 190, 255)
        return "SCHED", (255, 220, 90)
    try:
        alt = int(float(flight.get("alt") or 0))
    except Exception:
        alt = 0
    try:
        speed = int(float(flight.get("gspeed") or 0))
    except Exception:
        speed = 0
    source = str(flight.get("source") or "").upper()
    if alt > 1000:
        return "ENRT", (100, 190, 255)
    if speed > 40:
        return "TAXI", (255, 220, 90)
    if source == "ESTIMATED":
        return "EST", (255, 220, 90)
    return "LIVE", (95, 230, 135)


def _airborne(flight):
    takeoff = _parse_time(flight.get("datetime_takeoff"))
    if takeoff and takeoff <= datetime.now(timezone.utc):
        return True
    try:
        alt = int(float(flight.get("alt") or 0))
    except Exception:
        alt = 0
    try:
        speed = int(float(flight.get("gspeed") or 0))
    except Exception:
        speed = 0
    return alt > 1000 or speed > 120


def _departure_time(flight):
    for key in (
        "datetime_scheduled_departure", "scheduled_departure", "departure_scheduled",
        "datetime_real_departure", "real_departure", "departure_time",
        "datetime_takeoff", "first_seen",
    ):
        if flight.get(key):
            return flight.get(key)
    return None


def _takeoff_time(flight):
    for key in ("datetime_takeoff", "takeoff_time", "first_seen"):
        if flight.get(key):
            return flight.get(key)
    return _departure_time(flight)


def _event_time(flight):
    if _is_cancelled(flight):
        return "CANCELLED"
    if _is_landed(flight):
        return "LANDED " + _fmt_time(flight.get("datetime_landed"))
    if flight.get("_summary"):
        if _airborne(flight):
            return "ETA " + _fmt_time(flight.get("eta")) if flight.get("eta") else "TAKEOFF: " + _fmt_time(_takeoff_time(flight))
        departure = _departure_time(flight)
        return "DEP " + _fmt_time(departure) if departure else "DEP --:--"
    if flight.get("eta") and _airborne(flight):
        return "ETA " + _fmt_time(flight.get("eta"))
    if _airborne(flight):
        return "TAKEOFF: " + _fmt_time(_takeoff_time(flight))
    departure = _departure_time(flight)
    if departure:
        return "DEP " + _fmt_time(departure)
    try:
        speed = int(float(flight.get("gspeed") or 0))
    except Exception:
        speed = 0
    return format_speed_knots(speed) if speed else "LIVE"


def _gate_line(flight):
    if flight.get("_summary"):
        seconds = flight.get("flight_time")
        try:
            mins = int(seconds or 0) // 60
        except Exception:
            mins = 0
        return f"{mins // 60}H{mins % 60:02d}" if mins else ""
    try:
        alt = int(float(flight.get("alt") or 0))
    except Exception:
        alt = 0
    return f"{alt // 100}FL" if alt >= 10000 else ""


def _alt_speed_line(flight):
    try:
        alt = int(float(flight.get("alt") or 0))
    except Exception:
        alt = 0
    try:
        speed = int(float(flight.get("gspeed") or 0))
    except Exception:
        speed = 0
    parts = []
    if alt >= 10000:
        parts.append(f"{alt // 100}FL")
    elif alt > 0:
        parts.append(f"{alt}FT")
    if speed > 0:
        parts.append(format_speed_knots(speed))
    return " ".join(parts)


def _alt_line(flight):
    try:
        alt = int(float(flight.get("alt") or 0))
    except Exception:
        alt = 0
    if alt >= 10000:
        return f"ALT {alt // 100}FL"
    if alt > 0:
        return f"ALT {alt}FT"
    return "ALT ---"


def _speed_line(flight):
    try:
        speed = int(float(flight.get("gspeed") or 0))
    except Exception:
        speed = 0
    return f"SPD {format_speed_knots(speed)}" if speed > 0 else "SPD ---"


def _flight_lat_lon(flight):
    lat = flight.get("lat") or flight.get("latitude")
    lon = flight.get("lon") or flight.get("lng") or flight.get("longitude")
    try:
        lat = float(lat)
        lon = float(lon)
    except Exception:
        return None, None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None
    return lat, lon


def _reverse_geocode(lat, lon):
    detail = _reverse_geocode_detail(lat, lon)
    place = detail.get("place", "")
    region = detail.get("region", "")
    if place and region and place.upper() != region.upper():
        return f"{place} {region}"
    return place or region


def _reverse_geocode_detail(lat, lon):
    now = datetime.now(timezone.utc)
    key = f"{lat:.2f},{lon:.2f}"
    cached = _GEO_DETAIL_CACHE.get(key)
    if cached and cached["expires"] > now:
        return cached["detail"]
    url = (
        "https://nominatim.openstreetmap.org/reverse?"
        + urllib.parse.urlencode({
            "format": "jsonv2",
            "lat": f"{lat:.5f}",
            "lon": f"{lon:.5f}",
            "zoom": "10",
            "addressdetails": "1",
        })
    )
    detail = {"place": "", "region": ""}
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1"})
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        address = data.get("address") or {}
        place = (
            address.get("city") or address.get("town") or address.get("village")
            or address.get("hamlet") or address.get("county") or address.get("state")
            or address.get("country")
        )
        region = address.get("state_code") or address.get("state")
        detail = {"place": place or "", "region": region or ""}
    except Exception:
        detail = {"place": "", "region": ""}
    _GEO_DETAIL_CACHE[key] = {
        "expires": now + timedelta(seconds=_GEO_CACHE_SECONDS),
        "detail": detail,
    }
    _GEO_CACHE[key] = {
        "expires": now + timedelta(seconds=_GEO_CACHE_SECONDS),
        "label": (
            f"{detail['place']} {detail['region']}".strip()
            if detail.get("place") and detail.get("region") and detail["place"].upper() != detail["region"].upper()
            else (detail.get("place") or detail.get("region") or "")
        ),
    }
    return detail


def _over_detail(flight):
    if _is_landed(flight):
        dest = _airport_code(flight.get("dest_iata") or flight.get("dest_icao"))
        label = _AIRPORT_CITY.get(dest, dest)
        parts = label.rsplit(" ", 1)
        return {"region": parts[1] if len(parts) == 2 else "", "place": parts[0] if parts else label}
    preset = str(flight.get("_over") or "").strip()
    if preset:
        parts = preset.rsplit(" ", 1)
        return {"region": parts[1] if len(parts) == 2 and len(parts[1]) <= 3 else "", "place": preset}
    lat, lon = _flight_lat_lon(flight)
    if lat is not None:
        detail = _reverse_geocode_detail(lat, lon)
        if detail.get("place") or detail.get("region"):
            return detail
    dest = _airport_code(flight.get("dest_iata") or flight.get("dest_icao"))
    label = _AIRPORT_CITY.get(dest, dest) if dest != "---" else "IN FLIGHT"
    parts = label.rsplit(" ", 1)
    return {"region": parts[1] if len(parts) == 2 else "", "place": parts[0] if parts else label}


def _over_line(flight):
    if _is_cancelled(flight):
        return "NO FLIGHT"
    if _is_landed(flight):
        dest = _airport_code(flight.get("dest_iata") or flight.get("dest_icao"))
        return _AIRPORT_CITY.get(dest, dest)
    preset = str(flight.get("_over") or "").strip()
    if preset:
        return preset.upper()
    lat, lon = _flight_lat_lon(flight)
    if lat is None:
        dest = _airport_code(flight.get("dest_iata") or flight.get("dest_icao"))
        return _AIRPORT_CITY.get(dest, dest) if dest != "---" else "IN FLIGHT"
    label = _reverse_geocode(lat, lon)
    return (label or f"{lat:.1f},{lon:.1f}").upper()


def _position_heading(flight):
    if _is_cancelled(flight):
        return "CANCELLED"
    if _is_landed(flight):
        return "LANDED AT"
    lat, lon = _flight_lat_lon(flight)
    return "FLYING OVER" if lat is not None else "ENROUTE TO"


def _airline_iata(flight):
    ident = str(flight.get("flight") or "").strip().upper()
    if len(ident) >= 2:
        return ident[:2]
    airline = lookup_airline(flight.get("operating_as") or flight.get("callsign") or "")
    if airline:
        return airline[1]
    painted = str(flight.get("painted_as") or flight.get("operating_as") or "").upper()
    reverse = {
        "AAL": "AA", "UAL": "UA", "DAL": "DL", "SWA": "WN", "ASA": "AS",
        "JBU": "B6", "FFT": "F9", "NKS": "NK", "HAL": "HA", "BAW": "BA",
        "AFR": "AF", "DLH": "LH", "UAE": "EK", "ACA": "AC",
    }
    return reverse.get(painted)


def _draw_southwest_heart(draw, x, y):
    # 16x16 pixel version of the Southwest heart icon.
    gray = (190, 194, 198)
    red = (222, 20, 35)
    blue = (25, 78, 170)
    yellow = (255, 184, 32)
    white = (245, 245, 245)

    outline = [(4, 0), (6, 0), (8, 2), (10, 0), (12, 0), (14, 2), (15, 5),
               (15, 7), (14, 10), (8, 16), (2, 10), (0, 7), (0, 4), (2, 1)]
    draw.polygon([(x + px, y + py) for px, py in outline], fill=gray)
    inner = [(4, 2), (6, 2), (8, 4), (10, 2), (12, 2), (13, 3), (14, 5),
             (14, 7), (13, 9), (8, 14), (3, 9), (1, 7), (1, 5), (2, 3)]
    draw.polygon([(x + px, y + py) for px, py in inner], fill=white)
    draw.polygon([(x + 2, y + 5), (x + 7, y + 9), (x + 12, y + 13),
                  (x + 8, y + 14), (x + 3, y + 9), (x + 1, y + 7)],
                 fill=blue)
    draw.polygon([(x + 3, y + 3), (x + 6, y + 3), (x + 8, y + 5),
                  (x + 13, y + 9), (x + 12, y + 13), (x + 2, y + 5)],
                 fill=red)
    draw.polygon([(x + 9, y + 4), (x + 10, y + 2), (x + 12, y + 3),
                  (x + 14, y + 5), (x + 14, y + 7), (x + 13, y + 9)],
                 fill=yellow)
    draw.line((x + 2, y + 5, x + 12, y + 13), fill=white)
    draw.line((x + 8, y + 4, x + 13, y + 9), fill=white)
    draw.line((x + 8, y + 14, x + 12, y + 13), fill=white)


def _draw_delta_widget(draw, x, y):
    # Compact 12x12 Delta widget mark for the 64x32 matrix.
    red = (224, 25, 45)
    dark_red = (142, 18, 34)
    shadow = (86, 10, 22)

    draw.polygon(
        [(x + 6, y), (x + 12, y + 12), (x, y + 12)],
        fill=red,
    )
    draw.polygon(
        [(x + 6, y + 5), (x + 12, y + 12), (x + 8, y + 12)],
        fill=dark_red,
    )
    draw.polygon(
        [(x + 6, y + 5), (x + 4, y + 12), (x, y + 12)],
        fill=shadow,
    )
    draw.polygon(
        [(x + 6, y + 5), (x + 8, y + 12), (x + 4, y + 12)],
        fill=(190, 20, 40),
    )


def _fit_text(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1]
    return text


_PIXEL_FONT_5X7 = {
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    "-": ("00000", "00000", "00000", "11110", "00000", "00000", "00000"),
    ">": ("10000", "01000", "00100", "00010", "00100", "01000", "10000"),
    ":": ("00000", "00100", "00100", "00000", "00100", "00100", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "00100", "00100"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "11100"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10011", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
}


def _pixel_text_width(text, spacing=1):
    text = str(text or "").upper()
    return 0 if not text else len(text) * 5 + (len(text) - 1) * spacing


def _fit_pixel_text(text, max_width, spacing=1):
    text = str(text or "").upper()
    while text and _pixel_text_width(text, spacing) > max_width:
        text = text[:-1]
    return text


def _draw_pixel_text(draw, x, y, text, fill, spacing=1):
    cursor = x
    for ch in str(text or "").upper():
        glyph = _PIXEL_FONT_5X7.get(ch, _PIXEL_FONT_5X7[" "])
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit == "1":
                    draw.point((cursor + col, y + row), fill=fill)
        cursor += 5 + spacing


_MATRIX_FONT_4X6 = {
    " ": ("0000", "0000", "0000", "0000", "0000", "0000"),
    "-": ("0000", "0000", "1110", "0000", "0000", "0000"),
    ">": ("1000", "0100", "0010", "0100", "1000", "0000"),
    ":": ("0000", "0100", "0000", "0100", "0000", "0000"),
    ".": ("0000", "0000", "0000", "0000", "0000", "0100"),
    "0": ("1110", "1010", "1010", "1010", "1010", "1110"),
    "1": ("0100", "1100", "0100", "0100", "0100", "1110"),
    "2": ("1110", "0010", "0010", "1110", "1000", "1110"),
    "3": ("1110", "0010", "0110", "0010", "0010", "1110"),
    "4": ("1010", "1010", "1110", "0010", "0010", "0010"),
    "5": ("1110", "1000", "1110", "0010", "0010", "1110"),
    "6": ("1110", "1000", "1110", "1010", "1010", "1110"),
    "7": ("1110", "0010", "0010", "0100", "0100", "0100"),
    "8": ("1110", "1010", "1110", "1010", "1010", "1110"),
    "9": ("1110", "1010", "1010", "1110", "0010", "1110"),
    "A": ("1110", "1010", "1010", "1110", "1010", "1010"),
    "B": ("1100", "1010", "1100", "1010", "1010", "1100"),
    "C": ("1110", "1000", "1000", "1000", "1000", "1110"),
    "D": ("1100", "1010", "1010", "1010", "1010", "1100"),
    "E": ("1110", "1000", "1110", "1000", "1000", "1110"),
    "F": ("1110", "1000", "1110", "1000", "1000", "1000"),
    "G": ("1110", "1000", "1010", "1010", "1010", "1110"),
    "H": ("1010", "1010", "1110", "1010", "1010", "1010"),
    "I": ("1110", "0100", "0100", "0100", "0100", "1110"),
    "J": ("0110", "0010", "0010", "0010", "1010", "1110"),
    "K": ("1010", "1010", "1100", "1010", "1010", "1010"),
    "L": ("1000", "1000", "1000", "1000", "1000", "1110"),
    "M": ("1010", "1110", "1110", "1010", "1010", "1010"),
    "N": ("1010", "1110", "1110", "1110", "1010", "1010"),
    "O": ("1110", "1010", "1010", "1010", "1010", "1110"),
    "P": ("1110", "1010", "1010", "1110", "1000", "1000"),
    "Q": ("1110", "1010", "1010", "1010", "1110", "0010"),
    "R": ("1110", "1010", "1010", "1100", "1010", "1010"),
    "S": ("1110", "1000", "1110", "0010", "0010", "1110"),
    "T": ("1110", "0100", "0100", "0100", "0100", "0100"),
    "U": ("1010", "1010", "1010", "1010", "1010", "1110"),
    "V": ("1010", "1010", "1010", "1010", "1010", "0100"),
    "W": ("1010", "1010", "1010", "1110", "1110", "1010"),
    "X": ("1010", "1010", "0100", "0100", "1010", "1010"),
    "Y": ("1010", "1010", "1110", "0100", "0100", "0100"),
    "Z": ("1110", "0010", "0100", "0100", "1000", "1110"),
}


def _matrix_text_width(text, spacing=1):
    text = str(text or "").upper()
    return 0 if not text else len(text) * 4 + (len(text) - 1) * spacing


def _fit_matrix_text(text, max_width, spacing=1):
    text = str(text or "").upper()
    while text and _matrix_text_width(text, spacing) > max_width:
        text = text[:-1]
    return text


def _draw_matrix_text(draw, x, y, text, fill, spacing=1):
    cursor = x
    for ch in str(text or "").upper():
        glyph = _MATRIX_FONT_4X6.get(ch, _MATRIX_FONT_4X6[" "])
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit == "1":
                    draw.point((cursor + col, y + row), fill=fill)
        cursor += 4 + spacing


def _draw_tight_text(image, text, x, y, fill, font, spacing=-1):
    from PIL import Image, ImageDraw
    cursor = x
    for ch in str(text or ""):
        mask = Image.new("1", image.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.text((cursor, y), ch, fill=1, font=font)
        image.paste(Image.new("RGB", image.size, fill), (0, 0), mask)
        cursor += draw.textbbox((0, 0), ch, font=font)[2] + spacing
    return cursor


def _fetch(endpoint, params, api_key):
    now = datetime.now(timezone.utc)
    key = endpoint + "?" + urllib.parse.urlencode(sorted(params.items()))
    cached = _CACHE.get(key)
    if cached and cached["expires"] > now:
        return cached["data"]
    url = f"{_API_ROOT}{endpoint}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Pixora/0.1",
        "Authorization": "Bearer " + api_key,
        "Accept": "application/json",
        "Accept-Version": "v1",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    _CACHE[key] = {"data": data, "expires": now + timedelta(seconds=_CACHE_SECONDS)}
    return data


def _fetch_uncached(endpoint, params, api_key):
    url = f"{_API_ROOT}{endpoint}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Pixora/0.1",
        "Authorization": "Bearer " + api_key,
        "Accept": "application/json",
        "Accept-Version": "v1",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _data_rows(data):
    if isinstance(data, dict):
        rows = data.get("data")
        return rows if isinstance(rows, list) else []
    return data if isinstance(data, list) else []


def _pick_flight(flights):
    if not flights:
        return None
    now = datetime.now(timezone.utc)

    def score(f):
        try:
            alt = int(float(f.get("alt") or 0))
        except Exception:
            alt = 0
        if alt > 0:
            return 0
        eta = _parse_time(f.get("eta"))
        if eta:
            delta = abs((eta - now).total_seconds())
            return 1 + delta / 86400
        return 999

    return sorted(flights, key=score)[0]


def _pick_summary(rows, service_start=None):
    if not rows:
        return None
    if service_start:
        filtered = []
        for row in rows:
            dt = (
                _flight_departure_dt(row)
                or _parse_time(row.get("first_seen"))
                or _parse_time(row.get("datetime_takeoff"))
                or _parse_time(row.get("datetime_landed"))
            )
            if dt and dt >= service_start:
                filtered.append(row)
        if filtered:
            rows = filtered
    now = datetime.now(timezone.utc)

    def score(row):
        if row.get("datetime_takeoff") and not row.get("datetime_landed"):
            return 0
        for key in ("first_seen", "datetime_takeoff", "datetime_landed"):
            dt = _parse_time(row.get(key))
            if dt:
                return 1 + abs((dt - now).total_seconds()) / 86400
        return 999

    picked = sorted(rows, key=score)[0]
    picked["_summary"] = True
    return picked


def _flight_departure_dt(flight):
    return _parse_time(_departure_time(flight or {}))


def _summary_params(now, iata_ident, icao_ident, route, repeat_daily=False):
    if repeat_daily:
        service_start = _utc(_service_day_start_local(now.astimezone()))
        date_from = service_start
        date_to = service_start + timedelta(hours=36)
    else:
        date_from = now - timedelta(hours=18)
        date_to = now + timedelta(hours=36)
    params = {
        "flight_datetime_from": date_from.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "flight_datetime_to": date_to.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit": "10",
    }
    if iata_ident:
        params["flights"] = iata_ident
    if icao_ident:
        params["callsigns"] = icao_ident
    if route:
        params["routes"] = route
    return params


def _live_params(iata_ident, icao_ident, airline_icao, route):
    if iata_ident:
        return {"flights": iata_ident, "limit": "5"}
    if icao_ident:
        return {"callsigns": icao_ident, "limit": "5"}
    if route and airline_icao:
        return {"routes": route, "operating_as": airline_icao, "limit": "10"}
    return None


def _poll_state_key(terminal_key):
    local_day = _service_day_id()
    return f"{terminal_key}|{local_day}"


def _get_poll_state(key):
    state = _FLIGHT_POLL_STATE.get(key)
    if state:
        return state
    now_local = datetime.now().astimezone()
    six = _today_6am_local()
    state = {
        "flight": None,
        "next_poll": _utc(six if now_local < six else now_local),
        "last_error": None,
        "landed_seen": False,
        "landed_confirmed": False,
        "cancelled": False,
    }
    _FLIGHT_POLL_STATE[key] = state
    return state


def _schedule_next_poll(state, flight, now):
    next_day = _utc(_next_6am_local())
    if not flight:
        state["next_poll"] = now + timedelta(hours=1)
        return

    if _is_cancelled(flight):
        state["cancelled"] = True
        state["next_poll"] = next_day
        return

    if _is_landed(flight):
        if state.get("landed_seen"):
            state["landed_confirmed"] = True
            state["next_poll"] = next_day
        else:
            state["landed_seen"] = True
            state["next_poll"] = now + timedelta(minutes=15)
        return

    state["landed_seen"] = False
    state["landed_confirmed"] = False
    departure = _flight_departure_dt(flight)
    if departure and now < departure - timedelta(minutes=10):
        state["next_poll"] = departure - timedelta(minutes=10)
    elif not _airborne(flight):
        state["next_poll"] = now + timedelta(minutes=10)
    else:
        eta = _parse_time(flight.get("eta"))
        if eta and eta > now and eta - now <= timedelta(minutes=10):
            state["next_poll"] = now + timedelta(minutes=3)
        else:
            state["next_poll"] = now + timedelta(minutes=15)


def _load_summary(now, iata_ident, icao_ident, route, api_key, repeat_daily=False):
    service_start = _utc(_service_day_start_local(now.astimezone())) if repeat_daily else None
    data = _fetch_uncached("/flight-summary/full", _summary_params(now, iata_ident, icao_ident, route, repeat_daily), api_key)
    return _pick_summary(_data_rows(data), service_start)


def _load_live(iata_ident, icao_ident, airline_icao, route, api_key):
    params = _live_params(iata_ident, icao_ident, airline_icao, route)
    if not params:
        return None
    data = _fetch_uncached("/live/flight-positions/full", params, api_key)
    return _pick_flight(_data_rows(data))


def _merge_summary_and_live(summary, live):
    if not summary:
        return live
    if not live:
        return summary
    merged = dict(summary)
    for key, value in live.items():
        if value not in (None, "", [], {}):
            merged[key] = value
    for key, value in summary.items():
        if key.startswith("datetime_") or key in (
            "orig_iata", "orig_icao", "dest_iata", "dest_icao", "eta",
            "scheduled_departure", "datetime_scheduled_departure",
            "flight", "ident_iata", "flight_number",
        ):
            if merged.get(key) in (None, "", [], {}):
                merged[key] = value
    merged["_summary"] = bool(summary.get("_summary"))
    return merged


def _load_flight(opts):
    if _DISABLE_POLLING_FOR_TEST:
        return {
            "flight": "WN3416",
            "callsign": "SWA3416",
            "operating_as": "SWA",
            "painted_as": "SWA",
            "orig_iata": "MHT",
            "dest_iata": "MCO",
            "scheduled_departure": "2026-05-08T20:55:00Z",
            "eta": "2026-05-08T22:25:00Z",
            "alt": 30000,
            "gspeed": 430,
            "type": "B38M",
            "lat": 38.9072,
            "lon": -77.0369,
            "_over": "Washington DC",
            "_pixora_test": True,
        }, None
    api_key = str(opts.get("apiKey") or "").strip()
    if not api_key:
        return None, "SET API"
    ident = _ident_from_options(opts, use_icao=False)
    if not ident:
        return None, "SET FLT"
    last_error = None
    flight_no = _flight_number_from_options(opts)
    airline_icao = _airline_icao_from_options(opts)
    route = _route_from_options(opts)
    iata_ident = ident
    icao_ident = _ident_from_options(opts, use_icao=True)
    repeat_daily = _truthy(opts.get("repeatDaily"))
    terminal_key = _terminal_key(iata_ident, icao_ident, route, repeat_daily)
    force_refresh = _truthy(opts.get("_forceRefresh"))
    if force_refresh:
        _TERMINAL_CACHE.pop(terminal_key, None)
        _FLIGHT_POLL_STATE.pop(_poll_state_key(terminal_key), None)
    terminal_flight = _terminal_cached(terminal_key)
    if terminal_flight and not force_refresh:
        return terminal_flight, None
    now = datetime.now(timezone.utc)
    poll_key = _poll_state_key(terminal_key)
    poll_state = _get_poll_state(poll_key)
    cached_flight = poll_state.get("flight")
    next_poll = poll_state.get("next_poll")
    cached_error = poll_state.get("last_error")
    if poll_state.get("cancelled") and cached_flight and not force_refresh:
        return cached_flight, None
    if next_poll and now < next_poll and not force_refresh:
        if cached_flight:
            return cached_flight, None
        if cached_error:
            return None, cached_error
        return None, "WAIT 6A"

    try:
        if cached_flight and _airborne(cached_flight) and not _is_landed(cached_flight):
            live = _load_live(iata_ident, icao_ident, airline_icao, route, api_key)
            flight = _merge_summary_and_live(cached_flight, live)
        else:
            flight = _load_summary(now, iata_ident, icao_ident, route, api_key, repeat_daily)
            if flight and _airborne(flight) and not _is_landed(flight):
                try:
                    live = _load_live(iata_ident, icao_ident, airline_icao, route, api_key)
                    flight = _merge_summary_and_live(flight, live)
                except Exception:
                    pass
        if flight:
            poll_state["flight"] = flight
            poll_state["last_error"] = None
            _schedule_next_poll(poll_state, flight, now)
            _cache_terminal(terminal_key, flight)
            return flight, None
        last_error = "NO LIVE"
        poll_state["last_error"] = last_error
        _schedule_next_poll(poll_state, cached_flight, now)
        if cached_flight:
            return cached_flight, None
    except urllib.error.HTTPError as err:
        if err.code in (401, 403):
            return None, "BAD API"
        _schedule_next_poll(poll_state, cached_flight, now)
        if cached_flight:
            return cached_flight, None
        last_error = "NO LIVE"
        poll_state["last_error"] = last_error
    except Exception:
        _schedule_next_poll(poll_state, cached_flight, now)
        if cached_flight:
            return cached_flight, None
        last_error = "API ERR"
        poll_state["last_error"] = last_error
    return None, last_error or "NO LIVE"


def _display_error(error, options):
    if error == "NO LIVE":
        ident = _ident_from_options(options or {}, use_icao=False) or _flight_number_from_options(options or {}) or "flight"
        return f"No live tracking data for {ident}"
    return error


def _render_error_image(message, color):
    from PIL import Image, ImageDraw

    width = 128 if isinstance(message, dict) and message.get("_wide") else 64
    if isinstance(message, dict):
        message = message.get("text", "")
    image = Image.new("RGB", (width, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    words = str(message or "").split()
    lines = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), candidate, font=FONT_7)
        if current and bbox[2] - bbox[0] > width - 2:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if not lines:
        lines = [str(message or "")]
    if len(lines) > 4:
        lines = lines[:3] + [" ".join(lines[3:])]
    line_h = 8
    start_y = (32 - len(lines) * line_h) // 2 - 3
    for index, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=FONT_7)
        x = max(0, (width - (bbox[2] - bbox[0])) // 2)
        draw_sharp_text(image, (x, start_y + index * line_h), line, color, FONT_7)
    return image


def _draw_airline_mark(image, draw, flight, logo_left, logo_top, fallback_y=0):
    iata = _airline_iata(flight)
    if iata == "WN":
        _draw_southwest_heart(draw, logo_left, logo_top)
        return
    if iata == "DL":
        _draw_delta_widget(draw, logo_left, logo_top + 1)
        return
    logo = fetch_airline_logo(iata) if iata else None
    if logo:
        image.paste(logo, (logo_left, logo_top), logo)
    elif iata:
        airline = _fit_pixel_text(iata[:2], 12)
        _draw_pixel_text(draw, image.width - 1 - _pixel_text_width(airline), fallback_y, airline, (100, 190, 255))


def _layout_for_flight(flight, width=64):
    if width == 128:
        return {
            "logo_left": 0,
            "logo_top": 0,
            "text_left": 20,
            "ident_max": 105,
            "route_max": 105,
        }
    return {
        "logo_left": 0,
        "logo_top": 0,
        "text_left": 18,
        "ident_max": 45,
        "route_max": 45,
    }


def _render_flight_panel(flight, width=64):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, 32), (0, 5, 18))
    draw = ImageDraw.Draw(image)
    layout = _layout_for_flight(flight, width)
    ident = _fit_pixel_text(_flight_number(flight), layout["ident_max"])
    aircraft = _fit_pixel_text(_aircraft_type(flight), layout["ident_max"])
    route = f"{_airport_code(flight.get('orig_iata') or flight.get('orig_icao'))}>{_airport_code(flight.get('dest_iata') or flight.get('dest_icao'))}"
    bottom = _event_time(flight)

    _draw_airline_mark(image, draw, flight, layout["logo_left"], layout["logo_top"])
    _draw_pixel_text(draw, layout["text_left"], 0, ident, (235, 245, 255))
    if width == 128:
        bottom_w = _matrix_text_width(bottom, spacing=0)
        _draw_matrix_text(draw, layout["text_left"], 9, _fit_matrix_text(aircraft, 46, spacing=0), (100, 190, 255), spacing=0)
        _draw_matrix_text(draw, 74, 9, _fit_matrix_text(route, 52, spacing=0), (100, 190, 255), spacing=0)
        _draw_matrix_text(draw, max(0, (width - min(bottom_w, width - 2)) // 2), 25, _fit_matrix_text(bottom, width - 2, spacing=0), (255, 220, 90), spacing=0)
    else:
        _draw_matrix_text(draw, layout["text_left"], 9, _fit_matrix_text(aircraft, layout["ident_max"], spacing=0), (100, 190, 255), spacing=0)
        _draw_matrix_text(draw, layout["text_left"], 17, _fit_matrix_text(route, layout["route_max"], spacing=0), (100, 190, 255), spacing=0)
        _draw_matrix_text(draw, 0, 25, _fit_matrix_text(bottom, 63, spacing=0), (255, 220, 90), spacing=0)
    return image


def _render_status_panel(flight, width=64, compact=False):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, 32), (0, 5, 18))
    draw = ImageDraw.Draw(image)
    status, status_color = _status(flight)
    ident = _fit_pixel_text(_flight_number(flight), width - 1)
    heading = _fit_matrix_text(_position_heading(flight), width - 1, spacing=0)
    over = _fit_matrix_text(_over_line(flight), width - 1, spacing=0)
    detail_text = "GROUND" if _is_landed(flight) else (_alt_speed_line(flight) or status)
    details = _fit_matrix_text(detail_text, width - 1, spacing=0)
    if compact:
        _draw_matrix_text(draw, 0, 1, heading, status_color, spacing=0)
        where = _over_detail(flight)
        place = _fit_matrix_text(where.get("place") or over, width - 1, spacing=0)
        region = _fit_matrix_text(where.get("region") or "", width - 1, spacing=0)
        _draw_matrix_text(draw, 0, 9, place, (255, 220, 90), spacing=0)
        _draw_matrix_text(draw, 0, 17, region, (255, 220, 90), spacing=0)
        _draw_matrix_text(draw, 0, 25, details, (100, 190, 255), spacing=0)
    else:
        _draw_pixel_text(draw, 0, 0, ident, (235, 245, 255))
        _draw_matrix_text(draw, 0, 9, heading, status_color, spacing=0)
        _draw_matrix_text(draw, 0, 17, over, (255, 220, 90), spacing=0)
        _draw_matrix_text(draw, 0, 25, details, (100, 190, 255), spacing=0)
    return image


def _compose_slide(left, right, offset):
    from PIL import Image

    width = left.width
    frame = Image.new("RGB", (width, 32), (0, 5, 18))
    frame.paste(left, (-offset, 0))
    frame.paste(right, (width - offset, 0))
    return frame


def _save_static_webp(image):
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _save_slide_animation(first, second):
    width = first.width
    step = 16 if width == 128 else 8
    slide_offsets = list(range(step, width + 1, step))
    frames = [_compose_slide(first, second, offset) for offset in slide_offsets] + [second]
    frame_ms = 120
    out = BytesIO()
    frames[0].save(
        out, "WEBP", save_all=True,
        append_images=frames[1:],
        duration=frame_ms, loop=1,
        lossless=True, quality=100,
    )
    return out.getvalue()


def _save_locked_two_page_animation(first, second, first_dwell, second_dwell):
    width = first.width
    step = 16 if width == 128 else 8
    slide_offsets = list(range(step, width + 1, step))
    frames = [first] + [_compose_slide(first, second, offset) for offset in slide_offsets] + [second]
    durations = [max(1, int(first_dwell * 1000))]
    durations += [90 for _ in slide_offsets[:-1]]
    durations += [max(1, int(second_dwell * 1000))]
    durations += [1]
    out = BytesIO()
    frames[0].save(
        out, "WEBP", save_all=True,
        append_images=frames[1:],
        duration=durations, loop=1,
        lossless=True, quality=100,
    )
    return out.getvalue()


def _combine_side_by_side(first, second):
    from PIL import Image

    frame = Image.new("RGB", (128, 32), (0, 5, 18))
    left = first.crop((0, 0, 64, 32)) if first.width != 64 else first
    right = second.crop((0, 0, 64, 32)) if second.width != 64 else second
    frame.paste(left, (0, 0))
    frame.paste(right, (64, 0))
    return frame


def _two_page_response(opts, flight, first, second, locked=True):
    dwell = max(4, int(opts.get("_dwell", 30) or 30))
    half_dwell = max(2, dwell // 2)
    second_dwell = max(2, dwell - half_dwell)
    if locked:
        return {
            "body": _save_locked_two_page_animation(first, second, half_dwell, second_dwell),
            "dwell_secs": 1,
            "_stay": False,
        }
    return {
        "body": _save_static_webp(first),
        "dwell_secs": half_dwell,
        "_stay": False,
        "_frames": [
            {
                "body": _save_static_webp(second),
                "dwell_secs": second_dwell,
                "no_replay": False,
                "replay_body": None,
            }
        ],
    }


def render(options=None, dwell_ms=None):
    options = options or {}
    dwell = max(4, int(options.get("_dwell", 30) or 30))
    result = render_webp(options, dwell * 1000)
    return {
        "body": result["body"],
        # The animated WebP already contains the full page1 -> slide -> page2 timing.
        # A long Pixora-Dwell-Secs header makes the firmware replay it before moving on.
        "dwell_secs": result.get("dwell_secs", 1),
        "_stay": False,
    }


def render_webp(options=None, dwell_ms=30000):
    options = options or {}
    width = 128 if options.get("_target") == "matrixportal-s3-128x32" else 64
    flight, error = _load_flight(options)
    if error:
        color = (100, 190, 255) if error.startswith("SET") else (238, 80, 80)
        dwell = max(4, int(dwell_ms / 1000))
        error_dwell = max(2, dwell // 2)
        return {
            "body": _save_static_webp(_render_error_image({"text": _display_error(error, options), "_wide": width == 128}, color)),
            "durationMs": error_dwell * 1000,
            "dwell_secs": error_dwell,
        }

    opts = options
    dwell = max(4, int(dwell_ms / 1000))
    half_dwell = max(2, dwell // 2)
    second_dwell = max(2, dwell - half_dwell)
    if width == 128:
        first = _render_flight_panel(flight, 64)
        second = _render_status_panel(flight, 64, compact=True)
        return {
            "body": _save_static_webp(_combine_side_by_side(first, second)),
            "durationMs": max(1000, int(dwell_ms)),
            "dwell_secs": dwell,
        }

    first = _render_flight_panel(flight, width)
    second = _render_status_panel(flight, width, compact=True)
    return {
        "body": _save_locked_two_page_animation(first, second, half_dwell, second_dwell),
        "durationMs": max(1000, int(dwell_ms)),
        "dwell_secs": 1,
    }
