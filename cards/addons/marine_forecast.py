from card_utils import render_text_webp
from _coastal_common import (
    BLUE, GREEN, RED, YELLOW, fmt_number, marine_data, nws_alerts, nws_hourly,
    render_labeled_card, safe_text, wind_dir, wind_mph, zip_code,
)

CARD_ID = "marine_forecast"
CARD_NAME = "Marine Forecast"
CARD_DETAIL = "Coastal wind and seas"
CARD_CATEGORY = "Weather"
CARD_OPTIONS = [
    {"key": "zipCode", "label": "ZIP Code", "type": "text", "default": "02134", "maxlength": 5, "inputmode": "numeric"},
]


def _alert_label(alerts):
    for feature in alerts:
        event = safe_text((feature.get("properties") or {}).get("event")).upper()
        if "SMALL CRAFT" in event:
            return "SCA", RED
        if "GALE" in event or "STORM" in event:
            return "WARN", RED
        if "MARINE" in event:
            return "ADV", YELLOW
    return "OK", GREEN


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    try:
        period = (nws_hourly(zip_code(opts)) or [{}])[0]
        marine = marine_data(zip_code(opts))
        status, color = _alert_label(nws_alerts(zip_code(opts)))
    except Exception:
        return render_text_webp("MARINE ERR", (238, 80, 80))
    wind = wind_mph(period)
    seas = None if marine.get("wave_m") is None else marine["wave_m"] * 3.28084
    rows = [
        ("WND", f"{wind_dir(period)}{fmt_number(wind, '', 0)}", BLUE),
        ("SEA", fmt_number(seas, "", 1), YELLOW),
        ("ADV", status, color),
    ]
    return render_labeled_card("MARINE", rows, status, color, width)
