from io import BytesIO
import math
import urllib.request
from datetime import datetime, timedelta, timezone

from card_utils import (
    cached_priority_graphic,
    draw_sharp_text,
    fetch_json_url,
    fetch_sport_scoreboard,
    pick_sport_event,
    priority_graphic_key,
    render_sport_card,
    warm_priority_graphic,
)

from _sports_breaking import SCORE_ANIMATION_TEAMS_OPTION, animation_competitors, graphic_target_option, render_score_alert_frames
from _sports_wall import _fetch_headshot, fit_font as wall_fit_font, render_wall_score_frames

CARD_ID = "mlb"
CARD_NAME = "MLB Scores"
CARD_DETAIL = "Live ESPN scoreboard"
CARD_OPTIONS = [
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "BOS",
        "choices": [
            {"value": "ARI", "label": "Arizona Diamondbacks"},
            {"value": "ATH", "label": "Athletics"},
            {"value": "ATL", "label": "Atlanta Braves"},
            {"value": "BAL", "label": "Baltimore Orioles"},
            {"value": "BOS", "label": "Boston Red Sox"},
            {"value": "CHC", "label": "Chicago Cubs"},
            {"value": "CHW", "label": "Chicago White Sox"},
            {"value": "CIN", "label": "Cincinnati Reds"},
            {"value": "CLE", "label": "Cleveland Guardians"},
            {"value": "COL", "label": "Colorado Rockies"},
            {"value": "DET", "label": "Detroit Tigers"},
            {"value": "HOU", "label": "Houston Astros"},
            {"value": "KC", "label": "Kansas City Royals"},
            {"value": "LAA", "label": "Los Angeles Angels"},
            {"value": "LAD", "label": "Los Angeles Dodgers"},
            {"value": "MIA", "label": "Miami Marlins"},
            {"value": "MIL", "label": "Milwaukee Brewers"},
            {"value": "MIN", "label": "Minnesota Twins"},
            {"value": "NYM", "label": "New York Mets"},
            {"value": "NYY", "label": "New York Yankees"},
            {"value": "PHI", "label": "Philadelphia Phillies"},
            {"value": "PIT", "label": "Pittsburgh Pirates"},
            {"value": "SD", "label": "San Diego Padres"},
            {"value": "SF", "label": "San Francisco Giants"},
            {"value": "SEA", "label": "Seattle Mariners"},
            {"value": "STL", "label": "St. Louis Cardinals"},
            {"value": "TB", "label": "Tampa Bay Rays"},
            {"value": "TEX", "label": "Texas Rangers"},
            {"value": "TOR", "label": "Toronto Blue Jays"},
            {"value": "WSH", "label": "Washington Nationals"},
        ],
    },
    {
        "key": "runAnimationTarget",
        "label": "Run Scored Animation",
        "type": "select",
        "default": "device",
        "choices": [
            {"value": "device", "label": "Single Device"},
            {"value": "group_wall", "label": "Group Wall"},
        ],
    }
]
CARD_OPTIONS.append(graphic_target_option("gameStartAnimationTarget", "Start of Game Graphic"))
CARD_OPTIONS.append(graphic_target_option("scoringPlayAnimationTarget", "RBI / Scoring Play Graphic"))
CARD_OPTIONS.append(graphic_target_option("homeRunAnimationTarget", "Home Run Graphic"))
CARD_OPTIONS.append(graphic_target_option("walkOffAnimationTarget", "Walk-Off / Game Winner Graphic"))
CARD_OPTIONS.append(graphic_target_option("nowBattingAnimationTarget", "Now Batting Graphic"))
CARD_OPTIONS.append(dict(SCORE_ANIMATION_TEAMS_OPTION))

_URL = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
_CACHE = {"expires": datetime.min.replace(tzinfo=timezone.utc), "body": b""}
_SUMMARY_CACHE = {}
_COLOR = (117, 231, 214)
_RUN_STATE = {}
_GAME_STATE = {}
_BATTING_STATE = {}
_BATTING_PREWARM_STATE = {}
_LOGO_CACHE = {}


def _hex_color(value, fallback=_COLOR):
    value = str(value or "").strip().lstrip("#")
    if len(value) == 6:
        try:
            return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            pass
    return fallback


