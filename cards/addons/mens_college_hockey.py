import importlib.util
from pathlib import Path
from datetime import datetime, timezone

from card_utils import (
    cached_priority_graphic,
    fetch_sport_scoreboard,
    pick_sport_event,
    priority_graphic_key,
    render_sport_card,
    warm_priority_graphic,
)

from _sports_breaking import SCORE_ANIMATION_TEAMS_OPTION, animation_competitors, final_win_alert

CARD_ID = "mens_college_hockey"
CARD_NAME = "NCAA Hockey"
CARD_DETAIL = "Live ESPN men's college hockey scoreboard"
CARD_OPTIONS = [
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "BC",
        "choices": [
            {"value": "AF", "label": "Air Force Falcons"},
            {"value": "ASU", "label": "Arizona State Sun Devils"},
            {"value": "ARMY", "label": "Army Black Knights"},
            {"value": "BST", "label": "Bemidji State Beavers"},
            {"value": "BC", "label": "Boston College Eagles"},
            {"value": "BU", "label": "Boston University Terriers"},
            {"value": "BGSU", "label": "Bowling Green Falcons"},
            {"value": "BRWN", "label": "Brown Bears"},
            {"value": "COR", "label": "Cornell Big Red"},
            {"value": "DART", "label": "Dartmouth Big Green"},
            {"value": "HARV", "label": "Harvard Crimson"},
            {"value": "HC", "label": "Holy Cross Crusaders"},
            {"value": "ME", "label": "Maine Black Bears"},
            {"value": "MASS", "label": "Massachusetts Minutemen"},
            {"value": "M-OH", "label": "Miami (OH) RedHawks"},
            {"value": "MSU", "label": "Michigan State Spartans"},
            {"value": "MICH", "label": "Michigan Wolverines"},
            {"value": "UMD", "label": "Minnesota Duluth Bulldogs"},
            {"value": "MINN", "label": "Minnesota Golden Gophers"},
            {"value": "UNH", "label": "New Hampshire Wildcats"},
            {"value": "UND", "label": "North Dakota Fighting Hawks"},
            {"value": "NE", "label": "Northeastern Huskies"},
            {"value": "ND", "label": "Notre Dame Fighting Irish"},
            {"value": "OSU", "label": "Ohio State Buckeyes"},
            {"value": "PSU", "label": "Penn State Nittany Lions"},
            {"value": "PRIN", "label": "Princeton Tigers"},
            {"value": "RIT", "label": "RIT Tigers"},
            {"value": "CONN", "label": "UConn Huskies"},
            {"value": "UVM", "label": "Vermont Catamounts"},
            {"value": "WIS", "label": "Wisconsin Badgers"},
            {"value": "YALE", "label": "Yale Bulldogs"},
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

_URL = "https://site.api.espn.com/apis/site/v2/sports/hockey/mens-college-hockey/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_COLOR = (80, 220, 255)
_GOAL_STATE = {}


def _hockey_module():
    spec = importlib.util.spec_from_file_location("_pixora_nhl_anim", Path(__file__).with_name("nhl.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_HOCKEY_ANIM = _hockey_module()
_render_goal_animation = _HOCKEY_ANIM._render_goal_animation
_render_goal_animation_frames = _HOCKEY_ANIM._render_goal_animation_frames
_animation_width = _HOCKEY_ANIM._animation_width


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
        if not team.get("logo") and team.get("abbreviation"):
            team = {**team, "logo": f"https://a.espncdn.com/i/teamlogos/ncaa/500/{team.get('abbreviation', '').lower()}.png"}
        team_key = (team.get("abbreviation") or team.get("shortDisplayName") or favorite or "HOCK").upper()
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
                "dwell_secs": 6,
                "_stay": True,
                "_no_replay": True,
                "_priority": True,
                "_group_wall": {"type": "goal", "renderer": "_render_goal_animation_frames", "team": dict(animation_team), "dwell_secs": 6} if wall else None,
            }
    return None


def render(options=None):
    opts = options or {}
    animation = _maybe_goal_animation(opts)
    if animation:
        if animation.get("_group_wall"):
            normal_card = render_sport_card(opts, _URL, _CACHE, _COLOR, "NO HOCK")
            if normal_card:
                animation["body"] = normal_card
                animation["dwell_secs"] = opts.get("_dwell", 10)
                animation["_no_replay"] = False
        return animation
    return render_sport_card(opts, _URL, _CACHE, _COLOR, "NO HOCK")
