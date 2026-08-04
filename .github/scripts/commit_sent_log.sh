#!/usr/bin/env bash
# 텔레그램 발송 기록(data/telegram_sent_log.json)만 main에 커밋해 중복 발송 가드를 살려둔다.
#
# 배경(SERVICE_RULES §32): mark_sent_today()는 전송 스텝에서 파일을 쓰는데,
# 2026-07-02 b257bdc9가 전송을 커밋 스텝 *뒤*로 옮기면서(페이지가 라이브인 걸 확인한 뒤
# 보내야 하므로 이 순서 자체는 옳다) 그 기록이 커밋되지 않게 됐다. 가드는 fail-open이라
# 한 달간 조용히 죽어 있었다. 순서를 되돌릴 수 없으니 전송 뒤에 이 한 파일만 따로 커밋한다.
#
# 실패해도 잡을 되돌리지 않는다 — 기록이 유실되면 다음 실행에서
# send_telegram._warn_if_guard_is_dead()가 경고를 낸다(무음 실패 방지).
set -euo pipefail

BRIEFING_TYPE="${1:?사용법: commit_sent_log.sh <briefing_type>}"
LOG_FILE="data/telegram_sent_log.json"

git config user.email "dailyb-bot@users.noreply.github.com"
git config user.name "DailyB Bot"

git add "$LOG_FILE"
if git diff --staged --quiet; then
  echo "발송 기록 변경 없음 — 전송이 실패했거나 이미 기록된 상태"
  exit 0
fi

git commit -m "data: 텔레그램 발송 기록 ${BRIEFING_TYPE} $(TZ=Asia/Seoul date +'%Y-%m-%d %H:%M KST')"

# --autostash: 이 시점 워킹트리엔 다른 스텝이 만든 미스테이지 변경이 남아 있고,
# rebase는 겹치는 파일이 없어도 그것 때문에 거부된다(§18).
for i in 1 2 3; do
  git fetch origin main
  if git rebase --autostash origin/main && git push; then
    echo "✓ 발송 기록 커밋 완료"
    exit 0
  fi
  git rebase --abort 2>/dev/null || true
  echo "push 시도 $i 실패 — 10초 후 재시도"
  sleep 10
done

echo "::warning::발송 기록 push 3회 실패 — 중복 발송 가드가 다음 실행에서 경고를 냅니다"
exit 1
