import unittest
from fantrax_assistant.analysis import DraftPickAnalyzer

class TestDraftPickAnalyzer(unittest.TestCase):

    def test_draft_pick_analyzer_value_steal(self):
        analyzer = DraftPickAnalyzer()
        # Pick #30 drafted player with ADP #10 -> Major Value Steal (A / A+)
        result = analyzer.grade_pick(
            player_name="Jean-Philippe Mateta",
            team_id="Sam",
            overall_pick_num=30,
            player_adp=10.0,
            player_pos="F",
            player_team="CRY",
            team_roster=[]
        )

        self.assertEqual(result["player"], "Jean-Philippe Mateta")
        self.assertEqual(result["team_id"], "Sam")
        self.assertIn(result["grade"], ("A+", "A", "A-"))
        self.assertIn("Major value steal", result["rationale"])

    def test_draft_pick_analyzer_reach(self):
        analyzer = DraftPickAnalyzer()
        # Pick #10 drafted player with ADP #70 -> Reach (C / D)
        result = analyzer.grade_pick(
            player_name="Riccardo Calafiori",
            team_id="Scott",
            overall_pick_num=10,
            player_adp=70.0,
            player_pos="D",
            player_team="ARS",
            team_roster=[]
        )

        self.assertEqual(result["player"], "Riccardo Calafiori")
        self.assertIn(result["grade"], ("C+", "C", "C-", "D", "F"))
        self.assertIn("reach", result["rationale"].lower())

if __name__ == "__main__":
    unittest.main()
