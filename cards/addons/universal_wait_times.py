from datetime import datetime, timezone
from io import BytesIO
import re

from card_utils import draw_sharp_text
from _universal_common import (
    AMBER, BLUE, PARKS, center, child_items, draw_background, draw_globe, draw_twinkles,
    fonts, live_items, park_abbr, safe_text, save_webp,
)

CARD_ID = "universal_wait_times"
CARD_NAME = "Universal Wait Times"
CARD_DETAIL = "Live Universal park waits"
CARD_CATEGORY = "Travel"

CARD_OPTIONS = [
    {"key": "parkId", "label": "Park", "type": "select", "default": PARKS[0]["value"], "choices": PARKS},
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

_SAMPLE = [
    {"id": "sample-veloci", "entityType": "ATTRACTION", "name": "Jurassic World VelociCoaster", "status": "OPERATING", "queue": {"STANDBY": {"waitTime": 65}}},
    {"id": "sample-hagrid", "entityType": "ATTRACTION", "name": "Hagrid's Magical Creatures Motorbike Adventure", "status": "OPERATING", "queue": {"STANDBY": {"waitTime": 80}}},
    {"id": "sample-minion", "entityType": "ATTRACTION", "name": "Despicable Me Minion Mayhem", "status": "OPERATING", "queue": {"STANDBY": {"waitTime": 35}}},
]


def _selected_values(value):
    raw = value if isinstance(value, (list, tuple, set)) else str(value or "").split(",")
    return [safe_text(item).lower() for item in raw if safe_text(item)]


def _wait_time(item):
    queue = item.get("queue") or {}
    standby = queue.get("STANDBY") or queue.get("standby") or {}
    value = standby.get("waitTime") if isinstance(standby, dict) else None
    try:
        return int(value)
    except Exception:
        return None


def _short_name(name, max_chars=12):
    text = safe_text(name, "RIDE").upper()
    words = {
        "ADVENTURE": "ADV",
        "ATTRACTION": "ATTR",
        "JURASSIC": "JUR",
        "VELOCICOASTER": "VELOCI",
        "MOTORBIKE": "BIKE",
        "FORBIDDEN": "FORB",
        "DESPICABLE": "DESP",
        "TRANSFORMERS": "XFORMERS",
        "HOLLYWOOD": "HWOOD",
    }
    for src, dest in words.items():
        text = text.replace(src, dest)
    text = re.sub(r"[^A-Z0-9 ]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars].rstrip() if len(text) > max_chars else text


def _fit_short_name(draw, name, font, max_width, max_chars=24):
    for size in range(max_chars, 0, -1):
        text = _short_name(name, size)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return text
    return _short_name(name, 1)


def card_option_choices(option_key, options=None):
    if option_key != "favoriteRide":
        return []
    park_id = safe_text((options or {}).get("parkId"), PARKS[0]["value"])
    try:
        items = child_items(park_id)
        choices = []
        for item in items:
            if safe_text(item.get("entityType")).upper() != "ATTRACTION":
                continue
            item_id = safe_text(item.get("id"))
            name = safe_text(item.get("name"))
            if item_id and name:
                choices.append({"value": item_id, "label": name})
        choices = sorted(choices, key=lambda item: item["label"].lower())
    except Exception:
        choices = [{"value": item["id"], "label": item["name"]} for item in _SAMPLE]
    return [{"value": "", "label": "Any attraction"}] + choices


def _attractions_with_waits(items):
    rides = []
    for item in items:
        if safe_text(item.get("entityType")).upper() not in ("", "ATTRACTION"):
            continue
        status = safe_text(item.get("status")).upper()
        name = safe_text(item.get("name"))
        if name:
            rides.append({"id": safe_text(item.get("id")), "name": name, "wait": _wait_time(item), "open": status == "OPERATING", "status": status})
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
                if key not in seen:
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


def _draw_header(img, draw, f, park, age):
    draw_sharp_text(img, (1, -3), park, AMBER, f["header"])
    label = age or "LIVE"
    box = draw.textbbox((0, 0), label, font=f["tiny"])
    draw_sharp_text(img, (img.width - (box[2] - box[0]) - 1, 0), label, BLUE, f["tiny"])


def _draw_ride_row(img, y, ride, f, x_offset=1, show_minutes=True):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    status = safe_text(ride.get("status")).upper()
    if ride["open"]:
        wait = "--" if ride["wait"] is None else str(ride["wait"])
        wait_label = f"{wait}M" if show_minutes and wait != "--" else wait
    elif "DOWN" in status:
        wait_label = "DOWN"
    elif "REFURB" in status:
        wait_label = "REFURB" if show_minutes else "REF"
    else:
        wait_label = "CLOSED" if show_minutes else "CLSD"
    color = (
        (255, 100, 95) if not ride["open"]
        else (130, 150, 170) if ride["wait"] is None
        else (120, 255, 150) if ride["wait"] <= 20
        else (255, 220, 80) if ride["wait"] <= 50
        else (255, 100, 95)
    )
    slot_hint = "CLOSED" if show_minutes else "CLSD"
    slot_w = draw.textbbox((0, 0), slot_hint, font=f["number"])[2]
    wait_w = draw.textbbox((0, 0), wait_label, font=f["number"])[2]
    wait_x = img.width - slot_w - 1 + max(0, slot_w - wait_w)
    name_w = max(4, img.width - slot_w - 3 - x_offset)
    draw_sharp_text(img, (x_offset, y), _fit_short_name(draw, ride["name"], f["text"], name_w, 24), (230, 238, 255), f["text"])
    draw_sharp_text(img, (wait_x, y - 1), wait_label, color, f["number"])


def _render_card(rides, park, age, width, row_offset=0, sparkle_seed=None):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, 32), (4, 8, 18))
    draw = ImageDraw.Draw(img)
    f = fonts()
    draw_background(img, draw)
    _draw_header(img, draw, f, park, age)
    art_w = draw_globe(img, draw, 1, 10, 20) if width >= 128 else 0
    if not rides:
        center(img, draw, "NO WAITS", 15, (255, 120, 120), f["text"], art_w, width - 1)
    for index, ride in enumerate(rides):
        y = 6 + index * 8 - row_offset
        if 6 <= y <= 22:
            _draw_ride_row(img, y, ride, f, max(1, art_w), width >= 128)
    if sparkle_seed is not None:
        draw_twinkles(img, sparkle_seed)
    return img


