from io import BytesIO
import urllib.request
from datetime import datetime, timedelta, timezone

from card_utils import (
    cached_priority_graphic,
    draw_sharp_text,
    fetch_sport_scoreboard,
    pick_sport_event,
    priority_graphic_key,
    render_sport_card,
    warm_priority_graphic,
)

from _sports_breaking import SCORE_ANIMATION_TEAMS_OPTION, animation_competitors, final_win_alert, soccer_moment_alert, with_soccer_moment_options
from _sports_wall import render_wall_score_frames

CARD_ID = "soccer"
CARD_NAME = "Soccer Scores"
CARD_DETAIL = "Live ESPN soccer scoreboard"
CARD_OPTIONS = [
    {
        "key": "league",
        "label": "League",
        "type": "select",
        "default": "eng.1",
        "choices": [
            {"value": "eng.1", "label": "Premier League"},
            {"value": "usa.1", "label": "MLS"},
            {"value": "esp.1", "label": "La Liga"},
            {"value": "ita.1", "label": "Serie A"},
            {"value": "ger.1", "label": "Bundesliga"},
            {"value": "fra.1", "label": "Ligue 1"},
            {"value": "uefa.champions", "label": "Champions League"},
            {"value": "uefa.europa", "label": "Europa League"},
            {"value": "usa.nwsl", "label": "NWSL"},
        ],
    },
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "ARS",
        "choices": [
            {"value": "ARS", "label": "Arsenal"},
            {"value": "AVL", "label": "Aston Villa"},
            {"value": "CHE", "label": "Chelsea"},
            {"value": "LIV", "label": "Liverpool"},
            {"value": "MNC", "label": "Manchester City"},
            {"value": "MAN", "label": "Manchester United"},
            {"value": "NEW", "label": "Newcastle United"},
            {"value": "TOT", "label": "Tottenham Hotspur"},
        ],
    },
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
CARD_OPTIONS = with_soccer_moment_options(CARD_OPTIONS)
CARD_OPTIONS.append(dict(SCORE_ANIMATION_TEAMS_OPTION))

_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_COLOR = (70, 220, 125)
_GOAL_STATE = {}
_LOGO_CACHE = {}
_TEAMS_CACHE = {}


def _scoreboard_url(options):
    league = str((options or {}).get("league") or "eng.1").strip()
    if not league:
        league = "eng.1"
    return f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard"


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


def _team_logo_url(team):
    if team.get("logo"):
        return team.get("logo")
    logos = team.get("logos") or []
    if logos:
        return logos[0].get("href") or ""
    return ""


def _fetch_league_teams(league):
    league = str(league or "eng.1").strip() or "eng.1"
    now = datetime.now(timezone.utc)
    cached = _TEAMS_CACHE.get(league)
    if cached and cached["expires"] > now:
        return cached["teams"]
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/teams"
    request = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        import json
        data = json.loads(response.read().decode("utf-8"))
    teams = []
    for item in (((data.get("sports") or [{}])[0].get("leagues") or [{}])[0].get("teams") or []):
        team = item.get("team") or {}
        if team:
            teams.append(team)
    _TEAMS_CACHE[league] = {"teams": teams, "expires": now + timedelta(hours=12)}
    return teams


def _resolve_team_for_test(favorite, league="eng.1"):
    favorite = str(favorite or "").strip().upper()
    for team in _fetch_league_teams(league):
        values = {
            str(team.get("abbreviation", "")).upper(),
            str(team.get("shortDisplayName", "")).upper(),
            str(team.get("displayName", "")).upper(),
            str(team.get("name", "")).upper(),
        }
        if favorite and favorite in values:
            return {
                "abbreviation": team.get("abbreviation") or favorite,
                "color": team.get("color") or "46DC7D",
                "alternateColor": team.get("alternateColor") or "FFFFFF",
                "logo": _team_logo_url(team),
            }
    return {
        "abbreviation": favorite or "FC",
        "color": "46DC7D",
        "alternateColor": "FFFFFF",
        "logo": "",
    }


