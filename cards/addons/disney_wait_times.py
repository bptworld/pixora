from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
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
    {"value": "832fcd51-ea19-4e77-85c7-75d5843b127c", "label": "Disneyland Park"},
    {"value": "30ea578c-adc8-4116-a54d-dccb60765ef9", "label": "California Adventure"},
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
            return {"Magic Kingdom": "MK", "Hollywood Studios": "DHS", "Animal Kingdom": "DAK", "Disneyland Park": "DLR"}.get(label, label.upper())
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
    draw.rectangle((0, 0, img.width, 8), fill=(18, 26, 48))
    draw_sharp_text(img, (1, -3), park, (120, 205, 255), fonts["header"])
    label = age or "LIVE"
    box = draw.textbbox((0, 0), label, font=fonts["tiny"])
    draw_sharp_text(img, (img.width - (box[2] - box[0]) - 1, 0), label, (255, 210, 80), fonts["tiny"])


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
    wait = "--" if ride["open"] and ride["wait"] is None else str(ride["wait"]) if ride["open"] else "X"
    wait_label = f"{wait}M" if show_minutes and ride["open"] and wait not in ("--", "X") else wait
    color = (130, 150, 170) if ride["wait"] is None else (120, 255, 150) if ride["wait"] <= 20 else (255, 220, 80) if ride["wait"] <= 50 else (255, 100, 95)
    slot_box = draw.textbbox((0, 0), "888M" if show_minutes else "888", font=fonts["number"])
    slot_w = slot_box[2] - slot_box[0]
    wait_box = draw.textbbox((0, 0), wait_label, font=fonts["number"])
    wait_w = wait_box[2] - wait_box[0]
    wait_x = img.width - slot_w - 1 + max(0, slot_w - wait_w)
    name_w = max(4, img.width - slot_w - 3 - x_offset)
    draw_sharp_text(img, (x_offset, y), _fit_short_name(draw, ride["name"], fonts["text"], name_w, 24), (230, 238, 255), fonts["text"])
    draw_sharp_text(img, (wait_x, y - 1), wait_label, color, fonts["number"])


def _render_card(rides, park, age, width, park_id="", row_offset=0):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, 32), (5, 8, 18))
    draw = ImageDraw.Draw(img)
    fonts = _fonts()
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
        return _to_webp(_render_card(rides, park, age, width, park_id)), 12
    row_step = 8
    max_offset = max(0, (len(rides) - visible_rows) * row_step)
    offsets = [0, 0] + list(range(0, max_offset + 1)) + [max_offset] * 4
    frames = [_render_card(rides, park, age, width, park_id, offset) for offset in offsets]
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
