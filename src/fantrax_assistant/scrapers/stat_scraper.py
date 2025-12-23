"""Premier League official stats scraper."""

import json
import requests
from pathlib import Path
from datetime import datetime


def scrape_premier_league_stats() -> dict | None:
    """Scrape from Premier League's official API (used by FPL)."""

    # This is the official FPL API - it's public and free
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }

    print("Fetching stats from Premier League API...")

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        players = []

        # Parse player data
        for player in data['elements']:
            players.append({
                'name': f"{player['first_name']} {player['second_name']}",
                'team': player['team'],
                'position': player['element_type'],  # 1=GK, 2=DEF, 3=MID, 4=FWD
                'matches_played': player['minutes'] // 90,  # Rough estimate
                'starts': player['starts'],
                'minutes': player['minutes'],
                'goals': player['goals_scored'],
                'assists': player['assists'],
                'clean_sheets': player['clean_sheets'],
                'yellow_cards': player['yellow_cards'],
                'red_cards': player['red_cards'],
                'bonus': player['bonus'],
                'influence': float(player['influence']),
                'creativity': float(player['creativity']),
                'threat': float(player['threat']),
                'ict_index': float(player['ict_index']),
                'total_points': player['total_points'],
                'points_per_game': float(player['points_per_game'])
            })

        print(f"✓ Successfully scraped {len(players)} players")

        return {
            'last_updated': datetime.now().isoformat(),
            'source': 'Premier League API',
            'season': '2024-2025',
            'players': players
        }

    except Exception as e:
        print(f"Error: {e}")
        return None


def save_stats(output_file: str | Path = 'data/current_stats.json') -> bool:
    """Scrape and save stats."""
    data = scrape_premier_league_stats()

    if data:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open('w') as f:
            json.dump(data, f, indent=2)
        print(f"✓ Saved stats to {output_path}")
        return True

    return False


if __name__ == "__main__":
    save_stats()
