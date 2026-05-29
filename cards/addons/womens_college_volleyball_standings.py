import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sports_standings import render as _render

CARD_ID = "womens_college_volleyball_standings"
CARD_NAME = "Women's College Volleyball Standings"
CARD_DETAIL = "Women's college volleyball standings"
CARD_OPTIONS = [
    {
        "key": "group",
        "label": "Group",
        "type": "select",
        "default": "auto",
        "choices": [
            {"value": "auto", "label": "Default"},
            {"value": "division i", "label": "Division I"},
            {"value": "division ii", "label": "Division II"},
        ],
    },
]


def render(options=None):
    opts = dict(options or {})
    opts["league"] = "womens_college_volleyball"
    return _render(opts)
