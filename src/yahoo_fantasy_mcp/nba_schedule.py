"""NBA Schedule fetcher using NBA.com CDN API."""

from datetime import datetime, date
from functools import lru_cache
from typing import Any

import requests


# Mapping from NBA team tricodes to Yahoo Fantasy abbreviations
NBA_TO_YAHOO_TEAM = {
    "ATL": "ATL",
    "BOS": "BOS",
    "BKN": "BKN",
    "CHA": "CHA",
    "CHI": "CHI",
    "CLE": "CLE",
    "DAL": "DAL",
    "DEN": "DEN",
    "DET": "DET",
    "GSW": "GS",   # Golden State
    "HOU": "HOU",
    "IND": "IND",
    "LAC": "LAC",
    "LAL": "LAL",
    "MEM": "MEM",
    "MIA": "MIA",
    "MIL": "MIL",
    "MIN": "MIN",
    "NOP": "NO",   # New Orleans
    "NYK": "NY",   # New York
    "OKC": "OKC",
    "ORL": "ORL",
    "PHI": "PHI",
    "PHX": "PHX",
    "POR": "POR",
    "SAC": "SAC",
    "SAS": "SA",   # San Antonio
    "TOR": "TOR",
    "UTA": "UTA",
    "WAS": "WAS",
}

# Reverse mapping for lookup
YAHOO_TO_NBA_TEAM = {v: k for k, v in NBA_TO_YAHOO_TEAM.items()}

# NBA Schedule API URL
NBA_SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"


@lru_cache(maxsize=1)
def _fetch_nba_schedule() -> list[dict[str, Any]]:
    """Fetch full NBA season schedule from NBA.com CDN (cached)."""
    try:
        response = requests.get(NBA_SCHEDULE_URL, timeout=15)
        response.raise_for_status()
        data = response.json()

        schedule = data.get("leagueSchedule", {})
        game_dates = schedule.get("gameDates", [])

        all_games = []
        for game_date_info in game_dates:
            date_str = game_date_info.get("gameDate", "")
            try:
                # Parse date format: '01/29/2026 00:00:00'
                game_date = datetime.strptime(date_str, "%m/%d/%Y %H:%M:%S").date()
            except ValueError:
                continue

            games = game_date_info.get("games", [])
            for game in games:
                home_team = game.get("homeTeam", {}).get("teamTricode", "")
                away_team = game.get("awayTeam", {}).get("teamTricode", "")

                if home_team and away_team:
                    # Add entry for home team
                    all_games.append({
                        "date": game_date,
                        "team": home_team,
                        "opponent": away_team,
                        "home": True,
                        "matchup": f"{home_team} vs {away_team}",
                    })
                    # Add entry for away team
                    all_games.append({
                        "date": game_date,
                        "team": away_team,
                        "opponent": home_team,
                        "home": False,
                        "matchup": f"{away_team} @ {home_team}",
                    })

        return all_games
    except Exception:
        return []


def clear_schedule_cache() -> None:
    """Clear the cached schedule data (useful for refreshing)."""
    _fetch_nba_schedule.cache_clear()


def get_team_games_in_range(
    start_date: date,
    end_date: date,
    team_abbr: str | None = None,
) -> dict[str, list[dict]]:
    """
    Get games for each team within a date range.

    Args:
        start_date: Start date of the range
        end_date: End date of the range
        team_abbr: Optional Yahoo team abbreviation to filter for specific team

    Returns:
        Dict mapping Yahoo team abbreviation to list of games
    """
    all_games = _fetch_nba_schedule()

    team_games: dict[str, list[dict]] = {}

    for game in all_games:
        game_date = game["date"]
        if start_date <= game_date <= end_date:
            nba_team = game["team"]
            yahoo_team = NBA_TO_YAHOO_TEAM.get(nba_team, nba_team)

            if team_abbr and yahoo_team != team_abbr:
                continue

            if yahoo_team not in team_games:
                team_games[yahoo_team] = []

            team_games[yahoo_team].append({
                "date": game_date.isoformat(),
                "matchup": game["matchup"],
                "home": game["home"],
            })

    # Sort games by date for each team
    for team in team_games:
        team_games[team].sort(key=lambda x: x["date"])

    return team_games


def get_remaining_games_count(
    start_date: date,
    end_date: date,
) -> dict[str, int]:
    """
    Get remaining game count for each team within a date range.

    Args:
        start_date: Start date (typically today)
        end_date: End date of the fantasy week

    Returns:
        Dict mapping Yahoo team abbreviation to number of remaining games
    """
    team_games = get_team_games_in_range(start_date, end_date)
    return {team: len(games) for team, games in team_games.items()}


def get_team_games_played(team_abbr: str | None = None) -> dict[str, int]:
    """
    Get number of games each team has played so far this season.

    Args:
        team_abbr: Optional Yahoo team abbreviation to filter for specific team

    Returns:
        Dict mapping Yahoo team abbreviation to number of games played
    """
    all_games = _fetch_nba_schedule()
    today = date.today()

    team_games_played: dict[str, int] = {}

    for game in all_games:
        game_date = game["date"]
        # Only count games that have already been played (before today)
        if game_date < today:
            nba_team = game["team"]
            yahoo_team = NBA_TO_YAHOO_TEAM.get(nba_team, nba_team)

            if team_abbr and yahoo_team != team_abbr:
                continue

            team_games_played[yahoo_team] = team_games_played.get(yahoo_team, 0) + 1

    return team_games_played


def get_games_by_date(
    start_date: date,
    end_date: date,
) -> dict[str, list[str]]:
    """
    Get which teams play on each date.

    Args:
        start_date: Start date of the range
        end_date: End date of the range

    Returns:
        Dict mapping date string (YYYY-MM-DD) to list of Yahoo team abbreviations
    """
    team_games = get_team_games_in_range(start_date, end_date)

    date_teams: dict[str, list[str]] = {}

    for team, games in team_games.items():
        for game in games:
            game_date = game["date"]
            if game_date not in date_teams:
                date_teams[game_date] = []
            if team not in date_teams[game_date]:
                date_teams[game_date].append(team)

    # Sort dates and teams
    return {k: sorted(date_teams[k]) for k in sorted(date_teams.keys())}
