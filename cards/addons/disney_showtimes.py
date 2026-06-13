from datetime import datetime
from io import BytesIO
from pathlib import Path
import random
import re

from card_utils import draw_sharp_text, fetch_json_request, render_text_webp

CARD_ID = "disney_showtimes"
CARD_NAME = "Disney Showtimes"
CARD_CATEGORY = "Travel"
CARD_DETAIL = "Today's Disney showtimes"

_PARKS = [
    {"value": "75ea578a-adc8-4116-a54d-dccb60765ef9", "label": "Magic Kingdom"},
    {"value": "47f90d2c-e191-4239-a466-5892ef59a88b", "label": "EPCOT"},
    {"value": "288747d1-8b4f-4a64-867e-ea7c9b27bad8", "label": "Hollywood Studios"},
    {"value": "1c84a229-8862-4648-9c71-378ddd2c7693", "label": "Animal Kingdom"},
    {"value": "7340550b-c14d-4def-80bb-acdb51d49a66", "label": "Disneyland Park"},
    {"value": "832fcd51-ea19-4e77-85c7-75d5843b127c", "label": "California Adventure"},
]

CARD_OPTIONS = [
    {"key": "parkId", "label": "Park", "type": "select", "default": _PARKS[0]["value"], "choices": _PARKS},
]

_LIVE_URL = "https://api.themeparks.wiki/v1/entity/{park_id}/live"
_PARK_ASSETS = {
    "75ea578a-adc8-4116-a54d-dccb60765ef9": "cinderella-castle.png",
    "47f90d2c-e191-4239-a466-5892ef59a88b": "spaceship-earth.png",
    "288747d1-8b4f-4a64-867e-ea7c9b27bad8": "tower-of-terror.png",
    "1c84a229-8862-4648-9c71-378ddd2c7693": "tree-of-life.png",
    "7340550b-c14d-4def-80bb-acdb51d49a66": "sleeping-beauty-castle.png",
    "832fcd51-ea19-4e77-85c7-75d5843b127c": "california-adventure-wheel.png",
}
_SAMPLE = [
    {"name": "Festival of Fantasy Parade", "time": "3:00P"},
    {"name": "Mickey's Magical Friendship Faire", "time": "5:15P"},
    {"name": "Fireworks", "time": "9:20P"},
]


def _safe_text(value, default=""):
    return re.sub(r"\s+", " ", str(value or default)).strip()


def _park_label(park_id):
    for park in _PARKS:
        if park["value"] == park_id:
            label = park["label"]
            return {
                "Magic Kingdom": "MK",
                "Hollywood Studios": "DHS",
                "Animal Kingdom": "DAK",
                "Disneyland Park": "DLR",
                "California Adventure": "DCA",
            }.get(label, label.upper())
    return "DISNEY"


def _park_name(park_id):
    for park in _PARKS:
        if park["value"] == park_id:
            return park["label"].upper()
    return "DISNEY"


def _fit_text(draw, text, font, max_width):
    text = str(text or "").strip().upper()
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1].rstrip()
    return text


def _asset_path(filename):
    if not filename:
        return None
    here = Path(__file__).resolve()
    roots = [here.parents[2]]
    if len(here.parents) > 3:
        roots.append(here.parents[3])
    for root in roots:
        for rel in (f"graphics/assets/{filename}", f"cloud/graphics/assets/{filename}"):
            path = root / rel
            if path.exists():
                return path
    return None


def _parse_dt(value):
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except Exception:
        return None


def _time_label(value):
    dt = _parse_dt(value)
    if not dt:
        return "--"
    label = dt.strftime("%I:%M%p").lstrip("0")
    return label.replace(":00", "").replace("AM", "A").replace("PM", "P")


def _live_items(park_id):
    data = fetch_json_request(_LIVE_URL.format(park_id=park_id), seconds=180)
    items = data.get("liveData") if isinstance(data, dict) else []
    return items if isinstance(items, list) else []


def _show_rows(items):
    rows = []
    now_by_tz = {}
    for item in items:
        if _safe_text(item.get("entityType")).upper() != "SHOW":
            continue
        name = _safe_text(item.get("name"))
        if not name:
            continue
        for showtime in item.get("showtimes") or []:
            start = _parse_dt(showtime.get("startTime"))
            if not start:
                continue
            key = str(start.tzinfo)
            now = now_by_tz.get(key)
            if now is None:
                now = datetime.now(start.tzinfo)
                now_by_tz[key] = now
            if start.date() != now.date() or start < now:
                continue
            rows.append({"name": name, "time": _time_label(showtime.get("startTime")), "start": start})
    return sorted(rows, key=lambda row: (row["start"], row["name"]))[:6]


def _short_name(name, max_chars=14):
    text = _safe_text(name, "SHOW").upper()
    words = {
        "DISNEY": "",
        "MICKEY": "MICK",
        "MAGICAL": "MAGIC",
        "FRIENDSHIP": "FRIEND",
        "FESTIVAL": "FEST",
        "FANTASY": "FANT",
        "PARADE": "PAR",
        "FIREWORKS": "FIRE",
        "PROJECTIONS": "PROJ",
        "CELEBRATION": "CELEB",
    }
    for src, dest in words.items():
        text = text.replace(src, dest)
    text = re.sub(r"[^A-Z0-9 ]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars].rstrip() if len(text) > max_chars else text


def _fit_name(draw, name, font, max_width, max_chars=26):
    for size in range(max_chars, 0, -1):
        text = _short_name(name, size)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return text
    return _short_name(name, 1)


def _fonts():
    from PIL import ImageFont

    try:
        return {
            "header": ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8),
            "text": ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8),
            "tiny": ImageFont.truetype("assets/fonts/PixelifySans.ttf", 6),
        }
    except Exception:
        font = ImageFont.load_default()
        return {"header": font, "text": font, "tiny": font}


