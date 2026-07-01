from datetime import datetime
from io import BytesIO
from pathlib import Path
import random
import re

from card_utils import draw_sharp_text, fetch_json_request, pixora_local_now, pixora_local_timezone, render_text_webp

CARD_ID = "disney_park_hours"
CARD_NAME = "Disney Park Hours"
CARD_CATEGORY = "Travel"
CARD_DETAIL = "Today's Disney park hours"

_PARKS = [
    {"value": "75ea578a-adc8-4116-a54d-dccb60765ef9", "label": "Magic Kingdom"},
    {"value": "47f90d2c-e191-4239-a466-5892ef59a88b", "label": "EPCOT"},
    {"value": "288747d1-8b4f-4a64-867e-ea7c9b27bad8", "label": "Hollywood Studios"},
    {"value": "1c84a229-8862-4648-9c71-378ddd2c7693", "label": "Animal Kingdom"},
    {"value": "b070cbc5-feaa-4b87-a8c1-f94cca037a18", "label": "Typhoon Lagoon"},
    {"value": "ead53ea5-22e5-4095-9a83-8c29300d7c63", "label": "Blizzard Beach"},
    {"value": "7340550b-c14d-4def-80bb-acdb51d49a66", "label": "Disneyland Park"},
    {"value": "832fcd51-ea19-4e77-85c7-75d5843b127c", "label": "California Adventure"},
]
_DEFAULT_PARK_IDS = ",".join(park["value"] for park in _PARKS[:6])

CARD_OPTIONS = [
    {
        "key": "parkIds",
        "label": "Parks",
        "type": "multiselect",
        "default": _DEFAULT_PARK_IDS,
        "choices": _PARKS,
        "size": 8,
    },
]

_SCHEDULE_URL = "https://api.themeparks.wiki/v1/entity/{park_id}/schedule"
_PARK_ASSETS = {
    "75ea578a-adc8-4116-a54d-dccb60765ef9": "cinderella-castle.png",
    "47f90d2c-e191-4239-a466-5892ef59a88b": "spaceship-earth.png",
    "288747d1-8b4f-4a64-867e-ea7c9b27bad8": "tower-of-terror.png",
    "1c84a229-8862-4648-9c71-378ddd2c7693": "tree-of-life.png",
    "b070cbc5-feaa-4b87-a8c1-f94cca037a18": "typhoon-lagoon.png",
    "ead53ea5-22e5-4095-9a83-8c29300d7c63": "blizzard-beach.png",
    "7340550b-c14d-4def-80bb-acdb51d49a66": "sleeping-beauty-castle.png",
    "832fcd51-ea19-4e77-85c7-75d5843b127c": "california-adventure-wheel.png",
}


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
                "Typhoon Lagoon": "TL",
                "Blizzard Beach": "BB",
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


