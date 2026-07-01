from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import html
import json
import math
import re
import urllib.parse
import urllib.request

from card_utils import _settings_value, draw_sharp_text, fetch_json_request, pixora_local_now

CARD_ID = "cinemark_now_playing"
CARD_NAME = "Cinemark Now Playing"
CARD_DETAIL = "Cinemark theatre showtimes"
CARD_CATEGORY = "Utility"

_THEATRES = [
    {"value": "__nearest__", "label": "Nearest listed Cinemark", "url": "", "lat": None, "lon": None},
    {"value": "ma-hadley/cinemark-at-hampshire-mall-and-xd", "label": "Cinemark At Hampshire Mall and XD", "url": "/theatres/ma-hadley/cinemark-at-hampshire-mall-and-xd", "lat": 42.3543, "lon": -72.5529},
    {"value": "ct-manchester/cinemark-buckland-hills-18-xd-and-imax", "label": "Cinemark Buckland Hills 18 + XD", "url": "/theatres/ct-manchester/cinemark-buckland-hills-18-xd-and-imax", "lat": 41.8075, "lon": -72.5432},
    {"value": "ri-lincoln/cinemark-lincoln-mall-16-and-xd", "label": "Cinemark Lincoln Mall 16 and XD", "url": "/theatres/ri-lincoln/cinemark-lincoln-mall-16-and-xd", "lat": 41.8912, "lon": -71.4348},
    {"value": "ny-rochester/cinemark-tinseltown-rochester-and-imax", "label": "Cinemark Tinseltown Rochester + IMAX", "url": "/theatres/ny-rochester/cinemark-tinseltown-rochester-and-imax", "lat": 43.2068, "lon": -77.6966},
    {"value": "pa-philadelphia/cinemark-university-city-penn-6", "label": "Cinemark University City Penn 6", "url": "/theatres/pa-philadelphia/cinemark-university-city-penn-6", "lat": 39.9539, "lon": -75.1979},
    {"value": "tx-plano/cinemark-west-plano-and-xd", "label": "Cinemark West Plano and XD", "url": "/theatres/tx-plano/cinemark-west-plano-and-xd", "lat": 33.0508, "lon": -96.8321},
    {"value": "tx-dallas/cinemark-dallas-xd-and-imax", "label": "Cinemark Dallas XD and IMAX", "url": "/theatres/tx-dallas/cinemark-dallas-xd-and-imax", "lat": 32.8662, "lon": -96.7695},
    {"value": "ca-daly-city/cinemark-century-daly-city-20-xd-and-imax", "label": "Cinemark Century Daly City XD + IMAX", "url": "/theatres/ca-daly-city/cinemark-century-daly-city-20-xd-and-imax", "lat": 37.7022, "lon": -122.4842},
    {"value": "id-meridian/cinemark-majestic-cinemas", "label": "Cinemark Majestic Cinemas", "url": "/theatres/id-meridian/cinemark-majestic-cinemas", "lat": 43.6199, "lon": -116.3543},
    {"value": "ut-sandy/cinemark-century-sandy-union-heights-16", "label": "Cinemark Century Sandy Union Heights 16", "url": "/theatres/ut-sandy/cinemark-century-sandy-union-heights-16", "lat": 40.5686, "lon": -111.8671},
]

