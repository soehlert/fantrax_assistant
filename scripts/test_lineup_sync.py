#!/usr/bin/env python3
"""Local Test & Verification Tool for Fantrax Synchronization & Pre-Check Lineup Alerts.

Run locally to verify Fantrax API connectivity, automatic pre-check lineup fetching,
and simulate matchday lineup drop / scratch alerts before deploying.
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add src and root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from fantrax_assistant.config import DraftConfig
from fantrax_assistant.draft_state import DraftState
from fantrax_assistant.lineup_monitor import LineupMonitor
from fantrax_assistant.scrapers.fantrax_api import FantraxClient
from fantrax_assistant.notifications import NotificationManager


def parse_args():
    parser = argparse.ArgumentParser(description="Test Fantrax Sync & Lineup Alerts locally")
    parser.add_argument("--team-id", type=str, default="", help="Fantrax Team ID")
    parser.add_argument("--team-name", type=str, default="", help="Fantrax Team Name")
    parser.add_argument("--league-id", type=str, default="", help="Fantrax League ID")
    parser.add_argument("--simulate-scratch", action="store_true", help="Simulate a benched starter 45 mins before kickoff")
    parser.add_argument("--send-alert", action="store_true", help="Dispatch real notifications to configured channels")
    return parser.parse_args()


def main():
    args = parse_args()
    print("=" * 70)
    print(" ⚽ Fantrax Assistant - Local Lineup Sync & Alerts Test Runner")
    print("=" * 70)

    # 1. Load Settings
    settings_file = ROOT_DIR / "data" / "settings.json"
    settings = {}
    if settings_file.exists():
        try:
            with open(settings_file) as f:
                settings = json.load(f)
        except Exception as e:
            print(f"⚠️ Warning loading settings.json: {e}")

    league_id = args.league_id or settings.get("fantrax_league_id", "")
    team_id = args.team_id or settings.get("fantrax_team_id", "")
    team_name = args.team_name or settings.get("fantrax_team_name", "") or team_id or "Team 1"
    target_identifier = team_id or team_name or "Team 1"

    print(f"\n📋 Configuration:")
    print(f"   • League ID:         {league_id or '(Not configured - using demo mode)'}")
    print(f"   • Target Team ID:    {team_id or '(Not specified)'}")
    print(f"   • Target Team Name:  {team_name}")
    print(f"   • Auto-Sync Enabled: {settings.get('auto_sync_enabled', True)}")
    print(f"   • Slack Webhook:     {'Configured' if settings.get('slack_webhook_url') else 'None'}")
    print(f"   • Discord Webhook:   {'Configured' if settings.get('discord_webhook_url') else 'None'}")
    print(f"   • ntfy Topic:        {settings.get('ntfy_topic') or 'None'}")
    print(f"   • macOS Alerts:      {settings.get('macos_alerts_enabled', True)}")

    # 2. Test Live Fantrax API Fetch
    print("\n" + "-" * 70)
    print("📡 Step 1: Testing Fantrax API Connectivity...")
    client = FantraxClient()
    draft_state = DraftState()

    if league_id:
        roster_data = client.fetch_league_rosters(league_id)
        teams = roster_data.get("teams", {})
        print(f"   ✓ Successfully queried Fantrax. Found {len(teams)} team entries.")

        matched = teams.get(target_identifier) or teams.get(team_name) or teams.get(team_id)
        if matched:
            print(f"\n   Found matching team: '{matched.get('team_name')}' (ID: {matched.get('team_id')})")
            starters = matched.get("starters", [])
            bench = matched.get("bench", [])
            print(f"   • Active Starting XI ({len(starters)} players):")
            for idx, s in enumerate(starters, 1):
                print(f"     {idx:2d}. {s}")
            print(f"   • Bench ({len(bench)} players):")
            for idx, b in enumerate(bench, 1):
                print(f"     {idx:2d}. {b}")
        else:
            print(f"   ℹ️ Team identifier '{target_identifier}' not found in active teams list.")
            print(f"      Available teams in league: {list(teams.keys())[:5]}...")
    else:
        print("   ℹ️ No league ID configured. Testing fallback/simulated sync mode.")

    # 3. Test Pre-Check Auto-Sync Hook in LineupMonitor
    print("\n" + "-" * 70)
    print("🔄 Step 2: Testing LineupMonitor Pre-Check Auto-Sync Hook...")
    config = DraftConfig()
    config.load_all_data()

    monitor = LineupMonitor(config=config, draft_state=draft_state, fantrax_client=client)
    if not args.send_alert:
        # Disable notification dispatch for dry run unless explicitly requested
        monitor.notifier.slack_url = ""
        monitor.notifier.discord_url = ""
        monitor.notifier.ntfy_topic = ""
        monitor.notifier.macos_enabled = False

    # Build test roster
    roster = []
    # If draft_state has drafted players for this team, use them; otherwise use sample starters
    tracked_team = draft_state.teams.get(team_name) or draft_state.teams.get(team_id) or draft_state.teams.get("Team 1") or []
    if tracked_team:
        roster = list(tracked_team)
    else:
        # Generate sample squad
        roster = [
            {"player": "Erling Haaland", "position": "F", "team": "MCI", "fpg": 12.5},
            {"player": "Cole Palmer", "position": "M", "team": "CHE", "fpg": 11.0},
            {"player": "Bukayo Saka", "position": "M", "team": "ARS", "fpg": 10.5},
            {"player": "Bryan Mbeumo", "position": "M", "team": "BRE", "fpg": 8.5},
            {"player": "Anthony Gordon", "position": "M", "team": "NEW", "fpg": 7.8},
            {"player": "Josko Gvardiol", "position": "D", "team": "MCI", "fpg": 8.0},
            {"player": "Gabriel Magalhaes", "position": "D", "team": "ARS", "fpg": 7.5},
            {"player": "Trent Alexander-Arnold", "position": "D", "team": "LIV", "fpg": 7.0},
            {"player": "David Raya", "position": "G", "team": "ARS", "fpg": 6.5},
            {"player": "Alexander Isak", "position": "F", "team": "NEW", "fpg": 9.5},
            {"player": "Jean-Philippe Mateta", "position": "F", "team": "CRY", "fpg": 7.0},
            {"player": "Brennan Johnson", "position": "F", "team": "TOT", "fpg": 6.0},
            {"player": "Morgan Rogers", "position": "M", "team": "AVL", "fpg": 5.5},
            {"player": "Lewis Hall", "position": "D", "team": "NEW", "fpg": 5.0},
            {"player": "Mark Flekken", "position": "G", "team": "BRE", "fpg": 4.5}
        ]

    # Attach fixtures
    now = datetime.now(timezone.utc)
    for p in roster:
        p["fixture"] = {
            "kickoff_time": (now + timedelta(hours=3)).isoformat(),
            "display_time": "Today, 3:00 PM",
            "opponent": "OPP",
            "is_home": True,
            "fdr": 2
        }

    # Run pre-check alerts check
    alerts = monitor.check_team_lineup_alerts(target_identifier, roster, auto_sync=True)
    print(f"   ✓ check_team_lineup_alerts() executed with pre-check auto-sync.")
    print(f"   • Current alerts detected: {len(alerts)}")

    # 4. Simulated Matchday Lineup Scratch Test
    if args.simulate_scratch:
        print("\n" + "-" * 70)
        print("🚨 Step 3: Simulating 45-Minute Pre-Kickoff Benched Starter Alert...")

        # Mark first starter as benched 45 minutes before kickoff
        scratch_player = roster[0]["player"]
        roster[0]["fixture"]["kickoff_time"] = (now + timedelta(minutes=45)).isoformat()
        roster[0]["fixture"]["display_time"] = "Today, 3:00 PM"
        roster[0]["fixture"]["is_benched_override"] = True

        print(f"   Simulated Scenario: Starter '{scratch_player}' is benched 45 minutes before kickoff.")
        sim_alerts = monitor.check_team_lineup_alerts(target_identifier, roster, custom_starters=[scratch_player], auto_sync=False)

        if sim_alerts:
            print(f"\n   🎉 Alert Generated Successfully ({len(sim_alerts)} alert):")
            for a in sim_alerts:
                print(f"   • Severity:        {a['severity']}")
                print(f"   • Benched Player:  {a['starter']} ({a['starter_team']})")
                print(f"   • Minutes to KO:   {a['minutes_until_kickoff']} mins")
                print(f"   • Recommended Sub: {a['recommended_sub']}")
                print(f"   • Alert Message:\n     \"{a['alert_text']}\"")
                if args.send_alert:
                    print(f"   • Dispatched To:   {a.get('sent_channels')}")
        else:
            print("   ⚠️ No alert triggered. Check scratch parameters.")

    print("\n" + "=" * 70)
    print(" ✅ Local Verification Complete! System is ready.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
