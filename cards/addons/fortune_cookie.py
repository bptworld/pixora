from io import BytesIO
from datetime import date

from card_utils import pixora_local_now

CARD_ID = "fortune_cookie"
CARD_NAME = "Fortune Cookie"
CARD_DETAIL = "Tiny daily fortune"
CARD_OPTIONS = [
    {
        "key": "mode",
        "label": "Mode",
        "type": "select",
        "default": "fortune",
        "choices": [
            {"value": "fortune", "label": "Daily Fortune"},
            {"value": "random", "label": "Random Fortune"},
        ],
    },
]

FORTUNES = [
    "TRY AGAIN",
    "GOOD LUCK",
    "SAY YES",
    "MAKE IT",
    "KEEP GOING",
    "BIG IDEAS",
    "SHIP IT",
    "BE KIND",
    "STAY WEIRD",
    "LOOK UP",
]


def _blend(color, factor):
    return tuple(max(0, min(255, int(channel * factor))) for channel in color)


def _draw_cookie(draw, width):
    cx = width // 2
    bg = (9, 4, 1)
    shadow = (23, 10, 3)
    outline = (118, 65, 18)
    crust = (189, 111, 35)
    golden = (237, 165, 62)
    light = (255, 205, 104)
    glow = (255, 230, 148)
    paper = (255, 244, 204)
    paper_shadow = (183, 149, 94)
    paper_line = (210, 176, 118)

    draw.rectangle((0, 0, width - 1, 31), fill=bg)
    for x in range(2, width, 9):
        draw.point((x, 28), fill=(43, 20, 7))
        draw.point((x + 4, 4), fill=(31, 14, 5))

    draw.ellipse((cx - 31, 21, cx + 31, 34), fill=shadow)
    draw.polygon([(cx - 31, 19), (cx - 20, 10), (cx - 7, 12), (cx + 1, 20), (cx - 11, 28), (cx - 25, 27)], fill=outline)
    draw.polygon([(cx + 31, 19), (cx + 20, 10), (cx + 7, 12), (cx - 1, 20), (cx + 11, 28), (cx + 25, 27)], fill=outline)
    draw.polygon([(cx - 28, 18), (cx - 19, 11), (cx - 8, 13), (cx - 1, 20), (cx - 12, 26), (cx - 24, 25)], fill=crust)
    draw.polygon([(cx + 28, 18), (cx + 19, 11), (cx + 8, 13), (cx + 1, 20), (cx + 12, 26), (cx + 24, 25)], fill=golden)
    draw.polygon([(cx - 23, 17), (cx - 18, 13), (cx - 9, 15), (cx - 4, 20), (cx - 13, 23), (cx - 22, 23)], fill=golden)
    draw.polygon([(cx + 23, 17), (cx + 18, 13), (cx + 9, 15), (cx + 4, 20), (cx + 13, 23), (cx + 22, 23)], fill=light)
    draw.line((cx - 3, 13, cx + 2, 20, cx - 3, 27), fill=(104, 53, 15))
    draw.line((cx + 2, 13, cx - 2, 20, cx + 2, 27), fill=_blend(glow, 0.78))

    draw.polygon([(cx - 28, 13), (cx + 26, 13), (cx + 31, 21), (cx - 23, 21)], fill=paper_shadow)
    draw.polygon([(cx - 30, 10), (cx + 24, 10), (cx + 30, 18), (cx - 24, 18)], fill=paper)
    draw.line((cx - 26, 17, cx + 27, 17), fill=paper_line)
    draw.point((cx - 22, 12), fill=(255, 255, 230))
    draw.point((cx + 21, 11), fill=(255, 255, 230))

    for x, y, color in [
        (cx - 30, 27, crust),
        (cx - 23, 29, light),
        (cx + 28, 27, golden),
        (cx + 22, 29, crust),
    ]:
        draw.rectangle((x, y, x + 1, y + 1), fill=color)

    return (cx - 27, 10, cx + 27, 17)


def _fit_text(text, font, draw, max_width):
    text = str(text or "").upper()
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    while text and draw.textbbox((0, 0), text + ".", font=font)[2] > max_width:
        text = text[:-1]
    return (text + ".") if text else ""


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    mode = str(opts.get("mode") or "fortune").lower()
    idx = pixora_local_now().date().toordinal() % len(FORTUNES)
    msg = FORTUNES[idx] if mode != "random" else FORTUNES[(idx * 7 + 3) % len(FORTUNES)]

    image = Image.new("RGB", (width, 32), (9, 4, 1))
    draw = ImageDraw.Draw(image)
    text_box = _draw_cookie(draw, width)

    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        font = ImageFont.load_default()
    x1, y1, x2, y2 = text_box
    text = _fit_text(msg, font, draw, x2 - x1 + 1)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_x = x1 + ((x2 - x1 + 1) - text_w) // 2 - bbox[0]
    text_y = y1 + ((y2 - y1 + 1) - text_h) // 2 - bbox[1]
    draw.text((text_x, text_y), text, fill=(78, 39, 15), font=font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
