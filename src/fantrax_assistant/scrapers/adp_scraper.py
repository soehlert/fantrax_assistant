"""Fantrax ADP CSV loader."""

import json
import csv
from datetime import datetime
from pathlib import Path


def load_fantrax_csv(csv_file: str | Path) -> dict | None:
    """
    Load ADP data from Fantrax CSV export.

    Expected CSV format from Fantrax:
    ID,Player,Team,Position,RkOv,Status,Opponent,FPts,FP/G,%D,ADP,Ros,+/-

    Args:
        csv_file: Path to the Fantrax CSV export

    Returns:
        Dictionary with ADP/ranking data or None if loading fails.
    """
    csv_path = Path(csv_file)

    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        return None

    print(f"Loading ADP data from {csv_path}...")

    try:
        rankings = []

        with csv_path.open('r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                player_name = row['Player'].strip()
                team = row['Team'].strip()
                position = row['Position'].strip()

                # Parse ADP - handle empty values
                try:
                    adp = float(row['ADP']) if row['ADP'] else 999.0
                except (ValueError, KeyError):
                    adp = 999.0

                # Parse rank
                try:
                    rank = int(row['RkOv']) if row['RkOv'] else 999
                except (ValueError, KeyError):
                    rank = 999

                # Parse fantasy points
                try:
                    fpts = float(row['FPts']) if row['FPts'] else 0.0
                except (ValueError, KeyError):
                    fpts = 0.0

                # Parse FP/G
                try:
                    fpg = float(row['FP/G']) if row['FP/G'] else 0.0
                except (ValueError, KeyError):
                    fpg = 0.0

                rankings.append({
                    'rank': rank,
                    'player': player_name,
                    'position': position,
                    'team': team,
                    'adp': adp,
                    'fpts': fpts,
                    'fpg': fpg
                })

        # Sort by ADP
        rankings.sort(key=lambda x: x['adp'])

        print(f"✓ Successfully loaded {len(rankings)} player rankings")

        return {
            'last_updated': datetime.now().isoformat(),
            'source': 'Fantrax CSV Export',
            'season': '2024-2025',
            'rankings': rankings
        }

    except Exception as e:
        print(f"Error loading CSV: {e}")
        import traceback
        traceback.print_exc()
        return None


def save_rankings(csv_file: str | Path = 'fantrax_export.csv',
                 output_file: str | Path = 'data/adp_rankings.json') -> bool:
    """Load Fantrax CSV and save as JSON."""
    data = load_fantrax_csv(csv_file)

    if data:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open('w') as f:
            json.dump(data, f, indent=2)
        print(f"✓ Saved rankings to {output_path}")
        return True

    return False


if __name__ == "__main__":
    # Default: look for fantrax_export.csv in current directory
    save_rankings()