_FORMAT_CHOICES = [
    {"value": "", "label": "Any Format"},
    {"value": "xd", "label": "Cinemark XD"},
    {"value": "imax", "label": "IMAX"},
    {"value": "reald3d", "label": "RealD 3D"},
    {"value": "standard", "label": "Standard"},
    {"value": "closedcaption", "label": "Closed Caption"},
    {"value": "descriptive", "label": "Descriptive Narration"},
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
    {"key": "theatre", "label": "Theatre", "type": "select", "default": "__nearest__", "choices": [{"value": t["value"], "label": t["label"]} for t in _THEATRES]},
    {"key": "movie", "label": "Movie Filter", "type": "text", "default": "", "maxlength": 50},
    {"key": "ratings", "label": "Ratings", "type": "multiselect", "default": "", "size": 4, "choices": _RATING_CHOICES},
    {"key": "includeAttributes", "label": "Required Format", "type": "select", "default": "", "choices": _FORMAT_CHOICES},
    {"key": "dateOffset", "label": "Show Date", "type": "select", "default": "0", "choices": [{"value": "0", "label": "Today"}, {"value": "1", "label": "Tomorrow"}, {"value": "2", "label": "In 2 days"}, {"value": "3", "label": "In 3 days"}]},
    {"key": "maxMovies", "label": "Movies Shown", "type": "select", "default": "3", "choices": [{"value": str(i), "label": f"{i} movie" if i == 1 else f"{i} movies"} for i in range(1, 7)]},
    {"key": "pollMinutes", "label": "Poll Minutes", "type": "select", "default": "60", "choices": [{"value": "30", "label": "30 minutes"}, {"value": "60", "label": "60 minutes"}, {"value": "120", "label": "2 hours"}, {"value": "240", "label": "4 hours"}]},
]

_BASE = "https://www.cinemark.com"
_CACHE = {}
_ZIP_CACHE = {}


def _int(value, default, lo, hi):
    try:
        number = int(value)
    except Exception:
        number = default
    return max(lo, min(hi, number))


def _date_text(offset):
    return (pixora_local_now().date() + timedelta(days=_int(offset, 0, 0, 30))).isoformat()


def _request_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Pixora/0.1", "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _default_location():
    zip_code = re.sub(r"\D+", "", str(_settings_value("defaultZipCode", "") or ""))[:5]
    if not zip_code:
        return None
    now = datetime.now(timezone.utc)
    cached = _ZIP_CACHE.get(zip_code)
    if cached and cached["expires"] > now:
        return cached["lat"], cached["lon"]
    data = fetch_json_request(f"https://api.zippopotam.us/us/{zip_code}", seconds=86400)
    place = data["places"][0]
    lat, lon = float(place["latitude"]), float(place["longitude"])
    _ZIP_CACHE[zip_code] = {"lat": lat, "lon": lon, "expires": now + timedelta(days=7)}
    return lat, lon


def _miles(a_lat, a_lon, b_lat, b_lon):
    radius = 3958.8
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def _theatre_url(value):
    if value and value != "__nearest__":
        for theatre in _THEATRES:
            if theatre["value"] == value:
                return theatre["url"]
        return "/theatres/" + str(value).strip("/")
    loc = _default_location()
    if loc:
        choices = [t for t in _THEATRES if t.get("lat") is not None and t.get("lon") is not None]
        choices.sort(key=lambda t: _miles(loc[0], loc[1], t["lat"], t["lon"]))
        if choices:
            return choices[0]["url"]
    return _THEATRES[1]["url"]


def _clean_title(value):
    text = html.unescape(re.sub(r"\s+", " ", str(value or ""))).strip()
    return text or "MOVIE"


def _abbr_title(value, limit):
    text = _clean_title(value).upper()
    for old, new in {"MISSION IMPOSSIBLE": "M:I", "THE ": "", "CINEMARK ": ""}.items():
        text = text.replace(old, new)
    return text[:limit].rstrip()


def _normalize_rating(value):
    text = re.sub(r"[^A-Za-z0-9]+", "", str(value or "")).upper()
    return {"PG13": "PG13", "NC17": "NC17", "NOTRATED": "NR", "UNRATED": "NR"}.get(text, text)


def _rating_values(value):
    raw = value if isinstance(value, (list, tuple, set)) else str(value or "").split(",")
    return {_normalize_rating(item) for item in raw if _normalize_rating(item)}


def _parse_time(value):
    try:
        return datetime.fromisoformat(str(value or ""))
    except Exception:
        return None


def _time_text(showtime):
    dt = _parse_time(showtime.get("showDateTimeLocal"))
    if not dt:
        return "--"
    hour = dt.hour % 12 or 12
    return f"{hour}:{dt.minute:02d}{'A' if dt.hour < 12 else 'P'}"


