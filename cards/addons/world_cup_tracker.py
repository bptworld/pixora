from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import re
import urllib.request

from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "world_cup_tracker"
CARD_NAME = "World Cup Tracker"
CARD_CATEGORY = "Sports"
CARD_DETAIL = "Track one World Cup team"
CARD_OPTIONS = [
    {"key": "team", "label": "Team", "type": "text", "default": "USA", "maxlength": 20},
]

_COLOR = (70, 220, 125)
_CACHE = {}
_STANDINGS_URL = "https://site.web.api.espn.com/apis/v2/sports/soccer/fifa.world/standings"
_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=20260601-20260731"


def _fetch_json(url, seconds=300):
    now = datetime.now(timezone.utc)
    cached = _CACHE.get(url)
    if cached and cached["expires"] > now:
        return cached["data"]
    request = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=12) as response:
        data = json.loads(response.read().decode("utf-8"))
    _CACHE[url] = {"data": data, "expires": now + timedelta(seconds=seconds)}
    return data


def _team_values(team):
    return {
        str(team.get("abbreviation") or "").upper(),
        str(team.get("shortDisplayName") or "").upper(),
        str(team.get("displayName") or "").upper(),
        str(team.get("name") or "").upper(),
        str(team.get("location") or "").upper(),
    }


def _team_matches(team, selected):
    selected = str(selected or "").strip().upper()
    return bool(selected and selected in _team_values(team or {}))


def _stat(entry, *names):
    wanted = {str(name).lower() for name in names}
    for stat in entry.get("stats") or []:
        keys = {
            str(stat.get("type") or "").lower(),
            str(stat.get("name") or "").lower(),
            str(stat.get("abbreviation") or "").lower(),
        }
        if keys & wanted:
            return str(stat.get("displayValue") or stat.get("value") or "")
    return ""


def _rank_value(entry, fallback=99):
    try:
        note_rank = ((entry.get("note") or {}).get("rank"))
        if note_rank not in (None, ""):
            return int(float(note_rank))
    except Exception:
        pass
    try:
        rank = _stat(entry, "rank", "r")
        if rank:
            return int(float(rank))
    except Exception:
        pass
    return fallback


def _group_letter(group):
    match = re.search(r"group\s+([a-z])", str(group.get("name") or group.get("abbreviation") or ""), re.I)
    return match.group(1).upper() if match else ""


def _standings_for_team(selected):
    data = _fetch_json(_STANDINGS_URL, seconds=300)
    for child in data.get("children") or []:
        entries = (((child or {}).get("standings") or {}).get("entries") or [])
        entries = sorted(entries, key=lambda entry: _rank_value(entry))
        for index, entry in enumerate(entries, start=1):
            team = entry.get("team") or {}
            if _team_matches(team, selected):
                return child, entries, entry, _rank_value(entry, index)
    return None, [], None, 0


def _entry_row(entry, index):
    team = entry.get("team") or {}
    abbr = (team.get("abbreviation") or team.get("shortDisplayName") or "?")[:4].upper()
    wins = _stat(entry, "wins", "w")
    draws = _stat(entry, "ties", "draws", "d", "t")
    losses = _stat(entry, "losses", "l")
    points = _stat(entry, "points", "pts")
    record = f"{wins}-{draws}-{losses}" if wins or draws or losses else ""
    return {
        "rank": str(_rank_value(entry, index)),
        "abbr": abbr,
        "record": record,
        "points": points or "0",
        "team": team,
    }


def _event_dt(event):
    try:
        return datetime.fromisoformat(str(event.get("date") or "").replace("Z", "+00:00"))
    except Exception:
        return datetime.max.replace(tzinfo=timezone.utc)


def _event_state(event):
    comp = (event.get("competitions") or [{}])[0]
    return ((comp.get("status") or {}).get("type") or {}).get("state") or ""


def _event_teams(event):
    comp = (event.get("competitions") or [{}])[0]
    return [competitor.get("team") or {} for competitor in comp.get("competitors") or []]


def _event_has_team(event, selected):
    return any(_team_matches(team, selected) for team in _event_teams(event))


