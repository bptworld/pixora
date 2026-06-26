from io import BytesIO
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from card_utils import draw_sharp_text, render_text_webp
from _fantasy_yahoo import access_token, fmt_points, league_key, matchup_teams

WEEK_CHOICES = [{"value": "auto", "label": "Auto"}] + [
    {"value": str(week), "label": f"Week {week}"} for week in range(1, 19)
]

CARD_ID = "yahoo_fantasy_matchup"
CARD_NAME = "Yahoo Fantasy Matchup"
CARD_DETAIL = "Yahoo weekly matchup score"
CARD_OPTIONS = [
    {"key": "leagueKey", "label": "Yahoo League Key", "type": "text", "default": "", "maxlength": 40},
    {"key": "teamKey", "label": "Yahoo Team Key", "type": "text", "default": "", "maxlength": 48},
    {"key": "teamId", "label": "Team ID", "type": "number", "default": "", "min": 1, "max": 99},
    {"key": "teamName", "label": "Team Name Contains", "type": "text", "default": "", "maxlength": 40},
    {"key": "week", "label": "Week", "type": "select", "default": "auto", "choices": WEEK_CHOICES},
    {"key": "accessToken", "label": "Yahoo OAuth Access Token", "type": "password", "default": ""},
]


def _fit(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1]
    return text


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont
    opts = options or {}
    if not league_key(opts):
        return render_text_webp("SET LEAGUE", (100, 180, 255))
    if not access_token(opts):
        return render_text_webp("SET TOKEN", (255, 190, 80))
    try:
        mine, opp = matchup_teams(opts)
        if not mine:
            return render_text_webp("NO MATCH", (160, 170, 185))
    except Exception:
        return render_text_webp("YHOO ERR", (238, 80, 80))
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    image = Image.new("RGB", (width, 32), (8, 5, 2))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 14)
    except Exception:
        font = bold = big = ImageFont.load_default()
    draw.rectangle((0, 0, width - 1, 6), fill=(36, 14, 58))
    title = "YAHOO FANTASY"
    tw = draw.textbbox((0, 0), title, font=bold)[2]
    draw_sharp_text(image, ((width - tw) // 2, -3), title, (190, 130, 255), bold)
    my_name = str(mine.get("name") or "ME").upper()
    opp_name = str((opp or {}).get("name") or "OPP").upper()
    my_score = fmt_points(mine.get("points"))
    opp_score = fmt_points((opp or {}).get("points")) if opp else "--"
    if width == 128:
        draw_sharp_text(image, (2, 9), _fit(draw, my_name, font, 48), (245, 250, 255), font)
        draw_sharp_text(image, (78, 9), _fit(draw, opp_name, font, 48), (245, 250, 255), font)
        draw_sharp_text(image, (2, 20), my_score, (80, 235, 150), big)
        ow = draw.textbbox((0, 0), opp_score, font=big)[2]
        draw_sharp_text(image, (126 - ow, 20), opp_score, (255, 210, 80), big)
        draw_sharp_text(image, (59, 18), "VS", (150, 130, 170), font)
    else:
        draw_sharp_text(image, (1, 8), _fit(draw, my_name, font, 32), (245, 250, 255), font)
        opp_fit = _fit(draw, opp_name, font, 32)
        ow = draw.textbbox((0, 0), opp_fit, font=font)[2]
        draw_sharp_text(image, (63 - ow, 8), opp_fit, (245, 250, 255), font)
        draw_sharp_text(image, (1, 19), my_score, (80, 235, 150), bold)
        sw = draw.textbbox((0, 0), opp_score, font=bold)[2]
        draw_sharp_text(image, (63 - sw, 19), opp_score, (255, 210, 80), bold)
        draw_sharp_text(image, (28, 19), "VS", (150, 130, 170), font)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