def _format_match(row, required):
    required = re.sub(r"[^a-z0-9]+", "", str(required or "").lower())
    if not required:
        return True
    value = re.sub(r"[^a-z0-9]+", "", str(row.get("format") or "").lower())
    return required in value or value in required


def _parse_rows(page):
    rows = []
    blocks = re.split(r'<div class="showtimeMovieBlock[^"]*"', page)[1:]
    for block in blocks:
        title_match = re.search(r'data-movie-title="([^"]+)"', block)
        title = html.unescape(title_match.group(1)) if title_match else ""
        if not title:
            json_title = re.search(r'&quot;movieTitle&quot;:\s*&quot;([^&]+)&quot;', block)
            title = html.unescape(json_title.group(1)) if json_title else "Movie"
        rating_match = re.search(r'<span class="showtimeMovieRating">([^<]*)</span>', block)
        rating = _normalize_rating(html.unescape(rating_match.group(1))) if rating_match else ""
        for link in re.finditer(r'<a[^>]+class="showtime-link"[^>]+>', block):
            tag = link.group(0)
            href = html.unescape(re.search(r'href="([^"]+)"', tag).group(1) if re.search(r'href="([^"]+)"', tag) else "")
            dt_match = re.search(r"Showtime=([0-9T:\-]+)", href)
            if not dt_match:
                continue
            fmt_match = re.search(r'data-print-type-name="([^"]*)"', tag)
            rows.append({
                "movieName": _clean_title(title),
                "mpaaRating": rating,
                "format": html.unescape(fmt_match.group(1)) if fmt_match else "",
                "showDateTimeLocal": dt_match.group(1),
            })
    rows.sort(key=lambda row: row["showDateTimeLocal"])
    return rows


def _fetch_showtimes(opts):
    show_date = _date_text(opts.get("dateOffset"))
    theatre = _theatre_url(str(opts.get("theatre") or "__nearest__"))
    url = f"{_BASE}{theatre}?showDate={urllib.parse.quote(show_date)}"
    now = datetime.now(timezone.utc)
    cached = _CACHE.get(url)
    if cached and cached["expires"] > now:
        return cached["rows"]
    rows = _parse_rows(_request_text(url))
    _CACHE[url] = {"rows": rows, "expires": now + timedelta(minutes=_int(opts.get("pollMinutes"), 60, 15, 360))}
    return rows


def _demo_rows():
    today = pixora_local_now().date().isoformat()
    return [
        {"movieName": "The Mandalorian and Grogu", "showDateTimeLocal": f"{today}T19:00:00", "mpaaRating": "PG13", "format": "XD"},
        {"movieName": "The Mandalorian and Grogu", "showDateTimeLocal": f"{today}T21:45:00", "mpaaRating": "PG13", "format": "XD"},
        {"movieName": "Michael", "showDateTimeLocal": f"{today}T19:25:00", "mpaaRating": "PG13", "format": "Standard"},
        {"movieName": "The Sheep Detectives", "showDateTimeLocal": f"{today}T20:10:00", "mpaaRating": "PG", "format": "Standard"},
    ]


def _filter_rows(rows, opts):
    needle = str(opts.get("movie") or "").strip().lower()
    ratings = _rating_values(opts.get("ratings"))
    fmt = opts.get("includeAttributes")
    now = pixora_local_now().replace(tzinfo=None)
    out = []
    for row in rows:
        dt = _parse_time(row.get("showDateTimeLocal"))
        if dt and dt < now - timedelta(minutes=20):
            continue
        if needle and needle not in _clean_title(row.get("movieName")).lower():
            continue
        if ratings and _normalize_rating(row.get("mpaaRating")) not in ratings:
            continue
        if not _format_match(row, fmt):
            continue
        out.append(row)
    return out


