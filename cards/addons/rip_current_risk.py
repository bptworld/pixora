from card_utils import render_text_webp
from _coastal_common import BLUE, GREEN, RED, YELLOW, nws_alerts, render_labeled_card, safe_text, zip_code

CARD_ID = "rip_current_risk"
CARD_NAME = "Rip Current Risk"
CARD_DETAIL = "Active rip current alerts"
CARD_CATEGORY = "Weather"
CARD_OPTIONS = [
    {"key": "zipCode", "label": "ZIP Code", "type": "text", "default": "02134", "maxlength": 5, "inputmode": "numeric"},
]


def _risk(alerts):
    for feature in alerts:
        props = feature.get("properties") or {}
        event = safe_text(props.get("event")).upper()
        text = f"{event} {safe_text(props.get('headline'))} {safe_text(props.get('description'))}".upper()
        if "RIP CURRENT" in text:
            if "HIGH" in text:
                return "HIGH", RED, "RIP CURRENT"
            if "MODERATE" in text:
                return "MOD", YELLOW, "RIP CURRENT"
            return "ACTIVE", RED, "RIP CURRENT"
        if "BEACH HAZARDS" in event:
            return "HAZARD", YELLOW, "BEACH ALERT"
    return "LOW", GREEN, "NO ALERT"


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    try:
        risk, color, detail = _risk(nws_alerts(zip_code(opts)))
    except Exception:
        return render_text_webp("RIP ERR", (238, 80, 80))
    rows = [
        ("RIP", risk, color),
        ("NWS", detail, BLUE if risk == "LOW" else color),
    ]
    return render_labeled_card("RIP RISK", rows, risk, color, width)
