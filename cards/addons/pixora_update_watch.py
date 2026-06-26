from io import BytesIO
import re

from card_utils import draw_sharp_text, fetch_json_request, fetch_json_with_headers, render_text_webp

CARD_ID = "pixora_update_watch"
CARD_NAME = "Pixora Update Watch"
CARD_DETAIL = "Pixora release and card updates"
CARD_OPTIONS = [
    {"key": "currentVersion", "label": "Current Pixora Version", "type": "text", "default": "1.3.18", "maxlength": 20},
    {"key": "cardRegistryUrl", "label": "Card Registry URL", "type": "text", "default": "https://raw.githubusercontent.com/bptworld/pixora/main/cards/registry.json", "maxlength": 160},
    {"key": "lastCardCount", "label": "Card Count At Last Check", "type": "number", "default": "0", "min": 0},
]


def _version_tuple(value):
    nums = re.findall(r"\d+", str(value or ""))
    return tuple(int(n) for n in nums[:4]) or (0,)


def _latest_pixora_version():
    data = fetch_json_with_headers(
        "https://api.github.com/repos/bptworld/pixora/releases/latest",
        {"Accept": "application/vnd.github+json"},
        seconds=900,
        cache_key="pixora:latest-release",
    )
    versions = []
    for item in data.get("assets") or []:
        name = item.get("name", "")
        match = re.match(r"PixoraSetup-v([0-9][0-9A-Za-z._-]*)\.exe$", name)
        if match:
            versions.append(match.group(1))
    if not versions:
        return ""
    return sorted(versions, key=_version_tuple)[-1]


def _remote_card_count(registry_url):
    data = fetch_json_request(registry_url, seconds=900)
    return len(data.get("cards") or [])


def _draw_center(image, draw, text, x1, x2, y, color, font):
    w = draw.textbbox((0, 0), text, font=font)[2]
    draw_sharp_text(image, (x1 + ((x2 - x1 + 1) - w) // 2, y), text, color, font)


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    current = (opts.get("currentVersion") or "").strip()
    registry_url = (opts.get("cardRegistryUrl") or "").strip()
    try:
        last_card_count = max(0, int(opts.get("lastCardCount") or 0))
    except Exception:
        last_card_count = 0
    if not current:
        return render_text_webp("SET VER", (100, 180, 255))
    if not registry_url:
        return render_text_webp("SET REG", (100, 180, 255))

    try:
        latest = _latest_pixora_version()
        remote_cards = _remote_card_count(registry_url)
    except Exception:
        return render_text_webp("UPD ERR", (238, 80, 80))

    app_new = latest and _version_tuple(latest) > _version_tuple(current)
    card_delta = max(0, remote_cards - last_card_count)
    if not app_new and card_delta <= 0:
        return None

    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    image = Image.new("RGB", (width, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    draw.rectangle((0, 0, width - 1, 6), fill=(5, 20, 24))
    _draw_center(image, draw, "PIXORA UPDATE", 0, width - 1, -3, (80, 225, 205), bold)

    y = 9
    if app_new:
        draw_sharp_text(image, (1, y), "APP", (145, 165, 182), font)
        text = "v" + latest
        w = draw.textbbox((0, 0), text, font=bold)[2]
        draw_sharp_text(image, (width - 1 - w, y - 1), text, (245, 250, 255), bold)
        y += 9

    if card_delta > 0:
        draw_sharp_text(image, (1, y), "CARDS", (145, 165, 182), font)
        text = f"+{card_delta}"
        w = draw.textbbox((0, 0), text, font=bold)[2]
        draw_sharp_text(image, (width - 1 - w, y - 1), text, (255, 210, 80), bold)
        y += 9

    if app_new and card_delta > 0:
        _draw_center(image, draw, "BOTH READY", 0, width - 1, 22, (150, 170, 185), font)
    elif app_new:
        _draw_center(image, draw, "NEW RELEASE", 0, width - 1, 22, (150, 170, 185), font)
    else:
        _draw_center(image, draw, "NEW CARDS", 0, width - 1, 22, (150, 170, 185), font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

