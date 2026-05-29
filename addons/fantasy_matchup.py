from io import BytesIO

from card_utils import draw_sharp_text, render_text_webp
from _fantasy_sleeper import (
    fmt_points,
    league_id,
    matchup_for_roster,
    option_week,
    resolve_roster,
    roster_by_id,
    team_name,
    user_map,
)

WEEK_CHOICES = [{"value": "auto", "label": "Auto"}] + [
    {"value": str(week), "label": f"Week {week}"} for week in range(1, 19)
]

CARD_ID = "fantasy_matchup"
CARD_NAME = "Fantasy Matchup"
CARD_DETAIL = "Sleeper weekly matchup score"
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


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    lid = league_id(opts)
    if not lid:
        return render_text_webp("SET LEAGUE", (100, 180, 255))
    try:
        week = option_week(opts)
        roster = resolve_roster(lid, opts)
        if not roster:
            return render_text_webp("SET TEAM", (255, 190, 80))
        mine, opp = matchup_for_roster(lid, week, roster.get("roster_id"))
        if not mine:
            return render_text_webp("NO MATCH", (160, 170, 185))
        lookup = user_map(lid)
        opp_roster = roster_by_id(lid, opp.get("roster_id")) if opp else None
    except Exception:
        return render_text_webp("FANT ERR", (238, 80, 80))

    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    image = Image.new("RGB", (width, 32), (3, 5, 14))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("Silkscreen-Regular.ttf", 14)
    except Exception:
        font = bold = big = ImageFont.load_default()

    draw.rectangle((0, 0, width - 1, 8), fill=(15, 17, 38))
    title = f"FANTASY W{week}"
    tw = draw.textbbox((0, 0), title, font=bold)[2]
    draw_sharp_text(image, ((width - tw) // 2, -3), title, (160, 120, 255), bold)

    my_name = team_name(roster, lookup).upper()
    opp_name = team_name(opp_roster, lookup).upper() if opp_roster else "OPP"
    my_score = fmt_points(mine.get("points"))
    opp_score = fmt_points(opp.get("points")) if opp else "--"

    if width == 128:
        draw_sharp_text(image, (2, 9), _fit(draw, my_name, font, 48), (245, 250, 255), font)
        draw_sharp_text(image, (78, 9), _fit(draw, opp_name, font, 48), (245, 250, 255), font)
        draw_sharp_text(image, (2, 20), my_score, (80, 235, 150), big)
        ow = draw.textbbox((0, 0), opp_score, font=big)[2]
        draw_sharp_text(image, (126 - ow, 20), opp_score, (255, 210, 80), big)
        draw_sharp_text(image, (59, 18), "VS", (120, 140, 165), font)
    else:
        draw_sharp_text(image, (1, 8), _fit(draw, my_name, font, 32), (245, 250, 255), font)
        ow = draw.textbbox((0, 0), _fit(draw, opp_name, font, 32), font=font)[2]
        draw_sharp_text(image, (63 - ow, 8), _fit(draw, opp_name, font, 32), (245, 250, 255), font)
        draw_sharp_text(image, (1, 19), my_score, (80, 235, 150), bold)
        sw = draw.textbbox((0, 0), opp_score, font=bold)[2]
        draw_sharp_text(image, (63 - sw, 19), opp_score, (255, 210, 80), bold)
        draw_sharp_text(image, (28, 19), "VS", (120, 140, 165), font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
