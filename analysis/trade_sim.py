"""交易模擬：比較交易前後雙方的各項聯盟名次，以及對其他 11 隊的平均預期勝項數。

用法：python3 analysis/trade_sim.py "我送出的球員" "對方球員" [更多組...]
預期勝項：每項勝率 = Φ(差距 / 該項 12 隊間標準差)，對其餘 11 隊取平均後加總 11 項。
"""
from __future__ import annotations

import sys
from math import erf, sqrt

import pandas as pd

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import power_rankings as pr  # noqa: E402


def build():
    league = pr.load_league()
    cats = league["categories"]
    rosters = pr.load_rosters(league)
    stats, _ = pr.load_stats()
    m = rosters.merge(stats, left_on="key", right_index=True, how="left")
    m = m[m["GP_prev"].notna()].copy()
    pool = m.drop_duplicates("key").set_index("key")
    z = pr.player_zscores(pool, cats)
    z["TOTAL"] = z[[c["key"] for c in cats]].sum(axis=1)
    m = m.join(z.add_prefix("z_"), on="key")
    return league, cats, m


def team_table(m, cats, teams):
    act = m[m["active"]]
    return pd.DataFrame({t: pr.team_category_values(act[act["fantasy_team"] == t], cats) for t in teams}).T


def ranks(tv, cats):
    return pd.DataFrame({c["key"]: tv[c["key"]].rank(ascending=not c["higher_better"], method="min").astype(int) for c in cats})


def exp_wins(tv, cats, team, sd):
    phi = lambda x: 0.5 * (1 + erf(x / sqrt(2)))
    total = 0.0
    per = {}
    for c in cats:
        k = c["key"]
        others = tv.drop(index=team)[k]
        diff = (tv.loc[team, k] - others) if c["higher_better"] else (others - tv.loc[team, k])
        p = float((diff / sd[k]).map(phi).mean())
        per[k] = p
        total += p
    return total, per


def main(pairs):
    league, cats, m = build()
    keys = [c["key"] for c in cats]
    teams = [t["name"] for t in league["teams"]]
    me = league["my_team"]
    base = team_table(m, cats, teams)
    sd = base[keys].std(ddof=0)
    rb = ranks(base, cats)

    show = ["PTS", "OREB", "DREB", "AST", "STL", "BLK", "TOV", "FG3M", "MIN"]
    for out_p, in_p in pairs:
        for p in (out_p, in_p):
            r = m[m["player"] == p]
            if r.empty:
                sys.exit(f"找不到球員：{p}")
        partner = m.loc[m["player"] == in_p, "fantasy_team"].iloc[0]
        print(f"\n===== {out_p} → {partner}，換回 {in_p} =====")
        for p in (out_p, in_p):
            r = m[m["player"] == p].iloc[0]
            print(f"  {p:<26} 本季{int(r.GP_cur)}場 上季{int(r.GP_prev)}場  " +
                  " ".join(f"{s}={r[s]:.1f}" for s in show) +
                  f"  FG%={r.FGM/r.FGA:.3f} FT%={r.FTM/max(r.FTA,1e-9):.3f} 3P%={r.FG3M/max(r.FG3A,1e-9):.3f}")
            print(f"  {'':<26} z: " + " ".join(f"{k}={r['z_'+k]:+.1f}" for k in keys) + f"  總={r.z_TOTAL:+.1f}")
        t = m.copy()
        t.loc[t["player"] == out_p, "fantasy_team"] = partner
        t.loc[t["player"] == in_p, "fantasy_team"] = me
        after = team_table(t, cats, teams)
        ra = ranks(after, cats)
        for team in (me, partner):
            eb, _ = exp_wins(base, cats, team, sd)
            ea, per_a = exp_wins(after, cats, team, sd)
            _, per_b = exp_wins(base, cats, team, sd)
            print(f"\n  [{team}] 對其他 11 隊平均預期勝項：{eb:.2f} → {ea:.2f}（{ea-eb:+.2f}）")
            print("    名次：" + "  ".join(f"{k} {rb.loc[team,k]}→{ra.loc[team,k]}" for k in keys))
            print("    勝率變化：" + "  ".join(f"{k} {per_a[k]-per_b[k]:+.0%}" for k in keys if abs(per_a[k]-per_b[k]) >= 0.01))

    # 我的 AST 是否「贏太多」：AST 對其他隊的勝率
    _, per = exp_wins(base, cats, me, sd)
    print("\n目前各項對聯盟平均勝率：" + "  ".join(f"{k} {per[k]:.0%}" for k in keys))


if __name__ == "__main__":
    args = sys.argv[1:]
    main([(args[i], args[i + 1]) for i in range(0, len(args), 2)])
