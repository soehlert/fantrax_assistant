"""SportsGambler injury scraper for Premier League."""

import json
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup


def scrape_sportsgambler_injuries() -> dict | None:
    """
    Scrape injury data from SportsGambler Premier League page.

    Returns:
        Dictionary with injury information or None if scraping fails.
    """
    url = "https://www.sportsgambler.com/injuries/football/england-premier-league/"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    print("Fetching injury data from SportsGambler...")

    try:
        time.sleep(1)
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        injuries = []

        # Find all injury blocks (one per team)
        injury_blocks = soup.find_all('div', class_='injury-block')

        for block in injury_blocks:
            # Get team name from the title
            team_title = block.find('h3', class_='injuries-title')
            team_name = team_title.text.strip() if team_title else 'Unknown'

            # Find all injury rows within this team's block
            injury_rows = block.find_all('div', class_='inj-row')

            for row in injury_rows:
                # Find all the injury containers within the row
                containers = row.find_all('div', class_='inj-container')

                if not containers:
                    continue

                # Extract data from each span within containers
                player_span = row.find('span', class_='inj-player')
                position_span = row.find('span', class_='inj-position')
                info_span = row.find('span', class_='inj-info')
                return_span = row.find('span', class_='inj-return')
                type_span = row.find('span', class_='inj-type')

                if not player_span:
                    continue

                player_name = player_span.text.strip()
                position = position_span.text.strip() if position_span else 'Unknown'
                injury_info = info_span.text.strip() if info_span else 'Unknown'
                return_date = return_span.text.strip() if return_span else 'Unknown'

                # Determine injury type/severity from the icon class
                injury_type = 'Unknown'
                severity = 'Unknown'

                if type_span:
                    # Check for injury type classes
                    type_classes = type_span.get('class', [])

                    if 'injury-plus' in type_classes or 'injury-red' in type_classes:
                        severity = 'Out'
                        injury_type = 'Injured'
                    elif 'injury-question' in type_classes:
                        severity = 'Questionable'
                        injury_type = 'Questionable'
                    elif 'injury-card' in type_classes:
                        severity = 'Suspended'
                        injury_type = 'Suspended'

                # Refine severity based on return date
                if return_date and return_date != 'Unknown':
                    if '2026' in return_date:
                        # Parse month to determine if long term
                        try:
                            date_parts = return_date.split('-')
                            if len(date_parts) >= 2:
                                month = int(date_parts[1])
                                if month > 3:  # After March
                                    severity = 'Long Term'
                                else:
                                    severity = 'Medium Term'
                        except:
                            severity = 'Medium Term'
                    elif severity == 'Out':
                        severity = 'Short Term'

                injuries.append({
                    'player': player_name,
                    'team': team_name,
                    'position': position,
                    'injury_type': injury_info,
                    'status': injury_type,
                    'return_date': return_date,
                    'severity': severity
                })

        if not injuries:
            print("Warning: No injuries found - page structure may have changed")
            print(f"Found {len(injury_blocks)} injury blocks")

            return {
                'last_updated': datetime.now().isoformat(),
                'source': 'SportsGambler',
                'injuries': []
            }

        print(f"✓ Successfully scraped {len(injuries)} injuries")

        return {
            'last_updated': datetime.now().isoformat(),
            'source': 'SportsGambler',
            'injuries': injuries
        }

    except Exception as e:
        print(f"Error scraping SportsGambler: {e}")
        import traceback
        traceback.print_exc()

        return {
            'last_updated': datetime.now().isoformat(),
            'source': 'SportsGambler',
            'injuries': []
        }


def save_injuries(output_file: str | Path = 'data/injuries.json') -> bool:
    """Scrape and save injuries to JSON file."""
    data = scrape_sportsgambler_injuries()

    if data:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open('w') as f:
            json.dump(data, f, indent=2)

        injury_count = len(data.get('injuries', []))
        if injury_count > 0:
            print(f"✓ Saved {injury_count} injuries to {output_path}")
        else:
            print(f"✓ Saved empty injury list to {output_path}")
        return True

    return False


if __name__ == "__main__":
    save_injuries()
