#!/bin/bash
# DailyB 초기 세팅 스크립트
set -e

echo "=== DailyB 투자 비서 세팅 ==="

# 1. Python 의존성 설치
echo "[1/4] Python 패키지 설치 중..."
pip3 install -r requirements.txt

# 2. config.json 생성
if [ ! -f "config.json" ]; then
  cp config.example.json config.json
  echo "[2/4] config.json 생성됨 → 직접 편집하여 API 키 입력 필요"
else
  echo "[2/4] config.json 이미 존재"
fi

# 3. 데이터 디렉토리 초기화
mkdir -p data web/briefings web/assets

# 4. briefings.json 초기화
if [ ! -f "data/briefings.json" ]; then
  echo '{"briefings": []}' > data/briefings.json
  echo "[3/4] data/briefings.json 초기화됨"
fi

echo ""
echo "=== 세팅 완료 ==="
echo ""
echo "다음 단계:"
echo "  1. config.json 편집하여 Telegram bot_token, chat_id 입력"
echo "  2. gcp_credentials.json 파일을 이 디렉토리에 복사"
echo "  3. config.json의 google_sheets.spreadsheet_id 입력"
echo "  4. config.json의 web.base_url 입력"
echo ""
echo "수동 테스트:"
echo "  python3 scripts/fetch_data.py --type kospi"
echo "  python3 scripts/holiday_check.py --market kospi"
echo ""
