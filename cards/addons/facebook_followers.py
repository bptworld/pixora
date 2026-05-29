from card_utils import fetch_json_with_headers, render_counter_card, render_text_webp

CARD_ID = "facebook_followers"
CARD_NAME = "Facebook Followers"
CARD_DETAIL = "Page followers via Graph API"
CARD_OPTIONS = [
    {"key": "pageId", "label": "Page ID or Username", "type": "text", "default": "", "maxlength": 80},
    {"key": "accessToken", "label": "Graph API Token", "type": "password", "default": ""},
]


def render(options=None):
    opts = options or {}
    page_id = (opts.get("pageId") or "").strip()
    token = (opts.get("accessToken") or "").strip()
    if not page_id or not token:
        return render_text_webp("SET FB", (100, 180, 255))
    url = f"https://graph.facebook.com/v19.0/{page_id}?fields=name,followers_count,fan_count&access_token={token}"
    try:
        data = fetch_json_with_headers(url, seconds=1800, cache_key=f"fb:{page_id}")
        count = data.get("followers_count") or data.get("fan_count")
        label = data.get("name") or page_id
    except Exception:
        return render_text_webp("FB ERR", (238, 80, 80))
    return render_counter_card("FACEBOOK", label, count, (24, 119, 242), "FOLLOW", "facebook", opts.get("_target"))
