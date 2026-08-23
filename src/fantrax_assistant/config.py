"""Configuration loader for draft assistant."""

import json
import unicodedata
from pathlib import Path
from typing import Optional


def normalize_name(s: str) -> str:
    """Normalize string by removing accents, lowercasing, and stripping punctuation."""
    if not s:
        return ""
    return ''.join(
        c for c in unicodedata.normalize('NFD', str(s))
        if unicodedata.category(c) != 'Mn'
    ).lower().replace('-', ' ').replace('.', '').strip()


class DraftConfig:
    """
    Loads and manages all configuration and data for the draft assistant.
    """

    def __init__(self, data_dir: str | Path = 'data'):
        self.data_dir = Path(data_dir)
        self.stats: dict = {"players": []}
        self.injuries: dict = {"injuries": []}
        self.rankings: dict = {"rankings": []}
        self.league_config: dict = {}
        self.afcon: dict = {"players": []}
        self.set_pieces: dict = {}
        self._adp_map: dict = {}
        self._injury_map: dict = {}
        self._stats_map: dict = {}

    def load_all_data(self) -> bool:
        """Load all data files."""
        print("Loading data files...")

        self.stats = self._load_json('current_stats.json') or {"players": []}
        self.injuries = self._load_json('injuries.json') or {"injuries": []}
        self.rankings = self._load_json('adp_rankings.json') or {"rankings": []}
        self.league_config = self._load_json('league_config.json') or {}
        self.afcon = self._load_json('afcon_callups.json', quiet=True) or {"players": []}
        self.set_pieces = self._load_json('set_pieces.json', quiet=True) or {}

        # Pre-build fast O(1) lookup maps
        self._adp_map = {}
        if self.rankings and 'rankings' in self.rankings:
            for r in self.rankings['rankings']:
                norm = normalize_name(r.get('player', ''))
                if norm:
                    self._adp_map[norm] = r

        # Supplement rankings with players from SQLite database if missing (e.g. Goalkeepers)
        db_path = self.data_dir / "fantrax_assistant.db"
        if db_path.exists():
            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                c = conn.cursor()
                c.execute("SELECT name, position, team, adp, fpts, fpg FROM players")
                db_rows = c.fetchall()
                conn.close()
                for name, pos, team, adp, fpts, fpg in db_rows:
                    norm = normalize_name(name)
                    if norm and norm not in self._adp_map:
                        item = {
                            "rank": len(self.rankings.get('rankings', [])) + 1,
                            "player": name,
                            "position": pos,
                            "team": team,
                            "adp": float(adp or 999.0),
                            "fpts": float(fpts or 0.0),
                            "fpg": float(fpg or 0.0)
                        }
                        self._adp_map[norm] = item
                        if self.rankings and 'rankings' in self.rankings:
                            self.rankings['rankings'].append(item)
            except Exception as e:
                print(f"Warning: Failed to load supplementary DB players in DraftConfig: {e}")

        self._injury_map = {}
        if self.injuries and 'injuries' in self.injuries:
            for inj in self.injuries['injuries']:
                norm = normalize_name(inj.get('player', ''))
                if norm:
                    self._injury_map[norm] = inj

        self._stats_map = {}
        if self.stats and 'players' in self.stats:
            for st in self.stats['players']:
                norm = normalize_name(st.get('name', ''))
                if norm:
                    self._stats_map[norm] = st

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

    def _load_json(self, filename: str, quiet: bool = False) -> Optional[dict]:
        """Load a JSON file."""
        filepath = self.data_dir / filename

        if not filepath.exists():
            if not quiet:
                print(f"Warning: {filename} not found")
            return None

        try:
            with filepath.open('r') as f:
                return json.load(f)
        except Exception as e:
            if not quiet:
                print(f"Error loading {filename}: {e}")
            return None

    def _fuzzy_match_name(self, search_name: str, candidate_name: str) -> bool:
        """
        Check if two player names refer to the same player.
        """
        if not search_name or not candidate_name:
            return False

        s_lower = search_name.lower().strip()
        c_lower = candidate_name.lower().strip()

        # 1. Exact match
        if s_lower == c_lower:
            return True

        # 2. Strip accents for comparison
        import unicodedata
        s_norm = "".join(c for c in unicodedata.normalize('NFD', s_lower) if unicodedata.category(c) != 'Mn')
        c_norm = "".join(c for c in unicodedata.normalize('NFD', c_lower) if unicodedata.category(c) != 'Mn')

        if s_norm == c_norm:
            return True

        s_words = [w for w in s_norm.split() if len(w) > 1]
        c_words = [w for w in c_norm.split() if len(w) > 1]

        # Single-word names must match exactly (e.g. "Rayan" is not "Rayan Cherki")
        if len(s_words) == 1 or len(c_words) == 1:
            return False

        s_set = set(s_words)
        c_set = set(c_words)

        if s_set.issubset(c_set) or c_set.issubset(s_set):
            return True

        return False

    def get_player_stats(self, player_name: str) -> Optional[dict]:
        """Get current season stats for a player using fast O(1) lookup."""
        if not self.stats or 'players' not in self.stats:
            return None

        norm = normalize_name(player_name)
        if norm and hasattr(self, '_stats_map') and norm in self._stats_map:
            return self._stats_map[norm]

        for player in self.stats['players']:
            p_name = player.get('name', '')
            p_web = player.get('web_name', '')
            if self._fuzzy_match_name(player_name, p_name) or self._fuzzy_match_name(player_name, p_web) or normalize_name(player_name) == normalize_name(p_web):
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

    def get_player_set_piece_status(self, player_name: str) -> dict:
        """Check if player is designated penalty taker or set-piece taker."""
        if not self.set_pieces or 'players' not in self.set_pieces:
            return {'is_pk_taker': False, 'is_set_piece_taker': False}

        for name, info in self.set_pieces.get('players', {}).items():
            if self._fuzzy_match_name(player_name, name):
                return info

        return {'is_pk_taker': False, 'is_set_piece_taker': False}

    def get_player_injury(self, player_name: str) -> dict:
        """Get injury status for a player using fast O(1) lookup."""
        if not self.injuries or 'injuries' not in self.injuries:
            return {'status': 'Unknown', 'severity': 'Unknown'}

        norm = normalize_name(player_name)
        if norm and hasattr(self, '_injury_map') and norm in self._injury_map:
            return self._injury_map[norm]

        for injury in self.injuries['injuries']:
            if self._fuzzy_match_name(player_name, injury.get('player', '')):
                return injury

        return {'status': 'Healthy', 'severity': 'Healthy'}

    def get_player_adp(self, player_name: str) -> Optional[dict]:
        """Get ADP/ranking for a player using fast O(1) lookup."""
        if not self.rankings or 'rankings' not in self.rankings:
            return None

        norm = normalize_name(player_name)
        if norm and hasattr(self, '_adp_map') and norm in self._adp_map:
            return self._adp_map[norm]

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
