# 再一顆好不好 League Analyzer (Yahoo Fantasy Basketball)

> **Personal, non-commercial, read-only project.** Built by an individual Yahoo Fantasy Basketball player for one private league (Yahoo league ID 12847, 12 teams, 11-category head-to-head). Only the league's managers would ever see the results. No public release, no commercial use, and no redistribution of Yahoo data.

## Purpose

1. **League power rankings** - rank all 12 teams in each of our 11 scoring categories (player z-scores blending last-season and current-season stats) to see each team's strengths and weaknesses before weekly matchups.
2. **Roster analysis** - identify my team's punt categories, core players and trade candidates, and evaluate trades with other teams in the league.
3. **Daily streaming recommendations** - suggest free agents to add based on live weekly matchup totals and remaining NBA games.

## Yahoo Fantasy Sports data used (read-only)

League settings and stat categories, teams and rosters, player season/recent stats, weekly scoreboard and matchup stats, free agent lists, and league transactions. Access uses OAuth 2.0 with my own Yahoo account, a few scheduled pulls per day, and local caching. No write access is needed or requested. Credentials and tokens are never committed to this repository.

---

## Technical details: Yahoo Fantasy Basketball MCP Server

MCP Server for Yahoo Fantasy Basketball API, enabling LLM-powered 9-cat H2H analysis and player recommendations.

## Features

- **get_my_team** - View your roster and player stats
- **get_weekly_matchup** - Compare 9-cat stats with your weekly opponent
- **get_remaining_games** - Track remaining games for streaming decisions
- **get_free_agents** - Browse waiver wire sorted by any category
- **get_player_stats** - Get detailed stats for any player
- **get_league_standings** - View current league rankings
- **get_category_analysis** - Identify your team's strengths and weaknesses

## Setup

### 1. Create Yahoo Developer App

1. Go to [Yahoo Developer](https://developer.yahoo.com/apps/)
2. Click "Create an App"
3. Fill in:
   - Application Name: (anything, e.g., "Fantasy MCP")
   - Application Type: Installed Application
   - Redirect URI: `oob` (out of band)
   - API Permissions: Fantasy Sports (Read)
4. Save your **Consumer Key** and **Consumer Secret**

### 2. Find Your League ID

Your league ID is in the URL when you visit your league:
```
https://basketball.fantasysports.yahoo.com/nba/123456
                                              ^^^^^^
                                              This is your league_id
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```
YAHOO_CONSUMER_KEY=your_consumer_key
YAHOO_CONSUMER_SECRET=your_consumer_secret
YAHOO_LEAGUE_ID=123456
```

### 4. Install

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -e .
```

### 5. First Run (OAuth Authorization)

The first time you run the server, it will open a browser for Yahoo OAuth authorization:

```bash
uv run yahoo-fantasy-mcp
```

Follow the prompts to authorize access. The token will be saved for future use.

## Claude Desktop Integration

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "yahoo-fantasy": {
      "command": "uv",
      "args": ["--directory", "/path/to/fantasy", "run", "yahoo-fantasy-mcp"],
      "env": {
        "YAHOO_CONSUMER_KEY": "your_key",
        "YAHOO_CONSUMER_SECRET": "your_secret",
        "YAHOO_LEAGUE_ID": "your_league_id"
      }
    }
  }
}
```

## Usage Examples

Once connected, you can ask Claude things like:

- "How am I doing in my matchup this week?"
- "Which categories am I losing? What free agents could help?"
- "Show me the best available point guards"
- "Analyze my team's strengths and weaknesses"
- "Who should I stream to maximize assists this week?"

## Development

Test the server locally:

```bash
mcp dev src/yahoo_fantasy_mcp/server.py
```

## Troubleshooting

### OAuth Token Expired
Delete the `.yahoo_data` directory and re-authenticate:
```bash
rm -rf .yahoo_data
uv run yahoo-fantasy-mcp
```

### Rate Limiting
Yahoo has API rate limits. If you encounter errors, wait a few minutes before retrying.

### Wrong League
Make sure `YAHOO_LEAGUE_ID` is set to your basketball league, not another sport.