def _draw_magic_background(img, draw):
    for y in range(32):
        if y < 9:
            color = (26, 14, 52)
        else:
            blend = (y - 9) / 22
            color = (
                round(7 + 7 * (1 - blend)),
                round(8 + 4 * (1 - blend)),
                round(20 + 24 * (1 - blend)),
            )
        draw.line((0, y, img.width - 1, y), fill=color)
    stars = [
        (6, 12, (255, 245, 170), 0.65), (18, 26, (150, 220, 255), 0.5),
        (img.width - 9, 14, (255, 180, 230), 0.55),
        (img.width - 21, 27, (255, 245, 170), 0.6), (img.width // 2, 5, (255, 245, 170), 0.75),
        (12, 21, (255, 180, 230), 0.45), (31, 12, (255, 245, 170), 0.45),
        (img.width - 34, 22, (150, 220, 255), 0.5),
        (img.width // 2 + 18, 29, (255, 245, 170), 0.45),
    ]
    for x, y, color, chance in stars:
        if random.random() > chance:
            continue
        if 0 <= x < img.width:
            draw.point((x, y), fill=color)
            if color == (255, 245, 170) and 1 <= x < img.width - 1:
                draw.point((x + 1, y), fill=(120, 90, 180))
    draw.line((0, 8, img.width - 1, 8), fill=(135, 86, 220))


def _draw_twinkles(img, seed):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    rng = random.Random(seed)
    palette = [(255, 255, 235), (255, 230, 110), (155, 220, 255), (255, 170, 230)]
    zones = [
        (1, 10, img.width - 2, 14),
        (1, 25, img.width - 2, 30),
        (1, 15, 18, 24),
        (img.width - 18, 15, img.width - 2, 24),
    ]
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


def _parse_dt(value):
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except Exception:
        return None


def _time_label(value, compact=False):
    dt = _parse_dt(value)
    if not dt:
        return "--"
    local_tz = pixora_local_timezone()
    if dt.tzinfo and local_tz:
        dt = dt.astimezone(local_tz)
    if compact and dt.minute == 0:
        label = dt.strftime("%I%p").lstrip("0")
    else:
        label = dt.strftime("%I:%M%p").lstrip("0")
    return label.replace(":00", "").replace("AM", "A").replace("PM", "P")


def _today_for_schedule(data):
    for item in data.get("schedule") or []:
        if item.get("type") == "OPERATING":
            dt = _parse_dt(item.get("openingTime"))
            if dt:
                return dt.date().isoformat()
    return pixora_local_now().date().isoformat()


def _hours(park_id):
    data = fetch_json_request(_SCHEDULE_URL.format(park_id=park_id), seconds=1800)
    today = pixora_local_now().date().isoformat()
    dates = {today, _today_for_schedule(data)}
    operating = None
    early = None
    for item in data.get("schedule") or []:
        if item.get("date") not in dates:
            continue
        kind = str(item.get("type") or "").upper()
        desc = str(item.get("description") or "").lower()
        if kind == "OPERATING" and operating is None:
            operating = item
        elif ("early" in desc or kind == "TICKETED_EVENT") and early is None:
            early = item
    return operating, early


def _is_open(operating):
    start = _parse_dt((operating or {}).get("openingTime"))
    end = _parse_dt((operating or {}).get("closingTime"))
    if not start or not end:
        return False
    now = pixora_local_now()
    if start.tzinfo:
        now = now.astimezone(start.tzinfo)
    return start <= now <= end


def _center(image, draw, text, y, color, font, x1=0, x2=None):
    x2 = image.width - 1 if x2 is None else x2
    w = draw.textbbox((0, 0), text, font=font)[2]
    draw_sharp_text(image, (x1 + ((x2 - x1 + 1) - w) // 2, y), text, color, font)


def _park_ids(opts):
    raw = opts.get("parkIds")
    if raw in (None, ""):
        raw = opts.get("parkId") or CARD_OPTIONS[0]["default"]
    if isinstance(raw, (list, tuple, set)):
        values = [_safe_text(item) for item in raw]
    else:
        values = [_safe_text(item) for item in str(raw or "").split(",")]
    allowed = {park["value"] for park in _PARKS}
    result = []
    for value in values:
        if value in allowed and value not in result:
            result.append(value)
    return result or [_PARKS[0]["value"]]


def _draw_hours_image(park_id, operating, early, width, sparkle_seed=None):
    from PIL import Image, ImageDraw, ImageFont

    try:
        header = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        header = font = bold = ImageFont.load_default()

    image = Image.new("RGB", (width, 32), (7, 8, 20))
    draw = ImageDraw.Draw(image)
    _draw_magic_background(image, draw)
    status = "OPEN" if _is_open(operating) else "HOURS"
    sw = draw.textbbox((0, 0), status, font=font)[2]
    park = _park_name(park_id) if width >= 128 else _park_label(park_id)
    park = _fit_text(draw, park, header, width - sw - 5)
    draw_sharp_text(image, (1, -3), park, (255, 218, 84), header)
    draw_sharp_text(image, (width - sw - 1, -3), status, (100, 255, 150) if status == "OPEN" else (120, 225, 255), font)

    if not operating:
        _center(image, draw, "NO HOURS", 13, (255, 120, 120), bold)
    elif width >= 128:
        art_w = _draw_park_art(image, park_id, 1, 9, 27, 22)
        x1 = max(31, art_w)
        hours = f"{_time_label(operating.get('openingTime'))}-{_time_label(operating.get('closingTime'))}"
        _center(image, draw, hours, 10, (245, 250, 255), bold, x1, 127)
        if early:
            early_text = f"EE {_time_label(early.get('openingTime'), True)}-{_time_label(early.get('closingTime'), True)}"
            _center(image, draw, early_text, 22, (255, 210, 80), font, x1, 127)
        else:
            _center(image, draw, "TODAY", 22, (145, 165, 182), font, x1, 127)
    else:
        hours = f"{_time_label(operating.get('openingTime'), True)}-{_time_label(operating.get('closingTime'), True)}"
        _center(image, draw, hours, 9, (245, 250, 255), bold)
        if early:
            early_text = f"EE {_time_label(early.get('openingTime'), True)}"
            _center(image, draw, early_text, 22, (255, 210, 80), font)
        else:
            _center(image, draw, "TODAY", 22, (145, 165, 182), font)

    if sparkle_seed is not None:
        _draw_twinkles(image, sparkle_seed)
    return image


def _render_hours(park_id, operating, early, width):
    image = _draw_hours_image(park_id, operating, early, width)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _render_rotation(frames, duration=500):
    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0,
        lossless=True,
        quality=100,
    )
    return out.getvalue()


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    park_ids = _park_ids(opts)
    frames = []
    try:
        for park_index, park_id in enumerate(park_ids):
            operating, early = _hours(park_id)
            for sparkle_frame in range(6):
                frames.append(_draw_hours_image(park_id, operating, early, width, f"{park_id}-{park_index}-{sparkle_frame}"))
    except Exception:
        return render_text_webp("HOURS ERR", (238, 80, 80))
    if not frames:
        return render_text_webp("NO HOURS", (160, 160, 160))
    if len(park_ids) == 1 and len(frames) == 1:
        out = BytesIO()
        frames[0].save(out, "WEBP", lossless=True, quality=100)
        return out.getvalue()
    return {"body": _render_rotation(frames), "dwell_secs": max(3, len(park_ids) * 3), "_stay": False}
