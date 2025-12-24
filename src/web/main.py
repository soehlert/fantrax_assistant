import math
import json
from contextlib import asynccontextmanager
from typing import Annotated # Annotated is standard in Python 3.9+

from fastapi import FastAPI, Request, Form
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
async def read_root(request: Request, page_available: int = 1, page_drafted: int = 1):
    PAGE_SIZE = 15
    with open("data/draft_state.json", "r") as f:
        draft_state = json.load(f)
    all_drafted_player_names = draft_state.get("drafted_players", [])
    
    # This logic rebuilds the drafted list on every request to ensure it's fresh
    teams_data = draft_state.get("teams", {})
    tracked_player_details = {}
    for owner_name, roster in teams_data.items():
        for player_obj in roster:
            player_name = player_obj.get("player")
            if player_name:
                details = player_obj.copy()
                details["owner"] = owner_name
                details["team_id"] = owner_name
                tracked_player_details[player_name] = details

    drafted_players = []
    for player_name in all_drafted_player_names:
        if player_name in tracked_player_details:
            drafted_players.append(tracked_player_details[player_name])
        else:
            drafted_players.append({
                "player": player_name, "owner": "Untracked", "team_id": None, "adp": "N/A",
                "fpts": "N/A", "fpg": "N/A", "position": "N/A", "team": "N/A"
            })

    all_available = config.get_all_available_players(set(all_drafted_player_names))
    available_pagination = paginate(all_available, page_available, PAGE_SIZE)
    drafted_pagination = paginate(drafted_players, page_drafted, PAGE_SIZE)

    return templates.TemplateResponse(
        request=request, name="index.html",
        context={"available": available_pagination, "drafted": drafted_pagination}
    )

@app.get("/teams/{team_id}", response_class=HTMLResponse)
async def read_team(
    request: Request,
    team_id: str,
    page_suggestions: int = 1,
    draft_status: str = None,
    drafted_player: str = None
):
    with open("data/draft_state.json", "r") as f:
        draft_state = json.load(f)
    teams_data = draft_state.get("teams", {})
    all_drafted_player_names = draft_state.get("drafted_players", [])
    
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
    suggestions_pagination = paginate(suggestions, page_suggestions, 10)

    return templates.TemplateResponse(
        request=request, name="team.html",
        context={
            "team_name": team_name,
            "roster": roster,
            "position_breakdown": position_breakdown,
            "suggestions": suggestions_pagination,
            "draft_status": draft_status,
            "drafted_player": drafted_player
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



