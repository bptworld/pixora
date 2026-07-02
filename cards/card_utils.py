from io import BytesIO
import base64
import json
import math
import os
import sys
from pathlib import Path
import re
import urllib.request
import urllib.parse
import ipaddress
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

WEATHER_CACHE = {}
OPENWEATHER_ICON_CACHE = {}
LOGO_CACHE = {}
PRIORITY_GRAPHIC_CACHE = {}
PUBLIC_JSON_CACHE = {}
PUBLIC_IMAGE_CACHE = {}
PRIORITY_GRAPHIC_CACHE_TTL_SECS = 900
WEATHER_CACHE_MAX_ENTRIES = 128
ICON_CACHE_MAX_ENTRIES = 64
LOGO_CACHE_MAX_ENTRIES = 128
AIRLINE_LOGO_CACHE_MAX_ENTRIES = 64
PUBLIC_JSON_CACHE_MAX_ENTRIES = 128
PUBLIC_IMAGE_CACHE_MAX_ENTRIES = 96
PUBLIC_MAX_JSON_BYTES = 512 * 1024
PUBLIC_MAX_IMAGE_BYTES = 768 * 1024

_BOLD_NUMERIC_RE = re.compile(r"^[\d\s:.,+\-/$%]+$")
_PIXORA_BOLD_DIGITS = {
    "0": ("01110", "11011", "11011", "11011", "11011", "11011", "01110"),
    "1": ("01110", "11110", "00110", "00110", "00110", "00110", "11111"),
    "2": ("11110", "00011", "00011", "11110", "11000", "11000", "11111"),
    "3": ("11110", "00011", "00011", "01110", "00011", "00011", "11110"),
    "4": ("11011", "11011", "11011", "11111", "00011", "00011", "00011"),
    "5": ("11111", "11000", "11000", "11110", "00011", "00011", "11110"),
    "6": ("01111", "11000", "11000", "11110", "11011", "11011", "01110"),
    "7": ("11111", "00011", "00110", "00110", "01100", "01100", "01100"),
    "8": ("01110", "11011", "11011", "01110", "11011", "11011", "01110"),
    "9": ("01110", "11011", "11011", "01111", "00011", "11011", "01110"),
}
_PIXORA_BOLD_SYMBOLS = {
    ":": ("0", "0", "1", "0", "0", "1", "0"),
    ".": ("0", "0", "0", "0", "0", "0", "1"),
    ",": ("0", "0", "0", "0", "0", "1", "1"),
    "-": ("000", "000", "000", "111", "000", "000", "000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "/": ("0001", "0001", "0010", "0010", "0100", "0100", "1000"),
    "$": ("01110", "11000", "11000", "01110", "00011", "00011", "11110"),
    "%": ("10001", "00010", "00100", "00100", "01000", "10000", "10001"),
}
_NUMERIC_SEGMENTS = {
    "0": "abcfed",
    "1": "bc",
    "2": "abged",
    "3": "abgcd",
    "4": "fgbc",
    "5": "afgcd",
    "6": "afgecd",
    "7": "abc",
    "8": "abcdefg",
    "9": "abfgcd",
}
_PIXORA_BOLD_NUMERIC_CHARS = set(_PIXORA_BOLD_DIGITS) | set(_PIXORA_BOLD_SYMBOLS) | {" "}
_RUNTIME_SETTINGS_STACK = []


def _is_bold_font(font):
    try:
        return "bold" in " ".join(str(part) for part in font.getname()).lower()
    except Exception:
        return False


def pixora_bold_number_size(text, scale=1, spacing=1):
    text = str(text or "")
    width = 0
    for idx, ch in enumerate(text):
        glyph = _PIXORA_BOLD_DIGITS.get(ch) or _PIXORA_BOLD_SYMBOLS.get(ch)
        if glyph:
            width += len(glyph[0]) * scale
        elif ch == " ":
            width += 3 * scale
        else:
            width += 4 * scale
        if idx < len(text) - 1:
            width += spacing
    return max(0, width), 7 * scale


def draw_pixora_bold_number(draw, xy, text, color, scale=1, spacing=1):
    text = str(text or "")
    x, y = xy
    for ch in text:
        glyph = _PIXORA_BOLD_DIGITS.get(ch) or _PIXORA_BOLD_SYMBOLS.get(ch)
        if glyph:
            for gy, row in enumerate(glyph):
                for gx, pixel in enumerate(row):
                    if pixel == "1":
                        draw.rectangle(
                            (
                                x + gx * scale,
                                y + gy * scale,
                                x + (gx + 1) * scale - 1,
                                y + (gy + 1) * scale - 1,
                            ),
                            fill=color,
                        )
            x += len(glyph[0]) * scale + spacing
        elif ch == " ":
            x += 3 * scale + spacing
        else:
            x += 4 * scale + spacing


def _bold_mixed_number_parts(text):
    text = str(text or "")
    parts = []
    idx = 0
    while idx < len(text):
        ch = text[idx]
        is_numeric = ch in _PIXORA_BOLD_NUMERIC_CHARS
        start = idx
        idx += 1
        while idx < len(text) and ((text[idx] in _PIXORA_BOLD_NUMERIC_CHARS) == is_numeric):
            idx += 1
        value = text[start:idx]
        parts.append((is_numeric and any(c.isdigit() for c in value), value))
    return parts


def pixora_mixed_bold_number_size(text, font, scale=1, spacing=1):
    parts = _bold_mixed_number_parts(text)
    if not parts:
        return 0, 0
    width = 0
    height = 0
    for is_numeric, value in parts:
        if is_numeric:
            part_w, part_h = pixora_bold_number_size(value, scale=scale, spacing=spacing)
        else:
            try:
                bbox = font.getbbox(value)
                part_w = max(0, bbox[2] - bbox[0])
                part_h = max(0, bbox[3] - bbox[1])
            except Exception:
                part_w = len(value) * 4 * scale
                part_h = 7 * scale
        width += part_w
        height = max(height, part_h)
    return width, height


def use_runtime_settings(settings):
    token = len(_RUNTIME_SETTINGS_STACK)
    _RUNTIME_SETTINGS_STACK.append(dict(settings or {}))
    return token


def reset_runtime_settings(token=None):
    if token is None:
        _RUNTIME_SETTINGS_STACK.clear()
        return
    try:
        del _RUNTIME_SETTINGS_STACK[int(token):]
    except Exception:
        _RUNTIME_SETTINGS_STACK.clear()


def _settings_value(key, default=""):
    if _RUNTIME_SETTINGS_STACK:
        value = _RUNTIME_SETTINGS_STACK[-1].get(key)
        if value not in (None, ""):
            return value
    env_key = "PIXORA_" + re.sub(r"[^A-Z0-9]+", "_", key.upper())
    if os.environ.get(env_key):
        return os.environ.get(env_key)
    try:
        data_dir = os.environ.get("PIXORA_DATA_DIR")
        if data_dir:
            settings_path = Path(data_dir) / "settings.json"
        else:
            root = Path(__file__).resolve().parent
            settings_path = root.parent / "data" / "settings.json"
        if settings_path.exists():
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            return settings.get(key, default)
    except Exception:
        pass
    return default


def _timezone_name_for_lat_lon(lat, lon):
    try:
        lat = float(lat)
        lon = float(lon)
    except Exception:
        return ""
    if 18 <= lat <= 23 and -161 <= lon <= -154:
        return "Pacific/Honolulu"
    if lat >= 50 and lon <= -130:
        return "America/Anchorage"
    if lon <= -114:
        return "America/Los_Angeles"
    if lon <= -101:
        return "America/Denver"
    if lon <= -86:
        return "America/Chicago"
    return "America/New_York"


def _configured_timezone_name():
    tz_name = str(_settings_value("defaultTimezone", "") or _settings_value("defaultTimeZone", "") or "").strip()
    if tz_name:
        return tz_name
    lat = _settings_value("defaultLatitude", "")
    lon = _settings_value("defaultLongitude", "")
    tz_name = _timezone_name_for_lat_lon(lat, lon)
    if tz_name:
        return tz_name
    zip_code = re.sub(r"\D", "", str(_settings_value("defaultZipCode", "") or ""))[:5]
    if len(zip_code) == 5:
        try:
            location = fetch_json_request(f"https://api.zippopotam.us/us/{zip_code}", seconds=86400)
            place = location["places"][0]
            tz_name = _timezone_name_for_lat_lon(place["latitude"], place["longitude"])
            if tz_name:
                return tz_name
        except Exception:
            pass
    return str(os.environ.get("TZ") or "").strip()


def pixora_local_now():
    tz_name = _configured_timezone_name()
    if tz_name:
        try:
            return datetime.now(ZoneInfo(tz_name))
        except Exception:
            pass
    return datetime.now().astimezone()


def pixora_local_timezone():
    return pixora_local_now().tzinfo


def _priority_graphic_prune(now):
    for key, item in list(PRIORITY_GRAPHIC_CACHE.items()):
        if (now - item.get("seen", now)).total_seconds() > PRIORITY_GRAPHIC_CACHE_TTL_SECS:
            PRIORITY_GRAPHIC_CACHE.pop(key, None)


def _prune_expiring_cache(cache, now, max_entries):
    for key, item in list(cache.items()):
        if isinstance(item, dict) and item.get("expires", now) <= now:
            cache.pop(key, None)
    while len(cache) > max_entries:
        cache.pop(next(iter(cache)), None)


def _cache_get(cache, key):
    if key not in cache:
        return None
    value = cache.pop(key)
    cache[key] = value
    return value


def _cache_put(cache, key, value, max_entries):
    if key in cache:
        cache.pop(key, None)
    cache[key] = value
    while len(cache) > max_entries:
        cache.pop(next(iter(cache)), None)


def priority_graphic_key(card_id, team=None, kind="", width=64):
    team = team or {}
    parts = [
        str(card_id or ""),
        str(kind or ""),
        str(width or ""),
        str(team.get("abbreviation") or team.get("shortDisplayName") or team.get("displayName") or ""),
        str(team.get("logo") or ""),
        str(team.get("color") or ""),
        str(team.get("alternateColor") or ""),
        str(team.get("playerName") or ""),
        str(team.get("playerHeadshot") or ""),
        str(team.get("playerFlag") or ""),
        str(team.get("playerLogo") or ""),
    ]
    return "|".join(parts)


def cached_priority_graphic(cache_key, render):
    now = datetime.now(timezone.utc)
    _priority_graphic_prune(now)
    cached = PRIORITY_GRAPHIC_CACHE.get(cache_key)
    if cached and cached.get("body"):
        cached["seen"] = now
        return cached["body"]
    body = render()
    if body:
        PRIORITY_GRAPHIC_CACHE[cache_key] = {"body": body, "seen": now}
    return body


def warm_priority_graphic(cache_key, render):
    if cache_key not in PRIORITY_GRAPHIC_CACHE:
        cached_priority_graphic(cache_key, render)


def pixora_log(options, message):
    logger = (options or {}).get("_log") if isinstance(options, dict) else None
    if callable(logger):
        try:
            logger(str(message or ""))
        except Exception:
            pass


def card_context(options=None):
    options = options if isinstance(options, dict) else {}
    width = int(options.get("_width") or (128 if options.get("_target") == "matrixportal-s3-128x32" else 64))
    width = 128 if width > 96 else 64
    settings = options.get("_settings") if isinstance(options.get("_settings"), dict) else {}
    return {
        "options": options,
        "settings": settings,
        "width": width,
        "height": 32,
        "target": str(options.get("_target") or ("matrixportal-s3-128x32" if width > 96 else "matrixportal-s3")),
        "device_id": str(options.get("_device_id") or ""),
        "firmware_version": str(options.get("_firmware_version") or ""),
        "dwell_secs": max(1, int(options.get("_dwell") or 10)),
        "timezone": pixora_local_timezone(),
        "now": pixora_local_now(),
        "is_prefetch": bool(options.get("_is_prefetch")),
        "refresh_policy": str(options.get("_refresh_policy") or "balanced"),
        "log": lambda message: pixora_log(options, message),
    }


def _caller_allowed_domains():
    domains = []
    try:
        frame = sys._getframe(2)
        while frame:
            globals_dict = frame.f_globals if isinstance(frame.f_globals, dict) else {}
            for name in ("CARD_ALLOWED_DOMAINS", "ALLOWED_DOMAINS"):
                value = globals_dict.get(name)
                if isinstance(value, (list, tuple)):
                    domains.extend(str(item or "").strip() for item in value)
            if domains:
                break
            frame = frame.f_back
    except Exception:
        pass
    return [item for item in domains if item]


def _safe_public_url(url, allowed_domains=None):
    parsed = urllib.parse.urlparse(str(url or "").strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs are allowed.")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("URL host is required.")
    if host in ("localhost", "localhost.localdomain") or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("Localhost URLs are not allowed.")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise ValueError("Private network URLs are not allowed.")
    except ValueError as exc:
        if "URLs are not allowed" in str(exc):
            raise
    if allowed_domains is None:
        allowed_domains = _caller_allowed_domains()
    domains = [str(item or "").strip().lower() for item in (allowed_domains or []) if str(item or "").strip()]
    if domains and not any(host == domain or host.endswith("." + domain) for domain in domains):
        raise ValueError("URL host is not in the allowed domain list.")
    return parsed.geturl()


def _read_limited_response(response, max_bytes):
    max_bytes = max(1024, min(int(max_bytes or PUBLIC_MAX_JSON_BYTES), 2 * 1024 * 1024))
    data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("Response is too large.")
    return data


def cached_json(url, ttl_secs=300, headers=None, cache_key=None, max_bytes=PUBLIC_MAX_JSON_BYTES, allowed_domains=None):
    url = _safe_public_url(url, allowed_domains=allowed_domains)
    ttl_secs = max(15, min(int(ttl_secs or 300), 86400))
    max_bytes = max(1024, min(int(max_bytes or PUBLIC_MAX_JSON_BYTES), PUBLIC_MAX_JSON_BYTES))
    request_headers = {"User-Agent": "Pixora/0.1", "Accept": "application/json"}
    for key, value in (headers or {}).items():
        key = str(key or "").strip()
        if re.fullmatch(r"[A-Za-z0-9-]+", key):
            request_headers[key] = str(value or "")[:500]
    key = cache_key or url + "|" + json.dumps(request_headers, sort_keys=True)
    now = datetime.now(timezone.utc)
    _prune_expiring_cache(PUBLIC_JSON_CACHE, now, PUBLIC_JSON_CACHE_MAX_ENTRIES)
    cached = PUBLIC_JSON_CACHE.get(key)
    if cached and cached.get("expires", now) > now:
        return cached["data"]
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            body = _read_limited_response(response, max_bytes)
        data = json.loads(body.decode("utf-8"))
    except Exception:
        if cached and "data" in cached:
            return cached["data"]
        raise
    _cache_put(PUBLIC_JSON_CACHE, key, {"expires": now + timedelta(seconds=ttl_secs), "data": data}, PUBLIC_JSON_CACHE_MAX_ENTRIES)
    return data


def fetch_image_asset(url, size=16, ttl_secs=3600, max_bytes=PUBLIC_MAX_IMAGE_BYTES, allowed_domains=None):
    if not str(url or "").strip():
        return None
    url = _safe_public_url(url, allowed_domains=allowed_domains)
    size = max(1, min(int(size or 16), 64))
    ttl_secs = max(60, min(int(ttl_secs or 3600), 86400))
    max_bytes = max(1024, min(int(max_bytes or PUBLIC_MAX_IMAGE_BYTES), PUBLIC_MAX_IMAGE_BYTES))
    cache_key = (url, size)
    now = datetime.now(timezone.utc)
    _prune_expiring_cache(PUBLIC_IMAGE_CACHE, now, PUBLIC_IMAGE_CACHE_MAX_ENTRIES)
    cached = PUBLIC_IMAGE_CACHE.get(cache_key)
    if cached and cached.get("expires", now) > now:
        return cached["image"]
    try:
        from PIL import Image
        request = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1", "Accept": "image/png,image/jpeg,image/webp,image/*"})
        with urllib.request.urlopen(request, timeout=5) as response:
            data = _read_limited_response(response, max_bytes)
        image = Image.open(BytesIO(data)).convert("RGBA")
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.alpha_composite(image, ((size - image.width) // 2, (size - image.height) // 2))
        r, g, b, a = canvas.split()
        a = a.point(lambda p: 255 if p > 42 else 0)
        result = Image.merge("RGBA", (r, g, b, a))
    except Exception:
        if cached and "image" in cached:
            return cached["image"]
        return None
    _cache_put(PUBLIC_IMAGE_CACHE, cache_key, {"expires": now + timedelta(seconds=ttl_secs), "image": result}, PUBLIC_IMAGE_CACHE_MAX_ENTRIES)
    return result


def paste_image_asset(canvas, url, xy, size=16, ttl_secs=3600, allowed_domains=None):
    image = fetch_image_asset(url, size=size, ttl_secs=ttl_secs, allowed_domains=allowed_domains)
    if image is None:
        return False
    canvas.paste(image, (int(xy[0]), int(xy[1])), image)
    return True


def color_to_hex(color):
    r, g, b = parse_color(color)
    return f"{r:02X}{g:02X}{b:02X}"


def dim_color(color, factor=0.55):
    factor = max(0.0, min(float(factor or 0), 1.0))
    r, g, b = parse_color(color)
    return int(r * factor), int(g * factor), int(b * factor)


def contrast_text_color(background, light=(255, 255, 255), dark=(0, 0, 0)):
    r, g, b = parse_color(background)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b)
    return dark if luminance > 150 else light


def option_zip(key="zipCode", label="ZIP", default="", required=False):
    return {"key": key, "label": label, "type": "text", "default": default, "maxlength": 5, "inputmode": "numeric", "required": bool(required)}


def option_target(key, label, default="device", include_wall=True):
    choices = [{"value": "device", "label": "Device"}]
    if include_wall:
        choices.append({"value": "group_wall", "label": "Group Wall"})
    choices.append({"value": "off", "label": "Off"})
    return {"key": key, "label": label, "type": "select", "default": default, "choices": choices}


def option_select(key, label, choices, default=""):
    return {"key": key, "label": label, "type": "select", "default": default, "choices": choices or []}


def option_text(key, label, default="", maxlength=120):
    return {"key": key, "label": label, "type": "text", "default": default, "maxlength": max(1, min(int(maxlength or 120), 500))}


def option_number(key, label, default=1, min_value=0, max_value=999):
    return {"key": key, "label": label, "type": "number", "default": default, "min": min_value, "max": max_value}


def option_checkbox(key, label, default=False):
    return {"key": key, "label": label, "type": "checkbox", "default": bool(default)}


def _state_root():
    root = os.environ.get("PIXORA_CARD_STATE_DIR") or os.environ.get("PIXORA_DATA_DIR")
    if root:
        path = Path(root)
        if path.name != "card-state":
            path = path / "card-state"
    else:
        path = Path(__file__).resolve().parent.parent / "data" / "card-state"
    path.mkdir(parents=True, exist_ok=True)
    return path


class CardState:
    def __init__(self, card_id):
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", str(card_id or "card")).strip("_") or "card"
        self.path = _state_root() / f"{safe[:80]}.json"
        self.data = {}
        try:
            if self.path.exists():
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data = loaded
        except Exception:
            self.data = {}

    def get(self, key, default=None):
        return self.data.get(str(key), default)

    def set(self, key, value):
        self.data[str(key)] = _json_safe_payload(value)
        self.save()
        return self.data[str(key)]

    def update(self, values):
        if isinstance(values, dict):
            for key, value in values.items():
                self.data[str(key)] = _json_safe_payload(value)
            self.save()
        return dict(self.data)

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)


def card_state(card_id):
    return CardState(card_id)


def card_asset_path(card_id, filename):
    safe_card = re.sub(r"[^A-Za-z0-9_-]+", "_", str(card_id or "card")).strip("_") or "card"
    safe_name = str(filename or "").replace("\\", "/").strip("/")
    if not safe_name or ".." in safe_name or safe_name.startswith("/"):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_./ -]+", safe_name):
        return None
    root = Path(os.environ.get("PIXORA_CARD_ASSET_DIR") or (Path(__file__).resolve().parent / "assets"))
    base = (root / safe_card).resolve()
    path = (base / safe_name).resolve()
    try:
        path.relative_to(base)
    except Exception:
        return None
    return path if path.exists() and path.is_file() and path.stat().st_size <= 768 * 1024 else None


def load_card_asset_image(card_id, filename, size=None):
    path = card_asset_path(card_id, filename)
    if path is None:
        return None
    try:
        from PIL import Image
        image = Image.open(path).convert("RGBA")
        if size:
            size = max(1, min(int(size), 64))
            image.thumbnail((size, size), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            canvas.alpha_composite(image, ((size - image.width) // 2, (size - image.height) // 2))
            image = canvas
        return image
    except Exception:
        return None


def _json_safe_payload(value, depth=0):
    if depth > 4:
        return str(value)[:200]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe_payload(item, depth + 1) for item in value[:24]]
    if isinstance(value, dict):
        clean = {}
        for key, item in list(value.items())[:48]:
            clean[str(key)[:80]] = _json_safe_payload(item, depth + 1)
        return clean
    return str(value)[:200]


def special_graphic(renderer, kind="graphic", team=None, dwell_secs=6, wall_renderer=None, include_device=True, include_wall=False, group=None, stay=False, card=None):
    renderer = str(renderer or "").strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", renderer):
        raise ValueError("Renderer must be a function name in this card file.")
    kind = str(kind or "graphic").strip()[:80] or "graphic"
    dwell_secs = max(1, min(int(dwell_secs or 6), 60))
    payload = _json_safe_payload(team or {})
    result = {}
    if include_device:
        spec = {"renderer": renderer, "kind": kind, "team": payload, "dwell_secs": dwell_secs}
        if stay:
            spec["stay"] = True
        if card:
            spec["card"] = str(card)[:120]
        result["deviceGraphic"] = spec
    if include_wall:
        wall_name = str(wall_renderer or renderer).strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", wall_name):
            raise ValueError("Wall renderer must be a function name in this card file.")
        spec = {"renderer": wall_name, "kind": kind, "team": payload, "dwell_secs": dwell_secs}
        if group:
            spec["groupId"] = str(group)[:120]
        if card:
            spec["card"] = str(card)[:120]
        result["wallGraphic"] = spec
    return result


def bitmap_number_size(text, scale=1, spacing=1):
    return pixora_bold_number_size(text, scale=scale, spacing=spacing)


def draw_bitmap_number(draw, xy, text, color, scale=1, spacing=1, thickness=None):
    draw_pixora_bold_number(draw, xy, text, color, scale=scale, spacing=spacing)


def _draw_bitmap_number_base(text, color, thickness=None):
    from PIL import Image, ImageDraw
    text = str(text or "")
    width, height = bitmap_number_size(text, scale=1, spacing=1)
    image = Image.new("RGBA", (max(1, width), max(1, height)), (0, 0, 0, 0))
    draw_bitmap_number(ImageDraw.Draw(image), (0, 0), text, color, scale=1, spacing=1, thickness=thickness)
    return image


def bitmap_number_size_for_height(text, height):
    base = _draw_bitmap_number_base(text, (255, 255, 255))
    target_h = max(1, int(height))
    target_w = max(1, int(round(base.width * (target_h / base.height))))
    return target_w, target_h


def bitmap_number_height_for_font(font, extra=1):
    try:
        bbox = font.getbbox("88:88")
        return max(1, (bbox[3] - bbox[1]) + extra)
    except Exception:
        return 9 + extra


def draw_bitmap_number_fit(image, xy, text, fill, height, thickness=None):
    from PIL import Image
    base = _draw_bitmap_number_base(text, fill, thickness=thickness)
    target_w, target_h = bitmap_number_size_for_height(text, height)
    scaled = base.resize((target_w, target_h), Image.Resampling.NEAREST)
    image.paste(scaled, (int(xy[0]), int(xy[1])), scaled)


def draw_bitmap_number_fit_bold(image, xy, text, fill, height):
    from PIL import Image
    base = _draw_bitmap_number_base(text, fill)
    target_w, target_h = bitmap_number_size_for_height(text, height)
    scaled = base.resize((target_w, target_h), Image.Resampling.NEAREST)
    bold = Image.new("RGBA", (scaled.width + 1, scaled.height), (0, 0, 0, 0))
    bold.alpha_composite(scaled, (0, 0))
    bold.alpha_composite(scaled, (1, 0))
    image.paste(bold, (int(xy[0]), int(xy[1])), bold)


def bitmap_number_size_scaled(text, scale=2, spacing=1):
    return bitmap_number_size(text, scale=scale, spacing=spacing)


def draw_bitmap_number_scaled(image, xy, text, fill, scale=2, spacing=1):
    from PIL import ImageDraw
    draw_bitmap_number(ImageDraw.Draw(image), xy, text, fill, scale=scale, spacing=spacing)


def openweather_api_key():
    return (_settings_value("openWeatherApiKey") or os.environ.get("OPENWEATHER_API_KEY") or "").strip()


def temperature_units():
    value = str(_settings_value("temperatureUnits", "F") or "F").strip().upper()
    return "C" if value in ("C", "CELSIUS", "METRIC") else "F"


def openweather_units_param():
    return "metric" if temperature_units() == "C" else "imperial"


def time_format():
    value = str(_settings_value("timeFormat", "12") or "12").strip().lower()
    return "24" if value in ("24", "24h", "24-hour", "military") else "12"


def format_time(dt, include_ampm=False):
    if time_format() == "24":
        return dt.strftime("%H:%M")
    text = dt.strftime("%I:%M").lstrip("0")
    if include_ampm:
        text += dt.strftime("%p").lower()
    return text


def date_format():
    value = str(_settings_value("dateFormat", "md") or "md").strip()
    return value if value in ("md", "dm", "mon_d") else "md"


def format_short_date(dt):
    mode = date_format()
    if mode == "dm":
        return f"{dt.day:02d}/{dt.month:02d}"
    if mode == "mon_d":
        return f"{dt.strftime('%a')} {dt.month}/{dt.day}"
    return f"{dt.month:02d}/{dt.day:02d}"


def distance_units():
    value = str(_settings_value("distanceUnits", "imperial") or "imperial").strip().lower()
    return "metric" if value in ("metric", "km", "kilometers") else "imperial"


def format_distance_miles(miles, precision=0):
    try:
        miles = float(miles)
    except Exception:
        miles = 0.0
    if distance_units() == "metric":
        value = miles * 1.609344
        return f"{value:.{precision}f}km"
    return f"{miles:.{precision}f}mi"


def format_speed_knots(knots):
    try:
        knots = float(knots)
    except Exception:
        knots = 0.0
    if distance_units() == "metric":
        return f"{int(round(knots * 1.852))}KMH"
    return f"{int(round(knots))}KT"


def refresh_policy():
    value = str(_settings_value("refreshPolicy", "balanced") or "balanced").strip().lower()
    return value if value in ("conservative", "balanced", "frequent") else "balanced"


def refresh_seconds(conservative, balanced, frequent):
    return {"conservative": conservative, "balanced": balanced, "frequent": frequent}.get(refresh_policy(), balanced)


def convert_f_to_c(value):
    try:
        return int(round((float(value) - 32.0) * 5.0 / 9.0))
    except Exception:
        return value


def openweather_enabled():
    return bool(openweather_api_key())


def openweather_icon_from_weather(weather, default="sun"):
    weather = weather or {}
    try:
        code = int(weather.get("id"))
    except Exception:
        code = 0
    owm_icon = str(weather.get("icon") or "")
    main = str(weather.get("main") or "")
    desc = str(weather.get("description") or "")
    text = f"{main} {desc}".lower()
    is_night = owm_icon.endswith("n")
    if 200 <= code < 300 or "thunder" in text:
        return "thunder"
    if 300 <= code < 400 or "drizzle" in text:
        return "drizzle"
    if 500 <= code < 600 or "rain" in text or "shower" in text:
        return "rain"
    if 600 <= code < 700 or any(x in text for x in ("snow", "sleet", "ice", "flurr")):
        return "snow"
    if 700 <= code < 800 or any(x in text for x in ("fog", "mist", "haze", "smoke", "dust", "sand", "ash", "squall", "tornado")):
        return "fog"
    if code == 800 or "clear" in text:
        return "moon" if is_night else "sun"
    if code == 801:
        return "moon_cloud" if is_night else "partly"
    if 802 <= code < 900 or "cloud" in text or "overcast" in text:
        return "cloud"
    return default


def weather_icon_from_text(text, default="sun"):
    t = (text or "").lower()
    if any(x in t for x in ("thunder", "t-storm", "storm")):
        return "thunder"
    if any(x in t for x in ("drizzle", "sprinkle")):
        return "drizzle"
    if any(x in t for x in ("rain", "shower")):
        return "rain"
    if any(x in t for x in ("snow", "sleet", "ice", "blizzard", "wintry", "flurr")):
        return "snow"
    if any(x in t for x in ("fog", "mist", "haze", "smoke")):
        return "fog"
    if any(x in t for x in ("partly", "few clouds", "scattered")):
        return "partly"
    if any(x in t for x in ("cloud", "overcast")):
        return "cloud"
    if "moon" in t or "night" in t:
        return "moon"
    return default


def openweather_current_for_zip(zip_code, seconds=600):
    zip_code = re.sub(r"\D", "", zip_code or "")[:5]
    api_key = openweather_api_key()
    if len(zip_code) != 5 or not api_key:
        return None
    params = urllib.parse.urlencode({
        "zip": f"{zip_code},US",
        "appid": api_key,
        "units": openweather_units_param(),
    })
    return fetch_json_request(f"https://api.openweathermap.org/data/2.5/weather?{params}", seconds=seconds)


def openweather_sun_times_for_zip(zip_code):
    current = openweather_current_for_zip(zip_code, seconds=3600)
    if not current:
        return None
    sys = current.get("sys") or {}
    offset = int(current.get("timezone") or 0)
    if not sys.get("sunrise") or not sys.get("sunset"):
        return None
    tz = timezone(timedelta(seconds=offset))
    sunrise = datetime.fromtimestamp(int(sys["sunrise"]), tz=timezone.utc).astimezone(tz)
    sunset = datetime.fromtimestamp(int(sys["sunset"]), tz=timezone.utc).astimezone(tz)
    return sunrise, sunset


def openweather_air_quality_for_zip(zip_code):
    current = openweather_current_for_zip(zip_code, seconds=3600)
    if not current:
        return None
    coord = current.get("coord") or {}
    lat, lon = coord.get("lat"), coord.get("lon")
    api_key = openweather_api_key()
    if lat is None or lon is None or not api_key:
        return None
    params = urllib.parse.urlencode({"lat": lat, "lon": lon, "appid": api_key})
    data = fetch_json_request(f"https://api.openweathermap.org/data/2.5/air_pollution?{params}", seconds=1800)
    row = (data.get("list") or [{}])[0]
    main = row.get("main") or {}
    components = row.get("components") or {}
    # OpenWeather AQI is a 1-5 category, so keep the raw category and provide
    # PM2.5/PM10 for cards that want a more concrete number.
    return {
        "aqi": main.get("aqi"),
        "pm25": components.get("pm2_5"),
        "pm10": components.get("pm10"),
        "source": "openweather",
    }


def openweather_uv_for_zip(zip_code):
    current = openweather_current_for_zip(zip_code, seconds=3600)
    if not current:
        return None
    coord = current.get("coord") or {}
    lat, lon = coord.get("lat"), coord.get("lon")
    api_key = openweather_api_key()
    if lat is None or lon is None or not api_key:
        return None
    params = urllib.parse.urlencode({
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "units": openweather_units_param(),
        "exclude": "minutely,hourly,daily,alerts",
    })
    try:
        data = fetch_json_request(f"https://api.openweathermap.org/data/3.0/onecall?{params}", seconds=1800)
    except Exception:
        return None
    current = data.get("current") or {}
    return current.get("uvi")


def fetch_json_url(url, cache, seconds=45, force=False):
    now = datetime.now(timezone.utc)
    if not force and cache is not None and cache.get("body") and cache.get("expires", now) > now and cache.get("url", url) == url:
        return json.loads(cache["body"].decode("utf-8"))
    request = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1"})
    with urllib.request.urlopen(request, timeout=10) as response:
        body = response.read()
    if cache is not None:
        cache["body"] = body
        cache["expires"] = now + timedelta(seconds=seconds)
        cache["url"] = url
    return json.loads(body.decode("utf-8"))


def fetch_sport_scoreboard(url, cache, favorite="", seconds=15):
    scoreboard_url = dated_scoreboard_url(url)
    data = fetch_json_url(scoreboard_url, cache, seconds=seconds)
    event = pick_sport_event(data.get("events", []), favorite)
    force_refresh = event is None and bool(favorite)
    if event:
        competition = event.get("competitions", [{}])[0]
        state = competition.get("status", {}).get("type", {}).get("state")
        if state == "in":
            force_refresh = True
        elif state == "pre":
            try:
                event_dt = datetime.fromisoformat(event.get("date", "").replace("Z", "+00:00"))
                if event_dt <= datetime.now(timezone.utc) + timedelta(seconds=60):
                    force_refresh = True
            except Exception:
                pass
    if force_refresh:
        data = fetch_json_url(scoreboard_url, cache, seconds=seconds, force=True)
    return data


def fetch_json_request(url, seconds=600):
    now = datetime.now(timezone.utc)
    _prune_expiring_cache(WEATHER_CACHE, now, WEATHER_CACHE_MAX_ENTRIES)
    cached = WEATHER_CACHE.get(url)
    if cached and cached["expires"] > now:
        return cached["data"]
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Pixora/0.1", "Accept": "application/geo+json, application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        if cached and "data" in cached:
            return cached["data"]
        raise
    _cache_put(WEATHER_CACHE, url, {"expires": now + timedelta(seconds=seconds), "data": data}, WEATHER_CACHE_MAX_ENTRIES)
    return data


def fetch_json_with_headers(url, headers=None, seconds=600, cache_key=None):
    now = datetime.now(timezone.utc)
    key = cache_key or url + "|" + json.dumps(headers or {}, sort_keys=True)
    _prune_expiring_cache(WEATHER_CACHE, now, WEATHER_CACHE_MAX_ENTRIES)
    cached = WEATHER_CACHE.get(key)
    if cached and cached["expires"] > now:
        return cached["data"]
    request_headers = {"User-Agent": "Pixora/0.1", "Accept": "application/json"}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        if cached and "data" in cached:
            return cached["data"]
        raise
    _cache_put(WEATHER_CACHE, key, {"expires": now + timedelta(seconds=seconds), "data": data}, WEATHER_CACHE_MAX_ENTRIES)
    return data


def format_compact_number(value):
    try:
        n = float(value)
    except Exception:
        return "--"
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1000000000:
        return f"{sign}{n/1000000000:.1f}B"
    if n >= 1000000:
        return f"{sign}{n/1000000:.1f}M"
    if n >= 10000:
        return f"{sign}{n/1000:.0f}K"
    if n >= 1000:
        return f"{sign}{n/1000:.1f}K"
    return f"{sign}{int(round(n))}"


def _draw_counter_logo(draw, logo, x, y, color):
    logo = (logo or "").lower()
    if logo == "youtube":
        draw.rounded_rectangle((x, y + 3, x + 17, y + 15), radius=3, fill=(255, 0, 0))
        draw.polygon([(x + 7, y + 6), (x + 7, y + 12), (x + 13, y + 9)], fill=(255, 255, 255))
    elif logo == "facebook":
        draw.rounded_rectangle((x + 2, y + 1, x + 16, y + 15), radius=3, fill=(24, 119, 242))
        draw.rectangle((x + 9, y + 5, x + 12, y + 15), fill=(255, 255, 255))
        draw.rectangle((x + 7, y + 8, x + 14, y + 10), fill=(255, 255, 255))
        draw.rectangle((x + 10, y + 3, x + 15, y + 5), fill=(255, 255, 255))
        draw.point((x + 15, y + 5), fill=(24, 119, 242))
    elif logo == "x":
        draw.line((x + 3, y + 2, x + 15, y + 15), fill=(245, 250, 255), width=2)
        draw.line((x + 15, y + 2, x + 3, y + 15), fill=(245, 250, 255), width=2)
    elif logo == "instagram":
        draw.point((x + 3, y + 2), fill=(255, 220, 80))
        draw.line((x + 4, y + 1, x + 14, y + 1), fill=(245, 80, 170), width=2)
        draw.line((x + 15, y + 3, x + 15, y + 13), fill=(180, 80, 255), width=2)
        draw.line((x + 4, y + 15, x + 14, y + 15), fill=(255, 120, 60), width=2)
        draw.line((x + 2, y + 4, x + 2, y + 12), fill=(255, 200, 80), width=2)
        draw.ellipse((x + 6, y + 5, x + 12, y + 11), outline=(245, 250, 255))
        draw.point((x + 13, y + 4), fill=(255, 210, 80))
    else:
        draw.ellipse((x + 3, y + 2, x + 15, y + 14), outline=color)


def render_counter_card(title, label, value, color=(80, 180, 255), sublabel="FOLLOWERS", logo=None, target=None):
    from PIL import Image, ImageDraw, ImageFont
    width = 128 if target == "matrixportal-s3-128x32" else 64
    image = Image.new("RGB", (width, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 16)
    except Exception:
        font = bold = big = ImageFont.load_default()

    draw.rectangle((0, 0, width - 1, 6), fill=(5, 18, 28))
    title = str(title or "")[:20 if width == 128 else 12].upper()
    tw = draw.textbbox((0, 0), title, font=bold)[2]
    draw_sharp_text(image, ((width - tw) // 2, -3), title, color, bold)

    if logo:
        logo_x = 3 if width == 64 else 6
        _draw_counter_logo(draw, logo, logo_x, 10, color)
        value_left = 20 if width == 64 else 28
        value_width = width - value_left
    else:
        value_left = 0
        value_width = width

    val = format_compact_number(value)
    vw = draw.textbbox((0, 0), val, font=big)[2]
    if vw <= value_width - 2:
        draw_sharp_text(image, (value_left + (value_width - vw) // 2, 6), val, (245, 250, 255), big)
    else:
        vw = draw.textbbox((0, 0), val, font=bold)[2]
        draw_sharp_text(image, (value_left + (value_width - vw) // 2, 9), val, (245, 250, 255), bold)

    bottom = (str(label or sublabel or "")[:18 if width == 128 else 9] or sublabel).upper()
    bw = draw.textbbox((0, 0), bottom, font=font)[2]
    draw_sharp_text(image, ((width - bw) // 2, 22), bottom, (145, 165, 182), font)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def weather_for_zip(zip_code):
    zip_code = re.sub(r"\D", "", zip_code or "")[:5]
    if len(zip_code) != 5:
        raise ValueError("Enter a 5 digit ZIP code.")
    api_key = openweather_api_key()
    if api_key:
        try:
            current = openweather_current_for_zip(zip_code, seconds=600)
            weather = (current.get("weather") or [{}])[0]
            main = current.get("main") or {}
            condition = " ".join([
                str(weather.get("main") or ""),
                str(weather.get("description") or ""),
            ]).strip() or "Weather"
            temp = main.get("temp")
            wind = current.get("wind") or {}
            return {
                "temperature": int(round(float(temp))) if temp is not None else "--",
                "temperatureUnit": temperature_units(),
                "shortForecast": condition.title(),
                "icon": openweather_icon_from_weather(weather),
                "conditionId": weather.get("id"),
                "openWeatherIcon": weather.get("icon"),
                "feelsLike": int(round(float(main["feels_like"]))) if main.get("feels_like") is not None else None,
                "humidity": main.get("humidity"),
                "windSpeed": wind.get("speed"),
                "source": "openweather",
            }
        except Exception:
            pass
    location = fetch_json_request(f"https://api.zippopotam.us/us/{zip_code}", seconds=86400)
    place = location["places"][0]
    lat, lon = place["latitude"], place["longitude"]
    point = fetch_json_request(f"https://api.weather.gov/points/{lat},{lon}", seconds=86400)
    forecast_url = point["properties"]["forecastHourly"]
    forecast = fetch_json_request(forecast_url, seconds=600)
    period = forecast["properties"]["periods"][0]
    short = period.get("shortForecast", "Weather")
    return {
        "temperature": convert_f_to_c(period.get("temperature")) if temperature_units() == "C" else period.get("temperature"),
        "temperatureUnit": temperature_units(),
        "shortForecast": short,
        "icon": weather_icon_from_text(short),
        "source": "weather.gov",
    }


def openweather_forecast_for_zip(zip_code):
    zip_code = re.sub(r"\D", "", zip_code or "")[:5]
    api_key = openweather_api_key()
    if len(zip_code) != 5 or not api_key:
        return None
    params = urllib.parse.urlencode({
        "zip": f"{zip_code},US",
        "appid": api_key,
        "units": openweather_units_param(),
    })
    data = fetch_json_request(f"https://api.openweathermap.org/data/2.5/forecast?{params}", seconds=1800)
    rows = data.get("list") or []
    daily = {}
    for row in rows:
        raw = row.get("dt_txt") or ""
        try:
            dt = datetime.fromisoformat(raw)
        except Exception:
            dt = datetime.fromtimestamp(row.get("dt", 0), tz=timezone.utc)
        day_key = dt.date().isoformat()
        weather = (row.get("weather") or [{}])[0]
        condition = " ".join([str(weather.get("main") or ""), str(weather.get("description") or "")]).strip()
        icon = openweather_icon_from_weather(weather)
        main = row.get("main") or {}
        temp = main.get("temp")
        if temp is None:
            continue
        temp = float(temp)
        item = daily.setdefault(day_key, {
            "date": dt.date(),
            "name": dt.strftime("%A"),
            "high": temp,
            "low": temp,
            "shortForecast": condition.title() or "Weather",
            "icon": icon,
            "conditionId": weather.get("id"),
            "openWeatherIcon": weather.get("icon"),
            "noon_delta": 99,
        })
        item["high"] = max(item["high"], temp)
        item["low"] = min(item["low"], temp)
        noon_delta = abs(dt.hour - 12)
        if noon_delta < item.get("noon_delta", 99):
            item["shortForecast"] = condition.title() or item["shortForecast"]
            item["icon"] = icon
            item["conditionId"] = weather.get("id")
            item["openWeatherIcon"] = weather.get("icon")
            item["noon_delta"] = noon_delta
    days = []
    for item in sorted(daily.values(), key=lambda x: x["date"]):
        days.append({
            "name": item["name"],
            "temperature": int(round(item["high"])),
            "low": int(round(item["low"])),
            "temperatureUnit": temperature_units(),
            "shortForecast": item["shortForecast"],
            "icon": item["icon"],
            "conditionId": item.get("conditionId"),
            "openWeatherIcon": item.get("openWeatherIcon"),
            "isDaytime": True,
        })
    return days


def openweather_alerts_for_zip(zip_code):
    zip_code = re.sub(r"\D", "", zip_code or "")[:5]
    api_key = openweather_api_key()
    if len(zip_code) != 5 or not api_key:
        return None
    current_params = urllib.parse.urlencode({
        "zip": f"{zip_code},US",
        "appid": api_key,
        "units": openweather_units_param(),
    })
    current = fetch_json_request(f"https://api.openweathermap.org/data/2.5/weather?{current_params}", seconds=3600)
    coord = current.get("coord") or {}
    lat, lon = coord.get("lat"), coord.get("lon")
    if lat is None or lon is None:
        return None
    one_call_params = urllib.parse.urlencode({
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "units": openweather_units_param(),
        "exclude": "minutely,hourly,daily,current",
    })
    try:
        data = fetch_json_request(f"https://api.openweathermap.org/data/3.0/onecall?{one_call_params}", seconds=300)
    except Exception:
        return None
    alerts = []
    for alert in data.get("alerts") or []:
        event = alert.get("event") or "Weather Alert"
        alerts.append({
            "properties": {
                "event": event,
                "severity": "moderate",
                "headline": event,
                "description": alert.get("description") or "",
            }
        })
    return alerts


def draw_sharp_text(image, xy, text, fill, font):
    from PIL import Image, ImageDraw
    text = str(text or "")
    if text and any(ch.isdigit() for ch in text) and _is_bold_font(font):
        try:
            bbox = font.getbbox(text)
        except Exception:
            bbox = (0, 0, 0, 7)
        old_w = max(0, bbox[2] - bbox[0])
        scale = max(1, int(round(getattr(font, "size", 8) / 8)))
        spacing = scale
        parts = _bold_mixed_number_parts(text)
        use_mixed = any(is_numeric for is_numeric, _value in parts)
        if not use_mixed:
            mask = Image.new("1", image.size, 0)
            ImageDraw.Draw(mask).text(xy, text, fill=1, font=font)
            image.paste(Image.new("RGB", image.size, fill), (0, 0), mask)
            return
        new_w = pixora_mixed_bold_number_size(text, font, scale=scale, spacing=spacing)[0]
        x = int(xy[0])
        y = int(xy[1]) + int(bbox[1])
        right_margin = image.width - (x + old_w)
        left_margin = x
        if old_w > new_w and abs(left_margin - right_margin) <= 2:
            x += (old_w - new_w) // 2
        elif old_w > new_w and (right_margin <= 2 or x > image.width // 2):
            x += old_w - new_w
        mask = Image.new("1", image.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        cursor = x
        for is_numeric, value in parts:
            if is_numeric:
                draw_pixora_bold_number(mask_draw, (cursor, y), value, 1, scale=scale, spacing=spacing)
                cursor += pixora_bold_number_size(value, scale=scale, spacing=spacing)[0]
            else:
                try:
                    part_bbox = font.getbbox(value)
                    text_y = y - int(part_bbox[1])
                    part_w = max(0, part_bbox[2] - part_bbox[0])
                except Exception:
                    text_y = xy[1]
                    part_w = len(value) * 4 * scale
                mask_draw.text((cursor, text_y), value, fill=1, font=font)
                cursor += part_w
        image.paste(Image.new("RGB", image.size, fill), (0, 0), mask)
        return
    mask = Image.new("1", image.size, 0)
    ImageDraw.Draw(mask).text(xy, text, fill=1, font=font)
    image.paste(Image.new("RGB", image.size, fill), (0, 0), mask)


def draw_sharp_text_weighted(image, xy, text, fill, font, weight=2):
    from PIL import Image, ImageDraw
    text = str(text or "")
    mask = Image.new("1", image.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.text(xy, text, fill=1, font=font)
    if weight >= 2:
        draw.text((xy[0] + 1, xy[1]), text, fill=1, font=font)
    if weight >= 3:
        draw.text((xy[0], xy[1] + 1), text, fill=1, font=font)
    image.paste(Image.new("RGB", image.size, fill), (0, 0), mask)


def draw_centered_bitmap_number(image, box, text, fill, scale=1, spacing=1):
    from PIL import ImageDraw
    x1, y1, x2, y2 = box
    w, h = bitmap_number_size(text, scale=scale, spacing=spacing)
    x = int(round((x1 + x2 - w) / 2))
    y = int(round((y1 + y2 - h) / 2))
    draw_bitmap_number(ImageDraw.Draw(image), (x, y), text, fill, scale=scale, spacing=spacing)


def draw_centered_bitmap_number_fit(image, box, text, fill, height):
    x1, y1, x2, y2 = box
    w, h = bitmap_number_size_for_height(text, height)
    x = int(round((x1 + x2 - w) / 2))
    y = int(round((y1 + y2 - h) / 2))
    draw_bitmap_number_fit(image, (x, y), text, fill, height)


def draw_sport_score_number(image, box, text, fill, height):
    draw_centered_bitmap_number_fit(image, box, text, fill, height)


def draw_mini_weather_icon(draw, icon, cx, y):
    if icon == "sun":
        draw.ellipse((cx - 4, y + 2, cx + 4, y + 8), fill=(255, 205, 64))
        for pts in [
            (cx, y, cx, y + 1), (cx, y + 9, cx, y + 10),
            (cx - 6, y + 5, cx - 5, y + 5), (cx + 5, y + 5, cx + 6, y + 5),
        ]:
            draw.line(pts, fill=(255, 225, 90))
    elif icon == "moon":
        draw.ellipse((cx - 4, y + 1, cx + 4, y + 9), fill=(230, 240, 255))
        draw.ellipse((cx - 1, y, cx + 6, y + 8), fill=(0, 0, 0))
        draw.point((cx - 6, y + 2), fill=(160, 205, 255))
        draw.point((cx + 4, y + 10), fill=(160, 205, 255))
    elif icon == "partly":
        draw.ellipse((cx - 6, y + 1, cx + 1, y + 8), fill=(255, 205, 64))
        draw.ellipse((cx - 2, y + 4, cx + 4, y + 9), fill=(145, 170, 190))
        draw.ellipse((cx + 1, y + 2, cx + 7, y + 9), fill=(175, 195, 210))
        draw.rectangle((cx - 1, y + 6, cx + 8, y + 10), fill=(175, 195, 210))
    elif icon == "moon_cloud":
        draw.ellipse((cx - 6, y + 1, cx + 1, y + 8), fill=(215, 230, 255))
        draw.ellipse((cx - 3, y, cx + 3, y + 7), fill=(0, 0, 0))
        draw.ellipse((cx - 2, y + 4, cx + 4, y + 9), fill=(135, 155, 175))
        draw.ellipse((cx + 1, y + 2, cx + 7, y + 9), fill=(165, 185, 205))
        draw.rectangle((cx - 1, y + 6, cx + 8, y + 10), fill=(165, 185, 205))
    elif icon == "cloud":
        draw.ellipse((cx - 6, y + 3, cx, y + 8), fill=(135, 155, 175))
        draw.ellipse((cx - 2, y + 1, cx + 6, y + 8), fill=(170, 190, 205))
        draw.rectangle((cx - 5, y + 5, cx + 7, y + 9), fill=(170, 190, 205))
    elif icon == "rain":
        draw.ellipse((cx - 6, y + 2, cx, y + 6), fill=(120, 150, 170))
        draw.ellipse((cx - 2, y, cx + 6, y + 6), fill=(145, 170, 190))
        draw.rectangle((cx - 5, y + 4, cx + 7, y + 7), fill=(145, 170, 190))
        for dx in (-4, 0, 4):
            draw.line((cx + dx, y + 7, cx + dx - 1, y + 10), fill=(64, 181, 255))
    elif icon == "drizzle":
        draw.ellipse((cx - 6, y + 2, cx, y + 6), fill=(125, 150, 170))
        draw.ellipse((cx - 2, y, cx + 6, y + 6), fill=(150, 175, 195))
        draw.rectangle((cx - 5, y + 4, cx + 7, y + 7), fill=(150, 175, 195))
        for dx in (-3, 2):
            draw.point((cx + dx, y + 9), fill=(90, 190, 255))
    elif icon == "thunder":
        draw.ellipse((cx - 6, y + 2, cx, y + 6), fill=(90, 105, 125))
        draw.ellipse((cx - 2, y, cx + 6, y + 6), fill=(115, 130, 150))
        draw.rectangle((cx - 5, y + 4, cx + 7, y + 7), fill=(115, 130, 150))
        draw.polygon([(cx, y + 6), (cx - 3, y + 11), (cx + 1, y + 9), (cx - 1, y + 13), (cx + 5, y + 6)], fill=(255, 225, 60))
    elif icon == "snow":
        draw.ellipse((cx - 6, y + 2, cx, y + 6), fill=(180, 200, 215))
        draw.ellipse((cx - 2, y, cx + 6, y + 6), fill=(205, 220, 230))
        draw.rectangle((cx - 5, y + 4, cx + 7, y + 7), fill=(205, 220, 230))
        for dx in (-4, 0, 4):
            draw.point((cx + dx, y + 9), fill=(235, 250, 255))
    elif icon == "fog":
        draw.ellipse((cx - 6, y + 2, cx, y + 6), fill=(155, 170, 180))
        draw.ellipse((cx - 2, y, cx + 6, y + 6), fill=(185, 195, 205))
        draw.rectangle((cx - 5, y + 4, cx + 7, y + 7), fill=(185, 195, 205))
        draw.line((cx - 7, y + 9, cx + 7, y + 9), fill=(135, 155, 170))
        draw.line((cx - 5, y + 11, cx + 5, y + 11), fill=(110, 130, 145))


def paste_openweather_icon(image, icon_code, x, y, size=14):
    icon_code = re.sub(r"[^0-9a-z]", "", str(icon_code or "").lower())
    if not icon_code:
        return False
    try:
        from PIL import Image
        cached = _cache_get(OPENWEATHER_ICON_CACHE, (icon_code, size))
        if cached is None:
            url = f"https://openweathermap.org/img/wn/{icon_code}@2x.png"
            with urllib.request.urlopen(
                urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1"}),
                timeout=2,
            ) as response:
                data = response.read()
            icon = Image.open(BytesIO(data)).convert("RGBA")
            icon = icon.resize((size, size), Image.Resampling.LANCZOS)
            # Keep it crisp and bright on the LED panel by dropping very faint alpha.
            r, g, b, a = icon.split()
            a = a.point(lambda p: 255 if p > 42 else 0)
            cached = Image.merge("RGBA", (r, g, b, a))
            _cache_put(OPENWEATHER_ICON_CACHE, (icon_code, size), cached, ICON_CACHE_MAX_ENTRIES)
        image.paste(cached, (int(x), int(y)), cached)
        return True
    except Exception:
        return False


def fetch_logo(url, size=11):
    url = str(url or "").strip()
    if not url:
        return None
    cache_key = (url, int(size))
    cached = _cache_get(LOGO_CACHE, cache_key)
    if cached is not None:
        return cached
    try:
        from PIL import Image
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1"}), timeout=2
        ) as response:
            data = response.read()
        img = Image.open(BytesIO(data)).convert("RGBA")
        img.thumbnail((size, size), Image.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.alpha_composite(img, ((size - img.width) // 2, (size - img.height) // 2))
        img = canvas
        r, g, b, a = img.split()
        a = a.point(lambda p: 255 if p > 48 else 0)
        logo = Image.merge("RGBA", (r, g, b, a))
        _cache_put(LOGO_CACHE, cache_key, logo, LOGO_CACHE_MAX_ENTRIES)
        return logo
    except Exception:
        return None


def get_team_record(competitor, series=None):
    if (series or {}).get("type") == "playoff":
        team = (competitor or {}).get("team") or {}
        team_ids = {
            str((competitor or {}).get("id") or ""),
            str(team.get("id") or ""),
            str(team.get("uid") or ""),
        }
        team_ids = {value for value in team_ids if value}
        series_rows = (series or {}).get("competitors") or []
        matched = None
        others = []
        for row in series_rows:
            row_ids = {str(row.get("id") or ""), str(row.get("uid") or "")}
            row_ids = {value for value in row_ids if value}
            if team_ids & row_ids:
                matched = row
            else:
                others.append(row)
        if matched is not None:
            try:
                wins = int(matched.get("wins") or 0)
            except Exception:
                wins = 0
            try:
                opponent_wins = max(int(row.get("wins") or 0) for row in others) if others else 0
            except Exception:
                opponent_wins = 0
            return f"{wins}-{opponent_wins}"
    for record in competitor.get("records", []):
        if record.get("type") == "total" or record.get("name") == "overall":
            return record.get("summary", "")
    return ""


_NAMED_COLORS = {
    "white": (255, 255, 255), "red": (238, 80, 80), "green": (100, 220, 100),
    "blue": (80, 150, 255), "orange": (255, 160, 60), "yellow": (255, 230, 60),
    "teal": (24, 182, 163), "purple": (180, 120, 255), "pink": (255, 120, 180),
}


def parse_color(value, default=(255, 255, 255)):
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return tuple(max(0, min(255, int(value[index]))) for index in range(3))
        except Exception:
            return default
    text = str(value or "").strip()
    named = _NAMED_COLORS.get(text.lower())
    if named:
        return named
    text = text.lstrip("#")
    if len(text) == 3 and re.fullmatch(r"[0-9A-Fa-f]{3}", text):
        text = "".join(ch * 2 for ch in text)
    if len(text) == 6 and re.fullmatch(r"[0-9A-Fa-f]{6}", text):
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    return default


def _msg_font():
    from PIL import ImageFont
    try:
        return ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        return ImageFont.load_default()


def message_text_width(text):
    from PIL import Image, ImageDraw
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    return draw.textbbox((0, 0), text, font=_msg_font())[2]


def _message_width(width=64):
    return 128 if int(width or 64) >= 96 else 64


def _wrap_frame(text, color_rgb, width=64):
    from PIL import Image, ImageDraw
    width = _message_width(width)
    image = Image.new("RGB", (width, 32), (0, 0, 0))
    font = _msg_font()
    draw = ImageDraw.Draw(image)
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip() if current else word
        if draw.textbbox((0, 0), test, font=font)[2] <= width - 2:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    lines = lines[:4]
    line_h = 8
    y = (32 - len(lines) * line_h) // 2 - 3
    for line in lines:
        w = draw.textbbox((0, 0), line, font=font)[2]
        draw_sharp_text(image, ((width - w) // 2, y), line, color_rgb, font)
        y += line_h
    return image


def render_message_wrap(text, color_rgb, width=64):
    out = BytesIO()
    _wrap_frame(text, color_rgb, width=width).save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def render_message_flash(text, color_rgb, width=64):
    from PIL import Image
    width = _message_width(width)
    on_frame = _wrap_frame(text, color_rgb, width=width)
    off_frame = Image.new("RGB", (width, 32), (0, 0, 0))
    out = BytesIO()
    on_frame.save(
        out, "WEBP", save_all=True,
        append_images=[off_frame],
        duration=[500, 250],
        loop=0,
    )
    return out.getvalue()


def render_message_scroll(text, color_rgb, width=64):
    from PIL import Image, ImageDraw
    width = _message_width(width)
    font = _msg_font()
    draw_dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    text_w = draw_dummy.textbbox((0, 0), text, font=font)[2]
    px_per_frame = 2
    frame_ms = 33
    total = width + text_w + 32
    frames = []
    for i in range(0, total, px_per_frame):
        img = Image.new("RGB", (width, 32), (0, 0, 0))
        x = width - i
        if x < width:
            draw_sharp_text(img, (x, 12), text, color_rgb, font)
        frames.append(img)
    out = BytesIO()
    frames[0].save(
        out, "WEBP", save_all=True,
        append_images=frames[1:],
        duration=frame_ms,
        loop=0,
    )
    return out.getvalue()


def render_text_webp(text, color):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (64, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    draw_sharp_text(
        image,
        ((64 - (bbox[2] - bbox[0])) // 2, (32 - (bbox[3] - bbox[1])) // 2),
        text, color, font,
    )
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def fallback_frame(text, width=64, color=(180, 220, 255), background=(0, 0, 0), dwell_secs=None):
    from PIL import Image, ImageFont
    width = 128 if int(width or 64) > 96 else 64
    image = Image.new("RGB", (width, 32), parse_color(background, (0, 0, 0)))
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        font = ImageFont.load_default()
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image)
    words = str(text or "NO DATA").upper().split()
    lines = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if current and bbox[2] - bbox[0] > width - 4:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    lines = lines[:3] or ["NO DATA"]
    total_h = len(lines) * 9
    y = max(0, (32 - total_h) // 2)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = max(0, (width - (bbox[2] - bbox[0])) // 2)
        draw_sharp_text(image, (x, y), line, parse_color(color, (180, 220, 255)), font)
        y += 9
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    body = out.getvalue()
    if dwell_secs is None:
        return body
    return {"body": body, "dwell_secs": max(1, int(dwell_secs or 6))}


def pick_sport_event(events, favorite):
    local_tz = pixora_local_timezone()
    today = datetime.now(local_tz).date() if local_tz else pixora_local_now().date()
    favorite = (favorite or "").upper()
    today_events = []
    for event in events:
        raw = event.get("date", "")
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.astimezone(local_tz).date() == today:
                today_events.append(event)
        except Exception:
            today_events.append(event)
    events = today_events or []
    for state in ("in", "pre", "post"):
        for event in events:
            competition = event.get("competitions", [{}])[0]
            ev_state = competition.get("status", {}).get("type", {}).get("state")
            teams = json.dumps(event).upper()
            if ev_state == state and (not favorite or f'"{favorite}"' in teams):
                return event
    return None


def dated_scoreboard_url(url):
    today = pixora_local_now().strftime("%Y%m%d")
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}dates={today}"


def render_sport_card(options, url, cache, status_color, fallback_text):
    from PIL import Image, ImageDraw, ImageFont
    opts = options or {}
    sports_meta = opts.get("_sports_meta")
    if isinstance(sports_meta, dict):
        sports_meta.update({"has_event": False, "live": False, "state": ""})
    favorite = opts.get("favoriteTeam", "")
    data = fetch_sport_scoreboard(url, cache, favorite, seconds=15)
    event = pick_sport_event(data.get("events", []), favorite)
    if not event:
        cache["expires"] = datetime.now(timezone.utc) + timedelta(seconds=15)
        return None

    competition = event.get("competitions", [{}])[0]
    competitors = competition.get("competitors", [])
    away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[-1] if competitors else {})
    home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0] if competitors else {})
    away_team = away.get("team", {})
    home_team = home.get("team", {})
    state = competition.get("status", {}).get("type", {}).get("state")
    if isinstance(sports_meta, dict):
        sports_meta.update({"has_event": True, "live": state == "in", "state": state or ""})

    if state == "in":
        cache_secs = 15
    elif state == "pre":
        try:
            event_dt = datetime.fromisoformat(event.get("date", "").replace("Z", "+00:00"))
            secs_until = (event_dt - datetime.now(timezone.utc)).total_seconds()
            cache_secs = 15 if secs_until < 600 else 900
        except Exception:
            cache_secs = 900
    else:
        cache_secs = 900
    cache["expires"] = datetime.now(timezone.utc) + timedelta(seconds=cache_secs)
    status = competition.get("status", {}).get("type", {}).get("shortDetail", "")
    status = re.sub(r"\s+[A-Z]{2,3}T?$", "", status)   # strip timezone (ET, CT, PT…)
    status = re.sub(r"\s+-\s+", " ", status)             # "5/4 - 6:40" → "5/4 6:40"
    status = re.sub(r"\s+(AM|PM)", r"\1", status)        # "6:40 PM" → "6:40PM"
    score = "VS" if state == "pre" else f"{away.get('score', '0')}-{home.get('score', '0')}"
    logger = (options or {}).get("_log")
    if callable(logger) and state == "in":
        try:
            away_abbr = away_team.get("abbreviation") or away_team.get("shortDisplayName") or "AWAY"
            home_abbr = home_team.get("abbreviation") or home_team.get("shortDisplayName") or "HOME"
            logger(f"[sports] live scoreboard {away_abbr} {away.get('score', '0')} - {home_abbr} {home.get('score', '0')} {status}")
        except Exception:
            pass

    is_baseball = str(fallback_text or "").upper() in ("NO MLB", "NO CBASE", "NO SOFT")
    if is_baseball:
        status = baseball_status_without_clock(status)
    outs = baseball_outs(competition) if is_baseball and state == "in" else None
    batting_side = baseball_batting_side(status) if is_baseball and state == "in" else None
    bases = baseball_bases(competition) if is_baseball and state == "in" else None

    if (options or {}).get("_target") == "matrixportal-s3-128x32":
        compact_logo_text = str(fallback_text or "").upper()
        compact_basketball = compact_logo_text in ("NO NBA", "NO WNBA", "NO WCBB", "NO MCBB", "NO GLEAG")
        logo_size = 24 if compact_basketball else 28
        score_pad = 1 if compact_basketball else 6
        return _render_sport_card_128(
            away, home, away_team, home_team, status, score, status_color, competition.get("series"), outs, batting_side, bases, logo_size, score_pad, compact_basketball
        )

    image = Image.new("RGB", (64, 32), (5, 7, 10))
    draw = ImageDraw.Draw(image)
    try:
        tiny = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        small = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        score_font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        tiny = small = score_font = ImageFont.load_default()

    draw.rectangle((0, 0, 63, 6), fill=(8, 18, 28))
    header_status = status.upper()
    if outs is not None:
        while header_status and draw.textbbox((0, 0), header_status, font=tiny)[2] > 45:
            header_status = header_status[:-1].rstrip()
    else:
        header_status = header_status[:18]
    draw_sharp_text(image, (1, -3), header_status, status_color, tiny)
    if outs is not None:
        draw_baseball_out_dots(draw, 56, 2, outs, size=1)

    use_segment_score = any(ch.isdigit() for ch in score) and _BOLD_NUMERIC_RE.match(score)
    if use_segment_score:
        score_h = 9
        sw, sh = bitmap_number_size_for_height(score, score_h)
    else:
        sb = draw.textbbox((0, 0), score, font=score_font)
        sw, sh = sb[2] - sb[0], sb[3] - sb[1]
    pad = 3
    bx1, bx2 = 32 - sw // 2 - pad, 32 + (sw + 1) // 2 + pad
    if use_segment_score:
        pill_w = max(28, bx2 - bx1)
        bx1, bx2 = 32 - pill_w // 2, 32 + (pill_w + 1) // 2
    by1, by2 = 7, 7 + sh + pad * 2
    draw.rounded_rectangle((bx1, by1, bx2, by2), radius=3, fill=(18, 29, 39), outline=(69, 87, 104))
    if use_segment_score:
        draw_sport_score_number(image, (bx1 + 1, by1, bx2 + 1, by2), score, (247, 251, 255), score_h)
    else:
        draw_sharp_text(image, (33 - sw // 2, 4 + pad), score, (247, 251, 255), score_font)
    away_abbrev = away_team.get("abbreviation", "AWY")[:3]
    home_abbrev = home_team.get("abbreviation", "HME")[:3]
    habb_w = draw.textbbox((0, 0), home_abbrev, font=small)[2]
    away_abb_w = draw.textbbox((0, 0), away_abbrev, font=small)[2]
    away_abb_x = 2
    home_abb_x = 63 - habb_w
    if batting_side != "away":
        draw_sharp_text(image, (2, 15), away_abbrev, (255, 255, 255), small)
    if batting_side != "home":
        draw_sharp_text(image, (home_abb_x, 15), home_abbrev, (255, 255, 255), small)

    series = competition.get("series")
    away_rec = get_team_record(away, series)[:7]
    home_rec = get_team_record(home, series)[:7]
    draw_sharp_text(image, (2, 22), away_rec, (174, 185, 196), tiny)
    if home_rec:
        hrec_w = draw.textbbox((0, 0), home_rec, font=tiny)[2]
        draw_sharp_text(image, (63 - hrec_w, 22), home_rec, (174, 185, 196), tiny)

    away_logo = fetch_logo(away_team.get("logo", ""))
    home_logo = fetch_logo(home_team.get("logo", ""))
    if away_logo:
        image.paste(away_logo, (2, 7), away_logo)
    if home_logo:
        image.paste(home_logo, (52, 7), home_logo)
    if batting_side == "away":
        draw_baseball_diamond(draw, 10, 19, bases, size=3)
    elif batting_side == "home":
        draw_baseball_diamond(draw, 54, 19, bases, size=3)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def baseball_outs(competition):
    try:
        situation = (competition or {}).get("situation") or {}
        raw = situation.get("outs")
        if raw is None:
            raw = situation.get("out")
        if raw is None:
            return None
        return max(0, min(3, int(raw)))
    except Exception:
        return None


def _base_occupied(situation, *keys):
    for key in keys:
        if key not in situation:
            continue
        value = situation.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value > 0
        if isinstance(value, dict):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on", "occupied")
        if value:
            return True
    return False


def baseball_bases(competition):
    situation = (competition or {}).get("situation") or {}
    if not isinstance(situation, dict):
        return {"first": False, "second": False, "third": False}
    bases = {
        "first": _base_occupied(situation, "onFirst", "first", "firstBase", "runnerOnFirst"),
        "second": _base_occupied(situation, "onSecond", "second", "secondBase", "runnerOnSecond"),
        "third": _base_occupied(situation, "onThird", "third", "thirdBase", "runnerOnThird"),
    }
    runners = situation.get("runnersOnBase") or situation.get("runners") or []
    if isinstance(runners, dict):
        runners = runners.values()
    for runner in runners if isinstance(runners, (list, tuple, set, dict)) else []:
        base = runner.get("base") if isinstance(runner, dict) else runner
        label = str(base or "").strip().lower()
        if label in ("1", "1b", "first", "first base"):
            bases["first"] = True
        elif label in ("2", "2b", "second", "second base"):
            bases["second"] = True
        elif label in ("3", "3b", "third", "third base"):
            bases["third"] = True
    return bases


def baseball_status_without_clock(status):
    text = str(status or "").strip()
    text = re.sub(r"\s+\d{1,2}:\d{2}(?:\s*\d(?:st|nd|rd|th)?)?\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+\d{1,2}:\d{2}\s*$", "", text)
    return text.strip() or status


def baseball_batting_side(status):
    text = str(status or "").strip().lower()
    if text.startswith(("top", "t ")):
        return "away"
    if text.startswith(("bot", "bottom", "b ")):
        return "home"
    return None


def draw_baseball_out_dots(draw, cx, cy, outs, size=1):
    try:
        outs = max(0, min(3, int(outs)))
    except Exception:
        return
    spacing = 5 if size <= 1 else 6
    start = int(cx) - spacing
    y = int(cy)
    for index in range(3):
        x = start + index * spacing
        box = (x - size, y - size, x + size, y + size)
        if index < outs:
            draw.ellipse(box, fill=(232, 54, 62))
        else:
            draw.ellipse(box, outline=(92, 111, 130))


def draw_baseball_diamond(draw, cx, cy, bases=None, size=4):
    bases = bases if isinstance(bases, dict) else {}
    cx = int(cx)
    cy = int(cy)
    size = max(3, int(size or 4))
    line = (96, 118, 136)
    fill = (245, 248, 236)
    empty = (8, 18, 28)

    def diamond(x, y, occupied):
        points = [(x, y - size), (x + size, y), (x, y + size), (x - size, y)]
        draw.polygon(points, fill=fill if occupied else empty, outline=line)

    diamond(cx, cy - size, bool(bases.get("second")))
    diamond(cx - size, cy, bool(bases.get("third")))
    diamond(cx + size, cy, bool(bases.get("first")))
    plate_w = max(2, size - 1)
    draw.line((cx - plate_w, cy + size + 2, cx + plate_w, cy + size + 2), fill=line)


def draw_baseball_bat_marker(draw, cx, y, side):
    cx = int(cx)
    y = int(y)
    barrel = (196, 126, 56)
    highlight = (238, 184, 94)
    edge = (78, 43, 22)
    grip = (128, 74, 36)
    knob = (236, 202, 124)
    if side == "away":
        knob_x = cx - 8
        step = 1
    else:
        knob_x = cx + 8
        step = -1

    def x(offset):
        return knob_x + step * offset

    # Flat horizontal pixel bat: knob, thin handle, constant-thickness barrel.
    draw.rectangle((knob_x - 1, y - 1, knob_x + 1, y + 1), fill=edge)
    draw.point((knob_x, y), fill=knob)

    draw.line((x(1), y, x(5), y), fill=grip)
    draw.point((x(2), y - 1), fill=edge)
    draw.point((x(4), y + 1), fill=edge)

    b1 = x(6)
    b2 = x(16)
    left, right = sorted((b1, b2))
    draw.rectangle((left, y - 2, right, y + 2), fill=edge)
    draw.rectangle((left + 1, y - 1, right - 1, y + 1), fill=barrel)
    draw.line((left + 2, y - 1, right - 2, y - 1), fill=highlight)


def _render_sport_card_128(away, home, away_team, home_team, status, score, status_color, series=None, outs=None, batting_side=None, bases=None, logo_size=28, score_pad=6, regular_triple_score=False):
    from PIL import Image, ImageDraw, ImageFont

    def text_ink_bbox(text, font):
        mask = Image.new("1", (64, 20), 0)
        ImageDraw.Draw(mask).text((0, 0), text, fill=1, font=font)
        return mask.getbbox() or (0, 0, 0, 0)

    def compact_text_width(text, font, spacing_adjust=-1):
        text = str(text or "")
        if not text:
            return 0
        total = 0
        for ch in text:
            bbox = draw.textbbox((0, 0), ch, font=font)
            total += max(0, bbox[2] - bbox[0])
        return max(0, total + spacing_adjust * (len(text) - 1))

    def draw_compact_text(text, x, y, fill, font, spacing_adjust=-1):
        cursor = int(x)
        for ch in str(text or ""):
            draw_sharp_text(image, (cursor, y), ch, fill, font)
            bbox = draw.textbbox((0, 0), ch, font=font)
            cursor += max(0, bbox[2] - bbox[0] + spacing_adjust)

    image = Image.new("RGB", (128, 32), (5, 7, 10))
    draw = ImageDraw.Draw(image)
    try:
        tiny = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        small = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        score_font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 12)
        regular_score_font = ImageFont.truetype("assets/fonts/PixelifySans.ttf", 12)
    except Exception:
        tiny = small = score_font = regular_score_font = ImageFont.load_default()

    draw.rectangle((0, 0, 127, 6), fill=(8, 18, 28))
    status_text = (status or "").upper()
    status_w = draw.textbbox((0, 0), status_text, font=tiny)[2]
    draw_sharp_text(image, ((128 - status_w) // 2, -3), status_text[:30], status_color, tiny)

    logo_size = max(18, min(28, int(logo_size or 28)))
    away_logo = fetch_logo(away_team.get("logo", ""), size=logo_size)
    home_logo = fetch_logo(home_team.get("logo", ""), size=logo_size)
    away_color = parse_color("#" + str(away_team.get("color", "")).lstrip("#")) if away_team.get("color") else (255, 255, 255)
    home_color = parse_color("#" + str(home_team.get("color", "")).lstrip("#")) if home_team.get("color") else (255, 255, 255)
    away_logo_x = 0
    home_logo_x = 128 - logo_size

    if away_logo:
        image.paste(away_logo, (away_logo_x, 0), away_logo)
    else:
        draw.ellipse((1, 1, 1 + logo_size, logo_size), outline=away_color, width=2)
    if home_logo:
        image.paste(home_logo, (home_logo_x, 0), home_logo)
    else:
        draw.ellipse((127 - logo_size, 1, 127, logo_size), outline=home_color, width=2)

    use_regular_score = bool(regular_triple_score and re.search(r"\d{3,}", score or ""))
    if use_regular_score:
        score_font = regular_score_font
    use_segment_score = not use_regular_score and any(ch.isdigit() for ch in score) and _BOLD_NUMERIC_RE.match(score)
    if use_segment_score:
        score_h = bitmap_number_height_for_font(score_font, extra=1)
        sw, sh = bitmap_number_size_for_height(score, score_h)
    else:
        sb = draw.textbbox((0, 0), score, font=score_font)
        sw = sb[2] - sb[0]
    score_pad = max(1, int(score_pad or 6))
    pill_w = max(34, sw + score_pad * 2)
    bx1 = (128 - pill_w) // 2
    bx2 = bx1 + pill_w
    by1, by2 = 8, 24
    draw.rounded_rectangle((bx1, by1, bx2, by2), radius=4, fill=(18, 29, 39), outline=(69, 87, 104))
    if use_segment_score:
        draw_sport_score_number(image, (bx1 + 1, by1, bx2 + 1, by2), score, (247, 251, 255), score_h)
    else:
        text_x = int(round(64 - (sb[0] + sb[2]) / 2)) + 1
        text_y = int(round(((by1 + by2) / 2) - ((sb[1] + sb[3]) / 2)))
        draw_sharp_text(image, (text_x, text_y), score, (247, 251, 255), score_font)
    if outs is not None:
        draw_baseball_out_dots(draw, (bx1 + bx2) // 2, 29, outs, size=2)

    away_rec = get_team_record(away, series)[:8]
    home_rec = get_team_record(home, series)[:8]
    if away_rec:
        draw_sharp_text(image, (18, 22), away_rec, (174, 185, 196), tiny)
    if home_rec:
        hrec_w = draw.textbbox((0, 0), home_rec, font=tiny)[2]
        draw_sharp_text(image, (110 - hrec_w, 22), home_rec, (174, 185, 196), tiny)

    away_abbrev = (away_team.get("abbreviation", "AWY") or "AWY")[:3].upper()
    home_abbrev = (home_team.get("abbreviation", "HME") or "HME")[:3].upper()
    away_w = compact_text_width(away_abbrev, small)
    home_ink = text_ink_bbox(home_abbrev, small)
    away_x = bx1 - 1 - away_w
    home_x = bx2 + 3 - home_ink[0]
    if batting_side == "away":
        away_active_x = max(18, away_x + away_w // 2)
        draw_baseball_bat_marker(draw, away_active_x, 8, "away")
        draw_baseball_diamond(draw, away_active_x, 16, bases, size=3)
    else:
        draw_compact_text(away_abbrev, away_x, 10, (255, 255, 255), small)
    if batting_side == "home":
        home_active_x = min(110, home_x + compact_text_width(home_abbrev, small) // 2)
        draw_baseball_bat_marker(draw, home_active_x, 8, "home")
        draw_baseball_diamond(draw, home_active_x, 16, bases, size=3)
    else:
        draw_compact_text(home_abbrev, home_x, 10, (255, 255, 255), small)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


# ── Flight utilities ──────────────────────────────────────────────────────────

_AIRLINES = {
    "AAL": ("American",    "AA"), "UAL": ("United",      "UA"), "DAL": ("Delta",       "DL"),
    "SWA": ("Southwest",   "WN"), "ASA": ("Alaska",      "AS"), "JBU": ("JetBlue",     "B6"),
    "FFT": ("Frontier",    "F9"), "NKS": ("Spirit",      "NK"), "HAL": ("Hawaiian",    "HA"),
    "SKW": ("SkyWest",     "OO"), "RPA": ("Republic",    "YX"), "FDX": ("FedEx",       "FX"),
    "UPS": ("UPS Air",     "5X"), "GTI": ("Atlas",       "GT"), "SWQ": ("Sun Country", "SY"),
    "ENY": ("Envoy",       "MQ"), "PDT": ("Piedmont",    "PT"), "PSA": ("PSA",         "OH"),
    "WEN": ("Endeavor",    "9E"), "BAW": ("British",     "BA"), "AFR": ("Air France",  "AF"),
    "DLH": ("Lufthansa",   "LH"), "UAE": ("Emirates",    "EK"), "QFA": ("Qantas",      "QF"),
    "ANA": ("ANA",         "NH"), "JAL": ("Japan Air",   "JL"), "KAL": ("Korean Air",  "KE"),
    "CPA": ("Cathay",      "CX"), "SIA": ("Singapore",   "SQ"), "ACA": ("Air Canada",  "AC"),
    "WJA": ("WestJet",     "WS"), "THY": ("Turkish",     "TK"), "IBE": ("Iberia",      "IB"),
    "EZY": ("easyJet",     "U2"), "RYR": ("Ryanair",     "FR"), "KLM": ("KLM",         "KL"),
    "CSN": ("China South", "CZ"), "CCA": ("Air China",   "CA"), "AMX": ("Aeromexico",  "AM"),
    "VOI": ("Volaris",     "Y4"), "TAM": ("LATAM",       "JJ"), "AVA": ("Avianca",     "AV"),
    "GLO": ("GOL",         "G3"), "AZU": ("Azul",        "AD"), "SAS": ("SAS",         "SK"),
    "VLG": ("Vueling",     "VY"), "WZZ": ("Wizz",        "W6"), "EIN": ("Aer Lingus",  "EI"),
    "SWR": ("Swiss",       "LX"), "AUA": ("Austrian",    "OS"), "ETH": ("Ethiopian",   "ET"),
    "QTR": ("Qatar",       "QR"), "SVA": ("Saudia",      "SV"), "AIC": ("Air India",   "AI"),
    "MSR": ("EgyptAir",    "MS"), "TUI": ("TUI",         "BY"), "AEE": ("Aegean",      "A3"),
}

_IATA_TO_ICAO = {iata: icao for icao, (_, iata) in _AIRLINES.items()}
_AIRLINE_LOGO_CACHE = {}
_AIRLINE_LOGO_BASE = "https://raw.githubusercontent.com/bptworld/pixora/main/cards/assets/airlines"
_OPENSKY_TOKEN = {"token": None, "expires": datetime.min.replace(tzinfo=timezone.utc)}


def lookup_airline(callsign):
    prefix = (callsign or "").strip().upper()[:3]
    return _AIRLINES.get(prefix)


def iata_to_icao_prefix(iata):
    return _IATA_TO_ICAO.get((iata or "").upper())


def fetch_airline_logo(iata):
    iata = (iata or "").strip().upper()
    cached = _cache_get(_AIRLINE_LOGO_CACHE, iata)
    if cached is not None or iata in _AIRLINE_LOGO_CACHE:
        return cached
    logo = fetch_logo(f"{_AIRLINE_LOGO_BASE}/{iata}.png")
    if logo is None:
        logo = fetch_logo(f"https://images.kiwi.com/airlines/64/{iata.lower()}.png")
    _cache_put(_AIRLINE_LOGO_CACHE, iata, logo, AIRLINE_LOGO_CACHE_MAX_ENTRIES)
    return logo


def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def compass_dir(lat1, lon1, lat2, lon2):
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(math.radians(lat2))
    y = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) -
         math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dlon))
    deg = math.degrees(math.atan2(x, y)) % 360
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][round(deg / 45) % 8]


def _opensky_token(client_id, client_secret):
    now = datetime.now(timezone.utc)
    if _OPENSKY_TOKEN["token"] and _OPENSKY_TOKEN["expires"] > now:
        return _OPENSKY_TOKEN["token"]
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode()
    req = urllib.request.Request(
        "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Pixora/0.1"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    _OPENSKY_TOKEN["token"] = result["access_token"]
    _OPENSKY_TOKEN["expires"] = now + timedelta(seconds=result.get("expires_in", 1800) - 60)
    return _OPENSKY_TOKEN["token"]


def fetch_opensky(cache, client_id="", client_secret="", lamin=None, lamax=None, lomin=None, lomax=None):
    now = datetime.now(timezone.utc)
    if cache.get("body") and cache.get("expires", now) > now:
        return cache["body"]
    url = "https://opensky-network.org/api/states/all"
    if lamin is not None:
        url += f"?lamin={lamin:.4f}&lamax={lamax:.4f}&lomin={lomin:.4f}&lomax={lomax:.4f}"
    req = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1"})
    if client_id and client_secret:
        try:
            req.add_header("Authorization", f"Bearer {_opensky_token(client_id, client_secret)}")
        except Exception:
            pass
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    cache["body"] = data
    cache["expires"] = now + timedelta(seconds=30)
    return data


def render_flight_image(flight_num, airline_name, iata, alt_ft, speed_kt, line4):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (64, 32), (0, 5, 18))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()
    draw.rectangle((0, 0, 63, 6), fill=(0, 15, 45))
    logo = fetch_airline_logo(iata) if iata else None
    tx = 1
    if logo:
        image.paste(logo, (1, -1), logo)
        tx = 14
    draw_sharp_text(image, (tx, -3), flight_num[:9], (255, 255, 255), bold)
    draw_sharp_text(image, (1, 5), airline_name[:10], (100, 190, 255), font)
    alt_str = f"{alt_ft // 1000}K ft" if alt_ft >= 1000 else f"{alt_ft}ft"
    spd_str = f"{speed_kt}kt"
    draw_sharp_text(image, (1, 13), alt_str, (200, 230, 255), font)
    sw = draw.textbbox((0, 0), spd_str, font=font)[2]
    draw_sharp_text(image, (63 - sw, 13), spd_str, (200, 230, 255), font)
    draw_sharp_text(image, (1, 21), line4[:14], (150, 200, 255), font)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
