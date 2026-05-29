import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sports_standings import render as _render

CARD_ID = "soccer_standings"
CARD_NAME = "Soccer Standings"
CARD_DETAIL = "Soccer league table"
CARD_OPTIONS = [
    {
        "key": "soccerLeague",
        "label": "League",
        "type": "select",
        "default": "eng.1",
        "choices": [
            {"value": "eng.1", "label": "Premier League"},
            {"value": "usa.1", "label": "MLS"},
            {"value": "esp.1", "label": "La Liga"},
            {"value": "ita.1", "label": "Serie A"},
            {"value": "ger.1", "label": "Bundesliga"},
            {"value": "fra.1", "label": "Ligue 1"},
            {"value": "usa.nwsl", "label": "NWSL"},
        ],
    },
    {
        "key": "group",
        "label": "Group",
        "type": "select",
        "default": "auto",
        "choices": [
            {"value": "auto", "label": "Default"},
            {"value": "east", "label": "East"},
            {"value": "west", "label": "West"},
        ],
    },
]


def render(options=None):
    opts = dict(options or {})
    opts["league"] = "soccer"
    return _render(opts)
