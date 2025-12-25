import math
import json
from contextlib import asynccontextmanager
from typing import Annotated # Annotated is standard in Python 3.9+

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fantrax_assistant.config import DraftConfig
from fantrax_assistant.suggest import PlayerRecommendationEngine
from fantrax_assistant.draft_state import DraftState

# --- App Setup ---
config = DraftConfig()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load all data on startup
    config.load_all_data()
    yield
    # Clean up resources if needed on shutdown

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="src/web/static"), name="static")
templates = Jinja2Templates(directory="src/web/templates")

# --- Routes ---
# Note: In a real-world scenario, you'd have a proper database and a more robust
# way of managing state. For this tool, we are reading/writing from JSON on each
# request that modifies state, which is not ideal for high concurrency but works
# for a local, single-user tool.

@app.get("/api/players/autocomplete")
async def autocomplete_players(q: str = ""):
    """Endpoint for player name autocomplete."""
    if len(q) < 2:
        return JSONResponse({"players": []})

    with open("data/draft_state.json", "r") as f:
        draft_state = json.load(f)
    all_drafted_player_names = draft_state.get("drafted_players", [])
    
    all_available = config.get_all_available_players(set(all_drafted_player_names))
    
    matches = [
        p["player"] for p in all_available 
        if q.lower() in p["player"].lower()
    ]
    
    return JSONResponse({"players": matches[:10]})


@app.get("/", response_class=HTMLResponse)
async def read_root(
    request: Request,
    page_available: int = 1,
    page_drafted: int = 1,
    search: str = "",
    search_drafted: str = ""
):
    with open("data/draft_state.json", "r") as f:
        draft_state = json.load(f)

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

        enriched_player = {
            **player,
            'adp': player.get('adp'),
            'fpts': player.get('fpts'),
            'fpg': player.get('fpg'),
            'injury_severity': injury.get('severity', 'Healthy'),
            'at_afcon': afcon.get('at_afcon', False)
        }

        if player_name in drafted_player_names:
            # Find owner
            owner_team = None
            for team_id, roster in teams_data.items():
                if any(p.get('player') == player_name for p in roster):
                    owner_team = team_id
                    break

            enriched_player['owner'] = owner_team
            enriched_player['team_id'] = owner_team
            drafted_players.append(enriched_player)
        else:
            available_players.append(enriched_player)

    # Sort by FPTS (descending)
    drafted_players.sort(key=lambda p: p.get('fpts', 0), reverse=True)
    available_players.sort(key=lambda p: p.get('fpts', 0), reverse=True)

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
            "tracked_teams": list(teams_data.keys())
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
    return RedirectResponse(
        url=f"{base_url}?draft_status=success&message=Marked {exact_name} as drafted",
        status_code=303
    )


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
    with open("data/draft_state.json", "r") as f:
        draft_state = json.load(f)
    teams_data = draft_state.get("teams", {})
    all_drafted_player_names = draft_state.get("drafted_players", [])
    
    if team_id not in teams_data:
        raise HTTPException(status_code=404, detail="Team not found")

    roster = teams_data.get(team_id, [])
    team_name = team_id
    roster_rules = config.get_roster_rules()

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

    # Get suggestions using the backend engine
    drafted_names = set(all_drafted_player_names)
    engine = PlayerRecommendationEngine(config=config, my_team=roster, drafted_players=drafted_names)
    
    num_teams = len(teams_data) if teams_data else 10
    current_round = (len(drafted_names) // num_teams) + 1
    
    suggestions = engine.get_recommendations(current_round=current_round, n=100)

    for player in suggestions:
        player_name = player.get('player', '')
        injury = config.get_player_injury(player_name)
        afcon = config.get_player_afcon_status(player_name)

        player['injury_severity'] = injury.get('severity', 'Healthy')
        player['at_afcon'] = afcon.get('at_afcon', False)

        if exclude_teams:
            excluded_teams = set(t.strip().upper() for t in exclude_teams.split(',') if t.strip())
        else:
            excluded_teams = set()

        if exclude_positions:
            excluded_positions = set(p.strip().upper() for p in exclude_positions.split(',') if p.strip())
        else:
            excluded_positions = set()

        filtered_suggestions = [
            p for p in suggestions
            if p.get('team', '').upper() not in excluded_teams and p.get('position', '')[0].upper() not in excluded_positions
        ]

        suggestions_pagination = paginate(filtered_suggestions, page_suggestions, 10)

    return templates.TemplateResponse(
        request=request, name="team.html",
        context={
            "team_name": team_name,
            "roster": roster,
            "position_breakdown": position_breakdown,
            "suggestions": suggestions_pagination,
            "draft_status": draft_status,
            "drafted_player": drafted_player,
            "tracked_teams": list(teams_data.keys()),
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



