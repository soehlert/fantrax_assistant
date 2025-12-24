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
            else:
                # File doesn't exist (first run), create default
                self.teams = {"Team 1": []}
                self.my_team = "Team 1"
                self.drafted_players = set()
        except Exception as e:
            print(f"Error loading draft state: {e}")
            self.teams = {"Team 1": []}
            self.my_team = "Team 1"
            self.drafted_players = set()

    def save(self) -> bool:
        """Save draft state to file."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            data = {
                'last_updated': datetime.now().isoformat(),
                'my_team': self.my_team,
                'drafted_players': list(self.drafted_players),
                'teams': self.teams
            }

            with self.state_file.open('w') as f:
                json.dump(data, f, indent=2)

            return True
        except Exception as e:
            print(f"Error saving draft state: {e}")
            return False

    def add_to_team(self, player: dict, team_name: str = "Team 1"):
        """Add player to specific team."""
        if team_name not in self.teams:
            self.teams[team_name] = []

        player_name = player.get('player')

        # Check if player is already drafted by ANYONE
        if player_name in self.drafted_players:
            print(f"Error: {player_name} has already been drafted")
            return False

        # Check if player already on this specific team (shouldn't happen, but safety check)
        if any(p['player'] == player_name for p in self.teams[team_name]):
            print(f"Error: {player_name} already on {team_name}")
            return False

        # Add player
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
        self.save()
        return True


    def get_team(self, team_name: str) -> list:
        """Get a specific team's roster."""
        return self.teams.get(team_name, [])

    def get_all_teams(self) -> dict:
        """Get all teams."""
        return self.teams

    def mark_drafted(self, player_name: str):
        """Mark player as drafted by opponent."""
        self.drafted_players.add(player_name)
        self.save()

    def reset(self):
        """Reset draft state."""
        self.teams = {"Team 1": []}
        self.drafted_players = set()
        self.save()
