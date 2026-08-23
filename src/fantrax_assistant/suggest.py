"""Player recommendation engine for draft assistant."""

from .config import DraftConfig

PLAYER_SUB_ROLES = {
    # Arsenal Tactical Sub-Roles
    'RICCARDO CALAFIOURI': ('ARS', 'LB'),
    'RICCARDO CALAFIORI': ('ARS', 'LB'),
    'PIERO HINCAPIE': ('ARS', 'LB'),
    'OLEKSANDR ZINCHENKO': ('ARS', 'LB'),
    'MYLES LEWIS-SKELLY': ('ARS', 'LB'),
    'WILLIAM SALIBA': ('ARS', 'CB'),
    'GABRIEL': ('ARS', 'CB'),
    'GABRIEL MAGALHAES': ('ARS', 'CB'),
    'BEN WHITE': ('ARS', 'RB'),
    'JURRIEN TIMBER': ('ARS', 'RB_LB'),
    'TAKAHIRO TOMIYASU': ('ARS', 'RB_LB'),

    # Manchester City Tactical Sub-Roles
    'MATHUES NUNES': ('MCI', 'LB_RM'),
    'MATHEUS NUNES': ('MCI', 'LB_RM'),
    'ABDUKODIR KHUSANOV': ('MCI', 'CB'),
    'RUBEN DIAS': ('MCI', 'CB'),
    'MANUEL AKANJI': ('MCI', 'CB'),
    'JOHN STONES': ('MCI', 'CB_DM'),
    'NATHAN AKE': ('MCI', 'LB_CB'),
    'JOSKO GVARDIOL': ('MCI', 'LB_CB'),
    'KYLE WALKER': ('MCI', 'RB'),
    'RICO LEWIS': ('MCI', 'RB'),
    'RAYAN CHERKI': ('MCI', 'AM_RW'),

    # Liverpool Tactical Sub-Roles
    'TRENT ALEXANDER-ARNOLD': ('LIV', 'RB'),
    'CONOR BRADLEY': ('LIV', 'RB'),
    'VIRGIL VAN DIJK': ('LIV', 'CB'),
    'IBRAHIMA KONATE': ('LIV', 'CB'),
    'JARELL QUANSAH': ('LIV', 'CB'),
    'JOE GOMEZ': ('LIV', 'LB_CB'),
    'ANDY ROBERTSON': ('LIV', 'LB'),
    'KOSTAS TSIMIKAS': ('LIV', 'LB'),

    # Chelsea Tactical Sub-Roles
    'REECE JAMES': ('CHE', 'RB'),
    'MALO GUSTO': ('CHE', 'RB'),
    'MARC CUCURELLA': ('CHE', 'LB'),
    'RENATO VEIGA': ('CHE', 'LB'),
    'LEVI COLWILL': ('CHE', 'CB'),
    'WESLEY FOFANA': ('CHE', 'CB'),
    'AXEL DISASI': ('CHE', 'CB'),
    'TOSIN ADARABIOYO': ('CHE', 'CB'),

    # Manchester United Tactical Sub-Roles
    'DIOGO DALOT': ('MUN', 'RB_LB'),
    'NOUSSAIR MAZRAOUI': ('MUN', 'RB_LB'),
    'LUKE SHAW': ('MUN', 'LB'),
    'TYRELL MALACIA': ('MUN', 'LB'),
    'MATTHIJS DE LIGT': ('MUN', 'CB'),
    'LISANDRO MARTINEZ': ('MUN', 'CB'),
    'LENY YORO': ('MUN', 'CB'),
    'HARRY MAGUIRE': ('MUN', 'CB'),

    # Tottenham Hotspur Tactical Sub-Roles
    'PEDRO PORRO': ('TOT', 'RB'),
    'ARCHIE GRAY': ('TOT', 'RB_CM'),
    'DESTINY UDOGIE': ('TOT', 'LB'),
    'BEN DAVIES': ('TOT', 'LB_CB'),
    'CRISTIAN ROMERO': ('TOT', 'CB'),
    'MIKY VAN DE VEN': ('TOT', 'CB'),
    'RADU DRAGUSIN': ('TOT', 'CB'),

    # Newcastle United Tactical Sub-Roles
    'KIERAN TRIPPIER': ('NEW', 'RB'),
    'TINO LIVRAMENTO': ('NEW', 'RB_LB'),
    'LEWIS HALL': ('NEW', 'LB'),
    'DAN BURN': ('NEW', 'LB_CB'),
    'FABIAN SCHAR': ('NEW', 'CB'),
    'SVEN BOTMAN': ('NEW', 'CB'),

    # Aston Villa Tactical Sub-Roles
    'MATTY CASH': ('AVL', 'RB'),
    'LUCAS DIGNE': ('AVL', 'LB'),
    'IAN MAATSEN': ('AVL', 'LB'),
    'EZRI KONSA': ('AVL', 'CB'),
    'PAU TORRES': ('AVL', 'CB'),
    'TYRONE MINGS': ('AVL', 'CB'),

    # Brighton & Hove Albion Tactical Sub-Roles
    'PERVIS ESTUPINAN': ('BHA', 'LB'),
    'TARIQ LAMPTEY': ('BHA', 'RB'),
    'JOEL VELTMAN': ('BHA', 'RB_CB'),
    'LEWIS DUNK': ('BHA', 'CB'),
    'JAN PAUL VAN HECKE': ('BHA', 'CB'),

    # West Ham United Tactical Sub-Roles
    'EMERSON': ('WHU', 'LB'),
    'EMERSON PALMIERI': ('WHU', 'LB'),
    'AARON WAN-BISSAKA': ('WHU', 'RB'),
    'VLADIMIR COUFAL': ('WHU', 'RB'),
    'MAX KILMAN': ('WHU', 'CB'),
    'JEAN-CLAIR TODIBO': ('WHU', 'CB'),

    # Attacking & Midfield Tactical Roles
    'EBERECHI EZE': ('ARS', 'AM_CM'),
    'NONI MADUEKE': ('ARS', 'RW'),
    'BUKAYO SAKA': ('ARS', 'RW'),
    'GABRIEL MARTINELLI': ('ARS', 'LW'),
    'LEANDRO TROSSARD': ('ARS', 'LW'),
    'MARTIN ODEGAARD': ('ARS', 'AM'),
    'KAI HAVERTZ': ('ARS', 'ST, AM'),
    'GABRIEL JESUS': ('ARS', 'ST'),
    'MATHYS TEL': ('TOT', 'LW, ST'),
    'SON HEUNG-MIN': ('TOT', 'LW, ST'),
    'CONOR GALLAGHER': ('TOT', 'CM, AM'),
    'JAMES MADDISON': ('TOT', 'AM'),
    'DEJAN KULUSEVSKI': ('TOT', 'RW, AM'),
    'BRENNAN JOHNSON': ('TOT', 'RW'),
    'DOMINIC SOLANKE': ('TOT', 'ST'),
    'JACK GREALISH': ('MCI', 'LW'),
    'JEREMY DOKU': ('MCI', 'LW, RW'),
    'SAVINHO': ('MCI', 'RW, LW'),
    'PHIL FODEN': ('MCI', 'AM, RW, LW'),
    'BERNARDO SILVA': ('MCI', 'CM, RW'),
    'KEVIN DE BRUYNE': ('MCI', 'AM, CM'),
    'ERLING HAALAND': ('MCI', 'ST'),
}


