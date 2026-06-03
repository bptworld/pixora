from datetime import datetime, timezone

from card_utils import render_sport_card
from _sports_breaking import maybe_score_alert, render_score_alert_frames, with_score_animation_option

CARD_ID = "wnba"
CARD_NAME = "WNBA Scores"
CARD_DETAIL = "Live ESPN scoreboard"
CARD_OPTIONS = with_score_animation_option([
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "CONN",
        "choices": [
            {"value": "ATL", "label": "Atlanta Dream"},
            {"value": "CHI", "label": "Chicago Sky"},
            {"value": "CONN", "label": "Connecticut Sun"},
            {"value": "DAL", "label": "Dallas Wings"},
            {"value": "GS", "label": "Golden State Valkyries"},
            {"value": "IND", "label": "Indiana Fever"},
            {"value": "LV", "label": "Las Vegas Aces"},
            {"value": "LA", "label": "Los Angeles Sparks"},
            {"value": "MIN", "label": "Minnesota Lynx"},
            {"value": "NY", "label": "New York Liberty"},
            {"value": "PHX", "label": "Phoenix Mercury"},
            {"value": "POR", "label": "Portland Fire"},
            {"value": "SEA", "label": "Seattle Storm"},
            {"value": "TOR", "label": "Toronto Tempo"},
            {"value": "WSH", "label": "Washington Mystics"},
        ],
    }
])

_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_COLOR = (210, 120, 255)
_SCORE_STATE = {}
_render_score_alert_frames = render_score_alert_frames


def render(options=None):
    opts = options or {}
    animation = maybe_score_alert(opts, CARD_ID, _URL, _CACHE, _SCORE_STATE, sport="basketball", default_label="WNBA")
    if animation:
        if animation.get("_group_wall"):
            normal_card = render_sport_card(opts, _URL, _CACHE, _COLOR, "NO WNBA")
            if normal_card:
                animation["body"] = normal_card
                animation["dwell_secs"] = opts.get("_dwell", 10)
                animation["_no_replay"] = False
        return animation
    return render_sport_card(opts, _URL, _CACHE, _COLOR, "NO WNBA")
