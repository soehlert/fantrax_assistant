"""SQLite Database Manager for Fantrax Assistant unifying all 7 data sources."""

import sqlite3
import uuid
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

def normalize_name(s: str) -> str:
    """Normalize string by removing accents, lowercasing, and stripping punctuation."""
    if not s:
        return ""
    return ''.join(
        c for c in unicodedata.normalize('NFD', str(s))
        if unicodedata.category(c) != 'Mn'
    ).lower().replace('-', ' ').replace('.', '').strip()

class DatabaseManager:
    def __init__(self, db_path: str | Path = "data/fantrax_assistant.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Main Players table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                position TEXT,
                team TEXT,
                adp REAL,
                fpts REAL,
                fpg REAL,
                understat_id TEXT,
                fpl_id TEXT,
                updated_at TEXT
            )
            """)

            # 2. Player Aliases table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS player_aliases (
                alias TEXT PRIMARY KEY,
                player_id TEXT NOT NULL,
                FOREIGN KEY (player_id) REFERENCES players (id)
            )
            """)

            # 3. Premier League / FPL Match Stats table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS pl_match_stats (
                player_id TEXT PRIMARY KEY,
                fpl_id TEXT,
                starts INTEGER,
                appearances INTEGER,
                minutes INTEGER,
                goals INTEGER,
                assists INTEGER,
                clean_sheets INTEGER,
                goals_conceded INTEGER,
                expected_goals_conceded REAL,
                tackles INTEGER,
                cbi INTEGER,
                recoveries INTEGER,
                yellow_cards INTEGER,
                red_cards INTEGER,
                saves INTEGER,
                ict_index REAL,
                influence REAL,
                threat REAL,
                creativity REAL,
                FOREIGN KEY (player_id) REFERENCES players (id)
            )
            """)

            cursor.execute("PRAGMA table_info(pl_match_stats)")
            existing_cols = [row["name"] for row in cursor.fetchall()]
            new_cols = [
                ("goals_conceded", "INTEGER"),
                ("expected_goals_conceded", "REAL"),
                ("tackles", "INTEGER"),
                ("cbi", "INTEGER"),
                ("recoveries", "INTEGER"),
                ("yellow_cards", "INTEGER"),
                ("red_cards", "INTEGER"),
                ("saves", "INTEGER"),
            ]
            for col_name, col_type in new_cols:
                if col_name not in existing_cols:
                    cursor.execute(f"ALTER TABLE pl_match_stats ADD COLUMN {col_name} {col_type}")

            # 4. Recent Form table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS recent_form (
                player_id TEXT PRIMARY KEY,
                recent_fpts REAL,
                recent_fpg REAL,
                recent_games INTEGER,
                days_covered INTEGER,
                FOREIGN KEY (player_id) REFERENCES players (id)
            )
            """)

            # 5. Understat Stats table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS understat_stats (
                player_id TEXT NOT NULL,
                understat_id TEXT NOT NULL,
                season TEXT NOT NULL,
                games INTEGER,
                minutes INTEGER,
                goals INTEGER,
                npg INTEGER,
                xg REAL,
                npxg REAL,
                assists INTEGER,
                xa REAL,
                shots INTEGER,
                key_passes INTEGER,
                xg_chain REAL,
                xg_buildup REAL,
                PRIMARY KEY (player_id, season),
                FOREIGN KEY (player_id) REFERENCES players (id)
            )
            """)

            # 6. Injuries & AFCON table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS injuries (
                player_id TEXT PRIMARY KEY,
                severity TEXT,
                notes TEXT,
                at_afcon INTEGER,
                FOREIGN KEY (player_id) REFERENCES players (id)
            )
            """)

            conn.commit()

    def get_player_id_by_name(self, name: str) -> Optional[str]:
        norm_input = normalize_name(name)
        if not norm_input:
            return None

        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check player_aliases table
            cursor.execute("SELECT player_id FROM player_aliases WHERE alias = ?", (norm_input,))
            row = cursor.fetchone()
            if row:
                return row["player_id"]

            # Fallback to direct name query
            cursor.execute("SELECT id FROM players WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                return row["id"]

        return None

    def upsert_player(self, name: str, position: str, team: str, adp: float, fpts: float, fpg: float, understat_id: Optional[str] = None, fpl_id: Optional[str] = None) -> str:
        norm_input = normalize_name(name)
        player_id = self.get_player_id_by_name(name)
        now_str = datetime.now().isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            if not player_id:
                player_id = str(uuid.uuid4())
                cursor.execute("""
                INSERT INTO players (id, name, position, team, adp, fpts, fpg, understat_id, fpl_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (player_id, name, position, team, adp, fpts, fpg, understat_id, fpl_id, now_str))
            else:
                cursor.execute("""
                UPDATE players
                SET name = ?, position = ?, team = ?, adp = ?, fpts = ?, fpg = ?,
                    understat_id = COALESCE(?, understat_id),
                    fpl_id = COALESCE(?, fpl_id),
                    updated_at = ?
                WHERE id = ?
                """, (name, position, team, adp, fpts, fpg, understat_id, fpl_id, now_str, player_id))

            # Bind alias
            cursor.execute("INSERT OR REPLACE INTO player_aliases (alias, player_id) VALUES (?, ?)", (norm_input, player_id))
            conn.commit()

        return player_id

    def add_alias(self, alias_name: str, player_id: str):
        norm_alias = normalize_name(alias_name)
        if not norm_alias or not player_id:
            return
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO player_aliases (alias, player_id) VALUES (?, ?)", (norm_alias, player_id))
            conn.commit()

    def set_pl_stats(self, player_id: str, fpl_id: str, starts: int, appearances: int, minutes: int, goals: int = 0, assists: int = 0, clean_sheets: int = 0, goals_conceded: int = 0, expected_goals_conceded: float = 0.0, tackles: int = 0, cbi: int = 0, recoveries: int = 0, yellow_cards: int = 0, red_cards: int = 0, saves: int = 0, ict_index: float = 0.0, influence: float = 0.0, threat: float = 0.0, creativity: float = 0.0):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO pl_match_stats
            (player_id, fpl_id, starts, appearances, minutes, goals, assists, clean_sheets, goals_conceded, expected_goals_conceded, tackles, cbi, recoveries, yellow_cards, red_cards, saves, ict_index, influence, threat, creativity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (player_id, fpl_id, starts, appearances, minutes, goals, assists, clean_sheets, goals_conceded, expected_goals_conceded, tackles, cbi, recoveries, yellow_cards, red_cards, saves, ict_index, influence, threat, creativity))
            conn.commit()

    def set_understat_stats(self, player_id: str, understat_id: str, season: str, games: int, minutes: int, goals: int, npg: int, xg: float, npxg: float, assists: int, xa: float, shots: int, key_passes: int, xg_chain: float, xg_buildup: float):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO understat_stats
            (player_id, understat_id, season, games, minutes, goals, npg, xg, npxg, assists, xa, shots, key_passes, xg_chain, xg_buildup)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (player_id, understat_id, season, games, minutes, goals, npg, xg, npxg, assists, xa, shots, key_passes, xg_chain, xg_buildup))
            conn.commit()

    def set_injury_info(self, player_id: str, severity: str, notes: str, at_afcon: bool):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO injuries (player_id, severity, notes, at_afcon)
            VALUES (?, ?, ?, ?)
            """, (player_id, severity, notes, 1 if at_afcon else 0))
            conn.commit()

    def get_full_player_profile(self, name_or_id: str) -> Optional[Dict[str, Any]]:
        """Fetch unified player data across all 7 tables for a given UUID or player name."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Try direct lookup by UUID first
            cursor.execute("SELECT * FROM players WHERE id = ?", (name_or_id,))
            p_row = cursor.fetchone()

            # 2. Fallback to name / alias lookup
            if not p_row:
                player_id = self.get_player_id_by_name(name_or_id)
                if player_id:
                    cursor.execute("SELECT * FROM players WHERE id = ?", (player_id,))
                    p_row = cursor.fetchone()

            if not p_row:
                return None
            
            p_dict = dict(p_row)
            player_id = p_dict["id"]

            # Join PL Match Stats
            cursor.execute("SELECT * FROM pl_match_stats WHERE player_id = ?", (player_id,))
            pl_row = cursor.fetchone()
            p_dict["pl_stats"] = dict(pl_row) if pl_row else None

            # Join Understat Stats
            cursor.execute("SELECT * FROM understat_stats WHERE player_id = ? ORDER BY season DESC LIMIT 1", (player_id,))
            u_row = cursor.fetchone()
            p_dict["understat_stats"] = dict(u_row) if u_row else None

            # Join Recent Form
            cursor.execute("SELECT * FROM recent_form WHERE player_id = ?", (player_id,))
            rf_row = cursor.fetchone()
            p_dict["recent_form"] = dict(rf_row) if rf_row else None

            # Join Injuries
            cursor.execute("SELECT * FROM injuries WHERE player_id = ?", (player_id,))
            inj_row = cursor.fetchone()
            p_dict["injury"] = dict(inj_row) if inj_row else None

            return p_dict
