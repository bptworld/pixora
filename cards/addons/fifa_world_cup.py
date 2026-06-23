from datetime import datetime, timedelta, timezone
from io import BytesIO

from card_utils import (
    cached_priority_graphic,
    draw_sharp_text,
    fetch_json_with_headers,
    fetch_logo,
    priority_graphic_key,
    render_text_webp,
    warm_priority_graphic,
)
from _sports_breaking import SCORE_ANIMATION_TEAMS_OPTION, animation_competitors, final_win_alert, render_score_alert_frames, soccer_moment_alert, with_soccer_moment_options
from _sports_wall import render_wall_score_frames

CARD_ID = "fifa_world_cup"
CARD_NAME = "FIFA World Cup"
CARD_CATEGORY = "Sports"
CARD_DETAIL = "Selected team next match"
CARD_OPTIONS = [
    {
        "key": "favoriteTeam",
        "label": "Team",
        "type": "select",
        "default": "USA",
        "choices": [
            {"value": "", "label": "Next Match"},
            {"value": "USA", "label": "United States"},
            {"value": "CAN", "label": "Canada"},
            {"value": "MEX", "label": "Mexico"},
            {"value": "ARG", "label": "Argentina"},
            {"value": "BRA", "label": "Brazil"},
            {"value": "ENG", "label": "England"},
            {"value": "FRA", "label": "France"},
            {"value": "GER", "label": "Germany"},
            {"value": "ESP", "label": "Spain"},
            {"value": "POR", "label": "Portugal"},
            {"value": "ITA", "label": "Italy"},
            {"value": "NED", "label": "Netherlands"},
            {"value": "JPN", "label": "Japan"},
            {"value": "KOR", "label": "South Korea"},
            {"value": "AUS", "label": "Australia"},
        ],
    },
    {
        "key": "onlyGameDay",
        "label": "Only show on game day",
        "type": "checkbox",
        "default": False,
        "perInstance": True,
    },
]
CARD_OPTIONS.append({
    "key": "goalAnimationTarget",
    "label": "Goal Animation",
    "type": "select",
    "default": "group_wall",
    "choices": [
        {"value": "device", "label": "Single Device"},
        {"value": "group_wall", "label": "Group Wall"},
    ],
})
CARD_OPTIONS = with_soccer_moment_options(CARD_OPTIONS)
CARD_OPTIONS.append(dict(SCORE_ANIMATION_TEAMS_OPTION))

_COLOR = (70, 220, 125)
_CACHE_SECONDS = 300
_GOAL_STATE = {}


def _date_range():
    today = datetime.now().astimezone().date()
    start = today - timedelta(days=1)
    end = max(today + timedelta(days=1), datetime(today.year, 7, 31).date())
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _scoreboard(seconds=_CACHE_SECONDS):
    start, end = _date_range()
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={start}-{end}"
    return fetch_json_with_headers(
        url,
        seconds=seconds,
        cache_key=f"fifa_world_cup:scoreboard:{start}:{end}:{seconds}",
    )


def _event_dt(event):
    try:
        return datetime.fromisoformat(str(event.get("date") or "").replace("Z", "+00:00"))
    except Exception:
        return datetime.max.replace(tzinfo=timezone.utc)


def _team_values(team):
    return {
        str(team.get("abbreviation") or "").upper(),
        str(team.get("shortDisplayName") or "").upper(),
        str(team.get("displayName") or "").upper(),
        str(team.get("name") or "").upper(),
    }


def _event_has_favorite(event, favorite):
    favorite = str(favorite or "").strip().upper()
    if not favorite:
        return True
    competition = (event.get("competitions") or [{}])[0]
    for competitor in competition.get("competitors") or []:
        if favorite in _team_values(competitor.get("team") or {}):
            return True
    return False


def _events_for_today(events, favorite=""):
    today = datetime.now().astimezone().date()
    return [
        event
        for event in events
        if _event_dt(event).astimezone().date() == today and _event_has_favorite(event, favorite)
    ]


