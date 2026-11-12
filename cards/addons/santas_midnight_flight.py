"""Santa's Midnight Flight, a 64 + 128 + 64 Pixora LED Studio wall card."""
from io import BytesIO
from math import sin, tau
from random import Random

from PIL import Image, ImageDraw

CARD_ID = "santas_midnight_flight"
CARD_NAME = "Santa's Midnight Flight"
CARD_DETAIL = "Santa and four single-file reindeer cross a snowy night sky on a 64 + 128 + 64 display group."
CARD_VERSION = "1.0.0"
CARD_AUTHOR = "PixoraHQ"
CARD_WALL_WIDTHS = [64, 128, 64]
CARD_OPTIONS = [
    {"key": "wallTarget", "label": "Play on display group", "type": "select",
     "default": "group_wall", "choices": [{"value": "group_wall", "label": "Display group"}]},
]

WIDTH, HEIGHT = 256, 32
FRAME_MS = 100
FRAME_COUNT = 147
DEER_OFFSETS = (41, 65, 89, 113)
GOLD = "#ffcb67"
CREAM = "#fff0db"


def night_sky():
    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        draw.line((0, y, WIDTH - 1, y), fill=(5 + y // 4, 10 + y // 2, 26 + y))
    rng = Random(1225)
    stars = [(rng.randrange(WIDTH), rng.randrange(1, 23), rng.randrange(5)) for _ in range(68)]
    draw.ellipse((208, 2, 220, 14), fill="#ffdfab")
    draw.ellipse((205, 0, 217, 11), fill="#070e21")
    draw.polygon([(0, 28), (22, 24), (48, 29), (74, 26), (100, 29),
                  (123, 24), (148, 28), (176, 25), (204, 29), (235, 24),
                  (255, 27), (255, 31), (0, 31)], fill="#263755")
    for x, top in ((4, 25), (35, 25), (52, 27), (77, 24), (101, 26), (126, 23),
                   (157, 25), (177, 23), (199, 26), (224, 25), (247, 24)):
        draw.polygon([(x, top), (x-3, top+4), (x-1, top+4), (x-4, top+7),
                      (x+4, top+7), (x+1, top+4), (x+3, top+4)], fill="#10213b")
        draw.line((x, top, x-2, top+3), fill="#61789a")
    for x in (18, 22, 185, 189):
        draw.rectangle((x, 28, x+3, 31), fill="#15182e")
        draw.polygon([(x-1, 28), (x+1, 26), (x+4, 28)], fill="#7290ad")
        draw.point((x+2, 30), fill=GOLD)
    return image, stars


def reindeer(draw, x, y, phase, leader):
    def line(points, fill, width=1):
        draw.line([(x+a, y+b) for a,b in points], fill=fill, width=width)

    for dx, opposite in ((-4, False), (3, True)):
        kick = round(3 * sin(phase + (3.14 if opposite else 0)))
        line([(dx, 2), (dx-1, 5), (dx+kick, 7)], "#86513f")
        line([(dx+1, 2), (dx+2, 5), (dx-kick, 6)], "#d48b55")
        line([(dx-kick, 6), (dx-kick+1, 6)], "#382733")
    line([(-6, -1), (-9, -3)], "#d48b55", 2)
    draw.ellipse((x-7, y-3, x+6, y+3), fill="#b97145")
    line([(-5, -2), (3, -2)], "#eeaf6e")
    line([(3, 1), (6, -5)], "#d8935a", 3)
    draw.ellipse((x+5, y-7, x+11, y-3), fill="#e6a56d")
    line([(9, -5), (12, -4)], "#f1c58f", 2)
    line([(7, -7), (5, -10), (5, -12)], CREAM)
    line([(5, -10), (3, -11)], CREAM)
    line([(8, -7), (9, -10), (11, -11)], "#ffcf8d")
    line([(9, -10), (8, -12)], "#ffcf8d")
    draw.point((x+9, y-6), fill="#18172a")
    draw.point((x+12, y-4), fill="#ff4b46" if leader else "#372636")
    line([(3, -1), (6, 1)], "#dd424b", 2)
    draw.point((x+5, y+2), fill=GOLD)


def sleigh(draw, x, y):
    def polygon(points, color):
        draw.polygon([(x+a, y+b) for a,b in points], fill=color)

    def line(points, color, width=1):
        draw.line([(x+a, y+b) for a,b in points], fill=color, width=width)

    # Toy sack, Santa's coat and the red hat silhouette sit above the sleigh.
    draw.ellipse((x-12, y-8, x-2, y+2), fill="#31826c")
    draw.ellipse((x-11, y-8, x-5, y-5), fill="#5fbf8f")
    line([(-8,-8),(-6,-10),(-4,-8)], GOLD)
    draw.ellipse((x-3, y-6, x+7, y+3), fill="#ed3e4d")
    draw.ellipse((x, y-11, x+7, y-5), fill="#f6b68d")
    polygon([(0,-9),(7,-9),(8,-6),(4,-4),(2,-5)], CREAM)
    polygon([(-1,-11),(0,-15),(4,-16),(8,-12),(7,-10)], "#f34651")
    line([(-1,-11),(7,-11)], CREAM, 2)
    draw.point((x, y-15), fill=CREAM)
    draw.point((x+5, y-9), fill="#37232d")
    line([(4,-4),(8,-3),(11,-5)], "#ed3e4d", 2)
    draw.point((x+11, y-5), fill=CREAM)
    polygon([(-15,-1),(-10,1),(7,1),(13,-3),(17,-3),(15,3),(10,6),(-11,6)], "#c92942")
    line([(-14,-1),(-10,1),(7,1),(13,-3),(17,-3)], GOLD)
    line([(-11,4),(10,4)], "#f66a59")
    line([(-9,6),(-9,8),(8,8),(8,6)], "#c28c45")
    line([(-15,8),(-12,9),(12,9),(17,7),(18,5)], GOLD)


def frame_at(index, background, stars):
    image = background.copy()
    draw = ImageDraw.Draw(image)
    for x, y, shift in stars:
        strength = (index // 5 + shift + x) % 17
        draw.point((x, y), fill="#d9e9ff" if strength == 0 else "#426393")
    if index < 5 or index >= FRAME_COUNT - 5:
        return image
    travel = (index - 5) / (FRAME_COUNT - 11)
    x = round(-130 + 428 * travel)
    y = 18 + round(2 * sin(travel * tau * 2))
    positions = [(x+offset, y+round(1.5*sin(index*.56+i*.8))) for i,offset in enumerate(DEER_OFFSETS)]
    # A continuous harness makes the four silhouettes read as one team.
    last = (x+11,y-5)
    for dx,dy in positions:
        draw.line((*last,dx+3,dy), fill="#a98553")
        last = (dx+7,dy)
    for i, (dx,dy) in enumerate(positions):
        reindeer(draw,dx,dy,index*.68+i*.95,i==3)
    sleigh(draw,x,y)
    for i in range(7):
        px=x-17-i*4
        py=y+4+round(2*sin(index*.29+i))
        if (index+i*3)%7<4:
            draw.point((px,py),fill=GOLD if i<3 else "#85aadc")
    return image


def animation_frames():
    background, stars = night_sky()
    return [frame_at(index,background,stars) for index in range(FRAME_COUNT)]


def render(options=None):
    width = (options or {}).get("_width", 64)
    output = BytesIO()
    if width == WIDTH:
        frames = animation_frames()
        frames[0].save(output,"WEBP",save_all=True,append_images=frames[1:],
                       duration=FRAME_MS,lossless=True,loop=1,method=0)
    else:
        width = 128 if width == 128 else 64
        frame = frame_at(67,*night_sky())
        left = (WIDTH-width)//2
        frame.crop((left,0,left+width,HEIGHT)).save(output,"PNG")
    return output.getvalue()