def _render_body(rides, park, age, width):
    if len(rides) <= 3:
        frames = [_render_card(rides, park, age, width, 0, f"{park}-{index}") for index in range(6)]
        return save_webp(frames, 500), 12
    max_offset = max(0, (len(rides) - 3) * 8)
    offsets = [0, 0] + list(range(0, max_offset + 1)) + [max_offset] * 4
    frames = [_render_card(rides, park, age, width, offset, f"{park}-{index}-{offset}") for index, offset in enumerate(offsets)]
    durations = [700, 500] + [120] * (len(offsets) - 6) + [500, 700, 700, 900]
    return save_webp(frames, durations), max(12, int(round(sum(durations) / 1000)))


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    park_id = safe_text(opts.get("parkId"), PARKS[0]["value"])
    mode = safe_text(opts.get("mode"), "top")
    try:
        items = live_items(park_id)
    except Exception:
        items = _SAMPLE
    rides = _pick_rides(_attractions_with_waits(items), mode, opts.get("favoriteRide"))
    if not rides and items is not _SAMPLE:
        rides = _pick_rides(_attractions_with_waits(_SAMPLE), "top", "")
    body, dwell_secs = _render_body(rides, park_abbr(park_id), _status_age(items), width)
    return {"body": body, "dwell_secs": dwell_secs}
