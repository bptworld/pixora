from io import BytesIO
import random

CARD_ID = "pacman"
CARD_NAME = "Pac-Man Chase"
CARD_DETAIL = "Pac-Man chasing ghosts"
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
    {
        "key": "dots",
        "label": "Dots",
        "type": "select",
        "default": "on",
        "choices": [
            {"value": "on", "label": "On"},
            {"value": "off", "label": "Off"},
        ],
    },
]


def _on(value):
    return str(value or "").strip().lower() not in ("off", "no", "false", "0")


def _speed_ms(value):
    speed = str(value or "normal").strip().lower()
    if speed in ("fast", "quick"):
        return 65
    if speed in ("slow", "chill"):
        return 150
    return 95


def _maze(width):
    nodes = [(x, y) for y in (4, 12, 20, 28) for x in range(4, width, 8)]
    graph = {node: [] for node in nodes}
    for x, y in nodes:
        for other in ((x + 8, y), (x, y + 8)):
            if other not in graph:
                continue
            if other[1] != y and x not in (4, width - 4) and (x // 8 + y // 8) % 2:
                continue
            graph[(x, y)].append(other)
            graph[other].append((x, y))
    return graph


def _advance(actor, graph, rng, dots=None):
    position, target, previous = actor
    if position == target:
        choices = [n for n in graph[target] if n != previous] or graph[target]
        if dots is not None:
            fresh = [n for n in choices if n in dots]
            choices = fresh or choices
        destination = rng.choice(choices)
        previous, target = target, destination
    dx = (target[0] > position[0]) - (target[0] < position[0])
    dy = (target[1] > position[1]) - (target[1] < position[1])
    return ((position[0] + dx, position[1] + dy), target, previous), (dx, dy)


def _eat(dots, position):
    dots.difference_update({dot for dot in dots if abs(dot[0]-position[0])+abs(dot[1]-position[1]) <= 2})


def _background(width, graph):
    from PIL import Image, ImageDraw
    mask = Image.new('1', (width, 32)); draw = ImageDraw.Draw(mask)
    for node, neighbors in graph.items():
        x, y = node
        draw.rectangle((x-2, y-2, x+2, y+2), fill=1)
        for other in neighbors:draw.line((*node, *other), fill=1, width=5)
    image = Image.new('RGB', (width, 32))
    for y in range(32):
        for x in range(width):
            if not mask.getpixel((x,y)) and any(0<=x+dx<width and 0<=y+dy<32 and mask.getpixel((x+dx,y+dy)) for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))):
                image.putpixel((x,y),(20,64,190))
    return image


def _pacman(draw, position, direction, step):
    x,y=position; dx,dy=direction
    angle=0 if dx>0 else 180 if dx<0 else 90 if dy>0 else 270
    box=(x-2,y-2,x+2,y+2)
    if step%4==0:draw.ellipse(box,fill=(255,224,35))
    else:draw.pieslice(box,angle+35,angle+325,fill=(255,224,35))


def _ghost(draw, position, color, step):
    x,y=position
    draw.ellipse((x-2,y-2,x+2,y+2),fill=color)
    draw.rectangle((x-2,y,x+2,y+2),fill=color)
    draw.point((x-1,y-1),fill='white');draw.point((x+1,y-1),fill='white')
    draw.point((x+(1 if step%2 else -1),y+2),fill='black')


def render(options=None):
    from PIL import ImageDraw
    opts=options or {}
    width=128 if opts.get('_target')=='matrixportal-s3-128x32' or opts.get('_width')==128 else 64
    rng=random.Random()
    graph=_maze(width); nodes=list(graph)
    dots=set(nodes)
    for node,neighbors in graph.items():
        for other in neighbors:dots.add(((node[0]+other[0])//2,(node[1]+other[1])//2))
    starts=[nodes[0],*rng.sample(nodes[1:],3)]
    actors=[(node,node,None) for node in starts]
    background=_background(width,graph)
    dwell=max(3000,min(60000,int(opts.get('_dwell',10) or 10)*1000))
    duration=_speed_ms(opts.get('speed'))
    count=max(24,min(1000,round(dwell/duration)))
    frames=[]
    for step in range(count):
        image=background.copy();draw=ImageDraw.Draw(image)
        directions=[]
        for i,actor in enumerate(actors):
            actors[i],direction=_advance(actor,graph,rng,dots if i==0 else None)
            directions.append(direction)
        _eat(dots,actors[0][0])
        if _on(opts.get('dots','on')):
            for dot in dots:draw.point(dot,fill=(255,214,150))
        _pacman(draw,actors[0][0],directions[0],step)
        for i,color in enumerate(((255,65,65),(255,153,214),(75,220,255)),1):
            _ghost(draw,actors[i][0],color,step)
        frames.append(image)
    out=BytesIO()
    frames[0].save(out,'WEBP',save_all=True,append_images=frames[1:],duration=round(dwell/count),loop=1,lossless=True,quality=100)
    return out.getvalue()
