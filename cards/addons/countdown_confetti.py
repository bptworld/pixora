from io import BytesIO
from datetime import date

from card_utils import draw_sharp_text_weighted, pixora_local_now

CARD_ID = "countdown_confetti"
CARD_NAME = "Countdown Confetti"
CARD_DETAIL = "Event countdown with confetti"
CARD_OPTIONS = [
    {"key": "eventName", "label": "Event", "type": "text", "default": "PARTY", "maxlength": 10},
    {"key": "targetDate", "label": "Date", "type": "date", "default": ""},
]


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    event = (opts.get("eventName") or "PARTY").upper()[:10]
    target = opts.get("targetDate") or ""
    try:
        days = (date.fromisoformat(target) - pixora_local_now().date()).days
    except Exception:
        days = None

    frames = []
    try:
        font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 20)
    except Exception:
        font = big = ImageFont.load_default()

    dwell_ms = max(3000, min(60000, int(opts.get("_dwell", 10) or 10) * 1000))
    frame_count = max(14, min(72, int(round(dwell_ms / 120))))
    frame_duration = max(45, int(round(dwell_ms / frame_count)))

    for frame in range(frame_count):
        image = Image.new("RGB", (width, 32), (4, 3, 16))
        draw = ImageDraw.Draw(image)
        for i in range(32 if width == 128 else 18):
            x = (i * 11 + frame * 3) % width
            y = (i * 7 + frame * 2) % 32
            color = [(255,80,120), (80,220,255), (255,220,60), (120,255,120)][i % 4]
            draw.point((x, y), fill=color)
        label = "SET DATE" if days is None else ("TODAY!" if days == 0 else f"{max(0, days)}D")
        ew = draw.textbbox((0, 0), event, font=font)[2]
        draw.text(((width - ew) // 2, -3), event, fill=(255, 230, 120), font=font)
        if days is not None and days > 0:
            num_str = str(max(0, days))
            nb = draw.textbbox((0, 0), num_str, font=big)
            nw = nb[2] - nb[0]
            db = draw.textbbox((0, 0), "D", font=big)
            dw = db[2] - db[0]
            total_w = nw + 2 + dw
            x = (width - total_w) // 2
            draw_sharp_text_weighted(image, (x - 1, 2), num_str, (255, 255, 255), big, weight=2)
            draw.text((x + nw + 2, 9), "D", fill=(255, 255, 255), font=big)
        else:
            lw = draw.textbbox((0, 0), label, font=big if days is not None else font)[2]
            draw.text(((width - lw) // 2, 9), label, fill=(255, 255, 255), font=big if days is not None else font)
        frames.append(image)

    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:],
                   duration=frame_duration, loop=1, lossless=True, quality=100)
    return out.getvalue()
