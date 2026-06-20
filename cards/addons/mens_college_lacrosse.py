from datetime import datetime, timezone

from card_utils import render_sport_card
from _sports_breaking import maybe_score_alert, render_score_alert_frames, with_score_animation_option

CARD_ID = "mens_college_lacrosse"
CARD_NAME = "Men's College Lacrosse"
CARD_DETAIL = "Live ESPN men's college lacrosse scoreboard"
CARD_OPTIONS = with_score_animation_option([
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "NOTRE DAME",
        "choices": [
            {"value": "ARMY", "label": "Army Black Knights"},
            {"value": "BU", "label": "Boston University Terriers"},
            {"value": "CORNELL", "label": "Cornell Big Red"},
            {"value": "DUKE", "label": "Duke Blue Devils"},
            {"value": "GEORGETOWN", "label": "Georgetown Hoyas"},
            {"value": "HARV", "label": "Harvard Crimson"},
            {"value": "JOHNS HOPKINS", "label": "Johns Hopkins Blue Jays"},
            {"value": "MARYLAND", "label": "Maryland Terrapins"},
            {"value": "MICHIGAN", "label": "Michigan Wolverines"},
            {"value": "NORTH CAROLINA", "label": "North Carolina Tar Heels"},
            {"value": "NOTRE DAME", "label": "Notre Dame Fighting Irish"},
            {"value": "PENN STATE", "label": "Penn State Nittany Lions"},
            {"value": "PRINCETON", "label": "Princeton Tigers"},
            {"value": "RUTGERS", "label": "Rutgers Scarlet Knights"},
            {"value": "SYRACUSE", "label": "Syracuse Orange"},
            {"value": "VIRGINIA", "label": "Virginia Cavaliers"},
            {"value": "YALE", "label": "Yale Bulldogs"},
        ],
    }
])

_URL = "https://site.api.espn.com/apis/site/v2/sports/lacrosse/mens-college-lacrosse/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_COLOR = (105, 230, 180)
_SCORE_STATE = {}
_render_score_alert_frames = render_score_alert_frames


def render(options=None):
    opts = options or {}
    animation = maybe_score_alert(opts, CARD_ID, _URL, _CACHE, _SCORE_STATE, sport="lacrosse", default_label="MLAX")
    if animation:
        return animation
    return render_sport_card(opts, _URL, _CACHE, _COLOR, "NO MLAX")
