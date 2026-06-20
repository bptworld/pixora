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

CARD_ID = "college_baseball"
CARD_NAME = "College Baseball"
CARD_DETAIL = "Live ESPN college baseball scoreboard"
CARD_OPTIONS = [
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "BC",
        "choices": [
            {"value": "ASU", "label": "Arizona State Sun Devils"},
            {"value": "ARIZ", "label": "Arizona Wildcats"},
            {"value": "ARK", "label": "Arkansas Razorbacks"},
            {"value": "AUB", "label": "Auburn Tigers"},
            {"value": "BC", "label": "Boston College Eagles"},
            {"value": "CAL", "label": "California Golden Bears"},
            {"value": "DUKE", "label": "Duke Blue Devils"},
            {"value": "ECU", "label": "East Carolina Pirates"},
            {"value": "FLA", "label": "Florida Gators"},
            {"value": "FSU", "label": "Florida State Seminoles"},
            {"value": "UGA", "label": "Georgia Bulldogs"},
            {"value": "GT", "label": "Georgia Tech Yellow Jackets"},
            {"value": "UK", "label": "Kentucky Wildcats"},
            {"value": "LOU", "label": "Louisville Cardinals"},
            {"value": "LSU", "label": "LSU Tigers"},
            {"value": "MD", "label": "Maryland Terrapins"},
            {"value": "MSU", "label": "Michigan State Spartans"},
            {"value": "MICH", "label": "Michigan Wolverines"},
            {"value": "MINN", "label": "Minnesota Golden Gophers"},
            {"value": "MIZ", "label": "Missouri Tigers"},
            {"value": "NCSU", "label": "NC State Wolfpack"},
            {"value": "NEB", "label": "Nebraska Cornhuskers"},
            {"value": "UNC", "label": "North Carolina Tar Heels"},
            {"value": "ND", "label": "Notre Dame Fighting Irish"},
            {"value": "MISS", "label": "Ole Miss Rebels"},
            {"value": "RUTG", "label": "Rutgers Scarlet Knights"},
            {"value": "STAN", "label": "Stanford Cardinal"},
            {"value": "UCLA", "label": "UCLA Bruins"},
            {"value": "CONN", "label": "UConn Huskies"},
            {"value": "USC", "label": "USC Trojans"},
            {"value": "WAKE", "label": "Wake Forest Demon Deacons"},
        ],
    }
]

CARD_OPTIONS.append({
    "key": "runAnimationTarget",
    "label": "Run Scored Animation",
    "type": "select",
    "default": "device",
    "choices": [
        {"value": "device", "label": "Single Device"},
        {"value": "group_wall", "label": "Group Wall"},
    ],
})
CARD_OPTIONS.append(dict(SCORE_ANIMATION_TEAMS_OPTION))

_URL = "https://site.api.espn.com/apis/site/v2/sports/baseball/college-baseball/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_COLOR = (95, 210, 130)
_RUN_STATE = {}


def _baseball_module():
    spec = importlib.util.spec_from_file_location("_pixora_mlb_anim", Path(__file__).with_name("mlb.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_BASEBALL_ANIM = _baseball_module()
_render_run_animation = _BASEBALL_ANIM._render_run_animation
_render_run_animation_frames = _BASEBALL_ANIM._render_run_animation_frames
_run_animation_width = _BASEBALL_ANIM._run_animation_width


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
        if not team.get("logo") and team.get("abbreviation"):
            team = {**team, "logo": f"https://a.espncdn.com/i/teamlogos/ncaa/500/{team.get('abbreviation', '').lower()}.png"}
        team_key = (team.get("abbreviation") or team.get("shortDisplayName") or favorite or "CBASE").upper()
        key = f"{device_id}:{game_id}:{team_key}"
        try:
            score = int(competitor.get("score", 0) or 0)
        except Exception:
            score = 0
        animation_team = {**team, "_width": _run_animation_width(options)}
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
            target = str((options or {}).get("runAnimationTarget") or "device").strip().lower()
            wall = target in ("group", "group_wall", "wall") or target.startswith("group:")
            return {
                "body": cached_priority_graphic(cache_key, lambda animation_team=animation_team: _render_run_animation(animation_team)),
                "dwell_secs": 6,
                "_stay": True,
                "_no_replay": True,
                "_priority": True,
                "_group_wall": {"type": "run", "renderer": "_render_run_animation_frames", "team": dict(animation_team), "dwell_secs": 6} if wall else None,
            }
    return None


def render(options=None):
    opts = options or {}
    animation = _maybe_run_animation(opts)
    if animation:
        return animation
    return render_sport_card(opts, _URL, _CACHE, _COLOR, "NO CBASE")
