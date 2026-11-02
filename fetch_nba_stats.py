"""抓 NBA 球員數據與賽程，存到 data/ 給戰力分析用。

來源：Basketball-Reference（stats.nba.com 與 cdn.nba.com 會擋你的網路）
用法：
    cd ~/fantasy && .venv/bin/python fetch_nba_stats.py
"""
import re
import time
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
import requests

OUT = Path(__file__).resolve().parent / "data"
OUT.mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}

# BBRef 欄位（新舊版 data-stat 名稱都支援）→ 我們的欄位
FIELD = {
    "name_display": "PLAYER_NAME", "player": "PLAYER_NAME",
    "team_name_abbr": "TEAM_ABBREVIATION", "team_id": "TEAM_ABBREVIATION",
    "games": "GP", "g": "GP", "mp": "MIN",
    "fg": "FGM", "fga": "FGA", "fg3": "FG3M", "fg3a": "FG3A", "ft": "FTM", "fta": "FTA",
    "orb": "OREB", "drb": "DREB", "ast": "AST", "stl": "STL", "blk": "BLK", "tov": "TOV", "pts": "PTS",
}
# BBRef 隊名縮寫 → NBA 官方縮寫（賽程用）
TEAM_FIX = {"BRK": "BKN", "CHO": "CHA", "PHO": "PHX"}
NUM = ["GP", "MIN", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA",
       "OREB", "DREB", "AST", "STL", "BLK", "TOV", "PTS"]


class TotalsParser(HTMLParser):
    """解析 BBRef totals 表格：每個 <td data-stat=...> 一欄。"""

    def __init__(self):
        super().__init__()
        self.rows, self.row, self.stat, self.in_table = [], None, None, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table" and a.get("id") in ("totals_stats", "totals"):
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.row = {}
        elif self.in_table and self.row is not None and tag in ("td", "th"):
            self.stat = a.get("data-stat")
            if self.stat == "name_display" or self.stat == "player":
                self.row["_pid"] = a.get("data-append-csv", "")

    def handle_endtag(self, tag):
        if tag == "table" and self.in_table:
            self.in_table = False
        elif tag in ("td", "th"):
            self.stat = None
        elif tag == "tr" and self.row is not None:
            # 只收有球員 ID 的列：略過表格中間重複的表頭（Player）和 League Average
            if self.row.get("PLAYER_NAME") and self.row.get("_pid"):
                self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.row is not None and self.stat in FIELD:
            key = FIELD[self.stat]
            self.row[key] = self.row.get(key, "") + data.strip()


def fetch_bbref(season_end_year: int) -> pd.DataFrame:
    url = f"https://www.basketball-reference.com/leagues/NBA_{season_end_year}_totals.html"
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"  # BBRef 沒標編碼，不指定會把 Jokić 變成亂碼
    p = TotalsParser()
    p.feed(r.text)
    df = pd.DataFrame(p.rows)
    if df.empty:
        raise RuntimeError("頁面上找不到 totals 表格")
    for c in NUM:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0) if c in df else 0
    # 換過隊的球員：第一列是合計（2TM/TOT），最後一列是現在的球隊
    df["TEAM_ABBREVIATION"] = df["TEAM_ABBREVIATION"].replace(TEAM_FIX)
    current_team = df[~df["TEAM_ABBREVIATION"].str.match(r"^(\dTM|TOT)$")] \
        .groupby("_pid")["TEAM_ABBREVIATION"].last()
    df = df.groupby("_pid", sort=False).first().reset_index()
    df["TEAM_ABBREVIATION"] = df["_pid"].map(current_team).fillna(df["TEAM_ABBREVIATION"])
    df = df.rename(columns={"_pid": "PLAYER_ID"})
    return df[["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION"] + NUM]


class ScheduleParser(HTMLParser):
    """解析 BBRef 賽程表：日期取自 csk（YYYYMMDD…），隊伍取自 /teams/XXX/ 連結。"""

    def __init__(self):
        super().__init__()
        self.games, self.row, self.stat, self.in_table = [], None, None, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table" and a.get("id") == "schedule":
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.row = {}
        elif self.in_table and self.row is not None and tag in ("td", "th"):
            self.stat = a.get("data-stat")
            if self.stat == "date_game" and a.get("csk"):
                self.row["date"] = a["csk"][:8]
        elif self.row is not None and tag == "a" and self.stat in ("visitor_team_name", "home_team_name"):
            m = re.search(r"/teams/([A-Z]{3})/", a.get("href", ""))
            if m:
                self.row["away" if self.stat == "visitor_team_name" else "home"] = TEAM_FIX.get(m[1], m[1])

    def handle_endtag(self, tag):
        if tag == "table" and self.in_table:
            self.in_table = False
        elif tag in ("td", "th"):
            self.stat = None
        elif tag == "tr" and self.row is not None:
            if {"date", "away", "home"} <= self.row.keys():
                self.games.append(self.row)
            self.row = None


MONTHS = ["october", "november", "december", "january", "february", "march", "april"]


def fetch_schedule(season_end_year: int) -> pd.DataFrame:
    games = []
    for month in MONTHS:
        url = f"https://www.basketball-reference.com/leagues/NBA_{season_end_year}_games-{month}.html"
        r = requests.get(url, headers=UA, timeout=30)
        if r.status_code == 404:  # 還沒公布的月份
            continue
        r.raise_for_status()
        r.encoding = "utf-8"
        p = ScheduleParser()
        p.feed(r.text)
        games += p.games
        time.sleep(4)
    df = pd.DataFrame(games)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d").dt.date
    return df[["date", "home", "away"]]


for season, end_year in [("2025-26", 2026), ("2026-27", 2027)]:
    print(f"抓 {season} 球員數據（Basketball-Reference）…")
    df = fetch_bbref(end_year)
    df.to_csv(OUT / f"nba_stats_{season}.csv", index=False)
    print(f"   {len(df)} 位球員，最多 {int(df['GP'].max())} 場 → data/nba_stats_{season}.csv")
    time.sleep(4)  # BBRef 有頻率限制，別抓太快

print("抓 2026-27 賽程（Basketball-Reference，約 30 秒）…")
try:
    sched = fetch_schedule(2027)
    sched.to_csv(OUT / "nba_schedule_2026-27.csv", index=False)
    print(f"   {len(sched)} 場例行賽 → data/nba_schedule_2026-27.csv")
except Exception as e:
    print(f"   賽程抓取失敗（不影響戰力排名，本週對戰會用平均場次估）：{e}")

print("\n完成！回到 Claude 說一聲就好。")
