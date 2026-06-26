from datetime import datetime, timezone
from io import BytesIO
import re

from card_utils import draw_sharp_text, fetch_json_with_headers, render_text_webp

CARD_ID = "github_release_watch"
CARD_NAME = "GitHub Release Watch"
CARD_DETAIL = "Latest release for a repo"
CARD_OPTIONS = [
    {"key": "owner", "label": "Owner", "type": "text", "default": "bptworld", "maxlength": 40},
    {"key": "repo", "label": "Repo", "type": "text", "default": "pixora", "maxlength": 60},
    {"key": "onlyNew", "label": "Only show if new release", "type": "checkbox", "default": False},
    {"key": "currentTag", "label": "Current/Seen Tag", "type": "text", "default": "", "maxlength": 40},
    {"key": "token", "label": "GitHub Token (optional)", "type": "password", "default": ""},
]


def _latest(owner, repo, token):
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    base = f"https://api.github.com/repos/{owner}/{repo}"
    try:
        return fetch_json_with_headers(f"{base}/releases/latest", headers, seconds=900, cache_key=f"gh:{owner}/{repo}:{bool(token)}")
    except Exception:
        tags = fetch_json_with_headers(f"{base}/tags?per_page=1", headers, seconds=900, cache_key=f"ghtag:{owner}/{repo}:{bool(token)}")
        if tags:
            return {"tag_name": tags[0].get("name"), "name": tags[0].get("name"), "published_at": ""}
        raise


def _age(published):
    if not published:
        return "LATEST"
    try:
        dt = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
        days = max(0, int((datetime.now(timezone.utc) - dt).total_seconds() // 86400))
        if days == 0:
            return "TODAY"
        if days == 1:
            return "1 DAY"
        return f"{days} DAYS"
    except Exception:
        return "LATEST"


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    owner = re.sub(r"[^A-Za-z0-9_.-]", "", opts.get("owner") or "").strip()
    repo = re.sub(r"[^A-Za-z0-9_.-]", "", opts.get("repo") or "").strip()
    token = (opts.get("token") or "").strip()
    only_new = opts.get("onlyNew") is True or str(opts.get("onlyNew")).lower() == "true"
    current_tag = (opts.get("currentTag") or "").strip()
    if not owner or not repo:
        return render_text_webp("SET REPO", (100, 180, 255))
    try:
        rel = _latest(owner, repo, token)
    except Exception:
        return render_text_webp("GH ERR", (238, 80, 80))

    latest_tag = rel.get("tag_name") or rel.get("name") or "--"
    if only_new and current_tag and latest_tag.strip().lower() == current_tag.lower():
        return None

    tag = latest_tag[:16]
    name = repo[:10].upper()
    age = _age(rel.get("published_at"))

    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    image = Image.new("RGB", (width, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    draw.rectangle((0, 0, width - 1, 6), fill=(10, 18, 28))
    draw_sharp_text(image, (1, -3), "GITHUB", (145, 180, 255), bold)
    draw_sharp_text(image, (1, 8), (owner + "/" + repo).upper()[:22] if width == 128 else name, (245, 250, 255), bold)
    draw_sharp_text(image, (1, 16), latest_tag[:28 if width == 128 else 16], (80, 220, 170), font)
    aw = draw.textbbox((0, 0), age, font=font)[2]
    draw_sharp_text(image, (width - 1 - aw, 22), age, (150, 170, 185), font)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

