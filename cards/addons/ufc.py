from datetime import datetime, timedelta, timezone
from io import BytesIO
import re
import urllib.request

from card_utils import cached_priority_graphic, draw_sharp_text, fetch_json_url, pixora_local_now, pixora_local_timezone, priority_graphic_key, warm_priority_graphic


CARD_ID = "ufc"
CARD_NAME = "UFC"
CARD_DETAIL = "Live ESPN UFC fight card"
WALL_RENDER_VERSION = "ufc-moments-layout-v5"


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
    _graphic_target_option("roundEndAnimationTarget", "Round End Graphic"),
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
    "round_end": "ROUND END",
    "knockout": "KNOCKOUT",
    "submission": "SUBMISSION",
    "decision": "DECISION",
    "win": "WINNER",
}

_MOMENT_TARGET_KEYS = {
    "fight_start": "fightStartAnimationTarget",
    "round_start": "roundStartAnimationTarget",
    "round_end": "roundEndAnimationTarget",
    "knockout": "knockoutAnimationTarget",
    "submission": "submissionAnimationTarget",
    "decision": "decisionAnimationTarget",
    "win": "winAnimationTarget",
}

_TEST_RESULT_FIGHTER = {
    "winnerName": "PEREIRA",
    "winnerHeadshot": "https://a.espncdn.com/i/headshots/mma/players/full/4705658.png",
    "winnerFlag": "BRA",
}

