from datetime import date
from io import BytesIO

from card_utils import draw_sharp_text

CARD_ID = "battery_reminder"
CARD_NAME = "Battery Reminder"
CARD_DETAIL = "Rotating battery checklist"
CARD_OPTIONS = [
    {
        "key": "items",
        "label": "Items",
        "type": "text",
        "default": "Smoke detectors; Remotes; Hubitat sensors; Flashlights",
        "maxlength": 120,
    },
    {"key": "daysPerItem", "label": "Days Per Item", "type": "number", "default": "7", "min": 1, "max": 60},
]


def _items(text):
    values = [part.strip() for part in str(text or "").replace(",", ";").split(";") if part.strip()]
    return values or ["Smoke detectors"]


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    items = _items(opts.get("items"))
    try:
        days = max(1, int(opts.get("daysPerItem", 7)))
    except Exception:
        days = 7
    item = items[(date.today().toordinal() // days) % len(items)]

    image = Image.new("RGB", (width, 32), (0, 5, 9))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    draw.rectangle((3, 9, 18, 22), outline=(90, 220, 120))
    draw.rectangle((19, 13, 21, 18), fill=(90, 220, 120))
    draw.rectangle((5, 11, 14, 20), fill=(90, 220, 120))
    draw_sharp_text(image, (25, -3), "BATTERY", (90, 220, 120), bold)
    words = item.upper().split()
    lines = [" ".join(words[:4]), " ".join(words[4:])]
    y = 10
    for line in [l for l in lines if l][:2]:
        draw_sharp_text(image, (25, y), line[:22 if width == 128 else 9], (235, 245, 255), font)
        y += 9
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

