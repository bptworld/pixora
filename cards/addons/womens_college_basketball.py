from datetime import datetime, timezone

from card_utils import render_sport_card
from _sports_breaking import maybe_score_alert, render_score_alert_frames, with_score_animation_option

CARD_ID = "womens_college_basketball"
CARD_NAME = "Women's College Basketball"
CARD_DETAIL = "Live ESPN scoreboard"
CARD_OPTIONS = with_score_animation_option([
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "CONN",
        "choices": [
            {"value": "ARIZ", "label": "Arizona Wildcats"},
            {"value": "ARK", "label": "Arkansas Razorbacks"},
            {"value": "BAY", "label": "Baylor Bears"},
            {"value": "CAL", "label": "California Golden Bears"},
            {"value": "CONN", "label": "UConn Huskies"},
            {"value": "DUKE", "label": "Duke Blue Devils"},
            {"value": "FLA", "label": "Florida Gators"},
            {"value": "FSU", "label": "Florida State Seminoles"},
            {"value": "UGA", "label": "Georgia Lady Bulldogs"},
            {"value": "GT", "label": "Georgia Tech Yellow Jackets"},
            {"value": "IU", "label": "Indiana Hoosiers"},
            {"value": "IOWA", "label": "Iowa Hawkeyes"},
            {"value": "ISU", "label": "Iowa State Cyclones"},
            {"value": "UK", "label": "Kentucky Wildcats"},
            {"value": "LOU", "label": "Louisville Cardinals"},
            {"value": "LSU", "label": "LSU Tigers"},
            {"value": "MD", "label": "Maryland Terrapins"},
            {"value": "MICH", "label": "Michigan Wolverines"},
            {"value": "MSU", "label": "Michigan State Spartans"},
            {"value": "MINN", "label": "Minnesota Golden Gophers"},
            {"value": "MISS", "label": "Ole Miss Rebels"},
            {"value": "MISSST", "label": "Mississippi State Bulldogs"},
            {"value": "UNC", "label": "North Carolina Tar Heels"},
            {"value": "NCST", "label": "NC State Wolfpack"},
            {"value": "ND", "label": "Notre Dame Fighting Irish"},
            {"value": "OSU", "label": "Ohio State Buckeyes"},
            {"value": "OKLA", "label": "Oklahoma Sooners"},
            {"value": "ORE", "label": "Oregon Ducks"},
            {"value": "SC", "label": "South Carolina Gamecocks"},
            {"value": "STAN", "label": "Stanford Cardinal"},
            {"value": "TENN", "label": "Tennessee Lady Volunteers"},
            {"value": "TEX", "label": "Texas Longhorns"},
            {"value": "UCLA", "label": "UCLA Bruins"},
            {"value": "USC", "label": "USC Trojans"},
            {"value": "UVA", "label": "Virginia Cavaliers"},
            {"value": "VT", "label": "Virginia Tech Hokies"},
            {"value": "WASH", "label": "Washington Huskies"},
            {"value": "WIS", "label": "Wisconsin Badgers"},
        ],
    }
])

_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/womens-college-basketball/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_COLOR = (255, 135, 205)
_SCORE_STATE = {}
_render_score_alert_frames = render_score_alert_frames


def render(options=None):
    opts = options or {}
    animation = maybe_score_alert(opts, CARD_ID, _URL, _CACHE, _SCORE_STATE, sport="basketball", default_label="WCBB")
    if animation:
        return animation
    return render_sport_card(opts, _URL, _CACHE, _COLOR, "NO WCBB")
