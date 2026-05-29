from io import BytesIO
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from card_utils import draw_sharp_text, render_text_webp
from _fantasy_espn import fetch_league, fmt_points, league_id, points_for, record, team_label

CARD_ID = "espn_fantasy_standings"
CARD_NAME = "ESPN Fantasy Standings"
CARD_DETAIL = "ESPN league standings"
CARD_OPTIONS = [
    {"key": "leagueId", "label": "ESPN League ID", "type": "text", "default": "", "maxlength": 32},
    {"key": "season", "label": "Season", "type": "number", "default": "2026", "min": 2018, "max": 2100},
    {"key": "showRows", "label": "Rows", "type": "select", "default": "5", "choices": [
        {"value": "3", "label": "3 teams"},
        {"value": "5", "label": "5 teams"},
        {"value": "8", "label": "8 teams"},
        {"value": "12", "label": "12 teams"},
    ]},
    {"key": "espnS2", "label": "espn_s2 Cookie (private leagues only)", "type": "password", "default": ""},
    {"key": "swid", "label": "SWID Cookie (private leagues only)", "type": "password", "default": ""},
]


def _fit(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1]
    return text


def _draw_rows(rows, width, offset=0):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (width, 32), (5, 4, 13))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()
    draw.rectangle((0, 0, width - 1, 8), fill=(28, 8, 18))
    title = "ESPN STANDINGS" if width == 128 else "ESPN"
    tw = draw.textbbox((0, 0), title, font=bold)[2]
    draw_sharp_text(image, ((width - tw) // 2, -3), title, (255, 80, 80), bold)
    for idx, row in enumerate(rows):
        y = 8 + idx * 8 - offset
        if y < 1 or y > 29:
            continue
        draw_sharp_text(image, (1, y), str(idx + 1), (255, 210, 80), font)
        if width == 128:
            draw_sharp_text(image, (10, y), _fit(draw, row["name"], font, 56), (245, 250, 255), font)
            draw_sharp_text(image, (72, y), row["record"], (120, 220, 255), font)
            pf = fmt_points(row["pf"])
            pw = draw.textbbox((0, 0), pf, font=font)[2]
            draw_sharp_text(image, (126 - pw, y), pf, (150, 170, 185), font)
        else:
            draw_sharp_text(image, (9, y), _fit(draw, row["name"], font, 28), (245, 250, 255), font)
            rw = draw.textbbox((0, 0), row["record"], font=font)[2]
            draw_sharp_text(image, (63 - rw, y), row["record"], (120, 220, 255), font)
    return image


def render(options=None):
    opts = options or {}
    if not league_id(opts):
        return render_text_webp("SET LEAGUE", (100, 180, 255))
    try:
        limit = max(3, min(12, int(opts.get("showRows") or 5)))
    except Exception:
        limit = 5
    try:
        data = fetch_league(opts)
        rows = [{"name": team_label(team).upper(), "record": record(team), "pf": points_for(team)} for team in data.get("teams") or []]
        rows.sort(key=lambda r: (int(r["record"].split("-")[0]), r["pf"]), reverse=True)
        rows = rows[:limit]
    except Exception:
        return render_text_webp("ESPN ERR", (238, 80, 80))
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
