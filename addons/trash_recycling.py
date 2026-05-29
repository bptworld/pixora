from datetime import date, datetime, timedelta
from io import BytesIO

from card_utils import draw_sharp_text, format_short_date, render_text_webp

CARD_ID = "trash_recycling"
CARD_NAME = "Trash + Recycling"
CARD_DETAIL = "Weekly and bi-weekly pickup reminder"
CARD_OPTIONS = [
    {
        "key": "trashDay",
        "label": "Trash Day",
        "type": "select",
        "default": "1",
        "choices": [
            {"value": "0", "label": "Monday"},
            {"value": "1", "label": "Tuesday"},
            {"value": "2", "label": "Wednesday"},
            {"value": "3", "label": "Thursday"},
            {"value": "4", "label": "Friday"},
            {"value": "5", "label": "Saturday"},
            {"value": "6", "label": "Sunday"},
            {"value": "off", "label": "No trash reminder"},
        ],
    },
    {
        "key": "recyclingDay",
        "label": "Recycling Day",
        "type": "select",
        "default": "1",
        "choices": [
            {"value": "0", "label": "Monday"},
            {"value": "1", "label": "Tuesday"},
            {"value": "2", "label": "Wednesday"},
            {"value": "3", "label": "Thursday"},
            {"value": "4", "label": "Friday"},
            {"value": "5", "label": "Saturday"},
            {"value": "6", "label": "Sunday"},
            {"value": "off", "label": "No recycling reminder"},
        ],
    },
    {
        "key": "recyclingFrequency",
        "label": "Recycling Schedule",
        "type": "select",
        "default": "biweekly",
        "choices": [
            {"value": "weekly", "label": "Weekly"},
            {"value": "biweekly", "label": "Every other week"},
        ],
    },
    {
        "key": "recyclingAnchorDate",
        "label": "Known Recycling Pickup Date",
        "type": "date",
        "default": "",
    },
    {
        "key": "daysAhead",
        "label": "Show Within Days",
        "type": "number",
        "default": "7",
        "min": 0,
        "max": 14,
    },
]


def _safe_int(value, fallback):
    try:
        return int(value)
    except Exception:
        return fallback


def _next_weekday(today, weekday):
    delta = (weekday - today.weekday()) % 7
    return today + timedelta(days=delta), delta


def _is_recycling_week(pickup_date, anchor_text):
    if not anchor_text:
        return True
    try:
        anchor = date.fromisoformat(anchor_text)
    except Exception:
        return True
    return ((pickup_date - anchor).days // 7) % 2 == 0


def _next_pickups(opts):
    today = date.today()
    pickups = []

    trash_day = str(opts.get("trashDay", "1"))
    if trash_day != "off":
        pickup, days = _next_weekday(today, _safe_int(trash_day, 1))
        pickups.append(("TRASH", pickup, days, (70, 210, 120)))

    recycle_day = str(opts.get("recyclingDay", "1"))
    if recycle_day != "off":
        weekday = _safe_int(recycle_day, 1)
        pickup, days = _next_weekday(today, weekday)
        if opts.get("recyclingFrequency", "biweekly") == "biweekly":
            anchor = (opts.get("recyclingAnchorDate") or "").strip()
            if not _is_recycling_week(pickup, anchor):
                pickup += timedelta(days=14)
                days += 14
        pickups.append(("RECYCLE", pickup, days, (60, 165, 255)))

    try:
        window = max(0, min(14, int(opts.get("daysAhead", 7))))
    except Exception:
        window = 7
    return sorted([p for p in pickups if p[2] <= window], key=lambda item: (item[2], item[0]))


def _when_text(days):
    if days == 0:
        return "TODAY"
    if days == 1:
        return "TOMORROW"
    return f"{days} DAYS"


def _center_text(image, text, y, color, font):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    w = draw.textbbox((0, 0), text, font=font)[2]
    draw_sharp_text(image, ((image.width - w) // 2, y), text, color, font)


def _center_text_in(image, text, x1, x2, y, color, font):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    w = draw.textbbox((0, 0), text, font=font)[2]
    draw_sharp_text(image, (x1 + ((x2 - x1 + 1) - w) // 2, y), text, color, font)


def _text_width_tight(draw, text, font, spacing=-1):
    if not text:
        return 0
    return sum(draw.textbbox((0, 0), ch, font=font)[2] for ch in text) + spacing * (len(text) - 1)


def _center_tight_text_in(image, text, x1, x2, y, color, font, spacing=-1):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    text = str(text or "")
    x = x1 + ((x2 - x1 + 1) - _text_width_tight(draw, text, font, spacing)) // 2
    for ch in text:
        draw_sharp_text(image, (x, y), ch, color, font)
        x += draw.textbbox((0, 0), ch, font=font)[2] + spacing


def _draw_barrel(draw, x, y, color):
    shade = tuple(max(0, int(channel * 0.55)) for channel in color)
    highlight = tuple(min(255, int(channel * 1.25)) for channel in color)
    draw.rectangle((x + 1, y + 3, x + 9, y + 14), fill=color, outline=highlight)
    draw.line((x, y + 2, x + 10, y + 2), fill=highlight)
    draw.line((x + 2, y + 6, x + 8, y + 6), fill=shade)
    draw.line((x + 2, y + 10, x + 8, y + 10), fill=shade)
    draw.point((x + 3, y + 16), fill=(80, 95, 105))
    draw.point((x + 7, y + 16), fill=(80, 95, 105))


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    pickups = _next_pickups(opts)
    if not pickups:
        return None

    image = Image.new("RGB", (width, 32), (0, 4, 7))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    if len(pickups) >= 2 and pickups[0][2] == pickups[1][2]:
        title = "TRASH+REC"
        color = (90, 225, 205)
        days = pickups[0][2]
        barrels = [(2, (60, 165, 255)), (14, (70, 210, 120))]
        draw.rectangle((0, 0, width - 1, 8), fill=(4, 18, 20))
        _center_text(image, title, -3, color, bold)
        _center_tight_text_in(image, _when_text(days), 27, width - 1, 9, (245, 250, 255), bold)
        _center_text_in(image, format_short_date(pickups[0][1]).upper(), 27, width - 1, 18, (160, 190, 210), font)
    else:
        name, pickup, days, color = pickups[0]
        barrel_color = (70, 210, 120) if name == "RECYCLE" else (60, 165, 255)
        barrels = [(3, barrel_color)]
        draw.rectangle((0, 0, width - 1, 8), fill=(5, 18, 15))
        _center_text(image, name, -3, barrel_color, bold)
        _center_tight_text_in(image, _when_text(days), 15, width - 1, 9, (245, 250, 255), bold)
        _center_text_in(image, format_short_date(pickup).upper(), 15, width - 1, 18, (160, 190, 210), font)

    for x, barrel_color in barrels:
        _draw_barrel(draw, x, 12, barrel_color)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

