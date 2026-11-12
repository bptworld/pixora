"""Happy New Year, an offline 64 + 128 + 64 LED Studio animation."""
from io import BytesIO
from math import cos, sin, tau
from random import Random

from PIL import Image, ImageDraw, ImageFilter

CARD_ID = "happy_new_year"
CARD_NAME = "Happy New Year"
CARD_DETAIL = "A wall-wide gold Happy New Year greeting with fireworks across three panels."
CARD_VERSION = "1.1.0"
CARD_AUTHOR = "PixoraHQ"
CARD_WALL_WIDTHS = [64, 128, 64]
CARD_OPTIONS = [
    {"key": "wallTarget", "label": "Play on display group", "type": "select",
     "default": "group_wall", "choices": [{"value": "group_wall", "label": "Display group"}]},
]

WIDTH, HEIGHT = 256, 32
FRAME_MS, FRAME_COUNT = 100, 150
GOLD = (255, 197, 84)
PALE = (255, 236, 173)
INK = (11, 12, 32)
GLYPHS = {
    "H": (17, 17, 17, 31, 17, 17, 17),
    "A": (14, 17, 17, 31, 17, 17, 17),
    "P": (30, 17, 17, 30, 16, 16, 16),
    "Y": (17, 17, 10, 4, 4, 4, 4),
    "N": (17, 25, 21, 19, 17, 17, 17),
    "E": (31, 16, 16, 30, 16, 16, 31),
    "W": (17, 17, 17, 21, 21, 27, 17),
    "R": (30, 17, 17, 30, 20, 18, 17),
    " ": (0,)*7,
}


def greeting_mask(index):
    message = "HAPPY NEW YEAR"
    scale_x, scale_y = 3, 2
    left = (WIDTH-(6*len(message)-1)*scale_x)//2
    mask = Image.new("L", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(mask)
    for col, letter in enumerate(message):
        phase = index*tau/(8+col%5)+col*1.7
        shake_x = round(sin(phase))
        shake_y = round(1.5*cos(phase))
        for row, bits in enumerate(GLYPHS[letter]):
            for bit in range(5):
                if bits & (16 >> bit):
                    x, y = left+(6*col+bit)*scale_x+shake_x, 9+row*scale_y+shake_y
                    draw.rectangle((x, y, x+scale_x-1, y+scale_y-1), fill=255)
    return mask


def city():
    frame = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(frame)
    rng = Random(1231)
    for y in range(HEIGHT):
        draw.line((0,y,WIDTH-1,y), fill=(8+y//3,10+y//3,29+y//2))
    for _ in range(55):
        draw.point((rng.randrange(WIDTH), rng.randrange(24)), fill=rng.choice(("#414778","#686890")))
    x = 0
    while x < WIDTH:
        width, top = rng.randrange(4,10), rng.randrange(23,30)
        draw.rectangle((x,top,x+width-1,31), fill="#080c1e")
        for wx in range(x+1,x+width-1,2):
            for wy in range(top+2,31,2):
                if rng.randrange(4)==0:
                    draw.point((wx,wy), fill=rng.choice(("#846b64","#b98b58","#6573ac")))
        x += width+1
    return frame


def firework(draw, index, burst, x, y, color, seed):
    age = index-burst
    if -6 <= age < 0:
        rocket_y = round(y+(25-y)*(-age/6))
        draw.line((x,rocket_y,x,rocket_y+2), fill=color)
        draw.point((x,rocket_y), fill=PALE)
    if not 0 <= age < 20:
        return
    rng = Random(seed)
    for ray in range(24):
        angle = (ray+rng.uniform(-.25,.25))*tau/24
        speed = rng.uniform(.45,1.0)
        for tail in (2,0):
            travel = max(0,age-tail)*speed
            px = round(x+cos(angle)*travel*1.55)
            py = round(y+sin(angle)*travel*.85+age*age/220)
            brightness = (1-age/21)*(.46 if tail else 1)
            draw.point((px,py), fill=tuple(int(c*brightness) for c in color))
    if age < 3:
        draw.ellipse((x-1,y-1,x+1,y+1), fill=PALE)


def animation_frames():
    background = city()
    gold_text = Image.new("RGB", (WIDTH, HEIGHT), GOLD)
    ImageDraw.Draw(gold_text).rectangle((0, 9, WIDTH-1, 13), fill=PALE)
    bursts = (
        (3,31,7,GOLD), (5,222,8,(108,207,255)), (9,128,7,(255,123,166)),
        (23,79,21,(102,228,199)), (29,174,6,(172,139,255)),
        (38,25,22,(255,127,160)), (43,231,7,GOLD), (51,122,21,(111,175,255)),
        (62,62,9,(251,125,174)), (65,194,9,(169,142,255)),
        (75,20,10,(95,225,188)), (77,239,11,GOLD), (83,74,14,(103,170,255)),
        (89,181,15,(255,126,149)), (94,43,11,GOLD), (99,215,10,(97,233,186)),
        (107,15,12,(165,143,255)), (109,244,13,(255,121,166)),
        (117,63,9,(114,207,255)), (120,195,9,GOLD),
        (128,33,12,(255,128,157)), (130,224,12,(133,222,251)),
    )
    frames = []
    for index in range(FRAME_COUNT):
        frame = background.copy()
        draw = ImageDraw.Draw(frame)
        for seed, burst in enumerate(bursts):
            firework(draw,index,*burst,seed)
        text = greeting_mask(index)
        frame.paste(INK, mask=text.filter(ImageFilter.MaxFilter(3)))
        frame.paste(gold_text, mask=text)
        frames.append(frame)
    return frames


def render(options=None):
    width = (options or {}).get("_width", 64)
    out = BytesIO()
    frames = animation_frames()
    if width == WIDTH:
        frames[0].save(out,"WEBP",save_all=True,append_images=frames[1:],
                       duration=FRAME_MS,lossless=True,loop=1,method=0)
    else:
        width = 128 if width == 128 else 64
        height = HEIGHT*width//WIDTH
        frame = frames[14].resize((width,height),Image.Resampling.LANCZOS)
        preview = Image.new("RGB",(width,HEIGHT),INK)
        preview.paste(frame,(0,(HEIGHT-height)//2))
        preview.save(out,"PNG")
    return out.getvalue()
