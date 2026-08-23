import unittest
import asyncio
from pathlib import Path
from starlette.requests import Request

import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "src" / "web"))

from main import app, config, read_root, read_team, read_draft_analysis, read_player_profile, api_team_suggestions, db_mgr

class TestWebRoutesWithDB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config.load_all_data()

    def test_root_route(self):
        req = Request({'type': 'http', 'method': 'GET', 'path': '/', 'headers': []})
        req.scope['app'] = app
        res = asyncio.run(read_root(req))
        self.assertEqual(res.status_code, 200)

    def test_tracked_team_route(self):
        req = Request({'type': 'http', 'method': 'GET', 'path': '/teams/Sam', 'headers': []})
        req.scope['app'] = app
        res = asyncio.run(read_team(req, 'Sam'))
        self.assertEqual(res.status_code, 200)
        body = res.body.decode()
        self.assertIn("Draft Rating", body)
        self.assertIn("Sports Analyst Writeup", body)

    def test_draft_analysis_route(self):
        req = Request({'type': 'http', 'method': 'GET', 'path': '/draft/analysis', 'headers': []})
        req.scope['app'] = app
        res = asyncio.run(read_draft_analysis(req))
        self.assertEqual(res.status_code, 200)
        body = res.body.decode()
        self.assertIn("Tracked Team Grades", body)

    def test_player_profile_by_uuid(self):
        p_id = db_mgr.get_player_id_by_name("Jordan Pickford")
        req = Request({'type': 'http', 'method': 'GET', 'path': f'/player/{p_id}', 'headers': []})
        req.scope['app'] = app
        res = asyncio.run(read_player_profile(req, p_id))
        self.assertEqual(res.status_code, 200)
        self.assertIn("Jordan Pickford", res.body.decode())
        self.assertIn("Draft Player", res.body.decode())

    def test_team_suggestions_api(self):
        res = asyncio.run(api_team_suggestions("Sam", page=1))
        self.assertIn("players", res)
        self.assertGreater(len(res["players"]), 0)
        # Check that player objects contain UUID id
        first_player = res["players"][0]
        self.assertIn("id", first_player)

if __name__ == "__main__":
    unittest.main()
