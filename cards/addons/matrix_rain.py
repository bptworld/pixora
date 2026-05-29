from io import BytesIO

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


def _duration(value):
    speed = str(value or "normal").strip().lower()
    if speed == "fast":
        return 58
    if speed == "slow":
        return 130
    return 82


def _hash_noise(x, y, frame):
    value = (x * 374761393 + y * 668265263 + frame * 2246822519) & 0xFFFFFFFF
    value = (value ^ (value >> 13)) * 1274126177
    return (value ^ (value >> 16)) & 0xFF


def _glyph(index):
    glyphs = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ@$%#"
    return glyphs[index % len(glyphs)]


def render(options=None):
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64

    try:
        font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        try:
            font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        except Exception:
            font = ImageFont.load_default()

    dwell_ms = max(3000, min(60000, int(opts.get("_dwell", 10) or 10) * 1000))
    base_duration = _duration(opts.get("speed"))
    frame_count = max(28, min(96, int(round(dwell_ms / base_duration))))
    frame_duration = max(45, int(round(dwell_ms / frame_count)))

    columns = []
    x = 0
    index = 0
    while x < width:
        gap = 3 + (_hash_noise(index, 3, 1) % 3)
        columns.append({
            "x": x,
            "seed": index * 19 + 7,
            "speed": 1 + (_hash_noise(index, 5, 2) % 3),
            "offset": _hash_noise(index, 7, 3) % 48,
            "length": 4 + (_hash_noise(index, 11, 4) % 6),
            "dim": 0.55 + (_hash_noise(index, 13, 5) / 255.0) * 0.45,
        })
        x += gap
        index += 1

    frames = []
    for frame in range(frame_count):
        image = Image.new("RGB", (width, 32), (0, 2, 0))
        draw = ImageDraw.Draw(image)

        for col_index, column in enumerate(columns):
            x = column["x"]
            head = ((column["offset"] + frame * column["speed"]) % 52) - 10
            length = column["length"]
            for trail in range(length):
                y = head - trail * 5
                if y < -8 or y > 33:
                    continue

                fade = max(0.0, 1.0 - trail / max(1, length))
                flicker = 0.74 + (_hash_noise(col_index, trail, frame) / 255.0) * 0.42
                value = int(225 * fade * flicker * column["dim"])
                if trail == 0:
                    color = (190, 255, 205)
                elif trail == 1:
                    color = (58, min(255, value + 70), 82)
                else:
                    color = (0, max(22, value), max(18, value // 3))

                if _hash_noise(col_index, trail, frame + 31) > 232 and trail > 1:
                    color = (0, max(18, value // 2), max(10, value // 5))

                draw.text((x, y), _glyph(column["seed"] + frame + trail * 3), fill=color, font=font)

        glow = image.filter(ImageFilter.GaussianBlur(radius=0.85))
        image = Image.blend(glow, image, 0.74)
        pixels = image.load()
        for y in range(32):
            for x in range(width):
                r, g, b = pixels[x, y]
                if g > 18:
                    pixels[x, y] = (min(80, r), min(255, g + 12), min(110, b + 8))
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
