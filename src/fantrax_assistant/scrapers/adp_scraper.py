"""Fantrax ADP CSV loader."""

import json
import csv
from datetime import datetime
from pathlib import Path


def load_fantrax_csv(csv_file: str | Path) -> dict | None:
    """
    Load ADP / Projected Scoring data from Fantrax CSV export.

    Supports both default Fantrax CSV export:
    ID,Player,Team,Position,RkOv,Status,Opponent,FPts,FP/G,%D,ADP,Ros,+/-

    And custom projected scoring CSV export:
    Player,Team,Position,Projected Fpts,Proj FPG,PPG dif from last year,ADP,25/26 Fpts,25/26 FPG,25/26 GS,25/26 Goals,25/26 Assists,25/26 G+A

    Args:
        csv_file: Path to the Fantrax CSV export

    Returns:
        Dictionary with ADP/ranking data or None if loading fails.
    """
    csv_path = Path(csv_file)

    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        return None

    print(f"Loading data from {csv_path}...")

    try:
        rankings = []

        with csv_path.open('r', encoding='utf-8') as f:
            lines = f.readlines()

        # Skip non-header metadata lines (e.g. "Table 1") if present
        start_idx = 0
        for idx, line in enumerate(lines):
            if "Player" in line and "Position" in line:
                start_idx = idx
                break

        reader = csv.DictReader(lines[start_idx:])

        for idx, row in enumerate(reader):
            player_name = (row.get('Player') or '').strip()
            if not player_name:
                continue

            team = (row.get('Team') or '').strip()
            position = (row.get('Position') or '').strip()

            # Parse ADP - handle empty or '-' values
            try:
                raw_adp = (row.get('ADP') or '').strip()
                adp = float(raw_adp) if raw_adp and raw_adp != '-' else 999.0
            except ValueError:
                adp = 999.0

            # Parse rank if present
            try:
                raw_rank = (row.get('RkOv') or '').strip()
                rank = int(raw_rank) if raw_rank and raw_rank != '-' else None
            except ValueError:
                rank = None

            # Parse fantasy points (Projected Fpts or FPts)
            try:
                raw_fpts = (row.get('Projected Fpts') or row.get('FPts') or '').strip()
                fpts = float(raw_fpts) if raw_fpts and raw_fpts != '-' else 0.0
            except ValueError:
                fpts = 0.0

            # Parse FP/G (Proj FPG or FP/G)
            try:
                raw_fpg = (row.get('Proj FPG') or row.get('FP/G') or '').strip()
                fpg = float(raw_fpg) if raw_fpg and raw_fpg != '-' else 0.0
            except ValueError:
                fpg = 0.0

            rankings.append({
                'rank': rank if rank is not None else idx + 1,
                'player': player_name,
                'position': position,
                'team': team,
                'adp': adp,
                'fpts': fpts,
                'fpg': fpg
            })

        # Sort by ADP (primary) and FPts (secondary fallback if ADP is 999.0)
        rankings.sort(key=lambda x: (x['adp'], -x['fpts']))

        # Re-assign rank order sequentially if RkOv was not in the file
        for idx, item in enumerate(rankings, 1):
            if item['rank'] == 999 or item['rank'] is None:
                item['rank'] = idx

        print(f"✓ Successfully loaded {len(rankings)} player rankings")

        return {
            'last_updated': datetime.now().isoformat(),
            'source': 'Fantrax CSV Export',
            'season': '2025-2026',
            'rankings': rankings
        }

    except Exception as e:
        print(f"Error loading CSV: {e}")
        import traceback
        traceback.print_exc()
        return None


def save_rankings(csv_file: str | Path = 'data/fantrax_export.csv',
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
    # Default: look for data/fantrax_export.csv
    save_rankings()

