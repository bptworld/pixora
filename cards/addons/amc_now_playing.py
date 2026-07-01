from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import json
import re
import urllib.parse
import urllib.request

from card_utils import _settings_value, draw_sharp_text, fetch_json_request, pixora_local_now, pixora_local_timezone

CARD_ID = "amc_now_playing"
CARD_NAME = "AMC Now Playing"
CARD_DETAIL = "AMC theatre showtimes"
CARD_CATEGORY = "Utility"

_THEATRE_CHOICES = [
    {"value": "__nearby__", "label": "Nearby AMC theatres (20 mi)"},
    {"value": "amc-methuen-20", "label": "AMC Methuen 20"},
    {"value": "amc-tyngsboro-12", "label": "AMC Tyngsboro 12"},
    {"value": "amc-boston-common-19", "label": "AMC Boston Common 19"},
    {"value": "amc-braintree-10", "label": "AMC Braintree 10"},
    {"value": "amc-burlington-cinema-10", "label": "AMC Burlington Cinema 10"},
    {"value": "amc-danvers-20", "label": "AMC Danvers 20"},
    {"value": "amc-dartmouth-mall-11", "label": "AMC Dartmouth Mall 11"},
    {"value": "amc-dedham-12", "label": "AMC Dedham 12"},
    {"value": "amc-framingham-16", "label": "AMC Framingham 16"},
    {"value": "amc-south-bay-center-12", "label": "AMC South Bay Center 12"},
    {"value": "amc-assembly-row-12", "label": "AMC Assembly Row 12"},
    {"value": "amc-liberty-tree-mall-20", "label": "AMC Liberty Tree Mall 20"},
    {"value": "amc-empire-25", "label": "AMC Empire 25"},
    {"value": "amc-newport-centre-11", "label": "AMC Newport Centre 11"},
    {"value": "amc-jersey-gardens-20", "label": "AMC Jersey Gardens 20"},
    {"value": "amc-hamilton-24", "label": "AMC Hamilton 24"},
    {"value": "amc-river-east-21", "label": "AMC River East 21"},
    {"value": "amc-century-city-15", "label": "AMC Century City 15"},
    {"value": "amc-grove-14", "label": "AMC The Grove 14"},
    {"value": "amc-disney-springs-24", "label": "AMC Disney Springs 24"},
]

_FORMAT_CHOICES = [
    {"value": "", "label": "Any Format"},
    {"value": "imax", "label": "IMAX"},
    {"value": "dolbycinema", "label": "Dolby Cinema"},
    {"value": "prime", "label": "Prime at AMC"},
    {"value": "laser", "label": "Laser at AMC"},
    {"value": "reald3d", "label": "RealD 3D"},
    {"value": "opencaption", "label": "Open Caption"},
    {"value": "closedcaption", "label": "Closed Caption"},
    {"value": "descriptivevideo", "label": "Audio Description"},
    {"value": "reservedseating", "label": "Reserved Seating"},
]

_RATING_CHOICES = [
    {"value": "G", "label": "G"},
    {"value": "PG", "label": "PG"},
    {"value": "PG13", "label": "PG-13"},
    {"value": "R", "label": "R"},
    {"value": "NC17", "label": "NC-17"},
    {"value": "NR", "label": "Not Rated"},
]

CARD_OPTIONS = [
    {
        "key": "theatreNumber",
        "label": "Theatre",
        "type": "select",
        "default": "__nearby__",
        "choices": _THEATRE_CHOICES,
    },
    {"key": "movie", "label": "Movie Filter", "type": "text", "default": "", "maxlength": 50},
    {
        "key": "ratings",
        "label": "Ratings",
        "type": "multiselect",
        "default": "",
        "size": 4,
        "choices": _RATING_CHOICES,
    },
    {
        "key": "includeAttributes",
        "label": "Required Format",
        "type": "select",
        "default": "",
        "choices": _FORMAT_CHOICES,
    },
    {
        "key": "dateOffset",
        "label": "Show Date",
        "type": "select",
        "default": "0",
        "choices": [
            {"value": "0", "label": "Today"},
            {"value": "1", "label": "Tomorrow"},
            {"value": "2", "label": "In 2 days"},
            {"value": "3", "label": "In 3 days"},
        ],
    },
    {
        "key": "maxMovies",
        "label": "Movies Shown",
        "type": "select",
        "default": "3",
        "choices": [
            {"value": "1", "label": "1 movie"},
            {"value": "2", "label": "2 movies"},
            {"value": "3", "label": "3 movies"},
            {"value": "4", "label": "4 movies"},
            {"value": "5", "label": "5 movies"},
            {"value": "6", "label": "6 movies"},
        ],
    },
    {
        "key": "pollMinutes",
        "label": "Poll Minutes",
        "type": "select",
        "default": "60",
        "choices": [
            {"value": "30", "label": "30 minutes"},
            {"value": "60", "label": "60 minutes"},
            {"value": "120", "label": "2 hours"},
            {"value": "240", "label": "4 hours"},
        ],
    },
]

