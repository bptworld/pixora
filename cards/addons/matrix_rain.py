from io import BytesIO
import random

CARD_ID = "matrix_rain"
CARD_NAME = "Matrix Rain"
CARD_DETAIL = "Falling green code"
CARD_OPTIONS = [
    {
        "key": "speed",
        "label": "Speed",
        "type": "select",
        "default": "normal",
        "choices": [
            {"value": "slow", "label": "Slow"},
            {"value": "normal", "label": "Normal"},
            {"value": "fast", "label": "Fast"},
        ],
    },
]


def _hash_noise(x, y, frame):
    value = (x * 374761393 + y * 668265263 + frame * 2246822519) & 0xFFFFFFFF
    value = (value ^ (value >> 13)) * 1274126177
    return (value ^ (value >> 16)) & 0xFF


# Compact code-like glyphs: angular kana-inspired forms, digits and symbols.
# Bitmap strokes stay crisp on the physical LED grid without font fallback.
GLYPHS = (
    (7,1,7,4,7), (7,2,7,2,4), (5,7,1,2,4), (2,7,2,3,2),
    (7,1,3,1,7), (5,5,7,1,2), (4,7,5,1,2), (7,2,2,2,2),
    (1,1,5,5,2), (2,7,2,2,7), (4,4,7,1,1), (7,5,5,1,2),
    (7,5,5,5,7), (2,6,2,2,7), (7,1,7,4,7), (7,1,7,1,7),
    (5,5,7,1,1), (7,4,7,1,7), (7,4,7,5,7), (7,1,2,2,2),
    (7,5,7,5,7), (7,5,7,1,7), (2,7,2,7,2), (0,2,7,2,0),
)


def _columns(width,rng):
    return [{'x':x,'phase':rng.uniform(0,18),'speed':rng.uniform(1.3,3.2),
             'length':rng.uniform(4,9),'period':rng.uniform(13,21),
             'brightness':rng.choice((.4,.65,1,1)), 'seed':rng.randrange(100000)}
            for x in range(1,width-2,4)]


def _draw_glyph(draw,x,y,bits,color,mirror=False):
    for row,line in enumerate(bits):
        for col in range(3):
            if line & (1 << col):draw.point((x+(2-col if mirror else col),y+row),fill=color)


def render(options=None):
    from PIL import Image, ImageDraw
    opts=options or {}
    width=128 if opts.get('_target')=='matrixportal-s3-128x32' or opts.get('_width')==128 else 64
    dwell=max(3000,min(60000,int(opts.get('_dwell',10) or 10)*1000))
    count=max(30,min(600,round(dwell/80)))
    duration=round(dwell/count)
    rate={'slow':.6,'normal':1,'fast':1.6}.get(opts.get('speed'),1)
    columns=_columns(width,random.Random())
    frames=[]
    for frame in range(count):
        image=Image.new('RGB',(width,32),'black');draw=ImageDraw.Draw(image)
        seconds=frame*duration/1000
        for column in columns:
            head=column['phase']+seconds*column['speed']*rate
            for row in range(6):
                age=(head-row)%column['period']
                if age>=column['length']:continue
                fade=(1-age/column['length'])**1.6*column['brightness']
                if age<.85 and column['brightness']>.5:
                    color=(int(190*column['brightness']),int(255*column['brightness']),int(205*column['brightness']))
                else:color=(0,max(5,int(220*fade)),int(28*fade))
                # Most characters hold still while the head advances; a few
                # mutate, rather than changing every glyph every video frame.
                cycle=int((head-row)//column['period'])
                mutation=frame//8 if _hash_noise(column['seed'],row,4)>195 else 0
                index=_hash_noise(column['seed'],row,cycle+mutation)
                _draw_glyph(draw,column['x'],row*6-1,GLYPHS[index%len(GLYPHS)],color,index%3==0)
        frames.append(image)
    out=BytesIO()
    frames[0].save(out,'WEBP',save_all=True,append_images=frames[1:],duration=duration,
                   loop=1,lossless=True,quality=100)
    return out.getvalue()