def _placeholder_values(group_letter, rank):
    group_letter = str(group_letter or "").upper()
    if not group_letter or not rank:
        return set()
    values = {f"{rank}{group_letter}"}
    if int(rank or 0) == 3:
        values.add("3RD")
    return values


def _event_has_placeholder(event, group_letter, rank):
    wanted = _placeholder_values(group_letter, rank)
    if not wanted:
        return False
    for team in _event_teams(event):
        values = _team_values(team)
        if values & wanted:
            if "3RD" not in wanted:
                return True
            text = " ".join(values)
            if group_letter in text or "3RD" in values:
                return True
    return False


def _pick_knockout_event(selected, group_letter="", rank=0):
    data = _fetch_json(_SCOREBOARD_URL, seconds=300)
    events = [event for event in data.get("events") or [] if str((event.get("season") or {}).get("slug") or "") != "group-stage"]
    if not events:
        return None
    now = datetime.now(timezone.utc)
    exact = [event for event in events if _event_has_team(event, selected)]
    candidates = exact or [event for event in events if _event_has_placeholder(event, group_letter, rank)]
    if not candidates:
        return None
    active = [event for event in candidates if _event_state(event) == "in"]
    if active:
        return sorted(active, key=_event_dt)[0]
    upcoming = [event for event in candidates if _event_state(event) != "post" and _event_dt(event) >= now - timedelta(hours=4)]
    if upcoming:
        return sorted(upcoming, key=_event_dt)[0]
    return sorted(candidates, key=_event_dt, reverse=True)[0]


def _round_label(event):
    slug = str((event.get("season") or {}).get("slug") or "").replace("-", " ").upper()
    labels = {
        "ROUND OF 32": "R32",
        "ROUND OF 16": "R16",
        "QUARTERFINALS": "QF",
        "SEMIFINALS": "SF",
        "THIRD PLACE": "3RD",
        "FINAL": "FINAL",
    }
    return labels.get(slug, slug[:8] or "KNOCK")


def _abbr(team, width):
    if width == 128:
        return str(team.get("shortDisplayName") or team.get("abbreviation") or "TBD").upper()[:10]
    return str(team.get("abbreviation") or team.get("shortDisplayName") or "TBD").upper()[:4]


def _score_or_vs(event):
    comp = (event.get("competitions") or [{}])[0]
    competitors = comp.get("competitors") or []
    state = _event_state(event)
    if state == "pre":
        return "VS"
    away = next((item for item in competitors if item.get("homeAway") == "away"), competitors[-1] if competitors else {})
    home = next((item for item in competitors if item.get("homeAway") == "home"), competitors[0] if competitors else {})
    return f"{away.get('score', '0')}-{home.get('score', '0')}"


def _event_status(event):
    comp = (event.get("competitions") or [{}])[0]
    status = ((comp.get("status") or {}).get("type") or {}).get("shortDetail") or ""
    if _event_state(event) == "pre":
        dt = _event_dt(event).astimezone()
        return dt.strftime("%b").upper() + f" {dt.day} " + dt.strftime("%I:%M%p").lstrip("0")
    return status or "WORLD CUP"


def _fit(draw, text, font, max_width):
    text = str(text or "").strip()
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1].rstrip()
    return text


