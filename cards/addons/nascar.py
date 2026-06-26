from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import urllib.request

from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "nascar"
CARD_NAME = "NASCAR"
CARD_DETAIL = "ESPN NASCAR Cup standings"
CARD_OPTIONS = []

STANDINGS_URL = "https://site.web.api.espn.com/apis/v2/sports/racing/nascar-premier/standings"
_CACHE = {}


def _glyph_width(font, ch):
    try:
        return max(1, font.getbbox(ch)[2] - font.getbbox(ch)[0])
    except Exception:
        return 6


def _tight_text_width(text, font, spacing=-1):
    chars = list(str(text))
    if not chars:
        return 0
    return sum(_glyph_width(font, ch) for ch in chars) + (spacing * (len(chars) - 1))


def _draw_tight_text(image, xy, text, fill, font, spacing=-1):
    x, y = xy
    chars = list(str(text))
    for index, ch in enumerate(chars):
        draw_sharp_text(image, (x, y), ch, fill, font)
        if index < len(chars) - 1:
            x += max(1, _glyph_width(font, ch) + spacing)


def _stat(entry, *names):
    names = {n.lower() for n in names}
    for stat in entry.get("stats", []):
        if str(stat.get("type", "")).lower() in names or str(stat.get("abbreviation", "")).lower() in names:
            return stat.get("displayValue", "")
    return ""


def _driver_name(entry):
    athlete = entry.get("athlete") or {}
    name = athlete.get("shortName") or athlete.get("displayName") or athlete.get("name") or "DRIVER"
    name = str(name).upper().replace(" ", "")
    return name[:10]


def _points(entry):
    return str(_stat(entry, "points", "pts", "pointstotal", "totalpoints") or "").strip()


def _fetch_rows():
    now = datetime.now(timezone.utc)
    cached = _CACHE.get("standings")
    if cached and cached["expires"] > now:
        return cached["rows"]
    req = urllib.request.Request(STANDINGS_URL, headers={"User-Agent": "Pixora/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    children = data.get("children") or []
    entries = (((children[0] if children else {}).get("standings") or {}).get("entries") or [])
    rows = []
    for index, entry in enumerate(entries[:12], start=1):
        rank = _stat(entry, "rank", "rk") or str(index)
        rows.append((str(rank), _driver_name(entry), _points(entry)))
    _CACHE["standings"] = {"rows": rows, "expires": now + timedelta(minutes=30)}
    return rows


def _draw_header(image, color, font, bold, width=64):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, 6), fill=(6, 17, 26))
    title = "NASCAR"
    if width == 128:
        tw = _tight_text_width(title, bold, spacing=-1)
        _draw_tight_text(image, ((width - tw) // 2, -3), title, color, bold, spacing=-1)
    else:
        _draw_tight_text(image, (1, -3), title, color, bold, spacing=-1)


def _draw_rows(image, rows, color, font, bold, offset=0, width=64):
    for index, row in enumerate(rows):
        rank, name = row[0], row[1]
        points = row[2] if len(row) > 2 else ""
        y = 8 + (index * 8) - offset
        if y < 8 or y > 31:
            continue
        if width == 128:
            _draw_tight_text(image, (2, y), rank[:3], color, font, spacing=-1)
            _draw_tight_text(image, (18, y), name[:16], (235, 245, 255), font, spacing=-1)
            if points:
                pw = _tight_text_width(points, font, spacing=-1)
                _draw_tight_text(image, (127 - pw, y), points[:8], color, font, spacing=-1)
        else:
            _draw_tight_text(image, (1, y), rank[:2], color, font, spacing=-1)
            _draw_tight_text(image, (10, y), name, (235, 245, 255), font, spacing=-1)


def _frame(rows, color, font, bold, offset=0, width=64):
    from PIL import Image

    image = Image.new("RGB", (width, 32), (0, 5, 12))
    _draw_rows(image, rows, color, font, bold, offset, width=width)
    _draw_header(image, color, font, bold, width=width)
    return image


def render(options=None):
    from PIL import ImageFont

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    color = (255, 210, 70)
    try:
        rows = _fetch_rows()
    except Exception:
        return render_text_webp("NASCAR ERR", (238, 80, 80))
    if not rows:
        return render_text_webp("NO NASCAR", (160, 160, 160))

    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    out = BytesIO()
    if len(rows) <= 3:
        image = _frame(rows, color, font, bold, 0, width=width)
        image.save(out, "WEBP", lossless=True, quality=100)
        return out.getvalue()

    max_offset = (len(rows) - 3) * 8
    offsets = [0] + list(range(1, max_offset + 1))
    frames = [_frame(rows, color, font, bold, offset, width=width) for offset in offsets]
    durations = [2000] + [120 for _ in offsets[1:]]
    durations[-1] = 3000
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        lossless=True,
        quality=100,
    )
    return out.getvalue()

