import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sports_standings import render as _render

CARD_ID = "nba_standings"
CARD_NAME = "NBA Standings"
CARD_DETAIL = "NBA conference standings"
CARD_OPTIONS = [
    {
        "key": "group",
        "label": "Conference",
        "type": "select",
        "default": "east",
        "choices": [
            {"value": "east", "label": "Eastern Conference"},
            {"value": "west", "label": "Western Conference"},
        ],
    },
]


def render(options=None):
    opts = dict(options or {})
    opts["league"] = "nba"
    return _render(opts)
