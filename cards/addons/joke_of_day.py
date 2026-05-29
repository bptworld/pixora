from io import BytesIO

from card_utils import draw_sharp_text, fetch_json_request, render_message_wrap

CARD_ID = "joke_of_day"
CARD_NAME = "Joke of the Day"
CARD_DETAIL = "Tiny clean joke"
CARD_OPTIONS = [
    {
        "key": "style",
        "label": "Style",
        "type": "select",
        "default": "daily",
        "choices": [
            {"value": "daily", "label": "Daily joke"},
            {"value": "random", "label": "Random joke"},
        ],
    }
]

FALLBACK = "I told my LED matrix a joke. It lit up."


def _joke():
    try:
        data = fetch_json_request("https://official-joke-api.appspot.com/jokes/general/random", seconds=21600)
        if isinstance(data, list) and data:
            item = data[0]
            return f"{item.get('setup', '')} {item.get('punchline', '')}".strip()
    except Exception:
        pass
    return FALLBACK


def render(options=None):
    opts = options or {}
    if opts.get("_target") != "matrixportal-s3-128x32":
        return render_message_wrap(_joke()[:100], (255, 220, 80))
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (128, 32), (8, 4, 0))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("Silkscreen-Regular.ttf", 8)
    except Exception:
        font = ImageFont.load_default()
    text = _joke()[:140].upper()
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip() if current else word
        if draw.textbbox((0, 0), test, font=font)[2] <= 124:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    y = (32 - min(4, len(lines)) * 8) // 2 - 3
    for line in lines[:4]:
        w = draw.textbbox((0, 0), line, font=font)[2]
        draw_sharp_text(image, ((128 - w) // 2, y), line, (255, 220, 80), font)
        y += 8
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
