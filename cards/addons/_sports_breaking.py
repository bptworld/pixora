from io import BytesIO
from datetime import datetime, timezone

from card_utils import (
    cached_priority_graphic,
    draw_sharp_text,
    fetch_logo,
    fetch_sport_scoreboard,
    pick_sport_event,
    priority_graphic_key,
    warm_priority_graphic,
)

from _sports_wall import render_wall_score_frames


SCORE_ANIMATION_OPTION = {
    "key": "scoreAnimationTarget",
    "label": "Score Animation",
    "type": "select",
    "default": "device",
    "choices": [
        {"value": "device", "label": "Single Device"},
        {"value": "group_wall", "label": "Group Wall"},
    ],
}

SCORE_ANIMATION_TEAMS_OPTION = {
    "key": "scoreAnimationTeams",
    "label": "Show Special Graphic For",
    "type": "select",
    "default": "favorite",
    "choices": [
        {"value": "favorite", "label": "Favorite Team"},
        {"value": "both", "label": "Both Teams"},
    ],
}


def graphic_target_option(key, label, default="device"):
    return {
        "key": key,
        "label": label,
        "type": "select",
        "default": default,
        "choices": [
            {"value": "device", "label": "Single Device"},
            {"value": "group_wall", "label": "Group Wall"},
        ],
    }


def with_score_animation_option(options):
    options = list(options or [])
    if not any(isinstance(option, dict) and option.get("key") == "scoreAnimationTarget" for option in options):
        options.append(dict(SCORE_ANIMATION_OPTION))
    if not any(isinstance(option, dict) and option.get("key") == "scoreAnimationTeams" for option in options):
        options.append(dict(SCORE_ANIMATION_TEAMS_OPTION))
    return options


def with_game_moment_options(options, unit="quarter"):
    options = with_score_animation_option(options)
    label_unit = "Period" if str(unit or "").lower() == "period" else "Quarter"
    for key, label in (
        ("startPeriodAnimationTarget", f"Start of {label_unit} Graphic"),
        ("endPeriodAnimationTarget", f"End of {label_unit} Graphic"),
        ("winAnimationTarget", "End of Game Winner Graphic"),
    ):
        if not any(isinstance(option, dict) and option.get("key") == key for option in options):
            options.append(graphic_target_option(key, label))
    return options


def with_soccer_moment_options(options):
    options = list(options or [])
    for key, label in (
        ("gameStartAnimationTarget", "Start of Game Graphic"),
        ("gameEndAnimationTarget", "End of Game Graphic"),
        ("halfStartAnimationTarget", "Start of Half Graphic"),
        ("halfEndAnimationTarget", "End of Half Graphic"),
        ("winAnimationTarget", "End of Game Winner Graphic"),
    ):
        if not any(isinstance(option, dict) and option.get("key") == key for option in options):
            options.append(graphic_target_option(key, label))
    return options


def _hex_color(value, fallback=(245, 250, 255)):
    value = str(value or "").strip().lstrip("#")
    if len(value) == 6:
        try:
            return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            pass
    return fallback


def _animation_width(options):
    try:
        explicit = int((options or {}).get("_width") or 0)
        if explicit > 0:
            return max(64, min(512, explicit))
    except Exception:
        pass
    target = str((options or {}).get("_target") or "").lower()
    if "128x32" in target:
        return 128
    return 64


def selected_competitor(event, favorite):
    favorite = str(favorite or "").strip().upper()
    competition = event.get("competitions", [{}])[0]
    for competitor in competition.get("competitors", []):
        team = competitor.get("team", {})
        values = {
            str(team.get("abbreviation", "")).upper(),
            str(team.get("shortDisplayName", "")).upper(),
            str(team.get("displayName", "")).upper(),
            str(team.get("name", "")).upper(),
        }
        if favorite and favorite in values:
            return competitor
    return None


def animation_competitors(event, favorite, options):
    scope = str((options or {}).get("scoreAnimationTeams") or "favorite").strip().lower()
    if scope in ("both", "all", "game"):
        competition = event.get("competitions", [{}])[0]
        competitors = [item for item in competition.get("competitors", []) if item.get("team")]
        if competitors:
            return competitors
    competitor = selected_competitor(event, favorite)
    return [competitor] if competitor else []


def _score_kind(delta, sport="score"):
    sport = str(sport or "score").lower()
    try:
        delta = int(delta or 0)
    except Exception:
        delta = 0
    if sport == "basketball":
        if delta >= 3:
            return "three"
        if delta == 1:
            return "free_throw"
        return "bucket"
    if sport == "football":
        if delta >= 6:
            return "touchdown"
        if delta == 3:
            return "field_goal"
        if delta == 2:
            return "safety"
        return "score"
    if sport in ("lacrosse", "hockey", "soccer"):
        return "goal"
    if sport == "volleyball":
        return "point"
    return "score"


def _team_logo_url(team):
    if (team or {}).get("logo"):
        return team.get("logo")
    logos = (team or {}).get("logos") or []
    return logos[0].get("href") if logos else ""


def _headshot_sport_path(sport):
    sport = str(sport or "").lower()
    if sport in ("basketball", "nba", "wnba"):
        return "nba"
    if sport == "lacrosse":
        return "lacrosse"
    return ""


def _athlete_headshot(athlete, sport):
    headshot = (athlete or {}).get("headshot")
    if isinstance(headshot, dict):
        headshot = headshot.get("href")
    if headshot:
        return str(headshot).strip()
    athlete_id = str((athlete or {}).get("id") or "").strip()
    sport_path = _headshot_sport_path(sport)
    return f"https://a.espncdn.com/i/headshots/{sport_path}/players/full/{athlete_id}.png" if athlete_id and sport_path else ""


