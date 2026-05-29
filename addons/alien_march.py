from io import BytesIO

CARD_ID = "alien_march"
CARD_NAME = "Alien March"
CARD_DETAIL = "Retro invader parade"
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
        return 90
    if speed == "slow":
        return 190
    return 130


def _alien(draw, x, y, color, step):
    pts = [(2,0),(5,0),(1,1),(6,1),(0,2),(7,2),(0,3),(2,3),(5,3),(7,3),(0,4),(7,4)]
    for dx, dy in pts:
        draw.point((x + dx, y + dy), fill=color)
    draw.point((x + 2, y + 2), fill=(0, 0, 0))
    draw.point((x + 5, y + 2), fill=(0, 0, 0))
    if step % 2:
        draw.point((x + 1, y + 5), fill=color)
        draw.point((x + 6, y + 5), fill=color)
    else:
        draw.point((x + 3, y + 5), fill=color)
        draw.point((x + 4, y + 5), fill=color)


def render(options=None):
    from PIL import Image, ImageDraw

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    dwell_ms = max(3000, min(60000, int(opts.get("_dwell", 10) or 10) * 1000))
    base_duration = _duration(opts.get("speed"))
    frame_count = max(16, min(72, int(round(dwell_ms / base_duration))))
    frame_duration = max(45, int(round(dwell_ms / frame_count)))
    frames = []
    for frame in range(frame_count):
        image = Image.new("RGB", (width, 32), (0, 0, 8))
        draw = ImageDraw.Draw(image)
        offset = (frame % 8) - 4
        cols = 12 if width == 128 else 6
        start_x = (width - ((cols - 1) * 10 + 8)) // 2
        for row, color in enumerate([(125, 255, 90), (80, 220, 255), (255, 120, 220)]):
            for col in range(cols):
                _alien(draw, start_x + col * 10 + offset, 4 + row * 7, color, frame + row)
        ship_x = (width - 8) // 2 + ((frame % 8) - 4)
        draw.rectangle((ship_x, 27, ship_x + 8, 29), fill=(230, 230, 255))
        draw.point((ship_x + 4, 25), fill=(255, 240, 120))
        frames.append(image)

    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:],
                   duration=frame_duration, loop=1, lossless=True, quality=100)
    return out.getvalue()
