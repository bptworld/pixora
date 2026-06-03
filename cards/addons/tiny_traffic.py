from io import BytesIO

CARD_ID = "tiny_traffic"
CARD_NAME = "Tiny Traffic"
CARD_DETAIL = "Cars and signal lights"
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
        return 75
    if speed == "slow":
        return 165
    return 110


def _blend(color, factor):
    return tuple(max(0, min(255, int(channel * factor))) for channel in color)


def _phase(frame):
    cycle = frame % 48
    if cycle < 18:
        return "green"
    if cycle < 24:
        return "yellow"
    return "red"


def _traffic_progress(raw, light, stop_at):
    if light == "red" and stop_at - 0.12 < raw < stop_at + 0.18:
        return stop_at - 0.035
    if light == "yellow" and stop_at - 0.08 < raw < stop_at + 0.08:
        return raw * 0.45 + (stop_at - 0.02) * 0.55
    return raw


def _draw_background(draw, width, frame):
    sky_top = (4, 8, 18)
    sky_bottom = (7, 15, 24)
    for y in range(0, 10):
        t = y / 9.0
        color = tuple(int(sky_top[i] * (1 - t) + sky_bottom[i] * t) for i in range(3))
        draw.line((0, y, width - 1, y), fill=color)
    for i, x in enumerate(range(3, width, 13)):
        color = (95, 120, 175) if (frame + i) % 7 else (190, 215, 255)
        draw.point((x, 2 + (i * 5) % 7), fill=color)
    draw.rectangle((0, 9, width - 1, 12), fill=(18, 35, 31))
    for x in range(2, width, 11):
        draw.rectangle((x, 5, x + 5, 11), fill=(12, 22, 30))
        if (x + frame) % 3 == 0:
            draw.point((x + 2, 7), fill=(255, 210, 110))
    draw.rectangle((0, 24, width - 1, 31), fill=(20, 24, 21))
    draw.rectangle((0, 25, width - 1, 26), fill=(55, 62, 58))


def _draw_road(draw, width, frame):
    asphalt = (23, 25, 29)
    shadow = (14, 15, 18)
    draw.rectangle((0, 12, width - 1, 25), fill=asphalt)
    draw.rectangle((0, 18, width - 1, 19), fill=shadow)
    draw.line((0, 12, width - 1, 12), fill=(75, 78, 76))
    draw.line((0, 24, width - 1, 24), fill=(92, 96, 88))
    dash_offset = (frame * 2) % 14
    for x in range(-14, width + 14, 14):
        draw.line((x - dash_offset, 18, x + 6 - dash_offset, 18), fill=(245, 218, 100))
    cross_x = width - 18
    for stripe in range(4):
        y = 13 + stripe * 3
        draw.line((cross_x, y, cross_x + 8, y), fill=(215, 220, 210))


def _draw_signal(draw, width, light):
    pole = width - 8
    draw.line((pole, 5, pole, 25), fill=(72, 78, 86))
    draw.rectangle((pole - 4, 4, pole + 3, 14), fill=(20, 22, 27), outline=(92, 96, 105))
    states = [
        ("red", 6, (255, 48, 38), (60, 15, 15)),
        ("yellow", 9, (255, 218, 62), (62, 48, 14)),
        ("green", 12, (75, 255, 105), (16, 58, 18)),
    ]
    for name, y, on, off in states:
        color = on if light == name else off
        draw.rectangle((pole - 2, y, pole, y + 1), fill=color)
        if light == name:
            draw.point((pole + 1, y), fill=_blend(on, 1.35))


def _draw_car(draw, x, y, color, direction=1, kind="car", lights=False):
    dark = _blend(color, 0.48)
    light = _blend(color, 1.28)
    if kind == "truck":
        draw.rectangle((x, y + 1, x + 14, y + 5), fill=dark)
        draw.rectangle((x + 1, y, x + 9, y + 4), fill=color)
        draw.rectangle((x + 10, y + 2, x + 14, y + 5), fill=_blend(color, 0.75))
    else:
        draw.rectangle((x, y + 2, x + 11, y + 5), fill=dark)
        draw.rectangle((x + 1, y + 1, x + 10, y + 4), fill=color)
        draw.rectangle((x + 3, y, x + 8, y + 2), fill=light)
    draw.point((x + 2, y + 6), fill=(4, 5, 6))
    draw.point((x + 9, y + 6), fill=(4, 5, 6))
    if direction > 0:
        draw.point((x + 11, y + 3), fill=(255, 245, 160) if lights else (240, 235, 175))
        draw.point((x, y + 3), fill=(255, 40, 35))
        if lights:
            draw.line((x + 12, y + 3, x + 15, y + 2), fill=(95, 85, 45))
    else:
        draw.point((x, y + 3), fill=(255, 245, 160) if lights else (240, 235, 175))
        draw.point((x + 11, y + 3), fill=(255, 40, 35))
        if lights:
            draw.line((x - 1, y + 3, x - 4, y + 2), fill=(95, 85, 45))


def render(options=None):
    from PIL import Image, ImageDraw

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    frames = []
    dwell_ms = max(3000, min(60000, int(opts.get("_dwell", 10) or 10) * 1000))
    base_duration = _duration(opts.get("speed"))
    frame_count = max(24, min(72, int(round(dwell_ms / base_duration))))
    frame_duration = max(45, int(round(dwell_ms / frame_count)))
    for frame in range(frame_count):
        light = _phase(frame)
        image = Image.new("RGB", (width, 32), (4, 8, 18))
        draw = ImageDraw.Draw(image)
        _draw_background(draw, width, frame)
        _draw_road(draw, width, frame)
        _draw_signal(draw, width, light)

        lane = width + 34
        raw_a = (frame * 2.2 / lane) % 1.0
        raw_b = (frame * 1.7 / lane + 0.45) % 1.0
        raw_c = (frame * 1.35 / lane + 0.12) % 1.0
        progress_a = _traffic_progress(raw_a, light, 0.69)
        x_a = -16 + int(progress_a * lane)
        x_b = width + 10 - int(raw_b * lane)
        x_c = -22 + int(raw_c * lane)
        _draw_car(draw, x_a, 13, (70, 165, 255), 1, "car", lights=True)
        _draw_car(draw, x_b, 19, (255, 82, 70), -1, "truck", lights=True)
        if width == 128 or frame % 3 != 0:
            _draw_car(draw, x_c, 13, (255, 190, 70), 1, "car", lights=False)
        frames.append(image)

    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:],
                   duration=frame_duration, loop=1, lossless=True, quality=100)
    return out.getvalue()
