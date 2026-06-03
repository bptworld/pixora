from datetime import datetime, timedelta, timezone
from io import BytesIO
import html as html_lib
import json
import re
import urllib.parse
import urllib.request
from card_utils import draw_sharp_text, render_text_webp

_STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota",
    "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin",
    "WY": "Wyoming",
}

CARD_ID = "gas_price_local"
CARD_NAME = "Gas Price Local"
CARD_DETAIL = "AAA local gas average"
CARD_OPTIONS = [
    {"key": "zipCode", "label": "ZIP Code", "type": "text", "default": "02134", "maxlength": 5, "inputmode": "numeric"},
    {
        "key": "state",
        "label": "State Fallback",
        "type": "select",
        "default": "MA",
        "choices": [{"value": code, "label": name} for code, name in _STATE_NAMES.items()],
    },
]

_CACHE = {}


def _zip_location(zip_code):
    zip_code = re.sub(r"\D", "", zip_code or "")[:5]
    if len(zip_code) != 5:
        return None
    now = datetime.now(timezone.utc)
    key = f"zip:{zip_code}"
    cached = _CACHE.get(key)
    if cached and cached["expires"] > now:
        return cached["data"]
    req = urllib.request.Request(
        f"https://api.zippopotam.us/us/{zip_code}",
        headers={"User-Agent": "Pixora/0.1", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    place = data["places"][0]
    lat = place.get("latitude", "")
    lon = place.get("longitude", "")
    loc = {
        "zip": zip_code,
        "city": place.get("place name", ""),
        "state": place.get("state abbreviation", ""),
        "cities": [place.get("place name", "")],
    }
    try:
        query = urllib.parse.urlencode({"lat": lat, "lon": lon, "format": "jsonv2", "zoom": "10"})
        rev_req = urllib.request.Request(
            f"https://nominatim.openstreetmap.org/reverse?{query}",
            headers={"User-Agent": "Pixora/0.1", "Accept": "application/json"},
        )
        with urllib.request.urlopen(rev_req, timeout=10) as resp:
            address = json.loads(resp.read().decode("utf-8")).get("address", {})
        for key in ("city", "town", "village", "municipality", "county"):
            val = address.get(key, "")
            if val and val not in loc["cities"]:
                loc["cities"].append(val)
    except Exception:
        pass
    _CACHE[key] = {"data": loc, "expires": now + timedelta(days=7)}
    return loc


def _normalize_name(value):
    value = html_lib.unescape(re.sub(r"<[^>]+>", "", value or ""))
    value = re.sub(r"\([^)]*\)", "", value)
    value = value.replace(",", " ").replace("-", " ")
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _metro_prices(html):
    prices = []
    for match in re.finditer(r'<h3[^>]*data-cost="([0-9.]+)"[^>]*>(.*?)</h3>', html, re.I | re.S):
        name = html_lib.unescape(re.sub(r"<[^>]+>", "", match.group(2))).strip()
        prices.append({"name": name, "price": float(match.group(1))})
    return prices


def _best_local_match(location, metros):
    cities = [_normalize_name(c) for c in location.get("cities", []) if c]
    if not cities:
        cities = [_normalize_name(location.get("city", ""))]
    cities = [c for c in cities if c]
    if not cities:
        return None
    best = None
    best_score = 0
    for metro in metros:
        metro_norm = _normalize_name(metro["name"])
        score = 0
        for city in cities:
            city_words = [w for w in city.split() if len(w) > 2]
            if city and city in metro_norm:
                score += 10
            score += sum(1 for word in city_words if word in metro_norm)
        if score > best_score:
            best = metro
            best_score = score
    return best if best_score else None


def _fetch(state, zip_code=""):
    state = re.sub(r"[^A-Za-z]", "", state or "MA").upper()[:2] or "MA"
    location = None
    try:
        location = _zip_location(zip_code)
        if location and location.get("state"):
            state = location["state"].upper()
    except Exception:
        location = None

    now = datetime.now(timezone.utc)
    cache_key = f"gas:{state}:{(location or {}).get('zip', '')}"
    cached = _CACHE.get(cache_key)
    if cached and cached["expires"] > now:
        return cached["data"]
    url = f"https://gasprices.aaa.com/?state={state}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://gasprices.aaa.com/",
        "Connection": "close",
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    state_name = _STATE_NAMES.get(state, state)
    state_match = re.search(rf"Today's AAA\s+{re.escape(state_name)} Avg\.\s+\$([0-9.]+)", html)
    national_match = re.search(r"Today.s AAA National Average\s+\$([0-9.]+)", html)
    date_match = re.search(r"Price as of\s+([0-9/]+)", html)
    metros = _metro_prices(html)
    local = _best_local_match(location or {}, metros)
    data = {
        "state": state,
        "state_name": state_name,
        "location": local["name"] if local else state,
        "local": bool(local),
        "price": local["price"] if local else (float(state_match.group(1)) if state_match else None),
        "national": float(national_match.group(1)) if national_match else None,
        "date": date_match.group(1) if date_match else "",
    }
    _CACHE[cache_key] = {"data": data, "expires": now + timedelta(hours=6)}
    return data


def _is_wide(options):
    return (options or {}).get("_target") == "matrixportal-s3-128x32"


def _render_text_image(text, color, width=64):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (width, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    draw_sharp_text(image, ((width - (bbox[2] - bbox[0])) // 2, (32 - (bbox[3] - bbox[1])) // 2), text, color, font)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    width = 128 if _is_wide(opts) else 64
    try:
        data = _fetch(opts.get("state") or "MA", opts.get("zipCode") or "")
    except Exception:
        return _render_text_image("GAS ERR", (238, 80, 80), width)
    if data["price"] is None:
        return _render_text_image("NO GAS", (160, 160, 160), width)

    diff = data["price"] - (data["national"] or data["price"])
    color = (238, 80, 80) if diff > 0 else (80, 220, 120)
    image = Image.new("RGB", (width, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    header = data["location"][:9].upper() if data.get("local") else f"GAS {data['state']}"
    price = f"${data['price']:.2f}"
    tag = f"{diff:+.2f} vs US"
    if width == 128:
        draw.rectangle((4, 8, 18, 27), outline=(90, 170, 255), fill=(8, 18, 30))
        draw.rectangle((8, 11, 14, 15), fill=(90, 170, 255))
        draw.line((18, 12, 25, 17, 25, 25), fill=(90, 170, 255))
        header = (data["location"][:18].upper() if data.get("local") else f"GAS {data['state']}")
        draw_sharp_text(image, (31, -3), header, (255, 220, 80), bold)
        draw_sharp_text(image, (31, 8), price, (235, 245, 255), bold)
        tw = draw.textbbox((0, 0), tag, font=font)[2]
        draw_sharp_text(image, (width - tw - 3, 20), tag, color, font)
    else:
        draw.rectangle((2, 9, 12, 25), outline=(90, 170, 255), fill=(8, 18, 30))
        draw.rectangle((5, 12, 9, 15), fill=(90, 170, 255))
        draw.line((12, 12, 17, 16, 17, 23), fill=(90, 170, 255))
        draw_sharp_text(image, (20, -3), header, (255, 220, 80), bold)
        draw_sharp_text(image, (20, 8), price, (235, 245, 255), bold)
        draw_sharp_text(image, (20, 20), tag[:10], color, font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
