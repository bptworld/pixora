from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import urllib.parse

from card_utils import (
    cached_priority_graphic,
    draw_pixora_bold_number,
    draw_sharp_text,
    fetch_json_with_headers,
    format_time,
    pixora_bold_number_size,
    warm_priority_graphic,
)

CARD_ID = "launch_countdown"
CARD_NAME = "NASA / SpaceX Launch"
CARD_DETAIL = "Next rocket launch countdown"
CARD_OPTIONS = [
    {
        "key": "provider",
        "label": "Provider",
        "type": "select",
        "default": "all",
        "choices": [
            {"value": "all", "label": "All Launches"},
            {"value": "spacex", "label": "SpaceX"},
            {"value": "nasa", "label": "NASA"},
        ],
    },
    {
        "key": "view",
        "label": "View",
        "type": "select",
        "default": "countdown",
        "choices": [
            {"value": "countdown", "label": "Countdown"},
            {"value": "mission", "label": "Mission"},
            {"value": "location", "label": "Location"},
        ],
    },
    {"key": "goOnly", "label": "Only show Go launches", "type": "checkbox", "default": False},
    {
        "key": "launchAnimationTarget",
        "label": "Launch Animation",
        "type": "select",
        "default": "device",
        "choices": [
            {"value": "device", "label": "Single Device"},
            {"value": "group_wall", "label": "Group Wall"},
        ],
    },
]

_URL = "https://ll.thespacedevs.com/2.0.0/launch/upcoming/"
_FALLBACK_URL = "https://fdo.rocketlaunch.live/json/launches/next/5"
_DATA_DIR = Path(os.environ.get("PIXORA_DATA_DIR") or Path(__file__).resolve().parents[2] / "data")
_CACHE_PATH = _DATA_DIR / "launch_countdown_cache.json"
_CACHE_SECONDS = 6 * 60 * 60
_LAUNCH_WALL_STATE = {}
_LAUNCH_ANIMATION_STATE = {}


def _font(name, size):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(name, size)
    except Exception:
        return ImageFont.load_default()


def _width(opts):
    explicit = (opts or {}).get("_width")
    if explicit:
        try:
            return max(32, min(512, int(explicit)))
        except Exception:
            pass
    return 128 if (opts or {}).get("_target") == "matrixportal-s3-128x32" else 64


def _text_card(opts, text, color=(175, 220, 255)):
    from PIL import Image, ImageDraw

    width = _width(opts)
    image = Image.new("RGB", (width, 32), (0, 5, 15))
    draw = ImageDraw.Draw(image)
    font = _font("assets/fonts/Silkscreen-Regular.ttf", 8)
    bbox = draw.textbbox((0, 0), text, font=font)
    draw_sharp_text(
        image,
        ((width - (bbox[2] - bbox[0])) // 2, (32 - (bbox[3] - bbox[1])) // 2),
        text,
        color,
        font,
    )
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _launches():
    cached = _read_launch_cache()
    if cached:
        return cached

    params = urllib.parse.urlencode({"limit": 50, "format": "json"})
    try:
        data = fetch_json_with_headers(
            _URL + "?" + params,
            {"Accept": "application/json"},
            seconds=_CACHE_SECONDS,
            cache_key="launch_countdown:upcoming:50",
        )
        launches = data.get("results") or []
        _write_launch_cache(launches)
    except Exception:
        launches = _read_launch_cache(allow_stale=True)
        if not launches:
            launches = _rocketlaunch_live_launches()
            _write_launch_cache(launches)
    return launches


def _read_launch_cache(allow_stale=False):
    try:
        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "results" in data:
            fetched_at = _parse_time(data.get("fetched_at"))
            if allow_stale or (fetched_at and (datetime.now(timezone.utc) - fetched_at).total_seconds() < _CACHE_SECONDS):
                return data.get("results") or []
        if isinstance(data, dict) and data.get("results"):
            return data.get("results") if allow_stale else []
    except Exception:
        pass
    return []


def _write_launch_cache(launches):
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(
            json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "results": launches}),
            encoding="utf-8",
        )
    except Exception:
        pass


