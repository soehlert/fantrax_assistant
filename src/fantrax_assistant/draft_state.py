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
            else:
                self.teams = {"Team 1": []}
                self.my_team = "Team 1"
                self.drafted_players = set()
                self.draft_history = []
                self.save()
        except Exception as e:
            print(f"Error loading draft state: {e}")
            self.teams = {"Team 1": []}
            self.my_team = "Team 1"
            self.drafted_players = set()
            self.draft_history = []
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
                'teams': self.teams
            }

            with self.state_file.open('w') as f:
                json.dump(data, f, indent=2)

            return True
        except Exception as e:
            print(f"Error saving draft state: {e}")
            return False

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
        if player_name in self.draft_history:
            self.draft_history.remove(player_name)
        self.draft_history.append(player_name)
        self.save()
        return True

    def mark_drafted(self, player_name: str):
        """Mark a player as drafted by an untracked team."""
        self.drafted_players.add(player_name)
        if player_name in self.draft_history:
            self.draft_history.remove(player_name)
        self.draft_history.append(player_name)
        self.save()

    def undraft_player(self, player_name: str):
        """Remove player from drafted_players set and all team rosters."""
        self.remove_from_teams(player_name)
        self.drafted_players.discard(player_name)
        if player_name in self.draft_history:
            self.draft_history.remove(player_name)
        self.save()


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

    def mark_drafted(self, player_name: str):
        """Mark player as drafted by opponent."""
        self.drafted_players.add(player_name)
        self.save()

    def reset(self):
        """Reset draft state."""
        self.teams = {"Team 1": []}
        self.drafted_players = set()
        self.save()
