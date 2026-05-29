from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import urllib.parse
import urllib.request

from card_utils import draw_sharp_text, fetch_airline_logo, format_time, iata_to_icao_prefix, lookup_airline, render_text_webp

CARD_ID = "airport_board"
CARD_NAME = "Airport Board"
CARD_DETAIL = "Low-credit FR24 arrival and departure board"
CARD_OPTIONS = [
    {"key": "airport", "label": "Airport", "type": "text", "default": "BOS", "maxlength": 4},
    {
        "key": "boardType",
        "label": "Board",
        "type": "select",
        "default": "departures",
        "choices": [
            {"value": "departures", "label": "Departures"},
            {"value": "arrivals", "label": "Arrivals"},
            {"value": "both", "label": "Both"},
        ],
    },
    {
        "key": "airline",
        "label": "Airline",
        "type": "select",
        "default": "",
        "choices": [
            {"value": "", "label": "Any Airline"},
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
    {
        "key": "hours",
        "label": "Hours Ahead",
        "type": "select",
        "default": "2",
        "choices": [
            {"value": "1", "label": "1 hour"},
            {"value": "2", "label": "2 hours"},
            {"value": "4", "label": "4 hours"},
        ],
    },
    {
        "key": "maxFlights",
        "label": "Flights Shown",
        "type": "select",
        "default": "3",
        "choices": [
            {"value": "1", "label": "1 flight"},
            {"value": "2", "label": "2 flights"},
            {"value": "3", "label": "3 flights"},
            {"value": "5", "label": "5 flights"},
        ],
    },
    {
        "key": "pollMinutes",
        "label": "Poll Minutes",
        "type": "select",
        "default": "30",
        "choices": [
            {"value": "15", "label": "15 minutes"},
            {"value": "30", "label": "30 minutes"},
            {"value": "60", "label": "60 minutes"},
        ],
    },
    {"key": "apiKey", "label": "Flightradar24 API Token", "type": "text", "default": ""},
]

_API_ROOT = "https://fr24api.flightradar24.com/api"
_CACHE = {}
_RESULT_CACHE = {}


def _clean(value):
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _is_wide(options):
    return (options or {}).get("_target") == "matrixportal-s3-128x32"


def _parse_int(value, default, lo, hi):
    try:
        number = int(value)
    except Exception:
        number = default
    return max(lo, min(hi, number))


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


def _rows(data):
    if isinstance(data, dict):
        rows = data.get("data")
        return rows if isinstance(rows, list) else []
    return data if isinstance(data, list) else []


def _fetch_summary(params, api_key, seconds):
    now = datetime.now(timezone.utc)
    key = urllib.parse.urlencode(sorted(params.items()))
    cached = _CACHE.get(key)
    if cached and cached["expires"] > now:
        return cached["data"]
    url = f"{_API_ROOT}/flight-summary/light?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Pixora/0.1",
        "Authorization": "Bearer " + api_key,
        "Accept": "application/json",
        "Accept-Version": "v1",
    })
    with urllib.request.urlopen(req, timeout=18) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    _CACHE[key] = {"data": data, "expires": now + timedelta(seconds=seconds)}
    return data


def _safe_log(opts, message):
    logger = opts.get("_log") if isinstance(opts, dict) else None
    if callable(logger):
        try:
            logger(message)
        except Exception:
            pass


def _airport_code(row, *keys):
    for key in keys:
        value = row.get(key)
        if isinstance(value, dict):
            value = value.get("code_iata") or value.get("iata") or value.get("code")
        text = _clean(value)[:3]
        if text:
            return text
    return ""


def _airport_icao_code(row, *keys):
    for key in keys:
        value = row.get(key)
        if isinstance(value, dict):
            value = value.get("code_icao") or value.get("icao") or value.get("code")
        text = _clean(value)[:4]
        if text:
            return text
    return ""


def _airport_codes(row, iata_keys, icao_keys):
    iata = _airport_code(row, *iata_keys)
    icao = _airport_icao_code(row, *icao_keys)
    return iata, icao


def _airport_match(code, iata, icao):
    code = _clean(code)[:3]
    if iata == code:
        return True
    return bool(icao and (icao == code or icao == "K" + code))


