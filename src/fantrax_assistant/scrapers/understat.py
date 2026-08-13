import json
from typing import Dict, Optional, List

import pandas as pd
import redis
from understatapi import UnderstatClient


from scipy.stats import percentileofscore

class Understat:
    def __init__(self):
        self._client = UnderstatClient()
        self._redis = redis.Redis(host='localhost', port=6380, db=0, socket_timeout=1)
        self._memory_cache: Dict[str, List[Dict]] = {}

    def get_player_data(self, player_id: str) -> Dict:
        return self._client.player(player=player_id).get_shot_data()

    def get_all_players_data(
        self, league: str, season: str
    ) -> List[Dict]:
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

        # 3. Fetch from Understat API
        data = self._client.league(league=league).get_player_data(season=season)
        self._memory_cache[cache_key] = data

        # 4. Save to Redis if available
        try:
            self._redis.set(cache_key, json.dumps(data), ex=86400)  # Cache for 24 hours
        except Exception:
            pass

        return data

    def get_player_data_by_name(
        self, player_name: str, league: str, season: str
    ) -> Optional[Dict]:
        import unicodedata
        def norm(s: str) -> str:
            return ''.join(
                c for c in unicodedata.normalize('NFD', s)
                if unicodedata.category(c) != 'Mn'
            ).lower().replace('-', ' ').replace('.', '').strip()

        players = self.get_all_players_data(league=league, season=season)
        target = norm(player_name)

        # 1. Exact normalized match
        for p in players:
            if norm(p["player_name"]) == target:
                return p

        # 2. Token overlap / substring match (e.g. Gabriel Magalhaes -> Gabriel)
        target_tokens = set(target.split())
        for p in players:
            p_norm = norm(p["player_name"])
            p_tokens = set(p_norm.split())
            if target in p_norm or p_norm in target or (len(target_tokens) > 1 and target_tokens.issubset(p_tokens)):
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
        for col in ["npg", "xG", "xA", "shots", "key_passes"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["npg", "xG", "xA", "shots", "key_passes"])
        return df

    def get_player_percentiles(
        self, player_data: Dict, positional_data: pd.DataFrame
    ) -> Dict:
        if positional_data.empty:
            return {}

        percentiles = {}
        for col in ["npg", "xG", "xA", "shots", "key_passes"]:
            player_value = float(player_data.get(col, 0))
            percentiles[col] = percentileofscore(positional_data[col], player_value)
            
        return percentiles

