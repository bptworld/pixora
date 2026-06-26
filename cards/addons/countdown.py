from card_utils import (
    draw_sharp_text_weighted,
    draw_sharp_text,
    render_text_webp,
)

CARD_ID = "countdown"
CARD_NAME = "Countdown"
CARD_DETAIL = "Days until any event"
CARD_OPTIONS = [
    {"key": "eventName", "label": "Event Name", "type": "text",  "default": "EVENT",   "maxlength": 10},
    {"key": "targetDate","label": "Event Date", "type": "date",  "default": ""},
]


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont
    from io import BytesIO
    from datetime import date as date_type

    opts       = options or {}
    width      = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    event_name = (opts.get("eventName") or "EVENT").strip().upper()[:10]
    target_str = (opts.get("targetDate") or "").strip()

    image = Image.new("RGB", (width, 32), (5, 8, 20))
    draw  = ImageDraw.Draw(image)
    try:
        header_font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        big_font    = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 20)
        small_font  = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        header_font = big_font = small_font = ImageFont.load_default()

    # Header: event name centered, teal
    hw = draw.textbbox((0, 0), event_name, font=header_font)[2]
    draw_sharp_text(image, ((width - hw) // 2, -3), event_name, (24, 182, 163), header_font)
    draw.line((0, 8, width - 1, 8), fill=(15, 50, 50))

    try:
        target = date_type.fromisoformat(target_str)
        days   = (target - date_type.today()).days
    except Exception:
        days = None

    if days is None:
        tb = draw.textbbox((0, 0), "SET DATE", font=small_font)
        draw_sharp_text(image, ((width - (tb[2] - tb[0])) // 2, 13), "SET DATE", (140, 140, 140), small_font)
    elif days <= 0:
        msg = "TODAY!" if days == 0 else "PAST!"
        tb  = draw.textbbox((0, 0), msg, font=big_font)
        draw_sharp_text(image, ((width - (tb[2] - tb[0])) // 2, 9 + (14 - (tb[3] - tb[1])) // 2), msg, (80, 230, 140), big_font)
    else:
        num_str = str(days)
        nb = draw.textbbox((0, 0), num_str, font=big_font)
        nw, nh = nb[2] - nb[0], nb[3] - nb[1]
        draw_sharp_text_weighted(image, ((width - nw) // 2 - 1, 2), num_str, (220, 240, 255), big_font, weight=2)
        label = "DAY" if days == 1 else "DAYS"
        lb    = draw.textbbox((0, 0), label, font=small_font)
        draw_sharp_text(image, ((width - (lb[2] - lb[0])) // 2, 20), label, (100, 180, 255), small_font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