def _center(image, draw, text, y, font, color, x1=0, x2=None):
    x2 = image.width - 1 if x2 is None else x2
    width = draw.textbbox((0, 0), text, font=font)[2]
    draw_sharp_text(image, (x1 + ((x2 - x1 + 1) - width) // 2, y), text, color, font)


def _render_matchup(event, selected, width, font, bold):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, 32), (3, 8, 12))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, 8), fill=(4, 24, 20))
    title = f"{selected[:4].upper()} {_round_label(event)}"
    draw_sharp_text(image, (1, -3), title[:18 if width == 128 else 10], _COLOR, bold)

    teams = _event_teams(event)
    away = teams[1] if len(teams) > 1 else teams[0] if teams else {}
    home = teams[0] if teams else {}
    if width == 128:
        left = _fit(draw, _abbr(away, width), font, 48)
        right = _fit(draw, _abbr(home, width), font, 48)
        _center(image, draw, _score_or_vs(event), 9, bold, (245, 250, 255), 50, 77)
        draw_sharp_text(image, (2, 10), left, (245, 250, 255), font)
        rw = draw.textbbox((0, 0), right, font=font)[2]
        draw_sharp_text(image, (126 - rw, 10), right, (245, 250, 255), font)
        _center(image, draw, _event_status(event).upper()[:22], 22, font, (145, 165, 182), 0, 127)
    else:
        left = _abbr(away, width)
        right = _abbr(home, width)
        draw_sharp_text(image, (1, 10), left, (245, 250, 255), font)
        rw = draw.textbbox((0, 0), right, font=font)[2]
        draw_sharp_text(image, (63 - rw, 10), right, (245, 250, 255), font)
        _center(image, draw, _score_or_vs(event), 10, bold, (245, 250, 255))
        _center(image, draw, _event_status(event).upper()[:14], 22, font, (145, 165, 182))
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _draw_group_frame(rows, title, selected, color, offset, width, font, bold):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, 32), (3, 8, 12))
    draw = ImageDraw.Draw(image)
    selected = str(selected or "").upper()
    for index, row in enumerate(rows):
        y = 7 + index * 8 - offset
        if y < -1 or y > 31:
            continue
        is_selected = selected in _team_values(row.get("team") or {})
        main = (255, 235, 95) if is_selected else (245, 250, 255)
        muted = color if is_selected else (145, 165, 182)
        if width == 128:
            draw_sharp_text(image, (2, y), row["rank"], muted, font)
            draw_sharp_text(image, (14, y), row["abbr"], main, bold)
            draw_sharp_text(image, (54, y), row["record"][:7], (190, 205, 218), font)
            pts = f"PTS {row['points']}"
            pw = draw.textbbox((0, 0), pts, font=font)[2]
            draw_sharp_text(image, (127 - pw, y), pts, muted, font)
        else:
            draw_sharp_text(image, (1, y), row["rank"], muted, font)
            draw_sharp_text(image, (8, y), row["abbr"][:3], main, bold)
            pts = f"P{row['points']}"
            pw = draw.textbbox((0, 0), pts, font=font)[2]
            draw_sharp_text(image, (63 - pw, y), pts, muted, font)
    draw.rectangle((0, 0, width - 1, 8), fill=(4, 24, 20))
    draw_sharp_text(image, (1, -3), title[:18 if width == 128 else 10], color, bold)
    return image


def _render_group(child, entries, selected, width, font, bold):
    group = _group_letter(child) or "?"
    title = f"{str(selected).upper()[:4]} GROUP {group}" if width == 128 else f"{str(selected).upper()[:3]} GRP {group}"
    rows = [_entry_row(entry, index) for index, entry in enumerate(entries, start=1)]
    max_offset = max(0, (len(rows) - 3) * 8)
    offsets = [0] if max_offset == 0 else [0] + list(range(1, max_offset + 1))
    frames = [_draw_group_frame(rows, title, selected, _COLOR, offset, width, font, bold) for offset in offsets]
    out = BytesIO()
    if len(frames) == 1:
        frames[0].save(out, "WEBP", lossless=True, quality=100)
    else:
        durations = [2000] + [120 for _ in frames[1:]]
        durations[-1] = 3000
        frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=durations, loop=0, lossless=True, quality=100)
    return out.getvalue()


def render(options=None):
    from PIL import ImageFont

    opts = options or {}
    selected = str(opts.get("team") or "USA").strip().upper() or "USA"
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    try:
        child, entries, selected_entry, rank = _standings_for_team(selected)
    except Exception:
        return render_text_webp("WC TRACK ERR", (238, 80, 80))
    if not child or not selected_entry:
        return render_text_webp("TEAM NOT FOUND", (238, 80, 80))

    group = _group_letter(child)
    knockout = _pick_knockout_event(selected, group, rank)
    if knockout:
        state = _event_state(knockout)
        exact = _event_has_team(knockout, selected)
        if exact or state != "pre":
            return {"body": _render_matchup(knockout, selected, width, font, bold), "_sports_live": state == "in"}

    return _render_group(child, entries, selected, width, font, bold)
