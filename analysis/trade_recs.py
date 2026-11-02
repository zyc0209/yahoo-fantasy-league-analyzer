"""交易推薦（Python 參考實作，用來核對 Dashboard 上的計算）。

讀 dashboard_data/roster_stats.csv（與網頁同一份資料），
列舉 1 換 1、2 換 2，計算雙方「對其他 11 隊平均預期勝項」的變化。
"""
from itertools import combinations
from math import erf, sqrt
import pandas as pd

ME = "亦宸's Primo Team"
CATS = [("FG%", "pct", "FGM", "FGA", 1), ("FT%", "pct", "FTM", "FTA", 1), ("3PTM", "cnt", "FG3M", None, 1),
        ("3PT%", "pct", "FG3M", "FG3A", 1), ("PTS", "cnt", "PTS", None, 1), ("OREB", "cnt", "OREB", None, 1),
        ("DREB", "cnt", "DREB", None, 1), ("AST", "cnt", "AST", None, 1), ("ST", "cnt", "STL", None, 1),
        ("BLK", "cnt", "BLK", None, 1), ("TO", "cnt", "TOV", None, -1)]
SUMS = ["FGM", "FGA", "FTM", "FTA", "FG3M", "FG3A", "PTS", "OREB", "DREB", "AST", "STL", "BLK", "TOV"]

r = pd.read_csv("dashboard_data/roster_stats.csv")
# 球員 z 分數（比較基準：所有被持有球員；命中率依出手數加權）
Z = pd.DataFrame(index=r.index)
for key, kind, a, b, d in CATS:
    if kind == "pct":
        lg = r[a].sum() / r[b].sum(); imp = ((r[a] / r[b] - lg) * r[b]).fillna(0)  # 沒出手：影響 0，仍計入基準
        Z[key] = (imp - imp.mean()) / imp.std(ddof=0)
    else:
        Z[key] = d * (r[a] - r[a].mean()) / r[a].std(ddof=0)
r["z"] = Z.sum(axis=1)
act = r[r.active == 1]
zof = dict(zip(r.player, r.z))
VALUE_TOL = 0.5  # 換回的總 z 最多只能比送出的多 0.5
import sys as _s
PUNT = set(_s.argv[1].split(",")) if len(_s.argv) > 1 and _s.argv[1] else set()  # 我 punt 的項目不計入我的分數
teams = sorted(r.team.unique())
tot = {t: act[act.team == t][SUMS].sum() for t in teams}

def vals(s):
    return [s[a] / s[b] if k == "pct" else s[a] for _, k, a, b, _ in CATS]

base = {t: vals(tot[t]) for t in teams}
sd = [pd.Series([base[t][i] for t in teams]).std(ddof=0) for i in range(len(CATS))]
phi = lambda x: 0.5 * (1 + erf(x / sqrt(2)))

def exp_wins(team, V, punt=frozenset()):
    s = 0.0
    for i, (key, _, _, _, d) in enumerate(CATS):
        if key in punt: continue
        s += sum(phi(d * (V[team][i] - V[o][i]) / sd[i]) for o in teams if o != team) / (len(teams) - 1)
    return s

def rank(team, V, i):
    d = CATS[i][4]
    return 1 + sum(1 for o in teams if o != team and d * (V[o][i] - V[team][i]) > 0)

def evaluate(give, get, partner):
    V = dict(base)
    g = act[act.player.isin(give)][SUMS].sum(); h = act[act.player.isin(get)][SUMS].sum()
    V[ME] = vals(tot[ME] - g + h); V[partner] = vals(tot[partner] - h + g)
    return exp_wins(ME, V, PUNT), exp_wins(partner, V), [rank(ME, V, i) for i in range(len(CATS))]

me_b = exp_wins(ME, base, PUNT)
print(f"punt={sorted(PUNT)} base: me {me_b:.3f}")
mine = act[act.team == ME].player.tolist()
rows = []
for t in teams:
    if t == ME: continue
    p_b = exp_wins(t, base)
    theirs = act[act.team == t].player.tolist()
    for a in mine:
        for b in theirs:
            m_a, p_a, _ = evaluate([a], [b], t)
            rows.append(("1for1", a, b, t, m_a - me_b, p_a - p_b, zof[b] - zof[a]))
    for a in combinations(mine, 2):
        for b in combinations(theirs, 2):
            m_a, p_a, _ = evaluate(list(a), list(b), t)
            rows.append(("2for2", " + ".join(a), " + ".join(b), t, m_a - me_b, p_a - p_b, zof[b[0]] + zof[b[1]] - zof[a[0]] - zof[a[1]]))
df = pd.DataFrame(rows, columns=["kind", "give", "recv", "partner", "my_d", "pt_d", "value_gap"])
print("evaluated", df.groupby("kind").size().to_dict())
j = df[(df.give == "Ty Jerome") & (df.recv == "Michael Porter Jr.")]
print("Jerome->MPJ", j[["my_d", "pt_d", "value_gap"]].round(4).values.tolist())
print("z check:", {k: round(zof[k], 2) for k in ["Ty Jerome", "Michael Porter Jr.", "Kyrie Irving", "Nikola Jokić"]})
for k in ["1for1", "2for2"]:
    top = df[(df.kind == k) & (df.pt_d >= 0) & (df.value_gap <= VALUE_TOL)].nlargest(5, "my_d")
    print(f"\nTOP {k} (partner >= 0):")
    print(top.round(3).to_string(index=False))
df.round(5).to_csv("dashboard_data/_py_trades.csv", index=False)
