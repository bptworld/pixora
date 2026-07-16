import sys
import unittest
from datetime import datetime
from pathlib import Path


CARDS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CARDS_DIR))

from addons import market_status


class MarketStatusTests(unittest.TestCase):
    def test_open_during_regular_session(self):
        now = datetime(2026, 7, 15, 10, 0, tzinfo=market_status.EASTERN)
        state, label, _, _ = market_status._status(now)
        self.assertEqual((state, label), ("OPEN", "CLOSES"))

    def test_closed_on_weekend(self):
        now = datetime(2026, 7, 18, 10, 0, tzinfo=market_status.EASTERN)
        state, label, _, _ = market_status._status(now)
        self.assertEqual((state, label), ("CLOSED", "OPENS"))

    def test_good_friday_is_closed(self):
        good_friday = market_status._easter(2026) - market_status.timedelta(days=2)
        now = datetime.combine(good_friday, market_status.time(10, 0), market_status.EASTERN)
        self.assertEqual(market_status._status(now)[0], "CLOSED")

    def test_string_false_hides_countdown(self):
        self.assertFalse(market_status._truthy("false"))

    def test_official_2026_early_closes(self):
        self.assertEqual(market_status._close_time(market_status.date(2026, 11, 27)), market_status.time(13, 0))
        self.assertEqual(market_status._close_time(market_status.date(2026, 12, 24)), market_status.time(13, 0))
        self.assertEqual(market_status._close_time(market_status.date(2026, 7, 2)), market_status.time(16, 0))

    def test_next_year_saturday_new_year_is_observed_on_december_31(self):
        self.assertFalse(market_status._is_trading_day(market_status.date(2021, 12, 31)))


if __name__ == "__main__":
    unittest.main()
