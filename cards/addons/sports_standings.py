from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import urllib.request

from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "sports_standings"
CARD_NAME = "Sports Standings"
CARD_DETAIL = "Top teams from ESPN standings"
CARD_OPTIONS = [
    {
        "key": "league",
        "label": "League",
        "type": "select",
        "default": "mlb",
        "choices": [
            {"value": "mlb", "label": "MLB"},
            {"value": "nba", "label": "NBA"},
            {"value": "nhl", "label": "NHL"},
            {"value": "nfl", "label": "NFL"},
            {"value": "wnba", "label": "WNBA"},
        ],
    },
    {
        "key": "group",
        "label": "Group",
        "type": "select",
        "default": "auto",
        "choices": [
            {"value": "auto", "label": "Default"},
            {"value": "al_east", "label": "AL East"},
            {"value": "al_central", "label": "AL Central"},
            {"value": "al_west", "label": "AL West"},
            {"value": "nl_east", "label": "NL East"},
            {"value": "nl_central", "label": "NL Central"},
            {"value": "nl_west", "label": "NL West"},
            {"value": "al", "label": "American League"},
            {"value": "nl", "label": "National League"},
        ],
    },
]

LEAGUES = {
    "mlb": ("MLB", "https://site.web.api.espn.com/apis/v2/sports/baseball/mlb/standings", (117, 231, 214)),
    "nba": ("NBA", "https://site.web.api.espn.com/apis/v2/sports/basketball/nba/standings", (245, 150, 65)),
    "nhl": ("NHL", "https://site.web.api.espn.com/apis/v2/sports/hockey/nhl/standings", (80, 220, 255)),
    "nfl": ("NFL", "https://site.web.api.espn.com/apis/v2/sports/football/nfl/standings", (80, 150, 255)),
    "wnba": ("WNBA", "https://site.web.api.espn.com/apis/v2/sports/basketball/wnba/standings", (255, 170, 210)),
    "college_football": ("CFB", "https://site.web.api.espn.com/apis/v2/sports/football/college-football/standings", (80, 150, 255)),
    "mens_college_basketball": ("MCBB", "https://site.web.api.espn.com/apis/v2/sports/basketball/mens-college-basketball/standings", (245, 150, 65)),
    "womens_college_basketball": ("WCBB", "https://site.web.api.espn.com/apis/v2/sports/basketball/womens-college-basketball/standings", (255, 170, 210)),
    "mens_college_hockey": ("NCAA H", "https://site.web.api.espn.com/apis/v2/sports/hockey/mens-college-hockey/standings", (80, 220, 255)),
    "womens_college_hockey": ("W NCAA H", "https://site.web.api.espn.com/apis/v2/sports/hockey/womens-college-hockey/standings", (255, 150, 210)),
    "college_baseball": ("CBASE", "https://site.web.api.espn.com/apis/v2/sports/baseball/college-baseball/standings", (95, 210, 130)),
    "womens_college_volleyball": ("WVB", "https://site.web.api.espn.com/apis/v2/sports/volleyball/womens-college-volleyball/standings", (255, 185, 85)),
}
_CACHE = {}
_STANDINGS_HOLD_MS = 2000
_STANDINGS_SCROLL_MS = 120

MLB_DIVISIONS = {
    "al_east": {"BAL", "BOS", "NYY", "TB", "TOR"},
    "al_central": {"CHW", "CLE", "DET", "KC", "MIN"},
    "al_west": {"ATH", "HOU", "LAA", "SEA", "TEX"},
    "nl_east": {"ATL", "MIA", "NYM", "PHI", "WSH"},
    "nl_central": {"CHC", "CIN", "MIL", "PIT", "STL"},
    "nl_west": {"ARI", "COL", "LAD", "SD", "SF"},
}

