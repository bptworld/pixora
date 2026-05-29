from datetime import datetime, timezone
import math
from io import BytesIO
from card_utils import (
    draw_sharp_text, fetch_airline_logo, fetch_json_request, fetch_opensky, lookup_airline,
    haversine_miles, compass_dir, format_distance_miles, format_speed_knots, render_flight_image, render_text_webp,
)

CARD_ID = "flights_overhead"
CARD_NAME = "Flights Overhead"
CARD_DETAIL = "Live flights above you"
CARD_OPTIONS = [
    {"key": "zipCode",        "label": "ZIP Code",       "type": "text",     "default": "10001", "maxlength": 5, "inputmode": "numeric"},
    {"key": "radiusMiles",    "label": "Radius (mi)",    "type": "number",   "default": "50"},
    {"key": "clientId",       "label": "OpenSky Client ID",     "type": "text",     "default": ""},
    {"key": "clientSecret",   "label": "OpenSky Client Secret", "type": "text",     "default": ""},
]

_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": None}


def _is_wide(options):
    return (options or {}).get("_target") == "matrixportal-s3-128x32"


def _zip_latlon(zip_code):
    loc = fetch_json_request(f"https://api.zippopotam.us/us/{zip_code}", seconds=86400)
    p = loc["places"][0]
    return float(p["latitude"]), float(p["longitude"])


def _bbox(lat, lon, radius_miles):
    dlat = radius_miles / 69.0
    dlon = radius_miles / (69.0 * math.cos(math.radians(lat)))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


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
    draw_sharp_text(image, (tx, 6), row["flight"][:12], (255, 255, 255), bold)
    draw_sharp_text(image, (tx, 13), row["airline"][:16], (100, 190, 255), font)
    alt_str = f"{row['alt_ft'] // 1000}K ft" if row["alt_ft"] >= 1000 else f"{row['alt_ft']}ft"
    spd_str = format_speed_knots(row["speed_kt"]).lower()
    stats = f"{alt_str}  {spd_str}"
    sw = draw.textbbox((0, 0), stats, font=font)[2]
    draw_sharp_text(image, (127 - sw, 6), stats, (200, 230, 255), font)
    line4 = f"{format_distance_miles(row['distance'], 0)} {row['direction']}"
    lw = draw.textbbox((0, 0), line4[:22], font=font)[2]
    draw_sharp_text(image, (127 - lw, 20), line4[:22], (150, 200, 255), font)
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
    draw_sharp_text(image, (airline_x, 5), row["airline"][:10], (100, 190, 255), font)
    alt_str = f"{row['alt_ft'] // 1000}K ft" if row["alt_ft"] >= 1000 else f"{row['alt_ft']}ft"
    spd_str = format_speed_knots(row["speed_kt"]).lower()
    draw_sharp_text(image, (1, 13), alt_str, (200, 230, 255), font)
    sw = draw.textbbox((0, 0), spd_str, font=font)[2]
    draw_sharp_text(image, (63 - sw, 13), spd_str, (200, 230, 255), font)
    line4 = f"{format_distance_miles(row['distance'], 0)} {row['direction']}"
    draw_sharp_text(image, (1, 21), line4[:14], (150, 200, 255), font)
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


def _flight_row(home_lat, home_lon, item, rank):
    dist, s = item
    callsign = (s[1] or "").strip().upper()
    alt_ft = int((s[7] or s[13] or 0) * 3.28084)
    speed_kt = int((s[9] or 0) * 1.94384)
    direction = compass_dir(home_lat, home_lon, float(s[6]), float(s[5]))
    airline = lookup_airline(callsign)
    airline_name = airline[0] if airline else callsign[:8]
    iata = airline[1] if airline else None
    flight_num = (iata + callsign[3:]) if (airline and iata) else callsign
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
    }


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


def render(options=None):
    opts = options or {}
    wide = _is_wide(opts)
    zip_code = (opts.get("zipCode") or "10001").strip()
    radius = max(10, min(500, int(opts.get("radiusMiles") or 50)))
    cid = opts.get("clientId", "")
    csec = opts.get("clientSecret", "")

    lat, lon = _zip_latlon(zip_code)
    lamin, lamax, lomin, lomax = _bbox(lat, lon, radius)

    data = fetch_opensky(_CACHE, cid, csec, lamin, lamax, lomin, lomax)
    states = data.get("states") or []

    flights = []
    for s in states:
        if s[6] is None or s[5] is None or s[8]:
            continue
        dist = haversine_miles(lat, lon, float(s[6]), float(s[5]))
        flights.append((dist, s))
    flights.sort(key=lambda x: x[0])

    if not flights:
        return None

    if wide:
        rows = [_flight_row(lat, lon, item, index + 1) for index, item in enumerate(flights[:5])]
        return _render_wide_list(rows)

    rows = [_flight_row(lat, lon, item, index + 1) for index, item in enumerate(flights[:5])]
    return _render_64_list(rows)
