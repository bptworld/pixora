from io import BytesIO

CARD_ID = "snake"
CARD_NAME = "Snake"
CARD_DETAIL = "Snake eats dots"
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


def _duration(value):
    speed = str(value or "normal").strip().lower()
    if speed == "fast":
        return 80
    if speed == "slow":
        return 170
    return 115


def _path(width=64):
    right = width - 8
    mid = width // 2
    pts = []
    runs = [
        ((4, 8), (right - 12, 8), (4, 0)),
        ((right - 8, 12), (right - 8, 20), (0, 4)),
        ((right - 12, 24), (mid + 4, 24), (-4, 0)),
        ((mid, 20), (mid, 12), (0, -4)),
        ((mid - 4, 12), (12, 12), (-4, 0)),
        ((8, 16), (8, 24), (0, 4)),
        ((12, 24), (mid - 8, 24), (4, 0)),
        ((mid - 4, 20), (mid - 4, 16), (0, -4)),
        ((mid, 16), (right - 4, 16), (4, 0)),
        ((right, 12), (right, 8), (0, -4)),
    ]
    for (x, y), (end_x, end_y), (dx, dy) in runs:
        while True:
            if not pts or pts[-1] != (x, y):
                pts.append((x, y))
            if (x, y) == (end_x, end_y):
                break
            x += dx
            y += dy
    return pts


def _hash_noise(x, y, frame):
    value = (x * 374761393 + y * 668265263 + frame * 2246822519) & 0xFFFFFFFF
    value = (value ^ (value >> 13)) * 1274126177
    return (value ^ (value >> 16)) & 0xFF


def _blend(color, factor):
    return tuple(max(0, min(255, int(channel * factor))) for channel in color)


def _draw_board(draw, width, frame):
    bg = (0, 12, 5)
    grid = (3, 28, 11)
    wall = (18, 86, 32)
    wall_light = (58, 175, 72)
    draw.rectangle((0, 0, width - 1, 31), fill=bg)
    for x in range(4, width, 8):
        draw.line((x, 2, x, 29), fill=grid)
    for y in range(4, 32, 8):
        draw.line((2, y, width - 3, y), fill=grid)
    draw.rectangle((0, 0, width - 1, 31), outline=wall)
    draw.line((1, 1, width - 2, 1), fill=wall_light)
    draw.line((1, 30, width - 2, 30), fill=(8, 45, 18))
    for i in range(7 if width == 64 else 13):
        x = 3 + (_hash_noise(i, 11, frame // 3) % max(1, width - 6))
        y = 3 + (_hash_noise(i, 17, frame // 4) % 26)
        if _hash_noise(i, y, frame) > 186:
            draw.point((x, y), fill=(21, 70, 26))


def _direction(path, index):
    x1, y1 = path[index % len(path)]
    x2, y2 = path[(index + 1) % len(path)]
    dx = (x2 > x1) - (x2 < x1)
    dy = (y2 > y1) - (y2 < y1)
    return dx, dy


def _draw_food(draw, x, y, frame):
    pulse = 1 if frame % 8 in (0, 1, 2) else 0
    draw.rectangle((x - 2, y - 2, x + 2, y + 2), fill=(42, 8, 10))
    draw.rectangle((x - 1 - pulse, y - 1 - pulse, x + 1 + pulse, y + 1 + pulse), fill=(235, 42, 54))
    draw.point((x - 1, y - 1), fill=(255, 190, 130))
    draw.point((x + 1, y - 2), fill=(65, 220, 95))


def _draw_segment(draw, x, y, color, head=False):
    dark = _blend(color, 0.45)
    light = _blend(color, 1.3)
    draw.rectangle((x - 2, y - 2, x + 2, y + 2), fill=dark)
    draw.rectangle((x - 1, y - 1, x + 1, y + 1), fill=color)
    draw.point((x - 1, y - 2), fill=light)
    if head:
        draw.rectangle((x - 2, y - 2, x + 2, y + 2), outline=light)


def _draw_head_details(draw, x, y, dx, dy):
    eye = (1, -1) if dx > 0 else (-1, -1) if dx < 0 else (-1, -1)
    other = (1, 1) if dx > 0 else (-1, 1) if dx < 0 else (1, -1)
    draw.point((x + eye[0], y + eye[1]), fill=(2, 12, 2))
    draw.point((x + other[0], y + other[1]), fill=(2, 12, 2))
    if dx:
        tx = x + dx * 3
        draw.point((tx, y), fill=(255, 70, 90))
        draw.point((tx + dx, y - 1), fill=(255, 70, 90))
        draw.point((tx + dx, y + 1), fill=(255, 70, 90))
    elif dy:
        ty = y + dy * 3
        draw.point((x, ty), fill=(255, 70, 90))
        draw.point((x - 1, ty + dy), fill=(255, 70, 90))
        draw.point((x + 1, ty + dy), fill=(255, 70, 90))


def _food_position(path, frame, length, width):
    occupied = {path[(frame - i) % len(path)] for i in range(length + 1)}
    best = path[(frame + len(path) // 2) % len(path)]
    best_distance = -1
    seed = frame // 9
    for attempt in range(10):
        offset = 8 + (_hash_noise(seed + attempt * 3, width, 31) % max(9, len(path) - 8))
        candidate = path[(frame + offset) % len(path)]
        if candidate in occupied:
            continue
        distance = min(abs(candidate[0] - x) + abs(candidate[1] - y) for x, y in occupied)
        if distance > best_distance:
            best = candidate
            best_distance = distance
    return best


def render(options=None):
    from PIL import Image, ImageDraw

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    path = _path(width)
    dwell_ms = max(3000, min(60000, int(opts.get("_dwell", 10) or 10) * 1000))
    base_duration = _duration(opts.get("speed"))
    frame_count = max(len(path), min(96, int(round(dwell_ms / base_duration))))
    frame_duration = max(45, int(round(dwell_ms / frame_count)))
    frames = []
    for frame in range(frame_count):
        image = Image.new("RGB", (width, 32), (0, 12, 5))
        draw = ImageDraw.Draw(image)
        _draw_board(draw, width, frame)
        length = 10 + (_hash_noise(frame // 16, width, 3) % 5)
        food = _food_position(path, frame, length, width)
        _draw_food(draw, food[0], food[1], frame)
        for i in range(length, -1, -1):
            x, y = path[(frame - i) % len(path)]
            fade = max(0.34, 1.0 - i * 0.055)
            shimmer = 0.86 + (_hash_noise(i, frame, 19) / 255.0) * 0.22
            col = (int(74 * fade * shimmer), int(255 * fade * shimmer), int(88 * fade * shimmer))
            _draw_segment(draw, x, y, col, head=(i == 0))
        hx, hy = path[frame % len(path)]
        dx, dy = _direction(path, frame)
        _draw_head_details(draw, hx, hy, dx, dy)
        frames.append(image)

    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:],
                   duration=frame_duration, loop=1, lossless=True, quality=100)
    return out.getvalue()
