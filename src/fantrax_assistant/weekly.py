"""Weekly Team Manager & Auto-Sub Recommendation Engine."""

from datetime import datetime
from typing import Dict, List, Any, Optional
from .config import DraftConfig

# Standard Fantrax Roster Formation Constraints (New Draft City Rules)
POSITION_LIMITS = {
    'G': {'min': 1, 'max': 1},
    'D': {'min': 3, 'max': 5},
    'M': {'min': 3, 'max': 5},
    'F': {'min': 1, 'max': 4},
    'TOTAL_STARTERS': 11
}

# Premier League Team Match Schedule Mock / Live Fixture Map
# Format: team_code -> {'opponent': 'ARS', 'is_home': True, 'fdr': 2, 'kickoff_time': '2026-08-16T15:00:00Z', 'display_time': 'Sun Aug 16, 3:00 PM'}
DEFAULT_FIXTURE_SCHEDULE = {
    'ARS': {'opponent': 'WOL', 'is_home': True, 'fdr': 2, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun Aug 16, 3:00 PM'},
    'AVL': {'opponent': 'WHU', 'is_home': False, 'fdr': 3, 'kickoff_time': '2026-08-16T16:30:00Z', 'display_time': 'Sun Aug 16, 5:30 PM'},
    'BOU': {'opponent': 'NFO', 'is_home': False, 'fdr': 2, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun Aug 16, 3:00 PM'},
    'BRE': {'opponent': 'CRY', 'is_home': True, 'fdr': 3, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun Aug 16, 3:00 PM'},
    'BHA': {'opponent': 'EVE', 'is_home': False, 'fdr': 2, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun Aug 16, 3:00 PM'},
    'CHE': {'opponent': 'MCI', 'is_home': True, 'fdr': 4, 'kickoff_time': '2026-08-16T16:30:00Z', 'display_time': 'Sun Aug 16, 5:30 PM'},
    'CRY': {'opponent': 'BRE', 'is_home': False, 'fdr': 3, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun Aug 16, 3:00 PM'},
    'EVE': {'opponent': 'BHA', 'is_home': True, 'fdr': 3, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun Aug 16, 3:00 PM'},
    'FUL': {'opponent': 'MUN', 'is_home': False, 'fdr': 4, 'kickoff_time': '2026-08-15T19:00:00Z', 'display_time': 'Sat Aug 15, 8:00 PM'},
    'IPS': {'opponent': 'LIV', 'is_home': True, 'fdr': 5, 'kickoff_time': '2026-08-16T11:30:00Z', 'display_time': 'Sun Aug 16, 12:30 PM'},
    'LEI': {'opponent': 'TOT', 'is_home': True, 'fdr': 4, 'kickoff_time': '2026-08-17T19:00:00Z', 'display_time': 'Mon Aug 17, 8:00 PM'},
    'LIV': {'opponent': 'IPS', 'is_home': False, 'fdr': 2, 'kickoff_time': '2026-08-16T11:30:00Z', 'display_time': 'Sun Aug 16, 12:30 PM'},
    'MCI': {'opponent': 'CHE', 'is_home': False, 'fdr': 3, 'kickoff_time': '2026-08-16T16:30:00Z', 'display_time': 'Sun Aug 16, 5:30 PM'},
    'MUN': {'opponent': 'FUL', 'is_home': True, 'fdr': 2, 'kickoff_time': '2026-08-15T19:00:00Z', 'display_time': 'Sat Aug 15, 8:00 PM'},
    'NEW': {'opponent': 'SOU', 'is_home': True, 'fdr': 2, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun Aug 16, 3:00 PM'},
    'NFO': {'opponent': 'BOU', 'is_home': True, 'fdr': 3, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun Aug 16, 3:00 PM'},
    'SOU': {'opponent': 'NEW', 'is_home': False, 'fdr': 4, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun Aug 16, 3:00 PM'},
    'TOT': {'opponent': 'LEI', 'is_home': False, 'fdr': 2, 'kickoff_time': '2026-08-17T19:00:00Z', 'display_time': 'Mon Aug 17, 8:00 PM'},
    'WHU': {'opponent': 'AVL', 'is_home': True, 'fdr': 3, 'kickoff_time': '2026-08-16T16:30:00Z', 'display_time': 'Sun Aug 16, 5:30 PM'},
    'WOL': {'opponent': 'ARS', 'is_home': False, 'fdr': 5, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun Aug 16, 3:00 PM'},
}


from pathlib import Path

class WeeklyManagerEngine:
    """Calculates weekly ideal starting XI and Fantrax auto-sub recommendations."""

    def __init__(self, fixture_schedule: Optional[Dict[str, Dict[str, Any]]] = None, config: Optional[DraftConfig] = None):
        self.config = config
        if fixture_schedule:
            self.fixtures = fixture_schedule
        else:
            fix_file = Path(__file__).resolve().parent.parent.parent / "data" / "fixtures.json"
            if fix_file.exists():
                try:
                    with open(fix_file) as f:
                        self.fixtures = json.load(f)
                except Exception:
                    self.fixtures = DEFAULT_FIXTURE_SCHEDULE
            else:
                self.fixtures = DEFAULT_FIXTURE_SCHEDULE

    def _get_primary_position(self, pos_str: str) -> str:
        """Extract primary position code (G, D, M, F)."""
        if not pos_str:
            return 'M'
        positions = [p.strip() for p in pos_str.split(',')]
        for p in ['G', 'D', 'M', 'F']:
            if p in positions:
                return p
        return 'M'

    def calculate_projected_points(self, player: Dict[str, Any]) -> float:
        """Calculate projected weekly fantasy points based on form, fixture difficulty, home advantage, and starting probability."""
        p_name = player.get('player') or player.get('name', '')
        fpg = float(player.get('fpg', 0) or 0)

        if self.config:
            adp_info = self.config.get_player_adp(p_name)
            if adp_info and adp_info.get('fpg'):
                fpg = float(adp_info['fpg'])

        team_code = player.get('team', '')
        fixture = self.fixtures.get(team_code, {})

        fdr = fixture.get('fdr', 3)
        is_home = fixture.get('is_home', False)

        # FDR multiplier: FDR 1 (1.15), FDR 2 (1.08), FDR 3 (1.00), FDR 4 (0.90), FDR 5 (0.80)
        fdr_multiplier = {1: 1.15, 2: 1.08, 3: 1.00, 4: 0.90, 5: 0.80}.get(fdr, 1.0)
        home_boost = 1.05 if is_home else 0.97

        # Starting Probability & Rotation Risk Factor
        rotation_penalty = 1.0
        p_name_upper = str(p_name).upper().strip()
        NON_NAILED_ROTATION_PLAYERS = {'NONI MADUEKE', 'ARCHIE GRAY'}
        if p_name_upper in NON_NAILED_ROTATION_PLAYERS:
            rotation_penalty = 0.65
        elif team_code in {'MCI', 'ARS', 'CHE', 'LIV', 'TOT', 'BOU', 'MUN'}:
            if fpg < 3.8:
                rotation_penalty = 0.88

        # Medical / Injury Discount Factor based on realistic playing probability
        injury_factor = 1.0
        if self.config:
            inj = self.config.get_player_injury(p_name)
            if inj:
                sev = inj.get('severity', 'Healthy')
                inj_type = str(inj.get('injury_type', '')).lower()
                if '75%' in inj_type or 'knock' in inj_type:
                    injury_factor = 0.90
                elif '50%' in inj_type or sev == 'Short Term':
                    injury_factor = 0.50
                elif '25%' in inj_type or 'doubtful' in inj_type or sev == 'Medium Term':
                    injury_factor = 0.25
                elif sev in {'Long Term', 'Out', 'Suspended'} or 'out' in inj_type:
                    injury_factor = 0.0

        proj = fpg * fdr_multiplier * home_boost * rotation_penalty * injury_factor
        return round(proj, 2)

    def get_optimal_lineup(self, roster: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Formulate optimal starting 11 across all 7 valid Fantrax formations
        (3-5-2, 3-4-3, 4-5-1, 4-4-2, 4-3-3, 5-3-2, 5-4-1) utilizing multi-position flex eligibility
        (e.g. M,F or D,M) to maximize total starting XI projected points.
        """
        if not roster:
            return {
                'starters': [],
                'bench': [],
                'formation': '0-0-0',
                'total_projected_fpts': 0.0
            }

        # Enrich roster with projected points & eligible positions
        enriched = []
        for p in roster:
            p_copy = dict(p)
            p_name = p_copy.get('player') or p_copy.get('name', '')
            inj = self.config.get_player_injury(p_name) if self.config else {}
            afcon = self.config.get_player_afcon_status(p_name) if self.config else {}
            p_copy['injury_severity'] = inj.get('severity', 'Healthy')
            p_copy['injury_type'] = inj.get('injury_type', '')
            p_copy['injury_notes'] = inj.get('injury_type') or inj.get('notes', '')
            p_copy['at_afcon'] = afcon.get('at_afcon', False)

            p_copy['primary_pos'] = self._get_primary_position(p_copy.get('position', ''))
            p_copy['eligible_positions'] = [x.strip().upper() for x in (p_copy.get('position') or '').split(',') if x.strip()]
            if not p_copy['eligible_positions']:
                p_copy['eligible_positions'] = ['M']

            p_copy['proj_fpts'] = self.calculate_projected_points(p_copy)
            team_code = p_copy.get('team', '')
            p_copy['fixture'] = p.get('fixture') or self.fixtures.get(team_code, {
                'opponent': 'TBD',
                'is_home': True,
                'fdr': 3,
                'kickoff_time': '2026-08-16T15:00:00Z',
                'display_time': 'Sun Aug 16, 3:00 PM'
            })
            enriched.append(p_copy)

        # 1. Pick 1 Goalkeeper with highest projected points
        g_candidates = [p for p in enriched if 'G' in p['eligible_positions']]
        best_g = max(g_candidates, key=lambda x: x['proj_fpts']) if g_candidates else None

        outfield = [p for p in enriched if p != best_g and 'G' not in p['eligible_positions']]
        outfield.sort(key=lambda x: x['proj_fpts'], reverse=True)

        # 2. Test all valid Fantrax formations using exact combinatorial matching to maximize total projected points
        valid_formations = [(3, 5, 2), (4, 5, 1), (3, 4, 3), (4, 4, 2), (5, 4, 1), (4, 3, 3), (5, 3, 2), (3, 3, 4)]

        def can_fill_formation(cand_players, needed):
            slots = []
            for pos in ['D', 'M', 'F']:
                slots.extend([pos] * needed[pos])

            def backtrack(idx, used_slots, assign):
                if idx == len(cand_players):
                    return assign
                p = cand_players[idx]
                for s_idx, s_pos in enumerate(slots):
                    if s_idx not in used_slots and s_pos in p['eligible_positions']:
                        used_slots.add(s_idx)
                        assign[p['player']] = s_pos
                        res = backtrack(idx + 1, used_slots, assign)
                        if res is not None:
                            return res
                        used_slots.remove(s_idx)
                        if p['player'] in assign:
                            del assign[p['player']]
                return None

            return backtrack(0, set(), {})

        import itertools
        from fantrax_assistant.suggest import are_teammate_handcuffs

        def has_handcuff_conflict(combo):
            for p1, p2 in itertools.combinations(combo, 2):
                n1, t1, pos1 = p1.get('player') or p1.get('name'), p1.get('team', ''), p1.get('position', '')
                n2, t2, pos2 = p2.get('player') or p2.get('name'), p2.get('team', ''), p2.get('position', '')
                if are_teammate_handcuffs(n1, t1, pos1, n2, t2, pos2):
                    return True
            return False

        best_starters = []
        best_formation_str = "3-5-2"
        best_total_proj = -1.0

        # Evaluate combinations of size 10 from outfield (enforcing teammate handcuff separation)
        combo_size = min(10, len(outfield))
        for cand_combo in itertools.combinations(outfield, combo_size):
            if has_handcuff_conflict(cand_combo):
                continue
            base_score = sum(p['proj_fpts'] for p in cand_combo) + (best_g['proj_fpts'] if best_g else 0.0)
            if base_score <= best_total_proj:
                continue
            for (d, m, f) in valid_formations:
                needed = {'D': d, 'M': m, 'F': f}
                assignment = can_fill_formation(cand_combo, needed)
                if assignment:
                    best_total_proj = base_score
                    best_formation_str = f"{d}-{m}-{f}"
                    best_starters = []
                    if best_g:
                        g_c = dict(best_g)
                        g_c['assigned_pos'] = 'G'
                        best_starters.append(g_c)
                    for p in cand_combo:
                        p_c = dict(p)
                        p_c['assigned_pos'] = assignment[p['player']]
                        best_starters.append(p_c)
                    break

        # Fallback if no valid assignment found
        if not best_starters:
            best_starters = enriched[:11]
            best_total_proj = sum(p['proj_fpts'] for p in best_starters)
            best_formation_str = "4-4-2"

        # Separate starters & bench
        starter_names = {p['player'] for p in best_starters}
        bench = [p for p in enriched if p['player'] not in starter_names]

        # Sort starters strictly by assigned position slot: G -> D -> M -> F
        pos_order = {'G': 0, 'D': 1, 'M': 2, 'F': 3}
        best_starters.sort(
            key=lambda x: (
                pos_order.get(str(x.get('assigned_pos', 'M'))[0].upper(), 4),
                -x.get('proj_fpts', 0.0)
            )
        )
        bench.sort(key=lambda x: -x['proj_fpts'])

        return {
            'starters': best_starters,
            'bench': bench,
            'formation': best_formation_str,
            'total_projected_fpts': round(best_total_proj, 1)
        }

    def assign_and_sort_starters(self, starters: List[Dict[str, Any]], slot_overrides: Optional[Dict[str, str]] = None) -> str:
        """
        Assigns each starting player a unique legal position slot (1 G, 3-5 D, 3-5 M, 1-4 F)
        resolving dual-eligibility (e.g. M,F) to ensure valid formation rules, then sorts
        strictly by position order (G -> D -> M -> F) and descending projected FPts.
        Returns the formation string (e.g. '3-5-2').
        """
        slot_overrides = slot_overrides or {}
        # Prioritize standard fantasy formations (3-5-2, 4-4-2, 4-3-3, 3-4-3, etc.)
        valid_formations = [(3, 5, 2), (4, 4, 2), (4, 3, 3), (3, 4, 3), (4, 5, 1), (5, 3, 2), (5, 4, 1), (3, 3, 4)]

        # Specific preferences for dual-eligible starters
        player_prefs = {
            'Mathys Tel': 'F',
            'Jean-Philippe Mateta': 'F',
            'Eberechi Eze': 'M',
            'Rayan': 'M',
            'Matheus Nunes': 'D'
        }
        player_prefs.update(slot_overrides)

        for p in starters:
            pos_raw = p.get('position', '')
            elig = [x.strip().upper() for x in pos_raw.split(',') if x.strip().upper() in ['G', 'D', 'M', 'F']]
            if not elig:
                elig = ['M']
            p['eligible_positions'] = elig

        g_player = next((p for p in starters if 'G' in p.get('eligible_positions', [])), None)
        outfield = [p for p in starters if p != g_player]
        if g_player:
            g_player['assigned_pos'] = 'G'

        for (target_d, target_m, target_f) in valid_formations:
            counts = {'D': 0, 'M': 0, 'F': 0}
            limits = {'D': target_d, 'M': target_m, 'F': target_f}
            assignment = {}
            players_sorted = sorted(outfield, key=lambda p_item: (len(p_item.get('eligible_positions', [])), -float(p_item.get('proj_fpts', 0.0) or 0.0)))

            def backtrack(idx: int) -> bool:
                if idx == len(players_sorted):
                    return True
                p_item = players_sorted[idx]
                elig_list = list(p_item.get('eligible_positions', ['M']))
                pref = player_prefs.get(p_item.get('player') or p_item.get('name', ''))
                if pref and pref in elig_list:
                    elig_list.remove(pref)
                    elig_list.insert(0, pref)

                for pos in elig_list:
                    if counts[pos] < limits[pos]:
                        counts[pos] += 1
                        assignment[p_item.get('player')] = pos
                        if backtrack(idx + 1):
                            return True
                        counts[pos] -= 1
                        if p_item.get('player') in assignment:
                            del assignment[p_item.get('player')]
                return False

            if backtrack(0) and len(assignment) == len(outfield):
                for p_item in outfield:
                    p_item['assigned_pos'] = assignment.get(p_item.get('player'), p_item.get('primary_pos', 'M'))
                break

        for p in starters:
            if 'assigned_pos' not in p or not p['assigned_pos']:
                p['assigned_pos'] = p.get('primary_pos') or p.get('position', 'M').split(',')[0]

        # Sort strictly: G -> D -> M -> F, then descending projected points
        pos_order = {'G': 0, 'D': 1, 'M': 2, 'F': 3}
        starters.sort(
            key=lambda x: (
                pos_order.get(str(x.get('assigned_pos', 'M'))[0].upper(), 4),
                -float(x.get('proj_fpts', 0.0) or 0.0)
            )
        )

        d_count = sum(1 for p in starters if p.get('assigned_pos') == 'D')
        m_count = sum(1 for p in starters if p.get('assigned_pos') == 'M')
        f_count = sum(1 for p in starters if p.get('assigned_pos') == 'F')
        return f'{d_count}-{m_count}-{f_count}'

    def is_legal_roster_sub(self, current_starters: List[Dict[str, Any]], starter_to_remove: Dict[str, Any], sub_to_add: Dict[str, Any]) -> bool:
        """
        Verifies that replacing starter_to_remove with sub_to_add leaves a legal Fantrax roster formation
        (1 G, 3-5 D, 3-5 M, 1-4 F, total 11 starters).
        """
        proposed_11 = [p for p in current_starters if p['player'] != starter_to_remove['player']] + [sub_to_add]
        if len(proposed_11) != 11:
            return False

        # Goalkeeper constraint: must have exactly 1 G
        g_count = sum(1 for p in proposed_11 if 'G' in p.get('eligible_positions', []) or p.get('assigned_pos') == 'G')
        if g_count != 1:
            return False

        outfield = [p for p in proposed_11 if 'G' not in p.get('eligible_positions', []) and p.get('assigned_pos') != 'G']
        if len(outfield) != 10:
            return False

        valid_formations = [(3, 3, 4), (3, 4, 3), (3, 5, 2), (4, 3, 3), (4, 4, 2), (4, 5, 1), (5, 3, 2), (5, 4, 1)]

        for (target_d, target_m, target_f) in valid_formations:
            needed = {"D": target_d, "M": target_m, "F": target_f}
            current_counts = {"D": 0, "M": 0, "F": 0}
            assigned_count = 0

            remaining = []
            for p in outfield:
                elig = [x for x in p.get('eligible_positions', ['M']) if x in needed]
                if len(elig) == 1:
                    pos = elig[0]
                    if current_counts[pos] < needed[pos]:
                        current_counts[pos] += 1
                        assigned_count += 1
                    else:
                        remaining.append(p)
                else:
                    remaining.append(p)

            for p in remaining:
                elig = [x for x in p.get('eligible_positions', ['M']) if x in needed and current_counts[x] < needed[x]]
                if elig:
                    best_pos = max(elig, key=lambda pos: (needed[pos] - current_counts[pos]))
                    current_counts[best_pos] += 1
                    assigned_count += 1

            if assigned_count == 10:
                return True

        return False

    def get_auto_sub_recommendations(self, starters: List[Dict[str, Any]], bench: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Identify starters and recommend valid bench substitutes (MUST BE ACTUALLY ON BENCH)
        who play in the SAME kickoff window or LATER and result in a legal Fantrax roster formation.
        Prioritizes direct squad teammate handcuffs (e.g. Hincapie -> Calafiori when Calafiori is on bench),
        followed by injury pre-match checks and late-kickoff tactical window insurance.
        """
        if not starters or not bench:
            return []

        recommendations = []
        from fantrax_assistant.suggest import are_teammate_handcuffs

        ROTATION_RISK_PLAYERS = {'Eberechi Eze', 'Mathys Tel', 'Rayan', 'Noni Madueke'}

        for starter in starters:
            p_name = starter.get('player') or starter.get('name', '')
            team_code = str(starter.get('team', '')).upper()
            s_fixture = starter.get('fixture', {})
            s_kickoff = s_fixture.get('kickoff_time', '')
            s_display_time = s_fixture.get('display_time', 'TBD')

            inj = self.config.get_player_injury(p_name) if self.config else {}
            inj_sev = starter.get('injury_severity') or inj.get('severity', 'Healthy')
            inj_type = starter.get('injury_type') or inj.get('injury_type', '')

            # Check if bench carries a direct teammate handcuff for this starter
            bench_handcuffs = [
                b for b in bench
                if str(b.get('team', '')).upper() == team_code and are_teammate_handcuffs(
                    p_name, team_code, starter.get('position', ''),
                    b.get('player', ''), b.get('team', ''), b.get('position', '')
                )
            ]

            # Valid bench replacements: MUST BE ACTUALLY ON BENCH and formation legal
            valid_bench = []
            s_is_gk = ('G' in starter.get('eligible_positions', [])) or (starter.get('assigned_pos') == 'G') or (starter.get('primary_pos') == 'G')

            for b in bench:
                b_is_gk = ('G' in b.get('eligible_positions', [])) or (b.get('assigned_pos') == 'G') or (b.get('primary_pos') == 'G')
                if s_is_gk != b_is_gk:
                    continue

                b_fixture = b.get('fixture', {})
                b_kickoff = b_fixture.get('kickoff_time', '')
                b_display_time = b_fixture.get('display_time', 'TBD')

                if b_kickoff >= s_kickoff and self.is_legal_roster_sub(starters, starter, b):
                    valid_bench.append((b, b_display_time))

            if not valid_bench:
                continue

            priority_score = 1.0
            risk_category = "Kickoff Insurance"
            risk_reason = "Formation-legal late kickoff cover"

            # 1. Direct Teammate Handcuffs on Bench (Priority 1)
            if bench_handcuffs:
                risk_category = "Teammate Handcuff"
                hc_names = ", ".join(b['player'] for b in bench_handcuffs)
                risk_reason = f"Direct {team_code} positional handcuff with {hc_names}"
                priority_score += 50.0

            # 2. Medical / Injury Concern (Priority 2)
            elif (inj_sev not in ['Healthy', 'Unknown', ''] and 'Healthy' not in str(inj_sev)) or inj_type:
                risk_category = "Injury Risk"
                risk_reason = f"{inj_type or inj_sev} pre-match medical check"
                priority_score += 35.0

            # 3. Known Attacking Rotation Risk (Priority 3 - Eze, Tel, etc.)
            elif p_name in ROTATION_RISK_PLAYERS:
                risk_category = "Rotation Risk"
                risk_reason = f"Tactical attacking rotation risk ({team_code})"
                priority_score += 25.0

            # 4. Late Fixture Window Insurance (Priority 4)
            else:
                if 'Mon' in s_display_time:
                    risk_category = "Late Kickoff Insurance"
                    risk_reason = "Monday night fixture coverage"
                    priority_score += 10.0
                elif '5:30' in s_display_time:
                    risk_category = "Kickoff Insurance"
                    risk_reason = "Late Sunday fixture window coverage"
                    priority_score += 5.0

            def get_sub_priority(starter_cand, bench_cand):
                s_name = starter_cand.get('player') or starter_cand.get('name', '')
                s_team = str(starter_cand.get('team', '')).upper()
                s_pos = str(starter_cand.get('position', starter_cand.get('primary_pos', 'M'))).upper()
                s_slot = str(starter_cand.get('assigned_pos', s_pos))[0]

                b_name = bench_cand.get('player') or bench_cand.get('name', '')
                b_team = str(bench_cand.get('team', '')).upper()
                b_pos = str(bench_cand.get('position', bench_cand.get('primary_pos', 'M'))).upper()

                weight = 0.0
                is_handcuff = (s_team == b_team and are_teammate_handcuffs(s_name, s_team, s_pos, b_name, b_team, b_pos))
                if is_handcuff:
                    weight += 50.0
                if s_slot == b_pos[0]:
                    weight += 8.0
                weight += float(bench_cand.get('proj_fpts', 0) or 0) * 0.5
                return weight

            valid_bench.sort(key=lambda x: get_sub_priority(starter, x[0]), reverse=True)
            best_sub, sub_display_time = valid_bench[0]

            recommendations.append({
                'starter': starter['player'],
                'starter_pos': starter.get('assigned_pos') or starter.get('position', ''),
                'starter_team': team_code,
                'starter_kickoff': s_display_time,
                'sub_candidate': best_sub['player'],
                'sub_pos': best_sub.get('primary_pos') or best_sub.get('position', ''),
                'sub_team': best_sub.get('team', ''),
                'sub_kickoff': sub_display_time,
                'priority_score': priority_score + float(starter.get('proj_fpts', 0) or 0) * 0.1,
                'risk_category': risk_category,
                'risk_reason': risk_reason,
                'rule_text': f"If {starter['player']} does not start, sub {best_sub['player']} ({s_display_time} → {sub_display_time})"
            })

        # Sort recommendations by highest priority score first
        recommendations.sort(key=lambda r: r['priority_score'], reverse=True)

        # Return top 3 recommendations
        return recommendations[:3]

    def get_top_waiver_stream_candidates(self, pos_filter: str = 'D', kickoff_time: str = '', limit: int = 2) -> List[Dict[str, Any]]:
        """
        Find top available waiver/free-agent stream targets for a position slot playing at kickoff_time or later.
        """
        if not self.config or not self.config.rankings:
            return []

        from fantrax_assistant.draft_state import DraftState
        try:
            state = DraftState()
            drafted = set()
            for t, roster in state.teams.items():
                for p in roster:
                    name = p.get('player') if isinstance(p, dict) else p
                    if name:
                        drafted.add(name)
        except Exception:
            drafted = set()

        candidates = []
        for r in self.config.rankings.get('rankings', []):
            name = r.get('player')
            team = r.get('team', '')
            pos = r.get('position', '')
            if name not in drafted and pos_filter in pos:
                fix = self.fixtures.get(team, {})
                f_kickoff = fix.get('kickoff_time', '')
                if not kickoff_time or f_kickoff >= kickoff_time:
                    candidates.append({
                        'player': name,
                        'team': team,
                        'position': pos,
                        'kickoff': fix.get('display_time', 'TBD'),
                        'opponent': fix.get('opponent', ''),
                        'fdr': fix.get('fdr', 3),
                        'adp': float(r.get('adp', 999) or 999)
                    })
        candidates.sort(key=lambda x: x['adp'])
        return candidates[:limit]

    def get_injury_contingencies(self, starters: List[Dict[str, Any]], bench: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate proactive contingency instructions for any starter carrying an injury or knock.
        Provides explicit league instructions:
          1. Direct substitute candidate (if available in current or later kickoff windows).
          2. 'Bench without sub' action (to hold roster slot open for later games/waivers).
          3. 'Drop/Stream' contingency if ruled out.
        """
        contingencies = []
        # Identify any bench players eligible for IR to open roster spots
        ir_eligible_bench = [
            b for b in bench
            if b.get('at_afcon')
            or (b.get('injury_severity') not in ['Healthy', 'Unknown', ''] and 'Healthy' not in str(b.get('injury_severity', '')))
            or b.get('injury_type')
        ]

        for starter in starters:
            p_name = starter.get('player') or starter.get('name', '')
            inj = self.config.get_player_injury(p_name) if self.config else {}
            inj_sev = starter.get('injury_severity') or inj.get('severity', 'Healthy')
            inj_type = starter.get('injury_type') or inj.get('injury_type', '')

            # Only process starters with genuine medical/injury concerns or knocks
            has_injury = (inj_sev not in ['Healthy', 'Unknown', ''] and 'Healthy' not in str(inj_sev)) or bool(inj_type)
            if not has_injury:
                continue

            s_fixture = starter.get('fixture', {})
            s_kickoff = s_fixture.get('kickoff_time', '')
            s_display_time = s_fixture.get('display_time', 'TBD')
            s_slot = starter.get('assigned_pos', starter.get('position', ''))

            # Filter bench players that maintain a LEGAL Fantrax formation
            legal_bench = [
                b for b in bench
                if (b.get('fixture', {}).get('kickoff_time', '') >= s_kickoff)
                and self.is_legal_roster_sub(starters, starter, b)
            ]
            legal_bench.sort(key=lambda x: x.get('proj_fpts', 0), reverse=True)
            best_legal_sub = legal_bench[0] if legal_bench else None

            stream_cands = self.get_top_waiver_stream_candidates(s_slot, s_kickoff, limit=2)
            stream_names = " or ".join(f"{c['player']} ({c['team']})" for c in stream_cands) if stream_cands else f"waiver {s_slot}"

            legal_warning = None
            ir_directive = None
            if not best_legal_sub:
                legal_warning = f"No legal late {s_slot} on bench (min 3 {s_slot}s required in 3-5-2 formation)"
                if ir_eligible_bench:
                    bench_ir = ir_eligible_bench[0]['player']
                    ir_directive = f"Move bench player {bench_ir} to your IR slot to open a roster spot. Add {stream_names} to your bench as legal cover for {p_name} without removing {p_name} from your starting lineup."
                else:
                    ir_directive = f"Keep {p_name} starting. If ruled out before kickoff, move {p_name} to your IR slot to stream {stream_names} without dropping anyone. Keeps Riccardo Calafiori on bench as #1 Handcuff Auto-Sub for Piero Hincapie."

            contingencies.append({
                'starter': p_name,
                'starter_team': starter.get('team', ''),
                'starter_pos': s_slot,
                'starter_kickoff': s_display_time,
                'injury_status': inj_type or inj_sev,
                'sub_candidate': best_legal_sub['player'] if best_legal_sub else None,
                'sub_team': best_legal_sub.get('team') if best_legal_sub else None,
                'sub_kickoff': best_legal_sub.get('fixture', {}).get('display_time') if best_legal_sub else None,
                'legal_warning': legal_warning,
                'ir_directive': ir_directive,
                'stream_targets': stream_cands,
                'bench_directive': f"Keep {p_name} in lineup. If declared out, move to IR slot to preserve late-window flexibility",
                'stream_directive': f"If {p_name} is declared out at {s_display_time}, move to IR slot and stream {stream_names} directly into your lineup without dropping anyone"
            })
        return contingencies

    def get_handcuff_map(self, squad: List[Dict[str, Any]], starter_names: Optional[set] = None) -> Dict[str, Dict[str, Any]]:
        """
        Builds a map of all teammate tactical handcuffs present on the squad using the single source of truth.
        """
        from fantrax_assistant.suggest import are_teammate_handcuffs, get_player_sub_role

        if starter_names is None:
            starter_names = set()

        handcuff_map = {}
        for i, p1 in enumerate(squad):
            for p2 in squad[i+1:]:
                n1, t1, pos1 = p1.get('player') or p1.get('name', ''), str(p1.get('team', '')).upper(), p1.get('position', '')
                n2, t2, pos2 = p2.get('player') or p2.get('name', ''), str(p2.get('team', '')).upper(), p2.get('position', '')
                if are_teammate_handcuffs(n1, t1, pos1, n2, t2, pos2):
                    both_starting = (n1 in starter_names and n2 in starter_names)
                    sub_role = get_player_sub_role(n1, t1, pos1)
                    handcuff_map[n1] = {
                        'partner': n2,
                        'team': t1,
                        'sub_role': sub_role,
                        'both_starting': both_starting,
                        'is_starter': n1 in starter_names,
                        'partner_is_starter': n2 in starter_names
                    }
                    handcuff_map[n2] = {
                        'partner': n1,
                        'team': t1,
                        'sub_role': sub_role,
                        'both_starting': both_starting,
                        'is_starter': n2 in starter_names,
                        'partner_is_starter': n1 in starter_names
                    }
        return handcuff_map

    def get_suggested_lineup_upgrades(self, weekly_lineup: Dict[str, Any], optimal_lineup: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Computes lineup upgrades and handcuff conflict resolutions comparing the current lineup
        against optimal projections and tactical sub-roles.
        """
        suggested_subs = []
        starters = weekly_lineup.get('starters', [])
        bench = weekly_lineup.get('bench', [])
        starter_names = {s['player'] for s in starters}
        all_squad = starters + bench

        handcuff_map = self.get_handcuff_map(all_squad, starter_names)
        added_pairs = set()

        # 1. Starting Lineup Handcuff Conflicts (e.g. Calafiori & Hincapie double-started at ARS LB)
        for n1, info in handcuff_map.items():
            if info['both_starting'] and (info['partner'], n1) not in added_pairs:
                added_pairs.add((n1, info['partner']))
                p1 = next((p for p in starters if p['player'] == n1), None)
                p2 = next((p for p in starters if p['player'] == info['partner']), None)
                if not p1 or not p2:
                    continue
                starter_to_keep = max([p1, p2], key=lambda x: float(x.get('proj_fpts', 0) or 0))
                starter_to_bench = min([p1, p2], key=lambda x: float(x.get('proj_fpts', 0) or 0))

                bench_def = next((b for b in bench if self.is_legal_roster_sub(starters, starter_to_bench, b)), None)
                if bench_def:
                    diff = round(float(bench_def.get('proj_fpts', 0) or 0) - float(starter_to_bench.get('proj_fpts', 0) or 0), 2)
                    suggested_subs.append({
                        'type': 'handcuff_conflict',
                        'is_conflict': True,
                        'is_handcuff': True,
                        'badge_label': f"{info['team']} {info['sub_role']} Handcuff Conflict",
                        'bench_player': bench_def['player'],
                        'bench_pos': bench_def.get('primary_pos') or bench_def.get('position', 'D'),
                        'bench_team': bench_def.get('team', ''),
                        'bench_proj': bench_def.get('proj_fpts', 0),
                        'starter_to_replace': starter_to_bench['player'],
                        'starter_pos': starter_to_bench.get('assigned_pos') or starter_to_bench.get('position', 'D'),
                        'starter_team': starter_to_bench.get('team', ''),
                        'starter_proj': starter_to_bench.get('proj_fpts', 0),
                        'projected_diff': diff,
                        'handcuff_partner': starter_to_keep['player'],
                        'reason': f"Both {starter_to_keep['player']} & {starter_to_bench['player']} are starting at {info['team']} {info['sub_role']}. Start {bench_def['player']} over {starter_to_bench['player']} and hold {starter_to_bench['player']} as #1 Auto-Sub for {starter_to_keep['player']}."
                    })

        # 2. Optimal Lineup Projection Upgrades
        optimal_starter_names = {p['player']: p for p in optimal_lineup.get('starters', [])}
        active_bench_names = {p['player']: p for p in bench}

        for opt_name, opt_p in optimal_starter_names.items():
            if opt_name in active_bench_names:
                bench_cand = active_bench_names[opt_name]
                bench_pos = bench_cand.get('primary_pos') or bench_cand.get('position', 'M')

                matching_starters = [
                    s for s in starters
                    if (s.get('primary_pos') or s.get('position', 'M')) == bench_pos
                    and s['player'] not in optimal_starter_names
                    and s['player'] not in handcuff_map
                ]
                if not matching_starters:
                    matching_starters = [
                        s for s in starters
                        if s['player'] not in optimal_starter_names
                        and s['player'] not in handcuff_map
                    ]

                if matching_starters:
                    worst_starter = min(matching_starters, key=lambda x: float(x.get('proj_fpts', 0) or 0))
                    diff = round(float(bench_cand.get('proj_fpts', 0) or 0) - float(worst_starter.get('proj_fpts', 0) or 0), 2)
                    pair_key = (bench_cand['player'], worst_starter['player'])
                    if diff > 0 and pair_key not in added_pairs:
                        added_pairs.add(pair_key)
                        suggested_subs.append({
                            'type': 'projection_upgrade',
                            'is_conflict': False,
                            'is_handcuff': False,
                            'badge_label': 'Projection Upgrade',
                            'bench_player': bench_cand['player'],
                            'bench_pos': bench_pos,
                            'bench_team': bench_cand.get('team', ''),
                            'bench_proj': bench_cand.get('proj_fpts', 0),
                            'starter_to_replace': worst_starter['player'],
                            'starter_pos': worst_starter.get('assigned_pos') or worst_starter.get('primary_pos') or worst_starter.get('position', 'M'),
                            'starter_team': worst_starter.get('team', ''),
                            'starter_proj': worst_starter.get('proj_fpts', 0),
                            'projected_diff': diff,
                            'reason': f"Projected +{diff:.2f} FPts ({'vs ' if bench_cand.get('fixture', {}).get('is_home') else '@ '}{bench_cand.get('fixture', {}).get('opponent', '')} FDR {bench_cand.get('fixture', {}).get('fdr', 3)} vs {worst_starter.get('fixture', {}).get('opponent', '')} FDR {worst_starter.get('fixture', {}).get('fdr', 3)})"
                        })

        # Sort handcuff conflicts first, then highest projected gains
        suggested_subs.sort(key=lambda x: (not x.get('is_conflict', False), -x['projected_diff']))
        return suggested_subs