def _display_airport(iata, icao):
    if iata:
        return iata
    icao = _clean(icao)
    if len(icao) == 4 and icao.startswith("K"):
        return icao[1:]
    return icao[:4] or "---"


def _flight_number(row):
    for key in ("flight", "ident_iata", "ident", "callsign"):
        text = str(row.get(key) or "").replace(" ", "").upper()
        if text:
            return text[:8]
    op = _clean(row.get("operator_iata") or row.get("airline_iata") or row.get("airline"))
    num = "".join(ch for ch in str(row.get("flight_number") or "") if ch.isdigit())
    return (op + num)[:8] if op or num else "FLIGHT"


def _airline_iata(row):
    for key in ("operator_iata", "airline_iata", "painted_as", "operating_as"):
        text = _clean(row.get(key))
        if len(text) == 2:
            return text
    flight = _flight_number(row)
    if len(flight) >= 3 and flight[:2].isalpha():
        return flight[:2]
    return ""


def _airline_icao(row):
    for key in ("operating_as", "painted_as", "operator_icao", "airline_icao"):
        text = _clean(row.get(key))
        if len(text) == 3:
            return text
    callsign = _clean(row.get("callsign"))
    return callsign[:3] if len(callsign) >= 3 and callsign[:3].isalpha() else ""


def _status(row):
    chunks = []
    for key in ("status", "flight_status", "flight_state", "state", "status_text", "remarks"):
        value = row.get(key)
        if isinstance(value, dict):
            value = " ".join(str(v) for v in value.values())
        if value:
            chunks.append(str(value))
    text = " ".join(chunks).lower()
    if any(word in text for word in ("cancel", "cncl")):
        return "CANCEL"
    if any(word in text for word in ("delay", "late")):
        return "DELAY"
    if any(word in text for word in ("board", "gate")):
        return "BOARD"
    if row.get("datetime_landed") or "land" in text:
        return "LANDED"
    if row.get("datetime_takeoff") or "airborne" in text or "enroute" in text:
        return "ENRT"
    return "ON TIME"


def _time_for(row, direction):
    keys = (
        ("datetime_scheduled_departure", "scheduled_departure", "datetime_takeoff", "first_seen")
        if direction == "DEP" else
        ("datetime_scheduled_arrival", "scheduled_arrival", "eta", "datetime_landed")
    )
    for key in keys:
        value = row.get(key)
        if value:
            return value
    return ""


def _sort_time_for(row, direction):
    primary = _parse_time(_time_for(row, direction))
    if primary:
        return primary
    fallback_keys = (
        ("last_seen", "datetime_takeoff", "first_seen")
        if direction == "ARR" else
        ("datetime_takeoff", "first_seen", "last_seen")
    )
    for key in fallback_keys:
        parsed = _parse_time(row.get(key))
        if parsed:
            return parsed
    return datetime.max.replace(tzinfo=timezone.utc)


def _row_from_summary(row, airport, board_type, airline_filter):
    origin, origin_icao = _airport_codes(
        row,
        ("orig_iata", "origin_iata", "origin", "from"),
        ("orig_icao", "origin_icao", "orig_icao_actual"),
    )
    dest, dest_icao = _airport_codes(
        row,
        ("dest_iata", "destination_iata", "destination", "to"),
        ("dest_icao", "destination_icao", "dest_icao_actual"),
    )
    if _airport_match(airport, origin, origin_icao):
        direction = "DEP"
        other = _display_airport(dest, dest_icao)
    elif _airport_match(airport, dest, dest_icao):
        direction = "ARR"
        other = _display_airport(origin, origin_icao)
    else:
        return None
    if other == "---":
        return None
    if board_type == "departures" and direction != "DEP":
        return None
    if board_type == "arrivals" and direction != "ARR":
        return None
    iata = _airline_iata(row)
    icao = _airline_icao(row)
    filter_icao = iata_to_icao_prefix(airline_filter) if airline_filter else ""
    flight = _flight_number(row)
    if airline_filter and iata != airline_filter and not flight.startswith(airline_filter) and icao != filter_icao:
        return None
    airline = lookup_airline(flight) or lookup_airline(iata or flight)
    time_value = _time_for(row, direction)
    time_text = _fmt_time(time_value)
    if time_text == "--:--":
        time_text = "LIVE" if direction == "ARR" else "NOW"
    return {
        "flight": flight,
        "iata": iata or (airline[1] if airline else ""),
        "airline": airline[0] if airline else (iata or flight[:2] or "AIR"),
        "direction": direction,
        "other": other,
        "time": time_text,
        "status": _status(row),
        "sort": _sort_time_for(row, direction),
    }


