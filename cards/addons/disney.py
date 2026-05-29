from card_utils import (
    draw_sharp_text_weighted,
    draw_sharp_text,
    render_text_webp,
)

CARD_ID = "disney"
CARD_NAME = "Disney Countdown"
CARD_DETAIL = "Days until your trip"
CARD_OPTIONS = [
    {"key": "targetDate", "label": "Trip Date", "type": "date", "default": ""}
]

_SHOW_INTRO = {}  # device_id -> True means next render is the intro frame


def _draw_base(image, draw, header_font):
    width = image.width
    image.paste((8, 5, 18), (0, 0, width, 32))
    label = "DISNEY COUNTDOWN" if width == 128 else "DISNEY"
    w = draw.textbbox((0, 0), label, font=header_font)[2]
    draw_sharp_text(image, ((width - w) // 2 if width == 128 else 1, -3), label, (255, 210, 50), header_font)
    draw.line((0, 8, width - 1, 8), fill=(60, 45, 10))


def _draw_mickey(draw, cx, cy):
    col = (255, 210, 50)
    draw.ellipse((cx - 10, cy - 8,  cx + 10, cy + 8),  fill=col)
    draw.ellipse((cx - 17, cy - 14, cx - 7,  cy - 4),  fill=col)
    draw.ellipse((cx + 7,  cy - 14, cx + 17, cy - 4),  fill=col)


def _build_intro(header_font, sparkle_frame=0, width=64):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (width, 32), (8, 5, 18))
    draw = ImageDraw.Draw(img)
    _draw_base(img, draw, header_font)
    _draw_mickey(draw, width // 2, 22)
    sparkle_points = [
        (width // 2 - 17, 9), (width // 2 - 14, 11), (width // 2 - 10, 10), (width // 2 - 7, 13),
        (width // 2 + 7, 13), (width // 2 + 11, 10), (width // 2 + 15, 11), (width // 2 + 18, 9),
        (width // 2 - 8, 17), (width // 2 - 4, 19), (width // 2 - 1, 15), (width // 2 + 3, 18),
        (width // 2 + 7, 20), (width // 2 - 9, 23), (width // 2 - 4, 26), (width // 2 + 1, 24),
        (width // 2 + 6, 26), (width // 2 + 11, 23), (width // 2, 20), (width // 2 + 4, 22),
    ]
    colors = [(255, 255, 235), (255, 245, 170), (255, 232, 95)]
    for index, (x, y) in enumerate(sparkle_points):
        seed = (sparkle_frame * 17 + index * 31 + 7) % 11
        if seed in (0, 1, 2, 5, 7, 9):
            draw.point((x, y), fill=colors[(seed + sparkle_frame) % len(colors)])
    return img


def _build_intro_webp(header_font, width=64):
    from io import BytesIO

    frames = [_build_intro(header_font, frame, width) for frame in range(9)]
    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=150,
        loop=1,
        lossless=True,
        quality=100,
    )
    return out.getvalue()


def _build_countdown(days, header_font, big_font, small_font, width=64):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (width, 32), (8, 5, 18))
    draw = ImageDraw.Draw(img)
    _draw_base(img, draw, header_font)
    if days is None:
        tb = draw.textbbox((0, 0), "SET DATE", font=small_font)
        draw_sharp_text(img, ((width - (tb[2] - tb[0])) // 2, 13), "SET DATE", (180, 180, 180), small_font)
    elif days <= 0:
        msg = "TODAY!" if days == 0 else "ENJOY!"
        tb = draw.textbbox((0, 0), msg, font=big_font)
        draw_sharp_text(img, ((width - (tb[2] - tb[0])) // 2, 9 + (14 - (tb[3] - tb[1])) // 2), msg, (100, 255, 150), big_font)
    else:
        num_str = str(days)
        nb = draw.textbbox((0, 0), num_str, font=big_font)
        nw, nh = nb[2] - nb[0], nb[3] - nb[1]
        draw_sharp_text_weighted(img, ((width - nw) // 2 - 1, 2), num_str, (220, 240, 255), big_font, weight=2)
        label = "DAY" if days == 1 else "DAYS"
        lb = draw.textbbox((0, 0), label, font=small_font)
        draw_sharp_text(img, ((width - (lb[2] - lb[0])) // 2, 20), label, (200, 160, 255), small_font)
    return img


def render(options=None):
    from PIL import ImageFont
    from io import BytesIO
    from datetime import date as date_type

    opts       = options or {}
    width      = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    device_id  = opts.get("_device_id", "_")
    dwell      = max(4, int(opts.get("_dwell", 30)))
    target_str = (opts.get("targetDate") or "").strip()

    try:
        target = date_type.fromisoformat(target_str)
        days   = (target - date_type.today()).days
    except Exception:
        days = None

    try:
        header_font = ImageFont.truetype("PixelifySans-Bold.ttf", 8)
        big_font    = ImageFont.truetype("Silkscreen-Regular.ttf", 20)
        small_font  = ImageFont.truetype("Silkscreen-Regular.ttf", 8)
    except Exception:
        header_font = big_font = small_font = ImageFont.load_default()

    def to_webp(img):
        buf = BytesIO()
        img.save(buf, "WEBP", lossless=True, quality=100)
        return buf.getvalue()

    # Toggle: default True so the very first render is always the intro
    show_intro = _SHOW_INTRO.get(device_id, True)

    if show_intro:
        _SHOW_INTRO[device_id] = False  # next render: countdown
        body = _build_intro_webp(header_font, width)
        return {"body": body, "dwell_secs": 3, "_stay": True}
    else:
        _SHOW_INTRO[device_id] = True   # next render: intro again
        body = to_webp(_build_countdown(days, header_font, big_font, small_font, width))
        return {"body": body, "dwell_secs": dwell - 3}

