from io import BytesIO
import math

CARD_ID = "pixel_globe"
CARD_NAME = "Pixel Globe"
CARD_DETAIL = "Tiny rotating world"
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
        return 85
    if speed == "slow":
        return 180
    return 125


LAND_MASSES = [
    [(-2.55, -0.30), (-2.35, -0.18), (-2.12, -0.28), (-2.02, -0.04), (-2.25, 0.08), (-2.48, 0.02)],
    [(-1.72, 0.32), (-1.47, 0.48), (-1.16, 0.38), (-1.05, 0.12), (-1.34, 0.02), (-1.62, 0.10)],
    [(-0.78, -0.05), (-0.45, 0.10), (-0.18, -0.02), (-0.24, -0.30), (-0.58, -0.35)],
    [(0.10, 0.42), (0.38, 0.55), (0.72, 0.36), (0.62, 0.12), (0.28, 0.18)],
    [(0.78, -0.20), (1.08, -0.06), (1.32, -0.24), (1.10, -0.44), (0.84, -0.38)],
    [(1.82, 0.18), (2.10, 0.32), (2.42, 0.18), (2.30, -0.05), (1.98, -0.10)],
]


def _blend(color, factor):
    return tuple(max(0, min(255, int(channel * factor))) for channel in color)


def _project(lon, lat, rot, cx, cy, r):
    rel = lon + rot
    x3 = math.sin(rel) * math.cos(lat)
    z3 = math.cos(rel) * math.cos(lat)
    y3 = math.sin(lat)
    x = cx + x3 * r
    y = cy - y3 * r * 0.82
    return x, y, z3


def _draw_starfield(draw, width, frame):
    stars = [
        (5, 4, 0), (12, 23, 2), (19, 7, 1), (width - 9, 5, 1),
        (width - 17, 25, 0), (width - 4, 18, 2), (width - 27, 10, 1),
    ]
    for x, y, phase in stars:
        color = (95, 125, 190) if (frame + phase) % 4 else (170, 205, 255)
        draw.point((x, y), fill=color)


def _draw_globe(draw, cx, cy, r, rot):
    ocean_dark = (16, 65, 150)
    ocean = (28, 118, 230)
    ocean_light = (72, 170, 255)
    rim = (118, 215, 255)
    night = (2, 13, 42)
    land = (62, 206, 116)
    land_dark = (36, 132, 78)
    ice = (218, 246, 255)

    draw.ellipse((cx - r - 1, cy - r + 1, cx + r + 1, cy + r + 3), fill=(0, 5, 18))
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ocean_dark, outline=rim)
    draw.ellipse((cx - r + 3, cy - r + 2, cx + r - 1, cy + r - 2), fill=ocean)
    draw.arc((cx - r + 2, cy - r + 1, cx + r - 2, cy + r - 1), 200, 315, fill=ocean_light)
    draw.point((cx - 5, cy - 7), fill=(135, 220, 255))

    for lat in (-0.45, 0.0, 0.45):
        y = int(round(cy - math.sin(lat) * r * 0.82))
        half = int(round(math.cos(lat) * r))
        draw.arc((cx - half, y - 3, cx + half, y + 3), 0, 360, fill=(45, 145, 230))

    for lon in (-1.1, 0.0, 1.1):
        x_offset = math.sin(rot + lon) * r
        visible = math.cos(rot + lon)
        color = (54, 155, 235) if visible > 0 else (21, 73, 155)
        draw.arc((cx - abs(x_offset) - 2, cy - r + 1, cx + abs(x_offset) + 2, cy + r - 1), 90, 270, fill=color)

    for mass in LAND_MASSES:
        projected = []
        visible_z = []
        for lon, lat in mass:
            x, y, z = _project(lon, lat, rot, cx, cy, r)
            projected.append((int(round(x)), int(round(y))))
            visible_z.append(z)
        if sum(visible_z) / len(visible_z) <= -0.08:
            continue
        color = land if max(visible_z) > 0.2 else land_dark
        draw.polygon(projected, fill=color)
        if len(projected) > 2:
            draw.line(projected[:2], fill=_blend(color, 1.35))

    draw.arc((cx - r, cy - r, cx + r, cy + r), 270, 90, fill=night, width=3)
    draw.arc((cx - r, cy - r, cx + r, cy + r), 100, 250, fill=rim)
    draw.rectangle((cx - 4, cy - r + 2, cx + 3, cy - r + 3), fill=ice)
    draw.rectangle((cx - 5, cy + r - 3, cx + 4, cy + r - 2), fill=_blend(ice, 0.8))


def render(options=None):
    from PIL import Image, ImageDraw

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    frames = []
    dwell_ms = max(3000, min(60000, int(opts.get("_dwell", 10) or 10) * 1000))
    base_duration = _duration(opts.get("speed"))
    frame_count = max(32, min(96, int(round(dwell_ms / base_duration))))
    frame_duration = max(45, int(round(dwell_ms / frame_count)))
    for frame in range(frame_count):
        image = Image.new("RGB", (width, 32), (0, 1, 12))
        draw = ImageDraw.Draw(image)
        rot = frame / frame_count * math.tau
        _draw_starfield(draw, width, frame)
        _draw_globe(draw, width // 2, 16, 12, rot)
        frames.append(image)

    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:],
                   duration=frame_duration, loop=1, lossless=True, quality=100)
    return out.getvalue()
