import math
import json
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Annotated, Optional # Annotated is standard in Python 3.9+

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fantrax_assistant.config import DraftConfig
from fantrax_assistant.scrapers.understat import Understat
from fantrax_assistant.suggest import PlayerRecommendationEngine
from fantrax_assistant.draft_state import DraftState
from fantrax_assistant.analysis import DraftPickAnalyzer
from fantrax_assistant.db import DatabaseManager

# --- App Setup ---
from fantrax_assistant.weekly import WeeklyManagerEngine
from fantrax_assistant.lineup_monitor import LineupMonitor
from fantrax_assistant.waiver_manager import WaiverManagerEngine

config = DraftConfig()
understat = Understat()
analyzer = DraftPickAnalyzer(config=config)
db_mgr = DatabaseManager("data/fantrax_assistant.db")
weekly_engine = WeeklyManagerEngine(config=config)
lineup_monitor = LineupMonitor(config=config)
waiver_engine = WaiverManagerEngine(config=config)

from fantrax_assistant.fixtures_sync import fetch_live_pl_schedule

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load all data on startup
    config.load_all_data()
    # Sync live Premier League schedule & kickoff updates
    try:
        fetch_live_pl_schedule()
    except Exception as e:
        print(f"Non-critical fixture sync warning: {e}")
    # Ensure default draft state file exists
    DraftState()
    yield
    # Clean up resources if needed on shutdown

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="src/web/static"), name="static")
templates = Jinja2Templates(directory="src/web/templates")

CLUB_COLORS_MAP = {
    "ARS": "#EF0107", "AVL": "#95BFE5", "BHA": "#0057B8", "BOU": "#DA291C",
    "BRF": "#D20000", "BRE": "#D20000", "CHE": "#034694", "COV": "#00A3E0",
    "CRY": "#1B458F", "EVE": "#003399", "FUL": "#CC0000", "HUL": "#F5A623",
    "IPS": "#0054A6", "LEE": "#FFCD00", "LIV": "#C8102E", "MCI": "#6CABDD",
    "MUN": "#DA291C", "NEW": "#241F20", "NOT": "#DD0000", "NFO": "#DD0000",
    "SUN": "#EB172B", "TOT": "#132257"
}
templates.env.globals["CLUB_COLORS_MAP"] = CLUB_COLORS_MAP

def get_draft_state_dict() -> dict:
    state = DraftState()
    return {
        "my_team": state.my_team,
        "drafted_players": list(state.drafted_players),
        "teams": state.teams,
    }

@app.get("/api/players/autocomplete")
async def autocomplete_players(q: str = "", include_drafted: bool = True):
    """Endpoint for player name autocomplete."""
    if len(q) < 2:
        return JSONResponse({"players": []})

    all_players = config.rankings.get('rankings', []) if config.rankings else []
    seen = set()
    matches = []
    q_lower = q.strip().lower()

    for p in all_players:
        name = p.get("player", "")
        if q_lower in name.lower() and name not in seen:
            seen.add(name)
            matches.append(name)
            if len(matches) >= 10:
                break

    return JSONResponse({"players": matches})


@app.get("/api/players/search")
async def api_universal_player_search(q: str = ""):
    """Universal player search endpoint covering ALL players (drafted, available, on any team)."""
    import urllib.parse
    if not q or len(q.strip()) < 1:
        return JSONResponse({"results": []})

    query = q.strip().lower()
    state = DraftState()
    drafted_map = {}
    for team_id, roster in state.teams.items():
        for p in roster:
            p_name = p.get('player') or p.get('name')
            if p_name:
                drafted_map[p_name.lower()] = team_id

    for d_name in state.drafted_players:
        if d_name.lower() not in drafted_map:
            drafted_map[d_name.lower()] = "Other"

    all_players = config.rankings.get('rankings', []) if config.rankings else []
    matches = []
    seen = set()

    for p in all_players:
        name = p.get("player", "")
        if not name or name.lower() in seen:
            continue

        p_lower = name.lower()
        if query in p_lower:
            seen.add(p_lower)
            drafted_by = drafted_map.get(p_lower)
            matches.append({
                "name": name,
                "position": p.get("position", "M"),
                "team": p.get("team", ""),
                "fpg": safe_float(p.get("fpg")),
                "adp": safe_float(p.get("adp")),
                "is_drafted": drafted_by is not None,
                "drafted_by": drafted_by,
                "profile_url": f"/player/{urllib.parse.quote(name)}"
            })
            if len(matches) >= 8:
                break

    return JSONResponse({"results": matches})


@app.get("/", response_class=HTMLResponse)
async def read_root(
    request: Request,
    page_available: int = 1,
    page_drafted: int = 1,
    search: str = "",
    search_drafted: str = "",
    sort_available: str = "adp",
    sort_drafted: str = "recent",
    min_games: int = 5
):
    draft_state = get_draft_state_dict()

    drafted_player_names = draft_state.get("drafted_players", [])
    teams_data = draft_state.get("teams", {})

    # Get ALL players (both drafted and available)
    all_players = config.rankings.get('rankings', [])

    drafted_players = []
    available_players = []

    for player in all_players:
        player_name = player.get('player', '')
        injury = config.get_player_injury(player_name)
        afcon = config.get_player_afcon_status(player_name)

        p_uuid = db_mgr.get_player_id_by_name(player_name) or player_name

        enriched_player = {
            **player,
            'id': p_uuid,
            'adp': player.get('adp'),
            'fpts': player.get('fpts'),
            'fpg': player.get('fpg'),
            'injury_severity': injury.get('severity', 'Healthy'),
            'injury_type': injury.get('injury_type', ''),
            'injury_notes': injury.get('injury_type') or injury.get('notes', ''),
            'at_afcon': afcon.get('at_afcon', False)
        }

        is_drafted = any(config._fuzzy_match_name(player_name, d) for d in drafted_player_names)
        if is_drafted:
            # Find owner
            owner_team = None
            for team_id, roster in teams_data.items():
                if any(config._fuzzy_match_name(player_name, p.get('player', '')) for p in roster):
                    owner_team = team_id
                    break

            enriched_player['owner'] = owner_team
            enriched_player['team_id'] = owner_team
            drafted_players.append(enriched_player)
        else:
            available_players.append(enriched_player)

    # Estimate games played helper
    def est_games(p):
        fpts = float(p.get('fpts', 0) or 0)
        fpg = float(p.get('fpg', 0) or 0)
        return round(fpts / fpg) if fpg > 0 else 0

    # Sort available players
    if sort_available == "fpts":
        available_players.sort(key=lambda p: float(p.get('fpts', 0) or 0), reverse=True)
    elif sort_available == "fpg":
        available_players.sort(
            key=lambda p: (
                1 if (float(p.get('fpg', 0) or 0) > 0 and est_games(p) >= min_games) else 0,
                float(p.get('fpg', 0) or 0)
            ),
            reverse=True
        )
    else: # "adp" (default)
        available_players.sort(key=lambda p: float(p.get('adp', 999) or 999))

    # Sort drafted players
    if sort_drafted == "fpts":
        drafted_players.sort(key=lambda p: float(p.get('fpts', 0) or 0), reverse=True)
    elif sort_drafted == "fpg":
        drafted_players.sort(
            key=lambda p: (
                1 if (float(p.get('fpg', 0) or 0) > 0 and est_games(p) >= min_games) else 0,
                float(p.get('fpg', 0) or 0)
            ),
            reverse=True
        )
    elif sort_drafted == "adp":
        drafted_players.sort(key=lambda p: float(p.get('adp', 999) or 999))
    else: # "recent" (default)
        state_obj = DraftState()
        draft_history = state_obj.draft_history
        draft_order_map = {name: i for i, name in enumerate(draft_history)}
        drafted_players.sort(key=lambda p: draft_order_map.get(p.get('player', ''), -1), reverse=True)

    # Apply search filters
    if search:
        available_players = [p for p in available_players if search.lower() in p.get('player', '').lower()]

    if search_drafted:
        drafted_players = [p for p in drafted_players if search_drafted.lower() in p.get('player', '').lower()]

    # Paginate
    available_pagination = paginate(available_players, page_available, 10)
    drafted_pagination = paginate(drafted_players, page_drafted, 10)

    return templates.TemplateResponse(
        request=request, name="index.html",
        context={
            "available": available_pagination,
            "drafted": drafted_pagination,
            "search_query": search,
            "search_drafted_query": search_drafted,
            "sort_available": sort_available,
            "sort_drafted": sort_drafted,
            "min_games": min_games,
            "tracked_teams": [t for t in teams_data.keys() if t != 'Other'],
            "all_teams": list(teams_data.keys())
        }
    )

