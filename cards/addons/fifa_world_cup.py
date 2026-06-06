from datetime import datetime, timedelta, timezone
from io import BytesIO

from card_utils import draw_sharp_text, fetch_json_request, fetch_logo, render_text_webp

CARD_ID = "fifa_world_cup"
CARD_NAME = "FIFA World Cup"
CARD_DETAIL = "Live and upcoming World Cup matches"
CARD_OPTIONS = [
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "USA",
        "choices": [
            {"value": "", "label": "Next Match"},
            {"value": "USA", "label": "United States"},
            {"value": "CAN", "label": "Canada"},
            {"value": "MEX", "label": "Mexico"},
            {"value": "ARG", "label": "Argentina"},
            {"value": "BRA", "label": "Brazil"},
            {"value": "ENG", "label": "England"},
            {"value": "FRA", "label": "France"},
            {"value": "GER", "label": "Germany"},
            {"value": "ESP", "label": "Spain"},
            {"value": "POR", "label": "Portugal"},
            {"value": "ITA", "label": "Italy"},
            {"value": "NED", "label": "Netherlands"},
            {"value": "JPN", "label": "Japan"},
            {"value": "KOR", "label": "South Korea"},
            {"value": "AUS", "label": "Australia"},
        ],
    },
]

_COLOR = (70, 220, 125)
_CACHE_SECONDS = 300


def _date_range():
    now = datetime.now(timezone.utc)
    start = now.date()
    # The 2026 group stage starts June 11; before then, ask ESPN for the full
    # published tournament range so favorites can show their next fixture.
    if start < datetime(2026, 6, 11, tzinfo=timezone.utc).date():
        start = datetime(2026, 6, 11, tzinfo=timezone.utc).date()
    end = start + timedelta(days=45)
    tournament_end = datetime(2026, 7, 19, tzinfo=timezone.utc).date()
    if start <= tournament_end:
        end = min(end, tournament_end)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _scoreboard():
    start, end = _date_range()
    return fetch_json_request(
        f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={start}-{end}",
        seconds=_CACHE_SECONDS,
    )


def _event_dt(event):
    try:
        return datetime.fromisoformat(str(event.get("date") or "").replace("Z", "+00:00"))
    except Exception:
        return datetime.max.replace(tzinfo=timezone.utc)


def _team_values(team):
    return {
        str(team.get("abbreviation") or "").upper(),
        str(team.get("shortDisplayName") or "").upper(),
        str(team.get("displayName") or "").upper(),
        str(team.get("name") or "").upper(),
    }


def _event_has_favorite(event, favorite):
    favorite = str(favorite or "").strip().upper()
    if not favorite:
        return True
    competition = (event.get("competitions") or [{}])[0]
    for competitor in competition.get("competitors") or []:
        if favorite in _team_values(competitor.get("team") or {}):
            return True
    return False


def _pick_event(events, favorite=""):
    now = datetime.now(timezone.utc) - timedelta(hours=4)
    candidates = [event for event in events if _event_dt(event) >= now and _event_has_favorite(event, favorite)]
    if not candidates and favorite:
        candidates = [event for event in events if _event_has_favorite(event, favorite)]
    if not candidates:
        candidates = [event for event in events if _event_dt(event) >= now] or list(events)
    state_order = {"in": 0, "pre": 1, "post": 2}
    candidates.sort(key=lambda event: (
        state_order.get(((event.get("competitions") or [{}])[0].get("status") or {}).get("type", {}).get("state"), 3),
        _event_dt(event),
    ))
    return candidates[0] if candidates else None


def _score_text(away, home, state):
    if state == "pre":
        return "VS"
    return f"{away.get('score', '0')}-{home.get('score', '0')}"


def _status_text(event, state):
    competition = (event.get("competitions") or [{}])[0]
    status = (competition.get("status") or {}).get("type", {}).get("shortDetail") or ""
    if state == "pre":
        dt = _event_dt(event).astimezone()
        return f"{dt.strftime('%b')} {dt.day} {dt.strftime('%I:%M%p').lstrip('0')}"
    return status or "WORLD CUP"


def _logo(team, size=18):
    logos = team.get("logos") or []
    url = team.get("logo") or (logos[0].get("href") if logos else "")
    return fetch_logo(url, size=size) if url else None


def _center_text(image, draw, text, y, font, color, x1=0, x2=None):
    x2 = image.width - 1 if x2 is None else x2
    width = draw.textbbox((0, 0), text, font=font)[2]
    draw_sharp_text(image, (x1 + ((x2 - x1 + 1) - width) // 2, y), text, color, font)


def _render_event(event, width):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (width, 32), (3, 8, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors") or []
    away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[0] if competitors else {})
    home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[-1] if competitors else {})
    away_team = away.get("team") or {}
    home_team = home.get("team") or {}
    state = ((competition.get("status") or {}).get("type") or {}).get("state") or "pre"
    score = _score_text(away, home, state)
    status = _status_text(event, state).upper()

    draw.rectangle((0, 0, width - 1, 8), fill=(4, 24, 20))
    draw_sharp_text(image, (1, -3), "WORLD CUP", (70, 220, 125), bold)
    status_w = draw.textbbox((0, 0), status, font=font)[2]
    if status_w <= width - 56:
        draw_sharp_text(image, (width - status_w - 1, -3), status, (165, 190, 185), font)

    if width == 128:
        logo_size = 22
        away_logo = _logo(away_team, logo_size)
        home_logo = _logo(home_team, logo_size)
        if away_logo:
            image.paste(away_logo, (1, 8), away_logo)
        if home_logo:
            image.paste(home_logo, (105, 8), home_logo)
        score_w = draw.textbbox((0, 0), score, font=bold)[2]
        draw.rounded_rectangle((64 - score_w // 2 - 5, 10, 64 + (score_w + 1) // 2 + 5, 23), radius=3, fill=(15, 27, 34), outline=(52, 78, 88))
        _center_text(image, draw, score, 10, bold, (245, 250, 255), 0, 127)
        away_abbr = (away_team.get("abbreviation") or "AWY")[:3].upper()
        home_abbr = (home_team.get("abbreviation") or "HME")[:3].upper()
        draw_sharp_text(image, (26, 13), away_abbr, (245, 250, 255), bold)
        home_w = draw.textbbox((0, 0), home_abbr, font=bold)[2]
        draw_sharp_text(image, (102 - home_w, 13), home_abbr, (245, 250, 255), bold)
        detail = (event.get("name") or event.get("shortName") or "")[:24].upper()
        _center_text(image, draw, detail, 24, font, (130, 160, 170), 24, 103)
    else:
        away_abbr = (away_team.get("abbreviation") or "AWY")[:3].upper()
        home_abbr = (home_team.get("abbreviation") or "HME")[:3].upper()
        draw_sharp_text(image, (1, 10), away_abbr, (245, 250, 255), bold)
        home_w = draw.textbbox((0, 0), home_abbr, font=bold)[2]
        draw_sharp_text(image, (63 - home_w, 10), home_abbr, (245, 250, 255), bold)
        _center_text(image, draw, score, 10, bold, (245, 250, 255), 0, 63)
        _center_text(image, draw, status[:14], 22, font, (130, 160, 170), 0, 63)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def render(options=None):
    opts = options or {}
    favorite = str(opts.get("favoriteTeam") or "").strip().upper()
    try:
        data = _scoreboard()
    except Exception:
        return render_text_webp("WC ERR", (238, 80, 80))
    event = _pick_event(data.get("events") or [], favorite)
    if not event:
        return render_text_webp("NO WC", _COLOR)
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    return _render_event(event, width)
