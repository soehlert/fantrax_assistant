"""Tab completion for draft CLI."""

import click
from .config import DraftConfig
from .draft_state import DraftState


def get_team_names():
    """Get available team names for completion."""
    state = DraftState()
    return list(state.teams.keys())


def get_positions():
    """Get available positions for completion."""
    return ['G', 'D', 'M', 'F']


def get_clubs():
    """Get available clubs for completion."""
    config = DraftConfig()
    if config.load_all_data():
        clubs = set()
        for player in config.rankings.get('rankings', []):
            clubs.add(player.get('team', ''))
        return sorted(list(clubs))
    return []


class TeamCompleter:
    """Complete team names."""
    def __call__(self, ctx, args, incomplete):
        return [t for t in get_team_names() if t.startswith(incomplete)]


class PositionCompleter:
    """Complete positions."""
    def __call__(self, ctx, args, incomplete):
        return [p for p in get_positions() if p.startswith(incomplete)]


class ClubCompleter:
    """Complete club abbreviations."""
    def __call__(self, ctx, args, incomplete):
        return [c for c in get_clubs() if c.startswith(incomplete.upper())]
