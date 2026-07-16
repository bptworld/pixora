from datetime import date, datetime, time, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

from card_utils import draw_sharp_text

CARD_ID = "market_status"
CARD_NAME = "Market Open / Closed"
CARD_DETAIL = "NYSE/Nasdaq open status"
CARD_OPTIONS = [
    {"key": "showCountdown", "label": "Show Countdown", "type": "checkbox", "default": True},
]

EASTERN = ZoneInfo("America/New_York")
OPEN_TIME = time(9, 30)
CLOSE_TIME = time(16, 0)


def _truthy(value):
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "on"}


def _glyph_width(font, ch):
    try:
        return max(1, font.getbbox(ch)[2] - font.getbbox(ch)[0])
    except Exception:
        return 6


def _tight_text_width(text, font, spacing=-1):
    chars = list(str(text))
    return sum(_glyph_width(font, ch) for ch in chars) + spacing * max(0, len(chars) - 1)


def _draw_tight_text(image, xy, text, fill, font, spacing=-1):
    x, y = xy
    for index, ch in enumerate(str(text)):
        draw_sharp_text(image, (x, y), ch, fill, font)
        if index < len(str(text)) - 1:
            x += max(1, _glyph_width(font, ch) + spacing)


def _easter(year):
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _market_holidays(year):
    def observed(month, day):
        value = date(year, month, day)
        return value - timedelta(days=1) if value.weekday() == 5 else value + timedelta(days=1) if value.weekday() == 6 else value

    def nth_weekday(month, weekday, n):
        value = date(year, month, 1)
        while value.weekday() != weekday:
            value += timedelta(days=1)
        return value + timedelta(days=7 * (n - 1))

    def last_weekday(month, weekday):
        value = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
        while value.weekday() != weekday:
            value -= timedelta(days=1)
        return value

    holidays = {
        observed(1, 1), nth_weekday(1, 0, 3), nth_weekday(2, 0, 3),
        _easter(year) - timedelta(days=2), last_weekday(5, 0), observed(6, 19),
        observed(7, 4), nth_weekday(9, 0, 1), nth_weekday(11, 3, 4), observed(12, 25),
    }
    next_new_year = date(year + 1, 1, 1)
    if next_new_year.weekday() == 5:
        holidays.add(next_new_year - timedelta(days=1))
    return holidays


def _is_trading_day(day):
    return day.weekday() < 5 and day not in _market_holidays(day.year)


def _close_time(day):
    thanksgiving = date(day.year, 11, 1)
    thanksgiving += timedelta(days=(3 - thanksgiving.weekday()) % 7 + 21)
    early_close = (
        day == thanksgiving + timedelta(days=1)
        or (day.month, day.day) in {(7, 3), (12, 24)}
    )
    if early_close and _is_trading_day(day):
        return time(13, 0)
    return CLOSE_TIME


def _next_open(now):
    day = now.date()
    if _is_trading_day(day) and now.time() < OPEN_TIME:
        return datetime.combine(day, OPEN_TIME, EASTERN)
    day += timedelta(days=1)
    while not _is_trading_day(day):
        day += timedelta(days=1)
    return datetime.combine(day, OPEN_TIME, EASTERN)


def _status(now=None):
    now = now or datetime.now(EASTERN)
    open_at = datetime.combine(now.date(), OPEN_TIME, EASTERN)
    close_at = datetime.combine(now.date(), _close_time(now.date()), EASTERN)
    if _is_trading_day(now.date()) and open_at <= now < close_at:
        return "OPEN", "CLOSES", close_at - now, (80, 220, 120)
    return "CLOSED", "OPENS", _next_open(now) - now, (238, 80, 80)


def _duration_text(delta):
    minutes = max(0, int(delta.total_seconds() // 60))
    hours, mins = divmod(minutes, 60)
    return f"{hours // 24}D {hours % 24}H" if hours >= 24 else f"{hours}H {mins:02d}M"


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    state, label, delta, color = _status()
    image = Image.new("RGB", (64, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 14)
    except Exception:
        font = bold = big = ImageFont.load_default()

    draw.rectangle((0, 0, 63, 6), fill=(6, 18, 28))
    _draw_tight_text(image, (1, -3), "MARKET", (100, 190, 255), bold)
    width = _tight_text_width(state, big)
    _draw_tight_text(image, ((64 - width) // 2, 7), state, color, big)
    bottom = f"{label} {_duration_text(delta)}" if _truthy(opts.get("showCountdown", True)) else label
    width = _tight_text_width(bottom, font)
    _draw_tight_text(image, (max(0, (64 - width) // 2), 23), bottom, (160, 180, 195), font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
