from io import BytesIO
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from card_utils import draw_sharp_text, render_text_webp
from _fantasy_espn import fetch_league, league_id, lineup_entries, matchup_for_team, option_week, resolve_team

WEEK_CHOICES = [{"value": "auto", "label": "Auto"}] + [
    {"value": str(week), "label": f"Week {week}"} for week in range(1, 19)
]

CARD_ID = "espn_fantasy_lineup"
CARD_NAME = "ESPN Fantasy Lineup"
CARD_DETAIL = "ESPN starter points"
CARD_OPTIONS = [
    {"key": "leagueId", "label": "ESPN League ID", "type": "text", "default": "", "maxlength": 32},
    {"key": "season", "label": "Season", "type": "number", "default": "2026", "min": 2018, "max": 2100},
    {"key": "teamId", "label": "Team ID", "type": "number", "default": "", "min": 1, "max": 99},
    {"key": "teamAbbrev", "label": "Team Abbrev", "type": "text", "default": "", "maxlength": 8},
    {"key": "teamName", "label": "Team Name Contains", "type": "text", "default": "", "maxlength": 40},
    {"key": "week", "label": "Week", "type": "select", "default": "auto", "choices": WEEK_CHOICES},
    {"key": "espnS2", "label": "espn_s2 Cookie (private leagues only)", "type": "password", "default": ""},
    {"key": "swid", "label": "SWID Cookie (private leagues only)", "type": "password", "default": ""},
]


def _fit(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1]
    return text


def _draw(rows, width, week, offset=0):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (width, 32), (5, 4, 13))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()
    draw.rectangle((0, 0, width - 1, 6), fill=(28, 8, 18))
    title = f"ESPN LINEUP W{week}"
    tw = draw.textbbox((0, 0), title, font=bold)[2]
    draw_sharp_text(image, ((width - tw) // 2, -3), title, (255, 80, 80), bold)
    for idx, row in enumerate(rows):
        y = 8 + idx * 8 - offset
        if y < 1 or y > 29:
            continue
        if width == 128:
            draw_sharp_text(image, (1, y), _fit(draw, row["name"], font, 74), (245, 250, 255), font)
            pw = draw.textbbox((0, 0), row["points"], font=font)[2]
            draw_sharp_text(image, (126 - pw, y), row["points"], (80, 235, 150), font)
        else:
            draw_sharp_text(image, (1, y), _fit(draw, row["name"], font, 44), (245, 250, 255), font)
            pw = draw.textbbox((0, 0), row["points"], font=font)[2]
            draw_sharp_text(image, (63 - pw, y), row["points"], (80, 235, 150), font)
    return image


def render(options=None):
    opts = options or {}
    if not league_id(opts):
        return render_text_webp("SET LEAGUE", (100, 180, 255))
    try:
        data = fetch_league(opts)
        week = option_week(opts, data)
        team = resolve_team(data, opts)
        if not team:
            return render_text_webp("SET TEAM", (255, 190, 80))
        mine, _ = matchup_for_team(data, week, team.get("id"))
        rows = lineup_entries(mine or {})
    except Exception:
        return render_text_webp("ESPN ERR", (238, 80, 80))
    if not rows:
        return render_text_webp("NO LINEUP", (160, 170, 185))
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    if len(rows) <= 3:
        out = BytesIO()
        _draw(rows, width, week).save(out, "WEBP", lossless=True, quality=100)
        return out.getvalue()
    max_offset = (len(rows) - 3) * 8
    offsets = [0] + list(range(1, max_offset + 1)) + [max_offset]
    frames = [_draw(rows, width, week, off) for off in offsets]
    durations = [3000] + [220] * max_offset + [3000]
    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=durations, loop=0, lossless=True, quality=100)
    return {"body": out.getvalue(), "dwell_secs": max(8, round(sum(durations) / 1000)), "_stay": False}
