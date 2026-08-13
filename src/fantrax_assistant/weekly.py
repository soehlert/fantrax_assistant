"""Weekly Team Manager & Auto-Sub Recommendation Engine."""

from datetime import datetime
from typing import Dict, List, Any, Optional

# Standard Fantrax Roster Formation Constraints
POSITION_LIMITS = {
    'G': {'min': 1, 'max': 1},
    'D': {'min': 3, 'max': 5},
    'M': {'min': 3, 'max': 5},
    'F': {'min': 1, 'max': 3},
    'TOTAL_STARTERS': 11
}

# Premier League Team Match Schedule Mock / Live Fixture Map
# Format: team_code -> {'opponent': 'ARS', 'is_home': True, 'fdr': 2, 'kickoff_time': '2026-08-16T15:00:00Z', 'display_time': 'Sun 3:00 PM'}
DEFAULT_FIXTURE_SCHEDULE = {
    'ARS': {'opponent': 'WOL', 'is_home': True, 'fdr': 2, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun 3:00 PM'},
    'AVL': {'opponent': 'WHU', 'is_home': False, 'fdr': 3, 'kickoff_time': '2026-08-16T16:30:00Z', 'display_time': 'Sun 5:30 PM'},
    'BOU': {'opponent': 'NFO', 'is_home': False, 'fdr': 2, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun 3:00 PM'},
    'BRE': {'opponent': 'CRY', 'is_home': True, 'fdr': 3, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun 3:00 PM'},
    'BHA': {'opponent': 'EVE', 'is_home': False, 'fdr': 2, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun 3:00 PM'},
    'CHE': {'opponent': 'MCI', 'is_home': True, 'fdr': 4, 'kickoff_time': '2026-08-16T16:30:00Z', 'display_time': 'Sun 5:30 PM'},
    'CRY': {'opponent': 'BRE', 'is_home': False, 'fdr': 3, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun 3:00 PM'},
    'EVE': {'opponent': 'BHA', 'is_home': True, 'fdr': 3, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun 3:00 PM'},
    'FUL': {'opponent': 'MUN', 'is_home': False, 'fdr': 4, 'kickoff_time': '2026-08-15T19:00:00Z', 'display_time': 'Sat 8:00 PM'},
    'IPS': {'opponent': 'LIV', 'is_home': True, 'fdr': 5, 'kickoff_time': '2026-08-16T11:30:00Z', 'display_time': 'Sun 12:30 PM'},
    'LEI': {'opponent': 'TOT', 'is_home': True, 'fdr': 4, 'kickoff_time': '2026-08-17T19:00:00Z', 'display_time': 'Mon 8:00 PM'},
    'LIV': {'opponent': 'IPS', 'is_home': False, 'fdr': 2, 'kickoff_time': '2026-08-16T11:30:00Z', 'display_time': 'Sun 12:30 PM'},
    'MCI': {'opponent': 'CHE', 'is_home': False, 'fdr': 3, 'kickoff_time': '2026-08-16T16:30:00Z', 'display_time': 'Sun 5:30 PM'},
    'MUN': {'opponent': 'FUL', 'is_home': True, 'fdr': 2, 'kickoff_time': '2026-08-15T19:00:00Z', 'display_time': 'Sat 8:00 PM'},
    'NEW': {'opponent': 'SOU', 'is_home': True, 'fdr': 2, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun 3:00 PM'},
    'NFO': {'opponent': 'BOU', 'is_home': True, 'fdr': 3, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun 3:00 PM'},
    'SOU': {'opponent': 'NEW', 'is_home': False, 'fdr': 4, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun 3:00 PM'},
    'TOT': {'opponent': 'LEI', 'is_home': False, 'fdr': 2, 'kickoff_time': '2026-08-17T19:00:00Z', 'display_time': 'Mon 8:00 PM'},
    'WHU': {'opponent': 'AVL', 'is_home': True, 'fdr': 3, 'kickoff_time': '2026-08-16T16:30:00Z', 'display_time': 'Sun 5:30 PM'},
    'WOL': {'opponent': 'ARS', 'is_home': False, 'fdr': 5, 'kickoff_time': '2026-08-16T14:00:00Z', 'display_time': 'Sun 3:00 PM'},
}


class WeeklyManagerEngine:
    """Calculates weekly ideal starting XI and Fantrax auto-sub recommendations."""

    def __init__(self, fixture_schedule: Optional[Dict[str, Dict[str, Any]]] = None):
        self.fixtures = fixture_schedule or DEFAULT_FIXTURE_SCHEDULE

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
        """Calculate projected weekly fantasy points based on form, fixture difficulty, and home advantage."""
        fpg = float(player.get('fpg', 0) or 0)
        team_code = player.get('team', '')
        fixture = self.fixtures.get(team_code, {})

        fdr = fixture.get('fdr', 3)
        is_home = fixture.get('is_home', False)

        # FDR multiplier: FDR 1 (1.15), FDR 2 (1.08), FDR 3 (1.00), FDR 4 (0.90), FDR 5 (0.80)
        fdr_multiplier = {1: 1.15, 2: 1.08, 3: 1.00, 4: 0.90, 5: 0.80}.get(fdr, 1.0)
        home_boost = 1.05 if is_home else 0.97

        proj = fpg * fdr_multiplier * home_boost
        return round(proj, 2)

    def get_optimal_lineup(self, roster: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Formulate optimal starting 11 (1 G, 3-5 D, 3-5 M, 1-3 F) and bench order.
        """
        if not roster:
            return {
                'starters': [],
                'bench': [],
                'formation': '0-0-0',
                'total_projected_fpts': 0.0
            }

        # Enrich roster with projected points & primary position
        enriched = []
        for p in roster:
            p_copy = dict(p)
            p_copy['primary_pos'] = self.primary_pos = self._get_primary_position(p_copy.get('position', ''))
            p_copy['proj_fpts'] = self.calculate_projected_points(p_copy)
            team_code = p_copy.get('team', '')
            p_copy['fixture'] = self.fixtures.get(team_code, {
                'opponent': 'TBD',
                'is_home': True,
                'fdr': 3,
                'kickoff_time': '2026-08-16T15:00:00Z',
                'display_time': 'Sun 3:00 PM'
            })
            enriched.append(p_copy)

        # Sort by projected points descending
        enriched.sort(key=lambda x: x['proj_fpts'], reverse=True)

        by_pos = {'G': [], 'D': [], 'M': [], 'F': []}
        for p in enriched:
            by_pos[p['primary_pos']].append(p)

        starters = []
        bench = []

        # 1. Pick 1 Goalkeeper
        if by_pos['G']:
            starters.append(by_pos['G'][0])
            bench.extend(by_pos['G'][1:])
        
        # 2. Enforce Minimum Outfield Starters (3 D, 3 M, 1 F)
        d_candidates = list(by_pos['D'])
        m_candidates = list(by_pos['M'])
        f_candidates = list(by_pos['F'])

        for _ in range(min(3, len(d_candidates))):
            starters.append(d_candidates.pop(0))

        for _ in range(min(3, len(m_candidates))):
            starters.append(m_candidates.pop(0))

        for _ in range(min(1, len(f_candidates))):
            starters.append(f_candidates.pop(0))

        # 3. Fill remaining outfield starter spots (up to total 11 starters)
        remaining = d_candidates + m_candidates + f_candidates
        remaining.sort(key=lambda x: x['proj_fpts'], reverse=True)

        pos_counts = {
            'D': len([s for s in starters if s['primary_pos'] == 'D']),
            'M': len([s for s in starters if s['primary_pos'] == 'M']),
            'F': len([s for s in starters if s['primary_pos'] == 'F']),
        }

        for p in remaining:
            if len(starters) >= 11:
                bench.append(p)
                continue

            pos = p['primary_pos']
            max_allowed = POSITION_LIMITS[pos]['max']

            if pos_counts[pos] < max_allowed:
                starters.append(p)
                pos_counts[pos] += 1
            else:
                bench.append(p)

        # Sort starters & bench logically
        pos_order = {'G': 0, 'D': 1, 'M': 2, 'F': 3}
        starters.sort(key=lambda x: (pos_order.get(x['primary_pos'], 4), -x['proj_fpts']))
        bench.sort(key=lambda x: -x['proj_fpts'])

        d_cnt = pos_counts['D']
        m_cnt = pos_counts['M']
        f_cnt = pos_counts['F']
        formation_str = f"{d_cnt}-{m_cnt}-{f_cnt}"
        total_proj = round(sum(s['proj_fpts'] for s in starters), 1)

        return {
            'starters': starters,
            'bench': bench,
            'formation': formation_str,
            'total_projected_fpts': total_proj
        }

    def get_auto_sub_recommendations(self, starters: List[Dict[str, Any]], bench: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Identify starters with rotation risk and recommend valid bench substitutes
        who play in the SAME kickoff window or LATER.
        """
        if not starters or not bench:
            return []

        recommendations = []

        # Find starters with potential rotation / minutes risk
        # Risk factors: high rotation teams (MCI, CHE, ARS), returning from injury, or heavy fixture load
        high_rotation_teams = {'MCI', 'CHE', 'ARS', 'LIV'}

        for starter in starters:
            team_code = starter.get('team', '')
            s_fixture = starter.get('fixture', {})
            s_kickoff = s_fixture.get('kickoff_time', '')
            s_display_time = s_fixture.get('display_time', 'TBD')

            # Assess rotation risk score
            risk_score = 0
            risk_reasons = []

            if team_code in high_rotation_teams:
                risk_score += 2
                risk_reasons.append(f"{team_code} squad rotation risk")

            if starter.get('fpg', 0) < 3.0:
                risk_score += 1

            if risk_score == 0:
                continue

            # Find valid bench replacements playing in SAME kickoff window or LATER
            valid_bench = []
            for b in bench:
                b_fixture = b.get('fixture', {})
                b_kickoff = b_fixture.get('kickoff_time', '')
                b_display_time = b_fixture.get('display_time', 'TBD')

                # Kickoff comparison: b_kickoff >= s_kickoff
                if b_kickoff >= s_kickoff:
                    valid_bench.append((b, b_display_time))

            if not valid_bench:
                continue

            # Pick best valid bench player
            valid_bench.sort(key=lambda x: x[0].get('proj_fpts', 0), reverse=True)
            best_sub, sub_display_time = valid_bench[0]

            recommendations.append({
                'starter': starter['player'],
                'starter_pos': starter.get('position', ''),
                'starter_team': team_code,
                'starter_kickoff': s_display_time,
                'sub_candidate': best_sub['player'],
                'sub_pos': best_sub.get('position', ''),
                'sub_team': best_sub.get('team', ''),
                'sub_kickoff': sub_display_time,
                'risk_reason': ", ".join(risk_reasons),
                'rule_text': f"If {starter['player']} does not start, sub {best_sub['player']} ({s_display_time} → {sub_display_time})"
            })

        # Return top 3 recommendations
        return recommendations[:3]
