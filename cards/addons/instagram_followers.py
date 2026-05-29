from card_utils import fetch_json_with_headers, render_counter_card, render_text_webp

CARD_ID = "instagram_followers"
CARD_NAME = "Instagram Followers"
CARD_DETAIL = "Follower count via Instagram Graph"
CARD_OPTIONS = [
    {"key": "igUserId", "label": "Instagram Business User ID", "type": "text", "default": "", "maxlength": 80},
    {"key": "accessToken", "label": "Graph API Token", "type": "password", "default": ""},
]


def render(options=None):
    opts = options or {}
    ig_id = (opts.get("igUserId") or "").strip()
    token = (opts.get("accessToken") or "").strip()
    if not ig_id or not token:
        return render_text_webp("SET IG", (100, 180, 255))
    url = f"https://graph.facebook.com/v19.0/{ig_id}?fields=username,followers_count&access_token={token}"
    try:
        data = fetch_json_with_headers(url, seconds=1800, cache_key=f"ig:{ig_id}")
        count = data.get("followers_count")
        label = data.get("username") or "INSTAGRAM"
    except Exception:
        return render_text_webp("IG ERR", (238, 80, 80))
    return render_counter_card("INSTAGRAM", label, count, (225, 48, 108), "FOLLOW", "instagram", opts.get("_target"))
