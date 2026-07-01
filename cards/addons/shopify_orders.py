from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import re
import urllib.parse
import urllib.error
import urllib.request

from card_utils import _settings_value, draw_sharp_text, format_compact_number, pixora_local_now, render_text_webp

CARD_ID = "shopify_orders"
CARD_NAME = "Shopify Orders"
CARD_DETAIL = "Orders this week and all time"
CARD_OPTIONS = []
CARD_RULE_FIELDS = [
    {"id": "orders_this_week", "label": "Orders This Week"},
    {"id": "orders_all_time", "label": "Orders All Time"},
]

_CACHE = {}
_TOKEN_CACHE = {}
API_VERSION = "2026-04"


def _option(opts, key):
    value = str((opts or {}).get(key) or "").strip()
    if key == "shopDomain" and value.lower() in ("your-store", "your-store.myshopify.com"):
        value = ""
    if value:
        return value
    setting_key = "shopify" + key[:1].upper() + key[1:]
    return str(_settings_value(setting_key, "") or "").strip()


def _shop_domain(value):
    text = str(value or "").strip().lower()
    text = re.sub(r"^https?://", "", text).split("/", 1)[0].strip()
    if text in ("your-store", "your-store.myshopify.com"):
        return ""
    if text and "." not in text:
        text += ".myshopify.com"
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,80}", text or ""):
        return ""
    return text


def _is_app_automation_token(token):
    return str(token or "").strip().lower().startswith("atkn_")


