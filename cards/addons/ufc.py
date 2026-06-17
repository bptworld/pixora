from datetime import datetime, timedelta, timezone
from io import BytesIO
import math
import re
import urllib.request

from card_utils import cached_priority_graphic, draw_sharp_text, fetch_json_url, priority_graphic_key, warm_priority_graphic


CARD_ID = "ufc"
CARD_NAME = "UFC"
CARD_DETAIL = "Live ESPN UFC fight card"
WALL_RENDER_VERSION = "ufc-moments-winner-headshot-flag-v1"


def _graphic_target_option(key, label, default="group_wall"):
    return {
        "key": key,
        "label": label,
        "type": "select",
        "default": default,
        "choices": [
            {"value": "device", "label": "Single Device"},
            {"value": "group_wall", "label": "Group Wall"},
        ],
    }


CARD_OPTIONS = [
    {
        "key": "showRecords",
        "label": "Show Records",
        "type": "checkbox",
        "default": True,
    },
    _graphic_target_option("fightStartAnimationTarget", "Fight Start Graphic"),
    _graphic_target_option("roundStartAnimationTarget", "Round Start Graphic"),
    _graphic_target_option("knockoutAnimationTarget", "Knockout Graphic"),
    _graphic_target_option("submissionAnimationTarget", "Submission Graphic"),
    _graphic_target_option("decisionAnimationTarget", "Decision Graphic"),
    _graphic_target_option("winAnimationTarget", "Winner Graphic"),
]

_URL = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_CORE_STATUS_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_COLOR = (255, 70, 70)
_ALT = (245, 250, 255)
_MOMENT_STATE = {}
_CURRENT_FIGHT = {}
_HEADSHOT_CACHE = {}
_FLAG_CACHE = {}

_MOMENT_LABELS = {
    "fight_start": "FIGHT START",
    "round_start": "ROUND START",
    "knockout": "KNOCKOUT",
    "submission": "SUBMISSION",
    "decision": "DECISION",
    "win": "WINNER",
}

_MOMENT_TARGET_KEYS = {
    "fight_start": "fightStartAnimationTarget",
    "round_start": "roundStartAnimationTarget",
    "knockout": "knockoutAnimationTarget",
    "submission": "submissionAnimationTarget",
    "decision": "decisionAnimationTarget",
    "win": "winAnimationTarget",
}


def _competition_status(competition):
    status = ((competition.get("status") or {}).get("type") or {})
    detail = status.get("shortDetail") or status.get("detail") or status.get("description") or status.get("state") or ""
    detail = re.sub(r"\s+[A-Z]{2,3}T?$", "", str(detail)).strip()
    display_clock = str((competition.get("status") or {}).get("displayClock") or "").strip()
    period = int((competition.get("status") or {}).get("period") or 0)
    if period > 0 and display_clock and display_clock != "-":
        return f"R{period} {display_clock}"
    if period > 0:
        return f"ROUND {period}"
    name = str(status.get("name") or "").lower()
    if "pre" in name or "pre" in detail.lower():
        return "PRE-FIGHT"
    if status.get("completed"):
        return "FINAL"
    if str(status.get("state") or "").lower() == "in":
        return detail.upper()[:18] or "LIVE"
    return detail.upper()[:18] or "UFC"


def _fighter_name(competitor):
    athlete = competitor.get("athlete") or {}
    name = athlete.get("shortName") or athlete.get("displayName") or athlete.get("fullName") or "Fighter"
    name = str(name).strip()
    parts = [part for part in re.split(r"\s+", name.replace(".", "")) if part]
    return (parts[-1] if parts else name).upper()


def _athlete_id(competitor):
    athlete = (competitor or {}).get("athlete") or {}
    return str(athlete.get("id") or (competitor or {}).get("id") or "").strip()


def _headshot_url(competitor):
    athlete = (competitor or {}).get("athlete") or {}
    headshot = athlete.get("headshot") or {}
    if isinstance(headshot, dict) and headshot.get("href"):
        return str(headshot.get("href") or "").strip()
    athlete_id = _athlete_id(competitor)
    if athlete_id:
        return f"https://a.espncdn.com/i/headshots/mma/players/full/{athlete_id}.png"
    return ""


