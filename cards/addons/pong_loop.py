from io import BytesIO
import math

CARD_ID = "pong_loop"
CARD_NAME = "Pong Loop"
CARD_DETAIL = "Tiny paddles and ball"
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
        return 45
    if speed == "slow":
        return 120
    return 70


def _cycles(value):
    speed = str(value or "normal").strip().lower()
    if speed == "fast":
        return 4
    if speed == "slow":
        return 2
    return 3


def _score(options, cycles):
    seed = _hash_noise(cycles, int(options.get("_dwell", 10) or 10), 37)
    left = 1 + seed % 8
    right = 1 + (seed // 17) % 8
    if left == right:
        right = (right % 8) + 1
    return left, right


def _hash_noise(x, y, frame):
    value = (x * 374761393 + y * 668265263 + frame * 2246822519) & 0xFFFFFFFF
    value = (value ^ (value >> 13)) * 1274126177
    return (value ^ (value >> 16)) & 0xFF


def _hit_y(index, cycles, side):
    if side == "left" and index % cycles == 0:
        return 15
    seed = _hash_noise(index, cycles, 11 if side == "left" else 23)
    return 6 + (seed % 17)


def _smoothstep(value):
    return value * value * (3.0 - 2.0 * value)


def _lerp(a, b, t):
    return a + (b - a) * _smoothstep(t)


def _ball_position(progress, cycles, left_wall, travel):
    cycle = int(progress) % cycles
    u = progress - int(progress)
    left_y = _hit_y(cycle, cycles, "left")
    right_y = _hit_y(cycle, cycles, "right")
    next_left_y = _hit_y(cycle + 1, cycles, "left")
    if u < 0.5:
        segment_t = u * 2.0
        x_wave = _smoothstep(segment_t)
        y = _lerp(left_y, right_y, segment_t)
    else:
        segment_t = (u - 0.5) * 2.0
        x_wave = 1.0 - _smoothstep(segment_t)
        y = _lerp(right_y, next_left_y, segment_t)
    wobble = math.sin(u * math.tau * 2.0 + cycle * 1.7) * (1.2 + (_hash_noise(cycle, cycles, 5) % 4) * 0.25)
    if u < 0.08 or 0.42 < u < 0.58 or u > 0.92:
        wobble = 0.0
    return left_wall + int(round(x_wave * travel)), max(5, min(23, int(round(y + wobble))))


def _track_paddle(ball_y, t, side):
    if side == "left":
        idle = 7 + int(round((math.sin(t * math.tau * 1.35 + 0.65) + 1.0) * 7.5))
        contact = math.cos(t * math.tau) > 0.72
    else:
        idle = 7 + int(round((math.sin(t * math.tau * 1.85 + 2.2) + 1.0) * 7.5))
        contact = math.cos(t * math.tau) < -0.72
    target = ball_y if contact else idle
    return max(3, min(22, target - 4))


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    frames = []
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        font = ImageFont.load_default()

    dwell_ms = max(3000, min(60000, int(opts.get("_dwell", 10) or 10) * 1000))
    base_duration = _duration(opts.get("speed"))
    cycles = _cycles(opts.get("speed"))
    frame_count = max(24, min(72, int(round(dwell_ms / base_duration))))
    frame_duration = max(45, int(round(dwell_ms / frame_count)))
    left_wall = 8
    right_wall = width - 11
    travel = right_wall - left_wall
    left_score, right_score = _score(opts, cycles)
    for frame in range(frame_count + 1):
        progress = 0.0 if frame == frame_count else (frame / frame_count) * cycles
        t = progress % 1.0
        x, y = _ball_position(progress, cycles, left_wall, travel)
        image = Image.new("RGB", (width, 32), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        mid = width // 2 - 1
        draw.line((mid, 1, mid, 30), fill=(40, 40, 50))
        for yy in range(3, 30, 6):
            draw.point((mid, yy), fill=(90, 90, 105))
        left_y = _track_paddle(y, t, "left")
        right_y = _track_paddle(y, t, "right")
        draw.rectangle((5, left_y, 7, left_y + 8), fill=(220, 240, 255))
        draw.rectangle((width - 8, right_y, width - 6, right_y + 8), fill=(220, 240, 255))
        draw.rectangle((x, y, x + 2, y + 2), fill=(255, 255, 255))
        draw.text((width // 2 - 14, -4), str(left_score), fill=(90, 200, 255), font=font)
        draw.text((width // 2 + 9, -4), str(right_score), fill=(255, 190, 90), font=font)
        frames.append(image)

    out = BytesIO()
    durations = [frame_duration] * frame_count + [20]
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:],
                   duration=durations, loop=1, lossless=True, quality=100)
    return out.getvalue()
