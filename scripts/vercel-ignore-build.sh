#!/usr/bin/env bash
# Vercel "Ignored Build Step" 스크립트.
#   종료코드 1 → 배포 진행 / 0 → 배포 스킵
#
# 목적: 장중 뉴스 갱신(kospi-news-live·movers-why)이 평일 ~22회 main에 데이터
#       전용 커밋을 푸시하면서 Vercel 무료 플랜의 "일 100회 배포" 한도를 소진해
#       다른 변경(코드·브리핑)까지 배포가 막히는 문제를 해결한다.
#       데이터 전용 커밋(web/data/** 만 변경)은 배포를 건너뛴다. 이 데이터는
#       /api/data(raw.githubusercontent.com/main)로 신선하게 서빙되므로 재배포
#       가 필요 없다.
set -e

# 직전 커밋 대비 변경 파일. 비교 불가(첫 커밋 등) 시 안전하게 배포한다.
CHANGED="$(git diff --name-only HEAD^ HEAD 2>/dev/null || true)"
if [ -z "$CHANGED" ]; then
  echo "변경 파일 판별 불가 → 배포 진행"
  exit 1
fi

echo "변경 파일:"
echo "$CHANGED" | sed 's/^/  - /'

# web/data/ 밖의 파일이 하나라도 있으면 배포, 전부 web/data/ 면 스킵.
if echo "$CHANGED" | grep -qvE '^web/data/'; then
  echo "→ 코드/콘텐츠 변경 포함 → 배포 진행"
  exit 1
fi

echo "→ 데이터 전용 커밋(web/data/**) → 배포 스킵 (데이터는 /api/data로 서빙)"
exit 0
