"""Configuration management for Yahoo Fantasy MCP Server."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class YahooConfig:
    """Yahoo Fantasy API configuration."""

    consumer_key: str
    consumer_secret: str
    league_id: str
    team_id: str | None
    game_code: str
    data_dir: Path

    @classmethod
    def from_env(cls) -> "YahooConfig":
        """Load configuration from environment variables."""
        load_dotenv()

        consumer_key = os.getenv("YAHOO_CONSUMER_KEY")
        consumer_secret = os.getenv("YAHOO_CONSUMER_SECRET")
        league_id = os.getenv("YAHOO_LEAGUE_ID")

        if not consumer_key or not consumer_secret:
            raise ValueError(
                "YAHOO_CONSUMER_KEY and YAHOO_CONSUMER_SECRET must be set. "
                "Get these from https://developer.yahoo.com/apps/"
            )

        if not league_id:
            raise ValueError(
                "YAHOO_LEAGUE_ID must be set. "
                "Find it in your league URL: https://basketball.fantasysports.yahoo.com/nba/{league_id}"
            )

        team_id = os.getenv("YAHOO_TEAM_ID") or None
        game_code = os.getenv("YAHOO_GAME_CODE", "nba")

        # Store OAuth tokens in the project directory
        data_dir = Path(__file__).parent.parent.parent / ".yahoo_data"
        data_dir.mkdir(exist_ok=True)

        return cls(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            league_id=league_id,
            team_id=team_id,
            game_code=game_code,
            data_dir=data_dir,
        )