def _rocketlaunch_live_launches():
    data = fetch_json_with_headers(
        _FALLBACK_URL,
        {"Accept": "application/json"},
        seconds=_CACHE_SECONDS,
        cache_key="launch_countdown:rocketlaunchlive:next5",
    )
    launches = []
    for item in data.get("result") or []:
        provider = item.get("provider") or {}
        vehicle = item.get("vehicle") or {}
        missions = item.get("missions") or []
        mission = missions[0] if missions else {}
        pad = item.get("pad") or {}
        loc = pad.get("location") or {}
        loc_name = loc.get("name") or loc.get("statename") or loc.get("country") or ""
        launches.append({
            "name": item.get("name") or mission.get("name") or "Launch",
            "net": item.get("t0") or item.get("win_open"),
            "status": {"name": "Go" if item.get("t0") else "TBD"},
            "launch_service_provider": {"name": provider.get("name") or "Launch"},
            "rocket": {"configuration": {"full_name": vehicle.get("name") or "Rocket", "name": vehicle.get("name") or "Rocket"}},
            "mission": {"name": mission.get("name") or item.get("name") or "Mission", "description": mission.get("description") or item.get("mission_description") or ""},
            "program": [],
            "pad": {"name": pad.get("name") or "", "location": {"name": loc_name}},
        })
    return launches


def _search_text(launch):
    parts = [
        launch.get("name"),
        (launch.get("launch_service_provider") or {}).get("name"),
        ((launch.get("rocket") or {}).get("configuration") or {}).get("full_name"),
        ((launch.get("rocket") or {}).get("configuration") or {}).get("name"),
        (launch.get("mission") or {}).get("name"),
        (launch.get("mission") or {}).get("description"),
    ]
    for program in launch.get("program") or []:
        parts.append(program.get("name"))
        for agency in program.get("agencies") or []:
            parts.append(agency.get("name"))
            parts.append(agency.get("abbrev"))
    return " ".join(str(part or "") for part in parts).lower()


def _matches_provider(launch, provider):
    provider = (provider or "all").lower()
    if provider == "all":
        return True
    text = _search_text(launch)
    if provider == "spacex":
        return "spacex" in text or "space exploration technologies" in text
    if provider == "nasa":
        return "nasa" in text or "national aeronautics and space administration" in text
    return True


def _is_go(launch):
    status = (launch.get("status") or {}).get("name") or ""
    return status.lower() == "go"


def _pick_launch(opts):
    provider = str(opts.get("provider") or "all").lower()
    go_only = opts.get("goOnly") is True or str(opts.get("goOnly")).lower() == "true"
    for launch in _launches():
        if go_only and not _is_go(launch):
            continue
        if _matches_provider(launch, provider):
            return launch
    return None


