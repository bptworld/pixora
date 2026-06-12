from card_utils import (
    draw_sharp_text_weighted,
    draw_sharp_text,
    render_text_webp,
)
from pathlib import Path

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


def _draw_mickey_outline(draw, cx, cy, color=(255, 210, 50)):
    draw.ellipse((cx - 11, cy - 9, cx + 11, cy + 9), outline=color, width=2)
    draw.ellipse((cx - 18, cy - 16, cx - 7, cy - 5), outline=color, width=2)
    draw.ellipse((cx + 7, cy - 16, cx + 18, cy - 5), outline=color, width=2)


def _castle_asset_path():
    here = Path(__file__).resolve()
    for root in (here.parents[2], here.parents[3] if len(here.parents) > 3 else here.parents[2]):
        for rel in ("graphics/assets/cinderella-castle.png", "cloud/graphics/assets/cinderella-castle.png"):
            path = root / rel
            if path.exists():
                return path
    return None


def _draw_castle(image, x, y, max_w, max_h):
    from PIL import Image

    path = _castle_asset_path()
    if not path:
        return
    try:
        with Image.open(path) as source:
            castle = source.convert("RGBA")
            box = castle.getbbox()
            if box:
                castle = castle.crop(box)
            castle.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            image.paste(castle, (x, y + max(0, (max_h - castle.height) // 2)), castle)
    except Exception:
        return


def _draw_countdown_in_head(image, draw, cx, cy, days, number_font, tiny_font):
    color = (220, 240, 255) if days is None or days > 0 else (100, 255, 150)
    if days is None:
        lines = [("SET", tiny_font), ("DATE", tiny_font)]
    elif days <= 0:
        lines = [("TODAY", tiny_font)] if days == 0 else [("ENJOY", tiny_font)]
    else:
        lines = [(str(days), number_font)]
    total_h = 0
    metrics = []
    for text, font in lines:
        tb = draw.textbbox((0, 0), text, font=font)
        metrics.append((text, font, tb[2] - tb[0], tb[3] - tb[1]))
        total_h += tb[3] - tb[1]
    total_h += max(0, len(lines) - 1)
    y = cy - total_h // 2 - 4
    for text, font, tw, th in metrics:
        draw_sharp_text(image, (cx - tw // 2, y), text, color, font)
        y += th + 1


def _countdown_text(days):
    if days is None:
        return "Set Date"
    if days <= 0:
        return "Today!" if days == 0 else "Enjoy!"
    return f"{days} {'Day' if days == 1 else 'Days'}"


def _draw_128_center_countdown(image, draw, days, number_font, word_font):
    color = (220, 240, 255) if days is None or days > 0 else (100, 255, 150)
    if days is None or days <= 0:
        text = _countdown_text(days)
        tb = draw.textbbox((0, 0), text, font=word_font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        draw_sharp_text(image, ((image.width - tw) // 2, 13 + (14 - th) // 2 - 5), text, color, word_font)
        return
    number = str(days)
    word = "Day" if days == 1 else "Days"
    gap = 3
    nb = draw.textbbox((0, 0), number, font=number_font)
    wb = draw.textbbox((0, 0), word, font=word_font)
    nw, nh = nb[2] - nb[0], nb[3] - nb[1]
    ww, wh = wb[2] - wb[0], wb[3] - wb[1]
    total_w = nw + gap + ww
    base_y = 13 + (14 - max(nh, wh)) // 2 - 5
    x = (image.width - total_w) // 2
    draw_sharp_text(image, (x, base_y - 2), number, color, number_font)
    draw_sharp_text(image, (x + nw + gap, base_y + max(0, nh - wh)), word, (200, 160, 255), word_font)


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


def _build_128_reveal_frame(days, header_font, number_font, word_font, progress=1.0):
    from PIL import Image, ImageDraw

    width = 128
    img = Image.new("RGB", (width, 32), (8, 5, 18))
    draw = ImageDraw.Draw(img)
    _draw_base(img, draw, header_font)
    progress = max(0.0, min(1.0, progress))

    if progress >= 0.18:
        _draw_128_center_countdown(img, draw, days, number_font, word_font)

    castle_start = 47
    castle_end = 0
    mickey_start = 78
    mickey_end = width - 18
    castle_x = round(castle_start + (castle_end - castle_start) * progress)
    mickey_x = round(mickey_start + (mickey_end - mickey_start) * progress)
    _draw_castle(img, castle_x, 10, 38, 21)
    _draw_mickey_outline(draw, mickey_x, 22)
    return img


def _build_128_reveal_webp(days, header_font, number_font, word_font):
    from io import BytesIO

    steps = [0.0, 0.1, 0.2, 0.32, 0.45, 0.58, 0.72, 0.86, 1.0]
    frames = [_build_128_reveal_frame(days, header_font, number_font, word_font, progress) for progress in steps]
    frames.extend([frames[-1]] * 6)
    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=[110] * len(steps) + [450] * 6,
        loop=1,
        lossless=True,
        quality=100,
    )
    return out.getvalue()


def _build_countdown_frame(days, header_font, countdown_font, tiny_font, width=64, progress=1.0):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (width, 32), (8, 5, 18))
    draw = ImageDraw.Draw(img)
    _draw_base(img, draw, header_font)
    progress = max(0.0, min(1.0, progress))
    start_x = width // 2
    end_x = width - (20 if width <= 64 else 24)
    cx = round(start_x + (end_x - start_x) * progress)
    cy = 22
    castle_alpha = progress
    if castle_alpha > 0:
        castle_w = 22 if width <= 64 else 38
        castle_h = 21
        _draw_castle(img, 1 if width <= 64 else 4, 10, castle_w, castle_h)
    _draw_mickey_outline(draw, cx, cy)
    if progress >= 0.55:
        _draw_countdown_in_head(img, draw, cx, cy, days, countdown_font, tiny_font)
    return img


def _build_countdown_webp(days, header_font, countdown_font, tiny_font, width=64):
    from io import BytesIO

    steps = [0.0, 0.12, 0.25, 0.38, 0.5, 0.62, 0.75, 0.88, 1.0]
    frames = [_build_countdown_frame(days, header_font, countdown_font, tiny_font, width, progress) for progress in steps]
    frames.extend([frames[-1]] * 6)
    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=[110] * len(steps) + [450] * 6,
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
        header_font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        big_font    = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 20)
        countdown_font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 12)
        reveal_font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 12)
        reveal_word_font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        tiny_font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 6)
        small_font  = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        header_font = big_font = countdown_font = reveal_font = reveal_word_font = tiny_font = small_font = ImageFont.load_default()

    def to_webp(img):
        buf = BytesIO()
        img.save(buf, "WEBP", lossless=True, quality=100)
        return buf.getvalue()

    # Toggle: default True so the very first render is always the intro
    show_intro = _SHOW_INTRO.get(device_id, True)

    if show_intro:
        _SHOW_INTRO[device_id] = False  # next render: countdown
        body = _build_countdown_webp(days, header_font, countdown_font, tiny_font, width) if width <= 64 else _build_128_reveal_webp(days, header_font, reveal_font, reveal_word_font)
        return {"body": body, "dwell_secs": 3, "_stay": True}
    else:
        _SHOW_INTRO[device_id] = True   # next render: intro again
        body = to_webp(_build_countdown_frame(days, header_font, countdown_font, tiny_font, width, 1.0) if width <= 64 else _build_128_reveal_frame(days, header_font, reveal_font, reveal_word_font, 1.0))
        return {"body": body, "dwell_secs": dwell - 3}
