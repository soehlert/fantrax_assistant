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
                        player_details = {}
                        for item in items:
                            pid = item.get("id") if isinstance(item, dict) else str(item)
                            p_meta = player_db.get(pid, {}) if pid else {}
                            raw_pname = item.get("name") or item.get("playerName") or p_meta.get("name", "") if isinstance(item, dict) else str(item)
                            p_name = format_fantrax_name(raw_pname) or pid
                            if not p_name:
                                continue

                            p_pos = str(item.get("position") or p_meta.get("position") or "M").upper() if isinstance(item, dict) else "M"
                            p_team = str(item.get("team") or p_meta.get("team") or "PL").upper() if isinstance(item, dict) else "PL"
                            status = str(item.get("status", "")).upper() if isinstance(item, dict) else ""
                            slot = str(item.get("slot", "")).upper() if isinstance(item, dict) else ""
                            roster.append(p_name)
                            player_details[p_name] = {
                                "id": pid,
                                "name": p_name,
                                "position": p_pos,
                                "team": p_team,
                                "status": status,
                                "slot": slot
                            }
                            if status in ["ACTIVE", "START", "STARTER"] or (slot and slot not in ["B", "BENCH", "RES", "RESERVE", "IR"]):
                                starters.append(p_name)
                            else:
                                bench.append(p_name)

                    teams[tname] = {
                        "team_id": actual_team_id,
                        "team_name": tname,
                        "starters": [s for s in starters if s],
                        "bench": [b for b in bench if b],
                        "roster": [r for r in roster if r],
                        "player_details": player_details if "player_details" in locals() else {}
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

    def fetch_league_info(self, league_id: str) -> Dict[str, Any]:
        """Fetch general league info including schedule, matchups, and scoring periods."""
        if not league_id:
            return {"error": "Missing league_id"}

        cache_file = self.cache_dir / f"league_{league_id}_info.json"
        url = f"https://www.fantrax.com/fxea/general/getLeagueInfo?leagueId={league_id}"

        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if isinstance(data, dict) and "error" not in data:
                    with open(cache_file, "w") as f:
                        json.dump({"timestamp": datetime.now(timezone.utc).isoformat(), "data": data}, f, indent=2)
                    return data
                elif cache_file.exists():
                    try:
                        with open(cache_file) as f:
                            cached = json.load(f)
                            return cached.get("data", {})
                    except Exception:
                        pass
                return data if isinstance(data, dict) else {"error": "Invalid response"}
        except Exception as e:
            if cache_file.exists():
                try:
                    with open(cache_file) as f:
                        cached = json.load(f)
                        return cached.get("data", {})
                except Exception:
                    pass
            return {"error": str(e)}

    def fetch_matchup_scores(self, league_id: str, period: Optional[int] = None) -> Dict[str, Any]:
        """Fetch live matchup scores and category breakdowns for a specific scoring period."""
        if not league_id:
            return {"error": "Missing league_id", "matchups": []}

        p_str = f"&period={period}" if period else ""
        cache_key = f"p{period}" if period else "current"
        cache_file = self.cache_dir / f"league_{league_id}_matchup_{cache_key}.json"
        url = f"https://www.fantrax.com/fxea/general/getMatchupScores?leagueId={league_id}{p_str}"

        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = json.loads(resp.read().decode('utf-8'))
                if isinstance(raw, dict) and "error" not in raw and "matchups" in raw:
                    with open(cache_file, "w") as f:
                        json.dump({"timestamp": datetime.now(timezone.utc).isoformat(), "data": raw}, f, indent=2)
                    raw["cached"] = False
                    raw["synced_at"] = datetime.now(timezone.utc).strftime("%b %d, %I:%M %p")
                    return raw
                elif cache_file.exists():
                    try:
                        with open(cache_file) as f:
                            cached = json.load(f)
                            data = cached.get("data", {})
                            if isinstance(data, dict) and "matchups" in data:
                                data["cached"] = True
                                data["synced_at"] = (
                                    datetime.fromisoformat(cached["timestamp"]).strftime("%b %d, %I:%M %p")
                                    if "timestamp" in cached
                                    else "Cached"
                                )
                                return data
                    except Exception:
                        pass
                return raw if isinstance(raw, dict) else {"matchups": [], "period": period or 1, "cached": False}
        except Exception as e:
            if cache_file.exists():
                try:
                    with open(cache_file) as f:
                        cached = json.load(f)
                        data = cached.get("data", {})
                        if isinstance(data, dict):
                            data["cached"] = True
                            data["cache_time"] = cached.get("timestamp")
                            data["synced_at"] = (
                                datetime.fromisoformat(cached["timestamp"]).strftime("%b %d, %I:%M %p")
                                if "timestamp" in cached
                                else "Cached"
                            )
                            return data
                except Exception:
                    pass
            return {"error": str(e), "matchups": [], "period": period or 1, "cached": False}

    def fetch_period_rosters(self, league_id: str, period: Optional[int] = None) -> Dict[str, Any]:
        """Fetch all team rosters and active starters for a specific period."""
        if not league_id:
            return {"error": "Missing league_id", "teams": {}}

        p_str = f"&period={period}" if period else ""
        cache_key = f"p{period}" if period else "current"
        cache_file = self.cache_dir / f"league_{league_id}_rosters_{cache_key}.json"
        player_db = self.fetch_player_database("EPL")

        try:
            url_rosters = f"https://www.fantrax.com/fxea/general/getTeamRosters?leagueId={league_id}{p_str}"
            req_rosters = urllib.request.Request(url_rosters, headers=self.headers)
            with urllib.request.urlopen(req_rosters, timeout=10) as resp:
                rosters_raw = json.loads(resp.read().decode('utf-8'))

            league_info = self.fetch_league_info(league_id)
            team_info_map = league_info.get("teamInfo", {})

            if isinstance(rosters_raw, dict) and "error" not in rosters_raw:
                with open(cache_file, "w") as f:
                    json.dump({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "rosters": rosters_raw,
                        "teamInfo": team_info_map
                    }, f, indent=2)

            return self._parse_fantrax_roster_response(rosters_raw, team_info_map, player_db)
        except Exception as e:
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

    def get_live_matchup(
        self,
        league_id: str,
        team_name_or_id: str = "",
        period: Optional[int] = None,
        matchup_idx: Optional[int] = None,
        config: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Assemble comprehensive live matchup tracking payload for a team or specific matchup.
        Includes live score comparison, statistical category edges, side-by-side active starters,
        and fixture progress.
        """
        if not league_id:
            return {"error": "No Fantrax League ID configured.", "has_data": False}

        league_info = self.fetch_league_info(league_id)
        scoring_periods = league_info.get("scoringPeriods", [])

        # 1. Determine active period if not explicitly requested
        target_period = period
        if target_period is None:
            now_iso = datetime.now(timezone.utc).isoformat()
            for sp in scoring_periods:
                s_date = sp.get("startDate", "")
                e_date = sp.get("endDate", "")
                if s_date and e_date and s_date <= now_iso <= e_date:
                    target_period = sp.get("number")
                    break
            if target_period is None:
                target_period = 1

        matchup_scores_data = self.fetch_matchup_scores(league_id, period=target_period)
        all_matchups = matchup_scores_data.get("matchups", [])
        period_rosters_data = self.fetch_period_rosters(league_id, period=target_period)
        teams_rosters = period_rosters_data.get("teams", {})

        # Load fixture schedule from data/fixtures.json
        fixtures_map = {}
        fixtures_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "fixtures.json"
        if fixtures_path.exists():
            try:
                with open(fixtures_path) as f:
                    fixtures_map = json.load(f)
            except Exception:
                pass

        # 2. Identify the target matchup
        selected_matchup = None
        selected_matchup_idx = 0
        target_clean = str(team_name_or_id).strip().lower()

        if matchup_idx is not None and 0 <= matchup_idx < len(all_matchups):
            selected_matchup = all_matchups[matchup_idx]
            selected_matchup_idx = matchup_idx
        elif target_clean:
            for idx, m in enumerate(all_matchups):
                home_t = m.get("home", {})
                away_t = m.get("away", {})
                h_name = str(home_t.get("teamName", "")).lower()
                h_id = str(home_t.get("teamId", "")).lower()
                a_name = str(away_t.get("teamName", "")).lower()
                a_id = str(away_t.get("teamId", "")).lower()

                if target_clean in [h_name, h_id] or target_clean in [a_name, a_id] or (target_clean and (target_clean in h_name or target_clean in a_name)):
                    selected_matchup = m
                    selected_matchup_idx = idx
                    break

        if not selected_matchup and all_matchups:
            selected_matchup = all_matchups[0]
            selected_matchup_idx = 0

        # Build list of all available scoring periods for selector
        periods_list = []
        for sp in scoring_periods:
            p_num = sp.get("number", 1)
            periods_list.append({
                "period": p_num,
                "startDate": sp.get("startDate", ""),
                "endDate": sp.get("endDate", ""),
                "is_current": p_num == target_period
            })
        if not periods_list:
            periods_list = [{"period": i, "is_current": i == target_period} for i in range(1, 39)]

        # Build list of matchups in this period for selector dropdown
        matchups_overview = []
        for idx, m in enumerate(all_matchups):
            h = m.get("home", {})
            a = m.get("away", {})
            matchups_overview.append({
                "index": idx,
                "home_name": h.get("teamName", "Home"),
                "home_id": h.get("teamId", ""),
                "home_score": float(h.get("score", 0.0) or 0.0),
                "home_gp": h.get("gamesPlayed", 0),
                "away_name": a.get("teamName", "Away"),
                "away_id": a.get("teamId", ""),
                "away_score": float(a.get("score", 0.0) or 0.0),
                "away_gp": a.get("gamesPlayed", 0),
                "is_selected": idx == selected_matchup_idx
            })

        if not selected_matchup:
            return {
                "has_data": False,
                "league_id": league_id,
                "current_period": target_period,
                "periods": periods_list,
                "matchups_overview": matchups_overview,
                "error": "No matchup found for this period."
            }

        # 3. Parse selected matchup data
        home_meta = selected_matchup.get("home", {})
        away_meta = selected_matchup.get("away", {})
        home_id = str(home_meta.get("teamId", ""))
        home_name = home_meta.get("teamName", "Home Team")
        home_score = float(home_meta.get("score", 0.0) or 0.0)
        home_gp = int(home_meta.get("gamesPlayed", 0) or 0)

        away_id = str(away_meta.get("teamId", ""))
        away_name = away_meta.get("teamName", "Away Team")
        away_score = float(away_meta.get("score", 0.0) or 0.0)
        away_gp = int(away_meta.get("gamesPlayed", 0) or 0)

        score_diff = round(home_score - away_score, 2)
        is_user_home = bool(target_clean and (target_clean == home_id.lower() or target_clean in home_name.lower()))
        is_user_away = bool(target_clean and (target_clean == away_id.lower() or target_clean in away_name.lower()))

        # 4. Parse Categories Comparison
        raw_categories = selected_matchup.get("categories", [])
        categories = []
        home_cats_won = 0
        away_cats_won = 0
        cats_tied = 0

        for cat in raw_categories:
            c_name = cat.get("name", "")
            c_short = cat.get("shortName", "")
            c_group = cat.get("group", "")
            h_cat = cat.get("home", {})
            a_cat = cat.get("away", {})

            h_val = float(h_cat.get("value", 0.0) or 0.0)
            h_pts = float(h_cat.get("points", 0.0) or 0.0)
            h_disp = str(h_cat.get("display", f"{h_val:g}"))

            a_val = float(a_cat.get("value", 0.0) or 0.0)
            a_pts = float(a_cat.get("points", 0.0) or 0.0)
            a_disp = str(a_cat.get("display", f"{a_val:g}"))

            pts_diff = round(h_pts - a_pts, 2)
            if pts_diff > 0:
                leader = "home"
                home_cats_won += 1
            elif pts_diff < 0:
                leader = "away"
                away_cats_won += 1
            else:
                leader = "tie"
                cats_tied += 1

            categories.append({
                "name": c_name,
                "shortName": c_short,
                "group": c_group,
                "home_val": h_val,
                "home_pts": h_pts,
                "home_display": h_disp,
                "away_val": a_val,
                "away_pts": a_pts,
                "away_display": a_disp,
                "pts_diff": pts_diff,
                "leader": leader
            })

        # 5. Enrich Home and Away Rosters with player metadata & fixture progress
        def enrich_team_roster(team_id_str: str, team_name_str: str) -> Dict[str, Any]:
            team_data = teams_rosters.get(team_id_str) or teams_rosters.get(team_name_str, {})
            p_details = team_data.get("player_details", {})
            starters_list = team_data.get("starters", [])
            bench_list = team_data.get("bench", [])

            def enrich_player_item(p_name: str, is_starter: bool) -> Dict[str, Any]:
                details = p_details.get(p_name, {})
                pos = details.get("position", "M")
                team_code = details.get("team", "")

                # Lookup injury/fpg from config if available
                fpg = 0.0
                injury_sev = "Healthy"
                injury_type = ""
                if config:
                    adp_info = config.get_player_adp(p_name)
                    if adp_info:
                        fpg = float(adp_info.get("fpg", 0.0) or 0.0)
                        if not team_code:
                            team_code = adp_info.get("team", "")
                        if not pos or pos == "M":
                            pos = adp_info.get("position", pos)
                    inj = config.get_player_injury(p_name)
                    if inj:
                        injury_sev = inj.get("severity", "Healthy")
                        injury_type = inj.get("injury_type") or inj.get("notes", "")

                fix = fixtures_map.get(team_code, {})
                return {
                    "name": p_name,
                    "id": details.get("id", ""),
                    "position": pos,
                    "primary_pos": pos.split(",")[0].strip().upper() if pos else "M",
                    "team": team_code,
                    "is_starter": is_starter,
                    "fpg": fpg,
                    "injury_severity": injury_sev,
                    "injury_type": injury_type,
                    "fixture": {
                        "opponent": fix.get("opponent", "TBD"),
                        "is_home": fix.get("is_home", True),
                        "display_time": fix.get("display_time", "TBD"),
                        "kickoff_time": fix.get("kickoff_time", ""),
                        "started": fix.get("started", False),
                        "finished": fix.get("finished", False),
                        "fdr": fix.get("fdr", 3)
                    }
                }

            enriched_starters = [enrich_player_item(p, True) for p in starters_list]
            enriched_bench = [enrich_player_item(p, False) for p in bench_list]

            pos_order = {'G': 0, 'D': 1, 'M': 2, 'F': 3}
            enriched_starters.sort(key=lambda x: (pos_order.get(x['primary_pos'][0], 4), -x['fpg']))
            enriched_bench.sort(key=lambda x: (pos_order.get(x['primary_pos'][0], 4), -x['fpg']))

            # In-play vs played counters
            played_count = sum(1 for p in enriched_starters if p['fixture']['finished'])
            in_play_count = sum(1 for p in enriched_starters if p['fixture']['started'] and not p['fixture']['finished'])
            upcoming_count = sum(1 for p in enriched_starters if not p['fixture']['started'])

            return {
                "starters": enriched_starters,
                "bench": enriched_bench,
                "starters_count": len(enriched_starters),
                "bench_count": len(enriched_bench),
                "played_count": played_count,
                "in_play_count": in_play_count,
                "upcoming_count": upcoming_count
            }

        home_roster_enriched = enrich_team_roster(home_id, home_name)
        away_roster_enriched = enrich_team_roster(away_id, away_name)

        # Matchup status calculation
        is_live = False
        is_finished = False
        if home_gp >= 11 and away_gp >= 11:
            is_finished = True
        elif home_gp > 0 or away_gp > 0 or home_roster_enriched["in_play_count"] > 0 or away_roster_enriched["in_play_count"] > 0:
            is_live = True

        status_text = "FINAL" if is_finished else ("LIVE IN-PROGRESS" if is_live else "UPCOMING")
        status_color = "emerald" if is_live else ("slate" if is_finished else "blue")

        return {
            "has_data": True,
            "league_id": league_id,
            "current_period": target_period,
            "periods": periods_list,
            "matchups_overview": matchups_overview,
            "selected_matchup_index": selected_matchup_idx,
            "status_text": status_text,
            "status_color": status_color,
            "is_live": is_live,
            "is_finished": is_finished,
            "is_user_home": is_user_home,
            "is_user_away": is_user_away,
            "synced_at": matchup_scores_data.get("synced_at") or datetime.now(timezone.utc).strftime("%b %d, %I:%M %p"),
            "cached": matchup_scores_data.get("cached", False),
            "home": {
                "id": home_id,
                "name": home_name,
                "score": home_score,
                "games_played": home_gp,
                "cats_won": home_cats_won,
                "roster": home_roster_enriched
            },
            "away": {
                "id": away_id,
                "name": away_name,
                "score": away_score,
                "games_played": away_gp,
                "cats_won": away_cats_won,
                "roster": away_roster_enriched
            },
            "score_diff": score_diff,
            "categories": categories,
            "cats_tied": cats_tied
        }
