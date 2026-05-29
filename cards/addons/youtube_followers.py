from card_utils import fetch_json_with_headers, render_counter_card, render_text_webp

CARD_ID = "youtube_followers"
CARD_NAME = "YouTube Subscribers"
CARD_DETAIL = "Channel subscriber count"
CARD_OPTIONS = [
    {"key": "channelId", "label": "Channel ID", "type": "text", "default": "", "maxlength": 64},
    {"key": "apiKey", "label": "YouTube API Key", "type": "password", "default": ""},
]


def render(options=None):
    opts = options or {}
    channel_id = (opts.get("channelId") or "").strip()
    api_key = (opts.get("apiKey") or "").strip()
    if not channel_id or not api_key:
        return render_text_webp("SET YT", (100, 180, 255))
    url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&id={channel_id}&key={api_key}"
    try:
        data = fetch_json_with_headers(url, seconds=1800, cache_key=f"yt:{channel_id}")
        item = (data.get("items") or [])[0]
        title = item.get("snippet", {}).get("title") or "YOUTUBE"
        count = item.get("statistics", {}).get("subscriberCount")
    except Exception:
        return render_text_webp("YT ERR", (238, 80, 80))
    return render_counter_card("YOUTUBE", title, count, (255, 0, 0), "SUBS", "youtube", opts.get("_target"))
