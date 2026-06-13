from datetime import datetime

from card_utils import render_text_webp
from _coastal_common import (
    BLUE, GREEN, RED, YELLOW, next_tide, render_labeled_card, station_choices, station_from_options,
    time_label, zip_code,
)

CARD_ID = "fishing_window"
CARD_NAME = "Fishing Window"
CARD_DETAIL = "Tide-based fishing window"
CARD_CATEGORY = "Weather"
CARD_OPTIONS = [
    {"key": "zipCode", "label": "ZIP Code", "type": "text", "default": "02134", "maxlength": 5, "inputmode": "numeric"},
    {
        "key": "stationId",
        "label": "Station",
        "type": "select",
        "default": "",
        "choices": [{"value": "", "label": "Nearest station"}],
        "dynamicChoices": {"dependsOn": ["zipCode"]},
    },
]


def card_option_choices(option_key, options=None):
    return station_choices(zip_code(options or {})) if option_key == "stationId" else []


def _score(tide):
    if not tide:
        return "UNKNOWN", RED
    mins = abs((tide["time"] - datetime.now()).total_seconds()) / 60
    if mins <= 90:
        return "GOOD", GREEN
    if mins <= 180:
        return "FAIR", YELLOW
    return "SLOW", RED


def _until_text(tide):
    if not tide:
        return "--"
    mins = max(0, int((tide["time"] - datetime.now()).total_seconds() // 60))
    if mins < 60:
        return f"{mins}M"
    return f"{mins // 60}H{mins % 60:02d}"


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    try:
        station = station_from_options(opts)
        tide = next_tide(station["id"])
    except Exception:
        return render_text_webp("FISH ERR", (238, 80, 80))
    grade, color = _score(tide)
    tide_text = f"{tide['type']}{time_label(tide['time'])}" if tide else "--"
    rows = [
        ("TD", tide_text, BLUE),
        ("IN", _until_text(tide), YELLOW),
        ("WIN", grade, color),
    ]
    return render_labeled_card("FISH", rows, grade, color, width)
