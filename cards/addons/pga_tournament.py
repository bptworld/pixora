from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import re
import unicodedata
import urllib.request

from card_utils import draw_sharp_text, render_text_webp


CARD_ID = "pga_tournament"
CARD_NAME = "PGA Tournament"
CARD_DETAIL = "Current live PGA tournament"
CARD_OPTIONS = []

_COLOR = (92, 220, 132)
_BG = (0, 6, 12)
_CACHE = {}


def _width(options):
    options = options or {}
    try:
        explicit = int(options.get("_width") or 0)
        if explicit > 0:
            return max(64, min(128, explicit))
    except Exception:
        pass
    return 128 if options.get("_target") == "matrixportal-s3-128x32" else 64


def _font(name="Silkscreen-Regular.ttf", size=8):
    from PIL import ImageFont

    for prefix in ("assets/fonts", "cards/assets/fonts"):
        try:
            return ImageFont.truetype(f"{prefix}/{name}", size)
        except Exception:
            pass
    return ImageFont.load_default()


def _clean(text, limit=32):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _short_event_name(event, width):
    name = event.get("shortName") or event.get("name") or "PGA"
    words = [word for word in _clean(name, 48).replace("Championship", "Champ").split() if word]
    if not words:
        return "PGA"
    limit = 22 if width >= 96 else 12
    text = " ".join(words)
    if len(text) <= limit:
        return text
    if len(words) >= 2 and len(" ".join(words[:2])) <= limit:
        return " ".join(words[:2])
    return words[0][:limit]


def _dated_url():
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=7)
    end = now + timedelta(days=21)
    dates = start.strftime("%Y%m%d") + "-" + end.strftime("%Y%m%d")
    return f"https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates={dates}"


