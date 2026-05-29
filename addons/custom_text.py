from io import BytesIO

from card_utils import draw_sharp_text

CARD_ID = "custom_text"
CARD_NAME = "Custom Text"
CARD_DETAIL = "Two-line custom message"
CARD_OPTIONS = [
    {"key": "topLine", "label": "Top Line", "type": "text", "default": "Welcome to", "maxlength": 40},
    {"key": "bottomLine", "label": "Bottom Line", "type": "text", "default": "Bryan's Man Cave", "maxlength": 60},
    {
        "key": "theme",
        "label": "Theme",
        "type": "select",
        "default": "cyan",
        "choices": [
            {"value": "cyan", "label": "Cyan"},
            {"value": "sunset", "label": "Sunset"},
            {"value": "lime", "label": "Lime"},
            {"value": "pink", "label": "Pink"},
            {"value": "mono", "label": "Mono"},
        ],
    },
    {
        "key": "layout",
        "label": "Layout",
        "type": "select",
        "default": "title",
        "choices": [
            {"value": "title", "label": "Title + Big"},
            {"value": "balanced", "label": "Balanced"},
            {"value": "big", "label": "Big Message"},
            {"value": "stacked", "label": "Stacked"},
        ],
    },
    {
        "key": "align",
        "label": "Align",
        "type": "select",
        "default": "center",
        "choices": [
            {"value": "left", "label": "Left"},
            {"value": "center", "label": "Center"},
            {"value": "right", "label": "Right"},
        ],
    },
    {
        "key": "border",
        "label": "Border",
        "type": "select",
        "default": "none",
        "choices": [
            {"value": "none", "label": "None"},
            {"value": "line", "label": "Line"},
            {"value": "glow", "label": "Glow"},
            {"value": "dots", "label": "Dots"},
        ],
    },
]


THEMES = {
    "cyan": {
        "bg": (0, 0, 0),
        "top": (70, 230, 255),
        "bottom": (255, 255, 255),
        "accent": (35, 120, 155),
    },
    "sunset": {
        "bg": (8, 2, 6),
        "top": (255, 184, 70),
        "bottom": (255, 92, 132),
        "accent": (100, 35, 58),
    },
    "lime": {
        "bg": (0, 6, 2),
        "top": (122, 255, 90),
        "bottom": (235, 255, 210),
        "accent": (42, 130, 42),
    },
    "pink": {
        "bg": (8, 0, 9),
        "top": (255, 116, 220),
        "bottom": (255, 238, 250),
        "accent": (125, 42, 115),
    },
    "mono": {
        "bg": (0, 0, 0),
        "top": (185, 195, 205),
        "bottom": (245, 250, 255),
        "accent": (70, 78, 88),
    },
}


def _font(size, bold=False):
    from PIL import ImageFont

    names = ["Silkscreen-Bold.ttf", "Silkscreen-Regular.ttf"] if bold else ["Silkscreen-Regular.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _fit_font(draw, text, max_width, start_size, min_size, bold=False):
    text = str(text or "").strip()
    for size in range(start_size, min_size - 1, -1):
        font = _font(size, bold=bold)
        if _text_width(draw, text, font) <= max_width:
            return font
    return _font(min_size, bold=bold)


def _wrap_words(draw, text, font, max_width, max_lines=2):
    words = str(text or "").strip().split()
    if not words:
        return [""]
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip() if current else word
        if _text_width(draw, test, font) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) <= max_lines:
        return lines
    kept = lines[:max_lines]
    while kept[-1] and _text_width(draw, kept[-1] + "...", font) > max_width:
        kept[-1] = kept[-1][:-1].rstrip()
    kept[-1] = (kept[-1] + "...").strip()
    return kept


def _theme(name):
    return THEMES.get(str(name or "cyan").strip().lower(), THEMES["cyan"])


def _x_for(draw, text, font, width, align, margin=2):
    text_w = _text_width(draw, text, font)
    if align == "left":
        return margin
    if align == "right":
        return width - text_w - margin
    return (width - text_w) // 2


