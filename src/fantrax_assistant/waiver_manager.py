"""Waiver Wire Pickup Recommendation Engine for Fantrax Assistant.

Uses the exact same PlayerRecommendationEngine algorithm from the draft to evaluate
all unowned free agents, calculate Net FP/G gains vs drop candidates, and provide waiver recommendations.
"""

from typing import Dict, List, Any, Optional
from .suggest import PlayerRecommendationEngine
from .config import DraftConfig
from .draft_state import DraftState

class WaiverManagerEngine:
    """Calculates top free agent waiver wire pickup recommendations for tracked teams."""

    def __init__(self, config: Optional[DraftConfig] = None):
        self.config = config or DraftConfig()
        if not self.config.stats:
            self.config.load_all_data()

    def get_pickup_recommendations(
        self,
        team_name: str,
        state: DraftState,
        position_filter: Optional[str] = None,
        limit: int = 15
    ) -> List[Dict[str, Any]]:
        """
        Get ranked waiver wire pickup suggestions for a team.
        Identifies exact drop targets and calculates net FP/G gains.
        """
        team_roster = state.get_team(team_name)
        drafted_names = state.drafted_players

        # Instantiate PlayerRecommendationEngine (exact same algorithm as draft)
        rec_engine = PlayerRecommendationEngine(
            config=self.config,
            my_team=team_roster,
            drafted_players=drafted_names
        )

        # Get top evaluated unowned free agents
        raw_recommendations = rec_engine.get_recommendations(n=100)
        suggestions = []

        for item in raw_recommendations:
            p_data = item if isinstance(item, dict) else {}
            p_name = p_data.get('player') or p_data.get('name', '')
            pos = p_data.get('position', 'M')
            team_code = p_data.get('team', '')

            # Filter by position if specified
            if position_filter and position_filter.upper() != 'ALL':
                if position_filter.upper() not in pos.upper():
                    continue

            # Calculate effective FP/G and set-piece status
            effective_fpg = rec_engine.get_effective_fpg(p_data)
            set_piece_info = self.config.get_player_set_piece_status(p_name) if self.config else {}

            # Exclude injured or doubtful free agents
            inj = self.config.get_player_injury(p_name) if self.config else None
            if inj:
                sev = str(inj.get('severity') or '').strip()
                if any(k in sev for k in ['Long Term', 'Medium Term', 'Out', 'Doubtful']):
                    continue

            # Identify lowest-valued player on target team at this position (or bench)
            drop_candidate = None
            drop_candidate_fpg = 0.0

            pickup_pos_set = set(x.strip().upper() for x in pos.replace('/', ',').split(',') if x.strip())

            pos_matches = [
                tp for tp in team_roster
                if any(x in set((tp.get('position') or '').replace('/', ',').upper().split(',')) for x in pickup_pos_set)
            ]

            if pos_matches:
                # Find lowest FP/G player in matching eligible positions
                sorted_pos_matches = sorted(
                    pos_matches,
                    key=lambda x: rec_engine.get_effective_fpg(x)
                )
                drop_candidate_obj = sorted_pos_matches[0]
                drop_candidate = drop_candidate_obj.get('player')
                drop_candidate_fpg = rec_engine.get_effective_fpg(drop_candidate_obj)
            elif team_roster:
                # Overall lowest FP/G on bench/team
                sorted_roster = sorted(
                    team_roster,
                    key=lambda x: rec_engine.get_effective_fpg(x)
                )
                drop_candidate_obj = sorted_roster[0]
                drop_candidate = drop_candidate_obj.get('player')
                drop_candidate_fpg = rec_engine.get_effective_fpg(drop_candidate_obj)

            net_gain = round(effective_fpg - drop_candidate_fpg, 2)

            # Strictly require positive net improvement if roster is populated
            if team_roster and net_gain <= 0:
                continue

            # Generate 1-2 sentence sportswriter narrative explaining the 'why'
            stats_info = self.config.get_player_stats(p_name) if self.config else None
            narrative = self.generate_waiver_narrative(
                player_name=p_name,
                pos=pos,
                team_code=team_code,
                effective_fpg=effective_fpg,
                drop_candidate=drop_candidate,
                drop_fpg=drop_candidate_fpg,
                net_gain=net_gain,
                set_piece_info=set_piece_info,
                stats_info=stats_info
            )

            suggestions.append({
                'player': p_name,
                'position': pos,
                'team': team_code,
                'fpg': round(float(p_data.get('fpg', 0)), 2),
                'effective_fpg': round(effective_fpg, 2),
                'score': round(item.get('score', 0), 1),
                'drop_candidate': drop_candidate,
                'drop_candidate_fpg': round(drop_candidate_fpg, 2),
                'net_gain': net_gain,
                'set_piece_info': set_piece_info,
                'rationale': narrative,
                'reasons': item.get('reasons', [])
            })

        # Rank suggestions by Net FP/G Gain (highest upgrade first), then by algorithm score
        suggestions.sort(key=lambda s: (s['net_gain'], s['score']), reverse=True)
        return suggestions[:limit]

    def generate_waiver_narrative(
        self,
        player_name: str,
        pos: str,
        team_code: str,
        effective_fpg: float,
        drop_candidate: Optional[str],
        drop_fpg: float,
        net_gain: float,
        set_piece_info: dict,
        stats_info: Optional[dict] = None
    ) -> str:
        """Generate a concise 1-2 sentence sportswriter narrative explaining why the player is recommended."""
        starts = int(stats_info.get('starts', 0) or 0) if isinstance(stats_info, dict) else 0
        apps = int(stats_info.get('matches_played', 0) or 0) if isinstance(stats_info, dict) else 0
        start_rate = (starts / apps) if apps > 0 else 0.0

        sentences = []

        # 1. Primary Upgrade Sentence
        pos_display = pos.replace('/', ',')
        if drop_candidate and net_gain > 0:
            if net_gain >= 1.5:
                prefix = f"Significant roster upgrade: {player_name} ({effective_fpg:.2f} FP/G) delivers a +{net_gain:.2f} FP/G lift over {drop_candidate}."
            else:
                prefix = f"Solid depth upgrade: {player_name} ({effective_fpg:.2f} FP/G) nets a +{net_gain:.2f} FP/G improvement over {drop_candidate}."
        elif not drop_candidate:
            prefix = f"Immediate starting fit: {player_name} ({effective_fpg:.2f} FP/G) provides unowned {pos_display} scoring depth."
        else:
            prefix = f"{player_name} ({effective_fpg:.2f} FP/G) offers {pos_display} starting options for {team_code}."
        sentences.append(prefix)

        # 2. Tactical & Workload Context Sentence
        context_parts = []
        if set_piece_info.get('is_pk_taker') and set_piece_info.get('is_set_piece_taker'):
            context_parts.append(f"commands primary penalties and direct set pieces for {team_code}")
        elif set_piece_info.get('is_pk_taker'):
            context_parts.append(f"serves as primary penalty taker for {team_code}")
        elif set_piece_info.get('is_set_piece_taker'):
            context_parts.append(f"handles direct free-kick and corner deliveries for {team_code}")

        if apps >= 5 and start_rate >= 0.85:
            context_parts.append(f"boasts secured starter volume ({starts}/{apps} starts)")
        elif ',' in pos:
            context_parts.append(f"offers valuable {pos_display} dual-position roster flexibility")

        if context_parts:
            context_str = " and ".join(context_parts)
            sentences.append(f"He {context_str}.")
        elif team_code:
            sentences.append(f"Provides reliable regular rotation minutes in {team_code}'s lineup.")

        return " ".join(sentences)