def _parse_time(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _time_parts(launch):
    net = _parse_time(launch.get("net") or launch.get("window_start"))
    if not net:
        return "TBD", ""
    date_label = f"{net:%b} {net.day}"
    total = int((net - datetime.now(timezone.utc)).total_seconds())
    if total < 0:
        total = 0
    days = total // 86400
    hours = (total % 86400) // 3600
    minutes = (total % 3600) // 60
    if days >= 100:
        return f"{days}D", date_label
    if days >= 1:
        return f"{days}D {hours}H", date_label
    if hours >= 1:
        return f"{hours}H {minutes}M", format_time(net.astimezone(), include_ampm=True)
    return f"{minutes}M", format_time(net.astimezone(), include_ampm=True)


def _seconds_until(launch):
    net = _parse_time(launch.get("net") or launch.get("window_start"))
    if not net:
        return None
    return int((net - datetime.now(timezone.utc)).total_seconds())


def _launch_key(launch):
    return "|".join(str(launch.get(key) or "") for key in ("id", "slug", "name", "net"))


def _should_queue_launch_wall(launch):
    key = _launch_key(launch)
    now = datetime.now(timezone.utc)
    for old_key, seen_at in list(_LAUNCH_WALL_STATE.items()):
        if (now - seen_at).total_seconds() > 300:
            _LAUNCH_WALL_STATE.pop(old_key, None)
    if _LAUNCH_WALL_STATE.get(key):
        return False
    _LAUNCH_WALL_STATE[key] = now
    return True


def _should_queue_launch_animation(launch, phase):
    key = f"{_launch_key(launch)}|{phase}"
    now = datetime.now(timezone.utc)
    for old_key, seen_at in list(_LAUNCH_ANIMATION_STATE.items()):
        if (now - seen_at).total_seconds() > 300:
            _LAUNCH_ANIMATION_STATE.pop(old_key, None)
    if _LAUNCH_ANIMATION_STATE.get(key):
        return False
    _LAUNCH_ANIMATION_STATE[key] = now
    return True


def _clean_date(text):
    return " ".join(str(text or "").replace(" 0", " ").split())


def _fit(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1]
    return text


def _countdown_text_size(draw, text, digit_scale, digit_spacing, unit_font, gap=1):
    width = 0
    height = 7 * digit_scale
    for ch in str(text or ""):
        if ch.isdigit():
            w, h = pixora_bold_number_size(ch, scale=digit_scale, spacing=digit_spacing)
        elif ch == " ":
            w, h = 3, height
        else:
            bbox = draw.textbbox((0, 0), ch, font=unit_font)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        width += w + gap
        height = max(height, h)
    return max(0, width - gap), height


def _draw_countdown_text(image, xy, text, color, digit_scale, digit_spacing, unit_font, gap=1):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    x, y = xy
    digit_h = 7 * digit_scale
    for ch in str(text or ""):
        if ch.isdigit():
            draw_pixora_bold_number(draw, (x, y), ch, color, scale=digit_scale, spacing=digit_spacing)
            x += pixora_bold_number_size(ch, scale=digit_scale, spacing=digit_spacing)[0] + gap
        elif ch == " ":
            x += 3 + gap
        else:
            bbox = draw.textbbox((0, 0), ch, font=unit_font)
            unit_h = bbox[3] - bbox[1]
            unit_y = y + (digit_h - unit_h) // 2 - bbox[1]
            draw_sharp_text(image, (x - bbox[0], unit_y), ch, color, unit_font)
            x += (bbox[2] - bbox[0]) + gap


def _provider_label(launch):
    provider = (launch.get("launch_service_provider") or {}).get("name") or "LAUNCH"
    if "SpaceX" in provider:
        return "SPACEX"
    if "NASA" in _search_text(launch).upper():
        return "NASA"
    return provider.upper()[:8]


def _rocket_name(launch):
    rocket = ((launch.get("rocket") or {}).get("configuration") or {})
    return rocket.get("full_name") or rocket.get("name") or "ROCKET"


def _mission_name(launch):
    mission = (launch.get("mission") or {}).get("name")
    if mission:
        return mission
    name = launch.get("name") or "Mission"
    if "|" in name:
        return name.split("|", 1)[1].strip()
    return name


def _location(launch):
    pad = launch.get("pad") or {}
    loc = pad.get("location") or {}
    name = loc.get("name") or pad.get("name") or "Launch Site"
    if "," in name:
        return name.split(",", 1)[0]
    return name


def _draw_stars(draw, width):
    for x, y in ((7, 4), (22, 13), (39, 6), (55, 24), (77, 12), (101, 5), (118, 22)):
        if x < width - 1:
            draw.point((x, y), fill=(110, 150, 190))


def _draw_rocket(draw, x, y, color, flame=True):
    draw.polygon([(x + 4, y), (x + 8, y + 6), (x + 8, y + 18), (x, y + 18), (x, y + 6)], fill=(205, 220, 230))
    draw.polygon([(x + 4, y), (x + 1, y + 6), (x + 7, y + 6)], fill=color)
    draw.rectangle((x + 2, y + 8, x + 6, y + 12), fill=(35, 80, 120))
    draw.polygon([(x, y + 15), (x - 4, y + 21), (x + 1, y + 19)], fill=(130, 155, 180))
    draw.polygon([(x + 8, y + 15), (x + 12, y + 21), (x + 7, y + 19)], fill=(130, 155, 180))
    if flame:
        draw.polygon([(x + 2, y + 19), (x + 4, y + 28), (x + 6, y + 19)], fill=(255, 185, 60))
        draw.line((x + 4, y + 23, x + 4, y + 30), fill=(255, 80, 45))


def _draw_flying_rocket(draw, x, y, frame, direction="left"):
    body = (214, 226, 234)
    nose = (255, 160, 65)
    fin = (128, 154, 180)
    smoke = (92, 104, 118)
    flame = (255, 187, 56)
    flame_hot = (255, 80, 45)

    wiggle = frame % 2
    if direction == "right":
        draw.polygon([(x + 56, y + 7), (x + 48, y + 2), (x + 34, y + 2), (x + 34, y + 12), (x + 48, y + 12)], fill=body)
        draw.polygon([(x + 56, y + 7), (x + 48, y + 2), (x + 48, y + 12)], fill=nose)
        draw.rectangle((x + 42, y + 5, x + 46, y + 9), fill=(35, 80, 120))
        draw.polygon([(x + 39, y + 2), (x + 33, y - 2), (x + 35, y + 4)], fill=fin)
        draw.polygon([(x + 39, y + 12), (x + 33, y + 16), (x + 35, y + 10)], fill=fin)
        draw.polygon([(x + 34, y + 4), (x + 25 - wiggle, y + 7), (x + 34, y + 10)], fill=flame)
        draw.polygon([(x + 34, y + 6), (x + 28 - wiggle, y + 7), (x + 34, y + 8)], fill=flame_hot)
        for i in range(5):
            sx = x + 27 - (i * 6) - ((frame + i) % 3)
            sy = y + 4 + ((frame + i) % 5)
            r = 1 + (i % 2)
            draw.rectangle((sx - r, sy - r, sx + r, sy + r), fill=smoke)
        return

    draw.polygon([(x, y + 7), (x + 8, y + 2), (x + 22, y + 2), (x + 22, y + 12), (x + 8, y + 12)], fill=body)
    draw.polygon([(x, y + 7), (x + 8, y + 2), (x + 8, y + 12)], fill=nose)
    draw.rectangle((x + 10, y + 5, x + 14, y + 9), fill=(35, 80, 120))
    draw.polygon([(x + 17, y + 2), (x + 23, y - 2), (x + 21, y + 4)], fill=fin)
    draw.polygon([(x + 17, y + 12), (x + 23, y + 16), (x + 21, y + 10)], fill=fin)
    draw.polygon([(x + 22, y + 4), (x + 31 + wiggle, y + 7), (x + 22, y + 10)], fill=flame)
    draw.polygon([(x + 22, y + 6), (x + 28 + wiggle, y + 7), (x + 22, y + 8)], fill=flame_hot)
    for i in range(5):
        sx = x + 29 + (i * 6) + ((frame + i) % 3)
        sy = y + 4 + ((frame + i) % 5)
        r = 1 + (i % 2)
        draw.rectangle((sx - r, sy - r, sx + r, sy + r), fill=smoke)


def _save_webp_frame(image):
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _save_webp_animation(frames, duration=90, loop=1):
    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=loop,
        lossless=True,
        quality=100,
    )
    return out.getvalue()


