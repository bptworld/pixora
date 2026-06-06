from io import BytesIO
import math
from pathlib import Path
import urllib.request

from card_utils import draw_sharp_text


_LOGO_CACHE = {}
_ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
WALL_RENDER_VERSION = "sports-scenes-v1"


def hex_color(value, fallback=(117, 231, 214)):
    value = str(value or "").strip().lstrip("#")
    if len(value) == 6:
        try:
            return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            pass
    return fallback


def dim(color, factor):
    return tuple(max(0, min(255, int(c * factor))) for c in color)


def luminance(color):
    return (color[0] * 0.299) + (color[1] * 0.587) + (color[2] * 0.114)


def blend(left, right, amount):
    amount = max(0, min(1, amount))
    return tuple(int(left[i] + ((right[i] - left[i]) * amount)) for i in range(3))


def readable_accent(color, alt):
    if alt == (255, 255, 255) or luminance(alt) < 88:
        return (255, 231, 104)
    return alt


def kind_headline(kind, sport="score"):
    kind = str(kind or "score").lower()
    sport = str(sport or "score").lower()
    if kind in ("grand_slam", "grand slam", "slam"):
        return "GRAND SLAM"
    if kind in ("home_run", "homerun", "homer", "hr"):
        return "HOME RUN"
    if kind == "run":
        return "RUN SCORED"
    if kind == "touchdown":
        return "TOUCHDOWN"
    if kind == "field_goal":
        return "FIELD GOAL"
    if kind == "safety":
        return "SAFETY"
    if kind == "three":
        return "3 POINT"
    if kind == "free_throw":
        return "FREE THROW"
    if kind == "bucket":
        return "BUCKET"
    if kind == "point":
        return "POINT"
    if kind in ("win", "wins", "winner", "final_win"):
        return "WINS"
    if kind == "goal" or sport in ("hockey", "soccer", "lacrosse"):
        return "GOAL"
    return "SCORE"


def compact_headline(kind, sport="score"):
    kind = str(kind or "score").lower()
    sport = str(sport or "score").lower()
    if kind in ("grand_slam", "grand slam", "slam"):
        return "SLAM"
    if kind in ("home_run", "homerun", "homer", "hr"):
        return "HR"
    if kind == "run":
        return "RUN"
    if kind == "touchdown":
        return "TD"
    if kind == "field_goal":
        return "FG"
    if kind == "safety":
        return "SAFE"
    if kind == "three":
        return "3PT"
    if kind == "free_throw":
        return "FT"
    if kind == "bucket":
        return "BUCKET"
    if kind == "point":
        return "POINT"
    if kind in ("win", "wins", "winner", "final_win"):
        return "WIN"
    if kind == "goal" or sport in ("hockey", "soccer", "lacrosse"):
        return "GOAL"
    return "SCORE"


def fit_font(text, max_width, sizes):
    from PIL import Image, ImageDraw, ImageFont

    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    font = ImageFont.load_default()
    for size in sizes:
        try:
            font = ImageFont.truetype(str(_ASSETS_DIR / "fonts" / "PixelifySans-Bold.ttf"), size)
        except Exception:
            font = ImageFont.load_default()
        bbox = probe.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
    return font


def _team_logo_url(team):
    if team.get("logo"):
        return team.get("logo")
    logos = team.get("logos") or []
    if logos:
        return logos[0].get("href") or ""
    return ""


def _fetch_logo(url):
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


