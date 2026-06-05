from io import BytesIO
from datetime import datetime, timezone

from card_utils import (
    cached_priority_graphic,
    draw_sharp_text,
    fetch_sport_scoreboard,
    pick_sport_event,
    priority_graphic_key,
    warm_priority_graphic,
)

from _sports_wall import render_wall_score_frames


SCORE_ANIMATION_OPTION = {
    "key": "scoreAnimationTarget",
    "label": "Score Animation",
    "type": "select",
    "default": "device",
    "choices": [
        {"value": "device", "label": "Single Device"},
        {"value": "group_wall", "label": "Group Wall"},
    ],
}

SCORE_ANIMATION_TEAMS_OPTION = {
    "key": "scoreAnimationTeams",
    "label": "Show Special Graphic For",
    "type": "select",
    "default": "favorite",
    "choices": [
        {"value": "favorite", "label": "Favorite Team"},
        {"value": "both", "label": "Both Teams"},
    ],
}


def with_score_animation_option(options):
    options = list(options or [])
    if not any(isinstance(option, dict) and option.get("key") == "scoreAnimationTarget" for option in options):
        options.append(dict(SCORE_ANIMATION_OPTION))
    if not any(isinstance(option, dict) and option.get("key") == "scoreAnimationTeams" for option in options):
        options.append(dict(SCORE_ANIMATION_TEAMS_OPTION))
    return options


def _hex_color(value, fallback=(245, 250, 255)):
    value = str(value or "").strip().lstrip("#")
    if len(value) == 6:
        try:
            return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            pass
    return fallback


def _animation_width(options):
    try:
        explicit = int((options or {}).get("_width") or 0)
        if explicit > 0:
            return max(64, min(512, explicit))
    except Exception:
        pass
    target = str((options or {}).get("_target") or "").lower()
    if "128x32" in target:
        return 128
    return 64


def selected_competitor(event, favorite):
    favorite = str(favorite or "").strip().upper()
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


def animation_competitors(event, favorite, options):
    scope = str((options or {}).get("scoreAnimationTeams") or "favorite").strip().lower()
    if scope in ("both", "all", "game"):
        competition = event.get("competitions", [{}])[0]
        competitors = [item for item in competition.get("competitors", []) if item.get("team")]
        if competitors:
            return competitors
    competitor = selected_competitor(event, favorite)
    return [competitor] if competitor else []


def _score_kind(delta, sport="score"):
    sport = str(sport or "score").lower()
    try:
        delta = int(delta or 0)
    except Exception:
        delta = 0
    if sport == "basketball":
        if delta >= 3:
            return "three"
        if delta == 1:
            return "free_throw"
        return "bucket"
    if sport == "football":
        if delta >= 6:
            return "touchdown"
        if delta == 3:
            return "field_goal"
        if delta == 2:
            return "safety"
        return "score"
    if sport in ("lacrosse", "hockey", "soccer"):
        return "goal"
    if sport == "volleyball":
        return "point"
    return "score"


def competitor_won(competition, competitor):
    if not competitor:
        return False
    if competitor.get("winner") is True:
        return True
    try:
        score = int(competitor.get("score", 0) or 0)
    except Exception:
        return False
    others = [item for item in (competition or {}).get("competitors", []) if item is not competitor]
    other_scores = []
    for other in others:
        try:
            other_scores.append(int(other.get("score", 0) or 0))
        except Exception:
            pass
    return bool(other_scores) and score > max(other_scores)


def final_win_alert(card_id, state, key, competition, competitor, animation_team, sport="score", render=None, target="device", dwell_secs=7, renderer_name="_render_score_alert_frames"):
    previous = state.get(key) or {}
    if previous.get("win_animated"):
        return None
    if not competitor_won(competition, competitor):
        return None
    state[key] = {**previous, "win_animated": True, "seen": datetime.now(timezone.utc)}
    width = animation_team.get("_width") or 64
    cache_key = priority_graphic_key(card_id, animation_team, "win", width)
    render = render or render_score_alert
    target = str(target or "device").strip().lower()
    wall = target in ("group", "group_wall", "wall") or target.startswith("group:")
    return {
        "body": cached_priority_graphic(cache_key, lambda animation_team=animation_team: render(animation_team, "win")),
        "dwell_secs": dwell_secs,
        "_stay": True,
        "_no_replay": True,
        "_group_wall": {
            "type": "win",
            "renderer": renderer_name,
            "team": dict(animation_team),
            "kind": "win",
            "dwell_secs": max(dwell_secs, 7),
        } if wall else None,
    }


def _kind_lines(kind):
    kind = str(kind or "score").lower()
    if kind == "touchdown":
        return "TOUCH", "DOWN"
    if kind == "field_goal":
        return "FIELD", "GOAL"
    if kind == "safety":
        return "SAFETY", ""
    if kind == "three":
        return "3", "POINT"
    if kind == "free_throw":
        return "FREE", "THROW"
    if kind == "bucket":
        return "BUCKET", ""
    if kind == "goal":
        return "GOAL", ""
    if kind == "point":
        return "POINT", ""
    if kind in ("win", "wins", "winner", "final_win"):
        return "WINS", ""
    return "SCORE", ""


