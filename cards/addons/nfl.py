from io import BytesIO
import urllib.request
from datetime import datetime, timezone

from card_utils import (
    cached_priority_graphic,
    draw_sharp_text,
    fetch_json_url,
    fetch_sport_scoreboard,
    pick_sport_event,
    priority_graphic_key,
    render_sport_card,
    warm_priority_graphic,
)

from _sports_breaking import SCORE_ANIMATION_TEAMS_OPTION, animation_competitors, final_win_alert, game_moment_alert, graphic_target_option, render_score_alert_frames
from _sports_wall import render_wall_score_frames

CARD_ID = "nfl"
CARD_NAME = "NFL Scores"
CARD_DETAIL = "Live ESPN scoreboard"
CARD_OPTIONS = [
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "NE",
        "choices": [
            {"value": "ARI", "label": "Arizona Cardinals"},
            {"value": "ATL", "label": "Atlanta Falcons"},
            {"value": "BAL", "label": "Baltimore Ravens"},
            {"value": "BUF", "label": "Buffalo Bills"},
            {"value": "CAR", "label": "Carolina Panthers"},
            {"value": "CHI", "label": "Chicago Bears"},
            {"value": "CIN", "label": "Cincinnati Bengals"},
            {"value": "CLE", "label": "Cleveland Browns"},
            {"value": "DAL", "label": "Dallas Cowboys"},
            {"value": "DEN", "label": "Denver Broncos"},
            {"value": "DET", "label": "Detroit Lions"},
            {"value": "GB", "label": "Green Bay Packers"},
            {"value": "HOU", "label": "Houston Texans"},
            {"value": "IND", "label": "Indianapolis Colts"},
            {"value": "JAX", "label": "Jacksonville Jaguars"},
            {"value": "KC", "label": "Kansas City Chiefs"},
            {"value": "LV", "label": "Las Vegas Raiders"},
            {"value": "LAC", "label": "Los Angeles Chargers"},
            {"value": "LAR", "label": "Los Angeles Rams"},
            {"value": "MIA", "label": "Miami Dolphins"},
            {"value": "MIN", "label": "Minnesota Vikings"},
            {"value": "NE", "label": "New England Patriots"},
            {"value": "NO", "label": "New Orleans Saints"},
            {"value": "NYG", "label": "New York Giants"},
            {"value": "NYJ", "label": "New York Jets"},
            {"value": "PHI", "label": "Philadelphia Eagles"},
            {"value": "PIT", "label": "Pittsburgh Steelers"},
            {"value": "SF", "label": "San Francisco 49ers"},
            {"value": "SEA", "label": "Seattle Seahawks"},
            {"value": "TB", "label": "Tampa Bay Buccaneers"},
            {"value": "TEN", "label": "Tennessee Titans"},
            {"value": "WSH", "label": "Washington Commanders"},
        ],
    }
]

CARD_OPTIONS.append({
    "key": "scoreAnimationTarget",
    "label": "Score Animation",
    "type": "select",
    "default": "device",
    "choices": [
        {"value": "device", "label": "Single Device"},
        {"value": "group_wall", "label": "Group Wall"},
    ],
})
CARD_OPTIONS.append(graphic_target_option("startPeriodAnimationTarget", "Start of Quarter Graphic"))
CARD_OPTIONS.append(graphic_target_option("endPeriodAnimationTarget", "End of Quarter Graphic"))
CARD_OPTIONS.append(graphic_target_option("winAnimationTarget", "End of Game Winner Graphic"))
CARD_OPTIONS.append(dict(SCORE_ANIMATION_TEAMS_OPTION))

_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_SUMMARY_CACHE = {}
_COLOR = (100, 220, 80)
_SCORE_STATE = {}
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


def _team_logo_url(team):
    if team.get("logo"):
        return team.get("logo")
    logos = team.get("logos") or []
    if logos:
        return logos[0].get("href") or ""
    abbr = (team.get("abbreviation") or "").lower()
    return f"https://a.espncdn.com/i/teamlogos/nfl/500/{abbr}.png" if abbr else ""