def _fetch_big_logo(url):
    url = str(url or "").strip()
    if not url:
        return None
    if url in _LOGO_CACHE:
        return _LOGO_CACHE[url]
    try:
        from PIL import Image
        request = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1"})
        with urllib.request.urlopen(request, timeout=5) as response:
            data = response.read()
        logo = Image.open(BytesIO(data)).convert("RGBA")
        logo.thumbnail((22, 22), Image.LANCZOS)
        canvas = Image.new("RGBA", (22, 22), (0, 0, 0, 0))
        canvas.alpha_composite(logo, ((22 - logo.width) // 2, (22 - logo.height) // 2))
        _LOGO_CACHE[url] = canvas
        return canvas
    except Exception:
        return None


def _draw_baseball(draw, cx, cy, size):
    r = max(1, size // 2)
    if size <= 2:
        draw.point((int(cx), int(cy)), fill=(245, 248, 238))
        return
    box = (int(cx - r), int(cy - r), int(cx + r), int(cy + r))
    draw.ellipse(box, fill=(246, 246, 232), outline=(210, 210, 200))
    red = (210, 42, 48)
    if size >= 7:
        draw.arc((cx - r + 1, cy - r, cx + 1, cy + r), 285, 75, fill=red)
        draw.arc((cx - 1, cy - r, cx + r - 1, cy + r), 105, 255, fill=red)
        for dx, dy in [(-2, -2), (-3, 1), (2, -2), (3, 1)]:
            draw.point((int(cx + dx), int(cy + dy)), fill=red)


_BIG_RUN = {
    "R": ["1110", "1001", "1001", "1110", "1010", "1001", "1001"],
    "U": ["1001", "1001", "1001", "1001", "1001", "1001", "1111"],
    "N": ["1001", "1101", "1101", "1011", "1011", "1001", "1001"],
}


def _draw_big_run(draw, x, y, color):
    scale = 1
    gap = 1
    cursor = x
    for letter in "RUN":
        pattern = _BIG_RUN[letter]
        for row, bits in enumerate(pattern):
            for col, bit in enumerate(bits):
                if bit == "1":
                    px = cursor + col
                    py = y + row
                    draw.point((px, py), fill=color)
                    draw.point((px + 1, py), fill=color)
        cursor += len(pattern[0]) * scale + gap


def _draw_logo_or_fallback(image, draw, team, color, side="left", size=22):
    width = image.width
    size = max(14, min(22, int(size or 22)))
    x = 1 if side != "right" else max(1, width - size - 1)
    y = max(4, (32 - size) // 2)
    logo = _fetch_big_logo(team.get("logo", ""))
    if logo:
        if logo.width != size or logo.height != size:
            from PIL import Image

            logo = logo.resize((size, size), Image.LANCZOS)
        image.alpha_composite(logo, (x, y))
        return
    draw.ellipse((x, y, x + size - 1, y + size - 1), outline=color, width=2)
    abbr = (team.get("abbreviation") or team.get("shortDisplayName") or "MLB")[:3].upper()
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8 if size >= 20 else 6)
    except Exception:
        from PIL import ImageFont
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), abbr, font=font)
    draw_sharp_text(image, (x + size // 2 - (bbox[2] - bbox[0]) // 2, y + size // 2 - 4), abbr, color, font)


def _run_animation_text(kind):
    kind = str(kind or "run").lower()
    if kind in ("grand_slam", "grand slam", "slam"):
        return "GRAND", "SLAM"
    if kind in ("home_run", "homerun", "homer", "hr"):
        return "HOME", "RUN"
    if kind in ("walk_off", "walk-off"):
        return "WALK", "OFF"
    if kind in ("win", "winner", "game_winner", "game-winner"):
        return "GAME", "WIN"
    return "RUN", "SCORED"


def _home_run_headline(kind):
    kind = str(kind or "").lower()
    if kind in ("grand_slam", "grand slam", "slam"):
        return "GRAND SLAM"
    return "HOME RUN"


def _draw_home_run_frame_layout(image, draw, team, kind, color, alt, flash=False):
    width = image.width
    if width < 96:
        return 2, width - 2
    edge_size = 22 if width >= 96 else 16
    headshot = _fetch_headshot(team.get("playerHeadshot"), edge_size)
    left_edge = 2
    if headshot:
        hy = max(4, (32 - headshot.height) // 2)
        draw.rounded_rectangle((1, hy - 1, 2 + headshot.width, hy + headshot.height), radius=2, fill=(3, 9, 13, 255), outline=(alt if flash else color) + (255,))
        image.alpha_composite(headshot, (2, hy))
        left_edge = 4 + headshot.width
    _draw_logo_or_fallback(image, draw, team, color, side="right", size=edge_size)
    right_edge = max(left_edge + 14, width - edge_size - 4)
    return left_edge, right_edge


def _draw_home_run_middle_text(image, draw, team, kind, color, alt, show_player=True):
    width = image.width
    if width < 96:
        left_edge = 2
        right_edge = width - 2
    else:
        edge_size = 22
        left_edge = edge_size + 5 if team.get("playerHeadshot") else 2
        right_edge = width - edge_size - 5
    lane_w = max(10, right_edge - left_edge)
    event_text = _home_run_headline(kind)
    player_name = _compact_player_name(team.get("playerName"), "")
    event_display = "HR" if width < 96 and event_text == "HOME RUN" else "SLAM" if width < 96 and event_text == "GRAND SLAM" else event_text
    name_display = player_name[:8] if width < 96 else player_name
    event_font = _fit_regular_font(event_display, lane_w, (10, 9, 8, 7, 6))
    name_font = _fit_regular_font(name_display, lane_w, (8, 7, 6, 5))
    event_bbox = draw.textbbox((0, 0), event_display, font=event_font)
    event_x = left_edge + max(0, (lane_w - (event_bbox[2] - event_bbox[0])) // 2)
    if show_player and name_display:
        name_bbox = draw.textbbox((0, 0), name_display, font=name_font)
        name_x = left_edge + max(0, (lane_w - (name_bbox[2] - name_bbox[0])) // 2)
        draw_sharp_text(image, (name_x, 4 - name_bbox[1]), name_display, (245, 248, 236), name_font)
        draw_sharp_text(image, (event_x, 17 - event_bbox[1]), event_display, alt if alt != (255, 255, 255) else color, event_font)
    else:
        draw_sharp_text(image, (event_x, 10 - event_bbox[1]), event_display, alt if alt != (255, 255, 255) else color, event_font)


def _compact_player_name(name, fallback="BATTER"):
    parts = [part for part in str(name or "").replace(".", "").split() if part]
    if not parts:
        return fallback
    if len(parts) == 1:
        return parts[0].upper()
    return parts[-1].upper()


def _display_player_name(name, width):
    name = str(name or "").strip()
    if not name:
        return "Batter"
    if width <= 72:
        return _compact_player_name(name).title()
    return name


def _font_from_file(filename, size):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(f"cards/assets/fonts/{filename}", size)
    except Exception:
        return ImageFont.load_default()


def _fit_regular_font(text, max_width, sizes):
    from PIL import Image, ImageDraw

    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    fallback = _font_from_file("PixelifySans.ttf", sizes[-1] if sizes else 8)
    for size in sizes:
        font = _font_from_file("PixelifySans.ttf", size)
        bbox = probe.textbbox((0, 0), str(text or ""), font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
    return fallback


def _format_batting_stats(stats, width):
    stats = stats if isinstance(stats, dict) else {}
    h_ab = str(stats.get("H-AB") or "").strip()
    avg = str(stats.get("AVG") or "").strip()
    rbi = str(stats.get("RBI") or "").strip()
    hr = str(stats.get("HR") or "").strip()
    parts = []
    if h_ab:
        parts.append(h_ab)
    if rbi and rbi not in ("0", "0.0"):
        parts.append(f"RBI {rbi}")
    if hr and hr not in ("0", "0.0") and width >= 100:
        parts.append(f"HR {hr}")
    if avg:
        parts.append(f"AVG {avg}" if width >= 96 else avg)
    return "  ".join(parts) or "AT BAT"


def _render_now_batting_frames(team):
    from PIL import Image, ImageDraw

    color = _hex_color(team.get("color"), _COLOR)
    alt = _hex_color(team.get("alternateColor"), (255, 255, 255))
    if alt == (255, 255, 255):
        alt = (255, 224, 96)
    try:
        width = int(team.get("_width") or 64)
    except Exception:
        width = 64
    width = max(64, min(512, width))

    image = Image.new("RGBA", (width, 32), (1, 5, 8, 255))
    draw = ImageDraw.Draw(image)
    for y in range(0, 32, 2):
        shade = 8 + (y // 2)
        draw.line((0, y, width - 1, y), fill=(1, shade, 13, 255))
    draw.rectangle((0, 0, width - 1, 2), fill=color + (255,))
    draw.line((0, 31, width - 1, 31), fill=tuple(max(12, c // 3) for c in color) + (255,))

    if width < 96:
        text_left = 2
        text_right = width - 2
        text_width = max(28, text_right - text_left)
        label = "AT BAT"
        name = _display_player_name(team.get("playerName"), width)
        stats = _format_batting_stats(team.get("playerStats"), width)
        label_font = _font_from_file("PixelifySans-Bold.ttf", 6)
        name_font = _fit_regular_font(name, text_width, (9, 8, 7, 6))
        stats_font = _fit_regular_font(stats, text_width, (6, 5))
        label_bbox = draw.textbbox((0, 0), label, font=label_font)
        name_bbox = draw.textbbox((0, 0), name, font=name_font)
        stats_bbox = draw.textbbox((0, 0), stats, font=stats_font)
        label_x = text_left + max(0, (text_width - (label_bbox[2] - label_bbox[0])) // 2)
        name_x = text_left + max(0, (text_width - (name_bbox[2] - name_bbox[0])) // 2)
        stats_x = text_left + max(0, (text_width - (stats_bbox[2] - stats_bbox[0])) // 2)
        draw_sharp_text(image, (label_x, 4 - label_bbox[1]), label, color, label_font)
        draw_sharp_text(image, (name_x, 13 - name_bbox[1]), name, (245, 248, 250), name_font)
        draw_sharp_text(image, (stats_x, 23 - stats_bbox[1]), stats, (255, 255, 255), stats_font)
        return [image.convert("RGB")], [5000]

    headshot = _fetch_headshot(team.get("playerHeadshot"), 25)
    if headshot:
        hx = 2
        hy = 5
        draw.rounded_rectangle((hx - 1, hy - 1, hx + headshot.width, hy + headshot.height), radius=2, fill=(3, 9, 13, 255), outline=color + (255,))
        image.alpha_composite(headshot, (hx, hy))
        text_left = hx + headshot.width + 4
    else:
        _draw_logo_or_fallback(image, draw, team, color)
        text_left = 27

    text_right = width - 2
    text_width = max(28, text_right - text_left)
    name = _display_player_name(team.get("playerName"), width)
    stats = _format_batting_stats(team.get("playerStats"), width)
    name_font = _fit_regular_font(name, text_width, (12, 11, 10, 9, 8))
    stats_font = _fit_regular_font(stats, text_width, (8, 7, 6, 5))
    name_bbox = draw.textbbox((0, 0), name, font=name_font)
    stats_bbox = draw.textbbox((0, 0), stats, font=stats_font)
    name_x = text_left + max(0, (text_width - (name_bbox[2] - name_bbox[0])) // 2)
    stats_x = text_left + max(0, (text_width - (stats_bbox[2] - stats_bbox[0])) // 2)
    draw_sharp_text(image, (name_x, 6 - name_bbox[1]), name, (245, 248, 250), name_font)
    draw_sharp_text(image, (stats_x, 19 - stats_bbox[1]), stats, (255, 255, 255), stats_font)

    return [image.convert("RGB")], [5000]


def _render_rbi_card(team, kind="rbi"):
    from PIL import Image, ImageDraw

    color = _hex_color(team.get("color"), _COLOR)
    alt = _hex_color(team.get("alternateColor"), (255, 255, 255))
    if alt == (255, 255, 255):
        alt = (255, 224, 96)
    try:
        width = int(team.get("_width") or 64)
    except Exception:
        width = 64
    width = max(64, min(512, width))

    image = Image.new("RGBA", (width, 32), (1, 5, 8, 255))
    draw = ImageDraw.Draw(image)
    for y in range(0, 32, 2):
        shade = 8 + (y // 2)
        draw.line((0, y, width - 1, y), fill=(1, shade, 13, 255))
    draw.rectangle((0, 0, width - 1, 2), fill=color + (255,))
    draw.line((0, 31, width - 1, 31), fill=tuple(max(12, c // 3) for c in color) + (255,))

    headshot = _fetch_headshot(team.get("playerHeadshot"), 24) if width >= 96 else None
    if headshot:
        hx = 2
        hy = 6
        draw.rounded_rectangle((hx - 1, hy - 1, hx + headshot.width, hy + headshot.height), radius=2, fill=(3, 9, 13, 255), outline=color + (255,))
        image.alpha_composite(headshot, (hx, hy))
        text_left = hx + headshot.width + 4
    elif width >= 96:
        _draw_logo_or_fallback(image, draw, team, color)
        text_left = 27
    else:
        text_left = 2

    text_right = width - 2
    text_width = max(28, text_right - text_left)
    headline = "RBI" if str(kind or "").lower() in ("rbi", "scoring_play", "scoring-play") else "RUN"
    name = _display_player_name(team.get("playerName"), width)
    if not team.get("playerName"):
        name = "Scoring Play"
    stats = _format_batting_stats(team.get("playerStats"), width)
    if stats == "AT BAT":
        stats = "RUN SCORED"

    headline_font = _font_from_file("PixelifySans-Bold.ttf", 12 if width >= 96 else 9)
    name_font = _fit_regular_font(name, text_width, (10, 9, 8, 7) if width >= 96 else (8, 7, 6))
    stats_font = _fit_regular_font(stats, text_width, (7, 6, 5) if width >= 96 else (6, 5))
    headline_bbox = draw.textbbox((0, 0), headline, font=headline_font)
    name_bbox = draw.textbbox((0, 0), name, font=name_font)
    stats_bbox = draw.textbbox((0, 0), stats, font=stats_font)
    headline_x = text_left + max(0, (text_width - (headline_bbox[2] - headline_bbox[0])) // 2)
    name_x = text_left + max(0, (text_width - (name_bbox[2] - name_bbox[0])) // 2)
    stats_x = text_left + max(0, (text_width - (stats_bbox[2] - stats_bbox[0])) // 2)
    if width < 96:
        headline_color = alt if sum(alt) >= 140 else color
        draw_sharp_text(image, (headline_x, 4 - headline_bbox[1]), headline, headline_color, headline_font)
        draw_sharp_text(image, (name_x, 13 - name_bbox[1]), name, (245, 248, 250), name_font)
        draw_sharp_text(image, (stats_x, 23 - stats_bbox[1]), stats, (255, 255, 255), stats_font)
    else:
        draw_sharp_text(image, (headline_x, 2 - headline_bbox[1]), headline, alt, headline_font)
        draw_sharp_text(image, (name_x, 15 - name_bbox[1]), name, (245, 248, 250), name_font)
        draw_sharp_text(image, (stats_x, 24 - stats_bbox[1]), stats, (255, 255, 255), stats_font)

    out = BytesIO()
    image.convert("RGB").save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _render_compact_moment_card(team, kind="run"):
    from PIL import Image, ImageDraw

    color = _hex_color(team.get("color"), _COLOR)
    alt = _hex_color(team.get("alternateColor"), (255, 255, 255))
    if alt == (255, 255, 255):
        alt = (255, 224, 96)
    try:
        width = int(team.get("_width") or 64)
    except Exception:
        width = 64
    width = max(64, min(95, width))

    headline_map = {
        "home_run": "HOME RUN",
        "homerun": "HOME RUN",
        "homer": "HOME RUN",
        "hr": "HOME RUN",
        "grand_slam": "GRAND SLAM",
        "grand slam": "GRAND SLAM",
        "slam": "GRAND SLAM",
        "walk_off": "WALK OFF",
        "walk-off": "WALK OFF",
        "win": "GAME WIN",
        "winner": "GAME WIN",
    }
    headline = headline_map.get(str(kind or "run").lower(), "RUN")
    name = _display_player_name(team.get("playerName"), width)
    if not team.get("playerName"):
        name = "Scoring Play"
    stats = _format_batting_stats(team.get("playerStats"), width)
    if stats == "AT BAT":
        stats = "SCORED"

    image = Image.new("RGBA", (width, 32), (1, 5, 8, 255))
    draw = ImageDraw.Draw(image)
    for y in range(0, 32, 2):
        shade = 8 + (y // 2)
        draw.line((0, y, width - 1, y), fill=(1, shade, 13, 255))
    draw.rectangle((0, 0, width - 1, 2), fill=color + (255,))
    draw.line((0, 31, width - 1, 31), fill=tuple(max(12, c // 3) for c in color) + (255,))

    text_left = 2
    text_width = width - 4
    headline_font = _fit_regular_font(headline, text_width, (8, 7, 6))
    name_font = _fit_regular_font(name, text_width, (8, 7, 6))
    stats_font = _fit_regular_font(stats, text_width, (6, 5))
    headline_bbox = draw.textbbox((0, 0), headline, font=headline_font)
    name_bbox = draw.textbbox((0, 0), name, font=name_font)
    stats_bbox = draw.textbbox((0, 0), stats, font=stats_font)
    headline_x = text_left + max(0, (text_width - (headline_bbox[2] - headline_bbox[0])) // 2)
    name_x = text_left + max(0, (text_width - (name_bbox[2] - name_bbox[0])) // 2)
    stats_x = text_left + max(0, (text_width - (stats_bbox[2] - stats_bbox[0])) // 2)
    headline_color = alt if sum(alt) >= 140 else color
    draw_sharp_text(image, (headline_x, 4 - headline_bbox[1]), headline, headline_color, headline_font)
    draw_sharp_text(image, (name_x, 13 - name_bbox[1]), name, (245, 248, 250), name_font)
    draw_sharp_text(image, (stats_x, 23 - stats_bbox[1]), stats, (255, 255, 255), stats_font)

    out = BytesIO()
    image.convert("RGB").save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _render_run_animation_frames(team, kind="run"):
    from PIL import Image, ImageDraw, ImageFont

    color = _hex_color(team.get("color"), _COLOR)
    alt = _hex_color(team.get("alternateColor"), (255, 255, 255))
    try:
        width = int(team.get("_width") or 64)
    except Exception:
        width = 64
    width = max(64, min(512, width))
    if str(kind or "").lower() == "now_batting":
        return _render_now_batting_frames(team)
    if (team or {}).get("_wall"):
        return render_wall_score_frames(team, kind, sport="baseball", default_label="MLB")
    if str(kind or "").lower() in ("game_start", "game_end", "inning_start", "inning_end"):
        return render_score_alert_frames({**(team or {}), "_sport": "baseball"}, kind)
    frames = []
    durations = []
    try:
        font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        run_font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 9)
    except Exception:
        font = run_font = ImageFont.load_default()
    kind_key = str(kind or "run").lower()
    is_home_run = kind_key in ("home_run", "homerun", "homer", "hr", "grand_slam", "grand slam", "slam")

    for i in range(20):
        t = i / 19
        image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        if is_home_run:
            _draw_home_run_frame_layout(image, draw, team, kind_key, color, alt, flash=bool(i % 2))
        else:
            _draw_logo_or_fallback(image, draw, team, color)
        draw.line((0, 31, width - 1, 31), fill=tuple(max(0, c // 3) for c in color) + (255,))

        travel = max(56, width - 8)
        x = 3 + (travel * t)
        y = 29 - (25 * math.sin(t * math.pi / 2))
        size = max(1, int(1 + 9 * t))
        for trail in range(1, 4):
            tt = max(0, t - trail * 0.055)
            tx = 3 + (travel * tt)
            ty = 29 - (25 * math.sin(tt * math.pi / 2))
            fade = 90 - trail * 18
            draw.point((int(tx), int(ty)), fill=(255, 255, 255, fade))
        _draw_baseball(draw, x, y, size)
        frames.append(image.convert("RGB"))
        durations.append(45)

    ball_x, ball_y, ball_size = width - 5, 4, 10
    line1, line2 = _run_animation_text(kind)
    line1_bbox = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), line1, font=run_font)
    line1_x = 29 if width <= 64 and line1 == "RUN" else max(24, (width - (line1_bbox[2] - line1_bbox[0])) // 2)
    for step in range(3):
        image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        if is_home_run:
            _draw_home_run_frame_layout(image, draw, team, kind_key, color, alt, flash=bool(step % 2))
            _draw_baseball(draw, max(2, width - 27), ball_y, ball_size)
            _draw_home_run_middle_text(image, draw, team, kind_key, color, alt, show_player=step > 0)
        else:
            _draw_logo_or_fallback(image, draw, team, color)
            _draw_baseball(draw, ball_x, ball_y, ball_size)
            draw_sharp_text(image, (line1_x, 4), line1, color, run_font)
        frames.append(image.convert("RGB"))
        durations.append(170)

    scored_color = alt if alt != (255, 255, 255) else color
    line2_bbox = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), line2, font=font)
    line2_x = 21 if width <= 64 and line2 == "SCORED" else max(24, (width - (line2_bbox[2] - line2_bbox[0])) // 2)
    for show in (True, False, True, False, True, False, True, False, True):
        image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        if is_home_run:
            _draw_home_run_frame_layout(image, draw, team, kind_key, color, alt, flash=show)
            _draw_baseball(draw, max(2, width - 27), ball_y, ball_size)
            if show:
                _draw_home_run_middle_text(image, draw, team, kind_key, color, alt, show_player=True)
        else:
            _draw_logo_or_fallback(image, draw, team, color)
            _draw_baseball(draw, ball_x, ball_y, ball_size)
            draw_sharp_text(image, (line1_x, 4), line1, color, run_font)
            if show:
                draw_sharp_text(image, (line2_x, 16), line2, scored_color, font)
        frames.append(image.convert("RGB"))
        durations.append(220 if show else 160)

    return frames, durations


def _render_run_animation(team, kind="run"):
    kind_key = str(kind or "run").lower()
    try:
        width = int((team or {}).get("_width") or 64)
    except Exception:
        width = 64
    if kind_key in ("rbi", "scoring_play", "scoring-play"):
        return _render_rbi_card(team, kind_key)
    if width < 96 and kind_key in ("home_run", "homerun", "homer", "hr", "grand_slam", "grand slam", "slam", "walk_off", "walk-off", "win", "winner"):
        return _render_compact_moment_card(team, kind_key)
    frames, durations = _render_run_animation_frames(team, kind)
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


def _run_animation_width(options):
    options = options or {}
    try:
        explicit = int(options.get("_width") or 0)
        if explicit > 0:
            return max(64, min(512, explicit))
    except Exception:
        pass
    target = str(options.get("_target") or "").lower()
    if "128x32" in target:
        return 128
    return 64


def _selected_competitor(event, favorite):
    favorite = (favorite or "").strip().upper()
    competition = event.get("competitions", [{}])[0]
    for competitor in competition.get("competitors", []):
        team = competitor.get("team", {})
        values = {
            str(team.get("abbreviation", "")).upper(),
            str(team.get("shortDisplayName", "")).upper(),
            str(team.get("displayName", "")).upper(),
            str(team.get("name", "")).upper(),
        }
        if favorite and favorite in values:
            return competitor
    return None


def _fetch_summary(event_id, force=False):
    event_id = str(event_id or "").strip()
    if not event_id:
        return {}
    now = datetime.now(timezone.utc)
    cached = _SUMMARY_CACHE.get(event_id)
    if not force and cached and cached.get("expires", now) > now:
        return cached.get("body") or {}
    url = f"https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/summary?event={event_id}"
    data = fetch_json_url(url, {}, seconds=0)
    _SUMMARY_CACHE[event_id] = {"expires": now + timedelta(seconds=15), "body": data}
    return data


def _play_score_for_competitor(play, competitor):
    side = str(competitor.get("homeAway") or "").lower()
    key = "homeScore" if side == "home" else "awayScore"
    try:
        return int(play.get(key, 0) or 0)
    except Exception:
        return 0


def _play_team_matches(play, competitor):
    play_team = play.get("team") or {}
    team = competitor.get("team") or {}
    play_values = {
        str(play_team.get("id", "")),
        str(play_team.get("abbreviation", "")).upper(),
        str(play_team.get("shortDisplayName", "")).upper(),
        str(play_team.get("displayName", "")).upper(),
        str(play_team.get("name", "")).upper(),
    }
    team_values = {
        str(team.get("id", "")),
        str(team.get("abbreviation", "")).upper(),
        str(team.get("shortDisplayName", "")).upper(),
        str(team.get("displayName", "")).upper(),
        str(team.get("name", "")).upper(),
    }
    play_values = {value for value in play_values if value}
    team_values = {value for value in team_values if value}
    return bool(play_values & team_values)


def _play_is_bookkeeping(play):
    play_type = play.get("type") or {}
    type_key = str(play_type.get("type") or "").strip().lower()
    type_id = str(play_type.get("id") or "").strip()
    return type_key in {
        "start-batterpitcher",
        "end-batterpitcher",
        "start-inning",
        "end-inning",
    } or type_id in {"1", "59", "60", "99"}


def _athlete_id(value):
    athlete = (value or {}).get("athlete") if isinstance(value, dict) else {}
    if isinstance(athlete, dict):
        athlete_id = athlete.get("id")
        if athlete_id:
            return str(athlete_id).strip()
    if isinstance(value, dict) and value.get("id"):
        return str(value.get("id")).strip()
    return ""


def _participant_athlete_id(play, role="batter"):
    role = str(role or "").lower()
    for participant in (play or {}).get("participants") or []:
        if str(participant.get("type") or "").lower() == role:
            return _athlete_id(participant)
    return ""


def _athlete_index(summary):
    index = {}
    for group in ((summary or {}).get("boxscore") or {}).get("players") or []:
        team = group.get("team") or {}
        for stat_group in group.get("statistics") or []:
            labels = [str(label or "").strip() for label in (stat_group.get("labels") or stat_group.get("names") or [])]
            if labels and not {"H-AB", "AVG", "OBP", "SLG"} & set(labels):
                continue
            for item in stat_group.get("athletes") or []:
                athlete = item.get("athlete") or {}
                athlete_id = str(athlete.get("id") or "").strip()
                if not athlete_id:
                    continue
                headshot = athlete.get("headshot") or {}
                values = [str(value or "").strip() for value in (item.get("stats") or [])]
                batting_stats = {label: values[index] for index, label in enumerate(labels) if label and index < len(values)}
                index[athlete_id] = {
                    "id": athlete_id,
                    "displayName": athlete.get("displayName") or athlete.get("fullName") or athlete.get("shortName") or "",
                    "shortName": athlete.get("shortName") or athlete.get("displayName") or "",
                    "headshot": str(headshot.get("href") or "").strip() if isinstance(headshot, dict) else "",
                    "teamId": str(team.get("id") or "").strip(),
                    "teamAbbreviation": str(team.get("abbreviation") or "").strip().upper(),
                    "battingStats": batting_stats,
                }
    for roster_group in (summary or {}).get("rosters") or []:
        team = roster_group.get("team") or {}
        for item in roster_group.get("roster") or roster_group.get("athletes") or []:
            athlete = item.get("athlete") or item
            if not isinstance(athlete, dict):
                continue
            athlete_id = str(athlete.get("id") or "").strip()
            if not athlete_id or athlete_id in index:
                continue
            headshot = athlete.get("headshot") or {}
            index[athlete_id] = {
                "id": athlete_id,
                "displayName": athlete.get("displayName") or athlete.get("fullName") or athlete.get("shortName") or "",
                "shortName": athlete.get("shortName") or athlete.get("displayName") or "",
                "headshot": str(headshot.get("href") or "").strip() if isinstance(headshot, dict) else "",
                "teamId": str(team.get("id") or "").strip(),
                "teamAbbreviation": str(team.get("abbreviation") or "").strip().upper(),
            }
    return index


def _player_from_play(play, summary, role="batter"):
    athlete_id = _participant_athlete_id(play, role)
    if not athlete_id:
        return {}
    player = dict(_athlete_index(summary).get(athlete_id) or {})
    player["id"] = athlete_id
    if not player.get("headshot"):
        player["headshot"] = f"https://a.espncdn.com/i/headshots/mlb/players/full/{athlete_id}.png"
    if not player.get("displayName"):
        player["displayName"] = str((play or {}).get("text") or "").split(" pitches to ")[-1].strip()
    return player


def _player_from_id(athlete_id, summary):
    athlete_id = str(athlete_id or "").strip()
    if not athlete_id:
        return {}
    player = dict(_athlete_index(summary).get(athlete_id) or {})
    player["id"] = athlete_id
    if not player.get("headshot"):
        player["headshot"] = f"https://a.espncdn.com/i/headshots/mlb/players/full/{athlete_id}.png"
    return player


def _player_animation_team(team, player, kind):
    animation_team = dict(team or {})
    player = player or {}
    if player.get("displayName") or player.get("shortName"):
        role = "BATTER" if kind == "now_batting" else "HITTER" if kind in ("home_run", "grand_slam") else "RBI"
        animation_team["playerName"] = player.get("displayName") or player.get("shortName")
        animation_team["playerHeadshot"] = player.get("headshot") or ""
        animation_team["playerStats"] = player.get("battingStats") or {}
        animation_team["playerRole"] = role
        animation_team["momentKind"] = kind
    return animation_team


def _latest_run_play(event, competitor, previous_score, current_score, force_summary=False):
    try:
        summary = _fetch_summary(event.get("id"), force=force_summary)
    except Exception:
        return {}, {}
    plays = list(summary.get("scoringPlays") or [])
    if not plays:
        plays = []
        seen_score = previous_score
        for play in summary.get("plays") or []:
            if _play_is_bookkeeping(play):
                continue
            play_score = _play_score_for_competitor(play, competitor)
            if previous_score < play_score <= current_score and play_score > seen_score:
                plays.append(play)
            seen_score = max(seen_score, play_score)
    matched_candidates = []
    score_candidates = []
    for play in plays:
        play_score = _play_score_for_competitor(play, competitor)
        if previous_score < play_score <= current_score:
            if _play_team_matches(play, competitor):
                matched_candidates.append(play)
            score_candidates.append(play)
    play = (matched_candidates or score_candidates)[-1] if (matched_candidates or score_candidates) else None
    if not play:
        return {}, summary
    return play, summary


def _classify_latest_run(event, competitor, previous_score, current_score):
    play, summary = _latest_run_play(event, competitor, previous_score, current_score, force_summary=True)
    if not play:
        return {"kind": "run", "play": {}, "player": {}, "pending": True}
    delta = max(0, int(current_score or 0) - int(previous_score or 0))
    play_type = play.get("type") or {}
    text = " ".join([
        str(play_type.get("type", "")),
        str(play_type.get("text", "")),
        str(play_type.get("abbreviation", "")),
        str(play.get("text", "")),
        str(play.get("shortText", "")),
        str(play.get("detail", "")),
        str(play.get("description", "")),
    ]).replace("-", " ").replace("/", " ").lower()
    tokens = {part.strip(" .,:;!?()[]{}") for part in text.split()}
    player = _player_from_play(play, summary, "batter")
    if "grand slam" in text:
        return {"kind": "grand_slam", "play": play, "player": player}
    home_run_terms = {"homer", "homers", "homered", "hr", "hrs"}
    home_run_phrases = (
        "home run",
        "solo shot",
        "two run shot",
        "three run shot",
        "3 run shot",
        "2 run shot",
        "go ahead shot",
    )
    if any(term in tokens for term in home_run_terms) or any(phrase in text for phrase in home_run_phrases):
        return {"kind": "grand_slam" if delta >= 4 else "home_run", "play": play, "player": player}
    return {"kind": "rbi" if player else "run", "play": play, "player": player}


def _target_for_kind(options, kind):
    kind = str(kind or "run").lower()
    key = "runAnimationTarget"
    if kind in ("home_run", "grand_slam"):
        key = "homeRunAnimationTarget"
    elif kind in ("rbi", "scoring_play"):
        key = "scoringPlayAnimationTarget"
    elif kind in ("win", "walk_off"):
        key = "walkOffAnimationTarget"
    elif kind == "now_batting":
        key = "nowBattingAnimationTarget"
    value = str((options or {}).get(key) or "").strip().lower()
    if value:
        return value
    return str((options or {}).get("runAnimationTarget") or "device").strip().lower() if key == "runAnimationTarget" else "device"


def _mlb_animation_cache_key(card_kind, animation_team, player=None):
    width = animation_team.get("_width") or 64
    stats = animation_team.get("playerStats") if isinstance(animation_team.get("playerStats"), dict) else {}
    stats_sig = "|stats:" + ",".join(f"{key}={stats.get(key, '')}" for key in ("H-AB", "RBI", "HR", "AVG"))
    player_sig = f"|player:{(player or {}).get('id') or animation_team.get('playerName') or ''}|head:{animation_team.get('playerHeadshot') or ''}{stats_sig}"
    return priority_graphic_key(CARD_ID, animation_team, card_kind, width) + player_sig


def _mlb_moment_dwell(kind):
    kind = str(kind or "run").lower()
    if kind == "now_batting":
        return 5
    if kind in ("grand_slam", "win", "walk_off"):
        return 7
    return 6


def _pending_mlb_run_ready(previous):
    if not previous:
        return False
    try:
        pending_seen = previous.get("pending_seen")
        if not pending_seen:
            return False
        if isinstance(pending_seen, str):
            pending_seen = datetime.fromisoformat(pending_seen)
        if pending_seen.tzinfo is None:
            pending_seen = pending_seen.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - pending_seen).total_seconds() >= 5
    except Exception:
        return False


def _queue_mlb_animation(card_kind, options, team, player=None, dwell_secs=6, stay=False):
    animation_team = _player_animation_team(team, player, card_kind)
    animation_team["_width"] = _run_animation_width(options)
    target = _target_for_kind(options, card_kind)
    wall = target in ("group", "group_wall", "wall") or target.startswith("group:")
    cache_key = _mlb_animation_cache_key(card_kind, animation_team, player)
    return {
        "body": cached_priority_graphic(cache_key, lambda animation_team=animation_team, card_kind=card_kind: _render_run_animation(animation_team, card_kind)),
        "dwell_secs": dwell_secs,
        "_stay": stay,
        "_no_replay": True,
        "_priority": True,
        "_group_wall": {
            "type": card_kind,
            "renderer": "_render_run_animation_frames",
            "team": dict(animation_team),
            "kind": card_kind,
            "dwell_secs": dwell_secs,
        } if wall else None,
    }


def _team_for_player(player, competitors):
    team_id = str((player or {}).get("teamId") or "").strip()
    team_abbr = str((player or {}).get("teamAbbreviation") or "").strip().upper()
    for competitor in competitors or []:
        team = competitor.get("team") or {}
        values = {
            str(team.get("id") or "").strip(),
            str(team.get("abbreviation") or "").strip().upper(),
            str(team.get("shortDisplayName") or "").strip().upper(),
        }
        if (team_id and team_id in values) or (team_abbr and team_abbr in values):
            return team
    return (competitors[0].get("team") if competitors else {}) or {}


def _prewarm_now_batting(options, event, competition, summary, competitors):
    target = _target_for_kind(options, "now_batting")
    if target not in ("device", ""):
        return
    game_id = str(event.get("id") or competition.get("id") or datetime.now().strftime("%Y%m%d"))
    device_id = str((options or {}).get("_device_id") or "local")
    width = _run_animation_width(options)
    warm_key = f"{device_id}:{game_id}:{width}:now_batting"
    warmed = _BATTING_PREWARM_STATE.setdefault(warm_key, set())
    if len(_BATTING_PREWARM_STATE) > 80:
        _BATTING_PREWARM_STATE.clear()

    candidate_ids = []
    for item in ((summary.get("situation") or {}).get("dueUp") or []):
        athlete_id = str(item.get("playerId") or item.get("id") or "").strip()
        if athlete_id and athlete_id not in candidate_ids:
            candidate_ids.append(athlete_id)
    if len(candidate_ids) < 3:
        for play in reversed(summary.get("plays") or []):
            if str(((play.get("type") or {}).get("type") or "")).lower() != "start-batterpitcher":
                continue
            athlete_id = _participant_athlete_id(play, "batter")
            if athlete_id and athlete_id not in candidate_ids:
                candidate_ids.append(athlete_id)
            if len(candidate_ids) >= 3:
                break

    for athlete_id in candidate_ids[:3]:
        if athlete_id in warmed:
            continue
        player = _player_from_id(athlete_id, summary)
        if not player or not (player.get("displayName") or player.get("shortName")):
            continue
        team = _team_for_player(player, competitors)
        animation_team = _player_animation_team(team, player, "now_batting")
        animation_team["_width"] = width
        cache_key = _mlb_animation_cache_key("now_batting", animation_team, player)
        warm_priority_graphic(cache_key, lambda animation_team=animation_team: _render_run_animation(animation_team, "now_batting"))
        warmed.add(athlete_id)


def _mlb_log(options, message):
    log = (options or {}).get("_log")
    if callable(log):
        try:
            log(message)
        except Exception:
            pass


def _maybe_now_batting_animation(options, event, competition, competitors, favorite):
    state = str(((competition.get("status") or {}).get("type") or {}).get("state") or "").lower()
    if state != "in":
        _mlb_log(options, f"[mlb] now batting skipped state={state or 'unknown'}")
        return None
    try:
        summary = _fetch_summary(event.get("id"))
    except Exception as error:
        _mlb_log(options, f"[mlb] now batting summary unavailable: {error}")
        return None
    _prewarm_now_batting(options, event, competition, summary, competitors)
    competitor_ids = {str((item.get("team") or {}).get("id") or "").strip() for item in competitors or []}
    plays = [
        play for play in (summary.get("plays") or [])
        if str(((play.get("type") or {}).get("type") or "")).lower() == "start-batterpitcher"
    ]
    if not plays:
        _mlb_log(options, "[mlb] now batting skipped: no start-batterpitcher plays")
        return None
    play = plays[-1]
    player = _player_from_play(play, summary, "batter")
    if not player:
        _mlb_log(options, f"[mlb] now batting skipped: no batter participant play={play.get('id') or ''}")
        return None
    team_id = str(player.get("teamId") or (play.get("team") or {}).get("id") or "").strip()
    if competitor_ids and team_id and team_id not in competitor_ids:
        _mlb_log(options, f"[mlb] now batting skipped: batter team {team_id} not in game teams {sorted(competitor_ids)}")
        return None
    game_id = str(event.get("id") or competition.get("id") or datetime.now().strftime("%Y%m%d"))
    device_id = (options or {}).get("_device_id", "local")
    key = f"{device_id}:{game_id}:now_batting"
    signature = f"{play.get('id') or ''}:{player.get('id') or ''}"
    previous = _BATTING_STATE.get(key)
    _BATTING_STATE[key] = {"signature": signature, "seen": datetime.now(timezone.utc)}
    if previous is not None and previous.get("signature") == signature:
        _mlb_log(options, f"[mlb] now batting unchanged player={player.get('displayName') or player.get('id')}")
        return None
    team = {}
    for competitor in competitors or []:
        if str((competitor.get("team") or {}).get("id") or "").strip() == team_id:
            team = competitor.get("team") or {}
            break
    if not team:
        team = (competitors[0].get("team") if competitors else {}) or {}
    target = _target_for_kind(options, "now_batting")
    _mlb_log(options, f"[mlb] now batting queued player={player.get('displayName') or player.get('id')} team={team.get('abbreviation') or team_id} target={target} device={(options or {}).get('_device_id', 'local')}")
    return _queue_mlb_animation("now_batting", options, team, player, dwell_secs=5, stay=True)


def _maybe_final_winner_animation(options, state, key, competition, competitor, team, previous):
    if previous is None or (state.get(key) or {}).get("win_animated"):
        return None
    try:
        score = int(competitor.get("score", 0) or 0)
    except Exception:
        score = 0
    if not score:
        return None
    others = [item for item in (competition or {}).get("competitors") or [] if item is not competitor]
    other_scores = []
    for other in others:
        try:
            other_scores.append(int(other.get("score", 0) or 0))
        except Exception:
            pass
    if competitor.get("winner") is not True and (not other_scores or score <= max(other_scores)):
        return None
    state[key] = {**(state.get(key) or {}), "win_animated": True, "seen": datetime.now(timezone.utc)}
    return _queue_mlb_animation("win", options, team, None, dwell_secs=7, stay=True)


def _queue_mlb_scoring_animation(kind, options, animation_team, player, target, dwell_secs):
    wall = target in ("group", "group_wall", "wall") or target.startswith("group:")
    cache_key = _mlb_animation_cache_key(kind, animation_team, player)
    return {
        "body": cached_priority_graphic(cache_key, lambda animation_team=animation_team, kind=kind: _render_run_animation(animation_team, kind)),
        "dwell_secs": dwell_secs,
        "_stay": False,
        "_no_replay": True,
        "_priority": True,
        "_group_wall": {
            "type": kind,
            "renderer": "_render_run_animation_frames",
            "team": animation_team,
            "kind": kind,
            "dwell_secs": dwell_secs,
        } if wall else None,
    }


def _maybe_game_start_animation(options, event, competition, competitors, favorite):
    game_id = str(event.get("id") or competition.get("id") or datetime.now().strftime("%Y%m%d"))
    device_id = (options or {}).get("_device_id", "local")
    state = str(((competition.get("status") or {}).get("type") or {}).get("state") or "").lower()
    key = f"{device_id}:{game_id}:game_start"
    previous = _GAME_STATE.get(key)
    _GAME_STATE[key] = {"state": state, "seen": datetime.now(timezone.utc)}
    if previous is None or state != "in" or str(previous.get("state") or "").lower() == "in":
        return None

    favorite_competitor = _selected_competitor(event, favorite)
    competitor = favorite_competitor or (competitors[0] if competitors else {})
    team = (competitor or {}).get("team") or {}
    animation_team = dict(team)
    animation_team["_width"] = _run_animation_width(options)
    target = str((options or {}).get("gameStartAnimationTarget") or "device").strip().lower()
    wall = target in ("group", "group_wall", "wall") or target.startswith("group:")
    cache_key = priority_graphic_key(CARD_ID, animation_team, "game_start", animation_team["_width"])
    return {
        "body": cached_priority_graphic(cache_key, lambda animation_team=animation_team: _render_run_animation(animation_team, "game_start")),
        "dwell_secs": 6,
        "_stay": True,
        "_no_replay": True,
        "_priority": True,
        "_group_wall": {
            "type": "game_start",
            "renderer": "_render_run_animation_frames",
            "team": dict(animation_team),
            "kind": "game_start",
            "dwell_secs": 6,
        } if wall else None,
    }


def _maybe_run_animation(options):
    favorite = (options or {}).get("favoriteTeam", "")
    if not str(favorite or "").strip():
        return None
    log = (options or {}).get("_log")
    data = fetch_sport_scoreboard(_URL, _CACHE, favorite, seconds=15)
    event = pick_sport_event(data.get("events", []), favorite)
    if not event:
        return None

    competition = event.get("competitions", [{}])[0]
    state = competition.get("status", {}).get("type", {}).get("state")
    game_competitors = [item for item in competition.get("competitors", []) if item.get("team")]
    competitors = animation_competitors(event, favorite, options)
    if not competitors and not game_competitors:
        return None

    game_start = _maybe_game_start_animation(options, event, competition, competitors or game_competitors, favorite)
    if game_start:
        return game_start
    now_batting = _maybe_now_batting_animation(options, event, competition, game_competitors or competitors, favorite)
    if now_batting:
        return now_batting
    if not competitors:
        return None

    game_id = str(event.get("id") or competition.get("id") or datetime.now().strftime("%Y%m%d"))
    device_id = (options or {}).get("_device_id", "local")
    for competitor in competitors:
        team = competitor.get("team", {})
        team_key = (team.get("abbreviation") or team.get("shortDisplayName") or favorite or "MLB").upper()
        key = f"{device_id}:{game_id}:{team_key}"
        try:
            score = int(competitor.get("score", 0) or 0)
        except Exception:
            score = 0

        animation_team = dict(team)
        animation_team["_width"] = _run_animation_width(options)
        cache_key = priority_graphic_key(CARD_ID, animation_team, "run", animation_team["_width"])

        previous = _RUN_STATE.get(key)
        if state != "in":
            if str(state or "").lower() == "post":
                win = _maybe_final_winner_animation(options, _RUN_STATE, key, competition, competitor, animation_team, previous)
                if win and previous is not None:
                    return win
            _RUN_STATE[key] = {**(_RUN_STATE.get(key) or {}), "score": score, "animated": score, "seen": datetime.now(timezone.utc)}
            continue
        if previous is None:
            _RUN_STATE[key] = {"score": score, "animated": score, "seen": datetime.now(timezone.utc)}
            warm_priority_graphic(cache_key, lambda animation_team=animation_team: _render_run_animation(animation_team))
            continue

        last_score = int(previous.get("score", score) or 0)
        animated = int(previous.get("animated", last_score) or 0)
        pending_score = int(previous.get("pending_score", 0) or 0)
        pending_last_score = int(previous.get("pending_last_score", last_score) or 0)
        _RUN_STATE[key] = {
            "score": score,
            "animated": animated,
            "seen": datetime.now(timezone.utc),
            **({"pending_score": pending_score, "pending_last_score": pending_last_score, "pending_seen": previous.get("pending_seen")} if pending_score > animated else {}),
        }
        warm_priority_graphic(cache_key, lambda animation_team=animation_team: _render_run_animation(animation_team))

        score_to_animate = 0
        score_before_animation = last_score
        if pending_score > animated and score >= pending_score:
            score_to_animate = pending_score
            score_before_animation = pending_last_score
        elif score > last_score and score > animated:
            score_to_animate = score
            score_before_animation = last_score

        if score_to_animate:
            run_info = _classify_latest_run(event, competitor, score_before_animation, score_to_animate)
            pending = bool(run_info.get("pending"))
            if pending and not _pending_mlb_run_ready(previous):
                pending_seen = previous.get("pending_seen") if pending_score == score_to_animate else datetime.now(timezone.utc)
                _RUN_STATE[key] = {
                    "score": score,
                    "animated": animated,
                    "pending_score": score_to_animate,
                    "pending_last_score": score_before_animation,
                    "pending_seen": pending_seen,
                    "seen": datetime.now(timezone.utc),
                }
                if callable(log):
                    try:
                        log(f"[mlb] run pending classification {team_key} {score_before_animation}->{score_to_animate} device={device_id}")
                    except Exception:
                        pass
                continue
            kind = run_info.get("kind") or "run"
            player = run_info.get("player") or {}
            animation_team = _player_animation_team(animation_team, player, kind)
            target = _target_for_kind(options, kind)
            wall = target in ("group", "group_wall", "wall") or target.startswith("group:")
            _RUN_STATE[key] = {"score": score, "animated": score_to_animate, "seen": datetime.now(timezone.utc)}
            if callable(log):
                try:
                    log(f"[mlb] run detected {team_key} {score_before_animation}->{score_to_animate} kind={kind} target={target} wall={wall} device={device_id}")
                except Exception:
                    pass
            dwell_secs = _mlb_moment_dwell(kind)
            return _queue_mlb_scoring_animation(kind, options, animation_team, player, target, dwell_secs)
    return None


def render(options=None):
    animation = _maybe_run_animation(options or {})
    if animation:
        return animation
    return render_sport_card(options, _URL, _CACHE, _COLOR, "NO MLB")
