import sys
import threading
import unittest
import urllib.error
from io import BytesIO
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


CARDS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CARDS_DIR))

import card_utils


class RuntimeSettingsIsolationTests(unittest.TestCase):
    def tearDown(self):
        card_utils.reset_runtime_settings()

    def test_nested_settings_restore_previous_context(self):
        outer = card_utils.use_runtime_settings({"defaultZipCode": "01826"})
        try:
            self.assertEqual(card_utils._settings_value("defaultZipCode"), "01826")
            inner = card_utils.use_runtime_settings({"defaultZipCode": "10001"})
            try:
                self.assertEqual(card_utils._settings_value("defaultZipCode"), "10001")
            finally:
                card_utils.reset_runtime_settings(inner)
            self.assertEqual(card_utils._settings_value("defaultZipCode"), "01826")
        finally:
            card_utils.reset_runtime_settings(outer)

    def test_simultaneous_devices_cannot_read_each_others_settings(self):
        barrier = threading.Barrier(2)
        results = {}

        def render(device, zip_code, units):
            token = card_utils.use_runtime_settings({"defaultZipCode": zip_code, "temperatureUnits": units})
            try:
                barrier.wait(timeout=2)
                results[device] = (
                    card_utils._settings_value("defaultZipCode"),
                    card_utils._settings_value("temperatureUnits"),
                )
            finally:
                card_utils.reset_runtime_settings(token)

        workers = [
            threading.Thread(target=render, args=("livingroom", "01826", "F")),
            threading.Thread(target=render, args=("kitchen", "10001", "C")),
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=3)

        self.assertEqual(results["livingroom"], ("01826", "F"))
        self.assertEqual(results["kitchen"], ("10001", "C"))

    def test_shared_cache_operations_are_thread_safe_and_bounded(self):
        cache = {}
        errors = []
        start = threading.Barrier(6)

        def exercise_cache(worker_id):
            try:
                start.wait(timeout=2)
                for index in range(300):
                    key = f"{worker_id}:{index}"
                    card_utils._cache_put(cache, key, index, 32)
                    card_utils._cache_get(cache, key)
                    card_utils._prune_expiring_cache(
                        cache,
                        datetime.now(timezone.utc) + timedelta(seconds=1),
                        32,
                    )
            except Exception as exc:
                errors.append(exc)

        workers = [threading.Thread(target=exercise_cache, args=(index,)) for index in range(6)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=5)

        self.assertEqual(errors, [])
        self.assertLessEqual(len(cache), 32)


class SportsFetchTests(unittest.TestCase):
    def test_espn_403_retries_the_espn_web_edge(self):
        urls = []

        class Response(BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                self.close()
                return False

        def fake_urlopen(request, timeout=0):
            urls.append(request.full_url)
            self.assertEqual(request.get_header("Accept"), "application/json")
            self.assertEqual(timeout, 10)
            if len(urls) == 1:
                raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)
            return Response(b'{"events": []}')

        cache = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
        with patch("urllib.request.urlopen", fake_urlopen):
            result = card_utils.fetch_json_url(
                "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
                cache,
            )

        self.assertEqual(result, {"events": []})
        self.assertEqual(urls, [
            "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
            "https://site.web.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
        ])


if __name__ == "__main__":
    unittest.main()
