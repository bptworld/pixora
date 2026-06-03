from datetime import datetime, timedelta, timezone
import json
import urllib.parse
import urllib.request

API = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
_CACHE = {}


def clean(value):
    return str(value or "").strip()


def current_season():
    return datetime.now().year


def option_season(opts):
    try:
        return max(2018, min(2100, int(clean((opts or {}).get("season")) or current_season())))
    except Exception:
        return current_season()


def league_id(opts):
    return clean((opts or {}).get("leagueId"))


def _cookie_header(opts):
    espn_s2 = clean((opts or {}).get("espnS2"))
    swid = clean((opts or {}).get("swid"))
    chunks = []
    if espn_s2:
        chunks.append("espn_s2=" + espn_s2)
    if swid:
        chunks.append("SWID=" + swid)
    return "; ".join(chunks)


def fetch_league(opts, views=None, week=None, seconds=180):
    lid = league_id(opts)
    season = option_season(opts)
    views = views or ["mTeam", "mRoster", "mMatchup", "mMatchupScore", "mStatus", "mSettings"]
    params = [("view", view) for view in views]
    if week:
        params.append(("scoringPeriodId", str(week)))
    url = f"{API}/seasons/{season}/segments/0/leagues/{lid}?{urllib.parse.urlencode(params)}"
    cookie = _cookie_header(opts)
    cache_key = url + "|" + ("private" if cookie else "public")
    now = datetime.now(timezone.utc)
    cached = _CACHE.get(cache_key)
    if cached and cached["expires"] > now:
        return cached["data"]
    headers = {"User-Agent": "Pixora/0.1", "Accept": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    _CACHE[cache_key] = {"data": data, "expires": now + timedelta(seconds=seconds)}
    return data


def option_week(opts, data=None):
    raw = clean((opts or {}).get("week")).lower()
    if raw and raw != "auto":
        try:
            return max(1, min(23, int(raw)))
        except Exception:
            pass
    status = (data or {}).get("status") or {}
    for key in ("currentMatchupPeriod", "currentScoringPeriod"):
        try:
            week = int(status.get(key) or 0)
            if week > 0:
                return week
        except Exception:
            pass
    return 1


def team_label(team):
    parts = [
        clean(team.get("location")),
        clean(team.get("nickname")),
    ]
    label = " ".join(part for part in parts if part)
    return label or clean(team.get("name")) or clean(team.get("abbrev")) or f"Team {team.get('id')}"


def teams_by_id(data):
    return {int(team.get("id")): team for team in data.get("teams") or [] if team.get("id") is not None}


def resolve_team(data, opts):
    wanted_id = clean((opts or {}).get("teamId"))
    wanted_abbrev = clean((opts or {}).get("teamAbbrev")).upper()
    wanted_name = clean((opts or {}).get("teamName")).lower()
    teams = data.get("teams") or []
    for team in teams:
        if wanted_id and clean(team.get("id")) == wanted_id:
            return team
    for team in teams:
        if wanted_abbrev and clean(team.get("abbrev")).upper() == wanted_abbrev:
            return team
    for team in teams:
        label = team_label(team).lower()
        if wanted_name and wanted_name in label:
            return team
    return teams[0] if teams else None


def record(team):
    overall = ((team.get("record") or {}).get("overall") or {})
    wins = int(overall.get("wins") or 0)
    losses = int(overall.get("losses") or 0)
    ties = int(overall.get("ties") or 0)
    return f"{wins}-{losses}" + (f"-{ties}" if ties else "")


def points_for(team):
    overall = ((team.get("record") or {}).get("overall") or {})
    try:
        return float(overall.get("pointsFor") or 0)
    except Exception:
        return 0.0


def fmt_points(value):
    try:
        return f"{float(value or 0):.1f}"
    except Exception:
        return "0.0"


def matchup_for_team(data, week, team_id):
    for game in data.get("schedule") or []:
        if int(game.get("matchupPeriodId") or game.get("scoringPeriodId") or 0) != int(week):
            continue
        home = game.get("home") or {}
        away = game.get("away") or {}
        if int(home.get("teamId") or 0) == int(team_id):
            return home, away
        if int(away.get("teamId") or 0) == int(team_id):
            return away, home
    return None, None


def _entry_player(entry):
    return (((entry or {}).get("playerPoolEntry") or {}).get("player") or {})


def _entry_points(entry):
    for key in ("appliedStatTotal", "points"):
        if (entry or {}).get(key) is not None:
            return (entry or {}).get(key)
    stats = ((entry or {}).get("playerPoolEntry") or {}).get("appliedStatTotal")
    if stats is not None:
        return stats
    return 0


def _entry_slot(entry):
    try:
        return int((entry or {}).get("lineupSlotId") or 20)
    except Exception:
        return 20


def lineup_entries(side):
    roster = side.get("rosterForCurrentScoringPeriod") or side.get("roster") or {}
    entries = roster.get("entries") or []
    rows = []
    for entry in entries:
        if _entry_slot(entry) >= 20:
            continue
        player = _entry_player(entry)
        name = clean(player.get("fullName")) or clean(player.get("displayName")) or "PLAYER"
        pos = clean(player.get("defaultPositionId"))
        pro = clean(player.get("proTeamId"))
        rows.append({"name": name, "meta": " ".join(x for x in (pos, pro) if x), "points": fmt_points(_entry_points(entry))})
    return rows


def reset_cache():
    _CACHE.clear()
