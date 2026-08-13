#!/usr/bin/env python3
"""
Database Verification Script for fantrax_assistant.db
Checks schema integrity, row counts, query latency, edge-case name alias lookups, and foreign keys.
"""

import sys
import time
import sqlite3
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "src"))

from fantrax_assistant.db import DatabaseManager

def run_db_verification():
    db_path = root_dir / "data" / "fantrax_assistant.db"
    print(f"🔍 Verifying SQLite Database at: {db_path}\n")

    if not db_path.exists():
        print("❌ Error: Database file does not exist! Run `uv run python scripts/seed_db.py` first.")
        sys.exit(1)

    db = DatabaseManager(str(db_path))

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # 1. Check Tables and Row Counts
        print("📊 1. Table Row Counts & Schema Status:")
        tables = ["players", "player_aliases", "pl_match_stats", "recent_form", "understat_stats", "injuries"]
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            status = "✅" if count > 0 else "⚠️ (Empty)"
            print(f"   {status} {table:20}: {count:5} rows")

        # 2. Check Foreign Key Integrity
        print("\n🔒 2. Foreign Key Integrity Check:")
        cursor.execute("PRAGMA foreign_key_check")
        fk_errors = cursor.fetchall()
        if not fk_errors:
            print("   ✅ Foreign Key Check: 0 Violations (100% Intact)")
        else:
            print(f"   ⚠️ Foreign Key Check: {len(fk_errors)} Violations Found!")
            for err in fk_errors[:5]:
                print(f"      Violation in table {err[0]}, rowid {err[1]}")

        # 3. Query Performance / Latency Benchmark
        print("\n⚡ 3. Benchmark Query Latency (100 Lookups):")
        start_time = time.perf_counter()
        for _ in range(100):
            db.get_player_id_by_name("Gabriel Magalhaes")
            db.get_player_id_by_name("Erling Haaland")
            db.get_player_id_by_name("Jordan Pickford")
        elapsed = (time.perf_counter() - start_time) * 1000.0 / 300.0
        print(f"   ✅ Average Single Name/Alias Query Speed: {elapsed:.3f} ms / query")

        # 4. Audit Edge Case Name Aliases & Direct UUID Lookups
        print("\n🎯 4. Auditing Edge-Case Player Profile Lookups:")
        test_players = [
            "Erling Haaland",
            "Gabriel Magalhaes",
            "Bruno Guimaraes",
            "Jordan Pickford",
            "Declan Rice",
            "Rayan",
            "Rayan Ait-Nouri",
            "Bukayo Saka"
        ]

        success_count = 0
        for name in test_players:
            p_id = db.get_player_id_by_name(name)
            if not p_id:
                print(f"   ❌ Failed to map name to UUID: {name}")
                continue
            
            profile = db.get_full_player_profile(p_id)
            if profile and profile.get("name"):
                u_id = profile.get("understat_id") or "—"
                fpl_id = profile.get("fpl_id") or "—"
                cbi = profile.get("pl_stats", {}).get("cbi") if profile.get("pl_stats") else "—"
                print(f"   ✅ {name:20} -> UUID: {p_id[:8]}... | Understat ID: {u_id:5} | FPL ID: {fpl_id:4} | CBI: {cbi}")
                success_count += 1
            else:
                print(f"   ❌ Profile missing for UUID: {p_id}")

        print(f"\n🎉 Verification Complete: {success_count}/{len(test_players)} Edge Cases Verified!")

if __name__ == "__main__":
    run_db_verification()
