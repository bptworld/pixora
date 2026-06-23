import importlib.util
from pathlib import Path
from datetime import datetime, timezone

from card_utils import render_sport_card
from _sports_breaking import maybe_score_alert, with_score_animation_option

CARD_ID = "college_football"
CARD_NAME = "College Football"
CARD_DETAIL = "Live ESPN scoreboard"
CARD_OPTIONS = with_score_animation_option([
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "BC",
        "choices": [
            {"value": "ALA", "label": "Alabama Crimson Tide"},
            {"value": "APP", "label": "Appalachian State Mountaineers"},
            {"value": "ARIZ", "label": "Arizona Wildcats"},
            {"value": "ASU", "label": "Arizona State Sun Devils"},
            {"value": "ARK", "label": "Arkansas Razorbacks"},
            {"value": "ARMY", "label": "Army Black Knights"},
            {"value": "AUB", "label": "Auburn Tigers"},
            {"value": "BAY", "label": "Baylor Bears"},
            {"value": "BC", "label": "Boston College Eagles"},
            {"value": "BOIS", "label": "Boise State Broncos"},
            {"value": "BYU", "label": "BYU Cougars"},
            {"value": "CAL", "label": "California Golden Bears"},
            {"value": "CLEM", "label": "Clemson Tigers"},
            {"value": "CIN", "label": "Cincinnati Bearcats"},
            {"value": "COLO", "label": "Colorado Buffaloes"},
            {"value": "DUKE", "label": "Duke Blue Devils"},
            {"value": "FLA", "label": "Florida Gators"},
            {"value": "FSU", "label": "Florida State Seminoles"},
            {"value": "UGA", "label": "Georgia Bulldogs"},
            {"value": "GT", "label": "Georgia Tech Yellow Jackets"},
            {"value": "HOU", "label": "Houston Cougars"},
            {"value": "ILL", "label": "Illinois Fighting Illini"},
            {"value": "IND", "label": "Indiana Hoosiers"},
            {"value": "IOWA", "label": "Iowa Hawkeyes"},
            {"value": "ISU", "label": "Iowa State Cyclones"},
            {"value": "KU", "label": "Kansas Jayhawks"},
            {"value": "KSU", "label": "Kansas State Wildcats"},
            {"value": "UK", "label": "Kentucky Wildcats"},
            {"value": "LSU", "label": "LSU Tigers"},
            {"value": "LOU", "label": "Louisville Cardinals"},
            {"value": "MD", "label": "Maryland Terrapins"},
            {"value": "MIA", "label": "Miami Hurricanes"},
            {"value": "MICH", "label": "Michigan Wolverines"},
            {"value": "MSU", "label": "Michigan State Spartans"},
            {"value": "MINN", "label": "Minnesota Golden Gophers"},
            {"value": "MISS", "label": "Ole Miss Rebels"},
            {"value": "MSST", "label": "Mississippi State Bulldogs"},
            {"value": "MIZZ", "label": "Missouri Tigers"},
            {"value": "NEB", "label": "Nebraska Cornhuskers"},
            {"value": "UNC", "label": "North Carolina Tar Heels"},
            {"value": "NCST", "label": "NC State Wolfpack"},
            {"value": "NU", "label": "Northwestern Wildcats"},
            {"value": "ND", "label": "Notre Dame Fighting Irish"},
            {"value": "OSU", "label": "Ohio State Buckeyes"},
            {"value": "OKLA", "label": "Oklahoma Sooners"},
            {"value": "OKST", "label": "Oklahoma State Cowboys"},
            {"value": "ORE", "label": "Oregon Ducks"},
            {"value": "ORST", "label": "Oregon State Beavers"},
            {"value": "PSU", "label": "Penn State Nittany Lions"},
            {"value": "PITT", "label": "Pittsburgh Panthers"},
            {"value": "PUR", "label": "Purdue Boilermakers"},
            {"value": "RUTG", "label": "Rutgers Scarlet Knights"},
            {"value": "SC", "label": "South Carolina Gamecocks"},
            {"value": "STAN", "label": "Stanford Cardinal"},
            {"value": "SYR", "label": "Syracuse Orange"},
            {"value": "TCU", "label": "TCU Horned Frogs"},
            {"value": "TENN", "label": "Tennessee Volunteers"},
            {"value": "TEX", "label": "Texas Longhorns"},
            {"value": "TA&M", "label": "Texas A&M Aggies"},
            {"value": "TTU", "label": "Texas Tech Red Raiders"},
            {"value": "UCLA", "label": "UCLA Bruins"},
            {"value": "USC", "label": "USC Trojans"},
            {"value": "UTAH", "label": "Utah Utes"},
            {"value": "VAN", "label": "Vanderbilt Commodores"},
            {"value": "VT", "label": "Virginia Tech Hokies"},
            {"value": "UVA", "label": "Virginia Cavaliers"},
            {"value": "WASH", "label": "Washington Huskies"},
            {"value": "WVU", "label": "West Virginia Mountaineers"},
            {"value": "WIS", "label": "Wisconsin Badgers"},
        ],
    }
])

_URL = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_COLOR = (120, 220, 85)
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
        sport="football", default_label="CFB",
        render=_render_score_animation,
        renderer_name="_render_score_animation_frames",
    )
    if animation:
        return animation
    return render_sport_card(opts, _URL, _CACHE, _COLOR, "NO CFB")