def _is_current_or_upcoming(row, now):
    sort_time = row.get("sort")
    if not isinstance(sort_time, datetime) or sort_time == datetime.max.replace(tzinfo=timezone.utc):
        return True
    return sort_time >= now - timedelta(minutes=5)


def _board_rows(opts):
    api_key = str(opts.get("apiKey") or "").strip()
    if not api_key:
        return [], "SET API"
    airport = _clean(opts.get("airport") or "BOS")[:3]
    if len(airport) != 3:
        return [], "SET AIRPORT"
    hours = _parse_int(opts.get("hours"), 2, 1, 4)
    limit = _parse_int(opts.get("maxFlights"), 3, 1, 5)
    poll_minutes = _parse_int(opts.get("pollMinutes"), 30, 5, 120)
    board_type = str(opts.get("boardType") or "departures").lower()
    airline_filter = _clean(opts.get("airline"))[:2]
    force_refresh = str(opts.get("_forceRefresh") or "").strip().lower() in ("1", "true", "yes", "on")
    now = datetime.now(timezone.utc)
    result_key = "|".join([airport, board_type, airline_filter, str(hours), str(limit), str(poll_minutes)])
    cached = _RESULT_CACHE.get(result_key)
    if force_refresh:
        _RESULT_CACHE.pop(result_key, None)
        _CACHE.clear()
        _safe_log(opts, f"[airport_board] {opts.get('_device_id', '')} force refresh requested for {airport} {board_type}")
    elif cached and cached["expires"] > now:
        remaining = max(0, int((cached["expires"] - now).total_seconds()))
        _safe_log(opts, f"[airport_board] {opts.get('_device_id', '')} cache hit for {airport} {board_type}; rows={len(cached['rows'])}; next poll in {remaining}s")
        return cached["rows"], cached["error"]

    airport_filter = airport
    if board_type == "departures":
        airport_filter = f"outbound:{airport}"
    elif board_type == "arrivals":
        airport_filter = f"inbound:{airport}"

    query_lookback_minutes = 60 if board_type == "arrivals" else 2
    query_from = (now - timedelta(minutes=query_lookback_minutes)).replace(second=0, microsecond=0)
    params = {
        "flight_datetime_from": query_from.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "flight_datetime_to": (now + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "airports": airport_filter,
        "limit": str(limit if airline_filter else min(5, limit + (1 if board_type == "both" else 0))),
    }
    if airline_filter:
        params["airlines"] = airline_filter
    try:
        _safe_log(opts, f"[airport_board] {opts.get('_device_id', '')} polling FR24 {airport_filter} from={params['flight_datetime_from']} limit={params['limit']} window={hours}h cache={poll_minutes}m")
        data = _fetch_summary(params, api_key, poll_minutes * 60)
    except urllib.error.HTTPError as err:
        error = "BAD API" if err.code in (401, 403) else "FR24 ERR"
        _RESULT_CACHE[result_key] = {
            "rows": [],
            "error": error,
            "expires": now + timedelta(minutes=poll_minutes),
        }
        return [], error
    except Exception:
        _RESULT_CACHE[result_key] = {
            "rows": [],
            "error": "FR24 ERR",
            "expires": now + timedelta(minutes=poll_minutes),
        }
        return [], "FR24 ERR"
    raw_rows = _rows(data)
    rows = []
    seen = set()
    for item in raw_rows:
        row = _row_from_summary(item, airport, board_type, airline_filter)
        if not row:
            continue
        if not _is_current_or_upcoming(row, now):
            continue
        key = (row["flight"], row["direction"], row["other"], row["time"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    rows.sort(key=lambda r: r["sort"])
    rows = rows[:limit]
    _safe_log(opts, f"[airport_board] {opts.get('_device_id', '')} FR24 returned {len(raw_rows)} rows; usable={len(rows)} for {airport} {board_type}")
    _RESULT_CACHE[result_key] = {
        "rows": rows,
        "error": None,
        "expires": now + timedelta(minutes=poll_minutes),
    }
    return rows, None


def _text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), str(text or ""), font=font)
    return bbox[2] - bbox[0]


def _fit(draw, text, font, max_width):
    text = str(text or "")
    while text and _text_width(draw, text, font) > max_width:
        text = text[:-1]
    return text


def _row_text(row):
    return f"{row['time']} {row['flight']} {row['other']} {row['status']}"


def _draw_board(rows, airport, board_type, width, offset=0):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (width, 32), (1, 6, 14))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        font = ImageFont.load_default()

    draw.rectangle((0, 0, width - 1, 8), fill=(12, 24, 36))
    first_direction = rows[0]["direction"] if rows else "DEP"
    title = f"{airport} {'BOARD' if board_type == 'both' else first_direction}"
    draw_sharp_text(image, (2 if width == 128 else 1, -3), title[:16 if width == 128 else 9], (100, 190, 255), font)
    for index, row in enumerate(rows):
        y = 7 + index * 8 - offset
        if y < 1 or y > 29:
            continue
        text = _fit(draw, _row_text(row), font, width - 2)
        draw_sharp_text(image, (1, y), text, (235, 245, 255), font)
    return image


