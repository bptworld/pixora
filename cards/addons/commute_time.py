from datetime import datetime, timedelta, timezone
from io import BytesIO
import urllib.parse
from card_utils import draw_sharp_text, fetch_json_request, format_distance_miles, render_text_webp

CARD_ID = "commute_time"
CARD_NAME = "Commute Time"
CARD_DETAIL = "Drive time estimate"
CARD_OPTIONS = [
    {"key": "origin", "label": "From", "type": "text", "default": "Home address"},
    {"key": "destination", "label": "To", "type": "text", "default": "Work address"},
    {"key": "label", "label": "Label", "type": "text", "default": "COMMUTE", "maxlength": 10},
]

_GEOCODE_CACHE = {}
_ROUTE_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "route": None}


def _is_wide(options):
    return (options or {}).get("_target") == "matrixportal-s3-128x32"


def _render_text_image(text, color, width=64):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (width, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    draw_sharp_text(image, ((width - (bbox[2] - bbox[0])) // 2, (32 - (bbox[3] - bbox[1])) // 2), text, color, font)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _draw_dust(draw, x, y, frame, width=64):
    colors = [(105, 118, 118), (80, 92, 94), (135, 145, 142)]
    for index, (dx, dy) in enumerate(((38, 12), (42, 10), (45, 13), (49, 11), (53, 14))):
        drift = (frame + index * 2) % 4
        px = x + dx + drift
        py = y + dy + ((frame + index) % 2)
        if -1 <= px <= width and 0 <= py <= 31:
            draw.point((px, py), fill=colors[index % len(colors)])
        if index % 2 == 0 and -1 <= px + 1 <= width and 0 <= py <= 31:
            draw.point((px + 1, py), fill=(55, 66, 68))


def _draw_delorean(draw, x, y, frame=0, width=64):
    body = (150, 154, 156)
    mid = (184, 188, 190)
    bright = (230, 234, 236)
    shadow = (74, 78, 82)
    trim = (24, 27, 30)
    glass = (28, 47, 60)

    # Long low DMC-12 wedge. Kept compact so it fits cleanly on 64x32.
    draw.polygon(
        [
            (x + 0, y + 8),
            (x + 9, y + 5),
            (x + 21, y + 4),
            (x + 31, y + 6),
            (x + 36, y + 8),
            (x + 33, y + 10),
            (x + 2, y + 10),
        ],
        fill=body,
        outline=bright,
    )
    draw.polygon([(x + 12, y + 5), (x + 17, y + 2), (x + 26, y + 6), (x + 11, y + 6)], fill=mid, outline=bright)
    draw.polygon([(x + 15, y + 5), (x + 17, y + 3), (x + 22, y + 6), (x + 14, y + 6)], fill=glass)

    # Stainless panel lines, black belt strip, rear louvers.
    draw.line((x + 2, y + 8, x + 35, y + 8), fill=trim)
    draw.line((x + 8, y + 6, x + 32, y + 6), fill=(202, 206, 208))
    draw.line((x + 10, y + 5, x + 7, y + 9), fill=shadow)
    draw.line((x + 21, y + 4, x + 21, y + 10), fill=shadow)
    draw.line((x + 30, y + 6, x + 30, y + 9), fill=shadow)
    for lx in (27, 29, 31, 33):
        draw.line((x + lx, y + 5, x + lx - 2, y + 8), fill=trim)

    draw.point((x + 1, y + 8), fill=(255, 242, 170))
    draw.point((x + 35, y + 8), fill=(255, 60, 60))
    draw.ellipse((x + 7, y + 8, x + 13, y + 14), fill=(8, 10, 12), outline=(210, 216, 218))
    draw.ellipse((x + 25, y + 8, x + 31, y + 14), fill=(8, 10, 12), outline=(210, 216, 218))
    draw.point((x + 10, y + 11), fill=(165, 170, 173))
    draw.point((x + 28, y + 11), fill=(165, 170, 173))
    _draw_dust(draw, x, y, frame, width)


def _draw_base_card(label, minutes, miles, color, font, bold, width=64):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, 32), (3, 8, 11))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, 6), fill=(6, 18, 26))
    title = label[:20 if width == 128 else 10]
    tw = draw.textbbox((0, 0), title, font=font)[2]
    draw_sharp_text(image, (((width - tw) // 2) if width == 128 else 1, -3), title, (115, 205, 255), font)
    text = f"{minutes}min"
    draw_sharp_text(image, (1, 7), text, color, bold)
    miles_text = format_distance_miles(miles, 0)
    mw = draw.textbbox((0, 0), miles_text, font=font)[2]
    draw_sharp_text(image, (width - 1 - mw, 7), miles_text, (180, 200, 205), font)
    draw.line((0, 29, width - 1, 29), fill=(60, 80, 88))
    for x in range(2, width, 12):
        draw.rectangle((x, 27, x + 3, 27), fill=(110, 130, 135))
    return image


def _coords(value):
    text = (value or "").strip()
    if "," in text:
        parts = [p.strip() for p in text.split(",", 1)]
        try:
            return float(parts[0]), float(parts[1])
        except Exception:
            pass

    now = datetime.now(timezone.utc)
    cached = _GEOCODE_CACHE.get(text.lower())
    if cached and cached["expires"] > now:
        return cached["coords"]

    query = urllib.parse.urlencode({"q": text, "format": "json", "limit": "1"})
    data = fetch_json_request(f"https://nominatim.openstreetmap.org/search?{query}", seconds=86400)
    if not data:
        raise ValueError("Address not found")
    coords = (float(data[0]["lat"]), float(data[0]["lon"]))
    _GEOCODE_CACHE[text.lower()] = {"coords": coords, "expires": now + timedelta(days=7)}
    return coords


def _route(origin, destination):
    now = datetime.now(timezone.utc)
    key = f"{origin}:{destination}"
    cached = _ROUTE_CACHE.get("route")
    if cached and cached["key"] == key and _ROUTE_CACHE["expires"] > now:
        return cached
    olat, olon = origin
    dlat, dlon = destination
    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{olon:.6f},{olat:.6f};{dlon:.6f},{dlat:.6f}?overview=false&alternatives=false&steps=false"
    )
    data = fetch_json_request(url, seconds=180)
    route = data["routes"][0]
    result = {
        "key": key,
        "minutes": int(round(route["duration"] / 60.0)),
        "miles": route["distance"] / 1609.344,
    }
    _ROUTE_CACHE["route"] = result
    _ROUTE_CACHE["expires"] = now + timedelta(seconds=180)
    return result


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    width = 128 if _is_wide(opts) else 64
    origin = (opts.get("origin") or "").strip()
    destination = (opts.get("destination") or "").strip()
    label = (opts.get("label") or "COMMUTE").strip().upper()[:10]
    if not origin or not destination or "address" in origin.lower() or "address" in destination.lower():
        return _render_text_image("SET ROUTE", (100, 180, 255), width)

    try:
        route = _route(_coords(origin), _coords(destination))
    except Exception:
        return _render_text_image("ROUTE ERR", (238, 80, 80), width)

    minutes = route["minutes"]
    color = (100, 230, 140) if minutes < 30 else (255, 205, 75) if minutes < 60 else (255, 95, 80)

    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    frames = []
    for frame, x in enumerate(range(width + 2, -40, -4 if width == 128 else -5)):
        image = _draw_base_card(label, minutes, route["miles"], color, font, bold, width)
        draw = ImageDraw.Draw(image)
        _draw_delorean(draw, x, 16, frame, width)
        frames.append(image)
    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=95,
        loop=0,
        lossless=True,
        quality=100,
    )
    return out.getvalue()
