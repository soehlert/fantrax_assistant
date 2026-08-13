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
        team_roster: list[dict],
        player_fpg: float | None = None,
        player_fpts: float | None = None
    ) -> dict:
        """
        Calculates letter grade, grade score (0-100), and rationale text for a draft pick,
        incorporating consensus ADP value, points monster production (FP/G), and roster need fit.
        """
        adp = player_adp if (player_adp and player_adp > 0) else 100.0
        adp_diff = overall_pick_num - adp  # Positive = Steal, Negative = Reach

        # Fetch player metrics from config if not passed explicitly
        fpg = player_fpg
        fpts = player_fpts
        if (fpg is None or fpts is None) and self.config:
            details = self.config.get_player_adp(player_name)
            if details:
                if fpg is None: fpg = float(details.get('fpg', 0.0))
                if fpts is None: fpts = float(details.get('fpts', 0.0))
        
        fpg = fpg or 0.0
        fpts = fpts or 0.0

        # Baseline score starts at 81.0 for expected consensus ADP
        reasons = []

        if adp_diff >= 0:
            value_score = 81.0 + min(10.0, adp_diff * 0.7)
            if adp_diff >= 10:
                reasons.append(f"Major value steal! {player_name} (ADP #{adp:.1f}) was selected at pick #{overall_pick_num}.")
            elif adp_diff >= 4:
                reasons.append(f"Great value pick ({player_name}, ADP #{adp:.1f} at pick #{overall_pick_num}).")
            else:
                reasons.append(f"Solid pick right around expected ADP (#{adp:.1f}).")
        else:
            reach_ratio = abs(adp_diff) / max(1.0, adp)
            penalty = min(25.0, reach_ratio * 12.0 + abs(adp_diff) * 0.2)
            value_score = 81.0 - penalty

            if adp_diff <= -25:
                reasons.append(f"Target reach. {player_name} (ADP #{adp:.1f}) was selected ahead of consensus rank at pick #{overall_pick_num}.")
            elif adp_diff <= -8:
                reasons.append(f"Slight reach based on consensus ADP (#{adp:.1f}).")
            else:
                reasons.append(f"Fair market value pick right around expected ADP (#{adp:.1f}).")

        # 2. Points Monster / Elite Production Bonus
        monster_bonus = 0.0
        if fpg >= 2.5:
            monster_bonus = min(8.5, (fpg - 2.5) * 3.2)
            if fpg >= 4.0:
                reasons.append(f"Elite points monster ({fpg:.2f} FP/G) provides top-tier scoring output.")
            elif fpg >= 3.2:
                reasons.append(f"High production profile ({fpg:.2f} FP/G) adds strong weekly scoring upside.")

        # 3. Positional Need Fit
        primary_pos = player_pos.split(',')[0].strip().upper() if player_pos else 'M'
        roster_rules = {"G": 2, "D": 5, "M": 5, "F": 3}
        current_pos_count = sum(1 for p in team_roster if p.get('position', '').split(',')[0].strip().upper() == primary_pos)
        max_pos = roster_rules.get(primary_pos, 5)

        if current_pos_count < max_pos:
            if current_pos_count == 0 and primary_pos in ('G', 'D'):
                need_score = 3.0
                reasons.append(f"Fills an urgent starting {primary_pos} roster need for {team_id}.")
            else:
                need_score = 1.0
                reasons.append(f"Addresses team {primary_pos} positional depth ({current_pos_count + 1}/{max_pos}).")
        else:
            need_score = -4.0
            reasons.append(f"Roster surplus pick—{team_id} already reached standard capacity ({max_pos}) for position {primary_pos}.")

        score = max(55.0, min(100.0, value_score + monster_bonus + need_score))

        if score >= 94: grade, grade_class = "A+", "emerald"
        elif score >= 89: grade, grade_class = "A", "emerald"
        elif score >= 85: grade, grade_class = "A-", "emerald"
        elif score >= 81: grade, grade_class = "B+", "blue"
        elif score >= 77: grade, grade_class = "B", "blue"
        elif score >= 73: grade, grade_class = "B-", "blue"
        elif score >= 68: grade, grade_class = "C+", "amber"
        elif score >= 63: grade, grade_class = "C", "amber"
        elif score >= 58: grade, grade_class = "C-", "amber"
        elif score >= 52: grade, grade_class = "D", "red"
        else: grade, grade_class = "F", "red"

        return {
            "player": player_name,
            "team_id": team_id,
            "pick_number": overall_pick_num,
            "grade": grade,
            "grade_class": grade_class,
            "score": round(score, 1),
            "adp": player_adp,
            "fpg": round(fpg, 2) if fpg else None,
            "fpts": round(fpts, 1) if fpts else None,
            "position": player_pos,
            "team": player_team,
            "rationale": " ".join(reasons)
        }

    def backfill_retroactive_analysis(self, draft_state) -> list[dict]:
        """
        Retroactively evaluates all previously drafted players in draft_history/teams
        if they do not already have an evaluation in pick_analysis_history.
        """
        owner_map = {}
        for team_name, roster in draft_state.teams.items():
            for player_obj in roster:
                p_name = player_obj.get('player') or player_obj.get('name')
                if p_name:
                    owner_map[p_name] = team_name

        sequence = list(draft_state.draft_history)
        for p in draft_state.drafted_players:
            if p not in sequence:
                sequence.append(p)

        running_rosters: dict[str, list[dict]] = {t: [] for t in draft_state.teams.keys()}
        new_history = []

        for idx, p_name in enumerate(sequence, start=1):
            owner = owner_map.get(p_name, "Other")
            details = self.config.get_player_adp(p_name) if self.config else None
            p_adp = details.get('adp') if details else None
            p_pos = details.get('position', '') if details else ''
            p_team = details.get('team', '') if details else ''

            existing_record = next((item for item in draft_state.pick_analysis_history if item.get('player') == p_name), None)
            if existing_record:
                existing_record['pick_number'] = idx
                new_history.append(existing_record)
            else:
                current_roster = running_rosters.get(owner, [])
                analysis_item = self.grade_pick(
                    player_name=p_name,
                    team_id=owner,
                    overall_pick_num=idx,
                    player_adp=p_adp,
                    player_pos=p_pos,
                    player_team=p_team,
                    team_roster=current_roster
                )
                new_history.append(analysis_item)

            if owner in running_rosters:
                running_rosters[owner].append({"player": p_name, "position": p_pos})

        draft_state.pick_analysis_history = new_history
        draft_state.save()
        return new_history