def _draw_magic_background(img, draw):
    for y in range(32):
        if y < 9:
            color = (26, 14, 52)
        else:
            blend = (y - 9) / 22
            color = (round(7 + 7 * (1 - blend)), round(8 + 4 * (1 - blend)), round(20 + 24 * (1 - blend)))
        draw.line((0, y, img.width - 1, y), fill=color)
    draw.line((0, 8, img.width - 1, 8), fill=(135, 86, 220))


def _draw_twinkles(img, seed):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    rng = random.Random(seed)
    palette = [(255, 255, 235), (255, 230, 110), (155, 220, 255), (255, 170, 230)]
    zones = [(1, 10, img.width - 2, 14), (1, 27, img.width - 2, 30), (1, 15, 16, 24), (img.width - 18, 15, img.width - 2, 24)]
    for index in range(8 if img.width >= 128 else 5):
        x1, y1, x2, y2 = zones[index % len(zones)]
        x = rng.randint(x1, x2)
        y = rng.randint(y1, y2)
        color = palette[rng.randrange(len(palette))]
        draw.point((x, y), fill=color)
        if rng.random() < 0.55 and 1 <= x < img.width - 1 and 1 <= y < 31:
            draw.point((x - 1, y), fill=(110, 80, 170))
            draw.point((x + 1, y), fill=(110, 80, 170))
            draw.point((x, y - 1), fill=(110, 80, 170))
            draw.point((x, y + 1), fill=(110, 80, 170))


def _draw_park_art(img, park_id, x, y, max_w, max_h):
    from PIL import Image

    path = _asset_path(_PARK_ASSETS.get(park_id))
    if not path:
        return 0
    try:
        with Image.open(path) as source:
            art = source.convert("RGBA")
            box = art.getbbox()
            if box:
                art = art.crop(box)
            art.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            img.paste(art, (x + max(0, (max_w - art.width) // 2), y + max(0, (max_h - art.height) // 2)), art)
            return max_w + 2
    except Exception:
        return 0


def _draw_frame(rows, park_id, width, offset=0, sparkle_seed=None):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, 32), (7, 8, 20))
    draw = ImageDraw.Draw(img)
    fonts = _fonts()
    _draw_magic_background(img, draw)
    label = "SHOWS"
    label_font = fonts["text"]
    lw = draw.textbbox((0, 0), label, font=label_font)[2]
    park = _park_name(park_id) if width >= 128 else _park_label(park_id)
    park = _fit_text(draw, park, fonts["header"], width - lw - 5)
    draw_sharp_text(img, (1, -3), park, (255, 218, 84), fonts["header"])
    draw_sharp_text(img, (width - lw - 1, -3), label, (120, 225, 255), label_font)
    art_w = _draw_park_art(img, park_id, 1, 9, 27, 22) if width >= 128 else 0
    if not rows:
        text = "NO SHOWS"
        tw = draw.textbbox((0, 0), text, font=fonts["text"])[2]
        draw_sharp_text(img, (art_w + max(0, (width - art_w - tw) // 2), 15), text, (255, 120, 120), fonts["text"])
    for index, row in enumerate(rows):
        y = 7 + index * 8 - offset
        if y < 7 or y > 23:
            continue
        time = row["time"]
        tw = draw.textbbox((0, 0), time, font=fonts["text"])[2]
        time_x = width - tw - 1
        x = max(1, art_w)
        name = _fit_name(draw, row["name"], fonts["text"], max(4, time_x - x - 2), 26 if width >= 128 else 14)
        draw_sharp_text(img, (x, y), name, (235, 240, 255), fonts["text"])
        draw_sharp_text(img, (time_x, y), time, (255, 218, 84), fonts["text"])
    if sparkle_seed is not None:
        _draw_twinkles(img, sparkle_seed)
    return img


def _to_webp(frames, durations):
    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=durations, loop=0, lossless=True, quality=100)
    return out.getvalue()


def _render_rows(rows, park_id, width):
    visible = 3
    if len(rows) <= visible:
        frames = [_draw_frame(rows, park_id, width, 0, f"{park_id}-{index}") for index in range(6)]
        return _to_webp(frames, 500), 12
    max_offset = max(0, (len(rows) - visible) * 8)
    offsets = [0, 0] + list(range(0, max_offset + 1)) + [max_offset] * 4
    frames = [_draw_frame(rows, park_id, width, offset, f"{park_id}-{index}-{offset}") for index, offset in enumerate(offsets)]
    durations = [700, 500] + [120] * (len(offsets) - 6) + [500, 700, 700, 900]
    return _to_webp(frames, durations), max(12, int(round(sum(durations) / 1000)))


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    park_id = _safe_text(opts.get("parkId"), _PARKS[0]["value"])
    try:
        rows = _show_rows(_live_items(park_id))
    except Exception:
        rows = list(_SAMPLE)
    body, dwell_secs = _render_rows(rows, park_id, width)
    return {"body": body, "dwell_secs": dwell_secs}