def get_player_sub_role(player_name: str, team: str, pos: str) -> str:
    """Determine specific pitch sub-role (e.g. LB, CB, RB, LW, RW, AM, CM, DM, ST)."""
    name_clean = str(player_name or '').upper().strip()
    if name_clean in PLAYER_SUB_ROLES:
        return PLAYER_SUB_ROLES[name_clean][1]
    p_primary = pos.split(',')[0].strip().upper() if pos else 'M'
    return p_primary


def are_teammate_handcuffs(p1_name: str, p1_team: str, p1_pos: str, p2_name: str, p2_team: str, p2_pos: str) -> bool:
    """Check if two players share a specific tactical pitch sub-role (e.g. LB vs LB, LW vs LW)."""
    if str(p1_team).upper() != str(p2_team).upper():
        return False
    r1 = get_player_sub_role(p1_name, p1_team, p1_pos)
    r2 = get_player_sub_role(p2_name, p2_team, p2_pos)
    import re
    roles1 = {x.strip() for x in re.split(r'[,/_]', r1) if x.strip()}
    roles2 = {x.strip() for x in re.split(r'[,/_]', r2) if x.strip()}
    return len(roles1 & roles2) > 0


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

    def get_effective_fpg(self, player: dict) -> float:
        """
        Calculate effective FP/G regressed towards baseline based on sample size and potential (ADP).
        Low sample players (< 5 games) are capped at the 2.25 baseline unless ADP shows high potential (ADP <= 60).
        """
        try:
            fpts = float(player.get('fpts', 0))
            fpg_raw = float(player.get('fpg', 0))
            adp = float(player.get('adp', 999))
        except (ValueError, TypeError):
            return 0.0

        if fpg_raw <= 0:
            return 0.0

        # Estimate matches played from total FPts and FP/G
        games = fpts / fpg_raw if fpg_raw > 0 else 0
        league_baseline_fpg = 2.25

        # For low sample size (< 10 matches, e.g. January transfers or late arrivals):
        if games < 10:
            # High potential / proven new signing (ADP <= 150) gets regressed rating
            if adp <= 150:
                prior_games = 6.0
                effective_fpg = ((fpg_raw * games) + (league_baseline_fpg * prior_games)) / (games + prior_games)
            else:
                # Unproven fringe player (high ADP): cap effective FP/G at 2.25 baseline
                prior_games = 10.0
                regressed = ((fpg_raw * games) + (league_baseline_fpg * prior_games)) / (games + prior_games)
                effective_fpg = min(regressed, league_baseline_fpg)
        else:
            # Regular player with >= 10 matches
            prior_games = 3.0
            effective_fpg = ((fpg_raw * games) + (league_baseline_fpg * prior_games)) / (games + prior_games)

        return effective_fpg

    def calculate_base_value(self, player: dict) -> float:
        """
        Calculate base value from effective FP/G (weighted by sample size and rotation risk).
        Weight: 30%
        """
        fpg = self.get_effective_fpg(player)
        position = player.get('position', 'M')
        pos_weight = self.get_position_weight(position)
        rot_risk = self.calculate_rotation_risk_penalty(player)

        # Normalize FP/G to 0-100 scale (elite effective FP/G ~4.5 in this league)
        normalized = min(fpg / 4.5 * 100, 100)
        adjusted = normalized * pos_weight * rot_risk

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
        if not hasattr(self, '_recent_form_cache'):
            self._recent_form_cache = self.config._load_json('recent_form.json', quiet=True)
        recent_form = self._recent_form_cache

        if recent_form and 'recent_form' in recent_form:
            for form_player in recent_form['recent_form']:
                if self.config._fuzzy_match_name(player['player'], form_player.get('player', '')):
                    recent_fpts = form_player.get('recent_fpg', 0)
                    normalized = min(recent_fpts / 6.0 * 100, 100)
                    return normalized * 0.20

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

    NEW_MANAGER_CLUBS = {'LIV', 'CHE', 'MUN', 'BHA', 'WHU'}

    def calculate_rotation_risk_penalty(self, player: dict) -> float:
        """
        Calculate rotation risk, season availability, new team integration penalty,
        and new manager tactical reset uncertainty.
        """
        team = str(player.get('team', '')).upper()
        adp = float(player.get('adp', 999) or 999)

        stats = player.get('stats') or {}
        starts = int(stats.get('starts', 0) or 0)
        apps = int(stats.get('matches_played', 0) or 0)
        mins = int(stats.get('minutes', 0) or 0)

        # Big 6 clubs (ARS, MCI, CHE, LIV, MUN, TOT) carry higher rotation standards due to squad depth & UCL fixtures
        is_big_six = team in {'ARS', 'MCI', 'CHE', 'LIV', 'MUN', 'TOT'}

        start_rate = (starts / apps) if apps > 0 else 0.0

        # Base risk multiplier from start rate and season starts / minutes
        if apps >= 5 and start_rate >= 0.85:
            base_risk = 1.0
        elif apps >= 5 and start_rate >= 0.70:
            base_risk = 0.95
        elif (is_big_six and (starts >= 26 or mins >= 2300)) or (not is_big_six and (starts >= 24 or mins >= 2000)):
            base_risk = 1.0
        elif (is_big_six and (starts >= 22 or mins >= 1800)) or (not is_big_six and (starts >= 18 or mins >= 1500)):
            base_risk = 0.95
        elif (is_big_six and (starts >= 15 or mins >= 1200)) or (not is_big_six and (starts >= 12 or mins >= 1000)):
            base_risk = 0.88  # Moderate rotation risk (e.g. Eze with 21 starts at ARS receives -12% rotation adjustment)
        else:
            # Check for New Team Transfer status
            is_new_team = bool(player.get('is_new_signing') or player.get('is_new_transfer') or (starts == 0 and apps == 0 and adp < 150))
            if is_new_team:
                base_risk = 0.90 if adp < 50 else 0.85
            else:
                base_risk = 0.80

        # New manager tactical reset adjustment (non-core veterans on new manager clubs face line-up uncertainty)
        if team in self.NEW_MANAGER_CLUBS and starts < 30 and mins < 2500:
            base_risk *= 0.93

        return base_risk

    def calculate_handcuff_bonus(self, player: dict) -> float:
        """
        Calculate teammate handcuff / rotation insurance bonus based on specific tactical pitch sub-roles (e.g. LB, CB, RB).
        If user's roster already owns a key player from Club T sharing the specific tactical sub-role (e.g. Calafiori at LB),
        an available teammate from Club T at that specific sub-role (e.g. Hincapie at LB)
        receives a +4.0 point Handcuff Insurance Bonus!
        """
        if not self.my_team:
            return 0.0

        cand_name = player.get('player') or player.get('name')
        cand_team = str(player.get('team', '')).upper()
        cand_pos = str(player.get('position', '')).upper()

        if not cand_team or not cand_name:
            return 0.0

        # Check if user owns any player from the same team sharing the exact tactical sub-role
        for p in self.my_team:
            p_name = p.get('player') or p.get('name')
            if p_name == cand_name:
                continue
            p_team = str(p.get('team', '')).upper()
            p_pos = str(p.get('position', '')).upper()
            if p_team == cand_team:
                if are_teammate_handcuffs(p_name, p_team, p_pos, cand_name, cand_team, cand_pos):
                    return 4.0

        return 0.0

    def position_multiplier(self, player: dict) -> float:
        """
        Calculate position multiplier based on positional scarcity, value, and draft progress.
        - Attackers (F and M) weighted highest early due to goal/assist scarcity.
        - Defenders (D) and Goalkeepers (G) multipliers slide upward as draft progresses.
        """
        position_str = player.get('position', '')

        # Calculate draft progress ratio across 128 total league picks
        total_drafted = len(self.drafted_players) if hasattr(self, 'drafted_players') and self.drafted_players else 0
        progress = min(1.0, max(0.0, total_drafted / 128.0))

        primary_pos = position_str.split(',')[0].strip().upper() if position_str else 'M'

        if primary_pos == 'F':
            base_multiplier = 1.40
        elif primary_pos == 'M':
            base_multiplier = 1.15
        elif primary_pos == 'D':
            # Base 0.45 early, sliding up to 0.80 as draft progresses
            base_multiplier = 0.45 + (0.35 * progress)
        elif primary_pos == 'G':
            # Base 0.25 early, sliding up to 0.65 as draft progresses
            base_multiplier = 0.25 + (0.40 * progress)
        else:
            base_multiplier = 0.60

        # Tiny 1% versatility bonus per extra position (max +0.25 pts) to prevent double counting
        versatility_bonus = 1.0
        if ',' in position_str:
            num_positions = len(position_str.split(','))
            versatility_bonus = 1.0 + (0.01 * (num_positions - 1))

        return base_multiplier * versatility_bonus

    def calculate_position_need(self, player: dict) -> float:
        """
        Calculate value based on roster needs for the candidate's primary position,
        incorporating primary (1.0) and secondary backup (0.5) flex depth.
        """
        if not self.config.league_config:
            return 5.0

        position_str = player.get('position', '')
        roster_rules = self.config.league_config.get('roster_rules', {})
        pos_mult = self.position_multiplier(player)

        # Evaluate candidate's primary position (first listed position, e.g. 'M' for 'M,F')
        primary_pos = position_str.split(',')[0].strip().upper() if position_str else 'M'
        max_count = roster_rules.get(primary_pos, 5)

        # Primary position match counts as 1.0 depth; secondary backup position match counts as 0.5 depth
        effective_depth = 0.0
        for p in self.my_team:
            p_pos_list = [x.strip().upper() for x in (p.get('position') or '').split(',') if x.strip()]
            if not p_pos_list:
                continue
            if p_pos_list[0] == primary_pos:
                effective_depth += 1.0
            elif primary_pos in p_pos_list[1:]:
                effective_depth += 0.5

        slots_left = max(0.0, max_count - effective_depth)

        if slots_left == 0:
            pos_score = 3.0
        elif slots_left <= 1.0:
            # 4/5 or near-capacity position: modest 6.0 pts
            pos_score = 6.0
        elif slots_left >= 4.0:
            # Urgent position need (e.g. 0/5 or 1/5 drafted)
            pos_score = 13.0 if effective_depth == 0 else 11.0
        else:
            pos_score = 9.0

        return pos_score * pos_mult

    def calculate_position_scarcity(self, player: dict) -> float:
        """
        Calculate position scarcity and tier cliff preservation value.
        Weight: 5%

        Measures how much better this player is compared to the next available players
        at their primary position, adding a Tier Cliff Preservation Bonus (+2.0 pts)
        if drafting this player prevents falling off a steep production drop-off.
        """
        position_str = player.get('position', '')
        primary_pos = position_str.split(',')[0].strip().upper() if position_str else 'M'
        player_fpg = self.get_effective_fpg(player)

        all_players = self.config.rankings.get('rankings', [])
        position_players = [
            p for p in all_players
            if primary_pos in (p.get('position') or '').split(',')[0].strip().upper()
               and p.get('player') not in self.drafted_players
        ]

        if not position_players or len(position_players) < 2:
            return 2.5

        position_players.sort(key=lambda x: self.get_effective_fpg(x), reverse=True)

        player_rank = None
        for rank, p in enumerate(position_players):
            if p.get('player') == player.get('player'):
                player_rank = rank
                break

        if player_rank is None:
            return 1.0

        # Tier Cliff Analysis: compare candidate to next 3 available at position
        next_tier_start = player_rank + 1
        next_tier_end = min(player_rank + 4, len(position_players))

        scarcity_score = 1.5
        if next_tier_start < len(position_players):
            next_tier_players = position_players[next_tier_start:next_tier_end]
            next_tier_avg = sum(self.get_effective_fpg(p) for p in next_tier_players) / len(next_tier_players)

            if next_tier_avg > 0:
                drop_off = (player_fpg - next_tier_avg) / next_tier_avg
                scarcity_score = min(5.0, max(0.5, drop_off * 5.0))

                # Steep Tier Cliff Preservation Bonus (+2.0 pts if next tier drops >= 0.8 FP/G)
                if (player_fpg - next_tier_avg) >= 0.8:
                    scarcity_score = min(5.0, scarcity_score + 2.0)

        # Top 3 available position players get a high scarcity baseline
        if player_rank < 3:
            scarcity_score = max(scarcity_score, 3.5)

        return round(scarcity_score, 2)

    def calculate_positional_value(self, player: dict) -> float:
        """
        Calculate points above replacement for position.
        Weight: 5%
        """
        position = player.get('position', '')
        fpg = self.get_effective_fpg(player)

        all_players = self.config.rankings.get('rankings', [])
        position_players = [
            self.get_effective_fpg(p) for p in all_players
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

    def calculate_position_multiplier(self, player: dict) -> float:
        return self.position_multiplier(player)

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
        handcuff = self.calculate_handcuff_bonus(player)

        total = base + club_bonus + adp + form + injury + need + scarcity + positional + handcuff

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


    def get_recommendations(self, current_round: int = 1, n: int = 10, exclude_team: str = None, ignore_position: list = None) -> list[dict]:
        """Get top N player recommendations."""
        available = self.config.get_all_available_players(self.drafted_players)

        # Filter team I don't want
        if exclude_team:
            exclude_team_upper = exclude_team.upper()
            available = [p for p in available if p.get('team', '').upper() != exclude_team_upper]

        if ignore_position:
            available = [p for p in available if not any(pos in p.get('position', '') for pos in ignore_position)]

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
