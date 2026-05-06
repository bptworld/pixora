from io import BytesIO

CARD_ID = "starter"
CARD_NAME = "Starter"
CARD_DETAIL = "Example Hubyt card"
CARD_OPTIONS = [
    {
        "key": "message",
        "label": "Text",
        "type": "text",
        "default": "HELLO",
        "maxlength": 10
    }
]


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    options = options or {}
    message = str(options.get("message", "HELLO")).upper()[:10]

    image = Image.new("RGB", (64, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.truetype("Silkscreen-Bold.ttf", 8)
    except Exception:
        font = ImageFont.load_default()

    box = draw.textbbox((0, 0), message, font=font)
    width = box[2] - box[0]
    height = box[3] - box[1]
    x = max(0, (64 - width) // 2)
    y = max(0, (32 - height) // 2 - 2)

    draw.text((x, y), message, fill=(20, 149, 255), font=font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
