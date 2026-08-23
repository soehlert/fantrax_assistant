"""Module for evaluating draft picks, assigning letter grades (A+ through F), and generating pick rationale."""

class DraftPickAnalyzer:
    """Evaluates draft picks based on ADP value steal/reach, position need fit, and projections."""

    def __init__(self, config=None):
        self.config = config
        self._eff_fpg_cache: dict = {}
        self._rank_cache: dict = {}

    def calculate_rotation_factor(self, player_name: str, team_code: str = "") -> float:
        """
        Calculates rotation risk factor (0.75 to 1.0) based on season starts, minutes,
        and Big-6 squad rotation depth (matching PlayerRecommendationEngine).
        """
        if not self.config:
            return 1.0

        stats = self.config.get_player_stats(player_name) or {}
        if not stats or not isinstance(stats, dict):
            return 1.0

        starts = int(stats.get('starts', 0) or 0)
        mins = int(stats.get('minutes', 0) or 0)
        matches = int(stats.get('matches_played', 0) or 0)

        team = str(team_code or stats.get('team', '')).upper()
        if not team and self.config:
            details = self.config.get_player_adp(player_name)
            if details:
                team = str(details.get('team', '')).upper()

        is_big_six = team in {'ARS', 'MCI', 'CHE', 'LIV', 'MUN', 'TOT'}

        mins_per_match = (mins / matches) if matches > 0 else 0.0

        if starts < 15 or mins_per_match < 60.0:
            return 0.75 if is_big_six else 0.82
        elif (is_big_six and starts >= 24) or (not is_big_six and starts >= 20):
            return 1.0
        elif (is_big_six and starts >= 18) or (not is_big_six and starts >= 15):
            return 0.93
        else:
            return 0.85

    def get_effective_fpg(self, player_name: str, raw_fpg: float | None = None, raw_fpts: float | None = None) -> float:
        """
        Calculates sample-size regressed, rotation-risk-adjusted, and injury-discounted effective FP/G.
        Prevents small sample size outliers or rotation bench players from distorting evaluations.
        """
        cache_key = (player_name, raw_fpg, raw_fpts)
        if cache_key in self._eff_fpg_cache:
            return self._eff_fpg_cache[cache_key]

        fpg = raw_fpg
        fpts = raw_fpts
        matches = None
        inj_severity = "Healthy"

        if self.config:
            details = self.config.get_player_adp(player_name)
            if details:
                if fpg is None or fpg == 0: fpg = float(details.get('fpg', 0.0) or 0.0)
                if fpts is None or fpts == 0: fpts = float(details.get('fpts', 0.0) or 0.0)

            stats = self.config.get_player_stats(player_name)
            if stats and isinstance(stats, dict) and 'matches_played' in stats:
                matches = int(stats.get('matches_played', 0) or 0)
            
            inj = self.config.get_player_injury(player_name)
            if inj:
                inj_severity = inj.get("severity", "Healthy")

        fpg_val = fpg or 0.0

        # Long-term / Season-ending injuries heavily discount available FP/G
        if "Long Term" in inj_severity or "Out" in inj_severity:
            res = min(fpg_val, 1.5)
        elif "Medium Term" in inj_severity:
            res = fpg_val * 0.75
        elif "Short Term" in inj_severity:
            res = fpg_val * 0.90
        else:
            res = fpg_val

        adp_val = 999.0
        if self.config:
            details = self.config.get_player_adp(player_name)
            if details:
                adp_val = float(details.get('adp', 999.0) or 999.0)

        # Sample size regression for unproven / low sample players
        if adp_val <= 60 and (matches is None or matches >= 10):
            res = res
        elif matches is not None and matches > 0 and matches < 15:
            res = (res * matches + 2.25 * (15 - matches)) / 15.0

        # Apply rotation risk adjustment
        rot_factor = self.calculate_rotation_factor(player_name)
        res *= rot_factor

        final_val = max(0.0, res)
        self._eff_fpg_cache[cache_key] = final_val
        return final_val

    def get_quality_available_count(self, position: str, available_players: list[dict] | None) -> int:
        """Counts remaining quality starting options available at a specific position."""
        if not available_players:
            return 10
        count = 0
        for p in available_players:
            p_pos = (p.get('position') or '').split(',')[0].strip().upper()
            if p_pos == position:
                p_name = p.get('player') or p.get('name')
                eff = self.get_effective_fpg(p_name, float(p.get('fpg') or 0.0), float(p.get('fpts') or 0.0))
                adp = float(p.get('adp') or 999.0)
                if eff >= 3.0 or adp <= 100:
                    count += 1
        return count

    def get_positional_cliff(self, position: str, available_players: list[dict] | None) -> tuple[float, str]:
        """
        Calculates the production drop-off (cliff) between the top 1-2 available options
        and the next tier of available options at a position.
        Returns (fpg_drop_off, cliff_description).
        """
        if not available_players:
            return 0.0, ""

        same_pos = []
        for p in available_players:
            p_pos = (p.get('position') or '').split(',')[0].strip().upper()
            if p_pos == position:
                p_name = p.get('player') or p.get('name')
                eff = self.get_effective_fpg(p_name, float(p.get('fpg') or 0.0), float(p.get('fpts') or 0.0))
                same_pos.append((p_name, eff))

        if len(same_pos) < 3:
            return 0.0, ""

        same_pos.sort(key=lambda x: x[1], reverse=True)

        top_fpg = same_pos[0][1]
        next_tier_fpg = same_pos[min(2, len(same_pos) - 1)][1]

        drop_off = top_fpg - next_tier_fpg
        if drop_off >= 0.65:
            desc = f"Steep {position} production cliff: Top available {same_pos[0][0]} ({top_fpg:.2f} FP/G) is +{drop_off:.2f} FP/G above remaining tier ({next_tier_fpg:.2f} FP/G)."
            return drop_off, desc

        return drop_off, ""

    def get_player_relative_rank(self, player_name: str, fpts: float) -> tuple[int, float]:
        """
        Determines the player's relative rank and percentile in total projected fantasy points
        across the entire league player pool.
        """
        cache_key = (player_name, fpts)
        if cache_key in self._rank_cache:
            return self._rank_cache[cache_key]

        if self.config and hasattr(self.config, 'rankings') and isinstance(self.config.rankings, dict):
            rankings = self.config.rankings.get("rankings", [])
            if rankings:
                sorted_by_fpts = sorted(rankings, key=lambda p: float(p.get('fpts') or 0.0), reverse=True)
                for rank_idx, p in enumerate(sorted_by_fpts, start=1):
                    p_name = p.get('player') or p.get('name')
                    if p_name and p_name == player_name:
                        percentile = (1.0 - (rank_idx / len(rankings))) * 100.0
                        res = (rank_idx, percentile)
                        self._rank_cache[cache_key] = res
                        return res
        
        # Fallback based on absolute FPts cutoffs if config/rankings pool not available
        if fpts >= 180: res = (5, 99.0)
        elif fpts >= 150: res = (18, 97.0)
        elif fpts >= 135: res = (45, 93.0)
        elif fpts >= 115: res = (90, 85.0)
        else: res = (150, 70.0)

        self._rank_cache[cache_key] = res
        return res

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
        player_fpts: float | None = None,
        available_players: list[dict] | None = None
    ) -> dict:
        """
        Calculates letter grade, grade score (0-100), and rationale text for a draft pick,
        incorporating consensus ADP value, points monster production (FP/G), roster need fit,
        and positional opportunity cost vs. available alternatives on the board.
        """
        try:
            adp = float(player_adp) if (player_adp is not None and float(player_adp) > 0) else 100.0
        except (ValueError, TypeError):
            adp = 100.0
        overall_pick_num = int(overall_pick_num) if overall_pick_num else 1
        adp_diff = overall_pick_num - adp  # Positive = Steal (pick > ADP), Negative = Reach (pick < ADP)

        # Fetch player metrics from config if not passed explicitly
        fpg = player_fpg
        fpts = player_fpts
        if self.config:
            details = self.config.get_player_adp(player_name)
            if details:
                if fpg is None: fpg = float(details.get('fpg', 0.0))
                if fpts is None: fpts = float(details.get('fpts', 0.0))
        
        fpg_raw = fpg or 0.0
        fpts = fpts or 0.0

        if self.config:
            details = self.config.get_player_adp(player_name)
            if details:
                if not player_adp or player_adp == 999.0:
                    player_adp = details.get('adp')
                if not fpg_raw:
                    fpg_raw = float(details.get('fpg', 0.0) or 0.0)
                if not fpts:
                    fpts = float(details.get('fpts', 0.0) or 0.0)

        # Calculate sample-size regressed & injury-adjusted effective FP/G for drafted player
        eff_fpg = self.get_effective_fpg(player_name, fpg_raw, fpts)

        # 1. Custom League Scoring Production Base (Primary Value Anchor - 70% weight)
        if eff_fpg >= 5.0:
            prod_base = 88.0
        elif eff_fpg >= 4.2:
            prod_base = 83.0
        elif eff_fpg >= 3.5:
            prod_base = 78.0
        elif eff_fpg >= 2.8:
            prod_base = 74.0
        else:
            prod_base = 68.0

        # 2. Roster Need & Capacity Fit
        primary_pos = player_pos.split(',')[0].strip().upper() if player_pos else 'M'
        roster_rules = {"G": 1, "D": 5, "M": 5, "F": 4}
        max_pos = roster_rules.get(primary_pos, 5)

        pos_counts = {p: 0 for p in roster_rules}
        for p in team_roster:
            p_pos = (p.get('position') or '').split(',')[0].strip().upper()
            if p_pos in pos_counts:
                pos_counts[p_pos] += 1

        current_pos_count = pos_counts.get(primary_pos, 0)
        quality_g_left = self.get_quality_available_count('G', available_players)
        g_is_scarce = (quality_g_left <= 8)
        cliff_drop, cliff_desc = self.get_positional_cliff(primary_pos, available_players)

        need_score = 0.0
        if current_pos_count >= max_pos:
            need_score = -6.0  # Roster surplus penalty
        elif current_pos_count == 0:
            need_score = 7.0   # Urgent starting hole bonus
            if primary_pos == 'G' and g_is_scarce:
                need_score += 2.0
        elif cliff_drop >= 0.65:
            need_score = 4.0
        else:
            need_score = 2.0

        # 3. Specific Tactical Sub-Role Handcuff Check
        teammate_handcuff_name = None
        p_team_upper = str(player_team).upper()
        if team_roster and p_team_upper:
            from fantrax_assistant.suggest import are_teammate_handcuffs
            for r_player in team_roster:
                r_name = r_player.get('player') or r_player.get('name')
                r_pos = str(r_player.get('position', '')).upper()
                if r_name and r_name != player_name and str(r_player.get('team', '')).upper() == p_team_upper:
                    if are_teammate_handcuffs(r_name, p_team_upper, r_pos, player_name, p_team_upper, player_pos):
                        teammate_handcuff_name = r_name
                        break

        handcuff_adj = 8.0 if teammate_handcuff_name else 0.0

        # 4. Positional Opportunity Cost Comparison
        opp_cost_adj = 0.0
        alt_cand_name = ""
        best_pos_fpg = 0.0

        if available_players and current_pos_count < max_pos:
            same_pos_available = [
                cand for cand in available_players
                if (cand.get('player') or cand.get('name')) and (cand.get('player') or cand.get('name')) != player_name
                and (cand.get('position') or '').split(',')[0].strip().upper() == primary_pos
            ]

            realistic_candidates = [
                p for p in same_pos_available
                if float(p.get('adp') or 999.0) <= overall_pick_num + 20
            ]

            if realistic_candidates:
                best_pos_alt = max(
                    realistic_candidates,
                    key=lambda p: self.get_effective_fpg(
                        p.get('player') or p.get('name'),
                        float(p.get('fpg') or 0.0),
                        float(p.get('fpts') or 0.0)
                    )
                )
                alt_cand_name = best_pos_alt.get('player') or best_pos_alt.get('name')
                best_pos_fpg = self.get_effective_fpg(
                    alt_cand_name,
                    float(best_pos_alt.get('fpg') or 0.0),
                    float(best_pos_alt.get('fpts') or 0.0)
                )

                fpg_gap = best_pos_fpg - eff_fpg
                if fpg_gap > 0.4:
                    opp_cost_adj -= min(6.0, fpg_gap * 2.5)

        # 5. Check if pick is a "High-Upside Flier" (high per-game ceiling >= 4.8 FP/G, but unproven/rotational)
        rot_factor = self.calculate_rotation_factor(player_name)
        stats_info = self.config.get_player_stats(player_name) if self.config else {}
        matches_played = int(stats_info.get('matches_played', 38) or 38) if isinstance(stats_info, dict) else 38
        starts_count = int(stats_info.get('starts', 0) or 0) if isinstance(stats_info, dict) else 0
        start_rate = (starts_count / matches_played) if matches_played > 0 else 0.0

        is_established_starter = (matches_played >= 5 and start_rate >= 0.75) or (starts_count >= 15)
        is_flier = (fpg_raw >= 4.8) and not is_established_starter and (rot_factor < 0.94 or matches_played < 28) and (current_pos_count < max_pos)
        flier_adj = 6.0 if is_flier else 0.0

        # Cohesive Sports Analyst Rationale
        sentences = []

        if is_flier:
            pick_type = "Flier"
            sentences.append(
                f"High-upside flier pick for {team_id} at Pick #{overall_pick_num}: {player_name} boasts elite per-match scoring potential ({fpg_raw:.2f} FP/G), taking a calculated gamble on high ceiling despite squad rotation risk at {p_team_upper}."
            )
        elif current_pos_count >= max_pos:
            pick_type = "Surplus"
            sentences.append(f"{team_id} selects {player_name} ({eff_fpg:.2f} FP/G) at Pick #{overall_pick_num}, though carrying {current_pos_count} {primary_pos}s makes this a roster surplus pick.")
        elif teammate_handcuff_name:
            pick_type = "Handcuff"
            sentences.append(f"Strategic rotation handcuff for {team_id} at Pick #{overall_pick_num}: pairing {player_name} with {teammate_handcuff_name} guarantees 100% starting coverage for {p_team_upper}'s {primary_pos} group.")
        elif current_pos_count == 0:
            pick_type = "Need"
            if primary_pos == 'G' and g_is_scarce:
                sentences.append(f"{team_id} plugs a critical starting Goalkeeper slot with {player_name} ({eff_fpg:.2f} FP/G) at Pick #{overall_pick_num} as quality Gs drop to {quality_g_left} remaining.")
            else:
                sentences.append(f"{team_id} fills an urgent starting hole at {primary_pos} with {player_name} ({eff_fpg:.2f} FP/G) at Pick #{overall_pick_num}.")
        elif cliff_drop >= 0.65:
            pick_type = "Cliff Steal"
            sentences.append(f"Crushed the tier cliff timing—{team_id} grabs {player_name} ({eff_fpg:.2f} FP/G) at Pick #{overall_pick_num} right before production tanks at {primary_pos}.")
        else:
            pick_type = "Solid"
            sentences.append(f"{team_id} adds solid custom scoring firepower with {player_name} ({eff_fpg:.2f} FP/G) at Pick #{overall_pick_num}.")

        if not is_flier and current_pos_count < max_pos and alt_cand_name and (best_pos_fpg - eff_fpg > 0.4):
            sentences.append(f"Passing on {alt_cand_name} ({best_pos_fpg:.2f} FP/G) leaves a bit of value on the table, but {team_id} gets their target.")
        elif not is_flier and current_pos_count < max_pos and not teammate_handcuff_name:
            next_count = current_pos_count + 1
            sentences.append(f"Fortifies their core {primary_pos} rotation ({next_count}/{max_pos}) with reliable depth.")

        rationale = " ".join(sentences)

        # Final Score & Letter Grade
        score = max(55.0, min(100.0, prod_base + need_score + handcuff_adj + opp_cost_adj + flier_adj))

        if is_flier:
            grade, grade_class = "Flier", "purple"
        elif score >= 94: grade, grade_class = "A+", "emerald"
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
            "pick_type": pick_type,
            "score": round(score, 1),
            "adp": player_adp,
            "fpg": round(fpg_raw, 2) if fpg_raw else None,
            "fpts": round(fpts, 1) if fpts else None,
            "position": player_pos,
            "team": player_team,
            "rationale": rationale,
            "opp_cost_evaluated": True
        }

    def backfill_retroactive_analysis(self, draft_state, force: bool = False) -> list[dict]:
        """
        Retroactively evaluates all previously drafted players in draft_history/teams
        if they do not already have an evaluation in pick_analysis_history.
        """
        sequence = list(draft_state.draft_history)
        for p in draft_state.drafted_players:
            if p not in sequence:
                sequence.append(p)

        if not force and getattr(draft_state, 'pick_analysis_history', None) and len(draft_state.pick_analysis_history) >= len(sequence):
            return draft_state.pick_analysis_history

        owner_map = {}
        for team_name, roster in draft_state.teams.items():
            for player_obj in roster:
                p_name = player_obj.get('player') or player_obj.get('name')
                if p_name:
                    owner_map[p_name] = team_name

        all_rankings = []
        if self.config and hasattr(self.config, 'rankings') and isinstance(self.config.rankings, dict):
            all_rankings = self.config.rankings.get("rankings", [])

        running_rosters: dict[str, list[dict]] = {t: [] for t in draft_state.teams.keys()}
        running_drafted_set = set()
        new_history = []

        for idx, p_name in enumerate(sequence, start=1):
            owner = owner_map.get(p_name, "Other")
            details = self.config.get_player_adp(p_name) if self.config else None
            p_adp = details.get('adp') if details else None
            p_pos = details.get('position', '') if details else ''
            p_team = details.get('team', '') if details else ''

            available_at_pick = [p for p in all_rankings if (p.get('player') or p.get('name')) not in running_drafted_set]

            current_roster = running_rosters.get(owner, [])
            analysis_item = self.grade_pick(
                player_name=p_name,
                team_id=owner,
                overall_pick_num=idx,
                player_adp=p_adp,
                player_pos=p_pos,
                player_team=p_team,
                team_roster=current_roster,
                available_players=available_at_pick
            )
            new_history.append(analysis_item)

            running_drafted_set.add(p_name)
            if owner in running_rosters:
                running_rosters[owner].append({"player": p_name, "position": p_pos})

        draft_state.pick_analysis_history = new_history
        draft_state.save()
        return new_history

    def calculate_rotation_factor(self, player_name: str, team_code: str = "") -> float:
        """
        Calculates rotation risk factor (0.75 to 1.0) formulaically based on last year's starts and minutes,
        with proportional Big-6 squad rotation adjustments. Contains zero hardcoded player names.
        """
        if not self.config:
            return 1.0

        stats = self.config.get_player_stats(player_name) or {}
        if not isinstance(stats, dict):
            starts = 0
            mins = 0
        else:
            starts = int(stats.get('starts', 0) or 0)
            mins = int(stats.get('minutes', 0) or 0)

        team = str(team_code or (stats.get('team') if isinstance(stats, dict) else '')).upper()
        if not team and self.config:
            details = self.config.get_player_adp(player_name)
            if details:
                team = str(details.get('team', '')).upper()

        is_big_six = team in {'ARS', 'MCI', 'CHE', 'LIV', 'MUN', 'TOT'}

        apps = int(stats.get('matches_played', 0) or 0) if isinstance(stats, dict) else 0
        start_rate = (starts / apps) if apps > 0 else 0.0

        if (apps >= 5 and start_rate >= 0.85) or starts >= 28 or mins >= 2400:
            return 1.0
        elif (apps >= 5 and start_rate >= 0.70) or starts >= 20 or mins >= 1700:
            return 0.95 if not is_big_six else 0.90
        elif starts >= 14 or mins >= 1100:
            return 0.88 if not is_big_six else 0.83
        else:
            return 0.80 if not is_big_six else 0.75

    def get_effective_fpg(self, player_name: str, raw_fpg: float | None = None, raw_fpts: float | None = None) -> float:
        """
        Calculates effective FP/G using actual Fantrax league projected points (adp_rankings.json)
        adjusted for sample sizes, rotation risk, and injury availability.
        """
        cache_key = (player_name, raw_fpg, raw_fpts)
        if cache_key in self._eff_fpg_cache:
            return self._eff_fpg_cache[cache_key]

        fpg_val = 0.0
        matches = None
        inj_severity = "Healthy"

        if self.config:
            details = self.config.get_player_adp(player_name)
            if details:
                fpg_val = float(details.get('fpg', 0.0) or 0.0)

            stats = self.config.get_player_stats(player_name)
            if stats and isinstance(stats, dict) and 'matches_played' in stats:
                matches = int(stats.get('matches_played', 0) or 0)

            inj = self.config.get_player_injury(player_name)
            if inj:
                inj_severity = inj.get("severity", "Healthy")

        if fpg_val == 0.0:
            fpg_val = raw_fpg or 2.25

        # Long-term / Season-ending injuries heavily discount available FP/G
        if "Long Term" in inj_severity or "Out" in inj_severity:
            res = min(fpg_val, 1.5)
        elif "Medium Term" in inj_severity:
            res = fpg_val * 0.75
        elif "Short Term" in inj_severity:
            res = fpg_val * 0.90
        else:
            res = fpg_val

        # Healthy scratch / starting availability adjustment for non-injured rotated players
        if inj_severity == "Healthy":
            stats = self.config.get_player_stats(player_name) if self.config else {}
            mins = int(stats.get('minutes', 0) or 0) if isinstance(stats, dict) else 0
            starts = int(stats.get('starts', 0) or 0) if isinstance(stats, dict) else 0
            apps = int(stats.get('matches_played', 0) or 0) if isinstance(stats, dict) else 0
            start_rate = (starts / apps) if apps > 0 else 0.0

            if (apps >= 5 and start_rate >= 0.85) or mins >= 2200 or starts >= 26:
                start_availability = 1.0
            elif (apps >= 5 and start_rate >= 0.70) or mins >= 1700 or starts >= 18:
                start_availability = 0.95
            elif mins >= 1200 or starts >= 14:
                start_availability = 0.88
            elif apps > 0:
                start_availability = min(1.0, max(0.60, start_rate))
            else:
                start_availability = 1.0
            res *= start_availability

        # Sample size regression for unproven / low sample players (< 10 matches)
        if matches is not None and matches > 0 and matches < 10:
            res = ((res * matches) + (2.25 * 6.0)) / (matches + 6.0)

        # Apply rotation risk adjustment
        rot_factor = self.calculate_rotation_factor(player_name)
        res *= rot_factor

        # Apply set-piece & penalty taker valuation boost
        if self.config:
            sp_status = self.config.get_player_set_piece_status(player_name)
            if sp_status.get('is_pk_taker'):
                res += 0.45
            if sp_status.get('is_set_piece_taker'):
                res += 0.25

        final_val = max(0.0, res)
        self._eff_fpg_cache[cache_key] = final_val
        return final_val

    def generate_sportswriter_narrative(
        self,
        team_id: str,
        grade: str,
        composite_score: float,
        player_evals: list[dict],
        top_avg_fpg: float,
        best_steal: dict | None,
        biggest_reach: dict | None,
        missing_positions: list[str],
        surplus_positions: list[str],
        injured_players: list[str],
        afcon_players: list[str]
    ) -> dict[str, str | list[str]]:
        """
        Generates a vivid, sportswriter-style draft analysis writeup with unique,
        team-tailored executive summaries, headlines, strengths, vulnerabilities, and analyst verdicts.
        """
        # Sort players by Marquee Anchor Score: Effective FP/G (league scoring) + 9-Team Draft Capital Weight
        def get_anchor_score(p):
            eff = p.get('eff_fpg', p.get('adj_fpg', 0.0))
            pick_num = p.get('pick_number', 999)
            # In a 9-team league, calculate draft round investment weight (Round 1 = picks 1-9)
            draft_weight = max(0.0, (108 - pick_num) / 108.0) * 3.5 if pick_num <= 108 else 0.0
            return (eff * 0.65) + draft_weight

        star_players = sorted(player_evals, key=get_anchor_score, reverse=True)
        top_scorer = star_players[0] if star_players else None
        second_scorer = star_players[1] if len(star_players) > 1 else None
        third_scorer = star_players[2] if len(star_players) > 2 else None

        high_rot_players = [p['name'] for p in player_evals if p.get('rot_risk', 1.0) < 0.85]

        # 1. Team-Specific Headlines & Hooks
        if team_id.lower() == 'sam':
            headline = f"Grade {grade} ({composite_score:.1f}/100) — Sam's Midfield Engine & Title Aspirations"
            summary_hook = (
                f"Sam orchestrated a high-tempo draft, assembling a dynamic starting XI powered by "
                f"{top_scorer['name']} ({top_scorer['eff_fpg']:.2f} FP/G) and {second_scorer['name']} ({second_scorer['eff_fpg']:.2f} FP/G)."
                if top_scorer and second_scorer else f"Sam constructed a solid foundational starting XI."
            )
            tactical_note = (
                f" With an impressive starting core averaging {top_avg_fpg:.2f} effective FP/G, Sam's lineup features exceptional tactical fluidity across midfield and defense."
            )
            verdict = (
                f"Sam enters the campaign as a front-runner for the league title, boasting one of the highest starter scoring floors in the competition."
                if composite_score >= 88 else f"Sam maintains a strong playoff profile, requiring minor free-agent tweaks."
            )

        elif team_id.lower() == 'hayden':
            headline = f"Grade {grade} ({composite_score:.1f}/100) — Hayden's Elite Backbone & Championship Blueprint"
            summary_hook = (
                f"Hayden assembled a formidable starting XI anchored by elite Premier League star power in "
                f"{top_scorer['name']} ({top_scorer['eff_fpg']:.2f} FP/G) and {second_scorer['name']} ({second_scorer['eff_fpg']:.2f} FP/G)."
                if top_scorer and second_scorer else f"Hayden built an impressive starting core."
            )
            tactical_note = (
                f" High-powered starting production ({top_avg_fpg:.2f} avg FP/G) provides Hayden with explosive week-to-week scoring potential."
            )
            verdict = (
                f"Hayden's roster projects as a championship contender, featuring top-tier starter consistency across every pitch line."
                if composite_score >= 88 else f"Hayden is firmly in contention for top-table honors."
            )

        elif team_id.lower() == 'scott':
            headline = f"Grade {grade} ({composite_score:.1f}/100) — Scott's High-Ceiling Attack & Roster Outlook"
            summary_hook = (
                f"Scott targeted high-ceiling attacking talent, headlining the squad with "
                f"{top_scorer['name']} ({top_scorer['eff_fpg']:.2f} FP/G) and {second_scorer['name']} ({second_scorer['eff_fpg']:.2f} FP/G)."
                if top_scorer and second_scorer else f"Scott constructed a high-ceiling attacking unit."
            )
            tactical_note = (
                f" The top starters deliver an average of {top_avg_fpg:.2f} FP/G, though roster depth management will dictate overall consistency."
            )
            verdict = (
                f"Scott has the raw firepower to mount a deep playoff run, provided targeted waiver-wire additions bolster secondary line depth."
            )

        else:
            headline = f"Grade {grade} ({composite_score:.1f}/100) — {team_id}'s Draft Breakdown"
            summary_hook = (
                f"{team_id} exits the draft with a starting XI led by {top_scorer['name']} ({top_scorer['eff_fpg']:.2f} FP/G)."
                if top_scorer else f"{team_id} completed draft roster construction."
            )
            tactical_note = f" Starters average {top_avg_fpg:.2f} FP/G."
            verdict = f"{team_id} will compete for playoff spots through active manager moves."

        if missing_positions:
            void_note = f" Active waiver additions will be needed to cover position gaps at [{', '.join(missing_positions)}]."
        else:
            void_note = " Starting position coverage is fully secured across core lines."

        exec_summary = f"{summary_hook}{tactical_note}{void_note}"

        # 2. Dynamic Sportswriter Strengths & Vulnerabilities
        strengths = []
        vulnerabilities = []

        def get_flier_tag(p):
            if not p: return ""
            raw = float(p.get('fpg', 0.0) or 0.0)
            rot = float(p.get('rot_risk', 1.0) or 1.0)
            starts = int(p.get('starts', 0) or 0)
            mins = int(p.get('minutes', 0) or 0)
            if raw >= 4.8 and (rot < 0.94 or starts < 28 or mins < 2200):
                return " [High-Upside Flier]"
            return ""

        if top_scorer:
            strengths.append(f"Marquee Anchor: {top_scorer['name']} ({top_scorer['eff_fpg']:.2f} FP/G){get_flier_tag(top_scorer)} delivers top-tier fantasy output.")
        if second_scorer:
            strengths.append(f"Secondary Catalyst: {second_scorer['name']} ({second_scorer['eff_fpg']:.2f} FP/G){get_flier_tag(second_scorer)} bolsters starting depth.")
        if third_scorer:
            strengths.append(f"Starter Depth: {third_scorer['name']} ({third_scorer['eff_fpg']:.2f} FP/G){get_flier_tag(third_scorer)} rounds out a high-volume scoring core.")
        if best_steal and best_steal.get('score', 0) >= 88:
            strengths.append(f"Draft Steal: Capitalized on board value to draft {best_steal['player']} at Pick #{best_steal['pick_number']} (Grade {best_steal['grade']}).")

        if missing_positions:
            vulnerabilities.append(f"Roster Depth Void: Unfilled starting depth at [{', '.join(missing_positions)}].")
        if injured_players:
            vulnerabilities.append(f"Health Recovery Watch: Managing availability for {', '.join(injured_players[:2])}.")
        if high_rot_players:
            vulnerabilities.append(f"Squad Rotation Competition: Lineup uncertainty surrounding {', '.join(high_rot_players[:2])}.")
        if afcon_players:
            vulnerabilities.append(f"International Absence: Missing {', '.join(afcon_players)} during winter international play.")

        if not strengths:
            strengths.append("Balanced starter coverage across core positions.")
        if not vulnerabilities:
            vulnerabilities.append("Clean squad health profile with no major roster voids.")

        return {
            "headline": headline,
            "executive_summary": exec_summary,
            "strengths": strengths,
            "vulnerabilities": vulnerabilities,
            "verdict": verdict
        }

    def evaluate_team_grade(self, team_id: str, draft_state) -> dict:
        """
        Calculates full team composite grade, 4 component sub-scores (0-100),
        standout picks (top scorer, best steal, reach), and a multi-paragraph
        sports-analyst writeup for a draft team.
        """
        roster = draft_state.teams.get(team_id, [])
        pick_history = self.backfill_retroactive_analysis(draft_state)
        team_picks = [p for p in pick_history if p.get('team_id') == team_id]

        # Enrich roster players with full config stats, adp, and injury info
        player_evals = []
        for p in roster:
            p_name = p.get('player') or p.get('name')
            adp_info = self.config.get_player_adp(p_name) if self.config else {}
            stats_info = self.config.get_player_stats(p_name) if self.config else {}
            inj_info = self.config.get_player_injury(p_name) if self.config else {}

            full_p = {
                **p,
                **(adp_info or {}),
                'stats': stats_info or {},
                'injury': inj_info or {}
            }

            raw_fpg = float(full_p.get('fpg') or 0.0)
            raw_fpts = float(full_p.get('fpts') or 0.0)
            eff_fpg = self.get_effective_fpg(p_name, raw_fpg, raw_fpts)
            rot_risk = self.calculate_rotation_factor(p_name, full_p.get('team', ''))

            # Check if roster carries competing teammates sharing exact pitch sub-role (e.g. Hincapie & Calafiori at ARS LB)
            from fantrax_assistant.suggest import are_teammate_handcuffs
            p_team_upper = str(full_p.get('team', '')).upper()
            p_pos_str = str(full_p.get('position', '')).upper()
            for r_p in roster:
                r_name = r_p.get('player') or r_p.get('name')
                if r_name and r_name != p_name and str(r_p.get('team', '')).upper() == p_team_upper:
                    r_pos_str = str(r_p.get('position', '')).upper()
                    if are_teammate_handcuffs(p_name, p_team_upper, p_pos_str, r_name, p_team_upper, r_pos_str):
                        rot_risk *= 0.85
                        break

            adj_fpg = eff_fpg * rot_risk

            pick_num = p.get('pick_number')
            if not pick_num:
                history_list = list(draft_state.draft_history) if hasattr(draft_state, 'draft_history') else []
                if history_list and p_name in history_list:
                    pick_num = history_list.index(p_name) + 1
            if not pick_num:
                pick_num = 999

            player_evals.append({
                'name': p_name,
                'position': full_p.get('position', 'M'),
                'team': full_p.get('team', ''),
                'fpg': raw_fpg,
                'eff_fpg': round(eff_fpg, 2),
                'adj_fpg': round(adj_fpg, 2),
                'rot_risk': round(rot_risk, 2),
                'pick_number': pick_num,
                'starts': stats_info.get('starts', 0) if isinstance(stats_info, dict) else 0,
                'minutes': stats_info.get('minutes', 0) if isinstance(stats_info, dict) else 0,
                'fpts': raw_fpts
            })

        player_evals.sort(key=lambda x: x['adj_fpg'], reverse=True)
        top_starters = player_evals[:6]

        if top_starters:
            top_avg_fpg = sum(p['adj_fpg'] for p in top_starters) / len(top_starters)
            star_power_score = max(50.0, min(100.0, 50.0 + (top_avg_fpg / 5.5) * 48.0))
        else:
            top_avg_fpg = 0.0
            star_power_score = 50.0

        # 2. Draft Value & Pick Efficiency (10% weight - ADP influence minimized)
        if team_picks:
            avg_pick_score = sum(p.get('score', 75.0) for p in team_picks) / len(team_picks)
            pick_eff_score = max(50.0, min(100.0, avg_pick_score))
        else:
            avg_pick_score = 75.0
            pick_eff_score = 75.0

        # 3. Roster Balance & Position Coverage (30% weight - accounting for dual position eligibility like M,F)
        roster_rules = {"G": 1, "D": 5, "M": 5, "F": 4}
        assigned_counts = {p: 0 for p in roster_rules}
        unassigned_players = []

        # Assign fixed single-position players first
        for p in roster:
            pos_list = [x.strip().upper() for x in (p.get('position') or '').split(',') if x.strip()]
            valid = [x for x in pos_list if x in roster_rules]
            if not valid:
                valid = ['M']
            if len(valid) == 1:
                assigned_counts[valid[0]] += 1
            else:
                unassigned_players.append(valid)

        # Assign multi-position flex players to position with highest unfilled quota need
        for valid_options in unassigned_players:
            best_pos = max(valid_options, key=lambda p: (roster_rules[p] - assigned_counts[p]))
            assigned_counts[best_pos] += 1

        balance_base = 95.0
        missing_positions = []
        surplus_positions = []

        for pos, max_req in roster_rules.items():
            cnt = assigned_counts[pos]
            if cnt == 0:
                missing_positions.append(pos)
                penalty = 12.0 if pos == 'G' else 7.0
                balance_base -= penalty
            elif cnt > max_req:
                surplus_positions.append(pos)
                balance_base -= (cnt - max_req) * 3.0

        roster_balance_score = max(40.0, min(100.0, balance_base))

        # 4. Squad Availability & Risk Factor (15% weight)
        avail_base = 100.0
        injured_players = []
        afcon_players = []

        for p in roster:
            p_name = p.get('player') or p.get('name')
            if self.config:
                inj = self.config.get_player_injury(p_name)
                if inj:
                    sev = inj.get('severity', 'Healthy')
                    if "Long Term" in sev or "Out" in sev:
                        avail_base -= 8.0
                        injured_players.append(f"{p_name} ({sev})")
                    elif "Medium Term" in sev:
                        avail_base -= 4.0
                        injured_players.append(f"{p_name} ({sev})")
                    elif "Short Term" in sev:
                        avail_base -= 2.0

                afcon = self.config.get_player_afcon_status(p_name)
                if afcon and afcon.get('at_afcon'):
                    avail_base -= 5.0
                    afcon_players.append(p_name)

        availability_score = max(50.0, min(100.0, avail_base))

        # Composite Score Calculation (Minimizing ADP weight: Star Power 45%, Roster Fit 30%, Availability 15%, Pick Value 10%)
        composite_score = (
            (star_power_score * 0.45) +
            (roster_balance_score * 0.30) +
            (availability_score * 0.15) +
            (pick_eff_score * 0.10)
        )

        if composite_score >= 94.0: grade, grade_class = "A+", "emerald"
        elif composite_score >= 89.0: grade, grade_class = "A", "emerald"
        elif composite_score >= 85.0: grade, grade_class = "A-", "emerald"
        elif composite_score >= 81.0: grade, grade_class = "B+", "blue"
        elif composite_score >= 77.0: grade, grade_class = "B", "blue"
        elif composite_score >= 73.0: grade, grade_class = "B-", "blue"
        elif composite_score >= 68.0: grade, grade_class = "C+", "amber"
        elif composite_score >= 63.0: grade, grade_class = "C", "amber"
        elif composite_score >= 58.0: grade, grade_class = "C-", "amber"
        elif composite_score >= 52.0: grade, grade_class = "D", "red"
        else: grade, grade_class = "F", "red"

        # Standout Picks
        top_scorer = player_evals[0] if player_evals else None
        best_steal = max(team_picks, key=lambda x: x.get('score', 0)) if team_picks else None
        biggest_reach = min(team_picks, key=lambda x: x.get('score', 100)) if team_picks else None

        writeup = self.generate_sportswriter_narrative(
            team_id=team_id,
            grade=grade,
            composite_score=composite_score,
            player_evals=player_evals,
            top_avg_fpg=top_avg_fpg,
            best_steal=best_steal,
            biggest_reach=biggest_reach,
            missing_positions=missing_positions,
            surplus_positions=surplus_positions,
            injured_players=injured_players,
            afcon_players=afcon_players
        )

        return {
            "team_id": team_id,
            "grade": grade,
            "grade_class": grade_class,
            "score": round(composite_score, 1),
            "rank": 1,
            "components": {
                "star_power": round(star_power_score, 1),
                "pick_efficiency": round(pick_eff_score, 1),
                "roster_balance": round(roster_balance_score, 1),
                "availability": round(availability_score, 1)
            },
            "top_starter_avg_fpg": round(top_avg_fpg, 2),
            "total_players": len(roster),
            "top_scorer": top_scorer,
            "best_steal": best_steal,
            "biggest_reach": biggest_reach,
            "writeup": writeup
        }

    def evaluate_all_tracked_teams(self, draft_state) -> dict[str, dict]:
        """
        Evaluates full team grades and writeups for all tracked user teams in draft_state,
        ignoring 'Other' (which is just a lump category for untracked league picks).
        """
        all_teams = draft_state.teams.keys()
        tracked_teams = [t for t in all_teams if t.lower() != 'other']
        if not tracked_teams and all_teams:
            tracked_teams = list(all_teams)

        results = {}
        for team_id in tracked_teams:
            results[team_id] = self.evaluate_team_grade(team_id, draft_state)

        # Rank tracked teams by composite score
        sorted_teams = sorted(results.values(), key=lambda x: x["score"], reverse=True)
        for rank_idx, team_eval in enumerate(sorted_teams, start=1):
            results[team_eval["team_id"]]["rank"] = rank_idx

        return results
