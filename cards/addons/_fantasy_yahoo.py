from datetime import datetime, timedelta, timezone
import json
import re
import urllib.parse
import urllib.request

API = "https://fantasysports.yahooapis.com/fantasy/v2"
_CACHE = {}


def clean(value):
    return str(value or "").strip()


def _url(path):
    sep = "&" if "?" in path else "?"
    return API + path + sep + "format=json"


def get_json(path, token, seconds=180):
    url = _url(path)
    now = datetime.now(timezone.utc)
    cache_key = url + "|" + ("token" if token else "public")
    cached = _CACHE.get(cache_key)
    if cached and cached["expires"] > now:
        return cached["data"]
    headers = {"User-Agent": "Pixora/0.1", "Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    _CACHE[cache_key] = {"data": data, "expires": now + timedelta(seconds=seconds)}
    return data


def league_key(opts):
    return clean((opts or {}).get("leagueKey"))


def access_token(opts):
    return clean((opts or {}).get("accessToken"))


def option_week(opts):
    raw = clean((opts or {}).get("week")).lower()
    if not raw or raw == "auto":
        return None
    try:
        return max(1, min(23, int(raw)))
    except Exception:
        return None


def team_key_for(opts):
    key = clean((opts or {}).get("teamKey"))
    if key:
        return key
    lid = league_key(opts)
    team_id = clean((opts or {}).get("teamId"))
    return f"{lid}.t.{team_id}" if lid and team_id else ""


def _flatten_team(value, out):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("team_key", "team_id", "name", "url", "logo_url"):
                out[key] = item
            elif key == "team_points" and isinstance(item, dict):
                out["points"] = item.get("total")
            elif key == "team_standings" and isinstance(item, dict):
                out["rank"] = item.get("rank")
                totals = item.get("outcome_totals") or {}
                out["wins"] = totals.get("wins")
                out["losses"] = totals.get("losses")
                out["ties"] = totals.get("ties")
                out["percentage"] = totals.get("percentage")
                out["games_back"] = item.get("games_back")
            elif key == "roster" and isinstance(item, dict):
                out["roster"] = item
            elif key == "players" and isinstance(item, dict):
                out["players"] = item
            else:
                _flatten_team(item, out)
    elif isinstance(value, list):
        for item in value:
            _flatten_team(item, out)


def parse_team(team_obj):
    raw = team_obj.get("team") if isinstance(team_obj, dict) and "team" in team_obj else team_obj
    out = {}
    _flatten_team(raw, out)
    if "name" not in out and isinstance(raw, str):
        out["name"] = raw
    return out


def _collect_team_objects(value, rows):
    if isinstance(value, dict):
        if "team" in value:
            parsed = parse_team(value)
            if parsed.get("team_key") or parsed.get("name"):
                rows.append(parsed)
        for item in value.values():
            _collect_team_objects(item, rows)
    elif isinstance(value, list):
        for item in value:
            _collect_team_objects(item, rows)


def unique_teams(data):
    rows = []
    _collect_team_objects(data, rows)
    unique = {}
    for row in rows:
        key = clean(row.get("team_key")) or clean(row.get("name"))
        if key and key not in unique:
            unique[key] = row
        elif key:
            unique[key].update({k: v for k, v in row.items() if v not in (None, "")})
    return list(unique.values())


def standings(opts):
    data = get_json(f"/league/{league_key(opts)}/standings", access_token(opts), seconds=300)
    teams = [team for team in unique_teams(data) if team.get("rank") or team.get("wins") is not None]
    teams.sort(key=lambda t: int(t.get("rank") or 999))
    return teams


def scoreboard(opts):
    week = option_week(opts)
    suffix = f";week={week}" if week else ""
    return get_json(f"/league/{league_key(opts)}/scoreboard{suffix}", access_token(opts), seconds=120)


def matchup_teams(opts):
    wanted = team_key_for(opts)
    wanted_name = clean((opts or {}).get("teamName")).lower()
    teams = unique_teams(scoreboard(opts))
    selected = None
    for team in teams:
        if wanted and clean(team.get("team_key")) == wanted:
            selected = team
            break
    if not selected and wanted_name:
        for team in teams:
            if wanted_name in clean(team.get("name")).lower():
                selected = team
                break
    if not selected:
        selected = teams[0] if teams else None
    if not selected:
        return None, None
    # Yahoo scoreboards return teams in matchup order, so pair 0/1, 2/3, etc.
    idx = teams.index(selected)
    opp_idx = idx + 1 if idx % 2 == 0 else idx - 1
    opponent = teams[opp_idx] if 0 <= opp_idx < len(teams) else None
    return selected, opponent


def roster(opts):
    team_key = team_key_for(opts)
    week = option_week(opts)
    path = f"/team/{team_key}/roster"
    if week:
        path += f";week={week}"
    path += "/players/stats"
    return get_json(path, access_token(opts), seconds=180)


def _collect_players(value, rows):
    if isinstance(value, dict):
        if "player" in value:
            rows.append(parse_player(value.get("player")))
        for item in value.values():
            _collect_players(item, rows)
    elif isinstance(value, list):
        for item in value:
            _collect_players(item, rows)


def parse_player(value):
    out = {}

    def walk(item):
        if isinstance(item, dict):
            for key, val in item.items():
                if key in ("player_key", "name", "display_position", "editorial_team_abbr", "selected_position"):
                    out[key] = val
                elif key == "player_points" and isinstance(val, dict):
                    out["points"] = val.get("total")
                elif key == "name" and isinstance(val, dict):
                    out["full_name"] = val.get("full")
                else:
                    walk(val)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    if isinstance(out.get("name"), dict):
        out["full_name"] = out["name"].get("full")
    selected = out.get("selected_position")
    if isinstance(selected, list):
        for item in selected:
            if isinstance(item, dict) and item.get("position"):
                out["selected_position"] = item.get("position")
    return out


def lineup(opts):
    rows = []
    _collect_players(roster(opts), rows)
    clean_rows = []
    for row in rows:
        slot = clean(row.get("selected_position"))
        if slot.upper() in ("BN", "IR"):
            continue
        name = clean(row.get("full_name")) or clean(row.get("name")) or "PLAYER"
        clean_rows.append({
            "name": name,
            "meta": " ".join(x for x in (slot, clean(row.get("editorial_team_abbr"))) if x),
            "points": row.get("points") or "0",
        })
    return clean_rows


def record(team):
    wins = clean(team.get("wins") or "0")
    losses = clean(team.get("losses") or "0")
    ties = clean(team.get("ties") or "")
    return f"{wins}-{losses}" + (f"-{ties}" if ties and ties != "0" else "")


def fmt_points(value):
    try:
        return f"{float(value or 0):.1f}"
    except Exception:
        text = clean(value)
        match = re.search(r"\d+(?:\.\d+)?", text)
        return f"{float(match.group(0)):.1f}" if match else "0.0"


def reset_cache():
    _CACHE.clear()
