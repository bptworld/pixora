from io import BytesIO
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from card_utils import draw_sharp_text, render_text_webp
from _fantasy_yahoo import access_token, fmt_points, league_key, record, standings

CARD_ID = "yahoo_fantasy_standings"
CARD_NAME = "Yahoo Fantasy Standings"
CARD_DETAIL = "Yahoo league standings"
CARD_OPTIONS = [
    {"key": "leagueKey", "label": "Yahoo League Key", "type": "text", "default": "", "maxlength": 40},
    {"key": "showRows", "label": "Rows", "type": "select", "default": "5", "choices": [
        {"value": "3", "label": "3 teams"},
        {"value": "5", "label": "5 teams"},
        {"value": "8", "label": "8 teams"},
        {"value": "12", "label": "12 teams"},
    ]},
    {"key": "accessToken", "label": "Yahoo OAuth Access Token", "type": "password", "default": ""},
]


def _fit(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1]
    return text


def _draw_rows(rows, width, offset=0):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (width, 32), (8, 5, 2))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()
    draw.rectangle((0, 0, width - 1, 6), fill=(36, 14, 58))
    title = "YAHOO STANDINGS" if width == 128 else "YAHOO"
    tw = draw.textbbox((0, 0), title, font=bold)[2]
    draw_sharp_text(image, ((width - tw) // 2, -3), title, (190, 130, 255), bold)
    for idx, row in enumerate(rows):
        y = 8 + idx * 8 - offset
        if y < 1 or y > 29:
            continue
        draw_sharp_text(image, (1, y), str(row.get("rank") or idx + 1), (255, 210, 80), font)
        name = str(row.get("name") or "TEAM").upper()
        if width == 128:
            draw_sharp_text(image, (12, y), _fit(draw, name, font, 54), (245, 250, 255), font)
            draw_sharp_text(image, (72, y), record(row), (120, 220, 255), font)
            pf = fmt_points(row.get("points") or row.get("percentage"))
            pw = draw.textbbox((0, 0), pf, font=font)[2]
            draw_sharp_text(image, (126 - pw, y), pf, (150, 170, 185), font)
        else:
            draw_sharp_text(image, (10, y), _fit(draw, name, font, 28), (245, 250, 255), font)
            rw = draw.textbbox((0, 0), record(row), font=font)[2]
            draw_sharp_text(image, (63 - rw, y), record(row), (120, 220, 255), font)
    return image


def render(options=None):
    opts = options or {}
    if not league_key(opts):
        return render_text_webp("SET LEAGUE", (100, 180, 255))
    if not access_token(opts):
        return render_text_webp("SET TOKEN", (255, 190, 80))
    try:
        limit = max(3, min(12, int(opts.get("showRows") or 5)))
        rows = standings(opts)[:limit]
    except Exception:
        return render_text_webp("YHOO ERR", (238, 80, 80))
    if not rows:
        return render_text_webp("NO TEAMS", (160, 170, 185))
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    if len(rows) <= 3:
        out = BytesIO()
        _draw_rows(rows, width).save(out, "WEBP", lossless=True, quality=100)
        return out.getvalue()
    max_offset = (len(rows) - 3) * 8
    offsets = [0] + list(range(1, max_offset + 1)) + [max_offset]
    frames = [_draw_rows(rows, width, off) for off in offsets]
    durations = [3000] + [220] * max_offset + [3000]
    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=durations, loop=0, lossless=True, quality=100)
    return {"body": out.getvalue(), "dwell_secs": max(8, round(sum(durations) / 1000)), "_stay": False}
