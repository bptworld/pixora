from datetime import datetime
import re

from card_utils import draw_sharp_text
from _universal_common import (
    AMBER, BLUE, PARKS, center, draw_background, draw_globe, draw_twinkles,
    fit_text, fonts, live_items, park_abbr, park_name, parse_dt, safe_text, save_webp,
)

CARD_ID = "universal_showtimes"
CARD_NAME = "Universal Showtimes"
CARD_DETAIL = "Today's Universal showtimes"
CARD_CATEGORY = "Travel"

CARD_OPTIONS = [
    {"key": "parkId", "label": "Park", "type": "select", "default": PARKS[0]["value"], "choices": PARKS},
]

_SAMPLE = [
    {"name": "Universal Mega Movie Parade", "time": "2:00P"},
    {"name": "The Blues Brothers Show", "time": "4:15P"},
    {"name": "CineSational", "time": "9:00P"},
]


def _time_label(value):
    dt = parse_dt(value)
    if not dt:
        return "--"
    label = dt.strftime("%I:%M%p").lstrip("0")
    return label.replace(":00", "").replace("AM", "A").replace("PM", "P")


def _show_rows(items):
    rows = []
    now_by_tz = {}
    for item in items:
        if safe_text(item.get("entityType")).upper() != "SHOW":
            continue
        name = safe_text(item.get("name"))
        if not name:
            continue
        for showtime in item.get("showtimes") or []:
            start = parse_dt(showtime.get("startTime"))
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
    text = safe_text(name, "SHOW").upper()
    words = {
        "UNIVERSAL": "",
        "HOLLYWOOD": "HWOOD",
        "CINESATIONAL": "CINESAT",
        "CINEMA": "CINE",
        "CELEBRATION": "CELEB",
        "CHARACTER": "CHAR",
        "EXPERIENCE": "EXP",
        "SPECTACULAR": "SPEC",
        "PARADE": "PAR",
        "MEET": "MT",
        "WATERWORLD": "WATER",
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


def _draw_frame(rows, park_id, width, offset=0, sparkle_seed=None):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, 32), (4, 8, 18))
    draw = ImageDraw.Draw(img)
    f = fonts()
    draw_background(img, draw)

    label = "SHOWS"
    lw = draw.textbbox((0, 0), label, font=f["text"])[2]
    park = park_name(park_id) if width >= 128 else park_abbr(park_id)
    park = fit_text(draw, park, f["header"], width - lw - 5)
    draw_sharp_text(img, (1, -3), park, AMBER, f["header"])
    draw_sharp_text(img, (width - lw - 1, -3), label, BLUE, f["text"])

    art_w = draw_globe(img, draw, 2, 10, 19) if width >= 128 else 0
    if not rows:
        center(img, draw, "NO SHOWS", 15, (255, 120, 120), f["text"], art_w, width - 1)
    for index, row in enumerate(rows):
        y = 7 + index * 8 - offset
        if y < 7 or y > 23:
            continue
        time = row["time"]
        tw = draw.textbbox((0, 0), time, font=f["text"])[2]
        time_x = width - tw - 1
        x = max(1, art_w)
        name = _fit_name(draw, row["name"], f["text"], max(4, time_x - x - 2), 26 if width >= 128 else 14)
        draw_sharp_text(img, (x, y), name, (235, 240, 255), f["text"])
        draw_sharp_text(img, (time_x, y), time, AMBER, f["text"])

    if sparkle_seed is not None:
        draw_twinkles(img, sparkle_seed)
    return img


def _render_rows(rows, park_id, width):
    visible = 3
    if len(rows) <= visible:
        frames = [_draw_frame(rows, park_id, width, 0, f"{park_id}-{index}") for index in range(6)]
        return save_webp(frames, 500), 12
    max_offset = max(0, (len(rows) - visible) * 8)
    offsets = [0, 0] + list(range(0, max_offset + 1)) + [max_offset] * 4
    frames = [_draw_frame(rows, park_id, width, offset, f"{park_id}-{index}-{offset}") for index, offset in enumerate(offsets)]
    durations = [700, 500] + [120] * (len(offsets) - 6) + [500, 700, 700, 900]
    return save_webp(frames, durations), max(12, int(round(sum(durations) / 1000)))


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    park_id = safe_text(opts.get("parkId"), PARKS[0]["value"])
    try:
        rows = _show_rows(live_items(park_id))
    except Exception:
        rows = list(_SAMPLE)
    body, dwell_secs = _render_rows(rows, park_id, width)
    return {"body": body, "dwell_secs": dwell_secs}
