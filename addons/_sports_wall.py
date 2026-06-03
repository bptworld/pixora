from io import BytesIO
import math
import urllib.request

from card_utils import draw_sharp_text


_LOGO_CACHE = {}


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
            font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", size)
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


def render_wall_score_frames(team, kind="score", sport="score", default_label="TEAM"):
    from PIL import Image, ImageDraw

    team = team or {}
    try:
        width = int(team.get("_width") or 64)
    except Exception:
        width = 64
    width = max(64, min(512, width))
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
        for x in range(0, width, 6):
            shade = 12 + ((x + phase) % 18)
            draw.line((x, 3, x, 28), fill=(0, min(36, shade), min(38, shade), 255))
        draw.rectangle((0, 0, width - 1, 2), fill=color + (255,))
        draw.rectangle((0, 29, width - 1, 31), fill=dim(color, 0.28) + (255,))
        for x in range(2, width, 10):
            bulb = alt if ((x // 10) + phase) % 3 == 0 else dim(color, 0.35)
            draw.point((x, 1), fill=bulb + (255,))
            draw.point((width - 1 - x, 30), fill=bulb + (255,))
        draw.line((28, 5, width - 5, 5), fill=dim(color, 0.22) + (255,))
        draw.line((28, 27, width - 5, 27), fill=dim(color, 0.22) + (255,))
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
