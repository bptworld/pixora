from io import BytesIO

from card_utils import draw_sharp_text, fetch_json_request, render_message_wrap

CARD_ID = "quote_of_day"
CARD_NAME = "Quote of the Day"
CARD_DETAIL = "Short daily quote"
CARD_OPTIONS = [
    {"key": "fallbackQuote", "label": "Fallback Quote", "type": "text", "default": "Make today useful.", "maxlength": 60},
]

FALLBACKS = [
    "Make today useful.",
    "Small steps still move.",
    "Keep building.",
    "Choose the next right thing.",
    "Attention turns work into craft.",
]


def _quote(opts):
    try:
        data = fetch_json_request("https://zenquotes.io/api/today", seconds=21600)
        if isinstance(data, list) and data:
            return data[0].get("q") or data[0].get("quote")
    except Exception:
        pass
    return (opts.get("fallbackQuote") or FALLBACKS[0]).strip() or FALLBACKS[0]


def render(options=None):
    opts = options or {}
    if opts.get("_target") != "matrixportal-s3-128x32":
        return render_message_wrap(_quote(opts)[:90], (245, 250, 255))
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (128, 32), (0, 4, 10))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("Silkscreen-Regular.ttf", 8)
    except Exception:
        font = ImageFont.load_default()
    text = _quote(opts)[:140].upper()
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
        draw_sharp_text(image, ((128 - w) // 2, y), line, (245, 250, 255), font)
        y += 8
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