_API_ROOT = "https://api.amctheatres.com"
_NEARBY_RADIUS_MILES = 20
_CACHE = {}
_THEATRE_CACHE = {}
_ZIP_CACHE = {}
_VENDOR_KEY_PARTS = (
    "139B051F",
    "7B4C",
    "4D26",
    "BE7A",
    "EAA8ACA7A54B",
)


def _int(value, default, lo, hi):
    try:
        number = int(value)
    except Exception:
        number = default
    return max(lo, min(hi, number))


def _date_text(offset):
    day = pixora_local_now().date() + timedelta(days=_int(offset, 0, 0, 14))
    return day.isoformat()


def _clean_title(value):
    text = re.sub(r"[^A-Za-z0-9 &'!:.+-]+", " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text or "MOVIE"


def _abbr_title(value, limit):
    text = _clean_title(value).upper()
    replacements = {
        "MISSION IMPOSSIBLE": "M:I",
        "JURASSIC WORLD": "JURASSIC",
        "FINAL RECKONING": "FINAL",
        "THE ": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text[:limit].rstrip()


def _parse_utc(value):
    text = str(value or "").replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_local(value):
    try:
        return datetime.fromisoformat(str(value or ""))
    except Exception:
        return None


def _time_text(showtime):
    dt = _parse_local(showtime.get("showDateTimeLocal"))
    if not dt:
        dt = _parse_utc(showtime.get("showDateTimeUtc"))
        if dt:
            local_tz = pixora_local_timezone()
            dt = dt.astimezone(local_tz) if local_tz else dt.astimezone()
    if not dt:
        return "--"
    hour = dt.hour % 12 or 12
    suffix = "A" if dt.hour < 12 else "P"
    return f"{hour}:{dt.minute:02d}{suffix}"


def _format_text(showtime):
    premium = str(showtime.get("premiumFormat") or "").strip().upper()
    attrs = showtime.get("attributes") if isinstance(showtime.get("attributes"), list) else []
    codes = [str(a.get("code") or a.get("name") or "").upper() for a in attrs if isinstance(a, dict)]
    if premium:
        return premium[:8]
    for code, label in (
        ("IMAX", "IMAX"),
        ("DOLBY", "DOLBY"),
        ("PRIME", "PRIME"),
        ("LASER", "LASER"),
        ("3D", "3D"),
        ("OPENCAPTION", "OPEN CAP"),
    ):
        if any(code in c for c in codes):
            return label
    return str(showtime.get("mpaaRating") or "").upper()[:5]


def _request_json(url, api_key):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Pixora/0.1",
        "Accept": "application/json",
        "X-AMC-Vendor-Key": api_key,
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _location_from_default_zip():
    zip_code = re.sub(r"\D+", "", str(_settings_value("defaultZipCode", "") or ""))[:5]
    if not zip_code:
        lat = str(_settings_value("defaultLatitude", "") or "").strip()
        lon = str(_settings_value("defaultLongitude", "") or "").strip()
        if lat and lon:
            return float(lat), float(lon), "default location"
        raise ValueError("zip")

    now = datetime.now(timezone.utc)
    cached = _ZIP_CACHE.get(zip_code)
    if cached and cached["expires"] > now:
        return cached["lat"], cached["lon"], zip_code

    data = fetch_json_request(f"https://api.zippopotam.us/us/{zip_code}", seconds=86400)
    place = data["places"][0]
    lat, lon = float(place["latitude"]), float(place["longitude"])
    _ZIP_CACHE[zip_code] = {"lat": lat, "lon": lon, "expires": now + timedelta(days=7)}
    return lat, lon, zip_code


def _embedded_items(data, key):
    if not isinstance(data, dict):
        return []
    items = (data.get("_embedded") or {}).get(key) or []
    return items if isinstance(items, list) else []


def _vendor_key():
    return "-".join(_VENDOR_KEY_PARTS)


def _resolve_theatre_number(value, api_key):
    text = str(value or "").strip()
    if not text:
        raise ValueError("theatre")
    if text.isdigit():
        return text
    now = datetime.now(timezone.utc)
    cached = _THEATRE_CACHE.get(text)
    if cached and cached["expires"] > now:
        return cached["id"]

    slug = urllib.parse.quote(text, safe="")
    data = _request_json(f"{_API_ROOT}/v2/theatres/{slug}", api_key)
    theatre_id = str(data.get("id") or data.get("westWorldMediaTheatreNumber") or "").strip()
    if not theatre_id:
        raise ValueError("theatre")
    _THEATRE_CACHE[text] = {"id": theatre_id, "expires": now + timedelta(days=7)}
    return theatre_id


def _has_attribute(row, attribute):
    attribute = str(attribute or "").strip().lower()
    if not attribute:
        return True
    attrs = row.get("attributes") if isinstance(row.get("attributes"), list) else []
    values = []
    for item in attrs:
        if isinstance(item, dict):
            values.append(str(item.get("code") or "").lower())
            values.append(str(item.get("name") or "").lower().replace(" ", ""))
    premium = str(row.get("premiumFormat") or "").lower().replace(" ", "")
    values.append(premium)
    return any(attribute in value or value in attribute for value in values if value)


def _distance_miles(row):
    for key in ("distance", "distanceMiles", "distanceInMiles", "theatreDistance"):
        try:
            value = float(row.get(key))
            return value
        except Exception:
            pass
    theatre = row.get("theatre") if isinstance(row.get("theatre"), dict) else {}
    for key in ("distance", "distanceMiles", "distanceInMiles"):
        try:
            value = float(theatre.get(key))
            return value
        except Exception:
            pass
    return None


def _nearby_showtimes(opts, api_key):
    lat, lon, label = _location_from_default_zip()
    path = f"/v2/showtimes/views/current-location/{_date_text(opts.get('dateOffset'))}/{lat:.5f}/{lon:.5f}"
    url = f"{_API_ROOT}{path}"
    cache_key = url + "|" + str(opts.get("includeAttributes") or "") + "|" + api_key[-8:]
    now = datetime.now(timezone.utc)
    cached = _CACHE.get(cache_key)
    if cached and cached["expires"] > now:
        return cached["rows"]

    data = _request_json(url, api_key)
    rows = [row for row in _embedded_items(data, "showtimes") if isinstance(row, dict)]
    include = str(opts.get("includeAttributes") or "").strip()
    rows = [row for row in rows if _has_attribute(row, include)]
    rows = [
        row for row in rows
        if _distance_miles(row) is None or _distance_miles(row) <= _NEARBY_RADIUS_MILES
    ]
    rows.sort(key=lambda row: row.get("showDateTimeUtc") or row.get("showDateTimeLocal") or "")
    _CACHE[cache_key] = {
        "rows": rows,
        "expires": now + timedelta(minutes=_int(opts.get("pollMinutes"), 60, 15, 360)),
        "location": label,
    }
    return rows


def _showtimes(opts):
    api_key = _vendor_key()
    theatre_value = str(opts.get("theatreNumber") or "__nearby__").strip() or "__nearby__"
    if theatre_value == "__nearby__":
        return _nearby_showtimes(opts, api_key)

    theatre = _resolve_theatre_number(theatre_value, api_key)

    params = {"page-size": "100"}
    include = str(opts.get("includeAttributes") or "").strip()
    if include:
        params["include-attributes"] = include
        params["attribute-operator"] = "and"
    path = f"/v2/theatres/{theatre}/showtimes/{_date_text(opts.get('dateOffset'))}"
    url = f"{_API_ROOT}{path}?{urllib.parse.urlencode(params)}"
    cache_key = url + "|" + api_key[-8:]
    now = datetime.now(timezone.utc)
    cached = _CACHE.get(cache_key)
    if cached and cached["expires"] > now:
        return cached["rows"]

    data = _request_json(url, api_key)
    rows = _embedded_items(data, "showtimes")
    rows = [row for row in rows if isinstance(row, dict)]
    rows.sort(key=lambda row: row.get("showDateTimeUtc") or row.get("showDateTimeLocal") or "")
    _CACHE[cache_key] = {
        "rows": rows,
        "expires": now + timedelta(minutes=_int(opts.get("pollMinutes"), 60, 15, 360)),
    }
    return rows


def _demo_rows():
    today = pixora_local_now().date().isoformat()
    return [
        {"movieName": "Mission: Impossible", "showDateTimeLocal": f"{today}T19:00:00", "mpaaRating": "PG13", "premiumFormat": "IMAX"},
        {"movieName": "Mission: Impossible", "showDateTimeLocal": f"{today}T21:45:00", "mpaaRating": "PG13", "premiumFormat": "IMAX"},
        {"movieName": "F1 The Movie", "showDateTimeLocal": f"{today}T19:25:00", "mpaaRating": "PG13", "premiumFormat": "DOLBY"},
        {"movieName": "Lilo & Stitch", "showDateTimeLocal": f"{today}T20:10:00", "mpaaRating": "PG", "premiumFormat": ""},
    ]


def _movie_groups(rows, max_movies):
    now = datetime.now(timezone.utc)
    grouped = {}
    for row in rows:
        if row.get("isCanceled") or row.get("isEmbargoed") or row.get("isComingSoon"):
            continue
        show_utc = _parse_utc(row.get("showDateTimeUtc"))
        if show_utc and show_utc < now - timedelta(minutes=20):
            continue
        title = _clean_title(row.get("movieName"))
        grouped.setdefault(title, []).append(row)
    movies = []
    for title, shows in grouped.items():
        shows.sort(key=lambda row: row.get("showDateTimeUtc") or row.get("showDateTimeLocal") or "")
        movies.append({"title": title, "shows": shows[:4]})
    movies.sort(key=lambda movie: movie["shows"][0].get("showDateTimeUtc") or movie["shows"][0].get("showDateTimeLocal") or "")
    return movies[:max_movies]


def _filter_movie_rows(rows, movie_filter):
    needle = str(movie_filter or "").strip().lower()
    if not needle:
        return rows
    return [
        row for row in rows
        if needle in _clean_title(row.get("movieName")).lower()
    ]


def _normalize_rating(value):
    text = re.sub(r"[^A-Za-z0-9]+", "", str(value or "")).upper()
    aliases = {
        "PG13": "PG13",
        "PG": "PG",
        "G": "G",
        "R": "R",
        "NC17": "NC17",
        "NR": "NR",
        "NOTRATED": "NR",
        "UNRATED": "NR",
    }
    return aliases.get(text, text)


def _rating_values(value):
    if isinstance(value, (list, tuple, set)):
        raw = value
    else:
        raw = str(value or "").split(",")
    return {_normalize_rating(item) for item in raw if _normalize_rating(item)}


def _filter_rating_rows(rows, ratings):
    allowed = _rating_values(ratings)
    if not allowed:
        return rows
    return [
        row for row in rows
        if _normalize_rating(row.get("mpaaRating") or row.get("rating")) in allowed
    ]


def _fonts():
    from PIL import ImageFont
    try:
        return (
            ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8),
            ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8),
            ImageFont.truetype("assets/fonts/Jersey10-Regular.ttf", 10),
        )
    except Exception:
        font = ImageFont.load_default()
        return font, font, font


