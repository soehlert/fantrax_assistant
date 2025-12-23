"""Configuration loader for draft assistant."""

import json
from pathlib import Path
from typing import Optional


class DraftConfig:
    """
    Loads and manages all configuration and data for the draft assistant.
    """

    def __init__(self, data_dir: str | Path = 'data'):
        self.data_dir = Path(data_dir)
        self.stats: Optional[dict] = None
        self.injuries: Optional[dict] = None
        self.rankings: Optional[dict] = None
        self.league_config: Optional[dict] = None
        self.afcon: Optional[dict] = None

    def load_all_data(self) -> bool:
        """Load all data files."""
        print("Loading data files...")

        self.stats = self._load_json('current_stats.json')
        self.injuries = self._load_json('injuries.json')
        self.rankings = self._load_json('adp_rankings.json')
        self.league_config = self._load_json('league_config.json')
        self.afcon = self._load_json('afcon_callups.json')

        # Validate critical data
        if not self.league_config:
            print("✗ Missing league_config.json")
            return False

        if not self.rankings:
            print("✗ Missing adp_rankings.json")
            return False

        # Stats and injuries are optional but warn if missing
        if not self.stats:
            print("⚠ Warning: No current stats loaded")

        if not self.injuries:
            print("⚠ Warning: No injury data loaded")

        print("✓ All critical data loaded successfully")
        return True

    def _load_json(self, filename: str) -> Optional[dict]:
        """Load a JSON file."""
        filepath = self.data_dir / filename

        if not filepath.exists():
            print(f"Warning: {filename} not found")
            return None

        try:
            with filepath.open('r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {filename}: {e}")
            return None

    def _fuzzy_match_name(self, search_name: str, candidate_name: str) -> bool:
        """
        Check if two player names match using fuzzy logic.
        Handles cases like 'Richarlison' vs 'Richarlison de Andrade'
        """
        search_lower = search_name.lower().strip()
        candidate_lower = candidate_name.lower().strip()

        # Exact match
        if search_lower == candidate_lower:
            return True

        # Check if search name is contained in candidate (e.g., "Richarlison" in "Richarlison de Andrade")
        if search_lower in candidate_lower:
            return True

        # Check if candidate is contained in search
        if candidate_lower in search_lower:
            return True

        # Split names and check if all parts of search are in candidate
        search_parts = search_lower.split()
        candidate_parts = candidate_lower.split()

        # If all search parts are in candidate parts, it's a match
        if all(any(sp in cp for cp in candidate_parts) for sp in search_parts):
            return True

        return False

    def get_player_stats(self, player_name: str) -> Optional[dict]:
        """Get current season stats for a player using fuzzy matching."""
        if not self.stats or 'players' not in self.stats:
            return None

        for player in self.stats['players']:
            if self._fuzzy_match_name(player_name, player.get('name', '')):
                return player

        return None

    def get_player_afcon_status(self, player_name: str) -> dict:
        """Check if player is called up for AFCON."""
        if not self.afcon or 'players' not in self.afcon:
            return {'at_afcon': False}

        for player in self.afcon['players']:
            if self._fuzzy_match_name(player_name, player.get('player', '')):
                return {
                    'at_afcon': True,
                    'country': player.get('country', 'Unknown'),
                    'club': player.get('club', 'Unknown'),
                    'start_date': self.afcon.get('start_date'),
                    'end_date': self.afcon.get('end_date')
                }

        return {'at_afcon': False}


    def get_player_injury(self, player_name: str) -> dict:
        """Get injury status for a player using fuzzy matching."""
        if not self.injuries or 'injuries' not in self.injuries:
            return {'status': 'Unknown', 'severity': 'Unknown'}

        for injury in self.injuries['injuries']:
            if self._fuzzy_match_name(player_name, injury.get('player', '')):
                return injury

        return {'status': 'Healthy', 'severity': 'Healthy'}

    def get_player_adp(self, player_name: str) -> Optional[dict]:
        """Get ADP/ranking for a player using fuzzy matching."""
        if not self.rankings or 'rankings' not in self.rankings:
            return None

        for ranking in self.rankings['rankings']:
            if self._fuzzy_match_name(player_name, ranking.get('player', '')):
                return ranking

        return None

    def get_all_available_players(self, drafted_players: set) -> list[dict]:
        """Get all players not yet drafted, enriched with stats and injury data."""
        all_players = self.rankings.get('rankings', [])

        available = []

        for player in all_players:
            player_name = player.get('player', '')

            # Check if drafted using fuzzy matching (case-insensitive)
            is_drafted = False
            for drafted in drafted_players:
                if self._fuzzy_match_name(player_name, drafted):
                    is_drafted = True
                    break

            # Skip if already drafted
            if is_drafted:
                continue

            # Enrich with stats and injury data
            player['stats'] = self.get_player_stats(player_name)
            player['injury'] = self.get_player_injury(player_name)

            available.append(player)

        return available

    def get_scoring_rules(self) -> dict:
        """Get league scoring rules."""
        if not self.league_config:
            return {}
        return self.league_config.get('scoring_rules', {})

    def get_roster_rules(self) -> dict:
        """Get roster composition rules."""
        if not self.league_config:
            return {}
        return self.league_config.get('roster_rules', {})

    def create_league_config_template(self) -> bool:
        """Create a template league configuration file."""
        template = {
            "league_name": "My Fantasy League",
            "league_id": "your_league_id",
            "season": "2025-26",
            "total_rounds": 16,
            "scoring_rules": {
                "goals_forward": 4,
                "goals_midfielder": 5,
                "goals_defender": 6,
                "assists_official": 3,
                "assists_secondary": 1,
                "assists_fantasy": 2,
                "big_chances_created": 1,
                "games_played": 1,
                "games_started": 1,
                "own_goals": -2,
                "interceptions_per_game": 0.33,
                "penalties_conceded": -1,
                "penalty_kicks_missed": -2,
                "red_cards": -3,
                "shots_on_target_per_game": 0.5,
                "clean_sheets_midfielder": 1,
                "clean_sheets_defender": 4,
                "tackles_won_per_game": 0.33,
                "yellow_cards": -1,
                "goalkeeper_assists_official": 3,
                "goalkeeper_clean_sheets": 5,
                "goalkeeper_saves_per_game": 0.33,
                "goalkeeper_goals_against_per_game": -0.5
            },
            "roster_rules": {
                "DEF": 5,
                "MID": 5,
                "FWD": 4,
                "GK": 1
            }
        }

        filepath = self.data_dir / 'league_config.json'
        self.data_dir.mkdir(exist_ok=True)

        with filepath.open('w') as f:
            json.dump(template, f, indent=2)

        print(f"✓ Created league config template at {filepath}")
        print("Please edit this file with your league's specific settings")
        return True


if __name__ == "__main__":
    # Create data directory if it doesn't exist
    Path('data').mkdir(exist_ok=True)

    # Create config template
    config = DraftConfig()
    config.create_league_config_template()
