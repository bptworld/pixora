from io import BytesIO
import urllib.request
from datetime import datetime, timezone

from card_utils import (
    cached_priority_graphic,
    draw_sharp_text,
    fetch_sport_scoreboard,
    pick_sport_event,
    priority_graphic_key,
    render_sport_card,
    warm_priority_graphic,
)

from _sports_breaking import SCORE_ANIMATION_TEAMS_OPTION, animation_competitors, final_win_alert
from _sports_wall import render_wall_score_frames

CARD_ID = "nhl"
CARD_NAME = "NHL Scores"
CARD_DETAIL = "Live ESPN scoreboard"
CARD_OPTIONS = [
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "BOS",
        "choices": [
            {"value": "ANA", "label": "Anaheim Ducks"},
            {"value": "BOS", "label": "Boston Bruins"},
            {"value": "BUF", "label": "Buffalo Sabres"},
            {"value": "CGY", "label": "Calgary Flames"},
            {"value": "CAR", "label": "Carolina Hurricanes"},
            {"value": "CHI", "label": "Chicago Blackhawks"},
            {"value": "COL", "label": "Colorado Avalanche"},
            {"value": "CBJ", "label": "Columbus Blue Jackets"},
            {"value": "DAL", "label": "Dallas Stars"},
            {"value": "DET", "label": "Detroit Red Wings"},
            {"value": "EDM", "label": "Edmonton Oilers"},
            {"value": "FLA", "label": "Florida Panthers"},
            {"value": "LA", "label": "Los Angeles Kings"},
            {"value": "MIN", "label": "Minnesota Wild"},
            {"value": "MTL", "label": "Montreal Canadiens"},
            {"value": "NSH", "label": "Nashville Predators"},
            {"value": "NJ", "label": "New Jersey Devils"},
            {"value": "NYI", "label": "New York Islanders"},
            {"value": "NYR", "label": "New York Rangers"},
            {"value": "OTT", "label": "Ottawa Senators"},
            {"value": "PHI", "label": "Philadelphia Flyers"},
            {"value": "PIT", "label": "Pittsburgh Penguins"},
            {"value": "SJ", "label": "San Jose Sharks"},
            {"value": "SEA", "label": "Seattle Kraken"},
            {"value": "STL", "label": "St. Louis Blues"},
            {"value": "TB", "label": "Tampa Bay Lightning"},
            {"value": "TOR", "label": "Toronto Maple Leafs"},
            {"value": "UTAH", "label": "Utah Mammoth"},
            {"value": "VAN", "label": "Vancouver Canucks"},
            {"value": "VGK", "label": "Vegas Golden Knights"},
            {"value": "WSH", "label": "Washington Capitals"},
            {"value": "WPG", "label": "Winnipeg Jets"},
        ],
    }
]

CARD_OPTIONS.append({
    "key": "goalAnimationTarget",
    "label": "Goal Animation",
    "type": "select",
    "default": "device",
    "choices": [
        {"value": "device", "label": "Single Device"},
        {"value": "group_wall", "label": "Group Wall"},
    ],
})
CARD_OPTIONS.append(dict(SCORE_ANIMATION_TEAMS_OPTION))

_URL = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_COLOR = (100, 180, 255)
_GOAL_STATE = {}
_LOGO_CACHE = {}


def _hex_color(value, fallback=_COLOR):
    value = str(value or "").strip().lstrip("#")
    if len(value) == 6:
        try:
            return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            pass
    return fallback


