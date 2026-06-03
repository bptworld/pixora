from datetime import date
from io import BytesIO

from card_utils import draw_sharp_text

CARD_ID = "word_of_day"
CARD_NAME = "Word of the Day"
CARD_DETAIL = "Daily word with short meaning"
CARD_OPTIONS = [
    {
        "key": "mode",
        "label": "Mode",
        "type": "select",
        "default": "daily",
        "choices": [
            {"value": "daily", "label": "Daily word"},
            {"value": "random", "label": "Rotate words"},
        ],
    }
]

WORDS = [
    ("BRIGHT", "full of light"),
    ("MIRTH", "good cheer"),
    ("QUIET", "calm and still"),
    ("SPARK", "small flash"),
    ("NIMBLE", "quick moving"),
    ("BRISK", "quick and fresh"),
    ("GLIMMER", "faint shine"),
    ("JOVIAL", "cheerful"),
    ("ZEST", "lively energy"),
    ("WONDER", "awe or marvel"),
    ("COZY", "warm comfort"),
    ("FOCUS", "clear attention"),
]


def _pick(opts):
    today = date.today()
    if (opts or {}).get("mode") == "random":
        idx = (today.toordinal() * 7) % len(WORDS)
    else:
        idx = today.toordinal() % len(WORDS)
    return WORDS[idx]


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    word, meaning = _pick(opts)
    image = Image.new("RGB", (width, 32), (0, 4, 10))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()
    draw.rectangle((0, 0, width - 1, 8), fill=(8, 20, 32))
    w = draw.textbbox((0, 0), word, font=bold)[2]
    draw_sharp_text(image, ((width - w) // 2, -3), word, (100, 200, 255), bold)
    words = meaning.upper().split()
    lines = [" ".join(words[:5]), " ".join(words[5:])]
    y = 12
    for line in [l for l in lines if l]:
        tw = draw.textbbox((0, 0), line, font=font)[2]
        draw_sharp_text(image, ((width - tw) // 2, y), line, (220, 235, 245), font)
        y += 9
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

