"""A Christmas snowball fight for a 64 + 128 + 64 Pixora LED wall."""
from io import BytesIO
from math import sin, tau
from random import Random

from PIL import Image, ImageDraw

CARD_ID = "snowball_snowman"
CARD_NAME = "Snowball Snowman"
CARD_DETAIL = "Mr. and Mrs. Snowman hold hands between Christmas trees while kids trade snowballs."
CARD_VERSION = "1.1.0"
CARD_AUTHOR = "PixoraHQ"
CARD_WALL_WIDTHS = [64, 128, 64]
CARD_OPTIONS = [
    {"key": "wallTarget", "label": "Play on display group", "type": "select",
     "default": "group_wall", "choices": [{"value": "group_wall", "label": "Display group"}]},
]

WIDTH, HEIGHT = 256, 32
FRAME_COUNT, FRAME_MS = 160, 100
SNOW = "#e5f5ff"
GOLD = "#ffda79"


def village():
    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        draw.line((0, y, 255, y), fill=(10 + y // 2, 16 + y, 40 + y * 2))
    draw.ellipse((218, 2, 228, 12), fill="#ffe3af")
    draw.polygon([(0, 22), (23, 18), (56, 22), (96, 18), (133, 22),
                  (173, 18), (211, 22), (255, 18), (255, 31), (0, 31)], fill="#526a92")
    for x, y, size in ((12, 7, 12), (34, 12, 9), 
                        (221, 12, 9), (244, 5, 14)):
        for tier in (0, 4, 8):
            half = (size + tier) // 3
            draw.polygon([(x, y+tier), (x-half, y+tier+6), (x+half, y+tier+6)], fill="#195455")
            draw.line((x, y+tier, x-half, y+tier+6), fill="#77a9b4")
        if size >= 12:
            for dx, dy, color in ((0, 4, GOLD), (-2, 9, "#ff786f"),
                                  (3, 11, "#7bf0cc"), (-3, 13, GOLD)):
                draw.point((x+dx, y+dy), fill=color)
    draw.polygon([(0, 24), (30, 22), (63, 24), (101, 22), (137, 24),
                  (180, 22), (215, 24), (255, 22), (255, 31), (0, 31)], fill="#aecce8")
    draw.line([(0, 30), (31, 30), (50, 29), (80, 30), (134, 30),
               (153, 31), (186, 29), (221, 30), (255, 29)], fill="#cfe4f4")
    return image


def christmas_tree(draw, x, phase):
    draw.rectangle((x-2, 24, x+2, 28), fill="#795244")
    for top, half in ((6, 5), (11, 8), (16, 11)):
        draw.polygon([(x, top), (x-half, top+9), (x+half, top+9)], fill="#207658")
        draw.line((x, top, x-half, top+9), fill="#80b9a5")
    for dx, y, color in ((0, 11, "#ff7a80"), (-3, 15, GOLD), (3, 17, "#7deaff"),
                         (-5, 20, "#ff8b9d"), (1, 20, GOLD), (6, 23, "#ff8977"),
                         (-7, 24, "#7deaff"), (-1, 23, "#ee9bff")):
        draw.point((x+dx, y), fill=SNOW if (phase+dx+y) % 7 == 0 else color)
    draw.line((x-2, 5, x+2, 5), fill=GOLD)
    draw.line((x, 3, x, 7), fill=GOLD)
    draw.point((x, 5), fill="#fff6bd")


def snowman(draw, x, y, index, partner_side, scarf, hat):
    phase = (index+13*partner_side)*tau/40
    head = round(sin(phase))
    wink = (index + (0 if partner_side == 1 else 32)) % 80 in (14, 15, 16)
    shadow = "#91b7db"
    for dx, dy, radius in ((0, -5, 7), (0, -12, 6), (head, -19, 5)):
        draw.ellipse((x+dx-radius, y+dy-radius, x+dx+radius, y+dy+radius), fill=shadow)
        draw.ellipse((x+dx-radius, y+dy-radius, x+dx+radius-2, y+dy+radius-2), fill=SNOW)
    draw.line((x-5, y-15, x+5, y-15), fill=scarf, width=2)
    draw.line([(x-4*partner_side, y-15), (x-7*partner_side, y-11),
               (x-9*partner_side, y-11)], fill=scarf, width=2)
    if partner_side == 1:
        draw.rectangle((x+head-4, y-27, x+head+3, y-23), fill=hat)
        draw.line((x+head-6, y-23, x+head+5, y-23), fill=hat, width=2)
        draw.line((x+head-4, y-25, x+head+3, y-25), fill=scarf)
    else:
        draw.rounded_rectangle((x+head-5, y-26, x+head+4, y-22), radius=2, fill=hat)
        draw.line((x+head-5, y-23, x+head+4, y-23), fill="#ff9eba")
        draw.point((x+head, y-27), fill=SNOW)
    for dx, dy in ((head, -17), (0, -11), (0, -7), (0, -3)):
        draw.point((x+dx, y+dy), fill="#26334c")
    draw.point((x+head-2, y-20), fill="#26334c")
    draw.line((x+head+2, y-20+wink, x+head+2+wink, y-20+wink), fill="#26334c")
    draw.line((x+head, y-19, x+head+3*partner_side, y-18), fill="#ff9c4a")
    outside = -partner_side
    glove_y = y-10+round(2*sin(phase))
    draw.line([(x+5*outside, y-10), (x+8*outside, y-12),
               (x+11*outside, glove_y)], fill="#86513f", width=2)
    draw.rectangle((x+11*outside-1, glove_y-1, x+11*outside+1, glove_y+1), fill=scarf)


def snowman_couple(draw, index):
    snowman(draw, 115, 28, index, 1, "#e74657", "#262541")
    snowman(draw, 141, 28, index, -1, "#32b789", "#a5346f")
    hand_y = 18 + round(2*sin(index*tau/40))
    for x, side, color in ((115, 1, "#e74657"), (141, -1, "#32b789")):
        draw.line([(x+5*side, 18), (x+9*side, 20), (128, hand_y)], fill="#86513f", width=2)
        end = 128-side
        draw.ellipse((end-1, hand_y-1, end+1, hand_y+1), fill=color)


def child(draw, x, y, facing, coat, hat, action, phase):
    def line(points, color, width=1):
        draw.line([(x+facing*dx, y+dy) for dx, dy in points], fill=color, width=width)

    draw.ellipse((x-6, 28, x+6, 30), fill="#809fc4")
    step = round(2*sin(phase))
    line([(-2, -5), (-3+step, 0), (-1+step, 0)], "#293451", 2)
    line([(2, -5), (3-step, 0), (5-step, 0)], "#3f4b69", 2)
    draw.rounded_rectangle((x-4, y-12, x+4, y-4), radius=2, fill=coat)
    line([(-2, -11), (-5, -8), (-6, -6)], coat, 2)
    draw.ellipse((x-4, y-18, x+4, y-11), fill="#ffc599" if facing == 1 else "#b97756")
    draw.rounded_rectangle((x-4, y-20, x+4, y-15), radius=2, fill=hat)
    draw.point((x, y-21), fill=SNOW)
    draw.point((x+3*facing, y-14), fill="#30283b")
    line([(-3, -11), (3, -11)], GOLD)
    hand = {"ready": (6, -8), "windup": (-3, -16), "throw": (8, -15), "duck": (6, -13)}[action]
    line([(2, -10), hand], coat, 2)
    line([hand, (hand[0]+1, hand[1])], hat, 2)
    if action == "windup":
        hx, hy = x+facing*hand[0], y+hand[1]-2
        draw.ellipse((hx-1, hy-1, hx+1, hy+1), fill=SNOW)


def frame_at(index, background, flakes):
    image = background.copy()
    draw = ImageDraw.Draw(image)
    for x, y, speed in flakes:
        draw.point(((x + index//(4+speed)) % WIDTH, (y+index//speed) % 22), fill="#94b8d9")

    # The four volleys alternate directions. The receiver ducks before impact.
    volley, tick = divmod(index, 40)
    sender = volley % 2
    positions = (54 + round(4*sin(index*tau/80)), 202 - round(4*sin(index*tau/80)))
    christmas_tree(draw, 82, index//5)
    christmas_tree(draw, 174, index//5)
    for side, (coat, hat) in enumerate((("#dd4562", "#2cae93"), ("#278fda", "#ef624b"))):
        action = "ready"
        if side == sender and 3 <= tick < 10:
            action = "windup"
        if side == sender and 10 <= tick < 16:
            action = "throw"
        if side != sender and 24 <= tick < 33:
            action = "duck"
        y = 28 if action == "duck" else 26
        child(draw, positions[side], y, 1-2*side, coat, hat, action, index*tau/16)

    facing = 1-2*sender
    start = positions[sender]+8*facing
    end = positions[1-sender]-10*facing
    if 10 <= tick < 29:
        t = (tick-10)/18
        bx = round(start + (end-start)*t)
        by = round(11 + 13*t - 38*t*(1-t))
        draw.line((bx-3*facing, by, bx-facing, by), fill="#a5c6e5")
        draw.ellipse((bx-1, by-1, bx+1, by+1), fill=SNOW)
    if 29 <= tick < 35:
        for i, (dx, dy) in enumerate(((-2,-1), (0,-3), (2,-2), (3,0), (-1,2))):
            age = tick-28
            draw.point((end + dx*age//2, 24 + dy*age//2), fill=SNOW if i % 2 else "#b7d8ee")
    snowman_couple(draw, index)
    return image


def animation_frames():
    rng = Random(2512)
    flakes = [(rng.randrange(WIDTH), rng.randrange(22), rng.randrange(2, 6)) for _ in range(57)]
    background = village()
    return [frame_at(index, background, flakes) for index in range(FRAME_COUNT)]


def render(options=None):
    width = (options or {}).get("_width", 64)
    output = BytesIO()
    frames = animation_frames()
    if width == WIDTH:
        frames[0].save(output, "WEBP", save_all=True, append_images=frames[1:],
                       duration=FRAME_MS, lossless=True, loop=1, method=0)
    else:
        width = 128 if width == 128 else 64
        left = (WIDTH-width)//2
        frames[40].crop((left, 0, left+width, HEIGHT)).save(output, "PNG")
    return output.getvalue()
