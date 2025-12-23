"""Manage draft state (drafted players, my team)."""

import json
from pathlib import Path
from datetime import datetime


class DraftState:
    """Manage draft state persistence."""

    def __init__(self, state_file: str | Path = 'data/draft_state.json'):
        self.state_file = Path(state_file)
        self.drafted_players: set[str] = set()
        self.my_team: list[dict] = []
        self.load()

    def load(self) -> bool:
        """Load draft state from file."""
        if not self.state_file.exists():
            return False

        try:
            with self.state_file.open('r') as f:
                data = json.load(f)

            self.drafted_players = set(data.get('drafted_players', []))
            self.my_team = data.get('my_team', [])

            return True
        except Exception as e:
            print(f"Error loading draft state: {e}")
            return False

    def save(self) -> bool:
        """Save draft state to file."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            data = {
                'last_updated': datetime.now().isoformat(),
                'drafted_players': list(self.drafted_players),
                'my_team': self.my_team
            }

            with self.state_file.open('w') as f:
                json.dump(data, f, indent=2)

            return True
        except Exception as e:
            print(f"Error saving draft state: {e}")
            return False

    def add_to_my_team(self, player: dict):
        """Add player to my team."""
        # Check if player already on team
        player_name = player.get('player')
        if any(p['player'] == player_name for p in self.my_team):
            print(f"Warning: {player_name} already on team")
            return

        # Ensure we save all necessary data
        player_data = {
            'player': player.get('player'),
            'position': player.get('position'),
            'team': player.get('team'),
            'adp': player.get('adp'),
            'fpts': player.get('fpts'),
            'fpg': player.get('fpg')
        }
        self.my_team.append(player_data)
        self.drafted_players.add(player['player'])
        self.save()


    def mark_drafted(self, player_name: str):
        """Mark player as drafted by opponent."""
        self.drafted_players.add(player_name)
        self.save()

    def reset(self):
        """Reset draft state."""
        self.drafted_players = set()
        self.my_team = []
        self.save()
