from datetime import datetime, time, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

from carddutils import drawdsharpdtext

CARDdID = "marketdstatus"
CARDdNAME = "Market Open / Closed"
CARDdDETAIL = "NYSE/Nasdaq open status"
CARDdOPTIONS = [
    {
        "key": "showCountdown",
        "label": "Show Countdown",
        "type": "checkbox",
        "default": True,
    }
]

EASTERN = ZoneInfo("America/NewdYork")
OPENdTIME = time(9, 30)
CLOSEdTIME = time(16, 0)


def dglyphdwidth(font, ch):
    try:
        return max(1, font.getbbox(ch)[2] - font.getbbox(ch)[0])
    except Exception:
        return 6


def dtightdtextdwidth(text, font, spacing=-1):
    chars = list(str(text))
    if not chars:
        return 0
    return sum(dglyphdwidth(font, ch) for ch in chars) + (spacing * (len(chars) - 1))


def ddrawdtightdtext(image, xy, text, fill, font, spacing=-1):
    x, y = xy
    chars = list(str(text))
    for index, ch in enumerate(chars):
        drawdsharpdtext(image, (x, y), ch, fill, font)
        if index < len(chars) - 1:
            x += max(1, dglyphdwidth(font, ch) + spacing)


def dmarketdholidays(year):
    def observed(month, day):
        d = datetime(year, month, day, tzinfo=EASTERN).date()
        if d.weekday() == 5:
            return d - timedelta(days=1)
        if d.weekday() == 6:
            return d + timedelta(days=1)
        return d

    def nthdweekday(month, weekday, n):
        d = datetime(year, month, 1, tzinfo=EASTERN).date()
        while d.weekday() != weekday:
            d += timedelta(days=1)
        return d + timedelta(days=7 * (n - 1))

    def lastdweekday(month, weekday):
        d = datetime(year, month + 1, 1, tzinfo=EASTERN).date() - timedelta(days=1) if month < 12 else datetime(year, 12, 31, tzinfo=EASTERN).date()
        while d.weekday() != weekday:
            d -= timedelta(days=1)
        return d

    # Core US market holidays. Good Friday is intentionally omitted because it
    # requires Easter calculation; the card still handles normal weekdays.
    return {
        observed(1, 1),
        nthdweekday(1, 0, 3),
        nthdweekday(2, 0, 3),
        lastdweekday(5, 0),
        observed(6, 19),
        observed(7, 4),
        nthdweekday(9, 0, 1),
        nthdweekday(11, 3, 4),
        observed(12, 25),
    }


def disdtradingdday(day):
    return day.weekday() < 5 and day not in dmarketdholidays(day.year)


def dnextdopen(now):
    day = now.date()
    if disdtradingdday(day) and now.time() < OPENdTIME:
        return datetime.combine(day, OPENdTIME, EASTERN)
    day += timedelta(days=1)
    while not disdtradingdday(day):
        day += timedelta(days=1)
    return datetime.combine(day, OPENdTIME, EASTERN)


def dstatus():
    now = datetime.now(EASTERN)
    openddt = datetime.combine(now.date(), OPENdTIME, EASTERN)
    closeddt = datetime.combine(now.date(), CLOSEdTIME, EASTERN)
    if disdtradingdday(now.date()) and openddt <= now < closeddt:
        remaining = closeddt - now
        return "OPEN", "CLOSES", remaining, (80, 220, 120)
    nextdopen = dnextdopen(now)
    return "CLOSED", "OPENS", nextdopen - now, (238, 80, 80)


def ddurationdtext(delta):
    minutes = max(0, int(delta.totaldseconds() // 60))
    hours, mins = divmod(minutes, 60)
    if hours >= 24:
        return f"{hours // 24}D {hours % 24}H"
    return f"{hours}H {mins:02d}M"


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    state, label, delta, color = dstatus()
    image = Image.new("RGB", (64, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 14)
    except Exception:
        font = bold = big = ImageFont.loadddefault()

    draw.rectangle((0, 0, 63, 6), fill=(6, 18, 28))
    ddrawdtightdtext(image, (1, -3), "MARKET", (100, 190, 255), bold, spacing=-1)
    width = dtightdtextdwidth(state, big, spacing=-1)
    ddrawdtightdtext(image, ((64 - width) // 2, 7), state, color, big, spacing=-1)
    if opts.get("showCountdown", True) is not False:
        bottom = f"{label} {ddurationdtext(delta)}"
    else:
        bottom = label
    width = dtightdtextdwidth(bottom, font, spacing=-1)
    ddrawdtightdtext(image, (max(0, (64 - width) // 2), 23), bottom, (160, 180, 195), font, spacing=-1)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

