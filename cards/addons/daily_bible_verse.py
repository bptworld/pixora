from io import BytesIO
import json
import math
import urllib.request

from card_utils import draw_sharp_text, fetch_json_request

CARD_ID = "daily_bible_verse"
CARD_NAME = "Daily Bible Verse"
CARD_CATEGORY = "Utility"
CARD_DETAIL = "Scrolling verse of the day"
CARD_OPTIONS = [
    {"key": "label", "label": "Label", "type": "text", "default": "BIBLE", "maxlength": 12},
    {
        "key": "source",
        "label": "Source",
        "type": "select",
        "default": "bible_org",
        "choices": [
            {"value": "bible_org", "label": "Bible.org"},
            {"value": "the_bible_api", "label": "The Bible API"},
        ],
    },
    {
        "key": "translation",
        "label": "Translation",
        "type": "select",
        "default": "kjv",
        "choices": [
            {"value": "kjv", "label": "KJV"},
            {"value": "web", "label": "WEB"},
        ],
    },
    {"key": "fallbackVerse", "label": "Fallback Verse", "type": "text", "default": "John 3:16 For God so loved the world.", "maxlength": 400},
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

VERSE_OF_DAY_URL = "https://thebibleapi.netlify.app/.netlify/functions/verseOfDay?translation={translation}"
BIBLE_ORG_URL = "https://labs.bible.org/api/?passage=votd&type=json"
_CACHE = {}


def _font(size=8, bold=False):
    from PIL import ImageFont

    names = ["PixelifySans-Bold.ttf", "Silkscreen-Bold.ttf"] if bold else ["Silkscreen-Regular.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _clean_text(value):
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())


def _plain_ascii(value):
    return str(value or "").replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"').replace("\u2013", " - ").replace("\u2014", " - ")


def _clean_verse_text(value):
    text = _clean_text(_plain_ascii(value))
    return text.strip(' "')


def _fetch_bible_org():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    cached = _CACHE.get(BIBLE_ORG_URL)
    if cached and cached["expires"] > now:
        return cached["data"]
    request = urllib.request.Request(BIBLE_ORG_URL, headers={"User-Agent": "Pixora/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))
    _CACHE[BIBLE_ORG_URL] = {"expires": now + timedelta(seconds=21600), "data": data}
    return data


def _daily_verse_bible_org():
    data = _fetch_bible_org()
    if not isinstance(data, list) or not data:
        return ""
    first = data[0]
    last = data[-1]
    book = _clean_text(first.get("bookname"))
    chapter = _clean_text(first.get("chapter"))
    start_verse = _clean_text(first.get("verse"))
    end_verse = _clean_text(last.get("verse"))
    if book and chapter and start_verse and end_verse and end_verse != start_verse:
        reference = f"{book} {chapter}:{start_verse}-{end_verse}"
    elif book and chapter and start_verse:
        reference = f"{book} {chapter}:{start_verse}"
    else:
        reference = ""
    text = _clean_verse_text(" ".join(str(item.get("text") or "") for item in data))
    return f"{reference} {text}".strip() if text else ""


def _daily_verse_the_bible_api(opts):
    translation = str(opts.get("translation") or "kjv").lower()
    if translation not in {"kjv", "web"}:
        translation = "kjv"
    url = VERSE_OF_DAY_URL.format(translation=translation)
    data = fetch_json_request(url, seconds=21600)
    reference = _clean_text(f"{data.get('book', '')} {data.get('chapter', '')}:{data.get('verse', '')}")
    text = _clean_verse_text(data.get("text"))
    if reference and text:
        return f"{reference} {text}"
    if text:
        return text
    return ""


def _daily_verse(opts):
    source = str(opts.get("source") or "bible_org").lower()
    fetchers = [_daily_verse_the_bible_api, lambda _opts: _daily_verse_bible_org()]
    if source != "the_bible_api":
        fetchers.reverse()
    for fetcher in fetchers:
        try:
            verse = _clean_text(fetcher(opts))
            if verse:
                return verse
        except Exception:
            pass
    return _clean_text(_plain_ascii(opts.get("fallbackVerse"))) or "John 3:16 For God so loved the world."


def _scroll_timing(speed):
    if speed == "slow":
        return 1, 38
    if speed == "fast":
        return 2, 35
    return 1, 26


def _render_scroll(label, verse, width=64, speed="normal"):
    from PIL import Image, ImageDraw

    label_font = _font(8, bold=True)
    text_font = _font(8)
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    text = verse.upper()
    text_w = dummy.textbbox((0, 0), text, font=text_font)[2]
    px_per_frame, frame_ms = _scroll_timing(speed)
    total = width + text_w + 24
    strip_width = total + width

    base = Image.new("RGB", (width, 32), (0, 4, 10))
    base_draw = ImageDraw.Draw(base)
    base_draw.rectangle((0, 0, width - 1, 8), fill=(9, 20, 25))
    label_text = label[:22 if width == 128 else 10].upper()
    draw_sharp_text(base, (1, -3), label_text, (112, 232, 190), label_font)

    strip = Image.new("RGB", (strip_width, 24), (0, 4, 10))
    draw_sharp_text(strip, (width, 14), text, (245, 250, 255), text_font)

    frames = []
    for step in range(0, total, px_per_frame):
        frame = base.copy()
        frame.paste(strip.crop((step, 8, step + width, 32)), (0, 8))
        frames.append(frame)

    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=frame_ms,
        loop=1,
        lossless=True,
        quality=100,
    )
    animation_secs = math.ceil((len(frames) * frame_ms) / 1000)
    return out.getvalue(), max(4, animation_secs + 1)


def render(options=None):
    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    label = _clean_text(opts.get("label") or "BIBLE") or "BIBLE"
    verse = _daily_verse(opts)
    speed = str(opts.get("speed") or "normal").lower()
    if speed not in {"slow", "normal", "fast"}:
        speed = "normal"
    body, dwell_secs = _render_scroll(label, verse, width=width, speed=speed)
    return {"body": body, "dwell_secs": dwell_secs, "_stay": False}