def _draw_header(image, draw, width, bold):
    draw.rectangle((0, 0, width - 1, 6), fill=(175, 12, 22))
    draw.rectangle((0, 8, width - 1, 9), fill=(255, 204, 43))
    _, font, _ = _fonts()
    draw_sharp_text(image, (2, -3), "AMC", (255, 235, 90), bold)
    if width == 128:
        label = "NOW PLAYING"
        box = draw.textbbox((0, 0), label, font=font)
        draw_sharp_text(image, (width - (box[2] - box[0]) - 2, -3), label, (255, 245, 245), font)


def _showtimes_line(shows, limit):
    parts = []
    for show in shows:
        text = _time_text(show)
        if show.get("isSoldOut"):
            text += " SOLD"
        parts.append(text)
    return " ".join(parts)[:limit]


def _fit_text(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1].rstrip()
    return text


def _draw_time_chips(image, draw, shows, font):
    x = 1
    y = 19
    for idx, show in enumerate(shows[:3]):
        text = _time_text(show)
        box = draw.textbbox((0, 0), text, font=font)
        w = box[2] - box[0]
        color = (255, 206, 64) if idx == 0 else (235, 238, 210)
        if x + w > 63:
            break
        draw_sharp_text(image, (x, y), text, color, font)
        x += w + 3


