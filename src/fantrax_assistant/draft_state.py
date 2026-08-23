"""Manage draft state (teams, drafted players)."""

import json
from pathlib import Path
from datetime import datetime


class DraftState:
    """Manage draft state persistence across multiple teams."""

    def __init__(self, state_file: str | Path = 'data/draft_state.json'):
        self.teams: dict[str, list] = {}
        self.my_team: str = "Team 1"
        self.state_file = Path(state_file)
        self.drafted_players: set[str] = set()
        self.draft_history: list[str] = []
        self.pick_analysis_history: list[dict] = []
        self.transactions_history: list[dict] = []
        self.custom_lineups: dict[str, list] = {}
        self.fantrax_sync_meta: dict[str, dict] = {}
        self.load()

    def load(self):
        """Load draft state from JSON."""
        try:
            if self.state_file.exists():
                with self.state_file.open('r') as f:
                    state = json.load(f)
                    self.teams = {k: v for k, v in state.get('teams', {}).items()}
                    self.my_team = state.get('my_team', "Team 1")
                    self.drafted_players = set(state.get('drafted_players', []))
                    self.draft_history = state.get('draft_history', list(self.drafted_players))
                    self.pick_analysis_history = state.get('pick_analysis_history', [])
                    self.transactions_history = state.get('transactions_history', [])
                    self.custom_lineups = state.get('custom_lineups', {})
                    self.fantrax_sync_meta = state.get('fantrax_sync_meta', {})
            else:
                self.teams = {"Team 1": []}
                self.my_team = "Team 1"
                self.drafted_players = set()
                self.draft_history = []
                self.pick_analysis_history = []
                self.transactions_history = []
                self.custom_lineups = {}
                self.fantrax_sync_meta = {}
                self.save()
        except Exception as e:
            print(f"Error loading draft state: {e}")
            self.teams = {"Team 1": []}
            self.my_team = "Team 1"
            self.drafted_players = set()
            self.draft_history = []
            self.pick_analysis_history = []
            self.transactions_history = []
            self.custom_lineups = {}
            self.fantrax_sync_meta = {}
            self.save()

    def save(self) -> bool:
        """Save draft state to file."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            data = {
                'last_updated': datetime.now().isoformat(),
                'my_team': self.my_team,
                'drafted_players': list(self.drafted_players),
                'draft_history': self.draft_history,
                'pick_analysis_history': self.pick_analysis_history,
                'transactions_history': self.transactions_history,
                'custom_lineups': self.custom_lineups,
                'fantrax_sync_meta': self.fantrax_sync_meta,
                'teams': self.teams
            }

            with self.state_file.open('w') as f:
                json.dump(data, f, indent=2)

            return True
        except Exception as e:
            print(f"Error saving draft state: {e}")
            return False

    def add_pick_analysis(self, analysis_item: dict):
        """Record pick analysis evaluation in history."""
        # Replace existing analysis if already present for this player
        self.pick_analysis_history = [p for p in self.pick_analysis_history if p.get('player') != analysis_item.get('player')]
        self.pick_analysis_history.append(analysis_item)
        self.save()

    def remove_from_teams(self, player_name: str):
        """Remove player from any team roster."""
        for team_name, roster in self.teams.items():
            self.teams[team_name] = [p for p in roster if p.get('player') != player_name]

    def add_to_team(self, player: dict, team_name: str = "Team 1"):
        """Add player to specific team, preventing duplicates."""
        if team_name not in self.teams:
            self.teams[team_name] = []

        player_name = player.get('player')

        if any(p['player'] == player_name for p in self.teams[team_name]):
            print(f"{player_name} is already on {team_name}")
            return False

        self.remove_from_teams(player_name)

        player_data = {
            'player': player.get('player'),
            'position': player.get('position'),
            'team': player.get('team'),
            'adp': player.get('adp'),
            'fpts': player.get('fpts'),
            'fpg': player.get('fpg')
        }
        self.teams[team_name].append(player_data)
        self.drafted_players.add(player_name)
        if player_name not in self.draft_history:
            self.draft_history.append(player_name)
        self.save()
        return True

    def mark_drafted(self, player_name: str):
        """Mark a player as drafted by an untracked team."""
        self.drafted_players.add(player_name)
        if player_name not in self.draft_history:
            self.draft_history.append(player_name)
        self.save()

    def record_transaction(self, tx_type: str, team_name: str, player_name: str, dropped_player: str = None, notes: str = None):
        """Record a transaction in the transaction log history."""
        tx_item = {
            'timestamp': datetime.now().isoformat(),
            'type': tx_type,
            'team': team_name,
            'player': player_name,
            'dropped_player': dropped_player,
            'notes': notes or ''
        }
        self.transactions_history.append(tx_item)
        self.save()

    def add_player_to_team(self, team_name: str, player: dict, dropped_player_name: str = None, notes: str = None) -> bool:
        """Add a free agent player to a team, optionally dropping another player."""
        if dropped_player_name:
            self.drop_player_from_team(team_name, dropped_player_name, notes=f"Dropped for {player.get('player')}")
        
        success = self.add_to_team(player, team_name)
        if success:
            tx_type = "ADD & DROP" if dropped_player_name else "ADD"
            self.record_transaction(tx_type, team_name, player.get('player'), dropped_player=dropped_player_name, notes=notes)
        return success

    def drop_player_from_team(self, team_name: str, player_name: str, notes: str = None) -> bool:
        """Drop a player from a team back to the free agent pool."""
        if team_name in self.teams:
            self.teams[team_name] = [p for p in self.teams[team_name] if p.get('player') != player_name]
        self.drafted_players.discard(player_name)
        if player_name in self.draft_history:
            self.draft_history.remove(player_name)
        self.record_transaction("DROP", team_name, player_name, notes=notes)
        self.save()
        return True

    def get_team(self, team_name: str) -> list:
        """Get a specific team's roster."""
        return self.teams.get(team_name, [])

    def get_all_teams(self) -> dict:
        """Get all teams."""
        return self.teams

    def find_team_name(self, team_input: str) -> str | None:
        """Find team name case-insensitively."""
        if not team_input:
            return None
        for team in self.teams.keys():
            if team.lower() == team_input.lower():
                return team
        return None

    def reset(self):
        """Reset draft state."""
        self.teams = {"Team 1": []}
        self.drafted_players = set()
        self.draft_history = []
        self.pick_analysis_history = []
        self.save()