def _draw_logo_or_fallback(image, draw, team, color):
    logo = _fetch_big_logo(_team_logo_url(team))
    if logo:
        image.alpha_composite(logo, (1, 5))
        return
    draw.ellipse((1, 6, 22, 27), outline=color, width=2)
    abbr = (team.get("abbreviation") or team.get("shortDisplayName") or "NFL")[:3].upper()
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        from PIL import ImageFont
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), abbr, font=font)
    draw_sharp_text(image, (12 - (bbox[2] - bbox[0]) // 2, 11), abbr, color, font)


def _draw_football(draw, x, y, angle=0, bright=False):
    brown = (156, 86, 42) if bright else (126, 66, 34)
    edge = (210, 145, 90)
    white = (245, 245, 235)
    draw.ellipse((x - 4, y - 2, x + 4, y + 2), fill=brown, outline=edge)
    draw.line((x - 2, y, x + 2, y), fill=white)
    for dx in (-1, 1):
        draw.point((x + dx, y - 1), fill=white)
        draw.point((x + dx, y + 1), fill=white)


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


def _draw_uprights(draw, width=64):
    offset = max(0, int(width or 64) - 64)
    yellow = (255, 215, 60)
    draw.line((54 + offset, 7, 54 + offset, 27), fill=yellow)
    draw.line((62 + offset, 7, 62 + offset, 27), fill=yellow)
    draw.line((54 + offset, 27, 62 + offset, 27), fill=yellow)
    draw.line((58 + offset, 27, 58 + offset, 31), fill=yellow)


def _draw_goal_post(draw, color=None, width=64):
    offset = max(0, int(width or 64) - 64)
    yellow = (255, 215, 60)
    shadow = (126, 94, 30)
    draw.line((51 + offset, 7, 51 + offset, 27), fill=shadow)
    draw.line((61 + offset, 7, 61 + offset, 27), fill=shadow)
    draw.line((51 + offset, 27, 61 + offset, 27), fill=shadow)
    draw.line((56 + offset, 27, 56 + offset, 31), fill=shadow)
    draw.line((52 + offset, 6, 52 + offset, 26), fill=yellow)
    draw.line((62 + offset, 6, 62 + offset, 26), fill=yellow)
    draw.line((52 + offset, 26, 62 + offset, 26), fill=yellow)
    draw.line((57 + offset, 26, 57 + offset, 31), fill=yellow)


def _draw_endzone(draw, color):
    shade = tuple(max(0, c // 3) for c in color)
    draw.rectangle((49, 14, 63, 31), fill=shade)
    draw.line((49, 14, 49, 31), fill=color)
    draw.line((0, 31, 63, 31), fill=color)


def _render_score_animation_frames(team, kind="touchdown"):
    from PIL import Image, ImageDraw, ImageFont

    kind = str(kind or "score").lower()
    if (team or {}).get("_wall"):
        return render_wall_score_frames(team, kind, sport="football", default_label="NFL")
    if kind in (
        "win", "wins", "winner", "final_win",
        "game_start", "game_end",
        "quarter_start", "quarter_end",
        "period_start", "period_end",
    ):
        return render_score_alert_frames({**(team or {}), "_sport": "football"}, kind)

    color = _hex_color(team.get("color"), _COLOR)
    alt = _hex_color(team.get("alternateColor"), (255, 255, 255))
    text_color = alt if alt != (255, 255, 255) else color
    width = _animation_width(team)
    frames = []
    durations = []
    try:
        big = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 9)
        small = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        big = small = ImageFont.load_default()

    if kind == "field_goal":
        path = []
        for i, y in enumerate((24, 20, 15, 10, 8, 11)):
            t = i / 5
            path.append((24 + int((width - 30) * t), y))
        for i, (x, y) in enumerate(path):
            image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
            draw = ImageDraw.Draw(image)
            _draw_logo_or_fallback(image, draw, team, color)
            _draw_uprights(draw, width)
            if i:
                px, py = path[max(0, i - 1)]
                draw.point((px - 3, py + 2), fill=(90, 100, 90))
            _draw_football(draw, x, y)
            frames.append(image.convert("RGB"))
            durations.append(95)
        line1, line2 = "FIELD", "GOAL"
        line1_x, line2_x = (25, 28) if width <= 64 else (max(25, width // 2 - 15), max(28, width // 2 - 10))
    elif kind == "safety":
        path = []
        for i, y in enumerate((21, 20, 20, 21, 22, 23)):
            t = i / 5
            path.append((24 + int((width - 29) * t), y))
        for i, (x, y) in enumerate(path):
            image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
            draw = ImageDraw.Draw(image)
            _draw_logo_or_fallback(image, draw, team, color)
            draw.rectangle((width - 13, 12, width - 1, 31), outline=(255, 70, 80))
            _draw_football(draw, x, y)
            frames.append(image.convert("RGB"))
            durations.append(95)
        line1, line2 = "SAFETY", ""
        line1_x, line2_x = (23, 0) if width <= 64 else (max(23, width // 2 - 18), 0)
    else:
        path = []
        for i, y in enumerate((24, 22, 20, 18, 17, 18)):
            t = i / 5
            path.append((24 + int((width - 31) * t), y))
        for i, (x, y) in enumerate(path):
            image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
            draw = ImageDraw.Draw(image)
            _draw_logo_or_fallback(image, draw, team, color)
            _draw_goal_post(draw, color, width)
            if i:
                px, py = path[max(0, i - 1)]
                draw.point((px - 4, py + 1), fill=(85, 95, 80))
            _draw_football(draw, x, y)
            frames.append(image.convert("RGB"))
            durations.append(90)
        line1 = "TOUCH" if kind == "touchdown" else "SCORE"
        line2 = "DOWN" if kind == "touchdown" else ""
        line1_x, line2_x = ((25, 29) if width <= 64 else (max(25, width // 2 - 15), max(29, width // 2 - 11)))

    for show in (True, False, True, False, True, False, True, False, True):
        image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        _draw_logo_or_fallback(image, draw, team, color)
        if kind == "field_goal":
            _draw_uprights(draw, width)
            _draw_football(draw, width - 6, 11, bright=True)
        else:
            _draw_goal_post(draw, color, width)
            _draw_football(draw, width - 7, 18)
        if show:
            draw_sharp_text(image, (line1_x, 2), line1, text_color, big)
            if line2:
                draw_sharp_text(image, (line2_x, 13), line2, color, small)
        frames.append(image.convert("RGB"))
        durations.append(220 if show else 160)

    return frames, durations


def _render_score_animation(team, kind="touchdown"):
    frames, durations = _render_score_animation_frames(team, kind)
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


def _fetch_summary(event_id):
    if not event_id:
        return {}
    url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={event_id}"
    return fetch_json_url(url, _SUMMARY_CACHE, seconds=15)


def _play_score_for_competitor(play, competitor):
    side = competitor.get("homeAway")
    key = "homeScore" if side == "home" else "awayScore"
    try:
        return int(play.get(key, 0) or 0)
    except Exception:
        return 0


def _latest_score_play(event, competitor, previous_score, current_score):
    try:
        summary = _fetch_summary(event.get("id"))
    except Exception:
        return None
    team = competitor.get("team", {})
    favorite = (team.get("abbreviation") or "").upper()
    candidates = []
    for play in summary.get("scoringPlays") or []:
        play_team = (play.get("team") or {})
        values = {
            str(play_team.get("abbreviation", "")).upper(),
            str(play_team.get("shortDisplayName", "")).upper(),
            str(play_team.get("displayName", "")).upper(),
        }
        if favorite and favorite not in values:
            continue
        play_score = _play_score_for_competitor(play, competitor)
        if previous_score < play_score <= current_score:
            candidates.append(play)
    return candidates[-1] if candidates else None


def _classify_score_play(play):
    if not play:
        return "score"
    play_type = play.get("type") or {}
    text = " ".join([
        str(play_type.get("text", "")),
        str(play_type.get("abbreviation", "")),
        str(play.get("text", "")),
    ]).lower()
    if "field goal" in text or " fg" in f" {text}":
        return "field_goal"
    if "touchdown" in text or " td" in f" {text}":
        return "touchdown"
    if "safety" in text:
        return "safety"
    return "score"


def _play_athlete(play):
    preferred = ("scorer", "rusher", "receiver", "passer", "kicker", "returner")
    participants = (play or {}).get("participants") or []
    for wanted in preferred:
        for participant in participants:
            if str(participant.get("type") or "").lower() != wanted:
                continue
            athlete = participant.get("athlete") or participant
            if isinstance(athlete, dict) and athlete.get("id"):
                return athlete
    for key in ("athlete", "scorer"):
        athlete = (play or {}).get(key) or {}
        if isinstance(athlete, dict) and athlete.get("id"):
            return athlete
    return {}


def _scorer_for_play(play, team):
    athlete = _play_athlete(play)
    athlete_id = str(athlete.get("id") or "").strip()
    headshot = athlete.get("headshot") or {}
    if isinstance(headshot, dict):
        headshot = headshot.get("href")
    if not headshot and athlete_id:
        headshot = f"https://a.espncdn.com/i/headshots/nfl/players/full/{athlete_id}.png"
    name = athlete.get("shortName") or athlete.get("displayName") or athlete.get("fullName") or ""
    return {
        "playerName": name,
        "playerHeadshot": str(headshot or "").strip(),
        "playerLogo": _team_logo_url(team or {}),
    } if headshot else {}


def _maybe_score_animation(options):
    if (options or {}).get("_is_prefetch"):
        return None
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
    moment_team = None
    favorite_competitor = _selected_competitor(event, favorite)
    if favorite_competitor:
        moment_team = {**(favorite_competitor.get("team") or {})}
    elif competitors:
        moment_team = {**(competitors[0].get("team") or {})}
    if moment_team:
        moment = game_moment_alert(options, CARD_ID, _SCORE_STATE, event, competition, moment_team, sport="football", unit="quarter", default_label="NFL")
        if moment:
            return moment
    for competitor in competitors:
        team = competitor.get("team", {})
        team_key = (team.get("abbreviation") or team.get("shortDisplayName") or favorite or "NFL").upper()
        key = f"{device_id}:{game_id}:{team_key}"
        try:
            score = int(competitor.get("score", 0) or 0)
        except Exception:
            score = 0

        animation_team = {**team, "_width": _animation_width(options)}
        warm_key = priority_graphic_key(CARD_ID, animation_team, "score", animation_team["_width"])

        previous = _SCORE_STATE.get(key)
        if state != "in":
            if str(state or "").lower() == "post":
                win = final_win_alert(
                    CARD_ID, _SCORE_STATE, key, competition, competitor, animation_team,
                    sport="football", render=_render_score_animation,
                    target=(options or {}).get("winAnimationTarget") or (options or {}).get("scoreAnimationTarget") or "device", dwell_secs=7,
                    renderer_name="_render_score_animation_frames",
                )
                if win and previous is not None:
                    return win
            _SCORE_STATE[key] = {**(_SCORE_STATE.get(key) or {}), "score": score, "animated": score, "seen": datetime.now(timezone.utc)}
            continue
        if previous is None:
            _SCORE_STATE[key] = {"score": score, "animated": score, "seen": datetime.now(timezone.utc)}
            warm_priority_graphic(warm_key, lambda animation_team=animation_team: _render_score_animation(animation_team, "score"))
            continue

        last_score = int(previous.get("score", score) or 0)
        animated = int(previous.get("animated", last_score) or 0)
        _SCORE_STATE[key] = {"score": score, "animated": animated, "seen": datetime.now(timezone.utc)}
        warm_priority_graphic(warm_key, lambda animation_team=animation_team: _render_score_animation(animation_team, "score"))
        if score > last_score and score > animated:
            _SCORE_STATE[key]["animated"] = score
            play = _latest_score_play(event, competitor, last_score, score)
            kind = _classify_score_play(play)
            animation_team = {**animation_team, **_scorer_for_play(play, team)}
            target = str((options or {}).get("scoreAnimationTarget") or "device").strip().lower()
            wall = target in ("group", "group_wall", "wall") or target.startswith("group:")
            cache_key = priority_graphic_key(CARD_ID, animation_team, kind, animation_team["_width"])
            return {
                "body": cached_priority_graphic(cache_key, lambda animation_team=animation_team, kind=kind: _render_score_animation(animation_team, kind)),
                "dwell_secs": 6,
                "_stay": True,
                "_no_replay": True,
                "_priority": True,
                "_group_wall": {"type": "score", "renderer": "_render_score_animation_frames", "team": dict(animation_team), "kind": kind, "dwell_secs": 6} if wall else None,
            }
    return None


def render(options=None):
    opts = options or {}
    animation = _maybe_score_animation(opts)
    if animation:
        return animation
    return render_sport_card(opts, _URL, _CACHE, _COLOR, "NO NFL")