def _draw_logo_or_fallback(image, draw, team, color):
    logo = _fetch_big_logo(_team_logo_url(team))
    if logo:
        image.alpha_composite(logo, (1, 5))
        return
    draw.ellipse((1, 6, 22, 27), outline=color, width=2)
    abbr = (team.get("abbreviation") or team.get("shortDisplayName") or "FC")[:3].upper()
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
    white = (220, 235, 245)
    post = (245, 245, 245)
    draw.line((53 + offset, 13, 63 + offset, 13), fill=post)
    draw.line((53 + offset, 13, 53 + offset, 27), fill=post)
    draw.line((63 + offset, 13, 63 + offset, 27), fill=post)
    draw.line((53 + offset, 27, 63 + offset, 27), fill=post)
    for x in (56 + offset, 59 + offset):
        draw.line((x, 14, x, 26), fill=white)
    for y in (16, 19, 22, 25):
        draw.line((54 + offset, y, 62 + offset, y), fill=white)


def _draw_soccer_ball(draw, x, y):
    draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(245, 245, 238), outline=(180, 185, 185))
    dark = (18, 22, 26)
    draw.polygon([(x, y - 2), (x + 2, y), (x + 1, y + 3), (x - 1, y + 3), (x - 2, y)], fill=dark)
    for px, py in [(x - 3, y - 3), (x + 3, y - 3), (x - 4, y + 2), (x + 4, y + 2)]:
        draw.rectangle((px, py, px + 1, py + 1), fill=dark)


def _render_goal_animation_frames(team, kind="goal"):
    from PIL import Image, ImageDraw, ImageFont

    return render_wall_score_frames(team, kind, sport="soccer", default_label="FC")

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
    for i, y in enumerate((23, 22, 21, 20, 19, 20, 21)):
        t = i / 6
        path.append((24 + int((width - 29) * t), y))
    text_bbox = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), "GOAL", font=goal_font)
    text_x = 26 if width <= 64 else max(26, (width - (text_bbox[2] - text_bbox[0])) // 2)
    for i, (x, y) in enumerate(path):
        image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        _draw_logo_or_fallback(image, draw, team, color)
        _draw_net(draw, width)
        if i:
            px, py = path[max(0, i - 1)]
            draw.point((px - 4, py + 1), fill=(80, 90, 85))
            draw.point((px - 8, py + 2), fill=(45, 52, 48))
        _draw_soccer_ball(draw, x, y)
        frames.append(image.convert("RGB"))
        durations.append(90)

    for burst in range(4):
        image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        _draw_logo_or_fallback(image, draw, team, color)
        _draw_net(draw, width)
        _draw_soccer_ball(draw, width - 5, 21)
        if burst % 2 == 0:
            draw.line((width - 9, 15, width - 2, 26), fill=(245, 245, 245))
            draw.line((width - 2, 15, width - 9, 26), fill=(245, 245, 245))
        draw_sharp_text(image, (text_x, 0), "GOAL", text_color, goal_font)
        frames.append(image.convert("RGB"))
        durations.append(140)

    for show in (True, False, True, False, True, False, True, False, True):
        image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        _draw_logo_or_fallback(image, draw, team, color)
        _draw_net(draw, width)
        _draw_soccer_ball(draw, width - 5, 21)
        if show:
            draw_sharp_text(image, (text_x, 0), "GOAL", text_color, goal_font)
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
    url = _scoreboard_url(options)
    data = fetch_sport_scoreboard(url, _CACHE, favorite, seconds=15)
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
    league = str((options or {}).get("league") or "eng.1")
    moment_team = None
    favorite_competitor = _selected_competitor(event, favorite)
    if favorite_competitor:
        moment_team = {**(favorite_competitor.get("team") or {})}
    elif competitors:
        moment_team = {**(competitors[0].get("team") or {})}
    if moment_team:
        moment = soccer_moment_alert(
            options,
            CARD_ID,
            _GOAL_STATE,
            event,
            competition,
            moment_team,
            render=_render_goal_animation,
            renderer_name="_render_goal_animation_frames",
        )
        if moment:
            return moment
    for competitor in competitors:
        team = competitor.get("team", {})
        team_key = (team.get("abbreviation") or team.get("shortDisplayName") or favorite or "FC").upper()
        key = f"{device_id}:{league}:{game_id}:{team_key}"
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
                    sport="soccer", render=_render_goal_animation,
                    target=(options or {}).get("winAnimationTarget") or (options or {}).get("goalAnimationTarget") or "device", dwell_secs=7,
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
            normal_card = render_sport_card(opts, _scoreboard_url(opts), _CACHE, _COLOR, "NO SOCCER")
            if normal_card:
                animation["body"] = normal_card
                animation["dwell_secs"] = opts.get("_dwell", 10)
                animation["_no_replay"] = False
        return animation
    url = _scoreboard_url(opts)
    return render_sport_card(opts, url, _CACHE, _COLOR, "NO SOCCER")
