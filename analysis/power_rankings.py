"""11-Cat 戰力分析：球員 z-score、12 隊各項排名、本週對戰預測。

讀 data/ 下的陣容、聯盟設定與 NBA 數據，輸出 data/power_rankings.json。
資料來源層只靠 CSV，之後換成 Yahoo API 時分析邏輯不用改。

用法：python3 analysis/power_rankings.py
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# 本季權重 = 本季場數 / (本季場數 + PREV_GAME_WEIGHT × 上季場數)
# 上季 10 場只抵本季 1 場；沒有上季數據（菜鳥）時本季權重 = 1
PREV_GAME_WEIGHT = 0.1
# 沒有賽程時，每人每週預估出賽數
DEFAULT_WEEKLY_GAMES = 3.5
# 名字對不上時的手動對照：Yahoo 名 → NBA 名（正規化前）
ALIASES: dict[str, str] = {}
# 不確定歸屬、暫時當成沒人持有的球員
UNOWNED: set[str] = {"Cameron Johnson"}

STAT_COLS = ["FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA",
             "OREB", "DREB", "AST", "STL", "BLK", "TOV", "PTS", "MIN"]


def norm(name: str) -> str:
    name = ALIASES.get(name, name)
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[.'\-]", " ", s.lower())
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------- 資料讀取 ----------

def load_league() -> dict:
    return json.loads((DATA / "league.json").read_text())


def load_rosters(league: dict) -> pd.DataFrame:
    draft = pd.read_csv(DATA / "rosters_draft.csv")
    trades_path = DATA / "trades.csv"
    if trades_path.exists():  # 選秀陣容套用已知交易
        for _, t in pd.read_csv(trades_path).iterrows():
            hit = (draft["player"] == t["player"]) & (draft["fantasy_team"] == t["from_team"])
            assert hit.any(), f"交易球員不在 {t['from_team']} 的選秀陣容：{t['player']}"
            draft.loc[hit, "fantasy_team"] = t["to_team"]
    cur = pd.read_csv(DATA / "rosters_current.csv")
    current_teams = set(cur["fantasy_team"])
    taken = set(cur["player"])
    others = draft[~draft["fantasy_team"].isin(current_teams)
                   & ~draft["player"].isin(taken)
                   & ~draft["player"].isin(UNOWNED)].copy()
    others["slot"] = "?"
    others["source"] = "draft"
    cur = cur.copy()
    cur["source"] = "current"
    cols = ["fantasy_team", "player", "nba_team", "positions", "slot", "source"]
    r = pd.concat([cur[cols], others[cols]], ignore_index=True)
    r["active"] = r["slot"] != "IL"
    r["key"] = r["player"].map(norm)
    return r


def load_stats() -> tuple[pd.DataFrame, str]:
    prev = pd.read_csv(DATA / "nba_stats_2025-26.csv")
    cur = pd.read_csv(DATA / "nba_stats_2026-27.csv")
    for df in (prev, cur):
        df["key"] = df["PLAYER_NAME"].map(norm)
    p = prev.groupby("key")[["GP"] + STAT_COLS].sum()
    c = cur.groupby("key")[["GP"] + STAT_COLS].sum()
    team = cur.groupby("key")["TEAM_ABBREVIATION"].last()
    team = team.combine_first(prev.groupby("key")["TEAM_ABBREVIATION"].last())
    names = pd.concat([prev, cur]).groupby("key")["PLAYER_NAME"].last()

    keys = p.index.union(c.index)
    p, c = p.reindex(keys, fill_value=0), c.reindex(keys, fill_value=0)
    gp_p, gp_c = p["GP"].to_numpy(float), c["GP"].to_numpy(float)
    w = np.where(gp_p == 0, 1.0, np.where(gp_c == 0, 0.0, gp_c / (gp_c + PREV_GAME_WEIGHT * gp_p)))
    with np.errstate(invalid="ignore", divide="ignore"):
        pg_p = p[STAT_COLS].div(np.where(gp_p == 0, np.nan, gp_p), axis=0).fillna(0)
        pg_c = c[STAT_COLS].div(np.where(gp_c == 0, np.nan, gp_c), axis=0).fillna(0)
    blended = pg_p.mul(1 - w, axis=0) + pg_c.mul(w, axis=0)
    blended["GP_prev"], blended["GP_cur"], blended["w_cur"] = gp_p, gp_c, w
    blended["nba_team_now"] = team.reindex(keys)
    blended["nba_name"] = names.reindex(keys)
    as_of = f"2025-26 全季 + 2026-27 至今（最多 {int(gp_c.max())} 場）"
    return blended, as_of


# ---------- z-score ----------

def player_zscores(pool: pd.DataFrame, cats: list[dict]) -> pd.DataFrame:
    z = pd.DataFrame(index=pool.index)
    for cat in cats:
        if cat["type"] == "pct":
            made, att = pool[cat["made"]], pool[cat["att"]]
            lg = made.sum() / att.sum()
            pct = (made / att.replace(0, np.nan)).fillna(lg)
            impact = (pct - lg) * att
            z[cat["key"]] = (impact - impact.mean()) / impact.std(ddof=0)
        else:
            x = pool[cat["stat"]]
            zz = (x - x.mean()) / x.std(ddof=0)
            z[cat["key"]] = zz if cat["higher_better"] else -zz
    return z


def team_category_values(players: pd.DataFrame, cats: list[dict], games: pd.Series | None = None) -> dict:
    """球隊各項數值：計數項加總，命中率用總命中 / 總出手。games 給定時乘上出賽數。"""
    mult = games if games is not None else pd.Series(1.0, index=players.index)
    out = {}
    for cat in cats:
        if cat["type"] == "pct":
            made = (players[cat["made"]] * mult).sum()
            att = (players[cat["att"]] * mult).sum()
            out[cat["key"]] = float(made / att) if att else 0.0
            out[cat["key"] + "_made"], out[cat["key"] + "_att"] = float(made), float(att)
        else:
            out[cat["key"]] = float((players[cat["stat"]] * mult).sum())
    return out


# ---------- 對戰預測 ----------

def weekly_games(league: dict) -> tuple[dict[str, int] | None, list[str]]:
    path = DATA / "nba_schedule_2026-27.csv"
    wk = str(league["current_week"])
    if not path.exists() or wk not in league["week_dates"]:
        return None, []
    s = pd.read_csv(path, parse_dates=["date"])
    start, end = (pd.Timestamp(d) for d in league["week_dates"][wk])
    s = s[(s["date"] >= start) & (s["date"] <= end)]
    counts = pd.concat([s["home"], s["away"]]).value_counts().to_dict()
    days = [d.strftime("%Y-%m-%d") for d in pd.date_range(start, end)]
    return counts, days


def matchup_preview(me: pd.DataFrame, opp: pd.DataFrame, cats: list[dict], games: dict | None) -> list[dict]:
    def g(df):
        if games is None:
            return pd.Series(DEFAULT_WEEKLY_GAMES, index=df.index)
        return df["nba_team_now"].map(games).fillna(0).astype(float)

    mine = team_category_values(me, cats, g(me))
    theirs = team_category_values(opp, cats, g(opp))
    rows = []
    for cat in cats:
        k = cat["key"]
        a, b = mine[k], theirs[k]
        diff = (a - b) if cat["higher_better"] else (b - a)
        rel = diff / max(abs(a), abs(b), 1e-9)
        if cat["type"] == "pct":
            lean = "win" if diff > 0.008 else "lose" if diff < -0.008 else "close"
        else:
            lean = "win" if rel > 0.08 else "lose" if rel < -0.08 else "close"
        rows.append({"cat": k, "me": a, "opp": b, "edge": diff, "rel": rel, "lean": lean})
    return rows


# ---------- 主流程 ----------

def main() -> None:
    league = load_league()
    cats = league["categories"]
    rosters = load_rosters(league)
    stats, as_of = load_stats()

    merged = rosters.merge(stats, left_on="key", right_index=True, how="left")
    missing = merged[merged["GP_prev"].isna()]["player"].tolist()
    merged = merged[merged["GP_prev"].notna()].copy()
    merged["nba_team_now"] = merged["nba_team_now"].fillna(merged["nba_team"])

    # z-score 的比較基準：所有被持有的球員
    pool = merged.drop_duplicates("key").set_index("key")
    z = player_zscores(pool, cats)
    z["TOTAL"] = z[[c["key"] for c in cats]].sum(axis=1)
    merged = merged.join(z.add_prefix("z_"), on="key")

    active = merged[merged["active"]]
    teams = [t["name"] for t in league["teams"]]
    vals = {t: team_category_values(active[active["fantasy_team"] == t], cats) for t in teams}

    # 各項排名（1 = 最強）與球隊層級 z（12 隊之間標準化）
    cat_keys = [c["key"] for c in cats]
    tv = pd.DataFrame({t: {k: vals[t][k] for k in cat_keys} for t in teams}).T
    ranks, tz = pd.DataFrame(index=teams), pd.DataFrame(index=teams)
    for cat in cats:
        k = cat["key"]
        asc = not cat["higher_better"]
        ranks[k] = tv[k].rank(ascending=asc, method="min").astype(int)
        s = (tv[k] - tv[k].mean()) / tv[k].std(ddof=0)
        tz[k] = -s if asc else s
    tz["TOTAL"] = tz[cat_keys].sum(axis=1)
    overall = tz["TOTAL"].rank(ascending=False, method="min").astype(int)

    my, opp = league["my_team"], next(t["week3_opp"] for t in league["teams"] if t["name"] == league["my_team"])
    games, week_days = weekly_games(league)
    preview = matchup_preview(active[active["fantasy_team"] == my], active[active["fantasy_team"] == opp], cats, games)

    def player_rows(team):
        df = merged[merged["fantasy_team"] == team].sort_values("z_TOTAL", ascending=False)
        out = []
        for _, r in df.iterrows():
            gp = int(r["GP_cur"])
            out.append({
                "player": r["player"], "nba_team": r["nba_team_now"], "positions": r["positions"],
                "slot": r["slot"], "active": bool(r["active"]),
                "gp_cur": gp, "gp_prev": int(r["GP_prev"]), "w_cur": round(float(r["w_cur"]), 2),
                "games_this_week": int(games.get(r["nba_team_now"], 0)) if games else None,
                "per_game": {k: round(float(r[k]), 2) for k in ["PTS", "OREB", "DREB", "AST", "STL", "BLK", "TOV", "FG3M", "MIN"]},
                "pct": {"FG%": round(float(r["FGM"] / r["FGA"]), 3) if r["FGA"] else None,
                        "FT%": round(float(r["FTM"] / r["FTA"]), 3) if r["FTA"] else None,
                        "3PT%": round(float(r["FG3M"] / r["FG3A"]), 3) if r["FG3A"] else None},
                "z": {k: round(float(r["z_" + k]), 2) for k in cat_keys + ["TOTAL"]},
            })
        return out

    result = {
        "generated": date.today().isoformat(),
        "data_as_of": as_of,
        "prev_game_weight": PREV_GAME_WEIGHT,
        "categories": [{"key": c["key"], "higher_better": c["higher_better"], "type": c["type"]} for c in cats],
        "teams": [{
            "name": t,
            "record": next(x["record"] for x in league["teams"] if x["name"] == t),
            "standing": next(x["rank"] for x in league["teams"] if x["name"] == t),
            "roster_source": "current" if t in (my, opp) else "draft",
            "overall_rank": int(overall[t]),
            "total_z": round(float(tz.loc[t, "TOTAL"]), 2),
            "values": {k: round(vals[t][k], 4) for k in cat_keys},
            "ranks": {k: int(ranks.loc[t, k]) for k in cat_keys},
            "z": {k: round(float(tz.loc[t, k]), 2) for k in cat_keys},
        } for t in teams],
        "my_team": my,
        "opponent": opp,
        "week": league["current_week"],
        "week_dates": league["week_dates"].get(str(league["current_week"])),
        "schedule_available": games is not None,
        "matchup": preview,
        "my_players": player_rows(my),
        "opp_players": player_rows(opp),
        "unmatched_players": missing,
        "unowned_assumed": sorted(UNOWNED),
    }
    (DATA / "power_rankings.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))

    print(f"數據：{as_of}")
    print(f"對不上 NBA 數據的球員（{len(missing)}）：{missing}")
    print("\n總戰力排名：")
    for t in tz["TOTAL"].sort_values(ascending=False).index:
        print(f"  {overall[t]:>2}. {t:<26} z={tz.loc[t,'TOTAL']:+.2f}  " +
              " ".join(f"{k}:{ranks.loc[t,k]}" for k in cat_keys))
    print(f"\n本週 {my} vs {opp}：")
    for r in preview:
        print(f"  {r['cat']:<5} {r['me']:>9.3f} vs {r['opp']:>9.3f}  {r['lean']}")


if __name__ == "__main__":
    main()
