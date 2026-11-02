"""Yahoo Fantasy API client wrapper using yfpy."""

from datetime import datetime, timedelta, date
from statistics import mean, stdev
from typing import Any

from yfpy.query import YahooFantasySportsQuery

from .config import YahooConfig
from .nba_schedule import (
    get_remaining_games_count,
    get_games_by_date,
    get_team_games_in_range,
    get_team_games_played,
)


class YahooFantasyClient:
    """Client for interacting with Yahoo Fantasy Basketball API."""

    # Yahoo Fantasy API base URL
    BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"

    def __init__(self, config: YahooConfig):
        """Initialize the Yahoo Fantasy client."""
        self.config = config
        self._query: YahooFantasySportsQuery | None = None
        self._league_key: str | None = None
        self._scoring_categories: dict[str, tuple[str, int]] | None = None

    @property
    def query(self) -> YahooFantasySportsQuery:
        """Get or create the Yahoo Fantasy query object."""
        if self._query is None:
            self._query = YahooFantasySportsQuery(
                league_id=self.config.league_id,
                game_code=self.config.game_code,
                yahoo_consumer_key=self.config.consumer_key,
                yahoo_consumer_secret=self.config.consumer_secret,
                env_file_location=self.config.data_dir,
                save_token_data_to_env_file=True,
            )
        return self._query

    @property
    def league_key(self) -> str:
        """Get the league key."""
        if self._league_key is None:
            self._league_key = self.query.get_league_key()
        return self._league_key

    def _decode_string(self, value: Any) -> str:
        """Decode bytes to string if necessary."""
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value) if value else ""

    def _get_response_json(self, url: str) -> dict:
        """Make a direct API call and return JSON response."""
        response = self.query.get_response(url)
        return response.json()

    def get_scoring_categories(self) -> dict[str, tuple[str, int]]:
        """Get the league's scoring categories.

        Returns:
            Dict mapping stat_id to (stat_name, sort_order)
            sort_order: 1 = higher is better, 0 = lower is better
        """
        if self._scoring_categories is not None:
            return self._scoring_categories

        settings = self.query.get_league_settings()
        categories = {}

        if hasattr(settings, "stat_categories") and settings.stat_categories:
            stat_cats = settings.stat_categories
            if hasattr(stat_cats, "stats"):
                for stat in stat_cats.stats:
                    stat_id = str(getattr(stat, "stat_id", ""))
                    display_name = getattr(stat, "display_name", "")
                    sort_order = int(getattr(stat, "sort_order", 1))
                    enabled = getattr(stat, "enabled", 0)
                    is_only_display = getattr(stat, "is_only_display_stat", 0)

                    # Skip display-only stats (like FGM/A) - they show made/attempted
                    # but scoring is based on the percentage
                    if enabled == 1 and is_only_display != 1:
                        categories[stat_id] = (display_name, sort_order)

        self._scoring_categories = categories
        return categories

    def get_current_week(self) -> int:
        """Get the current matchup week."""
        league_info = self.query.get_league_info()
        return int(league_info.current_week)

    def get_my_team_id(self) -> str:
        """Get the authenticated user's team ID."""
        if self.config.team_id:
            return self.config.team_id

        teams = self.query.get_league_teams()
        for team in teams:
            if hasattr(team, "is_owned_by_current_login") and team.is_owned_by_current_login:
                return str(team.team_id)

        if teams:
            return str(teams[0].team_id)

        raise ValueError("Could not determine team ID")

    def get_my_team(self) -> dict[str, Any]:
        """Get the user's team roster with player season stats."""
        team_id = self.get_my_team_id()
        team_key = f"{self.league_key}.t.{team_id}"

        # Use direct API call to get roster with player season stats
        url = f"{self.BASE_URL}/team/{team_key}/roster/players/stats;type=season"
        data = self._get_response_json(url)

        fantasy_content = data.get("fantasy_content", {})
        team_data = fantasy_content.get("team", [])

        team_name = ""
        players = []

        if team_data:
            # Extract team name
            for item in team_data[0]:
                if isinstance(item, dict) and "name" in item:
                    team_name = self._decode_string(item["name"])

            # Extract players (usually in team_data[1])
            if len(team_data) > 1:
                roster = team_data[1].get("roster", {})
                players_container = roster.get("0", {}).get("players", {})

                for key, value in players_container.items():
                    if key == "count":
                        continue
                    player_info = value.get("player", [])
                    if player_info:
                        player_data = self._parse_player_from_api(player_info)
                        players.append(player_data)

        return {
            "team_id": team_id,
            "team_name": team_name,
            "players": players,
        }

    def get_weekly_matchup(self, week: int | None = None) -> dict[str, Any]:
        """Get the weekly matchup with detailed stat comparison."""
        if week is None:
            week = self.get_current_week()

        team_id = self.get_my_team_id()

        # Get scoreboard to find opponent
        url = f"{self.BASE_URL}/league/{self.league_key}/scoreboard;week={week}"
        data = self._get_response_json(url)

        fantasy_content = data.get("fantasy_content", {})
        league = fantasy_content.get("league", [])

        opponent_id = None
        stat_winners = []
        week_start = ""
        week_end = ""

        if len(league) > 1:
            scoreboard = league[1].get("scoreboard", {})
            matchups_container = scoreboard.get("0", {}).get("matchups", {})

            for key, value in matchups_container.items():
                if key == "count":
                    continue
                matchup = value.get("matchup", {})

                # Get week dates
                week_start = matchup.get("week_start", "")
                week_end = matchup.get("week_end", "")

                # Get stat winners
                stat_winners = [
                    sw.get("stat_winner", {})
                    for sw in matchup.get("stat_winners", [])
                ]

                teams_container = matchup.get("0", {}).get("teams", {})
                team_ids_in_matchup = []

                for tk, tv in teams_container.items():
                    if tk == "count":
                        continue
                    team_info = tv.get("team", [])
                    if team_info:
                        for item in team_info[0]:
                            if isinstance(item, dict) and "team_id" in item:
                                team_ids_in_matchup.append(item["team_id"])

                if str(team_id) in team_ids_in_matchup:
                    for tid in team_ids_in_matchup:
                        if tid != str(team_id):
                            opponent_id = tid
                    break

        if not opponent_id:
            return {"error": f"No matchup found for week {week}"}

        # Get detailed stats for both teams
        my_team_key = f"{self.league_key}.t.{team_id}"
        opp_team_key = f"{self.league_key}.t.{opponent_id}"

        my_name, my_stats = self._get_team_weekly_stats(my_team_key, week)
        opp_name, opp_stats = self._get_team_weekly_stats(opp_team_key, week)

        # Compare stats
        comparison = self._compare_weekly_stats(my_stats, opp_stats)

        return {
            "week": week,
            "week_start": week_start,
            "week_end": week_end,
            "my_team": {
                "team_id": team_id,
                "team_name": my_name,
                "stats": my_stats,
            },
            "opponent": {
                "team_id": opponent_id,
                "team_name": opp_name,
                "stats": opp_stats,
            },
            "comparison": comparison,
        }

    def _get_team_weekly_stats(self, team_key: str, week: int) -> tuple[str, dict[str, float]]:
        """Get a team's stats for a specific week."""
        url = f"{self.BASE_URL}/team/{team_key}/stats;type=week;week={week}"
        data = self._get_response_json(url)

        fantasy_content = data.get("fantasy_content", {})
        team = fantasy_content.get("team", [])

        team_name = ""
        stats = {}

        if team:
            for item in team[0]:
                if isinstance(item, dict) and "name" in item:
                    team_name = self._decode_string(item["name"])

            if len(team) > 1:
                team_stats = team[1].get("team_stats", {})
                stats_list = team_stats.get("stats", [])
                for stat_entry in stats_list:
                    stat = stat_entry.get("stat", {})
                    stat_id = str(stat.get("stat_id", ""))
                    value = stat.get("value", "")
                    stat_name = self._get_stat_name(stat_id)
                    if stat_name:
                        stats[stat_name] = self._parse_stat_value(value)

        return team_name, stats

    def _compare_weekly_stats(
        self, my_stats: dict[str, float], opp_stats: dict[str, float]
    ) -> dict[str, Any]:
        """Compare weekly stats between two teams using league scoring categories."""
        categories = self.get_scoring_categories()

        winning = []
        losing = []
        tied = []

        for stat_id, (stat_name, sort_order) in categories.items():
            my_val = my_stats.get(stat_name, 0)
            opp_val = opp_stats.get(stat_name, 0)

            if sort_order == 1:  # Higher is better
                if my_val > opp_val:
                    winning.append({"stat": stat_name, "my_value": my_val, "opp_value": opp_val})
                elif my_val < opp_val:
                    losing.append({"stat": stat_name, "my_value": my_val, "opp_value": opp_val})
                else:
                    tied.append({"stat": stat_name, "my_value": my_val, "opp_value": opp_val})
            else:  # Lower is better (TO, PF)
                if my_val < opp_val:
                    winning.append({"stat": stat_name, "my_value": my_val, "opp_value": opp_val})
                elif my_val > opp_val:
                    losing.append({"stat": stat_name, "my_value": my_val, "opp_value": opp_val})
                else:
                    tied.append({"stat": stat_name, "my_value": my_val, "opp_value": opp_val})

        return {
            "winning": winning,
            "losing": losing,
            "tied": tied,
            "score": f"{len(winning)}-{len(losing)}-{len(tied)}",
        }

    def get_remaining_games(self, week: int | None = None) -> dict[str, Any]:
        """Get remaining games for the week for both teams."""
        if week is None:
            week = self.get_current_week()

        team_id = self.get_my_team_id()
        team_key = f"{self.league_key}.t.{team_id}"

        # Get matchup data first to get week dates
        matchup_data = self.get_weekly_matchup(week)
        week_start_str = matchup_data.get("week_start", "")
        week_end_str = matchup_data.get("week_end", "")

        # Parse dates and determine remaining games date range
        today = date.today()
        try:
            week_end = datetime.strptime(week_end_str, "%Y-%m-%d").date()
            # Use today as start if we're mid-week, otherwise use week start
            if week_start_str:
                week_start = datetime.strptime(week_start_str, "%Y-%m-%d").date()
                remaining_start = max(today, week_start)
            else:
                remaining_start = today
        except ValueError:
            # Fallback: use today through end of week
            remaining_start = today
            week_end = today + timedelta(days=7)

        # Fetch NBA schedule for the remaining days
        schedule_data = get_team_games_in_range(remaining_start, week_end)
        games_by_date = get_games_by_date(remaining_start, week_end)

        # Get roster with player info
        url = f"{self.BASE_URL}/team/{team_key}/roster;week={week}/players/stats"
        data = self._get_response_json(url)
        my_players = self._parse_roster_for_games(data, schedule_data)

        # Get opponent
        opponent_id = matchup_data.get("opponent", {}).get("team_id")

        opp_players = []
        if opponent_id:
            opp_team_key = f"{self.league_key}.t.{opponent_id}"
            url = f"{self.BASE_URL}/team/{opp_team_key}/roster;week={week}/players/stats"
            data = self._get_response_json(url)
            opp_players = self._parse_roster_for_games(data, schedule_data)

        return {
            "week": week,
            "week_start": week_start_str,
            "week_end": week_end_str,
            "remaining_from": remaining_start.isoformat(),
            "games_by_date": games_by_date,
            "my_team": {
                "team_name": matchup_data.get("my_team", {}).get("team_name", ""),
                "total_remaining_games": sum(p.get("remaining_games", 0) for p in my_players),
                "players": my_players,
            },
            "opponent": {
                "team_name": matchup_data.get("opponent", {}).get("team_name", ""),
                "total_remaining_games": sum(p.get("remaining_games", 0) for p in opp_players),
                "players": opp_players,
            },
        }

    def _parse_roster_for_games(
        self, data: dict, schedule_data: dict[str, list[dict]] | None = None
    ) -> list[dict]:
        """Parse roster data to extract player remaining games."""
        players = []
        fantasy_content = data.get("fantasy_content", {})
        team_data = fantasy_content.get("team", [])

        if len(team_data) > 1:
            roster = team_data[1].get("roster", {})
            players_container = roster.get("0", {}).get("players", {})

            for key, value in players_container.items():
                if key == "count":
                    continue
                player_info = value.get("player", [])
                if player_info:
                    player_data = self._parse_player_from_api(player_info)

                    # Add remaining games from NBA schedule
                    if schedule_data:
                        player_team = player_data.get("team", "")
                        team_games = schedule_data.get(player_team, [])
                        player_data["remaining_games"] = len(team_games)
                        player_data["game_dates"] = [g["date"] for g in team_games]
                    else:
                        player_data["remaining_games"] = 0
                        player_data["game_dates"] = []

                    players.append(player_data)

        return players

    def get_free_agents(
        self,
        sort_by: str = "PTS",
        position: str | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Get available free agents sorted by a specific category."""
        stat_id = self._get_stat_id(sort_by)

        # Build URL for free agents
        url = f"{self.BASE_URL}/league/{self.league_key}/players;status=FA;sort={stat_id};sort_type=season;count={limit}/stats"
        if position:
            url = f"{self.BASE_URL}/league/{self.league_key}/players;status=FA;position={position.upper()};sort={stat_id};sort_type=season;count={limit}/stats"

        data = self._get_response_json(url)

        fantasy_content = data.get("fantasy_content", {})
        league = fantasy_content.get("league", [])

        free_agents = []
        if len(league) > 1:
            players_container = league[1].get("players", {})
            for key, value in players_container.items():
                if key == "count":
                    continue
                player_info = value.get("player", [])
                if player_info:
                    player_data = self._parse_player_from_api(player_info)
                    free_agents.append(player_data)

        return {
            "sort_by": sort_by,
            "position_filter": position,
            "count": len(free_agents),
            "players": free_agents,
        }

    def get_streaming_options(
        self,
        sort_by: str = "PTS",
        position: str | None = None,
        min_games: int = 3,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Get free agents optimized for streaming with remaining games info.

        This combines free agent data with NBA schedule to help identify
        the best streaming pickups based on remaining games this week.

        Args:
            sort_by: Category to sort by (PTS, AST, REB, STL, BLK, 3PTM, FG%, FT%, TO)
            position: Filter by position (PG, SG, SF, PF, C, G, F, UTIL)
            min_games: Minimum remaining games to include (default 3)
            limit: Maximum number of players to return (default 25)

        Returns:
            Free agents with remaining games info, sorted by games then by stat.
        """
        # Get current week dates
        week = self.get_current_week()
        matchup_data = self.get_weekly_matchup(week)
        week_end_str = matchup_data.get("week_end", "")

        # Calculate remaining games date range
        today = date.today()
        try:
            week_end = datetime.strptime(week_end_str, "%Y-%m-%d").date()
        except ValueError:
            week_end = today + timedelta(days=7)

        # Get NBA schedule
        schedule_data = get_team_games_in_range(today, week_end)
        games_by_date = get_games_by_date(today, week_end)

        # Get team games played this season (for calculating per-game averages)
        team_gp = get_team_games_played()

        # Get free agents
        fa_data = self.get_free_agents(sort_by, position, limit * 2)  # Get more to filter

        # Add remaining games and calculate averages for each player
        players_with_games = []
        counting_stats = ["PTS", "REB", "AST", "ST", "BLK", "TO", "3PTM", "OREB", "DREB", "PF"]

        for player in fa_data.get("players", []):
            player_team = player.get("team", "")
            team_games = schedule_data.get(player_team, [])
            remaining_games = len(team_games)

            if remaining_games >= min_games:
                player["remaining_games"] = remaining_games
                player["game_dates"] = [g["date"] for g in team_games]

                # Calculate per-game averages using team's games played
                gp = team_gp.get(player_team, 45)  # Default to 45 if not found
                stats = player.get("stats", {})
                averages = {}
                for stat_name in counting_stats:
                    if stat_name in stats and gp > 0:
                        averages[stat_name] = round(stats[stat_name] / gp, 1)
                # Copy percentage stats as-is
                for pct_stat in ["FG%", "FT%", "3PT%"]:
                    if pct_stat in stats:
                        averages[pct_stat] = stats[pct_stat]
                player["averages"] = averages
                player["team_gp"] = gp

                players_with_games.append(player)

        # Sort by remaining games (descending), then by per-game stat (using averages)
        stat_key = sort_by
        players_with_games.sort(
            key=lambda p: (
                -p.get("remaining_games", 0),
                -p.get("averages", {}).get(stat_key, p.get("stats", {}).get(stat_key, 0)),
            )
        )

        # Limit results
        players_with_games = players_with_games[:limit]

        # Get teams with most games this week
        team_game_counts = {
            team: len(games) for team, games in schedule_data.items()
        }
        top_teams = sorted(team_game_counts.items(), key=lambda x: -x[1])[:10]

        return {
            "week": week,
            "remaining_from": today.isoformat(),
            "week_end": week_end_str,
            "sort_by": sort_by,
            "min_games_filter": min_games,
            "position_filter": position,
            "games_by_date": games_by_date,
            "top_teams_by_games": top_teams,
            "count": len(players_with_games),
            "players": players_with_games,
        }

    def get_player_stats(self, player_name: str) -> dict[str, Any]:
        """Get detailed stats for a specific player by searching."""
        # Search for the player using Yahoo's search
        search_query = player_name.replace(" ", "+")
        url = f"{self.BASE_URL}/league/{self.league_key}/players;search={search_query}/stats"

        try:
            data = self._get_response_json(url)
        except Exception:
            return {"error": f"Player '{player_name}' not found"}

        fantasy_content = data.get("fantasy_content", {})
        league = fantasy_content.get("league", [])

        if len(league) > 1:
            players_container = league[1].get("players", {})
            for key, value in players_container.items():
                if key == "count":
                    continue
                player_info = value.get("player", [])
                if player_info:
                    player_data = self._parse_player_from_api(player_info, detailed=True)
                    return player_data

        return {"error": f"Player '{player_name}' not found"}

    def get_league_standings(self) -> dict[str, Any]:
        """Get current league standings."""
        standings = self.query.get_league_standings()

        teams = []
        for team in standings.teams:
            team_standings = getattr(team, "team_standings", None)
            outcome_totals = getattr(team_standings, "outcome_totals", None) if team_standings else None

            teams.append({
                "team_id": str(getattr(team, "team_id", "")),
                "team_name": self._decode_string(getattr(team, "name", "Unknown")),
                "rank": int(getattr(team_standings, "rank", 0)) if team_standings else 0,
                "wins": int(getattr(outcome_totals, "wins", 0)) if outcome_totals else 0,
                "losses": int(getattr(outcome_totals, "losses", 0)) if outcome_totals else 0,
                "ties": int(getattr(outcome_totals, "ties", 0)) if outcome_totals else 0,
                "points_for": float(getattr(team_standings, "points_for", 0)) if team_standings else 0,
                "points_against": float(getattr(team_standings, "points_against", 0)) if team_standings else 0,
            })

        teams.sort(key=lambda x: x["rank"])

        return {
            "standings": teams,
            "my_team_id": self.get_my_team_id(),
        }

    def get_all_teams(self) -> dict[str, Any]:
        """Get all teams in the league with basic info."""
        teams = self.query.get_league_teams()
        my_team_id = self.get_my_team_id()

        team_list = []
        for team in teams:
            team_id = str(getattr(team, "team_id", ""))

            # Get manager name safely
            manager_name = ""
            if hasattr(team, "managers") and team.managers:
                first_manager = team.managers[0]
                manager_name = self._decode_string(getattr(first_manager, "nickname", ""))

            team_list.append({
                "team_id": team_id,
                "team_name": self._decode_string(getattr(team, "name", "Unknown")),
                "manager": manager_name,
                "is_my_team": team_id == my_team_id,
            })

        return {
            "teams": team_list,
            "my_team_id": my_team_id,
        }

    def get_team_roster(self, team_id: str) -> dict[str, Any]:
        """Get any team's roster with player stats.

        Args:
            team_id: The team ID to get roster for
        """
        team_key = f"{self.league_key}.t.{team_id}"

        # Get roster with player season stats
        url = f"{self.BASE_URL}/team/{team_key}/roster/players/stats;type=season"
        data = self._get_response_json(url)

        fantasy_content = data.get("fantasy_content", {})
        team_data = fantasy_content.get("team", [])

        team_name = ""
        players = []

        if team_data:
            # Extract team name
            for item in team_data[0]:
                if isinstance(item, dict) and "name" in item:
                    team_name = self._decode_string(item["name"])

            # Extract players
            if len(team_data) > 1:
                roster = team_data[1].get("roster", {})
                players_container = roster.get("0", {}).get("players", {})

                # Get team games played for averages
                team_gp = get_team_games_played()

                for key, value in players_container.items():
                    if key == "count":
                        continue
                    player_info = value.get("player", [])
                    if player_info:
                        player_data = self._parse_player_from_api(player_info)

                        # Calculate averages
                        player_team = player_data.get("team", "")
                        gp = team_gp.get(player_team, 45)
                        stats = player_data.get("stats", {})
                        counting_stats = ["PTS", "REB", "AST", "ST", "BLK", "TO", "3PTM"]
                        averages = {}
                        for stat_name in counting_stats:
                            if stat_name in stats and gp > 0:
                                averages[stat_name] = round(stats[stat_name] / gp, 1)
                        for pct_stat in ["FG%", "FT%"]:
                            if pct_stat in stats:
                                averages[pct_stat] = stats[pct_stat]
                        player_data["averages"] = averages
                        players.append(player_data)

        return {
            "team_id": team_id,
            "team_name": team_name,
            "player_count": len(players),
            "players": players,
        }

    def compare_with_team(self, team_id: str) -> dict[str, Any]:
        """Compare my team's season stats with another team.

        Args:
            team_id: The team ID to compare against

        Returns:
            Comparison showing which categories each team is stronger in,
            with Z-scores and league rankings for context.
        """
        my_team_id = self.get_my_team_id()

        # Get league-wide Z-scores for context
        league_data = self._calculate_league_zscores()
        team_zscores = league_data["team_zscores"]
        league_stats = league_data["league_stats"]

        if my_team_id not in team_zscores or team_id not in team_zscores:
            return {"error": "Could not find team data"}

        my_data = team_zscores[my_team_id]
        other_data = team_zscores[team_id]

        # Get scoring categories
        categories = self.get_scoring_categories()

        # Compare categories
        comparison = []
        my_wins = 0
        other_wins = 0

        for stat_id, (stat_name, sort_order) in categories.items():
            my_val = my_data["stats"].get(stat_name, 0)
            other_val = other_data["stats"].get(stat_name, 0)
            my_z = my_data["zscores"].get(stat_name, 0)
            other_z = other_data["zscores"].get(stat_name, 0)
            my_rank = my_data["rankings"].get(stat_name, 0)
            other_rank = other_data["rankings"].get(stat_name, 0)

            # Determine winner (sort_order: 1 = higher is better, 0 = lower is better)
            if sort_order == 1:
                winner = "me" if my_val > other_val else ("them" if other_val > my_val else "tie")
            else:
                winner = "me" if my_val < other_val else ("them" if other_val < my_val else "tie")

            if winner == "me":
                my_wins += 1
            elif winner == "them":
                other_wins += 1

            comparison.append({
                "category": stat_name,
                "my_value": round(my_val, 3),
                "my_z": my_z,
                "my_rank": my_rank,
                "their_value": round(other_val, 3),
                "their_z": other_z,
                "their_rank": other_rank,
                "winner": winner,
                "higher_is_better": sort_order == 1,
            })

        # Sort comparison by my Z-score (show my strengths first)
        comparison.sort(key=lambda x: x["my_z"], reverse=True)

        return {
            "my_team": {
                "team_id": my_team_id,
                "team_name": my_data["name"],
                "total_z": my_data["total_z"],
            },
            "other_team": {
                "team_id": team_id,
                "team_name": other_data["name"],
                "total_z": other_data["total_z"],
            },
            "score": f"{my_wins}-{other_wins}",
            "comparison": comparison,
            "analysis": {
                "my_strengths": [c["category"] for c in comparison if c["winner"] == "me"],
                "their_strengths": [c["category"] for c in comparison if c["winner"] == "them"],
                "trade_suggestion": self._suggest_trade(comparison),
            },
        }

    def _suggest_trade(self, comparison: list[dict]) -> str:
        """Generate a trade suggestion based on category comparison."""
        my_strong = [c["category"] for c in comparison if c["my_z"] >= 0.5 and c["their_z"] <= 0]
        they_strong = [c["category"] for c in comparison if c["their_z"] >= 0.5 and c["my_z"] <= 0]

        if my_strong and they_strong:
            return f"考慮用你的 {', '.join(my_strong[:2])} 換他的 {', '.join(they_strong[:2])}"
        return ""

    def _extract_team_stats(self, data: dict) -> tuple[str, dict[str, float]]:
        """Extract team name and stats from API response."""
        fantasy_content = data.get("fantasy_content", {})
        team = fantasy_content.get("team", [])

        team_name = ""
        stats = {}

        if team:
            # Get team name
            for item in team[0]:
                if isinstance(item, dict) and "name" in item:
                    team_name = self._decode_string(item["name"])

            if len(team) > 1:
                team_stats = team[1].get("team_stats", {})
                stats_list = team_stats.get("stats", [])
                for stat_entry in stats_list:
                    stat = stat_entry.get("stat", {})
                    stat_id = str(stat.get("stat_id", ""))
                    value = stat.get("value", "")
                    stat_name = self._get_stat_name(stat_id)
                    if stat_name:
                        stats[stat_name] = self._parse_stat_value(value)

        return team_name, stats

    def get_category_analysis(self) -> dict[str, Any]:
        """Analyze team's category strengths across the season."""
        team_id = self.get_my_team_id()
        team_key = f"{self.league_key}.t.{team_id}"

        # Get my team's season stats
        url = f"{self.BASE_URL}/team/{team_key}/stats"
        data = self._get_response_json(url)

        fantasy_content = data.get("fantasy_content", {})
        team = fantasy_content.get("team", [])

        my_stats = {}
        if len(team) > 1:
            team_stats = team[1].get("team_stats", {})
            stats_list = team_stats.get("stats", [])
            for stat_entry in stats_list:
                stat = stat_entry.get("stat", {})
                stat_id = str(stat.get("stat_id", ""))
                value = stat.get("value", "")
                stat_name = self._get_stat_name(stat_id)
                if stat_name:
                    my_stats[stat_name] = self._parse_stat_value(value)

        # Get all teams' season stats for league average
        league_totals: dict[str, list[float]] = {}
        teams = self.query.get_league_teams()

        for t in teams:
            t_id = str(getattr(t, "team_id", ""))
            t_key = f"{self.league_key}.t.{t_id}"
            url = f"{self.BASE_URL}/team/{t_key}/stats"

            try:
                data = self._get_response_json(url)
                fantasy_content = data.get("fantasy_content", {})
                team_data = fantasy_content.get("team", [])

                if len(team_data) > 1:
                    team_stats = team_data[1].get("team_stats", {})
                    stats_list = team_stats.get("stats", [])
                    for stat_entry in stats_list:
                        stat = stat_entry.get("stat", {})
                        stat_id = str(stat.get("stat_id", ""))
                        value = stat.get("value", "")
                        stat_name = self._get_stat_name(stat_id)
                        if stat_name:
                            if stat_name not in league_totals:
                                league_totals[stat_name] = []
                            league_totals[stat_name].append(self._parse_stat_value(value))
            except Exception:
                continue

        league_avg = {k: sum(v) / len(v) if v else 0 for k, v in league_totals.items()}

        # Get scoring categories to determine which stats matter
        categories = self.get_scoring_categories()
        scoring_stats = {name for _, (name, _) in categories.items()}

        # Categorize strengths/weaknesses
        strengths = []
        weaknesses = []
        average = []

        for stat_name, value in my_stats.items():
            if stat_name not in scoring_stats:
                continue
            if stat_name not in league_avg or league_avg[stat_name] == 0:
                continue

            # Find sort order for this stat
            sort_order = 1
            for stat_id, (name, order) in categories.items():
                if name == stat_name:
                    sort_order = order
                    break

            # Calculate ratio based on sort order
            if sort_order == 0:  # Lower is better (TO, PF)
                ratio = league_avg[stat_name] / value if value > 0 else 1
            else:
                ratio = value / league_avg[stat_name]

            item = {
                "stat": stat_name,
                "value": value,
                "league_avg": round(league_avg[stat_name], 3),
                "difference_pct": round((ratio - 1) * 100, 1),
            }

            if ratio > 1.1:
                strengths.append(item)
            elif ratio < 0.9:
                weaknesses.append(item)
            else:
                average.append(item)

        return {
            "my_stats": my_stats,
            "league_average": league_avg,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "average": average,
        }

    def _get_all_teams_stats(self) -> dict[str, dict[str, float]]:
        """Get all teams' season stats. Returns dict of team_id -> stats."""
        teams = self.query.get_league_teams()
        all_stats = {}

        for t in teams:
            t_id = str(getattr(t, "team_id", ""))
            t_name = self._decode_string(getattr(t, "name", "Unknown"))
            t_key = f"{self.league_key}.t.{t_id}"
            url = f"{self.BASE_URL}/team/{t_key}/stats"

            try:
                data = self._get_response_json(url)
                _, stats = self._extract_team_stats(data)
                all_stats[t_id] = {"name": t_name, "stats": stats}
            except Exception:
                continue

        return all_stats

    def _calculate_league_zscores(
        self, punt_categories: list[str] | None = None
    ) -> dict[str, Any]:
        """Calculate Z-scores for all teams in the league.

        Args:
            punt_categories: Categories to exclude from total Z-score calculation

        Returns:
            Dict with league stats, team Z-scores, and rankings.
        """
        punt_categories = punt_categories or []

        # Get all teams' stats
        all_teams_stats = self._get_all_teams_stats()

        # Get scoring categories
        categories = self.get_scoring_categories()

        # Collect values for each category
        category_values: dict[str, list[tuple[str, float]]] = {}
        for team_id, team_data in all_teams_stats.items():
            stats = team_data["stats"]
            for stat_id, (stat_name, sort_order) in categories.items():
                if stat_name in stats:
                    if stat_name not in category_values:
                        category_values[stat_name] = []
                    category_values[stat_name].append((team_id, stats[stat_name]))

        # Calculate mean and stdev for each category
        league_stats = {}
        for stat_name, values in category_values.items():
            vals = [v[1] for v in values]
            if len(vals) >= 2:
                league_stats[stat_name] = {
                    "mean": mean(vals),
                    "stdev": stdev(vals) if len(vals) > 1 else 1,
                    "min": min(vals),
                    "max": max(vals),
                }

        # Calculate Z-scores for each team
        team_zscores = {}
        for team_id, team_data in all_teams_stats.items():
            stats = team_data["stats"]
            zscores = {}
            total_z = 0

            for stat_id, (stat_name, sort_order) in categories.items():
                if stat_name not in stats or stat_name not in league_stats:
                    continue

                value = stats[stat_name]
                cat_mean = league_stats[stat_name]["mean"]
                cat_stdev = league_stats[stat_name]["stdev"]

                if cat_stdev == 0:
                    z = 0
                else:
                    z = (value - cat_mean) / cat_stdev
                    # For negative categories (TO), flip the sign
                    if sort_order == 0:
                        z = -z

                zscores[stat_name] = round(z, 2)

                # Add to total if not punting this category
                if stat_name not in punt_categories:
                    total_z += z

            team_zscores[team_id] = {
                "name": team_data["name"],
                "zscores": zscores,
                "total_z": round(total_z, 2),
                "stats": stats,
            }

        # Calculate rankings for each category
        rankings = {}
        for stat_id, (stat_name, sort_order) in categories.items():
            if stat_name not in league_stats:
                continue

            # Sort teams by this category's Z-score
            sorted_teams = sorted(
                team_zscores.items(),
                key=lambda x: x[1]["zscores"].get(stat_name, 0),
                reverse=True,
            )
            for rank, (team_id, _) in enumerate(sorted_teams, 1):
                if team_id not in rankings:
                    rankings[team_id] = {}
                rankings[team_id][stat_name] = rank

        # Add rankings to team data
        for team_id in team_zscores:
            team_zscores[team_id]["rankings"] = rankings.get(team_id, {})

        return {
            "league_stats": league_stats,
            "team_zscores": team_zscores,
            "categories": {stat_id: name for stat_id, (name, _) in categories.items()},
        }

    def get_team_zscores(
        self, punt_categories: list[str] | None = None
    ) -> dict[str, Any]:
        """Get my team's Z-scores for each category.

        Args:
            punt_categories: Categories to exclude (e.g., ["FT%", "TO"] for punt FT/TO build)

        Returns:
            Z-scores for each category, league rank, and total Z-score.
        """
        punt_categories = punt_categories or []
        my_team_id = self.get_my_team_id()

        # Calculate league-wide Z-scores
        league_data = self._calculate_league_zscores(punt_categories)
        team_zscores = league_data["team_zscores"]
        league_stats = league_data["league_stats"]

        if my_team_id not in team_zscores:
            return {"error": "Could not find my team"}

        my_data = team_zscores[my_team_id]

        # Sort by total Z to get overall rank
        sorted_by_total = sorted(
            team_zscores.items(),
            key=lambda x: x[1]["total_z"],
            reverse=True,
        )
        overall_rank = next(
            (i for i, (tid, _) in enumerate(sorted_by_total, 1) if tid == my_team_id),
            0,
        )

        # Format category details
        category_details = []
        for stat_name, z in my_data["zscores"].items():
            is_punted = stat_name in punt_categories
            category_details.append({
                "category": stat_name,
                "value": my_data["stats"].get(stat_name, 0),
                "z_score": z,
                "league_rank": my_data["rankings"].get(stat_name, 0),
                "league_mean": round(league_stats.get(stat_name, {}).get("mean", 0), 2),
                "league_stdev": round(league_stats.get(stat_name, {}).get("stdev", 0), 2),
                "punted": is_punted,
            })

        # Sort by Z-score descending
        category_details.sort(key=lambda x: x["z_score"], reverse=True)

        return {
            "team_name": my_data["name"],
            "total_z": my_data["total_z"],
            "overall_rank": overall_rank,
            "total_teams": len(team_zscores),
            "punt_categories": punt_categories,
            "categories": category_details,
            "strengths": [c for c in category_details if c["z_score"] >= 0.5 and not c["punted"]],
            "weaknesses": [c for c in category_details if c["z_score"] <= -0.5 and not c["punted"]],
        }

    def get_league_zscores(
        self, punt_categories: list[str] | None = None
    ) -> dict[str, Any]:
        """Get Z-scores for all teams in the league.

        Args:
            punt_categories: Categories to exclude from total Z-score

        Returns:
            All teams ranked by total Z-score with category breakdown.
        """
        punt_categories = punt_categories or []
        my_team_id = self.get_my_team_id()

        league_data = self._calculate_league_zscores(punt_categories)
        team_zscores = league_data["team_zscores"]

        # Sort by total Z-score
        sorted_teams = sorted(
            team_zscores.items(),
            key=lambda x: x[1]["total_z"],
            reverse=True,
        )

        teams_list = []
        for rank, (team_id, data) in enumerate(sorted_teams, 1):
            teams_list.append({
                "rank": rank,
                "team_id": team_id,
                "team_name": data["name"],
                "total_z": data["total_z"],
                "zscores": data["zscores"],
                "is_my_team": team_id == my_team_id,
            })

        return {
            "punt_categories": punt_categories,
            "teams": teams_list,
            "league_stats": league_data["league_stats"],
        }

    def _parse_player_from_api(self, player_info: list, detailed: bool = False) -> dict[str, Any]:
        """Parse player data from Yahoo API response."""
        player_data: dict[str, Any] = {
            "player_id": "",
            "name": "",
            "team": "",
            "positions": [],
            "status": "",
            "stats": {},
        }

        if not player_info:
            return player_data

        # First element contains player metadata (as a list)
        if isinstance(player_info[0], list):
            for item in player_info[0]:
                if isinstance(item, dict):
                    if "player_id" in item:
                        player_data["player_id"] = str(item["player_id"])
                    if "name" in item:
                        name_obj = item["name"]
                        if isinstance(name_obj, dict):
                            player_data["name"] = name_obj.get("full", "")
                        else:
                            player_data["name"] = self._decode_string(name_obj)
                    if "editorial_team_abbr" in item:
                        player_data["team"] = item["editorial_team_abbr"]
                    if "display_position" in item:
                        player_data["positions"] = item["display_position"].split(",")
                    if "status" in item:
                        player_data["status"] = item["status"]
                    if "status_full" in item:
                        player_data["status_full"] = item["status_full"]
                    if "injury_note" in item and detailed:
                        player_data["injury_note"] = item["injury_note"]
                    if "percent_owned" in item and detailed:
                        player_data["percent_owned"] = item["percent_owned"]
                    if "eligible_positions" in item:
                        positions = item["eligible_positions"]
                        if isinstance(positions, list):
                            player_data["positions"] = [
                                p.get("position", "") if isinstance(p, dict) else str(p)
                                for p in positions
                            ]

        # Search for player_stats in remaining elements (could be in any position)
        for element in player_info[1:]:
            if isinstance(element, dict) and "player_stats" in element:
                player_stats = element.get("player_stats", {})
                stats_list = player_stats.get("stats", [])
                stats = {}
                for stat_entry in stats_list:
                    stat = stat_entry.get("stat", {})
                    stat_id = str(stat.get("stat_id", ""))
                    value = stat.get("value", "")
                    stat_name = self._get_stat_name(stat_id)
                    if stat_name:
                        stats[stat_name] = self._parse_stat_value(value)
                player_data["stats"] = stats
                break

        return player_data

    def _get_stat_name(self, stat_id: str) -> str | None:
        """Map Yahoo stat ID to human-readable name."""
        stat_map = {
            "0": "GP",
            "1": "GS",
            "2": "MIN",
            "3": "FGA",
            "4": "FGM",
            "5": "FG%",
            "6": "FTA",
            "7": "FTM",
            "8": "FT%",
            "9": "3PTA",
            "10": "3PTM",
            "11": "3PT%",
            "12": "PTS",
            "13": "OREB",
            "14": "DREB",
            "15": "REB",
            "16": "AST",
            "17": "ST",
            "18": "BLK",
            "19": "TO",
            "20": "A/T",
            "21": "PF",
            "22": "DISQ",
            "23": "TECH",
            "24": "EJCT",
            "25": "FF",
            "26": "MPG",
            "27": "DD",
            "28": "TD",
        }
        return stat_map.get(stat_id)

    def _get_stat_id(self, stat_name: str) -> str:
        """Map stat name to Yahoo stat ID."""
        name_map = {
            "PTS": "12",
            "REB": "15",
            "AST": "16",
            "ST": "17",
            "STL": "17",
            "BLK": "18",
            "TO": "19",
            "FG%": "5",
            "FT%": "8",
            "3PTM": "10",
            "3PM": "10",
            "OREB": "13",
            "PF": "21",
        }
        return name_map.get(stat_name.upper(), "12")

    def _parse_stat_value(self, value: Any) -> float:
        """Parse a stat value to float."""
        if value is None or value == "-" or value == "":
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0
