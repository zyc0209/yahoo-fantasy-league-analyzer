"""MCP Server for Yahoo Fantasy Basketball."""

from mcp.server.fastmcp import FastMCP

from .config import YahooConfig
from .yahoo_client import YahooFantasyClient

# Initialize MCP server
mcp = FastMCP("yahoo-fantasy-basketball")

# Global client instance (initialized on first use)
_client: YahooFantasyClient | None = None


def get_client() -> YahooFantasyClient:
    """Get or create the Yahoo Fantasy client."""
    global _client
    if _client is None:
        config = YahooConfig.from_env()
        _client = YahooFantasyClient(config)
    return _client


@mcp.tool()
def get_my_team() -> dict:
    """Get my team roster and player information.

    Returns the authenticated user's team with all players,
    their positions, and current stats.
    """
    client = get_client()
    return client.get_my_team()


@mcp.tool()
def get_weekly_matchup(week: int | None = None) -> dict:
    """Get the weekly head-to-head matchup with 9-cat comparison.

    Args:
        week: The week number (defaults to current week)

    Returns:
        My team stats, opponent stats, and comparison showing
        which categories I'm winning, losing, or close in.
    """
    client = get_client()
    return client.get_weekly_matchup(week)


@mcp.tool()
def get_remaining_games(week: int | None = None) -> dict:
    """Get remaining games this week for my team and opponent.

    Args:
        week: The week number (defaults to current week)

    Returns:
        Remaining games for each player on both teams,
        useful for streaming decisions.
    """
    client = get_client()
    return client.get_remaining_games(week)


@mcp.tool()
def get_free_agents(
    sort_by: str = "PTS",
    position: str | None = None,
    limit: int = 25,
) -> dict:
    """Get available free agents from the waiver wire.

    Args:
        sort_by: Category to sort by (PTS, AST, REB, STL, BLK, 3PTM, FG%, FT%, TO)
        position: Filter by position (PG, SG, SF, PF, C, G, F, UTIL)
        limit: Maximum number of players to return (default 25)

    Returns:
        List of available free agents with their stats,
        sorted by the specified category.
    """
    client = get_client()
    return client.get_free_agents(sort_by, position, limit)


@mcp.tool()
def get_streaming_options(
    sort_by: str = "PTS",
    position: str | None = None,
    min_games: int = 3,
    limit: int = 25,
) -> dict:
    """Get best streaming pickup options based on remaining games this week.

    Combines free agent data with NBA schedule to find players with
    the most remaining games. Perfect for streaming decisions.

    Args:
        sort_by: Category to sort by (PTS, AST, REB, STL, BLK, 3PTM, FG%, FT%, TO)
        position: Filter by position (PG, SG, SF, PF, C, G, F, UTIL)
        min_games: Minimum remaining games to include (default 3)
        limit: Maximum number of players to return (default 25)

    Returns:
        Free agents with remaining games info, sorted by games count,
        plus a schedule showing which teams play each day.
    """
    client = get_client()
    return client.get_streaming_options(sort_by, position, min_games, limit)


@mcp.tool()
def get_player_stats(player_name: str) -> dict:
    """Get detailed statistics for a specific player.

    Args:
        player_name: The player's name (partial match supported)

    Returns:
        Player's detailed stats, injury status, and ownership info.
    """
    client = get_client()
    return client.get_player_stats(player_name)


@mcp.tool()
def get_league_standings() -> dict:
    """Get current league standings.

    Returns:
        All teams ranked by their record, including
        wins, losses, ties, and points.
    """
    client = get_client()
    return client.get_league_standings()


@mcp.tool()
def get_all_teams() -> dict:
    """Get all teams in the league.

    Returns:
        List of all teams with their team_id and team_name.
        Use team_id to view their roster or compare stats.
    """
    client = get_client()
    return client.get_all_teams()


@mcp.tool()
def get_team_roster(team_id: str) -> dict:
    """Get any team's roster in the league.

    Args:
        team_id: The team ID (get from get_all_teams or get_league_standings)

    Returns:
        The team's full roster with player stats and per-game averages.
        Useful for scouting other teams' players for trades.
    """
    client = get_client()
    return client.get_team_roster(team_id)


@mcp.tool()
def compare_with_team(team_id: str) -> dict:
    """Compare my team's season stats with another team.

    Args:
        team_id: The team ID to compare against

    Returns:
        Category-by-category comparison with Z-scores and league rankings.
        Includes trade suggestions based on complementary strengths.
    """
    client = get_client()
    return client.compare_with_team(team_id)


@mcp.tool()
def get_team_zscores(punt_categories: list[str] | None = None) -> dict:
    """Get my team's Z-scores for each category.

    Z-score shows how many standard deviations above/below league average:
    - Z = 0: League average
    - Z = +1: Top ~16% (strong category)
    - Z = -1: Bottom ~16% (weak category)

    Args:
        punt_categories: Categories to exclude from total (e.g., ["FT%", "TO"])

    Returns:
        Z-scores, league rank, and total Z for each category.
        Perfect for identifying punt strategies and trade targets.
    """
    client = get_client()
    return client.get_team_zscores(punt_categories)


@mcp.tool()
def get_league_zscores(punt_categories: list[str] | None = None) -> dict:
    """Get Z-scores for all teams in the league, ranked by total value.

    Args:
        punt_categories: Categories to exclude from total Z-score

    Returns:
        All teams ranked by total Z-score with category breakdown.
        Useful for identifying the strongest teams and their builds.
    """
    client = get_client()
    return client.get_league_zscores(punt_categories)


@mcp.tool()
def get_category_analysis() -> dict:
    """Analyze my team's category strengths and weaknesses across the season.

    Returns:
        My stats compared to league average, categorized into
        strengths, weaknesses, and average categories.
        Useful for identifying punt strategies and trade targets.
    """
    client = get_client()
    return client.get_category_analysis()


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