def get_redirect_target(request: Request, default_url: str, params: dict) -> str:
    from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
    referer = request.headers.get("referer") or default_url
    parsed = urlparse(referer)
    query_dict = parse_qs(parsed.query)
    for key in ["draft_status", "message", "drafted_player"]:
        query_dict.pop(key, None)
    for k, v in params.items():
        if v is not None:
            query_dict[k] = [str(v)]
    new_query = urlencode(query_dict, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


@app.post("/draft/mark_drafted")
async def mark_player_drafted(request: Request, player_name: Annotated[str, Form()]):
    """Marks a player as drafted by an untracked team."""
    state = DraftState()
    player_details = config.get_player_adp(player_name)
    default_url = str(request.url_for('read_root'))

    if not player_details:
        target_url = get_redirect_target(request, default_url, {"draft_status": "error", "message": f"Player '{player_name}' not found"})
        return RedirectResponse(url=target_url, status_code=303)
    
    exact_name = player_details['player']
    if exact_name in state.drafted_players:
        target_url = get_redirect_target(request, default_url, {"draft_status": "error", "message": f"{exact_name} is already drafted"})
        return RedirectResponse(url=target_url, status_code=303)

    state.mark_drafted(exact_name)
    pick_num = len(state.drafted_players)
    available_players = [p for p in config.rankings.get("rankings", []) if p.get('player') not in state.drafted_players]
    analysis = analyzer.grade_pick(
        player_name=exact_name,
        team_id='Other',
        overall_pick_num=pick_num,
        player_adp=player_details.get('adp'),
        player_pos=player_details.get('position', ''),
        player_team=player_details.get('team', ''),
        team_roster=[],
        available_players=available_players
    )
    state.add_pick_analysis(analysis)

    target_url = get_redirect_target(request, default_url, {"draft_status": "success", "message": f"Marked {exact_name} as drafted"})
    return RedirectResponse(url=target_url, status_code=303)

@app.post("/draft/undraft")
async def undraft_player_endpoint(request: Request, player_name: Annotated[str, Form()]):
    """Undrafts a player, returning them to the available pool."""
    state = DraftState()
    state.undraft_player(player_name)
    default_url = str(request.url_for('read_root'))
    target_url = get_redirect_target(request, default_url, {"draft_status": "success", "message": f"Undrafted {player_name}"})
    return RedirectResponse(url=target_url, status_code=303)

@app.post("/api/draft/reassign")
async def reassign_player_team(request: Request):
    """Reassigns a drafted player to another team instantly."""
    try:
        data = await request.json()
        player_name = data.get("player")
        new_team = data.get("team")

        if not player_name or not new_team:
            return JSONResponse({"status": "error", "message": "Player and target team required"}, status_code=400)

        state = DraftState()
        player_info = config.get_player_adp(player_name) or {
            "player": player_name,
            "position": "M",
            "team": "TBD",
            "adp": 999
        }

        # add_to_team removes player from old team and moves to new_team
        state.add_to_team(player_info, new_team)
        analyzer.backfill_retroactive_analysis(state)
        return JSONResponse({"status": "success", "message": f"Moved {player_name} to {new_team}"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/api/draft/reorder")
async def reorder_draft_history(request: Request):
    """
    Reorders the draft sequence based on drag-and-drop actions in the feed
    and re-runs retroactive pick analysis.
    """
    try:
        data = await request.json()
        new_history = data.get("draft_history", [])
        if not new_history:
            return JSONResponse(status_code=400, content={"error": "Empty draft history"})

        state = DraftState()
        state.draft_history = new_history
        state.drafted_players = set(new_history)
        state.pick_analysis_history = []

        analyzer = DraftPickAnalyzer(config=config)
        updated_feed = analyzer.backfill_retroactive_analysis(state)
        state.save()

        return JSONResponse(content={"success": True, "feed": updated_feed})
    except Exception as e:
        print(f"Error reordering draft history: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/draft/delete")
async def delete_draft_pick(request: Request):
    """
    Deletes a drafted pick from draft history and team rosters,
    and re-evaluates retroactive pick analysis for remaining picks.
    """
    try:
        data = await request.json()
        player_name = data.get("player")
        if not player_name:
            return JSONResponse(status_code=400, content={"error": "Missing player name"})

        state = DraftState()
        state.undraft_player(player_name)

        analyzer = DraftPickAnalyzer(config=config)
        updated_feed = analyzer.backfill_retroactive_analysis(state, force=True)
        state.save()

        return JSONResponse(content={"success": True, "feed": updated_feed})
    except Exception as e:
        print(f"Error deleting draft pick: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/draft/swap")
async def swap_draft_pick(request: Request):
    """
    Swaps a drafted player with another player at the exact same pick position in draft history,
    updating team rosters and recalculating retroactive pick analysis.
    """
    try:
        data = await request.json()
        old_player = data.get("old_player")
        new_player = data.get("new_player")

        if not old_player or not new_player:
            return JSONResponse(status_code=400, content={"error": "Both old_player and new_player are required"})

        state = DraftState()
        if old_player not in state.draft_history:
            return JSONResponse(status_code=404, content={"error": f"Player '{old_player}' not found in draft history"})

        # Resolve canonical player name from rankings/ADP
        canonical_info = config.get_player_adp(new_player)
        canonical_name = canonical_info.get("player") if canonical_info else new_player

        # 1. Find which team owned old_player
        owning_team = None
        for t_name, roster in state.teams.items():
            if any(p.get("player") == old_player for p in roster):
                owning_team = t_name
                break

        # 2. Swap in draft_history (preserve exact pick index)
        pick_idx = state.draft_history.index(old_player)
        state.draft_history[pick_idx] = canonical_name

        # 3. Update drafted_players set
        state.drafted_players.discard(old_player)
        state.drafted_players.add(canonical_name)

        # 4. Update team rosters
        state.remove_from_teams(old_player)
        if owning_team:
            new_player_info = canonical_info or {
                "player": canonical_name,
                "position": "M",
                "team": "TBD",
                "adp": 999
            }
            player_data = {
                'player': new_player_info.get('player'),
                'position': new_player_info.get('position'),
                'team': new_player_info.get('team'),
                'adp': new_player_info.get('adp'),
                'fpts': new_player_info.get('fpts'),
                'fpg': new_player_info.get('fpg')
            }
            state.teams[owning_team].append(player_data)

        # 5. Recalculate retroactive analysis for all picks
        state.pick_analysis_history = []
        analyzer = DraftPickAnalyzer(config=config)
        updated_feed = analyzer.backfill_retroactive_analysis(state, force=True)
        state.save()

        return JSONResponse(content={
            "success": True,
            "message": f"Successfully swapped {old_player} for {new_player} at Pick #{pick_idx + 1}",
            "feed": updated_feed
        })
    except Exception as e:
        print(f"Error swapping draft pick: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


def get_team_suggestions_pagination(team_id: str, page: int = 1, page_size: int = 10, exclude_teams: str = "", exclude_positions: str = ""):
    draft_state = get_draft_state_dict()
    teams_data = draft_state.get("teams", {})
    roster = teams_data.get(team_id, [])

    all_drafted_player_names = list(draft_state.get("drafted_players", []))
    for t_name, t_roster in teams_data.items():
        for p in t_roster:
            p_name = p.get('player')
            if p_name and p_name not in all_drafted_player_names:
                all_drafted_player_names.append(p_name)

    drafted_names = set(all_drafted_player_names)
    engine = PlayerRecommendationEngine(config=config, my_team=roster, drafted_players=drafted_names)
    
    num_teams = 9
    current_round = (len(drafted_names) // num_teams) + 1
    
    suggestions = engine.get_recommendations(current_round=current_round, n=100)

    for player in suggestions:
        player_name = player.get('player', '')
        injury = config.get_player_injury(player_name)
        afcon = config.get_player_afcon_status(player_name)

        player['id'] = db_mgr.get_player_id_by_name(player_name) or player_name
        player['injury_severity'] = injury.get('severity', 'Healthy')
        player['at_afcon'] = afcon.get('at_afcon', False)

    excluded_teams = set(t.strip().upper() for t in exclude_teams.split(',') if t.strip()) if exclude_teams else set()
    excluded_positions = set(p.strip().upper() for p in exclude_positions.split(',') if p.strip()) if exclude_positions else set()

    filtered_suggestions = [
        p for p in suggestions
        if p.get('team', '').upper() not in excluded_teams and p.get('position', '')[0].upper() not in excluded_positions
    ]

    return paginate(filtered_suggestions, page, page_size)

@app.get("/api/teams/{team_id}/suggestions")
async def api_team_suggestions(
    team_id: str,
    page: int = 1,
    page_size: int = 10,
    exclude_teams: str = "",
    exclude_positions: str = ""
):
    pagination = get_team_suggestions_pagination(team_id, page=page, page_size=page_size, exclude_teams=exclude_teams, exclude_positions=exclude_positions)
    return {
        "players": pagination["players"],
        "page": pagination["page"],
        "total_pages": pagination["total_pages"],
        "has_next": pagination["page"] < pagination["total_pages"],
        "has_previous": pagination["page"] > 1
    }

@app.get("/teams/{team_id}", response_class=HTMLResponse)
async def read_team(
    request: Request,
    team_id: str,
    tab: str = "roster",
    page_suggestions: int = 1,
    draft_status: str = None,
    drafted_player: str = None,
    exclude_teams: str = "",
    exclude_positions: str = ""
):
    draft_state = get_draft_state_dict()
    teams_data = draft_state.get("teams", {})
    team_name = team_id

    if team_name not in teams_data:
        team_name = [t for t in teams_data.keys() if t != 'Other'][0] if teams_data else "Team 1"

    roster = teams_data.get(team_name, [])

    state = DraftState()
    analysis_history = analyzer.backfill_retroactive_analysis(state)
    grade_lookup = {a["player"]: a for a in analysis_history}

    for player in roster:
        p_name = player.get("player", "")
        a_data = grade_lookup.get(p_name, {})
        inj = config.get_player_injury(p_name)
        afcon = config.get_player_afcon_status(p_name)
        player["id"] = db_mgr.get_player_id_by_name(p_name) or p_name
        player["grade"] = a_data.get("grade", "—")
        player["grade_class"] = a_data.get("grade_class", "blue")
        player["pick_number"] = a_data.get("pick_number")
        player["injury_severity"] = inj.get("severity", "Healthy")
        player["injury_type"] = inj.get("injury_type", "")
        player["at_afcon"] = afcon.get("at_afcon", False)

    roster_rules = {"G": 1, "D": 5, "M": 5, "F": 4}
    all_drafted_player_names = list(draft_state.get("drafted_players", []))
    for t_name, t_roster in teams_data.items():
        for p in t_roster:
            p_name = p.get('player')
            if p_name and p_name not in all_drafted_player_names:
                all_drafted_player_names.append(p_name)

    # Calculate Position Breakdown
    position_counts = {"G": 0, "D": 0, "M": 0, "F": 0}
    for player in roster:
        pos = player.get("position", "").split(',')[0]
        if pos in position_counts:
            position_counts[pos] += 1
    position_breakdown = []
    for pos, max_val in roster_rules.items():
        current_val = position_counts.get(pos, 0)
        position_breakdown.append({
            "position": pos, "current": current_val, "max": max_val, "need": max(0, max_val - current_val)
        })

    # Premier League Club Colors & Metadata
    CLUB_COLORS = {
        "ARS": {"color": "#EF0107", "name": "Arsenal"},
        "AVL": {"color": "#95BFE5", "name": "Aston Villa"},
        "BHA": {"color": "#0057B8", "name": "Brighton"},
        "BOU": {"color": "#DA291C", "name": "Bournemouth"},
        "BRF": {"color": "#D20000", "name": "Brentford"},
        "BRE": {"color": "#D20000", "name": "Brentford"},
        "CHE": {"color": "#034694", "name": "Chelsea"},
        "COV": {"color": "#00A3E0", "name": "Coventry"},
        "CRY": {"color": "#1B458F", "name": "Crystal Palace"},
        "EVE": {"color": "#003399", "name": "Everton"},
        "FUL": {"color": "#CC0000", "name": "Fulham"},
        "HUL": {"color": "#F5A623", "name": "Hull"},
        "IPS": {"color": "#0054A6", "name": "Ipswich"},
        "LEE": {"color": "#FFCD00", "name": "Leeds"},
        "LIV": {"color": "#C8102E", "name": "Liverpool"},
        "MCI": {"color": "#6CABDD", "name": "Man City"},
        "MUN": {"color": "#DA291C", "name": "Man United"},
        "NEW": {"color": "#241F20", "name": "Newcastle"},
        "NOT": {"color": "#DD0000", "name": "Nottm Forest"},
        "NFO": {"color": "#DD0000", "name": "Nottm Forest"},
        "SUN": {"color": "#EB172B", "name": "Sunderland"},
        "TOT": {"color": "#132257", "name": "Tottenham"}
    }

    PL_CLUBS_ORDER = [
        "ARS", "AVL", "BHA", "BOU", "BRF", "CHE", "COV", "CRY", "EVE", "FUL",
        "HUL", "IPS", "LEE", "LIV", "MCI", "MUN", "NEW", "NOT", "SUN", "TOT"
    ]

    BIG_SIX = {"MCI", "ARS", "LIV", "MUN", "CHE", "TOT"}

    # Map player names and positions by club for current roster
    players_by_club = {}
    big_six_count = 0
    non_big_six_count = 0

    for player in roster:
        club = player.get("team", "UNKNOWN").upper()
        if club not in players_by_club:
            players_by_club[club] = []
        players_by_club[club].append({
            "name": player.get("player"),
            "position": player.get("position", "")
        })

        if club in BIG_SIX:
            big_six_count += 1
        else:
            non_big_six_count += 1

    # Include extra rostered clubs if any outside standard PL set
    all_known_clubs = PL_CLUBS_ORDER + [c for c in players_by_club.keys() if c not in PL_CLUBS_ORDER]

    club_breakdown = []
    for club in all_known_clubs:
        rostered_players = players_by_club.get(club, [])
        color_info = CLUB_COLORS.get(club, {"color": "#6c757d", "name": club})
        club_breakdown.append({
            "code": club,
            "name": color_info["name"],
            "count": len(rostered_players),
            "players": rostered_players,
            "is_big_six": club in BIG_SIX,
            "has_players": len(rostered_players) > 0,
            "accent_color": color_info["color"]
        })

    suggestions_pagination = get_team_suggestions_pagination(
        team_id=team_name, page=page_suggestions, page_size=10,
        exclude_teams=exclude_teams, exclude_positions=exclude_positions
    )

    # Weekly Manager Lineup & Auto-Sub Advice
    optimal_lineup = weekly_engine.get_optimal_lineup(roster)
    custom_starters = state.custom_lineups.get(team_name) or state.custom_lineups.get("Team 1")
    is_custom_lineup = False

    if custom_starters:
        def _norm_str(s: str) -> str:
            if not s:
                return ""
            import unicodedata
            nfkd = unicodedata.normalize('NFKD', s)
            return "".join([c for c in nfkd if not unicodedata.combining(c)]).strip().lower()

        norm_custom_set = {_norm_str(s) for s in custom_starters}
        all_players = optimal_lineup['starters'] + optimal_lineup['bench']
        c_starters = [p for p in all_players if _norm_str(p.get('player') or p.get('name', '')) in norm_custom_set]
        c_bench = [p for p in all_players if _norm_str(p.get('player') or p.get('name', '')) not in norm_custom_set]
        if len(c_starters) > 0:
            formation_str = weekly_engine.assign_and_sort_starters(c_starters)
            c_bench.sort(key=lambda x: -float(x.get('proj_fpts', 0.0) or 0.0))
            weekly_lineup = {
                'starters': c_starters,
                'bench': c_bench,
                'formation': formation_str,
                'total_projected_fpts': round(sum(p.get('proj_fpts', 0) for p in c_starters), 2)
            }
            is_custom_lineup = True
        else:
            weekly_lineup = optimal_lineup
    else:
        weekly_lineup = optimal_lineup

    # Build Handcuff Map & Suggested Lineup Upgrades via WeeklyManagerEngine (Single Source of Truth)
    starter_names_set = {s['player'] for s in weekly_lineup['starters']}
    all_squad = weekly_lineup['starters'] + weekly_lineup['bench']
    handcuff_map = weekly_engine.get_handcuff_map(all_squad, starter_names_set)
    suggested_subs = weekly_engine.get_suggested_lineup_upgrades(weekly_lineup, optimal_lineup)

    auto_subs = weekly_engine.get_auto_sub_recommendations(weekly_lineup['starters'], weekly_lineup['bench'])
    injury_contingencies = weekly_engine.get_injury_contingencies(weekly_lineup['starters'], weekly_lineup['bench'])
    lineup_monitor.draft_state = state
    lineup_alerts = lineup_monitor.check_team_lineup_alerts(team_name, roster, custom_starters=custom_starters)
    gw_reminder = lineup_monitor.check_gameweek_eve_health(team_name, roster, custom_starters=custom_starters)
    fantrax_sync_meta = state.fantrax_sync_meta.get(team_name, {})

    all_team_grades = analyzer.evaluate_all_tracked_teams(state)
    team_grade = all_team_grades.get(team_name) or analyzer.evaluate_team_grade(team_name, state)

    return templates.TemplateResponse(
        request=request, name="team.html",
        context={
            "team_name": team_name,
            "roster": roster,
            "position_breakdown": position_breakdown,
            "club_breakdown": club_breakdown,
            "big_six_count": big_six_count,
            "non_big_six_count": non_big_six_count,
            "suggestions": suggestions_pagination,
            "draft_status": draft_status,
            "drafted_player": drafted_player,
            "tracked_teams": [t for t in teams_data.keys() if t != 'Other'],
            "exclude_teams": exclude_teams,
            "exclude_positions": exclude_positions,
            "all_positions": ["G", "D", "M", "F"],
            "active_tab": tab,
            "weekly_lineup": weekly_lineup,
            "is_custom_lineup": is_custom_lineup,
            "suggested_subs": suggested_subs,
            "handcuff_map": handcuff_map,
            "fantrax_sync_meta": fantrax_sync_meta,
            "gw_reminder": gw_reminder,
            "auto_subs": auto_subs,
            "injury_contingencies": injury_contingencies,
            "lineup_alerts": lineup_alerts,
            "team_grade": team_grade
        }
    )

@app.post("/teams/{team_id}/draft")
async def draft_player(
    request: Request,
    team_id: str,
    player_name: Annotated[str, Form()],
):
    """Drafts a player by name to the specified team."""
    state = DraftState()
    player_details = config.get_player_adp(player_name)

    default_url = str(request.url_for('read_team', team_id=team_id))

    if not player_details:
        target_url = get_redirect_target(request, default_url, {
            "draft_status": "error",
            "message": f"Player '{player_name}' not found",
            "drafted_player": player_name
        })
        return RedirectResponse(url=target_url, status_code=303)

    # Use the backend logic to add the player
    success = state.add_to_team(player_details, team_id)

    if success:
        pick_num = len(state.drafted_players)
        team_roster = state.teams.get(team_id, [])
        available_players = [p for p in config.rankings.get("rankings", []) if p.get('player') not in state.drafted_players]
        analysis = analyzer.grade_pick(
            player_name=player_details.get('player'),
            team_id=team_id,
            overall_pick_num=pick_num,
            player_adp=player_details.get('adp'),
            player_pos=player_details.get('position', ''),
            player_team=player_details.get('team', ''),
            team_roster=team_roster,
            available_players=available_players
        )
        state.add_pick_analysis(analysis)

        target_url = get_redirect_target(request, default_url, {
            "draft_status": "success",
            "drafted_player": player_details.get('player'),
            "message": f"Drafted {player_details.get('player')} to {team_id}"
        })
        return RedirectResponse(url=target_url, status_code=303)
    else:
        target_url = get_redirect_target(request, default_url, {
            "draft_status": "error",
            "drafted_player": player_details.get('player'),
            "message": f"{player_details.get('player')} is already drafted"
        })
        return RedirectResponse(url=target_url, status_code=303)

@app.get("/draft/analysis", response_class=HTMLResponse)
async def read_draft_analysis(request: Request):
    """Render reverse chronological pick analysis and grades feed."""
    state = DraftState()
    analysis_history = analyzer.backfill_retroactive_analysis(state)
    analysis_history_sorted = list(reversed(analysis_history))
    teams_data = state.teams

    # Rolling calculation of the highest value steal (biggest pick_number - adp diff)
    top_steal = None
    best_steal_diff = -999.0

    for item in analysis_history:
        item["id"] = db_mgr.get_player_id_by_name(item.get("player")) or item.get("player")
        p_adp = item.get("adp")
        p_pick = item.get("pick_number", 0)
        if p_adp and p_adp > 0:
            diff = p_pick - p_adp
            if diff > best_steal_diff:
                best_steal_diff = diff
                top_steal = item

    # Rolling calculation of the best overall pick (excluding top 4 picks AND avoiding duplication with top_steal)
    eligible_best = [
        x for x in analysis_history 
        if x.get("pick_number", 0) > 4 
        and (not top_steal or x.get("player") != top_steal.get("player"))
    ]
    best_overall = max(eligible_best, key=lambda x: x.get("score", 0)) if eligible_best else (analysis_history[0] if analysis_history else None)

    if not top_steal and analysis_history:
        top_steal = best_overall

    # Rolling calculation of the worst pick (lowest score)
    worst_pick = min(analysis_history, key=lambda x: x.get("score", 100)) if analysis_history else None

    tracked_team_grades = analyzer.evaluate_all_tracked_teams(state)
    sorted_tracked_grades = sorted(tracked_team_grades.values(), key=lambda x: x.get("rank", 99))

    return templates.TemplateResponse(
        request=request,
        name="analysis.html",
        context={
            "feed": analysis_history_sorted,
            "best_overall": best_overall,
            "top_steal": top_steal,
            "worst_pick": worst_pick,
            "tracked_teams": [t for t in teams_data.keys() if t != 'Other'],
            "tracked_team_grades": sorted_tracked_grades
        }
    )

def safe_float(value, default=0.0):
    """Converts a value to a float, returning a default if it fails."""
    try:
        return float(value)
    except (ValueError, TypeError):
        print(f"Could not convert value '{value}' to float. Using default {default}.")
        return default

@app.get("/player/{player_name}", response_class=HTMLResponse)
async def read_player_profile(
    request: Request,
    player_name: str,
    draft_status: Optional[str] = None,
    drafted_player: Optional[str] = None,
    message: Optional[str] = None
):
    import urllib.parse, unicodedata, json
    from scipy.stats import percentileofscore
    import numpy as np
    from fantrax_assistant.db import DatabaseManager
    
    def norm(s):
        return ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn').lower().replace('-', ' ').strip()

    clean_identifier = urllib.parse.unquote(player_name).strip()
    db = DatabaseManager("data/fantrax_assistant.db")
    state = DraftState()
    draft_state_dict = get_draft_state_dict()

    # 1. Fetch Full Player Profile from SQLite DB using UUID or Name
    full_profile = db.get_full_player_profile(clean_identifier) or {}
    player_name_clean = full_profile.get("name") or clean_identifier
    player_uuid = full_profile.get("id") or clean_identifier

    fantrax_info = config.get_player_adp(player_name_clean) or {
        "player": full_profile.get("name", player_name_clean),
        "position": full_profile.get("position", "M"),
        "team": full_profile.get("team", ""),
        "adp": full_profile.get("adp"),
        "fpts": full_profile.get("fpts"),
        "fpg": full_profile.get("fpg")
    }

    # 2. Draft Status & Pick Analysis
    drafted_by_team = None
    for team_id, roster in state.teams.items():
        if any(p.get('player') == player_name_clean or p.get('id') == player_uuid for p in roster):
            drafted_by_team = team_id
            break

    analyzer = DraftPickAnalyzer(config=config)
    analysis_history = analyzer.backfill_retroactive_analysis(state, force=True)
    pick_analysis = next((a for a in analysis_history if a.get("player") == player_name_clean), None)

    # 3. Understat Data Lookup via SQLite Understat ID
    player_data = None
    understat_id = full_profile.get("understat_id")
    
    try:
        if understat_id:
            all_u = understat.get_all_players_data("EPL", "2024")
            player_data = next((u for u in all_u if str(u.get("id")) == str(understat_id)), None)

        if not player_data:
            player_pos_hint = (fantrax_info.get("position") or "").split(",")[0].strip()
            player_data = understat.get_player_data_by_name(
                player_name=player_name_clean, league="EPL", season="2024", player_position=player_pos_hint
            )
    except Exception as e:
        print(f"Understat lookup info for {player_name_clean}: {e}")

    # 4. PL Match Stats from DB or current_stats.json
    pl_stats = full_profile.get("pl_stats")
    if pl_stats:
        if "appearances" not in pl_stats and "total_apps" in pl_stats:
            pl_stats["appearances"] = pl_stats["total_apps"]
    else:
        try:
            with open("data/current_stats.json") as f:
                c_db = json.load(f)
                t_norm = norm(player_name_clean)
                for p in c_db.get("players", []):
                    p_norm = norm(p.get("name", ""))
                    if p_norm == t_norm or t_norm in p_norm or p_norm in t_norm:
                        starts = int(p.get("starts", 0) or 0)
                        matches = int(p.get("matches_played", 0) or 0)
                        pl_stats = {
                            "starts": starts,
                            "appearances": max(starts, matches),
                            "minutes": int(p.get("minutes", 0) or 0),
                            "tackles": int(p.get("tackles", 0) or 0),
                            "cbi": int(p.get("cbi", 0) or 0),
                            "recoveries": int(p.get("recoveries", 0) or 0),
                            "clean_sheets": int(p.get("clean_sheets", 0) or 0),
                            "goals_conceded": int(p.get("goals_conceded", 0) or 0),
                            "expected_goals_conceded": float(p.get("expected_goals_conceded", 0) or 0),
                            "yellow_cards": int(p.get("yellow_cards", 0) or 0),
                            "red_cards": int(p.get("red_cards", 0) or 0),
                            "saves": int(p.get("saves", 0) or 0),
                            "ict_index": float(p.get("ict_index", 0) or 0),
                            "influence": float(p.get("influence", 0) or 0),
                            "threat": float(p.get("threat", 0) or 0),
                        }
                        break
        except Exception as e:
            print(f"Error loading PL stats: {e}")

    # 5. Build Combined 10-Metric Offensive & Defensive Positional Percentile Chart
    chart_data = None
    try:
        with open("data/current_stats.json") as f:
            c_db = json.load(f)

        all_pl_players = c_db.get("players", [])
        target_pl = None
        t_norm = norm(player_name_clean)
        for p in all_pl_players:
            p_norm = norm(p.get("name", ""))
            if p_norm == t_norm or t_norm in p_norm or p_norm in t_norm:
                target_pl = p
                break

        # Map position string (e.g. M, F, D, G) to FPL element_type integer (1=GK, 2=DEF, 3=MID, 4=FWD)
        pos_str = (fantrax_info.get("position") or (player_data.get("position") if player_data else "") or (target_pl.get("position") if target_pl else "M")).split(",")[0].strip().upper()
        fpl_pos_map = {"G": 1, "GK": 1, "GOALKEEPER": 1, "D": 2, "DEF": 2, "DEFENDER": 2, "M": 3, "MID": 3, "MIDFIELDER": 3, "F": 4, "FWD": 4, "FORWARD": 4}
        target_pos_id = fpl_pos_map.get(pos_str, 3)

        # Filter peer players by matching FPL position integer
        peers = [p for p in all_pl_players if p.get("position") == target_pos_id]
        if not peers:
            peers = all_pl_players

        # Query Understat peers directly from DB understat_stats table for Understat metrics
        understat_peers = {}
        try:
            pos_like = f"{pos_str[0]}%"
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT u.xg, u.npxg, u.xa, u.shots, u.key_passes, u.xg_chain, u.xg_buildup
                FROM players p JOIN understat_stats u ON p.id = u.player_id
                WHERE upper(p.position) LIKE ? AND u.xg IS NOT NULL
                """, (pos_like,))
                u_rows = cursor.fetchall()
                if u_rows:
                    understat_peers = {
                        "xG": [float(r[0] or 0) for r in u_rows],
                        "npxG": [float(r[1] or 0) for r in u_rows],
                        "xA": [float(r[2] or 0) for r in u_rows],
                        "shots": [float(r[3] or 0) for r in u_rows],
                        "key_passes": [float(r[4] or 0) for r in u_rows],
                        "xGChain": [float(r[5] or 0) for r in u_rows],
                        "xGBuildup": [float(r[6] or 0) for r in u_rows],
                    }
        except Exception as e:
            print(f"Error loading Understat DB peers: {e}")

        metric_configs = [
            ("goals", "Goals", "goals"),
            ("npg", "Non-Penalty Goals", "goals"),
            ("xG", "xG (Expected Goals)", "xG"),
            ("npxG", "Non-Penalty xG", "xG"),
            ("assists", "Assists", "assists"),
            ("xA", "xA (Expected Assists)", "xA"),
            ("shots", "Shots", "shots"),
            ("key_passes", "Key Passes", "key_passes"),
            ("xGChain", "xG Chain", "ict_index"),
            ("xGBuildup", "xG Build-Up", "creativity"),
            ("cbi", "CBI (Clearances/Blocks/Int)", "cbi"),
            ("tackles", "Tackles Won", "tackles"),
            ("recoveries", "Ball Recoveries", "recoveries"),
            ("clean_sheets", "Clean Sheets", "clean_sheets")
        ]

        labels = []
        percentiles = []
        raw_values = []

        for u_key, label_name, pl_key in metric_configs:
            raw_val = 0.0
            # Official counting stats (goals, assists, tackles, cbi, recoveries, clean_sheets) MUST prioritize Fantrax first!
            if pl_key in {"goals", "assists", "clean_sheets", "tackles", "cbi", "recoveries"}:
                if fantrax_info and pl_key in fantrax_info and fantrax_info.get(pl_key) is not None:
                    raw_val = float(fantrax_info.get(pl_key, 0) or 0)
                elif pl_stats and pl_key in pl_stats and pl_stats.get(pl_key) is not None:
                    raw_val = float(pl_stats.get(pl_key, 0) or 0)
            elif player_data and u_key in player_data and player_data.get(u_key) is not None:
                raw_val = float(player_data.get(u_key, 0) or 0)
            elif pl_stats and pl_key in pl_stats and pl_stats.get(pl_key) is not None:
                raw_val = float(pl_stats.get(pl_key, 0) or 0)
            elif target_pl and pl_key in target_pl:
                raw_val = float(target_pl.get(pl_key, 0) or 0)

            # Fallback estimation for expected stats (xG/xA/shots) if Understat data is missing but FPL goals/threat exist
            if raw_val == 0.0 and pl_stats:
                goals_count = float(pl_stats.get("goals", 0) or 0)
                assists_count = float(pl_stats.get("assists", 0) or 0)
                threat_val = float(pl_stats.get("threat", 0) or 0)
                creativity_val = float(pl_stats.get("creativity", 0) or 0)

                if u_key in {"xG", "npxG"} and (goals_count > 0 or threat_val > 0):
                    raw_val = round(goals_count * 0.70 + (threat_val / 300.0), 2)
                elif u_key == "xA" and (assists_count > 0 or creativity_val > 0):
                    raw_val = round(assists_count * 0.70 + (creativity_val / 350.0), 2)
                elif u_key in {"xGChain", "xGBuildup"} and (threat_val > 0 or creativity_val > 0):
                    raw_val = round((threat_val + creativity_val) / 40.0, 2)
                elif u_key == "shots" and threat_val > 0:
                    raw_val = round(threat_val / 15.0, 1)
                elif u_key == "key_passes" and creativity_val > 0:
                    raw_val = round(creativity_val / 20.0, 1)

            # Select peer values: use Understat DB peers for Understat metrics, FPL peers for FPL metrics
            if u_key in understat_peers:
                peer_vals = understat_peers[u_key]
            else:
                peer_vals = [float(p.get(pl_key, 0) or 0) for p in peers]

            if raw_val == 0 or not peer_vals or all(v == 0 for v in peer_vals):
                pct = 0.0
            else:
                pct = round(float(percentileofscore(peer_vals, raw_val, kind='weak')), 1)

            labels.append(label_name)
            percentiles.append(pct)
            raw_values.append(round(raw_val, 2))

        chart_data = {
            "labels": labels,
            "percentiles": percentiles,
            "raw_values": raw_values
        }
    except Exception as e:
        print(f"Error building chart data for {player_name_clean}: {e}")

    # 6. Availability Status & Position Label
    inj_info = full_profile.get("injury") or config.get_player_injury(player_name_clean) or {}
    injury_severity = inj_info.get("severity") or "Healthy"
    injury_notes = inj_info.get("injury_type") or inj_info.get("notes") or ""
    at_afcon = bool(inj_info.get("at_afcon")) if "at_afcon" in inj_info else config.get_player_afcon_status(player_name_clean).get("at_afcon", False)

    pos_map = {"D": "Defender (D)", "M": "Midfielder (M)", "F": "Forward (F)", "G": "Goalkeeper (G)", "GK": "Goalkeeper (G)"}
    raw_pos = (fantrax_info.get("position") or (player_data.get("position") if player_data else "M")).split(",")[0].split(" ")[0].upper()
    position_display = pos_map.get(raw_pos, f"Position ({raw_pos})")

    # 7. Similar Available Alternatives (Constrained by ADP Window + Profile Distance)
    similar_players = []
    try:
        player_pos = (fantrax_info.get("position") or "M").split(",")[0].strip().upper()
        target_adp = float(fantrax_info.get("adp", 50) or 50)
        target_fpg = float(fantrax_info.get("fpg", 0) or 0)

        def is_injured_out(cand_name: str) -> bool:
            inj = config.get_player_injury(cand_name)
            if not inj:
                return False
            sev = str(inj.get("severity") or "").strip()
            return any(k in sev for k in ["Long Term", "Medium Term", "Out", "Doubtful"])

        # Compare across ALL players across the league (not just undrafted free agents)
        all_league_players = [
            p for p in config.rankings.get("rankings", [])
            if p.get("player") != player_name_clean
            and not is_injured_out(p.get("player", ""))
        ]

        pos_match = [
            p for p in all_league_players
            if player_pos in p.get("position", "").upper().split(",")
        ] or all_league_players

        adp_candidates = [
            p for p in pos_match
            if abs(float(p.get("adp", 999) or 999) - target_adp) <= 45
        ] or pos_match

        scored = []
        for cand in adp_candidates:
            cand_adp = float(cand.get("adp", 999) or 999)
            cand_fpg = float(cand.get("fpg", 0) or 0)

            adp_penalty = abs(cand_adp - target_adp) / 30.0
            fpg_penalty = abs(cand_fpg - target_fpg) * 0.5
            total_score = adp_penalty + fpg_penalty

            cand_copy = dict(cand)
            cand_copy["id"] = db.get_player_id_by_name(cand.get("player")) or cand.get("player")
            cand_copy["xg_per_game"] = round(float(cand.get("xg_per_game", 0) or 0), 2)
            cand_copy["xa_per_game"] = round(float(cand.get("xa_per_game", 0) or 0), 2)

            scored.append((cand_copy, total_score))

        scored.sort(key=lambda x: x[1])
        similar_players = [item[0] for item in scored[:3]]
    except Exception as e:
        print(f"Error finding similar players for {player_name_clean}: {e}")

    # 8. Rotation Risk Score & Status for Player Profile (season availability, rotation & new team risk)
    starts = pl_stats.get("starts", 0) if pl_stats else 0
    apps = pl_stats.get("total_apps") or pl_stats.get("appearances") if pl_stats else 0
    mins = pl_stats.get("minutes", 0) if pl_stats else 0
    adp_val = safe_float(fantrax_info.get("adp", 999))

    is_new_team = bool(fantrax_info.get("is_new_signing") or (full_profile and full_profile.get("is_new_transfer")) or (starts == 0 and apps == 0 and adp_val < 150))

    player_team_upper = (fantrax_info.get("team") or "").upper()
    is_big_six_club = player_team_upper in {"ARS", "MCI", "CHE", "LIV", "MUN", "TOT"}

    start_rate = (starts / apps) if apps > 0 else 0.0

    if apps >= 5 and start_rate >= 0.85:
        rotation_risk_info = {"level": "Low", "badge": "Nailed Starter", "sub": "100% Expected Value (100% Start Rate)", "color": "emerald"}
    elif apps >= 5 and start_rate >= 0.70:
        rotation_risk_info = {"level": "Low", "badge": "Regular Starter", "sub": "95% Expected Value (Regular Starter)", "color": "emerald"}
    elif (is_big_six_club and (starts >= 26 or mins >= 2300)) or (not is_big_six_club and (starts >= 24 or mins >= 2000)):
        rotation_risk_info = {"level": "Low", "badge": "Nailed Starter", "sub": "100% Expected Value", "color": "emerald"}
    elif (not is_big_six_club and starts >= 20 and apps > 0 and starts >= 0.75 * apps) or (not is_big_six_club and mins >= 1800):
        rotation_risk_info = {"level": "Low", "badge": "Regular Starter", "sub": "95% Expected Value (-5% Workload Adj.)", "color": "emerald"}
    elif apps < 5 and apps > 0:
        rotation_risk_info = {"level": "Medium", "badge": "Small Sample", "sub": "85% Expected Value (<5 Games Played)", "color": "amber"}
    elif is_new_team and starts < 5:
        rotation_risk_info = {"level": "Medium", "badge": "New Team", "sub": "85% Expected Value (-15% Integration Adj.)", "color": "amber"}
    elif is_big_six_club and (starts < 26 or mins < 2300):
        rotation_risk_info = {"level": "Medium", "badge": "Moderate Rotation Risk", "sub": "88% Expected Value (-12% Rotation Adj.)", "color": "amber"}
    elif starts >= 15 or mins >= 1200:
        rotation_risk_info = {"level": "Medium", "badge": "Moderate Rotation Risk", "sub": "88% Expected Value (-12% Rotation Adj.)", "color": "amber"}
    else:
        rotation_risk_info = {"level": "High", "badge": "Large Rotation Risk", "sub": "80% Expected Value (-20% Rotation Adj.)", "color": "red"}
    # 9. Relative Form Badge (reign in "Elite Dominant Form" to strictly require top 15 overall or top 3 position relative rank)
    fpts_val = safe_float(fantrax_info.get("fpts", 0))
    fpg_val = safe_float(fantrax_info.get("fpg", 0))
    starts_val = int(pl_stats.get("starts", 0)) if pl_stats else 0
    primary_pos = (fantrax_info.get("position") or "M").split(',')[0].strip().upper()

    analyzer = DraftPickAnalyzer(config=config)
    fpts_rank, _ = analyzer.get_player_relative_rank(player_name_clean, fpts_val)

    pos_rank = 999
    if config and hasattr(config, 'rankings') and isinstance(config.rankings, dict):
        rankings = config.rankings.get("rankings", [])
        same_pos = [p for p in rankings if (p.get('position') or '').split(',')[0].strip().upper() == primary_pos]
        same_pos_sorted = sorted(same_pos, key=lambda p: safe_float(p.get('fpts') or 0.0), reverse=True)
        for idx, p in enumerate(same_pos_sorted, start=1):
            p_name = p.get('player') or p.get('name')
            if p_name == player_name_clean:
                pos_rank = idx
                break

    # Calculate Risk & Flier classifications based on explicit user criteria
    # Risk: High FP/G (>= 3.8) but low match volume/starts (< 15 starts) because they were out long-term injured last season
    inj_sev = (injury_severity or "").strip()
    is_injured_out = any(k in inj_sev for k in ["Long Term", "Medium Term", "Out", "Doubtful", "Injury"])
    is_risk = (fpg_val >= 3.8 or safe_float(fantrax_info.get("fpg_2425")) >= 3.8) and (starts_val < 15 or apps < 18) and is_injured_out

    # Flier: From another league / new transfer / promoted team who is not established yet
    promoted_teams = ["IPSWICH", "LEICESTER", "SOUTHAMPTON", "IPS", "LEI", "SOU"]
    player_team_upper = (fantrax_info.get("team") or "").upper()
    is_promoted = any(pt in player_team_upper for pt in promoted_teams)
    
    is_established_starter = (apps >= 5 and start_rate >= 0.70) or (starts_val >= 15)
    is_flier = not is_established_starter and (is_new_team or is_promoted or (starts_val == 0 and apps == 0)) and fpts_rank > 15

    effective_starts = starts_val if starts_val >= 15 else (15 if is_established_starter else starts_val)

    if (fpts_rank <= 10 or pos_rank <= 2) and effective_starts >= 12:
        form_badge = {"label": "Best of the best", "class": "bg-red-500/20 text-red-400 border-red-500/30"}
    elif (fpts_rank <= 15 or pos_rank <= 4) and effective_starts >= 10:
        form_badge = {"label": "Elite level player", "class": "bg-amber-500/20 text-amber-300 border-amber-500/30"}
    elif is_risk:
        form_badge = {"label": "Rotation Risk", "class": "bg-amber-500/20 text-amber-400 border-amber-500/30"}
    elif is_flier:
        form_badge = {"label": "Flier", "class": "bg-purple-500/20 text-purple-300 border-purple-500/30"}
    elif (fpts_rank <= 50 or pos_rank <= 10) and effective_starts >= 5:
        form_badge = {"label": "High production player", "class": "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"}
    elif fpts_rank <= 110:
        form_badge = {"label": "Solid contributor", "class": "bg-blue-500/20 text-blue-400 border-blue-500/30"}
    else:
        form_badge = {"label": "Bench role", "class": "bg-surface-variant text-on-surface-variant"}

    return templates.TemplateResponse(
        request=request,
        name="player_profile.html",
        context={
            "player_name": player_name_clean,
            "player_id": player_uuid,
            "fantrax_info": fantrax_info or {},
            "position_display": position_display,
            "drafted_by_team": drafted_by_team,
            "pick_analysis": pick_analysis,
            "player_data": player_data,
            "chart_data": chart_data,
            "pl_stats": pl_stats,
            "similar_players": similar_players,
            "injury_severity": injury_severity,
            "injury_notes": injury_notes,
            "at_afcon": at_afcon,
            "rotation_risk_info": rotation_risk_info,
            "form_badge": form_badge,
            "tracked_teams": [t for t in draft_state_dict.get("teams", {}).keys() if t != 'Other'],
            "draft_status": draft_status,
            "drafted_player": drafted_player,
            "message": message
        }
    )

# --- Settings Routes ---
@app.get("/api/settings")
async def get_settings_json():
    settings_file = Path("data/settings.json")
    settings = {}
    if settings_file.exists():
        try:
            with open(settings_file) as f:
                settings = json.load(f)
        except Exception:
            pass
    return JSONResponse(settings)

@app.post("/api/settings")
async def save_settings_api(request: Request):
    try:
        data = await request.json()
        slack_url = str(data.get("slack_webhook_url", "")).strip()
        macos_enabled = bool(data.get("macos_alerts_enabled", True))
        fantrax_league_id = str(data.get("fantrax_league_id", "")).strip()
        fantrax_team_id = str(data.get("fantrax_team_id", "")).strip()
        fantrax_team_name = str(data.get("fantrax_team_name", "")).strip()
        auto_sync_enabled = bool(data.get("auto_sync_enabled", True))
        gameweek_reminder_enabled = bool(data.get("gameweek_reminder_enabled", True))
    except Exception:
        form_data = await request.form()
        slack_url = str(form_data.get("slack_webhook_url", "")).strip()
        macos_enabled = form_data.get("macos_alerts_enabled") is not None
        fantrax_league_id = str(form_data.get("fantrax_league_id", "")).strip()
        fantrax_team_id = str(form_data.get("fantrax_team_id", "")).strip()
        fantrax_team_name = str(form_data.get("fantrax_team_name", "")).strip()
        auto_sync_enabled = form_data.get("auto_sync_enabled") is not None
        gameweek_reminder_enabled = form_data.get("gameweek_reminder_enabled") is not None

    settings_file = Path("data/settings.json")
    settings = {
        "slack_webhook_url": slack_url,
        "macos_alerts_enabled": macos_enabled,
        "fantrax_league_id": fantrax_league_id,
        "fantrax_team_id": fantrax_team_id,
        "fantrax_team_name": fantrax_team_name,
        "auto_sync_enabled": auto_sync_enabled,
        "gameweek_reminder_enabled": gameweek_reminder_enabled
    }
    with open(settings_file, "w") as f:
        json.dump(settings, f, indent=2)

    return JSONResponse({"status": "success", "settings": settings})

@app.get("/settings")
async def get_settings(request: Request, draft_status: Optional[str] = None, save_success: bool = False):
    state = get_draft_state_dict()
    drafted_player = state.get("drafted_player")
    teams_data = state.get("teams", {})

    settings_file = Path("data/settings.json")
    settings = {}
    if settings_file.exists():
        try:
            with open(settings_file) as f:
                settings = json.load(f)
        except Exception:
            pass

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "settings": settings,
            "save_success": save_success,
            "tracked_teams": [t for t in teams_data.keys() if t != 'Other'],
            "draft_status": draft_status,
            "drafted_player": drafted_player
        }
    )

@app.post("/settings")
async def save_settings(request: Request):
    form_data = await request.form()
    slack_webhook_url = str(form_data.get("slack_webhook_url", "")).strip()
    ntfy_topic = str(form_data.get("ntfy_topic", "")).strip()
    macos_alerts_enabled = form_data.get("macos_alerts_enabled") is not None
    fantrax_league_id = str(form_data.get("fantrax_league_id", "")).strip()
    fantrax_team_id = str(form_data.get("fantrax_team_id", "")).strip()
    fantrax_team_name = str(form_data.get("fantrax_team_name", "")).strip()
    auto_sync_enabled = form_data.get("auto_sync_enabled") is not None
    gameweek_reminder_enabled = form_data.get("gameweek_reminder_enabled") is not None

    settings_file = Path("data/settings.json")
    settings = {
        "slack_webhook_url": slack_webhook_url,
        "ntfy_topic": ntfy_topic,
        "macos_alerts_enabled": macos_alerts_enabled,
        "fantrax_league_id": fantrax_league_id,
        "fantrax_team_id": fantrax_team_id,
        "fantrax_team_name": fantrax_team_name,
        "auto_sync_enabled": auto_sync_enabled,
        "gameweek_reminder_enabled": gameweek_reminder_enabled
    }
    with open(settings_file, "w") as f:
        json.dump(settings, f, indent=2)

    referer = request.headers.get("referer", "/settings")
    if "save_success=true" not in referer:
        separator = "&" if "?" in referer else "?"
        redirect_url = f"{referer}{separator}save_success=true"
    else:
        redirect_url = referer

    return RedirectResponse(url=redirect_url, status_code=303)

@app.post("/settings/test-alert")
async def send_test_alert(request: Request):
    from fantrax_assistant.notifications import NotificationManager
    notifier = NotificationManager()
    test_alert = {
        "starter": "Eberechi Eze",
        "starter_pos": "M",
        "starter_team": "ARS",
        "kickoff_time": "Sun Aug 16, 3:00 PM",
        "minutes_until_kickoff": 45.0,
        "severity": "WARNING (Test Scratch)",
        "reason": "Test Lineup Alert from Fantrax Assistant Settings",
        "recommended_sub": "Riccardo Calafiori",
        "alert_text": "[TEST ALERT] Eberechi Eze (ARS) is benched for Sun Aug 16, 3:00 PM kickoff. Recommended Sub: Riccardo Calafiori."
    }
    notifier.send_lineup_alert(test_alert)
    referer = request.headers.get("referer", "/settings")
    return RedirectResponse(url=referer, status_code=303)

@app.post("/api/settings/test-alert")
async def send_test_alert_api(request: Request):
    from fantrax_assistant.notifications import NotificationManager
    notifier = NotificationManager()
    test_alert = {
        "starter": "Eberechi Eze",
        "starter_pos": "M",
        "starter_team": "ARS",
        "kickoff_time": "Sun Aug 16, 3:00 PM",
        "minutes_until_kickoff": 45.0,
        "severity": "WARNING (Test Scratch)",
        "reason": "Test Lineup Alert from Fantrax Assistant Settings",
        "recommended_sub": "Riccardo Calafiori",
        "alert_text": "[TEST ALERT] Eberechi Eze (ARS) is benched for Sun Aug 16, 3:00 PM kickoff. Recommended Sub: Riccardo Calafiori."
    }
    sent = notifier.send_lineup_alert(test_alert)
    return JSONResponse({"status": "success", "sent_channels": sent})

@app.post("/api/teams/{team_id}/sync-fantrax")
async def sync_fantrax_endpoint(team_id: str):
    from fantrax_assistant.scrapers.fantrax_api import FantraxClient
    state = DraftState()
    settings_file = Path("data/settings.json")
    league_id = ""
    team_name_or_id = team_id
    if settings_file.exists():
        try:
            with open(settings_file) as f:
                s = json.load(f)
                league_id = s.get("fantrax_league_id", "")
                team_name_or_id = s.get("fantrax_team_name") or team_id
        except Exception:
            pass

    client = FantraxClient()
    result = client.sync_team_roster(league_id or "demo_league", team_name_or_id, state)
    state.fantrax_sync_meta[team_id] = result
    state.fantrax_sync_meta["Team 1"] = result
    if result.get("team_name"):
        state.fantrax_sync_meta[result["team_name"]] = result
    state.save()
    return result

@app.post("/api/teams/{team_id}/lineup/swap")
async def swap_lineup_player(team_id: str, request: Request):
    state = DraftState()
    data = await request.json()
    starter_name = data.get("starter")
    bench_name = data.get("bench")

    roster = state.get_team(team_id)
    weekly_lineup = weekly_engine.get_optimal_lineup(roster)
    current_starters = state.custom_lineups.get(team_id)
    if not current_starters:
        current_starters = [p['player'] for p in weekly_lineup['starters']]

    new_starters = []
    for s in current_starters:
        if s == starter_name:
            new_starters.append(bench_name)
        else:
            new_starters.append(s)

    state.custom_lineups[team_id] = new_starters
    state.save()
    return {"success": True, "starters": new_starters}

@app.post("/api/teams/{team_id}/lineup/reset")
async def reset_lineup(team_id: str):
    state = DraftState()
    if team_id in state.custom_lineups:
        del state.custom_lineups[team_id]
        state.save()
    return {"success": True}

# --- Waiver Wire & Transaction Routes ---
@app.get("/waivers")
async def get_waiver_wire(
    request: Request,
    team: Optional[str] = None,
    position: Optional[str] = "ALL"
):
    state = DraftState()
    teams_data = state.get_all_teams()
    tracked_teams = [t for t in teams_data.keys() if t != 'Other']
    selected_team = team if team in teams_data else (state.my_team if state.my_team in teams_data else (tracked_teams[0] if tracked_teams else "Sam"))

    suggestions = waiver_engine.get_pickup_recommendations(
        team_name=selected_team,
        state=state,
        position_filter=position,
        limit=20
    )

    transactions = getattr(state, 'transactions_history', [])[::-1]

    return templates.TemplateResponse(
        request=request,
        name="waivers.html",
        context={
            "selected_team": selected_team,
            "selected_position": position.upper() if position else "ALL",
            "suggestions": suggestions,
            "transactions": transactions,
            "tracked_teams": tracked_teams,
            "team_roster": state.get_team(selected_team),
            "draft_status": None,
            "drafted_player": None
        }
    )

@app.post("/api/transactions/add")
async def add_player_transaction(request: Request):
    try:
        data = await request.json()
        team_name = data.get("team")
        player_name = data.get("player")
        dropped_player_name = data.get("dropped_player")
        notes = data.get("notes")

        if not team_name or not player_name:
            return JSONResponse({"status": "error", "message": "Team and player name required"}, status_code=400)

        state = DraftState()
        player_info = config.get_player_adp(player_name) or {
            "player": player_name,
            "position": data.get("position", "M"),
            "team": data.get("team_code", "TBD"),
            "fpg": data.get("fpg", 0.0),
            "fpts": data.get("fpts", 0.0),
            "adp": 999
        }

        success = state.add_player_to_team(
            team_name=team_name,
            player=player_info,
            dropped_player_name=dropped_player_name,
            notes=notes or f"Waiver pickup ({player_info.get('position', 'M')})"
        )

        return JSONResponse({"status": "success", "message": f"Added {player_name} to {team_name}"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/api/transactions/drop")
async def drop_player_transaction(request: Request):
    try:
        data = await request.json()
        team_name = data.get("team")
        player_name = data.get("player")

        if not team_name or not player_name:
            return JSONResponse({"status": "error", "message": "Team and player name required"}, status_code=400)

        state = DraftState()
        state.drop_player_from_team(team_name=team_name, player_name=player_name, notes="Roster drop")
        return JSONResponse({"status": "success", "message": f"Dropped {player_name} from {team_name}"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

# --- Helper Functions ---
def paginate(data: list, page: int, page_size: int):
    total_items = len(data)
    total_pages = math.ceil(total_items / page_size)
    start = (page - 1) * page_size
    end = start + page_size
    items_on_page = data[start:end]
    return {
        "players": items_on_page, "page": page, "page_size": page_size,
        "total_items": total_items, "total_pages": total_pages
    }



