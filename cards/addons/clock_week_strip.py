from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from card_utils import draw_pixora_bold_number, draw_sharp_text, format_short_date, format_time, pixora_bold_number_size, pixora_local_now

CARD_ID = "clock_week_strip"
CARD_NAME = "Clock Week Strip"
CARD_DETAIL = "Time with weekday strip"
CARD_OPTIONS = [
    {"key": "timezone", "label": "Time Zone", "type": "text", "default": "", "placeholder": "Use global default"},
    {
        "key": "timeFormat",
        "label": "Time Format",
        "type": "select",
        "default": "",
        "choices": [
            {"value": "", "label": "Use global default"},
            {"value": "12", "label": "12-hour"},
            {"value": "24", "label": "24-hour"},
        ],
    },
    {
        "key": "dateFormat",
        "label": "Date Format",
        "type": "select",
        "default": "",
        "choices": [
            {"value": "", "label": "Use global default"},
            {"value": "md", "label": "MM/DD"},
            {"value": "dm", "label": "DD/MM"},
            {"value": "mon_d", "label": "Day M/D"},
        ],
    },
]

_DAYS = ("M", "T", "W", "T", "F", "S", "S")


def _center_text(image, draw, text, y, font, color, x1=0, x2=None):
    x2 = image.width - 1 if x2 is None else x2
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    draw_sharp_text(image, (x1 + ((x2 - x1 + 1) - width) // 2 - bbox[0], y), text, color, font)


def _draw_week_strip(image, draw, x, y, cell_w, today_idx, font, compact=False):
    for idx, label in enumerate(_DAYS):
        x1 = x + idx * cell_w
        x2 = x1 + cell_w - 2
        active = idx == today_idx
        fill = (35, 118, 220) if active else (10, 18, 27)
        outline = (90, 170, 255) if active else (32, 48, 60)
        text = (245, 250, 255) if active else (112, 135, 152)
        draw.rectangle((x1, y, x2, y + 8), fill=fill, outline=outline)
        if not compact or active:
            _center_text(image, draw, label, y - 3, font, text, x1, x2)


def _short_date(now, opts):
    value = str((opts or {}).get("dateFormat") or "").strip()
    if value == "dm":
        return f"{now.day:02d}/{now.month:02d}"
    if value == "mon_d":
        return f"{now.strftime('%a')} {now.month}/{now.day}"
    if value == "md":
        return f"{now.month:02d}/{now.day:02d}"
    return format_short_date(now)


def _date_text(now, opts):
    short_date = _short_date(now, opts)
    if any(ch.isalpha() for ch in short_date):
        return short_date.upper()
    return short_date


def _clock_now(opts):
    tz_name = str((opts or {}).get("timezone") or (opts or {}).get("timeZone") or "").strip()
    if tz_name:
        try:
            return datetime.now(ZoneInfo(tz_name))
        except Exception:
            pass
    return pixora_local_now()


def _clock_time_text(now, opts):
    value = str((opts or {}).get("timeFormat") or "").strip().lower()
    if value in ("24", "24h", "24-hour", "military"):
        return now.strftime("%H:%M")
    if value in ("12", "12h", "12-hour"):
        return now.strftime("%I:%M").lstrip("0")
    return format_time(now)


def _render_64(now, time_text, font, opts):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (64, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    _draw_week_strip(image, draw, 1, 0, 9, now.weekday(), font, compact=True)

    tw, th = pixora_bold_number_size(time_text, scale=2, spacing=1)
    draw_pixora_bold_number(draw, ((64 - tw) // 2, 11), time_text, (235, 247, 255), scale=2, spacing=1)
    date = f"{now.strftime('%a').upper()} {_date_text(now, opts)}"
    _center_text(image, draw, date[:11], 24, font, (92, 185, 255), 0, 63)
    return image


def _render_128(now, time_text, font, opts):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (128, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    _draw_week_strip(image, draw, 2, 1, 10, now.weekday(), font)
    _center_text(image, draw, now.strftime("%B").upper()[:10], 11, font, (112, 135, 152), 2, 70)
    _center_text(image, draw, _date_text(now, opts), 21, font, (92, 185, 255), 2, 70)

    tw, th = pixora_bold_number_size(time_text, scale=2, spacing=2)
    draw.rectangle((73, 0, 127, 31), fill=(2, 8, 16))
    draw.line((72, 3, 72, 28), fill=(32, 54, 70))
    draw_pixora_bold_number(draw, (75 + max(0, (52 - tw) // 2), 9), time_text, (235, 247, 255), scale=2, spacing=2)
    return image


def render(options=None):
    from PIL import ImageFont

    opts = options or {}
    now = _clock_now(opts)
    time_text = _clock_time_text(now, opts)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        font = ImageFont.load_default()

    image = _render_128(now, time_text, font, opts) if opts.get("_target") == "matrixportal-s3-128x32" else _render_64(now, time_text, font, opts)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