def _fetch_big_logo(url):
    url = str(url or "").strip()
    if not url:
        return None
    if url in _LOGO_CACHE:
        return _LOGO_CACHE[url]
    try:
        from PIL import Image
        request = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1"})
        with urllib.request.urlopen(request, timeout=5) as response:
            data = response.read()
        logo = Image.open(BytesIO(data)).convert("RGBA")
        logo.thumbnail((22, 22), Image.LANCZOS)
        canvas = Image.new("RGBA", (22, 22), (0, 0, 0, 0))
        canvas.alpha_composite(logo, ((22 - logo.width) // 2, (22 - logo.height) // 2))
        _LOGO_CACHE[url] = canvas
        return canvas
    except Exception:
        return None


def _draw_logo_or_fallback(image, draw, team, color):
    logo = _fetch_big_logo(team.get("logo", ""))
    if logo:
        image.alpha_composite(logo, (1, 5))
        return
    draw.ellipse((1, 6, 22, 27), outline=color, width=2)
    abbr = (team.get("abbreviation") or team.get("shortDisplayName") or "NHL")[:3].upper()
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        from PIL import ImageFont
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), abbr, font=font)
    draw_sharp_text(image, (12 - (bbox[2] - bbox[0]) // 2, 11), abbr, color, font)


def _animation_width(options):
    options = options or {}
    try:
        explicit = int(options.get("_width") or 0)
        if explicit > 0:
            return max(64, min(512, explicit))
    except Exception:
        pass
    target = str(options.get("_target") or "").lower()
    return 128 if "128x32" in target else 64


def _draw_net(draw, width=64):
    offset = max(0, int(width or 64) - 64)
    red = (220, 42, 50)
    white = (210, 230, 245)
    draw.line((53 + offset, 15, 63 + offset, 15), fill=red)
    draw.line((53 + offset, 15, 53 + offset, 27), fill=red)
    draw.line((63 + offset, 15, 63 + offset, 27), fill=red)
    draw.line((53 + offset, 27, 63 + offset, 27), fill=red)
    for x in (56 + offset, 59 + offset):
        draw.line((x, 16, x, 26), fill=white)
    for y in (18, 21, 24):
        draw.line((54 + offset, y, 62 + offset, y), fill=white)


def _draw_puck(draw, x, y, bright=False):
    fill = (35, 38, 42) if not bright else (80, 88, 96)
    draw.ellipse((x - 3, y - 2, x + 3, y + 2), fill=fill, outline=(125, 135, 145))
    draw.line((x - 2, y - 2, x + 2, y - 2), fill=(185, 195, 205))


def _render_goal_animation_frames(team, kind="goal"):
    from PIL import Image, ImageDraw, ImageFont

    return render_wall_score_frames(team, kind, sport="hockey", default_label="NHL")

    color = _hex_color(team.get("color"), _COLOR)
    alt = _hex_color(team.get("alternateColor"), (255, 255, 255))
    text_color = alt if alt != (255, 255, 255) else color
    width = _animation_width(team)
    frames = []
    durations = []
    try:
        goal_font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 10)
    except Exception:
        goal_font = ImageFont.load_default()

    path = []
    for i, y in enumerate((22, 21, 20, 19, 18, 18, 20, 21)):
        t = i / 7
        path.append((24 + int((width - 30) * t), y))
    text_bbox = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), "GOAL", font=goal_font)
    text_x = 26 if width <= 64 else max(26, (width - (text_bbox[2] - text_bbox[0])) // 2)
    for i, (x, y) in enumerate(path):
        image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        _draw_logo_or_fallback(image, draw, team, color)
        _draw_net(draw, width)
        if i:
            px, py = path[max(0, i - 1)]
            draw.point((px - 2, py), fill=(110, 120, 130))
            draw.point((px - 5, py + 1), fill=(60, 66, 72))
        _draw_puck(draw, x, y)
        frames.append(image.convert("RGB"))
        durations.append(90)

    for shake in range(4):
        image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        _draw_logo_or_fallback(image, draw, team, color)
        _draw_net(draw, width)
        _draw_puck(draw, width - 5, 21, bright=shake % 2 == 0)
        if shake % 2 == 0:
            draw.line((width - 9, 16, width - 2, 26), fill=(245, 245, 245))
            draw.line((width - 2, 16, width - 9, 26), fill=(245, 245, 245))
        draw_sharp_text(image, (text_x, 2), "GOAL", text_color, goal_font)
        frames.append(image.convert("RGB"))
        durations.append(140)

    for show in (True, False, True, False, True, False, True, False, True):
        image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        _draw_logo_or_fallback(image, draw, team, color)
        _draw_net(draw, width)
        _draw_puck(draw, width - 5, 21, bright=True)
        if show:
            draw_sharp_text(image, (text_x, 2), "GOAL", text_color, goal_font)
        frames.append(image.convert("RGB"))
        durations.append(220 if show else 160)

    return frames, durations


def _render_goal_animation(team, kind="goal"):
    frames, durations = _render_goal_animation_frames(team, kind)
    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=1,
        lossless=True,
        quality=100,
    )
    return out.getvalue()


