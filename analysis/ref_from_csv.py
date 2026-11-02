"""Independent reference: compute what the dashboard shows from roster_stats.csv + teams_meta.json.

Usage: python3 ref_from_csv.py <dir with roster_stats.csv and teams_meta.json>  → prints JSON
"""
import json
import sys
from pathlib import Path

import pandas as pd

D = Path(sys.argv[1])
r = pd.read_csv(D / "roster_stats.csv")
meta = json.loads((D / "teams_meta.json").read_text())
ME = next(t["team"] for t in meta if t["is_me"])
OPP = next(t["team"] for t in meta if t["is_opp"])
CATS = [("FG%", "FGM", "FGA", 1), ("FT%", "FTM", "FTA", 1), ("3PTM", "FG3M", None, 1), ("3PT%", "FG3M", "FG3A", 1),
        ("PTS", "PTS", None, 1), ("OREB", "OREB", None, 1), ("DREB", "DREB", None, 1), ("AST", "AST", None, 1),
        ("ST", "STL", None, 1), ("BLK", "BLK", None, 1), ("TO", "TOV", None, -1)]
SUMS = ["FGM", "FGA", "FTM", "FTA", "FG3M", "FG3A", "PTS", "OREB", "DREB", "AST", "STL", "BLK", "TOV"]

act = r[r.active == 1]
tot = act.groupby("team")[SUMS].sum()
cats = {}
for key, a, b, d in CATS:
    v = tot[a] / tot[b] if b else tot[a]
    z = d * (v - v.mean()) / v.std(ddof=0)
    rank = (d * v).rank(ascending=False, method="min").astype(int)
    cats[key] = {"value": v.to_dict(), "rank": rank.to_dict(), "z": z.to_dict()}
total = {t: sum(cats[k]["z"][t] for k, *_ in CATS) for t in tot.index}
ts = pd.Series(total)
overall = ts.rank(ascending=False, method="min").astype(int).to_dict()

def week(team):
    p = act[act.team == team]
    return (p[SUMS].mul(p["games_week"], axis=0)).sum()
A, B = week(ME), week(OPP)
mu = []
for key, a, b, d in CATS:
    x = A[a] / A[b] if b else A[a]; y = B[a] / B[b] if b else B[a]
    edge = d * (x - y); rel = edge / max(abs(x), abs(y), 1e-9)
    lean = ("win" if edge > 0.008 else "lose" if edge < -0.008 else "close") if b else ("win" if rel > 0.08 else "lose" if rel < -0.08 else "close")
    mu.append({"cat": key, "me": x, "opp": y, "lean": lean})

pz = {}
Z = pd.DataFrame(index=r.index)
for key, a, b, d in CATS:
    if b:
        lg = r[a].sum() / r[b].sum()
        x = ((r[a] / r[b] - lg) * r[b]).where(r[b] > 0, 0.0)
    else:
        x = r[a]
    Z[key] = d * (x - x.mean()) / x.std(ddof=0)
Z["total"] = Z[[k for k, *_ in CATS]].sum(axis=1)
for i, p in r.iterrows():
    if p.team in (ME, OPP):
        pz[p.player] = {k: float(Z.loc[i, k]) for k in Z.columns}

print(json.dumps({
    "ranks": {t: [int(cats[k]["rank"][t]) for k, *_ in CATS] for t in tot.index},
    "total_z": {t: float(v) for t, v in total.items()},
    "overall": {t: int(v) for t, v in overall.items()},
    "mu": mu,
    "pz": pz,
}, ensure_ascii=False))
