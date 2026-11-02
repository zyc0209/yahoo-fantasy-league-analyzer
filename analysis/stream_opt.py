"""洗格人選：用自由市場球員換掉 Larsson，重算本週最佳排陣與預期拿下類別數。

沿用 lineup_opt.py 的模型；新球員從生效日起才可上場（FA 視為 11/3 生效、W (Nov 3) 11/4、W (Nov 4) 11/5）。
數據用與 Dashboard 相同的兩季加權場均（本季權重 = 本季場數 ÷（本季場數 + 0.1 × 上季場數））。
"""
import itertools, sys
import numpy as np
import pandas as pd
sys.path.insert(0, "analysis")
import power_rankings as pr

ME, OPP, DROP = "亦宸's Primo Team", "柏淙's Crazy Team", "Pelle Larsson"
START, END = "2026-11-02", "2026-11-08"
CATS = [("FG%", "FGM", "FGA", 1), ("FT%", "FTM", "FTA", 1), ("3PTM", "FG3M", None, 1), ("3PT%", "FG3M", "FG3A", 1),
        ("PTS", "PTS", None, 1), ("OREB", "OREB", None, 1), ("DREB", "DREB", None, 1), ("AST", "AST", None, 1),
        ("ST", "STL", None, 1), ("BLK", "BLK", None, 1), ("TO", "TOV", None, -1)]
K = {"PTS": 2.5}
SUMS = ["FGM", "FGA", "FTM", "FTA", "FG3M", "FG3A", "PTS", "OREB", "DREB", "AST", "STL", "BLK", "TOV"]
IX = {k: i for i, k in enumerate(SUMS)}
SLOTS = ["PG", "SG", "G", "SF", "PF", "F", "C", "Util", "Util", "Util"]
FITS = {"PG": {"PG"}, "SG": {"SG"}, "G": {"PG", "SG"}, "SF": {"SF"}, "PF": {"PF"}, "F": {"SF", "PF"}, "C": {"C"},
        "Util": {"PG", "SG", "SF", "PF", "C"}}
CANDS = [
    ("Devin Vassell", "SAS", "SG,SF", "2026-11-04", "W"), ("Kris Dunn", "LAC", "PG,SG", "2026-11-03", ""),
    ("Jared McCain", "OKC", "PG,SG", "2026-11-03", ""), ("Aday Mara", "OKC", "C", "2026-11-04", "W"),
    ("Sandro Mamukelashvili", "LAL", "PF,C", "2026-11-05", "W"), ("Grayson Allen", "CHA", "SG,SF", "2026-11-04", "W"),
    ("Julian Champagnie", "SAS", "SF,PF", "2026-11-03", ""), ("De'Andre Hunter", "SAC", "SF,PF", "2026-11-03", ""),
    ("Draymond Green", "GSW", "PF,C", "2026-11-03", "P"), ("Reed Sheppard", "HOU", "PG,SG", "2026-11-03", "Q"),
    ("Isaiah Jackson", "LAC", "C", "2026-11-05", "W"), ("Kyle Kuzma", "MIL", "SF,PF", "2026-11-03", ""),
    ("Quentin Grimes", "LAL", "SG,SF", "2026-11-03", ""), ("Jaylen Wells", "MEM", "SG,SF", "2026-11-03", ""),
    ("Derrick Jones Jr.", "LAC", "SF,PF", "2026-11-03", "Q"), ("Obi Toppin", "IND", "SF,PF", "2026-11-03", "Q"),
    ("Naji Marshall", "DAL", "SG,SF,PF", "2026-11-03", ""), ("Matisse Thybulle", "LAL", "SG,SF", "2026-11-03", ""),
    ("Tre Jones", "CHI", "PG,SG", "2026-11-03", ""), ("Mitchell Robinson", "BOS", "C", "2026-11-03", "P"),
]

stats, _ = pr.load_stats()
r = pd.read_csv("dashboard_data/roster_stats.csv").set_index("player")
cur = pd.read_csv("data/rosters_current.csv")
sch = pd.read_csv("data/nba_schedule_2026-27.csv", parse_dates=["date"])
days = list(pd.date_range(START, END))
sch = sch[(sch.date >= START) & (sch.date <= END)]
plays = lambda nba, d: bool(((sch.date == d) & ((sch.home == nba) | (sch.away == nba))).any())

def erf(x):  # Abramowitz-Stegun, vectorized
    s = np.sign(x); x = np.abs(x); t = 1 / (1 + 0.3275911 * x)
    return s * (1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-x * x))
phi = lambda x: 0.5 * (1 + erf(x / np.sqrt(2)))

P = {}
for _, p in cur[(cur.fantasy_team == ME) & (cur.slot != "IL")].iterrows():
    P[p.player] = dict(v=np.array([r.loc[p.player, k] for k in SUMS], float), nba=r.loc[p.player, "nba"],
                       pos=set(p.positions.split(",")), frm=pd.Timestamp(START))
