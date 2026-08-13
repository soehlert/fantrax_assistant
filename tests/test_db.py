import unittest
from pathlib import Path
from fantrax_assistant.db import DatabaseManager

class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        self.test_db_path = Path("tests/test_fantrax.db")
        if self.test_db_path.exists():
            self.test_db_path.unlink()
        self.db = DatabaseManager(self.test_db_path)

    def tearDown(self):
        if self.test_db_path.exists():
            self.test_db_path.unlink()

    def test_upsert_and_retrieve_player(self):
        player_id = self.db.upsert_player(
            name="Rayan",
            position="M,F",
            team="BOU",
            adp=45.0,
            fpts=120.0,
            fpg=2.5,
            understat_id="14395"
        )
        self.assertIsNotNone(player_id)
        
        # Test lookup by name
        fetched_id = self.db.get_player_id_by_name("Rayan")
        self.assertEqual(player_id, fetched_id)

        # Test full profile retrieval
        profile = self.db.get_full_player_profile("Rayan")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["name"], "Rayan")
        self.assertEqual(profile["understat_id"], "14395")

    def test_explicit_alias_mapping(self):
        player_id = self.db.upsert_player(
            name="Gabriel Magalhaes",
            position="D",
            team="ARS",
            adp=24.0,
            fpts=140.0,
            fpg=3.2,
            understat_id="5613"
        )
        self.db.add_alias("Gabriel", player_id)

        fetched_id = self.db.get_player_id_by_name("Gabriel")
        self.assertEqual(player_id, fetched_id)

if __name__ == "__main__":
    unittest.main()
