from datetime import datetime, timezone

from card_utils import render_sport_card
from _sports_breaking import maybe_score_alert, render_score_alert_frames, with_score_animation_option

CARD_ID = "nba_g_league"
CARD_NAME = "NBA G League"
CARD_DETAIL = "Live ESPN NBA G League scoreboard"
CARD_OPTIONS = with_score_animation_option([
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "MNE",
        "choices": [
            {"value": "AUS", "label": "Austin Spurs"},
            {"value": "BIR", "label": "Birmingham Squadron"},
            {"value": "CAP", "label": "Capital City Go-Go"},
            {"value": "CLC", "label": "Cleveland Charge"},
            {"value": "CPS", "label": "College Park Skyhawks"},
            {"value": "DEL", "label": "Delaware Blue Coats"},
            {"value": "GRD", "label": "Grand Rapids Gold"},
            {"value": "GBO", "label": "Greensboro Swarm"},
            {"value": "IWA", "label": "Iowa Wolves"},
            {"value": "LIN", "label": "Long Island Nets"},
            {"value": "MNE", "label": "Maine Celtics"},
            {"value": "MHU", "label": "Memphis Hustle"},
            {"value": "MXC", "label": "Mexico City Capitanes"},
            {"value": "MCC", "label": "Motor City Cruise"},
            {"value": "OKL", "label": "Oklahoma City Blue"},
            {"value": "OSC", "label": "Osceola Magic"},
            {"value": "RAP", "label": "Raptors 905"},
            {"value": "RGV", "label": "Rio Grande Valley Vipers"},
            {"value": "RCITY", "label": "Rip City Remix"},
            {"value": "SLC", "label": "Salt Lake City Stars"},
            {"value": "SAN", "label": "San Diego Clippers"},
            {"value": "SCW", "label": "Santa Cruz Warriors"},
            {"value": "SXF", "label": "Sioux Falls Skyforce"},
            {"value": "SBL", "label": "South Bay Lakers"},
            {"value": "STO", "label": "Stockton Kings"},
            {"value": "TEX", "label": "Texas Legends"},
            {"value": "VALLEY", "label": "Valley Suns"},
            {"value": "WES", "label": "Westchester Knicks"},
            {"value": "WCB", "label": "Windy City Bulls"},
            {"value": "WIS", "label": "Wisconsin Herd"},
        ],
    }
])

_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba-development/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_COLOR = (85, 180, 255)
_SCORE_STATE = {}
_render_score_alert_frames = render_score_alert_frames


def render(options=None):
    opts = options or {}
    animation = maybe_score_alert(opts, CARD_ID, _URL, _CACHE, _SCORE_STATE, sport="basketball", default_label="GLEAG")
    if animation:
        if animation.get("_group_wall"):
            normal_card = render_sport_card(opts, _URL, _CACHE, _COLOR, "NO GLEAG")
            if normal_card:
                animation["body"] = normal_card
                animation["dwell_secs"] = opts.get("_dwell", 10)
                animation["_no_replay"] = False
        return animation
    return render_sport_card(opts, _URL, _CACHE, _COLOR, "NO GLEAG")
