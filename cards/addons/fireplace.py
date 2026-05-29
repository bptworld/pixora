from io import BytesIO

CARD_ID = "fireplace"
CARD_NAME = "Fireplace"
CARD_DETAIL = "Realistic pixel fire"
CARD_OPTIONS = [
    {
        "key": "height",
        "label": "Height",
        "type": "select",
        "default": "normal",
        "choices": [
            {"value": "low", "label": "Low"},
            {"value": "normal", "label": "Normal"},
            {"value": "tall", "label": "Tall"},
        ],
    },
]


def _palette(value):
    value = max(0, min(255, int(value)))
    stops = [
        (0, (2, 0, 0)),
        (26, (22, 3, 1)),
        (54, (75, 12, 3)),
        (92, (150, 32, 5)),
        (132, (228, 74, 8)),
        (176, (255, 142, 20)),
        (216, (255, 215, 75)),
        (255, (255, 248, 190)),
    ]
    for index in range(len(stops) - 1):
        left_value, left_color = stops[index]
        right_value, right_color = stops[index + 1]
        if value <= right_value:
            span = max(1, right_value - left_value)
            t = (value - left_value) / span
            return tuple(int(left_color[channel] + (right_color[channel] - left_color[channel]) * t) for channel in range(3))
    return stops[-1][1]


def _hash_noise(x, y, frame):
    value = (x * 374761393 + y * 668265263 + frame * 2246822519) & 0xFFFFFFFF
    value = (value ^ (value >> 13)) * 1274126177
    return (value ^ (value >> 16)) & 0xFF


def _draw_logs(draw, width):
    base_y = 29
    draw.rectangle((0, 27, width - 1, 31), fill=(10, 4, 3))
    logs = [
        (6, 25, width // 2 + 7, 30, (66, 34, 17), (20, 8, 5)),
        (width // 2 - 9, 23, width - 6, 28, (80, 39, 18), (22, 9, 5)),
        (13, 27, width - 14, 31, (45, 22, 11), (13, 5, 3)),
    ]
    for x1, y1, x2, y2, bark, dark in logs:
        draw.rounded_rectangle((x1, y1, x2, y2), radius=2, fill=bark)
        draw.line((x1 + 2, y1 + 1, x2 - 2, y2 - 1), fill=dark)
        draw.line((x1 + 5, y2 - 1, x2 - 5, y1 + 2), fill=(126, 58, 21))
        draw.ellipse((x1 - 2, y1, x1 + 4, y2), fill=(30, 12, 6), outline=(112, 55, 22))
        draw.ellipse((x2 - 4, y1, x2 + 2, y2), fill=(28, 11, 5), outline=(104, 49, 19))
    draw.rectangle((0, base_y, width - 1, 31), fill=(12, 5, 4))


def _draw_firebox(draw, width):
    draw.rectangle((0, 0, width - 1, 31), fill=(8, 0, 0))
    back_left = 8 if width == 64 else 18
    back_right = width - back_left - 1
    draw.rectangle((back_left, 0, back_right, 27), fill=(12, 1, 1))
    draw.rectangle((0, 0, back_left - 1, 31), fill=(9, 0, 0))
    draw.rectangle((back_right + 1, 0, width - 1, 31), fill=(9, 0, 0))
    brick = (25, 5, 4)
    dark = (8, 0, 0)
    for y in range(7, 24, 8):
        draw.line((back_left, y, back_right, y), fill=brick)
    draw.rectangle((0, 0, width - 1, 2), fill=dark)
    draw.rectangle((0, 28, width - 1, 31), fill=(6, 2, 2))


def render(options=None):
    from PIL import Image, ImageDraw, ImageFilter

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    height_mode = str(opts.get("height", "normal")).lower()
    flame_height = {"low": 17, "normal": 22, "tall": 28}.get(height_mode, 22)
    base_y = 26

    dwell_ms = max(3000, min(60000, int(opts.get("_dwell", 10) or 10) * 1000))
    frame_count = max(30, min(96, int(round(dwell_ms / 70))))
    frame_duration = max(45, int(round(dwell_ms / frame_count)))

    frames = []
    source_count = 3 if width == 64 else 5

    for frame in range(frame_count):
        image = Image.new("RGB", (width, 32), (2, 0, 0))
        draw = ImageDraw.Draw(image)
        _draw_firebox(draw, width)
        pixels = image.load()
        for y in range(max(0, base_y - flame_height - 2), base_y + 2):
            rise = max(0.0, min(1.0, (base_y - y) / max(1, flame_height)))
            envelope = (1.0 - rise) ** 0.58
            for x in range(width):
                heat_value = 0.0
                for source in range(source_count):
                    anchor = width * (0.30 + source * (0.40 / max(1, source_count - 1)))
                    sway = ((_hash_noise(source * 13, int(rise * 31), frame) / 255.0) - 0.5) * (3.0 + rise * 8.0)
                    center = anchor + sway + (rise * rise * (source - source_count / 2) * 0.72)
                    radius = (width / 8.2) * (1.05 * envelope + 0.08)
                    distance = abs(x - center) / max(0.1, radius)
                    if distance < 1.55:
                        tongue = max(0.0, 1.0 - distance / 1.25) ** 1.42
                        flicker = 0.76 + (_hash_noise(x + source * 17, y, frame) / 255.0) * 0.42
                        heat_value += 270 * tongue * (1.0 - rise * 0.54) * flicker

                hearth_center = abs(x - width / 2) / (width / 2)
                bed_glow = max(0.0, 1.0 - hearth_center * 1.6) * max(0.0, 1.0 - rise * 6.0) * 190
                core = max(0.0, 1.0 - abs(x - width / 2) / (width * (0.14 + envelope * 0.13))) * max(0.0, 1.0 - rise * 1.55) * 150
                heat_value += bed_glow + core
                heat_value -= rise * 48
                heat_value += (_hash_noise(x, y, frame + 29) - 128) * 0.18
                if heat_value > 10:
                    existing = pixels[x, y]
                    color = _palette(heat_value)
                    pixels[x, y] = tuple(max(existing[i], color[i]) for i in range(3))

        glow = image.filter(ImageFilter.GaussianBlur(radius=1.15))
        image = Image.blend(glow, image, 0.78)
        draw = ImageDraw.Draw(image)

        for x in range(2, width - 2, 7):
            if _hash_noise(x, 3, frame) > 232:
                spark_y = 4 + (_hash_noise(x, 8, frame) % 11)
                spark_x = max(1, min(width - 2, x + (_hash_noise(x, 9, frame) % 5) - 2))
                draw.point((spark_x, spark_y), fill=(255, 188, 62))

        _draw_logs(draw, width)
        frames.append(image)

    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=frame_duration,
        loop=1,
        lossless=True,
        quality=100,
    )
    return out.getvalue()