def _scorer_for_score(competition, competitor, score, sport):
    team = (competitor or {}).get("team") or {}
    team_ids = {str(value) for value in (competitor.get("id"), team.get("id"), team.get("uid")) if value}
    scoring = []
    for detail in (competition or {}).get("details") or []:
        detail_team = detail.get("team") or {}
        if not detail.get("scoringPlay") or (team_ids and str(detail_team.get("id") or "") not in team_ids):
            continue
        athletes = detail.get("athletesInvolved") or detail.get("participants") or []
        athlete = athletes[0] if athletes else detail.get("athlete") or {}
        if isinstance(athlete, dict) and "athlete" in athlete:
            athlete = athlete.get("athlete") or {}
        headshot = _athlete_headshot(athlete, sport)
        if not headshot:
            continue
        scoring.append({
            "playerName": athlete.get("shortName") or athlete.get("displayName") or athlete.get("fullName") or "",
            "playerHeadshot": headshot,
            "playerLogo": _team_logo_url(team),
        })
    if not scoring:
        return {}
    try:
        index = max(0, min(len(scoring) - 1, int(score) - 1))
    except Exception:
        index = len(scoring) - 1
    return scoring[index]


def competitor_won(competition, competitor):
    if not competitor:
        return False
    if competitor.get("winner") is True:
        return True
    try:
        score = int(competitor.get("score", 0) or 0)
    except Exception:
        return False
    others = [item for item in (competition or {}).get("competitors", []) if item is not competitor]
    other_scores = []
    for other in others:
        try:
            other_scores.append(int(other.get("score", 0) or 0))
        except Exception:
            pass
    return bool(other_scores) and score > max(other_scores)


def final_win_alert(card_id, state, key, competition, competitor, animation_team, sport="score", render=None, target="device", dwell_secs=7, renderer_name="_render_score_alert_frames"):
    previous = state.get(key) or {}
    if previous.get("win_animated"):
        return None
    if not competitor_won(competition, competitor):
        return None
    state[key] = {**previous, "win_animated": True, "seen": datetime.now(timezone.utc)}
    width = animation_team.get("_width") or 64
    cache_key = priority_graphic_key(card_id, animation_team, "win", width)
    render = render or render_score_alert
    target = str(target or "device").strip().lower()
    wall = target in ("group", "group_wall", "wall") or target.startswith("group:")
    return {
        "body": cached_priority_graphic(cache_key, lambda animation_team=animation_team: render(animation_team, "win")),
        "dwell_secs": dwell_secs,
        "_stay": True,
        "_no_replay": True,
        "_priority": True,
        "_group_wall": {
            "type": "win",
            "renderer": renderer_name,
            "team": dict(animation_team),
            "kind": "win",
            "dwell_secs": max(dwell_secs, 7),
        } if wall else None,
    }


def _status_text(competition):
    status = ((competition or {}).get("status") or {})
    status_type = status.get("type") or {}
    return " ".join(
        str(value or "")
        for value in (
            status_type.get("name"),
            status_type.get("description"),
            status_type.get("detail"),
            status_type.get("shortDetail"),
            status.get("displayClock"),
        )
    ).lower()


def game_moment_alert(options, card_id, state, event, competition, animation_team, sport="score", unit="quarter", default_label="TEAM"):
    status = (competition.get("status") or {})
    status_type = status.get("type") or {}
    game_state = str(status_type.get("state") or "").lower()
    game_id = str(event.get("id") or competition.get("id") or datetime.now().strftime("%Y%m%d"))
    device_id = (options or {}).get("_device_id", "local")
    key = f"{card_id}:{device_id}:{game_id}:game_moment"
    try:
        period = int(status.get("period") or 0)
    except Exception:
        period = 0
    text = _status_text(competition)
    unit = str(unit or "quarter").lower()
    start_kind = "period_start" if unit == "period" else "quarter_start"
    end_kind = "period_end" if unit == "period" else "quarter_end"
    previous = state.get(key)
    signature = {"period": period, "state": game_state, "text": text, "seen": datetime.now(timezone.utc)}
    state[key] = signature
    if previous is None:
        return None

    kind = ""
    target_key = ""
    if period > 0 and period > int(previous.get("period") or 0) and game_state == "in":
        kind = start_kind
        target_key = "startPeriodAnimationTarget"
    elif "end" in text and (unit in text or ("quarter" in text if unit != "period" else "period" in text)):
        previous_text = str(previous.get("text") or "")
        if "end" not in previous_text or text != previous_text:
            kind = end_kind
            target_key = "endPeriodAnimationTarget"
    if not kind:
        return None

    animation_team = {**(animation_team or {}), "_width": _animation_width(options), "_sport": sport}
    cache_key = priority_graphic_key(card_id, animation_team, kind, animation_team["_width"])
    target = str((options or {}).get(target_key) or "device").strip().lower()
    wall = target in ("group", "group_wall", "wall") or target.startswith("group:")
    return {
        "body": cached_priority_graphic(cache_key, lambda animation_team=animation_team, kind=kind: render_score_alert(animation_team, kind)),
        "dwell_secs": 6,
        "_stay": True,
        "_no_replay": True,
        "_priority": True,
        "_group_wall": {
            "type": kind,
            "renderer": "_render_score_alert_frames",
            "team": dict(animation_team),
            "kind": kind,
            "dwell_secs": 6,
        } if wall else None,
    }


