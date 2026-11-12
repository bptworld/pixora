"""An autumn harvest parade for a 64 + 128 + 64 Pixora LED wall."""
from io import BytesIO
from math import sin, tau
from random import Random

from PIL import Image, ImageDraw

CARD_ID = "thanksgiving_harvest_parade"
CARD_NAME = "Thanksgiving Harvest Parade"
CARD_DETAIL = "Three floats bring a pumpkin and turkey drummer, a cornucopia, and a Pilgrim dinner through falling autumn leaves."
CARD_VERSION = "1.1.0"
CARD_AUTHOR = "PixoraHQ"
CARD_WALL_WIDTHS = [64, 128, 64]
CARD_OPTIONS = [
    {"key": "wallTarget", "label": "Play on display group", "type": "select",
     "default": "group_wall", "choices": [{"value": "group_wall", "label": "Display group"}]},
]

WIDTH, HEIGHT = 256, 32
FRAME_COUNT, FRAME_MS = 246, 100
GOLD = "#ffd67d"
LEAF_COLORS = ("#ef8140", "#e8a340", "#c64e4d", "#ffc65e")


def backdrop():
    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        draw.line((0, y, WIDTH-1, y), fill=(30+4*y, 19+2*y, 48+2*y))
    draw.ellipse((197, 3, 213, 19), fill="#f6ae70")
    draw.polygon([(0, 23), (25, 17), (61, 22), (104, 17), (135, 23),
                  (176, 18), (209, 22), (242, 17), (255, 20), (255, 31),
                  (0, 31)], fill="#6a3b49")
    rng = Random(11)
    for x in (7, 25, 49, 93, 157, 218, 247):
        top = rng.randint(10, 15)
        draw.line((x, top+4, x, 25), fill="#542e37", width=2)
        draw.ellipse((x-5, top, x+5, top+10), fill="#843d42")
        draw.ellipse((x-5, top, x+2, top+7), fill="#a55343")
        draw.point((x-1, top+2), fill="#d78953")
    draw.rectangle((0, 25, 255, 31), fill="#362637")
    draw.line((0, 25, 255, 25), fill="#774b49")
    for x in range(2, WIDTH, 8):
        y = rng.choice((27, 30, 31))
        draw.line((x, y, x+2, y), fill=rng.choice(("#593740", "#814741", "#965141")))
    return image


def pumpkin(draw, x, y):
    draw.line([(x, y+2), (x+1, y-2), (x+4, y-3)], fill="#81a665", width=2)
    for left, right, top, color in ((-15, 15, 2, "#ac4130"), (-12, 12, 1, "#ed692e"),
                                    (-7, 7, 0, "#ff9a3a"), (-2, 4, 1, "#ffb44c")):
        draw.ellipse((x+left, y+top, x+right, y+17), fill=color)
    draw.arc((x-7, y+1, x+7, y+17), 66, 275, fill="#e97532")
    draw.line((x-9, y+5, x-10, y+9), fill="#ffbe62")


def turkey(draw, x, y, index):
    for dx, dy, color in ((-12,-10,"#e16845"), (-9,-13,"#f28f47"),
                          (-5,-15,"#ffd064"), (-1,-14,"#df6643")):
        draw.line((x-3, y-3, x+dx, y+dy), fill=color, width=3)
        draw.point((x+dx, y+dy), fill=GOLD)
    draw.ellipse((x-9, y-8, x+4, y+2), fill="#9f533a")
    draw.ellipse((x-7, y-7, x+1, y-1), fill="#c57349")
    draw.line((x+1, y-4, x+3, y-11), fill="#bf6b43", width=3)
    draw.ellipse((x+1, y-13, x+6, y-8), fill="#dd9960")
    draw.point((x+5, y-12), fill="#251e2e")
    draw.polygon([(x+6,y-11),(x+9,y-10),(x+6,y-9)], fill=GOLD)
    draw.point((x+6, y-8), fill="#f3534a")
    draw.line((x-4,y+1,x-4,y+4,x-1,y+4), fill=GOLD)
    draw.rectangle((x+3,y-5,x+10,y), fill="#e3ac63")
    draw.rectangle((x+3,y-4,x+10,y-1), fill="#b5454b")
    draw.line((x+4,y-4,x+9,y-1), fill="#ffca79")
    stick_y = y-6-round(3*abs(sin(index*tau/8)))
    draw.line((x+1,y-6,x+8,stick_y), fill="#ffe0aa")


def cornucopia(draw, x):
    draw.polygon([(x-24, 8), (x-16, 12), (x-8, 11), (x+4, 6),
                  (x+11, 10), (x+11, 18), (x+4, 22), (x-11, 21),
                  (x-20, 17)], fill="#a55f3d")
    for dx, dy in ((-18, 12), (-13, 14), (-7, 14), (-1, 11)):
        draw.arc((x+dx-3, dy-2, x+dx+4, dy+8), 280, 95, fill="#f3bd72")
    draw.ellipse((x+2, 6, x+16, 22), fill="#e7a45d")
    draw.ellipse((x+5, 8, x+15, 20), fill="#65364a")
    for dx, dy, radius, color in ((12, 15, 4, "#d8474a"), (20, 17, 4, "#fd983a"),
                                   (9, 19, 3, "#e7bb54"), (27, 20, 2, "#c95253")):
        draw.ellipse((x+dx-radius, dy-radius, x+dx+radius, dy+radius), fill=color)
        draw.line((x+dx, dy-radius, x+dx+2, dy-radius-2), fill="#96b75b")
    draw.line((x+19, 11, x+26, 5), fill="#f5be59", width=2)
    for dx, dy in ((21, 8), (24, 5), (23, 10), (27, 7)):
        draw.point((x+dx, dy), fill=GOLD)


