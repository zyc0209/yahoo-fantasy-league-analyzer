from yahoo_fantasy_mcp.config import YahooConfig
from yahoo_fantasy_mcp.yahoo_client import YahooFantasyClient

config = YahooConfig.from_env()
client = YahooFantasyClient(config)
team = client.get_my_team()
print(f"成功！球隊: {team['team_name']}")
