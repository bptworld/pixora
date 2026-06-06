from datetime import datetime
from io import BytesIO

from card_utils import draw_sharp_text, format_time

CARD_ID = "clock_calendar"
CARD_NAME = "Clock with Calendar"
CARD_DETAIL = "Time and today's date"

_SEGMENTS = {
    "0": "abcfed",
    "1": "bc",
    "2": "abged",
    "3": "abgcd",
    "4": "fgbc",
    "5": "afgcd",
    "6": "afgecd",
    "7": "abc",
    "8": "abcdefg",
    "9": "abfgcd",
}


def _bitmap_time_size(text, scale=1, spacing=1):
    width = 0
    for idx, ch in enumerate(str(text or "")):
        if ch in _SEGMENTS:
            width += 5 * scale
        elif ch == ":":
            width += scale
        elif ch == " ":
            width += 3 * scale
        if idx < len(str(text or "")) - 1:
            width += spacing
    return max(0, width), 9 * scale


def _draw_bitmap_time(draw, xy, text, color, scale=1, spacing=1):
    x, y = xy
    for ch in str(text or ""):
        segments = _SEGMENTS.get(ch)
        if segments:
            bar = max(1, scale)

            def hseg(px, py):
                draw.rectangle((x + px * scale, y + py * scale, x + (px + 3) * scale - 1, y + py * scale + bar - 1), fill=color)

            def vseg(px, py):
                draw.rectangle((x + px * scale, y + py * scale, x + px * scale + bar - 1, y + (py + 3) * scale - 1), fill=color)

            if "a" in segments:
                hseg(1, 0)
            if "b" in segments:
                vseg(4, 1)
            if "c" in segments:
                vseg(4, 5)
            if "d" in segments:
                hseg(1, 8)
            if "e" in segments:
                vseg(0, 5)
            if "f" in segments:
                vseg(0, 1)
            if "g" in segments:
                hseg(1, 4)
            x += 5 * scale + spacing
        elif ch == ":":
            draw.rectangle((x, y + 2 * scale, x + scale - 1, y + 3 * scale - 1), fill=color)
            draw.rectangle((x, y + 6 * scale, x + scale - 1, y + 7 * scale - 1), fill=color)
            x += scale + spacing
        elif ch == " ":
            x += 3 * scale + spacing


def _center_text(image, draw, text, y, font, color, x1=0, x2=None):
    x2 = image.width - 1 if x2 is None else x2
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    draw_sharp_text(image, (x1 + ((x2 - x1 + 1) - width) // 2 - bbox[0], y), text, color, font)


def _draw_calendar_icon(image, draw, x, y, day, font, scale=1):
    cell = 3 * scale
    gap = max(1, scale)
    cols = 7
    rows = 7
    red = (214, 0, 18)
    white = (232, 236, 238)
    dim = (36, 38, 40)
    grid_w = cols * cell + (cols - 1) * gap
    grid_h = rows * cell + (rows - 1) * gap

    def tile(col, row, color):
        px = x + col * (cell + gap)
        py = y + row * (cell + gap)
        draw.rectangle((px, py, px + cell - 1, py + cell - 1), fill=color)

    for row in range(rows):
        for col in range(cols):
            tile(col, row, red if row < 2 else dim)

    digit = str(day.day % 10)
    segments = _SEGMENTS.get(digit, _SEGMENTS["0"])
    active = set()
    if "a" in segments:
        active.update((col, 2) for col in range(1, 6))
    if "b" in segments:
        active.update((5, row) for row in range(3, 5))
    if "c" in segments:
        active.update((5, row) for row in range(5, 7))
    if "d" in segments:
        active.update((col, 6) for col in range(1, 6))
    if "e" in segments:
        active.update((1, row) for row in range(5, 7))
    if "f" in segments:
        active.update((1, row) for row in range(3, 5))
    if "g" in segments:
        active.update((col, 4) for col in range(1, 6))

    for col, row in active:
        tile(col, row, white)

    draw.rectangle((x - 1, y - 1, x + grid_w, y + grid_h), outline=(18, 18, 18))


def _render_64(now, time_text, font):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (64, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    _draw_calendar_icon(image, draw, 1, 4, now, font, scale=1)
    time_w, time_h = _bitmap_time_size(time_text, scale=1, spacing=1)
    _draw_bitmap_time(draw, (64 - time_w - 2, 7), time_text, (232, 236, 238), scale=1, spacing=1)
    _draw_bottom_blocks(draw, 30, 25, 62, active=3, block_w=5, gap=3)
    return image


def _render_128(now, time_text, font):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (128, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    _draw_calendar_icon(image, draw, 3, 3, now, font, scale=1)

    time_scale = 2
    time_spacing = 4
    time_w, time_h = _bitmap_time_size(time_text, scale=time_scale, spacing=time_spacing)
    time_x = 44 + max(0, (78 - time_w) // 2)
    _draw_bitmap_time(draw, (time_x, 4), time_text, (232, 236, 238), scale=time_scale, spacing=time_spacing)
    _draw_bottom_blocks(draw, 36, 26, 125, active=4, block_w=8, gap=6)
    return image


def _draw_bottom_blocks(draw, x1, y, x2, active=0, block_w=6, gap=4):
    dim = (24, 25, 26)
    bright = (232, 236, 238)
    x = x1
    idx = 0
    while x + block_w - 1 <= x2:
        draw.rectangle((x, y, x + block_w - 1, y + 2), fill=bright if idx == active else dim)
        x += block_w + gap
        idx += 1


def render(options=None):
    from PIL import ImageFont

    opts = options or {}
    is_wide = opts.get("_target") == "matrixportal-s3-128x32"
    now = datetime.now()
    time_text = format_time(now)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        font = ImageFont.load_default()

    image = _render_128(now, time_text, font) if is_wide else _render_64(now, time_text, font)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