def _movie_groups(rows, max_movies):
    grouped = {}
    for row in rows:
        grouped.setdefault(_clean_title(row.get("movieName")), []).append(row)
    movies = [{"title": title, "shows": shows[:4]} for title, shows in grouped.items()]
    movies.sort(key=lambda movie: movie["shows"][0].get("showDateTimeLocal") or "")
    return movies[:max_movies]


def _fonts():
    from PIL import ImageFont
    try:
        return ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8), ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        font = ImageFont.load_default()
        return font, font


def _fit_text(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1].rstrip()
    return text


def _draw_header(image, draw, width, bold):
    draw.rectangle((0, 0, width - 1, 6), fill=(155, 8, 18))
    draw.rectangle((0, 8, width - 1, 9), fill=(245, 245, 245))
    _, font = _fonts()
    draw_sharp_text(image, (2, -3), "CINEMARK", (245, 245, 245), bold)
    if width == 128:
        label = "NOW PLAYING"
        box = draw.textbbox((0, 0), label, font=font)
        draw_sharp_text(image, (width - (box[2] - box[0]) - 2, -3), label, (255, 210, 70), font)


def _draw_64(movie):
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (64, 32), (7, 8, 12))
    draw = ImageDraw.Draw(image)
    bold, font = _fonts()
    _draw_header(image, draw, 64, bold)
    draw_sharp_text(image, (2, 8), _abbr_title(movie["title"], 11), (250, 250, 245), font)
    times = [_time_text(show) for show in movie["shows"][:2]]
    widths = [draw.textbbox((0, 0), time, font=font)[2] for time in times]
    x = max(1, (64 - sum(widths) - (6 if len(times) > 1 else 0)) // 2)
    for idx, (time, width) in enumerate(zip(times, widths)):
        draw_sharp_text(image, (x, 18), time, (255, 210, 70) if idx == 0 else (235, 238, 210), font)
        x += width + 6
    return image


def _draw_128(movies):
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (128, 32), (7, 8, 12))
    draw = ImageDraw.Draw(image)
    bold, font = _fonts()
    _draw_header(image, draw, 128, bold)
    for idx, movie in enumerate(movies[:2]):
        y = 8 + idx * 11
        draw_sharp_text(image, (2, y), _fit_text(draw, _abbr_title(movie["title"], 20), font, 62), (250, 250, 245) if idx == 0 else (205, 216, 226), font)
        for time_idx, show in enumerate(movie["shows"][:2]):
            draw_sharp_text(image, (72 if time_idx == 0 else 102, y), _time_text(show), (255, 210, 70) if time_idx == 0 else (235, 238, 210), font)
    return image


def _to_webp(image):
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _message_webp(text, color, width):
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (width, 32), (7, 8, 12))
    draw = ImageDraw.Draw(image)
    bold, font = _fonts()
    _draw_header(image, draw, width, bold)
    text = _fit_text(draw, str(text or "").upper(), font, width - 2)
    box = draw.textbbox((0, 0), text, font=font)
    draw_sharp_text(image, ((width - (box[2] - box[0])) // 2, 14), text, color, font)
    return _to_webp(image)


def _animated(images, dwell):
    if len(images) <= 1:
        return _to_webp(images[0])
    out = BytesIO()
    images[0].save(out, "WEBP", save_all=True, append_images=images[1:], duration=2200, loop=0, lossless=True, quality=100)
    return {"body": out.getvalue(), "dwell_secs": max(dwell, 4), "_no_replay": True}


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    dwell = _int(opts.get("_dwell"), 10, 4, 120)
    try:
        rows = _demo_rows() if opts.get("_demo") else _fetch_showtimes(opts)
    except Exception:
        return _message_webp("CNMK ERR", (238, 80, 80), width)
    movies = _movie_groups(_filter_rows(rows, opts), _int(opts.get("maxMovies"), 3, 1, 6))
    if not movies:
        return _message_webp("NO SHOWS", (160, 170, 180), width)
    if width == 128:
        return _animated([_draw_128(movies[i:i + 2]) for i in range(0, len(movies), 2)], dwell)
    return _animated([_draw_64(movie) for movie in movies], dwell)
