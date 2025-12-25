import json
from typing import Dict, Optional, List

import pandas as pd
from understatapi import UnderstatClient


from scipy.stats import percentileofscore

class Understat:
    def __init__(self):
        self._client = UnderstatClient()

    def get_player_data(self, player_id: str) -> Dict:
        return self._client.player(player=player_id).get_shot_data()

    def get_all_players_data(
        self, league: str, season: str
    ) -> List[Dict]:
        return self._client.league(league=league).get_player_data(season=season)

    def get_player_data_by_name(
        self, player_name: str, league: str, season: str
    ) -> Optional[Dict]:
        players = self.get_all_players_data(league=league, season=season)
        for player in players:
            if player["player_name"] == player_name:
                return player
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

