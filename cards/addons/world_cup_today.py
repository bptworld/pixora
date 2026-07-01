from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from card_utils import draw_sharp_text, fetch_json_with_headers, pixora_local_now, pixora_local_timezone, render_text_webp

CARD_ID = "world_cup_today"
CARD_NAME = "World Cup Today"
CARD_CATEGORY = "Sports"
CARD_DETAIL = "Today's World Cup matches"
CARD_OPTIONS = [
    {
        "key": "city",
        "label": "City",
        "type": "select",
        "default": "all",
        "choices": [
            {"value": "all", "label": "All Cities"},
            {"value": "Atlanta", "label": "Atlanta"},
            {"value": "Boston", "label": "Boston"},
            {"value": "Dallas", "label": "Dallas"},
            {"value": "Guadalajara", "label": "Guadalajara"},
            {"value": "Houston", "label": "Houston"},
            {"value": "Kansas City", "label": "Kansas City"},
            {"value": "Los Angeles", "label": "Los Angeles"},
            {"value": "Mexico City", "label": "Mexico City"},
            {"value": "Miami", "label": "Miami"},
            {"value": "Monterrey", "label": "Monterrey"},
            {"value": "New York", "label": "New York / New Jersey"},
            {"value": "Philadelphia", "label": "Philadelphia"},
            {"value": "San Francisco", "label": "San Francisco Bay Area"},
            {"value": "Seattle", "label": "Seattle"},
            {"value": "Toronto", "label": "Toronto"},
            {"value": "Vancouver", "label": "Vancouver"},
        ],
    },
]

_COLOR = (70, 220, 125)
_WIN = (88, 235, 130)
_LOSS = (245, 86, 96)
_TIE = (255, 210, 90)
_CACHE_SECONDS = 300
_FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"


def _date_range():
    today = pixora_local_now().date()
    start = today - timedelta(days=1)
    end = today + timedelta(days=1)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _scoreboard(seconds=_CACHE_SECONDS):
    start, end = _date_range()
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={start}-{end}"
    return fetch_json_with_headers(
        url,
        seconds=seconds,
        cache_key=f"world_cup_today:scoreboard:{start}:{end}:{seconds}",
    )


def _event_dt(event):
    try:
        return datetime.fromisoformat(str(event.get("date") or "").replace("Z", "+00:00"))
    except Exception:
        return datetime.max.replace(tzinfo=timezone.utc)


def _event_city(event):
    competition = (event.get("competitions") or [{}])[0]
    venue = competition.get("venue") or event.get("venue") or {}
    address = venue.get("address") or {}
    return str(address.get("city") or venue.get("city") or "").strip()


def _city_matches(event, city):
    city = str(city or "all").strip().lower()
    if not city or city == "all":
        return True
    event_city = _event_city(event).lower()
    if city == "new york":
        return "new york" in event_city or "east rutherford" in event_city
    if city == "san francisco":
        return "san francisco" in event_city or "santa clara" in event_city
    if city == "los angeles":
        return "los angeles" in event_city or "inglewood" in event_city
    if city == "boston":
        return "boston" in event_city or "foxborough" in event_city
    if city == "dallas":
        return "dallas" in event_city or "arlington" in event_city
    return city in event_city


def _events_for_today(events, city="all"):
    today = pixora_local_now().date()
    local_tz = pixora_local_timezone()
    todays = [event for event in events if _event_dt(event).astimezone(local_tz).date() == today and _city_matches(event, city)]
    return sorted(todays, key=_event_dt)


def _competitor_team(event, home_away):
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors") or []
    fallback = competitors[0] if home_away == "away" and competitors else competitors[-1] if competitors else {}
    competitor = next((item for item in competitors if item.get("homeAway") == home_away), fallback)
    return competitor.get("team") or {}


def _competitor(event, home_away):
    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors") or []
    fallback = competitors[0] if home_away == "away" and competitors else competitors[-1] if competitors else {}
    return next((item for item in competitors if item.get("homeAway") == home_away), fallback)


def _event_state(event):
    competition = (event.get("competitions") or [{}])[0]
    return ((competition.get("status") or {}).get("type") or {}).get("state") or ""


def _team_label(team, width):
    if width == 128:
        text = team.get("shortDisplayName") or team.get("abbreviation") or team.get("name") or "TEAM"
    else:
        text = team.get("abbreviation") or team.get("shortDisplayName") or team.get("name") or "TM"
    return str(text).upper()


def _limit_team_text(text, limit):
    text = str(text or "").strip().upper()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def _fit_text(draw, text, font, max_width):
    text = str(text or "").strip()
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1].rstrip()
    return text


def _space_width(draw, font):
    try:
        return max(1, int(round(draw.textlength(" ", font=font))))
    except Exception:
        with_space = draw.textbbox((0, 0), "X X", font=font)[2]
        without_space = draw.textbbox((0, 0), "XX", font=font)[2]
    return max(1, with_space - without_space)


def _load_font(name, size):
    from PIL import ImageFont

    for path in (f"assets/fonts/{name}", str(_FONT_DIR / name)):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _event_row(event, draw, font, result_font, width):
    state = _event_state(event)
    if state in ("in", "post"):
        return _score_row(event, draw, result_font, width, final=(state == "post"))
    name_limit = 10 if width == 128 else 3
    away = _limit_team_text(_team_label(_competitor_team(event, "away"), width), name_limit)
    home = _limit_team_text(_team_label(_competitor_team(event, "home"), width), name_limit)
    vs = "VS"
    vs_width = draw.textbbox((0, 0), vs, font=font)[2]
    vs_x = (width - vs_width) // 2
    gap = _space_width(draw, font)
    away_width = max(10, vs_x - gap)
    home_width = max(10, width - (vs_x + vs_width + gap))
    return {
        "away": _fit_text(draw, away, font, away_width),
        "home": _fit_text(draw, home, font, home_width),
        "vs": vs,
        "vs_x": vs_x,
        "home_x": vs_x + vs_width + gap,
        "away_right": vs_x - gap,
    }


