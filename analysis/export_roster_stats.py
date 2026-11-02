"""輸出所有被持有球員的混合場均數據（給 Dashboard 的交易模擬與推薦用）。"""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import pandas as pd
import power_rankings as pr

league = pr.load_league()
rosters = pr.load_rosters(league)
stats, _ = pr.load_stats()
m = rosters.merge(stats, left_on="key", right_index=True, how="left")
m = m[m["GP_prev"].notna()].copy()
cols3 = ["FGM", "FGA", "FTM", "FTA", "FG3M", "FG3A"]
cols2 = ["PTS", "OREB", "DREB", "AST", "STL", "BLK", "TOV"]
games, _ = pr.weekly_games(league)
out = pd.DataFrame({
    "player": m["player"], "team": m["fantasy_team"], "slot": m["slot"],
    "active": m["active"].astype(int), "nba": m["nba_team_now"], "pos": m["positions"],
    "gp_cur": m["GP_cur"].astype(int), "gp_prev": m["GP_prev"].astype(int), "w_cur": m["w_cur"].round(2),
    "games_week": m["nba_team_now"].map(games or {}).fillna(0).astype(int),
})
for c in cols3: out[c] = m[c].round(3)
for c in cols2: out[c] = m[c].round(2)
out = out.sort_values(["team", "player"])
out.to_csv("dashboard_data/roster_stats.csv", index=False)
print(len(out), "rows", out["team"].nunique(), "teams", out["active"].sum(), "active")
