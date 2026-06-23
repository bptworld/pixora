import importlib.util
from pathlib import Path
from datetime import datetime, timezone

from card_utils import render_sport_card
from _sports_breaking import maybe_score_alert, with_score_animation_option

CARD_ID = "cfl"
CARD_NAME = "CFL Scores"
CARD_DETAIL = "Live ESPN CFL scoreboard"
CARD_OPTIONS = with_score_animation_option([
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "BCL",
        "choices": [
            {"value": "BCL", "label": "BC Lions"},
            {"value": "CSP", "label": "Calgary Stampeders"},
            {"value": "EES", "label": "Edmonton Elks"},
            {"value": "HTC", "label": "Hamilton Tiger-Cats"},
            {"value": "MTA", "label": "Montreal Alouettes"},
            {"value": "ORB", "label": "Ottawa Redblacks"},
            {"value": "SRR", "label": "Saskatchewan Roughriders"},
            {"value": "TAT", "label": "Toronto Argonauts"},
            {"value": "WBB", "label": "Winnipeg Blue Bombers"},
        ],
    }
])

_URL = "https://site.api.espn.com/apis/site/v2/sports/football/cfl/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_COLOR = (235, 70, 80)
_SCORE_STATE = {}


def _football_module():
    spec = importlib.util.spec_from_file_location("_pixora_nfl_anim", Path(__file__).with_name("nfl.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_FOOTBALL_ANIM = _football_module()
_render_score_animation = _FOOTBALL_ANIM._render_score_animation
_render_score_animation_frames = _FOOTBALL_ANIM._render_score_animation_frames


def render(options=None):
    opts = options or {}
    animation = maybe_score_alert(
        opts, CARD_ID, _URL, _CACHE, _SCORE_STATE,
        sport="football", default_label="CFL",
        render=_render_score_animation,
        renderer_name="_render_score_animation_frames",
    )
    if animation:
        return animation
    return render_sport_card(opts, _URL, _CACHE, _COLOR, "NO CFL")