MLB_GROUP_ALIASES = {
    "east": "al_east",
    "al-east": "al_east",
    "ale": "al_east",
    "american_east": "al_east",
    "central": "al_central",
    "al-central": "al_central",
    "alc": "al_central",
    "west": "al_west",
    "al-west": "al_west",
    "alw": "al_west",
    "nl-east": "nl_east",
    "nle": "nl_east",
    "national_east": "nl_east",
    "nl-central": "nl_central",
    "nlc": "nl_central",
    "nl-west": "nl_west",
    "nlw": "nl_west",
    "american": "al",
    "national": "nl",
}


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


def _fetch(url):
    now = datetime.now(timezone.utc)
    cached = _CACHE.get(url)
    if cached and cached["expires"] > now:
        return cached["data"]
    request = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))
    _CACHE[url] = {"data": data, "expires": now + timedelta(seconds=1800)}
    return data


def _stat(entry, *names):
    names = {n.lower() for n in names}
    for stat in entry.get("stats", []):
        if str(stat.get("type", "")).lower() in names or str(stat.get("abbreviation", "")).lower() in names:
            return stat.get("displayValue", "")
    return ""


def _compact_dash(value):
    return str(value).replace(" - ", "-")


def _format_games_back(value):
    text = str(value).strip()
    if not text or text == "-":
        return "-"
    try:
        number = float(text)
        return f"{number:.1f}"
    except Exception:
        return text


def _pick_child(children, group):
    if not children:
        return None
    if group == "auto":
        for child in children:
            if (((child or {}).get("standings") or {}).get("entries") or []):
                return child
        return children[0]
    wanted = {
        "al": ("american", "al"),
        "nl": ("national", "nl"),
        "al_east": ("american", "al"),
        "al_central": ("american", "al"),
        "al_west": ("american", "al"),
        "nl_east": ("national", "nl"),
        "nl_central": ("national", "nl"),
        "nl_west": ("national", "nl"),
    }.get(group, ())
    for child in children:
        text = " ".join(str(child.get(k, "")) for k in ("name", "abbreviation", "shortName")).lower()
        if any(term in text for term in wanted):
            return child
    generic_terms = [term for term in str(group).replace("_", " ").replace("-", " ").split() if term]
    if generic_terms:
        for child in children:
            text = " ".join(str(child.get(k, "")) for k in ("name", "abbreviation", "shortName")).lower().replace("-", " ")
            if all(term in text for term in generic_terms):
                return child
    return children[0]


def _normalize_group(league_key, group):
    group = str(group or "auto").strip().lower().replace(" ", "_")
    if league_key == "mlb":
        return MLB_GROUP_ALIASES.get(group, group)
    return group


def _standings(opts):
    league_key = str((opts or {}).get("league", "mlb")).lower()
    group = _normalize_group(league_key, (opts or {}).get("group", "auto"))
    if league_key == "soccer":
        soccer_league = str((opts or {}).get("soccerLeague") or "usa.1").strip() or "usa.1"
        soccer_titles = {
            "eng.1": "EPL",
            "usa.1": "MLS",
            "esp.1": "LALIGA",
            "ita.1": "SERIEA",
            "ger.1": "BUND",
            "fra.1": "LIGUE1",
            "usa.nwsl": "NWSL",
        }
        title = soccer_titles.get(soccer_league, "SOCCER")
        url = f"https://site.web.api.espn.com/apis/v2/sports/soccer/{soccer_league}/standings"
        color = (80, 220, 170)
    else:
        title, url, color = LEAGUES.get(league_key, LEAGUES["mlb"])
    data = _fetch(url)
    child = _pick_child(data.get("children", []), group)
    entries = ((child or {}).get("standings") or {}).get("entries", [])
    if league_key == "mlb" and group in MLB_DIVISIONS:
        wanted = MLB_DIVISIONS[group]
        entries = [entry for entry in entries if (entry.get("team", {}).get("abbreviation") or "").upper() in wanted]
    rows = []
    for rank, entry in enumerate(entries, start=1):
        team = entry.get("team", {})
        abbr = team.get("abbreviation") or team.get("shortDisplayName") or "?"
        wins = _stat(entry, "wins", "w")
        losses = _stat(entry, "losses", "l")
        ties = _stat(entry, "ties", "t")
        gb = _stat(entry, "gamesbehind", "gb")
        pts = _stat(entry, "points", "pts")
        record = f"{wins}-{losses}" if wins or losses else pts
        if ties and ties != "0":
            record += f"-{ties}"
        record = _compact_dash(record)
        right = "GB--" if gb in ("", "-") else f"GB-{_format_games_back(gb)}"
        if league_key in ("nhl", "soccer") and pts:
            right = f"PTS-{pts}"
        rows.append((str(rank), abbr[:4].upper(), record[:10], right[:10]))
    return title, color, rows[:24]


