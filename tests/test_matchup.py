"""Unit tests for live Fantrax matchup tracker backend and web routes."""

import unittest
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from starlette.requests import Request

from fantrax_assistant.scrapers.fantrax_api import FantraxClient
from fantrax_assistant.config import DraftConfig
from web.main import app, read_live_matchup, api_live_matchup, api_live_matchup_sync

class TestMatchupEngine(unittest.TestCase):

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.cache_dir = Path(self.temp_dir.name)
        self.client = FantraxClient(cache_dir=self.cache_dir)
        self.config = DraftConfig()
        self.config.load_all_data()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_league_id_matchup(self):
        res = self.client.get_live_matchup(league_id="", team_name_or_id="Sam")
        self.assertFalse(res.get("has_data"))
        self.assertIn("error", res)

    def test_get_live_matchup_structure(self):
        mock_info = {
            "scoringPeriods": [
                {"number": 1, "startDate": "2026-08-21T15:00:00.0-0400", "endDate": "2026-08-28T14:59:59.0-0400"},
                {"number": 2, "startDate": "2026-08-28T15:00:00.0-0400", "endDate": "2026-09-04T14:59:59.0-0400"}
            ],
            "teamInfo": {
                "t1": {"name": "Cucu For Kudus Puffs", "id": "t1"},
                "t2": {"name": "Opponent FC", "id": "t2"}
            }
        }
        mock_scores = {
            "period": 1,
            "matchups": [
                {
                    "home": {"teamName": "Cucu For Kudus Puffs", "teamId": "t1", "score": 45.5, "gamesPlayed": 8},
                    "away": {"teamName": "Opponent FC", "teamId": "t2", "score": 38.0, "gamesPlayed": 7},
                    "categories": [
                        {
                            "name": "Goals",
                            "shortName": "G",
                            "group": "Outfielder",
                            "home": {"value": 2.0, "points": 10.0, "display": "2"},
                            "away": {"value": 1.0, "points": 5.0, "display": "1"}
                        },
                        {
                            "name": "Clean Sheets",
                            "shortName": "CS",
                            "group": "Outfielder",
                            "home": {"value": 1.0, "points": 4.0, "display": "1"},
                            "away": {"value": 2.0, "points": 8.0, "display": "2"}
                        }
                    ]
                }
            ]
        }
        mock_rosters = {
            "teams": {
                "t1": {
                    "team_id": "t1",
                    "team_name": "Cucu For Kudus Puffs",
                    "starters": ["Bukayo Saka", "Erling Haaland"],
                    "bench": ["Cole Palmer"],
                    "player_details": {
                        "Bukayo Saka": {"position": "M", "team": "ARS", "id": "p1"},
                        "Erling Haaland": {"position": "F", "team": "MCI", "id": "p2"},
                        "Cole Palmer": {"position": "M", "team": "CHE", "id": "p3"}
                    }
                },
                "t2": {
                    "team_id": "t2",
                    "team_name": "Opponent FC",
                    "starters": ["Son Heung-min"],
                    "bench": [],
                    "player_details": {
                        "Son Heung-min": {"position": "F", "team": "TOT", "id": "p4"}
                    }
                }
            }
        }

        self.client.fetch_league_info = lambda *args, **kwargs: mock_info
        self.client.fetch_matchup_scores = lambda *args, **kwargs: mock_scores
        self.client.fetch_period_rosters = lambda *args, **kwargs: mock_rosters

        res = self.client.get_live_matchup(
            league_id="test_league",
            team_name_or_id="Cucu For Kudus Puffs",
            period=1,
            config=self.config
        )

        self.assertTrue(res.get("has_data"))
        self.assertEqual(res["current_period"], 1)
        self.assertEqual(res["home"]["name"], "Cucu For Kudus Puffs")
        self.assertEqual(res["home"]["score"], 45.5)
        self.assertEqual(res["away"]["name"], "Opponent FC")
        self.assertEqual(res["away"]["score"], 38.0)
        self.assertEqual(res["score_diff"], 7.5)
        self.assertTrue(res["is_user_home"])
        self.assertFalse(res["is_user_away"])

        # Check category parsing
        self.assertEqual(len(res["categories"]), 2)
        cat1 = res["categories"][0]
        self.assertEqual(cat1["name"], "Goals")
        self.assertEqual(cat1["pts_diff"], 5.0)
        self.assertEqual(cat1["leader"], "home")

        cat2 = res["categories"][1]
        self.assertEqual(cat2["name"], "Clean Sheets")
        self.assertEqual(cat2["pts_diff"], -4.0)
        self.assertEqual(cat2["leader"], "away")

    def test_live_matchup_web_routes(self):
        req = Request({'type': 'http', 'method': 'GET', 'path': '/matchup', 'headers': []})
        req.scope['app'] = app
        res = asyncio.run(read_live_matchup(req, period=1))
        self.assertEqual(res.status_code, 200)
        body = res.body.decode()
        self.assertIn("Live Matchup Tracker", body)

    def test_live_matchup_api_route(self):
        res = asyncio.run(api_live_matchup(period=1))
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.body.decode())
        self.assertIn("has_data", data)
        self.assertIn("periods", data)

    def test_live_matchup_sync_post(self):
        scope = {
            'type': 'http',
            'method': 'POST',
            'path': '/api/matchup/sync',
            'headers': [(b'content-type', b'application/json')],
            'app': app
        }
        async def mock_receive():
            return {'type': 'http.request', 'body': b'{"period": 1}'}

        req = Request(scope, mock_receive)
        res = asyncio.run(api_live_matchup_sync(req))
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.body.decode())
        self.assertIn("has_data", data)

if __name__ == "__main__":
    unittest.main()