def _result_color(competitor, final=True):
    if not final:
        return (245, 250, 255)
    if competitor.get("winner") is True:
        return _WIN
    if competitor.get("winner") is False:
        return _LOSS
    return _TIE


def _score_row(event, draw, font, width, final=False):
    away = _competitor(event, "away")
    home = _competitor(event, "home")
    away_name = _limit_team_text(str((_competitor_team(event, "away").get("abbreviation") or "AWY")).upper(), 3)
    home_name = _limit_team_text(str((_competitor_team(event, "home").get("abbreviation") or "HME")).upper(), 3)
    score = f"{away.get('score', '0')}-{home.get('score', '0')}"
    score_width = draw.textbbox((0, 0), score, font=font)[2]
    score_x = width - score_width - 1
    gap = _space_width(draw, font)

    if width == 64:
        teams_x = 1
        sep = "-"
        max_teams_width = max(8, score_x - teams_x)
        away_width = draw.textbbox((0, 0), away_name, font=font)[2]
        sep_width = draw.textbbox((0, 0), sep, font=font)[2]
        home_width = max(1, max_teams_width - away_width - sep_width)
        return {
            "kind": "score",
            "layout": "teams_left",
            "away": away_name,
            "home": _fit_text(draw, home_name, font, home_width),
            "sep": sep,
            "score": score,
            "teams_x": teams_x,
            "sep_x": teams_x + away_width,
            "home_x": teams_x + away_width + sep_width,
            "score_x": score_x,
            "away_color": _result_color(away, final),
            "home_color": _result_color(home, final),
            "sep_color": (120, 170, 190),
            "score_color": (255, 210, 90) if not final else (245, 250, 255),
        }

    vs = "VS"
    vs_width = draw.textbbox((0, 0), vs, font=font)[2]
    vs_x = 57
    home_x = vs_x + vs_width + gap
    home_width = max(8, score_x - gap - home_x)
    away_width = max(8, vs_x - gap)
    return {
        "kind": "score",
        "away": _fit_text(draw, away_name, font, away_width),
        "home": _fit_text(draw, home_name, font, home_width),
        "vs": vs,
        "score": score,
        "vs_x": vs_x,
        "home_x": home_x,
        "score_x": score_x,
        "away_right": vs_x - gap,
        "away_color": _result_color(away, final),
        "home_color": _result_color(home, final),
        "score_color": (255, 210, 90) if not final else (245, 250, 255),
    }


def _draw_frame(rows, offset, width, font, result_font, bold):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, 32), (3, 8, 12))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, 6), fill=(4, 24, 20))
    title = "WORLD CUP TODAY" if width == 128 else "WC TODAY"
    draw_sharp_text(image, (1, -3), title, _COLOR, bold)

    row_top = 7
    for index, row in enumerate(rows):
        y = row_top + (index * 8) - offset
        if y < row_top or y > 31:
            continue
        if row.get("kind") == "score":
            row_font = result_font
            if row.get("layout") == "teams_left":
                draw_sharp_text(image, (row["teams_x"], y), row["away"], row["away_color"], row_font)
                draw_sharp_text(image, (row["sep_x"], y), row["sep"], row["sep_color"], row_font)
                draw_sharp_text(image, (row["home_x"], y), row["home"], row["home_color"], row_font)
            else:
                away_w = draw.textbbox((0, 0), row["away"], font=row_font)[2]
                draw_sharp_text(image, (row["away_right"] - away_w, y), row["away"], row["away_color"], row_font)
                draw_sharp_text(image, (row["vs_x"], y), row["vs"], (180, 190, 195), row_font)
                draw_sharp_text(image, (row["home_x"], y), row["home"], row["home_color"], row_font)
            draw_sharp_text(image, (row["score_x"], y), row["score"], row["score_color"], row_font)
        else:
            color = (245, 250, 255) if index % 2 == 0 else (205, 224, 222)
            away_w = draw.textbbox((0, 0), row["away"], font=font)[2]
            draw_sharp_text(image, (row["away_right"] - away_w, y), row["away"], color, font)
            draw_sharp_text(image, (row["vs_x"], y), row["vs"], _COLOR, font)
            draw_sharp_text(image, (row["home_x"], y), row["home"], color, font)
    return image


def _render_rows(events, width):
    from PIL import Image, ImageDraw, ImageFont

    font = _load_font("Silkscreen-Regular.ttf", 8)
    result_font = _load_font("Silkscreen-Regular.ttf", 8)
    bold = _load_font("Silkscreen-Regular.ttf", 8)

    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    rows = [_event_row(event, dummy, font, result_font, width) for event in events]
    rows = [row for row in rows if row]
    if not rows:
        return render_text_webp("NO WC TODAY", (160, 170, 180))

    max_offset = max(0, (len(rows) - 3) * 8)
    offsets = [0] if max_offset == 0 else [0] + list(range(1, max_offset + 1))
    frames = [_draw_frame(rows, offset, width, font, result_font, bold) for offset in offsets]

    out = BytesIO()
    durations = [2500] if len(frames) == 1 else [2000] + [120 for _ in frames[1:]]
    if len(durations) > 1:
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


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    city = opts.get("city") or "all"
    try:
        data = _scoreboard()
    except Exception:
        return render_text_webp("WC ERR", (238, 80, 80))
    events = _events_for_today(data.get("events") or [], city)
    live = any(_event_state(event) == "in" for event in events)
    return {"body": _render_rows(events, width), "_sports_live": live}
