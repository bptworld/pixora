from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import urllib.parse
import urllib.request

from card_utils import draw_sharp_text, lookup_airline, render_text_webp

CARD_ID = "airport_board"
CARD_NAME = "Airport Board"
CARD_DETAIL = "Free FlightStats arrival and departure board"
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
            {"value": "10", "label": "10 flights"},
        ],
    },
    {
        "key": "pollMinutes",
        "label": "Poll Minutes",
        "type": "select",
        "default": "30",
        "choices": [
            {"value": "10", "label": "10 minutes"},
            {"value": "15", "label": "15 minutes"},
            {"value": "30", "label": "30 minutes"},
            {"value": "60", "label": "60 minutes"},
        ],
    },
    {"key": "skipNoData", "label": "Skip if no data", "type": "checkbox", "default": False},
]

_API_ROOT = "https://www.flightstats.com/v2/api-next/flight-tracker"
_CACHE = {}
_RESULT_CACHE = {}


def _clean(value):
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _is_wide(options):
    return (options or {}).get("_target") == "matrixportal-s3-128x32"


def _truthy(value):
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "on"}


def _skip_no_data(options):
    return _truthy((options or {}).get("skipNoData"))


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


def _flightstats_rows(data):
    if isinstance(data, dict):
        payload = data.get("data")
        if isinstance(payload, dict):
            rows = payload.get("flights")
            return rows if isinstance(rows, list) else []
    return []


def _fetch_flightstats_board(kind, airport, date_value, start_hour, hours, airline_filter, seconds):
    now = datetime.now(timezone.utc)
    params = {"numHours": str(hours)}
    if airline_filter:
        params["carrierCode"] = airline_filter
    key = "|".join([
        kind,
        airport,
        date_value.strftime("%Y-%m-%d"),
        str(start_hour),
        urllib.parse.urlencode(sorted(params.items())),
    ])
    cached = _CACHE.get(key)
    if cached and cached["expires"] > now:
        return cached["data"]
    url = (
        f"{_API_ROOT}/{kind}/{airport}/"
        f"{date_value.year}/{date_value.month}/{date_value.day}/{start_hour}"
        f"?{urllib.parse.urlencode(params)}"
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; Pixora/0.1)",
        "Accept": "application/json",
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


def _flight_number(row):
    carrier = row.get("carrier") if isinstance(row.get("carrier"), dict) else {}
    op = _clean(carrier.get("fs"))[:3]
    num = "".join(ch for ch in str(carrier.get("flightNumber") or "") if ch.isdigit())
    return (op + num)[:8] if op or num else "FLIGHT"


def _airline_iata(row):
    carrier = row.get("carrier") if isinstance(row.get("carrier"), dict) else {}
    return _clean(carrier.get("fs"))[:3]


def _status(row):
    return "ON TIME"


def _time_for(row, direction):
    value = row.get("departureTime") if direction == "DEP" else row.get("arrivalTime")
    if isinstance(value, dict):
        return value.get("timeAMPM") or value.get("time24") or ""
    return ""


def _sort_time_for(row, direction):
    primary = _parse_time(row.get("sortTime"))
    if primary:
        return primary
    return datetime.max.replace(tzinfo=timezone.utc)


def _row_from_flightstats(row, direction, airline_filter):
    airport = row.get("airport") if isinstance(row.get("airport"), dict) else {}
    other = _clean(airport.get("fs"))[:4] or "---"
    if other == "---":
        return None
    iata = _airline_iata(row)
    flight = _flight_number(row)
    if airline_filter and iata != airline_filter and not flight.startswith(airline_filter):
        return None
    airline = lookup_airline(flight) or lookup_airline(iata or flight)
    time_value = _time_for(row, direction)
    time_text = str(time_value or "").replace(" ", "") or ("LIVE" if direction == "ARR" else "NOW")
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


def _flightstats_windows(now, hours):
    local_now = now.astimezone()
    windows = []
    remaining = hours
    cursor = local_now.replace(minute=0, second=0, microsecond=0)
    while remaining > 0:
        available_today = max(1, 24 - cursor.hour)
        chunk = min(remaining, available_today, 12)
        windows.append((cursor.date(), cursor.hour, chunk))
        cursor += timedelta(hours=chunk)
        remaining -= chunk
    return windows


def _board_rows(opts):
    airport = _clean(opts.get("airport") or "BOS")[:3]
    if len(airport) != 3:
        return [], "SET AIRPORT"
    hours = _parse_int(opts.get("hours"), 2, 1, 4)
    limit = _parse_int(opts.get("maxFlights"), 3, 1, 10)
    poll_minutes = _parse_int(opts.get("pollMinutes"), 30, 10, 120)
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

    directions = []
    if board_type in ("departures", "both"):
        directions.append(("dep", "DEP"))
    if board_type in ("arrivals", "both"):
        directions.append(("arr", "ARR"))
    try:
        raw_rows = []
        for kind, direction in directions:
            for date_value, start_hour, chunk_hours in _flightstats_windows(now, hours):
                _safe_log(opts, f"[airport_board] {opts.get('_device_id', '')} polling FlightStats {airport} {kind} {date_value} {start_hour}:00 +{chunk_hours}h cache={poll_minutes}m")
                data = _fetch_flightstats_board(kind, airport, date_value, start_hour, chunk_hours, airline_filter, poll_minutes * 60)
                for item in _flightstats_rows(data):
                    raw_rows.append((item, direction))
    except urllib.error.HTTPError as err:
        error = None if err.code == 404 else "FS ERR"
        _RESULT_CACHE[result_key] = {
            "rows": [],
            "error": error,
            "expires": now + timedelta(minutes=poll_minutes),
        }
        return [], error
    except Exception:
        _RESULT_CACHE[result_key] = {
            "rows": [],
            "error": "FS ERR",
            "expires": now + timedelta(minutes=poll_minutes),
        }
        return [], "FS ERR"
    rows = []
    seen = set()
    for item, direction in raw_rows:
        row = _row_from_flightstats(item, direction, airline_filter)
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
    _safe_log(opts, f"[airport_board] {opts.get('_device_id', '')} FlightStats returned {len(raw_rows)} rows; usable={len(rows)} for {airport} {board_type}")
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


def _compact_time(value, width):
    text = str(value or "")
    text = text.replace("AM", "A").replace("PM", "P")
    if width < 128:
        return text[:5]
    return text[:6]


def _draw_row(image, draw, row, y, width, font):
    if width >= 128:
        columns = [
            (1, 33, _compact_time(row.get("time"), width), (235, 245, 255)),
            (35, 69, row.get("flight"), (235, 245, 255)),
            (72, 91, row.get("other"), (160, 215, 255)),
            (94, width - 2, row.get("status"), (210, 230, 235)),
        ]
    else:
        columns = [
            (1, 22, _compact_time(row.get("time"), width), (235, 245, 255)),
            (25, 49, row.get("flight"), (235, 245, 255)),
            (52, width - 2, row.get("other"), (160, 215, 255)),
        ]
    for x, max_x, value, color in columns:
        text = _fit(draw, value, font, max(0, max_x - x))
        draw_sharp_text(image, (x, y), text, color, font)


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
        _draw_row(image, draw, row, y, width, font)
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
    sub = "FLIGHTSTATS" if width == 128 else "FSTAT"
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
        if _skip_no_data(opts):
            return None
        return _render_empty(airport, board_type, 128 if wide else 64)
    return _render_board(rows, airport, board_type, 128 if wide else 64)