def _draw_border(draw, width, style, color):
    style = str(style or "none").lower()
    if style == "line":
        draw.rectangle((0, 0, width - 1, 31), outline=color)
    elif style == "glow":
        draw.rectangle((0, 0, width - 1, 31), outline=tuple(max(0, c // 2) for c in color))
        draw.line((1, 1, width - 2, 1), fill=color)
        draw.line((1, 30, width - 2, 30), fill=tuple(max(0, c // 3) for c in color))
    elif style == "dots":
        for x in range(1, width, 6):
            draw.point((x, 1), fill=color)
            draw.point((width - 1 - x, 30), fill=color)


def _draw_lines(image, draw, lines, font, y, color, width, align, step=9):
    for line in lines:
        x = _x_for(draw, line, font, width, align)
        draw_sharp_text(image, (x, y), line, color, font)
        y += step


def render(options=None):
    from PIL import Image, ImageDraw

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    top = str(opts.get("topLine") or "Welcome to").strip()
    bottom = str(opts.get("bottomLine") or "Bryan's Man Cave").strip()
    theme = _theme(opts.get("theme"))
    layout = str(opts.get("layout") or "title").lower()
    align = str(opts.get("align") or "center").lower()

    if align not in {"left", "center", "right"}:
        align = "center"

    image = Image.new("RGB", (width, 32), theme["bg"])
    draw = ImageDraw.Draw(image)
    _draw_border(draw, width, opts.get("border"), theme["accent"])

    if layout == "big":
        text = bottom or top
        big_font = _fit_font(draw, text, width - 4, 15 if width == 128 else 12, 8, bold=True)
        if _text_width(draw, text, big_font) <= width - 4:
            y = 8 if width == 64 else 7
            draw_sharp_text(image, (_x_for(draw, text, big_font, width, align), y), text, theme["bottom"], big_font)
        else:
            wrap_font = _font(8, bold=True)
            lines = _wrap_words(draw, text, wrap_font, width - 4, max_lines=3)
            y = max(0, (32 - len(lines) * 9) // 2 - 2)
            _draw_lines(image, draw, lines, wrap_font, y, theme["bottom"], width, align)
    elif layout == "balanced":
        top_font = _fit_font(draw, top, width - 4, 10 if width == 128 else 8, 6, bold=True)
        bottom_font = _fit_font(draw, bottom, width - 4, 10 if width == 128 else 8, 6, bold=True)
        draw_sharp_text(image, (_x_for(draw, top, top_font, width, align), 4), top, theme["top"], top_font)
        if _text_width(draw, bottom, bottom_font) <= width - 4:
            draw_sharp_text(image, (_x_for(draw, bottom, bottom_font, width, align), 18), bottom, theme["bottom"], bottom_font)
        else:
            lines = _wrap_words(draw, bottom, _font(8, bold=False), width - 4, max_lines=2)
            _draw_lines(image, draw, lines, _font(8, bold=False), 15, theme["bottom"], width, align)
    elif layout == "stacked":
        font = _font(8, bold=True)
        lines = _wrap_words(draw, f"{top} {bottom}".strip(), font, width - 4, max_lines=3)
        y = max(0, (32 - len(lines) * 9) // 2 - 2)
        _draw_lines(image, draw, lines, font, y, theme["bottom"], width, align)
    else:
        top_font = _fit_font(draw, top, width - 4, 8 if width == 128 else 7, 6, bold=False)
        bottom_font = _fit_font(draw, bottom, width - 4, 14 if width == 128 else 11, 8, bold=True)
        draw_sharp_text(image, (_x_for(draw, top, top_font, width, align), 1), top, theme["top"], top_font)
        if _text_width(draw, bottom, bottom_font) <= width - 4:
            draw_sharp_text(image, (_x_for(draw, bottom, bottom_font, width, align), 14), bottom, theme["bottom"], bottom_font)
        else:
            wrap_font = _font(8, bold=True)
            lines = _wrap_words(draw, bottom, wrap_font, width - 4, max_lines=2)
            _draw_lines(image, draw, lines, wrap_font, 13, theme["bottom"], width, align)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
