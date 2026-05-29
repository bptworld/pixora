from datetime import datetime, timezone

from card_utils import render_sport_card
from _sports_breaking import maybe_score_alert, render_score_alert_frames, with_score_animation_option

CARD_ID = "womens_college_volleyball"
CARD_NAME = "Women's College Volleyball"
CARD_DETAIL = "Live ESPN women's college volleyball scoreboard"
CARD_OPTIONS = with_score_animation_option([
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "UCLA",
        "choices": [
            {"value": "AMER", "label": "American University Eagles"},
            {"value": "ASU", "label": "Arizona State Sun Devils"},
            {"value": "ARIZ", "label": "Arizona Wildcats"},
            {"value": "ARK", "label": "Arkansas Razorbacks"},
            {"value": "AUB", "label": "Auburn Tigers"},
            {"value": "BOIS", "label": "Boise State Broncos"},
            {"value": "CAL", "label": "California Golden Bears"},
            {"value": "COLO", "label": "Colorado Buffaloes"},
            {"value": "CSU", "label": "Colorado State Rams"},
            {"value": "DEL", "label": "Delaware Blue Hens"},
            {"value": "FAMU", "label": "Florida A&M Rattlers"},
            {"value": "FLA", "label": "Florida Gators"},
            {"value": "FSU", "label": "Florida State Seminoles"},
            {"value": "UGA", "label": "Georgia Bulldogs"},
            {"value": "GT", "label": "Georgia Tech Yellow Jackets"},
            {"value": "HAW", "label": "Hawai'i Rainbow Warriors"},
            {"value": "IU", "label": "Indiana Hoosiers"},
            {"value": "ISU", "label": "Iowa State Cyclones"},
            {"value": "UK", "label": "Kentucky Wildcats"},
            {"value": "NU", "label": "Northwestern Wildcats"},
            {"value": "ND", "label": "Notre Dame Fighting Irish"},
            {"value": "SDSU", "label": "San Diego State Aztecs"},
            {"value": "SJSU", "label": "San José State Spartans"},
            {"value": "STAN", "label": "Stanford Cardinal"},
            {"value": "UAB", "label": "UAB Blazers"},
            {"value": "UCLA", "label": "UCLA Bruins"},
            {"value": "CONN", "label": "UConn Huskies"},
            {"value": "USC", "label": "USC Trojans"},
            {"value": "YALE", "label": "Yale Bulldogs"},
        ],
    }
])

_URL = "https://site.api.espn.com/apis/site/v2/sports/volleyball/womens-college-volleyball/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_COLOR = (255, 185, 85)
_SCORE_STATE = {}
_render_score_alert_frames = render_score_alert_frames


def render(options=None):
    opts = options or {}
    animation = maybe_score_alert(opts, CARD_ID, _URL, _CACHE, _SCORE_STATE, sport="volleyball", default_label="WVB")
    if animation:
        if animation.get("_group_wall"):
            normal_card = render_sport_card(opts, _URL, _CACHE, _COLOR, "NO WVB")
            if normal_card:
                animation["body"] = normal_card
                animation["dwell_secs"] = opts.get("_dwell", 10)
                animation["_no_replay"] = False
        return animation
    return render_sport_card(opts, _URL, _CACHE, _COLOR, "NO WVB")
