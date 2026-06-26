from io import BytesIO
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from card_utils import draw_sharp_text, render_text_webp
from _fantasy_yahoo import access_token, fmt_points, league_key, lineup, team_key_for

WEEK_CHOICES = [{"value": "auto", "label": "Auto"}] + [
    {"value": str(week), "label": f"Week {week}"} for week in range(1, 19)
]

CARD_ID = "yahoo_fantasy_lineup"
CARD_NAME = "Yahoo Fantasy Lineup"
CARD_DETAIL = "Yahoo starter points"
CARD_OPTIONS = [
    {"key": "leagueKey", "label": "Yahoo League Key", "type": "text", "default": "", "maxlength": 40},
    {"key": "teamKey", "label": "Yahoo Team Key", "type": "text", "default": "", "maxlength": 48},
    {"key": "teamId", "label": "Team ID", "type": "number", "default": "", "min": 1, "max": 99},
    {"key": "week", "label": "Week", "type": "select", "default": "auto", "choices": WEEK_CHOICES},
    {"key": "accessToken", "label": "Yahoo OAuth Access Token", "type": "password", "default": ""},
]


def _fit(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1]
    return text


def _draw(rows, width, offset=0):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (width, 32), (8, 5, 2))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()
    draw.rectangle((0, 0, width - 1, 6), fill=(36, 14, 58))
    title = "YAHOO LINEUP"
    tw = draw.textbbox((0, 0), title, font=bold)[2]
    draw_sharp_text(image, ((width - tw) // 2, -3), title, (190, 130, 255), bold)
    for idx, row in enumerate(rows):
        y = 8 + idx * 8 - offset
        if y < 1 or y > 29:
            continue
        name = str(row.get("name") or "PLAYER").upper()
        pts = fmt_points(row.get("points"))
        if width == 128:
            draw_sharp_text(image, (1, y), _fit(draw, name, font, 74), (245, 250, 255), font)
            pw = draw.textbbox((0, 0), pts, font=font)[2]
            draw_sharp_text(image, (126 - pw, y), pts, (80, 235, 150), font)
        else:
            draw_sharp_text(image, (1, y), _fit(draw, name, font, 44), (245, 250, 255), font)
            pw = draw.textbbox((0, 0), pts, font=font)[2]
            draw_sharp_text(image, (63 - pw, y), pts, (80, 235, 150), font)
    return image


def render(options=None):
    opts = options or {}
    if not league_key(opts) or not team_key_for(opts):
        return render_text_webp("SET TEAM", (100, 180, 255))
    if not access_token(opts):
        return render_text_webp("SET TOKEN", (255, 190, 80))
    try:
        rows = lineup(opts)
    except Exception:
        return render_text_webp("YHOO ERR", (238, 80, 80))
    if not rows:
        return render_text_webp("NO LINEUP", (160, 170, 185))
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    if len(rows) <= 3:
        out = BytesIO()
        _draw(rows, width).save(out, "WEBP", lossless=True, quality=100)
        return out.getvalue()
    max_offset = (len(rows) - 3) * 8
    offsets = [0] + list(range(1, max_offset + 1)) + [max_offset]
    frames = [_draw(rows, width, off) for off in offsets]
    durations = [3000] + [220] * max_offset + [3000]
    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=durations, loop=0, lossless=True, quality=100)
    return {"body": out.getvalue(), "dwell_secs": max(8, round(sum(durations) / 1000)), "_stay": False}
