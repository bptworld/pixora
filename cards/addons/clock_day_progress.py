from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from card_utils import draw_pixora_bold_number, draw_sharp_text, format_short_date, format_time, pixora_bold_number_size, pixora_local_now

CARD_ID = "clock_day_progress"
CARD_NAME = "Clock Day Progress"
CARD_DETAIL = "Time with day progress"
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


def _center_text(image, draw, text, y, font, color, x1=0, x2=None):
    x2 = image.width - 1 if x2 is None else x2
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    draw_sharp_text(image, (x1 + ((x2 - x1 + 1) - width) // 2 - bbox[0], y), text, color, font)


def _draw_time(draw, x, y, text, color, scale=2, spacing=1):
    draw_pixora_bold_number(draw, (x, y), text, color, scale=scale, spacing=spacing)


def _day_progress(now):
    elapsed = now.hour * 3600 + now.minute * 60 + now.second
    return max(0.0, min(1.0, elapsed / 86400.0))


def _short_date(now, opts):
    value = str((opts or {}).get("dateFormat") or "").strip()
    if value == "dm":
        return f"{now.day:02d}/{now.month:02d}"
    if value == "mon_d":
        return f"{now.strftime('%a')} {now.month}/{now.day}"
    if value == "md":
        return f"{now.month:02d}/{now.day:02d}"
    return format_short_date(now)


def _date_label(now, opts):
    short_date = _short_date(now, opts)
    if any(ch.isalpha() for ch in short_date):
        return short_date.upper()
    return f"{now.strftime('%a').upper()} {short_date}"


def _draw_progress(draw, box, progress, fill=(62, 224, 150)):
    x1, y1, x2, y2 = box
    draw.rectangle(box, outline=(40, 58, 70))
    inner_w = max(0, x2 - x1 - 1)
    filled = int(round(inner_w * progress))
    if filled > 0:
        draw.rectangle((x1 + 1, y1 + 1, x1 + filled, y2 - 1), fill=fill)
    for tick in (0.25, 0.5, 0.75):
        x = x1 + 1 + int(inner_w * tick)
        draw.line((x, y1 + 1, x, y2 - 1), fill=(12, 20, 25))


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


def _render_64(now, time_text, font):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (64, 32), (0, 4, 8))
    draw = ImageDraw.Draw(image)
    progress = _day_progress(now)
    pct = f"{int(progress * 100):02d}%"
    weekday = now.strftime("%a").upper()

    draw.rectangle((0, 0, 63, 7), fill=(5, 15, 22))
    draw_sharp_text(image, (1, -4), weekday, (150, 178, 196), font)
    pct_w = draw.textbbox((0, 0), pct, font=font)[2]
    draw_sharp_text(image, (63 - pct_w, -4), pct, (62, 224, 150), font)

    tw, th = pixora_bold_number_size(time_text, scale=2, spacing=1)
    _draw_time(draw, (64 - tw) // 2, 10, time_text, (235, 247, 255), scale=2, spacing=1)
    _draw_progress(draw, (2, 28, 61, 31), progress)
    return image


def _render_128(now, time_text, font, opts):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (128, 32), (0, 4, 8))
    draw = ImageDraw.Draw(image)
    progress = _day_progress(now)
    pct = f"{int(progress * 100)}%"
    date = _date_label(now, opts)

    tw, th = pixora_bold_number_size(time_text, scale=3, spacing=2)
    _draw_time(draw, 2, 5, time_text, (235, 247, 255), scale=3, spacing=2)
    draw.line((tw + 7, 3, tw + 7, 29), fill=(28, 45, 54))
    right_x = tw + 11
    _center_text(image, draw, now.strftime("%A").upper()[:9], -1, font, (62, 224, 150), right_x, 126)
    _center_text(image, draw, date[:14], 8, font, (150, 178, 196), right_x, 126)
    _center_text(image, draw, f"DAY {pct}", 17, font, (235, 247, 255), right_x, 126)
    _draw_progress(draw, (right_x, 28, 126, 31), progress)
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

    image = _render_128(now, time_text, font, opts) if opts.get("_target") == "matrixportal-s3-128x32" else _render_64(now, time_text, font)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
