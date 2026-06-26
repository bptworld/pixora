from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import random
import re

from card_utils import draw_sharp_text, fetch_json_request

CARD_ID = "disney_wait_times"
CARD_NAME = "Disney Wait Times"
CARD_DETAIL = "Live Disney park waits"
CARD_CATEGORY = "Travel"

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

CARD_OPTIONS = [
    {"key": "parkId", "label": "Park", "type": "select", "default": _PARKS[0]["value"], "choices": _PARKS},
    {
        "key": "favoriteRide",
        "label": "Attractions",
        "type": "multiselect",
        "default": "",
        "size": 7,
        "choices": [{"value": "", "label": "Any attraction"}],
        "dynamicChoices": {"dependsOn": ["parkId"]},
    },
    {
        "key": "mode",
        "label": "Display",
        "type": "select",
        "default": "top",
        "choices": [
            {"value": "top", "label": "Longest waits"},
            {"value": "short", "label": "Shortest open waits"},
            {"value": "favorite", "label": "Selected attractions"},
        ],
    },
]

_LIVE_URL = "https://api.themeparks.wiki/v1/entity/{park_id}/live"
_CHILDREN_URL = "https://api.themeparks.wiki/v1/entity/{park_id}/children"
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
_SAMPLE = [
    {"id": "sample-tiana", "entityType": "ATTRACTION", "name": "Tiana's Bayou Adventure", "status": "OPERATING", "queue": {"STANDBY": {"waitTime": 75}}},
    {"id": "sample-tron", "entityType": "ATTRACTION", "name": "TRON Lightcycle / Run", "status": "OPERATING", "queue": {"STANDBY": {"waitTime": 55}}},
    {"id": "sample-space", "entityType": "ATTRACTION", "name": "Space Mountain", "status": "OPERATING", "queue": {"STANDBY": {"waitTime": 40}}},
]


def _safe_text(value, default=""):
    return re.sub(r"\s+", " ", str(value or default)).strip()


def _selected_values(value):
    if isinstance(value, (list, tuple, set)):
        raw = value
    else:
        raw = str(value or "").split(",")
    values = []
    for item in raw:
        text = _safe_text(item).lower()
        if text:
            values.append(text)
    return values


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


def _wait_time(item):
    queue = item.get("queue") or {}
    standby = queue.get("STANDBY") or queue.get("standby") or {}
    value = standby.get("waitTime") if isinstance(standby, dict) else None
    try:
        return int(value)
    except Exception:
        return None


def _short_name(name, max_chars=12):
    text = _safe_text(name, "RIDE").upper()
    words = {
        "ADVENTURE": "ADV",
        "MOUNTAIN": "MTN",
        "RAILWAY": "RR",
        "LIGHTCYCLE": "LIGHT",
        "PIRATES": "PIR",
        "CARIBBEAN": "CARIB",
        "HAUNTED": "HAUNT",
        "MANSION": "MANS",
        "EXPEDITION": "EXP",
        "GUARDIANS": "GOTG",
    }
    for src, dest in words.items():
        text = text.replace(src, dest)
    text = re.sub(r"[^A-Z0-9 ]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip()


def _fit_short_name(draw, name, font, max_width, max_chars=24):
    max_width = max(1, int(max_width or 1))
    for size in range(max_chars, 0, -1):
        text = _short_name(name, size)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return text
    return _short_name(name, 1)


def _live_items(park_id):
    data = fetch_json_request(_LIVE_URL.format(park_id=park_id), seconds=180)
    items = data.get("liveData") if isinstance(data, dict) else []
    if not isinstance(items, list):
        return []
    return items


def _child_items(park_id):
    data = fetch_json_request(_CHILDREN_URL.format(park_id=park_id), seconds=86400)
    items = data.get("children") if isinstance(data, dict) else []
    if not isinstance(items, list):
        return []
    return items


def _attraction_choice_items(park_id):
    items = _child_items(park_id)
    attractions = []
    for item in items:
        if _safe_text(item.get("entityType")).upper() != "ATTRACTION":
            continue
        item_id = _safe_text(item.get("id"))
        name = _safe_text(item.get("name"))
        if item_id and name:
            attractions.append({"value": item_id, "label": name})
    return sorted(attractions, key=lambda item: item["label"].lower())


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


def card_option_choices(option_key, options=None):
    if option_key != "favoriteRide":
        return []
    park_id = _safe_text((options or {}).get("parkId"), _PARKS[0]["value"])
    try:
        choices = _attraction_choice_items(park_id)
    except Exception:
        choices = [{"value": item["id"], "label": item["name"]} for item in _SAMPLE]
    return [{"value": "", "label": "Any attraction"}] + choices


def _attractions_with_waits(items):
    rides = []
    for item in items:
        if _safe_text(item.get("entityType")).upper() not in ("", "ATTRACTION"):
            continue
        wait = _wait_time(item)
        status = _safe_text(item.get("status")).upper()
        name = _safe_text(item.get("name"))
        if not name:
            continue
        rides.append({"id": _safe_text(item.get("id")), "name": name, "wait": wait, "open": status == "OPERATING", "status": status})
    return rides


def _pick_rides(rides, mode, favorites):
    favorites = _selected_values(favorites)
    if mode == "favorite" and favorites:
        matches = []
        seen = set()
        for favorite in favorites:
            exact = [ride for ride in rides if favorite == ride.get("id", "").lower()]
            if not exact:
                exact = [ride for ride in rides if favorite in ride["name"].lower()]
            for ride in exact:
                key = ride.get("id") or ride["name"]
                if key in seen:
                    continue
                matches.append(ride)
                seen.add(key)
        if matches:
            return matches
    open_rides = [ride for ride in rides if ride["open"] and ride["wait"] is not None]
    if mode == "short":
        positive = [ride for ride in open_rides if ride["wait"] > 0]
        return sorted(positive or open_rides, key=lambda ride: (ride["wait"], ride["name"]))[:5]
    waited_rides = [ride for ride in rides if ride["wait"] is not None]
    return sorted(open_rides or waited_rides, key=lambda ride: (-ride["wait"], ride["name"]))[:5]


def _status_age(items):
    latest = None
    for item in items:
        raw = item.get("lastUpdated")
        if not raw:
            continue
        try:
            stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except Exception:
            continue
        if latest is None or stamp > latest:
            latest = stamp
    if not latest:
        return ""
    mins = max(0, int((datetime.now(timezone.utc) - latest.astimezone(timezone.utc)).total_seconds() // 60))
    return f"{mins}M"


def _fonts():
    from PIL import ImageFont

    try:
        return {
            "header": ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8),
            "tiny": ImageFont.truetype("assets/fonts/PixelifySans.ttf", 6),
            "text": ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8),
            "number": ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8),
        }
    except Exception:
        font = ImageFont.load_default()
        return {"header": font, "tiny": font, "text": font, "number": font}


