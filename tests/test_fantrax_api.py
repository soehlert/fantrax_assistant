"""Unit tests for Fantrax API client and roster sync."""

import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from fantrax_assistant.scrapers.fantrax_api import FantraxClient
from fantrax_assistant.draft_state import DraftState

class TestFantraxAPI(unittest.TestCase):

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.cache_dir = Path(self.temp_dir.name)
        self.client = FantraxClient(cache_dir=self.cache_dir)
        self.state_file = self.cache_dir / "draft_state.json"
        self.state = DraftState(state_file=self.state_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_league_id(self):
        res = self.client.fetch_league_rosters("")
        self.assertIn("error", res)

    def test_sync_team_roster_simulated(self):
        res = self.client.sync_team_roster("test_league_123", "Sam", self.state)
        self.assertTrue(res.get("success"))
        self.assertIn("synced_at", res)

    def test_parse_fantrax_roster_response(self):
        raw_data = {
            "rosters": {
                "team_1": {
                    "teamName": "Sam",
                    "starters": [{"name": "Eberechi Eze"}, {"name": "Matheus Nunes"}],
                    "bench": [{"name": "Mikkel Damsgaard"}],
                    "roster": [{"name": "Eberechi Eze"}, {"name": "Matheus Nunes"}, {"name": "Mikkel Damsgaard"}]
                }
            }
        }
        parsed = self.client._parse_fantrax_roster_response(raw_data)
        self.assertIn("Sam", parsed["teams"])
        self.assertEqual(len(parsed["teams"]["Sam"]["starters"]), 2)
        self.assertEqual(len(parsed["teams"]["Sam"]["bench"]), 1)

    def test_sync_by_team_id(self):
        mock_raw = {
            "rosters": {
                "team_1": {
                    "teamId": "12345",
                    "teamName": "Sam Team",
                    "starters": [{"name": "Eberechi Eze"}, {"name": "Matheus Nunes"}],
                    "bench": [{"name": "Mikkel Damsgaard"}],
                    "roster": [{"name": "Eberechi Eze"}, {"name": "Matheus Nunes"}, {"name": "Mikkel Damsgaard"}]
                }
            }
        }
        with patch.object(self.client, "fetch_league_rosters") as mock_fetch:
            mock_fetch.return_value = self.client._parse_fantrax_roster_response(mock_raw)
            res = self.client.sync_team_roster("test_league_123", "12345", self.state)
            self.assertTrue(res.get("success"))
            self.assertIn("Sam Team", self.state.custom_lineups)
            self.assertEqual(self.state.custom_lineups["Sam Team"], ["Eberechi Eze", "Matheus Nunes"])

    def test_web_sync_endpoint(self):
        import asyncio
        from web.main import sync_fantrax_endpoint
        res = asyncio.run(sync_fantrax_endpoint("Sam"))
        self.assertTrue(res.get("success"))

    def test_parse_fxea_enveloped_response(self):
        envelope_data = {
            "responses": [
                {
                    "data": {
                        "rosters": {
                            "t1": {
                                "teamName": "FC United",
                                "teamId": "9988",
                                "starters": [{"name": "Erling Haaland"}],
                                "bench": [{"name": "Cole Palmer"}]
                            }
                        }
                    }
                }
            ]
        }
        parsed = self.client._parse_fantrax_roster_response(envelope_data)
        self.assertIn("FC United", parsed["teams"])
        self.assertEqual(parsed["teams"]["FC United"]["team_id"], "9988")
        self.assertEqual(parsed["teams"]["FC United"]["starters"], ["Erling Haaland"])

    def test_parse_tables_response(self):
        table_data = {
            "tables": [
                {
                    "title": "Arsenal Squad",
                    "teamId": "ars_1",
                    "rows": [
                        {"scorer": {"name": "Bukayo Saka"}, "status": "Active"},
                        {"scorer": {"name": "Gabriel Jesus"}, "status": "Res"}
                    ]
                }
            ]
        }
        parsed = self.client._parse_fantrax_roster_response(table_data)
        self.assertIn("Arsenal Squad", parsed["teams"])
        self.assertEqual(parsed["teams"]["Arsenal Squad"]["starters"], ["Bukayo Saka"])
        self.assertEqual(parsed["teams"]["Arsenal Squad"]["bench"], ["Gabriel Jesus"])

if __name__ == "__main__":
    unittest.main()
