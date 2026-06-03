from event_sport_utils import render_event_sport_card

CARD_ID = "f1"
CARD_NAME = "F1 Racing"
CARD_DETAIL = "ESPN Formula 1 status"
CARD_OPTIONS = []


def render(options=None):
    return render_event_sport_card("racing", "f1", "F1", (245, 80, 90), "NO F1", icon="race", scroll_leaders=True, hide_score=True, options=options, leaderboard_only=True)
