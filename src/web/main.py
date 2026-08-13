import math
import json
from contextlib import asynccontextmanager
from typing import Annotated # Annotated is standard in Python 3.9+

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
config = DraftConfig()
understat = Understat()
analyzer = DraftPickAnalyzer(config=config)
db_mgr = DatabaseManager("data/fantrax_assistant.db")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load all data on startup
    config.load_all_data()
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
async def autocomplete_players(q: str = ""):
    """Endpoint for player name autocomplete (excludes already drafted players)."""
    if len(q) < 2:
        return JSONResponse({"players": []})

    draft_state = get_draft_state_dict()
    drafted_names = set(draft_state.get("drafted_players", []))

    all_players = config.rankings.get('rankings', []) if config.rankings else []

    seen = set()
    matches = []
    for p in all_players:
        name = p.get("player", "")

        # Skip if player is already drafted
        if any(config._fuzzy_match_name(name, d) for d in drafted_names):
            continue

        if q.lower() in name.lower() and name not in seen:
            seen.add(name)
            matches.append(name)
            if len(matches) >= 10:
                break

    return JSONResponse({"players": matches})


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
            "tracked_teams": [t for t in teams_data.keys() if t != 'Other']
        }
    )

@app.post("/draft/mark_drafted")
async def mark_player_drafted(request: Request, player_name: Annotated[str, Form()]):
    """Marks a player as drafted by an untracked team."""
    state = DraftState()
    player_details = config.get_player_adp(player_name)
    base_url = request.url_for('read_root')

    if not player_details:
        return RedirectResponse(
            url=f"{base_url}?draft_status=error&message=Player '{player_name}' not found",
            status_code=303
        )
    
    exact_name = player_details['player']
    if exact_name in state.drafted_players:
        return RedirectResponse(
            url=f"{base_url}?draft_status=error&message={exact_name} is already drafted",
            status_code=303
        )

    state.mark_drafted(exact_name)
    pick_num = len(state.drafted_players)
    analysis = analyzer.grade_pick(
        player_name=exact_name,
        team_id='Other',
        overall_pick_num=pick_num,
        player_adp=player_details.get('adp'),
        player_pos=player_details.get('position', ''),
        player_team=player_details.get('team', ''),
        team_roster=[]
    )
    state.add_pick_analysis(analysis)

    return RedirectResponse(
        url=f"{base_url}?draft_status=success&message=Marked {exact_name} as drafted",
        status_code=303
    )

@app.post("/draft/undraft")
async def undraft_player_endpoint(request: Request, player_name: Annotated[str, Form()]):
    """Undrafts a player, returning them to the available pool."""
    state = DraftState()
    state.undraft_player(player_name)
    referer = request.headers.get("referer") or str(request.url_for('read_root'))
    return RedirectResponse(url=referer, status_code=303)


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
    
    num_teams = len(teams_data) if teams_data else 10
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
        a_data = grade_lookup.get(player.get("player"), {})
        player["id"] = db_mgr.get_player_id_by_name(player.get("player")) or player.get("player")
        player["grade"] = a_data.get("grade", "—")
        player["grade_class"] = a_data.get("grade_class", "blue")
        player["pick_number"] = a_data.get("pick_number")

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

    # Sort club breakdown in alphabetical order by team code
    club_breakdown.sort(key=lambda x: x["code"])

    suggestions_pagination = get_team_suggestions_pagination(
        team_id=team_name, page=page_suggestions, page_size=10,
        exclude_teams=exclude_teams, exclude_positions=exclude_positions
    )

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
            "all_positions": ["G", "D", "M", "F"]
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

    base_url = request.url_for('read_team', team_id=team_id)

    if not player_details:
        # Player not found in the master list
        return RedirectResponse(
            url=f"{base_url}?draft_status=error&drafted_player=Player '{player_name}' not found",
            status_code=303
        )

    # Use the backend logic to add the player
    success = state.add_to_team(player_details, team_id)

    if success:
        pick_num = len(state.drafted_players)
        team_roster = state.teams.get(team_id, [])
        analysis = analyzer.grade_pick(
            player_name=player_details.get('player'),
            team_id=team_id,
            overall_pick_num=pick_num,
            player_adp=player_details.get('adp'),
            player_pos=player_details.get('position', ''),
            player_team=player_details.get('team', ''),
            team_roster=team_roster
        )
        state.add_pick_analysis(analysis)

        return RedirectResponse(
            url=f"{base_url}?draft_status=success&drafted_player={player_details.get('player')}",
            status_code=303
        )
    else:
        # Player was likely already drafted
        return RedirectResponse(
            url=f"{base_url}?draft_status=error&drafted_player={player_details.get('player')} is already drafted",
            status_code=303
        )

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

    return templates.TemplateResponse(
        request=request,
        name="analysis.html",
        context={
            "feed": analysis_history_sorted,
            "best_overall": best_overall,
            "top_steal": top_steal,
            "worst_pick": worst_pick,
            "tracked_teams": [t for t in teams_data.keys() if t != 'Other']
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
async def read_player_profile(request: Request, player_name: str):
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

    analysis_history = analyzer.backfill_retroactive_analysis(state)
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
    if not pl_stats:
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
                            "total_apps": max(starts, matches),
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

        target_pos = target_pl.get("position") if target_pl else None
        peers = [p for p in all_pl_players if p.get("position") == target_pos] if target_pos else all_pl_players

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
            if player_data and u_key in player_data and player_data.get(u_key) is not None:
                raw_val = float(player_data.get(u_key, 0) or 0)
            elif pl_stats and pl_key in pl_stats and pl_stats.get(pl_key) is not None:
                raw_val = float(pl_stats.get(pl_key, 0) or 0)
            elif target_pl and pl_key in target_pl:
                raw_val = float(target_pl.get(pl_key, 0) or 0)

            peer_vals = [float(p.get(pl_key, 0) or 0) for p in peers]
            pct = round(float(percentileofscore(peer_vals, raw_val, kind='weak')), 1) if peer_vals else 50.0

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
    inj_info = full_profile.get("injury") or {}
    injury_severity = inj_info.get("severity") or config.get_player_injury(player_name_clean).get("severity", "Healthy")
    injury_notes = inj_info.get("notes") or config.get_player_injury(player_name_clean).get("notes", "")
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

        all_available = [
            p for p in config.rankings.get("rankings", [])
            if p.get("player") not in state.drafted_players
            and p.get("player") != player_name_clean
        ]

        pos_match = [
            p for p in all_available
            if player_pos in p.get("position", "").upper().split(",")
        ] or all_available

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
            "tracked_teams": [t for t in draft_state_dict.get("teams", {}).keys() if t != 'Other'],
        }
    )

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



