from io import BytesIO

from card_utils import draw_sharp_text, render_text_webp
from _fantasy_sleeper import (
    fmt_points,
    league_id,
    matchup_for_roster,
    option_week,
    player_name,
    resolve_roster,
)

WEEK_CHOICES = [{"value": "auto", "label": "Auto"}] + [
    {"value": str(week), "label": f"Week {week}"} for week in range(1, 19)
]

CARD_ID = "fantasy_lineup"
CARD_NAME = "Fantasy Lineup"
CARD_DETAIL = "Sleeper starter points"
CARD_OPTIONS = [
    {"key": "leagueId", "label": "Sleeper League ID", "type": "text", "default": "", "maxlength": 32},
    {"key": "username", "label": "Sleeper Username", "type": "text", "default": "", "maxlength": 40},
    {"key": "teamName", "label": "Team Name Contains", "type": "text", "default": "", "maxlength": 40},
    {"key": "rosterId", "label": "Roster ID", "type": "number", "default": "", "min": 1, "max": 99},
    {"key": "week", "label": "Week", "type": "select", "default": "auto", "choices": WEEK_CHOICES},
]


def _fit(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1]
    return text


def _draw(rows, width, week, offset=0):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (width, 32), (3, 5, 14))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()
    draw.rectangle((0, 0, width - 1, 8), fill=(15, 17, 38))
    title = f"LINEUP W{week}"
    tw = draw.textbbox((0, 0), title, font=bold)[2]
    draw_sharp_text(image, ((width - tw) // 2, -3), title, (160, 120, 255), bold)
    for idx, row in enumerate(rows):
        y = 8 + idx * 8 - offset
        if y < 1 or y > 29:
            continue
        if width == 128:
            draw_sharp_text(image, (1, y), _fit(draw, row["name"], font, 62), (245, 250, 255), font)
            draw_sharp_text(image, (70, y), _fit(draw, row["meta"], font, 28), (120, 140, 165), font)
            pw = draw.textbbox((0, 0), row["points"], font=font)[2]
            draw_sharp_text(image, (126 - pw, y), row["points"], (80, 235, 150), font)
        else:
            draw_sharp_text(image, (1, y), _fit(draw, row["name"], font, 44), (245, 250, 255), font)
            pw = draw.textbbox((0, 0), row["points"], font=font)[2]
            draw_sharp_text(image, (63 - pw, y), row["points"], (80, 235, 150), font)
    return image


def render(options=None):
    opts = options or {}
    lid = league_id(opts)
    if not lid:
        return render_text_webp("SET LEAGUE", (100, 180, 255))
    try:
        week = option_week(opts)
        roster = resolve_roster(lid, opts)
        if not roster:
            return render_text_webp("SET TEAM", (255, 190, 80))
        mine, _ = matchup_for_roster(lid, week, roster.get("roster_id"))
        if not mine:
            return render_text_webp("NO LINEUP", (160, 170, 185))
        player_points = mine.get("players_points") or {}
        rows = []
        for player_id in mine.get("starters") or []:
            if not player_id or str(player_id) == "0":
                continue
            name, meta = player_name(player_id)
            rows.append({"name": name.upper(), "meta": meta.upper(), "points": fmt_points(player_points.get(str(player_id)))})
    except Exception:
        return render_text_webp("FANT ERR", (238, 80, 80))
    if not rows:
        return render_text_webp("NO LINEUP", (160, 170, 185))

    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    visible = 3
    if len(rows) <= visible:
        out = BytesIO()
        _draw(rows, width, week).save(out, "WEBP", lossless=True, quality=100)
        return out.getvalue()
    max_offset = (len(rows) - visible) * 8
    offsets = [0] + list(range(1, max_offset + 1)) + [max_offset]
    frames = [_draw(rows, width, week, off) for off in offsets]
    durations = [3000] + [220] * max_offset + [3000]
    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=durations, loop=0, lossless=True, quality=100)
    return {"body": out.getvalue(), "dwell_secs": max(8, round(sum(durations) / 1000)), "_stay": False}
