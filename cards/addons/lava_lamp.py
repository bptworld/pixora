from io import BytesIO
import math

CARD_ID = "lava_lamp"
CARD_NAME = "Lava Lamp"
CARD_DETAIL = "Drifting pixel blobs"
CARD_OPTIONS = [
    {
        "key": "palette",
        "label": "Palette",
        "type": "select",
        "default": "neon",
        "choices": [
            {"value": "neon", "label": "Neon"},
            {"value": "warm", "label": "Warm"},
            {"value": "cool", "label": "Cool"},
            {"value": "sunset", "label": "Sunset"},
            {"value": "ocean", "label": "Ocean"},
        ],
    },
]


PALETTES = {
    "neon": {
        "bg": (1, 0, 10),
        "glass": (18, 22, 45),
        "colors": [(255, 70, 190), (40, 220, 255), (120, 255, 90)],
    },
    "warm": {
        "bg": (12, 2, 0),
        "glass": (55, 22, 12),
        "colors": [(255, 70, 35), (255, 160, 45), (255, 60, 120)],
    },
    "cool": {
        "bg": (0, 4, 14),
        "glass": (16, 38, 58),
        "colors": [(40, 190, 255), (70, 255, 190), (120, 90, 255)],
    },
    "sunset": {
        "bg": (12, 1, 9),
        "glass": (58, 25, 40),
        "colors": [(255, 88, 70), (255, 190, 72), (215, 72, 255)],
    },
    "ocean": {
        "bg": (0, 6, 13),
        "glass": (13, 44, 58),
        "colors": [(30, 180, 255), (35, 245, 185), (125, 230, 255)],
    },
}


def _palette(name):
    return PALETTES.get(str(name or "neon").strip().lower(), PALETTES["neon"])


def _blend(color, factor):
    return tuple(max(0, min(255, int(channel * factor))) for channel in color)


def _organic_points(cx, cy, rx, ry, phase, wobble):
    points = []
    for step in range(14):
        angle = math.tau * step / 14.0
        wave = 1.0 + math.sin(phase + step * 1.43) * wobble + math.cos(phase * 0.7 + step * 2.1) * wobble * 0.45
        x = int(round(cx + math.cos(angle) * rx * wave))
        y = int(round(cy + math.sin(angle) * ry * wave))
        points.append((x, y))
    return points


def _draw_blob(draw, cx, cy, rx, ry, color, phase):
    shadow = _blend(color, 0.28)
    body = _blend(color, 0.86)
    hot = _blend(color, 1.28)
    glow = _blend(color, 1.55)
    points = _organic_points(cx, cy, rx + 1, ry + 1, phase, 0.16)
    draw.polygon([(x + 1, y + 1) for x, y in points], fill=shadow)
    draw.polygon(points, fill=body)

    lobe_a = (
        cx - int(rx * 0.72),
        cy - int(ry * 0.55),
        cx + int(rx * 0.28),
        cy + int(ry * 0.42),
    )
    lobe_b = (
        cx - int(rx * 0.16),
        cy - int(ry * 0.38),
        cx + int(rx * 0.78),
        cy + int(ry * 0.65),
    )
    draw.ellipse(lobe_a, fill=color)
    draw.ellipse(lobe_b, fill=body)
    draw.arc((cx - rx + 2, cy - ry + 1, cx + rx - 2, cy + ry - 2), 205, 315, fill=hot)
    draw.point((cx - max(1, rx // 3), cy - max(1, ry // 2)), fill=glow)


def render(options=None):
    from PIL import Image, ImageDraw

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    palette = _palette(opts.get("palette"))
    colors = palette["colors"]
    frames = []
    dwell_ms = max(3000, min(60000, int(opts.get("_dwell", 10) or 10) * 1000))
    frame_count = max(32, min(96, int(round(dwell_ms / 90))))
    frame_duration = max(45, int(round(dwell_ms / frame_count)))
    blob_count = 6 if width == 128 else 4
    for frame in range(frame_count):
        t = frame / frame_count
        image = Image.new("RGB", (width, 32), palette["bg"])
        draw = ImageDraw.Draw(image)
        for y in range(3, 30, 6):
            draw.line((2, y, width - 3, y), fill=_blend(palette["glass"], 0.45))
        for i in range(blob_count):
            color = colors[i % len(colors)]
            lane = (i + 0.5) / blob_count
            drift = (t * (0.65 + i * 0.11) + i * 0.23) % 1.0
            cx = int(5 + lane * (width - 10) + math.sin(t * math.tau * 1.2 + i * 1.9) * (5 + width * 0.02))
            cy = int(30 - drift * 36 + math.sin(t * math.tau * 1.6 + i) * 3)
            if cy < -6:
                cy += 42
            phase = t * math.tau * (2.0 + i * 0.17) + i
            rx = 5 + (i % 3) + int((math.sin(phase) + 1.0) * 1.5)
            ry = 5 + ((i + 1) % 3) + int((math.cos(phase * 0.85) + 1.0) * 1.5)
            _draw_blob(draw, cx, cy, rx, ry, color, phase)
        draw.rectangle((0, 0, width - 1, 31), outline=palette["glass"])
        draw.line((2, 1, width - 3, 1), fill=_blend(palette["glass"], 1.35))
        draw.line((2, 30, width - 3, 30), fill=_blend(palette["glass"], 1.15))
        frames.append(image)

    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:],
                   duration=frame_duration, loop=1, lossless=True, quality=100)
    return out.getvalue()
