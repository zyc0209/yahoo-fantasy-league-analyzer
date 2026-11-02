"""本週每日排陣最佳化：對單一對手，最大化本週預期拿下的類別數。

- 對手：目前先發 10 格的球員有比賽就出賽，BN / IL 不計（依使用者設定）。
- 我方：每天從有比賽的非傷停球員中選最多 10 人，須能排進 PG/SG/G/SF/PF/F/C/Util×3。
- 每項勝率 = Φ(預期差距 / 差距的標準差)。計數項單場變異 = k × 場均（PTS k=2.5，其餘 1.1）；
  命中率的變異 ≈ p(1-p) / 整週出手數。預期拿下類別數 = 11 項勝率加總。
用法：python3 analysis/lineup_opt.py [--out 球員,球員]  （--out 代表假設該球員本週缺陣）
"""
import itertools, sys
from math import erf, sqrt
import pandas as pd

ME, OPP = "亦宸's Primo Team", "柏淙's Crazy Team"
START, END = "2026-11-02", "2026-11-08"
CATS = [("FG%", "FGM", "FGA", 1), ("FT%", "FTM", "FTA", 1), ("3PTM", "FG3M", None, 1), ("3PT%", "FG3M", "FG3A", 1),
        ("PTS", "PTS", None, 1), ("OREB", "OREB", None, 1), ("DREB", "DREB", None, 1), ("AST", "AST", None, 1),
        ("ST", "STL", None, 1), ("BLK", "BLK", None, 1), ("TO", "TOV", None, -1)]
K = {"PTS": 2.5}
SUMS = ["FGM", "FGA", "FTM", "FTA", "FG3M", "FG3A", "PTS", "OREB", "DREB", "AST", "STL", "BLK", "TOV"]
SLOTS = ["PG", "SG", "G", "SF", "PF", "F", "C", "Util", "Util", "Util"]
FITS = {"PG": {"PG"}, "SG": {"SG"}, "G": {"PG", "SG"}, "SF": {"SF"}, "PF": {"PF"}, "F": {"SF", "PF"}, "C": {"C"},
        "Util": {"PG", "SG", "SF", "PF", "C"}}
out_players = set(sys.argv[sys.argv.index("--out") + 1].split(",")) if "--out" in sys.argv else set()

r = pd.read_csv("dashboard_data/roster_stats.csv").set_index("player")
cur = pd.read_csv("data/rosters_current.csv")
sch = pd.read_csv("data/nba_schedule_2026-27.csv", parse_dates=["date"])
days = list(pd.date_range(START, END))
sch = sch[(sch.date >= START) & (sch.date <= END)]
plays = lambda nba, d: bool(((sch.date == d) & ((sch.home == nba) | (sch.away == nba))).any())

mine = cur[(cur.fantasy_team == ME) & (cur.slot != "IL")]
mine = mine[~mine.player.isin(out_players)]
opp_start = cur[(cur.fantasy_team == OPP) & ~cur.slot.isin(["BN", "IL"])]
pos = {p.player: set(p.positions.split(",")) for _, p in mine.iterrows()}

def feasible(players):
    order = sorted(players, key=lambda p: len(pos[p]))
    def go(i, used):
        if i == len(order): return True
        for j, s in enumerate(SLOTS):
            if j not in used and pos[order[i]] & FITS[s]:
                if go(i + 1, used | {j}): return True
        return False
    return go(0, frozenset())

def totals(games):  # games: {player: n}
    t = {k: 0.0 for k in SUMS}
    for p, n in games.items():
        for k in SUMS: t[k] += r.loc[p, k] * n
    return t

opp_games = {p: sum(plays(r.loc[p, "nba"], d) for d in days) for p in opp_start.player}
OT = totals(opp_games)
phi = lambda x: 0.5 * (1 + erf(x / sqrt(2)))

def exp_wins(T, detail=False):
    tot, per = 0.0, {}
    for key, a, b, d in CATS:
        if b:
            pm, po = T[a] / T[b], OT[a] / OT[b]
            var = pm * (1 - pm) / T[b] + po * (1 - po) / OT[b]
            p = phi(d * (pm - po) / sqrt(var))
        else:
            k = K.get(key, 1.1)
            p = phi(d * (T[a] - OT[a]) / sqrt(k * (T[a] + OT[a])))
        per[key] = p; tot += p
    return (tot, per) if detail else tot

# 每天的候選先發組合
day_opts = []
for d in days:
    avail = [p for p in mine.player if plays(r.loc[p, "nba"], d)]
    if len(avail) <= 10 and feasible(avail):
        day_opts.append([tuple(avail)])
    else:
        n = min(10, len(avail))
        opts = [c for c in itertools.combinations(avail, n) if feasible(c)]
        day_opts.append(opts)
fixed = {}
for opts in day_opts:
    if len(opts) == 1:
        for p in opts[0]: fixed[p] = fixed.get(p, 0) + 1
free = [i for i, o in enumerate(day_opts) if len(o) > 1]
print("需要取捨的日子：", [days[i].strftime("%a %m/%d") + f"（{len(day_opts[i][0]) + 0} 選自 {len([p for p in mine.player if plays(r.loc[p,'nba'], days[i])])} 人，{len(day_opts[i])} 種合法組合）" for i in free])

best = None
for combo in itertools.product(*[day_opts[i] for i in free]):
    g = dict(fixed)
    for lineup in combo:
        for p in lineup: g[p] = g.get(p, 0) + 1
    v = exp_wins(totals(g))
    if best is None or v > best[0]: best = (v, combo, g)

def report(name, g):
    v, per = exp_wins(totals(g), detail=True)
    print(f"\n{name}：預期拿下 {v:.2f} 項")
    print("  " + "  ".join(f"{k} {p:.0%}" for k, p in per.items()))
    return v

v_best = report("最佳排法", best[2])
for i, lineup in zip(free, best[1]):
    avail = [p for p in mine.player if plays(r.loc[p, "nba"], days[i])]
    print(f"  {days[i].strftime('%a %m/%d')} 坐板凳：{', '.join(p for p in avail if p not in lineup)}")
# 對照：照目前先發格（BN 三人不上），其他天有比賽就上
cur_start = set(mine[~mine.slot.isin(["BN"])].player)
g0 = dict(fixed)
for i in free:
    for p in day_opts[i][0]:
        pass
    avail = [p for p in mine.player if plays(r.loc[p, "nba"], days[i])]
    for p in avail:
        if p in cur_start: g0[p] = g0.get(p, 0) + 1
v0 = report("照你目前的先發（Diabaté、Turner、Larsson 坐板凳）", g0)
print(f"\n差距：{v_best - v0:+.2f} 項")
# 每個人在爆格日多上一場的邊際價值（相對最佳排法）
print("\n爆格日每多上一場的邊際價值（以最佳排法為基準，移除/加入一場）：")
base_t = totals(best[2])
for p in mine.player:
    t = dict(base_t)
    sign = -1 if p in best[1][0] else 1
    for k in SUMS: t[k] += sign * r.loc[p, k]
    dv = exp_wins(t) - v_best
    print(f"  {p:<24} {'先發' if sign < 0 else '板凳'}  {'少上' if sign < 0 else '多上'}一場 → {dv:+.3f}")
