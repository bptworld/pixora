from datetime import datetime, timezone

from card_utils import render_sport_card
from _sports_breaking import maybe_score_alert, render_score_alert_frames, with_score_animation_option

CARD_ID = "nba"
CARD_NAME = "NBA Scores"
CARD_DETAIL = "Live ESPN scoreboard"
CARD_OPTIONS = with_score_animation_option([
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "BOS",
        "choices": [
            {"value": "ATL", "label": "Atlanta Hawks"},
            {"value": "BOS", "label": "Boston Celtics"},
            {"value": "BKN", "label": "Brooklyn Nets"},
            {"value": "CHA", "label": "Charlotte Hornets"},
            {"value": "CHI", "label": "Chicago Bulls"},
            {"value": "CLE", "label": "Cleveland Cavaliers"},
            {"value": "DAL", "label": "Dallas Mavericks"},
            {"value": "DEN", "label": "Denver Nuggets"},
            {"value": "DET", "label": "Detroit Pistons"},
            {"value": "GS", "label": "Golden State Warriors"},
            {"value": "HOU", "label": "Houston Rockets"},
            {"value": "IND", "label": "Indiana Pacers"},
            {"value": "LAC", "label": "LA Clippers"},
            {"value": "LAL", "label": "Los Angeles Lakers"},
            {"value": "MEM", "label": "Memphis Grizzlies"},
            {"value": "MIA", "label": "Miami Heat"},
            {"value": "MIL", "label": "Milwaukee Bucks"},
            {"value": "MIN", "label": "Minnesota Timberwolves"},
            {"value": "NO", "label": "New Orleans Pelicans"},
            {"value": "NY", "label": "New York Knicks"},
            {"value": "OKC", "label": "Oklahoma City Thunder"},
            {"value": "ORL", "label": "Orlando Magic"},
            {"value": "PHI", "label": "Philadelphia 76ers"},
            {"value": "PHX", "label": "Phoenix Suns"},
            {"value": "POR", "label": "Portland Trail Blazers"},
            {"value": "SAC", "label": "Sacramento Kings"},
            {"value": "SA", "label": "San Antonio Spurs"},
            {"value": "TOR", "label": "Toronto Raptors"},
            {"value": "UTAH", "label": "Utah Jazz"},
            {"value": "WSH", "label": "Washington Wizards"},
        ],
    }
])

_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_COLOR = (245, 150, 65)
_SCORE_STATE = {}
_render_score_alert_frames = render_score_alert_frames


def render(options=None):
    opts = options or {}
    animation = maybe_score_alert(opts, CARD_ID, _URL, _CACHE, _SCORE_STATE, sport="basketball", default_label="NBA")
    if animation:
        if animation.get("_group_wall"):
            normal_card = render_sport_card(opts, _URL, _CACHE, _COLOR, "NO NBA")
            if normal_card:
                animation["body"] = normal_card
                animation["dwell_secs"] = opts.get("_dwell", 10)
                animation["_no_replay"] = False
        return animation
    return render_sport_card(opts, _URL, _CACHE, _COLOR, "NO NBA")