def _render_board(rows, airport, board_type, width):
    if len(rows) <= 3:
        out = BytesIO()
        _draw_board(rows, airport, board_type, width, 0).save(out, "WEBP", lossless=True, quality=100)
        return {"body": out.getvalue(), "dwell_secs": 8, "_stay": False}
    max_offset = max(0, (len(rows) - 3) * 8)
    offsets = [0]
    offsets.extend(range(1, max_offset + 1))
    offsets.append(max_offset)
    frames = [_draw_board(rows, airport, board_type, width, offset) for offset in offsets]
    durations = [4000] + [220] * max_offset + [4000]
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
        "dwell_secs": max(10, round(sum(durations) / 1000)),
        "_stay": False,
    }


def _render_empty(airport, board_type, width):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (width, 32), (1, 6, 14))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        font = ImageFont.load_default()
    draw.rectangle((0, 0, width - 1, 8), fill=(12, 24, 36))
    label = "DEP" if board_type == "departures" else ("ARR" if board_type == "arrivals" else "BOARD")
    draw_sharp_text(image, (2 if width == 128 else 1, -3), f"{airport} {label}"[:16 if width == 128 else 9], (100, 190, 255), font)
    msg = "NO UPCOMING FLIGHTS" if width == 128 else "NO FLIGHTS"
    sub = "FR24 BOARD" if width == 128 else "FR24"
    mw = _text_width(draw, msg, font)
    sw = _text_width(draw, sub, font)
    draw_sharp_text(image, ((width - mw) // 2, 10), msg, (180, 210, 235), font)
    draw_sharp_text(image, ((width - sw) // 2, 21), sub, (130, 150, 165), font)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return {"body": out.getvalue(), "dwell_secs": 5, "_stay": False}


def _save_cycle(frames):
    if not frames:
        return None
    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=4000,
        loop=0,
        lossless=True,
        quality=100,
    )
    return {"body": out.getvalue(), "dwell_secs": max(4, len(frames) * 4), "_stay": False}


def render(options=None):
    opts = options or {}
    wide = _is_wide(opts)
    airport = _clean(opts.get("airport") or "BOS")[:3] or "BOS"
    board_type = str(opts.get("boardType") or "departures").lower()
    rows, error = _board_rows(opts)
    if error:
        return render_text_webp(error, (255, 210, 80))
    if not rows:
        _safe_log(opts, f"[airport_board] {opts.get('_device_id', '')} no upcoming rows for {airport} {board_type}")
        return _render_empty(airport, board_type, 128 if wide else 64)
    return _render_board(rows, airport, board_type, 128 if wide else 64)
