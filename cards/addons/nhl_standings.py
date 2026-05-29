import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sports_standings import render as _render

CARD_ID = "nhl_standings"
CARD_NAME = "NHL Standings"
CARD_DETAIL = "NHL conference standings"
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
    opts["league"] = "nhl"
    return _render(opts)
