from io import BytesIO

CARD_ID = "heartbeat"
CARD_NAME = "8-Bit Heartbeat"
CARD_DETAIL = "Pulsing pixel heart"
CARD_OPTIONS = [
    {
        "key": "color",
        "label": "Color",
        "type": "select",
        "default": "red",
        "choices": [
            {"value": "red", "label": "Red"},
            {"value": "pink", "label": "Pink"},
            {"value": "blue", "label": "Blue"},
            {"value": "green", "label": "Green"},
        ],
    },
]


def _color(value):
    v = str(value or "red").lower()
    if v == "blue":
        return (60, 170, 255)
    if v == "pink":
        return (255, 90, 190)
    if v == "green":
        return (80, 240, 120)
    return (255, 45, 75)


def _blend(color, factor):
    return tuple(max(0, min(255, int(channel * factor))) for channel in color)


def _draw_ecg(draw, width, frame):
    baseline = 17
    pattern_width = 34
    offset = (frame * 3) % pattern_width
    points = [
        (0, baseline),
        (9, baseline),
        (12, baseline - 6),
        (16, baseline + 9),
        (20, baseline - 2),
        (23, baseline),
        (34, baseline),
    ]
    shadow = (0, 42, 58)
    blue = (75, 230, 255)
    hot = (180, 255, 255)
    for start in range(-pattern_width * 2, width + pattern_width * 2, pattern_width):
        shifted = [(start + x - offset, y) for x, y in points]
        draw.line(shifted, fill=shadow, width=3)
        draw.line(shifted, fill=blue)
        for x, y in shifted:
            if -1 <= x <= width:
                draw.point((x, y), fill=hot)


def _draw_pixel_heart(draw, cx, cy, color, pulse):
    pattern = [
        "01100110",
        "11111111",
        "11111111",
        "11111111",
        "01111110",
        "00111100",
        "00011000",
        "00000000",
    ]
    pixel = 3
    grow = 1 if pulse else 0
    heart_w = len(pattern[0]) * pixel
    heart_h = (len(pattern) - 1) * pixel
    x0 = cx - heart_w // 2
    y0 = cy - heart_h // 2
    dark = _blend(color, 0.38)
    mid = _blend(color, 0.78)
    light = _blend(color, 1.35)
    shine = (255, 185, 205) if color[0] > 200 else _blend(color, 1.7)

    for row, line in enumerate(pattern):
        for col, filled in enumerate(line):
            if filled != "1":
                continue
            x = x0 + col * pixel
            y = y0 + row * pixel
            draw.rectangle((x + 1, y + 1, x + pixel + grow, y + pixel + grow), fill=dark)
    for row, line in enumerate(pattern):
        for col, filled in enumerate(line):
            if filled != "1":
                continue
            x = x0 + col * pixel
            y = y0 + row * pixel
            fill = light if row < 2 and col in (1, 2, 5, 6) else mid if row > 4 else color
            draw.rectangle((x, y, x + pixel - 1 + grow, y + pixel - 1 + grow), fill=fill)

    draw.rectangle((x0 + 2 * pixel, y0 + pixel, x0 + 2 * pixel + 1, y0 + pixel + 1), fill=shine)
    draw.rectangle((x0 + 5 * pixel, y0 + pixel, x0 + 5 * pixel + 1, y0 + pixel + 1), fill=shine)


def render(options=None):
    from PIL import Image, ImageDraw

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    color = _color(opts.get("color"))
    frames = []
    dwell_ms = max(3000, min(60000, int(opts.get("_dwell", 10) or 10) * 1000))
    beat = [0, 0, 1, 0, 0, 0, 1, 0]
    frame_count = max(24, min(96, int(round(dwell_ms / 90))))
    frame_duration = max(45, int(round(dwell_ms / frame_count)))
    for frame in range(frame_count):
        image = Image.new("RGB", (width, 32), (1, 0, 4))
        draw = ImageDraw.Draw(image)
        for y in (7, 25):
            draw.line((0, y, width - 1, y), fill=(7, 3, 13))
        _draw_ecg(draw, width, frame)
        _draw_pixel_heart(draw, width // 2, 16, color, beat[frame % len(beat)])
        frames.append(image)

    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:],
                   duration=frame_duration, loop=0, lossless=True, quality=100)
    return out.getvalue()
