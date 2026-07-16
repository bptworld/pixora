import sys
import unittest
from pathlib import Path
from unittest.mock import ANY, patch


CARDS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CARDS_DIR))

from addons import weather_forecast


class WeatherForecastIconTests(unittest.TestCase):
    def test_nws_icon_url_falls_back_to_forecast_text(self):
        period = {
            "icon": "https://api.weather.gov/icons/land/day/sct?size=medium",
            "shortForecast": "Partly Sunny",
        }
        self.assertEqual(weather_forecast._weather_icon_name(period), "partly")

    def test_openweather_symbolic_icon_is_preserved(self):
        period = {
            "icon": "rain",
            "openWeatherIcon": "10d",
            "shortForecast": "Rain",
        }
        self.assertEqual(weather_forecast._weather_icon_name(period), "rain")

    def test_day_icon_uses_local_pixel_renderer(self):
        period = {
            "icon": "cloud",
            "openWeatherIcon": "04d",
            "shortForecast": "Cloudy",
        }
        with patch.object(weather_forecast, "draw_mini_weather_icon") as draw_icon:
            weather_forecast._draw_icon(object(), period, 8, 10)
        draw_icon.assert_called_once_with(ANY, "cloud", 8, 7)


if __name__ == "__main__":
    unittest.main()
