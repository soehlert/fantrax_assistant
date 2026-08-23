import unittest
from fantrax_assistant.analysis import DraftPickAnalyzer

class TestDraftPickAnalyzer(unittest.TestCase):

    def test_draft_pick_analyzer_urgent_need(self):
        analyzer = DraftPickAnalyzer()
        # Pick #30 drafted player -> fills urgent starting hole (A / A-)
        result = analyzer.grade_pick(
            player_name="Jean-Philippe Mateta",
            team_id="Sam",
            overall_pick_num=30,
            player_adp=10.0,
            player_pos="F",
            player_team="CRY",
            team_roster=[],
            player_fpg=4.1
        )

        self.assertEqual(result["player"], "Jean-Philippe Mateta")
        self.assertEqual(result["team_id"], "Sam")
        self.assertIn(result["grade"], ("A+", "A", "A-"))
        self.assertIn("fills an urgent starting hole", result["rationale"])

    def test_draft_pick_analyzer_roster_surplus(self):
        analyzer = DraftPickAnalyzer()
        # Pick player when carrying max roster capacity -> Roster Surplus Pick
        roster_full = [{'player': f'M{i}', 'position': 'M'} for i in range(5)]
        result = analyzer.grade_pick(
            player_name="Alex Iwobi",
            team_id="Hayden",
            overall_pick_num=107,
            player_adp=70.4,
            player_pos="M",
            player_team="FUL",
            team_roster=roster_full,
            player_fpg=4.26
        )

        self.assertEqual(result["player"], "Alex Iwobi")
        self.assertIn("roster surplus pick", result["rationale"])

    def test_backfill_retroactive_analysis(self):
        analyzer = DraftPickAnalyzer()

        class MockDraftState:
            def __init__(self):
                self.teams = {"Sam": [{"player": "Jean-Philippe Mateta"}]}
                self.draft_history = ["Jean-Philippe Mateta"]
                self.drafted_players = {"Jean-Philippe Mateta"}
                self.pick_analysis_history = []
            def save(self):
                pass

        mock_state = MockDraftState()
        history = analyzer.backfill_retroactive_analysis(mock_state)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["player"], "Jean-Philippe Mateta")
        self.assertEqual(history[0]["team_id"], "Sam")

    def test_opportunity_cost_penalty(self):
        analyzer = DraftPickAnalyzer()
        available = [
            {"player": "Player A", "position": "M", "fpg": 2.2, "adp": 40.0},
            {"player": "Player B", "position": "M", "fpg": 4.1, "adp": 35.0}, # Better available M
        ]
        # Drafting Player A (2.2 FP/G) when Player B (4.1 FP/G) is available at same position
        result = analyzer.grade_pick(
            player_name="Player A",
            team_id="Sam",
            overall_pick_num=35,
            player_adp=40.0,
            player_pos="M",
            player_team="MCI",
            team_roster=[],
            player_fpg=2.2,
            available_players=available
        )

        self.assertIn("leaves a bit of value on the table", result["rationale"])
        self.assertIn("Player B", result["rationale"])

    def test_evaluate_team_grade_and_all_teams(self):
        analyzer = DraftPickAnalyzer()

        class MockDraftState:
            def __init__(self):
                self.teams = {
                    "Sam": [
                        {"player": "Erling Haaland", "position": "F", "fpg": 6.94, "fpts": 208.0, "team": "MCI"},
                        {"player": "Rayan Cherki", "position": "M", "fpg": 5.49, "fpts": 154.0, "team": "MCI"},
                        {"player": "Eberechi Eze", "position": "M,F", "fpg": 5.81, "fpts": 105.0, "team": "ARS"},
                        {"player": "Jean-Philippe Mateta", "position": "F", "fpg": 4.57, "fpts": 146.0, "team": "CRY"},
                        {"player": "Jordan Pickford", "position": "G", "fpg": 3.80, "fpts": 114.0, "team": "EVE"}
                    ],
                    "Scott": [
                        {"player": "Cole Palmer", "position": "M", "fpg": 5.45, "fpts": 158.0, "team": "CHE"},
                        {"player": "Igor Thiago", "position": "F", "fpg": 4.36, "fpts": 140.0, "team": "BRF"}
                    ]
                }
                self.draft_history = ["Erling Haaland", "Cole Palmer", "Rayan Cherki", "Eberechi Eze", "Jean-Philippe Mateta", "Igor Thiago", "Jordan Pickford"]
                self.drafted_players = set(self.draft_history)
                self.pick_analysis_history = []
            def save(self):
                pass

        mock_state = MockDraftState()
        sam_grade = analyzer.evaluate_team_grade("Sam", mock_state)
        self.assertEqual(sam_grade["team_id"], "Sam")
        self.assertIn(sam_grade["grade"], ("A+", "A", "A-", "B+", "B"))
        self.assertIn("star_power", sam_grade["components"])
        self.assertIn("pick_efficiency", sam_grade["components"])
        self.assertIn("roster_balance", sam_grade["components"])
        self.assertIn("availability", sam_grade["components"])
        self.assertIn("headline", sam_grade["writeup"])
        self.assertIn("executive_summary", sam_grade["writeup"])
        self.assertIn("verdict", sam_grade["writeup"])

        all_grades = analyzer.evaluate_all_tracked_teams(mock_state)
        self.assertEqual(len(all_grades), 2)
        self.assertIn("Sam", all_grades)
        self.assertIn("Scott", all_grades)
        self.assertIn(all_grades["Sam"]["rank"], (1, 2))
        self.assertIn(all_grades["Scott"]["rank"], (1, 2))

if __name__ == "__main__":
    unittest.main()

