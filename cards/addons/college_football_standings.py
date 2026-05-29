import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sports_standings import render as _render

CARD_ID = "college_football_standings"
CARD_NAME = "College Football Standings"
CARD_DETAIL = "College football conference standings"
CARD_OPTIONS = [
    {
        "key": "group",
        "label": "Conference",
        "type": "select",
        "default": "big ten",
        "choices": [
            {"value": "acc", "label": "ACC"},
            {"value": "big 12", "label": "Big 12"},
            {"value": "big ten", "label": "Big Ten"},
            {"value": "sec", "label": "SEC"},
            {"value": "american", "label": "American"},
            {"value": "mountain west", "label": "Mountain West"},
            {"value": "mid american", "label": "MAC"},
            {"value": "conference usa", "label": "Conference USA"},
            {"value": "sun belt", "label": "Sun Belt"},
        ],
    },
]


def render(options=None):
    opts = dict(options or {})
    opts["league"] = "college_football"
    return _render(opts)
