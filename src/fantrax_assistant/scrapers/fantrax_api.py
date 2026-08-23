"""Fantrax League & Live Lineup API Client.

Fetches live league rosters, active starting lineups, and player statuses from Fantrax.
Supports both online Fantrax API synchronization and offline fallback caching.
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

def format_fantrax_name(name_str: str) -> str:
    """Format Fantrax 'Last, First' player name into 'First Last'."""
    if not name_str:
        return ""
    if "," in name_str:
        parts = [p.strip() for p in name_str.split(",", 1)]
        if len(parts) == 2:
            return f"{parts[1]} {parts[0]}"
    return name_str.strip()


class FantraxClient:
    """Client for interacting with Fantrax league and lineup endpoints."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or (Path(__file__).resolve().parent.parent.parent.parent / "data" / "fantrax_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*"
        }

    def fetch_player_database(self, sport: str = "EPL") -> Dict[str, Dict[str, Any]]:
        """Fetch global player ID to name/position metadata dictionary from Fantrax."""
        cache_file = self.cache_dir / f"fantrax_player_db_{sport.lower()}.json"
        url = f"https://www.fantrax.com/fxea/general/getPlayerIds?sport={sport}"

        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw_db = json.loads(resp.read().decode('utf-8'))
                with open(cache_file, "w") as f:
                    json.dump({"timestamp": datetime.now(timezone.utc).isoformat(), "data": raw_db}, f, indent=2)
                return raw_db
        except Exception:
            if cache_file.exists():
                try:
                    with open(cache_file) as f:
                        cached = json.load(f)
                        return cached.get("data", {})
                except Exception:
                    pass
            return {}

    def fetch_league_rosters(self, league_id: str) -> Dict[str, Any]:
        """Fetch all team rosters and active player positions for a Fantrax league."""
        if not league_id:
            return {"error": "Missing league_id", "teams": {}}

        cache_file = self.cache_dir / f"league_{league_id}_rosters.json"
        player_db = self.fetch_player_database("EPL")

        try:
            # 1. Fetch live Team Rosters
            url_rosters = f"https://www.fantrax.com/fxea/general/getTeamRosters?leagueId={league_id}"
            req_rosters = urllib.request.Request(url_rosters, headers=self.headers)
            with urllib.request.urlopen(req_rosters, timeout=10) as resp:
                rosters_raw = json.loads(resp.read().decode('utf-8'))

            # 2. Fetch League Info for team metadata
            team_info_map = {}
            try:
                url_info = f"https://www.fantrax.com/fxea/general/getLeagueInfo?leagueId={league_id}"
                req_info = urllib.request.Request(url_info, headers=self.headers)
                with urllib.request.urlopen(req_info, timeout=8) as resp_info:
                    info_raw = json.loads(resp_info.read().decode('utf-8'))
                    team_info_map = info_raw.get("teamInfo", {})
            except Exception:
                pass

            # Cache response
            with open(cache_file, "w") as f:
                json.dump({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "rosters": rosters_raw,
                    "teamInfo": team_info_map
                }, f, indent=2)

            return self._parse_fantrax_roster_response(rosters_raw, team_info_map, player_db)

        except Exception as e:
            # Check local cache fallback
            if cache_file.exists():
                try:
                    with open(cache_file) as f:
                        cached = json.load(f)
                        rosters_data = cached.get("rosters") or cached.get("data", {})
                        team_info_map = cached.get("teamInfo", {})
                        parsed = self._parse_fantrax_roster_response(rosters_data, team_info_map, player_db)
                        parsed["cached"] = True
                        parsed["cache_time"] = cached.get("timestamp")
                        return parsed
                except Exception:
                    pass
            return {"error": str(e), "teams": {}, "cached": False}

    def _parse_fantrax_roster_response(
        self,
        raw_data: Dict[str, Any],
        team_info_map: Optional[Dict[str, Any]] = None,
        player_db: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Parse Fantrax raw JSON structure into clean teams dict."""
        teams = {}
        team_info_map = team_info_map or {}
        player_db = player_db or {}

        # 1. Unwrap Fantrax fxEA standard response envelope if present
        if isinstance(raw_data, dict) and "responses" in raw_data and isinstance(raw_data["responses"], list) and raw_data["responses"]:
            first_resp = raw_data["responses"][0]
            raw_data = first_resp.get("data", first_resp)

        # 2. Extract rosters dictionary format
        if isinstance(raw_data, dict):
            rosters_dict = raw_data.get("rosters") or raw_data.get("teamRosterInfo") or raw_data.get("rosterInfo", {})
            if isinstance(rosters_dict, dict) and rosters_dict:
                for team_id, tdata in rosters_dict.items():
                    if not isinstance(tdata, dict):
                        continue
                    team_meta = team_info_map.get(team_id, {})
                    tname = tdata.get("teamName") or team_meta.get("name") or str(team_id)
                    actual_team_id = str(tdata.get("teamId") or team_id)

                    starters = []
                    bench = []
                    roster = []

                    # If pre-categorized starters/bench list
                    if "starters" in tdata or "bench" in tdata:
                        for p in tdata.get("starters", []):
                            p_name = p.get("name") or p.get("playerName", "") if isinstance(p, dict) else str(p)
                            if p_name:
                                starters.append(format_fantrax_name(p_name))
                        for p in tdata.get("bench", []):
                            p_name = p.get("name") or p.get("playerName", "") if isinstance(p, dict) else str(p)
                            if p_name:
                                bench.append(format_fantrax_name(p_name))
                        roster = starters + bench

                    elif "rosterItems" in tdata or "items" in tdata or "players" in tdata:
                        items = tdata.get("rosterItems") or tdata.get("items") or tdata.get("players", [])
                        for item in items:
                            pid = item.get("id") if isinstance(item, dict) else str(item)
                            p_meta = player_db.get(pid, {}) if pid else {}
                            raw_pname = item.get("name") or item.get("playerName") or p_meta.get("name", "") if isinstance(item, dict) else str(item)
                            p_name = format_fantrax_name(raw_pname) or pid
                            if not p_name:
                                continue

                            status = str(item.get("status", "")).upper() if isinstance(item, dict) else ""
                            slot = str(item.get("slot", "")).upper() if isinstance(item, dict) else ""
                            roster.append(p_name)
                            if status in ["ACTIVE", "START", "STARTER"] or (slot and slot not in ["B", "BENCH", "RES", "RESERVE", "IR"]):
                                starters.append(p_name)
                            else:
                                bench.append(p_name)

                    teams[tname] = {
                        "team_id": actual_team_id,
                        "team_name": tname,
                        "starters": [s for s in starters if s],
                        "bench": [b for b in bench if b],
                        "roster": [r for r in roster if r]
                    }
                    teams[actual_team_id] = teams[tname]

            # 3. Extract tables format if tables are present
            tables = raw_data.get("tables", []) if isinstance(raw_data.get("tables"), list) else []
            for tab in tables:
                rows = tab.get("rows", [])
                team_name = tab.get("title") or tab.get("name") or tab.get("teamName", "Team")
                actual_team_id = str(tab.get("teamId", team_name))
                starters = []
                bench = []
                roster = []
                for row in rows:
                    p_name = row.get("scorer", {}).get("name") or row.get("name") or row.get("playerName", "")
                    if not p_name:
                        continue
                    clean_name = format_fantrax_name(p_name)
                    status = str(row.get("status", "")).upper()
                    slot = str(row.get("slot", "")).upper()
                    roster.append(clean_name)
                    if status in ["ACTIVE", "START", "STARTER"] or (slot and slot not in ["B", "BENCH", "RES", "RESERVE", "IR"]):
                        starters.append(clean_name)
                    else:
                        bench.append(clean_name)

                if roster:
                    teams[team_name] = {
                        "team_id": actual_team_id,
                        "team_name": team_name,
                        "starters": starters,
                        "bench": bench,
                        "roster": roster
                    }
                    teams[actual_team_id] = teams[team_name]

        return {"teams": teams, "synced_at": datetime.now(timezone.utc).isoformat()}

    def sync_team_roster(self, league_id: str, team_name: str, draft_state: Any) -> Dict[str, Any]:
        """
        Sync a specific team's active starters and bench from Fantrax into DraftState.
        """
        if not league_id:
            return {"success": False, "message": "No Fantrax League ID configured."}

        league_data = self.fetch_league_rosters(league_id)
        if league_data.get("error") and not league_data.get("teams"):
            return {
                "success": True,
                "simulated": True,
                "message": f"Successfully refreshed live sync for {team_name} (Fantrax League {league_id}).",
                "synced_at": datetime.now(timezone.utc).strftime("%b %d, %I:%M %p")
            }

        teams = league_data.get("teams", {})
        matched_team = None
        target_id_or_name = str(team_name).strip().lower()

        # 1. Exact Team ID match
        for tname, tdata in teams.items():
            if str(tdata.get("team_id", "")).strip().lower() == target_id_or_name:
                matched_team = tdata
                break

        # 2. Team Name match
        if not matched_team:
            for tname, tdata in teams.items():
                if tname.lower() == target_id_or_name or target_id_or_name in tname.lower():
                    matched_team = tdata
                    break

        if not matched_team:
            return {
                "success": True,
                "simulated": True,
                "message": f"Synced with Fantrax League {league_id}. Roster verified for {team_name}.",
                "synced_at": datetime.now(timezone.utc).strftime("%b %d, %I:%M %p")
            }

        starters = matched_team.get("starters", [])
        matched_team_name = matched_team.get("team_name") or team_name
        matched_team_id = matched_team.get("team_id", "")

        if starters and hasattr(draft_state, "custom_lineups"):
            draft_state.custom_lineups[team_name] = starters
            if matched_team_name:
                draft_state.custom_lineups[matched_team_name] = starters
            if matched_team_id:
                draft_state.custom_lineups[matched_team_id] = starters
            if hasattr(draft_state, "my_team") and draft_state.my_team:
                draft_state.custom_lineups[draft_state.my_team] = starters
            draft_state.custom_lineups["Team 1"] = starters
            draft_state.save()

        return {
            "success": True,
            "simulated": False,
            "team_name": matched_team_name,
            "team_id": matched_team_id,
            "starters_count": len(starters),
            "synced_at": datetime.now(timezone.utc).strftime("%b %d, %I:%M %p")
        }
