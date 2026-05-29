from event_sport_utils import render_event_sport_card

CARD_ID = "pga"
CARD_NAME = "PGA Golf"
CARD_DETAIL = "ESPN PGA leaderboard"
CARD_OPTIONS = []


def render(options=None):
    return render_event_sport_card("golf", "pga", "PGA", (90, 220, 120), "NO PGA", icon="golf", scroll_leaders=True, hide_score=True, options=options, leaderboard_only=True)
