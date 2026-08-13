"""Module for evaluating draft picks, assigning letter grades (A+ through F), and generating pick rationale."""

class DraftPickAnalyzer:
    """Evaluates draft picks based on ADP value steal/reach, position need fit, and projections."""

    def __init__(self, config=None):
        self.config = config

    def grade_pick(
        self,
        player_name: str,
        team_id: str,
        overall_pick_num: int,
        player_adp: float | None,
        player_pos: str,
        player_team: str,
        team_roster: list[dict]
    ) -> dict:
        """
        Calculates letter grade, grade score (0-100), and rationale text for a draft pick.
        """
        adp = player_adp if (player_adp and player_adp > 0) else 100.0
        adp_diff = overall_pick_num - adp  # Positive = Steal (taken later than ADP), Negative = Reach

        score = 82.0 + (adp_diff * 0.8)
        reasons = []

        if adp_diff >= 15:
            reasons.append(f"Major value steal! {player_name} (ADP #{adp:.1f}) was selected at pick #{overall_pick_num}.")
        elif adp_diff >= 5:
            reasons.append(f"Great value pick ({player_name}, ADP #{adp:.1f} at pick #{overall_pick_num}).")
        elif adp_diff <= -20:
            reasons.append(f"Significant reach. {player_name} (ADP #{adp:.1f}) was selected early at pick #{overall_pick_num}.")
        elif adp_diff <= -8:
            reasons.append(f"Slight reach based on consensus ADP (#{adp:.1f}).")
        else:
            reasons.append(f"Fair market value pick right around expected ADP (#{adp:.1f}).")

        primary_pos = player_pos.split(',')[0].strip().upper() if player_pos else 'M'
        roster_rules = {"G": 2, "D": 5, "M": 5, "F": 3}
        current_pos_count = sum(1 for p in team_roster if p.get('position', '').split(',')[0].strip().upper() == primary_pos)
        max_pos = roster_rules.get(primary_pos, 5)

        if current_pos_count < max_pos:
            if current_pos_count == 0 and primary_pos in ('G', 'D'):
                score += 6.0
                reasons.append(f"Fills an urgent starting {primary_pos} roster need for {team_id}.")
            else:
                score += 3.0
                reasons.append(f"Addresses team {primary_pos} positional depth ({current_pos_count + 1}/{max_pos}).")
        else:
            score -= 8.0
            reasons.append(f"Roster surplus pick—{team_id} already reached standard capacity ({max_pos}) for position {primary_pos}.")

        score = max(50.0, min(100.0, score))

        if score >= 97: grade, grade_class = "A+", "emerald"
        elif score >= 93: grade, grade_class = "A", "emerald"
        elif score >= 90: grade, grade_class = "A-", "emerald"
        elif score >= 87: grade, grade_class = "B+", "blue"
        elif score >= 83: grade, grade_class = "B", "blue"
        elif score >= 80: grade, grade_class = "B-", "blue"
        elif score >= 77: grade, grade_class = "C+", "amber"
        elif score >= 73: grade, grade_class = "C", "amber"
        elif score >= 70: grade, grade_class = "C-", "amber"
        elif score >= 60: grade, grade_class = "D", "red"
        else: grade, grade_class = "F", "red"

        return {
            "player": player_name,
            "team_id": team_id,
            "pick_number": overall_pick_num,
            "grade": grade,
            "grade_class": grade_class,
            "score": round(score, 1),
            "adp": player_adp,
            "position": player_pos,
            "team": player_team,
            "rationale": " ".join(reasons)
        }
