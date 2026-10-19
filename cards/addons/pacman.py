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


def _raw_maze(width):
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


class MazeGraph(dict):
    pass


def _maze(width):
    raw=_raw_maze(width)
    ends={(RADIUS,14*TILE+RADIUS),(27*TILE+RADIUS,14*TILE+RADIUS)}
    junctions={p for p,neighbors in raw.items() if len(neighbors)!=2 or not (neighbors[0][0]==neighbors[1][0] or neighbors[0][1]==neighbors[1][1])}|ends
    xs=sorted({x for x,y in junctions});ys=sorted({y for x,y in junctions})
    # Keep five-pixel lanes, but replace long wall interiors with two-pixel
    # bars. Junction order and corridor connections remain the classic maze.
    def pixel(p):return (6+xs.index(p[0])*7,6+ys.index(p[1])*7)
    graph=MazeGraph({pixel(p):[] for p in junctions});graph.tunnels=set()
    graph.world=(max(x for x,y in graph)+7,max(y for x,y in graph)+7)
    for start in junctions:
        for following in raw[start]:
            previous=start;current=following;warp=abs(start[0]-following[0])>TILE
            while current not in junctions:
                nxt=next(n for n in raw[current] if n!=previous)
                warp |= abs(nxt[0]-current[0])>TILE
                previous,current=current,nxt
            a,b=pixel(start),pixel(current);graph[a].append(b)
            if warp:graph.tunnels.add((a,b))
    return graph


def _dots(graph):
    dots=set(graph)
    for start,neighbors in graph.items():
        for end in neighbors:
            if (start,end) in graph.tunnels:continue
            length=abs(end[0]-start[0])+abs(end[1]-start[1])
            dx=(end[0]>start[0])-(end[0]<start[0]);dy=(end[1]>start[1])-(end[1]<start[1])
            for step in range(4,length,4):dots.add((start[0]+step*dx,start[1]+step*dy))
    return dots


def _advance(actor, graph, rng, dots=None):
    position, target, previous = actor
    if position == target:
        choices = [n for n in graph[target] if n != previous] or graph[target]
        if dots is not None:
            fresh = [n for n in choices if n in dots]
            choices = fresh or choices
        destination = rng.choice(choices)
        previous, target = target, destination
    if (previous,target) in getattr(graph,'tunnels',()):
        direction=-1 if target[0]>previous[0] else 1
        next_x=(position[0]+direction)%graph.world[0]
        return ((next_x,position[1]),target,previous),(direction,0)
    dx = (target[0] > position[0]) - (target[0] < position[0])
    dy = (target[1] > position[1]) - (target[1] < position[1])
    return ((position[0] + dx, position[1] + dy), target, previous), (dx, dy)


def _eat(dots, position):
    dots.difference_update({dot for dot in dots if abs(dot[0]-position[0])+abs(dot[1]-position[1]) <= RADIUS})


def _background(width, graph):
    from PIL import Image, ImageDraw, ImageFilter
    mask=Image.new('L',graph.world);draw=ImageDraw.Draw(mask)
    for node,neighbors in graph.items():
        x,y=node;draw.rectangle((x-2,y-2,x+2,y+2),fill=255)
        for other in neighbors:
            if (node,other) not in graph.tunnels:draw.line((*node,*other),fill=255,width=5)
            else:draw.line((*node,0 if node[0]<other[0] else graph.world[0]-1,node[1]),fill=255,width=5)
    border=mask.filter(ImageFilter.MaxFilter(5))
    image=Image.new('RGB',graph.world)
    for y in range(image.height):
        for x in range(image.width):
            if border.getpixel((x,y)) and not mask.getpixel((x,y)):image.putpixel((x,y),(35,48,185))
    return image


