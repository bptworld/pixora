from io import BytesIO
import math
import urllib.request
from datetime import datetime, timedelta, timezone

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

from _sports_breaking import SCORE_ANIMATION_TEAMS_OPTION, animation_competitors, final_win_alert
from _sports_wall import render_wall_score_frames

CARD_ID = "mlb"
CARD_NAME = "MLB Scores"
CARD_DETAIL = "Live ESPN scoreboard"
CARD_OPTIONS = [
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "BOS",
        "choices": [
            {"value": "ARI", "label": "Arizona Diamondbacks"},
            {"value": "ATH", "label": "Athletics"},
            {"value": "ATL", "label": "Atlanta Braves"},
            {"value": "BAL", "label": "Baltimore Orioles"},
            {"value": "BOS", "label": "Boston Red Sox"},
            {"value": "CHC", "label": "Chicago Cubs"},
            {"value": "CHW", "label": "Chicago White Sox"},
            {"value": "CIN", "label": "Cincinnati Reds"},
            {"value": "CLE", "label": "Cleveland Guardians"},
            {"value": "COL", "label": "Colorado Rockies"},
            {"value": "DET", "label": "Detroit Tigers"},
            {"value": "HOU", "label": "Houston Astros"},
            {"value": "KC", "label": "Kansas City Royals"},
            {"value": "LAA", "label": "Los Angeles Angels"},
            {"value": "LAD", "label": "Los Angeles Dodgers"},
            {"value": "MIA", "label": "Miami Marlins"},
            {"value": "MIL", "label": "Milwaukee Brewers"},
            {"value": "MIN", "label": "Minnesota Twins"},
            {"value": "NYM", "label": "New York Mets"},
            {"value": "NYY", "label": "New York Yankees"},
            {"value": "PHI", "label": "Philadelphia Phillies"},
            {"value": "PIT", "label": "Pittsburgh Pirates"},
            {"value": "SD", "label": "San Diego Padres"},
            {"value": "SF", "label": "San Francisco Giants"},
            {"value": "SEA", "label": "Seattle Mariners"},
            {"value": "STL", "label": "St. Louis Cardinals"},
            {"value": "TB", "label": "Tampa Bay Rays"},
            {"value": "TEX", "label": "Texas Rangers"},
            {"value": "TOR", "label": "Toronto Blue Jays"},
            {"value": "WSH", "label": "Washington Nationals"},
        ],
    },
    {
        "key": "runAnimationTarget",
        "label": "Run Scored Animation",
        "type": "select",
        "default": "device",
        "choices": [
            {"value": "device", "label": "Single Device"},
            {"value": "group_wall", "label": "Group Wall"},
        ],
    }
]
CARD_OPTIONS.append(dict(SCORE_ANIMATION_TEAMS_OPTION))

_URL = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_SUMMARY_CACHE = {}
_COLOR = (117, 231, 214)
_RUN_STATE = {}
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