def _draw_badge(image, draw, team, color, default_label):
    logo = _fetch_logo(_team_logo_url(team or {}))
    if logo:
        image.alpha_composite(logo, (0, 5))
        return
    draw.rounded_rectangle((0, 4, 25, 28), radius=2, outline=color, width=2, fill=(4, 7, 9, 255))
    abbr = str((team or {}).get("abbreviation") or (team or {}).get("shortDisplayName") or default_label).upper()[:3]
    font = fit_font(abbr, 21, (9, 8, 7, 6))
    bbox = draw.textbbox((0, 0), abbr, font=font)
    draw_sharp_text(image, (13 - (bbox[2] - bbox[0]) // 2, 11), abbr, color, font)


def _draw_sport_mark(draw, sport, x, y, color, alt, phase=0):
    sport = str(sport or "score").lower()
    if sport in ("baseball", "mlb", "softball"):
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(246, 246, 232), outline=(210, 210, 200))
        draw.arc((x - 3, y - 4, x + 1, y + 4), 285, 75, fill=(210, 42, 48))
        draw.arc((x - 1, y - 4, x + 3, y + 4), 105, 255, fill=(210, 42, 48))
    elif sport in ("hockey", "nhl"):
        draw.ellipse((x - 5, y - 2, x + 5, y + 2), fill=(38, 42, 48), outline=(145, 155, 165))
        draw.line((x - 3, y - 2, x + 3, y - 2), fill=(210, 220, 230))
    elif sport == "soccer":
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(245, 245, 238), outline=(180, 185, 185))
        draw.polygon([(x, y - 2), (x + 2, y), (x + 1, y + 3), (x - 1, y + 3), (x - 2, y)], fill=(18, 22, 26))
    elif sport in ("football", "nfl", "ufl", "cfl"):
        draw.ellipse((x - 5, y - 3, x + 5, y + 3), fill=(136, 72, 36), outline=(215, 145, 90))
        draw.line((x - 2, y, x + 2, y), fill=(245, 245, 235))
    elif sport in ("basketball", "nba", "wnba"):
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(224, 116, 48), outline=(255, 178, 96))
        draw.line((x - 4, y, x + 4, y), fill=(60, 36, 24))
        draw.line((x, y - 4, x, y + 4), fill=(60, 36, 24))
    else:
        r = 2 + (phase % 3)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=alt, outline=color)


def _draw_firework(draw, cx, cy, radius, color, alt=None, phase=0, width=64):
    alt = alt or (255, 255, 255)
    palette = [
        color,
        alt,
        (255, 82, 62),
        (255, 202, 64),
        (102, 220, 255),
        (255, 116, 214),
    ]
    cx = int(cx)
    cy = int(cy)
    radius = max(2, int(radius))
    core = palette[phase % len(palette)]
    draw.rectangle((cx - 1, cy - 1, cx + 1, cy + 1), fill=(255, 245, 170, 255))
    for ray, angle in enumerate((0, 35, 70, 110, 145, 180, 215, 250, 290, 325)):
        radians = math.radians(angle + (phase % 3) * 5)
        length = radius + (ray % 3)
        x1 = int(cx + math.cos(radians) * max(2, radius - 4))
        y1 = int(cy + math.sin(radians) * max(2, radius - 4))
        x2 = int(cx + math.cos(radians) * length)
        y2 = int(cy + math.sin(radians) * min(length, 11))
        fire_color = palette[(ray + phase) % len(palette)]
        draw.line((cx, cy, x2, y2), fill=fire_color + (255,))
        if 0 <= x1 < width and 0 <= y1 < 32:
            draw.point((x1, y1), fill=(255, 255, 210, 255))
        if 0 <= x2 < width and 0 <= y2 < 32:
            draw.rectangle((x2 - 1, y2 - 1, x2 + 1, y2 + 1), fill=fire_color + (255,))
    for spark in range(6):
        sx = int(cx + math.cos((spark * 61 + phase * 13) * math.pi / 180) * (radius + 3))
        sy = int(cy + math.sin((spark * 61 + phase * 13) * math.pi / 180) * min(radius + 3, 12))
        if 0 <= sx < width and 0 <= sy < 32:
            draw.point((sx, sy), fill=palette[(spark + 2 + phase) % len(palette)] + (255,))


