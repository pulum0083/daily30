#!/bin/bash
# DailyB — 코스피 시초가 브리핑 실행 스크립트
# launchd에서 매주 월~금 08:30 KST에 호출됨

PROJECT_DIR="/Users/luke/Service App/DailyB"
LOG_FILE="$PROJECT_DIR/logs/kospi_$(date +%Y%m%d).log"

mkdir -p "$PROJECT_DIR/logs"
exec >> "$LOG_FILE" 2>&1

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] 코스피 브리핑 시작 ==="

# 1. 한국 시장 휴장 확인
python3 "$PROJECT_DIR/scripts/holiday_check.py" --market kospi
if [ $? -ne 0 ]; then
  echo "[SKIP] 한국 시장 휴장일 — 브리핑 생성 안 함"
  exit 0
fi

cd "$PROJECT_DIR"
mkdir -p data web/briefings

# 2. 시장 데이터 사전 수집
python3 "$PROJECT_DIR/scripts/fetch_data.py" --type kospi

# 3. Claude 브리핑 생성
claude --dangerously-skip-permissions -p "$(cat agents/kospi_morning.md)"

# 4. Telegram 전송
python3 "$PROJECT_DIR/scripts/send_telegram.py" --type kospi || echo "[WARN] Telegram 전송 실패 (무시)"

# 5. Git 커밋 & 푸시
git config user.email "dailyb-bot@users.noreply.github.com"
git config user.name "DailyB Bot"
git add web/ data/
git diff --staged --quiet || git commit -m "📊 코스피 브리핑: $(TZ=Asia/Seoul date +'%Y-%m-%d %H:%M KST')"
git push || echo "[WARN] git push 실패"

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] 코스피 브리핑 완료 ==="
