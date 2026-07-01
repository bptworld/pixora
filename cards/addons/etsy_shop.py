from io import BytesIO
from datetime import datetime, timedelta, timezone
import json
import urllib.parse
import urllib.error
import urllib.request

from card_utils import (
    _settings_value,
    draw_sharp_text,
    format_compact_number,
    pixora_local_now,
)

CARD_ID = "etsy_shop"
CARD_NAME = "Etsy Shop Pulse"
CARD_DETAIL = "Orders and shop stats from Etsy"
CARD_OPTIONS = [
    {"key": "shopId", "label": "Shop ID", "type": "text", "default": "", "maxlength": 32},
    {"key": "apiKey", "label": "Etsy API Key", "type": "hidden", "default": ""},
    {"key": "apiSecret", "label": "Etsy Shared Secret", "type": "hidden", "default": ""},
    {"key": "accessToken", "label": "OAuth Bearer Token", "type": "password", "default": ""},
    {"key": "refreshToken", "label": "OAuth Refresh Token", "type": "hidden", "default": ""},
    {
        "key": "view",
        "label": "View",
        "type": "select",
        "default": "pulse",
        "choices": [
            {"value": "pulse", "label": "Shop Pulse"},
            {"value": "today", "label": "Today's Orders + Revenue"},
            {"value": "week", "label": "Weekly Orders + Revenue"},
            {"value": "scroller", "label": "Scroller: New Order with Title"},
        ],
    },
]

_STATE = {}
_TOKEN_CACHE = {}
_SHOP_ID_CACHE = {}
_API_CACHE = {}


def _option(opts, key, setting_key=None):
    value = str((opts or {}).get(key) or "").strip()
    if value:
        return value
    if key == "apiKey":
        from os import environ
        value = str(environ.get("PIXORA_ETSY_API_KEY") or "").strip()
        if value:
            return value
    if key == "apiSecret":
        from os import environ
        value = str(environ.get("PIXORA_ETSY_SHARED_SECRET") or "").strip()
        if value:
            return value
    return str(_settings_value(setting_key or f"etsy{key[:1].upper()}{key[1:]}", "") or "").strip()


def _headers(opts):
    api_key = _option(opts, "apiKey")
    api_secret = _option(opts, "apiSecret")
    token = _option(opts, "accessToken")
    refresh_token = _option(opts, "refreshToken")
    if not api_key:
        return None
    if refresh_token:
        token = _refresh_access_token(api_key, refresh_token) or token
    x_api_key = f"{api_key}:{api_secret}" if api_secret else api_key
    headers = {"x-api-key": x_api_key}
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


def _refresh_access_token(api_key, refresh_token):
    from datetime import timedelta
    import json
    import urllib.request

    key = f"{api_key}:{refresh_token}"
    cached = _TOKEN_CACHE.get(key)
    now = datetime.now(timezone.utc)
    if cached and cached.get("expires", now) > now:
        return cached.get("access")
    try:
        form = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "client_id": api_key,
            "refresh_token": refresh_token,
        }).encode("utf-8")
        request = urllib.request.Request(
            "https://api.etsy.com/v3/public/oauth/token",
            data=form,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))
        access = data.get("access_token") or ""
        if access:
            expires = now + timedelta(seconds=max(60, int(data.get("expires_in") or 3600) - 60))
            _TOKEN_CACHE[key] = {"access": access, "expires": expires}
            return access
    except Exception:
        pass
    return ""


def _api_get(path, opts, params=None, seconds=120, cache_suffix=""):
    headers = _headers(opts)
    if not headers:
        raise ValueError("missing Etsy API key")
    base = "https://api.etsy.com/v3/application/"
    query = urllib.parse.urlencode(params or {})
    url = base + path.lstrip("/")
    if query:
        url += "?" + query
    cache_key = f"etsy:{path}:{query}:{cache_suffix}:{bool(headers.get('Authorization'))}"
    now = datetime.now(timezone.utc)
    cached = _API_CACHE.get(cache_key)
    if cached and cached.get("expires", now) > now:
        return cached.get("data")
    request_headers = {"User-Agent": "Pixora/0.1", "Accept": "application/json"}
    request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = ""
        try:
            raw = error.read().decode("utf-8", "replace")
        except Exception:
            pass
        if cached and "data" in cached:
            return cached["data"]
        raise RuntimeError(
            f"Etsy {path} HTTP {error.code}: {raw or error.reason or 'request failed'}"
        ) from error
    except Exception:
        if cached and "data" in cached:
            return cached["data"]
        raise
    _API_CACHE[cache_key] = {
        "expires": now + timedelta(seconds=max(1, int(seconds or 120))),
        "data": data,
    }
    return data


