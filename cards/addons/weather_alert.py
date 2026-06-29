from io import BytesIO
from datetime import datetime, timezone

from card_utils import _settings_value, cached_priority_graphic, draw_sharp_text, fetch_json_request, openweather_alerts_for_zip, priority_graphic_key, render_text_webp

CARD_ID = "weather_alert"
CARD_NAME = "Weather Alert"
CARD_DETAIL = "Skips when clear. Note: also exposes rule fields alert_count, event, and severity."
_SEVERITY_CHOICES = [
    {"value": "minor", "label": "Minor"},
    {"value": "moderate", "label": "Moderate"},
    {"value": "severe", "label": "Severe"},
    {"value": "extreme", "label": "Extreme"},
    {"value": "unknown", "label": "Unknown"},
]
_TARGET_CHOICES = [
    {"value": "device", "label": "Single Device"},
    {"value": "group_wall", "label": "Group Wall"},
]
CARD_OPTIONS = [
    {"key": "zipCode", "label": "ZIP Code", "type": "text", "default": "10001", "maxlength": 5, "inputmode": "numeric"},
    {"key": "severityLevels", "label": "Display Levels", "type": "multiselect", "default": "minor,moderate,severe,extreme,unknown", "size": 5, "choices": _SEVERITY_CHOICES},
    {"key": "severeAlertTarget", "label": "Severe Alert Graphic", "type": "select", "default": "device", "choices": _TARGET_CHOICES},
    {"key": "extremeAlertTarget", "label": "Extreme Alert Graphic", "type": "select", "default": "group_wall", "choices": _TARGET_CHOICES},
]
CARD_RULE_FIELDS = [
    {"id": "alert_count", "label": "Alert Count"},
    {"id": "event", "label": "Event"},
    {"id": "severity", "label": "Severity"},
]
_ALERT_STATE = {}


def _zip_latlon(zip_code):
    loc = fetch_json_request(f"https://api.zippopotam.us/us/{zip_code}", seconds=86400)
    p = loc["places"][0]
    return float(p["latitude"]), float(p["longitude"])


def _default_zip():
    import re

    return re.sub(r"\D", "", _settings_value("defaultZipCode", "") or "")[:5]


def _severity_color(severity):
    sev = (severity or "").lower()
    if sev == "extreme":
        return (255, 60, 90)
    if sev == "severe":
        return (255, 95, 70)
    if sev == "moderate":
        return (255, 190, 70)
    return (255, 230, 90)


def _severity_key(severity):
    sev = str(severity or "").strip().lower()
    return sev if sev in {"minor", "moderate", "severe", "extreme"} else "unknown"


def _selected_levels(value):
    if isinstance(value, (list, tuple, set)):
        raw = [str(item or "").strip().lower() for item in value]
    else:
        raw = [part.strip().lower() for part in str(value or "").replace("|", ",").split(",")]
    levels = {item for item in raw if item}
    valid = {"minor", "moderate", "severe", "extreme", "unknown"}
    levels = {item for item in levels if item in valid}
    return levels or set(valid)


def _short_event(event):
    text = (event or "Weather Alert").upper()
    for word in ("WARNING", "WATCH", "ADVISORY", "STATEMENT"):
        text = text.replace(word, word[:4])
    return " ".join(text.split())[:14]


def _fit(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1]
    return text


