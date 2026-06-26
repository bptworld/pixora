from io import BytesIO
import urllib.parse

from card_utils import draw_sharp_text, fetch_json_with_headers, render_text_webp

CARD_ID = "lastfm_now_playing"
CARD_NAME = "Last.fm Now Playing"
CARD_DETAIL = "Current or recent track"
CARD_OPTIONS = [
    {"key": "username", "label": "Last.fm Username", "type": "text", "default": "", "maxlength": 40},
    {"key": "apiKey", "label": "Last.fm API Key", "type": "password", "default": ""},
]


def _track(username, api_key):
    qs = urllib.parse.urlencode({
        "method": "user.getrecenttracks",
        "user": username,
        "api_key": api_key,
        "format": "json",
        "limit": "1",
    })
    data = fetch_json_with_headers(f"https://ws.audioscrobbler.com/2.0/?{qs}", seconds=60, cache_key=f"lastfm:{username}")
    tracks = data.get("recenttracks", {}).get("track") or []
    if not tracks:
        return None
    t = tracks[0]
    artist = (t.get("artist") or {}).get("#text") or ""
    title = t.get("name") or ""
    now = (t.get("@attr") or {}).get("nowplaying") == "true"
    return {"artist": artist, "title": title, "now": now}


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    username = (opts.get("username") or "").strip()
    api_key = (opts.get("apiKey") or "").strip()
    if not username or not api_key:
        return render_text_webp("SET FM", (100, 180, 255))
    try:
        track = _track(username, api_key)
    except Exception:
        return render_text_webp("FM ERR", (238, 80, 80))
    if not track:
        return render_text_webp("NO MUSIC", (160, 170, 180))

    image = Image.new("RGB", (64, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()
    if opts.get("_target") == "matrixportal-s3-128x32":
        image = Image.new("RGB", (128, 32), (0, 5, 12))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 127, 6), fill=(30, 5, 10))
        title = "LAST.FM"
        tw = draw.textbbox((0, 0), title, font=bold)[2]
        draw_sharp_text(image, ((128 - tw) // 2, -3), title, (220, 35, 50), bold)
        draw.ellipse((3, 12, 14, 23), outline=(220, 35, 50), width=2)
        draw.polygon([(12, 16), (18, 12), (18, 24)], fill=(220, 35, 50))
        draw_sharp_text(image, (24, 8), (track["title"] or "TRACK")[:20].upper(), (245, 250, 255), font)
        draw_sharp_text(image, (24, 17), (track["artist"] or "ARTIST")[:20].upper(), (150, 170, 185), font)
        state = "LIVE" if track["now"] else "RECENT"
        sw = draw.textbbox((0, 0), state, font=font)[2]
        draw_sharp_text(image, (126 - sw, 22), state, (80, 220, 120) if track["now"] else (145, 165, 182), font)
        out = BytesIO()
        image.save(out, "WEBP", lossless=True, quality=100)
        return out.getvalue()

    draw.rectangle((0, 0, 63, 6), fill=(30, 5, 10))
    draw_sharp_text(image, (1, -3), "LAST.FM", (220, 35, 50), bold)
    draw.ellipse((2, 12, 13, 23), outline=(220, 35, 50), width=2)
    draw.polygon([(12, 16), (18, 12), (18, 24)], fill=(220, 35, 50))
    draw_sharp_text(image, (23, 8), (track["title"] or "TRACK")[:9].upper(), (245, 250, 255), font)
    draw_sharp_text(image, (23, 17), (track["artist"] or "ARTIST")[:9].upper(), (150, 170, 185), font)
    if track["now"]:
        draw_sharp_text(image, (47, 22), "LIVE", (80, 220, 120), font)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

