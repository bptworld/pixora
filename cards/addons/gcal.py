from datetime import datetime, date, timedelta
from io import BytesIO
import urllib.request
from card_utils import draw_sharp_text, format_time, render_text_webp

CARD_ID = "gcal"
CARD_NAME = "Google Calendar"
CARD_DETAIL = "Next upcoming event"
CARD_OPTIONS = [
    {"key": "icsUrl",      "label": "Calendar ICS URL", "type": "text", "default": ""},
    {"key": "lookahead",   "label": "Days ahead",       "type": "number", "default": "14"},
]

_CACHE = {}


# ── ICS parsing ───────────────────────────────────────────────────────────────

def _parse_dt(raw):
    raw = (raw or "").strip().rstrip("Z")
    try:
        if "T" in raw:
            return datetime.strptime(raw[:15], "%Y%m%dT%H%M%S")
        return datetime.strptime(raw[:8], "%Y%m%d").date()
    except Exception:
        return None


def _occurrences(start, rrule_raw, from_dt, to_dt):
    if not rrule_raw:
        return [start]

    rule = {}
    for part in rrule_raw.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            rule[k.upper()] = v

    freq     = rule.get("FREQ", "")
    interval = max(1, int(rule.get("INTERVAL", 1)))
    count    = int(rule.get("COUNT", 9999))
    byday    = rule.get("BYDAY", "")
    start_d  = start.date() if isinstance(start, datetime) else start

    def make(d):
        return datetime.combine(d, start.time()) if isinstance(start, datetime) else d

    results = []

    if freq == "DAILY":
        d, n = start_d, 0
        while d <= to_dt and n < count:
            if d >= from_dt:
                results.append(make(d))
            d += timedelta(days=interval)
            n += 1

    elif freq == "WEEKLY":
        day_map = {"MO":0,"TU":1,"WE":2,"TH":3,"FR":4,"SA":5,"SU":6}
        targets = {day_map[x] for x in byday.split(",") if x in day_map} or {start_d.weekday()}
        d, n = start_d, 0
        while d <= to_dt and n < count:
            if d.weekday() in targets and d >= from_dt:
                results.append(make(d))
                n += 1
            d += timedelta(days=1)

    elif freq == "MONTHLY":
        d = start_d
        while d <= to_dt:
            if d >= from_dt:
                results.append(make(d))
            m = d.month + interval
            y = d.year + (m - 1) // 12
            m = (m - 1) % 12 + 1
            try:
                d = date(y, m, d.day)
            except ValueError:
                break

    elif freq == "YEARLY":
        y = start_d.year
        while True:
            try:
                d = date(y, start_d.month, start_d.day)
            except ValueError:
                y += interval
                continue
            if d > to_dt:
                break
            if d >= from_dt:
                results.append(make(d))
            y += interval

    return results


