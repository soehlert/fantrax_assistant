"""FPL Fixture Difficulty Rating scraper."""

import json
import requests
from datetime import datetime
from pathlib import Path


def scrape_fpl_fdr() -> dict | None:
    """
    Scrape Fixture Difficulty Ratings from FPL API.

    Returns:
        Dictionary with FDR data or None if scraping fails.
    """
    # FPL Bootstrap API has all the data we need
    bootstrap_url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    fixtures_url = "https://fantasy.premierleague.com/api/fixtures/"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }

    print("Fetching FDR data from FPL API...")

    try:
        # Get team data
        response = requests.get(bootstrap_url, headers=headers, timeout=30)
        response.raise_for_status()
        bootstrap_data = response.json()

        # Get fixtures
        response = requests.get(fixtures_url, headers=headers, timeout=30)
        response.raise_for_status()
        fixtures_data = response.json()

        # Build team ID to name mapping
        teams = {team['id']: team['name'] for team in bootstrap_data['teams']}

        # Process fixtures - get next 5 gameweeks for each team
        team_fixtures = {}

        for fixture in fixtures_data:
            if fixture['finished']:
                continue

            home_team = fixture['team_h']
            away_team = fixture['team_a']

            # FDR from home team's perspective (difficulty of away opponent)
            home_fdr = fixture['team_h_difficulty']
            # FDR from away team's perspective (difficulty of home opponent)
            away_fdr = fixture['team_a_difficulty']

            # Add to home team's fixtures
            if home_team not in team_fixtures:
                team_fixtures[home_team] = []
            team_fixtures[home_team].append({
                'gameweek': fixture['event'],
                'opponent': teams[away_team],
                'home': True,
                'fdr': home_fdr
            })

            # Add to away team's fixtures
            if away_team not in team_fixtures:
                team_fixtures[away_team] = []
            team_fixtures[away_team].append({
                'gameweek': fixture['event'],
                'opponent': teams[home_team],
                'home': False,
                'fdr': away_fdr
            })

        # Sort fixtures by gameweek and take next 5
        for team_id in team_fixtures:
            team_fixtures[team_id].sort(key=lambda x: x['gameweek'])
            team_fixtures[team_id] = team_fixtures[team_id][:5]

        # Convert team IDs to names
        fdr_by_team = {
            teams[team_id]: fixtures
            for team_id, fixtures in team_fixtures.items()
        }

        print(f"✓ Successfully scraped FDR for {len(fdr_by_team)} teams")

        return {
            'last_updated': datetime.now().isoformat(),
            'source': 'Fantasy Premier League API',
            'fdr_by_team': fdr_by_team
        }

    except Exception as e:
        print(f"Error scraping FPL FDR: {e}")
        import traceback
        traceback.print_exc()
        return None


def save_fdr(output_file: str | Path = 'data/fdr.json') -> bool:
    """Scrape and save FDR data."""
    data = scrape_fpl_fdr()

    if data:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open('w') as f:
            json.dump(data, f, indent=2)
        print(f"✓ Saved FDR to {output_path}")
        return True

    return False


if __name__ == "__main__":
    save_fdr()