_TEST_MATCHUP = {
    "leftName": "PEREIRA",
    "rightName": "HILL",
    "leftHeadshot": "https://a.espncdn.com/i/headshots/mma/players/full/4705658.png",
    "rightHeadshot": "https://a.espncdn.com/i/headshots/mma/players/full/4426988.png",
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
    country = athlete.get("country") or athlete.get("citizenship") or athlete.get("birthPlace") or {}
    if isinstance(country, dict):
        code = country.get("abbreviation") or country.get("code") or country.get("country")
        if code:
            return str(code).strip().upper()
    return ""


def _draw_flag_code(code, size):
    code = str(code or "").strip().upper()
    if code not in {"AUS", "BRA", "CAN", "ENG", "FRA", "IRL", "MEX", "NGA", "NZL", "POL", "RUS", "UK", "USA"}:
        return None
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    x0, y0, x1, y1 = 1, max(1, size // 5), size - 2, size - max(2, size // 5)
    red = (200, 22, 45, 255)
    blue = (0, 56, 168, 255)
    dark_blue = (0, 38, 84, 255)
    green = (0, 122, 61, 255)
    yellow = (255, 205, 0, 255)
    white = (245, 245, 245, 255)

    def hstripe(colors):
        height = y1 - y0 + 1
        stripe_h = max(1, height // len(colors))
        y = y0
        for index, fill in enumerate(colors):
            bottom = y1 if index == len(colors) - 1 else min(y1, y + stripe_h - 1)
            draw.rectangle((x0, y, x1, bottom), fill=fill)
            y = bottom + 1

    def vstripe(colors):
        width = x1 - x0 + 1
        stripe_w = max(1, width // len(colors))
        x = x0
        for index, fill in enumerate(colors):
            right = x1 if index == len(colors) - 1 else min(x1, x + stripe_w - 1)
            draw.rectangle((x, y0, right, y1), fill=fill)
            x = right + 1

    draw.rectangle((x0, y0, x1, y1), fill=white)
    if code == "USA":
        hstripe([red, white, red, white, red])
        draw.rectangle((x0, y0, x0 + max(4, size // 3), y0 + max(3, size // 4)), fill=dark_blue)
        draw.point((x0 + 2, y0 + 2), fill=white)
        draw.point((x0 + 4, y0 + 4), fill=white)
    elif code == "BRA":
        draw.rectangle((x0, y0, x1, y1), fill=(0, 156, 59, 255))
        draw.polygon([(size // 2, y0 + 1), (x1 - 1, size // 2), (size // 2, y1 - 1), (x0 + 1, size // 2)], fill=yellow)
        draw.ellipse((size // 2 - 3, size // 2 - 3, size // 2 + 3, size // 2 + 3), fill=blue)
    elif code == "CAN":
        vstripe([red, white, red])
    elif code in ("ENG", "UK"):
        draw.rectangle((size // 2 - 1, y0, size // 2 + 1, y1), fill=red)
        draw.rectangle((x0, size // 2 - 1, x1, size // 2 + 1), fill=red)
    elif code == "FRA":
        vstripe([(0, 35, 149, 255), white, (237, 41, 57, 255)])
    elif code == "IRL":
        vstripe([(22, 155, 98, 255), white, (255, 136, 62, 255)])
    elif code == "MEX":
        vstripe([green, white, red])
    elif code == "NGA":
        vstripe([green, white, green])
    elif code == "NZL":
        draw.rectangle((x0, y0, x1, y1), fill=(0, 0, 139, 255))
        draw.point((x1 - 4, y0 + 4), fill=red)
        draw.point((x1 - 7, y0 + 8), fill=red)
    elif code == "POL":
        hstripe([white, (220, 20, 60, 255)])
    elif code == "RUS":
        hstripe([white, blue, red])
    elif code == "AUS":
        draw.rectangle((x0, y0, x1, y1), fill=(0, 0, 139, 255))
        draw.point((x1 - 4, y0 + 4), fill=white)
        draw.point((x1 - 7, y0 + 8), fill=white)
    draw.rectangle((x0, y0, x1, y1), outline=(210, 220, 226, 255))
    return image


def _fetch_flag(url, size=22):
    url = str(url or "").strip()
    if not url:
        return None
    key = f"{url}|{size}"
    if key in _FLAG_CACHE:
        return _FLAG_CACHE[key]
    code_flag = _draw_flag_code(url, size)
    if code_flag:
        _FLAG_CACHE[key] = code_flag
        return code_flag
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
    local_tz = pixora_local_timezone()
    local_event = event_time.astimezone(local_tz) if local_tz else event_time.astimezone()
    return local_event.date() == pixora_local_now().date()


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


def _draw_matchup_card(image, draw, fonts, matchup, header, bottom="", show_records=True):
    width = image.width
    tiny, small, bold = fonts
    left_name = str(matchup.get("leftName") or "FIGHTER").upper()
    right_name = str(matchup.get("rightName") or "FIGHTER").upper()
    left_winner = bool(matchup.get("leftWinner"))
    right_winner = bool(matchup.get("rightWinner"))

    draw.rectangle((0, 0, width - 1, 6), fill=(28, 6, 9))
    draw.rectangle((0, 29, width - 1, 31), fill=(70, 8, 12))
    header = _fit_text(draw, header, tiny, width - 2)
    draw_sharp_text(image, (1, -4), header, _COLOR, tiny)

    if width >= 96:
        bottom = _fit_text(draw, str(bottom or "UFC").upper(), tiny, width - 4)
        ew = draw.textbbox((0, 0), bottom, font=tiny)[2]
        draw_sharp_text(image, ((width - ew) // 2, 21), bottom, (150, 165, 180), tiny)
        mid = width // 2
        head_size = 22
        left_head_x = 1
        right_head_x = width - head_size - 1
        vs_left = mid - 12
        vs_right = mid + 12
        left_text_x = left_head_x + head_size + 2
        left_text_right = vs_left - 3
        right_text_x = vs_right + 3
        right_text_right = right_head_x - 3
        left_head = _fetch_headshot(matchup.get("leftHeadshot"), 22)
        right_head = _fetch_headshot(matchup.get("rightHeadshot"), 22)
        vs = "WIN" if left_winner or right_winner else "VS"
        vw = draw.textbbox((0, 0), vs, font=small)[2]
        draw.rounded_rectangle((vs_left, 9, vs_right, 20), radius=2, fill=(5, 5, 8), outline=(70, 8, 12))
        draw_sharp_text(image, ((width - vw) // 2, 9), vs, _COLOR, small)
        left_text = _fit_text(draw, left_name, bold, max(8, left_text_right - left_text_x))
        right_text = _fit_text(draw, right_name, bold, max(8, right_text_right - right_text_x))
        draw.rectangle((2, 8, left_text_right + 1, 18), fill=(4, 5, 8))
        draw.rectangle((right_text_x - 1, 8, width - 3, 18), fill=(4, 5, 8))
        lw = draw.textbbox((0, 0), left_text, font=bold)[2]
        draw_sharp_text(image, (max(left_text_x, left_text_right - lw), 8), left_text, _ALT if not left_winner else (255, 225, 95), bold)
        draw_sharp_text(image, (right_text_x, 8), right_text, _ALT if not right_winner else (255, 225, 95), bold)
        if left_head:
            image.paste(left_head, (left_head_x, 8), left_head)
        else:
            draw.rectangle((left_head_x, 8, left_head_x + head_size - 1, 29), fill=(10, 12, 16), outline=(70, 8, 12))
        if right_head:
            image.paste(right_head, (right_head_x, 8), right_head)
        else:
            draw.rectangle((right_head_x, 8, right_head_x + head_size - 1, 29), fill=(10, 12, 16), outline=(70, 8, 12))
    else:
        left_text = _fit_text(draw, left_name, small, 29)
        right_x = 35
        right_text = _fit_text(draw, right_name, small, 63 - right_x)
        draw_sharp_text(image, (1, 8), left_text, _ALT if not left_winner else (255, 225, 95), small)
        vs = "W" if left_winner or right_winner else "VS"
        vw = draw.textbbox((0, 0), vs, font=tiny)[2]
        draw_sharp_text(image, ((64 - vw) // 2, 9), vs, _COLOR, tiny)
        draw_sharp_text(image, (right_x, 8), right_text, _ALT if not right_winner else (255, 225, 95), small)
        bottom = _fit_text(draw, str(bottom or "UFC").upper(), tiny, 62)
        bw = draw.textbbox((0, 0), bottom, font=tiny)[2]
        draw_sharp_text(image, ((64 - bw) // 2, 21), bottom, (150, 165, 180), tiny)


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
    bottom = meta or str(event.get("shortName") or event.get("name") or "UFC").upper()
    if width < 96 and bool((options or {}).get("showRecords", True)):
        lr = _record(left, compact=True)
        rr = _record(right, compact=True)
        if lr and rr:
            bottom = f"{lr} {rr}"
    _draw_matchup_card(
        image,
        draw,
        (tiny, small, bold),
        {
            "leftName": left_name,
            "rightName": right_name,
            "leftHeadshot": _headshot_url(left),
            "rightHeadshot": _headshot_url(right),
            "leftWinner": left.get("winner"),
            "rightWinner": right.get("winner"),
        },
        f"UFC {status}",
        bottom,
    )

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
            "ROUND END": "ROUND",
            "KNOCKOUT": "KO",
            "SUBMISSION": "SUB",
            "DECISION": "DEC",
            "WINNER": "WIN",
        }
        return compact.get(label, label[:6])
    return label


def _round_label(kind, round_number):
    kind = str(kind or "round_start").lower()
    suffix = "END" if kind == "round_end" else "START"
    try:
        round_number = int(round_number or 0)
    except Exception:
        round_number = 0
    if round_number > 0:
        return f"ROUND {round_number} {suffix}"
    return f"ROUND {suffix}"


def _draw_winner_text(image, draw, winner_name, moment_label, width, color, alt, phase, headshot_url="", flag_url=""):
    winner_name = str(winner_name or "").strip().upper()
    if not winner_name:
        return
    moment_label = str(moment_label or "WINNER").strip().upper()
    head_size = 26 if width >= 96 else 18
    flag_size = 24 if width >= 96 else 16
    headshot = _fetch_headshot(headshot_url, head_size)
    flag = _fetch_flag(flag_url, flag_size)
    if width < 96:
        name_sizes = (9, 8, 7, 6)
        label_sizes = (7, 6, 5)
        y_values = (7, 18)
    else:
        name_sizes = (14, 13, 12, 11, 10, 9, 8, 7)
        label_sizes = (10, 9, 8, 7)
        y_values = (5, 18)
    draw.rectangle((1, 3, width - 2, 28), fill=(5, 5, 8), outline=alt if phase % 2 else color)
    text_left = 4
    text_right = width - 4
    if headshot:
        hx = 2
        hy = max(3, (32 - headshot.height) // 2)
        image.paste(headshot, (hx, hy), headshot)
        draw.rectangle((1, hy - 1, hx + headshot.width + 1, hy + headshot.height), outline=alt if phase % 2 else color)
        text_left = hx + headshot.width + 4
    if flag:
        fx = width - flag.width - 2
        fy = max(4, (32 - flag.height) // 2)
        image.paste(flag, (fx, fy), flag)
        draw.rectangle((fx - 1, fy - 1, width - 2, fy + flag.height), outline=alt if phase % 2 else color)
        text_right = fx - 3
    lines = (
        (winner_name, name_sizes, y_values[0], alt if phase % 2 else color),
        (moment_label, label_sizes, y_values[1], color if phase % 2 else alt),
    )
    for line, sizes, y_base, fill in lines:
        text_width = max(8, text_right - text_left)
        font = _fit_font(draw, line, text_width, sizes)
        box = draw.textbbox((0, 0), line, font=font)
        text_w = box[2] - box[0]
        x = text_left + max(0, (text_width - text_w) // 2) - box[0]
        y = y_base - box[1]
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            draw_sharp_text(image, (x + dx, y + dy), line, (70, 0, 8), font)
        draw_sharp_text(image, (x, y), line, fill, font)


def _render_round_matchup_frame(team, kind="round_start"):
    from PIL import Image, ImageDraw, ImageFont

    team = team or {}
    width = _animation_width(team)
    image = Image.new("RGB", (width, 32), (4, 5, 8))
    draw = ImageDraw.Draw(image)
    try:
        tiny = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        small = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 9)
    except Exception:
        tiny = small = bold = ImageFont.load_default()
    matchup = {
        "leftName": team.get("leftName") or "PEREIRA",
        "rightName": team.get("rightName") or "HILL",
        "leftHeadshot": team.get("leftHeadshot") or _TEST_RESULT_FIGHTER["winnerHeadshot"],
        "rightHeadshot": team.get("rightHeadshot") or "https://a.espncdn.com/i/headshots/mma/players/full/4426988.png",
        "leftWinner": False,
        "rightWinner": False,
    }
    header = "FIGHT START" if str(kind or "").lower() == "fight_start" else _round_label(kind, team.get("roundNumber"))
    _draw_matchup_card(image, draw, (tiny, small, bold), matchup, header, "UFC")
    return image


def _render_round_matchup_frames(team, kind="round_start"):
    frame = _render_round_matchup_frame(team, kind)
    return [frame.copy() for _ in range(12)], [250] * 12


def _render_result_wall_frames(team, kind="knockout"):
    from PIL import Image, ImageDraw

    team = team or {}
    width = _animation_width(team)
    color = _hex_color(team.get("color"), _COLOR)
    alt = _hex_color(team.get("alternateColor"), _ALT)
    label = _moment_label(kind, width)
    winner_name = str(team.get("winnerName") or team.get("winner") or "").strip().upper()
    winner_headshot = str(team.get("winnerHeadshot") or "").strip()
    winner_flag = str(team.get("winnerFlag") or "").strip()
    if not winner_name:
        return [], []
    frames = []
    durations = []
    for step in range(18):
        image = Image.new("RGB", (width, 32), (3, 4, 7) if step % 2 else (18, 1, 5))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width - 1, 2), fill=color)
        draw.rectangle((0, 29, width - 1, 31), fill=(90, 10, 16))
        for x in range(4 + (step % 3), width, 12):
            draw.point((x, 1), fill=alt if step % 2 else (255, 238, 180))
        _draw_winner_text(image, draw, winner_name, label, width, color, alt, step, winner_headshot, winner_flag)
        frames.append(image)
        durations.append(140)
    return frames, durations


def _render_moment_animation_frames(team=None, kind="knockout"):
    team = team or {}
    kind = str(kind or "knockout").lower()
    if kind in ("fight_start", "round_start", "round_end"):
        return _render_round_matchup_frames(team, kind)
    if kind in ("knockout", "submission", "decision", "win"):
        return _render_result_wall_frames(team, kind)
    return _render_result_wall_frames(team, kind)


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
        result_details = []
        for item in details:
            detail_text = str(((item or {}).get("type") or {}).get("text") or (item or {}).get("text") or "")
            lower_detail = detail_text.lower()
            if "winner" in lower_detail or lower_detail.startswith("result"):
                result_details.append(detail_text)
        text += " " + " ".join(result_details)
    text = text.lower()
    if re.search(r"\bsubmission\b|\bsub\b", text):
        return "submission"
    if re.search(r"\bko\b|\btko\b|\bko/tko\b|\bkotko\b|\bknockout\b", text):
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
    winner = _winner_competitor(competition)
    return _fighter_name(winner) if winner else ""


def _winner_headshot_url(competition):
    winner = _winner_competitor(competition)
    return _headshot_url(winner) if winner else ""


def _winner_flag_url(competition):
    winner = _winner_competitor(competition)
    return _flag_url(winner) if winner else ""


def _winner_competitor(competition):
    for competitor in (competition or {}).get("competitors") or []:
        if competitor.get("winner") is True:
            return competitor
    return None


def _sample_result_fighter(competition):
    competitors = (competition or {}).get("competitors") or []
    return _winner_competitor(competition) or (competitors[0] if competitors else None)


def _result_test_payload(competition):
    competitor = _sample_result_fighter(competition)
    if not competitor:
        return dict(_TEST_RESULT_FIGHTER)
    payload = {
        "winnerName": _fighter_name(competitor),
        "winnerHeadshot": _headshot_url(competitor),
        "winnerFlag": _flag_url(competitor),
    }
    if not payload["winnerName"] or not payload["winnerHeadshot"]:
        return dict(_TEST_RESULT_FIGHTER)
    if not payload["winnerFlag"]:
        payload["winnerFlag"] = _TEST_RESULT_FIGHTER["winnerFlag"]
    return payload


def _matchup_payload(competition):
    competitors = list((competition or {}).get("competitors") or [])
    competitors.sort(key=lambda item: int(item.get("order") or 99))
    if len(competitors) < 2:
        return dict(_TEST_MATCHUP)
    left = competitors[0]
    right = competitors[1]
    return {
        "leftName": _fighter_name(left),
        "rightName": _fighter_name(right),
        "leftHeadshot": _headshot_url(left),
        "rightHeadshot": _headshot_url(right),
    }


def _warm_moment_test_graphics(base_team, competition):
    result_payload = _result_test_payload(competition)
    matchup_payload = _matchup_payload(competition)
    for kind in _MOMENT_TARGET_KEYS:
        test_team = dict(base_team)
        if kind in ("round_start", "round_end"):
            test_team.update(matchup_payload)
            test_team["roundNumber"] = 2 if kind == "round_end" else 1
        elif kind in ("knockout", "submission", "decision", "win"):
            test_team.update(result_payload)
        warm_priority_graphic(
            priority_graphic_key(CARD_ID, base_team, kind, base_team["_width"]),
            lambda test_team=test_team, kind=kind: _render_moment_animation(test_team, kind),
        )


def _queue_moment(kind, options, event, competition):
    width = _animation_width(options)
    if kind in ("knockout", "submission", "decision", "win"):
        winner_name = _winner_last_name(competition)
        winner_headshot = _winner_headshot_url(competition) if winner_name else ""
        winner_flag = _winner_flag_url(competition) if winner_name else ""
        if not winner_name:
            logger = (options or {}).get("_log")
            if callable(logger):
                logger(f"[ufc] skipped {kind} graphic: ESPN result has no winner for competition {(competition or {}).get('id') or (event or {}).get('id') or 'unknown'}")
            return None
    elif kind in ("round_start", "round_end"):
        winner_name = ""
        winner_headshot = ""
        winner_flag = ""
    else:
        result_payload = _result_test_payload(competition)
        winner_name = result_payload.get("winnerName") or ""
        winner_headshot = result_payload.get("winnerHeadshot") or ""
        winner_flag = result_payload.get("winnerFlag") or ""
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
    if kind in ("round_start", "round_end"):
        team.update(_matchup_payload(competition))
        team["roundNumber"] = int(((competition.get("status") or {}).get("period") or 0))
    target = _target_for_moment(kind, options)
    wall = target in ("group", "group_wall", "wall") or target.startswith("group:")
    cache_key = (
        f"{priority_graphic_key(CARD_ID, team, kind, width)}|{WALL_RENDER_VERSION}"
        f"|winner:{winner_name}|head:{winner_headshot}|flag:{winner_flag}"
        f"|round:{team.get('roundNumber') or ''}"
        f"|left:{team.get('leftName') or ''}:{team.get('leftHeadshot') or ''}"
        f"|right:{team.get('rightName') or ''}:{team.get('rightHeadshot') or ''}"
    )
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
    if (options or {}).get("_is_prefetch"):
        return None
    status = ((competition.get("status") or {}).get("type") or {})
    state = str(status.get("state") or "").lower()
    completed = bool(status.get("completed"))
    period = int((competition.get("status") or {}).get("period") or 0)
    display_clock = str((competition.get("status") or {}).get("displayClock") or "").strip()
    result_kind = _result_kind(event, competition)
    winner_ready = _winner_competitor(competition) is not None
    result_ready = winner_ready and (completed or result_kind in ("knockout", "submission", "decision", "win"))
    key = _moment_key(options, event, competition)
    previous = _MOMENT_STATE.get(key)
    signature = {
        "state": state,
        "completed": completed,
        "period": period,
        "clock": display_clock,
        "result": result_kind if result_ready else "",
        "winner": winner_ready,
    }
    _MOMENT_STATE[key] = {**signature, "seen": datetime.now(timezone.utc)}

    team = {"abbreviation": "UFC", "color": "FF4646", "alternateColor": "FFF2A8", "_width": _animation_width(options)}
    _warm_moment_test_graphics(team, competition)
    if previous is None:
        return None
    if result_ready and not previous.get("result"):
        return _queue_moment(result_kind, options, event, competition)
    if signature["winner"] and not previous.get("winner"):
        return _queue_moment("win", options, event, competition)
    if state == "in" and previous.get("state") != "in":
        return _queue_moment("fight_start", options, event, competition)
    if period > 0 and period > int(previous.get("period") or 0):
        return _queue_moment("round_start", options, event, competition)
    previous_clock = str(previous.get("clock") or "").strip()
    if (
        state == "in"
        and period > 0
        and previous.get("period") == period
        and previous_clock
        and previous_clock not in ("0:00", "00:00", "-")
        and display_clock in ("0:00", "00:00")
    ):
        return _queue_moment("round_end", options, event, competition)
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
        team = {"abbreviation": "UFC", "color": "FF4646", "alternateColor": "FFF2A8", "_width": _animation_width(opts)}
        _warm_moment_test_graphics(team, {})
        return None
    animation = _maybe_moment_animation(opts, event, competition)
    if animation:
        return animation
    return _render_event(event, opts, competition)