def pilgrim(draw, x, y, facing, coat, bonnet):
    draw.rectangle((x-4, y+8, x+4, y+9), fill="#8d5149")
    draw.line((x-3, y+9, x-3, 21), fill="#82433c")
    draw.rounded_rectangle((x-4, y+1, x+4, y+8), radius=2, fill=coat)
    draw.ellipse((x-3, y-4, x+3, y+2), fill="#eaa479" if bonnet else "#f6c096")
    if bonnet:
        draw.arc((x-5, y-7, x+5, y+3), 175, 365, fill="#fff2d6", width=2)
        draw.point((x-3*facing, y+1), fill="#fff2d6")
    else:
        draw.rectangle((x-3, y-8, x+3, y-4), fill="#242032")
        draw.line((x-5, y-4, x+5, y-4), fill="#242032")
        draw.point((x+2*facing, y-5), fill=GOLD)
    draw.point((x+2*facing, y-2), fill="#2e2032")
    draw.line((x-2, y+2, x+2, y+2), fill="#fff0d2")


def dinner(draw, x, index):
    for dx, y, facing, coat, bonnet in ((-22, 12, 1, "#48465d", False),
                                         (-10, 10, 1, "#73607c", True),
                                         (14, 10, -1, "#4c525f", False),
                                         (26, 12, -1, "#865365", True)):
        pilgrim(draw, x+dx, y, facing, coat, bonnet)
    draw.line((x-15, 18, x-15, 22), fill="#673844", width=2)
    draw.line((x+19, 18, x+19, 22), fill="#673844", width=2)
    draw.polygon([(x-15, 14), (x+19, 14), (x+22, 18), (x-18, 18)], fill="#ffe0ae")
    draw.line((x-18, 18, x+22, 18), fill="#bb6e61")
    for dx in (-12, -6, 12, 18):
        draw.line((x+dx-1, 16, x+dx+1, 16), fill="#fff6dd")
    draw.ellipse((x-3, 12, x+8, 16), fill="#8c4d3d")
    draw.ellipse((x-2, 12, x+6, 15), fill="#df9452")
    draw.line((x+5, 14, x+8, 12), fill="#f5ca83")
    arm_y = 14 - int(index % 12 < 4)
    draw.line((x-21, 16, x-16, arm_y), fill="#48465d", width=2)
    draw.point((x-16, arm_y), fill="#f6c096")
    draw.line((x+25, 16, x+21, 14), fill="#865365", width=2)
    draw.point((x+21, 14), fill="#eaa479")


def float_base(draw, x, index):
    draw.rounded_rectangle((x-24, 22, x+36, 27), radius=2, fill="#843f4d")
    draw.line((x-24, 22, x+36, 22), fill="#f0b870")
    for i in range(11):
        draw.point((x-21+i*5, 24), fill=GOLD if (index//3+i)%4==0 else "#e77851")
    for wheel in (x-16, x+27):
        draw.ellipse((wheel-3, 25, wheel+3, 31), fill="#191a2b", outline="#a56858")
        spoke = index//2 % 4
        dx, dy = ((2,0),(1,1),(0,2),(-1,1))[spoke]
        draw.line((wheel-dx,28-dy,wheel+dx,28+dy), fill="#edba7e")


def animation_frames():
    rng = Random(1126)
    leaves = [(rng.randrange(WIDTH), rng.randrange(29), rng.randrange(3, 8),
               rng.choice(LEAF_COLORS)) for _ in range(32)]
    background = backdrop()
    frames = []
    for index in range(FRAME_COUNT):
        frame = background.copy()
        draw = ImageDraw.Draw(frame)
        for x, y, rate, color in leaves:
            lx = (x-index//2+round(3*sin((index+y)*tau/23))) % WIDTH
            ly = (y+index//rate) % 29
            draw.point((lx, ly), fill=color)
            if (index//3+x)%4 < 2:
                draw.point((lx+1, ly-1), fill=color)
        lead = -44+2*index
        for x, kind in ((lead, "pumpkin"), (lead-78, "cornucopia"), (lead-156, "dinner")):
            if x+36 < 0 or x-25 >= WIDTH:
                continue
            if kind == "pumpkin":
                pumpkin(draw, x-3, 5)
                turkey(draw, x+23, 18, index)
            elif kind == "cornucopia":
                cornucopia(draw, x)
            else:
                dinner(draw, x, index)
            float_base(draw, x, index)
        frames.append(frame)
    return frames


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
        frames[83].crop((left, 0, left+width, HEIGHT)).save(output, "PNG")
    return output.getvalue()
