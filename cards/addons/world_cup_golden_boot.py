from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import unicodedata
import urllib.request

from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "world_cup_golden_boot"
CARD_NAME = "World Cup Golden Boot"
CARD_CATEGORY = "Sports"
CARD_DETAIL = "World Cup top scorers"
CARD_OPTIONS = []

_COLOR = (255, 210, 80)
_CACHE = {}
_LEADERS_URL = "https://sports.core.api.espn.com/v2/sports/soccer/leagues/fifa.world/seasons/2026/types/1/leaders?lang=en&region=us"


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


def _ref_data(item, key):
    ref = ((item.get(key) or {}).get("$ref") or "").replace("http://", "https://")
    if not ref:
        return {}
    try:
        return _fetch_json(ref, seconds=3600)
    except Exception:
        return {}


def _plain_text(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _leaders(limit=10):
    data = _fetch_json(_LEADERS_URL, seconds=300)
    category = next((cat for cat in data.get("categories") or [] if cat.get("name") == "goalsLeaders"), None)
    rows = []
    for item in (category or {}).get("leaders") or []:
        athlete = _ref_data(item, "athlete")
        team = _ref_data(item, "team")
        name = _plain_text(athlete.get("shortName") or athlete.get("displayName") or athlete.get("fullName") or "PLAYER")
        abbr = team.get("abbreviation") or team.get("shortDisplayName") or ""
        try:
            goals = int(float(item.get("value") or 0))
        except Exception:
            goals = 0
        rows.append({"name": name, "team": abbr, "goals": goals})
        if len(rows) >= limit:
            break
    return rows


def _fit(draw, text, font, max_width):
    text = str(text or "").strip().upper()
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1].rstrip()
    return text


def _draw_frame(rows, offset, width, font, bold):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, 32), (5, 6, 9))
    draw = ImageDraw.Draw(image)
    for index, row in enumerate(rows):
        y = 7 + index * 8 - offset
        if y < -1 or y > 31:
            continue
        rank = str(index + 1)
        draw_sharp_text(image, (1, y), rank, _COLOR, font)
        if width == 128:
            name = _fit(draw, row["name"], font, 70)
            draw_sharp_text(image, (13, y), name, (245, 250, 255), font)
            team = str(row["team"] or "")[:3].upper()
            draw_sharp_text(image, (91, y), team, (145, 165, 182), font)
            goals = str(row["goals"])
            gw = draw.textbbox((0, 0), goals, font=bold)[2]
            draw_sharp_text(image, (126 - gw, y - 1), goals, _COLOR, bold)
        else:
            name = _fit(draw, row["name"], font, 38)
            draw_sharp_text(image, (8, y), name, (245, 250, 255), font)
            goals = str(row["goals"])
            gw = draw.textbbox((0, 0), goals, font=bold)[2]
            draw_sharp_text(image, (63 - gw, y - 1), goals, _COLOR, bold)
    draw.rectangle((0, 0, width - 1, 8), fill=(26, 18, 4))
    draw_sharp_text(image, (1, -3), "GOLDEN BOOT" if width == 128 else "GOLD BOOT", _COLOR, bold)
    return image


def _render(rows, width):
    from PIL import ImageFont

    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    max_offset = max(0, (len(rows) - 3) * 8)
    if max_offset == 0:
        offsets = [0]
    elif width == 128:
        offsets = list(range(0, max_offset + 1, 24))
        if offsets[-1] != max_offset:
            offsets.append(max_offset)
    else:
        offsets = [0] + list(range(1, max_offset + 1))
    frames = [_draw_frame(rows, offset, width, font, bold) for offset in offsets]
    out = BytesIO()
    if len(frames) == 1:
        frames[0].save(out, "WEBP", lossless=True, quality=100)
    else:
        durations = [4000 for _ in frames] if width == 128 else [2000] + [120 for _ in frames[1:]]
        durations[-1] = 3000
        frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=durations, loop=0, lossless=True, quality=100)
    return out.getvalue()


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    try:
        rows = _leaders()
    except Exception:
        return render_text_webp("BOOT ERR", (238, 80, 80))
    if not rows:
        return render_text_webp("NO GOALS", (160, 160, 160))
    return _render(rows, width)
