#!/bin/bash
# DailyB — 미국 시장 브리핑 실행 스크립트
# launchd에서 매주 월~금 22:30 KST에 호출됨

PROJECT_DIR="/Users/luke/Service App/DailyB"
LOG_FILE="$PROJECT_DIR/logs/us_$(date +%Y%m%d).log"

mkdir -p "$PROJECT_DIR/logs"
exec >> "$LOG_FILE" 2>&1

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] 미국 시장 브리핑 시작 ==="

# 1. 미국 시장 휴장 확인
python3 "$PROJECT_DIR/scripts/holiday_check.py" --market us
if [ $? -ne 0 ]; then
  echo "[SKIP] 미국 시장 휴장일 — 브리핑 생성 안 함"
  exit 0
fi

cd "$PROJECT_DIR"
mkdir -p data web/briefings

# 2. 시장 데이터 사전 수집
python3 "$PROJECT_DIR/scripts/fetch_data.py" --type us

# 3. 뉴스 요약 (Gemini Flash)
python3 "$PROJECT_DIR/scripts/fetch_news.py" --type us || echo "[WARN] 뉴스 수집 실패 (무시)"

# 4. Claude 분석 생성 + HTML 저장
python3 "$PROJECT_DIR/scripts/call_claude.py" --type us

# 5. latest.json 업데이트 (구독자 즉시 발송용)
python3 "$PROJECT_DIR/scripts/update_latest.py" --type us || echo "[WARN] latest.json 업데이트 실패 (무시)"

# 6. Telegram 전송
python3 "$PROJECT_DIR/scripts/send_telegram.py" --type us || echo "[WARN] Telegram 전송 실패 (무시)"

# 7. 이메일 발송
python3 "$PROJECT_DIR/scripts/send_email.py" --type us || echo "[WARN] 이메일 발송 실패 (무시)"

# 8. Git 커밋 & 푸시
git config user.email "dailyb-bot@users.noreply.github.com"
git config user.name "DailyB Bot"
git add web/ data/
git diff --staged --quiet || git commit -m "🇺🇸 미국 브리핑: $(TZ=Asia/Seoul date +'%Y-%m-%d %H:%M KST')"
git push || echo "[WARN] git push 실패"

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] 미국 시장 브리핑 완료 ==="