def _normalize_shop_name(value):
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())


def _resolve_shop_id(shop_id, opts):
    shop_id = str(shop_id or "").strip()
    if shop_id.isdigit():
        return shop_id
    headers = _headers(opts)
    token = str(headers.get("Authorization", "") if headers else "").replace("Bearer ", "", 1).strip()
    user_id = token.split(".", 1)[0] if token else ""
    if not user_id.isdigit():
        return shop_id
    cache_key = f"{user_id}:{shop_id}"
    cached = _SHOP_ID_CACHE.get(cache_key)
    now = datetime.now(timezone.utc)
    if cached and cached.get("expires", now) > now:
        return cached.get("shop_id") or shop_id
    data = _api_get(f"users/{user_id}/shops", opts, seconds=300, cache_suffix=user_id)
    shops = data.get("results") if isinstance(data, dict) else data
    shops = shops or []
    wanted = _normalize_shop_name(shop_id)
    chosen = None
    for shop in shops:
        if _normalize_shop_name(shop.get("shop_name") or shop.get("shopName") or shop.get("name")) == wanted:
            chosen = shop
            break
    if not chosen and len(shops) == 1:
        chosen = shops[0]
    if not chosen:
        data = _api_get("shops", opts, params={"shop_name": shop_id}, seconds=300, cache_suffix=shop_id)
        shop_results = data.get("results") if isinstance(data, dict) else data
        for shop in shop_results or []:
            if _normalize_shop_name(shop.get("shop_name") or shop.get("shopName") or shop.get("name")) == wanted:
                chosen = shop
                break
        if not chosen and len(shop_results or []) == 1:
            chosen = shop_results[0]
    resolved = str((chosen or {}).get("shop_id") or (chosen or {}).get("shopId") or shop_id)
    _SHOP_ID_CACHE[cache_key] = {"shop_id": resolved, "expires": now + timedelta(seconds=300)}
    return resolved


def _safe_log(opts, message):
    logger = (opts or {}).get("_log")
    if callable(logger):
        try:
            logger(message)
        except Exception:
            pass


def _error_card(opts, error):
    text = str(error or "")
    upper = text.upper()
    _safe_log(opts, "[etsy_shop] " + text)
    if "SHARED SECRET" in upper or "INVALID API CREDENTIALS" in upper or "KEYSTRING:SECRET" in upper:
        return _text_card(opts, "ETSY KEY", (238, 80, 80))
    if "401" in text or "403" in text or "UNAUTHORIZED" in upper or "FORBIDDEN" in upper:
        return _text_card(opts, "ETSY AUTH", (238, 80, 80))
    if "404" in text or "NOT FOUND" in upper:
        return _text_card(opts, "SHOP ERR", (238, 80, 80))
    if "EXPECTED INT" in upper or "SHOP_ID" in upper:
        return _text_card(opts, "SHOP ID", (238, 80, 80))
    if "429" in text:
        return _text_card(opts, "ETSY RATE", (238, 160, 70))
    return _text_card(opts, "ETSY ERR", (238, 80, 80))


def _money_value(value):
    if not isinstance(value, dict):
        return None, ""
    try:
        amount = float(value.get("amount") or 0)
        divisor = float(value.get("divisor") or 100)
        currency = str(value.get("currency_code") or "").upper()
        return amount / max(1, divisor), currency
    except Exception:
        return None, ""


