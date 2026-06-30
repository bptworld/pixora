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
    {"key": "minorAlertTarget", "label": "Minor Alert Graphic", "type": "select", "default": "device", "choices": _TARGET_CHOICES},
    {"key": "moderateAlertTarget", "label": "Moderate Alert Graphic", "type": "select", "default": "device", "choices": _TARGET_CHOICES},
    {"key": "severeAlertTarget", "label": "Severe Alert Graphic", "type": "select", "default": "device", "choices": _TARGET_CHOICES},
    {"key": "extremeAlertTarget", "label": "Extreme Alert Graphic", "type": "select", "default": "group_wall", "choices": _TARGET_CHOICES},
    {"key": "unknownAlertTarget", "label": "Unknown Alert Graphic", "type": "select", "default": "device", "choices": _TARGET_CHOICES},
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
    severity = _severity_key(severity)
    key = f"{severity}AlertTarget"
    fallback = "group_wall" if severity == "extreme" else "device"
    if severity not in {"minor", "moderate", "severe", "extreme", "unknown"}:
        key = "unknownAlertTarget"
    return str((options or {}).get(key) or fallback).strip().lower()


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
    event = str(team.get("event") or "WEATHER ALERT").upper()
    palettes = {
        "minor": {
            "label": "MINOR",
            "accent": (110, 210, 255),
            "header": (10, 42, 62),
            "glow": (18, 85, 116),
            "icon": (145, 230, 255),
        },
        "moderate": {
            "label": "MODERATE",
            "accent": (255, 205, 80),
            "header": (75, 48, 8),
            "glow": (130, 86, 12),
            "icon": (255, 230, 120),
        },
        "severe": {
            "label": "SEVERE",
            "accent": (255, 112, 58),
            "header": (82, 24, 10),
            "glow": (150, 48, 22),
            "icon": (255, 190, 88),
        },
        "extreme": {
            "label": "EXTREME",
            "accent": (255, 54, 94),
            "header": (88, 10, 30),
            "glow": (160, 22, 58),
            "icon": (255, 226, 86),
        },
        "unknown": {
            "label": "WEATHER",
            "accent": (190, 160, 255),
            "header": (48, 32, 78),
            "glow": (86, 62, 128),
            "icon": (215, 198, 255),
        },
    }
    palette = palettes.get(severity, palettes["unknown"])
    accent = palette["accent"]
    header = palette["header"]
    glow = palette["glow"]
    label = palette["label"]
    frames = []
    durations = []
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 9)
        header_font = ImageFont.truetype("assets/fonts/Jersey20-Regular.ttf", 8)
    except Exception:
        font = bold = header_font = ImageFont.load_default()

    def fit(text, max_width, face):
        text = str(text or "")
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        while text and probe.textbbox((0, 0), text, font=face)[2] > max_width:
            text = text[:-1].rstrip()
        return text

    event_display = event if width <= 80 else fit(event, width - 5, font)

    for index in range(18):
        image = Image.new("RGB", (width, 32), (1, 3, 7))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width - 1, 6), fill=header)
        draw.line((0, 7, width - 1, 7), fill=accent)

        pulse = index % 6
        dash_offset = (index * 3) % 14
        for x in range(-14, width + 14, 14):
            x0 = x + dash_offset
            draw.line((x0, 31, x0 + 7, 24), fill=glow)
        draw.rectangle((0, 29, width - 1, 31), fill=tuple(max(0, c // 2) for c in header))

        if width <= 80:
            badge = label[:7]
            draw_sharp_text(image, (1, -1), badge, (255, 255, 255), header_font)
            draw.rectangle((width - 13, 9, width - 4, 18), outline=accent)
            draw.line((width - 9, 11, width - 9, 15), fill=palette["icon"])
            draw.point((width - 9, 17), fill=palette["icon"])
            line1, line2 = _reason_lines_64(draw, event_display, font, width - 18)
            draw_sharp_text(image, (1, 9), line1, (245, 245, 245), font)
            draw_sharp_text(image, (1, 17), line2, (245, 245, 245), font)
            if pulse in (0, 1):
                draw.line((width - 15, 22, width - 3, 22), fill=accent)
        else:
            title = "WEATHER ALERT" if severity == "unknown" else (f"{label} ALERT" if width < 180 else f"{label} WEATHER ALERT")
            title = fit(title, width - 42, header_font)
            draw_sharp_text(image, (2, -1), title, (255, 255, 255), header_font)
            icon_x = width - 24
            draw.polygon([(icon_x + 10, 8), (icon_x, 25), (icon_x + 20, 25)], outline=accent)
            draw.line((icon_x + 10, 13, icon_x + 10, 19), fill=palette["icon"])
            draw.point((icon_x + 10, 22), fill=palette["icon"])
            event_x = 4 if width < 180 else 9
            event_w = width - event_x - 32
            draw_sharp_text(image, (event_x, 12), fit(event_display, event_w, font), (245, 245, 245), font)
            draw.line((event_x, 23, min(width - 31, event_x + 48 + pulse * 4), 23), fill=accent)
            if width >= 180:
                draw_sharp_text(image, (width - 89, 22), "TAKE ACTION", accent, font)
        frames.append(image)
        durations.append(120)
    return frames, durations


def _render_weather_alert_animation(team, kind="severe"):
    frames, durations = _render_weather_alert_frames(team, kind)
    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=durations, loop=1, lossless=True, quality=100)
    return out.getvalue()


def _maybe_severity_animation(options, alert, zip_code):
    props = (alert or {}).get("properties") or {}
    severity = _severity_key(props.get("severity"))
    if severity not in {"minor", "moderate", "severe", "extreme", "unknown"}:
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
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    header_bg = tuple(max(0, c // 4) for c in color)
    draw.rectangle((0, 0, width - 1, 6), fill=header_bg)
    title = "WEATHER ALERT" if is_wide else "WX ALERT"
    draw_sharp_text(image, (1, -3), title, (255, 235, 150), bold)
    icon_x = width - 16
    if is_wide:
        draw.ellipse((icon_x, 10, icon_x + 10, 20), outline=color)
        draw.arc((icon_x - 7, 3, icon_x + 17, 27), 205, 335, fill=(80, 110, 130))
        draw.arc((icon_x - 11, -1, icon_x + 21, 31), 205, 335, fill=(45, 70, 90))
        draw.polygon([(icon_x + 5, 7), (icon_x - 1, 20), (icon_x + 6, 17), (icon_x + 1, 28), (icon_x + 13, 13), (icon_x + 6, 15)], fill=(255, 230, 80))
    else:
        draw.polygon([(55, 9), (50, 20), (56, 17), (52, 28), (62, 14), (57, 16)], fill=(255, 230, 80))
    if is_wide:
        event = _fit(draw, event_text.upper(), font, 105)
        draw_sharp_text(image, (1, 10), event, (245, 245, 245), font)
    else:
        line1, line2 = _reason_lines_64(draw, event_text, font, 43)
        draw_sharp_text(image, (1, 5), line1, (245, 245, 245), font)
        draw_sharp_text(image, (1, 13), line2, (245, 245, 245), font)
    sev = (severity or "Alert").upper()[:8]
    draw_sharp_text(image, (1, 21), sev, color, font)
    if len(alerts) > 1:
        draw_sharp_text(image, (width - 15, 21), f"+{len(alerts)-1}", (210, 220, 225), font)

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