def _draw_baseball(draw, cx, cy, size):
    r = max(1, size // 2)
    if size <= 2:
        draw.point((int(cx), int(cy)), fill=(245, 248, 238))
        return
    box = (int(cx - r), int(cy - r), int(cx + r), int(cy + r))
    draw.ellipse(box, fill=(246, 246, 232), outline=(210, 210, 200))
    red = (210, 42, 48)
    if size >= 7:
        draw.arc((cx - r + 1, cy - r, cx + 1, cy + r), 285, 75, fill=red)
        draw.arc((cx - 1, cy - r, cx + r - 1, cy + r), 105, 255, fill=red)
        for dx, dy in [(-2, -2), (-3, 1), (2, -2), (3, 1)]:
            draw.point((int(cx + dx), int(cy + dy)), fill=red)


_BIG_RUN = {
    "R": ["1110", "1001", "1001", "1110", "1010", "1001", "1001"],
    "U": ["1001", "1001", "1001", "1001", "1001", "1001", "1111"],
    "N": ["1001", "1101", "1101", "1011", "1011", "1001", "1001"],
}


def _draw_big_run(draw, x, y, color):
    scale = 1
    gap = 1
    cursor = x
    for letter in "RUN":
        pattern = _BIG_RUN[letter]
        for row, bits in enumerate(pattern):
            for col, bit in enumerate(bits):
                if bit == "1":
                    px = cursor + col
                    py = y + row
                    draw.point((px, py), fill=color)
                    draw.point((px + 1, py), fill=color)
        cursor += len(pattern[0]) * scale + gap


def _draw_logo_or_fallback(image, draw, team, color):
    logo = _fetch_big_logo(team.get("logo", ""))
    if logo:
        image.alpha_composite(logo, (1, 5))
        return
    draw.ellipse((1, 6, 22, 27), outline=color, width=2)
    abbr = (team.get("abbreviation") or team.get("shortDisplayName") or "MLB")[:3].upper()
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        from PIL import ImageFont
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), abbr, font=font)
    draw_sharp_text(image, (12 - (bbox[2] - bbox[0]) // 2, 11), abbr, color, font)


def _run_animation_text(kind):
    kind = str(kind or "run").lower()
    if kind in ("grand_slam", "grand slam", "slam"):
        return "GRAND", "SLAM"
    if kind in ("home_run", "homerun", "homer", "hr"):
        return "HOME", "RUN"
    return "RUN", "SCORED"


def _render_run_animation_frames(team, kind="run"):
    from PIL import Image, ImageDraw, ImageFont

    return render_wall_score_frames(team, kind, sport="baseball", default_label="MLB")

    color = _hex_color(team.get("color"), _COLOR)
    alt = _hex_color(team.get("alternateColor"), (255, 255, 255))
    try:
        width = int(team.get("_width") or 64)
    except Exception:
        width = 64
    width = max(64, min(512, width))
    frames = []
    durations = []
    try:
        font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        run_font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 9)
    except Exception:
        font = run_font = ImageFont.load_default()

    for i in range(20):
        t = i / 19
        image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        _draw_logo_or_fallback(image, draw, team, color)
        draw.line((0, 31, width - 1, 31), fill=tuple(max(0, c // 3) for c in color) + (255,))

        travel = max(56, width - 8)
        x = 3 + (travel * t)
        y = 29 - (25 * math.sin(t * math.pi / 2))
        size = max(1, int(1 + 9 * t))
        for trail in range(1, 4):
            tt = max(0, t - trail * 0.055)
            tx = 3 + (travel * tt)
            ty = 29 - (25 * math.sin(tt * math.pi / 2))
            fade = 90 - trail * 18
            draw.point((int(tx), int(ty)), fill=(255, 255, 255, fade))
        _draw_baseball(draw, x, y, size)
        frames.append(image.convert("RGB"))
        durations.append(45)

    ball_x, ball_y, ball_size = width - 5, 4, 10
    line1, line2 = _run_animation_text(kind)
    line1_bbox = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), line1, font=run_font)
    line1_x = 29 if width <= 64 and line1 == "RUN" else max(24, (width - (line1_bbox[2] - line1_bbox[0])) // 2)
    for step in range(3):
        image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        _draw_logo_or_fallback(image, draw, team, color)
        _draw_baseball(draw, ball_x, ball_y, ball_size)
        draw_sharp_text(image, (line1_x, 4), line1, color, run_font)
        frames.append(image.convert("RGB"))
        durations.append(170)

    scored_color = alt if alt != (255, 255, 255) else color
    line2_bbox = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), line2, font=font)
    line2_x = 21 if width <= 64 and line2 == "SCORED" else max(24, (width - (line2_bbox[2] - line2_bbox[0])) // 2)
    for show in (True, False, True, False, True, False, True, False, True):
        image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        _draw_logo_or_fallback(image, draw, team, color)
        _draw_baseball(draw, ball_x, ball_y, ball_size)
        draw_sharp_text(image, (line1_x, 4), line1, color, run_font)
        if show:
            draw_sharp_text(image, (line2_x, 16), line2, scored_color, font)
        frames.append(image.convert("RGB"))
        durations.append(220 if show else 160)

    return frames, durations


def _render_run_animation(team, kind="run"):
    frames, durations = _render_run_animation_frames(team, kind)
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


def _run_animation_width(options):
    options = options or {}
    try:
        explicit = int(options.get("_width") or 0)
        if explicit > 0:
            return max(64, min(512, explicit))
    except Exception:
        pass
    target = str(options.get("_target") or "").lower()
    if "128x32" in target:
        return 128
    return 64


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
    event_id = str(event_id or "").strip()
    if not event_id:
        return {}
    now = datetime.now(timezone.utc)
    cached = _SUMMARY_CACHE.get(event_id)
    if cached and cached.get("expires", now) > now:
        return cached.get("body") or {}
    url = f"https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/summary?event={event_id}"
    data = fetch_json_url(url, {}, seconds=0)
    _SUMMARY_CACHE[event_id] = {"expires": now + timedelta(seconds=15), "body": data}
    return data


def _play_score_for_competitor(play, competitor):
    side = str(competitor.get("homeAway") or "").lower()
    key = "homeScore" if side == "home" else "awayScore"
    try:
        return int(play.get(key, 0) or 0)
    except Exception:
        return 0


def _play_team_matches(play, competitor):
    play_team = play.get("team") or {}
    team = competitor.get("team") or {}
    play_values = {
        str(play_team.get("id", "")),
        str(play_team.get("abbreviation", "")).upper(),
        str(play_team.get("shortDisplayName", "")).upper(),
        str(play_team.get("displayName", "")).upper(),
        str(play_team.get("name", "")).upper(),
    }
    team_values = {
        str(team.get("id", "")),
        str(team.get("abbreviation", "")).upper(),
        str(team.get("shortDisplayName", "")).upper(),
        str(team.get("displayName", "")).upper(),
        str(team.get("name", "")).upper(),
    }
    play_values = {value for value in play_values if value}
    team_values = {value for value in team_values if value}
    return bool(play_values & team_values)


def _classify_latest_run(event, competitor, previous_score, current_score):
    try:
        summary = _fetch_summary(event.get("id"))
    except Exception:
        return "run"
    plays = list(summary.get("scoringPlays") or [])
    if not plays:
        plays = [play for play in summary.get("plays") or [] if play.get("scoringPlay")]
    candidates = []
    for play in plays:
        if not _play_team_matches(play, competitor):
            continue
        play_score = _play_score_for_competitor(play, competitor)
        if previous_score < play_score <= current_score:
            candidates.append(play)
    play = candidates[-1] if candidates else None
    if not play:
        return "run"
    delta = max(0, int(current_score or 0) - int(previous_score or 0))
    play_type = play.get("type") or {}
    text = " ".join([
        str(play_type.get("text", "")),
        str(play_type.get("abbreviation", "")),
        str(play.get("text", "")),
    ]).lower()
    if "grand slam" in text:
        return "grand_slam"
    if "homered" in text or "home run" in text or " homer" in f" {text}":
        return "grand_slam" if delta >= 4 else "home_run"
    return "run"


def _maybe_run_animation(options):
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
        team_key = (team.get("abbreviation") or team.get("shortDisplayName") or favorite or "MLB").upper()
        key = f"{device_id}:{game_id}:{team_key}"
        try:
            score = int(competitor.get("score", 0) or 0)
        except Exception:
            score = 0

        animation_team = dict(team)
        animation_team["_width"] = _run_animation_width(options)
        cache_key = priority_graphic_key(CARD_ID, animation_team, "run", animation_team["_width"])

        previous = _RUN_STATE.get(key)
        if state != "in":
            if str(state or "").lower() == "post":
                win = final_win_alert(
                    CARD_ID, _RUN_STATE, key, competition, competitor, animation_team,
                    sport="baseball", render=_render_run_animation,
                    target=(options or {}).get("runAnimationTarget") or "device", dwell_secs=7,
                    renderer_name="_render_run_animation_frames",
                )
                if win and previous is not None:
                    return win
            _RUN_STATE[key] = {**(_RUN_STATE.get(key) or {}), "score": score, "animated": score, "seen": datetime.now(timezone.utc)}
            continue
        if previous is None:
            _RUN_STATE[key] = {"score": score, "animated": score, "seen": datetime.now(timezone.utc)}
            warm_priority_graphic(cache_key, lambda animation_team=animation_team: _render_run_animation(animation_team))
            continue

        last_score = int(previous.get("score", score) or 0)
        animated = int(previous.get("animated", last_score) or 0)
        _RUN_STATE[key] = {"score": score, "animated": animated, "seen": datetime.now(timezone.utc)}
        warm_priority_graphic(cache_key, lambda animation_team=animation_team: _render_run_animation(animation_team))
        if score > last_score and score > animated:
            _RUN_STATE[key]["animated"] = score
            kind = _classify_latest_run(event, competitor, last_score, score)
            target = str((options or {}).get("runAnimationTarget") or "device").strip().lower()
            wall = target in ("group", "group_wall", "wall")
            cache_key = priority_graphic_key(CARD_ID, animation_team, kind, animation_team["_width"])
            return {
                "body": cached_priority_graphic(cache_key, lambda animation_team=animation_team, kind=kind: _render_run_animation(animation_team, kind)),
                "dwell_secs": 5 if kind in ("home_run", "grand_slam") else 4,
                "_stay": False,
                "_no_replay": True,
                "_group_wall": {
                    "type": kind,
                    "renderer": "_render_run_animation_frames",
                    "team": animation_team,
                    "kind": kind,
                    "dwell_secs": 7 if kind == "grand_slam" else 6,
                } if wall else None,
            }
    return None


def render(options=None):
    animation = _maybe_run_animation(options or {})
    if animation:
        normal_card = render_sport_card(options, _URL, _CACHE, _COLOR, "NO MLB")
        if animation.get("_group_wall"):
            if normal_card:
                animation["body"] = normal_card
                animation["dwell_secs"] = (options or {}).get("_dwell", 10)
                animation["_no_replay"] = False
            return animation
        if normal_card:
            animation["_replay_body"] = normal_card
        return animation
    return render_sport_card(options, _URL, _CACHE, _COLOR, "NO MLB")