def _selected_competitor(event, favorite):
    favorite = (favorite or "").strip().upper()
    competition = event.get("competitions", [{}])[0]
    for competitor in competition.get("competitors", []):
        team = competitor.get("team", {})
        values = {
            str(team.get("abbreviation", "")).upper(),
            str(team.get("shortDisplayName", "")).upper(),
            str(team.get("displayName", "")).upper(),
            str(team.get("name", "")).upper(),
        }
        if favorite and favorite in values:
            return competitor
    return None


def _maybe_goal_animation(options):
    favorite = (options or {}).get("favoriteTeam", "")
    if not str(favorite or "").strip():
        return None
    data = fetch_sport_scoreboard(_URL, _CACHE, favorite, seconds=15)
    event = pick_sport_event(data.get("events", []), favorite)
    if not event:
        return None

    competition = event.get("competitions", [{}])[0]
    state = competition.get("status", {}).get("type", {}).get("state")
    competitors = animation_competitors(event, favorite, options)
    if not competitors:
        return None

    game_id = str(event.get("id") or competition.get("id") or datetime.now().strftime("%Y%m%d"))
    device_id = (options or {}).get("_device_id", "local")
    for competitor in competitors:
        team = competitor.get("team", {})
        team_key = (team.get("abbreviation") or team.get("shortDisplayName") or favorite or "NHL").upper()
        key = f"{device_id}:{game_id}:{team_key}"
        try:
            score = int(competitor.get("score", 0) or 0)
        except Exception:
            score = 0

        animation_team = {**team, "_width": _animation_width(options)}
        cache_key = priority_graphic_key(CARD_ID, animation_team, "goal", animation_team["_width"])

        previous = _GOAL_STATE.get(key)
        if state != "in":
            if str(state or "").lower() == "post":
                win = final_win_alert(
                    CARD_ID, _GOAL_STATE, key, competition, competitor, animation_team,
                    sport="hockey", render=_render_goal_animation,
                    target=(options or {}).get("goalAnimationTarget") or "device", dwell_secs=7,
                    renderer_name="_render_goal_animation_frames",
                )
                if win and previous is not None:
                    return win
            _GOAL_STATE[key] = {**(_GOAL_STATE.get(key) or {}), "score": score, "animated": score, "seen": datetime.now(timezone.utc)}
            continue
        if previous is None:
            _GOAL_STATE[key] = {"score": score, "animated": score, "seen": datetime.now(timezone.utc)}
            warm_priority_graphic(cache_key, lambda animation_team=animation_team: _render_goal_animation(animation_team))
            continue

        last_score = int(previous.get("score", score) or 0)
        animated = int(previous.get("animated", last_score) or 0)
        _GOAL_STATE[key] = {"score": score, "animated": animated, "seen": datetime.now(timezone.utc)}
        warm_priority_graphic(cache_key, lambda animation_team=animation_team: _render_goal_animation(animation_team))
        if score > last_score and score > animated:
            _GOAL_STATE[key]["animated"] = score
            target = str((options or {}).get("goalAnimationTarget") or "device").strip().lower()
            wall = target in ("group", "group_wall", "wall") or target.startswith("group:")
            return {
                "body": cached_priority_graphic(cache_key, lambda animation_team=animation_team: _render_goal_animation(animation_team)),
                "dwell_secs": 4,
                "_stay": True,
                "_no_replay": True,
                "_group_wall": {"type": "goal", "renderer": "_render_goal_animation_frames", "team": dict(animation_team), "dwell_secs": 6} if wall else None,
            }
    return None


def render(options=None):
    opts = options or {}
    animation = _maybe_goal_animation(opts)
    if animation:
        if animation.get("_group_wall"):
            normal_card = render_sport_card(opts, _URL, _CACHE, _COLOR, "NO NHL")
            if normal_card:
                animation["body"] = normal_card
                animation["dwell_secs"] = opts.get("_dwell", 10)
                animation["_no_replay"] = False
        return animation
    return render_sport_card(opts, _URL, _CACHE, _COLOR, "NO NHL")