def _draw_header(img, draw, fonts, park, age):
    draw.rectangle((0, 0, img.width, 6), fill=(26, 14, 52))
    if random.random() < 0.75:
        draw.point((img.width // 2, 2), fill=(255, 245, 170))
        draw.point((img.width // 2 + 1, 2), fill=(210, 180, 255))
    if img.width >= 128:
        if random.random() < 0.55:
            draw.point((img.width // 2 - 18, 5), fill=(190, 230, 255))
        if random.random() < 0.55:
            draw.point((img.width // 2 + 24, 4), fill=(255, 180, 230))
            draw.point((img.width // 2 + 25, 4), fill=(255, 245, 170))
    draw_sharp_text(img, (1, -3), park, (255, 218, 84), fonts["header"])
    label = age or "LIVE"
    box = draw.textbbox((0, 0), label, font=fonts["tiny"])
    draw_sharp_text(img, (img.width - (box[2] - box[0]) - 1, 0), label, (120, 225, 255), fonts["tiny"])
    draw.line((0, 8, img.width - 1, 8), fill=(135, 86, 220))


def _draw_magic_background(img, draw):
    for y in range(32):
        if y < 9:
            continue
        blend = (y - 9) / 22
        color = (
            round(7 + 6 * (1 - blend)),
            round(8 + 4 * (1 - blend)),
            round(20 + 22 * (1 - blend)),
        )
        draw.line((0, y, img.width - 1, y), fill=color)
    for x, y, color, chance in [
        (8, 13, (255, 245, 170), 0.65),
        (13, 21, (255, 180, 230), 0.45),
        (20, 28, (150, 220, 255), 0.5),
        (31, 11, (255, 245, 170), 0.45),
        (img.width - 7, 16, (255, 180, 230), 0.55),
        (img.width - 12, 23, (150, 220, 255), 0.5),
        (img.width - 19, 27, (255, 245, 170), 0.6),
        (img.width // 2 + 3, 30, (255, 245, 170), 0.45),
    ]:
        if random.random() > chance:
            continue
        if 0 <= x < img.width:
            draw.point((x, y), fill=color)
            if color == (255, 245, 170) and 1 <= x < img.width - 1:
                draw.point((x + 1, y), fill=(120, 90, 180))


def _draw_twinkles(img, seed):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    rng = random.Random(seed)
    palette = [(255, 255, 235), (255, 230, 110), (155, 220, 255), (255, 170, 230)]
    zones = [
        (1, 10, img.width - 2, 13),
        (1, 27, img.width - 2, 30),
        (1, 14, 13, 25),
        (img.width - 14, 14, img.width - 2, 25),
    ]
    for index in range(7 if img.width >= 128 else 5):
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


def _draw_ride_row(img, y, ride, fonts, wide=False, x_offset=1, show_minutes=True):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    status = _safe_text(ride.get("status")).upper()
    if ride["open"]:
        wait = "--" if ride["wait"] is None else str(ride["wait"])
        wait_label = f"{wait}M" if show_minutes and wait != "--" else wait
    elif "DOWN" in status:
        wait_label = "DOWN"
    elif "REFURB" in status:
        wait_label = "REFURB" if wide else "REF"
    elif status:
        wait_label = "CLOSED" if wide else "CLSD"
    else:
        wait_label = "CLSD"
    color = (
        (255, 100, 95) if not ride["open"]
        else (130, 150, 170) if ride["wait"] is None
        else (120, 255, 150) if ride["wait"] <= 20
        else (255, 220, 80) if ride["wait"] <= 50
        else (255, 100, 95)
    )
    slot_hint = "CLOSED" if wide else "CLSD"
    slot_box = draw.textbbox((0, 0), slot_hint, font=fonts["number"])
    slot_w = slot_box[2] - slot_box[0]
    wait_box = draw.textbbox((0, 0), wait_label, font=fonts["number"])
    wait_w = wait_box[2] - wait_box[0]
    wait_x = img.width - slot_w - 1 + max(0, slot_w - wait_w)
    name_w = max(4, img.width - slot_w - 3 - x_offset)
    draw_sharp_text(img, (x_offset, y), _fit_short_name(draw, ride["name"], fonts["text"], name_w, 24), (230, 238, 255), fonts["text"])
    draw_sharp_text(img, (wait_x, y - 1), wait_label, color, fonts["number"])


def _render_card(rides, park, age, width, park_id="", row_offset=0, sparkle_seed=None):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, 32), (7, 8, 20))
    draw = ImageDraw.Draw(img)
    fonts = _fonts()
    _draw_magic_background(img, draw)
    _draw_header(img, draw, fonts, park, age)
    art_w = _draw_park_art(img, park_id, 1, 9, 27, 22) if width >= 128 else 0
    if not rides:
        text = "NO WAITS"
        box = draw.textbbox((0, 0), text, font=fonts["text"])
        x = art_w + max(0, ((width - art_w) - (box[2] - box[0])) // 2)
        draw_sharp_text(img, (x, 15), text, (255, 120, 120), fonts["text"])
        return img
    for index, ride in enumerate(rides):
        y = 6 + index * 8 - row_offset
        if 6 <= y <= 22:
            _draw_ride_row(img, y, ride, fonts, wide=width >= 128, x_offset=max(1, art_w), show_minutes=width >= 128)
    if sparkle_seed is not None:
        _draw_twinkles(img, sparkle_seed)
    return img


def _to_webp(img, append_images=None, durations=None):
    out = BytesIO()
    if append_images:
        img.save(out, "WEBP", save_all=True, append_images=append_images, duration=durations or 160, loop=0, lossless=True, quality=100)
    else:
        img.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _render_body(rides, park, age, width, park_id):
    visible_rows = 3
    if len(rides) <= visible_rows:
        frames = [_render_card(rides, park, age, width, park_id, 0, f"{park}-{index}") for index in range(6)]
        return _to_webp(frames[0], frames[1:], 500), 12
    row_step = 8
    max_offset = max(0, (len(rides) - visible_rows) * row_step)
    offsets = [0, 0] + list(range(0, max_offset + 1)) + [max_offset] * 4
    frames = [_render_card(rides, park, age, width, park_id, offset, f"{park}-{index}-{offset}") for index, offset in enumerate(offsets)]
    durations = [700, 500] + [120] * (len(offsets) - 6) + [500, 700, 700, 900]
    total_secs = max(12, int(round(sum(durations) / 1000)))
    return _to_webp(frames[0], frames[1:], durations), total_secs


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    park_id = _safe_text(opts.get("parkId"), _PARKS[0]["value"])
    mode = _safe_text(opts.get("mode"), "top")
    favorite = opts.get("favoriteRide")

    try:
        items = _live_items(park_id)
    except Exception:
        items = _SAMPLE
    rides = _pick_rides(_attractions_with_waits(items), mode, favorite)
    if not rides and items is not _SAMPLE:
        rides = _pick_rides(_attractions_with_waits(_SAMPLE), "top", "")
    body, dwell_secs = _render_body(rides, _park_label(park_id), _status_age(items), width, park_id)
    return {"body": body, "dwell_secs": dwell_secs}
