import sys
import unittest
from pathlib import Path

from PIL import Image


CARDS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CARDS_DIR))

from addons import weather_forecast


class WeatherForecastIconTests(unittest.TestCase):
    def test_nws_icon_url_uses_sky_condition_code(self):
        period = {
            "icon": "https://api.weather.gov/icons/land/day/sct?size=medium",
            "shortForecast": "Partly Sunny",
        }
        self.assertEqual(weather_forecast._weather_icon_name(period), "partly")

    def test_nws_night_icon_uses_night_variant(self):
        period = {
            "icon": "https://api.weather.gov/icons/land/night/sct?size=medium",
            "shortForecast": "Partly Cloudy",
        }
        self.assertEqual(weather_forecast._weather_icon_name(period), "moon_cloud")

    def test_openweather_symbolic_icon_is_preserved(self):
        period = {
            "icon": "rain",
            "openWeatherIcon": "10d",
            "shortForecast": "Rain",
        }
        self.assertEqual(weather_forecast._weather_icon_name(period), "rain")

    def test_nws_icon_url_uses_weather_code_over_unrelated_text(self):
        period = {
            "icon": "https://api.weather.gov/icons/land/day/rain_showers,20?size=medium",
            "shortForecast": "Smoke",
        }
        self.assertEqual(weather_forecast._weather_icon_name(period), "rain")

    def test_nws_compound_icon_prefers_significant_condition(self):
        period = {
            "icon": "https://api.weather.gov/icons/land/day/bkn/tsra_hi,40?size=medium",
            "shortForecast": "Partly Sunny then Slight Chance Thunderstorms",
        }
        self.assertEqual(weather_forecast._weather_icon_name(period), "thunder")

    def test_day_icon_is_compact(self):
        image = Image.new("RGB", (16, 16), (0, 5, 15))
        weather_forecast._draw_icon(image, {"icon": "cloud"}, 8, 10)
        changed = [(x, y) for y in range(16) for x in range(16) if image.getpixel((x, y)) != (0, 5, 15)]
        self.assertTrue(changed)
        self.assertLessEqual(max(x for x, _ in changed) - min(x for x, _ in changed) + 1, 11)
        self.assertLessEqual(max(y for _, y in changed) - min(y for _, y in changed) + 1, 9)


if __name__ == "__main__":
    unittest.main()
