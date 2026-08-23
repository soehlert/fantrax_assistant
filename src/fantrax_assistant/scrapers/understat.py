import json
from typing import Dict, Optional, List, Any
import requests
import pandas as pd
import redis
from scipy.stats import percentileofscore

UNDERSTAT_BASE_URL = "https://understat.com"
AJAX_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


class Understat:
    """Direct, native Understat client without legacy Selenium dependencies."""

    def __init__(self):
        self._session = requests.Session()
        self._redis = redis.Redis(host='localhost', port=6380, db=0, socket_timeout=1)
        self._memory_cache: Dict[str, List[Dict]] = {}

    def _request_ajax(self, endpoint: str) -> Dict[str, Any]:
        url = f"{UNDERSTAT_BASE_URL}/{endpoint}"
        resp = self._session.get(url, headers=AJAX_HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def get_player_data(self, player_id: str) -> List[Dict]:
        """Fetch shot-level data for a player."""
        data = self._request_ajax(f"getPlayerData/{player_id}")
        return data.get("shots", [])

    def get_all_players_data(
        self, league: str = "EPL", season: str = "2024"
    ) -> List[Dict]:
        """Fetch all player stats for a league and season."""
        cache_key = f"understat:league:{league}:{season}"

        # 1. Try Redis cache if running
        try:
            cached_data = self._redis.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception:
            pass

        # 2. Try in-memory cache fallback
        if cache_key in self._memory_cache:
            return self._memory_cache[cache_key]

        # 3. Fetch directly from Understat AJAX API
        data_dict = self._request_ajax(f"getLeagueData/{league}/{season}")
        players = data_dict.get("players", [])
        self._memory_cache[cache_key] = players

        # 4. Save to Redis if available
        try:
            self._redis.set(cache_key, json.dumps(players), ex=86400)  # Cache for 24 hours
        except Exception:
            pass

        return players

    def get_player_data_by_name(
        self, player_name: str, league: str, season: str, player_position: Optional[str] = None
    ) -> Optional[Dict]:
        import unicodedata
        def norm(s: str) -> str:
            return ''.join(
                c for c in unicodedata.normalize('NFD', str(s))
                if unicodedata.category(c) != 'Mn'
            ).lower().replace('-', ' ').replace('.', '').strip()

        players = self.get_all_players_data(league=league, season=season)
        target = norm(player_name)

        # 1. Exact normalized match
        for p in players:
            if norm(p["player_name"]) == target:
                return p

        # 2. Position-filtered token overlap / substring match
        target_pos = (player_position or "").split(",")[0].strip().upper()
        target_tokens = set(target.split())
        for p in players:
            p_norm = norm(p["player_name"])
            p_tokens = set(p_norm.split())
            p_pos = p.get("position", "").split(" ")[0].upper()

            if len(target_tokens) > 1 and target_tokens.issubset(p_tokens):
                if not target_pos or target_pos in p_pos or p_pos in target_pos:
                    return p
            elif target in p_norm:
                if len(target_tokens) > 1 or (target_pos and (target_pos in p_pos or p_pos in target_pos)):
                    return p

        return None

    def get_positional_data(
        self, player_position: str, league: str, season: str
    ) -> pd.DataFrame:
        players = self.get_all_players_data(league=league, season=season)
        
        positional_players = [
            p for p in players if p["position"].split(" ")[0] == player_position
        ]
        
        if not positional_players:
            return pd.DataFrame()

        df = pd.DataFrame(positional_players)
        cols = ["goals", "npg", "xG", "npxG", "assists", "xA", "shots", "key_passes", "xGChain", "xGBuildup"]
        for col in cols:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        return df

    def get_player_percentiles(
        self, player_data: Dict, positional_data: pd.DataFrame
    ) -> Dict:
        if positional_data.empty:
            return {}

        cols = ["goals", "npg", "xG", "npxG", "assists", "xA", "shots", "key_passes", "xGChain", "xGBuildup"]
        percentiles = {}
        for col in cols:
            player_value = float(player_data.get(col, 0))
            if col in positional_data.columns:
                percentiles[col] = percentileofscore(positional_data[col], player_value)
            else:
                percentiles[col] = 0.0
            
        return percentiles