def soccer_moment_alert(options, card_id, state, event, competition, animation_team, render=None, renderer_name="_render_score_alert_frames"):
    status = (competition.get("status") or {})
    status_type = status.get("type") or {}
    game_state = str(status_type.get("state") or "").lower()
    game_id = str(event.get("id") or competition.get("id") or datetime.now().strftime("%Y%m%d"))
    device_id = (options or {}).get("_device_id", "local")
    key = f"{card_id}:{device_id}:{game_id}:soccer_moment"
    try:
        period = int(status.get("period") or 0)
    except Exception:
        period = 0
    text = _status_text(competition)
    previous = state.get(key)
    signature = {"period": period, "state": game_state, "text": text, "seen": datetime.now(timezone.utc)}
    state[key] = signature
    if previous is None:
        return None

    kind = ""
    target_key = ""
    previous_state = str(previous.get("state") or "").lower()
    previous_text = str(previous.get("text") or "")
    previous_period = int(previous.get("period") or 0)
    stripped_text = text.strip()
    is_halftime = (
        "halftime" in text
        or "half time" in text
        or "status_halftime" in text
        or stripped_text in ("ht", "half")
        or ("half" in text and "end" in text)
    )

    if game_state == "post" and previous_state != "post":
        kind = "game_end"
        target_key = "gameEndAnimationTarget"
    elif game_state == "in" and previous_state != "in":
        kind = "game_start" if period <= 1 else "half_start"
        target_key = "gameStartAnimationTarget" if kind == "game_start" else "halfStartAnimationTarget"
    elif game_state == "in" and period > previous_period:
        kind = "half_start"
        target_key = "halfStartAnimationTarget"
    elif is_halftime and text != previous_text:
        kind = "half_end"
        target_key = "halfEndAnimationTarget"
    if not kind:
        return None

    animation_team = {
        **(animation_team or {}),
        **_soccer_matchup_payload(competition),
        "_width": _animation_width(options),
        "_sport": "soccer",
    }
    render = render or render_score_alert
    cache_key = priority_graphic_key(card_id, animation_team, kind, animation_team["_width"])
    target = str((options or {}).get(target_key) or "device").strip().lower()
    wall = target in ("group", "group_wall", "wall") or target.startswith("group:")
    return {
        "body": cached_priority_graphic(cache_key, lambda animation_team=animation_team, kind=kind: render(animation_team, kind)),
        "dwell_secs": 6,
        "_stay": True,
        "_no_replay": True,
        "_priority": True,
        "_group_wall": {
            "type": kind,
            "renderer": renderer_name,
            "team": dict(animation_team),
            "kind": kind,
            "dwell_secs": 6,
        } if wall else None,
    }


def _team_display_label(team):
    return (
        (team or {}).get("shortDisplayName")
        or (team or {}).get("displayName")
        or (team or {}).get("name")
        or (team or {}).get("abbreviation")
        or ""
    )


def _soccer_matchup_payload(competition):
    payload = {}
    for competitor in (competition or {}).get("competitors") or []:
        side = str(competitor.get("homeAway") or "").lower()
        if side not in ("away", "home"):
            continue
        team = competitor.get("team") or {}
        prefix = "away" if side == "away" else "home"
        payload[f"{prefix}TeamName"] = _team_display_label(team)
        payload[f"{prefix}TeamAbbr"] = team.get("abbreviation") or team.get("shortDisplayName") or ""
        payload[f"{prefix}TeamLogo"] = _team_logo_url(team)
    return payload


def _kind_lines(kind):
    kind = str(kind or "score").lower()
    if kind == "touchdown":
        return "TOUCH", "DOWN"
    if kind == "field_goal":
        return "FIELD", "GOAL"
    if kind == "safety":
        return "SAFETY", ""
    if kind == "three":
        return "3", "POINT"
    if kind == "free_throw":
        return "FREE", "THROW"
    if kind == "bucket":
        return "BUCKET", ""
    if kind == "goal":
        return "GOAL", ""
    if kind in ("hat_trick", "hat-trick", "hattrick"):
        return "HAT", "TRICK"
    if kind == "point":
        return "POINT", ""
    if kind in ("win", "wins", "winner", "final_win"):
        return "WINS", ""
    if kind in ("quarter_start", "period_start"):
        return "START", "PERIOD" if kind == "period_start" else "QTR"
    if kind in ("quarter_end", "period_end"):
        return "END", "PERIOD" if kind == "period_end" else "QTR"
    if kind == "game_start":
        return "START", "GAME"
    if kind == "game_end":
        return "END", "GAME"
    if kind == "half_start":
        return "START", "HALF"
    if kind == "half_end":
        return "END", "HALF"
    return "SCORE", ""