def _fetch_headshot(url, size=22):
    url = str(url or "").strip()
    if not url:
        return None
    key = f"{url}|{size}"
    if key in _HEADSHOT_CACHE:
        return _HEADSHOT_CACHE[key]
    try:
        from PIL import Image

        request = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1"})
        with urllib.request.urlopen(request, timeout=4) as response:
            data = response.read()
        image = Image.open(BytesIO(data)).convert("RGBA")
        side = min(image.width, image.height)
        if side > 0:
            left = max(0, (image.width - side) // 2)
            top = max(0, (image.height - side) // 3)
            image = image.crop((left, top, left + side, top + side))
        image.thumbnail((size, size), Image.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.alpha_composite(image, ((size - image.width) // 2, (size - image.height) // 2))
        _HEADSHOT_CACHE[key] = canvas
        return canvas
    except Exception:
        _HEADSHOT_CACHE[key] = None
        return None


def _flag_url(competitor):
    athlete = (competitor or {}).get("athlete") or {}
    flag = athlete.get("flag") or {}
    if isinstance(flag, dict) and flag.get("href"):
        return str(flag.get("href") or "").strip()
    return ""


def _fetch_flag(url, size=22):
    url = str(url or "").strip()
    if not url:
        return None
    key = f"{url}|{size}"
    if key in _FLAG_CACHE:
        return _FLAG_CACHE[key]
    try:
        from PIL import Image

        request = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1"})
        with urllib.request.urlopen(request, timeout=4) as response:
            data = response.read()
        image = Image.open(BytesIO(data)).convert("RGBA")
        image.thumbnail((size, size), Image.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.alpha_composite(image, ((size - image.width) // 2, (size - image.height) // 2))
        _FLAG_CACHE[key] = canvas
        return canvas
    except Exception:
        _FLAG_CACHE[key] = None
        return None


def _record(competitor, compact=False):
    records = competitor.get("records") or []
    for record in records:
        summary = str(record.get("summary") or "").strip()
        if summary:
            if compact:
                parts = summary.split("-")
                if len(parts) >= 2:
                    return "-".join(parts[:2])
            return summary
    return ""


def _fight_weight(competition):
    fight_type = competition.get("type") or {}
    return str(fight_type.get("abbreviation") or fight_type.get("text") or "").strip()


def _fight_broadcast(competition):
    broadcast = str(competition.get("broadcast") or "").strip()
    if broadcast:
        return broadcast
    for item in competition.get("broadcasts") or []:
        names = item.get("names") or []
        if names:
            return str(names[0]).strip()
    for item in competition.get("geoBroadcasts") or []:
        media = item.get("media") or {}
        name = str(media.get("shortName") or media.get("name") or "").strip()
        if name:
            return name
    return ""


def _fight_venue(competition):
    venue = competition.get("venue") or {}
    address = venue.get("address") or {}
    return str(address.get("city") or venue.get("fullName") or "").strip()


def _fight_rounds(competition):
    try:
        rounds = int((((competition.get("format") or {}).get("regulation") or {}).get("periods") or 0))
        return f"{rounds}R" if rounds else ""
    except Exception:
        return ""


def _fight_meta(competition):
    parts = [_fight_weight(competition), _fight_rounds(competition)]
    return " ".join(part for part in parts if part)


def _event_datetime(event):
    value = str((event or {}).get("date") or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _event_is_stale(event):
    event_time = _event_datetime(event)
    if not event_time:
        return False
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - event_time > timedelta(hours=8)


def _event_is_today(event):
    event_time = _event_datetime(event)
    if not event_time:
        return False
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)
    return event_time.astimezone().date() == datetime.now().astimezone().date()


def _event_has_live_fight(event):
    for competition in (event or {}).get("competitions") or []:
        status = ((competition.get("status") or {}).get("type") or {})
        if str(status.get("state") or "").lower() == "in" and not status.get("completed"):
            return True
    return False


def _event_completed(event):
    status = (((event or {}).get("status") or {}).get("type") or {})
    if status.get("completed"):
        return True
    competitions = (event or {}).get("competitions") or []
    return bool(competitions) and all((((competition.get("status") or {}).get("type") or {}).get("completed")) for competition in competitions)


def _event_has_recent_fight(event):
    return any(bool(competition.get("recent")) for competition in (event or {}).get("competitions") or [])


def _event_should_show(event):
    if _event_has_live_fight(event):
        return not _event_is_stale(event)
    if not _event_is_today(event):
        return False
    if _event_completed(event) and not _event_has_recent_fight(event):
        return False
    return True


def _fight_state(competition):
    return str((((competition or {}).get("status") or {}).get("type") or {}).get("state") or "").lower()


def _fight_completed(competition):
    return bool((((competition or {}).get("status") or {}).get("type") or {}).get("completed"))


def _fight_key(event, competition):
    return f"{(event or {}).get('id') or 'ufc'}:{(competition or {}).get('id') or 'fight'}"


def _moment_key(options, event, competition):
    device_id = str((options or {}).get("_device_id") or "local")
    return f"{device_id}:{competition.get('id') or event.get('id') or 'ufc'}"


def _moment_result_seen(options, event, competition):
    previous = _MOMENT_STATE.get(_moment_key(options, event, competition)) or {}
    return bool(previous.get("result") or previous.get("winner") or previous.get("completed"))


def _pick_fight(events, options=None):
    fights = _all_fights(events, include_stale=False)
    if not fights:
        return None, None
    device_id = str((options or {}).get("_device_id") or "local")
    active_key = _CURRENT_FIGHT.get(device_id)
    if active_key:
        for event, competition, _index in fights:
            if _fight_key(event, competition) == active_key:
                if _fight_state(competition) == "in" or (_fight_completed(competition) and not _moment_result_seen(options, event, competition)):
                    return event, competition
                _CURRENT_FIGHT.pop(device_id, None)
                break
        else:
            _CURRENT_FIGHT.pop(device_id, None)

    live = [
        item for item in fights
        if _fight_state(item[1]) == "in" and not _fight_completed(item[1])
    ]
    if live:
        live.sort(key=lambda item: (0 if item[1].get("recent") else 1, item[2]))
        event, competition, _index = live[0]
        _CURRENT_FIGHT[device_id] = _fight_key(event, competition)
        return event, competition

    upcoming = [
        item for item in fights
        if _fight_state(item[1]) == "pre" and not _fight_completed(item[1])
    ]
    if upcoming:
        upcoming.sort(key=lambda item: (item[2],))
        event, competition, _index = upcoming[0]
        return event, competition

    recent_results = [
        item for item in fights
        if _fight_completed(item[1]) and item[1].get("recent")
    ]
    if recent_results:
        recent_results.sort(key=lambda item: (item[2],))
        event, competition, _index = recent_results[-1]
        return event, competition

    return None, None


def _all_fights(events, include_stale=True):
    fights = []
    for event in events or []:
        if not include_stale and _event_is_stale(event):
            continue
        if not include_stale and not _event_should_show(event):
            continue
        for index, competition in enumerate(event.get("competitions") or []):
            if len(competition.get("competitors") or []) >= 2:
                fights.append((event, competition, index))
    return fights


def _pick_event(events):
    event, _competition = _pick_fight(events)
    if event:
        return event
    for wanted in ("in", "pre", "post"):
        for event in events:
            competition = (event.get("competitions") or [{}])[0]
            state = (((competition.get("status") or {}).get("type") or {}).get("state") or "").lower()
            if state == wanted:
                return event
    return events[0]


def _fit_text(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1].rstrip()
    return text


def _render_no_event(width):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (width, 32), (4, 5, 8))
    draw = ImageDraw.Draw(image)
    try:
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 10)
        small = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        bold = small = ImageFont.load_default()
    title = "UFC"
    tw = draw.textbbox((0, 0), title, font=bold)[2]
    draw_sharp_text(image, ((width - tw) // 2, 5), title, _COLOR, bold)
    msg = "NO FIGHTS"
    mw = draw.textbbox((0, 0), msg, font=small)[2]
    draw_sharp_text(image, ((width - mw) // 2, 20), msg, (150, 165, 180), small)
    return _webp(image)


def _render_event(event, options, competition=None):
    from PIL import Image, ImageDraw, ImageFont

    width = 128 if (options or {}).get("_target") == "matrixportal-s3-128x32" else 64
    image = Image.new("RGB", (width, 32), (4, 5, 8))
    draw = ImageDraw.Draw(image)
    try:
        tiny = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        small = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 9)
    except Exception:
        tiny = small = bold = ImageFont.load_default()

    competition = competition or (event.get("competitions") or [{}])[0]
    competitors = list(competition.get("competitors") or [])
    competitors.sort(key=lambda item: int(item.get("order") or 99))
    if len(competitors) < 2:
        return _render_no_event(width)

    left = competitors[0]
    right = competitors[1]
    left_name = _fighter_name(left)
    right_name = _fighter_name(right)
    status = _competition_status(competition)
    meta = _fight_meta(competition)

    draw.rectangle((0, 0, width - 1, 7), fill=(28, 6, 9))
    draw.rectangle((0, 29, width - 1, 31), fill=(70, 8, 12))
    header = _fit_text(draw, f"UFC {status}", tiny, width - 2)
    draw_sharp_text(image, (1, -4), header, _COLOR, tiny)

    if width >= 96:
        event_name = _fit_text(draw, (meta or str(event.get("shortName") or event.get("name") or "UFC")).upper(), tiny, width - 4)
        ew = draw.textbbox((0, 0), event_name, font=tiny)[2]
        draw_sharp_text(image, ((width - ew) // 2, 21), event_name, (150, 165, 180), tiny)
        mid = width // 2
        left_head = _fetch_headshot(_headshot_url(left), 22)
        right_head = _fetch_headshot(_headshot_url(right), 22)
        vs = "WIN" if left.get("winner") or right.get("winner") else "VS"
        vw = draw.textbbox((0, 0), vs, font=small)[2]
        draw.rounded_rectangle((mid - 12, 9, mid + 12, 20), radius=2, fill=(5, 5, 8), outline=(70, 8, 12))
        draw_sharp_text(image, ((width - vw) // 2, 9), vs, _COLOR, small)
        left_text = _fit_text(draw, left_name, bold, 45)
        right_text = _fit_text(draw, right_name, bold, 45)
        draw.rectangle((2, 8, 57, 18), fill=(4, 5, 8))
        draw.rectangle((71, 8, 126, 18), fill=(4, 5, 8))
        draw_sharp_text(image, (14, 8), left_text, _ALT if not left.get("winner") else (255, 225, 95), bold)
        rw = draw.textbbox((0, 0), right_text, font=bold)[2]
        draw_sharp_text(image, (114 - rw, 8), right_text, _ALT if not right.get("winner") else (255, 225, 95), bold)
        if left_head:
            image.paste(left_head, (1, 8), left_head)
        else:
            draw.rectangle((1, 8, 22, 29), fill=(10, 12, 16), outline=(70, 8, 12))
        if right_head:
            image.paste(right_head, (105, 8), right_head)
        else:
            draw.rectangle((105, 8, 126, 29), fill=(10, 12, 16), outline=(70, 8, 12))
    else:
        left_text = _fit_text(draw, left_name, small, 29)
        right_text = _fit_text(draw, right_name, small, 29)
        draw_sharp_text(image, (1, 8), left_text, _ALT if not left.get("winner") else (255, 225, 95), small)
        rw = draw.textbbox((0, 0), right_text, font=small)[2]
        draw_sharp_text(image, (63 - rw, 8), right_text, _ALT if not right.get("winner") else (255, 225, 95), small)
        vs = "W" if left.get("winner") or right.get("winner") else "VS"
        vw = draw.textbbox((0, 0), vs, font=tiny)[2]
        draw_sharp_text(image, ((64 - vw) // 2, 9), vs, _COLOR, tiny)

        show_records = bool((options or {}).get("showRecords", True))
        bottom = ""
        if show_records:
            lr = _record(left, compact=True)
            rr = _record(right, compact=True)
            if lr and rr:
                bottom = f"{lr} {rr}"
        if not bottom:
            bottom = meta or str(event.get("shortName") or event.get("name") or "UFC").upper()
        bottom = _fit_text(draw, bottom, tiny, 62)
        bw = draw.textbbox((0, 0), bottom, font=tiny)[2]
        draw_sharp_text(image, ((64 - bw) // 2, 21), bottom, (150, 165, 180), tiny)

    return _webp(image)


def _animation_width(options):
    try:
        explicit = int((options or {}).get("_width") or 0)
        if explicit > 0:
            return max(64, min(512, explicit))
    except Exception:
        pass
    return 128 if str((options or {}).get("_target") or "").lower().find("128x32") >= 0 else 64


def _hex_color(value, fallback=_COLOR):
    value = str(value or "").strip().lstrip("#")
    if len(value) == 6:
        try:
            return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            pass
    return fallback


def _fit_font(draw, text, max_width, sizes):
    from PIL import ImageFont

    text = str(text or "")
    font = ImageFont.load_default()
    for size in sizes:
        try:
            font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", size)
        except Exception:
            font = ImageFont.load_default()
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return font
    return font


def _moment_label(kind, width):
    kind = str(kind or "knockout").lower()
    label = _MOMENT_LABELS.get(kind, kind.replace("_", " ").upper())
    if width < 96:
        compact = {
            "FIGHT START": "FIGHT",
            "ROUND START": "ROUND",
            "KNOCKOUT": "KO",
            "SUBMISSION": "SUB",
            "DECISION": "DEC",
            "WINNER": "WIN",
        }
        return compact.get(label, label[:6])
    return label


def _draw_cage(draw, width, phase, color):
    bg = (3, 4, 7)
    draw.rectangle((0, 0, width - 1, 31), fill=bg)
    for y in (2, 5, 8):
        shade = 18 + y * 4
        draw.line((0, y, width - 1, y), fill=(shade, shade // 3, shade // 3))
    for x in range(-32, width + 32, 8):
        offset = (phase % 4) - 2
        draw.line((x + offset, 0, x + 23 + offset, 31), fill=(22, 28, 34))
        draw.line((x + 23 - offset, 0, x - offset, 31), fill=(17, 20, 26))
    draw.rectangle((0, 0, width - 1, 31), outline=(70, 76, 86))
    draw.rectangle((0, 0, width - 1, 2), fill=color)
    draw.rectangle((0, 29, width - 1, 31), fill=(90, 10, 16))
    for x in range(3, width, 11):
        light = (255, 238, 180) if ((x // 11) + phase) % 3 == 0 else (95, 35, 40)
        draw.rectangle((x, 1, min(width - 1, x + 1), 2), fill=light)


def _draw_octagon(draw, width, phase, color):
    mat = (24, 26, 30)
    edge = (118, 126, 132)
    y0 = 13
    cx = width // 2
    half = min(width // 2 - 3, 75)
    points = [
        (cx - half + 10, y0 + 3),
        (cx - half + 22, y0),
        (cx + half - 22, y0),
        (cx + half - 10, y0 + 3),
        (cx + half - 3, 24),
        (cx + half - 14, 31),
        (cx - half + 14, 31),
        (cx - half + 3, 24),
    ]
    draw.polygon(points, fill=mat, outline=edge)
    draw.line((cx - half + 5, 24, cx + half - 5, 24), fill=(50, 54, 60))
    draw.line((cx, y0, cx, 31), fill=(45, 48, 54))
    for x in range(cx - half + 8, cx + half - 8, 12):
        if ((x // 12) + phase) % 2 == 0:
            draw.point((x, 25), fill=color)


def _draw_fighter(draw, x, y, facing=1, color=(245, 250, 255), accent=_COLOR, pose=0):
    head = (x, y - 5, x + 3, y - 2)
    draw.ellipse(head, outline=color, fill=(14, 16, 20))
    draw.line((x + 1, y - 1, x + 1, y + 7), fill=color)
    arm_y = y + 1 + (pose % 2)
    draw.line((x + 1, arm_y, x + 1 + facing * 8, arm_y - 3), fill=accent)
    draw.line((x + 1, arm_y, x - facing * 5, arm_y + 2), fill=color)
    draw.line((x + 1, y + 7, x + 1 + facing * 4, y + 13), fill=color)
    draw.line((x + 1, y + 7, x - facing * 4, y + 13), fill=color)


def _draw_burst(draw, cx, cy, radius, color, alt, phase, width):
    for idx, angle in enumerate(range(0, 360, 30)):
        radians = math.radians(angle + phase * 9)
        length = radius + (idx % 4)
        x2 = int(cx + math.cos(radians) * length)
        y2 = int(cy + math.sin(radians) * min(length, 12))
        fill = alt if idx % 2 else color
        draw.line((cx, cy, x2, y2), fill=fill)
        if 0 <= x2 < width and 0 <= y2 < 32:
            draw.rectangle((x2 - 1, y2 - 1, x2 + 1, y2 + 1), fill=fill)
    draw.rectangle((cx - 1, cy - 1, cx + 1, cy + 1), fill=(255, 242, 112))


def _draw_moment_text(image, draw, label, width, color, alt, phase, reveal=1.0):
    max_width = width - (8 if width >= 96 else 29)
    font = _fit_font(draw, label, max_width, (20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8))
    box = draw.textbbox((0, 0), label, font=font)
    text_w = box[2] - box[0]
    x = max(29 if width < 96 else 2, (width - text_w) // 2) - box[0]
    y = (6 if width < 96 else 5) - box[1]
    panel_x0 = max(0, x - 3)
    panel_x1 = min(width - 1, x + text_w + 4)
    draw.rectangle((panel_x0, 5, panel_x1, 23), fill=(5, 5, 8), outline=color if phase % 2 else alt)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        draw_sharp_text(image, (x + dx, y + dy), label, (70, 0, 8), font)
    draw_sharp_text(image, (x, y), label, alt if phase % 2 else color, font)
    if reveal < 1:
        cover_x = int(panel_x0 + ((panel_x1 - panel_x0 + 1) * reveal))
        draw.rectangle((cover_x, 4, panel_x1 + 1, 24), fill=(5, 5, 8))


def _draw_winner_text(image, draw, winner_name, width, color, alt, phase, headshot_url="", flag_url=""):
    winner_name = str(winner_name or "").strip().upper()
    if not winner_name:
        return
    headshot = _fetch_headshot(headshot_url, 26) if width >= 96 else None
    flag = _fetch_flag(flag_url, 24) if width >= 96 else None
    if width < 96:
        lines = ["WINNER", winner_name]
        sizes = (9, 8, 7, 6)
        y_values = (5, 16)
    else:
        lines = [f"WINNER - {winner_name}"]
        sizes = (17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7)
        y_values = (8,)
    draw.rectangle((1, 4, width - 2, 25), fill=(5, 5, 8), outline=alt if phase % 2 else color)
    text_left = 30 if headshot else 0
    text_right = width - 30 if flag else width
    if headshot:
        image.paste(headshot, (2, 3), headshot)
        draw.rectangle((1, 3, 28, 29), outline=alt if phase % 2 else color)
    if flag:
        flag_x = width - 27
        image.paste(flag, (flag_x + 1, 4), flag)
        draw.rectangle((flag_x, 3, width - 2, 28), outline=alt if phase % 2 else color)
    for line, y_base in zip(lines, y_values):
        text_width = max(8, text_right - text_left - 4)
        font = _fit_font(draw, line, text_width, sizes)
        box = draw.textbbox((0, 0), line, font=font)
        text_w = box[2] - box[0]
        x = max(text_left + 1, text_left + ((text_width - text_w) // 2)) - box[0]
        y = y_base - box[1]
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            draw_sharp_text(image, (x + dx, y + dy), line, (70, 0, 8), font)
        draw_sharp_text(image, (x, y), line, alt if phase % 2 else color, font)


def _render_moment_animation_frames(team=None, kind="knockout"):
    from PIL import Image, ImageDraw

    team = team or {}
    width = _animation_width(team)
    color = _hex_color(team.get("color"), _COLOR)
    alt = _hex_color(team.get("alternateColor"), _ALT)
    label = _moment_label(kind, width)
    winner_name = str(team.get("winnerName") or team.get("winner") or "").strip().upper()
    winner_headshot = str(team.get("winnerHeadshot") or "").strip()
    winner_flag = str(team.get("winnerFlag") or "").strip()
    kind = str(kind or "knockout").lower()
    frames = []
    durations = []

    for step in range(10):
        image = Image.new("RGB", (width, 32), (3, 4, 7))
        draw = ImageDraw.Draw(image)
        _draw_cage(draw, width, step, color)
        _draw_octagon(draw, width, step, color)
        left_x = max(8, width // 2 - 20)
        right_x = min(width - 12, width // 2 + 17)
        _draw_fighter(draw, left_x, 15, 1, alt, color, step)
        _draw_fighter(draw, right_x, 15, -1, alt, (255, 210, 70), step + 1)
        if step > 3:
            _draw_burst(draw, width // 2, 13, 3 + step, color, alt, step, width)
        frames.append(image)
        durations.append(55)

    for step in range(16):
        image = Image.new("RGB", (width, 32), (3, 4, 7) if step % 2 else (22, 2, 6))
        draw = ImageDraw.Draw(image)
        _draw_cage(draw, width, step + 10, color)
        _draw_octagon(draw, width, step + 10, color)
        if kind in ("knockout", "submission"):
            _draw_burst(draw, width // 2, 14, 9 + (step % 6), color, alt, step, width)
            _draw_fighter(draw, max(6, width // 2 - 24), 16, 1, alt, color, step)
            if kind == "submission":
                draw.arc((width // 2 + 4, 15, width // 2 + 22, 31), 200, 520, fill=(255, 210, 70))
                draw.line((width // 2 + 9, 25, width // 2 + 25, 27), fill=alt)
            else:
                draw.line((width // 2 + 7, 27, width // 2 + 25, 29), fill=alt)
                draw.line((width // 2 + 13, 24, width // 2 + 22, 29), fill=alt)
        else:
            _draw_fighter(draw, max(7, width // 2 - 24), 15, 1, alt, color, step)
            _draw_fighter(draw, min(width - 11, width // 2 + 22), 15, -1, alt, (255, 210, 70), step + 1)
            if kind in ("fight_start", "round_start"):
                draw.rectangle((width // 2 - 2, 7, width // 2 + 2, 25), outline=(255, 210, 70))
                draw.line((width // 2 - 8, 16, width // 2 + 8, 16), fill=(255, 210, 70))
            else:
                _draw_burst(draw, width // 2, 16, 6 + (step % 4), color, alt, step, width)
        _draw_moment_text(image, draw, label, width, color, alt, step, min(1, (step + 1) / 8))
        frames.append(image)
        durations.append(75)

    for step in range(12):
        image = Image.new("RGB", (width, 32), (3, 4, 7) if step % 2 else (18, 1, 5))
        draw = ImageDraw.Draw(image)
        _draw_cage(draw, width, step + 26, color)
        _draw_octagon(draw, width, step + 26, color)
        for burst_x in (max(11, width // 5), width // 2, min(width - 12, width * 4 // 5)):
            _draw_burst(draw, burst_x, 8 + ((step + burst_x) % 12), 5 + (step % 5), color, alt, step + burst_x, width)
        _draw_moment_text(image, draw, label, width, color, alt, step, 1)
        frames.append(image)
        durations.append(110)

    if winner_name and kind in ("knockout", "submission", "decision", "win"):
        for step in range(14):
            image = Image.new("RGB", (width, 32), (3, 4, 7) if step % 2 else (18, 1, 5))
            draw = ImageDraw.Draw(image)
            _draw_cage(draw, width, step + 38, color)
            _draw_octagon(draw, width, step + 38, color)
            for burst_x in (max(11, width // 4), min(width - 12, width * 3 // 4)):
                _draw_burst(draw, burst_x, 9 + ((step + burst_x) % 10), 5 + (step % 5), color, alt, step + burst_x, width)
            _draw_winner_text(image, draw, winner_name, width, color, alt, step, winner_headshot, winner_flag)
            frames.append(image)
            durations.append(120)

    return frames, durations


def _render_moment_animation(team=None, kind="knockout"):
    frames, durations = _render_moment_animation_frames(team, kind)
    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=1,
        lossless=True,
        quality=100,
    )
    return out.getvalue()


def _core_status_result(event, competition):
    event_id = str((event or {}).get("id") or "").strip()
    competition_id = str((competition or {}).get("id") or "").strip()
    if not event_id or not competition_id:
        return {}
    url = (
        "https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc/"
        f"events/{event_id}/competitions/{competition_id}/status?lang=en&region=us"
    )
    try:
        data = fetch_json_url(url, _CORE_STATUS_CACHE, seconds=5, force=True)
        return data.get("result") or {}
    except Exception:
        return {}


def _result_kind(event, competition):
    status = ((competition.get("status") or {}).get("type") or {})
    text = " ".join(str(status.get(key) or "") for key in ("name", "description", "detail", "shortDetail"))
    result = _core_status_result(event, competition)
    if result:
        text += " " + " ".join(
            str(result.get(key) or "")
            for key in ("name", "displayName", "description", "displayDescription", "shortDisplayName")
        )
    notes = competition.get("notes")
    if isinstance(notes, list):
        text += " " + " ".join(str((item or {}).get("headline") or (item or {}).get("text") or item) for item in notes)
    elif notes:
        text += " " + str(notes)
    details = competition.get("details")
    if isinstance(details, list):
        text += " " + " ".join(
            str(((item or {}).get("type") or {}).get("text") or (item or {}).get("text") or "")
            for item in details
        )
    text = text.lower()
    if "submission" in text or "sub" in text:
        return "submission"
    if "ko" in text or "tko" in text or "knockout" in text:
        return "knockout"
    if "decision" in text or status.get("completed"):
        return "decision"
    return "win"


def _target_for_moment(kind, options):
    kind = str(kind or "").lower()
    key = _MOMENT_TARGET_KEYS.get(kind)
    opts = options or {}
    return str(opts.get(key) or opts.get("momentAnimationTarget") or "device").strip().lower()


def _winner_last_name(competition):
    for competitor in (competition or {}).get("competitors") or []:
        if competitor.get("winner"):
            return _fighter_name(competitor)
    return ""


def _winner_headshot_url(competition):
    for competitor in (competition or {}).get("competitors") or []:
        if competitor.get("winner"):
            return _headshot_url(competitor)
    return ""


def _winner_flag_url(competition):
    for competitor in (competition or {}).get("competitors") or []:
        if competitor.get("winner"):
            return _flag_url(competitor)
    return ""


def _queue_moment(kind, options, event, competition):
    width = _animation_width(options)
    winner_name = _winner_last_name(competition) if kind in ("knockout", "submission", "decision", "win") else ""
    winner_headshot = _winner_headshot_url(competition) if winner_name else ""
    winner_flag = _winner_flag_url(competition) if winner_name else ""
    team = {
        "abbreviation": "UFC",
        "shortDisplayName": "UFC",
        "displayName": "UFC",
        "color": "FF4646",
        "alternateColor": "FFF2A8",
        "winnerName": winner_name,
        "winnerHeadshot": winner_headshot,
        "winnerFlag": winner_flag,
        "_width": width,
    }
    target = _target_for_moment(kind, options)
    wall = target in ("group", "group_wall", "wall") or target.startswith("group:")
    cache_key = f"{priority_graphic_key(CARD_ID, team, kind, width)}|winner:{winner_name}|head:{winner_headshot}|flag:{winner_flag}"
    return {
        "body": cached_priority_graphic(cache_key, lambda: _render_moment_animation(team, kind)),
        "dwell_secs": 7,
        "_stay": True,
        "_no_replay": True,
        "_priority": True,
        "_group_wall": {
            "type": kind,
            "renderer": "_render_moment_animation_frames",
            "team": dict(team),
            "kind": kind,
            "dwell_secs": 7,
        } if wall else None,
    }


def _maybe_moment_animation(options, event, competition):
    status = ((competition.get("status") or {}).get("type") or {})
    state = str(status.get("state") or "").lower()
    completed = bool(status.get("completed"))
    period = int((competition.get("status") or {}).get("period") or 0)
    result_kind = _result_kind(event, competition)
    has_result = completed or any(c.get("winner") for c in competition.get("competitors") or []) or result_kind in ("knockout", "submission", "decision")
    key = _moment_key(options, event, competition)
    previous = _MOMENT_STATE.get(key)
    signature = {
        "state": state,
        "completed": completed,
        "period": period,
        "result": result_kind if has_result else "",
        "winner": any(c.get("winner") for c in competition.get("competitors") or []),
    }
    _MOMENT_STATE[key] = {**signature, "seen": datetime.now(timezone.utc)}

    team = {"abbreviation": "UFC", "color": "FF4646", "alternateColor": "FFF2A8", "_width": _animation_width(options)}
    warm_priority_graphic(priority_graphic_key(CARD_ID, team, "knockout", team["_width"]), lambda: _render_moment_animation(team, "knockout"))
    if previous is None:
        return None
    if has_result and not previous.get("result"):
        return _queue_moment(result_kind, options, event, competition)
    if signature["winner"] and not previous.get("winner"):
        return _queue_moment("win", options, event, competition)
    if state == "in" and previous.get("state") != "in":
        return _queue_moment("fight_start", options, event, competition)
    if period > 0 and period > int(previous.get("period") or 0):
        return _queue_moment("round_start", options, event, competition)
    return None


def _webp(image):
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def render(options=None):
    opts = options or {}
    data = fetch_json_url(_URL, _CACHE, seconds=15)
    events = data.get("events") or []
    event, competition = _pick_fight(events, opts)
    if not event:
        return None
    animation = _maybe_moment_animation(opts, event, competition)
    if animation:
        if animation.get("_group_wall"):
            animation["body"] = _render_event(event, opts, competition)
            animation["dwell_secs"] = opts.get("_dwell", 10)
            animation["_no_replay"] = False
        return animation
    return _render_event(event, opts, competition)