def _draw_boom(draw, image, width, color, alt, phase=0):
    boom = "BOOM"
    font = fit_font(boom, min(44, max(26, width - 34)), (12, 11, 10, 9, 8))
    bbox = draw.textbbox((0, 0), boom, font=font)
    boom_w = bbox[2] - bbox[0]
    x = max(29, (width - boom_w) // 2) - bbox[0]
    y = 2 - bbox[1]
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        draw_sharp_text(image, (x + dx, y + dy), boom, (255, 70, 44), font)
    draw_sharp_text(image, (x, y), boom, alt if phase % 2 else (255, 236, 112), font)
    center_x = x + boom_w // 2
    _draw_firework(draw, center_x, 16, 11 + (phase % 3), color, alt, phase, width)


def _draw_light_tower(draw, x, y, mirror=False, phase=0):
    steel = (50, 62, 68, 255)
    dim_bulb = (82, 100, 112, 255)
    bright = (236, 246, 255, 255)
    glow = (156, 210, 255, 255)
    mast_bottom = 21
    leg = -1 if mirror else 1
    draw.line((x, y + 6, x, mast_bottom), fill=steel)
    draw.line((x, y + 9, x + leg * 8, mast_bottom), fill=steel)
    draw.line((x, y + 9, x - leg * 8, mast_bottom), fill=steel)
    draw.line((x - 5, y + 13, x + 5, y + 13), fill=steel)
    draw.line((x - 4, y + 17, x + 4, y + 17), fill=steel)
    panel_x0 = x - 7
    panel_y0 = y
    draw.rectangle((panel_x0 - 1, panel_y0 - 1, panel_x0 + 15, panel_y0 + 6), outline=steel, fill=(5, 11, 16, 255))
    for row in range(2):
        for col in range(5):
            bulb_x = panel_x0 + 1 + col * 3
            bulb_y = panel_y0 + 1 + row * 3
            fill = bright if (phase + row + col) % 4 else dim_bulb
            draw.rectangle((bulb_x, bulb_y, bulb_x + 1, bulb_y + 1), fill=fill)
            if fill == bright:
                draw.point((bulb_x, min(31, bulb_y + 2)), fill=glow)


def _draw_stadium_bowl(draw, width, phase, color, alt):
    center = width // 2
    crowd_a = (42, 48, 55, 255)
    crowd_b = (72, 78, 84, 255)
    rail = (212, 220, 218, 255)
    # Pixel rows for the inside of the stadium bowl.
    for row, y in enumerate((14, 16, 18, 20)):
        spread = width * (0.28 + row * 0.10)
        arc_lift = 5 + row * 1.6
        x0 = max(0, int(center - spread))
        x1 = min(width - 1, int(center + spread))
        step = 4 if width >= 128 else 5
        for x in range(x0, x1, step):
            normalized = abs((x - center) / max(1, spread))
            if normalized > 1:
                continue
            y_arc = int(y + (normalized * normalized * arc_lift))
            fill = crowd_b if ((x // step) + row + phase) % 3 else crowd_a
            if 0 <= y_arc < 31:
                draw.point((x, y_arc), fill=fill)
                if width >= 192 and ((x // step) + phase) % 6 == 0:
                    draw.point((min(width - 1, x + 1), y_arc), fill=(132, 138, 142, 255))

    # Bright curved railing, like the sample's stadium interior sweep.
    for spread, y_base, lift, line_color in (
        (0.48, 18, 8.5, rail),
        (0.38, 21, 6.5, (152, 160, 154, 255)),
    ):
        prev = None
        for x in range(max(0, int(center - width * spread)), min(width, int(center + width * spread))):
            normalized = abs((x - center) / max(1, width * spread))
            y = int(y_base + normalized * normalized * lift)
            if prev:
                draw.line((prev[0], prev[1], x, y), fill=line_color)
            prev = (x, y)


def _draw_ballpark_frame(width, phase, color, alt):
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (width, 32), (0, 4, 9, 255))
    draw = ImageDraw.Draw(image)
    # Stadium seating and night-sky pixels.
    for y, row_color in ((3, (10, 22, 35)), (6, (15, 28, 44)), (9, (12, 24, 38))):
        for x in range(0, width, 5):
            if ((x // 5) + phase + y) % 4:
                draw.point((x, y), fill=row_color + (255,))
            if ((x // 5) + phase) % 7 == 0:
                draw.point((min(width - 1, x + 2), y + 1), fill=(32, 48, 62, 255))
    if width >= 128:
        _draw_light_tower(draw, 23, 1, mirror=False, phase=phase)
        _draw_light_tower(draw, width - 24, 1, mirror=True, phase=phase + 2)
    else:
        _draw_light_tower(draw, 15, 1, mirror=False, phase=phase)
    _draw_stadium_bowl(draw, width, phase, color, alt)

    # Outfield, infield, foul lines, and bases.
    draw.rectangle((0, 22, width - 1, 31), fill=(5, 74, 42, 255))
    for x in range(-width, width, 10):
        draw.line((x + phase % 10, 31, x + 42 + phase % 10, 22), fill=(8, 94, 52, 255))
    draw.rectangle((0, 29, width - 1, 31), fill=(7, 112, 58, 255))
    home_x = width // 2
    draw.polygon(
        [(home_x, 21), (min(width - 1, home_x + 34), 29), (home_x, 31), (max(0, home_x - 34), 29)],
        fill=(102, 72, 40, 255),
        outline=(178, 150, 92, 255),
    )
    draw.line((home_x, 30, max(0, home_x - 70), 22), fill=(230, 220, 180, 255))
    draw.line((home_x, 30, min(width - 1, home_x + 70), 22), fill=(230, 220, 180, 255))
    for bx, by in ((home_x, 30), (max(4, home_x - 33), 27), (home_x, 23), (min(width - 5, home_x + 33), 27)):
        draw.polygon([(bx, by - 2), (bx + 3, by), (bx, by + 2), (bx - 3, by)], fill=(242, 234, 196, 255))
    return image, draw


def _draw_baseball_wall_text(image, draw, width, headline, phase, color, alt, reveal=1):
    headline = str(headline or "RUN SCORED").upper()
    if width < 96:
        headline = compact_headline("home_run" if headline == "HOME RUN" else "run", "baseball")
    max_text_width = max(28, width - (10 if width >= 128 else 32))
    font = fit_font(headline, max_text_width, (30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8))
    words = headline.split() if width >= 96 else [headline]
    word_gap = max(4, min(8, width // 36)) if len(words) > 1 else 0
    word_boxes = [draw.textbbox((0, 0), word, font=font) for word in words]
    text_w = sum(box[2] - box[0] for box in word_boxes) + (word_gap * max(0, len(words) - 1))
    bbox = draw.textbbox((0, 0), headline, font=font)
    center_x = width // 2
    x = max(31 if width < 96 else 4, center_x - text_w // 2) - bbox[0]
    panel_x0 = max(2, x - 5)
    panel_x1 = min(width - 3, x + text_w + 6)
    y = 3 - bbox[1] if width >= 128 else 6 - bbox[1]
    panel_y0, panel_y1 = (3, 25) if width >= 128 else (5, 24)
    if width < 128:
        draw.rectangle((panel_x0, panel_y0, panel_x1, panel_y1), fill=(2, 10, 13, 255), outline=dim(color, 0.55) + (255,))
    else:
        draw.line((panel_x0, panel_y1, panel_x1, panel_y1), fill=dim(color, 0.62) + (255,))
    fill = alt if phase % 6 < 3 else (245, 248, 236)
    word_x = x
    for word, word_box in zip(words, word_boxes):
        word_w = word_box[2] - word_box[0]
        word_y = 6 - word_box[1]
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            draw_sharp_text(image, (word_x + dx, word_y + dy), word, (40, 8, 6), font)
        draw_sharp_text(image, (word_x, word_y), word, fill, font)
        word_x += word_w + word_gap
    if reveal < 1:
        cover_x = int(panel_x0 + ((panel_x1 - panel_x0 + 1) * reveal))
        draw.rectangle((cover_x, panel_y0 - 1, panel_x1 + 1, panel_y1 + 1), fill=(0, 4, 9, 255))


def _render_baseball_wall_frames(team, kind="run", default_label="MLB"):
    team = team or {}
    try:
        width = int(team.get("_width") or 64)
    except Exception:
        width = 64
    width = max(64, min(512, width))
    color = hex_color(team.get("color"), (117, 231, 214))
    alt = readable_accent(color, hex_color(team.get("alternateColor"), (255, 255, 255)))
    kind_key = str(kind or "run").lower()
    headline = kind_headline(kind_key, "baseball")
    frames = []
    durations = []

    for frame_index in range(6):
        image, draw = _draw_ballpark_frame(width, frame_index, color, alt)
        _draw_sport_mark(draw, "baseball", max(8, width // 2 - 9), 20, color, alt, frame_index)
        frames.append(image.convert("RGB"))
        durations.append(120)

    for frame_index in range(52):
        image, draw = _draw_ballpark_frame(width, frame_index, color, alt)
        t = min(1, frame_index / 26)
        ball_x = 9 + ((width - 26) * t)
        ball_y = 24 - (17 * math.sin(t * math.pi))
        if 0 < frame_index < 34:
            previous = None
            start_t = max(0, t - 0.34)
            for segment in range(22):
                tt = start_t + ((t - start_t) * segment / 21)
                tx = 9 + ((width - 26) * tt)
                ty = 24 - (17 * math.sin(tt * math.pi))
                if previous:
                    age = segment / 21
                    outer = (255, 74, 36, 255) if segment % 3 else (255, 180, 56, 255)
                    inner = (255, 232, 128, 255) if age > 0.38 else (255, 154, 54, 255)
                    draw.line((previous[0], previous[1] + 2, int(tx), int(ty) + 2), fill=outer)
                    draw.line((previous[0], previous[1], int(tx), int(ty)), fill=inner)
                previous = (int(tx), int(ty))
        for trail in range(1, 10):
            tt = max(0, t - trail * 0.035)
            tx = 9 + ((width - 26) * tt)
            ty = 24 - (17 * math.sin(tt * math.pi))
            trail_color = ((255, 192, 48), (245, 50, 64), (245, 248, 236), (38, 160, 255))[trail % 4]
            if frame_index < 34:
                draw.point((int(tx), int(ty)), fill=trail_color + (255,))
                if trail < 5:
                    draw.point((max(0, int(tx) - 1), int(ty)), fill=trail_color + (255,))
        if frame_index < 32:
            _draw_sport_mark(draw, "baseball", int(ball_x), int(ball_y), color, alt, frame_index)
        reveal = max(0, min(1, (frame_index - 14) / 13))
        if reveal > 0:
            _draw_baseball_wall_text(image, draw, width, headline, frame_index, color, alt, reveal=reveal)
        if frame_index > 23:
            boom_font = fit_font("BOOM", 34, (10, 9, 8))
            crack_font = fit_font("CRACK", 38, (8, 7, 6))
            draw_sharp_text(image, (5, 10), "CRACK", (245, 50, 64) if frame_index % 4 < 2 else (245, 248, 236), crack_font)
            if width >= 128:
                draw_sharp_text(image, (width - 52, 18), "BOOM", (38, 160, 255) if frame_index % 4 < 2 else (245, 248, 236), boom_font)
            phase = frame_index - 23
            _draw_firework(draw, int(width * 0.22), 10, 4 + (phase % 8), (245, 50, 64), alt, phase, width)
            _draw_firework(draw, int(width * 0.74), 9, 5 + ((phase + 3) % 8), color, (255, 96, 200), phase + 2, width)
            if frame_index > 30:
                _draw_firework(draw, width - 20, 8, 4 + ((phase + 5) % 7), (38, 160, 255), alt, phase + 4, width)
        frames.append(image.convert("RGB"))
        durations.append(55)

    for frame_index in range(14):
        image, draw = _draw_ballpark_frame(width, 52 + frame_index, color, alt)
        _draw_baseball_wall_text(image, draw, width, headline, frame_index, color, alt, reveal=1)
        crack_font = fit_font("CRACK", 38, (8, 7, 6))
        draw_sharp_text(image, (5, 10), "CRACK", (245, 50, 64) if frame_index % 2 else (245, 248, 236), crack_font)
        if width >= 128:
            boom_font = fit_font("BOOM", 34, (10, 9, 8))
            draw_sharp_text(image, (width - 52, 18), "BOOM", (38, 160, 255) if frame_index % 2 else (245, 248, 236), boom_font)
        _draw_sport_mark(draw, "baseball", width - 17, 7, color, alt, frame_index)
        _draw_firework(draw, int(width * 0.22), 10, 8 + (frame_index % 4), (245, 50, 64), alt, frame_index, width)
        _draw_firework(draw, int(width * 0.74), 9, 9 + ((frame_index + 2) % 4), color, (255, 96, 200), frame_index + 2, width)
        _draw_firework(draw, width - 20, 8, 7 + ((frame_index + 1) % 4), (38, 160, 255), alt, frame_index + 4, width)
        frames.append(image.convert("RGB"))
        durations.append(90)

    return frames, durations


def _draw_generic_arena_frame(image, draw, width, sport, phase, color, alt):
    sport = str(sport or "score").lower()
    draw.rectangle((0, 0, width - 1, 31), fill=(0, 0, 0, 255))
    for y, shade in ((3, 22), (6, 34), (9, 28)):
        for x in range(0, width, 5):
            if ((x // 5) + y + phase) % 4:
                draw.point((x, y), fill=(0, min(44, shade), min(48, shade), 255))
    for tower_x in (max(8, width // 8), min(width - 9, width - width // 8)):
        for col in range(4):
            bx = tower_x + col * 2 - 4
            fill = (230, 242, 255, 255) if (phase + col) % 3 else dim(alt, 0.35) + (255,)
            draw.rectangle((bx, 1, bx + 1, 2), fill=fill)

    if sport in ("football", "nfl", "ufl", "cfl"):
        draw.rectangle((0, 14, width - 1, 31), fill=(5, 82, 42, 255))
        for x in range(0, width, max(8, width // 12)):
            draw.line((x, 14, x, 31), fill=(190, 220, 190, 255))
            for y in (18, 26):
                draw.point((min(width - 1, x + 3), y), fill=(240, 245, 235, 255))
        draw.line((0, 22, width - 1, 22), fill=(240, 245, 235, 255))
        draw.rectangle((0, 14, max(3, width // 16), 31), fill=dim(color, 0.45) + (255,))
        draw.rectangle((width - max(4, width // 16), 14, width - 1, 31), fill=dim(color, 0.45) + (255,))
    elif sport in ("hockey", "nhl"):
        draw.rectangle((0, 13, width - 1, 31), fill=(188, 228, 240, 255))
        draw.rectangle((0, 13, width - 1, 15), fill=(245, 250, 255, 255))
        draw.line((width // 2, 14, width // 2, 31), fill=(220, 40, 52, 255))
        draw.ellipse((width // 2 - 11, 19, width // 2 + 11, 31), outline=(42, 132, 210, 255))
        draw.line((max(0, width // 4), 14, max(0, width // 4), 31), fill=(42, 132, 210, 255))
        draw.line((min(width - 1, width * 3 // 4), 14, min(width - 1, width * 3 // 4), 31), fill=(42, 132, 210, 255))
        draw.rectangle((2, 21, 7, 28), outline=(220, 40, 52, 255))
        draw.rectangle((width - 8, 21, width - 3, 28), outline=(220, 40, 52, 255))
    elif sport in ("soccer", "lacrosse"):
        draw.rectangle((0, 13, width - 1, 31), fill=(6, 96, 50, 255))
        for x in range(-width, width, 12):
            draw.line((x + phase % 12, 31, x + 38 + phase % 12, 13), fill=(8, 118, 58, 255))
        draw.rectangle((4, 17, width - 5, 30), outline=(220, 240, 220, 255))
        draw.line((width // 2, 13, width // 2, 31), fill=(220, 240, 220, 255))
        draw.ellipse((width // 2 - 10, 19, width // 2 + 10, 31), outline=(220, 240, 220, 255))
        draw.rectangle((2, 20, 10, 28), outline=(220, 240, 220, 255))
        draw.rectangle((width - 11, 20, width - 3, 28), outline=(220, 240, 220, 255))
    elif sport in ("basketball", "nba", "wnba"):
        court = (178, 104, 48, 255)
        paint = dim(color, 0.55) + (255,)
        draw.rectangle((0, 13, width - 1, 31), fill=court)
        for x in range(0, width, 7):
            draw.line((x, 13, x + 16, 31), fill=(202, 130, 65, 255))
        draw.line((width // 2, 13, width // 2, 31), fill=(245, 220, 178, 255))
        draw.ellipse((width // 2 - 10, 19, width // 2 + 10, 31), outline=(245, 220, 178, 255))
        draw.rectangle((0, 19, 15, 31), outline=(245, 220, 178, 255), fill=paint)
        draw.rectangle((width - 16, 19, width - 1, 31), outline=(245, 220, 178, 255), fill=paint)
        draw.rectangle((5, 16, 7, 18), fill=(245, 245, 245, 255))
        draw.rectangle((width - 8, 16, width - 6, 18), fill=(245, 245, 245, 255))
    else:
        draw.rectangle((0, 14, width - 1, 31), fill=dim(color, 0.22) + (255,))
        for x in range(0, width, 6):
            shade = 12 + ((x + phase) % 18)
            draw.line((x, 3, x, 28), fill=(0, min(36, shade), min(38, shade), 255))
        draw.line((28, 5, width - 5, 5), fill=dim(color, 0.22) + (255,))
        draw.line((28, 27, width - 5, 27), fill=dim(color, 0.22) + (255,))

    draw.rectangle((0, 0, width - 1, 2), fill=color + (255,))
    draw.rectangle((0, 29, width - 1, 31), fill=dim(color, 0.28) + (255,))
    for x in range(2, width, 10):
        bulb = alt if ((x // 10) + phase) % 3 == 0 else dim(color, 0.35)
        draw.point((x, 1), fill=bulb + (255,))
        draw.point((width - 1 - x, 30), fill=bulb + (255,))


def render_wall_score_frames(team, kind="score", sport="score", default_label="TEAM"):
    from PIL import Image, ImageDraw

    team = team or {}
    try:
        width = int(team.get("_width") or 64)
    except Exception:
        width = 64
    width = max(64, min(512, width))
    if str(sport or "").lower() in ("baseball", "mlb", "softball") and str(kind or "").lower() in ("run", "home_run", "homerun", "homer", "hr", "grand_slam", "grand slam", "slam"):
        return _render_baseball_wall_frames(team, kind, default_label=default_label)
    color = hex_color(team.get("color"), (117, 231, 214))
    alt = readable_accent(color, hex_color(team.get("alternateColor"), (255, 255, 255)))
    headline = compact_headline(kind, sport) if width < 96 else kind_headline(kind, sport)
    is_win = str(kind or "").lower() in ("win", "wins", "winner", "final_win")
    title_font = fit_font(headline, max(24, width - 38), (13, 12, 11, 10, 9, 8, 7))
    text_bbox = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), headline, font=title_font)
    text_w = text_bbox[2] - text_bbox[0]
    if width >= 96:
        panel_w = min(width - 4, text_w + 8)
        panel_x0 = max(2, (width - panel_w) // 2)
        panel_x1 = panel_x0 + panel_w
        text_x = panel_x0 + max(0, (panel_w - text_w) // 2) - text_bbox[0]
    else:
        text_x = max(33, (width - text_w) // 2)
        if text_x + text_w > width - 3:
            text_x = max(31, width - text_w - 3)
        panel_x0 = max(31, text_x - 4)
        panel_x1 = min(width - 3, text_x + text_w + 4)
    panel_y0 = 8
    panel_y1 = 23
    text_h = text_bbox[3] - text_bbox[1]
    text_y = panel_y0 + (((panel_y1 - panel_y0 + 1) - text_h) // 2) - text_bbox[1] - 1
    frames = []
    durations = []

    def base_frame(phase):
        image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        _draw_generic_arena_frame(image, draw, width, sport, phase, color, alt)
        _draw_badge(image, draw, team, color, default_label)
        return image, draw

    start_x = 30
    end_x = width - 9
    for i in range(14):
        t = i / 13
        image, draw = base_frame(i)
        x = start_x + ((end_x - start_x) * t)
        y = 25 - (15 * math.sin(t * math.pi))
        for trail in range(1, 6):
            tt = max(0, t - trail * 0.04)
            tx = start_x + ((end_x - start_x) * tt)
            ty = 25 - (15 * math.sin(tt * math.pi))
            draw.line((int(tx) - 2, int(ty), int(tx) + 2, int(ty)), fill=blend(alt, color, 1 - trail / 6) + (255,))
        _draw_sport_mark(draw, sport, int(x), int(y), color, alt, i)
        frames.append(image.convert("RGB"))
        durations.append(48)

    impact_x = width - 11
    impact_y = 9
    for i in range(6):
        image, draw = base_frame(i + 14)
        radius = 3 + i * 2
        for angle in range(0, 360, 45):
            radians = math.radians(angle)
            draw.line(
                (impact_x, impact_y, int(impact_x + math.cos(radians) * radius), int(impact_y + math.sin(radians) * min(radius, 9))),
                fill=blend(color, alt, 0.45) + (255,),
            )
        _draw_sport_mark(draw, sport, impact_x, impact_y, color, alt, i)
        frames.append(image.convert("RGB"))
        durations.append(60)

    for i in range(12):
        image, draw = base_frame(i + 20)
        reveal = int(text_w * min(1, (i + 1) / 8))
        draw.rectangle((panel_x0, panel_y0, panel_x1, panel_y1), fill=(2, 8, 10, 255), outline=dim(color, 0.55) + (255,))
        draw_sharp_text(image, (text_x, text_y), headline, color if i % 2 else alt, title_font)
        if reveal < text_w and text_x + reveal <= panel_x1:
            draw.rectangle((text_x + reveal, panel_y0 - 1, panel_x1, panel_y1 + 1), fill=(2, 8, 10, 255))
        for sparkle in range(3):
            sx = (37 + i * 11 + sparkle * 29) % max(width, 1)
            sy = 7 + ((i + sparkle * 3) % 18)
            draw.point((sx, sy), fill=alt + (255,))
            draw.point((sx + 1, sy), fill=alt + (255,))
        if is_win:
            shell_radius = 4 + i
            _draw_firework(draw, width - 12, 8, shell_radius, color, alt, i, width)
            _draw_firework(draw, 34 + (i % 3), 22, max(3, shell_radius - 3), alt, color, i + 2, width)
            if i in (4, 5, 6, 7):
                _draw_boom(draw, image, width, color, alt, i)
        frames.append(image.convert("RGB"))
        durations.append(85)

    for i in range(8):
        image, draw = base_frame(i + 32)
        draw.rectangle((panel_x0, panel_y0, panel_x1, panel_y1), fill=(2, 8, 10, 255), outline=(alt if i % 2 else color) + (255,))
        draw_sharp_text(image, (text_x, text_y), headline, alt if i % 2 else color, title_font)
        _draw_sport_mark(draw, sport, impact_x, impact_y, color, alt, i)
        if is_win:
            _draw_firework(draw, 34 + ((i % 2) * 7), 8, 8 + (i % 4), color, alt, i, width)
            _draw_firework(draw, width - 12, 22, 10 + ((i + 2) % 4), alt, color, i + 5, width)
            if width >= 96:
                _draw_firework(draw, width // 2, 16, 12 + (i % 3), (255, 202, 64), alt, i + 8, width)
            if i < 4:
                _draw_boom(draw, image, width, color, alt, i)
        frames.append(image.convert("RGB"))
        durations.append(130)

    return frames, durations
