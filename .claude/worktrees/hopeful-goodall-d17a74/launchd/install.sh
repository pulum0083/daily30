#!/bin/bash
# launchd 에이전트 설치 스크립트
# 실행: bash launchd/install.sh

PLIST_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

mkdir -p "$LAUNCH_AGENTS"
mkdir -p "/Users/luke/Service App/DailyB/logs"

echo "=== DailyB launchd 에이전트 설치 ==="

for plist in com.dailyb.kospi.plist com.dailyb.us.plist com.dailyb.weekly.plist; do
  src="$PLIST_DIR/$plist"
  dst="$LAUNCH_AGENTS/$plist"

  # 기존 등록 해제 (실패해도 무시)
  launchctl unload "$dst" 2>/dev/null || true

  cp "$src" "$dst"
  launchctl load "$dst"
  echo "[OK] $plist 등록 완료"
done

echo ""
echo "=== 등록된 에이전트 ==="
launchctl list | grep com.dailyb

echo ""
echo "수동 실행 테스트:"
echo "  launchctl start com.dailyb.kospi"
echo "  launchctl start com.dailyb.us"
echo "  launchctl start com.dailyb.weekly"
echo ""
echo "등록 해제:"
echo "  bash launchd/uninstall.sh"
