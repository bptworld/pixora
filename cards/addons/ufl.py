import importlib.util
from pathlib import Path
from datetime import datetime, timezone

from card_utils import (
    cached_priority_graphic,
    fetch_json_url,
    fetch_sport_scoreboard,
    pick_sport_event,
    priority_graphic_key,
    render_sport_card,
    warm_priority_graphic,
)

from _sports_breaking import SCORE_ANIMATION_TEAMS_OPTION, animation_competitors, final_win_alert

CARD_ID = "ufl"
CARD_NAME = "UFL Scores"
CARD_DETAIL = "Live ESPN UFL scoreboard"
CARD_OPTIONS = [
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "DC",
        "choices": [
            {"value": "BHAM", "label": "Birmingham Stallions"},
            {"value": "CLB", "label": "Columbus Aviators"},
            {"value": "DAL", "label": "Dallas Renegades"},
            {"value": "DC", "label": "DC Defenders"},
            {"value": "HOU", "label": "Houston Gamblers"},
            {"value": "LOU", "label": "Louisville Kings"},
            {"value": "ORL", "label": "Orlando Storm"},
            {"value": "STL", "label": "St. Louis Battlehawks"},
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
CARD_OPTIONS.append(dict(SCORE_ANIMATION_TEAMS_OPTION))

_URL = "https://site.api.espn.com/apis/site/v2/sports/football/ufl/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_SUMMARY_CACHE = {}
_SCORE_STATE = {}
_COLOR = (80, 190, 255)


def _football_module():
    spec = importlib.util.spec_from_file_location("_pixora_nfl_anim", Path(__file__).with_name("nfl.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_FOOTBALL_ANIM = _football_module()
_render_score_animation = _FOOTBALL_ANIM._render_score_animation
_render_score_animation_frames = _FOOTBALL_ANIM._render_score_animation_frames
_animation_width = _FOOTBALL_ANIM._animation_width


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
    url = f"https://site.api.espn.com/apis/site/v2/sports/football/ufl/summary?event={event_id}"
    return fetch_json_url(url, _SUMMARY_CACHE, seconds=15)


def _play_score_for_competitor(play, competitor):
    side = competitor.get("homeAway")
    key = "homeScore" if side == "home" else "awayScore"
    try:
        return int(play.get(key, 0) or 0)
    except Exception:
        return 0


def _team_logo_url(team):
    if (team or {}).get("logo"):
        return team.get("logo")
    logos = (team or {}).get("logos") or []
    if logos:
        return logos[0].get("href") or ""
    abbr = str((team or {}).get("abbreviation") or "").strip().lower()
    return f"https://a.espncdn.com/i/teamlogos/ufl/500/{abbr}.png" if abbr else ""


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
        headshot = f"https://a.espncdn.com/i/headshots/ufl/players/full/{athlete_id}.png"
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
    for competitor in competitors:
        team = competitor.get("team", {})
        if not team.get("logo") and team.get("abbreviation"):
            team = {**team, "logo": f"https://a.espncdn.com/i/teamlogos/ufl/500/{team.get('abbreviation', '').lower()}.png"}
        team_key = (team.get("abbreviation") or team.get("shortDisplayName") or favorite or "UFL").upper()
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
                    target=(options or {}).get("scoreAnimationTarget") or "device", dwell_secs=7,
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
    return render_sport_card(opts, _URL, _CACHE, _COLOR, "NO UFL")