def render_score_alert_frames(team, kind="score"):
    from PIL import Image, ImageDraw, ImageFont

    if (team or {}).get("_wall") or (team or {}).get("_sport"):
        return render_wall_score_frames(team, kind, sport=(team or {}).get("_sport") or "score")

    try:
        width = int((team or {}).get("_width") or 64)
    except Exception:
        width = 64
    width = max(64, min(512, width))
    color = _hex_color((team or {}).get("color"), (117, 231, 214))
    alt = _hex_color((team or {}).get("alternateColor"), (245, 250, 255))
    bg = tuple(max(0, c // 7) for c in color)
    try:
        small = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 10)
    except Exception:
        small = big = ImageFont.load_default()

    abbr = str((team or {}).get("abbreviation") or (team or {}).get("shortDisplayName") or "TEAM").upper()[:6]
    line1, line2 = _kind_lines(kind)
    frames = []
    durations = []
    for step in range(12):
        image = Image.new("RGB", (width, 32), bg if step % 2 == 0 else (0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width - 1, 8), fill=(0, 0, 0))
        abbr_w = draw.textbbox((0, 0), abbr, font=small)[2]
        draw_sharp_text(image, ((width - abbr_w) // 2, -3), abbr, alt, small)
        line1_w = draw.textbbox((0, 0), line1, font=big)[2]
        draw_sharp_text(image, ((width - line1_w) // 2, 7), line1, color, big)
        if line2:
            line2_w = draw.textbbox((0, 0), line2, font=small)[2]
            draw_sharp_text(image, ((width - line2_w) // 2, 20), line2, alt, small)
        frames.append(image)
        durations.append(140 if step % 2 == 0 else 90)
    return frames, durations


def render_score_alert(team, kind="score"):
    frames, durations = render_score_alert_frames(team, kind)
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


def maybe_score_alert(options, card_id, url, cache, state, sport="score", default_label="TEAM"):
    favorite = (options or {}).get("favoriteTeam", "")
    if not str(favorite or "").strip():
        return None
    data = fetch_sport_scoreboard(url, cache, favorite, seconds=15)
    event = pick_sport_event(data.get("events", []), favorite)
    if not event:
        return None

    competition = event.get("competitions", [{}])[0]
    game_state = competition.get("status", {}).get("type", {}).get("state")
    competitors = animation_competitors(event, favorite, options)
    if not competitors:
        return None

    game_id = str(event.get("id") or competition.get("id") or datetime.now().strftime("%Y%m%d"))
    device_id = (options or {}).get("_device_id", "local")
    for competitor in competitors:
        team = competitor.get("team", {})
        team_key = (team.get("abbreviation") or team.get("shortDisplayName") or favorite or default_label).upper()
        key = f"{card_id}:{device_id}:{game_id}:{team_key}"
        try:
            score = int(competitor.get("score", 0) or 0)
        except Exception:
            score = 0

        animation_team = {**team, "_width": _animation_width(options), "_sport": sport}
        warm_key = priority_graphic_key(card_id, animation_team, "score", animation_team["_width"])
        previous = state.get(key)
        if game_state != "in":
            if str(game_state or "").lower() == "post":
                win = final_win_alert(
                    card_id,
                    state,
                    key,
                    competition,
                    competitor,
                    animation_team,
                    sport=sport,
                    target=(options or {}).get("scoreAnimationTarget") or "device",
                )
                if win and previous is not None:
                    return win
            state[key] = {**(state.get(key) or {}), "score": score, "animated": score, "seen": datetime.now(timezone.utc)}
            continue
        if previous is None:
            state[key] = {"score": score, "animated": score, "seen": datetime.now(timezone.utc)}
            warm_priority_graphic(warm_key, lambda animation_team=animation_team: render_score_alert(animation_team, "score"))
            continue

        last_score = int(previous.get("score", score) or 0)
        animated = int(previous.get("animated", last_score) or 0)
        state[key] = {"score": score, "animated": animated, "seen": datetime.now(timezone.utc)}
        if score > last_score and score > animated:
            state[key]["animated"] = score
            kind = _score_kind(score - last_score, sport=sport)
            target = str((options or {}).get("scoreAnimationTarget") or "device").strip().lower()
            wall = target in ("group", "group_wall", "wall") or target.startswith("group:")
            cache_key = priority_graphic_key(card_id, animation_team, kind, animation_team["_width"])
            return {
                "body": cached_priority_graphic(cache_key, lambda animation_team=animation_team, kind=kind: render_score_alert(animation_team, kind)),
                "dwell_secs": 5,
                "_stay": True,
                "_no_replay": True,
                "_group_wall": {
                    "type": kind,
                    "renderer": "_render_score_alert_frames",
                    "team": dict(animation_team),
                    "kind": kind,
                    "dwell_secs": 6,
                } if wall else None,
            }
    return None
