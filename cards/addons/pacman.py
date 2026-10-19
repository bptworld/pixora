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


# Classic 28-by-31 arcade floor plan. Five pixels per tile keep actors
# inside the one-tile corridors; the camera follows the action vertically.
# Layout reference: https://subethasoftware.com/2022/09/19/drawing-a-maze-level-on-the-coco-part-1/
TILE = 5
RADIUS = TILE // 2
MAZE = (
    "############################",
    "#............##............#",
    "#.####.#####.##.#####.####.#",
    "#o####.#####.##.#####.####o#",
    "#.####.#####.##.#####.####.#",
    "#..........................#",
    "#.####.##.########.##.####.#",
    "#.####.##.########.##.####.#",
    "#......##....##....##......#",
    "######.##### ## #####.######",
    "     #.##### ## #####.#     ",
    "     #.##          ##.#     ",
    "     #.## ###--### ##.#     ",
    "######.## #      # ##.######",
    "      .   #      #   .      ",
    "######.## #      # ##.######",
    "     #.## ######## ##.#     ",
    "     #.##          ##.#     ",
    "     #.## ######## ##.#     ",
    "######.## ######## ##.######",
    "#............##............#",
    "#.####.#####.##.#####.####.#",
    "#.####.#####.##.#####.####.#",
    "#o..##.......  .......##..o#",
    "###.##.##.########.##.##.###",
    "###.##.##.########.##.##.###",
    "#......##....##....##......#",
    "#.##########.##.##########.#",
    "#.##########.##.##########.#",
    "#..........................#",
    "############################",
)


def _maze(width):
    # Flood fill excludes the ghost pen and the blank space outside the maze.
    start=(1,1); reachable={start};pending=[start]
    while pending:
        x,y=pending.pop()
        for xx,yy in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if 0<=xx<28 and 0<=yy<31 and MAZE[yy][xx] not in '#-' and (xx,yy) not in reachable:
                reachable.add((xx,yy));pending.append((xx,yy))
    def pixel(node):return (node[0]*TILE+RADIUS,node[1]*TILE+RADIUS)
    graph = {pixel((x,y)):[pixel(n) for n in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)) if n in reachable] for x,y in sorted(reachable,key=lambda p:(p[1],p[0]))}
    left=(RADIUS,14*TILE+RADIUS);right=(27*TILE+RADIUS,left[1])
    graph[left].append(right);graph[right].append(left)
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
    if abs(target[0]-position[0])>TILE:
        return (target,target,previous), (-1 if position[0]==RADIUS else 1,0)
    dx = (target[0] > position[0]) - (target[0] < position[0])
    dy = (target[1] > position[1]) - (target[1] < position[1])
    return ((position[0] + dx, position[1] + dy), target, previous), (dx, dy)


def _eat(dots, position):
    dots.difference_update({dot for dot in dots if abs(dot[0]-position[0])+abs(dot[1]-position[1]) <= RADIUS})


def _background(width, graph):
    from PIL import Image, ImageDraw
    image=Image.new('RGB',(28*TILE,31*TILE));draw=ImageDraw.Draw(image)
    for y,row in enumerate(MAZE):
        for x,tile in enumerate(row):
            if tile=='#':
                # Only the edges of wall masses are blue, leaving hollow blocks.
                for dx,dy,box in ((1,0,(x*TILE+TILE-1,y*TILE,x*TILE+TILE-1,y*TILE+TILE-1)),(-1,0,(x*TILE,y*TILE,x*TILE,y*TILE+TILE-1)),(0,1,(x*TILE,y*TILE+TILE-1,x*TILE+TILE-1,y*TILE+TILE-1)),(0,-1,(x*TILE,y*TILE,x*TILE+TILE-1,y*TILE))):
                    xx,yy=x+dx,y+dy
                    if 0<=xx<28 and 0<=yy<31 and MAZE[yy][xx]!='#':draw.line(box,fill=(20,64,190))
            elif tile=='-':draw.line((x*TILE,y*TILE+RADIUS,x*TILE+TILE-1,y*TILE+RADIUS),fill=(255,153,214))
    return image


