"""Fantrax recent form CSV loader."""

import json
import csv
from datetime import datetime
from pathlib import Path


def load_recent_form_csv(csv_file: str | Path, days: int = 30) -> dict | None:
    """
    Load recent form data from Fantrax CSV export.

    Args:
        csv_file: Path to the Fantrax recent form CSV export
        days: Number of days covered (30 or 60)

    Returns:
        Dictionary with recent form data or None if loading fails.
    """
    csv_path = Path(csv_file)

    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        return None

    print(f"Loading {days}-day form data from {csv_path}...")

    try:
        recent_form = []

        with csv_path.open('r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                player_name = row['Player'].strip()

                recent_form.append({
                    'player': player_name,
                    'team': row.get('Team', '').strip(),
                    'position': row.get('Position', '').strip(),
                    'recent_fpts': float(row.get('FPts', 0) or 0),
                    'recent_fpg': float(row.get('FP/G', 0) or 0),
                    'recent_games': int(row.get('GP', 0) or 0),
                    'days': days
                })

        print(f"✓ Successfully loaded {len(recent_form)} players' recent form")

        return {
            'last_updated': datetime.now().isoformat(),
            'source': 'Fantrax CSV Export',
            'days_covered': days,
            'recent_form': recent_form
        }

    except Exception as e:
        print(f"Error loading CSV: {e}")
        import traceback
        traceback.print_exc()
        return None


def save_recent_form(csv_file: str | Path = 'data/fantrax_recent_30d.csv',
                     output_file: str | Path = 'data/recent_form.json',
                     days: int = 30) -> bool:
    """Load Fantrax recent form CSV and save as JSON."""
    data = load_recent_form_csv(csv_file, days)

    if data:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open('w') as f:
            json.dump(data, f, indent=2)
        print(f"✓ Saved recent form to {output_path}")
        return True

    return False


if __name__ == "__main__":
    save_recent_form()
