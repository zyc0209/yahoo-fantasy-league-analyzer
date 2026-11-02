#!/bin/bash
# 每日更新：抓 NBA 數據與賽程 → 更新本週日期 → 重算戰力 → 輸出 Dashboard 用的球員檔
# 手動執行：bash ~/fantasy/scripts/daily_update.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
LOG=logs/daily_$(date +%Y%m%d).log
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') 開始每日更新"
  # 抓數據前先備份，失敗時保留舊資料
  mkdir -p data/backup && cp data/nba_stats_*.csv data/nba_schedule_*.csv data/backup/ 2>/dev/null || true
  $PY fetch_nba_stats.py
  $PY scripts/set_week.py
  $PY analysis/power_rankings.py
  $PY analysis/export_roster_stats.py
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') 完成"
} >> "$LOG" 2>&1
# 只保留最近 30 天的紀錄
find logs -name 'daily_*.log' -mtime +30 -delete 2>/dev/null || true
