"""Lineup Alert Monitoring Engine for Fantrax Assistant.

Monitors official Premier League team sheets 60 minutes before kickoff and 5 minutes
before kickoff (warmup injury watch), alerting the manager if any starter in their Ideal XI is benched or scratched.
"""

from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from .weekly import WeeklyManagerEngine
from .config import DraftConfig
from .notifications import NotificationManager

class LineupMonitor:
    """Monitors starting lineup confirmations and generates emergency auto-sub alerts."""

    def __init__(self, config: Optional[DraftConfig] = None):
        self.config = config
        self.weekly_engine = WeeklyManagerEngine(config=config)
        self.notifier = NotificationManager()

    def check_team_lineup_alerts(
        self,
        team_id: str,
        roster: List[Dict[str, Any]],
        fixtures_override: Optional[Dict[str, Any]] = None,
        now_dt: Optional[datetime] = None,
        custom_starters: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Check team's active Starting XI against official match lineup confirmations.
        Prioritizes user's custom Starting XI over default optimal recommendations.
        Generates alerts for 60-minute lineup drops and 5-minute warmup scratches.
        """
        if not roster:
            return []

        # Get Ideal Starting XI and Bench
        lineup_data = self.weekly_engine.get_optimal_lineup(roster)
        starters = lineup_data.get('starters', [])
        bench = lineup_data.get('bench', [])

        # If user specified a custom active starting lineup, reorder starters & bench to match user choice
        if custom_starters:
            custom_set = set(custom_starters)
            all_players = starters + bench
            starters = [p for p in all_players if (p.get('player') or p.get('name')) in custom_set]
            bench = [p for p in all_players if (p.get('player') or p.get('name')) not in custom_set]

        auto_subs = self.weekly_engine.get_auto_sub_recommendations(starters, bench)
        contingencies = self.weekly_engine.get_injury_contingencies(starters, bench)
        ctg_lookup = {c['starter']: c for c in contingencies}

        # Map starter -> recommended sub
        sub_lookup = {}
        for sub_rec in auto_subs:
            sub_lookup[sub_rec['starter']] = sub_rec['sub_candidate']

        current_time = now_dt or datetime.now(timezone.utc)
        alerts = []

        for s in starters:
            p_name = s.get('player') or s.get('name', '')
            team_code = s.get('team', '')
            fix = s.get('fixture', {})
            kickoff_str = fix.get('kickoff_time', '')
            display_time = fix.get('display_time', 'TBD')

            # Parse kickoff datetime
            if not kickoff_str:
                continue

            try:
                kickoff_dt = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
            except Exception:
                continue

            diff_seconds = (kickoff_dt - current_time).total_seconds()
            minutes_until_kickoff = diff_seconds / 60.0

            # Check if within 60-minute team sheet window or 5-minute warmup window
            is_warmup_window = 0 <= minutes_until_kickoff <= 10
            is_lineup_window = 0 <= minutes_until_kickoff <= 65

            # Check injury status
            inj_info = self.config.get_player_injury(p_name) if self.config else {'severity': 'Healthy'}
            is_injured = inj_info.get('severity', 'Healthy') != 'Healthy'

            # Simulated or actual starter confirmation check
            # (In production, checks live PL element stats or injury feed)
            is_benched = False
            benched_reason = ""

            if is_injured:
                is_benched = True
                benched_reason = f"Injured ({inj_info.get('severity')})"
            elif fix.get('is_benched_override'):
                is_benched = True
                benched_reason = "Official Team Sheet: Benched / Not Starting"

            # Trigger Alert if starter is benched/injured within 60-minute or 5-minute window
            if (is_benched or fix.get('is_benched_override')) and (is_lineup_window or fix.get('force_alert')):
                recommended_sub = sub_lookup.get(p_name)
                if not recommended_sub and bench:
                    # Fallback to top valid bench sub
                    valid_subs = [
                        b['player'] for b in bench
                        if self.weekly_engine.is_legal_roster_sub(starters, s, b)
                    ]
                    recommended_sub = valid_subs[0] if valid_subs else "No Legal Bench Sub Available"

                severity = "CRITICAL (Warmup Scratch)" if is_warmup_window else "WARNING (Lineup Scratch)"
                time_label = f"{int(minutes_until_kickoff)} mins to kickoff" if minutes_until_kickoff >= 0 else "Kickoff past"

                ctg = ctg_lookup.get(p_name, {})
                alert_text = f"[{severity}] {p_name} ({team_code}) is NOT in the starting XI for {display_time} ({time_label}). Swap to recommended sub: {recommended_sub}."
                if ctg.get('ir_directive'):
                    alert_text += f" | {ctg.get('ir_directive')}"

                alert_dict = {
                    'starter': p_name,
                    'starter_pos': s.get('assigned_pos', s.get('primary_pos', 'M')),
                    'starter_team': team_code,
                    'kickoff_time': display_time,
                    'minutes_until_kickoff': round(minutes_until_kickoff, 1),
                    'severity': severity,
                    'reason': benched_reason or "Official Team Sheet: Benched",
                    'recommended_sub': recommended_sub,
                    'ir_directive': ctg.get('ir_directive'),
                    'stream_directive': ctg.get('stream_directive'),
                    'legal_warning': ctg.get('legal_warning'),
                    'alert_text': alert_text
                }
                sent_channels = self.notifier.send_lineup_alert(alert_dict)
                alert_dict['sent_channels'] = sent_channels
                alerts.append(alert_dict)

        return alerts

    def check_gameweek_eve_health(
        self,
        team_id: str,
        roster: List[Dict[str, Any]],
        custom_starters: Optional[List[str]] = None,
        now_dt: Optional[datetime] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Runs 24 hours before the gameweek's first match.
        Checks for:
          1. Unset or incomplete starting lineup (fewer than 11 starters).
          2. Confirmed injured/out players left in active starting spots.
          3. Pre-match injury contingencies requiring IR/waiver action.
        Sends a high-priority reminder if issues are found.
        """
        if not roster:
            return None

        lineup_data = self.weekly_engine.get_optimal_lineup(roster)
        starters = lineup_data.get('starters', [])
        bench = lineup_data.get('bench', [])

        if custom_starters:
            custom_set = set(custom_starters)
            all_players = starters + bench
            starters = [p for p in all_players if (p.get('player') or p.get('name')) in custom_set]
            bench = [p for p in all_players if (p.get('player') or p.get('name')) not in custom_set]

        # Find earliest kickoff
        earliest_kickoff_dt = None
        earliest_kickoff_str = "Tomorrow"
        for p in starters + bench:
            k_str = p.get('fixture', {}).get('kickoff_time', '')
            if k_str:
                try:
                    k_dt = datetime.fromisoformat(k_str.replace('Z', '+00:00'))
                    if earliest_kickoff_dt is None or k_dt < earliest_kickoff_dt:
                        earliest_kickoff_dt = k_dt
                        earliest_kickoff_str = p.get('fixture', {}).get('display_time', 'Tomorrow')
                except Exception:
                    pass

        current_time = now_dt or datetime.now(timezone.utc)
        if earliest_kickoff_dt:
            diff_hours = (earliest_kickoff_dt - current_time).total_seconds() / 3600.0
            is_eve_window = 0 <= diff_hours <= 36
        else:
            is_eve_window = False

        if not is_eve_window:
            return None

        issues = []
        # Check 1: Incomplete Starting XI
        if len(starters) < 11:
            issues.append(f"Incomplete Starting XI: Only {len(starters)} of 11 starting spots are filled.")

        # Check 2: Injured or Out players in Starting XI
        injured_starters = []
        for s in starters:
            p_name = s.get('player') or s.get('name', '')
            inj = self.config.get_player_injury(p_name) if self.config else {}
            sev = s.get('injury_severity') or inj.get('severity', 'Healthy')
            if sev in ['Long-term', 'Medium-term', 'Out', 'Suspended']:
                injured_starters.append(f"{p_name} ({sev})")

        if injured_starters:
            issues.append(f"Injured players starting: {', '.join(injured_starters)}.")

        # Check 3: Pre-match injury contingencies and legal roster risks
        contingencies = self.weekly_engine.get_injury_contingencies(starters, bench)
        for ctg in contingencies:
            if ctg.get('legal_warning'):
                issues.append(f"{ctg['starter']} ({ctg['starter_team']}, {ctg['injury_status']}): {ctg['legal_warning']}. IR Action: {ctg.get('ir_directive') or ctg.get('stream_directive')}")

        if not issues:
            return None

        reminder = {
            "title": f"⚠️ Gameweek Lineup Alert for {team_id}",
            "team_name": team_id,
            "first_kickoff": earliest_kickoff_str,
            "issues": issues,
            "message": f"Lineup issues detected for {team_id} ahead of {earliest_kickoff_str}:\n" + "\n".join(f"• {iss}" for iss in issues) + "\nPlease update your Fantrax starting XI before the deadline.",
            "severity": "CRITICAL" if len(starters) < 11 else "WARNING"
        }

        sent_channels = self.notifier.send_gameweek_reminder(reminder)
        reminder["sent_channels"] = sent_channels
        return reminder