def _test_launch(seconds=0):
    return {
        "name": "Test Launch",
        "net": (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(),
        "status": {"name": "Go"},
        "launch_service_provider": {"name": "SpaceX"},
        "rocket": {"configuration": {"full_name": "Falcon 9", "name": "Falcon 9"}},
        "mission": {"name": "Pixora Test"},
        "program": [],
        "pad": {"name": "Pad", "location": {"name": "Cape Canaveral"}},
    }


def _shake_frames(launch, opts):
    offsets = (-1, 1, -2, 2, -1, 1, 0, 1, -1, 0)
    return [_draw_launch_page(launch, opts, rocket_offset=offset) for offset in offsets], [85] * len(offsets)


def _draw_liftoff_page(width, x=None, y=7, frame=0, direction="left"):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, 32), (0, 0, 0))
    if x is not None:
        _draw_flying_rocket(ImageDraw.Draw(image), x, y, frame, direction=direction)
    return image


def _liftoff_frames(launch, opts):
    width = _width(opts)
    frames = []
    durations = []
    for _ in range(3):
        frames.append(_draw_liftoff_page(width))
        durations.append(110)
    steps = 18
    for frame in range(steps):
        x = width + 5 - int((width + 34) * frame / (steps - 1))
        y = 7 + ((frame % 3) - 1)
        frames.append(_draw_liftoff_page(width, x=x, y=y, frame=frame))
        durations.append(65)
    for frame in range(steps):
        x = -61 + int((width + 66) * frame / (steps - 1))
        y = 7 + (((frame + 1) % 3) - 1)
        frames.append(_draw_liftoff_page(width, x=x, y=y, frame=frame, direction="right"))
        durations.append(65)
    return frames, durations


