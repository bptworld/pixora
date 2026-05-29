import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sports_standings import render as _render

CARD_ID = "mens_college_hockey_standings"
CARD_NAME = "College Hockey Standings"
CARD_DETAIL = "Men's college hockey standings"
CARD_OPTIONS = [
    {
        "key": "group",
        "label": "Conference",
        "type": "select",
        "default": "big ten",
        "choices": [
            {"value": "big ten", "label": "Big Ten"},
            {"value": "hockey east", "label": "Hockey East"},
            {"value": "nchc", "label": "NCHC"},
            {"value": "ecac", "label": "ECAC"},
            {"value": "ccha", "label": "CCHA"},
            {"value": "atlantic hockey", "label": "Atlantic Hockey"},
            {"value": "independent", "label": "Independent"},
        ],
    },
]


def render(options=None):
    opts = dict(options or {})
    opts["league"] = "mens_college_hockey"
    return _render(opts)
