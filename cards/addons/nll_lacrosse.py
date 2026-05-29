from datetime import datetime, timezone

from card_utils import render_sport_card
from _sports_breaking import maybe_score_alert, render_score_alert_frames, with_score_animation_option

CARD_ID = "nll_lacrosse"
CARD_NAME = "NLL Lacrosse"
CARD_DETAIL = "Live ESPN NLL scoreboard"
CARD_OPTIONS = with_score_animation_option([
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "BUF",
        "choices": [
            {"value": "BUF", "label": "Buffalo Bandits"},
            {"value": "CGY", "label": "Calgary Roughnecks"},
            {"value": "COL", "label": "Colorado Mammoth"},
            {"value": "GA", "label": "Georgia Swarm"},
            {"value": "HFX", "label": "Halifax Thunderbirds"},
            {"value": "LV", "label": "Las Vegas Desert Dogs"},
            {"value": "OSH", "label": "Oshawa FireWolves"},
            {"value": "OTT", "label": "Ottawa Black Bears"},
            {"value": "PHI", "label": "Philadelphia Wings"},
            {"value": "ROC", "label": "Rochester Knighthawks"},
            {"value": "SD", "label": "San Diego Seals"},
            {"value": "SAS", "label": "Saskatchewan Rush"},
            {"value": "TOR", "label": "Toronto Rock"},
            {"value": "VAN", "label": "Vancouver Warriors"},
        ],
    }
])

_URL = "https://site.api.espn.com/apis/site/v2/sports/lacrosse/nll/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_COLOR = (170, 125, 255)
_SCORE_STATE = {}
_render_score_alert_frames = render_score_alert_frames


def render(options=None):
    opts = options or {}
    animation = maybe_score_alert(opts, CARD_ID, _URL, _CACHE, _SCORE_STATE, sport="lacrosse", default_label="NLL")
    if animation:
        if animation.get("_group_wall"):
            normal_card = render_sport_card(opts, _URL, _CACHE, _COLOR, "NO NLL")
            if normal_card:
                animation["body"] = normal_card
                animation["dwell_secs"] = opts.get("_dwell", 10)
                animation["_no_replay"] = False
        return animation
    return render_sport_card(opts, _URL, _CACHE, _COLOR, "NO NLL")
