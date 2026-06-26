from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import urllib.request

from card_utils import draw_sharp_text, render_text_webp

CARD_ID = "music_assistant_now_playing"
CARD_NAME = "Music Assistant Now Playing"
CARD_DETAIL = "Direct Music Assistant player"
CARD_OPTIONS = [
    {"key": "serverUrl", "label": "Music Assistant URL", "type": "text", "default": "http://musicassistant.local:8095", "maxlength": 100},
    {"key": "playerId", "label": "Player ID", "type": "text", "default": "", "maxlength": 80},
    {"key": "token", "label": "API Token (optional)", "type": "password", "default": ""},
    {"key": "skipWhenIdle", "label": "Skip when not playing", "type": "checkbox", "default": True},
]

_CACHE = {}


def _api(server_url, command, args=None, token=""):
    server = (server_url or "").strip().rstrip("/")
    if not server:
        raise ValueError("server required")
    if not server.startswith(("http://", "https://")):
        server = "http://" + server
    body = json.dumps({"command": command, "args": args or {}}).encode("utf-8")
    headers = {"User-Agent": "Pixora/0.1", "Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(server + "/api", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("result", data)


def _queues(server_url, token):
    key = server_url.rstrip("/") + "|" + bool(token)
    now = datetime.now(timezone.utc)
    cached = _CACHE.get(key)
    if cached and cached["expires"] > now:
        return cached["data"]
    data = _api(server_url, "player_queues/all", token=token)
    _CACHE[key] = {"data": data or [], "expires": now + timedelta(seconds=20)}
    return data or []


def _is_playing(queue):
    state = str(queue.get("state") or queue.get("status") or "").lower()
    return state == "playing" or queue.get("active") is True


def _pick_queue(queues, player_id):
    player_id = (player_id or "").strip()
    if player_id:
        for queue in queues:
            ids = [
                str(queue.get("queue_id") or ""),
                str(queue.get("player_id") or ""),
                str(queue.get("id") or ""),
            ]
            if player_id in ids:
                return queue
    for queue in queues:
        if _is_playing(queue):
            return queue
    return queues[0] if queues else None


def _text(value):
    if isinstance(value, dict):
        return value.get("name") or value.get("sort_name") or value.get("display_name") or ""
    return str(value or "")


def _artist(item):
    artists = item.get("artists") or item.get("artist") or []
    if isinstance(artists, list):
        names = [_text(a) for a in artists if _text(a)]
        return ", ".join(names)
    return _text(artists)


def _now_playing(queue):
    item = queue.get("current_item") or queue.get("current_media") or queue.get("media_item") or {}
    if isinstance(item, dict) and "media_item" in item:
        item = item.get("media_item") or item
    title = item.get("name") or item.get("title") or queue.get("current_item_name") or "Unknown"
    artist = _artist(item) or item.get("artist_name") or ""
    mappings = item.get("provider_mappings")
    if not artist and isinstance(mappings, list) and mappings:
        artist = mappings[0].get("artist") or ""
    album = _text(item.get("album"))
    player = queue.get("display_name") or queue.get("name") or queue.get("queue_id") or "Music"
    return {"title": _text(title), "artist": _text(artist), "album": album, "player": _text(player), "playing": _is_playing(queue)}


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    server_url = (opts.get("serverUrl") or "").strip()
    player_id = (opts.get("playerId") or "").strip()
    token = (opts.get("token") or "").strip()
    skip_idle = opts.get("skipWhenIdle") is True or str(opts.get("skipWhenIdle")).lower() == "true"
    if not server_url:
        return render_text_webp("SET MA", (100, 180, 255))

    try:
        queue = _pick_queue(_queues(server_url, token), player_id)
    except Exception:
        return render_text_webp("MA ERR", (238, 80, 80))
    if not queue:
        return render_text_webp("NO PLAYER", (160, 170, 180))

    info = _now_playing(queue)
    if skip_idle and not info["playing"]:
        return None

    image = Image.new("RGB", (64, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    color = (80, 220, 170) if info["playing"] else (160, 170, 185)
    if opts.get("_target") == "matrixportal-s3-128x32":
        image = Image.new("RGB", (128, 32), (0, 5, 12))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 127, 6), fill=(5, 18, 25))
        title = "MUSIC ASST"
        tw = draw.textbbox((0, 0), title, font=bold)[2]
        draw_sharp_text(image, ((128 - tw) // 2, -3), title, color, bold)
        draw.ellipse((4, 12, 15, 23), outline=color, width=2)
        draw.rectangle((14, 9, 17, 19), fill=color)
        draw.line((17, 9, 21, 11), fill=color, width=2)
        draw_sharp_text(image, (26, 8), (info["title"] or "TRACK")[:20].upper(), (245, 250, 255), font)
        draw_sharp_text(image, (26, 17), (info["artist"] or info["player"] or "PLAYER")[:20].upper(), (150, 170, 185), font)
        state = "PLAY" if info["playing"] else "IDLE"
        sw = draw.textbbox((0, 0), state, font=font)[2]
        draw_sharp_text(image, (126 - sw, 22), state, color, font)
        out = BytesIO()
        image.save(out, "WEBP", lossless=True, quality=100)
        return out.getvalue()

    draw.rectangle((0, 0, 63, 6), fill=(5, 18, 25))
    draw_sharp_text(image, (1, -3), "MUSIC ASST", color, bold)
    draw.ellipse((3, 12, 14, 23), outline=color, width=2)
    draw.rectangle((13, 9, 16, 19), fill=color)
    draw.line((16, 9, 20, 11), fill=color, width=2)
    draw_sharp_text(image, (24, 8), (info["title"] or "TRACK")[:9].upper(), (245, 250, 255), font)
    draw_sharp_text(image, (24, 17), (info["artist"] or info["player"] or "PLAYER")[:9].upper(), (150, 170, 185), font)
    state = "PLAY" if info["playing"] else "IDLE"
    sw = draw.textbbox((0, 0), state, font=font)[2]
    draw_sharp_text(image, (63 - sw, 22), state, color, font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