def _draw_64(movie):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (64, 32), (7, 8, 12))
    draw = ImageDraw.Draw(image)
    bold, font, _ = _fonts()
    _draw_header(image, draw, 64, bold)
    title = _abbr_title(movie["title"], 11)
    draw_sharp_text(image, (2, 8), title, (250, 250, 245), font)
    times = [_time_text(show) for show in movie["shows"][:2]]
    widths = [draw.textbbox((0, 0), time, font=font)[2] for time in times]
    total_w = sum(widths) + (6 if len(times) > 1 else 0)
    x = max(1, (64 - total_w) // 2)
    for idx, (time, width) in enumerate(zip(times, widths)):
        color = (255, 206, 64) if idx == 0 else (235, 238, 210)
        draw_sharp_text(image, (x, 18), time, color, font)
        x += width + 6
    return image


def _draw_128(movies):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (128, 32), (7, 8, 12))
    draw = ImageDraw.Draw(image)
    bold, font, _ = _fonts()
    _draw_header(image, draw, 128, bold)
    for idx, movie in enumerate(movies[:2]):
        y = 8 + idx * 11
        color = (250, 250, 245) if idx == 0 else (205, 216, 226)
        title = _fit_text(draw, _abbr_title(movie["title"], 20), font, 62)
        draw_sharp_text(image, (2, y), title, color, font)
        times = [_time_text(show) for show in movie["shows"][:2]]
        for time_idx, time in enumerate(times):
            time_color = (255, 206, 64) if time_idx == 0 else (235, 238, 210)
            x = 72 if time_idx == 0 else 102
            draw_sharp_text(image, (x, y), time, time_color, font)
    return image


