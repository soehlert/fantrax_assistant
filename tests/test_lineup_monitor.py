"""Unit tests for LineupMonitor and 24h pre-gameweek health checks."""

import unittest
from datetime import datetime, timezone, timedelta
from fantrax_assistant.config import DraftConfig
from fantrax_assistant.lineup_monitor import LineupMonitor

class TestLineupMonitor(unittest.TestCase):

    def setUp(self):
        self.config = DraftConfig()
        self.config.load_all_data()
        self.monitor = LineupMonitor(config=self.config)
        # Disable live notification dispatch during unit testing
        self.monitor.notifier.slack_url = ""
        self.monitor.notifier.macos_enabled = False
        self.monitor.notifier.ntfy_topic = ""

    def test_custom_starters_lineup_alert(self):
        # Mock roster
        roster = [
            {"player": "Mathys Tel", "position": "M", "team": "TOT", "assigned_pos": "M", "fixture": {"kickoff_time": (datetime.now(timezone.utc) + timedelta(minutes=45)).isoformat(), "display_time": "Today, 3:00 PM", "is_benched_override": True}},
            {"player": "Conor Gallagher", "position": "M", "team": "TOT", "assigned_pos": "M", "fixture": {"kickoff_time": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(), "display_time": "Tomorrow, 8:00 PM"}}
        ]
        # When Tel is chosen as custom starter
        alerts = self.monitor.check_team_lineup_alerts("Sam", roster, custom_starters=["Mathys Tel"])
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["starter"], "Mathys Tel")

    def test_gameweek_eve_health_incomplete_lineup(self):
        # Incomplete roster with only 2 players (fewer than 11)
        roster = [
            {"player": "Mathys Tel", "position": "M", "team": "TOT", "fixture": {"kickoff_time": (datetime.now(timezone.utc) + timedelta(hours=20)).isoformat(), "display_time": "Tomorrow, 3:00 PM"}},
            {"player": "Conor Gallagher", "position": "M", "team": "TOT", "fixture": {"kickoff_time": (datetime.now(timezone.utc) + timedelta(hours=20)).isoformat(), "display_time": "Tomorrow, 3:00 PM"}}
        ]
        reminder = self.monitor.check_gameweek_eve_health("Sam", roster)
        self.assertIsNotNone(reminder)
        self.assertIn("Incomplete Starting XI", reminder["message"])

if __name__ == "__main__":
    unittest.main()
