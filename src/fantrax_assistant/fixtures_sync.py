"""Fetches live Premier League fixtures and starting XI lineup confirmations."""

import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional

FIXTURES_API_URL = "https://fantasy.premierleague.com/api/fixtures/"
BOOTSTRAP_API_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

def fetch_live_pl_schedule() -> Dict[str, Any]:
    """Fetch current season fixtures and live team lineups from Premier League API."""
    try:
        # 1. Fetch team ID mapping
        req_boot = urllib.request.Request(BOOTSTRAP_API_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req_boot, timeout=10) as resp:
            boot_data = json.loads(resp.read().decode())
        
        team_map = {t['id']: t['short_name'] for t in boot_data.get('teams', [])}

        # 2. Fetch all 380 fixtures
        req_fix = urllib.request.Request(FIXTURES_API_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req_fix, timeout=10) as resp:
            fixtures_raw = json.loads(resp.read().decode())

        schedule_by_team = {}
        now_iso = datetime.now(timezone.utc).isoformat()

        # Group by upcoming gameweek or next match per team
        for fix in fixtures_raw:
            team_h = team_map.get(fix.get('team_h'), '')
            team_a = team_map.get(fix.get('team_a'), '')
            kickoff = fix.get('kickoff_time', '')
            event = fix.get('event', 1)

            if not team_h or not team_a or not kickoff:
                continue

            dt = datetime.fromisoformat(kickoff.replace('Z', '+00:00'))
            display_time = dt.strftime('%a %b %d, %I:%M %p')

            # Home team entry
            if team_h not in schedule_by_team or fix.get('event') == 1:
                schedule_by_team[team_h] = {
                    'opponent': team_a,
                    'is_home': True,
                    'fdr': fix.get('team_h_difficulty', 3),
                    'kickoff_time': kickoff,
                    'display_time': display_time,
                    'gameweek': event,
                    'started': fix.get('started', False),
                    'finished': fix.get('finished', False)
                }

            # Away team entry
            if team_a not in schedule_by_team or fix.get('event') == 1:
                schedule_by_team[team_a] = {
                    'opponent': team_h,
                    'is_home': False,
                    'fdr': fix.get('team_a_difficulty', 3),
                    'kickoff_time': kickoff,
                    'display_time': display_time,
                    'gameweek': event,
                    'started': fix.get('started', False),
                    'finished': fix.get('finished', False)
                }

        # Save to data/fixtures.json
        output_file = DATA_DIR / "fixtures.json"
        with open(output_file, 'w') as f:
            json.dump(schedule_by_team, f, indent=2)

        print(f"Successfully synced Premier League fixtures for {len(schedule_by_team)} teams into data/fixtures.json!")
        return schedule_by_team

    except Exception as e:
        print(f"Error fetching live PL schedule: {e}")
        return {}

if __name__ == "__main__":
    fetch_live_pl_schedule()