def _viewport(image,width,position,companions=()):
    from PIL import Image
    # Unwrap the tunnel around Pac-Man so chasing ghosts remain beside him
    # on screen even while they cross opposite ends of the maze.
    period=image.width
    points=[position]+[(position[0]+((x-position[0]+period//2)%period-period//2),y) for x,y in companions]
    left=round((min(x for x,y in points)+max(x for x,y in points)-width)/2)
    top=max(0,min(image.height-32,round((min(y for x,y in points)+max(y for x,y in points)-31)/2)))
    view=Image.new('RGB',(width,32))
    for offset in (-period,0,period):view.paste(image,(offset-left,-top))
    return view


def _pacman(draw, position, direction, step):
    x,y=position; dx,dy=direction
    angle=0 if dx>0 else 180 if dx<0 else 90 if dy>0 else 270
    box=(x-RADIUS,y-RADIUS,x+RADIUS,y+RADIUS)
    if step%4==0:draw.ellipse(box,fill=(255,224,35))
    else:draw.pieslice(box,angle+35,angle+325,fill=(255,224,35))


def _ghost(draw, position, color, step):
    x,y=position
    draw.ellipse((x-2,y-2,x+2,y+2),fill=color)
    draw.rectangle((x-2,y,x+2,y+2),fill=color)
    draw.point((x-1,y-1),fill='white');draw.point((x+1,y-1),fill='white')
    draw.point((x+(1 if step%2 else -1),y+2),fill='black')



def _touching(first,second):
    dx=abs(first[0]-second[0]);dx=min(dx,28*TILE-dx)
    dy=abs(first[1]-second[1])
    return dx*dx+dy*dy<=(2*RADIUS)**2


def _caught(draw,position,step):
    x,y=position
    # Mouth opens until the last sliver disappears, then a brief empty beat.
    if step<6:
        opening=35+step*28
        draw.pieslice((x-RADIUS,y-RADIUS,x+RADIUS,y+RADIUS),opening,360-opening,fill=(255,224,35))


def _focus(actors,width):
    from itertools import combinations
    pac=actors[0][0];period=28*TILE
    for pair in combinations(range(1,5),2):
        ghosts=[actors[i][0] for i in pair]
        xs=[pac[0]]+[pac[0]+((x-pac[0]+period//2)%period-period//2) for x,y in ghosts]
        ys=[pac[1]]+[y for x,y in ghosts]
        if max(xs)-min(xs)<=width-2*RADIUS-2 and max(ys)-min(ys)<=32-2*RADIUS-2:
            return ghosts
    return None


def _spawn(graph,width,rng):
    nodes=list(graph)
    while True:
        start=rng.choice(nodes)
        nearby=[n for n in nodes if not _touching(n,start) and abs(n[1]-start[1])<=10 and abs(n[0]-start[0])<=width//3]
        if len(nearby)<2:continue
        near=rng.sample(nearby,2)
        others=rng.sample([n for n in nodes if n!=start and n not in near],2)
        rng.shuffle(near)
        actors=[(n,n,None) for n in [start,*near,*others]]
        if _focus(actors,width) and not any(_touching(actors[i][0],actors[j][0]) for i in range(5) for j in range(i+1,5)):
            return actors


def render(options=None):
    from PIL import ImageDraw
    opts=options or {}
    width=128 if opts.get('_target')=='matrixportal-s3-128x32' or opts.get('_width')==128 else 64
    rng=random.Random()
    graph=_maze(width); nodes=list(graph)
    dots={node for node in nodes if MAZE[node[1]//TILE][node[0]//TILE] in ".o"}
    actors=_spawn(graph,width,rng)
    background=_background(width,graph)
    caught=None
    dwell=max(3000,min(60000,int(opts.get('_dwell',10) or 10)*1000))
    duration=_speed_ms(opts.get('speed'))
    count=max(24,min(1000,round(dwell/duration)))
    frames=[]
    for step in range(count):
        image=background.copy();draw=ImageDraw.Draw(image)
        if caught is not None and caught>=8:
            actors=_spawn(graph,width,rng)
            caught=None
        directions=[(1,0)]*5
        if caught is None:
            # Move independently, but do not strand Pac-Man outside a view
            # containing two ghosts. Rejected moves wait rather than teleport.
            order=list(range(5));rng.shuffle(order)
            for i in order:
                proposed,direction=_advance(actors[i],graph,rng,dots if i==0 else None)
                candidate=list(actors);candidate[i]=proposed
                crowded=i>0 and any(_touching(proposed[0],candidate[j][0]) for j in range(1,5) if j!=i)
                if not crowded and _focus(candidate,width) is not None:
                    actors=candidate;directions[i]=direction
            if any(_touching(actors[0][0],actor[0]) for actor in actors[1:]):caught=0
        _eat(dots,actors[0][0])
        if _on(opts.get('dots','on')):
            for dot in dots:draw.point(dot,fill=(255,214,150))
        if caught is None:_pacman(draw,actors[0][0],directions[0],step)
        else:_caught(draw,actors[0][0],caught);caught+=1
        for i,color in enumerate(((255,65,65),(255,153,214),(75,220,255),(255,170,55)),1):
            _ghost(draw,actors[i][0],color,step)
        frames.append(_viewport(image,width,actors[0][0],_focus(actors,width)))
    out=BytesIO()
    frames[0].save(out,'WEBP',save_all=True,append_images=frames[1:],duration=round(dwell/count),loop=1,lossless=True,quality=100)
    return out.getvalue()