def _to_webp(image):
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _message_webp(text, color, width):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, 32), (7, 8, 12))
    draw = ImageDraw.Draw(image)
    bold, font, _ = _fonts()
    _draw_header(image, draw, width, bold)
    text = str(text or "").upper()
    while text and draw.textbbox((0, 0), text, font=font)[2] > width - 2:
        text = text[:-1].rstrip()
    box = draw.textbbox((0, 0), text, font=font)
    draw_sharp_text(image, ((width - (box[2] - box[0])) // 2, 14), text, color, font)
    return _to_webp(image)


def _animated(images, dwell):
    frames = images or []
    if len(frames) <= 1:
        return _to_webp(frames[0])
    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=2200, loop=0, lossless=True, quality=100)
    return {"body": out.getvalue(), "dwell_secs": max(dwell, 4), "_no_replay": True}


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    dwell = _int(opts.get("_dwell"), 10, 4, 120)

    if opts.get("_demo"):
        rows = _demo_rows()
    else:
        try:
            rows = _showtimes(opts)
        except PermissionError:
            return _message_webp("AMC KEY", (255, 206, 64), width)
        except ValueError as exc:
            if str(exc) == "zip":
                return _message_webp("SET ZIP", (255, 206, 64), width)
            return _message_webp("SET THEATRE", (255, 206, 64), width)
        except Exception:
            return _message_webp("AMC ERR", (238, 80, 80), width)

    rows = _filter_movie_rows(rows, opts.get("movie"))
    rows = _filter_rating_rows(rows, opts.get("ratings"))
    movies = _movie_groups(rows, _int(opts.get("maxMovies"), 3, 1, 6))
    if not movies:
        return _message_webp("NO SHOWS", (160, 170, 180), width)

    if width == 128:
        pages = [movies[i:i + 2] for i in range(0, len(movies), 2)]
        return _animated([_draw_128(page) for page in pages], dwell)
    return _animated([_draw_64(movie) for movie in movies], dwell)
