"""Seeder script to populate SQLite database (data/fantrax_assistant.db) from all data files."""

import json
from pathlib import Path
from fantrax_assistant.db import DatabaseManager, normalize_name
from fantrax_assistant.scrapers.understat import Understat
from fantrax_assistant.config import DraftConfig

def seed_database():
    print("Starting database seeding process...")
    db = DatabaseManager("data/fantrax_assistant.db")
    config = DraftConfig()
    config.load_all_data()
    understat = Understat()

    # 1. Ingest Fantrax Rankings (Master player list)
    rankings = config.rankings.get("rankings", [])
    print(f"Ingesting {len(rankings)} players from Fantrax ADP rankings...")

    # Explicit Understat ID mapping overrides for edge case names
    EXPLICIT_UNDERSTAT_MAPPINGS = {
        "rayan": "14395",            # Rayan (Bournemouth) -> Understat 14395
        "rayan ait nouri": "6674",    # Rayan Aït-Nouri (Wolves) -> Understat 6674
        "gabriel magalhaes": "5613",  # Gabriel (Arsenal) -> Understat 5613
        "bruno guimaraes": "6521",    # Bruno Guimarães (Newcastle) -> Understat 6521
        "rayane cherki": "12845",     # Rayan Cherki -> Understat 12845
        "rayan cherki": "12845",
        "david raya": "7710",
        "jordan pickford": "741",
        "erling haaland": "8260",
        "eberechi eze": "8367",
        "declan rice": "5553"
    }

    # Pre-fetch Understat data to map IDs
    try:
        u_players = understat.get_all_players_data("EPL", "2024")
    except Exception as e:
        print(f"Warning: Could not fetch Understat API data during seed: {e}")
        u_players = []

    u_by_norm = {}
    for up in u_players:
        u_by_norm[normalize_name(up.get("player_name", ""))] = up

    # Seed Players
    for p in rankings:
        p_name = p.get("player", "")
        p_norm = normalize_name(p_name)
        p_pos = p.get("position", "")
        p_team = p.get("team", "")
        p_adp = float(p.get("adp", 999.0) or 999.0)
        p_fpts = float(p.get("fpts", 0.0) or 0.0)
        p_fpg = float(p.get("fpg", 0.0) or 0.0)

        # Match Understat ID
        understat_id = EXPLICIT_UNDERSTAT_MAPPINGS.get(p_norm)
        if not understat_id and p_norm in u_by_norm:
            understat_id = u_by_norm[p_norm].get("id")

        player_id = db.upsert_player(
            name=p_name,
            position=p_pos,
            team=p_team,
            adp=p_adp,
            fpts=p_fpts,
            fpg=p_fpg,
            understat_id=understat_id
        )

        # Bind common aliases
        db.add_alias(p_name, player_id)
        db.add_alias(p_norm, player_id)

    print("✓ Successfully seeded main players table and alias bindings.")

    # 2. Ingest Current Premier League Match Stats (current_stats.json)
    try:
        stats_file = Path("data/current_stats.json")
        if stats_file.exists():
            with stats_file.open() as f:
                c_data = json.load(f)
                for sp in c_data.get("players", []):
                    sp_name = sp.get("name", "")
                    player_id = db.get_player_id_by_name(sp_name)
                    if player_id:
                        fpl_id = str(sp.get("id", ""))
                        starts = int(sp.get("starts", 0) or 0)
                        matches = int(sp.get("matches_played", 0) or 0)
                        total_apps = max(starts, matches)
                        db.set_pl_stats(
                            player_id=player_id,
                            fpl_id=fpl_id,
                            starts=starts,
                            appearances=total_apps,
                            minutes=int(sp.get("minutes", 0) or 0),
                            goals=int(sp.get("goals", 0) or 0),
                            assists=int(sp.get("assists", 0) or 0),
                            clean_sheets=int(sp.get("clean_sheets", 0) or 0),
                            ict_index=float(sp.get("ict_index", 0) or 0),
                            influence=float(sp.get("influence", 0) or 0),
                            threat=float(sp.get("threat", 0) or 0),
                            creativity=float(sp.get("creativity", 0) or 0)
                        )
            print("✓ Successfully ingested Premier League official match stats.")
    except Exception as e:
        print(f"Error seeding PL stats: {e}")

    # 3. Ingest Understat Metrics into DB
    try:
        for up in u_players:
            up_name = up.get("player_name", "")
            up_id = up.get("id", "")
            player_id = db.get_player_id_by_name(up_name)
            if not player_id:
                # Try finding player_id via explicit mapping
                norm_up = normalize_name(up_name)
                for k, eid in EXPLICIT_UNDERSTAT_MAPPINGS.items():
                    if eid == up_id:
                        player_id = db.get_player_id_by_name(k)
                        break

            if player_id:
                db.set_understat_stats(
                    player_id=player_id,
                    understat_id=up_id,
                    season="2024",
                    games=int(up.get("games", 0) or 0),
                    minutes=int(up.get("time", 0) or 0),
                    goals=int(up.get("goals", 0) or 0),
                    npg=int(up.get("npg", 0) or 0),
                    xg=float(up.get("xG", 0) or 0),
                    npxg=float(up.get("npxG", 0) or 0),
                    assists=int(up.get("assists", 0) or 0),
                    xa=float(up.get("xA", 0) or 0),
                    shots=int(up.get("shots", 0) or 0),
                    key_passes=int(up.get("key_passes", 0) or 0),
                    xg_chain=float(up.get("xGChain", 0) or 0),
                    xg_buildup=float(up.get("xGBuildup", 0) or 0)
                )
        print("✓ Successfully ingested Understat stats into SQLite.")
    except Exception as e:
        print(f"Error seeding Understat stats: {e}")

    # 4. Ingest Injuries & AFCON Status
    try:
        injuries_file = Path("data/injuries.json")
        if injuries_file.exists():
            with injuries_file.open() as f:
                inj_data = json.load(f)
                for ip in inj_data.get("injuries", []):
                    ip_name = ip.get("player", "")
                    player_id = db.get_player_id_by_name(ip_name)
                    if player_id:
                        afcon_status = config.get_player_afcon_status(ip_name).get("at_afcon", False)
                        db.set_injury_info(
                            player_id=player_id,
                            severity=ip.get("severity", "Healthy"),
                            notes=ip.get("notes", ""),
                            at_afcon=afcon_status
                        )
            print("✓ Successfully ingested Injuries and AFCON status.")
    except Exception as e:
        print(f"Error seeding Injuries: {e}")

    print("🎉 Database seeding complete! data/fantrax_assistant.db is ready.")

if __name__ == "__main__":
    seed_database()