OT = np.zeros(len(SUMS))
for p in cur[(cur.fantasy_team == OPP) & ~cur.slot.isin(["BN", "IL"])].player:
    OT += np.array([r.loc[p, k] for k in SUMS]) * sum(plays(r.loc[p, "nba"], d) for d in days)

def exp_wins(T):  # T: (..., 13)
    per = []
    for key, a, b, d in CATS:
        ma = T[..., IX[a]]; oa = OT[IX[a]]
        if b:
            mb = T[..., IX[b]]; ob = OT[IX[b]]; pm, po = ma / mb, oa / ob
            per.append(phi(d * (pm - po) / np.sqrt(pm * (1 - pm) / mb + po * (1 - po) / ob)))
        else:
            per.append(phi(d * (ma - oa) / np.sqrt(K.get(key, 1.1) * (ma + oa))))
    per = np.stack(per, -1)
    return per.sum(-1), per

def feasible(players, pos):
    order = sorted(players, key=lambda x: len(pos[x]))
    def go(i, used):
        if i == len(order): return True
        return any(j not in used and pos[order[i]] & FITS[s] and go(i + 1, used | {j}) for j, s in enumerate(SLOTS))
    return go(0, frozenset())

def best_week(roster):
    pos = {p: roster[p]["pos"] for p in roster}
    fixed = np.zeros(len(SUMS)); free = []
    for d in days:
        avail = [p for p in roster if d >= roster[p]["frm"] and plays(roster[p]["nba"], d)]
        if len(avail) <= 10 and feasible(avail, pos):
            for p in avail: fixed += roster[p]["v"]
            free.append(None)
        else:
            opts = [c for c in itertools.combinations(avail, min(10, len(avail))) if feasible(c, pos)]
            free.append((opts, np.array([sum(roster[p]["v"] for p in c) for c in opts])))
    choices = [f for f in free if f is not None]
    assert len(choices) <= 2
    A = choices[0][1]; B = choices[1][1] if len(choices) > 1 else np.zeros((1, len(SUMS)))
    T = fixed + A[:, None, :] + B[None, :, :]
    tot, per = exp_wins(T)
    i, j = np.unravel_index(np.argmax(tot), tot.shape)
    lineups = [choices[0][0][i]] + ([choices[1][0][j]] if len(choices) > 1 else [])
    games = {}
    for d in days:
        avail = [p for p in roster if d >= roster[p]["frm"] and plays(roster[p]["nba"], d)]
        for p in avail: games[p] = games.get(p, 0)
    return float(tot[i, j]), {k: float(per[i, j, n]) for n, (k, *_) in enumerate(CATS)}, lineups

def games_played(roster, lineups):
    pos = {p: roster[p]["pos"] for p in roster}; g = {}; li = iter(lineups)
    for d in days:
        avail = [p for p in roster if d >= roster[p]["frm"] and plays(roster[p]["nba"], d)]
        on = avail if (len(avail) <= 10 and feasible(avail, pos)) else next(li)
        for p in on: g[p] = g.get(p, 0) + 1
    return g

base_v, base_per, base_l = best_week(P)
print(f"保留 Larsson：預期 {base_v:.2f} 項（Larsson 本週實際上場 {games_played(P, base_l).get(DROP, 0)} 場）")
rows = []
for name, nba, posn, frm, flag in CANDS:
    key = pr.norm(name)
    if key not in stats.index: print("找不到數據：", name); continue
    s = stats.loc[key]
    roster = {p: v for p, v in P.items() if p != DROP}
    roster[name] = dict(v=np.array([s[k] for k in SUMS], float), nba=nba, pos=set(posn.split(",")), frm=pd.Timestamp(frm))
    v, per, lineups = best_week(roster)
    g = games_played(roster, lineups)
    rows.append(dict(name=name, flag=flag, frm=frm[5:], g=g.get(name, 0), d=v - base_v,
                     dper={k: per[k] - base_per[k] for k in per}, gp=f"{int(s.GP_cur)}/{int(s.GP_prev)}",
                     line=f"{s.PTS:.1f}分 {s.FG3M:.1f}三分 {s.OREB+s.DREB:.1f}板({s.DREB:.1f}防) {s.AST:.1f}助 {s.STL:.1f}抄 {s.BLK:.1f}帽 FG{s.FGM/s.FGA:.3f}",
                     sched="".join("X" if plays(nba, d) else "." for d in days)))
rows.sort(key=lambda x: -x["d"])
print("\n排名 球員 [狀態] 生效 賽程(一~日) 本週上場 | 預期項數 | 搖擺項勝率變化 | 兩季加權場均 (本季/上季場數)")
for i, x in enumerate(rows, 1):
    sw = " ".join(f"{k}{x['dper'][k]:+.0%}" for k in ["DREB", "3PTM", "PTS", "3PT%", "ST", "BLK", "FG%", "TO", "AST"] if abs(x["dper"][k]) >= 0.01)
    print(f"{i:>2}. {x['name']:<22}{('['+x['flag']+']') if x['flag'] else '':<4} {x['frm']} {x['sched']} {x['g']}場 | {x['d']:+.2f} | {sw} | {x['line']} ({x['gp']})")