def _render_launch_animation_frames(payload=None, kind=None):
    payload = payload or {}
    width = payload.get("_width") or 64
    phase = str(kind or payload.get("phase") or "liftoff").lower()
    launch = payload.get("launch") if isinstance(payload.get("launch"), dict) else None
    if not launch:
        launch = _test_launch(3 if phase == "shake" else 0)
    opts = {
        "view": "countdown",
        "_width": width,
    }
    if phase == "shake":
        return _shake_frames(launch, opts)
    return _liftoff_frames(launch, opts)


def render_launch_test(width=64, phase="liftoff"):
    frames, durations = _render_launch_animation_frames({"_width": width, "phase": phase}, phase)
    return _save_webp_animation(frames, duration=durations, loop=1)


def _draw_launch_page(launch, opts, rocket_x=None, rocket_y=5, rocket_offset=0, flying_frame=None):
    from PIL import Image, ImageDraw

    width = _width(opts)
    is_wide = width == 128
    view = str(opts.get("view") or "countdown").lower()
    image = Image.new("RGB", (width, 32), (2, 6, 18))
    draw = ImageDraw.Draw(image)
    font = _font("assets/fonts/Silkscreen-Regular.ttf", 8)
    bold = _font("assets/fonts/PixelifySans-Bold.ttf", 8)
    blue = (80, 175, 255)
    orange = (255, 160, 65)
    white = (238, 245, 255)
    muted = (135, 165, 190)

    _draw_stars(draw, width)
    draw.rectangle((0, 0, width - 1, 8), fill=(5, 14, 34))
    title = _provider_label(launch)
    draw_sharp_text(image, (1, -3), title, blue, bold)
    if view == "mission":
        top = _fit(draw, _rocket_name(launch).upper(), bold, width - 20)
        bottom = _fit(draw, _mission_name(launch).upper(), font, width - 20)
        draw_sharp_text(image, (1, 10), top, white, bold)
        draw_sharp_text(image, (1, 21), bottom, muted, font)
    elif view == "location":
        countdown, when = _time_parts(launch)
        loc = _fit(draw, _location(launch).upper(), bold, width - 20)
        draw_sharp_text(image, (1, 10), loc, white, bold)
        draw_sharp_text(image, (1, 21), _clean_date(when or countdown), muted, font)
    else:
        countdown, when = _time_parts(launch)
        text = countdown
        digit_scale = 1
        digit_spacing = digit_scale
        tw, th = _countdown_text_size(draw, text, digit_scale, digit_spacing, bold)
        time_text = _clean_date(when)
        rocket_max = width - 20
        rocket = _rocket_name(launch).upper()
        if not is_wide:
            rocket = rocket.replace("FALCON 9", "F9").replace("FALCON HEAVY", "FHVY")
        rocket = _fit(draw, rocket, font, rocket_max)
        content_w = width - 20
        _draw_countdown_text(
            image,
            (max(1, (content_w - tw) // 2), 11),
            text,
            white,
            digit_scale,
            digit_spacing,
            bold,
        )
        time_w = draw.textbbox((0, 0), time_text, font=font)[2]
        draw_sharp_text(image, (max(1, (content_w - time_w) // 2), 16), time_text, orange, font)
        rocket_w = draw.textbbox((0, 0), rocket, font=font)[2]
        draw_sharp_text(image, (max(1, (content_w - rocket_w) // 2), 23), rocket, muted, font)

    if flying_frame is None:
        _draw_rocket(draw, (rocket_x if rocket_x is not None else width - 17) + rocket_offset, rocket_y, orange)
    else:
        _draw_flying_rocket(draw, rocket_x if rocket_x is not None else width - 4, rocket_y, flying_frame)

    return image


def render(options=None):
    opts = options or {}
    try:
        launch = _pick_launch(opts)
    except Exception:
        return _text_card(opts, "LAUNCH ERR", (238, 80, 80))
    if not launch:
        return None

    view = str(opts.get("view") or "countdown").lower()
    seconds = _seconds_until(launch)
    if view == "countdown" and seconds is not None:
        shake_key = f"{CARD_ID}|{_launch_key(launch)}|shake|{opts.get('_target', '')}"
        liftoff_key = f"{CARD_ID}|{_launch_key(launch)}|liftoff|{opts.get('_target', '')}"
        if 0 < seconds <= 120:
            warm_priority_graphic(
                shake_key,
                lambda: _save_webp_animation(*_shake_frames(launch, opts), loop=1),
            )
        if -30 <= seconds <= 120:
            warm_priority_graphic(
                liftoff_key,
                lambda: _save_webp_animation(*_liftoff_frames(launch, opts), loop=1),
            )
        if 0 < seconds <= 5 and _should_queue_launch_animation(launch, "shake"):
            frames, durations = _shake_frames(launch, opts)
            body = cached_priority_graphic(
                shake_key,
                lambda: _save_webp_animation(frames, duration=durations, loop=1),
            )
            return {
                "body": body,
                "dwell_secs": 4,
                "_stay": True,
                "_no_replay": True,
                "_priority_graphic": True,
            }
        if -30 <= seconds <= 0 and _should_queue_launch_animation(launch, "liftoff"):
            frames, durations = _liftoff_frames(launch, opts)
            body = cached_priority_graphic(
                liftoff_key,
                lambda: _save_webp_animation(frames, duration=durations, loop=1),
            )
            target = str(opts.get("launchAnimationTarget") or "device").strip().lower()
            if (target in ("group", "group_wall", "wall") or target.startswith("group:")) and _should_queue_launch_wall(launch):
                return {
                    "body": body,
                    "dwell_secs": 4,
                    "_group_wall": {
                        "type": "launch",
                        "renderer": "_render_launch_animation_frames",
                        "team": {"phase": "liftoff", "launch": launch},
                        "dwell_secs": 4,
                    },
                    "_priority_graphic": True,
                }
            return {
                "body": body,
                "dwell_secs": 4,
                "_stay": True,
                "_no_replay": True,
                "_priority_graphic": True,
            }

    return _save_webp_frame(_draw_launch_page(launch, opts))
