import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch


CARDS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CARDS_DIR))

from addons import flights_overhead


AIRCRAFT = {
    "hex": "abc123", "flight": "AAL123", "lat": 42.68, "lon": -71.31,
    "alt_baro": 12000, "gs": 300, "track": 90, "t": "A320", "category": "A4",
}


class FlightsOverheadTests(unittest.TestCase):
    def setUp(self):
        flights_overhead._SNAPSHOT_CACHE.clear()
        flights_overhead._SNAPSHOT_PENDING.clear()

    def test_fast_snapshot_does_not_wait_for_route_enrichment(self):
        opts = {"zipCode": "01826", "radiusMiles": 50, "source": "auto"}
        with patch.object(flights_overhead, "_zip_latlon", return_value=(42.6764, -71.3186)), \
             patch.object(flights_overhead, "_fetch_aircraft", return_value=[dict(AIRCRAFT)]), \
             patch.object(flights_overhead, "_route_for_callsign", side_effect=AssertionError("route lookup blocked snapshot")):
            snapshot = flights_overhead._build_snapshot(opts, enrich_routes=False)
        self.assertEqual(len(snapshot["rows"]), 1)
        self.assertEqual(snapshot["rows"][0]["flight"], "AA123")
        self.assertEqual(snapshot["rows"][0]["route"], "")

    def test_cloud_prefetch_returns_flight_instead_of_update_placeholder(self):
        opts = {"zipCode": "01826", "radiusMiles": 50, "source": "auto", "_is_prefetch": True, "_target": "matrixportal-s3"}
        with patch.object(flights_overhead, "_build_snapshot", return_value={"rows": [flights_overhead._flight_row(42.6764, -71.3186, (1.0, dict(AIRCRAFT)), 1, enrich_route=False)], "radius": 50, "updated": time.time()}), \
             patch.object(flights_overhead, "_enrich_snapshot_routes_async"):
            result = flights_overhead.render(opts)
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("body"))
        self.assertEqual(result.get("dwell_secs"), 2)

    def test_string_false_filters_are_honored(self):
        allowed = flights_overhead._allowed_buckets({
            "showAirliners": "false", "showRegionalJets": "false", "showBusinessJets": "false",
            "showHelicopters": "false", "showSmallProps": "true",
        })
        self.assertEqual(allowed, {"prop"})

    def test_error_state_is_not_labeled_as_updating(self):
        with patch.object(flights_overhead, "_render_message", side_effect=lambda text, wide: text):
            result = flights_overhead._render_snapshot({"rows": [], "radius": 50, "error": "provider down"}, {}, False)
        self.assertEqual(result, "Flight data unavailable")

    def test_auto_source_raises_when_every_provider_fails(self):
        failure = RuntimeError("down")
        with patch.object(flights_overhead, "_fetch_adsb_lol", side_effect=failure), \
             patch.object(flights_overhead, "_fetch_adsb_fi", side_effect=failure):
            with self.assertRaisesRegex(RuntimeError, "sources unavailable"):
                flights_overhead._fetch_aircraft(42.67, -71.31, 50, "auto")


if __name__ == "__main__":
    unittest.main()
