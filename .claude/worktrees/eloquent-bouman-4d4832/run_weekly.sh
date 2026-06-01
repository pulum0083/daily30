#!/bin/bash
# DailyB — 주간 리포트 실행 스크립트
# launchd에서 매주 일요일 21:00 KST에 호출됨

set -e
PROJECT_DIR="/Users/luke/Service App/DailyB"
LOG_FILE="$PROJECT_DIR/logs/weekly_$(date +%Y%m%d).log"

mkdir -p "$PROJECT_DIR/logs"
exec >> "$LOG_FILE" 2>&1

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] 주간 리포트 시작 ==="

cd "$PROJECT_DIR"
claude --dangerously-skip-permissions -p "$(cat agents/weekly_report.md)"

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] 주간 리포트 완료 ==="
