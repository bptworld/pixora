from datetime import datetime

from card_utils import draw_sharp_text, fetch_json_request, render_text_webp
from _universal_common import (
    AMBER, BLUE, PARKS, SCHEDULE_URL, center, draw_background, draw_globe, draw_twinkles,
    fit_text, fonts, park_abbr, park_name, parse_dt, safe_text, save_webp, time_label,
)

CARD_ID = "universal_park_hours"
CARD_NAME = "Universal Park Hours"
CARD_DETAIL = "Today's Universal park hours"
CARD_CATEGORY = "Travel"

_DEFAULT_PARK_IDS = ",".join(park["value"] for park in PARKS[:4])

CARD_OPTIONS = [
    {
        "key": "parkIds",
        "label": "Parks",
        "type": "multiselect",
        "default": _DEFAULT_PARK_IDS,
        "choices": PARKS,
        "size": 5,
    },
]


def _today_for_schedule(data):
    for item in data.get("schedule") or []:
        if safe_text(item.get("type")).upper() == "OPERATING":
            dt = parse_dt(item.get("openingTime"))
            if dt:
                return dt.date().isoformat()
    return datetime.now().date().isoformat()


def _hours(park_id):
    data = fetch_json_request(SCHEDULE_URL.format(park_id=park_id), seconds=1800)
    today = datetime.now().date().isoformat()
    dates = {today, _today_for_schedule(data)}
    operating = None
    early = None
    for item in data.get("schedule") or []:
        if item.get("date") not in dates:
            continue
        kind = safe_text(item.get("type")).upper()
        desc = safe_text(item.get("description")).lower()
        if kind == "OPERATING" and operating is None:
            operating = item
        elif ("early" in desc or kind == "TICKETED_EVENT") and early is None:
            early = item
    return operating, early


def _is_open(operating):
    start = parse_dt((operating or {}).get("openingTime"))
    end = parse_dt((operating or {}).get("closingTime"))
    if not start or not end:
        return False
    return start <= datetime.now(start.tzinfo) <= end


def _park_ids(opts):
    raw = opts.get("parkIds")
    if raw in (None, ""):
        raw = opts.get("parkId") or CARD_OPTIONS[0]["default"]
    values = raw if isinstance(raw, (list, tuple, set)) else str(raw or "").split(",")
    allowed = {park["value"] for park in PARKS}
    result = []
    for value in values:
        value = safe_text(value)
        if value in allowed and value not in result:
            result.append(value)
    return result or [PARKS[0]["value"]]


def _draw_hours_image(park_id, operating, early, width, sparkle_seed=None):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, 32), (4, 8, 18))
    draw = ImageDraw.Draw(image)
    f = fonts()
    draw_background(image, draw)

    status = "OPEN" if _is_open(operating) else "HOURS"
    sw = draw.textbbox((0, 0), status, font=f["text"])[2]
    park = park_name(park_id) if width >= 128 else park_abbr(park_id)
    park = fit_text(draw, park, f["header"], width - sw - 5)
    draw_sharp_text(image, (1, -3), park, AMBER, f["header"])
    draw_sharp_text(image, (width - sw - 1, -3), status, (120, 255, 150) if status == "OPEN" else BLUE, f["text"])

    if not operating:
        center(image, draw, "NO HOURS", 14, (255, 120, 120), f["text"])
    elif width >= 128:
        art_w = draw_globe(image, draw, 2, 10, 19)
        x1 = max(25, art_w)
        hours = f"{time_label(operating.get('openingTime'))}-{time_label(operating.get('closingTime'))}"
        center(image, draw, hours, 10, (245, 250, 255), f["header"], x1, width - 1)
        if early:
            early_text = f"EARLY {time_label(early.get('openingTime'), True)}-{time_label(early.get('closingTime'), True)}"
            center(image, draw, early_text, 22, AMBER, f["text"], x1, width - 1)
        else:
            center(image, draw, "TODAY", 22, (145, 165, 182), f["text"], x1, width - 1)
    else:
        hours = f"{time_label(operating.get('openingTime'), True)}-{time_label(operating.get('closingTime'), True)}"
        center(image, draw, hours, 9, (245, 250, 255), f["header"])
        if early:
            center(image, draw, f"EARLY {time_label(early.get('openingTime'), True)}", 22, AMBER, f["text"])
        else:
            center(image, draw, "TODAY", 22, (145, 165, 182), f["text"])

    if sparkle_seed is not None:
        draw_twinkles(image, sparkle_seed)
    return image


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
    return {"body": save_webp(frames, 500), "dwell_secs": max(3, len(park_ids) * 3), "_stay": False}
