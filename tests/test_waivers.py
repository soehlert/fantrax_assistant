import unittest
import json
import shutil
from pathlib import Path
from fantrax_assistant.config import DraftConfig
from fantrax_assistant.draft_state import DraftState
from fantrax_assistant.waiver_manager import WaiverManagerEngine

class TestWaiversAndTransactions(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("scratch/test_waivers_temp")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.test_dir / "draft_state.json"

        # Create dummy draft state
        dummy_state = {
            "my_team": "TestTeam",
            "drafted_players": ["Erling Haaland", "Bukayo Saka"],
            "teams": {
                "TestTeam": [
                    {"player": "Erling Haaland", "position": "F", "team": "MCI", "fpg": 6.5, "fpts": 65.0, "adp": 1.0},
                    {"player": "Bukayo Saka", "position": "M", "team": "ARS", "fpg": 5.8, "fpts": 58.0, "adp": 4.0}
                ]
            },
            "transactions_history": []
        }
        with open(self.state_file, "w") as f:
            json.dump(dummy_state, f)

        self.config = DraftConfig()
        self.config.load_all_data()
        self.state = DraftState(state_file=self.state_file)
        self.waiver_engine = WaiverManagerEngine(config=self.config)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_add_and_drop_transaction(self):
        """Test adding a free agent and dropping an existing player."""
        new_player = {"player": "Cole Palmer", "position": "M", "team": "CHE", "fpg": 6.0, "fpts": 60.0, "adp": 10.0}
        
        # Add Cole Palmer, drop Bukayo Saka
        success = self.state.add_player_to_team(
            team_name="TestTeam",
            player=new_player,
            dropped_player_name="Bukayo Saka",
            notes="Waiver Pickup Upgrade"
        )
        self.assertTrue(success)

        # Check roster
        roster_names = [p['player'] for p in self.state.get_team("TestTeam")]
        self.assertIn("Cole Palmer", roster_names)
        self.assertNotIn("Bukayo Saka", roster_names)

        # Check transaction history log
        self.assertEqual(len(self.state.transactions_history), 2)  # 1 Drop + 1 Add/Drop log
        tx = self.state.transactions_history[-1]
        self.assertEqual(tx['type'], "ADD & DROP")
        self.assertEqual(tx['player'], "Cole Palmer")
        self.assertEqual(tx['dropped_player'], "Bukayo Saka")

    def test_waiver_pickup_recommendations(self):
        """Test generating free agent pickup suggestions using WaiverManagerEngine."""
        recs = self.waiver_engine.get_pickup_recommendations("TestTeam", self.state, limit=5)
        self.assertTrue(len(recs) > 0)
        
        top_pick = recs[0]
        self.assertIn('player', top_pick)
        self.assertIn('effective_fpg', top_pick)
        self.assertIn('net_gain', top_pick)
        self.assertNotIn(top_pick['player'], self.state.drafted_players)

if __name__ == '__main__':
    unittest.main()
