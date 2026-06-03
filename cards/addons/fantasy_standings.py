from io import BytesIO

from card_utils import draw_sharp_text, render_text_webp
from _fantasy_sleeper import fmt_points, league_id, roster_pf, roster_record, rosters, team_name, user_map

CARD_ID = "fantasy_standings"
CARD_NAME = "Fantasy Standings"
CARD_DETAIL = "Sleeper league standings"
CARD_OPTIONS = [
    {"key": "leagueId", "label": "Sleeper League ID", "type": "text", "default": "", "maxlength": 32},
    {"key": "showRows", "label": "Rows", "type": "select", "default": "5", "choices": [
        {"value": "3", "label": "3 teams"},
        {"value": "5", "label": "5 teams"},
        {"value": "8", "label": "8 teams"},
        {"value": "12", "label": "12 teams"},
    ]},
]


def _fit(draw, text, font, max_width):
    text = str(text or "")
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1]
    return text


def _draw_rows(rows, width, offset=0):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (width, 32), (3, 5, 14))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()
    draw.rectangle((0, 0, width - 1, 8), fill=(15, 17, 38))
    title = "FANTASY STANDINGS" if width == 128 else "FANTASY"
    tw = draw.textbbox((0, 0), title, font=bold)[2]
    draw_sharp_text(image, ((width - tw) // 2, -3), title, (160, 120, 255), bold)
    for idx, row in enumerate(rows):
        y = 8 + idx * 8 - offset
        if y < 1 or y > 29:
            continue
        rank = str(idx + 1)
        draw_sharp_text(image, (1, y), rank, (255, 210, 80), font)
        if width == 128:
            draw_sharp_text(image, (10, y), _fit(draw, row["name"], font, 56), (245, 250, 255), font)
            draw_sharp_text(image, (72, y), row["record"], (120, 220, 255), font)
            pf = fmt_points(row["pf"])
            pw = draw.textbbox((0, 0), pf, font=font)[2]
            draw_sharp_text(image, (126 - pw, y), pf, (150, 170, 185), font)
        else:
            draw_sharp_text(image, (9, y), _fit(draw, row["name"], font, 28), (245, 250, 255), font)
            rw = draw.textbbox((0, 0), row["record"], font=font)[2]
            draw_sharp_text(image, (63 - rw, y), row["record"], (120, 220, 255), font)
    return image


def _save(frames, durations):
    out = BytesIO()
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=durations, loop=0, lossless=True, quality=100)
    return out.getvalue()


def render(options=None):
    opts = options or {}
    lid = league_id(opts)
    if not lid:
        return render_text_webp("SET LEAGUE", (100, 180, 255))
    try:
        limit = max(3, min(12, int(opts.get("showRows") or 5)))
    except Exception:
        limit = 5
    try:
        lookup = user_map(lid)
        rows = []
        for roster in rosters(lid):
            rows.append({
                "name": team_name(roster, lookup).upper(),
                "record": roster_record(roster),
                "pf": roster_pf(roster),
            })
        rows.sort(key=lambda r: (int(r["record"].split("-")[0]), r["pf"]), reverse=True)
        rows = rows[:limit]
    except Exception:
        return render_text_webp("FANT ERR", (238, 80, 80))
    if not rows:
        return render_text_webp("NO TEAMS", (160, 170, 185))
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    visible = 3
    if len(rows) <= visible:
        out = BytesIO()
        _draw_rows(rows, width, 0).save(out, "WEBP", lossless=True, quality=100)
        return out.getvalue()
    max_offset = (len(rows) - visible) * 8
    offsets = [0] + list(range(1, max_offset + 1)) + [max_offset]
    frames = [_draw_rows(rows, width, off) for off in offsets]
    durations = [3000] + [220] * max_offset + [3000]
    return {"body": _save(frames, durations), "dwell_secs": max(8, round(sum(durations) / 1000)), "_stay": False}
