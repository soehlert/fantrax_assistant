import unittest
from fantrax_assistant.weekly import WeeklyManagerEngine

class TestWeeklyManagerEngine(unittest.TestCase):

    def setUp(self):
        self.engine = WeeklyManagerEngine()
        self.sample_roster = [
            {'player': 'Jordan Pickford', 'position': 'G', 'team': 'EVE', 'fpg': 3.5},
            {'player': 'Gabriel Magalhaes', 'position': 'D', 'team': 'ARS', 'fpg': 4.1},
            {'player': 'Virgil van Dijk', 'position': 'D', 'team': 'LIV', 'fpg': 3.9},
            {'player': 'Pedro Porro', 'position': 'D', 'team': 'TOT', 'fpg': 3.6},
            {'player': 'Daniel Munoz', 'position': 'D', 'team': 'CRY', 'fpg': 3.4},
            {'player': 'Bruno Fernandes', 'position': 'M', 'team': 'MUN', 'fpg': 4.3},
            {'player': 'Rayan Cherki', 'position': 'M', 'team': 'MCI', 'fpg': 3.8},
            {'player': 'Eberechi Eze', 'position': 'M', 'team': 'ARS', 'fpg': 3.7},
            {'player': 'Cole Palmer', 'position': 'M', 'team': 'CHE', 'fpg': 4.2},
            {'player': 'Erling Haaland', 'position': 'F', 'team': 'MCI', 'fpg': 5.0},
            {'player': 'Alexander Isak', 'position': 'F', 'team': 'LIV', 'fpg': 3.8},
            # Bench candidates
            {'player': 'Antoine Semenyo', 'position': 'M,F', 'team': 'MCI', 'fpg': 3.5},
            {'player': 'Dominik Szoboszlai', 'position': 'M', 'team': 'LIV', 'fpg': 3.2},
            {'player': 'Ollie Watkins', 'position': 'F', 'team': 'AVL', 'fpg': 3.4},
        ]

    def test_optimal_lineup_formation(self):
        lineup = self.engine.get_optimal_lineup(self.sample_roster)
        starters = lineup['starters']
        bench = lineup['bench']

        self.assertEqual(len(starters), 11)
        self.assertEqual(len(bench), len(self.sample_roster) - 11)

        # Check goalkeeper count
        gks = [p for p in starters if p['primary_pos'] == 'G']
        self.assertEqual(len(gks), 1)

        # Check formation bounds
        ds = len([p for p in starters if p['primary_pos'] == 'D'])
        ms = len([p for p in starters if p['primary_pos'] == 'M'])
        fs = len([p for p in starters if p['primary_pos'] == 'F'])

        self.assertTrue(3 <= ds <= 5)
        self.assertTrue(3 <= ms <= 5)
        self.assertTrue(1 <= fs <= 3)
        self.assertGreater(lineup['total_projected_fpts'], 0)

    def test_auto_sub_recommendations(self):
        lineup = self.engine.get_optimal_lineup(self.sample_roster)
        auto_subs = self.engine.get_auto_sub_recommendations(lineup['starters'], lineup['bench'])

        self.assertIsInstance(auto_subs, list)
        if auto_subs:
            sub = auto_subs[0]
            self.assertIn('starter', sub)
            self.assertIn('sub_candidate', sub)
            self.assertIn('rule_text', sub)
            # Check kickoff condition
            self.assertGreaterEqual(sub['sub_kickoff'], sub['starter_kickoff'])

if __name__ == '__main__':
    unittest.main()