def _fetch_events(ics_url, days_ahead):
    now    = datetime.now()
    cached = _CACHE.get(ics_url)
    if cached and cached["expires"] > now:
        return cached["data"]

    req = urllib.request.Request(ics_url, headers={"User-Agent": "Pixora/0.1"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8", errors="replace")

    # Unfold continuation lines
    lines = []
    for line in raw.splitlines():
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line.strip()
        else:
            lines.append(line.strip())

    # Parse VEVENT blocks
    events, current, in_ev = [], {}, False
    for line in lines:
        if line == "BEGIN:VEVENT":
            in_ev, current = True, {}
        elif line == "END:VEVENT":
            if in_ev and current:
                events.append(current)
            in_ev = False
        elif in_ev and ":" in line:
            key, _, val = line.partition(":")
            base = key.split(";")[0].upper()
            current[base] = val

    today  = now.date()
    cutoff = today + timedelta(days=days_ahead)
    upcoming = []

    for ev in events:
        summary  = ev.get("SUMMARY", "No Title")
        dtstart  = _parse_dt(ev.get("DTSTART", ""))
        rrule    = ev.get("RRULE", "")
        if dtstart is None:
            continue
        start_d = dtstart.date() if isinstance(dtstart, datetime) else dtstart
        if start_d > cutoff:
            continue
        for occ in _occurrences(dtstart, rrule, today, cutoff):
            occ_d = occ.date() if isinstance(occ, datetime) else occ
            if occ_d < today or occ_d > cutoff:
                continue
            upcoming.append({
                "summary": summary,
                "start":   occ,
                "allday":  not isinstance(occ, datetime),
            })

    upcoming.sort(key=lambda e: (
        e["start"] if isinstance(e["start"], datetime)
        else datetime.combine(e["start"], datetime.min.time())
    ))

    _CACHE[ics_url] = {"data": upcoming, "expires": now + timedelta(minutes=15)}
    return upcoming


# ── Formatting ────────────────────────────────────────────────────────────────

def _fmt_when(ev):
    start  = ev["start"]
    today  = date.today()
    start_d = start.date() if isinstance(start, datetime) else start

    if start_d == today:
        day_str = "Today"
    elif start_d == today + timedelta(days=1):
        day_str = "Tomorrow"
    elif (start_d - today).days < 7:
        day_str = start_d.strftime("%A")[:3]
    else:
        day_str = start_d.strftime("%b %-d") if hasattr(start_d, "strftime") else str(start_d)

    if ev["allday"]:
        return day_str
    return f"{day_str} {format_time(start, include_ampm=True)}"


def _fmt_relative(ev):
    start = ev["start"]
    now   = datetime.now()
    if isinstance(start, datetime):
        delta = start - now
        total = int(delta.total_seconds())
        if total < 0:
            return "now"
        if total < 3600:
            return f"in {total // 60}m"
        if total < 86400:
            h = total // 3600
            m = (total % 3600) // 60
            return f"in {h}h{m:02d}m" if m else f"in {h}h"
    days = (start if isinstance(start, date) else start.date()) - date.today()
    n = days.days
    if n == 0:
        return "All Day"
    return f"in {n}d"


# ── Render ────────────────────────────────────────────────────────────────────

def render(options=None):
    from PIL import Image, ImageDraw, ImageFont
    opts      = options or {}
    width     = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    ics_url   = (opts.get("icsUrl") or "").strip()
    lookahead = max(1, min(365, int(opts.get("lookahead") or 14)))

    if not ics_url:
        return render_text_webp("SET URL", (100, 180, 255))

    try:
        events = _fetch_events(ics_url, lookahead)
    except Exception as e:
        return render_text_webp("CAL ERR", (238, 80, 80))

    image = Image.new("RGB", (width, 32), (5, 8, 20))
    draw  = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    # Header bar: when (left) + relative countdown (right)
    draw.rectangle((0, 0, width - 1, 6), fill=(15, 25, 55))
    if not events:
        draw_sharp_text(image, (1, -3), "CALENDAR", (100, 140, 255), bold)
        msg = "No events"
        mw = draw.textbbox((0, 0), msg, font=font)[2]
        draw_sharp_text(image, ((width - mw) // 2, 14), msg, (120, 130, 145), font)
    else:
        ev       = events[0]
        when_str = _fmt_when(ev)
        rel_str  = _fmt_relative(ev)
        ww = draw.textbbox((0, 0), when_str, font=font)[2]
        rw = draw.textbbox((0, 0), rel_str, font=font)[2]
        draw_sharp_text(image, (1, -3), when_str, (160, 180, 220), font)
        if ww + rw + 6 <= width - 2:
            draw_sharp_text(image, (width - 1 - rw, -3), rel_str, (80, 200, 140), font)

        # Word-wrap title into remaining space (y=9 to y=31 = 23px = up to 3 lines)
        words = ev["summary"].split()
        lines, current = [], ""
        for word in words:
            test = (current + " " + word).strip() if current else word
            if draw.textbbox((0, 0), test, font=font)[2] <= width - 2:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        lines = lines[:3]

        line_h = 9
        y = 9
        for line in lines:
            lw = draw.textbbox((0, 0), line, font=font)[2]
            draw_sharp_text(image, ((width - lw) // 2, y), line, (220, 230, 255), font)
            y += line_h

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