def _receipt_total(receipt):
    for key in ("grandtotal", "total_price", "total"):
        amount, currency = _money_value(receipt.get(key) if isinstance(receipt, dict) else None)
        if amount is not None:
            return amount, currency
    return None, ""


def _receipt_timestamp(receipt):
    if not isinstance(receipt, dict):
        return None
    for key in ("created_timestamp", "create_timestamp", "created", "create_date"):
        try:
            value = int(receipt.get(key) or 0)
        except Exception:
            value = 0
        if value > 0:
            return datetime.fromtimestamp(value, timezone.utc)
    return None


def _receipt_id(receipt):
    if not isinstance(receipt, dict):
        return ""
    return str(receipt.get("receipt_id") or receipt.get("receiptId") or receipt.get("id") or "")


def _receipt_status(receipt):
    if not isinstance(receipt, dict):
        return ""
    if receipt.get("status"):
        return str(receipt.get("status"))
    if receipt.get("is_paid") or receipt.get("was_paid"):
        return "paid"
    if receipt.get("is_shipped") or receipt.get("was_shipped"):
        return "completed"
    return "open"


def _shop_receipts(shop_id, opts):
    params = {
        "limit": 100,
        "offset": 0,
        "sort_on": "created",
        "sort_order": "down",
    }
    data = _api_get(f"shops/{shop_id}/receipts", opts, params=params, seconds=120, cache_suffix=shop_id)
    if isinstance(data, dict):
        return data.get("results") or data.get("receipts") or []
    if isinstance(data, list):
        return data
    return []


def _shop_info(shop_id, opts):
    try:
        return _api_get(f"shops/{shop_id}", opts, seconds=300, cache_suffix=shop_id)
    except Exception:
        return {}


def _etsy_data(opts):
    shop_id = _option(opts, "shopId")
    if not shop_id:
        raise ValueError("missing shop ID")
    resolved_shop_id = _resolve_shop_id(shop_id, opts)
    shop = _shop_info(resolved_shop_id, opts)
    receipts = _shop_receipts(resolved_shop_id, opts)
    paid = 0
    open_orders = 0
    for receipt in receipts:
        status = _receipt_status(receipt).lower()
        if status == "paid" or receipt.get("was_paid") or receipt.get("is_paid"):
            paid += 1
        if status in ("open", "paid", "payment processing"):
            open_orders += 1
    newest = receipts[0] if receipts else {}
    total, currency = _receipt_total(newest)
    now_local = pixora_local_now()
    today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now_local - timedelta(days=7)
    today_orders, today_revenue, today_currency = _period_totals(receipts, today_start)
    week_orders, week_revenue, week_currency = _period_totals(receipts, week_start)
    return {
        "shop_id": shop_id,
        "resolved_shop_id": resolved_shop_id,
        "shop": shop if isinstance(shop, dict) else {},
        "receipts": receipts,
        "paid": paid,
        "open": open_orders,
        "newest": newest,
        "newest_id": _receipt_id(newest),
        "newest_total": total,
        "newest_currency": currency,
        "newest_title": _receipt_title(newest),
        "today_orders": today_orders,
        "today_revenue": today_revenue,
        "today_currency": today_currency or currency or str((shop or {}).get("currency_code") or "").upper(),
        "week_orders": week_orders,
        "week_revenue": week_revenue,
        "week_currency": week_currency or currency or str((shop or {}).get("currency_code") or "").upper(),
    }


def _period_totals(receipts, since_local):
    orders = 0
    revenue = 0.0
    currency = ""
    since_utc = since_local.astimezone(timezone.utc)
    for receipt in receipts:
        created = _receipt_timestamp(receipt)
        if not created or created < since_utc:
            continue
        if not (receipt.get("is_paid") or str(receipt.get("status") or "").lower() in ("paid", "completed")):
            continue
        total, item_currency = _receipt_total(receipt)
        orders += 1
        if total is not None:
            revenue += total
        if item_currency:
            currency = item_currency
    return orders, revenue, currency


