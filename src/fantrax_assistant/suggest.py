"""Player recommendation engine for draft assistant."""

from .config import DraftConfig


class PlayerRecommendationEngine:
    """Calculate player values and provide recommendations."""

    def __init__(self, config: DraftConfig, my_team: list, drafted_players: set):
        self.config = config
        self.my_team = my_team
        self.drafted_players = drafted_players

    def get_position_weight(self, position: str) -> float:
        """Get position difficulty weight (higher = more valuable)."""
        if not self.config.league_config:
            return 1.0

        scoring = self.config.league_config.get('scoring_rules', {})
        positions = scoring.get('positions', {})

        weight = positions.get(position, {}).get('weight', 1.0)
        return weight

    def get_top_8_clubs(self) -> set:
        """Get list of top 8 clubs."""
        if not self.config.league_config:
            return set()

        scoring = self.config.league_config.get('scoring_rules', {})
        return set(scoring.get('top_8_clubs', []))

    def calculate_base_value(self, player: dict) -> float:
        """
        Calculate base value from Fantrax FP/G (already includes league scoring).
        Weight: 30%
        """
        fpg = player.get('fpg', 0)
        position = player.get('position', 'M')
        pos_weight = self.get_position_weight(position)

        # Normalize FP/G to 0-100 scale
        # Assume elite player averages ~6 FP/G
        normalized = min(fpg / 6.0 * 100, 100)
        adjusted = normalized * pos_weight

        return min(adjusted * 0.30, 30)


    def calculate_adp_value(self, player: dict, current_round: int) -> float:
        """
        Calculate value based on ADP.
        Weight: 15%
        Lower ADP = better player (drafted earlier)
        """
        adp = player.get('adp', 999)

        # Lower ADP is better - normalize so lower numbers = higher score
        # ADP 1 = 99.5, ADP 50 = 75, ADP 200 = 0
        normalized = max(0, 100 - (adp / 2))

        return normalized * 0.07

    def calculate_form_value(self, player: dict) -> float:
        """
        Calculate recent form value.
        Weight: 20%
        """
        # Try to get recent form data
        recent_form = self.config._load_json('recent_form.json')

        if recent_form and 'recent_form' in recent_form:
            for form_player in recent_form['recent_form']:
                if self.config._fuzzy_match_name(player['player'], form_player.get('player', '')):
                    recent_fpts = form_player.get('recent_fpg', 0)
                    normalized = min(recent_fpts / 6.0 * 100, 100)
                    return normalized * 0.20

        # Check minimum starts requirement
        min_starts = 5 if days >= 60 else 3

        if starts < min_starts:
            return None

        # Fallback to season stats
        stats = player.get('stats')
        if not stats:
            return 10.0

        matches = stats.get('matches_played', 0)
        if matches == 0:
            return 5.0

        form_score = min(matches / 15.0, 1.0) * 100
        return form_score * 0.20

    def calculate_club_bonus(self, player: dict) -> float:
        """
        Calculate bonus for most goals by non-top-8 club.
        Weight: Included in base value
        """
        stats = player.get('stats')

        # Check if stats exist before accessing
        if not stats:
            return 0

        top_8 = self.get_top_8_clubs()

        if not self.config.league_config:
            return 0

        scoring = self.config.league_config.get('scoring_rules', {})
        bonus = scoring.get('non_top_8_most_goals_bonus', 0)

        team = player.get('team', '')
        goals = stats.get('goals', 0)

        # If player is from non-top-8 team and has good goal tally, add bonus
        if team not in top_8 and goals >= 5:
            return bonus

        return 0

    def calculate_missed_time(self, player: dict) -> float:
        """
        Calculate injury/AFCON penalty.
        Weight: 15%
        """
        injury = player.get('injury', {})
        severity = injury.get('severity', 'Healthy')

        # Check AFCON status
        afcon_status = self.config.get_player_afcon_status(player['player'])

        if afcon_status.get('at_afcon'):
            return 0.3 * 15

        multipliers = {
            'Healthy': 1.0,
            'Questionable': 0.85,
            'Doubtful': 0.6,
            'Short Term': 0.4,
            'Medium Term': 0.25,
            'Long Term': 0.1,
            'Unknown': 0.9,
            'Suspended': 0.5
        }

        multiplier = multipliers.get(severity, 0.9)
        return multiplier * 15

    def position_multiplier(self, player: dict) -> float:
        """
        Calculate position multiplier based on position and versatility.
        Attackers weighted most heavily, defenders least.
        Versatile players (multiple positions) get bonus.
        """
        position_str = player.get('position', '')

        # Base multiplier by PRIMARY position (or highest attacking position if multiple)
        if 'F' in position_str:
            base_multiplier = 1.25
        elif 'M' in position_str:
            base_multiplier = 0.75
        elif 'D' in position_str:
            base_multiplier = 0.50
        elif 'G' in position_str:
            base_multiplier = 0.25
        else:
            base_multiplier = 0.5

        # Versatility bonus - players with multiple positions
        versatility_bonus = 1.0
        if ',' in position_str:
            num_positions = len(position_str.split(','))
            versatility_bonus = 1.0 + (0.15 * (num_positions - 1))

        return base_multiplier * versatility_bonus

    def calculate_position_need(self, player: dict) -> float:
        """
        Calculate value based on roster needs.
        Weight: 10%
        """
        if not self.config.league_config:
            return 5.0

        position = player.get('position', '')
        roster_rules = self.config.league_config.get('roster_rules', {})

        current_count = sum(
            1 for p in self.my_team
            if position in p.get('position', '')
        )

        max_count = roster_rules.get(position, 0)
        position_multiplier = self.position_multiplier(player)

        if current_count >= max_count:
            return 3.0 * position_multiplier
        elif current_count == 0:
            return 15.0 * position_multiplier
        else:
            return 10.0 * position_multiplier

    def calculate_position_scarcity(self, player: dict) -> float:
        """
        Calculate position scarcity value.
        Weight: 5%

        Measures how much better this player is compared to the next
        available players at their position.
        """
        position = player.get('position', '')
        player_fpg = player.get('fpg', 0)

        all_players = self.config.rankings.get('rankings', [])
        position_players = [
            p for p in all_players
            if position in p.get('position', '')
               and p['player'] not in self.drafted_players
        ]

        if not position_players or len(position_players) < 2:
            return 2.5  # No scarcity data available

        position_players.sort(key=lambda x: x.get('fpg', 0), reverse=True)

        # Find this player's rank among available
        player_rank = None
        for rank, p in enumerate(position_players):
            if p['player'] == player.get('player'):
                player_rank = rank
                break

        if player_rank is None:
            return 1.0

        # If this is one of the top 5, high scarcity
        if player_rank < 5:
            return 2.0

        # Compare to next available tier (next 5 players)
        next_tier_start = player_rank + 1
        next_tier_end = min(player_rank + 6, len(position_players))

        if next_tier_start >= len(position_players):
            return 5.0  # Last player, high scarcity

        next_tier_players = position_players[next_tier_start:next_tier_end]
        next_tier_avg = sum(p.get('fpg', 0) for p in next_tier_players) / len(next_tier_players)

        if next_tier_avg == 0:
            return 5.0

        # How much better is this player than the next tier?
        drop_off = (player_fpg - next_tier_avg) / next_tier_avg
        scarcity = min(drop_off * 5.0, 5.0)  # Cap at 5

        return max(scarcity, 0.5)  # Floor at 0.5

    def calculate_positional_value(self, player: dict) -> float:
        """
        Calculate points above replacement for position.
        Weight: 5%
        """
        position = player.get('position', '')
        fpg = player.get('fpg', 0)

        all_players = self.config.rankings.get('rankings', [])
        position_players = [
            p.get('fpg', 0) for p in all_players
            if position in p.get('position', '')
        ]

        if not position_players:
            return 2.5

        avg_fpg = sum(position_players) / len(position_players)

        if avg_fpg == 0:
            return 2.5

        above_avg = (fpg - avg_fpg) / avg_fpg
        normalized = ((above_avg + 1) / 2) * 5
        normalized = max(0, min(5, normalized))

        return normalized

    def calculate_total_score(self, player: dict, current_round: int) -> float:
        """Calculate total weighted score for a player."""
        base = self.calculate_base_value(player)
        club_bonus = self.calculate_club_bonus(player)
        adp = self.calculate_adp_value(player, current_round)
        form = self.calculate_form_value(player)
        injury = self.calculate_missed_time(player)
        need = self.calculate_position_need(player)
        scarcity = self.calculate_position_scarcity(player)
        positional = self.calculate_positional_value(player)

        total = base + club_bonus + adp + form + injury + need + scarcity + positional

        return round(total, 2)

    def get_score_breakdown(self, player: dict, current_round: int) -> dict:
        """Get detailed breakdown of how score was calculated with intermediate values."""

        # Get base inputs
        fpg = player.get('fpg', 0)
        position = player.get('position', 'M')
        adp = player.get('adp', 999)
        matches = player.get('stats', {}).get('matches_played', 0) if player.get('stats') else 0

        # Calculate components
        base = self.calculate_base_value(player)
        club_bonus = self.calculate_club_bonus(player)
        adp_score = self.calculate_adp_value(player, current_round)
        form = self.calculate_form_value(player)
        injury = self.calculate_missed_time(player)
        need = self.calculate_position_need(player)
        scarcity = self.calculate_position_scarcity(player)
        positional = self.calculate_positional_value(player)

        # Get intermediate values for display
        pos_weight = self.get_position_weight(position)
        base_normalized = min(fpg / 6.0 * 100, 100)
        adp_normalized = max(0, 100 - (adp / 2))

        # Get injury multiplier
        injury_status = player.get('injury', {}).get('severity', 'Healthy')
        multipliers = {
            'Healthy': 1.0, 'Questionable': 0.85, 'Doubtful': 0.6,
            'Short Term': 0.7, 'Medium Term': 0.4, 'Long Term': 0.1,
            'Unknown': 0.9, 'Suspended': 0.5
        }
        injury_mult = multipliers.get(injury_status, 0.9)

        return {
            # Base value inputs and calculation
            'base_fpg': fpg,
            'base_position_weight': pos_weight,
            'base_normalized': round(base_normalized, 2),
            'base_value': round(base, 2),

            # Club bonus
            'club_bonus': round(club_bonus, 2),

            # ADP inputs and calculation
            'adp_value_raw': adp,
            'adp_normalized': round(adp_normalized, 2),
            'adp_value': round(adp_score, 2),

            # Form value
            'form_matches': matches,
            'form_value': round(form, 2),

            # Injury inputs and calculation
            'injury_status': injury_status,
            'injury_multiplier': injury_mult,
            'injury_penalty': round(injury, 2),

            # Position need
            'position_need': round(need, 2),

            # Scarcity
            'scarcity': round(scarcity, 2),

            # Positional value
            'positional_value': round(positional, 2),

            # Total
            'total': round(base + club_bonus + adp_score + form + injury + need + scarcity + positional, 2)
        }


    def get_recommendations(self, current_round: int, n: int = 10) -> list[dict]:
        """Get top N player recommendations."""
        available = self.config.get_all_available_players(self.drafted_players)

        for player in available:
            player['recommendation_score'] = self.calculate_total_score(
                player, current_round
            )

        available.sort(key=lambda x: x['recommendation_score'], reverse=True)

        return available[:n]

    def get_positional_rank(self, player_name: str) -> int:
        """Get player's rank within their position."""
        all_players = self.config.rankings.get('rankings', [])
        player_data = self.config.get_player_adp(player_name)

        if not player_data:
            return 999

        position = player_data.get('position', '')

        position_players = [
            p for p in all_players
            if position in p.get('position', '')
        ]

        position_players.sort(key=lambda x: x.get('fpg', 0), reverse=True)

        for rank, p in enumerate(position_players, 1):
            if p['player'] == player_name:
                return rank

        return 99