def _client_credentials_token(shop_domain, client_id, client_secret):
    cache_key = f"{shop_domain}:{client_id[:8]}:{client_secret[:8]}"
    now = datetime.now(timezone.utc)
    cached = _TOKEN_CACHE.get(cache_key)
    if cached and cached.get("expires", now) > now and cached.get("access_token"):
        return cached["access_token"]
    form = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://{shop_domain}/admin/oauth/access_token",
        data=form,
        method="POST",
        headers={
            "User-Agent": "Pixora/0.1",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = ""
        try:
            raw = error.read().decode("utf-8", "replace")
        except Exception:
            pass
        raise RuntimeError(f"Shopify token HTTP {error.code}: {raw or error.reason or 'token request failed'}") from error
    access_token = str(data.get("access_token") or "").strip()
    if not access_token:
        raise RuntimeError("Shopify token response did not include access_token")
    try:
        expires_in = int(data.get("expires_in") or 86400)
    except Exception:
        expires_in = 86400
    _TOKEN_CACHE[cache_key] = {
        "access_token": access_token,
        "expires": now + timedelta(seconds=max(60, expires_in - 120)),
        "scope": str(data.get("scope") or ""),
    }
    return access_token


def _admin_access_token(shop_domain, opts):
    direct = _option(opts, "accessToken")
    client_id = _option(opts, "clientId")
    client_secret = _option(opts, "clientSecret")
    if direct and not _is_app_automation_token(direct):
        return direct
    if client_id and client_secret:
        return _client_credentials_token(shop_domain, client_id, client_secret)
    if direct and _is_app_automation_token(direct):
        raise ValueError("Shopify App Automation Token cannot read Admin API data. Use Client ID and Client Secret.")
    return ""


def _week_start_utc():
    local_now = pixora_local_now()
    start = local_now - timedelta(days=local_now.weekday())
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _graphql(shop_domain, token, query, variables=None):
    url = f"https://{shop_domain}/admin/api/{API_VERSION}/graphql.json"
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "User-Agent": "Pixora/0.1",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": token,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = ""
        try:
            raw = error.read().decode("utf-8", "replace")
        except Exception:
            pass
        raise RuntimeError(f"HTTP {error.code}: {raw or error.reason or 'Shopify request failed'}") from error
    if data.get("errors"):
        message = "; ".join(str(item.get("message") or item) for item in data.get("errors") or [])
        raise RuntimeError(message or "Shopify GraphQL error")
    return data.get("data") or {}


def _error_card(opts, error):
    text = str(error or "")
    upper = text.upper()
    logger = (opts or {}).get("_log")
    if callable(logger):
        try:
            logger(f"[shopify_orders] {text}")
        except Exception:
            pass
    if "MISSING SHOPIFY SETTINGS" in upper:
        return render_text_webp("SET SHOP", (95, 180, 255))
    if "APP AUTOMATION TOKEN" in upper:
        return render_text_webp("SHOP TOKEN", (238, 160, 70))
    if "TOKEN HTTP" in upper or "CLIENT_CREDENTIALS" in upper or "CLIENT ID" in upper or "CLIENT SECRET" in upper:
        return render_text_webp("SHOP AUTH", (238, 80, 80))
    if "HTTP 404" in upper or "NOT FOUND" in upper:
        return render_text_webp("SHOP URL", (238, 80, 80))
    if "HTTP 401" in upper or "HTTP 403" in upper or "INVALID API KEY" in upper or "ACCESS TOKEN" in upper:
        return render_text_webp("SHOP AUTH", (238, 80, 80))
    if "READ_ORDERS" in upper or "ACCESS DENIED" in upper or "SCOPE" in upper:
        return render_text_webp("SHOP SCOPE", (238, 160, 70))
    return render_text_webp("SHOP ERR", (238, 80, 80))


def _counts(opts):
    shop_domain = _shop_domain(_option(opts, "shopDomain"))
    token = _admin_access_token(shop_domain, opts) if shop_domain else ""
    if not shop_domain or not token:
        raise ValueError("missing Shopify settings")
    cache_key = f"{shop_domain}:{token[:8]}:{_week_start_utc()}"
    now = datetime.now(timezone.utc)
    cached = _CACHE.get(cache_key)
    if cached and cached["expires"] > now:
        return cached["data"]
    data = _graphql(
        shop_domain,
        token,
        """
        query PixoraShopifyOrders($weekQuery: String!) {
          ordersThisWeek: ordersCount(query: $weekQuery, limit: null) {
            count
            precision
          }
          ordersAllTime: ordersCount(limit: null) {
            count
            precision
          }
        }
        """,
        {"weekQuery": f"processed_at:>={_week_start_utc()}"},
    )
    counts = {
        "orders_this_week": int(((data.get("ordersThisWeek") or {}).get("count")) or 0),
        "orders_all_time": int(((data.get("ordersAllTime") or {}).get("count")) or 0),
        "week_precision": str(((data.get("ordersThisWeek") or {}).get("precision")) or ""),
        "all_precision": str(((data.get("ordersAllTime") or {}).get("precision")) or ""),
    }
    _CACHE[cache_key] = {"data": counts, "expires": now + timedelta(seconds=300)}
    return counts


def rule_value(options=None, field=""):
    data = _counts(options or {})
    key = str(field or "orders_this_week").strip()
    return data.get(key, "")


def _card_label(opts, width):
    label = _option(opts, "cardLabel") or "SHOPIFY"
    label = re.sub(r"\s+", " ", str(label or "")).strip().upper() or "SHOPIFY"
    limit = 18 if width == 128 else 10
    return label[:limit]


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    shop_domain = _shop_domain(_option(opts, "shopDomain"))
    if not shop_domain:
        return render_text_webp("SET SHOP", (95, 180, 255))
    try:
        counts = _counts(opts)
    except Exception as error:
        return _error_card(opts, error)

    image = Image.new("RGB", (width, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 15)
    except Exception:
        font = bold = big = ImageFont.load_default()

    draw.rectangle((0, 0, width - 1, 6), fill=(6, 22, 26))
    title = _card_label(opts, width)
    while title and draw.textbbox((0, 0), title, font=bold)[2] > width - 2:
        title = title[:-1]
    draw_sharp_text(image, (1, -3), title or "SHOP", (70, 220, 140), bold)

    week = format_compact_number(counts.get("orders_this_week"))
    total = format_compact_number(counts.get("orders_all_time"))
    if width == 128:
        draw_sharp_text(image, (5, 8), "WEEK", (150, 170, 185), font)
        draw_sharp_text(image, (5, 17), week, (245, 250, 255), big)
        draw.line((64, 10, 64, 28), fill=(35, 70, 75))
        draw_sharp_text(image, (72, 8), "ALL", (150, 170, 185), font)
        draw_sharp_text(image, (72, 17), total, (245, 250, 255), big)
    else:
        draw_sharp_text(image, (2, 8), "WK", (150, 170, 185), font)
        ww = draw.textbbox((0, 0), week, font=bold)[2]
        draw_sharp_text(image, (62 - ww, 7), week, (245, 250, 255), bold)
        draw_sharp_text(image, (2, 20), "ALL", (150, 170, 185), font)
        aw = draw.textbbox((0, 0), total, font=bold)[2]
        draw_sharp_text(image, (62 - aw, 19), total, (245, 250, 255), bold)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()
