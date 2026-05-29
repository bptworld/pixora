from io import BytesIO
import math

CARD_ID = "aquarium"
CARD_NAME = "Pixel Aquarium"
CARD_DETAIL = "Fish and bubbles"
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


FISH = [
    {"phase": 0.00, "speed": 1.00, "y": 10, "amp": 3, "color": (255, 170, 55), "left": False, "size": 1},
    {"phase": 0.35, "speed": 0.82, "y": 20, "amp": 2, "color": (80, 220, 255), "left": True, "size": 1},
    {"phase": 0.68, "speed": 1.22, "y": 15, "amp": 4, "color": (255, 110, 180), "left": False, "size": 0},
]


def _hash_noise(x, y, frame):
    value = (x * 374761393 + y * 668265263 + frame * 2246822519) & 0xFFFFFFFF
    value = (value ^ (value >> 13)) * 1274126177
    return (value ^ (value >> 16)) & 0xFF


def _blend(color, factor):
    return tuple(max(0, min(255, int(channel * factor))) for channel in color)


def _fish(draw, x, y, color, left=False, size=1, step=0):
    rx = 3 + size
    ry = 2 + (1 if size > 0 else 0)
    body = (x - rx, y - ry, x + rx, y + ry)
    draw.ellipse(body, fill=color)
    draw.arc((x - rx, y - ry, x + rx, y + ry), 205, 315, fill=_blend(color, 1.35))
    tail_flick = 1 if step % 6 < 3 else 0
    if left:
        draw.polygon([(x + rx, y), (x + rx + 4 + size, y - 3 - tail_flick), (x + rx + 4 + size, y + 3 + tail_flick)], fill=_blend(color, 0.85))
        draw.point((x - max(1, rx - 1), y - 1), fill=(0, 0, 0))
    else:
        draw.polygon([(x - rx, y), (x - rx - 4 - size, y - 3 - tail_flick), (x - rx - 4 - size, y + 3 + tail_flick)], fill=_blend(color, 0.85))
        draw.point((x + max(1, rx - 1), y - 1), fill=(0, 0, 0))
    draw.point((x, y + ry), fill=_blend(color, 0.55))


def _draw_tank(draw, width, frame):
    top = (0, 16, 38)
    bottom = (0, 30, 48)
    for y in range(32):
        t = y / 31.0
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        draw.line((0, y, width - 1, y), fill=color)
    for y in (5, 13, 21):
        offset = (frame + y) % 9
        for x in range(-offset, width, 18):
            draw.point((x, y), fill=(15, 55, 78))
            draw.point((x + 8, y + 1), fill=(10, 44, 68))
    draw.rectangle((0, 26, width - 1, 31), fill=(30, 38, 21))
    for x in range(0, width, 4):
        shade = 36 + (_hash_noise(x, 27, 2) % 28)
        draw.point((x, 28 + (_hash_noise(x, 29, 3) % 3)), fill=(shade, shade - 10, 24))
    draw.rectangle((0, 0, width - 1, 31), outline=(12, 55, 78))


def _draw_plants(draw, width, frame):
    for i, x in enumerate(range(2, width, 7)):
        height = 3 + (_hash_noise(i, width, 5) % 6)
        sway = (_hash_noise(i, frame // 3, 8) % 3) - 1
        color = (35, 130 + (_hash_noise(i, 2, 1) % 70), 80)
        draw.line((x, 30, x + sway, 30 - height), fill=color)
        if height > 5:
            draw.point((x + sway + 1, 28 - height), fill=_blend(color, 1.25))


def _draw_bubbles(draw, width, frame, frame_count):
    count = 8 if width == 64 else 15
    for i in range(count):
        lane = 4 + (_hash_noise(i, width, 12) % max(1, width - 8))
        speed = 0.65 + (_hash_noise(i, 4, 9) % 65) / 100.0
        phase = (_hash_noise(i, 7, 1) / 255.0)
        t = ((frame / frame_count) * speed + phase) % 1.0
        by = int(29 - t * 34)
        bx = lane + int(math.sin(t * math.tau * 1.4 + i) * 2)
        if by > 1:
            size = 1 + (_hash_noise(i, by, frame // 2) % 2)
            color = (95, 185, 230) if i % 3 else (145, 225, 255)
            draw.rectangle((bx, by, bx + size, by + size), outline=color)


def render(options=None):
    from PIL import Image, ImageDraw

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    dwell_ms = max(3000, min(60000, int(opts.get("_dwell", 10) or 10) * 1000))
    base_duration = _duration(opts.get("speed"))
    frame_count = max(24, min(72, int(round(dwell_ms / base_duration))))
    frame_duration = max(45, int(round(dwell_ms / frame_count)))
    frames = []
    for frame in range(frame_count):
        t = frame / frame_count
        image = Image.new("RGB", (width, 32), (0, 15, 35))
        draw = ImageDraw.Draw(image)
        _draw_tank(draw, width, frame)
        _draw_plants(draw, width, frame)
        _draw_bubbles(draw, width, frame, frame_count)
        swim = width + 34
        for i, fish in enumerate(FISH):
            progress = (t * fish["speed"] + fish["phase"]) % 1.0
            if fish["left"]:
                x = width + 14 - int(progress * swim)
            else:
                x = -14 + int(progress * swim)
            wobble = math.sin(t * math.tau * (1.0 + i * 0.35) + i * 1.7)
            y = fish["y"] + int(wobble * fish["amp"]) + ((_hash_noise(frame // 8, i, 4) % 3) - 1)
            if -12 <= x <= width + 12:
                _fish(draw, x, y, fish["color"], left=fish["left"], size=fish["size"], step=frame + i)
        frames.append(image)

    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:],
                   duration=frame_duration, loop=1, lossless=True, quality=100)
    return out.getvalue()
