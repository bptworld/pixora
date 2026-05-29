from io import BytesIO
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from card_utils import draw_sharp_text, render_text_webp
from _fantasy_espn import fetch_league, fmt_points, league_id, matchup_for_team, option_week, resolve_team, team_label, teams_by_id

WEEK_CHOICES = [{"value": "auto", "label": "Auto"}] + [
    {"value": str(week), "label": f"Week {week}"} for week in range(1, 19)
]

CARD_ID = "espn_fantasy_matchup"
CARD_NAME = "ESPN Fantasy Matchup"
CARD_DETAIL = "ESPN weekly matchup score"
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


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    if not league_id(opts):
        return render_text_webp("SET LEAGUE", (100, 180, 255))
    try:
        data = fetch_league(opts)
        week = option_week(opts, data)
        team = resolve_team(data, opts)
        if not team:
            return render_text_webp("SET TEAM", (255, 190, 80))
        mine, opp = matchup_for_team(data, week, team.get("id"))
        if not mine:
            return render_text_webp("NO MATCH", (160, 170, 185))
        teams = teams_by_id(data)
        opp_team = teams.get(int((opp or {}).get("teamId") or 0), {})
    except Exception:
        return render_text_webp("ESPN ERR", (238, 80, 80))

    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    image = Image.new("RGB", (width, 32), (5, 4, 13))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("Silkscreen-Regular.ttf", 14)
    except Exception:
        font = bold = big = ImageFont.load_default()
    draw.rectangle((0, 0, width - 1, 8), fill=(28, 8, 18))
    title = f"ESPN FANTASY W{week}"
    tw = draw.textbbox((0, 0), title, font=bold)[2]
    draw_sharp_text(image, ((width - tw) // 2, -3), title, (255, 80, 80), bold)
    my_name = team_label(team).upper()
    opp_name = team_label(opp_team).upper() if opp_team else "OPP"
    my_score = fmt_points(mine.get("totalPoints"))
    opp_score = fmt_points((opp or {}).get("totalPoints")) if opp else "--"
    if width == 128:
        draw_sharp_text(image, (2, 9), _fit(draw, my_name, font, 48), (245, 250, 255), font)
        draw_sharp_text(image, (78, 9), _fit(draw, opp_name, font, 48), (245, 250, 255), font)
        draw_sharp_text(image, (2, 20), my_score, (80, 235, 150), big)
        ow = draw.textbbox((0, 0), opp_score, font=big)[2]
        draw_sharp_text(image, (126 - ow, 20), opp_score, (255, 210, 80), big)
        draw_sharp_text(image, (59, 18), "VS", (120, 140, 165), font)
    else:
        draw_sharp_text(image, (1, 8), _fit(draw, my_name, font, 32), (245, 250, 255), font)
        opp_fit = _fit(draw, opp_name, font, 32)
        ow = draw.textbbox((0, 0), opp_fit, font=font)[2]
        draw_sharp_text(image, (63 - ow, 8), opp_fit, (245, 250, 255), font)
        draw_sharp_text(image, (1, 19), my_score, (80, 235, 150), bold)
        sw = draw.textbbox((0, 0), opp_score, font=bold)[2]
        draw_sharp_text(image, (63 - sw, 19), opp_score, (255, 210, 80), bold)
        draw_sharp_text(image, (28, 19), "VS", (120, 140, 165), font)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