def _option_enabled(value):
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _pick_event(events, favorite=""):
    now = datetime.now(timezone.utc) - timedelta(hours=4)
    candidates = [event for event in events if _event_dt(event) >= now and _event_has_favorite(event, favorite)]
    if not candidates and favorite:
        candidates = [event for event in events if _event_has_favorite(event, favorite)]
    if not candidates:
        candidates = [event for event in events if _event_dt(event) >= now] or list(events)
    state_order = {"in": 0, "pre": 1, "post": 2}
    candidates.sort(key=lambda event: (
        state_order.get(((event.get("competitions") or [{}])[0].get("status") or {}).get("type", {}).get("state"), 3),
        _event_dt(event),
    ))
    return candidates[0] if candidates else None


def _score_text(away, home, state):
    if state == "pre":
        return "VS"
    return f"{away.get('score', '0')}-{home.get('score', '0')}"


def _status_text(event, state):
    competition = (event.get("competitions") or [{}])[0]
    status = (competition.get("status") or {}).get("type", {}).get("shortDetail") or ""
    if state == "pre":
        dt = _event_dt(event).astimezone()
        return f"{dt.strftime('%b')} {dt.day} {dt.strftime('%I:%M%p').lstrip('0')}"
    return status or "WORLD CUP"


def _logo(team, size=18):
    logos = team.get("logos") or []
    url = team.get("logo") or (logos[0].get("href") if logos else "")
    return fetch_logo(url, size=size) if url else None


