from datetime import datetime, timezone
from io import BytesIO
import random
import re

from card_utils import draw_sharp_text, fetch_json_request, pixora_local_timezone, render_text_webp

PARKS = [
    {"value": "eb3f4560-2383-4a36-9152-6b3e5ed6bc57", "label": "Universal Studios Florida"},
    {"value": "267615cc-8943-4c2a-ae2c-5da728ca591f", "label": "Islands of Adventure"},
    {"value": "12dbb85b-265f-44e6-bccf-f1faa17211fc", "label": "Epic Universe"},
    {"value": "fe78a026-b91b-470c-b906-9d2266b692da", "label": "Volcano Bay"},
    {"value": "bc4005c5-8c7e-41d7-b349-cdddf1796427", "label": "Universal Studios Hollywood"},
]

LIVE_URL = "https://api.themeparks.wiki/v1/entity/{park_id}/live"
CHILDREN_URL = "https://api.themeparks.wiki/v1/entity/{park_id}/children"
SCHEDULE_URL = "https://api.themeparks.wiki/v1/entity/{park_id}/schedule"
BLUE = (76, 180, 255)
AMBER = (255, 188, 74)
BG = (4, 8, 18)
HEADER = (8, 20, 44)


def safe_text(value, default=""):
    return re.sub(r"\s+", " ", str(value or default)).strip()


def park_abbr(park_id):
    for park in PARKS:
        if park["value"] == park_id:
            label = park["label"]
            return {
                "Universal Studios Florida": "USF",
                "Islands of Adventure": "IOA",
                "Epic Universe": "EPIC",
                "Volcano Bay": "VB",
                "Universal Studios Hollywood": "USH",
            }.get(label, label.upper())
    return "UNIV"


def park_name(park_id):
    for park in PARKS:
        if park["value"] == park_id:
            return park["label"].upper()
    return "UNIVERSAL"


def fit_text(draw, text, font, max_width):
    text = str(text or "").strip().upper()
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1].rstrip()
    return text


def fonts():
    from PIL import ImageFont

    try:
        return {
            "header": ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8),
            "text": ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8),
            "number": ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8),
            "tiny": ImageFont.truetype("assets/fonts/PixelifySans.ttf", 6),
        }
    except Exception:
        font = ImageFont.load_default()
        return {"header": font, "text": font, "number": font, "tiny": font}


def draw_background(img, draw):
    for y in range(32):
        if y < 9:
            color = HEADER
        else:
            blend = (y - 9) / 22
            color = (
                round(4 + 5 * (1 - blend)),
                round(8 + 12 * (1 - blend)),
                round(18 + 26 * (1 - blend)),
            )
        draw.line((0, y, img.width - 1, y), fill=color)
    draw.line((0, 8, img.width - 1, 8), fill=(28, 96, 150))


def draw_twinkles(img, seed):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    rng = random.Random(seed)
    palette = [(170, 230, 255), (255, 200, 100), (100, 170, 255), (245, 250, 255)]
    zones = [(1, 10, img.width - 2, 14), (1, 26, img.width - 2, 30), (1, 15, 16, 24), (img.width - 18, 15, img.width - 2, 24)]
    for index in range(7 if img.width >= 128 else 5):
        x1, y1, x2, y2 = zones[index % len(zones)]
        x = rng.randint(x1, x2)
        y = rng.randint(y1, y2)
        color = palette[rng.randrange(len(palette))]
        draw.point((x, y), fill=color)
        if rng.random() < 0.45 and 1 <= x < img.width - 1 and 1 <= y < 31:
            draw.point((x + 1, y), fill=(28, 80, 140))
            draw.point((x, y + 1), fill=(28, 80, 140))


def draw_globe(img, draw, x, y, size):
    cx = x + size // 2
    cy = y + size // 2
    r = size // 2 - 1
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=BLUE, width=2)
    draw.arc((cx - r + 4, cy - r, cx + r - 4, cy + r), 78, 282, fill=(120, 220, 255), width=1)
    draw.arc((cx - r + 4, cy - r, cx + r - 4, cy + r), 258, 102, fill=(120, 220, 255), width=1)
    draw.line((cx - r + 2, cy, cx + r - 2, cy), fill=(120, 220, 255), width=1)
    draw.line((cx, cy - r + 2, cx, cy + r - 2), fill=(45, 118, 190), width=1)
    draw.arc((cx - r - 3, cy - 3, cx + r + 3, cy + r + 2), 205, 335, fill=AMBER, width=2)
    return size + 2


def center(image, draw, text, y, color, font, x1=0, x2=None):
    x2 = image.width - 1 if x2 is None else x2
    w = draw.textbbox((0, 0), text, font=font)[2]
    draw_sharp_text(image, (x1 + ((x2 - x1 + 1) - w) // 2, y), text, color, font)


def parse_dt(value):
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except Exception:
        return None


def time_label(value, compact=False):
    dt = parse_dt(value)
    if not dt:
        return "--"
    local_tz = pixora_local_timezone()
    if dt.tzinfo and local_tz:
        dt = dt.astimezone(local_tz)
    if compact and dt.minute == 0:
        label = dt.strftime("%I%p").lstrip("0")
    else:
        label = dt.strftime("%I:%M%p").lstrip("0")
    return label.replace(":00", "").replace("AM", "A").replace("PM", "P")


def live_items(park_id):
    data = fetch_json_request(LIVE_URL.format(park_id=park_id), seconds=180)
    items = data.get("liveData") if isinstance(data, dict) else []
    return items if isinstance(items, list) else []


def child_items(park_id):
    data = fetch_json_request(CHILDREN_URL.format(park_id=park_id), seconds=86400)
    items = data.get("children") if isinstance(data, dict) else []
    return items if isinstance(items, list) else []


def save_webp(frames, durations=500):
    out = BytesIO()
    if len(frames) == 1:
        frames[0].save(out, "WEBP", lossless=True, quality=100)
    else:
        frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=durations, loop=0, lossless=True, quality=100)
    return out.getvalue()
