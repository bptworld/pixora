from io import BytesIO

from card_utils import draw_sharp_text, render_message_wrap

CARD_ID = "package_watch"
CARD_NAME = "Package Watch"
CARD_DETAIL = "Manual package status"
CARD_OPTIONS = [
    {"key": "carrier", "label": "Carrier", "type": "text", "default": "UPS", "maxlength": 8},
    {"key": "status", "label": "Status", "type": "text", "default": "Out for delivery", "maxlength": 50},
    {
        "key": "mode",
        "label": "Mode",
        "type": "select",
        "default": "compact",
        "choices": [
            {"value": "compact", "label": "Compact"},
            {"value": "wrap", "label": "Wrapped message"},
        ],
    },
]


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    carrier = (opts.get("carrier") or "UPS").strip().upper()[:8]
    status = (opts.get("status") or "Out for delivery").strip()
    if opts.get("mode") == "wrap":
        return render_message_wrap(f"{carrier}: {status}", (245, 250, 255))

    image = Image.new("RGB", (width, 32), (0, 4, 9))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()
    draw.rectangle((3, 8, 18, 22), outline=(190, 150, 80))
    draw.line((3, 8, 10, 3, 18, 8), fill=(220, 175, 90))
    draw.line((10, 3, 10, 17), fill=(120, 90, 50))
    draw_sharp_text(image, (24, -3), carrier, (255, 210, 110), bold)
    words = status.upper().split()
    lines = [" ".join(words[:4]), " ".join(words[4:8])]
    y = 10
    for line in [l for l in lines if l][:2]:
        draw_sharp_text(image, (24, y), line[:22 if width == 128 else 10], (235, 245, 255), font)
        y += 9
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