def _receipt_title(receipt):
    if not isinstance(receipt, dict):
        return ""
    transactions = receipt.get("transactions") or []
    if transactions and isinstance(transactions[0], dict):
        return str(transactions[0].get("title") or transactions[0].get("listing_title") or "").strip()
    return str(receipt.get("title") or receipt.get("listing_title") or "").strip()


def _money_text(amount, currency=""):
    prefix = "$" if str(currency or "").upper() == "USD" else (str(currency or "").upper() + " " if currency else "")
    if amount >= 1000:
        return f"{prefix}{amount / 1000:.1f}K"
    return f"{prefix}{amount:.0f}" if amount == int(amount) else f"{prefix}{amount:.2f}"


def _font(name, size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(name, size)
    except Exception:
        return ImageFont.load_default()


def _display_width(opts):
    return 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64


def _text_card(opts, text, color):
    from PIL import Image, ImageDraw

    width = _display_width(opts)
    image = Image.new("RGB", (width, 32), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = _font("assets/fonts/Silkscreen-Regular.ttf", 8)
    bbox = draw.textbbox((0, 0), text, font=font)
    draw_sharp_text(
        image,
        ((width - (bbox[2] - bbox[0])) // 2, (32 - (bbox[3] - bbox[1])) // 2),
        text,
        color,
        font,
    )
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def _new_order_animation(data, opts):
    from PIL import Image, ImageDraw

    width = _display_width(opts)
    font = _font("assets/fonts/Silkscreen-Regular.ttf", 8)
    bold = _font("assets/fonts/PixelifySans-Bold.ttf", 8)
    frames = []
    durations = []
    total = data.get("newest_total")
    currency = data.get("newest_currency") or ""
    amount = f"{currency} {total:.2f}" if total is not None else "ORDER"
    for show in (True, False, True, False, True, True):
        image = Image.new("RGB", (width, 32), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width - 1, 31), outline=(245, 115, 35))
        if show:
            title = "NEW ORDER"
            tw = draw.textbbox((0, 0), title, font=bold)[2]
            draw_sharp_text(image, ((width - tw) // 2, 3), title, (255, 170, 75), bold)
            aw = draw.textbbox((0, 0), amount, font=font)[2]
            draw_sharp_text(image, ((width - aw) // 2, 17), amount, (245, 250, 255), font)
        frames.append(image)
        durations.append(260 if show else 150)
    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=durations, loop=1, lossless=True, quality=100)
    return out.getvalue()


def _scroll_title_card(data, opts):
    from PIL import Image, ImageDraw

    width = _display_width(opts)
    font = _font("assets/fonts/Silkscreen-Regular.ttf", 8)
    bold = _font("assets/fonts/PixelifySans-Bold.ttf", 8)
    orange = (245, 112, 35)
    white = (245, 250, 255)
    muted = (180, 145, 120)
    title = (data.get("newest_title") or "New Order")[:90]
    total = data.get("newest_total")
    amount = _money_text(total, data.get("newest_currency")) if total is not None else ""
    message = f"NEW ORDER  {title}"
    if amount:
        message += f"  {amount}"
    text_w = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), message, font=font)[2]
    frames = []
    for x in range(width, -text_w - 8, -3):
        image = Image.new("RGB", (width, 32), (8, 5, 2))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width - 1, 8), fill=(26, 12, 4))
        draw_sharp_text(image, (2, -3), "ETSY", orange, bold)
        draw_sharp_text(image, (width - 38, -3), amount[:7] if amount else "ORDER", muted, font)
        draw_sharp_text(image, (x, 14), message, white, font)
        frames.append(image)
    if not frames:
        frames.append(Image.new("RGB", (width, 32), (8, 5, 2)))
    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=45, loop=0, lossless=True, quality=100)
    return out.getvalue()


def _draw_row(image, text, value, y, color, font, value_font=None):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    value_font = value_font or font
    draw_sharp_text(image, (2, y), text, color, font)
    value = str(value)
    vw = draw.textbbox((0, 0), value, font=value_font)[2]
    draw_sharp_text(image, (image.width - vw - 2, y), value, (245, 250, 255), value_font)


