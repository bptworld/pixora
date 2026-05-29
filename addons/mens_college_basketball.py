from datetime import datetime, timezone

from card_utils import render_sport_card
from _sports_breaking import maybe_score_alert, render_score_alert_frames, with_score_animation_option

CARD_ID = "mens_college_basketball"
CARD_NAME = "Men's College Basketball"
CARD_DETAIL = "Live ESPN scoreboard"
CARD_OPTIONS = with_score_animation_option([
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "CONN",
        "choices": [
            {"value": "ALA", "label": "Alabama Crimson Tide"},
            {"value": "ARIZ", "label": "Arizona Wildcats"},
            {"value": "ARK", "label": "Arkansas Razorbacks"},
            {"value": "AUB", "label": "Auburn Tigers"},
            {"value": "BAY", "label": "Baylor Bears"},
            {"value": "BOIS", "label": "Boise State Broncos"},
            {"value": "BUT", "label": "Butler Bulldogs"},
            {"value": "BYU", "label": "BYU Cougars"},
            {"value": "CAL", "label": "California Golden Bears"},
            {"value": "CLEM", "label": "Clemson Tigers"},
            {"value": "CONN", "label": "UConn Huskies"},
            {"value": "CREI", "label": "Creighton Bluejays"},
            {"value": "DUKE", "label": "Duke Blue Devils"},
            {"value": "FLA", "label": "Florida Gators"},
            {"value": "FSU", "label": "Florida State Seminoles"},
            {"value": "GONZ", "label": "Gonzaga Bulldogs"},
            {"value": "GT", "label": "Georgia Tech Yellow Jackets"},
            {"value": "GTWN", "label": "Georgetown Hoyas"},
            {"value": "HOU", "label": "Houston Cougars"},
            {"value": "ILL", "label": "Illinois Fighting Illini"},
            {"value": "IU", "label": "Indiana Hoosiers"},
            {"value": "IOWA", "label": "Iowa Hawkeyes"},
            {"value": "ISU", "label": "Iowa State Cyclones"},
            {"value": "KU", "label": "Kansas Jayhawks"},
            {"value": "KSU", "label": "Kansas State Wildcats"},
            {"value": "UK", "label": "Kentucky Wildcats"},
            {"value": "LOU", "label": "Louisville Cardinals"},
            {"value": "MARQ", "label": "Marquette Golden Eagles"},
            {"value": "MD", "label": "Maryland Terrapins"},
            {"value": "MEM", "label": "Memphis Tigers"},
            {"value": "MICH", "label": "Michigan Wolverines"},
            {"value": "MSU", "label": "Michigan State Spartans"},
            {"value": "MINN", "label": "Minnesota Golden Gophers"},
            {"value": "MIZZ", "label": "Missouri Tigers"},
            {"value": "UNC", "label": "North Carolina Tar Heels"},
            {"value": "NCST", "label": "NC State Wolfpack"},
            {"value": "NEB", "label": "Nebraska Cornhuskers"},
            {"value": "NU", "label": "Northwestern Wildcats"},
            {"value": "ND", "label": "Notre Dame Fighting Irish"},
            {"value": "OSU", "label": "Ohio State Buckeyes"},
            {"value": "OKLA", "label": "Oklahoma Sooners"},
            {"value": "ORE", "label": "Oregon Ducks"},
            {"value": "PUR", "label": "Purdue Boilermakers"},
            {"value": "RUTG", "label": "Rutgers Scarlet Knights"},
            {"value": "SDSU", "label": "San Diego State Aztecs"},
            {"value": "STAN", "label": "Stanford Cardinal"},
            {"value": "SYR", "label": "Syracuse Orange"},
            {"value": "TENN", "label": "Tennessee Volunteers"},
            {"value": "TEX", "label": "Texas Longhorns"},
            {"value": "TA&M", "label": "Texas A&M Aggies"},
            {"value": "UCLA", "label": "UCLA Bruins"},
            {"value": "USC", "label": "USC Trojans"},
            {"value": "VILL", "label": "Villanova Wildcats"},
            {"value": "UVA", "label": "Virginia Cavaliers"},
            {"value": "WIS", "label": "Wisconsin Badgers"},
            {"value": "XAV", "label": "Xavier Musketeers"},
        ],
    }
])

_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_COLOR = (255, 185, 80)
_SCORE_STATE = {}
_render_score_alert_frames = render_score_alert_frames


def render(options=None):
    opts = options or {}
    animation = maybe_score_alert(opts, CARD_ID, _URL, _CACHE, _SCORE_STATE, sport="basketball", default_label="MCBB")
    if animation:
        if animation.get("_group_wall"):
            normal_card = render_sport_card(opts, _URL, _CACHE, _COLOR, "NO MCBB")
            if normal_card:
                animation["body"] = normal_card
                animation["dwell_secs"] = opts.get("_dwell", 10)
                animation["_no_replay"] = False
        return animation
    return render_sport_card(opts, _URL, _CACHE, _COLOR, "NO MCBB")
