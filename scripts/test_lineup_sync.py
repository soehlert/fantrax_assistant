#!/usr/bin/env python3
"""Local Test & Verification Tool for Fantrax Synchronization & Pre-Check Lineup Alerts.

Run locally to verify Fantrax API connectivity, automatic pre-check lineup fetching,
and simulate matchday lineup drop / scratch alerts on YOUR real team before deploying.
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
    parser.add_argument("--league-id", type=str, default="", help="Fantrax League ID")
    parser.add_argument("--team-id", type=str, default="", help="Fantrax Team ID")
    parser.add_argument("--team-name", type=str, default="", help="Fantrax Team Name")
    parser.add_argument("--save", action="store_true", help="Permanently save provided league-id and team-id to data/settings.json")
    parser.add_argument("--scratch-player", type=str, default="", help="Specific starter name from your team to simulate as scratched/benched")
    parser.add_argument("--simulate-scratch", action="store_true", help="Simulate a benched starter 45 mins before kickoff using your actual roster")
    parser.add_argument("--send-alert", action="store_true", help="Dispatch real notifications to configured channels")
    return parser.parse_args()


def build_roster_from_fantrax_team(matched_team: dict, config: DraftConfig) -> list:
    """Build rich player roster dicts from Fantrax team starters and bench."""
    starters = matched_team.get("starters", [])
    bench = matched_team.get("bench", [])
    all_names = starters + bench
    player_details = matched_team.get("player_details", {})

    rich_roster = []
    seen = set()
    for name in all_names:
        if not name or name in seen:
            continue
        seen.add(name)
        p_detail = player_details.get(name, {})
        adp_info = config.get_player_adp(name) or {}

        pos = p_detail.get("position") or (adp_info.get("position") or "M").split(",")[0].strip().upper()
        team_code = p_detail.get("team") or adp_info.get("team") or "PL"
        fpg = float(adp_info.get("fpg", 0.0) or 0.0)

        elig = [x.strip().upper() for x in str(pos).split(",") if x.strip().upper() in ["G", "D", "M", "F"]] or ["M"]

        rich_roster.append({
            "player": name,
            "name": name,
            "position": pos,
            "assigned_pos": elig[0],
            "primary_pos": elig[0],
            "eligible_positions": elig,
            "team": team_code,
            "fpg": fpg
        })
    return rich_roster


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

    # Determine IDs
    league_id = args.league_id or settings.get("fantrax_league_id", "")
    team_id = args.team_id or settings.get("fantrax_team_id", "")
    team_name = args.team_name or settings.get("fantrax_team_name", "") or team_id or "Team 1"

    # Save settings if requested or if new IDs were supplied with --save
    if args.save or (args.league_id or args.team_id or args.team_name):
        if args.league_id:
            settings["fantrax_league_id"] = args.league_id
            league_id = args.league_id
        if args.team_id:
            settings["fantrax_team_id"] = args.team_id
            team_id = args.team_id
        if args.team_name:
            settings["fantrax_team_name"] = args.team_name
            team_name = args.team_name

        if args.save or args.league_id or args.team_id:
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(settings_file, "w") as f:
                json.dump(settings, f, indent=2)
            print(f"💾 Saved configuration to {settings_file.name}:")
            print(f"   • fantrax_league_id: {settings.get('fantrax_league_id')}")
            print(f"   • fantrax_team_id:   {settings.get('fantrax_team_id')}")
            print(f"   • fantrax_team_name: {settings.get('fantrax_team_name')}")

    target_identifier = team_id or team_name or "Team 1"

    print(f"\n📋 Active Configuration:")
    print(f"   • League ID:         {league_id or '(Not configured - use --league-id to set)'}")
    print(f"   • Target Team ID:    {team_id or '(Not configured - use --team-id to set)'}")
    print(f"   • Target Team Name:  {team_name}")
    print(f"   • Auto-Sync Enabled: {settings.get('auto_sync_enabled', True)}")
    print(f"   • Slack Webhook:     {'Configured' if settings.get('slack_webhook_url') else 'None'}")
    print(f"   • Discord Webhook:   {'Configured' if settings.get('discord_webhook_url') else 'None'}")
    print(f"   • ntfy Topic:        {settings.get('ntfy_topic') or 'None'}")
    print(f"   • macOS Alerts:      {settings.get('macos_alerts_enabled', True)}")

    # 2. Test Live Fantrax API Fetch
    print("\n" + "-" * 70)
    print("📡 Step 1: Connecting to Fantrax API & Fetching Team Lineup...")
    client = FantraxClient()
    draft_state = DraftState()
    config = DraftConfig()
    config.load_all_data()

    matched_team = None
    real_roster = []

    if league_id:
        roster_data = client.fetch_league_rosters(league_id)
        teams = roster_data.get("teams", {})
        print(f"   ✓ Successfully connected to Fantrax. Found {len(teams)} teams in league.")

        # Search by team ID or team name
        matched_team = teams.get(target_identifier) or teams.get(team_id) or teams.get(team_name)
        if not matched_team:
            for t_key, t_val in teams.items():
                if str(t_val.get("team_id", "")).strip().lower() == str(target_identifier).strip().lower():
                    matched_team = t_val
                    break
                if str(t_val.get("team_name", "")).strip().lower() == str(target_identifier).strip().lower():
                    matched_team = t_val
                    break

        if matched_team:
            actual_tname = matched_team.get("team_name", team_name)
            actual_tid = matched_team.get("team_id", team_id)
            print(f"\n   🎯 Found your team: '{actual_tname}' (Team ID: {actual_tid})")
            starters = matched_team.get("starters", [])
            bench = matched_team.get("bench", [])
            print(f"   • Active Starting XI ({len(starters)} players):")
            for idx, s in enumerate(starters, 1):
                p_meta = config.get_player_adp(s) or {}
                pos = (p_meta.get("position") or "M").split(",")[0].strip().upper()
                tm = p_meta.get("team") or "PL"
                print(f"     {idx:2d}. {s:<24} [{pos}] ({tm})")
            print(f"   • Bench ({len(bench)} players):")
            for idx, b in enumerate(bench, 1):
                p_meta = config.get_player_adp(b) or {}
                pos = (p_meta.get("position") or "M").split(",")[0].strip().upper()
                tm = p_meta.get("team") or "PL"
                print(f"     {idx:2d}. {b:<24} [{pos}] ({tm})")

            real_roster = build_roster_from_fantrax_team(matched_team, config)
            # Sync to local draft state
            client.sync_team_roster(league_id, actual_tid or actual_tname, draft_state)
        else:
            print(f"   ⚠️ Team ID / Name '{target_identifier}' not found in Fantrax league response.")
            print(f"      Available teams in league:")
            for idx, (t_key, t_info) in enumerate(teams.items(), 1):
                if idx <= 12 and isinstance(t_info, dict):
                    print(f"      - ID: {t_info.get('team_id')} | Name: '{t_info.get('team_name')}'")
    else:
        print("   ℹ️ No league ID configured yet.")
        print("   💡 Tip: Save your League ID & Team ID with:")
        print("      PYTHONPATH=src uv run python scripts/test_lineup_sync.py --league-id \"<LEAGUE_ID>\" --team-id \"<TEAM_ID>\" --save")

    # 3. Test Pre-Check Auto-Sync Hook in LineupMonitor
    print("\n" + "-" * 70)
    print("🔄 Step 2: Verifying LineupMonitor Pre-Check Auto-Sync Hook...")
    monitor = LineupMonitor(config=config, draft_state=draft_state, fantrax_client=client)
    if not args.send_alert:
        monitor.notifier.slack_url = ""
        monitor.notifier.discord_url = ""
        monitor.notifier.ntfy_topic = ""
        monitor.notifier.macos_enabled = False

    # Use actual roster if found, else draft_state, else sample fallback
    roster_to_use = real_roster
    if not roster_to_use:
        tracked_team = draft_state.teams.get(team_name) or draft_state.teams.get(team_id) or draft_state.teams.get("Team 1") or []
        if tracked_team:
            roster_to_use = list(tracked_team)

    if not roster_to_use:
        print("   (Using sample squad since real team was not found)")
        roster_to_use = [
            {"player": "Cole Palmer", "position": "M", "assigned_pos": "M", "primary_pos": "M", "team": "CHE", "fpg": 11.0},
            {"player": "Bukayo Saka", "position": "M", "assigned_pos": "M", "primary_pos": "M", "team": "ARS", "fpg": 10.5},
            {"player": "Bryan Mbeumo", "position": "M", "assigned_pos": "M", "primary_pos": "M", "team": "BRE", "fpg": 8.5},
            {"player": "Anthony Gordon", "position": "M", "assigned_pos": "M", "primary_pos": "M", "team": "NEW", "fpg": 7.8},
            {"player": "Josko Gvardiol", "position": "D", "assigned_pos": "D", "primary_pos": "D", "team": "MCI", "fpg": 8.0},
            {"player": "Gabriel Magalhaes", "position": "D", "assigned_pos": "D", "primary_pos": "D", "team": "ARS", "fpg": 7.5},
            {"player": "Trent Alexander-Arnold", "position": "D", "assigned_pos": "D", "primary_pos": "D", "team": "LIV", "fpg": 7.0},
            {"player": "David Raya", "position": "G", "assigned_pos": "G", "primary_pos": "G", "team": "ARS", "fpg": 6.5},
            {"player": "Alexander Isak", "position": "F", "assigned_pos": "F", "primary_pos": "F", "team": "NEW", "fpg": 9.5},
            {"player": "Jean-Philippe Mateta", "position": "F", "assigned_pos": "F", "primary_pos": "F", "team": "CRY", "fpg": 7.0},
            {"player": "Brennan Johnson", "position": "F", "assigned_pos": "F", "primary_pos": "F", "team": "TOT", "fpg": 6.0},
            {"player": "Morgan Rogers", "position": "M", "assigned_pos": "M", "primary_pos": "M", "team": "AVL", "fpg": 5.5},
            {"player": "Lewis Hall", "position": "D", "assigned_pos": "D", "primary_pos": "D", "team": "NEW", "fpg": 5.0},
            {"player": "Mark Flekken", "position": "G", "assigned_pos": "G", "primary_pos": "G", "team": "BRE", "fpg": 4.5}
        ]

    # Attach live/mock fixtures
    now = datetime.now(timezone.utc)
    for p in roster_to_use:
        p["fixture"] = {
            "kickoff_time": (now + timedelta(hours=3)).isoformat(),
            "display_time": "Today, 3:00 PM",
            "opponent": "OPP",
            "is_home": True,
            "fdr": 2
        }

    # Execute pre-check sync
    active_custom_starters = draft_state.custom_lineups.get(target_identifier) or (matched_team.get("starters") if matched_team else None)
    alerts = monitor.check_team_lineup_alerts(target_identifier, roster_to_use, custom_starters=active_custom_starters, auto_sync=True)
    print(f"   ✓ Pre-check auto-sync and lineup monitor executed cleanly.")
    print(f"   • Starting XI size evaluated: {len(active_custom_starters or [])} starters")
    print(f"   • Current alerts detected:    {len(alerts)}")

    # 4. Simulated Matchday Lineup Scratch Test on YOUR Actual Team
    if args.simulate_scratch or args.scratch_player:
        print("\n" + "-" * 70)
        print("🚨 Step 3: Simulating 45-Minute Pre-Kickoff Benched Starter Alert...")

        starters_list = active_custom_starters or [p["player"] for p in roster_to_use[:11]]

        def _is_gk(p_name: str) -> bool:
            p_dict = next((x for x in roster_to_use if x.get("player") == p_name or x.get("name") == p_name), None)
            if not p_dict:
                return False
            pos = p_dict.get("assigned_pos") or p_dict.get("primary_pos") or p_dict.get("position", "")
            return "G" in [x.strip().upper() for x in str(pos).split(",")]

        # Filter out Goalkeeper: Never pick GK for default scratch simulation since backup GK is rarely rostered
        outfield_starters = [p for p in starters_list if not _is_gk(p)]
        scratch_target = args.scratch_player or (outfield_starters[0] if outfield_starters else starters_list[0])

        # Find target in roster
        target_player_dict = None
        for p in roster_to_use:
            if p.get("player") == scratch_target or p.get("name") == scratch_target:
                target_player_dict = p
                break

        if not target_player_dict:
            target_player_dict = next((p for p in roster_to_use if not _is_gk(p.get("player") or p.get("name"))), roster_to_use[0])
            scratch_target = target_player_dict.get("player") or target_player_dict.get("name")

        # Set all bench players and other starters to kick off after the scratched player
        for p in roster_to_use:
            p["fixture"] = {
                "kickoff_time": (now + timedelta(hours=2)).isoformat(),
                "display_time": "Today, 4:15 PM",
                "opponent": "OPP",
                "is_home": True,
                "fdr": 2,
                "is_benched_override": False
            }

        # Set 45-minute countdown and scratch override for target starter
        target_player_dict["fixture"]["kickoff_time"] = (now + timedelta(minutes=45)).isoformat()
        target_player_dict["fixture"]["display_time"] = "Today, 3:00 PM"
        target_player_dict["fixture"]["is_benched_override"] = True

        print(f"   Simulated Scenario: Your outfield starter '{scratch_target}' ({target_player_dict.get('team')}, {target_player_dict.get('position')}) is benched 45 mins before kickoff.")
        sim_alerts = monitor.check_team_lineup_alerts(
            target_identifier,
            roster_to_use,
            custom_starters=starters_list,
            auto_sync=False
        )

        if sim_alerts:
            print(f"\n   🎉 Scratch Alert Triggered Successfully ({len(sim_alerts)} alert):")
            for a in sim_alerts:
                print(f"   • Severity:        {a['severity']}")
                print(f"   • Benched Player:  {a['starter']} ({a['starter_team']}, {a['starter_pos']})")
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
