from __future__ import annotations

from io import BytesIO
from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "addons"))

from PIL import Image, ImageDraw, ImageFont

from card_utils import (
    draw_pixora_bold_number,
    draw_mini_weather_icon,
    draw_sharp_text,
    pixora_bold_number_size,
    render_counter_card,
)

OUT_DIR = ROOT / "assets" / "previews"
ADDONS_DIR = ROOT / "addons"


def _font(name="assets/fonts/Silkscreen-Regular.ttf", size=8):
    try:
        return ImageFont.truetype(str(ROOT / name), size)
    except Exception:
        return ImageFont.load_default()


FONT = _font()
BOLD = _font("assets/fonts/Silkscreen-Bold.ttf")
BIG = _font("assets/fonts/Silkscreen-Bold.ttf", 16)


def _webp(image):
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _save(card_id, body):
    if isinstance(body, dict):
        body = body.get("body")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{card_id}.webp").write_bytes(body)


def _center(image, text, y, color, font=FONT, x1=0, x2=63):
    draw = ImageDraw.Draw(image)
    text = str(text)
    w = draw.textbbox((0, 0), text, font=font)[2]
    draw_sharp_text(image, (x1 + ((x2 - x1 + 1) - w) // 2, y), text, color, font)


def _fallback(card_id, name):
    image = Image.new("RGB", (64, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    words = str(name or card_id).upper().replace("+", " + ").split()
    lines = []
    line = ""
    for word in words:
        test = (line + " " + word).strip()
        if draw.textbbox((0, 0), test, font=FONT)[2] <= 62:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    y = max(0, (32 - min(3, len(lines)) * 8) // 2 - 3)
    for line in lines[:3]:
        _center(image, line, y, (24, 210, 190), FONT)
        y += 8
    return _webp(image)


def _simple_header(title, color=(24, 210, 190)):
    image = Image.new("RGB", (64, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 63, 8), fill=(5, 18, 25))
    _center(image, title[:12].upper(), -3, color, BOLD)
    return image, draw


def _clock():
    image = Image.new("RGB", (64, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    _center(image, "04:56", -4, (20, 149, 255), BIG)
    draw_mini_weather_icon(draw, "cloud", 22, 17)
    draw_sharp_text(image, (36, 17), "68F", (235, 247, 255), FONT)
    return _webp(image)


def _clock_calendar():
    image = Image.new("RGB", (64, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    cell = 3
    gap = 1
    for row in range(7):
        for col in range(7):
            x = 1 + col * (cell + gap)
            y = 4 + row * (cell + gap)
            draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=(214, 0, 18) if row < 2 else (36, 38, 40))
    for col, row in {
        (1, 2), (2, 2), (3, 2), (4, 2), (5, 2),
        (1, 3), (1, 4),
        (1, 4), (2, 4), (3, 4), (4, 4), (5, 4),
        (5, 5), (5, 6),
        (1, 6), (2, 6), (3, 6), (4, 6), (5, 6),
    }:
        x = 1 + col * (cell + gap)
        y = 4 + row * (cell + gap)
        draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=(232, 236, 238))
    _center(image, "12:00", 8, (232, 236, 238), BOLD, 30, 63)
    x = 30
    for idx in range(4):
        draw.rectangle((x, 25, x + 4, 27), fill=(232, 236, 238) if idx == 3 else (24, 25, 26))
        x += 8
    return _webp(image)


def _clock_day_progress():
    image = Image.new("RGB", (64, 32), (0, 4, 8))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 63, 7), fill=(5, 15, 22))
    draw_sharp_text(image, (1, -4), "FRI", (150, 178, 196), FONT)
    draw_sharp_text(image, (48, -4), "50%", (62, 224, 150), FONT)
    time_text = "12:00"
    tw, th = pixora_bold_number_size(time_text, scale=2, spacing=1)
    draw_pixora_bold_number(draw, ((64 - tw) // 2, 10), time_text, (235, 247, 255), scale=2, spacing=1)
    draw.rectangle((2, 28, 61, 31), outline=(40, 58, 70))
    draw.rectangle((3, 29, 32, 30), fill=(62, 224, 150))
    for x in (17, 32, 47):
        draw.line((x, 29, x, 30), fill=(12, 20, 25))
    return _webp(image)


def _clock_week_strip():
    image = Image.new("RGB", (64, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    days = "MTWTFSS"
    for idx, label in enumerate(days):
        x1 = 1 + idx * 9
        x2 = x1 + 7
        active = idx == 4
        draw.rectangle((x1, 0, x2, 8), fill=(35, 118, 220) if active else (10, 18, 27), outline=(90, 170, 255) if active else (32, 48, 60))
        if active:
            _center(image, label, -3, (245, 250, 255), FONT, x1, x2)
    _center(image, "12:00", 5, (235, 247, 255), BIG)
    _center(image, "FRI 06/05", 24, (92, 185, 255), FONT)
    return _webp(image)


def _weather_forecast():
    image, draw = _simple_header("4 DAY", (24, 182, 163))
    cols = [8, 24, 40, 56]
    data = [("Tu", "sun", "72", "54"), ("We", "cloud", "68", "52"), ("Th", "rain", "61", "49"), ("Fr", "sun", "70", "55")]
    for x in (16, 32, 48):
        draw.line((x, 0, x, 31), fill=(25, 35, 50))
    for cx, (day, icon, hi, lo) in zip(cols, data):
        _center(image, day, -3, (160, 190, 215), FONT, cx - 8, cx + 8)
        draw_mini_weather_icon(draw, icon, cx, 7)
        _center(image, hi, 14, (255, 175, 70), BOLD, cx - 8, cx + 8)
        _center(image, lo, 22, (110, 175, 255), FONT, cx - 8, cx + 8)
    return _webp(image)


def _weather_alert():
    image, draw = _simple_header("WX ALERT", (255, 190, 70))
    draw_sharp_text(image, (1, 10), "T-STORM", (245, 245, 245), FONT)
    draw_sharp_text(image, (1, 21), "WATCH", (255, 190, 70), FONT)
    draw.ellipse((48, 10, 58, 20), outline=(255, 190, 70))
    draw.polygon([(53, 7), (47, 20), (54, 17), (49, 28), (61, 13), (54, 15)], fill=(255, 230, 80))
    return _webp(image)


def _weather_radar_loop():
    image = Image.new("RGB", (64, 32), (0, 4, 8))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 63, 8), fill=(0, 8, 14))
    draw_sharp_text(image, (1, -3), "RADAR RAIN", (118, 245, 210), FONT)
    cx, cy = 20, 20
    for r in (7, 13, 19):
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(8, 42, 48))
    draw.line((cx - 18, cy, cx + 18, cy), fill=(5, 34, 40))
    draw.line((cx, cy - 18, cx, cy + 11), fill=(5, 34, 40))
    draw.line((cx, cy, 37, 11), fill=(42, 238, 190))
    draw.rectangle((42, 12, 51, 16), fill=(42, 210, 98))
    draw.rectangle((47, 18, 59, 21), fill=(255, 218, 70))
    draw.rectangle((35, 23, 45, 26), fill=(42, 190, 92))
    draw.rectangle((12, 14, 20, 17), fill=(42, 210, 98))
    draw.rectangle((cx - 1, cy - 1, cx + 1, cy + 1), fill=(118, 245, 210))
    return _webp(image)


def _air_quality():
    image, draw = _simple_header("AIR", (125, 220, 255))
    for x in (21, 43):
        draw.line((x, 10, x, 31), fill=(22, 34, 42))
    for (x1, x2), label, value, color in [
        ((0, 20), "AQI", "42", (80, 225, 110)),
        ((22, 42), "POL", "LOW", (80, 225, 110)),
        ((44, 63), "UV", "6", (255, 150, 60)),
    ]:
        _center(image, label, 9, (150, 170, 185), FONT, x1, x2)
        _center(image, value, 20, color, BOLD, x1, x2)
    return _webp(image)


def _sport(title="TOP 7TH", away="HOU", home="BOS", score="3-1", color=(245, 150, 65)):
    image = Image.new("RGB", (64, 32), (5, 7, 10))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 63, 8), fill=(8, 18, 28))
    _center(image, title[:18].upper(), -3, color, FONT)
    sw = draw.textbbox((0, 0), score, font=BOLD)[2]
    draw.rounded_rectangle((32 - sw // 2 - 3, 7, 32 + (sw + 1) // 2 + 3, 20), radius=3, fill=(18, 29, 39), outline=(69, 87, 104))
    _center(image, score, 8, (247, 251, 255), BOLD, 0, 63)
    draw.ellipse((2, 8, 12, 18), fill=(28, 80, 160))
    draw.ellipse((52, 8, 62, 18), fill=(180, 35, 45))
    draw_sharp_text(image, (2, 15), away[:3], (255, 255, 255), BOLD)
    hw = draw.textbbox((0, 0), home[:3], font=BOLD)[2]
    draw_sharp_text(image, (63 - hw, 15), home[:3], (255, 255, 255), BOLD)
    draw_sharp_text(image, (2, 22), "32-18", (174, 185, 196), FONT)
    draw_sharp_text(image, (43, 22), "30-20", (174, 185, 196), FONT)
    return _webp(image)


def _event_sport(title, icon="race"):
    image, draw = _simple_header(title[:10], (255, 190, 70))
    if icon == "golf":
        draw.line((4, 9, 4, 25), fill=(255, 190, 70))
        draw.polygon([(5, 9), (15, 12), (5, 15)], fill=(245, 80, 80))
        draw.ellipse((8, 25, 13, 30), fill=(235, 245, 245))
    elif icon == "fight":
        draw.rectangle((2, 12, 8, 19), fill=(255, 190, 70))
        draw.rectangle((9, 10, 15, 17), fill=(245, 80, 90))
    elif icon == "tennis":
        draw.ellipse((2, 10, 14, 22), fill=(185, 240, 80), outline=(255, 190, 70))
        draw.line((12, 22, 16, 29), fill=(180, 195, 210))
    else:
        for r in range(4):
            for c in range(4):
                draw.rectangle((2 + c * 3, 10 + r * 3, 4 + c * 3, 12 + r * 3), fill=(235, 245, 255) if (r + c) % 2 == 0 else (255, 190, 70))
    rows = [("1", "LEADER", "-12"), ("2", "CHASE", "-10")]
    y = 9
    for rank, name, score in rows:
        draw_sharp_text(image, (18, y), rank, (180, 195, 210), FONT)
        draw_sharp_text(image, (28, y), name, (235, 245, 255), FONT)
        w = draw.textbbox((0, 0), score, font=FONT)[2]
        draw_sharp_text(image, (63 - w, y), score, (255, 190, 70), FONT)
        y += 9
    return _webp(image)


def _fifa_world_cup():
    image = Image.new("RGB", (64, 32), (3, 8, 12))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 63, 8), fill=(4, 24, 20))
    draw_sharp_text(image, (1, -3), "WORLD CUP", (70, 220, 125), BOLD)
    draw.ellipse((1, 10, 14, 23), outline=(70, 220, 125), width=2)
    draw.ellipse((49, 10, 62, 23), outline=(90, 150, 255), width=2)
    draw_sharp_text(image, (3, 13), "USA", (245, 250, 255), FONT)
    draw_sharp_text(image, (50, 13), "PAR", (245, 250, 255), FONT)
    _center(image, "VS", 11, (245, 250, 255), BOLD)
    _center(image, "JUN 12", 22, (130, 160, 170), FONT)
    return _webp(image)


def _world_cup_today():
    image = Image.new("RGB", (64, 32), (3, 8, 12))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 63, 8), fill=(4, 24, 20))
    draw_sharp_text(image, (1, -3), "WC TODAY", (70, 220, 125), BOLD)
    rows = ["USA VS MEX", "CAN VS BRA", "ENG VS FRA"]
    y = 8
    for idx, row in enumerate(rows):
        draw_sharp_text(image, (1, y), row, (245, 250, 255) if idx % 2 == 0 else (205, 224, 222), FONT)
        y += 8
    return _webp(image)


def _world_cup_tracker():
    image, draw = _simple_header("USA GROUP D", (70, 220, 125))
    rows = [("1", "USA", "PTS 6"), ("2", "PAR", "PTS 4"), ("3", "AUS", "PTS 1")]
    y = 7
    for rank, team, pts in rows:
        selected = team == "USA"
        draw_sharp_text(image, (1, y), rank, (70, 220, 125), FONT)
        draw_sharp_text(image, (8, y), team, (255, 235, 95) if selected else (245, 250, 255), BOLD)
        w = draw.textbbox((0, 0), pts, font=FONT)[2]
        draw_sharp_text(image, (63 - w, y), pts, (70, 220, 125) if selected else (145, 165, 182), FONT)
        y += 8
    return _webp(image)


def _world_cup_golden_boot():
    image, draw = _simple_header("GOLD BOOT", (255, 210, 80))
    rows = [("1", "BALOGUN", "2"), ("2", "RAMOS", "1"), ("3", "MARTIN", "1")]
    y = 7
    for rank, name, goals in rows:
        draw_sharp_text(image, (1, y), rank, (255, 210, 80), FONT)
        draw_sharp_text(image, (8, y), name, (245, 250, 255), FONT)
        w = draw.textbbox((0, 0), goals, font=BOLD)[2]
        draw_sharp_text(image, (63 - w, y - 1), goals, (255, 210, 80), BOLD)
        y += 8
    return _webp(image)


def _stock():
    image = Image.new("RGB", (64, 32), (0, 4, 8))
    draw = ImageDraw.Draw(image)
    draw.polygon([(3, 13), (9, 7), (15, 13), (9, 19)], fill=(120, 145, 170))
    draw.polygon([(9, 7), (15, 13), (9, 16), (3, 13)], fill=(220, 230, 240))
    draw_sharp_text(image, (20, 0), "ETH", (245, 250, 255), BOLD)
    draw_sharp_text(image, (20, 9), "$3560", (80, 235, 100), BOLD)
    draw_sharp_text(image, (20, 19), "+1.4%", (80, 235, 100), FONT)
    return _webp(image)


def _market():
    image, draw = _simple_header("MARKETS", (100, 190, 255))
    rows = [("DOW", "+0.4%"), ("S&P", "+0.8%"), ("NAS", "+1.1%")]
    y = 7
    for label, pct in rows:
        draw_sharp_text(image, (1, y), label, (245, 250, 255), FONT)
        w = draw.textbbox((0, 0), pct, font=FONT)[2]
        draw_sharp_text(image, (63 - w, y), pct, (80, 220, 120), FONT)
        y += 8
    return _webp(image)


def _market_status():
    image, draw = _simple_header("MARKET", (100, 190, 255))
    _center(image, "OPEN", 5, (80, 220, 120), BIG)
    _center(image, "CLOSES 2H", 23, (160, 180, 195), FONT)
    return _webp(image)


def _portfolio():
    image = Image.new("RGB", (64, 32), (0, 5, 15))
    draw = ImageDraw.Draw(image)
    _center(image, "PORTFOLIO", -3, (100, 190, 255), BOLD)
    _center(image, "$12.4K", 6, (245, 250, 255), BIG)
    draw_sharp_text(image, (1, 22), "+$184", (80, 220, 120), FONT)
    draw_sharp_text(image, (37, 22), "+1.5%", (80, 220, 120), FONT)
    return _webp(image)


def _hubitat(title="KITCHEN", value="72.4", attr="TEMP", color=(255, 195, 80)):
    image, draw = _simple_header(title[:10], (160, 190, 230))
    _center(image, value, 2, color, BIG)
    _center(image, attr, 21, (80, 105, 130), FONT)
    return _webp(image)


def _hubitat_multi():
    image, draw = _simple_header("HUBITAT", (160, 190, 230))
    rows = [("DOOR", "CLOSED", (80, 220, 120)), ("TEMP", "72", (255, 195, 80)), ("LOCK", "LOCKED", (80, 220, 120))]
    y = 7
    for name, val, color in rows:
        draw_sharp_text(image, (1, y), name, (150, 170, 185), FONT)
        w = draw.textbbox((0, 0), val, font=FONT)[2]
        draw_sharp_text(image, (63 - w, y), val, color, FONT)
        y += 8
    return _webp(image)


def _safety(text="ALL SECURE"):
    image, draw = _simple_header("SAFETY", (80, 220, 120))
    draw.rectangle((3, 11, 15, 25), outline=(80, 220, 120))
    draw.line((6, 18, 9, 22), fill=(80, 220, 120))
    draw.line((9, 22, 14, 14), fill=(80, 220, 120))
    draw_sharp_text(image, (20, 13), text[:10], (245, 250, 255), BOLD)
    return _webp(image)


def _flight():
    image = Image.new("RGB", (64, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    draw.polygon([(2, 1), (13, 1), (16, 5), (11, 15), (2, 15)], fill=(210, 35, 45))
    draw.polygon([(2, 2), (8, 8), (3, 15)], fill=(20, 80, 180))
    draw_sharp_text(image, (19, -3), "DL2887", (245, 250, 255), BOLD)
    draw_sharp_text(image, (19, 6), "A321", (180, 200, 210), FONT)
    draw_sharp_text(image, (19, 14), "BOS>MCO", (180, 200, 210), FONT)
    draw_sharp_text(image, (1, 23), "ETA 6:26", (80, 220, 170), FONT)
    return _webp(image)


def _airport():
    image, draw = _simple_header("AIRPORT", (80, 220, 170))
    _center(image, "BOS", 7, (245, 250, 255), BOLD)
    _center(image, "NO DELAYS", 16, (80, 220, 120), FONT)
    _center(image, "FAA STATUS", 24, (150, 170, 185), FONT)
    return _webp(image)


def _commute():
    image, draw = _simple_header("COMMUTE", (80, 180, 255))
    _center(image, "HOME > WORK", 8, (245, 250, 255), FONT)
    _center(image, "27 MIN", 17, (80, 220, 120), BOLD)
    return _webp(image)


def _gas():
    image, draw = _simple_header("GAS", (255, 210, 80))
    draw.rectangle((2, 10, 13, 25), outline=(255, 210, 80))
    draw.rectangle((5, 13, 10, 16), fill=(80, 180, 255))
    draw_sharp_text(image, (19, 9), "$3.28", (245, 250, 255), BOLD)
    draw_sharp_text(image, (19, 19), "REGULAR", (150, 170, 185), FONT)
    return _webp(image)


def _dns():
    image, draw = _simple_header("PI-HOLE", (80, 220, 170))
    draw_sharp_text(image, (1, 9), "BLOCK", (145, 165, 182), FONT)
    draw_sharp_text(image, (39, 8), "1.2K", (245, 250, 255), BOLD)
    draw_sharp_text(image, (1, 18), "TOTAL", (145, 165, 182), FONT)
    draw_sharp_text(image, (40, 18), "22K", (200, 220, 235), FONT)
    draw_sharp_text(image, (41, 25), "5.4%", (255, 210, 80), FONT)
    return _webp(image)


def _github():
    image, draw = _simple_header("GITHUB", (145, 180, 255))
    draw_sharp_text(image, (1, 8), "PIXORA", (245, 250, 255), BOLD)
    draw_sharp_text(image, (1, 16), "v1.3.18", (80, 220, 170), FONT)
    draw_sharp_text(image, (25, 24), "TODAY", (150, 170, 185), FONT)
    return _webp(image)


def _github_issues():
    image, draw = _simple_header("GITHUB", (145, 180, 255))
    _center(image, "7", 5, (245, 250, 255), BIG)
    _center(image, "ISSUES", 23, (150, 170, 185), FONT)
    return _webp(image)


def _pixora_update():
    image, draw = _simple_header("PIXORA UPDATE", (80, 225, 205))
    draw_sharp_text(image, (1, 9), "APP", (145, 165, 182), FONT)
    draw_sharp_text(image, (35, 8), "v1.3.19", (245, 250, 255), BOLD)
    draw_sharp_text(image, (1, 18), "CARDS", (145, 165, 182), FONT)
    draw_sharp_text(image, (48, 17), "+4", (255, 210, 80), BOLD)
    _center(image, "BOTH READY", 24, (150, 170, 185), FONT)
    return _webp(image)


def _rss():
    image, draw = _simple_header("NEWS", (80, 220, 170))
    draw_sharp_text(image, (1, 10), "PIXORA ADDS", (245, 250, 255), FONT)
    draw_sharp_text(image, (1, 20), "NEW CARDS", (245, 250, 255), FONT)
    return _webp(image)


def _uptime():
    image, draw = _simple_header("SITE", (80, 180, 255))
    _center(image, "UP", 5, (80, 220, 120), BIG)
    _center(image, "142ms", 23, (150, 170, 185), FONT)
    return _webp(image)


def _ping():
    image, draw = _simple_header("PING", (80, 220, 170))
    _center(image, "24ms", 5, (80, 220, 120), BIG)
    _center(image, "1.1.1.1", 23, (150, 170, 185), FONT)
    return _webp(image)


def _lastfm():
    image, draw = _simple_header("LAST.FM", (220, 35, 50))
    draw.ellipse((2, 12, 13, 23), outline=(220, 35, 50), width=2)
    draw.polygon([(12, 16), (18, 12), (18, 24)], fill=(220, 35, 50))
    draw_sharp_text(image, (23, 8), "SONG", (245, 250, 255), FONT)
    draw_sharp_text(image, (23, 17), "ARTIST", (150, 170, 185), FONT)
    draw_sharp_text(image, (47, 24), "LIVE", (80, 220, 120), FONT)
    return _webp(image)


def _music_assistant():
    image, draw = _simple_header("MUSIC ASST", (80, 220, 170))
    draw.ellipse((3, 12, 14, 23), outline=(80, 220, 170), width=2)
    draw.rectangle((13, 9, 16, 19), fill=(80, 220, 170))
    draw.line((16, 9, 20, 11), fill=(80, 220, 170), width=2)
    draw_sharp_text(image, (24, 8), "SONG", (245, 250, 255), FONT)
    draw_sharp_text(image, (24, 17), "ARTIST", (150, 170, 185), FONT)
    draw_sharp_text(image, (43, 24), "PLAY", (80, 220, 170), FONT)
    return _webp(image)


def _home_assistant():
    image, draw = _simple_header("OUTDOOR", (65, 190, 255))
    _center(image, "72.4F", 6, (245, 250, 255), BIG)
    draw_sharp_text(image, (1, 24), "SENSOR", (150, 170, 185), FONT)
    return _webp(image)


def _shopify_orders():
    image, draw = _simple_header("SHOPIFY", (70, 220, 140))
    draw_sharp_text(image, (2, 8), "WK", (150, 170, 185), FONT)
    draw_sharp_text(image, (45, 7), "12", (245, 250, 255), BOLD)
    draw_sharp_text(image, (2, 20), "ALL", (150, 170, 185), FONT)
    draw_sharp_text(image, (38, 19), "1.2K", (245, 250, 255), BOLD)
    return _webp(image)


def _trash():
    image, draw = _simple_header("TRASH", (70, 210, 120))
    _center(image, "TOMORROW", 9, (245, 250, 255), BOLD, 15, 63)
    _center(image, "WED 5/13", 18, (160, 190, 210), FONT, 15, 63)
    draw.rectangle((3, 13, 12, 27), outline=(70, 210, 120))
    draw.line((2, 12, 13, 12), fill=(70, 210, 120))
    return _webp(image)


def _sunrise():
    image = Image.new("RGB", (64, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    draw.ellipse((5, 7, 19, 21), fill=(255, 196, 58))
    draw.line((2, 25, 24, 25), fill=(60, 180, 225))
    draw.line((12, 3, 12, 5), fill=(255, 226, 110))
    draw.line((1, 14, 4, 14), fill=(255, 226, 110))
    draw.line((20, 14, 23, 14), fill=(255, 226, 110))
    draw_sharp_text(image, (27, 5), "RISE", (255, 210, 80), FONT)
    draw_sharp_text(image, (27, 13), "5:22", (235, 245, 255), BOLD)
    draw_sharp_text(image, (27, 21), "SET 8:04", (255, 125, 80), FONT)
    return _webp(image)


def _word_day():
    image, draw = _simple_header("GLIMMER", (100, 200, 255))
    _center(image, "FAINT", 12, (220, 235, 245), FONT)
    _center(image, "SHINE", 21, (220, 235, 245), FONT)
    return _webp(image)


def _quote_day():
    image = Image.new("RGB", (64, 32), (0, 0, 0))
    draw_sharp_text(image, (2, 2), "SMALL STEPS", (245, 250, 255), FONT)
    draw_sharp_text(image, (8, 12), "STILL", (245, 250, 255), FONT)
    draw_sharp_text(image, (6, 22), "MOVE.", (245, 250, 255), FONT)
    return _webp(image)


def _joke_day():
    image = Image.new("RGB", (64, 32), (0, 0, 0))
    draw_sharp_text(image, (4, 2), "LED JOKE:", (255, 220, 80), FONT)
    draw_sharp_text(image, (1, 12), "IT LIT UP.", (245, 250, 255), FONT)
    draw_sharp_text(image, (22, 22), "HA!", (255, 220, 80), BOLD)
    return _webp(image)


def _battery():
    image = Image.new("RGB", (64, 32), (0, 5, 9))
    draw = ImageDraw.Draw(image)
    draw.rectangle((3, 9, 18, 22), outline=(90, 220, 120))
    draw.rectangle((19, 13, 21, 18), fill=(90, 220, 120))
    draw.rectangle((5, 11, 14, 20), fill=(90, 220, 120))
    draw_sharp_text(image, (25, -3), "BATTERY", (90, 220, 120), BOLD)
    draw_sharp_text(image, (25, 10), "SMOKE", (235, 245, 255), FONT)
    draw_sharp_text(image, (25, 19), "SENSORS", (235, 245, 255), FONT)
    return _webp(image)


def _package():
    image = Image.new("RGB", (64, 32), (0, 4, 9))
    draw = ImageDraw.Draw(image)
    draw.rectangle((3, 8, 18, 22), outline=(190, 150, 80))
    draw.line((3, 8, 10, 3, 18, 8), fill=(220, 175, 90))
    draw.line((10, 3, 10, 17), fill=(120, 90, 50))
    draw_sharp_text(image, (24, -3), "UPS", (255, 210, 110), BOLD)
    draw_sharp_text(image, (24, 10), "OUT FOR", (235, 245, 255), FONT)
    draw_sharp_text(image, (24, 19), "DELIVERY", (235, 245, 255), FONT)
    return _webp(image)


def _mega_millions():
    image, draw = _simple_header("MEGA MILL", (255, 215, 70))
    _center(image, "37 47 49", 8, (245, 250, 255), BOLD)
    _center(image, "51 58 +16", 17, (255, 220, 80), BOLD)
    _center(image, "$215 MILLION", 25, (175, 150, 205), FONT)
    return _webp(image)


def _megabucks():
    image, draw = _simple_header("MEGABUCKS", (70, 230, 170))
    _center(image, "4 7 15", 8, (245, 250, 255), BOLD)
    _center(image, "20 24 25", 17, (245, 250, 255), BOLD)
    _center(image, "MAY 11 2026", 25, (120, 190, 170), FONT)
    return _webp(image)


def _standings():
    image, draw = _simple_header("MLB STAND", (117, 231, 214))
    rows = [("1", "BOS", "28-13"), ("2", "NYY", "25-16"), ("3", "TB", "24-17")]
    y = 7
    for rank, team, rec in rows:
        draw_sharp_text(image, (1, y), rank, (117, 231, 214), FONT)
        draw_sharp_text(image, (8, y), team, (245, 250, 255), BOLD)
        draw_sharp_text(image, (31, y), rec, (190, 205, 218), FONT)
        y += 8
    return _webp(image)


def _fantasy(kind="MATCHUP", platform="FANTASY", color=(117, 231, 214)):
    image, draw = _simple_header(platform, color)
    draw.rectangle((2, 11, 29, 21), fill=(13, 28, 36), outline=(48, 82, 96))
    draw.rectangle((35, 11, 62, 21), fill=(13, 28, 36), outline=(48, 82, 96))
    _center(image, "YOU", 10, (245, 250, 255), BOLD, 2, 29)
    _center(image, "OPP", 10, (245, 250, 255), BOLD, 35, 62)
    _center(image, "88", 21, (80, 225, 150), BOLD, 2, 29)
    _center(image, "82", 21, (255, 190, 70), BOLD, 35, 62)
    _center(image, kind, 24, (160, 180, 195), FONT)
    return _webp(image)


def _message(title, l1, l2="", color=(24, 210, 190)):
    image, draw = _simple_header(title, color)
    _center(image, l1, 10, (245, 250, 255), BOLD)
    if l2:
        _center(image, l2, 21, (150, 170, 185), FONT)
    return _webp(image)


CUSTOM = {
    "clock": _clock,
    "clock_calendar": _clock_calendar,
    "clock_day_progress": _clock_day_progress,
    "clock_week_strip": _clock_week_strip,
    "weather_forecast": _weather_forecast,
    "weather_alert": _weather_alert,
    "weather_radar_loop": _weather_radar_loop,
    "air_quality": _air_quality,
    "mlb": lambda: _sport("TOP 7TH", "HOU", "BOS", "3-1", (245, 150, 65)),
    "nba": lambda: _sport("3RD 4:22", "BOS", "NYK", "82-79", (245, 150, 65)),
    "wnba": lambda: _sport("2ND 1:12", "CON", "NY", "45-40", (255, 170, 210)),
    "nfl": lambda: _sport("3RD 8:12", "NE", "BUF", "17-14", (80, 150, 255)),
    "nhl": lambda: _sport("2ND 6:41", "BOS", "MTL", "2-1", (80, 220, 255)),
    "college_football": lambda: _sport("4TH 2:10", "BC", "ND", "24-21", (80, 150, 255)),
    "mens_college_basketball": lambda: _sport("2ND 9:30", "DUKE", "UNC", "60-58", (245, 150, 65)),
    "womens_college_basketball": lambda: _sport("3RD 1:18", "CONN", "SC", "50-48", (255, 170, 210)),
    "college_baseball": lambda: _sport("BOT 5TH", "UVA", "FSU", "5-4", (95, 210, 130)),
    "college_softball": lambda: _sport("TOP 6TH", "OU", "TEX", "4-2", (245, 120, 170)),
    "mens_college_hockey": lambda: _sport("2ND 8:01", "BC", "BU", "3-2", (80, 220, 255)),
    "mens_college_lacrosse": lambda: _sport("3RD 4:12", "ND", "UVA", "9-8", (105, 230, 180)),
    "womens_college_lacrosse": lambda: _sport("2ND 6:02", "BC", "UNC", "7-6", (255, 150, 210)),
    "pll_lacrosse": lambda: _sport("4TH 1:22", "CAN", "ATL", "13-11", (220, 120, 255)),
    "nll_lacrosse": lambda: _sport("3RD 2:45", "BUF", "TOR", "10-9", (170, 125, 255)),
    "ufl": lambda: _sport("2ND 5:44", "DC", "STL", "14-10", (80, 190, 255)),
    "cfl": lambda: _sport("3RD 9:00", "BCL", "WBB", "21-17", (235, 70, 80)),
    "nba_g_league": lambda: _sport("4TH 3:02", "MNE", "STO", "95-90", (85, 180, 255)),
    "soccer": lambda: _sport("78'", "BOS", "MIA", "2-1", (80, 220, 170)),
    "womens_college_volleyball": lambda: _sport("SET 3", "UK", "UCLA", "2-1", (255, 185, 85)),
    "fifa_world_cup": _fifa_world_cup,
    "world_cup_golden_boot": _world_cup_golden_boot,
    "world_cup_today": _world_cup_today,
    "world_cup_tracker": _world_cup_tracker,
    "pga": lambda: _event_sport("PGA", "golf"),
    "lpga": lambda: _event_sport("LPGA", "golf"),
    "f1": lambda: _event_sport("F1", "race"),
    "nascar": lambda: _event_sport("NASCAR", "race"),
    "stocks": _stock,
    "market_indexes": _market,
    "market_status": _market_status,
    "portfolio_pulse": _portfolio,
    "crypto_watch": lambda: _stock(),
    "hubitat": _hubitat,
    "hubitat_multi": _hubitat_multi,
    "hubitat_safety": _safety,
    "flight_track": _flight,
    "airport_delays": _airport,
    "commute_time": _commute,
    "gas_price_local": _gas,
    "dns_stats": _dns,
    "github_release_watch": _github,
    "github_issues_watch": _github_issues,
    "pixora_update_watch": _pixora_update,
    "rss_headlines": _rss,
    "website_uptime": _uptime,
    "ping_monitor": _ping,
    "lastfm_now_playing": _lastfm,
    "music_assistant_now_playing": _music_assistant,
    "home_assistant_entity": _home_assistant,
    "shopify_orders": _shopify_orders,
    "trash_recycling": _trash,
    "sunrise_sunset": _sunrise,
    "word_of_day": _word_day,
    "quote_of_day": _quote_day,
    "joke_of_day": _joke_day,
    "battery_reminder": _battery,
    "package_watch": _package,
    "mega_millions": _mega_millions,
    "megabucks": _megabucks,
    "sports_standings": _standings,
    "fantasy_matchup": lambda: _fantasy("MATCHUP", "FANTASY", (117, 231, 214)),
    "fantasy_lineup": lambda: _fantasy("LINEUP", "FANTASY", (117, 231, 214)),
    "fantasy_standings": lambda: _fantasy("STAND", "FANTASY", (117, 231, 214)),
    "espn_fantasy_matchup": lambda: _fantasy("MATCHUP", "ESPN", (255, 70, 70)),
    "espn_fantasy_lineup": lambda: _fantasy("LINEUP", "ESPN", (255, 70, 70)),
    "espn_fantasy_standings": lambda: _fantasy("STAND", "ESPN", (255, 70, 70)),
    "yahoo_fantasy_matchup": lambda: _fantasy("MATCHUP", "YAHOO", (165, 105, 255)),
    "yahoo_fantasy_lineup": lambda: _fantasy("LINEUP", "YAHOO", (165, 105, 255)),
    "yahoo_fantasy_standings": lambda: _fantasy("STAND", "YAHOO", (165, 105, 255)),
    "youtube_followers": lambda: render_counter_card("YOUTUBE", "Pixora", 123456, (255, 0, 0), "SUBS", "youtube"),
    "facebook_followers": lambda: render_counter_card("FACEBOOK", "Pixora", 123456, (24, 119, 242), "FOLLOW", "facebook"),
    "twitter_followers": lambda: render_counter_card("X", "@pixora", 123456, (245, 250, 255), "FOLLOW", "x"),
    "instagram_followers": lambda: render_counter_card("INSTAGRAM", "pixora", 123456, (225, 48, 108), "FOLLOW", "instagram"),
    "countdown": lambda: _message("COUNTDOWN", "14 DAYS", "VACATION", (80, 180, 255)),
    "countdown_confetti": lambda: _message("COUNTDOWN", "14 DAYS", "CONFETTI", (255, 120, 190)),
    "disney": lambda: _message("DISNEY", "42 DAYS", "MAGIC", (255, 210, 80)),
    "disney_park_hours": lambda: _message("MAGIC", "9A-10P", "EE 8:30A", (120, 205, 255)),
    "disney_wait_times": lambda: _message("DISNEY", "75 MIN", "WAIT", (120, 205, 255)),
    "gcal": lambda: _message("CALENDAR", "MEETING", "2:30PM", (80, 180, 255)),
    "moon_phase": lambda: _message("MOON", "WAXING", "61%", (200, 220, 255)),
}


SAMPLE_OPTIONS = {
    "clock": {"zipCode": "02134"},
    "weather_forecast": {"zipCode": "02134"},
    "weather_alert": {"zipCode": "02134"},
    "weather_radar_loop": {"zipCode": "02134"},
    "weather_mood": {"zipCode": "02134"},
    "air_quality": {"zipCode": "02134"},
}


def _load_module(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    count = 0
    for path in sorted(ADDONS_DIR.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        mod = _load_module(path)
        card_id = getattr(mod, "CARD_ID", path.stem)
        name = getattr(mod, "CARD_NAME", card_id)
        body = None
        if card_id in CUSTOM:
            body = CUSTOM[card_id]()
        else:
            try:
                body = mod.render(SAMPLE_OPTIONS.get(card_id, {}))
            except Exception:
                body = None
            if not body:
                body = _fallback(card_id, name)
        _save(card_id, body)
        count += 1
    print(f"Generated {count} card previews in {OUT_DIR}")


if __name__ == "__main__":
    main()
