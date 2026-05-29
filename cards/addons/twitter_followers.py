from card_utils import fetch_json_with_headers, render_counter_card, render_text_webp

CARD_ID = "twitter_followers"
CARD_NAME = "X / Twitter Followers"
CARD_DETAIL = "Follower count via X API"
CARD_OPTIONS = [
    {"key": "username", "label": "Username", "type": "text", "default": "", "maxlength": 32},
    {"key": "bearerToken", "label": "X API Bearer Token", "type": "password", "default": ""},
]


def render(options=None):
    opts = options or {}
    username = (opts.get("username") or "").strip().lstrip("@")
    token = (opts.get("bearerToken") or "").strip()
    if not username or not token:
        return render_text_webp("SET X", (100, 180, 255))
    url = f"https://api.twitter.com/2/users/by/username/{username}?user.fields=public_metrics"
    try:
        data = fetch_json_with_headers(url, {"Authorization": f"Bearer {token}"}, seconds=1800, cache_key=f"x:{username}")
        user = data.get("data", {})
        count = user.get("public_metrics", {}).get("followers_count")
        label = user.get("username") or username
    except Exception:
        return render_text_webp("X ERR", (238, 80, 80))
    return render_counter_card("X", "@" + label, count, (245, 250, 255), "FOLLOW", "x", opts.get("_target"))
