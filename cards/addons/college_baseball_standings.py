import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sports_standings import render as _render

CARD_ID = "college_baseball_standings"
CARD_NAME = "College Baseball Standings"
CARD_DETAIL = "College baseball standings"
CARD_OPTIONS = []


def render(options=None):
    opts = dict(options or {})
    opts["league"] = "college_baseball"
    opts["group"] = "auto"
    return _render(opts)
