#!/bin/bash
# launchd 에이전트 제거 스크립트

LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

echo "=== DailyB launchd 에이전트 제거 ==="

for plist in com.dailyb.kospi.plist com.dailyb.us.plist com.dailyb.weekly.plist; do
  dst="$LAUNCH_AGENTS/$plist"
  if [ -f "$dst" ]; then
    launchctl unload "$dst" 2>/dev/null || true
    rm "$dst"
    echo "[OK] $plist 제거됨"
  else
    echo "[SKIP] $plist 없음"
  fi
done
