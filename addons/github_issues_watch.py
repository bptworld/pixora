from io import BytesIO
import re
import urllib.parse

from card_utils import draw_sharp_text, fetch_json_with_headers, render_text_webp

CARD_ID = "github_issues_watch"
CARD_NAME = "GitHub Issues Watch"
CARD_DETAIL = "Open issue count"
CARD_OPTIONS = [
    {"key": "owner", "label": "Owner", "type": "text", "default": "bptworld", "maxlength": 40},
    {"key": "repo", "label": "Repo", "type": "text", "default": "pixora", "maxlength": 60},
    {"key": "assignee", "label": "Assignee (optional)", "type": "text", "default": "", "maxlength": 40},
    {"key": "token", "label": "GitHub Token (optional)", "type": "password", "default": ""},
]


def _count(owner, repo, assignee, token):
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    query = f"repo:{owner}/{repo} is:issue is:open"
    if assignee:
        query += f" assignee:{assignee}"
    url = "https://api.github.com/search/issues?" + urllib.parse.urlencode({"q": query, "per_page": "1"})
    data = fetch_json_with_headers(url, headers, seconds=300, cache_key=f"ghissues:{query}:{bool(token)}")
    return data.get("total_count", 0)


def render(options=None):
    from PIL import Image, ImageDraw, ImageFont

    opts = options or {}
    owner = re.sub(r"[^A-Za-z0-9_.-]", "", opts.get("owner") or "").strip()
    repo = re.sub(r"[^A-Za-z0-9_.-]", "", opts.get("repo") or "").strip()
    assignee = re.sub(r"[^A-Za-z0-9_.-]", "", opts.get("assignee") or "").strip()
    token = (opts.get("token") or "").strip()
    if not owner or not repo:
        return render_text_webp("SET REPO", (100, 180, 255))
    try:
        count = _count(owner, repo, assignee, token)
    except Exception:
        return render_text_webp("ISS ERR", (238, 80, 80))
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    image = Image.new("RGB", (width, 32), (0, 5, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("PixelifySans-Bold.ttf", 16)
    except Exception:
        font = bold = big = ImageFont.load_default()
    draw.rectangle((0, 0, width - 1, 8), fill=(10, 18, 28))
    draw_sharp_text(image, (1, -3), "GITHUB", (145, 180, 255), bold)
    if width == 128:
        repo_text = (owner + "/" + repo).upper()[:17]
        rw = draw.textbbox((0, 0), repo_text, font=font)[2]
        draw_sharp_text(image, (width - 2 - rw, -3), repo_text, (150, 170, 185), font)
    text = str(count)
    tw = draw.textbbox((0, 0), text, font=big)[2]
    draw_sharp_text(image, ((width - tw) // 2, 5), text, (245, 250, 255), big)
    bottom = "ISSUES" if not assignee else "ASSIGNED"
    bw = draw.textbbox((0, 0), bottom, font=font)[2]
    draw_sharp_text(image, ((width - bw) // 2, 23), bottom, (150, 170, 185), font)
    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()

