from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from card_utils import (
    cached_json,
    card_context,
    card_state,
    contrast_text_color,
    fallback_frame,
    option_target,
    option_text,
    paste_image_asset,
    pixora_log,
    special_graphic,
)


CARD_ID = "starter_custom_card"
CARD_NAME = "Starter Custom Card"
CARD_DETAIL = "Template showing safe helpers, options, rule values, and special graphics."
CARD_VERSION = "1.0.0"
CARD_AUTHOR = "Your Name"
CARD_LICENSE = "MIT"
CARD_ALLOWED_DOMAINS = ["api.example.com", "assets.example.com"]
REQUIRED_SETTINGS = []
TAGS = ["template", "community"]
RULE_VALUES = [
    {"key": "status", "label": "Status"},
    {"key": "count", "label": "Count"},
]

CARD_OPTIONS = [
    option_text("label", "Label", "Pixora"),
    option_target("alertTarget", "Alert Graphic", default="device"),
]


def _font(size=8):
    try:
        return ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _webp(image):
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _status_payload(options):
    if (options or {}).get("_is_prefetch"):
        return {"status": "preview", "count": 1, "logo": ""}
    try:
        return cached_json("https://api.example.com/status", ttl_secs=300)
    except Exception:
        return {"status": "offline", "count": 0, "logo": ""}


def render_alert_animation(team, kind="alert"):
    width = int(team.get("_width") or 64)
    frames = []
    durations = []
    for frame in range(8):
        image = Image.new("RGB", (width, 32), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        color = (255, 220, 80) if frame % 2 == 0 else (80, 220, 255)
        draw.rectangle((0, 0, width - 1, 31), outline=color)
        draw.text((4, 11), str(team.get("label") or "ALERT")[:18], fill=color, font=_font())
        frames.append(image)
        durations.append(100)
    return frames, durations


def render(options=None):
    ctx = card_context(options)
    payload = _status_payload(options)
    label = str((options or {}).get("label") or payload.get("status") or "Pixora")
    count = int(payload.get("count") or 0)
    if not label:
        return fallback_frame("No data", width=ctx["width"], dwell_secs=6)

    image = Image.new("RGB", (ctx["width"], 32), (4, 8, 12))
    draw = ImageDraw.Draw(image)
    accent = (40, 220, 200)
    text_color = contrast_text_color(accent)
    draw.rectangle((0, 0, ctx["width"] - 1, 31), outline=accent)
    draw.rectangle((2, 2, min(ctx["width"] - 3, 33), 29), fill=accent)
    draw.text((6, 11), str(count)[:3], fill=text_color, font=_font())
    draw.text((38, 7), label[:18], fill=(230, 245, 255), font=_font())
    draw.text((38, 18), "CUSTOM", fill=(120, 190, 255), font=_font())
    paste_image_asset(image, str(payload.get("logo") or ""), (ctx["width"] - 18, 8), size=14)

    state = card_state(CARD_ID)
    previous_count = int(state.get("count", count) or 0)
    state.set("count", count)
    pixora_log(options, f"rendered count={count}")

    result = {"body": _webp(image), "dwell_secs": ctx["dwell_secs"]}
    target = str((options or {}).get("alertTarget") or "device").lower()
    if count > previous_count and target != "off":
        result.update(
            special_graphic(
                renderer="render_alert_animation",
                wall_renderer="render_alert_animation",
                kind="alert",
                team={"label": label, "count": count},
                dwell_secs=5,
                include_device=True,
                include_wall=target in ("group", "group_wall", "wall"),
                stay=True,
            )
        )
    return result


def rule_value(options=None, field=""):
    payload = _status_payload(options)
    if field == "count":
        return int(payload.get("count") or 0)
    return str(payload.get("status") or "")
