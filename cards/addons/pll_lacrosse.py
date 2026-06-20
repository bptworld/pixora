from datetime import datetime, timezone

from card_utils import render_sport_card
from _sports_breaking import maybe_score_alert, render_score_alert_frames, with_score_animation_option

CARD_ID = "pll_lacrosse"
CARD_NAME = "PLL Lacrosse"
CARD_DETAIL = "Live ESPN PLL scoreboard"
CARD_OPTIONS = with_score_animation_option([
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "CAN",
        "choices": [
            {"value": "CAN", "label": "Boston Cannons"},
            {"value": "RED", "label": "California Redwoods"},
            {"value": "CHA", "label": "Carolina Chaos"},
            {"value": "OUT", "label": "Denver Outlaws"},
            {"value": "WHP", "label": "Maryland Whipsnakes"},
            {"value": "ATL", "label": "New York Atlas"},
            {"value": "WAT", "label": "Philadelphia Waterdogs"},
            {"value": "ARC", "label": "Utah Archers"},
        ],
    }
])

_URL = "https://site.api.espn.com/apis/site/v2/sports/lacrosse/pll/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_COLOR = (220, 120, 255)
_SCORE_STATE = {}
_render_score_alert_frames = render_score_alert_frames


def render(options=None):
    opts = options or {}
    animation = maybe_score_alert(opts, CARD_ID, _URL, _CACHE, _SCORE_STATE, sport="lacrosse", default_label="PLL")
    if animation:
        return animation
    return render_sport_card(opts, _URL, _CACHE, _COLOR, "NO PLL")
