"""Turkey Chase, an offline 64 + 128 + 64 LED Studio animation."""
from io import BytesIO
import math
import random

from PIL import Image, ImageDraw

CARD_ID = "turkey_chase"
CARD_NAME = "Turkey Chase"
CARD_DETAIL = "A Thanksgiving chase across three panels ordered 64, 128, 64."
CARD_VERSION = "1.0.0"
CARD_AUTHOR = "PixoraHQ"
CARD_WALL_WIDTHS = [64, 128, 64]
CARD_OPTIONS = [
    {"key": "wallTarget", "label": "Play on display group", "type": "select",
     "default": "group_wall", "choices": [{"value": "group_wall", "label": "Display group"}]},
]

WIDTH = 256
HEIGHT = 32
FRAME_MS = 100
FRAMES = 124
GROUND = 28
GOLD = "#ffbe56"
RUST = "#e05d37"
RED = "#f34839"
BROWN = "#a24b2c"
CREAM = "#fff3be"
INK = "#160d17"


def backdrop():
    image = Image.new("RGB", (WIDTH, HEIGHT), "#080b1b")
    draw = ImageDraw.Draw(image)
    for y in range(23):
        draw.line((0, y, WIDTH - 1, y), fill=(9 + y, 10 + y // 3, 29 + y // 3))
    draw.ellipse((212, 3, 222, 13), fill="#ffc470")
    draw.ellipse((209, 1, 219, 11), fill="#101022")
    draw.polygon([(0, 21), (24, 15), (51, 21), (81, 16), (115, 22),
                  (144, 16), (177, 21), (209, 17), (256, 22), (256, 29), (0, 29)], fill="#302033")
    for x in (9, 44, 71, 167, 202, 239, 253):
        draw.polygon([(x - 6, 20), (x - 3, 13), (x, 14), (x + 3, 10), (x + 7, 20)],
                     fill="#532939")
        draw.line((x, 16, x, 26), fill="#4a2e2f")
        draw.point((x + 3, 15), fill="#965031")
    draw.rectangle((0, GROUND, WIDTH - 1, HEIGHT - 1), fill="#36211f")
    draw.line((0, GROUND, WIDTH - 1, GROUND), fill="#94512b")
    for x in range(4, WIDTH, 9):
        y = 29 + (x % 3)
        draw.line((x, y, x + 2, y), fill="#623626")
    return image


def turkey(draw, x, feet, front=False, fan=0, gait=0, panic=False):
    y = feet - 12

    def oval(box, color):
        a, b, c, d = box
        draw.ellipse((x + a, y + b, x + c, y + d), fill=color)

    def line(points, color, width=1):
        draw.line([(x + a, y + b) for a, b in points], fill=color, width=width)

    if front:
        # Outer plumes are drawn first so all seven golden tips stay readable.
        for index in (-3, 3, -2, 2, -1, 1, 0):
            spread = index * (2 + 2.8 * fan)
            top = -5 - 6 * fan + abs(index) * (0.5 + 0.55 * fan)
            end = (round(spread), round(top))
            line([(0, 3), end], (RUST, RED, GOLD, RUST)[abs(index)], 4)
            oval((end[0] - 2, end[1] - 2, end[0] + 2, end[1] + 1), GOLD)
            line([(0, 4), (end[0], end[1] + 2)], "#7a312c")
    else:
        for tip, color in [((-10, -6), RUST), ((-13, -3), GOLD), ((-11, 0), RED)]:
            line([(-4, 3), tip], color, 3)
    stride = round(gait)
    for side, swing in [(-1, stride), (1, -stride)]:
        ankle = side * 3 + swing
        line([(side * 3, 7), (ankle, 11), (ankle + 2, 12)], GOLD)
    oval((-7, -2, 7, 9), BROWN)
    oval((-6, 1, 6, 8), "#c87541")
    if front:
        oval((-8, 0, -4, 6), "#86402c")
        oval((4, 0, 8, 6), "#86402c")
        oval((-3, -5, 3, 2), "#f0a666")
        for eye in (-2, 2):
            draw.point((x + eye, y - 3), fill=CREAM)
            draw.point((x + eye, y - 2), fill=INK)
        line([(-1, 0), (1, 0)], GOLD, 2)
        draw.point((x + 1, y + 2), fill=RED)
    else:
        line([(5, 2), (8, -5)], "#eb9f6f", 3)
        oval((6, -8, 11, -3), "#f3ba81")
        draw.point((x + 10, y - 6), fill=INK)
        draw.polygon([(x + 11, y - 6), (x + 15, y - 4), (x + 11, y - 3)], fill=GOLD)
        draw.point((x + 10, y - 2), fill=RED)
    if panic:
        for side in (-1, 1):
            line([(side * 5, 3), (side * 10, -1)], BROWN, 3)


def pilgrim(draw, x, feet, stride=0, aim=False, recoil=0):
    y = feet - 19
    for side in (-1, 1):
        toe = x + side * (2 + stride)
        draw.line((x + side, y + 12, toe, feet - 1), fill="#5f617e", width=3)
        draw.line((toe - 1, feet, toe + 2, feet), fill="#292537", width=2)
    draw.polygon([(x - 4, y + 6), (x + 3, y + 6), (x + 5, y + 14), (x - 5, y + 14)], fill="#575a78")
    draw.polygon([(x - 3, y + 6), (x + 4, y + 6), (x + 1, y + 10)], fill=CREAM)
    draw.rectangle((x - 4, y + 11, x + 4, y + 12), fill=INK)
    draw.point((x + 1, y + 11), fill=GOLD)
    draw.ellipse((x - 3, y, x + 5, y + 6), fill="#eeb17e")
    draw.point((x + 4, y + 3), fill=INK)
    draw.rectangle((x - 4, y - 4, x + 3, y), fill="#666985")
    draw.line((x - 6, y + 1, x + 6, y + 1), fill="#3d3e59", width=2)
    draw.rectangle((x - 4, y - 1, x + 3, y), fill=INK)
    draw.point((x + 2, y - 1), fill=GOLD)
    tip = (x + 22 - recoil, y + (7 if aim else 1))
    stock = (x + 1 - recoil, y + 10)
    draw.line((x - 2, y + 8, x + 7, y + 9), fill="#777c99", width=3)
    draw.line((*stock, *tip), fill="#d6bca4", width=2)
    draw.line((stock[0] - 3, stock[1] + 2, stock[0] + 7, stock[1] - 1), fill="#9a552e", width=3)
    return tip


def make_frame(background, t, feathers):
    image = background.copy()
    draw = ImageDraw.Draw(image)
    turkey_x = -16 + 144 * min(t / 3.9, 1)
    feet = GROUND
    if t < 3.9:
        turkey(draw, round(turkey_x), feet - round(abs(math.sin(t * 13))), gait=3 * math.sin(t * 15))
    elif t < 9:
        shock = max(0, t - 7.25)
        jump = round(9 * abs(math.sin(shock * 6.4)) * max(0, 1 - shock / 2)) if shock else 0
        turkey(draw, 128, feet - jump, front=True, fan=min((t - 4.5) / 2.65, 1) if 4.5 < t < 7.25 else (0.32 if shock else 0), panic=bool(shock))
        if 7.3 < t < 7.85:
            for x, y in [(114, 4), (141, 4), (112, 8), (144, 8)]:
                draw.line((x, y, x + 1, y + 2), fill=GOLD)
    else:
        turkey_x = 128 + 60 * (t - 9)
        turkey(draw, round(turkey_x), feet - round(2 * abs(math.sin(t * 20))), gait=5 * math.sin(t * 22), panic=True)
    if 4.6 <= t < 12.25:
        pilgrim_x = -23 + 72 * min((t - 4.6) / 2.15, 1)
        if t >= 9.15:
            pilgrim_x = 49 + 74 * (t - 9.15)
        moving = t < 6.75 or t >= 9.15
        muzzle = pilgrim(draw, round(pilgrim_x), feet - int(moving and abs(math.sin(t * 17)) > .6),
                         round(3 * math.sin(t * 19)) if moving else 0,
                         aim=not moving, recoil=3 if 7.25 <= t < 7.42 else 0)
        if 7.25 <= t < 7.43:
            x, y = muzzle
            draw.polygon([(x, y), (x + 4, y - 4), (x + 5, y - 1),
                          (x + 13, y), (x + 5, y + 2), (x + 3, y + 4)], fill=GOLD)
            draw.line((x, y, x + 8, y), fill=CREAM, width=2)
        if 7.35 <= t < 8.15:
            smoke = t - 7.35
            x, y = muzzle
            for i in range(4):
                cx, cy = x + 3 * i + round(13 * smoke), y - i - round(9 * smoke)
                r = 2 + round(3 * smoke)
                draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                             fill=(120 - int(smoke * 88), 118 - int(smoke * 90), 129 - int(smoke * 88)))
    if 7.25 <= t < 10.5:
        elapsed = t - 7.25
        for vx, vy, color, spin in feathers:
            x = round(128 + vx * elapsed)
            y = round(15 + vy * elapsed + 12 * elapsed ** 2)
            if y >= GROUND:
                y = GROUND - 1
            angle = spin + elapsed * 7
            dx, dy = round(2 * math.cos(angle)), round(2 * math.sin(angle))
            draw.line((x - dx, y - dy, x + dx, y + dy), fill=color, width=2)
            draw.point((x, y), fill=CREAM)
    return image


def animation_frames():
    background = backdrop()
    randomizer = random.Random(320)
    feathers = [(randomizer.uniform(-43, 43), randomizer.uniform(-34, -9),
                 randomizer.choice((GOLD, RUST, RED, "#eeb17e")), randomizer.random() * math.tau)
                for _ in range(22)]
    return [make_frame(background, index * FRAME_MS / 1000, feathers) for index in range(FRAMES)]


def render_wall(options=None):
    if (options or {}).get("_width", WIDTH) != WIDTH:
        raise ValueError("Turkey Chase needs a 64, 128, 64 display group.")
    frames = animation_frames()
    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:],
                   duration=FRAME_MS, lossless=True, loop=1, method=0)
    return out.getvalue()


def render(options=None):
    width = (options or {}).get("_width", 64)
    if width == WIDTH:
        return render_wall(options)
    width = 128 if width == 128 else 64
    # A regular card preview shows the center of the scene at native pixel size.
    still = make_frame(backdrop(), 5.7, ())
    out = BytesIO()
    still.crop(((WIDTH - width) // 2, 0, (WIDTH + width) // 2, HEIGHT)).save(out, "PNG")
    return out.getvalue()

