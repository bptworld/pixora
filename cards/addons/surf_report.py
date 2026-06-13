from card_utils import render_text_webp
from _coastal_common import (
    BLUE, GREEN, RED, YELLOW, fmt_number, marine_data, render_labeled_card, wind_dir, wind_mph,
    nws_hourly, zip_code,
)

CARD_ID = "surf_report"
CARD_NAME = "Surf Report"
CARD_DETAIL = "Wave, swell, and wind"
CARD_CATEGORY = "Weather"
CARD_OPTIONS = [
    {"key": "zipCode", "label": "ZIP Code", "type": "text", "default": "02134", "maxlength": 5, "inputmode": "numeric"},
]


def _rating(wave_ft, wind):
    if wave_ft is None:
        return "NO DATA"
    if 2 <= wave_ft <= 6 and (wind is None or wind <= 15):
        return "GOOD", GREEN
    if wave_ft >= 1 and (wind is None or wind <= 22):
        return "FAIR", YELLOW
    return "POOR", RED


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    try:
        marine = marine_data(zip_code(opts))
        period = (nws_hourly(zip_code(opts)) or [{}])[0]
    except Exception:
        return render_text_webp("SURF ERR", (238, 80, 80))
    wave = None if marine.get("wave_m") is None else marine["wave_m"] * 3.28084
    wind = wind_mph(period)
    grade = _rating(wave, wind)
    color = GREEN if grade == "GOOD" else YELLOW if grade == "FAIR" else RED
    if wave is None:
        return render_labeled_card("SURF", [("SRC", "MARINE", BLUE), ("WND", f"{wind_dir(period)}{fmt_number(wind, '', 0)}", YELLOW)], "NO DATA", RED, width)
    rows = [
        ("WAV", fmt_number(wave, "", 1), BLUE),
        ("PER", fmt_number(marine.get("period"), "S", 0), YELLOW),
        ("WND", f"{wind_dir(period)}{fmt_number(wind, '', 0)}", GREEN if not wind or wind <= 15 else YELLOW),
    ]
    return render_labeled_card("SURF", rows, grade, color, width)
