from card_utils import render_text_webp
from _coastal_common import (
    GREEN, RED, YELLOW, fmt_number, marine_data, next_tide, nws_alerts, nws_hourly,
    BLUE, render_labeled_card, safe_text, station_choices, station_from_options, time_label, wind_dir,
    wind_mph, zip_code,
)

CARD_ID = "boating_conditions"
CARD_NAME = "Boating Conditions"
CARD_DETAIL = "Wind, seas, and tide for boating"
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


def _grade(wind, seas, alerts):
    alert_text = " ".join(safe_text((a.get("properties") or {}).get("event")).upper() for a in alerts)
    if "SMALL CRAFT" in alert_text or "GALE" in alert_text or (wind and wind >= 25) or (seas and seas >= 6):
        return "NO GO", RED
    if (wind and wind >= 15) or (seas and seas >= 3):
        return "CAUTION", YELLOW
    return "GO", GREEN


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    try:
        period = (nws_hourly(zip_code(opts)) or [{}])[0]
        marine = marine_data(zip_code(opts))
        station = station_from_options(opts)
        tide = next_tide(station["id"])
        seas = None if marine.get("wave_m") is None else marine["wave_m"] * 3.28084
        wind = wind_mph(period)
        grade, color = _grade(wind, seas, nws_alerts(zip_code(opts)))
    except Exception:
        return render_text_webp("BOAT ERR", (238, 80, 80))
    tide_text = f"{tide['type']}{time_label(tide['time'])}" if tide else "--"
    rows = [
        ("WND", f"{wind_dir(period)}{fmt_number(wind, '', 0)}", BLUE),
        ("SEA", fmt_number(seas, "", 1), YELLOW),
        ("TD", tide_text, GREEN),
    ]
    return render_labeled_card("BOAT", rows, grade, color, width)