def _fetch_scoreboard():
    now = datetime.now(timezone.utc)
    cached = _CACHE.get("scoreboard")
    if cached and cached["expires"] > now:
        return cached["data"]
    request = urllib.request.Request(_dated_url(), headers={"User-Agent": "Pixora/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=12) as response:
        data = json.loads(response.read().decode("utf-8"))
    events = data.get("events") or []
    live = any(_event_state(event).get("state") == "in" for event in events)
    _CACHE["scoreboard"] = {"data": data, "expires": now + (timedelta(seconds=30) if live else timedelta(minutes=10))}
    return data


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _event_state(event):
    comp = (event.get("competitions") or [{}])[0]
    return (comp.get("status") or event.get("status") or {}).get("type", {})


def _status_text(event):
    comp = (event.get("competitions") or [{}])[0]
    status = comp.get("status") or event.get("status") or {}
    status_type = status.get("type") or {}
    state = status_type.get("state") or ""
    detail = status_type.get("shortDetail") or status_type.get("detail") or status_type.get("description") or ""
    period = status.get("period") or ""
    if state == "in":
        return f"LIVE R{period}" if period else "LIVE"
    if state == "post":
        return "FINAL"
    detail = re.sub(r"\s+[A-Z]{2,3}T?$", "", str(detail))
    detail = detail.replace("Thu, ", "").replace("Fri, ", "").replace("Sat, ", "").replace("Sun, ", "")
    return _clean(detail.upper(), 18) or "UPCOMING"


def _pick_event(events):
    now = datetime.now(timezone.utc)
    live = [event for event in events if _event_state(event).get("state") == "in"]
    if live:
        return live[0]
    upcoming = []
    recent = []
    for event in events:
        dt = _parse_dt(event.get("date"))
        state = _event_state(event).get("state")
        if state != "post" and (not dt or dt >= now - timedelta(days=2)):
            upcoming.append((dt or now, event))
        elif dt:
            recent.append((dt, event))
    if upcoming:
        return sorted(upcoming, key=lambda item: item[0])[0][1]
    if recent:
        return sorted(recent, key=lambda item: item[0], reverse=True)[0][1]
    return events[0] if events else None


def _rank_value(competitor):
    try:
        return int(competitor.get("order") or 9999)
    except Exception:
        return 9999


def _leader_rows(event, limit=12):
    comp = (event.get("competitions") or [{}])[0]
    competitors = [item for item in (comp.get("competitors") or []) if isinstance(item, dict)]
    competitors.sort(key=_rank_value)
    rows = []
    for competitor in competitors[:limit]:
        athlete = competitor.get("athlete") or {}
        name = athlete.get("shortName") or athlete.get("displayName") or athlete.get("fullName") or "Player"
        score = str(competitor.get("score") or "").strip() or "E"
        thru = ""
        for stat in competitor.get("statistics") or competitor.get("stats") or []:
            stat_name = str(stat.get("name") or stat.get("type") or stat.get("abbreviation") or "").lower()
            value = str(stat.get("displayValue") or stat.get("value") or "").strip()
            if stat_name in ("thru", "through", "holes") and value:
                thru = value
            elif stat_name in ("score", "total", "topar") and value:
                score = value
        rows.append({
            "rank": str(competitor.get("order") or len(rows) + 1),
            "name": _clean(name, 22),
            "score": score,
            "thru": thru,
        })
    return rows


def _center(image, draw, text, y, color, font, x1=0, x2=None):
    if x2 is None:
        x2 = image.width - 1
    text = str(text or "")
    w = draw.textbbox((0, 0), text, font=font)[2]
    draw_sharp_text(image, (x1 + max(0, ((x2 - x1 + 1) - w) // 2), y), text, color, font)


def _draw_shell(width, title):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, 32), _BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, 6), fill=(5, 18, 25))
    font = _font()
    bold = _font("Silkscreen-Bold.ttf")
    _center(image, draw, title.upper(), -3, _COLOR, bold)
    draw.line((0, 31, width - 1, 31), fill=(20, 78, 48))
    return image, draw, font, bold


def _summary_frame(event, width):
    image, draw, font, bold = _draw_shell(width, "PGA")
    name = _short_event_name(event, width).upper()
    status = _status_text(event)
    if width >= 96:
        _center(image, draw, name, 9, (235, 245, 255), bold)
        _center(image, draw, status, 21, _COLOR, font)
    else:
        _center(image, draw, name, 9, (235, 245, 255), font)
        _center(image, draw, status, 21, _COLOR, font)
    return image


def _leader_frame(event, rows, start, width):
    title = _short_event_name(event, width).upper()
    image, draw, font, bold = _draw_shell(width, title if width >= 96 else "PGA")
    visible = rows[start:start + 3]
    for index, row in enumerate(visible):
        y = 8 + index * 8
        rank = row.get("rank", "")[:3 if width >= 96 else 2]
        score = row.get("score", "")[:6 if width >= 96 else 4]
        name_limit = 18 if width >= 96 else 9
        name = _clean(row.get("name"), name_limit).upper()
        draw_sharp_text(image, (2, y), rank, _COLOR, font)
        draw_sharp_text(image, (18 if width >= 96 else 13, y), name, (235, 245, 255), font)
        if score:
            w = draw.textbbox((0, 0), score, font=bold)[2]
            draw_sharp_text(image, (width - w - 1, y), score, _COLOR, bold)
    return image


def _webp(frames, durations):
    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=len(frames) > 1,
        append_images=frames[1:],
        duration=durations if len(frames) > 1 else durations[0],
        loop=0 if len(frames) > 1 else 1,
        lossless=True,
        quality=100,
    )
    return out.getvalue()


def render(options=None):
    width = _width(options)
    try:
        events = _fetch_scoreboard().get("events") or []
    except Exception:
        return render_text_webp("PGA ERR", (238, 90, 90))
    event = _pick_event(events)
    if not event:
        return render_text_webp("NO PGA", (160, 160, 160))
    rows = _leader_rows(event, 12)
    frames = [_summary_frame(event, width)]
    durations = [2500]
    if rows:
        step = 3
        for start in range(0, min(len(rows), 12), step):
            frames.append(_leader_frame(event, rows, start, width))
            durations.append(2500 if start == 0 else 1800)
    return _webp(frames, durations)
