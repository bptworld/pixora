from card_utils import render_text_webp
from _coastal_common import (
    BLUE, GREEN, ORANGE, RED, YELLOW, coops_latest, fmt_number, marine_data,
    render_labeled_card, station_choices, station_from_options, zip_code,
)

CARD_ID = "beach_conditions"
CARD_NAME = "Beach Conditions"
CARD_DETAIL = "Water, waves, and beach wind"
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


def _grade(wave_ft, wind):
    if (wave_ft is not None and wave_ft >= 6) or (wind is not None and wind >= 25):
        return "ROUGH", RED
    if (wave_ft is not None and wave_ft >= 3) or (wind is not None and wind >= 15):
        return "FAIR", YELLOW
    return "GOOD", GREEN


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    try:
        station = station_from_options(opts)
        water = coops_latest(station["id"], "water_temperature")
        wind = coops_latest(station["id"], "wind")
        marine = marine_data(zip_code(opts))
    except Exception:
        return render_text_webp("BEACH ERR", (238, 80, 80))
    wave_ft = None if marine.get("wave_m") is None else marine["wave_m"] * 3.28084
    grade, color = _grade(wave_ft, wind)
    water_text = fmt_number(water, "F", 0) if water is not None else "--"
    wave_text = fmt_number(wave_ft, "FT", 1)
    rows = [
        ("TMP", water_text, BLUE),
        ("WAV", wave_text, YELLOW),
        ("WND", fmt_number(wind, "", 0), GREEN if not wind or wind < 15 else ORANGE),
    ]
    return render_labeled_card("BEACH", rows, grade, color, width)