def _reason_lines_64(draw, text, font, max_width=46):
    text = (text or "Weather Alert").upper()
    replacements = {
        "THUNDERSTORM": "TSTM",
        "THUNDER": "TSTM",
        "FLOODING": "FLOOD",
        "WARNING": "WARN",
        "WATCH": "WATCH",
        "ADVISORY": "ADVY",
        "STATEMENT": "STMT",
        "WEATHER": "WX",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    words = [word for word in " ".join(text.split()).split() if word not in {"MINOR", "MODERATE", "SEVERE", "EXTREME"}]
    if len(words) <= 2:
        lines = words[:2]
        while len(lines) < 2:
            lines.append("")
        return [_fit(draw, line, font, max_width) for line in lines]
    lines = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if not current or draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
            if len(lines) == 1:
                break
    if current and len(lines) < 2:
        lines.append(current)
    while len(lines) < 2:
        lines.append("")
    return [_fit(draw, line, font, max_width) for line in lines[:2]]


def _alerts_for_zip(zip_code):
    alerts = None
    try:
        alerts = openweather_alerts_for_zip(zip_code)
    except Exception:
        alerts = None
    if alerts is None:
        try:
            lat, lon = _zip_latlon(zip_code)
            data = fetch_json_request(f"https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}", seconds=120)
            alerts = data.get("features") or []
        except Exception:
            alerts = []
    return alerts or []


def _filtered_alerts(alerts, options):
    selected = _selected_levels((options or {}).get("severityLevels"))
    out = []
    for alert in alerts or []:
        props = alert.get("properties") or {}
        if _severity_key(props.get("severity")) in selected:
            out.append(alert)
    return out


def _alert_identity(alert, zip_code):
    props = (alert or {}).get("properties") or {}
    return "|".join(str(value or "") for value in (
        zip_code,
        props.get("id"),
        props.get("@id"),
        props.get("event"),
        props.get("severity"),
        props.get("onset"),
        props.get("effective"),
        props.get("expires"),
        props.get("headline"),
    ))


def _animation_width(options):
    try:
        explicit = int((options or {}).get("_width") or 0)
        if explicit > 0:
            return max(64, min(512, explicit))
    except Exception:
        pass
    target = str((options or {}).get("_target") or "").lower()
    return 128 if "128x32" in target else 64


def _target_for_severity(severity, options):
    key = "extremeAlertTarget" if _severity_key(severity) == "extreme" else "severeAlertTarget"
    return str((options or {}).get(key) or "device").strip().lower()


def _wall_selected(target):
    return target in ("group", "group_wall", "wall") or target.startswith("group:")


def _render_weather_alert_frames(team, kind="severe"):
    from PIL import Image, ImageDraw, ImageFont

    team = team or {}
    try:
        width = int(team.get("_width") or 64)
    except Exception:
        width = 64
    width = max(64, min(512, width))
    severity = _severity_key(team.get("severity") or kind)
    color = _severity_color(severity)
    event = str(team.get("event") or "WEATHER ALERT").upper()
    headline = "EXTREME WX" if severity == "extreme" else "SEVERE WX"
    frames = []
    durations = []
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 9)
    except Exception:
        font = bold = ImageFont.load_default()

    def fit(text, max_width, face):
        text = str(text or "")
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        while text and probe.textbbox((0, 0), text, font=face)[2] > max_width:
            text = text[:-1].rstrip()
        return text

    event = fit(event, width - 4, font)
    for index in range(20):
        flash = index % 2 == 0
        bg = (34, 0, 8) if severity == "extreme" else (28, 8, 0)
        image = Image.new("RGB", (width, 32), bg if flash else (4, 6, 8))
        draw = ImageDraw.Draw(image)
        rail = color if flash else tuple(max(0, c // 3) for c in color)
        draw.rectangle((0, 0, width - 1, 4), fill=rail)
        draw.rectangle((0, 28, width - 1, 31), fill=rail)
        for x in range(0, width, 12):
            offset = (x + index * 4) % max(width, 1)
            draw.line((offset, 4, max(0, offset - 10), 28), fill=tuple(max(0, c // 2) for c in color))
        icon_x = width - 16
        draw.ellipse((icon_x, 9, icon_x + 11, 20), outline=color)
        draw.polygon([(icon_x + 5, 6), (icon_x, 20), (icon_x + 6, 17), (icon_x + 2, 28), (icon_x + 14, 12), (icon_x + 7, 15)], fill=(255, 230, 80))
        title = headline if flash else "WX ALERT"
        title_w = draw.textbbox((0, 0), title, font=bold)[2]
        draw_sharp_text(image, (max(1, (width - title_w) // 2), 5), title, color if flash else (245, 245, 245), bold)
        event_w = draw.textbbox((0, 0), event, font=font)[2]
        draw_sharp_text(image, (max(1, (width - event_w) // 2), 19), event, (245, 245, 245), font)
        frames.append(image)
        durations.append(120 if flash else 85)
    return frames, durations


def _render_weather_alert_animation(team, kind="severe"):
    frames, durations = _render_weather_alert_frames(team, kind)
    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=durations, loop=1, lossless=True, quality=100)
    return out.getvalue()


def _maybe_severity_animation(options, alert, zip_code):
    props = (alert or {}).get("properties") or {}
    severity = _severity_key(props.get("severity"))
    if severity not in {"severe", "extreme"}:
        return None
    device_id = (options or {}).get("_device_id", "local")
    identity = _alert_identity(alert, zip_code)
    key = f"{device_id}:{zip_code}:{severity}:{identity}"
    previous = _ALERT_STATE.get(key)
    _ALERT_STATE[key] = {"seen": datetime.now(timezone.utc)}
    if previous is not None:
        return None

    width = _animation_width(options)
    team = {
        "abbreviation": "WX",
        "event": props.get("event") or "Weather Alert",
        "severity": severity,
        "color": "%02X%02X%02X" % _severity_color(severity),
        "alternateColor": "FFE650",
        "_width": width,
    }
    target = _target_for_severity(severity, options)
    wall = _wall_selected(target)
    cache_key = priority_graphic_key(CARD_ID, team, severity, width)
    return {
        "body": cached_priority_graphic(cache_key, lambda team=team, severity=severity: _render_weather_alert_animation(team, severity)),
        "dwell_secs": 8,
        "_stay": True,
        "_no_replay": True,
        "_priority": True,
        "_group_wall": {
            "type": severity,
            "renderer": "_render_weather_alert_frames",
            "team": dict(team),
            "kind": severity,
            "dwell_secs": 8,
        } if wall else None,
    }


def rule_value(options=None, field=""):
    opts = options or {}
    zip_code = (opts.get("zipCode") or "").strip() or _default_zip()
    if len(zip_code) != 5:
        return ""
    alerts = _filtered_alerts(_alerts_for_zip(zip_code), opts)
    key = str(field or "alert_count").strip()
    if key == "alert_count":
        return len(alerts)
    props = (alerts[0].get("properties") or {}) if alerts else {}
    if key == "event":
        return props.get("event", "")
    if key == "severity":
        return props.get("severity", "")
    return ""


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    zip_code = (opts.get("zipCode") or "").strip() or _default_zip()
    if len(zip_code) != 5:
        return render_text_webp("SET ZIP", (100, 180, 255))

    alerts = _filtered_alerts(_alerts_for_zip(zip_code), opts)

    if not alerts:
        return None

    props = alerts[0].get("properties", {})
    event_text = props.get("event") or "Weather Alert"
    event = _short_event(event_text)
    severity = props.get("severity", "")
    color = _severity_color(severity)

    is_wide = opts.get("_target") == "matrixportal-s3-128x32"
    width = 128 if is_wide else 64
    image = Image.new("RGB", (width, 32), (18, 6, 0))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        small_font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 6)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = small_font = bold = ImageFont.load_default()

    header_bg = tuple(max(0, min(255, c // 3 + 18)) for c in color)
    draw.rectangle((0, 0, width - 1, 7), fill=header_bg)
    title = "WEATHER ALERT" if is_wide else "WX ALERT"
    draw_sharp_text(image, (1, -3), title, color, bold)
    icon_x = width - 16
    draw.ellipse((icon_x, 10, icon_x + 10, 20), outline=color)
    draw.arc((icon_x - 7, 3, icon_x + 17, 27), 205, 335, fill=(80, 110, 130))
    draw.arc((icon_x - 11, -1, icon_x + 21, 31), 205, 335, fill=(45, 70, 90))
    draw.polygon([(icon_x + 5, 7), (icon_x - 1, 20), (icon_x + 6, 17), (icon_x + 1, 28), (icon_x + 13, 13), (icon_x + 6, 15)], fill=(255, 230, 80))
    if is_wide:
        event = _fit(draw, event_text.upper(), font, 105)
        draw_sharp_text(image, (1, 10), event, (245, 245, 245), font)
    else:
        line1, line2 = _reason_lines_64(draw, event_text, small_font, 43)
        draw_sharp_text(image, (1, 8), line1, (245, 245, 245), small_font)
        draw_sharp_text(image, (1, 14), line2, (245, 245, 245), small_font)
    sev = (severity or "Alert").upper()[:8]
    draw_sharp_text(image, (1, 23), sev, color, font)
    if len(alerts) > 1:
        draw_sharp_text(image, (width - 15, 23), f"+{len(alerts)-1}", (210, 220, 225), font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    normal_body = out.getvalue()
    animation = None
    for alert in alerts:
        animation = _maybe_severity_animation(opts, alert, zip_code)
        if animation:
            break
    if animation:
        return animation
    return normal_body
