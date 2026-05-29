import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sports_standings import render as _render

CARD_ID = "mens_college_basketball_standings"
CARD_NAME = "Men's College Basketball Standings"
CARD_DETAIL = "Men's college basketball standings"
CARD_OPTIONS = [
    {
        "key": "group",
        "label": "Conference",
        "type": "select",
        "default": "acc",
        "choices": [
            {"value": "acc", "label": "ACC"},
            {"value": "big 12", "label": "Big 12"},
            {"value": "big east", "label": "Big East"},
            {"value": "big ten", "label": "Big Ten"},
            {"value": "sec", "label": "SEC"},
            {"value": "pac 12", "label": "Pac-12"},
            {"value": "atlantic 10", "label": "Atlantic 10"},
            {"value": "american", "label": "American"},
            {"value": "mountain west", "label": "Mountain West"},
            {"value": "west coast", "label": "West Coast"},
        ],
    },
]


def render(options=None):
    opts = dict(options or {})
    opts["league"] = "mens_college_basketball"
    return _render(opts)