def _draw_header(image, title, color, font, bold, width=64):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, 6), fill=(6, 18, 26))
    if width == 128:
        text = f"{title} STANDINGS"
        tw = _tight_text_width(text, bold, spacing=-1)
        _draw_tight_text(image, ((width - tw) // 2, -3), text, color, bold, spacing=-1)
    else:
        _draw_tight_text(image, (1, -3), title, color, bold, spacing=-1)
        _draw_tight_text(image, (24, -3), "STAND", (150, 170, 185), font, spacing=-1)


def _draw_rows(image, rows, color, font, bold, offset=0, width=64):
    for idx, abbr, record, right in rows:
        y = 7 + ((int(idx) - 1) * 8) - offset
        if y < -8 or y > 31:
            continue
        if width == 128:
            _draw_tight_text(image, (2, y), idx[:2], color, font, spacing=-1)
            _draw_tight_text(image, (13, y), abbr, (245, 250, 255), bold, spacing=-1)
            _draw_tight_text(image, (46, y), record, (190, 205, 218), font, spacing=-1)
            right_w = _tight_text_width(right, font, spacing=-1)
            _draw_tight_text(image, (127 - right_w, y), right, (145, 165, 182), font, spacing=-1)
            continue
        x = 1
        _draw_tight_text(image, (x, y), idx, color, font, spacing=-1)
        x += max(1, _tight_text_width(idx, font, spacing=-1))
        _draw_tight_text(image, (x, y), abbr, (245, 250, 255), bold, spacing=-1)
        right_x = max(29, 64 - _tight_text_width("GB-00.0", font, spacing=-1))
        _draw_tight_text(image, (right_x, y), right, (145, 165, 182), font, spacing=-1)


def _render_frame(title, color, rows, font, bold, offset=0, width=64):
    from PIL import Image

    image = Image.new("RGB", (width, 32), (0, 5, 12))
    _draw_rows(image, rows, color, font, bold, offset, width=width)
    _draw_header(image, title, color, font, bold, width=width)
    return image


def render(options=None):
    from PIL import ImageFont
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64

    try:
        title, color, rows = _standings(opts)
    except Exception:
        return render_text_webp("STAND ERR", (238, 80, 80))
    if not rows:
        return render_text_webp("NO STAND", (160, 160, 160))

    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    out = BytesIO()
    if len(rows) <= 3:
        image = _render_frame(title, color, rows, font, bold, 0, width=width)
        image.save(out, "WEBP", lossless=True, quality=100)
        return out.getvalue()

    max_offset = max(0, (len(rows) - 3) * 8)
    offsets = [0] + list(range(1, max_offset + 1))
    top_frame = _render_frame(title, color, rows, font, bold, 0, width=width)
    scroll_frames = [_render_frame(title, color, rows, font, bold, offset, width=width) for offset in offsets[1:]]
    bottom_frame = _render_frame(title, color, rows, font, bold, max_offset, width=width)
    frames = [top_frame] + scroll_frames + [bottom_frame]
    durations = [_STANDINGS_HOLD_MS] + [_STANDINGS_SCROLL_MS for _ in scroll_frames] + [_STANDINGS_HOLD_MS]
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
    return {"body": out.getvalue(), "_frame_durations_ms": durations}
