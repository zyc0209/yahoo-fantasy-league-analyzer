"""依今天日期設定 league.json 的本週週次與日期（每週一到週日）。
第 2 週是 2026-10-26 ~ 11-01，之後每 7 天一週。對手不會自動改，換週時請告訴 Claude 新對手。"""
import json
from datetime import date, timedelta
from pathlib import Path

p = Path(__file__).resolve().parent.parent / "data" / "league.json"
league = json.loads(p.read_text())
week2 = date(2026, 10, 26)
today = date.today()
week = 2 + (today - week2).days // 7 if today >= week2 else 1
start = week2 + timedelta(days=7 * (week - 2))
end = start + timedelta(days=6)
changed = league.get("current_week") != week
league["current_week"] = week
league.setdefault("week_dates", {})[str(week)] = [start.isoformat(), end.isoformat()]
p.write_text(json.dumps(league, ensure_ascii=False, indent=2))
print(f"本週：第 {week} 週 {start} ~ {end}" + ("（換週了，記得更新對手）" if changed else ""))
