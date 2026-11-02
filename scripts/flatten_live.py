import json, sys
src, dst = sys.argv[1], sys.argv[2]
d = json.load(open(src))
row = {"week": d["week"], "opponent": "柏淙's Crazy Team", "start": d["start"], "end": d["end"], "as_of": d["as_of"],
       "days_done": ",".join(d["days_done"]), "first_add_date": d["first_add_date"], "drop_default": d["drop_candidates"][0], "note": d["note"]}
for side in ("me", "opp"):
    for k, v in d[side].items():
        row[f"{side}_{k}"] = v
open(dst, "w").write(json.dumps([row], ensure_ascii=False, separators=(",", ":")))
