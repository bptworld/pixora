from datetime import datetime, time, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

from card_utils import draw_sharp_text

CARD_ID = "market_status"
CARD_NAME = "Market Open / Closed"
CARD_DETAIL = "NYSE/Nasdaq open status"
CARD_OPTIONS = [
    {
        "key": "showCountdown",
        "label": "Show Countdown",
        "type": "checkbox",
        "default": True,
    }
]

EASTERN = ZoneInfo("America/New_York")
OPEN_TIME = time(9, 30)
CLOSE_TIME = time(16, 0)


def _glyph_width(font, ch):
    try:
        return max(1, font.getbbox(ch)[2] - font.getbbox(ch)[0])
    except Exception:
        return 6


def _tight_text_width(text, font, spacing=-1):
    chars = list(str(text))
    if not chars:
        return 0
    return sum(_glyph_width(font, ch) for ch in chars) + (spacing * (len(chars) - 1))


def _draw_tight_text(image, xy, text, fill, font, spacing=-1):
    x, y = xy
    chars = list(str(text))
    for index, ch in enumerate(chars):
        draw_sharp_text(image, (x, y), ch, fill, font)
        if index < len(chars) - 1:
            x += max(1, _glyph_width(font, ch) + spacing)


def _market_holidays(year):
    def observed(month, day):
        d = datetime(year, month, day, tzinfo=EASTERN).date()
        if d.weekday() == 5:
            return d - timedelta(days=1)
        if d.weekday() == 6:
            return d + timedelta(days=1)
        return d

    def nth_weekday(month, weekday, n):
        d = datetime(year, month, 1, tzinfo=EASTERN).date()
        while d.weekday() != weekday:
            d += timedelta(days=1)
        return d + timedelta(days=7 * (n - 1))

    def last_weekday(month, weekday):
        d = datetime(year, month + 1, 1, tzinfo=EASTERN).date() - timedelta(days=1) if month < 12 else datetime(year, 12, 31, tzinfo=EASTERN).date()
        while d.weekday() != weekday:
            d -= timedelta(days=1)
        return d

    # Core US market holidays. Good Friday is intentionally omitted because it
    # requires Easter calculation; the card still handles normal weekdays.
    return {
        observed(1, 1),
        nth_weekday(1, 0, 3),
        nth_weekday(2, 0, 3),
        last_weekday(5, 0),
        observed(6, 19),
        observed(7, 4),
        nth_weekday(9, 0, 1),
        nth_weekday(11, 3, 4),
        observed(12, 25),
    }


def _is_trading_day(day):
    return day.weekday() < 5 and day not in _market_holidays(day.year)


def _next_open(now):
    day = now.date()
    if _is_trading_day(day) and now.time() < OPEN_TIME:
        return datetime.combine(day, OPEN_TIME, EASTERN)
    day += timedelta(days=1)
    while not _is_trading_day(day):
        day += timedelta(days=1)
    return datetime.combine(day, OPEN_TIME, EASTERN)


def _status():
    now = datetime.now(EASTERN)
    open_dt = datetime.combine(now.date(), OPEN_TIME, EASTERN)
    close_dt = datetime.combine(now.date(), CLOSE_TIME, EASTERN)
    if _is_trading_day(now.date()) and open_dt <= now < close_dt:
        remaining = close_dt - now
        return "OPEN", "CLOSES", remaining, (80, 220, 120)
    next_open = _next_open(now)
    return "CLOSED", "OPENS", next_open - now, (238, 80, 80)


def _duration_text(delta):
    minutes = max(0, int(delta.total_seconds() // 60))
    hours, mins = divmod(minutes, 60)
    if hours >= 24:
        return f"{hours // 24}D {hours % 24}H"
    return f"{hours}H {mins:02d}M"


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    state, label, delta, color = _status()
    image = Image.new("RGB", (64, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("PixelifySans-Bold.ttf", 14)
    except Exception:
        font = bold = big = ImageFont.load_default()

    draw.rectangle((0, 0, 63, 8), fill=(6, 18, 28))
    _draw_tight_text(image, (1, -3), "MARKET", (100, 190, 255), bold, spacing=-1)
    width = _tight_text_width(state, big, spacing=-1)
    _draw_tight_text(image, ((64 - width) // 2, 7), state, color, big, spacing=-1)
    if opts.get("showCountdown", True) is not False:
        bottom = f"{label} {_duration_text(delta)}"
    else:
        bottom = label
    width = _tight_text_width(bottom, font, spacing=-1)
    _draw_tight_text(image, (max(0, (64 - width) // 2), 23), bottom, (160, 180, 195), font, spacing=-1)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