def _center_text(image, draw, text, y, font, color, x1=0, x2=None):
    x2 = image.width - 1 if x2 is None else x2
    width = draw.textbbox((0, 0), text, font=font)[2]
    draw_sharp_text(image, (x1 + ((x2 - x1 + 1) - width) // 2, y), text, color, font)


def _animation_width(options):
    options = options or {}
    try:
        explicit = int(options.get("_width") or 0)
        if explicit > 0:
            return max(64, min(512, explicit))
    except Exception:
        pass
    target = str(options.get("_target") or "").lower()
    return 128 if "128x32" in target else 64


def _team_for_animation(team, width):
    abbr = (team or {}).get("abbreviation") or (team or {}).get("shortDisplayName") or "FC"
    return {
        **(team or {}),
        "abbreviation": abbr,
        "color": (team or {}).get("color") or "46DC7D",
        "alternateColor": (team or {}).get("alternateColor") or "FFFFFF",
        "logo": (team or {}).get("logo") or (((team or {}).get("logos") or [{}])[0].get("href") if (team or {}).get("logos") else ""),
        "flagCode": str(abbr or "").upper(),
        "_width": width,
    }


def _matchup_payload(competition):
    payload = {}
    for competitor in (competition or {}).get("competitors") or []:
        side = str(competitor.get("homeAway") or "").lower()
        if side not in ("away", "home"):
            continue
        team = competitor.get("team") or {}
        prefix = "away" if side == "away" else "home"
        payload[f"{prefix}TeamName"] = team.get("shortDisplayName") or team.get("displayName") or team.get("name") or team.get("abbreviation") or ""
        payload[f"{prefix}TeamAbbr"] = team.get("abbreviation") or team.get("shortDisplayName") or ""
        payload[f"{prefix}TeamLogo"] = _team_flag_url(team)
    return payload


def _team_flag_url(team):
    logos = (team or {}).get("logos") or []
    return (team or {}).get("logo") or (logos[0].get("href") if logos else "")


def _athlete_headshot(athlete):
    headshot = (athlete or {}).get("headshot")
    if isinstance(headshot, dict):
        headshot = headshot.get("href")
    if headshot:
        return str(headshot).strip()
    athlete_id = str((athlete or {}).get("id") or "").strip()
    return f"https://a.espncdn.com/i/headshots/soccer/players/full/{athlete_id}.png" if athlete_id else ""


def _scorer_for_goal(competition, competitor, score):
    team = (competitor or {}).get("team") or {}
    team_ids = {str(value) for value in (competitor.get("id"), team.get("id"), team.get("uid")) if value}
    goals = []
    for detail in (competition or {}).get("details") or []:
        detail_team = detail.get("team") or {}
        if not detail.get("scoringPlay") or str(detail_team.get("id") or "") not in team_ids:
            continue
        athletes = detail.get("athletesInvolved") or []
        athlete = athletes[0] if athletes else {}
        goals.append({
            "playerName": athlete.get("shortName") or athlete.get("displayName") or athlete.get("fullName") or "",
            "playerHeadshot": _athlete_headshot(athlete),
            "playerFlag": _team_flag_url(team),
        })
    if not goals:
        return {}
    try:
        index = max(0, min(len(goals) - 1, int(score) - 1))
    except Exception:
        index = len(goals) - 1
    return goals[index]


def _test_scorer_payload(team, favorite):
    favorite = str(favorite or (team or {}).get("abbreviation") or "USA").strip().upper()
    samples = {
        "ARG": ("MESSI", "https://a.espncdn.com/i/headshots/soccer/players/full/45843.png"),
        "POR": ("RONALDO", "https://a.espncdn.com/photo/2026/0603/r1667633_1296x1296_1-1.jpg"),
        "USA": ("PULISIC", "https://a.espncdn.com/photo/2026/0622/r1677762_1296x1296_1-1.jpg"),
    }
    name, headshot = samples.get(favorite, (favorite or "PLAYER", "https://a.espncdn.com/i/headshots/soccer/players/full/45843.png"))
    return {
        "playerName": name,
        "playerHeadshot": headshot,
        "playerFlag": _team_flag_url(team or {}) or f"https://a.espncdn.com/i/teamlogos/countries/500/{favorite.lower()}.png",
    }


def _team_matches(team, favorite):
    favorite = str(favorite or "").strip().upper()
    if not favorite:
        return False
    return favorite in _team_values(team or {})


def _resolve_team_for_test(favorite, width=64):
    favorite = str(favorite or "").strip().upper()
    try:
        data = _scoreboard(seconds=15)
        for event in data.get("events") or []:
            competition = (event.get("competitions") or [{}])[0]
            for competitor in competition.get("competitors") or []:
                team = competitor.get("team") or {}
                if _team_matches(team, favorite):
                    return {**_team_for_animation(team, width), **_matchup_payload(competition), **_test_scorer_payload(team, favorite)}
    except Exception:
        pass
    fallback_team = {
        "abbreviation": favorite or "FC",
        "color": "46DC7D",
        "alternateColor": "FFFFFF",
        "logo": f"https://a.espncdn.com/i/teamlogos/countries/500/{(favorite or 'usa').lower()}.png",
    }
    return {**_team_for_animation(fallback_team, width), **_test_scorer_payload(fallback_team, favorite)}


def _render_goal_animation_frames(team, kind="goal"):
    kind = str(kind or "goal").lower()
    if (team or {}).get("_wall"):
        return render_wall_score_frames(team, kind, sport="soccer", default_label="FC")
    return render_score_alert_frames({**(team or {}), "_sport": "soccer"}, kind)


def _render_goal_animation(team, kind="goal"):
    frames, durations = _render_goal_animation_frames(team, kind)
    out = BytesIO()
    frames[0].save(
        out,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=1,
        lossless=True,
        quality=100,
    )
    return out.getvalue()


def _draw_small_flag(draw, box, code):
    code = str(code or "").strip().upper()
    if code not in {"ARG", "AUS", "BRA", "CAN", "ENG", "ESP", "FRA", "GER", "ITA", "JPN", "KOR", "MEX", "NED", "POR", "USA"}:
        return False
    x0, y0, x1, y1 = box
    red = (200, 22, 45)
    blue = (0, 56, 168)
    dark_blue = (0, 38, 84)
    green = (0, 122, 61)
    yellow = (255, 205, 0)
    black = (20, 20, 20)
    white = (245, 245, 245)
    draw.rectangle((x0, y0, x1, y1), fill=white, outline=(210, 220, 226))

    def hstripe(colors):
        height = y1 - y0 + 1
        stripe_h = max(1, height // len(colors))
        y = y0
        for index, color in enumerate(colors):
            bottom = y1 if index == len(colors) - 1 else min(y1, y + stripe_h - 1)
            draw.rectangle((x0, y, x1, bottom), fill=color)
            y = bottom + 1

    def vstripe(colors):
        width = x1 - x0 + 1
        stripe_w = max(1, width // len(colors))
        x = x0
        for index, color in enumerate(colors):
            right = x1 if index == len(colors) - 1 else min(x1, x + stripe_w - 1)
            draw.rectangle((x, y0, right, y1), fill=color)
            x = right + 1

    if code == "USA":
        hstripe([red, white, red, white, red])
        draw.rectangle((x0, y0, x0 + 5, y0 + 5), fill=dark_blue)
        draw.point((x0 + 2, y0 + 2), fill=white)
        draw.point((x0 + 4, y0 + 4), fill=white)
    elif code == "CAN":
        vstripe([red, white, red])
        draw.rectangle((x0 + 6, y0 + 4, x0 + 8, y0 + 7), fill=red)
    elif code == "MEX":
        vstripe([green, white, red])
    elif code == "ARG":
        hstripe([(116, 172, 223), white, (116, 172, 223)])
        draw.point((x0 + 7, y0 + 5), fill=yellow)
    elif code == "BRA":
        draw.rectangle((x0, y0, x1, y1), fill=(0, 156, 59), outline=(210, 220, 226))
        draw.polygon([(x0 + 7, y0 + 1), (x1 - 1, y0 + 5), (x0 + 7, y1 - 1), (x0 + 1, y0 + 5)], fill=yellow)
        draw.rectangle((x0 + 6, y0 + 4, x0 + 8, y0 + 6), fill=blue)
    elif code == "ENG":
        draw.rectangle((x0 + 6, y0, x0 + 8, y1), fill=red)
        draw.rectangle((x0, y0 + 4, x1, y0 + 6), fill=red)
    elif code == "FRA":
        vstripe([(0, 35, 149), white, (237, 41, 57)])
    elif code == "GER":
        hstripe([black, (221, 0, 0), yellow])
    elif code == "ESP":
        hstripe([(198, 11, 30), yellow, (198, 11, 30)])
    elif code == "POR":
        draw.rectangle((x0, y0, x0 + 5, y1), fill=(0, 102, 0))
        draw.rectangle((x0 + 6, y0, x1, y1), fill=(255, 0, 0))
        draw.point((x0 + 6, y0 + 5), fill=yellow)
    elif code == "ITA":
        vstripe([(0, 146, 70), white, (206, 43, 55)])
    elif code == "NED":
        hstripe([(174, 28, 40), white, (33, 70, 139)])
    elif code == "JPN":
        draw.ellipse((x0 + 4, y0 + 2, x1 - 4, y1 - 2), fill=(188, 0, 45))
    elif code == "KOR":
        draw.pieslice((x0 + 4, y0 + 2, x1 - 4, y1 - 2), 0, 180, fill=(205, 46, 58))
        draw.pieslice((x0 + 4, y0 + 2, x1 - 4, y1 - 2), 180, 360, fill=(0, 71, 160))
    elif code == "AUS":
        draw.rectangle((x0, y0, x1, y1), fill=(0, 0, 139), outline=(210, 220, 226))
        draw.point((x0 + 10, y0 + 4), fill=white)
        draw.point((x0 + 12, y0 + 8), fill=white)
    draw.rectangle((x0, y0, x1, y1), outline=(210, 220, 226))
    return True


def _maybe_goal_animation(options):
    opts = options or {}
    favorite = str(opts.get("favoriteTeam") or "").strip().upper()
    if not favorite and str(opts.get("scoreAnimationTeams") or "favorite").strip().lower() not in ("both", "all", "game"):
        return None
    try:
        data = _scoreboard(seconds=15)
    except Exception:
        return None
    event = _pick_event(_events_for_today(data.get("events") or [], favorite), favorite)
    if not event:
        return None

    competition = (event.get("competitions") or [{}])[0]
    state = ((competition.get("status") or {}).get("type") or {}).get("state")
    competitors = animation_competitors(event, favorite, opts)
    if not competitors:
        return None

    game_id = str(event.get("id") or competition.get("id") or datetime.now().strftime("%Y%m%d"))
    device_id = opts.get("_device_id", "local")
    width = _animation_width(opts)
    moment_team = None
    if favorite:
        for competitor in competitors:
            team = competitor.get("team") or {}
            if _team_matches(team, favorite):
                moment_team = _team_for_animation(team, width)
                break
    if moment_team is None and competitors:
        moment_team = _team_for_animation(competitors[0].get("team") or {}, width)
    if moment_team:
        moment = soccer_moment_alert(
            opts,
            CARD_ID,
            _GOAL_STATE,
            event,
            competition,
            moment_team,
            render=_render_goal_animation,
            renderer_name="_render_goal_animation_frames",
        )
        if moment:
            return moment
    for competitor in competitors:
        team = competitor.get("team") or {}
        team_key = (team.get("abbreviation") or team.get("shortDisplayName") or favorite or "FC").upper()
        key = f"{device_id}:fifa.world:{game_id}:{team_key}"
        try:
            score = int(competitor.get("score", 0) or 0)
        except Exception:
            score = 0

        animation_team = _team_for_animation(team, width)
        cache_key = priority_graphic_key(CARD_ID, animation_team, "goal", width)
        previous = _GOAL_STATE.get(key)
        if state != "in":
            if str(state or "").lower() == "post":
                win = final_win_alert(
                    CARD_ID, _GOAL_STATE, key, competition, competitor, animation_team,
                    sport="soccer", render=_render_goal_animation,
                    target=opts.get("winAnimationTarget") or opts.get("goalAnimationTarget") or "device", dwell_secs=7,
                    renderer_name="_render_goal_animation_frames",
                )
                if win and previous is not None:
                    return win
            _GOAL_STATE[key] = {**(_GOAL_STATE.get(key) or {}), "score": score, "animated": score, "seen": datetime.now(timezone.utc)}
            continue

        if previous is None:
            _GOAL_STATE[key] = {"score": score, "animated": score, "seen": datetime.now(timezone.utc)}
            warm_priority_graphic(cache_key, lambda animation_team=animation_team: _render_goal_animation(animation_team))
            continue

        last_score = int(previous.get("score", score) or 0)
        animated = int(previous.get("animated", last_score) or 0)
        _GOAL_STATE[key] = {"score": score, "animated": animated, "seen": datetime.now(timezone.utc)}
        warm_priority_graphic(cache_key, lambda animation_team=animation_team: _render_goal_animation(animation_team))
        if score > last_score and score > animated:
            animation_team = {**animation_team, **_scorer_for_goal(competition, competitor, score)}
            cache_key = priority_graphic_key(CARD_ID, animation_team, "goal", width)
            _GOAL_STATE[key]["animated"] = score
            target = str(opts.get("goalAnimationTarget") or "device").strip().lower()
            wall = target in ("group", "group_wall", "wall") or target.startswith("group:")
            return {
                "body": cached_priority_graphic(cache_key, lambda animation_team=animation_team: _render_goal_animation(animation_team)),
                "dwell_secs": 6,
                "_stay": True,
                "_no_replay": True,
                "_priority": True,
                "_group_wall": {
                    "type": "goal",
                    "kind": "goal",
                    "renderer": "_render_goal_animation_frames",
                    "team": dict(animation_team),
                    "dwell_secs": 6,
                } if wall else None,
            }
    return None


def _render_event(event, width):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (width, 32), (3, 8, 12))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("assets/fonts/Silkscreen-Regular.ttf", 8)
        bold = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = bold = ImageFont.load_default()

    competition = (event.get("competitions") or [{}])[0]
    competitors = competition.get("competitors") or []
    away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[0] if competitors else {})
    home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[-1] if competitors else {})
    away_team = away.get("team") or {}
    home_team = home.get("team") or {}
    state = ((competition.get("status") or {}).get("type") or {}).get("state") or "pre"
    score = _score_text(away, home, state)
    status = _status_text(event, state).upper()

    draw.rectangle((0, 0, width - 1, 8), fill=(4, 24, 20))
    header = "WORLD CUP"
    draw_sharp_text(image, (1, -3), header, (70, 220, 125), bold)
    status_w = draw.textbbox((0, 0), status, font=font)[2]
    header_w = draw.textbbox((0, 0), header, font=bold)[2]
    available_status_w = width - header_w - 6
    while status and status_w > available_status_w:
        status = status[:-1].rstrip()
        status_w = draw.textbbox((0, 0), status, font=font)[2]
    if status:
        draw_sharp_text(image, (width - status_w - 1, -3), status, (165, 190, 185), font)

    def draw_logo_or_flag(team, xy, size):
        logo = _logo(team, size)
        if logo:
            image.paste(logo, xy, logo)
            return True
        return _draw_small_flag(draw, (xy[0], xy[1] + 2, xy[0] + size - 1, xy[1] + size - 4), team.get("abbreviation"))

    if width == 128:
        logo_size = 22
        away_has_mark = draw_logo_or_flag(away_team, (1, 8), logo_size)
        home_has_mark = draw_logo_or_flag(home_team, (105, 8), logo_size)
        score_w = draw.textbbox((0, 0), score, font=bold)[2]
        draw.rounded_rectangle((64 - score_w // 2 - 5, 10, 64 + (score_w + 1) // 2 + 5, 23), radius=3, fill=(15, 27, 34), outline=(52, 78, 88))
        _center_text(image, draw, score, 10, bold, (245, 250, 255), 0, 127)
        away_abbr = (away_team.get("abbreviation") or "AWY")[:3].upper()
        home_abbr = (home_team.get("abbreviation") or "HME")[:3].upper()
        if not away_has_mark:
            draw_sharp_text(image, (26, 13), away_abbr, (245, 250, 255), bold)
        home_w = draw.textbbox((0, 0), home_abbr, font=bold)[2]
        if not home_has_mark:
            draw_sharp_text(image, (102 - home_w, 13), home_abbr, (245, 250, 255), bold)
        detail = (event.get("name") or event.get("shortName") or "")[:24].upper()
        _center_text(image, draw, detail, 23, font, (130, 160, 170), 24, 103)
    else:
        away_abbr = (away_team.get("abbreviation") or "AWY")[:3].upper()
        home_abbr = (home_team.get("abbreviation") or "HME")[:3].upper()
        away_logo = _logo(away_team, 13)
        home_logo = _logo(home_team, 13)
        if away_logo:
            image.paste(away_logo, (1, 10), away_logo)
        elif _draw_small_flag(draw, (1, 12, 14, 20), away_abbr):
            pass
        else:
            draw_sharp_text(image, (1, 10), away_abbr, (245, 250, 255), bold)
        home_w = draw.textbbox((0, 0), home_abbr, font=bold)[2]
        if home_logo:
            image.paste(home_logo, (50, 10), home_logo)
        elif _draw_small_flag(draw, (49, 12, 62, 20), home_abbr):
            pass
        else:
            draw_sharp_text(image, (63 - home_w, 10), home_abbr, (245, 250, 255), bold)
        _center_text(image, draw, score, 10, bold, (245, 250, 255), 0, 63)
        _center_text(image, draw, status[:14], 22, font, (130, 160, 170), 0, 63)

    out = BytesIO()
    image.save(out, "WEBP", lossless=True, quality=100)
    return out.getvalue()


def render(options=None):
    opts = options or {}
    animation = _maybe_goal_animation(opts)
    if animation:
        return animation
    favorite = str(opts.get("favoriteTeam") or "").strip().upper()
    try:
        data = _scoreboard()
    except Exception:
        return None
    events = data.get("events") or []
    if _option_enabled(opts.get("onlyGameDay")):
        events = _events_for_today(events, favorite)
        if not events:
            return None
    event = _pick_event(events, favorite)
    if not event:
        return None
    width = 128 if opts.get("_target") == "matrixportal-s3-128x32" else 64
    competition = (event.get("competitions") or [{}])[0]
    state = ((competition.get("status") or {}).get("type") or {}).get("state")
    return {"body": _render_event(event, width), "_sports_live": state == "in"}
