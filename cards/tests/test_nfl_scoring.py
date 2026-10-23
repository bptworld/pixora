"""Real NFL detector: a separately reported extra point must not replay a TD."""
import sys
from pathlib import Path

source = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(source), str(source / 'addons')]
import nfl

nfl.game_moment_alert = lambda *args, **kwargs: None
nfl.warm_priority_graphic = lambda *args: None
nfl.cached_priority_graphic = lambda *args: b'artwork'
nfl._scorer_for_play = lambda *args: {}
summary_reads = []
current_play = {}
def summary(*args):
    summary_reads.append(True)
    return {'scoringPlays': [current_play]}
nfl._fetch_summary = summary

def check(previous, score, play_kind, expected):
    nfl._SCORE_STATE.clear()
    nfl._SCORE_STATE['panel:game:NE'] = {'score': previous, 'animated': previous}
    competitor = {'homeAway': 'home', 'score': str(score),
                  'team': {'abbreviation': 'NE'}}
    event = {'id': 'game', 'competitions': [
        {'status': {'type': {'state': 'in'}}, 'competitors': [competitor]}]}
    nfl.fetch_sport_scoreboard = lambda *args, **kwargs: {'events': [event]}
    nfl.pick_sport_event = lambda *args: event
    current_play.clear()
    current_play.update({'team': {'abbreviation': 'NE'}, 'homeScore': score,
                         'type': {'text': play_kind}})
    summary_reads.clear()
    result = nfl._maybe_score_animation({'favoriteTeam': 'NE', '_device_id': 'panel',
                                       'scoreAnimationTarget': 'group_wall'})
    if expected is None:
        assert result is None, 'Extra point replayed a touchdown'
        assert not summary_reads, 'Conversion unnecessarily queried touchdown details'
    else:
        assert result['_group_wall']['kind'] == expected, result
    assert nfl._SCORE_STATE['panel:game:NE']['animated'] == score

check(0, 6, 'Rushing Touchdown', 'touchdown')
check(6, 7, 'Rushing Touchdown', None)
check(0, 7, 'Rushing Touchdown', 'touchdown')
check(7, 10, 'Field Goal Good', 'field_goal')
check(10, 16, 'Passing Touchdown', 'touchdown')
check(16, 17, 'Passing Touchdown', None)
check(17, 20, 'Field Goal Good', 'field_goal')
print('NFL scoring passed: touchdowns, combined TD/kick, separate extra points, field goals and consumed history.')
