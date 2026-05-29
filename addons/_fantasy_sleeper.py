from datetime import datetime, timedelta, timezone
import json
import urllib.parse
import urllib.request

API = "https://api.sleeper.app/v1"
_CACHE = {}


def clean(value):
    return str(value or "").strip()


def get_json(path, seconds=300):
    now = datetime.now(timezone.utc)
    url = path if str(path).startswith("http") else API + path
    cached = _CACHE.get(url)
    if cached and cached["expires"] > now:
        return cached["data"]
    req = urllib.request.Request(url, headers={"User-Agent": "Pixora/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    _CACHE[url] = {"data": data, "expires": now + timedelta(seconds=seconds)}
    return data


def nfl_state():
    return get_json("/state/nfl", seconds=900)


def current_week():
    state = nfl_state()
    for key in ("display_week", "week"):
        try:
            week = int(state.get(key) or 0)
            if week > 0:
                return week
        except Exception:
            pass
    return 1


def option_week(opts):
    week = clean((opts or {}).get("week")).lower()
    if not week or week == "auto":
        return current_week()
    try:
        return max(1, min(23, int(week)))
    except Exception:
        return current_week()


def league_id(opts):
    return clean((opts or {}).get("leagueId"))


def league(league_id_value):
    return get_json(f"/league/{league_id_value}", seconds=900)


def users(league_id_value):
    return get_json(f"/league/{league_id_value}/users", seconds=900)


def rosters(league_id_value):
    return get_json(f"/league/{league_id_value}/rosters", seconds=900)


def matchups(league_id_value, week):
    return get_json(f"/league/{league_id_value}/matchups/{week}", seconds=120)


def players():
    return get_json("/players/nfl", seconds=86400)


def user_by_name(username):
    username = urllib.parse.quote(clean(username), safe="")
    return get_json(f"/user/{username}", seconds=3600)


def user_map(league_id_value):
    return {str(user.get("user_id")): user for user in users(league_id_value)}


def team_name(roster, user_lookup):
    user = user_lookup.get(str(roster.get("owner_id"))) or {}
    meta = user.get("metadata") or {}
    return clean(meta.get("team_name")) or clean(user.get("display_name")) or clean(user.get("username")) or f"Roster {roster.get('roster_id')}"


def resolve_roster(league_id_value, opts):
    wanted_roster = clean((opts or {}).get("rosterId"))
    wanted_user = clean((opts or {}).get("username"))
    wanted_team = clean((opts or {}).get("teamName")).lower()
    user_id = ""
    if wanted_user:
        try:
            user_id = clean(user_by_name(wanted_user).get("user_id"))
        except Exception:
            user_id = ""
    lookup = user_map(league_id_value)
    for roster in rosters(league_id_value):
        rid = str(roster.get("roster_id"))
        if wanted_roster and rid == wanted_roster:
            return roster
        if user_id and clean(roster.get("owner_id")) == user_id:
            return roster
        if wanted_team and wanted_team in team_name(roster, lookup).lower():
            return roster
    return None


def roster_by_id(league_id_value, roster_id):
    wanted = str(roster_id)
    for roster in rosters(league_id_value):
        if str(roster.get("roster_id")) == wanted:
            return roster
    return None


def matchup_for_roster(league_id_value, week, roster_id):
    all_rows = matchups(league_id_value, week)
    target = None
    for row in all_rows:
        if str(row.get("roster_id")) == str(roster_id):
            target = row
            break
    if not target:
        return None, None
    matchup_id = target.get("matchup_id")
    opponent = None
    for row in all_rows:
        if row is not target and row.get("matchup_id") == matchup_id:
            opponent = row
            break
    return target, opponent


def points(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def fmt_points(value):
    num = points(value)
    return f"{num:.1f}"


def roster_record(roster):
    settings = roster.get("settings") or {}
    wins = int(settings.get("wins") or 0)
    losses = int(settings.get("losses") or 0)
    ties = int(settings.get("ties") or 0)
    return f"{wins}-{losses}" + (f"-{ties}" if ties else "")


def roster_pf(roster):
    settings = roster.get("settings") or {}
    return points(settings.get("fpts")) + points(settings.get("fpts_decimal")) / 100.0


def player_name(player_id):
    info = (players() or {}).get(str(player_id)) or {}
    first = clean(info.get("first_name"))
    last = clean(info.get("last_name"))
    name = clean(info.get("full_name")) or clean((first + " " + last).strip()) or str(player_id)
    position = clean(info.get("position"))
    team = clean(info.get("team"))
    suffix = " ".join(part for part in (position, team) if part)
    return name, suffix


def reset_cache():
    _CACHE.clear()
