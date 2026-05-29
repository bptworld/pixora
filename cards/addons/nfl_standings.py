import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sports_standings import render as _render

CARD_ID = "nfl_standings"
CARD_NAME = "NFL Standings"
CARD_DETAIL = "NFL conference standings"
CARD_OPTIONS = [
    {
        "key": "group",
        "label": "Conference",
        "type": "select",
        "default": "afc",
        "choices": [
            {"value": "afc", "label": "AFC"},
            {"value": "nfc", "label": "NFC"},
        ],
    },
]


def render(options=None):
    opts = dict(options or {})
    opts["league"] = "nfl"
    return _render(opts)