def _draw_soccer_device_pitch(draw, width, phase, color):
    grass_a = (4, 78, 40)
    grass_b = (6, 104, 50)
    line = (218, 242, 220)
    draw.rectangle((0, 0, width - 1, 31), fill=grass_a)
    for x in range(-8, width + 8, 8):
        fill = grass_b if ((x // 8) + phase) % 2 else grass_a
        draw.polygon([(x, 31), (x + 12, 31), (x + 22, 0), (x + 10, 0)], fill=fill)
    draw.rectangle((2, 4, width - 3, 29), outline=line)
    draw.line((width // 2, 4, width // 2, 29), fill=line)
    draw.ellipse((width // 2 - 8, 12, width // 2 + 8, 28), outline=line)
    draw.rectangle((2, 13, 12, 25), outline=line)
    draw.rectangle((width - 13, 13, width - 3, 25), outline=line)
    draw.rectangle((0, 0, width - 1, 2), fill=color)
    draw.rectangle((0, 30, width - 1, 31), fill=tuple(max(0, c // 2) for c in color))


def _draw_timing_surface(draw, width, phase, color, sport):
    sport = str(sport or "score").lower()
    if sport == "soccer":
        _draw_soccer_device_pitch(draw, width, phase, color)
        return
    if sport in ("football", "nfl", "ufl", "cfl"):
        grass_a = (8, 78, 40)
        grass_b = (10, 102, 48)
        line = (230, 244, 226)
        draw.rectangle((0, 0, width - 1, 31), fill=grass_a)
        for x in range(0, width, 12):
            if ((x // 12) + phase) % 2 == 0:
                draw.rectangle((x, 3, min(width - 1, x + 6), 29), fill=grass_b)
            draw.line((x, 5, x, 29), fill=line)
        draw.line((0, 17, width - 1, 17), fill=line)
        draw.rectangle((0, 0, width - 1, 2), fill=color)
        draw.rectangle((0, 30, width - 1, 31), fill=tuple(max(0, c // 2) for c in color))
        return
    if sport in ("basketball", "nba", "wnba"):
        court = (174, 101, 47)
        stripe = (202, 130, 65)
        line = (248, 224, 184)
        paint = tuple(max(0, c // 2) for c in color)
        draw.rectangle((0, 0, width - 1, 31), fill=court)
        for x in range(-width, width, 9):
            draw.line((x + phase % 9, 31, x + 22 + phase % 9, 0), fill=stripe)
        draw.line((width // 2, 3, width // 2, 30), fill=line)
        draw.ellipse((width // 2 - 9, 11, width // 2 + 9, 29), outline=line)
        draw.rectangle((0, 13, 14, 31), outline=line, fill=paint)
        draw.rectangle((width - 15, 13, width - 1, 31), outline=line, fill=paint)
        draw.rectangle((0, 0, width - 1, 2), fill=color)
        return
    if sport in ("hockey", "nhl"):
        ice = (185, 228, 240)
        line = (245, 250, 255)
        blue = (42, 132, 210)
        red = (220, 40, 52)
        draw.rectangle((0, 0, width - 1, 31), fill=ice)
        draw.rectangle((0, 0, width - 1, 3), fill=line)
        draw.line((width // 2, 3, width // 2, 31), fill=red)
        draw.line((max(0, width // 4), 3, max(0, width // 4), 31), fill=blue)
        draw.line((min(width - 1, width * 3 // 4), 3, min(width - 1, width * 3 // 4), 31), fill=blue)
        draw.ellipse((width // 2 - 9, 13, width // 2 + 9, 31), outline=blue)
        draw.rectangle((2, 19, 8, 28), outline=red)
        draw.rectangle((width - 9, 19, width - 3, 28), outline=red)
        draw.rectangle((0, 0, width - 1, 2), fill=color)
        return
    if sport in ("baseball", "mlb", "college_baseball"):
        grass = (10, 82, 44)
        dirt = (148, 90, 46)
        line = (248, 238, 210)
        draw.rectangle((0, 0, width - 1, 31), fill=grass)
        cx = width // 2
        draw.polygon(((cx, 8), (width - 7, 24), (cx, 31), (7, 24)), fill=dirt, outline=line)
        draw.line((cx, 8, cx, 31), fill=(180, 116, 58))
        draw.line((7, 24, width - 7, 24), fill=(180, 116, 58))
        for x, y in ((cx, 9), (width - 10, 24), (cx, 29), (10, 24)):
            draw.rectangle((x - 1, y - 1, x + 1, y + 1), fill=line)
        draw.rectangle((0, 0, width - 1, 2), fill=color)
        draw.rectangle((0, 30, width - 1, 31), fill=tuple(max(0, c // 2) for c in color))
        return
    if sport == "lacrosse":
        turf_a = (9, 72, 42)
        turf_b = (14, 96, 54)
        line = (230, 244, 226)
        draw.rectangle((0, 0, width - 1, 31), fill=turf_a)
        for x in range(-width, width, 10):
            draw.line((x + phase % 10, 31, x + 30 + phase % 10, 0), fill=turf_b)
        draw.rectangle((3, 5, width - 4, 29), outline=line)
        draw.line((width // 2, 5, width // 2, 29), fill=line)
        draw.ellipse((width // 2 - 7, 15, width // 2 + 7, 29), outline=line)
        draw.rectangle((0, 0, width - 1, 2), fill=color)
        draw.rectangle((0, 30, width - 1, 31), fill=tuple(max(0, c // 2) for c in color))
        return
    if sport == "volleyball":
        court = (188, 112, 52)
        line = (248, 232, 190)
        draw.rectangle((0, 0, width - 1, 31), fill=court)
        draw.rectangle((3, 5, width - 4, 29), outline=line)
        draw.line((width // 2, 5, width // 2, 29), fill=(40, 44, 54))
        for y in range(7, 28, 4):
            draw.point((width // 2, y), fill=line)
        draw.rectangle((0, 0, width - 1, 2), fill=color)
        return
    bg = tuple(max(0, c // 7) for c in color)
    draw.rectangle((0, 0, width - 1, 31), fill=bg)
    draw.rectangle((0, 0, width - 1, 2), fill=color)


def _soccer_timing_text(kind):
    kind = str(kind or "").lower()
    if kind == "game_start":
        return "KICK", "OFF"
    if kind == "game_end":
        return "FULL", "TIME"
    if kind == "half_start":
        return "2ND", "HALF"
    if kind == "half_end":
        return "HALF", "TIME"
    return _kind_lines(kind)


def _timing_text(kind, sport):
    sport = str(sport or "").lower()
    if sport == "soccer":
        return _soccer_timing_text(kind)
    kind = str(kind or "").lower()
    if kind == "game_start":
        return "GAME", "ON"
    if kind == "game_end":
        return "FINAL", ""
    if kind == "quarter_start":
        return "START", "QTR"
    if kind == "quarter_end":
        return "END", "QTR"
    if kind == "period_start":
        return "START", "PERIOD"
    if kind == "period_end":
        return "END", "PERIOD"
    if kind == "half_start":
        return "START", "HALF"
    if kind == "half_end":
        return "END", "HALF"
    if kind == "inning_start":
        return "START", "INNING"
    if kind == "inning_end":
        return "END", "INNING"
    return _kind_lines(kind)


def _fit_device_text(draw, text, font, max_width):
    text = str(text or "").strip().upper()
    while text and draw.textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-1].rstrip()
    return text


def _player_goal_name(team):
    name = str((team or {}).get("playerName") or "").strip()
    if not name:
        return ""
    parts = [part for part in name.replace(".", "").split() if part]
    return (parts[-1] if parts else name).upper()


def _draw_player_goal_device_frame(image, draw, team, kind, step, width, color, alt, small, big):
    name = _player_goal_name(team)
    kind_key = str(kind or "").lower()
    if not name or kind_key not in ("goal", "hat_trick", "hat-trick", "hattrick"):
        return False

    headshot = fetch_logo((team or {}).get("playerHeadshot"), size=22) if (team or {}).get("playerHeadshot") else None
    flag_url = (team or {}).get("playerFlag") or (team or {}).get("playerLogo") or _team_logo_url(team or {})
    flag = fetch_logo(flag_url, size=18 if width >= 96 else 14) if flag_url else None
    edge = alt if step % 2 else color
    panel_x0 = 25 if width < 96 else 28
    panel_x1 = width - (17 if width < 96 else 23)
    if panel_x1 - panel_x0 < 28:
        panel_x0 = 16
        panel_x1 = width - 16

    if headshot:
        hx = 1
        hy = max(5, (32 - headshot.height) // 2)
        draw.rectangle((0, hy - 1, hx + headshot.width, hy + headshot.height), fill=(0, 0, 0), outline=edge)
        image.paste(headshot, (hx, hy), headshot)
    else:
        abbr = str((team or {}).get("abbreviation") or "FC").upper()[:3]
        draw.rectangle((1, 8, 22, 25), fill=(0, 0, 0), outline=edge)
        abbr_w = draw.textbbox((0, 0), abbr, font=small)[2]
        draw_sharp_text(image, (12 - abbr_w // 2, 10), abbr, edge, small)

    if flag:
        fx = width - flag.width - 1
        fy = max(7, (32 - flag.height) // 2)
        draw.rectangle((fx - 1, fy - 1, width - 1, fy + flag.height), fill=(0, 0, 0), outline=edge)
        image.paste(flag, (fx, fy), flag)

    draw.rectangle((panel_x0, 5, panel_x1, 26), fill=(0, 0, 0), outline=edge)
    name = _fit_device_text(draw, name, small, max(8, panel_x1 - panel_x0 - 4))
    goal = "HAT TRICK" if kind_key in ("hat_trick", "hat-trick", "hattrick") else "GOAL"
    goal_font = big
    if draw.textbbox((0, 0), goal, font=goal_font)[2] > max(8, panel_x1 - panel_x0 - 4):
        goal_font = small
    if draw.textbbox((0, 0), goal, font=goal_font)[2] > max(8, panel_x1 - panel_x0 - 4):
        goal = "HAT" if kind_key in ("hat_trick", "hat-trick", "hattrick") else goal
    goal_w = draw.textbbox((0, 0), goal, font=goal_font)[2]
    name_w = draw.textbbox((0, 0), name, font=small)[2]
    draw_sharp_text(image, (panel_x0 + ((panel_x1 - panel_x0 + 1) - name_w) // 2, 4), name, alt, small)
    draw_sharp_text(image, (panel_x0 + ((panel_x1 - panel_x0 + 1) - goal_w) // 2, 16), goal, color if step % 2 else alt, goal_font)
    return True


def _draw_128_soccer_net_badges(image, draw, team, font):
    width = image.width
    if width < 96:
        return
    sides = (
        (2, (team or {}).get("awayTeamName"), (team or {}).get("awayTeamLogo")),
        (width - 35, (team or {}).get("homeTeamName"), (team or {}).get("homeTeamLogo")),
    )
    fallback_label = (team or {}).get("shortDisplayName") or (team or {}).get("displayName") or (team or {}).get("name") or (team or {}).get("abbreviation") or "FC"
    fallback_logo = _team_logo_url(team)
    for x0, raw_label, raw_logo in sides:
        label = _fit_device_text(draw, raw_label or fallback_label, font, 34)
        logo = fetch_logo(raw_logo or fallback_logo, size=13)
        if label:
            label_w = draw.textbbox((0, 0), label, font=font)[2]
            label_x = x0 + max(0, (33 - label_w) // 2)
            draw.rectangle((max(0, label_x - 1), 4, min(width - 1, label_x + label_w + 1), 11), fill=(0, 44, 21))
            draw_sharp_text(image, (label_x, 1), label, (245, 250, 255), font)
        if logo:
            image.paste(logo, (x0 + 10, 14), logo)


def _render_soccer_timing_device_frames(team, kind):
    from PIL import Image, ImageDraw, ImageFont

    try:
        width = int((team or {}).get("_width") or 64)
    except Exception:
        width = 64
    width = max(64, min(512, width))
    color = _hex_color((team or {}).get("color"), (70, 220, 125))
    alt = _hex_color((team or {}).get("alternateColor"), (245, 250, 255))
    try:
        small = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 10)
    except Exception:
        small = big = ImageFont.load_default()
    abbr = str((team or {}).get("abbreviation") or (team or {}).get("shortDisplayName") or "FC").upper()[:5]
    line1, line2 = _soccer_timing_text(kind)
    frames = []
    durations = []
    for step in range(10):
        image = Image.new("RGB", (width, 32), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        _draw_soccer_device_pitch(draw, width, step, color)
        _draw_128_soccer_net_badges(image, draw, team, small)
        abbr_w = draw.textbbox((0, 0), abbr, font=small)[2]
        if width < 96:
            draw.rectangle((1, 3, 3 + abbr_w, 10), fill=(0, 32, 18))
            draw_sharp_text(image, (2, 0), abbr, alt, small)
        for text, y, font, fill in ((line1, 3, big, (230, 36, 48)), (line2, 15, small, color)):
            if not text:
                continue
            if text == "HALF":
                fill = (230, 36, 48)
            text_w = draw.textbbox((0, 0), text, font=font)[2]
            x = (width - text_w) // 2
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                draw_sharp_text(image, (x + dx, y + dy), text, (0, 35, 18), font)
            draw_sharp_text(image, (x, y), text, fill, font)
        frames.append(image)
        durations.append(130 if step % 2 == 0 else 90)
    return frames, durations


def _is_timing_kind(kind):
    return str(kind or "").lower() in (
        "game_start", "game_end",
        "half_start", "half_end",
        "quarter_start", "quarter_end",
        "period_start", "period_end",
        "inning_start", "inning_end",
    )


def _render_sport_timing_device_frames(team, kind):
    from PIL import Image, ImageDraw, ImageFont

    sport = str((team or {}).get("_sport") or "score").lower()
    if sport == "soccer":
        return _render_soccer_timing_device_frames(team, kind)
    try:
        width = int((team or {}).get("_width") or 64)
    except Exception:
        width = 64
    width = max(64, min(512, width))
    color = _hex_color((team or {}).get("color"), (117, 231, 214))
    alt = _hex_color((team or {}).get("alternateColor"), (245, 250, 255))
    try:
        small = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 10)
    except Exception:
        small = big = ImageFont.load_default()
    abbr = str((team or {}).get("abbreviation") or (team or {}).get("shortDisplayName") or "TEAM").upper()[:5]
    line1, line2 = _timing_text(kind, sport)
    line1 = _fit_device_text(ImageDraw.Draw(Image.new("RGB", (1, 1))), line1, big, max(26, width - 8))
    line2 = _fit_device_text(ImageDraw.Draw(Image.new("RGB", (1, 1))), line2, small, max(26, width - 8))
    frames = []
    durations = []
    for step in range(10):
        image = Image.new("RGB", (width, 32), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        _draw_timing_surface(draw, width, step, color, sport)
        if width >= 96:
            abbr_w = draw.textbbox((0, 0), abbr, font=small)[2]
            draw.rectangle((1, 3, 3 + abbr_w, 10), fill=(0, 20, 28) if sport in ("hockey", "nhl") else (0, 32, 18))
            draw_sharp_text(image, (2, 0), abbr, alt, small)
        for text, y, font, fill in ((line1, 4, big, (230, 36, 48)), (line2, 17, small, color if sport not in ("hockey", "nhl") else (20, 80, 160))):
            if not text:
                continue
            text_w = draw.textbbox((0, 0), text, font=font)[2]
            x = (width - text_w) // 2
            shadow = (0, 28, 18) if sport not in ("hockey", "nhl", "basketball", "nba", "wnba", "volleyball") else (42, 24, 16) if sport in ("basketball", "nba", "wnba", "volleyball") else (224, 246, 255)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                draw_sharp_text(image, (x + dx, y + dy), text, shadow, font)
            draw_sharp_text(image, (x, y), text, fill, font)
        frames.append(image)
        durations.append(130 if step % 2 == 0 else 90)
    return frames, durations


def _draw_world_cup_logo_or_fallback(image, draw, team, color, alt):
    from PIL import ImageFont

    logo = fetch_logo((team or {}).get("logo"), size=21) if (team or {}).get("logo") else None
    if logo:
        image.paste(logo, (2, 5), logo if logo.mode == "RGBA" else None)
        return
    abbr = str((team or {}).get("abbreviation") or "FC").upper()[:3]
    try:
        font = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
    except Exception:
        font = ImageFont.load_default()
    draw.rectangle((2, 6, 23, 25), fill=(0, 0, 0), outline=color)
    text_w = draw.textbbox((0, 0), abbr, font=font)[2]
    draw_sharp_text(image, (3 + max(0, (19 - text_w) // 2), 11), abbr, alt, font)


def _draw_world_cup_net(draw, width):
    offset = max(0, int(width or 64) - 64)
    white = (220, 235, 245)
    post = (245, 245, 245)
    draw.line((53 + offset, 13, 63 + offset, 13), fill=post)
    draw.line((53 + offset, 13, 53 + offset, 27), fill=post)
    draw.line((63 + offset, 13, 63 + offset, 27), fill=post)
    draw.line((53 + offset, 27, 63 + offset, 27), fill=post)
    for x in (56 + offset, 59 + offset):
        draw.line((x, 14, x, 26), fill=white)
    for y in (16, 19, 22, 25):
        draw.line((54 + offset, y, 62 + offset, y), fill=white)


def _draw_world_cup_ball(draw, x, y):
    draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(245, 245, 238), outline=(180, 185, 185))
    dark = (18, 22, 26)
    draw.polygon([(x, y - 2), (x + 2, y), (x + 1, y + 3), (x - 1, y + 3), (x - 2, y)], fill=dark)
    for px, py in [(x - 3, y - 3), (x + 3, y - 3), (x - 4, y + 2), (x + 4, y + 2)]:
        draw.rectangle((px, py, px + 1, py + 1), fill=dark)


def _render_soccer_win_device_frames(team):
    from PIL import Image, ImageDraw, ImageFont

    try:
        width = int((team or {}).get("_width") or 64)
    except Exception:
        width = 64
    width = max(64, min(512, width))
    color = _hex_color((team or {}).get("color"), (70, 220, 125))
    alt = _hex_color((team or {}).get("alternateColor"), (245, 250, 255))
    try:
        small = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 10)
    except Exception:
        small = big = ImageFont.load_default()

    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    abbr = str((team or {}).get("abbreviation") or (team or {}).get("shortDisplayName") or "TEAM").upper()
    abbr = _fit_device_text(probe, abbr, small, max(20, width - 32))
    win_text = _fit_device_text(probe, "WINS", big, max(18, width - 32))
    frames = []
    durations = []

    win_w = probe.textbbox((0, 0), win_text, font=big)[2]
    text_x = 26 if width <= 64 else max(26, (width - win_w) // 2)
    ball_path = [(27 + int((width - 33) * (i / 7)), 23 - min(5, abs(3 - i))) for i in range(8)]

    for step, (x, y) in enumerate(ball_path):
        image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        _draw_world_cup_logo_or_fallback(image, draw, team, color, alt)
        _draw_world_cup_net(draw, width)
        if step:
            px, py = ball_path[step - 1]
            draw.point((px - 4, py + 1), fill=(80, 90, 85))
            draw.point((px - 8, py + 2), fill=(45, 52, 48))
        _draw_world_cup_ball(draw, x, y)
        frames.append(image.convert("RGB"))
        durations.append(85)

    for step in range(12):
        image = Image.new("RGBA", (width, 32), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        _draw_world_cup_logo_or_fallback(image, draw, team, color, alt)
        _draw_world_cup_net(draw, width)
        _draw_world_cup_ball(draw, width - 5, 21)
        if step % 2 == 0:
            draw.line((width - 9, 15, width - 2, 26), fill=(245, 245, 245))
            draw.line((width - 2, 15, width - 9, 26), fill=(245, 245, 245))
        for i in range(5):
            sx = 25 + ((step * 5 + i * 9) % max(1, width - 32))
            sy = 2 + ((step * 3 + i * 5) % 10)
            fill = alt if i % 2 else color
            draw.point((sx, sy), fill=fill)
            draw.point((sx + 1, sy), fill=fill)
        if step % 4 != 3:
            draw_sharp_text(image, (text_x, 0), win_text, color if step % 2 else alt, big)
            abbr_w = draw.textbbox((0, 0), abbr, font=small)[2]
            draw_sharp_text(image, (max(25, text_x + max(0, (win_w - abbr_w) // 2)), 12), abbr, (255, 204, 76), small)
        frames.append(image.convert("RGB"))
        durations.append(170 if step % 4 != 3 else 110)
    return frames, durations


def _draw_device_sport_mark(draw, sport, x, y, color, alt, phase=0):
    sport = str(sport or "").lower()
    if sport in ("basketball", "nba", "wnba"):
        ball = (224, 124, 48)
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=ball, outline=alt)
        draw.line((x - 4, y, x + 4, y), fill=(88, 46, 22))
        draw.arc((x - 4, y - 4, x + 4, y + 4), 70, 110, fill=(88, 46, 22))
        draw.arc((x - 4, y - 4, x + 4, y + 4), 250, 290, fill=(88, 46, 22))
        return
    if sport == "volleyball":
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(245, 242, 218), outline=alt)
        draw.arc((x - 4, y - 4, x + 4, y + 4), 15, 165, fill=color)
        draw.arc((x - 4, y - 4, x + 4, y + 4), 195, 330, fill=color)
        draw.line((x, y - 4, x, y + 4), fill=(120, 130, 140))
        return
    if sport == "lacrosse":
        ball = (245, 245, 235)
        draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=ball, outline=alt)
        draw.line((x - 6, y + 5, x + 5, y - 6), fill=color)
        draw.arc((x + 2, y - 8, x + 10, y), 80, 265, fill=alt)
        return
    draw.rectangle((x - 3, y - 3, x + 3, y + 3), fill=color, outline=alt)


def _sport_scene_label(kind, sport):
    sport = str(sport or "").lower()
    kind = str(kind or "").lower()
    if kind in ("win", "wins", "winner", "final_win"):
        return "WINS", ""
    if sport in ("basketball", "nba", "wnba"):
        if kind == "three":
            return "3", "POINT"
        if kind == "free_throw":
            return "FREE", "THROW"
        return "BUCKET", ""
    if sport == "volleyball":
        return "POINT", ""
    if sport == "lacrosse":
        return "GOAL", ""
    return _kind_lines(kind)


def _render_sport_scene_device_frames(team, kind):
    from PIL import Image, ImageDraw, ImageFont

    sport = str((team or {}).get("_sport") or "score").lower()
    try:
        width = int((team or {}).get("_width") or 64)
    except Exception:
        width = 64
    width = max(64, min(512, width))
    color = _hex_color((team or {}).get("color"), (117, 231, 214))
    alt = _hex_color((team or {}).get("alternateColor"), (245, 250, 255))
    try:
        small = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 10)
    except Exception:
        small = big = ImageFont.load_default()

    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    abbr = str((team or {}).get("abbreviation") or (team or {}).get("shortDisplayName") or "TEAM").upper()
    abbr = _fit_device_text(probe, abbr, small, max(18, width - 42))
    line1, line2 = _sport_scene_label(kind, sport)
    line1 = _fit_device_text(probe, line1, big, max(20, width - 40))
    line2 = _fit_device_text(probe, line2, small, max(20, width - 40))
    is_win = str(kind or "").lower() in ("win", "wins", "winner", "final_win")
    text_w = max(probe.textbbox((0, 0), line1, font=big)[2], probe.textbbox((0, 0), line2 or abbr, font=small)[2])
    panel_x0 = 24 if width < 96 else max(26, (width - text_w) // 2 - 4)
    panel_x1 = min(width - 17, panel_x0 + max(26, text_w + 8))
    frames = []
    durations = []

    for step in range(16):
        image = Image.new("RGB", (width, 32), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        _draw_timing_surface(draw, width, step, color, sport)
        logo = fetch_logo((team or {}).get("logo"), size=18) if (team or {}).get("logo") else None
        if logo:
            image.paste(logo, (2, 7), logo if logo.mode == "RGBA" else None)
        else:
            badge = abbr[:3]
            draw.rectangle((2, 7, 21, 24), fill=(0, 0, 0), outline=alt)
            badge_w = draw.textbbox((0, 0), badge, font=small)[2]
            draw_sharp_text(image, (3 + max(0, (17 - badge_w) // 2), 10), badge, alt, small)

        start_x = 24
        end_x = width - 10
        t = min(1, step / 9)
        mark_x = int(start_x + ((end_x - start_x) * t))
        arc = 10 if sport in ("basketball", "volleyball") else 5
        mark_y = int(24 - arc * (1 - abs((t * 2) - 1)))
        for trail in range(1, 4):
            tx = max(start_x, mark_x - trail * 5)
            draw.point((tx, min(28, mark_y + trail)), fill=alt)
        _draw_device_sport_mark(draw, sport, mark_x, mark_y, color, alt, step)

        if step >= 6:
            draw.rectangle((panel_x0, 5, panel_x1, 26), fill=(2, 8, 10), outline=(alt if step % 2 else color))
            l1_w = draw.textbbox((0, 0), line1, font=big)[2]
            draw_sharp_text(image, (panel_x0 + max(0, ((panel_x1 - panel_x0 + 1) - l1_w) // 2), 6), line1, (255, 204, 76) if is_win else alt, big)
            bottom = abbr if is_win or not line2 else line2
            b_w = draw.textbbox((0, 0), bottom, font=small)[2]
            draw_sharp_text(image, (panel_x0 + max(0, ((panel_x1 - panel_x0 + 1) - b_w) // 2), 18), bottom, color if is_win else (255, 204, 76), small)
            if is_win:
                for i in range(3):
                    sx = (panel_x1 + 3 + step * 3 + i * 9) % width
                    sy = 4 + ((step + i * 4) % 20)
                    draw.point((sx, sy), fill=alt)
                    draw.point((sx + 1, sy), fill=color)
        frames.append(image)
        durations.append(80 if step < 10 else 130)
    return frames, durations


def render_score_alert_frames(team, kind="score"):
    from PIL import Image, ImageDraw, ImageFont

    if (team or {}).get("_wall"):
        return render_wall_score_frames(team, kind, sport=(team or {}).get("_sport") or "score")
    kind_key = str(kind or "").lower()
    if str((team or {}).get("_sport") or "").lower() == "soccer" and kind_key in ("win", "wins", "winner", "final_win"):
        return _render_soccer_win_device_frames(team)
    if _is_timing_kind(kind) and str((team or {}).get("_sport") or "").lower() in ("soccer", "football", "basketball", "hockey", "lacrosse", "volleyball", "baseball", "nfl", "nhl", "nba", "wnba", "ufl", "cfl", "mlb", "college_baseball"):
        return _render_sport_timing_device_frames(team, kind)
    if str((team or {}).get("_sport") or "").lower() in ("basketball", "nba", "wnba", "lacrosse", "volleyball"):
        return _render_sport_scene_device_frames(team, kind)

    try:
        width = int((team or {}).get("_width") or 64)
    except Exception:
        width = 64
    width = max(64, min(512, width))
    color = _hex_color((team or {}).get("color"), (117, 231, 214))
    alt = _hex_color((team or {}).get("alternateColor"), (245, 250, 255))
    bg = tuple(max(0, c // 7) for c in color)
    try:
        small = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 8)
        big = ImageFont.truetype("assets/fonts/PixelifySans-Bold.ttf", 10)
    except Exception:
        small = big = ImageFont.load_default()

    abbr = str((team or {}).get("abbreviation") or (team or {}).get("shortDisplayName") or "TEAM").upper()[:6]
    line1, line2 = _kind_lines(kind)
    frames = []
    durations = []
    for step in range(12):
        image = Image.new("RGB", (width, 32), bg if step % 2 == 0 else (0, 0, 0))
        draw = ImageDraw.Draw(image)
        if not _draw_player_goal_device_frame(image, draw, team, kind, step, width, color, alt, small, big):
            draw.rectangle((0, 0, width - 1, 8), fill=(0, 0, 0))
            abbr_w = draw.textbbox((0, 0), abbr, font=small)[2]
            draw_sharp_text(image, ((width - abbr_w) // 2, -3), abbr, alt, small)
            line1_w = draw.textbbox((0, 0), line1, font=big)[2]
            draw_sharp_text(image, ((width - line1_w) // 2, 7), line1, color, big)
            if line2:
                line2_w = draw.textbbox((0, 0), line2, font=small)[2]
                draw_sharp_text(image, ((width - line2_w) // 2, 20), line2, alt, small)
        frames.append(image)
        durations.append(140 if step % 2 == 0 else 90)
    return frames, durations


def render_score_alert(team, kind="score"):
    frames, durations = render_score_alert_frames(team, kind)
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


def maybe_score_alert(options, card_id, url, cache, state, sport="score", default_label="TEAM", render=None, renderer_name="_render_score_alert_frames"):
    favorite = (options or {}).get("favoriteTeam", "")
    if not str(favorite or "").strip():
        return None
    data = fetch_sport_scoreboard(url, cache, favorite, seconds=15)
    event = pick_sport_event(data.get("events", []), favorite)
    if not event:
        return None

    competition = event.get("competitions", [{}])[0]
    game_state = competition.get("status", {}).get("type", {}).get("state")
    competitors = animation_competitors(event, favorite, options)
    if not competitors:
        return None

    game_id = str(event.get("id") or competition.get("id") or datetime.now().strftime("%Y%m%d"))
    device_id = (options or {}).get("_device_id", "local")
    for competitor in competitors:
        team = competitor.get("team", {})
        team_key = (team.get("abbreviation") or team.get("shortDisplayName") or favorite or default_label).upper()
        key = f"{card_id}:{device_id}:{game_id}:{team_key}"
        try:
            score = int(competitor.get("score", 0) or 0)
        except Exception:
            score = 0

        animation_team = {**team, "_width": _animation_width(options), "_sport": sport}
        warm_key = priority_graphic_key(card_id, animation_team, "score", animation_team["_width"])
        previous = state.get(key)
        if game_state != "in":
            if str(game_state or "").lower() == "post":
                win = final_win_alert(
                    card_id,
                    state,
                    key,
                    competition,
                    competitor,
                    animation_team,
                    sport=sport,
                    render=render,
                    target=(options or {}).get("winAnimationTarget") or (options or {}).get("scoreAnimationTarget") or "device",
                    renderer_name=renderer_name,
                )
                if win and previous is not None:
                    return win
            state[key] = {**(state.get(key) or {}), "score": score, "animated": score, "seen": datetime.now(timezone.utc)}
            continue
        if previous is None:
            state[key] = {"score": score, "animated": score, "seen": datetime.now(timezone.utc)}
            warm_priority_graphic(warm_key, lambda animation_team=animation_team: render_score_alert(animation_team, "score"))
            continue

        last_score = int(previous.get("score", score) or 0)
        animated = int(previous.get("animated", last_score) or 0)
        state[key] = {"score": score, "animated": animated, "seen": datetime.now(timezone.utc)}
        if score > last_score and score > animated:
            state[key]["animated"] = score
            kind = _score_kind(score - last_score, sport=sport)
            animation_team = {**animation_team, **_scorer_for_score(competition, competitor, score, sport)}
            target = str((options or {}).get("scoreAnimationTarget") or "device").strip().lower()
            wall = target in ("group", "group_wall", "wall") or target.startswith("group:")
            cache_key = priority_graphic_key(card_id, animation_team, kind, animation_team["_width"])
            return {
                "body": cached_priority_graphic(cache_key, lambda animation_team=animation_team, kind=kind: (render or render_score_alert)(animation_team, kind)),
                "dwell_secs": 6,
                "_stay": True,
                "_no_replay": True,
                "_priority": True,
                "_group_wall": {
                    "type": kind,
                    "renderer": renderer_name,
                    "team": dict(animation_team),
                    "kind": kind,
                    "dwell_secs": 6,
                } if wall else None,
            }
    return None