def _render_card(data, opts):
    from PIL import Image, ImageDraw

    width = _display_width(opts)
    view = str(opts.get("view") or "pulse").lower()
    image = Image.new("RGB", (width, 32), (8, 5, 2))
    draw = ImageDraw.Draw(image)
    font = _font("assets/fonts/Silkscreen-Regular.ttf", 8)
    bold = _font("assets/fonts/PixelifySans-Bold.ttf", 8)
    big = _font("assets/fonts/PixelifySans-Bold.ttf", 16)
    orange = (245, 112, 35)
    muted = (180, 145, 120)
    white = (245, 250, 255)
    green = (65, 220, 155)

    draw.rectangle((0, 0, width - 1, 8), fill=(26, 12, 4))
    title = "ETSY"
    draw_sharp_text(image, (2, -3), title, orange, bold)
    shop = data.get("shop") or {}
    name = str(shop.get("shop_name") or shop.get("shopName") or "").upper()
    if width == 128 and name:
        name = name[:14]
        nw = draw.textbbox((0, 0), name, font=font)[2]
        draw_sharp_text(image, (width - nw - 2, -3), name, muted, font)

    if view == "today":
        orders = data.get("today_orders") or 0
        revenue = _money_text(float(data.get("today_revenue") or 0), data.get("today_currency"))
        heading = "TODAY"
        draw_sharp_text(image, (2, 9), heading, muted, font)
        value = f"{orders} ORD" if width == 128 else str(orders)
        tw = draw.textbbox((0, 0), value, font=big)[2]
        draw_sharp_text(image, ((width - tw) // 2, 8), value, white, big)
        bw = draw.textbbox((0, 0), revenue, font=font)[2]
        draw_sharp_text(image, ((width - bw) // 2, 22), revenue, green, font)
    elif view == "week":
        orders = data.get("week_orders") or 0
        revenue = _money_text(float(data.get("week_revenue") or 0), data.get("week_currency"))
        heading = "7 DAY"
        draw_sharp_text(image, (2, 9), heading, muted, font)
        value = f"{orders} ORD" if width == 128 else str(orders)
        tw = draw.textbbox((0, 0), value, font=big)[2]
        draw_sharp_text(image, ((width - tw) // 2, 8), value, white, big)
        bw = draw.textbbox((0, 0), revenue, font=font)[2]
        draw_sharp_text(image, ((width - bw) // 2, 22), revenue, green, font)
    else:
        admirers = shop.get("num_favorers") or shop.get("num_favorites") or shop.get("favorite_count") or 0
        sales = shop.get("transaction_sold_count") or shop.get("sales_count") or 0
        if width == 128:
            _draw_row(image, "ADMIRERS:", format_compact_number(admirers), 10, muted, font)
            _draw_row(image, "SALES:", str(sales), 21, muted, font)
        else:
            _draw_row(image, "ADM:", str(int(admirers or 0)), 10, muted, font)
            _draw_row(image, "SALE:", str(int(sales or 0)), 21, muted, font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def render(options=None):
    opts = options or {}
    shop_id = _option(opts, "shopId")
    if not shop_id:
        return _text_card(opts, "SET ETSY", (245, 112, 35))
    if not _headers(opts):
        return _text_card(opts, "ETSY KEY", (245, 112, 35))
    if not _option(opts, "accessToken") and not _option(opts, "refreshToken"):
        return _text_card(opts, "ETSY TOK", (245, 112, 35))
    try:
        data = _etsy_data(opts)
    except Exception as error:
        return _error_card(opts, error)

    key = f"{opts.get('_device_id', 'local')}:{shop_id}"
    newest_id = data.get("newest_id")
    previous = _STATE.get(key)
    _STATE[key] = {"newest_id": newest_id, "seen": datetime.now(timezone.utc)}
    if str(opts.get("view") or "pulse").lower() == "scroller":
        return _scroll_title_card(data, opts)
    body = _render_card(data, opts)
    if previous and newest_id and newest_id != previous.get("newest_id"):
        return {
            "body": _new_order_animation(data, opts),
            "dwell_secs": 6,
            "_stay": False,
            "_no_replay": True,
        }
    return body
