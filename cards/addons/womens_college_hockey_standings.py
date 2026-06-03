import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sports_standings import render as _render

CARD_ID = "womens_college_hockey_standings"
CARD_NAME = "Women's College Hockey Standings"
CARD_DETAIL = "Women's college hockey standings"
CARD_OPTIONS = [
    {
        "key": "group",
        "label": "Conference",
        "type": "select",
        "default": "auto",
        "choices": [
            {"value": "auto", "label": "Default"},
            {"value": "hockey east", "label": "Hockey East"},
            {"value": "ecac", "label": "ECAC"},
            {"value": "wcha", "label": "WCHA"},
            {"value": "atlantic hockey", "label": "Atlantic Hockey"},
            {"value": "independent", "label": "Independent"},
        ],
    },
]


def render(options=None):
    opts = dict(options or {})
    opts["league"] = "womens_college_hockey"
    return _render(opts)