def _camera(position,width,world,camera=None):
    x,y=position;period,height=world
    target_y=max(0,min(height-32,y-16))
    if camera is None:return [x,x,x-width//2,target_y]
    unwrapped,previous,left,top=camera
    unwrapped+=(x-previous+period//2)%period-period//2
    target_x=unwrapped-width//2
    left+=max(-1,min(1,target_x-left))
    top+=max(-1,min(1,target_y-top))
    return [unwrapped,x,left,top]


def _viewport(image,width,camera):
    from PIL import Image
    period=image.width;left=camera[2]%period;top=camera[3]
    view=Image.new('RGB',(width,32))
    for offset in (-period,0,period,2*period):view.paste(image,(offset-left,-top))
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



def _touching(first,second,period=28*TILE):
    dx=abs(first[0]-second[0]);dx=min(dx,period-dx)
    dy=abs(first[1]-second[1])
    return dx*dx+dy*dy<=(2*RADIUS)**2


def _caught(draw,position,step):
    x,y=position
    # Mouth opens until the last sliver disappears, then a brief empty beat.
    if step<6:
        opening=35+step*28
        draw.pieslice((x-RADIUS,y-RADIUS,x+RADIUS,y+RADIUS),opening,360-opening,fill=(255,224,35))


def _starting_ghosts_visible(actors,width,world):
    pac=actors[0][0];camera=_camera(pac,width,world)
    count=0
    for actor in actors[1:]:
        x,y=actor[0]
        dx=(x-pac[0]+world[0]//2)%world[0]-world[0]//2
        if abs(dx)<=width//2-RADIUS-1 and camera[3]+RADIUS<=y<camera[3]+32-RADIUS:count+=1
    return count>=2


def _spawn(graph,width,rng):
    nodes=list(graph)
    while True:
        start=rng.choice(nodes)
        nearby=[n for n in nodes if not _touching(n,start,graph.world[0]) and abs(n[1]-start[1])<=12 and abs(n[0]-start[0])<=width//3]
        if len(nearby)<2:continue
        near=rng.sample(nearby,2)
        others=rng.sample([n for n in nodes if n!=start and n not in near],2)
        rng.shuffle(near)
        actors=[(n,n,None) for n in [start,*near,*others]]
        safe=all(min(abs(start[0]-a[0][0]),graph.world[0]-abs(start[0]-a[0][0]))**2+(start[1]-a[0][1])**2>=64 for a in actors[1:])
        if safe and _starting_ghosts_visible(actors,width,graph.world) and not any(_touching(actors[i][0],actors[j][0],graph.world[0]) for i in range(5) for j in range(i+1,5)):
            return actors


def render(options=None):
    from PIL import ImageDraw
    opts=options or {}
    width=128 if opts.get('_target')=='matrixportal-s3-128x32' or opts.get('_width')==128 else 64
    rng=random.Random()
    graph=_maze(width); nodes=list(graph)
    dots=_dots(graph)
    actors=_spawn(graph,width,rng)
    background=_background(width,graph)
    caught=None
    camera=_camera(actors[0][0],width,graph.world)
    dwell=max(3000,min(60000,int(opts.get('_dwell',10) or 10)*1000))
    duration=_speed_ms(opts.get('speed'))
    count=max(24,min(1000,round(dwell/duration)))
    frames=[]
    for step in range(count):
        image=background.copy();draw=ImageDraw.Draw(image)
        if caught is not None and caught>=8:
            # Pac-Man stays at the collision location; random ghosts restart
            # away from him so a lost life never relocates the camera.
            pac=actors[0]
            choices=[n for n in nodes if not _touching(n,pac[0],graph.world[0]) and abs(n[1]-pac[0][1])+abs(n[0]-pac[0][0])>12]
            actors=[pac,*[(n,n,None) for n in rng.sample(choices,4)]]
            caught=None
        directions=[(1,0)]*5
        if caught is None:
            # Ghosts choose their own paths and may leave the camera freely.
            order=list(range(5));rng.shuffle(order)
            for i in order:
                proposed,direction=_advance(actors[i],graph,rng,dots if i==0 else None)
                candidate=list(actors);candidate[i]=proposed
                crowded=i>0 and any(_touching(proposed[0],candidate[j][0],graph.world[0]) for j in range(1,5) if j!=i)
                if not crowded:
                    actors=candidate;directions[i]=direction
            if any(_touching(actors[0][0],actor[0],graph.world[0]) for actor in actors[1:]):caught=0
        _eat(dots,actors[0][0])
        if _on(opts.get('dots','on')):
            for dot in dots:draw.point(dot,fill=(255,214,150))
        if caught is None:_pacman(draw,actors[0][0],directions[0],step)
        else:_caught(draw,actors[0][0],caught);caught+=1
        for i,color in enumerate(((255,65,65),(255,153,214),(75,220,255),(255,170,55)),1):
            _ghost(draw,actors[i][0],color,step)
        camera=_camera(actors[0][0],width,graph.world,camera)
        frames.append(_viewport(image,width,camera))
    out=BytesIO()
    frames[0].save(out,'WEBP',save_all=True,append_images=frames[1:],duration=(dwell+count-1)//count,loop=1,lossless=True,quality=100)
    return out.getvalue()
